/* The pull-down's tiles: which of the eight show and in what order, and the Settings > Appearance > Control Center page that edits it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The pull-down is the stock dialog/dropdown_dialog (ui/dialog/dropdown_dialog.bin, the status bar swipe): in its view_switchs eight
 * 50 x 50 tile images (img_wifiswitch, img_btswitch, img_keylockswitch, img_gainswitch, img_usbmode, img_outputswitch, img_playset,
 * img_sysset: the tile ids '0'..'7', the stock slot order, four in a row) each with a caption label (label_wifi, label_bt, label_lock,
 * label_gain, label_usbmode, label_outputway, label_playset, label_sysset). The setting is one small file, PULLDOWN_FILE: the shown
 * tiles' ids in order, optionally '-' and the hidden ones ("01234567", all shown in the stock order, is the default; the home-menu
 * file's grammar, tools/pod_pages.py parse_pulldown is the model and test/pod/pulldown_tiles.py fuzzes the two against each other):
 * known characters only, no id twice, '-' at most once, a file shorter than PD_FILE_MAX; anything else, or no file, is the default.
 * Every tile the shown part does not list is hidden.
 *
 * Two hooks: on_wm_tsdown_fun (0x4cd6e8, tools/pod.py TSDOWN, the swipe's gates, below) and dialog_dropdown_dialog_init (0x475f04, tools/pod.py PULLDOWN_INIT): run when the dialog is built (never at boot or in the
 * main loop; the navigator's dialog-init dispatcher is its only caller). m1plus_pulldown_init runs the stock init to completion (it
 * binds the dialog's pointer handlers and, through its widget_foreach visitor, every tile's click: we move tiles, we do not replace
 * behaviour) and returns its result; then, if every tile and caption is found,
 * shown tile k takes the place the stock tile k has (read from the widgets, not hard-coded) with its caption at the same offset,
 * and the other tiles and captions are hidden: visible=false and sensitive=false (a hidden widget would still take touches).
 * Nothing is renamed or deleted, the dialog's size and the brightness slider stay. Everything fallible (the lookups) happens before
 * the first move; the default file moves nothing at all.
 *
 * The Control Center page (ui/m1plus_pulldown.bin, opened by patch/m1plus.c) is the Main Menu page's twin (patch/menu.c "The Main Menu
 * page"): a row per tile with a switch and an up arrow on every shown row but the first, both pictures (insensitive); the row takes
 * every tap and decides by where it is: on the arrow's rectangle it moves the tile one place up, elsewhere it shows or hides it (a
 * tile shown joins the end). The shown tiles come first in order, the hidden ones after them in the stock order. Each change is saved
 * at once; a failed save is undone and the page stays as it was.
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "entries.h"
#include "battery.h"
#include "lineout.h"
#include "shot.h"
#include "covercache.h"
#include "palette.h"
#include "minibar.h"
#include "radio.h"
#include "sbapi.h"
#include "peqlib.h"
#include "podcasts.h"

#define PD_N 16 /* every tile: the eight stock ones, then ours (ids '8', '9', 'a' ... 'f') */
#define PD_STOCK 8 /* ids 0-7 are the stock tiles: the default shows them in this order */
#define PD_SLOTS 8 /* the pull-down has room for eight tiles: a file that shows more is invalid */
#define PD_FILE_MAX 20 /* tools/pod_pages.py PULLDOWN_FILE_MAX */
#define PD_QUIT \
    0xd /* dialog_quit's result the stock tile handlers use: on_wm_tsmove_fun goes on to open a page only for it */

enum {
    PD_SLEEP = PD_STOCK,
    PD_SETTINGS,
    PD_EQ,
    PD_POWER,
    PD_AIRPLAY,
    PD_DLNA,
    PD_TRANSFER,
    PD_SHOT
}; /* the ids of our tiles (AirPlay and DLNA are switches, not actions) */

#define PD_ACT_WIFI (PD_N + 0u) /* long press on the Wi-Fi tile (img_wifiswitch) */
#define PD_ACT_BT (PD_N + 1u) /* long press on the Bluetooth tile (img_btswitch) */
#define PD_ACT_NP (PD_N + 2u) /* a tap on page 2's Now Playing card */
#define PD_ACT_QUEUE (PD_N + 3u) /* page 2's Up Next, Go to Artist and Go to Album discs */
#define PD_ACT_ARTIST (PD_N + 4u)
#define PD_ACT_ALBUM (PD_N + 5u)
#define PD_ACT_MODE (PD_N + 6u) /* Play Mode: not a page, the pull-down stays */
#define PD_ACT_PODS \
    (PD_N + \
     7u) /* page 2's podcast and audiobook discs: the Podcasts and Audiobooks pages, the episode's notes (the show's or the book's page) */
#define PD_ACT_BOOKS (PD_N + 8u)
#define PD_ACT_NOTES (PD_N + 10u)
#define PD_ACT_RD_NP \
    (PD_N + \
     20u) /* page 2 for a radio station: its card (Radio Now Playing), the four discs (My Stations, Recently Played, Station Info, Search) */
#define PD_ACT_RD_MY (PD_N + 21u)
#define PD_ACT_RD_RECENT (PD_N + 22u)
#define PD_ACT_RD_INFO (PD_N + 23u)
#define PD_ACT_RD_SEARCH (PD_N + 24u)

/* Our tiles' widgets are in the asset (tools/mod_pulldown.py), hidden and insensitive, named pod_tile_* / pod_cap_*. */
static const char *const PD_IMG[PD_N] = {"img_wifiswitch",   "img_btswitch",      "img_keylockswitch", "img_gainswitch",
                                         "img_usbmode",      "img_outputswitch",  "img_playset",       "img_sysset",
                                         "pod_tile_sleep",   "pod_tile_settings", "pod_tile_eq",       "pod_tile_power",
                                         "pod_tile_airplay", "pod_tile_dlna",     "pod_tile_transfer", "pod_tile_shot"};
static const char *const PD_LAB[PD_N] = {"label_wifi",      "label_bt",         "label_lock",       "label_gain",
                                         "label_usbmode",   "label_outputway",  "label_playset",    "label_sysset",
                                         "pod_cap_sleep",   "pod_cap_settings", "pod_cap_eq",       "pod_cap_power",
                                         "pod_cap_airplay", "pod_cap_dlna",     "pod_cap_transfer", "pod_cap_shot"};

static const char *pd_name(void *w);
static void pd_close_subpages(const char *name);
static void pd_close_children(const char *name);
static void *pd_by_name(const char *name);

/* The id of a file character ('0'-'9', 'a'-'f'), or PD_N. */
static unsigned pd_id(char c) {
    return c >= '0' && c <= '9' ? (unsigned)(c - '0') : c >= 'a' && c <= 'f' ? (unsigned)(c - 'a') + 10u : PD_N;
}

/* The shown tiles in order (ord, at least PD_N long) from the saved file; the count. The default: the eight stock tiles in stock order
 * (ord is then every id in order). */
static unsigned pd_load(unsigned char *ord) {
    char buf[PD_FILE_MAX];
    unsigned char tmp[PD_N];
    int fd, n;
    unsigned i, len, part = 0, k = 0, seen = 0;
    for (i = 0; i < PD_N; i++) ord[i] = (unsigned char)i;
    fd = open(PULLDOWN_FILE, 0, 0);
    if (fd < 0) return PD_STOCK;
    n = read(fd, buf, sizeof buf);
    close(fd);
    if (n <= 0 || n >= (int)sizeof buf) return PD_STOCK; /* empty, or too long to be a list */
    len = (unsigned)n - (buf[n - 1] == '\n');
    for (i = 0; i < len; i++) {
        unsigned id;
        if (buf[i] == '-') { /* the hidden part starts: once */
            if (part) return PD_STOCK;
            part = 1;
            continue;
        }
        id = pd_id(buf[i]);
        if (id >= PD_N || (seen >> id & 1)) return PD_STOCK;
        seen |= 1u << id;
        if (!part) {
            if (k >= PD_SLOTS) return PD_STOCK; /* more than the pull-down holds */
            tmp[k++] = (unsigned char)id;
        }
    }
    for (i = 0; i < k; i++) ord[i] = tmp[i];
    return k;
}

/* ---- the pull-down */

/* What a tap on one of our tiles does. Stock's Playback and System tiles never open a page from their click handler: they quit the dialog with PD_QUIT and set a flag, and on_wm_tsmove_fun
 * (the status bar swipe, which opened the dialog MODALLY with navigator_to and carries on when it returns) opens the page after it. Ours do the same: the click handler checks what the stock
 * handlers check, stores which tile it was in pd_pending and quits the dialog; pd_open_dialog (the hook at that navigator_to call) runs the action once the dialog is gone. The Power Off
 * tile is the case that opens no page: pd_poweroff. */
static struct {
    void *dlg, *img;
    unsigned id;
} pd_tile[PD_N - PD_STOCK] __attribute__((section(".scratch")));
static unsigned pd_pending
    __attribute__((section(".scratch"))); /* tile id + 1 of the tap the dialog was quit for, 0: none */

/* The AirPlay and DLNA tiles are switches: the tap calls stock's own switch (airplay_switch 0x5076a8, dlna_switch 0x507674: flip the setting byte and write [SYSSET] AIRPLAY / DLNA to the settings ini, what
 * the Network Service page's rows do), and the tile's picture follows the byte: the lit disc when it is on, the ring when off, as stock's Wi-Fi tile (the visitor 0x473f30 sets drop_wifiopen / drop_wifi
 * from its flag when the dialog is built). The service itself is not touched: stock's network-status timer (on_wm_timer_networkstatus 0x4cfd94: airplay_start, dmr_serverstart) starts or stops it to
 * match the byte within a second, and only while Wi-Fi is connected. The dialog stays open (nothing is pending, nothing quits). Switching on with no Wi-Fi keeps the preference and says so. */
static int pd_is_switch(unsigned id) { return id == PD_AIRPLAY || id == PD_DLNA; }

static int pd_switch_on(unsigned id) {
    return *(volatile unsigned char *)(id == PD_AIRPLAY ? AIRPLAY_FLAG : DLNA_FLAG) != 0;
}

static void pd_switch_art(unsigned id, void *img) {
    int on = pd_switch_on(id);
    image_base_set_image(img, id == PD_AIRPLAY ? (on ? "drop_airplayopen" : "drop_airplay")
                                               : (on ? "drop_dlnaopen" : "drop_dlna"));
    widget_invalidate_force(img, (void *)0);
}

static void pd_sleep_art(void *img) {
    int on = *(volatile unsigned char *)SLEEP_FLAG != 0 && *(volatile int *)SLEEP_TIME > 0;
    image_base_set_image(img, on ? "drop_sleepopen" : "drop_sleep");
}

static void pd_switch(unsigned id, void *img) {
    if (id == PD_AIRPLAY)
        airplay_switch();
    else
        dlna_switch();
    pd_switch_art(id, img);
    if (pd_switch_on(id) && networkGetConnectStatus() <= 0) pod_toast(TR("Connect to Wi-Fi first"));
}

/* The three conditions of the stock tile handlers (0x4754c8): a tile does nothing while they hold. */
static int pd_blocked(void) {
    return *(int *)DROPDOWN_BUSY == 2 || *(int *)POWER_USBSTATE == 2 || airplayGetFlag() == 2;
}

static int pd_on_tile(void *ctx, void *e) {
    unsigned k = (unsigned)((char *)ctx - (char *)pd_tile) / (unsigned)sizeof pd_tile[0];
    (void)e;
    if (k >= PD_N - PD_STOCK || !pd_tile[k].dlg || pd_blocked()) return RET_OK;
    if (pd_is_switch(pd_tile[k].id)) { /* stays open */
        pd_switch(pd_tile[k].id, pd_tile[k].img);
        return RET_OK;
    }
    pd_pending = pd_tile[k].id + 1;
    if (dialog_quit(pd_tile[k].dlg, PD_QUIT) != RET_OK) pd_pending = 0; /* the dialog stays as it was */
    return RET_OK;
}

