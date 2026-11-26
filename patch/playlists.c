/* M1+ Music Playlists: the stock playlists as a grid, each one a 2x2 mosaic of its albums' covers.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_playlists.bin: the navbar (Back, the small title, "..." | Now Playing) over a stock list, list_view > scroll_view
 * (playlists_scrollview), the structure of the Albums page (patch/albums.c, docs/modules/albums.md), whose ONE child is a custom view, view_grid,
 * that paints the cells itself in its own EVT_AFTER_PAINT through the shared grid (patch/grid.c). The stock scroll_view does the scrolling.
 * A cell is a GRID_COVER px tile, the playlist's name under it and "N tracks" under that. docs/modules/playlists.md has the whole design.
 *
 *   data      the playlists come from the stock query (loadLocalClassList(CLASS_PLAYLISTS), copied: what the stock Playlists page lists) when
 *             the page opens and again whenever its window comes back to the front (a playlist may have been edited in the stock songs
 *             page, or one created, imported or deleted), so nothing is cached across visits. Per playlist the loader reads its songs
 *             (loadLocalClassList(CLASS_PLAYLIST_SONGS) with classinfo[1] = the playlist) ONE playlist a tick: the track count, and from the
 *             first PL_SCAN songs the first four distinct albums that have a Cover Flow cache file (the key is the cc_album_key of the song:
 *             its artist and album as the playlist stored them; when that file does not exist the album of that name in the library is looked
 *             up, whose record carries the artist the cache key was made from).
 *   tiles     the grid's ring (GRID_TILES). The tile of a playlist with 2..4 albums is composed by grid_mosaic from the 168 px cache files
 *             box-reduced to a quadrant, one source per tick; one album is that cover full size; none is the stock placeholder disc. Paint never
 *             decodes, and neither does the loader while the scroll_view drags or flings.
 *   modes     the card's Grid / List rows switch the grid and the list (LIST_ROW_H rows, 52 px mosaics, patch/grid.c grid_list_paint) in place;
 *             the choice is saved in PLAYLISTS_FILE.
 *   order     the card's Title, Date Added, Last Played and Updated rows (the ticked row again reverses, PLAYLISTS_SORT_FILE; the times are patch/plmeta.c's): pl.ord is the stock row at each
 *             display position, the stock list is never reordered.
 *   touch     a tap on a cell or row opens the playlist in our Songs page (patch/songs.c, class 0xff13), or the stock songs page (allmusic_page) as the stock
 *             Playlists page does when ours does not open.
 *   menu      the "..." button opens the shared view-sort card (patch/viewsort.c): New Playlist, Import, Export (the stock code), Delete Playlists (select mode on this
 *             page: marks, a bar with the Delete pill, the stock delete handler's sequence on the stock selection vector; the stock Playlists page only where the page
 *             cannot), then Grid / List, then Title, Date Added, Last Played, Updated. No hook.
 */
#include "selmode.h"
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "keyboard.h"
#include "picker.h"
#include "viewsort.h"
#include "libsrc.h"
#include "sbsrc.h"
#include "songops.h"
#include "playlists.h"
#include "fnv.h"
#include "entries.h"
#include "rowmenu.h"
#include "pins.h"
#include "plmeta.h"

#define CELL_H GRID_CELL_H
#define PITCH GRID_PITCH
#define PL_W 320
#define PL_AHEAD (pl.list ? 2 : 1)
#define HOME_PLAYLIST 14
#define PL_PICK_MS 400 /* the picker's add after a New playlist: the keyboard page's close is over */
#define PL_TOP \
    SG_TITLE_H /* the content starts with the large title (as Albums' al_top without pills): the rows or the grid's first gap follow it */
#if GRID_TILES < GRID_COLS * ((GRID_VIEW_H + CELL_H) / PITCH + 2 + 1) + 2
#error GRID_TILES cannot hold the visible cells, the next row and the history
#endif
#if GRID_TILES < (GRID_VIEW_H / LIST_ROW_H) + 2 + 2 + 2
#error GRID_TILES cannot hold the visible rows, the next two and the history
#endif

#define P(w, off) (*(void **)((char *)(w) + (off)))

#define PL_SIG 9 /* pl_dbsig: three files, three words each */
#define PL_DB "/mnt/data/database.db"

typedef grid_tile_t tile_t;

typedef struct {
    unsigned key[4]; /* the first distinct albums of the playlist that have a cache file */
    int nk, songs;
    int scanned; /* 0 not read, 1 read, PL_SCAN_MISS read and an album had a key but no cache file (its file may appear: read again when the page returns) */
    int has; /* the picker: how many of the songs being added the playlist (row 1: Favourites) holds, by its scan (picker_in); 0 before it */
} info_t;
#define PL_SCAN_MISS 2

static struct {
    void *win, *view, *sv, *status, *btn_more;
    void *title, *back, *np, *btn_selall, *bar,
        *del; /* the navbar's title, Back and Now Playing; the select mode's Select All text, bar and Delete pill (the last three optional: no select mode without them) */
    m1_sel_t sel; /* the select mode's marks and chrome (patch/selmode.c); pill: pl.del */
    int select; /* select mode (Delete Playlists in the menu) */
    void *st_ltitle, *st_lsub; /* the hidden labels whose styles are the list mode's two text styles */
    int list; /* 1 list mode, 0 grid */
    int press; /* list: the row under the finger, + 1 */
    void *pls; /* our copy of the stock playlist rows */
    unsigned count;
    info_t *info; /* count entries */
    void *albums; /* the library's albums (cc_albums), loaded at the first scan, for the album-name lookup */
    int albums_tried;
    unsigned *tmp; /* one quadrant (side / 2 squared words) for grid_mosaic */
    int seen, dir, noscroll;
    int down;
    m1_tap_t tap;
    rowmenu_t
        rm; /* the long press sheet (Play, Shuffle | Pin / Unpin Playlist, Add to Playlist | Play Next, Play After; the library's page only: rm.on) */
    int menu; /* a card is open: 0 none, 1 the "..." card (views, order), 2 the list-plus button's (the four actions) */
    unsigned more_timer;
    vs_t vs; /* the "..." card (patch/viewsort.c) */
    unsigned *ord; /* the stock playlist at each display position (after the picker's rows), NULL = the stock order */
    int sort,
        rev; /* the order: 0 Title, 1 Date Added, 2 Last Played, 3 Updated (PLAYLISTS_SORT_FILE); rev = the other direction (Z-A, Oldest First) */
    unsigned msig
        [3]; /* PLAYLISTS_META_FILE's state (pl_metasig) when the playlists were last read: a date order sorts again when it moved */
    void *fade; /* the navbar's fade (img_nb_fade, optional): shown only while the list is scrolled */
    void *big; /* pl_title, the large title: the first thing in the content (optional) */
    int title_on; /* the navbar's small title (pl.title) is shown: the large one has scrolled away, or select mode, or the scroll events are missing */
    unsigned sig[PL_SIG]; /* the database's state (pl_dbsig) when the playlists were last read */
    int have_sig;
    int bg; /* another window is in front: the loader does not run (pl_on_bg) */
    void *btn_plactions; /* the navbar's list-plus button: the capsule's left cap at NAV_CF_X, opens the actions card */
    const lib_src_t *
        src; /* the library source (playlists_open_src): NULL = the stock playlists, today's code; set before everything else reads it */
    unsigned gen, rows,
        gen_timer; /* src: the source's gen() and gen_rows when the playlists were read, and the timer that watches it */
    void *spin; /* a source's loading spinner (pl_spin, optional) */
    ls_cpoll_t
        cp; /* the shared cover poll (patch/libsrc.c ls_cover_poll): the rescan and the cover spinners' turn while a source's mosaic is still filling */
    grid_t g; /* LAST (test/pod/playlists.py reads the fields above by index) */
} pl __attribute__((section(".scratch")));

static int pl_rows(void) { return ((int)pl.count + GRID_COLS - 1) / GRID_COLS; }
static int pl_rows_h(void) {
    return pl.list ? (int)pl.count * LIST_ROW_H : pl_rows() ? GRID_ROW_GAP + pl_rows() * PITCH : 0;
} /* the cells' or rows' height */
static int pl_pad(void) {
    return pl.select ? SG_BAR_H : 0;
} /* the select bar covers the window's last SG_BAR_H rows: the list scrolls clear of it */
static int pl_content(void) { return pl_rows_h() ? PL_TOP + pl_rows_h() + pl_pad() : 0; }
static int pl_max_scroll(void) {
    int m = pl_content() - GRID_VIEW_H;
    return m > 0 ? m : 0;
}
static int pl_off(void) { return grid_sv_off(pl.sv); }
/* The same offset measured from the top of the rows (negative while the title block is in view). */
static int pl_coff(void) { return pl_off() - PL_TOP; }

/* The navbar's fade (an insensitive image, built hidden) is for rows passing under the bar: shown while the list is scrolled, hidden at rest, where the
 * first row would be darkened by it. It is never a touch target. No fade widget = nothing happens. The small title is the navbar's once the large one
 * has scrolled away (m1_title_gone, the rule every large-title page shares), and in select mode ("N Selected"); without the scroll events it stays. */
static void pl_fade(void) {
    m1_title_set(pl.title, &pl.title_on, pl.noscroll || pl.select || m1_title_gone(pl_off(), 0));
    if (!pl.fade) return;
    grid_fade(pl.fade, pl_off() > 0);
}
static void pl_redraw(void) { grid_sv_redraw(pl.sv); }

/* Pick mode (the Add to Playlist picker, patch/picker.c; docs/modules/picker.md): "New playlist" is row 0, the playlists follow. When the picker opens over
 * our own Songs page of a playlist, the Playlists page below it has a state, kept aside here and put back when the picker goes. */
static struct {
    int on, id;
    unsigned timer;
    void *stash;
    void *star; /* the Favourites row's glyph: a 24 px white star, alpha bitmap */
    void *
        tick; /* the mark of a row that holds every song being added: the Add Songs page's grey tick (sg_pdone), RM_DOTS_PX */
    char name[0x100]; /* the playlist id belongs to while the add waits on its timer (pl_pick_later) */
} pick __attribute__((section(".scratch")));

/* A playlist just made on the Playlists page (not the picker): its page opens once the keyboard has gone (pl_new_later). */
static struct {
    int id;
    unsigned timer;
    char name[0x100];
} pl_new __attribute__((section(".scratch")));
static int pl_v(void) { return pick.on ? 2 : 0; } /* the rows before the playlists: New playlist, Favourites */
/* The picker's row i (Favourites or a playlist) holds every song being added (its scan said so): the tick, and a tap adds nothing. */
static int pl_full(int i) {
    return pick.on && i > 0 && pl.info[i].has > 0 && (unsigned)pl.info[i].has == picker_count();
}
/* The stock playlist (index in the copy of the stock list) shown at display position k, after the picker's rows. */
static unsigned pl_slot(unsigned k) { return pl.ord ? pl.ord[k] : k; }
static void *pl_rec(int i) { return deque_at(pl.pls, pl_slot((unsigned)(i - pl_v()))); }
/* The playlist's id: REC_DISC, what the stock row handler hands to classinfo[1] (@0x53d5f4) */
static int pl_id(int i) { return I(pl_rec(i), REC_DISC); }

/* ---------------------------------------------------------------------------
 * The window: the rows that touch the view and the ones about to
 */
static int pl_row_of(int s) { return s > GRID_ROW_GAP + CELL_H ? (s - GRID_ROW_GAP - CELL_H) / PITCH + 1 : 0; }

