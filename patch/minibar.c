/* M1+ Music mini player bar: a floating "now playing" card at the bottom of the Home instance of the menu.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * No stock function is hooked. The widgets are in the menu's own asset (ui/m1plus_menu.bin, tools/pod_ui.py: pod_minibar, a
 * hidden and insensitive view holding the card button, the title and artist labels and the play, pause and next buttons);
 * patch/home.c calls minibar_start for the Home instance only (the menu opened from the grid icon keeps its navbar and never
 * gets a bar). Everything here runs from the menu window's events and one page-scoped timer.
 *
 *   start    looks up the widgets and the stock list, registers EVT_DESTROY / EVT_WINDOW_TO_BG / EVT_WINDOW_TO_FG and the
 *            card's EVT_AFTER_PAINT, and arms a one-shot MB_FIRST_MS later (the menu's first paint does nothing extra).
 *            Any widget missing, any registration or the timer failing: nothing is shown or moved, the menu is as it was.
 *   timer    mb_first (the one-shot) starts the MB_TICK_MS repeating mb_tick; both call mb_work. Only while the window is in
 *            front: EVT_WINDOW_TO_BG removes the timer, EVT_WINDOW_TO_FG arms the one-shot again, EVT_DESTROY removes it and
 *            frees the cover bitmap. mb_work is the only code that changes anything:
 *              nothing queued (cc_playing NULL)  the bar is hidden (hidden and insensitive) and the list's spacer row is
 *                                                hidden again: the menu is as it was.
 *              a track is playing or paused      the bar shows and the list's spacer row is visible (see mb_pad). When the
 *                                                track changed (a hash of its path, title and file name): the title and artist
 *                                                labels and the cover. The play / pause button follows
 *                                                mclGetPlayStatus (2 = playing, as the lock screen's refresh reads it), swapped
 *                                                only when it changes.
 *   radio    mb_radio decides first (patch/radio.h; docs/modules/radio.md): while a station connects, plays or is paused, and in Error or Stopped after a
 *            session unless a local song is really playing or paused (mb_local_alive: status 3, or 2 with hciplayer playing), the bar
 *            shows the station and never the stale local queue's track (Stopped only while rd_owns_bar: a local track start clears it);
 *            in Idle and in Stopped after a local track the local logic above applies unchanged. "Stopped" line, play glyph, play = rd_play again.
 *            Title: the station's name ("Radio" without one). Second line, radio Now Playing's words: "Connecting…", "Live" (playing),
 *            "Paused", "Can't play: <error>". Cover: the station's cached logo (rd_logo_file as radionp.c; the logo worker is started when
 *            it is not cached and the cover redone when the file appears), else the radio glyph on Now Playing's card grey, else the
 *            stock disc. The look is unchanged; the next button stays, greyed (mb_next_off) and insensitive (a live station has none), white again when
 *            the bar goes back to a track. The key is (station address, state, error text), so labels are redone only when one changes;
 *            the cover only for another station.
 *            Card: radio Now Playing (rn_open, also in Error). A station has no pause here: Connecting or Playing -> rd_stop (the glyph is Stop, mb_stop on the pause button),
 *            Paused (made by a key, unplugged headphones, an output switch) -> rd_resume (mclSetResume, or Error No Wi-Fi without a connection; the engine's
 *            tick turns stock's status 3 into Paused), Error -> rd_play of the same station (a retry); the glyph is play while Paused or in Error.
 *   cover    MB_ART (36) px, decoded on the timer, never in paint (paint draws the resident bitmap with canvas_draw_image): the album's
 *            Cover Flow cache file when it exists (cc_url), else the /tmp file demo wrote for the playing track (COVER_SRC as
 *            Now Playing reads it; demo writes it a little after the track changes, so for MB_SETTLE ticks the file's hash is
 *            read again and the cover redone if it changed), else the stock placeholder disc. The box filter of
 *            patch/covercache.c; the four MB_ART_R px corners are rounded by the bitmap's own alpha, so they show the card
 *            in its pressed state too.
 *   look     the card is a pre-rendered translucent glass pill (the button's bg_image mb_glass, mb_glass_down when pressed: dark
 *            fill, sheen, rim light), the same for every track. The list runs behind it. Nothing is coloured at run time.
 *   touch    the card opens Now Playing as the menu's Now Playing row does (on_backtoplayer_onclick); play / pause calls
 *            playpause_quick_click and next calls next_quick_click(e, 0): the functions the lock screen's, Now Playing's and the
 *            hardware keys' handlers call (tools/pod.py), with their own checks, toasts and notifications.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "minibar.h"
#include "common.h"
#include "i18n.h"
#include "podcasts.h"
#include "radio.h"
#include "sbapi.h"
#include "libsrc.h"

extern unsigned np_file_key(const char *path); /* patch/nowplaying.c: a hash of the picture file, 0 if unreadable */
extern const char *
np_cover_file(int *busy); /* the /tmp file of the playing track's cover, NULL for none; busy while demo makes it */

#define MB_HASH_PRIME 16777619u