/* Long press on the stock Wi-Fi (0) and Bluetooth (1) tiles (same RM_LONG_MS hold and SC_DRAG_PX move limit as Home Screen pins, patch/pins.c):
 * holding fires while the finger is still down, stores PD_ACT_WIFI / PD_ACT_BT in pd_pending and quits the dialog with PD_QUIT so pd_open_dialog opens
 * or restacks the page once the modal dialog returns. Our EVT_CLICK listener is bound after stock's (so runs first) and answers RET_STOP after a fired
 * hold so stock's toggle never runs on release. Resetting PRESSDOWN_Y stops a residual drag on row 1 (y 51..80 < 81) from re-opening the pull-down. */
static struct {
    void *dlg;
    unsigned timer;
    unsigned down; /* 1 = Wi-Fi, 2 = Bluetooth, 0 = none */
    unsigned fired; /* 1 = Wi-Fi, 2 = Bluetooth: long press fired for this touch */
    m1_tap_t tap;
} pd_hold __attribute__((section(".scratch")));

static void pd_hold_reset(void) {
    m1_timer_stop(&pd_hold.timer);
    memset(&pd_hold, 0, sizeof pd_hold);
}

static int pd_on_hold_fire(const void *info) {
    unsigned which = pd_hold.down;
    void *dlg = pd_hold.dlg;
    (void)info;
    pd_hold.timer = 0;
    pd_hold.down = 0;
    if (!which || !dlg || pd_blocked()) return RET_OK;
    pd_hold.fired = which;
    pd_pending = (which == 1 ? PD_ACT_WIFI : PD_ACT_BT) + 1;
    if (dialog_quit(dlg, PD_QUIT) == RET_OK)
        *(volatile int *)PRESSDOWN_Y = 480;
    else
        pd_pending = 0;
    return RET_OK;
}

static int pd_on_hold_touch(void *ctx, void *e) {
    unsigned which = (unsigned)(long)ctx;
    int type = e ? *(int *)e : 0;
    if (type == EVT_POINTER_DOWN) {
        m1_timer_stop(&pd_hold.timer);
        pd_hold.fired = 0;
        pd_hold.down = 0;
        if (!e || !pd_hold.dlg || pd_blocked()) return RET_OK;
        pd_hold.down = which;
        m1_tap_at(&pd_hold.tap, e);
        pd_hold.timer = timer_add(pd_on_hold_fire, (void *)0, RM_LONG_MS);
    } else if (type == EVT_POINTER_MOVE) {
        if (pd_hold.down == which && (!e || !m1_tap_near(&pd_hold.tap, e))) {
            m1_timer_stop(&pd_hold.timer);
            pd_hold.down = 0;
        }
    } else if (pd_hold.down == which) { /* UP or ABORT */
        m1_timer_stop(&pd_hold.timer);
        pd_hold.down = 0;
    }
    return RET_OK;
}

static int pd_on_hold_click(void *ctx, void *e) {
    unsigned which = (unsigned)(long)ctx;
    (void)e;
    if (pd_hold.fired == which) {
        pd_hold.fired = 0;
        return RET_STOP; /* suppress stock's toggle click after a long press */
    }
    return RET_OK;
}

static void pd_bind_hold(void *dlg, void *const *img, unsigned shown) {
    unsigned t;
    pd_hold_reset();
    pd_hold.dlg = dlg;
    for (t = 0; t < 2; t++) {
        if (!(shown >> t & 1) || !img[t]) continue;
        /* Bind DOWN last: if any earlier listener cannot be bound, no hold timer can start. */
        if (widget_on(img[t], EVT_POINTER_MOVE, pd_on_hold_touch, (void *)(long)(t + 1)) &&
            widget_on(img[t], EVT_POINTER_UP, pd_on_hold_touch, (void *)(long)(t + 1)) &&
            widget_on(img[t], EVT_POINTER_ABORT, pd_on_hold_touch, (void *)(long)(t + 1)) &&
            widget_on(img[t], EVT_CLICK, pd_on_hold_click, (void *)(long)(t + 1)))
            widget_on(img[t], EVT_POINTER_DOWN, pd_on_hold_touch, (void *)(long)(t + 1));
    }
}

/* The window in front is the one called name: it is left alone (window_manager_switch_to with the window itself is not what stock ever does). */
static int pd_front(const char *name) {
    void *wm = window_manager();
    const char *top = wm ? pd_name(window_manager_get_top_window(wm)) : (const char *)0;
    return top && !strcmp(top, name);
}

/* Our own page: when its window is already in the stack its sub-pages are closed and it is brought to the front, else it is opened afresh (a page of ours keeps one window, see pd_close_subpages);
 * a page already in front is left alone. Its callers are tiles: the page is rooted (pd_note_opener), not the sub-page of the window that happened to be in front. */
int pd_open_own(const char *window, int (*open_it)(void)) {
    void *w;
    if (pd_front(window)) return 1;
    pd_close_subpages(window);
    w = m1_restack_window(window);
    if (!w) {
        if (open_it() != 0) return 0;
        w = pd_by_name(window);
    }
    pd_note_opener(w, (void *)0);
    return 1;
}

/* ---- who opened what
 *
 * A page of ours that more than one route opens (the Volume page and its rows, Settings' Gain / Equalizer / Volume & Sound rows, the Equalizer tile) must not close a window it did not open: its sub-pages are not
 * "the windows above it" (a Settings page the Control Center opened over it, or the Equalizer opened from a tile over Volume, sit there too). pd_op records, for a window of ours, the window it was opened from:
 * open_page (patch/m1plus.c) notes the window in front when a page opens (a row tap is on the page in front); the tile and status bar routes (pd_open_page, rooted) note NULL. Entries: 16 in .scratch, no
 * allocation; an entry is cleared by its window's EVT_DESTROY (which also turns the entries opened from it into PD_ORPHAN: a freed address is never taken for an opener), and a full table first drops the
 * entries of windows that are no longer open. A window with no entry (stock's, or a full table) is nobody's child and is never closed by pd_close_children.
 * Reopening a page that is already in the stack: its entry follows the route that reopens it. A row tap makes the page in front its opener (Back returns there); a tile or the status bar makes it rooted. */
#define PD_OPS 16
#define PD_ORPHAN ((void *)1) /* the opener went away */
static struct {
    void *win, *from;
} pd_op[PD_OPS] __attribute__((section(".scratch")));

static int pd_find(void *w) {
    int i;
    for (i = 0; i < PD_OPS; i++)
        if (w && pd_op[i].win == w) return i;
    return -1;
}

void *pd_front_window(void) {
    void *wm = window_manager();
    return wm ? window_manager_get_top_window(wm) : (void *)0;
}

/* w is a window in the manager that is not closing. */
static int pd_alive(void *w) {
    void *wm = window_manager();
    unsigned n;
    if (!wm || !w) return 0;
    for (n = widget_count_children(wm); n--;)
        if (widget_get_child(wm, n) == w) return widget_is_window_opened(w) != 0;
    return 0;
}

static int pd_op_gone(void *ctx, void *e) {
    int i = pd_find(ctx);
    (void)e;
    if (i >= 0) pd_op[i].win = (void *)0;
    for (i = 0; i < PD_OPS; i++)
        if (pd_op[i].win && pd_op[i].from == ctx) pd_op[i].from = PD_ORPHAN;
    return RET_OK;
}

/* win was opened from `from` (NULL: by a tile or the status bar). */
void pd_note_opener(void *win, void *from) {
    int i = pd_find(win);
    if (!win) return;
    if (i < 0) {
        for (i = 0; i < PD_OPS && pd_op[i].win; i++) {
        }
        if (i == PD_OPS) { /* full: the entries of windows that are gone */
            int k;
            for (k = 0; k < PD_OPS; k++)
                if (!pd_alive(pd_op[k].win)) pd_op[k].win = (void *)0;
            for (i = 0; i < PD_OPS && pd_op[i].win; i++) {
            }
            if (i == PD_OPS) return;
        }
        if (!widget_on(win, EVT_DESTROY, pd_op_gone, win)) return;
        pd_op[i].win = win;
    }
    pd_op[i].from = from;
}

/* window_open for a page a row or a button of the page in front opens: that page is recorded as its opener. Every window of ours that can sit above a page pd_open_page reopens is opened through here. */
void *pd_window_open(const char *asset) {
    void *from = pd_front_window(), *win = window_open(asset);
    if (win && from) pd_note_opener(win, from);
    return win;
}

/* w was opened by the window `of` or by a window that was (its chain of openers leads to `of`). */
static int pd_under(void *w, void *of) {
    int i, hops;
    for (hops = 0; hops < PD_OPS; hops++) {
        i = pd_find(w);
        if (i < 0 || !pd_op[i].from || pd_op[i].from == PD_ORPHAN) return 0;
        if (pd_op[i].from == of) return 1;
        w = pd_op[i].from;
    }
    return 0;
}

/* w hangs from a window a tile or the status bar opened (a rooted entry) without passing through `of`. */
static int pd_rooted(void *w, void *of) {
    int i, hops;
    for (hops = 0; hops < PD_OPS; hops++) {
        i = pd_find(w);
        if (i < 0 || pd_op[i].from == PD_ORPHAN) return 0;
        if (!pd_op[i].from) return 1;
        if (pd_op[i].from == of) return 0;
        w = pd_op[i].from;
    }
    return 0;
}

/* The topmost window called name. */
static void *pd_by_name(const char *name) {
    void *wm = window_manager();
    unsigned n;
    if (!wm) return (void *)0;
    for (n = widget_count_children(wm); n--;) {
        const char *nm = pd_name(widget_get_child(wm, n));
        if (nm && !strcmp(nm, name)) return widget_get_child(wm, n);
    }
    return (void *)0;
}

/* The windows the page `name` opened (the chain of openers leads to it), wherever they are in the stack, are closed, the topmost first; nothing else is. */
static void pd_close_children(const char *name) {
    void *wm = window_manager(), *page = pd_by_name(name), *sub[8];
    unsigned n, i, k = 0;
    if (!wm || !page) return;
    n = widget_count_children(wm);
    for (i = 0; i < n && k < 8; i++) {
        void *w = widget_get_child(wm, i);
        if (w && pd_under(w, page) && widget_is_window_opened(w)) sub[k++] = w;
    }
    while (k--) window_close(sub[k]);
}

/* A page of ours that more than one route opens: left alone in front; else the windows it opened are closed (pd_close_children), and it is restacked, else open_it()ed. Every route goes through here: the
 * Control Center Equalizer tile and the Volume status bar tap (rooted), the Volume page's rows and Settings' Gain / Equalizer / Volume & Sound rows (not: the page in front is the opener). 1 when it is up. */
int pd_open_page(const char *window, int (*open_it)(void), int rooted) {
    void *from, *w;
    if (pd_front(window)) return 1;
    from = rooted ? (void *)0 : pd_front_window();
    pd_close_children(window);
    w = m1_restack_window(window);
    if (!w) {
        if (open_it() != 0) return 0;
        w = pd_by_name(window);
    }
    if (rooted)
        pd_note_opener(w, (void *)0);
    else if (pd_alive(from))
        pd_note_opener(w, from);
    return 1;
}

/* Power Off: what the power key's long press does (on_wm_keylong_fun 0x4cdd9c), without the key: ignored while standby_mode is nonzero (a confirm is up, or poweroff_page has run) or the key's own
 * block word is 2; then the screen is lit, standby_mode = 1, the stock confirm (kind 1, the text of "msg_poweroff", modal, over the page like our confirms); Yes (CONFIRM_YES) opens poweroff_page,
 * whose init does the whole stock shutdown (resume record, stop, DAC off, splash, poweroff after ~2 s); any other answer sets standby_mode back to 0. This code never calls system() or reboots
 * (that would skip the resume save); the key-only byte stock also sets (0xa041b8) is not needed. */