/* The rows (grid rows, or list rows = playlists) that touch the view: [*r0, *r1], inside [0, n - 1] also while a drag pulls the list past an end (overscroll). */
static void pl_span(int *r0, int *r1) {
    int n = pl.list ? (int)pl.count : pl_rows(), s = pl_coff();
    if (pl.list)
        *r0 = s / LIST_ROW_H, *r1 = (s + GRID_VIEW_H - 1) / LIST_ROW_H;
    else
        *r0 = pl_row_of(s), *r1 = (s + GRID_VIEW_H - GRID_ROW_GAP + PITCH - 1) / PITCH - 1;
    if (*r0 < 0) *r0 = 0;
    if (*r1 > n - 1) *r1 = n - 1;
}

static void pl_window(int *lo, int *hi) {
    int per = pl.list ? 1 : GRID_COLS, n = pl.list ? (int)pl.count : pl_rows(), r0, r1;
    pl_span(&r0, &r1);
    if (pl.dir < 0)
        r0 -= PL_AHEAD;
    else
        r1 += PL_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > n - 1) r1 = n - 1;
    *lo = r0 * per;
    *hi = (r1 + 1) * per - 1;
    if (*hi > (int)pl.count - 1) *hi = (int)pl.count - 1;
}

/* The top of playlist a's cell or row in the window, and its height (the rows start PL_TOP down the content: pl_coff is measured from there). */
static int pl_top(int a) { return (pl.list ? a * LIST_ROW_H : GRID_ROW_GAP + a / GRID_COLS * PITCH) - pl_coff(); }
static int pl_height(void) { return pl.list ? LIST_ROW_H : CELL_H; }

static tile_t *pl_find(int a) { return grid_find(&pl.g, a); }

/* The tile's texts: the name and the count (blank until the playlist has been read). */
static void pl_texts(tile_t *t, int a) {
    info_t *in = &pl.info[a];
    char sub[48];
    sub[0] = 0;
    t->markw = pl_full(a) ? rowmenu_text_end(RM_MORE_RIGHT, 0) - LIST_TEXT_X
                          : 0; /* (the tick's room: the callers clear fit) */
    if (a < pl_v()) {
        grid_set(t, TR(a ? "Favorites" : "playlist_create"), sub, 0);
        return;
    }
    if (in->scanned) m1_fmt(sub, sizeof sub, TR(in->songs == 1 ? "%d track" : "%d tracks"), in->songs);
    grid_set(t, cc_str(pl_rec(a), REC_TITLE), sub, 0);
}

static void pl_kick(void);
/* A source's covers on the shared poll (patch/libsrc.c ls_cover_poll): a tile whose playlist was read with a cover still on its way (PL_SCAN_MISS) shows the spinner (a tile with load set,
 * patch/grid.c grid_spin_*) until its mosaic has a picture; every tick of the poll reads those playlists again (the file may be there now; a cover does not move the gen) and turns and redraws
 * the spinners; the poll ends when no playlist is waiting any more, or gives up (the spinners go; the tiles are read again when the page returns). */
static void pl_cp_ask(void) {
    int i, any = 0;
    if (!pl.src || !pl.view || pl.bg || !pl.info || !pl.count) return;
    for (i = 0; i < (int)pl.count; ++i)
        if (pl.info[i].scanned == PL_SCAN_MISS) pl.info[i].scanned = 0, any = 1;
    if (any) pl_kick();
}
static int pl_cp_spin(void) {
    int n;
    if (!pl.view) return 0;
    n = grid_spin_turn(&pl.g);
    pl_redraw();
    return n;
}
static void pl_cp_giveup(void) {
    int i;
    for (i = 0; pl.g.tiles && i < pl.g.n; ++i) pl.g.tiles[i].load = 0;
    if (pl.view) pl_redraw();
}
static void pl_loading(tile_t *t, int a) {
    t->load = pl.src && pl.info && pl.info[a].scanned == PL_SCAN_MISS;
    if (!t->load) return;
    grid_spin_open(&pl.g, "wf_spin", 14);
    if (pl.view) ls_cover_poll(&pl.cp, pl.win, pl_cp_ask, pl_cp_spin, pl_cp_giveup);
}

/* Playlist a's chosen cover (patch/plcover.h; a local playlist only: a source's never looks): its sig, 0 for none, c filled. The picker's rows have none. */
static unsigned pl_cover(int a, plc_t *c) {
    if (pl.src || a < pl_v() || !pl.pls || a >= (int)pl.count) return 0;
    return plc_get(pl_id(a), cc_str(pl_rec(a), REC_TITLE), c) ? c->sig : 0;
}

/* The tile's cover: the chosen cover of its playlist when it has one, else the next step of its mosaic. */
static void pl_art(tile_t *t, int a) {
    plc_t c;
    if (t->cov && pl_cover(a, &c))
        grid_plc(&pl.g, t, &c), t->cov = c.sig;
    else
        grid_mosaic(&pl.g, t, pl.tmp);
}

/* The tile's texts and mosaic keys from the playlist's scan (the count shows once the playlist has been read). */
static void pl_prep(tile_t *t, int a) {
    info_t *in = &pl.info[a];
    plc_t c;
    grid_free_art(t);
    t->fit = 0, t->art = 0, t->qi = 0;
    t->mid = a < pl_v();
    t->nq = in->nk > 1 && !pl.tmp ? 1 : in->nk;
    memcpy(t->qkey, in->key, sizeof t->qkey);
    t->cov = pl_cover(a, &c);
    if (in->scanned && !in->nk && !t->cov) t->art = 2; /* no album with a cover: the placeholder */
    pl_texts(t, a);
    pl_loading(t, a);
}

/* The texts are cut to a width that the select mode changes (the list's rows make room for the mark): every tile's are made again from the playlist. */
static void pl_retext(void) {
    int i;
    for (i = 0; pl.g.tiles && pl.pls && i < pl.g.n; ++i) {
        tile_t *t = &pl.g.tiles[i];
        if (t->album && t->album - 1 < (int)pl.count) pl_texts(t, t->album - 1), t->fit = 0;
    }
}

static tile_t *pl_tile(int a) {
    int lo, hi, fresh;
    tile_t *t;
    pl_window(&lo, &hi);
    t = grid_tile(&pl.g, a, lo, hi, &fresh);
    if (fresh) pl_prep(t, a);
    return t;
}

static tile_t *pl_tile_of(void *ctx, int a) {
    (void)ctx;
    return pl_tile(a);
}

/* ---------------------------------------------------------------------------
 * Paint (the cell paint is the grid's)
 */
/* The select mark of playlist a: the list's rows have a column left of the cover (the cover and the texts move right by SG_SEL_COL, as the Songs page's); a grid cell
 * has it at the bottom right of its cover (SG_MARK px, 6 px in). Drawn only when wholly inside the window. */
static void pl_mark(void *canvas, int a, int x, int y) {
    grid_mark_draw(canvas, pl.sel.mark[m1_sel_is(&pl.sel, a)], x, y, GRID_VIEW_H);
}

/* The picker's New playlist row: a dark rounded square over the placeholder disc and a plus (two 2 px bars, as Lucide's plus at this size) in the art box. Only when
 * wholly inside the window (a row half under the navbar shows the disc, as the marks are drawn). */
static void pl_plus(void *canvas, int y) {
    int i, x = LIST_ART_X, c = LIST_ART_X + LIST_ART / 2, cy = y + LIST_ART / 2;
    if (y < 0 || y + LIST_ART > GRID_VIEW_H) return;
    canvas_set_fill_color(canvas, 0xff2e2c2cu); /* #2C2C2E (red lowest) */
    for (i = 0; i < 2; ++i) { /* the corners of a LIST_R 4 arc: the first line starts 2 px in, the second 1 */
        canvas_fill_rect(canvas, x + 2 - i, y + i, LIST_ART - 2 * (2 - i), 1);
        canvas_fill_rect(canvas, x + 2 - i, y + LIST_ART - 1 - i, LIST_ART - 2 * (2 - i), 1);
    }
    canvas_fill_rect(canvas, x, y + 2, LIST_ART, LIST_ART - 4);
    canvas_set_fill_color(canvas, 0xffffffffu);
    canvas_fill_rect(canvas, c - 10, cy - 1, 20, 2);
    canvas_fill_rect(canvas, c - 1, cy - 10, 2, 20);
}

/* The Favourites row's glyph: the star of the Favorites icon (the filled five-point star, outer radius 10.5 px), 4 x 4 samples a pixel into the alpha of a white bitmap
 * (the cross and the chevron are made the same way). Coordinates are eighths of a pixel; the unit vectors are thousandths. */
#define PL_STAR 24
static void *pl_make_star(void) {
    static const int ox[5] = {0, 951, 588, -588, -951}, oy[5] = {-1000, -309, 809, 809, -309};
    static const int ix[5] = {588, 951, 0, -951, -588}, iy[5] = {-809, 309, 1000, 309, -809};
    int vx[10], vy[10], x, y, i, j, k, n;
    unsigned *px;
    void *b = bitmap_create_ex(PL_STAR, PL_STAR, PL_STAR * 4, BITMAP_RGBA8888);
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != PL_STAR * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    for (k = 0; k < 5; ++k) { /* centre (12, 12.5) px: a star's visual centre is a little below its circle's */
        vx[2 * k] = 96 + 84 * ox[k] / 1000, vy[2 * k] = 100 + 84 * oy[k] / 1000;
        vx[2 * k + 1] = 96 + 38 * ix[k] / 1000, vy[2 * k + 1] = 100 + 38 * iy[k] / 1000;
    }
    for (y = 0; y < PL_STAR; ++y)
        for (x = 0; x < PL_STAR; ++x) {
            for (n = 0, i = 0; i < 4; ++i)
                for (j = 0; j < 4; ++j) {
                    int sx = x * 8 + 2 * j + 1, sy = y * 8 + 2 * i + 1, in = 0;
                    for (k = 0; k < 10; ++k) { /* even-odd: the edges a ray to +x crosses */
                        int a = k, c = (k + 1) % 10;
                        if ((vy[a] > sy) != (vy[c] > sy) &&
                            ((sx - vx[a]) * (vy[c] - vy[a]) < (vx[c] - vx[a]) * (sy - vy[a])) == (vy[c] > vy[a]))
                            in ^= 1;
                    }
                    n += in;
                }
            px[y * PL_STAR + x] = (unsigned)(n * 255 / 16) << 24 | 0xffffffu;
        }
    bitmap_unlock_buffer(b);
    return b;
}

/* The picker's Favourites row: the New playlist row's dark rounded square with the star centred in the art box. */
static void pl_star(void *canvas, int y) {
    int i, x = LIST_ART_X, src[4], dst[4];
    if (y < 0 || y + LIST_ART > GRID_VIEW_H) return;
    canvas_set_fill_color(canvas, 0xff2e2c2cu); /* #2C2C2E (red lowest) */
    for (i = 0; i < 2; ++i) {
        canvas_fill_rect(canvas, x + 2 - i, y + i, LIST_ART - 2 * (2 - i), 1);
        canvas_fill_rect(canvas, x + 2 - i, y + LIST_ART - 1 - i, LIST_ART - 2 * (2 - i), 1);
    }
    canvas_fill_rect(canvas, x, y + 2, LIST_ART, LIST_ART - 4);
    if (!pick.star) return;
    src[0] = src[1] = 0, src[2] = src[3] = PL_STAR;
    dst[0] = x + (LIST_ART - PL_STAR) / 2, dst[1] = y + (LIST_ART - PL_STAR) / 2, dst[2] = dst[3] = PL_STAR;
    canvas_draw_image(canvas, pick.star, src, dst);
}

