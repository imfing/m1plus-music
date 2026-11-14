/* M1+ Music Tape: a landscape, fullscreen cassette Now Playing page.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/tape.md has the design. The page is ui/m1plus_tape.bin (tools/pod_ui.py build_tape_page): a fullscreen window (320 x 480, the stock status bar is not drawn) holding
 * one view tape_view (the whole window: the touch target, painted by this file in its own EVT_AFTER_PAINT) and a hidden label that only carries the font. Like the Pod
 * (patch/ipod.c) it has no hook, no widget per thing drawn, one page-scoped timer set in place with timer_modify, and nothing at boot.
 *
 *   picture   LANDSCAPE, 480 x 320, on the portrait panel: the picture is turned 90 degrees clockwise into a 320 x 480 RGBA frame this file owns, so landscape (x, y) is the frame's
 *             row x, column 319 - y (tp_pix), the map Cover Flow's landscape captions use (patch/coverflow.c). The frame starts as tape_shell with the grain and the knurl laid on (tp_finish; the cassette, no text), and only what
 *             changes is drawn into it: the tape packs and hub sprites (the timer), the printed marks (the timer) and the text (the paint, which has the canvas and so the font). The
 *             paint blits the frame 1:1; the timer invalidates only the rectangle that changed.
 *   text      the device font's glyph alpha (font_get_glyph) blended into the frame through the same map: AWTK's text drawing does not rotate, this does not need it (Cover Flow's
 *             landscape captions are the precedent, on the device). Each field restores its rectangle from the shell and clips the glyphs to it.
 *   reels     tape_top (the holes' rings, the window's scale and bevel) over a tape pack drawn per pixel (a distance table, integer) over the shell; tape_hubs: 12 frames. A pack
 *             is redrawn when its radius changes (position / length: the area of tape is conserved), a hub only when its frame (5 degrees) changes.
 *   touch     taps only, mapped back to landscape: a tap on the top left screw (50 x 50 px, drawn darker and turned while it is held) closes the page, a tap anywhere else plays /
 *             pauses. The page registers pointer DOWN, UP and ABORT only: no MOVE, no grab, so the window manager's own touch hook (the pull-down from the top edge) sees every
 *             drag as it does on any other page.
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "entries.h"
#include "scrobble.h"

#define FRAME_W 320 /* the frame is TP_H wide (columns) and TP_W tall (rows) */

enum { F_TITLE, F_ARTIST, F_ALBUM, F_TIMES, F_BIG, F_MODEL, F_STATUS, F_SPEC, F_BADGE, F_N };
enum {
    C_INK,
    C_SUB,
    C_BAND,
    C_PRINT,
    C_BADGE
}; /* a field's colour: the theme's title / artist ink, album / times / status ink, the band's ink (the big A), the print (the model name, the bias line), the sticker's ink (one for every theme) */

/* The themes, in the order of the saved value (tools/tape_art.py THEME_NAMES, THEMES; test/pod/tape.py draws every one from the python table and compares): the picture names
 * (tape_shell_<name>, tape_hubs_<name>, tape_marks_<name>), the colours as r | g << 8 | b << 16, the model name and the bias line printed on the label, the tape's own colour
 * (the pack's base and what its sheen adds, r g b: ferric brown, chrome's darker brown, metal's blue-black). */
#define TP_THEMES 3
static const char *const theme_name[TP_THEMES] = {"normal", "chrome", "metal"};
static const unsigned theme_rgb[TP_THEMES][5] = {{0x2a1f1bu, 0x62524au, 0xffffffu, 0xbe783cu, 0x081c2au},
                                                 {0x181412u, 0x483e3au, 0xffffffu, 0x3a3ac0u, 0x081c2au},
                                                 {0x5eb2d9u, 0x4888a8u, 0x5eb2d9u, 0x5eb2d9u, 0x081c2au}};
static const char *const theme_model[TP_THEMES] = {"TYPE I NORMAL", "TYPE II CHROME", "TYPE IV METAL"};
static const char *const theme_spec[TP_THEMES] = {
    "NORMAL BIAS \xc2\xb7 120\xc2\xb5s EQ", "HIGH BIAS \xc2\xb7 70\xc2\xb5s EQ", "METAL BIAS \xc2\xb7 70\xc2\xb5s EQ"};
static const unsigned char theme_pack[TP_THEMES][2][3] = {
    {{0x22, 0x15, 0x0e}, {0x6c - 0x22, 0x4f - 0x15, 0x38 - 0x0e}},
    {{0x1a, 0x14, 0x12}, {0x5a - 0x1a, 0x4c - 0x14, 0x46 - 0x12}},
    {{0x12, 0x12, 0x15}, {0x50 - 0x12, 0x50 - 0x12, 0x58 - 0x15}}};
static const char *const badge_text[3] = {"", "HI-RES", "DSD"}; /* tp.badge: none, a hi-res PCM stream, DSD */

struct field {
    short x, y; /* the pen's start, or the right end / middle by `anchor`; y is the line's vertical middle */
    unsigned char px, anchor, bold; /* font size; 'l', 'r', 'm' */
    unsigned short room; /* the width the text is cut to */
    short x0, y0, x1, y1; /* the rectangle the field restores and clips to (x1, y1 exclusive) */
    unsigned char rgb; /* C_* */
};

/* tools/tape_art.py TEXT; the numbers are checked by test/pod/tape.py */
static const struct field fields[F_N] = {
    [F_TITLE] = {47, 49, 22, 'l', 0, 388, 43, 37, 439, 62, C_INK},
    [F_ARTIST] = {47, 70, 16, 'l', 0, 262, 43, 62, 311, 83, C_INK},
    [F_ALBUM] = {47, 89, 13, 'l', 0, 190, 43, 83, 243, 99, C_SUB},
    [F_TIMES] = {435, 89, 12, 'r', 0, 100, 325, 83, 439, 99, C_SUB},
    [F_BIG] = {65, 146, 54, 'm', 1, 400, 39, 112, 97, 182, C_BAND},
    [F_MODEL] = {47, 206, 12, 'l', 0, 130, 41, 195, 175, 218, C_PRINT}, /* the fine print: type and grade */
    [F_STATUS] = {435, 206, 12, 'r', 0, 212, 219, 195, 441, 219, C_SUB},
    [F_SPEC] = {435, 70, 11, 'r', 0, 124, 311, 62, 439, 83,
                C_PRINT}, /* the tape's bias and equalisation, at the right end of the artist's line */
    [F_BADGE] = {58, 248, 11, 'm', 1, 44, TP_BADGE_X, TP_BADGE_Y, TP_BADGE_X + TP_BADGE_W, TP_BADGE_Y + TP_BADGE_H,
                 C_BADGE}, /* the sticker on the shell: tape_badge under the text */
};
#define STATUS_W 212

typedef struct {
    short x, y;
    unsigned short w, h, advance;
    unsigned char format, pitch;
    const unsigned char *data;
} tp_glyph;

