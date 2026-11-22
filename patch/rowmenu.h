/* The track rows' "..." menu: Play Next, Play After, Add to Playlist, Favorite, Get Info (patch/rowmenu.c, docs/modules/rowmenu.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Shared by the album page (patch/albumpage.c) and the Songs page (patch/songs.c). A page paints the "..." in its own row painter (rowmenu_paint), hit-tests the zone itself
 * with its own press and drag rules (rowmenu_zone_x) and calls rowmenu_open_src for the row; the scrim, the bottom sheet and its five rows are widgets of the page's asset
 * (tools/pod_ui.py row_menu, last in z-order); nothing here adds a widget per row.
 */
#pragma once
#include "offsets.inc"
#include "libsrc.h"
#include "common.h"

typedef struct rowmenu rowmenu_t;

/* A page's "Add to Playlist" for the row `row` (its own one-row selection and the picker, patch/songops.c so_add). Called after the menu has closed. */
typedef void (*rowmenu_add_fn)(int row);

/* A stock playlist's "Remove from Playlist" (rowmenu_set_remove): called after the menu has closed with the menu's own copy of the row's record (its REC_ID is the playlist row's id; freed after the call). */
typedef void (*rowmenu_remove_fn)(void *rec);

/* The Queue page's sheet (rowmenu_open_queue): called once the sheet has closed with the row it opened for and the row of the sheet that was tapped (RMQ_*). */
typedef void (*rowmenu_queue_fn)(int row, int act);
#define RMQ_NEXT 0 /* Play Next */
#define RMQ_AFTER 1 /* Play After */
#define RMQ_REMOVE 2 /* Remove from Queue */
/* The Home pins' sheet (patch/pins.c, tools/pod_ui.py row_menu(pins=True)) is the same three-row sheet with other words and glyphs; its rows call back with these. */
#define RMP_PLAY RMQ_NEXT /* Play */
#define RMP_SHUFFLE RMQ_AFTER /* Shuffle */
#define RMP_UNPIN RMQ_REMOVE /* Unpin Playlist / Unpin Artist / Pin Artist (three-row sheet) */
/* The five-row album long-press sheet (Albums page, Home album pins, Recently Played; tools/pod_ui.py row_menu(album=True)): Play, Shuffle, Play Next, Play After, Pin / Unpin Album. */
#define RMA_PLAY 0
#define RMA_SHUFFLE 1
#define RMA_NEXT 2
#define RMA_AFTER 3
#define RMA_PIN 4

struct rowmenu_slot {
    rowmenu_t *rm;
    int k; /* 0 Play Next, 1 Play After, 2 Add to Playlist, 3 Favorite, 4 Get Info, 5 Pin Song, 6 Remove from Playlist */
};

struct rowmenu {
    void *win, *scrim, *card;
    void *item[RM_ROWS];
    void *fav_label,
        *fav_icon; /* the Favorite row's label and glyph: "Favorite" / "Undo Favorite" and the outline / filled star, set at every open */
    void *
        dots; /* the "..." as a RGBA bitmap (RM_DOTS_PX square, RM_DOTS_RGB with the image's coverage as alpha); NULL: the page has no "..." */
    void *
        rows; /* a deque of one stSongInfo, the row the open menu is for (a copy: the page's list may be replaced under the menu) */
    int fav; /* the open menu's row is a favourite (stock myfav) */
    int on; /* the "..." is shown: the assets are there */
    int open;
    int row; /* the page's index of the row */
    rowmenu_add_fn add;
    rowmenu_queue_fn queue; /* the Queue page's sheet is open (three rows: RMQ_*), this is what its rows call */
    int alt; /* the track sheet is showing the album sheet's five rows (rowmenu_open_album): its words are put back at the next rowmenu_open_src */
    int queued; /* bound by rowmenu_bind_queue (three rows, the Queue page's) or rowmenu_bind_album (five rows) */
    struct rowmenu_slot slot[RM_ROWS];
    /* A source's row (rowmenu_open_src): the third row is Download / Cancel Download / Remove Download in place of Add to Playlist, Favorite and its toast go through the source. */
    const lib_src_t *src; /* NULL: the stock library */
    void *dl_label, *dl_icon; /* the third row's label and glyph, set at every open */
    void *pin_label,
        *pin_icon; /* the sixth row's label and glyph (Pin Song / Unpin Song, rm_ic_pin / rm_ic_unpin), set at every open; NULL: the page's asset has no such row */
    int pin; /* the open menu has the Pin Song row: a song of the card (no source), the asset has the row */
    rowmenu_remove_fn remove; /* the page's Remove from Playlist (rowmenu_set_remove), NULL: the page has no such row */
    int rm_row; /* the open menu has the Remove from Playlist row */
    int dl; /* the third row's action for a source: LS_ACT_DOWNLOAD / LS_ACT_CANCEL_DL / LS_ACT_DELETE_DL */
};

