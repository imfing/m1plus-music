/* M1+ Music Now Playing: the stock playing_page (ui/playing_page.bin, tools/mod_nowplaying.py) gets a cover-tinted
 * background, rounded cover corners that match it, and a remaining-time label that the assets cannot give it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One hook, playing_page_init (0x53d1e4): the page's init, run when Now Playing is built, never at boot or in the
 * main loop. It runs the stock function to completion and then
 * starts a page-scoped 500 ms timer (np_tick) and registers EVT_DESTROY on the window, which removes the timer. It also binds a click handler on the queue
 * button (np_on_queue: our Queue page, patch/queuepage.c; the stock drawer opens when it answers RET_OK).
 * The timer does three things and nothing else:
 *   - the tint: demo writes the track's cover to /tmp/coverpic.jpg or /tmp/externpic.jpg (parseplaycover_thd,
 *     source type word 0x97cad8: 2 and 3/5; 1 while it works); when the file changes (a hash of its bytes) the
 *     picture is decoded by the stock loader, box-averaged to one colour (patch/covercache.c) and np_tone turns that
 *     into a dark, a little desaturated tone that is set as the window's bg_color (widget_set_style); a static
 *     gradient image over it (ui/playing_page.bin, np_tint.png) fades it to black towards the bottom. No cover, or a
 *     source that is not a JPEG file: the neutral dark tone.
 *   - the times: label_playtime and label_playlen carry stock's elapsed and total (stock rewrites both on every tick);
 *     np_elapsed and np_remaining, labels of the asset, show "m:ss" and "-m:ss" from get_playtimeandlength while that
 *     call gives a length, and stock's two show again whenever it does not.
 *   - the info page's lines (np_info): rewritten as "Label: value" with spaced units, only when stock wrote them anew;
 *     the quality line is shown by np_quality, a label of ours, because stock rewrites label_info on every tick.
 * EXPERIMENTAL, the status bar: while the page is in front its bg_color is the page's colour on the first row (np_bar_color),
 * set from np_set_color; EVT_WINDOW_TO_BACKGROUND, the destroy, a replaced page and the tick's top-window check put the stock
 * black back (np_bar_black). Nothing is done unless both window events are registered.
 * The cover is square (AWTK cannot clip an image); its four corners are painted over in the colour the window has
 * there (the tone under the gradient), anti-aliased, from the cover widget's own EVT_AFTER_PAINT: 4 x 12 x 12 pixels
 * of a table np_corner_init computes once, a few dozen canvas_fill_rect calls, and only when the cover repaints.
 * Every failure (a widget of the asset missing, no timer, an unreadable file, an undecodable picture)
 * leaves the stock page as it is, square corners included. docs/modules/nowplaying.md.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "home.h"
#include "i18n.h"
#include "common.h"
#include "lyrics.h"
#include "sbsrc.h" /* sba_now_cover, sba_rec_track, sba_rec_size, sba_url, sba_gen; lib_nd and ls_favorite for the star */
#include "entries.h"
#define NP_ONCE_MS 30 /* the one-shot decode after a track change seen by the cover's paint */
#define NP_SB_WAIT \
    10 /* ticks (5 s) a server track with no cover file yet keeps the previous track's cover on the art before stock's picture shows */

/* The queue button (btn_queue, stock handler 0x53b14c: navigator_to("dialog/playqueue_dialog")) opens our Queue page instead. Bound after the stock init, so it runs before the stock
 * handler: RET_STOP keeps the drawer from opening once our page is up, RET_OK lets it open (a stream, a window that will not open). docs/modules/queue.md. */
static int np_on_queue(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    return queue_open() == 0 ? RET_STOP : RET_OK;
}
#include "podcasts.h"
#include "books.h" /* bk_art_cover */
#include "minibar.h" /* mb_art_t: the header cover of the info page */
#include "fnv.h"
#include "xfade.h" /* xfade_out_rate: the output rate of a converted track */
#include "pcfeed.h" /* PF_NOTE */
#include "pcnotes.h" /* pno_read: the episode's long notes */
#include "pcdetail.h" /* pd_paras: the notes wrapped as the episode page does */

/* Our widgets of the page: the scroll_view that holds them all, the cover view, title, artist, album, the two badge pictures, then per row (label, value; the Location's second line is the value NPI_ROWS) and the
 * row hairlines. Names in the asset (tools/mod_nowplaying.py). */
enum {
    NI_SCROLL,
    NI_ART,
    NI_TITLE,
    NI_TITLE2,
    NI_ARTIST,
    NI_ALBUM,
    NI_HIRES,
    NI_DSD,
    NI_KEY,
    NI_VAL = NI_KEY + NPI_ROWS,
    NI_HAIR = NI_VAL + NPI_ROWS + 1,
    NI_N = NI_HAIR + NPI_ROWS
};
/* The notes page's widgets (page 1 while spoken audio plays, tools/mod_nowplaying.py): the scroll_view, then the header's cover, title, second title line, artist and third line (in the order of NI_ART..NI_ALBUM, so one routine places both
 * headers), the hairline, the hint and the painted body. */
enum { NN_SCROLL, NN_ART, NN_TITLE, NN_TITLE2, NN_ARTIST, NN_ALBUM, NN_HAIR, NN_HINT, NN_BODY, NN_SCRIM, NN_N };
static const char *const np_nw_names[NN_N] = {"np_n_scroll", "np_n_art",          "np_n_title", "np_n_title2",
                                              "np_n_artist", "np_n_album",        "np_n_hair",  "np_n_hint",
                                              "np_n_body",   "img_np_scrim_notes"};

/* A scroll container (the info page's, the notes page's): its widget, the content's scroll offset in px (0 the top) and height, and the finger on it: down, moved (a vertical drag has begun), where it went down, where it was last. */
typedef struct {
    void *w;
    int off, h, td, tm, tsx, tsy, tly;
} np_scr_t;

static const char *const np_iw_names[NI_N] = {
    "np_i_scroll",    "np_i_art", "np_i_title", "np_i_title2", "np_i_artist", "np_i_album", "np_i_badge_hires",
    "np_i_badge_dsd", "np_i_k0",  "np_i_k1",    "np_i_k2",     "np_i_k3",     "np_i_k4",    "np_i_k5",
    "np_i_k6",        "np_i_k7",  "np_i_v0",    "np_i_v1",     "np_i_v2",     "np_i_v3",    "np_i_v4",
    "np_i_v5",        "np_i_v6",  "np_i_v7",    "np_i_v8",     "np_i_h0",     "np_i_h1",    "np_i_h2",
    "np_i_h3",        "np_i_h4",  "np_i_h5",    "np_i_h6",     "np_i_h7"};

static struct {
    void *fav; /* btn_fav (stock's star button): wears the bookmark styles while an episode plays */
    void *mode; /* btn_playmode: the speed button while an episode or a book part plays */
    int speedon; /* 1 while np_mode_sync has a speed style on it: its tap changes the speed */
    void *prev, *next,
        *queue; /* btn_prev, btn_next: the skip buttons while an episode or a book part plays; btn_queue: a plain list then */
    int skipon; /* 1 while np_skip_sync has the skip glyphs on them: their taps seek */
    unsigned shid; /* bit i: stock's label i (Genre, Year) is hidden for spoken audio */
    int spoken; /* 1: the header's track is a podcast episode or a book part (np_header): the info page leaves Genre and Year out */
    pc_ep_t
        ep; /* the playing podcast episode's .episodes entry (pc_ep_of), read when the track changes; zeroed for anything else */
    int favrec, favv; /* a server track's star: the REC_ID favv (1 starred) was read for, 0 none yet */
    unsigned favgen; /* sba_gen() at that read: the cache changed since when it differs */
    void *win, *rem, *tot; /* the window, np_remaining (ours), label_playlen (stock) */
    void *el, *pt; /* np_elapsed (ours), label_playtime (stock's elapsed time); both 0 if the page lacks either */
    void *title, *artist; /* stock scrlabel_title / scrlabel_artist: marquee timers stopped while the screen is dark */
    int dark; /* 1 while stock's 500 ms timer and marquees are paused for screen-off */
    unsigned timer; /* the repeating np_tick timer */
    unsigned interval; /* interval last accepted by timer_modify */
    unsigned key; /* what the colour was last made from: 0 nothing yet, NP_KEY_NEUTRAL, or a file's hash */
    unsigned sig; /* np_cover_sig at the last full hash: while it is unchanged the file is not hashed again */
    unsigned color; /* the window's bg_color as 0x00BBGGRR (what the corners are painted from) */
    int shown; /* the seconds np_remaining shows, -1 none */
    int eshown; /* the seconds np_elapsed shows, -1 none */
    int own; /* 1: our times are the visible labels, 0: stock's are */
    void *idx; /* label_index, the track position between the times (hidden in the asset) */
    int idxon; /* the Track Position setting as read when the page started or came back */
    int shrinkon; /* the Shrink on Pause setting, read alike */
    int idxpos; /* what idx shows: the position (0-based), 0 while hidden */
    unsigned idxn; /* and the queue size, 0 hidden */
    int fg; /* 1 from the page's start and EVT_WINDOW_TO_FOREGROUND, 0 after EVT_WINDOW_TO_BACKGROUND */
    int barok; /* 1: both window events are registered, so the status bar may be tinted (else it never is) */
    int bar; /* 1: the status bar's bg_color is ours (np_bar_color) and must go back to black */
    void *iw[NI_N]; /* the info page's own widgets (np_iw_names), 0 for one the asset lacks */
    int ihead, irow; /* 1: the asset has the whole header / all eight rows (and the scroll_view), so ours show them */
    unsigned qdone; /* the hash of the quality text laid out, 0 none yet */
    int qown; /* 1: our rows 0..3 are the quality and label_info is hidden */
    unsigned rown; /* bit r: row r shows ours (the stock label of it is hidden) */
    int relay; /* ticks left that lay the page out again whatever the text */
    unsigned ikey; /* mb_track_key of the track the header shows, 0 none */
    unsigned rkey; /* mb_track_key of the track the rows were laid out for (a stream's size comes from its record) */
    int ibadge; /* the badge shown: 0 none, 1 HI-RES, 2 DSD */
    np_scr_t
        si; /* the info page's scroll_view np_i_scroll: every child is at its page y - NPI_TOP - si.off (np_info_scroll); h is the content's height from NPI_TOP to the end of the last row (np_flow), the virtual_h */
    np_scr_t sn; /* the notes page's np_n_scroll, alike (np_notes_scroll); h from np_notes_layout */
    void *nw[NN_N]; /* the notes page's widgets (np_nw_names), 0 for one the asset lacks */
    int nok; /* 1: the asset has all of them, so spoken audio gets the notes page in the lyrics page's place */
    int non; /* 1: the notes page is shown and the lyrics page stands down (np_notes_sync) */
    unsigned epkey; /* mb_track_key of the track np.ep, np.ntext were read for */
    char *ntext; /* the notes text (heap, PF_NOTE + 1 bytes): '\n' between paragraphs; "" none. 0 for music */
    pd_t *
        npd; /* the notes wrapped (heap): lines and their page y, laid out once a track change or relay (np_notes_layout) */
    int nby; /* the notes' top (page y) */
    int tsh; /* 0, or NPI_TITLE_LH when the title takes two lines: the artist, the album and the rows are that much lower (m1_wrap2) */
    void *sv; /* slide_view: its page (value) says whether the info page is the one shown */
    int fdirty; /* 1: the rows are laid out again (np_flow) at the end of the tick */
    int rkw[NPI_ROWS], rvx[NPI_ROWS], rvw[NPI_ROWS]; /* per row: its label's text width, its value box's x and width */
    int fmtw, locn; /* the Format value's text width (the badge's place); the Location's lines (1 or 2) */
    mb_art_t ia; /* the header's cover (patch/minibar.c), NPI_ART px with NPI_ART_R px corners */
    void *info[NP_INFO_N]; /* the info page's stock labels (np_info_names), the data: 0 for one the page lacks */
    unsigned
        done[NP_INFO_N]; /* the hash of the text each label held after our last look: stock's text, or what we wrote */
    unsigned char corner[NP_ART_R * NP_ART_R]; /* the top left corner's coverage outside the arc, 0..255 */
    void *art,
        *sbmp; /* img_playcover, and the NP_ART x NP_ART RGBA bitmap of a server track's cover (made on first use, freed with the page) */
    unsigned sbkey; /* np_hash of the cover file sbmp holds */
    int sbrec, sbshow; /* the REC_ID of the track sbmp is for; 1: sbmp is drawn over stock's picture */
    int sbbook; /* 1: sbmp is the book cover of a local audiobook part stock has no picture of (np_book_cover) */
    int sbseen; /* the REC_ID np_server_art last looked at */
    int sbwait; /* ticks the playing server track has had no cover file while sbmp (the previous track's) is kept on show */
    int pfrec; /* the REC_ID of the queue record whose cover was last asked for ahead */
    unsigned once; /* the one-shot np_art_once timer, 0 none */
    void *shadow; /* img_np_shadow (the asset's), scaled with the cover; 0 if the page lacks it */
    int asz, afrom,
        ato; /* the cover's side now (0: the asset's NP_ART), where its spring started, where it goes (0: no target yet) */
    unsigned at0, anim; /* the spring's start (time_now_ms), its frame timer (0 none) */
    int cr; /* the corner radius np.corner holds (0: NP_ART_R) */
    unsigned pchk; /* the play button's status check timer (0 none) */
    int pst, pleft; /* the status when the button was tapped, checks left */
    void *slider; /* slider_play, the progress bar (np_on_scrub) */
    int scrub; /* 1 while a finger is on it: the bar goes to NP_BAR_SCRUB px thick, 0 to NP_BAR */
    int bsz, bfrom; /* its bar_size now, and where the ease started */
    unsigned bt0, btimer; /* the ease's start (time_now_ms), its frame timer (0 none) */
    void *dots; /* slide_indicator, the page dots in the middle of the times row (np_dots_*) */
    int dop, dfrom; /* the dots' opacity now (label_index has 255 - dop), and where a page change's fade started */
    unsigned dt0, dtimer; /* that page change's time (time_now_ms), its frame timer (0 none) */
} np __attribute__((section(".scratch")));