static void pd_poweroff(void) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    if (*(int *)STANDBY_MODE != 0 || *(int *)POWERKEY_BLOCK == 2) return;
    awake_screen();
    *(int *)STANDBY_MODE = 1;
    memset(&info, 0, sizeof info);
    info.kind = MSGINFO_KIND;
    getFormatString("msg_poweroff", info.text, sizeof info.text);
    if (pod_confirm_dialog(&info) == CONFIRM_YES && navigator_to("poweroff_page") == RET_OK) return;
    *(int *)STANDBY_MODE = 0; /* No, Back, or a page that will not open */
}

/* The action of tile id (PD_SLEEP ..): our Sleep Timer page (as Now Playing's Sleep Timer row opens it), the Settings root and the Equalizer page the All Playback Settings row opens, or the Power Off
 * confirm. A page that will not open leaves nothing to show (the dialog is gone by now, as stock's own tile when navigator_to fails). */
static void pd_run(unsigned id) {
    if (id == PD_POWER)
        pd_poweroff();
    else if (id == PD_SLEEP) {
        pd_open_own("m1plus_sleeptimer_page", pod_open_sleeptimer);
    } else if (id == PD_SETTINGS)
        pd_open_own("m1plus_settings_page", pod_open_settings);
    else if (id == PD_EQ)
        pd_open_page("m1plus_peq_page", pod_open_peq, 1);
    else if (id == PD_TRANSFER && ns_transfer_ok())
        pd_open_page("m1plus_wifitransfer_page", pod_open_wifitransfer, 1); /* one window with Network Services' row */
    else if (id == PD_SHOT)
        shot_start(); /* the Developer > Screenshot row's confirm */
    else if (id == PD_ACT_WIFI) {
        if (access(KILL_SD, F_OK) == 0 || !pd_open_page("m1plus_wifi_page", wifipage_open, 1))
            navigator_to("systemset/wifi_page");
    } else if (id == PD_ACT_BT) {
        if (access(KILL_SD, F_OK) == 0 || !pd_open_page("m1plus_bluetooth_page", btpage_open, 1))
            navigator_to("systemset/bluetooth_page");
    } else if (id == PD_ACT_NP)
        m1_open_now_playing(); /* Radio's page while a station plays, else stock's player (the Home bar's card) */
    else if (id == PD_ACT_QUEUE) {
        if (queue_open() == -2)
            navigator_to(
                "dialog/playqueue_dialog"); /* Now Playing's queue button: our page, the stock drawer when its window will not open */
    } else if (id == PD_ACT_ARTIST || id == PD_ACT_ALBUM) {
        if (!pm_goto(id == PD_ACT_ARTIST)) pod_toast(TR("Not found")); /* the More sheet's Look up rows */
    } else if (id == PD_ACT_PODS)
        podcasts_goto((const char *)0, 0);
    else if (id == PD_ACT_BOOKS)
        books_goto((const char *)0);
    else if (
        id ==
        PD_ACT_NOTES) { /* the playing episode's show and notes, the playing part's book (its page is its info too) */
        void *t = cc_playing();
        const char *path = t ? cc_str(t, REC_PATH) : "";
        if (bk_is_path(path))
            books_goto(path);
        else if (pc_is_path(path))
            podcasts_goto(path, id == PD_ACT_NOTES);
        else
            pod_toast(TR("Not found"));
    } else if (id == PD_ACT_RD_NP)
        rn_open(); /* the Home bar's card for a station (a stopped one too) */
    else if (id == PD_ACT_RD_MY || id == PD_ACT_RD_RECENT || id == PD_ACT_RD_SEARCH)
        radio_open_at(id == PD_ACT_RD_MY ? RD_AT_MY : id == PD_ACT_RD_RECENT ? RD_AT_RECENT : RD_AT_SEARCH);
    else if (id == PD_ACT_RD_INFO && sinfo_open() != 0)
        pod_toast(TR("Not found")); /* Radio Now Playing's sheet row */
}

static void cc2_stop(void);
static void pd_slide_stop(void);

/* The hook at on_wm_tsmove_fun's navigator_to("dialog/dropdown_dialog") (tools/pod.py PULLDOWN_DIALOG_SITE): the stock call, then, when the dialog was quit by one of our tiles (its result is
 * PD_QUIT, as for stock's tiles), the tile's action. Stock's own code that follows (the two flag tests) sees the result unchanged. */
int pd_open_dialog(const char *name) {
    int ret;
    unsigned act;
    ret = navigator_to(name);
    pd_hold_reset();
    cc2_stop(); /* (the dialog's destroy has run it; this one only makes sure) */
    act = pd_pending;
    pd_pending = 0;
    if (ret == PD_QUIT && act) pd_run(act - 1);
    return ret;
}

/* The Control Labels switch (Settings > Appearance): on by default; "0" hides every tile caption while keeping the discs in place. */
int pd_labels_setting(void) { return set_read(PDLABELS_FILE, '1') != '0'; }

int pd_labels_toggle(void) {
    int next = !pd_labels_setting();
    return home_write_atomic(PDLABELS_FILE, next ? "1\n" : "0\n") != 0 ? -1 : next;
}

static void pd_start(void *dlg) {
    void *img[PD_N], *lab[PD_N];
    int px[PD_N], py[PD_N], dx[PD_N], dy[PD_N];
    unsigned char ord[PD_N];
    unsigned i, n, shown = 0;
    int labels;
    for (i = 0; i < PD_N; i++) {
        img[i] = widget_lookup(dlg, PD_IMG[i], 1);
        lab[i] = widget_lookup(dlg, PD_LAB[i], 1);
        if (!img[i] || !lab[i]) return; /* not our asset: leave the stock tiles */
        px[i] = widget_get_prop_int(img[i], "x", 0);
        py[i] = widget_get_prop_int(img[i], "y", 0);
        dx[i] = widget_get_prop_int(lab[i], "x", 0) - px[i];
        dy[i] = widget_get_prop_int(lab[i], "y", 0) - py[i];
    }
    labels = pd_labels_setting();
    n = pd_load(ord);
    for (i = 0; i < n; i++) shown |= 1u << ord[i];
    pd_bind_hold(dlg, img, shown);
    for (i = 0; i < n; i++)
        if (ord[i] != i) break;
    if (n == PD_STOCK && i == n) { /* the stock layout (ours stay as the asset has them: hidden) */
        if (!labels)
            for (i = 0; i < PD_STOCK; i++) m1_show(lab[i], 0);
        return;
    }
    for (i = 0; i < n; i++) { /* shown tile ord[i] takes tile i's place (the places were read above) */
        unsigned id = ord[i];
        widget_move(img[id], px[i], py[i]);
        if (labels) widget_move(lab[id], px[i] + dx[id], py[i] + dy[id]);
        if (id >= PD_STOCK) { /* ours: bound to a tap, then shown (one that cannot be bound stays hidden) */
            pd_tile[id - PD_STOCK].dlg = dlg;
            pd_tile[id - PD_STOCK].img = img[id];
            pd_tile[id - PD_STOCK].id = id;
            if (widget_on(img[id], EVT_CLICK, pd_on_tile, &pd_tile[id - PD_STOCK])) {
                if (pd_is_switch(id))
                    pd_switch_art(id, img[id]);
                else if (id == PD_SLEEP)
                    pd_sleep_art(img[id]);
                m1_show(img[id], 1);
                if (labels) m1_show(lab[id], 1);
            } else
                shown &= ~(1u << id);
        }
    }
    for (i = 0; i < PD_N; i++) {
        if (!(shown >> i & 1)) {
            m1_show(img[i], 0);
            m1_show(lab[i], 0);
        } else if (!labels)
            m1_show(lab[i], 0);
    }
}

/* ---- the Playback / System Settings tiles
 *
 * Stock marks "inside settings" in two words: syssetinto_flag (SYSSET_FLAG) and playsetinto_flag (PLAYSET_FLAG), which the page inits set to 1 and the Back handlers clear. The top-right Now Playing button
 * opens the player over the page without clearing either (the page stays in the window stack behind it), and the tile visitor of the stock pull-down init disables a tile and skips its click bind while its flag
 * is positive, so both tiles stay dead until Home clears the flags. Before the stock init runs the flags are made to say whether the page is where the user can be: a page that is gone, or has the player (Now
 * Playing, Radio Now Playing) or Home above it, is not inside settings (flag 0: the tile is enabled and bound as stock does, and its handler does what it always does, store 2 and quit the dialog); a page that is
 * in the stack with none of those above it is (flag 1; so a page the user returns to has its tile disabled again, as stock). Windows between the page and the front are its sub-pages. */
static const struct {
    const char *window, *nav; /* the page's window name (the asset's root) and the name navigator_to opens it by */
    const char *own; /* the window of our own page that replaces it (its sub-pages are windows above it), or none */
    volatile int *flag;
} PD_SET[2] = {{"sysset_page", "systemset/sysset_page", (const char *)0, (volatile int *)SYSSET_FLAG},
               {"playset_page", "playset/playset_page", "m1plus_playset_page", (volatile int *)PLAYSET_FLAG}};

static const char *pd_name(void *w) { return w ? *(const char **)((char *)w + WIDGET_NAME) : (const char *)0; }

/* A window that leaves settings: the player, Radio Now Playing, Home. */
static int pd_leaves(const char *nm) {
    return !strcmp(nm, "playing_page") || !strcmp(nm, "m1plus_radionp") || !strcmp(nm, "home_page");
}

/* The named window in the manager and whether a window that leaves settings is above it; 0 when there is none. */
static void *pd_window(void *wm, const char *name, int *above) {
    unsigned n = widget_count_children(wm);
    *above = 0;
    while (n--) {
        void *w = widget_get_child(wm, n);
        const char *nm = pd_name(w);
        if (!nm) continue;
        if (!strcmp(nm, name)) return w;
        if (pd_leaves(nm)) *above = 1;
    }
    return (void *)0;
}

/* Our page's sub-pages left in the stack (the windows right above it, up to the first that leaves settings: a picker or a slider page the top-right Now Playing button covered) are closed before the page is
 * restacked. A page of ours keeps one window (pod_fg, the slider pages' widgets): a sub-page left under the restacked page and opened again from it would be a second instance, and closing that one would
 * leave the first with no refresh and with the pointers of a destroyed window. A window that hangs from one a tile or the status bar opened (pd_rooted: the Volume page and the Equalizer, Gain and Volume & Sound
 * pages reached by those routes, with what they opened) is not closed: the user came to it by another route, and Back must return to it. */
static void pd_close_subpages(const char *name) {
    void *wm = window_manager(), *sub[8], *page;
    unsigned n, i, k = 0;
    if (!wm) return;
    n = widget_count_children(wm);
    for (i = 0; i < n && (!pd_name(widget_get_child(wm, i)) || strcmp(pd_name(widget_get_child(wm, i)), name)); i++) {
    }
    page = i < n ? widget_get_child(wm, i) : (void *)0;
    for (i++; i < n && k < 8; i++) {
        void *w = widget_get_child(wm, i);
        const char *nm = pd_name(w);
        if (nm && pd_leaves(nm)) break;
        if (w && !pd_rooted(w, page) && widget_is_window_opened(w)) sub[k++] = w;
    }
    while (k--) window_close(sub[k]); /* (the topmost first) */
}

static void pd_reconcile(void) {
    void *wm = window_manager();
    unsigned i;
    if (!wm) return;
    for (i = 0; i < 2; i++) {
        int above, above_own = 1;
        void *win = pd_window(wm, PD_SET[i].window, &above);
        void *own = PD_SET[i].own ? pd_window(wm, PD_SET[i].own, &above_own) : (void *)0;
        *PD_SET[i].flag = (win && widget_is_window_opened(win) && !above) ||
                          (own && widget_is_window_opened(own) && !above_own); /* (a page that is closing is gone) */
    }
}

/* The hook at the two navigator_to calls of on_wm_tsmove_fun that open the page a tile chose (flag 2): the page when it is still in the stack is brought to the front the way stock brings the player back
 * (window_manager_switch_to, nothing closed, Back returns to where the user came from); otherwise (or if that fails) stock's call. The page's own init sets the flag when it opens; a restacked page runs no
 * init, so the flag is set here; a page that will not open leaves no flag of 2. Any other name is the stock call. A tap only. The Playback name opens our Playback Settings page (m1plus_playset_page: restacked
 * when in the stack, else pod_open_playset), the stock list only when ours will not open; either window keeps the Playback flag (pd_reconcile). */
