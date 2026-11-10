/* M1+ Music Now Playing More menu: the stock playmore_dialog (the sheet Now Playing's More button opens: ui/dialog/
 * playmore_dialog.bin, seven list_item rows listitem0..6) as an iOS style bottom sheet with two pages.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The sheet is as high as its page's rows (page 1: PM_PAGE_N = 6 x 50 = 300 px, page 2: PM_PAGE2_N = 6 x 50 = 300 px) and sits on the bottom of the screen; the page
 * above it is dimmed by the asset's own dialog highlight (highlight="default(alpha=..)", the AWTK dialog highlighter the window
 * manager sets up when the dialog opens). The glass is the dialog's first child, an insensitive image (pod_glass) that gets the page's own picture and height
 * (pm_sheet6, 300 px, both pages): never a crop of a taller one. Page 1 (when it opens): Look up album (listitem4), Look up artist (5), Add to playlist
 * (2), Cassette Mode (pod_tape, the asset's: it opens the landscape cassette page, patch/tape.c), Vinyl Mode (pod_vinyl: the turntable page, patch/vinyl.c) and "More" (pod_more, a row the asset adds, hidden until now; a chevron
 * at its right). A tap on More switches to page 2: a header row "< More" (pod_back, also the asset's; a tap returns to page 1), Playback speed (1), Sleep Timer (pod_sleep: a link to the stock Power page), A-B repeat (0), Find Cover & Lyrics (pod_art) and
 * Delete (6, its label red in the asset). Online search (3) is never shown. A switch only hides one row set and shows the other and sets the sheet to the page's height;
 * there is no slide. A tap above the sheet closes it: that is the stock handler's (pointer y < dialog y), which works unchanged with the new y.
 *
 * One hook, dialog_playmore_dialog_init (0x479cc4): run when the dialog is built (a tap on Now Playing's More button, never
 * at boot or in the main loop). m1plus_playmore_init runs the stock init to completion (it binds every row's handler and the
 * speed / A-B widgets, which keep their stock handlers: we move rows, we do not replace behaviour; it also pins the sheet at
 * y 130) and then, if every widget of the asset is there, arranges page 1
 * and anchors the sheet. Everything fallible (the widget lookups, the handlers, the labels' texts) is done before the first
 * row moves, so any failure leaves the stock seven rows (pod_more, pod_back, pod_tape and pod_vinyl stay hidden and insensitive in the asset).
 *
 * The stock to-background handler (0x4789f0, bound by the stock init to the dialog's EVT_WINDOW_TO_BG) moves the dialog back to
 * y 130 when another dialog (the Delete confirm) opens over it. Ours puts the sheet back on the bottom, so it has to run after the
 * stock one: the emitter runs the newest handler first, so it is bound on the list_view, which the window event reaches after the
 * dialog (widget_dispatch_recursive, the widget before its children).
 *
 * Hidden rows are visible=false and sensitive=false (a hidden widget would still take touches) and are stacked after the
 * shown ones (widget_restack): the stock list_view layouter re-stacks the visible children in child order at every relayout
 * (docs/modules/home-guard.md "The stock list code under the menu's hand-placed rows"), so the order survives it.
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "podcasts.h"

#define PM_ROWS 14 /* listitem0..6, then pod_more, pod_back, pod_tape, pod_vinyl, pod_goep, pod_art, pod_sleep */
#define PM_MORE 7
#define PM_BACK 8
#define PM_TAPE 9
#define PM_VINYL 10
#define PM_GOEP 11 /* Go to Podcasts: page 1 of a podcast episode */
#define PM_ART 12
#define PM_SLEEP 13 /* Sleep Timer: a link to the stock Power page, page 2 */
#define PM_ART_DIM \
    100 /* the Find Cover & Lyrics row's opacity (of 255) while the Wi-Fi is off: dimmed, and it takes no tap */
#define GO_ALBUM 4 /* listitem4, Look up album */
#define PM_DELETE 6 /* listitem6, Delete song */
#define GO_ARTIST 5 /* listitem5, Look up artist */
extern int coverflow_artist(void *artists, unsigned index,
                            unsigned scope); /* patch/coverflow.c: 0 once the page is up */
