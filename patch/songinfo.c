/* M1+ Music Get Info: the page behind the track rows' "..." sheet (docs/modules/songinfo.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Station Info's mechanism (patch/radioinfo.c): the stock navbar over a stock list (list_view > scroll_view) holding ONE content view that this file paints in its EVT_AFTER_PAINT (the scroll offset
 * taken off the canvas), every text wrapped once by the Podcasts episode page's wrapper (pd_lines). The header is the track's cover (the Cover Flow cache file of its album, else the placeholder
 * disc; one grid tile) with the title, the artist and the album beside it; below, label / value pairs, a pair with no value left out: Format, Sample Rate / Bit Depth, Bitrate, Duration, Size, Path.
 * Everything is read once when the page opens: the file's first bytes (one read of 2 KB, a second after an ID3v2 tag: FLAC STREAMINFO, the WAV fmt chunk, the Ogg Vorbis identification header or the first
 * MPEG frame), the file's size, and the duration (the durations table, else FLAC's own total, else TagLib's length of this one file). Nothing is written, no timer runs, the memory is freed with the window.
 * Action rows (Go to Album, Go to Artist, Delete) can follow the last pair: the content ends at gi.h.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "durations.h"
#include "grid.h"
#include "i18n.h"
#include "pcdetail.h"
#include "songinfo.h"
#include "sbsrc.h"

#define GI_X 16 /* the pairs' left edge and width */
#define GI_W 288
#define GI_TOP 16 /* the header: the cover's top and side, the texts beside it */
#define GI_COVER 96
#define GI_TX 124
#define GI_TW 180
#define GI_HEAD_PITCH 26 /* the title (22 px), at most two lines */
#define GI_HEAD_LINES 2
#define GI_SUB_PITCH 20 /* the artist and the album (16 px), one line each */
#define GI_KEY_PITCH 18 /* a pair's label (14 px) */
#define GI_VAL_PITCH 22 /* and its value (18 px) */
#define GI_HEAD_GAP 16 /* under the cover */
#define GI_PAIR_GAP 10 /* (Format to Size fit above the fold, Path's label peeks under them) */
#define GI_BOTTOM 20
#define GI_VIEW_H 400 /* the list under the navbar */
#define GI_SRC 1100 /* wide chars of one text (a longer one ends there, with an ellipsis where the lines end) */
#define GI_WIDE 3600 /* wide chars kept in all */
#define GI_LINES 120 /* wrapped lines kept */
#define GI_WRAP 40 /* lines one text may take */
#define GI_HEAD_BYTES 2048 /* the file's first bytes read, and the bytes after an ID3v2 tag */

enum { K_HEAD, K_SUB, K_KEY, K_VAL };

typedef struct {
    int off; /* the line's first char in gi.lw */
    short len, y; /* chars; top in content coordinates */
    unsigned char kind;
} gi_ln_t;

/* What the file's first bytes say. */
typedef struct {
    unsigned rate, bits; /* Hz, bits per sample; 0 unknown */
    unsigned hi, lo; /* FLAC: the total samples, 36 bits (hi 4 bits) */
    int flac;
} gi_head_t;

static struct {
    void *win, *sv, *view, *fade, *st[4]; /* st: the four text styles (title, artist and album, label, value) */
    unsigned *lw; /* the texts, wide, one NUL after each */
    gi_ln_t *ln;
    pd_t *d; /* only its advances' cache */
    grid_t g; /* the cover: one tile */
    int nln, nw, h, fade_on;
} gi __attribute__((section(".scratch")));

#define GI_I(w, off) (*(int *)((char *)(w) + (off)))

static void gi_free(void) {
    grid_free(&gi.g);
    free(gi.lw);
    free(gi.ln);
    free(gi.d);
    gi.lw = (unsigned *)0, gi.ln = (gi_ln_t *)0, gi.d = (pd_t *)0;
}