static int pl_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = pl_off(), co = pl_coff(), r0, r1, last, a;
    (void)ctx;
    if (!canvas || !pl.view || !pl.g.tiles || !pl.count) return RET_OK;
    I(canvas, CANVAS_OY) +=
        off; /* the window's top is 0: the rows are placed by co (their offset from the first row) */
    pl_span(&r0, &r1);
    if (r1 >= r0 && pl.list) {
        for (a = r0; pl.select && a <= r1; ++a) /* (the fill and the mark, under the cover and text) */
            m1_sel_paint(&pl.sel, canvas, a, a * LIST_ROW_H - co, LIST_ROW_H, 320,
                         LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, GRID_VIEW_H);
        grid_list_paint(canvas, &pl.g, pl.st_ltitle, pl.st_lsub, r0, r1, co, GRID_VIEW_H, pl.select ? 0 : pl.press,
                        pl.select ? SG_SEL_COL : 0, !pl.select && !pl_v(), pl_tile_of, (void *)0);
        if (pl_v() && r0 == 0) pl_plus(canvas, LIST_ART_Y - co);
        if (pl_v() && r0 <= 1 && r1 >= 1) pl_star(canvas, LIST_ROW_H + LIST_ART_Y - co);
        for (a = r0; pick.tick && a <= r1; ++a) /* the picker's tick where the "..." would be */
            if (pl_full(a))
                rowmenu_paint_bmp(canvas, pick.tick, RM_MORE_RIGHT, 0, a * LIST_ROW_H - co, LIST_ROW_H, GRID_VIEW_H);
    } else if (r1 >= r0) {
        last = (r1 + 1) * GRID_COLS;
        if (last > (int)pl.count) last = (int)pl.count;
        grid_paint(canvas, &pl.g, r0 * GRID_COLS, last, GRID_ROW_GAP - co, GRID_VIEW_H, pl_tile_of, (void *)0);
        /* the names on the covers: the tiles are a ring keyed by the playlist (grid_find), not tiles[a] */
        for (a = r0 * GRID_COLS; a < last && !pl.src && pl.pls; ++a) {
            grid_tile_t *t = a >= pl_v() ? grid_find(&pl.g, a) : (grid_tile_t *)0;
            if (t)
                grid_plc_name(canvas, &pl.g, t, cc_str(pl_rec(a), REC_TITLE), grid_cell_x(a),
                              grid_cell_y(a, GRID_ROW_GAP - co), GRID_VIEW_H);
        }
        for (a = r0 * GRID_COLS; pl.select && pl.sel.mark[0] && a < last; ++a)
            pl_mark(canvas, a, grid_cell_x(a) + GRID_COVER - SG_MARK - 6,
                    grid_cell_y(a, GRID_ROW_GAP - co) + GRID_COVER - SG_MARK - 6);
    }
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Reading a playlist: its track count and the albums for its mosaic
 */

/* Reads playlist i's songs: how many, and from the first PL_SCAN the first four distinct albums that have a cover. The stock query leaves them
 * in *pdeq_showlist, which the next query replaces (the library lookup is therefore loaded first). */
/* A source's playlist: its tracks from src->list; the mosaic's keys are the first four distinct cover files among the first PL_SCAN tracks (sbs_mosaic_keys; one asked for and not there yet: PL_SCAN_MISS,
 * the file may appear). The mosaic reads the files by those keys (grid_t.url). */
static void pl_scan_src(info_t *in, void *rec) {
    void *list = pl.src == &lib_nd
                     ? sbs_playlist_scan(pl.src, rec) /* (src->list, but a cached playlist is not asked for again) */
                     : pl.src->list(pl.src, LS_PLAYLISTS, rec);
    int miss = 0;
    if (list)
        in->songs = (int)deque_size(list);
    else
        in->songs = pl.src->count ? pl.src->count(pl.src, LS_PLAYLISTS, rec)
                                  : 0; /* (not cached yet: the sync's songCount, not a 0) */
    in->nk = sbs_mosaic_keys(pl.src, list, in->key, &miss);
    if (!list && pl.src->state && pl.src->state(pl.src, LS_PLAYLISTS, rec) == LS_ST_LOADING)
        miss = 1; /* (the tracks are on their way: read again, the tile fills in place) */
    in->scanned = miss ? PL_SCAN_MISS : 1;
    if (list) deque_destroy(list);
}

static void pl_scan(int i) {
    info_t *in = &pl.info[i];
    int n, miss, got;
    void *list;
    if (i <
        pl_v()) { /* the picker's New playlist row has nothing to read; Favourites only what it holds of the songs being added */
        if (i == 1) in->has = picker_in_fav();
        in->scanned = 1;
        return;
    }
    if (!pl.albums_tried) {
        pl.albums_tried = 1;
        pl.albums = cc_albums();
    }
    if (pl.src) {
        pl_scan_src(in, pl_rec(i));
        return;
    }
    *(int *)(CLASSINFO + 4) = pl_id(i);
    got = loadLocalClassList(CLASS_PLAYLIST_SONGS);
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? (int)deque_size(list) : 0;
    in->songs = n;
    in->has = pick.on && got > 0 ? picker_in(list) : 0;
    in->nk = grid_mosaic_keys(list, pl.albums, in->key,
                              &miss); /* patch/grid.c: shared with the Songs page's playlist header */
    in->scanned = miss ? PL_SCAN_MISS : 1;
    picker_restore(); /* (the picker keeps the browsing record of the page it is over) */
}

/* ---------------------------------------------------------------------------
 * The loader: one step a tick on the page's own timer (a scan of one playlist, or one source of one mosaic)
 */
static int pl_next_load(void) {
    int lo, hi, a, best = -1, bd = 0x7fffffff;
    if (!pl.g.tiles || !pl.count) return -1;
    pl_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        tile_t *t = pl_find(a);
        int top, d;
        if (pl.info[a].scanned && t && t->art) continue;
        top = pl_top(a);
        d = m1_abs(top + pl_height() / 2 - GRID_VIEW_H / 2);
        if (top >= GRID_VIEW_H || top + pl_height() <= 0) d += 100000;
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int pl_on_load(const void *unused);

static void pl_kick(void) {
    if (!pl.more_timer && pl.view && !pl.bg && (pl.noscroll || pl_next_load() >= 0))
        pl.more_timer = timer_add(pl_on_load, (void *)0, PL_MORE_MS);
}

/* The tile's finished picture is made of the albums the scan found, in the same order: pl_prep would compose it again unchanged. */
static int pl_same_art(const tile_t *t, const info_t *in) {
    int i;
    plc_t c;
    if (t->art != 1 || t->nq != (in->nk > 1 && !pl.tmp ? 1 : in->nk) || t->cov != pl_cover(t->album - 1, &c)) return 0;
    for (i = 0; i < t->nq; ++i)
        if (t->qkey[i] != in->key[i]) return 0;
    return 1;
}

static int pl_on_load(const void *unused) {
    int a;
    (void)unused;
    pl.more_timer = 0;
    if (!pl.view) return RET_OK;
    grid_dir(pl_off(), &pl.seen, &pl.dir);
    if (grid_moving(pl.sv)) {
        pl_kick();
        return RET_OK;
    }
    a = pl_next_load();
    if (a >= 0) {
        tile_t *t = pl_tile(a);
        int top = pl_top(a);
        if (!pl.info[a].scanned) {
            unsigned ck = t->ckey;
            pl_scan(a);
            if (pl_same_art(t, &pl.info[a])) { /* read again (PL_SCAN_MISS), the same albums: the mosaic stays */
                pl_texts(t, a);
                t->ckey = ck, t->fit = 0;
            } else
                pl_prep(t, a);
            pl_loading(t, a);
        } else if (!t->art)
            pl_art(t, a);
        if (top < GRID_VIEW_H && top + pl_height() > 0) pl_redraw();
    }
    pl_kick();
    return RET_OK;
}

static int pl_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pl.view) return RET_OK;
    pl_fade();
    grid_dir(pl_off(), &pl.seen, &pl.dir);
    pl_kick();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The playlists: read when the page opens and each time it comes back to the front
 */
static void pl_size(void) {
    int h = pl_content();
    if (!h) h = GRID_VIEW_H; /* (the empty page hides the view) */
    widget_resize(pl.view, PL_W, h);
    widget_set_prop_int(pl.sv, "virtual_h", h);
}

/* The stock query again and the page rebuilt from it: tiles and scans dropped (they were of the old list) unless the list and the database are as they were. */
static void pl_select(int on);

/* The database's state: modification time (seconds, nanoseconds) and size of the file and of its WAL and journal (a write may land only in those). Every playlist's
 * songs are rows of that file, so an edit anywhere (the stock picker, our pages, the player's own writes) changes it. 0 when the file cannot be read (no signature:
 * nothing is kept). struct stat (MIPS o32): st_size at +0x30, st_mtime at +0x40, its nanoseconds at +0x44. */
static int pl_dbsig(unsigned sig[PL_SIG]) {
    static const char *const path[3] = {PL_DB, PL_DB "-wal", PL_DB "-journal"};
    unsigned st[40];
    int i;
    for (i = 0; i < 3; ++i) {
        memset(st, 0, sizeof st);
        if (__xstat(3, path[i], st) != 0)
            sig[3 * i] = sig[3 * i + 1] = sig[3 * i + 2] = 0xffffffffu;
        else
            sig[3 * i] = st[0x40 / 4], sig[3 * i + 1] = st[0x44 / 4], sig[3 * i + 2] = st[0x30 / 4];
        if (i == 0 && sig[0] == 0xffffffffu) return 0;
    }
    return 1;
}

/* PLAYLISTS_META_FILE's state, as pl_dbsig takes a file's: all ones when there is none. A date order that moved (a playlist was played, a song added) sorts again. */
static void pl_metasig(unsigned sig[3]) {
    unsigned st[40];
    memset(st, 0, sizeof st);
    if (__xstat(3, PLAYLISTS_META_FILE, st) != 0)
        sig[0] = sig[1] = sig[2] = 0xffffffffu;
    else
        sig[0] = st[0x40 / 4], sig[1] = st[0x44 / 4], sig[2] = st[0x30 / 4];
}

static int pl_same_str(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* What a source's playlist row carries besides its id and name (the cover, the song count, the length: the row's REC_META); "" for a stock row. */
static const char *pl_meta(void *rec) { return pl.src ? cc_str(rec, REC_META) : ""; }

/* The freshly read list is the page's: as many rows, the same id, name and content in each (a rename, delete, add, reorder or a changed song count or cover changes one). */
static int pl_same_list(void *old, unsigned oldn, void *fresh, unsigned n) {
    unsigned i;
    if (!old || !fresh || oldn != n) return 0;
    for (i = 0; i < n; ++i) {
        void *a = deque_at(old, i), *b = deque_at(fresh, i);
        if (pl.src ? !pl_same_str(pl.src->rec_id(pl.src, a), pl.src->rec_id(pl.src, b))
                   : I(a, REC_DISC) != I(b, REC_DISC))
            return 0;
        if (!pl_same_str(cc_str(a, REC_TITLE), cc_str(b, REC_TITLE))) return 0;
        if (!pl_same_str(pl_meta(a), pl_meta(b))) return 0;
    }
    return 1;
}

/* The order (the card's rows): pl.ord[k] = the stock playlist shown at position k. Title compares names as the Artist order does (cc_name_keys / cc_key_cmp: digit runs by value, ASCII case
 * folded, a CJK name by its pinyin initials; ties keep the stock order); Z-A is the whole order reversed. A date order puts the newest first (Oldest First reversed) by the time patch/plmeta.c keeps
 * for the playlist (stock id and name); ties go by Title A-Z. A playlist with no such time: Last Played puts it after all the others in both directions; Date Added and Updated rank it by a key of the
 * stock table (pl_keys) below every stamped playlist, so Oldest First is the exact reverse of Newest First. A source's playlists are Title only.
 * The stock list is never reordered. No memory: NULL (the stock order). */
