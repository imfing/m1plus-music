/* M1+ Music Songs: the library as one list, in the Apple Music manner.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_songs.bin (docs/modules/songs.md has the whole design): the glass navbar (Back, the small title, the "..." that holds Search Songs, Select, Albums / Songs and Sort, Now Playing) over a
 * stock list, list_view > scroll_view (songs_scrollview) whose ONE child, view_grid, is the content view of the Albums page (patch/albums.c): it paints the rows,
 * the section headers, the pinned header and the select marks itself in its own EVT_AFTER_PAINT, with no widget per song; the stock scroll_view does the scrolling.
 * The content view's only children are the large title and the Play / Shuffle pills (real flat buttons that scroll with it; a playlist's page has the album page's Shuffle disc and Play pill instead: image buttons, the glyph an image and the text painted here). Beside the list, as widgets of the
 * window: the A-Z rail (outside the scroll_view, so a touch on it never starts a drag) and the letter bubble, the sort card, and the select mode's bar.
 *
 *   data      loadLocalClassList(0xf001) (what allmusic_page_init runs: getAllMusic into *pdeq_showlist, in the stock sort order, sort_flag). The 20,000 songs of a big
 *             library are NOT copied: the page keeps one 8 byte entry per song (the cover key, the section letter) and reads the title and the artist from the stock
 *             list while painting. The stock list is replaced by the next stock query (another page's), so every use first checks that it is still the list this index
 *             was made from (sg_valid: the pointer, the size, the first record) and the page reads it again when its window comes back to the front (or, if it is
 *             on top, from a timer, when a paint finds it gone). The library's albums (cc_albums, loaded first: it is a stock query too) answer the cover lookup of a song
 *             whose own artist + album has no cache file.
 *   sections  with the stock Title order (sort_flag 0) the songs are grouped by the Initial the scan stored (REC_INITIAL: '*' digits, 'A'..'Z', '#'; digits and symbols
 *             are one section, "#"), the stock order kept: the labelling with the most songs under their own letter (sg_sections), strays stay where they are; the rail
 *             is a compact index (the letters of the sections, or every k-th with dots between when they would be more than SG_RAIL_ITEMS items) that a finger maps
 *             onto every section; any other order is a plain list and has no rail.
 *   tiles     the Albums list's ring (patch/grid.c, GRID_TILES 52 px covers), one per song, decoded one per 16 ms tick when the scroll_view is still. The covers are
 *             the Cover Flow cache; the background build (patch/covercache.c) makes the ones of the songs around the first in view that have none.
 *   touch     a tap on a row plays it as the stock Songs row does (loadSongList, then playing_page); in select mode it toggles the row's mark. The rail grabs the
 *             touch: DOWN, MOVE, UP set the scroll_view's offset to the section's header (a coasting list is stopped first) and show the bubble.
 *   select    the page's own multi-select: marks in a bitset, "N Selected", Select All, and the bar. Add to playlist and Delete run the stock code on the stock
 *             selection vector, which the page fills from its bitset at that moment (select_recordinit, set_selectindex): Delete is batch_delete_file (class 0xf001,
 *             *pdeq_showlist, the vector) after the stock confirm dialog; Add opens the stock playlist picker (playlist_page with the add context), which adds the
 *             selection to the playlist that is tapped and closes itself.
 *   sort      the Sort card (patch/viewsort.c: Title, File Name, Format, Recently Added; Recently Added is sort_flag 3 Newest First or 4 Oldest First) sets sort_flag as the stock sort
 *             dialog's row handler does (the flag and [SYSSET] SORTSELECT), then reads the list again. A tap on the ticked Title, File Name or Format row reverses it (Z-A, SONGS_SORT_FILE; the
 *             flag stays 0..2): the query's list is reversed in place (records swapped), so the page, its rows, its index, Select and the taps all use the order shown; the sections and the rail are
 *             mirrored as the Artists page's; play queues are reversed too (so_play_dir).
 *   lists     the same page shows the other stock song lists, each in the stock order of its query (docs/modules/songs.md "The other lists"): Favourites, Recently
 *             Added, Recently Played, Most Played, Hi-Res (the menu rows, songs_open_list) and a playlist (the Playlists page, songs_open_playlist: its id goes into
 *             classinfo[1] before every query and play, as the stock row tap leaves it). A list is what the stock allmusic_page shows for its class: no sort (Search
 *             moves to Sort's slot, the capsule is three pieces), so no sections and no rail; its title is the menu row's text or the playlist's name, cut with an
 *             ellipsis; play, Shuffle (that list, the stock Shuffle mode) and the stock Delete (batch_delete_file with the list's class: the stock removes the
 *             song from that list's table, and the file too when asked) use its class; it is read again whenever the page comes back to the front (a play changes
 *             Recently Played and Most Played, Now Playing's star the Favourites).
 *             A genre's songs (songs_open_genre, from the Genres page, class 0xff09) are such a list too: the genre's name is in classinfo + 0x30d (and classinfo[0],
 *             the Unknown Genre byte) for every query and play, as the stock row tap leaves it; the stock navbar has no Search there, so its card is Select alone.
 *             An artist's songs (Cover Flow's artist page, songs_open_artist) is the same page on class 0xff11: its whole state is the 0x390 byte browsing
 *             record loadAlbumList(0xf004) and loadAlbumdetailList(0xff01, the All songs row) build, which the page snapshots and puts back before every query
 *             and play; the artist is the title and the grey line of a row is its album. A composer's songs (songs_open_artist with CLASS_COMPOSERS) are the same on\n *             class 0xff14 (loadAlbumList(0xf005), loadAlbumdetailList(0xff02)), the grey line staying the artist.
 *   albums    Recently Added (class 0xf009) has a View group in the "..." card (Albums / Songs, docs/modules/recent-albums.md): the same page shows the newest-first Albums grid
 *             (patch/grid.c, a second tile ring sg.rg). The grid is read from the full `time_create desc` query (sort_flag 3 through loadLocalClassList(0xf001), the flag put back
 *             at once), copied into at most RV_MAX library album rows (sg.rrow) at the moment of the toggle; the album view reads only that copy and the library's albums, never
 *             *pdeq_showlist, so the stock list the query replaced matters to the songs view only: leaving the album view reads class 0xf009 again (sg_load). The choice is
 *             kept in RECENTADD_VIEW_FILE.
 *   count     the content view's label sg_foot under the last row: "25 songs", on every list.
 * No hook; everything runs from the page's widgets and timers.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "viewsort.h"
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "songops.h"
#include "rowmenu.h"

extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */
extern int search_open(void); /* patch/search.c: our keyboard, then the results page; -1 when it did not open */

#define ROW LIST_ROW_H
#define SG_W 320 /* the content's width: the list_view's (the scroll_view clips at 310) */
#define SG_TAP_PX SC_DRAG_PX
#define SG_AHEAD 2 /* rows loaded beyond the view in the scroll direction */
#if GRID_TILES < (GRID_VIEW_H / LIST_ROW_H) + 2 + 2 + 2
#error GRID_TILES cannot hold the visible rows, the next two and the history
#endif
#if SG_RAIL_ITEMS * SG_RAIL_PITCH > GRID_VIEW_H - SG_BAR_H
#error the rail cannot hold SG_RAIL_ITEMS items in select mode
#endif

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

typedef grid_tile_t tile_t;

typedef struct {
    unsigned key; /* cc_album_key of the song: its cover's cache file */
    unsigned char letter; /* the section letter: 'A'..'Z' or '#' */
    unsigned char sig
        [3]; /* 24 bits of a hash of what the row shows (both lines, the cover key, the section): a list read again with every sig the same keeps its tiles */
} song_t;

static void sg_set_sig(song_t *s, unsigned h) {
    s->sig[0] = (unsigned char)h, s->sig[1] = (unsigned char)(h >> 8), s->sig[2] = (unsigned char)(h >> 16);
}
static int sg_same_sig(const song_t *a, const song_t *b) {
    return a->sig[0] == b->sig[0] && a->sig[1] == b->sig[1] && a->sig[2] == b->sig[2];
}

static struct {
    void *win, *view, *sv, *status, *title, *back, *np;
    void *fade; /* the navbar's fade (img_nb_fade, optional): shown only while the list is scrolled */
    void *
        btn_more; /* the navbar's "..." (Select, Albums / Songs, Sort: what the list offers), or on a list that would offer Select alone (sg_direct) the Select button: no card */
    void *btn_select; /* the Select button (sg_direct lists): bound as btn_more once the page knows its list */
    void *btn_cf; /* the artist's songs list only: the Cover Flow button (back to the covers) */
    void *
        btn_search; /* the lists that search (not a genre's or an artist's songs): the capsule's left cap at NAV_CF_X, Albums' Cover Flow place */
    void *btn_selall, *btn_play, *btn_shuffle, *btn_add, *btn_del;
    /* A playlist's header has the album page's Shuffle disc and Play pill instead of the library's two flat pills (btn_play, btn_shuffle): hd_play, hd_shuffle, and the pill's
     * glyph and hidden text label (sg_glyph, sg_play_text; the text is painted by the content view). Only one set is shown (sg_pills), the other is hidden and insensitive. */
    void *hd_play, *hd_shuffle;
    pod_pill_t pill;
    void *st_title, *st_sub; /* hidden labels whose styles are the text styles (the rail's and the header's are az's) */
    void *bar;
    vs_t
        vs; /* the "..." card (patch/viewsort.c): Search Songs, Select, Albums / Songs (Recently Added), Title, File Name, Format, Recently Added (the library) */
    void *list; /* the stock list the index is of (*pdeq_showlist when valid) */
    void *first; /* its first record: with the size, tells a list another query replaced */
    unsigned count;
    song_t *idx; /* count entries */
    unsigned char *sel; /* the select mode's bitset: (count + 7) / 8 bytes */
    unsigned nsel;
    int select; /* select mode */
    int sort; /* sort_flag as the page last read it */
    int rev; /* the library's Title, File Name and Format orders run Z-A (SONGS_SORT_FILE): the stock list is reversed in place after the query */
    az_t al; /* the sections and the rail (patch/azlist.c); al.nsec is 0 for a plain list */
    void *albums; /* the library's albums (cc_albums), for the cover lookup */
    int albums_tried;
    /* the select marks (SG_MARK px): bitmaps */
    void *mark[2]; /* unselect, selected */
    int press; /* the row under the finger, + 1 */
    int seen, dir, noscroll;
    int down, down_x, down_y; /* the row a press began on, + 1, and where */
    int title_on; /* the small title is shown */
    int menu; /* the sort card is open */
    int picker; /* the stock playlist picker is open over this page */
    unsigned more_timer, stale_timer, build_timer;
    int own, done,
        build_at; /* the cover build: this page holds the worker's set; its done counter at the last poll; the song it was made around */
    char title_save[0x200]; /* nagvation_title across the picker */
    int cls; /* the class listed: CLASS_ALL_SONGS (the library: sort, sections, rail) or another stock song list */
    int pl_id; /* CLASS_PLAYLIST_SONGS: the playlist, classinfo[1] for every query and play; CLASS_GENRE_SONGS: 1 for the Unknown Genre row (classinfo + 0xc) */
    const char *key; /* the title's key (TR), or 0: the title is name */
    char name[0x100]; /* a playlist's name */
    unsigned char ci
        [CLASSINFO_SIZE]; /* CLASS_ARTIST_SONGS / CLASS_14: the browsing record of the artist or composer (CLASSINFO, as the two stock queries left it), put back before every query and play */
    void *big; /* the large title (sg_title) */
    void *foot; /* the song count under the last row (sg_foot, a label in the content view) */
    void *
        hname; /* a playlist's header: the name (sg_hname, an optional label of the content view; the count is the list's footer) */
    unsigned *htmp; /* one quadrant of the header's mosaic (PH_COVER / 2 squared words) for grid_mosaic */
    int head; /* the page has a playlist's header (class 0xff13, its labels, its tile and quadrant buffer): the pills and the rows start lower, the large title is not shown */
    grid_t hg; /* the header's one tile, PH_COVER px (patch/grid.c, as the Playlists page's mosaics) */
    void *st_gtitle, *st_gsub; /* the album view's two grid text styles (optional hidden labels) */
    int rv; /* Recently Added shows its albums (the grid) */
    unsigned rn; /* the albums of the grid */
    unsigned *rrow; /* rn library album rows, newest first (the stock row numbers) */
    grid_t rg; /* the album view's tile ring (GRID_COVER px covers), made when the view is entered */
    rowmenu_t rm; /* the rows' "..." menu (patch/rowmenu.c) */
    int tend; /* the text end the tiles were last fitted for (without select mode): a list read again with another one drops them */
    int down_more; /* the press began in a row's "..." zone */
    grid_t g; /* the tile ring (LAST: test/pod/songs.py reads the fields above by index) */
} sg __attribute__((section(".scratch")));

