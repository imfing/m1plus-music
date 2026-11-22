/* M1+ Music Crossfade: dual-decoder real-time track overlap inside hciplayer (docs/modules/crossfade.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Built with PEQ_PLAYER into hciplayer's payload (no .bss: per-instance state lives in player_state on the heap).
 *
 * Stock hciplayer's PreInitNextSong (0x42b834) opens the next track's stream, demuxer, d_audio and sh_audio into a
 * second MPContext at 0xaf9b90 (next_mpctx) and sets NEXT_STATE (0xb10dd0) = 2 once done. During the final D seconds
 * of Track A, this stage initializes next_mpctx->sh_audio's codec via stock's init_best_audio_codec (0x47eb50, setting
 * NEXT_CODEC_INITED 0xb10d70 = 1 so stock's gapless swap skips re-init and stock's uninit_next_song frees it on cancel),
 * decodes Track B into next_sh->a_buffer in lockstep with Track A, matches Track B's ReplayGain (from 0xb0c790),
 * converts Track B with swr (patch/xfsrc.c) when sample rates differ, and mixes with an equal-power cos/sin curve.
 * Leftover decoded frames stay in next_sh->a_buffer and are played first after the gapless swap (sample-accurate).
 */
#include "xfade.h"

/* Pinned hciplayer addresses (tools/mod_player.py PINS). */
#define MPCTX (*(char *volatile *)0xaf9e30u)
#define NEXT_MPCTX ((char *)0xaf9b90u)
#define NEXT_STATE (*(volatile int *)0xb10dd0u) /* 0 idle, 1 preloading, 2 preloaded ready */
#define NEXT_FLAG (*(volatile int *)0xb10de0u) /* 1 preload requested */
#define NEXT_CODEC_INITED (*(volatile int *)0xb10d70u) /* 1 init_best_audio_codec already ran on next_sh */
#define MQA_MODE (*(volatile int *)0xb10c54u) /* 2 = MQA */
#define ACODEC_LIST (*(char **volatile *)0xb10c4cu)
#define AFM_LIST (*(char **volatile *)0xb10c28u)
#define RG_MODE (*(volatile int *)0xb10e30u) /* 0 off, 1 track, 2 album */
#define RG_NEXT ((const volatile int *)0xb0c790u) /* {track_gain, track_peak, album_gain, album_peak} in 1e-5 units */
#define INIT_BEST_ACODEC 0x47eb50u /* int (void *sh_audio, char **ac_list, char **afm_list) */
#define UNINIT_NEXT 0x42a9ccu /* void (void): frees next_mpctx (calls uninit_audio if NEXT_CODEC_INITED == 1) */
#define DEMUX_LEN 0x486914u /* double (void *demuxer) */
/* The vendor's FLAC seek trim: demux_audio's FLAC seek stores the target time here and flac_decode_frame (0x5b6508)
 * rejects every frame starting before it, until demux_audio's close clears it. Track A's seek must not trim Track B. */
#define FLAC_SEEK_TRIM (*(volatile float *)0xb15290u)

#define AF_FORMAT_FLOAT 0x1d
#define HALF_PI 1.57079632679489661923
#define RG_UNSET ((int)0x80000000u)
#define SEEK_BACK_S 0.5 /* backward jump larger than this aborts active crossfade and re-preloads */
#define MIN_TRACK_S 10.0 /* never crossfade short clips (< 10 s, matching demo's xfadeset.c) */

enum { FK_NONE, FK_FLOAT, FK_S16, FK_S24, FK_S32, FK_U8 };

/* Same MPlayer af format bitmask decoding as patch/vu.c. */
static int fmt_kind(int format, int bps) {
    if (format == AF_FORMAT_FLOAT) return bps == 4 ? FK_FLOAT : FK_NONE;
    if ((format & ~63) || !(format & 1) || (format & 4) || bps * 8 != (((format >> 3) & 7) + 1) * 8) return FK_NONE;
    if (format & 2) return bps == 1 ? FK_U8 : FK_NONE;
    return bps == 2 ? FK_S16 : bps == 3 ? FK_S24 : bps == 4 ? FK_S32 : FK_NONE;
}

