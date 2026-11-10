/* M1+ Music iPod: a virtual iPod Classic. A fullscreen page with the iPod screen on top and a touch click wheel below.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/ipod.md has the design. The page is ui/m1plus_ipod.bin (tools/pod_ui.py build_ipod_page): a fullscreen window (320 x 480, so the stock
 * status bar is not drawn, as the lock screen's) holding the view ipod_screen (320 x 240, insensitive; the payload paints it in its own EVT_AFTER_PAINT:
 * title bar, rows, cover pane, Now Playing screen) and the view ipod_wheel (220 x 220, the touch target; its child image is the drawn wheel, insensitive),
 * and the hidden labels that only carry the text styles. No hook, no widget per row: everything runs from the page's widgets, its window events and ONE
 * page-scoped timer (the battery, the play state and the track), exactly the precedents of Albums, Songs, the mini player bar and Cover Flow.
 *
 *   levels     a small stack (IP_DEPTH): the main menu, then Albums / Artists / Songs / Playlists, an artist's albums, an album's or a playlist's tracks, and Now
 *              Playing. A list level keeps only its row cursor (sel, top); its rows are read from the stock list (*pdeq_showlist, or *pdeq_playlist) while it
 *              is the list the stock queries last made (ip_valid: the pointer, the size and the first record, as the Songs page checks); anything else gets its
 *              query run again (ip_run: the chain of ancestors, as the stock pages do) when the page is in front, from a step, a tap or the window coming back.
 *              The rows are never read from a stale list.
 *   wheel      the touch on the ring. The finger's angle (ip_angle, integer atan) around the wheel's centre turns one step every IP_STEP (15 degrees); a touch
 *              that turns no step and travels less than IP_TAP_PX is a tap: the centre button selects, the ring's four sectors are MENU (top), previous (left),
 *              next (right) and play / pause (bottom). Outside the ring's circle a touch does nothing (the view is square). The view grabs the touch.
 *   play       a track opens the stock way: loadSongList of the shown list, start_player (what the stock Play all button calls), Now Playing level.
 *   sound      none: docs/modules/ipod.md "The click sound" has the evidence and the options.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "ipod_theme.h"
#include "ipod_render.h"
#undef widget_prepare_text_style
#undef canvas_draw_text_in_rect
#undef canvas_draw_image
#define widget_prepare_text_style ip_render_prepare
#define canvas_draw_text_in_rect ip_render_text
#define canvas_draw_image ip_render_image
#include "common.h"
#include "i18n.h"
#include "podcasts.h"

extern unsigned np_file_key(const char *path); /* patch/nowplaying.c: a hash of the picture file, 0 if unreadable */
extern const char *
np_cover_file(int *busy); /* the /tmp file of the playing track's cover, NULL for none; busy while demo makes it */
extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern int pod_open_settings(void); /* patch/m1plus.c: the Settings page */
extern unsigned pod_rand(unsigned n); /* patch/shuffle.c: the shuffle generator (seeded once) */
extern void pod_set_mode(int mode); /* patch/shuffle.c: the stock play mode, set as the Play settings page does */
extern void *pg_episode_queue(
    const char *root, const pc_show_t *s, const pc_ep_t *eps, int neps, int at,
    int *idx); /* patch/podcasts.c: the queue of a show's local episodes, set up as an episode start does */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play */
/* patch/ipod_cf.c: the Cover Flow screen (level K_CF: the albums list drawn as covers; docs/modules/ipod-coverflow.md) */
extern int ipcf_open(void *win), ipcf_up(void), ipcf_busy(void), ipcf_tick(void *list, unsigned count);
extern void ipcf_close(void), ipcf_goto(int sel), ipcf_paint(void *canvas, void *list, unsigned count, void *style);

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define ART_GREY 0xff2b2b2bu

enum {
    K_MAIN,
    K_MUSIC,
    K_ALBUMS,
    K_ARTISTS,
    K_SONGS,
    K_PLAYLISTS,
    K_ARTIST_ALBUMS,
    K_TRACKS,
    K_PL_TRACKS,
    K_NOW,
    K_SETTINGS,
    K_CF,
    K_PODCASTS,
    K_PC_EPS
};
enum { S_SHUFFLE, S_REPEAT, S_APPEARANCE, S_COUNT };
enum { M_COVER, M_ALBUMS, M_ARTISTS, M_SONGS, M_PLAYLISTS, M_SHUFFLE, M_COUNT };
enum { ROOT_MUSIC, ROOT_COVER, ROOT_PODCASTS, ROOT_SHUFFLE, ROOT_NOW, ROOT_SETTINGS, ROOT_COUNT };
enum { R_NONE, R_CENTRE, R_RING };

static const char *const MAIN_KEYS[ROOT_COUNT] = {"Music",         "Cover Flow",  "Podcasts",
                                                  "Shuffle Songs", "Now Playing", "cdrippersettings"};
static const char *const MUSIC_KEYS[M_COUNT] = {"Cover Flow", "Albums",    "Artists",
                                                "Songs",      "Playlists", "Shuffle Songs"};
static const char *const SET_KEYS[S_COUNT] = {"Shuffle", "Repeat", "Appearance"};
static const char *const MODE_ICONS[4] = {"ipod_mode_shuffle", "ipod_mode_repeat", "ipod_mode_repeat1",
                                          "ipod_playing"}; /* the play mode marks, then the playing track's speaker */
static void *ip_mode_bitmap(int i);
static void ip_pc_play(int at);
#define IP_NP_GONE 3 /* looks without a current track before Now Playing says Not Playing */

struct lvl {
    int kind, sel, top;
    char title
        [40]; /* the title bar's text for a list opened from a record (an album, an artist, a playlist); empty: the level's own name */
};

#define IP_ROW_ART 54 /* the cover fills the row exactly (IP_TALL_H): stacked covers leave no seam */
struct row_art {
    void *bmp;
    int kind, index;
    unsigned id, key[4], parts, drawn, waiting;
    char *path[4];
};

static struct {
    void *win, *screen, *wheel;
    void *st_row, *st_sel, *st_title, *st_small, *st_subsel, *st_np1, *st_np2, *st_time, *st_val,
        *st_np3; /* hidden labels: the text styles */
    struct lvl st[IP_DEPTH];
    pc_show_t *
        pc_shows; /* the Podcasts level's shows (those with an episode file; compacted) and the open show's local episodes: malloc'd while their levels are in the stack */
    pc_ep_t *pc_eps;
    int pc_n, pc_neps;
    int depth; /* index of the level in front */
    void *list; /* the stock list the front level's rows are read from (valid while it is still the current one) */
    void *first;
    unsigned count;
    int cls; /* the class of the tracks listed (stock: classinfo[0] after the query) */
    unsigned timer;
    int fg;
    /* the wheel */
    int touch; /* R_NONE, R_CENTRE, R_RING */
    int sx, sy, lx, ly; /* the start and the last point, wheel coordinates relative to the centre */
    int last, acc; /* the last angle (sixteenths of a degree) and the unspent turn */
    int turned, far; /* a step was made / the finger travelled IP_TAP_PX or more */
    int menu_zone, long_done; /* the touch began on the MENU sector; a long press already popped to the main menu */
    unsigned down_t; /* the time of that touch (ms) */
    int dir, rev; /* the committed turn direction (+1 / -1, 0 none) and the reverse travel since (sixteenths) */
    int speed, fast; /* smoothed angular speed (sixteenths a second); whether it has been above IP_FAST since fast_t0 */
    unsigned lt, fast_t0; /* the time of the last move; the time the speed went above IP_FAST (event times, ms) */
    /* what the screen shows besides the lists, and the signature of it */
    void *art, *np_refl; /* the decoded square cover, and its reflection (IP_ART x IP_NP_REFLECT, made with it) */
    void *shadow; /* the menu half's shadow on the pane (IP_SHADOW_W x IP_PANE_H, straight-alpha black), made at open */
    int no_shadow; /* a pass of the split close that must not draw it (the right half moves apart from the menu) */
    int np_valid; /* np_refl holds the current cover's reflection */
    unsigned track; /* the track the cover was made for (a hash), 0 none */
    unsigned fkey; /* the hash of the /tmp cover file it was made from, 0 when it was not */
    int settle;
    int now_shown; /* the main menu has its Now Playing row (something plays or is paused) */
    int np_have, np_gone, np_pos,
        np_len; /* Now Playing: the text of the last track is kept, looks without a track, the last valid position and length ... */
    unsigned np_key; /* ... and the track (ip.track) they belong to */
    char np_text[3][64]; /* title, artist, album of the last track */
    void *mode_bmp[4]; /* the play mode marks (ip_mode_bitmap), made on first use */
    unsigned mode_tried; /* bit i: mark i was tried (a failure is not retried) */
    unsigned
        ival; /* the page timer's interval now (IPCF_FRAME_MS, IP_DRIFT_MS or IP_TICK_MS); timer_modify changes it */
    unsigned lookn; /* fast ticks since the last ip_look */
    struct row_art rows[4];
    int row_worker; /* only stop the shared builder when this page owns it */
    /* the split pages' cover pane: two cover slots, each panning slowly, cross-faded every IP_PANE_HOLD_MS (the reference's artwork pane) */
    struct {
        void *bmp[2]; /* the covers, IP_PANE_ART square RGBA each, made on first use */
        void *mix; /* the pane-sized frame of a cross-fade (both covers mixed on the timer, never in paint) */
        int have[2]; /* bmp[i] holds key[i]'s cover (or the disc) */
        unsigned key[2]; /* the album each slot shows (0 = the placeholder, still) */
        unsigned ms[2]; /* each slot's pan phase: time since it began, ms */
        int rev[2]; /* the pan runs from the right to the left (every other cover) */
        int cur, fading, next_ready, picked, mix_ok, mix_bad;
        unsigned fade_ms,
            cycle; /* time since the cross-fade began; time since the last one began (the next is due at IP_PANE_HOLD_MS) */
        unsigned t0, bad; /* the time of the last step; an album whose cover would not decode (not tried again) */
        unsigned pk; /* the playing album's key the last look saw, and whether it has a cached cover */
        int pk_art;
        unsigned rot
            [IP_PANE_KEYS]; /* the random albums with a cached cover that rotate while nothing with one plays; drawn once a visit of the main menu */
        int rot_n, rot_i;
        char rot_trk[IP_PANE_KEYS][96]; /* the first track of each rotation album: the extractor's input */
        unsigned char lvl
            [2]; /* where slot s' picture came from: 0 the 168 px cache file, 1 demo's full-resolution file of the playing track, 2 a transient extraction (both box-filtered to IP_PANE_ART) */
        int xfer,
            worker; /* xfer: 1 a transient extraction of the next rotation cover runs on the shared worker, 2 it finished; worker: this page holds the job set */
        unsigned xfer_key, up_wait, trk_ms,
            trk; /* the playing track's key as the pane last saw it; * the album it is for; ms until the sharp picture of the playing album is looked for again; when the track last changed */
        int busy_seen,
            upgrade; /* demo was seen making a cover since the track changed; the next fade is the same album sharpened (same phase) */
        int px; /* the shown slot's pan place the frame was built at, in 1/256 px (0 .. IP_PANE_R * 256) */
    } pane;
    /* the pane while the main menu's Podcasts row is the selection: the picture ipod_podcasts (IP_PANE_W x IP_PANE_H, loaded on the first look, kept while the page
     * lives), and No Podcasts under it when no show folder has an episode file (pc_any: -1 not looked yet this visit of the main menu, else pc_any_episode) */
    unsigned pc_img[32]; /* bitmap_t is 0x48 bytes */
    int pc_img_ok, pc_any;
    unsigned sig[5]; /* the last painted values of the timer's look: battery, play state, track, position, queue */
} ip __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Small helpers
 */
static unsigned ip_len(const char *s) {
    unsigned n = 0;
    while (s[n]) n++;
    return n;
}

static unsigned ip_lerp(unsigned a, unsigned b, int i,
                        int n) { /* the colour a .. b (r | g << 8 | b << 16) at i of n - 1 */
    unsigned c = 0, k;
    for (k = 0; k < 24; k += 8) {
        int x = (int)(a >> k & 255), y = (int)(b >> k & 255);
        c |= (unsigned)(x + (y - x) * i / (n > 1 ? n - 1 : 1)) << k;
    }
    return c;
}

static void ip_fill(void *canvas, int x, int y, int w, int h, unsigned rgb) { ip_render_fill(canvas, x, y, w, h, rgb); }

static unsigned ip_stops(const unsigned *c, const unsigned char *at, int n, int y, int h) {
    int p = h > 1 ? y * 100 / (h - 1) : 0, i;
    for (i = 1; i < n && p > at[i]; ++i) {
    }
    if (i >= n) return c[n - 1];
    return ip_lerp(c[i - 1], c[i], p - at[i - 1], at[i] - at[i - 1] + 1);
}

static void ip_selection(void *canvas, int w, int y, int h) {
    static const unsigned colors[] = {0xe3ab3eu, 0xe0a037u, 0xdc972cu, 0xd68c21u, 0xd38415u};
    static const unsigned char at[] = {0, 25, 50, 75, 100};
    int i;
    for (i = 0; i < h; ++i)
        ip_fill(canvas, 0, y + i, w, 1, i == 0 ? 0xf8dd9au : i == h - 1 ? 0x814f15u : ip_stops(colors, at, 5, i, h));
}

static void ip_header(void *canvas, int w) {
    const struct ip_theme_palette *p = ip_theme_colors();
    static const unsigned char at[] = {0, 42, 47, 100};
    int i;
    for (i = 0; i < IP_BAR_H - 1; ++i) ip_fill(canvas, 0, i, w, 1, ip_stops(p->header, at, 4, i, IP_BAR_H - 1));
    ip_fill(canvas, 0, IP_BAR_H - 1, w, 1, p->header_rule);
}

static void ip_pc_pane_look(void);
static void ip_redraw(void) {
    ip_pc_pane_look();
    if (ip.screen) widget_invalidate_force(ip.screen, (void *)0);
}

/* Only the cover pane's rectangle (x IP_PANE_X .., the pane's height: the menu's shadow lies inside it): widget_invalidate_force ends in widget_invalidate with the rectangle it is
 * given (the widget's own coordinates, 16 bytes x, y, w, h: docs/modules/addresses.md). A pan or fade frame repaints no menu text. */
static void ip_redraw_pane(void) {
    int r[4];
    r[0] = IP_PANE_X, r[1] = 0, r[2] = IP_PANE_W, r[3] = IP_PANE_H;
    if (ip.screen) widget_invalidate_force(ip.screen, r);
}

/* The main menu's Now Playing row is there only while something plays or is paused (the reference's). Rows after it move up when it is hidden. */
static int ip_now_shown(void) {
    int s = mclGetPlayStatus();
    return s == 2 || s == 3;
}
static int ip_root_id(int row) { return row >= ROOT_NOW && !ip_now_shown() ? row + 1 : row; }

static int ip_is_list(int kind) { return kind != K_MAIN && kind != K_MUSIC && kind != K_NOW && kind != K_SETTINGS; }
static int ip_is_pc(int kind) {
    return kind == K_PODCASTS || kind == K_PC_EPS;
} /* lists of our own (pcmodel), not stock deques */
static int ip_tall(int kind) {
    return kind == K_ALBUMS || kind == K_ARTIST_ALBUMS || kind == K_PLAYLISTS;
} /* cover rows; song lists are plain text rows */
static int ip_split(int kind) { return kind == K_MAIN || kind == K_MUSIC || kind == K_SETTINGS; }
static int ip_is_tracks(int kind) { return kind == K_SONGS || kind == K_TRACKS || kind == K_PL_TRACKS; }
static struct lvl *ip_top(void) { return &ip.st[ip.depth]; }

