/* M1+ Music Now Playing More menu: the stock playmore_dialog (the sheet Now Playing's More button opens: ui/dialog/
 * playmore_dialog.bin, seven list_item rows listitem0..6) as an iOS style bottom sheet with two pages.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The sheet is as high as its page's rows (page 1: PM_PAGE_N = 5 x 50 = 250 px, page 2: PM_PAGE2_N = 6 x 50 = 300 px, the Display Mode page: PM_PAGE_MODE_N = 5 x 50 = 250 px) and sits on the bottom of the screen; the page
 * above it is dimmed by the asset's own dialog highlight (highlight="default(alpha=..)", the AWTK dialog highlighter the window
 * manager sets up when the dialog opens). The glass is the dialog's first child, an insensitive image (pod_glass) that gets the page's own picture and height
 * (pc_sheet3 to pc_sheet6): never a crop of a taller one. Page 1 (when it opens): Look up album (listitem4), Look up artist (5), Add to playlist
 * (2), Display Mode (pod_mode: a chevron at its right) and "More" (pod_more, a row the asset adds, hidden until now; a chevron
 * at its right). A tap on Display Mode switches to the Display Mode page: the header row "< Display Mode" (pod_back; a tap returns to page 1), Cassette Mode (pod_tape: it opens the landscape cassette page, patch/tape.c), Vinyl Mode
 * (pod_vinyl: the turntable page, patch/vinyl.c), VU Meter Mode (pod_vu: the needle meters, patch/vupage.c) and Lyrics Mode (pod_lyr: the full-screen lyrics page, patch/idlelyrics.c; dimmed for a track without lyrics).
 * A tap on More switches to page 2: the same header row reading "< More" (a tap returns to page 1), Playback speed (1), Sleep Timer (pod_sleep: a link to the stock Power page), A-B repeat (0), Find Cover & Lyrics (pod_art) and
 * Delete (6, its label red in the asset). For a podcast episode or an audiobook part, Speed and Sleep Timer move to page 1 and page 2 is the
 * back header, A-B repeat and Delete (no Find Cover & Lyrics). Online search (3) is never shown. A switch only hides one row set and shows the other and sets the sheet to the page's height;
 * there is no slide. A tap above the sheet closes it: that is the stock handler's (pointer y < dialog y), which works unchanged with the new y.
 *
 * One hook, dialog_playmore_dialog_init (0x479cc4): run when the dialog is built (a tap on Now Playing's More button, never
 * at boot or in the main loop). m1plus_playmore_init runs the stock init to completion (it binds every row's handler and the
 * speed / A-B widgets, which keep their stock handlers: we move rows, we do not replace behaviour; it also pins the sheet at
 * y 130) and then, if every widget of the asset is there, arranges page 1
 * and anchors the sheet. Everything fallible (the widget lookups, the handlers, the labels' texts) is done before the first
 * row moves, so any failure leaves the stock seven rows (the asset's added rows stay hidden and insensitive).
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
#include "sbapi.h"
#include "libsrc.h"
#include "sbsrc.h"
#include "albums.h"
#include "coverflow.h"
#include "entries.h"
#include "artsplit.h"
#include "artists.h"
#include "lyrics.h"
#include "picker.h"

#define PM_ROWS \
    17 /* listitem0..6, then pod_more, pod_back, pod_tape, pod_vinyl, pod_goep, pod_art, pod_sleep, pod_mode, pod_lyr, pod_vu */
#define PM_MORE 7
#define PM_BACK 8
#define PM_TAPE 9
#define PM_VINYL 10
#define PM_GOEP 11 /* Go to Podcasts: page 1 of a podcast episode */
#define PM_ART 12
#define PM_SLEEP 13 /* Sleep Timer: our Sleep Timer page, page 2 (an episode's or part's page 1) */
#define PM_MODE 14 /* Display Mode: opens the Display Mode page, page 1 */
#define PM_LYR 15 /* Lyrics Mode: the full-screen lyrics page, the Display Mode page */
#define PM_VU 16 /* VU Meter Mode: the VU Meter page, the Display Mode page (between Vinyl Mode and Lyrics Mode) */
#define PM_ART_DIM \
    100 /* the Find Cover & Lyrics row's opacity (of 255) while the Wi-Fi is off: dimmed, and it takes no tap */