static struct {
    void *win, *view, *st_font;
    int theme; /* the theme shown (0 .. 2): the saved one when the page opened, or the playing track's when that is TP_THEME_AUTO */
    int automatic; /* the saved theme was TP_THEME_AUTO: the theme follows the track */
    void *frame, *base, *top, *hubs, *marks, *screw,
        *sticker; /* RGBA8888 bitmaps in the frame's orientation (the images are made turned); sticker (tape_badge) may be missing: then no sticker is shown */
    unsigned short *lut; /* sqrt(d2h) * 8 for d2h < TP_LUT_N: a distance in 1/16 px */
    unsigned timer, ival;
    int fg;
    /* what the page shows now */
    unsigned key; /* the playing track (a hash), 0 none, ~0 not looked at yet */
    int playing, repeat, pos, len;
    char title[96], artist[64], album[64], fmt[24], times[24];
    /* the stream's quality (tp_quality): what the status line, the sticker and an automatic theme show */
    unsigned
        t_key; /* when the track changed (ms, never 0), 0 once the player's information is looked at again; until then the page holds the last track (tp.key is the last one's) */
    int q_rate, q_bits; /* the stream the quality was last worked out from (-1: the file name alone) */
    unsigned q_name; /* its codec name's hash */
    int q_br; /* and its bit rate (bit/s), compared only while the record is not known to be this track's */
    int o_rate, o_bits, o_br; /* the player's record as it was when the track changed */
    unsigned o_name;
    int unsure; /* the record read since the change is still that one: it may be the last track's */
    int r_pos,
        r_len; /* the record's position and length at its last look with a length, before a change of track: the last track's */
    unsigned
        p_hash; /* the shown track's file (a hash, set with its texts), 0 none: a change to the same file is not held */
    unsigned q_key; /* the track all of this is for (tp.key is forgotten by a full redraw, this is not) */
    int q_seen; /* 0 until the page's first look */
    int badge; /* 0 none, 1 HI-RES, 2 DSD */
    int tried; /* the theme whose pictures would not load (-1 none): not tried again for this track */
    int batt, charging, vol, hh, mm; /* batt -1: no bar */
    int rs, rt; /* the packs' radii, 1/16 px; -1: not drawn yet */
    unsigned ang[2]; /* the hubs' turn, 1/16 degree, 0 .. 959 (60 degrees: six teeth) */
    int hub[2]; /* the hub frame drawn */
    unsigned t_last;
    unsigned pending; /* fields to draw at the next paint */
    int dx0, dy0, dx1, dy1; /* the landscape rectangle changed since the last invalidate (empty: dx1 <= dx0) */
    /* the touch */
    int touch, pressed, sx, sy; /* a touch is down; the close screw is held; where it began (landscape) */
    int idle; /* opened by Now Playing's timer (tape_open_idle): a tap anywhere closes the page; cleared with the rest at destroy */
} tp __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Pixels: the frame's orientation
 */
static unsigned *tp_pix(unsigned *d, int pitch, int x, int y) { return d + x * pitch + (TP_H - 1 - y); }

/* A pixel moved by alpha a (of 256) towards white or black, channel by channel (tools/tape_art.py blend_to). */
static unsigned tp_blend(unsigned v, unsigned a, unsigned white) {
    unsigned o = v & 0xff000000u, k;
    for (k = 0; k < 24; k += 8) {
        unsigned c = v >> k & 255;
        o |= (white ? c + ((255 - c) * a >> 8) : c - (c * a >> 8)) << k;
    }
    return o;
}

/* The shell's grain and knurl, laid on bmp (the page's own copy of tape_shell, TP_H x TP_W) once when the page opens, by tape_tex: red the knurl's strength (128 is the cell's
 * own alpha), green the grain's amplitude (tools/tape_art.py finish, integer for integer). The grain is a hash of the pixel's place: light or dark by its top bit, alpha
 * |n - 128| * amplitude >> 7. The knurl is a 4 x 4 cell at the landscape place (row, 319 - column): the groove, the lit top and left edge, the shaded bottom and right edge, the
 * face. Both are texture no PNG packs: baked into the three shells they cost the rootfs about 600 KB. A tape_tex that will not load or has another size leaves the shell smooth. */
static void tp_finish(void *bmp) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    static const unsigned char kn[4][2] = {{78, 0}, {58, 1}, {64, 0}, {14, 1}}; /* alpha, towards white */
    unsigned bitmap[32], format, stride, *p = (unsigned *)0, x, y;
    const unsigned char *m = (const unsigned char *)0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(tp.win, "tape_tex", bitmap)) return;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    if (format < 4 && bitmap[0] == TP_H && bitmap[1] == TP_W)
        m = bitmap_lock_buffer_for_read(bitmap); /* read in place */
    p = m ? (unsigned *)bitmap_lock_buffer_for_write(bmp) : (unsigned *)0;
    if (p) {
        stride = bitmap_get_line_length(bitmap);
        for (y = 0; y < TP_W; ++y)
            for (x = 0; x < TP_H; ++x) {
                const unsigned char *t = m + y * stride + x * 4;
                unsigned g = t[at[format][0]], a = t[at[format][1]], i = y * TP_H + x, v, n, u, w;
                if (!(g | a)) continue;
                v = p[i];
                if (a) {
                    n = (i + 1) * 0x9E3779B1u, n ^= n >> 16, n *= 0x85EBCA6Bu, n = (n ^ n >> 13) >> 8 & 255;
                    v = tp_blend(v, (n >= 128 ? n - 128 : 128 - n) * a >> 7, n >= 128);
                }
                if (g) {
                    u = y & 3, w = ~x & 3;
                    n = u == 3 || w == 3 ? 0 : !u || !w ? 1 : u == 2 || w == 2 ? 2 : 3;
                    u = kn[n][0] * g >> 7;
                    v = tp_blend(v, u > 255 ? 255 : u, kn[n][1]);
                }
                p[i] = v;
            }
        bitmap_unlock_buffer(bmp);
    }
    if (m) bitmap_unlock_buffer(bitmap);
    widget_unload_image(tp.win, bitmap);
}

static void tp_free(void) {
    void **b[7] = {&tp.frame, &tp.base, &tp.top, &tp.hubs, &tp.marks, &tp.screw, &tp.sticker};
    int i;
    for (i = 0; i < 7; ++i)
        if (*b[i]) bitmap_destroy(*b[i]), *b[i] = (void *)0;
    if (tp.lut) free(tp.lut), tp.lut = (unsigned short *)0;
}

/* ---------------------------------------------------------------------------
 * Dirty rectangles (landscape) and the invalidate (frame coordinates: column 319 - y1 + 1, row x0)
 */
static void tp_dirty(int x0, int y0, int x1, int y1) {
    if (tp.dx1 <= tp.dx0)
        tp.dx0 = x0, tp.dy0 = y0, tp.dx1 = x1, tp.dy1 = y1;
    else {
        if (x0 < tp.dx0) tp.dx0 = x0;
        if (y0 < tp.dy0) tp.dy0 = y0;
        if (x1 > tp.dx1) tp.dx1 = x1;
        if (y1 > tp.dy1) tp.dy1 = y1;
    }
}

static void tp_flush(void) {
    int r[4];
    if (tp.dx1 <= tp.dx0 || !tp.view) return;
    r[0] = TP_H - tp.dy1, r[1] = tp.dx0, r[2] = tp.dy1 - tp.dy0, r[3] = tp.dx1 - tp.dx0;
    tp.dx0 = tp.dy0 = tp.dx1 = tp.dy1 = 0;
    widget_invalidate_force(tp.view, r);
}

/* ---------------------------------------------------------------------------
 * The reels: base, tape pack, tape_top, hub, per landscape pixel
 */
/* The tape pack: a smooth near-black brown #22150E with a static bow-tie sheen towards #6C4F38 (the light does not turn with the reel): |cos|^14 of the angle from the
 * upper left / lower right axis through the centre, the lower right lobe x 0.45; 2 px windings modulating both; a lighter ring just inside the edge and a dark edge.
 * tools/tape_art.py pack_rgb is the same arithmetic. */
