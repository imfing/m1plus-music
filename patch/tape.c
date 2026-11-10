/* M1+ Music Tape: a landscape, fullscreen cassette Now Playing page.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/tape.md has the design. The page is ui/m1plus_tape.bin (tools/pod_ui.py build_tape_page): a fullscreen window (320 x 480, the stock status bar is not drawn) holding
 * one view tape_view (the whole window: the touch target, painted by this file in its own EVT_AFTER_PAINT) and a hidden label that only carries the font. Like the Pod
 * (patch/ipod.c) it has no hook, no widget per thing drawn, one page-scoped timer set in place with timer_modify, and nothing at boot.
 *
 *   picture   LANDSCAPE, 480 x 320, on the portrait panel: the picture is turned 90 degrees clockwise into a 320 x 480 RGBA frame this file owns, so landscape (x, y) is the frame's
 *             row x, column 319 - y (tp_pix), the map Cover Flow's landscape captions use (patch/coverflow.c). The frame starts as tape_shell (the cassette, no text), and only what
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

#define FRAME_W 320 /* the frame is TP_H wide (columns) and TP_W tall (rows) */

enum { F_TITLE, F_ARTIST, F_ALBUM, F_TIMES, F_BIG, F_MODEL, F_STATUS, F_N };
enum {
    C_INK,
    C_SUB,
    C_BAND,
    C_PRINT
}; /* a field's colour: the theme's title / artist ink, album / times / status ink, the band's ink (the big A), the print (the model name) */

/* The themes, in the order of the saved value (tools/tape_art.py THEME_NAMES, THEMES; test/pod/tape.py draws every one from the python table and compares): the picture names
 * (tape_shell_<name>, tape_hubs_<name>, tape_marks_<name>), the colours as r | g << 8 | b << 16, the model name printed on the label. */
#define TP_THEMES 3
static const char *const theme_name[TP_THEMES] = {"normal", "chrome", "metal"};
static const unsigned theme_rgb[TP_THEMES][4] = {{0x2a1f1bu, 0x62524au, 0xffffffu, 0xbe783cu},
                                                 {0x181412u, 0x483e3au, 0xffffffu, 0x3a3ac0u},
                                                 {0x5eb2d9u, 0x4888a8u, 0x5eb2d9u, 0x5eb2d9u}};
static const char *const theme_model[TP_THEMES] = {"TYPE I NORMAL", "TYPE II CHROME", "TYPE IV METAL"};

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
    [F_ARTIST] = {47, 70, 16, 'l', 0, 388, 43, 62, 439, 83, C_INK},
    [F_ALBUM] = {47, 89, 13, 'l', 0, 190, 43, 83, 243, 99, C_SUB},
    [F_TIMES] = {435, 89, 12, 'r', 0, 100, 325, 83, 439, 99, C_SUB},
    [F_BIG] = {65, 146, 54, 'm', 1, 400, 39, 112, 97, 182, C_BAND},
    [F_MODEL] = {47, 206, 12, 'l', 0, 130, 41, 195, 175, 218, C_PRINT}, /* the fine print: type and grade */
    [F_STATUS] = {435, 206, 12, 'r', 0, 212, 219, 195, 441, 219, C_SUB},
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
    int theme; /* the saved theme when the page opened */
    void *frame, *base, *top, *hubs, *marks,
        *screw; /* RGBA8888 bitmaps in the frame's orientation (the images are made turned) */
    unsigned short *lut; /* sqrt(d2h) * 8 for d2h < TP_LUT_N: a distance in 1/16 px */
    unsigned timer, ival;
    int fg;
    /* what the page shows now */
    unsigned key; /* the playing track (a hash), 0 none, ~0 not looked at yet */
    int playing, repeat, pos, len;
    char title[96], artist[64], album[64], fmt[8], times[24];
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

static unsigned tp_mix(unsigned v, unsigned c, unsigned a) { /* c over v by a (of 255), opaque result */
    unsigned w = a + (a >> 7);
    return 0xff000000u | (((v & 0xff00ffu) * (256 - w) + (c & 0xff00ffu) * w) >> 8 & 0xff00ffu) |
           (((v & 0xff00u) * (256 - w) + (c & 0xff00u) * w) >> 8 & 0xff00u);
}

__attribute__((noinline)) unsigned tp_isqrt(unsigned v) {
    unsigned r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= r + bit)
            v -= r + bit, r = (r >> 1) + bit;
        else
            r >>= 1;
        bit >>= 2;
    }
    return r;
}

