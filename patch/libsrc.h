/* Library source: where the Albums, album, Artists, Songs and Playlists pages get their rows, plays them and finds their covers (patch/libsrc.c holds the stock source, patch/sbsrc.c the
 * Navidrome one; docs/modules/subsonic.md "The seam" has the design and the evidence).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The pages read stock records: a deque of stSongInfo (REC_* in offsets.inc) that a stock query filled and cc_copy_list copied. A source hands them the same kind of deque, built from its
 * own data, so every painter, sort, hit test and select mode keeps working on records; what differs is only where a list comes from (the page's open and refresh), how a row plays,
 * where its cover and length come from and what its extras are. A page keeps one `const lib_src_t *src` (NULL = stock, the code that is there today) and calls these in the few places
 * it called a stock query, so a page without a source behaves exactly as before. Nothing here is a hook; all of it runs from the page's own widgets and timers.
 *
 * Records of a non-stock source: REC_ID is synthetic (<= -3; the queue records of a play use <= -2, patch/sbapi.h), REC_PATH holds "nd://<server id>" (never a file; the stock cover and length workers are not started for such a page),
 * REC_TITLE / REC_ALBUM / REC_ARTIST the texts, REC_TRACK / REC_DISC / REC_YEAR the numbers, REC_TYPE 8 for a track and 4 for an album, artist or playlist row. The strings are owned
 * by the deque's copy (cc_copy_list's rule), so a page destroys the deque as it destroys any copy. The server id of a row is found with lib_src_t.rec_id, never by parsing REC_PATH.
 */
#pragma once

#define REC_META \
    0x28 /* a string slot stock leaves NULL: a non-stock source's own data for the row (Playlists: "p\t<cover>\t<songs>\t<seconds>", patch/sbsrc.h); never read from a stock record */

enum {
    LS_ALBUMS,
    LS_ARTISTS,
    LS_SONGS,
    LS_PLAYLISTS,
    LS_FAVORITES,
    LS_DOWNLOADED,
    LS_SEARCH_ARTISTS,
    LS_SEARCH_ALBUMS,
    LS_SEARCH_SONGS
}; /* the list a page asks for */
enum {
    LS_PLAY_KEEP,
    LS_PLAY_ORDER,
    LS_PLAY_SHUFFLE
}; /* a row tap keeps the play mode, Play plays in order, Shuffle shuffles (patch/songops.h SO_*) */

/* How a track row is dressed beyond its text: what sbsrc fills for the page's row painter (the stock source leaves it all 0). */
enum { LS_DL_NONE = 0, LS_DL_WAIT, LS_DL_ACTIVE, LS_DL_DONE, LS_DL_FAILED };
typedef struct {
    int dl; /* LS_DL_*: LS_DL_DONE draws the downloaded badge, LS_DL_ACTIVE the grey right value "Downloading 42 %" (pct) */
    int pct; /* 0..100 while LS_DL_ACTIVE; -1 when the size is unknown (the value is "Downloading") */
    int dsd; /* a DSD file: the DSD marker, and an undownloaded one asks "Download to Play?" before anything plays */
    int fav; /* the server's favourite (Subsonic star) */
    int offline; /* the row cannot play now: not downloaded and no Wi-Fi (drawn dimmed, a tap says so) */
} ls_row_t;

/* The row menu's extra actions (patch/rowmenu.c: Play Next, Play After, Add to Playlist, Favorite, Get Info stay; a source adds or replaces). */
enum {
    LS_ACT_DOWNLOAD = 1,
    LS_ACT_DELETE_DL,
    LS_ACT_FAVORITE,
    LS_ACT_CANCEL_DL,
    LS_ACT_UNFAVORITE, /* Undo Favorite: LS_ACT_FAVORITE sets the star, this clears it (the caller's wish, not a toggle of what the source thinks) */
    LS_ACT_DOWNLOAD_ALL /* Download Album: `rec` is not a record but the page's list (a deque of records, list order); every track not on the card and not already queued is queued, and the one toast is the source's */
}; /* (cancel: a waiting or running download) */

/* The controls a source's pages offer in their navbar and cards (lib_src_t.caps): a page shows one only when the source has it. The stock library (a NULL source, or &lib_stock) has them
 * all; Navidrome's pages have Search only (Cover Flow needs the stock cache worker, and the source's Select is not finished). */
