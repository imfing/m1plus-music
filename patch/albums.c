/* M1+ Music Albums: the library's albums as a grid of covers or as a list, two modes of one page.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_albums.bin: the navbar (Back, "Albums", Cover Flow, the mode toggle, Now Playing) over a stock list, list_view >
 * scroll_view (albums_scrollview), exactly the structure of the library lists, whose ONE child is a custom view, view_grid, that paints the
 * albums itself in its own EVT_AFTER_PAINT, as the Recently Played shelf of the menu does (patch/recent.c). There is no widget per album: a
 * library of any size costs the album deque (the stock list, copied as Cover Flow copies it) and a small ring of decoded covers. The stock
 * scroll_view does the scrolling: the drag, the fling and its animation, the catch of a coasting list (patch/scroll.c), the clamp.
 *
 *   grid mode  GRID_COLS (2) columns of GRID_COVER (144) px covers, GRID_GAP px apart, a one-line album and a
 *              one-line artist under each (two text styles taken from the hidden labels label_grid_title and
 *              label_grid_sub); (patch/offsets.inc); row r starts GRID_ROW_GAP + r * PITCH px down the content.
 *   list mode  LIST_ROW_H px rows: a LIST_ART px cover, the album and the artist (two sizes and colours, taken
 *              from two hidden labels of the page, label_row_title and label_row_sub, with
 *              widget_prepare_text_style), a hairline under each row, the row under the finger filled LIST_PRESS.
 *   content    view_grid is as high as the whole content (grid: GRID_ROW_GAP + rows * PITCH, list: count * LIST_ROW_H) and the scroll_view's
 *              virtual_h is set to match (the list_view layouter sums its children's heights into it too); the scroll_view shows it through its
 *              GRID_VIEW_H window at yoffset. The paint moves the canvas origin down by yoffset, so what it draws is in window coordinates (the
 *              top of the window is 0) and only what intersects [0, GRID_VIEW_H) is drawn: a cover with canvas_draw_image (clipped by hand to
 *              the window; the scroll_view also sets the canvas clip to its rectangle), text with canvas_draw_text_in_rect, cut at the window's
 *              edges by that clip.
 *   tiles      GRID_TILES (12) entries. A tile is the album's cover reduced from the Cover Flow cache file (168 px,
 *              box filter) to the mode's cover size (the finished bitmap is kept, not the JPEG). PAINT NEVER DECODES:
 *              it draws the resident tiles and the placeholder for the rest. A page-owned timer (al_on_load, armed
 *              when the view moves or a mode starts, ended when nothing is left to load, removed with the page)
 *              decodes ONE cover per 16 ms tick: the missing cell nearest the middle of the view first (the cells in
 *              view before any other), then the next AL_AHEAD rows in the scroll direction. A tile in that window
 *              is never replaced; the rest of the ring (at least two tiles) is the history, least recently used
 *              replaced, so a reversal finds what it just left. Texts are converted to wide chars with the tile's
 *              record and cut to their width with an ellipsis (measured with the canvas' own font, in the text's own
 *              style) the first time they are drawn.
 *              The loader decodes nothing while the scroll_view is moving (a finger dragging it, or its scroll animator running): a decode
 *              is a few ms on the UI thread and the next touch would wait behind it. Meanwhile it only polls (a compare per tick), and the
 *              scroll events (EVT_SCROLL, the scroll end) re-arm it.
 *              Memory: GRID_TILES (12) bitmaps of at most GRID_COVER^2 * 4 (81 KB) plus one for the placeholder
 *              = 1.08 MB, whatever the library; a decode also holds the 168 px source (113 KB) for its duration.
 *   art        the cover cache (patch/covercache.c); a missing or empty cache file shows the stock placeholder disc
 *              (p_default). Missing files are built in the background by the shared worker (see "The background cache
 *              build" below); the tiles that found no file try again as the worker advances.
 *   touch      the scroll_view's: a drag scrolls, a release flings, a touch on a coasting list stops it and presses nothing. The content view
 *              only sees the pointer events the scroll_view passes on, as the shelf does: DOWN remembers the cell or row under the finger (the
 *              list mode fills the row LIST_PRESS), ABORT (the scroll_view took the gesture as a drag) forgets it, and a release closer than
 *              AL_TAP_PX (the scroll_view's own drag threshold) to the press on both axes, on the same cell or row, opens the stock album
 *              page as Cover Flow does (cc_open_album). Coordinates go through widget_to_local, which includes the scroll offset.
 *
 * An artist's or composer's page opens with the header instead of the large title: the artist's circle (an artist's only; a composer's header never has one) (AL_PHOTO_D px, made by the loader's first tick, patch/artistphoto.c), the
 * name under it (al_name) and the pills under that; al_top() is where the rows start (docs/modules/albums.md "Scoped to an artist"). An artist with no photo in the cache has the same header without the circle
 * (no placeholder): the name and the pills PH_SHIFT higher, the rows with them. When the page opens it asks the cover worker to look at this artist again (al_recheck, after the page's own cover build); a photo
 * found or removed switches the circle in place (al_layout).
 *
 * The navbar is Cover Flow, "..." and Now Playing; the "..." card (patch/viewsort.c) searches (Search Albums; not on a scoped page), sorts (Title, Artist, Recently Added, Year: cc_album_order, saved in
 * ALBUMS_SORT_FILE) and switches the mode. The switch is in place (no window opens or closes): the tiles are dropped, the
 * content is resized and the scroll keeps the first album in view, and the choice is persisted
 * (ALBUMS_FILE, written as the Start-in setting is). The menu's Albums row opens the page in the saved mode; if
 * the page cannot open it falls back to the stock Albums list through the Home dispatcher. No stock function is
 * hooked; everything runs from this page's widgets and timers.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "viewsort.h"
#include "search.h"
#include "songops.h"
#include "nextalbum.h"
#include "artistphoto.h"

extern int coverflow_open(void); /* patch/coverflow.c: the menu's Cover Flow row, opened over this page */
extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */
extern int coverflow_artist(void *artists, unsigned index,
                            unsigned scope); /* patch/coverflow.c: Cover Flow scoped to an artist */
/* patch/songs.c: our Songs page on all the artist's (or composer's: scope CLASS_COMPOSERS) songs; -1 when it did not open */
extern int songs_open_artist(void *artist, unsigned scope);
extern void *songs_artist_list(
    void *artist,
    unsigned
        scope); /* patch/songs.c: the artist's (or composer's) songs through the stock queries (no page); NULL when there is no All songs row */
extern int songs_play_artist(
    void *artist, unsigned scope,
    int how); /* patch/songs.c: Play (SO_IN_ORDER) / Shuffle (SO_SHUFFLE) on the artist's (or composer's) songs; -1 when nothing plays */
extern int
coverflow_artist_albums(void *artist_row, unsigned scope, int keep_card, void **albums,
                        unsigned **keys); /* patch/coverflow.c: one artist's album rows and their cache keys */