static int sg_on_stale(const void *unused);
static void *sg_under __attribute__((section(
    ".scratch"))); /* a Songs page below the one open (Search was opened from it and a playlist result opened ours): its state, put back when this page is destroyed */

static void sg_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int sg_abs(int v) { return v < 0 ? -v : v; }
static int sg_off(void) { return sg.sv ? I(sg.sv, SC_YOFF) : 0; }
static void sg_redraw(void) { widget_invalidate_force(sg.sv, (void *)0); }

/* The text of a record: its title, else its file name. */
static const char *sg_name(void *rec) {
    const char *t = cc_str(rec, REC_TITLE);
    return *t ? t : cc_str(rec, REC_NAME);
}

/* ---------------------------------------------------------------------------
 * The stock list and its index
 */

/* The library is shown reversed: the Z-A direction of one of the alphabetical orders (sort_flag 0..2). */
static int sg_flipped(void) { return sg.cls == CLASS_ALL_SONGS && sg.rev && sg.sort >= 0 && sg.sort < 3; }

/* The section rank of a record, in the order the stock Title sort puts them (toolsQueryDbTable's title comparator 0x5e0dac: digits and most symbols before the
 * letters): 0 "#" (the Initial '*', a title that starts with a digit, or '#', anything else), 1..26 'A'..'Z'. From the Initial the scan stored; 0 (never written: a
 * database older than the column) takes the title's first character. */
static unsigned char sg_rank(void *rec) {
    int c = B(rec, REC_INITIAL), k;
    if (!c) c = (unsigned char)*sg_name(rec);
    k = az_rank_of(c);
    if (sg_flipped())
        k = k ? 26 - k
              : 26; /* Z-A: Z is rank 0 .. A rank 25 and "#" last, so the ranks still rise down the list (as the Artists page) */
    return (unsigned char)k;
}

/* The stock list in the other order, in place: the records (REC_SIZE bytes, as the queue reversal of so_play_dir and the shuffle's swaps) are exchanged. */
static void sg_reverse(void *list) {
    unsigned n = deque_size(list), i;
    char tmp[REC_SIZE];
    for (i = 0; i < n / 2; ++i) {
        void *a = deque_at(list, i), *b = deque_at(list, n - 1 - i);
        memcpy(tmp, a, REC_SIZE), memcpy(a, b, REC_SIZE), memcpy(b, tmp, REC_SIZE);
    }
}

/* The index is of the stock list `list` as long as that list is still in *pdeq_showlist, as big, and starts with the same record. */
static int sg_valid(void) {
    void *cur = *(void **)PDEQ_SHOWLIST;
    return sg.list && cur == sg.list && deque_size(cur) == sg.count && (!sg.count || deque_at(cur, 0) == sg.first);
}

static int sg_lib(void) {
    return sg.cls == CLASS_ALL_SONGS;
} /* the library: the only list with the sort card, sections and the rail */
static int sg_genre(void) {
    return sg.cls == CLASS_GENRE_SONGS;
} /* a genre's songs: the stock navbar has no Search there */
static int sg_artist(void) {
    return sg.cls == CLASS_ARTIST_SONGS || sg.cls == CLASS_14;
} /* an artist's (or a composer's) songs: Cover Flow's artist page is its other view (a toggle, not a stack) */
static int sg_recent(void) {
    return sg.cls == CLASS_RECENTADD;
} /* Recently Added: its card also holds the Albums / Songs rows (the songs or the newest albums) */
static int sg_searches(void) {
    return !sg_genre() && !sg_artist() && sg.cls != CLASS_PLAYLIST_SONGS && sg.btn_search;
} /* a list with the Search button (a genre's songs: the stock navbar has none; an artist's: Cover Flow has its place; a playlist's: no Search inside a playlist) */
static int sg_direct(void) {
    return !sg_lib() && !sg_recent();
} /* a list whose "..." card would hold Select alone: the navbar has the Select button instead (btn_select), no card */
static int sg_title_end(void) {
    return (sg_artist() && sg.btn_cf) || sg_searches() ? NAV_CF_X : NAV_VIEW_X;
} /* the small title ends at the capsule's first piece: "..." (214), or Search / Cover Flow (168) */
/* The rows of the "..." card the list offers, what its navbar had as buttons: Select (not in Recently Added's albums view), Albums / Songs (Recently Added), the four sorts (the library).
 * Search is the navbar button (btn_search), not a row. */
static unsigned sg_offers(void) {
    if (sg_lib()) return VS_WITH_SELECT | VS_ALL_SORTS;
    if (sg_recent()) return VS_WITH_VIEWS | (sg.rv ? 0 : VS_WITH_SELECT);
    return VS_WITH_SELECT;
}

/* What a genre's stock row tap leaves in the browsing record (@0x535c4c): classinfo[0] = 0xff09, the name (0x80 bytes, cut as snprintf cuts it) at + 0x30d, the byte + 0xc. */
static void sg_genre_info(const char *name, int unknown) {
    unsigned char *ci = (unsigned char *)CLASSINFO;
    unsigned i;
    *(int *)ci = CLASS_GENRE_SONGS;
    memset(ci + CLASSINFO_GENRE, 0, CLASSINFO_GENRE_SIZE);
    for (i = 0; name[i] && i < CLASSINFO_GENRE_SIZE - 1; ++i) ci[CLASSINFO_GENRE + i] = (unsigned char)name[i];
    ci[CLASSINFO_GENRE_UNKNOWN] = unknown != 0;
}

/* The browsing record as the class listed needs it (another page's query may have changed it): a playlist's id in classinfo[1], a genre's name, an artist's whole
 * record. */
static void sg_classinfo(void) {
    if (sg.cls == CLASS_PLAYLIST_SONGS)
        *(int *)(CLASSINFO + CLASSINFO_ARG) = sg.pl_id;
    else if (sg_genre())
        sg_genre_info(sg.name, sg.pl_id);
    else if (sg_artist())
        memcpy((void *)CLASSINFO, sg.ci, CLASSINFO_SIZE);
}

/* The stock query of the class listed (into *pdeq_showlist), the browsing record put back first. */
static int sg_query(void) {
    sg_classinfo();
    return loadLocalClassList(sg.cls);
}

/* Content geometry (patch/azlist.c: the rows, and the headers in Title order, start at SG_TOP; section s's header is at az_hdr_y(s), its songs follow). The page
 * keeps al.count and al.content (what the scroll offset is clamped to) in step with the list: sg_load and sg_size. */
static int sg_row_y(int i) { return az_row_y(&sg.al, i); }
static int sg_pad(void) {
    return sg.select ? SG_BAR_H : 0;
} /* the bar covers the window's last SG_BAR_H rows: the list scrolls clear of it */
static int sg_rows_end(void) { return az_rows_end(&sg.al); } /* the content y under the last row: the song count */
static int sg_content(void) { return sg_rows_end() + SG_FOOT_H + sg_pad(); }
static int sg_max_scroll(void) { return az_max_scroll(&sg.al); }
static int sg_row_from(int y) { return az_row_from(&sg.al, y); }
static int sg_at(int y) {
    return az_at(&sg.al, y);
} /* the song under content point y: its row, or -1 for the title block, a header and the air below the last row */
static void sg_span(int *r0, int *r1) { az_span(&sg.al, r0, r1); }

/* The songs the tiles are kept for: those in view and SG_AHEAD rows beyond them in the scroll direction. */
static void sg_window(int *lo, int *hi) {
    int r0, r1;
    sg_span(&r0, &r1);
    if (sg.dir < 0)
        r0 -= SG_AHEAD;
    else
        r1 += SG_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > (int)sg.count - 1) r1 = (int)sg.count - 1;
    *lo = r0, *hi = r1;
}

/* The select mode moves the row's content right by one column. */
static int sg_tx(void) { return LIST_TEXT_X + (sg.select ? SG_SEL_COL : 0); }
static int sg_art_x(void) { return LIST_ART_X + (sg.select ? SG_SEL_COL : 0); }

/* The row's "..." (patch/rowmenu.c): shown outside select mode, its zone ends at the list's edge, or left of the A-Z rail while that is shown; the title and the artist end before it. */
static int sg_more_right(void) { return RM_MORE_RIGHT - az_inset(&sg.al); }
static int sg_edge(void) { return rowmenu_on(&sg.rm) ? rowmenu_zone_x(sg_more_right()) - RM_TEXT_GAP : az_end(&sg.al); }
static int sg_more(void) { return !sg.select && rowmenu_on(&sg.rm); }
static int sg_text_end(void) { return sg.select ? az_end(&sg.al) : sg_edge(); }

static int sg_is_sel(int i) { return sg.sel && (sg.sel[i >> 3] >> (i & 7) & 1); }