enum { LS_CAP_COVERFLOW = 1u << 0, LS_CAP_SEARCH = 1u << 1, LS_CAP_SELECT = 1u << 2 };
#define LS_CAP_ALL (LS_CAP_COVERFLOW | LS_CAP_SEARCH | LS_CAP_SELECT)

typedef struct lib_src lib_src_t;
struct lib_src {
    const char *name; /* "stock", "navidrome" */
    /* The rows of a list, a deque of records the caller destroys; NULL when it is empty or could not be made. `scope` is the row the list is of (a record, not a deque):
     *   LS_ALBUMS    NULL: every album; an artist row: that artist's albums (the stock All songs row last, as loadAlbumList leaves it)
     *   LS_ARTISTS   NULL
     *   LS_SONGS     NULL: every song; an album row: its tracks (an artist's All songs row: all the artist's songs)
     *   LS_PLAYLISTS NULL: the playlists; a playlist row: its tracks
     * LS_FAVORITES, LS_DOWNLOADED and LS_SEARCH_ARTISTS / _ALBUMS / _SONGS (scope NULL: the cached results of the last sba_search, patch/search.c) are Navidrome's lists; the stock source returns NULL for them. After a stock list of tracks the browsing record (CLASSINFO) is what the query left,
     * as the page needs it for a play (the page saves and puts it back as it does today). */
    void *(*list)(const lib_src_t *s, int which, void *scope);
    /* The record's id as the source knows it (the server id for Navidrome, "" for stock); the pages pass it back through scope. */
    const char *(*rec_id)(const lib_src_t *s, void *rec);
    /* Play track `at` of `list` (its records, as list() made them) and the rest as the queue: how is LS_PLAY_*; at -1 is a random track. It builds the queue, starts it and opens Now Playing
     * as patch/songops.c so_play does (a so_open_fn), or shows why not (a message). cls is the stock class of the page's list (so_play's), which a non-stock source ignores; pages call
     * this through patch/songops.c so_play_src. 0 started, -1 nothing started. A DSD row that is not on the card returns -2 for the page to confirm. */
    int (*play)(const lib_src_t *s, void *list, int at, int how, void (*open)(void *queue, int idx, int cls), int cls);
    /* The record's cover file: its path is written to `path` (the page decodes "file://" + path; it is the source's own file, never the Cover Flow cache file of `key`), asked for when it is missing. 1 the file is there, 0 asked (the page polls),
     * -1 no cover (the stock source: -1 for a missing file, the page's own worker makes it). Replaces cc_build_add for this page. A mosaic (patch/sbsrc.h sbs_mosaic_keys) keys the files by the hash in their names. */
    int (*cover)(const lib_src_t *s, void *rec, unsigned key, char *path, unsigned cap);
    /* The track's length in seconds (the footer total): 0 unknown. Replaces the durations table for this page. */
    unsigned (*seconds)(const lib_src_t *s, void *rec);
    /* The row's extras; called while painting, so it only reads memory (a status record), never a file. */
    void (*row)(const lib_src_t *s, void *rec, ls_row_t *out);
    /* A row-menu action on the record: LS_ACT_*; 0 done, otherwise the reason is shown by the source. */
    int (*act)(const lib_src_t *s, void *rec, int what);
    /* A number that changes when the source's data or a row's extras did: the page's timer re-reads or repaints when it moves (sba_gen + sba_dl_gen for Navidrome). */
    unsigned (*gen)(const lib_src_t *s);
    /* 1 when list(which, NULL) holds every row, 0 while it is a part that grows (Navidrome's paged Songs: the page shows no A-Z rail and re-reads as gen moves). NULL = always complete (the stock source). */
    int (*complete)(const lib_src_t *s, int which);
    /* 1 when the page's row `rec` is the track the player is on (the playing marker: the wave in place of the number). NULL = the stock test (is_playing on the record's path, as the page
     * always did); a source's queue records carry stream addresses, never the page's nd:// ones, so such a source answers itself (Navidrome: sbs_playing(rec_id)). Appended last. */
    int (*playing)(const lib_src_t *s, void *rec);
    /* Play Next / Play After for a source: the row's stock queue record (the same kind a play builds: REC_PATH the stream address or the local file, REC_ID the source's synthetic id) as a deque of one the caller
     * destroys, to hand to upnext_add. NULL when it cannot be queued now, the reason shown by the source (offline and not downloaded: "Connect to Wi-Fi first"; an undownloaded DSD row too, but the caller asks
     * ls_dsd_confirm first). Appended last; NULL for the stock source (its records are already the queue's). */
    void *(*queue_row)(const lib_src_t *s, void *rec);
    /* The stock-only controls this source's pages may show (LS_CAP_*; read it with ls_caps, not this field: a NULL source is the stock library). */
    unsigned caps;
    /* The number of rows list(which, scope) holds when its own data is not cached yet, from the source's record: the Playlists page shows a playlist's count from the sync's songCount
     * until its tracks arrive. 0 unknown. NULL for the stock source (its query answers at once). Appended last. */
    int (*count)(const lib_src_t *s, int which, void *scope);
    /* Whether list(which, scope) can still grow into rows: LS_ST_READY (the rows are there, or the server answered with none), LS_ST_LOADING (not cached yet: asked for, or about to be) or LS_ST_FAILED
     * (the request failed) or LS_ST_OFFLINE (no Wi-Fi and nothing cached). A page with no rows shows its layout and a loading indicator for LS_ST_LOADING, the empty text only for the others. NULL = always
     * ready (the stock source). Appended last. */
    int (*state)(const lib_src_t *s, int which, void *scope);
    /* The part of gen that moves with the list's rows (Navidrome: sba_gen and the retry epoch, not the download counters). A page whose gen moved reads the list again only when this moved too, and
     * otherwise repaints the rows it shows (a download's progress changes how a row is painted, never which rows there are). Read it after gen (gen may act on the change). NULL = every gen move
     * is a list change. Read it with ls_gen_rows. Appended last. */
    unsigned (*gen_rows)(const lib_src_t *s);
};
enum {
    LS_ST_READY = 0,
    LS_ST_LOADING,
    LS_ST_FAILED,
    LS_ST_OFFLINE
}; /* lib_src_t.state; OFFLINE: nothing cached and no Wi-Fi to ask on (a FAILED that says why) */