#define CELL_H GRID_CELL_H /* the cell geometry is the grid's (patch/grid.h), shared with the Recently Played shelf */
#define PITCH GRID_PITCH
#define AL_W \
    320 /* the content's width: the list_view's (its layouter gives a child a mobile scroll bar's list the full width; the scroll_view clips at 310, the covers end at 308) */
#define AL_MORE_MS 16 /* the loader's tick */
#define AL_TAP_PX \
    SC_DRAG_PX /* a release closer than this to the press on both axes is a tap (from there the scroll_view drags) */
#define AL_AHEAD (al.list ? 2 : 1) /* rows loaded beyond the view in the scroll direction */
/* the most cells a frame can touch: (view + cell) / pitch + 1 rows of GRID_COLS; the ring must hold them, the next
 * row in the scroll direction and leave two tiles of history */
#if GRID_TILES < GRID_COLS * ((GRID_VIEW_H + CELL_H) / PITCH + 2 + 1) + 2
#error GRID_TILES cannot hold the visible cells, the next row and the history
#endif
#if GRID_TILES < (GRID_VIEW_H / LIST_ROW_H) + 2 + 2 + 2
#error GRID_TILES cannot hold the visible rows, the next two and the history
#endif

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

typedef grid_tile_t tile_t; /* the grid's tile (patch/grid.h) */

static struct {
    void *win, *view, *sv, *status, *btn; /* btn: the "..." button */
    void *st_title, *st_sub; /* hidden labels whose styles are the list's two text styles */
    void *st_gtitle, *st_gsub; /* and the grid's two */
    void *albums; /* our copy of the stock album rows */
    /* scoped to one artist or composer (albums_open_artist), else all NULL / 0: artist_row is a deque holding a copy of the stock row,
     * scope its list class, keys the albums' cache keys (the library albums' of the same names; NULL: each album keys itself) */
    void *artist_row;
    unsigned scope, *keys;
    unsigned *
        order; /* display order as stock row numbers (cc_album_order, Settings > Library > Album Order); NULL = stock order */
    unsigned count;
    int list; /* 1 list mode, 0 grid */
    int press; /* list: the row under the finger, + 1 */
    int seen; /* the scroll offset the loader last looked at (the direction is read from its change) */
    int dir; /* the way the content last went: 1 down the list, -1 back up */
    int noscroll; /* the scroll events could not be registered: the loader keeps polling for as long as the page is up */
    int down, down_x, down_y; /* the cell or row a press began on, + 1 (0 none), and where (screen coordinates) */
    unsigned more_timer; /* the loader's */
    /* the background cache build (the shared worker, patch/covercache.c): build_timer is the one-shot start, then the poll;
     * own = this page holds the worker's job set; done = the worker's done counter at the last poll */
    unsigned build_timer;
    int own, done;
    void *fade; /* the navbar's fade (img_nb_fade, optional): shown only while the list is scrolled */
    void *small,
        *big; /* label_title (the navbar's small title) and al_title (the large one, the first thing in the content); either may be missing */
    int title_on; /* the small title is shown (the large one has scrolled away, or the scroll events are missing) */
    /* the scan that queues the missing albums runs in AL_SCAN_BATCH steps on build_timer: scanning = a scan is under
     * way (own set held, worker not started); scan_cur / scan_centre = the cc_build_near_step cursor and the album it
     * is centred on; scanned = a finished scan found nothing missing (kept until the page closes: al is cleared on open) */
    int scanning, scanned;
    unsigned scan_cur, scan_centre;
    int fg;
    int sort,
        rev; /* the order shown (cc_sort_mode: CC_SORT_*) and its direction (cc_sort_rev: 1 = Z-A, Oldest First) */
    vs_t vs; /* the "..." card */
    /* an artist's or composer's page under the name: the Play and Shuffle pills (pills: both widgets exist) and each album's year
     * (cc_album_years of the artist's songs, one entry per stock row, 0 = none; NULL: no years); the library's page has neither */
    void *btn_play, *btn_shuffle;
    int pills;
    unsigned *years;
    /* an artist's or composer's page with the name header (head: pills, and the asset's al_name label; a composer never has a photo): the circle (hdr: the photo, else the placeholder; made by the loader, hdr_done once tried)
     * and the name under it (name_lbl) replace the large title (al_title hidden) */
    int head, hdr_done;
    void *name_lbl, *hdr;
    az_t
        az; /* the list mode's sections, rail and pinned header (patch/azlist.c; az.nsec 0: a plain list: the scoped page, a grid) */
    int az_ok; /* the page's rail, bubble and header text styles were found: the list may have sections */
    /* circ: the artist has a photo in the cache, so the circle is drawn and the name and pills are PH_SHIFT lower; without it the same header (name, pills, rows) is PH_SHIFT higher (the circle's room is gone, nothing else differs).
     * rk: the re-check of this artist (patch/artistphoto.c ap_recheck) 0 not made, 1 running on the page's set, 2 done; rk_ep: ap_epoch() when it started */
    int circ, rk;
    unsigned rk_ep;
    grid_t
        g; /* the tile ring (GRID_TILES, heap), the placeholder, the mode's cover size (g.side): patch/grid.c; LAST (test/pod/albums.py reads the fields above by index) */
} al __attribute__((section(".scratch")));

/* The room of the circle, when the artist page has none (no photo): everything under it is this much higher. */
static int al_gone(void) { return al.circ ? 0 : PH_SHIFT; }

/* Hidden and out of the hit test together (this AWTK's widget_find_target ignores visible). */
static void al_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int al_rows(void) { return ((int)al.count + GRID_COLS - 1) / GRID_COLS; }
/* The content starts with the large title (the Songs and Artists pages' block); the rows, or the grid's first gap, follow it. An artist's page has the pills
 * under the title: the block ends at AL_PILLS_END and the list's first row is GRID_ROW_GAP under it (the grid's first gap is its own). */
static int al_top(void) {
    int end = al.head ? AL_HEAD_END - al_gone() : AL_PILLS_END;
    return !al.pills ? SG_TITLE_H : al.list ? end + GRID_ROW_GAP : end;
}
/* The list's content is the az_t's (its top is al_top(), al_size keeps it; the section headers between the rows when the Title order has them). */
static int al_content(void) {
    return al.list ? az_rows_end(&al.az) : al_top() + (al_rows() ? GRID_ROW_GAP + al_rows() * PITCH : 0);
}
/* The section header's height the list mode has above its first row now: 0 in the grid, in a plain list and with Section Headers off. */
static int al_hh(void) { return al.list && al.az.nsec ? al.az.hdr_h : 0; }
static int al_max_scroll(void) {
    int m = al_content() - GRID_VIEW_H;
    return m > 0 ? m : 0;
}

/* The scroll_view's offset: px down the content that the top of the window is. */
static int al_off(void) { return al.sv ? I(al.sv, SC_YOFF) : 0; }

/* The same offset measured from the top of the rows (negative while the title block is in view). */
static int al_coff(void) { return al_off() - al_top(); }