/* The tile of song a, made from the stock record (the caller has checked sg_valid). */
static void sg_prep(tile_t *t, int a) {
    void *rec = deque_at(sg.list, (unsigned)a);
    const char *sub = cc_str(
        rec,
        sg.cls == CLASS_ARTIST_SONGS
            ? REC_ALBUM
            : REC_ARTIST); /* an artist's list: the artist is the title, the album the grey line (a composer's keeps the artist) */
    char buf[300];
    if (sg.cls ==
        CLASS_OFTEN) { /* Most Played: "12 plays · Artist" (the count first, a long artist is the part that is cut); REC_TRACK = plays - 1 */
        int plays = I(rec, REC_TRACK) + 1;
        char count[48];
        pod_fmt(count, sizeof count, TR(plays == 1 ? "%d play" : "%d plays"), plays);
        snprintf(buf, sizeof buf, "%s%s%s", count, sub[0] ? " \xc2\xb7 " : "", sub);
        sub = buf;
    }
    grid_set(t, sg_name(rec), sub, sg.idx[a].key);
}

static tile_t *sg_tile(int a) {
    int lo, hi, fresh;
    tile_t *t;
    sg_window(&lo, &hi);
    t = grid_tile(&sg.g, a, lo, hi, &fresh);
    if (fresh) sg_prep(t, a);
    return t;
}

/* The texts are cut to a width that the select mode changes: every tile's are made again from the record. */
static void sg_retext(void) {
    int i;
    for (i = 0; sg.g.tiles && sg.list && i < sg.g.n; ++i) {
        tile_t *t = &sg.g.tiles[i];
        if (t->album && t->album - 1 < (int)sg.count) sg_prep(t, t->album - 1), t->fit = 0;
    }
}

/* ---------------------------------------------------------------------------
 * Recently Added's album view: the Albums grid (patch/grid.c) under the large title, from RV_TOP (where the pills begin on the songs view; there are none here)
 */
#define RV_TOP SG_PILL_Y
#define RV_MAX 60 /* albums kept */
#define RV_AHEAD 1 /* grid rows loaded beyond the view in the scroll direction */
/* sort_flag of "Time added (descending)": getAllMusic runs sort_time_desc, `select * from songtable ORDER BY time_create desc` */
#define RV_SORT_TIME_DESC 3
#if GRID_TILES < GRID_COLS * ((GRID_VIEW_H + GRID_CELL_H) / GRID_PITCH + 2 + 1) + 2
#error GRID_TILES cannot hold the visible cells, the next row and the history
#endif

static int rv_rows(void) { return ((int)sg.rn + GRID_COLS - 1) / GRID_COLS; }
static int rv_content(void) { return RV_TOP + rv_rows() * GRID_PITCH; }
static void *rv_rec(int a) { return deque_at(sg.albums, sg.rrow[a]); } /* the library album row of album a */

/* The grid rows that touch the view: [*r0, *r1], none when r1 < r0 (kept inside [0, rows - 1] also while a drag pulls the list past an end). */
static void rv_span(int *r0, int *r1) {
    int s = sg_off(), n = rv_rows();
    *r0 = s > RV_TOP + GRID_CELL_H ? (s - RV_TOP - GRID_CELL_H) / GRID_PITCH + 1 : 0;
    *r1 = (s + GRID_VIEW_H - RV_TOP + GRID_PITCH - 1) / GRID_PITCH - 1;
    if (*r0 < 0) *r0 = 0;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The albums [*lo, *hi] the tiles are kept for: those in view and RV_AHEAD rows beyond them in the scroll direction. */
static void rv_window(int *lo, int *hi) {
    int r0, r1;
    rv_span(&r0, &r1);
    if (sg.dir < 0)
        r0 -= RV_AHEAD;
    else
        r1 += RV_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > rv_rows() - 1) r1 = rv_rows() - 1;
    *lo = r0 * GRID_COLS;
    *hi = (r1 + 1) * GRID_COLS - 1;
    if (*hi > (int)sg.rn - 1) *hi = (int)sg.rn - 1;
}

static tile_t *rv_tile(int a) {
    int lo, hi, fresh;
    tile_t *t;
    rv_window(&lo, &hi);
    t = grid_tile(&sg.rg, a, lo, hi, &fresh);
    if (fresh) {
        void *rec = rv_rec(a);
        grid_set(t, cc_str(rec, REC_ALBUM), cc_str(rec, REC_ARTIST), cc_album_key(rec));
    }
    return t;
}

static tile_t *rv_tile_of(void *ctx, int a) {
    (void)ctx;
    return rv_tile(a);
}

static void rv_paint(void *canvas) {
    int r0, r1, last;
    rv_span(&r0, &r1);
    if (r1 < r0) return;
    last = (r1 + 1) * GRID_COLS;
    if (last > (int)sg.rn) last = (int)sg.rn;
    grid_paint(canvas, &sg.rg, r0 * GRID_COLS, last, RV_TOP - sg_off(), GRID_VIEW_H, rv_tile_of, (void *)0);
}

