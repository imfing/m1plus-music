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
#include "songops.h"
#include "pins.h"

int rowmenu_zone_x(int right) { return right - RM_MORE_W; }

/* The glyph bitmap's left edge: centred in the zone, or its right edge on `right` (flush). */
static int rm_glyph_x(int right, int flush) {
    return flush ? right - RM_DOTS_PX : rowmenu_zone_x(right) + (RM_MORE_W - RM_DOTS_PX) / 2;
}

int rowmenu_text_end(int right, int flush) { return rm_glyph_x(right, flush) + RM_INK_X - RM_INK_GAP; }

/* The long press: one timer for the page that has the finger down (a page's touch is one at a time). */
static struct {
    unsigned timer;
    int row;
    rowmenu_hold_fn fn;
} rm_hold __attribute__((section(".scratch")));

void rowmenu_hold_stop(void) { m1_timer_stop(&rm_hold.timer); }

static int rm_on_hold(const void *unused) {
    rowmenu_hold_fn fn = rm_hold.fn;
    (void)unused;
    rm_hold.timer = 0;
    if (fn) fn(rm_hold.row);
    return RET_OK;
}

void rowmenu_hold_start(int row, rowmenu_hold_fn fn) {
    rowmenu_hold_stop();
    rm_hold.row = row, rm_hold.fn = fn;
    rm_hold.timer = timer_add(rm_on_hold, (void *)0, RM_LONG_MS);
}

void rowmenu_hold_move(const m1_tap_t *t, void *e) {
    if (rm_hold.timer && !m1_tap_near(t, e)) rowmenu_hold_stop();
}

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
    rowmenu_hold_stop();
    rm->open = 0;
    rm->add = (rowmenu_add_fn)0;
    rm->queue = (rowmenu_queue_fn)0;
    if (rm->rows) deque_destroy(rm->rows);
    rm->rows = (void *)0;
    m1_scrim(rm->scrim, 0);
    m1_show(rm->card, 0);
    rm->src = (const lib_src_t *)0;
}

/* The toast of each refusal, translated (UPNEXT_*, docs/modules/queue.md); keys in tools/pod_i18n.py. A row whose file is not found: "File not found" with the card
 * in, "Storage unavailable" without it (so_missing). */
static const char *rm_refusal(int r) {
    if (r == UPNEXT_MISSING) return so_missing();
    return TR(r == UPNEXT_STREAM    ? "Not available while streaming"
              : r == UPNEXT_FOLDER  ? "Not available for folder playback"
              : r == UPNEXT_PODCAST ? "Not available for podcasts"
              : r == UPNEXT_FULL    ? "Queue is full"
              : r == UPNEXT_MEMORY  ? "Not enough memory"
              : r == UPNEXT_DLNA    ? "Not available while DLNA is on"
                                    : "msg_addfailed"); /* UPNEXT_EMPTY: nothing to add (the stock "Adding Failed") */
}

void rowmenu_upnext_toast(int r, int after) {
    if (r == UPNEXT_ADDED)
        pod_toast(TR(after ? "Added to Queue" : "Playing Next"));
    else if (r < 0)
        pod_toast(rm_refusal(r)); /* (UPNEXT_STARTED: playback started, nothing to say and nothing to open) */
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
    rowmenu_upnext_toast(r, after);
}

/* Pin Song / Unpin Song on the row's copy. The pins' own toast says when six are pinned already. */
static void rm_pin_song(rowmenu_t *rm) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0;
    if (rec) {
        if (pins_has_song(cc_str(rec, REC_PATH), I(rec, REC_CUE_START)))
            pins_unpin_song(cc_str(rec, REC_PATH), I(rec, REC_CUE_START));
        else
            pins_pin_song(rec);
    }
    rowmenu_close(rm);
}