/* ---- the file's first bytes */
static int gi_eq(const unsigned char *b, const char *s, unsigned n) {
    unsigned i;
    for (i = 0; i < n; ++i)
        if (b[i] != (unsigned char)s[i]) return 0;
    return 1;
}

static unsigned gi_be(const unsigned char *p, int n) {
    unsigned v = 0;
    while (n-- > 0) v = v << 8 | *p++;
    return v;
}

static unsigned gi_le(const unsigned char *p, int n) {
    unsigned v = 0;
    p += n;
    while (n-- > 0) v = v << 8 | *--p;
    return v;
}

/* "fLaC", then the STREAMINFO block (type 0, 34 bytes) first: 20 bits of rate, 3 of channels - 1, 5 of bits - 1, 36 of total samples from byte 18. */
static int gi_flac(const unsigned char *b, unsigned n, gi_head_t *h) {
    if (n < 26 || !gi_eq(b, "fLaC", 4) || (b[4] & 0x7f) || gi_be(b + 5, 3) != 34) return 0;
    h->rate = (unsigned)b[18] << 12 | (unsigned)b[19] << 4 | b[20] >> 4;
    h->bits = (((unsigned)b[20] & 1) << 4 | b[21] >> 4) + 1;
    h->hi = b[21] & 15, h->lo = gi_be(b + 22, 4);
    h->flac = 1;
    return h->rate != 0;
}

/* RIFF WAVE: the fmt chunk (tag 2, channels 2, rate 4, byte rate 4, block align 2, bits 2) among the chunks that fit in the bytes read. */
static int gi_wav(const unsigned char *b, unsigned n, gi_head_t *h) {
    unsigned p = 12, sz;
    if (n < 28 || !gi_eq(b, "RIFF", 4) || !gi_eq(b + 8, "WAVE", 4)) return 0;
    while (p + 8 <= n) {
        sz = gi_le(b + p + 4, 4);
        if (gi_eq(b + p, "fmt ", 4)) {
            if (sz < 16 || p + 24 > n) return 0;
            h->rate = gi_le(b + p + 12, 4), h->bits = gi_le(b + p + 22, 2);
            return h->rate != 0;
        }
        if (sz > n) return 0;
        p += 8 + sz + (sz & 1);
    }
    return 0;
}

/* Ogg Vorbis: the first page's first packet is the identification header (0x01 "vorbis", version 4, channels 1, rate 4). */
static int gi_ogg(const unsigned char *b, unsigned n, gi_head_t *h) {
    unsigned p;
    if (n < 40 || !gi_eq(b, "OggS", 4)) return 0;
    p = 27u + b[26];
    if (p + 16 > n || !gi_eq(b + p, "\1vorbis", 7)) return 0;
    h->rate = gi_le(b + p + 12, 4);
    return h->rate != 0;
}

/* The first MPEG audio frame header (11 sync bits, a valid version, layer, bitrate and rate index) whose next frame, when it starts inside the bytes read, has a header of the same
 * version, layer and rate: its sample rate. Only for an MPEG file's extension (other containers can hold such bytes in any box). */
static int gi_mpeg(const unsigned char *b, unsigned n, gi_head_t *h) {
    static const unsigned short T[3][3] = {{44100, 48000, 32000}, {22050, 24000, 16000}, {11025, 12000, 8000}};
    static const unsigned short K[5][14] = {/* kbps of bitrate index 1..14: V1 L1, V1 L2, V1 L3, V2 L1, V2 L2/L3 */
                                            {32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448},
                                            {32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384},
                                            {32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320},
                                            {32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256},
                                            {8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160}};
    unsigned i, j, ver, lay, br, sr, rate, kbps, len, pad;
    for (i = 0; i + 4 <= n; ++i) {
        if (b[i] != 0xff || (b[i + 1] & 0xe0) != 0xe0) continue;
        ver = b[i + 1] >> 3 & 3, lay = b[i + 1] >> 1 & 3, br = b[i + 2] >> 4, sr = b[i + 2] >> 2 & 3,
        pad = b[i + 2] >> 1 & 1;
        if (ver == 1 || !lay || !br || br == 15 || sr == 3) continue;
        rate = T[ver == 3 ? 0 : ver == 2 ? 1 : 2][sr];
        kbps = K[ver == 3 ? 3 - lay : lay == 3 ? 3 : 4][br - 1];
        if (lay == 3) /* layer I: 4-byte slots */
            len = (12000 * kbps / rate + pad) * 4;
        else
            len = (lay == 1 && ver != 3 ? 72000 : 144000) * kbps / rate + pad;
        j = i + len;
        if (j + 4 <= n &&
            (b[j] != 0xff || (b[j + 1] & 0xfe) != (b[i + 1] & 0xfe) || (b[j + 2] & 0x0c) != (b[i + 2] & 0x0c)))
            continue;
        h->rate = rate;
        return 1;
    }
    return 0;
}

