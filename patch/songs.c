/* M1+ Music Songs: the library as one list, in the Apple Music manner.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_songs.bin (docs/modules/songs.md has the whole design): the glass navbar (Back, the small title, the "..." that holds Select, a playlist's Rename / Clean Up / Pin Playlist, Albums / Songs and Sort, Now Playing) over a
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
 *             and play; the artist is the title and the grey line of a row is its album. A composer's songs (songs_open_artist with CLASS_COMPOSERS) are the same on
 *             class 0xff14 (loadAlbumList(0xf005), loadAlbumdetailList(0xff02)), the grey line staying the artist.
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
#include "libsrc.h"
#include "sbsrc.h"
#include "fnv.h"
#include "coverflow.h"
#include "entries.h"
#include "artsplit.h"
#include "genresplit.h"
#include "search.h"
#include "pins.h"
#include "selmode.h"
#include "keyboard.h"

#define ROW LIST_ROW_H
#define SG_MARK_UP \
    1 /* a source row's marks sit 1 px above the grey line's box centre: that box centres the font's whole line, and the letters' own middle (cap height) is higher */
#define SG_W 320 /* the content's width: the list_view's (the scroll_view clips at 310) */
#define SG_AHEAD 2 /* rows loaded beyond the view in the scroll direction */
#if GRID_TILES < (GRID_VIEW_H / LIST_ROW_H) + 2 + 2 + 2
#error GRID_TILES cannot hold the visible rows, the next two and the history
#endif
#if SG_RAIL_ITEMS * SG_RAIL_PITCH > GRID_VIEW_H - SG_BAR_H
#error the rail cannot hold SG_RAIL_ITEMS items in select mode
#endif

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
    m1_pill_t pill;
    void *st_title, *st_sub; /* hidden labels whose styles are the text styles (the rail's and the header's are az's) */
    void *st_dim,
        *st_subdim; /* a source's rows that cannot play: the title's and the grey line's dim styles (NULL: drawn as the others) */
    void *bar;
    vs_t
        vs; /* the "..." card (patch/viewsort.c): Select, a stock playlist's Rename (slot 6) / Clean Up / Pin Playlist, Albums / Songs (Recently Added), Title, File Name, Format, Recently Added (the library) */
    void *list; /* the stock list the index is of (*pdeq_showlist when valid) */
    void *first; /* its first record: with the size, tells a list another query replaced */
    unsigned count;
    song_t *idx; /* count entries */
    m1_sel_t sel; /* the select mode's marks and chrome (patch/selmode.c) */
    int select; /* select mode */
    int sort; /* sort_flag as the page last read it */
    int rev; /* the library's Title, File Name and Format orders run Z-A (SONGS_SORT_FILE): the stock list is reversed in place after the query */
    az_t al; /* the sections and the rail (patch/azlist.c); al.nsec is 0 for a plain list */
    void *albums; /* the library's albums (cc_albums), for the cover lookup */
    int albums_tried;
    int press; /* the row under the finger, + 1 */
    int seen, dir, noscroll;
    int down; /* the row a press began on, + 1 */
    m1_tap_t tap; /* and where */
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
    void *hname2; /* the name's second line (sg_hname2): m1_wrap2 breaks a name wider than PH_NAME_W */
    int tsh; /* 0, or AH_TITLE_LH while the name takes two lines: the pills and the rows are that much lower */
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
    int down_name; /* Edit mode: the press began on the header's name (a tap renames) */
    int down_cover; /* Edit mode: the press began on the header's cover (a tap opens the Cover page) */
    int cover_due; /* the Cover page is open over this page: the header is made again when this page is back in front */
    void *
        cbadge; /* Edit mode: the round pencil on the header cover's lower right corner (sg_cbadge, a bitmap painted over the cover); 0: none */
    int pick; /* the Add Songs page (docs/modules/songs.md "Add Songs"): the library over a playlist's Edit page; a tap adds the song to playlist pk_id */
    int pk_id; /* the playlist the picked songs go to */
    unsigned *pk_h; /* the playlist's songs (and those added here) as two FNV words of the path each, pk_n pairs */
    unsigned pk_n;
    void *pk_add, *pk_done; /* the marks as bitmaps (sg_padd white, sg_pdone grey): alpha the coverage */
    int addrow; /* an empty stock playlist: its header and one Add Songs row (the tile, the text), no pills, no footer, no "No songs" (sg_load) */
    int add_down; /* the press began on the Add Songs row (drawn pressed) */
    void *add_note,
        *add_badge; /* the Add Songs tile's masks as bitmaps (sg_addnote grey, sg_addbadge white); 0: no Add Songs row */
    int reread; /* the page was under an Add Songs page: its fg handler reads the list again (Edit mode kept) */
    int fg_due; /* the page was put back from sg_under and its fg handler has not run since (sg_on_put_back runs it) */
    void *
        handle; /* Edit mode's reorder handle (sg_handle) as a bitmap: alpha the coverage, colour SG_HANDLE_RGB; 0: no handles, no reorder */
    int lift; /* Edit mode: the row lifted by its handle, + 1 (0: none) */
    int lslot, lgrab, lfy,
        lslide; /* the lift: the slot the row would land in, the finger's offset on the row's top, the finger's y in the window (the list's top 0), the list's yslidable before */
    unsigned edge_timer; /* the lift's auto-scroll near the list's top or the select bar */
    void *hpencil, *edel,
        *eplus; /* Edit mode: the grey pencil after the name (sg_hpencil), the bar's Delete and + (sg_edel, sg_eplus) */
    const lib_src_t *
        src; /* a non-stock library source (songs_open_src), or 0: every stock path above is then unchanged; sg.list is the source's own copy (deque_destroy) */
    int split; /* an artist's songs from the artist split (patch/artsplit.c): the list is built from the library's songs, not the stock query; sg.name is the artist, sg.pl_id 1 for the Unknown Artist row */
    int gsplit; /* a genre's songs from the genre split (patch/genresplit.c): the list is the stock genre query run once per tag that names it (gs_fill); sg.name is the name, sg.pl_id 1 for the Unknown Genre row */
    int which; /* the source's list: LS_SONGS, LS_FAVORITES or LS_DOWNLOADED */
    int part; /* the source's list is a part that grows (lib_src_t.complete): no sections, no rail */
    unsigned sgen, srows; /* the source's gen and gen_rows when the list was read */
    unsigned dlsig; /* LS_DOWNLOADED: the source's dl_rows when the list was read */
    int dlq,
        down_act; /* LS_DOWNLOADED: the rows at the top that are downloads still to come (the Downloading section); a press began on its Clear */
    unsigned gen_timer; /* the source's gen poll */
    ls_cpoll_t
        cp; /* the shared cover poll (patch/libsrc.c ls_cover_poll): the retry of the covers the source was asked for */
    void *
        scope_d; /* a source's list of a row (songs_open_src_in): a one-record deque, our copy of the row, the scope of every re-read; freed with the page */
    void *
        spin; /* a source's page: the loading spinner (sg_spin, optional: the status label says Loading... without it) under the title */
    int wait; /* the source's rows are not cached yet (lib_src_t.state): the page and the spinner show, not the empty text */
    grid_t g; /* the tile ring (LAST: test/pod/songs.py reads the fields above by index) */
} sg __attribute__((section(".scratch")));

static int sg_on_stale(const void *unused);
static void *sg_under __attribute__((section(
    ".scratch"))); /* a Songs page below the one open (Search was opened from it and a playlist result opened ours): its state, put back when this page is destroyed */

static int sg_off(void) { return grid_sv_off(sg.sv); }
static void sg_redraw(void) { grid_sv_redraw(sg.sv); }

/* A lifted row (Edit mode's reorder, docs/modules/songs.md "Reorder") is let go: the auto-scroll timer is removed, the touch released and the list slides again. Safe to call at any time. */
static void sg_lift_end(int repaint) {
    if (!sg.lift) return;
    sg.lift = 0;
    m1_timer_stop(&sg.edge_timer);
    if (m1_lift_sv == sg.sv) m1_lift_sv = (void *)0;
    if (sg.sv) {
        widget_ungrab(sg.sv, sg.view);
        widget_set_prop_int(sg.sv, "yslidable", sg.lslide);
    }
    if (repaint) sg_redraw();
}

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
    if (sg_flipped()) k = az_flip_rank(k); /* Z-A (as the Artists page) */
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
    void *cur =
        sg.src ? sg.list : *(void **)PDEQ_SHOWLIST; /* a source's list is the page's own copy: nothing replaces it */
    return grid_list_same(cur, sg.list, sg.count, sg.first);
}

static int sg_lib(void) {
    return sg.cls == CLASS_ALL_SONGS && !sg.src;
} /* the library: the only list with the sort card, sections and the rail */
/* A source's complete Songs list is sectioned by the title's first letter (az_sections copes with a source that is not in title order); a part of it that grows has no rail. */
static int sg_ranked(void) { return sg.src && sg.which == LS_SONGS && !sg.scope_d && !sg.part; }
static int sg_genre(void) {
    return sg.cls == CLASS_GENRE_SONGS;
} /* a genre's songs: the stock navbar has no Search there */
static int sg_artist(void) {
    return sg.cls == CLASS_ARTIST_SONGS || sg.cls == CLASS_14;
} /* an artist's (or a composer's) songs: Cover Flow's artist page is its other view (a toggle, not a stack) */
/* The page kinds a source shares with the stock classes: a source's playlist is the playlist page (header, no Search), a source artist's All Songs the artist's songs (the artist is the
 * title, the album the grey line, no sections, no Search; its Cover Flow slot stays empty as the source has no Cover Flow). */
static int sg_playlist(void) { return sg.cls == CLASS_PLAYLIST_SONGS || (sg.src && sg.which == LS_PLAYLISTS); }
static int sg_artist_songs(void) {
    return sg.cls == CLASS_ARTIST_SONGS || (sg.src && sg.scope_d && sg.which == LS_SONGS);
}
static int sg_recent(void) {
    return sg.cls == CLASS_RECENTADD;
} /* Recently Added: its card also holds the Albums / Songs rows (the songs or the newest albums) */
static int sg_searches(void) {
    return !sg.pick && !sg_genre() && !sg_artist() && !sg_artist_songs() && !sg_playlist() && sg.btn_search &&
           (ls_caps(sg.src) &
            LS_CAP_SEARCH); /* (sg_artist: a composer's songs too, which sg_artist_songs leaves out) */
} /* a list with the Search button (a genre's songs: the stock navbar has none; an artist's: Cover Flow has its place; a playlist's: no Search inside a playlist; a source without the control: none) */
static int sg_selects(void) { return (ls_caps(sg.src) & LS_CAP_SELECT) != 0; }
static int sg_cleans(void) {
    return sg.cls == CLASS_PLAYLIST_SONGS && !sg.src;
} /* a stock playlist's songs: the card has Clean Up Playlist under Select (a source's playlist is the server's: nothing to clean) */
/* A stock playlist's Edit mode: select mode with the pills gone, the rows higher, the name tappable and the bar's Delete | + (docs/modules/songs.md "A playlist's header"). */
static int sg_edit(void) { return sg.select && sg.head && sg_cleans(); }
/* Edit mode's reorder handles (docs/modules/songs.md "Reorder"): at the right of every row of a plain list (a playlist has no sections); the row text ends at their zone. */
static int sg_handles(void) { return sg_edit() && sg.handle && !sg.al.nsec && sg.count; }
static int sg_direct(void) {
    return !sg_lib() && !sg_recent() && !sg_cleans();
} /* a list whose "..." card would hold Select alone: the navbar has the Select button instead (btn_select), no card */
static int sg_mid(void) {
    return !sg_direct() || sg_selects();
} /* the capsule has its "..." (or Select) piece; a source's direct list without Select has none */
static int sg_title_end(void) {
    if (sg.pick) return NAV_VIEW_X + NAV_VIEW_W; /* (Done and the title alone: no capsule, no Now Playing) */
    if ((sg_artist() && sg.btn_cf) || sg_searches()) return sg_mid() ? NAV_CF_X : NAV_VIEW_X;
    if (sg.src && !sg_selects())
        return NAV_VIEW_X + NAV_VIEW_W; /* no button at all: the title runs to Now Playing (260) */
    return NAV_VIEW_X;
} /* the small title ends at the capsule's first piece: "..." (214), or Search / Cover Flow (168) */
/* The rows of the "..." card the list offers, what its navbar had as buttons: Select (not in Recently Added's albums view), Albums / Songs (Recently Added), the four sorts (the library).
 * Search is the navbar button (btn_search), not a row. */
static unsigned sg_offers(void) {
    if (sg_lib()) return VS_WITH_SELECT | VS_ALL_SORTS;
    if (sg_recent()) return VS_WITH_VIEWS | (sg.rv ? 0 : VS_WITH_SELECT);
    if (sg_cleans())
        return VS_WITH_SELECT | VS_WITH_ACT2 |
               VS_WITH_ACT3; /* a playlist: Edit (the Select row, sg_edit_row), Clean Up Playlist (slot 8), Pin / Unpin Playlist (slot 9) */
    return VS_WITH_SELECT;
}

/* What a genre's stock row tap leaves in the browsing record (@0x535c4c): classinfo[0] = 0xff09, the name (0x80 bytes, cut as snprintf cuts it) at + 0x30d, the byte + 0xc. */
static void sg_genre_info(const char *name, int unknown) { songs_genre_record(name, unknown); }

