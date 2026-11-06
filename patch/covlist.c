/* M1+ Music cover lists: the plain list of the albums that have no art, or no cache file at all (Settings > Developer > Cover Cache, docs/modules/settings.md "Cover Cache").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Nothing new is built for it: the page is the Albums page's own asset (ui/m1plus_covlist.bin is tools/pod_ui.py build_grid_page without the toggle and the Cover Flow
 * button: the plain navbar, a stock list_view > scroll_view holding the one content view view_grid, the hidden text-style labels) and the Albums list mode's code path:
 * the rows are painted by the content view's own EVT_AFTER_PAINT with the shared list painter (patch/grid.c grid_list_paint: the press fill, the hairline, the title in
 * label_row_title and the artist in label_row_sub), moved left over the cover's room (a negative shift) and with no bitmap anywhere, so nothing is decoded and no
 * placeholder is drawn. A row is its album's title and, under it, the artist. The stock scroll_view does the scrolling (patch/scroll.c's gesture hook included). A tap (a release
 * within SC_DRAG_PX of the press on the same row) opens the album through cc_open_album, the Albums page's own call, so Back returns here.
 *
 * The rows are display positions of the album list (the order Albums shows, cc_album_order), made by the Cover Cache page's count (patch/homecover.c) and copied here; the
 * album list is loaded again once at open (cc_albums), held while the page is up and freed with the window. No timer, no hook.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define CV_W 320 /* the content's width: the list_view's */
#define CV_TAP_PX SC_DRAG_PX
#define CV_RING 12 /* tiles: the rows in view are at most GRID_VIEW_H / LIST_ROW_H + 2 */
#define CV_TEXT_X 16 /* the rows' text starts where the menu rows' do (no cover) */

static struct {
    void *win, *view, *sv, *status, *fade, *st_title, *st_sub;
    void *albums; /* cc_albums, for the rows' texts and cc_open_album */
    unsigned *order; /* cc_album_order: display position -> stock row (NULL: stock order) */
    unsigned short *idx; /* the rows: display positions, in order */
    unsigned n;
    int press, down, down_x, down_y; /* the pressed row + 1 (fill), the row a press began on + 1 and where */
    grid_t
        g; /* all zero: no bitmaps, no placeholder (grid_blit draws nothing); the painter only wants it for the cover */
    grid_tile_t ring[CV_RING];
} cv __attribute__((section(".scratch")));

static int cv_off(void) { return cv.sv ? I(cv.sv, SC_YOFF) : 0; }
static void cv_redraw(void) { widget_invalidate_force(cv.sv, (void *)0); }

/* The tile of row r: its texts made when the ring slot held another row. */
static grid_tile_t *cv_tile(void *ctx, int r) {
    grid_tile_t *t = &cv.ring[r % CV_RING];
    (void)ctx;
    if (t->album != r + 1) {
        void *rec = cc_row(cv.albums, cv.order, cv.idx[r]);
        memset(t, 0, sizeof *t);
        grid_set(t, cc_str(rec, REC_ALBUM), cc_str(rec, REC_ARTIST), 0);
        t->album = r + 1;
    }
    return t;
}

static int cv_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = cv_off(), r0, r1;
    (void)ctx;
    if (!canvas || !cv.view || !cv.n) return RET_OK;
    r0 = off / LIST_ROW_H, r1 = (off + GRID_VIEW_H - 1) / LIST_ROW_H;
    if (r0 < 0) r0 = 0; /* the offset is outside [0, max] while a drag pulls past an end: rows stay inside [0, n - 1] */
    if (r1 > (int)cv.n - 1) r1 = (int)cv.n - 1;
    if (r1 < r0) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    grid_list_paint(canvas, &cv.g, cv.st_title, cv.st_sub, r0, r1, off, GRID_VIEW_H, cv.press, CV_TEXT_X - LIST_TEXT_X,
                    1, cv_tile, (void *)0);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* The navbar's fade (an insensitive image, built hidden) shows while the list is scrolled. */
static int cv_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!cv.fade) return RET_OK;
    widget_set_visible(cv.fade, cv_off() > 0, 0);
    widget_set_sensitive(cv.fade, 0);
    return RET_OK;
}

static int cv_row_of(void *e) {
    int pt[2], r;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(cv.view, pt); /* includes the scroll offset */
    r = pt[1] < 0 ? -1 : pt[1] / LIST_ROW_H;
    return r < (int)cv.n ? r : -1;
}

static void cv_set_press(int p) {
    if (cv.press == p) return;
    cv.press = p;
    cv_redraw();
}