/* A dark, a little desaturated tone of the cover's average colour (r, g, b bytes), as a color_t word
 * (0xAABBGGRR, alpha ff). Value: NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) / 255 for the brightest channel v; every
 * channel keeps NP_SAT_NUM / NP_SAT_DEN of its distance from v (a grey stays grey). A black cover is the neutral
 * tone. With NP_V_MAX 192 the white title and the #AAAAAA lines keep 4.5:1 over the gradient (test/pod/nowplaying.py). */
__attribute__((noinline)) unsigned np_tone(unsigned r, unsigned g, unsigned b) {
    return m1_tone(r, g, b); /* patch/common.c, shared with the album page's tint */
}

/* A clock without a leading zero, as Apple Music prints it: "m:ss", or "h:mm:ss" from an hour on; neg puts a "-" first. */
__attribute__((noinline)) void np_format_clock(char *out, unsigned size, int secs, int neg) {
    const char *sign = neg ? "-" : "";
    if (secs < 0) secs = 0;
    if (secs >= 3600)
        snprintf(out, size, "%s%d:%02d:%02d", sign, secs / 3600, secs / 60 % 60, secs % 60);
    else
        snprintf(out, size, "%s%d:%02d", sign, secs / 60, secs % 60);
}

/* "-m:ss", or "-h:mm:ss" from an hour on: the seconds left. A position past the end shows -0:00. */
__attribute__((noinline)) void np_format_remaining(char *out, unsigned size, int pos, int len) {
    np_format_clock(out, size, len - pos, 1);
}

/* The coverage of the area outside a quarter circle of radius NP_ART_R in the corner square of NP_ART_R pixels
 * (the circle's centre at the square's inner corner), 0..255: each pixel is sampled 8 x 8 times. The same numbers
 * as the PNG mask of the earlier builds (test/pod/nowplaying.py). */
__attribute__((noinline)) void np_corner_init(void) {
    m1_corner_fill(np.corner, NP_ART_R);
    np.cr = NP_ART_R;
}

/* The pause spring: 1024 x g(t) every 10 ms, g = e^(-zeta wn t) (cos wd t + zeta / sqrt(1 - zeta^2) sin wd t), wd = wn sqrt(1 - zeta^2); critically damped (g = (1 + wn t) e^(-wn t))
 * for the shrink, zeta 1, wn 22 /s; zeta 0.75, wn 18 /s for the grow (-0.028 at 260 ms: a subtle bounce, 2 px). test/pod/nowplaying.py computes the same numbers. */
static const short np_shrink_tab[NP_SHRINK_MS / 10 + 1] = {1024, 1003, 950, 879, 799, 716, 635, 558, 486, 421,
                                                           363,  311,  266, 226, 192, 162, 137, 115, 97,  81,
                                                           68,   57,   47,  39,  33,  27,  23,  19,  15};
static const short np_grow_tab[NP_GROW_MS / 10 + 1] = {
    1024, 1009, 969, 911, 841, 763, 683, 602, 523, 448, 378, 314, 256, 205, 160, 121, 88, 60, 37, 19, 4,  -7, -16, -22,
    -26,  -28,  -29, -29, -28, -27, -25, -23, -20, -18, -16, -14, -11, -10, -8,  -6,  -5, -4, -3, -2, -1, -1, 0};

/* The cover's side `el` ms into a spring from `from` to `to` px: the grow table when it gets bigger, else the shrink one; linear between entries, `to` from the table's end on. The side is an even number
 * of px from `to` (rounded to the nearest), so the cover stays centred: an odd step would move one edge alone, and the bounce would show on one side only. */
__attribute__((noinline)) int np_art_size(int from, int to, int el) {
    const short *tab = to > from ? np_grow_tab : np_shrink_tab;
    int ms = to > from ? NP_GROW_MS : NP_SHRINK_MS, idx, g, d;
    if (el <= 0) return from;
    if (el >= ms) return to;
    idx = el / 10;
    g = tab[idx] + (tab[idx + 1] - tab[idx]) * (el % 10) / 10;
    d = (from - to) * g;
    return to + 2 * ((d + (d >= 0 ? 1024 : -1024)) / 2048);
}

/* The cover (and its shadow, scaled alike) at a side of s px, centred where the full cover is; the corner table follows the radius (NP_ART_R at the full size, scaled, never more). The old and the new
 * rectangle of the bigger widget are invalidated. */
static void np_art_place(int s) {
    void *big = np.shadow ? np.shadow : np.art;
    int in = (NP_ART - s) / 2, x = NP_ART_X + in, y = NP_ART_Y + in, pad = NP_SHADOW_PAD * s / NP_ART,
        r = (NP_ART_R * s + NP_ART / 2) / NP_ART;
    if (r > NP_ART_R) r = NP_ART_R;
    if (r != np.cr) {
        m1_corner_fill(np.corner, (unsigned)r);
        np.cr = r;
    }
    widget_invalidate_force(big, (void *)0);
    widget_move(np.art, x, y);
    widget_resize(np.art, s, s);
    if (np.shadow) { /* lighter as the cover shrinks: NP_SHADOW_DIM at the paused size, full from NP_ART on */
        int k = s < NP_ART_SMALL ? 0 : s > NP_ART ? NP_ART - NP_ART_SMALL : s - NP_ART_SMALL;
        widget_set_opacity(np.shadow, NP_SHADOW_DIM + (255 - NP_SHADOW_DIM) * k / (NP_ART - NP_ART_SMALL));
        widget_move(np.shadow, x - pad, y - pad);
        widget_resize(np.shadow, s + 2 * pad, s + 2 * pad);
    }
    widget_invalidate_force(big, (void *)0);
    np.asz = s;
}

static int np_art_live(void);

/* A frame of the spring: the side for the time it has run, until it has landed. The artwork no longer seen (screen off, another page, the lyrics or info page): it lands at once. */
static int np_art_frame(const void *timer) {
    int el, s;
    (void)timer;
    if (!np.win || !np.anim) return RET_OK;
    if (!np_art_live()) {
        np.anim = 0; /* RET_OK ends this timer */
        if (np.asz != np.ato) np_art_place(np.ato);
        return RET_OK;
    }
    el = (int)(time_now_ms() - np.at0);
    s = np_art_size(np.afrom, np.ato, el);
    if (s != np.asz) np_art_place(s);
    if (el < (np.ato > np.afrom ? NP_GROW_MS : NP_SHRINK_MS)) return RET_REPEAT;
    np.anim = 0;
    return RET_OK;
}

/* The art page is what the page shows, lit and in front: only then does the cover move, else it is put at its size. */
static int np_art_live(void) {
    return np.fg && m1_screen_lit() && (!np.sv || widget_get_prop_int(np.sv, "value", NP_ART_PAGE) == NP_ART_PAGE);
}

/* Settings > Now Playing > Shrink on Pause (NPSHRINK_FILE): on by default; "0" keeps the cover full size. */
int np_shrink_setting(void) { return set_read(NPSHRINK_FILE, '1') != '0'; }
int np_shrink_toggle(void) { return home_set_digit(NPSHRINK_FILE, !np_shrink_setting(), 1); }

/* The cover's size follows the player, with Shrink on Pause on: small while paused or stopped (Wi-Fi Transfer stops the player under the page), full otherwise; with it off, always full. A new target
 * springs from the size the cover has (a change mid-spring turns it round), or is set at once when `animate` is 0 or no frame timer is had. */
static void np_art_sync(int animate) {
    int want, st;
    if (!np.art) return;
    st = mclGetPlayStatus();
    want = np.shrinkon && (st == NP_PAUSED || st == NP_STOPPED) ? NP_ART_SMALL : NP_ART;
    if (want == np.ato) {
        if (!animate && np.anim) { /* the spring is no longer seen: it lands now */
            m1_timer_stop(&np.anim);
            if (np.asz != want) np_art_place(want);
        }
        return;
    }
    np.ato = want;
    if (animate && !np.anim) {
        np.anim = timer_add(np_art_frame, (void *)0, NP_FRAME_MS);
    } else if (!animate)
        m1_timer_stop(&np.anim);
    if (!np.anim) {
        if (want != np.asz) np_art_place(want);
        return;
    }
    np.afrom = np.asz ? np.asz : NP_ART;
    np.at0 = time_now_ms();
}

/* After a tap on the play button: stock's handler (it runs after ours) changes the status a moment later; the cover follows as soon as it has. */
static int np_play_check(const void *timer) {
    (void)timer;
    if (!np.win || !np.pchk) return RET_OK;
    if (mclGetPlayStatus() == np.pst && --np.pleft > 0) return RET_REPEAT;
    np.pchk = 0;
    np_art_sync(np_art_live());
    return RET_OK;
}

static int np_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!np.win || !np.art) return RET_OK;
    np.pst = mclGetPlayStatus();
    np.pleft = NP_PLAY_CHECKS;
    if (!np.pchk) np.pchk = timer_add(np_play_check, (void *)0, NP_PLAY_MS);
    return RET_OK;
}

static int np_art_once(const void *timer);

/* The cover widget's EVT_AFTER_PAINT: the four corners, in widget coordinates (the stock paint only translates), for the side the cover has now. */
static int np_on_art_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int s = np.asz ? np.asz : NP_ART;
    (void)ctx;
    if (!canvas || !np.win) return RET_OK;
    if (np.art) { /* a server track's cover (stock draws nothing for a stream; its placeholder must not show between two tracks): sbmp stays up while a server track is playing, until
                   * the new cover is decoded (np_art_once, a moment after the change is seen here, or the tick); a local track draws stock's picture */
        void *t = cc_playing();
        int rec = t ? *(int *)((char *)t + REC_ID) : 0;
        if (rec <= -2 || np.sbbook) { /* (or a book part's cover: np_server_art drops it with the tick) */
            int r[4] = {0, 0, NP_ART, NP_ART}, d[4] = {0, 0, s, s};
            if (np.sbshow && np.sbmp) canvas_draw_image(canvas, np.sbmp, r, d);
            if (rec != np.sbseen && !np.once) np.once = timer_add(np_art_once, (void *)0, NP_ONCE_MS);
        }
    }
    m1_corners(canvas, np.corner, np.cr ? (unsigned)np.cr : NP_ART_R, (unsigned)s, np.color,
               NP_ART_Y + (NP_ART - s) / 2, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H);
    return RET_OK;
}

/* FNV-1a over the file's bytes (at most NP_HASH_MAX of them) and its length, never 0; 0 when it cannot be read or is
 * empty. */
__attribute__((noinline)) unsigned np_file_key(const char *path) {
    unsigned char buf[512];
    unsigned h = FNV_SEED, total = 0, n, i;
    void *f = fopen(path, "rb");
    if (!f) return 0;
    while (total < NP_HASH_MAX && (n = fread(buf, 1, sizeof buf, f)) > 0) {
        for (i = 0; i < n; ++i) h = (h ^ buf[i]) * FNV_PRIME;
        total += n;
    }
    fclose(f);
    h = (h ^ total) * FNV_PRIME;
    return total ? h | !h : 0;
}

/* EXPERIMENTAL: the status bar takes the colour the page has on its first row, so the bar and the page read as one surface
 * (m1_bar_tint / m1_bar_black, patch/common.c, shared with the album page). np_bar_color is the colour (0x..BBGGRR) under the black gradient on the first row (np_tint.png: black, NP_ALPHA_TOP at the first row to NP_ALPHA_BOTTOM at the last), darkened
 * until the bar's white glyphs keep 4.5:1 (m1_bar_color). */
__attribute__((noinline)) unsigned np_bar_color(unsigned color) {
    return m1_bar_color(m1_shade(color, 0, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H));
}

/* The bar in the page's colour, while the page is in front and its events are registered. */
static void np_bar_apply(void) {
    if (np.barok && np.fg && m1_bar_tint(np.win, np_bar_color(np.color)))
        np.bar = 1; /* a failed call keeps what the bar has (and owes) */
}

/* The stock black, if the bar is ours. Called on every way out: background, destroy, a window above, a replaced page. A page
 * that took the bar over since (the album page on Back) keeps it: only the owner restores. */
static void np_bar_black(void) {
    if (!np.bar) return;
    np.bar = 0;
    m1_bar_black(np.win);
}

/* The timer's check, for what the events missed: the bar is ours only while the page is the top normal window. A dialog
 * (the pull-down) is not a normal window; its EVT_WINDOW_TO_BACKGROUND has cleared np.fg. */