/* The browsing record a stock genre row tap leaves: sg_genre_info and the genre split's per-tag queries (patch/genresplit.c) write it the same way. */
void songs_genre_record(const char *name, int unknown) {
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
    if (sg.gsplit)
        return gs_fill(
            sg.name, sg.pl_id); /* every tag that names it, asked through the stock genre query (patch/genresplit.c) */
    if (sg.split)
        return as_fill(
            sg.name,
            sg.pl_id); /* the browsing record is as songs_open_artist left it; the list is the artist's songs */
    return loadLocalClassList(sg.cls);
}

/* Content geometry (patch/azlist.c: the rows, and the headers in Title order, start at SG_TOP; section s's header is at az_hdr_y(s), its songs follow). The page
 * keeps al.count and al.content (what the scroll offset is clamped to) in step with the list: sg_load and sg_size. */
static int sg_row_y(int i) { return az_row_y(&sg.al, i); }
static int sg_pad(void) {
    return sg.select ? SG_BAR_H : 0;
} /* the bar covers the window's last SG_BAR_H rows: the list scrolls clear of it */
static int sg_rows_end(void) { return az_rows_end(&sg.al); } /* the content y under the last row: the song count */
static int sg_content(void) { return sg_rows_end() + (sg.addrow ? ROW : 0) + SG_FOOT_H + sg_pad(); }
static int sg_max_scroll(void) { return az_max_scroll(&sg.al); }
static int sg_row_from(int y) { return az_row_from(&sg.al, y); }
static int sg_at(int y) {
    return az_pin_hit(&sg.al, y) ? -1 : az_at(&sg.al, y);
} /* the song under content point y: its row, or -1 for the title block, a header (the pinned band too) and the air below the last row */
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
static int sg_edge(void) {
    return rowmenu_on(&sg.rm) ? rowmenu_text_end(sg_more_right(), az_inset(&sg.al) > 0) : az_end(&sg.al);
}
static int sg_more(void) { return !sg.select && !sg.pick && rowmenu_on(&sg.rm); }
static int sg_text_end(void) { return sg.select ? (sg_handles() ? SG_HANDLE_X : az_end(&sg.al)) : sg_edge(); }

/* Edit mode's handle as a bitmap, as the rows' "..." is made (patch/rowmenu.c rowmenu_make_glyph): the image sg_handle is white on transparent (cc_decode flattens it over black: the red channel is the coverage),
 * the bitmap's alpha is that coverage and its colour SG_HANDLE_RGB. 0 when it cannot be made. */