/* Remove from Playlist: the page removes the row the copy is of (its own row id, not an index of a list that may have been read again), then the copy goes. */
static void rm_remove(rowmenu_t *rm) {
    void *rows = rm->rows, *rec = rows ? deque_at(rows, 0) : (void *)0;
    rowmenu_remove_fn fn = rm->rm_row ? rm->remove : (rowmenu_remove_fn)0;
    rm->rows = (void *)0;
    rowmenu_close(rm);
    if (rec && fn) fn(rec);
    if (rows) deque_destroy(rows);
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
    if (rm->queued || rm->alt) { /* the Queue, pins or album sheet: the page does the act once the sheet is gone */
        rowmenu_queue_fn fn = rm->queue;
        int row = rm->row, act = rm->act[s->k];
        rowmenu_close(rm);
        if (fn) fn(row, act);
        return RET_OK;
    }
    if (s->k == RM_REMOVE_ROW) {
        rm_remove(rm);
    } else if (s->k == RM_PIN_ROW) {
        if (rm->pin) rm_pin_song(rm);
    } else if (rm->src && s->k == 2) {
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
        rowmenu_upnext_toast(r, s->k);
    }
    return RET_OK;
}

/* A widget of the menu: "<prefix>_<what><k>" (k < 0: no index), rm_* for the sheet, rp_* for the popup. */
static void *rm_widget(const rowmenu_t *rm, const char *what, int k) {
    char name[24];
    if (k < 0)
        snprintf(name, sizeof name, "%s_%s", rm->popup ? "rp" : "rm", what);
    else
        snprintf(name, sizeof name, "%s_%s%d", rm->popup ? "rp" : "rm", what, k);
    return widget_lookup(rm->win, name, 1);
}

static int rm_bind(rowmenu_t *rm, void *win, int rows, int popup) {
    int i, ok;
    memset(rm, 0, sizeof *rm);
    rm->win = win, rm->popup = popup;
    rm->scrim = rm_widget(rm, "scrim", -1);
    if (rm->scrim) widget_on(rm->scrim, EVT_CLICK, rm_on_scrim, rm);
    rm->card = rm_widget(rm, "card", -1);
    ok = rm->scrim && rm->card;
    rm->nitems = rows;
    for (i = 0; i < rows; ++i) {
        rm->slot[i].rm = rm, rm->slot[i].k = i, rm->act[i] = (signed char)i;
        rm->item[i] = rm_widget(rm, "item", i);
        rm->label[i] = rm_widget(rm, "label", i);
        if (rm->item[i]) widget_on(rm->item[i], EVT_CLICK, rm_on_item, &rm->slot[i]);
        ok = ok && rm->item[i];
    }
    for (i = 0; i < RM_HAIRS; ++i) rm->hair[i] = rm_widget(rm, "hair", i);
    if (popup) { /* (no "..." of its own: the page's navbar button opens it) */
        m1_scrim(rm->scrim, 0);
        m1_show(rm->card, 0);
        rm->on = ok, rm->queued = 1;
        return ok;
    }
    if (rows == RM_ROWS) {
        rm->fav_label = widget_lookup(win, "rm_label3", 1);
        rm->fav_icon = widget_lookup(win, "rm_icon3", 1);
        rm->dl_label = widget_lookup(win, "rm_label2", 1);
        rm->dl_icon = widget_lookup(win, "rm_icon2", 1);
        rm->pin_label = widget_lookup(win, "rm_label5", 1);
        rm->pin_icon = widget_lookup(win, "rm_icon5", 1);
    }
    m1_scrim(rm->scrim, 0);
    m1_show(rm->card, 0);
    if (!ok) return 0;
    rm->dots = rm_make_dots(win);
    rm->on = rm->dots != (void *)0;
    return rm->on;
}

/* Lays the sheet out from `seq`, top to bottom: the asset's row indices, RM_BREAK between two groups. The rows listed are shown PM_ROW_H apart, the others hidden; a hairline (rm_hair<k>) sits on the
 * top edge of the first row of every group but the first (none inside a group, none above the first row); the card is as high as the rows, on the window's foot, in the glass of that many rows
 * (pc_sheet<n>, 1..7). */
#define RM_BREAK (-1)

