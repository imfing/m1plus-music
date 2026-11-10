/* M1+ Music band page: one band of a preset (docs/modules/peq.md "Preset editing").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opened by a band row of the Preset page (patch/peqpage.c, which owns the working preset and the file): ui/m1plus_peqband.bin, a cards page whose navbar is the glass capsule [Previous band | Next band | Now Playing] under the title "Band N".
 * Under it the graph card of patch/peqpage.c with a ring on the band's curve, a Peak / Low shelf / High shelf control (one view painted in its EVT_BEFORE_PAINT: the container, the selected segment's pill; three labels over it) and a card of three horizontal
 * sliders (one view: the card with its three tracks baked in, a white fill to the thumb and a round thumb, painted before its labels): Frequency (log, 20 Hz .. 20 kHz, three significant figures), Gain (linear +-12 dB, 0.1 dB) and Q (log, 0.1 .. 10, 0.01). The top 28 px of a slider
 * row are its name and value: a tap there types the value on the number keypad (a bottom sheet of the page's asset, bk_*: digits, point, backspace, a minus key for Gain, an Hz / kHz key for Frequency; Done clamps to the engine's range: 20 Hz-20 kHz, +-24 dB, Q 0.1-10); the rest of the row is the track: a touch sets the value at once and a drag follows the finger.
 *
 * An edit changes the working preset's band in place and plays at once: the record is saved and the player told (peqpage_commit(1), the same reload path as the 10-Band editor: at most every BD_SEND_MS while dragging, and once more at the release); the graph is drawn again at most every
 * BD_GRAPH_MS. Leaving the page (Back or Now Playing) with edits not saved asks first (bd_on_back): a centred dialog, Save / Save As New... / Don't Save / Cancel. A drag is the view's alone (DOWN grabs the touch at the window, as the 10-Band editor's sliders do, and the scroll_view's yslidable is off for the gesture); a touch in the text zone is no gesture: it
 * is a tap when it ends within BD_TAP_PX of where it began. Nothing here runs a timer, a hook or anything at boot.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "i18n.h"
#include "peq.h"
#include "peqpage.h"
#include "tenband.h"

#define BD_GRAPH_MS 60
#define BD_SEND_MS 150
#define BD_TAP_PX 10 /* a touch in the text zone that moves less than this is a tap */
#define BD_FREQ_MIN 20.0
#define BD_FREQ_MAX 20000.0
#define BD_GAIN_SLIDE 12.0 /* the slider's range, either way (the engine takes 24) */
#define BD_Q_MIN 0.1
#define BD_Q_MAX 10.0
#define BD_GREY "#8A8A8A"
#define I(w, off) (*(int *)((char *)(w) + (off)))

static struct {
    void *win, *sv, *graph, *gtop, *gbot, *seg, *hsl, *title;
    void *seg_l[3], *hs_v[BD_ROWS];
    void *dscrim, *dcard, *dname, *ditem[4]; /* the unsaved-changes dialog */
    void *segbg, *pill, *card, *fill, *thumb, *ring; /* bitmaps (none: no memory) */
    peq_graph g;
    int band, n; /* the band shown; how many there are */
    int drag, down_row, down_x, down_y, seg_down, seg_x,
        seg_y; /* drag: the row being dragged, -1 none; down_*: a press in a text zone; seg_*: a press on the control */
    int dirty, last_graph, last_send, sent, graph_due, slide;
    void *kscrim, *kcard, *ktitle, *krange, *kval, *kunit, *kcaret, *kunitk, *ksign, *kk[10], *kdot, *kdel, *kcancel,
        *kdone; /* the number keypad */
    char ktext[16];
    int kopen, krow, kkhz, kneg,
        kn; /* open; the row it is for; the number reads in kHz; a minus sign; the number's length */
    int dlg,
        leave; /* dialog open; the way out it was asked for: 0 none, 1 Back, 2 Now Playing (kept while the Save As name entry is up) */
    int ring_x, ring_y; /* the ring's centre in the graph view, -1 none */
} bd __attribute__((section(".scratch")));

static int pend_band
    __attribute__((section(".scratch"))); /* the band peqband_open asks for (read by the page as it opens) */

/* ---------------------------------------------------------------------------
 * Values <-> track positions
 */
static double bd_clamp(double v, double lo, double hi) { return v < lo ? lo : v > hi ? hi : v; }