/* The navbar's fade (an insensitive image, built hidden) is for rows passing under the bar: shown while the list is scrolled, hidden at rest, where the
 * first row would be darkened by it. Visible and sensitive move together (never a touch target). No fade widget = nothing happens. The small title
 * is the navbar's once the large one has scrolled away (pod_title_gone, the rule every large-title page shares); without the scroll events it stays. */
static void al_fade(void) {
    pod_title_set(al.small, &al.title_on,
                  al.noscroll || pod_title_gone(al_off(), al.head ? AL_HEAD_COLLAPSE - al_gone() : 0));
    if (!al.fade) return;
    widget_set_visible(al.fade, al_off() > 0, 0);
    widget_set_sensitive(al.fade, 0);
}

/* The persisted mode: "1" the grid, "0" the list, anything else ALBUMS_DEFAULT_GRID. */
static int al_use_grid(void) {
    int c = set_read(ALBUMS_FILE, 0);
    return c == '1' ? 1 : c == '0' ? 0 : ALBUMS_DEFAULT_GRID;
}

/* The window repaints (the scroll_view's rectangle: the content view itself is as high as the library). */
static void al_redraw(void) { widget_invalidate_force(al.sv, (void *)0); }

/* ---------------------------------------------------------------------------
 * Tiles
 */

/* The first grid row that touches the view, or the row of scroll offset s. */
static int al_row_of(int s) { return s > GRID_ROW_GAP + CELL_H ? (s - GRID_ROW_GAP - CELL_H) / PITCH + 1 : 0; }

/* The rows (grid rows, or list rows = albums) that touch the view: [*r0, *r1], r1 < r0 for none. The offset is outside
 * [0, max] while a drag pulls the list past an end (the stock scroll_view's overscroll, the gap above the first row): the
 * rows are kept inside [0, n - 1], never a row before the first (album -1 read past the album list and crashed the app). */
static void al_span(int *r0, int *r1) {
    int n = al.list ? (int)al.count : al_rows(), s = al_coff();
    if (al.list)
        az_span(&al.az, r0, r1);
    else
        *r0 = al_row_of(s), *r1 = (s + GRID_VIEW_H - GRID_ROW_GAP + PITCH - 1) / PITCH - 1;
    if (*r0 < 0) *r0 = 0;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The albums [*lo, *hi] the tiles are kept for: those in view and AL_AHEAD rows beyond them in the scroll direction. */
static void al_window(int *lo, int *hi) {
    int per = al.list ? 1 : GRID_COLS, n = al.list ? (int)al.count : al_rows(), r0, r1;
    al_span(&r0, &r1);
    if (al.dir < 0)
        r0 -= AL_AHEAD;
    else
        r1 += AL_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > n - 1) r1 = n - 1;
    *lo = r0 * per;
    *hi = (r1 + 1) * per - 1;
    if (*hi > (int)al.count - 1) *hi = (int)al.count - 1;
}

/* The scoped list's stock "All songs" row (kept as the last tile with two albums or more). */
static int al_is_card(void *rec) { return al.artist_row && rec && I(rec, REC_ID) == ID_ALL_SONGS; }

/* The tile that holds album a, or NULL. */
static tile_t *al_find(int a) { return grid_find(&al.g, a); }

/* The tile of album a: the one it has, else a free one, else the least recently used one outside the window (the
 * window is never replaced: it holds the cells in view and the ones about to be). A new tile gets its texts and cover key. */
static tile_t *al_tile(int a) {
    int lo, hi, fresh;
    tile_t *t;
    al_window(&lo, &hi);
    t = grid_tile(&al.g, a, lo, hi, &fresh);
    if (fresh) {
        void *rec = cc_row(al.albums, al.order, (unsigned)a);
        unsigned row = al.order ? al.order[a] : (unsigned)a; /* (keys and years are by stock row) */
        if (al_is_card(
                rec)) /* All Songs over the artist: no cover file (key 0), the placeholder; an artist's page has no line under it */
            grid_set(t, TR("local_allsong"), "", 0);
        else if (
            al.artist_row) { /* an artist's or composer's album: its year as the grey line, none when no song of it has one */
            char year[5];
            unsigned y = al.years ? al.years[row] : 0;
            year[0] = y ? (char)('0' + y / 1000) : 0, year[1] = (char)('0' + y / 100 % 10),
            year[2] = (char)('0' + y / 10 % 10), year[3] = (char)('0' + y % 10), year[4] = 0;
            grid_set(t, cc_str(rec, REC_ALBUM), year, al.keys ? al.keys[row] : cc_album_key(rec));
        } else
            grid_set(t, cc_str(rec, REC_ALBUM), cc_str(rec, REC_ARTIST), al.keys ? al.keys[row] : cc_album_key(rec));
    }
    return t;
}

/* The cover from the cache file, reduced to the mode's size with the box filter. */
static void al_art(tile_t *t) { grid_art(&al.g, t); }

/* ---------------------------------------------------------------------------
 * Paint (the cell paint is the grid's, patch/grid.c; the list mode's rows are this page's own)
 */

static tile_t *al_tile(int a);
static tile_t *al_tile_of(void *ctx, int a) {
    (void)ctx;
    return al_tile(a);
}

static void al_paint_grid(void *canvas) {
    int r0, r1, last;
    al_span(&r0, &r1);
    if (r1 < r0) return;
    last = (r1 + 1) * GRID_COLS;
    if (last > (int)al.count) last = (int)al.count;
    grid_paint(canvas, &al.g, r0 * GRID_COLS, last, GRID_ROW_GAP - al_coff(), GRID_VIEW_H, al_tile_of, (void *)0);
}

static void al_paint_list(void *canvas) {
    int r0, r1;
    al_span(&r0, &r1);
    grid_list_paint(canvas, &al.g, al.st_title, al.st_sub, r0, r1, al_off(), GRID_VIEW_H, al.press, 0, 1, al_tile_of,
                    (void *)0); /* patch/grid.c */
    az_paint_heads(&al.az, canvas); /* the section letters, then over everything the pinned band and its letter */
}

