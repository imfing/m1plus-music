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

#include "plcover.h"

#define GRID_NAME_MIN 64 /* the smallest cover side that shows a playlist's name (the list rows' 52 px do not) */
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
    int xw; /* a source's row: the width its marks / state value take from the text (the text was cut for it; patch/albumpage.c, patch/songs.c cut it again when it changes) */
    int load; /* a source's cover on its way (the page sets it; with art not 1 the grid draws the spinner on the disc) */
    int subx; /* list mode: the grey line starts this far right of the text (a download ring sits before it); the owner clears GRID_FIT_ARTIST when it changes */
    unsigned
        cov; /* a playlist tile: the sig of the chosen cover it was made for (plc_t.sig), 0 the mosaic; the owner compares it to see a cover change */
    int nm; /* a chosen cover with the Name on Cover flag (grid_plc sets it, grid_free_art clears it): grid_plc_name draws the playlist's name on it */
    int nochev; /* list mode with chevrons: this row opens nothing (a dimmed Not available result): no chevron, the text runs to LIST_TEXT_W */
    int markw; /* list mode without chevrons: > 0, the texts end this far after LIST_TEXT_X (the page paints a mark beyond them: the picker's tick); the owner clears fit when it changes */
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
    void *chev; /* the list rows' chevron (m1_make_chevron), made on first use; freed by grid_free */
    const void *
        az; /* the Albums list's az_t (patch/azlist.h): grid_list_paint takes a row's y from az_row_y (the section headers between the rows); NULL: row r at r * LIST_ROW_H */
    unsigned clock;
    void *spin[8]; /* the cover spinner's frames (grid_spin_open), spin_px square; spin_n the current one */
    int spin_px, spin_n;
    int person; /* 1: the pictures are artists' (the Artists page): a portrait file is cut as pv_square cuts it, from the top third (cc_decode box 2) */
    /* the file of a cover key as "file://<path>" into out (80 bytes), NULL when there is none; NULL here: the Cover Flow cache file (cc_url). A source's page sets it. */
    const char *(*url)(char *out, unsigned key);
} grid_t;

/* n tiles on the heap; 0 when there is no memory (the grid is then unusable: grid_free it). side and round as above. */
int grid_init(grid_t *g, void *win, int n, int side, int round);
/* The cover size and corners (round clamped to GRID_MAX_ROUND; blend as above). Call grid_drop first when tiles exist: they were made for the old shape. */
void grid_shape(grid_t *g, int side, int round, int blend);
void grid_free(grid_t *g);
void grid_drop(grid_t *g); /* every tile and the placeholder dropped (the cover size changes) */
void grid_placeholder(grid_t *g); /* the placeholder bitmap: the theme's disc reduced like a cover, else flat grey */
void grid_free_art(grid_tile_t *t);

/* The cover spinner a source's page draws on a tile whose cover is on its way (grid_tile_t.load, art not 1): the 8 frames "<prefix>0".."<prefix>7" (wf_spin, 14 px; wf_spinL, 28 px)
 * made into grey bitmaps with alpha, once (a failed set is not retried); grid_free frees them. grid_spin_turn advances the frame and returns how many tiles are loading (the
 * page's 250 ms timer redraws and repeats while it is not 0). Without grid_spin_open nothing is drawn. */
void grid_spin_open(grid_t *g, const char *prefix, int px);
int grid_spin_turn(grid_t *g);
/* The current frame at x, y (cut at the view's edges as grid_blit_from does); 0 when the frames are not open. A page that paints its own busy row turns grid_t.spin_n itself. */
int grid_spin_draw(void *canvas, grid_t *g, int x, int y, int view_h);
/* An empty level's status line (patch/podcasts.c, the Discover and search levels; the Audiobooks levels): `key` (already translated) in grey 20 px `style`, wrapped to the margins in at most four lines, the lines
 * centred as a block between content y top and bottom (and each across the page); busy puts the spinner (the frames of g, grid_spin_open) before the first line, the two centred as a group. off: the scroll offset. */
void grid_hint_paint(void *canvas, grid_t *g, void *style, const char *key, int busy, int top, int bottom, int off);

grid_tile_t *grid_find(grid_t *g, int album);
/* The scroll_view sv is moving: a finger is dragging it (pressed and past the drag threshold) or its scroll animator (the fling) is running.
 * 0 for a null sv. The loaders decode nothing meanwhile (a decode is a few ms on the UI thread and the next touch would wait behind it). */
int grid_moving(void *sv);
/* The way a page's content went since its loader last looked: off its offset now, *seen the one it saw; *dir 1 down, -1 up (kept when it did not move). */
void grid_dir(int off, int *seen, int *dir);
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
/* A playlist's chosen cover (patch/plcover.h) as the whole tile in one call: plc_art at the grid's side, the rounded corners, art 1 (art 2 without memory). */
void grid_plc(grid_t *g, grid_tile_t *t, const plc_t *c);
/* The name (UTF-8, the owner's current one) in white on the tile's cover at (x, y), top left, up to two lines (g->st_title, wrapped by pw_wrap, a last line cut with an ellipsis), when the tile has
 * t->nm, a cover (art 1), g->side >= GRID_NAME_MIN and the style; lines not wholly inside 0..view_h (view_h > 0) are not drawn. Sets the canvas' text style. */
void grid_plc_name(void *canvas, grid_t *g, const grid_tile_t *t, const char *name, int x, int y, int view_h);

/* Cell i (row-major, GRID_COLS a row): its top left in the view when the first row's top is at origin_y. */
int grid_cell_x(int i);
int grid_cell_y(int i, int origin_y);
/* The cell under view point (x, y) among count cells, or -1: the cover and the two lines, not the gaps, margins or air. */
int grid_cell_at(int x, int y, int origin_y, int count);