static struct {
    void *win, *bar, *card, *title, *artist, *play, *pause, *next, *sv,
        *pad; /* the list's scroll view and its trailing spacer row */
    unsigned timer; /* the one-shot or the repeating timer, 0 none */
    unsigned interval; /* repeating timer interval last accepted by timer_modify */
    int fg; /* the window is in front */
    int shown; /* the bar is up */
    int playing; /* the glyph shown: 1 pause (playing), 0 play, -1 neither set yet */
    unsigned key; /* the track the labels and the cover were made for, 0 none */
    mb_art_t art; /* the cover (shared with the lock screen's bar), its /tmp file hash and settle ticks */
    mb_blur_t bl; /* the backdrop blur (shared with the lock screen's bar): the plane, allowed, partial frame */
    int recent_pending; /* dark album changes need publishing when the screen is lit */
    int radio; /* the bar shows the radio (see mb_radio); next is greyed then */
    unsigned rkey; /* the station the cover was made for (a hash of its address), 0 none */
    int rlogo; /* the station's logo is not cached yet: look again on the next ticks */
} mb __attribute__((section(".scratch")));

/* Hidden and out of the hit test together (this AWTK's widget_find_target ignores visible). */
static void mb_vis(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* ---------------------------------------------------------------------------
 * The list: it always runs to the window's bottom, under the translucent pill. While the bar shows, the trailing spacer row pod_pad
 * (MB_PAD high, an invisible insensitive view that is the list's last child) is visible, so the stock list_view layout (it sums every
 * visible child's own height into virtual_h) keeps the padding at every relayout and the last row can scroll clear above the pill.
 * patch/menu.c menu_arrange reads the spacer's visibility when it sets virtual_h. Showing or hiding it also adjusts virtual_h at once (the
 * relayout the visibility change marks gives the same value) and keeps yoffset inside the new range.
 */
static void mb_pad(int on) {
    int vh = widget_get_prop_int(mb.sv, "virtual_h", 0), max;
    widget_set_visible(mb.pad, on, 0); /* insensitive in the asset: it never takes a touch */
    vh += on ? MB_PAD : -MB_PAD;
    if (vh < 0) vh = 0;
    widget_set_prop_int(mb.sv, "virtual_h", vh);
    max = vh - widget_get_prop_int(mb.sv, "h", 0); /* a shorter list may not stay scrolled past its end */
    if (max < 0) max = 0;
    if (widget_get_prop_int(mb.sv, "yoffset", 0) > max) widget_set_prop_int(mb.sv, "yoffset", max);
    widget_invalidate_force(mb.sv, (void *)0);
}

/* The next button: white and live for a local track, NP_OFF grey, insensitive (no press feedback, no click) while a station owns the bar. */
static void mb_next_look(int live) {
    const char *n = live ? "mb_next" : "mb_next_off";
    widget_set_prop_str(mb.next, "style:normal:icon", n);
    widget_set_prop_str(mb.next, "style:over:icon", n);
    widget_set_prop_str(mb.next, "style:pressed:icon", live ? "mb_next_down" : n);
    widget_set_sensitive(mb.next, live);
    widget_invalidate_force(mb.bar, (void *)0); /* the whole pill, as every change inside it */
}

/* The pause button's glyph: Stop (a square, radio Now Playing's) while a station owns the bar, the pause bars for a local track. It shows only while a station connects or plays. */
static void mb_pause_look(int stop) {
    const char *n = stop ? "mb_stop" : "mb_pause";
    widget_set_prop_str(mb.pause, "style:normal:icon", n);
    widget_set_prop_str(mb.pause, "style:over:icon", n);
    widget_set_prop_str(mb.pause, "style:pressed:icon", stop ? "mb_stop_down" : "mb_pause_down");
    widget_invalidate_force(mb.bar, (void *)0);
}

static void mb_hide(void) {
    if (!mb.shown) return;
    mb.shown = 0;
    mb.key = 0;
    mb.art.fkey = 0;
    mb.rkey = 0;
    mb.rlogo = 0;
    mb.art.settle = 0;
    mb_vis(mb.bar, 0);
    mb_pad(0);
}

static void mb_show(void) {
    mb_pad(1);
    mb_vis(mb.bar, 1);
    widget_invalidate_force(mb.bar, (void *)0);
    mb.shown = 1;
}

/* ---------------------------------------------------------------------------
 * The card: texts, cover (its look, the pill fill and edge, is the asset's style: nothing is coloured per track)
 */

unsigned mb_track_key(void *t) {
    unsigned h = cc_fnv(cc_fnv(cc_fnv(FNV_SEED, cc_str(t, REC_PATH)), cc_str(t, REC_TITLE)), cc_str(t, REC_NAME));
    h = (h ^ *(unsigned *)((char *)t + REC_CUE_START)) * MB_HASH_PRIME;
    return h | !h;
}

static void mb_labels(void *t) {
    const char *title = cc_str(t, REC_TITLE);
    if (!*title) title = cc_str(t, REC_NAME);
    widget_set_text_utf8(mb.title, title);
    widget_set_text_utf8(mb.artist, cc_str(t, REC_ARTIST));
    widget_invalidate_force(mb.card, (void *)0); /* the whole pill, not the labels' rectangles (see the blur) */
}

/* The four corners' alpha: 255 less the coverage outside the arc (the colour channels are left as they are). */
/* The bitmap's locked pixels, the bitmap and its corner table made on first use; NULL: no cover (the card paints none). */
unsigned *mb_art_begin(mb_art_t *a) {
    if (!a->bmp) {
        a->bmp = bitmap_create_ex(MB_ART, MB_ART, MB_ART * 4, BITMAP_RGBA8888);
        if (a->bmp) pod_corner_fill(a->corner, MB_ART_R);
    }
    return a->bmp ? (unsigned *)bitmap_lock_buffer_for_write(a->bmp) : (unsigned *)0;
}

/* The four corners' alpha: 255 less the coverage outside the arc (the colour channels are left as they are); unlocks. */
void mb_art_end(mb_art_t *a, unsigned *px) {
    unsigned k, x, y;
    for (k = 0; k < 4; ++k)
        for (y = 0; y < MB_ART_R; ++y)
            for (x = 0; x < MB_ART_R; ++x) {
                unsigned *p = px + (k & 2 ? MB_ART - 1 - y : y) * MB_ART + (k & 1 ? MB_ART - 1 - x : x);
                *p = (*p & 0xffffff) | (255u - a->corner[y * MB_ART_R + x]) << 24;
            }
    bitmap_unlock_buffer(a->bmp);
}

/* The playing track's cover into the bitmap. first: a new track (the /tmp file is read again for a few ticks). 1 when the bitmap changed. A server track's is the server's file (the one Now Playing
 * shows), a placeholder until it lands (mb_art_settle keeps looking), else demo's /tmp file; never the library's album of the same name. */
int mb_art_cover(mb_art_t *a, void *win, void *t, int first) {
    char url[80], tmp[120];
    const char *file = (const char *)0, *path;
    unsigned album = *cc_str(t, REC_ALBUM) ? cc_album_key(t) : 0, *px, i;
    int busy = 0, server, sc = ls_rec_cover(t, tmp, sizeof tmp, &server);
    px = mb_art_begin(a);
    if (!px) return 0;
    if (first) a->settle = MB_SETTLE;
    a->fkey = 0;
    if (sc == 1 && (a->fkey = np_file_key(tmp + 7)) != 0) {
        file = tmp;
        if (first) a->settle = 0; /* the server's file is the track's own, and does not change */
    } else if (sc == 0) {
        a->settle = MB_SETTLE; /* on its way: the placeholder, and mb_art_settle looks again */
    } else {
        file = !server && album ? cc_url(url, album)
                                : (const char *)0; /* (a server track never takes the library's album of its name) */
        if (file) {
            if (first) a->settle = 0; /* the cache file is the album's, not the track's: nothing to wait for */
        } else if ((path = np_cover_file(&busy)) != (const char *)0 && !busy) {
            a->fkey = np_file_key(path);
            if (a->fkey) {
                snprintf(tmp, sizeof tmp, "file://%s", path);
                file = tmp;
            }
        }
    }
    if (!file || !cc_decode(win, file, 1, MB_ART, 1,
                            px)) { /* the stock placeholder disc, as the grid's tiles have it, else flat grey */
        for (i = 0; i < MB_ART * MB_ART; ++i) px[i] = MB_GREY;
        cc_decode(win, "p_default", 0, MB_ART, 1, px);
    }
    mb_art_end(a, px);
    return 1;
}

/* Demo writes the /tmp cover a little after the track changes: look again for MB_SETTLE ticks and redo the cover if the file is new. */
int mb_art_settle(mb_art_t *a, void *win, void *t) {
    int busy = 0, server;
    char tmp[120];
    const char *path;
    unsigned k;
    int sc = ls_rec_cover(t, tmp, sizeof tmp, &server);
    if (sc == 0) return 0; /* a server cover on its way: nothing is counted off while it is asked for */
    if (sc == 1) { /* it landed: shown once */
        a->settle = 0;
        k = np_file_key(tmp + 7);
        return k && k != a->fkey ? mb_art_cover(a, win, t, 0) : 0;
    }
    path = np_cover_file(&busy);
    if (busy) return 0; /* being replaced: not counted */
    a->settle--;
    k = path ? np_file_key(path) : 0;
    return k && k != a->fkey ? mb_art_cover(a, win, t, 0) : 0;
}

/* In the card's coordinates (the card's EVT_AFTER_PAINT): the resident cover. Nothing is decoded here. */
void mb_art_paint(mb_art_t *a, void *canvas) {
    int src[4], dst[4];
    if (!canvas || !a->bmp) return;
    src[0] = 0, src[1] = 0, src[2] = MB_ART, src[3] = MB_ART;
    dst[0] = MB_ART_X, dst[1] = MB_ART_Y, dst[2] = MB_ART, dst[3] = MB_ART;
    canvas_draw_image(canvas, a->bmp, src, dst);
}

void mb_art_free(mb_art_t *a) {
    if (a->bmp) bitmap_destroy(a->bmp);
    a->bmp = (void *)0;
}

static void mb_cover(void *t, int first) {
    if (mb_art_cover(&mb.art, mb.win, t, first)) widget_invalidate_force(mb.card, (void *)0);
}

static void mb_settle(void *t) {
    if (mb_art_settle(&mb.art, mb.win, t)) widget_invalidate_force(mb.card, (void *)0);
}

/* The card's own EVT_AFTER_PAINT, in the card's coordinates: the resident cover. Nothing is decoded here. */
static int mb_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (!canvas || !mb.win || !mb.art.bmp || !mb.shown) return RET_OK;
    mb_art_paint(&mb.art, canvas);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The backdrop blur (EXPERIMENTAL; tools/pod_blur.py is the bit-exact model, docs/modules/minibar.md Step B)
 *
 * The card's EVT_BEFORE_PAINT runs after the list has painted its rows into the drawing buffer and before the glass image goes over them. The
 * pixels of the pill's rectangle are reduced 2 x 2 into a plane of packed words (the three RGB565 channel sums in 10-bit fields), box-blurred
 * (two 4-tap passes along the rows, two along the columns, no field can carry into the next), darkened by 1/8 and written back, inside the pill
 * only. Fixed-point integer code, no allocation per frame (the plane is allocated once at start and freed with the page). Every precondition is
 * checked at every call and any structural mismatch (the lcd is not the 565 memory lcd, a null or odd buffer, a pitch or size that does not fit,
 * the rectangle off the screen) switches the blur off for the page: the glass is then drawn over the sharp rows, exactly the version without it.
 * A frame whose clip does not cover the whole pill (a partial repaint, for instance a row's press highlight under the pill) is not blurred: the
 * pixels outside the clip are the last frame's blurred ones, and blurring across the seam would show; the card is invalidated instead (the
 * next tick, and at once when a button is pressed or released) so the next frame repaints all of it.
 */
#define MB_FLD(p) \
    (((p) & 0xF800u) << 9 | ((p) & 0x07E0u) << 5 | ((p) & 0x1Fu)) /* RGB565 to three 10-bit fields: 20, 10, 0 */
#define MB_MASK 0x0FF3FCFFu /* three 8-bit fields at 0, 10, 20: the sum of four words >> 2 */
#define MB_DARK 0x01F07C1Fu /* three 5-bit fields at 0, 10, 20: the 8-bit fields >> 3 */
#define MB_HALF \
    0x00200802u /* 2 in each field: the rounding of every >> 2 (without it the smaller red and blue fields fall behind green: a green cast) */

static unsigned mb_isqrt(unsigned n) {
    unsigned s = 0;
    while ((s + 1) * (s + 1) <= n) ++s;
    return s;
}

/* Columns at the end of full row y outside the pill's arc, rounded up (tools/pod_blur.py inset). */
static unsigned mb_inset(unsigned y) {
    unsigned yy = y < MB_R ? y : 2 * MB_R - 1 - y, d2 = 2 * (MB_R - yy) - 1;
    return MB_R - (mb_isqrt(4 * MB_R * MB_R - d2 * d2) >> 1);
}

static void mb_blur_init(mb_blur_t *bl) {
    unsigned hy, a, b;
    for (hy = 0; hy < MB_HH; ++hy) {
        a = mb_inset(2 * hy), b = mb_inset(2 * hy + 1);
        bl->x0[hy] = (unsigned char)(((a > b ? a : b) + 2) >> 1); /* (max inset + 1 + 1) / 2 */
    }
}

/* One 4-tap pass over n words at v with stride (replicated edges): out[i] = (v[i-left] + .. + v[i-left+3]) / 4 per field. */
static void mb_line(unsigned *v, int n, int stride, int left) {
    unsigned pad[MB_HW + 5], s, *p = pad + left, *q = v, *o = v;
    int i;
    for (i = 0; i < n; ++i, q += stride) p[i] = *q; /* the line, then the replicated edges */
    for (i = 0; i < left; ++i) pad[i] = p[0];
    for (i = n + left; i < n + 5; ++i) pad[i] = pad[n + left - 1];
    s = pad[0] + pad[1] + pad[2] + pad[3];
    for (p = pad, i = 0; i < n; ++i, o += stride, ++p) {
        *o = ((s + MB_HALF) >> 2) & MB_MASK;
        s = s - p[0] + p[4]; /* subtract first: no field borrows or carries */
    }
}

#define MB_PEEK(p, off) (*(int *)((char *)(p) + (off)))

/* The blur of the pill under canvas (translated to the card). 0: not done (see above). */
static void mb_blur(mb_blur_t *bl, void *canvas) {
    char *lcd = (char *)MB_PEEK(canvas, CANVAS_LCD), *fb;
    int ox = MB_PEEK(canvas, CANVAS_OX), oy = MB_PEEK(canvas, CANVAS_OY), w, h, pitch, hy, hx, x0;
    unsigned *pl = bl->pl, v, px;
    if (!lcd || !pl) return;
    w = MB_PEEK(lcd, LCD_W), h = MB_PEEK(lcd, LCD_H), pitch = MB_PEEK(lcd, LCD_LINE);
    fb = (char *)MB_PEEK(lcd, LCD_FB);
    if ((unsigned)MB_PEEK(lcd, LCD_BEGIN) != LCD_565_BEGIN || !fb || ((unsigned)fb & 3) || w < MB_W || w > 2048 ||
        h < MB_H || h > 2048 || pitch < 2 * w || pitch > 8192 || (pitch & 3) || ox < 0 || oy < 0 || (ox & 1) ||
        ox + MB_W > w || oy + MB_H > h) {
        bl->on = 0; /* not the lcd this was written for: no blur on this page */
        return;
    }
    if (MB_PEEK(canvas, CANVAS_CLIP) > ox || MB_PEEK(canvas, CANVAS_CLIP + 4) > oy ||
        MB_PEEK(canvas, CANVAS_CLIP + 8) < ox + MB_W - 1 || MB_PEEK(canvas, CANVAS_CLIP + 12) < oy + MB_H - 1) {
        bl->fix = 1; /* a partial repaint: the whole pill again next */
        return;
    }
    fb += oy * pitch + ox * 2;
    for (hy = 0; hy < MB_HH; ++hy)
        for (hx = 0; hx < MB_HW; ++hx) {
            const unsigned short *r = (const unsigned short *)(fb + 2 * hy * pitch + 4 * hx);
            const unsigned short *q = (const unsigned short *)((const char *)r + pitch);
            pl[hy * MB_HW + hx] = MB_FLD(r[0]) + MB_FLD(r[1]) + MB_FLD(q[0]) + MB_FLD(q[1]);
        }
    for (hy = 0; hy < MB_HH; ++hy) mb_line(pl + hy * MB_HW, MB_HW, 1, 2), mb_line(pl + hy * MB_HW, MB_HW, 1, 1);
    for (hx = 0; hx < MB_HW; ++hx) mb_line(pl + hx, MB_HH, MB_HW, 2), mb_line(pl + hx, MB_HH, MB_HW, 1);
    for (hy = 0; hy < MB_HH; ++hy) {
        unsigned *r0 = (unsigned *)(fb + 2 * hy * pitch), *r1 = (unsigned *)((char *)r0 + pitch);
        for (x0 = bl->x0[hy], hx = x0; hx < MB_HW - x0; ++hx) {
            v = pl[hy * MB_HW + hx];
            v = v - ((v >> 3) & MB_DARK) + MB_HALF;
            px = ((v >> 22) & 0x1Fu) << 11 | ((v >> 12) & 0x3Fu) << 5 | ((v >> 2) & 0x1Fu);
            r0[hx] = r1[hx] = px | px << 16;
        }
    }
}

/* The shared entry (the Home bar's and the lock bar's before-paint handlers): the blur when it is still allowed. */
void mb_blur_paint(mb_blur_t *bl, void *canvas) {
    if (canvas && bl->on) mb_blur(bl, canvas);
}

/* The plane, unless the SD file m1plus-noblur turns the blur off or there is no memory. */
int mb_blur_alloc(mb_blur_t *bl) {
    if (access(MB_BLUR_OFF, F_OK) == 0) return 0;
    bl->pl = (unsigned *)calloc(MB_HW * MB_HH, sizeof(unsigned));
    return bl->pl != (unsigned *)0;
}

/* Every handler is registered: the blur runs. */
void mb_blur_enable(mb_blur_t *bl) {
    mb_blur_init(bl);
    bl->on = 1;
}

void mb_blur_free(mb_blur_t *bl) {
    if (bl->pl) free(bl->pl);
    memset(bl, 0, sizeof *bl);
}

static int mb_on_before_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (canvas && mb.win && mb.shown) mb_blur_paint(&mb.bl, canvas);
    return RET_OK;
}