/* A bitmap of ours from the asset `name`, w x h as the image is stored (turned), as RGBA8888 whatever order the decoder gave. NULL when it cannot be loaded or has another size. */
static void *tp_load(const char *name, unsigned w, unsigned h) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, x, y, ok = 0, *out;
    const unsigned char *data;
    unsigned stride;
    void *bmp;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(tp.win, name, bitmap)) return (void *)0;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    bmp = (void *)0;
    data =
        format < 4 && bitmap[0] == w && bitmap[1] == h ? bitmap_lock_buffer_for_read(bitmap) : (const unsigned char *)0;
    if (data) {
        stride = bitmap_get_line_length(bitmap);
        bmp = bitmap_create_ex(w, h, w * 4, BITMAP_RGBA8888);
        out = bmp ? (unsigned *)bitmap_lock_buffer_for_write(bmp) : (unsigned *)0;
        if (out) {
            for (y = 0; y < h; ++y) {
                const unsigned char *s = data + y * stride;
                for (x = 0; x < w; ++x, s += 4)
                    out[y * w + x] = (unsigned)s[at[format][0]] | (unsigned)s[at[format][1]] << 8 |
                                     (unsigned)s[at[format][2]] << 16 | (unsigned)s[at[format][3]] << 24;
            }
            ok = 1;
        }
        if (out) bitmap_unlock_buffer(bmp);
        bitmap_unlock_buffer(bitmap);
    }
    widget_unload_image(tp.win, bitmap);
    if (!ok && bmp) bitmap_destroy(bmp), bmp = (void *)0;
    return bmp;
}

