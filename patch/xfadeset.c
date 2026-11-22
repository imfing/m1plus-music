/* M1+ Music Crossfade, demo's side (docs/modules/crossfade.md): persistent settings, smart cross-album decision,
 * runtime tmpfs record (/tmp/m1plus-xfade) and early gapless preload via Hook 36 (rd_auto_change).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The user's settings live on flash (XFADE_SET_FILE: one character, 'a'..'l' on with 1..12 s, 'A'..'L' off with the
 * duration kept, missing off with 5 s; XFADE_AUTO_FILE: '0' Always, missing or '1' Keep Albums Gapless). The player never reads flash for crossfade: demo writes the
 * effective per-transition duration (0 when skipped for same-album, DSD, CUE, podcasts, audiobooks, short tracks or
 * off) to tmpfs XFADE_FILE right before triggering stock's gapless preload (0x5d0ea4).
 *
 * When the user has Gapless OFF but Crossfade ON, xfade_auto_change temporarily raises MCL_GAPLESS around the preload
 * call and around the seamless mclNextSong(1) handoff inside mclAutoChange, restoring the user's Gapless byte
 * immediately so the saved Gapless setting is never modified.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "xfade.h"
#include "i18n.h"

#define S(p, off) (*(const char **)((const char *)(p) + (off)))

static struct {
    unsigned char loaded, on, sec, smart;
    unsigned char forced_gapless; /* 1: we opened a preload while stock's Gapless switch was off */
    int seq; /* monotonic sequence written into XFADE_FILE */
    int last_pos; /* last playing queue index we saw (resets forced_gapless on track change) */
    int last_rt; /* last runtime seconds written to XFADE_FILE (-1 = unknown) */
    int last_keep; /* and its keep flag */
} xf __attribute__((section(".scratch")));

static void xf_load(void) {
    int c;
    if (xf.loaded) return;
    c = set_read(XFADE_SET_FILE, 0);
    xf.on = c >= 'a' && c < 'a' + XFADE_MAX_SEC;
    xf.sec = c >= 'a' && c < 'a' + XFADE_MAX_SEC   ? (unsigned char)(c - 'a' + 1)
             : c >= 'A' && c < 'A' + XFADE_MAX_SEC ? (unsigned char)(c - 'A' + 1)
                                                   : XFADE_DEF_SEC;
    xf.smart = set_read(XFADE_AUTO_FILE, '1') != '0';
    xf.last_pos = -1;
    xf.last_rt = -1;
    xf.loaded = 1;
}

static int xf_save(int on, int sec) {
    char text[3] = {0, '\n', 0};
    text[0] = (char)((on ? 'a' : 'A') + sec - 1);
    return home_write_atomic(XFADE_SET_FILE, text);
}

static int xf_write_runtime(int seconds, int keep) {
    xfade_record r;
    int i, ok;
    memset(&r, 0, sizeof r);
    for (i = 0; i < 8; ++i) r.magic[i] = XFADE_MAGIC[i];
    r.seconds = seconds;
    r.seq = ++xf.seq;
    r.keep = keep;
    ok = m1_save(XFADE_FILE, 0644, &r, sizeof r);
    if (ok) xf.last_rt = seconds, xf.last_keep = keep;
    return ok;
}

int xfade_on(void) {
    xf_load();
    return xf.on;
}

int xfade_sec(void) {
    xf_load();
    return xf.sec;
}

int xfade_seconds(void) { return xfade_on() ? xf.sec : 0; }

int xfade_on_toggle(void) {
    int next = !xfade_on();
    if (xf_save(next, xf.sec) != 0) return -1;
    xf.on = (unsigned char)next;
    if (!next) {
        xf_write_runtime(0, 0);
        if (xf.forced_gapless && *(volatile int *)MCL_PRELOAD == 1 && *(volatile unsigned char *)MCL_GAPLESS == 0) {
            mclSetGaplessMode(0); /* closes our preload without changing user's off setting */
        }
        xf.forced_gapless = 0;
    }
    return next;
}

int xfade_sec_set(int sec) {
    if (sec < XFADE_MIN_SEC || sec > XFADE_MAX_SEC) return -1;
    if (sec == xfade_sec()) return sec;
    if (xf_save(xf.on, sec) != 0) return -1;
    xf.sec = (unsigned char)sec;
    return sec;
}

int xfade_auto(void) {
    xf_load();
    return xf.smart;
}

int xfade_auto_toggle(void) {
    int next = !xfade_auto();
    if (home_write_atomic(XFADE_AUTO_FILE, next ? "1\n" : "0\n") != 0) return -1;
    xf.smart = (unsigned char)next;
    return next;
}

void xfade_boot(void) {
    unlink(XFADE_FILE);
    unlink(XFADE_FILE ".tmp");
    unlink(XFOUT_FILE);
}