/* The list scrolled (a drag, a fling, scroll_to: EVT_SCROLL, dispatched by every yoffset change): the scroll view invalidates its own rectangle, which ends
 * at the list's bottom and, with the scroll bar beside it, at x 309, so the clip would not always cover the whole pill. The pill is invalidated too: the dirty region
 * of the frame is then the union of both and always contains all of it, wherever the list's own rectangle ends. The offset is not touched, so this cannot loop. */
static int mb_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (mb.win && mb.bl.on && mb.shown) widget_invalidate_force(mb.card, (void *)0);
    return RET_OK;
}

/* A press, a release or an abort on a button repaints only the button's rectangle: the whole pill is invalidated so the frame is not partial. */
static int mb_on_touch(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (mb.win && mb.bl.on) widget_invalidate_force(mb.card, (void *)0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The radio: while a station owns the output the bar shows it (hciplayer plays it; stock's play queue still holds the last local song)
 */

#define MB_RADIO_CARD 0xff2e2c2cu /* radionp.c RN_CARD_GLYPH, #2C2C2E: the card of the radio glyph */
#define MB_GLYPH 16 /* the glyph's size on the cover: radionp's 96 of 264 px, scaled to MB_ART */

/* A local song is really playing or paused (an Error left standing after a session must not hide it): playing needs hciplayer's own word, paused is stock's status 3. */
static int mb_local_alive(void) {
    int ps = mclGetPlayStatus();
    return ps == 3 || (ps == MB_PLAYING && mclGetHciplayerStatus());
}

/* The bar shows the radio while a station connects, plays or is paused, and in Error or Stopped after a session (so a tap plays it again) unless local music took over. */
static int mb_radio(void) {
    if (rd_running()) return 1;
    if (!rd_list()->n || rd_at() >= rd_list()->n || mb_local_alive()) return 0;
    return rd_state() == RD_ERROR ||
           (rd_state() == RD_STOPPED &&
            rd_owns_bar()); /* a Stopped station stays on the bar (a tap plays it again) until a local track starts */
}

/* The station's favicon address ("" for none). */
static void mb_fav(const rd_list_t *l, int at, char *fav, unsigned n) {
    fav[0] = 0;
    if (l->n && at < l->n) rd_favicon(rd_info(l, at), fav, n);
}

/* The line under the station's name, with radio Now Playing's words (radionp.c rn_line); a playing stream is "Live" (the bar is narrow: the codec caption is Now Playing's). */
static void mb_radio_line(char *out, unsigned n) {
    int st = rd_state();
    if (st == RD_ERROR)
        snprintf(out, n, rd_error()[0] ? "%s: %s" : "%s", TR("Can't play"), rd_error());
    else if (st == RD_CONNECTING)
        snprintf(out, n, "%s", TR("Connecting…"));
    else if (st == RD_PAUSED)
        snprintf(out, n, "%s", TR("Paused"));
    else if (st == RD_STOPPED)
        snprintf(out, n, "%s", TR("Stopped"));
    else
        snprintf(out, n, "%s", TR("Live"));
}

static void mb_radio_labels(const rd_list_t *l, int at) {
    char line[200];
    const char *name = l->n && at < l->n ? rd_name(l, at) : "";
    mb_radio_line(line, sizeof line);
    widget_set_text_utf8(mb.title, name[0] ? name : TR("Radio"));
    widget_set_text_utf8(mb.artist, line);
    widget_invalidate_force(mb.card, (void *)0);
}

/* The station's cover into mb.bmp: its cached logo (the engine's logo worker makes the file; radionp.c rn_logo reads it the same way), else the radio glyph on radio Now Playing's card
 * grey, else the stock disc. A logo not cached yet starts the worker and asks for another look on the next ticks (mb.rlogo). */
static void mb_radio_cover(const rd_list_t *l, int at) {
    char fav[RD_FAV_MAX + 1], path[48], url[64];
    unsigned *px, g[MB_GLYPH * MB_GLYPH], i, x, y, o;
    int ok = 0, st;
    px = mb_art_begin(&mb.art);
    if (!px) return;
    mb.art.fkey = 0, mb.art.settle = 0, mb.rlogo = 0;
    mb_fav(l, at, fav, sizeof fav);
    if (fav[0]) {
        st = rd_logo_file(rd_logo_hash(fav), path, sizeof path);
        if (st == 1 && pc_cover_ok(path)) {
            snprintf(url, sizeof url, "file://%s", path);
            ok = cc_decode(mb.win, url, 1, MB_ART, 1, px);
        } else if (st == 0) {
            mb.rlogo = 1;
            if (!rd_logo_running()) rd_logo_start(fav);
        }
    }
    if (!ok) {
        for (i = 0; i < MB_ART * MB_ART; ++i) px[i] = MB_RADIO_CARD;
        memset(g, 0, sizeof g);
        if (cc_decode(mb.win, "pod_ic_rd_art", 0, MB_GLYPH, 1,
                      g)) { /* decoded over black: per channel the lighter of the glyph and the card */
            o = (MB_ART - MB_GLYPH) / 2;
            for (y = 0; y < MB_GLYPH; ++y)
                for (x = 0; x < MB_GLYPH; ++x) {
                    unsigned a = g[y * MB_GLYPH + x], b = px[(o + y) * MB_ART + o + x], c = 0xff000000u, k;
                    for (k = 0; k < 24; k += 8) c |= ((a >> k & 255) > (b >> k & 255) ? a : b) & (255u << k);
                    px[(o + y) * MB_ART + o + x] = c;
                }
        } else {
            for (i = 0; i < MB_ART * MB_ART; ++i) px[i] = MB_GREY;
            cc_decode(mb.win, "p_default", 0, MB_ART, 1, px);
        }
    }
    mb_art_end(&mb.art, px);
    widget_invalidate_force(mb.card, (void *)0);
}

static void mb_glyph(void) {
    int playing = mclGetPlayStatus() == MB_PLAYING;
    if (mb.radio) { /* the stop glyph (in the pause button) while connecting or playing; play when paused and in Error. Stock's status 3 / 2 leads the engine's tick, so a tap shows at once */
        int st = rd_state();
        playing = st == RD_CONNECTING || ((st == RD_PLAYING || st == RD_PAUSED) && mclGetPlayStatus() != 3);
    }
    if (playing == mb.playing) return;
    mb.playing = playing;
    mb_vis(mb.play, !playing);
    mb_vis(mb.pause, playing);
    widget_invalidate_force(mb.card, (void *)0); /* the whole pill, not the glyph's rectangle (see the blur) */
}

/* The radio's turn of mb_work: the station's name and state, its logo, no next button. The key is the station, the state and the error's words, so the labels are made again when one of
 * them changes and not every tick; the cover only for another station (or when a logo that was missing has arrived). */
static void mb_work_radio(void) {
    const rd_list_t *l = rd_list();
    int at = rd_at(), pending = 0;
    unsigned skey = l->n && at < l->n ? cc_fnv(FNV_SEED, rd_url(l, at)) : 0, key;
    char fav[RD_FAV_MAX + 1], path[48];
    skey |= !skey;
    key = cc_fnv((skey ^ (unsigned)rd_state()) * MB_HASH_PRIME, rd_error());
    key |= !key;
    if (!mb.radio) { /* from local to radio: nothing of the track stays */
        mb.radio = 1;
        mb.key = mb.rkey = 0;
        mb.art.settle = 0;
        mb_next_look(0); /* a live station has no next: the button stays, greyed and inert */
        mb_pause_look(1); /* and no pause: its slot stops the station */
    }
    if (!mb.shown || key != mb.key) {
        mb.key = key;
        mb_radio_labels(l, at);
    }
    mb_fav(l, at, fav, sizeof fav);
    if (mb.rlogo && fav[0]) {
        pending = rd_logo_file(rd_logo_hash(fav), path, sizeof path);
        if (pending == 0 && !rd_logo_running()) rd_logo_start(fav); /* (the worker was busy when the cover was made) */
    }
    if (!mb.shown || skey != mb.rkey || (mb.rlogo && fav[0] && pending != 0)) {
        mb.rkey = skey;
        mb_radio_cover(l, at);
    }
    if (!mb.shown) {
        mb.playing = -1;
        mb_show();
    }
    mb_glyph();
    if (mb.bl.fix) {
        mb.bl.fix = 0;
        widget_invalidate_force(mb.card, (void *)0);
    }
}

/* The one thing the timer does. */
static void mb_work(void) {
    void *t;
    unsigned key;
    if (mb_radio()) {
        mb_work_radio();
        return;
    }
    if (mb.radio) { /* the radio let go: the local track's bar again */
        mb.radio = 0;
        mb.key = mb.rkey = 0;
        mb.rlogo = 0;
        mb.playing = -1;
        mb_next_look(1);
        mb_pause_look(0);
    }
    t = cc_playing();
    if ((t && recent_note(t)) || mb.recent_pending) {
        mb.recent_pending = 0;
        recent_refresh();
    }
    if (!t) {
        mb_hide();
        return;
    }
    key = mb_track_key(t);
    if (!mb.shown || key != mb.key) {
        mb.key = key;
        mb_labels(t);
        mb_cover(t, 1);
    } else if (mb.art.settle > 0) {
        mb_settle(t);
    }
    if (!mb.shown) {
        mb.playing = -1;
        mb_show();
    }
    mb_glyph();
    if (mb.bl.fix) { /* a frame under the pill was partial: the whole pill again, so the blur is not seamed */
        mb.bl.fix = 0;
        widget_invalidate_force(mb.card, (void *)0);
    }
}

/* ---------------------------------------------------------------------------
 * The timer and the window's events
 */
static int mb_tick(const void *timer) {
    unsigned want;
    (void)timer;
    if (!mb.win || !mb.fg) {
        mb.timer = 0;
        return RET_OK;
    }
    want = pod_screen_lit() ? MB_TICK_MS : POD_DARK_MS;
    if (mb.timer && mb.interval != want && timer_modify(mb.timer, want) == RET_OK) mb.interval = want;
    if (!pod_screen_lit()) {
        if (recent_note(cc_playing())) mb.recent_pending = 1;
        return RET_REPEAT;
    }
    mb_work();
    return RET_REPEAT;
}

static int mb_first(const void *timer) {
    (void)timer;
    mb.timer = 0; /* this one ends with the return */
    if (!mb.win || !mb.fg) return RET_OK;
    mb.timer = timer_add(mb_tick, (void *)0, MB_TICK_MS);
    mb.interval = MB_TICK_MS;
    if (mb.timer) {
        if (pod_screen_lit())
            mb_work();
        else if (recent_note(cc_playing()))
            mb.recent_pending = 1;
    }
    return RET_OK;
}

static void mb_unarm(void) {
    if (mb.timer) timer_remove(mb.timer);
    mb.timer = 0;
}

static void mb_stop(void) {
    mb_unarm();
    mb_art_free(&mb.art);
    mb_blur_free(&mb.bl);
    memset(&mb, 0, sizeof mb);
}

static int mb_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == mb.win) mb_stop(); /* an earlier window's end leaves the new one alone */
    return RET_OK;
}

static int mb_on_background(void *ctx, void *e) {
    (void)e;
    if (!mb.win || ctx != mb.win) return RET_OK;
    mb.fg = 0;
    mb_unarm();
    return RET_OK;
}

static int mb_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!mb.win || ctx != mb.win) return RET_OK;
    mb.fg = 1;
    if (!mb.timer) mb.timer = timer_add(mb_first, (void *)0, MB_FIRST_MS);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch
 */