static int gi_any(const unsigned char *b, unsigned n, int mpeg, gi_head_t *h) {
    return gi_flac(b, n, h) || gi_wav(b, n, h) || gi_ogg(b, n, h) || (mpeg && gi_mpeg(b, n, h));
}

/* mpeg: the file's extension is an MPEG audio one (gi_mpeg). */
static void gi_read_head(const char *path, int mpeg, gi_head_t *h) {
    unsigned char b[GI_HEAD_BYTES];
    int fd, n;
    memset(h, 0, sizeof *h);
    fd = open(path, 0, 0);
    if (fd < 0) return;
    n = read(fd, b, sizeof b);
    if (n >= 10 &&
        gi_eq(
            b, "ID3",
            3)) { /* an ID3v2 tag first: 10 bytes of header, a synchsafe size, a 10 byte footer when flag 0x10 is set */
        long off = 10 +
                   (long)((unsigned)(b[6] & 0x7f) << 21 | (unsigned)(b[7] & 0x7f) << 14 | (unsigned)(b[8] & 0x7f) << 7 |
                          (b[9] & 0x7f)) +
                   (b[5] & 0x10 ? 10 : 0);
        n = lseek(fd, off, 0) == off ? read(fd, b, sizeof b) : 0;
    }
    if (n > 0) gi_any(b, (unsigned)n, mpeg, h);
    close(fd);
}

/* seconds = (hi * 2^32 + lo) / rate by long division (no 64-bit divide in the payload). */
static unsigned gi_div36(unsigned hi, unsigned lo, unsigned rate) {
    unsigned rem = hi % rate, q = 0, i;
    for (i = 0; i < 32; ++i) {
        rem = rem << 1 | (lo >> (31 - i) & 1);
        q <<= 1;
        if (rem >= rate) rem -= rate, q |= 1;
    }
    return q;
}

/* ---- the texts */
/* v in decimal, zero-padded to width digits, at o; the end. */
static char *gi_u(char *o, unsigned v, int width) {
    char t[12];
    int n = 0;
    do t[n++] = (char)('0' + v % 10);
    while ((v /= 10) != 0);
    while (n < width) t[n++] = '0';
    while (n) *o++ = t[--n];
    return o;
}

static char *gi_s(char *o, const char *s) {
    while (*s) *o++ = *s++;
    return o;
}

/* 44100 -> "44.1 kHz", 48000 -> "48 kHz", 22050 -> "22.05 kHz". */
static void gi_rate_text(char *out, unsigned rate) {
    char *o = gi_u(out, rate / 1000, 0);
    unsigned f = rate % 1000;
    if (f) {
        *o++ = '.';
        o = gi_u(o, f, 3);
        while (o[-1] == '0') --o;
    }
    *gi_s(o, " kHz") = 0;
}

/* 3 min 5 s -> "3:05", 1 h 2 min 3 s -> "1:02:03". */
static void gi_time_text(char *out, unsigned sec) {
    char *o = out;
    if (sec >= 3600) {
        o = gi_u(o, sec / 3600, 0);
        *o++ = ':';
        o = gi_u(o, sec / 60 % 60, 2);
    } else
        o = gi_u(o, sec / 60, 0);
    *o++ = ':';
    o = gi_u(o, sec % 60, 2);
    *o = 0;
}