static const unsigned char pk_wind[32] = {/* 32 + 32 sin(2 pi i / 32): the windings, one period per 2 px of distance */
                                          32, 38, 44, 50, 55, 59, 62, 63, 64, 63, 62, 59, 55, 50, 44, 38,
                                          32, 26, 20, 14, 9,  5,  2,  1,  0,  1,  2,  5,  9,  14, 20, 26};

/* The pack of radius R (1/16 px) at distance d (1/16 px) laid over `under`; (dx, dy) are the pixel's half pixels from the centre. */
static unsigned tp_pack(unsigned under, int d, int R, int dx, int dy) {
    const unsigned char *base = theme_pack[tp.theme][0], *rise = theme_pack[tp.theme][1];
    unsigned u, u2, d2, lobe, w, mb, k, e, c = 0xff000000u;
    int cov, s = -dx - dy, i;
    if (d < 0 || d > R + 8) return under;
    cov = R + 8 - d;
    if (cov > 16) cov = 16;
    d2 = (unsigned)(dx * dx + dy * dy);
    lobe = 0;
    if ((unsigned)(s * s) >=
        d2) { /* cos^2 >= 1/2; below it the lobe is under 513 of 65536 and adds nothing (same pixels as without this test) */
        u = ((unsigned)(s * s) << 15) / d2; /* cos^2 of the angle, 16 bits (65536: on the axis) */
        if (u > 65535u) u = 65535u;
        u2 = u * u >> 16;
        lobe = (u2 * u2 >> 16) * u2 >> 16; /* u^7 = cos^14 */
        lobe = lobe * u >> 16;
        if (s < 0) lobe = lobe * 115 >> 8;
    }
    w = pk_wind[d & 31];
    mb = 236 + (w * 13 >> 5);
    k = lobe * (179 + (w * 77 >> 6)) >> 8;
    e = d > R - 16 ? 115 : d > R - 35 ? 287 : 256;
    for (i = 0; i < 3; ++i) {
        unsigned v = ((base[i] * mb >> 8) + (rise[i] * k >> 16)) * e >> 8;
        c |= (v > 255 ? 255 : v) << 8 * i;
    }
    return cov >= 16 ? c : m1_mix(under, c, (unsigned)cov * 255 / 16);
}

static int tp_in_clear(int x, int y) {
    int qx = x < TP_CLEAR_X0 + TP_CLEAR_R       ? TP_CLEAR_X0 + TP_CLEAR_R
             : x > TP_CLEAR_X1 - 1 - TP_CLEAR_R ? TP_CLEAR_X1 - 1 - TP_CLEAR_R
                                                : x;
    int qy = y < TP_CLEAR_Y0 + TP_CLEAR_R       ? TP_CLEAR_Y0 + TP_CLEAR_R
             : y > TP_CLEAR_Y1 - 1 - TP_CLEAR_R ? TP_CLEAR_Y1 - 1 - TP_CLEAR_R
                                                : y;
    if (x < TP_CLEAR_X0 || x >= TP_CLEAR_X1 || y < TP_CLEAR_Y0 || y >= TP_CLEAR_Y1) return 0;
    return (x - qx) * (x - qx) + (y - qy) * (y - qy) <= TP_CLEAR_R * TP_CLEAR_R;
}

static int tp_dist(
    int x, int y, int cx, int *dx,
    int *
        dy) { /* the pixel's centre from the reel's centre: half pixels, and the distance in 1/16 px (-1: past the table) */
    unsigned d2;
    *dx = 2 * (x - cx) + 1, *dy = 2 * (y - TP_REEL_Y) + 1;
    d2 = (unsigned)(*dx * *dx + *dy * *dy);
    return d2 < TP_LUT_N ? tp.lut[d2] : -1;
}

/* The pixel at landscape (x, y) of the window area as it is now: the shell, the packs where the holes or the window show them, the overlay. */
static unsigned tp_reel_px(const unsigned *base, const unsigned *top, int x, int y) {
    unsigned c = *tp_pix((unsigned *)base, FRAME_W, x, y), a;
    int dx0, dy0, dx1, dy1, d0 = tp_dist(x, y, TP_REEL_X0, &dx0, &dy0), d1 = tp_dist(x, y, TP_REEL_X1, &dx1, &dy1),
                            clear = tp_in_clear(x, y);
    const unsigned *t;
    if (clear || (d0 >= 0 && d0 <= 16 * TP_HOLE_R)) c = tp_pack(c, d0, tp.rs, dx0, dy0);
    if (clear || (d1 >= 0 && d1 <= 16 * TP_HOLE_R)) c = tp_pack(c, d1, tp.rt, dx1, dy1);
    if (x >= TP_TOP_X && x < TP_TOP_X + TP_TOP_W && y >= TP_TOP_Y && y < TP_TOP_Y + TP_TOP_H) {
        t = top + (x - TP_TOP_X) * TP_TOP_H + (TP_TOP_H - 1 - (y - TP_TOP_Y));
        a = *t >> 24;
        if (a) c = m1_mix(c, *t, a);
    }
    return c;
}

/* A sprite of a sheet of cells `cell` px square, stacked, turned: cell i's landscape pixel (u, v). */
static unsigned tp_sprite(const unsigned *sheet, int cell, int i, int u, int v) {
    return sheet[(i * cell + u) * cell + (cell - 1 - v)];
}

/* The reels' pixels of the landscape rectangle (x0, y0, x1, y1) into the frame, and the hubs over them where they reach. */
static void tp_reel_rect(unsigned *f, int pitch, const unsigned *base, const unsigned *top, const unsigned *hubs,
                         int x0, int y0, int x1, int y1) {
    int x, y, k;
    for (x = x0; x < x1; ++x)
        for (y = y0; y < y1; ++y) *tp_pix(f, pitch, x, y) = tp_reel_px(base, top, x, y);
    for (k = 0; k < 2; ++k) {
        int hx = (k ? TP_REEL_X1 : TP_REEL_X0) - TP_HUB_PX / 2, hy = TP_REEL_Y - TP_HUB_PX / 2;
        for (x = hx > x0 ? hx : x0; x < hx + TP_HUB_PX && x < x1; ++x)
            for (y = hy > y0 ? hy : y0; y < hy + TP_HUB_PX && y < y1; ++y) {
                unsigned s = tp_sprite(hubs, TP_HUB_PX, tp.hub[k], x - hx, y - hy), a = s >> 24;
                if (a) *tp_pix(f, pitch, x, y) = m1_mix(*tp_pix(f, pitch, x, y), s, a);
            }
    }
}