static inline float read_sample(const void *buf, int k, unsigned idx) {
    if (k == FK_FLOAT) {
        float v = ((const float *)buf)[idx];
        return (v >= -3.0e38f && v <= 3.0e38f) ? v : 0.0f;
    }
    if (k == FK_S16) return (float)((const short *)buf)[idx] * (1.0f / 32768.0f);
    if (k == FK_S32) return (float)((double)((const int *)buf)[idx] * (1.0 / 2147483648.0));
    if (k == FK_U8) return (float)((int)((const unsigned char *)buf)[idx] - 128) * (1.0f / 128.0f);
    /* FK_S24 */
    const unsigned char *b = (const unsigned char *)buf + idx * 3;
    int s = (int)(b[0] | (b[1] << 8) | ((int)(signed char)b[2] << 16));
    return (float)s * (1.0f / 8388608.0f);
}

/* Gentle soft clip above +/-0.95 for native integer output so summing two hot tracks never wraps or hard-clips. */
static inline float soft_clip(float x) {
    if (!(x >= -3.0e38f && x <= 3.0e38f)) return 0.0f;
    if (x > 0.95f) {
        float d = x - 0.95f;
        return 0.95f + 0.05f * (d / (d + 0.05f));
    }
    if (x < -0.95f) {
        float d = -0.95f - x;
        return -0.95f - 0.05f * (d / (d + 0.05f));
    }
    return x;
}

static inline void write_sample(void *buf, int k, unsigned idx, float v) {
    if (k == FK_FLOAT) {
        ((float *)buf)[idx] = (v >= -3.0e38f && v <= 3.0e38f) ? v : 0.0f;
        return;
    }
    v = soft_clip(v);
    if (k == FK_S16) {
        int s = (int)(v * 32767.0f + (v >= 0 ? 0.5f : -0.5f));
        if (s > 32767) s = 32767;
        if (s < -32768) s = -32768;
        ((short *)buf)[idx] = (short)s;
    } else if (k == FK_S32) {
        double d = (double)v * 2147483647.0;
        if (d > 2147483647.0) d = 2147483647.0;
        if (d < -2147483648.0) d = -2147483648.0;
        ((int *)buf)[idx] = (int)d;
    } else if (k == FK_U8) {
        int s = (int)(v * 127.0f + 128.5f);
        if (s > 255) s = 255;
        if (s < 0) s = 0;
        ((unsigned char *)buf)[idx] = (unsigned char)s;
    } else { /* FK_S24 */
        int s = (int)(v * 8388607.0f + (v >= 0 ? 0.5f : -0.5f));
        if (s > 8388607) s = 8388607;
        if (s < -8388608) s = -8388608;
        unsigned char *b = (unsigned char *)buf + idx * 3;
        b[0] = (unsigned char)(s & 0xff);
        b[1] = (unsigned char)((s >> 8) & 0xff);
        b[2] = (unsigned char)((s >> 16) & 0xff);
    }
}

int xfade_load(xfade_record *r) {
    memset(r, 0, sizeof *r);
    void *f = fopen(XFADE_FILE, "rb");
    if (!f) return 0;
    char extra;
    int ok = fread(r, 1, sizeof *r, f) == sizeof *r && fread(&extra, 1, 1, f) == 0;
    if (fclose(f)) ok = 0;
    if (!ok || memcmp(r->magic, XFADE_MAGIC, 8) || r->seconds < 0 || r->seconds > XFADE_MAX_SEC) {
        memset(r, 0, sizeof *r);
        return 0;
    }
    return 1;
}

/* Decoded position of the audio block currently entering play() (seconds), or -1 if unavailable: stock's calc_a_pts
 * (0x44600c) less what the decoder's buffer still holds. A decoder with timestamps: sh_audio->pts plus the bytes decoded
 * since (pts_bytes). One without (pts is MP_NOPTS_VALUE, and pts_bytes counts from the start or the last seek): the last
 * packet's pts from the demuxer plus, at a constant bitrate, the packet data read but not decoded yet; the decoded
 * bytes count only when the demuxer has nothing either. */