/* Decimal units like the desktop's: "12.3 MB", "1.25 GB", "845 KB". */
static void gi_size_text(char *out, unsigned sz) {
    char *o = out;
    if (sz >= 1000000000u) {
        unsigned t = (sz + 5000000u) / 10000000u; /* hundredths of a GB */
        o = gi_u(o, t / 100, 0), *o++ = '.', o = gi_u(o, t % 100, 2), o = gi_s(o, " GB");
    } else if (sz >= 1000000u) {
        unsigned t = (sz + 50000u) / 100000u; /* tenths of an MB */
        o = gi_u(o, t / 10, 0), *o++ = '.', o = gi_u(o, t % 10, 0), o = gi_s(o, " MB");
    } else if (sz >= 1000u)
        o = gi_u(o, (sz + 500) / 1000, 0), o = gi_s(o, " KB");
    else
        o = gi_u(o, sz, 0), o = gi_s(o, " B");
    *o = 0;
}

/* The upper-case extension of the file name ("flac" -> "FLAC"), at most 7 letters; empty when there is none. */
static void gi_format_text(char *out, const char *path) {
    const char *dot = (const char *)0, *p;
    unsigned n = 0;
    out[0] = 0;
    for (p = path; *p; ++p) { /* the last '.' after the last '/' */
        if (*p == '/')
            dot = (const char *)0;
        else if (*p == '.')
            dot = p;
    }
    if (!dot || !dot[1]) return;
    for (++dot; *dot && n < 7; ++dot, ++n) out[n] = (char)(*dot >= 'a' && *dot <= 'z' ? *dot - 32 : *dot);
    out[n] = 0;
    if (*dot) out[0] = 0; /* (a longer one is not an extension) */
}

/* ---- the lines */
/* One text as lines of the given kind from y; the y under it. Cut where the tables are full. */
static int gi_put(const char *text, int kind, int y) {
    static const short pitch[4] = {GI_HEAD_PITCH, GI_SUB_PITCH, GI_KEY_PITCH, GI_VAL_PITCH};
    pw_line_t pl[GI_WRAP];
    unsigned *w = gi.lw + gi.nw;
    unsigned len = 0;
    int n, k, nl, maxl = kind == K_HEAD ? GI_HEAD_LINES : kind == K_VAL ? GI_WRAP : 1;
    if (!gi.lw || !gi.ln || !gi.d || gi.nw + GI_SRC + 2 >= GI_WIDE || gi.nln + GI_WRAP >= GI_LINES) return y;
    while (text[len] && len < 4u * GI_SRC) ++len;
    tk_utf8_to_utf16_ex(text, len, w, GI_SRC);
    for (n = 0; n < GI_SRC && w[n]; ++n) {
    }
    w[n] = 0;
    if (!n) return y;
    nl = pd_lines(gi.d, gi.st[kind], w, n, kind <= K_SUB ? GI_TW : GI_W, maxl, pl);
    for (k = 0; k < nl; ++k) {
        gi.ln[gi.nln].off = gi.nw + pl[k].start, gi.ln[gi.nln].len = pl[k].len;
        gi.ln[gi.nln].y = (short)y, gi.ln[gi.nln].kind = (unsigned char)kind;
        ++gi.nln;
        y += pitch[kind];
    }
    gi.nw += n + 1;
    return y;
}

/* A label over its value; nothing for an empty value. */
static int gi_pair(const char *key, const char *val, int y) {
    if (!val[0]) return y;
    y = gi_put(key, K_KEY, y);
    y = gi_put(val, K_VAL, y);
    return y + GI_PAIR_GAP;
}

