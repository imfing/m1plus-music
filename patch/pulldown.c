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
    }
}

/* The hook at on_wm_tsmove_fun's navigator_to("dialog/dropdown_dialog") (tools/pod.py PULLDOWN_DIALOG_SITE): the stock call, then, when the dialog was quit by one of our tiles (its result is
 * PD_QUIT, as for stock's tiles), the tile's action. Stock's own code that follows (the two flag tests) sees the result unchanged. */
int pd_open_dialog(const char *name) {
    int ret;
    unsigned act;
    ret = navigator_to(name);
    pd_hold_reset();
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