static int mb_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!mb.win) return RET_OK;
    if (mb.radio) { /* a station has no pause here: Stop while it connects or plays, Play resumes a pause made elsewhere (the engine's tick reconciles Paused with stock's status 3) */
        switch (rd_state()) {
        case RD_PAUSED:
            rd_resume();
            break;
        case RD_PLAYING:
        case RD_CONNECTING:
            rd_stop();
            break;
        case RD_ERROR:
        case RD_STOPPED:
            if (rd_list()->n) rd_play(rd_list(), rd_at()); /* a retry of the same station */
            break;
        default:
            break;
        }
        mb_work();
        return RET_OK;
    }
    playpause_quick_click();
    mb_glyph();
    return RET_OK;
}

/* The card: radio Now Playing while the bar shows the radio (also in Error, which stock's entry hook does not take), else Now Playing as the menu's row opens it. */
static int mb_on_card(void *ctx, void *e) {
    if (mb.radio && rn_open() == 0) return RET_OK;
    return pod_on_player(ctx, e);
}

/* next_quick_click reads the event's time (it ignores a click within a second of the last); the click's own event is
 * what the stock handlers pass. */
static int mb_on_next(void *ctx, void *e) {
    unsigned ev[4];
    (void)ctx;
    if (!mb.win || mb.radio) return RET_OK; /* (greyed and insensitive for a station: nothing to skip to) */
    if (!e) {
        memset(ev, 0, sizeof ev);
        ev[2] = time_now_ms();
        e = ev;
    }
    next_quick_click(e, 0);
    mb_work();
    return RET_OK;
}