/* The track position 0..1 of a band's value in row r (0 frequency, 1 gain, 2 Q). */
static double bd_t(int r, const peq_band *b) {
    if (r == 0) return bd_clamp(pp_db10(b->frequency / BD_FREQ_MIN) / 30.0, 0, 1);
    if (r == 1) return bd_clamp((b->gain + BD_GAIN_SLIDE) / (2 * BD_GAIN_SLIDE), 0, 1);
    return bd_clamp(pp_db10(b->q / BD_Q_MIN) / 20.0, 0, 1);
}

/* The value a position t of the track gives: frequency to three significant figures, gain to 0.1 dB, Q to 0.01. */
static double bd_value(int r, double t) {
    t = bd_clamp(t, 0, 1);
    if (r == 0) {
        double f = BD_FREQ_MIN * pow(1000, t), step = f < 100 ? 0.1 : f < 1000 ? 1 : f < 10000 ? 10 : 100;
        return bd_clamp((int)(f / step + 0.5) * step, BD_FREQ_MIN, BD_FREQ_MAX);
    }
    if (r == 1) {
        double g = (2 * t - 1) * BD_GAIN_SLIDE * 10;
        return (int)(g + (g < 0 ? -0.5 : 0.5)) / 10.0;
    }
    return bd_clamp((int)(BD_Q_MIN * pow(100, t) * 100 + 0.5) / 100.0, BD_Q_MIN, BD_Q_MAX);
}

/* A touch x in the view (the list's coordinates: the card is BD_CARD_X in) to a track position. */
__attribute__((used, retain)) double peqband_t(int x) {
    return bd_clamp((x - BD_CARD_X - BD_TRACK_X) / (double)BD_TRACK_W, 0, 1);
}

static int bd_px(int r) {
    peq_preset *p = peqpage_work();
    return p && bd.band < p->count ? (int)(bd_t(r, &p->bands[bd.band]) * BD_TRACK_W + 0.5) : 0;
}

/* The band's field of row r set to v (the engine's range); 1 when it changed. */
static int bd_set(int r, double v) {
    peq_preset *p = peqpage_work();
    peq_band *b;
    double *f;
    if (!p || bd.band >= p->count) return 0;
    b = &p->bands[bd.band];
    f = r == 0 ? &b->frequency : r == 1 ? &b->gain : &b->q;
    v = r == 0   ? bd_clamp(v, BD_FREQ_MIN, BD_FREQ_MAX)
        : r == 1 ? bd_clamp(v, -24, 24)
                 : bd_clamp(v, BD_Q_MIN, BD_Q_MAX);
    if (*f == v) return 0;
    *f = v;
    return 1;
}

/* ---------------------------------------------------------------------------
 * Bitmaps: the control's container and pill, the card with its tracks, the fill, the thumb, the ring
 */
static unsigned bd_seg_px(int x, int y, int w, int h) { return tb_px(28, tb_cover(x, y, w, h, BD_SEG_R)); }
static unsigned bd_pill_px(int x, int y, int w, int h) {
    return tb_px(229, tb_cover(x, y, w, h, BD_SEG_R - BD_SEG_PAD + 1));
}

/* The card: #1C1C1C with BD_HSL_R corners, a hairline under the first two rows and a track (a capsule, grey 62) in each row. */
static unsigned bd_card_px(int x, int y, int w, int h) {
    double v = 28, a = 1, r = BD_TRACK_H / 2.0;
    int row = y / BD_ROW_H;
    if (y % BD_ROW_H == BD_ROW_H - 1 && row < BD_ROWS - 1 && x >= BD_TRACK_X) v = 51;
    if (x >= BD_TRACK_X - 3 && x < BD_TRACK_X + BD_TRACK_W + 3 && row < BD_ROWS) {
        double cy = row * BD_ROW_H + BD_TRACK_Y,
               dx = x + 0.5 < BD_TRACK_X + r                ? BD_TRACK_X + r - (x + 0.5)
                    : x + 0.5 > BD_TRACK_X + BD_TRACK_W - r ? x + 0.5 - (BD_TRACK_X + BD_TRACK_W - r)
                                                            : 0,
               dy = y + 0.5 - cy, d = __builtin_sqrt(dx * dx + dy * dy);
        v += (62 - v) * bd_clamp(r + 0.5 - d, 0, 1);
    }
    if ((x < BD_HSL_R || x >= w - BD_HSL_R) && (y < BD_HSL_R || y >= h - BD_HSL_R)) a = tb_cover(x, y, w, h, BD_HSL_R);
    return tb_px(v, a);
}

static unsigned bd_fill_px(int x, int y, int w, int h) { return tb_px(242, tb_cover(x, y, w, h, BD_TRACK_H / 2.0)); }
static unsigned bd_thumb_px(int x, int y, int w, int h) { return tb_px(250, tb_cover(x, y, w, h, w / 2.0)); }