/* Redraw the reel window area (all = 1: the whole of tape_top's rectangle) or just the two hub squares; marks the change dirty. */
static void tp_reels(int all) {
    unsigned *f, *base, *top, *hubs;
    int pitch = FRAME_W, k;
    f = (unsigned *)bitmap_lock_buffer_for_write(tp.frame);
    base = (unsigned *)bitmap_lock_buffer_for_read(tp.base);
    top = (unsigned *)bitmap_lock_buffer_for_read(tp.top);
    hubs = (unsigned *)bitmap_lock_buffer_for_read(tp.hubs);
    if (f && base && top && hubs) {
        if (all) {
            tp_reel_rect(f, pitch, base, top, hubs, TP_TOP_X, TP_TOP_Y, TP_TOP_X + TP_TOP_W, TP_TOP_Y + TP_TOP_H);
            tp_dirty(TP_TOP_X, TP_TOP_Y, TP_TOP_X + TP_TOP_W, TP_TOP_Y + TP_TOP_H);
        } else {
            for (k = 0; k < 2; ++k) {
                int hx = (k ? TP_REEL_X1 : TP_REEL_X0) - TP_HUB_PX / 2, hy = TP_REEL_Y - TP_HUB_PX / 2;
                tp_reel_rect(f, pitch, base, top, hubs, hx, hy, hx + TP_HUB_PX, hy + TP_HUB_PX);
                tp_dirty(hx, hy, hx + TP_HUB_PX, hy + TP_HUB_PX);
            }
        }
    }
    if (f) bitmap_unlock_buffer(tp.frame);
    if (base) bitmap_unlock_buffer(tp.base);
    if (top) bitmap_unlock_buffer(tp.top);
    if (hubs) bitmap_unlock_buffer(tp.hubs);
}

/* The printed play / pause mark, the repeat arrow and the close screw (pressed: its darker, turned sprite): the band restored under them, the sprite over it. */
static void tp_marks(unsigned which) { /* which: bit 0 the play / pause mark, 1 the repeat arrow, 2 the close screw */
    unsigned *f = (unsigned *)bitmap_lock_buffer_for_write(tp.frame);
    const unsigned *base = (const unsigned *)bitmap_lock_buffer_for_read(tp.base),
                   *m = (const unsigned *)bitmap_lock_buffer_for_read(tp.marks),
                   *sc = (const unsigned *)bitmap_lock_buffer_for_read(tp.screw);
    int i, u, v;
    if (f && base && m && sc) {
        for (i = 0; i < 3; ++i) {
            int mx = i == 2 ? TP_SCREW_X
                     : i    ? TP_REPEAT_X
                            : TP_PLAY_X,
                my = i == 2 ? TP_SCREW_Y
                     : i    ? TP_REPEAT_Y
                            : TP_PLAY_Y,
                cell = i            ? 2
                       : tp.playing ? 0
                                    : 1;
            if (!(which >> i & 1)) continue;
            for (u = 0; u < TP_MARK_PX; ++u)
                for (v = 0; v < TP_MARK_PX; ++v) {
                    unsigned *p = tp_pix(f, FRAME_W, mx + u, my + v),
                             s = (i == 1 && !tp.repeat) || (i == 2 && !tp.pressed)
                                     ? 0
                                     : (i == 2 ? tp_sprite(sc, TP_MARK_PX, 0, u, v)
                                               : tp_sprite(m, TP_MARK_PX, cell, u, v));
                    *p = *tp_pix((unsigned *)base, FRAME_W, mx + u, my + v);
                    if (s >> 24) *p = m1_mix(*p, s, s >> 24);
                }
            tp_dirty(mx, my, mx + TP_MARK_PX, my + TP_MARK_PX);
        }
    }
    if (f) bitmap_unlock_buffer(tp.frame);
    if (base) bitmap_unlock_buffer(tp.base);
    if (m) bitmap_unlock_buffer(tp.marks);
    if (sc) bitmap_unlock_buffer(tp.screw);
}

/* ---------------------------------------------------------------------------
 * Text: the font's glyph alpha, blended in turned (the paint has the canvas, so the font)
 */
static int tp_adv(void *font, unsigned size, unsigned ch) {
    tp_glyph g;
    return font_get_glyph(font, ch, size, &g) ? 4 : g.advance + 1;
}

static int tp_width(void *font, unsigned size, const unsigned *s, int len) {
    int i, w = 0;
    for (i = 0; i < len; ++i) w += tp_adv(font, size, s[i]);
    return w;
}

/* One field: its rectangle restored from the shell, then the text of the field at its place, cut with an ellipsis to its room, the glyphs clipped to the rectangle. */
static void tp_field(unsigned *f, const unsigned *base, void *font, int id, const char *utf8, unsigned px) {
    const struct field *fd = &fields[id];
    unsigned wide[64], n = 0, i;
    int x, y, w, ascent, pass;
    short vm[4];
    tp_glyph g;
    for (x = fd->x0; x < fd->x1; ++x)
        for (y = fd->y0; y < fd->y1; ++y) *tp_pix(f, FRAME_W, x, y) = *tp_pix((unsigned *)base, FRAME_W, x, y);
    tp_dirty(fd->x0, fd->y0, fd->x1, fd->y1);
    while (utf8[n] && n < 255) ++n;
    if (!n) return;
    if (id == F_BADGE) { /* the sticker under its text (the field's rectangle is the picture's) */
        const unsigned *s = (const unsigned *)bitmap_lock_buffer_for_read(tp.sticker);
        if (!s) return;
        for (x = 0; x < TP_BADGE_W; ++x)
            for (y = 0; y < TP_BADGE_H; ++y) {
                unsigned c = s[x * TP_BADGE_H + (TP_BADGE_H - 1 - y)], *p = tp_pix(f, FRAME_W, fd->x0 + x, fd->y0 + y);
                if (c >> 24) *p = m1_mix(*p, c, c >> 24);
            }
        bitmap_unlock_buffer(tp.sticker);
    }
    tk_utf8_to_utf16_ex(utf8, n, wide, 63);
    wide[63] = 0;
    for (n = 0; wide[n]; ++n) {
    }
    w = tp_width(font, px, wide, (int)n);
    if (w > fd->room) {
        int ell = tp_adv(font, px, ELLIPSIS), keep = 0;
        for (w = 0, i = 0; i < n && w + tp_adv(font, px, wide[i]) + ell <= fd->room; ++i)
            w += tp_adv(font, px, wide[i]);
        keep = (int)i;
        wide[keep] = ELLIPSIS, n = (unsigned)keep + 1, w += ell;
    }
    x = fd->anchor == 'r' ? fd->x - w : fd->anchor == 'm' ? fd->x - w / 2 : fd->x;
    y = fd->y - ((int)px + 1) / 2;
    font_get_vmetrics(vm, font, px);
    ascent = vm[0];
    for (pass = 0; pass <= fd->bold; ++pass) {
        int pen = x + pass;
        for (i = 0; i < n; pen += tp_adv(font, px, wide[i++])) {
            int r, c;
            if (font_get_glyph(font, wide[i], px, &g) || !g.data || g.format != GLYPH_FORMAT_ALPHA) continue;
            for (r = 0; r < g.h; ++r)
                for (c = 0; c < g.w; ++c) {
                    unsigned a = g.data[r * g.w + c];
                    int gx = pen + g.x + c, gy = y + g.y + ascent + r;
                    if (a && gx >= fd->x0 && gx < fd->x1 && gy >= fd->y0 && gy < fd->y1) {
                        unsigned *p = tp_pix(f, FRAME_W, gx, gy);
                        *p = m1_mix(*p, theme_rgb[tp.theme][fd->rgb], a);
                    }
                }
        }
    }
}