typedef struct {
    char title[200], artist[200], album[200], path[GI_SRC];
    int cue_start, cue_end;
    unsigned ckey;
    int remote; /* a Navidrome track: t is its row, the page takes its facts from the server's data (and the local file once downloaded) */
    char cover[200]; /* remote: the cover's cache file when it is there */
    sba_track_t t;
} gi_rec_t;

/* The title, artist and album beside the cover, centred on its height, then the pairs. */
static void gi_build(const gi_rec_t *r) {
    char fmt[16], rate[32], bits[16], key[96], val[64], br[24], dur[16], size[24];
    gi_head_t h;
    unsigned sec = 0;
    long sz;
    int y, i, whole = r->cue_start <= 0 && r->cue_end <= r->cue_start, cue_dur = r->cue_end > r->cue_start;
    gi.nln = gi.nw = 0;
    y = gi_put(r->title, K_HEAD, 0);
    y = gi_put(r->artist, K_SUB, y);
    y = gi_put(r->album, K_SUB, y);
    for (i = 0; i < gi.nln; ++i)
        gi.ln[i].y = (short)(gi.ln[i].y + GI_TOP + (GI_COVER - y) / 2); /* (y is the block's height: it started at 0) */
    y = GI_TOP + GI_COVER + GI_HEAD_GAP;

    if (r->remote) { /* the server's data; the file's own bytes only when it is on the card (what the server leaves out) */
        const sba_track_t *t = &r->t;
        unsigned k;
        memset(&h, 0, sizeof h);
        for (k = 0; t->suffix[k] && k < 7; ++k)
            fmt[k] = (char)(t->suffix[k] >= 'a' && t->suffix[k] <= 'z' ? t->suffix[k] - 32 : t->suffix[k]);
        fmt[k] = 0;
        h.rate = t->sample_rate, h.bits = t->bit_depth;
        sz = t->size;
        if (r->path[0]) { /* downloaded */
            gi_head_t fh;
            gi_read_head(r->path, !strcmp(fmt, "MP3") || !strcmp(fmt, "MP2"), &fh);
            if (!h.rate) h.rate = fh.rate, h.bits = fh.bits;
            if (!sz) sz = cc_file_size(r->path);
            if (sz < 0 || sz > 0x7fffffff) sz = 0;
        }
        sec = t->seconds;
    } else {
        gi_format_text(fmt, r->path);
        gi_read_head(r->path,
                     !strcmp(fmt, "MP3") || !strcmp(fmt, "MP2") || !strcmp(fmt, "MP1") || !strcmp(fmt, "MPA") ||
                         !strcmp(fmt, "MPGA"),
                     &h);
        sz = cc_file_size(r->path);
        if (sz < 0 || sz > 0x7fffffff) sz = 0;
        if (cue_dur) { /* a CUE track with both ends: nothing to measure */
            sec = (unsigned)(r->cue_end - r->cue_start);
        } else if (
            sz) { /* the table (this size), else FLAC's own total, else TagLib's length of this one file; less a CUE track's start */
            int v, start = r->cue_start > 0 ? r->cue_start : 0;
            dur_acquire();
            v = dur_file(r->path, (unsigned)sz);
            dur_release();
            if (v < 0) v = h.flac && h.rate ? (int)gi_div36(h.hi, h.lo, h.rate) : dur_probe(r->path);
            sec = v > start ? (unsigned)(v - start) : 0;
        }
    }
    gi_rate_text(rate, h.rate);
    if (h.rate && h.bits && h.bits <= 32) {
        *gi_s(gi_u(bits, h.bits, 0), "-bit") = 0;
        snprintf(key, sizeof key, "%s / %s", TR("Sample Rate"), TR("Bit Depth"));
        snprintf(val, sizeof val, "%s / %s", rate, bits);
    } else {
        snprintf(key, sizeof key, "%s", TR("Sample Rate"));
        snprintf(val, sizeof val, "%s", h.rate ? rate : "");
    }
    br[0] = 0;
    if (r->remote && r->t.bitrate)
        *gi_s(gi_u(br, r->t.bitrate, 0), " kbps") = 0; /* (the server's own figure) */
    else if (whole && sec &&
             sz) { /* the file's average: its bytes over its length (a CUE track's length is not the file's) */
        *gi_s(gi_u(br, (((unsigned)sz / sec) * 8 + 500) / 1000, 0), " kbps") = 0;
    }
    dur[0] = size[0] = 0;
    if (sec) gi_time_text(dur, sec);
    if (sz) gi_size_text(size, (unsigned)sz);

    y = gi_pair(TR("Format"), fmt, y);
    y = gi_pair(key, val, y);
    y = gi_pair(TR("Bitrate"), br, y);
    y = gi_pair(TR("Duration"), dur, y);
    y = gi_pair(TR("Size"), size, y);
    y = gi_pair(TR("Path"), r->path, y);
    gi.h = (y > GI_TOP + GI_COVER ? y - GI_PAIR_GAP : y) + GI_BOTTOM;
    if (gi.h < GI_VIEW_H) gi.h = GI_VIEW_H;
    widget_resize(gi.view, 320, gi.h);
    widget_set_prop_int(gi.sv, "virtual_h", gi.h);
}