static double track_a_pos(void) {
    char *mp = MPCTX, *sh = mp ? *(char **)(mp + 0x2c) : 0;
    if (!sh) return -1.0;
    double pts = *(double *)(sh + 0x20);
    int obps = *(int *)(sh + 0x4c);
    int pts_bytes = *(int *)(sh + 0xd0);
    int abuf_len = *(int *)(sh + 0x6c);
    if (!(pts >= -1e12 && pts <= 1e12)) {
        char *ds = *(char **)(mp + 0x34);
        if (!ds) return -1.0;
        int ibps = *(int *)(sh + 0x50); /* sh_audio->i_bps */
        pts = *(double *)(ds + 0x10);
        if (!(pts >= -1e12 && pts <= 1e12)) return -1.0;
        if (pts != 0.0 || ibps || !pts_bytes) {
            /* ds_tell_pts: pts_bytes (+0x18) - buffer_size (+4) + buffer_pos (+0); sh_audio->a_in_buffer_len (+0x5c) */
            int ahead = *(int *)(ds + 0x18) - *(int *)(ds + 4) + *(int *)ds - *(int *)(sh + 0x5c);
            if (ibps) pts += (double)ahead / (double)ibps;
            pts_bytes = 0;
        }
    }
    if (obps > 0) pts += (double)(pts_bytes - abuf_len) / (double)obps;
    return pts >= 0.0 ? pts : 0.0;
}

static double track_a_duration(void) {
    char *mp = MPCTX, *demux = mp ? *(char **)(mp + 0x28) : 0;
    if (!demux) return 0.0;
    double d = ((double (*)(void *))DEMUX_LEN)(demux);
    return (d > 0.0 && d < 1e8) ? d : 0.0;
}

static double track_b_duration(void) {
    char *demux = *(char **)(NEXT_MPCTX + 0x28);
    if (!demux) return 0.0;
    double d = ((double (*)(void *))DEMUX_LEN)(demux);
    return (d > 0.0 && d < 1e8) ? d : 0.0;
}

/* Exact ReplayGain linear multiplier for Track B from 0xb0c790 (matches stock 0x428354..0x428480). */
static double next_rg_gain(void) {
    int mode = RG_MODE;
    if (mode != 1 && mode != 2) return 1.0;
    int gain_i = mode == 1 ? RG_NEXT[0] : RG_NEXT[2];
    unsigned peak_u = mode == 1 ? (unsigned)RG_NEXT[1] : (unsigned)RG_NEXT[3];
    if (mode == 1 && gain_i == RG_UNSET) {
        gain_i = RG_NEXT[2];
        peak_u = (unsigned)RG_NEXT[3];
    }
    if (gain_i == RG_UNSET || gain_i == 100000) return 1.0;
    if (!peak_u) peak_u = 100000u;
    double gdb = (double)gain_i * 1e-5;
    double peak = (double)(int)(peak_u > 0x7fffffffu ? 0x7fffffffu : peak_u) * 1e-5;
    if (gdb < -60.0 || gdb > 24.0) return 1.0;
    double lin = pow(10.0, gdb * 0.05);
    if (peak > 1e-6 && lin * peak > 1.0) lin = 1.0 / peak;
    return (lin > 0.0 && lin <= 16.0) ? lin : 1.0;
}

static int codec_blocked(char *sh) {
    char *codec = *(char **)(sh + 4);
    if (!codec) return 1;
    const char *name = *(char **)(codec + 0x3d0), *drv = *(char **)(codec + 0x3e0);
    if (!drv) return 1;
    if (!strcmp(drv, "dsdiff") || !strcmp(drv, "hwac3") || !strcmp(drv, "hwmpa") || !strcmp(drv, "spdif")) return 1;
    if (name && strlen(name) >= 5 && !memcmp(name, "ffdsd", 5)) return 1;
    return 0;
}