/* The artist's circle (AL_PHOTO_D px at AL_PHOTO_X, AL_PHOTO_Y in the content; the loader made it): the part inside the window. */
static void al_paint_head(void *canvas) {
    int y = AL_PHOTO_Y - al_off(), top = y < 0 ? -y : 0,
        bottom = y + AL_PHOTO_D > GRID_VIEW_H ? GRID_VIEW_H - y : AL_PHOTO_D;
    int src[4], dst[4];
    if (!al.hdr || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = AL_PHOTO_D, src[3] = bottom - top;
    dst[0] = AL_PHOTO_X, dst[1] = y + top, dst[2] = AL_PHOTO_D, dst[3] = bottom - top;
    canvas_draw_image(canvas, al.hdr, src, dst);
}

/* The view's own EVT_AFTER_PAINT: the visible cells or rows and nothing else. It draws what is resident and the placeholder for the rest; it
 * decodes nothing and arms no timer (al_on_load does that). The canvas origin is the content view's, which the scroll_view has moved up by
 * yoffset: it is moved back down by that for the duration of the paint (what canvas_translate does, CANVAS_OY), so the window's top is 0. */
static int al_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = al_off();
    (void)ctx;
    if (!canvas || !al.view || !al.g.tiles || !al.count) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    if (al.circ) al_paint_head(canvas);
    if (al.list)
        al_paint_list(canvas);
    else
        al_paint_grid(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The loader: one cover per tick on the page's own timer
 */
static int al_abs(int v) { return v < 0 ? -v : v; }

/* The album to decode next, or -1: of the window's albums without a tile that was tried, the cell nearest the middle
 * of the view, the cells in view before the rest (the window is the view and the rows ahead). */
static int al_next_load(void) {
    int lo, hi, a,
        best = -1, bd = 0x7fffffff,
        s = al.list ? al_off() : al_coff(); /* (the list's rows are placed by the az_t: from the content's top) */
    if (!al.g.tiles || !al.count) return -1;
    al_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        tile_t *t = al_find(a);
        int top, h, d;
        if (t && t->art) continue;
        if (al.list)
            top = az_row_y(&al.az, a) - s, h = LIST_ROW_H;
        else
            top = GRID_ROW_GAP + a / GRID_COLS * PITCH - s, h = CELL_H;
        d = al_abs(top + h / 2 - GRID_VIEW_H / 2);
        if (top >= GRID_VIEW_H || top + h <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int al_on_load(const void *unused);
static int al_first(void);
static void al_layout(int circ);
_Static_assert(PH_SHIFT == AL_PHOTO_Y + AL_PHOTO_D && AL_HEAD_END - PH_SHIFT == AL_PILLS_END &&
                   AL_HEAD_PILL_Y - PH_SHIFT == SG_PILL_Y,
               "the artist header without a circle is the one with it, PH_SHIFT higher");

/* Is there a photo for this artist now: a non-empty -168 file of its key (or of the lead artist's)? */
static int al_has_photo(void) {
    char url[80];
    int st = ap_lookup(cc_str(deque_at(al.artist_row, 0), REC_TITLE), AP_HEAD, url);
    return st == AP_PHOTO || st == AP_LEAD;
}

/* The header's circle, once: the artist's -168 photo (or the lead artist's, ap_lookup) cut to a circle. A photo that does not decode leaves the plain page. */
static void al_head_load(void) {
    char url[80];
    unsigned *px;
    void *b;
    int st = ap_lookup(cc_str(deque_at(al.artist_row, 0), REC_TITLE), AP_HEAD, url);
    al.hdr_done = 1;
    if (st == AP_PHOTO || st == AP_LEAD) {
        b = ap_bitmap(AL_PHOTO_D, &px);
        if (b) {
            int ok = cc_decode(al.win, url, 1, AL_PHOTO_D, 1, px);
            if (ok) ap_circle(px, AL_PHOTO_D);
            bitmap_unlock_buffer(b);
            if (ok) {
                al.hdr = b;
                return;
            }
            bitmap_destroy(b);
        }
    }
    al_layout(0);
}

/* The scroll_view is moving: a finger is dragging it (pressed and past the drag threshold), or its scroll animator (the fling) is running.
 * A decode is a few ms on the UI thread and the next touch would wait behind it, so the loader decodes nothing meanwhile: the rows show the
 * placeholder disc. (scroll_view_t pressed / dragged / wa and the animator's state and widget: patch/scroll.c reads the same.) */
static int al_moving(void) { return grid_moving(al.sv); }

/* Arms the loader if there is something to load and it is not running. */
static void al_kick(void) {
    if (al.fg && !al.more_timer && al.view && (al.noscroll || (al.circ && !al.hdr_done) || al_next_load() >= 0))
        al.more_timer = timer_add(al_on_load, (void *)0, AL_MORE_MS);
}

/* The way the content went since the loader last looked. */
static void al_dir(void) {
    int s = al_off();
    if (s != al.seen) al.dir = s > al.seen ? 1 : -1;
    al.seen = s;
}

static int al_on_load(const void *unused) {
    int a;
    (void)unused;
    al.more_timer = 0;
    if (!al.view || !al.fg) return RET_OK;
    al_dir();
    if (al_moving()) { /* nothing is decoded while it moves: look again next tick (the polling ends with the page, or when nothing is left to load) */
        al_kick();
        return RET_OK;
    }
    if (al.circ && !al.hdr_done) { /* the header's circle first (it is the first thing in view) */
        al_head_load();
        al_redraw();
        al_kick();
        return RET_OK;
    }
    a = al_next_load();
    if (a >= 0) {
        tile_t *t = al_tile(a);
        int top = al.list ? az_row_y(&al.az, a) - al_off() : GRID_ROW_GAP + a / GRID_COLS * PITCH - al_coff();
        al_art(t);
        if (top < GRID_VIEW_H && top + (al.list ? LIST_ROW_H : CELL_H) > 0) al_redraw();
    }
    al_kick();
    return RET_OK;
}

/* The scroll_view's EVT_SCROLL (every change of its offset: the drag, the fling, a scroll_to) and its scroll end: the direction is read and the
 * loader armed. */
static int al_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!al.view) return RET_OK;
    al_fade();
    al_dir();
    al_kick();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The background cache build. Albums with no cache file (neither a picture nor the "no art" marker) are built by the
 * shared worker thread (patch/covercache.c) while the page is up: no Preparing screen, the grid shows the placeholder
 * disc until a cover's file appears. The jobs are the albums nearest the first one in view first. A one-shot timer
 * starts it a moment after the page is up (the scan stats every album's file, so it is not part of opening); a poll
 * every AL_BUILD_MS then watches the worker's done counter and, when it advanced, lets the tiles that found no file try
 * again (al_retry); the loader (al_kick) decodes them one per tick as before. One worker at a time app-wide: when
 * Cover Flow (or another page) holds it, nothing is started. Cancelled and joined when the page goes (or Cover Flow opens).
 */
#define AL_BUILD_START_MS 50
#define AL_BUILD_MS 500
#define AL_SCAN_BATCH 64 /* albums stat'ed per scan step */
#define AL_SCAN_MS 20 /* between steps: input is served in between */

/* The tiles that were shown as the placeholder for want of a cache file, and whose file exists now, try again. */
static void al_retry(void) {
    char url[80];
    int i, any = 0;
    for (i = 0; al.g.tiles && i < GRID_TILES; ++i) {
        tile_t *t = &al.g.tiles[i];
        if (t->album && t->art == 2 && cc_url(url, t->ckey)) t->art = 0, any = 1;
    }
    if (any) al_kick();
}

static int al_on_build(const void *unused);
static void al_recheck(void);
static void al_recheck_done(void);

/* The page's build set released: a running worker is cancelled (joined if it has finished, else left to exit on its own, cc_build_stop). */
static void al_build_end(void) {
    if (al.build_timer) timer_remove(al.build_timer);
    al.build_timer = 0;
    if (al.own) cc_build_stop();
    al.own = 0;
    al.scanning = 0;
    if (al.rk == 1) al.rk = 0; /* (a re-check cut short is asked for again) */
}

static int al_on_build(const void *unused) {
    int done;
    (void)unused;
    al.build_timer = 0;
    if (!al.view || !al.own) return RET_OK;
    done = cc_build_done();
    if (done != al.done) al.done = done, al_retry();
    if (done >= cc_build_total()) {
        int rk = al.rk == 1;
        al_build_end();
        if (rk)
            al.rk = 2, al_recheck_done();
        else
            al_recheck(); /* the cover build is over: this artist's photo is looked at */
        return RET_OK;
    }
    al.build_timer = timer_add(al_on_build, (void *)0, AL_BUILD_MS);
    if (!al.build_timer) al_build_end(); /* no way to watch it: stop, the covers built so far stay */
    return RET_OK;
}

/* The scan in steps: the first call (the one-shot AL_BUILD_START_MS) opens the set, every call considers AL_SCAN_BATCH
 * albums (nearest the first one in view first, as cc_build_near) and, while more remains, re-arms itself AL_SCAN_MS
 * later so input is served between steps. The worker starts only after the last step: it never reads a job being written. */
static int al_on_build_start(const void *unused) {
    (void)unused;
    al.build_timer = 0;
    if (!al.view || !al.count) return RET_OK;
    if (!al.scanning) {
        if (al.own || al.scanned) return RET_OK;
        if (!cc_build_open(al.count, CC_MISSING)) {
            if (cc_build_orphan()) /* a worker stopped by the page before is still inside a job: ask again shortly */
                al.build_timer = timer_add(al_on_build_start, (void *)0, AL_BUILD_MS);
            return RET_OK;
        }
        al.own = al.scanning = 1;
        al.scan_cur = 0, al.scan_centre = (unsigned)al_first();
    }
    if (!cc_build_near_step(al.albums, al.order, al.keys, al.scan_centre, &al.scan_cur, AL_SCAN_BATCH)) {
        al.build_timer = timer_add(al_on_build_start, (void *)0, AL_SCAN_MS);
        if (!al.build_timer) al_build_end(); /* no way to continue: nothing built, the next foreground retries */
        return RET_OK;
    }
    al.scanning = 0;
    if (!cc_build_total())
        al.scanned = 1; /* everything has its file or marker: no more scans until the page is opened again */
    if (!cc_build_start()) { /* nothing missing, no card, no space, no thread: the set is already freed */
        al.own = 0;
        al_recheck();
        return RET_OK;
    }
    al.done = 0;
    al.build_timer = timer_add(al_on_build, (void *)0, AL_BUILD_MS);
    if (!al.build_timer) al_build_end();
    return RET_OK;
}

/* Starts the build a moment from now unless one is going or already due. */
static void al_build_later(void) {
    if (al.view && al.g.tiles && !al.own && !al.scanned && !al.build_timer)
        al.build_timer = timer_add(al_on_build_start, (void *)0, AL_BUILD_START_MS);
}

static int al_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    al.fg = 1;
    al_kick();
    al_build_later();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch (the pointer events the scroll_view passes down to the content view)
 */

/* The grid album under content point (x, y), or -1 for a gap, the margins and the empty tail of the last row. */
static int al_cell_at(int x, int y) {
    y -= al_top(); /* (the title block above the grid is no cell) */
    if (y < 0 || y >= al_content() - al_top()) return -1;
    return grid_cell_at(x, y, GRID_ROW_GAP, (int)al.count);
}

/* The list album under content point y, or -1 below the last row. */
static int al_row_at(int y) { return az_at(&al.az, y); /* -1 for a header, the air below and above */ }

/* The album under the pointer event: its screen position into the content view's coordinates (widget_to_local includes the scroll offset). */
static int al_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(al.view, pt);
    return al.list ? al_row_at(pt[1]) : al_cell_at(pt[0], pt[1]);
}

static void al_set_press(int p) {
    if (al.press == p) return;
    al.press = p;
    al_redraw();
}

static int al_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    al.down = 0;
    if (!e || !al.view) return RET_OK;
    a = al_item_of(e);
    al.down = a + 1, al.down_x = I(e, PE_X), al.down_y = I(e, PE_Y);
    if (al.list) al_set_press(a + 1);
    return RET_OK;
}

static int al_on_up(void *ctx, void *e) {
    int a = al.down - 1, dx, dy;
    (void)ctx;
    al.down = 0;
    if (al.list) al_set_press(0);
    if (a < 0 || !e || !al.view) return RET_OK;
    dx = al_abs(I(e, PE_X) - al.down_x);
    dy = al_abs(I(e, PE_Y) - al.down_y);
    if (dx < AL_TAP_PX && dy < AL_TAP_PX && al_item_of(e) == a) {
        int row = (int)(al.order ? al.order[a] : (unsigned)a); /* the stock row */
        /* the All Songs tile of an artist or a composer: our Songs page on every song (Cover Flow's All albums card; a page that does not open
         * leaves the stock page on the All songs row) */
        if (al_is_card(deque_at(al.albums, (unsigned)row)) &&
            songs_open_artist(deque_at(al.artist_row, 0), al.scope) != -1)
            return RET_OK;
        na_note_albums(al.albums, al.order, al.count, al.scope,
                       al.artist_row); /* the order shown, for Continue with Next Album */
        cc_open_album(al.artist_row, al.scope, row); /* scoped: the artist's list, class 0xff01 / 0xff02 */
        na_note_drop();
    }
    return RET_OK;
}

/* The scroll_view took the gesture as a drag (it aborts its children's press), or the window went to the background. */
static int al_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    al.down = 0;
    if (al.list) al_set_press(0);
    return RET_OK;
}

static int al_on_bg(void *ctx, void *e) {
    az_rail_end(&al.az);
    al_on_abort(ctx, e);
    al.fg = 0;
    if (al.more_timer) timer_remove(al.more_timer);
    al.more_timer = 0;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The page and the toggle
 */
/* The navbar's Cover Flow button: the same open as the menu's row (the playing album, else the last), over this
 * page, so Back returns here. */
static int al_on_cover(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    al_build_end(); /* one worker at a time: Cover Flow builds what is missing itself, with its Preparing screen */
    if (al.artist_row)
        coverflow_artist(al.artist_row, 0, al.scope); /* the same artist's covers */
    else
        coverflow_open();
    return RET_OK;
}

/* An artist's page: Play is every song of the artist in order from the first, Shuffle the stock Shuffle mode from a random one (the Songs page's pills on the artist's list). */
static int al_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (al.artist_row && al.count) songs_play_artist(deque_at(al.artist_row, 0), al.scope, SO_IN_ORDER);
    return RET_OK;
}

static int al_on_shuffle(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (al.artist_row && al.count) songs_play_artist(deque_at(al.artist_row, 0), al.scope, SO_SHUFFLE);
    return RET_OK;
}

static int al_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (al.more_timer) timer_remove(al.more_timer);
    al_build_end(); /* the timer removed, the worker cancelled (cc_build_stop) */
    grid_free(&al.g);
    if (al.hdr) bitmap_destroy(al.hdr);
    az_free(&al.az);
    if (al.albums) deque_destroy(al.albums);
    if (al.artist_row) deque_destroy(al.artist_row);
    free(al.keys);
    free(al.years);
    free(al.order);
    memset(&al, 0, sizeof al);
    return RET_OK;
}