extern int albums_open_artist(void *artists, unsigned index,
                              unsigned scope); /* patch/albums.c: 0 once up, -1 when the window will not open */

/* what each page shows, top to bottom, as indices into pm.row[]; the sheet is as high as its page's rows (PM_PAGE_N, PM_PAGE2_N) */
static const unsigned char pm_page[3][PM_PAGE_N] = {
    {4, 5, 2, PM_TAPE, PM_VINYL,
     PM_MORE}, /* Look up album, Look up artist, Add to playlist, Cassette Mode, Vinyl Mode, More */
    {PM_BACK, 1, PM_SLEEP, 0, PM_ART,
     6}, /* the back header, Playback speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete */
    {PM_GOEP,
     PM_MORE}, /* page 1 of a podcast episode: Go to Podcasts, More (the rows that mean nothing for an episode are hidden) */
};
static const unsigned char pm_rows[3] = {PM_PAGE_N, PM_PAGE2_N, PM_PAGE_EP_N};
static const char *const pm_glass[3] = {
    "pm_sheet6", "pm_sheet6",
    "pc_sheet2"}; /* each set's own picture (pc_sheet2: the Podcasts page's 100 px glass, the same pane) */

static struct {
    void *dlg, *lv, *sv, *bar,
        *glass; /* the dialog, its list_view, scroll_view and scroll bar, and the glass image under them */
    void *row[PM_ROWS];
    int page; /* 0: the first page, 1: the More page */
    int ep; /* the playing track is a podcast episode: the first page is the episode's (set 2) */
} pm __attribute__((section(".scratch")));

