/* M1+ Music Vinyl: a fullscreen turntable Now Playing page (portrait).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/vinyl.md has the design. The page is ui/m1plus_vinyl.bin (tools/pod_ui.py build_vinyl_page): a fullscreen window (320 x 480, the stock status bar is not drawn)
 * holding one view vinyl_view (the whole window: the touch target, painted by this file in its own EVT_AFTER_PAINT) and the text as ordinary labels over it (the title, its
 * twin one pixel right for weight, the artist, the times, the status line). Like the Tape page (patch/tape.c) it has no hook, no widget per thing drawn, one page-scoped
 * timer set in place with timer_modify, and nothing at boot.
 *
 *   picture   a 320 x 480 RGBA frame this file owns, composed from tools/vinyl_art.py's layers: vinyl_base (the plinth, the record with its static grooves and sheen,
 *             the keys at rest), the label (the playing track's cover reduced to 152 px, or vinyl_label) turned about the record's centre, vinyl_lid (the white rim, the
 *             spindle: they do not turn), the arm's shadow and the arm (one sprite each, turned about the pivot, bilinear, the arm premultiplied), vinyl_cap. Only what
 *             changed is composed again and invalidated: the label's square while it turns, the arm's old and new boxes when it moves, a key's cell.
 *   record    the label turns at 33 1/3 rpm while playing, speeding up and slowing down over VN_SPINUP_MS / VN_SPINDOWN_MS; paused it stands still.
 *   arm       on the groove while playing (the outer groove at the start of the track to the inner one at its end: vn_groove), parked straight down beside the record
 *             otherwise; a change of more than a degree (play, pause, a new track) swings it there over a few ticks.
 *   touch     taps only: the chevron closes, the keys play / pause and skip (the stock functions the Now Playing buttons call), a tap on the record plays / pauses. The
 *             page registers pointer DOWN, UP and ABORT only: no MOVE, no grab, so the window manager's own touch hook (the pull-down from the top edge) sees every drag.
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "covercache.h"

extern unsigned np_file_key(const char *path); /* patch/nowplaying.c: a hash of the picture file, 0 if unreadable */
extern const char *
np_cover_file(int *busy); /* the /tmp file of the playing track's cover, NULL for none; busy while demo makes it */

enum { K_NONE, K_CLOSE, K_PREV, K_PLAY, K_NEXT, K_RECORD };

/* tools/vinyl_art.py groove_table16: the arm's turn on the groove at p = i / VN_GROOVE_N of the track (test/pod/vinyl.py compares) */
static const short vn_groove[VN_GROOVE_N + 1] = {1671, 1680, 1688, 1697, 1706, 1715, 1724, 1733, 1741, 1750, 1759,
                                                 1768, 1776, 1785, 1794, 1803, 1812, 1820, 1829, 1838, 1846, 1855,
                                                 1864, 1873, 1881, 1890, 1899, 1908, 1916, 1925, 1934, 1943, 1952};
/* sin(i degrees) * 16384, i = 0 .. 90 */
static const short vn_sin_t[91] = {
    0,     286,   572,   857,   1143,  1428,  1713,  1997,  2280,  2563,  2845,  3126,  3406,  3686,  3964,  4240,
    4516,  4790,  5063,  5334,  5604,  5872,  6138,  6402,  6664,  6924,  7182,  7438,  7692,  7943,  8192,  8438,
    8682,  8923,  9162,  9397,  9630,  9860,  10087, 10311, 10531, 10749, 10963, 11174, 11381, 11585, 11786, 11982,
    12176, 12365, 12551, 12733, 12911, 13085, 13255, 13421, 13583, 13741, 13894, 14044, 14189, 14330, 14466, 14598,
    14726, 14849, 14968, 15082, 15191, 15296, 15396, 15491, 15582, 15668, 15749, 15826, 15897, 15964, 16026, 16083,
    16135, 16182, 16225, 16262, 16294, 16322, 16344, 16362, 16374, 16382, 16384};

static struct {
    void *win, *view, *title, *title2, *artist, *times, *status;
    void *frame, *base, *keys, *arm, *sh, *lid, *cap, *fall,
        *cover; /* RGBA8888 bitmaps: the frame, the layers, the fallback label, the decoded cover */
    unsigned timer, ival;
    int fg;
    unsigned key; /* the playing track (a hash), 0 none, ~0 not looked at yet */
    int playing, pos, len;
    char fmt[8];
    int vol, hh, mm;
    int theme; /* the plinth theme of this open (vinyl_theme): which pictures and which page asset */
    int rec; /* the record's colour of this open (vinyl_record), 0 Black */
    int retint, tinted; /* Cover: the cover may have changed; the base holds a tinted record */
    int rim_saved; /* vr.rim holds the installed base's rim pixels */
    unsigned char tst[5][3]; /* the tint's ramp stops it holds */
    int has_cover, settle; /* the label is the cover (else vinyl_label); /tmp looks left */
    unsigned fkey, cover_t; /* the /tmp file's hash when decoded; the next look at it */
    int spin; /* the label's speed, 0 .. 256 of 33 1/3 rpm */
    unsigned acc; /* the turn not yet drawn (ms x spin; 80 make 1/16 degree) */
    int ang, lc, ls; /* the label's turn and its cosine and sine */
    int arm_at, arm_to, ac, as, armed; /* the arm's turn drawn, its target, cosine and sine; armed: drawn once */
    int ab[4]; /* the box the arm (and its shadow) was drawn in */
    int sw_from, sw_to, sw_t, sw_len; /* a swing of the arm (vn_arm_next): from, to, ms gone, ms long (0: none) */
    int playkey; /* the play key shows 0 play, 1 pause; -1 not drawn */
    int pressed; /* the key drawn pressed, K_NONE */
    unsigned t_last;
    int dx0, dy0, dx1, dy1; /* the rectangle changed since the last invalidate (empty: dx1 <= dx0) */
    int touch, down, sx, sy; /* a touch is down; what it began on; where */
    int idle; /* opened by Now Playing's timer (vinyl_open_idle): a tap on the record closes the page; cleared with the rest at destroy */
} vn __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Fixed point
 */
static int vn_q(unsigned t) { /* sin of t (1/16 degree, 0 .. 1440) x 16384 */
    unsigned i = t >> 4;
    return i >= 90 ? vn_sin_t[90] : vn_sin_t[i] + (((vn_sin_t[i + 1] - vn_sin_t[i]) * (int)(t & 15)) >> 4);
}

__attribute__((noinline)) int vn_sin(int a) {
    unsigned t = (unsigned)(a % 5760 + 5760) % 5760;
    return t < 1440 ? vn_q(t) : t < 2880 ? vn_q(2880 - t) : t < 4320 ? -vn_q(t - 2880) : -vn_q(5760 - t);
}

static int vn_cos(int a) { return vn_sin(a + 1440); }

/* The arm's turn on the groove at pos / len (vn_groove, linear between its points). */
__attribute__((noinline)) int vn_groove_at(int pos, int len) {
    unsigned p = len > 0 ? (unsigned)pos * 65536u / (unsigned)len : 0, i, f; /* pos <= len <= 65535 */
    if (p > 65536u) p = 65536u;
    i = p >> 11, f = p & 2047;
    return i >= VN_GROOVE_N ? vn_groove[VN_GROOVE_N]
                            : vn_groove[i] + (((vn_groove[i + 1] - vn_groove[i]) * (int)f) >> 11);
}

#define VN_HOT \
    static inline \
        __attribute__((always_inline)) /* the per-pixel helpers: -Oz would call each (docs/modules/vinyl.md "Cost") */

VN_HOT unsigned vn_lerp(unsigned p, unsigned q, unsigned f) { /* p to q by f / 256, the four bytes */
    unsigned g = 256 - f;
    return (((p & 0xff00ffu) * g + (q & 0xff00ffu) * f) >> 8 & 0xff00ffu) |
           ((((p >> 8) & 0xff00ffu) * g + ((q >> 8) & 0xff00ffu) * f) & 0xff00ff00u);
}

VN_HOT unsigned vn_mix(unsigned v, unsigned c, unsigned a) { /* c over v by a (of 255), opaque result */
    unsigned w = a + (a >> 7);
    return 0xff000000u | (((v & 0xff00ffu) * (256 - w) + (c & 0xff00ffu) * w) >> 8 & 0xff00ffu) |
           (((v & 0xff00u) * (256 - w) + (c & 0xff00u) * w) >> 8 & 0xff00u);
}