/* The ring that marks the band on the curve: a white ring BD_RING wide with a black centre. */
static unsigned bd_ring_px(int x, int y, int w, int h) {
    double dx = x + 0.5 - w / 2.0, dy = y + 0.5 - h / 2.0, d = __builtin_sqrt(dx * dx + dy * dy), r = w / 2.0;
    double outer = bd_clamp(r + 0.5 - d, 0, 1), inner = bd_clamp(d - (r - 2.5) + 0.5, 0, 1);
    return tb_px(242 * inner, outer);
}

static void *bd_canvas(void *e) { return e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0; }

/* ---------------------------------------------------------------------------
 * Painting
 */
static int bd_on_gpaint(void *ctx, void *e) {
    void *canvas = bd_canvas(e);
    (void)ctx;
    if (!bd.win) return RET_OK;
    peq_graph_paint(&bd.g, e);
    if (canvas && bd.ring && bd.ring_x >= 0)
        peq_blit(canvas, bd.ring, BD_RING, BD_RING, bd.ring_x - BD_RING / 2, bd.ring_y - BD_RING / 2);
    return RET_OK;
}

static int bd_on_spaint(void *ctx, void *e) {
    void *canvas = bd_canvas(e);
    peq_preset *p = peqpage_work();
    (void)ctx;
    if (!canvas || !bd.win || !bd.segbg || !p || bd.band >= p->count) return RET_OK;
    peq_blit(canvas, bd.segbg, BD_SEG_W, BD_SEG_H, BD_CARD_X, BD_SEG_Y);
    if (bd.pill)
        peq_blit(canvas, bd.pill, BD_SEG_PILL_W, BD_SEG_PILL_H,
                 BD_CARD_X + p->bands[bd.band].type * (BD_SEG_W / 3) + BD_SEG_PAD, BD_SEG_Y + BD_SEG_PAD);
    return RET_OK;
}

static int bd_on_hpaint(void *ctx, void *e) {
    void *canvas = bd_canvas(e);
    int r;
    (void)ctx;
    if (!canvas || !bd.win || !bd.card) return RET_OK;
    peq_blit(canvas, bd.card, BD_HSL_W, BD_HSL_H, BD_CARD_X, 0);
    for (r = 0; r < BD_ROWS; ++r) {
        int px = bd_px(r), cx = BD_CARD_X + BD_TRACK_X, cy = r * BD_ROW_H + BD_TRACK_Y;
        if (bd.fill && px > 0) peq_blit(canvas, bd.fill, px, BD_TRACK_H, cx, cy - BD_TRACK_H / 2);
        if (bd.thumb) peq_blit(canvas, bd.thumb, BD_THUMB, BD_THUMB, cx + px - BD_THUMB / 2, cy - BD_THUMB / 2);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The page's texts from the band
 */
/* "3.2": a Q in hundredths, the zeros trimmed (the Preset page's form). */
static void bd_texts(void) {
    peq_preset *p = peqpage_work();
    char text[48];
    int k;
    if (!p || bd.band >= p->count) return;
    pp_freq(text, sizeof text, p->bands[bd.band].frequency);
    widget_set_text_utf8(bd.hs_v[0], text);
    pp_gain(text, sizeof text, p->bands[bd.band].gain, 1);
    widget_set_text_utf8(bd.hs_v[1], text);
    pp_qtext(text, sizeof text, p->bands[bd.band].q);
    widget_set_text_utf8(bd.hs_v[2], text);
    for (k = 0; k < 3; ++k) peq_label_colors(bd.seg_l[k], k == p->bands[bd.band].type ? "#000000" : "#FFFFFF");
}

/* The ring's place on the curve at the band's frequency (the curve of the whole preset at that column, clamped to the plot). */
static void bd_ring(void) {
    peq_preset *p = peqpage_work();
    int c;
    double y;
    bd.ring_x = bd.ring_y = -1;
    if (!p || bd.band >= p->count || !bd.ring) return;
    c = (int)(pp_db10(p->bands[bd.band].frequency / 20.0) / 10.0 * GR_DECADE);
    c = c < 0 ? 0 : c >= GR_PW ? GR_PW - 1 : c;
    y = GR_PY0 + GR_PH / 2 + 0.5 - bd.g.db[c] * (GR_PH / 2.0) / bd.g.range;
    bd.ring_x = GR_CARD_X + GR_PX0 + c;
    bd.ring_y = (int)bd_clamp(y, GR_PY0 + 0.5, GR_PY0 + GR_PH - 0.5);
}

static void bd_graph(void) {
    peq_preset *p = peqpage_work();
    if (!p) return;
    peq_graph_curve(&bd.g, p);
    peq_graph_scale(&bd.g, bd.gtop, bd.gbot);
    peq_graph_draw(&bd.g);
    bd_ring();
    widget_invalidate_force(bd.graph, (void *)0);
    bd.graph_due = 0;
}

static void bd_title(void) {
    char text[48];
    pod_fmt(text, sizeof text, TR("Band %d"), bd.band + 1);
    widget_set_text_utf8(bd.title, text);
}

/* Everything from the working preset's band. */
static void bd_refresh(void) {
    bd_title();
    bd_texts();
    bd_graph();
    widget_invalidate_force(bd.seg, (void *)0);
    widget_invalidate_force(bd.hsl, (void *)0);
}

/* The edit plays: the record and the player (peqpage_commit(1)). */
static void bd_send(void) {
    bd.dirty = 0;
    peqpage_commit(1);
}

/* ---------------------------------------------------------------------------
 * Touch: the control
 */
static unsigned bd_time(void *e) { return (unsigned)I(e, 8); }

static void bd_pt(void *view, void *e, int *x, int *y) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(view, pt);
    *x = pt[0], *y = pt[1];
}

static int bd_on_sdown(void *ctx, void *e) {
    int x, y;
    (void)ctx;
    if (!e || !bd.win) return RET_OK;
    bd_pt(bd.seg, e, &x, &y);
    bd.seg_down = 1, bd.seg_x = x, bd.seg_y = y;
    return RET_OK;
}

static int bd_on_sabort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bd.seg_down = 0;
    return RET_OK;
}