static int np_bar_sync(void) {
    int top = m1_is_top(np.win);
    if (np.bar && !top)
        np_bar_black();
    else if (!np.bar && top)
        np_bar_apply();
    return top;
}

/* The cover's tone as the page shows it: in Light Mode the page is neutral (pal_tone: the dark chromatic tone cannot flip, and the page's white text does). np_tone_raw is
 * the tone as chosen, so np_relight can put the page right when the mode changes while it is open. */
static unsigned np_tone_raw __attribute__((section(".scratch")));

static void np_set_color(unsigned tone) {
    unsigned v[4], color = pal_tone(tone); /* value_t: type at 0, the uint32 at 8 */
    np_tone_raw = tone;
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    if (widget_set_style(np.win, "normal:bg_color", v) != RET_OK) return;
    np.color = color & 0xffffff;
    widget_invalidate_force(np.win, (void *)0);
    np_bar_apply();
}

void np_relight(void) {
    if (np.win && np_tone_raw) np_set_color(np_tone_raw); /* (patch/palette.c pal_apply) */
}

unsigned np_hash(const char *s);

/* An audiobook part's own cover, the book's (bk_art_cover), for a part stock has no picture of: "file://<path>" in npb.url, asked once per playing track path (a readdir). The answer is
 * forgotten by np_cover_file whenever the playing track is not the one it is for (whatever stock's source says meanwhile) and while stock is busy (every track start, a restart of the
 * same part too), so a book art file built meanwhile shows when the part plays again. NULL: not a part, or the book has no cover. */
static struct {
    unsigned key; /* np_hash of the track path the answer is for, 0 none yet */
    int ok;
    char url[NP_COVER_URL];
} npb __attribute__((section(".scratch")));

/* np_hash of the playing track's path when it is an audiobook part, else 0. */
static unsigned np_book_key(const char **path) {
    void *t = cc_playing();
    const char *p = t ? cc_str(t, REC_PATH) : (const char *)0;
    *path = p;
    return p && bk_is_path(p) ? np_hash(p) : 0;
}

const char *np_book_cover(void) {
    const char *p;
    unsigned key = np_book_key(&p);
    if (!key) return (const char *)0;
    if (key != npb.key) npb.key = key, npb.ok = bk_art_cover(p, npb.url, sizeof npb.url) != (const char *)0;
    return npb.ok ? npb.url + 7 : (const char *)0;
}

/* The cover file of the source type, or NULL for a source with no JPEG file; busy is set while demo is still making it. A part of an audiobook that stock has no picture of (no source, not busy) gets its book's cover. */
const char *np_cover_file(int *busy) { /* also the mini player bar's (patch/minibar.c) */
    int src = *(volatile int *)COVER_SRC;
    const char *server_cover = sba_now_cover(cc_playing()), *p;
    *busy = src == COVER_SRC_BUSY;
    if (*busy || np_book_key(&p) != npb.key) npb.key = 0; /* another track, or a (re)start: asked again */
    if (server_cover) return server_cover;
    if (src == COVER_SRC_EMBEDDED) return "/tmp/coverpic.jpg";
    if (src == COVER_SRC_FOLDER || src == COVER_SRC_CACHE) return "/tmp/externpic.jpg";
    return *busy ? (const char *)0 : np_book_cover();
}

/* The cheap look at the cover (no byte of it is read): a hash of the source type, the file's length (fseek/ftell) and the
 * playing track's path. demo writes a new cover for every track change (and passes through the busy state first), so while
 * all three are as at the last full hash the file is taken as unchanged; any difference sends it to np_file_key. 0: the
 * file cannot be opened (a full look, which tries again too). */
__attribute__((noinline)) unsigned np_cover_sig(const char *path, int src) {
    void *f = fopen(path, "rb");
    void *track;
    long size;
    unsigned h;
    if (!f) return 0;
    size = !fseek(f, 0, 2) ? ftell(f) : -1;
    fclose(f);
    if (size <= 0) return 0;
    track = cc_playing();
    h = np_hash(track ? cc_str(track, REC_PATH) : "");
    h = (h ^ (unsigned)size) * FNV_PRIME;
    h = (h ^ (unsigned)src) * FNV_PRIME;
    return h | !h;
}

/* The cover of the queue record after the playing one, asked for once while a server track plays (sba_now_cover asks when the file is not cached and the ask has not failed), so
 * it is usually there when the track starts. */
static void np_prefetch(int rec) {
    void *q = *(void **)PLAY_QUEUE, *next;
    int pos = mclGetPlayPos(), nrec;
    if (!q || pos < 0 || (unsigned)pos + 1 >= deque_size(q)) return;
    next = deque_at(q, (unsigned)pos + 1);
    nrec = next ? *(int *)((char *)next + REC_ID) : 0;
    if (nrec <= -2 && nrec != rec && nrec != np.pfrec) np.pfrec = nrec, (void)sba_now_cover(next);
}

/* A playing server track's cover file (or the book cover of a local audiobook part stock has no picture of) is the big art: stock draws /tmp/coverpic.jpg, which it never writes for a stream. The picture is decoded once into a bitmap of ours
 * and drawn over stock's by np_on_art_paint; a track with no cached cover (sba_now_cover asks for it) shows stock's, and so does every other local track. */
static void np_server_art(void) {
    void *t = cc_playing();
    int rec = t ? *(int *)((char *)t + REC_ID) : 0;
    const char *path;
    unsigned key, *px;
    char url[NP_COVER_URL]; /* "file://" and a cover file's path */
    if (!np.art) return;
    np.sbseen = rec;
    /* a local track (or none): stock's picture, unless it is an audiobook part stock has none of: the book's cover */
    if (rec > -2) {
        int busy;
        path = np_cover_file(&busy);
        if (!(path && path == npb.url + 7) && !(busy && np.sbbook)) {
            if (np.sbshow) np.sbshow = 0, widget_invalidate_force(np.art, (void *)0);
            np.sbbook = np.sbwait = 0;
            return;
        }
        if (!path) return; /* stock is making a picture: the book's stays until it is there */
        np.sbbook = 1;
    } else {
        np.sbbook = 0;
        np_prefetch(rec);
        path = sba_now_cover(t);
    }
    if (!path) { /* not cached yet (sba_now_cover has asked), or the track has none: the previous cover stays for NP_SB_WAIT ticks, then stock's */
        if (np.sbshow && ++np.sbwait > NP_SB_WAIT)
            np.sbshow = 0, np.sbwait = 0, widget_invalidate_force(np.art, (void *)0);
        return;
    }
    np.sbwait = 0;
    key = np_hash(path);
    if (np.sbshow &&
        key == np.sbkey) { /* the picture is already up (the next track of the album): only the record changes */
        np.sbrec = rec;
        return;
    }
    if (!np.sbmp) np.sbmp = bitmap_create_ex(NP_ART, NP_ART, NP_ART * 4, BITMAP_RGBA8888);
    px = np.sbmp ? (unsigned *)bitmap_lock_buffer_for_write(np.sbmp) : (unsigned *)0;
    if (!px) return;
    snprintf(url, sizeof url, "file://%s", path);
    np.sbshow = cc_decode(np.win, url, 1, NP_ART, 1, px);
    bitmap_unlock_buffer(np.sbmp);
    np.sbkey = key, np.sbrec = rec;
    widget_invalidate_force(np.art, (void *)0);
}

/* The one-shot timer of np_on_art_paint: decodes the new track's cover at once, outside the paint. Returning RET_OK ends the timer. */
static int np_art_once(const void *timer) {
    (void)timer;
    np.once = 0;
    if (np.win) np_server_art();
    return RET_OK;
}

static void np_cover(void) {
    int busy;
    const char *path = np_cover_file(&busy);
    unsigned key, sig, px, album, tone;
    char url[NP_COVER_URL]; /* cc_url's size at least, and "file://" with np_cover_file's path */
    void *track;
    if (busy) return; /* the file is being replaced: keep the colour */
    if (!path) { /* no picture file: the neutral tone, once */
        if (np.key != NP_KEY_NEUTRAL) np.key = NP_KEY_NEUTRAL, np_set_color(NP_NEUTRAL);
        return;
    }
    sig = np_cover_sig(path, *(volatile int *)COVER_SRC);
    if (sig && sig == np.sig && np.key && np.key != NP_KEY_NEUTRAL)
        return; /* same source, length and track as at the last look */
    track =
        cc_playing(); /* the track's album: its tone may be known (the album page's, an earlier play); an untagged one has no key */
    /* (a book part's cover is not its tags' album) */
    album = track && *cc_str(track, REC_ALBUM) && path != npb.url + 7 ? cc_album_key(track) : 0;
    if (sig && album && m1_tone_get(album, &tone)) { /* known: no hash of the file (up to NP_HASH_MAX bytes) */
        np.sig = sig, np.key = NP_KEY_TONE; /* a key no hash is compared equal to: the next full look colours again */
        np_set_color(tone);
        return;
    }
    key = np_file_key(path);
    if (!key) return; /* unreadable: try again next tick */
    if (*(volatile int *)COVER_SRC == COVER_SRC_BUSY) return; /* demo started over while we read */
    np.sig = sig;
    if (key == np.key) return; /* unchanged: nothing to do */
    np.key = key;
    /* the tone cache is RAM only: after a boot the album's Cover Flow cache file (168 px, the album page's source) is a far
     * cheaper decode than the embedded picture (often 600-1400 px); no such file: the playing cover's own file */
    if (album && cc_url(url, album) && cc_decode(np.win, url, 1, 1, 1, &px)) {
        tone = np_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        np_set_color(tone);
        m1_tone_put(album, tone);
        return;
    }
    snprintf(url, sizeof url, "file://%s", path);
    if (cc_decode(np.win, url, 1, 1, 1, &px)) {
        tone = np_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        np_set_color(tone);
        m1_tone_put(album, tone);
    }
}

/* The idle lyrics page's (patch/idlelyrics.c) view of this page: its window, 0 when it has none (the page then does not open), and the colour the window has (a color_t word) once the cover's tone has been looked
 * at again: this page's own tick does not run while another window covers it, so the idle page asks. np_cover compares the cheap signature and does no work for a track it has seen. */
void *np_window(void) { return np.win; }

unsigned np_idle_color(void) {
    if (!np.win) return NP_NEUTRAL | 0xff000000u;
    np_cover();
    return np.color | 0xff000000u;
}

/* np_elapsed and np_remaining are the visible labels while the player gives a length, label_playtime and label_playlen
 * (stock's) otherwise. Stock rewrites its two on its own tick ("01:27"), so ours are separate labels and not rewrites of
 * stock's text, which a paint between the two timers would show. */
static void np_label(int own) {
    if (own == np.own) return;
    np.own = own;
    widget_set_visible(np.rem, own, 0); /* all four are insensitive in the asset, so hidden is also untouchable */
    widget_set_visible(np.tot, !own, 0);
    if (np.el) {
        widget_set_visible(np.el, own, 0);
        widget_set_visible(np.pt, !own, 0);
    }
}

/* While a finger is on the progress bar (np.scrub) the times follow it, as Apple Music's do: the position is the slider's value scaled from its max (stock sets the track's
 * length there) to the player's length. Stock's own VALUE_CHANGING handler writes label_playtime the same way, under np_elapsed. No 64-bit division in the payload. */
static int np_scrub_pos(int pos, int len) {
    unsigned max = widget_get_prop_int(np.slider, "max", 0), v = widget_get_prop_int(np.slider, "value", -1);
    if (!max || v > max) return pos;
    return max == (unsigned)len ? (int)v : (int)(v / max * len + v % max * len / max);
}

static void np_time(void) {
    int pos = 0, len = 0;
    char text[16];
    if (!np.rem || !np.tot) return;
    if (get_playtimeandlength(&pos, &len) != 1 || len <= 0) {
        np_label(0);
        return;
    }
    if (np.scrub && np.slider) pos = np_scrub_pos(pos, len);
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if (np.shown != len - pos) {
        np_format_remaining(text, sizeof text, pos, len);
        widget_set_text_utf8(np.rem, text);
        np.shown = len - pos;
    }
    if (np.el && np.eshown != pos) {
        np_format_clock(text, sizeof text, pos, 0);
        widget_set_text_utf8(np.el, text);
        np.eshown = pos;
    }
    np_label(1);
}

/* Settings > Now Playing > Track Position (NPPOS_FILE): "5/10" in the middle of the times row. Stock writes label_index ("%d/%d", the position + 1 and the queue size) only on a
 * track change; ours writes the same text on every tick, so a queue edit shows at once. Shown only with the setting on and a queue of two or more with the position inside it. */
int np_pos_setting(void) { return set_read(NPPOS_FILE, 0) == '1'; }
int np_pos_toggle(void) { return home_set_digit(NPPOS_FILE, !np_pos_setting(), 1); }

static void np_index(void) {
    int pos = mclGetPlayPos();
    void *q = *(void **)PLAY_QUEUE;
    unsigned n = q ? deque_size(q) : 0;
    char text[24];
    if (!np.idx) return;
    if (!np.idxon || n < 2 || pos < 0 || (unsigned)pos >= n)
        pos = 0, n = 0; /* hidden (as after the page start memset) */
    if (pos == np.idxpos && n == np.idxn) return;
    if (n) {
        snprintf(text, sizeof text, "%u/%u", (unsigned)pos + 1, n);
        widget_set_text_utf8(np.idx, text);
    }
    widget_set_visible(np.idx, n != 0, 0);
    np.idxpos = pos;
    np.idxn = n;
}

