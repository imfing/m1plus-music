/* M1+ Music keyboard embedded in the stock Tidal > Search page (docs/modules/tidalkb.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Stock's page init (tidal_tidal_serach_page_init 0x4c4a24) walks its widgets with a callback (0x4c1f3c); for the edit `search_edit` the callback calls edit_set_focus(edit, 1) at
 * 0x4c2088, and that focus is what pops stock's T9 keyboard, then binds the IM action event (0x13c) to 0x4c4990 and sets the tips. The call site `jalr edit_set_focus` is now `jal tidal_kb_focus`
 * (the lw t9, a1 = 1 and the delay slot `move a0, s0` stay stock's; stock ignores the result).
 * The page asset (tools/pod_ui.py add_tidal_keyboard) carries our field inside the search bar (kb_field with the hint, text, caret and clear button, over the stock edit) and the keyboard's pad,
 * candidate strip and pop-up at the bottom of the window. The hook hides the stock edit, attaches the pad (keyboard_attach, patch/keyboard.c: the same embedding the Search
 * and Radio pages use) and returns without focusing the edit, so nothing opens: the Tidal page stays on screen, the pad is up and the typing shows in the bar. Every change of the text is written into
 * the edit (stock's search routine 0x4c4740 reads only the window of its a0 and `search_edit`). The action key trims the text, runs 0x4c4740 (history file, result page, empty-text warning)
 * and hides the pad so the results show; a tap on the bar (EVT_CLICK of the list_item that holds it, which the field passes on: a view has no on_event) shows the pad again. Text that stock puts
 * into the edit itself (a tap on a history row: 0x4c2edc -> 0x4c2254) is picked up by a page-scoped poll, shown in the bar, and hides the pad.
 * The navbar's own Search button (stock binds EVT_CLICK -> 0x4c4740 on it before the hook runs) gets our handler on top: the action key's submission, RET_STOP.
 * Fallback, stock's own T9 (our pad and field are then hidden and made insensitive): an edit in no window, an asset without our widgets or a keyboard already up (keyboard_attach refuses), a handler that will not bind. It is decided
 * once, at the page's init, before anything is changed. No hook besides the one call site; no allocation; never at boot.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "keyboard.h"
#include "tidalkb.h"
#include "i18n.h"

#define TK_POLL_MS 250 /* how often the bar is compared with what stock put into the edit */
#define TK_MAX 127 /* bytes of text: the stock edit's own limit (its search routine's buffers are 0x100) */
#define TK_TEXT (TK_MAX + 1)
#define TK_BTN_X 273 /* stock's navbar Search button: button_create(navbar, 0x111, 0, 0x2f, 0x32) */
#define TK_BTN_W 47
#define TK_BTN_H 50

static struct {
    void *win, *edit; /* the Tidal search page and its search_edit; 0 when none is attached */
    unsigned timer; /* the poll (0: none) */
} tk __attribute__((section(".scratch")));

static void tk_stop(void) {
    if (tk.timer) timer_remove(tk.timer);
    tk.timer = 0;
}

/* The pad's text changed: the stock edit holds it too (the search routine reads only the edit). */
static void tk_on_change(const char *text) {
    if (tk.edit) widget_set_text_utf8(tk.edit, text);
}

/* A new search starts from nothing, as stock's tab buttons do (btn_track 0x4c2854, btn_artist 0x4c27c0, btn_album 0x4c272c): the search threads only download, and the page's timer (0x4c3bb4 -> 0x4c3238)
 * parses the answer with _deque_push_back onto *(struct + 0xc), so without this the new results are appended behind the old ones. The three result structs (tracks, artists, albums) are { total, limit,
 * offset, deque }: limit back to 50, offset 0, the deque cleared; the scroll offset the timer restores (0xa04150) back to the top. All three, not only the current tab's (0xa04158 picks which one
 * 0x4c2380 searches): a tab tap clears and searches its own again, so nothing is lost. Only the UI thread touches the deques (the threads download, the timer parses). */
static void tk_reset_results(void) {
    static const unsigned structs[3] = {TIDAL_TRACKS, TIDAL_ARTISTS, TIDAL_ALBUMS};
    unsigned i;
    for (i = 0; i < 3; ++i) {
        int *r = (int *)structs[i];
        void *dq = (void *)r[3];
        r[1] = 50;
        r[2] = 0;
        if (dq) deque_clear(dq);
    }
    *(volatile int *)TIDAL_SCROLL = 0;
}

/* The action key: the text without spaces at both ends goes to the edit and to stock's search, and the pad gives way to the results. An empty text does nothing (the pad stays). */
static void tk_on_go(void) {
    char text[TK_TEXT];
    const char *s = keyboard_text();
    unsigned a = 0, b = 0, i;
    while (s[b]) ++b;
    while (a < b && s[a] == ' ') ++a;
    while (b > a && s[b - 1] == ' ') --b;
    if (a == b || !tk.edit) return;
    for (i = a; i < b; ++i) text[i - a] = s[i];
    text[b - a] = 0;
    keyboard_set_text(text); /* the bar shows the trimmed text; on_change writes it into the edit */
    keyboard_show(0);
    tk_reset_results();
    stock_tidal_search(tk.edit, (void *)0);
}

/* What stock wrote into the edit (a history row tap) is the bar's text from now on, and the pad goes. */
static void tk_sync(void) {
    char cur[TK_TEXT * 4];
    if (!tk.edit || pod_text_utf8(tk.edit, cur, sizeof cur) < 0 || !strcmp(cur, keyboard_text())) return;
    keyboard_set_text(cur);
    keyboard_show(0);
}