/* A release near the press, on the control: that segment is the band's type. */
static int bd_on_sup(void *ctx, void *e) {
    int x, y, k, dx, dy;
    peq_preset *p = peqpage_work();
    (void)ctx;
    if (!e || !bd.win || !bd.seg_down || !p || bd.band >= p->count) return RET_OK;
    bd.seg_down = 0;
    bd_pt(bd.seg, e, &x, &y);
    dx = x - bd.seg_x, dy = y - bd.seg_y;
    if (dx < -BD_TAP_PX || dx > BD_TAP_PX || dy < -BD_TAP_PX || dy > BD_TAP_PX) return RET_OK;
    x -= BD_CARD_X;
    if (x < 0 || x >= BD_SEG_W || y < BD_SEG_Y || y >= BD_SEG_Y + BD_SEG_H) return RET_OK;
    k = x / (BD_SEG_W / 3);
    if (k > 2) k = 2;
    if (p->bands[bd.band].type == k) return RET_OK;
    p->bands[bd.band].type = k;
    bd_send();
    bd_refresh();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch: the sliders
 */
static void bd_slide(int on) {
    if (!on) {
        bd.slide = widget_get_prop_int(bd.sv, "yslidable", 1);
        widget_set_prop_int(bd.sv, "yslidable", 0);
    } else
        widget_set_prop_int(bd.sv, "yslidable", bd.slide);
}

static void bd_follow(void *e) {
    int x, y, r = bd.drag;
    unsigned now = bd_time(e);
    bd_pt(bd.hsl, e, &x, &y);
    if (!bd_set(r, bd_value(r, peqband_t(x)))) return;
    bd.dirty = 1;
    bd_texts();
    widget_invalidate_force(bd.hsl, (void *)0);
    if (!bd.sent || now - (unsigned)bd.last_graph >= BD_GRAPH_MS)
        bd.last_graph = (int)now, bd_graph();
    else
        bd.graph_due = 1;
    if (!bd.sent || now - (unsigned)bd.last_send >= BD_SEND_MS) {
        bd.last_send = (int)now, bd.sent = 1;
        bd_send();
    }
}

static void bd_end(void) {
    if (bd.drag < 0) return;
    bd.drag = -1;
    widget_ungrab(bd.win, bd.hsl);
    bd_slide(1);
    if (bd.dirty) bd_send(); /* the last step, saved */
    if (bd.graph_due) bd_graph();
    widget_invalidate_force(bd.hsl, (void *)0);
}

static int bd_on_down(void *ctx, void *e) {
    int x, y, r;
    (void)ctx;
    if (!e || !bd.win || bd.drag >= 0) return RET_OK;
    bd_pt(bd.hsl, e, &x, &y);
    if (x < BD_CARD_X || x >= BD_CARD_X + BD_HSL_W || y < 0 || y >= BD_HSL_H) return RET_OK; /* beside the card */
    r = y / BD_ROW_H;
    if (y % BD_ROW_H < BD_TEXT_H) { /* the name and the value: a tap types it */
        bd.down_row = r, bd.down_x = x, bd.down_y = y;
        return RET_OK;
    }
    bd.drag = r, bd.dirty = bd.sent = 0, bd.down_row = -1;
    widget_grab(bd.win, bd.hsl);
    bd_slide(0);
    bd_follow(e);
    widget_invalidate_force(bd.hsl, (void *)0);
    return RET_OK;
}

static int bd_on_move(void *ctx, void *e) {
    (void)ctx;
    if (e && bd.win && bd.drag >= 0) bd_follow(e);
    return RET_OK;
}

static void bd_show(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* ---------------------------------------------------------------------------
 * The number keypad (a bottom sheet in the page's asset: bk_*): a tap on a row's name or value opens it with the value in its most natural unit
 */
#define BK_MAX 7 /* characters of the number */
#define MINUS "\xe2\x88\x92" /* U+2212 */

/* The unit shown after the number: Hz or kHz (the key toggles), dB, none for Q. */
static const char *bk_hz(void) { return bd.kkhz ? "kHz" : "Hz"; }
static const char *bk_unit(void) { return bd.krow == 0 ? bk_hz() : bd.krow == 1 ? "dB" : ""; }

/* The number, the unit and the caret in the field: the unit at the field's right, the caret before it, the number right aligned against the caret. */
static void bk_show_text(void) {
    char text[16];
    const char *unit = bk_unit();
    int uw = bd.krow == 0 ? (bd.kkhz ? 34 : 26) : bd.krow == 1 ? 26 : 0;
    int ux = BK_FIELD_X + BK_FIELD_W - BK_PAD - uw, cx = ux - (uw ? BK_CARET_GAP : 0) - BK_CARET_W;
    snprintf(text, sizeof text, "%s%s", bd.kneg ? MINUS : "", bd.ktext);
    widget_set_text_utf8(bd.kval, text);
    widget_set_text_utf8(bd.kunit, unit);
    widget_move(bd.kunit, ux, BK_FIELD_Y);
    widget_resize(bd.kunit, uw ? uw : 1, BK_FIELD_H);
    widget_move(bd.kcaret, cx, BK_FIELD_Y + (BK_FIELD_H - BK_CARET_H) / 2);
    widget_move(bd.kval, BK_FIELD_X + 10, BK_FIELD_Y + (BK_FIELD_H - BK_VAL_H) / 2);
    widget_resize(bd.kval, cx - 2 - (BK_FIELD_X + 10), BK_VAL_H);
    widget_set_text_utf8(bd.kunitk, bk_hz());
    widget_invalidate_force(bd.kcard, (void *)0);
}

static void bk_close(void) {
    bd.kopen = 0;
    bd_show(bd.kscrim, 0);
    bd_show(bd.kcard, 0);
}

/* A digit or the point. */
static int bd_on_kkey(void *ctx, void *e) {
    int c = (int)(long)ctx;
    (void)e;
    if (!bd.win || !bd.kopen) return RET_OK;
    if (c == '.') {
        int i;
        for (i = 0; i < bd.kn; ++i)
            if (bd.ktext[i] == '.') return RET_OK;
        if (bd.kn + 2 > BK_MAX) return RET_OK;
        if (!bd.kn) bd.ktext[bd.kn++] = '0';
        bd.ktext[bd.kn++] = '.';
    } else {
        if (bd.kn == 1 && bd.ktext[0] == '0') bd.kn = 0; /* no leading zero */
        if (bd.kn >= BK_MAX) return RET_OK;
        bd.ktext[bd.kn++] = (char)c;
    }
    bd.ktext[bd.kn] = 0;
    bk_show_text();
    return RET_OK;
}

/* Backspace: the last character; with the number empty, the minus sign. */
static int bd_on_kdel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bd.win || !bd.kopen) return RET_OK;
    if (bd.kn)
        bd.ktext[--bd.kn] = 0;
    else
        bd.kneg = 0;
    bk_show_text();
    return RET_OK;
}

/* The minus key (Gain only). */
static int bd_on_ksign(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bd.win || !bd.kopen || bd.krow != 1) return RET_OK;
    bd.kneg = !bd.kneg;
    bk_show_text();
    return RET_OK;
}

