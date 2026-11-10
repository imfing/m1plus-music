/* Release Notes: the page behind the Software Update page's "Release Notes" pill (docs/modules/update.md "Release notes").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The notes are the text the check kept (pn_up_notes: the GitHub release's body, cleaned). The page is the Find Cover & Lyrics lyrics detail's mechanism (patch/onlineart.c): the stock navbar over a stock list
 * (list_view > scroll_view) holding ONE content view that this file paints in its EVT_AFTER_PAINT (the scroll offset taken off the canvas), the text wrapped once into lines by the Podcasts episode page's wrapper
 * (pd_lines: patch/pcwrap.c, from the font's own advances; kinsoku, CJK anywhere), so the stock scroll_view does the dragging and the fling. No network, no timer, nothing on the card; the memory is freed with the window.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "i18n.h"
#include "podcasts.h"
#include "pcjson.h"
#include "pcnet.h"
#include "pcdetail.h"
#include "upver.h"

#define RN_X 16 /* the text's left edge and width */
#define RN_W 288
#define RN_TOP 12
#define RN_HEAD_H 30 /* the heading "Version 1.0.1" (22 px) */
#define RN_HEAD_GAP 12
#define RN_PITCH 24 /* a line of the notes (18 px) */
#define RN_PITCH_LOCK 27 /* a line of the Custom Wallpaper instructions (20 px, the asset's label_line) */
#define RN_GAP 12 /* an empty line of the notes */
#define RN_BOTTOM 20
#define RN_VIEW_H 400 /* the list under the navbar */
#define RN_WIDE (UP_NOTES_MAX + 2048) /* wide chars kept: a char is at least one byte, a line adds its NUL */
#define RN_LINES 700 /* wrapped lines kept */
#define RN_SRC 600 /* wide chars of one line of the notes (a longer one ends there) */
#define RN_WRAP 40 /* lines one line of the notes may take (600 chars of the widest glyph need about 40) */

typedef struct {
    int off; /* the line's first char in rn.lw */
    short len, y; /* chars; top in content coordinates */
} rn_ln_t;

static struct {
    void *win, *sv, *view, *st_head, *st_line;
    unsigned *lw; /* the notes, wide, one NUL after each source line */
    rn_ln_t *ln;
    int nln, h, pitch; /* pitch: a line's height, RN_PITCH or RN_PITCH_LOCK */
    unsigned head[40]; /* "Version 1.0.1", wide */
    int headn;
} rn __attribute__((section(".scratch")));

#define RN_I(w, off) (*(int *)((char *)(w) + (off)))

static void rn_free(void) {
    free(rn.lw);
    free(rn.ln);
    rn.lw = (unsigned *)0, rn.ln = (rn_ln_t *)0;
}

/* The lines: each line of the notes wrapped to RN_W; an empty one is a gap. Cut where the tables are full. */
static void rn_build(const char *text) {
    pd_t *d = calloc(1, sizeof *d);
    int wn = 0, y = RN_TOP + RN_HEAD_H + RN_HEAD_GAP, gap = 1;
    rn.lw = calloc(RN_WIDE + 1, sizeof *rn.lw);
    rn.ln = calloc(RN_LINES, sizeof *rn.ln);
    rn.nln = 0;
    if (!d || !rn.lw || !rn.ln) {
        free(d);
        rn_free();
        rn.h = RN_VIEW_H;
        return;
    }
    while (*text && rn.nln + RN_WRAP < RN_LINES && wn + RN_SRC + 2 < RN_WIDE) {
        const char *e = text;
        unsigned len;
        int n, k, nl;
        pw_line_t pl[RN_WRAP];
        while (*e && *e != '\n') ++e;
        len = (unsigned)(e - text);
        while (len && (text[len - 1] == ' ' || text[len - 1] == '\t')) --len;
        if (!len) {
            if (!gap) y += RN_GAP, gap = 1;
            text = *e ? e + 1 : e;
            continue;
        }
        gap = 0;
        if (len > 4u * RN_SRC) len = 4u * RN_SRC;
        tk_utf8_to_utf16_ex(text, len, rn.lw + wn, RN_SRC);
        for (n = 0; n < RN_SRC && rn.lw[wn + n]; ++n) {
        }
        text = *e ? e + 1 : e;
        if (!n) continue;
        nl = pd_lines(d, rn.st_line, rn.lw + wn, n, RN_W, RN_WRAP, pl);
        for (k = 0; k < nl; ++k) {
            rn.ln[rn.nln].off = wn + pl[k].start, rn.ln[rn.nln].len = pl[k].len, rn.ln[rn.nln].y = (short)y;
            ++rn.nln;
            y += rn.pitch;
        }
        wn += n + 1;
    }
    rn.h = y + RN_BOTTOM;
    if (rn.h < RN_VIEW_H) rn.h = RN_VIEW_H;
    free(d);
}