static const char **pl_key __attribute__((section(".scratch")));
static unsigned *pl_when
    __attribute__((section(".scratch"))); /* the time of each stock playlist for the date order, 0 = none */
static unsigned *pl_fb __attribute__((
    section(".scratch"))); /* its key from the stock table when it has no time (Date Added, Updated); NULL: none read */
static unsigned *pl_kmin __attribute__((section(
    ".scratch"))); /* pl_keys' answer by playlist id: the lowest and the highest row id of its songs, 0 = none (an empty playlist) */
static unsigned *pl_kmax __attribute__((section(".scratch")));
static unsigned char pl_unplayed
    __attribute__((section(".scratch"))); /* the last pl_sort was Last Played and no playlist had been played */

static int pl_sort_now(void) { return pl.src ? 0 : pl.sort; }
static int pl_rev_now(void) { return pl.src && pl.sort ? 0 : pl.rev; }

static int pl_cmp(unsigned a, unsigned b) {
    int d, rev = pl_rev_now() != 0;
    if (pl_when) {
        unsigned ta = pl_when[a], tb = pl_when[b];
        if (pl_fb && (!ta || !tb)) {
            if (ta || tb) return (ta != 0) != rev ? -1 : 1; /* a stamp is newer than a key */
            if (pl_fb[a] != pl_fb[b]) return (pl_fb[a] > pl_fb[b]) != rev ? -1 : 1;
        } else if (ta != tb) {
            if (!ta || !tb) return ta ? -1 : 1;
            return (ta > tb) != rev ? -1 : 1;
        }
    }
    d = cc_key_cmp(pl_key[a], pl_key[b]);
    return d ? d : a < b ? -1 : a > b;
}

static const char *pl_ntext(const void *ctx, unsigned i) { return cc_str(deque_at((void *)ctx, i), REC_TITLE); }

/* One row of pl_keys' query: cd_num, min(id), max(id) as text. A row of another shape, or an id out of range, is skipped. */
static unsigned pl_num(const char *s) {
    unsigned v = 0;
    if (!s || !*s) return ~0u;
    for (; *s; ++s) {
        if (*s < '0' || *s > '9' || v > 0x0ccccccc) return ~0u;
        v = v * 10 + (unsigned)(*s - '0');
    }
    return v;
}
static int pl_key_row(void *arg, int n, char **v, char **names) {
    unsigned id, lo, hi;
    (void)arg, (void)names;
    if (n != 3 || !pl_kmin || !pl_kmax) return 0;
    id = pl_num(v[0]), lo = pl_num(v[1]), hi = pl_num(v[2]);
    if (id <= PL_MAX && lo != ~0u && hi != ~0u) pl_kmin[id] = lo, pl_kmax[id] = hi;
    return 0;
}

/* The lowest and the highest row id of every playlist's songs, in ONE read-only statement through the hooked toolsQueryDbTable (our row callback, no argument; it clears *tools_pdeq_directory and
 * touches no list; the Library filter passes a statement that does not read songtable). Rows of a playlist are numbered upward through the table (a new song takes the highest id + 1), so these order
 * the playlists that have no time: Date Added by the lowest, Updated by the highest, an empty one by its own id. 0 when the query failed or there is no memory (the keys stay unread). */
static int pl_keys(void) {
    free(pl_kmin);
    pl_kmin = calloc(2 * (PL_MAX + 1), sizeof *pl_kmin);
    pl_kmax = pl_kmin ? pl_kmin + PL_MAX + 1 : (unsigned *)0;
    if (!pl_kmin) return 0;
    if (toolsQueryDbTable(STOCK_DB_PATH, "select cd_num,min(id),max(id) from playlist where id>100 group by cd_num",
                          (void *)pl_key_row, 0) >= 0)
        return 1;
    free(pl_kmin);
    pl_kmin = pl_kmax = (unsigned *)0;
    return 0;
}

static void pl_sort(void) {
    unsigned n = pl.count > (unsigned)pl_v() ? pl.count - (unsigned)pl_v() : 0, i;
    int sort = pl_sort_now(), title_rev = !sort && pl_rev_now();
    free(pl.ord);
    pl.ord = (unsigned *)0;
    pl_unplayed = 0;
    if (n == 1 && pl.pls &&
        sort == PLM_PLAYED) { /* (one playlist: nothing to order, but the card still says it was never played) */
        plm_read();
        pl_unplayed = !plm_get(I(deque_at(pl.pls, 0), REC_DISC), cc_str(deque_at(pl.pls, 0), REC_TITLE), sort);
    }
    if (n < 2 || !pl.pls) return;
    pl.ord = calloc(n, sizeof *pl.ord);
    pl_key = pl.ord ? cc_name_keys(n, pl_ntext, pl.pls) : (const char **)0;
    pl_when = sort && pl_key ? calloc(n, sizeof *pl_when) : (unsigned *)0;
    pl_fb = (unsigned *)0;
    if (sort && !pl_when) sort = 0; /* no memory for the times: Title */
    if (!pl.ord || !pl_key) {
        free(pl.ord);
        pl.ord = (unsigned *)0;
    } else {
        if (sort) {
            unsigned any = 0, miss = 0;
            plm_read();
            for (i = 0; i < n; ++i)
                any |= pl_when[i] =
                    plm_get(I(deque_at(pl.pls, i), REC_DISC), cc_str(deque_at(pl.pls, i), REC_TITLE), sort),
                       miss |= !pl_when[i];
            pl_unplayed = sort == PLM_PLAYED && !any;
            if (sort != PLM_PLAYED && miss && pl_keys())
                pl_fb /* (every playlist stamped: no query) */ = calloc(n, sizeof *pl_fb);
            for (i = 0; pl_fb && i < n; ++i) {
                unsigned id = (unsigned)I(deque_at(pl.pls, i), REC_DISC);
                pl_fb[i] = id <= PL_MAX ? (pl_kmax[id] ? (sort == PLM_ADDED ? pl_kmin[id] : pl_kmax[id]) : id) : 0;
            }
        }
        for (i = 0; i < n; ++i) pl.ord[i] = i;
        cc_heapsort(pl.ord, n, pl_cmp);
        for (i = 0; title_rev && i < n / 2; ++i) {
            unsigned t = pl.ord[i];
            pl.ord[i] = pl.ord[n - 1 - i], pl.ord[n - 1 - i] = t;
        }
    }
    free(pl_when);
    free(pl_fb);
    free(pl_kmin);
    pl_when = pl_fb = pl_kmin = pl_kmax = (unsigned *)0;
    free((void *)pl_key);
    pl_key = (const char **)0;
}

/* A source's list as the page shows it: a hash of every row's id, name and content (cover, song count, length; the source's gen moves for any fetch anywhere, so it says nothing about this list). */
static unsigned pl_src_sig(void *list) {
    unsigned h = FNV_SEED, i, k;
    for (i = 0; list && i < deque_size(list); ++i) {
        void *r = deque_at(list, i);
        const char *s[3];
        s[0] = pl.src->rec_id(pl.src, r), s[1] = cc_str(r, REC_TITLE), s[2] = pl_meta(r);
        for (k = 0; k < 3; ++k) {
            const unsigned char *p = (const unsigned char *)s[k];
            for (; *p; ++p) h = (h ^ *p) * FNV_PRIME;
            h = (h ^ 0x100) * FNV_PRIME; /* (the field's end: "ab","c" is not "a","bc") */
        }
    }
    return h ? h : 1;
}

/* A source's list that changed (a playlist came, went or was renamed), the page's tiles carried over: each row that is in both lists (same id and name) keeps its tile, its decoded
 * cover and its scan (read again, quietly: the tile's picture stays when the albums are the same), at its new place; only the new rows start empty. `old` is the previous list and
 * `oldord` its name order. 0 when there is no memory (the caller drops everything). */
static int pl_carry(void *old, unsigned oldn, const unsigned *oldord, unsigned newn) {
    int *inv = calloc(oldn ? oldn : 1, sizeof *inv);
    info_t *fresh = calloc(newn ? newn : 1, sizeof(info_t));
    unsigned k, j, hint = 0;
    int i;
    if (!inv || !fresh) {
        free(inv);
        free(fresh);
        return 0;
    }
    for (j = 0; j < oldn; ++j) inv[j] = -1;
    for (
        k = 0; k < newn;
        ++k) { /* the old place of each new row: the next after the last match first (an insert or a delete moves the rest by one), else a search */
        void *r = deque_at(pl.pls, pl_slot(k));
        const char *id = pl.src->rec_id(pl.src, r), *name = cc_str(r, REC_TITLE);
        unsigned t;
        for (t = 0; t < oldn; ++t) {
            unsigned c = (hint + t) % oldn, so = oldord ? oldord[c] : c;
            void *o = deque_at(old, so);
            if (pl_same_str(pl.src->rec_id(pl.src, o), id) && pl_same_str(cc_str(o, REC_TITLE), name)) {
                inv[c] = (int)k, hint = c + 1;
                for (i = 0; i < 4; ++i) fresh[k].key[i] = pl.info[c].key[i];
                fresh[k].nk = pl.info[c].nk,
                fresh[k].songs = pl.info[c].songs; /* (scanned stays 0: read again by the loader) */
                break;
            }
        }
    }
    for (i = 0; i < pl.g.n; ++i) { /* the tiles follow their playlist; a tile of a playlist that is gone is free */
        grid_tile_t *t = &pl.g.tiles[i];
        if (!t->album) continue;
        if (t->album - 1 < (int)oldn && inv[t->album - 1] >= 0)
            t->album = inv[t->album - 1] + 1;
        else {
            grid_free_art(t);
            memset(t, 0, sizeof *t);
        }
    }
    free(pl.info);
    pl.info = fresh;
    free(inv);
    return 1;
}

static void pl_reorder(void);
static void pl_resort(void);

