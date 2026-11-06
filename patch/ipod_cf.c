/* M1+ Music iPod: the Cover Flow screen of the virtual iPod (patch/ipod.c) -- the iPod Classic's Cover Flow in the 320 x 240 screen.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/ipod-coverflow.md has the design. This file holds only what Cover Flow adds to the iPod page: the slide's position and its easing, the
 * covers' textures and the screen's paint. The albums, the wheel, the levels and the one page timer stay in patch/ipod.c, which calls in here when its
 * Cover Flow level (K_CF) is in front. No hook, no widget, no timer of its own: the page's ONE timer runs ipcf_tick (patch/ipod.c sets its interval in place, ip_want_ms / ip_retime).
 *
 *   renderer   Cover Flow's own depth renderer (patch/coverflow.c coverflow_render, header coverflow.h), with a shelf scaled to the 240 px screen (IPCF_*
 *              in offsets.inc) and seven covers visible (cfg.tail). The textures are the 168 px cache files (/mnt/mmc/.m1plus/covers, patch/covercache.c) the
 *              Cover Flow page and the Albums grid share; the placeholder is the Pod's own (`ipod_placeholder`, the iTunes one).
 *   textures   8 slots (the 7 of the ring and a spare), decoded one a tick on the page's timer (UI thread, cc_decode), nearest the centre first, the side
 *              the slide is moving towards first. Paint renders from what is resident and never decodes, queries or touches a file.
 *   slide      pos / target in 16.16 album units: the wheel moves the target (ipcf_goto), each fast tick closes dt / (dt + IPCF_TAU_MS) of the gap.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "coverflow.h"
#include "common.h"
#include "i18n.h"
#include "ipod_theme.h"
#include "ipod_render.h"
#undef widget_prepare_text_style
#undef canvas_draw_text_in_rect
#undef canvas_draw_image
#define widget_prepare_text_style ip_render_prepare
#define canvas_draw_text_in_rect ip_render_text
#define canvas_draw_image ip_render_image

extern unsigned ip_fit(void *canvas, unsigned *s,
                       int maxw); /* patch/ipod.c: the wide string cut with an ellipsis to maxw px */

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define IPCF_SLOTS (CF_RING + 1)
#define TEXELS (ART_SIZE * ART_SIZE)
#define PLACE (ipcf.tex + IPCF_SLOTS * TEXELS)

static const cfg_t shelf = {IP_W,    IPCF_FRAME_H, IP_W / 2,     IPCF_TOP, IPCF_ART,  IPCF_EYE,  IPCF_X1, IPCF_XS,
                            IPCF_Z1, IPCF_ZS,      IPCF_REFLECT, 0,        IPCF_TURN, IPCF_TAIL, IPCF_BG};

static struct {
    int pos, target; /* the slide's position and where it goes, 16.16 albums (first: test/pod/ipod_cf.py reads them) */
    void *win, *frame;
    unsigned *tex; /* IPCF_SLOTS textures, then the placeholder */
    unsigned key[IPCF_SLOTS]; /* the album key each slot holds, 0 empty */
    int idx[IPCF_SLOTS]; /* the album's row when it was decoded (only to pick the farthest slot to reuse) */
    const unsigned *art[IPCF_SLOTS]; /* its texture: the slot's own, or the placeholder (the album has no art) */
    int dir; /* the way it last went: 1 towards later albums, -1 back */
    int more; /* a wanted cover is not decoded yet */
    int drawn, dc, dfrac; /* the position the frame holds, once drawn */
    void *list; /* the stock list and its size the frame was drawn from */
    unsigned count;
    unsigned bg;
    unsigned t0; /* the last time the slide moved (ms) */
} ipcf __attribute__((section(".scratch")));

void ipcf_close(void) {
    if (ipcf.frame) bitmap_destroy(ipcf.frame);
    if (ipcf.tex) free(ipcf.tex);
    memset(&ipcf, 0, sizeof ipcf);
}

