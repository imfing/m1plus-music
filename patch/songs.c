/* M1+ Music Songs: the library as one list, in the Apple Music manner.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_songs.bin (docs/modules/songs.md has the whole design): the glass navbar (Back, the small title, Search, Sort, Select, Now Playing) over a
 * stock list, list_view > scroll_view (songs_scrollview) whose ONE child, view_grid, is the content view of the Albums page (patch/albums.c): it paints the rows,
 * the section headers, the pinned header and the select marks itself in its own EVT_AFTER_PAINT, with no widget per song; the stock scroll_view does the scrolling.
 * The content view's only children are the large title and the Play / Shuffle pills (real flat buttons that scroll with it). Beside the list, as widgets of the
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
 *   sort      the sort card sets sort_flag as the stock sort dialog's row handler does (the flag and [SYSSET] SORTSELECT), then reads the list again.
 *   lists     the same page shows the other stock song lists, each in the stock order of its query (docs/modules/songs.md "The other lists"): Favourites, Recently
 *             Added, Recently Played, Most Played, Hi-Res (the menu rows, songs_open_list) and a playlist (the Playlists page, songs_open_playlist: its id goes into
 *             classinfo[1] before every query and play, as the stock row tap leaves it). A list is what the stock allmusic_page shows for its class: no sort (Search
 *             moves to Sort's slot, the capsule is three pieces), so no sections and no rail; its title is the menu row's text or the playlist's name, cut with an
 *             ellipsis; play, Shuffle (that list, the stock Shuffle mode) and the stock Delete (batch_delete_file with the list's class: the stock removes the
 *             song from that list's table, and the file too when asked) use its class; it is read again whenever the page comes back to the front (a play changes
 *             Recently Played and Most Played, Now Playing's star the Favourites).
 *             A genre's songs (songs_open_genre, from the Genres page, class 0xff09) are such a list too: the genre's name is in classinfo + 0x30d (and classinfo[0],
 *             the Unknown Genre byte) for every query and play, as the stock row tap leaves it; the stock navbar has no Search there, so the capsule is Select | Now
 *             Playing (Select the left cap).
 *             An artist's songs (Cover Flow's artist page, songs_open_artist) is the same page on class 0xff11: its whole state is the 0x390 byte browsing
 *             record loadAlbumList(0xf004) and loadAlbumdetailList(0xff01, the All songs row) build, which the page snapshots and puts back before every query
 *             and play; the artist is the title and the grey line of a row is its album.
 *   albums    Recently Added (class 0xf009) has a navbar toggle (btn_albumview, docs/modules/recent-albums.md): the same page shows the newest-first Albums grid
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
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "songops.h"
#include "rowmenu.h"
#include "subsonic.h"
#include "durations.h"

extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */
extern int search_open(void); /* patch/search.c: our keyboard, then the results page; -1 when it did not open */
extern void pod_toast(const char *text);
extern unsigned pod_rand(unsigned n);

#define ROW LIST_ROW_H
#define SG_W 320 /* the content and scroll_view width; the mobile scrollbar sits off the screen edge */
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

typedef struct {
    void *local;
    const sb_song_t *server;
    unsigned order;
    unsigned local_index;
    unsigned char source;
    unsigned short duration;
} sg_entry_t;

typedef struct {
    unsigned hash;
    unsigned local_index;
    unsigned short duration;
    unsigned char visible;
} sg_match_slot_t;

static void sg_set_sig(song_t *s, unsigned h) {
    s->sig[0] = (unsigned char)h, s->sig[1] = (unsigned char)(h >> 8), s->sig[2] = (unsigned char)(h >> 16);
}
static int sg_same_sig(const song_t *a, const song_t *b) {
    return a->sig[0] == b->sig[0] && a->sig[1] == b->sig[1] && a->sig[2] == b->sig[2];
}

static struct {
    void *win, *view, *sv, *status, *title, *back, *np;
    void *fade; /* the navbar's fade (img_nb_fade, optional): shown only while the list is scrolled */
    void *btn_view; /* Recently Added only (optional widget): the songs / albums toggle */
    void *btn_cf; /* the artist's songs list only: the Cover Flow button (back to the covers) */
    void *btn_search, *btn_sort, *btn_select, *btn_selall, *btn_play, *btn_shuffle, *btn_add, *btn_del;
    void *st_title, *st_sub; /* hidden labels whose styles are the text styles (the rail's and the header's are az's) */
    void *bar, *scrim, *card, *tick[SG_SORT_ROWS];
    void *list; /* the stock local list the index is of (*pdeq_showlist when valid) */
    void *first; /* its first record: with the size, tells a list another query replaced */
    unsigned count;
    song_t *idx; /* count entries */
    unsigned char *sel; /* the select mode's bitset: (count + 7) / 8 bytes */
    unsigned nsel;
    int select; /* select mode */
    int sort; /* sort_flag as the page last read it */
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
        [CLASSINFO_SIZE]; /* CLASS_ARTIST_SONGS: the browsing record of the artist (CLASSINFO, as the two stock queries left it), put back before every query and play */
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
    unsigned local_count;
    sg_entry_t *entry; /* the merged virtual library when Navidrome is indexed */
    unsigned entry_count, entry_cap, nav_cursor, nav_total, nav_local_visible, nav_timer;
    unsigned nav_match_cap;
    sg_match_slot_t *nav_match;
    sb_library_index_t nav_index;
    sb_library_downloads_t nav_downloads;
    int nav_overlay, nav_scanning, nav_filter, nav_dur_held;
    char nav_name[SB_TEXT], nav_artist[SB_META];
} sg __attribute__((section(".scratch")));

static int sg_on_stale(const void *unused);
static int sg_nav_scan_step(void);
static void sg_nav_schedule(void);
static void sg_select(int on);
static void *sg_under __attribute__((section(
    ".scratch"))); /* a Songs page below the one open (Search was opened from it and a playlist result opened ours): its state, put back when this page is destroyed */
static struct {
    int active, filter;
    char name[SB_TEXT], artist[SB_META];
} sg_nav_request __attribute__((section(".scratch")));

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

static void sg_get_entry(unsigned i, sg_entry_t *entry) {
    if (!entry) return;
    entry->local = (void *)0, entry->server = (const sb_song_t *)0;
    entry->order = 0, entry->local_index = i, entry->source = SB_LIBRARY_LOCAL, entry->duration = 0;
    if (sg.nav_overlay && sg.entry && i < sg.entry_count) {
        entry->local = sg.entry[i].local;
        entry->server = sg.entry[i].server;
        entry->order = sg.entry[i].order;
        entry->local_index = sg.entry[i].local_index;
        entry->source = sg.entry[i].source;
        entry->duration = sg.entry[i].duration;
    } else
        entry->local = sg.list && i < deque_size(sg.list) ? deque_at(sg.list, i) : (void *)0;
}

static const char *sg_entry_title(const sg_entry_t *entry) {
    if (entry && entry->server) return entry->server->title[0] ? entry->server->title : "Untitled";
    return entry && entry->local ? sg_name(entry->local) : "";
}

static const char *sg_entry_artist(const sg_entry_t *entry) {
    if (entry && entry->server) return entry->server->artist;
    return entry && entry->local ? cc_str(entry->local, REC_ARTIST) : "";
}

static const char *sg_entry_album(const sg_entry_t *entry) {
    if (entry && entry->server) return entry->server->album;
    return entry && entry->local ? cc_str(entry->local, REC_ALBUM) : "";
}

static const char *sg_entry_subtitle(const sg_entry_t *entry) {
    if (sg.nav_filter == SB_LIBRARY_FILTER_ARTIST || sg.nav_filter == SB_LIBRARY_FILTER_ALBUM_ARTIST)
        return sg_entry_album(entry);
    return sg_entry_artist(entry);
}

static int sg_entry_stream(const sg_entry_t *entry) {
    return entry && entry->source == SB_LIBRARY_STREAM && entry->server;
}