static void pl_load(void) {
    void *list, *old = pl.pls;
    unsigned oldn = pl.count, *oldord = pl.ord, was = pl.count;
    int carry = 0;
    unsigned sig[PL_SIG];
    int have, keep, i, redo = 0;
    unsigned msig[3];
    pl_select(0); /* a page read again is not in select mode (the marks were of the old list) */
    m1_timer_stop(&pl.more_timer);
    pl.pls = (void *)0;
    if (pl.src) { /* the source's own copy; the hash of its rows stands for the database's state */
        memset(sig, 0, sizeof sig);
        pl.gen = pl.src->gen(pl.src);
        pl.rows = ls_gen_rows(pl.src);
        have = 1;
        list = pl.src->list(pl.src, LS_PLAYLISTS, (void *)0);
        if (list && deque_size(list))
            pl.pls = list;
        else if (list)
            deque_destroy(list);
        sig[0] = pl_src_sig(pl.pls);
    } else {
        have = pl_dbsig(sig);
        if (loadLocalClassList(CLASS_PLAYLISTS) > 0) {
            list = *(void **)PDEQ_PLAYLIST;
            if (list && deque_size(list)) pl.pls = cc_copy_list(list);
        }
        picker_restore();
    }
    pl.count = (pl.pls ? deque_size(pl.pls) : 0) + (unsigned)pl_v();
    if (pl.count > PL_MAX + (unsigned)pl_v()) pl.count = PL_MAX + (unsigned)pl_v();
    /* Nothing changed (the same playlists, the database file untouched since the scans were made): the scans and the tiles stay (a visit to a playlist's songs page or a
     * dialog and back does not grey and recompose every mosaic). Any doubt, and everything is dropped. */
    keep = have && pl.have_sig && pl.info && pl.g.tiles && pl.count && oldn == pl.count &&
           pl_same_list(old, oldn - (unsigned)pl_v(), pl.pls, pl.count - (unsigned)pl_v());
    for (oldn = 0; keep && oldn < PL_SIG; ++oldn) keep = sig[oldn] == pl.sig[oldn];
    /* A cover chosen, changed or removed meanwhile (the file's, not the database's): that tile is made again (its scan stays). */
    for (i = 0; keep && i < pl.g.n; ++i) {
        tile_t *t = &pl.g.tiles[i];
        plc_t c;
        if (t->album && t->album - 1 < (int)pl.count && t->cov != pl_cover(t->album - 1, &c)) pl_prep(t, t->album - 1);
    }
    /* The cover cache grows while another page is open (the Cover Flow build): a playlist whose scan found an album without a file is read again, and its
     * tile composed again, by the loader. Complete scans (every album had its file or none) stay: no query, no decode. */
    for (oldn = 0; keep && oldn < pl.count; ++oldn)
        if (pl.info[oldn].scanned == PL_SCAN_MISS) pl.info[oldn].scanned = 0;
    m1_sel_reset(&pl.sel, 0);
    if (!keep) {
        pl.ord = (unsigned *)0; /* (pl_sort frees the order it is given: the old one is kept here for pl_carry) */
        pl_sort();
        carry = pl.src && !pl_v() && old && pl.info && pl.g.tiles && pl.g.placeholder && was && pl.count &&
                pl_carry(old, was, oldord, pl.count);
        if (!carry) {
            grid_drop(&pl.g);
            free(pl.info);
            pl.info = pl.count ? calloc(pl.count, sizeof(info_t)) : (info_t *)0;
            if (pl.count && !pl.info) pl.count = 0;
            for (i = 0; pl.info && i < pl_v(); ++i)
                pl.info[i].scanned =
                    !i; /* New playlist: nothing to read; Favourites: the loader reads what it holds (pl_scan) */
            grid_placeholder(&pl.g);
        }
        free(oldord);
    }
    if (old) deque_destroy(old);
    pl.have_sig = have;
    memcpy(pl.sig, sig, sizeof pl.sig);
    pl_metasig(msig);
    redo = keep && pl_sort_now() &&
           (msig[0] != pl.msig[0] || msig[1] != pl.msig[1] ||
            msig[2] != pl.msig[2]); /* nothing else changed, but a time did: the order may be another */
    memcpy(pl.msig, msig, sizeof msig);
    m1_sel_reset(&pl.sel, pl.count); /* none: no select mode (the menu's Delete opens the stock page) */
    {
        int st = pl.src && !pl.count && pl.src->state ? pl.src->state(pl.src, LS_PLAYLISTS, (void *)0) : LS_ST_READY;
        m1_show(pl.view, 1); /* (the large title stays when there are no rows) */
        ls_room(pl.status, pl.spin, LS_ROOM_NAV + SG_TITLE_H);
        m1_show(pl.status, pl.count == 0 && !(st == LS_ST_LOADING && pl.spin));
        ls_spin(pl.spin, st == LS_ST_LOADING && pl.count == 0 && pl.spin != (void *)0);
        if (!pl.count) widget_set_tr_text(pl.status, pl.src ? ls_empty_key(st, "No playlists") : "No playlists");
    }
    pl_size();
    pl.dir = 1;
    pl.seen = pl_off();
    pl_redraw();
    pl_kick();
    if (redo) pl_resort();
}

/* The card's Name row: the order changes (pl.rev is set). The playlists are put in the new order and every playlist keeps its scan (info follows its playlist); the tiles are made again for the
 * new places and the list goes back to the top. Where the scans cannot be carried over (no memory) the page reads everything again. */
static void pl_reorder(void) {
    unsigned n = pl.count > (unsigned)pl_v() ? pl.count - (unsigned)pl_v() : 0, k, v = (unsigned)pl_v(), *old = pl.ord,
             *inv = (unsigned *)0;
    info_t *fresh = (info_t *)0;
    void *wa = P(pl.sv, SC_WA);
    pl.ord = (unsigned *)0;
    pl_sort();
    if (n && pl.info) {
        inv = calloc(n, sizeof *inv);
        fresh = calloc(pl.count, sizeof(info_t));
    }
    if (!inv || !fresh) {
        free(inv);
        free(fresh);
        free(old);
        pl.have_sig = 0; /* nothing is kept: pl_load makes the page again (with pl.rev) */
        pl_load();
        return;
    }
    for (k = 0; k < n; ++k) inv[old ? old[k] : k] = k; /* the stock playlist -> where it was shown */
    for (k = 0; k < v + n; ++k) { /* (field by field: a struct assignment would call memcpy) */
        const info_t *from = &pl.info[k < v ? k : v + inv[pl_slot(k - v)]];
        int j;
        for (j = 0; j < 4; ++j) fresh[k].key[j] = from->key[j];
        fresh[k].nk = from->nk, fresh[k].songs = from->songs, fresh[k].scanned = from->scanned,
        fresh[k].has = from->has;
    }
    free(pl.info);
    pl.info = fresh;
    free(inv);
    free(old);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING &&
        P(wa, SC_AN_WIDGET) == pl.sv) { /* a coasting list stops (patch/scroll.c sc_down) */
        widget_animator_destroy(wa);
        stock_scroll_done(pl.sv, (void *)0);
    }
    m1_timer_stop(&pl.more_timer);
    pl.press = pl.down = 0, pl.dir = 1;
    grid_drop(&pl.g); /* the tiles were of the other places */
    if (pl.g.tiles) grid_placeholder(&pl.g);
    widget_set_prop_int(pl.sv, "yoffset", 0);
    pl.seen = pl_off();
    pl_fade();
    pl_redraw();
    pl_kick();
}

/* A date order after a read that kept everything else: the playlists are put in the order the times give now, only when that is another one (the list stays where it is otherwise). */
static void pl_resort(void) {
    unsigned n = pl.count > (unsigned)pl_v() ? pl.count - (unsigned)pl_v() : 0, k, *old = pl.ord;
    int same = 1;
    pl.ord = (unsigned *)0;
    pl_sort();
    for (k = 0; k < n; ++k)
        if ((old ? old[k] : k) != (pl.ord ? pl.ord[k] : k)) same = 0;
    free(pl.ord);
    pl.ord = old;
    if (!same) pl_reorder();
}

/* ---------------------------------------------------------------------------
 * Touch: a tap on a cell opens the playlist in the stock songs page
 */
static int pl_cell_at(int x, int y) {
    int a;
    y -= PL_TOP; /* (the title block above the rows is no cell) */
    if (y < 0 || y >= pl_rows_h()) return -1;
    if (!pl.list) return grid_cell_at(x, y, GRID_ROW_GAP, (int)pl.count);
    a = y / LIST_ROW_H; /* a list row: any x */
    return a < (int)pl.count ? a : -1;
}

static int pl_item_of(void *e) {
    int pt[2];
    grid_ev_local(pl.view, e, pt);
    return pl_cell_at(pt[0], pt[1]);
}

/* Our Songs page on the playlist (patch/songs.c songs_open_playlist: its name the title, its id in classinfo[1]); a page that does not open leaves the
 * stock Playlists page's row handler (@0x53d300, mode 0): the name for the page's title, the id into classinfo[1], then the stock Songs page with the
 * playlist class. Back returns here. */
static void pl_create(void);
static void pl_pick_add(int id, int have, const char *name);
static void pl_pick_later(int id, const char *name);
static void pl_new_later(int id, const char *name);

/* A tap on a source's playlist: its Songs page; if that page does not open, the playlist plays in order (the tap of a row). */
static void pl_open_src(void *rec) {
    void *list;
    if (songs_open_src_in(pl.src, LS_PLAYLISTS, rec, cc_str(rec, REC_TITLE)) == 0) return;
    list = pl.src->list(pl.src, LS_PLAYLISTS, rec);
    if (!list) return;
    so_play_src(pl.src, CLASS_PLAYLIST_SONGS, list, 0, LS_PLAY_ORDER, pod_open_player);
    deque_destroy(list);
}

static void pl_open(int i) {
    void *rec;
    if (pl_v()) { /* the picker: New playlist (row 0), Favourites (row 1), or the add to that playlist */
        if (i == 0)
            pl_create();
        else if (pl_full(i)) /* every song being added is there: said, and the picker stays for another choice */
            pod_toast(TR(i == 1 ? "Already in Favorites" : "Already in Playlist"));
        else
            pl_pick_add(i == 1 ? PICKER_FAVOURITES : pl_id(i), pl.info[i].has,
                        i == 1 ? "" : cc_str(pl_rec(i), REC_TITLE));
        return;
    }
    rec = pl_rec(i);
    if (pl.src) {
        pl_open_src(rec);
        return;
    }
    if (songs_open_playlist(I(rec, REC_DISC), cc_str(rec, REC_TITLE)) != -1) return;
    snprintf((char *)NAV_TITLE, 0x200, "%s", cc_str(rec, REC_TITLE));
    *(int *)(CLASSINFO + 4) = I(rec, REC_DISC);
    navigator_to_with_context("allmusic_page", (const void *)CLASS_PLAYLIST_SONGS);
}

/* ---------------------------------------------------------------------------
 * Select mode (the menu's Delete Playlists), in the Songs page's manner (patch/songs.c, docs/modules/songs.md "Select"): the navbar's Back becomes the x, the title
 * "N Selected", Select All at the right, a mark on every cell or row, a bar below with the Delete pill. Delete runs the stock handler's sequence (@0x53dbcc) on the
 * stock selection vector, which the page fills from its own marks at that moment.
 */
static void pl_head(void) { /* the navbar's title: "N Selected" in select mode, else Playlists */
    if (!pl.title) return;
    if (!pl.select) {
        widget_set_tr_text(pl.title, pl_v() ? "Add to Playlist" : "Playlists");
        return;
    }
    m1_sel_head(&pl.sel);
}

/* The select mode is there when the asset has its widgets, the marks decoded and the selection bitset exists. */
static int pl_select_ok(void) {
    if (pl.src) return 0;
    return pl.btn_selall && pl.bar && pl.del && pl.sel.mark[0] && pl.sel.mark[1] && pl.sel.bits && pl.count;
}

static void pl_select(int on) {
    int i, max;
    void *nav[3];
    if (on == pl.select) return;
    pl.select = on;
    pl.press = pl.down = 0;
    nav[0] = pl.btn_more, nav[1] = pl.np;
    for (i = 0; i < 2; ++i) m1_show(nav[i], !on);
    m1_show(pl.btn_plactions, !on);
    m1_sel_enter(&pl.sel, on, NAV_CF_X);
    pl_head();
    pl_retext();
    pl_size();
    max = pl_max_scroll();
    if (pl_off() > max) widget_set_prop_int(pl.sv, "yoffset", max);
    pl_fade();
    pl_redraw();
}

static void pl_toggle(int i) {
    if (!m1_sel_toggle(&pl.sel, i)) return;
    pl_head();
    pl_redraw();
}

static int pl_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pl.select || !pl.sel.bits) return RET_OK;
    m1_sel_toggle_all(&pl.sel);
    pl_head();
    pl_redraw();
    return RET_OK;
}

static int pl_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pl.select)
        pl_select(0);
    else
        navigator_back();
    return RET_OK;
}

/* The long press sheet (docs/modules/pins.md): the library's page only (not a source's, not the picker, not select mode, not under a card), a playlist of the stock list. */
static void *pl_pin_rec(int a) {
    if (!pl.rm.on || pl.src || pl_v() || pl.select || pl.menu || pl.vs.on || a < 0 || a >= (int)pl.count)
        return (void *)0;
    return pl_rec(a);
}

/* A row of the sheet (it has closed): Play, Shuffle, Pin Playlist / Unpin Playlist, Add to Playlist, Play Next, Play After for the playlist it was opened on (pins_playlist_act for all but the pin, which
 * needs the page's cover keys). The scans run in this thread's ticks, so none is between the row and the player. */