/* The main menu's Podcasts row is the selection: the pane shows the podcasts picture, not the covers (the reference's). */
static int ip_pc_pane(void) { return ip_top()->kind == K_MAIN && ip_root_id(ip_top()->sel) == ROOT_PODCASTS; }

/* What that pane needs, looked once before it is painted (never in paint): the picture, and whether any show has an episode file (once a visit of the main menu). */
static void ip_pc_pane_look(void) {
    if (!ip.win || !ip_pc_pane()) return;
    if (!ip.pc_img_ok) ip.pc_img_ok = !widget_load_image(ip.win, "ipod_podcasts", ip.pc_img);
    if (ip.pc_any < 0) ip.pc_any = pc_any_episode();
}

/* The wide string cut with an ellipsis to maxw px (the canvas has the text's style): grid.c's search. Its length. At most 63 characters are read. */
unsigned ip_fit(void *canvas, unsigned *s, int maxw) {
    unsigned len = 0, lo, hi, ellipsis = ELLIPSIS;
    while (s[len]) len++;
    if (maxw <= 0) return 0;
    if (len && (int)(canvas_measure_text(canvas, s, len) + 0.999f) > maxw) {
        if ((int)(canvas_measure_text(canvas, &ellipsis, 1) + 0.999f) > maxw) return 0;
        lo = 0, hi = len - 1;
        while (lo < hi) {
            unsigned mid = (lo + hi + 1) / 2, keep = s[mid];
            s[mid] = ellipsis;
            if ((int)(canvas_measure_text(canvas, s, mid + 1) + 0.999f) <= maxw)
                lo = mid;
            else
                hi = mid - 1;
            s[mid] = keep;
        }
        s[lo] = ellipsis;
        s[lo + 1] = 0;
        len = lo + 1;
    }
    return len;
}

/* Text in rect (x, y, w, h) with the style the canvas has (widget_prepare_text_style was called), cut to w. */
static void ip_text(void *canvas, const char *utf8, int x, int y, int w, int h) {
    unsigned wide[64], n;
    int rect[4];
    n = ip_len(utf8);
    if (!n) return;
    tk_utf8_to_utf16_ex(utf8, n, wide, 64);
    n = ip_fit(canvas, wide, w);
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    if (n) canvas_draw_text_in_rect(canvas, wide, n, rect);
}

/* ---------------------------------------------------------------------------
 * The wheel's angle. Sixteenths of a degree, clockwise from 12 o'clock (0 .. 5759). atan(x) = x / (1 + 0.28125 x^2) radians for 0 <= x <= 1 (error under
 * 0.1 degree), in Q10; the octants are folded onto it. Pure integer code, so the emulation tests check it against math.atan2.
 */
__attribute__((noinline)) int ip_angle(int dx, int dy) {
    unsigned ax = (unsigned)(dx < 0 ? -dx : dx), ay = (unsigned)(dy < 0 ? -dy : dy), lo = ax < ay ? ax : ay,
             hi = ax < ay ? ay : ax, t, d, a;
    if (!hi) return 0;
    t = (lo << 10) / hi; /* tan of the angle from the nearer axis, Q10, 0 .. 1024 */
    d = 1024 + ((288u * t * t) >> 20);
    a = (t << 10) / d; /* radians, Q10 */
    a = a * 917u >> 10; /* sixteenths of a degree: 16 * 180 / pi = 917.7 */
    /* a = atan(lo / hi): the angle from the vertical axis when |dx| <= |dy|, else from the horizontal one. dy < 0 is up; 90 degrees = 1440 (right), 270 = 4320 (left) */
    if (ax > ay)
        a = dx > 0 ? (dy < 0 ? 1440 - a : 1440 + a) : (dy < 0 ? 4320 + a : 4320 - a);
    else
        a = dy < 0 ? (dx >= 0 ? a : 5760 - a) : (dx >= 0 ? 2880 - a : 2880 + a);
    return (int)(a % 5760u);
}

/* The turn from angle a to b: the shorter way, -2880 .. 2879. */
__attribute__((noinline)) int ip_turn(int a, int b) {
    int d = b - a;
    if (d >= 2880) d -= 5760;
    if (d < -2880) d += 5760;
    return d;
}

/* Whether the chord from (ax, ay) to (bx, by) passes within IP_DEAD_R of the origin (coordinates clamped to +-150 by the caller: the cross product squared must
 * fit 32 bits). Integer: |a x b|^2 < R^2 |b - a|^2 inside the segment, else the nearer end. */
__attribute__((noinline)) int ip_chord_near(int ax, int ay, int bx, int by) {
    int dx = bx - ax, dy = by - ay, t = -(ax * dx + ay * dy), len2 = dx * dx + dy * dy, cross;
    unsigned c2;
    if (len2 == 0 || t <= 0) return ax * ax + ay * ay < IP_DEAD_R * IP_DEAD_R;
    if (t >= len2) return bx * bx + by * by < IP_DEAD_R * IP_DEAD_R;
    cross = ax * by - ay * bx;
    c2 = (unsigned)(cross * cross);
    return c2 < (unsigned)(IP_DEAD_R * IP_DEAD_R) * (unsigned)len2;
}

/* The wheel's memory of a drag goes (a new target or list, a new touch): the unspent turn, the direction, the speed, the tier. */
static void ip_wheel_reset(void) { ip.acc = ip.dir = ip.rev = ip.speed = ip.fast = 0; }

/* ---------------------------------------------------------------------------
 * The stock lists
 */
static void *ip_stock_list(int kind) {
    if (ip_is_pc(kind)) return kind == K_PODCASTS ? (void *)ip.pc_shows : (void *)ip.pc_eps;
    return *(void **)(kind == K_PLAYLISTS ? PDEQ_PLAYLIST : PDEQ_SHOWLIST);
}

static void ip_pc_free(void) {
    free(ip.pc_shows);
    free(ip.pc_eps);
    ip.pc_shows = (pc_show_t *)0, ip.pc_eps = (pc_ep_t *)0;
    ip.pc_n = ip.pc_neps = 0;
}

/* The model of the front Podcasts level, read again: the shows with an episode file in the Podcasts page's order, or the open show's local episodes (newest first). Levels behind keep what they need (the
 * shows stay while an episode list is open); what no level in the stack shows is freed. 1 when the level's list exists. */
static int ip_pc_run(int d) {
    int k, m = 0;
    int kind = ip.st[d].kind;
    if (kind != K_PC_EPS) {
        free(ip.pc_eps);
        ip.pc_eps = (pc_ep_t *)0, ip.pc_neps = 0;
    }
    if (kind == K_PODCASTS) {
        pc_show_t *all = calloc(PC_MAX_SHOWS, sizeof *all);
        int n;
        free(ip.pc_shows);
        ip.pc_shows = all, ip.pc_n = 0;
        if (!all) return 0;
        n = pc_scan_shows(all, PC_MAX_SHOWS);
        for (k = 0; k < n; ++k)
            if (all[k].count) memcpy(&all[m++], &all[k], sizeof *all);
        ip.pc_n = m;
        return 1;
    }
    {
        pc_ep_t *all;
        int n;
        free(ip.pc_eps);
        ip.pc_eps = (pc_ep_t *)0, ip.pc_neps = 0;
        if (d < 1 || ip.st[d - 1].kind != K_PODCASTS || !ip.pc_shows || ip.st[d - 1].sel >= ip.pc_n) return 0;
        all = calloc(PC_MAX_EPS, sizeof *all);
        if (!all) return 0;
        n = pc_load_show(&ip.pc_shows[ip.st[d - 1].sel], all, PC_MAX_EPS);
        for (k = 0; k < n; ++k)
            if (all[k].state == PC_LOCAL) memcpy(&all[m++], &all[k], sizeof *all);
        ip.pc_eps = all, ip.pc_neps = m;
        return 1;
    }
}

/* Nothing of the model is kept once no level in the stack is a Podcasts one (called before every level's list is read). */
static void ip_pc_trim(void) {
    int k, keep = 0;
    for (k = 1; k <= ip.depth; ++k) keep |= ip.st[k].kind == K_PODCASTS;
    if (!keep) ip_pc_free();
}

static int ip_pc_count(int kind) { return kind == K_PODCASTS ? ip.pc_n : ip.pc_neps; }

/* The stock record behind display row i of a list. An artist's albums are shown with the stock "All songs" record FIRST (the stock list has it last): row 0 is that record, rows 1 ..
 * the albums in the stock order. Everything that reads a row of such a list (its text, its cover, a tap, the query of its songs) goes through here. */
static int ip_stock_index(int kind, void *list, int i) {
    unsigned n, k;
    if (kind != K_ARTIST_ALBUMS || !list) return i;
    n = deque_size(list);
    for (k = 0; k < n && I(deque_at(list, k), REC_ID) != ID_ALL_SONGS; ++k) {
    }
    if (k >= n) return i;
    return i == 0 ? (int)k : i - 1 < (int)k ? i - 1 : i;
}

static void *ip_rec(int kind, void *list, int i) { return deque_at(list, (unsigned)ip_stock_index(kind, list, i)); }

static int ip_valid(void) {
    void *cur;
    if (!ip_is_list(ip_top()->kind)) return 1;
    cur = ip_stock_list(ip_top()->kind);
    if (ip_is_pc(ip_top()->kind)) return cur && ip.list == cur && ip.count == (unsigned)ip_pc_count(ip_top()->kind);
    return ip.list && cur == ip.list && deque_size(cur) == ip.count && (!ip.count || deque_at(cur, 0) == ip.first);
}

/* The query of level d (its ancestors first: an artist's albums need the artists list, a track list the albums list). 1 when the level's list exists. */
static int ip_run(int d) {
    struct lvl *l = &ip.st[d];
    void *par;
    if (ip_is_pc(l->kind)) return ip_pc_run(d);
    switch (l->kind) {
    case K_ALBUMS:
    case K_CF:
        loadLocalClassList(CLASS_ALBUMS);
        break;
    case K_ARTISTS:
        loadLocalClassList(CLASS_ARTISTS);
        break;
    case K_SONGS:
        loadLocalClassList(CLASS_ALL_SONGS);
        break;
    case K_PLAYLISTS:
        loadLocalClassList(CLASS_PLAYLISTS);
        break;
    case K_ARTIST_ALBUMS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(ip.st[d - 1].kind);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        loadAlbumList(CLASS_ARTISTS, deque_at(par, (unsigned)ip.st[d - 1].sel));
        break;
    case K_TRACKS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(ip.st[d - 1].kind);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        if (ip.st[d - 1].kind ==
            K_ARTISTS) { /* an artist with one album: its songs, the album list skipped (loadAlbumList, then the album's own record) */
            unsigned k, n;
            void *alb = (void *)0;
            loadAlbumList(CLASS_ARTISTS, deque_at(par, (unsigned)ip.st[d - 1].sel));
            par = *(void **)PDEQ_SHOWLIST;
            n = par ? deque_size(par) : 0;
            for (k = 0; k < n && !alb; ++k)
                if (I(deque_at(par, k), REC_ID) != ID_ALL_SONGS) alb = deque_at(par, k);
            if (!alb) return 0;
            loadAlbumdetailList(CLASS_ARTIST_ALBUMS, alb);
        } else
            loadAlbumdetailList(ip.st[d - 1].kind == K_ALBUMS || ip.st[d - 1].kind == K_CF ? CLASS_ALBUMS
                                                                                           : CLASS_ARTIST_ALBUMS,
                                ip_rec(ip.st[d - 1].kind, par, ip.st[d - 1].sel));
        *(int *)G_CLASS_TYPE = *(int *)CLASSINFO; /* as albuminfo_page_init leaves it */
        break;
    case K_PL_TRACKS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(K_PLAYLISTS);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        *(int *)(CLASSINFO + CLASSINFO_ARG) =
            I(deque_at(par, (unsigned)ip.st[d - 1].sel), REC_DISC); /* what the stock row tap leaves (@0x53d5f4) */
        loadLocalClassList(CLASS_PLAYLIST_SONGS);
        break;
    default:
        return 1;
    }
    return ip_stock_list(l->kind) != (void *)0;
}

/* Level d = the front one, its list read again from the stock queries. */
static void ip_load(void) {
    struct lvl *l = ip_top();
    void *list;
    ip.list = ip.first = (void *)0;
    ip.count = 0;
    ip_pc_trim();
    if (!ip_is_list(l->kind)) return;
    if (ip_run(ip.depth) && (list = ip_stock_list(l->kind)) != (void *)0) {
        ip.list = list, ip.count = ip_is_pc(l->kind) ? (unsigned)ip_pc_count(l->kind) : deque_size(list);
        ip.first = ip.count && !ip_is_pc(l->kind) ? deque_at(list, 0) : (void *)0;
        ip.cls = ip_is_tracks(l->kind) ? (l->kind == K_SONGS       ? CLASS_ALL_SONGS
                                          : l->kind == K_PL_TRACKS ? CLASS_PLAYLIST_SONGS
                                                                   : *(int *)CLASSINFO)
                                       : 0;
    }
    if (l->sel >= (int)ip.count) l->sel = ip.count ? (int)ip.count - 1 : 0;
    if (l->top > l->sel) l->top = l->sel;
    if (l->top < 0) l->top = 0;
}

/* The page is in front and its list went stale (another page queried): read it again. Returns whether the rows can be read now. */
static int ip_ensure(void) {
    if (ip_valid()) return 1;
    if (!pod_is_top(ip.win)) return 0;
    ip_load();
    return ip_valid();
}

static const char *ip_row_text(int kind, int i) {
    void *rec;
    const char *s;
    if (kind == K_MAIN) return TR(MAIN_KEYS[ip_root_id(i)]);
    if (kind == K_MUSIC) return TR(MUSIC_KEYS[i]);
    if (kind == K_SETTINGS) return TR(SET_KEYS[i]);
    if (kind == K_PODCASTS) return ip.pc_shows[i].title[0] ? ip.pc_shows[i].title : ip.pc_shows[i].dir;
    if (kind == K_PC_EPS) return ip.pc_eps[i].title[0] ? ip.pc_eps[i].title : ip.pc_eps[i].file;
    rec = ip_rec(kind, ip.list, i);
    if (kind == K_ALBUMS || kind == K_ARTIST_ALBUMS) {
        if (I(rec, REC_ID) == ID_ALL_SONGS)
            return TR(kind == K_ARTIST_ALBUMS ? "local_allsong" : "All albums"); /* the stock "All Songs" */
        s = cc_str(rec, REC_ALBUM);
    } else if (kind == K_ARTISTS || kind == K_PLAYLISTS)
        s = cc_str(rec, REC_TITLE);
    else {
        s = cc_str(rec, REC_TITLE);
        if (!*s) s = cc_str(rec, REC_NAME);
    }
    return *s ? s : "-";
}

static int ip_rows(void) {
    return ip_top()->kind == K_MAIN       ? ROOT_COUNT - !ip_now_shown()
           : ip_top()->kind == K_MUSIC    ? M_COUNT
           : ip_top()->kind == K_SETTINGS ? S_COUNT
                                          : (int)ip.count;
}

/* ---------------------------------------------------------------------------
 * The cover (decoded on the timer, never in paint) and the battery reading
 */
static unsigned ip_track_key(void *t) {
    unsigned h = cc_fnv(cc_fnv(cc_fnv(FNV_SEED, cc_str(t, REC_PATH)), cc_str(t, REC_TITLE)), cc_str(t, REC_NAME));
    return h | !h;
}

/* The cover's reflection, made once when the cover changes: the cover itself is drawn flat and square (a straight copy, no transform). The IP_NP_REFLECT rows under it are a
 * mirror of its last rows, 30 % opaque next to the cover and fading out, mixed into the screen colour (an opaque bitmap IP_ART x IP_NP_REFLECT). */