VN_HOT unsigned vn_dim(unsigned v, unsigned a) { /* black over v by a */
    unsigned w = 256 - (a + (a >> 7));
    return 0xff000000u | ((v & 0xff00ffu) * w >> 8 & 0xff00ffu) | ((v & 0xff00u) * w >> 8 & 0xff00u);
}

VN_HOT unsigned
vn_over(unsigned v, unsigned p) { /* the premultiplied p over v (a channel never passes 255: p's are <= its alpha) */
    unsigned a = p >> 24, w = 256 - (a + (a >> 7));
    return 0xff000000u | (((v & 0xff00ffu) * w >> 8 & 0xff00ffu) + (p & 0xff00ffu)) |
           (((v & 0xff00u) * w >> 8 & 0xff00u) + (p & 0xff00u));
}

VN_HOT unsigned vn_tap(const unsigned *img, int w, int h, int x, int y) {
    return x >= 0 && y >= 0 && x < w && y < h ? img[y * w + x] : 0;
}

/* The sprite (VN_ARM_W x VN_ARM_H, its pivot VN_ARM_PX, VN_ARM_PY) at the screen pixel whose centre is (vx, vy) half pixels from the pivot, turned by (c, s),
 * given the sums px = c vx + s vy and py = c vy - s vx (vn_row steps them along a row): bilinear, 0 outside. */
VN_HOT unsigned vn_sprite(const unsigned *img, int px, int py) {
    int fx = (px >> 7) + VN_ARM_PX * 256 - 128, fy = (py >> 7) + VN_ARM_PY * 256 - 128, ix = fx >> 8, iy = fy >> 8;
    unsigned ax = (unsigned)fx & 255, ay = (unsigned)fy & 255;
    const unsigned *r;
    if (ix < -1 || iy < -1 || ix >= VN_ARM_W || iy >= VN_ARM_H) return 0;
    if (ix < 0 || iy < 0 || ix + 1 >= VN_ARM_W || iy + 1 >= VN_ARM_H) /* the edge: taps outside are 0 */
        return vn_lerp(
            vn_lerp(vn_tap(img, VN_ARM_W, VN_ARM_H, ix, iy), vn_tap(img, VN_ARM_W, VN_ARM_H, ix + 1, iy), ax),
            vn_lerp(vn_tap(img, VN_ARM_W, VN_ARM_H, ix, iy + 1), vn_tap(img, VN_ARM_W, VN_ARM_H, ix + 1, iy + 1), ax),
            ay);
    r = img + iy * VN_ARM_W + ix;
    if (!(r[0] | r[1] | r[VN_ARM_W] | r[VN_ARM_W + 1])) return 0; /* most of the sprite is clear */
    return vn_lerp(vn_lerp(r[0], r[1], ax), vn_lerp(r[VN_ARM_W], r[VN_ARM_W + 1], ax), ay);
}

/* The label at the pixel whose centre is (vx, vy) half pixels from the record's centre, turned by the label's angle, given px = lc vx + ls vy and
 * py = lc vy - ls vx: bilinear, clamped to the picture. */
VN_HOT unsigned vn_label(const unsigned *src, int px, int py) {
    int fx = (px >> 7) + VN_LAB_R * 256 - 128, fy = (py >> 7) + VN_LAB_R * 256 - 128, lim = (VN_LAB_PX - 2) * 256 + 255,
        ix, iy;
    unsigned ax, ay;
    const unsigned *r;
    fx = fx < 0 ? 0 : fx > lim ? lim : fx;
    fy = fy < 0 ? 0 : fy > lim ? lim : fy;
    ix = fx >> 8, iy = fy >> 8, ax = (unsigned)fx & 255, ay = (unsigned)fy & 255;
    r = src + iy * VN_LAB_PX + ix;
    return 0xff000000u | vn_lerp(vn_lerp(r[0], r[1], ax), vn_lerp(r[VN_LAB_PX], r[VN_LAB_PX + 1], ax), ay);
}

/* ---------------------------------------------------------------------------
 * Pictures
 */
/* A bitmap of ours from the asset `name`, w x h, as RGBA8888 whatever order the decoder gave (premultiplied when pm). NULL when it cannot be loaded or has another size. */
static void *vn_load(const char *name, unsigned w, unsigned h, int pm) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, x, y, ok = 0, *out, stride;
    const unsigned char *data;
    void *bmp = (void *)0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(vn.win, name, bitmap)) return bmp;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data =
        format < 4 && bitmap[0] == w && bitmap[1] == h ? bitmap_lock_buffer_for_read(bitmap) : (const unsigned char *)0;
    if (data) {
        stride = bitmap_get_line_length(bitmap);
        bmp = bitmap_create_ex(w, h, w * 4, BITMAP_RGBA8888);
        out = bmp ? (unsigned *)bitmap_lock_buffer_for_write(bmp) : (unsigned *)0;
        if (out) {
            for (y = 0; y < h; ++y) {
                const unsigned char *s = data + y * stride;
                for (x = 0; x < w; ++x, s += 4) {
                    unsigned r = s[at[format][0]], g = s[at[format][1]], b = s[at[format][2]], a = s[at[format][3]];
                    if (pm) r = (r * a + 127) / 255, g = (g * a + 127) / 255, b = (b * a + 127) / 255;
                    out[y * w + x] = r | g << 8 | b << 16 | a << 24;
                }
            }
            ok = 1;
            bitmap_unlock_buffer(bmp);
        }
        bitmap_unlock_buffer(bitmap);
    }
    widget_unload_image(vn.win, bitmap);
    if (!ok && bmp) bitmap_destroy(bmp), bmp = (void *)0;
    return bmp;
}

/* The pictures a plinth theme changes, in the order base, lid, arm, armsh, cap, keys (tools/vinyl_art.py tname: Graphite's keep their names), and the page asset of each theme. */
static const char *const vn_names[VN_THEMES][6] = {
    {"vinyl_base", "vinyl_lid", "vinyl_arm", "vinyl_armsh", "vinyl_cap", "vinyl_keys"},
    {"vinyl_base_white", "vinyl_lid_white", "vinyl_arm_white", "vinyl_armsh_white", "vinyl_cap_white",
     "vinyl_keys_white"}};
static const char *const vn_pages[VN_THEMES] = {"m1plus_vinyl", "m1plus_vinyl_white"};
/* The film grain of each theme: its amplitude and the picture of its weight (tools/vinyl_art.py GRAIN, GRAINED); Snow has none. */
static const unsigned char vn_grain_amp[VN_THEMES] = {VN_GRAIN, 0};
static const char *const vn_grain_name[VN_THEMES] = {"vinyl_grain", (const char *)0};

#define VN_D255(x) \
    (((x) + 128 + (((x) + 128) >> 8)) >> 8) /* x / 255 rounded, x in 0 .. 65535 (tools/vinyl_art.py d255) */

/* soft[n - (128 - 3 amp)][c]: a channel c soft-light blended with n (tools/vinyl_art.py soft_light), n in 128 +- 3 amp; made for amp at the first grain. */
static struct {
    unsigned amp;
    unsigned char soft[6 * VN_GRAIN + 1][256];
} vg __attribute__((section(".scratch")));

/* The theme's film grain on the rectangle (x0, y0) w x h of bmp (a VN_W x VN_H base of ours), once when it is loaded: each pixel soft-light blended with a hash of its
 * place by the weight vinyl_grain holds in red (tools/vinyl_art.py grain_apply, integer for integer). The grain is noise that no PNG packs: shipping it costs the rootfs
 * ~65 KB. Nothing when the theme has none or vinyl_grain will not load (the base stays clean). */