/* The popup's place and width (rowmenu_bind_popup): the view-sort card's (patch/viewsort.c vs_fit, its action-only form): under the navbar at PL_CARD_RIGHT / PL_CARD_Y, as wide as the widest label
 * from its x plus the slack and the margin, VS_CARD_MIN..PL_CARD_MAX (a label that cannot be measured: PL_CARD_MAX), the rows, labels and hairlines that wide, the glass of n rows (vs_glass<n>). */
static void rm_popup_fit(rowmenu_t *rm, const signed char *seq, int len, int h, int n) {
    int i, w = 0, ok = 1, lx = VS_TICK_X + VS_LABEL_X_GLYPH - VS_GLYPH_X;
    char glass[16];
    for (i = 0; i < len && ok; ++i) {
        const unsigned *t;
        int k = seq[i], tw;
        if (k < 0 || k >= rm->nitems || !rm->label[k]) continue;
        t = widget_get_text(rm->label[k]);
        tw = t && *t ? m1_text_w(rm->label[k], t) : 0;
        if (tw <= 0)
            ok = 0;
        else if (lx + tw > w)
            w = lx + tw;
    }
    if (ok) {
        w += VS_TEXT_SLACK + VS_LABEL_R; /* (the slack: a label exactly as wide as its text gets an ellipsis) */
        if (w < VS_CARD_MIN) w = VS_CARD_MIN;
        if (w > PL_CARD_MAX) w = PL_CARD_MAX;
    } else
        w = PL_CARD_MAX;
    for (i = 0; i < rm->nitems; ++i) {
        if (rm->item[i]) widget_resize(rm->item[i], w, PM_ROW_H);
        if (rm->label[i]) widget_resize(rm->label[i], w - lx - VS_LABEL_R, PM_ROW_H);
    }
    for (i = 0; i < RM_HAIRS; ++i)
        if (rm->hair[i]) widget_resize(rm->hair[i], w, 1);
    widget_move(rm->card, PL_CARD_RIGHT - w, PL_CARD_Y);
    widget_resize(rm->card, w, h);
    snprintf(glass, sizeof glass, VS_GLASS_FMT, n);
    widget_set_prop_str(rm->card, "style:normal:bg_image", glass);
}

static void rm_layout(rowmenu_t *rm, const signed char *seq, int len) {
    static const char *const glass[] = {"",          "pc_sheet1", "pc_sheet2", "pc_sheet3",
                                        "pc_sheet4", "pc_sheet5", "pc_sheet6", "pc_sheet7"};
    int i, y = 0, n = 0, h = 0, brk = 0;
    for (i = 0; i < rm->nitems; ++i) m1_show(rm->item[i], 0);
    for (i = 0; i < RM_HAIRS; ++i)
        if (rm->hair[i]) widget_set_visible(rm->hair[i], 0, 0);
    for (i = 0; i < len; ++i) {
        int k = seq[i];
        if (k == RM_BREAK) {
            brk = n > 0;
            continue;
        }
        if (k < 0 || k >= rm->nitems || !rm->item[k]) continue;
        if (brk && h < RM_HAIRS) {
            if (rm->hair[h]) {
                widget_move(rm->hair[h], 0, y);
                widget_set_visible(rm->hair[h], 1, 0); /* (insensitive: a touch on the line is the row's) */
            }
            ++h;
        }
        brk = 0;
        widget_move(rm->item[k], 0, y);
        m1_show(rm->item[k], 1);
        y += PM_ROW_H, ++n;
    }
    if (!rm->card || n < 1 || n >= (int)(sizeof glass / sizeof glass[0])) return;
    if (rm->popup) {
        rm_popup_fit(rm, seq, len, y, n);
        return;
    }
    widget_move(rm->card, 0, AH_WIN_H - y);
    widget_resize(rm->card, PM_DIALOG_W, y);
    widget_set_prop_str(rm->card, "style:normal:bg_image", glass[n]);
}

/* Row k's words and glyph (the widgets <prefix>_label<k> / <prefix>_icon<k>). */
static void rm_words(rowmenu_t *rm, int k, const char *text, const char *glyph) {
    void *l = rm_widget(rm, "label", k), *g = rm_widget(rm, "icon", k);
    if (l) widget_set_tr_text(l, text);
    if (g) widget_set_prop_str(g, "image", glyph);
}