/* A cover of the tile (its bitmap, else the placeholder) at (x, y) in the view; rows beyond view_h (> 0) are cut by hand. */
void grid_blit(void *canvas, grid_t *g, grid_tile_t *t, int x, int y, int view_h);
/* The playing marker (ah_wave, AB_WAVE px) as a bitmap in the accent or Neutral fill, the album page's: NULL when it did not decode; the caller destroys it. grid_wave_draw: at (x, top) of the window, only when wholly inside 0..view_h (a NULL wave draws nothing). */
void *grid_wave_make(void *win);
void grid_wave_draw(void *canvas, void *wave, int x, int top, int view_h);
/* A w x h piece of bmp from (sx, sy) at (x, y) of the window, the rows outside 0..view_h cut by hand (view_h 0: no bottom cut); NULL bmp draws nothing. */
void grid_blit_from(void *canvas, void *bmp, int sx, int sy, int w, int h, int x, int y, int view_h);
/* The SG_MARK x SG_MARK select mark bmp at (x, top), only when wholly inside 0..view_h. */
void grid_mark_draw(void *canvas, void *bmp, int x, int top, int view_h);
/* The tile's album (pass 0) or artist (pass 1) in rect (x, y, w, h), cut once; drawn only when wholly inside view_h (> 0); 0: always, for a paint inside a
 * scroll_view, whose canvas clip cuts it at the view's edges (as a cover). The canvas has the style. */
void grid_text(void *canvas, grid_tile_t *t, int pass, int x, int y, int w, int h, int view_h);
/* The list mode's rows [r0, r1] (row r is tile_of(ctx, r)) of a view scrolled `off` px: the pressed fill (row press - 1, 0 none), the cover, the hairline,
 * then the titles (style label st_title) and the subtitles (st_sub), cut at the view's edges by the scroll_view's canvas clip (the callers paint inside one). Shared by the Albums and Playlists lists. shift: the
 * cover, the texts (and their width) and the hairline's start move right by it (the Playlists page's select mode makes room for the mark; 0 elsewhere); the pressed fill stays.
 * The hairline runs from the text to LIST_HAIR_END (Apple's inset). A grid whose `az` is set (the Albums list) moves the hairline end, the chevron and the text end left by az_inset while the A-Z rail is shown. chev: the row opens a page: the shared grey chevron (m1_make_chevron) at LIST_CHEV_X and the texts end LIST_TEXT_W_CHEV after LIST_TEXT_X (0: no chevron, the texts to LIST_TEXT_W). */
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
/* The same for a run of cells that starts a row of its own: cell a sits at the position a - base of the run (column, row) from origin_y (the Albums grid's sections). */
void grid_paint_base(void *canvas, grid_t *g, int first, int last, int base, int origin_y, int view_h,
                     grid_tile_t *(*tile_of)(void *, int), void *ctx);

/* Page helpers of the list pages (the stock calls their copies made, in the same order). */
#define GRID_NAV_TITLE_H 22 /* the navbar's small title's height */

/* The scroll_view sv's yoffset, 0 for none. */
static inline int grid_sv_off(void *sv) { return sv ? I(sv, SC_YOFF) : 0; }
static inline void grid_sv_redraw(void *sv) { widget_invalidate_force(sv, (void *)0); }
/* The stock list `list` (count rows, the first record `first`) is still the one in *pdeq_showlist (cur). */
static inline int grid_list_same(void *cur, void *list, unsigned count, void *first) {
    return list && cur == list && deque_size(cur) == count && (!count || deque_at(cur, 0) == first);
}
/* *press = p, the view redrawn when it changed. */
static inline void grid_set_press(int *press, int p, void *sv) {
    if (*press == p) return;
    *press = p;
    grid_sv_redraw(sv);
}
/* The press ends: *down (the item the pointer went down on, plus 1) is 0 and the pressed row's fill goes. */
static inline void grid_press_end(int *down, int *press, void *sv) {
    *down = 0;
    grid_set_press(press, 0, sv);
}
/* The pointer event e in the coordinates of view (widget_to_local includes the scroll offset): pt[0] x, pt[1] y. */
static inline void grid_ev_local(void *view, void *e, int *pt) {
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(view, pt);
}
/* Binds h to sv's EVT_SCROLL and EVT_SCROLL_END (the second only when the first bound); returns 1 when either failed: the large title's collapse needs the events, so
 * the navbar keeps its small title (title, when not NULL, is shown) and *title_on (when not NULL) is set to that flag. */
static inline int grid_scroll_bind(void *sv, int (*h)(void *, void *), void *title, int *title_on) {
    int noscroll = !widget_on(sv, EVT_SCROLL, h, (void *)0) || !widget_on(sv, EVT_SCROLL_END, h, (void *)0);
    if (noscroll && title) widget_set_visible(title, 1, 0);
    if (title_on) *title_on = noscroll;
    return noscroll;
}
/* The fade strip under the navbar: shown (on) or hidden, never touched. */
static inline void grid_fade(void *fade, int on) {
    widget_set_visible(fade, on, 0);
    widget_set_sensitive(fade, 0);
}
/* The icon of a navbar button: normal and over the same, pressed its own. */
static inline void grid_icons(void *w, const char *normal, const char *pressed) {
    widget_set_prop_str(w, "style:normal:icon", normal);
    widget_set_prop_str(w, "style:over:icon", normal);
    widget_set_prop_str(w, "style:pressed:icon", pressed);
}
/* The navbar's small title ends at x end. */
static inline void grid_title_end(void *title, int end) { widget_resize(title, end - NAV_TITLE_X, GRID_NAV_TITLE_H); }