static int cv_on_down(void *ctx, void *e) {
    int r;
    (void)ctx;
    cv.down = 0;
    if (!e || !cv.view) return RET_OK;
    r = cv_row_of(e);
    cv.down = r + 1, cv.down_x = I(e, PE_X), cv.down_y = I(e, PE_Y);
    cv_set_press(r + 1);
    return RET_OK;
}

static int cv_abs(int v) { return v < 0 ? -v : v; }

static int cv_on_up(void *ctx, void *e) {
    int r = cv.down - 1;
    (void)ctx;
    cv.down = 0;
    cv_set_press(0);
    if (r < 0 || !e || !cv.view) return RET_OK;
    if (cv_abs(I(e, PE_X) - cv.down_x) < CV_TAP_PX && cv_abs(I(e, PE_Y) - cv.down_y) < CV_TAP_PX && cv_row_of(e) == r) {
        unsigned d = cv.idx[r];
        cc_open_album((void *)0, 0, (int)(cv.order ? cv.order[d] : d)); /* the stock row, as the Albums page opens it */
    }
    return RET_OK;
}

/* The scroll_view took the gesture as a drag, or the window went to the background: the press is forgotten. */
static int cv_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    cv.down = 0;
    cv_set_press(0);
    return RET_OK;
}

static int cv_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (cv.albums) deque_destroy(cv.albums);
    free(cv.order);
    free(cv.idx);
    memset(&cv, 0, sizeof cv);
    return RET_OK;
}

/* The list page: kind 0 No Art, 1 Missing Covers; idx[0..n) are display positions of the album list (copied). 0 once it is up, -1 when it could not open. */
int covlist_open(int kind, const unsigned short *idx, unsigned n) {
    unsigned m, i;
    void *title;
    if (cv.win) return -1;
    memset(&cv, 0, sizeof cv);
    cv.win = window_open("m1plus_covlist");
    if (!cv.win) return -1;
    widget_on(cv.win, EVT_DESTROY, cv_on_destroy, (void *)0);
    pod_bind(cv.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(cv.win, "btn_backtoplayer", pod_on_player, (void *)0);
    cv.view = widget_lookup(cv.win, "view_grid", 1);
    cv.sv = widget_lookup(cv.win, "covlist_scrollview", 1);
    cv.status = widget_lookup(cv.win, "label_status", 1);
    cv.fade = widget_lookup(cv.win, "img_nb_fade", 1); /* optional */
    cv.st_title = widget_lookup(cv.win, "label_row_title", 1);
    cv.st_sub = widget_lookup(cv.win, "label_row_sub", 1);
    if (!cv.view || !cv.sv || !cv.status || !cv.st_title || !cv.st_sub) {
        navigator_back(); /* an asset that is not ours */
        return -1;
    }
    title = widget_lookup(cv.win, "label_title", 1);
    if (kind)
        widget_set_tr_text(title, "Missing Covers");
    else
        widget_set_tr_text(title, "No Art");
    cv.albums = cc_albums();
    cv.order = cc_album_order(cv.albums);
    m = cv.albums ? deque_size(cv.albums) : 0;
    cv.idx = n ? calloc(n, sizeof *cv.idx) : (unsigned short *)0;
    for (i = 0; cv.idx && i < n; ++i)
        if (idx[i] < m) cv.idx[cv.n++] = idx[i]; /* (a position the library no longer has is dropped) */
    if (!cv.n) {
        widget_set_visible(cv.view, 0, 0);
        widget_set_sensitive(cv.view, 0);
        widget_set_visible(cv.status, 1, 0);
        widget_set_sensitive(cv.status, 1);
        widget_set_tr_text(cv.status, "No albums");
        return 0;
    }
    widget_set_visible(cv.status, 0, 0);
    widget_set_sensitive(cv.status, 0);
    widget_resize(cv.view, CV_W, (int)cv.n * LIST_ROW_H);
    widget_set_prop_int(cv.sv, "virtual_h", (int)cv.n * LIST_ROW_H);
    widget_on(cv.sv, EVT_SCROLL, cv_on_scroll, (void *)0);
    widget_on(cv.sv, EVT_SCROLL_END, cv_on_scroll, (void *)0);
    widget_on(cv.win, EVT_WINDOW_TO_BG, cv_on_abort, (void *)0);
    widget_on(cv.view, EVT_POINTER_DOWN, cv_on_down, (void *)0);
    widget_on(cv.view, EVT_POINTER_UP, cv_on_up, (void *)0);
    widget_on(cv.view, EVT_POINTER_ABORT, cv_on_abort, (void *)0);
    widget_on(cv.view, EVT_AFTER_PAINT, cv_on_paint, (void *)0);
    return 0;
}