static void vn_grain(void *bmp, int x0, int y0, int w, int h) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned amp = vn_grain_amp[vn.theme], bitmap[32], format, stride, *p = (unsigned *)0, x, y, n0;
    const unsigned char *m = (const unsigned char *)0;
    if (!amp) return;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(vn.win, vn_grain_name[vn.theme], bitmap)) return;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    if (format < 4 && bitmap[0] == VN_W && bitmap[1] == VN_H)
        m = bitmap_lock_buffer_for_read(bitmap); /* read in place: the weight is R */
    p = m ? (unsigned *)bitmap_lock_buffer_for_write(bmp) : (unsigned *)0;
    if (p) {
        if (vg.amp != amp)
            for (vg.amp = amp, y = 0; y <= 6 * amp; ++y)
                for (x = 0, n0 = 128 - 3 * amp + y; x < 256; ++x)
                    vg.soft[y][x] = (unsigned char)(((255 - x) * x * n0 >> 16) +
                                                    VN_D255(x * (255 - VN_D255((255 - x) * (255 - n0)))));
        stride = bitmap_get_line_length(bitmap);
        for (y = (unsigned)y0; y < (unsigned)(y0 + h); ++y)
            for (x = (unsigned)x0; x < (unsigned)(x0 + w); ++x) {
                unsigned i = y * VN_W + x, wt = m[y * stride + x * 4 + at[format][0]], v = p[i], hs, n, k, o;
                if (!wt) continue;
                hs = (i + 1) * 0x9E3779B1u, hs ^= hs >> 16, hs *= 0x85EBCA6Bu, hs ^= hs >> 13;
                n = VN_D255(((hs & 255) + (hs >> 8 & 255) + (hs >> 16 & 255)) * 2 *
                            amp); /* the value less 128 - 3 amp */
                for (o = v & 0xff000000u, k = 0; k < 24; k += 8) {
                    unsigned c = v >> k & 255;
                    o |= VN_D255(c * (255 - wt) + vg.soft[n][c] * wt) << k;
                }
                p[i] = o;
            }
        bitmap_unlock_buffer(bmp);
    }
    if (m) bitmap_unlock_buffer(bitmap);
    widget_unload_image(vn.win, bitmap);
}

static void vn_free(void) {
    void **b[9] = {&vn.frame, &vn.base, &vn.keys, &vn.arm, &vn.sh, &vn.lid, &vn.cap, &vn.fall, &vn.cover};
    int i;
    for (i = 0; i < 9; ++i)
        if (*b[i]) bitmap_destroy(*b[i]), *b[i] = (void *)0;
}

/* ---------------------------------------------------------------------------
 * Composing: what changed is drawn again into the frame and its rectangle marked to invalidate
 */
static void vn_dirty(int x0, int y0, int x1, int y1) {
    if (vn.dx1 <= vn.dx0)
        vn.dx0 = x0, vn.dy0 = y0, vn.dx1 = x1, vn.dy1 = y1;
    else {
        if (x0 < vn.dx0) vn.dx0 = x0;
        if (y0 < vn.dy0) vn.dy0 = y0;
        if (x1 > vn.dx1) vn.dx1 = x1;
        if (y1 > vn.dy1) vn.dy1 = y1;
    }
}

static void vn_flush(void) {
    int r[4];
    if (vn.dx1 <= vn.dx0 || !vn.view) return;
    r[0] = vn.dx0, r[1] = vn.dy0, r[2] = vn.dx1 - vn.dx0, r[3] = vn.dy1 - vn.dy0;
    vn.dx0 = vn.dy0 = vn.dx1 = vn.dy1 = 0;
    widget_invalidate_force(vn.view, r);
}

/* The layers a compose reads and the frame it writes, locked once for a whole look (vn_lock .. vn_unlock). */
static struct {
    unsigned *f, *base, *lab, *lid, *arm, *sh, *cap;
    void *labmap;
} vl __attribute__((section(".scratch")));

static int vn_lock(void) {
    vl.labmap = vn.has_cover ? vn.cover : vn.fall;
    vl.f = (unsigned *)bitmap_lock_buffer_for_write(vn.frame);
    vl.base = (unsigned *)bitmap_lock_buffer_for_read(vn.base);
    vl.lab = (unsigned *)bitmap_lock_buffer_for_read(vl.labmap);
    vl.lid = (unsigned *)bitmap_lock_buffer_for_read(vn.lid);
    vl.arm = (unsigned *)bitmap_lock_buffer_for_read(vn.arm);
    vl.sh = (unsigned *)bitmap_lock_buffer_for_read(vn.sh);
    vl.cap = (unsigned *)bitmap_lock_buffer_for_read(vn.cap);
    return vl.f && vl.base && vl.lab && vl.lid && vl.arm && vl.sh && vl.cap;
}

static void vn_unlock(void) {
    if (vl.f) bitmap_unlock_buffer(vn.frame);
    if (vl.base) bitmap_unlock_buffer(vn.base);
    if (vl.lab) bitmap_unlock_buffer(vl.labmap);
    if (vl.lid) bitmap_unlock_buffer(vn.lid);
    if (vl.arm) bitmap_unlock_buffer(vn.arm);
    if (vl.sh) bitmap_unlock_buffer(vn.sh);
    if (vl.cap) bitmap_unlock_buffer(vn.cap);
    memset(&vl, 0, sizeof vl);
}

/* The rectangle (x0, y0) .. (x1, y1) of the frame above the key band: the base, the label inside VN_LAB_IN, the lid, the arm's shadow and the arm, the cap.
 * The layers are locked (vn_lock). */
static void vn_row(int y, int x0, int x1);
static int vn_isqrt(int n);
static int vn_retint(void);
void vn_cols(int c, int s, int ox, int oy, int y, int *x0, int *x1);

static void vn_compose(int x0, int y0, int x1, int y1) {
    int y;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > VN_W) x1 = VN_W;
    if (y1 > VN_BAND_Y0) y1 = VN_BAND_Y0;
    if (x1 <= x0 || y1 <= y0) return;
    for (y = y0; y < y1; ++y) vn_row(y, x0, x1);
    vn_dirty(x0, y0, x1, y1);
}

/* Row y, columns x0 .. x1 (inside the frame above the band). The samplers' sums (lc vx + ls vy and the like) step by a constant along the row, so a pixel
 * costs no multiply; each is the sum vn_label / vn_sprite are defined on, exactly. */
/* Row y, columns x0 .. x1 (inside the frame above the band), in passes, one a layer, each over its own columns only (base; the label inside its circle; the
 * lid; the arm and its shadow where they can touch, vn_cols; the cap), so each loop holds only its own sums and a pixel the arm cannot touch costs no sampling.
 * The samplers' sums (lc vx + ls vy and the like) step by a constant along the row: no multiply a pixel, and each is the sum vn_label / vn_sprite are defined
 * on, exactly. The same layering, pixel for pixel, as one pass would give. */
static void vn_row(int y, int x0, int x1) {
    const unsigned *b = vl.base + y * VN_W;
    unsigned *f = vl.f + y * VN_W, l;
    int x, a, e, vy;
    for (x = x0; x < x1; ++x) f[x] = b[x] | 0xff000000u;
    vy = 2 * (y - VN_REC_Y) + 1, e = 4 * VN_LAB_IN * VN_LAB_IN - vy * vy;
    if (e >= 0) { /* the label: |2 (x - VN_REC_X) + 1| <= h */
        int h = vn_isqrt(e), vx, lx, ly, dlx = 2 * vn.lc, dly = -2 * vn.ls;
        a = VN_REC_X - ((h + 1) >> 1), e = VN_REC_X + ((h - 1) >> 1) + 1;
        if (a < x0) a = x0;
        if (e > x1) e = x1;
        vx = 2 * (a - VN_REC_X) + 1, lx = vn.lc * vx + vn.ls * vy, ly = vn.lc * vy - vn.ls * vx;
        for (x = a; x < e; ++x, lx += dlx, ly += dly) f[x] = vn_label(vl.lab, lx, ly);
    }
    if (y >= VN_LID_Y && y < VN_LID_Y + VN_LID_PX) {
        const unsigned *lid = vl.lid + (y - VN_LID_Y) * VN_LID_PX - VN_LID_X;
        a = x0 < VN_LID_X ? VN_LID_X : x0, e = x1 > VN_LID_X + VN_LID_PX ? VN_LID_X + VN_LID_PX : x1;
        for (x = a; x < e; ++x)
            if ((l = lid[x]) >> 24) f[x] = vn_mix(f[x], l, l >> 24);
    }
    if (vn.armed && y >= vn.ab[1] && y < vn.ab[3]) {
        int px, py, sx, sy, dx = 2 * vn.ac, dy = -2 * vn.as, pvx, pvy = 2 * (y - VN_PIV_Y) + 1,
                            svy = pvy - 2 * VN_SH_DY;
        a = VN_W, e = 0;
        vn_cols(vn.ac, vn.as, 0, 0, y, &a, &e);
        vn_cols(vn.ac, vn.as, VN_SH_DX, VN_SH_DY, y, &a, &e);
        if (a < x0) a = x0;
        if (a < vn.ab[0]) a = vn.ab[0];
        if (e > x1) e = x1;
        if (e > vn.ab[2]) e = vn.ab[2];
        pvx = 2 * (a - VN_PIV_X) + 1;
        px = vn.ac * pvx + vn.as * pvy, py = vn.ac * pvy - vn.as * pvx;
        sx = vn.ac * (pvx - 2 * VN_SH_DX) + vn.as * svy, sy = vn.ac * svy - vn.as * (pvx - 2 * VN_SH_DX);
        for (x = a; x < e; ++x, px += dx, py += dy, sx += dx, sy += dy) {
            unsigned s = vn_sprite(vl.sh, sx, sy) >> 24, p = vn_sprite(vl.arm, px, py), c = f[x];
            if (s) c = vn_dim(c, s);
            if (p >> 24) c = vn_over(c, p);
            f[x] = c;
        }
    }
    if (y >= VN_CAP_Y && y < VN_CAP_Y + VN_CAP_PX) {
        const unsigned *cap = vl.cap + (y - VN_CAP_Y) * VN_CAP_PX - VN_CAP_X;
        a = x0 < VN_CAP_X ? VN_CAP_X : x0, e = x1 > VN_CAP_X + VN_CAP_PX ? VN_CAP_X + VN_CAP_PX : x1;
        for (x = a; x < e; ++x)
            if ((l = cap[x]) >> 24) f[x] = vn_mix(f[x], l, l >> 24);
    }
}