static void rm_show(rowmenu_t *rm, int row, rowmenu_queue_fn fn) {
    rm->row = row, rm->queue = fn, rm->open = 1;
    m1_scrim(rm->scrim, 1);
    m1_show(rm->card, 1);
}

int rowmenu_open_rows(rowmenu_t *rm, int row, const rowmenu_row_t *rows, int n, rowmenu_queue_fn fn) {
    signed char seq[2 * RM_ROWS];
    int i, k = 0, len = 0;
    if (!rm->on || rm->open || !fn) return 0;
    for (i = 0; i < n && len < (int)sizeof seq; ++i) {
        if (!rows[i].text) {
            seq[len++] = RM_BREAK;
            continue;
        }
        if (k >= rm->nitems) break;
        rm_words(rm, k, rows[i].text, rows[i].glyph);
        rm->act[k] = (signed char)rows[i].act;
        seq[len++] = (signed char)k++;
    }
    if (!k) return 0;
    rm_layout(rm, seq, len);
    rm->alt = 1, rm->src = (const lib_src_t *)0;
    rm_show(rm, row, fn);
    return 1;
}

int rowmenu_open_album(rowmenu_t *rm, int row, int pinned, rowmenu_queue_fn fn) {
    const rowmenu_row_t rows[] = {{"Play", "rm_ic_pplay", RMA_PLAY},
                                  {"Shuffle", "rm_ic_pshuffle", RMA_SHUFFLE},
                                  RM_GROUP,
                                  {pinned ? "Unpin Album" : "Pin Album", pinned ? "rm_ic_unpin" : "rm_ic_pin", RMA_PIN},
                                  {"Add to Playlist", "rm_ic_add", RMA_ADD},
                                  RM_GROUP,
                                  {"Play Next", "rm_ic_next", RMA_NEXT},
                                  {"Play After", "rm_ic_after", RMA_AFTER}};
    return rowmenu_open_rows(rm, row, rows, (int)(sizeof rows / sizeof rows[0]), fn);
}

int rowmenu_bind(rowmenu_t *rm, void *win) { return rm_bind(rm, win, RM_ROWS, 0); }

int rowmenu_bind_popup(rowmenu_t *rm, void *win) { return rm_bind(rm, win, RM_POPUP_ROWS, 1); }

int rowmenu_bind_queue(rowmenu_t *rm, void *win) {
    int on = rm_bind(rm, win, RM_QUEUE_ROWS, 0);
    rm->queued = 1;
    return on;
}

int rowmenu_bind_album(rowmenu_t *rm, void *win) {
    int on = rm_bind(rm, win, RM_ALBUM_ROWS, 0);
    rm->queued = 1;
    return on;
}

int rowmenu_open_queue(rowmenu_t *rm, int row, rowmenu_queue_fn fn) {
    static const signed char seq[] = {0, 1, RM_BREAK, 2};
    int i;
    if (!rm->on || !rm->queued || rm->open || !fn) return 0;
    for (i = 0; i < rm->nitems; ++i) rm->act[i] = (signed char)i;
    rm_layout(rm, seq, (int)sizeof seq);
    rm->alt = 0;
    rm_show(rm, row, fn);
    return 1;
}

void rowmenu_free(rowmenu_t *rm) {
    rowmenu_hold_stop();
    if (rm->rows) deque_destroy(rm->rows);
    if (rm->dots) bitmap_destroy(rm->dots);
    memset(rm, 0, sizeof *rm);
}