static void *sg_make_bmp(const char *image, unsigned size, unsigned rgb) {
    unsigned *px, i;
    void *b = bitmap_create_ex(size, size, size * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != size * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(sg.win, image, 1, size, 1, px);
    for (i = 0; ok && i < size * size; ++i) px[i] = (px[i] & 0xff) << 24 | rgb;
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}
static void *sg_make_handle(void) { return sg_make_bmp("sg_handle", SG_HANDLE_PX, SG_HANDLE_RGB); }

/* Add Songs: the song is in the playlist (or was added here); the playlist's songs are kept as so_song_key words. */
static int sg_pk_has(void *rec) {
    unsigned h[2], i;
    so_song_key(rec, h);
    for (i = 0; i < sg.pk_n; ++i)
        if (sg.pk_h[2 * i] == h[0] && sg.pk_h[2 * i + 1] == h[1]) return 1;
    return 0;
}

/* The tile of song a, made from the stock record (the caller has checked sg_valid). */
static void sg_prep(tile_t *t, int a) {
    void *rec = deque_at(sg.list, (unsigned)a);
    const char *sub = cc_str(
        rec, sg_artist_songs() ? REC_ALBUM
                               : REC_ARTIST); /* an artist's list: the artist is the title, the album the grey line */
    char buf[300];
    if (sg.cls ==
        CLASS_OFTEN) { /* Most Played: "12 plays · Artist" (the count first, a long artist is the part that is cut); REC_TRACK = plays - 1 */
        int plays = I(rec, REC_TRACK) + 1;
        char count[48];
        m1_fmt(count, sizeof count, TR(plays == 1 ? "%d play" : "%d plays"), plays);
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
        d = m1_abs(top + GRID_CELL_H / 2 - GRID_VIEW_H / 2);
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
/* A lifted row (Edit mode's reorder): the slot it is over has the others closed up around it. Row r is shown at the position sg_vrow(r) (the lifted row's own is the slot, drawn empty). */
static int sg_vrow(int r) {
    int l = sg.lift - 1, s = sg.lslot;
    if (!sg.lift || r == l) return r;
    if (l < s && r > l && r <= s) return r - 1;
    if (s < l && r >= s && r < l) return r + 1;
    return r;
}

/* The reorder handle of the row whose top is at window y: the bitmap centred at SG_HANDLE_CX on the row, clipped to the window as the rows' "..." is. */
static void sg_handle_paint(void *canvas, int y) {
    int cy = y + (ROW - 1 - SG_HANDLE_PX) / 2, top = cy < 0 ? -cy : 0,
        bottom = cy + SG_HANDLE_PX > GRID_VIEW_H ? GRID_VIEW_H - cy : SG_HANDLE_PX, src[4], dst[4];
    if (!sg_handles() || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = SG_HANDLE_PX, src[3] = bottom - top;
    dst[0] = SG_HANDLE_CX - SG_HANDLE_PX / 2, dst[1] = cy + top, dst[2] = SG_HANDLE_PX, dst[3] = bottom - top;
    canvas_draw_image(canvas, sg.handle, src, dst);
}

/* The lifted row, over everything the rows drew: the lighter background, its marks, cover, texts and handle at the finger (sg.lfy - sg.lgrab). No shadow: the list is black around it. */
static void sg_paint_float(void *canvas, int tx, int room) {
    int r = sg.lift - 1, y = sg.lfy - sg.lgrab, pass;
    tile_t *t;
    if (r < 0 || r >= (int)sg.count) return;
    t = sg_tile(r);
    az_fill(canvas, 0, y, y + ROW - 1, SG_W, SG_FLOAT_BG);
    m1_sel_paint(&sg.sel, canvas, r, y, ROW, SG_W, LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, GRID_VIEW_H);
    grid_blit(canvas, &sg.g, t, sg_art_x(), y + LIST_ART_Y, GRID_VIEW_H);
    for (pass = 0; pass < 2; ++pass) {
        widget_prepare_text_style(pass ? sg.st_sub : sg.st_title, canvas);
        grid_text(canvas, t, pass, tx, y + (pass ? LIST_SUB_Y : LIST_TITLE_Y), room, pass ? LIST_SUB_H : LIST_TITLE_H,
                  0);
    }
    sg_handle_paint(canvas, y);
}

/* Edit mode's round pencil on the header cover's lower right corner, over the cover (a child widget would be under it: the content paints in its EVT_AFTER_PAINT). */
#define SG_CBADGE 28 /* tools/mod_icons.py SG_CBADGE */
#define SG_CBADGE_IN 6 /* px in from the cover's corner */
static void sg_cbadge_paint(void *canvas, int off) {
    if (!sg_edit() || !sg.cbadge) return;
    grid_blit_from(canvas, sg.cbadge, 0, 0, SG_CBADGE, SG_CBADGE, PH_COVER_X + PH_COVER - SG_CBADGE - SG_CBADGE_IN,
                   PH_COVER_Y + PH_COVER - SG_CBADGE - SG_CBADGE_IN - off, GRID_VIEW_H);
}

static void sg_paint_rows(void *canvas) {
    int r0, r1, r, off = sg_off(), tx = sg_tx(), hair = az_end(&sg.al) - tx, room = sg_text_end() - tx, pass;
    ls_row_t xr[32]; /* a source's row extras, read once per paint (src only; at most 32 rows are in view) */
    unsigned dim = 0; /* bit r - r0: a source's row that cannot play now: dim title and grey line */
    if (sg.head &&
        !sg.wait) { /* a playlist's mosaic (the cover, or the placeholder disc until it is made; not while its tracks are on their way) */
        grid_tile_t *h = grid_find(&sg.hg, 0);
        if (h) grid_blit(canvas, &sg.hg, h, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
        if (h && !sg.src) grid_plc_name(canvas, &sg.hg, h, sg.name, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
        sg_cbadge_paint(canvas, off);
    }
    if (sg.head && !sg.wait && !sg_edit())
        m1_pill_paint(&sg.pill, canvas, PH_BTN_Y + sg.tsh - off); /* a playlist's Play pill text, over its picture */
    sg_span(&r0, &r1);
    if (sg.src && r1 - r0 > 31) r1 = r0 + 31;
    if (sg.lift) { /* (a row may be shown one position beside where it is) */
        if (r0 > 0) --r0;
        if (r1 < (int)sg.count - 1) ++r1;
    }
    for (r = r0; r <= r1; ++r) {
        tile_t *t;
        int y = sg_row_y(sg_vrow(r)) - off;
        if (sg.lift == r + 1) continue; /* (its slot stays empty) */
        t = sg_tile(r);
        if (sg.src) {
            sg.src->row(sg.src, deque_at(sg.list, (unsigned)r), &xr[r - r0]);
            if (sg.st_dim && sg.st_subdim && xr[r - r0].offline) dim |= 1u << (r - r0);
        }
        if (sg.press == r + 1 && !sg.select) az_fill(canvas, 0, y, y + ROW - 1, SG_W, LIST_PRESS);
        m1_sel_paint(&sg.sel, canvas, r, y, ROW, SG_W, LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, GRID_VIEW_H);
        grid_blit(canvas, &sg.g, t, sg_art_x(), y + LIST_ART_Y, GRID_VIEW_H);
        az_fill(canvas, tx, y + ROW - 1, y + ROW, hair, LIST_HAIR);
        if (sg_more())
            rowmenu_paint(canvas, &sg.rm, sg_more_right(), az_inset(&sg.al) > 0, y, ROW, GRID_VIEW_H);
        else if (sg.pick)
            rowmenu_paint_bmp(canvas, sg_pk_has(deque_at(sg.list, (unsigned)r)) ? sg.pk_done : sg.pk_add,
                              sg_more_right(), az_inset(&sg.al) > 0, y, ROW, GRID_VIEW_H);
        sg_handle_paint(canvas, y);
    }
    for (
        pass = 0; pass < (sg.src ? 4 : 2);
        ++pass) { /* titles, then artists, then (a source's rows that cannot play) the same in the dim styles: one text style at a time */
        widget_prepare_text_style(pass == 0   ? sg.st_title
                                  : pass == 1 ? sg.st_sub
                                  : pass == 2 ? sg.st_dim
                                              : sg.st_subdim,
                                  canvas);
        for (r = r0; r <= r1; ++r) {
            int y = sg_row_y(sg_vrow(r)) - off, sub = pass & 1, pre = 0;
            if (sg.lift == r + 1) continue;
            if (sg.src && (int)(dim >> (r - r0) & 1) != pass >> 1) continue;
            if (sub && sg.src) { /* the grey line: the marks first, then the artist */
                ls_row_t *x = &xr[r - r0];
                pre = ls_marks_w(x);
                if (pre) pre += LS_MK_GAP;
                ls_marks_draw(canvas, sg.win, x, tx, y + LIST_SUB_Y + LIST_SUB_H / 2 - SG_MARK_UP, GRID_VIEW_H);
            }
            {
                tile_t *t = sg_tile(r);
                if (sub && t->xw != pre) { /* the marks' room changed: the lines are cut again from the record */
                    t->xw = pre;
                    sg_prep(t, r), t->fit = 0;
                }
                grid_text(canvas, t, sub, tx + pre, y + (sub ? LIST_SUB_Y : LIST_TITLE_Y), room - pre,
                          sub ? LIST_SUB_H : LIST_TITLE_H, 0);
            }
        }
    }
    az_paint_heads(&sg.al, canvas); /* the section letters, then over everything the pinned band and its letter */
    if (sg.lift) sg_paint_float(canvas, tx, room);
}

/* A LIST_ART px mask of the Add Songs tile at (LIST_ART_X, y), cut at the view's edges. */
static void sg_add_blit(void *canvas, void *bmp, int y) {
    int top = y < 0 ? -y : 0, bottom = y + LIST_ART > GRID_VIEW_H ? GRID_VIEW_H - y : LIST_ART, src[4], dst[4];
    if (bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = LIST_ART, src[3] = bottom - top;
    dst[0] = LIST_ART_X, dst[1] = y + top, dst[2] = LIST_ART, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* An empty stock playlist (docs/modules/songs.md "Add Songs"): the header's mosaic, then where the first row would be the Add Songs row: the tile (a SG_ADD_TILE_RGB square, the grey notes,
 * the white badge) and "Add Songs" in the title style, centred on the row; no hairline. A press fills it as a row's. */
static void sg_paint_add(void *canvas) {
    int off = sg_off(), y = sg.al.top - off, rect[4];
    const unsigned *text = widget_get_text(sg.status);
    unsigned n = 0;
    grid_tile_t *h = grid_find(&sg.hg, 0);
    if (h) grid_blit(canvas, &sg.hg, h, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
    if (h && !sg.src) grid_plc_name(canvas, &sg.hg, h, sg.name, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
    sg_cbadge_paint(canvas, off);
    if (sg.add_down) az_fill(canvas, 0, y, y + ROW - 1, SG_W, LIST_PRESS);
    m1_capsule(canvas, GRID_VIEW_H, LIST_ART_X, y + LIST_ART_Y, LIST_ART, LIST_ART, LIST_R, SG_ADD_TILE_RGB);
    sg_add_blit(canvas, sg.add_note, y + LIST_ART_Y);
    sg_add_blit(canvas, sg.add_badge, y + LIST_ART_Y);
    while (text && text[n]) ++n;
    rect[0] = LIST_TEXT_X, rect[1] = y + (ROW - 1 - LIST_TITLE_H) / 2, rect[2] = SG_W - LIST_TEXT_X - SG_HDR_X,
    rect[3] = LIST_TITLE_H;
    widget_prepare_text_style(sg.st_title, canvas);
    if (n && rect[1] >= 0 && rect[1] + LIST_TITLE_H <= GRID_VIEW_H) canvas_draw_text_in_rect(canvas, text, n, rect);
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
    if (!canvas || !sg.view || !sg.g.tiles || (!sg.count && !sg.addrow)) return RET_OK;
    if (sg.addrow) { /* (no list to check: an empty playlist reads none) */
        I(canvas, CANVAS_OY) += off;
        sg_paint_add(canvas);
        I(canvas, CANVAS_OY) -= off;
        return RET_OK;
    }
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
        d = m1_abs(top + ROW / 2 - GRID_VIEW_H / 2);
        if (top >= GRID_VIEW_H || top + ROW <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int sg_on_load(const void *unused);
static void sg_cp_arm(void);

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

/* The cover of a tile: its own key's file, else the library album's (cc_cover_key); a tile with neither shows the placeholder. */
static void sg_art(tile_t *t) {
    char url[80];
    if (t->album - 1 >= (int)sg.count) {
        grid_art(&sg.g, t);
        return;
    }
    if (sg.src) { /* the source's cover file (1 there, 0 asked: look again shortly, -1 none) */
        int r;
        memcpy(url, "file://", 8); /* the file the source returns is its own (not the Cover Flow cache key's) */
        r = sg.src->cover(sg.src, deque_at(sg.list, (unsigned)(t->album - 1)), t->ckey, url + 7, sizeof url - 7);
        if (r > 0)
            grid_art_url(&sg.g, t, url);
        else {
            t->art = 2;
            if (r == 0) sg_cp_arm();
        }
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
    grid_dir(sg_off(), &sg.seen, &sg.dir);
    if (grid_moving(sg.sv)) { /* nothing is decoded while it moves: look again next tick */
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
        grid_tile_t *h = grid_find(&sg.hg, 0);
        plc_t c;
        if (h->cov && !sg.src && plc_get(sg.pl_id, sg.name, &c))
            grid_plc(&sg.hg, h, &c), h->cov = c.sig; /* the playlist's chosen cover, whole */
        else
            grid_mosaic(&sg.hg, h, sg.htmp);
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
    int on = sg.noscroll || sg.select || sg.pick || (sg.head && !sg.count && !sg.wait) ||
             m1_title_gone(sg_off(), sg.head ? PH_COLLAPSE + sg.tsh : 0);
    m1_title_set(sg.title, &sg.title_on, on);
    /* The navbar's fade (an insensitive image, built hidden) is for rows passing under the bar: shown while the list is scrolled, hidden at rest, where
     * it would darken the large title (as the Albums and Playlists pages). Never a touch target. No fade widget = nothing happens. */
    if (sg.fade) {
        grid_fade(sg.fade, sg_off() > 0);
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

/* A source's covers that were asked for and are not there yet: the tiles that showed the placeholder look again, and so does a playlist's header. */
static void sg_head_prep(void);
static void sg_cp_ask(void) {
    if (sg.view && sg.src) {
        sg_retry();
        if (sg.head && sg.hg.tiles) sg_head_prep(), sg_kick();
    }
}
static void sg_cp_arm(void) { ls_cover_poll(&sg.cp, sg.win, sg_cp_ask, (int (*)(void))0, (void (*)(void))0); }

static void sg_build_end(void) {
    m1_timer_stop(&sg.build_timer);
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
    if (!sg.src && sg.view && (sg.rv ? sg.rg.tiles : sg.g.tiles) && !sg.own &&
        !sg.build_timer) /* (a source makes its own covers: lib_src_t.cover) */
        sg.build_timer = timer_add(sg.rv ? rv_on_build_start : sg_on_build_start, (void *)0, SG_BUILD_START_MS);
}

/* The scroll_view's EVT_SCROLL (every change of its offset) and scroll end: the title, the direction, the loader and, when the page has gone far from where
 * the build looked, a new build. */
static int sg_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.view) return RET_OK;
    grid_dir(sg_off(), &sg.seen, &sg.dir);
    sg_title_update();
    sg_kick();
    if (!sg.rv && m1_abs(sg_first() - sg.build_at) > SG_BUILD_MOVE && !grid_moving(sg.sv)) sg_build_later();
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

static const char *sg_name_text(void) { return sg.key ? TR(sg.key) : sg.name; } /* a list's title */

/* The song count under the last row: "25 songs" (the key by n == 1, the number where the translation has its %d). */
static void sg_foot_text(void) {
    char buf[64];
    m1_fmt(buf, sizeof buf, TR(sg.count - (unsigned)sg.dlq == 1 ? "%d song" : "%d songs"),
           (int)sg.count - sg.dlq); /* (the downloads still to come are not songs of the list yet) */
    widget_set_text_utf8(sg.foot, buf);
    widget_move(sg.foot, SG_HDR_X, sg_rows_end() + SG_FOOT_GAP);
}

/* A playlist's header from the list just read: the tile's four album keys (the Playlists page's mosaic, patch/grid.c grid_mosaic_keys, from the first PL_SCAN songs and
 * the library's albums for the lookup), the tile made again only when they changed (a return to the front keeps the mosaic: no flicker), and the count. */
static void sg_head_prep(void) {
    unsigned key[4], cov = 0;
    int nk, fresh, i, same, miss = 0;
    grid_tile_t *t;
    plc_t c;
    if (!sg.head) return;
    if (!sg.src && plc_get(sg.pl_id, sg.name, &c))
        cov = c.sig; /* a chosen cover (a source's page never looks) replaces the mosaic */
    memset(key, 0, sizeof key);
    if (sg.src) {
        nk = sg.count ? sbs_mosaic_keys(sg.src, sg.list, key, &miss)
                      : 0; /* (a source's covers are its own files: the keys are theirs, grid_t.url) */
        if (miss) sg_cp_arm();
    } else
        nk = sg.count ? grid_mosaic_keys(sg.list, sg.albums, key, (int *)0) : 0;
    t = grid_tile(&sg.hg, 0, 0, 0, &fresh);
    if (sg_edit() && !fresh && t->art && t->cov == cov)
        return; /* Edit keeps the tile until Done (sg_select): no new mosaic per move, remove or add; a cover chosen there shows */
    for (i = 0, same = !fresh && t->nq == (nk > 1 && !sg.htmp ? 1 : nk) && t->art && t->cov == cov; i < 4; ++i)
        same = same && t->qkey[i] == key[i];
    if (!same) {
        grid_free_art(t);
        t->art = 0, t->qi = 0;
        t->nq = nk > 1 && !sg.htmp ? 1 : nk;
        t->cov = cov;
        memcpy(t->qkey, key, sizeof key);
        if (!nk && !cov) t->art = 2; /* no album with a cover: the placeholder */
    }
}

/* Where the rows start: under the pills (PH_TOP), PH_EDIT_UP higher where the pills are gone (Edit mode, the Add Songs row of an empty playlist). */
static void sg_top(void) {
    if (sg.head) sg.al.top = PH_TOP + sg.tsh - (sg_edit() || sg.addrow ? PH_EDIT_UP : 0);
}

/* Edit mode's grey pencil: 16 px, 8 px after the name's last line, centred on it; hidden outside Edit. */
#define SG_PENCIL 16
#define SG_PENCIL_GAP 8
static void sg_pencil(void) {
    int on = sg_edit() && sg.hpencil;
    if (!sg.hpencil) return;
    if (on) {
        void *last = sg.tsh ? sg.hname2 : sg.hname;
        const unsigned *t = widget_get_text(last);
        int w = t && *t ? m1_text_w(last, t) : 0, x;
        if (w > PH_NAME_W) w = PH_NAME_W;
        x = PH_NAME_X + (PH_NAME_W + w) / 2 + SG_PENCIL_GAP;
        if (x + SG_PENCIL > SG_W - 2) x = SG_W - 2 - SG_PENCIL;
        widget_move(sg.hpencil, x, PH_NAME_Y + sg.tsh + (PH_NAME_H - SG_PENCIL) / 2);
    }
    widget_set_visible(sg.hpencil, on, 0);
}

/* Edit mode's bottom bar: Delete | + over the list's Add | Delete (hidden and insensitive then). Delete is dim until a row is marked, + is always on. Runs after m1_sel_head, which sets the two stock pills. */
static void sg_bar_edit(void) {
    int on = sg_edit() && sg.edel && sg.eplus, any = sg.sel.nsel != 0;
    if (sg.edel) {
        m1_show(sg.edel, on);
        m1_show(sg.eplus, on);
    }
    if (!on) return;
    m1_show(sg.btn_add, 0);
    m1_show(sg.btn_del, 0);
    widget_set_prop_int(sg.edel, "enable", any);
    widget_set_sensitive(sg.edel, any);
}

static void sg_head(
    void) { /* the navbar's title: the select mode's (patch/selmode.c), else "Songs" or the list's name, cut to its room with an ellipsis */
    if (!sg.select) {
        if (sg.pick) { /* Add Songs: "Add to <the playlist>" */
            char t[0x140];
            wk_subst(t, sizeof t, TR("Add to %s"), sg.name);
            az_fit(sg.title, t);
            return;
        }
        az_fit(sg.title, sg_lib() ? TR("Songs") : sg_name_text());
        return;
    }
    m1_sel_head(&sg.sel);
    sg_bar_edit();
}

/* The rail's widget: centred on the list the select bar leaves (docs/modules/songs.md). */
static void sg_rail_fit(void) { az_rail_fit(&sg.al, GRID_VIEW_H - sg_pad()); }

/* The stock query again, and the page rebuilt from it: the index, the sections, the tiles. The library's albums are loaded first (once): both are stock queries
 * that replace *pdeq_showlist. */
static unsigned sg_sig(void *rec, unsigned key, unsigned rank) {
    const char *s[2];
    unsigned h = FNV_SEED ^ key, k;
    s[0] = sg_name(rec), s[1] = cc_str(rec, sg_artist_songs() ? REC_ALBUM : REC_ARTIST);
    h = (h ^ rank) * FNV_PRIME;
    for (k = 0; k < 2; ++k) {
        const unsigned char *p = (const unsigned char *)s[k];
        for (; *p; ++p) h = (h ^ *p) * FNV_PRIME;
        h = (h ^ 0x100) * FNV_PRIME; /* (the line's end: "ab","c" is not "a","bc") */
    }
    return h;
}

static int sg_on_gen(const void *unused);

/* The one loading spinner (patch/libsrc.c ls_spin): centred in the room under the large title (the rule of ls_room, in view_grid's coordinates: the spinner is its child, 50 px under the window's top), a playlist's where its Play pill will be (the header's Play pill and cover are hidden while its tracks are on their way). */
static void sg_spinner(int on) {
    if (!sg.spin) return;
    if (on && sg.head)
        widget_move(sg.spin, (SG_W - 14) / 2, PH_BTN_Y + sg.tsh + (AH_BTN_H - 14) / 2);
    else if (on)
        widget_move(sg.spin, (SG_W - 14) / 2, SG_TITLE_H + (450 - LS_ROOM_NAV - SG_TITLE_H - 14) / 2);
    ls_spin(sg.spin, on);
}

/* The Downloaded page of a source that lists its downloads still to come (lib_src_t.dl_rows). */
static int sg_dl(void) { return sg.src && sg.which == LS_DOWNLOADED && sg.src->dl_rows; }
/* The source's rows as last read are still the rows: gen_rows did not move, nor (the Downloaded page) the download rows. */
static int sg_rows_same(void) {
    return ls_gen_rows(sg.src) == sg.srows && (!sg_dl() || sg.src->dl_rows(sg.src, (int *)0) == sg.dlsig);
}
static const char *const sg_dl_heads[2] = {"Downloading", "Downloaded"};

static void sg_pills(void);
static void sg_load(int keep) {
    unsigned i;
    int at = keep ? sg_off() : 0, same = 0, st = LS_ST_READY;
    void *list = (void *)0;
    song_t *old = sg.idx;
    unsigned old_n = sg.count;
    void *old_list =
        sg.src ? sg.list : (void *)0; /* a source's list is ours: destroyed once the new one has replaced it */
    if (sg_lib())
        free(old),
            old =
                (song_t
                     *)0; /* (the library is big: its old index is not held beside the new one, and it is read again only when it changed) */
    m1_timer_stop(&sg.more_timer);
    sg_lift_end(0);
    sg_build_end();
    rowmenu_close(&sg.rm); /* (a menu's row is an index of the list that is read again) */
    sg.idx = (song_t *)0, sg.list = sg.first = (void *)0, sg.count = 0, m1_sel_reset(&sg.sel, 0), sg.al.count = 0,
    sg.al.nsec = 0, sg.press = sg.down = 0, sg.wait = 0;
    if (!sg.albums_tried && !sg.src) {
        sg.albums_tried = 1;
        sg.albums = cc_albums();
    }
    sg.sort = sg_lib() ? *(int *)SORT_FLAG : 0; /* (a list has the order of its query: sort_flag is the library's) */
    if (sg.sort < 0 || sg.sort > 4) sg.sort = 0;
    if (sg.src) { /* gen and completeness are read before the list: a list read after "complete" is the whole one */
        sg.sgen = sg.src->gen(sg.src);
        sg.srows = ls_gen_rows(sg.src);
        if (sg_dl()) sg.dlsig = sg.src->dl_rows(sg.src, (int *)0);
        sg.part = !sg.scope_d && sg.src->complete &&
                  !sg.src->complete(sg.src,
                                    sg.which); /* (a scoped list is read whole; the paging is of the unscoped Songs) */
        list = sg.src->list(sg.src, sg.which, sg.scope_d ? deque_at(sg.scope_d, 0) : (void *)0);
    } else if (sg_query() > 0)
        list = *(void **)PDEQ_SHOWLIST;
    if (list && sg_flipped()) sg_reverse(list);
    if (list) sg.count = deque_size(list);
    sg.dlq = 0, sg.al.sec_text = (const char *const *)0, sg.al.sec_act = (const char *)0;
    if (sg_dl()) {
        az_prefs(&sg.al); /* (the last read may have had the section: the switches' own values again) */
        if (list) sg.src->dl_rows(sg.src, &sg.dlq);
        if (sg.dlq < 0 || sg.dlq > (int)sg.count) sg.dlq = 0;
    }
    if (sg.src && !list && sg.src->state)
        st = sg.src->state(sg.src, sg.which, sg.scope_d ? deque_at(sg.scope_d, 0) : (void *)0);
    sg.wait = st == LS_ST_LOADING;
    if (sg.src) sg_pills(); /* (the pills come with the rows) */
    if (sg.count) {
        sg.idx = calloc(sg.count, sizeof(song_t));
        if (!sg.idx || !m1_sel_reset(&sg.sel, sg.count)) {
            free(sg.idx);
            m1_sel_reset(&sg.sel, 0);
            sg.idx = (song_t *)0, sg.count = 0;
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
        if ((sg_lib() && sg.sort == 0) || sg_ranked()) {
            az_sections(&sg.al, &sg.idx[0].letter, sizeof(song_t));
            if (sg_flipped()) /* the headers and the rail show the letters of the mirrored ranks: rank 0 is Z, 25 is A, 26 is "#" */
                az_flip_letters(&sg.al);
        }
        if (sg.dlq) { /* the downloads still to come are a section of their own with a Clear, the finished ones the second: named headers whatever the Section Headers switch says, no rail */
            sg.al.nsec = sg.dlq < (int)sg.count ? 2 : 1;
            sg.al.sec_start[0] = 0, sg.al.sec_start[1] = (unsigned)sg.dlq;
            sg.al.sec_text = sg_dl_heads, sg.al.sec_act = "Clear", sg.al.st_act = sg.st_sub;
            sg.al.hdr_h = SG_HDR_H, sg.al.norail = 1;
        }
    }
    /* The same rows as before (count and every sig; the tiles hold their texts and covers by row): the tiles and the placeholder stay, so a list read again
     * does not flash its covers away. Anything else, or a doubt, drops them. A cover that was not there (art 2) is looked for again. */
    if (old && old_n && (sg.src ? old_n <= sg.count : old_n == sg.count) && sg.g.tiles &&
        sg.g.placeholder) { /* (a source's list that grew keeps the tiles of its first rows) */
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
    sg.addrow = sg.head && !sg.count && !sg.wait && !list && sg.add_note && sg.add_badge && sg_cleans();
    sg_top();
    if (sg.head) sg_pills(); /* (the Add Songs row has none) */
    m1_show(
        sg.view,
        sg.count != 0 || sg.wait || !sg.head ||
            sg.addrow); /* (a list still loading, or an empty one without a header: the title block, the spinner or the status line under it) */
    if (!sg.head) ls_room(sg.status, (void *)0, LS_ROOM_NAV + SG_TITLE_H);
    m1_show(sg.status, sg.count == 0 && !(sg.wait && sg.spin) && !sg.addrow);
    if (sg.foot)
        widget_set_visible(sg.foot, !sg.rv && !sg.wait && !sg.part && !sg.addrow,
                           0); /* (no count while a paged list is still growing) */
    if (!sg.count) /* (the hidden label holds the Add Songs row's text: sg_paint_add draws it) */
        widget_set_tr_text(sg.status, sg.addrow  ? "Add Songs"
                                      : list     ? "Not enough memory"
                                      : sg_lib() ? "Update Library first"
                                                 : ls_empty_key(st, "No songs"));
    sg_spinner(sg.wait && sg.spin);
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
    if (sg.src) {
        if (old_list && old_list != sg.list) deque_destroy(old_list);
        if (list && list != sg.list) deque_destroy(list); /* (an empty list, or no memory for its index) */
        if (!sg.gen_timer) sg.gen_timer = timer_add(sg_on_gen, (void *)0, LS_GEN_MS);
    }
}

/* The source's gen moved (rows came, a download changed): read the list again where it does not disturb the user (select mode, the card, a finger on the list) and the page is on top.
 * The scroll position is kept (sg_load(1)). */
static int sg_on_gen(const void *unused) {
    (void)unused;
    sg.gen_timer = 0;
    if (!sg.src || !sg.view) return RET_OK;
    if (sg.src->gen(sg.src) != sg.sgen && !sg.select && !sg.menu && !sg.down && !grid_moving(sg.sv) &&
        m1_is_top(sg.win)) {
        if (sg_rows_same()) { /* only a download's progress moved: the rows are the same, the visible ones are painted again (their state is read while painting) */
            sg.sgen = sg.src->gen(sg.src);
            sg_redraw();
        } else if (sg.rm.open)
            sg_redraw(); /* (the row menu stays: progress only redraws the rows' ring, the list is read once the menu has closed) */
        else
            sg_load(1); /* (re-arms the timer) */
    }
    if (!sg.gen_timer) sg.gen_timer = timer_add(sg_on_gen, (void *)0, LS_GEN_MS);
    return RET_OK;
}

/* Another query replaced the stock list under a page that is on top (a paint found it): read it again. A page behind another reads it when it comes back. */
static int sg_on_stale(const void *unused) {
    (void)unused;
    sg.stale_timer = 0;
    if (sg.view && !sg.rv && sg.g.tiles && !sg_valid() && m1_is_top(sg.win)) sg_load(1);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Recently Added's toggle between the songs and the albums (docs/modules/recent-albums.md)
 */

/* The Play / Shuffle buttons: the library's two flat pills, or a playlist's header disc and pill (album page style); the set not in use is hidden AND insensitive, the
 * albums view (rv) has neither, and in select mode the shown ones stay in the content, dead. */
static void sg_pills(void) {
    int lib = !sg.rv && !sg.head && !sg.wait && !sg.pick, /* (the Add Songs page has no pills) */
        hd = !sg.rv && sg.head && !sg.wait; /* (a source's rows still on their way: neither set) */
    widget_set_visible(sg.btn_play, lib, 0);
    widget_set_visible(sg.btn_shuffle, lib, 0);
    widget_set_sensitive(sg.btn_play, lib && !sg.select);
    widget_set_sensitive(sg.btn_shuffle, lib && !sg.select);
    hd = hd && !sg_edit() &&
         !sg.addrow; /* (Edit mode and the Add Songs row: hidden and insensitive, the rows take their band) */
    widget_set_visible(sg.hd_play, hd, 0);
    widget_set_visible(sg.hd_shuffle, hd, 0);
    widget_set_sensitive(sg.hd_play, hd && !sg.select);
    widget_set_sensitive(sg.hd_shuffle, hd && !sg.select);
    widget_set_visible(sg.pill.glyph, hd, 0); /* (an insensitive image: taps reach hd_play) */
}

/* The widgets of the view: the albums have no Play / Shuffle pills, no song count and no Select (the card's Select row goes, Albums ticked then). */
static void rv_ui(void) {
    sg_pills();
    if (sg.foot)
        widget_set_visible(sg.foot, !sg.rv && !sg.part, 0); /* (an insensitive label: shown, never a touch target) */
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
    m1_timer_stop(&sg.more_timer);
    sg_build_end();
    if (!rv_load()) {
        grid_free(&sg.rg);
        return 0;
    }
    sg.rv = 1, sg.press = sg.down = 0, sg.dir = 1;
    rv_ui();
    m1_show(sg.view, sg.rn != 0);
    m1_show(sg.status, sg.rn == 0);
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
    m1_timer_stop(&sg.more_timer);
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
    home_write_atomic(RECENTADD_VIEW_FILE, sg.rv ? "1\n" : "0\n");
}

/* ---------------------------------------------------------------------------
 * Playing: the stock Songs row's handler (@0x5275a4: loadSongList of the shown list, then Now Playing at the row), as Shuffle Songs does it (patch/shuffle.c)
 */
/* Song `at` (-1: a random one) of the list and the list as the queue, in Now Playing (patch/songops.c). */
static void sg_play_at(int at, int how) {
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    if (sg.src) { /* the source plays its own records (a DSD row that is not downloaded, -2, asks "Download to Play?") */
        if (so_play_src(sg.src, sg.cls, sg.list, at, how, pod_start_player) == -2) ls_dsd_confirm(sg.src, sg.list, at);
        return;
    }
    sg_classinfo(); /* loadSongList runs the class query again and keeps classinfo for the memory playback */
    if (sg.split ||
        sg.gsplit) { /* a split's songs are the queue as they are (patch/songops.c so_play_own); the stock genre query on a split name finds nothing */
        so_play_own(sg.list, at, how, pod_start_player);
        return;
    }
    so_play_dir(sg.cls, sg.list, at, how, pod_start_player, sg_flipped());
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
    sg_lift_end(0);
    sg.select = on;
    sg.press = sg.down = 0;
    nav[0] = sg.btn_more, nav[1] = sg.np;
    for (i = 0; i < 2; ++i) m1_show(nav[i], !on);
    if (sg.btn_cf) m1_show(sg.btn_cf, !on && sg_artist());
    if (sg.btn_search) m1_show(sg.btn_search, !on && sg_searches());
    sg_pills(); /* the pills stay in the content, dim and dead (the library's) or dead (a playlist's) */
    m1_sel_enter(&sg.sel, on, sg_title_end());
    if (sg_edit()) grid_icons(sg.back, "ah_nav_done", "ah_nav_done_down"); /* the check: Done */
    if (!on && sg.head && sg.hg.tiles && sg_valid())
        sg_head_prep(), sg_kick(); /* Done: the mosaic from the first albums now, if they changed */
    if (!on && sg.edel) { /* the stock bar's Add and Delete again, Edit's pair away */
        m1_show(sg.edel, 0);
        m1_show(sg.eplus, 0);
        m1_show(sg.btn_add, 1);
        m1_show(sg.btn_del, 1);
    }
    sg_top();
    sg_pencil();
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
    if (m1_sel_toggle(&sg.sel, i)) sg_count_changed();
}

static int sg_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg.select || !sg.sel.bits) return RET_OK;
    m1_sel_toggle_all(&sg.sel);
    sg_count_changed();
    return RET_OK;
}

/* The class Delete and Add pass to the stock code: the list's own, but a genre split's list is real songs of several tags, so it goes the generic songtable path (0xf001) that works from each
 * selected record, never a path keyed on the split name (patch/genresplit.c). */
static int sg_op_cls(void) { return sg.gsplit ? CLASS_ALL_SONGS : sg.cls; }

/* Remove from Playlist, a stock playlist's select mode trash (docs/modules/playlists.md "Remove from Playlist"): the stock delete (so_delete) would take each song out of every playlist that holds it
 * and offers to delete the file, so this playlist's marked rows leave by their own row ids instead (so_remove_ids), after a confirm. The ids are taken before the dialog (it is modal: the page may
 * read its list again under it); no file is ever deleted from here. */
static int sg_remove_marked(void) {
    char buf[200];
    unsigned n = sg.sel.nsel, done = 0;
    int *ids, yes;
    if (!n) {
        pod_toast(TR("msg_delsongfailed"));
        return 0;
    }
    if (!sg_valid()) return 1; /* (another page's query replaced the list: the marks are of rows no longer shown) */
    ids = so_marked_ids(sg.list, sg.count, sg.sel.bits, n);
    if (!ids) return 0;
    m1_fmt(buf, sizeof buf, TR(n == 1 ? "Remove %d song from this playlist?" : "Remove %d songs from this playlist?"),
           (int)n);
    yes = pod_confirm(buf);
    if (yes) done = so_remove_ids(ids, n);
    free(ids);
    if (!yes) return 0;
    pod_toast(TR(done ? "Removed from Playlist" : "Can't remove from playlist"));
    return 1;
}

/* Delete and Add run the stock code on the stock selection vector (patch/songops.c), filled from the page's marks at that moment. */
static int sg_on_delete(void *ctx, void *e) {
    int edit = sg_edit();
    (void)ctx;
    (void)e;
    if (!sg.select || sg.src) return RET_OK; /* (a source's tracks are not deleted from here) */
    if (sg_cleans() ? sg_remove_marked()
                    : so_delete(sg_op_cls(), sg.list, sg.count, sg.sel.bits, sg.sel.nsel, sg_valid())) {
        if (edit) { /* a playlist's Edit mode stays: the list read again, no marks (an empty playlist is still there, and + still works) */
            sg_load(1);
            return RET_OK;
        }
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
    if (!sg.select || sg.src) return RET_OK; /* (a source's sheet has no Add to Playlist) */
    r = so_add(sg_op_cls(), sg.count, sg.sel.bits, sg.sel.nsel, sg_valid(), sg.title_save, &sg.picker);
    if (r < 0) {
        sg_select(0);
        sg_load(1);
    }
    return RET_OK;
}

static int sg_open_page(int cls, int pl_id, const char *key, const char *name, const lib_src_t *src, int which,
                        void *scope);
static void sg_edit_reload(void);
static unsigned *sg_pick_h __attribute__((
    section(".scratch"))); /* sg_add_songs: the playlist's songs for the page about to open (it takes them) */
static unsigned sg_pick_n __attribute__((section(".scratch")));
static int sg_pick_id __attribute__((section(".scratch"))), sg_pick_next __attribute__((section(".scratch")));

/* Edit mode's +: the Add Songs page (the library, sg.pick) over this one. The playlist's songs are collected first (by path); the page below is read again when it comes back (sg.reread). A page that
 * is already over another (a playlist reached through Search) opens nothing. */
static void sg_add_songs(void) {
    char nm[sizeof sg.name];
    unsigned i, n;
    unsigned *h;
    if (!sg.view || sg_under) return;
    if (sg.count && !sg_valid()) sg_edit_reload();
    n = sg.list ? sg.count : 0;
    h = calloc(2 * (n + 1), sizeof *h);
    if (!h) return;
    for (i = 0; i < n; ++i) so_song_key(deque_at(sg.list, i), &h[2 * i]);
    memcpy(nm, sg.name, sizeof nm);
    sg_pick_h = h, sg_pick_n = n, sg_pick_id = sg.pl_id, sg_pick_next = 1;
    if (sg_open_page(CLASS_ALL_SONGS, 0, (const char *)0, nm, (const lib_src_t *)0, 0, (void *)0) == -1 || sg_pick_next)
        free(sg_pick_h), sg_pick_h = (unsigned *)0,
                         sg_pick_next = 0; /* (a page that did not open: the page below is as it was) */
}

/* A tap on row a of the Add Songs page: the song goes to the end of the playlist at once, as the stock picker adds it (so_add_row), and its mark turns to the tick; a song already in it does
 * nothing. A list another page replaced is read again first. */
static void sg_pick_tap(int a) {
    unsigned h[2], *g;
    void *rec;
    if (a < 0 || a >= (int)sg.count) return;
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    rec = deque_at(sg.list, (unsigned)a);
    if (sg_pk_has(rec)) return;
    if (!so_add_row(CLASS_ALL_SONGS, sg.list, sg.count, (unsigned)a, sg.pk_id)) {
        pod_toast(TR("msg_addfailed"));
        return;
    }
    so_song_key(rec, h);
    g = calloc(2 * (sg.pk_n + 1), sizeof *g);
    if (g) {
        memcpy(g, sg.pk_h, 2 * sg.pk_n * sizeof *g);
        g[2 * sg.pk_n] = h[0], g[2 * sg.pk_n + 1] = h[1];
        free(sg.pk_h);
        sg.pk_h = g, ++sg.pk_n;
    }
    pod_toast(TR("msg_addplaylistsuccess"));
    sg_redraw();
}

static int sg_on_eplus(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg_edit()) sg_add_songs();
    return RET_OK;
}

/* An artist's songs and Cover Flow's artist page are two views of the artist (a toggle: the Cover Flow button here, the list button there), so Back from this one
 * leaves the artist, not just the list: this page closes and, when the artist's covers page is what is under it, that closes too (two navigator_backs, no loop;
 * these pages have no close animation, so each takes effect at once). The Cover Flow button closes only this page. */

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
    grid_ev_local(sg.view, e, pt);
    return sg_at(pt[1]);
}

/* The press or release is in a row's "..." zone. */
static int sg_in_zone(void *e) {
    int pt[2], x0;
    if (!sg_more()) return 0;
    grid_ev_local(sg.view, e, pt);
    x0 = rowmenu_zone_x(sg_more_right());
    return pt[0] >= x0 && pt[0] < x0 + RM_MORE_W;
}

/* Add to Playlist for one row (the menu's third row): the page's picker with a selection of that row alone. */
static void sg_add_one(int row) {
    int r;
    if (!sg.sel.bits || row < 0 || row >= (int)sg.count || sg.src) return;
    sg.sel.bits[row >> 3] |= (unsigned char)(1 << (row & 7));
    r = so_add(sg_op_cls(), sg.count, sg.sel.bits, 1, sg_valid(), sg.title_save, &sg.picker);
    memset(sg.sel.bits, 0, (sg.count + 7) / 8); /* (the picker and the stock vector have their own copies) */
    if (r < 0) sg_load(1);
}

/* Remove from Playlist for one row (the sheet's last row on a stock playlist): the row leaves by the row id of the menu's copy (so a list read again under the sheet cannot point it at another
 * row; a copy of another playlist's row is refused), no dialog, then the toast and the list read again with its scroll offset. */
static void sg_remove_one(void *rec) {
    int id = I(rec, REC_ID);
    unsigned done;
    if (!sg_cleans() || !sg.view || I(rec, REC_DISC) != sg.pl_id) return;
    done = so_remove_ids(&id, 1);
    pod_toast(TR(done ? "Removed from Playlist" : "Can't remove from playlist"));
    if (done) sg_load(1);
}

static void sg_open_menu(int a) {
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    if (sg.src && I(deque_at(sg.list, (unsigned)a), REC_TYPE) != 8)
        return; /* (a source's list may hold other rows: only a track has a sheet) */
    rowmenu_open_src(&sg.rm, a, deque_at(sg.list, (unsigned)a), sg_add_one, sg.src);
}

/* The press or release is on the Downloading header's Clear (patch/azlist.c az_act_hit). */
static int sg_on_act(void *e) {
    int pt[2];
    if (!sg.dlq) return 0;
    grid_ev_local(sg.view, e, pt);
    return az_act_hit(&sg.al, pt[0], pt[1]);
}

/* A press held RM_LONG_MS on a row: its menu opens while the finger is still down; the press is forgotten, so the release does nothing. */
static void sg_on_hold(int row) {
    sg.down = sg.down_more = sg.down_act = 0;
    grid_set_press(&sg.press, 0, sg.sv);
    if (sg.view && !sg.select && !sg.rv && (unsigned)row < sg.count) sg_open_menu(row);
}

/* The album grid's long press sheet (the Albums page's, docs/modules/pins.md) on the track sheet's widgets (rowmenu_open_album): a row of it (the sheet has closed) for album a. */
static void rv_sheet(int a, int act) {
    void *rec = sg.rv && (unsigned)a < sg.rn ? rv_rec(a) : (void *)0;
    const char *name, *path;
    unsigned ckey;
    if (!rec) return;
    name = cc_str(rec, REC_ALBUM), path = cc_str(rec, REC_PATH), ckey = cc_album_key(rec);
    pins_album_act(name, ckey, path, act);
}

/* A press held RM_LONG_MS on an album of the grid: the sheet opens while the finger is down; the press is forgotten, so the release opens nothing. */
static void rv_on_hold(int a) {
    sg.down = 0;
    if (!sg.view || !sg.rv || (unsigned)a >= sg.rn) return;
    rowmenu_open_album(&sg.rm, a, pins_has_album(cc_str(rv_rec(a), REC_ALBUM)), rv_sheet);
}

/* ---------------------------------------------------------------------------
 * Edit mode's reorder (docs/modules/songs.md "Reorder"): a press in a row's handle zone lifts the row at once; it follows the finger, the others close up around its slot (sg_vrow), a finger near the
 * list's top or the select bar scrolls the list on a timer; the release writes the new order (so_reorder_rows) when the slot changed.
 */
static void sg_edit_reload(void);

static int sg_in_handle(void *e) {
    int pt[2];
    if (!sg_handles() || !e) return 0;
    grid_ev_local(sg.view, e, pt);
    return pt[0] >= SG_HANDLE_X && pt[0] < SG_HANDLE_X + SG_HANDLE_W;
}

/* The slot the lifted row's middle is over (clamped to the list). */
static void sg_lift_slot(void) {
    int s = sg.lfy - sg.lgrab + sg_off() + ROW / 2 - sg.al.top;
    s = s < 0 ? 0 : s / ROW;
    if (s > (int)sg.count - 1) s = (int)sg.count - 1;
    sg.lslot = s;
}

/* Which way the finger asks the list to scroll: -1 near the top, 1 near the select bar, 0 else; and where one tick takes the list (the offset when it is at an end). */
static int sg_edge_dir(void) { return sg.lfy < SG_EDGE ? -1 : sg.lfy >= GRID_VIEW_H - SG_BAR_H - SG_EDGE ? 1 : 0; }
static int sg_edge_to(int d) {
    int to = sg_off() + d * SG_EDGE_STEP;
    return to < 0 ? 0 : to > sg_max_scroll() ? sg_max_scroll() : to;
}

static int sg_on_edge(const void *unused) {
    int d = sg.lift ? sg_edge_dir() : 0, to = sg_edge_to(d);
    (void)unused;
    if (!d ||
        to ==
            sg_off()) { /* not near an edge or at the end of the list: the timer ends (a move near the edge starts it again) */
        sg.edge_timer = 0;
        return RET_OK;
    }
    widget_set_prop_int(sg.sv, "yoffset", to);
    sg_lift_slot();
    sg_redraw();
    return RET_REPEAT;
}

static void sg_edge_arm(void) {
    int d = sg_edge_dir();
    if (sg.edge_timer || !sg.lift || !d || sg_edge_to(d) == sg_off()) return;
    sg.edge_timer = timer_add(sg_on_edge, (void *)0, SG_EDGE_MS);
}

/* The press on row a's handle: the row lifts (drawn at the finger, its slot empty), the touch is grabbed at the list and the list's sliding goes off (m1_lift_sv keeps it off, patch/scroll.c). */
static void sg_lift_start(int a, void *e) {
    int pt[2];
    grid_ev_local(sg.view, e, pt);
    sg.lift = a + 1, sg.lslot = a, sg.lgrab = pt[1] - sg_row_y(a), sg.lfy = pt[1] - sg_off();
    sg.lslide = widget_get_prop_int(sg.sv, "yslidable", 1);
    widget_set_prop_int(sg.sv, "yslidable", 0);
    m1_lift_sv = sg.sv;
    widget_grab(sg.sv,
                sg.view); /* (stock refuses it when the list has another grab: the sliding is off all the same) */
    sg_redraw();
}

static void sg_lift_follow(void *e) {
    int pt[2];
    grid_ev_local(sg.view, e, pt);
    sg.lfy = pt[1] - sg_off();
    sg_lift_slot();
    sg_redraw();
}

/* The marks follow the moved row: its bit goes from `from` to `to`, the rows between shift by one. */
static void sg_move_marks(int from, int to) {
    unsigned char *b = sg.sel.bits;
    int i, step = to > from ? 1 : -1, keep;
    if (!b) return;
#define SG_BIT(i) ((b[(i) >> 3] >> ((i) & 7)) & 1)
#define SG_SETBIT(i, v) (b[(i) >> 3] = (unsigned char)((b[(i) >> 3] & ~(1 << ((i) & 7))) | ((v) << ((i) & 7))))
    keep = SG_BIT(from);
    for (i = from; i != to; i += step) SG_SETBIT(i, SG_BIT(i + step));
    SG_SETBIT(to, keep);
#undef SG_BIT
#undef SG_SETBIT
}

/* Row `from` dropped on slot `to`: the rows of that range take their ids in the new order (so_reorder_rows), then the list is read again with Edit mode, its marks (moved with the row) and its place. A write that
 * did not run says so and changes nothing: the list in memory is as it was, so the row is back where it was. */
static void sg_reorder(int from, int to) {
    int lo = from < to ? from : to, hi = from < to ? to : from, i, ok = 0;
    unsigned n = (unsigned)(hi - lo + 1);
    int *ids;
    if (!sg_valid()) { /* (another page's query replaced the list: it is read again, nothing is written) */
        sg_edit_reload();
        return;
    }
    ids = calloc(n, sizeof *ids);
    if (ids) {
        ok = 1;
        for (i = lo; i <= hi; ++i) {
            void *rec = deque_at(sg.list, (unsigned)i);
            ids[i - lo] = I(rec, REC_ID);
            if (I(rec, REC_DISC) != sg.pl_id) ok = 0;
        }
        ok = ok && so_reorder_rows(sg.pl_id, ids, n, (unsigned)(from - lo), (unsigned)(to - lo));
        free(ids);
    }
    if (!ok) {
        pod_toast(TR("Can't reorder playlist"));
        return;
    }
    sg_move_marks(from, to);
    sg_edit_reload();
}

/* The release of a lift: the slot under it (the release's own point when it has one), the lift over, then the move. */
static void sg_lift_drop(void *e) {
    int from = sg.lift - 1, to;
    if (e && sg.view) sg_lift_follow(e);
    to = sg.lslot;
    sg_lift_end(1);
    if (to != from) sg_reorder(from, to);
}

static int sg_on_move(void *ctx, void *e) {
    (void)ctx;
    if (sg.lift && e) {
        sg_lift_follow(e);
        sg_edge_arm();
    } else if (sg.down && e)
        rowmenu_hold_move(&sg.tap, e);
    return RET_OK;
}

static void sg_rename(void);

/* Edit mode: the press or release is on the header's cover (a local playlist's: the Cover page). */
static int sg_in_cover(void *e) {
    int pt[2];
    if (!sg_edit() || !e || !sg.view) return 0;
    grid_ev_local(sg.view, e, pt);
    return pt[0] >= PH_COVER_X && pt[0] < PH_COVER_X + PH_COVER && pt[1] >= PH_COVER_Y && pt[1] < PH_COVER_Y + PH_COVER;
}

/* Opens the Cover page for this playlist (Edit mode): its id, name and the albums' cover keys (the header's); this page makes its header again when it is back in front (sg_on_fg). */
static void sg_cover(void) {
    unsigned key[4];
    int nk;
    if (!sg_edit() || !sg.view) return;
    memset(key, 0, sizeof key);
    nk = sg.count ? grid_mosaic_keys(sg.list, sg.albums, key, (int *)0) : 0;
    sg.cover_due = 1;
    if (plcpage_open(sg.pl_id, sg.name, key, nk) < 0) sg.cover_due = 0;
}

/* Edit mode: the press or release is on the header's name (its lines' band, the full width). */
static int sg_in_name(void *e) {
    int pt[2];
    if (!sg_edit() || !e) return 0;
    grid_ev_local(sg.view, e, pt);
    return pt[1] >= PH_NAME_Y - 4 && pt[1] < PH_NAME_Y + sg.tsh + PH_NAME_H + 4;
}

/* The press or release is on the Add Songs row (the full width). */
static int sg_in_add(void *e) {
    int pt[2];
    if (!sg.addrow || !e || !sg.view) return 0;
    grid_ev_local(sg.view, e, pt);
    return pt[1] >= sg.al.top && pt[1] < sg.al.top + ROW;
}

static int sg_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    sg.down = sg.down_more = 0;
    sg.down_name = sg_in_name(e);
    sg.down_cover = sg_in_cover(e);
    if (sg.down_name || sg.down_cover) m1_tap_at(&sg.tap, e);
    if (sg_in_add(e)) {
        sg.add_down = 1, m1_tap_at(&sg.tap, e);
        sg_redraw();
        return RET_OK;
    }
    if (sg.rv) { /* the album grid: no press fill */
        int pt[2];
        if (!e || !sg.view) return RET_OK;
        grid_ev_local(sg.view, e, pt);
        sg.down = rv_cell_at(pt[0], pt[1]) + 1, m1_tap_at(&sg.tap, e);
        if (sg.down > 0 && (unsigned)(sg.down - 1) < sg.rn && rowmenu_on(&sg.rm))
            rowmenu_hold_start(sg.down - 1, rv_on_hold);
        return RET_OK;
    }
    if (!e || !sg.view || !sg.count || !sg_valid()) return RET_OK;
    a = sg_item_of(e);
    sg.down_act = !sg.select && sg_on_act(e);
    if (sg.down_act) a = -1; /* (the pinned header lies over a row: the press is the button's) */
    if (a >= 0 && sg_in_handle(e)) { /* Edit mode: the handle lifts the row at once */
        sg_lift_start(a, e);
        return RET_OK;
    }
    sg.down = a + 1, m1_tap_at(&sg.tap, e);
    sg.down_more = a >= 0 && sg_in_zone(e);
    if (!sg.select && !sg.down_more) grid_set_press(&sg.press, a + 1, sg.sv);
    if (a >= 0 && !sg.select && sg_more()) rowmenu_hold_start(a, sg_on_hold);
    return RET_OK;
}

static int sg_on_up(void *ctx, void *e) {
    int a = sg.down - 1, more = sg.down_more, act = sg.down_act, name = sg.down_name, cover = sg.down_cover;
    (void)ctx;
    sg.down_name = sg.down_cover = 0;
    if (sg.lift) {
        sg.down = sg.down_more = sg.down_act = 0;
        sg_lift_drop(e);
        return RET_OK;
    }
    if (name && e && sg.view && m1_tap_near(&sg.tap, e) && sg_in_name(e)) { /* Edit mode: a tap on the name renames */
        sg.down = sg.down_more = sg.down_act = 0;
        sg_rename();
        return RET_OK;
    }
    if (cover && e && sg.view && m1_tap_near(&sg.tap, e) &&
        sg_in_cover(e)) { /* Edit mode: a tap on the cover opens the Cover page */
        sg.down = sg.down_more = sg.down_act = 0;
        sg_cover();
        return RET_OK;
    }
    if (sg.add_down) { /* the Add Songs row: a tap opens the Add Songs page */
        sg.add_down = 0;
        sg_redraw();
        if (e && m1_tap_near(&sg.tap, e) && sg_in_add(e)) sg_add_songs();
        return RET_OK;
    }
    rowmenu_hold_stop();
    sg.down = sg.down_more = sg.down_act = 0;
    grid_set_press(&sg.press, 0, sg.sv);
    if (act && e && sg.view && sg.dlq && m1_tap_near(&sg.tap, e) &&
        sg_on_act(e)) { /* Clear: every download still to come leaves the queue; the finished ones stay */
        sg.src->act(sg.src, (void *)0, LS_ACT_CANCEL_ALL_DL);
        sg_load(1);
        return RET_OK;
    }
    if (a < 0 || !e || !sg.view) return RET_OK;
    if (sg.rv) { /* an album: our album page, as the Albums page's tap opens it (cc_open_album takes the stock row) */
        int pt[2];
        grid_ev_local(sg.view, e, pt);
        if (m1_tap_near(&sg.tap, e) && rv_cell_at(pt[0], pt[1]) == a && (unsigned)a < sg.rn)
            cc_open_album((void *)0, 0, (int)sg.rrow[a]);
        return RET_OK;
    }
    if (m1_tap_near(&sg.tap, e) && sg_item_of(e) == a) {
        if (sg.pick)
            sg_pick_tap(a);
        else if (sg.select)
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
    rowmenu_hold_stop();
    sg.down = sg.down_more = sg.down_act = sg.down_name = 0;
    if (sg.add_down) sg.add_down = 0, sg_redraw();
    sg_lift_end(1); /* (an abort puts the row back: nothing is written) */
    grid_set_press(&sg.press, 0, sg.sv);
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
/* A playlist's Pin Playlist / Unpin Playlist row (slot 9, docs/modules/pins.md): its words and glyph follow the pin, set before the card is fitted. */
static void sg_pin_row(void) {
    int pinned = pins_has_playlist(sg.pl_id, sg.name);
    if (sg.vs.label[VS_ACT3]) widget_set_tr_text(sg.vs.label[VS_ACT3], pins_label_playlist(sg.pl_id, sg.name));
    if (sg.vs.glyph[VS_ACT3 - VS_SORTS])
        widget_set_prop_str(sg.vs.glyph[VS_ACT3 - VS_SORTS], "image", pinned ? "pod_ic_vsunpin" : "pod_ic_vspin");
}

/* A playlist's first row is Edit: the Select row with the pencil glyph (set before the card is fitted). */
static void sg_edit_row(void) {
    if (sg.vs.label[VS_SELECT]) widget_set_tr_text(sg.vs.label[VS_SELECT], "Edit");
    if (sg.vs.glyph[VS_SELECT - VS_SORTS])
        widget_set_prop_str(sg.vs.glyph[VS_SELECT - VS_SORTS], "image", "pod_ic_vsrename");
}

static void sg_menu(int on) {
    sg.menu = on;
    if (on && sg_cleans()) sg_edit_row(), sg_pin_row();
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

/* Clean Up Playlist (the card's row on a playlist; docs/modules/playlists.md "Clean Up Playlist"). Stock Update Library never touches the playlist table, so a song
 * whose file left the card (deleted, or moved to another folder) stays in the playlist with its old path. The row checks this playlist's songs against the card
 * (sg_gone: so_gone_mark, only paths under /mnt/mmc/). First the repair, unasked (so_relink: nothing is lost by it): a missing row whose song is in the library
 * under another path gets that path, and the list is read again. Then, for the rows still missing, a confirm and the removal (so_clean: this playlist's rows by their
 * own ids, never a file, never another playlist). Guards, nothing written: no card (/tmp/mmc_add, the stock "No TF Card Found"); a card that is in but not mounted
 * (m1_card_mounted: every path would look missing); nothing missing. The page's select bitset holds the marks (the page is not in select mode) and is cleared again;
 * the rows are marked again after the dialog (it is modal: the page may have read its list again under it) and only those that were asked about (their row ids,
 * so_marked_ids / so_keep_ids) and are still missing are removed: a file that went under the dialog is left for the next clean-up. */
static unsigned sg_gone(void) {
    unsigned checked;
    return sg.count && sg.sel.bits && sg_valid() ? so_gone_mark(sg.list, sg.count, sg.sel.bits, &checked) : 0;
}

static void sg_clean(void) {
    char buf[200];
    unsigned gone, fixed, done = 0;
    if (!sg_cleans() || !sg.view || sg.select) return;
    if (!so_card()) {
        pod_toast(TR("msg_nottf"));
        return;
    }
    if (!sg_valid())
        sg_load(1); /* (another page's query replaced the stock list: read again, then check what is shown) */
    gone = sg_gone();
    if (!gone) {
        pod_toast(TR("All songs are on the card"));
        return;
    }
    if (!m1_card_mounted()) {
        memset(sg.sel.bits, 0, (sg.count + 7) / 8);
        pod_toast(TR("Card not readable, nothing removed"));
        return;
    }
    fixed = so_relink(sg.list, sg.count, sg.sel.bits);
    if (fixed) sg_load(1); /* the rows with their new paths (the marks go with the old list) */
    gone = sg_gone();
    if (gone) {
        m1_fmt(buf, sizeof buf,
               TR(gone == 1 ? "Remove %d missing song from this playlist?"
                            : "Remove %d missing songs from this playlist?"),
               (int)gone);
        int *ids = so_marked_ids(sg.list, sg.count, sg.sel.bits, gone); /* the rows the dialog's count is of */
        if (ids && pod_confirm(buf) && so_card() && m1_card_mounted() && sg_gone() &&
            so_keep_ids(sg.list, sg.count, sg.sel.bits, ids, gone))
            done = so_clean(sg.list, sg.count, sg.sel.bits);
        free(ids);
    }
    if (sg.sel.bits && sg.count) memset(sg.sel.bits, 0, (sg.count + 7) / 8);
    if (done) {
        pod_toast(TR("Playlist cleaned up"));
        sg_load(1);
    } else if (fixed) {
        m1_fmt(buf, sizeof buf, TR(fixed == 1 ? "%d song updated" : "%d songs updated"), (int)fixed);
        pod_toast(buf);
    }
}

/* A playlist header's name in one or two lines (the album page's title, m1_wrap2) and what sits under it: the pills and the rows AH_TITLE_LH lower while it takes two. */
static void sg_name_place(void) {
    sg.tsh = m1_wrap2(sg.hname, sg.hname2, sg_name_text(), PH_NAME_W) ? AH_TITLE_LH : 0;
    sg_top();
    widget_move(sg.hd_play, AH_PLAY_X, PH_BTN_Y + sg.tsh);
    widget_move(sg.hd_shuffle, AH_SHUF_X, PH_BTN_Y + sg.tsh);
    widget_set_visible(sg.hname2, sg.tsh != 0, 0);
    m1_pill_place(&sg.pill, PH_BTN_Y + sg.tsh);
    sg_pencil();
}

/* Rename Playlist (the card's row on a stock playlist; docs/modules/playlists.md "Rename Playlist"): our keyboard as New Playlist opens it (pl_create), the current name in the field. The keyboard is not
 * modal: sg_renamed runs on Done, after the keyboard page was told to close, with the name trimmed and 1 to KB_MAX (63) bytes; the playlist it is for is remembered (sg_rn_id), so a page that is no
 * longer that playlist's changes nothing. Stock's ids start at 0, so "a rename is waiting" is its own flag (sg_rn_on), not the id. */
static int sg_rn_id __attribute__((section(".scratch")));
static int sg_rn_on __attribute__((section(".scratch")));

/* The stock list of playlists (getAllPlayList into *pdeq_playlist, as New Playlist reads it) has another playlist called name: 1. A list that cannot be read is no duplicate (the statement still
 * names one row). The stock read writes "Playlists" into nagvation_title: the title is put back whatever the read gave. */
static int sg_pl_taken(int id, const char *name) {
    char title[NAV_TITLE_SIZE];
    void *list;
    unsigned i, n;
    int got;
    memcpy(title, (void *)NAV_TITLE, sizeof title);
    got = loadLocalClassList(CLASS_PLAYLISTS);
    memcpy((void *)NAV_TITLE, title, sizeof title);
    if (got <= 0) return 0;
    list = *(void **)PDEQ_PLAYLIST;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n; ++i) {
        void *r = deque_at(list, i);
        if (I(r, REC_DISC) != id && (!strcmp(cc_str(r, REC_TITLE), name) || !strcmp(cc_str(r, REC_NAME), name)))
            return 1;
    }
    return 0;
}

/* The list read again with Edit mode and its marks kept (the rows did not change; sg_load drops the marks with the old list). */
static void sg_edit_reload(void) {
    unsigned n = sg.count, nsel = sg.sel.nsel;
    unsigned bytes = (n + 7) / 8;
    unsigned char *keep = sg.select && sg.sel.bits && n ? calloc(bytes, 1) : (unsigned char *)0;
    if (keep) memcpy(keep, sg.sel.bits, bytes);
    sg_load(1);
    if (keep && sg.count == n && sg.sel.bits) {
        memcpy(sg.sel.bits, keep, bytes);
        sg.sel.nsel = nsel;
        sg_head();
        sg_redraw();
    }
    free(keep);
}

/* Done: an unchanged name does nothing; another playlist's name is stock's "already exists" message; else one statement renames the header row (so_rename_pl). Then the page's name, its header
 * (one or two lines), the small title, stock's nagvation_title when it held the old name, and a Home pin of this playlist (pins_rename_playlist) follow; the Playlists page reads its list again when it is
 * back in front (the database changed). A statement that did not run changes nothing and says so. */
static void sg_renamed(const char *name) {
    char old[sizeof sg.name];
    int id = sg_rn_id, on = sg_rn_on;
    sg_rn_on = 0;
    if (!on || !sg.win || !sg_cleans() || sg.pl_id != id || !name || !*name || strlen(name) > KB_MAX) return;
    if (!strcmp(name, sg.name)) return;
    if (sg_pl_taken(id, name)) {
        pod_toast(TR("msg_playlistexist"));
        return;
    }
    if (!so_rename_pl(id, name)) {
        pod_toast(TR("Can't rename playlist"));
        return;
    }
    memcpy(old, sg.name, sizeof old);
    snprintf(sg.name, sizeof sg.name, "%s", name);
    if (!strcmp((const char *)NAV_TITLE, old)) snprintf((char *)NAV_TITLE, 0x200, "%s", name);
    pins_rename_playlist(id, old, name);
    plc_rename(id, old, name);
    az_fit(sg.big, sg_name_text());
    sg_head();
    if (sg.head) {
        sg_name_place();
        sg_edit_reload(); /* (the rows start lower or higher with a name of the other number of lines) */
    }
}

static void sg_rename(void) {
    if (!sg_cleans() || !sg.view) return;
    sg_rn_id = sg.pl_id, sg_rn_on = 1;
    if (keyboard_open(TR("Rename Playlist"), TR("msg_newplaylists"), sg.name, sg_renamed, (kb_cancel_fn)0, KB_DONE) < 0)
        sg_rn_on = 0;
}

/* Pins the playlist to the top of Home, or takes the pin away (patch/pins.c): its id and name, and the mosaic's album keys from the list the page holds (grid_mosaic_keys, as the header's tile). */
static void sg_pin(void) {
    unsigned key[4];
    int nk;
    if (!sg_cleans() || !sg.view || sg.select) return;
    if (pins_has_playlist(
            sg.pl_id,
            sg.name)) { /* (an unreadable pins file: has is 0 and the pin below refuses with the toast, said once) */
        pins_unpin_playlist(sg.pl_id, sg.name);
        return;
    }
    memset(key, 0, sizeof key);
    nk = sg.count ? grid_mosaic_keys(sg.list, sg.albums, key, (int *)0) : 0;
    pins_pin_playlist(sg.pl_id, sg.name, key, (unsigned)nk);
}

static int sg_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx, cur = sg.sort > 3 ? 3 : sg.sort;
    (void)e;
    sg_menu(0);
    if (k == VS_ACT2) { /* a playlist's Clean Up Playlist */
        sg_clean();
        return RET_OK;
    }
    if (k == VS_ACT3) { /* a playlist's Pin Playlist / Unpin Playlist */
        sg_pin();
        return RET_OK;
    }
    if (k ==
        VS_SELECT) { /* the old Select button (a stock playlist's Edit): select mode (an empty list has nothing to select) */
        if (sg.view && (sg.count || sg_cleans()) && !sg.rv) sg_select(1);
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
            if (home_write_atomic(SONGS_SORT_FILE, rev ? "a\n" : "0\n") != 0) return RET_OK;
            sg.rev = rev;
        }
    } else { /* another order, in its default direction */
        if (sg.rev && home_write_atomic(SONGS_SORT_FILE, "0\n") == 0) sg.rev = 0;
        sg_set_flag(k);
    }
    sg_load(0);
    return RET_OK;
}

/* Search: our keyboard, then our results page (patch/search.c, docs/modules/search.md). Its queries leave their list in *pdeq_showlist, which makes this page read it again when it is
 * back. Where ours will not open (a results page is already under this one, or no keyboard asset) the stock page (@0x52704c: navigator_to("search_page"), nothing set first). */
static void sg_search(void) {
    if (sg.view && !sg.select && sg.src) {
        search_open_src(sg.src); /* never the stock page: it would search the card */
        return;
    }
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
    sg.fg_due = 0;
    if (!sg.view || !sg.g.tiles) return RET_OK;
    if (sg.reread) { /* back from the Add Songs page: the playlist read again (the songs added), Edit mode (if on) and the place kept */
        sg.reread = 0;
        *(int *)G_CLASS_TYPE = sg.cls;
        sg_edit_reload();
    } else if (
        sg.picker) { /* back from the stock playlist picker: its title and class put back, the add done (it changed the records it added), select mode over */
        sg.picker = 0;
        *(int *)G_CLASS_TYPE = sg.cls;
        memcpy((void *)NAV_TITLE, sg.title_save, sizeof sg.title_save);
        sg_select(0);
        sg_load(1);
    } else if (sg.src) {
        if (sg.src->gen(sg.src) != sg.sgen) {
            if (sg_rows_same())
                sg.sgen = sg.src->gen(sg.src), sg_redraw();
            else
                sg_load(1);
        }
        if (!sg.gen_timer) sg.gen_timer = timer_add(sg_on_gen, (void *)0, LS_GEN_MS);
        sg_spinner(sg.wait && sg.spin);
    } else if (!sg.rv && (!sg_valid() || sg_changes())) /* (the album view reads no stock list: nothing is stale) */
        sg_load(1); /* (a list read again whose rows are the same keeps its tiles: sg_load) */
    if (sg.cover_due) { /* back from the Cover page: the header's cover from the choice made there (Edit keeps the tile only while the choice is the same) */
        sg.cover_due = 0;
        if (sg.head && sg.hg.tiles) sg_head_prep();
    }
    sg_build_later();
    sg_kick(); /* the loader stops on a list another page replaced (Search's queries), and the list can be valid again by now: covers still to load start it here */
    return RET_OK;
}

/* The page below is put back from sg_under in the top page's destroy handler, and the window manager may send the page below its foreground event before that (the event
 * then went to the top page's state): the fg handler runs here when it has not run since, so the Add Songs page's songs show and the timers start again either way. */
static int sg_on_put_back(const void *unused) {
    (void)unused;
    if (sg.fg_due && sg.win) sg_on_fg((void *)0, (void *)0);
    return RET_OK;
}

static int sg_on_bg(void *ctx, void *e) {
    az_rail_end(&sg.al);
    rowmenu_close(&sg.rm);
    return sg_on_abort(ctx, e);
}

static int sg_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    sg_lift_end(0);
    if (sg.handle) bitmap_destroy(sg.handle);
    if (sg.pk_add) bitmap_destroy(sg.pk_add);
    if (sg.pk_done) bitmap_destroy(sg.pk_done);
    if (sg.add_note) bitmap_destroy(sg.add_note);
    if (sg.cbadge) bitmap_destroy(sg.cbadge);
    if (sg.add_badge) bitmap_destroy(sg.add_badge);
    free(sg.pk_h);
    m1_timer_stop(&sg.more_timer);
    m1_timer_stop(&sg.stale_timer);
    m1_timer_stop(&sg.gen_timer);
    ls_cover_end(&sg.cp);
    ls_spin_end(sg.spin);
    if (sg.src && sg.list) deque_destroy(sg.list);
    if (sg.scope_d) deque_destroy(sg.scope_d);
    sg_build_end();
    grid_free(&sg.g);
    grid_free(&sg.hg);
    grid_free(&sg.rg);
    free(sg.rrow);
    free(sg.htmp);
    if (sg.albums) deque_destroy(sg.albums);
    az_free(&sg.al);
    m1_sel_free(&sg.sel);
    free(sg.idx);
    rowmenu_free(&sg.rm);
    memset(&sg, 0, sizeof sg);
    if (sg_under) {
        memcpy(&sg, sg_under, sizeof sg), free(sg_under), sg_under = (void *)0;
        sg.reread =
            sg.head; /* (a playlist's page under an Add Songs page, in Edit or from its Add Songs row: its songs may have changed) */
        sg.fg_due = 1;
        timer_add(sg_on_put_back, (void *)0, 0);
    }
    return RET_OK;
}

/* A playlist's page over a Songs page (Search opened from it): the page below keeps its widgets, its state is set aside (its timers and the cover build ended; the
 * fg handler starts them again) and sg starts empty. 0 on success or with no page below, -1 when the page below stays (a second level, or no memory). */
static int sg_stack(void) {
    if (!sg.win) return 0;
    if (sg_under || !(sg_under = calloc(1, sizeof sg))) return -1;
    sg_build_end();
    m1_timer_stop(&sg.more_timer);
    m1_timer_stop(&sg.stale_timer);
    m1_timer_stop(&sg.gen_timer);
    ls_cover_end(&sg.cp);
    ls_spin_end(sg.spin);
    sg.more_timer = sg.stale_timer = sg.gen_timer = 0;
    memcpy(sg_under, &sg, sizeof sg);
    memset(&sg, 0, sizeof sg);
    return 0;
}

/* The page listing class cls (pl_id: a playlist's id; key: the title's key, or 0 for name). 0 once the page is up, -1 if the window could not open, -2 if the
 * asset is not ours (the page is left again). */
static int sg_split_next
    __attribute__((section(".scratch"))); /* songs_open_artist: the page about to open is an artist split's */
static int gs_split_next
    __attribute__((section(".scratch"))); /* songs_open_genre_split: the page about to open is a genre split's */
static int sg_open_page(int cls, int pl_id, const char *key, const char *name, const lib_src_t *src, int which,
                        void *scope) {
    int i, az_ok;
    void *scope_d = (void *)0;
    if (scope && !(scope_d = so_row_deque(scope)))
        return -1; /* (before the stack: a failure leaves the page below as it is) */
    /* a page is open already: a playlist's page, or a source's list of a row (an artist's All Songs reached through Search from the source's Songs page), goes over it (sg_stack); anything else does not open */
    if (sg.win && ((cls != CLASS_PLAYLIST_SONGS && !(src && scope) && !sg_pick_next) || sg_stack() == -1)) {
        if (scope_d) deque_destroy(scope_d);
        return -1;
    }
    memset(&sg, 0, sizeof sg);
    sg.cls = cls, sg.pl_id = pl_id, sg.key = key;
    sg.src = src, sg.which = which, sg.scope_d = scope_d;
    if (sg_pick_next) { /* Add Songs: the playlist's id, name (sg.name) and songs, taken from sg_add_songs */
        sg.pick = 1, sg.pk_id = sg_pick_id, sg.pk_h = sg_pick_h, sg.pk_n = sg_pick_n;
        sg_pick_h = (unsigned *)0, sg_pick_next = 0;
    }
    sg.split = sg_split_next, sg_split_next = 0;
    sg.gsplit = gs_split_next, gs_split_next = 0;
    if (sg_artist())
        memcpy(sg.ci, (void *)CLASSINFO, CLASSINFO_SIZE); /* songs_open_artist ran the two queries just before */
    for (i = 0; name[i] && i < (int)sizeof sg.name - 1; ++i) sg.name[i] = name[i];
    if (name[i]) /* a name cut short is cut before a character, not inside one */
        while (i > 0 && ((unsigned char)name[i] & 0xc0) == 0x80) --i;
    sg.name[i] = 0;
    sg.win = window_open("m1plus_songs");
    if (!sg.win) {
        if (sg.scope_d) deque_destroy(sg.scope_d), sg.scope_d = (void *)0;
        free(sg.pk_h);
        if (sg_under)
            memcpy(&sg, sg_under, sizeof sg), free(sg_under),
                sg_under = (void *)0; /* the page below is the open one again */
        return -1;
    }
    widget_on(sg.win, EVT_DESTROY, sg_on_destroy, (void *)0);
    sg.back = m1_bind(sg.win, "btn_return", sg_on_back, (void *)0);
    sg.np = m1_bind(sg.win, "btn_backtoplayer", m1_on_player, (void *)0);
    sg.btn_more = m1_bind(sg.win, "btn_more", sg_on_more, (void *)0);
    sg.btn_select = m1_bind(sg.win, "btn_select", sg_on_more, (void *)0); /* optional: Select in the "..." place */
    sg.btn_cf = m1_bind(sg.win, "btn_coverflow", sg_on_cf, (void *)0); /* optional */
    sg.btn_search = m1_bind(sg.win, "btn_search", sg_on_search, (void *)0); /* optional */
    sg.st_gtitle = widget_lookup(sg.win, "label_grid_title", 1); /* optional: the album view's text styles */
    sg.st_gsub = widget_lookup(sg.win, "label_grid_sub", 1);
    sg.btn_selall = m1_bind(sg.win, "btn_selall", sg_on_selall, (void *)0);
    sg.btn_play = m1_bind(sg.win, "btn_play", sg_on_play, (void *)0);
    sg.btn_shuffle = m1_bind(sg.win, "btn_shuffle", sg_on_shuffle, (void *)0);
    sg.hd_play = m1_bind(sg.win, "hd_play", sg_on_play, (void *)0);
    sg.hd_shuffle = m1_bind(sg.win, "hd_shuffle", sg_on_shuffle, (void *)0);
    sg.pill.glyph = widget_lookup(sg.win, "sg_glyph", 1);
    sg.pill.ptext = widget_lookup(sg.win, "sg_play_text", 1);
    sg.btn_add = m1_bind(sg.win, "sg_add", sg_on_add, (void *)0);
    sg.btn_del = m1_bind(sg.win, "sg_del", sg_on_delete, (void *)0);
    sg.edel = m1_bind(sg.win, "sg_edel", sg_on_delete, (void *)0); /* optional: a playlist's Edit bar (Delete | +) */
    sg.eplus = m1_bind(sg.win, "sg_eplus", sg_on_eplus, (void *)0);
    sg.hpencil = widget_lookup(sg.win, "sg_hpencil", 1);
    sg.title = widget_lookup(sg.win, "label_title", 1);
    sg.fade = widget_lookup(sg.win, "img_nb_fade", 1); /* optional */
    sg.view = widget_lookup(sg.win, "view_grid", 1);
    sg.sv = widget_lookup(sg.win, "songs_scrollview", 1);
    sg.status = widget_lookup(sg.win, "label_status", 1);
    sg.spin = widget_lookup(sg.win, "sg_spin", 1); /* optional */
    sg.st_title = widget_lookup(sg.win, "label_row_title", 1);
    sg.st_sub = widget_lookup(sg.win, "label_row_sub", 1);
    sg.st_dim = widget_lookup(sg.win, "label_row_dim", 1);
    sg.st_subdim = widget_lookup(sg.win, "label_row_subdim", 1);
    az_ok = az_bind(&sg.al, sg.win);
    sg.bar = widget_lookup(sg.win, "sg_bar", 1);
    sg.big = widget_lookup(sg.win, "sg_title", 1); /* optional: the large title */
    sg.foot = widget_lookup(sg.win, "sg_foot", 1);
    sg.hname = widget_lookup(sg.win, "sg_hname", 1); /* optional: a playlist's header */
    sg.hname2 = widget_lookup(sg.win, "sg_hname2", 1);
    sg.al.win = sg.win, sg.al.sv = sg.sv, sg.al.top = SG_TOP, sg.al.row = ROW;
    az_prefs(&sg.al);
    if (!sg.foot || !sg.back || !sg.np || !sg.btn_more || !sg.btn_select || !sg.btn_selall || !sg.btn_play ||
        !sg.btn_shuffle || !sg.hd_play || !sg.hd_shuffle || !sg.pill.glyph || !sg.pill.ptext || !sg.btn_add ||
        !sg.btn_del || !sg.title || !sg.view || !sg.sv || !sg.status || !sg.st_title || !sg.st_sub || !az_ok ||
        !sg.bar) {
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
    if (sg_cleans()) rowmenu_set_remove(&sg.rm, sg_remove_one); /* a stock playlist: Remove from Playlist, last */
    if (sg_direct()) {
        if (sg_selects()) { /* the card would hold Select alone: the Select button takes the "..." place (left cap at 214, or the middle piece after Search / Cover Flow) and sg.btn_more stands for it from here on */
            m1_show(sg.btn_more, 0);
            sg.btn_more = sg.btn_select;
            m1_show(sg.btn_more, 1);
        } else { /* a source without Select: the card has nothing to hold, so neither button shows */
            m1_show(sg.btn_more, 0);
            m1_show(sg.btn_select, 0);
        }
    }
    if ((sg_artist() && sg.btn_cf) ||
        sg_searches()) { /* the capsule's left cap at Albums' Cover Flow place: Cover Flow on an artist's songs, Search on the lists that search; the "..." (or Select) is its middle piece */
        const char *mid = sg_direct() ? "pod_nav_select" : "pod_nav_moremid";
        char down[32];
        snprintf(down, sizeof down, "%s_down", mid);
        m1_show(sg_artist() ? sg.btn_cf : sg.btn_search, 1);
        if (!sg_mid()) /* no middle piece: the left cap moves to 214, beside Now Playing (no gap in the capsule) */
            widget_move(sg_artist() ? sg.btn_cf : sg.btn_search, NAV_VIEW_X, 0);
        grid_icons(sg.btn_more, mid, down);
    }
    if (sg.src && !sg_searches() && !sg_selects() &&
        !(sg_artist() &&
          sg.btn_cf)) { /* no piece on the capsule's left: Now Playing is the plain disc, as on a bar with no buttons */
        grid_icons(sg.np, "ah_nav_np", "ah_nav_np_down");
    }
    if (!sg_lib() || sg.pick) grid_title_end(sg.title, sg_title_end()); /* a list: the titles are the list's */
    if (!sg_lib()) az_fit(sg.big, sg_name_text());
    /* A playlist's header (docs/modules/songs.md): the mosaic tile (the Playlists page's, patch/grid.c) and the name under it (the count is the footer under the last row,
     * as Apple Music's), the pills and the rows lower, the large title gone. Without the label, the tile or the quadrant buffer the page keeps its plain look (the large title). */
    if (sg_playlist() && sg.hname && sg.hname2) {
        sg.htmp = calloc((PH_COVER / 2) * (PH_COVER / 2), 4);
        if (grid_init(&sg.hg, sg.win, 1, PH_COVER, PH_COVER_R)) {
            if (sg.src) sg.hg.url = sbs_cover_url;
            grid_placeholder(&sg.hg);
            sg.hg.st_title = sg.st_gtitle; /* the name on a chosen cover (optional label) */
            sg.head = 1;
            if (sg_cleans()) {
                sg.handle = sg_make_handle(); /* (without it Edit has no handles) */
                sg.cbadge =
                    m1_asset_rgba(sg.win, "sg_cbadge", SG_CBADGE, SG_CBADGE,
                                  0); /* (without it the cover has no badge; a tap still opens the Cover page) */
                sg.add_note = sg_make_bmp("sg_addnote", LIST_ART,
                                          SG_HANDLE_RGB); /* (without both an empty playlist says "No songs") */
                sg.add_badge = sg_make_bmp("sg_addbadge", LIST_ART, 0x00ffffffu);
            }
            m1_show(sg.big, 0);
            widget_set_visible(sg.hname, 1, 0); /* (insensitive labels: shown, never a touch target) */
            sg_name_place();
        } else
            grid_free(&sg.hg);
    }
    if (!sg.head) {
        m1_centre_pill(sg.btn_play, SG_PILL_W);
        m1_centre_pill(sg.btn_shuffle, SG_PILL_W);
    }
    if (sg.pick) { /* Add Songs: the check where Back is, no buttons and no large title, the rows start under the navbar */
        m1_show(sg.btn_more, 0);
        m1_show(sg.btn_select, 0);
        m1_show(sg.np, 0);
        if (sg.btn_cf) m1_show(sg.btn_cf, 0);
        if (sg.btn_search) m1_show(sg.btn_search, 0);
        m1_show(sg.big, 0);
        grid_icons(sg.back, "ah_nav_done", "ah_nav_done_down");
        sg.al.top = 0;
        sg.pk_add = sg_make_bmp("sg_padd", RM_DOTS_PX, 0x00ffffffu);
        sg.pk_done = sg_make_bmp("sg_pdone", RM_DOTS_PX, SG_HANDLE_RGB);
    }
    sg_pills();
    az_make_disc(&sg.al);
    m1_sel_init(&sg.sel, sg.win, sg.back, sg.title, sg.btn_selall, sg.bar, sg.btn_add, sg.btn_del, (void *)0,
                (void *)0); /* the marks: all or none */
    sg.noscroll = grid_scroll_bind(sg.sv, sg_on_scroll, sg.title, &sg.title_on);
    widget_on(sg.win, EVT_WINDOW_TO_FG, sg_on_fg, (void *)0);
    widget_on(sg.win, EVT_WINDOW_TO_BG, sg_on_bg, (void *)0);
    widget_on(sg.view, EVT_POINTER_DOWN, sg_on_down, (void *)0);
    widget_on(sg.view, EVT_POINTER_UP, sg_on_up, (void *)0);
    widget_on(sg.view, EVT_POINTER_MOVE, sg_on_move, (void *)0);
    widget_on(sg.view, EVT_POINTER_ABORT, sg_on_abort, (void *)0);
    widget_on(sg.view, EVT_AFTER_PAINT, sg_on_paint, (void *)0);
    az_bind_rail(&sg.al, sg_on_rail, sg_on_rail_paint);
    if (!grid_init(&sg.g, sg.win, GRID_TILES, LIST_ART, 0)) {
        grid_free(&sg.g);
        m1_show(sg.view, 0);
        m1_show(sg.al.rail, 0);
        m1_show(sg.status, 1);
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
    int r = sg_open_page(cls, pl_id, key, name, (const lib_src_t *)0, 0, (void *)0);
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

/* A genre row the genre split made (patch/genresplit.c gs_is_row): its songs are the songs of every tag that names it, answered by gs_fill. No fallback to the stock page: the stock query on a
 * split name finds nothing, so it would open an empty list. -1 when the page did not open. */
int songs_open_genre_split(const char *name, int unknown) {
    int r;
    gs_split_next = 1;
    r = sg_open(CLASS_GENRE_SONGS, unknown != 0, (const char *)0, name, -1);
    gs_split_next = 0;
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
    if (!comp && as_is_row(artist)) return as_load(artist); /* the artist split's row: its songs, patch/artsplit.c */
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
    int split = scope != CLASS_COMPOSERS && as_is_row(artist), unknown = split && I(artist, REC_ID) == -1;
    if (sg.win || !artist || !songs_artist_list(artist, scope)) return -1;
    sg_split_next = split;
    return sg_open(scope == CLASS_COMPOSERS ? CLASS_14 : CLASS_ARTIST_SONGS, unknown, (const char *)0,
                   cc_str(artist, REC_TITLE), -1);
}

/* The artist's (or composer's: scope CLASS_COMPOSERS) albums page's Play (how SO_IN_ORDER: the songs in order from the first) and Shuffle (SO_SHUFFLE: the stock Shuffle
 * mode from a random song), the way this page's pills play the list: the two queries, then so_play on class 0xff11 (a composer's 0xff14, the class the stock All songs
 * row leaves; the record is fresh). -1 when there is nothing to play. */
int songs_play_artist(void *artist, unsigned scope, int how) {
    void *list = songs_artist_list(artist, scope);
    if (!list || !deque_size(list)) return -1;
    if (scope != CLASS_COMPOSERS && as_is_row(artist)) { /* the artist split's songs are the queue as they are */
        so_play_own(list, how == SO_SHUFFLE ? -1 : 0, how, pod_start_player);
        return 0;
    }
    so_play(scope == CLASS_COMPOSERS ? CLASS_14 : CLASS_ARTIST_SONGS, list, how == SO_SHUFFLE ? -1 : 0, how,
            pod_start_player);
    return 0;
}

/* The page for a library source's list (patch/libsrc.h): the Songs page fed from src->list(which, NULL), which is LS_SONGS, LS_FAVORITES or LS_DOWNLOADED, titled `title`. Taps, Play and Shuffle play
 * through so_play_src; covers come from src->cover; a list the source says is incomplete has no rail and is read again, scroll position kept, as the source's gen moves. src NULL or &lib_stock opens
 * today's page: the library for LS_SONGS, the stock Favorites list for LS_FAVORITES (title is the stock's); LS_DOWNLOADED has none (-1). 0 once the page is up, -1 when it did not open, -2 an asset that is
 * not ours (as the other openers). The rows' download state and the "..." sheet come from src->row and src->act (the row menu). */
/* The same page scoped to a row of the source (patch/libsrc.h, src->list's scope): scope is the row (copied, the page keeps the copy for its re-reads): LS_PLAYLISTS of a
 * playlist row is its tracks, LS_SONGS of an artist row is the artist's songs (the All Songs tile). NULL scope is songs_open_src. -1 when the page did not open or a
 * list needs a scope it does not have. */
int songs_open_src_in(const lib_src_t *src, int which, void *scope, const char *title) {
    if (!src || src == &lib_stock) {
        if (which == LS_SONGS) return songs_open();
        return which == LS_FAVORITES ? songs_open_list(HOME_FAV) : -1;
    }
    if (which != LS_SONGS && which != LS_FAVORITES && which != LS_DOWNLOADED && which != LS_PLAYLISTS) return -1;
    if (which == LS_PLAYLISTS && !scope) return -1;
    return sg_open_page(CLASS_ALL_SONGS, 0, (const char *)0, title ? title : "", src, which, scope);
}

int songs_open_src(const lib_src_t *src, int which, const char *title) {
    return songs_open_src_in(src, which, (void *)0, title);
}
