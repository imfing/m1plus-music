/* The album grid, shared by the Albums page (patch/albums.c) and the Recently Played shelf of the menu (patch/recent.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One cell is a GRID_COVER px cover, the album (GRID_TITLE_H high, GRID_TITLE_GAP under the cover) and the artist (GRID_SUB_H, under
 * the album), GRID_COLS cells a row GRID_GAP apart from x GRID_MARGIN, rows GRID_ROW_GAP apart (PITCH from row to row): the geometry of
 * offsets.inc GRID_*. This module is what both users do with a cell and neither owns:
 *   tiles    grid_tile_t: a cell's album text (wide chars, cut with an ellipsis ONCE, the first time it is drawn) and its cover, a bitmap the
 *            loader made once from the Cover Flow cache file (cc_url; box-reduced by cc_decode) or the stock placeholder disc.
 *   ring     grid_tile / grid_find: the tiles are a fixed ring keyed by the user's album number; the least recently used one outside the
 *            window the user protects is replaced (the shelf has as many tiles as cells, so its ring never replaces).
 *   loader   grid_art makes ONE cover (the user decides when: the Albums page one per 16 ms tick for the cell nearest the middle of its
 *            view, the shelf one per tick once it is in view). Paint never decodes.
 *   paint    grid_paint: the covers, then the album pass and the artist pass (one text style at a time, widget_prepare_text_style on the
 *            user's two hidden labels), for cells first..last in one view's EVT_AFTER_PAINT; grid_blit / grid_text for the Albums list mode.
 *   hit      grid_cell_at: the cell under a point: the cover or its two lines; the gaps and margins are dead.
 *   corners  g->round: the radius of the cover's corners in px (GRID_R for both grids, 0 for the Albums list's small covers), blended into black in the pixels: the tiles stay opaque.
 * The user supplies the albums (the Albums page its sorted stock list, the shelf its recent entries with their cover keys) and the position
 * (origin y of the first row in the view); the scrolling, the timers and the touch stay with the user.
 */
#pragma once

#define GRID_TEXT 48 /* wide chars kept per text, the NUL included */
#define GRID_CELL_H (GRID_COVER + GRID_TITLE_GAP + GRID_TITLE_H + GRID_SUB_H)
#define GRID_PITCH (GRID_CELL_H + GRID_ROW_GAP) /* row to row */
#define GRID_COL_PITCH (GRID_COVER + GRID_GAP)
#define GRID_LIST_W 320 /* the list mode's fills: the content view's width */
#define GRID_FIT_TITLE 1
#define GRID_FIT_ARTIST 2
#define GRID_PLACEHOLDER "p_default" /* the stock 254 px disc, as Cover Flow's */
#define GRID_GREY 0xff2b2b2bu
#define GRID_MAX_ROUND 22 /* the largest corner radius (the Search page's round artist thumbnails: half of 44) */

typedef struct {
    int album; /* the user's album number + 1; 0 = free */
    unsigned stamp;
    unsigned ckey; /* the cover key (cc_album_key of the album row: the cache file's name) */
    void *bmp; /* the cover, side x side RGBA, once decoded */
    int art; /* 0 not tried, 1 bmp is the cover, 2 no cache file / no picture: the placeholder */
    int fit; /* GRID_FIT_*: which texts have been cut to their width */
    int tw, aw; /* title / artist length, in wide chars */
    unsigned title[GRID_TEXT], artist[GRID_TEXT];
    unsigned qkey
        [4]; /* a mosaic tile (grid_mosaic): the distinct cover keys, nq of them (0..4), qi of them already placed in bmp */
    int nq, qi;
    int mid; /* list mode: the title alone in the row, centred vertically (the picker's New playlist row) */
    int nochev; /* list mode with chevrons: this row opens nothing (a dimmed Not available result): no chevron, the text runs to LIST_TEXT_W */
} grid_tile_t;

typedef struct {
    void *win; /* the page's window (the image loader wants one) */
    void *st_title, *st_sub; /* the hidden labels whose styles are the album and artist text styles */
    int side; /* the cover size (GRID_COVER, or the Albums list mode's) */
    int round; /* corner radius in px, 0: square */
    int blend; /* 1: the corners are cut in the bitmap's alpha (drawn over a background that changes, the Albums list's
                                    * pressed row); 0: blended into black once, the tile opaque (both grids lie on black) */
    unsigned char corner[GRID_MAX_ROUND * GRID_MAX_ROUND]; /* the top left corner's coverage outside the arc, 0..255 */
    grid_tile_t *tiles; /* n tiles, heap */
    int n;
    void *placeholder; /* bitmap of the disc */
    void *chev; /* the list rows' chevron (pod_make_chevron), made on first use; freed by grid_free */
    unsigned clock;
} grid_t;

/* n tiles on the heap; 0 when there is no memory (the grid is then unusable: grid_free it). side and round as above. */
int grid_init(grid_t *g, void *win, int n, int side, int round);
/* The cover size and corners (round clamped to GRID_MAX_ROUND; blend as above). Call grid_drop first when tiles exist: they were made for the old shape. */
void grid_shape(grid_t *g, int side, int round, int blend);
void grid_free(grid_t *g);
void grid_drop(grid_t *g); /* every tile and the placeholder dropped (the cover size changes) */
void grid_placeholder(grid_t *g); /* the placeholder bitmap: the theme's disc reduced like a cover, else flat grey */
void grid_free_art(grid_tile_t *t);