/* The unit key (Frequency only): the number now reads in the other unit. */
static int bd_on_kunit(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bd.win || !bd.kopen || bd.krow != 0) return RET_OK;
    bd.kkhz = !bd.kkhz;
    bk_show_text();
    return RET_OK;
}

/* Done: the typed number in its unit, clamped to the engine's range; text that is no number changes nothing. Cancel and the scrim close the sheet and change nothing. */
static int bd_on_kdone(void *ctx, void *e) {
    double v;
    int r = bd.krow;
    (void)ctx;
    (void)e;
    if (!bd.win || !bd.kopen) return RET_OK;
    bk_close();
    if (bd.kn && bd.ktext[bd.kn - 1] == '.') bd.ktext[--bd.kn] = 0;
    if (r < 0 || r >= BD_ROWS || !bd.kn || !peq_number(bd.ktext, &v)) return RET_OK;
    if (bd.kneg) v = -v;
    if (r == 0 && bd.kkhz) v *= 1000;
    if (!bd_set(r, v)) return RET_OK;
    bd_send();
    bd_refresh();
    return RET_OK;
}

static int bd_on_kcancel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bd.win && bd.kopen) bk_close();
    return RET_OK;
}

/* A tap on a slider row's text zone: the number keypad with the value as it is, in the most natural unit (kHz from 1000 Hz). */
static void bd_type(int r) {
    peq_preset *p = peqpage_work();
    char range[64];
    double v;
    if (!p || bd.band >= p->count) return;
    v = r == 0 ? p->bands[bd.band].frequency : r == 1 ? p->bands[bd.band].gain : p->bands[bd.band].q;
    bd.krow = r, bd.kkhz = r == 0 && v >= 1000, bd.kneg = v < 0;
    if (v < 0) v = -v;
    if (bd.kkhz) v /= 1000;
    bd.kn = (int)pp_num(bd.ktext, v);
    bd.ktext[bd.kn] = 0;
    snprintf(range, sizeof range, "%s %s", TR("Range"),
             r == 0   ? "20 Hz \xe2\x80\x93 20 kHz"
             : r == 1 ? MINUS "24 \xe2\x80\x93 +24 dB"
                      : "0.1 \xe2\x80\x93 10");
    widget_set_text_utf8(bd.ktitle, r == 0 ? TR("Frequency") : r == 1 ? TR("Gain") : "Q");
    widget_set_text_utf8(bd.krange, range);
    bd_show(bd.kunitk, r == 0);
    widget_set_sensitive(bd.ksign, r == 1);
    peq_label_colors(bd.ksign, r == 1 ? "#FFFFFF" : "#5A5A5E");
    widget_set_text_utf8(bd.ksign, MINUS);
    bk_show_text();
    bd.kopen = 1;
    bd_show(bd.kscrim, 1);
    bd_show(bd.kcard, 1);
}