/* Block-local read cursor over next_mpctx->sh_audio->a_buffer: frames advance off in O(1) and unconsumed bytes
 * are compacted only on refill or once when process_block() exits (keeping a_buffer exact for stock's handoff). */
typedef struct {
    char *sh;
    char *abuf;
    int off;
    int len;
    int size;
} b_reader;

static void compact_buf(char *abuf, int off, int len) {
    int rem = len - off;
    if (rem <= 0 || off <= 0) return;
    if (rem <= off) {
        memcpy(abuf, abuf + off, (unsigned)rem);
        return;
    }
    int i = 0;
    if (!(((unsigned)abuf | (unsigned)off) & 3u)) {
        int wrem = rem & ~3;
        for (; i < wrem; i += 4) *(unsigned *)(abuf + i) = *(unsigned *)(abuf + off + i);
    }
    for (; i < rem; ++i) abuf[i] = abuf[off + i];
}

static void b_open(b_reader *b) {
    memset(b, 0, sizeof *b);
    if (NEXT_STATE != 2) return;
    char *sh = *(char **)(NEXT_MPCTX + 0x2c);
    if (!sh) return;
    b->sh = sh;
    b->abuf = *(char **)(sh + 0x68);
    b->len = *(int *)(sh + 0x6c);
    b->size = *(int *)(sh + 0x70);
}

static void b_flush(b_reader *b) {
    if (!b->sh || !b->abuf || b->off <= 0) return;
    if (NEXT_STATE != 2 || *(char **)(NEXT_MPCTX + 0x2c) != b->sh) return;
    int rem = b->len - b->off;
    if (rem < 0) rem = 0;
    if (rem > 0) compact_buf(b->abuf, b->off, b->len);
    /* ad_driver already advanced pts_bytes when decoding into a_buffer; leaving a_buffer_len exact ensures
     * playing_audio_pts (pts + (pts_bytes - a_buffer_len)/o_bps) matches the handoff. */
    *(int *)(b->sh + 0x6c) = rem;
    b->len = rem;
    b->off = 0;
}

/* Pull one stereo float frame (scaled by b_rg) from next_mpctx->sh_audio->a_buffer, decoding more if needed.
 * Returns 1 on success, 0 on EOF/error (out set to 0). Unconsumed bytes remain in a_buffer for handoff. */
static int pull_b_frame(xfade_dsp *x, b_reader *b, float out[2]) {
    out[0] = out[1] = 0.0f;
    if (x->b_eof) return 0;
    int frame_bytes = x->b_bps * x->b_ch;
    if (!b->sh || !b->abuf || frame_bytes <= 0 || b->size < frame_bytes) {
        x->b_eof = 1;
        return 0;
    }
    if (b->len - b->off < frame_bytes) {
        int rem = b->len - b->off;
        if (rem < 0) rem = 0;
        if (rem > 0 && b->off > 0) compact_buf(b->abuf, b->off, b->len);
        b->len = rem;
        b->off = 0;
        *(int *)(b->sh + 0x6c) = rem;
        char *drv = *(char **)(b->sh + 0x88);
        int (*dec)(void *, void *, int, int) = drv ? *(int (**)(void *, void *, int, int))(drv + 0x14) : 0;
        if (!dec) {
            x->b_eof = 1;
            return 0;
        }
        int room = b->size - b->len;
        int want = frame_bytes * 256;
        if (want > room) want = room;
        if (want < frame_bytes) {
            x->b_eof = 1;
            return 0;
        }
        float trim = FLAC_SEEK_TRIM;
        FLAC_SEEK_TRIM = 0.0f;
        int got = dec(b->sh, b->abuf + b->len, want, room);
        FLAC_SEEK_TRIM = trim;
        if (got <= 0) {
            x->b_eof = 1;
            return 0;
        }
        b->len += got;
        *(int *)(b->sh + 0x6c) = b->len;
        if (b->len - b->off < frame_bytes) {
            x->b_eof = 1;
            return 0;
        }
    }
    const void *p = b->abuf + b->off;
    float l = read_sample(p, x->b_fmt, 0) * (float)x->b_rg;
    float r = x->b_ch > 1 ? read_sample(p, x->b_fmt, 1) * (float)x->b_rg : l;
    out[0] = l;
    out[1] = r;
    b->off += frame_bytes;
    return 1;
}