/* The rail of the list mode: shown with sections (and the Index Rail switch on), hidden in the grid. */
static void al_rail(void) {
    if (!al.az_ok) return;
    if (al.list)
        az_rail_fit(&al.az, GRID_VIEW_H);
    else {
        al_show(al.az.rail, 0);
        al_show(al.az.bubble, 0);
    }
}

static int al_on_rail(void *ctx, void *e) {
    (void)ctx;
    if (al.view && al.list) az_rail_event(&al.az, e);
    return RET_OK;
}

static int al_on_rail_paint(void *ctx, void *e) {
    (void)ctx;
    if (al.view && al.list) az_rail_paint(&al.az, e);
    return RET_OK;
}

/* The sections of the library list in the Title order only: the rank of the first letter of the album's title (cc_name_initial: a CJK title as its pinyin initial, kana
 * as its Hepburn initial), az_sections' labelling (the list keeps its order, a stray stays in the section around it). Z-A mirrors the ranks as the Songs page does
 * (Z is rank 0 .. A rank 25, "#" last, so they still rise down the list) and its letters back. The Artist, Recently Added and Year orders, the artist's own albums (their
 * order is Cover Flow's) and a page without memory or without the furniture: a plain list. */
static void al_sections(void) {
    unsigned char *rank;
    unsigned i;
    al.az.nsec = 0;
    if (!al.az_ok || al.artist_row || al.sort != CC_SORT_TITLE || !al.count) return;
    rank = calloc(al.count, 1);
    if (!rank) return;
    for (i = 0; i < al.count; ++i) {
        int k = az_rank_of(cc_name_initial(cc_str(cc_row(al.albums, al.order, i), REC_ALBUM)));
        rank[i] = (unsigned char)(al.rev ? (k ? 26 - k : 26) : k);
    }
    az_sections(&al.az, rank, 1);
    free(rank);
    if (al.rev) /* the letters of the mirrored ranks: rank 0 is Z, 25 is A, 26 is "#" */
        for (i = 0; i < (unsigned)al.az.nsec; ++i) {
            int t = al.az.sec_letter[i] == '#' ? 0 : al.az.sec_letter[i] - 'A' + 1;
            al.az.sec_letter[i] = (unsigned char)(t == 26 ? '#' : 'Z' - t);
        }
}