/* The info page (page 3). Stock writes its lines when the track changes (show_player_face 0x53bab4 -> the fill 0x539c40, only
 * while its "changed" flags are set; the page timer calls it every tick but it fills only then): "%s:%s" for album, genre, year,
 * location, "%s:%.2fMB" for the size, "%s|%.1fkHz|%dbit|%dkbps" (the quality line, label_info), the label and the "Unknown" of a
 * missing value in the app's language (getFormatString: player_unknown, player_location ...). Those six labels are the data
 * source and stay (hidden and insensitive once ours show); the page itself is ours (docs/modules/nowplaying.md "Information page"):
 *   - the header (np_header): cover, title, artist, album of the playing record;
 *   - eight rows (np_quality for the first four, np_row for the others; np_set_row, np_flow): Format, Sample Rate, Bit Depth, Bitrate (label_info's fields), Genre, Year, File Size, Location; a label and a right aligned
 *     value, the HI-RES / DSD badge (tape_badge, the cassette theme's rule) left of the Format value; the Location's path is under its label in up to two lines (np_loc_fit). A row stock has no value for is left out
 *     and the ones below move up;
 *   - all of it is a child of the scroll_view np_i_scroll, placed by np_cy (page y, minus the scroll_view's top, minus np.si.off): np_info_scroll moves the whole content.
 * A label of ours is placed with widget_move / widget_resize from the measured text, never painted. The Genre, Year, File Size and
 * quality labels are our keys, the Location label stock's. np.done remembers the hash of each stock text after our last look, so a line is
 * laid out only when stock has written it again (or for NP_RELAY ticks after the page starts: a label measures in its own style only
 * once the window is open). Anything that does not look as expected gives the line back to stock's label. */
static const char *const np_info_names[NP_INFO_N] = {"label_info", "label_album", "label_genre",
                                                     "label_year", "label_size",  "label_location"};

typedef struct {
    char *p, *end;
} np_out;

static void np_put(np_out *o, char c) {
    if (o->p < o->end) *o->p++ = c;
}
static void np_puts(np_out *o, const char *s) {
    while (*s) np_put(o, *s++);
}
static int np_starts(const char *s, const char *w) {
    while (*w)
        if (*s++ != *w++) return 0;
    return 1;
}
static int np_digit(char c) { return c >= '0' && c <= '9'; }

__attribute__((noinline)) unsigned np_hash(const char *s) {
    unsigned h = m1_fnv(FNV_SEED, s);
    return h | !h;
}

/* s into out (size bytes, NUL terminated), cut at a character boundary. */
static void np_cut(char *out, unsigned size, const char *s) {
    unsigned n = 0;
    while (s[n] && n + 1 < size) ++n;
    while (n && s[n] && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    memcpy(out, s, n);
    out[n] = 0;
}

/* The text after the first colon (leading spaces dropped) of a stock line "Label:value"; NULL without a colon or with a label of no length. */
static const char *np_after_colon(const char *s) {
    const char *c = s;
    while (*c && *c != ':') ++c;
    if (!*c || c == s) return (const char *)0;
    for (++c; *c == ' '; ++c) {
    }
    return c;
}

/* v with a space between a digit and "MB" ("35.92MB" -> "35.92 MB"), into out. */
static void np_size_text(const char *v, char *out, unsigned size) {
    np_out o;
    const char *p;
    o.p = out, o.end = out + size - 1;
    for (p = v; *p; ++p) {
        if (p > v && np_digit(p[-1]) && np_starts(p, "MB"))
            np_puts(&o, " MB"), p += 1;
        else
            np_put(&o, *p);
    }
    *o.p = 0;
}

/* The size and location lines of a playing server stream: stock's come from the queue record, whose path is the stream address (the token and salt are in it) and whose file does not exist. The
 * label is stock's (its text up to the colon), the size is the server's (sba_rec_size, "N.NN MB"; "Unknown" when the server gave none), the location is the server's address without
 * credentials, path or query. 0 for any other line or track (a local file, and a downloaded track, which plays from its own path, are stock's). */
__attribute__((noinline)) int np_stream_text(int i, const char *s, char *out, unsigned size) {
    void *t = cc_playing();
    const char *path, *colon = s, *u, *e, *at;
    int rec;
    np_out o;
    if ((i != 4 && i != 5) || !t) return 0;
    rec = *(int *)((char *)t + REC_ID);
    path = cc_str(t, REC_PATH);
    if (rec > -2 || !np_starts(path, "http") || !sba_rec_track(rec)[0]) return 0;
    o.p = out, o.end = out + size - 1;
    while (*colon && *colon != ':') ++colon;
    if (*colon && colon != s) {
        for (u = s; u < colon; ++u) np_put(&o, *u);
        np_puts(&o, ": ");
    }
    if (i == 4) {
        unsigned bytes = sba_rec_size(rec), mb = bytes >> 20,
                 hundredths = (((bytes & 0xfffffu) * 100u) + 524288u) >> 20;
        char num[24];
        if (hundredths >= 100) ++mb, hundredths -= 100;
        if (bytes) {
            snprintf(num, sizeof num, "%u.%02d MB", mb, (int)hundredths);
            np_puts(&o, num);
        } else {
            np_puts(&o, TR("Unknown"));
        }
    } else {
        const char *auth, *host;
        u = sba_url();
        auth = u;
        while (*auth && !(auth[0] == ':' && auth[1] == '/' && auth[2] == '/')) ++auth;
        auth = *auth ? auth + 3 : u;
        for (e = auth; *e && *e != '/'; ++e) {
        }
        for (host = at = auth; at < e; ++at)
            if (*at == '@') host = at + 1; /* userinfo is not shown */
        if (host == e) {
            np_puts(&o, TR("Unknown"));
        } else {
            for (at = u; at < auth; ++at) np_put(&o, *at);
            for (at = host; at < e; ++at) np_put(&o, *at);
        }
    }
    if (o.p >= o.end) return 0;
    *o.p = 0;
    return 1;
}

/* The width of w's text in its own font (0: no text, or it cannot be measured). */
static int np_tw(void *w) {
    const unsigned *t = widget_get_text(w);
    return t && *t ? m1_text_w(w, t) : 0;
}

/* A page y as a scroll_view's: its top and the content offset off taken off. */
static int np_cyo(int off, int y) { return y - NPI_TOP - off; }
static int np_cy(int y) { return np_cyo(np.si.off, y); }

/* w at x, page y, ww wide and as high as a px line plus NPI_PAD above and below; y is the text's top; the container is scrolled off. */
static void np_placeo(int off, void *w, int x, int y, int ww, int px) {
    widget_move(w, x, np_cyo(off, y) - NPI_PAD);
    widget_resize(w, ww, px + 2 * NPI_PAD);
}
static void np_place(void *w, int x, int y, int ww, int px) { np_placeo(np.si.off, w, x, y, ww, px); }

static void np_vis(void *w, int on) {
    if (w) widget_set_visible(w, on, 0); /* all of ours are insensitive in the asset */
}

/* The cover bitmap of the header view: resident, drawn here (never decoded in the paint). */
static int np_on_info_art(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (np.win) mb_art_paint_at(&np.ia, canvas, 0, 0);
    return RET_OK;
}

/* The header's places in a container scrolled off: the cover view, title, second title line, artist and album/third line (w points at the cover; the title has the whole column). */
static void np_head_place(void *const *w, int off) {
    widget_move(w[0], NPI_X, np_cyo(off, NPI_ART_Y));
    np_placeo(off, w[1], NPI_TEXT_X, NPI_TITLE_Y, NPI_TEXT_W, NPI_TITLE_PX);
    np_placeo(off, w[2], NPI_TEXT_X, NPI_TITLE_Y + NPI_TITLE_LH, NPI_TEXT_W, NPI_TITLE_PX);
    np_vis(w[2], np.tsh != 0);
    np_placeo(off, w[3], NPI_TEXT_X, NPI_ARTIST_Y + np.tsh, NPI_TEXT_W, NPI_META_PX);
    np_placeo(off, w[4], NPI_TEXT_X, NPI_ALBUM_Y + np.tsh, NPI_TEXT_W, NPI_META_PX);
}

/* The header's texts in a container (w as np_head_place's): the title in one or two lines, returning the second line's shift, the artist and the third line cut to the column. */
static int np_head_text(void *const *w, const char *title, const char *artist, const char *third) {
    int sh = m1_wrap2(w[1], w[2], title, NPI_TEXT_W) ? NPI_TITLE_LH : 0;
    m1_fit(w[3], artist, NPI_TEXT_W);
    m1_fit(w[4], third, NPI_TEXT_W);
    return sh;
}

/* 1: the info page is bare (spoken audio with the notes page, whose header is the same): no header, the rows from NPI_BARE_Y. */
static int np_bare(void) { return np.spoken && np.nok; }

/* The info page's header shown, or hidden while the page is bare (hidden widgets are insensitive in the asset). */
static void np_ihead_vis(void) {
    int on = !np_bare();
    np_vis(np.iw[NI_ART], on);
    np_vis(np.iw[NI_TITLE], on);
    np_vis(np.iw[NI_TITLE2], on && np.tsh);
    np_vis(np.iw[NI_ARTIST], on);
    np_vis(np.iw[NI_ALBUM], on);
}

/* Both headers' covers painted again (the bitmap or its settle changed). */
static void np_art_inval(void) {
    widget_invalidate_force(np.iw[NI_ART], (void *)0);
    if (np.nok) widget_invalidate_force(np.nw[NN_ART], (void *)0);
}

/* The playing track's episode entry (pc_ep_of) and, for spoken audio, the notes page's text: .notes' line of its guid (pno_read, the show folder's file), else the entry's description; "" for a book part or an episode with neither.
 * The files are read here, once per track change (np_header); the text and the layout's heap block live while spoken audio plays. */
static void np_ep_load(const char *path) {
    memset(&np.ep, 0, sizeof np.ep);
    free(np.ntext);
    np.ntext = (char *)0;
    if (pc_is_path(path)) pc_ep_of(path, &np.ep);
    if (!np.spoken || !np.nok) {
        free(np.npd);
        np.npd = (pd_t *)0;
        return;
    }
    np.ntext = calloc(PF_NOTE + 1, 1);
    if (!np.npd) np.npd = calloc(1, sizeof *np.npd);
    if (np.ntext && pc_is_path(path)) {
        char f[PC_FILE * 3 + 24];
        const char *q, *name = path;
        unsigned dl;
        for (q = path; *q; ++q)
            if (*q == '/') name = q + 1;
        dl = (unsigned)(name - path);
        if (np.ep.guid && dl + 8 < sizeof f) {
            memcpy(f, path, dl);
            memcpy(f + dl, ".notes", 7);
            pno_read(f, np.ep.guid, np.ntext, PF_NOTE + 1);
        }
        if (!np.ntext[0]) snprintf(np.ntext, PF_NOTE + 1, "%s", np.ep.desc);
    }
}

/* The notes page's moving parts at the scroll offset np.sn.off: the header, the hairline under it, the hint. The body is painted (np_on_notes_paint) at that offset. */
static void np_notes_place(void) {
    int hy = NPI_ROW_Y + np.tsh;
    np_head_place(np.nw + NN_ART, np.sn.off);
    widget_move(np.nw[NN_HAIR], NPI_X, np_cyo(np.sn.off, hy));
    np_placeo(np.sn.off, np.nw[NN_HINT], NPI_X, np.nby, PD_W, NPI_META_PX);
    widget_invalidate_force(np.nw[NN_BODY], (void *)0);
}

/* The notes laid out for the header as it is now (np.tsh): the text wrapped once from the body label's own advances (pd_paras: the episode page's wrapper, pitch and paragraph air), the content's height, the hint when there is no
 * text. The offset stays inside the new height. Called when the track changes and on the relay ticks, never per tick; no allocation of its own. */
static void np_notes_layout(void) {
    int end;
    if (!np.nok) return;
    np.nby = NPI_ROW_Y + np.tsh + NPN_GAP;
    end = np.nby;
    if (np.npd) { /* the advances are measured again: the body's style may have resolved since the last layout (same widget) */
        np.npd->nl = 0;
        np.npd->cache_st = (void *)0;
    }
    if (np.npd && np.ntext && np.ntext[0]) end = pd_paras(np.npd, np.nw[NN_BODY], np.ntext, np.nby);
    if (np.npd && np.npd->nl > 0) {
        np_vis(np.nw[NN_HINT], 0);
    } else {
        m1_fit(np.nw[NN_HINT], TR("No description"), PD_W);
        np_vis(np.nw[NN_HINT], 1);
        end = np.nby + PD_PITCH;
    }
    np.sn.h = end + NPN_GAP - NPI_TOP < NPI_VIEW_H ? NPI_VIEW_H : end + NPN_GAP - NPI_TOP;
    widget_set_prop_int(np.nw[NN_SCROLL], "virtual_h", np.sn.h);
    if (np.sn.off > np.sn.h - NPI_VIEW_H) np.sn.off = np.sn.h - NPI_VIEW_H;
    np_notes_place();
}

/* The notes page's scroll offset set to off px (0 the top, at most np.sn.h - NPI_VIEW_H): the notes' side of np_scroll. */
__attribute__((noinline)) void np_notes_scroll(int off) {
    int max = np.sn.h - NPI_VIEW_H;
    if (!np.nok) return;
    np.sn.off = off > max ? max : off;
    if (np.sn.off < 0) np.sn.off = 0;
    np_notes_place();
}

/* The notes page shown in the lyrics page's place while spoken audio plays, the lyrics page standing down (ly_standdown, patch/lyrics.c), and back for music. */
static void np_notes_sync(void) {
    int on = np.nok && np.spoken;
    if (on == np.non) return;
    np.non = on;
    widget_set_visible(np.nw[NN_SCROLL], on, 0);
    widget_set_sensitive(np.nw[NN_SCROLL], on);
    widget_set_visible(np.nw[NN_SCRIM], on, 0);
    ly_standdown(on);
}

/* The notes page's painted body: the wrapped lines of np.npd that lie wholly inside the view (AWTK does not clip a text), in the body label's style, at the scroll offset. Never reads a file. */
static int np_on_notes_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int k;
    (void)ctx;
    if (!canvas || !np.win || !np.npd || np.npd->nl <= 0) return RET_OK;
    widget_prepare_text_style(np.nw[NN_BODY], canvas);
    for (k = 0; k < np.npd->nl; ++k) {
        int y = np.npd->dy[k] - NPI_TOP - np.sn.off - NPI_PAD, rect[4];
        if (y + NPI_META_PX + 2 * NPI_PAD <= 0) continue;
        if (y + NPI_META_PX + 2 * NPI_PAD > NPI_VIEW_H) break;
        if (y < 0 || np.npd->dl[k].len <= 0) continue;
        rect[0] = NPI_X, rect[1] = y, rect[2] = PD_W, rect[3] = NPI_META_PX + 2 * NPI_PAD;
        canvas_draw_text_in_rect(canvas, np.npd->text + np.npd->dl[k].start, (unsigned)np.npd->dl[k].len, rect);
    }
    return RET_OK;
}