/* Produce one stereo float frame at Track A's sample rate: direct when the rates match, else through the swr converter,
 * which is fed XF_SRC_CHUNK frames at a time (its output waits in the converter's fifo, which goes on to Track B's own
 * instance). Returns 1 on success, 0 once Track B reaches EOF. */
static int next_b_sample(xfade_dsp *x, b_reader *b, float out[2]) {
    xf_src *s = x->src;
    if (!s) return pull_b_frame(x, b, out);
    while (!s->count) {
        float in[2 * XF_SRC_CHUNK];
        int n = 0;
        for (; n < XF_SRC_CHUNK; ++n) {
            float f[2];
            if (!pull_b_frame(x, b, f)) break;
            in[2 * n] = f[0];
            in[2 * n + 1] = f[1];
        }
        if (!n) {
            out[0] = out[1] = 0.0f;
            return 0;
        }
        if (s->nch == 1)
            for (int i = 0; i < n; ++i) in[i] = in[2 * i];
        xfsrc_fill(s, in, n);
    }
    const float *f = s->fifo + s->head * s->nch;
    out[0] = f[0];
    out[1] = s->nch > 1 ? f[1] : f[0];
    ++s->head;
    if (!--s->count) s->head = 0;
    return 1;
}

/* Try to start crossfade on the preloaded next_mpctx. Returns 1 if active, 0 if ineligible. */
static int try_start(xfade_dsp *x, double eff_dur) {
    if (NEXT_STATE != 2 || MQA_MODE == 2) return 0;
    char *sh = *(char **)(NEXT_MPCTX + 0x2c);
    if (!sh) return 0;
    if (!NEXT_CODEC_INITED) {
        float trim = FLAC_SEEK_TRIM;
        FLAC_SEEK_TRIM = 0.0f;
        int ok = ((int (*)(void *, void *, void *))INIT_BEST_ACODEC)(sh, ACODEC_LIST, AFM_LIST);
        FLAC_SEEK_TRIM = trim;
        if (!ok) {
            x->next_bad = 1;
            return 0;
        }
        NEXT_CODEC_INITED = 1;
    }
    if (codec_blocked(sh)) {
        x->next_bad = 1;
        return 0;
    }
    int brate = *(int *)(sh + 0x3c);
    int bbps = *(int *)(sh + 0x40);
    int bch = *(int *)(sh + 0x44);
    int bfmt = *(int *)(sh + 0x38);
    int bk = fmt_kind(bfmt, bbps);
    if (bk == FK_NONE || brate < 8000 || brate > 384000 || bch < 1 || bch > 2) {
        x->next_bad = 1;
        return 0;
    }
    x->b_rate = brate;
    x->b_ch = bch;
    x->b_fmt = bk;
    x->b_bps = bbps;
    x->b_rg = next_rg_gain();
    xfsrc_free(x->src);
    x->src = brate == x->rate ? 0 : xfsrc_new(brate, x->rate, bch);
    if (brate != x->rate && !x->src) {
        x->next_bad = 1;
        return 0;
    }
    x->b_eof = 0;
    x->pos_frames = 0;
    x->dur_s = eff_dur;
    x->tot_frames = (int)(eff_dur * (double)x->rate + 0.5);
    if (x->tot_frames < 1) x->tot_frames = 1;
    x->ga = 1.0;
    x->gb = 0.0;
    x->hold[0] = x->hold[1] = 0.0f;
    x->state = XF_ACTIVE;
    xf_note_fade(1);
    return 1;
}