static int vn_isqrt(int n) { /* floor(sqrt(n)), n >= 0 */
    int r = 0, bit = 1 << 20;
    while (bit > n) bit >>= 2;
    for (; bit; bit >>= 2)
        if (n >= r + bit)
            n -= r + bit, r = (r >> 1) + bit;
        else
            r >>= 1;
    return r;
}

/* The label turned: only the rows' spans inside its circle change (the square's corners do not), each a pixel wide each side; the square is invalidated. */
static void vn_label_draw(void) {
    int y;
    vn.lc = vn_cos(vn.ang), vn.ls = vn_sin(vn.ang);
    for (y = VN_REC_Y - VN_LAB_IN; y <= VN_REC_Y + VN_LAB_IN; ++y) {
        int vy = 2 * (y - VN_REC_Y) + 1, r2 = 4 * VN_LAB_IN * VN_LAB_IN - vy * vy, h;
        if (r2 < 0) continue;
        h = (vn_isqrt(r2) + 1) / 2 + 1; /* |2 (x - VN_REC_X) + 1| <= sqrt(r2) inside this */
        if (y >= 0 && y < VN_BAND_Y0) vn_row(y, VN_REC_X - h < 0 ? 0 : VN_REC_X - h, VN_REC_X + h);
    }
    vn_dirty(VN_REC_X - VN_LAB_IN < 0 ? 0 : VN_REC_X - VN_LAB_IN, VN_REC_Y - VN_LAB_IN, VN_REC_X + VN_LAB_IN + 1,
             VN_REC_Y + VN_LAB_IN + 1);
}

/* The box the arm turned by a covers with its shadow (x1, y1 exclusive), clipped to the frame above the band. */
__attribute__((noinline)) void vn_arm_box(int a, int *b) {
    static const short u[4][2] = {{-VN_ARM_PX, -VN_ARM_PY},
                                  {VN_ARM_W - VN_ARM_PX, -VN_ARM_PY},
                                  {-VN_ARM_PX, VN_ARM_H - VN_ARM_PY},
                                  {VN_ARM_W - VN_ARM_PX, VN_ARM_H - VN_ARM_PY}};
    int c = vn_cos(a), s = vn_sin(a), i, x0 = VN_W, y0 = VN_H, x1 = -VN_W, y1 = -VN_H;
    for (i = 0; i < 4; ++i) {
        int x = VN_PIV_X + ((c * u[i][0] - s * u[i][1]) >> 14), y = VN_PIV_Y + ((s * u[i][0] + c * u[i][1]) >> 14);
        if (x < x0) x0 = x;
        if (y < y0) y0 = y;
        if (x > x1) x1 = x;
        if (y > y1) y1 = y;
    }
    b[0] = x0 - 2 < 0 ? 0 : x0 - 2, b[1] = y0 - 2 < 0 ? 0 : y0 - 2;
    b[2] = x1 + 3 + VN_SH_DX > VN_W ? VN_W : x1 + 3 + VN_SH_DX;
    b[3] = y1 + 3 + VN_SH_DY > VN_BAND_Y0 ? VN_BAND_Y0 : y1 + 3 + VN_SH_DY;
}

/* a <= p v + q < b narrows [*lo, *hi] (v, inclusive), one step wide each side for the rounding */
static void vn_range(int p, int q, int a, int b, int *lo, int *hi) {
    int u, w;
    if (!p) {
        if (q < a || q >= b) *lo = 1, *hi = 0;
        return;
    }
    u = (a - q) / p, w = (b - q) / p;
    if (u > w) {
        int t = u;
        u = w, w = t;
    }
    if (u - 1 > *lo) *lo = u - 1;
    if (w + 1 < *hi) *hi = w + 1;
}

/* The columns [x0, x1) of row y the sprite turned by (c, s) can touch with its pivot moved by (ox, oy) (vn_sprite's bounds, a pixel wide each side), widening
 * [*x0, *x1); a row it misses leaves them alone. */
__attribute__((noinline)) void vn_cols(int c, int s, int ox, int oy, int y, int *x0, int *x1) {
    int vy = 2 * (y - oy - VN_PIV_Y) + 1, lo = -4 * VN_W, hi = 4 * VN_W, a, b;
    /* vn_sprite: 128 fx = c vx + s vy + 128 (VN_ARM_PX 256 - 128) in [-256 128, VN_ARM_W 256 128); 128 fy = c vy - s vx + 128 (VN_ARM_PY 256 - 128) likewise */
    vn_range(c, s * vy + 128 * (VN_ARM_PX * 256 - 128), -256 * 128, VN_ARM_W * 256 * 128, &lo, &hi);
    vn_range(-s, c * vy + 128 * (VN_ARM_PY * 256 - 128), -256 * 128, VN_ARM_H * 256 * 128, &lo, &hi);
    if (lo > hi) return;
    a = ((lo - 1) >> 1) + ox + VN_PIV_X - 1,
    b = ((hi - 1) >> 1) + ox + VN_PIV_X + 2; /* vx = 2 (x - ox - VN_PIV_X) + 1 */
    if (a < *x0) *x0 = a;
    if (b > *x1) *x1 = b;
}

/* The arm at turn a: the rows of its old box and its new one, each composed once over the columns the old or the new arm or their shadows touch (not the
 * boxes' empty corners: a turned arm fills little of its box). The layers are locked. */
static void vn_arm_draw(int a) {
    int oc = vn.ac, os = vn.as, had = vn.armed, y0, y1, xa, xb, y;
    int nb[4];
    vn_arm_box(a, nb);
    y0 = nb[1], y1 = nb[3], xa = nb[0], xb = nb[2];
    if (had) {
        if (vn.ab[1] < y0) y0 = vn.ab[1];
        if (vn.ab[3] > y1) y1 = vn.ab[3];
        if (vn.ab[0] < xa) xa = vn.ab[0];
        if (vn.ab[2] > xb) xb = vn.ab[2];
    }
    vn.arm_at = a, vn.ac = vn_cos(a), vn.as = vn_sin(a), vn.armed = 1;
    memcpy(vn.ab, nb, sizeof nb);
    for (y = y0; y < y1; ++y) {
        int x0 = VN_W, x1 = 0;
        vn_cols(vn.ac, vn.as, 0, 0, y, &x0, &x1);
        vn_cols(vn.ac, vn.as, VN_SH_DX, VN_SH_DY, y, &x0, &x1);
        if (had) {
            vn_cols(oc, os, 0, 0, y, &x0, &x1);
            vn_cols(oc, os, VN_SH_DX, VN_SH_DY, y, &x0, &x1);
        }
        vn_compose(x0 < xa ? xa : x0, y, x1 > xb ? xb : x1, y + 1);
    }
}