int pd_open_settings(const char *name) {
    unsigned i;
    int ret;
    for (i = 0; i < 2 && strcmp(name, PD_SET[i].nav); i++) {
    }
    if (i < 2 && PD_SET[i].own) pd_close_subpages(PD_SET[i].own);
    if (i < 2 && PD_SET[i].own && (m1_restack_window(PD_SET[i].own) || pod_open_playset() == 0)) {
        pd_note_opener(pd_by_name(PD_SET[i].own), (void *)0); /* a tile's page is rooted, as pd_open_own's */
        *PD_SET[i].flag = 1; /* our page replaces stock's list: restacked, else opened as the Settings row opens it */
        return RET_OK;
    }
    if (i < 2 && m1_restack_window(PD_SET[i].window)) {
        *PD_SET[i].flag = 1;
        return RET_OK;
    }
    ret = navigator_to(name);
    if (i < 2 && ret != RET_OK) *PD_SET[i].flag = 0;
    return ret;
}

/* The dialog's EVT_WINDOW_CLOSE, after stock's own handler (0x4750ec: dropdown_menu_state = 0, the 500 ms refresh timer removed, nothing else): the 10 ms slide timer (callback 0x47535c, its id in the property
 * "timer_idex", 0xffffffff for none) is cancelled as stock's pointer-down handler 0x47514c cancels it. Widget destruction is deferred to an idle, so a tick after the close would store state 3 (0x4754c4) with no
 * dialog and the swipe would be refused for ever. Writes no global; the state is stock's handler's. */
static int pd_on_close(void *dlg, void *evt) {
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    (void)evt;
    pd_hold_reset();
    if (!dlg || widget_get_prop(dlg, "timer_idex", v) != RET_OK) return RET_OK;
    if (value_uint32(v) == 0xffffffffu || !timer_count()) return RET_OK;
    widget_remove_timer(dlg, value_uint32(v));
    value_set_uint32(v, 0xffffffffu);
    widget_set_prop(dlg, "timer_idex", v);
    return RET_OK;
}

/* The bar copy's clock follows 24-Hour Time as the real bar does: stock's switch (change_time24h_12h) re-formats only the real bar's bar_dclock, so the copy kept the asset's
 * "hh:mm" (24 h) whatever the setting. With the switch off it takes the real bar's 12 h format. The dialog is built each time it opens, so a change shows the next time. */
static void pd_clock(void *dlg) {
    void *w = *(volatile unsigned char *)TIME_24H ? 0 : widget_lookup(dlg, PD_CLOCK_NAME, 1);
    if (w) digit_clock_set_format(w, PD_CLOCK_12H);
}

/* ---- page 2's Now Playing card
 *
 * The card pod_cc2_top (a button, so a tap on it is an EVT_CLICK) holds, in the asset, the labels pod_cc2_title / _artist / _elapsed / _remain, the favourite disc pod_cc2_fav and the transport
 * pod_cc2_prev / _play / _next (baked images, the play slot shows drop_cc_play or drop_cc_pause); the cover and the progress bar are painted in the card's EVT_AFTER_PAINT, cover first (the Home bar's
 * mb_art_*: one 96 px bitmap with rounded corners, made once per track, never in paint). One 500 ms timer runs only while page 2 shows (pd_page_set) and ends with the dialog (EVT_DESTROY; pd_open_dialog
 * makes sure). cc2_work is the only code that changes anything and looks at the player:
 *   nothing queued       "Not Playing", no artist, a grey cover, the three transport buttons and the star greyed and insensitive, the bar empty, no times
 *   a local track        title (else the file name) and artist; the cover (mb_art_cover on the track key); the star (checkFavExist, on a track change and after a tap); play / pause by mclGetPlayStatus;
 *                        the bar and the times from get_playtimeandlength. A server track (sba_rec_track) has no star here: stock's star would write its stream record, whose address carries the login token,
 *                        into the local favourites (Now Playing sends it to the server; this card leaves it)
 *   a radio station      (mb_radio_active) the station and its line as the Home bar shows them, a grey cover, play / stop by the bar's rule (mb_radio_play_click), no skip, no star, no bar
 * The buttons are the stock calls of the Home bar: playpause_quick_click, next_quick_click / prev_quick_click with a synthesized click event (stock ignores a click within a second of the last), the star's
 * checkFavExist / deleteMusicFromFav / addMyFav (what Now Playing's star does for a local track). A tap on the card elsewhere quits the dialog (as a tile does) and pd_run opens Now Playing. */
#define CC2_COVER 96
#define CC2_COVER_R 8
#define CC2_COVER_X 12 /* in the card: the dialog's (22, 56) less the card's (10, 44) */
#define CC2_COVER_Y 12
#define CC2_BAR_X 120 /* the bar (130, 134) .. (297, 138) of the dialog */
#define CC2_BAR_Y 90
#define CC2_BAR_W 168
#define CC2_BAR_H 5
#define CC2_TICK_MS 500
#define CC2_GREY 0xff3c3a3au /* #3A3A3C: the placeholder cover (the favourite disc's grey) */
#define CC2_TRACK 0xff4a4848u /* #48484A */
#define CC2_FILL 0xfff2f2f2u /* #F2F2F2 */

static struct {
    void *dlg, *card, *title, *artist, *el, *rem, *fav, *prev, *play, *next;
    void *pm, *up, *goart, *goalb, *eq, *eqdisc, *eqsub, *sl, *sldisc,
        *slsub; /* the lower cards: the four discs, the Equalizer and the Sleep cards */
    void *eqtitle; /* the Equalizer card's title: Speed for an episode or a book part */
    unsigned eqhash, slhash, eqthash; /* the sub lines and the Equalizer title shown (hashes), 0 none yet */
    int kind; /* what plays (mode 1): 0 music, 1 a podcast episode, 2 an audiobook part */
    int lsig, ltick; /* the discs' look (-1 none yet); the ticks since the Equalizer's name was read */
    unsigned timer;
    mb_art_t art;
    unsigned key; /* the track key the cover and the star were made for, 0 none */
    unsigned thash, ahash; /* the title and artist shown (hashes), 0 none yet */
    int mode; /* -1 nothing shown yet, 0 not playing, 1 a local track, 2 a radio station */
    int sig; /* the buttons' look: mode, playing, favourite, server (-1 none yet) */
    int favd; /* the star: the playing track is a favourite */
    int pos, len; /* the seconds shown; len 0: no bar, no times */
    void *livel, *liver, *livetx; /* a station's LIVE divider (three widgets) */
    unsigned rser,
        rkey; /* the card's title shown (hash); the favourites serial and the station the Saved state was read for */
    int live, saved, rpend; /* LIVE shown; the station is in My Stations; its logo is not cached yet */
} cc2 __attribute__((section(".scratch")));

static const unsigned char cc2_in8[8] = {
    5, 3, 2, 1, 1, 0, 0, 0}; /* the cover's corner: the columns a row starts in from the left (radius 8) */
static const unsigned char cc2_in2[2] = {1, 0}; /* the bar's (radius 2) */

/* A rectangle with round corners: row i of the top r rows (and the same from the bottom) starts in[i] px in (a small round fill renders square on the device, so it is drawn by rows). */
static void cc2_rrect(void *canvas, unsigned color, int x, int y, int w, int h, const unsigned char *in, int r) {
    int i, d;
    canvas_set_fill_color(canvas, color);
    for (i = 0; i < h; i++) {
        d = i < r ? in[i] : h - 1 - i < r ? in[h - 1 - i] : 0;
        canvas_fill_rect(canvas, x + d, y + i, w - 2 * d, 1);
    }
}

static int cc2_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int fw;
    (void)ctx;
    if (!canvas || !cc2.dlg) return RET_OK;
    if ((cc2.mode == 1 || cc2.mode == 2) && cc2.art.bmp)
        mb_art_paint_at(&cc2.art, canvas, CC2_COVER_X, CC2_COVER_Y);
    else
        cc2_rrect(canvas, CC2_GREY, CC2_COVER_X, CC2_COVER_Y, CC2_COVER, CC2_COVER, cc2_in8, CC2_COVER_R);
    if (cc2.mode == 2) return RET_OK; /* a station has LIVE in the bar's place */
    cc2_rrect(canvas, CC2_TRACK, CC2_BAR_X, CC2_BAR_Y, CC2_BAR_W, CC2_BAR_H, cc2_in2, 2);
    fw = cc2.len > 0 ? CC2_BAR_W * cc2.pos / cc2.len : 0;
    if (fw >=
        2 * CC2_BAR_H) /* the fill takes the accent, as Now Playing's progress fill does (the track stays neutral) */
        cc2_rrect(canvas, pal_accent() ? pal_fill() : CC2_FILL, CC2_BAR_X, CC2_BAR_Y, fw, CC2_BAR_H, cc2_in2, 2);
    return RET_OK;
}

static int cc2_server(void *rec) { return rec && sba_rec_track(*(int *)((char *)rec + REC_ID))[0] != 0; }

/* A button's picture and whether it takes touches. */
static void cc2_img(void *w, const char *image, int on) {
    image_base_set_image(w, image);
    widget_set_sensitive(w, on);
    widget_invalidate_force(w, (void *)0);
}

/* The transport and the star for what plays. */
static void cc2_look(int playing, int server) {
    int sig = cc2.mode | playing << 2 | cc2.favd << 3 | server << 4 | cc2.kind << 5, skip = cc2.mode == 1;
    if (sig == cc2.sig) return;
    cc2.sig = sig;
    m1_show(cc2.prev, cc2.mode != 2); /* a station has no skip: the play button alone, centred */
    m1_show(cc2.next, cc2.mode != 2);
    cc2_img(cc2.prev, cc2.kind ? "drop_cc_back15" : skip ? "drop_cc_prev" : "drop_cc_prev_off", skip);
    cc2_img(cc2.next, cc2.kind ? "drop_cc_fwd30" : skip ? "drop_cc_next" : "drop_cc_next_off", skip);
    if (cc2.mode == 0)
        cc2_img(cc2.play, "drop_cc_play_off", 0);
    else
        cc2_img(cc2.play, playing ? (cc2.mode == 2 ? "drop_cc_stop" : "drop_cc_pause") : "drop_cc_play", 1);
    m1_show(
        cc2.fav,
        cc2.mode != 2 &&
            !(cc2.mode == 1 &&
              (server ||
               cc2.kind))); /* a station, a server track, an episode and a part have no star here: it is not shown (hidden is also insensitive) */
    if (cc2.mode == 1 && !server && !cc2.kind)
        cc2_img(cc2.fav, cc2.favd ? "drop_cc_fav_on" : "drop_cc_fav", 1);
    else
        cc2_img(cc2.fav, "drop_cc_fav_off", 0);
}

static void cc2_text(void *w, unsigned *hash, const char *s) {
    unsigned h = cc_fnv(FNV_SEED, s) | 1;
    if (h == *hash) return;
    *hash = h;
    widget_set_text_utf8(w, s);
}

/* An episode's or a part's speed (playspeed_mode 0..3, the one Now Playing's speed button shows); 0 for anything else. */
static const char *const cc2_speed_name[PC_SPEEDS] = {"1\xc3\x97", "1.25\xc3\x97", "1.5\xc3\x97", "2\xc3\x97"};

static int cc2_speed(void) {
    int mode = *(volatile int *)PLAYSPEED_MODE;
    return cc2.kind && mode > 0 && mode < PC_SPEEDS ? mode : 0;
}

/* The lower half's pictures for an episode or a part (sig: the look cc2_lower computed): Podcasts (or Audiobooks), Up Next, its notes (info), the next episode (part); the Equalizer card is
 * Speed, lit when it is not 1x. The Sleep card is the music's. The texts are cc2_lower's. */