static void start_abort(xfade_dsp *x, int re_preload) {
    x->abort_tot = x->rate / 50; /* 20 ms ramp */
    if (x->abort_tot < 1) x->abort_tot = 1;
    x->abort_left = x->abort_tot;
    x->abort_ga0 = x->ga;
    x->abort_gb0 = x->gb;
    x->state = XF_ABORT;
    xfsrc_free(x->src);
    x->src = 0;
    xf_note_fade(0);
    if (re_preload && NEXT_STATE == 2) {
        ((void (*)(void))UNINIT_NEXT)();
        NEXT_CODEC_INITED = 0;
        NEXT_STATE = 0;
        NEXT_FLAG = 1; /* main loop runs PreInitNextSong fresh from 0:00 */
    }
    x->checked_seq = 0;
    x->next_bad = 0;
    x->b_total_s = -1.0;
}

static void force_eof(void) {
    char *mp = MPCTX;
    if (!mp) return;
    char *ds = *(char **)(mp + 0x34);
    if (ds) *(volatile int *)(ds + 0x1c) = 1; /* d_audio->eof = 1 */
    *(volatile int *)(mp + 0x14) = 1; /* mpctx->eof = PT_NEXT_ENTRY */
}

void xfade_release(xfade_dsp *x) {
    xfsrc_free(x->src);
    x->src = 0;
}

xf_src *xfade_take_src(xfade_dsp *x) {
    xf_src *s = x->src;
    if (x->state != XF_ACTIVE && x->state != XF_DONE) return 0;
    x->src = 0;
    return s;
}

void xfade_reset(xfade_dsp *x, int rate, int channels, int fmt, int bps) {
    xfade_release(x);
    memset(x, 0, sizeof *x);
    x->rate = rate;
    x->channels = channels;
    x->fmt = fmt_kind(fmt, bps);
    x->bps = bps;
    x->total_s = track_a_duration();
    x->b_total_s = -1.0;
    x->last_pos = -1.0;
    x->last_check = -1.0;
}

int xfade_carry_out(const xfade_dsp *x, xfade_carry *c) {
    memset(c, 0, sizeof *c);
    if (x->state != XF_ACTIVE || !x->tot_frames) return 0;
    double u = (double)x->pos_frames / (double)x->tot_frames;
    if (u <= 0.0 || u >= 0.995) return 0;
    c->active = 1;
    c->u = u;
    c->dur = x->dur_s;
    return 1;
}

void xfade_carry_in(xfade_dsp *x, const xfade_carry *c) {
    if (!c || !c->active || c->u <= 0.0 || c->u >= 0.995 || x->rate < 8000) return;
    double dur = c->dur;
    double rem = (1.0 - c->u) * dur;
    if (rem > 3.0) {
        rem = 3.0;
        dur = rem / (1.0 - c->u);
    }
    if (rem < 0.02) return;
    x->dur_s = dur;
    x->tot_frames = (int)(dur * (double)x->rate + 0.5);
    if (x->tot_frames < 1) x->tot_frames = 1;
    x->pos_frames = (int)(c->u * (double)x->tot_frames);
    if (x->pos_frames >= x->tot_frames) return;
    x->state = XF_TAIL_IN;
}