int xfade_out_rate(void) {
    xfout_record r;
    void *f;
    unsigned n;
    if (!*(volatile unsigned char *)HCI_RUNNING) return 0; /* a player that went away left its record */
    f = fopen(XFOUT_FILE, "rb");
    if (!f) return 0;
    n = fread(&r, 1, sizeof r, f);
    fclose(f);
    return n == sizeof r && r.magic == XFOUT_MAGIC && r.rate >= 8000 && r.rate <= 384000 ? r.rate : 0;
}

void xfade_on_preload_cancel(void) {
    xf.forced_gapless = 0;
    xf_write_runtime(0, 0);
}

static int ci_eq(const char *a, const char *b) {
    while (*a && *b) {
        int ca = (unsigned char)*a++, cb = (unsigned char)*b++;
        if (ca >= 'A' && ca <= 'Z') ca += 32;
        if (cb >= 'A' && cb <= 'Z') cb += 32;
        if (ca != cb) return 0;
    }
    return *a == *b;
}

/* pre is lower case; ASCII case is ignored (the card's file system does not tell "Podcasts" from "podcasts"). */
static int has_prefix(const char *s, const char *pre) {
    while (*pre) {
        int c = (unsigned char)*s++;
        if (c >= 'A' && c <= 'Z') c += 32;
        if (c != *pre++) return 0;
    }
    return 1;
}

/* Not music, or not crossfade's to join: streams (radio, a server's or a feed's audio), everything under the Podcasts
 * and Audiobooks folders (the Library filter's rule, patch/pcmodel.c PQ_MUSIC) and DSD. */
static int path_excluded(const char *p) {
    const char *dot;
    if (!p || !*p) return 1;
    if (has_prefix(p, "http://") || has_prefix(p, "https://")) return 1;
    if (has_prefix(p, "/mnt/mmc/podcasts/") || has_prefix(p, "/mnt/mmc/audiobooks/")) return 1;
    dot = strrchr(p, '.');
    if (dot && (ci_eq(dot, ".dsf") || ci_eq(dot, ".dff") || ci_eq(dot, ".iso"))) return 1;
    return 0;
}

/* Next queue index matching stock's 0x5d0ea4 rules: mode 0 (List) -> pos + 1 if < size; mode 3 (Repeat All) -> wraps
 * unless folder skip handles end; mode 1 (Repeat Track) or anything else -> -1. */
static int next_index(void *q, int pos, int mode) {
    unsigned n = deque_size(q);
    if (pos < 0 || (unsigned)pos >= n || n == 0) return -1;
    if (mode == 0) return (unsigned)(pos + 1) < n ? pos + 1 : -1;
    if (mode == 3) return (unsigned)(pos + 1) < n ? pos + 1 : (n > 1 ? 0 : -1);
    return -1;
}

/* The join cur -> nxt is one crossfade has a part in: Crossfade on, two music files, no CUE track. */
static int transition_music(void *cur, void *nxt) {
    if (xfade_seconds() <= 0 || !cur || !nxt) return 0;
    /* CUE track inside a single file: keep gapless. */
    if (I(cur, REC_CUE_END) > 0 || I(cur, REC_CUE_START) > 0 || I(nxt, REC_CUE_START) > 0 || I(nxt, REC_CUE_END) > 0)
        return 0;
    return !path_excluded(S(cur, REC_PATH)) && !path_excluded(S(nxt, REC_PATH));
}

/* Effective crossfade seconds for the transition cur -> nxt (transition_music), or 0 when this join should stay
 * gapless / clean. */
static int transition_seconds(void *cur, void *nxt, int total_s) {
    int sec = xfade_seconds();
    const char *ca, *na;
    int max_eff;
    if (total_s < 10) return 0;
    /* Smart cross-album mode: keep consecutive tracks of the same album gapless. */
    if (xfade_auto()) {
        ca = S(cur, REC_ALBUM);
        na = S(nxt, REC_ALBUM);
        if (ca && *ca && na && *na && strcmp(ca, na) == 0) return 0;
    }
    max_eff = (total_s - 4) / 2;
    if (max_eff < 1) return 0;
    return sec > max_eff ? max_eff : sec;
}

/* Called from rd_auto_change (Hook 36) on every idle pass when Radio does not own the player.
 * Handles early preload (total - cur <= eff + 5), writes /tmp/m1plus-xfade, and bridges MCL_GAPLESS during
 * seamless handoff if the user had Gapless off. Always finishes by calling stock mclAutoChange(). */
