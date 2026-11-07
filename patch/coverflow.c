/* M1+ Music Cover Flow: the stock Local Music albums as a cover carousel inside demo.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * After the design of q2-pod's Cover Flow (https://github.com/DiamondBond/q2-pod). The depth renderer
 * (pose/project/unproject/column/draw_cover/coverflow_render, after Rockbox PictureFlow), the
 * thumbnail-cache design (one pthread, free-space guard, empty-file "no art" marker, ART_NEAR window)
 * and the texture-ring bookkeeping follow its design; everything that touches the device -- the
 * stock queries, the art calls, the page, its layout and its touch handling -- is written for the
 * M1 Plus, which has a touchscreen and no scroll wheel, so the wheel-only parts of q2-pod
 * (keys 172/173, ringnav, scrub) are gone; a transparent touch layer of the page's own drives the
 * shelf (drag, fling, snap, tap by x): its own position in depth mode, a stock slide_menu in the flat fallback.
 *
 * No stock function is hooked. The page is opened from a row of the M1+ Music menu (the library's
 * albums) or from a row of the M1+ Music Artists list (one artist's
 * albums, coverflow_artist: q2-pod's ARTIST_ALBUMS scope, with the stock "All songs" row as its All
 * albums card), and everything here is reached only from that page's own widgets, timers and its
 * one worker thread. A tap on the centre cover opens our album page (open_album; the stock page when it does not open).
 *
 * The shelf is the 168 px one (offsets.inc: 276 px frame, DRAG_PX 108); the cache files carry
 * their size (<key>-168.jpg). The captions are hscroll_labels in the asset (tools/pod_ui.py). With
 * CF_HOST the renderer alone is built for the host (test/coverflow.py). docs/architecture.md.
 */
#include "offsets.inc"

#include "coverflow.h" /* CF_ONE, CF_REACH, CF_RING, cfg_t, coverflow_render */
#define CF_WANTED (CF_RING + 1) /* the covers the loader keeps decoded: the ring and the next one ahead */
#define CF_SLOTS (CF_WANTED + 1) /* texture slots: those and one left behind, for a reversal */
#define CF_TEXELS (ART_SIZE * ART_SIZE)
#define CF_MAXW CFL_W /* the most columns a shelf has: the per-column spans below */

#ifdef CF_HOST
#include <stdlib.h>
#include <string.h>
#else
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "subsonic.h"
#endif
#include "covercache.h"
#include "common.h"

extern int
songs_open_artist(void *artist); /* patch/songs.c: our Songs page on all the artist's songs; -1 when it did not open */
extern int songs_open_nav_filter(int filter, const char *name, const char *artist); /* patch/songs.c */

/* ===========================================================================
 * The depth renderer (q2-pod, after Rockbox PictureFlow). All integer: 16.16 turns and
 * rotations, geometry in 1/16 px, row spans in 1/256 px. Built on the host too (test/coverflow.py).
 */

/* cos and sin of 0 to 90 degrees in 3.75 degree steps, 16.16 (a shelf turns its side covers cfg_t.turn steps) */
static const int cf_cos[25] = {65536, 65396, 64975, 64277, 63303, 62058, 60547, 58777, 56756,
                               54491, 51993, 49273, 46341, 43211, 39896, 36410, 32768, 28986,
                               25080, 21066, 16962, 12785, 8554,  4286,  0};
static const int cf_sin[25] = {0,     4286,  8554,  12785, 16962, 21066, 25080, 28986, 32768,
                               36410, 39896, 43211, 46341, 49273, 51993, 54491, 56756, 58777,
                               60547, 62058, 63303, 64277, 64975, 65396, 65536};

/* cfg_t (a shelf's geometry) is in coverflow.h. */
const cfg_t cf_portrait = {CF_VIEW_W, CF_VIEW_H, CF_CX,      CF_TOP, ART_SIZE, CF_EYE, CF_X1, CF_XS,
                           CF_Z1,     CF_ZS,     CF_REFLECT, 0,      CF_TURN,  0,      0};
const cfg_t cf_land = {CFL_W, CFL_H, CFL_CX,     CFL_TOP, ART_SIZE, CF_EYE, CFL_X1, CFL_XS,
                       CF_Z1, CF_ZS, CF_REFLECT, 1,       CF_TURN,  0,      0};

/* A right-hand cover t (16.16, >= 0) from the visual position: centre xc and depth zc (1/16 px),
 * rotation c, s (16.16) and brightness (of 256). Left covers mirror it. */
typedef struct {
    int xc, zc, c, s, bright;
} pose_t;

static void pose(const cfg_t *g, int t, pose_t *p) {
    int a = (t < CF_ONE ? t : CF_ONE) * g->turn, i = a >> 16, f = a >> 4 & 4095;
    p->c = cf_cos[i] + (i < g->turn ? (cf_cos[i + 1] - cf_cos[i]) * f >> 12 : 0);
    p->s = cf_sin[i] + (i < g->turn ? (cf_sin[i + 1] - cf_sin[i]) * f >> 12 : 0);
    if (t < CF_ONE) {
        /* xc = A t + B t^2: x1 at t = 1, arriving at the stack's xs slope, and quick at
         * first, so the covers turning in and out mid-step keep clear of each other. */
        int sq = (int)((unsigned)t * (unsigned)t >> 16);
        p->xc = (16 * (2 * g->x1 - g->xs) * t + 16 * (g->xs - g->x1) * sq) >> 16;
        p->zc = 16 * g->z1 * t >> 16;
        p->bright = 256 - ((256 - CF_BRIGHT1) * t >> 16);
    } else {
        int e = t - CF_ONE;
        p->xc = 16 * g->x1 + (16 * g->xs * e >> 16);
        p->zc = 16 * g->z1 + (16 * g->zs * e >> 16);
        p->bright = e < CF_ONE       ? CF_BRIGHT1 - ((CF_BRIGHT1 - CF_BRIGHT2) * e >> 16)
                    : e < 2 * CF_ONE ? CF_BRIGHT2 * (2 * CF_ONE - e) >> 16
                                     : 0;
    }
    if (g->tail) /* the iPod page's longer shelf: a light dim to g->tail at three out, gone by 3.5 */
        p->bright = t < 3 * CF_ONE       ? 256 - (int)((256 - g->tail) * (unsigned)t / (3 * CF_ONE))
                    : t < 7 * CF_ONE / 2 ? g->tail * (7 * CF_ONE - 2 * t) >> 16
                                         : 0;
}

/* Screen x (1/16 px right of the centre line) of the cover point u (1/16 px from its middle). */
static int project(const cfg_t *g, const pose_t *p, int u) {
    int eye = 16 * g->eye;
    return (p->xc + (u * p->c >> 16)) * eye / (eye + p->zc - (u * p->s >> 16));
}

/* The cover point under screen x dx (1/16 px right of the centre line), the inverse of project;
 * 0 when the column misses the cover. *h gets the cover's projected height there (1/256 px). */
static int unproject(const cfg_t *g, const pose_t *p, int dx, int *u, int *h) {
    int eye = 16 * g->eye, half = 8 * g->art, den = (eye * p->c + dx * p->s) >> 16;
    if (den <= 0) return 0;
    *u = (dx * (eye + p->zc) - eye * p->xc) / den;
    if (*u < -half || *u >= half) return 0;
    *h = g->art * 256 * eye / (eye + p->zc - (*u * p->s >> 16));
    return 1;
}

#define HOT static inline __attribute__((always_inline)) /* -Oz would call these per pixel */

/* p scaled by b (of 256), per 8-bit channel; alpha is left 0. */
HOT unsigned shade(unsigned p, unsigned b) {
    return ((p & 0xff00ffu) * b >> 8 & 0xff00ffu) | ((p & 0xff00u) * b >> 8 & 0xff00u);
}

/* The frame being drawn, nearest cover first: each pixel's alpha byte holds the coverage so far
 * (255 opaque), and a layer only fills what is left, which composites as drawing back to front
 * would. Per column, rows solid_top to solid_bottom are known opaque and skipped outright. */
typedef struct {
    const cfg_t *g;
    unsigned *d; /* the logical (0, 0) pixel */
    int cs, rs; /* pixels from one logical column / row to the next: 1 and pitch, or pitch and -1 */
    short solid_top[CF_MAXW], solid_bottom[CF_MAXW];
} shelf_t;

/* colour (alpha ignored) under what is already at px, covering cov (of 256) of the pixel */
HOT void put(unsigned *px, unsigned colour, unsigned cov) {
    unsigned a = *px >> 24, have = a + (a >> 7), w = cov * (256 - have) >> 8;
    if (!a && cov == 256) {
        *px = colour | 0xff000000u;
        return;
    }
    if (!w) return;
    have += w;
    *px = ((*px & 0xffffffu) + shade(colour, w)) | (have > 255 ? 255u : have) << 24;
}

/* One texture column (texels ART_SIZE apart) h high (1/256 px) on the horizon at frame column col,
 * its partial end rows by coverage, then its reflection fading out below. */
static void column(shelf_t *f, int col, const unsigned *tex, int h, int bright) {
    if (h < 16) return;
    const cfg_t *g = f->g;
    unsigned *d = f->d + col * f->cs;
    int top = 256 * (g->top + g->art / 2) - h / 2, bottom = top + h, step = (ART_SIZE << 20) / (h >> 4);
    int solid_top = f->solid_top[col], solid_bottom = f->solid_bottom[col];
    int y = top >> 8, end = (bottom + 255) >> 8, last = end < g->h ? end : g->h;
    int first = y, final = end - 1; /* the rows the edges cross */
    int v = (((y << 8) + 128 - top) >> 4) * step >> 4, pitch = f->rs; /* v: 16.16 texel row */
    unsigned *px,
        haze = shade(g->bg, 256 - (unsigned)bright); /* the fade: towards black, or towards bg (still opaque) */
    if (y < 0) v -= y * step, y = 0;
    px = d + y * pitch;
    while (y < last) {
        int run;
        if (y >= solid_top && y < solid_bottom) {
            int skip = solid_bottom - y;
            v += skip * step, px += skip * pitch, y = solid_bottom;
            continue;
        }
        run = y < solid_top && solid_top < last ? solid_top : last; /* up to the opaque span */
        for (; y < run; ++y, v += step, px += pitch) {
            int row = v < 0 ? 0 : v >> 16 >= ART_SIZE ? ART_SIZE - 1 : v >> 16;
            unsigned cov = 256;
            if (y == first || y == final) {
                int from = y << 8 > top ? y << 8 : top, to = (y + 1) << 8 < bottom ? (y + 1) << 8 : bottom;
                cov = (unsigned)(to - from);
            }
            put(px, shade(tex[row * ART_SIZE], (unsigned)bright) + haze, cov);
        }
    }
    /* The reflection starts where the body ends, sharing the row the body only partly covers. */
    {
        int reflect = h * g->reflect / g->art, stop = (bottom + reflect + 255) >> 8;
        int fade = reflect > 0 ? (256 << 16) / reflect : 0; /* fading per 1/256 px, 16.16 */
        unsigned dim = (unsigned)bright * CF_REFLECT_TOP >> 8;
        int s0, s1;
        if (stop > g->h) stop = g->h;
        for (y = bottom >> 8, px = d + y * pitch; reflect && y < stop; ++y, px += pitch) {
            int from = y << 8 > bottom ? y << 8 : bottom, dist = ((from + ((y + 1) << 8)) >> 1) - bottom, mirrored, row;
            unsigned cov;
            if (dist >= reflect) break;
            if (y < 0 || (y >= solid_top && y < solid_bottom)) continue;
            mirrored = dist * step >> 8 >> 16; /* texel rows up from the bottom edge */
            row = ART_SIZE - 1 - (mirrored >= ART_SIZE ? ART_SIZE - 1 : mirrored);
            cov = (unsigned)(((y + 1) << 8) - from) * (256u - (unsigned)(dist * fade >> 16)) >> 8;
            if (g->bg)
                put(px, tex[row * ART_SIZE], cov * dim >> 8);
            else
                put(px, shade(tex[row * ART_SIZE], dim), cov);
        }
        /* The rows this body covers whole are opaque now: join them to the known span, or keep
         * the longer of the two. */
        s0 = (top + 255) >> 8, s1 = bottom >> 8;
        s0 = s0 < 0 ? 0 : s0, s1 = s1 > g->h ? g->h : s1;
        if (s1 <= s0) return;
        if (solid_bottom > solid_top && s0 <= solid_bottom && s1 >= solid_top) {
            s0 = s0 < solid_top ? s0 : solid_top;
            s1 = s1 > solid_bottom ? s1 : solid_bottom;
        } else if (s1 - s0 <= solid_bottom - solid_top)
            return;
        f->solid_top[col] = (short)s0, f->solid_bottom[col] = (short)s1;
    }
}