/* The loading spinner every source page shares (the Wi-Fi page's wf_spin0..7 frames, a 14 px image the asset builds hidden): ls_spin shows it and turns a frame every 250 ms from one shared timer
 * that ends once every spinner is hidden; ls_spin_end forgets it without touching the widget (a page's destroy). Four spinners at most turn at once (the pages stacked). */
void ls_spin(void *img, int on);
void ls_spin_end(void *img);
int ls_spin_tick(const void *arg); /* (the timer's callback; arg is stock's timer_info_t, not a ctx, and is not read) */
/* The pace at which a source page looks at src->gen (every source page: Albums, album, Artists, Playlists, Songs). A gen read is a sum of counters, so one pace costs nothing. */
#define LS_GEN_MS 500

/* The cover poll every source page shares. A source's cover (lib_src_t.cover, sba_rec_cover) that answers 0 ("asked, look again") is looked at again by ONE timer, every LS_COVER_MS, for as long as
 * some page has one pending and that page is the top window with the screen lit; a hidden page or a dark screen polls nothing. The page keeps an ls_cpoll_t and calls ls_cover_poll each time a
 * cover answers 0 (it is the "pending" flag; the tick clears it and the page's re-ask sets it again if the cover is still on its way). Per tick, for a pending page: `ask` (look at the pending covers
 * again: tiles back to 0, the header's file), then `spin` (turn the page's cover spinners and redraw; it returns how many tiles still load, 0 ends the spinning; the last redraw is the one that removes the
 * last spinner). The poll ends two quiet ticks after the last pending cover (a spinner still showing then is cleared through `giveup`). One give-up rule: after LS_COVER_POLLS asks (5 minutes) without the covers arriving the page's `giveup` runs (clear the spinners,
 * redraw, no more asking); a file that lands later is found when the tile is next loaded (scroll, gen re-read, reopen) or the page calls ls_cover_poll again, which starts a fresh count. */
#define LS_COVER_MS 250
#define LS_COVER_POLLS 1200
typedef struct {
    void *win; /* the page's window (the poll runs only while it is the top window) */
    void (*ask)(void); /* look at the pending covers again (may call ls_cover_poll itself); optional */
    int (*spin)(void); /* turn the cover spinners, redraw; returns the number of tiles still loading; optional */
    void (*giveup)(void); /* stop: clear the spinners and redraw; optional */
    int on, pend, idle, polls; /* (the helper's) */
} ls_cpoll_t;
void ls_cover_poll(ls_cpoll_t *p, void *win, void (*ask)(void), int (*spin)(void), void (*giveup)(void));
void ls_cover_end(ls_cpoll_t *p); /* forgets the page's poll (its destroy); the timer ends with the last one */
int ls_cover_tick(const void *arg); /* the timer's callback (stock's timer_info_t, not read) */