static void cc2_spoken_lower(int sig, int sl) {
    if (sig == cc2.lsig) return;
    cc2.lsig = sig;
    cc2_text(cc2.eqtitle, &cc2.eqthash, TR("Speed"));
    cc2_img(cc2.pm, cc2.kind == 1 ? "drop_cc_podhome" : "drop_cc_bkhome", 1);
    cc2_img(
        cc2.up, "drop_cc_queue",
        1); /* the queue as Now Playing shows it for an episode or a part: a plain list (np_playlist), not music's list-music */
    cc2_img(cc2.goart, "drop_cc_notes", 1);
    cc2_img(cc2.goalb, "drop_cc_nextep", 1);
    cc2_img(cc2.eqdisc, cc2_speed() ? "drop_cc_speed_on" : "drop_cc_speed",
            0); /* the card is the button: its disc takes no touches */
    cc2_img(cc2.sldisc, sl ? "drop_cc_sleep_on" : "drop_cc_sleep", 0);
}

/* ---- a station on page 2 (docs/modules/pulldown.md "Radio"): the four discs are My Stations, Recently Played, Station Info and Search, the Equalizer card becomes the Station card (Saved: in My Stations),
 * LIVE stands in the bar's place while it connects or plays; the cover is the station's logo (mb_radio_art, the Home bar's). */
static void cc2_radio_discs(void) {
    cc2_img(cc2.pm, "drop_cc_rd_my", 1);
    cc2_img(cc2.up, "drop_cc_rd_recent", 1);
    cc2_img(cc2.goart, "drop_cc_rd_info", 1);
    cc2_img(cc2.goalb, "drop_cc_rd_search", 1);
    cc2_img(cc2.eqdisc, cc2.saved ? "drop_cc_station_on" : "drop_cc_station", 0);
}

/* The logo: made when the station changes, and again once a logo that was not cached yet is (the worker is started as the Home bar does). */
static void cc2_radio_cover(const rd_list_t *l, int at) {
    char fav[RD_FAV_MAX + 1], path[48];
    unsigned key = cc_fnv(FNV_SEED, at < l->n ? rd_url(l, at) : "") | 1;
    int redo = key != cc2.key;
    if (!redo && cc2.rpend && at < l->n) {
        rd_favicon(rd_info(l, at), fav, sizeof fav);
        if (fav[0]) {
            redo = rd_logo_file(rd_logo_hash(fav), path, sizeof path) != 0;
            if (!redo && !rd_logo_running()) rd_logo_start(fav);
        }
    }
    if (!redo) return;
    cc2.key = key;
    if (mb_radio_art(&cc2.art, cc2.dlg, &cc2.rpend)) widget_invalidate_force(cc2.card, (void *)0);
}

/* Saved: read from the card file when the station or the favourites change (rd_serial), not at every tick. */
static void cc2_radio_saved(const rd_list_t *l, int at) {
    unsigned key = cc_fnv(FNV_SEED, at < l->n ? rd_url(l, at) : "") | 1, ser = rd_serial();
    if (key == cc2.rkey && ser == cc2.rser) return;
    cc2.rkey = key, cc2.rser = ser;
    cc2.saved = at < l->n && rd_fav_has(rd_url(l, at));
}

/* LIVE (the two capsules and the word) shows while the station connects or plays, as Radio Now Playing's divider. */
static void cc2_live(int on) {
    if (on == cc2.live) return;
    cc2.live = on;
    m1_show(cc2.livel, on);
    m1_show(cc2.liver, on);
    m1_show(cc2.livetx, on);
    widget_invalidate_force(cc2.card, (void *)0);
}

/* The Station card: Add to / Remove from My Stations as Radio Now Playing's sheet does, the same toasts; the pull-down stays. */
static void cc2_radio_toggle(void) {
    const rd_list_t *l = rd_list();
    int r;
    if (!l->n || rd_at() >= l->n) return;
    r = rd_fav_toggle(l, rd_at());
    pod_toast(TR(r < 0 ? "Could not save My Stations" : r ? "Added to My Stations" : "Removed from My Stations"));
    cc2.rkey = 0; /* read again */
}

/* The lower cards for what plays and the settings: the four discs (live for a queued track, grey and insensitive otherwise; the Play Mode disc shows the mode, lit unless it is List play) and the Equalizer
 * and Sleep cards (always live: lit while the switch is on / a timer runs, the sub line the preset or Off / the minutes left). The images are set when the look changes, the texts when they differ. */
static void cc2_lower(void) {
    static const char *const pm_img[4] = {"drop_cc_pm_order", "drop_cc_pm_one", "drop_cc_pm_shuffle", "drop_cc_pm_all"};
    char buf[64], line[40];
    int on = cc2.mode == 1, pm = pod_play_mode() & 3, eq = *(volatile unsigned char *)EQ_FLAG != 0, rd = cc2.mode == 2;
    int sl = *(volatile unsigned char *)SLEEP_FLAG != 0 && *(volatile int *)SLEEP_TIME > 0, spd = cc2_speed(),
        sig = on | pm << 1 | eq << 3 | sl << 4 | rd << 5 | (rd && cc2.saved) << 6 | cc2.kind << 7 | spd << 9;
    if (cc2.kind)
        cc2_spoken_lower(sig, sl);
    else if (sig != cc2.lsig) {
        cc2.lsig = sig;
        cc2_text(cc2.eqtitle, &cc2.eqthash, rd ? TR("Station") : TR("Equalizer"));
        if (rd)
            cc2_radio_discs();
        else {
            cc2_img(cc2.pm, on ? pm_img[pm] : "drop_cc_pm_off", on);
            cc2_img(cc2.up, on ? "drop_cc_upnext" : "drop_cc_upnext_off", on);
            cc2_img(cc2.goart, on ? "drop_cc_artist" : "drop_cc_artist_off", on);
            cc2_img(cc2.goalb, on ? "drop_cc_album" : "drop_cc_album_off", on);
            cc2_img(cc2.eqdisc, eq ? "drop_cc_eq_on" : "drop_cc_eq", 0);
        }
        cc2_img(cc2.sldisc, sl ? "drop_cc_sleep_on" : "drop_cc_sleep", 0);
        cc2.ltick = 0;
    }
    if (cc2.kind)
        cc2_text(cc2.eqsub, &cc2.eqhash, cc2_speed_name[spd]);
    else if (rd)
        cc2_text(cc2.eqsub, &cc2.eqhash, TR(cc2.saved ? "Saved" : "Not Saved"));
    else if (!eq)
        cc2_text(cc2.eqsub, &cc2.eqhash, TR("Off"));
    else if (cc2.ltick++ % 4 == 0 || !cc2.eqhash) { /* the state file is read now and then, not at every tick */
        cc2_text(cc2.eqsub, &cc2.eqhash, peq_playing_name(buf, sizeof buf) ? TR(buf) : TR("Off"));
    }
    if (sl)
        pc_left_text(line, sizeof line, (unsigned)*(volatile int *)SLEEP_TIME), cc2_text(cc2.slsub, &cc2.slhash, line);
    else
        cc2_text(cc2.slsub, &cc2.slhash, TR("Off"));
}

/* The bar and the times: pos / len seconds, len 0 for none. */
static void cc2_time(int pos, int len) {
    char a[16], b[16];
    if (len > 0 && pos > len) pos = len;
    if (pos < 0) pos = 0;
    if (len <= 0) pos = len = 0;
    if (pos == cc2.pos && len == cc2.len) return;
    cc2.pos = pos, cc2.len = len;
    a[0] = b[0] = 0;
    if (len > 0) {
        snprintf(a, sizeof a, "%d:%02d", pos / 60, pos % 60);
        snprintf(b, sizeof b, "-%d:%02d", (len - pos) / 60, (len - pos) % 60);
    }
    widget_set_text_utf8(cc2.el, a);
    widget_set_text_utf8(cc2.rem, b);
    widget_invalidate_force(cc2.card, (void *)0);
}

static void cc2_work(void) {
    void *t = (void *)0;
    char line[200];
    int mode, playing, server = 0, pos = 0, len = 0, kind = 0;
    unsigned key = 0;
    if (!cc2.dlg) return;
    if (mb_radio_active())
        mode = 2;
    else
        mode = (t = cc_playing()) ? 1 : 0;
    if (mode == 1) { /* an episode or a book part: Now Playing's spoken-audio controls (docs/modules/nowplaying.md) */
        const char *path = cc_str(t, REC_PATH);
        kind = pc_is_path(path) ? 1 : bk_is_path(path) ? 2 : 0;
    }
    if (kind != cc2.kind) cc2.lsig = -1;
    if (mode != cc2.mode || kind != cc2.kind) {
        cc2.mode = mode;
        cc2.kind = kind;
        cc2.sig = -1;
        cc2.key = cc2.rkey = cc2.rpend = 0;
        widget_invalidate_force(cc2.card, (void *)0); /* the cover place: the picture or the grey */
    }
    if (mode == 1) {
        const char *title = cc_str(t, REC_TITLE), *sub = cc_str(t, REC_ARTIST);
        if (!*title) title = cc_str(t, REC_NAME);
        if (kind == 2 && *sub) { /* a book: its title, then the part's name */
            const char *book = sub;
            sub = title;
            title = book;
        }
        cc2_text(cc2.title, &cc2.thash, title);
        cc2_text(cc2.artist, &cc2.ahash, sub);
        key = mb_track_key(t);
        server = cc2_server(t);
        if (key != cc2.key) {
            cc2.key = key;
            cc2.favd = !server && checkFavExist(t) != 0;
            if (mb_art_cover(&cc2.art, cc2.dlg, t, 1)) widget_invalidate_force(cc2.card, (void *)0);
        } else if (cc2.art.settle > 0 && mb_art_settle(&cc2.art, cc2.dlg, t))
            widget_invalidate_force(cc2.card, (void *)0);
        playing = mclGetPlayStatus() == MB_PLAYING;
        if (get_playtimeandlength(&pos, &len) != 1) len = 0;
    } else if (mode == 2) {
        const rd_list_t *l = rd_list();
        int at = rd_at();
        const char *name = l->n && at < l->n ? rd_name(l, at) : "";
        mb_radio_line(line, sizeof line);
        cc2_text(cc2.title, &cc2.thash, rd_meta_head(name[0] ? name : TR("Radio")));
        cc2_text(cc2.artist, &cc2.ahash, line);
        cc2.favd = 0;
        playing = mb_radio_playing();
        cc2_radio_cover(l, at);
        cc2_radio_saved(l, at);
    } else {
        cc2_text(cc2.title, &cc2.thash, TR("Not Playing"));
        cc2_text(cc2.artist, &cc2.ahash, "");
        cc2.favd = 0;
        playing = 0;
    }
    cc2_live(mode == 2 && rd_running() && rd_state() != RD_PAUSED);
    cc2_look(playing, server);
    cc2_lower();
    cc2_time(pos, len);
}

static int cc2_tick(const void *timer) {
    (void)timer;
    if (!cc2.dlg) return RET_OK;
    cc2_work();
    return RET_REPEAT;
}

/* Page 2 shows: the card at once, then every tick. A refused timer leaves the card as it was made. */
static void cc2_arm(void) {
    if (!cc2.dlg) return;
    cc2_work();
    if (!cc2.timer) cc2.timer = timer_add(cc2_tick, (void *)0, CC2_TICK_MS);
}

static void cc2_stop(void) {
    pd_slide_stop();
    if (!cc2.dlg) return;
    m1_timer_stop(&cc2.timer);
    mb_art_free(&cc2.art);
    memset(&cc2, 0, sizeof cc2);
}

static int cc2_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == cc2.dlg) cc2_stop(); /* an earlier dialog's end leaves the new one alone */
    return RET_OK;
}

static int cc2_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!cc2.dlg) return RET_OK;
    if (cc2.mode == 2)
        mb_radio_play_click();
    else if (cc2.mode == 1)
        playpause_quick_click();
    cc2_work();
    return RET_OK;
}