/* Looks up and binds the widgets of the page's window and makes the "..." bitmap. 1 when the "..." can be shown (assets found, M1+ Music not switched off), else 0
 * (the page then paints no "..." and takes no tap for it; it works as before). Call once, after the window opened. */
int rowmenu_bind(rowmenu_t *rm, void *win);

/* The Queue page's menu: the same widgets and the same sheet with three rows only (Play Next, Play After, Remove from Queue; the page's asset, tools/pod_ui.py row_menu(queue=True)). */
int rowmenu_bind_queue(rowmenu_t *rm, void *win);

/* The album long-press sheet: the same widgets and callback shape with RM_ALBUM_ROWS (5) rows (Play, Shuffle, Play Next, Play After, Pin / Unpin Album; tools/pod_ui.py row_menu(album=True)). */
int rowmenu_bind_album(rowmenu_t *rm, void *win);

/* Opens the Queue or pins/album sheet for its row `row`; `fn(row, act)` runs after the sheet has closed, when a row of it is tapped. 1 when open. */
int rowmenu_open_queue(rowmenu_t *rm, int row, rowmenu_queue_fn fn);

/* The toast of upnext_add's return status (`r`, with `after` 0 Play Next / 1 Play After): UPNEXT_ADDED -> "Playing Next" / "Added to Queue", refusal -> translated reason, UPNEXT_STARTED -> none. */
void rowmenu_upnext_toast(int r, int after);

/* The five-row album sheet (Play, Shuffle, Play Next, Play After, Pin Album / Unpin Album: `pinned` picks the last) on a menu bound by rowmenu_bind (a page whose asset has the track sheet: its rows
 * are reworded and the rows past the fifth hidden; rowmenu_open_src puts them back). `fn(row, act)` with act RMA_* runs after the sheet has closed. 1 when open. */
int rowmenu_open_album(rowmenu_t *rm, int row, int pinned, rowmenu_queue_fn fn);

/* The sheet `n` rows high (1..RM_ROWS) at the window's foot, in the glass of that height (pc_sheet<n>; a crop of a taller one is never used): the rows past the n-th are the caller's to hide
 * (m1_show(rm->item[i], 0)). Call before an open when the sheet's rows vary (the Home pins' sheet, the track rows' sheet: rowmenu_open_src does it). */
void rowmenu_set_rows(rowmenu_t *rm, int n);

/* Frees the bitmap and the row copy (the window's destroy). */
void rowmenu_free(rowmenu_t *rm);

/* The "..." is shown (the page's text end and hit test follow this). */
static inline int rowmenu_on(const rowmenu_t *rm) { return rm->on; }

/* The left edge of the "..." zone whose right edge is `right` (RM_MORE_RIGHT, or RM_MORE_RIGHT_RAIL beside the Songs page's rail). */
int rowmenu_zone_x(int right);

/* Where the text of a row ends: RM_INK_GAP before the glyph's ink, for the zone whose right edge is `right` and `flush` as rowmenu_paint takes them. */
int rowmenu_text_end(int right, int flush);

/* The long press (RM_LONG_MS): a page calls rowmenu_hold_start from its press on a row; when the time is up `fn(row)` runs (the page clears its press and calls its open). The page stops it on a
 * release, an abort and a move of SC_DRAG_PX or more (rowmenu_hold_move with the press point); rowmenu_close and rowmenu_free stop it too. */
typedef void (*rowmenu_hold_fn)(int row);
void rowmenu_hold_start(int row, rowmenu_hold_fn fn);
void rowmenu_hold_stop(void);
void rowmenu_hold_move(const m1_tap_t *t, void *e);

/* The "..." of a row whose top is at y (the page's paint coordinates) in the zone whose right edge is `right`, cut to [0, view_h) like the chevrons. `flush` 0: centred in the
 * zone; `flush` 1: its bitmap's right edge on `right` (the Songs page beside the A-Z rail). */
void rowmenu_paint(void *canvas, const rowmenu_t *rm, int right, int flush, int y, int row_h, int view_h);

/* Opens the sheet for the row `row` whose record is `rec`; `add` is the page's Add to Playlist; src is the row's library source (NULL or &lib_stock: the card's library).
 * 1 when the menu is open, 0 when it cannot be (no "...", no memory). The five rows: Play Next, Play After (the source's queue record through upnext_add; an undownloaded DSD row asks
 * "Download to Play?" first), Download / Cancel Download / Remove Download by the row's state, Favorite / Undo Favorite (the source's star), Get Info (the page for the source's data). */
int rowmenu_open_src(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add, const lib_src_t *src);

/* Closes the menu and drops the row copy. */
void rowmenu_close(rowmenu_t *rm);

/* The page's Remove from Playlist (a stock playlist's songs page, patch/songs.c): the sheet then has the row last (after Pin Song when that shows) for a playlist song record (REC_ID over PL_MAX). Call after rowmenu_bind; NULL takes it away. */
void rowmenu_set_remove(rowmenu_t *rm, rowmenu_remove_fn fn);