#define GO_ALBUM 4 /* listitem4, Look up album */
#define PM_DELETE 6 /* listitem6, Delete song */
#define PM_ADDPL 2 /* listitem2, Add to playlist */
#define PM_DEL_FILE \
    0x14 /* the Delete confirm's second answer (stock 0x4792a8: delete_playqueue_file(1), the file too; 0xa, CONFIRM_YES, is delete_playqueue_file(0)) */
#define GO_ARTIST 5 /* listitem5, Look up artist */
#define PM_ALBUMS_WINDOW "m1plus_albums_page" /* our Albums page's window (tools/pod_pages.py ALBUMS) */

/* what each page shows, top to bottom, as indices into pm.row[]; the sheet is as high as its page's rows (PM_PAGE_N, PM_PAGE2_N) */
static const unsigned char pm_page[5][PM_PAGE_MAX] = {
    {4, 5, 2, PM_MODE, PM_MORE}, /* Look up album, Look up artist, Add to playlist, Display Mode, More */
    {PM_BACK, 1, PM_SLEEP, 0, PM_ART,
     6}, /* the back header, Playback speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete */
    {PM_GOEP, 1, PM_SLEEP,
     0}, /* page 1 of a podcast episode: Go to Podcasts, Playback speed, Sleep Timer, A-B repeat (the rows that mean nothing for an episode are hidden; no More page, so no Delete) */
    {PM_BACK, PM_TAPE, PM_VINYL, PM_VU,
     PM_LYR}, /* the Display Mode page: the back header, Cassette Mode, Vinyl Mode, VU Meter Mode, Lyrics Mode */
    {PM_MODE, 1, PM_SLEEP,
     0}, /* page 1 of an audiobook part: Display Mode, Playback speed, Sleep Timer, A-B repeat (a part has no album or artist to look up, nor a playlist to join; no More page, so no Delete) */
};
static const unsigned char pm_rows[5] = {PM_PAGE_N, PM_PAGE2_N, PM_PAGE_EP_N, PM_PAGE_MODE_N, PM_PAGE_BOOK_N};
static const char *const pm_glass[5] = {
    "pc_sheet5", "pc_sheet6", "pc_sheet4", "pc_sheet5",
    "pc_sheet4"}; /* each set's own picture, as high as its rows (the bottom sheets' one family of panes, tools/mod_icons.py PC_SHEETS) */

static struct {
    void *dlg, *lv, *sv, *bar,
        *glass; /* the dialog, its list_view, scroll_view and scroll bar, and the glass image under them */
    void *row[PM_ROWS];
    void *back_label; /* the back header's label: "More" on page 2, "Display Mode" on the Display Mode page */
    int page; /* 0: the first page, 1: the More page, 2: the Display Mode page */
    int ep; /* the playing track is a podcast episode: the first page is the episode's (set 2) */
    int book; /* the playing track is an audiobook part: the first page is the part's (set 4) */
    int srv; /* the playing track is a server track (streamed or downloaded): Find Cover & Lyrics is not for it (its cover and lyrics have no local album or file to be saved under) */
} pm __attribute__((section(".scratch")));

/* The row set shown: 0 the first page, 1 the More page, 2 the first page of an episode, 3 the Display Mode page, 4 the first page
 * of an audiobook part. An episode or part has no More page: whatever pm.page says, it is on its first page (or the Display Mode page). */
static int pm_set(void) {
    if (pm.page == 2) return 3;
    if (pm.ep) return 2;
    if (pm.book) return 4;
    return pm.page ? 1 : 0;
}

/* The playing track's kind, read each time the rows are laid out and at Delete's tap: the sheet can stay open while the queue moves on. */
static void pm_kind_now(void) {
    void *track = cc_playing();
    pm.ep = track && pc_is_path(cc_str(track, REC_PATH));
    pm.book = track && bk_is_path(cc_str(track, REC_PATH));
}

/* The rows as pm.page says: the shown ones at y = position x PM_ROW_H, the others hidden and parked under the sheet; the
 * children stacked in that order; the sheet PM_PAGE_N rows high on the bottom of the screen. */