/* The album to decode next, or -1: of the window's albums without a tile that was tried, the cell nearest the middle of the view, the cells in view first. */
static int rv_next_load(void) {
    int lo, hi, a, best = -1, bd = 0x7fffffff, s = sg_off();
    if (!sg.rg.tiles || !sg.rn) return -1;
    rv_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        tile_t *t = grid_find(&sg.rg, a);
        int top = RV_TOP + a / GRID_COLS * GRID_PITCH - s, d;
        if (t && t->art) continue;
        d = sg_abs(top + GRID_CELL_H / 2 - GRID_VIEW_H / 2);
        if (top >= GRID_VIEW_H || top + GRID_CELL_H <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

/* The album under content point (x, y), or -1 for the title block, a gap, the margins and the empty tail of the last row. */
static int rv_cell_at(int x, int y) {
    if (y < RV_TOP || y >= rv_content()) return -1;
    return grid_cell_at(x, y, RV_TOP, (int)sg.rn);
}

/* ---------------------------------------------------------------------------
 * Paint: the rows, the headers and the pinned header, in one EVT_AFTER_PAINT of the content view. Coordinates are the window's (its top is 0): the scroll_view has
 * moved the canvas up by yoffset, which the paint adds back (CANVAS_OY) for its duration, as the Albums page does.
 */
static void sg_paint_rows(void *canvas) {
    int r0, r1, r, off = sg_off(), tx = sg_tx(), hair = az_end(&sg.al) - tx, room = sg_text_end() - tx, pass;
    if (sg.head) { /* a playlist's mosaic (the cover, or the placeholder disc until it is made) */
        grid_tile_t *h = grid_find(&sg.hg, 0);
        if (h) grid_blit(canvas, &sg.hg, h, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
    }
    if (sg.head) pod_pill_paint(&sg.pill, canvas, PH_BTN_Y - off); /* a playlist's Play pill text, over its picture */
    sg_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        tile_t *t = sg_tile(r);
        int y = sg_row_y(r) - off;
        if (sg.press == r + 1 && !sg.select) az_fill(canvas, 0, y, y + ROW - 1, SG_W, LIST_PRESS);
        if (sg.select && sg.mark[0]) {
            void *m = sg.mark[sg_is_sel(r)];
            int src[4], dst[4], top = y + (ROW - SG_MARK) / 2;
            if (top >= 0 && top + SG_MARK <= GRID_VIEW_H) {
                src[0] = 0, src[1] = 0, src[2] = SG_MARK, src[3] = SG_MARK;
                dst[0] = LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, dst[1] = top, dst[2] = SG_MARK, dst[3] = SG_MARK;
                canvas_draw_image(canvas, m, src, dst);
            }
        }
        grid_blit(canvas, &sg.g, t, sg_art_x(), y + LIST_ART_Y, GRID_VIEW_H);
        az_fill(canvas, tx, y + ROW - 1, y + ROW, hair, LIST_HAIR);
        if (sg_more()) rowmenu_paint(canvas, &sg.rm, sg_more_right(), az_inset(&sg.al) > 0, y, ROW, GRID_VIEW_H);
    }
    for (pass = 0; pass < 2; ++pass) { /* titles, then artists: one text style at a time */
        widget_prepare_text_style(pass ? sg.st_sub : sg.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, sg_tile(r), pass, tx, sg_row_y(r) - off + (pass ? LIST_SUB_Y : LIST_TITLE_Y), room,
                      pass ? LIST_SUB_H : LIST_TITLE_H, 0);
    }
    az_paint_heads(&sg.al, canvas); /* the section letters, then over everything the pinned band and its letter */
}

static int sg_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = sg_off();
    (void)ctx;
    if (sg.rv) {
        if (canvas && sg.view && sg.rg.tiles && sg.rn) {
            I(canvas, CANVAS_OY) += off;
            rv_paint(canvas);
            I(canvas, CANVAS_OY) -= off;
        }
        return RET_OK;
    }
    if (!canvas || !sg.view || !sg.g.tiles || !sg.count) return RET_OK;
    if (!sg_valid()) { /* another query replaced the stock list: nothing of it is read; the page reads it again when it is on top */
        if (!sg.stale_timer) sg.stale_timer = timer_add(sg_on_stale, (void *)0, 100);
        return RET_OK;
    }
    I(canvas, CANVAS_OY) += off;
    sg_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The loader: one cover per tick on the page's own timer, none while the scroll_view moves (the Albums page's, docs/modules/albums.md)
 */
static int sg_next_load(void) {
    int lo, hi, a, best = -1, bd = 0x7fffffff, s = sg_off();
    if (!sg.g.tiles || !sg.count || !sg_valid()) return -1;
    sg_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        tile_t *t = grid_find(&sg.g, a);
        int top = sg_row_y(a) - s, d;
        if (t && t->art) continue;
        d = sg_abs(top + ROW / 2 - GRID_VIEW_H / 2);
        if (top >= GRID_VIEW_H || top + ROW <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int sg_on_load(const void *unused);

static int sg_moving(void) { return grid_moving(sg.sv); }

/* The playlist header's mosaic still to be made (one source a tick) and in view. */
static int sg_head_pending(void) {
    grid_tile_t *t = sg.head && sg.hg.tiles ? grid_find(&sg.hg, 0) : (grid_tile_t *)0;
    return t && !t->art && sg_off() < PH_COVER_Y + PH_COVER;
}

static void sg_kick(void) {
    if (!sg.more_timer && sg.view &&
        (sg.noscroll || (sg.rv ? rv_next_load() : sg_next_load()) >= 0 || sg_head_pending()))
        sg.more_timer = timer_add(sg_on_load, (void *)0, SG_MORE_MS);
}

static void sg_dir(void) {
    int s = sg_off();
    if (s != sg.seen) sg.dir = s > sg.seen ? 1 : -1;
    sg.seen = s;
}

/* The cover of a tile: its own key's file, else the library album's (cc_cover_key); a tile with neither shows the placeholder. */
static void sg_art(tile_t *t) {
    char url[80];
    if (t->album - 1 >= (int)sg.count) {
        grid_art(&sg.g, t);
        return;
    }
    t->ckey = cc_cover_key(sg.albums, t->ckey, cc_str(deque_at(sg.list, (unsigned)(t->album - 1)), REC_ALBUM), url);
    grid_art_url(&sg.g, t, *url ? url : (const char *)0);
}

static int sg_on_load(const void *unused) {
    int a;
    (void)unused;
    sg.more_timer = 0;
    if (!sg.view) return RET_OK;
    sg_dir();
    if (sg_moving()) { /* nothing is decoded while it moves: look again next tick */
        sg_kick();
        return RET_OK;
    }
    if (sg.rv) { /* the album view: one cover of the grid */
        a = rv_next_load();
        if (a >= 0) {
            tile_t *t = rv_tile(a);
            int top = RV_TOP + a / GRID_COLS * GRID_PITCH - sg_off();
            grid_art(&sg.rg, t);
            if (top < GRID_VIEW_H && top + GRID_CELL_H > 0) sg_redraw();
        }
        sg_kick();
        return RET_OK;
    }
    if (sg_head_pending()) { /* the header's mosaic first: it is what the page opens on */
        grid_mosaic(&sg.hg, grid_find(&sg.hg, 0), sg.htmp);
        sg_redraw();
        sg_kick();
        return RET_OK;
    }
    a = sg_next_load();
    if (a >= 0) {
        tile_t *t = sg_tile(a);
        int top = sg_row_y(a) - sg_off();
        sg_art(t);
        if (top < GRID_VIEW_H && top + ROW > 0) sg_redraw();
    }
    sg_kick();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The navbar's title: the large title is in the content; once it has scrolled away the navbar shows the small one
 */
static void sg_title_update(void) {
    int on = sg.noscroll || sg.select || pod_title_gone(sg_off(), sg.head ? PH_COLLAPSE : 0);
    pod_title_set(sg.title, &sg.title_on, on);
    /* The navbar's fade (an insensitive image, built hidden) is for rows passing under the bar: shown while the list is scrolled, hidden at rest, where
     * it would darken the large title (as the Albums and Playlists pages). Never a touch target. No fade widget = nothing happens. */
    if (sg.fade) {
        widget_set_visible(sg.fade, sg_off() > 0, 0);
        widget_set_sensitive(sg.fade, 0);
    }
}

/* The background cover build (the Albums page's, docs/modules/albums.md): the covers of the songs around the first one in view that have no cache file. */
#define SG_BUILD_START_MS 50
#define SG_BUILD_MS 500

static void sg_retry(void) { /* every tile that showed the placeholder for want of a file tries again */
    int i, any = 0;
    for (i = 0; i < GRID_TILES; ++i) {
        tile_t *t = sg.rv ? (sg.rg.tiles ? &sg.rg.tiles[i] : (tile_t *)0) : sg.g.tiles ? &sg.g.tiles[i] : (tile_t *)0;
        if (t && t->album && t->art == 2) t->art = 0, any = 1;
    }
    if (any) sg_kick();
}

static void sg_build_end(void) {
    if (sg.build_timer) timer_remove(sg.build_timer);
    sg.build_timer = 0;
    if (sg.own) cc_build_stop();
    sg.own = 0;
}

static int sg_on_build(const void *unused) {
    int done;
    (void)unused;
    sg.build_timer = 0;
    if (!sg.view || !sg.own) return RET_OK;
    done = cc_build_done();
    if (done != sg.done) sg.done = done, sg_retry();
    if (done >= cc_build_total()) {
        sg_build_end();
        return RET_OK;
    }
    sg.build_timer = timer_add(sg_on_build, (void *)0, SG_BUILD_MS);
    if (!sg.build_timer) sg_build_end();
    return RET_OK;
}

static int sg_first(void) {
    int a = sg_row_from(sg_off() < 0 ? 0 : sg_off());
    return a < 0 ? 0 : a;
}

static int sg_on_build_start(const void *unused) {
    int c, lo, hi, i, seen_n = 0;
    unsigned seen[2 * SG_BUILD_N + 1];
    (void)unused;
    sg.build_timer = 0;
    if (!sg.view || !sg.count || sg.own || !sg_valid()) return RET_OK;
    if (!cc_build_open(2 * SG_BUILD_N + 1, CC_MISSING)) {
        if (cc_build_orphan()) /* a worker stopped by the page before is still inside a job: ask again shortly */
            sg.build_timer = timer_add(sg_on_build_start, (void *)0, SG_BUILD_MS);
        return RET_OK;
    }
    sg.own = 1;
    c = sg_first();
    sg.build_at = c;
    lo = c - SG_BUILD_N<0 ? 0 : c - SG_BUILD_N, hi = c + SG_BUILD_N>(int) sg.count - 1 ? (int)sg.count - 1
                                                                                       : c + SG_BUILD_N;
    for (i = 0; i <= hi - lo; ++i) { /* outward from the first in view: it, one after, one before, ... */
        int k, a;
        for (k = 0; k < 2; ++k) {
            unsigned key;
            int j;
            a = k ? c - i : c + i;
            if (a < lo || a > hi || (k && !i)) continue;
            key = sg.idx[a].key;
            for (j = 0; j < seen_n && seen[j] != key; ++j) {
            }
            if (j < seen_n) continue;
            seen[seen_n++] = key;
            if (cc_build_add(cc_str(deque_at(sg.list, (unsigned)a), REC_PATH), key) < 0) goto go;
        }
    }
go:
    if (!cc_build_start()) { /* nothing missing, no card, no space, no thread: the set is already freed */
        sg.own = 0;
        return RET_OK;
    }
    sg.done = 0;
    sg.build_timer = timer_add(sg_on_build, (void *)0, SG_BUILD_MS);
    if (!sg.build_timer) sg_build_end();
    return RET_OK;
}

/* The album view's build: the (at most RV_MAX) albums, in order, those with no cache file. */
static int rv_on_build_start(const void *unused) {
    unsigned i;
    (void)unused;
    sg.build_timer = 0;
    if (!sg.view || !sg.rv || !sg.rn || sg.own || !cc_build_open(sg.rn, CC_MISSING)) return RET_OK;
    sg.own = 1;
    for (i = 0; i < sg.rn; ++i) {
        void *rec = rv_rec((int)i);
        if (cc_build_add(cc_str(rec, REC_PATH), cc_album_key(rec)) < 0) break;
    }
    if (!cc_build_start()) { /* nothing missing, no card, no space, no thread: the set is already freed */
        sg.own = 0;
        return RET_OK;
    }
    sg.done = 0;
    sg.build_timer = timer_add(sg_on_build, (void *)0, SG_BUILD_MS);
    if (!sg.build_timer) sg_build_end();
    return RET_OK;
}

static void sg_build_later(void) {
    if (sg.view && (sg.rv ? sg.rg.tiles : sg.g.tiles) && !sg.own && !sg.build_timer)
        sg.build_timer = timer_add(sg.rv ? rv_on_build_start : sg_on_build_start, (void *)0, SG_BUILD_START_MS);
}

/* The scroll_view's EVT_SCROLL (every change of its offset) and scroll end: the title, the direction, the loader and, when the page has gone far from where
 * the build looked, a new build. */
static int sg_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.view) return RET_OK;
    sg_dir();
    sg_title_update();
    sg_kick();
    if (!sg.rv && sg_abs(sg_first() - sg.build_at) > SG_BUILD_MOVE && !sg_moving()) sg_build_later();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Reading the stock list
 */
static void sg_size(void) {
    int h = sg.rv ? (sg.rn ? rv_content() : GRID_VIEW_H) : sg.count ? sg_content() : GRID_VIEW_H;
    sg.al.content = sg_content();
    widget_resize(sg.view, SG_W, h);
    widget_set_prop_int(sg.sv, "virtual_h", h);
}

/* "%d Selected" in the player's language, the number where the translation has its %d. */
static void sg_fmt(char *out, unsigned size, const char *f, int n) { pod_fmt(out, size, f, n); }

static const char *sg_name_text(void) { return sg.key ? TR(sg.key) : sg.name; } /* a list's title */

/* The song count under the last row: "25 songs" (the key by n == 1, the number where the translation has its %d). */
static void sg_foot_text(void) {
    char buf[64];
    sg_fmt(buf, sizeof buf, TR(sg.count == 1 ? "%d song" : "%d songs"), (int)sg.count);
    widget_set_text_utf8(sg.foot, buf);
    widget_move(sg.foot, SG_HDR_X, sg_rows_end() + SG_FOOT_GAP);
}

/* A playlist's header from the list just read: the tile's four album keys (the Playlists page's mosaic, patch/grid.c grid_mosaic_keys, from the first PL_SCAN songs and
 * the library's albums for the lookup), the tile made again only when they changed (a return to the front keeps the mosaic: no flicker), and the count. */
static void sg_head_prep(void) {
    unsigned key[4];
    int nk, fresh, i, same;
    grid_tile_t *t;
    if (!sg.head) return;
    memset(key, 0, sizeof key);
    nk = sg.count ? grid_mosaic_keys(sg.list, sg.albums, key, (int *)0) : 0;
    t = grid_tile(&sg.hg, 0, 0, 0, &fresh);
    for (i = 0, same = !fresh && t->nq == (nk > 1 && !sg.htmp ? 1 : nk) && t->art; i < 4; ++i)
        same = same && t->qkey[i] == key[i];
    if (!same) {
        grid_free_art(t);
        t->art = 0, t->qi = 0;
        t->nq = nk > 1 && !sg.htmp ? 1 : nk;
        memcpy(t->qkey, key, sizeof key);
        if (!nk) t->art = 2; /* no album with a cover: the placeholder */
    }
}

static void sg_head(
    void) { /* the navbar's title: "N Selected" in select mode, else "Songs" or the list's name, cut to its room with an ellipsis */
    char buf[64];
    if (!sg.select) {
        az_fit(sg.title, sg_lib() ? TR("Songs") : sg_name_text());
        return;
    }
    sg_fmt(buf, sizeof buf, TR("%d Selected"), (int)sg.nsel);
    widget_set_text_utf8(sg.title, buf);
}

/* The rail's widget: centred on the list the select bar leaves (docs/modules/songs.md). */
static void sg_rail_fit(void) { az_rail_fit(&sg.al, GRID_VIEW_H - sg_pad()); }

/* The stock query again, and the page rebuilt from it: the index, the sections, the tiles. The library's albums are loaded first (once): both are stock queries
 * that replace *pdeq_showlist. */
static unsigned sg_sig(void *rec, unsigned key, unsigned rank) {
    const char *s[2];
    unsigned h = 2166136261u ^ key, k;
    s[0] = sg_name(rec), s[1] = cc_str(rec, sg.cls == CLASS_ARTIST_SONGS ? REC_ALBUM : REC_ARTIST);
    h = (h ^ rank) * 16777619u;
    for (k = 0; k < 2; ++k) {
        const unsigned char *p = (const unsigned char *)s[k];
        for (; *p; ++p) h = (h ^ *p) * 16777619u;
        h = (h ^ 0x100) * 16777619u; /* (the line's end: "ab","c" is not "a","bc") */
    }
    return h;
}

static void sg_load(int keep) {
    unsigned i;
    int at = keep ? sg_off() : 0, same = 0;
    void *list = (void *)0;
    song_t *old = sg.idx;
    unsigned old_n = sg.count;
    if (sg_lib())
        free(old),
            old =
                (song_t
                     *)0; /* (the library is big: its old index is not held beside the new one, and it is read again only when it changed) */
    if (sg.more_timer) timer_remove(sg.more_timer);
    sg.more_timer = 0;
    sg_build_end();
    rowmenu_close(&sg.rm); /* (a menu's row is an index of the list that is read again) */
    free(sg.sel);
    sg.idx = (song_t *)0, sg.sel = (unsigned char *)0, sg.list = sg.first = (void *)0, sg.count = sg.nsel = 0,
    sg.al.count = 0, sg.al.nsec = 0, sg.press = sg.down = 0;
    if (!sg.albums_tried) {
        sg.albums_tried = 1;
        sg.albums = cc_albums();
    }
    sg.sort = sg_lib() ? *(int *)SORT_FLAG : 0; /* (a list has the order of its query: sort_flag is the library's) */
    if (sg.sort < 0 || sg.sort > 4) sg.sort = 0;
    if (sg_query() > 0) list = *(void **)PDEQ_SHOWLIST;
    if (list && sg_flipped()) sg_reverse(list);
    if (list) sg.count = deque_size(list);
    if (sg.count) {
        sg.idx = calloc(sg.count, sizeof(song_t));
        sg.sel = calloc((sg.count + 7) / 8, 1);
        if (!sg.idx || !sg.sel) {
            free(sg.idx);
            free(sg.sel);
            sg.idx = (song_t *)0, sg.sel = (unsigned char *)0, sg.count = 0;
        }
    }
    sg.al.count = (int)sg.count;
    if (sg.count) {
        sg.list = list, sg.first = deque_at(list, 0);
        for (i = 0; i < sg.count; ++i) {
            void *rec = deque_at(list, i);
            sg.idx[i].key = cc_album_key(rec);
            sg.idx[i].letter = sg_rank(rec);
            if (!sg_lib())
                sg_set_sig(&sg.idx[i], sg_sig(rec, sg.idx[i].key,
                                              sg.idx[i].letter)); /* (the library keeps no old index to compare) */
        }
        if (sg_lib() && sg.sort == 0) {
            az_sections(&sg.al, &sg.idx[0].letter, sizeof(song_t));
            if (sg_flipped()) /* the headers and the rail show the letters of the mirrored ranks: rank 0 is Z, 25 is A, 26 is "#" */
                for (i = 0; i < (unsigned)sg.al.nsec; ++i) {
                    int t = sg.al.sec_letter[i] == '#' ? 0 : sg.al.sec_letter[i] - 'A' + 1;
                    sg.al.sec_letter[i] = (unsigned char)(t == 26 ? '#' : 'Z' - t);
                }
        }
    }
    /* The same rows as before (count and every sig; the tiles hold their texts and covers by row): the tiles and the placeholder stay, so a list read again
     * does not flash its covers away. Anything else, or a doubt, drops them. A cover that was not there (art 2) is looked for again. */
    if (old && old_n && old_n == sg.count && sg.g.tiles && sg.g.placeholder) {
        same = 1;
        for (i = 0; i < old_n && same; ++i)
            same = old[i].key == sg.idx[i].key && old[i].letter == sg.idx[i].letter && sg_same_sig(&old[i], &sg.idx[i]);
    }
    free(old);
    if (same && sg.tend != sg_edge()) same = 0; /* the rail came or went: the texts end elsewhere */
    sg.tend = sg_edge();
    if (same) {
        for (i = 0; i < (unsigned)sg.g.n; ++i)
            if (sg.g.tiles[i].art == 2) sg.g.tiles[i].art = 0;
    } else
        grid_drop(&sg.g);
    sg_head_prep();
    if (!same) grid_placeholder(&sg.g);
    sg_show(sg.view, sg.count != 0);
    sg_show(sg.status, sg.count == 0);
    if (!sg.count)
        widget_set_tr_text(sg.status, list ? "Not enough memory" : sg_lib() ? "Update Local Music first" : "No songs");
    sg_size();
    sg_foot_text();
    widget_set_prop_int(sg.sv, "yoffset",
                        at < 0 ? 0
                        : at > sg_max_scroll()
                            ? sg_max_scroll()
                            : at); /* a list read again keeps its place (or the last place there is) */
    sg.dir = 1;
    sg.seen = sg_off();
    sg.build_at = sg_first();
    sg_rail_fit();
    sg_head();
    sg_title_update();
    sg_redraw();
    sg_kick();
    sg_build_later();
}

/* Another query replaced the stock list under a page that is on top (a paint found it): read it again. A page behind another reads it when it comes back. */
static int sg_on_stale(const void *unused) {
    (void)unused;
    sg.stale_timer = 0;
    if (sg.view && !sg.rv && sg.g.tiles && !sg_valid() && pod_is_top(sg.win)) sg_load(1);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Recently Added's toggle between the songs and the albums (docs/modules/recent-albums.md)
 */

/* The Play / Shuffle buttons: the library's two flat pills, or a playlist's header disc and pill (album page style); the set not in use is hidden AND insensitive, the
 * albums view (rv) has neither, and in select mode the shown ones stay in the content, dead. */
static void sg_pills(void) {
    int lib = !sg.rv && !sg.head, hd = !sg.rv && sg.head;
    widget_set_visible(sg.btn_play, lib, 0);
    widget_set_visible(sg.btn_shuffle, lib, 0);
    widget_set_sensitive(sg.btn_play, lib && !sg.select);
    widget_set_sensitive(sg.btn_shuffle, lib && !sg.select);
    widget_set_visible(sg.hd_play, hd, 0);
    widget_set_visible(sg.hd_shuffle, hd, 0);
    widget_set_sensitive(sg.hd_play, hd && !sg.select);
    widget_set_sensitive(sg.hd_shuffle, hd && !sg.select);
    widget_set_visible(sg.pill.glyph, hd, 0); /* (an insensitive image: taps reach hd_play) */
}

/* The widgets of the view: the albums have no Play / Shuffle pills, no song count and no Select (the card's Select row goes, Albums ticked then). */
static void rv_ui(void) {
    sg_pills();
    if (sg.foot) widget_set_visible(sg.foot, !sg.rv, 0); /* (an insensitive label: shown, never a touch target) */
    vs_offer(&sg.vs, sg_offers());
}

/* The albums of the newest songs: the full `time_create desc` query (stock's "Time added (descending)" order, sort_flag 3 of getAllMusic, the flag put back at once),
 * each song resolved to the library album row of its album name (getAllAlbum groups by album COLLATE NOCASE, so a compilation's tracks all find the row of the album, and
 * so does its cover key), the first RV_MAX distinct rows in order; a song with no album is skipped. The query replaces *pdeq_showlist: the songs view reads its list again
 * when it comes back. 1 when done (rn may be 0), 0 when there was no memory (nothing was queried). */
static int rv_load(void) {
    void *list;
    unsigned i, j, n, nlib = sg.albums ? deque_size(sg.albums) : 0;
    int flag = *(int *)SORT_FLAG;
    free(sg.rrow);
    sg.rrow = (unsigned *)calloc(RV_MAX, sizeof(unsigned));
    sg.rn = 0;
    if (!sg.rrow) return 0;
    *(int *)SORT_FLAG = RV_SORT_TIME_DESC;
    list = loadLocalClassList(CLASS_ALL_SONGS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    *(int *)SORT_FLAG = flag;
    *(int *)G_CLASS_TYPE = sg.cls;
    n = list && nlib ? deque_size(list) : 0;
    for (i = 0; i < n && sg.rn < RV_MAX; ++i) {
        const char *album = cc_str(deque_at(list, i), REC_ALBUM);
        if (!*album) continue;
        for (j = 0; j < sg.rn && cc_nocase(cc_str(rv_rec((int)j), REC_ALBUM), album); ++j) {
        }
        if (j < sg.rn) continue; /* an album already in */
        for (j = 0; j < nlib; ++j) {
            void *r = deque_at(sg.albums, j);
            if (I(r, REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), album)) {
                sg.rrow[sg.rn++] = j;
                break;
            }
        }
    }
    sg.list = sg.first = (void *)0; /* the songs view's list is not the stock list any more */
    return 1;
}

/* A coasting list stops (patch/scroll.c sc_down), as the Albums page's mode switch does. */
static void sg_stop_scroll(void) {
    void *wa = P(sg.sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING && P(wa, SC_AN_WIDGET) == sg.sv) {
        widget_animator_destroy(wa);
        stock_scroll_done(sg.sv, (void *)0);
    }
}

static int rv_enter(void) {
    if (!sg_recent() || sg.rv || sg.select || !sg.st_gtitle || !sg.st_gsub) return 0;
    if (!grid_init(&sg.rg, sg.win, GRID_TILES, GRID_COVER, 0)) {
        grid_free(&sg.rg);
        return 0;
    }
    grid_shape(&sg.rg, GRID_COVER, GRID_R, 0);
    sg.rg.st_title = sg.st_gtitle, sg.rg.st_sub = sg.st_gsub;
    grid_placeholder(&sg.rg);
    sg_stop_scroll();
    if (sg.more_timer) timer_remove(sg.more_timer);
    sg.more_timer = 0;
    sg_build_end();
    if (!rv_load()) {
        grid_free(&sg.rg);
        return 0;
    }
    sg.rv = 1, sg.press = sg.down = 0, sg.dir = 1;
    rv_ui();
    sg_show(sg.view, sg.rn != 0);
    sg_show(sg.status, sg.rn == 0);
    if (!sg.rn) widget_set_tr_text(sg.status, "No albums");
    sg_size();
    widget_set_prop_int(sg.sv, "yoffset", 0);
    sg.seen = sg_off();
    sg_title_update();
    sg_redraw();
    sg_kick();
    sg_build_later();
    return 1;
}

static void rv_leave(void) {
    sg_stop_scroll();
    if (sg.more_timer) timer_remove(sg.more_timer);
    sg.more_timer = 0;
    sg_build_end();
    sg.rv = 0, sg.rn = 0;
    free(sg.rrow);
    sg.rrow = (unsigned *)0;
    grid_free(&sg.rg);
    rv_ui();
    sg_load(0); /* the songs view reads its own list again (the album view's query replaced it) */
}

/* The card's Albums / Songs rows: the albums grid or the songs list, in place, and the choice saved. The ticked row does nothing. */
static void sg_set_view(int grid) {
    if (!sg_recent() || sg.select || grid == sg.rv) return;
    if (sg.rv)
        rv_leave();
    else if (!rv_enter())
        return;
    home_write_atomic(RECENTADD_VIEW_FILE, RECENTADD_VIEW_TMP, sg.rv ? "1\n" : "0\n");
}

/* ---------------------------------------------------------------------------
 * Playing: the stock Songs row's handler (@0x5275a4: loadSongList of the shown list, then Now Playing at the row), as Shuffle Songs does it (patch/shuffle.c)
 */
/* Now Playing on the queue: the stock Songs row's tail (start_player copies the queue). */
static void sg_open_player(void *queue, int idx, int cls) {
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    context.dq = queue, context.idx = idx, context.cls = cls, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context);
}

/* Song `at` (-1: a random one) of the list and the list as the queue, in Now Playing (patch/songops.c). */
static void sg_play_at(int at, int how) {
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    sg_classinfo(); /* loadSongList runs the class query again and keeps classinfo for the memory playback */
    so_play_dir(sg.cls, sg.list, at, how, sg_open_player, sg_flipped());
}

static int sg_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg.view && sg.count) sg_play_at(0, SO_IN_ORDER);
    return RET_OK;
}

/* Shuffle: the library through Shuffle Songs (patch/shuffle.c: the stock Shuffle mode from a random song; it reads the list again: this page reads it when it is
 * back); a list in the stock Shuffle mode from a random song of its own, as the album page's Shuffle. */
static int sg_on_shuffle(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.view || !sg.count) return RET_OK;
    if (sg_lib())
        shuffle_play(0);
    else
        sg_play_at(-1, SO_SHUFFLE);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The select mode
 */
static void sg_select(int on) {
    int i;
    void *nav[2];
    if (on == sg.select) return;
    sg.select = on;
    sg.nsel = 0;
    if (sg.sel) memset(sg.sel, 0, (sg.count + 7) / 8);
    sg.press = sg.down = 0;
    nav[0] = sg.btn_more, nav[1] = sg.np;
    for (i = 0; i < 2; ++i) sg_show(nav[i], !on);
    if (sg.btn_cf) sg_show(sg.btn_cf, !on && sg_artist());
    if (sg.btn_search) sg_show(sg.btn_search, !on && sg_searches());
    sg_show(sg.btn_selall, on);
    sg_show(sg.bar, on);
    sg_pills(); /* the pills stay in the content, dim and dead (the library's) or dead (a playlist's) */
    widget_resize(sg.title, (on ? SG_SELALL_X : sg_title_end()) - NAV_TITLE_X, 22);
    widget_set_prop_str(sg.back, "style:normal:icon", on ? "ah_nav_close" : "ah_nav_back");
    widget_set_prop_str(sg.back, "style:over:icon", on ? "ah_nav_close" : "ah_nav_back");
    widget_set_prop_str(sg.back, "style:pressed:icon", on ? "ah_nav_close_down" : "ah_nav_back_down");
    sg.title_on = -1;
    sg_head();
    sg_title_update();
    sg_retext();
    sg_size();
    if (sg_off() > sg_max_scroll()) widget_set_prop_int(sg.sv, "yoffset", sg_max_scroll());
    sg_rail_fit();
    sg_redraw();
}

static void sg_count_changed(void) {
    sg_head();
    sg_redraw();
}

static void sg_toggle(int i) {
    if (i < 0 || i >= (int)sg.count || !sg.sel) return;
    sg.sel[i >> 3] ^= (unsigned char)(1 << (i & 7));
    sg.nsel += sg_is_sel(i) ? 1 : (unsigned)-1;
    sg_count_changed();
}

static int sg_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.select || !sg.sel) return RET_OK;
    if (sg.nsel < sg.count) { /* all, unless all are: then none */
        unsigned i;
        memset(sg.sel, 0, (sg.count + 7) / 8);
        for (i = 0; i < sg.count; ++i) sg.sel[i >> 3] |= (unsigned char)(1 << (i & 7));
        sg.nsel = sg.count;
    } else {
        memset(sg.sel, 0, (sg.count + 7) / 8);
        sg.nsel = 0;
    }
    sg_count_changed();
    return RET_OK;
}