static int sg_text_equal(const char *a, const char *b) {
    unsigned i = 0, j = 0;
    if (!a) a = "";
    if (!b) b = "";
    while (a[i] == ' ' || a[i] == '\t' || a[i] == '\r' || a[i] == '\n') ++i;
    while (b[j] == ' ' || b[j] == '\t' || b[j] == '\r' || b[j] == '\n') ++j;
    for (;;) {
        unsigned ca = (unsigned char)a[i], cb = (unsigned char)b[j];
        while (ca && (a[i] == ' ' || a[i] == '\t' || a[i] == '\r' || a[i] == '\n') &&
               (a[i + 1] == ' ' || a[i + 1] == '\t' || a[i + 1] == '\r' || a[i + 1] == '\n'))
            ++i, ca = (unsigned char)a[i];
        while (cb && (b[j] == ' ' || b[j] == '\t' || b[j] == '\r' || b[j] == '\n') &&
               (b[j + 1] == ' ' || b[j + 1] == '\t' || b[j + 1] == '\r' || b[j + 1] == '\n'))
            ++j, cb = (unsigned char)b[j];
        if (ca >= 'A' && ca <= 'Z') ca += 'a' - 'A';
        if (cb >= 'A' && cb <= 'Z') cb += 'a' - 'A';
        if (ca != cb) return 0;
        if (!ca) return 1;
        ++i, ++j;
    }
}

static unsigned sg_hash_text(unsigned h, const char *s) {
    unsigned n = 0;
    if (!s) s = "";
    while (s[n] == ' ' || s[n] == '\t' || s[n] == '\r' || s[n] == '\n') ++n;
    while (s[n]) {
        unsigned c = (unsigned char)s[n++];
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
            while (s[n] == ' ' || s[n] == '\t' || s[n] == '\r' || s[n] == '\n') ++n;
            if (!s[n]) break;
            c = ' ';
        }
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        h = (h ^ c) * 16777619u;
    }
    return (h ^ 0xffu) * 16777619u;
}

static unsigned sg_duplicate_hash(const char *title, const char *artist, const char *album) {
    unsigned h = sg_hash_text(2166136261u, title);
    h = sg_hash_text(h, artist);
    h = sg_hash_text(h, album);
    return h ? h : 1u;
}

static unsigned sg_local_duplicate_hash(void *rec) {
    const char *title = sg_name(rec);
    return sg_duplicate_hash(title, cc_str(rec, REC_ARTIST), cc_str(rec, REC_ALBUM));
}

static int sg_strong_local_match(const sb_song_t *song, void *rec) {
    unsigned size = 0;
    int seconds, local_track, local_disc;
    if (!song || !rec || !sg_text_equal(song->title, sg_name(rec)) ||
        !sg_text_equal(song->artist, cc_str(rec, REC_ARTIST)) || !sg_text_equal(song->album, cc_str(rec, REC_ALBUM)))
        return 0;
    local_track = *(int *)((char *)rec + REC_TRACK);
    local_disc = *(int *)((char *)rec + REC_DISC);
    if (song->track && local_track && song->track != (unsigned)local_track) return 0;
    if (song->disc && local_disc && song->disc != (unsigned)local_disc) return 0;
    if (song->track && local_track && song->track == (unsigned)local_track &&
        (!song->disc || !local_disc || song->disc == (unsigned)local_disc))
        return 1;
    seconds = dur_song(rec, &size);
    return song->duration && seconds > 0 &&
           (unsigned)(seconds > (int)song->duration ? seconds - (int)song->duration : (int)song->duration - seconds) <=
               1u;
}

static void sg_match_add(void *rec, unsigned local_index, int visible) {
    unsigned hash = sg_local_duplicate_hash(rec), at = hash & (sg.nav_match_cap - 1);
    while (sg.nav_match[at].hash) at = (at + 1) & (sg.nav_match_cap - 1);
    sg.nav_match[at].hash = hash, sg.nav_match[at].visible = visible != 0;
    sg.nav_match[at].local_index = local_index;
}

static sg_match_slot_t *sg_remote_local_copy(const sb_song_t *song) {
    unsigned hash, at;
    if (!song || !sg.nav_match || !sg.nav_match_cap) return (sg_match_slot_t *)0;
    hash = sg_duplicate_hash(song->title, song->artist, song->album);
    at = hash & (sg.nav_match_cap - 1);
    while (sg.nav_match[at].hash) {
        sg_match_slot_t *slot = &sg.nav_match[at];
        unsigned local_index = slot->local_index;
        if (slot->hash == hash && sg.list && local_index < sg.local_count &&
            sg_strong_local_match(song, deque_at(sg.list, local_index)))
            return slot;
        at = (at + 1) & (sg.nav_match_cap - 1);
    }
    return (sg_match_slot_t *)0;
}

static unsigned short sg_local_server_duration(void *rec, unsigned local_index) {
    unsigned hash, at;
    if (!rec || !sg.nav_match || !sg.nav_match_cap) return 0;
    hash = sg_local_duplicate_hash(rec), at = hash & (sg.nav_match_cap - 1);
    while (sg.nav_match[at].hash) {
        if (sg.nav_match[at].hash == hash && sg.nav_match[at].local_index == local_index)
            return sg.nav_match[at].duration;
        at = (at + 1) & (sg.nav_match_cap - 1);
    }
    return 0;
}

static const char *sg_local_filter_field(void *rec, int filter) {
    switch (filter) {
    case SB_LIBRARY_FILTER_ARTIST:
        return cc_str(rec, REC_ARTIST);
    case SB_LIBRARY_FILTER_ALBUM_ARTIST: {
        const char *album_artist = cc_str(rec, REC_ALBUM_ARTIST);
        return *album_artist ? album_artist : cc_str(rec, REC_ARTIST);
    }
    case SB_LIBRARY_FILTER_COMPOSER:
        return cc_str(rec, REC_COMPOSER);
    case SB_LIBRARY_FILTER_GENRE:
        return cc_str(rec, REC_GENRE);
    default:
        return "";
    }
}

static int sg_local_matches(void *rec) {
    const char *album_artist;
    if (!rec) return 0;
    if (sg.nav_filter == SB_LIBRARY_FILTER_NONE) return 1;
    if (sg.nav_filter == SB_LIBRARY_FILTER_ALBUM) {
        const char *album_artist = cc_str(rec, REC_ALBUM_ARTIST);
        return sg_text_equal(cc_str(rec, REC_ALBUM), sg.nav_name) &&
               (!sg.nav_artist[0] ||
                sg_text_equal(*album_artist ? album_artist : cc_str(rec, REC_ARTIST), sg.nav_artist));
    }
    if (sg.nav_filter == SB_LIBRARY_FILTER_ALBUM_ARTIST) {
        album_artist = sg_local_filter_field(rec, sg.nav_filter);
        return sg_text_equal(album_artist, sg.nav_name);
    }
    return sg_text_equal(sg_local_filter_field(rec, sg.nav_filter), sg.nav_name);
}

/* ---------------------------------------------------------------------------
 * The stock list and its index
 */

/* The section rank of a record, in the order the stock Title sort puts them (toolsQueryDbTable's title comparator 0x5e0dac: digits and most symbols before the
 * letters): 0 "#" (the Initial '*', a title that starts with a digit, or '#', anything else), 1..26 'A'..'Z'. From the Initial the scan stored; 0 (never written: a
 * database older than the column) takes the title's first character. */
static unsigned char sg_rank(void *rec) {
    int c = B(rec, REC_INITIAL);
    if (!c) c = (unsigned char)*sg_name(rec);
    return (unsigned char)az_rank_of(c);
}

static unsigned char sg_entry_rank(const sg_entry_t *entry) {
    if (entry && entry->local) return sg_rank(entry->local);
    return (unsigned char)az_rank_of(cc_name_initial(sg_entry_title(entry)));
}

/* The index is of the stock list `list` as long as that list is still in *pdeq_showlist, as big, and starts with the same record. */
static int sg_valid(void) {
    void *cur = *(void **)PDEQ_SHOWLIST;
    unsigned expect = sg.nav_overlay ? sg.local_count : sg.count;
    if (sg.nav_overlay && !sg.nav_local_visible)
        return 1; /* server-only rows do not depend on the stock global song list */
    if (sg.nav_overlay)
        return cur == sg.list && (!expect || (cur && deque_size(cur) == expect && deque_at(cur, 0) == sg.first));
    return sg.list && cur == sg.list && deque_size(cur) == expect && (!expect || deque_at(cur, 0) == sg.first);
}

static int sg_stock_valid(void) {
    void *cur = *(void **)PDEQ_SHOWLIST;
    if (!sg.nav_overlay) return sg_valid();
    return cur == sg.list &&
           (!sg.local_count || (cur && deque_size(cur) == sg.local_count && deque_at(cur, 0) == sg.first));
}