/* The header: the playing record's title, artist and album, its cover; the badge of a Hi-Res or DSD track (the cassette theme's rule: tape_badge) is np_flow's, on the Format row. For spoken audio the notes page's header
 * and notes are laid out with it. New text and cover only when the track changed (mb_track_key) or the layout is redone; the episode's files are read only when the track changed. */
static unsigned np_header(int force) {
    void *t = cc_playing();
    const char *title, *path;
    char tb[200], ab[200], cb[200];
    unsigned key = t ? mb_track_key(t) : 0;
    int badge = t ? tape_badge(t) : 0;
    if (!np.ihead) return key;
    if (key == np.ikey && badge == np.ibadge && !force) {
        if (t && np.ia.settle > 0 && mb_art_settle(&np.ia, np.win, t)) np_art_inval();
        return key;
    }
    title = t ? cc_str(t, REC_TITLE) : "";
    if (t && !*title) title = cc_str(t, REC_NAME);
    np_cut(tb, sizeof tb, title);
    np_cut(ab, sizeof ab, t ? cc_str(t, REC_ARTIST) : "");
    np_cut(cb, sizeof cb, t ? cc_str(t, REC_ALBUM) : "");
    path = t ? cc_str(t, REC_PATH) : "";
    np.spoken = t && pc_spoken_path(path);
    if (key != np.epkey) np.epkey = key, np_ep_load(path);
    if (t && pc_is_path(path)) { /* an episode: its date and length (the show is the artist line already) */
        char d[40], l[24];
        d[0] = l[0] = 0;
        if (np.ep.pub) pc_when(np.ep.pub, (unsigned)time((long *)0), d, sizeof d);
        if (np.ep.dur) pc_len_text(l, sizeof l, np.ep.dur);
        snprintf(cb, sizeof cb, "%s%s%s", d, d[0] && l[0] ? " \xc2\xb7 " : "", l);
    }
    np.tsh = np_head_text(np.iw + NI_ART, tb, ab, cb); /* the title in one or two lines */
    np_head_place(np.iw + NI_ART, np.si.off);
    np_ihead_vis();
    if (np.nok && np.spoken) {
        np_head_text(np.nw + NN_ART, tb, ab, cb);
        np_vis(np.nw[NN_TITLE], 1);
        np_vis(np.nw[NN_ARTIST], 1);
        np_vis(np.nw[NN_ALBUM], 1);
        np_notes_layout();
    }
    np.fdirty = 1; /* the badge */
    if (key != np.ikey || !np.ia.bmp) {
        if (t)
            mb_art_cover(&np.ia, np.win, t, 1);
        else
            mb_art_free(&np.ia);
    }
    np.ikey = key, np.ibadge = badge;
    np_art_inval();
    return key;
}

/* The rows 0..3 of stock's quality line "FLAC|44.1kHz|16bit|1021kbps" (the first four fields): out[f] the field's text with the unit after a space ("44.1 kHz", the format as it is), "" for a field with no value (or a
 * zero one, bit depth or rate the player did not know). Returns how many rows have a text. */
static int np_qparse(const char *s, char out[4][32]) {
    static const char *const unit[4] = {"", "kHz", "bit", "kbps"};
    int n = 0, f, last = 0;
    const char *p = s;
    for (f = 0; f < 4; ++f) out[f][0] = 0;
    for (f = 0; f < 4 && !last; ++f) {
        const char *b = p, *e = p;
        unsigned ul = f == 3 ? 4 : f ? 3 : 0, len, nz = 0, k;
        while (*e && *e != '|') ++e;
        last = !*e;
        p = last ? e : e + 1;
        while (b < e && *b == ' ') ++b;
        while (e > b && e[-1] == ' ') --e;
        if (ul && (unsigned)(e - b) >= ul && np_starts(e - ul, unit[f])) {
            e -= ul;
            while (e > b && (e[-1] == ' ' || e[-1] == '-')) --e;
        }
        len = (unsigned)(e - b);
        for (k = 0; k < len; ++k)
            if (b[k] != '0' && b[k] != '.') nz = 1;
        if (!len || (f && !nz)) continue;
        if (len > 23) len = 23;
        memcpy(out[f], b, len);
        out[f][len] = 0;
        if (f) {
            out[f][len] = ' ';
            np_cut(out[f] + len + 1, 6, unit[f]);
        }
        ++n;
    }
    return n;
}

/* The Location v in w1 and w2 (the second line), room px wide each; np.locn lines. 1: one line when it fits. 2: else broken after the last '/' that fits line 1, when the rest fits line 2. 3: else at the last character
 * that fits line 1, when the rest fits line 2. 4: else line 2 is the end (as much as fits) and line 1 is "..." and what fits just before it. Only the last M1_FIT_TAIL bytes are looked at (rule 4 at once when it is
 * longer). tools/mod_nowplaying.py loc_wrap is the model. */
static void np_loc_fit(void *w1, void *w2, const char *v, int room) {
    char l[M1_FIT_TAIL + 8];
    unsigned len = 0, lo, hi, m, n1, b1, b2, cut;
    while (v[len]) ++len;
    cut = len > M1_FIT_TAIL;
    if (cut) {
        v += len - M1_FIT_TAIL;
        while (m1_utf8_cont(v, 0)) ++v;
        len = 0;
        while (v[len]) ++len;
    }
    np.locn = 1;
    if (!cut) {
        if (m1_text_wn(w1, 0, v, len) <= room) {
            widget_set_text_utf8(w1, v);
            return;
        }
        lo = 0, hi = len; /* the longest prefix that fits line 1 */
        while ((m = m1_utf8_mid(v, lo, hi)) < hi) {
            if (m1_text_wn(w1, 0, v, m) <= room)
                lo = m;
            else
                hi = m;
        }
        n1 = lo;
        np.locn = 2;
        for (m = n1; m > 0; --m) /* the last '/' inside the prefix: the break is after it */
            if (v[m - 1] == '/') {
                if (m1_text_wn(w1, 0, v + m, len - m) <= room) {
                    memcpy(l, v, m);
                    l[m] = 0;
                    widget_set_text_utf8(w1, l);
                    widget_set_text_utf8(w2, v + m);
                    return;
                }
                break;
            }
        if (n1 && m1_text_wn(w1, 0, v + n1, len - n1) <= room) {
            memcpy(l, v, n1);
            l[n1] = 0;
            widget_set_text_utf8(w1, l);
            widget_set_text_utf8(w2, v + n1);
            return;
        }
    }
    np.locn = 2;
    b2 = 0;
    if (m1_text_wn(w2, 0, v, len) > room) { /* the first start from which the end fits line 2 */
        lo = 0, hi = len;
        while ((m = m1_utf8_mid(v, lo, hi)) < hi) {
            if (m1_text_wn(w2, 0, v + m, len - m) <= room)
                hi = m;
            else
                lo = m;
        }
        b2 = hi;
    }
    b1 = 0;
    if (m1_text_wn(w1, 1, v, b2) > room) { /* the first start from which "..." and the text up to b2 fit line 1 */
        lo = 0, hi = b2;
        while ((m = m1_utf8_mid(v, lo, hi)) < hi) {
            if (m1_text_wn(w1, 1, v + m, b2 - m) <= room)
                hi = m;
            else
                lo = m;
        }
        b1 = hi;
    }
    l[0] = l[1] = l[2] = '.';
    memcpy(l + 3, v + b1, b2 - b1);
    l[3 + b2 - b1] = 0;
    widget_set_text_utf8(w1, l);
    widget_set_text_utf8(w2, v + b2);
}

/* Row r shows ours (own) or nothing of ours (rows 4..7: stock's label of it, never both visible). */
static void np_row_own(int r, int own) {
    void *s = r >= 4 ? np.info[r - 2] : (void *)0;
    if (((np.rown >> r & 1) != 0) == own) return;
    np.rown ^= 1u << r;
    np.fdirty = 1;
    np_vis(np.iw[NI_KEY + r], own);
    np_vis(np.iw[NI_VAL + r], own);
    if (r == NPI_LOC_ROW && !own) np_vis(np.iw[NI_VAL + NPI_ROWS], 0);
    if (!s) return;
    widget_set_visible(s, !own, 0);
    if (own) widget_set_sensitive(s, 0);
}

/* Row r's label and value texts, measured; np_flow places them. A value is right aligned in what its label leaves, the Location's path (np_loc_fit) is under its label. alt (or 0): the text for a value that does
 * not fit whole. */
static void np_set_row(int r, const char *key, const char *val, const char *alt) {
    void *k = np.iw[NI_KEY + r], *w = np.iw[NI_VAL + r];
    int room;
    widget_set_text_utf8(k, key);
    np.rkw[r] = np_tw(k);
    if (r == NPI_LOC_ROW) {
        np_loc_fit(w, np.iw[NI_VAL + NPI_ROWS], val, NPI_R - NPI_X);
    } else {
        room = NPI_R - NPI_X - np.rkw[r] - NPI_KEY_GAP;
        if (room < 0) room = 0;
        np.rvx[r] = NPI_R - room;
        np.rvw[r] = room;
        if (alt && m1_text_wn(w, 0, val, (unsigned)strlen(val)) > room) val = alt; /* the shorter text, whole */
        m1_fit(w, val, room);
        if (r == 0) np.fmtw = np_tw(w);
    }
    np_row_own(r, 1);
    np.fdirty = 1;
}

/* The rows' places, from the top (NPI_ROW_Y under the header, NPI_BARE_Y on a bare page): a hairline above each row that shows (but a bare page's first), its label and value NPI_ROW_TEXT under it, the next row NPI_ROW_PITCH on; the Location's path under its label in np.locn lines; the badge on the
 * Format row, NPI_BADGE_GAP left of the value's text. The content's end sets the scroll_view's virtual_h. Everything is placed by np_cy, so the same call moves it all to a new content offset. */