static void tp_free(void) {
    void **b[6] = {&tp.frame, &tp.base, &tp.top, &tp.hubs, &tp.marks, &tp.screw};
    int i;
    for (i = 0; i < 6; ++i)
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
#define PK_BODY 0xff0e1624u /* near-black brown #24160E */
#define PK_EDGE 0xff05080cu
#define PK_WIND 0xff101928u /* the windings are 1/3 px lines in the mock: a third of the way to #2E1C12 */
#define PK_LIGHT 0xff304a6au /* the sheen: two soft lobes on the circle, upper left (the stronger) and lower right */
#define PK_LIGHT2 0xff1c2a3eu

/* The pack of radius R (1/16 px) at distance d (1/16 px) laid over `under`; the pixel at (dx, dy) half pixels from the centre decides the highlight's sector (upper left, 190 to 240 degrees). */
static unsigned tp_pack(unsigned under, int d, int R, int dx, int dy) {
    unsigned c;
    int cov;
    if (d < 0 || d > R + 8) return under;
    cov = R + 8 - d;
    if (cov > 16) cov = 16;
    if (d >= R - 16)
        c = PK_EDGE;
    else if (d >= R - 80 && d < R - 48 && -1008 * dy + 178 * dx >= 0 && -887 * dx + 512 * dy >= 0)
        c = PK_LIGHT;
    else if (d >= R - 80 && d < R - 48 && 1008 * dy - 178 * dx >= 0 && 887 * dx - 512 * dy >= 0)
        c = PK_LIGHT2;
    else if (d >= 16 * (TP_HUB_R + 2) && (d - 16 * (TP_HUB_R + 2)) % 48 < 16)
        c = PK_WIND;
    else
        c = PK_BODY;
    return cov >= 16 ? c : tp_mix(under, c, (unsigned)cov * 255 / 16);
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
        if (a) c = tp_mix(c, *t, a);
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
                if (a) *tp_pix(f, pitch, x, y) = tp_mix(*tp_pix(f, pitch, x, y), s, a);
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
                    if (s >> 24) *p = tp_mix(*p, s, s >> 24);
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
                        *p = tp_mix(*p, theme_rgb[tp.theme][fd->rgb], a);
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
    pod_text_utf8(lab, buf, sizeof buf);
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
    while (path[n]) {
        if (path[n] == '.') dot = n + 1;
        if (path[n] == '/') dot = 0;
        ++n;
    }
    for (i = dot; dot && path[i] && k < 4; ++i)
        out[k++] = path[i] >= 'a' && path[i] <= 'z' ? (char)(path[i] - 32) : path[i];
    out[k] = 0;
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
    *rt = (int)tp_isqrt(take2);
    *rs = (int)tp_isqrt((TP_PACK_MAX * TP_PACK_MAX + TP_PACK_MIN * TP_PACK_MIN) * 256u - take2);
}

/* One look at everything: updates the state, draws what is not text into the frame, marks the text to redraw and what to invalidate. */
static void tp_update(int force) {
    void *t = cc_playing();
    int pos = 0, len = 0, charging, batt, vol, playing = mclGetPlayStatus() == 2, mode = mclGetPlayMode(),
        repeat = mode == MODE_REPEAT_ONE || mode == MODE_REPEAT_ALL;
    int rs, rt, k, all = 0, hubs = 0, marks = 0, i;
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
    if (key != tp.key) {
        const char *s;
        tp.key = key;
        s = t ? cc_str(t, REC_TITLE) : "";
        if (t && !*s) s = cc_str(t, REC_NAME);
        tp_copy(tp.title, sizeof tp.title, t ? s : TR("Not Playing"));
        tp_copy(tp.artist, sizeof tp.artist, t ? cc_str(t, REC_ARTIST) : "");
        tp_copy(tp.album, sizeof tp.album, t ? cc_str(t, REC_ALBUM) : "");
        tp_format(tp.fmt, t ? cc_str(t, REC_PATH) : "");
        tp.pending |= 1u << F_TITLE | 1u << F_ARTIST | 1u << F_ALBUM | 1u << F_STATUS;
        tp.pos = -1;
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
    return !pod_screen_lit() ? POD_DARK_MS : tp.playing ? TP_PLAY_MS : TP_IDLE_MS;
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
    if (pod_screen_lit())
        tp_update(
            0); /* dark: no reels, no text, no invalidation; the first lit tick looks at everything (dt is capped, the text compares with what it shows) */
    tp_retime();
    return RET_REPEAT;
}

static int tp_first(const void *timer) {
    (void)timer;
    tp.timer = 0;
    if (!tp.win || !tp.fg) return RET_OK;
    if (!pod_screen_lit()) { /* opened with the screen off: the first full draw waits for the light */
        tp.timer = timer_add(tp_first, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    tp_update(1);
    tp.ival = tp_want_ms();
    tp.timer = timer_add(tp_tick, (void *)0, tp.ival);
    return RET_OK;
}

static void tp_unarm(void) {
    if (tp.timer) timer_remove(tp.timer);
    tp.timer = 0;
}

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
 * The saved theme (Settings > Now Playing > Theme): "1" Chrome, "2" Metal (an optional newline), anything else or no file Normal; reading never writes.
 */
int tape_theme(void) {
    int c = set_read(TAPETHEME_FILE, 0);
    return c == '1' || c == '2' ? c - '0' : 0;
}

/* Choose the theme (0 Normal, 1 Chrome, 2 Metal), saved atomically; the theme, or -1 (an unknown theme, or one that could not be saved: the saved one is unchanged). */
int tape_theme_set(int theme) {
    static const char *const text[TP_THEMES] = {"0\n", "1\n", "2\n"};
    if (theme < 0 || theme >= TP_THEMES) return -1;
    return home_write_atomic(TAPETHEME_FILE, TAPETHEME_TMP, text[theme]) == 0 ? theme : -1;
}

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
        unsigned *f, d2;
        char name[32];
        tp.theme = tape_theme(); /* read once: a change in Settings shows the next time the page opens */
        snprintf(name, sizeof name, "tape_shell_%s", theme_name[tp.theme]);
        tp.base = tp_load(name, TP_H, TP_W);
        snprintf(name, sizeof name, "tape_hubs_%s", theme_name[tp.theme]);
        tp.hubs = tp_load(name, TP_HUB_PX, TP_HUB_PX * TP_SPRITES);
        snprintf(name, sizeof name, "tape_marks_%s", theme_name[tp.theme]);
        tp.marks = tp_load(name, TP_MARK_PX, TP_MARK_PX * 3);
        tp.top = tp_load("tape_top", TP_TOP_H, TP_TOP_W);
        tp.screw = tp_load("tape_screw", TP_MARK_PX, TP_MARK_PX);
        tp.frame = bitmap_create_ex(TP_H, TP_W, TP_H * 4, BITMAP_RGBA8888);
        tp.lut = (unsigned short *)calloc(TP_LUT_N, sizeof(unsigned short));
        f = tp.frame && tp.base ? (unsigned *)bitmap_lock_buffer_for_write(tp.frame) : (unsigned *)0;
        if (f && tp.top && tp.hubs && tp.marks && tp.screw && tp.lut) {
            const unsigned *b = (const unsigned *)bitmap_lock_buffer_for_read(tp.base);
            if (b) {
                memcpy(f, b, (unsigned)TP_H * TP_W * 4);
                bitmap_unlock_buffer(tp.base);
            } else
                f = (unsigned *)0;
        }
        if (f) bitmap_unlock_buffer(tp.frame);
        if (f && tp.top && tp.hubs && tp.marks && tp.screw && tp.lut) {
            for (d2 = 0; d2 < TP_LUT_N; ++d2) tp.lut[d2] = (unsigned short)tp_isqrt(d2 << 6);
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