static void pm_arrange(void) {
    unsigned char used[PM_ROWS];
    int set, stream = sbs_playing_stream(); /* (the track now: the sheet can stay open across a track change) */
    unsigned i, k = 0, n;
    int h;
    pm_kind_now(); /* so is its kind: an episode or a part that the queue reached under the open sheet gets its own page, without More and Delete */
    if ((pm.ep || pm.book) && pm.page == 1) pm.page = 0;
    set = pm_set();
    n = pm_rows[set];
    h = (int)n * PM_ROW_H;
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
        m1_show(r, 1);
    }
    for (i = 0; i < PM_ROWS;
         i++) { /* parked under the shown rows: nothing it could shadow if a hit test did look at it */
        if (used[i]) continue;
        widget_move(pm.row[i], 0, h);
        m1_show(pm.row[i], 0);
    }
    for (i = 0; i < n; i++) widget_restack(pm.row[pm_page[set][i]], k++);
    if (set ==
        1) { /* Find Cover & Lyrics needs the Wi-Fi: looked at each time page 2 shows (stock's get_wifisignal, as the Podcasts guard) */
        int online = get_wifisignal() > 0 && !pm.srv;
        widget_set_opacity(pm.row[PM_ART], online ? 255 : PM_ART_DIM);
        widget_set_sensitive(pm.row[PM_ART], online);
    } else
        widget_set_opacity(pm.row[PM_ART], 255);
    if (pm.page ==
        2) { /* Lyrics Mode needs lyric rows on Now Playing (ly_has_rows, the idle timer's test): looked at each time the page shows */
        int rows = ly_has_rows();
        widget_set_opacity(pm.row[PM_LYR], rows ? 255 : PM_ART_DIM);
        widget_set_sensitive(pm.row[PM_LYR], rows);
    } else
        widget_set_opacity(pm.row[PM_LYR], 255);
    if (pm.page) /* the one back header serves both pages: it names the page it heads */
        widget_set_tr_text(pm.back_label, pm.page == 2 ? "Display Mode" : "More");
    /* a Subsonic stream (sbs_playing_stream: no file on the card) takes neither Add to playlist nor Delete: stock's Add to playlist would copy the record, whose path is the stream address with the login
     * token, into a card playlist; stock's Delete would drop it from the queue and report a deleted song. Dimmed and insensitive; a downloaded track is a file and keeps both. The track is the one playing
     * when the rows are laid out, and the handlers ask again at the tap (pm_stream_now): the sheet can stay open while the queue moves on to a stream. */
    widget_set_opacity(pm.row[PM_ADDPL], stream ? PM_ART_DIM : 255);
    widget_set_opacity(pm.row[PM_DELETE], stream ? PM_ART_DIM : 255);
    if (stream) {
        widget_set_sensitive(pm.row[PM_ADDPL], 0);
        widget_set_sensitive(pm.row[PM_DELETE], 0);
    }
    for (i = 0; i < PM_ROWS; i++)
        if (!used[i]) widget_restack(pm.row[i], k++);
    widget_resize(pm.glass, PM_DIALOG_W, h); /* the glass of the page's own height: pm_glass[set], never a crop */
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

/* Display Mode (the row is pod_mode, page 1): the page of the four Now Playing looks (Cassette Mode, Vinyl Mode, VU Meter Mode, Lyrics Mode); its back header returns to page 1 (pm_on_back). */
static int pm_on_mode(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    pm.page = 2;
    pm_arrange();
    return RET_OK;
}

/* Cassette Mode (the row is pod_tape): the landscape cassette page (patch/tape.c) over Now Playing. The page opens first and the sheet closes once it is up (a window below the top one, as Settings >
 * Shanling Home closes the menu under the Settings page): a page that cannot open leaves the sheet as it was. */