static void np_flow(void) {
    int bare = np_bare(), r, y = bare ? NPI_BARE_Y : NPI_ROW_Y + np.tsh, end = y, badge = np.ibadge, bx = 0, by = 0;
    int bw = badge == 2 ? NPI_BADGE_DSD_W : badge == 1 ? NPI_BADGE_HIRES_W : 0;
    np.fdirty = 0;
    for (r = 0; r < NPI_ROWS; ++r) {
        void *h = np.iw[NI_HAIR + r];
        int on = np.rown >> r & 1;
        np_vis(h, on && !bare); /* bare: the first shown row has no hairline (bare is cleared below) */
        if (!on) continue;
        bare = 0;
        widget_move(h, NPI_X, np_cy(y));
        widget_resize(h, NPI_R - NPI_X, 1);
        np_place(np.iw[NI_KEY + r], NPI_X, y + NPI_ROW_TEXT, np.rkw[r] + 4, NPI_ROW_PX);
        if (r == NPI_LOC_ROW) {
            np_place(np.iw[NI_VAL + r], NPI_X, y + NPI_LOC_Y, NPI_R - NPI_X, NPI_ROW_PX);
            np_vis(np.iw[NI_VAL + NPI_ROWS], np.locn > 1);
            if (np.locn > 1)
                np_place(np.iw[NI_VAL + NPI_ROWS], NPI_X, y + NPI_LOC_Y + NPI_LOC_LH, NPI_R - NPI_X, NPI_ROW_PX);
            end = y + NPI_LOC_Y + (np.locn - 1) * NPI_LOC_LH + NPI_ROW_PX + NPI_FOOT;
        } else {
            np_place(np.iw[NI_VAL + r], np.rvx[r], y + NPI_ROW_TEXT, np.rvw[r], NPI_ROW_PX);
            if (!r) bx = NPI_R - np.fmtw - NPI_BADGE_GAP - bw, by = y + NPI_ROW_TEXT + (NPI_ROW_PX - NPI_BADGE_H) / 2;
            y += NPI_ROW_PITCH;
            end = y;
        }
    }
    if (!(np.rown & 1) || bx < NPI_X + np.rkw[0] + 4) bw = 0;
    np_vis(np.iw[NI_HIRES], bw && badge == 1);
    np_vis(np.iw[NI_DSD], bw && badge == 2);
    if (bw) {
        void *img = np.iw[badge == 2 ? NI_DSD : NI_HIRES];
        widget_move(img, bx, np_cy(by));
        widget_resize(img, bw, NPI_BADGE_H);
    }
    np.si.h = end - NPI_TOP < NPI_VIEW_H ? NPI_VIEW_H : end - NPI_TOP;
    widget_set_prop_int(np.iw[NI_SCROLL], "virtual_h", np.si.h);
}

/* The content's scroll offset set to off px (0 the top, at most np.si.h - NPI_VIEW_H) and every child of np_i_scroll moved to it: the one place a scroll goes through. */
__attribute__((noinline)) void np_info_scroll(int off) {
    int max = np.si.h - NPI_VIEW_H;
    if (!np.irow || !np.ihead) return;
    np.si.off = off > max ? max : off;
    if (np.si.off < 0) np.si.off = 0;
    np_head_place(np.iw + NI_ART, np.si.off);
    np_ihead_vis();
    np_flow();
}

/* The container a listener's ctx (its scroll_view) belongs to, 0 for none. */
static np_scr_t *np_scr_of(void *ctx) {
    if (!ctx) return (np_scr_t *)0;
    return ctx == np.si.w ? &np.si : ctx == np.sn.w ? &np.sn : (np_scr_t *)0;
}

/* The one place a scroll of either container goes through. */
static void np_scroll_to(np_scr_t *s, int off) {
    if (s == &np.si)
        np_info_scroll(off);
    else
        np_notes_scroll(off);
}

/* DOWN, MOVE, UP and ABORT of np_i_scroll and np_n_scroll (listeners, as the lyrics page's). A vertical drag of NPI_TAP_PX or more scrolls the content with the finger; a sideways one is the slide view's page swipe, and a tap
 * does nothing. Once the drag is vertical every MOVE of it answers RET_STOP, so the slide view gets an ABORT in its place (widget_on_pointer_move @0x6716f8) and turns no page however far the finger drifts sideways. */
static int np_on_info_touch(void *ctx, void *e) {
    int type, x, y;
    np_scr_t *s = np_scr_of(ctx);
    if (!e || !np.win || !s) return RET_OK;
    type = *(int *)e;
    x = *(int *)((char *)e + PE_X), y = *(int *)((char *)e + PE_Y);
    if (type == EVT_POINTER_DOWN) {
        s->td = 1, s->tm = 0, s->tsx = x, s->tsy = y, s->tly = y;
    } else if (type == EVT_POINTER_MOVE && s->td) {
        if (!s->tm) {
            if (m1_abs(y - s->tsy) >= NPI_TAP_PX && m1_abs(y - s->tsy) > m1_abs(x - s->tsx))
                s->tm = 1, s->tly = y;
            else if (m1_abs(x - s->tsx) >= NPI_TAP_PX)
                s->td = 0; /* sideways: the slide view's */
        } else {
            np_scroll_to(s, s->off - (y - s->tly));
            s->tly = y;
        }
        if (s->tm) return RET_STOP;
    } else if (type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) {
        s->td = 0;
    }
    return RET_OK;
}

/* One row y of the view (0 its top) painted in the page's colour with alpha a: the window's tone under np_scrim (the scrim's alpha at that row, the model's scrim_alpha) and under the black gradient (m1_shade). */
static void np_fade_row(void *canvas, int y, unsigned a) {
    int row = NPI_TOP + y, sy = row - NP_SCRIM_Y, d = sy < NP_SCRIM_H - 1 - sy ? sy : NP_SCRIM_H - 1 - sy;
    unsigned sa = d <= 0               ? 0
                  : d >= NP_SCRIM_EDGE ? NP_SCRIM_ALPHA
                                       : (unsigned)(NP_SCRIM_ALPHA * d / NP_SCRIM_EDGE),
             keep = 255 - sa, c = np.color;
    c = (c & 255) * keep / 255 | (c >> 8 & 255) * keep / 255 << 8 | (c >> 16 & 255) * keep / 255 << 16;
    ui_fill_color(canvas, m1_shade(c, (unsigned)row, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H) | a << 24);
    canvas_fill_rect(canvas, 0, y, NPI_X + NPI_R, 1);
}

/* The scroll_view's EVT_AFTER_PAINT (over its children): the top NPI_FADE rows fade into the page's colour while the content is scrolled (offset over 0), the bottom ones while there is more under the view. A linear
 * ramp, opaque at the edge. No decode or allocation: at most 2 x NPI_FADE one-row fills. */
static int np_on_info_fade(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    np_scr_t *s = np_scr_of(ctx);
    int k, top, bot;
    if (!s || !canvas || !np.win) return RET_OK;
    top = s->off > 0, bot = s->off < s->h - NPI_VIEW_H;
    if (!top && !bot) return RET_OK;
    for (k = 0; k < NPI_FADE; ++k) {
        unsigned a = 255u * (unsigned)(2 * (NPI_FADE - k) - 1) / (2 * NPI_FADE);
        if (top) np_fade_row(canvas, k, a);
        if (bot) np_fade_row(canvas, NPI_VIEW_H - 1 - k, a);
    }
    return RET_OK;
}

/* The page dots share the middle of the times row with the track position (label_index, np_index). With the middle free the dots show; while
 * the position shows there, the dots take its place for NP_DOTS_MS after a page change and hand it back: each fades over NP_DOTS_FADE_MS,
 * the other at 255 - the dots' opacity. */
static void np_dots_set(int op) {
    if (op == np.dop || !np.dots) return; /* (a page without the dots leaves the position alone) */
    np.dop = op;
    widget_set_opacity(np.dots, op), widget_invalidate_force(np.dots, (void *)0);
    if (np.idx) widget_set_opacity(np.idx, 255 - op), widget_invalidate_force(np.idx, (void *)0);
}

/* The dots' opacity el ms after a page change, from np.dfrom: in over NP_DOTS_FADE_MS, held, out over NP_DOTS_FADE_MS from NP_DOTS_MS. */
static int np_dots_at(int el) {
    if (el < NP_DOTS_FADE_MS) return np.dfrom + (255 - np.dfrom) * el / NP_DOTS_FADE_MS;
    if (el < NP_DOTS_MS) return 255;
    if (el < NP_DOTS_MS + NP_DOTS_FADE_MS) return 255 - 255 * (el - NP_DOTS_MS) / NP_DOTS_FADE_MS;
    return 0;
}

static int np_dots_frame(const void *timer) {
    int el;
    (void)timer;
    if (!np.win || !np.dtimer) return RET_OK;
    el = (int)(time_now_ms() - np.dt0);
    np_dots_set(np.idxn ? np_dots_at(el) : 255); /* the position went away meanwhile: the dots stay */
    if (np.idxn && el < NP_DOTS_MS + NP_DOTS_FADE_MS) return RET_REPEAT;
    np.dtimer = 0; /* RET_OK ends this timer */
    return RET_OK;
}

/* Each tick, after np_index: the dots with the middle free, the position without a page change's fade running. */
static void np_dots_sync(void) {
    if (!np.dtimer) np_dots_set(np.idxn ? 0 : 255);
}

/* The slide view's page changed: the dots come in over the position (a second change restarts the hold from where the fade is). */
static void np_dots_flash(void) {
    if (!np.dots || !np.idxn) return;
    np.dfrom = np.dop;
    np.dt0 = time_now_ms();
    if (!np.dtimer) np.dtimer = timer_add(np_dots_frame, (void *)0, NP_FRAME_MS);
    if (!np.dtimer) np_dots_set(0);
}

/* The slide view left the info page or the notes page: its content is at the top when the page comes back. */
static void np_page_reset(void) {
    if (np.si.off && np.sv && widget_get_prop_int(np.sv, "value", NPI_PAGE) != NPI_PAGE) np_info_scroll(0);
    if (np.sn.off && np.sv && widget_get_prop_int(np.sv, "value", NPN_PAGE) != NPN_PAGE) np_notes_scroll(0);
}

static int np_on_page(void *ctx, void *e) {
    (void)e;
    if (np.win && ctx == np.sv) np_page_reset(), np_dots_flash();
    return RET_OK;
}

/* The Sample Rate of a track the player converts to the rate out its output is kept at (Crossfade,
 * docs/modules/crossfade.md), from stock's value v ("44.1 kHz"): full "44.1 \xe2\x86\x92 96 kHz", and alt "\xe2\x86\x92 96 kHz" for a
 * row whose label leaves no room for both. 0 (nothing written) when out is 0 or the track's own rate. */
static int np_resampled(const char *v, int out, char full[48], char alt[24]) {
    char o[16];
    unsigned n, vl = 0;
    if (!out || !v[0]) return 0;
    n = (unsigned)snprintf(o, sizeof o, "%d.%03d", out / 1000, out % 1000);
    while (o[n - 1] == '0') --n;
    if (o[n - 1] == '.') --n;
    snprintf(o + n, sizeof o - n, " kHz");
    if (!strcmp(v, o)) return 0;
    while (v[vl]) ++vl;
    if (vl > 4 && !strcmp(v + vl - 4, " kHz")) vl -= 4;
    if (vl > 23) vl = 23;
    memcpy(full, v, vl);
    snprintf(full + vl, 48 - vl, " \xe2\x86\x92 %s", o);
    snprintf(alt, 24, "\xe2\x86\x92 %s", o);
    return 1;
}

/* The quality line. Stock rewrites label_info with the compact text on every page tick, so it stays the data source: hidden and insensitive while rows 0..3 (Format, Sample Rate, Bit Depth, Bitrate) show, laid out
 * when its text changes; a field it has no value for leaves its row out. A page without them, an unreadable text or one with no field gives the line back to label_info (never a stale line). */
static void np_quality(int force) {
    char s[NP_INFO_BUF], q[4][32], full[48], alt[24];
    unsigned h;
    int need, f, out, conv;
    if (!np.irow || !np.info[0]) return;
    need = m1_text_utf8(np.info[0], s, sizeof s);
    if (need > 0 && (unsigned)need < sizeof s) { /* else none, empty or cut short */
        out = xfade_out_rate();
        h = np_hash(s) ^ (unsigned)out * 2654435761u;
        if (h == np.qdone && np.qown && !force) return;
        if (np_qparse(s, q)) {
            conv = np_resampled(q[1], out, full, alt);
            for (f = 0; f < 4; ++f) {
                if (q[f][0])
                    np_set_row(f,
                               TR(f == 0   ? "Format"
                                  : f == 1 ? "Sample Rate"
                                  : f == 2 ? "Bit Depth"
                                           : "Bitrate"),
                               f == 1 && conv ? full : q[f], f == 1 && conv ? alt : 0);
                else
                    np_row_own(f, 0);
            }
            np.qdone = h;
            if (!np.qown) {
                np.qown = 1;
                widget_set_visible(np.info[0], 0, 0);
                widget_set_sensitive(np.info[0], 0);
            }
            return;
        }
    }
    if (np.qown) {
        for (f = 0; f < 4; ++f) np_row_own(f, 0);
        widget_set_visible(np.info[0], 1, 0);
    }
    np.qown = 0;
    np.qdone = 0;
}

/* Stock's line i (2 Genre, 3 Year, 4 File Size, 5 Location, "Label:value") as row i + 2. 0 when the text is not "Label:value". */
static int np_row(int i, const char *s) {
    char out[NP_INFO_BUF + 64], key[64], val[NP_INFO_BUF + 8];
    const char *line = np_stream_text(i, s, out, sizeof out) ? out : s, *v = np_after_colon(line), *c;
    unsigned kl;
    if (!v) return 0;
    if (i == 5) {
        for (c = line; *c != ':'; ++c) {
        }
        kl = (unsigned)(c - line) < sizeof key - 1 ? (unsigned)(c - line) : (unsigned)sizeof key - 1;
        memcpy(key, line, kl);
        key[kl] = 0;
    } else {
        np_cut(key, sizeof key, TR(i == 2 ? "Genre" : i == 3 ? "Year" : "File Size"));
    }
    if (!key[0]) return 0;
    if (i == 4)
        np_size_text(v, val, sizeof val);
    else
        np_cut(val, sizeof val, v);
    np_set_row(i + 2, key, val, 0);
    return 1;
}

