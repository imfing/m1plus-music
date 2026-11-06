/* M1+ Music track rows' "..." menu: Play Next, Play After, Add to Playlist (docs/modules/rowmenu.md has the design, the geometry and the device checklist).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Shared by the album page and the Songs page. Each page paints the grey "..." at the right end of its rows and hit-tests it with the same press and drag rules as its row tap; this file
 * is what happens after: the bottom sheet (Now Playing's More sheet's look, laid out by the asset) shows over a scrim that closes it, and a
 * row of the sheet runs Play Next / Play After (a one-row deque holding a copy of the row's stSongInfo through upnext_add, patch/upnext.c) or hands Add to Playlist back to the page
 * (its one-row selection and the picker). The widgets are the page asset's (tools/pod_ui.py row_menu): the hidden, insensitive scrim and card, last in z-order. No hook, no timer.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "i18n.h"
#include "upnext.h"
#include "rowmenu.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */

static void rm_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

int rowmenu_zone_x(int right) { return right - RM_MORE_W; }

/* The "..." as a bitmap: the image rm_dots is white on transparent (cc_decode flattens it over black, so the red channel is the coverage), the bitmap's alpha is that coverage and its
 * colour RM_DOTS_RGB. */
static void *rm_make_dots(void *win) {
    unsigned *px, i;
    void *b = bitmap_create_ex(RM_DOTS_PX, RM_DOTS_PX, RM_DOTS_PX * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != RM_DOTS_PX * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, "rm_dots", 1, RM_DOTS_PX, 1, px);
    for (i = 0; ok && i < RM_DOTS_PX * RM_DOTS_PX; ++i) px[i] = (px[i] & 0xff) << 24 | RM_DOTS_RGB;
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

void rowmenu_close(rowmenu_t *rm) {
    rm->open = 0;
    rm->add = (rowmenu_add_fn)0;
    if (rm->rows) deque_destroy(rm->rows);
    rm->rows = (void *)0;
    rm_show(rm->scrim, 0);
    rm_show(rm->card, 0);
}

/* The toast of each refusal (UPNEXT_*, docs/modules/queue.md); keys in tools/pod_i18n.py. */
static const char *rm_refusal(int r) {
    return r == UPNEXT_STREAM    ? "Not available while streaming"
           : r == UPNEXT_FOLDER  ? "Not available for folder playback"
           : r == UPNEXT_PODCAST ? "Not available for podcasts"
           : r == UPNEXT_MISSING ? "Storage unavailable"
           : r == UPNEXT_FULL    ? "Queue is full"
           : r == UPNEXT_MEMORY  ? "Not enough memory"
           : r == UPNEXT_DLNA    ? "Not available while DLNA is on"
                                 : "msg_addfailed"; /* UPNEXT_EMPTY: nothing to add (the stock "Adding Failed") */
}

static int rm_on_scrim(void *ctx, void *e) {
    (void)e;
    rowmenu_close((rowmenu_t *)ctx);
    return RET_OK;
}

static int rm_on_item(void *ctx, void *e) {
    struct rowmenu_slot *s = (struct rowmenu_slot *)ctx;
    rowmenu_t *rm = s->rm;
    (void)e;
    if (!rm->open) return RET_OK;
    if (s->k == 2) { /* Add to Playlist: the page's one-row selection and picker, once the menu is gone */
        rowmenu_add_fn add = rm->add;
        int row = rm->row;
        rowmenu_close(rm);
        if (add) add(row);
    } else { /* Play Next / Play After: the row's copy through upnext_add, the deque destroyed, the menu closed, then the toast */
        void *rows = rm->rows;
        int r;
        rm->rows = (void *)0;
        r = rows ? upnext_add(rows, s->k) : UPNEXT_EMPTY;
        if (rows) deque_destroy(rows);
        rowmenu_close(rm);
        if (r == UPNEXT_ADDED)
            pod_toast(TR(s->k ? "Added to Queue" : "Playing Next"));
        else if (r < 0)
            pod_toast(TR(rm_refusal(r))); /* (UPNEXT_STARTED: playback started, nothing to say and nothing to open) */
    }
    return RET_OK;
}

int rowmenu_bind(rowmenu_t *rm, void *win) {
    static const char *const ITEMS[RM_ROWS] = {"rm_item0", "rm_item1", "rm_item2"};
    int i, ok;
    memset(rm, 0, sizeof *rm);
    rm->win = win;
    rm->scrim = pod_bind(win, "rm_scrim", rm_on_scrim, rm);
    rm->card = widget_lookup(win, "rm_card", 1);
    ok = rm->scrim && rm->card;
    for (i = 0; i < RM_ROWS; ++i) {
        rm->slot[i].rm = rm, rm->slot[i].k = i;
        rm->item[i] = pod_bind(win, ITEMS[i], rm_on_item, &rm->slot[i]);
        ok = ok && rm->item[i];
    }
    rm_show(rm->scrim, 0);
    rm_show(rm->card, 0);
    if (!ok || home_off()) return 0;
    rm->dots = rm_make_dots(win);
    rm->on = rm->dots != (void *)0;
    return rm->on;
}

void rowmenu_free(rowmenu_t *rm) {
    if (rm->rows) deque_destroy(rm->rows);
    if (rm->dots) bitmap_destroy(rm->dots);
    memset(rm, 0, sizeof *rm);
}

void rowmenu_paint(void *canvas, const rowmenu_t *rm, int right, int flush, int y, int row_h, int view_h) {
    int cy = y + (row_h - 1 - RM_DOTS_PX) / 2, top = cy < 0 ? -cy : 0,
        bottom = cy + RM_DOTS_PX > view_h ? view_h - cy : RM_DOTS_PX, src[4], dst[4];
    if (!rm->on || !rm->dots || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = RM_DOTS_PX, src[3] = bottom - top;
    dst[0] = flush ? right - RM_DOTS_PX : rowmenu_zone_x(right) + (RM_MORE_W - RM_DOTS_PX) / 2, dst[1] = cy + top,
    dst[2] = RM_DOTS_PX, dst[3] = bottom - top;
    canvas_draw_image(canvas, rm->dots, src, dst);
}

int rowmenu_open(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add) {
    void *d;
    if (!rm->on || rm->open || !rec || home_off()) return 0;
    d = _create_deque("stSongInfo");
    if (!d) return 0;
    deque_init(d);
    _deque_push_back(
        d, rec); /* a copy, as the stock queries push rows (the page's list may be replaced while the menu is open) */
    if (deque_size(d) != 1) {
        deque_destroy(d);
        return 0;
    }
    rm->rows = d, rm->row = row, rm->add = add, rm->open = 1;
    rm_show(rm->scrim, 1);
    rm_show(rm->card, 1);
    return 1;
}