static int pm_on_tape(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (tape_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Vinyl Mode (the row is pod_vinyl): the turntable page (patch/vinyl.c), opened the same way: the page first, the sheet closed once it is up. */

static int pm_on_vinyl(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (vinyl_open() == 0) window_close(ctx);
    return RET_OK;
}

/* VU Meter Mode (the row is pod_vu): the needle meters page (patch/vupage.c), opened the same way: the page first, the sheet closed once it is up. */

static int pm_on_vu(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (vupage_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Lyrics Mode (the row is pod_lyr): the full-screen lyrics page (patch/idlelyrics.c, the page the Idle Display timer opens), opened the same way: the page first, the sheet closed once it is up. Not for a
 * track without lyric rows (the row is dimmed and insensitive then; this is the second look, and the rows are laid out again so that a track that changed under the open sheet shows it): the Album
 * Cover fallback is the idle timer's, not this row's. Closing the sheet under the page sends stock's EVT_WINDOW_TO_FG to the window then on top, the lyrics page (stock's close, 0x6929c8..0x692a44:
 * window_manager_get_top_window after the removal), not to Now Playing, whose handler would take the lyrics engine back (ly_refresh). */

static int pm_on_lyr(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (!ly_has_rows()) {
        pm_arrange();
        return RET_OK;
    }
    if (idlelyrics_open_idle() == 0) window_close(ctx);
    return RET_OK;
}

/* Go to Podcasts (the row is pod_goep): the Podcasts page (patch/podcasts.c podcasts_go: uncovered when it is below, else opened), the same order: the page first, the sheet closed once it is up. */

static int pm_on_goep(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (podcasts_go() == 0) window_close(ctx);
    return RET_OK;
}

/* Find Cover & Lyrics (the row is pod_art, page 2): our page (patch/onlineart.c) over Now Playing, opened the same way: the page first, the sheet closed once it is up. Not with the Wi-Fi off (the row is dimmed
 * and insensitive then; this is the second look), nor for an episode or audiobook part (the row is not shown). */

static int pm_on_art(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg || get_wifisignal() <= 0 || pm.srv || pm.ep || pm.book) return RET_OK;
    if (onlineart_open() == 0) window_close(ctx);
    return RET_OK;
}

/* Sleep Timer (the row is pod_sleep, page 2; page 1 for an episode or part): our Sleep Timer page (m1plus_sleeptimer, patch/sleeptimer.c) over Now Playing. A page of ours keeps one window: an opened one in the stack is brought to the front (m1_restack_window; stock's
 * restack delivers EVT_WINDOW_TO_FG, which refreshes our page's checks), else it is opened afresh. The page FIRST, the sheet closed once it is up (a window below the top one); a page that cannot open leaves the sheet.
 * Its top-right Now Playing button restacks the player over it, which a later tap here reuses; a plain Back closes it and returns to Now Playing. */
static int pm_on_sleep(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (!m1_restack_window("m1plus_sleeptimer_page") && pod_open_sleeptimer() != 0) return RET_OK;
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

/* songerinfoflag for a page about to open: 1 (a track tap or Play on it unwinds to the Now Playing in the stack), but from the Control Center (pm_goto) with no Now Playing in the stack it stays as it was. */
static unsigned char pm_no_np __attribute__((section(".scratch")));
static unsigned char pm_flag_set(unsigned char prev) { return pm_no_np ? prev : 1; }

/* The page just opened above `below` holds songerinfoflag until it ends (pm_on_album_gone); a page that cannot be watched does not keep the flag. */
static void pm_flag_hold(void *below, unsigned char prev) {
    void *top = window_manager_get_top_window(window_manager());
    if (top && top != below && widget_on(top, EVT_DESTROY, pm_on_album_gone, top)) {
        if (!pm_flag_owner) pm_flag_prev = prev; /* an older owner still pending keeps the byte from before it */
        pm_flag_owner = top;
    } else
        *(unsigned char *)SONGER_FLAG = prev;
}

/* Look up album / Look up artist while the player is on a Subsonic track (sbs_playing_ours): the source's own album page / the source's Albums page of the artist, never the card's library (which
 * does not have the album, or has another of the same name). The stock handler never runs (RET_STOP). An album or artist the cache does not know is the toast "Not found" with the sheet left open.
 * The rest is the library path's: the sheet and an album page in the stack close, songerinfoflag is set until the new page ends. An Albums page of ours in the stack (the one the play came from) is
 * closed for the artist's: the page is one window.
 * A page of ours that was closed is still there when navigator_close returns: stock's close (0x692960) takes the window out of the manager and destroys it from an idle (idle_add 0x68f6b8), and only
 * the destroy clears the page's state, so the opener answers -1 until then. The open is therefore tried at once and, when it answers -1 after a close, again from a timer (PM_PEND_MS, at most
 * PM_PEND_TRIES times) while Now Playing is still the window on top; the record waits in pm_pend. A second lookup, or another window on top, drops a pending one. */
#define PM_PEND_MS 30
#define PM_PEND_TRIES 40
#define PM_PEND_NAME 256
static struct {
    void *d, *below; /* the list of one record to open; the window that was on top (Now Playing) */
    int artist, tries;
    unsigned timer;
    int local; /* the library's Look up album waits for our album page to go (pm_local_tick): the album's name */
    char name[PM_PEND_NAME];
} pm_pend __attribute__((section(".scratch")));

static void pm_pend_drop(void) {
    m1_timer_stop(&pm_pend.timer);
    if (pm_pend.d) deque_destroy(pm_pend.d);
    memset(&pm_pend, 0, sizeof pm_pend);
}

/* The source's page on d's record, with songerinfoflag held by it; the opener's result (0 up, -1 the window would not open). */
static int pm_src_open(void *d, int artist, void *below) {
    unsigned char prev = *(unsigned char *)SONGER_FLAG;
    int r;
    *(unsigned char *)SONGER_FLAG = pm_flag_set(prev);
    r = artist ? albums_open_src(&lib_nd, deque_at(d, 0)) : album_open_src(&lib_nd, 0, deque_at(d, 0));
    if (r != 0)
        *(unsigned char *)SONGER_FLAG = prev;
    else
        pm_flag_hold(below, prev);
    return r;
}

static int pm_pend_tick(const void *unused) {
    (void)unused;
    pm_pend.timer = 0;
    if (!pm_pend.d) return RET_OK;
    if (window_manager_get_top_window(window_manager()) == pm_pend.below &&
        pm_src_open(pm_pend.d, pm_pend.artist, pm_pend.below) == -1 && ++pm_pend.tries < PM_PEND_TRIES) {
        pm_pend.timer = timer_add(pm_pend_tick, (void *)0, PM_PEND_MS); /* the closed page is not destroyed yet */
        if (pm_pend.timer) return RET_OK;
    }
    pm_pend_drop(); /* opened, given up, or the user is somewhere else */
    return RET_OK;
}

static int pm_lookup_src(void *dlg, int artist) {
    void *d = artist ? sbs_playing_artist() : sbs_playing_album(), *below;
    int closed;
    if (!d) {
        pod_toast(TR("Not found"));
        return RET_STOP;
    }
    pm_pend_drop();
    closed = navigator_window_is_exist(AB_WINDOW) || (artist && navigator_window_is_exist(PM_ALBUMS_WINDOW));
    if (dlg) window_close(dlg);
    pm_close_albums();
    if (artist && navigator_window_is_exist(PM_ALBUMS_WINDOW)) navigator_close(PM_ALBUMS_WINDOW);
    below = window_manager_get_top_window(window_manager());
    if (pm_src_open(d, artist, below) == -1 &&
        closed) { /* the page just closed still holds its window: once it is destroyed */
        pm_pend.d = d, pm_pend.below = below, pm_pend.artist = artist;
        pm_pend.timer = timer_add(pm_pend_tick, (void *)0, PM_PEND_MS);
        if (pm_pend.timer) return RET_STOP;
        pm_pend.d = (void *)0;
    }
    deque_destroy(d);
    return RET_STOP;
}

/* The library album's page on the Albums row `row` (ours, or stock's when ours will not open: cc_open_album), with songerinfoflag held by it. */
static void pm_local_open(int row) {
    void *top;
    unsigned char prev = *(unsigned char *)SONGER_FLAG;
    *(unsigned char *)SONGER_FLAG = pm_flag_set(prev);
    if (cc_open_album((void *)0, 0, row) < 0) {
        *(unsigned char *)SONGER_FLAG = prev;
        return; /* the list changed between the two reads: the sheet is closed, nothing opened */
    }
    top = window_manager_get_top_window(window_manager());
    if (top && pm_is_album(top) && widget_on(top, EVT_DESTROY, pm_on_album_gone, top)) {
        if (!pm_flag_owner) pm_flag_prev = prev; /* an older owner still pending keeps the byte from before it */
        pm_flag_owner = top;
    } else
        *(unsigned char *)SONGER_FLAG = prev; /* cannot tell when it ends: do not leave the flag set */
}

/* Our album page was in the stack and has been closed: its window is destroyed from stock's idle (pm_lookup_src's note), and until then album_open answers -1 and cc_open_album would open stock's
 * albuminfo_page instead. The open waits for the destroy (album_page_up), at most PM_PEND_TRIES ticks; after them it is made anyway (stock's page, as before). Another window on top drops it. */
static int pm_local_tick(const void *unused) {
    int row;
    (void)unused;
    pm_pend.timer = 0;
    if (!pm_pend.local) return RET_OK;
    if (window_manager_get_top_window(window_manager()) == pm_pend.below) {
        if (album_page_up() && ++pm_pend.tries < PM_PEND_TRIES) {
            pm_pend.timer = timer_add(pm_local_tick, (void *)0, PM_PEND_MS);
            if (pm_pend.timer) return RET_OK;
        }
        row = cc_find_album(pm_pend.name); /* (the row again: the list may have moved meanwhile) */
        if (row >= 0) pm_local_open(row);
    }
    pm_pend_drop();
    return RET_OK;
}

static int pm_go_album(void *ctx) {
    void *track;
    const char *name;
    int row, wait;
    track = cc_playing();
    if (!track) return RET_OK;
    if (sbs_playing_ours()) return pm_lookup_src(ctx, 0);
    name = cc_str(track, REC_ALBUM);
    row = cc_find_album(name);
    if (row < 0) return RET_OK;
    pm_pend_drop();
    wait = album_page_up() && snprintf(pm_pend.name, sizeof pm_pend.name, "%s", name) < (int)sizeof pm_pend.name;
    if (ctx) window_close(ctx);
    pm_close_albums();
    if (wait) { /* our album page is in the stack: the new one opens once that window is destroyed */
        pm_pend.local = 1, pm_pend.below = window_manager_get_top_window(window_manager());
        pm_pend.timer = timer_add(pm_local_tick, (void *)0, PM_PEND_MS);
        if (pm_pend.timer) return RET_STOP;
        pm_pend.local = 0;
    }
    pm_local_open(row);
    return RET_STOP;
}

static int pm_on_lookup_album(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    pm_no_np = 0;
    return pm_go_album(ctx);
}

/* Look up artist (listitem5): our Albums page scoped to the artist (albums_open_artist, what the Artists list opens; Cover Flow if that window will not open) instead of the stock album_page.
 * Same mechanism as Look up album: bound after the stock init, so it runs first; RET_STOP keeps the stock handler (0x4793ac) from running, RET_OK
 * lets it run. The artist is the playing track's REC_ARTIST, looked up in the Artists list the stock page would show (loadLocalClassList(0xf004):
 * getAllArtist, or the album-artist list when Settings' artist type says so; a row's name is REC_TITLE, compared ASCII case-insensitively as the list
 * groups; the Unknown Artist row, id -1, never matches). The page opens FIRST (as Cassette Mode does) and the sheet closes once it is up, so any
 * failure (nothing playing, no artist tag, not in the list, Cover Flow already open, the page will not open) leaves everything as it was for the
 * stock handler. Like the stock one it sets songerinfoflag (a track tap or Play on an album page above then unwinds to the Now Playing that is
 * in the stack) and closes an albuminfo_page in the stack; the flag is released by the destroy of that page (pm_on_album_gone). */
static int pm_go_artist(void *ctx) {
    void *track, *one, *top, *below;
    const char *name;
    int ret;
    unsigned char prev;
    track = cc_playing();
    if (!track) return RET_OK;
    if (sbs_playing_ours()) return pm_lookup_src(ctx, 1);
    name = cc_str(track, REC_ARTIST);
    if (!*name) return RET_OK;
    one =
        artists_find(name); /* (the artist split on: the first name of the field, never the joined name's empty page) */
    if (!one) return RET_OK;
    prev = *(unsigned char *)SONGER_FLAG;
    *(unsigned char *)SONGER_FLAG = pm_flag_set(prev);
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
    if (ctx) window_close(ctx);
    pm_close_albums();
    return RET_STOP;
}

static int pm_on_lookup_artist(void *ctx, void *e) {
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    pm_no_np = 0;
    return pm_go_artist(ctx);
}

/* The Control Center's Go to Artist / Go to Album (patch/pulldown.c, after the dialog has quit): the same lookups as the sheet's rows, with no sheet to close. 1 when the page was opened (or the track is a
 * Subsonic one, whose miss has shown its own "Not found"), 0 when nothing was opened. */
int pm_goto(int artist) {
    pm_no_np = !navigator_window_is_exist("playing_page");
    return (artist ? pm_go_artist((void *)0) : pm_go_album((void *)0)) == RET_STOP;
}

/* The player is on a Subsonic stream at this moment (not when the sheet opened): Add to playlist and Delete are refused, and the rows are laid out again so that they show it (a sheet opened on a
 * downloaded song whose queue has moved on to a stream still had them live). */
static int pm_stream_now(void) {
    if (!sbs_playing_stream()) return 0;
    pm_arrange();
    return 1;
}

/* An episode or a book part is never deleted from here (its page has no Delete row). The queue can reach one while music's More page is open, with Delete still showing: the tap lays the sheet out
 * again, as the part's page, and does nothing else. */
static int pm_spoken_now(void) {
    void *rec = cc_playing();
    if (!rec || !pc_spoken_path(cc_str(rec, REC_PATH))) return 0;
    pm_arrange();
    return 1;
}

/* The track Delete was asked for: the queue record's id and path, compared again after the confirm. */
#define PM_DEL_PATH 768
static int pm_same_track(int id, const char *path) {
    void *rec = cc_playing();
    return rec && *(int *)((char *)rec + REC_ID) == id && !strcmp(cc_str(rec, REC_PATH), path);
}

/* Delete (listitem6) is stock's handler (0x4791f4) done here, and stock's never runs (RET_STOP). Stock's: with a track in the queue, the modal confirm (dialog/confirminfo_dialog, kind 3, the text
 * msg_delsong), then delete_playqueue_file(0) for the answer 0xa and delete_playqueue_file(1) for 0x14, the message msg_delsongsuccess and the refresh flag; any other answer does nothing; with no
 * track the message msg_delsongfailed. Two things differ. The sheet closes BEFORE the confirm opens (the glass confirm card is translucent, so an open sheet behind it showed through; stock's own Add
 * to playlist, 0x4798f0, closes the sheet the same way). And the track is looked at again AFTER the answer: the confirm is modal but the main loop runs under it, the queue moves on, and
 * delete_playqueue_file takes whatever plays when it is called. So the answer counts only while the player is still on the track the question was asked for (the same queue id and path) and that
 * track is not a Subsonic stream; otherwise nothing is deleted and the message is msg_delsongfailed. (Stock deleted the next song when the track changed under the question.) */
static int pm_on_delete(void *ctx, void *e) {
    struct {
        int kind, ms;
        char text[0x400];
    } info; /* stock's 0x408 bytes */
    char path[PM_DEL_PATH];
    const char *text;
    void *rec;
    unsigned i;
    int id, ans;
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (pm_stream_now() || pm_spoken_now()) return RET_STOP;
    rec = cc_playing();
    window_close(ctx);
    if (!rec) {
        pod_toast(TR("msg_delsongfailed"));
        return RET_STOP;
    }
    id = *(int *)((char *)rec + REC_ID);
    text = cc_str(rec, REC_PATH);
    for (i = 0; text[i] && i < sizeof path - 1; ++i) path[i] = text[i];
    path[i] = 0;
    if (text[i]) { /* a path that does not fit cannot be told apart later */
        pod_toast(TR("msg_delsongfailed"));
        return RET_STOP;
    }
    memset(&info, 0, sizeof info);
    info.kind = 3;
    text = TR("msg_delsong");
    for (i = 0; text[i] && i < 0x200 - 1; ++i) info.text[i] = text[i];
    ans =
        navigator_to_with_context("dialog/confirminfo_dialog", &info); /* (pm is gone from here on: the sheet closed) */
    if (ans != CONFIRM_YES && ans != PM_DEL_FILE) return RET_STOP;
    if (!pm_same_track(id, path) || sbs_playing_stream()) {
        pod_toast(TR("msg_delsongfailed"));
        return RET_STOP;
    }
    delete_playqueue_file(ans == PM_DEL_FILE);
    pod_toast(TR("msg_delsongsuccess"));
    *(unsigned char *)FORCE_REFRESH = 1;
    return RET_STOP;
}

/* Add to playlist (listitem2) is stock's handler (0x4798f0) done here with our picker (patch/picker.c: the page the track rows' Add to Playlist opens) in place of stock's playlist_page. Stock's:
 * player_addplayList() (-5 with no track or a stopped player: a message, the sheet stays; else it fills the tags a folder-played row lacks and puts the playing row in the selection vector), the
 * sheet closed, then playlist_page with PICKER_PLAYING, whose row handler adds the queue's selected row. Ours opens the picker on a copy of the playing row (the queue can move on under it; the
 * add is the track that played at the tap), and stock's never runs (RET_STOP). Stock's runs untouched for its own -5 and for its own stream lists (Tidal, DLNA: the play types the Queue page leaves
 * to stock), and its page is opened as it opens it where our picker cannot open. For a Subsonic stream neither runs (the row is dimmed and insensitive; this is the second look). */
static int pm_on_addpl(void *ctx, void *e) {
    void *rec;
    int type;
    (void)e;
    if (!pm.dlg || ctx != pm.dlg) return RET_OK;
    if (pm_stream_now()) return RET_STOP;
    type = mclGetPlayType();
    if (type == QP_STREAM_A || type == QP_STREAM_B || type == QP_STREAM_C || type == QP_STREAM_D) return RET_OK;
    if (player_addplayList() < 0 || !(rec = cc_playing())) return RET_OK;
    window_close(ctx); /* (pm is gone from here on: the sheet closed) */
    if (picker_open_rec(CLASS_ALL_SONGS, rec) < 0)
        navigator_to_with_context("playlist_page", (const void *)(long)PICKER_PLAYING);
    return RET_STOP;
}

static void pm_start(void *dlg) {
    static const char *const names[PM_ROWS] = {"listitem0", "listitem1", "listitem2", "listitem3", "listitem4",
                                               "listitem5", "listitem6", "pod_more",  "pod_back",  "pod_tape",
                                               "pod_vinyl", "pod_goep",  "pod_art",   "pod_sleep", "pod_mode",
                                               "pod_lyr",   "pod_vu"};
    void *more_label, *back_label, *speed_label, *note_label, *tape_label, *vinyl_label, *goep_label, *art_label,
        *sleep_label, *mode_label, *lyr_label, *vu_label, *track;
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
    mode_label = widget_lookup(dlg, "pod_mode_label", 1);
    lyr_label = widget_lookup(dlg, "pod_lyr_label", 1);
    vu_label = widget_lookup(dlg, "pod_vu_label", 1);
    if (!pm.lv || !pm.sv || !pm.bar || !pm.glass || !more_label || !back_label || !speed_label || !note_label ||
        !tape_label || !vinyl_label || !goep_label || !art_label || !sleep_label || !mode_label || !lyr_label ||
        !vu_label)
        goto fail;
    for (i = 0; i < PM_ROWS; i++) { /* exactly the asset: seventeen rows in the scroll_view */
        pm.row[i] = widget_lookup(dlg, names[i], 1);
        if (!pm.row[i] || *(void **)((char *)pm.row[i] + W_PARENT) != pm.sv) goto fail;
    }
    if (widget_count_children(pm.sv) != PM_ROWS) goto fail;
    if (widget_set_tr_text(more_label, "More") != RET_OK) goto fail;
    if (widget_set_tr_text(back_label, "Display Mode") != RET_OK)
        goto fail; /* the Display Mode page's header text, tried here: pm_arrange sets the shown page's */
    if (widget_set_tr_text(back_label, "More") != RET_OK) goto fail;
    if (widget_set_tr_text(mode_label, "Display Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(lyr_label, "Lyrics Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(speed_label, "Speed") != RET_OK)
        goto fail; /* the stock "Multiple Speed" is wider than the room before the badges */
    if (widget_set_tr_text(note_label, "Files below 48 kHz only") != RET_OK) goto fail;
    if (widget_set_tr_text(tape_label, "Cassette Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(vinyl_label, "Vinyl Mode") != RET_OK) goto fail;
    if (widget_set_tr_text(vu_label, "VU Meter Mode") != RET_OK) goto fail;
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
    if (!widget_on(pm.row[PM_MODE], EVT_CLICK, pm_on_mode, dlg)) goto fail;
    if (!widget_on(pm.row[PM_LYR], EVT_CLICK, pm_on_lyr, dlg)) goto fail;
    if (!widget_on(pm.row[PM_VU], EVT_CLICK, pm_on_vu, dlg)) goto fail;
    pm.back_label = back_label;
    if (!widget_on(pm.row[GO_ALBUM], EVT_CLICK, pm_on_lookup_album, dlg)) goto fail;
    if (!widget_on(pm.row[GO_ARTIST], EVT_CLICK, pm_on_lookup_artist, dlg)) goto fail;
    if (!widget_on(pm.row[PM_DELETE], EVT_CLICK, pm_on_delete, dlg)) goto fail;
    if (!widget_on(pm.row[PM_ADDPL], EVT_CLICK, pm_on_addpl, dlg)) goto fail;
    pm.page = 0;
    track = cc_playing();
    pm.srv = track && sba_rec_track(*(int *)((char *)track + REC_ID))[0] != 0;
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