static int bd_on_up(void *ctx, void *e) {
    int x, y, r;
    (void)ctx;
    if (!e || !bd.win) return RET_OK;
    if (bd.drag >= 0) {
        bd_follow(e); /* the release position counts */
        bd_end();
        return RET_OK;
    }
    r = bd.down_row;
    bd.down_row = -1;
    if (r < 0) return RET_OK;
    bd_pt(bd.hsl, e, &x, &y);
    if (x - bd.down_x < -BD_TAP_PX || x - bd.down_x > BD_TAP_PX || y - bd.down_y < -BD_TAP_PX ||
        y - bd.down_y > BD_TAP_PX)
        return RET_OK;
    bd_type(r);
    return RET_OK;
}

static int bd_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bd.win) return RET_OK;
    bd.down_row = -1;
    bd_end();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The navbar's Previous / Next, the page
 */
static void bd_goto(int band) {
    if (bd.drag >= 0) bd_end();
    bd.band = band;
    bd_refresh();
}

static int bd_on_prev(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bd.win && bd.n > 0) bd_goto((bd.band + bd.n - 1) % bd.n);
    return RET_OK;
}

static int bd_on_next(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bd.win && bd.n > 0) bd_goto((bd.band + 1) % bd.n);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Leaving with edits not saved: the dialog
 */
static void bd_dialog(int on) {
    bd.dlg = on;
    bd_show(bd.dscrim, on);
    bd_show(bd.dcard, on);
}

/* The way out the user asked for. */
static void bd_leave(void) {
    int how = bd.leave;
    bd.leave = 0;
    if (how == 2)
        pod_open_now_playing();
    else
        navigator_back();
}

/* Back and Now Playing: out at once when nothing is unsaved, else the dialog (Back, Now Playing and a tap on the scrim are the only ways here; Previous / Next never ask). */
static void bd_ask(int how) {
    char name[PEQ_NAME];
    if (!bd.win || !bd.dcard || bd.dlg || !peqpage_edited()) {
        bd.leave = how;
        bd_leave();
        return;
    }
    if (bd.drag >= 0) bd_end();
    bd.leave = how;
    peqpage_name(name, sizeof name);
    widget_set_text_utf8(bd.dname, name);
    bd_dialog(1);
}