static int tk_tick(const void *unused);

static void tk_arm(void) { tk.timer = timer_add(tk_tick, (void *)0, TK_POLL_MS); }

static int tk_tick(const void *unused) {
    (void)unused;
    tk.timer = 0;
    if (!tk.win) return RET_OK;
    tk_sync();
    tk_arm();
    return RET_OK;
}

static int tk_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != tk.win) return RET_OK; /* a page that was replaced meanwhile */
    tk_stop();
    keyboard_detach();
    memset(&tk, 0, sizeof tk);
    return RET_OK;
}

/* A tap on the bar (the click of the list_item that holds the field and the stock edit): the pad comes back with the bar's text. */
static int tk_on_click(void *ctx, void *e) {
    (void)e;
    if (ctx != tk.edit || !tk.win || keyboard_shown()) return RET_OK;
    tk_sync();
    keyboard_show(1);
    return RET_OK;
}

/* Stock's navbar Search button (button_create(navbar, 273, 0, 47, 50) in the page init 0x4c4a74..0x4c4a8c, EVT_CLICK -> 0x4c4740 with the window as context, 0x4c4aac..0x4c4ac8) runs the search
 * directly: the pad would stay up over the results and tk_reset_results would be skipped. Our handler is bound after it, and the emitter runs the newest first (emitter_on_with_tag puts a handler at
 * the head), so it takes the tap: the action key's submission (keyboard_go, which commits a pending composition first), and RET_STOP so that stock's handler does not run as well. An empty text does nothing, as the action key. */
static int tk_on_search_btn(void *ctx, void *e) {
    (void)e;
    if (ctx != tk.win || !tk.edit) return RET_OK; /* a page that was replaced meanwhile: stock's search */
    tk_sync(); /* a history text stock wrote that the poll has not shown yet */
    keyboard_go(); /* the action key's path: a pending pinyin composition is committed first (kb_finish), then tk_on_go */
    return RET_STOP;
}

/* The button: the last child of the navbar when it has stock's geometry (the page init adds it just before the widget_foreach that runs the hook); NULL for any other layout. */
static void *tk_search_btn(void *win) {
    void *nav = widget_lookup(win, "navigationbar_view", 1), *b;
    unsigned n;
    if (!nav) return (void *)0;
    n = widget_count_children(nav);
    if (!n) return (void *)0;
    b = widget_get_child(nav, n - 1);
    if (!b || *(int *)((char *)b + W_X) != TK_BTN_X || *(int *)((char *)b + W_Y) != 0 ||
        *(int *)((char *)b + W_W) != TK_BTN_W || *(int *)((char *)b + W_H) != TK_BTN_H)
        return (void *)0;
    return b;
}

/* Stock's T9 is used instead: our widgets must not stay on the page (the asset starts the pad visible and the field in the bar sensitive, over the stock edit and the results). */
static void tk_hide_ours(void *win) {
    static const char *const names[2] = {"kb_pad", "kb_field"};
    unsigned i;
    for (i = 0; i < 2; ++i) {
        void *w = widget_lookup(win, names[i], 1);
        if (!w) continue;
        widget_set_visible(w, 0, 0);
        widget_set_sensitive(w, 0);
    }
}

/* The hook (tools/pod.py TIDALKB_SITE): edit_set_focus(edit, 1) of stock's bind callback. */
int tidal_kb_focus(void *edit, int on) {
    void *win, *bar, *btn;
    const char *hint = TR("Search Tidal"); /* fits TK_TEXT_W in every language (test/pod/tidalkb.py asset_tests) */
    if (!edit || on != 1) return edit_set_focus(edit, on);
    win = widget_get_window(edit);
    if (!win) return edit_set_focus(edit, on);
    if (keyboard_busy()) {
        tk_hide_ours(win);
        return edit_set_focus(edit, on);
    }
    tk_stop();
    memset(&tk, 0, sizeof tk);
    /* the click comes from the list_item `listitem_ssid` that holds the field (list_item_on_event 0x60bb80, see docs/modules/tidalkb.md): bind there (the edit itself if it has no parent but the window) */
    bar = *(void **)((char *)edit + W_PARENT);
    if (!bar || bar == win) bar = edit;
    btn = tk_search_btn(win);
    if (!btn || keyboard_attach(win, hint, TK_TEXT_X, TK_TEXT_W, TK_CARET_Y, 0, tk_on_change, tk_on_go) != 0) {
        tk_hide_ours(win);
        return edit_set_focus(edit, on); /* an asset without our widgets or another navbar */
    }
    if (!widget_on(win, EVT_DESTROY, tk_on_destroy, win) || !widget_on(bar, EVT_CLICK, tk_on_click, edit) ||
        !widget_on(btn, EVT_CLICK, tk_on_search_btn, win)) {
        keyboard_detach(); /* a handler that did not bind: stock's T9 (one that did finds no attached page and does nothing) */
        memset(&tk, 0, sizeof tk);
        tk_hide_ours(win);
        return edit_set_focus(edit, on);
    }
    keyboard_set_max(TK_MAX);
    tk.win = win, tk.edit = edit;
    tk_arm(); /* (no timer: a history row's text then reaches the bar at the next tap on it) */
    widget_set_visible(edit, 0, 0); /* our field is the bar's text now; the stock edit stays for the search routine */
    widget_set_sensitive(edit, 0);
    return RET_OK;
}