/* The first album in view: its row's first album in the grid, the top row in the list; inside [0, count - 1] also while
 * the list is pulled past an end (overscroll). */
static int al_first(void) {
    int a = al.list ? az_row_from(&al.az, al_off() + al_hh())
                    : al_row_of(al_coff()) * GRID_COLS; /* (the list: the row just under the pinned band) */
    if (a > (int)al.count - 1) a = (int)al.count - 1;
    return a < 0 ? 0 : a;
}

/* The covers of a mode: the grid's GRID_COVER px with the shelf's GRID_R corners blended into black (the view is black, tiles stay opaque);
 * the list's LIST_ART px with LIST_R corners cut in the alpha (a pressed row's fill lies behind them). */
static void al_shape(int list) { grid_shape(&al.g, list ? LIST_ART : GRID_COVER, list ? LIST_R : GRID_R, list); }

/* The content view as high as the mode's content, and the scroll_view told the same (the list_view layouter sums it again at the next layout). */
static void al_size(void) {
    int h;
    al.az.top = al_top();
    h = al_content();
    al.az.content = h;
    widget_resize(al.view, AL_W, h);
    widget_set_prop_int(al.sv, "virtual_h", h);
}

/* A coasting list stops (patch/scroll.c sc_down). */
static void al_stop_scroll(void) {
    void *wa = P(al.sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING && P(wa, SC_AN_WIDGET) == al.sv) {
        widget_animator_destroy(wa);
        stock_scroll_done(al.sv, (void *)0);
    }
}

/* The circle in place: circ 1 draws it with the name and the pills below (AL_NAME_Y, AL_HEAD_PILL_Y); 0 takes its room (PH_SHIFT) out: the same name and pills, the rows with them. The scroll offset is kept inside the new content. */
static void al_layout(int circ) {
    int max;
    if (!al.head || circ == al.circ || !al.view) return;
    al.circ = circ;
    widget_move(al.name_lbl, PH_NAME_X, AL_NAME_Y - al_gone());
    widget_move(al.btn_play, AL_PLAY_X, AL_HEAD_PILL_Y - al_gone());
    widget_move(al.btn_shuffle, AL_SHUFFLE_X, AL_HEAD_PILL_Y - al_gone());
    if (al.hdr) bitmap_destroy(al.hdr);
    al.hdr = (void *)0, al.hdr_done = 0;
    al_stop_scroll();
    al_size();
    max = al_max_scroll();
    if (al_off() > max) widget_set_prop_int(al.sv, "yoffset", max);
    al.seen = al_off();
    al_fade();
    al_redraw();
    al_kick();
}

/* The artist's photo is looked at again by the cover worker (never the UI thread): once, after the page's own cover build, and only when the worker is free (otherwise Home's pass covers it). The albums' first
 * tracks are what the page has. The page's build timer polls it as it does the cover build. */
#define AL_RC_BUF 4096
static void al_recheck(void) {
    char *buf;
    unsigned i, n = 0;
    if (!al.view || !al.head || al.scope != CLASS_ARTISTS || al.rk || al.own || al.build_timer || !al.albums) return;
    al.rk = 2; /* (asked once per open) */
    buf = calloc(1, AL_RC_BUF);
    if (!buf) return;
    for (i = 0; i < (unsigned)deque_size(al.albums); ++i) {
        void *r = deque_at(al.albums, i);
        const char *path = r && I(r, REC_ID) != ID_ALL_SONGS ? cc_str(r, REC_PATH) : "";
        unsigned len = 0;
        while (path[len]) ++len;
        if (!len) continue;
        if (n + len + 2 > AL_RC_BUF) break;
        memcpy(buf + n, path, len);
        n += len;
        buf[n++] = '\n';
    }
    buf[n] = 0;
    al.rk_ep = ap_epoch();
    if (n && ap_recheck(cc_str(deque_at(al.artist_row, 0), REC_TITLE), buf)) {
        al.own = 1, al.rk = 1, al.done = 0;
        al.build_timer = timer_add(al_on_build, (void *)0, AL_BUILD_MS);
        if (!al.build_timer) al_build_end(), al.rk = 2;
    }
    free(buf);
}