/* The cover t (16.16, signed) turns from the visual position, under what is drawn. */
static void draw_cover(shelf_t *f, int t, const unsigned *tex) {
    pose_t p;
    int side = t < 0 ? -1 : 1, a, b, lo, hi, v;
    const cfg_t *g = f->g;
    int half = 8 * g->art;
    pose(g, t * side, &p);
    if (p.bright <= 0 || !tex) return;
    a = project(g, &p, -half), b = project(g, &p, half);
    lo = (16 * g->cx + (a < b ? a : b)) >> 4, hi = (16 * g->cx + (a < b ? b : a)) >> 4;
    for (v = lo; v <= hi; ++v) { /* v: the column as if the cover were on the right */
        int col = side > 0 ? v : 2 * g->cx - 1 - v, u, h, k;
        if (col < 0 || col >= g->w || !unproject(g, &p, (2 * v + 1 - 2 * g->cx) * 8, &u, &h)) continue;
        k = (u + half) * ART_SIZE / (16 * g->art); /* the texture column under that point */
        if (k < 0) k = 0;
        if (k >= ART_SIZE) k = ART_SIZE - 1;
        column(f, col, tex + (side > 0 ? k : ART_SIZE - 1 - k), h, p.bright);
    }
}

/* The ring slot of the k-th nearest pair's nearer (i 0) or farther (i 1) cover at frac: the side
 * the position is moving away from is farther. */
static int slot(int frac, int k, int i) { return (i == 0) == (frac < 0) ? CF_REACH - k : CF_REACH + k; }

/* The shelf at frac (16.16, -CF_ONE/2 to under CF_ONE/2) past its centre cover: ring[j] is the
 * texture of the cover j - CF_REACH from the centre, or 0 to leave it out. Nearest first; nearer
 * covers and their reflections overlap farther ones. The bitmap d (pitch pixels a line) holds the
 * whole frame: g->w x g->h, or for a rotated shelf g->h wide and g->w high, where the logical
 * (x, y) lands at physical (g->h - 1 - y, x) and the renderer simply walks columns down the bitmap
 * and rows leftwards, so the turn costs no copy and no second bitmap. */
void coverflow_render(const cfg_t *g, unsigned *d, int pitch, int frac, const unsigned *const ring[CF_RING]) {
    shelf_t f;
    int x, y, k, i, pw = g->rot ? g->h : g->w, ph = g->rot ? g->w : g->h;
    f.g = g;
    f.d = g->rot ? d + (g->h - 1) : d;
    f.cs = g->rot ? pitch : 1, f.rs = g->rot ? -1 : pitch;
    for (x = 0; x < g->w; ++x) f.solid_top[x] = f.solid_bottom[x] = 0;
    for (y = 0; y < ph; ++y) memset(d + y * pitch, 0, pw * 4);
    for (k = 0; k <= CF_REACH; ++k)
        for (i = 0; i < (k ? 2 : 1); ++i) {
            int j = slot(frac, k, i);
            draw_cover(&f, (j - CF_REACH) * CF_ONE - frac, ring[j]);
        }
    for (y = 0; y < ph; ++y) { /* over black, or over g->bg: what the covers do not cover of each pixel */
        unsigned *p = d + y * pitch;
        x = pw;
        if (g->bg) do {
                unsigned a = *p >> 24, have = a + (a >> 7);
                *p = ((*p & 0xffffffu) + shade(g->bg, 256 - have)) | 0xff000000u;
                ++p;
            } while (--x);
        else
            do *p++ |= 0xff000000u;
            while (--x);
    }
}

#ifndef CF_HOST
/* ===========================================================================
 * The page. UI thread only, except the worker thread marked below.
 */
#define I(r, off) (*(int *)((char *)(r) + (off)))

#define POSITION_FILE \
    CARD_DIR "/coverflow-position" /* the centre album's key (8 hex digits), so a reboot opens on it */
#define ART_NEAR 3 /* flat fallback: real art only this many covers either side */
#define PLACEHOLDER "p_default" /* the stock 254 px disc, Now Playing's missing-art image */
#define POLL_MS 250
#define LOAD_MS 1 /* the texture loader: one decode per main-loop turn, input in between */
#define MAX_ALBUMS 4000 /* the job array and the slide_menu's children are bounded */
#define CF_SAMPLES 8 /* pointer samples kept for the fling velocity */
#define CF_NAV_BATCH 256
#define CF_NAV_MS 16
#define CF_NAV_ALBUM_ID CC_NAV_ALBUM_ID

typedef struct {
    unsigned hash, row;
} cf_album_slot_t;

enum { CF_COVERS, CF_PREPARING }; /* CF_COVERS is 0: a zeroed cf is on it */
enum { ARTIST_ALBUMS = 1 }; /* cf.scoped, as q2-pod's */

static struct {
    void *win, *covers, *slide, *name, *artist, *status, *cancel;
    void *
        songs; /* btn_songs, the artist page's other button: our Songs page on the artist (hidden unless the stock list had the All songs row) */
    void *input; /* the transparent touch layer over the covers, the frame's size */
    int land; /* landscape: the frame is the body under the navbar, turned a quarter */
    void *albums; /* our copy of the stock album rows */
    unsigned *
        order; /* the library shelf's display order, as the stock row numbers (cc_album_order; scoped: the same order with Artist as Title, cc_scoped_sort); NULL = stock order */
    unsigned count; /* how many of them are covers (scoped: the card only with two albums) */
    unsigned local_count, nav_cursor, nav_total, nav_slot_cap;
    unsigned nav_timer;
    int nav_scanning;
    cf_album_slot_t *nav_slots;
    const sb_song_t **nav_art; /* first server art source for local albums missing cached art */
    const sb_song_t **nav_album_art; /* first server art source for each virtual album */
    sb_library_index_t nav_index; /* keeps nav_art and nav_album_art pointers valid */
    /* Scoped (ARTIST_ALBUMS, else 0): albums holds one artist's album rows as the stock artist
     * page lists them (loadAlbumList 0xf004), the last one the stock "All songs" row, shown as
     * the All albums card; artist_row is a deque holding our copy of that artist's row; keys[i]
     * is album i's cache key, the library album of the same name's, so the covers are the main
     * Cover Flow's files. No saved album: the main Cover Flow's last album is left alone. */
    int scoped;
    unsigned
        scope; /* scoped: the stock class the row came from, CLASS_ARTISTS or CLASS_COMPOSERS (what loadAlbumList takes) */
    void *artist_row;
    unsigned *keys;
    int owns; /* this page holds the shared worker's job set (cc_build_*) */
    unsigned timer;
    unsigned saved_album; /* the centre album's key, kept across opens and reboots */
    int screen, album;
    /* touch: the pointer is down (and grabbed); a horizontal drag has started, from the finger at origin;
     * the press stopped a snap animation; the greatest excursion from the down point (either axis); the
     * offset the press found; the recent samples for the fling velocity (a ring, the newest at sample) */
    int built; /* the covers screen's widgets exist (once per page) */
    int fg; /* page timers and worker callbacks run only while this window is foreground */
    int dragging, active, interrupted, reach, down_x, down_y, origin, base_off;
    int sample, samples, sx[CF_SAMPLES], st[CF_SAMPLES];
    /* the snap animation: from and to offsets, its start (time_now_ms) and length, and its timer */
    int snap_from, snap_to, snap_ms;
    unsigned snap_t0, snap_timer;
} cf __attribute__((section(".scratch")));

/* The depth renderer's state: the frame, the textures of the covers around the visual position
 * and the placeholder's. No frame: the flat fallback (stock images on the slide_menu). */
static struct {
    void *frame; /* bitmap_t *, RGBA8888: CF_VIEW_W x CF_VIEW_H, or in landscape the body (CFL_H x CFL_W) */
    unsigned *tex; /* CF_SLOTS texture slots, then the placeholder */
    int album[CF_SLOTS]; /* each slot's album + 1; 0 is empty */
    const unsigned *art[CF_SLOTS]; /* its texture: the slot's own, or the placeholder (the album has no art) */
    int c, frac, drawn; /* the position the frame holds, once drawn */
    int dir; /* the way the shelf last went: 1 towards later albums, -1 back */
    int seen; /* the centre album the last paint saw + 1; 0 none yet */
    unsigned load_timer; /* the texture loader's timer (the page's own) */
} fx __attribute__((section(".scratch")));

/* Depth mode's shelf, owned here (no stock widget is laid out as it moves): the committed album and the
 * offset from it, in the slide_menu's xoffset units (CF_VIEW_H a cover, positive towards the previous
 * albums). The flat fallback keeps both in its slide_menu. */
static struct {
    int value, off;
} cfpos __attribute__((section(".scratch")));

/* A position save is small but fsyncs the card; never run that from page destruction on the UI thread. */
static struct {
    unsigned mutex[8]; /* zero-filled pthread_mutex_t, as in patch/shuffle.c */
    int running, pending;
    unsigned key;
} cf_position_job __attribute__((section(".scratch"), aligned(8)));

/* Visibility and hit-testing together. This AWTK build's hit test (widget_find_target_default
 * 0x6747d4, widget_on_pointer_down_children 0x6714ac) only checks flags & 9 -- enable (bit 0) and
 * sensitive (bit 3) -- and never visible (bit 2), so a hidden widget still takes the touches over
 * its rectangle. Everything this page hides is therefore made insensitive as well. */