/* Delete and Add run the stock code on the stock selection vector (patch/songops.c), filled from the page's marks at that moment. */
static int sg_on_delete(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.select) return RET_OK;
    if (so_delete(sg.cls, sg.list, sg.count, sg.sel, sg.nsel, sg_valid())) {
        sg_select(0);
        sg_load(1);
    }
    return RET_OK;
}

/* Add to playlist: the stock playlist picker over this page; the title the picker may overwrite and the browsing class it sets are put back when this window comes to the front. */
static int sg_on_add(void *ctx, void *e) {
    int r;
    (void)ctx;
    (void)e;
    if (!sg.select) return RET_OK;
    r = so_add(sg.cls, sg.count, sg.sel, sg.nsel, sg_valid(), sg.title_save, &sg.picker);
    if (r < 0) {
        sg_select(0);
        sg_load(1);
    }
    return RET_OK;
}

/* An artist's songs and Cover Flow's artist page are two views of the artist (a toggle: the Cover Flow button here, the list button there), so Back from this one
 * leaves the artist, not just the list: this page closes and, when the artist's covers page is what is under it, that closes too (two navigator_backs, no loop;
 * these pages have no close animation, so each takes effect at once). The Cover Flow button closes only this page. */
extern void *coverflow_artist_page(void); /* patch/coverflow.c: the artist's covers window, NULL when there is none */