/* The re-check is over: if a photo appeared or went, the header switches; a replaced one is read again. */
static void al_recheck_done(void) {
    int want;
    if (!al.view || !al.head || al.scope != CLASS_ARTISTS) return;
    want = al_has_photo();
    if (want != al.circ)
        al_layout(want);
    else if (want && ap_epoch() != al.rk_ep) {
        if (al.hdr) bitmap_destroy(al.hdr);
        al.hdr = (void *)0, al.hdr_done = 0;
        al_redraw();
        al_kick();
    }
}

/* Switches the mode in place: nothing opens or closes. The first album in view stays at the top. */
static void al_set_mode(int list) {
    int first = al_first(), max;
    al_stop_scroll();
    if (al.more_timer) timer_remove(al.more_timer);
    al.more_timer = 0;
    az_rail_end(&al.az);
    al.list = list, al.press = 0, al.down = 0, al.dir = 1;
    grid_drop(&al.g); /* the tiles were made for the other shape */
    al_shape(list);
    if (al.g.tiles) grid_placeholder(&al.g);
    al_size();
    al_rail();
    max = al_max_scroll();
    first = !first ? 0
            : list
                ? az_row_y(&al.az, first) - al_hh() /* (a section's first album brings its header to the top) */
                : al_top() + first / GRID_COLS * PITCH; /* (the first album is at the top: the title block with it) */
    widget_set_prop_int(al.sv, "yoffset", first > max ? max : first);
    al.seen = al_off();
    al_fade();
    vs_view(&al.vs, list);
    al_redraw();
    al_kick();
}

/* The order changed: the tiles are dropped (they were for other albums), the list starts at the top, the cover scan starts again (nearest the first album in view first). */
static void al_resort(void) {
    free(al.order);
    al.order = cc_album_order_mode(al.albums, al.sort, al.rev);
    if (!al.view || !al.g.tiles) return;
    al_stop_scroll();
    if (al.more_timer) timer_remove(al.more_timer);
    al.more_timer = 0;
    al_build_end();
    al.scanned = 0;
    al.press = 0, al.down = 0, al.dir = 1;
    grid_drop(&al.g);
    grid_placeholder(&al.g);
    al_sections(); /* (the Title order has them, the others are plain) */
    al_size();
    al_rail();
    widget_set_prop_int(al.sv, "yoffset", 0);
    al.seen = al_off();
    al_fade();
    al_redraw();
    al_kick();
    al_build_later();
}

/* The "..." card's rows: a sort row sets the order in its default direction, the row already ticked reverses it (saved first: a save that fails leaves the old order and its tick); the Grid / List row
 * the other mode, in place, saved (the ticked view does nothing); the Search row opens the Search page scoped to albums (patch/search.c; the library search where that will not open). The card closes. */
static int al_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx;
    (void)e;
    if (!al.view) return RET_OK;
    vs_menu(&al.vs, 0, al.sort, al.rev, al.list);
    if (k == VS_SEARCH) {
        if (search_open_in(SEARCH_ALBUMS) < 0) search_open();
    } else if (k == VS_SORTS || k == VS_SORTS + 1) {
        int list = k == VS_SORTS + 1;
        if (list == al.list) return RET_OK;
        al_set_mode(list);
        home_write_atomic(ALBUMS_FILE, ALBUMS_TMP, al.list ? "0\n" : "1\n");
    } else if (k >= 0 && k < VS_SORTS) {
        int rev = k == al.sort ? !al.rev : 0;
        if (cc_sort_mode_set(k, rev) == k) {
            al.sort = k, al.rev = rev;
            al_resort();
        }
    }
    return RET_OK;
}

static int al_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    vs_menu(&al.vs, 0, al.sort, al.rev, al.list);
    return RET_OK;
}

static int al_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (al.win && al.vs.card) vs_menu(&al.vs, !al.vs.on, al.sort, al.rev, al.list);
    return RET_OK;
}

/* The page in the given mode. 0 once it is up, -1 if the window could not open, -2 if the asset is not ours (the
 * page is left again). artist_row (a deque holding the stock row of an artist, or a composer when scope says so) scopes it to that artist's albums: the
 * page then owns the deque, from the moment the window is up. */
