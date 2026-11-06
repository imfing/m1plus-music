/* M1+ Music Radio: Station Info, the page behind Radio Now Playing's sheet row (docs/modules/radio.md "Station Info").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Plain text, the Release Notes page's mechanism (patch/relnotes.c): the stock navbar over a stock list (list_view > scroll_view) holding ONE content view that this file paints in its EVT_AFTER_PAINT
 * (the scroll offset taken off the canvas): the station's name as a large heading, then label / value pairs (the label small grey, the value white), every text wrapped once into lines by the Podcasts
 * episode page's wrapper (pd_lines: patch/pcwrap.c; at spaces, a word longer than the line anywhere, CJK anywhere), so a long address shows in full and the stock scroll_view does the dragging and the
 * fling. The station is the one the engine has when the page opens (its name, address and info are copied then); the Status pair is the last block and is laid out again on a 500 ms page timer when the
 * engine's state (or error) changed. Nothing is written, nothing is fetched; the memory is freed with the window.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "i18n.h"
#include "pcdetail.h"
#include "radio.h"

#define SINFO_X 16 /* the text's left edge and width */
#define SINFO_W 288
#define SINFO_TOP 12
#define SINFO_HEAD_PITCH 34 /* the heading (28 px), at most three lines */
#define SINFO_HEAD_LINES 3
#define SINFO_HEAD_GAP 18
#define SINFO_KEY_PITCH 20 /* a pair's label (14 px) */
#define SINFO_VAL_PITCH 24 /* and its value (18 px) */
#define SINFO_PAIR_GAP 16
#define SINFO_BOTTOM 20
#define SINFO_VIEW_H 400 /* the list under the navbar */
#define SINFO_SRC 1100 /* wide chars of one text (a longer one ends there, with an ellipsis where the lines end) */
#define SINFO_WIDE 3600 /* wide chars kept in all (a char is at least one byte; a text adds its NUL) */
#define SINFO_LINES 240 /* wrapped lines kept */
#define SINFO_WRAP 40 /* lines one text may take (1100 chars of the widest glyph need about 35) */

enum { K_HEAD, K_KEY, K_VAL };

typedef struct {
    int off; /* the line's first char in sinfo.lw */
    short len, y; /* chars; top in content coordinates */
    unsigned char kind;
} sinfo_ln_t;

static struct {
    void *win, *sv, *view, *fade, *st[3]; /* st: the three text styles (heading, label, value) */
    unsigned *lw; /* the texts, wide, one NUL after each */
    sinfo_ln_t *ln;
    pd_t *d; /* only its advances' cache */
    int nln, nw, h, fade_on;
    int stat_ln, stat_nw, stat_y; /* where the Status pair begins: the lines, the wide chars, the y */
    unsigned timer;
    char stat[200]; /* the Status text the lines show */
} sinfo __attribute__((section(".scratch")));

#define SINFO_I(w, off) (*(int *)((char *)(w) + (off)))

static void sinfo_free(void) {
    free(sinfo.lw);
    free(sinfo.ln);
    free(sinfo.d);
    sinfo.lw = (unsigned *)0, sinfo.ln = (sinfo_ln_t *)0, sinfo.d = (pd_t *)0;
}

/* One text as lines of the given kind from y; the y under it. Cut where the tables are full. */
static int sinfo_put(const char *text, int kind, int y) {
    static const short pitch[3] = {SINFO_HEAD_PITCH, SINFO_KEY_PITCH, SINFO_VAL_PITCH};
    pw_line_t pl[SINFO_WRAP];
    unsigned *w = sinfo.lw + sinfo.nw;
    unsigned len = 0;
    int n, k, nl, maxl = kind == K_HEAD ? SINFO_HEAD_LINES : kind == K_KEY ? 1 : SINFO_WRAP;
    if (!sinfo.lw || !sinfo.ln || !sinfo.d || sinfo.nw + SINFO_SRC + 2 >= SINFO_WIDE ||
        sinfo.nln + SINFO_WRAP >= SINFO_LINES)
        return y;
    while (text[len] && len < 4u * SINFO_SRC) ++len;
    tk_utf8_to_utf16_ex(text, len, w, SINFO_SRC);
    for (n = 0; n < SINFO_SRC && w[n]; ++n) {
    }
    w[n] = 0;
    if (!n) return y;
    nl = pd_lines(sinfo.d, sinfo.st[kind], w, n, SINFO_W, maxl, pl);
    for (k = 0; k < nl; ++k) {
        sinfo.ln[sinfo.nln].off = sinfo.nw + pl[k].start, sinfo.ln[sinfo.nln].len = pl[k].len;
        sinfo.ln[sinfo.nln].y = (short)y, sinfo.ln[sinfo.nln].kind = (unsigned char)kind;
        ++sinfo.nln;
        y += pitch[kind];
    }
    sinfo.nw += n + 1;
    return y;
}