static int sg_on_back(void *ctx, void *e) {
    void *cfw;
    (void)ctx;
    (void)e;
    if (sg.select) {
        sg_select(0);
        return RET_OK;
    }
    cfw = sg_artist() ? coverflow_artist_page() : (void *)0;
    navigator_back();
    if (cfw && window_manager_get_top_window(window_manager()) == cfw) navigator_back();
    return RET_OK;
}

static int sg_on_cf(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg.view && sg_artist() && !sg.select && !sg.menu) navigator_back();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows (the Albums list's: DOWN remembers, ABORT forgets, UP within the drag threshold on the same row acts)
 */
static int sg_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(sg.view, pt);
    return sg_at(pt[1]);
}

static void sg_set_press(int p) {
    if (sg.press == p) return;
    sg.press = p;
    sg_redraw();
}

/* The press or release is in a row's "..." zone. */
static int sg_in_zone(void *e) {
    int pt[2], x0;
    if (!sg_more()) return 0;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(sg.view, pt);
    x0 = rowmenu_zone_x(sg_more_right());
    return pt[0] >= x0 && pt[0] < x0 + RM_MORE_W;
}

/* Add to Playlist for one row (the menu's third row): the page's picker with a selection of that row alone. */
static void sg_add_one(int row) {
    int r;
    if (!sg.sel || row < 0 || row >= (int)sg.count) return;
    sg.sel[row >> 3] |= (unsigned char)(1 << (row & 7));
    r = so_add(sg.cls, sg.count, sg.sel, 1, sg_valid(), sg.title_save, &sg.picker);
    memset(sg.sel, 0, (sg.count + 7) / 8); /* (the picker and the stock vector have their own copies) */
    if (r < 0) sg_load(1);
}

static void sg_open_menu(int a) {
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    rowmenu_open(&sg.rm, a, deque_at(sg.list, (unsigned)a), sg_add_one);
}

static int sg_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    sg.down = sg.down_more = 0;
    if (sg.rv) { /* the album grid: no press fill */
        int pt[2];
        if (!e || !sg.view) return RET_OK;
        pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
        widget_to_local(sg.view, pt);
        sg.down = rv_cell_at(pt[0], pt[1]) + 1, sg.down_x = I(e, PE_X), sg.down_y = I(e, PE_Y);
        return RET_OK;
    }
    if (!e || !sg.view || !sg.count || !sg_valid()) return RET_OK;
    a = sg_item_of(e);
    sg.down = a + 1, sg.down_x = I(e, PE_X), sg.down_y = I(e, PE_Y);
    sg.down_more = a >= 0 && sg_in_zone(e);
    if (!sg.select && !sg.down_more) sg_set_press(a + 1);
    return RET_OK;
}

static int sg_on_up(void *ctx, void *e) {
    int a = sg.down - 1, more = sg.down_more;
    (void)ctx;
    sg.down = sg.down_more = 0;
    sg_set_press(0);
    if (a < 0 || !e || !sg.view) return RET_OK;
    if (sg.rv) { /* an album: our album page, as the Albums page's tap opens it (cc_open_album takes the stock row) */
        int pt[2];
        pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
        widget_to_local(sg.view, pt);
        if (sg_abs(I(e, PE_X) - sg.down_x) < SG_TAP_PX && sg_abs(I(e, PE_Y) - sg.down_y) < SG_TAP_PX &&
            rv_cell_at(pt[0], pt[1]) == a && (unsigned)a < sg.rn)
            cc_open_album((void *)0, 0, (int)sg.rrow[a]);
        return RET_OK;
    }
    if (sg_abs(I(e, PE_X) - sg.down_x) < SG_TAP_PX && sg_abs(I(e, PE_Y) - sg.down_y) < SG_TAP_PX &&
        sg_item_of(e) == a) {
        if (sg.select)
            sg_toggle(a);
        else if (more) {
            if (sg_in_zone(e)) sg_open_menu(a); /* (a press that began on the "..." and ended off it does nothing) */
        } else
            sg_play_at(a, SO_KEEP);
    }
    return RET_OK;
}

static int sg_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    sg.down = sg.down_more = 0;
    sg_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The rail (patch/azlist.c: grab, jump, bubble, the compact index and its alignment; docs/modules/songs.md)
 */

static int sg_on_rail(void *ctx, void *e) {
    (void)ctx;
    if (sg.view) az_rail_event(&sg.al, e);
    return RET_OK;
}

static int sg_on_rail_paint(void *ctx, void *e) {
    (void)ctx;
    if (sg.view) az_rail_paint(&sg.al, e);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The Sort card (patch/viewsort.c): Title, File Name, Format and Recently Added are the stock sort_flag 0, 1, 2 and 3 / 4 (Newest First / Oldest First under Recently Added); a row sets the
 * stock order (@0x47d114: sort_flag and [SYSSET] SORTSELECT) and the list is read again. The ticked row of the alphabetical three reverses (SONGS_SORT_FILE, saved first), Recently Added flips 3 and 4.
 */
static void sg_menu(int on) {
    sg.menu = on;
    vs_menu(&sg.vs, on, sg.sort > 3 ? 3 : sg.sort, sg.sort == 4 || sg_flipped(),
            !sg.rv); /* (Recently Added's Albums row is ticked in the albums view) */
}

static int sg_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg_direct()) {
        if (sg.view && sg.count && !sg.select)
            sg_select(1); /* Select straight away (an empty list has nothing to select) */
    } else if (sg.view && sg.vs.card && !sg.select)
        sg_menu(!sg.menu);
    return RET_OK;
}