/* ---- paint */
/* One text drawn wholly inside the view (AWTK does not clip texts; the same rule as every text of the payload's pages). */
static void gi_text(void *canvas, const unsigned *s, int n, int kind, int y, int h) {
    int rect[4];
    if (n <= 0 || y < 0 || y + h > GI_VIEW_H) return;
    rect[0] = kind <= K_SUB ? GI_TX : GI_X, rect[1] = y, rect[2] = kind <= K_SUB ? GI_TW : GI_W, rect[3] = h;
    canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

static int gi_on_paint(void *ctx, void *e) {
    static const short pitch[4] = {GI_HEAD_PITCH, GI_SUB_PITCH, GI_KEY_PITCH, GI_VAL_PITCH};
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off, i, kind = -1;
    (void)ctx;
    if (!canvas || !gi.win) return RET_OK;
    off = GI_I(gi.sv, SC_YOFF);
    if (gi.fade && (off > 0) != gi.fade_on) {
        gi.fade_on = off > 0;
        widget_set_visible(gi.fade, gi.fade_on, 0);
        widget_set_sensitive(gi.fade, 0);
    }
    GI_I(canvas, CANVAS_OY) += off;
    if (gi.g.tiles) grid_blit(canvas, &gi.g, gi.g.tiles, GI_X, GI_TOP - off, GI_VIEW_H);
    for (i = 0; gi.lw && gi.ln && i < gi.nln; ++i) {
        int y = gi.ln[i].y - off, k = gi.ln[i].kind;
        if (y + pitch[k] <= 0) continue;
        if (y >= GI_VIEW_H) break;
        if (k != kind) widget_prepare_text_style(gi.st[kind = k], canvas);
        gi_text(canvas, gi.lw + gi.ln[i].off, gi.ln[i].len, k, y, pitch[k]);
    }
    GI_I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ctx is the window the handler was bound to: a closed page is destroyed later, after songinfo_open may have opened its successor, whose state this must not clear. */
static int gi_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != gi.win) return RET_OK;
    gi_free();
    memset(&gi, 0, sizeof gi);
    return RET_OK;
}

static void gi_copy(char *out, unsigned n, const char *s) { snprintf(out, n, "%s", s ? s : ""); }