static void np_info(void) {
    char s[NP_INFO_BUF];
    unsigned i, h;
    int force = np.relay > 0;
    if (force) --np.relay;
    unsigned key;
    np_page_reset();
    key = np_header(force);
    if (key != np.rkey) {
        force = 1, np.rkey = key; /* a new track: its rows again (a stream's stock text is the same for every record) */
        if (np.si.off) np_info_scroll(0); /* and the page at the top */
        if (np.sn.off) np_notes_scroll(0);
    }
    np_notes_sync();
    np_quality(force);
    if (!np.irow) return;
    for (i = 2; i < NP_INFO_N; ++i) {
        int need;
        if (i < 4 && np.info[i]) { /* Genre and Year: nothing of spoken audio's; stock's label of them is hidden too */
            if (np.spoken) {
                np_row_own((int)i + 2, 0);
                widget_set_visible(np.info[i], 0, 0);
                np.done[i] = 0, np.shid |= 1u << i;
                continue;
            }
            if (np.shid >> i & 1) np.shid &= ~(1u << i), widget_set_visible(np.info[i], 1, 0), force = 1;
        }
        need = np.info[i] ? m1_text_utf8(np.info[i], s, sizeof s) : -1;
        /* none, empty, or too long for s (cut short): stock's label */
        if (need <= 0 || (unsigned)need >= sizeof s) {
            np_row_own((int)i + 2, 0);
            np.done[i] = 0;
            continue;
        }
        h = np_hash(s);
        if (h == np.done[i] && !force) continue; /* the text we last laid out */
        np.done[i] = h;
        if (!np_row((int)i, s)) np_row_own((int)i + 2, 0);
    }
    if (np.fdirty) np_flow();
    if (np.si.off > np.si.h - NPI_VIEW_H) np_info_scroll(np.si.off); /* the content got shorter */
}

/* The favourite button of an episode is a bookmark (docs/modules/podcasts.md "Saved"): stock's star toggles myfav and sets btn_imgfav_style / btn_imgunfav_style (its click handler at once, show_player_face on a
 * track change); while the playing path is an episode the button's style is mapped to btn_imgsave_style / btn_imgunsave_style (the same icons, a bookmark, in the page theme), and back for music. Stock sets its style
 * only when the name differs from the one it wants, so the swap lasts until stock's next fill; our click handler (run after stock's) and the tick put it back. */
static int np_is_server(void *rec) { return rec && sba_rec_track(*(int *)((char *)rec + REC_ID))[0] != 0; }

/* The playing server track's favourite (1 starred), read from the cache through the source (nd_row on the queue record: the album's cache file, or the Favorites list) when the track or sba_gen
 * differs from the last read, or fresh is set; else the last answer. A star moves the cache first and sba_gen when the server answers, so a refusal puts the star back by itself. */
static int np_server_fav(void *rec, int fresh) {
    int id = *(int *)((char *)rec + REC_ID);
    unsigned gen = sba_gen();
    if (fresh || np.favrec != id || np.favgen != gen) {
        ls_row_t x;
        lib_nd.row(&lib_nd, rec, &x);
        np.favrec = id, np.favgen = gen, np.favv = x.fav;
    }
    return np.favv;
}

static void np_fav_sync(void) {
    const char *cur, *want = (const char *)0;
    void *rec;
    int ep;
    if (!np.fav) return;
    cur = *(const char *const *)((char *)np.fav + WIDGET_STYLE);
    if (!cur) return;
    rec = cc_playing();
    if (np_is_server(
            rec)) { /* a server track (streamed or downloaded): the star shows the server's favourite, not stock's myfav (which has no row for it) */
        want = np_server_fav(rec, 0) ? "btn_imgfav_style" : "btn_imgunfav_style";
        if (strcmp(cur, want)) {
            widget_use_style(np.fav, want);
            widget_set_prop_str(np.fav, "style:pressed:icon", "np_unfav_down");
        }
        return;
    }
    ep = rec && pc_is_path(cc_str(rec, REC_PATH));
    if (ep) {
        if (!strcmp(cur, "btn_imgfav_style"))
            want = "btn_imgsave_style";
        else if (!strcmp(cur, "btn_imgunfav_style"))
            want = "btn_imgunsave_style";
    } else if (!strcmp(cur, "btn_imgsave_style"))
        want = "btn_imgfav_style";
    else if (!strcmp(cur, "btn_imgunsave_style"))
        want = "btn_imgunfav_style";
    if (want) {
        widget_use_style(np.fav, want);
        /* stock's inline pressed icon (the page sets np_unfav_down on the widget) is a star: the bookmark presses to its own outline */
        widget_set_prop_str(np.fav, "style:pressed:icon", ep ? "np_unsave_down" : "np_unfav_down");
    }
}

/* The star. A server track's goes to the server (ls_favorite: the row sheet's Favorite, with its toast) and RET_STOP keeps stock's handler away: it would write the stream record, whose address
 * carries the login token, into the local favourites table. Bound after the stock init, so it runs first. Every other track is stock's. */
static int np_on_fav(void *ctx, void *e) {
    void *rec = cc_playing();
    (void)ctx;
    (void)e;
    if (np_is_server(rec)) {
        ls_favorite(&lib_nd, rec, np_server_fav(rec, 1));
        np_server_fav(rec, 1);
        np_fav_sync();
        return RET_STOP;
    }
    np_fav_sync();
    return RET_OK;
}

/* The play mode button while an episode or an audiobook part plays is the speed button (docs/modules/nowplaying.md "Spoken audio controls"): it wears the page theme's btn_imgspeed<mode>_style
 * (the text 1x .. 2x) for stock's playspeed_mode, and a tap goes to the next speed. Stock sets the button's style itself (its click handler, the page's fill, stock_np_mode_button), so every tick
 * compares the name; back on music, stock_np_mode_button puts the play mode's picture back. A book plays its parts in order (bk_play sets List play), an episode queue too: the tap never reaches
 * stock's handler while the speed shows. */
static int np_speed_mode(void) {
    int mode = *(volatile int *)PLAYSPEED_MODE;
    return mode < 0 || mode >= PC_SPEEDS ? 0 : mode;
}

static void np_mode_sync(void) {
    static const char *const style[PC_SPEEDS] = {"btn_imgspeed0_style", "btn_imgspeed1_style", "btn_imgspeed2_style",
                                                 "btn_imgspeed3_style"};
    void *rec = cc_playing();
    const char *cur, *want;
    if (!np.mode) return;
    if (!rec || !pc_spoken_path(cc_str(rec, REC_PATH))) {
        if (np.speedon) stock_np_mode_button(np.win);
        np.speedon = 0;
        return;
    }
    cur = *(const char *const *)((char *)np.mode + WIDGET_STYLE);
    want = style[np_speed_mode()];
    if (!cur || strcmp(cur, want)) widget_use_style(np.mode, want);
    np.speedon = 1;
}

/* The next speed: the show's or the book's, saved (pc_speed_set) and put in the player (pc_speed_apply). The decoder takes a speed only when it starts, so a player that plays or is paused is restarted at
 * its place as stock's Multiple Speed handlers do (0x4799c8: save_stop_player, then save_start_player(1) when it was paused, else (0)). 0 when nothing spoken plays or the speed could not be saved (the toast is shown). */
int np_speed_step(void) {
    void *rec = cc_playing();
    const char *path;
    unsigned key;
    int st;
    if (!rec || !pc_spoken_path(cc_str(rec, REC_PATH))) return 0;
    path = cc_str(rec, REC_PATH);
    key = bk_is_path(path) ? bk_book_of(path) : pc_show_of(path);
    if (!key || !pc_speed_set(key, (np_speed_mode() + 1) % PC_SPEEDS)) {
        pod_toast(TR("Storage unavailable"));
        return 0;
    }
    pc_speed_apply(key);
    st = mclGetPlayStatus();
    if (st == MB_PLAYING || st == NP_PAUSED) {
        save_stop_player();
        save_start_player(mclGetSavePlayStatus() == NP_PAUSED);
    }
    return 1;
}

/* A tap on the speed button. */
static int np_on_mode(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!np.speedon || !cc_playing()) return RET_OK;
    np_speed_step();
    np_mode_sync();
    return RET_STOP;
}

/* The prev / next buttons while an episode or an audiobook part plays (docs/modules/nowplaying.md "Skip buttons"): they skip back NP_SKIP_BACK and forward NP_SKIP_FWD seconds in the track, as a
 * podcast player's do. The widgets, their slots and stock's handlers stay: np_skip_sync (each tick) puts the skip glyphs on the five states, and np_on_skip (bound after the stock init, so it runs
 * first) seeks with the stock seek_time and returns RET_STOP only while those glyphs show; music is stock's. The hardware keys still change track. */
#define NP_SKIP_BACK 15
#define NP_SKIP_FWD 30
#define NP_SKIP_END \
    5 /* a forward skip lands at most this far from the end: the track ends by playing, never by the tap */

static void np_skip_look(void *btn, const char *img, const char *down) {
    static const char *const state[5] = {"normal", "disable", "focused", "over", "pressed"};
    char name[40];
    int i;
    if (!btn) return;
    for (i = 0; i < 5; ++i) {
        snprintf(name, sizeof name, "style:%s:bg_image", state[i]);
        widget_set_prop_str(btn, name, i == 4 ? down : img);
    }
}

static void np_skip_sync(void) {
    void *rec = cc_playing();
    int on = rec && pc_spoken_path(cc_str(rec, REC_PATH));
    if (on == np.skipon || !np.prev || !np.next) return;
    np_skip_look(np.prev, on ? "np_back15" : "np_prev", on ? "np_back15_down" : "np_prev_down");
    np_skip_look(np.next, on ? "np_fwd30" : "np_next", on ? "np_fwd30_down" : "np_next_down");
    /* the queue button: a plain list, since the queue holds episodes or parts, not songs */
    np_skip_look(np.queue, on ? "np_playlist" : "np_playqueue", on ? "np_playlist_down" : "np_playqueue_down");
    np.skipon = on;
}

/* The skip: forward (NP_SKIP_FWD s on) or back (NP_SKIP_BACK s). A stopped player or one with no length yet takes no skip (seek_time does nothing when stopped): 0 then, 1 otherwise. */
int np_spoken_seek(int fwd) {
    int pos = 0, len = 0, to;
    if (get_playtimeandlength(&pos, &len) != 1 || len <= 0 || pos < 0) return 0;
    if (fwd) {
        to = pos + NP_SKIP_FWD;
        if (to > len - NP_SKIP_END) to = len - NP_SKIP_END;
        if (to <= pos) return 1; /* already in the last seconds */
    } else
        to = pos > NP_SKIP_BACK ? pos - NP_SKIP_BACK : 0;
    seek_time(to);
    return 1;
}

/* A tap on btn_prev (ctx 0) or btn_next (ctx 1); the tap is ours even when there is nothing to seek in. */
static int np_on_skip(void *ctx, void *e) {
    (void)e;
    if (!np.skipon) return RET_OK;
    if (np_spoken_seek(ctx != (void *)0)) np_time();
    return RET_STOP;
}

static void np_work_lit(void) {
    np_server_art();
    np_cover();
    np_time();
    np_index();
    np_dots_sync();
    np_info();
    ly_tick(); /* the lyrics page (patch/lyrics.c) */
    np_fav_sync();
    np_mode_sync();
    np_skip_sync();
}

static void np_work(void) {
    recent_note(cc_playing()); /* No stock list query: the page underneath owns pdeq_showlist;
                               * the menu's foreground handler resolves the cover key. */
    np_art_sync(
        np_art_live()); /* a pause seen with the screen dark or another page in front: the cover is just small */
    if (!m1_screen_lit()) return;
    np_work_lit();
}

/* Pause stock's 500 ms playing_page timer (0x53cf48 -> show_player_face) and title/artist hscroll_label 16 ms
 * marquees strictly while the screen is off, and resume synchronously before the panel lights up on wake
 * (patch/battery.c). Resuming on wake regardless of np.fg preserves stock's lit behaviour (including its stream
 * disconnect check while another page is in front) and avoids any TO_BG/TO_FG edge case stranding the timer. */
static void np_dark_set(int dark, int force_lit) {
    int vis;
    if (!np.win) return;
    if (dark) {
        if (np.dark) return;
        np.dark = 1;
        player_timer_clear(np.win);
        if (np.title) hscroll_label_stop(np.title);
        if (np.artist) hscroll_label_stop(np.artist);
        return;
    }
    if (!np.dark) return;
    np.dark = 0;
    vis = np.fg || m1_is_top(np.win);
    if (vis) show_player_face(np.win, 0);
    player_timer_start(np.win);
    if (np.title) hscroll_label_start(np.title);
    if (np.artist) hscroll_label_start(np.artist);
    if (force_lit && vis) {
        recent_note(cc_playing());
        np_work_lit();
    }
}

void np_on_dark(void) {
    if (!np.win) return;
    if (np.timer && np.interval != POD_DARK_MS && timer_modify(np.timer, POD_DARK_MS) == RET_OK)
        np.interval = POD_DARK_MS;
    np_dark_set(1, 0);
}

void np_on_wake(void) {
    if (!np.win) return;
    if (np.timer && np.interval != NP_TICK_MS && timer_modify(np.timer, NP_TICK_MS) == RET_OK) np.interval = NP_TICK_MS;
    np_dark_set(0, 1);
}