/* A key's cell of the band: the play key in its look (the glyph, pressed), previous and next pressed from vinyl_keys, at rest from the base. */
static void vn_key(int k) {
    unsigned *f = (unsigned *)bitmap_lock_buffer_for_write(vn.frame),
             *base = (unsigned *)bitmap_lock_buffer_for_read(vn.base),
             *keys = (unsigned *)bitmap_lock_buffer_for_read(vn.keys);
    int x0 = k == K_PREV   ? VN_PREV_X0
             : k == K_PLAY ? VN_PLAY_X0
                           : VN_NEXT_X0,
        x1 = k == K_PREV   ? VN_PLAY_X0
             : k == K_PLAY ? VN_NEXT_X0
                           : VN_NEXT_X1,
        down = vn.pressed == k,
        cell = k == K_PLAY ? (vn.playkey + 2 * down) * (VN_NEXT_X0 - VN_PLAY_X0)
               : down      ? (k == K_PREV ? VN_CELL_PREV : VN_CELL_NEXT)
                           : -1,
        x, y;
    if (f && base && keys) {
        for (y = VN_BAND_Y0; y < VN_BAND_Y1; ++y)
            for (x = x0; x < x1; ++x)
                f[y * VN_W + x] = cell < 0 ? base[y * VN_W + x] : keys[(y - VN_BAND_Y0) * VN_KEYS_W + cell + x - x0];
        vn_dirty(x0, VN_BAND_Y0, x1, VN_BAND_Y1);
    }
    if (f) bitmap_unlock_buffer(vn.frame);
    if (base) bitmap_unlock_buffer(vn.base);
    if (keys) bitmap_unlock_buffer(vn.keys);
}

static int vn_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int src[4];
    (void)ctx;
    if (!canvas || !vn.win || !vn.frame) return RET_OK;
    src[0] = 0, src[1] = 0, src[2] = VN_W, src[3] = VN_H;
    canvas_draw_image(canvas, vn.frame, src, src);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * What the page shows: the player, the cover, the status bar and the clock, looked at on the timer
 */
static int vn_volume(void) { /* the status bar's label_volume text, read only (never set) */
    void *bar = *(void **)SYSTEM_BAR, *lab = bar ? widget_lookup(bar, "label_volume", 1) : (void *)0;
    char buf[16];
    int v = 0, i;
    if (!lab) return 0;
    buf[0] = 0;
    pod_text_utf8(lab, buf, sizeof buf);
    for (i = 0; buf[i] >= '0' && buf[i] <= '9' && i < 4; ++i) v = v * 10 + buf[i] - '0';
    return v;
}