/* The frame and the textures, or neither (0: the caller falls back to the Cover Flow page). The slide stands on album 0. */
int ipcf_open(void *win) {
    unsigned *p, i;
    if (ipcf.frame) return 1;
    memset(&ipcf, 0, sizeof ipcf);
    ipcf.win = win;
    ipcf.frame = bitmap_create_ex(IP_W, IPCF_FRAME_H, IP_W * 4, BITMAP_RGBA8888);
    ipcf.tex = ipcf.frame ? calloc((IPCF_SLOTS + 1) * TEXELS, 4) : (unsigned *)0;
    if (!ipcf.tex) {
        ipcf_close();
        return 0;
    }
    *(unsigned short *)((char *)ipcf.frame + BITMAP_FLAGS) |= 1; /* OPAQUE: every pixel is */
    p = PLACE;
    for (i = 0; i < TEXELS; ++i) p[i] = 0xff2b2b2bu; /* until the theme's disc loads */
    cc_decode(win, "ipod_placeholder", 0, ART_SIZE, 1, p);
    ipcf.dir = 1, ipcf.more = 1;
    return 1;
}

int ipcf_up(void) { return ipcf.frame != (void *)0; }
int ipcf_busy(void) { return ipcf.frame && (ipcf.pos != ipcf.target || ipcf.more); }

/* ---------------------------------------------------------------------------
 * Textures
 */
static unsigned key_of(void *r) {
    return r && I(r, REC_ID) != ID_ALL_SONGS && *cc_str(r, REC_ALBUM) ? cc_album_key(r) : 0;
}

static int resident(unsigned key) {
    int i;
    for (i = 0; i < IPCF_SLOTS; ++i)
        if (ipcf.key[i] == key) return i;
    return -1;
}

static const unsigned *tex_of(void *list, unsigned count, int a) {
    unsigned key = (unsigned)a < count ? key_of(deque_at(list, (unsigned)a)) : 0;
    int i = key ? resident(key) : -1;
    return i < 0 ? PLACE : ipcf.art[i];
}

/* The k-th album wanted around c, nearest first (c, then each ring distance ahead of the travel, then behind it); -1 for none. */
static int wanted(int c, int n, int k) {
    int a = k == 0 ? c : c + (k + 1) / 2 * (k & 1 ? ipcf.dir : -ipcf.dir);
    return a >= 0 && a < n ? a : -1;
}

/* The nearest wanted cover that is not decoded yet goes into a free slot, else the farthest one's. Returns whether one was decoded; ipcf.more says whether any is left. */
static int fill(void *list, unsigned count, int c) {
    char url[80];
    const char *file;
    int k, done = 0, slot, dist, i;
    ipcf.more = 0;
    for (k = 0; k < CF_RING; ++k) {
        int a = wanted(c, (int)count, k);
        unsigned key = a < 0 ? 0 : key_of(deque_at(list, (unsigned)a));
        if (!key || resident(key) >= 0) continue;
        if (done) {
            ipcf.more = 1;
            break;
        }
        slot = -1, dist = -1;
        for (i = 0; i < IPCF_SLOTS && slot < 0; ++i)
            if (!ipcf.key[i]) slot = i;
        if (slot < 0)
            for (i = 0; i < IPCF_SLOTS; ++i) {
                int d = ipcf.idx[i] > c ? ipcf.idx[i] - c : c - ipcf.idx[i];
                if (d > dist) dist = d, slot = i;
            }
        ipcf.key[slot] = key, ipcf.idx[slot] = a;
        file = cc_url(url, key);
        ipcf.art[slot] = file && cc_decode(ipcf.win, file, 1, ART_SIZE, 0, ipcf.tex + slot * TEXELS)
                             ? ipcf.tex + slot * TEXELS
                             : PLACE; /* no art, or no cache file yet */
        done = 1;
    }
    if (done) ipcf.drawn = 0;
    return done;
}

/* ---------------------------------------------------------------------------
 * The slide
 */

/* The wheel moved the cursor to album sel: the slide goes there. Never more than IPCF_NEAR albums away at the start. */
void ipcf_goto(int sel) {
    int t = sel << 16, d = t - ipcf.pos;
    if (!ipcf.frame) return;
    if (ipcf.pos == ipcf.target) ipcf.t0 = time_now_ms();
    ipcf.target = t;
    if (d > IPCF_NEAR << 16)
        ipcf.pos = t - (IPCF_NEAR << 16);
    else if (d < -(IPCF_NEAR << 16))
        ipcf.pos = t + (IPCF_NEAR << 16);
    if (d) ipcf.dir = d < 0 ? -1 : 1;
    ipcf.drawn = 0;
}