static int sg_lib(void) {
    return sg.cls == CLASS_ALL_SONGS;
} /* the library: the only list with the sort card, sections and the rail */
static int sg_genre(void) {
    return sg.cls == CLASS_GENRE_SONGS;
} /* a genre's songs: the stock navbar has no Search there */
static int sg_artist(void) {
    return sg.cls == CLASS_ARTIST_SONGS;
} /* an artist's songs: Cover Flow's artist page is its other view (a toggle, not a stack) */
static int sg_recent(void) {
    return sg.cls == CLASS_RECENTADD && sg.btn_view;
} /* Recently Added with the view toggle: Search 122 | Select 168 | toggle 214 | Now Playing, no small title (it does not fit before x 122) */
static int sg_search_x(void) {
    return sg_lib() || sg_recent() ? NAV_SEARCH_X : sg_genre() ? NAV_VIEW_X : NAV_CF_X;
} /* the capsule's first piece: a list's Search takes Sort's slot; a genre's has none (Select, the left cap, is first) */

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
    else if (sg.cls == CLASS_ARTIST_SONGS)
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
static int sg_more_right(void) { return sg.al.nsec > 0 ? RM_MORE_RIGHT_RAIL : RM_MORE_RIGHT; }
static int sg_edge(void) { return rowmenu_on(&sg.rm) ? rowmenu_zone_x(sg_more_right()) - RM_TEXT_GAP : SG_TEXT_END; }
static int sg_more(void) { return !sg.select && rowmenu_on(&sg.rm); }
static int sg_text_end(void) { return sg.select ? SG_TEXT_END : sg_edge(); }

static int sg_is_sel(int i) { return sg.sel && (sg.sel[i >> 3] >> (i & 7) & 1); }