/* "VOL 42 | FLAC | 21:07 | 60%": 12 px if it fits STATUS_W, else 11; the clock goes first, then the format. */
static void tp_status(void *font, char *out, unsigned size, unsigned *px) {
    char batt[8], parts[3][24];
    unsigned wide[64], p, form, n;
    snprintf(batt, sizeof batt, "%s%d%%", tp.charging ? "+" : "", tp.batt < 0 ? 0 : tp.batt);
    snprintf(parts[0], sizeof parts[0], "VOL %d", tp.vol);
    snprintf(parts[1], sizeof parts[1], "%s", tp.fmt);
    snprintf(parts[2], sizeof parts[2], "%02d:%02d", tp.hh, tp.mm);
    for (p = 12;; p = 11)
        for (form = 0; form < 3; ++form) {
            if (tp.batt < 0)
                snprintf(out, size, "VOL %d", tp.vol);
            else if (form == 0)
                snprintf(out, size, "%s%s%s%s%s%s%s", parts[0], tp.fmt[0] ? " | " : "", tp.fmt, " | ", parts[2], " | ",
                         batt);
            else if (form == 1)
                snprintf(out, size, "%s%s%s | %s", parts[0], tp.fmt[0] ? " | " : "", tp.fmt, batt);
            else
                snprintf(out, size, "%s | %s", parts[0], batt);
            for (n = 0; out[n]; ++n) wide[n] = (unsigned char)out[n]; /* ASCII only */
            if (tp_width(font, p, wide, (int)n) <= STATUS_W || (p == 11 && form == 2)) {
                *px = p;
                return;
            }
        }
}

static int tp_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int src[4], i;
    (void)ctx;
    if (!canvas || !tp.win || !tp.frame) return RET_OK;
    if (tp.pending) {
        unsigned *f = (unsigned *)bitmap_lock_buffer_for_write(tp.frame);
        const unsigned *base = (const unsigned *)bitmap_lock_buffer_for_read(tp.base);
        void *font;
        widget_prepare_text_style(tp.st_font, canvas);
        font = *(void **)((char *)canvas + CANVAS_FONT);
        if (f && base && font) {
            char line[64];
            unsigned px;
            for (i = 0; i < F_N; ++i) {
                if (!(tp.pending >> i & 1)) continue;
                switch (i) {
                case F_TITLE:
                    tp_field(f, base, font, i, tp.title, fields[i].px);
                    break;
                case F_ARTIST:
                    tp_field(f, base, font, i, tp.artist, fields[i].px);
                    break;
                case F_ALBUM:
                    tp_field(f, base, font, i, tp.album, fields[i].px);
                    break;
                case F_TIMES:
                    tp_field(f, base, font, i, tp.times, fields[i].px);
                    break;
                case F_BIG:
                    tp_field(f, base, font, i, "A", fields[i].px);
                    break;
                case F_MODEL:
                    tp_field(f, base, font, i, theme_model[tp.theme], fields[i].px);
                    break;
                case F_SPEC:
                    tp_field(f, base, font, i, theme_spec[tp.theme], fields[i].px);
                    break;
                case F_BADGE:
                    tp_field(f, base, font, i, tp.sticker ? badge_text[tp.badge] : "", fields[i].px);
                    break;
                default:
                    tp_status(font, line, sizeof line, &px);
                    tp_field(f, base, font, i, line, px);
                }
            }
            tp.pending = 0;
            tp.dx0 = tp.dy0 = tp.dx1 = tp.dy1 = 0; /* the fields' rectangles were asked for by tp_update */
        }
        if (f) bitmap_unlock_buffer(tp.frame);
        if (base) bitmap_unlock_buffer(tp.base);
    }
    src[0] = 0, src[1] = 0, src[2] = TP_H, src[3] = TP_W;
    canvas_draw_image(canvas, tp.frame, src, src);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * What the page shows: the player, the status bar and the clock, looked at on the timer
 */
static int tp_battery(int *charging) {
    void *bar = *(void **)SYSTEM_BAR, *pg, *img;
    const char *name;
    *charging = 0;
    pg = bar ? widget_lookup(bar, "pgbar_battery", 1) : (void *)0;
    if (!pg) return -1;
    img = widget_lookup(bar, "img_battery", 1);
    name = img ? widget_get_prop_str(img, "image", "") : "";
    *charging = name && !strcmp(name, "bar_charge");
    return widget_get_prop_int(pg, "value", 0);
}

static int tp_volume(void) { /* the status bar's label_volume text, read only (never set) */
    void *bar = *(void **)SYSTEM_BAR, *lab = bar ? widget_lookup(bar, "label_volume", 1) : (void *)0;
    char buf[16];
    int v = 0, i;
    if (!lab) return 0;
    buf[0] = 0;
    m1_text_utf8(lab, buf, sizeof buf);
    for (i = 0; buf[i] >= '0' && buf[i] <= '9' && i < 4; ++i) v = v * 10 + buf[i] - '0';
    return v;
}

static void tp_copy(char *dst, unsigned size, const char *s) {
    unsigned n = 0;
    while (s[n] && n + 1 < size) dst[n] = s[n], ++n;
    while (n && ((unsigned char)s[n] & 0xc0) == 0x80 && s[n]) --n; /* a cut never leaves half a UTF-8 character */
    dst[n] = 0;
}

static void tp_format(
    char *out,
    const char *path) { /* the file extension, upper case, at most 4 characters: what the track's information gives */
    unsigned n = 0, dot = 0, i, k = 0;
    out[0] = 0;
    if (path[0] == 'h' && path[1] == 't' && path[2] == 't' && path[3] == 'p')
        return; /* a stream's address (Subsonic's stream.view) has no file format in it */
    while (path[n]) {
        if (path[n] == '.') dot = n + 1;
        if (path[n] == '/') dot = 0;
        ++n;
    }
    for (i = dot; dot && path[i] && k < 4; ++i)
        out[k++] = path[i] >= 'a' && path[i] <= 'z' ? (char)(path[i] - 32) : path[i];
    out[k] = 0;
}

/* The playing stream's quality: the status line's text ("FLAC 24/96", "MP3 320", "DSD64"; the file's extension alone when the player's information is not used), the tape an
 * automatic theme shows (lossy Normal, lossless Chrome, hi-res and DSD Metal) and the sticker (1 HI-RES, 2 DSD). `look` asks the player (mclGetInfo: a mutex and a copy);
 * without it, or while the player has no stream (no rate, no name), everything follows the extension. Lossless is by the codec's name as stock's get_hrflag spells it, or by
 * the extension; hi-res is get_hrflag's rule (over 48 kHz, or 24 bit from 44.1 kHz), DSD is 1 bit. rate / bits / name tell one stream from the next (-1, -1, 0: the extension). */
struct tp_q {
    int theme, badge, rate, bits, br, pos, len; /* pos, len: the record's position and length (0 without a record) */
    unsigned name;
    char fmt[24];
};

static int tp_lossless(const char *s) {
    static const char names[] = "FLAC\0ALAC\0WAV\0APE\0AIFF\0AIF\0DSD\0DSF\0DFF\0ISO\0WV\0";
    const char *n = names;
    while (*n) {
        if (!strcmp(n, s)) return 1;
        while (*n++) {
        }
    }
    return 0;
}