__attribute__((noinline)) void ip_reflect(const unsigned *src, unsigned *dst) {
    unsigned x, y, k, bg = ip_theme_colors()->bg;
    for (y = 0; y < IP_NP_REFLECT; ++y) {
        int a = (int)(IP_NP_REFLECT - y) * 77 / IP_NP_REFLECT;
        for (x = 0; x < IP_ART; ++x) {
            unsigned p = src[(IP_ART - 1 - y) * IP_ART + x], c = 0xff000000u;
            for (k = 0; k < 24; k += 8) {
                int b = (int)(bg >> k & 255), channel = (int)(p >> k & 255);
                c |= (unsigned)(b + (channel - b) * a / 255) << k;
            }
            dst[y * IP_ART + x] = c;
        }
    }
}

static void ip_cover(void *t, int first) {
    char url[80], tmp[40];
    const char *file = (const char *)0, *path;
    unsigned album = t && *cc_str(t, REC_ALBUM) ? cc_album_key(t) : 0, *px, i;
    int busy = 0;
    if (!ip.art) ip.art = bitmap_create_ex(IP_ART, IP_ART, IP_ART * 4, BITMAP_RGBA8888);
    if (!ip.art) return;
    px = (unsigned *)bitmap_lock_buffer_for_write(ip.art);
    if (!px) return;
    if (first) ip.settle = 4;
    ip.fkey = 0;
    file = album ? cc_url(url, album) : (const char *)0;
    if (file) {
        if (first) ip.settle = 0;
    } else if (t && (path = np_cover_file(&busy)) != (const char *)0 && !busy) {
        ip.fkey = np_file_key(path);
        if (ip.fkey) {
            snprintf(tmp, sizeof tmp, "file://%s", path);
            file = tmp;
        }
    }
    if (!file || !cc_decode(ip.win, file, 1, IP_ART, 1, px)) { /* the placeholder, else flat grey */
        for (i = 0; i < IP_ART * IP_ART; ++i) px[i] = ART_GREY;
        cc_decode(ip.win, "ipod_placeholder", 0, IP_ART, 1, px);
    }
    ip.np_valid = 0;
    if (!ip.np_refl) ip.np_refl = bitmap_create_ex(IP_ART, IP_NP_REFLECT, IP_ART * 4, BITMAP_RGBA8888);
    if (ip.np_refl) {
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ip.np_refl);
        if (d && bitmap_get_line_length(ip.np_refl) == IP_ART * 4) {
            ip_reflect(px, d);
            ip.np_valid = 1;
        }
        if (d) bitmap_unlock_buffer(ip.np_refl);
    }
    bitmap_unlock_buffer(ip.art);
}

/* ---------------------------------------------------------------------------
 * The main menu's cover pane, as q2-pod's Split Home (docs/modules/ipod.md "The cover pane"). All of it runs on the page's one timer (ip_tick); paint only copies.
 *   cover   the playing album's cover when the Cover Flow cache has it (cc_url: a picture, not the "no art" marker), else a random album's cached cover (drawn once a
 *           visit of the main menu: IP_PANE_TRIES cache file tests), else the placeholder, still. Decoded once, straight from the 168 px cache file to IP_PANE_ART (the
 *           pane's height zoomed 110%), on a tick of its own.
 *   pan     each axis a linear ping-pong across the zoom's margin (IP_PANE_R px, a sweep IP_DRIFT_X_MS / IP_DRIFT_Y_MS) from the centred crop. The phase counts only
 *           time shown (a step at most IP_DRIFT_MAX_MS) and carries over to a new cover. Paint copies a pane-sized window of the bitmap 1:1 at whole pixels, so nothing
 *           is resampled while it moves (the slideshow before this zoomed a 168 px window every frame and shimmered); a tick that moves no pixel repaints nothing.
 */
static void ip_rows_stop(void) {
    if (ip.row_worker) cc_build_stop();
    ip.row_worker = 0;
}

static void ip_row_reset(struct row_art *a) {
    unsigned j;
    for (j = 0; j < 4; ++j) {
        if (a->path[j]) free(a->path[j]);
        a->path[j] = (char *)0;
        a->key[j] = 0;
    }
    a->parts = a->drawn = a->waiting = 0;
}

/* Own the record's strings before another stock query can replace its deque. */
static void ip_row_source(struct row_art *a, void *rec) {
    unsigned key = cc_album_key(rec), j;
    const char *path = cc_str(rec, REC_PATH);
    if (!*path || a->parts >= 4) return;
    for (j = 0; j < a->parts; ++j)
        if (a->key[j] == key) return;
    a->key[a->parts] = key;
    a->path[a->parts] = strdup(path);
    ++a->parts;
}

static void ip_row_prepare(struct row_art *a, int kind, int index, unsigned id, void *rec) {
    ip_row_reset(a);
    a->kind = kind, a->index = index, a->id = id;
    if (kind == K_PLAYLISTS) {
        void *songs;
        unsigned i, n;
        *(int *)(CLASSINFO + CLASSINFO_ARG) = I(rec, REC_DISC);
        loadLocalClassList(CLASS_PLAYLIST_SONGS);
        songs = *(void **)PDEQ_SHOWLIST;
        n = songs ? deque_size(songs) : 0;
        for (i = 0; i < n && i < 16 && a->parts < 4; ++i) ip_row_source(a, deque_at(songs, i));
        /* PDEQ_PLAYLIST remains the foreground list. No borrowed song pointer survives. */
    } else if (I(rec, REC_ID) != ID_ALL_SONGS)
        ip_row_source(a, rec);
    if (!a->parts) a->parts = 1;
}

/* Decode one visible part per tick. Paint only copies these bounded, page-owned bitmaps. */
static int ip_row_decode(struct row_art *a, unsigned part) {
    static const unsigned char quad[5][4] = {{0, 0, 0, 0}, {0, 0, 0, 0}, {0, 1, 1, 0}, {0, 1, 2, 0}, {0, 1, 2, 3}};
    char url[80], path[80];
    const char *file = a->key[part] ? cc_url(url, a->key[part]) : (const char *)0;
    unsigned *px, temp[27 * 27], j, q, x, y, side = a->parts == 1 ? IP_ROW_ART : IP_ROW_ART / 2;
    int missing = a->key[part] && cc_file_size(cc_path(path, sizeof path, a->key[part], "")) < 0;
    if (!a->bmp) a->bmp = bitmap_create_ex(IP_ROW_ART, IP_ROW_ART, IP_ROW_ART * 4, BITMAP_RGBA8888);
    if (!a->bmp) {
        a->drawn |= 1u << part;
        return 0;
    }
    px = (unsigned *)bitmap_lock_buffer_for_write(a->bmp);
    if (!px) {
        a->drawn |= 1u << part;
        return 0;
    }
    if (!a->drawn)
        for (j = 0; j < IP_ROW_ART * IP_ROW_ART; ++j) px[j] = 0xff4a4a4au;
    if (side == IP_ROW_ART) {
        if (!cc_decode(ip.win, file ? file : "ipod_placeholder", file != (const char *)0, side, 1, px))
            for (j = 0; j < IP_ROW_ART * IP_ROW_ART; ++j) px[j] = 0xff4a4a4au;
    } else {
        for (j = 0; j < side * side; ++j) temp[j] = 0xff4a4a4au;
        cc_decode(ip.win, file ? file : "ipod_placeholder", file != (const char *)0, side, 1, temp);
        for (q = 0; q < 4; ++q)
            if (quad[a->parts][q] == part)
                for (y = 0; y < side; ++y)
                    for (x = 0; x < side; ++x)
                        px[(y + (q / 2) * side) * IP_ROW_ART + x + (q % 2) * side] = temp[y * side + x];
    }
    bitmap_unlock_buffer(a->bmp);
    a->drawn |= 1u << part;
    if (missing && a->path[part])
        a->waiting |= 1u << part;
    else
        a->waiting &= ~(1u << part);
    return 1;
}

static int ip_rows_more(void) {
    int i, kind = ip_top()->kind;
    if (!ip_tall(kind)) return 0;
    for (i = 0; i < 4 && ip_top()->top + i < (int)ip.count; ++i) {
        struct row_art *a = &ip.rows[i];
        if (a->kind != kind || a->index != ip_top()->top + i || !a->parts || a->drawn != (1u << a->parts) - 1) return 1;
    }
    return 0;
}

static void ip_rows_build(void) {
    int i, n = (int)ip.count - ip_top()->top, kind = ip_top()->kind;
    unsigned j;
    if (n > 4) n = 4;
    if (ip.row_worker || cc_build_busy() || !pod_card_mounted()) return;
    for (i = 0; i < n; ++i)
        if (ip.rows[i].kind == kind && ip.rows[i].index == ip_top()->top + i && ip.rows[i].waiting) break;
    if (i == n || !cc_build_open(16, CC_MISSING)) return;
    ip.row_worker = 1;
    for (i = 0; i < n; ++i)
        if (ip.rows[i].kind == kind && ip.rows[i].index == ip_top()->top + i)
            for (j = 0; j < ip.rows[i].parts; ++j)
                if (ip.rows[i].waiting & (1u << j)) cc_build_add(ip.rows[i].path[j], ip.rows[i].key[j]);
    if (!cc_build_start()) ip.row_worker = 0;
}

static int ip_rows_tick(void) {
    int i, kind = ip_top()->kind;
    unsigned j;
    if (!pod_is_top(ip.win)) return 0;
    if (ip.row_worker && cc_build_done() >= cc_build_total()) ip_rows_stop();
    if (!ip_tall(kind) || !ip_valid()) {
        ip_rows_stop();
        return 0;
    }
    for (i = 0; i < 4 && ip_top()->top + i < (int)ip.count; ++i) {
        struct row_art *a = &ip.rows[i];
        int index = ip_top()->top + i;
        void *rec = ip_rec(kind, ip.list, index);
        unsigned id = kind == K_PLAYLISTS ? (unsigned)I(rec, REC_DISC) : cc_album_key(rec);
        if (a->kind != kind || a->index != index || a->id != id || !a->parts) {
            ip_row_prepare(a, kind, index, id, rec);
            return 1;
        }
        for (j = 0; j < a->parts; ++j) {
            char path[80];
            int initial = !(a->drawn & (1u << j));
            if (initial || ((a->waiting & (1u << j)) && cc_file_size(cc_path(path, sizeof path, a->key[j], "")) >= 0)) {
                int changed = ip_row_decode(a, j);
                ip_rows_build();
                return changed;
            }
        }
    }
    ip_rows_build();
    return 0;
}

static void ip_rows_free(void) {
    int i;
    ip_rows_stop();
    for (i = 0; i < 4; ++i) {
        ip_row_reset(&ip.rows[i]);
        if (ip.rows[i].bmp) bitmap_destroy(ip.rows[i].bmp);
        ip.rows[i].bmp = (void *)0;
    }
}

static void ip_pane_reset(
    void) { /* a split page comes back as the main menu: new random covers, and the playing album's cover looked up again (it may be cached since) */
    ip.pane.picked = ip.pane.pk_art = 0;
    ip.pane.pk = 0;
    ip.pc_any = -1; /* episodes may have come or gone */
}