static int sg_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    sg_menu(0);
    return RET_OK;
}

static void sg_set_flag(int flag) {
    *(int *)SORT_FLAG = flag;
    write_int_config(flag, "SYSSET", "SORTSELECT");
}

static void sg_search(void);

static int sg_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx, cur = sg.sort > 3 ? 3 : sg.sort;
    (void)e;
    sg_menu(0);
    if (k == VS_SELECT) { /* the old Select button: select mode (an empty list has nothing to select) */
        if (sg.view && sg.count && !sg.rv) sg_select(1);
        return RET_OK;
    }
    if (k == VS_SORTS || k == VS_SORTS + 1) { /* Recently Added's View group */
        sg_set_view(k == VS_SORTS);
        return RET_OK;
    }
    if (!sg.view || k < 0 || k >= VS_SORTS) return RET_OK;
    if (k == cur) {
        if (k == 3) { /* Recently Added: Newest First <-> Oldest First */
            sg_set_flag(sg.sort == 3 ? 4 : 3);
        } else { /* Title, File Name, Format: A-Z <-> Z-A, saved first (a save that fails changes nothing) */
            int rev = !sg.rev;
            if (home_write_atomic(SONGS_SORT_FILE, SONGS_SORT_TMP, rev ? "a\n" : "0\n") != 0) return RET_OK;
            sg.rev = rev;
        }
    } else { /* another order, in its default direction */
        if (sg.rev && home_write_atomic(SONGS_SORT_FILE, SONGS_SORT_TMP, "0\n") == 0) sg.rev = 0;
        sg_set_flag(k);
    }
    sg_load(0);
    return RET_OK;
}

/* Search: our keyboard, then our results page (patch/search.c, docs/modules/search.md). Its queries leave their list in *pdeq_showlist, which makes this page read it again when it is
 * back. Where ours will not open (a results page is already under this one, or no keyboard asset) the stock page (@0x52704c: navigator_to("search_page"), nothing set first). */
static void sg_search(void) {
    if (sg.view && !sg.select && search_open() < 0) navigator_to_with_context("search_page", (const void *)0);
}

static int sg_on_search(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.menu) sg_search();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
/* The lists whose content changes while the page is behind another: a play changes Recently Played and Most Played, Now Playing's star the Favourites. The others
 * (the library, a playlist, a genre, an artist, Recently Added, Hi-Res) change only through this page (its own delete and add read again) or the picker. */
static int sg_changes(void) { return sg.cls == CLASS_FAV || sg.cls == CLASS_RECENT || sg.cls == CLASS_OFTEN; }

static int sg_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.view || !sg.g.tiles) return RET_OK;
    if (sg.picker) { /* back from the stock playlist picker: its title and class put back, the add done (it changed the records it added), select mode over */
        sg.picker = 0;
        *(int *)G_CLASS_TYPE = sg.cls;
        memcpy((void *)NAV_TITLE, sg.title_save, sizeof sg.title_save);
        sg_select(0);
        sg_load(1);
    } else if (!sg.rv && (!sg_valid() || sg_changes())) /* (the album view reads no stock list: nothing is stale) */
        sg_load(1); /* (a list read again whose rows are the same keeps its tiles: sg_load) */
    sg_build_later();
    sg_kick(); /* the loader stops on a list another page replaced (Search's queries), and the list can be valid again by now: covers still to load start it here */
    return RET_OK;
}

static int sg_on_bg(void *ctx, void *e) {
    az_rail_end(&sg.al);
    rowmenu_close(&sg.rm);
    return sg_on_abort(ctx, e);
}

static int sg_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    if (sg.more_timer) timer_remove(sg.more_timer);
    if (sg.stale_timer) timer_remove(sg.stale_timer);
    sg_build_end();
    grid_free(&sg.g);
    grid_free(&sg.hg);
    grid_free(&sg.rg);
    free(sg.rrow);
    free(sg.htmp);
    if (sg.albums) deque_destroy(sg.albums);
    az_free(&sg.al);
    for (i = 0; i < 2; ++i)
        if (sg.mark[i]) bitmap_destroy(sg.mark[i]);
    free(sg.idx);
    free(sg.sel);
    rowmenu_free(&sg.rm);
    memset(&sg, 0, sizeof sg);
    if (sg_under) memcpy(&sg, sg_under, sizeof sg), free(sg_under), sg_under = (void *)0;
    return RET_OK;
}

/* A playlist's page over a Songs page (Search opened from it): the page below keeps its widgets, its state is set aside (its timers and the cover build ended; the
 * fg handler starts them again) and sg starts empty. 0 on success or with no page below, -1 when the page below stays (a second level, or no memory). */
static int sg_stack(void) {
    if (!sg.win) return 0;
    if (sg_under || !(sg_under = calloc(1, sizeof sg))) return -1;
    sg_build_end();
    if (sg.more_timer) timer_remove(sg.more_timer);
    if (sg.stale_timer) timer_remove(sg.stale_timer);
    sg.more_timer = sg.stale_timer = 0;
    memcpy(sg_under, &sg, sizeof sg);
    memset(&sg, 0, sizeof sg);
    return 0;
}

/* The page listing class cls (pl_id: a playlist's id; key: the title's key, or 0 for name). 0 once the page is up, -1 if the window could not open, -2 if the
 * asset is not ours (the page is left again). */