static void tp_quality(void *t, int look, struct tp_q *q) {
    int in[PLAYINFO_SIZE / 4], rate, bits, kbps, ok, dsd, lossless, hires;
    char ext[8], *codec = (char *)in + PLAYINFO_FMT;
    const char *name;
    memset(in, 0, sizeof in);
    if (t && look) mclGetInfo(in);
    q->pos = in[PLAYINFO_POS / 4], q->len = in[PLAYINFO_LEN / 4];
    codec[PLAYINFO_BITS - PLAYINFO_FMT - 1] = 0;
    rate = in[PLAYINFO_RATE / 4], bits = in[PLAYINFO_BITS / 4], kbps = in[PLAYINFO_BITRATE / 4] / 1000;
    ok = rate > 0 && codec[0];
    tp_format(ext, t ? cc_str(t, REC_PATH) : "");
    name = ext[0] ? ext : codec;
    dsd = ok ? bits == 1 : !strcmp(ext, "DSF") || !strcmp(ext, "DFF");
    lossless = dsd || tp_lossless(ext) || (ok && tp_lossless(codec));
    hires = ok && lossless && !dsd && (rate > 48000 || (bits >= 24 && rate >= 44100));
    q->theme = dsd || hires ? 2 : lossless;
    q->badge = dsd ? 2 : hires;
    q->rate = ok ? rate : -1, q->bits = ok ? bits : -1, q->name = ok ? cc_fnv(FNV_SEED, codec) : 0;
    q->br = ok ? in[PLAYINFO_BITRATE / 4] : 0;
    if (ok && dsd && rate >= 32 * 44100)
        snprintf(q->fmt, sizeof q->fmt, "DSD%d", (rate + 22050) / 44100);
    else if (ok && lossless && !dsd && rate % 1000 / 100)
        snprintf(q->fmt, sizeof q->fmt, "%s %d/%d.%d", name, bits, rate / 1000, rate % 1000 / 100);
    else if (ok && lossless && !dsd)
        snprintf(q->fmt, sizeof q->fmt, "%s %d/%d", name, bits, rate / 1000);
    else if (ok && !lossless && kbps > 0)
        snprintf(q->fmt, sizeof q->fmt, "%s %d", name, kbps);
    else
        snprintf(q->fmt, sizeof q->fmt, "%s", name);
}

/* The theme's three pictures (the shell with its grain and knurl, the hubs, the marks) in place of the ones shown, and the shell copied into the frame: 1, or 0 with nothing
 * changed (a picture missing or of another size, no memory). The page then draws everything again. */
static int tp_theme_load(int theme) {
    char name[32];
    void *b[3], **old[3] = {&tp.base, &tp.hubs, &tp.marks};
    unsigned *f = (unsigned *)0;
    const unsigned *s = (const unsigned *)0;
    int i;
    snprintf(name, sizeof name, "tape_shell_%s", theme_name[theme]);
    b[0] = m1_asset_rgba(tp.win, name, TP_H, TP_W, 0);
    snprintf(name, sizeof name, "tape_hubs_%s", theme_name[theme]);
    b[1] = m1_asset_rgba(tp.win, name, TP_HUB_PX, TP_HUB_PX * TP_SPRITES, 0);
    snprintf(name, sizeof name, "tape_marks_%s", theme_name[theme]);
    b[2] = m1_asset_rgba(tp.win, name, TP_MARK_PX, TP_MARK_PX * 3, 0);
    if (b[0] && b[1] && b[2] && tp.frame) {
        tp_finish(b[0]);
        f = (unsigned *)bitmap_lock_buffer_for_write(tp.frame);
        s = f ? (const unsigned *)bitmap_lock_buffer_for_read(b[0]) : s;
        if (s) memcpy(f, s, (unsigned)TP_H * TP_W * 4), bitmap_unlock_buffer(b[0]);
        if (f) bitmap_unlock_buffer(tp.frame);
    }
    for (i = 0; i < 3; ++i) {
        void *drop = s ? *old[i] : b[i];
        if (s) *old[i] = b[i];
        if (drop) bitmap_destroy(drop);
    }
    if (s) tp.theme = theme;
    return s != (const unsigned *)0;
}

/* The quality looked at again: the status line's format, the sticker and, with the automatic theme, the tape. After a change of track (tp.t_key) the page holds the last track
 * (tp_update shows its texts, time, format, sticker and tape) until the player's record is the new track's, and then all of the new track comes at once. The player is asked at
 * every look meanwhile. The record is the new track's when it has a stream (rate, name), a length, and that length is not the last track's (tp.r_len) or its position is below the
 * last track's (tp.r_pos): the player updates the whole record every 200 ms and a change of track zeroes the position and length first, so a record with no length is not yet
 * and one with the old length and a later position is the last track's arriving late. TP_INFO_MS is the fallback (equal lengths, a pause, a player that says nothing): the record
 * is taken as it is. A VBR file's bit rate is the one of the first look (the rate is not part of what tells streams apart); while the record is word for word the one read when
 * the track changed (tp.unsure) it may be the last track's, so the bit rate is compared too and the first record that differs is the track's (not needed once the length or
 * position has told). `hold`: the texts of the new track are not shown yet, so nothing changes until the record is ready. 1: the theme changed, everything is to be drawn again. */
static int tp_look(void *t, unsigned now, int hold) {
    struct tp_q q;
    int look = !tp.t_key;
    if (tp.t_key) {
        tp_quality(t, 1, &q);
        if (now - tp.t_key >= TP_INFO_MS)
            look = 1;
        else if (q.rate > 0 && q.len > 0 && (q.len != tp.r_len || q.pos < tp.r_pos))
            look = 1, tp.unsure = 0;
        if (look)
            tp.t_key = 0;
        else if (hold)
            return 0;
    } else
        tp_quality(t, 1, &q);
    if (look && q.len > 0) tp.r_pos = q.pos, tp.r_len = q.len;
    if (!look) tp_quality(t, 0, &q), q.rate = -3;
    if (q.rate == tp.q_rate && q.bits == tp.q_bits && q.name == tp.q_name && (!tp.unsure || q.br == tp.q_br)) return 0;
    if (look && (q.rate != tp.o_rate || q.bits != tp.o_bits || q.name != tp.o_name || q.br != tp.o_br)) tp.unsure = 0;
    tp.q_rate = q.rate, tp.q_bits = q.bits, tp.q_name = q.name, tp.q_br = q.br;
    if (strcmp(tp.fmt, q.fmt)) {
        snprintf(tp.fmt, sizeof tp.fmt, "%s", q.fmt);
        tp.pending |= 1u << F_STATUS;
    }
    if (!look) return 0;
    if (q.badge != tp.badge) tp.badge = q.badge, tp.pending |= 1u << F_BADGE;
    if (tp.automatic && t && q.theme != tp.theme && q.theme != tp.tried) {
        if (tp_theme_load(q.theme)) return 1;
        tp.tried = q.theme; /* no memory, a picture gone: the tape shown stays for this track */
    }
    return 0;
}

static unsigned tp_track_key(void *t) {
    unsigned h = cc_fnv(cc_fnv(cc_fnv(FNV_SEED, cc_str(t, REC_PATH)), cc_str(t, REC_TITLE)), cc_str(t, REC_NAME));
    return h | !h;
}

/* The packs' radii in 1/16 px at pos / len: r_supply^2 + r_takeup^2 = 66^2 + 16^2, the take-up's area growing in step. */
__attribute__((noinline)) void tp_radii(int pos, int len, int *rs, int *rt) {
    unsigned p = len > 0 ? (unsigned)pos * 65536u / (unsigned)len : 0, take2; /* pos <= len <= 65535: fits 32 bits */
    if (p > 65536u) p = 65536u;
    take2 =
        TP_PACK_MIN * TP_PACK_MIN * 256u + (unsigned)((TP_PACK_MAX * TP_PACK_MAX - TP_PACK_MIN * TP_PACK_MIN) * p >> 8);
    *rt = (int)m1_isqrt(take2);
    *rs = (int)m1_isqrt((TP_PACK_MAX * TP_PACK_MAX + TP_PACK_MIN * TP_PACK_MIN) * 256u - take2);
}