static void show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The whole frame is due for a repaint: the shelf moved or its album changed. AWTK repaints only the dirty
 * rectangles (canvas_begin_frame 0x6447b4 clips the canvas to them, canvas_set_clip_rect), and the stock
 * slide_menu marks only its own rectangle, CF_VIEW_W x CF_VIEW_H, when its xoffset or value changes
 * (slide_menu_set_prop 0x613c94 and slide_menu_set_value 0x613a1c -> widget_invalidate 0x668d9c), which is
 * not the landscape frame: without this only that part of the frame changed on the screen. The touch layer
 * is the frame's size in both modes. */
static void redraw(void) {
    if (cf.input) widget_invalidate_force(cf.input, (void *)0);
}

static unsigned album_count(void) { return cf.albums ? cf.count : 0; }
static int abs_i(int v) { return v < 0 ? -v : v; }
static int clamp_i(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }
static void *album_at(unsigned i) { return i < album_count() ? cc_row(cf.albums, cf.order, i) : (void *)0; }

/* The All albums card: the "All songs" row the stock artist query appends (getAlbumByArtist). */
static int is_card(void *r) { return cf.scoped && r && I(r, REC_ID) == ID_ALL_SONGS; }

/* The artist has songs: the stock list ended with the All songs row (load_artist keeps cf.albums whole, also when the card is dropped from the shelf). An
 * artist's page only: songs_open_artist runs the artist queries (a composer's would be 0xf005 / 0xff02 -> 0xff14). */
static int has_songs(void) {
    unsigned n = cf.scoped && cf.scope == CLASS_ARTISTS && cf.albums ? deque_size(cf.albums) : 0;
    return n && I(deque_at(cf.albums, n - 1), REC_ID) == ID_ALL_SONGS;
}

static int is_nav_album(void *r) { return r && I(r, REC_ID) == CF_NAV_ALBUM_ID; }

static const char *nav_album_artist(const sb_song_t *song) {
    return song->album_artist[0] ? song->album_artist : song->artist;
}

static const char *local_album_artist(void *record) {
    const char *album_artist = cc_str(record, REC_ALBUM_ARTIST);
    return *album_artist ? album_artist : cc_str(record, REC_ARTIST);
}