/* next_quick_click / prev_quick_click read the event's time: the click's own event is what the stock handlers pass (a synthesized one when there is none). */
static int cc2_skip(int next, void *e) {
    unsigned ev[4];
    if (!cc2.dlg || cc2.mode != 1) return RET_OK;
    if (cc2.kind) { /* an episode or a part: back 15 s, forward 30 s (Now Playing's buttons) */
        np_spoken_seek(next);
        cc2_work();
        return RET_OK;
    }
    if (!e) {
        memset(ev, 0, sizeof ev);
        ev[2] = time_now_ms();
        e = ev;
    }
    if (next)
        next_quick_click(e, 0);
    else
        prev_quick_click(e, 0);
    cc2_work();
    return RET_OK;
}

/* The next episode or part in the queue, as the next key does (stock's next_quick_click with a synthesized click). */
static void cc2_next_track(void) {
    unsigned ev[4];
    memset(ev, 0, sizeof ev);
    ev[2] = time_now_ms();
    next_quick_click(ev, 0);
    cc2_work();
}

static int cc2_on_next(void *ctx, void *e) {
    (void)ctx;
    return cc2_skip(1, e);
}

static int cc2_on_prev(void *ctx, void *e) {
    (void)ctx;
    return cc2_skip(0, e);
}

static int cc2_on_fav(void *ctx, void *e) {
    void *t = cc_playing();
    (void)ctx;
    (void)e;
    if (!cc2.dlg || cc2.mode != 1 || !t || cc2_server(t)) return RET_OK;
    if (checkFavExist(t))
        deleteMusicFromFav(t);
    else
        addMyFav(t);
    cc2.favd = checkFavExist(t) != 0;
    cc2_work();
    return RET_OK;
}

/* Quit the dialog with the action act (pd_open_dialog runs it once the dialog is gone); the dialog stays as it was when it will not quit. */
static void cc2_leave(unsigned act) {
    if (!cc2.dlg || pd_blocked()) return;
    pd_pending = act + 1;
    if (dialog_quit(cc2.dlg, PD_QUIT) != RET_OK) pd_pending = 0;
}

static int cc2_on_card(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    cc2_leave(cc2.mode == 2 ? PD_ACT_RD_NP : PD_ACT_NP);
    return RET_OK;
}

/* The lower cards' taps (ctx: the action). Play Mode stays on the pull-down: the next of Now Playing's four modes (List play, Repeat one, Shuffle, Repeat all; pod_set_mode is what the Play settings page does
 * and keeps the Shuffle flag, docs/modules/shuffle.md). The discs of the queued track and the two cards quit the dialog; pd_run opens the page. */
static int cc2_on_act(void *ctx, void *e) {
    unsigned act = (unsigned)(long)ctx;
    (void)e;
    if (!cc2.dlg) return RET_OK;
    if (cc2.kind &&
        act !=
            PD_SLEEP) { /* an episode or a part: the four discs are Podcasts / Audiobooks, Up Next, its notes and the next one; the Equalizer card is Speed */
        if (cc2.mode != 1) return RET_OK;
        if (act == PD_EQ) {
            np_speed_step();
            cc2.lsig = -1;
            cc2_work();
        } else if (act == PD_ACT_ALBUM)
            cc2_next_track();
        else
            cc2_leave(act == PD_ACT_MODE    ? (cc2.kind == 1 ? PD_ACT_PODS : PD_ACT_BOOKS)
                      : act == PD_ACT_QUEUE ? act
                                            : PD_ACT_NOTES);
        return RET_OK;
    }
    if (cc2.mode == 2 && act != PD_SLEEP) { /* a station: the same slots, other places */
        if (act == PD_EQ)
            cc2_radio_toggle(), cc2_work();
        else
            cc2_leave(act == PD_ACT_MODE     ? PD_ACT_RD_MY
                      : act == PD_ACT_QUEUE  ? PD_ACT_RD_RECENT
                      : act == PD_ACT_ARTIST ? PD_ACT_RD_INFO
                                             : PD_ACT_RD_SEARCH);
        return RET_OK;
    }
    if (act == PD_ACT_MODE) {
        if (cc2.mode != 1) return RET_OK;
        pod_set_mode((pod_play_mode() + 1) & 3);
        cc2.lsig = -1;
        cc2_work();
    } else if (act == PD_SLEEP || act == PD_EQ || cc2.mode == 1)
        cc2_leave(act);
    return RET_OK;
}

/* The card's lookups and handlers; 0 when anything is missing or refused (page 2 is then never shown). The timer starts when page 2 does. */
static int cc2_start(void *dlg) {
    memset(&cc2, 0, sizeof cc2);
    cc2.card = widget_lookup(dlg, "pod_cc2_top", 1);
    cc2.title = widget_lookup(dlg, "pod_cc2_title", 1);
    cc2.artist = widget_lookup(dlg, "pod_cc2_artist", 1);
    cc2.el = widget_lookup(dlg, "pod_cc2_elapsed", 1);
    cc2.rem = widget_lookup(dlg, "pod_cc2_remain", 1);
    cc2.fav = widget_lookup(dlg, "pod_cc2_fav", 1);
    cc2.prev = widget_lookup(dlg, "pod_cc2_prev", 1);
    cc2.play = widget_lookup(dlg, "pod_cc2_play", 1);
    cc2.next = widget_lookup(dlg, "pod_cc2_next", 1);
    cc2.pm = widget_lookup(dlg, "pod_cc2_playmode", 1);
    cc2.up = widget_lookup(dlg, "pod_cc2_upnext", 1);
    cc2.goart = widget_lookup(dlg, "pod_cc2_artistgo", 1);
    cc2.goalb = widget_lookup(dlg, "pod_cc2_albumgo", 1);
    cc2.eq = widget_lookup(dlg, "pod_cc2_right1", 1);
    cc2.eqdisc = widget_lookup(dlg, "pod_cc2_eqdisc", 1);
    cc2.eqtitle = widget_lookup(dlg, "pod_cc2_eqtitle", 1);
    cc2.eqsub = widget_lookup(dlg, "pod_cc2_eqsub", 1);
    cc2.sl = widget_lookup(dlg, "pod_cc2_right2", 1);
    cc2.sldisc = widget_lookup(dlg, "pod_cc2_sleepdisc", 1);
    cc2.slsub = widget_lookup(dlg, "pod_cc2_sleepsub", 1);
    cc2.livel = widget_lookup(dlg, "pod_cc2_live_l", 1);
    cc2.liver = widget_lookup(dlg, "pod_cc2_live_r", 1);
    cc2.livetx = widget_lookup(dlg, "pod_cc2_live", 1);
    if (cc2.pm && cc2.up && cc2.goart && cc2.goalb && cc2.eq && cc2.eqdisc && cc2.eqsub && cc2.sl && cc2.sldisc &&
        cc2.slsub && cc2.eqtitle && cc2.livel && cc2.liver && cc2.livetx && cc2.card && cc2.title && cc2.artist &&
        cc2.el && cc2.rem && cc2.fav && cc2.prev && cc2.play && cc2.next &&
        widget_on(dlg, EVT_DESTROY, cc2_on_destroy, dlg) &&
        widget_on(cc2.card, EVT_AFTER_PAINT, cc2_on_paint, (void *)0) &&
        widget_on(cc2.card, EVT_CLICK, cc2_on_card, (void *)0) &&
        widget_on(cc2.fav, EVT_CLICK, cc2_on_fav, (void *)0) &&
        widget_on(cc2.prev, EVT_CLICK, cc2_on_prev, (void *)0) &&
        widget_on(cc2.play, EVT_CLICK, cc2_on_play, (void *)0) &&
        widget_on(cc2.next, EVT_CLICK, cc2_on_next, (void *)0) &&
        widget_on(cc2.pm, EVT_CLICK, cc2_on_act, (void *)(long)PD_ACT_MODE) &&
        widget_on(cc2.up, EVT_CLICK, cc2_on_act, (void *)(long)PD_ACT_QUEUE) &&
        widget_on(cc2.goart, EVT_CLICK, cc2_on_act, (void *)(long)PD_ACT_ARTIST) &&
        widget_on(cc2.goalb, EVT_CLICK, cc2_on_act, (void *)(long)PD_ACT_ALBUM) &&
        widget_on(cc2.eq, EVT_CLICK, cc2_on_act, (void *)(long)PD_EQ) &&
        widget_on(cc2.sl, EVT_CLICK, cc2_on_act, (void *)(long)PD_SLEEP)) {
        mb_art_size(&cc2.art, CC2_COVER, CC2_COVER_R);
        cc2.dlg = dlg;
        cc2.mode = cc2.sig = cc2.lsig = -1;
        return 1;
    }
    memset(&cc2, 0, sizeof cc2); /* (a handler that was registered finds no dialog of ours any more) */
    return 0;
}

/* ---- the two pages
 *
 * The pull-down has two pages side by side; a left / right swipe slides between them (the pages follow the finger, then ease to the page a flick or the nearer half picks). Page 1 is the dialog as stock and the tiles' hook leave it (view_switchs: the tiles and their captions; view_backlight: the
 * brightness card); page 2 is the asset's container pod_cc2 (hidden and insensitive there) with its dots pod_cc2_dot0 / _dot1. The status bar copy and the grabber belong to both. A slide only moves
 * those three containers by one offset (page 2 PD_PAGE_W right of page 1) and hides the page entirely off the dialog (m1_show: hidden is also insensitive), so what the hook set inside view_switchs (the
 * tiles shown, their places, the Control Labels) comes back exactly as it was. The dialog is built
 * afresh at each open, on the page the last slide landed on (pd_last, memory only: page 1 after a power-on; the dots show the page).
 *
 * The gesture is read on the dialog's "before children" pointer events (EVT_POINTER_*_BEFORE, dispatched ahead of the children and of the dialog's own listeners; RET_STOP ends the dispatch). A press
 * above PD_SWIPE_YMAX is watched: once it moved PD_SWIPE_PX horizontally and more than vertically it is a page swipe, and from then on its moves and its release are swallowed, so the tile or the slider
 * under the finger never gets them (no click, no hold) and stock's own handlers never see them. A vertical-dominant press is left to stock whole. Stock's
 * handlers (dialog_dropdown_dialog_init binds 0xff: 0x47514c, 0x101: 0x4755e8, 0x103: 0x4752f0): the down only cancels the 10 ms slide timer; the move drags the dialog (state 1, 2) only for a press that
 * began at y >= 0x118 (280) and moved up, and the up starts the slide timer only in states 1 and 2: a press above PD_SWIPE_YMAX = 280 never gets stock into them, so swallowing its moves and its release leaves
 * stock with nothing to settle. A press at or below 280 (the brightness card's lower part, the grabber, the dots) is stock's drag-to-close zone and is not watched. The Wi-Fi / Bluetooth long press timer is
 * stopped when the swipe is recognised (the tile does not see the move that decided it). Fails soft: any lookup or bind that fails leaves the dialog as it was (the dots stay hidden, page 2 never shows). */
#define PD_SWIPE_PX 20 /* the horizontal travel that makes a page swipe */
#define PD_SWIPE_YMAX 280 /* a press from here down is stock's drag-to-close zone (0x118, stock's move handler) */
#define PD_PAGE_W 320 /* a page's travel: the screen's width (page 2 sits this far right of page 1) */
#define PD_SLIDE_MS \
    300 /* a whole page's slide after the release; a shorter way takes its share, at least PD_SLIDE_MIN_MS */