static void pl_sheet(int a, int act) {
    void *rec = pl_pin_rec(a);
    const char *name;
    int id;
    unsigned nk;
    if (!rec || !pl.info) return;
    id = I(rec, REC_DISC), name = cc_str(rec, REC_TITLE);
    if (act == RMA_PIN) {
        if (pins_has_playlist(id, name))
            pins_unpin_playlist(id, name);
        else {
            nk = (unsigned)pl.info[a].nk;
            pins_pin_playlist(id, name, pl.info[a].key, nk > 4 ? 4 : nk);
        }
    } else
        pins_playlist_act(id, name, act);
}

/* A press held RM_LONG_MS on a playlist: the sheet opens while the finger is down; the press is forgotten, so the release opens nothing. */
static void pl_on_hold(int a) {
    void *rec = pl_pin_rec(a);
    pl.down = 0;
    if (pl.list) grid_set_press(&pl.press, 0, pl.sv);
    if (!rec || pl.bg) return;
    rowmenu_open_playlist(&pl.rm, a, pins_has_playlist(I(rec, REC_DISC), cc_str(rec, REC_TITLE)), pl_sheet);
}

static int pl_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    pl.down = 0;
    if (!e || !pl.view) return RET_OK;
    a = pl_item_of(e);
    pl.down = a + 1, m1_tap_at(&pl.tap, e);
    if (pl.list && !pl.select) grid_set_press(&pl.press, a + 1, pl.sv);
    if (a >= 0 && pl_pin_rec(a)) rowmenu_hold_start(a, pl_on_hold);
    return RET_OK;
}

static int pl_on_move(void *ctx, void *e) {
    (void)ctx;
    if (pl.down && e) rowmenu_hold_move(&pl.tap, e); /* a drift of SC_DRAG_PX or more is a drag, not a long press */
    return RET_OK;
}

static int pl_on_up(void *ctx, void *e) {
    int a = pl.down - 1;
    (void)ctx;
    rowmenu_hold_stop();
    pl.down = 0;
    if (pl.list) grid_set_press(&pl.press, 0, pl.sv);
    if (a < 0 || !e || !pl.view) return RET_OK;
    if (m1_tap_near(&pl.tap, e) && pl_item_of(e) == a) {
        if (pl.select)
            pl_toggle(a);
        else
            pl_open(a);
    }
    return RET_OK;
}

static int pl_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rowmenu_hold_stop();
    pl.down = 0;
    if (pl.list) grid_set_press(&pl.press, 0, pl.sv);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The "..." card (patch/viewsort.c): New Playlist, Import, Export and Delete Playlists, then Grid / List, then Title, Date Added, Last Played, Updated. New playlist, Import and Export run the
 * stock code and the page reads the playlists again; Delete is select mode (above); Grid and List switch the view in place (below); the four sort rows set the order (below).
 */
#define PL_ROWS_MORE \
    (VS_WITH_VIEWS | VS_ALL_SORTS) /* the "..." card: Grid, List, then the four sort rows (slots 0..3) */
#define PL_ROWS_MORE_SRC (VS_WITH_VIEWS | 1u << 0) /* a source's: Title only */
#define PL_ROWS_ACTIONS \
    (VS_WITH_SEARCH | VS_WITH_SELECT | VS_WITH_ACT2 | \
     VS_WITH_ACT3) /* the list-plus button's card: New Playlist, Import, Export, Delete Playlists (slots 6..9) */

/* Closes the open card, or opens card `kind` (1 the "..." card, 2 the list-plus button's: the one card's rows offered again). */
static void pl_menu_kind(int kind) {
    pl.menu = kind;
    if (kind) vs_offer(&pl.vs, kind == 1 ? (pl.src ? PL_ROWS_MORE_SRC : PL_ROWS_MORE) : PL_ROWS_ACTIONS);
    vs_menu(&pl.vs, kind != 0, pl_sort_now(), pl_rev_now(), pl.list);
}
static void pl_menu(int on) { pl_menu_kind(on ? 1 : 0); }

/* The stock one-line message box, as the stock Playlists page shows "full" and "exists" (@0x53e97c, @0x53e9f8). */
static void pl_toast(const char *text) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = MSGINFO_KIND;
    info.ms = MSGINFO_MS;
    for (i = 0; text[i] && i < sizeof info.text - 1; ++i) info.text[i] = text[i];
    navigator_to_with_context("dialog/msginfo_dialog", &info);
}

/* Done on our keyboard (patch/keyboard.c; not modal: it calls this after the keyboard page was told to close, the name trimmed, 1 to 63 bytes): the
 * stock create handler's tail (@0x53e8e4): the stock list is read first, createPlayListItem adds the playlist to the database (-1 full, -2 exists),
 * the stock message box for those two, and this page, which is in front again (or about to be: the other order only reads twice), reads its list again. */
static void pl_named(const char *name) {
    int r;
    loadLocalClassList(CLASS_PLAYLISTS);
    r = createPlayListItem(*(void **)PDEQ_PLAYLIST, name);
    picker_restore();
    if (r >= 0) plm_added(r, name); /* its Date Added (a failed write only leaves it without one) */
    if (r == -1)
        pl_toast(TR("msg_playlistfull"));
    else if (r == -2)
        pl_toast(TR("msg_playlistexist"));
    else if (
        r >= 0 && pl_v() &&
        pl.win) { /* the picker: the new playlist gets the songs, the page closes, once the keyboard page has gone (pl_pick_later) */
        pl_pick_later(r, name);
        return;
    }
    if (pl.win && pl.view) pl_load();
    if (r >= 0 && pl.win && !pl_v()) pl_new_later(r, name);
}

/* What stock Import reads (importPlayList @0x4ef394 through toolsGetDirectoryM3u8 @0x5e9794): the regular files (d_type 8) of this folder ending .m3u8 or .m3u, any case, in readdir
 * order. Each is made a playlist by createPlayListItem @0x4eeca8, named after the file without its last extension cut to PL_IMPORT_NAME bytes (snprintf into 0x40; an empty one is
 * "Playlist<its id>"), at the lowest free id. Before that checkPlayListByName @0x4ef2e4 deletes, with its songs, the playlist whose name is the whole uncut one: so a file whose name
 * is longer is never a replacement, each Import makes another playlist of the cut name. createPlayListItem returns -1 only at 100 playlists: Import stops there, returning 1. */
#define PL_IMPORT_DIR "/mnt/mmc/_explaylist_data"
#define PL_DT_REG 8
#define PL_IMPORT_NAME 63

/* name is the text from fn up to (not including) end. */
static int pl_same_span(const char *name, const char *fn, const char *end) {
    while (fn < end && *name == *fn) ++name, ++fn;
    return fn == end && !*name;
}

/* Whether the first n playlists of list have one with this id and this name. */
static int pl_has_pair(void *list, unsigned n, int id, const char *name) {
    unsigned i;
    for (i = 0; i < n; ++i)
        if (I(deque_at(list, i), REC_DISC) == id && pl_same_str(cc_str(deque_at(list, i), REC_TITLE), name)) return 1;
    return 0;
}

/* Takes for a file the first playlist Import made that is not taken yet and has the name stock gave it: fn up to end, or for an empty one (fn == end) "Playlist<its id>". */
static int pl_take_made(void *list, unsigned m, const unsigned char *made, unsigned char *used, const char *fn,
                        const char *end) {
    char gen[16];
    unsigned i;
    for (i = 0; i < m; ++i) {
        const char *nm = cc_str(deque_at(list, i), REC_TITLE);
        if (!made[i] || used[i]) continue;
        if (fn == end) snprintf(gen, sizeof gen, "Playlist%d", I(deque_at(list, i), REC_DISC));
        if (fn == end ? pl_same_str(nm, gen) : pl_same_span(nm, fn, end)) return used[i] = 1, (int)i;
    }
    return -1;
}

/* After importPlayList ran: the stock list read again against this page's copy, read before (nothing else changes the list in between). A playlist (id, name) the copy did not have is
 * one Import made: new (its Date Added), or the replacement of the copy's playlist of that name that is gone (its times move to the new id). One the copy had is as it was, unless
 * its file was imported and stock made it again under the same id (Updated). One write. */
static void pl_stamp_imported(void) {
    void *list, *d;
    char *ent;
    int id[PL_MAX], was[PL_MAX], from[PL_MAX];
    const char *name[PL_MAX];
    unsigned char made[PL_MAX], used[PL_MAX], hit[PL_MAX], took[PL_MAX];
    unsigned i, j, n = 0, m, old = pl.pls ? deque_size(pl.pls) : 0;
    int k;
    if (loadLocalClassList(CLASS_PLAYLISTS) <= 0) return;
    list = *(void **)PDEQ_PLAYLIST;
    m = list ? deque_size(list) : 0;
    if (m > PL_MAX) m = PL_MAX;
    if (old > PL_MAX) old = PL_MAX;
    memset(used, 0, sizeof used), memset(hit, 0, sizeof hit), memset(took, 0, sizeof took);
    for (i = 0; i < m; ++i) from[i] = -1;
    for (i = 0; i < m; ++i)
        made[i] = !pl_has_pair(pl.pls, old, I(deque_at(list, i), REC_DISC), cc_str(deque_at(list, i), REC_TITLE));
    /* The folder once, in stock's order, each file taking what stock did with it, to find where stock stopped and which playlists it made again under their own id. Every file stock
     * reached has its playlist now (made empty when its songs are not found); the first that has none is where it stopped (100 playlists): it and the files after it were not
     * imported. A cut or empty name is never a replacement: its file takes one playlist Import made. A whole name takes the copy's playlist of that name that is gone (deleted, made
     * again under another id: one playlist Import made), else one still there (made again under its own id: Updated), else one playlist Import made. */
    if (m && (d = opendir(PL_IMPORT_DIR)) != (void *)0) {
        while ((ent = readdir(d)) != (char *)0) {
            const char *fn = ent + 11, *dot = strrchr(fn, '.'); /* (struct dirent: d_type at 10, d_name at 11) */
            if ((unsigned char)ent[10] != PL_DT_REG || !dot || (strcasecmp(dot, ".m3u8") && strcasecmp(dot, ".m3u")))
                continue;
            if (dot == fn || dot - fn > PL_IMPORT_NAME) {
                if (pl_take_made(list, m, made, used, fn, dot == fn ? fn : fn + PL_IMPORT_NAME) < 0) break;
                continue;
            }
            for (i = 0; i < m && !pl_same_span(cc_str(deque_at(list, i), REC_TITLE), fn, dot); ++i) {
            }
            if (i == m) break;
            for (j = 0; j < old; ++j) {
                void *o = deque_at(pl.pls, j);
                if (!took[j] && pl_same_span(cc_str(o, REC_TITLE), fn, dot) &&
                    !pl_has_pair(list, m, I(o, REC_DISC), cc_str(o, REC_TITLE)))
                    break;
            }
            if (j < old) { /* the copy's playlist of this name is gone: the playlist this file made replaces it */
                took[j] = 1;
                if ((k = pl_take_made(list, m, made, used, fn, dot)) >= 0) from[k] = I(deque_at(pl.pls, j), REC_DISC);
                continue;
            }
            for (i = 0; i < m && (made[i] || hit[i] || !pl_same_span(cc_str(deque_at(list, i), REC_TITLE), fn, dot));
                 ++i) {
            }
            if (i < m)
                hit[i] = 1;
            else
                pl_take_made(list, m, made, used, fn, dot);
        }
        closedir(d);
    }
    for (i = 0; i < m; ++i) {
        void *r = deque_at(list, i);
        const char *nm = cc_str(r, REC_TITLE);
        int w = -1;
        if (!made[i] && !hit[i]) continue; /* there before and not imported: as it was */
        if (hit[i])
            w = I(r, REC_DISC);
        else if (from[i] >= 0)
            w = from[i]; /* the playlist its file replaced */
        else
            for (j = 0; j < old && w < 0; ++j) { /* (a file the folder walk did not see) */
                void *o = deque_at(pl.pls, j);
                if (took[j] || !pl_same_str(cc_str(o, REC_TITLE), nm) || pl_has_pair(list, m, I(o, REC_DISC), nm))
                    continue;
                took[j] = 1,
                w = I(o, REC_DISC); /* the copy's playlist of this name, gone and not taken by a file: replaced */
            }
        id[n] = I(r, REC_DISC), name[n] = nm, was[n++] = w;
    }
    plm_imported(n, id, name, was);
}