grid_tile_t *grid_find(grid_t *g, int album);
/* The scroll_view sv is moving: a finger is dragging it (pressed and past the drag threshold) or its scroll animator (the fling) is running.
 * 0 for a null sv. The loaders decode nothing meanwhile (a decode is a few ms on the UI thread and the next touch would wait behind it). */
int grid_moving(void *sv);
/* The tile of album a: the one it has, else a free one, else the least recently used one outside [lo, hi] (the window). *fresh is 1 when
 * the tile was just reset: the caller then sets its texts and cover key (grid_set). */
grid_tile_t *grid_tile(grid_t *g, int a, int lo, int hi, int *fresh);
void grid_set(grid_tile_t *t, const char *album, const char *artist, unsigned ckey);

/* The cover from the cache file of t->ckey (t->art 1), else the placeholder (t->art 2); a bitmap that cannot be made also gives 2. */
void grid_art(grid_t *g, grid_tile_t *t);
/* The same from a picture file at url ("file://<path>", any size the stock loader takes; NULL: no picture, the placeholder): the Podcasts page's covers. The caller has checked the size (pc_cover_ok). */
void grid_art_url(grid_t *g, grid_tile_t *t, const char *url);

/* A mosaic cover (the Playlists page): the tile's nq distinct cover keys qkey[] (the caller sets them, qi 0), ONE source decoded per call into
 * tmp (side / 2 squared words, the caller's) and placed in its quadrants; the covers repeat to fill four quadrants (1: the one cover full size,
 * 2: A B / B A, 3: A B / C A, 4: A B / C D). The tile's bitmap exists, unfinished, until the last call, which rounds the corners and sets
 * art 1; 0 keys, or a bitmap that cannot be made, give art 2 (the placeholder). A source that does not decode leaves its quadrants grey. */
void grid_mosaic(grid_t *g, grid_tile_t *t, unsigned *tmp);

/* Cell i (row-major, GRID_COLS a row): its top left in the view when the first row's top is at origin_y. */
int grid_cell_x(int i);
int grid_cell_y(int i, int origin_y);
/* The cell under view point (x, y) among count cells, or -1: the cover and the two lines, not the gaps, margins or air. */
int grid_cell_at(int x, int y, int origin_y, int count);

/* A cover of the tile (its bitmap, else the placeholder) at (x, y) in the view; rows beyond view_h (> 0) are cut by hand. */
void grid_blit(void *canvas, grid_t *g, grid_tile_t *t, int x, int y, int view_h);
/* The tile's album (pass 0) or artist (pass 1) in rect (x, y, w, h), cut once; drawn only when wholly inside view_h (> 0); 0: always, for a paint inside a
 * scroll_view, whose canvas clip cuts it at the view's edges (as a cover). The canvas has the style. */
void grid_text(void *canvas, grid_tile_t *t, int pass, int x, int y, int w, int h, int view_h);
/* The list mode's rows [r0, r1] (row r is tile_of(ctx, r)) of a view scrolled `off` px: the pressed fill (row press - 1, 0 none), the cover, the hairline,
 * then the titles (style label st_title) and the subtitles (st_sub), cut at the view's edges by the scroll_view's canvas clip (the callers paint inside one). Shared by the Albums and Playlists lists. shift: the
 * cover, the texts (and their width) and the hairline's start move right by it (the Playlists page's select mode makes room for the mark; 0 elsewhere); the pressed fill stays.
 * The hairline runs from the text to LIST_HAIR_END (Apple's inset). chev: the row opens a page: the shared grey chevron (pod_make_chevron) at LIST_CHEV_X and the texts end LIST_TEXT_W_CHEV after LIST_TEXT_X (0: no chevron, the texts to LIST_TEXT_W). */
void grid_list_paint(void *canvas, grid_t *g, void *st_title, void *st_sub, int r0, int r1, int off, int view_h,
                     int press, int shift, int chev, grid_tile_t *(*tile_of)(void *, int), void *ctx);

/* A playlist's mosaic: the first (up to) four distinct albums of its songs that have a Cover Flow cache file, as cache keys in key[4], and how many (0..4). From the
 * first PL_SCAN songs of the list `songs` (a stock song list); the key is the cc_album_key of the song (its artist and album as the playlist stored them), and when
 * that has no file the album of that name in `albums` (the library's copy, cc_albums; NULL: no lookup), whose record carries the artist the cache key was made from.
 * *miss (NULL: not wanted) is set to 1 when a scanned song's album had a key but no file under any of them (the file may be written later), else 0.
 * Shared by the Playlists page (one playlist a tick) and the Songs page's playlist header. */
int grid_mosaic_keys(void *songs, void *albums, unsigned *key, int *miss);

/* Cells [first, last): the covers, then the albums, then the artists. tile_of(ctx, a) gives cell a's tile. */
void grid_paint(void *canvas, grid_t *g, int first, int last, int origin_y, int view_h,
                grid_tile_t *(*tile_of)(void *, int), void *ctx);