static unsigned cf_text_hash(unsigned h, const char *s) {
    unsigned i;
    if (!s) s = "";
    for (i = 0; s[i]; ++i) {
        unsigned c = (unsigned char)s[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        h = (h ^ c) * 16777619u;
    }
    return h;
}

static unsigned cf_album_hash(const char *artist, const char *album) {
    unsigned h = cf_text_hash(2166136261u, artist);
    h = (h ^ 0xffu) * 16777619u;
    h = cf_text_hash(h, album);
    return h ? h : 1u;
}

static unsigned key_at(unsigned i);

static const char *cf_art_url(unsigned i, char *cache, char *remote) {
    void *r = album_at(i);
    unsigned key;
    const char *file;
    if (!r || is_card(r)) return (const char *)0;
    if (is_nav_album(r)) {
        unsigned row = cf.order ? cf.order[i] : i;
        const sb_song_t *song = row >= cf.local_count && row < MAX_ALBUMS && cf.nav_album_art
                                    ? cf.nav_album_art[row - cf.local_count]
                                    : (const sb_song_t *)0;
        return sb_library_cover_url(song, remote, 512) > 0 ? remote : (const char *)0;
    }
    key = key_at(i);
    file = cc_url(cache, key);
    if (file) return file;
    if (cf.nav_art && cf.order && cf.order[i] < cf.local_count && cf.nav_art[cf.order[i]])
        return sb_library_cover_url(cf.nav_art[cf.order[i]], remote, 512) > 0 ? remote : (const char *)0;
    if (cf.nav_art && !cf.order && i < cf.local_count && cf.nav_art[i])
        return sb_library_cover_url(cf.nav_art[i], remote, 512) > 0 ? remote : (const char *)0;
    return (const char *)0;
}

/* Album i's cache key; 0 (the card) has no art. */
static unsigned key_at(unsigned i) {
    void *r = album_at(i);
    if (!r || is_card(r)) return 0;
    return cf.keys ? cf.keys[cf.order ? cf.order[i] : i] : cc_album_key(r); /* (the keys are by stock row) */
}

static void cf_nav_release(void) {
    free(cf.nav_slots);
    cf.nav_slots = (cf_album_slot_t *)0;
    cf.nav_slot_cap = 0;
    free(cf.nav_art);
    cf.nav_art = (const sb_song_t **)0;
    free(cf.nav_album_art);
    cf.nav_album_art = (const sb_song_t **)0;
    sb_library_index_close(&cf.nav_index);
    cf.nav_cursor = cf.nav_total = 0;
    cf.nav_scanning = 0;
}

/* The cache is built by the shared worker (patch/covercache.c, cc_build_*): its thread touches no widget, deque or
 * image manager; this page only polls its counters from its own timer. */
static void stop_timer(void) {
    if (cf.timer) timer_remove(cf.timer);
    cf.timer = 0;
}

/* This page's job set released: a running worker is cancelled (joined if it has finished, else left to exit on its own, cc_build_stop). */
static void build_end(void) {
    if (cf.owns) cc_build_stop();
    cf.owns = 0;
}

static void fx_close(void) {
    if (fx.load_timer) timer_remove(fx.load_timer);
    if (fx.frame) bitmap_destroy(fx.frame);
    free(fx.tex);
    memset(&fx, 0, sizeof fx);
}

/* The page's shelf now: the portrait one, or the landscape one turned a quarter; in Light Mode the same over paper (bg: the covers fade towards it, as on the Pod's white
 * Cover Flow). */
static const cfg_t *shelf(void) {
    static cfg_t lit __attribute__((section(".scratch")));
    const cfg_t *g = cf.land ? &cf_land : &cf_portrait;
    unsigned i;
    if (!pal_light()) return g;
    for (i = 0; i < sizeof lit / sizeof(int); ++i)
        ((int *)&lit)[i] = ((const int *)g)[i]; /* (a struct copy would call memcpy) */
    lit.bg = LIGHT_PAPER * 0x010101u;
    return &lit;
}

/* An opaque frame bitmap for g: its logical w x h, or h x w when it is turned. */
static void *frame_new(const cfg_t *g) {
    int pw = g->rot ? g->h : g->w, ph = g->rot ? g->w : g->h;
    void *b = bitmap_create_ex(pw, ph, pw * 4, BITMAP_RGBA8888);
    if (b) *(unsigned short *)((char *)b + BITMAP_FLAGS) |= 1; /* OPAQUE: every pixel is */
    return b;
}

/* The frame and every texture at once, or neither: the flat covers then stand in. */
static int fx_open(const cfg_t *g) {
    unsigned *placeholder;
    int i;
    memset(&fx, 0, sizeof fx);
    fx.frame = frame_new(g);
    fx.tex = fx.frame ? calloc((CF_SLOTS + 1) * CF_TEXELS, 4) : (unsigned *)0;
    if (!fx.tex) {
        fx_close();
        return 0;
    }
    placeholder = fx.tex + CF_SLOTS * CF_TEXELS;
    for (i = 0; i < CF_TEXELS; ++i) placeholder[i] = 0xff2b2b2bu; /* until the theme image loads */
    fx.dir = 1;
    return 1;
}

#define PLACE (fx.tex + CF_SLOTS * CF_TEXELS) /* the placeholder texture */

/* ---------------------------------------------------------------------------
 * The shelf's position. Depth mode keeps it in cfpos and stock is not involved: the stock slide_menu
 * lays out every one of its children on each xoffset or value change (slide_menu_set_prop 0x613c94 ->
 * widget_layout_children 0x656d1c, slide_menu_set_value 0x6139fc), O(albums) per drag step, so depth
 * mode has none. The flat fallback's covers are that slide_menu's image children, so it keeps driving
 * the stock widget through its public properties ("value", "xoffset", "h"; no field offset pinned).
 */
static void show_album(void);

static int depth(void) { return fx.frame != (void *)0; }
static int shelf_up(void) { return depth() ? cf.input != (void *)0 : cf.slide != (void *)0; }
static int stride(void) { return depth() ? CF_VIEW_H : widget_get_prop_int(cf.slide, "h", CF_VIEW_H); }
static int offset(void) { return depth() ? cfpos.off : widget_get_prop_int(cf.slide, "xoffset", 0); }
static int value(void) { return depth() ? cfpos.value : widget_get_prop_int(cf.slide, "value", 0); }
static int count(void) { return depth() ? (int)album_count() : (int)widget_count_children(cf.slide); }

static __attribute__((noinline)) void set_offset(int off) {
    if (depth())
        cfpos.off = off;
    else
        widget_set_prop_int(cf.slide, "xoffset", off);
    redraw();
}

/* A new committed album (v differs from value()): the captions follow. */
static __attribute__((noinline)) void set_value(int v) {
    if (!depth()) {
        slide_menu_set_value(cf.slide, v); /* EVT_VALUE_CHANGED -> on_changed -> show_album */
        return;
    }
    cfpos.value = v;
    show_album();
}

static int floor_div(int a, int b) { /* floor division, b > 0 */ return a / b - (a % b < 0); }

/* The visual position from the committed album and the live drag/animation offset. The stock commit
 * is value - round(xoffset / item width), the item width being the slide_menu's height (its delta
 * index @0x612360), so the continuous position is p = value - offset / stride: a positive offset (a
 * drag to the right) walks back towards the previous album. Depth mode keeps the same units. c gets
 * the centre album of n and frac (16.16, -1/2 to under 1/2) how far past it the shelf stands, the
 * renderer's sign. */
static int visual(int n, int *c, int *frac) {
    int s = stride(), d = offset(), q;
    if (n <= 0 || s <= 0) return 0;
    q = floor_div(2 * d + s, 2 * s); /* round(d / s) */
    *c = clamp_i(
        value() - q, 0,
        n - 1); /* the shelf has ends: past one (the overscroll, under half a cover) the end cover stays the centre */
    *frac = ((value() - *c) * s - d) * CF_ONE / s; /* p - c */
    return s;
}

/* ---------------------------------------------------------------------------
 * Textures. Paint uses only what is resident (fx_ring) and never touches a file: the placeholder stands
 * in for a cover not decoded yet, and a page-owned timer (on_load, UI thread: the stock image calls are
 * not known to be thread-safe, so the worker never makes them) decodes one wanted cover per callback,
 * nearest first, then the next one in the direction of travel; the slot reused is the one farthest from
 * the centre that is not wanted, so the cover just left behind survives a reversal. An artist's shelf
 * wants nothing past its ends. Each decode still stalls the UI thread for its length (not measured on
 * the device yet; measure before moving decoding to a worker).
 */
static int around(int c, int k, int n) { /* album c + k of n; -1 past the shelf's ends (every shelf has them) */
    int a = c + k;
    return a >= 0 && a < n ? a : -1;
}

/* The k-th album wanted around c, nearest first: c, then each ring distance ahead of the travel then
 * behind it, then the next one ahead; -1 for none. */
static int wanted(int c, int n, int k) {
    if (k == 0) return around(c, 0, n);
    if (k < CF_RING) return around(c, (k + 1) / 2 * (k & 1 ? fx.dir : -fx.dir), n);
    return k == CF_RING ? around(c, (CF_REACH + 1) * fx.dir, n) : -1;
}

static int resident(int a) { /* the slot holding album a, or -1 */
    int i;
    for (i = 0; i < CF_SLOTS; ++i)
        if (fx.album[i] == a + 1) return i;
    return -1;
}

static int distance(int a, int c) { /* along the shelf */ return abs_i(a - c); }

/* Album a decoded into a free slot, else into the farthest unwanted one (CF_SLOTS > CF_WANTED: there is one). */
static void fx_load(int a, int c, int n) {
    char url[80], remote[512];
    const char *file;
    int i, k, far = -1, slot = -1;
    for (i = 0; i < CF_SLOTS; ++i) {
        int b = fx.album[i] - 1, keep = 0, d;
        if (b < 0) {
            slot = i;
            break;
        }
        for (k = 0; k < CF_WANTED; ++k) keep |= wanted(c, n, k) == b;
        d = distance(b, c);
        if (!keep && d > far) far = d, slot = i;
    }
    if (slot < 0) return;
    fx.album[slot] = a + 1;
    file = cf_art_url((unsigned)a, url, remote);
    fx.art[slot] = file && cc_decode(cf.win, file, 1, ART_SIZE, 0, fx.tex + slot * CF_TEXELS)
                       ? fx.tex + slot * CF_TEXELS
                       : PLACE; /* no art, or no cache file yet */
}

/* Each ring slot's texture at centre c from what is resident (the placeholder for a cover not decoded
 * yet, 0 past an artist's ends); 1 if a wanted cover is missing. Never loads. */
static int fx_ring(int c, int n, const unsigned *ring[CF_RING]) {
    int j, k, missing = 0;
    for (j = 0; j < CF_RING; ++j) {
        int a = around(c, j - CF_REACH, n), i = a < 0 ? -1 : resident(a);
        ring[j] = a < 0 ? (const unsigned *)0 : i < 0 ? PLACE : fx.art[i];
    }
    for (k = 0; k < CF_WANTED; ++k) {
        int a = wanted(c, n, k);
        if (a >= 0 && resident(a) < 0) missing = 1;
    }
    return missing;
}

/* Up to budget wanted covers decoded at the shelf's current position, the frame redrawn if any came;
 * 1 if more are wanted. */
static int fx_fill(int budget) {
    int c, frac, n = count(), k, done = 0, more = 0;
    if (!depth() || !visual(n, &c, &frac)) return 0;
    for (k = 0; k < CF_WANTED; ++k) {
        int a = wanted(c, n, k);
        if (a < 0 || resident(a) >= 0) continue;
        if (done == budget) {
            more = 1;
            break;
        }
        fx_load(a, c, n);
        ++done;
    }
    if (done) {
        fx.drawn = 0;
        redraw();
    }
    return more;
}

static int on_load(const void *unused) {
    (void)unused;
    fx.load_timer = 0;
    if (cf.fg && cf.screen == CF_COVERS && shelf_up() && fx_fill(1))
        fx.load_timer = timer_add(on_load, (void *)0, LOAD_MS);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Landscape's overlay: what the frame carries besides the covers, drawn into the physical bitmap
 * through the same quarter-turn map (logical (x, y) is the pixel at row x, column CFL_H - 1 - y).
 * The captions use the page's font straight from the canvas (widget_prepare_text_style puts the
 * caption label's font and size there; canvas_draw_text @0x645348 reads them the same way): each
 * glyph's 8-bit alpha is blended in turned, positioned as the canvas does, x + glyph.x,
 * y + glyph.y + ascent, advancing by the glyph's advance + 1 (4 for a missing glyph).
 */
#define CAP_MAX 64 /* wide chars kept per caption, the ellipsis included */

typedef struct {
    short x, y;
    unsigned short w, h, advance;
    unsigned char format, pitch;
    const unsigned char *data;
} glyph_t;

static unsigned mix(unsigned v, unsigned c, unsigned a) { /* c over v by a (of 255) */
    unsigned w = a + (a >> 7);
    return 0xff000000u | (((v & 0xff00ffu) * (256 - w) + (c & 0xff00ffu) * w) >> 8 & 0xff00ffu) |
           (((v & 0xff00u) * (256 - w) + (c & 0xff00u) * w) >> 8 & 0xff00u);
}

/* The physical pixel of the logical (x, y), 0 outside the frame. */
static unsigned *turned(unsigned *d, int pitch, int x, int y) {
    return (unsigned)x < CFL_W && (unsigned)y < CFL_H ? d + x * pitch + (CFL_H - 1 - y) : (unsigned *)0;
}

static int advance(void *font, unsigned size, unsigned ch, glyph_t *g) {
    return font_get_glyph(font, ch, size, g) ? 4 : g->advance + 1;
}

/* The wide string s (len chars) with its line top at y, centred in CFL_CAP_W, cut with an ellipsis
 * when it is wider; colour rgb. */
static void caption(unsigned *d, int pitch, void *canvas, unsigned *s, int len, int y, unsigned rgb) {
    void *font = *(void **)((char *)canvas + CANVAS_FONT);
    unsigned size = *(unsigned short *)((char *)canvas + CANVAS_FONT_SIZE);
    int adv[CAP_MAX], i, w = 0, x, ascent;
    short vm[4];
    glyph_t g;
    if (!font || !len) return;
    for (i = 0; i < len; ++i) w += adv[i] = advance(font, size, s[i], &g);
    if (w > CFL_CAP_W) {
        int ell = advance(font, size, ELLIPSIS, &g);
        for (w = 0, i = 0; i < len && w + adv[i] + ell <= CFL_CAP_W; ++i) w += adv[i];
        s[i] = ELLIPSIS, adv[i] = ell, len = i + 1, w += ell;
    }
    font_get_vmetrics(vm, font, size);
    ascent = vm[0];
    x = (CFL_W - w) / 2;
    for (i = 0; i < len; x += adv[i++]) {
        int r, c;
        if (font_get_glyph(font, s[i], size, &g) || !g.data || g.format != GLYPH_FORMAT_ALPHA) continue;
        for (r = 0; r < g.h; ++r)
            for (c = 0; c < g.w; ++c) {
                unsigned a = g.data[r * g.w + c];
                unsigned *px = a ? turned(d, pitch, x + g.x + c, y + g.y + ascent + r) : (unsigned *)0;
                if (px) *px = mix(*px, rgb, a);
            }
    }
}

/* One caption line from a UTF-8 string, in the label's own size (the canvas takes its style). */
static void caption_line(unsigned *d, int pitch, void *canvas, void *label, const char *text, int y, unsigned rgb) {
    unsigned s[CAP_MAX];
    unsigned n = 0, len = 0;
    while (text[n] && n < 255) ++n;
    widget_prepare_text_style(label, canvas);
    tk_utf8_to_utf16_ex(text, n, s, CAP_MAX - 1);
    s[CAP_MAX - 1] = 0; /* never read past the array, whatever the conversion leaves */
    while (s[len]) ++len;
    caption(d, pitch, canvas, s, (int)len, y, rgb);
}

/* The centre album's two caption lines, in the labels' own sizes and colours (tools/pod_ui.py). */
static void captions_land(unsigned *d, int pitch, void *canvas) {
    void *r = album_at((unsigned)cf.album);
    if (!r) return;
    caption_line(d, pitch, canvas, cf.name, is_card(r) ? TR("All albums") : cc_str(r, REC_ALBUM), CFL_ALBUM_Y,
                 ui_ink(0xffffffffu) & 0xffffffu);
    caption_line(d, pitch, canvas, cf.artist, cc_str(r, REC_ARTIST), CFL_ARTIST_Y, ui_ink(0xffaaaaaau) & 0xffffffu);
}

/* The touch layer's EVT_AFTER_PAINT: the frame, from resident textures only (an artist's shelf
 * stops at both ends, q2-pod coverflow_bounded: no repeats); missing covers go to the loader. */
static int on_paint(void *ctx, void *e) {
    int c, frac, n, r[4];
    const unsigned *ring[CF_RING];
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    const cfg_t *g = shelf();
    (void)ctx;
    if (!cf.fg || !canvas || !depth() || cf.screen != CF_COVERS || !shelf_up()) return RET_OK;
    n = count();
    if (!visual(n, &c, &frac)) return RET_OK;
    if (fx.seen && c != fx.seen - 1) fx.dir = c < fx.seen - 1 ? -1 : 1; /* the way it went, for the prefetch */
    fx.seen = c + 1;
    if (fx_ring(c, n, ring) && !fx.load_timer) fx.load_timer = timer_add(on_load, (void *)0, LOAD_MS);
    if (!fx.drawn || c != fx.c || frac != fx.frac) {
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(fx.frame);
        int pitch = (int)(bitmap_get_line_length(fx.frame) / 4);
        if (!d) return RET_OK;
        coverflow_render(g, d, pitch, frac, ring);
        if (cf.land) captions_land(d, pitch, canvas);
        bitmap_unlock_buffer(fx.frame);
        fx.c = c, fx.frac = frac, fx.drawn = 1;
    }
    r[0] = 0, r[1] = 0, r[2] = g->rot ? g->h : g->w, r[3] = g->rot ? g->w : g->h;
    canvas_draw_image(canvas, fx.frame, r, r);
    return RET_OK;
}

/* Flat fallback (no depth frame): the children are stock images, real art only near the centre.
 * The picture is set only when it changes, so a commit costs one property read per child and a
 * file check for the few covers in the window (q2-pod's cover()). */
static void flat_cover(void *img, unsigned i, int near) {
    char url[80], remote[512];
    const char *want = PLACEHOLDER;
    const char *file = near ? cf_art_url(i, url, remote) : (const char *)0;
    if (file) want = file;
    if (strcmp(widget_get_prop_str(img, "image", ""), want)) image_base_set_image(img, want);
}

/* Album over artist under the covers; the card is All albums over the artist. */
static void captions(void *r) {
    widget_set_text_utf8(cf.name, is_card(r) ? TR("All albums") : cc_str(r, REC_ALBUM));
    widget_set_text_utf8(cf.artist, cc_str(r, REC_ARTIST));
}

static void show_album(void) {
    unsigned n = album_count(), c = (unsigned)value();
    void *r = album_at(c);
    if (!r) return;
    cf.album = (int)c;
    if (!cf.scoped) cf.saved_album = cc_album_key(r);
    captions(r);
    if (cf.land) fx.drawn = 0; /* the captions are part of the frame: draw it again */
    redraw();
    if (!depth()) {
        unsigned i;
        for (i = 0; i < n; ++i) {
            unsigned d = i > c ? i - c : c - i;
            flat_cover(widget_get_child(cf.slide, i), i, d <= ART_NEAR);
        }
    }
}

static int on_changed(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (cf.screen == CF_COVERS) show_album();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch. A transparent view over the covers takes every pointer event in the frame and drives
 * the shelf through set_offset and set_value, so nothing depends on a stock widget's own drag or
 * on clicks reaching its children. A gesture is a tap
 * while the finger stays within TAP_SLOP of where it went down (both axes, the release included);
 * a horizontal drag starts once the finger is DRAG_START along the carousel and no further across,
 * its travel counted from that threshold (no jump), and then moves the shelf with the finger
 * (DRAG_PX per album); a mostly vertical gesture is neither. A release settles: a drag coasts by
 * the fling (the velocity over the last FLING_WINDOW ms, the release included) and eases to a
 * cover, a press that stopped an animation eases to the nearest cover, and a tap is hit-tested
 * by x: the centre cover opens its album, a side cover is brought to the centre. The easing is
 * by elapsed time (1 - (1 - p)^3 over SNAP_BASE_MS + SNAP_ALBUM_MS per album of travel), so a
 * late timer callback does not stretch it, and a nonzero offset always has its timer running.
 * All in the UI thread; the timer is the page's own, removed at destroy.
 */

/* Every shelf has ends (no wrap, as Apple's): an offset of `albums` covers (positive: towards the first album)
 * stays within the albums, so p = value - offset / h never leaves 0..n-1. Past an end only the finger goes, rubber-banded
 * (rubber), and the snap eases back to the bound. */
static int bound(int albums) {
    int v = value(), n = count();
    return clamp_i(albums, v - (n - 1), v);
}

/* The rubber band: past an end the shelf follows the finger at half speed and saturates at OVER_MAX (2/5 of a cover,
 * so the end cover stays the centre: the renderer's offset from the centre stays under 1/2). With x the finger's travel
 * past the end, the shelf shows m * x / (x + 2 m), m = OVER_MAX; unrubber is its inverse (a press that finds the shelf
 * overscrolled picks the travel up where it was). The flat fallback's slide_menu would show its wrapped covers, so it has none. */
static int rubber(int off, int h) {
    int lo = bound(-0x7fff) * h, hi = bound(0x7fff) * h, m = h * OVER_NUM / OVER_DEN, x;
    if (!depth()) return clamp_i(off, lo, hi);
    if (off > hi)
        x = off - hi, off = hi + m * x / (x + 2 * m);
    else if (off < lo)
        x = lo - off, off = lo - m * x / (x + 2 * m);
    return off;
}

static int unrubber(int off, int h) {
    int lo = bound(-0x7fff) * h, hi = bound(0x7fff) * h, m = h * OVER_NUM / OVER_DEN, s;
    if (!depth() || h <= 0) return off;
    if (off > hi)
        s = off - hi, off = hi + (s >= m ? 64 * m : 2 * m * s / (m - s));
    else if (off < lo)
        s = lo - off, off = lo - (s >= m ? 64 * m : 2 * m * s / (m - s));
    return off;
}

static void snap_stop(void) {
    if (cf.snap_timer) timer_remove(cf.snap_timer);
    cf.snap_timer = 0;
}

/* The offset reached its target: commit it as the stock widget does (offset back to 0 and
 * value - offset / h; the target is within the shelf), and the captions follow. */
static void commit(void) {
    int h = stride(), n = count(), q, v, now;
    if (n <= 0 || h <= 0) return;
    q = cf.snap_to / h;
    now = value();
    v = clamp_i(now - q, 0, n - 1);
    set_offset(0);
    if (v != now)
        set_value(v);
    else
        show_album();
}

/* The eased offset at time now: 1 - (1 - p)^3 of the way, p the elapsed share of snap_ms; exactly
 * the target once the time is up. */
static int eased(unsigned now) {
    unsigned el = now - cf.snap_t0;
    int q, e;
    if (el >= (unsigned)cf.snap_ms) return cf.snap_to;
    q = 256 - (int)(el * 256 / (unsigned)cf.snap_ms); /* 1 - p, of 256 */
    e = 4096 - (q * q * q >> 12); /* 1 - (1 - p)^3, of 4096 */
    return cf.snap_from + (cf.snap_to - cf.snap_from) * e / 4096;
}

static void snap_land(void) { /* on the target: commit it */
    cf.snap_timer = 0;
    set_offset(cf.snap_to);
    commit();
}

static int on_snap(const void *unused) {
    int off;
    (void)unused;
    cf.snap_timer = 0;
    if (!cf.fg || cf.screen != CF_COVERS || !shelf_up()) return RET_OK;
    off = eased(time_now_ms());
    if (off == cf.snap_to) {
        snap_land();
        return RET_OK;
    }
    set_offset(off);
    cf.snap_timer = timer_add(on_snap, (void *)0, SNAP_MS);
    if (!cf.snap_timer) snap_land(); /* no timer: finish now rather than leave the shelf between covers */
    return RET_OK;
}

/* Ease the offset from where it is to `albums` covers away from the committed one (positive:
 * towards the previous albums, as a drag to the right does). */
static void snap(int albums) {
    int h = stride(), d;
    snap_stop();
    cf.snap_from = offset();
    cf.snap_to = bound(albums) * h;
    d = abs_i(cf.snap_to - cf.snap_from);
    if (!d || h <= 0) {
        snap_land();
        return;
    }
    cf.snap_ms = SNAP_BASE_MS + SNAP_ALBUM_MS * d / h;
    if (cf.snap_ms > SNAP_MAX_MS) cf.snap_ms = SNAP_MAX_MS;
    cf.snap_t0 = time_now_ms();
    cf.snap_timer = timer_add(on_snap, (void *)0, SNAP_MS);
    if (!cf.snap_timer) snap_land();
}

static void open_album(int index);

/* x along the carousel, y across it: portrait takes the event's numbers as they come; landscape
 * turns the point back by the frame's map (logical (x, y) is physical (CFL_H - 1 - y, x)). */
static void where(void *e, int *x, int *y);

static void tap(int x) {
    const cfg_t *g = shelf();
    pose_t p1;
    int d = x - g->cx, a, b, far;
    pose(g, CF_ONE, &p1);
    a = project(g, &p1, -8 * g->art), b = project(g, &p1, 8 * g->art);
    far = 16 * abs_i(d) > (a > b ? a : b) ? 2 : 1; /* past the first cover's drawn outer edge (1/16 px) */
    if (abs_i(d) < g->art / 2) { /* the centre cover */
        if (!offset()) open_album(value());
        return;
    }
    snap(d < 0 ? far : -far); /* a side cover comes to the centre */
}

static int pe(void *e, int field) { return *(int *)((char *)e + field); }

static void where(void *e, int *x, int *y) {
    int p[2];
    p[0] = pe(e, PE_X), p[1] = pe(e, PE_Y);
    if (cf.land) {
        widget_to_local(cf.input, p);
        *x = p[1], *y = CFL_H - 1 - p[0];
    } else {
        *x = p[0], *y = p[1];
    }
}

/* Finger travel per album along the carousel. */
static int drag_px(void) { return cf.land ? CFL_DRAG_PX : DRAG_PX; }

/* The finger at (x, y) at time t, from a move or the release: the excursion, the drag's start (its
 * travel counted from the threshold, so the shelf neither jumps by it nor loses a sparse event's
 * travel beyond it), the shelf under the finger, the sample. */
static void track(int x, int y, int t) {
    int dx = x - cf.down_x, dy = y - cf.down_y;
    if (abs_i(dx) > cf.reach) cf.reach = abs_i(dx);
    if (abs_i(dy) > cf.reach) cf.reach = abs_i(dy);
    if (!cf.active && abs_i(dx) >= DRAG_START && abs_i(dx) >= abs_i(dy))
        cf.active = 1, cf.origin = cf.down_x + (dx > 0 ? DRAG_START : -DRAG_START);
    if (cf.active) {
        int h = stride(), off = cf.base_off + (x - cf.origin) * h / drag_px();
        set_offset(rubber(off, h));
    }
    cf.sample = (cf.sample + 1) % CF_SAMPLES;
    cf.sx[cf.sample] = x, cf.st[cf.sample] = t;
    if (cf.samples < CF_SAMPLES) ++cf.samples;
}

/* The fling, in offset units: the finger's velocity from the oldest sample of the last FLING_WINDOW
 * ms to the newest (none but the newest: it rested, no fling), coasting FLING_MS, at most three
 * covers. Kept in offset units to the end, not rounded to whole finger pixels per ms. */
static int fling(int h) {
    int newest = cf.sample, old = newest, k, dt;
    for (k = 1; k < cf.samples; ++k) {
        int j = (newest - k + CF_SAMPLES) % CF_SAMPLES;
        if (cf.st[newest] - cf.st[j] > FLING_WINDOW) break;
        old = j;
    }
    dt = cf.st[newest] - cf.st[old];
    if (dt <= 0) return 0;
    return clamp_i((cf.sx[newest] - cf.sx[old]) * FLING_MS * h / (dt * drag_px()), -3 * h, 3 * h);
}

static int on_pointer(void *ctx, void *e) {
    int type, x, y, t;
    (void)ctx;
    if (!cf.fg || !e || !shelf_up() || cf.screen != CF_COVERS) return RET_OK;
    type = pe(e, 0), t = pe(e, EV_TIME);
    where(e, &x, &y);
    if (type == EVT_POINTER_DOWN) {
        cf.interrupted = cf.snap_timer != 0; /* the shelf stops where the animation had it */
        snap_stop();
        cf.dragging = 1, cf.active = cf.reach = 0;
        cf.down_x = x, cf.down_y = y, cf.base_off = unrubber(offset(), stride());
        cf.sample = 0, cf.samples = 1, cf.sx[0] = x, cf.st[0] = t;
        widget_grab(cf.covers, cf.input); /* moves and the release come here wherever they go */
    } else if (type == EVT_POINTER_MOVE && cf.dragging) {
        track(x, y, t);
    } else if ((type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) && cf.dragging) {
        int h = stride(), off;
        if (type == EVT_POINTER_UP) track(x, y, t); /* the release's own travel counts */
        cf.dragging = 0;
        widget_ungrab(cf.covers, cf.input);
        if (type == EVT_POINTER_UP && !cf.active && !cf.interrupted && cf.reach <= TAP_SLOP) {
            tap(x);
            return RET_OK;
        }
        off = offset() + (type == EVT_POINTER_UP && cf.active && h > 0 ? fling(h) : 0);
        snap(h > 0 ? (off >= 0 ? off + h / 2 : off - h / 2) / h : 0); /* the nearest cover to where it is going */
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Landscape. The Settings > Library > Landscape switch chooses the page's presentation, kept in
 * LANDSCAPE_FILE (like the Albums view's), and the page opens in it. The navbar stays as it is in both (Back, the
 * title, Now Playing); in landscape the covers view and the touch layer are the body under it, CFL_Y down and
 * CFL_W high, the caption labels are hidden (the frame carries the captions), and the frame bitmap is the
 * body-sized one. Without a depth frame the covers are flat and portrait, whatever the setting says.
 */
static int use_land(void) { return set_read(LANDSCAPE_FILE, 0) == '1'; }

/* The setting for the Landscape switch (patch/m1plus.c). */
int coverflow_landscape(void) { return use_land(); }

/* Flip it (atomic write, patch/home.c); the new state, or -1 when it could not be saved. */
int coverflow_landscape_toggle(void) {
    int next = !use_land();
    return home_write_atomic(LANDSCAPE_FILE, LANDSCAPE_TMP, next ? "1\n" : "0\n") == 0 ? next : -1;
}

/* The widgets for the current mode. */
static void layout(void) {
    int on = cf.land;
    widget_set_visible(cf.name, !on, 0); /* still insensitive: only the visibility changes */
    widget_set_visible(cf.artist, !on, 0);
    widget_move(cf.covers, 0, on ? CFL_Y : CF_COVER_Y);
    widget_resize(cf.covers, SCREEN_W, on ? CFL_W : CF_VIEW_H);
    widget_resize(cf.input, SCREEN_W, on ? CFL_W : CF_VIEW_H);
}

/* The artist page's Songs button (the capsule's left cap at NAV_VIEW_X, as the Artists page's switch): shown, Now Playing becomes the capsule's right cap
 * (the asset has the disc, which the main page and a composer's page keep); the title ends before the slot. */
static void artist_nav(void) {
    void *title = widget_lookup(cf.win, "label_title", 1), *np = widget_lookup(cf.win, "btn_backtoplayer", 1);
    if (!cf.scoped) return;
    show(cf.songs, has_songs());
    if (has_songs() && np) {
        widget_set_prop_str(np, "style:normal:icon", "ah_nav_play");
        widget_set_prop_str(np, "style:over:icon", "ah_nav_play");
        widget_set_prop_str(np, "style:pressed:icon", "ah_nav_play_down");
    }
    if (title)
        widget_resize(title, NAV_VIEW_X - widget_get_prop_int(title, "x", 0), widget_get_prop_int(title, "h", 0));
}

/* The covers screen: the depth frame over a touch layer, the shelf's position in cfpos; or, when the
 * frame could not be allocated, the flat fallback: a stock slide_menu with one stock image per album
 * (it commits an index; the touch layer drives it, bounded). */
static void to_covers(void) {
    cf.screen = CF_COVERS;
    show(cf.status, 0);
    show(cf.cancel, 0);
    show(cf.covers, 1); /* the captions are never hidden, and stay insensitive (the asset): they
                         * lie over the frame's black bottom rows, so its touch layer gets the touch */
    artist_nav();
    if (!cf.built) {
        unsigned n = album_count(), i;
        cf.built = 1;
        cf.land = use_land();
        if (!fx_open(shelf())) { /* no frame, no landscape: the flat covers */
            cf.land = 0;
            cf.slide =
                widget_factory_create_widget(widget_factory(), "slide_menu", cf.covers, 0, 0, CF_VIEW_W, ART_SIZE);
            if (!cf.slide) return;
            for (i = 0; i < n; ++i) {
                void *img = image_create(cf.slide, 0, 0, 0, 0);
                if (!img) break;
                image_set_draw_type(img, IMAGE_SCALE_AUTO);
            }
            widget_set_sensitive(cf.slide, 0); /* the input layer drives it; it takes no touch */
            widget_on(cf.slide, EVT_VALUE_CHANGED, on_changed, (void *)0);
        }
        cf.input = widget_factory_create_widget(widget_factory(), "view", cf.covers, 0, 0, CF_VIEW_W, CF_VIEW_H);
        if (cf.input) {
            /* fully transparent, in the string form the assets use */
            widget_set_prop_str(cf.input, "style:normal:bg_color", "#00000000");
            widget_set_prop_str(cf.input, "style:normal:border_color", "#00000000");
            widget_on(cf.input, EVT_POINTER_DOWN, on_pointer, (void *)0);
            widget_on(cf.input, EVT_POINTER_MOVE, on_pointer, (void *)0);
            widget_on(cf.input, EVT_POINTER_UP, on_pointer, (void *)0);
            widget_on(cf.input, EVT_POINTER_ABORT, on_pointer, (void *)0);
            widget_on(cf.input, EVT_AFTER_PAINT, on_paint, (void *)0); /* the frame, on top */
        }
        if (cf.land) layout();
        /* The stock slide_menu starts on item 1, not 0 (its constructor stores 1 in `value`,
         * @0x613970), so a page that wants the first album, or has only one, must set it: the
         * artist's Cover Flow opened on its second album and, with a single album, on item 1 of 1
         * whose captions were then never set. Depth mode starts where it is told too. */
        if (depth()) {
            cfpos.value = cf.album, cfpos.off = 0;
            cc_decode(cf.win, PLACEHOLDER, 0, ART_SIZE, 0, PLACE); /* the theme image */
            /* only the centre cover now (one decode in the open call); the ring and the next one ahead follow, one per
             * on_load tick. A refused timer is retried by the first paint (fx_ring finds covers missing). */
            if (fx_fill(1) && !fx.load_timer) fx.load_timer = timer_add(on_load, (void *)0, LOAD_MS);
        } else if (value() != cf.album) {
            set_value(cf.album);
        }
    }
    show_album();
    widget_invalidate_force(cf.win, (void *)0);
}

/* ---------------------------------------------------------------------------
 * The album view is our album page (patch/albumpage.c), or the plain stock albuminfo_page when it does not open. A tap on the
 * centre cover does what a stock Albums row does (cc_open_album, patch/covercache.c, which the Albums grid shares): the stock
 * list goes back into *pdeq_showlist, the cover-task list is rebuilt and the cover thread released, and the page opens on
 * the row. Both queries repeat on every open. An artist's All albums card is not an album: it opens our Songs page on
 * all the artist's songs, as the Songs button does.
 */
static void open_album(int index) {
    void *r = album_at((unsigned)index);
    if (!r) return;
    snap_stop();
    cf.album = index;
    if (is_card(r) && has_songs() && songs_open_artist(deque_at(cf.artist_row, 0)) != -1) return;
    if (is_nav_album(r)) {
        (void)songs_open_nav_filter(SB_LIBRARY_FILTER_ALBUM, cc_str(r, REC_ALBUM), cc_str(r, REC_ALBUM_ARTIST));
        return;
    }
    if (!cf.scoped) cf.saved_album = cc_album_key(r);
    cc_open_album(cf.scoped ? cf.artist_row : (void *)0, cf.scope,
                  (int)(cf.order ? cf.order[index] : (unsigned)index)); /* the stock row */
}

/* The artist page's Songs button: our Songs page on all the artist's songs, so Back returns here. A page that did not open falls back to the stock page on the
 * All songs row, the last of the stock list (what the All albums card does when ours does not open). */
static int on_songs(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (cf.screen != CF_COVERS || !album_count() || !has_songs())
        return RET_OK; /* (no albums: the page shows no covers and no button) */
    snap_stop();
    if (songs_open_artist(deque_at(cf.artist_row, 0)) == -1)
        cc_open_album(cf.artist_row, cf.scope, (int)deque_size(cf.albums) - 1);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Opening: the album list, then art for the albums with no cache file (q2-pod's first-run build;
 * later opens resume where a cancel left off).
 */
/* The centre album's key as 8 lowercase hex digits and a newline, in a file of the card's own (the keys belong to the card's
 * library, so the file stays on it), written by pod_card_write. Only with the card mounted. */
static void position_write(unsigned key) {
    char text[16];
    snprintf(text, sizeof text, "%08x\n", key);
    pod_card_write(CARD_DIR, POSITION_FILE, POSITION_FILE ".tmp", text, 9, (const void *)0, 0);
}

static void *position_worker(void *unused) {
    (void)unused;
    for (;;) {
        unsigned key;
        pthread_mutex_lock(cf_position_job.mutex);
        if (!cf_position_job.pending) {
            cf_position_job.running = 0;
            pthread_mutex_unlock(cf_position_job.mutex);
            return (void *)0;
        }
        key = cf_position_job.key;
        cf_position_job.pending = 0;
        pthread_mutex_unlock(cf_position_job.mutex);
        position_write(key);
    }
}

static void position_save(unsigned key) {
    unsigned long thread; /* pthread_t is an unsigned long in the device's o32 import table */
    int start = 0;
    if (!key) return;
    pthread_mutex_lock(cf_position_job.mutex);
    cf_position_job.key = key;
    cf_position_job.pending = 1;
    if (!cf_position_job.running) cf_position_job.running = start = 1;
    pthread_mutex_unlock(cf_position_job.mutex);
    if (!start) return;
    if (pthread_create(&thread, (void *)0, position_worker, (void *)0)) {
        pthread_mutex_lock(cf_position_job.mutex);
        cf_position_job.running = 0;
        pthread_mutex_unlock(cf_position_job.mutex);
        return; /* the next close can retry; UI navigation never waits on card I/O */
    }
    pthread_detach(thread);
}

/* The saved key: exactly 8 hex digits and an optional newline; anything else, a missing file or the card not mounted is 0. */
static unsigned position_load(void) {
    char text[16];
    unsigned key = 0;
    int fd, n, i;
    if (!pod_card_mounted()) return 0;
    fd = open(POSITION_FILE, O_RDONLY, 0);
    if (fd < 0) return 0;
    n = read(fd, text, sizeof text);
    close(fd);
    if (n == 9 && text[8] == '\n') n = 8;
    if (n != 8) return 0;
    for (i = 0; i < 8; ++i) {
        int c = text[i];
        if (c >= '0' && c <= '9')
            c -= '0';
        else if (c >= 'a' && c <= 'f')
            c -= 'a' - 10;
        else if (c >= 'A' && c <= 'F')
            c -= 'A' - 10;
        else
            return 0;
        key = key << 4 | (unsigned)c;
    }
    return key;
}

static int on_poll(const void *unused) {
    char progress[96];
    (void)unused;
    cf.timer = 0;
    if (!cf.fg) return RET_OK;
    if (cc_build_done() >= cc_build_total()) {
        build_end(); /* the thread has finished: joined and freed */
        to_covers();
        return RET_OK;
    }
    snprintf(progress, sizeof progress, "%s %d/%d", TR("Preparing covers..."), cc_build_done(), cc_build_total());
    widget_set_text_utf8(cf.status, progress);
    cf.timer = timer_add(on_poll, (void *)0, POLL_MS);
    if (!cf.timer) { /* nothing would ever finish this screen: stop here and show what is cached */
        build_end();
        to_covers();
    }
    return RET_OK;
}

static int on_cancel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (cf.screen != CF_PREPARING) return RET_OK;
    stop_timer();
    build_end(); /* what was written stays, the rest is left as it was */
    to_covers();
    return RET_OK;
}

/* The albums, exactly as the stock Albums page lists them, copied (cc_albums) so later stock queries (the
 * album page's) cannot pull them away. They are shown in the Settings > Library > Album Order order (patch/covercache.c;
 * the copy itself keeps the stock order, cf.order maps the shelf to it); a library over MAX_ALBUMS is not shown. */
static int load_albums(void) {
    cf.albums = cc_albums();
    cf.count = cf.albums ? deque_size(cf.albums) : 0;
    cf.local_count = cf.count;
    if (cf.count && cf.count <= MAX_ALBUMS) cf.order = cc_album_order(cf.albums);
    return (int)cf.count;
}

static int open_covers(int n, const char *empty);
static void show_preparing(void);

/* Prepare a bounded album identity map; the actual catalog scan runs in small
 * UI timer slices so opening Cover Flow does not stall the player. */
static int cf_nav_prepare(void) {
    sb_library_index_t index;
    cf_album_slot_t *slots;
    const sb_song_t **art;
    const sb_song_t **album_art;
    unsigned *order, *old_order = cf.order;
    unsigned local = cf.count, total, cap = 1, target, i;
    if (cf.scoped || local > MAX_ALBUMS || sb_library_index_open(&index)) return 0;
    total = index.count + index.dsd_count;
    if (!index.count || total > 100000u) {
        sb_library_index_close(&index);
        return 0;
    }
    target = 2u * MAX_ALBUMS;
    while (cap < target && cap < 0x80000000u) cap <<= 1;
    slots = (cf_album_slot_t *)calloc(cap, sizeof *slots);
    art = local ? (const sb_song_t **)calloc(local, sizeof *art) : (const sb_song_t **)0;
    album_art =
        local < MAX_ALBUMS ? (const sb_song_t **)calloc(MAX_ALBUMS - local, sizeof *album_art) : (const sb_song_t **)0;
    order = (unsigned *)calloc(MAX_ALBUMS, sizeof *order);
    if (!slots || (local && !art) || !order) {
        free(slots), free(art), free(album_art), free(order);
        sb_library_index_close(&index);
        return 0;
    }
    for (i = 0; i < local; ++i) {
        void *r = deque_at(cf.albums, i);
        const char *album = cc_str(r, REC_ALBUM);
        unsigned hash, at;
        order[i] = old_order ? old_order[i] : i;
        if (!r || I(r, REC_ID) == -1 || !*album) continue;
        hash = cf_album_hash(local_album_artist(r), album), at = hash & (cap - 1);
        while (slots[at].hash) at = (at + 1) & (cap - 1);
        slots[at].hash = hash, slots[at].row = i;
    }
    free(old_order);
    cf.order = order;
    cf.nav_index.songs = index.songs;
    cf.nav_index.count = index.count;
    cf.nav_index.dsd_count = index.dsd_count;
    cf.nav_index.mapping_size = index.mapping_size;
    cf.nav_index.mapping = index.mapping;
    cf.local_count = local;
    cf.nav_slots = slots;
    cf.nav_art = art;
    cf.nav_album_art = album_art;
    cf.nav_slot_cap = cap;
    cf.nav_total = total;
    cf.nav_cursor = 0;
    cf.nav_scanning = 1;
    return 1;
}

static int cf_nav_add(const sb_song_t *song) {
    unsigned hash, at, row;
    unsigned rec[REC_SIZE / 4];
    const char *artist = nav_album_artist(song);
    if (sb_library_is_dsd(song) || !song->album[0]) return 0;
    hash = cf_album_hash(artist, song->album), at = hash & (cf.nav_slot_cap - 1);
    while (cf.nav_slots[at].hash) {
        row = cf.nav_slots[at].row;
        {
            void *r = deque_at(cf.albums, row);
            if (cf.nav_slots[at].hash == hash && !cc_nocase(local_album_artist(r), artist) &&
                !cc_nocase(cc_str(r, REC_ALBUM), song->album)) {
                if (song->cover[0]) {
                    if (row < cf.local_count && cf.nav_art && !cf.nav_art[row])
                        cf.nav_art[row] = song;
                    else if (row >= cf.local_count && row < MAX_ALBUMS && cf.nav_album_art) {
                        const sb_song_t *old = cf.nav_album_art[row - cf.local_count];
                        if (!old || !old->cover[0]) cf.nav_album_art[row - cf.local_count] = song;
                    }
                }
                return 0;
            }
        }
        at = (at + 1) & (cf.nav_slot_cap - 1);
    }
    if (cf.count >= MAX_ALBUMS) return 0;
    if (!cf.albums) {
        cf.albums = _create_deque("stSongInfo");
        if (!cf.albums) return -1;
        deque_init(cf.albums);
    }
    memset(rec, 0, sizeof rec);
    *(int *)((char *)rec + REC_ID) = CF_NAV_ALBUM_ID;
    *(char **)((char *)rec + REC_NAME) = (char *)song->album;
    /* stSongInfo owns and frees REC_PATH as a string. Keep mmap-backed art
     * pointers in nav_album_art so deque destruction never frees mapped data. */
    *(char **)((char *)rec + REC_PATH) = (char *)song->id;
    *(char **)((char *)rec + REC_TITLE) = (char *)song->album;
    *(char **)((char *)rec + REC_ALBUM) = (char *)song->album;
    *(char **)((char *)rec + REC_ARTIST) = (char *)artist;
    *(char **)((char *)rec + REC_ALBUM_ARTIST) = (char *)artist;
    *(int *)((char *)rec + REC_TYPE) = 4;
    row = cf.count;
    _deque_push_back(cf.albums, rec);
    if (deque_size(cf.albums) != row + 1) return -1;
    cf.nav_slots[at].hash = hash, cf.nav_slots[at].row = row;
    if (cf.nav_album_art && song->cover[0]) cf.nav_album_art[row - cf.local_count] = song;
    cf.order[row] = row;
    ++cf.count;
    return 1;
}

static void cf_nav_finish(void) {
    if (cf.nav_timer) timer_remove(cf.nav_timer);
    cf.nav_timer = 0, cf.nav_scanning = 0;
    free(cf.nav_slots);
    cf.nav_slots = (cf_album_slot_t *)0, cf.nav_slot_cap = 0;
    (void)open_covers((int)cf.count, "No albums");
}

static int cf_nav_step(const void *unused);

static void cf_nav_schedule(void) {
    if (cf.fg && cf.win && cf.nav_scanning && !cf.nav_timer) {
        cf.nav_timer = timer_add(cf_nav_step, (void *)0, CF_NAV_MS);
        if (!cf.nav_timer) cf_nav_finish();
    }
}

static int cf_nav_step(const void *unused) {
    unsigned end;
    (void)unused;
    cf.nav_timer = 0;
    if (!cf.fg || !cf.nav_scanning || !cf.win) return RET_OK;
    end = cf.nav_cursor + CF_NAV_BATCH;
    if (end < cf.nav_cursor || end > cf.nav_total) end = cf.nav_total;
    while (cf.nav_cursor < end) {
        const sb_song_t *song = &cf.nav_index.songs[cf.nav_cursor++];
        if (cf_nav_add(song) < 0) {
            cf_nav_finish();
            return RET_OK;
        }
    }
    if (cf.nav_cursor >= cf.nav_total) {
        cf_nav_finish();
        return RET_OK;
    }
    cf_nav_schedule();
    return RET_OK;
}

/* The album the shelf opens on: the playing track's album when something is queued, else the one last centred
 * (POSITION_FILE). Looked up once, at open (no polling). The track's album is its album key (cc_album_key, the FNV
 * of artist then album the cache files carry), else the album of that name: the library groups albums by name and
 * lists one artist for each, which a compilation's tracks do not all share. -1: no match (nothing playing, an
 * online or untagged track, an artist who does not have that album). */
static int find_playing(void) {
    void *t = cc_playing();
    const char *album = t ? cc_str(t, REC_ALBUM) : "";
    unsigned key, n = album_count(), i;
    if (!*album) return -1;
    key = cc_album_key(t);
    for (i = 0; i < n; ++i)
        if (key_at(i) == key) return (int)i;
    for (i = 0; i < n; ++i)
        if (!is_card(album_at(i)) && !cc_nocase(cc_str(album_at(i), REC_ALBUM), album)) return (int)i;
    return -1;
}

static void pick_start(void) {
    unsigned n = album_count(), i;
    int playing = find_playing();
    if (playing >= 0) {
        cf.album = playing;
        return;
    }
    for (i = 0; cf.saved_album && i < n; ++i)
        if (key_at(i) == cf.saved_album) cf.album = (int)i;
}

/* One artist's albums, exactly as the stock artist page lists them (loadAlbumList(0xf004, artist),
 * album_page_init), the stock "All songs" row last: kept as the All albums card when there are two
 * albums or more (q2-pod's ARTIST_ALBUMS cards), dropped otherwise. Each album takes the cache key
 * of the library's album of the same name (getAllAlbum groups by name, ASCII case aside, as
 * strcasecmp compares), so the covers are the files the main Cover Flow built and nothing is
 * extracted twice; an album the library list lacks keys itself. */
/* The library's album-name index (case-insensitive, the first row of a name wins), used when an artist has enough
 * albums that one pass over the library to build it costs less than a scan per album (IDX_MIN: about a pass over the
 * library per 24 scans). Open addressing, at most half full: a slot holds a library row + 1. */
#define IDX_MIN 24
static unsigned nc_hash(const char *s) { /* FNV-1a over the ASCII-folded bytes (cc_nocase's equality) */
    unsigned h = 2166136261u;
    for (; *s; ++s) h = (h ^ (unsigned)(*s >= 'A' && *s <= 'Z' ? *s + 32 : (unsigned char)*s)) * 16777619u;
    return h;
}

static unsigned *name_index(void *all, unsigned m, unsigned *mask) {
    unsigned size = 16, i, *t;
    while (size < 2 * m) size <<= 1;
    t = calloc(size, sizeof *t);
    if (!t) return (unsigned *)0;
    *mask = size - 1;
    for (i = 0; i < m; ++i) {
        const char *s = cc_str(deque_at(all, i), REC_ALBUM);
        unsigned h = nc_hash(s) & *mask;
        while (t[h] && cc_nocase(cc_str(deque_at(all, t[h] - 1), REC_ALBUM), s)) h = (h + 1) & *mask;
        if (!t[h]) t[h] = i + 1; /* an equal name is already there from an earlier row: it stays */
    }
    return t;
}

static void *name_find(void *all, const unsigned *t, unsigned mask, const char *s) {
    unsigned h = nc_hash(s) & mask;
    for (; t[h]; h = (h + 1) & mask) {
        void *r = deque_at(all, t[h] - 1);
        if (!cc_nocase(cc_str(r, REC_ALBUM), s)) return r;
    }
    return (void *)0;
}

/* One artist's (or composer's) albums for any page: the rows of loadAlbumList(scope, the artist) copied into *albums (the stock All songs row last, kept
 * when keep_card and two albums or more, else dropped from the count), their cache keys into *keys (calloc, n entries; NULL when it cannot be made or
 * the list is over MAX_ALBUMS: each album then keys itself). Returns the count (0: none, *albums NULL). The caller frees both. The Cover Flow page and
 * the Albums page's scoped mode (patch/albums.c) share it. */
int coverflow_artist_albums(void *artist_row, unsigned scope, int keep_card, void **albums, unsigned **keys) {
    void *list, *all;
    unsigned n, i, j, m, mask = 0, *ix = (unsigned *)0;
    *albums = (void *)0, *keys = (unsigned *)0;
    loadAlbumList(scope, deque_at(artist_row, 0));
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    if (!n || !(*albums = cc_copy_list(list))) return 0;
    if (I(deque_at(*albums, n - 1), REC_ID) == ID_ALL_SONGS && (!keep_card || n - 1 < 2)) --n;
    if (!n || n > MAX_ALBUMS) return (int)n;
    *keys = calloc(n, sizeof **keys); /* none: each album keys itself */
    all = *keys && loadLocalClassList(CLASS_ALBUMS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    m = all ? deque_size(all) : 0;
    if (n >= IDX_MIN && m) ix = name_index(all, m, &mask); /* none (few albums, or no memory): the scan below */
    for (i = 0; *keys && i < n; ++i) {
        void *r = deque_at(*albums, i), *same = r, *hit;
        if (I(r, REC_ID) == ID_ALL_SONGS) continue; /* key 0: no art */
        if (ix) {
            hit = name_find(all, ix, mask, cc_str(r, REC_ALBUM));
            if (hit) same = hit;
        } else {
            for (j = 0; j < m; ++j)
                if (!strcasecmp(cc_str(deque_at(all, j), REC_ALBUM), cc_str(r, REC_ALBUM))) {
                    same = deque_at(all, j);
                    break;
                }
        }
        (*keys)[i] = cc_album_key(same);
    }
    free(ix);
    return (int)n;
}

static int load_artist(void) {
    cf.count = (unsigned)coverflow_artist_albums(cf.artist_row, cf.scope, 1, &cf.albums, &cf.keys);
    if (cf.count && cf.count <= MAX_ALBUMS)
        cf.order = cc_album_order_mode(cf.albums, cc_scoped_sort(),
                                       cc_sort_rev()); /* the Albums page's order for one artist */
    return (int)cf.count;
}

static int start_build(void);

static void show_preparing(void) {
    cf.screen = CF_PREPARING;
    show(cf.covers, 0);
    show(cf.status, 1);
    show(cf.cancel, 1);
    widget_set_tr_text(cf.status, "Preparing covers...");
}

/* The worker of a page left a moment ago is still inside its last album (cc_build_stop orphans it): ask again. */
static int on_retry(const void *unused) {
    (void)unused;
    cf.timer = 0;
    if (!cf.fg) return RET_OK;
    if (cf.screen == CF_PREPARING && !start_build()) to_covers();
    return RET_OK;
}

/* Jobs for the albums with no cache file yet. 1 when a
 * build is running (or about to start, behind a stopped worker's last album) and the preparing screen is up, 0 when there is nothing to build (or no card, no space, no thread,
 * or the shared worker is busy with another page's set). */
static int start_build(void) {
    unsigned n = album_count(), i;
    if (!cf.fg || !cf.win) return 0;
    if (!cc_build_open(n, CC_MISSING)) {
        if (!cc_build_orphan()) return 0;
        cf.timer = timer_add(on_retry, (void *)0, POLL_MS);
        if (!cf.timer) return 0;
        show_preparing();
        return 1;
    }
    cf.owns = 1;
    for (i = 0; i < n; ++i) {
        if (is_nav_album(album_at(i))) continue; /* Nav artwork already lives in its shared cache */
        unsigned key = key_at(i);
        if (cc_build_add(cc_str(album_at(i), REC_PATH), key) < 0) break;
    }
    if (!cc_build_start()) { /* nothing to build, no card, no space, or no thread: show what is cached already */
        cf.owns = 0;
        return 0;
    }
    cf.timer = timer_add(on_poll, (void *)0, POLL_MS);
    if (!cf.timer) {
        build_end(); /* no completion callback possible: stop the worker, show what is cached */
        return 0;
    }
    show_preparing();
    return 1;
}

/* A page can remain in the navigator stack after it goes behind Now Playing, an album, or another page.
 * Stop all callbacks before the window starts leaving the foreground; resume from the foreground event. */
static void page_pause(void) {
    int was_dragging = cf.dragging;
    cf.fg = 0;
    stop_timer();
    if (cf.nav_timer) timer_remove(cf.nav_timer);
    cf.nav_timer = 0;
    if (fx.load_timer) timer_remove(fx.load_timer);
    fx.load_timer = 0;
    snap_stop();
    cf.dragging = cf.active = cf.interrupted = 0;
    if (was_dragging && cf.covers && cf.input) widget_ungrab(cf.covers, cf.input);
    if (cf.owns) build_end();
}

static int on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    page_pause();
    return RET_OK;
}

static int on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    cf.fg = 1;
    if (!cf.win) return RET_OK;
    if (cf.screen == CF_COVERS && shelf_up()) {
        set_offset(0);
        if (depth()) cfpos.value = cf.album;
    }
    if (cf.nav_scanning) {
        cf_nav_schedule();
    } else if (cf.screen == CF_PREPARING) {
        if (!start_build()) to_covers();
    } else if (cf.screen == CF_COVERS && depth() && fx_fill(1) && !fx.load_timer) {
        fx.load_timer = timer_add(on_load, (void *)0, LOAD_MS);
    }
    return RET_OK;
}

/* Back: preparing -> cancel and covers, covers -> leave the page. */
/* The artist's covers window (patch/songs.c: Back from the artist's songs list leaves the artist too), NULL when this is not an artist page. */
void *coverflow_artist_page(void) { return cf.win && cf.scoped ? cf.win : (void *)0; }

static int on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (cf.screen == CF_PREPARING) return on_cancel((void *)0, (void *)0);
    page_pause();
    navigator_back();
    return RET_OK;
}

/* The window is going: stop the timer, join the worker, free everything we own. Nothing of ours
 * may outlive the page. */
static int on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    page_pause();
    fx_close();
    if (cf.saved_album && !cf.scoped) position_save(cf.saved_album);
    if (cf.albums) deque_destroy(cf.albums);
    if (cf.artist_row) deque_destroy(cf.artist_row);
    free(cf.keys);
    free(cf.order);
    cf_nav_release();
    cf.albums = cf.artist_row = (void *)0;
    cf.keys = cf.order = (unsigned *)0;
    cf.win = cf.covers = cf.slide = cf.input = cf.name = cf.artist = (void *)0;
    cf.status = cf.cancel = cf.songs = (void *)0;
    cf.screen = CF_COVERS;
    cf.album = cf.scoped = cf.land = cf.built = 0;
    cfpos.value = cfpos.off = 0;
    return RET_OK;
}

/* The page and its widgets, everything hidden that waits for a screen; -1 if it did not open. */
static int open_page(void) {
    cf.win = window_open("m1plus_cover");
    if (!cf.win) return -1;
    cf.fg = 1;
    widget_on(cf.win, EVT_DESTROY, on_destroy, (void *)0);
    widget_on(cf.win, EVT_WINDOW_TO_BG, on_bg, (void *)0);
    widget_on(cf.win, EVT_WINDOW_TO_FG, on_fg, (void *)0);
    pod_bind(cf.win, "btn_return", on_back, (void *)0);
    pod_bind(cf.win, "btn_backtoplayer", pod_on_player, (void *)0);
    cf.covers = widget_lookup(cf.win, "view_covers", 1);
    cf.name = widget_lookup(cf.win, "label_album", 1);
    cf.artist = widget_lookup(cf.win, "label_artist", 1);
    cf.status = widget_lookup(cf.win, "label_status", 1);
    cf.cancel = pod_bind(cf.win, "btn_cancel", on_cancel, (void *)0);
    cf.songs = pod_bind(cf.win, "btn_songs", on_songs, (void *)0); /* in the asset, hidden; the artist page shows it */
    if (!cf.covers || !cf.name || !cf.artist || !cf.status || !cf.cancel) {
        navigator_back(); /* an asset that is not ours: leave rather than work on half a page */
        return -1;
    }
    show(cf.status, 0);
    show(cf.cancel, 0);
    return 0;
}

/* n albums loaded: their covers (after building the missing art), else `empty` or "too large". */
static int open_covers(int n, const char *empty) {
    if (n <= 0 || n > MAX_ALBUMS) {
        show(cf.covers, 0);
        show(cf.status, 1);
        widget_set_text_utf8(cf.name, "");
        widget_set_text_utf8(cf.artist, "");
        widget_set_tr_text(cf.status, n > 0 ? "Library too large" : empty);
        cf.screen = CF_COVERS;
        return 0;
    }
    if (!cf.scoped) cf.saved_album = position_load(); /* the last album outlives a reboot */
    pick_start();
    if (!start_build()) to_covers();
    return 0;
}

/* The M1+ Music menu's Cover Flow row. 0 once the page is up, -1 if it could not open (the caller
 * then leaves the menu as it was). */
int coverflow_open(void) {
    int n;
    if (cf.win) return -1;
    memset(&cf, 0, sizeof cf);
    if (open_page()) return -1;
    n = load_albums();
    if (cf_nav_prepare()) {
        cf.screen = CF_PREPARING;
        show(cf.covers, 0);
        show(cf.status, 1);
        show(cf.cancel, 0); /* the asynchronous index scan cannot be cancelled mid-record */
        widget_set_tr_text(cf.status, "Loading Navidrome albums…");
        cf.nav_timer = timer_add(cf_nav_step, (void *)0, CF_NAV_MS);
        if (!cf.nav_timer) cf_nav_finish();
        return 0;
    }
    return open_covers(n, "Update Local Music first");
}

/* The Artists list's row `index` of `artists` (patch/artists.c; the caller keeps its list): the
 * same page on that artist's albums, titled with the artist (q2-pod's coverflow_artist). scope is the
 * list's stock class: CLASS_ARTISTS, or CLASS_COMPOSERS for a composer (loadAlbumList(0xf005, row) is
 * getAlbumByComposer with the same last "All songs" row; the album page is then class 0xff02 -> 0xff14).
 * Back leaves it for the list. 0 once the page is up, -1 if it could not open. */
int coverflow_artist(void *artists, unsigned index, unsigned scope) {
    void *row = artists && index < deque_size(artists) ? deque_at(artists, index) : (void *)0, *title;
    if (cf.win || !row) return -1;
    memset(&cf, 0, sizeof cf);
    cf.scoped = ARTIST_ALBUMS;
    cf.scope = scope == CLASS_COMPOSERS ? CLASS_COMPOSERS : CLASS_ARTISTS;
    cf.artist_row = _create_deque("stSongInfo");
    if (!cf.artist_row) return -1;
    deque_init(cf.artist_row);
    _deque_push_back(cf.artist_row, row); /* a copy, as the stock queries push rows */
    if (open_page()) {
        if (!cf.win) { /* else the window's on_destroy frees it */
            deque_destroy(cf.artist_row);
            cf.artist_row = (void *)0;
        }
        return -1;
    }
    title = widget_lookup(cf.win, "label_title", 1);
    if (title) {
        widget_set_text_utf8(title, cc_str(row, REC_TITLE));
        widget_resize(title, NAV_VIEW_X - widget_get_prop_int(title, "x", 0),
                      widget_get_prop_int(title, "h", 0)); /* ends before the button's slot */
    }
    return open_covers(load_artist(), "No albums");
}
#endif /* CF_HOST */