void rowmenu_paint(void *canvas, const rowmenu_t *rm, int right, int flush, int y, int row_h, int view_h) {
    int cy = y + (row_h - 1 - RM_DOTS_PX) / 2, top = cy < 0 ? -cy : 0,
        bottom = cy + RM_DOTS_PX > view_h ? view_h - cy : RM_DOTS_PX, src[4], dst[4];
    if (!rm->on || !rm->dots || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = RM_DOTS_PX, src[3] = bottom - top;
    dst[0] = rm_glyph_x(right, flush), dst[1] = cy + top, dst[2] = RM_DOTS_PX, dst[3] = bottom - top;
    canvas_draw_image(canvas, rm->dots, src, dst);
}

/* The third row's words and glyph: Add to Playlist for the stock library; for a source Download, Cancel Download (waiting or running) or Remove Download (on the card). */
static void rm_third(rowmenu_t *rm, const ls_row_t *x) {
    const char *text = "Add to Playlist", *icon = "rm_ic_add";
    if (rm->src) {
        if (x->dl == LS_DL_DONE)
            text = "Remove Download", icon = "pc_ic_trash", rm->dl = LS_ACT_DELETE_DL;
        else if (x->dl == LS_DL_WAIT || x->dl == LS_DL_ACTIVE)
            text = "Cancel Download", icon = "rm_ic_cxdl", rm->dl = LS_ACT_CANCEL_DL;
        else
            text = "Download", icon = "rm_ic_dl", rm->dl = LS_ACT_DOWNLOAD;
    }
    if (rm->dl_label) widget_set_tr_text(rm->dl_label, text);
    if (rm->dl_icon) widget_set_prop_str(rm->dl_icon, "image", icon);
}

/* The track sheet's rows in three groups: Pin Song / Unpin Song (a song of the card: no source, a path the pins can hold), Add to Playlist (a source's Download row), Favorite, Get Info | Play Next,
 * Play After | Remove from Playlist (a page that has it, rowmenu_set_remove, for a playlist song record: REC_ID over PL_MAX). The glass is as many rows high as are shown. */
static void rm_track_rows(rowmenu_t *rm, void *rec) {
    const char *path = cc_str(rec, REC_PATH);
    signed char seq[2 * RM_ROWS];
    int len = 0;
    rm->pin =
        !rm->src && rm->pin_label && rm->pin_icon && rm->item[RM_PIN_ROW] && pins_song_ok(path, I(rec, REC_CUE_START));
    if (rm->pin) {
        int has = pins_has_song(path, I(rec, REC_CUE_START));
        widget_set_tr_text(rm->pin_label, has ? "Unpin Song" : "Pin Song");
        widget_set_prop_str(rm->pin_icon, "image", has ? "rm_ic_unpin" : "rm_ic_pin");
        seq[len++] = RM_PIN_ROW;
    }
    rm->rm_row = !rm->src && rm->remove && rm->item[RM_REMOVE_ROW] && I(rec, REC_ID) > PL_MAX;
    seq[len++] = 2, seq[len++] = 3, seq[len++] = 4, seq[len++] = RM_BREAK;
    seq[len++] = 0, seq[len++] = 1;
    if (rm->rm_row) seq[len++] = RM_BREAK, seq[len++] = RM_REMOVE_ROW;
    rm_layout(rm, seq, len);
}

void rowmenu_set_remove(rowmenu_t *rm, rowmenu_remove_fn fn) { rm->remove = fn; }

int rowmenu_open_src(rowmenu_t *rm, int row, void *rec, rowmenu_add_fn add, const lib_src_t *src) {
    void *d;
    ls_row_t x;
    if (src == &lib_stock) src = (const lib_src_t *)0;
    if (!rm->on || rm->open || !rec) return 0;
    if (rm->alt) { /* rowmenu_open_rows was the last: the track sheet's words again (rows 2, 3 and 5 are set below at every open; row 6 is never reworded: no such sheet has seven rows) */
        rm_words(rm, 0, "Play Next", "rm_ic_next");
        rm_words(rm, 1, "Play After", "rm_ic_after");
        rm_words(rm, 4, "Get Info", "rm_ic_info");
        rm->alt = 0;
    }
    d = so_row_deque(rec); /* a copy (the page's list may be replaced while the menu is open) */
    if (!d) return 0;
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
    rm_track_rows(rm, rec);
    rm->rows = d, rm->row = row, rm->add = add, rm->open = 1;
    m1_scrim(rm->scrim, 1);
    m1_show(rm->card, 1);
    return 1;
}