static void vn_format(char *out, const char *path) { /* the file extension, upper case, at most 4 characters */
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

static unsigned vn_track_key(void *t) {
    unsigned h = cc_fnv(cc_fnv(cc_fnv(FNV_SEED, cc_str(t, REC_PATH)), cc_str(t, REC_TITLE)), cc_str(t, REC_NAME));
    return h | !h;
}

/* The label: the album's cached cover (/mnt/mmc/.m1plus/covers), else the playing track's /tmp cover once demo has made it, reduced to VN_LAB_PX; else vinyl_label.
 * first: a new track (the /tmp file is looked at again VN_SETTLE times: demo writes it a little after the change). */
static void vn_cover(void *t, int first) {
    char url[80], tmp[40];
    const char *file = (const char *)0, *path;
    unsigned album = t && *cc_str(t, REC_ALBUM) ? cc_album_key(t) : 0, *px;
    int busy = 0, ok = 0;
    if (first) vn.settle = VN_SETTLE;
    vn.fkey = 0;
    file = album ? cc_url(url, album) : (const char *)0;
    if (file) {
        if (first) vn.settle = 0; /* the cache file is the album's: nothing to wait for */
    } else if (t && (path = np_cover_file(&busy)) != (const char *)0 && !busy) {
        vn.fkey = np_file_key(path);
        if (vn.fkey) {
            snprintf(tmp, sizeof tmp, "file://%s", path);
            file = tmp;
        }
    }
    px = file ? (unsigned *)bitmap_lock_buffer_for_write(vn.cover) : (unsigned *)0;
    if (px) {
        ok = cc_decode(vn.win, file, 1, VN_LAB_PX, 1, px);
        bitmap_unlock_buffer(vn.cover);
    }
    vn.has_cover = ok;
    vn.retint = vn.rec == VN_REC_COVER;
    vn.cover_t = time_now_ms() + VN_COVER_MS;
}

static int vn_settle(void *t) { /* 1 when the label changed */
    int busy = 0;
    const char *path = np_cover_file(&busy);
    unsigned k;
    vn.cover_t = time_now_ms() + VN_COVER_MS;
    if (busy) return 0; /* being replaced: not counted */
    vn.settle--;
    k = path ? np_file_key(path) : 0;
    if (!k || k == vn.fkey) return 0;
    vn_cover(t, 0);
    return 1;
}

static void vn_copy(char *dst, unsigned size, const char *s) {
    unsigned n = 0;
    while (s[n] && n + 1 < size) dst[n] = s[n], ++n;
    while (n && ((unsigned char)s[n] & 0xc0) == 0x80 && s[n]) --n; /* a cut never leaves half a UTF-8 character */
    dst[n] = 0;
}

/* "VOL 42 | FLAC | 21:07" (tools/vinyl_art.py status_text). No battery: the status bar only has it in 20 % steps. */
static void vn_status(char *out, unsigned size) {
    snprintf(out, size, "VOL %d | %s%s%02d:%02d", vn.vol, vn.fmt, vn.fmt[0] ? " | " : "", vn.hh, vn.mm);
}

/* The arm's next turn toward `to`. A change of more than VN_ARM_SNAP (play, pause, a new track) is a swing eased in and out (smoothstep) over
 * VN_SWING_MS + 1 ms a 1/16 degree, on the page's clock (dt is capped, so a stalled loop holds the swing instead of jumping it); a target that moves a little
 * on the way (the groove as the track plays) is followed, one that jumps starts a new swing from where the arm is. A smaller change is drawn once it reaches
 * VN_ARM_STEP (the groove followed while playing). */
static int vn_arm_next(int to, int dt) {
    int d = to - vn.arm_at, f, e;
    if (vn.sw_len) {
        if (to - vn.sw_to > VN_ARM_SNAP || vn.sw_to - to > VN_ARM_SNAP)
            vn.sw_len = 0;
        else
            vn.sw_to = to;
    }
    if (!vn.sw_len) {
        if (d <= VN_ARM_SNAP && -d <= VN_ARM_SNAP) return d >= VN_ARM_STEP || -d >= VN_ARM_STEP ? to : vn.arm_at;
        vn.sw_from = vn.arm_at, vn.sw_to = to, vn.sw_t = 0, vn.sw_len = VN_SWING_MS + (d < 0 ? -d : d);
    }
    vn.sw_t += dt;
    if (vn.sw_t >= vn.sw_len) {
        vn.sw_len = 0;
        return vn.sw_to;
    }
    f = vn.sw_t * 256 / vn.sw_len, e = f * f * (768 - 2 * f) >> 16; /* 0 .. 255; smoothstep 0 .. 256 */
    return vn.sw_from + (vn.sw_to - vn.sw_from) * e / 256;
}

static int vn_moving(void) {
    int d = vn.arm_to - vn.arm_at;
    return vn.spin || vn.playing || vn.sw_len || d >= VN_ARM_STEP || -d >= VN_ARM_STEP;
}

/* One look at everything: the text, the cover, the label's turn, the arm, the keys; draws what changed and invalidates it. */
static void vn_update(int force) {
    void *t = cc_playing();
    int pos = 0, len = 0, vol, playing = mclGetPlayStatus() == 2, label = force, to, d, i;
    unsigned key = t ? vn_track_key(t) : 0, now = time_now_ms(), dt = now - vn.t_last, step;
    long secs = time((long *)0);
    const int *tm = secs > 1577836800L ? localtime(&secs) : (const int *)0;
    int hh = tm ? tm[2] : 0, mm = tm ? tm[1] : 0, status = force, tinted = 0;
    char line[96];
    if (force) vn.key = ~0u;
    if (!vn.t_last || dt > VN_DT_MAX)
        dt = vn.t_last ? VN_DT_MAX : 0; /* the first look turns nothing; a stalled loop never jumps */
    vn.t_last = now | !now;
    if (!t || get_playtimeandlength(&pos, &len) != 1 || len <= 0) pos = len = 0;
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if (len > 65535) len = 65535, pos = pos > len ? len : pos;
    if (key != vn.key) {
        const char *s = t ? cc_str(t, REC_TITLE) : "";
        if (t && !*s) s = cc_str(t, REC_NAME);
        vn.key = key;
        vn_copy(line, sizeof line, t ? s : TR("Not Playing"));
        widget_set_text_utf8(vn.title, line);
        widget_set_text_utf8(vn.title2, line);
        vn_copy(line, sizeof line, t ? cc_str(t, REC_ARTIST) : "");
        widget_set_text_utf8(vn.artist, line);
        vn_format(vn.fmt, t ? cc_str(t, REC_PATH) : "");
        vn.pos = -1, status = 1, label = 1;
        vn_cover(t, 1);
    } else if (vn.settle > 0 && (int)(now - vn.cover_t) >= 0 && vn_settle(t))
        label = 1;
    if (vn.retint) vn.retint = 0, tinted = vn_retint(); /* Cover: before the layers are locked */
    if (pos != vn.pos || len != vn.len) {
        vn.pos = pos, vn.len = len;
        snprintf(line, sizeof line, "%d:%02d  -%d:%02d", pos / 60, pos % 60, (len - pos) / 60, (len - pos) % 60);
        widget_set_text_utf8(vn.times, line);
    }
    vol = vn_volume();
    if (status || vol != vn.vol || hh != vn.hh || mm != vn.mm) {
        vn.vol = vol, vn.hh = hh, vn.mm = mm;
        vn_status(line, sizeof line);
        widget_set_text_utf8(vn.status, line);
    }
    vn.playing = playing;
    /* the record: speeds up to 33 1/3 rpm while playing, slows to a stop otherwise */
    if (playing && vn.spin < 256)
        vn.spin += (int)(dt * 256 / VN_SPINUP_MS) + 1, vn.spin = vn.spin > 256 ? 256 : vn.spin;
    else if (!playing && vn.spin > 0)
        vn.spin -= (int)(dt * 256 / VN_SPINDOWN_MS) + 1, vn.spin = vn.spin < 0 ? 0 : vn.spin;
    if (!vn.spin) vn.acc = 0;
    vn.acc += dt * (unsigned)vn.spin;
    step = vn.acc / 80, vn.acc %= 80; /* VN_SPEED x spin / 256 a second */
    if (step) vn.ang = (int)(((unsigned)vn.ang + step) % 5760u), label = 1;
    /* the arm: on the groove while playing; paused, it stays where it is until the record has stopped, then parks (its swing never shares a tick with the
     * label's, and comes well after stock's pause stall); nothing playing: parked. A jump of more than VN_ARM_SNAP swings there */
    to = !t ? VN_PARK : playing ? vn_groove_at(pos, len) : vn.spin && vn.armed ? vn.arm_at : VN_PARK;
    vn.arm_to = to;
    if (!vn_lock()) /* the layers, locked once for this look's composes */
        ;
    else if (force) { /* the first look: everything above the band at once */
        vn.arm_at = to, vn.ac = vn_cos(to), vn.as = vn_sin(to), vn.armed = 1, vn.sw_len = 0;
        vn_arm_box(to, vn.ab);
        vn.lc = vn_cos(vn.ang), vn.ls = vn_sin(vn.ang);
        vn_compose(0, 0, VN_W, VN_BAND_Y0);
    } else {
        if (tinted) vn_compose(0, VN_REC_Y - VN_REC_R, VN_REC_X + VN_REC_R + 1, VN_REC_Y + VN_REC_R + 1);
        d = vn_arm_next(to, (int)dt);
        if (d != vn.arm_at) vn_arm_draw(d);
        if (label) vn_label_draw();
    }
    vn_unlock();
    if (force || playing != vn.playkey) {
        vn.playkey = playing;
        for (i = force ? K_PREV : K_PLAY; i <= (force ? K_NEXT : K_PLAY); ++i) vn_key(i);
    }
    vn_flush();
}

/* ---------------------------------------------------------------------------
 * The timer, the window's events
 */
static unsigned vn_want_ms(void) {
    return !pod_screen_lit() ? POD_DARK_MS : vn_moving() ? VN_PLAY_MS : VN_IDLE_MS;
} /* screen off: a slow check, no visual work (docs/modules/vinyl.md "Idle power") */

static void vn_retime(void) {
    unsigned want = vn_want_ms();
    if (vn.timer && want != vn.ival) {
        timer_modify(vn.timer, want);
        vn.ival = want;
    }
}

static int vn_tick(const void *timer) {
    (void)timer;
    if (!vn.win || !vn.fg) {
        vn.timer = 0;
        return RET_OK;
    }
    if (pod_screen_lit())
        vn_update(0); /* dark: nothing drawn, nothing read; the first lit tick catches up (dt is capped) */
    vn_retime();
    return RET_REPEAT;
}

static int vn_first(const void *timer) {
    (void)timer;
    vn.timer = 0;
    if (!vn.win || !vn.fg) return RET_OK;
    if (!pod_screen_lit()) { /* opened with the screen off: the first full draw waits for the light */
        vn.timer = timer_add(vn_first, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    vn_update(1);
    vn.ival = vn_want_ms();
    vn.timer = timer_add(vn_tick, (void *)0, vn.ival);
    return RET_OK;
}

static void vn_unarm(void) {
    if (vn.timer) timer_remove(vn.timer);
    vn.timer = 0;
}

static void vn_release(void) { /* the touch is over (or never was): a key held is let go */
    int was = vn.pressed;
    vn.touch = 0, vn.down = K_NONE, vn.pressed = K_NONE;
    if (was && vn.frame) vn_key(was), vn_flush();
}

static int vn_on_background(void *ctx, void *e) {
    (void)e;
    if (!vn.win || ctx != vn.win) return RET_OK;
    vn.fg = 0;
    vn_unarm();
    vn_release();
    return RET_OK;
}

static int vn_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!vn.win || ctx != vn.win) return RET_OK;
    vn.fg = 1;
    if (!vn.timer) vn.timer = timer_add(vn_first, (void *)0, VN_FIRST_MS);
    return RET_OK;
}

static int vn_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != vn.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    vn_unarm();
    vn_free();
    memset(&vn, 0, sizeof vn);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch
 */
static void vn_local(void *e, int *x, int *y) {
    int pt[2];
    pt[0] = *(int *)((char *)e + PE_X), pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(vn.view, pt);
    *x = pt[0], *y = pt[1];
}

__attribute__((noinline)) int vn_hit(int x, int y) {
    int dx = x - VN_REC_X, dy = y - VN_REC_Y;
    if (x >= 0 && x < VN_CLOSE_X1 && y >= 0 && y < VN_CLOSE_Y1) return K_CLOSE;
    if (y >= VN_BAND_Y0 && y < VN_H && x >= VN_PREV_X0 && x < VN_NEXT_X1)
        return x < VN_PLAY_X0 ? K_PREV : x < VN_NEXT_X0 ? K_PLAY : K_NEXT;
    if (y < VN_BAND_Y0 && dx * dx + dy * dy < VN_REC_R * VN_REC_R) return K_RECORD;
    return K_NONE;
}

/* DOWN, UP and ABORT of the view; nothing else is bound and nothing is grabbed (a MOVE is never consumed here: the stock pull-down from the top edge reads the drag itself). */
static int vn_on_touch(void *ctx, void *e) {
    int type, x, y;
    (void)ctx;
    if (!e || !vn.win) return RET_OK;
    type = *(int *)e;
    if (type == EVT_POINTER_DOWN) {
        vn_release();
        vn_local(e, &x, &y);
        vn.touch = 1, vn.sx = x, vn.sy = y, vn.down = vn_hit(x, y);
        if (vn.down >= K_PREV && vn.down <= K_NEXT) vn.pressed = vn.down, vn_key(vn.down), vn_flush();
    } else if (type == EVT_POINTER_UP && vn.touch) {
        int dx, dy, down = vn.down, hit;
        vn_local(e, &x, &y);
        dx = x - vn.sx, dy = y - vn.sy, hit = vn_hit(x, y);
        vn_release();
        if (hit != down) return RET_OK; /* the finger left what it began on: nothing */
        if (down == K_CLOSE) {
            navigator_back();
            return RET_OK;
        }
        if (down == K_RECORD && ((dx < 0 ? -dx : dx) >= VN_TAP_PX || (dy < 0 ? -dy : dy) >= VN_TAP_PX)) return RET_OK;
        if (down == K_RECORD && vn.idle) {
            navigator_back();
            return RET_OK;
        }
        if (down == K_PLAY || down == K_RECORD)
            playpause_quick_click();
        else if (down == K_NEXT)
            next_quick_click(
                e, 0); /* the click's own event: stock reads its time and ignores a click within 1 s of the last */
        else if (down == K_PREV)
            prev_quick_click(e, 0);
        else
            return RET_OK;
        vn_update(
            0); /* the page looks again at once: the key's glyph, the arm and the record follow without waiting a tick */
        vn_retime();
    } else if (type == EVT_POINTER_ABORT) {
        vn_release();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The record's colour (Settings > Now Playing > Record: 0 Black, 1 Cover; docs/modules/vinyl.md "Record colours"). Black is the installed base as it is. Cover is composed into the page's own
 * copy of the base (vn.base is a copy vn_load made: never the image manager's bitmap) when the page opens and on each track change, so every look reads that base exactly as it reads the black
 * one and costs the same. vinyl_rec holds the record map t in its red channel (0 where the base stays); the colour is five stops (r, g, b) at t = 0, 118, 190, 235, 255 made into a 256 entry
 * table by vn_ramp. Inside the rim a pixel is the table's colour (opaque); a pixel of the rim (the disc's coverage under 1) is the installed base's (kept at the first recolour: vr.rim) plus the colour's difference from the black record's
 * rim (VN_REC_K) by the coverage: the base already holds the plinth and the record's shadow there (whatever the theme), so the picture carries none of it. tools/vinyl_art.py ramp_table,
 * rec_in_map and test/pod/vinyl.py rec_base are the same arithmetic.
 */
#define VN_RIM_MAX 1536 /* the map's rim pixels (1020 measured; test/pod/vinyl.py checks the margin) */

static struct {
    unsigned w[256]; /* the colour of map value t, opaque */
    unsigned rim
        [VN_RIM_MAX]; /* the installed base's rim pixels (the map's, in scan order), kept at the first recolour: a rim pixel always blends from these */
} vr __attribute__((section(".scratch")));

static void vn_ramp(const unsigned char (*st)[3]) {
    static const unsigned char tt[5] = {0, 118, 190, 235, 255};
    int t, k = 0;
    for (t = 0; t < 256; ++t) {
        int t0, t1, d, i;
        unsigned c[3];
        while (k < 3 && t > tt[k + 1]) ++k;
        t0 = tt[k], t1 = tt[k + 1], d = t1 - t0;
        for (i = 0; i < 3; ++i) c[i] = (unsigned)(st[k][i] * (t1 - t) + st[k + 1][i] * (t - t0) + d / 2) / (unsigned)d;
        vr.w[t] = c[0] | c[1] << 8 | c[2] << 16 | 0xff000000u;
    }
}

/* The colour st on the page's base inside the record's box, 1 when composed (0: vinyl_rec would not load or is another size: the base is left as it is). */
static int vn_recolour(const unsigned char (*st)[3]) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, *base, stride = 0;
    const unsigned char *data;
    int ok = 0, x, y, ri = 0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(vn.win, "vinyl_rec", bitmap)) return 0;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data = format < 4 && bitmap[0] == VN_RB_W && bitmap[1] == VN_RB_H ? bitmap_lock_buffer_for_read(bitmap)
                                                                      : (const unsigned char *)0;
    base = data ? (unsigned *)bitmap_lock_buffer_for_write(vn.base) : (unsigned *)0;
    if (base) {
        stride = bitmap_get_line_length(bitmap);
        vn_ramp(st);
        for (y = 0; y < VN_RB_H; ++y) {
            const unsigned char *s = data + y * stride + at[format][0];
            unsigned *o = base + (y + VN_RB_Y0) * VN_W + VN_RB_X0;
            int vy = 2 * (y + VN_RB_Y0 - VN_REC_Y) + 1;
            for (x = 0; x < VN_RB_W; ++x, s += 4) {
                unsigned m = *s, w;
                int vx, d2;
                if (!m) continue;
                vx = 2 * (x + VN_RB_X0 - VN_REC_X) + 1, d2 = vx * vx + vy * vy, w = vr.w[m];
                if (d2 > (2 * VN_REC_R - 2) *
                             (2 * VN_REC_R - 2)) { /* the rim: the disc's coverage of this pixel, in 1/8 pixel */
                    int c = 8 * VN_REC_R + 4 - vn_isqrt(16 * d2), i;
                    unsigned cov = c <= 0 ? 0 : c >= 8 ? 255 : (unsigned)c * 32, b = o[x], out = 0xff000000u;
                    if (ri <
                        VN_RIM_MAX) { /* the first recolour: the base is still the installed one; later ones blend from what it saved */
                        if (!vn.rim_saved) vr.rim[ri] = b;
                        b = vr.rim[ri];
                    }
                    ++ri;
                    for (i = 0; i < 24; i += 8) {
                        int v = (int)(b >> i & 255) + (int)((((w >> i & 255) * cov + 127) / 255)) -
                                (int)((VN_REC_K * cov + 127) / 255);
                        out |= (unsigned)(v < 0 ? 0 : v > 255 ? 255 : v) << i;
                    }
                    w = out;
                }
                o[x] = w;
            }
        }
        bitmap_unlock_buffer(vn.base);
        vn.rim_saved = 1;
        ok = 1;
    }
    if (data) bitmap_unlock_buffer(bitmap);
    widget_unload_image(vn.win, bitmap);
    return ok;
}

/* The saved plinth theme: '1' Snow (an optional newline), anything else or no file Graphite; reading never writes. */
int vinyl_theme(void) { return set_read(VINYLTHEME_FILE, 0) == '1'; }

/* Choose the theme (0 Graphite, 1 Snow), saved atomically; the theme, or -1 (unknown, or not saved: the saved one is unchanged). */
int vinyl_theme_set(int theme) {
    static const char *const text[VN_THEMES] = {"0\n", "1\n"};
    if (theme < 0 || theme >= VN_THEMES) return -1;
    return home_write_atomic(VINYLTHEME_FILE, VINYLTHEME_TMP, text[theme]) == 0 ? theme : -1;
}

/* The saved colour: '1' Cover (an optional newline), anything else or no file Black; reading never writes. */
int vinyl_record(void) { return set_read(VINYLREC_FILE, 0) == '1'; }

/* Choose the colour (0 Black, 1 Cover), saved atomically; the colour, or -1 (unknown, or not saved: the saved one is unchanged). */
int vinyl_record_set(int rec) {
    static const char *const text[VN_RECS] = {"0\n", "1\n"};
    if (rec < 0 || rec >= VN_RECS) return -1;
    return home_write_atomic(VINYLREC_FILE, VINYLREC_TMP, text[rec]) == 0 ? rec : -1;
}

/* The Cover colour: the record tinted from the decoded cover (vn.cover, VN_LAB_PX square). The mean colour of each cell of a 16 x 16 grid; the chroma-weighted mean of the cells whose chroma
 * (max - min) is at least the grid's mean; its saturation clamped to 170 .. 235 and its value to 125 .. 190 (the hue kept); then the ramp (tools/vinyl_art.py cover_tint_px and tint_stops are the
 * same integers). 0 for a (nearly) grey cover (the mean chroma under 24) or no cover: the record is black. */
static int vn_tint(unsigned char (*st)[3]) {
    const unsigned *px = vn.has_cover ? (const unsigned *)bitmap_lock_buffer_for_read(vn.cover) : (const unsigned *)0;
    unsigned char cell[3][256];
    unsigned sum[3] = {0, 0, 0}, sw = 0, mean = 0, hi, lo, sat, val, k, span, c[3];
    int i, j, x, y, a;
    if (!px) return 0;
    for (j = 0; j < 16; ++j)
        for (i = 0; i < 16; ++i) {
            unsigned s[3] = {0, 0, 0}, cnt = 0;
            for (y = j * VN_LAB_PX / 16; y < (j + 1) * VN_LAB_PX / 16; ++y)
                for (x = i * VN_LAB_PX / 16; x < (i + 1) * VN_LAB_PX / 16; ++x, ++cnt) {
                    unsigned p = px[y * VN_LAB_PX + x];
                    s[0] += p & 255, s[1] += p >> 8 & 255, s[2] += p >> 16 & 255;
                }
            for (a = 0; a < 3; ++a) cell[a][j * 16 + i] = (unsigned char)(s[a] / cnt);
        }
    bitmap_unlock_buffer(vn.cover);
    for (i = 0; i < 256; ++i) {
        hi = lo = cell[0][i];
        for (a = 1; a < 3; ++a) hi = cell[a][i] > hi ? cell[a][i] : hi, lo = cell[a][i] < lo ? cell[a][i] : lo;
        mean += hi - lo;
    }
    mean /= 256;
    if (mean < 24) return 0;
    for (i = 0; i < 256; ++i) {
        hi = lo = cell[0][i];
        for (a = 1; a < 3; ++a) hi = cell[a][i] > hi ? cell[a][i] : hi, lo = cell[a][i] < lo ? cell[a][i] : lo;
        if (hi - lo >= mean) {
            for (a = 0; a < 3; ++a) sum[a] += cell[a][i] * (hi - lo);
            sw += hi - lo;
        }
    }
    for (a = 0; a < 3; ++a) c[a] = sum[a] / sw;
    hi = c[0] > c[1] ? c[0] : c[1], hi = c[2] > hi ? c[2] : hi;
    lo = c[0] < c[1] ? c[0] : c[1], lo = c[2] < lo ? c[2] : lo;
    sat = (hi - lo) * 255 / (hi ? hi : 1), sat = sat < 170 ? 170 : sat > 235 ? 235 : sat;
    val = hi < 125 ? 125 : hi > 190 ? 190 : hi;
    k = val * sat / 255, span = hi - lo ? hi - lo : 1;
    for (a = 0; a < 3; ++a) {
        unsigned t =
            (val - k + (c[a] - lo) * k / span) * 225 >> 8; /* the tint, a little deeper than the label's colour */
        st[0][a] = (unsigned char)(t * 77 >> 8);
        st[1][a] = (unsigned char)t;
        st[2][a] = (unsigned char)(t + ((255 - t) * 26 >> 8));
        st[3][a] = (unsigned char)(t + ((255 - t) * 51 >> 8));
        st[4][a] = (unsigned char)(t + ((255 - t) * 72 >> 8));
    }
    return 1;
}

/* The page's record after a new cover (Cover colour): tinted from it, or black (a grey cover, none) again. 1 when the base changed, so the record's box is composed again. */
static int vn_retint(void) {
    unsigned char st[5][3];
    int i;
    if (vn_tint(st)) {
        for (i = 0; vn.tinted && i < 15 && st[i / 3][i % 3] == vn.tst[i / 3][i % 3]; ++i) {
        }
        if (i == 15) return 0; /* the same tint: the base is already it */
        if (!vn_recolour(st)) return 0;
        memcpy(vn.tst, st, sizeof st), vn.tinted = 1;
        return 1;
    }
    if (vn.tinted) { /* back to black: only the pixels vn_recolour wrote, so the plinth keeps its grain: inside the rim the
                        installed base's (no grain there), the rim the pixels it saved (grained where the plinth shows through) */
        void *b = vn_load(vn_names[vn.theme][0], VN_W, VN_H, 0);
        unsigned *src = b ? (unsigned *)bitmap_lock_buffer_for_read(b) : (unsigned *)0,
                 *dst = src ? (unsigned *)bitmap_lock_buffer_for_write(vn.base) : (unsigned *)0;
        int x, y, ri = 0;
        if (dst)
            for (y = 0; y < VN_RB_H; ++y) {
                unsigned *o = dst + (y + VN_RB_Y0) * VN_W + VN_RB_X0;
                const unsigned *s = src + (y + VN_RB_Y0) * VN_W + VN_RB_X0;
                int vy = 2 * (y + VN_RB_Y0 - VN_REC_Y) + 1;
                for (x = 0; x < VN_RB_W; ++x) {
                    int vx = 2 * (x + VN_RB_X0 - VN_REC_X) + 1, d2 = vx * vx + vy * vy;
                    if (d2 <= (2 * VN_REC_R - 2) * (2 * VN_REC_R - 2))
                        o[x] = s[x];
                    else if (d2 < (2 * VN_REC_R + 2) * (2 * VN_REC_R + 2) && 8 * VN_REC_R + 4 - vn_isqrt(16 * d2) > 0)
                        o[x] = ri < VN_RIM_MAX ? vr.rim[ri] : s[x], ++ri; /* vn_recolour's rim pixels, in its order */
                }
            }
        if (dst) bitmap_unlock_buffer(vn.base);
        if (src) bitmap_unlock_buffer(b);
        if (b) bitmap_destroy(b);
        vn.tinted = 0;
        return dst != (unsigned *)0;
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * Open: the More dialog's Vinyl Mode row. 0 once the page is up (or already open); -1 when it could not open (nothing is left of it).
 */
int vinyl_open(void) {
    if (vn.win) return 0;
    memset(&vn, 0, sizeof vn);
    vn.theme = vinyl_theme(); /* read once: a change in Settings shows the next time the page opens */
    vn.win = window_open(vn_pages[vn.theme]);
    if (!vn.win) {
        memset(&vn, 0, sizeof vn);
        return -1;
    }
    widget_on(vn.win, EVT_DESTROY, vn_on_destroy, vn.win);
    vn.view = widget_lookup(vn.win, "vinyl_view", 1);
    vn.title = widget_lookup(vn.win, "vn_title", 1);
    vn.title2 = widget_lookup(vn.win, "vn_title2", 1);
    vn.artist = widget_lookup(vn.win, "vn_artist", 1);
    vn.times = widget_lookup(vn.win, "vn_times", 1);
    vn.status = widget_lookup(vn.win, "vn_status", 1);
    if (vn.view && vn.title && vn.title2 && vn.artist && vn.times && vn.status) {
        unsigned *f;
        vn.base = vn_load(vn_names[vn.theme][0], VN_W, VN_H, 0);
        if (vn.base) vn_grain(vn.base, 0, 0, VN_W, VN_H);
        vn.keys = vn_load(vn_names[vn.theme][5], VN_KEYS_W, VN_BAND_Y1 - VN_BAND_Y0, 0);
        vn.arm = vn_load(vn_names[vn.theme][2], VN_ARM_W, VN_ARM_H, 1);
        vn.sh = vn_load(vn_names[vn.theme][3], VN_ARM_W, VN_ARM_H, 0);
        vn.lid = vn_load(vn_names[vn.theme][1], VN_LID_PX, VN_LID_PX, 0);
        vn.cap = vn_load(vn_names[vn.theme][4], VN_CAP_PX, VN_CAP_PX, 0);
        vn.fall = vn_load("vinyl_label", VN_LAB_PX, VN_LAB_PX, 0);
        vn.cover = bitmap_create_ex(VN_LAB_PX, VN_LAB_PX, VN_LAB_PX * 4, BITMAP_RGBA8888);
        vn.frame = bitmap_create_ex(VN_W, VN_H, VN_W * 4, BITMAP_RGBA8888);
        vn.rec =
            vinyl_record(); /* read once (a change in Settings shows the next time the page opens); Cover is composed into vn.base at the first look, once the cover is decoded (vn_retint) */
        f = vn.frame && vn.base && vn.keys && vn.arm && vn.sh && vn.lid && vn.cap && vn.fall && vn.cover
                ? (unsigned *)bitmap_lock_buffer_for_write(vn.frame)
                : (unsigned *)0;
        if (f) {
            const unsigned *b = (const unsigned *)bitmap_lock_buffer_for_read(vn.base);
            if (b) {
                memcpy(f, b, (unsigned)VN_W * VN_H * 4);
                bitmap_unlock_buffer(vn.base);
            }
            bitmap_unlock_buffer(vn.frame);
            if (!b) f = (unsigned *)0;
        }
        if (f) {
            vn.fg = 1;
            vn.key = ~0u;
            vn.playkey = -1;
            vn.arm_at = vn.arm_to = VN_PARK;
            widget_on(vn.win, EVT_WINDOW_TO_BG, vn_on_background, vn.win);
            widget_on(vn.win, EVT_WINDOW_TO_FG, vn_on_foreground, vn.win);
            widget_on(vn.view, EVT_POINTER_DOWN, vn_on_touch, (void *)0);
            widget_on(vn.view, EVT_POINTER_UP, vn_on_touch, (void *)0);
            widget_on(vn.view, EVT_POINTER_ABORT, vn_on_touch, (void *)0);
            widget_on(vn.view, EVT_AFTER_PAINT, vn_on_paint, (void *)0);
            vn.timer = timer_add(vn_first, (void *)0, VN_FIRST_MS);
            return 0;
        }
    }
    vn_free(); /* an asset that is not ours, or no memory: the window goes again */
    vn.win = (void *)0; /* (its destroy handler leaves a newer page alone) */
    navigator_back();
    memset(&vn, 0, sizeof vn);
    return -1;
}

/* Open for Now Playing's idle timer (patch/bigcover.c bc_timed_open): as vinyl_open, and a tap on the record then closes the page like the chevron (as stock's Album Cover page closes on a tap)
 * instead of pausing. A page that is already open is left as it is, flag included. The flag lives in the page's state, which destroy clears. */
int vinyl_open_idle(void) {
    int was = vn.win != (void *)0, r = vinyl_open();
    if (!was && r == 0) vn.idle = 1;
    return r;
}