/* The backdrop blur is optional and last: the plane, the paint handler and the press handlers. Anything missing (an SD file turns it off, no memory,
 * a refused registration) and the page has the glass over the sharp rows. */
static void mb_blur_setup(void) {
    static void *const *btn[4] = {
        &mb.play, &mb.pause, &mb.next,
        &mb.sv}; /* the buttons, and the list (a row's press highlight repaints only the row) */
    static const int ev[3] = {EVT_POINTER_DOWN, EVT_POINTER_UP, EVT_POINTER_ABORT};
    int ok, i, j;
    if (!mb_blur_alloc(&mb.bl)) return;
    ok = widget_on(mb.card, EVT_BEFORE_PAINT, mb_on_before_paint, (void *)0);
    ok = ok && widget_on(mb.sv, EVT_SCROLL, mb_on_scroll, (void *)0);
    for (i = 0; ok && i < 4; ++i)
        for (j = 0; ok && j < 3; ++j) ok = widget_on(*btn[i], ev[j], mb_on_touch, (void *)0) != 0;
    if (ok)
        mb_blur_enable(&mb.bl);
    else
        mb_blur_free(&mb.bl);
}

/* The Home instance of the menu is up (patch/home.c, after the list took the whole window). */
void minibar_start(void *win) {
    void *fade;
    if (!win) return;
    /* the Home instance has no navbar (home.c hid it): the fade under the bar (img_nb_fade, a sibling of the list at y 50) goes with it, or it would
     * float over the list as a dark band with a sharp top edge (V2.1oAB device). Hidden and insensitive, as the bar. */
    fade = widget_lookup(win, "img_nb_fade", 1);
    if (fade) {
        widget_set_visible(fade, 0, 0);
        widget_set_sensitive(fade, 0);
    }
    if (mb.win) mb_stop(); /* an earlier window that never said it was gone */
    mb.win = win;
    mb.bar = widget_lookup(win, "pod_minibar", 1);
    mb.card = widget_lookup(win, "pod_mb_card", 1);
    mb.title = widget_lookup(win, "pod_mb_title", 1);
    mb.artist = widget_lookup(win, "pod_mb_artist", 1);
    mb.play = widget_lookup(win, "pod_mb_play", 1);
    mb.pause = widget_lookup(win, "pod_mb_pause", 1);
    mb.next = widget_lookup(win, "pod_mb_next", 1);
    mb.sv = widget_lookup(win, "pod_scrollview", 1);
    mb.pad = widget_lookup(win, "pod_pad", 1);
    mb.playing = -1;
    mb.fg = 1;
    if (!mb.bar || !mb.card || !mb.title || !mb.artist || !mb.play || !mb.pause || !mb.next || !mb.sv || !mb.pad ||
        !widget_on(win, EVT_DESTROY, mb_on_destroy, win) || !widget_on(win, EVT_WINDOW_TO_BG, mb_on_background, win) ||
        !widget_on(win, EVT_WINDOW_TO_FG, mb_on_foreground, win) ||
        !widget_on(mb.card, EVT_AFTER_PAINT, mb_on_paint, (void *)0) ||
        !widget_on(mb.card, EVT_CLICK, mb_on_card, (void *)0) ||
        !widget_on(mb.play, EVT_CLICK, mb_on_play, (void *)0) ||
        !widget_on(mb.pause, EVT_CLICK, mb_on_play, (void *)0) ||
        !widget_on(mb.next, EVT_CLICK, mb_on_next, (void *)0)) {
        mb_stop(); /* a handler that was registered finds no window of ours any more */
        return;
    }
    mb.timer = timer_add(mb_first, (void *)0, MB_FIRST_MS);
    if (!mb.timer) {
        mb_stop();
        return;
    }
    mb_blur_setup();
}