static int bd_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bd_ask(1);
    return RET_OK;
}

static int bd_on_player(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bd_ask(2);
    return RET_OK;
}

/* The dialog's buttons: 0 Save, 1 Save As New (the name entry; the page leaves when it comes back with the preset saved), 2 Don't Save, 3 Cancel (the scrim too). */
static int bd_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx;
    (void)e;
    if (!bd.win || !bd.dlg) return RET_OK;
    bd_dialog(0);
    if (k == 0) {
        if (peqpage_save())
            bd_leave();
        else
            bd.leave = 0;
    } else if (k == 1)
        peqpage_saveas();
    else if (k == 2) {
        if (peqpage_revert())
            bd_leave();
        else
            bd.leave = 0;
    } else
        bd.leave = 0;
    return RET_OK;
}

/* Back in front (the keyboard closed): the texts again; after Save As New the page leaves when the new file was written, else it stays. */
static int bd_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bd.win) return RET_OK;
    if (bd.drag >= 0) bd_end();
    bd_refresh();
    if (bd.leave && !peqpage_edited())
        bd_leave();
    else
        bd.leave = 0;
    return RET_OK;
}

static void bd_release(void) {
    if (bd.win && bd.drag >= 0) bd_slide(1);
    if (bd.segbg) bitmap_destroy(bd.segbg);
    if (bd.pill) bitmap_destroy(bd.pill);
    if (bd.card) bitmap_destroy(bd.card);
    if (bd.fill) bitmap_destroy(bd.fill);
    if (bd.thumb) bitmap_destroy(bd.thumb);
    if (bd.ring) bitmap_destroy(bd.ring);
    peq_graph_free(&bd.g);
    memset(&bd, 0, sizeof bd);
}

static int bd_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == bd.win) bd_release();
    return RET_OK;
}

int peqband_open(int band) {
    pend_band = band;
    return pod_open_peqband() == 0;
}