/* Update state before processing a block of frames; returns 0 if no samples need touching. */
static int prepare(xfade_dsp *x, unsigned frames) {
    if (x->fmt == FK_NONE || x->channels < 1 || x->channels > 2 || x->rate < 8000 || !frames) return 0;
    double pos = track_a_pos();
    if (x->state == XF_ACTIVE) {
        if (NEXT_STATE != 2) {
            /* mcl-closegapless cancelled the preload mid-fade */
            start_abort(x, 0);
        } else if (pos >= 0.0 && x->last_pos >= 0.0 && pos < x->last_pos - SEEK_BACK_S) {
            /* user sought backward out of the fade window */
            start_abort(x, 1);
        }
        if (pos >= 0.0) x->last_pos = pos;
        return 1;
    }
    if (x->state == XF_ABORT || x->state == XF_TAIL_IN || x->state == XF_DONE) {
        if (pos >= 0.0) x->last_pos = pos;
        return 1;
    }
    /* XF_IDLE: only inspect /tmp/m1plus-xfade once a preload is ready (NEXT_STATE == 2). */
    if (pos >= 0.0) x->last_pos = pos;
    if (NEXT_STATE != 2) {
        x->checked_seq = 0;
        x->next_sec = 0;
        x->next_bad = 0;
        x->b_total_s = -1.0;
        x->last_check = -1.0;
        return 0;
    }
    if (x->next_bad) return 0;
    int due = pos >= 0.0 && (x->last_check < 0.0 || pos - x->last_check >= 0.5 || pos < x->last_check);
    if (x->total_s < MIN_TRACK_S) {
        /* A length the demuxer did not know when the track started is asked for again, every 0.5 s. */
        if (due) {
            x->last_check = pos;
            x->total_s = track_a_duration();
            due = 0;
        }
        if (x->total_s < MIN_TRACK_S) return 0;
    }
    if (!x->checked_seq || due) {
        xfade_record r;
        if (pos >= 0.0) x->last_check = pos;
        if (xfade_load(&r) && r.seconds > 0) {
            int seq = r.seq ? r.seq : 1;
            if (seq == x->bad_seq) {
                x->next_sec = 0;
                x->checked_seq = seq;
                return 0;
            }
            x->next_sec = r.seconds;
            x->checked_seq = seq;
        } else {
            x->next_sec = 0;
            x->checked_seq = -1;
            return 0;
        }
    }
    if (x->next_sec <= 0) return 0;
    if (pos < 0.0) return 0;
    if (x->b_total_s < 0.0) x->b_total_s = track_b_duration();
    if (x->b_total_s > 0.0 && x->b_total_s < MIN_TRACK_S) {
        x->next_bad = 1;
        return 0;
    }
    double eff = (double)x->next_sec;
    double max_eff = (x->total_s - 4.0) * 0.5;
    if (x->b_total_s > 0.0) {
        double max_b = (x->b_total_s - 4.0) * 0.5;
        if (max_b < max_eff) max_eff = max_b;
    }
    if (max_eff < 1.0) return 0;
    if (eff > max_eff) eff = max_eff;
    double rem = x->total_s - pos;
    if (rem <= eff && rem > 0.05) {
        if (try_start(x, rem < eff ? rem : eff)) return 1;
    }
    return 0;
}

static void step_frame(xfade_dsp *x, b_reader *b, float a_in[2], float out[2]) {
    if (x->state == XF_DONE) {
        float bb[2];
        next_b_sample(x, b, bb);
        out[0] = bb[0];
        out[1] = bb[1];
    } else if (x->state == XF_ABORT) {
        double frac = (double)x->abort_left / (double)x->abort_tot; /* 1 -> 0 */
        double ga = 1.0 + (x->abort_ga0 - 1.0) * frac;
        double gb = x->abort_gb0 * frac;
        out[0] = (float)(ga * a_in[0] + gb * x->hold[0]);
        out[1] = (float)(ga * a_in[1] + gb * x->hold[1]);
        if (--x->abort_left == 0) {
            x->state = XF_IDLE;
            x->ga = 1.0;
            x->gb = 0.0;
        }
    } else if (x->state == XF_TAIL_IN) {
        double u = (double)x->pos_frames / (double)x->tot_frames;
        if (u >= 1.0) {
            x->state = XF_IDLE;
            out[0] = a_in[0];
            out[1] = a_in[1];
            return;
        }
        double gb = sin(HALF_PI * u);
        out[0] = (float)(gb * a_in[0]);
        out[1] = (float)(gb * a_in[1]);
        if (++x->pos_frames >= x->tot_frames) x->state = XF_IDLE;
    } else {
        out[0] = a_in[0];
        out[1] = a_in[1];
    }
}

/* Optimized block processor: avoids per-sample cos/sin by stepping a 2D rotation oscillator in XF_ACTIVE. */
static void step_active_rot(xfade_dsp *x, double *ga, double *gb, double *dc, double *ds, int *init) {
    if (!*init) {
        double u = (double)x->pos_frames / (double)x->tot_frames;
        if (u > 1.0) u = 1.0;
        double ang = HALF_PI * u;
        double step = HALF_PI / (double)x->tot_frames;
        *ga = cos(ang);
        *gb = sin(ang);
        *dc = cos(step);
        *ds = sin(step);
        *init = 1;
    }
}