/* One tick of the page's timer: the slide eases, one wanted cover is decoded. list / count are the front level's stock list (valid). 1: the screen needs painting. */
int ipcf_tick(void *list, unsigned count) {
    unsigned now = time_now_ms();
    int changed = 0, c;
    if (!ipcf.frame) return 0;
    if (ipcf.pos != ipcf.target) {
        int dt = (int)(now - ipcf.t0), diff = ipcf.target - ipcf.pos, step;
        if (dt < 1) dt = 1;
        if (dt > 100) dt = 100;
        step = diff * dt / (dt + IPCF_TAU_MS);
        if (!step) step = diff < 0 ? -1 : 1;
        ipcf.pos += step;
        if (ipcf.target - ipcf.pos < IPCF_DONE && ipcf.pos - ipcf.target < IPCF_DONE) ipcf.pos = ipcf.target;
        changed = 1;
    }
    ipcf.t0 = now;
    if (count) {
        c = (ipcf.pos + CF_ONE / 2) >> 16;
        if (c >= (int)count) c = (int)count - 1;
        if (fill(list, count, c)) changed = 1;
    } else
        ipcf.more = 0;
    return changed;
}

/* ---------------------------------------------------------------------------
 * Paint
 */

/* The utf-8 text centred in the screen's width in the style the canvas has (dark 17 px: label_ip_row), cut with an ellipsis, in the line at y. */
static void caption(void *canvas, const char *utf8, int y) {
    unsigned wide[64], n = 0, len;
    int rect[4], w;
    while (utf8[n]) n++;
    if (!n) return;
    tk_utf8_to_utf16_ex(utf8, n, wide, 64);
    len = ip_fit(canvas, wide, IP_W - 24);
    if (!len) return;
    w = (int)(canvas_measure_text(canvas, wide, len) + 0.999f);
    rect[0] = (IP_W - w) / 2, rect[1] = y, rect[2] = w + 2, rect[3] = IPCF_CAP_H;
    canvas_draw_text_in_rect(canvas, wide, len, rect);
}

/* The screen under the title bar (the caller has filled it white and paints the bar after): the frame (covers and reflections on white) at IPCF_FRAME_Y, the album under the
 * centre cover and its artist in style (the list rows' dark text). list is NULL while the stock list is stale (nothing). */
void ipcf_paint(void *canvas, void *list, unsigned count, void *style) {
    const unsigned *ring[CF_RING];
    int c, frac, j, src[4], dst[4];
    void *r;
    if (!ipcf.frame || !list) return;
    widget_prepare_text_style(style, canvas);
    if (!count) {
        caption(canvas, TR("No songs"), IP_SCREEN_H / 2 - IPCF_CAP_H / 2);
        return;
    }
    c = (ipcf.pos + CF_ONE / 2) >> 16;
    if (c < 0) c = 0;
    if (c >= (int)count) c = (int)count - 1;
    frac = ipcf.pos - (c << 16);
    if (list != ipcf.list || count != ipcf.count) ipcf.list = list, ipcf.count = count, ipcf.drawn = 0;
    if (!ipcf.drawn || c != ipcf.dc || frac != ipcf.dfrac || ipcf.bg != ip_theme_colors()->bg) {
        cfg_t themed;
        memcpy(&themed, &shelf, sizeof themed);
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ipcf.frame);
        if (!d) return;
        for (j = 0; j < CF_RING; ++j) {
            int a = c + j - CF_REACH;
            ring[j] = a >= 0 && a < (int)count ? tex_of(list, count, a) : (const unsigned *)0;
        }
        themed.bg = ip_theme_colors()->bg;
        coverflow_render(&themed, d, (int)(bitmap_get_line_length(ipcf.frame) / 4), frac, ring);
        bitmap_unlock_buffer(ipcf.frame);
        ipcf.drawn = 1, ipcf.dc = c, ipcf.dfrac = frac;
        ipcf.bg = themed.bg;
    }
    src[0] = 0, src[1] = 0, src[2] = IP_W, src[3] = IPCF_FRAME_H;
    dst[0] = 0, dst[1] = IPCF_FRAME_Y, dst[2] = IP_W, dst[3] = IPCF_FRAME_H;
    canvas_draw_image(canvas, ipcf.frame, src, dst);
    r = deque_at(list, (unsigned)c);
    caption(canvas, cc_str(r, REC_ALBUM), IPCF_CAP_Y);
    caption(canvas, cc_str(r, REC_ARTIST), IPCF_CAP_Y + IPCF_CAP_H);
}
