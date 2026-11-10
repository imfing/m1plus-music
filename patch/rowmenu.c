/* M1+ Music track rows' "..." menu: Play Next, Play After, Add to Playlist, Favorite, Get Info (docs/modules/rowmenu.md has the design, the geometry and the device checklist).
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
#include "songinfo.h"
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
    rm->src = (const lib_src_t *)0;
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

/* Favorite / Undo Favorite: stock's own star calls (manage_myfav 0x4ef884: checkFavExist, then deleteMusicFromFav or addMyFav, on the record; Now Playing's star and the Playlists page's Favorites
 * list read the same myfav table) on the row's copy. The answer is read again: a call that changed nothing is "Adding Failed". */
static void rm_favorite(rowmenu_t *rm) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0;
    int was, now;
    if (!rec) {
        rowmenu_close(rm);
        return;
    }
    if (rm->src) { /* a source's track: its own star (the label the menu opened with says which way it goes), the row re-paints from the source's gen */
        const lib_src_t *src = rm->src;
        was = rm->fav;
        rm->rows =
            (void
                 *)0; /* the record lives until the act has read it (rowmenu_close would destroy it), like the download action */
        rowmenu_close(rm);
        ls_favorite(src, rec, was);
        deque_destroy(rows);
        return;
    }
    was = checkFavExist(rec) != 0;
    if (was)
        deleteMusicFromFav(rec);
    else
        addMyFav(rec);
    now = checkFavExist(rec) != 0;
    rowmenu_close(rm);
    pod_toast(TR(now == was ? "msg_addfailed" : now ? "Added to Favorites" : "Removed from Favorites"));
}

/* The third row of a source's sheet: Download, Cancel Download, Remove Download through the source (the row's state changes with its gen). */
static void rm_download(rowmenu_t *rm) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0;
    const lib_src_t *src = rm->src;
    int what = rm->dl;
    rm->rows = (void *)0;
    rowmenu_close(rm);
    if (rec && src && src->act) src->act(src, rec, what);
    if (rows) deque_destroy(rows);
}

/* Play Next / Play After for a source's row: its queue record (a stream address or the local file) through upnext_add; an undownloaded DSD row asks to be downloaded instead. */
static void rm_queue_src(rowmenu_t *rm, int after) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0, *q;
    const lib_src_t *src = rm->src;
    ls_row_t x;
    int r;
    rm->rows = (void *)0;
    rowmenu_close(rm);
    if (!rec || !src || !src->queue_row) {
        if (rows) deque_destroy(rows);
        return;
    }
    memset(&x, 0, sizeof x);
    if (src->row) src->row(src, rec, &x);
    if (x.dsd && x.dl != LS_DL_DONE) { /* DSD plays from the card only */
        ls_dsd_confirm(src, rows, 0);
        deque_destroy(rows);
        return;
    }
    q = src->queue_row(src, rec); /* (it shows why when it cannot) */
    deque_destroy(rows);
    if (!q) return;
    r = upnext_add(q, after);
    deque_destroy(q);
    if (r == UPNEXT_ADDED)
        pod_toast(TR(after ? "Added to Queue" : "Playing Next"));
    else if (r < 0)
        pod_toast(TR(rm_refusal(r)));
}

/* Get Info: the page opens on the row's copy (it copies what it shows), then the copy goes. */
static void rm_info(rowmenu_t *rm) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0;
    rm->rows = (void *)0;
    rowmenu_close(rm);
    if (rec) songinfo_open(rec);
    if (rows) deque_destroy(rows);
}

static int rm_on_item(void *ctx, void *e) {
    struct rowmenu_slot *s = (struct rowmenu_slot *)ctx;
    rowmenu_t *rm = s->rm;
    (void)e;
    if (!rm->open) return RET_OK;
    if (rm->src && s->k == 2) {
        rm_download(rm);
    } else if (rm->src && s->k < 2) {
        rm_queue_src(rm, s->k);
    } else if (s->k == 3) {
        rm_favorite(rm);
    } else if (s->k == 4) {
        rm_info(rm);
    } else if (s->k == 2) { /* Add to Playlist: the page's one-row selection and picker, once the menu is gone */
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
    static const char *const ITEMS[RM_ROWS] = {"rm_item0", "rm_item1", "rm_item2", "rm_item3", "rm_item4"};
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
    rm->fav_label = widget_lookup(win, "rm_label3", 1);
    rm->fav_icon = widget_lookup(win, "rm_icon3", 1);
    rm->dl_label = widget_lookup(win, "rm_label2", 1);
    rm->dl_icon = widget_lookup(win, "rm_icon2", 1);
    rm_show(rm->scrim, 0);
    rm_show(rm->card, 0);
    if (!ok) return 0;
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
    return rowmenu_open_src(rm, row, rec, add, (const lib_src_t *)0);
}

/* The third row's words and glyph: Add to Playlist for the stock library; for a source Download, Cancel Download (waiting or running) or Remove Download (on the card). */
static void rm_third(rowmenu_t *rm, const ls_row_t *x) {
    const char *text = "Add to Playlist", *icon = "rm_ic_add";
    if (rm->src) {
        if (x->dl == LS_DL_DONE)
            text = "Remove Download", icon = "rm_ic_rmdl", rm->dl = LS_ACT_DELETE_DL;
        else if (x->dl == LS_DL_WAIT || x->dl == LS_DL_ACTIVE)
            text = "Cancel Download", icon = "rm_ic_cxdl", rm->dl = LS_ACT_CANCEL_DL;
        else
            text = "Download", icon = "rm_ic_dl", rm->dl = LS_ACT_DOWNLOAD;
    }
    if (rm->dl_label) widget_set_tr_text(rm->dl_label, text);
    if (rm->dl_icon) widget_set_prop_str(rm->dl_icon, "image", icon);
}

int rowmenu_open_src(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add, const lib_src_t *src) {
    void *d;
    ls_row_t x;
    if (src == &lib_stock) src = (const lib_src_t *)0;
    if (!rm->on || rm->open || !rec) return 0;
    d = _create_deque("stSongInfo");
    if (!d) return 0;
    deque_init(d);
    _deque_push_back(
        d, rec); /* a copy, as the stock queries push rows (the page's list may be replaced while the menu is open) */
    if (deque_size(d) != 1) {
        deque_destroy(d);
        return 0;
    }
    memset(&x, 0, sizeof x);
    if (src && src->row) src->row(src, rec, &x);
    rm->src = src;
    rm->fav = src ? x.fav != 0 : checkFavExist(rec) != 0; /* (the sheet shows the state of this row now) */
    rm_third(rm, &x);
    if (rm->fav_label) widget_set_tr_text(rm->fav_label, rm->fav ? "Undo Favorite" : "Favorite");
    if (rm->fav_icon) widget_set_prop_str(rm->fav_icon, "image", rm->fav ? "rm_ic_unfav" : "rm_ic_fav");
    rm->rows = d, rm->row = row, rm->add = add, rm->open = 1;
    rm_show(rm->scrim, 1);
    rm_show(rm->card, 1);
    return 1;
}
