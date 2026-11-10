/* The track rows' "..." menu: Play Next, Play After, Add to Playlist, Favorite, Get Info (patch/rowmenu.c, docs/modules/rowmenu.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Shared by the album page (patch/albumpage.c) and the Songs page (patch/songs.c). A page paints the "..." in its own row painter (rowmenu_paint), hit-tests the zone itself
 * with its own press and drag rules (rowmenu_zone_x) and calls rowmenu_open for the row; the scrim, the bottom sheet and its five rows are widgets of the page's asset
 * (tools/pod_ui.py row_menu, last in z-order); nothing here adds a widget per row.
 */
#pragma once
#include "libsrc.h"

typedef struct rowmenu rowmenu_t;

/* A page's "Add to Playlist" for the row `row` (its own one-row selection and the picker, patch/songops.c so_add). Called after the menu has closed. */
typedef void (*rowmenu_add_fn)(int row);

struct rowmenu_slot {
    rowmenu_t *rm;
    int k; /* 0 Play Next, 1 Play After, 2 Add to Playlist, 3 Favorite, 4 Get Info */
};

struct rowmenu {
    void *win, *scrim, *card;
    void *item[5];
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
    struct rowmenu_slot slot[5];
    /* A source's row (rowmenu_open_src): the third row is Download / Cancel Download / Remove Download in place of Add to Playlist, Favorite and its toast go through the source. */
    const lib_src_t *src; /* NULL: the stock library */
    void *dl_label, *dl_icon; /* the third row's label and glyph, set at every open */
    int dl; /* the third row's action for a source: LS_ACT_DOWNLOAD / LS_ACT_CANCEL_DL / LS_ACT_DELETE_DL */
};

/* Looks up and binds the widgets of the page's window and makes the "..." bitmap. 1 when the "..." can be shown (assets found, M1+ Music not switched off), else 0
 * (the page then paints no "..." and takes no tap for it; it works as before). Call once, after the window opened. */
int rowmenu_bind(rowmenu_t *rm, void *win);

/* Frees the bitmap and the row copy (the window's destroy). */
void rowmenu_free(rowmenu_t *rm);

/* The "..." is shown (the page's text end and hit test follow this). */
static inline int rowmenu_on(const rowmenu_t *rm) { return rm->on; }

/* The left edge of the "..." zone whose right edge is `right` (RM_MORE_RIGHT, or RM_MORE_RIGHT_RAIL beside the Songs page's rail). */
int rowmenu_zone_x(int right);

/* The "..." of a row whose top is at y (the page's paint coordinates) in the zone whose right edge is `right`, cut to [0, view_h) like the chevrons. `flush` 0: centred in the
 * zone; `flush` 1: its bitmap's right edge on `right` (the Songs page beside the A-Z rail). */
void rowmenu_paint(void *canvas, const rowmenu_t *rm, int right, int flush, int y, int row_h, int view_h);

/* Opens the sheet for the row `row` whose record is `rec`; `add` is the page's Add to Playlist. 1 when the menu is open, 0 when it cannot be (no "...", no memory). */
int rowmenu_open(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add);

/* The same for a row of a library source (src NULL or &lib_stock: rowmenu_open). The five rows: Play Next, Play After (the source's queue record through upnext_add; an undownloaded DSD row asks
 * "Download to Play?" first), Download / Cancel Download / Remove Download by the row's state, Favorite / Undo Favorite (the source's star), Get Info (the page for the source's data). */
int rowmenu_open_src(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add, const lib_src_t *src);

/* Closes the menu and drops the row copy. */
void rowmenu_close(rowmenu_t *rm);