/* A label over its value; nothing for an empty value. */
static int sinfo_pair(const char *key, const char *val, int y) {
    if (!val[0]) return y;
    y = sinfo_put(key, K_KEY, y);
    y = sinfo_put(val, K_VAL, y);
    return y + SINFO_PAIR_GAP;
}

/* The Status pair's words: the engine's state, or the error's text. */
static void sinfo_status(char *out, unsigned n) {
    switch (rd_state()) {
    case RD_CONNECTING:
        snprintf(out, n, "%s", TR("Connecting…"));
        break;
    case RD_PLAYING:
        snprintf(out, n, "%s", TR("Playing"));
        break;
    case RD_PAUSED:
        snprintf(out, n, "%s", TR("Paused"));
        break;
    case RD_ERROR:
        snprintf(out, n, "%s", rd_error()[0] ? rd_error() : TR("Can't play"));
        break;
    default:
        snprintf(out, n, "%s", TR("Stopped"));
    }
}

/* The Status pair (always the last block) laid out again from where it begins. */
static void sinfo_stat_block(void) {
    int y;
    sinfo.nln = sinfo.stat_ln, sinfo.nw = sinfo.stat_nw;
    sinfo_status(sinfo.stat, sizeof sinfo.stat);
    y = sinfo_pair(TR("Status"), sinfo.stat, sinfo.stat_y);
    sinfo.h = (y > sinfo.stat_y ? y - SINFO_PAIR_GAP : sinfo.stat_y) + SINFO_BOTTOM;
    if (sinfo.h < SINFO_VIEW_H) sinfo.h = SINFO_VIEW_H;
    widget_resize(sinfo.view, 320, sinfo.h);
    widget_set_prop_int(sinfo.sv, "virtual_h", sinfo.h);
}

/* The field idx (0 country, 1 codec, 2 bitrate) of a station's info ("country<TAB>codec<TAB>bitrate<TAB>favicon") into out. */
static void sinfo_field(const char *info, int idx, char *out, unsigned n) {
    unsigned q = 0;
    int i;
    for (i = 0; i < idx; ++i) {
        while (*info && *info != '\t') ++info;
        if (*info == '\t') ++info;
    }
    while (*info && *info != '\t') {
        if (q + 1 < n) out[q++] = *info;
        ++info;
    }
    out[q] = 0;
}

/* The pairs the station has, in the page's order. */
static void sinfo_build(const char *name, const char *url, const char *info) {
    char country[64], codec[32], rate[24], logo[RD_FAV_MAX + 1];
    int y = SINFO_TOP;
    sinfo.nln = sinfo.nw = 0;
    y = sinfo_put(name[0] ? name : TR("Radio"), K_HEAD, y);
    y += SINFO_HEAD_GAP;
    y = sinfo_pair(TR("Stream URL"), url, y);
    rd_favicon(info, logo, sizeof logo);
    y = sinfo_pair(TR("Logo URL"), logo, y);
    sinfo_field(info, 0, country, sizeof country);
    sinfo_field(info, 1, codec, sizeof codec);
    sinfo_field(info, 2, rate, sizeof rate);
    if (!strcmp(rate, "0")) rate[0] = 0;
    if (rate[0]) snprintf(rate + strlen(rate), sizeof rate - strlen(rate), " kbps");
    y = sinfo_pair(TR("Country"), country, y);
    y = sinfo_pair(TR("Codec"), codec, y);
    y = sinfo_pair(TR("Bitrate"), rate, y);
    y = sinfo_pair(TR("Source"), info[0] ? TR("Radio Browser") : TR("Imported"), y);
    sinfo.stat_ln = sinfo.nln, sinfo.stat_nw = sinfo.nw, sinfo.stat_y = y;
    sinfo_stat_block();
}

