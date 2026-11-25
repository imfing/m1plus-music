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
 *   wheel      the touch on the ring. The finger's angle (ip_angle, integer atan) around the wheel's centre turns one step every IP_STEP (20 degrees); a touch
 *              that turns no step and travels less than IP_TAP_PX is a tap: the centre button selects, the ring's four sectors are MENU (top), previous (left),
 *              next (right) and play / pause (bottom). On Now Playing a hold of previous / next scans (ip_scan_tick: its own target, a direct mclSetSeek every IP_SCAN_SEEK_MS). Outside the ring's circle a touch does nothing (the view is square). The view grabs the touch.
 *   play       a track opens the stock way: loadSongList of the shown list, start_player (what the stock Play all button calls), Now Playing level.
 *   sound      none: docs/modules/ipod.md "The wheel" has the evidence and the options.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "libsrc.h"
#include "ipod_theme.h"
#include "ipod_render.h"
#include "textgamma.h"
#include "entries.h"
#undef widget_prepare_text_style
#undef canvas_draw_text_in_rect
#undef canvas_draw_image
#define widget_prepare_text_style ip_render_prepare
#define canvas_draw_text_in_rect ip_render_text
#define canvas_draw_image ip_render_image
#include "common.h"
#include "i18n.h"
#include "podcasts.h"
#include "radio.h"
#include "lyrics.h"
#include "peqout.h"
#include "scrobble.h"
#include "plmeta.h"

/* patch/ipod_cf.c: the Cover Flow screen (level K_CF: the albums list drawn as covers; docs/modules/ipod-coverflow.md) */

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
    K_CF_TRACKS,
    K_PODCASTS,
    K_PC_EPS,
    K_GENRES,
    K_GENRE_SONGS,
    K_COMPOSERS,
    K_COMPOSER_ALBUMS
};
enum { S_SHUFFLE, S_REPEAT, S_APPEARANCE, S_COUNT };
/* the iPod classic's default menus (its user guide), less the levels the player has no content for */
enum { M_COVER, M_PLAYLISTS, M_ARTISTS, M_ALBUMS, M_SONGS, M_GENRES, M_COMPOSERS, M_COUNT };
enum { ROOT_MUSIC, ROOT_COVER, ROOT_PODCASTS, ROOT_SETTINGS, ROOT_SHUFFLE, ROOT_NOW, ROOT_COUNT };
enum { R_NONE, R_CENTRE, R_RING };

static const char *const MAIN_KEYS[ROOT_COUNT] = {"Music",         "Cover Flow", "Podcasts", "cdrippersettings",
                                                  "Shuffle Songs", "Now Playing"};
static const char *const MUSIC_KEYS[M_COUNT] = {"Cover Flow", "Playlists", "Artists",  "Albums",
                                                "Songs",      "Genres",    "Composers"};
static const char *const SET_KEYS[S_COUNT] = {"Shuffle", "Repeat", "Appearance"};
static const char *const MODE_ICONS[5] = {
    "ipod_mode_shuffle", "ipod_mode_repeat", "ipod_mode_repeat1", "ipod_playing",
    "ipod_shuffle_big"}; /* the play mode marks, the playing track's speaker, the shuffle slider's mark */
static void *ip_mode_bitmap(int i);
static int ip_lyr_load(void);
static void ip_pc_play(int at);
#define IP_NP_GONE 3 /* looks without a current track before Now Playing says Not Playing */

/* Now Playing's views, cycled by the centre: the progress bar, the scrubber, the shuffle slider, the lyrics. */
enum { IPV_BAR, IPV_SCRUB, IPV_SHUFFLE, IPV_LYRICS };

/* The lyrics view's text: the .lrc read whole, its time tags and tag lines dropped, the lines NUL-terminated in place (src: their offsets); rows: the lines wrapped
 * to IP_LY_W at the first paint (laid), each a byte range of text. */
struct ip_lyr {
    int n_src, n_rows, laid;
    unsigned short src[IP_LY_SRC], row_at[IP_LY_ROWS];
    unsigned char row_len[IP_LY_ROWS];
    char text[IP_LY_BUF];
};

struct lvl {
    int kind, sel, top;
    char title
        [40]; /* the title bar's text for a list opened from a record (an album, an artist, a playlist); empty: the level's own name */
};

#define IP_ROW_ART IP_TALL_H /* the cover fills the row exactly: stacked covers leave no seam */
struct row_art {
    void *bmp;
    int kind, index;
    unsigned id, key[4], parts, drawn, waiting, songs,
        albums, /* songs: a playlist row's track count, or a genre row's artist count, albums: a genre row's album count (these rows have no cover) */
        last; /* last: the tick clock when a row last wanted it (the least recent unwanted slot is reused) */
    char *path[4];
};

static struct {
    void *win, *screen, *wheel;
    void *st_row, *st_sel, *st_title, *st_small, *st_subsel, *st_np1, *st_np2, *st_time, *st_val, *st_np3, *st_shuf,
        *st_selb; /* hidden labels: the text styles */
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
    int side,
        scan; /* the touch began on the previous / next sector; a hold of it on Now Playing is scanning (sc_pos is the scan target, sc_dir +1 / -1, sc_n ticks so far, sc_len the length) */
    int sc_dir, sc_n, sc_pos, sc_len;
    int sc_hold; /* after the last seek: sc_pos stays on the bar until the player's time reaches it or sc_until (ms) passes */
    unsigned sc_until;
    int sc_sent; /* the target of the last direct seek (the scan's start position before the first), and its time (ms) */
    unsigned sc_seek_t;
    int scrub; /* Now Playing's centre press put the scrubber up: the wheel moves sc_pos (seeking as the scan does) */
    unsigned scrub_t,
        vol_until; /* the scrubber's last turn (ms); the volume bar shows until this time (0: not shown) */
    int npv; /* Now Playing's view besides the scrubber (ip.scrub): IPV_SHUFFLE, IPV_LYRICS, else 0 */
    unsigned npv_t; /* the shuffle slider's last turn (ms) */
    unsigned th_t0; /* the shuffle slider's thumb glides from choice th_from since this time (0: still) */
    unsigned bar_t0; /* the title bar drops in since this time (0: in place) */
    int bar_hold; /* a full-screen page opens or closes: no title bar until the split ends, then it drops in (ip_bar_wait) */
    unsigned vs_t0; /* the volume bar slides in over the progress bar (vs_back: out again) since this time (0: still) */
    int vs_back;
    int bar_end; /* the drop just ended: the timer looks at playback as after a level slide */
    int th_from;
    unsigned sl_t0; /* a slide between two views started at this time (0: none): sl_from out, sl_to in */
    int sl_from, sl_to;
    struct ip_lyr *lyr; /* the lyrics view's text, read from the track's .lrc (malloc, kept until the page closes) */
    int ly_top; /* the lyrics view's scroll, in lines */
    unsigned down_t; /* the time of that touch (ms) */
    int dir, rev; /* the committed turn direction (+1 / -1, 0 none) and the reverse travel since (sixteenths) */
    int speed, fast; /* smoothed angular speed (sixteenths a second); whether it has been above IP_FAST since fast_t0 */
    unsigned lt, fast_t0; /* the time of the last move; the time the speed went above IP_FAST (event times, ms) */
    /* what the screen shows besides the lists, and the signature of it */
    void *art,
        *np_pic; /* the decoded square cover, and the Now Playing picture made from it (ip_tilt: the turned cover and its reflection) */
    void *shadow; /* the menu half's shadow on the pane (IP_SHADOW_W x IP_PANE_H, straight-alpha black), made at open */
    int no_shadow; /* a pass of the split close that must not draw it (the right half moves apart from the menu) */
    int np_valid; /* np_pic holds the current cover's picture */
    int np_face; /* the title style's face: 0 not set yet, 1 the default font, 2 the bold face (ly_title_face) */
    unsigned track; /* the track the cover was made for (a hash), 0 none */
    unsigned fkey; /* the hash of the /tmp cover file it was made from, 0 when it was not */
    int settle;
    int now_shown; /* the main menu has its Now Playing row (something plays or is paused) */
    int np_have, np_gone, np_pos,
        np_len; /* Now Playing: the text of the last track is kept, looks without a track, the last valid position and length ... */
    unsigned np_key; /* ... and the track (ip.track) they belong to */
    char np_text[3][64]; /* title, artist, album of the last track */
    void *
        pend_q; /* a song just started from a list (ip_play): its queue kept, the record and its key, and when; until the player reports it, Now Playing shows it (ip_np_track) */
    void *pend_rec;
    unsigned pend_key, pend_ms;
    void *mode_bmp[5]; /* the play mode marks (ip_mode_bitmap), made on first use */
    unsigned mode_tried; /* bit i: mark i was tried (a failure is not retried) */
    unsigned
        ival; /* the page timer's interval now (IPCF_FRAME_MS, IP_DRIFT_MS or IP_TICK_MS); timer_modify changes it */
    unsigned lookn; /* fast ticks since the last ip_look */
    struct row_art rows[IP_ROW_SLOTS]; /* a pool keyed by (kind, index, id), not by screen position */
    int row_top, row_dir; /* the last top row seen and the direction it moved: prefetch goes that way first */
    unsigned row_clock;
    void *
        row_ph; /* the placeholder at row size, decoded once: a row whose cover is not decoded yet (scrolling) shows it, not a grey block */
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
    unsigned
        pc_wait; /* when a wheel step landed on that row (0: none pending): the picture waits IP_PC_PANE_MS, so a fast turn past it does not flash it */
    unsigned pc_fade,
        pc_t0; /* how far the picture has faded in over the covers (0 the covers .. IP_PC_FADE_MS the picture alone); when the tick last looked */
    unsigned sig[5]; /* the last painted values of the timer's look: battery, play state, track, position, queue */
} ip __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Small helpers
 */
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

static void ip_selection_in(void *canvas, int x, int w, int y, int h) {
    static const unsigned colors[] = {0xe3ab3eu, 0xe0a037u, 0xdc972cu, 0xd68c21u, 0xd38415u};
    static const unsigned char at[] = {0, 25, 50, 75, 100};
    int i;
    for (i = 0; i < h; ++i)
        ip_fill(canvas, x, y + i, w, 1, i == 0 ? 0xf8dd9au : i == h - 1 ? 0x814f15u : ip_stops(colors, at, 5, i, h));
}

static void ip_selection(void *canvas, int w, int y, int h) { ip_selection_in(canvas, 0, w, y, h); }

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

static int ip_is_list(int kind) { return kind != K_MAIN && kind != K_MUSIC && kind != K_NOW && kind != K_SETTINGS; }
static int ip_is_pc(int kind) {
    return kind == K_PODCASTS || kind == K_PC_EPS;
} /* lists of our own (pcmodel), not stock deques */
static int ip_who_albums(int kind) {
    return kind == K_ARTIST_ALBUMS || kind == K_COMPOSER_ALBUMS;
} /* an artist's or a composer's albums */
static int ip_tall(int kind) {
    return kind == K_ALBUMS || ip_who_albums(kind) || kind == K_PLAYLISTS || kind == K_GENRES;
} /* cover rows; song lists are plain text rows */
static int ip_coverless(int kind) {
    return kind == K_PLAYLISTS || kind == K_GENRES;
} /* tall rows with no cover: a name and a count line (the iPod's playlist and genre rows) */
static int ip_two(int kind) { return kind == K_SONGS; } /* two-line text rows: the title over the artist */
static int ip_split(int kind) { return kind == K_MAIN || kind == K_MUSIC || kind == K_SETTINGS; }
static int ip_is_tracks(int kind) {
    return kind == K_SONGS || kind == K_TRACKS || kind == K_CF_TRACKS || kind == K_PL_TRACKS || kind == K_GENRE_SONGS;
}
static struct lvl *ip_top(void) { return &ip.st[ip.depth]; }

/* The main menu's Podcasts row is the selection: the pane shows the podcasts picture, not the covers (the reference's). */
static int ip_pc_row(void) { return ip_top()->kind == K_MAIN && ip_top()->sel == ROOT_PODCASTS; }
/* ... and has been since the last wheel step for IP_PC_PANE_MS (the tick clears pc_wait): the picture is due, and fades in over IP_PC_FADE_MS (out the same way when it is not). */
static int ip_pc_due(void) { return ip_pc_row() && !ip.pc_wait; }
/* The picture alone, the covers still (the fade is over). */
static int ip_pc_pane(void) { return ip_top()->kind == K_MAIN && ip.pc_fade >= IP_PC_FADE_MS; }
static int ip_pc_fading(void) { return ip_top()->kind == K_MAIN && ip.pc_fade != (ip_pc_due() ? IP_PC_FADE_MS : 0u); }