int songinfo_open(void *rec) {
    gi_rec_t *r;
    grid_tile_t *t;
    char url[80];
    int fresh = 0;
    if (!rec) return -1;
    if (gi.win && pod_is_top(gi.win) && widget_is_window_opened(gi.win)) return 0;
    r = (gi_rec_t *)calloc(1, sizeof *r);
    if (!r) return -1;
    gi_copy(r->path, sizeof r->path, cc_str(rec, REC_PATH));
    gi_copy(r->title, sizeof r->title, cc_str(rec, REC_TITLE)[0] ? cc_str(rec, REC_TITLE) : cc_str(rec, REC_NAME));
    gi_copy(r->artist, sizeof r->artist, cc_str(rec, REC_ARTIST));
    gi_copy(r->album, sizeof r->album, cc_str(rec, REC_ALBUM));
    r->cue_start = GI_I(rec, REC_CUE_START), r->cue_end = GI_I(rec, REC_CUE_END);
    /* the cover: the file of the track's own artist and album, else the library album record of that name's (a collab shows the album's cover): one targeted query, none when the
     * own file is there or the track has no album tag; a record with no file shows the placeholder like the own key */
    r->ckey = cc_album_key(rec);
    if (sbs_track(
            rec, &r->t)) { /* a Navidrome track: its path is the local file (when downloaded), nothing else is a file */
        r->remote = 1, r->ckey = 0;
        if (!sba_dl_path(r->t.id, r->path, sizeof r->path)) r->path[0] = 0;
        if (sba_track_cover(r->t.album_id, r->t.cover, r->cover, sizeof r->cover, 0) != 1)
            r->cover[0] = 0; /* (the album's file; never asks) */
    } else if (
        !cc_url(url,
                r->ckey)) { /* (main's fallback: a track's own album cover, else the library record's of that album) */
        unsigned rep = cc_album_rep_key(cc_str(rec, REC_ALBUM));
        if (rep) r->ckey = rep;
    }
    if (gi.win) { /* closing (destroyed later) or under another window: let it go, its late EVT_DESTROY finds gi.win changed */
        if (widget_is_window_opened(gi.win)) window_close(gi.win);
        gi_free();
    }
    memset(&gi, 0, sizeof gi);
    gi.win = window_open("m1plus_songinfo");
    if (!gi.win) {
        free(r);
        return -1;
    }
    widget_on(gi.win, EVT_DESTROY, gi_on_destroy, gi.win);
    pod_bind(gi.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(gi.win, "btn_backtoplayer", pod_on_player, (void *)0);
    gi.sv = widget_lookup(gi.win, "gi_scrollview", 1);
    gi.view = widget_lookup(gi.win, "gi_view", 1);
    gi.fade = widget_lookup(gi.win, "img_nb_fade", 1);
    gi.st[K_HEAD] = widget_lookup(gi.win, "label_head", 1);
    gi.st[K_SUB] = widget_lookup(gi.win, "label_sub", 1);
    gi.st[K_KEY] = widget_lookup(gi.win, "label_key", 1);
    gi.st[K_VAL] = widget_lookup(gi.win, "label_val", 1);
    if (!gi.sv || !gi.view || !gi.st[K_HEAD] || !gi.st[K_SUB] || !gi.st[K_KEY] || !gi.st[K_VAL]) {
        free(r);
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    gi.lw = calloc(GI_WIDE + 1, sizeof *gi.lw);
    gi.ln = calloc(GI_LINES, sizeof *gi.ln);
    gi.d = calloc(1, sizeof *gi.d);
    if (!gi.lw || !gi.ln || !gi.d || !grid_init(&gi.g, gi.win, 1, GI_COVER, GRID_R)) { /* no memory: no page */
        free(r);
        navigator_back();
        return -1;
    }
    t = grid_tile(&gi.g, 0, 0, 0, &fresh);
    if (t) {
        grid_set(t, "", "", r->ckey);
        if (r->remote) {
            char url[210];
            if (r->cover[0]) {
                snprintf(url, sizeof url, "file://%s", r->cover);
                grid_art_url(&gi.g, t, url);
            }
        } else
            grid_art(&gi.g, t);
        if (t->art != 1) grid_placeholder(&gi.g);
    }
    gi_build(r);
    free(r);
    widget_on(gi.view, EVT_AFTER_PAINT, gi_on_paint, (void *)0);
    widget_invalidate_force(gi.win, (void *)0);
    return 0;
}