/* Up to IP_PANE_KEYS distinct random albums with a cached cover, in random order (IP_PANE_TRIES draws from one album query). Their number. */
static int ip_pane_pick(unsigned *keys, char (*trks)[96]) {
    char url[80];
    void *list = loadLocalClassList(CLASS_ALBUMS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    unsigned n = list ? deque_size(list) : 0, t, key, j;
    int got = 0;
    for (t = 0; n && t < IP_PANE_TRIES && got < IP_PANE_KEYS; ++t) {
        void *rec = deque_at(list, pod_rand(n));
        if (!rec || I(rec, REC_ID) == ID_ALL_SONGS || !*cc_str(rec, REC_ALBUM)) continue;
        key = cc_album_key(rec);
        for (j = 0; j < (unsigned)got && keys[j] != key; ++j) {
        }
        if (j == (unsigned)got && cc_url(url, key))
            snprintf(trks[got], 96, "%s", cc_str(rec, REC_PATH)), keys[got++] = key;
    }
    return got;
}

/* The album whose cover the pane should hold: the playing one's when it is cached (a cache file test only when the playing album changes), else 0: the random rotation. */
static unsigned ip_pane_want(void) {
    char url[80];
    void *t = cc_playing();
    unsigned k = t && *cc_str(t, REC_ALBUM) ? cc_album_key(t) : 0;
    if (k != ip.pane.pk) ip.pane.pk = k, ip.pane.pk_art = k && cc_url(url, k);
    if (!ip.pane.picked)
        ip.pane.rot_n = ip_pane_pick(ip.pane.rot, ip.pane.rot_trk), ip.pane.rot_i = 0, ip.pane.picked = 1;
    return ip.pane.pk_art && ip.pane.pk != ip.pane.bad ? ip.pane.pk : 0;
}

/* The pan of slot s in 1/256 px: a linear sweep of IP_PANE_R px across the cover's margin in IP_PANE_PAN_MS (the reference's 7.5 s), every other cover the other way; the
 * placeholder stands still. The frame is built at this fraction (ip_pane_frame), so the drift moves a little each frame and never in whole-pixel jumps. */
static int ip_pane_pos(int s) {
    unsigned t, pos;
    if (!ip.pane.key[s]) return IP_PANE_R * 128;
    t = ip.pane.ms[s] % (2 * IP_PANE_PAN_MS);
    pos = IP_PANE_R * 256 * (t < IP_PANE_PAN_MS ? t : 2 * IP_PANE_PAN_MS - t) / IP_PANE_PAN_MS;
    return (int)(ip.pane.rev[s] ? IP_PANE_R * 256 - pos : pos);
}

/* The pane needs IP_PANE_ART px, the cache's files are 168: a cover from them is stretched 1.57 times and reads soft. Two sharper sources, both decoded straight to IP_PANE_ART
 * with the box filter, each on a tick of its own and never during a fade:
 *   the playing album   demo's own full-resolution file for the playing track (np_cover_file: /tmp/coverpic.jpg embedded, /tmp/externpic.jpg folder, 264 px). It is used only
 *                       when demo is done with it and it is the playing track's: not busy, and either demo was seen making a cover since the track changed or IP_PANE_SHARP_MS
 *                       have passed (a stale file of the last track is never shown). Until then the 168 px file shows, and the sharp one replaces it once (a fade of the same album
 *                       at the same pan phase).
 *   the rotation        the next cover's album is extracted on demand into ONE transient RAM file (IP_PANE_TMP) by the shared builder's worker (cc_build_add_file) at
 *                       IP_PANE_NEXT_MS, decoded and deleted. Only while the job set is free; busy, failed or a source under 264 px: the 168 px file, as before. */
#define IP_PANE_TMP "/tmp/m1plus-pane.jpg"

static int ip_pane_sharp_ready(void) {
    int busy;
    const char *path = np_cover_file(&busy);
    if (busy) {
        ip.pane.busy_seen = 1;
        return 0;
    }
    if (!path || cc_file_size(path) <= 0) return 0;
    return ip.pane.busy_seen || time_now_ms() - ip.pane.trk_ms >= IP_PANE_SHARP_MS;
}

/* Stop the transient extraction (cc_build_stop: never waits) and drop its file. Safe at any time. */
static void ip_pane_xfer_stop(void) {
    if (ip.pane.worker) cc_build_stop();
    if (ip.pane.worker || ip.pane.xfer) unlink(IP_PANE_TMP), unlink(IP_PANE_TMP ".tmp");
    ip.pane.worker = ip.pane.xfer = 0;
}

/* Start the extraction of the track's album art at IP_PANE_ART px into the transient file. 1: running; 0: not allowed or not possible (the 168 px file is used). */
static int ip_pane_xfer_start(const char *track) {
    if (!*track || ip.row_worker || cc_build_busy() || !pod_card_mounted() || !pod_screen_lit()) return 0;
    unlink(IP_PANE_TMP);
    if (!cc_build_open(1, CC_MISSING)) return 0;
    if (cc_build_add_file(track, IP_PANE_TMP, IP_PANE_ART) != 1 || !cc_build_start()) {
        cc_build_stop();
        return 0;
    }
    ip.pane.worker = 1;
    return 1;
}

/* The cover of `key` (0: the placeholder) into slot s. 1 when it is a cover; a cache file that does not decode leaves the placeholder there and is not tried again (bad).
 * transient: the extracted file for key's album is there (ip_pane_xfer_*): decoded, then deleted. The source is, in order, that file, the playing track's full-resolution file
 * (for the playing album), the 168 px cache file; one that fails to decode falls to the next. */
static int ip_pane_decode(int s, unsigned key, int transient) {
    char url[80];
    const char *file = (const char *)0;
    unsigned *px, i;
    int lvl = 0, ok = 0, busy;
    if (!ip.pane.bmp[s]) ip.pane.bmp[s] = bitmap_create_ex(IP_PANE_ART, IP_PANE_ART, IP_PANE_ART * 4, BITMAP_RGBA8888);
    if (!ip.pane.bmp[s]) return 0;
    px = (unsigned *)bitmap_lock_buffer_for_write(ip.pane.bmp[s]);
    if (!px) return 0;
    if (key && transient && !access(IP_PANE_TMP, F_OK)) {
        ok = cc_decode(ip.win, "file://" IP_PANE_TMP, 1, IP_PANE_ART, 1, px), lvl = 2;
    }
    if (transient) unlink(IP_PANE_TMP);
    if (!ok && key && key == ip.pane.pk && ip.pane.pk_art && ip_pane_sharp_ready()) {
        snprintf(url, sizeof url, "file://%s", np_cover_file(&busy));
        ok = cc_decode(ip.win, url, 1, IP_PANE_ART, 1, px), lvl = 1;
    }
    if (!ok && key && (file = cc_url(url, key)) != (const char *)0)
        ok = cc_decode(ip.win, file, 1, IP_PANE_ART, 1, px), lvl = 0;
    if (!ok) { /* the placeholder, else flat grey */
        for (i = 0; i < IP_PANE_ART * IP_PANE_ART; ++i) px[i] = ART_GREY;
        cc_decode(ip.win, "ipod_placeholder", 0, IP_PANE_ART, 1, px);
        if (key) ip.pane.bad = key;
        key = 0;
    }
    bitmap_unlock_buffer(ip.pane.bmp[s]);
    ip.pane.key[s] = key, ip.pane.have[s] = 1, ip.pane.lvl[s] = (unsigned char)lvl;
    return key != 0;
}

/* u + (v - u) * f / 256 per colour channel (f 0 .. 255), the R / B lane pair and the G lane at once. */
static unsigned ip_lerp8(unsigned u, unsigned v, unsigned f) {
    return ((((u & 0xff00ffu) * (256 - f) + (v & 0xff00ffu) * f) >> 8) & 0xff00ffu) |
           ((((u & 0xff00u) * (256 - f) + (v & 0xff00u) * f) >> 8) & 0xff00u);
}

/* One pane frame, built on the timer into the page's own IP_PANE_W x IP_PANE_H bitmap (paint only copies it): each row of the cover's window at the pan's place in 1/256 px,
 * every pixel the linear mix of its source column and the next by the fraction (so the picture moves smoothly instead of a pixel at a time); during a cross-fade both covers
 * are built at their own fractions and mixed by the eased fade in the same pass. One pass over 160 x 240 pixels (two interpolations and a mix while fading). */
static void ip_pane_frame(void) {
    const unsigned *a, *b = (const unsigned *)0;
    unsigned *d, p = 0, al = 0, x, y, fa, fb;
    int c = ip.pane.cur, o = !c, pa = ip_pane_pos(c), pb = ip_pane_pos(o), xa, xb;
    ip.pane.mix_ok = 0;
    if (!ip.pane.mix) ip.pane.mix = bitmap_create_ex(IP_PANE_W, IP_PANE_H, IP_PANE_W * 4, BITMAP_RGBA8888);
    if (!ip.pane.mix) {
        ip.pane.mix_bad = 1; /* no frame bitmap: paint falls back to the whole-pixel window of the cover */
        return;
    }
    if (!ip.pane.bmp[c] || (ip.pane.fading && !ip.pane.bmp[o])) return;
    xa = (IP_PANE_ART - IP_PANE_W - IP_PANE_R) / 2 + (pa >> 8), fa = (unsigned)pa & 255;
    xb = (IP_PANE_ART - IP_PANE_W - IP_PANE_R) / 2 + (pb >> 8), fb = (unsigned)pb & 255;
    if (ip.pane.fading) {
        p = ip.pane.fade_ms * 1024 / IP_PANE_FADE_MS;
        if (p > 1023) p = 1023;
        al = ((p * p / 1024) * (3072 - 2 * p) / 1024) * 256 / 1024; /* 0 .. 255 */
    }
    a = (const unsigned *)bitmap_lock_buffer_for_read(ip.pane.bmp[c]);
    if (ip.pane.fading) b = (const unsigned *)bitmap_lock_buffer_for_read(ip.pane.bmp[o]);
    d = (unsigned *)bitmap_lock_buffer_for_write(ip.pane.mix);
    if (a && d && (b || !ip.pane.fading)) {
        for (y = 0; y < IP_PANE_H; ++y) {
            const unsigned *ra = a + (y + IP_PANE_R / 2) * IP_PANE_ART + xa,
                           *rb = b ? b + (y + IP_PANE_R / 2) * IP_PANE_ART + xb : ra;
            unsigned *row = d + y * IP_PANE_W;
            for (x = 0; x < IP_PANE_W; ++x) {
                unsigned u = ip_lerp8(ra[x], ra[x + 1], fa);
                if (b) u = ip_lerp8(u, ip_lerp8(rb[x], rb[x + 1], fb), al);
                row[x] = 0xff000000u | u;
            }
        }
        ip.pane.mix_ok = 1;
    }
    if (a) bitmap_unlock_buffer(ip.pane.bmp[c]);
    if (b) bitmap_unlock_buffer(ip.pane.bmp[o]);
    if (d) bitmap_unlock_buffer(ip.pane.mix);
}

/* One tick (the page is in front and a split page is the level). The reference's artwork pane: a cover pans for IP_PANE_PAN_MS; every IP_PANE_HOLD_MS the next one fades in over
 * IP_PANE_FADE_MS while both pan. The next cover is decoded in the other slot IP_PANE_NEXT_MS in, a tick of its own, never during the fade. The playing album's cached cover
 * replaces the rotation (it fades in at once and stays, panning back and forth). Whether the pane changed. */

static int ip_pane_advance(void) {
    unsigned want, now, step;
    int c = ip.pane.cur, o = !c;
    if (!ip_split(ip_top()->kind) || !pod_is_top(ip.win)) return 0;
    now = time_now_ms(), step = now - ip.pane.t0;
    ip.pane.t0 = now;
    if (step > IP_DRIFT_MAX_MS) step = IP_DRIFT_MAX_MS;
    want = ip_pane_want();
    { /* a new track: demo makes its cover file again; the pane trusts the file only after seeing that (or IP_PANE_SHARP_MS later), never a stale one of the last track */
        void *pt = cc_playing();
        unsigned tk = pt ? ip_track_key(pt) : 0;
        if (tk != ip.pane.trk) {
            if (ip.pane.trk != ~0u)
                ip.pane.trk_ms =
                    now; /* (the first sight of a track after the page opened: its file is taken as current) */
            ip.pane.trk = tk, ip.pane.busy_seen = 0;
        }
        if (*(volatile int *)COVER_SRC == COVER_SRC_BUSY) ip.pane.busy_seen = 1;
    }
    if (want && ip.pane.xfer) ip_pane_xfer_stop(); /* something plays now: the rotation's extraction is not needed */
    if (ip.pane.xfer == 1 && ip.pane.worker &&
        cc_build_done() >= cc_build_total()) { /* the worker finished: join it, the file (if any) is decoded below */
        cc_build_stop();
        ip.pane.worker = 0, ip.pane.xfer = 2;
    }
    if (!ip.pane.have[c]) { /* the first cover: no fade */
        ip_pane_decode(c, want ? want : ip.pane.rot_n ? ip.pane.rot[0] : 0, 0);
        ip.pane.ms[c] = ip.pane.cycle = 0, ip.pane.rev[c] = 0, ip.pane.rot_i = 1;
        return 1;
    }
    ip.pane.ms[c] = (ip.pane.ms[c] + step) % (2 * IP_PANE_PAN_MS);
    ip.pane.cycle += step;
    if (ip.pane.fading) {
        ip.pane.ms[o] = (ip.pane.ms[o] + step) % (2 * IP_PANE_PAN_MS);
        ip.pane.fade_ms += step;
        if (ip.pane.fade_ms >= IP_PANE_FADE_MS) ip.pane.fading = 0, ip.pane.cur = o;
        return 1;
    }
    if (want && want == ip.pane.key[c] && !ip.pane.upgrade) ip.pane.next_ready = 0;
    if (want && want != ip.pane.key[c] && !(ip.pane.next_ready && ip.pane.key[o] == want)) {
        ip.pane.next_ready = ip_pane_decode(o, want, 0);
        return 1;
    }
    if (want && want == ip.pane.key[c] && ip.pane.lvl[c] < 1 &&
        !ip.pane
             .next_ready) { /* the playing album is on screen from the 168 px file: look for demo's sharp one twice a second */
        if (ip.pane.up_wait > step)
            ip.pane.up_wait -= step;
        else {
            ip.pane.up_wait = 500;
            if (ip_pane_sharp_ready()) {
                ip.pane.next_ready = ip_pane_decode(o, want, 0), ip.pane.upgrade = ip.pane.next_ready;
                return 1;
            }
        }
    }
    if (ip.pane.xfer == 2) { /* the extraction is done: decode it into the other slot, on this tick */
        ip.pane.xfer = 0;
        ip.pane.next_ready = ip_pane_decode(o, ip.pane.xfer_key, 1);
        return 1;
    }
    if (!want && !ip.pane.next_ready && !ip.pane.xfer && ip.pane.cycle >= IP_PANE_NEXT_MS && ip.pane.rot_n > 0) {
        unsigned k = 0;
        int t, ti = 0;
        for (t = 0; t < ip.pane.rot_n && !k; ++t) {
            unsigned cand = ip.pane.rot[(ip.pane.rot_i + t) % ip.pane.rot_n];
            if (cand != ip.pane.key[c] && cand != ip.pane.bad)
                k = cand, ti = (ip.pane.rot_i + t) % ip.pane.rot_n,
                ip.pane.rot_i = (ip.pane.rot_i + t + 1) % ip.pane.rot_n;
        }
        if (k) {
            if (ip_pane_xfer_start(
                    ip.pane.rot_trk
                        [ti])) { /* the sharp picture comes from the shared worker; the tick that sees it done decodes it */
                ip.pane.xfer = 1, ip.pane.xfer_key = k;
                return 0;
            }
            ip.pane.next_ready = ip_pane_decode(o, k, 0);
            return 1;
        }
    }
    if (ip.pane.next_ready && (want || ip.pane.upgrade || ip.pane.cycle >= IP_PANE_HOLD_MS)) {
        ip.pane.fading = 1, ip.pane.fade_ms = 0, ip.pane.next_ready = 0;
        if (ip.pane.upgrade)
            ip.pane.ms[o] = ip.pane.ms[c], ip.pane.rev[o] = ip.pane.rev[c],
            ip.pane.upgrade = 0; /* the same album sharpened: the same place */
        else
            ip.pane.ms[o] = 0, ip.pane.rev[o] = !ip.pane.rev[c], ip.pane.cycle = 0;
        return 1;
    }
    return 0;
}

/* The tick's pane work: the state machine above, then the frame when something moved. 1: the pane's rectangle needs painting. */
static int ip_pane_step(void) {
    int changed, pos;
    if (!ip_split(ip_top()->kind) || !pod_is_top(ip.win) || ip_pc_pane())
        return 0; /* (the Podcasts picture is still: the covers wait, and pan on from where they were) */
    changed = ip_pane_advance();
    if (!ip.pane.have[ip.pane.cur]) return changed;
    pos = ip_pane_pos(ip.pane.cur);
    if (!ip.pane.mix_bad &&
        (changed || !ip.pane.mix_ok || ip.pane.fading || pos != ip.pane.px)) { /* the frame at the new place */
        ip_pane_frame();
        ip.pane.px = pos;
        return 1;
    }
    if (ip.pane.mix_bad &&
        (changed || pos >> 8 != ip.pane.px >> 8)) { /* no frame bitmap: the whole-pixel window moves */
        ip.pane.px = pos;
        return 1;
    }
    return 0;
}

/* The interval the page's one timer should have: IPCF_FRAME_MS while the Cover Flow level in front slides or decodes (ipod_cf.c); IP_DRIFT_MS while the cover pans
 * (the main menu is the level, the page is in front, and the pane has a cover or is still being made); IP_TICK_MS otherwise (the disc: the slow look still finds a new cover). */
static unsigned ip_want_ms(void) {
    if (ip.fg && !pod_screen_lit())
        return POD_DARK_MS; /* the screen is off: no visual work (the idle-power rule of the other pages) */
    if (ip.fg && pod_is_top(ip.win) && ip_render_active()) return IPCF_FRAME_MS;
    if (ip.fg && ip.touch == R_RING && ip.menu_zone && !ip.long_done && ip.depth > 0)
        return IP_DRIFT_MS; /* watching for the long press of MENU */
    if (ip.fg && pod_is_top(ip.win) && ip_rows_more()) return IPCF_FRAME_MS;
    if (ip.fg && pod_is_top(ip.win) && ip.row_worker) return IP_DRIFT_MS;
    if (ip.fg && ip_top()->kind == K_CF && ipcf_busy()) return IPCF_FRAME_MS;
    if (ip_pc_pane()) return IP_TICK_MS; /* the Podcasts picture: nothing moves */
    if (ip_split(ip_top()->kind) && ip.fg && ip.pane.fading && pod_is_top(ip.win)) return IP_FADE_TICK_MS;
    return ip_split(ip_top()->kind) && ip.fg &&
                   (!ip.pane.have[ip.pane.cur] || ip.pane.key[ip.pane.cur] || ip.pane.rot_n) && pod_is_top(ip.win)
               ? IP_PAN_MS
               : IP_TICK_MS;
}

static void ip_retime(void) {
    unsigned want = ip_want_ms();
    if (ip.timer && want != ip.ival) {
        timer_modify(ip.timer, want);
        ip.ival = want;
    }
}

/* The battery as the real status bar shows it: pgbar_battery's value (0 .. 100) and whether img_battery is the charging picture. -1: no bar. */
static int ip_battery(int *charging) {
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

/* One look at everything the timer watches. Returns whether the screen needs a repaint, and keeps the cover. */
static int ip_look(void) {
    unsigned sig[5];
    int charging, i, pos = 0, len = 0, changed = 0;
    void *t = cc_playing(), *q = *(void **)PLAY_QUEUE;
    sig[0] = (unsigned)(ip_battery(&charging) + 1) | (unsigned)charging << 8;
    sig[1] = (unsigned)mclGetPlayStatus();
    sig[2] = t ? ip_track_key(t) : 0;
    ip.np_gone = t ? 0 : ip.np_gone + 1;
    if (!t && ip.np_gone == IP_NP_GONE && ip.np_have)
        ip.np_have = 0, changed = 1; /* the player really has no track: Now Playing says so */
    sig[3] = 0;
    if (ip_now_shown() !=
        ip.now_shown) { /* the Now Playing row came or went: the root's cursor stays on the same item */
        struct lvl *root = &ip.st[0];
        ip.now_shown = ip_now_shown();
        if (ip.now_shown && root->sel >= ROOT_NOW)
            root->sel++;
        else if (!ip.now_shown && root->sel > ROOT_NOW)
            root->sel--;
        if (root->sel > ROOT_COUNT - !ip.now_shown - 1) root->sel = ROOT_COUNT - !ip.now_shown - 1;
        changed = 1;
    }
    if (ip_top()->kind == K_NOW && t && get_playtimeandlength(&pos, &len) == 1)
        sig[3] = (unsigned)(pos + 1) * 4099u ^ (unsigned)len;
    sig[4] = (q ? deque_size(q) : 0) ^ ((unsigned)pod_play_mode() << 24);
    if (sig[2] != ip.track &&
        (t || !ip.np_have)) { /* (no track for a moment, the last one still shown: its cover stays, not the disc) */
        ip.track = sig[2];
        ip_cover(t, 1);
        changed = 1;
    } else if (ip.settle > 0 && t) { /* demo writes the /tmp cover a little after the track changes */
        int busy = 0;
        const char *path = np_cover_file(&busy);
        unsigned k;
        if (!busy) {
            ip.settle--;
            k = path ? np_file_key(path) : 0;
            if (k && k != ip.fkey) ip_cover(t, 0), changed = 1;
        }
    }
    for (i = 0; i < 5; ++i)
        if (sig[i] != ip.sig[i]) ip.sig[i] = sig[i], changed = 1;
    return changed;
}

/* ---------------------------------------------------------------------------
 * Painting
 */
static void ip_chevron(void *canvas, int x, int ymid, unsigned rgb) {
    int dy;
    for (dy = -4; dy <= 4; ++dy) ip_fill(canvas, x + 4 - (dy < 0 ? -dy : dy), ymid + dy, 2, 1, rgb);
}

/* The battery of the reference's status bar: a 24 x 12 frame and a 3 x 5 nub (27 px in all), the empty well a three-stop grey gradient, the charge a green (red below 20 %)
 * fill in two bands of five rows, the lit top half and the darker bottom half, inside the 1 px outline. */
#define BGR(c) ((((c) & 0xffu) << 16) | ((c) & 0xff00u) | (((c) >> 16) & 0xffu))
static void ip_battery_glyph(void *canvas, int x, int y) {
    static const unsigned green[10] = {BGR(0xa4d08au), BGR(0xdcf8c7u), BGR(0xc9ecb0u), BGR(0xa5e07fu), BGR(0xa1de7du),
                                       BGR(0x6bab46u), BGR(0x4e932cu), BGR(0x539831u), BGR(0x5fa53eu), BGR(0x539831u)};
    static const unsigned red[10] = {BGR(0xd17f6bu), BGR(0xf0b2a8u), BGR(0xe89d90u), BGR(0xe87259u), BGR(0xe67357u),
                                     BGR(0xb74124u), BGR(0xa3300bu), BGR(0xa7340fu), BGR(0xb3421cu), BGR(0xa73410u)};
    static const unsigned char at[] = {0, 50, 100};
    const struct ip_theme_palette *p = ip_theme_colors();
    int charging, pct = ip_battery(&charging), w, i;
    for (i = 1; i < 11; ++i) ip_fill(canvas, x + 1, y + i, 22, 1, ip_stops(p->battery_empty, at, 3, i - 1, 10));
    if (pct >= 0) {
        w = 22 * (pct > 100 ? 100 : pct) / 100;
        for (i = 0; i < 10 && w > 0; ++i)
            ip_fill(canvas, x + 1, y + 1 + i, w, 1, (pct <= 20 && !charging ? red : green)[i]);
    }
    ip_fill(canvas, x, y, 24, 1, p->battery_edge), ip_fill(canvas, x, y + 11, 24, 1, p->battery_edge),
        ip_fill(canvas, x, y, 1, 12, p->battery_edge), ip_fill(canvas, x + 23, y, 1, 12, p->battery_edge);
    ip_fill(canvas, x + 24, y + 3, 3, 5, p->battery_edge);
}

/* The play state, 10 px tall from y (the rows the battery glyph uses, so the bar's glyphs share one centre line), in the selection's blue, a row at a time down its
 * gradient, as the iPod's: a 12 x 14 glyph, a triangle 10 px wide, or two 4 px bars. */
static void ip_play_glyph(void *canvas, int x, int y) {
    int st = mclGetPlayStatus() == 2 ? 1 : mclGetPlayStatus() == 3 ? 2 : 0, r;
    for (r = 0; st && r < 14; ++r) {
        unsigned c = ip_lerp(IP_SEL_TOP, IP_SEL_BOT, r, 14);
        if (st == 1)
            ip_fill(canvas, x + 1, y + r, ((r < 13 - r ? r : 13 - r) + 1) * 10 / 7, 1, c);
        else
            ip_fill(canvas, x + 1, y + r, 4, 1, c), ip_fill(canvas, x + 7, y + r, 4, 1, c);
    }
}

static const char *ip_title(int kind) {
    switch (kind) {
    case K_MUSIC:
        return TR("Music");
    case K_ALBUMS:
        return TR("Albums");
    case K_ARTISTS:
        return TR("Artists");
    case K_SONGS:
        return TR("Songs");
    case K_PLAYLISTS:
        return TR("Playlists");
    case K_PODCASTS:
        return TR("Podcasts");
    case K_NOW:
        return TR("Now Playing");
    case K_CF:
        return TR("Cover Flow");
    case K_SETTINGS:
        return TR("cdrippersettings");
    default:
        return "Pod"; /* the page's own name, a brand like the Extras item's label: plain in every language (pod_i18n.BRANDS) */
    }
}

/* The iPod's title bar: the title on the left, no clock; the play state right of it, next to the battery. */
static void ip_paint_bar(void *canvas, int kind) {
    int right = ip_split(kind) ? IP_SPLIT_X : IP_W;
    ip_header(canvas, right);
    /* One centre line, y 11.5 (rows 7 .. 16): the glyphs are 10 px from y 7; the text box starts at y 1, because AWTK's metric centring in the 23 px
     * box put the caps 1 px high on the device (shot-0014: caps 6 .. 15). */
    ip_play_glyph(canvas, right - 8 - 27 - 8 - 12, IP_BAR_H / 2 - 7); /* 8 px before the battery, 8 px from the edge */
    ip_battery_glyph(canvas, right - 8 - 27, IP_BAR_H / 2 - 6);
    widget_prepare_text_style(ip.st_title, canvas); /* left, 16 px */
    ip_text(canvas, ip_top()->title[0] ? ip_top()->title : ip_title(kind), IP_TEXT_X, 1,
            right - 8 - 27 - 8 - 12 - 6 - IP_TEXT_X, IP_BAR_H - 1);
}

/* The shadow the white menu casts on the pane (the real iPod's, and iPlayr's .shadow(black 0.7, radius 8, x 4) on the menu's background): IP_SHADOW_W columns of black from the pane's
 * left edge, 52 % opaque at x 160 and falling off like a gaussian (sigma 3.6) to nearly nothing by the tenth column. A straight-alpha RGBA bitmap made once at open (demo's canvas
 * blends such images over the screen: test/awtk_fill.py), drawn after the pane over the cover and over the plain fill alike; paint allocates nothing. */
static const unsigned char ip_shadow_alpha[IP_SHADOW_W] = {132, 122, 105, 83, 61, 41, 26, 15, 8, 4};

static void ip_shadow_make(void) {
    unsigned *px, x, y;
    ip.shadow = bitmap_create_ex(IP_SHADOW_W, IP_PANE_H, IP_SHADOW_W * 4, BITMAP_RGBA8888);
    px = ip.shadow ? (unsigned *)bitmap_lock_buffer_for_write(ip.shadow) : (unsigned *)0;
    if (!px) {
        if (ip.shadow) bitmap_destroy(ip.shadow);
        ip.shadow = (void *)0;
        return;
    }
    for (y = 0; y < IP_PANE_H; ++y)
        for (x = 0; x < IP_SHADOW_W; ++x) px[y * IP_SHADOW_W + x] = (unsigned)ip_shadow_alpha[x] << 24;
    bitmap_unlock_buffer(ip.shadow);
    ip_render_edge(ip.shadow); /* in a split slide it moves with the menu half, not the pane */
}

/* The cover pane of the main menu (the iPod 6G split screen), flush against the white menu (no rule): a pane-sized window of the cover's bitmap at the pan's place, copied 1:1 (source and destination the same
 * size: canvas_draw_image blits, it does not scale). Paint only draws what the timer decoded. */
static void ip_paint_pane(void *canvas) {
    int src[4], dst[4];
    ip_fill(canvas, IP_SPLIT_X, 0, IP_W - IP_SPLIT_X, IP_SCREEN_H, ip_theme_colors()->pane);
    dst[0] = IP_PANE_X, dst[1] = 0, dst[2] = IP_PANE_W, dst[3] = IP_PANE_H;
    if (ip_pc_pane()) { /* the Podcasts row: its picture, still, and No Podcasts centred under the glyph when there is no episode */
        src[0] = src[1] = 0, src[2] = IP_PANE_W, src[3] = IP_PANE_H;
        if (ip.pc_img_ok) canvas_draw_image(canvas, ip.pc_img, src, dst);
        if (!ip.pc_any) {
            unsigned wide[64], n = ip_len(TR("No Podcasts"));
            int w, rect[4];
            widget_prepare_text_style(ip.st_sel, canvas);
            tk_utf8_to_utf16_ex(TR("No Podcasts"), n, wide, 64);
            n = ip_fit(canvas, wide, IP_PANE_W - 2 * IP_TEXT_X);
            w = n ? (int)(canvas_measure_text(canvas, wide, n) + 0.999f) : 0;
            rect[0] = IP_PANE_X + (IP_PANE_W - w) / 2, rect[1] = IP_PC_TEXT_Y, rect[2] = w + 2, rect[3] = IP_ROW_H;
            if (n) canvas_draw_text_in_rect(canvas, wide, n, rect);
        }
    } else if (
        ip.pane.mix_ok &&
        ip.pane.mix) { /* the frame built on the timer at the sub-pixel place (the cross-fade included): a 1:1 copy */
        src[0] = src[1] = 0, src[2] = IP_PANE_W, src[3] = IP_PANE_H;
        canvas_draw_image(canvas, ip.pane.mix, src, dst);
    } else if (ip.pane.have[ip.pane.cur] && ip.pane.bmp[ip.pane.cur]) {
        src[0] = (IP_PANE_ART - IP_PANE_W - IP_PANE_R) / 2 + (ip_pane_pos(ip.pane.cur) >> 8), src[1] = IP_PANE_R / 2,
        src[2] = IP_PANE_W, src[3] = IP_PANE_H;
        canvas_draw_image(canvas, ip.pane.bmp[ip.pane.cur], src, dst);
    }
    if (ip.shadow && !ip.no_shadow) { /* the menu's shadow on the pane's left edge */
        src[0] = src[1] = 0, src[2] = IP_SHADOW_W, src[3] = IP_PANE_H;
        dst[0] = IP_PANE_X, dst[2] = IP_SHADOW_W;
        canvas_draw_image(canvas, ip.shadow, src, dst);
    }
}

/* A text in the canvas' current style, right aligned so that it ends at x2 (a Settings row's value; at most 120 px). Its width. */
static int ip_text_right(void *canvas, const char *utf8, int x2, int y, int h) {
    unsigned wide[64], n = ip_len(utf8);
    int rect[4], w;
    if (!n) return 0;
    tk_utf8_to_utf16_ex(utf8, n, wide, 64);
    n = ip_fit(canvas, wide, 72);
    w = n ? (int)(canvas_measure_text(canvas, wide, n) + 0.999f) : 0;
    rect[0] = x2 - w, rect[1] = y, rect[2] = w + 2, rect[3] = h;
    if (n) canvas_draw_text_in_rect(canvas, wide, n, rect);
    return w;
}

/* A text of at most 50 px that starts at x (left) or ends at x, whatever the style's alignment (Now Playing's times). */
static void ip_text_edge(void *canvas, const char *utf8, int x, int left, int y, int h) {
    unsigned wide[16], n = ip_len(utf8);
    int rect[4], w;
    if (!n || n > 15) return;
    tk_utf8_to_utf16_ex(utf8, n, wide, 16);
    n = ip_fit(canvas, wide, 50);
    w = n ? (int)(canvas_measure_text(canvas, wide, n) + 0.999f) : 0;
    rect[0] = left ? x : x - w, rect[1] = y, rect[2] = w + 2, rect[3] = h;
    if (n) canvas_draw_text_in_rect(canvas, wide, n, rect);
}

/* The value a Settings row shows: the play mode as the stock Play settings page names it (Shuffle is mode 2; Repeat is mode 1 or 3), the version tag on About. NULL: none. */
static const char *ip_set_value(int row) {
    int mode = pod_play_mode();
    if (row == S_SHUFFLE) return TR(mode == MODE_SHUFFLE ? "Songs" : "Off");
    if (row == S_REPEAT) return mode == MODE_REPEAT_ONE ? TR("One") : mode == MODE_REPEAT_ALL ? TR("All") : TR("Off");
    if (row == S_APPEARANCE) return TR(ip_theme_dark() ? "Dark" : "Light");
    return (const char *)0;
}

static void ip_paint_list(void *canvas, int kind) {
    struct lvl *l = ip_top();
    void *playing = ip_is_tracks(kind) ? cc_playing() : (void *)0;
    int i, fixed = ip_split(kind), n = ip.list || fixed ? ip_rows() : 0, right = fixed ? IP_SPLIT_X : IP_W, pass, y;
    int tall = ip_tall(kind), h = tall ? IP_TALL_H : IP_ROW_H, visible = tall ? IP_TALL_ROWS : IP_ROWS;
    if (!fixed && !ip_valid()) n = 0; /* a stale list is never read */
    for (pass = 0; pass < 2; ++pass) { /* the unselected rows, then the selected one: one text style at a time */
        widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
        for (i = 0; i < visible && l->top + i < n; ++i) {
            int idx = l->top + i, sel = idx == l->sel, vw = 0, chev = !ip_is_tracks(kind) && kind != K_PC_EPS;
            const char *val = kind == K_SETTINGS ? ip_set_value(idx) : (const char *)0;
            if (sel != pass) continue;
            y = IP_BAR_H + i * h;
            if (sel) ip_selection(canvas, right, y, h);
            if (val) { /* blue on white, white on the selection (the reference's value colours) */
                widget_prepare_text_style(sel ? ip.st_subsel : ip.st_val, canvas);
                vw = ip_text_right(canvas, val, right - IP_TEXT_X, y, h), chev = 0;
                widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
            }
            if (kind ==
                K_PC_EPS) { /* the iPod's blue dot of an episode not played at all (no place saved either); text indented for it on every row */
                static const unsigned char dot[8] = {4, 6, 8, 8, 8, 8, 6, 4};
                int k;
                unsigned pos, len;
                if (pc_state(ip.pc_eps[idx].hash, &pos, &len) == PC_NEW)
                    for (k = 0; k < 8; ++k)
                        ip_fill(canvas, 6 + (8 - dot[k]) / 2, y + (h - 8) / 2 + k, dot[k], 1,
                                sel ? 0xffffffu : 0xe17d2au);
            }
            ip_text(canvas, ip_row_text(kind, idx),
                    tall               ? IP_ROW_ART + 8
                    : kind == K_PC_EPS ? IP_TEXT_X + 16
                                       : IP_TEXT_X,
                    y + (tall ? 4 : 0),
                    vw ? right - IP_TEXT_X - IP_TEXT_X - vw - 12
                       : right - IP_TEXT_X - 22 -
                             (tall               ? IP_ROW_ART + 8
                              : kind == K_PC_EPS ? 16
                                                 : 0),
                    IP_ROW_H);
            if (tall) {
                struct row_art *a = &ip.rows[i];
                int src[4] = {0, 0, IP_ROW_ART, IP_ROW_ART}, dst[4] = {0, y, IP_ROW_ART, IP_ROW_ART};
                void *rec = ip_rec(kind, ip.list, idx);
                char sub[256];
                unsigned identity = kind == K_PLAYLISTS ? (unsigned)I(rec, REC_DISC) : cc_album_key(rec);
                if (a->bmp && a->kind == kind && a->index == idx && a->id == identity && a->drawn)
                    canvas_draw_image(canvas, a->bmp, src, dst);
                else
                    ip_fill(canvas, 0, y, IP_ROW_ART, IP_ROW_ART, ip_theme_colors()->rule);
                if (kind == K_PLAYLISTS)
                    snprintf(sub, sizeof sub, "%s", TR("Playlists"));
                else
                    snprintf(sub, sizeof sub, "%s", cc_str(rec, REC_ARTIST));
                widget_prepare_text_style(sel ? ip.st_subsel : ip.st_small, canvas);
                ip_text(canvas, sub, IP_ROW_ART + 8, y + 30, right - IP_TEXT_X - 22 - IP_ROW_ART - 8, 20);
                widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
            }
            if (sel && chev)
                ip_chevron(canvas, right - 14, y + h / 2, 0xffffffu); /* as the iPod: only the selected row has one */
            if (!sel && playing && ip_is_tracks(kind)) {
                void *rec = deque_at(ip.list, (unsigned)idx);
                const char *path = cc_str(rec, REC_PATH);
                if (*path && !strcmp(path, cc_str(playing, REC_PATH)) &&
                    I(rec, REC_CUE_START) ==
                        I(playing, REC_CUE_START)) { /* the speaker: the playing track, right aligned */
                    void *bmp = ip_mode_bitmap(3);
                    int src[4] = {0, 0, IP_PLAY_PX, IP_PLAY_PX},
                        dst[4] = {IP_W - IP_TEXT_X - IP_PLAY_PX, y + (h - IP_PLAY_PX) / 2, IP_PLAY_PX, IP_PLAY_PX};
                    if (bmp) canvas_draw_image(canvas, bmp, src, dst);
                }
            }
        }
    }
    if (!fixed && n == 0 && ip_valid()) {
        widget_prepare_text_style(ip.st_small, canvas);
        ip_text(canvas,
                TR(kind == K_ALBUMS || kind == K_ARTIST_ALBUMS ? "No albums"
                   : kind == K_ARTISTS                         ? "No artists"
                   : kind == K_PLAYLISTS                       ? "No playlists"
                   : ip_is_pc(kind)                            ? "No downloaded episodes"
                                                               : "No songs"),
                IP_TEXT_X, IP_BAR_H, IP_W - 2 * IP_TEXT_X, IP_ROW_H);
    }
}

/* The play mode's mark (stock's one play mode makes shuffle and repeat exclusive): the asset images ipod_mode_shuffle / ipod_mode_repeat / ipod_mode_repeat1 (a heavy white Lucide
 * glyph at 32 px, tools/mod_icons.py). Decoded once on first use, with the box filter down to IP_MODE_PX, into a page-owned bitmap: the glyph is white and the decode is over black, so
 * a pixel's value is its coverage, and the bitmap is that coverage mixed from the screen's colour to the mark's (opaque: the screen is white in both appearances). Paint copies it. */
static void *ip_mode_bitmap(int i) {
    unsigned tmp[IP_MODE_PX * IP_MODE_PX], *px, k, size = i == 3 ? IP_PLAY_PX : IP_MODE_PX;
    if (ip.mode_bmp[i] || (ip.mode_tried >> i & 1)) return ip.mode_bmp[i];
    ip.mode_tried |= 1 << i;
    if (!cc_decode(ip.win, MODE_ICONS[i], 0, size, 1, tmp)) return (void *)0;
    ip.mode_bmp[i] = bitmap_create_ex(size, size, size * 4, BITMAP_RGBA8888);
    px = ip.mode_bmp[i] ? (unsigned *)bitmap_lock_buffer_for_write(ip.mode_bmp[i]) : (unsigned *)0;
    if (!px) return (void *)0;
    for (
        k = 0; k < size * size;
        ++k) /* the marks in the mark colour; the speaker in the title bar glyph's blue, a row at a time down its gradient */
        px[k] = 0xff000000u |
                ip_lerp(ip_theme_colors()->bg,
                        i == 3 ? ip_lerp(IP_SEL_TOP, IP_SEL_BOT, (int)(k / size), (int)size) : ip_theme_colors()->mode,
                        (int)(tmp[k] & 255), 256);
    bitmap_unlock_buffer(ip.mode_bmp[i]);
    return ip.mode_bmp[i];
}

static void ip_mode_draw(void *canvas, int mode) {
    int i = mode == MODE_SHUFFLE      ? 0
            : mode == MODE_REPEAT_ALL ? 1
            : mode == MODE_REPEAT_ONE ? 2
                                      : -1,
        src[4] = {0, 0, IP_MODE_PX, IP_MODE_PX}, dst[4] = {IP_MODE_X, IP_MODE_Y, IP_MODE_PX, IP_MODE_PX};
    void *bmp = i >= 0 ? ip_mode_bitmap(i) : (void *)0;
    if (bmp) canvas_draw_image(canvas, bmp, src, dst);
}

/* One row (i of IP_NP_BAR_H) of the progress bar at screen row y: the 18 px track is white with its top and bottom edges shaded in, the fill the reference's six-stop
 * glossy blue over the whole height; `alpha` (255 opaque) mixes it into the screen colour, for the reflection under the bar. */
static void ip_bar_row(void *canvas, int y, int i, int fw, int alpha) {
    static const unsigned blue[] = {BGR(0x86abffu), BGR(0x6b99f5u), BGR(0x3d89ebu),
                                    BGR(0x3698f9u), BGR(0x37b0ffu), BGR(0x5cbbffu)};
    static const unsigned char at[] = {0, 20, 58, 58, 82, 100};
    unsigned bg = ip_theme_colors()->bg, edge = ip_theme_colors()->progress_edge;
    int grey = 255 - (i < 4    ? (4 - i) * 10
                      : i > 10 ? (i - 10) * 6
                               : 0); /* the shading of the track's top and bottom edges */
    unsigned track = (unsigned)grey * 0x010101u, fill = ip_stops(blue, at, 6, i, IP_NP_BAR_H);
    if (i == 0 || i == IP_NP_BAR_H - 1) track = edge;
    if (alpha < 255) track = ip_lerp(bg, track, alpha, 256), fill = ip_lerp(bg, fill, alpha, 256);
    if (fw > 0) ip_fill(canvas, IP_NP_TRACK_X, y, fw, 1, fill);
    ip_fill(canvas, IP_NP_TRACK_X + fw, y, IP_NP_TRACK_W - fw, 1, track);
    if (i > 0 && i < IP_NP_BAR_H - 1) {
        unsigned side = alpha < 255 ? ip_lerp(bg, edge, alpha, 256) : edge;
        if (fw == 0) ip_fill(canvas, IP_NP_TRACK_X, y, 1, 1, side);
        ip_fill(canvas, IP_NP_TRACK_X + IP_NP_TRACK_W - 1, y, 1, 1, side);
    }
}

/* Now Playing never blanks while the player changes track: for a moment the player has no current track (cc_playing NULL) or no time (get_playtimeandlength fails or says 0), and
 * a repaint landing then used to drop the text or the whole bar until a later tick. The text of the last track is kept (np_text) for IP_NP_GONE looks without one, the bar is
 * always drawn from the last valid (position, length): on a new track the fill starts empty at 00:00, the length being the last one known (the song record has no duration). */
static void ip_paint_now(void *canvas) {
    void *t = cc_playing(), *queue = *(void **)PLAY_QUEUE;
    int pos = 0, len = 0, src[4], dst[4], fw, i, n, ok;
    char line[48], a[12], b[12];
    const char *f;
    if (t) {
        f = cc_str(t, REC_TITLE);
        snprintf(ip.np_text[0], sizeof ip.np_text[0], "%s", *f ? f : cc_str(t, REC_NAME));
        snprintf(ip.np_text[1], sizeof ip.np_text[1], "%s", cc_str(t, REC_ARTIST));
        snprintf(ip.np_text[2], sizeof ip.np_text[2], "%s", cc_str(t, REC_ALBUM));
        ip.np_have = 1;
    } else if (!ip.np_have) {
        widget_prepare_text_style(ip.st_np2, canvas);
        ip_text(canvas, TR("Not Playing"), IP_TEXT_X, IP_BAR_H + 80, IP_W - 2 * IP_TEXT_X, 30);
        return;
    }
    ip_mode_draw(canvas, pod_play_mode());
    if (ip.art) { /* the cover, flat and square: a straight copy */
        src[0] = 0, src[1] = 0, src[2] = IP_ART, src[3] = IP_ART;
        dst[0] = IP_NP_ART_X, dst[1] = IP_NP_ART_Y, dst[2] = IP_ART, dst[3] = IP_ART;
        canvas_draw_image(canvas, ip.art, src, dst);
    }
    if (ip.np_refl && ip.np_valid) { /* and its reflection, made once with the cover */
        src[0] = 0, src[1] = 0, src[2] = IP_ART, src[3] = IP_NP_REFLECT;
        dst[0] = IP_NP_ART_X, dst[1] = IP_NP_ART_Y + IP_ART, dst[2] = IP_ART, dst[3] = IP_NP_REFLECT;
        canvas_draw_image(canvas, ip.np_refl, src, dst);
    }
    /* The text column beside the cover, centred on it: the title 18 black, the artist and the album 16 grey, the queue place 14 grey. */
    widget_prepare_text_style(ip.st_np1, canvas);
    ip_text(canvas, ip.np_text[0], IP_NP_TEXT_X, 62, IP_W - IP_NP_TEXT_X - 8, 24);
    widget_prepare_text_style(ip.st_np2, canvas);
    ip_text(canvas, ip.np_text[1], IP_NP_TEXT_X, 87, IP_W - IP_NP_TEXT_X - 8, 22);
    ip_text(canvas, ip.np_text[2], IP_NP_TEXT_X, 108, IP_W - IP_NP_TEXT_X - 8, 22);
    if (queue) { /* the place in the queue: "3 / 12" (the translation table allows one %d a text, so no "3 of 12") */
        n = (int)deque_size(queue);
        snprintf(line, sizeof line, "%d / %d", mclGetPlayPos() + 1, n);
        widget_prepare_text_style(ip.st_np3, canvas);
        ip_text(canvas, line, IP_NP_TEXT_X, 132, IP_W - IP_NP_TEXT_X - 8, 20);
    }
    ok = get_playtimeandlength(&pos, &len) == 1 && len > 0;
    if (ok)
        ip.np_pos = pos, ip.np_len = len, ip.np_key = ip.track;
    else
        len = ip.np_len, pos = ip.np_key == ip.track
                                   ? ip.np_pos
                                   : 0; /* no time now: the last length; the position of this track, else 0 */
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    fw = len > 0 ? IP_NP_TRACK_W * pos / len : 0;
    for (i = 0; i < IP_NP_BAR_H; ++i) ip_bar_row(canvas, IP_NP_BAR_Y + i, i, fw, 255);
    for (i = 0; i < IP_NP_BAR_REFLECT; ++i)
        ip_bar_row(canvas, IP_NP_BAR_Y + IP_NP_BAR_H + i, IP_NP_BAR_H - 1 - i, fw,
                   (IP_NP_BAR_REFLECT - i) * 77 / IP_NP_BAR_REFLECT);
    snprintf(a, sizeof a, "%02d:%02d", pos / 60, pos % 60);
    snprintf(b, sizeof b, "-%02d:%02d", (len - pos) / 60, (len - pos) % 60);
    widget_prepare_text_style(ip.st_time, canvas); /* 15 px black, in 50 px side columns */
    ip_text_edge(canvas, a, 8, 1, IP_NP_BAR_Y - 4, 22);
    ip_text_edge(canvas, b, IP_W - 8, 0, IP_NP_BAR_Y - 4, 22);
}

static void ip_paint_current(void *canvas) {
    int kind = ip_top()->kind;
    ip_fill(canvas, 0, 0, IP_W, IP_SCREEN_H, ip_theme_colors()->bg);
    if (ip_split(kind)) ip_paint_pane(canvas);
    if (kind == K_CF)
        ipcf_paint(canvas, ip_valid() ? ip.list : (void *)0, ip_valid() ? ip.count : 0,
                   ip.st_row); /* the covers on white under the bar (patch/ipod_cf.c) */
    else if (kind == K_NOW)
        ip_paint_now(canvas);
    else
        ip_paint_list(canvas, kind);
    ip_paint_bar(canvas, kind);
}

static void ip_paint_scope(void *canvas, const int *saved, int dx, int width) {
    int i;
    I(canvas, CANVAS_OX) = saved[0] + dx;
    I(canvas, CANVAS_OY) = saved[1];
    for (i = 0; i < 4; ++i) I(canvas, CANVAS_CLIP + i * 4) = saved[i + 2];
    if (I(canvas, CANVAS_CLIP) < saved[0]) I(canvas, CANVAS_CLIP) = saved[0];
    if (I(canvas, CANVAS_CLIP) < saved[0] + dx) I(canvas, CANVAS_CLIP) = saved[0] + dx;
    if (I(canvas, CANVAS_CLIP + 4) < saved[1]) I(canvas, CANVAS_CLIP + 4) = saved[1];
    if (I(canvas, CANVAS_CLIP + 8) >= saved[0] + width) I(canvas, CANVAS_CLIP + 8) = saved[0] + width - 1;
    if (I(canvas, CANVAS_CLIP + 8) >= saved[0] + dx + width) I(canvas, CANVAS_CLIP + 8) = saved[0] + dx + width - 1;
    if (I(canvas, CANVAS_CLIP + 12) >= saved[1] + IP_SCREEN_H) I(canvas, CANVAS_CLIP + 12) = saved[1] + IP_SCREEN_H - 1;
}

/* The canvas shifted by dx with its clip cut to the screen columns x0 .. x1 (the split transition draws a page's two halves at different offsets). */
static void ip_paint_range(void *canvas, const int *saved, int dx, int x0, int x1) {
    int i;
    I(canvas, CANVAS_OX) = saved[0] + dx;
    I(canvas, CANVAS_OY) = saved[1];
    for (i = 0; i < 4; ++i) I(canvas, CANVAS_CLIP + i * 4) = saved[i + 2];
    if (I(canvas, CANVAS_CLIP) < saved[0] + x0) I(canvas, CANVAS_CLIP) = saved[0] + x0;
    if (I(canvas, CANVAS_CLIP + 4) < saved[1]) I(canvas, CANVAS_CLIP + 4) = saved[1];
    if (I(canvas, CANVAS_CLIP + 8) >= saved[0] + x1) I(canvas, CANVAS_CLIP + 8) = saved[0] + x1 - 1;
    if (I(canvas, CANVAS_CLIP + 12) >= saved[1] + IP_SCREEN_H) I(canvas, CANVAS_CLIP + 12) = saved[1] + IP_SCREEN_H - 1;
}

/* A split transition (the reference's fullscreen pages): the split page's menu half slides left out by half the width and its artwork pane slides right out, uncovering the
 * fullscreen page that stays still; closing runs it backwards (the halves slide in over the fullscreen page's picture). Returns 1 when it painted the whole screen. */
static int ip_paint_split(void *canvas, const int *saved, int old_dx, int new_dx) {
    if (ip_render_direction() > 0) {
        ip_paint_range(canvas, saved, 0, 0, IP_W);
        ip_render_begin();
        ip_paint_current(canvas);
        ip_render_end();
        ip_paint_range(canvas, saved, old_dx, old_dx > 0 ? old_dx : 0, IP_SPLIT_X + old_dx + IP_SHADOW_W);
        ip_render_out(canvas, 0);
        ip_paint_range(canvas, saved, -old_dx, IP_SPLIT_X - old_dx, IP_W);
        ip_render_out(canvas, 1);
    } else {
        ip_paint_range(canvas, saved, 0, 0, IP_W);
        ip_render_out(canvas, 2);
        ip_paint_range(canvas, saved, new_dx, new_dx > 0 ? new_dx : 0, IP_SPLIT_X + new_dx + IP_SHADOW_W);
        ip_render_begin();
        ip_paint_current(canvas);
        ip_render_end();
        ip_paint_range(canvas, saved, -new_dx, IP_SPLIT_X - new_dx, IP_W);
        ip.no_shadow = 1; /* the shadow belongs to the menu half */
        ip_render_begin();
        ip_paint_current(canvas);
        ip_render_end();
        ip.no_shadow = 0;
    }
    return 1;
}

static int ip_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int saved[6], i, old_dx, new_dx;
    (void)ctx;
    if (!canvas || !ip.win) return RET_OK;
    saved[0] = I(canvas, CANVAS_OX), saved[1] = I(canvas, CANVAS_OY);
    for (i = 0; i < 4; ++i) saved[i + 2] = I(canvas, CANVAS_CLIP + i * 4);
    if (!ip_render_active() && ip_split(ip_top()->kind) &&
        saved[2] >=
            saved[0] +
                IP_SPLIT_X) { /* only the pane's rectangle is dirty (a pan or fade frame): the menu is not painted again, */
        ip_paint_pane(canvas); /* and the recorded model of the whole page is left as it is */
        return RET_OK;
    }
    if (ip_render_split()) {
        ip_render_offsets(&old_dx, &new_dx);
        ip_paint_split(canvas, saved, old_dx, new_dx);
        I(canvas, CANVAS_OX) = saved[0], I(canvas, CANVAS_OY) = saved[1];
        for (i = 0; i < 4; ++i) I(canvas, CANVAS_CLIP + i * 4) = saved[i + 2];
        return RET_OK;
    }
    if (ip_render_active()) {
        int width = ip_render_width();
        ip_render_offsets(&old_dx, &new_dx);
        if (width == IP_SPLIT_X) ip_paint_pane(canvas); /* stationary right pane between split menus */
        ip_paint_scope(canvas, saved, old_dx, width);
        ip_render_out(canvas, 2);
        ip_paint_scope(canvas, saved, new_dx, width);
    }
    ip_render_begin();
    ip_paint_current(canvas);
    ip_render_end();
    I(canvas, CANVAS_OX) = saved[0], I(canvas, CANVAS_OY) = saved[1];
    for (i = 0; i < 4; ++i) I(canvas, CANVAS_CLIP + i * 4) = saved[i + 2];
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Actions
 */

static int ip_fullscreen(int kind) { return kind == K_NOW || kind == K_CF; }

/* The slide between two levels: the menu half (IP_SPLIT_X) between split pages; 0, the split, between a split page and a fullscreen one (Now Playing, Cover Flow); else the whole width. */
static int ip_slide_width(int from, int to) {
    if (ip_split(from) && ip_split(to)) return IP_SPLIT_X;
    if ((ip_split(from) && ip_fullscreen(to)) || (ip_fullscreen(from) && ip_split(to))) return 0;
    return IP_W;
}

static void ip_push(int kind) {
    if (ip.depth + 1 >= IP_DEPTH) return;
    ip_render_transition(1, ip_slide_width(ip_top()->kind, kind));
    {
        struct lvl *nl = &ip.st[++ip.depth];
        nl->kind = kind, nl->sel = nl->top = 0, nl->title[0] = 0;
    }
    ip_wheel_reset();
    ip_load();
    ip_redraw();
    ip_retime(); /* the pace of the new level: Cover Flow's frames, else the pan stops */
}

static void ip_pop(void) {
    if (ip.depth == 0) {
        ip_render_cancel();
        navigator_back(); /* MENU on the main menu closes the page */
        return;
    }
    ip_render_transition(-1, ip_slide_width(ip_top()->kind, ip.st[ip.depth - 1].kind));
    if (ip_top()->kind == K_CF) ipcf_close(); /* Cover Flow's frame and textures go */
    ip.depth--;
    ip_wheel_reset();
    ip_load();
    if (ip.depth == 0) ip_pane_reset(); /* back on the main menu: a new random cover, the playing one looked up again */
    ip_redraw();
    ip_retime();
}

/* A long press of MENU (IP_LONG_MS) pops every level to the main menu, with the slide of the last one (the reference's). */
static void ip_pop_root(void) {
    int d;
    if (ip.depth == 0) return;
    ip_render_transition(-1, ip_slide_width(ip_top()->kind, K_MAIN));
    for (d = ip.depth; d > 0; --d)
        if (ip.st[d].kind == K_CF) ipcf_close();
    ip.depth = 0;
    ip_wheel_reset();
    ip_load();
    ip_pane_reset();
    ip_redraw();
    ip_retime();
}

/* A step of the wheel: the cursor moves `rows` rows (no wrap, as the iPod; clamped at the ends, and a step that wanted to go past an end nudges the rows), the
 * window follows it. */
static void ip_step(int dir, int rows) {
    struct lvl *l = ip_top();
    if (ip_render_active()) ip_render_cancel();
    int n, want;
    if (l->kind == K_NOW) return; /* nothing turns on Now Playing in this version (docs/modules/ipod.md) */
    if (l->kind != K_MAIN && l->kind != K_MUSIC && l->kind != K_SETTINGS && !ip_ensure()) return;
    n = ip_rows();
    if (n <= 0) return;
    want = l->sel + dir * rows;
    want = want < 0 ? 0 : want >= n ? n - 1 : want;
    if (l->kind ==
        K_CF) { /* the slide goes to the album (ipod_cf.c), the pace is the animation's; at an end nothing happens */
        if (want != l->sel) l->sel = want, ipcf_goto(want), ip_retime(), ip_redraw();
        return;
    }
    l->sel = want;
    if (l->sel < l->top) l->top = l->sel;
    {
        int visible = ip_tall(l->kind) ? IP_TALL_ROWS : IP_ROWS;
        if (l->sel >= l->top + visible) l->top = l->sel - visible + 1;
    }
    ip_redraw();
}

/* The stock Songs row's handler (@0x5275a4: loadSongList of the shown list), then start_player as the stock Play all button does (@0x525d48): the queue is
 * copied, force_refreshflag is set, the page stays where it is. The Now Playing level shows the result. */
static void ip_play(int at, int shuffle) {
    void *pick, *queue, *first;
    unsigned n, idx = 0;
    int found;
    if (!ip_ensure() || at < 0 || (unsigned)at >= ip.count) return;
    pick = deque_at(ip.list, (unsigned)at);
    if (!pick || access(cc_str(pick, REC_PATH), F_OK)) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    queue = _create_deque("stSongInfo");
    if (!queue) return;
    deque_init(queue);
    if (ip_top()->kind ==
        K_PL_TRACKS) { /* the playlist's id goes back into classinfo[1], as the stock row tap leaves it (the Songs page does the same before every play) */
        void *pl = ip_stock_list(K_PLAYLISTS);
        int row = ip.st[ip.depth - 1].sel;
        if (pl && (unsigned)row < deque_size(pl))
            *(int *)(CLASSINFO + CLASSINFO_ARG) = I(deque_at(pl, (unsigned)row), REC_DISC);
    }
    found = loadSongList(queue, cc_str(pick, REC_NAME), I(pick, REC_CUE_START), ip.cls);
    n = deque_size(queue);
    if (n) { /* the row's own index wins over a duplicate file name (the Songs page's rule) */
        if ((unsigned)at < n && !strcmp(cc_str(deque_at(queue, (unsigned)at), REC_PATH), cc_str(pick, REC_PATH)) &&
            I(deque_at(queue, (unsigned)at), REC_CUE_START) ==
                I(pick, REC_CUE_START)) /* (a CUE image's tracks share the path) */
            idx = (unsigned)at;
        else if (found >= 0 && (unsigned)found < n)
            idx = (unsigned)found;
    }
    if (shuffle &&
        n) { /* Shuffle Songs leaves the podcast episodes out (patch/pcmodel.c; the queue itself when there are none) */
        int at_i = (int)idx;
        queue = pc_strip(queue, &at_i);
        idx = (unsigned)at_i;
        n = queue ? deque_size(queue) : 0;
        if (!queue) {
            pod_toast(TR("No songs"));
            return;
        }
    }
    first = n ? deque_at(queue, idx) : (void *)0;
    if (!first || access(cc_str(first, REC_PATH), F_OK)) {
        deque_destroy(queue);
        pod_toast(TR(n ? "Storage unavailable" : "No songs"));
        return;
    }
    *(int *)G_CLASS_TYPE = ip.cls;
    if (shuffle)
        pod_set_mode_for_queue(
            MODE_SHUFFLE); /* Shuffle Songs: stock Shuffle over the whole queue, as the Shuffle page sets it (patch/shuffle.c) */
    start_player(queue, (int)idx, ip.cls, PLAY_MODE);
    *(unsigned char *)FORCE_REFRESH = 1;
    deque_destroy(queue);
    ip_push(K_NOW);
}

/* Shuffle Songs: the whole library is the queue (the Songs query, as the Shuffle page), a random first song, stock Shuffle (mode 2) so the rest are drawn at random; the iPod's
 * own Now Playing level shows it (no stock page). Nothing is changed when the library is empty or the first file is gone. */
static void ip_shuffle_all(void) {
    void *list = loadLocalClassList(CLASS_ALL_SONGS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    unsigned n = list ? deque_size(list) : 0;
    if (!n) {
        pod_toast(TR("Update Local Music first"));
        return;
    }
    ip.list = list, ip.count = n, ip.first = deque_at(list, 0), ip.cls = CLASS_ALL_SONGS;
    ip_play((int)pod_rand(n), 1);
}

/* Centre press on a Settings row: Shuffle flips Off / Songs, Repeat cycles Off, One, All (both are the one stock play mode: Shuffle is mode 2, which has no repeat of its own, so
 * turning Repeat on turns Shuffle off and the reverse). */
static void ip_settings_select(int row) {
    int mode = pod_play_mode();
    if (row == S_SHUFFLE) {
        if (mode == MODE_SHUFFLE)
            pod_set_in_order();
        else
            pod_set_mode(MODE_SHUFFLE);
    } else if (row == S_REPEAT)
        pod_set_mode(mode == MODE_REPEAT_ONE   ? MODE_REPEAT_ALL
                     : mode == MODE_REPEAT_ALL ? MODE_ORDER
                                               : MODE_REPEAT_ONE);
    else if (row == S_APPEARANCE && ip_theme_toggle() >= 0) {
        ip_render_cancel();
        ip_theme_apply(ip.win, widget_lookup(ip.win, "ipod_wheel_img", 1));
        ip.track = ~0u;
        ip.np_valid = 0;
    }
    ip_redraw();
}

/* Open a level whose title bar names the record it came from (an album, an artist, a playlist). The text is copied before anything can replace the stock list it points into,
 * cut at a character boundary. */
static void ip_push_titled(int kind, const char *title) {
    char t[40];
    unsigned n = 0;
    while (title[n] && n < sizeof t - 1) t[n] = title[n], ++n;
    while (n && title[n] && (title[n] & 0xc0) == 0x80) --n; /* not in the middle of a character */
    t[n] = 0;
    ip_push(kind);
    if (ip_top()->kind == kind && !ip_top()->title[0]) memcpy(ip_top()->title, t, n + 1);
}

/* An artist: the album list (the stock "All songs" record first), or, with exactly one album, that album's songs directly. The query tells which. */
static void ip_open_artist(int row) {
    char name[40], album[40];
    void *list = ip.list, *rec = deque_at(list, (unsigned)row);
    unsigned n, k, albums = 0, i;
    const char *s = cc_str(rec, REC_TITLE);
    for (i = 0; s[i] && i < sizeof name - 1; ++i) name[i] = s[i];
    name[i] = 0;
    album[0] = 0;
    loadAlbumList(CLASS_ARTISTS, rec);
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    for (k = 0; k < n; ++k) {
        void *r = deque_at(list, k);
        if (I(r, REC_ID) == ID_ALL_SONGS) continue;
        if (!albums++) {
            s = cc_str(r, REC_ALBUM);
            for (i = 0; s[i] && i < sizeof album - 1; ++i) album[i] = s[i];
            album[i] = 0;
        }
    }
    if (albums == 1)
        ip_push_titled(K_TRACKS, album); /* the real iPod names the page for the album */
    else
        ip_push_titled(K_ARTIST_ALBUMS, name);
}

static void ip_select(void) {
    struct lvl *l = ip_top();
    int kind = l->kind;
    if (kind == K_NOW) {
        playpause_quick_click();
        ip_look();
        ip_redraw();
        return;
    }
    if (kind == K_SETTINGS) {
        ip_settings_select(l->sel);
        return;
    }
    if (kind == K_MAIN) {
        int row = ip_root_id(l->sel);
        if (row == ROOT_MUSIC)
            ip_push(K_MUSIC);
        else if (row == ROOT_COVER) {
            if (ipcf_open(ip.win))
                ip_push(K_CF);
            else
                coverflow_open();
        } else if (row == ROOT_PODCASTS)
            ip_push(K_PODCASTS);
        else if (row == ROOT_SHUFFLE)
            ip_shuffle_all();
        else if (row == ROOT_NOW)
            ip_push(K_NOW);
        else if (row == ROOT_SETTINGS)
            ip_push(K_SETTINGS);
        return;
    }
    if (kind == K_MUSIC) {
        switch (l->sel) {
        case M_COVER: /* Cover Flow inside the iPod screen (ipod_cf.c); no memory for its frame: the existing Cover Flow page, over this one */
            if (ipcf_open(ip.win))
                ip_push(K_CF);
            else
                coverflow_open();
            break;
        case M_ALBUMS:
            ip_push(K_ALBUMS);
            break;
        case M_ARTISTS:
            ip_push(K_ARTISTS);
            break;
        case M_SONGS:
            ip_push(K_SONGS);
            break;
        case M_PLAYLISTS:
            ip_push(K_PLAYLISTS);
            break;
        case M_SHUFFLE:
            ip_shuffle_all();
            break; /* Shuffle Songs: stock Shuffle over the library, the iPod's own Now Playing */
        }
        return;
    }
    if (!ip_ensure() || !ip.count) return;
    if (kind == K_PODCASTS)
        ip_push_titled(K_PC_EPS, ip.pc_shows[l->sel].title[0] ? ip.pc_shows[l->sel].title : ip.pc_shows[l->sel].dir);
    else if (kind == K_PC_EPS)
        ip_pc_play(l->sel);
    else if (ip_is_tracks(kind))
        ip_play(l->sel, 0);
    else if (kind == K_ALBUMS || kind == K_CF ||
             kind == K_ARTIST_ALBUMS) { /* Cover Flow's centre button: the album's tracks */
        void *rec = ip_rec(kind, ip.list, l->sel);
        ip_push_titled(K_TRACKS, I(rec, REC_ID) == ID_ALL_SONGS
                                     ? TR(kind == K_ARTIST_ALBUMS ? "local_allsong" : "All albums")
                                     : cc_str(rec, REC_ALBUM));
    } else if (kind == K_ARTISTS)
        ip_open_artist(l->sel);
    else if (kind == K_PLAYLISTS)
        ip_push_titled(K_PL_TRACKS, cc_str(deque_at(ip.list, (unsigned)l->sel), REC_TITLE));
}

/* A tap on an episode: the show's local episodes are the queue, as the Podcasts page plays one (pg_episode_queue: resume, speed, List play), then the page's own Now Playing. */
static void ip_pc_play(int at) {
    char root[PC_FILE + 20];
    int idx = 0, d = ip.depth;
    void *queue;
    if (d < 1 || ip.st[d - 1].kind != K_PODCASTS || !ip.pc_shows || ip.st[d - 1].sel >= ip.pc_n || at < 0 ||
        at >= ip.pc_neps)
        return;
    pc_root(root);
    queue = pg_episode_queue(root, &ip.pc_shows[ip.st[d - 1].sel], ip.pc_eps, ip.pc_neps, at, &idx);
    if (!queue) return;
    *(int *)G_CLASS_TYPE = 1;
    start_player(queue, idx, 1, PLAY_MODE);
    *(unsigned char *)FORCE_REFRESH = 1;
    deque_destroy(queue);
    ip_push(K_NOW);
}

/* previous / next: the stock functions the Now Playing buttons and the hardware keys call (a click within a second of the last is ignored by stock). */
static void ip_skip(int next, void *e) {
    unsigned ev[4];
    if (!e) {
        memset(ev, 0, sizeof ev);
        ev[2] = time_now_ms();
        e = ev;
    }
    if (next)
        next_quick_click(e, 0);
    else
        prev_quick_click(e, 0);
    if (ip_look()) ip_redraw();
}

/* ---------------------------------------------------------------------------
 * The wheel's touch
 */
static void ip_local(void *e, int *x, int *y) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(ip.wheel, pt);
    *x = pt[0] - IP_WHEEL_D / 2, *y = pt[1] - IP_WHEEL_D / 2;
}

static void ip_release(void) {
    if (ip.touch != R_NONE) widget_ungrab(ip.win, ip.wheel);
    ip.touch = R_NONE;
}

/* Rows a step for a list of n rows at tier idx (0 .. any: past the last tier is the last tier). A list of IP_LONG rows or fewer is always 1. */
__attribute__((noinline)) int ip_tier_rows(int n, int idx) {
    static const unsigned char tiers[] = {1, 2, 3, 5, 8, 13, 21, 34};
    if (n <= IP_LONG || idx <= 0) return 1;
    return tiers[idx > (int)sizeof tiers - 1 ? (int)sizeof tiers - 1 : idx];
}

static int ip_clamp150(int v) { return v < -150 ? -150 : v > 150 ? 150 : v; }

/* One move of a finger that began on the ring, to (x, y) at time `now` (ms). The turn from the last angle accumulates in ip.acc and every IP_STEP of it moves
 * the cursor, with these rules (docs/modules/ipod.md "The wheel"):
 *   chord      a move whose chord passes within IP_DEAD_R of the centre turns nothing (the angle jumps there); the reference angle is just taken again.
 *   reversal   after the direction flips, IP_REVERSE of reverse travel is swallowed first (the turn-around jitter), then the accumulator starts again from 0.
 *   speed      the angular speed, clamped at IP_VMAX and smoothed (3/20), reset by a pause (IP_PAUSE_MS) or a reversal; on a list of more than IP_LONG rows, held above IP_FAST
 *              for IP_TIER_MS a time it climbs one tier of rows a step, and it is tier 0 (one row) again the moment the speed falls below. */
static void ip_turn_move(int x, int y, unsigned now) {
    int a = ip_angle(x, y), d, mag, dt, idx = 0, rows;
    if (ip_chord_near(ip_clamp150(ip.lx), ip_clamp150(ip.ly), ip_clamp150(x), ip_clamp150(y))) {
        ip.last = a, ip.lt = now, ip.speed = ip.fast = 0;
        return;
    }
    d = ip_turn(ip.last, a);
    ip.last = a;
    if (!d) return;
    mag = d < 0 ? -d : d;
    dt = (int)(now - ip.lt);
    ip.lt = now;
    if (dt > IP_PAUSE_MS || dt < 0)
        ip.speed = ip.fast = 0;
    else if (dt > 0) {
        int inst = mag * 1000 / dt;
        if (inst > IP_VMAX) inst = IP_VMAX;
        ip.speed += (inst - ip.speed) * IP_SMOOTH_NUM / IP_SMOOTH_DEN;
    }
    if (!ip.dir) ip.dir = d > 0 ? 1 : -1;
    if ((d > 0 ? 1 : -1) != ip.dir) {
        ip.rev += mag;
        if (ip.rev < IP_REVERSE) return;
        ip.dir = -ip.dir, ip.rev = 0, ip.acc = 0, ip.speed = ip.fast = 0;
        return;
    }
    if (ip.rev) { /* travel back in the committed direction first takes back the swallowed reverse travel (a jitter nets zero) */
        int back = mag < ip.rev ? mag : ip.rev;
        ip.rev -= back, mag -= back;
        d = d < 0 ? -mag : mag;
    }
    ip.acc += d;
    if (ip.speed > IP_FAST) {
        if (!ip.fast) ip.fast = 1, ip.fast_t0 = now;
        idx = (int)((now - ip.fast_t0) / IP_TIER_MS);
    } else
        ip.fast = 0;
    rows = ip_tier_rows(ip_rows(), idx);
    while (ip.acc >= IP_STEP) ip.acc -= IP_STEP, ip.turned = 1, ip_step(1, rows);
    while (ip.acc <= -IP_STEP) ip.acc += IP_STEP, ip.turned = 1, ip_step(-1, rows);
}

static int ip_on_wheel(void *ctx, void *e) {
    int type, x, y, r2;
    (void)ctx;
    if (!e || !ip.win) return RET_OK;
    type = *(int *)e;
    if (type == EVT_POINTER_DOWN) {
        ip_local(e, &x, &y);
        r2 = x * x + y * y;
        ip_release();
        if (r2 > IP_RING_R * IP_RING_R) return RET_OK; /* the square's corners are not the wheel */
        ip.touch = r2 < IP_HUB_R * IP_HUB_R ? R_CENTRE : R_RING;
        ip.sx = ip.lx = x, ip.sy = ip.ly = y;
        ip.last = ip_angle(x, y), ip.turned = ip.far = 0, ip.lt = (unsigned)I(e, 8);
        ip.down_t = (unsigned)I(e, 8), ip.long_done = 0;
        ip.menu_zone = ip.touch == R_RING && y < 0 && -y > (x < 0 ? -x : x);
        ip_wheel_reset();
        widget_grab(ip.win, ip.wheel);
        ip_retime();
    } else if (type == EVT_POINTER_MOVE && ip.touch != R_NONE) {
        int dx, dy;
        ip_local(e, &x, &y);
        dx = x - ip.sx, dy = y - ip.sy;
        if (dx * dx + dy * dy >= IP_TAP_PX * IP_TAP_PX) ip.far = 1;
        if (ip.touch == R_RING && !ip.long_done) ip_turn_move(x, y, (unsigned)I(e, 8));
        ip.lx = x, ip.ly = y;
    } else if (type == EVT_POINTER_UP && ip.touch != R_NONE) {
        int touch = ip.touch, turned = ip.turned, far = ip.far, sx = ip.sx, sy = ip.sy, was_long = ip.long_done;
        unsigned held = (unsigned)I(e, 8) - ip.down_t;
        ip_local(e, &x, &y);
        if ((x - sx) * (x - sx) + (y - sy) * (y - sy) >= IP_TAP_PX * IP_TAP_PX) far = 1;
        ip_release();
        if (was_long) {
            ip_retime();
            return RET_OK;
        }
        if (!turned && !far && ip.menu_zone &&
            held >=
                IP_LONG_MS) { /* the long press, when the timer had not seen it yet (on the main menu it closes nothing) */
            ip_pop_root();
            return RET_OK;
        }
        ip_retime();
        if (turned || far) return RET_OK;
        if (touch == R_CENTRE)
            ip_select();
        else if ((sy < 0 ? -sy : sy) > (sx < 0 ? -sx : sx)) {
            if (sy < 0)
                ip_pop(); /* MENU */
            else
                playpause_quick_click(), ip_look(), ip_redraw();
        } else
            ip_skip(sx > 0, e);
    } else if (type == EVT_POINTER_ABORT) {
        ip_release();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The timer, the window's events
 */
static int ip_tick(const void *timer) {
    int finished = 0;
    (void)timer;
    if (!ip.win || !ip.fg) {
        ip.timer = 0;
        return RET_OK;
    }
    if (ip.touch == R_RING && ip.menu_zone && !ip.long_done && !ip.turned && !ip.far && ip.depth > 0 &&
        time_now_ms() - ip.down_t >= IP_LONG_MS) {
        ip.long_done = 1; /* MENU held: back to the main menu */
        ip_pop_root();
    }
    if (!pod_screen_lit()) { /* the screen is off: no pan, no cover work, no repaint (the idle-power rule); the next lit tick looks again */
        ip_pane_xfer_stop();
        ip_retime();
        return RET_REPEAT;
    }
    if (ip_render_active()) {
        if (ip_render_tick()) ip_redraw();
        if (ip_render_active()) return RET_REPEAT;
        finished = 1;
    }
    if (!ip_valid() &&
        pod_is_top(
            ip.win)) { /* another query replaced the stock list under the page: read it again (the Songs page's stale timer) */
        ip_load();
        ip_redraw();
    }
    if (ip_rows_tick()) ip_redraw();
    if (ip_top()->kind == K_CF && ip_valid() && ipcf_tick(ip.list, ip.count))
        ip_redraw(); /* Cover Flow slides and decodes on this timer (ipod_cf.c) */
    if ((ip.pane.worker || ip.pane.xfer) && !(ip_split(ip_top()->kind) && pod_is_top(ip.win)))
        ip_pane_xfer_stop(); /* the pane is not in front: its extraction goes (cc_build_stop) */
    if (ip_pane_step()) ip_redraw_pane(); /* the cover pane of a split page: only its rectangle is invalidated */
    if (finished || ip.ival == IP_TICK_MS ||
        ++ip.lookn >= IP_DRIFT_LOOK) { /* refresh playback as soon as a transition finishes */
        ip.lookn = 0;
        if (ip_look()) ip_redraw();
    }
    ip_retime(); /* one timer, its interval changed in place (timer_modify): never removed or added while the page lives */
    return RET_REPEAT;
}

static int ip_first(const void *timer) {
    (void)timer;
    ip.timer = 0;
    if (!ip.win || !ip.fg) return RET_OK;
    ip.ival = ip_want_ms();
    ip.timer = timer_add(ip_tick, (void *)0, ip.ival);
    if (ip_look()) ip_redraw();
    return RET_OK;
}

static void ip_unarm(void) {
    if (ip.timer) timer_remove(ip.timer);
    ip.timer = 0;
}

static int ip_on_background(void *ctx, void *e) {
    (void)e;
    if (!ip.win || ctx != ip.win) return RET_OK;
    ip.fg = 0;
    ip_render_cancel();
    ip_rows_stop();
    ip_pane_xfer_stop();
    ip_unarm();
    ip_release();
    return RET_OK;
}

static int ip_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!ip.win || ctx != ip.win) return RET_OK;
    ip.fg = 1;
    ip_render_cancel();
    ip_load(); /* another page may have queried (the Playlists a stock page opened, Cover Flow ...): the list is read again */
    if (ip.depth == 0) ip_pane_reset(); /* ... and the main menu has a new random cover */
    ip.sig[0] = ip.sig[1] = ip.sig[2] = ip.sig[3] = ip.sig[4] = ~0u; /* ... and the screen is painted fresh */
    if (!ip.timer) ip.timer = timer_add(ip_first, (void *)0, IP_FIRST_MS);
    ip_redraw();
    return RET_OK;
}

static int ip_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != ip.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    ip_unarm();
    ip_render_close();
    if (ip.touch != R_NONE) widget_ungrab(ip.win, ip.wheel);
    ip_pane_xfer_stop();
    ip_rows_free();
    if (ip.art) bitmap_destroy(ip.art);
    if (ip.np_refl) bitmap_destroy(ip.np_refl);
    if (ip.pane.bmp[0]) bitmap_destroy(ip.pane.bmp[0]);
    if (ip.pane.bmp[1]) bitmap_destroy(ip.pane.bmp[1]);
    if (ip.pane.mix) bitmap_destroy(ip.pane.mix);
    if (ip.shadow) bitmap_destroy(ip.shadow);
    for (int m = 0; m < 4; ++m)
        if (ip.mode_bmp[m]) bitmap_destroy(ip.mode_bmp[m]);
    ipcf_close();
    ip_pc_free();
    memset(&ip, 0, sizeof ip);
    return RET_OK;
}

/* The menu's iPod row. 0 once the page is up (or already open); -1 when it could not open (no window, an asset that is not ours): nothing happens. */
int ipod_open(void) {
    if (ip.win) return 0;
    memset(&ip, 0, sizeof ip);
    ip.win = window_open("m1plus_ipod");
    if (!ip.win) {
        memset(&ip, 0, sizeof ip);
        return -1;
    }
    widget_on(ip.win, EVT_DESTROY, ip_on_destroy, ip.win);
    ip.screen = widget_lookup(ip.win, "ipod_screen", 1);
    ip.wheel = widget_lookup(ip.win, "ipod_wheel", 1);
    ip.st_row = widget_lookup(ip.win, "label_ip_row", 1);
    ip.st_sel = widget_lookup(ip.win, "label_ip_sel", 1);
    ip.st_title = widget_lookup(ip.win, "label_ip_title", 1);
    ip.st_small = widget_lookup(ip.win, "label_ip_small", 1);
    ip.st_subsel = widget_lookup(ip.win, "label_ip_subsel", 1);
    ip.st_np1 = widget_lookup(ip.win, "label_ip_np1", 1);
    ip.st_np2 = widget_lookup(ip.win, "label_ip_np2", 1);
    ip.st_time = widget_lookup(ip.win, "label_ip_time", 1);
    ip.st_val = widget_lookup(ip.win, "label_ip_val", 1);
    ip.st_np3 = widget_lookup(ip.win, "label_ip_np3", 1);
    if (!ip.screen || !ip.wheel || !ip.st_row || !ip.st_sel || !ip.st_title || !ip.st_small || !ip.st_subsel ||
        !ip.st_np1 || !ip.st_np2 || !ip.st_time || !ip.st_val || !ip.st_np3) {
        navigator_back(); /* an asset that is not ours: the window goes again */
        ip.win = (void *)0; /* (its destroy handler leaves a newer page alone) */
        memset(&ip, 0, sizeof ip);
        return -1;
    }
    ip.depth = 0;
    ip.now_shown = ip_now_shown();
    ip.pane.trk = ~0u;
    ip.pc_any = -1;
    ip_theme_load();
    ip_theme_apply(ip.win, widget_lookup(ip.win, "ipod_wheel_img", 1));
    ip_render_open();
    ip_shadow_make();
    ip.st[0].kind = K_MAIN;
    ip.track = ~0u; /* the first look makes the cover (the placeholder when nothing plays) */
    ip.fg = 1;
    widget_on(ip.win, EVT_WINDOW_TO_BG, ip_on_background, ip.win);
    widget_on(ip.win, EVT_WINDOW_TO_FG, ip_on_foreground, ip.win);
    widget_on(ip.wheel, EVT_POINTER_DOWN, ip_on_wheel, (void *)0);
    widget_on(ip.wheel, EVT_POINTER_MOVE, ip_on_wheel, (void *)0);
    widget_on(ip.wheel, EVT_POINTER_UP, ip_on_wheel, (void *)0);
    widget_on(ip.wheel, EVT_POINTER_ABORT, ip_on_wheel, (void *)0);
    widget_on(ip.screen, EVT_AFTER_PAINT, ip_on_paint, (void *)0);
    ip.timer = timer_add(ip_first, (void *)0, IP_FIRST_MS);
    return 0;
}