#define PD_SLIDE_MIN_MS 120
#define PD_FLICK 300 /* px/s: a release this fast turns the page its way, whatever the travel */
#define PD_FLICK_STALE_MS 100 /* a finger that stood this long before the release has no speed */
static struct {
    void *pg[3], *dot[2]; /* view_switchs and view_backlight (page 1), pod_cc2 (page 2); the dots */
    int px[3], py[3]; /* the three containers' places in the asset */
    int page; /* 0 = tiles, 1 = page 2: the page shown, or the one a slide goes to */
    int mode; /* 0 not watched, 1 undecided, 2 page swipe (swallowed), 3 vertical (stock's) */
    int x0, y0, x; /* the press and the latest finger x */
    int off, off0,
        vis; /* page 1's offset (0 page 1 in place, -PD_PAGE_W page 2 in place), the offset at the press; the pages shown (bit 0 page 1, bit 1 page 2) */
    int vx, lx; /* the finger's speed (px/s) and its last x */
    unsigned lt; /* that move's time (time_now_ms) */
    int from, to; /* the slide's offsets */
    unsigned t0, dur, anim; /* its start, length (ms), frame timer (0 none) */
} pd_pg __attribute__((section(".scratch")));
/* The page the last slide landed on (0 page 1, 1 page 2): the next open starts there. Memory only, so a power-on starts on page 1. */
static int pd_last __attribute__((section(".scratch")));

/* Both pages at page 1's offset `off` (page 2 PD_PAGE_W to its right); a page entirely off the dialog is hidden (m1_show: and insensitive). */
static void pd_slide_place(int off) {
    int vis = (off > -PD_PAGE_W ? 1 : 0) | (off < 0 ? 2 : 0);
    unsigned i;
    for (i = 0; i < 3; i++) widget_move(pd_pg.pg[i], pd_pg.px[i] + off + (i == 2 ? PD_PAGE_W : 0), pd_pg.py[i]);
    if (vis != pd_pg.vis) {
        m1_show(pd_pg.pg[0], vis & 1);
        m1_show(pd_pg.pg[1], vis & 1);
        m1_show(pd_pg.pg[2], (vis & 2) != 0);
        pd_pg.vis = vis;
    }
    pd_pg.off = off;
}

static void pd_dots(int page) {
    unsigned i;
    for (i = 0; i < 2; i++) {
        image_base_set_image(pd_pg.dot[i], (int)i == page ? "drop_dot_on" : "drop_dot_off");
        widget_invalidate_force(pd_pg.dot[i], (void *)0);
    }
}

/* The slide has landed on `page`: the pages in place, the other one hidden, the dots, page 2's timer. */
static void pd_page_set(int page) {
    m1_timer_stop(&pd_pg.anim);
    pd_slide_place(page ? -PD_PAGE_W : 0);
    pd_dots(page);
    pd_pg.page = pd_last = page;
    if (page)
        cc2_arm();
    else
        m1_timer_stop(&cc2.timer); /* the card keeps its picture; the timer runs on page 2 only */
}

/* Ease-out cubic: the share (of 1024) of the way done after el of dur ms. */
static int pd_ease(unsigned el, unsigned dur) {
    int r = el >= dur ? 0 : (int)((dur - el) * 1024 / dur);
    return 1024 - r * r / 1024 * r / 1024;
}

static int pd_slide_frame(const void *timer) {
    unsigned el;
    (void)timer;
    if (!pd_pg.anim || !cc2.dlg) return RET_OK;
    el = time_now_ms() - pd_pg.t0;
    if (el >= pd_pg.dur) {
        pd_pg.anim = 0; /* RET_OK ends this timer */
        pd_page_set(pd_pg.page);
        return RET_OK;
    }
    pd_slide_place(pd_pg.from + (pd_pg.to - pd_pg.from) * pd_ease(el, pd_pg.dur) / 1024);
    return RET_REPEAT;
}

/* The finger left (or the gesture was aborted, vx 0): a flick turns the page its way, else the nearer page wins. The dots show the page at once; the pages slide there, or land at once when no frame
 * timer is had or they are there. */
static void pd_slide_release(int vx) {
    int page = vx < -PD_FLICK  ? 1
               : vx > PD_FLICK ? 0
                               : pd_pg.off < -PD_PAGE_W / 2,
        to = page ? -PD_PAGE_W : 0, d = to - pd_pg.off;
    unsigned dur;
    if (d < 0) d = -d;
    dur = (unsigned)(PD_SLIDE_MS * d / PD_PAGE_W);
    if (dur < PD_SLIDE_MIN_MS) dur = PD_SLIDE_MIN_MS;
    pd_pg.page = page;
    pd_dots(page);
    m1_timer_stop(&pd_pg.anim);
    if (d && (pd_pg.anim = timer_add(pd_slide_frame, (void *)0, NP_FRAME_MS)) != 0) {
        pd_pg.from = pd_pg.off;
        pd_pg.to = to;
        pd_pg.t0 = time_now_ms();
        pd_pg.dur = dur;
        return;
    }
    pd_page_set(page);
}

/* The dialog is going (cc2_stop): no frame after it. */
static void pd_slide_stop(void) { m1_timer_stop(&pd_pg.anim); }

/* A move of a page swipe: the pages follow the finger, a third as far past either end; the speed is the mean of the last two moves'. */
static void pd_slide_drag(void) {
    unsigned t = time_now_ms(), dt = t - pd_pg.lt;
    int off = pd_pg.off0 + pd_pg.x - pd_pg.x0;
    if (dt) pd_pg.vx = (pd_pg.vx + (pd_pg.x - pd_pg.lx) * 1000 / (int)dt) / 2;
    pd_pg.lx = pd_pg.x;
    pd_pg.lt = t;
    if (off > 0)
        off /= 3;
    else if (off < -PD_PAGE_W)
        off = -PD_PAGE_W + (off + PD_PAGE_W) / 3;
    pd_slide_place(off);
}

static void pd_swipe_begin(void) {
    pd_pg.mode = 2;
    pd_pg.off0 = pd_pg.off;
    pd_pg.vx = 0;
    m1_timer_stop(&pd_hold.timer); /* the tile under the finger will not see this move */
    pd_hold.down = 0;
    if (!cc2.timer) cc2_arm(); /* page 2 comes into view: its card up to date */
}

static int pd_on_swipe(void *ctx, void *e) {
    int type = e ? *(int *)e : 0, dx, dy;
    (void)ctx;
    if (type == EVT_POINTER_DOWN_BEFORE) {
        pd_pg.mode = 0;
        if (!e || *(int *)((char *)e + PE_Y) >= PD_SWIPE_YMAX) return RET_OK;
        pd_pg.x0 = pd_pg.x = *(int *)((char *)e + PE_X);
        pd_pg.y0 = *(int *)((char *)e + PE_Y);
        pd_pg.lx = pd_pg.x0; /* the speed's first sample */
        pd_pg.lt = time_now_ms();
        if (pd_pg
                .anim) { /* a press on sliding pages catches them where they are: it is a swipe from the start, and no tile under it sees it */
            m1_timer_stop(&pd_pg.anim);
            pd_swipe_begin();
            return RET_STOP;
        }
        pd_pg.mode = 1;
    } else if (type == EVT_POINTER_MOVE_BEFORE) {
        if (!e || pd_pg.mode == 0 || pd_pg.mode == 3) return RET_OK;
        pd_pg.x = *(int *)((char *)e + PE_X);
        if (pd_pg.mode == 1) {
            dx = pd_pg.x - pd_pg.x0;
            dy = *(int *)((char *)e + PE_Y) - pd_pg.y0;
            if (dx < 0) dx = -dx;
            if (dy < 0) dy = -dy;
            if (dx > PD_SWIPE_PX && dx > dy) {
                pd_swipe_begin();
            } else if (dy > PD_SWIPE_PX && dy >= dx) {
                pd_pg.mode = 3;
                return RET_OK;
            } else
                return RET_OK;
        }
        pd_slide_drag();
        return RET_STOP;
    } else if (type == EVT_POINTER_UP_BEFORE || type == EVT_POINTER_ABORT) {
        int swipe = pd_pg.mode == 2;
        pd_pg.mode = 0;
        if (!swipe) return RET_OK;
        pd_slide_release(type == EVT_POINTER_ABORT || time_now_ms() - pd_pg.lt > PD_FLICK_STALE_MS ? 0 : pd_pg.vx);
        return type == EVT_POINTER_ABORT ? RET_OK : RET_STOP;
    }
    return RET_OK;
}

/* The dialog's init, kill switch off: look up page 2 and bind the swipe, then show the dots and the remembered page (pd_last). */
static void pd_pages_start(void *dlg) {
    unsigned i;
    memset(&pd_pg, 0, sizeof pd_pg);
    pd_pg.pg[0] = widget_lookup(dlg, "view_switchs", 1);
    pd_pg.pg[1] = widget_lookup(dlg, "view_backlight", 1);
    pd_pg.pg[2] = widget_lookup(dlg, "pod_cc2", 1);
    pd_pg.dot[0] = widget_lookup(dlg, "pod_cc2_dot0", 1);
    pd_pg.dot[1] = widget_lookup(dlg, "pod_cc2_dot1", 1);
    if (!pd_pg.pg[0] || !pd_pg.pg[1] || !pd_pg.pg[2] || !pd_pg.dot[0] || !pd_pg.dot[1] || !cc2_start(dlg)) return;
    /* DOWN last: if an earlier listener cannot be bound, no gesture starts. */
    if (!widget_on(dlg, EVT_POINTER_MOVE_BEFORE, pd_on_swipe, (void *)0) ||
        !widget_on(dlg, EVT_POINTER_UP_BEFORE, pd_on_swipe, (void *)0) ||
        !widget_on(dlg, EVT_POINTER_ABORT, pd_on_swipe, (void *)0) ||
        !widget_on(dlg, EVT_POINTER_DOWN_BEFORE, pd_on_swipe, (void *)0)) {
        cc2_stop(); /* page 2 never shows: the card's handlers find no dialog of ours */
        return;
    }
    for (i = 0; i < 3; i++) {
        pd_pg.px[i] = widget_get_prop_int(pd_pg.pg[i], "x", 0);
        pd_pg.py[i] = widget_get_prop_int(pd_pg.pg[i], "y", 0);
    }
    pd_pg.vis = 1; /* page 1 shown, page 2 hidden: as the asset has them */
    for (i = 0; i < 2; i++) {
        image_base_set_image(pd_pg.dot[i], i == 0 ? "drop_dot_on" : "drop_dot_off");
        m1_show(pd_pg.dot[i], 1);
    }
    if (pd_last) pd_page_set(1); /* the last open ended on page 2: open there, before the first paint (no slide) */
}

/* The hook (tools/pod.py PULLDOWN_INIT): the flags, then stock, then ours. */
int m1plus_pulldown_init(void *dlg, void *ctx) {
    int ret;
    pd_reconcile();
    ret = stock_pulldown_init_trampoline(dlg, ctx);
    if (ret == RET_OK && dlg) {
        widget_on(dlg, EVT_WINDOW_CLOSE, pd_on_close, dlg); /* a refused bind leaves stock's behaviour */
        pd_start(dlg);
        if (access(KILL_SD, F_OK) != 0) {
            bp_pulldown(
                dlg); /* the Battery Percentage and the EQ mark of the bar copy at once, before the first paint */
            lo_bar_refresh(dlg);
            pd_clock(dlg);
            pd_pages_start(dlg);
        }
    }
    return ret;
}

/* ---- the swipe's two gates (docs/modules/pulldown.md "Swipe gates and the window stack")
 *
 * on_wm_tsmove_fun opens the pull-down only while lockscreen_pageflag is not 1 (set by the lock page's init, cleared by its EVT_WINDOW_CLOSE) and dropdown_menu_state is 0 (its 0 is the dialog's own
 * EVT_WINDOW_CLOSE). A window that goes away without that event (stock's window manager can drop a close that arrives during an animation) leaves the word set for ever and the swipe dead until a reboot.
 * The hook runs before stock's on_wm_tsdown_fun and only clears: a flag is zeroed when no window of its name is in the window stack (a window under another page keeps its flag); nothing is closed, destroyed or opened, and
 * a flag is never set. With both words 0 (always, but for a lock screen or a pull-down on the way) it is two loads and the stock call.
 *
 * The third gate is usblink_status 2 (a computer has the card). check_usb_status stores it with the USB page's pending byte; the response timer clears the byte and opens usbmode_page (its result ignored), whose
 * close (usbmode_exit) stores 3. On an unplug the idle poll resets only 1 and 3, so a page that never opened or closed without its event leaves 2 for ever: no swipe, no card mount check, no auto standby.
 * The byte can also stay 1: Auto Update's modal scan dialog runs inside that timer, which does not fire again until the scan returns (then it opens the page, cable or not). Two hooks: pd_usb_poll wraps
 * the idle poll's call and, with state 2, the cable gone and no usbmode_page in the stack, drops the byte and stores 1, so the same call runs stock's own unplug (storage_config.sh stop, pc_check 0, state 0),
 * over the scan dialog too (stock's own scan runs with the state already 0 or 3). pd_usb_take is the timer's read of the byte: a request whose cable is gone is dropped, and its state 2 unplugged at once.
 * The touch hook covers a page lost with the cable never out: state 2, no page pending and no usbmode_page set the byte again. */