void peqband_opened(void *win) {
    peq_preset *p = peqpage_work();
    int k;
    char name[24];
    if (bd.win) { /* a band page exists already (it cannot: the Preset page opens one): the new one replaces it */
        void *old = bd.win;
        bd_release();
        if (widget_is_window_opened(old)) window_close(old);
    }
    memset(&bd, 0, sizeof bd);
    pod_bind(
        win, "btn_return", bd_on_back,
        (void
             *)0); /* (m1plus.c open_page leaves these two to this page; an asset that is not ours still gets its way out) */
    pod_bind(win, "btn_backtoplayer", bd_on_player, (void *)0);
    if (!p || pend_band < 0 || pend_band >= p->count) return;
    bd.graph = widget_lookup(win, "pod_graph", 1);
    bd.gtop = widget_lookup(win, "pod_gr_top", 1);
    bd.gbot = widget_lookup(win, "pod_gr_bot", 1);
    bd.seg = widget_lookup(win, "pod_seg", 1);
    bd.hsl = widget_lookup(win, "pod_hsl", 1);
    bd.sv = widget_lookup(win, "pod_scrollview", 1);
    bd.title = widget_lookup(win, "label_title", 1);
    for (k = 0; k < 3; ++k) {
        snprintf(name, sizeof name, "pod_seg_l%d", k);
        bd.seg_l[k] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "pod_hs_v%d", k);
        bd.hs_v[k] = widget_lookup(win, name, 1);
        if (!bd.seg_l[k] || !bd.hs_v[k]) goto bad;
    }
    bd.dscrim = widget_lookup(win, "pq_scrim", 1);
    bd.dcard = widget_lookup(win, "pq_card", 1);
    bd.dname = widget_lookup(win, "pq_name", 1);
    for (k = 0; k < 4; ++k) {
        snprintf(name, sizeof name, "pq_item%d", k);
        bd.ditem[k] = widget_lookup(win, name, 1);
        if (!bd.ditem[k]) goto bad;
    }
    if (!bd.dscrim || !bd.dcard || !bd.dname) goto bad;
    bd.kscrim = widget_lookup(win, "bk_scrim", 1);
    bd.kcard = widget_lookup(win, "bk_card", 1);
    bd.ktitle = widget_lookup(win, "bk_title", 1);
    bd.krange = widget_lookup(win, "bk_range", 1);
    bd.kval = widget_lookup(win, "bk_val", 1);
    bd.kunit = widget_lookup(win, "bk_unit", 1);
    bd.kcaret = widget_lookup(win, "bk_caret", 1);
    bd.kunitk = widget_lookup(win, "bk_unitk", 1);
    bd.ksign = widget_lookup(win, "bk_sign", 1);
    bd.kdot = widget_lookup(win, "bk_dot", 1);
    bd.kdel = widget_lookup(win, "bk_del", 1);
    bd.kcancel = widget_lookup(win, "bk_cancel", 1);
    bd.kdone = widget_lookup(win, "bk_done", 1);
    if (!bd.kscrim || !bd.kcard || !bd.ktitle || !bd.krange || !bd.kval || !bd.kunit || !bd.kcaret || !bd.kunitk ||
        !bd.ksign || !bd.kdot || !bd.kdel || !bd.kcancel || !bd.kdone)
        goto bad;
    for (k = 0; k < 10; ++k) {
        snprintf(name, sizeof name, "bk_k%d", k);
        bd.kk[k] = widget_lookup(win, name, 1);
        if (!bd.kk[k]) goto bad;
    }
    if (!bd.graph || !bd.gtop || !bd.gbot || !bd.seg || !bd.hsl || !bd.sv || !bd.title) goto bad;
    bd.band = pend_band, bd.n = p->count;
    bd.drag = bd.down_row = -1;
    bd.slide = 1;
    bd.segbg = tb_make(BD_SEG_W, BD_SEG_H, bd_seg_px);
    bd.pill = tb_make(BD_SEG_PILL_W, BD_SEG_PILL_H, bd_pill_px);
    bd.card = tb_make(BD_HSL_W, BD_HSL_H, bd_card_px);
    bd.fill = tb_make(BD_TRACK_W, BD_TRACK_H, bd_fill_px);
    bd.thumb = tb_make(BD_THUMB, BD_THUMB, bd_thumb_px);
    bd.ring = tb_make(BD_RING, BD_RING, bd_ring_px);
    bd.win = win;
    bd_refresh();
    widget_on(bd.graph, EVT_BEFORE_PAINT, bd_on_gpaint, (void *)0);
    widget_on(bd.seg, EVT_BEFORE_PAINT, bd_on_spaint, (void *)0);
    widget_on(bd.seg, EVT_POINTER_DOWN, bd_on_sdown, (void *)0);
    widget_on(bd.seg, EVT_POINTER_UP, bd_on_sup, (void *)0);
    widget_on(bd.seg, EVT_POINTER_ABORT, bd_on_sabort, (void *)0);
    widget_on(bd.hsl, EVT_BEFORE_PAINT, bd_on_hpaint, (void *)0);
    widget_on(bd.hsl, EVT_POINTER_DOWN, bd_on_down, (void *)0);
    widget_on(bd.hsl, EVT_POINTER_MOVE, bd_on_move, (void *)0);
    widget_on(bd.hsl, EVT_POINTER_UP, bd_on_up, (void *)0);
    widget_on(bd.hsl, EVT_POINTER_ABORT, bd_on_abort, (void *)0);
    for (k = 0; k < 4; ++k) widget_on(bd.ditem[k], EVT_CLICK, bd_on_item, (void *)(long)k);
    widget_on(bd.dscrim, EVT_CLICK, bd_on_item, (void *)3L);
    for (k = 0; k < 10; ++k) widget_on(bd.kk[k], EVT_CLICK, bd_on_kkey, (void *)(long)('0' + k));
    widget_on(bd.kdot, EVT_CLICK, bd_on_kkey, (void *)(long)'.');
    widget_on(bd.kdel, EVT_CLICK, bd_on_kdel, (void *)0);
    widget_on(bd.ksign, EVT_CLICK, bd_on_ksign, (void *)0);
    widget_on(bd.kunitk, EVT_CLICK, bd_on_kunit, (void *)0);
    widget_on(bd.kdone, EVT_CLICK, bd_on_kdone, (void *)0);
    widget_on(bd.kcancel, EVT_CLICK, bd_on_kcancel, (void *)0);
    widget_on(bd.kscrim, EVT_CLICK, bd_on_kcancel, (void *)0);
    pod_bind(win, "btn_bprev", bd_on_prev, (void *)0);
    pod_bind(win, "btn_bnext", bd_on_next, (void *)0);
    widget_on(win, EVT_WINDOW_TO_FG, bd_on_fg, (void *)0);
    widget_on(win, EVT_DESTROY, bd_on_destroy, win);
    return;
bad: /* an asset that is not ours */
    memset(&bd, 0, sizeof bd);
}