/* One look at everything: updates the state, draws what is not text into the frame, marks the text to redraw and what to invalidate. */
static void tp_update(int force) {
    void *t = cc_playing();
    int pos = 0, len = 0, charging, batt, vol, playing = mclGetPlayStatus() == 2, mode = mclGetPlayMode(),
        repeat = mode == MODE_REPEAT_ONE || mode == MODE_REPEAT_ALL;
    int rs, rt, k, all = 0, hubs = 0, marks = 0, i, held = 0;
    unsigned key = t ? tp_track_key(t) : 0, now = time_now_ms(), dt = now - tp.t_last;
    long secs = time((long *)0);
    const int *tm = secs > 1577836800L ? localtime(&secs) : (const int *)0;
    int hh = tm ? tm[2] : 0, mm = tm ? tm[1] : 0;
    if (force) tp.key = ~0u, tp.rs = -1;
    if (!tp.t_last || dt > 250)
        dt = tp.t_last ? 250 : 0; /* the first look turns nothing; a stalled loop never jumps the reels */
    tp.t_last = now | !now;
    if (!t || get_playtimeandlength(&pos, &len) != 1 || len <= 0) pos = len = 0;
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if (len > 65535) len = 65535, pos = pos > len ? len : pos;
    /* Another track than the one the quality is for (tp.q_key, not the track shown: a full redraw forgets tp.key and is no change, and a held track that is left for the one
     * shown again is a change, which ends its wait): the page's first look asks the player at once, a change waits (and holds the page, below), unless it is the same file as
     * the track shown (the next track of a CUE image, or the shown track itself come back: the same stream). Either way the record as it is now may be the last track's (the
     * page may open, or come back to the front, right after a change), so it is kept to tell this track's from. Its position and length are not taken here: the record may
     * already be the new track's, and the ones to compare with are the last track's (tp.r_pos, tp.r_len: tp_look keeps them while nothing is held). The file compared is the
     * one of the track shown (tp.p_hash), not of a track skipped while held. */
    if (key != tp.q_key || !tp.q_seen) {
        struct tp_q q;
        unsigned file = t ? cc_fnv(FNV_SEED, cc_str(t, REC_PATH)) | 1u : 0;
        tp.t_key = tp.q_seen && file && tp.p_hash && file != tp.p_hash ? now | !now : 0;
        tp.q_rate = -2, tp.tried = -1;
        tp_quality(t, 1, &q);
        tp.o_rate = q.rate, tp.o_bits = q.bits, tp.o_name = q.name, tp.o_br = q.br;
        tp.unsure = 1, tp.q_key = key, tp.q_seen = 1;
    }
    /* A change of track while a track plays is one event: the texts, the position, the format, the sticker and the tape stay as they were until the player's record is the new
     * track's, and all change in that update (tp_look). Not held: the first look, a full redraw, the same file, nothing playing. */
    k = tp_look(t, now, key != tp.key && t && !force);
    held = key != tp.key && t && !force && tp.t_key;
    if (key != tp.key && !held) {
        const char *s;
        tp.key = key;
        tp.p_hash = t ? cc_fnv(FNV_SEED, cc_str(t, REC_PATH)) | 1u : 0;
        s = t ? cc_str(t, REC_TITLE) : "";
        if (t && !*s) s = cc_str(t, REC_NAME);
        tp_copy(tp.title, sizeof tp.title, t ? s : TR("Not Playing"));
        tp_copy(tp.artist, sizeof tp.artist, t ? cc_str(t, REC_ARTIST) : "");
        tp_copy(tp.album, sizeof tp.album, t ? cc_str(t, REC_ALBUM) : "");
        tp.pending |= 1u << F_TITLE | 1u << F_ARTIST | 1u << F_ALBUM | 1u << F_STATUS;
        tp.pos = -1;
    } else if (held)
        pos = tp.pos, len = tp.len; /* the time and the packs stay too (the hubs go on turning) */
    if (k) { /* another tape: the frame is the new shell, everything on it is drawn again */
        force = 1, tp.rs = -1;
        tp_dirty(0, 0, TP_W, TP_H);
    }
    if (pos != tp.pos || len != tp.len) {
        tp.pos = pos, tp.len = len;
        snprintf(tp.times, sizeof tp.times, "%d:%02d  -%d:%02d", pos / 60, pos % 60, (len - pos) / 60,
                 (len - pos) % 60);
        tp.pending |= 1u << F_TIMES;
    }
    batt = tp_battery(&charging);
    vol = tp_volume();
    if (batt != tp.batt || charging != tp.charging || vol != tp.vol || hh != tp.hh || mm != tp.mm) {
        tp.batt = batt, tp.charging = charging, tp.vol = vol, tp.hh = hh, tp.mm = mm;
        tp.pending |= 1u << F_STATUS;
    }
    if (force) tp.pending = (1u << F_N) - 1, marks = 1;
    if (playing != tp.playing || repeat != tp.repeat) tp.playing = playing, tp.repeat = repeat, marks = 1;
    tp_radii(pos, len, &rs, &rt);
    if (tp.rs < 0 || rs - tp.rs >= 4 || tp.rs - rs >= 4 || rt - tp.rt >= 4 || tp.rt - rt >= 4)
        tp.rs = rs, tp.rt = rt, all = 1;
    if (playing)
        for (k = 0; k < 2; ++k) {
            unsigned r = (unsigned)(k ? tp.rt : tp.rs), step = dt * 1229u / (r ? r : 1),
                     a = tp.ang[k] + 1920u * 2 -
                         step % 1920u; /* 1920 sixteenths: the 120 degree cycle of the 3-spoke drive */
            tp.ang[k] = a % 1920u;
            if ((int)(tp.ang[k] / 80) != tp.hub[k]) tp.hub[k] = (int)(tp.ang[k] / 80), hubs = 1;
        }
    if (all || hubs) tp_reels(all);
    if (marks) tp_marks(7);
    for (i = 0; i < F_N; ++i) /* the text is drawn by the paint (it has the font); its rectangles are asked for now */
        if (tp.pending >> i & 1) tp_dirty(fields[i].x0, fields[i].y0, fields[i].x1, fields[i].y1);
    tp_flush();
}

/* ---------------------------------------------------------------------------
 * The timer, the window's events
 */
static unsigned tp_want_ms(void) {
    return !m1_screen_lit() ? POD_DARK_MS : tp.playing ? TP_PLAY_MS : TP_IDLE_MS;
} /* screen off: a slow check, no visual work (docs/modules/tape.md "Idle power") */

static void tp_retime(void) {
    unsigned want = tp_want_ms();
    if (tp.timer && want != tp.ival) {
        timer_modify(tp.timer, want);
        tp.ival = want;
    }
}

static int tp_tick(const void *timer) {
    (void)timer;
    if (!tp.win || !tp.fg) {
        tp.timer = 0;
        return RET_OK;
    }
    scrobble_note(cc_playing()); /* lit or dark (patch/scrobble.c) */
    if (m1_screen_lit())
        tp_update(
            0); /* dark: no reels, no text, no invalidation; the first lit tick looks at everything (dt is capped, the text compares with what it shows) */
    tp_retime();
    return RET_REPEAT;
}