static int pd_off_state __attribute__((section(".scratch"))); /* 0 not read yet, 1 on, 2 kill switch */

static int pd_off(void) {
    if (!pd_off_state) pd_off_state = home_off() ? 2 : 1;
    return pd_off_state != 1;
}

/* true: a window of that name is in the stack, wherever. A window under another page keeps its word: its init does not run again when the page above closes, so a word cleared now would be wrong then (the
 * pull-down over the lock screen, a second pull-down). */
static int pd_present(void *wm, const char *name) {
    unsigned n = widget_count_children(wm);
    while (n--) {
        const char *nm = pd_name(widget_get_child(wm, n));
        if (nm && !strcmp(nm, name)) return 1;
    }
    return 0;
}

/* The hook (tools/pod.py TSDOWN): the two words made true, a lost USB page asked for again, then stock. */
int m1plus_tsdown(void *ctx, void *e) {
    volatile int *lock = (volatile int *)LOCK_PAGEFLAG, *state = (volatile int *)DROPDOWN_STATE;
    volatile unsigned char *pending = (volatile unsigned char *)USB_PAGE_PENDING;
    int lost = *(volatile int *)POWER_USBSTATE == 2 && *(volatile int *)POWER_EXT &&
               !*pending; /* host has the card, no page on the way */
    if ((*lock || *state || lost) && !pd_off()) {
        void *wm = window_manager();
        if (wm) {
            if (*lock && !pd_present(wm, "screensaver_page")) *lock = 0;
            if (*state && !pd_present(wm, "dropdown_dialog")) *state = 0;
            if (lost && !pd_present(wm, "usbmode_page")) *pending = 1; /* the response timer opens the page */
        }
    }
    return stock_tsdown_trampoline(ctx, e);
}

/* The hook (tools/pod_pins.py USBPOLL_SITE): a USB state 2 whose cable is gone, with no usbmode_page left to run usbmode_exit, made stock's 1, then stock's poll, whose unplug branch runs
 * storage_config.sh stop, clears pc_check and stores 0. */
int pd_usb_poll(void) {
    volatile int *usb = (volatile int *)POWER_USBSTATE;
    if (*usb == 2 && !*(volatile int *)POWER_EXT && !pd_off()) {
        void *wm = window_manager();
        if (wm && !pd_present(wm, "usbmode_page")) {
            *usb = 1;
            *(volatile unsigned char *)USB_PAGE_PENDING = 0;
        }
    }
    return check_usb_status();
}

/* The hook (tools/pod_pins.py USBTAKE_SITE, the pod_usb_site stub): the response timer's USB page request, 0 for none. A request whose cable is gone is dropped, and a state 2 unplugged at once
 * (pd_usb_poll), so a cable back before the next idle pass meets stock's 0 -> 1 -> 2, not a stale 2. */
int pd_usb_take(void) {
    volatile unsigned char *pending = (volatile unsigned char *)USB_PAGE_PENDING;
    if (*pending && !*(volatile int *)POWER_EXT && !pd_off()) {
        *pending = 0;
        if (*(volatile int *)POWER_USBSTATE == 2) pd_usb_poll();
    }
    return *pending;
}

/* ---- the Control Center page */

static struct { /* the page while it is open */
    void *row[PD_N], *sw[PD_N], *up[PD_N], *win, *sv;
    unsigned char order[PD_N]; /* every tile: the shown ones in order, then the hidden ones in stock order */
    unsigned n; /* how many are shown */
    unsigned down,
        pressed; /* tile id + 1 of the row a touch went down on / of the arrow showing its pressed look (0: none) */
    int zone; /* that touch went down inside the row's arrow rectangle */
} pg __attribute__((section(".scratch")));

static int pg_shown(unsigned id) {
    unsigned i;
    for (i = 0; i < pg.n; i++)
        if (pg.order[i] == id) return 1;
    return 0;
}

static void pg_rebuild(void) { /* the shown tiles stay, the hidden ones follow in stock order */
    unsigned i, k = pg.n;
    for (i = 0; i < PD_N; i++)
        if (!pg_shown(i)) pg.order[k++] = (unsigned char)i;
}

static char pg_char(unsigned id) { return (char)(id < 10 ? '0' + id : 'a' + id - 10); }

static int pg_save(void) {
    char buf[PD_N + 4];
    unsigned i, k = 0;
    for (i = 0; i < pg.n; i++) buf[k++] = pg_char(pg.order[i]);
    if (pg.n < PD_N) {
        buf[k++] = '-';
        for (i = pg.n; i < PD_N; i++) buf[k++] = pg_char(pg.order[i]);
    }
    buf[k++] = '\n';
    buf[k] = 0;
    return home_write_atomic(PULLDOWN_FILE, buf);
}

/* Arrange the rows from pg.order: y, switch image, arrow; then keep the row of tile `focus` (255: none) inside the scroll view's window and repaint (as patch/menu.c cm_layout). */
static void pg_layout(unsigned focus) {
    unsigned pos;
    for (pos = 0; pos < PD_N; pos++) {
        unsigned id = pg.order[pos];
        int on = pos < pg.n;
        widget_move(pg.row[id], 0, (int)pos * POD_ROW_H);
        image_base_set_image(pg.sw[id], on ? "sset_on" : "sset_off");
        widget_set_visible(pg.up[id], on && pos > 0, 0); /* a picture only: never a touch target */
        widget_set_sensitive(pg.up[id], 0);
    }
    for (pos = 0; pos < PD_N; pos++)
        widget_restack(pg.row[pg.order[pos]], pos); /* the children in page order: a relayout keeps it */
    if (pg.sv && focus < PD_N) {
        int vh = widget_get_prop_int(pg.sv, "h", 0), off = widget_get_prop_int(pg.sv, "yoffset", 0), top = 0,
            max = (int)PD_N * POD_ROW_H - vh;
        for (pos = 0; pos < PD_N; pos++)
            if (pg.order[pos] == focus) top = (int)pos * POD_ROW_H;
        if (vh > 0) {
            if (top < off) off = top;
            if (top + POD_ROW_H > off + vh) off = top + POD_ROW_H - vh;
            if (off > max) off = max;
            if (off < 0) off = 0;
            widget_set_prop_int(pg.sv, "yoffset", off);
        }
    }
    if (pg.win) widget_invalidate_force(pg.win, (void *)0);
}

/* Keep the change if it saved, else put the list back (and leave the page as it is). */
static void pg_commit(const unsigned char *old, unsigned old_n, unsigned id) {
    unsigned i;
    if (pg_save() != 0) {
        for (i = 0; i < old_n; i++) pg.order[i] = old[i];
        pg.n = old_n;
        pg_rebuild();
        return;
    }
    pg_layout(id);
}

static int pg_has_arrow(unsigned id) { return pg.n > 1 && pg.order[0] != id && pg_shown(id); }

static int
pg_in_zone(unsigned id,
           void *e) { /* the pointer event is in the arrow's x range of the row (screen coordinates: widget_to_local) */
    int pt[2], x, w;
    if (!e || !pg_has_arrow(id)) return 0;
    pt[0] = *(int *)((char *)e + PE_X);
    pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(pg.row[id], pt);
    x = widget_get_prop_int(pg.up[id], "x", 0);
    w = widget_get_prop_int(pg.up[id], "w", 0);
    return pt[0] >= x && pt[0] < x + w;
}

static void pg_release(void) { /* the arrow that shows its pressed look goes back to normal */
    if (pg.pressed) widget_set_state(pg.up[pg.pressed - 1], "normal");
    pg.pressed = 0;
}

static void pg_toggle(unsigned id) {
    unsigned i, k = 0, old_n = pg.n;
    unsigned char old[PD_N];
    for (i = 0; i < pg.n; i++) old[i] = pg.order[i];
    if (pg_shown(id)) { /* hidden: out of the order */
        for (i = 0; i < old_n; i++)
            if (old[i] != id) pg.order[k++] = old[i];
        pg.n = k;
    } else if (pg.n < PD_SLOTS) { /* shown again at the end */
        pg.order[pg.n++] = (unsigned char)id;
    } else { /* the pull-down holds eight: nothing changes */
        pod_toast(TR("Up to 8 controls"));
        return;
    }
    pg_rebuild();
    pg_commit(old, old_n, id);
}

static void pg_up(unsigned id) {
    unsigned i, k, old_n = pg.n;
    unsigned char old[PD_N];
    for (i = 0; i < pg.n; i++) old[i] = pg.order[i];
    for (k = 1; k < pg.n; k++) {
        if (pg.order[k] != id) continue;
        pg.order[k] = pg.order[k - 1];
        pg.order[k - 1] = (unsigned char)id;
        pg_commit(old, old_n, id);
        break;
    }
}

/* The row's pointer DOWN, UP and ABORT: remember where this touch began and show the arrow pressed while it is down inside its rectangle. */
static int pg_on_touch(void *ctx, void *e) {
    unsigned id = (unsigned)(long)ctx;
    int type = e ? *(int *)e : 0;
    if (type == EVT_POINTER_DOWN) {
        pg_release();
        pg.down = id + 1;
        pg.zone = pg_in_zone(id, e);
        if (pg.zone) {
            widget_set_state(pg.up[id], "pressed");
            pg.pressed = id + 1;
        }
    } else {
        pg_release();
    }
    return RET_OK;
}

static int pg_on_row(void *ctx, void *e) {
    unsigned id = (unsigned)(long)ctx;
    int zone = pg.down == id + 1 ? pg.zone : pg_in_zone(id, e);
    pg_release();
    pg.down = 0;
    if (zone && pg_has_arrow(id))
        pg_up(id);
    else
        pg_toggle(id);
    return RET_OK;
}

static int pg_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    memset(&pg, 0, sizeof pg);
    return RET_OK;
}

static void *pg_find(void *win, const char *base, unsigned i) {
    char name[24];
    snprintf(name, sizeof name, "%s%u", base, i);
    return widget_lookup(win, name, 1);
}

/* The Control Center page is up (patch/m1plus.c open_page): lay it out from the saved file and bind its rows. */
void pulldown_page_opened(void *win) {
    unsigned i;
    for (i = 0; i < PD_N; i++) {
        pg.row[i] = pg_find(win, "pod_row", i);
        pg.sw[i] = pg_find(win, "pod_switch", i);
        pg.up[i] = pg_find(win, "pod_up", i);
        if (!pg.row[i] || !pg.sw[i] || !pg.up[i]) { /* not our asset: leave it as it is */
            memset(&pg, 0, sizeof pg);
            return;
        }
    }
    pg.win = win;
    pg.sv = widget_lookup(win, "pod_scrollview", 1);
    if (pg.sv) menu_plain_paint(pg.sv);
    pg.n = pd_load(pg.order);
    pg_rebuild();
    pg_layout(255);
    for (i = 0; i < PD_N; i++) {
        widget_on(pg.row[i], EVT_CLICK, pg_on_row, (void *)(long)i);
        widget_on(pg.row[i], EVT_POINTER_DOWN, pg_on_touch, (void *)(long)i);
        widget_on(pg.row[i], EVT_POINTER_UP, pg_on_touch, (void *)(long)i);
        widget_on(pg.row[i], EVT_POINTER_ABORT, pg_on_touch, (void *)(long)i);
    }
    widget_on(win, EVT_DESTROY, pg_on_destroy, (void *)0);
}