/* The tile of song a, made from the stock record (the caller has checked sg_valid). */
static void sg_prep(tile_t *t, int a) {
    sg_entry_t entry;
    sg_get_entry((unsigned)a, &entry);
    const char *sub = sg.cls == CLASS_ARTIST_SONGS || sg.nav_filter == SB_LIBRARY_FILTER_ARTIST ||
                              sg.nav_filter == SB_LIBRARY_FILTER_ALBUM_ARTIST
                          ? sg_entry_album(&entry)
                          : sg_entry_subtitle(&entry);
    char buf[300];
    if (!sg.nav_overlay &&
        sg.cls ==
            CLASS_OFTEN) { /* Most Played: "12 plays · Artist" (the count first, a long artist is the part that is cut); REC_TRACK = plays - 1 */
        int plays = I(entry.local, REC_TRACK) + 1;
        char count[48];
        pod_fmt(count, sizeof count, TR(plays == 1 ? "%d play" : "%d plays"), plays);
        snprintf(buf, sizeof buf, "%s%s%s", count, sub[0] ? " \xc2\xb7 " : "", sub);
        sub = buf;
    }
    grid_set(t, sg_entry_title(&entry), sub, sg.idx[a].key);
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

#define SG_NAV_DOT 10
static void sg_nav_dot_paint(void *canvas, int x, int y) {
    if (y < 0 || y + SG_NAV_DOT > GRID_VIEW_H) return;
    canvas_set_fill_color(canvas, 0xff34c759u);
    canvas_fill_rect(canvas, x + 4, y, 2, 1);
    canvas_fill_rect(canvas, x + 2, y + 1, 6, 1);
    canvas_fill_rect(canvas, x + 1, y + 2, 8, 6);
    canvas_fill_rect(canvas, x + 2, y + 8, 6, 1);
    canvas_fill_rect(canvas, x + 4, y + 9, 2, 1);
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
    int r0, r1, r, off = sg_off(), tx = sg_tx(), hair = SG_TEXT_END - tx, pass;
    if (sg.head) { /* a playlist's mosaic (the cover, or the placeholder disc until it is made) */
        grid_tile_t *h = grid_find(&sg.hg, 0);
        if (h) grid_blit(canvas, &sg.hg, h, PH_COVER_X, PH_COVER_Y - off, GRID_VIEW_H);
    }
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
        if (sg_more() && (!sg.nav_overlay || sg.entry[r].source == SB_LIBRARY_LOCAL))
            rowmenu_paint(canvas, &sg.rm, sg_more_right(), sg.al.nsec > 0, y, ROW, GRID_VIEW_H);
    }
    for (pass = 0; pass < 2; ++pass) { /* titles, then artists: one text style at a time */
        widget_prepare_text_style(pass ? sg.st_sub : sg.st_title, canvas);
        for (r = r0; r <= r1; ++r) {
            sg_entry_t entry;
            int row_end, row_room, w;
            sg_get_entry((unsigned)r, &entry);
            row_end = sg_entry_stream(&entry) ? (sg.al.nsec > 0 ? SG_RAIL_X : SG_W) : sg_text_end();
            row_room = row_end - tx;
            w = row_room - (sg_entry_stream(&entry) ? SG_NAV_DOT + 12 : 0);
            if (w < 1) w = 1;
            grid_text(canvas, sg_tile(r), pass, tx, sg_row_y(r) - off + (pass ? LIST_SUB_Y : LIST_TITLE_Y), w,
                      pass ? LIST_SUB_H : LIST_TITLE_H, 0);
            if (!pass && sg_entry_stream(&entry)) {
                int x = row_end - SG_NAV_DOT - 5;
                sg_nav_dot_paint(canvas, x, sg_row_y(r) - off + (ROW - SG_NAV_DOT) / 2);
            }
        }
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
    {
        sg_entry_t entry;
        sg_get_entry((unsigned)(t->album - 1), &entry);
        if (entry.server && sb_library_cover_url(entry.server, url, sizeof url) > 0) {
            grid_art_url(&sg.g, t, url);
            return;
        }
        if (entry.server)
            t->ckey = cc_cover_key(sg.albums, cc_key_of(sg_entry_artist(&entry), sg_entry_album(&entry)),
                                   sg_entry_album(&entry), url);
        else
            t->ckey = cc_cover_key(sg.albums, t->ckey, cc_str(entry.local, REC_ALBUM), url);
    }
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
            {
                sg_entry_t entry;
                sg_get_entry((unsigned)a, &entry);
                if (entry.local && cc_build_add(cc_str(entry.local, REC_PATH), key) < 0) goto go;
            }
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

static const char *sg_name_text(void) {
    if (sg.nav_overlay && sg.nav_filter != SB_LIBRARY_FILTER_NONE) return sg.nav_name;
    return sg.key ? TR(sg.key) : sg.name;
} /* a list's title */

/* The song count under the last row: "25 songs" (the key by n == 1, the number where the translation has its %d). */
static void sg_foot_text(void) {
    char buf[96], count[48], duration[40];
    unsigned i, total = 0;
    int known = 1;
    sg_fmt(count, sizeof count, TR(sg.count == 1 ? "%d song" : "%d songs"), (int)sg.count);
    if (sg.nav_overlay && sg.nav_filter == SB_LIBRARY_FILTER_ALBUM && sg.count) {
        dur_acquire();
        for (i = 0; i < sg.count; ++i) {
            sg_entry_t entry;
            int seconds;
            unsigned size;
            sg_get_entry(i, &entry);
            if (entry.server && entry.server->duration) {
                seconds = (int)entry.server->duration;
            } else if (entry.local) {
                seconds = dur_song(entry.local, &size);
                if (seconds <= 0 && entry.duration) seconds = (int)entry.duration;
            } else {
                seconds = entry.duration ? (int)entry.duration : 0;
            }
            if (seconds <= 0) {
                known = 0;
                break;
            }
            total += (unsigned)seconds;
        }
        dur_release();
        if (known) {
            dur_text(duration, sizeof duration, total);
            snprintf(buf, sizeof buf, "%s \xc2\xb7 %s", count, duration);
        } else
            snprintf(buf, sizeof buf, "%s", count);
    } else
        snprintf(buf, sizeof buf, "%s", count);
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
        az_fit(sg.title, sg.nav_overlay && sg.nav_filter != SB_LIBRARY_FILTER_NONE ? sg.nav_name
                         : sg_lib()                                                ? TR("Songs")
                                                                                   : sg_name_text());
        return;
    }
    sg_fmt(buf, sizeof buf, TR("%d Selected"), (int)sg.nsel);
    widget_set_text_utf8(sg.title, buf);
}

/* The rail's widget: centred on the list the select bar leaves (docs/modules/songs.md). */
static void sg_rail_fit(void) { az_rail_fit(&sg.al, GRID_VIEW_H - sg_pad()); }

static void sg_ticks(void) {
    int i;
    for (i = 0; i < SG_SORT_ROWS; ++i) widget_set_visible(sg.tick[i], i == sg.sort, 0);
}

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

static const char *sg_entry_filename(const sg_entry_t *entry, char *out, unsigned cap) {
    if (entry->server) {
        if (sb_track_filename(out, cap, entry->server) >= 0) return out;
        return sg_entry_title(entry);
    }
    return cc_str(entry->local, REC_NAME);
}

static const char *sg_entry_suffix(const sg_entry_t *entry) {
    const char *path, *dot;
    if (entry->server) return entry->server->suffix;
    path = cc_str(entry->local, REC_PATH);
    dot = strrchr(path, '.');
    return dot ? dot + 1 : "";
}

static unsigned sg_entry_created(const sg_entry_t *entry) {
    return entry->server ? entry->server->created : (unsigned)I(entry->local, REC_TIME_CREATE);
}

static int sg_entry_cmp(const sg_entry_t *a, const sg_entry_t *b) {
    int d = 0;
    if (sg.nav_filter == SB_LIBRARY_FILTER_ALBUM || sg.nav_filter == SB_LIBRARY_FILTER_ARTIST ||
        sg.nav_filter == SB_LIBRARY_FILTER_ALBUM_ARTIST) {
        if (sg.nav_filter != SB_LIBRARY_FILTER_ALBUM) d = cc_key_cmp(sg_entry_album(a), sg_entry_album(b));
        if (!d) {
            unsigned ad = a->server ? a->server->disc : (unsigned)I(a->local, REC_DISC);
            unsigned bd = b->server ? b->server->disc : (unsigned)I(b->local, REC_DISC);
            unsigned at = a->server ? a->server->track : (unsigned)I(a->local, REC_TRACK);
            unsigned bt = b->server ? b->server->track : (unsigned)I(b->local, REC_TRACK);
            d = ad < bd ? -1 : ad > bd ? 1 : at < bt ? -1 : at > bt ? 1 : 0;
        }
        if (!d) d = cc_key_cmp(sg_entry_title(a), sg_entry_title(b));
    } else if (sg.sort == 1) {
        char an[SB_TEXT + 16], bn[SB_TEXT + 16];
        d = cc_key_cmp(sg_entry_filename(a, an, sizeof an), sg_entry_filename(b, bn, sizeof bn));
    } else if (sg.sort == 2) {
        d = cc_key_cmp(sg_entry_suffix(a), sg_entry_suffix(b));
    } else if (sg.sort == 3 || sg.sort == 4) {
        unsigned ac = sg_entry_created(a), bc = sg_entry_created(b);
        d = ac < bc ? -1 : ac > bc ? 1 : 0;
        if (sg.sort == 3) d = -d;
    } else {
        d = cc_key_cmp(sg_entry_title(a), sg_entry_title(b));
        if (!d) d = cc_key_cmp(sg_entry_artist(a), sg_entry_artist(b));
        if (!d) d = cc_key_cmp(sg_entry_album(a), sg_entry_album(b));
    }
    if (d) return d;
    if (!!a->local != !!b->local) return a->local ? -1 : 1;
    return a->order < b->order ? -1 : a->order > b->order;
}

static void sg_entry_swap(unsigned a, unsigned b) {
    sg_entry_t *x = &sg.entry[a], *y = &sg.entry[b];
    void *local = x->local;
    const sb_song_t *server = x->server;
    unsigned order = x->order, local_index = x->local_index;
    unsigned char source = x->source;
    unsigned short duration = x->duration;
    x->local = y->local, x->server = y->server, x->order = y->order, x->local_index = y->local_index,
    x->source = y->source, x->duration = y->duration;
    y->local = local, y->server = server, y->order = order, y->local_index = local_index, y->source = source,
    y->duration = duration;
}

static void sg_entry_sift(unsigned root, unsigned end) {
    unsigned child;
    while ((child = root * 2u + 1u) < end) {
        if (child + 1u < end && sg_entry_cmp(&sg.entry[child], &sg.entry[child + 1u]) < 0) ++child;
        if (sg_entry_cmp(&sg.entry[root], &sg.entry[child]) >= 0) return;
        sg_entry_swap(root, child);
        root = child;
    }
}

static void sg_entry_sort(unsigned count) {
    unsigned i;
    for (i = count / 2u; i > 0; --i) sg_entry_sift(i - 1u, count);
    for (i = count; i > 1u; --i) {
        sg_entry_swap(0, i - 1u);
        sg_entry_sift(0, i - 1u);
    }
}

static unsigned sg_entry_signature(const sg_entry_t *entry, unsigned key, unsigned rank) {
    unsigned h = 2166136261u ^ key;
    const char *s[3] = {sg_entry_title(entry), sg_entry_subtitle(entry), entry->server ? entry->server->cover : ""};
    unsigned k;
    h = (h ^ rank ^ entry->source) * 16777619u;
    for (k = 0; k < 3; ++k) {
        const unsigned char *p = (const unsigned char *)s[k];
        for (; *p; ++p) h = (h ^ *p) * 16777619u;
        h = (h ^ 0x100u) * 16777619u;
    }
    return h;
}

static void sg_overlay_finish(void) {
    song_t *index;
    unsigned char *selection;
    unsigned i;
    int at = sg_off();
    if (sg.nav_timer) timer_remove(sg.nav_timer);
    sg.nav_timer = 0;
    index = sg.entry_count ? (song_t *)calloc(sg.entry_count, sizeof *index) : (song_t *)0;
    selection = sg.entry_count ? (unsigned char *)calloc((sg.entry_count + 7) / 8, 1) : (unsigned char *)0;
    if (sg.entry_count && (!index || !selection)) {
        free(index);
        free(selection);
        sg.entry_count = sg.nav_local_visible;
        sg.nav_scanning = 0;
        sb_library_index_close(&sg.nav_index);
        sb_library_downloads_close(&sg.nav_downloads);
        free(sg.nav_match);
        sg.nav_match = (sg_match_slot_t *)0, sg.nav_match_cap = 0;
        widget_set_tr_text(sg.foot, "Navidrome library could not be loaded");
        return;
    }
    if (sg.entry_count > 1) sg_entry_sort(sg.entry_count);
    for (i = 0; i < sg.entry_count; ++i) {
        sg_entry_t *entry = &sg.entry[i];
        unsigned key =
            entry->local ? cc_album_key(entry->local) : cc_key_of(sg_entry_artist(entry), sg_entry_album(entry));
        if (entry->local && !entry->duration)
            entry->duration = sg_local_server_duration(entry->local, entry->local_index);
        index[i].key = key;
        index[i].letter = sg_entry_rank(entry);
        sg_set_sig(&index[i], sg_entry_signature(entry, key, index[i].letter));
    }
    free(sg.idx);
    free(sg.sel);
    sg.idx = index, sg.sel = selection;
    sg.count = sg.entry_count;
    sg.al.count = (int)sg.count;
    sg.al.nsec = 0;
    if (sg.count && sg.nav_filter == SB_LIBRARY_FILTER_NONE && sg.sort == 0)
        az_sections(&sg.al, &sg.idx[0].letter, sizeof(song_t));
    sg.nav_scanning = 0;
    sb_library_downloads_close(&sg.nav_downloads);
    free(sg.nav_match);
    sg.nav_match = (sg_match_slot_t *)0, sg.nav_match_cap = 0;
    grid_drop(&sg.g);
    grid_placeholder(&sg.g);
    sg_show(sg.view, sg.count != 0);
    sg_show(sg.status, sg.count == 0);
    if (!sg.count)
        widget_set_tr_text(sg.status,
                           sg.nav_filter == SB_LIBRARY_FILTER_NONE ? SB_LIBRARY_EMPTY_HINT : SB_LIBRARY_NO_MATCH_HINT);
    sg_size();
    sg_foot_text();
    widget_set_prop_int(sg.sv, "yoffset", at < 0 ? 0 : at > sg_max_scroll() ? sg_max_scroll() : at);
    sg_rail_fit();
    sg_head();
    sg_title_update();
    sg_redraw();
    sg_kick();
    sg_build_later();
}

#define SG_NAV_BATCH 512
static void sg_nav_progress(void) {
    char text[80];
    if (sg.count) {
        snprintf(text, sizeof text, "Loading %u/%u", sg.nav_cursor, sg.nav_total);
        widget_set_text_utf8(sg.foot, text);
    } else {
        snprintf(text, sizeof text, "Loading Navidrome\n%u/%u", sg.nav_cursor, sg.nav_total);
        widget_set_text_utf8(sg.status, text);
    }
}

static int sg_nav_scan_step(void) {
    unsigned end;
    if (!sg.nav_scanning || !sg.nav_index.songs) return 0;
    end = sg.nav_cursor + SG_NAV_BATCH;
    if (end < sg.nav_cursor || end > sg.nav_total) end = sg.nav_total;
    while (sg.nav_cursor < end) {
        unsigned offset = sg.nav_cursor++;
        const sb_song_t *song = offset < sg.nav_index.count
                                    ? &sg.nav_index.songs[offset]
                                    : &sg.nav_index.songs[sg.nav_index.count + offset - sg.nav_index.count];
        char path[320];
        int offline = 0, dsd = sb_library_is_dsd(song);
        sg_match_slot_t *local_copy;
        sg_entry_t *entry;
        if (!song->id[0] || !sb_library_matches(song, sg.nav_filter, sg.nav_name, sg.nav_artist)) continue;
        local_copy = sg_remote_local_copy(song);
        if (local_copy) {
            if (song->duration && !local_copy->duration)
                local_copy->duration = (unsigned short)(song->duration > 65535u ? 65535u : song->duration);
            /* A local duplicate belongs in this server category even when its
             * SD metadata omits or disagrees on genre/composer/album artist. */
            if (!local_copy->visible && sg.entry_count < sg.entry_cap) {
                unsigned local_index = local_copy->local_index;
                entry = &sg.entry[sg.entry_count++];
                memset(entry, 0, sizeof *entry);
                entry->local = deque_at(sg.list, local_index);
                entry->local_index = local_index;
                entry->source = SB_LIBRARY_LOCAL;
                entry->order = local_index;
                entry->duration = local_copy->duration;
                local_copy->visible = 1;
                ++sg.nav_local_visible;
            }
            continue;
        }
        if (sb_library_downloads_contains(&sg.nav_downloads, song) &&
            sb_library_offline_path(song, path, sizeof path) == 1)
            offline = 1;
        if (dsd && !offline) continue;
        if (sg.entry_count >= sg.entry_cap) continue;
        entry = &sg.entry[sg.entry_count++];
        memset(entry, 0, sizeof *entry);
        entry->server = song;
        entry->source = offline ? SB_LIBRARY_OFFLINE : SB_LIBRARY_STREAM;
        entry->order = offset;
        entry->duration = (unsigned short)(song->duration > 65535u ? 65535u : song->duration);
    }
    if (sg.nav_cursor >= sg.nav_total) {
        if (sg.nav_dur_held) dur_release(), sg.nav_dur_held = 0;
        sg_overlay_finish();
        return 0;
    }
    sg_nav_progress();
    return 1;
}

static int sg_on_nav_scan(const void *unused) {
    (void)unused;
    sg.nav_timer = 0;
    if (!sg.nav_scanning) return RET_OK;
    if (!sg.nav_index.songs) {
        sg.entry_count = sg.nav_local_visible;
        if (sg.nav_dur_held) dur_release(), sg.nav_dur_held = 0;
        sg.nav_scanning = 0;
        sg_overlay_finish();
        if (!sg.count) widget_set_tr_text(sg.status, "Navidrome index could not be read");
        return RET_OK;
    }
    if (sg_nav_scan_step()) sg_nav_schedule();
    return RET_OK;
}

static void sg_nav_schedule(void) {
    if (!sg.nav_scanning || sg.nav_timer || !sg.view) return;
    sg.nav_timer = timer_add(sg_on_nav_scan, (void *)0, SG_MORE_MS);
    if (!sg.nav_timer) {
        /* Keep local entries usable and avoid leaving a permanent loading page
         * if the UI has no timer slot available. */
        sg.entry_count = sg.nav_local_visible;
        if (sg.nav_dur_held) dur_release(), sg.nav_dur_held = 0;
        sg.nav_scanning = 0;
        sg_overlay_finish();
        if (!sg.count) widget_set_tr_text(sg.status, "Navidrome library scan could not start");
    }
}

/* If the stock query replaces the local deque while this virtual page is open,
 * its local record pointers cannot be read safely. Restart this view as a
 * server-only overlay; that keeps the page usable and lets the scanner rebuild
 * the remote/offline rows without touching stale local records. */
static void sg_nav_remote_fallback(void) {
    int at = sg_off();
    if (!sg.nav_overlay) return;
    if (sg.nav_timer) timer_remove(sg.nav_timer);
    sg.nav_timer = 0;
    sg_build_end();
    if (sg.nav_dur_held) dur_release(), sg.nav_dur_held = 0;
    free(sg.nav_match);
    sg.nav_match = (sg_match_slot_t *)0, sg.nav_match_cap = 0;
    sg.count = sg.entry_count = sg.nav_local_visible = 0;
    sg.al.count = 0, sg.al.nsec = 0;
    if (sg.select) sg_select(0);
    free(sg.idx), free(sg.sel);
    sg.idx = (song_t *)0, sg.sel = (unsigned char *)0;
    sg.nsel = 0;
    sg.local_count = 0, sg.list = sg.first = (void *)0;
    sg.nav_cursor = 0;
    sg.nav_total = sg.nav_index.count + sg.nav_index.dsd_count;
    sb_library_downloads_close(&sg.nav_downloads);
    if (sg.nav_index.songs) (void)sb_library_downloads_open(&sg.nav_downloads);
    grid_drop(&sg.g);
    grid_placeholder(&sg.g);
    sg_size();
    sg_show(sg.view, 0);
    sg_show(sg.status, 1);
    if (!sg.nav_index.songs || !sg.nav_total) {
        sg.nav_scanning = 0;
        widget_set_tr_text(sg.status, SB_LIBRARY_EMPTY_HINT);
        return;
    }
    sg.nav_scanning = 1;
    dur_acquire(), sg.nav_dur_held = 1;
    sg_foot_text();
    sg_ticks();
    sg_rail_fit();
    sg_head();
    sg_title_update();
    widget_set_prop_int(sg.sv, "yoffset", at < 0 ? 0 : at > sg_max_scroll() ? sg_max_scroll() : at);
    sg_nav_progress();
    sg_redraw();
    sg_nav_schedule();
}

static void sg_overlay_release(void) {
    if (sg.nav_timer) timer_remove(sg.nav_timer);
    sg.nav_timer = 0;
    if (sg.nav_dur_held) dur_release(), sg.nav_dur_held = 0;
    sb_library_index_close(&sg.nav_index);
    sb_library_downloads_close(&sg.nav_downloads);
    free(sg.nav_match);
    free(sg.entry);
    sg.nav_match = (sg_match_slot_t *)0, sg.nav_match_cap = 0;
    sg.entry = (sg_entry_t *)0, sg.entry_count = sg.entry_cap = 0;
    sg.nav_cursor = sg.nav_total = sg.nav_local_visible = 0;
    sg.nav_scanning = 0;
}

static void sg_overlay_start(void *list, int at) {
    unsigned i, local_count = list ? deque_size(list) : 0;
    unsigned index_count = 0, cap = 1, target = 0;
    int have_index = sb_library_index_open(&sg.nav_index) == 0;
    if (have_index) index_count = sg.nav_index.count + sg.nav_index.dsd_count;
    sg.local_count = local_count;
    sg.list = list;
    sg.first = local_count ? deque_at(list, 0) : (void *)0;
    sg.nav_cursor = 0, sg.nav_total = index_count;
    if (have_index) (void)sb_library_downloads_open(&sg.nav_downloads);
    if (local_count > (unsigned)-1 - index_count || local_count + index_count > (unsigned)-1 / sizeof *sg.entry) {
        sb_library_index_close(&sg.nav_index);
        sb_library_downloads_close(&sg.nav_downloads);
        have_index = 0, index_count = 0, sg.nav_total = 0;
    }
    sg.entry_cap = local_count + index_count;
    if (sg.entry_cap) sg.entry = (sg_entry_t *)calloc(sg.entry_cap, sizeof *sg.entry);
    if (sg.entry_cap && !sg.entry) {
        sg_overlay_release();
        sg_show(sg.view, 0);
        sg_show(sg.status, 1);
        widget_set_tr_text(sg.status, "Not enough memory for library");
        sg_size();
        return;
    }
    if (have_index && local_count && local_count <= 0x20000000u) {
        target = local_count * 2u;
        while (cap < target && cap < 0x80000000u) cap <<= 1;
        if (cap >= target) {
            sg.nav_match = (sg_match_slot_t *)calloc(cap, sizeof *sg.nav_match);
            if (sg.nav_match) sg.nav_match_cap = cap;
        }
        if (!sg.nav_match) {
            sb_library_index_close(&sg.nav_index);
            sb_library_downloads_close(&sg.nav_downloads);
            have_index = 0, index_count = 0, sg.nav_total = 0;
        }
    }
    for (i = 0; i < local_count; ++i) {
        void *record = deque_at(list, i);
        sg_entry_t *entry;
        int visible = sg_local_matches(record);
        if (sg.nav_match && sg.nav_match_cap) sg_match_add(record, i, visible);
        if (!visible || sg.entry_count >= sg.entry_cap) continue;
        entry = &sg.entry[sg.entry_count++];
        entry->local = record;
        entry->local_index = i;
        entry->source = SB_LIBRARY_LOCAL;
        entry->order = i;
    }
    sg.nav_local_visible = sg.entry_count;
    sg.count = sg.entry_count;
    sg.al.count = (int)sg.count;
    sg.idx = sg.count ? (song_t *)calloc(sg.count, sizeof *sg.idx) : (song_t *)0;
    sg.sel = sg.count ? (unsigned char *)calloc((sg.count + 7) / 8, 1) : (unsigned char *)0;
    if (sg.count && (!sg.idx || !sg.sel)) {
        free(sg.idx), free(sg.sel);
        sg.idx = (song_t *)0, sg.sel = (unsigned char *)0;
        sg.count = sg.al.count = 0;
        sg_overlay_release();
        sg_show(sg.view, 0);
        sg_show(sg.status, 1);
        widget_set_tr_text(sg.status, "Not enough memory for library");
        sg_size();
        return;
    }
    for (i = 0; i < sg.count; ++i) {
        unsigned key = cc_album_key(sg.entry[i].local);
        sg.idx[i].key = key;
        sg.idx[i].letter = sg_entry_rank(&sg.entry[i]);
        sg_set_sig(&sg.idx[i], sg_entry_signature(&sg.entry[i], key, sg.idx[i].letter));
    }
    if (sg.count && sg.sort == 0 && sg.nav_filter == SB_LIBRARY_FILTER_NONE)
        az_sections(&sg.al, &sg.idx[0].letter, sizeof(song_t));
    sg_show(sg.view, sg.count != 0);
    sg_show(sg.status, sg.count == 0);
    if (!sg.count) widget_set_tr_text(sg.status, sg.nav_total ? SB_LIBRARY_LOADING_HINT : SB_LIBRARY_EMPTY_HINT);
    sg_size();
    sg_foot_text();
    widget_set_prop_int(sg.sv, "yoffset", at < 0 ? 0 : at > sg_max_scroll() ? sg_max_scroll() : at);
    sg.dir = 1, sg.seen = sg_off(), sg.build_at = sg_first();
    sg_ticks();
    sg_rail_fit();
    sg_head();
    sg_title_update();
    sg_redraw();
    if (have_index && sg.nav_total) {
        sg.nav_scanning = 1;
        dur_acquire(), sg.nav_dur_held = 1;
        sg_nav_progress();
        sg_nav_schedule();
    } else
        sg_overlay_finish();
    sg_build_later();
}

static void sg_load(int keep) {
    unsigned i;
    int at = keep ? sg_off() : 0, same = 0;
    void *list = (void *)0;
    song_t *old = sg.idx;
    unsigned old_n = sg.count;
    if (sg.nav_overlay) {
        free(old);
        old = (song_t *)0;
        sg_overlay_release();
    }
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
    if (sg.sort < 0 || sg.sort >= SG_SORT_ROWS) sg.sort = 0;
    if (sg_query() > 0) list = *(void **)PDEQ_SHOWLIST;
    if (sg.nav_overlay) {
        grid_drop(&sg.g);
        grid_placeholder(&sg.g);
        sg.tend = sg_edge();
        sg_overlay_start(list, at);
        return;
    }
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
        if (sg_lib() && sg.sort == 0) az_sections(&sg.al, &sg.idx[0].letter, sizeof(song_t));
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
        widget_set_tr_text(sg.status, list && deque_size(list) ? "Not enough memory"
                                      : sg_lib()               ? SB_LIBRARY_EMPTY_HINT
                                                               : "No songs");
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
    sg_ticks();
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
    if (sg.view && !sg.rv && sg.g.tiles && !sg_valid() && pod_is_top(sg.win)) {
        if (sg.nav_overlay)
            sg_nav_remote_fallback();
        else
            sg_load(1);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Recently Added's toggle between the songs and the albums (docs/modules/recent-albums.md)
 */

/* The toggle shows the glyph of the view a tap switches to. */
static void rv_glyph(void) {
    const char *icon = sg.rv ? "pod_nav_list" : "pod_nav_grid";
    if (!sg.btn_view) return;
    widget_set_prop_str(sg.btn_view, "style:normal:icon", icon);
    widget_set_prop_str(sg.btn_view, "style:over:icon", icon);
    widget_set_prop_str(sg.btn_view, "style:pressed:icon", sg.rv ? "pod_nav_list_down" : "pod_nav_grid_down");
}

/* The widgets of the view: the albums have no Play / Shuffle pills, no song count and no Select; Search takes Select's slot (Search 168 | toggle 214 | Now Playing). */
static void rv_ui(void) {
    sg_show(sg.btn_play, !sg.rv);
    sg_show(sg.btn_shuffle, !sg.rv);
    if (sg.foot) widget_set_visible(sg.foot, !sg.rv, 0); /* (an insensitive label: shown, never a touch target) */
    sg_show(sg.btn_select, !sg.rv);
    widget_move(sg.btn_search, sg.rv ? NAV_CF_X : NAV_SEARCH_X, 0);
    rv_glyph();
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

/* The navbar toggle: the other view, in place, and the choice saved. */
static int sg_on_view(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!sg_recent() || sg.select || sg.menu) return RET_OK;
    if (sg.rv)
        rv_leave();
    else if (!rv_enter())
        return RET_OK;
    home_write_atomic(RECENTADD_VIEW_FILE, RECENTADD_VIEW_TMP, sg.rv ? "1\n" : "0\n");
    return RET_OK;
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
    if (sg.nav_overlay) {
        unsigned start = 0, n, i;
        sb_library_queue_entry_t *queue;
        if (!sg.count || !sg.entry) return;
        if (how == SO_KEEP) {
            if (at < 0 || (unsigned)at >= sg.count) return;
            start = (unsigned)at;
        } else if (how == SO_SHUFFLE && sg.count > SB_QUEUE_MAX)
            start = pod_rand(sg.count - SB_QUEUE_MAX + 1u);
        n = sg.count - start;
        if (n > SB_QUEUE_MAX) n = SB_QUEUE_MAX;
        queue = (sb_library_queue_entry_t *)calloc(n, sizeof *queue);
        if (!queue) {
            pod_toast("Could not prepare library queue");
            return;
        }
        for (i = 0; i < n; ++i) {
            sg_entry_t *entry = &sg.entry[start + i];
            queue[i].local_record = entry->local;
            queue[i].server_song = entry->server;
            queue[i].server_index = entry->order;
            queue[i].source = entry->source;
        }
        (void)sb_library_play_queue(queue, n, how == SO_KEEP ? 0 : at, how);
        free(queue);
        return;
    }
    if (at >= 0 && (unsigned)at < sg.count && sg.list && sb_library_play_recent(deque_at(sg.list, (unsigned)at)) == 0)
        return;
    so_play(sg.cls, sg.list, at, how, sg_open_player);
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
    if (sg.nav_overlay)
        sg_play_at(-1, SO_SHUFFLE);
    else if (sg_lib())
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
    void *nav[4];
    if (on == sg.select) return;
    sg.select = on;
    sg.nsel = 0;
    if (sg.sel) memset(sg.sel, 0, (sg.count + 7) / 8);
    sg.press = sg.down = 0;
    nav[0] = sg.btn_search, nav[1] = sg.btn_sort, nav[2] = sg.btn_select, nav[3] = sg.np;
    for (i = 0; i < 4; ++i)
        sg_show(nav[i],
                !on && (i != 1 || sg_lib()) &&
                    (i != 0 || (!sg_genre() &&
                                !sg_artist()))); /* (a list has no Sort, a genre's songs and an artist's no Search) */
    if (sg.btn_cf) sg_show(sg.btn_cf, !on && sg_artist());
    if (sg_recent()) sg_show(sg.btn_view, !on);
    sg_show(sg.btn_selall, on);
    sg_show(sg.bar, on);
    widget_set_sensitive(sg.btn_play, !on); /* the pills stay in the content, dim and dead (their disabled style) */
    widget_set_sensitive(sg.btn_shuffle, !on);
    widget_resize(sg.title, (on ? SG_SELALL_X : sg_search_x()) - NAV_TITLE_X, 22);
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

static unsigned char *sg_stock_selection(unsigned *selected) {
    unsigned i, count = 0;
    unsigned char *bits;
    if (selected) *selected = 0;
    if (!sg.nav_overlay) return (unsigned char *)0;
    bits = sg.local_count ? (unsigned char *)calloc((sg.local_count + 7) / 8, 1) : (unsigned char *)0;
    if (sg.local_count && !bits) return (unsigned char *)0;
    for (i = 0; i < sg.count; ++i) {
        sg_entry_t entry;
        if (!sg_is_sel((int)i)) continue;
        sg_get_entry(i, &entry);
        if (entry.source != SB_LIBRARY_LOCAL || !entry.local || entry.local_index >= sg.local_count) continue;
        bits[entry.local_index >> 3] |= (unsigned char)(1u << (entry.local_index & 7));
        ++count;
    }
    if (selected) *selected = count;
    return bits;
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
    unsigned char *bits;
    unsigned selected;
    int deleted;
    (void)ctx;
    (void)e;
    if (!sg.select) return RET_OK;
    if (sg.nav_overlay) {
        bits = sg_stock_selection(&selected);
        if (sg.local_count && !bits) {
            pod_toast("Not enough memory");
            return RET_OK;
        }
        if (!selected) {
            free(bits);
            pod_toast("Select a local song");
            return RET_OK;
        }
        deleted = so_delete(CLASS_ALL_SONGS, sg.list, sg.local_count, bits, selected, sg_stock_valid());
        free(bits);
    } else
        deleted = so_delete(sg.cls, sg.list, sg.count, sg.sel, sg.nsel, sg_valid());
    if (deleted) {
        sg_select(0);
        sg_load(1);
    }
    return RET_OK;
}

/* Add to playlist: the stock playlist picker over this page; the title the picker may overwrite and the browsing class it sets are put back when this window comes to the front. */
static int sg_on_add(void *ctx, void *e) {
    int r;
    unsigned char *bits;
    unsigned selected;
    (void)ctx;
    (void)e;
    if (!sg.select) return RET_OK;
    if (sg.nav_overlay) {
        bits = sg_stock_selection(&selected);
        if (sg.local_count && !bits) {
            pod_toast("Not enough memory");
            return RET_OK;
        }
        if (!selected) {
            free(bits);
            pod_toast("Select a local song");
            return RET_OK;
        }
        r = so_add(CLASS_ALL_SONGS, sg.local_count, bits, selected, sg_stock_valid(), sg.title_save, &sg.picker);
        free(bits);
    } else
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

static int sg_on_select(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg.view && sg.count && !sg.menu && !sg.rv) sg_select(1);
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
    if (pt[0] < x0 || pt[0] >= x0 + RM_MORE_W) return 0;
    if (sg.nav_overlay && sg.down > 0 && sg.down - 1 < (int)sg.entry_count &&
        sg.entry[sg.down - 1].source != SB_LIBRARY_LOCAL)
        return 0;
    return 1;
}

/* Add to Playlist for one row (the menu's third row): the page's picker with a selection of that row alone. */
static void sg_add_one(int row) {
    int r;
    unsigned char *bits;
    unsigned selected;
    if (!sg.sel || row < 0 || row >= (int)sg.count) return;
    if (sg.nav_overlay) {
        sg_entry_t entry;
        sg_get_entry((unsigned)row, &entry);
        if (entry.source != SB_LIBRARY_LOCAL || entry.local_index >= sg.local_count) return;
        sg.sel[row >> 3] |= (unsigned char)(1 << (row & 7));
        bits = sg_stock_selection(&selected);
        sg.sel[row >> 3] &= (unsigned char)~(1 << (row & 7));
        if (sg.local_count && !bits) {
            pod_toast("Not enough memory");
            return;
        }
        r = so_add(CLASS_ALL_SONGS, sg.local_count, bits, selected, sg_stock_valid(), sg.title_save, &sg.picker);
        free(bits);
        if (r < 0) sg_load(1);
        return;
    }
    sg.sel[row >> 3] |= (unsigned char)(1 << (row & 7));
    r = so_add(sg.cls, sg.count, sg.sel, 1, sg_valid(), sg.title_save, &sg.picker);
    memset(sg.sel, 0, (sg.count + 7) / 8); /* (the picker and the stock vector have their own copies) */
    if (r < 0) sg_load(1);
}

static void sg_open_menu(int a) {
    sg_entry_t entry;
    sg_get_entry((unsigned)a, &entry);
    if (!sg_valid()) {
        sg_load(1);
        return;
    }
    if (!entry.local || entry.source != SB_LIBRARY_LOCAL) return;
    rowmenu_open(&sg.rm, a, entry.local, sg_add_one);
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
 * The sort card: the stock sort dialog's five labels under the Sort button; a row sets the stock order (@0x47d114: sort_flag and [SYSSET] SORTSELECT), the list is read again
 */
static void sg_menu(int on) {
    sg.menu = on;
    if (on) sg_ticks();
    sg_show(sg.scrim, on);
    sg_show(sg.card, on);
}

static int sg_on_sort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg.view && !sg.select && sg_lib()) sg_menu(!sg.menu);
    return RET_OK;
}

static int sg_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    sg_menu(0);
    return RET_OK;
}

static int sg_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx;
    (void)e;
    sg_menu(0);
    if (!sg.view || k < 0 || k >= SG_SORT_ROWS || k == *(int *)SORT_FLAG) return RET_OK;
    *(int *)SORT_FLAG = k;
    write_int_config(k, "SYSSET", "SORTSELECT");
    sg_load(0);
    return RET_OK;
}

/* Search: our keyboard, then our results page (patch/search.c, docs/modules/search.md). Its queries leave their list in *pdeq_showlist, which makes this page read it again when it is
 * back. Where ours will not open (a results page is already under this one, or no keyboard asset) the stock page (@0x52704c: navigator_to("search_page"), nothing set first). */
static int sg_on_search(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sg.view && !sg.select && !sg.menu && search_open() < 0)
        navigator_to_with_context("search_page", (const void *)0);
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
    } else if (!sg.rv && (!sg_valid() || sg_changes())) { /* (the album view reads no stock list: nothing is stale) */
        if (sg.nav_overlay && !sg_valid())
            sg_nav_remote_fallback();
        else
            sg_load(1); /* (a list read again whose rows are the same keeps its tiles: sg_load) */
    }
    sg_build_later();
    sg_nav_schedule();
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
    sg_overlay_release();
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
    if (sg.nav_timer) timer_remove(sg.nav_timer);
    sg.more_timer = sg.stale_timer = sg.nav_timer = 0;
    memcpy(sg_under, &sg, sizeof sg);
    memset(&sg, 0, sizeof sg);
    return 0;
}