static int tp_first(const void *timer) {
    (void)timer;
    tp.timer = 0;
    if (!tp.win || !tp.fg) return RET_OK;
    if (!m1_screen_lit()) { /* opened with the screen off: the first full draw waits for the light */
        tp.timer = timer_add(tp_first, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    tp_update(1);
    tp.ival = tp_want_ms();
    tp.timer = timer_add(tp_tick, (void *)0, tp.ival);
    return RET_OK;
}

static void tp_unarm(void) { m1_timer_stop(&tp.timer); }

static void tp_release(void) { /* the touch is over (or never was): the close screw is let go */
    int was = tp.pressed;
    tp.touch = tp.pressed = 0;
    if (was && tp.frame) tp_marks(4), tp_flush();
}

static int tp_on_background(void *ctx, void *e) {
    (void)e;
    if (!tp.win || ctx != tp.win) return RET_OK;
    tp.fg = 0;
    tp_unarm();
    tp_release();
    return RET_OK;
}

static int tp_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!tp.win || ctx != tp.win) return RET_OK;
    tp.fg = 1;
    if (!tp.timer) tp.timer = timer_add(tp_first, (void *)0, TP_FIRST_MS);
    return RET_OK;
}

static int tp_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != tp.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    tp_unarm();
    tp_free();
    memset(&tp, 0, sizeof tp);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch: frame coordinates (the view is the window) back to landscape (x, y) = (row, 319 - column)
 */
static void tp_local(void *e, int *x, int *y) {
    int pt[2];
    pt[0] = *(int *)((char *)e + PE_X), pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(tp.view, pt);
    *x = pt[1], *y = TP_H - 1 - pt[0];
}

static int tp_in_close(int x, int y) {
    return x >= TP_CLOSE_X0 && x < TP_CLOSE_X1 && y >= TP_CLOSE_Y0 && y < TP_CLOSE_Y1;
}

/* DOWN, UP and ABORT of the view; nothing else is bound and nothing is grabbed (a MOVE is never consumed here: the stock pull-down from the top edge reads the drag itself). */
static int tp_on_touch(void *ctx, void *e) {
    int type, x, y;
    (void)ctx;
    if (!e || !tp.win) return RET_OK;
    type = *(int *)e;
    if (type == EVT_POINTER_DOWN) {
        tp_release();
        tp_local(e, &x, &y);
        tp.touch = 1, tp.sx = x, tp.sy = y;
        if (tp_in_close(x, y)) tp.pressed = 1, tp_marks(4), tp_flush();
    } else if (type == EVT_POINTER_UP && tp.touch) {
        int dx, dy, close = tp.pressed;
        tp_local(e, &x, &y);
        dx = x - tp.sx, dy = y - tp.sy;
        tp_release();
        if (close) { /* began on the screw: ends on it, it closes; the finger left it, nothing */
            if (tp_in_close(x, y)) navigator_back();
        } else if ((dx < 0 ? -dx : dx) < TP_TAP_PX && (dy < 0 ? -dy : dy) < TP_TAP_PX) {
            if (tp.idle) {
                navigator_back();
                return RET_OK;
            }
            playpause_quick_click();
            tp_update(0);
            tp_retime();
        }
    } else if (type == EVT_POINTER_ABORT) {
        tp_release();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The saved theme (Settings > Now Playing > Theme): "1" Chrome, "2" Metal, "3" by the track's quality (TP_THEME_AUTO; each with an optional newline), anything else or no
 * file Normal; reading never writes.
 */
int tape_theme(void) {
    int c = set_read(TAPETHEME_FILE, 0);
    return c >= '0' && c <= '0' + TP_THEME_AUTO ? c - '0' : TP_THEME_AUTO;
}

/* Choose the theme (0 Normal, 1 Chrome, 2 Metal, 3 by the track), saved atomically; the theme, or -1 (an unknown theme, or one that could not be saved: the saved one is unchanged). */
int tape_theme_set(int theme) { return home_set_digit(TAPETHEME_FILE, TAPETHEME_TMP, theme, TP_THEME_AUTO); }

/* ---------------------------------------------------------------------------
 * Open: the More dialog's Cassette Mode row. 0 once the page is up (or already open); -1 when it could not open (nothing is left of it).
 */
int tape_open(void) {
    if (tp.win) return 0;
    memset(&tp, 0, sizeof tp);
    tp.win = window_open("m1plus_tape");
    if (!tp.win) {
        memset(&tp, 0, sizeof tp);
        return -1;
    }
    widget_on(tp.win, EVT_DESTROY, tp_on_destroy, tp.win);
    tp.view = widget_lookup(tp.win, "tape_view", 1);
    tp.st_font = widget_lookup(tp.win, "label_tp_font", 1);
    if (tp.view && tp.st_font) {
        unsigned d2;
        int theme = tape_theme(); /* read once: a change in Settings shows the next time the page opens */
        tp.automatic = theme == TP_THEME_AUTO;
        if (tp.automatic) { /* the playing track's tape at once (nothing playing: Normal), so the open loads one shell */
            struct tp_q q;
            void *t = cc_playing();
            tp_quality(t, 1, &q);
            theme = t ? q.theme : 0;
        }
        tp.frame = bitmap_create_ex(TP_H, TP_W, TP_H * 4, BITMAP_RGBA8888);
        tp.top = m1_asset_rgba(tp.win, "tape_top", TP_TOP_H, TP_TOP_W, 0);
        tp.screw = m1_asset_rgba(tp.win, "tape_screw", TP_MARK_PX, TP_MARK_PX, 0);
        tp.sticker = m1_asset_rgba(tp.win, "tape_badge", TP_BADGE_H, TP_BADGE_W,
                                   0); /* missing: the page opens without the sticker */
        tp.lut = (unsigned short *)calloc(TP_LUT_N, sizeof(unsigned short));
        if (tp.frame && tp.top && tp.screw && tp.lut && tp_theme_load(theme)) {
            for (d2 = 0; d2 < TP_LUT_N; ++d2) tp.lut[d2] = (unsigned short)m1_isqrt(d2 << 6);
            tp.ang[1] = 400, tp.hub[1] = 400 / 80; /* the reels do not start in step */
            tp.fg = 1;
            tp.rs = tp.rt = -1;
            tp.key = ~0u;
            widget_on(tp.win, EVT_WINDOW_TO_BG, tp_on_background, tp.win);
            widget_on(tp.win, EVT_WINDOW_TO_FG, tp_on_foreground, tp.win);
            widget_on(tp.view, EVT_POINTER_DOWN, tp_on_touch, (void *)0);
            widget_on(tp.view, EVT_POINTER_UP, tp_on_touch, (void *)0);
            widget_on(tp.view, EVT_POINTER_ABORT, tp_on_touch, (void *)0);
            widget_on(tp.view, EVT_AFTER_PAINT, tp_on_paint, (void *)0);
            tp.pending = (1u << F_N) - 1;
            tp.timer = timer_add(tp_first, (void *)0, TP_FIRST_MS);
            return 0;
        }
    }
    tp_free(); /* an asset that is not ours, or no memory: the window goes again */
    tp.win = (void *)0; /* (its destroy handler leaves a newer page alone) */
    navigator_back();
    memset(&tp, 0, sizeof tp);
    return -1;
}

/* Open for Now Playing's idle timer (patch/bigcover.c bc_timed_open): as tape_open, and a tap anywhere (the screw included) then closes the page, as stock's Album Cover page does, instead of
 * pausing. A page that is already open is left as it is, flag included. The flag lives in the page's state, which destroy clears. */
int tape_open_idle(void) {
    int was = tp.win != (void *)0, r = tape_open();
    if (!was && r == 0) tp.idle = 1;
    return r;
}