/* One text drawn wholly inside the view (AWTK does not clip texts; the same rule as every text of the payload's pages). */
static void sinfo_text(void *canvas, const unsigned *s, int n, int y, int h) {
    int rect[4];
    if (n <= 0 || y < 0 || y + h > SINFO_VIEW_H) return;
    rect[0] = SINFO_X, rect[1] = y, rect[2] = SINFO_W, rect[3] = h;
    canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

static int sinfo_on_paint(void *ctx, void *e) {
    static const short pitch[3] = {SINFO_HEAD_PITCH, SINFO_KEY_PITCH, SINFO_VAL_PITCH};
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off, i, kind = -1;
    (void)ctx;
    if (!canvas || !sinfo.win) return RET_OK;
    off = SINFO_I(sinfo.sv, SC_YOFF);
    if (sinfo.fade && (off > 0) != sinfo.fade_on) {
        sinfo.fade_on = off > 0;
        widget_set_visible(sinfo.fade, sinfo.fade_on, 0);
        widget_set_sensitive(sinfo.fade, 0);
    }
    SINFO_I(canvas, CANVAS_OY) += off;
    for (i = 0; sinfo.lw && sinfo.ln && i < sinfo.nln; ++i) {
        int y = sinfo.ln[i].y - off, k = sinfo.ln[i].kind;
        if (y + pitch[k] <= 0) continue;
        if (y >= SINFO_VIEW_H) break;
        if (k != kind) widget_prepare_text_style(sinfo.st[kind = k], canvas);
        sinfo_text(canvas, sinfo.lw + sinfo.ln[i].off, sinfo.ln[i].len, y, pitch[k]);
    }
    SINFO_I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* The 500 ms page timer: the Status pair again when the words changed (nothing while the page is covered or the screen is dark). */
static int sinfo_tick(const void *unused) {
    char now[sizeof sinfo.stat];
    (void)unused;
    if (!sinfo.win) {
        sinfo.timer = 0;
        return RET_OK;
    }
    if (!pod_screen_lit() || !pod_is_top(sinfo.win)) return RET_REPEAT;
    sinfo_status(now, sizeof now);
    if (strcmp(now, sinfo.stat)) {
        sinfo_stat_block();
        widget_invalidate_force(sinfo.win, (void *)0);
    }
    return RET_REPEAT;
}

/* ctx is the window the handler was bound to: a closed page is destroyed later, after sinfo_open may have opened its successor, whose state this must not clear. */
static int sinfo_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != sinfo.win) return RET_OK;
    if (sinfo.timer) timer_remove(sinfo.timer);
    sinfo_free();
    memset(&sinfo, 0, sizeof sinfo);
    return RET_OK;
}

int sinfo_open(void) {
    const rd_list_t *l = rd_list();
    int at = rd_at();
    char name[RD_NAME_MAX + 1], url[1100], info[300];
    if (sinfo.win && pod_is_top(sinfo.win) && widget_is_window_opened(sinfo.win)) return 0;
    if (home_off() || !l->n || at >= l->n) return -1;
    snprintf(name, sizeof name, "%s", rd_name(l, at));
    snprintf(url, sizeof url, "%s", rd_url(l, at));
    snprintf(info, sizeof info, "%s", rd_info(l, at));
    if (sinfo
            .win) { /* closing (destroyed later) or under another window: let it go, its late EVT_DESTROY finds sinfo.win changed */
        if (widget_is_window_opened(sinfo.win)) window_close(sinfo.win);
        if (sinfo.timer) timer_remove(sinfo.timer);
        sinfo_free();
    }
    memset(&sinfo, 0, sizeof sinfo);
    sinfo.win = window_open("m1plus_radioinfo");
    if (!sinfo.win) return -1;
    widget_on(sinfo.win, EVT_DESTROY, sinfo_on_destroy, sinfo.win);
    pod_bind(sinfo.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(sinfo.win, "btn_backtoplayer", pod_on_player, (void *)0);
    sinfo.sv = widget_lookup(sinfo.win, "ri_scrollview", 1);
    sinfo.view = widget_lookup(sinfo.win, "ri_view", 1);
    sinfo.fade = widget_lookup(sinfo.win, "img_nb_fade", 1);
    sinfo.st[K_HEAD] = widget_lookup(sinfo.win, "label_head", 1);
    sinfo.st[K_KEY] = widget_lookup(sinfo.win, "label_key", 1);
    sinfo.st[K_VAL] = widget_lookup(sinfo.win, "label_val", 1);
    if (!sinfo.sv || !sinfo.view || !sinfo.st[K_HEAD] || !sinfo.st[K_KEY] || !sinfo.st[K_VAL]) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    sinfo.lw = calloc(SINFO_WIDE + 1, sizeof *sinfo.lw);
    sinfo.ln = calloc(SINFO_LINES, sizeof *sinfo.ln);
    sinfo.d = calloc(1, sizeof *sinfo.d);
    if (!sinfo.lw || !sinfo.ln || !sinfo.d) { /* no memory: no page */
        navigator_back();
        return -1;
    }
    sinfo_build(name, url, info);
    widget_on(sinfo.view, EVT_AFTER_PAINT, sinfo_on_paint, (void *)0);
    sinfo.timer = timer_add(sinfo_tick, (void *)0, 500);
    widget_invalidate_force(sinfo.win, (void *)0);
    return 0;
}