/* The page listing class cls (pl_id: a playlist's id; key: the title's key, or 0 for name). 0 once the page is up, -1 if the window could not open, -2 if the
 * asset is not ours (the page is left again). */
static int sg_open_page(int cls, int pl_id, const char *key, const char *name) {
    static const char *const ITEMS[SG_SORT_ROWS] = {"sg_item0", "sg_item1", "sg_item2", "sg_item3", "sg_item4"};
    static const char *const TICKS[SG_SORT_ROWS] = {"sg_tick0", "sg_tick1", "sg_tick2", "sg_tick3", "sg_tick4"};
    int i;
    if (sg.win && (cls != CLASS_PLAYLIST_SONGS || sg_stack() == -1)) return -1;
    memset(&sg, 0, sizeof sg);
    sg.cls = cls, sg.pl_id = pl_id, sg.key = key;
    if (cls == CLASS_ALL_SONGS && sg_nav_request.active) {
        sg.nav_overlay = 1;
        sg.nav_filter = sg_nav_request.filter;
        memcpy(sg.nav_name, sg_nav_request.name, sizeof sg.nav_name);
        memcpy(sg.nav_artist, sg_nav_request.artist, sizeof sg.nav_artist);
    }
    sg_nav_request.active = 0;
    if (cls == CLASS_ARTIST_SONGS)
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
    sg.btn_search = pod_bind(sg.win, "btn_search", sg_on_search, (void *)0);
    sg.btn_sort = pod_bind(sg.win, "btn_sort", sg_on_sort, (void *)0);
    sg.btn_cf = pod_bind(sg.win, "btn_coverflow", sg_on_cf, (void *)0); /* optional */
    sg.btn_select = pod_bind(sg.win, "btn_select", sg_on_select, (void *)0);
    sg.btn_view = pod_bind(sg.win, "btn_albumview", sg_on_view, (void *)0); /* optional: Recently Added's toggle */
    sg.st_gtitle = widget_lookup(sg.win, "label_grid_title", 1); /* optional: the album view's text styles */
    sg.st_gsub = widget_lookup(sg.win, "label_grid_sub", 1);
    sg.btn_selall = pod_bind(sg.win, "btn_selall", sg_on_selall, (void *)0);
    sg.btn_play = pod_bind(sg.win, "btn_play", sg_on_play, (void *)0);
    sg.btn_shuffle = pod_bind(sg.win, "btn_shuffle", sg_on_shuffle, (void *)0);
    sg.btn_add = pod_bind(sg.win, "sg_add", sg_on_add, (void *)0);
    sg.btn_del = pod_bind(sg.win, "sg_del", sg_on_delete, (void *)0);
    sg.scrim = pod_bind(sg.win, "sg_scrim", sg_on_scrim, (void *)0);
    sg.card = widget_lookup(sg.win, "sg_card", 1);
    sg.title = widget_lookup(sg.win, "label_title", 1);
    sg.fade = widget_lookup(sg.win, "img_nb_fade", 1); /* optional */
    sg.view = widget_lookup(sg.win, "view_grid", 1);
    sg.sv = widget_lookup(sg.win, "songs_scrollview", 1);
    sg.status = widget_lookup(sg.win, "label_status", 1);
    if (sg.status) label_set_line_wrap(sg.status, 1), widget_set_prop_bool(sg.status, "word_wrap", 1);
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
    if (!sg.foot || !sg.back || !sg.np || !sg.btn_search || !sg.btn_sort || !sg.btn_select || !sg.btn_selall ||
        !sg.btn_play || !sg.btn_shuffle || !sg.btn_add || !sg.btn_del || !sg.scrim || !sg.card || !sg.title ||
        !sg.view || !sg.sv || !sg.status || !sg.st_title || !sg.st_sub || !sg.al.st_hdr || !sg.al.st_rail ||
        !sg.al.st_rail_on || !sg.al.rail || !sg.al.bubble || !sg.al.bubble_letter || !sg.bar) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    for (i = 0; i < SG_SORT_ROWS; ++i) {
        sg.tick[i] = widget_lookup(sg.win, TICKS[i], 1);
        if (!sg.tick[i] || !pod_bind(sg.win, ITEMS[i], sg_on_item, (void *)(long)i)) {
            navigator_back();
            return -2;
        }
    }
    sg_menu(0);
    rowmenu_bind(&sg.rm, sg.win); /* the rows' "..." menu (optional: no widgets or the kill switch means no "...") */
    if (!sg_lib()) { /* a list: no Sort; Search (the capsule's left cap) moves to Sort's slot, beside Select, and the titles are the list's */
        sg_show(sg.btn_sort, 0);
        if (sg_genre()) { /* a genre's songs: no Search either; Select is the capsule's left cap (its own glass piece) */
            sg_show(sg.btn_search, 0);
            widget_set_prop_str(sg.btn_select, "style:normal:icon", "pod_nav_selectl");
            widget_set_prop_str(sg.btn_select, "style:over:icon", "pod_nav_selectl");
            widget_set_prop_str(sg.btn_select, "style:pressed:icon", "pod_nav_selectl_down");
        } else if (
            sg_artist() &&
            sg.btn_cf) { /* an artist's songs: the Cover Flow button is the capsule's left cap (Albums' place), no Search */
            sg_show(sg.btn_search, 0);
            sg_show(sg.btn_cf, 1);
        } else if (sg_recent()) { /* Recently Added: Search 122 | Select 168 | toggle 214 | Now Playing */
            widget_move(sg.btn_select, NAV_CF_X, 0);
            sg_show(sg.btn_view, 1);
        } else
            widget_move(sg.btn_search, NAV_CF_X, 0);
        widget_resize(sg.title, sg_search_x() - NAV_TITLE_X, 22);
        az_fit(sg.big, sg_name_text());
    }
    if (sg.nav_overlay && sg.nav_filter != SB_LIBRARY_FILTER_NONE) az_fit(sg.big, sg.nav_name);
    /* A playlist's header (docs/modules/songs.md): the mosaic tile (the Playlists page's, patch/grid.c) and the name under it (the count is the footer under the last row,
     * as Apple Music's), the pills and the rows lower, the large title gone. Without the label, the tile or the quadrant buffer the page keeps its plain look (the large title). */
    if (sg.cls == CLASS_PLAYLIST_SONGS && sg.hname) {
        sg.htmp = calloc((PH_COVER / 2) * (PH_COVER / 2), 4);
        if (grid_init(&sg.hg, sg.win, 1, PH_COVER, PH_COVER_R)) {
            grid_placeholder(&sg.hg);
            sg.head = 1;
            sg.al.top = PH_TOP;
            widget_move(sg.btn_play, SG_PILL_X0, PH_PILL_Y);
            widget_move(sg.btn_shuffle, SG_PILL_X1, PH_PILL_Y);
            az_fit(sg.hname, sg_name_text());
            sg_show(sg.big, 0);
            widget_set_visible(sg.hname, 1, 0); /* (an insensitive label: shown, never a touch target) */
        } else
            grid_free(&sg.hg);
    }
    pod_centre_pill(sg.btn_play, SG_PILL_W);
    pod_centre_pill(sg.btn_shuffle, SG_PILL_W);
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
int songs_open(void) {
    int r;
    memset(&sg_nav_request, 0, sizeof sg_nav_request);
    sg_nav_request.active = 1;
    sg_nav_request.filter = SB_LIBRARY_FILTER_NONE;
    r = sg_open(CLASS_ALL_SONGS, 0, (const char *)0, "", HOME_MYMUSIC);
    sg_nav_request.active = 0;
    return r;
}

int songs_open_nav_filter(int filter, const char *name, const char *artist) {
    unsigned i;
    int r;
    if (filter <= SB_LIBRARY_FILTER_NONE || filter > SB_LIBRARY_FILTER_GENRE || !name || !*name) return -1;
    memset(&sg_nav_request, 0, sizeof sg_nav_request);
    sg_nav_request.active = 1;
    sg_nav_request.filter = filter;
    for (i = 0; name[i] && i + 1 < sizeof sg_nav_request.name; ++i) sg_nav_request.name[i] = name[i];
    for (i = 0; artist && artist[i] && i + 1 < sizeof sg_nav_request.artist; ++i) sg_nav_request.artist[i] = artist[i];
    r = sg_open(CLASS_ALL_SONGS, 0, (const char *)0, sg_nav_request.name, -1);
    sg_nav_request.active = 0;
    return r;
}

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

/* Cover Flow's artist page (`artist`: the Artists row, the name in REC_TITLE): every song of the artist, the way the stock All songs card gets them:
 * loadAlbumList(0xf004, artist) fills the browsing record and the albums, the last one the All songs row, and loadAlbumdetailList(0xff01, that row) turns
 * the record into class 0xff11's (the all-songs flag, the album text, classinfo[0]). The page keeps the record. -1 when the page did not open or the
 * artist has no All songs row (the caller opens the stock page). */
int songs_open_artist(void *artist) {
    void *list, *row;
    unsigned n;
    if (sg.win || !artist) return -1;
    loadAlbumList(CLASS_ARTISTS, artist);
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    row = n ? deque_at(list, n - 1) : (void *)0;
    if (!row || I(row, REC_ID) != ID_ALL_SONGS) return -1;
    loadAlbumdetailList(CLASS_ARTIST_ALBUMS, row);
    return sg_open(CLASS_ARTIST_SONGS, 0, (const char *)0, cc_str(artist, REC_TITLE), -1);
}