/* 1 when two lists of records hold the same rows in the same order (REC_PATH, REC_TITLE and REC_ARTIST of each): a page whose source's gen moved keeps its tiles and scroll then and swaps the records. */
int ls_same_list(void *old, unsigned oldn, void *fresh, unsigned n);
/* The key of the status line of a page with no rows: LOADING "Loading…" (a page without a spinner), OFFLINE "Connect to Wi-Fi first", FAILED "Can't connect to the server", else `empty` (the page's "No albums"). */
const char *ls_empty_key(int st, const char *empty);

/* A server track's cover for the playback-side pages (Now Playing, the mini bar, Vinyl Mode's label, the Pod cover pane, the queue, the timed cover page): "file://<path>" is written to url when the file is
 * there. *server is 1 when the record is a server track at all (its REC_ID is in the queue map, sba_rec_track), so its cover is never looked for under the library's album key; for a local track the result is -1
 * and nothing is written. Else sba_rec_cover's: 1 the cached file, 0 asked for or on its way (look again), -1 the track has none. */
int ls_rec_cover(void *rec, char *url, unsigned cap, int *server);
/* 1 when the record is a server track (its REC_ID is in the queue map), 0 for a local track or no record. */
int ls_rec_server(void *rec);

/* The controls the source may show: LS_CAP_ALL for the stock library (src NULL or &lib_stock), else src->caps. */
unsigned ls_gen_rows(const lib_src_t *src); /* src->gen_rows, or src->gen when the source has no split */
unsigned ls_caps(const lib_src_t *src);

/* The DSD "Download to Play?" confirm: for the row `at` of `list` (at < 0: the row the source's last play answered -2 for, a random Shuffle start) it asks in the stock confirm dialog (Cancel / Download, the
 * title and size in the text); Download queues the file through src->act(LS_ACT_DOWNLOAD). 1 when a download was asked for, else 0. Pages call it when so_play_src returns -2; patch/sbsrc.c. */
int ls_dsd_confirm(const lib_src_t *src, void *list, int at);

/* Favorite / Undo Favorite for the record through src->act(LS_ACT_FAVORITE, or LS_ACT_UNFAVORITE when `was`), with the toast of a success ("Added to Favorites" / "Removed from Favorites" by `was`, the state the caller showed; the source toasts a refusal).
 * The row sheet's Favorite and Now Playing's star on a server track. Returns the act's result (0 done). */
int ls_favorite(const lib_src_t *src, void *rec, int was);

/* Row marks (patch/libsrc.c ls_mark_*): the small pictures the pages draw from an ls_row_t. The pictures are the Podcasts atlas' (pc_atlas): the light grey downloaded disc (PA_BADGE_PX
 * square), the download ring (PA_DL_PX square, 12 steps; the arc is the progress) and the grey "DSD" tag (PA_DSD_W x PA_DSD_H), cut once into a bitmap of our own. */
enum { LS_MK_DONE, LS_MK_DSD };
#define LS_MK_GAP 6 /* between two marks, and between the marks and the text */
/* The width of the marks a row shows (the disc when downloaded, the ring while downloading or queued, the DSD tag when DSD, LS_MK_GAP between); 0 for none. */
int ls_marks_w(const ls_row_t *r);
/* Paints the row's marks left to right from x, centred on the line y_mid of a view view_h high (0: no clipping by hand); win lends its image loader the first time. */
void ls_marks_draw(void *canvas, void *win, const ls_row_t *r, int x, int y_mid, int view_h);
/* The download ring's step of a row (0..PA_DL_N - 1: the arc is step / PA_DL_N of the circle; 0 for a queued track or an unknown progress), -1 when the row is not downloading. The ring is drawn by ls_marks_draw, before the DSD tag. */
int ls_ring_step(const ls_row_t *r);

/* The stock library as a source (list = the stock queries and copies, play = so_play, cover and seconds = today's workers; patch/libsrc.c). Pages use NULL for it; this exists so a
 * source-neutral helper can be handed a pointer. */
extern const lib_src_t lib_stock;
/* The Navidrome source (patch/sbsrc.c); NULL when no server is saved. */
const lib_src_t *lib_navidrome(void);