static int al_open(int list, void *artist_row, unsigned scope) {
    if (al.win) return -1;
    memset(&al, 0, sizeof al);
    al.win = window_open("m1plus_albums");
    if (!al.win) return -1;
    al.list = list;
    al.artist_row = artist_row, al.scope = scope;
    widget_on(al.win, EVT_DESTROY, al_on_destroy, (void *)0);
    pod_bind(al.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(al.win, "btn_backtoplayer", pod_on_player, (void *)0);
    pod_bind(al.win, "btn_coverflow", al_on_cover, (void *)0);
    pod_bind(al.win, "btn_more", al_on_more, (void *)0);
    al.btn = widget_lookup(al.win, "btn_more", 1);
    al.view = widget_lookup(al.win, "view_grid", 1);
    al.sv = widget_lookup(al.win, "albums_scrollview", 1);
    al.status = widget_lookup(al.win, "label_status", 1);
    al.btn_play = widget_lookup(al.win, "btn_play", 1); /* optional: an artist's page only */
    al.btn_shuffle = widget_lookup(al.win, "btn_shuffle", 1);
    al.pills = artist_row && al.btn_play && al.btn_shuffle;
    al.name_lbl = widget_lookup(al.win, "al_name", 1); /* optional: the photo header's name */
    al.head = al.pills && al.name_lbl;
    al.circ = al.head && scope == CLASS_ARTISTS &&
              al_has_photo(); /* (the cache says: a photo, else the header has no circle; a composer: none) */
    al.fade = widget_lookup(al.win, "img_nb_fade", 1); /* optional */
    al.st_title = widget_lookup(al.win, "label_row_title", 1);
    al.st_sub = widget_lookup(al.win, "label_row_sub", 1);
    al.st_gtitle = widget_lookup(al.win, "label_grid_title", 1);
    al.st_gsub = widget_lookup(al.win, "label_grid_sub", 1);
    if (!al.view || !al.sv || !al.status || !al.st_title || !al.st_sub || !al.st_gtitle || !al.st_gsub) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    if (vs_bind(
            &al.vs, al.win, al_on_item, al_on_scrim,
            (artist_row ? VS_ALL_SORTS & ~(1u << CC_SORT_ARTIST) : VS_ALL_SORTS | VS_WITH_SEARCH) |
                VS_WITH_VIEWS)) { /* (one artist's albums: no Artist row, and no Search row: it searched the whole library's albums) */
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    al.sort = artist_row ? cc_scoped_sort() : cc_sort_mode();
    al.rev = cc_sort_rev();
    vs_view(&al.vs, list);
    al.az.win = al.win, al.az.sv = al.sv, al.az.top = al_top(), al.az.row = LIST_ROW_H;
    az_prefs(&al.az);
    al.az.st_hdr = widget_lookup(al.win, "label_hdr", 1);
    al.az.st_rail = widget_lookup(al.win, "label_rail", 1);
    al.az.st_rail_on = widget_lookup(al.win, "label_rail_on", 1);
    al.az.rail = widget_lookup(al.win, "sg_rail", 1);
    al.az.bubble = widget_lookup(al.win, "sg_bubble", 1);
    al.az.bubble_letter = widget_lookup(al.win, "sg_bubble_letter", 1);
    al.az_ok = al.az.st_hdr && al.az.st_rail && al.az.st_rail_on && al.az.rail && al.az.bubble && al.az.bubble_letter;
    al_show(al.status, 0);
    al.small = widget_lookup(al.win, "label_title", 1);
    al.big = widget_lookup(al.win, "al_title", 1);
    if (artist_row) { /* the artist's albums and, with two or more, the All Songs row last, titled with the artist (Cover Flow's scoped list) */
        const char *name = cc_str(deque_at(artist_row, 0), REC_TITLE);
        al.count = (unsigned)coverflow_artist_albums(artist_row, scope, 1, &al.albums, &al.keys);
        if (al.count) { /* the years: one read of the artist's (composer's) songs (the stock queries of the Songs page's artist list) */
            void *songs = songs_artist_list(deque_at(artist_row, 0), scope);
            if (songs) al.years = cc_album_years(al.albums, songs);
        }
        al.order = cc_album_order_mode(
            al.albums, al.sort, al.rev); /* the chosen order (Artist as Title); the keys and years stay by stock row */
        az_fit(al.big,
               name); /* both titles cut with an ellipsis to their room (296 px; the 110 px before Cover Flow) */
        az_fit(al.small, name);
        if (al.head) { /* the name under the circle, centred (22 px), in place of the large title */
            az_fit(al.name_lbl, name);
            al_show(al.name_lbl, 1);
            al_show(al.big, 0);
            if (!al.circ) widget_move(al.name_lbl, PH_NAME_X, AL_NAME_Y - PH_SHIFT);
        }
    } else {
        az_fit(al.big, TR("Albums")); /* (the language's word) */
        az_fit(al.small, TR("Albums"));
        al.albums = cc_albums();
        al.count = al.albums ? deque_size(al.albums) : 0;
        al.order = cc_album_order_mode(al.albums, al.sort, al.rev);
    }
    al.az.count = (int)al.count;
    if (!al.count || !grid_init(&al.g, al.win, GRID_TILES, GRID_COVER, 0)) {
        grid_free(&al.g);
        al_show(al.view, 0);
        al_show(al.status, 1);
        if (al.az_ok) al_show(al.az.rail, 0), al_show(al.az.bubble, 0); /* (nothing to index) */
        widget_set_tr_text(al.status, al.count     ? "Not enough memory"
                                      : artist_row ? "No albums"
                                                   : "Update Local Music first");
        return 0;
    }
    if (al.pills) { /* under the large title: the pills as the Songs page's (the label and glyph centred as a pair), shown and live */
        pod_bind(al.win, "btn_play", al_on_play, (void *)0);
        pod_bind(al.win, "btn_shuffle", al_on_shuffle, (void *)0);
        pod_centre_pill(al.btn_play, AL_PLAY_W);
        pod_centre_pill(al.btn_shuffle, AL_SHUFFLE_W);
        if (al.head) { /* the pills sit under the name */
            widget_move(al.btn_play, AL_PLAY_X, AL_HEAD_PILL_Y - al_gone());
            widget_move(al.btn_shuffle, AL_SHUFFLE_X, AL_HEAD_PILL_Y - al_gone());
        }
        al_show(al.btn_play, 1);
        al_show(al.btn_shuffle, 1);
    }
    al.g.az = &al.az; /* (list rows lie below the headers) */
    al_shape(list);
    al.g.st_title = al.st_gtitle,
    al.g.st_sub = al.st_gsub; /* the grid's two text styles (the list mode's are drawn by this page) */
    grid_placeholder(&al.g);
    al_sections();
    al_size();
    al_rail();
    al.dir = 1;
    al.fg = 1;
    al.noscroll = !widget_on(al.sv, EVT_SCROLL, al_on_scroll, (void *)0) ||
                  !widget_on(al.sv, EVT_SCROLL_END, al_on_scroll, (void *)0);
    if (al.noscroll && al.small)
        widget_set_visible(
            al.small, 1,
            0); /* the large title's collapse needs the scroll events: without them the navbar keeps its title */
    al.title_on = al.noscroll;
    al_kick();
    al_build_later();
    if (widget_on(al.win, EVT_WINDOW_TO_FG, al_on_fg, (void *)0))
        widget_on(al.win, EVT_WINDOW_TO_BG, al_on_bg, (void *)0);
    else
        widget_on(al.win, EVT_WINDOW_TO_BG, al_on_abort, (void *)0);
    widget_on(al.view, EVT_POINTER_DOWN, al_on_down, (void *)0);
    widget_on(al.view, EVT_POINTER_UP, al_on_up, (void *)0);
    widget_on(al.view, EVT_POINTER_ABORT, al_on_abort, (void *)0);
    widget_on(al.view, EVT_AFTER_PAINT, al_on_paint, (void *)0);
    if (al.az_ok) {
        az_make_disc(&al.az);
        widget_on(al.az.rail, EVT_POINTER_DOWN, al_on_rail, (void *)0);
        widget_on(al.az.rail, EVT_POINTER_MOVE, al_on_rail, (void *)0);
        widget_on(al.az.rail, EVT_POINTER_UP, al_on_rail, (void *)0);
        widget_on(al.az.rail, EVT_POINTER_ABORT, al_on_rail, (void *)0);
        widget_on(al.az.rail, EVT_AFTER_PAINT, al_on_rail_paint, (void *)0);
    }
    return 0;
}

/* The M1+ Music menu's Albums row: the mode used last (the grid on a first use). A window that will not open leaves
 * the stock Albums list, through the Home dispatcher. 0 once something is requested. */
int albums_open(void) {
    int r = al_open(!al_use_grid(), (void *)0, 0);
    if (r == -1 && !al.win) return pod_home_open(HOME_ALBUM);
    return r;
}

/* The Artists page's row `index` of `artists` (patch/artists.c; the caller keeps its list): the same page, in the mode used last, on that artist's
 * albums (scope CLASS_ARTISTS, or CLASS_COMPOSERS for a composer), the name as its title. 0 once the page is up, -1 if it could not open (the caller
 * opens Cover Flow on the artist), -2 if the asset is not ours. */
int albums_open_artist(void *artists, unsigned index, unsigned scope) {
    void *row = artists && index < deque_size(artists) ? deque_at(artists, index) : (void *)0, *d;
    int r;
    if (al.win || !row) return -1;
    d = _create_deque("stSongInfo");
    if (!d) return -1;
    deque_init(d);
    _deque_push_back(d, row); /* a copy, as the stock queries push rows */
    r = al_open(!al_use_grid(), d, scope == CLASS_COMPOSERS ? CLASS_COMPOSERS : CLASS_ARTISTS);
    if (!al.win) deque_destroy(d); /* else the window's destroy frees it */
    return r;
}