/* What that pane needs, looked once before it is painted (never in paint): the picture, and whether any show has an episode file (once a visit of the main menu). */
static void ip_pc_pane_look(void) {
    if (!ip.win) return;
    if (ip_top()->kind !=
        K_MAIN) { /* a level over the main menu: back on it, the pane is what its row wants at once (no fade on MENU back) */
        ip.pc_wait = 0;
        ip.pc_fade = ip.st[0].kind == K_MAIN && ip.st[0].sel == ROOT_PODCASTS ? IP_PC_FADE_MS : 0;
        return;
    }
    if (!ip_pc_row()) return;
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
    n = strlen(utf8);
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

/* The Now Playing view in front (IPV_*). */
static int ip_np_view(void) { return ip.scrub ? IPV_SCRUB : ip.npv; }

/* The shuffle slider's choice: 0 Off, 1 Songs, 2 Albums. */
static int ip_shuf_kind(void) { return pod_shuffle_kind(); }
static void ip_shuf_set(int kind) {
    ip.th_from = ip_shuf_kind(), ip.th_t0 = time_now_ms() | 1;
    pod_set_shuffle_kind(kind);
}

/* A level change: the wheel starts again, and Now Playing opens on its progress bar (no scrubber, no volume bar). */
static void ip_level_reset(void) {
    ip_wheel_reset();
    ip.scrub = 0, ip.vol_until = 0, ip.sl_t0 = 0, ip.npv = 0, ip.th_t0 = 0, ip.bar_t0 = 0, ip.bar_hold = 0,
    ip.vs_t0 = 0;
}

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
        /* the recent list: every file of the show is in it (a downloaded old episode of an archive show too) */
        all = pc_load_recent(&ip.pc_shows[ip.st[d - 1].sel], &n);
        if (!all) return 0;
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
    if (!ip_who_albums(kind) || !list) return i;
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
        if (l->kind == K_CF) ipcf_order_load(); /* once a visit, before the list: it reads the albums itself */
        if (loadLocalClassList(CLASS_ALBUMS) > 0) cc_drop_unknown_album(*(void **)PDEQ_SHOWLIST);
        if (l->kind == K_CF)
            ipcf_arrange(*(void **)PDEQ_SHOWLIST); /* the shelf in the shared order (patch/ipod_cf.c) */
        break;
    case K_ARTISTS:
        loadLocalClassList(CLASS_ARTISTS);
        break;
    case K_GENRES:
        loadLocalClassList(CLASS_GENRES);
        break;
    case K_COMPOSERS:
        loadLocalClassList(CLASS_COMPOSERS);
        break;
    case K_GENRE_SONGS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(ip.st[d - 1].kind);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        par = deque_at(par, (unsigned)ip.st[d - 1].sel);
        songs_genre_record(cc_str(par, REC_TITLE), I(par, REC_ID) == -1); /* as the stock genre row tap leaves it */
        loadLocalClassList(CLASS_GENRE_SONGS);
        break;
    case K_SONGS:
        loadLocalClassList(CLASS_ALL_SONGS);
        break;
    case K_PLAYLISTS:
        loadLocalClassList(CLASS_PLAYLISTS);
        break;
    case K_ARTIST_ALBUMS:
    case K_COMPOSER_ALBUMS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(ip.st[d - 1].kind);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        loadAlbumList(l->kind == K_COMPOSER_ALBUMS ? CLASS_COMPOSERS : CLASS_ARTISTS,
                      deque_at(par, (unsigned)ip.st[d - 1].sel));
        break;
    case K_TRACKS:
    case K_CF_TRACKS:
        if (d < 1 || !ip_run(d - 1)) return 0;
        par = ip_stock_list(ip.st[d - 1].kind);
        if (!par || (unsigned)ip.st[d - 1].sel >= deque_size(par)) return 0;
        if (ip.st[d - 1].kind == K_ARTISTS ||
            ip.st[d - 1].kind ==
                K_COMPOSERS) { /* an artist with one album: its songs, the album list skipped (loadAlbumList, then the album's own record) */
            unsigned k, n;
            void *alb = (void *)0;
            loadAlbumList(ip.st[d - 1].kind == K_COMPOSERS ? CLASS_COMPOSERS : CLASS_ARTISTS,
                          deque_at(par, (unsigned)ip.st[d - 1].sel));
            par = *(void **)PDEQ_SHOWLIST;
            n = par ? deque_size(par) : 0;
            for (k = 0; k < n && !alb; ++k)
                if (I(deque_at(par, k), REC_ID) != ID_ALL_SONGS) alb = deque_at(par, k);
            if (!alb) return 0;
            loadAlbumdetailList(ip.st[d - 1].kind == K_COMPOSERS ? CLASS_COMPOSER_ALBUMS : CLASS_ARTIST_ALBUMS, alb);
        } else
            loadAlbumdetailList(ip.st[d - 1].kind == K_ALBUMS || ip.st[d - 1].kind == K_CF ? CLASS_ALBUMS
                                : ip.st[d - 1].kind == K_COMPOSER_ALBUMS                   ? CLASS_COMPOSER_ALBUMS
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
        ip.cls = ip_is_tracks(l->kind) ? (l->kind == K_SONGS         ? CLASS_ALL_SONGS
                                          : l->kind == K_PL_TRACKS   ? CLASS_PLAYLIST_SONGS
                                          : l->kind == K_GENRE_SONGS ? CLASS_GENRE_SONGS
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
    if (!m1_is_top(ip.win)) return 0;
    ip_load();
    return ip_valid();
}

static const char *ip_row_text(int kind, int i) {
    void *rec;
    const char *s;
    if (kind == K_MAIN) return TR(MAIN_KEYS[i]);
    if (kind == K_MUSIC) return TR(MUSIC_KEYS[i]);
    if (kind == K_SETTINGS) return TR(SET_KEYS[i]);
    if (kind == K_PODCASTS) return ip.pc_shows[i].title[0] ? ip.pc_shows[i].title : ip.pc_shows[i].dir;
    if (kind == K_PC_EPS) return ip.pc_eps[i].title[0] ? ip.pc_eps[i].title : ip.pc_eps[i].file;
    rec = ip_rec(kind, ip.list, i);
    if (kind == K_ALBUMS || ip_who_albums(kind)) {
        if (I(rec, REC_ID) == ID_ALL_SONGS)
            return TR(ip_who_albums(kind) ? "local_allsong" : "All albums"); /* the stock "All Songs" */
        s = cc_str(rec, REC_ALBUM);
    } else if (kind == K_ARTISTS || kind == K_PLAYLISTS || kind == K_GENRES || kind == K_COMPOSERS)
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

static void ip_pend_drop(void) {
    if (ip.pend_q) deque_destroy(ip.pend_q);
    ip.pend_q = ip.pend_rec = (void *)0, ip.pend_key = 0;
}

/* The track Now Playing is about: the player's, except just after a list started one (ip_play): start_player returns before the player has moved, so for up to IP_NP_PEND_MS
 * the started record stands in, and Now Playing never slides in on the last song only to change under the finger. */
static void *ip_np_track(void) {
    void *t = cc_playing();
    if (!ip.pend_rec) return t;
    if ((t && ip_track_key(t) == ip.pend_key) || time_now_ms() - ip.pend_ms >= IP_NP_PEND_MS) {
        ip_pend_drop();
        return t;
    }
    return ip.pend_rec;
}

/* One pixel of the square cover at (sx, sy) in 1/256 px (pixel centres at whole numbers), bilinear and clamped to the edges. */
static unsigned ip_art_px(const unsigned *src, int sx, int sy) {
    int x0, y0, fx, fy, k;
    unsigned a, b, c, d, out = 0xff000000u;
    sx = sx<0 ? 0 : sx>(IP_ART - 1) << 8 ? (IP_ART - 1) << 8 : sx;
    sy = sy<0 ? 0 : sy>(IP_ART - 1) << 8 ? (IP_ART - 1) << 8 : sy;
    x0 = sx >> 8, y0 = sy >> 8, fx = sx & 255, fy = sy & 255;
    a = src[y0 * IP_ART + x0], b = src[y0 * IP_ART + x0 + (x0 < IP_ART - 1)];
    c = src[(y0 + (y0 < IP_ART - 1)) * IP_ART + x0],
    d = src[(y0 + (y0 < IP_ART - 1)) * IP_ART + x0 + (x0 < IP_ART - 1)];
    for (k = 0; k < 24; k += 8) {
        int top = (int)(a >> k & 255) * (256 - fx) + (int)(b >> k & 255) * fx,
            bot = (int)(c >> k & 255) * (256 - fx) + (int)(d >> k & 255) * fx;
        out |= (unsigned)((top * (256 - fy) + bot * fy) >> 16) << k;
    }
    return out;
}

/* p mixed over q by f / 256 (opaque). */
static unsigned ip_mix256(unsigned q, unsigned p, int f) {
    unsigned k, c = 0xff000000u;
    for (k = 0; k < 24; k += 8) {
        int b = (int)(q >> k & 255);
        c |= (unsigned)(b + (((int)(p >> k & 255) - b) * f >> 8)) << k;
    }
    return c;
}

/* The Now Playing picture, made once when the cover (or the appearance) changes; paint only copies it. The square cover turned as on the iPod classic: the near (left) edge
 * IP_NP_ART_W px tall, the far (right) edge IP_NP_ART_HR, both centred on the same line, every column's height linear in x and its source column the perspective one (the far
 * half is narrower). Under it the IP_NP_REFLECT row reflection, a mirror of the cover's last rows from 30 % opaque fading out, shorter towards the far edge. Mixed into the
 * screen colour (an opaque IP_NP_ART_W x (IP_NP_ART_W + IP_NP_REFLECT) bitmap), the top and bottom edges anti-aliased. */
__attribute__((noinline)) void ip_tilt(const unsigned *src, unsigned *dst) {
    unsigned bg = ip_theme_colors()->bg;
    int x, y, w = IP_NP_ART_W, hl = IP_NP_ART_W << 8, hr = IP_NP_ART_HR << 8;
    for (x = 0; x < w; ++x) {
        int t = ((2 * x + 1) << 11) / w; /* the screen column's centre, 1/4096 of the width */
        int u = (int)(((unsigned)t * IP_NP_ART_HR << 12) /
                      (unsigned)(IP_NP_ART_W * 4096 -
                                 (IP_NP_ART_W - IP_NP_ART_HR) * t)); /* its place on the cover, 1/4096 */
        int h = hl - (int)(((hl - hr) * t) >> 12), top = (hl - h) / 2, bot = top + h,
            rl = IP_NP_REFLECT * h / IP_NP_ART_W; /* 1/256 px */
        int sx = (u * IP_ART >> 4) - 128;
        for (y = 0; y < IP_NP_ART_W + IP_NP_REFLECT; ++y) {
            int py = (y << 8) + 128, lo = y << 8 > top ? y << 8 : top, hi = (y + 1) << 8 < bot ? (y + 1) << 8 : bot,
                cov = hi > lo ? hi - lo : 0, d = py - bot;
            unsigned c = bg | 0xff000000u;
            if (d < 0) d = 0;
            if (cov < 256 && (y + 1) << 8 > bot && d < rl)
                c = ip_mix256(bg, ip_art_px(src, sx, (int)((unsigned)(h - d) * IP_ART * 256u / (unsigned)h) - 128),
                              77 * (rl - d) / rl);
            if (cov > 0)
                c = ip_mix256(c, ip_art_px(src, sx, (int)((unsigned)(py - top) * IP_ART * 256u / (unsigned)h) - 128),
                              cov);
            dst[y * w + x] = c;
        }
    }
}

/* A server track's cover (ls_rec_cover: the file Now Playing shows, asked for when missing); *server 1 when the track is one, -1 when it is not or there is no track. */
static int ip_server_cover(void *t, char *url, unsigned cap, int *server) {
    *server = 0;
    return t ? ls_rec_cover(t, url, cap, server) : -1;
}

/* The Now Playing cover: a server track's own file (never the library's album of the same name; the placeholder until it lands, the settle ticks look again), else the album's cached cover, else the /tmp one. */
static void ip_cover(void *t, int first) {
    char url[80], tmp[NP_COVER_URL], srv[120];
    const char *file = (const char *)0, *path;
    unsigned album = t && *cc_str(t, REC_ALBUM) ? cc_album_key(t) : 0, *px, i;
    int busy = 0, server, sc = ip_server_cover(t, srv, sizeof srv, &server);
    if (!ip.art) ip.art = bitmap_create_ex(IP_ART, IP_ART, IP_ART * 4, BITMAP_RGBA8888);
    if (!ip.art) return;
    px = (unsigned *)bitmap_lock_buffer_for_write(ip.art);
    if (!px) return;
    if (first) ip.settle = 4;
    ip.fkey = 0;
    if (sc == 1 && (ip.fkey = np_file_key(srv + 7)) != 0) {
        file = srv;
        if (first) ip.settle = 0; /* the server's file is the track's own, and does not change */
    } else if (sc == 0) {
        ip.settle = 4; /* on its way: the placeholder, and the settle ticks look again */
    } else {
        file = !server && album ? cc_url(url, album) : (const char *)0;
        if (file) {
            if (first) ip.settle = 0;
        } else if (t && t == cc_playing() && (path = np_cover_file(&busy)) != (const char *)0 &&
                   !busy) { /* (the /tmp file is the player's track: not yet for a started one, ip_np_track) */
            ip.fkey = np_file_key(path);
            if (ip.fkey) {
                snprintf(tmp, sizeof tmp, "file://%s", path);
                file = tmp;
            }
        }
    }
    if (!file || !cc_decode(ip.win, file, 1, IP_ART, 1, px)) { /* the placeholder, else flat grey */
        for (i = 0; i < IP_ART * IP_ART; ++i) px[i] = ART_GREY;
        cc_decode(ip.win, "ipod_placeholder", 0, IP_ART, 1, px);
    }
    ip.np_valid = 0;
    if (!ip.np_pic)
        ip.np_pic = bitmap_create_ex(IP_NP_ART_W, IP_NP_ART_W + IP_NP_REFLECT, IP_NP_ART_W * 4, BITMAP_RGBA8888);
    if (ip.np_pic) {
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ip.np_pic);
        if (d && bitmap_get_line_length(ip.np_pic) == IP_NP_ART_W * 4) {
            ip_tilt(px, d);
            ip.np_valid = 1;
        }
        if (d) bitmap_unlock_buffer(ip.np_pic);
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

/* A genre's artists (group "songer") or albums (group "album"): the groups of the stock genre query's songs (`style like '<name cut to 127 bytes>'`, as the stock row tap
 * lists them; Unknown Genre: no tag), counted by the hooked toolsQueryDbTable into the tools deque (the shown genre list is not touched), so the Library filter applies and
 * an album list is grouped as the Albums page groups it. 0 when the query fails. */
static unsigned ip_genre_count(const char *name, int unknown, const char *group) {
    static const char head[] = "select * from songtable where ";
    char sql[400], *o = sql;
    const char *p;
    void *dq = (void *)0;
    unsigned n = 0;
    memcpy(o, head, sizeof head - 1), o += sizeof head - 1;
    if (unknown) {
        memcpy(o, "ifnull(style,'')=''", 19), o += 19;
    } else {
        memcpy(o, "style like '", 12), o += 12;
        for (p = name; *p && p - name < CLASSINFO_GENRE_SIZE - 1; ++p) {
            if (*p == '\'') *o++ = '\'';
            *o++ = *p;
        }
        *o++ = '\'';
    }
    snprintf(o, (unsigned)(sql + sizeof sql - o), " group by %s COLLATE NOCASE", group);
    if (toolsQueryDbTable(STOCK_DB_PATH, sql, STOCK_SONG_ROW, 0) >= 0) dq = *(void **)PDEQ_TOOLS_TMP;
    if (dq) n = deque_size(dq), deque_clear(dq);
    return n;
}

/* A genre row's identity: its name's FNV-1a hash (the stock genre records carry no stable id). */
static unsigned ip_name_key(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h;
}

static void ip_row_prepare(struct row_art *a, int kind, int index, unsigned id, void *rec) {
    ip_row_reset(a);
    a->kind = kind, a->index = index, a->id = id;
    if (kind == K_PLAYLISTS) {
        void *songs;
        *(int *)(CLASSINFO + CLASSINFO_ARG) = I(rec, REC_DISC);
        loadLocalClassList(CLASS_PLAYLIST_SONGS);
        songs = *(void **)PDEQ_SHOWLIST;
        a->songs = songs ? deque_size(songs) : 0; /* the iPod's playlist row: no cover, the song count under the name */
        a->parts = a->drawn = 1;
        /* PDEQ_PLAYLIST remains the foreground list. No borrowed song pointer survives. */
        return;
    } else if (kind == K_GENRES) { /* the iPod's genre row: no cover, its artists and albums under the name */
        const char *name = cc_str(rec, REC_TITLE);
        int unknown = I(rec, REC_ID) == -1;
        a->songs = ip_genre_count(name, unknown, "songer");
        a->albums = ip_genre_count(name, unknown, "album");
        a->parts = a->drawn = 1;
        return;
    } else if (I(rec, REC_ID) != ID_ALL_SONGS)
        ip_row_source(a, rec);
    if (!a->parts) a->parts = 1;
}

/* Decode one visible part per tick. Paint only copies these bounded, page-owned bitmaps. */
static int ip_row_decode(struct row_art *a, unsigned part) {
    char url[80], path[80];
    const char *file = a->key[part] ? cc_url(url, a->key[part]) : (const char *)0;
    unsigned *px, j;
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
    /* no cached cover (not made yet, or the album has no art): the placeholder, as Cover Flow's, never a grey block */
    if (!(file && cc_decode(ip.win, file, 1, IP_ROW_ART, 1, px)) &&
        !cc_decode(ip.win, "ipod_placeholder", 0, IP_ROW_ART, 1, px))
        for (j = 0; j < IP_ROW_ART * IP_ROW_ART; ++j) px[j] = 0xff4a4a4au;
    bitmap_unlock_buffer(a->bmp);
    a->drawn |= 1u << part;
    if (missing && a->path[part])
        a->waiting |= 1u << part;
    else
        a->waiting &= ~(1u << part);
    return 1;
}

static unsigned ip_row_id(int kind, int index) {
    void *rec = ip_rec(kind, ip.list, index);
    return kind == K_PLAYLISTS ? (unsigned)I(rec, REC_DISC)
           : kind == K_GENRES  ? ip_name_key(cc_str(rec, REC_TITLE))
                               : cc_album_key(rec);
}

static struct row_art *ip_row_find(int kind, int index, unsigned id) {
    int i;
    for (i = 0; i < IP_ROW_SLOTS; ++i)
        if (ip.rows[i].parts && ip.rows[i].kind == kind && ip.rows[i].index == index && ip.rows[i].id == id)
            return &ip.rows[i];
    return (struct row_art *)0;
}

/* The k-th row of the wanted order: the visible rows, then IP_ROW_AHEAD rows beyond them in the scroll direction, then the other side. */
static int ip_row_wanted(int k) {
    int top = ip_top()->top, dir = ip.row_dir < 0 ? -1 : 1, idx;
    if (k < IP_TALL_ROWS)
        idx = top + k;
    else if (k < IP_TALL_ROWS + IP_ROW_AHEAD)
        idx = dir > 0 ? top + IP_TALL_ROWS + (k - IP_TALL_ROWS) : top - 1 - (k - IP_TALL_ROWS);
    else
        idx = dir > 0 ? top - 1 - (k - IP_TALL_ROWS - IP_ROW_AHEAD)
                      : top + IP_TALL_ROWS + (k - IP_TALL_ROWS - IP_ROW_AHEAD);
    return idx < (int)ip.count ? idx : -1;
}

#define IP_ROW_WANTED (IP_TALL_ROWS + 2 * IP_ROW_AHEAD)

static int ip_row_incomplete(struct row_art *a) { return !a || a->drawn != (1u << a->parts) - 1; }

static int ip_rows_more(void) {
    int k, kind = ip_top()->kind;
    if (!ip_tall(kind)) return 0;
    for (k = 0; k < IP_ROW_WANTED; ++k) {
        int idx = ip_row_wanted(k);
        if (idx >= 0 && ip_row_incomplete(ip_row_find(kind, idx, ip_row_id(kind, idx)))) return 1;
    }
    return 0;
}

static void ip_rows_build(void) {
    int i, n = (int)ip.count - ip_top()->top, kind = ip_top()->kind;
    unsigned j;
    struct row_art *a[IP_TALL_ROWS];
    if (n > IP_TALL_ROWS) n = IP_TALL_ROWS;
    if (ip.row_worker || cc_build_busy() || !m1_card_mounted()) return;
    for (i = 0; i < n; ++i) a[i] = ip_row_find(kind, ip_top()->top + i, ip_row_id(kind, ip_top()->top + i));
    for (i = 0; i < n; ++i)
        if (a[i] && a[i]->waiting) break;
    if (i == n || !cc_build_open(16, CC_MISSING)) return;
    ip.row_worker = 1;
    for (i = 0; i < n; ++i)
        if (a[i])
            for (j = 0; j < a[i]->parts; ++j)
                if (a[i]->waiting & (1u << j)) cc_build_add(a[i]->path[j], a[i]->key[j]);
    if (!cc_build_start()) ip.row_worker = 0;
}

/* One row's work for this tick: a new row takes the least recently wanted slot and decodes its first part at once; a known one decodes its next part. */
static int ip_row_step(int kind, int index) {
    unsigned id = ip_row_id(kind, index), j;
    struct row_art *a = ip_row_find(kind, index, id);
    if (!a) {
        int i, best = -1;
        for (i = 0; i < IP_ROW_SLOTS; ++i) {
            if (ip.rows[i].last == ip.row_clock && ip.rows[i].parts) continue;
            if (best < 0 || (!ip.rows[i].parts && ip.rows[best].parts) ||
                (!ip.rows[i].parts == !ip.rows[best].parts && (int)(ip.rows[i].last - ip.rows[best].last) < 0))
                best = i;
        }
        if (best < 0) return 0;
        a = &ip.rows[best];
        ip_row_prepare(a, kind, index, id, ip_rec(kind, ip.list, index));
        a->last = ip.row_clock;
        if (!ip_coverless(kind)) ip_row_decode(a, 0);
        return 1;
    }
    for (j = 0; j < a->parts; ++j) {
        char path[80];
        if (!(a->drawn & (1u << j)) ||
            ((a->waiting & (1u << j)) && cc_file_size(cc_path(path, sizeof path, a->key[j], "")) >= 0)) {
            ip_row_decode(a, j);
            return 1;
        }
    }
    return 0;
}

static int ip_rows_tick(void) {
    int k, kind = ip_top()->kind, top = ip_top()->top, changed = 0;
    unsigned j;
    if (!m1_is_top(ip.win)) return 0;
    if (ip.row_worker && cc_build_done() >= cc_build_total()) ip_rows_stop();
    if (!ip_tall(kind) || !ip_valid()) {
        ip_rows_stop();
        return 0;
    }
    if (!ip_coverless(kind) && !ip.row_ph && /* the placeholder is for covers; playlist and genre rows have none */
        (ip.row_ph = bitmap_create_ex(IP_ROW_ART, IP_ROW_ART, IP_ROW_ART * 4, BITMAP_RGBA8888)) != (void *)0) {
        unsigned *px = (unsigned *)bitmap_lock_buffer_for_write(ip.row_ph);
        if (px) {
            if (!cc_decode(ip.win, "ipod_placeholder", 0, IP_ROW_ART, 1, px)) /* no placeholder: grey, made once */
                for (j = 0; j < IP_ROW_ART * IP_ROW_ART; ++j) px[j] = 0xff4a4a4au;
            bitmap_unlock_buffer(ip.row_ph);
        }
        return 1;
    }
    if (top != ip.row_top) ip.row_dir = top > ip.row_top ? 1 : -1;
    ip.row_top = top;
    ++ip.row_clock;
    for (k = 0; k < IP_ROW_WANTED; ++k) { /* the rows wanted now keep their slots */
        int idx = ip_row_wanted(k);
        struct row_art *a = idx < 0 ? (struct row_art *)0 : ip_row_find(kind, idx, ip_row_id(kind, idx));
        if (a) a->last = ip.row_clock;
    }
    for (k = 0; k < IP_ROW_WANTED; ++k) {
        int idx = ip_row_wanted(k);
        if (idx >= 0 && ip_row_step(kind, idx)) {
            changed = k < IP_TALL_ROWS;
            ip_rows_build();
            return changed;
        }
    }
    ip_rows_build();
    return 0;
}

static void ip_rows_free(void) {
    int i;
    ip_rows_stop();
    for (i = 0; i < IP_ROW_SLOTS; ++i) {
        ip_row_reset(&ip.rows[i]);
        if (ip.rows[i].bmp) bitmap_destroy(ip.rows[i].bmp);
        ip.rows[i].bmp = (void *)0;
    }
    if (ip.row_ph) bitmap_destroy(ip.row_ph);
    ip.row_ph = (void *)0;
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
    unsigned n, t, key, j;
    int got = 0;
    cc_drop_unknown_album(list);
    n = list ? deque_size(list) : 0;
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
    unsigned k = t && *cc_str(t, REC_ALBUM) && !ls_rec_server(t)
                     ? cc_album_key(t)
                     : 0; /* (a server track never takes the library's album of its name: the rotation shows) */
    if (k != ip.pane.pk) ip.pane.pk = k, ip.pane.pk_art = k && cc_url(url, k);
    if (!ip.pane.picked)
        ip.pane.rot_n = ip_pane_pick(ip.pane.rot, ip.pane.rot_trk), ip.pane.rot_i = 0, ip.pane.picked = 1;
    return ip.pane.pk_art && ip.pane.pk != ip.pane.bad ? ip.pane.pk : 0;
}

/* The pan of slot s in 1/256 px: a linear sweep of IP_PANE_R px across the cover's margin in IP_PANE_PAN_MS (the reference's 7.5 s), every other cover the other way; the
 * placeholder stands still. The frame is built at this fraction (ip_pane_frame), so the drift moves a little each frame and never in whole-pixel jumps. */
static int ip_pane_still(int s) { return ip.pane.key[s] && ip.pane.pk_art && ip.pane.key[s] == ip.pane.pk; }

static int ip_pane_pos(int s) {
    unsigned t, pos;
    if (!ip.pane.key[s]) return IP_PANE_R * 128;
    if (ip_pane_still(
            s)) { /* the playing album's cover: half the margin to the centre while it fades in, easing out, then still */
        t = IP_PANE_FADE_MS - (ip.pane.ms[s] < IP_PANE_FADE_MS ? ip.pane.ms[s] : IP_PANE_FADE_MS);
        pos = IP_PANE_R * 64 * t / IP_PANE_FADE_MS * t / IP_PANE_FADE_MS;
        return (int)(ip.pane.rev[s] ? IP_PANE_R * 128 + pos : IP_PANE_R * 128 - pos);
    }
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
    if (!*track || ip.row_worker || cc_build_busy() || !m1_card_mounted() || !m1_screen_lit()) return 0;
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
    char url[NP_COVER_URL];
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

/* The fades' smoothstep: ms of total as 0 .. 255. */
static unsigned ip_ease(unsigned ms, unsigned total) {
    unsigned p = ms * 1024 / total;
    if (p > 1023) p = 1023;
    return ((p * p / 1024) * (3072 - 2 * p) / 1024) * 256 / 1024;
}

/* One pane frame, built on the timer into the page's own IP_PANE_W x IP_PANE_H bitmap (paint only copies it): each row of the cover's window at the pan's place in 1/256 px,
 * every pixel the linear mix of its source column and the next by the fraction (so the picture moves smoothly instead of a pixel at a time); during a cross-fade both covers
 * are built at their own fractions and mixed by the eased fade in the same pass. One pass over 160 x 240 pixels (two interpolations and a mix while fading). */
static void ip_pane_frame(void) {
    const unsigned *a, *b = (const unsigned *)0;
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    const unsigned char *pc = (const unsigned char *)0;
    unsigned *d, al = 0, x, y, fa, fb, format = 0, line = 0, pal = 0;
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
    if (ip.pane.fading) al = ip_ease(ip.pane.fade_ms, IP_PANE_FADE_MS);
    if (ip_top()->kind == K_MAIN && ip.pc_fade &&
        ip.pc_img_ok) { /* the Podcasts picture fading in or out over the covers: its own pane-sized bitmap, read in place */
        format = (unsigned)(*(unsigned short *)((char *)ip.pc_img + BITMAP_FORMAT)) - 1u;
        if (format < 4 && ip.pc_img[0] == IP_PANE_W && ip.pc_img[1] == IP_PANE_H)
            pc = (const unsigned char *)bitmap_lock_buffer_for_read(ip.pc_img),
            line = bitmap_get_line_length(ip.pc_img), pal = ip_ease(ip.pc_fade, IP_PC_FADE_MS);
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
                if (pc) {
                    const unsigned char *q = pc + y * line + x * 4;
                    u = ip_lerp8(u, q[at[format][0]] | q[at[format][1]] << 8 | (unsigned)q[at[format][2]] << 16, pal);
                }
                row[x] = 0xff000000u | u;
            }
        }
        ip.pane.mix_ok = 1;
    }
    if (a) bitmap_unlock_buffer(ip.pane.bmp[c]);
    if (b) bitmap_unlock_buffer(ip.pane.bmp[o]);
    if (d) bitmap_unlock_buffer(ip.pane.mix);
    if (pc) bitmap_unlock_buffer(ip.pc_img);
}

/* One tick (the page is in front and a split page is the level). The reference's artwork pane: a cover pans for IP_PANE_PAN_MS; every IP_PANE_HOLD_MS the next one fades in over
 * IP_PANE_FADE_MS while both pan. The next cover is decoded in the other slot IP_PANE_NEXT_MS in, a tick of its own, never during the fade. The playing album's cached cover
 * replaces the rotation (it fades in at once, gliding half the margin to the centre, and stays there still). Whether the pane changed. */

/* Slot s' pan phase on by step ms; the playing album's stops once it has settled (ip_pane_pos). */
static void ip_pane_age(int s, unsigned step) {
    ip.pane.ms[s] = (ip.pane.ms[s] + step) % (2 * IP_PANE_PAN_MS);
    if (ip_pane_still(s) && ip.pane.ms[s] > IP_PANE_FADE_MS) ip.pane.ms[s] = IP_PANE_FADE_MS;
}

static int ip_pane_advance(void) {
    unsigned want, now, step;
    int c = ip.pane.cur, o = !c;
    if (!ip_split(ip_top()->kind) || !m1_is_top(ip.win)) return 0;
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
    ip_pane_age(c, step);
    ip.pane.cycle += step;
    if (ip.pane.fading) {
        ip_pane_age(o, step);
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

/* The tick's Podcasts picture: the wait after a wheel step ends, then the picture fades in (or out, off the row) over IP_PC_FADE_MS; at once when there is no frame to blend
 * it into. 1: the pane needs painting (the frame is built again: ip_pane_step). */
static int ip_pc_step(void) {
    unsigned now = time_now_ms(), step = now - ip.pc_t0, want;
    ip.pc_t0 = now;
    if (ip.pc_wait && (!ip_pc_row() || now - ip.pc_wait >= IP_PC_PANE_MS)) ip.pc_wait = 0;
    if (!ip_pc_fading()) return 0;
    want = ip_pc_due() ? IP_PC_FADE_MS : 0;
    if (step > IP_FADE_TICK_MS) step = IP_FADE_TICK_MS; /* (the first step after a long interval) */
    if (ip.pane.mix_bad || !ip.pane.have[ip.pane.cur] || !m1_is_top(ip.win)) step = IP_PC_FADE_MS;
    ip.pc_fade =
        want ? (ip.pc_fade + step < want ? ip.pc_fade + step : want) : (ip.pc_fade > step ? ip.pc_fade - step : 0);
    ip.pane.mix_ok = 0;
    return 1;
}

/* The tick's pane work: the state machine above, then the frame when something moved. 1: the pane's rectangle needs painting. */
static int ip_pane_step(void) {
    int changed, pos;
    if (!ip_split(ip_top()->kind) || !m1_is_top(ip.win) || ip_pc_pane())
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
    if (ip.fg && !m1_screen_lit())
        return POD_DARK_MS; /* the screen is off: no visual work (the idle-power rule of the other pages) */
    if (ip.fg && m1_is_top(ip.win) && ip_render_active()) return IPCF_FRAME_MS;
    if (ip.fg && ip.touch == R_RING && ip.menu_zone && !ip.long_done && ip.depth > 0)
        return IP_DRIFT_MS; /* watching for the long press of MENU */
    if (ip.fg && ip.touch == R_RING && ip.side && !ip.turned && ip_top()->kind == K_NOW)
        return IP_DRIFT_MS; /* watching for the hold of previous / next (scan) */
    if (ip.fg && (ip.bar_hold || ip.bar_t0)) return IPCF_FRAME_MS; /* the title bar waits for a slide, then drops in */
    if (ip.fg && (ip.sl_t0 || ip.th_t0 || ip.vs_t0) && ip_top()->kind == K_NOW)
        return IPCF_FRAME_MS; /* a view slides in or out, the shuffle thumb glides */
    if (ip.fg && (ip.scrub || ip.npv == IPV_SHUFFLE) && ip_top()->kind == K_NOW)
        return IP_DRIFT_MS; /* the scrubber's and the shuffle slider's idle end */
    if (ip.fg && m1_is_top(ip.win) && ip_rows_more()) return IPCF_FRAME_MS;
    if (ip.fg && m1_is_top(ip.win) && ip.row_worker) return IP_DRIFT_MS;
    if (ip.fg && ipcf_going()) return IPCF_FRAME_MS; /* the cover going to Now Playing or back */
    if (ip.fg && (ip_top()->kind == K_CF || ip_top()->kind == K_CF_TRACKS) && ipcf_busy()) return IPCF_FRAME_MS;
    if (ip.fg && (ip.pc_wait || ip_pc_fading())) return IP_FADE_TICK_MS; /* the Podcasts picture is due, or fades */
    if (ip_pc_pane()) return IP_TICK_MS; /* the Podcasts picture: nothing moves */
    if (ip_split(ip_top()->kind) && ip.fg && ip.pane.fading && m1_is_top(ip.win)) return IP_FADE_TICK_MS;
    return ip_split(ip_top()->kind) && ip.fg &&
                   (!ip.pane.have[ip.pane.cur] || ip.pane.key[ip.pane.cur] || ip.pane.rot_n) && m1_is_top(ip.win) &&
                   !(ip_pane_still(ip.pane.cur) && ip.pane.ms[ip.pane.cur] >= IP_PANE_FADE_MS)
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
    void *t = ip_np_track(), *q = *(void **)PLAY_QUEUE;
    sig[0] = (unsigned)(ip_battery(&charging) + 1) | (unsigned)charging << 8;
    sig[1] = (unsigned)mclGetPlayStatus();
    sig[2] = t ? ip_track_key(t) : 0;
    ip.np_gone = t ? 0 : ip.np_gone + 1;
    if (!t && ip.np_gone == IP_NP_GONE && ip.np_have)
        ip.np_have = 0, changed = 1; /* the player really has no track: Now Playing says so */
    sig[3] = 0;
    if (ip_now_shown() !=
        ip.now_shown) { /* the Now Playing row (the last) came or went: a cursor on it moves up to Shuffle Songs */
        struct lvl *root = &ip.st[0];
        ip.now_shown = ip_now_shown();
        if (root->sel > ROOT_COUNT - !ip.now_shown - 1) root->sel = ROOT_COUNT - !ip.now_shown - 1;
        changed = 1;
    }
    if (ip_top()->kind == K_NOW && t && get_playtimeandlength(&pos, &len) == 1)
        sig[3] = (unsigned)(pos + 1) * 4099u ^ (unsigned)len;
    sig[4] = (q ? deque_size(q) : 0) ^ ((unsigned)pod_play_mode() << 24);
    if (sig[2] != ip.track &&
        (t || !ip.np_have)) { /* (no track for a moment, the last one still shown: its cover stays, not the disc) */
        ip.track = sig[2];
        ip.scan = ip.sc_hold = ip.scrub = 0; /* a scan, the scrubber or a held target belongs to the old track */
        ip.ly_top = 0;
        if (ip.npv == IPV_LYRICS && !ip_lyr_load()) ip.npv = 0; /* the lyrics view shows the new track's, or goes */
        ip_cover(t, 1);
        changed = 1;
    } else if (
        ip.settle > 0 && t &&
        t ==
            cc_playing()) { /* demo writes the /tmp cover a little after the track changes (once the player is on it) */
        int busy = 0, server, sc;
        char srv[120];
        const char *path;
        unsigned k;
        sc = ip_server_cover(t, srv, sizeof srv, &server);
        if (sc == 1) { /* the server's cover landed: shown once */
            ip.settle = 0;
            k = np_file_key(srv + 7);
            if (k && k != ip.fkey) ip_cover(t, 0), changed = 1;
        } else if (sc != 0) { /* (0: on its way, nothing is counted off) */
            path = np_cover_file(&busy);
            if (!busy) {
                ip.settle--;
                k = path ? np_file_key(path) : 0;
                if (k && k != ip.fkey) ip_cover(t, 0), changed = 1;
            }
        }
    }
    if (ip.sc_hold) { /* the seek's target stays until the player's time is within a second of it (or it ran out, or Now Playing is not shown) */
        int d = pos - ip.sc_pos;
        if (ip_top()->kind != K_NOW || !t || (int)(time_now_ms() - ip.sc_until) >= 0 || (len > 0 && d >= -1 && d <= 1))
            ip.sc_hold = 0, changed = 1;
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
    case K_GENRES:
        return TR("Genres");
    case K_COMPOSERS:
        return TR("Composers");
    case K_SONGS:
        return TR("Songs");
    case K_PLAYLISTS:
        return TR("Playlists");
    case K_PODCASTS:
        return TR("Podcasts");
    case K_NOW:
        return TR("Now Playing");
    case K_CF:
    case K_CF_TRACKS:
        return TR("Cover Flow");
    case K_SETTINGS:
        return TR("cdrippersettings");
    default:
        return "Pod"; /* the page's own name, a brand like the Extras item's label: plain in every language (pod_i18n.BRANDS) */
    }
}

static void ip_paint_bar_at(void *canvas, int kind, int right);

/* The iPod's title bar: the title on the left, no clock; the play state right of it, next to the battery. Entering Now Playing, the whole bar drops in from above the
 * screen (IP_BAR_DROP_MS) once the level slide has shown the page. */
static void ip_paint_bar(void *canvas, int kind) {
    int right = ip_split(kind) ? IP_SPLIT_X : IP_W, drop = 0, ms = (int)(time_now_ms() - ip.bar_t0);
    if (ms < 0) ms = 0; /* (bar_t0 is the start | 1) */
    if (ip.bar_hold) return; /* a full-screen page opening or closing: its picture first, the bar after */
    if (ip.bar_t0 && ms < IP_BAR_DROP_MS)
        drop = IP_BAR_H - (int)ip_ease((unsigned)ms, IP_BAR_DROP_MS) * IP_BAR_H / 255; /* rows still above the screen */
    I(canvas, CANVAS_OY) -= drop;
    ip_paint_bar_at(canvas, kind, right);
    I(canvas, CANVAS_OY) += drop;
}

static void ip_paint_bar_at(void *canvas, int kind, int right) {
    ip_header(canvas, right);
    /* One centre line, y 11.5 (rows 7 .. 16): the glyphs are 10 px from y 7; the text box starts at y 1, because AWTK's metric centring in the 23 px
     * box put the caps 1 px high on the device (shot-0014: caps 6 .. 15). */
    ip_play_glyph(canvas, right - 8 - 27 - 8 - 12, IP_BAR_H / 2 - 7); /* 8 px before the battery, 8 px from the edge */
    ip_battery_glyph(canvas, right - 8 - 27, IP_BAR_H / 2 - 6);
    widget_prepare_text_style(ip.st_title, canvas); /* left, 16 px */
    ip_text(canvas,
            kind == K_NOW && ip_np_view() == IPV_LYRICS && ip.np_have
                ? ip.np_text[0] /* the iPod names the lyrics for the song */
            : ip_top()->title[0] ? ip_top()->title
                                 : ip_title(kind),
            IP_TEXT_X, 1, right - 8 - 27 - 8 - 12 - 6 - IP_TEXT_X, IP_BAR_H - 1);
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
            unsigned wide[64], n = strlen(TR("No Podcasts"));
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
        int skip = ip_render_shadow_skip(); /* while a split slides it fades: its outer columns only */
        src[0] = skip, src[1] = 0, src[2] = IP_SHADOW_W - skip, src[3] = IP_PANE_H;
        dst[0] = IP_PANE_X, dst[2] = IP_SHADOW_W - skip;
        if (skip < IP_SHADOW_W) canvas_draw_image(canvas, ip.shadow, src, dst);
    }
}

/* A text in the canvas' current style, right aligned so that it ends at x2 (a Settings row's value; at most 120 px). Its width. */
static int ip_text_right(void *canvas, const char *utf8, int x2, int y, int h) {
    unsigned wide[64], n = strlen(utf8);
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
    unsigned wide[16], n = strlen(utf8);
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
    if (row == S_SHUFFLE) return TR(mode != MODE_SHUFFLE ? "Off" : pod_shuffle_kind() == 2 ? "Albums" : "Songs");
    if (row == S_REPEAT) return mode == MODE_REPEAT_ONE ? TR("One") : mode == MODE_REPEAT_ALL ? TR("All") : TR("Off");
    if (row == S_APPEARANCE) return TR(ip_theme_dark() ? "Dark" : "Light");
    return (const char *)0;
}

/* Row i's top when `visible` rows share the 220 px under the title bar exactly (integer division); its height is the next top minus this one. */
static int ip_row_y(int i, int visible) { return IP_BAR_H + i * (IP_SCREEN_H - IP_BAR_H) / visible; }

static void ip_paint_list(void *canvas, int kind) {
    struct lvl *l = ip_top();
    void *playing = ip_is_tracks(kind) ? cc_playing() : (void *)0;
    int i, fixed = ip_split(kind), n = ip.list || fixed ? ip_rows() : 0, right = fixed ? IP_SPLIT_X : IP_W, pass, y;
    int tall = ip_tall(kind), two = ip_two(kind), h, visible = tall ? IP_TALL_ROWS : two ? IP_SONG_ROWS : IP_ROWS;
    if (!fixed && !ip_valid()) n = 0; /* a stale list is never read */
    for (pass = 0; pass < 2; ++pass) { /* the unselected rows, then the selected one: one text style at a time */
        widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
        for (i = 0; i < visible && l->top + i < n; ++i) {
            int idx = l->top + i, sel = idx == l->sel, vw = 0, chev = !ip_is_tracks(kind) && kind != K_PC_EPS;
            int art =
                    tall && !ip_coverless(kind), /* a cover at the left; the iPod's playlist and genre rows have none */
                cut = art                ? IP_ROW_ART + 8
                      : kind == K_PC_EPS ? 16
                                         : 0,
                tx = art ? IP_ROW_ART + 8 : IP_TEXT_X + cut;
            const char *val = kind == K_SETTINGS ? ip_set_value(idx) : (const char *)0;
            if (sel != pass) continue;
            y = ip_row_y(i, visible), h = ip_row_y(i + 1, visible) - y;
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
            ip_text(canvas, ip_row_text(kind, idx), tx,
                    y + (tall  ? 4
                         : two ? 2
                               : 0),
                    vw ? right - IP_TEXT_X - IP_TEXT_X - vw - 12 : right - IP_TEXT_X - 22 - cut,
                    tall || two ? IP_ROW_H : h);
            if (two) {
                if (!sel && y + h < IP_SCREEN_H) ip_fill(canvas, 0, y + h - 1, right, 1, ip_theme_colors()->rule);
                widget_prepare_text_style(sel ? ip.st_subsel : ip.st_small, canvas);
                ip_text(canvas, cc_str(deque_at(ip.list, (unsigned)idx), REC_ARTIST), tx, y + IP_SONG_SUB_Y,
                        right - IP_TEXT_X - 22 - cut, 20);
                widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
            }
            if (tall) {
                unsigned identity = ip_row_id(kind, idx);
                struct row_art *a = ip_row_find(kind, idx, identity);
                int src[4] = {0, 0, IP_ROW_ART, IP_ROW_ART}, dst[4] = {0, y, IP_ROW_ART, IP_ROW_ART};
                void *rec = ip_rec(kind, ip.list, idx);
                int line = art ? IP_ROW_ART : 0;
                if (!sel &&
                    y + h < IP_SCREEN_H) /* the iPod's hairline under a row, from the cover's edge to the screen's */
                    ip_fill(canvas, line, y + h - 1, right - line, 1, ip_theme_colors()->rule);
                char sub[256];
                if (art && a && a->bmp && a->drawn)
                    canvas_draw_image(canvas, a->bmp, src, dst);
                else if (art && ip.row_ph)
                    canvas_draw_image(canvas, ip.row_ph, src, dst);
                else if (art)
                    ip_fill(canvas, 0, y, IP_ROW_ART, IP_ROW_ART, ip_theme_colors()->rule);
                if (art)
                    snprintf(sub, sizeof sub, "%s", cc_str(rec, REC_ARTIST));
                else if (a && kind == K_GENRES) { /* the genre's artists and albums once counted; blank until then */
                    char artists[64], albums[64];
                    m1_fmt(artists, sizeof artists, TR(a->songs == 1 ? "%d Artist" : "%d Artists"), (int)a->songs);
                    m1_fmt(albums, sizeof albums, TR(a->albums == 1 ? "%d Album" : "%d Albums"), (int)a->albums);
                    snprintf(sub, sizeof sub, "%s, %s", artists, albums);
                } else if (a) /* the count once the playlist has been read; blank until then */
                    m1_fmt(sub, sizeof sub, TR(a->songs == 1 ? "%d song" : "%d songs"), (int)a->songs);
                else
                    sub[0] = 0;
                widget_prepare_text_style(sel ? ip.st_subsel : ip.st_small, canvas);
                ip_text(canvas, sub, tx, y + 30, right - IP_TEXT_X - 22 - cut, 20);
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
                TR(kind == K_ALBUMS || ip_who_albums(kind) ? "No albums"
                   : kind == K_ARTISTS                     ? "No artists"
                   : kind == K_PLAYLISTS                   ? "No playlists"
                   : ip_is_pc(kind)                        ? "No downloaded episodes"
                                                           : "No songs"),
                IP_TEXT_X, IP_BAR_H, IP_W - 2 * IP_TEXT_X, IP_ROW_H);
    }
}

/* The play mode's mark (stock's one play mode makes shuffle and repeat exclusive): the asset images ipod_mode_shuffle / ipod_mode_repeat / ipod_mode_repeat1 (a heavy white Lucide
 * glyph at 32 px, tools/mod_icons.py). Decoded once on first use, with the box filter down to IP_MODE_PX, into a page-owned bitmap: the glyph is white and the decode is over black, so
 * a pixel's value is its coverage, and the bitmap is that coverage mixed from the screen's colour to the mark's (opaque: the screen is white in both appearances). Paint copies it. */
static void *ip_mode_bitmap(int i) {
    unsigned tmp[IP_SHUF_ICON * IP_SHUF_ICON], *px, k, size = i == 3 ? IP_PLAY_PX : i == 4 ? IP_SHUF_ICON : IP_MODE_PX;
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

static void ip_mode_draw(void *canvas, int mode, int dx) {
    int i = mode == MODE_SHUFFLE      ? 0
            : mode == MODE_REPEAT_ALL ? 1
            : mode == MODE_REPEAT_ONE ? 2
                                      : -1,
        src[4] = {0, 0, IP_MODE_PX, IP_MODE_PX}, dst[4] = {IP_MODE_X + dx, IP_MODE_Y, IP_MODE_PX, IP_MODE_PX};
    void *bmp = i >= 0 ? ip_mode_bitmap(i) : (void *)0;
    if (bmp) canvas_draw_image(canvas, bmp, src, dst);
}

/* One row (i of IP_NP_BAR_H) of the progress bar at screen row y, row by row as Apple's iPod classic screenshot: the fill a light upper half over a saturated lower half
 * with a darker rim (top and bottom rows, the left column, and a dark then a light column where it ends); the empty track a sunken grey with no outline. `alpha` (255
 * opaque) mixes the row into the screen colour, for the reflection under the bar. */
static const unsigned ip_bar_blue[IP_NP_BAR_H] = {
    BGR(0x7e97d7u), BGR(0x87abffu), BGR(0x769efau), BGR(0x6e9cf6u), BGR(0x6c9df4u), BGR(0x6ba1f8u), BGR(0x66a3ffu),
    BGR(0x3d89ebu), BGR(0x3698f9u), BGR(0x33a3ffu), BGR(0x37b0ffu), BGR(0x42b4fdu), BGR(0x5cbbffu), BGR(0x5c9ed0u)};

static const unsigned char ip_bar_grey[IP_NP_BAR_H] = {0xe1, 0xfb, 0xff, 0xfa, 0xf6, 0xf4, 0xf0, 0xe8,
                                                       0xe3, 0xe5, 0xee, 0xf2, 0xed, 0xc5}; /* the empty track's rows */

static void ip_bar_row(void *canvas, int x, int y, int i, int fw, int alpha) {
    unsigned bg = ip_theme_colors()->bg, fill = ip_bar_blue[i], track = ip_bar_grey[i] * 0x010101u;
    unsigned rim = ip_lerp(fill, BGR(0x7a96b8u), 77, 257), glint = ip_lerp(fill, 0xd0d0d0u, 102, 257);
    if (alpha < 255)
        track = ip_lerp(bg, track, alpha, 257), fill = ip_lerp(bg, fill, alpha, 257),
        rim = ip_lerp(bg, rim, alpha, 257), glint = ip_lerp(bg, glint, alpha, 257);
    if (fw > 0) ip_fill(canvas, x, y, fw, 1, fill);
    ip_fill(canvas, x + fw, y, IP_NP_TRACK_W - fw, 1, track);
    if (fw > 0 && i > 0 && i < IP_NP_BAR_H - 1) {
        ip_fill(canvas, x, y, 1, 1, rim);
        if (fw >= 3) ip_fill(canvas, x + fw - 2, y, 1, 1, rim), ip_fill(canvas, x + fw - 1, y, 1, 1, glint);
    }
}

/* The volume the bar shows (0 .. 100): Bluetooth's own word on Bluetooth (headset_output 2), as stock's steps use. */
static int ip_volume(void) {
    int v = *(volatile int *)HEADSET_OUTPUT == 2 ? *(volatile int *)BT_VOLUME : *(volatile int *)G_VOLUME;
    return v < 0 ? 0 : v > 100 ? 100 : v;
}

/* The volume bar's speaker in the text colour, centred on the bar: a 3 x 6 body and a 4 column cone (8 .. 14 rows), IP_SPK_W wide, then `waves` arcs 3 px apart. */
static void ip_speaker(void *canvas, int x, int waves) {
    unsigned c = ip_theme_colors()->fg;
    int y = IP_NP_BAR_Y + IP_NP_BAR_H / 2, i, h;
    ip_fill(canvas, x, y - 3, 3, 6, c);
    for (i = 0; i < 4; ++i) ip_fill(canvas, x + 3 + i, y - 4 - i, 1, 8 + 2 * i, c);
    for (i = 0; i < waves; ++i) { /* a straight middle and its two ends a column in */
        h = 6 + 4 * i;
        ip_fill(canvas, IP_SPK_W + x + 2 + 3 * i, y - h / 2 + 1, 1, h - 2, c);
        ip_fill(canvas, IP_SPK_W + x + 1 + 3 * i, y - h / 2, 1, 1, c);
        ip_fill(canvas, IP_SPK_W + x + 1 + 3 * i, y + h / 2 - 1, 1, 1, c);
    }
}

/* One row of the scrubber's knob at column x, dy rows from the bar's middle: the fill's blue of that bar row (the end rows past the bar take the nearest), its rim colour
 * as the outline; `alpha` mixes it into the screen colour, for the reflection. */
static void ip_diamond_row(void *canvas, int x, int y, int dy, int alpha) {
    int w = IP_NP_KNOB - (dy < 0 ? -dy : dy), i = dy + IP_NP_BAR_H / 2;
    unsigned bg = ip_theme_colors()->bg, fill, rim;
    if (w < 0) return;
    fill = ip_bar_blue[i < 0 ? 0 : i > IP_NP_BAR_H - 1 ? IP_NP_BAR_H - 1 : i];
    rim = ip_lerp(fill, BGR(0x7a96b8u), 77, 257);
    if (alpha < 255) fill = ip_lerp(bg, fill, alpha, 257), rim = ip_lerp(bg, rim, alpha, 257);
    ip_fill(canvas, x - w, y, 2 * w + 1, 1, rim);
    if (w > 1) ip_fill(canvas, x - w + 1, y, 2 * w - 1, 1, fill);
}

/* The scrubber's knob at column x, the iPod's: a diamond IP_NP_KNOB rows each side of the bar's middle in the bar's blue, and its reflection mirrored with the bar's. */
static void ip_diamond(void *canvas, int x) {
    int mid = IP_NP_BAR_Y + IP_NP_BAR_H / 2, dy, k;
    for (dy = -IP_NP_KNOB; dy <= IP_NP_KNOB; ++dy) ip_diamond_row(canvas, x, mid + dy, dy, 255);
    for (k = 0; k < IP_NP_BAR_REFLECT - 1;
         ++k) /* reflection row k mirrors bar row IP_NP_BAR_H - 1 - k, as ip_np_strip's */
        ip_diamond_row(canvas, x, IP_NP_BAR_Y + IP_NP_BAR_H + 1 + k, IP_NP_BAR_H - 1 - k - IP_NP_BAR_H / 2,
                       (IP_NP_BAR_REFLECT - 1 - k) * 56 / (IP_NP_BAR_REFLECT - 1));
}

/* The bar, its reflection and the times dx px across. kind 0: the progress bar filled to pos; 1: the scrubber, an empty track with the diamond on pos (the iPod's);
 * 2: the volume bar, filled to the volume, a quiet speaker before it and a loud one after it, no times. */
static void ip_np_strip(void *canvas, int dx, int kind, int pos, int len) {
    int x = IP_NP_TRACK_X + dx, fw, i;
    char a[12], b[12];
    fw = kind == 2 ? IP_NP_TRACK_W * ip_volume() / 100 : kind || len <= 0 ? 0 : IP_NP_TRACK_W * pos / len;
    for (i = 0; i < IP_NP_BAR_H; ++i) ip_bar_row(canvas, x, IP_NP_BAR_Y + i, i, fw, 255);
    for (i = 0; i < IP_NP_BAR_REFLECT - 1; ++i) /* one clear row, then the mirror from 22 % */
        ip_bar_row(canvas, x, IP_NP_BAR_Y + IP_NP_BAR_H + 1 + i, IP_NP_BAR_H - 1 - i, fw,
                   (IP_NP_BAR_REFLECT - 1 - i) * 56 / (IP_NP_BAR_REFLECT - 1));
    if (kind == 2) {
        ip_speaker(canvas, x - IP_NP_TIME_GAP - IP_SPK_W, 0);
        ip_speaker(canvas, x + IP_NP_TRACK_W + IP_NP_TIME_GAP, 2);
        return;
    }
    if (kind) ip_diamond(canvas, x + (len > 0 ? IP_NP_TRACK_W * pos / len : 0));
    snprintf(a, sizeof a, "%d:%02d", pos / 60, pos % 60);
    snprintf(b, sizeof b, "-%d:%02d", (len - pos) / 60, (len - pos) % 60);
    widget_prepare_text_style(
        ip.st_time,
        canvas); /* 16 px black, hugging the track's ends, the box (y BAR_Y - 1, 22 tall) centring the digits on the bar as on the iPod */
    ip_text_edge(canvas, a, x - IP_NP_TIME_GAP, 0, IP_NP_BAR_Y - 1, 22);
    ip_text_edge(canvas, b, x + IP_NP_TRACK_W + IP_NP_TIME_GAP, 1, IP_NP_BAR_Y - 1, 22);
}

/* The slide between two Now Playing views (the iPod's): the new one comes in from the right edge pushing the old one out to the left, the idle ends too (the iPod
 * slides every view change one way). The eased offset 0 .. IP_W, or -1 when no slide runs (none, done, the view changed again, or the volume bar is up). */
static int ip_np_slide(void) {
    unsigned ms = (int)(time_now_ms() - ip.sl_t0) < 0 ? 0 : time_now_ms() - ip.sl_t0; /* (sl_t0 is the start | 1) */
    if (!ip.sl_t0 || ip.sl_to != ip_np_view() || ip.vol_until || ms >= IP_SCRUB_SLIDE_MS) return -1;
    return (int)(ip_ease(ms, IP_SCRUB_SLIDE_MS) * IP_W / 255);
}

/* The text width of utf8 in the canvas's style (at most 63 characters). */
static int ip_text_w(void *canvas, const char *utf8) {
    unsigned wide[64], n = strlen(utf8);
    if (!n || n > 63) return 0;
    tk_utf8_to_utf16_ex(utf8, n, wide, 64);
    for (n = 0; n < 63 && wide[n];) ++n;
    return n ? (int)(canvas_measure_text(canvas, wide, n) + 0.999f) : 0;
}

/* The shuffle slider dx px across, in the progress bar's place (the iPod's, from the user's nano photos): a large shuffle mark where the elapsed time was, then one rail
 * from IP_SHUF_X, IP_SHUF_W wide (a faint rim with cut corners round a groove, no dividers) with Off, Songs and Albums at the centres of its thirds, and the thumb: a raised panel in the
 * progress bar's gloss (no outline, soft sides) over the chosen third, gliding there in IP_SHUF_THUMB_MS. The names stay put in one left-aligned 16 px style, the chosen one in the selection blue. */
static void ip_shuf_strip(void *canvas, int dx) {
    static const char *const names[3] = {"Off", "Songs", "Albums"};
    int cur = ip_shuf_kind(), y = IP_NP_BAR_Y + IP_NP_BAR_H / 2, slot = IP_SHUF_W / 3, i, r, cx, x0 = IP_SHUF_X + dx,
        top = y - IP_SHUF_H / 2, in, tx, tw = slot;
    unsigned ms = (int)(time_now_ms() - ip.th_t0) < 0 ? 0 : time_now_ms() - ip.th_t0; /* (th_t0 is the start | 1) */
    int src[4] = {0, 0, IP_SHUF_ICON, IP_SHUF_ICON},
        dst[4] = {IP_NP_TRACK_X - IP_NP_TIME_GAP - IP_SHUF_ICON + dx, y - IP_SHUF_ICON / 2, IP_SHUF_ICON, IP_SHUF_ICON};
    void *bmp = ip_mode_bitmap(
        4); /* our own mark drawn at its size (tools/mod_icons.py ipod_shuffle_big), not the 16 px one scaled */
    unsigned bg = ip_theme_colors()->bg, rim = ip_lerp(bg, 0x9a9a9au, 140, 256), face;
    tx = cur * slot; /* the thumb's left, relative to the rail */
    if (ip.th_t0 && ms < IP_SHUF_THUMB_MS && ip.th_from != cur)
        tx = ip.th_from * slot + (cur - ip.th_from) * slot * (int)ip_ease(ms, IP_SHUF_THUMB_MS) / 255;
    if (bmp) canvas_draw_image(canvas, bmp, src, dst);
    for (
        r = 0; r < IP_SHUF_H;
        ++r) { /* the rail: a faint rim, its corners cut two rows deep, a groove (a soft shadow under the top, lighter downwards) */
        in = r == 0 || r == IP_SHUF_H - 1 ? 2 : r == 1 || r == IP_SHUF_H - 2 ? 1 : 0;
        ip_fill(canvas, x0 + in, top + r, IP_SHUF_W - 2 * in, 1, rim);
        if (r && r < IP_SHUF_H - 1)
            ip_fill(canvas, x0 + in + 1, top + r, IP_SHUF_W - 2 * in - 2, 1,
                    r == 1   ? 0xc8c8c8u
                    : r == 2 ? 0xd6d6d6u
                    : r == 3 ? 0xe0e0e0u
                             : ip_lerp(0xe6e6e6u, 0xf2f2f2u, r - 4, IP_SHUF_H - 6));
    }
    for (
        r = 0; r < IP_SHUF_H;
        ++r) { /* the thumb standing out of it, the rail's full height over its rim (the photos: the rim breaks under it) with the same cut corners: no outline, the bar's glossy rows (a bright upper half over a darker lower one), soft sides */
        in = r == 0 || r == IP_SHUF_H - 1 ? 2 : r == 1 || r == IP_SHUF_H - 2 ? 1 : 0;
        i = r * IP_NP_BAR_H /
            IP_SHUF_H; /* the progress bar's gloss, row for row: its track's greys with a little of its fill's blue */
        face = ip_lerp(ip_bar_grey[i] * 0x010101u, ip_bar_blue[i], 24, 256);
        ip_fill(canvas, x0 + tx + in, top + r, tw - 2 * in, 1, ip_lerp(face, BGR(0xa9b1bcu), 128, 256));
        ip_fill(canvas, x0 + tx + in + 1, top + r, tw - 2 * in - 2, 1, face);
    }
    for (i = 0; i < 3; ++i) {
        const char *t = TR(names[i]);
        widget_prepare_text_style(i == cur ? ip.st_shuf : ip.st_np3,
                                  canvas); /* both 14 px left aligned: the same box puts the name in the same place */
        cx = IP_SHUF_X + i * slot + slot / 2 + dx;
        ip_text_edge(canvas, t, cx - ip_text_w(canvas, t) / 2, 1, IP_NP_BAR_Y - 1 - IP_SHUF_TEXT_UP,
                     22); /* the times' box, raised to centre the caps on the rail */
    }
}

/* ---------------------------------------------------------------------------
 * The lyrics view (the iPod's: the track's lyrics as plain text). The .lrc beside the track (stock's file, docs/modules/onlineart.md), read when the view is chosen and on a
 * track change while it is up: [mm:ss.xx] tags dropped, tag lines ([ar:...], [ti:...]) dropped, blank lines kept single, at most IP_LY_BUF - 1 bytes (UTF-8).
 */

/* The lines of text[0 .. n) cut in place: each NUL-terminated, its offset in src. 0 when no line has text. */
static int ip_lyr_parse(struct ip_lyr *L, int n) {
    char *t = L->text, *out = t;
    int i = 0, e, k, c, tags, blank = 1, any = 0;
    L->n_src = 0;
    if (n >= 3 && (unsigned char)t[0] == 0xef && (unsigned char)t[1] == 0xbb && (unsigned char)t[2] == 0xbf) i = 3;
    for (; i < n && L->n_src < IP_LY_SRC; i = e + 1) {
        for (e = i; e < n && t[e] != '\n';) ++e;
        k = e; /* the line is t[i .. k) */
        while (k > i && (t[k - 1] == '\r' || t[k - 1] == ' ' || t[k - 1] == '\t')) --k;
        for (tags = 0;;) { /* the leading time tags; any other tag makes it a tag line */
            while (i < k && (t[i] == ' ' || t[i] == '\t')) ++i;
            if (i >= k || t[i] != '[') break;
            for (c = i + 1; c < k && t[c] != ']';) ++c;
            if (c >= k) break;
            if (t[i + 1] < '0' || t[i + 1] > '9') {
                tags = 1;
                break;
            }
            i = c + 1;
        }
        if (tags || (k <= i && blank)) continue; /* a tag line, or a blank after a blank (or at the start) */
        L->src[L->n_src++] = (unsigned short)(out - t);
        for (c = i; c < k;) *out++ = t[c++]; /* forward in place: out never passes t + i */
        *out++ = 0;
        blank = k <= i;
        any |= k > i;
    }
    while (L->n_src && !L->text[L->src[L->n_src - 1]]) --L->n_src; /* no blank at the end */
    L->laid = 0, L->n_rows = 0;
    return any;
}

/* Reads the playing track's .lrc (or .LRC): 1 when it has a line of text. */
static int ip_lyr_load(void) {
    void *t = cc_playing(), *f;
    const char *path = t ? cc_str(t, REC_PATH) : "";
    char p[IP_LY_PATH];
    int k, dot = -1, n;
    for (k = 0; path[k]; ++k)
        if (path[k] == '.')
            dot = k;
        else if (path[k] == '/')
            dot = -1;
    if (!k || dot < 0) dot = k;
    if (!k || dot + 5 > (int)sizeof p) return 0;
    memcpy(p, path, (unsigned)dot);
    memcpy(p + dot, ".lrc", 5);
    f = fopen(p, "rb");
    if (!f) memcpy(p + dot, ".LRC", 5), f = fopen(p, "rb");
    if (!f) return 0;
    if (!ip.lyr) ip.lyr = (struct ip_lyr *)calloc(1, sizeof *ip.lyr);
    if (!ip.lyr) {
        fclose(f);
        return 0;
    }
    n = (int)fread(ip.lyr->text, 1, IP_LY_BUF - 1, f);
    fclose(f);
    if (n < 0) n = 0;
    if (n == IP_LY_BUF - 1) /* cut: the last, partial line goes (no broken character) */
        while (n > 0 && ip.lyr->text[n - 1] != '\n') --n;
    ip.lyr->text[n] = 0;
    return ip_lyr_parse(ip.lyr, n);
}

/* The code point at s (UTF-8) and its length in bytes (1 for a stray byte). */
static unsigned ip_utf8(const unsigned char *s, int *len) {
    unsigned c = s[0];
    int n = c < 0xc0 ? 1 : c < 0xe0 ? 2 : c < 0xf0 ? 3 : 4, i;
    if (n == 1) {
        *len = 1;
        return c;
    }
    c &= 0x3f >> (n - 1);
    for (i = 1; i < n; ++i) {
        if ((s[i] & 0xc0) != 0x80) {
            *len = 1;
            return s[0];
        }
        c = c << 6 | (s[i] & 0x3f);
    }
    *len = n;
    return c;
}

/* The lines wrapped to IP_LY_W in the canvas's style (the lyrics style): the most characters that fit, back to the last space when there is one. */
static void ip_lyr_layout(void *canvas) {
    struct ip_lyr *L = ip.lyr;
    unsigned wide[IP_LY_WIDE];
    unsigned short at[IP_LY_WIDE + 1];
    int s, n, b, len, i, k, lo, hi, j;
    L->n_rows = 0;
    for (s = 0; s < L->n_src && L->n_rows < IP_LY_ROWS; ++s) {
        const unsigned char *p = (const unsigned char *)L->text + L->src[s];
        for (n = 0, b = 0; p[b] && n < IP_LY_WIDE; ++n)
            at[n] = (unsigned short)b, wide[n] = ip_utf8(p + b, &len), b += len;
        at[n] = (unsigned short)b;
        if (!n) {
            L->row_at[L->n_rows] = L->src[s], L->row_len[L->n_rows++] = 0;
            continue;
        }
        for (i = 0; i < n && L->n_rows < IP_LY_ROWS;) {
            lo = 1, hi = n - i;
            if (hi > 60) hi = 60; /* ip_text draws at most 63 */
            while (lo < hi) {
                k = (lo + hi + 1) / 2;
                if ((int)(canvas_measure_text(canvas, wide + i, (unsigned)k) + 0.999f) <= IP_LY_W)
                    lo = k;
                else
                    hi = k - 1;
            }
            k = lo;
            if (i + k < n) /* back to the last space, the space staying on this row */
                for (j = i + k - 1; j > i; --j)
                    if (wide[j] == ' ') {
                        k = j - i + 1;
                        break;
                    }
            L->row_at[L->n_rows] = (unsigned short)(L->src[s] + at[i]);
            L->row_len[L->n_rows++] = (unsigned char)(at[i + k] - at[i] > 255 ? 255 : at[i + k] - at[i]);
            for (i += k; i < n && wide[i] == ' ';) ++i;
        }
    }
    L->laid = 1;
}

/* The lyrics view's height above the screen's: the scroll's last line (0 when it all fits). */
static int ip_lyr_max(void) {
    int h = IP_LY_ART + IP_LY_GAP + (ip.lyr ? ip.lyr->n_rows : 0) * IP_LY_LINE + IP_LY_GAP / 2,
        room = IP_SCREEN_H - IP_LY_ART_Y;
    return h > room ? (h - room + IP_LY_LINE - 1) / IP_LY_LINE : 0;
}

/* The lyrics view dx px across, scrolled ly_top lines (the whole page scrolls, as the iPod's): a small cover, the album and the artist (bold) beside it, the lines under it
 * left aligned, and a thin scroll bar at the right edge. */
static void ip_lyr_paint(void *canvas, int dx) {
    struct ip_lyr *L = ip.lyr;
    int y0, i, y, src[4], dst[4], max, room, h, ty, th;
    char row[256];
    if (!L) return;
    widget_prepare_text_style(ip.st_np3, canvas);
    if (!L->laid) ip_lyr_layout(canvas);
    max = ip_lyr_max();
    if (ip.ly_top > max) ip.ly_top = max;
    if (ip.ly_top < 0) ip.ly_top = 0;
    y0 = IP_LY_ART_Y - ip.ly_top * IP_LY_LINE;
    if (ip.art) {
        src[0] = 0, src[1] = 0, src[2] = IP_ART, src[3] = IP_ART;
        dst[0] = IP_LY_ART_X + dx, dst[1] = y0, dst[2] = IP_LY_ART, dst[3] = IP_LY_ART;
        canvas_draw_image(canvas, ip.art, src, dst);
    }
    ip_text(canvas, ip.np_text[2], IP_LY_TEXT_X + dx, y0 + IP_LY_ALBUM_DY, IP_W - IP_LY_TEXT_X - 12, 20);
    if (ly_latin(ip.np_text[1]) + 1 != ip.np_face) { /* the artist in the bold face when it is all in it */
        ly_title_face(ip.st_np1, ip.np_text[1]);
        ip.np_face = ly_latin(ip.np_text[1]) + 1;
    }
    widget_prepare_text_style(ip.st_np1, canvas);
    ip_text(canvas, ip.np_text[1], IP_LY_TEXT_X + dx, y0 + IP_LY_ARTIST_DY, IP_W - IP_LY_TEXT_X - 12, 24);
    widget_prepare_text_style(ip.st_np3, canvas);
    for (i = 0; i < L->n_rows; ++i) {
        y = y0 + IP_LY_ART + IP_LY_GAP + i * IP_LY_LINE;
        if (y + IP_LY_LINE <= IP_BAR_H) continue;
        if (y >= IP_SCREEN_H) break;
        if (!L->row_len[i]) continue;
        memcpy(row, L->text + L->row_at[i], L->row_len[i]);
        row[L->row_len[i]] = 0;
        ip_text(canvas, row, IP_LY_X + dx, y, IP_LY_W + 4, IP_LY_LINE);
    }
    if (max > 0) { /* the scroll bar: a faint track, the thumb as long as the screen's share of the page */
        room = IP_SCREEN_H - IP_BAR_H - 4;
        h = room * (IP_SCREEN_H - IP_LY_ART_Y) / (IP_SCREEN_H - IP_LY_ART_Y + max * IP_LY_LINE);
        if (h < 12) h = 12;
        ty = IP_BAR_H + 2 + (room - h) * ip.ly_top / max;
        th = h;
        ip_fill(canvas, IP_W - IP_LY_SB_W - 2 + dx, IP_BAR_H + 2, IP_LY_SB_W, room,
                ip_lerp(ip_theme_colors()->bg, ip_theme_colors()->fg, 24, 256));
        ip_fill(canvas, IP_W - IP_LY_SB_W - 2 + dx, ty, IP_LY_SB_W, th,
                ip_lerp(ip_theme_colors()->bg, ip_theme_colors()->fg, 110, 256));
    }
}

/* The Now Playing page's picture and text dx px across (the cover turned with its reflection, the play mode mark, the text column beside the cover). */
static void ip_np_body(void *canvas, int dx) {
    void *queue = *(void **)PLAY_QUEUE;
    int src[4], dst[4], n;
    char line[48];
    ip_mode_draw(canvas, pod_play_mode(), dx);
    if (ip.np_pic && ip.np_valid) { /* the turned cover and its reflection, made once with the cover: a straight copy */
        src[0] = 0, src[1] = 0, src[2] = IP_NP_ART_W, src[3] = IP_NP_ART_W + IP_NP_REFLECT;
        dst[0] = IP_NP_ART_X + dx, dst[1] = IP_NP_ART_Y, dst[2] = IP_NP_ART_W, dst[3] = IP_NP_ART_W + IP_NP_REFLECT;
        canvas_draw_image(canvas, ip.np_pic, src, dst);
    } else if (ip.art) { /* no picture bitmap: the cover flat, scaled to the near edge */
        src[0] = 0, src[1] = 0, src[2] = IP_ART, src[3] = IP_ART;
        dst[0] = IP_NP_ART_X + dx, dst[1] = IP_NP_ART_Y, dst[2] = IP_NP_ART_W, dst[3] = IP_NP_ART_W;
        canvas_draw_image(canvas, ip.art, src, dst);
    }
    /* The text column beside the cover: the title 18 black (bold when its face has every character), the artist and the album 16 black, the queue place 14 black (IP_NP_*_Y). */
    widget_prepare_text_style(ip.st_np1, canvas);
    ip_text(canvas, ip.np_text[0], IP_NP_TEXT_X + dx, IP_NP_TITLE_Y, IP_W - IP_NP_TEXT_X - 8, 24);
    widget_prepare_text_style(ip.st_np2, canvas);
    ip_text(canvas, ip.np_text[1], IP_NP_TEXT_X + dx, IP_NP_ARTIST_Y, IP_W - IP_NP_TEXT_X - 8, 22);
    ip_text(canvas, ip.np_text[2], IP_NP_TEXT_X + dx, IP_NP_ALBUM_Y, IP_W - IP_NP_TEXT_X - 8, 22);
    if (queue) { /* the place in the queue: "3 / 12" (the translation table allows one %d a text, so no "3 of 12") */
        n = (int)deque_size(queue);
        snprintf(line, sizeof line, "%d / %d", mclGetPlayPos() + 1, n);
        widget_prepare_text_style(ip.st_np3, canvas);
        ip_text(canvas, line, IP_NP_TEXT_X + dx, IP_NP_PLACE_Y, IP_W - IP_NP_TEXT_X - 8, 20);
    }
}

/* One Now Playing view dx px across; body: with the page's picture and text (a slide to or from the lyrics moves the whole page, the others only the bar). */
static void ip_np_view_paint(void *canvas, int dx, int v, int body, int pos, int len) {
    if (v == IPV_LYRICS) {
        ip_lyr_paint(canvas, dx);
        return;
    }
    if (body) ip_np_body(canvas, dx);
    if (v == IPV_SHUFFLE)
        ip_shuf_strip(canvas, dx);
    else
        ip_np_strip(canvas, dx, v == IPV_SCRUB, pos, len);
}

/* Now Playing never blanks while the player changes track: for a moment the player has no current track (cc_playing NULL) or no time (get_playtimeandlength fails or says 0), and
 * a repaint landing then used to drop the text or the whole bar until a later tick. The text of the last track is kept (np_text) for IP_NP_GONE looks without one, the bar is
 * always drawn from the last valid (position, length): on a new track the fill starts empty at 00:00, the length being the last one known (the song record has no duration). */
static void ip_paint_now(void *canvas) {
    void *t = ip_np_track();
    int pos = 0, len = 0, ok, off, full, vs;
    const char *f;
    if (t) {
        f = cc_str(t, REC_TITLE);
        snprintf(ip.np_text[0], sizeof ip.np_text[0], "%s", *f ? f : cc_str(t, REC_NAME));
        snprintf(ip.np_text[1], sizeof ip.np_text[1], "%s", cc_str(t, REC_ARTIST));
        snprintf(ip.np_text[2], sizeof ip.np_text[2], "%s", cc_str(t, REC_ALBUM));
        ip.np_have = 1;
        if (ip_np_view() != IPV_LYRICS &&
            ly_latin(ip.np_text[0]) + 1 !=
                ip.np_face) { /* the title in the bold face when it is all in it, else the default font (a style change only when that flips) */
            ly_title_face(ip.st_np1, ip.np_text[0]);
            ip.np_face = ly_latin(ip.np_text[0]) + 1;
        }
    } else if (!ip.np_have) {
        widget_prepare_text_style(ip.st_np2, canvas);
        ip_text(canvas, TR("Not Playing"), IP_TEXT_X, IP_BAR_H + 80, IP_W - 2 * IP_TEXT_X, 30);
        return;
    }
    ok = t == cc_playing() && get_playtimeandlength(&pos, &len) == 1 &&
         len > 0; /* (a started song not reached yet: the player's time is the last one's) */
    if (ok)
        ip.np_pos = pos, ip.np_len = len, ip.np_key = ip.track;
    else
        len = ip.np_len, pos = ip.np_key == ip.track
                                   ? ip.np_pos
                                   : 0; /* no time now: the last length; the position of this track, else 0 */
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if ((ip.scan || ip.sc_hold || ip.scrub) && len > 0)
        pos = ip.sc_pos > len ? len : ip.sc_pos; /* the scan's target, not the player's time */
    off = ip_np_slide();
    vs = ip.vs_t0 ? (int)(time_now_ms() - ip.vs_t0) : IP_SCRUB_SLIDE_MS;
    vs = vs < 0                   ? 0
         : vs < IP_SCRUB_SLIDE_MS ? (int)ip_ease((unsigned)vs, IP_SCRUB_SLIDE_MS) * IP_W / 255
                                  : -1; /* the volume slide's offset, -1: none */
    if (ip.vol_until) { /* the volume bar, coming in from the right over the progress bar going left */
        ip_np_body(canvas, 0);
        if (vs >= 0 && !ip.vs_back) ip_np_strip(canvas, -vs, 0, pos, len);
        ip_np_strip(canvas, vs >= 0 && !ip.vs_back ? IP_W - vs : 0, 2, pos, len);
    } else if (vs >= 0 && ip.vs_back) { /* and out: it goes right, the progress bar back from the left */
        ip_np_body(canvas, 0);
        ip_np_strip(canvas, vs, 2, pos, len);
        ip_np_strip(canvas, vs - IP_W, 0, pos, len);
    } else if (off < 0)
        ip_np_view_paint(canvas, 0, ip_np_view(), 1, pos, len);
    else {
        full = ip.sl_from == IPV_LYRICS || ip.sl_to == IPV_LYRICS;
        if (!full) ip_np_body(canvas, 0);
        ip_np_view_paint(canvas, -off, ip.sl_from, full, pos, len);
        ip_np_view_paint(canvas, IP_W - off, ip.sl_to, full, pos, len);
    }
}

/* The floating flipped album card over Cover Flow (K_CF_TRACKS): the card alone, filling its rectangle (IPCF_CARD_*), with
 * sky-blue glossy album + artist header (white text), a 1 px edge, seven crisp white track rows (no scrollbar), blue selection
 * bar and playing speaker. ip_cf_face lays the same paint into the picture the 3D flip turns. */
static void ip_paint_card_body(void *canvas) {
    struct lvl *l = ip_top();
    void *playing = cc_playing();
    int n = ip_valid() ? (int)ip.count : 0, pass, i;
    int ly = IPCF_CARD_Y + IPCF_CARD_HDR + 1, lh = IPCF_CARD_H - IPCF_CARD_HDR - 1;
    int ix = IPCF_CARD_X + 1, iw = IPCF_CARD_W - 2;
    const char *alb = ipcf_album(), *art = ipcf_artist();
    ip_fill(canvas, IPCF_CARD_X, IPCF_CARD_Y, IPCF_CARD_W, IPCF_CARD_HDR + 1, 0xb8976bu);
    ip_fill(canvas, IPCF_CARD_X, ly, IPCF_CARD_W, lh, 0xd4cec8u);
    ip_fill(canvas, ix, ly, IPCF_CARD_W - 2, lh, ip_theme_colors()->bg);
    { /* iPod classic sky-blue gloss header gradient */
        static const unsigned hdr_c[] = {0xe4ae5au, 0xebbc6du, 0xf6d196u};
        static const unsigned char hdr_at[] = {0, 45, 100};
        ip_fill(canvas, ix, IPCF_CARD_Y + 1, IPCF_CARD_W - 2, 1, 0xe8bb74u);
        for (i = 2; i < IPCF_CARD_HDR; ++i)
            ip_fill(canvas, ix, IPCF_CARD_Y + i, IPCF_CARD_W - 2, 1,
                    ip_stops(hdr_c, hdr_at, 3, i - 2, IPCF_CARD_HDR - 2));
        ip_fill(canvas, ix, IPCF_CARD_Y + IPCF_CARD_HDR, IPCF_CARD_W - 2, 1, 0xbc9252u);
    }
    widget_prepare_text_style(ly_latin(alb) ? ip.st_selb : ip.st_sel, canvas);
    ip_text(canvas, alb, IPCF_CARD_X + 10, IPCF_CARD_Y + 4, IPCF_CARD_W - 20, 21);
    widget_prepare_text_style(ip.st_subsel, canvas);
    ip_text(canvas, art, IPCF_CARD_X + 10, IPCF_CARD_Y + 24, IPCF_CARD_W - 20, 17);
    for (pass = 0; pass < 2; ++pass) {
        widget_prepare_text_style(pass ? ip.st_sel : ip.st_row, canvas);
        for (i = 0; i < IPCF_CARD_ROWS && l->top + i < n; ++i) {
            int idx = l->top + i, sel = idx == l->sel, y = ly + i * lh / IPCF_CARD_ROWS;
            int h = ly + (i + 1) * lh / IPCF_CARD_ROWS - y, spk = 0;
            if (sel != pass) continue;
            if (sel) ip_selection_in(canvas, ix, iw, y, h);
            if (!sel && playing) {
                void *rec = deque_at(ip.list, (unsigned)idx);
                const char *path = cc_str(rec, REC_PATH);
                if (*path && !strcmp(path, cc_str(playing, REC_PATH)) &&
                    I(rec, REC_CUE_START) == I(playing, REC_CUE_START)) {
                    void *bmp = ip_mode_bitmap(3);
                    int src[4] = {0, 0, IP_PLAY_PX, IP_PLAY_PX},
                        dst[4] = {ix + iw - 6 - IP_PLAY_PX, y + (h - IP_PLAY_PX) / 2, IP_PLAY_PX, IP_PLAY_PX};
                    if (bmp) canvas_draw_image(canvas, bmp, src, dst);
                    spk = IP_PLAY_PX + 6;
                }
            }
            ip_text(canvas, ip_row_text(K_CF_TRACKS, idx), IPCF_CARD_X + 10, y, iw - 18 - spk, h);
        }
    }
    if (n == 0 && ip_valid()) {
        widget_prepare_text_style(ip.st_small, canvas);
        ip_text(canvas, TR("No songs"), IPCF_CARD_X + 10, ly + 8, IPCF_CARD_W - 20, IP_ROW_H);
    }
}

/* The text colour of a card style (ipod_theme.c ip_theme_apply sets the labels'). */
static unsigned ip_card_ink(const void *style) {
    return style == ip.st_row ? ip_theme_colors()->fg : style == ip.st_small ? ip_theme_colors()->sub : 0xffffffu;
}

/* The card's picture for the 3D flip (patch/ipod_cf.c ipcf_face), painted again when what the card shows changes, while it is in
 * front: so the flip opening turns the card with its text, and closing or going to Now Playing turns the card as it was last. */
static void ip_cf_face(void *canvas) {
    static struct {
        void *list, *playing;
        unsigned count;
        int sel, top, valid, dark;
    } k __attribute__((section(".scratch")));
    struct lvl *l = ip_top();
    void *playing = cc_playing();
    int valid = ip_valid();
    unsigned *face = ipcf_face();
    if (!face) return;
    if (ipcf_face_ok() && k.list == ip.list && k.playing == playing && k.count == ip.count && k.sel == l->sel &&
        k.top == l->top && k.valid == valid && k.dark == ip_theme_dark())
        return;
    k.list = ip.list, k.playing = playing, k.count = ip.count, k.sel = l->sel, k.top = l->top, k.valid = valid,
    k.dark = ip_theme_dark();
    ipcf_face_done(ip_render_raster(ip_paint_card_body, canvas, face, IPCF_CARD_X, IPCF_CARD_Y, IPCF_CARD_W,
                                    IPCF_CARD_H, ip_card_ink));
}

/* The card settled over the parted side covers (ipcf_paint_bg). */
static void ip_paint_cf_card(void *canvas) {
    ipcf_paint_bg(canvas);
    ip_paint_card_body(canvas);
}

static void ip_paint_current(void *canvas) {
    int kind = ip_top()->kind;
    ip_fill(canvas, 0, 0, IP_W, IP_SCREEN_H, ip_theme_colors()->bg);
    if (ip_split(kind)) ip_paint_pane(canvas);
    if ((kind == K_CF || kind == K_NOW) && ipcf_going()) /* the cover going to Now Playing or back (patch/ipod_cf.c) */
        ipcf_paint_go(canvas, kind == K_CF && ip_valid() ? ip.list : (void *)0,
                      kind == K_CF && ip_valid() ? ip.count : 0, ip.st_row);
    else if (kind == K_CF)
        ipcf_paint(canvas, ip_valid() ? ip.list : (void *)0, ip_valid() ? ip.count : 0,
                   ip.st_row); /* the covers on white under the bar (patch/ipod_cf.c) */
    else if (kind == K_CF_TRACKS) {
        ip_cf_face(canvas);
        if (ipcf_flipping())
            ipcf_paint_flip(canvas, ip_valid() && ip.count ? ip_top()->sel - ip_top()->top : -1);
        else
            ip_paint_cf_card(canvas);
    } else if (kind == K_NOW)
        ip_paint_now(canvas);
    else
        ip_paint_list(canvas, kind);
    ip_paint_bar(canvas, kind == K_NOW && ipcf_going() ? K_CF : kind); /* Cover Flow's title while its cover goes */
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

/* The menu half's shadow alone, at the menu's right edge moved by menu_dx (over the still pane in a cover transition: the menu's own pass is cut at its edge, because its
 * full-width white fill would whiten the pane's first columns under the shadow). */
static void ip_cover_shadow(void *canvas, const int *saved, int menu_dx) {
    int src[4] = {0, 0, IP_SHADOW_W, IP_PANE_H}, dst[4] = {IP_PANE_X, 0, IP_SHADOW_W, IP_PANE_H};
    if (!ip.shadow) return;
    ip_paint_range(canvas, saved, menu_dx, IP_SPLIT_X + menu_dx, IP_SPLIT_X + menu_dx + IP_SHADOW_W);
    canvas_draw_image(canvas, ip.shadow, src, dst);
}

/* A cover transition (a full-width list from a split menu: Music > Songs): the split page's artwork pane stays still, the list comes in over it from the right and its left edge
 * pushes the menu half out on the left (the menu moves once the list reaches it); closing runs it backwards. page_dx is the full-width page's offset. */
static void ip_paint_cover(void *canvas, const int *saved, int page_dx) {
    int menu_dx = page_dx < IP_SPLIT_X ? page_dx - IP_SPLIT_X : 0;
    if (ip_render_direction() > 0) {
        ip_paint_range(canvas, saved, 0, IP_SPLIT_X, IP_W);
        ip_render_out(canvas, 1); /* the old pane, still (its shadow is the menu's) */
        ip_paint_range(canvas, saved, menu_dx, 0, IP_SPLIT_X + menu_dx);
        ip_render_out(canvas, 0);
        ip_cover_shadow(canvas, saved, menu_dx);
        ip_paint_range(canvas, saved, page_dx, page_dx, IP_W);
        ip_render_begin();
        ip_paint_current(canvas);
        ip_render_end();
    } else {
        ip.no_shadow = 1; /* the shadow belongs to the menu half */
        ip_paint_range(canvas, saved, 0, IP_SPLIT_X, IP_W);
        ip_paint_current(canvas);
        ip.no_shadow = 0;
        ip_paint_range(canvas, saved, menu_dx, 0, IP_SPLIT_X + menu_dx);
        ip_render_begin();
        ip_paint_current(canvas);
        ip_render_end();
        ip_cover_shadow(canvas, saved, menu_dx);
        ip_paint_range(canvas, saved, page_dx, page_dx, IP_W);
        ip_render_out(canvas, 2);
    }
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
    if (ip_render_split() || ip_render_cover()) {
        ip_render_offsets(&old_dx, &new_dx);
        if (ip_render_split())
            ip_paint_split(canvas, saved, old_dx, new_dx);
        else
            ip_paint_cover(canvas, saved, ip_render_direction() > 0 ? new_dx : old_dx);
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
    if (ip_render_active() && ip_render_width() != IP_W)
        ip_paint_bar(
            canvas,
            ip_top()
                ->kind); /* the iPod's title bar stays put over a slide between split menus, already titled for the new level; a full-width
                                        page (Music > Artists) slides in whole, its bar with it */
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Actions
 */

static int ip_fullscreen(int kind) { return kind == K_NOW || kind == K_CF || kind == K_CF_TRACKS; }

/* The slide between two levels: the menu half (IP_SPLIT_X) between split pages; 0, the split, between a split page and a fullscreen one (Now Playing, Cover Flow); -1, the
 * cover, between a split page and a full-width list (Music > Songs); else the whole width. */
static int ip_slide_width(int from, int to) {
    if (ip_split(from) && ip_split(to)) return IP_SPLIT_X;
    if ((ip_split(from) && ip_fullscreen(to)) || (ip_fullscreen(from) && ip_split(to))) return 0;
    if (ip_split(from) != ip_split(to)) return -1;
    return IP_W;
}

/* Into or out of a full-screen page (Now Playing, Cover Flow): its picture comes without the title bar, which drops in from above the screen once the split
 * is over (ip_paint_bar). Over the other slides the bar stays put (split menus) or slides with its page (full-width pages). */
static void ip_bar_wait(int from, int to) {
    if (ip_fullscreen(from) != ip_fullscreen(to)) ip.bar_hold = 1;
}

static void ip_push(int kind) {
    if (ip.depth + 1 >= IP_DEPTH) return;
    ip_render_transition(1, ip_slide_width(ip_top()->kind, kind));
    {
        struct lvl *nl = &ip.st[++ip.depth];
        nl->kind = kind, nl->sel = nl->top = 0, nl->title[0] = 0;
    }
    ip_level_reset();
    ip_bar_wait(ip.st[ip.depth - 1].kind, kind);
    ip_load();
    ip_render_restart(); /* the slide counts from the loaded list, not the press */
    ip_redraw();
    ip_retime(); /* the pace of the new level: Cover Flow's frames, else the pan stops */
}

static void ip_push_flip(int kind) {
    if (ip.depth + 1 >= IP_DEPTH) return;
    ip_render_cancel();
    {
        struct lvl *nl = &ip.st[++ip.depth];
        nl->kind = kind, nl->sel = nl->top = 0, nl->title[0] = 0;
    }
    ip_level_reset();
    ip_load();
    ip_redraw();
    ip_retime();
}

static void ip_pop(void) {
    int from = ip_top()->kind;
    if (ip.depth == 0) {
        ip_render_cancel();
        navigator_back(); /* MENU on the main menu closes the page */
        return;
    }
    if (from == K_NOW && ip.st[ip.depth - 1].kind == K_CF && ipcf_gone()) { /* the cover that went comes back */
        ip_render_cancel();
        ipcf_go_close(0);
        ip.depth--;
        ip_level_reset();
        ip_load();
        ip_redraw();
        ip_retime();
        return;
    }
    if (from == K_CF_TRACKS && ip.st[ip.depth - 1].kind == K_CF) {
        int row = ip.count ? ip_top()->sel - ip_top()->top : -1;
        ip_render_cancel();
        ipcf_flip_close(row);
        ip.depth--;
        ip_level_reset();
        ip_load();
        ip_redraw();
        ip_retime();
        return;
    }
    ip_render_transition(-1, ip_slide_width(from, ip.st[ip.depth - 1].kind));
    if (from == K_CF) ipcf_close(); /* Cover Flow's frame and textures go */
    ip.depth--;
    ip_level_reset();
    ip_bar_wait(from, ip_top()->kind);
    ip_load();
    ip_render_restart(); /* the slide counts from the loaded list, not the press */
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
    d = ip_top()->kind;
    ip.depth = 0;
    ip_level_reset();
    ip_bar_wait(d, K_MAIN);
    ip_load();
    ip_render_restart(); /* the slide counts from the loaded list, not the press */
    ip_pane_reset();
    ip_redraw();
    ip_retime();
}

/* A step of the wheel: the cursor moves `rows` rows (no wrap, as the iPod; clamped at the ends, and a step that wanted to go past an end nudges the rows), the
 * window follows it. */
static void ip_np_turn(int dir, int rows);
static void ip_np_select(void);

static void ip_step(int dir, int rows) {
    struct lvl *l = ip_top();
    if (ip_render_active()) ip_render_cancel();
    int n, want;
    if (l->kind == K_NOW) { /* the volume, or the scrubber's target */
        ip_np_turn(dir, rows);
        return;
    }
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
    ip.pc_wait = ip_pc_row() ? time_now_ms() | 1 : 0;
    if (l->sel < l->top) l->top = l->sel;
    {
        int visible = l->kind == K_CF_TRACKS ? IPCF_CARD_ROWS
                      : ip_tall(l->kind)     ? IP_TALL_ROWS
                      : ip_two(l->kind)      ? IP_SONG_ROWS
                                             : IP_ROWS;
        if (l->sel >= l->top + visible) l->top = l->sel - visible + 1;
    }
    ip_redraw();
}

/* The stock Songs row's handler (@0x5275a4: loadSongList of the shown list), then start_player as the stock Play all button does (@0x525d48): the queue is
 * copied, force_refreshflag is set, the page stays where it is. The Now Playing level shows the result. */
static void ip_play(int at, int shuffle) {
    void *pick, *queue, *first;
    unsigned n, idx = 0;
    int found, plid = -1;
    char plname[96];
    plname[0] = 0;
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
        if (pl && (unsigned)row < deque_size(pl)) {
            *(int *)(CLASSINFO + CLASSINFO_ARG) = plid = I(deque_at(pl, (unsigned)row), REC_DISC);
            snprintf(plname, sizeof plname, "%s", cc_str(deque_at(pl, (unsigned)row), REC_TITLE));
        }
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
    if (plid >= 0 && plname[0]) plm_played(plid, plname); /* the playlist's Last Played (patch/plmeta.c) */
    *(unsigned char *)FORCE_REFRESH = 1;
    ip_pend_drop();
    ip.pend_q = queue, ip.pend_rec = first, ip.pend_key = ip_track_key(first), ip.pend_ms = time_now_ms();
    ip_push(K_NOW);
}

/* A play from Cover Flow: the play key on the centre album (its first track; the tracks loaded as the centre button's
 * card loads them, without the flip) or the centre button on a track of the flipped card. Now Playing opens over the
 * shelf, not over a card, so MENU comes back to the covers: the card level is dropped from under it and the flip set back
 * at once. Instead of the level slide the album's cover goes to Now Playing's place (ipcf_go_open, ipcf_go_card). */
static void ip_cf_play(int at) {
    int card = ip_top()->kind == K_CF_TRACKS, d = ip.depth - card;
    if (card)
        ipcf_go_card(ip_top()->sel - ip_top()->top);
    else {
        ipcf_go_open(ip.list, ip.count, ip_top()->sel);
        ipcf_flip_open(ip.list, ip.count, ip_top()->sel);
        ip_push_flip(K_CF_TRACKS);
        if (ip.depth != d + 1) return;
    }
    if (ip_valid() && ip.count) ip_play(at, 0);
    ipcf_flip_close(-1);
    ipcf_flip_settle();
    if (ip.depth == d + 2 && ip_top()->kind == K_NOW) {
        ip.st[d + 1] = ip.st[d + 2];
        ip.depth = d + 1;
        ip_render_cancel(); /* no level slide: the cover goes */
        ip_retime();
        return;
    }
    ipcf_go_close(1);
    ip.depth = d; /* nothing played (no songs, the file gone): back on the shelf */
    ip_level_reset();
    ip_load();
    ip_redraw();
    ip_retime();
}

/* The play key on Cover Flow, as on the iPod: playing, it pauses where you are; paused on the centre album's track, it
 * plays on and the cover goes to Now Playing (no new start); otherwise (stopped, another album) it plays the centre album
 * from its first track (ip_cf_play). */
static void ip_cf_key(void) {
    int s = mclGetPlayStatus(), d = ip.depth;
    void *t = cc_playing(), *r = deque_at(ip.list, (unsigned)ip_top()->sel);
    if (s == 2) {
        playpause_quick_click();
        ip_look();
        ip_redraw();
        return;
    }
    if (s != 3 || !t || !r || !*cc_str(t, REC_ALBUM) || !*cc_str(r, REC_ALBUM) || cc_album_key(t) != cc_album_key(r)) {
        ip_cf_play(0);
        return;
    }
    playpause_quick_click();
    ipcf_go_open(ip.list, ip.count, ip_top()->sel);
    ip_push(K_NOW);
    if (ip.depth == d + 1) ip_render_cancel(); /* no level slide: the cover goes */
    ip_retime();
}

/* Shuffle Songs: the whole library is the queue (the Songs query, as the Shuffle page), a random first song, stock Shuffle (mode 2) so the rest are drawn at random; the iPod's
 * own Now Playing level shows it (no stock page). Nothing is changed when the library is empty or the first file is gone. */
static void ip_shuffle_all(void) {
    void *list = loadLocalClassList(CLASS_ALL_SONGS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    unsigned n = list ? deque_size(list) : 0;
    if (!n) {
        pod_toast(TR("Update Library first"));
        return;
    }
    ip.list = list, ip.count = n, ip.first = deque_at(list, 0), ip.cls = CLASS_ALL_SONGS;
    ip_play((int)pod_rand(n), 1);
}

/* Centre press on a Settings row: Shuffle flips Off / Songs (it reads Albums when Now Playing's slider chose them), Repeat cycles Off, One, All (both are the one stock play mode: Shuffle is mode 2, which has no repeat of its own, so
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

/* An artist or a composer (scope CLASS_COMPOSERS): the album list (the stock "All songs" record first), or, with exactly one album, that album's songs directly. The query tells which. */
static void ip_open_artist(int row, int scope) {
    char name[40], album[40];
    void *list = ip.list, *rec = deque_at(list, (unsigned)row);
    unsigned n, k, albums = 0, i;
    const char *s = cc_str(rec, REC_TITLE);
    for (i = 0; s[i] && i < sizeof name - 1; ++i) name[i] = s[i];
    name[i] = 0;
    album[0] = 0;
    loadAlbumList(scope, rec);
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
        ip_push_titled(scope == CLASS_COMPOSERS ? K_COMPOSER_ALBUMS : K_ARTIST_ALBUMS, name);
}

/* Cover Flow inside the iPod screen (ipod_cf.c); no memory for its frame: the existing Cover Flow page, over this one */
static void ip_open_cover(void) {
    if (ipcf_open(ip.win)) {
        int at;
        ip_push(K_CF);
        if (ip_top()->kind == K_CF && ip_valid() && (at = ipcf_start(ip.list, ip.count)) >= 0)
            ip_top()->sel = at, ip_redraw(); /* on the playing album */
    } else
        coverflow_open();
}

static void ip_select(void) {
    struct lvl *l = ip_top();
    int kind = l->kind;
    if (kind == K_NOW) { /* the scrubber up or down (play / pause is the wheel's bottom sector, as on the iPod) */
        ip_np_select();
        return;
    }
    if (kind == K_SETTINGS) {
        ip_settings_select(l->sel);
        return;
    }
    if (kind == K_MAIN) {
        int row = l->sel; /* Now Playing is the last row: a row is its ROOT_ id */
        if (row == ROOT_MUSIC)
            ip_push(K_MUSIC);
        else if (row == ROOT_COVER)
            ip_open_cover();
        else if (row == ROOT_PODCASTS)
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
        case M_COVER:
            ip_open_cover();
            break;
        case M_GENRES:
            ip_push(K_GENRES);
            break;
        case M_COMPOSERS:
            ip_push(K_COMPOSERS);
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
        }
        return;
    }
    if (!ip_ensure() || !ip.count) return;
    if (kind == K_PODCASTS)
        ip_push_titled(K_PC_EPS, ip.pc_shows[l->sel].title[0] ? ip.pc_shows[l->sel].title : ip.pc_shows[l->sel].dir);
    else if (kind == K_PC_EPS)
        ip_pc_play(l->sel);
    else if (ip_is_tracks(kind)) {
        if (kind == K_CF_TRACKS)
            ip_cf_play(l->sel); /* the card's track: its cover goes to Now Playing, MENU comes back to the covers */
        else
            ip_play(l->sel, 0);
    } else if (kind == K_CF) { /* Cover Flow's centre button: flip the album cover over to its tracklist card */
        ipcf_flip_open(ip.list, ip.count, l->sel);
        ip_push_flip(K_CF_TRACKS);
    } else if (kind == K_ALBUMS || ip_who_albums(kind)) {
        void *rec = ip_rec(kind, ip.list, l->sel);
        ip_push_titled(K_TRACKS, I(rec, REC_ID) == ID_ALL_SONGS
                                     ? TR(ip_who_albums(kind) ? "local_allsong" : "All albums")
                                     : cc_str(rec, REC_ALBUM));
    } else if (kind == K_ARTISTS || kind == K_COMPOSERS)
        ip_open_artist(l->sel, kind == K_COMPOSERS ? CLASS_COMPOSERS : CLASS_ARTISTS);
    else if (kind == K_GENRES)
        ip_push_titled(K_GENRE_SONGS, cc_str(deque_at(ip.list, (unsigned)l->sel), REC_TITLE));
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
    *(int *)G_CLASS_TYPE = CLASS_ALL_SONGS;
    start_player(queue, idx, CLASS_ALL_SONGS, PLAY_MODE);
    *(unsigned char *)FORCE_REFRESH = 1;
    ip_pend_drop();
    if ((unsigned)idx < deque_size(queue))
        ip.pend_rec = deque_at(queue, (unsigned)idx), ip.pend_key = ip_track_key(ip.pend_rec),
        ip.pend_ms = time_now_ms();
    ip.pend_q = queue;
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

/* Hold-to-scan (Now Playing only): a previous / next touch held IP_LONG_MS that turned and travelled nothing moves a scan target of its own (never read back from the
 * player's time): 1 s a timer tick for the first IP_SCAN_SLOW_TICKS ticks, then 3 s, backwards for previous, clamped to [0, length - 1]. Every IP_SCAN_SEEK_MS, when the target
 * moved since the last seek, the scan seeks the player directly with stock mclSetSeek (a fire-and-forget message to hciplayer: no wait, a paused player stays paused), so the
 * scan is audible; the release sends one last seek if the target moved, and the target stays on the bar (sc_hold) until the player's time reaches it. Nothing plays, or a Radio
 * stream, or DLNA: nothing happens. mclSetSeek returning -1 (no player link) ends the scan. */
static int ip_scan_ok(int *pos, int *len) {
    int s = mclGetPlayStatus();
    return ip_top()->kind == K_NOW && (s == 2 || s == 3) && !rd_running() && *(volatile int *)DMR_SERVERFLAG != 1 &&
           cc_playing() && get_playtimeandlength(pos, len) == 1 && *len > 0;
}

static void ip_scan_cancel(void) {
    if (!ip.scan) return;
    ip.scan = ip.sc_hold = 0;
    ip_redraw();
}

/* The direct seek to the scan target: absolute seconds, the CUE start of the playing record added (stock seek_time does the same). 0: nothing sent (stopped, no track),
 * 1: sent, -1: no player link. */
static int ip_scan_seek(void) {
    void *t;
    if (mclGetPlayStatus() == 1 || !(t = cc_playing())) return 0;
    if (mclSetSeek(ip.sc_pos + I(t, REC_CUE_START)) < 0) return -1;
    ip.sc_sent = ip.sc_pos, ip.sc_seek_t = time_now_ms();
    return 1;
}

/* The page timer's tick while the touch is held: enters scan mode at IP_LONG_MS, then moves the target and seeks every IP_SCAN_SEEK_MS. */
static void ip_scan_tick(void) {
    int pos = 0, len = 0, step;
    if (ip.touch != R_RING || !ip.side || ip.turned || ip_top()->kind != K_NOW) return;
    if (!ip.scan) {
        if (ip.far || time_now_ms() - ip.down_t < IP_LONG_MS || !ip_scan_ok(&pos, &len)) return;
        ip.scan = 1, ip.scrub = ip.sc_hold = 0, ip.sc_n = 0, ip.sc_pos = ip.sc_sent = pos, ip.sc_len = len,
        ip.sc_dir = ip.sx > 0 ? 1 : -1;
        ip.sc_seek_t = time_now_ms();
    }
    step = ip.sc_n < IP_SCAN_SLOW_TICKS ? IP_SCAN_SLOW_S : IP_SCAN_FAST_S;
    ip.sc_n++;
    ip.sc_pos += ip.sc_dir * step;
    if (ip.sc_pos > ip.sc_len - 1) ip.sc_pos = ip.sc_len - 1;
    if (ip.sc_pos < 0) ip.sc_pos = 0;
    if (ip.sc_pos != ip.sc_sent && (int)(time_now_ms() - ip.sc_seek_t) >= IP_SCAN_SEEK_MS && ip_scan_seek() < 0) {
        ip.scan = ip.sc_hold = 0; /* no player link: the scan ends quietly */
    }
    ip_redraw();
}

static void ip_scan_commit(void) {
    ip.scan = 0;
    if (ip.sc_pos != ip.sc_sent) {
        if (ip_scan_seek() < 0) {
            ip.sc_hold = 0;
            ip_redraw();
            return;
        }
    }
    ip.sc_hold = 1, ip.sc_until = time_now_ms() + IP_SCAN_HOLD_MS;
    ip_look();
    ip_redraw();
}

/* The Now Playing wheel, as the iPod classic's. A turn sets the volume: stock's own volume dialog steps (VOLP_ADD / VOLP_DEC, IP_VOL_STEPS a wheel step) with the Pod window as their
 * context, so the Max Volume cap, the Bluetooth volume, set_devicevolume and the saves stay stock's; each adds the dialog's 3 s auto-close timer to that window, which stock's stop
 * (VOLP_STOP) removes at once (patch/volume.c does the same). Line Out keeps its fixed level (the volume keys are inert there too). The bar shows the volume for IP_VOL_SHOW_MS.
 * The centre puts up the scrubber: a turn moves the scan's target (IP_SCRUB_S seconds a step, times the wheel's speed tier) and only the knob moves; the finger's release seeks
 * there once (ip_scrub_send), as on the iPod. The centre again, or IP_SCRUB_IDLE_MS without a turn, sends a seek still due and puts the progress bar back. Nothing to scrub: the
 * centre does nothing. */
/* Whether view v can come up now: the scrubber when a hold scan could run, the shuffle slider with a track, the lyrics when the track has a .lrc with text. */
static int ip_np_can(int v) {
    int pos = 0, len = 0;
    if (v == IPV_SCRUB) return ip_scan_ok(&pos, &len);
    if (v == IPV_SHUFFLE) return cc_playing() != (void *)0;
    return v == IPV_LYRICS && ip_lyr_load();
}

/* Now Playing goes to view v, sliding the new one in from the right. Leaving the scrubber sends its last seek and holds the target as the scan's release does. */
static void ip_np_go(int v) {
    int from = ip_np_view(), pos = 0, len = 0;
    unsigned now = time_now_ms();
    if (from == IPV_SCRUB) {
        ip.scrub = 0;
        if (ip.sc_pos != ip.sc_sent) ip_scan_seek();
        if (ip.sc_pos == ip.sc_sent && (int)(ip.sc_seek_t - ip.npv_t) >= 0)
            ip.sc_hold = 1,
            ip.sc_until = now + IP_SCAN_HOLD_MS; /* sought since it came up (npv_t): the target stays on the bar */
    }
    if (v == IPV_SCRUB && ip_scan_ok(&pos, &len)) {
        ip.sc_pos = ip.sc_sent =
            ip.sc_hold ? ip.sc_pos : pos; /* a target still on the bar is where the scrubber starts */
        ip.scrub = 1, ip.sc_hold = ip.scan = 0, ip.sc_len = len;
        ip.scrub_t = now;
    }
    ip.npv = v == IPV_SHUFFLE || v == IPV_LYRICS ? v : 0;
    if (v == IPV_LYRICS) ip.ly_top = 0;
    ip.npv_t = now, ip.vol_until = 0, ip.vs_t0 = 0;
    ip.sl_from = from, ip.sl_to = ip_np_view(), ip.sl_t0 = now | 1;
    ip_redraw();
    ip_retime();
}

/* The centre: the next view that can come up (scrubber, shuffle slider, lyrics), after the last the progress bar again. Nothing can: nothing happens. */
static void ip_np_select(void) {
    int cur = ip_np_view(), v = cur + 1;
    while (v <= IPV_LYRICS && !ip_np_can(v)) ++v;
    if (v > IPV_LYRICS) v = IPV_BAR;
    if (v != cur) ip_np_go(v);
}

static void ip_np_turn(int dir, int rows) {
    int i, pos = 0, len = 0;
    if (ip.scrub) {
        if (!ip_scan_ok(&pos, &len)) {
            ip.scrub = 0, ip_redraw();
            return;
        }
        ip.sc_len = len;
        ip.sc_pos += dir * rows * IP_SCRUB_S;
        if (ip.sc_pos > len - 1) ip.sc_pos = len - 1;
        if (ip.sc_pos < 0) ip.sc_pos = 0;
        ip.scrub_t = time_now_ms(); /* only the knob moves: the seek waits for the release */
        ip_redraw();
        return;
    }
    if (ip.npv == IPV_SHUFFLE) { /* the slider: one choice a step, the shuffle set at once */
        int k = ip_shuf_kind() + (dir > 0 ? 1 : -1);
        ip.npv_t = time_now_ms();
        if (k >= 0 && k <= 2) ip_shuf_set(k);
        ip_redraw();
        return;
    }
    if (ip.npv == IPV_LYRICS) { /* the lyrics scroll, a line a step (ip_lyr_paint keeps it in range) */
        ip.ly_top += dir * rows;
        if (ip.ly_top < 0) ip.ly_top = 0;
        if (ip.lyr && ip.lyr->laid && ip.ly_top > ip_lyr_max()) ip.ly_top = ip_lyr_max();
        ip_redraw();
        return;
    }
    if (peqout_current() == PO_LINEOUT) return;
    for (i = 0; i < IP_VOL_STEPS; ++i) ((int (*)(void *, void *))(dir > 0 ? VOLP_ADD : VOLP_DEC))(ip.win, (void *)0);
    ((void (*)(void *))VOLP_STOP)(ip.win);
    if (!ip.vol_until) ip.vs_t0 = time_now_ms() | 1, ip.vs_back = 0; /* it slides in from the right, as the scrubber */
    ip.vol_until = time_now_ms() + IP_VOL_SHOW_MS;
    if (!ip.vol_until) ip.vol_until = 1;
    ip_redraw();
}

/* The finger left the wheel with the scrubber up: one seek to its target if it moved. No player link: the scrubber goes quietly. */
static void ip_scrub_send(void) {
    if (!ip.scrub || ip_top()->kind != K_NOW || ip.sc_pos == ip.sc_sent) return;
    if (ip_scan_seek() < 0) ip.scrub = 0;
    ip_redraw();
}

/* The page timer's look at the two: the scrubber's idle end; the volume bar's end. */
static void ip_np_tick(void) {
    unsigned now = time_now_ms();
    if (ip.scrub && ip_top()->kind != K_NOW) ip.scrub = 0;
    if (ip.scrub) {
        if ((int)(now - ip.scrub_t) >= IP_SCRUB_IDLE_MS) ip_np_go(IPV_BAR);
    }
    if (ip.npv && ip_top()->kind != K_NOW) ip.npv = 0;
    if (ip.npv == IPV_SHUFFLE && (int)(now - ip.npv_t) >= IP_SCRUB_IDLE_MS) ip_np_go(IPV_BAR);
    if (ip.vol_until && (int)(now - ip.vol_until) >= 0)
        ip.vol_until = 0, ip.vs_t0 = now | 1, ip.vs_back = 1,
        ip_redraw(); /* it goes right, the progress bar comes back from the left */
    if (ip.vs_t0) { /* a volume slide frame; its end paints the still bar once */
        if ((int)(now - ip.vs_t0) >= IP_SCRUB_SLIDE_MS || ip_top()->kind != K_NOW) ip.vs_t0 = 0;
        ip_redraw();
    }
    if (ip.bar_hold && !ip_render_active())
        ip.bar_hold = 0, ip.bar_t0 = (now + (ip_fullscreen(ip_top()->kind) ? IP_BAR_WAIT_MS : 0)) | 1,
        ip_redraw(); /* the slide is over: the bar drops in (after a wait onto a full-screen page, as the iPod's) */
    else if (ip.bar_t0) { /* a drop frame; its end paints the bar in place once */
        if ((int)(now - ip.bar_t0) >= IP_BAR_DROP_MS) ip.bar_t0 = 0, ip.bar_end = 1;
        ip_redraw();
    }
    if (ip.th_t0) { /* a thumb frame; its end paints the still slider once */
        if ((int)(now - ip.th_t0) >= IP_SHUF_THUMB_MS || ip.npv != IPV_SHUFFLE) ip.th_t0 = 0;
        if (ip_top()->kind == K_NOW) ip_redraw();
    }
    if (ip.sl_t0) { /* a slide frame; its end paints the still bar once */
        if (ip_np_slide() < 0) ip.sl_t0 = 0;
        if (ip_top()->kind == K_NOW) ip_redraw();
    }
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
    if (ip.touch == R_RING && ip_top()->kind == K_CF)
        ipcf_rush(); /* the shelf catches up quicker once the finger is off */
    ip.touch = R_NONE;
    ip.scan = 0;
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
    if (ip_top()->kind == K_CF && idx > IPCF_MAX_TIER)
        idx = IPCF_MAX_TIER; /* Cover Flow caps acceleration so fast turns glide smoothly */
    rows = ip_tier_rows(ip_top()->kind == K_NOW && (ip.scrub || ip.npv == IPV_LYRICS) ? IP_LONG + 1 : ip_rows(),
                        idx); /* the scrubber and the lyrics speed up as a long list does */
    while (ip.acc >= IP_STEP) ip.acc -= IP_STEP, ip.turned = 1, ip_step(1, rows);
    while (ip.acc <= -IP_STEP) ip.acc += IP_STEP, ip.turned = 1, ip_step(-1, rows);
    if (ip.turned) ip_scan_cancel(); /* turning the wheel during a hold: no scan, no seek */
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
        ip.side = ip.touch == R_RING && (y < 0 ? -y : y) <= (x < 0 ? -x : x);
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
        int touch = ip.touch, turned = ip.turned, far = ip.far, sx = ip.sx, sy = ip.sy, was_long = ip.long_done,
            scan = ip.scan, side = ip.side;
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
        if (scan) { /* the scan ends: one seek to its target, no skip */
            ip_scan_commit();
            ip_retime();
            return RET_OK;
        }
        if (!turned && !far && side && held >= IP_LONG_MS &&
            ip_top()->kind == K_NOW) { /* a hold with nothing to scan: no tap either */
            ip_retime();
            return RET_OK;
        }
        ip_retime();
        if (turned && touch == R_RING) ip_scrub_send();
        if (turned || far) return RET_OK;
        if (touch == R_CENTRE)
            ip_select();
        else if ((sy < 0 ? -sy : sy) > (sx < 0 ? -sx : sx)) {
            if (sy < 0)
                ip_pop(); /* MENU */
            else if (ip_top()->kind == K_CF && ip_valid() && ip.count)
                ip_cf_key();
            else
                playpause_quick_click(), ip_look(), ip_redraw();
        } else
            ip_skip(sx > 0, e);
    } else if (type == EVT_POINTER_ABORT) {
        int was = ip.scan;
        ip.sc_hold = 0;
        ip_release();
        if (was) ip_redraw(); /* an abort cancels the scan: no seek */
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
    ip_scan_tick();
    ip_np_tick();
    scrobble_note(cc_playing()); /* lit or dark; it asks the player at most every SC_POLL_MS (patch/scrobble.c) */
    if (!m1_screen_lit()) { /* the screen is off: no pan, no cover work, no repaint (the idle-power rule); the next lit tick looks again */
        ip_pane_xfer_stop();
        ip_retime();
        return RET_REPEAT;
    }
    if (ip_render_active()) {
        if (ip_render_tick()) ip_redraw();
        if (ip_render_active()) return RET_REPEAT;
        finished = 1;
        ip_np_tick(); /* the slide just ended: Now Playing's bar starts to drop in this tick */
    }
    if (!ip_valid() &&
        m1_is_top(
            ip.win)) { /* another query replaced the stock list under the page: read it again (the Songs page's stale timer) */
        ip_load();
        ip_redraw();
    }
    if (ip_rows_tick()) ip_redraw();
    if (ip_top()->kind == K_NOW && ipcf_going()) {
        if (ipcf_go_tick()) ip_redraw(); /* the cover going to Now Playing */
    } else if (ip_top()->kind == K_CF && ip_valid() && ipcf_tick(ip.list, ip.count))
        ip_redraw(); /* Cover Flow slides, closes flips and decodes on this timer (ipod_cf.c) */
    else if (ip_top()->kind == K_CF_TRACKS && ipcf_flip_tick())
        ip_redraw(); /* the album cover flipping over to its tracklist card */
    if ((ip.pane.worker || ip.pane.xfer) && !(ip_split(ip_top()->kind) && m1_is_top(ip.win)))
        ip_pane_xfer_stop(); /* the pane is not in front: its extraction goes (cc_build_stop) */
    {
        int pc = ip_pc_step(); /* (first: the covers' frame is built with the picture's fade) */
        if (ip_pane_step() || pc) ip_redraw_pane();
    } /* the cover pane of a split page: only its rectangle is invalidated */
    if (finished || ip.bar_end || ip.ival == IP_TICK_MS ||
        ++ip.lookn >=
            IP_DRIFT_LOOK) { /* refresh playback as soon as a transition (the level slide, then the bar's drop) finishes */
        ip.lookn = 0, ip.bar_end = 0;
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

static void ip_unarm(void) { m1_timer_stop(&ip.timer); }

static int ip_on_background(void *ctx, void *e) {
    (void)e;
    if (!ip.win || ctx != ip.win) return RET_OK;
    ip.fg = 0;
    tg_soften(0); /* the page in front draws in the usual gamma */
    ip_render_cancel();
    ipcf_flip_settle();
    ip_rows_stop();
    ip_pane_xfer_stop();
    ip_unarm();
    ip_release();
    ip.scrub = 0, ip.vol_until = 0, ip.sl_t0 = 0, ip.vs_t0 = 0,
    ip.npv = 0; /* back on the progress bar (a scrubber's unsent target is dropped) */
    return RET_OK;
}

static int ip_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!ip.win || ctx != ip.win) return RET_OK;
    ip.fg = 1;
    tg_soften(1);
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
    tg_soften(0);
    ip_unarm();
    ip_render_close();
    if (ip.touch != R_NONE) widget_ungrab(ip.win, ip.wheel);
    ip_pane_xfer_stop();
    ip_rows_free();
    if (ip.art) bitmap_destroy(ip.art);
    if (ip.np_pic) bitmap_destroy(ip.np_pic);
    if (ip.pane.bmp[0]) bitmap_destroy(ip.pane.bmp[0]);
    if (ip.pane.bmp[1]) bitmap_destroy(ip.pane.bmp[1]);
    if (ip.pane.mix) bitmap_destroy(ip.pane.mix);
    if (ip.shadow) bitmap_destroy(ip.shadow);
    for (int m = 0; m < 5; ++m)
        if (ip.mode_bmp[m]) bitmap_destroy(ip.mode_bmp[m]);
    ipcf_close();
    ip_pc_free();
    ip_pend_drop();
    free(ip.lyr);
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
    ip.st_shuf = widget_lookup(ip.win, "label_ip_shuf", 1);
    ip.st_selb = widget_lookup(ip.win, "label_ip_selb", 1);
    if (!ip.st_selb) ip.st_selb = ip.st_sel; /* the Cover Flow card's bold album style falls back to the regular one */
    ly_font(); /* the bold face is loaded before the first paint in it */
    if (!ip.screen || !ip.wheel || !ip.st_row || !ip.st_sel || !ip.st_title || !ip.st_small || !ip.st_subsel ||
        !ip.st_np1 || !ip.st_np2 || !ip.st_time || !ip.st_val || !ip.st_np3 || !ip.st_shuf) {
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
    tg_soften(1); /* the screen's dark-on-white text in the soft gamma (patch/textgamma.c) */
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