/* One text drawn wholly inside the view (AWTK does not clip texts; the same rule as every text of the payload's pages). */
static void rn_text(void *canvas, const unsigned *s, int n, int y, int h) {
    int rect[4];
    if (n <= 0 || y < 0 || y + h > RN_VIEW_H) return;
    rect[0] = RN_X, rect[1] = y, rect[2] = RN_W, rect[3] = h;
    canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

static int rn_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off, i;
    (void)ctx;
    if (!canvas || !rn.win) return RET_OK;
    off = RN_I(rn.sv, SC_YOFF);
    RN_I(canvas, CANVAS_OY) += off;
    widget_prepare_text_style(rn.st_head, canvas);
    rn_text(canvas, rn.head, rn.headn, RN_TOP - off, RN_HEAD_H);
    widget_prepare_text_style(rn.st_line, canvas);
    for (i = 0; rn.lw && rn.ln && i < rn.nln; ++i) {
        int y = rn.ln[i].y - off;
        if (y + rn.pitch <= 0) continue;
        if (y >= RN_VIEW_H) break;
        rn_text(canvas, rn.lw + rn.ln[i].off, rn.ln[i].len, y, rn.pitch);
    }
    RN_I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

static int rn_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != rn.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    rn_free();
    memset(&rn, 0, sizeof rn);
    return RET_OK;
}

/* The page: window `name`, the heading and the text (both UTF-8) painted by the shared painter, a line of the text `pitch` px high. 0 once it is up (or a page of this file is already open); -1 when it could not open (nothing is left of it). */
static int rn_open(const char *name, const char *head, const char *text, int pitch) {
    unsigned o = 0;
    if (rn.win) return 0;
    memset(&rn, 0, sizeof rn);
    while (head[o]) ++o;
    rn.pitch = pitch;
    rn.win = window_open(name);
    if (!rn.win) {
        memset(&rn, 0, sizeof rn);
        return -1;
    }
    widget_on(rn.win, EVT_DESTROY, rn_on_destroy, rn.win);
    pod_bind(rn.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(rn.win, "btn_backtoplayer", pod_on_player, (void *)0);
    rn.sv = widget_lookup(rn.win, "rn_scrollview", 1);
    rn.view = widget_lookup(rn.win, "rn_view", 1);
    rn.st_head = widget_lookup(rn.win, "label_head", 1);
    rn.st_line = widget_lookup(rn.win, "label_line", 1);
    if (!rn.sv || !rn.view || !rn.st_head || !rn.st_line) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    tk_utf8_to_utf16_ex(head, o, rn.head, 39);
    for (rn.headn = 0; rn.headn < 39 && rn.head[rn.headn]; ++rn.headn) {
    }
    rn_build(text);
    widget_resize(rn.view, 320, rn.h);
    widget_set_prop_int(rn.sv, "virtual_h", rn.h);
    widget_on(rn.view, EVT_AFTER_PAINT, rn_on_paint, (void *)0);
    widget_invalidate_force(rn.win, (void *)0);
    return 0;
}

/* Open: the Software Update page's Release Notes pill. 0 once the page is up (or already open); -1 when it could not open or there are no notes (nothing is left of it). */
int relnotes_open(void) {
    char head[48];
    const char *notes = pn_up_notes(), *tpl = TR("Version %s"), *tag = pn_up_tag();
    unsigned o = 0;
    if (rn.win) return 0;
    if (!notes[0]) return -1;
    while (*tpl && o + 1 < sizeof head) {
        if (tpl[0] == '%' && tpl[1] == 's') { /* (the translations are printf-like, never a format) */
            tpl += 2;
            while (*tag && o + 1 < sizeof head) head[o++] = *tag++;
        } else
            head[o++] = *tpl++;
    }
    head[o] = 0;
    return rn_open("m1plus_relnotes", head, notes, RN_PITCH);
}

/* Open: the Lock Screen's Custom Wallpaper row, the same page and painter, its text 20 px on a 27 px pitch (docs/modules/lockscreen.md "Custom Wallpaper"): the heading and three paragraphs, a blank line between them (the 12 px gap), in the
 * language in use. 0 once it is up (or already open); -1 when it could not open. */
int lockinfo_open(void) {
    char text[3 * 240 + 4];
    snprintf(text, sizeof text, "%s\n\n%s\n\n%s",
             TR("Copy pictures to a folder named lockscreenimage at the top level of the card."),
             TR("JPG or PNG, exactly 320 x 480 pixels, under 1 MB each."),
             TR("Up to 5 pictures. Choose one in Wallpaper."));
    return rn_open("m1plus_lockinfo", TR("Add Your Own Pictures"), text, RN_PITCH_LOCK);
}