/* The picker's add (patch/picker.c: batch_add_file, the message), then the page closes as the stock picker's handler closes its window (window_close on the row's window). */
static void pl_pick_add(int id, int have, const char *name) {
    void *win = pl.win;
    picker_add(id, have, name);
    if (win) window_close(win);
}

/* The keyboard calls pl_named from its own click handler right after navigator_back, so its window is still going (its close animation, its widgets about to be destroyed
 * under the handler). The add, its message dialog and the picker's own window_close are three more window operations on top of that; they wait PL_PICK_MS on a timer of the
 * picker's page (removed with it), when the keyboard is gone and the picker is the front window. */
static int pl_pick_fire(const void *unused) {
    (void)unused;
    pick.timer = 0;
    if (pick.on && pl.win) pl_pick_add(pick.id, 0, pick.name);
    return RET_OK;
}

static void pl_pick_later(int id, const char *name) {
    if (pick.timer) return;
    pick.id = id;
    snprintf(pick.name, sizeof pick.name, "%s", name);
    pick.timer = timer_add(pl_pick_fire, (void *)0, PL_PICK_MS);
    if (!pick.timer) pl_pick_add(id, 0, name); /* no timer: now */
}

/* The new playlist's own page (empty: its Add Songs row, patch/songs.c), as a tap on its row opens it; PL_PICK_MS after the keyboard's Done, for the reason pl_pick_later waits.
 * Nothing when the Playlists page is not the front window by then. */
static int pl_new_fire(const void *unused) {
    (void)unused;
    pl_new.timer = 0;
    if (pl.win && m1_is_top(pl.win)) songs_open_playlist(pl_new.id, pl_new.name);
    return RET_OK;
}

static void pl_new_later(int id, const char *name) {
    if (pl_new.timer) return;
    pl_new.id = id;
    snprintf(pl_new.name, sizeof pl_new.name, "%s", name);
    pl_new.timer = timer_add(pl_new_fire, (void *)0, PL_PICK_MS);
}

static void pl_create(void) {
    keyboard_open(TR("playlist_create"), TR("msg_newplaylists"), (const char *)0, pl_named, (kb_cancel_fn)0, KB_DONE);
}

/* The stock confirm dialog of the stock delete handler (@0x53dc78: kind 1, the text at +8, msg_delplaylist): modal; 0xa (CONFIRM_YES) is Yes, anything else ends it (@0x53dcc0). */
static int pl_ask(const char *text) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = 1;
    for (i = 0; text[i] && i < sizeof info.text - 1; ++i) info.text[i] = text[i];
    return pod_confirm_dialog(&info) == CONFIRM_YES;
}

/* Import: the stock row's handler (@0x53dedc) run here, so the page knows the answer: the stock confirm (msg_importplaylist; Yes 0xa), importPlayList, then its message box (-2
 * msg_nottf, -6 msg_notplaylist, else msg_importsuccess). No, or nothing imported, stamps nothing. */
static void pl_import(void) {
    int r;
    if (!pl_ask(TR("msg_importplaylist"))) return;
    r = importPlayList();
    if (r != -2 && r != -6) pl_stamp_imported();
    pl_toast(TR(r == -2 ? "msg_nottf" : r == -6 ? "msg_notplaylist" : "msg_importsuccess"));
}

/* The page's marks into the stock selection: a vector of ints as long as *pdeq_playlist, 1 for each selected row. The stock list is read first (another page's
 * query may have replaced it) and must be what the page shows (as many playlists, the same ids in the same order): else nothing is selected and the page reads again. */
static int pl_stock_selection(void) {
    void *list;
    unsigned i, n;
    if (loadLocalClassList(CLASS_PLAYLISTS) <= 0 || !*(void **)SEL_VEC) return 0;
    list = *(void **)PDEQ_PLAYLIST;
    n = list ? deque_size(list) : 0;
    if (!n || !pl.pls || n != deque_size(pl.pls)) return 0;
    for (i = 0; i < n; ++i)
        if (I(deque_at(list, i), REC_DISC) != I(deque_at(pl.pls, i), REC_DISC))
            return 0; /* (stock positions: the page may show them in the name order) */
    select_recordinit((int)n);
    for (i = 0; i < pl.count && i < n; ++i)
        if (m1_sel_is(&pl.sel, (int)i))
            set_selectindex((int)pl_slot(i)); /* the mark of a displayed row is of its stock playlist */
    return 1;
}

/* The selected playlists the stock delete took out: their chosen covers and their times go (the page's list is still the one they were selected in; a playlist the stock list still
 * has stays). */
static void pl_forget_deleted(void) {
    int id[PL_MAX];
    const char *name[PL_MAX];
    void *list;
    unsigned i, j, n, gone = 0;
    if (pl.src || loadLocalClassList(CLASS_PLAYLISTS) < 0) return;
    list = *(void **)PDEQ_PLAYLIST;
    n = list ? deque_size(list) : 0;
    for (i = (unsigned)pl_v(); i < pl.count && gone < PL_MAX; ++i) {
        if (!m1_sel_is(&pl.sel, (int)i)) continue;
        for (j = 0; j < n && I(deque_at(list, j), REC_DISC) != pl_id((int)i); ++j) {
        }
        if (j < n) continue;
        id[gone] = pl_id((int)i), name[gone] = cc_str(pl_rec((int)i), REC_TITLE);
        plc_forget(id[gone], name[gone]);
        ++gone;
    }
    plm_forget_many(gone, id, name);
}

/* Delete: the stock handler's sequence (@0x53dbcc): nothing selected is the message msg_delplaylistfailed; the confirm dialog (msg_delplaylist; Yes 0xa); then
 * batch_delete_file(0xf00b, *pdeq_playlist, the selection, 0, 0), which runs deletePlaylist and deleteAllMusicByPlaylist for each selected row; the message
 * msg_delplaylistsuccess. The stock page rebuilds its list afterwards: this page reads it again (pl_load ends select mode). */
static int pl_on_delete(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pl.select) return RET_OK;
    if (!pl.sel.nsel) {
        pl_toast(TR("msg_delplaylistfailed"));
        return RET_OK;
    }
    if (!pl_ask(TR("msg_delplaylist"))) return RET_OK;
    if (pl_stock_selection()) {
        batch_delete_file(CLASS_PLAYLISTS, *(void **)PDEQ_PLAYLIST, *(void **)SEL_VEC, 0, 0);
        pl_forget_deleted();
        pl_toast(TR("msg_delplaylistsuccess"));
    }
    pl_load();
    return RET_OK;
}

static int pl_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pl.view && pl.menu != 2)
        pl_menu_kind(
            pl.menu ? 0 : 1); /* (a tap while the list-plus button's card is open is ignored: one card at a time) */
    return RET_OK;
}

static int pl_on_actions(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pl.view && !pl.menu && !pl.select && !pl.src) pl_menu_kind(2);
    return RET_OK;
}

static int pl_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pl_menu(0);
    return RET_OK;
}

enum { PL_NEW, PL_IMPORT, PL_EXPORT, PL_DELETE };

static void pl_set_mode(int list);

/* A tap on a card row: the slots 6..9 are the page's actions (VS_SEARCH + PL_NEW ..), 4 and 5 Grid and List, 0..3 the sort rows: a row sets its order in its default direction (Title A-Z, the dates
 * Newest First), the ticked row again reverses it. */
static int pl_on_item(void *ctx, void *e) {
    int which = (int)(long)ctx;
    (void)e;
    pl_menu(0);
    if (!pl.view) return RET_OK;
    if (which == VS_SORTS || which == VS_SORTS + 1) { /* Grid, List: the mode in place, saved */
        int list = which == VS_SORTS + 1;
        if (list != pl.list && pl.g.tiles) {
            pl_set_mode(list);
            home_write_atomic(PLAYLISTS_FILE, list ? "0\n" : "1\n");
        }
        return RET_OK;
    }
    if (which >= 0 && which < VS_SORTS) { /* a sort row; saved first (a save that fails changes nothing) */
        int rev = which == pl_sort_now() ? !pl_rev_now() : 0;
        char text[3];
        text[0] = (char)((rev ? 'a' : '0') + which), text[1] = '\n', text[2] = 0;
        if (home_write_atomic(PLAYLISTS_SORT_FILE, text) != 0) return RET_OK;
        pl.sort = which, pl.rev = rev;
        pl_reorder();
        if (pl_unplayed) pod_toast(TR("No playlists played yet")); /* (only on the user's own choice of the order) */
        return RET_OK;
    }
    which -= VS_SEARCH;
    if (pl.src) return RET_OK; /* New Playlist, Import, Export, Delete Playlists are the stock library's */
    *(int *)NAVIGATION_STATUS = 0; /* the stock pages' normal (not multi-select) mode: export all */
    if (which == PL_NEW) {
        pl_create(); /* the keyboard is not modal: pl_named reads the list when the name is in */
        return RET_OK;
    } else if (which == PL_IMPORT) {
        pl_import();
    } else if (which == PL_EXPORT)
        stock_playlist_export((void *)0, (void *)0);
    else { /* Delete Playlists: select mode on this page (nothing to select with no playlist); where it cannot be (the asset or the marks lack it) the stock Playlists page, whose multi-select deletes */
        if (!pl.count) return RET_OK;
        if (!pl_select_ok())
            pod_home_open(HOME_PLAYLIST);
        else
            pl_select(1);
        return RET_OK;
    }
    pl_load();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The page
 */
/* A source's page watches its gen: the data changed, the page reads again (the playlists whose cover was asked for are read again by the shared cover poll, pl_cp_ask). */
static int pl_on_gen(const void *unused) {
    unsigned g;
    (void)unused;
    if (!pl.src || !pl.view || pl.bg) return RET_REPEAT;
    g = pl.src->gen(pl.src);
    if (g != pl.gen && ls_gen_rows(pl.src) == pl.rows) { /* only a download's progress moved: no playlist changed */
        pl.gen = g;
        return RET_REPEAT;
    }
    if (g != pl.gen) {
        pl_load();
        return RET_REPEAT;
    }
    return RET_REPEAT;
}

/* ctx is the event's window: while the picker is up pl is the picker's state, and the page below it (playlists_pick) has its own in the stash. */
static int pl_on_fg(void *ctx, void *e) {
    (void)e;
    if (ctx != pl.win) return RET_OK;
    pl.bg = 0;
    if (pl.view && pl.g.tiles) pl_load();
    return RET_OK;
}

/* Behind another window (the stock songs page of a playlist, a dialog) the loader stops: a scan sets classinfo[1] and replaces *pdeq_showlist,
 * the list the songs page draws its rows from and plays. The to-foreground reads everything again and restarts it. */
static int pl_on_bg(void *ctx, void *e) {
    if (ctx != pl.win) return RET_OK;
    pl.bg = 1;
    rowmenu_close(&pl.rm);
    m1_timer_stop(&pl.more_timer);
    return pl_on_abort(ctx, e);
}

/* ---------------------------------------------------------------------------
 * The view toggle (the Albums page's, docs/modules/albums.md): the grid or the list, switched in place and saved
 */
static int pl_use_grid(void) { return set_read(PLAYLISTS_FILE, '1') != '0'; }

/* The covers of a mode: GRID_COVER px with GRID_R corners blended into black, or LIST_ART px with LIST_R corners cut in the alpha (a pressed row lies behind). */
static void pl_shape(int list) { grid_shape(&pl.g, list ? LIST_ART : GRID_COVER, list ? LIST_R : GRID_R, list); }

static int pl_first(void) {
    int a = pl.list ? pl_coff() / LIST_ROW_H : pl_row_of(pl_coff()) * GRID_COLS;
    if (a > (int)pl.count - 1) a = (int)pl.count - 1;
    return a < 0 ? 0 : a;
}

/* Switches the mode in place; the first playlist in view stays at the top. */
static void pl_set_mode(int list) {
    int first = pl_first(), max;
    void *wa = P(pl.sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING &&
        P(wa, SC_AN_WIDGET) == pl.sv) { /* a coasting list stops (patch/scroll.c sc_down) */
        widget_animator_destroy(wa);
        stock_scroll_done(pl.sv, (void *)0);
    }
    m1_timer_stop(&pl.more_timer);
    pl.list = list, pl.press = 0, pl.down = 0, pl.dir = 1;
    grid_drop(&pl.g); /* the tiles were made for the other shape */
    pl_shape(list);
    if (pl.g.tiles) grid_placeholder(&pl.g);
    pl_size();
    max = pl_max_scroll();
    /* the first playlist in view stays at the top, the title block above it; the first playlist itself = the top, with the title */
    first = !first ? 0 : PL_TOP + (list ? first * LIST_ROW_H : first / GRID_COLS * PITCH);
    widget_set_prop_int(pl.sv, "yoffset", first > max ? max : first);
    pl.seen = pl_off();
    pl_fade();
    pl_redraw();
    pl_kick();
}

static int pl_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    m1_timer_stop(&pl.more_timer);
    m1_timer_stop(&pl.gen_timer);
    ls_cover_end(&pl.cp);
    ls_spin_end(pl.spin);
    grid_free(&pl.g);
    if (pl.pls) deque_destroy(pl.pls);
    if (pl.albums) deque_destroy(pl.albums);
    free(pl.info);
    free(pl.ord);
    m1_sel_free(&pl.sel);
    rowmenu_free(&pl.rm);
    free(pl.tmp);
    memset(&pl, 0, sizeof pl);
    m1_timer_stop(&pick.timer);
    m1_timer_stop(&pl_new.timer);
    if (pick.star) bitmap_destroy(pick.star);
    if (pick.tick) bitmap_destroy(pick.tick);
    pick.star = pick.tick = (void *)0;
    if (pick.on) { /* the picker's page: its copies freed, the page below it (if there was one) as it was */
        pick.on = 0;
        picker_release();
    }
    if (pick.stash) {
        memcpy(&pl, pick.stash, sizeof pl);
        free(pick.stash);
        pick.stash = (void *)0;
    }
    return RET_OK;
}