static void pm_show(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The row set shown: 0 the first page, 1 the More page, 2 the first page of an episode. */
static int pm_set(void) { return pm.page ? 1 : pm.ep ? 2 : 0; }

/* The rows as pm.page says: the shown ones at y = position x PM_ROW_H, the others hidden and parked under the sheet; the
 * children stacked in that order; the sheet PM_PAGE_N rows high on the bottom of the screen. */
static void pm_arrange(void) {
    unsigned char used[PM_ROWS];
    int set = pm_set();
    unsigned i, k = 0, n = pm_rows[set];
    int h = (int)n * PM_ROW_H;
    memset(used, 0, sizeof used);
    widget_invalidate_force(pm.dlg, (void *)0);
    for (i = 0; i < PM_ROWS; i++) {
        widget_resize(
            pm.row[i], PM_SV_W,
            PM_ROW_H); /* the asset has Go to artist and Delete 60 px high: the layouter keeps a row's own height */
        widget_set_state(pm.row[i], "normal"); /* the row that was tapped is hidden by its own click */
    }
    for (i = 0; i < n; i++) {
        void *r = pm.row[pm_page[set][i]];
        used[pm_page[set][i]] = 1;
        widget_move(r, 0, (int)i * PM_ROW_H);
        pm_show(r, 1);
    }
    for (i = 0; i < PM_ROWS;
         i++) { /* parked under the shown rows: nothing it could shadow if a hit test did look at it */
        if (used[i]) continue;
        widget_move(pm.row[i], 0, h);
        pm_show(pm.row[i], 0);
    }
    for (i = 0; i < n; i++) widget_restack(pm.row[pm_page[set][i]], k++);
    if (pm.page ==
        1) { /* Find Cover & Lyrics needs the Wi-Fi: looked at each time page 2 shows (stock's get_wifisignal, as the Podcasts guard) */
        int online = get_wifisignal() > 0;
        widget_set_opacity(pm.row[PM_ART], online ? 255 : PM_ART_DIM);
        widget_set_sensitive(pm.row[PM_ART], online);
    } else
        widget_set_opacity(pm.row[PM_ART], 255);
    for (i = 0; i < PM_ROWS; i++)
        if (!used[i]) widget_restack(pm.row[i], k++);
    widget_resize(
        pm.glass, PM_DIALOG_W,
        h); /* the glass of the page's own height: pm_sheet6 (pages 1 and 2, 300 px) or pc_sheet2 (an episode's page 1), never a crop */
    image_base_set_image(pm.glass, pm_glass[set]);
    widget_resize(pm.dlg, PM_DIALOG_W, h);
    widget_move(pm.dlg, 0, PM_SCREEN_H - h);
    widget_resize(pm.lv, PM_DIALOG_W, h);
    widget_resize(pm.sv, PM_SV_W, h);
    widget_resize(pm.bar, PM_BAR_W, h);
    widget_set_prop_int(pm.sv, "virtual_h", h);
    widget_set_prop_int(pm.sv, "yoffset", 0);
    widget_invalidate_force(pm.dlg, (void *)0);
}

static int pm_on_more(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    pm.page = 1;
    pm_arrange();
    return RET_OK;
}

static int pm_on_back(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    pm.page = 0;
    pm_arrange();
    return RET_OK;
}

/* Cassette Mode (the row is pod_tape): the landscape cassette page (patch/tape.c) over Now Playing. The page opens first and the sheet closes once it is up (a window below the top one, as Settings >
 * Shanling Home closes the menu under the Settings page): a page that cannot open leaves the sheet as it was. */
extern int tape_open(void);

static int pm_on_tape(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (tape_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Vinyl Mode (the row is pod_vinyl): the turntable page (patch/vinyl.c), opened the same way: the page first, the sheet closed once it is up. */
extern int vinyl_open(void);

static int pm_on_vinyl(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (vinyl_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Go to Podcasts (the row is pod_goep): the Podcasts page (patch/podcasts.c podcasts_go: uncovered when it is below, else opened), the same order: the page first, the sheet closed once it is up. */
extern int podcasts_go(void);

static int pm_on_goep(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (podcasts_go() == 0) window_close(ctx);
    return RET_OK;
}

/* Find Cover & Lyrics (the row is pod_art, page 2): our page (patch/onlineart.c) over Now Playing, opened the same way: the page first, the sheet closed once it is up. Not with the Wi-Fi off (the row is dimmed
 * and insensitive then; this is the second look). */
extern int onlineart_open(void);

static int pm_on_art(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg || get_wifisignal() <= 0) return RET_OK;
    if (onlineart_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Sleep Timer (the row is pod_sleep, page 2): the stock Settings > Power page (powermanager_page: the Sleep Timer switch and its hour / minute selectors), opened over Now Playing. The page has no single_instance property,
 * so a plain navigator_to stacks a new one every time. The pile-up needs the page's top-right Now Playing button, which restacks the player and leaves the Power page under it, and then reopening Sleep Timer; a plain
 * Back closes the page. A Power window already in the stack is brought to the front (pod_open_stock, which restacks as the Settings tiles do); otherwise stock's open. The restacked page refreshes itself: stock's restack delivers
 * EVT_WINDOW_TO_FG, and the handler the page's init bound for it (0x4a9b2c) runs the page refresh (0x4a9924: switch and selectors from the timer), so nothing here refreshes it (pinned in tools/pod.py PLAYMORE_PINS).
 * Back (0x4a91d0) saves the picker values and calls navigator_back; with Now Playing directly below the page that returns to Now Playing. The page FIRST, the sheet closed once it is up (a window below the top one);
 * a page that cannot open leaves the sheet. */
static int pm_on_sleep(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (pod_open_stock("systemset/powermanager_page", "powermanager_page") != RET_OK) return RET_OK;
    window_close(ctx);
    return RET_OK;
}

/* Another dialog opened over the sheet: the stock handler (on the dialog, so it ran before this one on the list_view) has just
 * moved it to y 130. */
static int pm_on_bg(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    widget_move(ctx, 0, PM_SCREEN_H - (int)pm_rows[pm_set()] * PM_ROW_H);
    return RET_OK;
}

static int pm_on_destroy(void *ctx, void *e) {
    (void)e;
    if (pm.dlg && ctx == pm.dlg) memset(&pm, 0, sizeof pm); /* an earlier dialog's end: the new one keeps its state */
    return RET_OK;
}

/* Look up album (listitem4): our album page instead of the stock playerjumpinfo_page. Bound after the stock init, so it runs
 * before the stock handler (0x4795cc; top comment); RET_STOP keeps the stock one from running, RET_OK lets it run. The order is
 * the stock Look up artist's (0x4793ac): the sheet closes, an albuminfo_page already in the stack is closed, songerinfoflag is
 * set (the page's track tap and Play then unwind to the Now Playing that is in the stack instead of stacking a second one),
 * the page opens. The library lookup comes first: no playing track, no album tag or no such album in the list leaves everything
 * as it was and the stock handler runs (its own message or page). Stock clears the flag only on album_page's window event, so
 * the new page's destroy does: pm_flag_owner is the window we set it for, so the end of an older page never clears the flag of
 * a newer one, and pm_flag_prev is the byte before (set by a Look up artist whose album_page is still below: it stays set). */
static void *pm_flag_owner __attribute__((section(".scratch")));
static unsigned char pm_flag_prev __attribute__((section(".scratch")));

static int pm_on_album_gone(void *ctx, void *e) {
    (void)e;
    if (ctx == pm_flag_owner) {
        pm_flag_owner = (void *)0;
        *(unsigned char *)SONGER_FLAG = pm_flag_prev;
    }
    return RET_OK;
}

/* An album page in the stack, ours (patch/albumpage.c) or the stock albuminfo_page it falls back to. */
static void pm_close_albums(void) {
    if (navigator_window_is_exist("albuminfo_page")) navigator_close("albuminfo_page");
    if (navigator_window_is_exist(AB_WINDOW)) navigator_close(AB_WINDOW);
}

static int pm_is_album(void *win) {
    const char *name = *(const char **)((char *)win + WIDGET_NAME);
    return !strcmp(name, "albuminfo_page") || !strcmp(name, AB_WINDOW);
}

static int pm_on_lookup_album(void *ctx, void *e) {
    void *track, *top;
    int row;
    unsigned char prev;
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    track = cc_playing();
    if (!track) return RET_OK;
    row = cc_find_album(cc_str(track, REC_ALBUM));
    if (row < 0) return RET_OK;
    window_close(ctx);
    pm_close_albums();
    prev = *(unsigned char *)SONGER_FLAG;
    *(unsigned char *)SONGER_FLAG = 1;
    if (cc_open_album((void *)0, 0, row) < 0) {
        *(unsigned char *)SONGER_FLAG = prev;
        return RET_STOP; /* the list changed between the two reads: the sheet is closed, nothing opened */
    }
    top = window_manager_get_top_window(window_manager());
    if (top && pm_is_album(top) && widget_on(top, EVT_DESTROY, pm_on_album_gone, top)) {
        if (!pm_flag_owner) pm_flag_prev = prev; /* an older owner still pending keeps the byte from before it */
        pm_flag_owner = top;
    } else
        *(unsigned char *)SONGER_FLAG = prev; /* cannot tell when it ends: do not leave the flag set */
    return RET_STOP;
}

/* Look up artist (listitem5): our Albums page scoped to the artist (albums_open_artist, what the Artists list opens; Cover Flow if that window will not open) instead of the stock album_page.
 * Same mechanism as Look up album: bound after the stock init, so it runs first; RET_STOP keeps the stock handler (0x4793ac) from running, RET_OK
 * lets it run. The artist is the playing track's REC_ARTIST, looked up in the Artists list the stock page would show (loadLocalClassList(0xf004):
 * getAllArtist, or the album-artist list when Settings' artist type says so; a row's name is REC_TITLE, compared ASCII case-insensitively as the list
 * groups; the Unknown Artist row, id -1, never matches). The page opens FIRST (as Cassette Mode does) and the sheet closes once it is up, so any
 * failure (nothing playing, no artist tag, not in the list, Cover Flow already open, the page will not open) leaves everything as it was for the
 * stock handler. Like the stock one it sets songerinfoflag (a track tap or Play on an album page above then unwinds to the Now Playing that is
 * in the stack) and closes an albuminfo_page in the stack; the flag is released by the destroy of that page (pm_on_album_gone). */
static int pm_on_lookup_artist(void *ctx, void *e) {
    void *track, *list, *one, *top, *below;
    const char *name;
    unsigned i, n;
    int found = -1, ret;
    unsigned char prev;
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    track = cc_playing();
    if (!track) return RET_OK;
    name = cc_str(track, REC_ARTIST);
    if (!*name) return RET_OK;
    if (loadLocalClassList(CLASS_ARTISTS) <= 0) return RET_OK;
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n && found < 0; i++) {
        void *r = deque_at(list, i);
        if (*(int *)((char *)r + REC_ID) != -1 && !cc_nocase(cc_str(r, REC_TITLE), name)) found = (int)i;
    }
    if (found < 0) return RET_OK;
    one = _create_deque(
        "stSongInfo"); /* the page takes its own copy of the row; this list only carries it there (and keeps the stock list's reload from pulling it away) */
    if (!one) return RET_OK;
    deque_init(one);
    _deque_push_back(one, deque_at(list, (unsigned)found));
    prev = *(unsigned char *)SONGER_FLAG;
    *(unsigned char *)SONGER_FLAG = 1;
    below = window_manager_get_top_window(window_manager());
    ret = albums_open_artist(one, 0, CLASS_ARTISTS);
    if (ret == -1) ret = coverflow_artist(one, 0, CLASS_ARTISTS);
    deque_destroy(one);
    if (ret != 0) {
        *(unsigned char *)SONGER_FLAG = prev;
        return RET_OK;
    }
    top = window_manager_get_top_window(window_manager());
    if (top && top != below && widget_on(top, EVT_DESTROY, pm_on_album_gone, top)) {
        if (!pm_flag_owner) pm_flag_prev = prev;
        pm_flag_owner = top;
    } else
        *(unsigned char *)SONGER_FLAG = prev;
    window_close(ctx);
    pm_close_albums();
    return RET_STOP;
}

/* Delete (listitem6): the sheet closes BEFORE the stock handler (0x4791f4) opens its confirm. That handler is modal (navigator_to_with_context
 * returns the answer, 0xa yes / 0x14 no; it never touches its ctx, the dialog), so it runs on unchanged after the sheet is gone: only on Yes does it
 * delete_playqueue_file(0) and show the result. The glass confirm card is translucent, so an open sheet behind it showed through. Stock's own Add to
 * playlist (0x4798f0) closes the sheet the same way (window_close, then goes on with the same handler), so continuing after window_close is the stock
 * pattern. Speed, A-B and Look up open no dialog; Look up album / artist and Cassette Mode close the sheet themselves. A No leaves Now Playing, no sheet. */
static int pm_on_delete(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    window_close(ctx);
    return RET_OK;
}

static void pm_start(void *dlg) {
    static const char *const names[PM_ROWS] = {"listitem0", "listitem1", "listitem2", "listitem3", "listitem4",
                                               "listitem5", "listitem6", "pod_more",  "pod_back",  "pod_tape",
                                               "pod_vinyl", "pod_goep",  "pod_art",   "pod_sleep"};
    void *more_label, *back_label, *speed_label, *note_label, *tape_label, *vinyl_label, *goep_label, *art_label,
        *sleep_label, *track;
    unsigned i;
    if (pm.dlg) memset(&pm, 0, sizeof pm); /* an earlier dialog that never said it was gone */
    pm.dlg = dlg;
    pm.lv = widget_lookup(dlg, "playmore_listview", 1);
    pm.sv = widget_lookup(dlg, "playmore_scrollview", 1);
    pm.bar = widget_lookup(dlg, "scroll_bar_m", 1);
    pm.glass = widget_lookup(dlg, "pod_glass", 1);
    more_label = widget_lookup(dlg, "pod_more_label", 1);
    back_label = widget_lookup(dlg, "pod_back_label", 1);
    speed_label = widget_lookup(dlg, "scrlabel1", 1);
    note_label = widget_lookup(dlg, "label1_msg", 1);
    tape_label = widget_lookup(dlg, "pod_tape_label", 1);
    vinyl_label = widget_lookup(dlg, "pod_vinyl_label", 1);
    goep_label = widget_lookup(dlg, "pod_goep_label", 1);
    art_label = widget_lookup(dlg, "pod_art_label", 1);
    sleep_label = widget_lookup(dlg, "pod_sleep_label", 1);
    if (!pm.lv || !pm.sv || !pm.bar || !pm.glass || !more_label || !back_label || !speed_label || !note_label ||
        !tape_label || !vinyl_label || !goep_label || !art_label || !sleep_label)
        goto fail;
    for (i = 0; i < PM_ROWS; i++) { /* exactly the asset: fourteen rows in the scroll_view */
        pm.row[i] = widget_lookup(dlg, names[i], 1);
        if (!pm.row[i] || *(void **)((char *)pm.row[i] + W_PARENT) != pm.sv) goto fail;
    }
    if (widget_count_children(pm.sv) != PM_ROWS) goto fail;
    if (widget_set_tr_text(more_label, "More") != RET_OK) goto fail;
    if (widget_set_tr_text(back_label, "More") != RET_OK) goto fail;
    if (widget_set_tr_text(speed_label, "Speed") != RET_OK)
        goto fail; /* the stock "Multiple Speed" is wider than the room before the badges */
    if (widget_set_tr_text(note_label, "Files below 48 kHz only") != RET_OK) goto fail;
    if (widget_set_tr_text(tape_label, "Cassette Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(vinyl_label, "Vinyl Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(goep_label, "Go to Podcasts") != RET_OK) goto fail;
    if (widget_set_tr_text(art_label, "Cover & Lyrics") != RET_OK) goto fail;
    if (widget_set_tr_text(sleep_label, "powerm_sleep") != RET_OK)
        goto fail; /* the stock key: the Power page's own row text */
    if (!widget_on(dlg, EVT_DESTROY, pm_on_destroy, dlg)) goto fail;
    if (!widget_on(pm.lv, EVT_WINDOW_TO_BG, pm_on_bg, dlg))
        goto fail; /* after the stock one on the dialog (top comment) */
    if (!widget_on(pm.row[PM_MORE], EVT_CLICK, pm_on_more, dlg)) goto fail;
    if (!widget_on(pm.row[PM_BACK], EVT_CLICK, pm_on_back, dlg)) goto fail;
    if (!widget_on(pm.row[PM_TAPE], EVT_CLICK, pm_on_tape, dlg)) goto fail;
    if (!widget_on(pm.row[PM_VINYL], EVT_CLICK, pm_on_vinyl, dlg)) goto fail;
    if (!widget_on(pm.row[PM_GOEP], EVT_CLICK, pm_on_goep, dlg)) goto fail;
    if (!widget_on(pm.row[PM_ART], EVT_CLICK, pm_on_art, dlg)) goto fail;
    if (!widget_on(pm.row[PM_SLEEP], EVT_CLICK, pm_on_sleep, dlg)) goto fail;
    if (!widget_on(pm.row[GO_ALBUM], EVT_CLICK, pm_on_lookup_album, dlg)) goto fail;
    if (!widget_on(pm.row[GO_ARTIST], EVT_CLICK, pm_on_lookup_artist, dlg)) goto fail;
    if (!widget_on(pm.row[PM_DELETE], EVT_CLICK, pm_on_delete, dlg)) goto fail;
    pm.page = 0;
    track = cc_playing();
    pm.ep = track && pc_is_path(cc_str(track, REC_PATH));
    pm_arrange();
    return;
fail:
    memset(
        &pm, 0,
        sizeof pm); /* the stock rows are as the stock init left them; a handler that was bound finds no dialog of ours */
}

/* The hook (tools/pod.py PLAYMORE_INIT): stock first, then ours. */
int m1plus_playmore_init(void *dlg, void *ctx) {
    int ret = stock_playmore_init_trampoline(dlg, ctx);
    if (ret == RET_OK && dlg) pm_start(dlg);
    return ret;
}