static int process_block(xfade_dsp *x, void *audio, unsigned frames, int is_float) {
    if (!prepare(x, frames)) return 0;
    int ch = x->channels, k = is_float ? FK_FLOAT : x->fmt;
    double ga = 1.0, gb = 0.0, dc = 1.0, ds = 0.0;
    int rot_init = 0;
    b_reader b;
    memset(&b, 0, sizeof b);
    if (x->state == XF_ACTIVE || x->state == XF_DONE) b_open(&b);
    for (unsigned i = 0; i < frames; ++i) {
        if (x->state == XF_IDLE) break;
        float a[2], out[2];
        if (is_float) {
            float *fa = audio;
            a[0] = fa[i * (unsigned)ch];
            a[1] = ch > 1 ? fa[i * (unsigned)ch + 1] : a[0];
        } else {
            a[0] = read_sample(audio, k, i * (unsigned)ch);
            a[1] = ch > 1 ? read_sample(audio, k, i * (unsigned)ch + 1) : a[0];
        }
        if (x->state == XF_ACTIVE) {
            step_active_rot(x, &ga, &gb, &dc, &ds, &rot_init);
            float bb[2];
            if (!next_b_sample(x, &b, bb)) {
                /* Track B ended early during overlap: do not fade A to silence or force_eof A.
                 * Mark this preload's seq ineligible, re-preload Track B from 0:00, and restore Track A. */
                x->bad_seq = x->checked_seq;
                x->ga = ga;
                x->gb = gb;
                if (x->pos_frames == 0) {
                    if (NEXT_STATE == 2) {
                        ((void (*)(void))UNINIT_NEXT)();
                        NEXT_CODEC_INITED = 0;
                        NEXT_STATE = 0;
                        NEXT_FLAG = 1;
                    }
                    x->checked_seq = 0;
                    x->next_bad = 0;
                    x->b_total_s = -1.0;
                    x->state = XF_IDLE;
                    x->ga = 1.0;
                    x->gb = 0.0;
                    b.sh = 0;
                    if (i == 0) return 0;
                    break;
                }
                start_abort(x, 1);
                b.sh = 0;
                step_frame(x, &b, a, out);
            } else {
                x->hold[0] = bb[0];
                x->hold[1] = bb[1];
                x->ga = ga;
                x->gb = gb;
                out[0] = (float)(ga * a[0] + gb * bb[0]);
                out[1] = (float)(ga * a[1] + gb * bb[1]);
                double nga = ga * dc - gb * ds;
                double ngb = gb * dc + ga * ds;
                ga = nga > 0.0 ? nga : 0.0;
                gb = ngb < 1.0 ? ngb : 1.0;
                if (++x->pos_frames >= x->tot_frames) {
                    x->ga = 0.0;
                    x->gb = 1.0;
                    x->state = XF_DONE;
                    force_eof();
                }
            }
        } else {
            step_frame(x, &b, a, out);
        }
        if (is_float) {
            float *fa = audio;
            if (ch > 1) {
                fa[i * 2] = out[0];
                fa[i * 2 + 1] = out[1];
            } else {
                fa[i] = 0.5f * (out[0] + out[1]);
            }
        } else if (ch > 1) {
            write_sample(audio, k, i * 2, out[0]);
            write_sample(audio, k, i * 2 + 1, out[1]);
        } else {
            write_sample(audio, k, i, 0.5f * (out[0] + out[1]));
        }
    }
    b_flush(&b);
    return 1;
}

int xfade_process_float(xfade_dsp *x, float *audio, unsigned frames) { return process_block(x, audio, frames, 1); }

int xfade_process_native(xfade_dsp *x, void *audio, unsigned frames) { return process_block(x, audio, frames, 0); }