static int sg_open_page(int cls, int pl_id, const char *key, const char *name) {
    int i;
    if (sg.win && (cls != CLASS_PLAYLIST_SONGS || sg_stack() == -1)) return -1;
    memset(&sg, 0, sizeof sg);
    sg.cls = cls, sg.pl_id = pl_id, sg.key = key;
    if (sg_artist())
        memcpy(sg.ci, (void *)CLASSINFO, CLASSINFO_SIZE); /* songs_open_artist ran the two queries just before */
    for (i = 0; name[i] && i < (int)sizeof sg.name - 1; ++i) sg.name[i] = name[i];
    if (name[i]) /* a name cut short is cut before a character, not inside one */
        while (i > 0 && ((unsigned char)name[i] & 0xc0) == 0x80) --i;
    sg.name[i] = 0;
    sg.win = window_open("m1plus_songs");
    if (!sg.win) {
        if (sg_under)
            memcpy(&sg, sg_under, sizeof sg), free(sg_under),
                sg_under = (void *)0; /* the page below is the open one again */
        return -1;
    }
    widget_on(sg.win, EVT_DESTROY, sg_on_destroy, (void *)0);
    sg.back = pod_bind(sg.win, "btn_return", sg_on_back, (void *)0);
    sg.np = pod_bind(sg.win, "btn_backtoplayer", pod_on_player, (void *)0);
    sg.btn_more = pod_bind(sg.win, "btn_more", sg_on_more, (void *)0);
    sg.btn_select = pod_bind(sg.win, "btn_select", sg_on_more, (void *)0); /* optional: Select in the "..." place */
    sg.btn_cf = pod_bind(sg.win, "btn_coverflow", sg_on_cf, (void *)0); /* optional */
    sg.btn_search = pod_bind(sg.win, "btn_search", sg_on_search, (void *)0); /* optional */
    sg.st_gtitle = widget_lookup(sg.win, "label_grid_title", 1); /* optional: the album view's text styles */
    sg.st_gsub = widget_lookup(sg.win, "label_grid_sub", 1);
    sg.btn_selall = pod_bind(sg.win, "btn_selall", sg_on_selall, (void *)0);
    sg.btn_play = pod_bind(sg.win, "btn_play", sg_on_play, (void *)0);
    sg.btn_shuffle = pod_bind(sg.win, "btn_shuffle", sg_on_shuffle, (void *)0);
    sg.hd_play = pod_bind(sg.win, "hd_play", sg_on_play, (void *)0);
    sg.hd_shuffle = pod_bind(sg.win, "hd_shuffle", sg_on_shuffle, (void *)0);
    sg.pill.glyph = widget_lookup(sg.win, "sg_glyph", 1);
    sg.pill.ptext = widget_lookup(sg.win, "sg_play_text", 1);
    sg.btn_add = pod_bind(sg.win, "sg_add", sg_on_add, (void *)0);
    sg.btn_del = pod_bind(sg.win, "sg_del", sg_on_delete, (void *)0);
    sg.title = widget_lookup(sg.win, "label_title", 1);
    sg.fade = widget_lookup(sg.win, "img_nb_fade", 1); /* optional */
    sg.view = widget_lookup(sg.win, "view_grid", 1);
    sg.sv = widget_lookup(sg.win, "songs_scrollview", 1);
    sg.status = widget_lookup(sg.win, "label_status", 1);
    sg.st_title = widget_lookup(sg.win, "label_row_title", 1);
    sg.st_sub = widget_lookup(sg.win, "label_row_sub", 1);
    sg.al.st_hdr = widget_lookup(sg.win, "label_hdr", 1);
    sg.al.st_rail = widget_lookup(sg.win, "label_rail", 1);
    sg.al.st_rail_on = widget_lookup(sg.win, "label_rail_on", 1);
    sg.al.rail = widget_lookup(sg.win, "sg_rail", 1);
    sg.al.bubble = widget_lookup(sg.win, "sg_bubble", 1);
    sg.al.bubble_letter = widget_lookup(sg.win, "sg_bubble_letter", 1);
    sg.bar = widget_lookup(sg.win, "sg_bar", 1);
    sg.big = widget_lookup(sg.win, "sg_title", 1); /* optional: the large title */
    sg.foot = widget_lookup(sg.win, "sg_foot", 1);
    sg.hname = widget_lookup(sg.win, "sg_hname", 1); /* optional: a playlist's header */
    sg.al.win = sg.win, sg.al.sv = sg.sv, sg.al.top = SG_TOP, sg.al.row = ROW;
    az_prefs(&sg.al);
    if (!sg.foot || !sg.back || !sg.np || !sg.btn_more || !sg.btn_select || !sg.btn_selall || !sg.btn_play ||
        !sg.btn_shuffle || !sg.hd_play || !sg.hd_shuffle || !sg.pill.glyph || !sg.pill.ptext || !sg.btn_add ||
        !sg.btn_del || !sg.title || !sg.view || !sg.sv || !sg.status || !sg.st_title || !sg.st_sub || !sg.al.st_hdr ||
        !sg.al.st_rail || !sg.al.st_rail_on || !sg.al.rail || !sg.al.bubble || !sg.al.bubble_letter || !sg.bar) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    if (vs_bind(&sg.vs, sg.win, sg_on_item, sg_on_scrim, sg_offers())) { /* the rows this list offers (sg_offers) */
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    vs_dated(&sg.vs, 1u << 3); /* only Recently Added reads Newest First / Oldest First */
    if (sg_lib()) sg.rev = set_read(SONGS_SORT_FILE, '0') == 'a';
    rowmenu_bind(&sg.rm, sg.win); /* the rows' "..." menu (optional: no widgets means no "...") */
    if (sg_direct()) { /* the card would hold Select alone: the Select button takes the "..." place (left cap at 214, or the middle piece after Search / Cover Flow) and sg.btn_more stands for it from here on */
        sg_show(sg.btn_more, 0);
        sg.btn_more = sg.btn_select;
        sg_show(sg.btn_more, 1);
    }
    if ((sg_artist() && sg.btn_cf) ||
        sg_searches()) { /* the capsule's left cap at Albums' Cover Flow place: Cover Flow on an artist's songs, Search on the lists that search; the "..." (or Select) is its middle piece */
        const char *mid = sg_direct() ? "pod_nav_select" : "pod_nav_moremid";
        char down[32];
        snprintf(down, sizeof down, "%s_down", mid);
        sg_show(sg_artist() ? sg.btn_cf : sg.btn_search, 1);
        widget_set_prop_str(sg.btn_more, "style:normal:icon", mid);
        widget_set_prop_str(sg.btn_more, "style:over:icon", mid);
        widget_set_prop_str(sg.btn_more, "style:pressed:icon", down);
    }
    if (!sg_lib()) { /* a list: the titles are the list's */
        widget_resize(sg.title, sg_title_end() - NAV_TITLE_X, 22);
        az_fit(sg.big, sg_name_text());
    }
    /* A playlist's header (docs/modules/songs.md): the mosaic tile (the Playlists page's, patch/grid.c) and the name under it (the count is the footer under the last row,
     * as Apple Music's), the pills and the rows lower, the large title gone. Without the label, the tile or the quadrant buffer the page keeps its plain look (the large title). */
    if (sg.cls == CLASS_PLAYLIST_SONGS && sg.hname) {
        sg.htmp = calloc((PH_COVER / 2) * (PH_COVER / 2), 4);
        if (grid_init(&sg.hg, sg.win, 1, PH_COVER, PH_COVER_R)) {
            grid_placeholder(&sg.hg);
            sg.head = 1;
            sg.al.top = PH_TOP;
            widget_move(sg.hd_play, AH_PLAY_X, PH_BTN_Y);
            widget_move(sg.hd_shuffle, AH_SHUF_X, PH_BTN_Y);
            az_fit(sg.hname, sg_name_text());
            sg_show(sg.big, 0);
            widget_set_visible(sg.hname, 1, 0); /* (an insensitive label: shown, never a touch target) */
        } else
            grid_free(&sg.hg);
    }
    if (sg.head)
        pod_pill_place(&sg.pill, PH_BTN_Y);
    else {
        pod_centre_pill(sg.btn_play, SG_PILL_W);
        pod_centre_pill(sg.btn_shuffle, SG_PILL_W);
    }
    sg_pills();
    pod_centre_pill(sg.btn_add, SG_BAR_PILL_W);
    pod_centre_pill(sg.btn_del, SG_BAR_PILL_W);
    az_make_disc(&sg.al);
    sg.mark[0] = pod_make_mark(sg.win, "unselect");
    sg.mark[1] = pod_make_mark(sg.win, "selected");
    if (!sg.mark[0] || !sg.mark[1])
        sg.mark[0] = sg.mark[1] =
            (void *)0; /* (one that did not decode is freed with the other at destroy: the pair is all or none) */
    sg.noscroll = !widget_on(sg.sv, EVT_SCROLL, sg_on_scroll, (void *)0) ||
                  !widget_on(sg.sv, EVT_SCROLL_END, sg_on_scroll, (void *)0);
    if (sg.noscroll)
        widget_set_visible(
            sg.title, 1,
            0); /* the large title's collapse needs the scroll events: without them the navbar keeps its title */
    sg.title_on = sg.noscroll;
    widget_on(sg.win, EVT_WINDOW_TO_FG, sg_on_fg, (void *)0);
    widget_on(sg.win, EVT_WINDOW_TO_BG, sg_on_bg, (void *)0);
    widget_on(sg.view, EVT_POINTER_DOWN, sg_on_down, (void *)0);
    widget_on(sg.view, EVT_POINTER_UP, sg_on_up, (void *)0);
    widget_on(sg.view, EVT_POINTER_ABORT, sg_on_abort, (void *)0);
    widget_on(sg.view, EVT_AFTER_PAINT, sg_on_paint, (void *)0);
    widget_on(sg.al.rail, EVT_POINTER_DOWN, sg_on_rail, (void *)0);
    widget_on(sg.al.rail, EVT_POINTER_MOVE, sg_on_rail, (void *)0);
    widget_on(sg.al.rail, EVT_POINTER_UP, sg_on_rail, (void *)0);
    widget_on(sg.al.rail, EVT_POINTER_ABORT, sg_on_rail, (void *)0);
    widget_on(sg.al.rail, EVT_AFTER_PAINT, sg_on_rail_paint, (void *)0);
    if (!grid_init(&sg.g, sg.win, GRID_TILES, LIST_ART, 0)) {
        grid_free(&sg.g);
        sg_show(sg.view, 0);
        sg_show(sg.al.rail, 0);
        sg_show(sg.status, 1);
        widget_set_tr_text(sg.status, "Not enough memory");
        return 0;
    }
    grid_shape(&sg.g, LIST_ART, LIST_R, 1); /* the Albums list's covers: LIST_ART px, LIST_R corners cut in the alpha */
    *(int *)G_CLASS_TYPE = sg.cls; /* as allmusic_page_init leaves it (@0x5289e8) */
    sg_load(0);
    /* the view used last (a failure leaves the songs) */
    if (sg_recent() && set_read(RECENTADD_VIEW_FILE, '0') == '1') rv_enter();
    return 0;
}

static int sg_open(int cls, int pl_id, const char *key, const char *name, int home) {
    int r = sg_open_page(cls, pl_id, key, name);
    if (r == -1 && !sg.win && home >= 0) return pod_home_open(home);
    return r;
}

/* The M1+ Music menu's Songs row. A window that will not open leaves the stock Songs page, through the Home dispatcher. 0 once something is requested. */
int songs_open(void) { return sg_open(CLASS_ALL_SONGS, 0, (const char *)0, "", HOME_MYMUSIC); }

/* The lists the menu's rows open on this page (tools/pod_pages.py ACT_LIST, the row's argument is the stock Home tile): the tile, its class, the title's key (the row's text). */
static const struct {
    int home, cls;
    const char *key;
} SG_LISTS[] = {
    {HOME_FAV, CLASS_FAV, "Favorites"},
    {HOME_RECENTADD, CLASS_RECENTADD, "Recently Added"},
    {HOME_RECENT, CLASS_RECENT, "Recently Played"},
    {HOME_MOST, CLASS_OFTEN, "Most Played"},
    {HOME_HIRES, CLASS_HIRES, "hr"},
};

/* A list row of the menu. A window that will not open, or a tile that is not one of the lists, leaves the tile's stock page. */
int songs_open_list(int home) {
    unsigned i;
    for (i = 0; i < sizeof SG_LISTS / sizeof SG_LISTS[0]; ++i)
        if (SG_LISTS[i].home == home) return sg_open(SG_LISTS[i].cls, 0, SG_LISTS[i].key, "", home);
    return pod_home_open(home);
}

/* The Playlists page's tap on playlist `id` called `name`: -1 when the page did not open (the caller opens the stock songs page). */
int songs_open_playlist(int id, const char *name) {
    return sg_open(CLASS_PLAYLIST_SONGS, id, (const char *)0, name, -1);
}

/* The Genres page's tap on the genre `name` (unknown: its Unknown Genre row): the genre's songs, titled with the name. A window that will not open leaves the stock row tap's
 * own sequence (@0x535c4c: the browsing record, then allmusic_page with 0xff09; the stock query sets the page's title), so the stock Songs page opens. */
int songs_open_genre(const char *name, int unknown) {
    int r = sg_open(CLASS_GENRE_SONGS, unknown != 0, (const char *)0, name, -1);
    if (r == -1 && !sg.win) {
        sg_genre_info(name, unknown);
        navigator_to_with_context("allmusic_page", (const void *)CLASS_GENRE_SONGS);
    }
    return r;
}

/* The artist's (scope CLASS_ARTISTS) or composer's (CLASS_COMPOSERS) songs as the stock All songs card gets them (the two queries songs_open_artist runs, no page):
 * loadAlbumList(0xf004 / 0xf005, row) fills the browsing record and the albums, the last one the All songs row (getAlbumByArtist and getAlbumByComposer both append it),
 * and loadAlbumdetailList(0xff01 / 0xff02, that row) turns the record into class 0xff11's / 0xff14's and lists the songs. Returns that stock list (in *pdeq_showlist,
 * good until the next query), or NULL when there is no All songs row. */
void *songs_artist_list(void *artist, unsigned scope) {
    void *list, *row;
    unsigned n;
    int comp = scope == CLASS_COMPOSERS;
    if (!artist) return (void *)0;
    loadAlbumList(comp ? CLASS_COMPOSERS : CLASS_ARTISTS, artist);
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    row = n ? deque_at(list, n - 1) : (void *)0;
    if (!row || I(row, REC_ID) != ID_ALL_SONGS) return (void *)0;
    loadAlbumdetailList(comp ? CLASS_COMPOSER_ALBUMS : CLASS_ARTIST_ALBUMS, row);
    return *(void **)PDEQ_SHOWLIST;
}

/* Cover Flow's artist page and the scoped Albums page's All Songs tile (`artist`: the Artists row, the name in REC_TITLE; scope CLASS_ARTISTS, or CLASS_COMPOSERS for
 * a composer's row): every song of the artist or composer (songs_artist_list), class 0xff11 or 0xff14. The page keeps the record. -1 when the page did not open or there
 * is no All songs row (the caller opens the stock page). */
int songs_open_artist(void *artist, unsigned scope) {
    if (sg.win || !artist || !songs_artist_list(artist, scope)) return -1;
    return sg_open(scope == CLASS_COMPOSERS ? CLASS_14 : CLASS_ARTIST_SONGS, 0, (const char *)0,
                   cc_str(artist, REC_TITLE), -1);
}

/* The artist's (or composer's: scope CLASS_COMPOSERS) albums page's Play (how SO_IN_ORDER: the songs in order from the first) and Shuffle (SO_SHUFFLE: the stock Shuffle
 * mode from a random song), the way this page's pills play the list: the two queries, then so_play on class 0xff11 (a composer's 0xff14, the class the stock All songs
 * row leaves; the record is fresh). -1 when there is nothing to play. */
int songs_play_artist(void *artist, unsigned scope, int how) {
    void *list = songs_artist_list(artist, scope);
    if (!list || !deque_size(list)) return -1;
    so_play(scope == CLASS_COMPOSERS ? CLASS_14 : CLASS_ARTIST_SONGS, list, how == SO_SHUFFLE ? -1 : 0, how,
            sg_open_player);
    return 0;
}