static int np_tick(const void *timer) {
    unsigned want;
    int lit;
    (void)timer;
    if (!np.win) return RET_OK; /* not ours any more: a timer that returns RET_OK ends */
    lit = m1_screen_lit();
    np_dark_set(!lit, 0);
    want = lit ? NP_TICK_MS : POD_DARK_MS;
    if (np.timer && np.interval != want && timer_modify(np.timer, want) == RET_OK) np.interval = want;
    /* another page on top: nothing of this one is seen, np_on_foreground catches up. A dialog (the pull-down) also clears np.fg
     * but leaves the page the top normal window and partly visible, so the work goes on under it. */
    if (!np_bar_sync() && np.barok && !np.fg) return RET_REPEAT;
    np_work();
    return RET_REPEAT;
}

/* The page is over (or replaced): the timer goes, the status bar is black again, the state is cleared. */
static void np_stop(void) {
    np_bar_black();
    ly_stop();
    free(np.ntext);
    free(np.npd);
    m1_timer_stop(&np.timer);
    m1_timer_stop(&np.anim);
    m1_timer_stop(&np.pchk);
    m1_timer_stop(&np.btimer);
    m1_timer_stop(&np.dtimer);
    if (np.sbmp) bitmap_destroy(np.sbmp);
    mb_art_free(&np.ia);
    memset(&np, 0, sizeof np);
}

static int np_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != np.win) return RET_OK; /* an earlier page's end: the new one keeps its state */
    np_stop();
    return RET_OK;
}

/* The progress bar thickens under the finger, as Apple Music's scrubber does: slider_play eases to NP_BAR_SCRUB px thick (centred in its 30 px target, so it grows both ways)
 * when a touch lands on it and back to NP_BAR when the touch ends, over NP_SCRUB_MS (an ease-in-out cubic, so neither end jumps; a frame every NP_FRAME_MS; a change mid-way turns round from the
 * thickness it has). Only its bar_size and corners change; the drag and the seek stay stock's slider and handlers. */
static void np_bar_set(int b) {
    static const char *const state[5] = {"normal", "disable", "focused", "over", "pressed"};
    char name[40];
    int i;
    if (b == np.bsz) return;
    np.bsz = b;
    widget_set_prop_int(np.slider, "bar_size", b);
    for (i = 0; i < 5; ++i) {
        snprintf(name, sizeof name, "style:%s:round_radius", state[i]);
        widget_set_prop_int(np.slider, name, b / 2 + 1);
    }
    widget_invalidate_force(np.slider, (void *)0);
}

/* The thickness el ms into an ease from `from` to `to`: 1 - (1 - t)^3 of the way, rounded. */
static int np_bar_ease(int from, int to, int el) {
    int p = el >= NP_SCRUB_MS ? 1024 : (el < 0 ? 0 : el) * 1024 / NP_SCRUB_MS, u = 2048 - 2 * p;
    int e = p < 512 ? 4 * p * p / 1024 * p / 1024 : 1024 - u * u / 1024 * u / 1024 / 2;
    return from + ((to - from) * e + (to > from ? 512 : -512)) / 1024;
}

static int np_bar_frame(const void *timer) {
    int el;
    (void)timer;
    if (!np.win || !np.btimer) return RET_OK;
    el = (int)(time_now_ms() - np.bt0);
    np_bar_set(np_bar_ease(np.bfrom, np.scrub ? NP_BAR_SCRUB : NP_BAR, el));
    if (el < NP_SCRUB_MS) return RET_REPEAT;
    np.btimer = 0; /* RET_OK ends this timer */
    return RET_OK;
}

/* on: the touch's start (1) or end (0); animate 0 (another window over the page) sets the thickness at once. No frame timer: at once too. */
static void np_scrub_look(int on, int animate) {
    if (!np.slider || (np.scrub == on && (animate || !np.btimer))) return;
    np.scrub = on;
    np.bfrom = np.bsz;
    np.bt0 = time_now_ms();
    if (animate && !np.btimer) np.btimer = timer_add(np_bar_frame, (void *)0, NP_FRAME_MS);
    if (animate && np.btimer) return;
    m1_timer_stop(&np.btimer);
    np_bar_set(on ? NP_BAR_SCRUB : NP_BAR);
}

/* slider_play's own pointer events (the _BEFORE copies reach its emitter first, whatever the slider answers; the slider holds the grab, so the release comes here too), and
 * its EVT_VALUE_CHANGING while dragged: the times follow the finger at once (np_time, np_scrub_pos), not on the next tick. Stock's handler, bound first, stops its timer
 * while dragging, so the value stays the finger's until the release seeks. */
static int np_on_scrub(void *ctx, void *e) {
    int type = e ? *(int *)e : 0;
    (void)ctx;
    if (!np.win) return RET_OK;
    if (type == EVT_POINTER_DOWN_BEFORE)
        np_scrub_look(1, 1);
    else if (type == EVT_POINTER_UP_BEFORE || type == EVT_POINTER_ABORT)
        np_scrub_look(0, 1);
    else if (type == EVT_VALUE_CHANGING && np.scrub)
        np_time();
    return RET_OK;
}

/* Another window came over the page (a page, a dialog, the pull-down): the bar is black while it covers. */
static int np_on_background(void *ctx, void *e) {
    (void)e;
    if (!np.win || ctx != np.win) return RET_OK;
    np_scrub_look(0, 0); /* a touch the new window took: the progress bar is thin again, at once */
    if (np.barok) np.fg = 0;
    np_bar_black();
    return RET_OK;
}

static int np_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!np.win || ctx != np.win) return RET_OK;
    np.relay = NP_RELAY; /* the info page is laid out again (a language or font change meanwhile) */
    np_info_scroll(0); /* and starts at the top */
    np_notes_scroll(0);
    ly_refresh(); /* a lyrics text size changed in Settings is laid out now */
    np.idxon = np_pos_setting(); /* so is the Track Position switch */
    np.shrinkon = np_shrink_setting(); /* and Shrink on Pause (np_work puts the cover at its size: fg is still 0) */
    np_work(); /* the page is current when it reappears (fg still 0: a new colour tints the bar once, below) */
    /* the mode button's picture follows the play mode: stock sets it only in its own click handler, so a mode set on the Queue page (or elsewhere) is shown now */
    stock_np_mode_button(ctx);
    np_mode_sync(); /* an episode's or a part's speed again */
    np.fg = 1;
    np_bar_apply();
    return RET_OK;
}

/* The touch and the fades of a scroll container sc (listeners with the widget as ctx: np_scr_of). */
static void np_scroll_listen(void *sc) {
    widget_on(sc, EVT_POINTER_DOWN, np_on_info_touch, sc);
    widget_on(sc, EVT_POINTER_MOVE, np_on_info_touch, sc);
    widget_on(sc, EVT_POINTER_UP, np_on_info_touch, sc);
    widget_on(sc, EVT_POINTER_ABORT, np_on_info_touch, sc);
    widget_on(sc, EVT_AFTER_PAINT, np_on_info_fade, sc);
}

static void np_start(void *win) {
    void *art;
    unsigned n;
    if (np.win) np_stop(); /* an earlier page that never said it was gone */
    np.win = win;
    np.rem = widget_lookup(win, "np_remaining", 1);
    np.tot = widget_lookup(win, "label_playlen", 1);
    np.el = widget_lookup(win, "np_elapsed", 1);
    np.pt = widget_lookup(win, "label_playtime", 1);
    np.title = widget_lookup(win, "scrlabel_title", 1);
    np.artist = widget_lookup(win, "scrlabel_artist", 1);
    np.fav = widget_lookup(win, "btn_fav", 1);
    if (np.fav) widget_on(np.fav, EVT_CLICK, np_on_fav, (void *)0);
    np.mode = widget_lookup(win, "btn_playmode", 1);
    np.prev = widget_lookup(win, "btn_prev", 1);
    np.next = widget_lookup(win, "btn_next", 1);
    if (np.prev && np.next) {
        widget_on(np.prev, EVT_CLICK, np_on_skip, (void *)0);
        widget_on(np.next, EVT_CLICK, np_on_skip, (void *)1);
    }
    np.queue = widget_lookup(win, "btn_queue", 1);
    if (np.mode) widget_on(np.mode, EVT_CLICK, np_on_mode, (void *)0);
    np.slider = widget_lookup(win, "slider_play", 1);
    np.bsz = NP_BAR; /* the asset's */
    if (np.slider) {
        widget_on(np.slider, EVT_POINTER_DOWN_BEFORE, np_on_scrub, (void *)0);
        widget_on(np.slider, EVT_POINTER_UP_BEFORE, np_on_scrub, (void *)0);
        widget_on(np.slider, EVT_POINTER_ABORT, np_on_scrub, (void *)0);
        widget_on(np.slider, EVT_VALUE_CHANGING, np_on_scrub, (void *)0);
    }
    if (!np.el || !np.pt) np.el = np.pt = (void *)0; /* only the pair is swapped */
    np.shown = np.eshown = -1;
    np.idx = widget_lookup(win, "label_index", 1);
    np.idxon = np_pos_setting();
    np.dots = widget_lookup(win, "slide_indicator", 1);
    np.dop = 255; /* the asset's: the dots and the (hidden) position both opaque */
    np.shrinkon = np_shrink_setting();
    for (n = 0; n < NP_INFO_N; ++n) np.info[n] = widget_lookup(win, np_info_names[n], 1);
    for (n = 0; n < NI_N; ++n) np.iw[n] = widget_lookup(win, np_iw_names[n], 1);
    np.ihead = np.iw[NI_ART] && np.iw[NI_TITLE] && np.iw[NI_TITLE2] && np.iw[NI_ARTIST] && np.iw[NI_ALBUM];
    np.irow = np.iw[NI_SCROLL] && np.iw[NI_VAL + NPI_ROWS] && np.iw[NI_HIRES] && np.iw[NI_DSD];
    for (n = 0; n < NPI_ROWS; ++n)
        if (!np.iw[NI_KEY + n] || !np.iw[NI_VAL + n] || !np.iw[NI_HAIR + n]) np.irow = 0;
    for (n = 0; n < NN_N; ++n) np.nw[n] = widget_lookup(win, np_nw_names[n], 1);
    np.nok = np.ihead;
    for (n = 0; n < NN_N; ++n)
        if (!np.nw[n]) np.nok = 0;
    np.relay = NP_RELAY;
    np.color = NP_NEUTRAL & 0xffffff; /* the asset's window colour */
    if (!widget_on(win, EVT_DESTROY, np_on_destroy, win)) {
        memset(&np, 0, sizeof np);
        return;
    }
    np.timer = timer_add(np_tick, (void *)0, NP_TICK_MS);
    np.interval = NP_TICK_MS;
    if (!np.timer) { /* the page stays stock; the destroy handler finds no window of ours any more */
        memset(&np, 0, sizeof np);
        return;
    }
    art = widget_lookup(win, "img_playcover", 1);
    if (art) {
        np.art = art;
        np.asz = NP_ART;
        np.shadow = widget_lookup(win, "img_np_shadow", 1);
        np_corner_init();
        widget_on(art, EVT_AFTER_PAINT, np_on_art_paint, (void *)0);
        m1_bind(win, "btn_play", np_on_play, (void *)0); /* before stock's handler: np_play_check sees its change */
    }
    m1_bind(win, "btn_queue", np_on_queue, (void *)0);
    np.sv = widget_lookup(win, "slide_view",
                          1); /* its page: the cover springs only while the art page shows; the info page's reset */
    if (np.sv)
        widget_on(np.sv, EVT_VALUE_CHANGED, np_on_page, np.sv); /* the scroll resets and the dots (np_dots_flash) */
    ly_start(win);
    np.si.w = np.iw[NI_SCROLL];
    if (np.irow && np.ihead) np_scroll_listen(np.si.w); /* the content's touch and fades */
    if (np.nok) {
        np.sn.w = np.nw[NN_SCROLL];
        np_scroll_listen(np.sn.w);
        widget_on(np.nw[NN_BODY], EVT_AFTER_PAINT, np_on_notes_paint, (void *)0);
        widget_on(np.nw[NN_ART], EVT_AFTER_PAINT, np_on_info_art, (void *)0);
    }
    if (np.ihead) {
        mb_art_size(&np.ia, NPI_ART, NPI_ART_R);
        widget_on(np.iw[NI_ART], EVT_AFTER_PAINT, np_on_info_art, (void *)0);
        if (np.info[1]) { /* label_album: the header shows the record's album */
            widget_set_visible(np.info[1], 0, 0);
            widget_set_sensitive(np.info[1], 0);
        }
    }
    np_art_sync(0); /* opened while paused: the cover starts small */
    np.fg = 1;
    np.barok = widget_on(win, EVT_WINDOW_TO_BG, np_on_background, win) &&
               widget_on(win, EVT_WINDOW_TO_FG, np_on_foreground, win);
    np_bar_apply(); /* the asset's tone until the cover's is known */
    np_work();
}

/* The hook (tools/pod.py PLAYING_INIT): stock first, then ours. */
int m1plus_playing_init(void *win, void *ctx) {
    int ret = stock_playing_init_trampoline(win, ctx);
    if (ret == RET_OK && win) np_start(win);
    return ret;
}