int xfade_auto_change(void) {
    int sec, pos, mode, pt, cur_s = 0, total_s = 0, next_i, eff, preload, keep = 0;
    unsigned char running, saved_gap;
    void *q;
    if (home_off()) return mclAutoChange();
    sec = xfade_seconds();
    if (sec <= 0 && !xf.forced_gapless) return mclAutoChange();
    running = *(volatile unsigned char *)HCI_RUNNING;
    preload = *(volatile int *)MCL_PRELOAD;
    pos = mclGetPlayPos();
    if (pos != xf.last_pos) {
        xf.last_pos = pos;
        if (preload == 0) xf.forced_gapless = 0;
    }
    /* Case 1: Track A just ended (running == 0) after we forced a crossfade preload while user's Gapless was off.
     * Temporarily raise MCL_GAPLESS so mclAutoChange -> mclNextSong(1) takes the seamless gapless handoff path
     * instead of restarting hciplayer with mclStartPlayer. */
    if (xf.forced_gapless && !running && preload == 1) {
        int r;
        saved_gap = *(volatile unsigned char *)MCL_GAPLESS;
        *(volatile unsigned char *)MCL_GAPLESS = 1;
        r = mclAutoChange();
        *(volatile unsigned char *)MCL_GAPLESS = saved_gap;
        xf.forced_gapless = 0;
        return r;
    }
    /* Case 2: Playing a local track with Crossfade enabled and no preload sent yet (preload == 0). */
    if (sec > 0 && running && preload == 0 && mclGetPlayStatus() == 2) {
        pt = mclGetPlayType();
        if (pt != 2 && pt != 0xf0 && pt != 0xf1) { /* not DLNA / stream modes stock skips */
            q = *(void **)PLAY_QUEUE;
            mode = mclGetPlayMode();
            next_i = q ? next_index(q, pos, mode) : -1;
            void *cur = next_i >= 0 ? deque_at(q, (unsigned)pos) : 0;
            void *nxt = next_i >= 0 ? deque_at(q, (unsigned)next_i) : 0;
            keep = transition_music(cur, nxt);
            if (keep && mclGetPlayTime(&cur_s, &total_s) && total_s >= 10 && cur_s >= 0 && cur_s < total_s) {
                eff = transition_seconds(cur, nxt, total_s);
                if (eff > 0 && total_s - cur_s <= eff + 5) {
                    xf_write_runtime(eff, 1);
                    saved_gap = *(volatile unsigned char *)MCL_GAPLESS;
                    if (!saved_gap) *(volatile unsigned char *)MCL_GAPLESS = 1;
                    mcl_gapless_preload();
                    if (!saved_gap) {
                        *(volatile unsigned char *)MCL_GAPLESS = 0;
                        if (*(volatile int *)MCL_PRELOAD == 1) xf.forced_gapless = 1;
                    }
                    return mclAutoChange();
                }
            }
        }
    }
    /* No active preload: clear any stale runtime duration so short, excluded or same-album tracks never inherit one.
     * The record still says whether the coming join is between two music tracks (keep). */
    if (preload == 0 && (running ? xf.last_rt != 0 || xf.last_keep != keep : xf.last_rt > 0 || xf.last_keep > 0))
        xf_write_runtime(0, keep);
    return mclAutoChange();
}

/* The Crossfade page (tools/pod_pages.py PSXFADE_PAGE, tools/pod_ui.py cards_xfade): below the switch card the duration header and card, Keep Albums Gapless and the note show while the switch is on (hidden they
 * are also insensitive, and close up); the slider (1 .. 12 s) and its text follow the saved duration. */
static void xf_text(void *win) {
    char buf[40];
    void *t = widget_lookup(win, "pod_xf_val", 1);
    int sec = xfade_sec();
    if (!t) return;
    snprintf(buf, sizeof buf, "%d %s", sec, TR(sec == 1 ? "second" : "seconds"));
    widget_set_text_utf8(t, buf);
}

void xfade_show(void *win) {
    static const char *const names[] = {"pod_sec0", "pod_xfcard", "pod_row1", "pod_note0", "pod_note1"};
    int on = xfade_on(), i;
    void *s;
    for (i = 0; i < 5; i++) {
        void *w = widget_lookup(win, names[i], 1);
        if (w) widget_set_visible(w, on, 0), widget_set_sensitive(w, on);
    }
    s = widget_lookup(win, "pod_xf_slider", 1);
    if (s) widget_set_prop_int(s, "value", xfade_sec());
    xf_text(win);
}

static int xf_slider(void *ctx, void *e) {
    void *s = widget_lookup(ctx, "pod_xf_slider", 1);
    (void)e;
    if (!s) return RET_OK;
    xfade_sec_set(widget_get_prop_int(s, "value", xfade_sec()));
    xf_text(ctx);
    return RET_OK;
}

void xfade_opened(void *win) {
    void *s = widget_lookup(win, "pod_xf_slider", 1);
    if (!s) return;
    widget_on(s, EVT_VALUE_CHANGING, (void *)xf_slider, win);
    widget_on(s, EVT_VALUE_CHANGED, (void *)xf_slider, win);
}