/* 0 once the page is up, -1 if the window could not open, -2 if the asset is not ours (the page is left again). */
static int pl_on_gen(const void *unused);

static int pl_open_page(const lib_src_t *src) {
    if (pl.win) return -1;
    memset(&pl, 0, sizeof pl);
    pl.src = src == &lib_stock ? (const lib_src_t *)0 : src;
    pl.win = window_open("m1plus_playlists");
    if (!pl.win) return -1;
    widget_on(pl.win, EVT_DESTROY, pl_on_destroy, (void *)0);
    pl.back = m1_bind(pl.win, "btn_return", pl_on_back, (void *)0);
    pl.np = m1_bind(pl.win, "btn_backtoplayer", m1_on_player, (void *)0);
    pl.btn_selall = m1_bind(pl.win, "btn_selall", pl_on_selall, (void *)0); /* the select mode's widgets: optional */
    pl.del = m1_bind(pl.win, "pl_del", pl_on_delete, (void *)0);
    pl.bar = widget_lookup(pl.win, "pl_bar", 1);
    pl.title = widget_lookup(pl.win, "label_title", 1);
    pl.btn_more = m1_bind(pl.win, "btn_more", pl_on_more, (void *)0);
    pl.btn_plactions = m1_bind(pl.win, "btn_plactions", pl_on_actions, (void *)0);
    pl.view = widget_lookup(pl.win, "view_grid", 1);
    if (!pl.src && !pl_v()) { /* the long press sheet (an asset without it: no long press) */
        rowmenu_bind_album(&pl.rm, pl.win);
    }
    pl.sv = widget_lookup(pl.win, "playlists_scrollview", 1);
    pl.status = widget_lookup(pl.win, "label_status", 1);
    pl.spin = widget_lookup(pl.win, "pl_spin", 1); /* optional */
    pl.fade = widget_lookup(pl.win, "img_nb_fade", 1); /* optional */
    pl.big = widget_lookup(pl.win, "pl_title", 1);
    pl.g.st_title = widget_lookup(pl.win, "label_grid_title", 1);
    pl.g.st_sub = widget_lookup(pl.win, "label_grid_sub", 1);
    pl.st_ltitle = widget_lookup(pl.win, "label_row_title", 1);
    pl.st_lsub = widget_lookup(pl.win, "label_row_sub", 1);
    if (!pl.btn_more || !pl.btn_plactions || !pl.view || !pl.sv || !pl.status || !pl.g.st_title || !pl.g.st_sub ||
        !pl.st_ltitle || !pl.st_lsub) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    if (vs_bind(&pl.vs, pl.win, pl_on_item, pl_on_scrim,
                VS_ALL_SORTS | VS_WITH_VIEWS | VS_WITH_SEARCH | VS_WITH_SELECT | VS_WITH_ACT2 | VS_WITH_ACT3)) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    vs_dated(&pl.vs, 1u << 1 | 1u << 2 | 1u << 3); /* Title reads A-Z / Z-A, the dates Newest First / Oldest First */
    {
        int c = set_read(PLAYLISTS_SORT_FILE, '0');
        pl.sort = c >= '0' && c <= '3' ? c - '0' : c >= 'a' && c <= 'd' ? c - 'a' : 0;
        pl.rev = c >= 'a' && c <= 'd';
    }
    vs_offer(&pl.vs, pl.src ? PL_ROWS_MORE_SRC : PL_ROWS_MORE);
    pl.tmp = calloc((GRID_COVER / 2) * (GRID_COVER / 2),
                    4); /* one quadrant of a mosaic; without it a mosaic falls back to its first cover */
    { /* the stock grid, its two text styles are this page's hidden labels */
        void *st_title = pl.g.st_title, *st_sub = pl.g.st_sub;
        if (!grid_init(&pl.g, pl.win, GRID_TILES, GRID_COVER, GRID_R)) {
            grid_free(&pl.g);
            m1_show(pl.view, 0);
            m1_show(pl.status, 1);
            widget_set_tr_text(pl.status, "Not enough memory");
            return 0;
        }
        pl.g.st_title = st_title, pl.g.st_sub = st_sub;
        if (pl.src) pl.g.url = sbs_cover_url; /* (a source's mosaic keys are its cover files' hashes) */
    }
    m1_sel_init(&pl.sel, pl.win, pl.back, pl.title, pl.btn_selall, pl.bar, pl.del, (void *)0, (void *)0,
                (void *)0); /* the marks: all or none (no marks: no select mode) */
    if (pl_v() && !pick.star) pick.star = pl_make_star();
    if (pl_v() && !pick.tick) pick.tick = rowmenu_make_glyph(pl.win, "sg_pdone", SG_HANDLE_RGB);
    pl.list = pl_v() || !pl_use_grid(); /* the picker is always the list (the saved choice is the page's own) */
    pl_shape(pl.list);
    if (pl.src) { /* read-only remote playlists: no list-plus button (New Playlist, Import, Export, Delete Playlists, Clean Up are the stock library's), the title runs on */
        m1_show(pl.btn_plactions, 0);
        grid_icons(pl.btn_more, "pod_nav_more",
                   "pod_nav_more_down"); /* (the capsule's left cap is gone: "..." takes its rounded edge) */
        if (pl.title) grid_title_end(pl.title, NAV_VIEW_X);
        pl.gen_timer = timer_add(pl_on_gen, (void *)0, LS_GEN_MS);
    }
    if (pl_v()) { /* the picker: Back and the title only */
        m1_show(pl.btn_more, 0), m1_show(pl.np, 0), m1_show(pl.btn_plactions, 0);
        if (pl.title) grid_title_end(pl.title, SG_SELALL_X);
        pl_head();
    }
    if (pl.big) az_fit(pl.big, pl_v() ? TR("Add to Playlist") : TR("Playlists")); /* (296 px, an ellipsis when wider) */
    pl.noscroll = grid_scroll_bind(pl.sv, pl_on_scroll, pl.title, &pl.title_on);
    widget_on(pl.win, EVT_WINDOW_TO_FG, pl_on_fg, pl.win);
    widget_on(pl.win, EVT_WINDOW_TO_BG, pl_on_bg, pl.win);
    widget_on(pl.view, EVT_POINTER_DOWN, pl_on_down, (void *)0);
    widget_on(pl.view, EVT_POINTER_MOVE, pl_on_move, (void *)0);
    widget_on(pl.view, EVT_POINTER_UP, pl_on_up, (void *)0);
    widget_on(pl.view, EVT_POINTER_ABORT, pl_on_abort, (void *)0);
    widget_on(pl.view, EVT_AFTER_PAINT, pl_on_paint, (void *)0);
    pl_load();
    return 0;
}

/* The M1+ Music menu's Playlists row. A window that will not open leaves the stock Playlists page, through the Home dispatcher. 0 once something is requested. */
int playlists_open(void) { return playlists_open_src((const lib_src_t *)0); }

/* The Playlists page over a library source (patch/libsrc.h): src NULL or &lib_stock is the stock playlists, today's page. Another source's page is read-only (no New Playlist, Import,
 * Export, Delete Playlists, Clean Up); its window that will not open is -1 (there is no stock page to fall back to). */
__attribute__((noinline)) int playlists_open_src(const lib_src_t *src) {
    int r;
    if (src == &lib_stock) src = (const lib_src_t *)0;
    r = pl_open_page(src);
    if (r == -1 && !pl.win && !src) return pod_home_open(HOME_PLAYLIST);
    return r;
}

/* The Add to Playlist picker's page (patch/picker.c picker_open): this page in pick mode. Over our own Playlists page's Songs page the state of the Playlists page below
 * is kept aside first (pl is one struct) and put back by pl_on_destroy. 0 once the page is up; < 0 where it could not open (the caller falls back to the stock picker). */
int playlists_pick(void) {
    int r, front = pl.win && !pl.bg;
    if (pick.on) return -1;
    if (pl.win) {
        pick.stash = calloc(1, sizeof pl);
        if (!pick.stash) return -1;
        if (!pl.bg)
            pl_on_bg(
                pl.win,
                (void
                     *)0); /* the page in front (its long press sheet's Add to Playlist): it goes behind now, its loader stopped, as its own to-background would (that event finds pl the picker's and leaves it) */
        memcpy(pick.stash, &pl, sizeof pl);
        memset(&pl, 0, sizeof pl);
    }
    pick.on = 1;
    r = pl_open_page((const lib_src_t *)0);
    if (r < 0) {
        pick.on = 0; /* (a page left again, -2, ends in pl_on_destroy, which puts the stash back) */
        if (r == -1 && pick.stash) {
            memcpy(&pl, pick.stash, sizeof pl);
            free(pick.stash);
            pick.stash = (void *)0;
            if (front) pl_on_fg(pl.win, (void *)0); /* still in front: its loader runs again */
        }
    }
    return r;
}
