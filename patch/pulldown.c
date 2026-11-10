/* The pull-down's tiles: which of the eight show and in what order, and the Settings > System > Appearance > Control Center page that edits it.
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
 * One hook, dialog_dropdown_dialog_init (0x475f04, tools/pod.py PULLDOWN_INIT): run when the dialog is built (never at boot or in the
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
#include "home.h"
#include "common.h"

#define PD_N 8
#define PD_FILE_MAX 12 /* tools/pod_pages.py PULLDOWN_FILE_MAX */

extern void menu_plain_paint(void *sv); /* patch/menu.c */

static const char *const PD_IMG[PD_N] = {"img_wifiswitch", "img_btswitch",     "img_keylockswitch", "img_gainswitch",
                                         "img_usbmode",    "img_outputswitch", "img_playset",       "img_sysset"};
static const char *const PD_LAB[PD_N] = {"label_wifi",    "label_bt",        "label_lock",    "label_gain",
                                         "label_usbmode", "label_outputway", "label_playset", "label_sysset"};

/* The shown tiles in order (ord, at least PD_N long) from the saved file; the count. The default: all eight in stock order. */
static unsigned pd_load(unsigned char *ord) {
    char buf[PD_FILE_MAX];
    unsigned char tmp[PD_N];
    int fd, n;
    unsigned i, len, part = 0, k = 0, seen = 0;
    for (i = 0; i < PD_N; i++) ord[i] = (unsigned char)i;
    fd = open(PULLDOWN_FILE, 0, 0);
    if (fd < 0) return PD_N;
    n = read(fd, buf, sizeof buf);
    close(fd);
    if (n <= 0 || n >= (int)sizeof buf) return PD_N; /* empty, or too long to be a list */
    len = (unsigned)n - (buf[n - 1] == '\n');
    for (i = 0; i < len; i++) {
        unsigned id;
        if (buf[i] == '-') { /* the hidden part starts: once */
            if (part) return PD_N;
            part = 1;
            continue;
        }
        id = (unsigned char)buf[i] - '0';
        if (id >= PD_N || (seen >> id & 1)) return PD_N;
        seen |= 1u << id;
        if (!part) tmp[k++] = (unsigned char)id;
    }
    for (i = 0; i < k; i++) ord[i] = tmp[i];
    return k;
}

/* ---- the pull-down */

static void pd_hide(void *w) {
    widget_set_visible(w, 0, 0);
    widget_set_sensitive(w, 0);
}

static void pd_start(void *dlg) {
    void *img[PD_N], *lab[PD_N];
    int px[PD_N], py[PD_N], dx[PD_N], dy[PD_N];
    unsigned char ord[PD_N];
    unsigned i, n, shown = 0;
    for (i = 0; i < PD_N; i++) {
        img[i] = widget_lookup(dlg, PD_IMG[i], 1);
        lab[i] = widget_lookup(dlg, PD_LAB[i], 1);
        if (!img[i] || !lab[i]) return; /* not our asset: leave the stock tiles */
        px[i] = widget_get_prop_int(img[i], "x", 0);
        py[i] = widget_get_prop_int(img[i], "y", 0);
        dx[i] = widget_get_prop_int(lab[i], "x", 0) - px[i];
        dy[i] = widget_get_prop_int(lab[i], "y", 0) - py[i];
    }
    n = pd_load(ord);
    for (i = 0; i < n; i++) shown |= 1u << ord[i];
    for (i = 0; i < n; i++)
        if (ord[i] != i) break;
    if (n == PD_N && i == n) return; /* the stock layout */
    for (i = 0; i < n; i++) { /* shown tile ord[i] takes tile i's place (the places were read above) */
        widget_move(img[ord[i]], px[i], py[i]);
        widget_move(lab[ord[i]], px[i] + dx[ord[i]], py[i] + dy[ord[i]]);
    }
    for (i = 0; i < PD_N; i++)
        if (!(shown >> i & 1)) {
            pd_hide(img[i]);
            pd_hide(lab[i]);
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
    volatile int *flag;
} PD_SET[2] = {{"sysset_page", "systemset/sysset_page", (volatile int *)SYSSET_FLAG},
               {"playset_page", "playset/playset_page", (volatile int *)PLAYSET_FLAG}};

/* The named window in the manager and whether a window that leaves settings is above it; 0 when there is none. */
static void *pd_window(void *wm, const char *name, int *above) {
    unsigned n = widget_count_children(wm);
    *above = 0;
    while (n--) {
        void *w = widget_get_child(wm, n);
        const char *nm = w ? *(const char **)((char *)w + WIDGET_NAME) : (const char *)0;
        if (!nm) continue;
        if (!strcmp(nm, name)) return w;
        if (!strcmp(nm, "playing_page") || !strcmp(nm, "m1plus_radionp") || !strcmp(nm, "home_page")) *above = 1;
    }
    return (void *)0;
}

static void pd_reconcile(void) {
    void *wm = window_manager();
    unsigned i;
    if (!wm) return;
    for (i = 0; i < 2; i++) {
        int above;
        void *win = pd_window(wm, PD_SET[i].window, &above);
        *PD_SET[i].flag = win && widget_is_window_opened(win) && !above; /* (a page that is closing is gone) */
    }
}

/* The hook at the two navigator_to calls of on_wm_tsmove_fun that open the page a tile chose (flag 2): the page when it is still in the stack is brought to the front the way stock brings the player back
 * (window_manager_switch_to, nothing closed, Back returns to where the user came from); otherwise (or if that fails) stock's call. The page's own init sets the flag when it opens; a restacked page runs no
 * init, so the flag is set here; a page that will not open leaves no flag of 2. Any other name is the stock call. A tap only. */
int pd_open_settings(const char *name) {
    unsigned i;
    int ret;
    for (i = 0; i < 2 && strcmp(name, PD_SET[i].nav); i++) {
    }
    if (i < 2 && pod_restack_window(PD_SET[i].window)) {
        *PD_SET[i].flag = 1;
        return RET_OK;
    }
    ret = navigator_to(name);
    if (i < 2 && ret != RET_OK) *PD_SET[i].flag = 0;
    return ret;
}

/* The hook (tools/pod.py PULLDOWN_INIT): the flags, then stock, then ours. */
int m1plus_pulldown_init(void *dlg, void *ctx) {
    int ret;
    pd_reconcile();
    ret = stock_pulldown_init_trampoline(dlg, ctx);
    if (ret == RET_OK && dlg) pd_start(dlg);
    return ret;
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

static int pg_save(void) {
    char buf[PD_N + 4];
    unsigned i, k = 0;
    for (i = 0; i < pg.n; i++) buf[k++] = (char)('0' + pg.order[i]);
    if (pg.n < PD_N) {
        buf[k++] = '-';
        for (i = pg.n; i < PD_N; i++) buf[k++] = (char)('0' + pg.order[i]);
    }
    buf[k++] = '\n';
    buf[k] = 0;
    return home_write_atomic(PULLDOWN_FILE, PULLDOWN_TMP, buf);
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
    } else if (pg.n < PD_N) { /* shown again at the end */
        pg.order[pg.n++] = (unsigned char)id;
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
