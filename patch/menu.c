/* M1+ Music's customisable main menu: which items show, in which order, which of the others the Extras page lists, and the
 * Main Menu and Settings > Extras pages that edit it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The menu's asset (ui/m1plus_menu.bin) holds a stock list row for every item in the default order (the nine
 * menu items, the nine Extras tiles: Favorites ... CD Ripper, then Settings and the Pod: POD_MENU_ITEMS in all), then the Extras row (the
 * last, always shown, never hidden or moved); ui/m1plus_extras.bin holds the same row for every item. The setting is one small file,
 * MENU_FILE: the shown items in menu order, one character each (the item id, its row index: '0'..'8', then 'a'..'i' for ids 9..17,
 * 'j' for Settings, id 18, 'k' for the Pod, id 19), then optionally '-' and the items turned off (the Extras page does not list them), then a newline
 * ("12345\n", Cover Flow ... Playlists, is the default; Now Playing, Shuffle, Settings and the Pod are items that are hidden by default). It is read,
 * strictly, every time the menu, the Extras page or a customise page opens (and when the menu comes back to the foreground):
 * known characters only, no id twice (in either part or across them), '-' at most once, Settings never after it (it stays
 * reachable), a file shorter than POD_MENU_FILE_MAX; anything else, or no file, is the default list with nothing off
 * (tools/pod_pages.py parse_menu_full is the model, test/pod/menu.py fuzzes the two against each other). Nothing here can fail the
 * page open: a row or the list missing from the tree leaves the asset as it is.
 *
 * Arranging is plain widget calls on the stock list: a hidden row is hidden and insensitive (this AWTK
 * hit-tests hidden widgets) and parked at y 0, the shown ones are moved to y = position x ROW_H, and the
 * scroll_view's virtual_h and offset are set for the shown rows (the Artists list does the same for its
 * rows), and the children are stacked in the order they are shown (the stock list_view lays its visible rows out in child
 * order whenever the window is marked for relayout, and its paint hook assumes y order; see menu_arrange). Extras shows the
 * items the menu does not show and the list does not turn off, in a fixed order (tools/pod_pages.py EXTRAS_ORDER): the default
 * four titled groups (Play, Library, Collections, Tools), each with a section header above its first listed row.
 *
 * The Main Menu page (ui/m1plus_mainmenu.bin, opened by patch/m1plus.c): a row per item with a switch and an up
 * arrow on every shown item but the first, both pictures (insensitive); the row takes every tap and decides by
 * where it is: on the arrow's rectangle it moves the item one place up, elsewhere it shows or hides the item
 * (shown ones join the end of the menu, and an item shown has its off flag cleared). The shown items come first in menu order, the
 * hidden ones after them in the default order. The Settings > Extras page (ui/m1plus_extrascfg.bin): a switch row (the whole row
 * toggles) per item but Settings, only the rows the menu does not show, in the Extras order; on = listed on Extras, off = turned
 * off. Each change is saved at once (a failed save is undone) and the rows move in place; the menu and the Extras page arrange
 * again when they are back in front.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "grid.h"

#define N POD_MENU_ITEMS
#define CUSTOMIZE POD_SETTINGS_ID

static struct {
    unsigned char order[N]; /* the shown items, in menu order */
    unsigned n;
    unsigned off; /* bit id: the item is turned off (not listed on Extras); never a shown item or Settings */
} mn __attribute__((section(".scratch")));

static struct { /* the Main Menu page while it is open */
    void *row[N], *sw[N], *up[N], *win, *sv;
    unsigned char order[N]; /* every item: the shown ones in menu order, then the hidden ones */
    unsigned down,
        pressed; /* item id + 1 of the row a touch went down on / of the arrow showing its pressed look (0: none) */
    int zone; /* that touch went down inside the row's arrow rectangle */
} cm __attribute__((section(".scratch")));

static struct { /* the Settings > Extras page while it is open (no row for Settings: row[CUSTOMIZE] is 0) */
    void *row[N], *sw[N], *hdr[POD_EXTRAS_GROUPS], *win, *sv; /* hdr: the group section headers (a missing one: 0) */
} xc __attribute__((section(".scratch")));

static const unsigned char EX_ORDER[N] = POD_EXTRAS_ORDER; /* the Extras page's rows (item ids), top to bottom */

static const unsigned char EX_GROUP[N] = POD_EXTRAS_GROUP; /* the Extras group (section header) of each item id */

static void
mn_defaults(void) { /* tools/pod_pages.py DEFAULT_MENU: Cover Flow, Albums, Artists, Songs, Playlists ("12345") */
    static const unsigned char ids[POD_MENU_DEFAULT] = POD_MENU_DEFAULT_IDS;
    unsigned i;
    for (i = 0; i < POD_MENU_DEFAULT; i++) mn.order[i] = ids[i];
    mn.n = POD_MENU_DEFAULT;
    mn.off = 0;
}

/* The item id of a saved character ('0'..'8' the menu items, 'a'..'i' the Extras tiles, ids 9..17, 'j' Settings, 'k' the Pod, 'l' Podcasts, 'm' Search, 'n' Radio), or 255. */
static unsigned mn_id(unsigned c) {
    if (c - '0' < 9) return c - '0';
    if (c - 'a' < 15) return 9 + c - 'a';
    return 255;
}

static char mn_char(unsigned id) { return (char)(id < 9 ? '0' + id : 'a' + (id - 9)); }

/* The saved list, or the defaults. */
static void mn_load(void) {
    char buf[POD_MENU_FILE_MAX];
    int fd, n;
    unsigned i, len, part = 0, k = 0, seen = 0, off = 0;
    unsigned char ord[N];
    mn_defaults();
    fd = open(MENU_FILE, 0, 0);
    if (fd < 0) return;
    n = read(fd, buf, sizeof buf);
    close(fd);
    if (n <= 0 || n >= (int)sizeof buf) return; /* empty, or too long to be a list */
    len = (unsigned)n - (buf[n - 1] == '\n');
    for (i = 0; i < len; i++) {
        unsigned id;
        if (buf[i] == '-') { /* the off part starts: once */
            if (part) return;
            part = 1;
            continue;
        }
        id = mn_id((unsigned char)buf[i]);
        if (id >= N || (seen >> id & 1)) return;
        seen |= 1u << id;
        if (!part)
            ord[k++] = (unsigned char)id;
        else if (id == CUSTOMIZE)
            return; /* Settings can never be turned off */
        else
            off |= 1u << id;
    }
    for (i = 0; i < k; i++) mn.order[i] = ord[i];
    mn.n = k;
    mn.off = off;
}

static int mn_save(void) {
    char buf[N + 4];
    unsigned i, k = mn.n;
    for (i = 0; i < mn.n; i++) buf[i] = mn_char(mn.order[i]);
    if (mn.off) { /* the off items in the Extras order (pod_pages.format_menu) */
        buf[k++] = '-';
        for (i = 0; i < N; i++)
            if (mn.off >> EX_ORDER[i] & 1) buf[k++] = mn_char(EX_ORDER[i]);
    }
    buf[k++] = '\n';
    buf[k] = 0;
    return home_write_atomic(MENU_FILE, MENU_TMP, buf);
}

static void mn_show(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static void *mn_find(void *win, const char *base, unsigned i) {
    char name[24];
    snprintf(name, sizeof name, "%s%u", base, i);
    return widget_lookup(win, name, 1);
}

/* Row w at y (shown) or parked at y 0 and hidden. */
static void mn_put(void *w, int y, int on) {
    widget_move(w, 0, on ? y : 0);
    mn_show(w, on);
}

static void mn_place(void *w, unsigned pos, int on) { /* ... at position pos of the 52 px rows */
    mn_put(w, (int)pos * POD_ROW_H, on);
}

/* A section header (a caption, tools/pod_ui.py extras_header): at y or parked, shown or hidden, and never sensitive: a touch on it falls to the list. */
static void mn_header(void *w, int y, int on) {
    widget_move(w, 0, on ? y : 0);
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, 0);
}

static int mn_shown(unsigned id);
static int mn_listed(unsigned id);

/* Stack the Extras page (cfg 0) or Settings > Extras (cfg 1): per group, in the fixed order, its header (if the asset has it) above the group's first listed row, then
 * its rows; the groups with no listed row have their headers hidden, and the unlisted rows are hidden, last. A row is listed when the menu does not show the item and,
 * on the Extras page, the list did not turn it off (the Settings > Extras page lists the turned-off ones too, and has no row for Settings: row[CUSTOMIZE] is 0).
 * tools/pod_pages.py extras_display / extras_layout are the model. seq gets the children in stacking order; returns their count, and the list's height in *vh. */
static unsigned mn_extras(void *const *row, void *const *hdr, int cfg, void **seq, int *vh) {
    unsigned g, i, k = 0;
    int y = 0, has[POD_EXTRAS_GROUPS];
    for (g = 0; g < POD_EXTRAS_GROUPS; g++) {
        has[g] = 0;
        for (i = 0; i < N; i++) {
            unsigned id = EX_ORDER[i];
            if (EX_GROUP[id] != g || !row[id] || !(cfg ? !mn_shown(id) : mn_listed(id))) continue;
            if (!has[g] && hdr[g]) {
                mn_header(hdr[g], y, 1);
                seq[k++] = hdr[g];
                y += POD_EXTRAS_HDR_H;
            }
            has[g] = 1;
            mn_put(row[id], y, 1);
            seq[k++] = row[id];
            y += POD_ROW_H;
        }
    }
    for (g = 0; g < POD_EXTRAS_GROUPS; g++)
        if (!has[g] && hdr[g]) {
            mn_header(hdr[g], 0, 0);
            seq[k++] = hdr[g];
        }
    for (i = 0; i < N; i++) {
        unsigned id = EX_ORDER[i];
        if (!row[id] || (cfg ? !mn_shown(id) : mn_listed(id))) continue;
        mn_place(row[id], 0, 0);
        seq[k++] = row[id];
    }
    *vh = y;
    return k;
}

static int mn_shown(unsigned id) {
    unsigned i;
    for (i = 0; i < mn.n; i++)
        if (mn.order[i] == id) return 1;
    return 0;
}

/* The Extras page lists an item the menu does not show and the list did not turn off; never Settings (its button is in the page's navbar, its row stays hidden). */
static int mn_listed(unsigned id) { return id != CUSTOMIZE && !mn_shown(id) && !(mn.off >> id & 1); }

/* The stock list_view gives its scroll_view a paint-children hook (list_view_on_add_child, sw 0xf4 @0x60cd10, stock
 * function 0x60c164) that returns at the first visible child whose top is below the canvas: it takes the children to be
 * in y order. The plain painter (what a scroll_view outside a list_view uses) has no such early exit, so a page whose
 * rows are placed by hand lets the scroll_view use that one. Only the exact stock hook on a real scroll_view is cleared. */
static void mn_plain_paint(void *sv) {
    if (*(unsigned *)((char *)sv + W_VT) == SV_VTABLE && *(unsigned *)((char *)sv + SV_PAINT_CHILDREN) == LV_PAINT_HOOK)
        *(unsigned *)((char *)sv + SV_PAINT_CHILDREN) = 0;
}

void menu_plain_paint(void *sv) { mn_plain_paint(sv); } /* patch/pulldown.c: its page lays its rows out by hand too */

/* The menu (extras 0) or the Extras page (extras 1) as the saved list says. The stock list_view lays its visible rows
 * out again, in child order (children_layouter_list_view @0x60abbc, set_virtual_h @0x60b20c), whenever the window is
 * marked for relayout (widget_set_visible does that, and the main loop lays out before every paint, @0x6939f4): the
 * first frame after the menu comes back from the lock screen showed the asset's order. So the children are stacked in
 * the order they are shown (hidden rows last, they are skipped), and that layout gives the rows the y and the virtual
 * height set here: any relayout leaves the page as it is.
 *
 * The menu's list has three non-row children (the Home instance's): the Daily Mix section (patch/dailymix.c), DM_SEC_H high, which follows the shown rows (below Extras:
 * the rows keep their places, the section sits at y = shown rows x 52 while it is visible), the Recently Played shelf (patch/recent.c), one to three rows of covers high
 * (its own height), right after the section, and the trailing spacer row pod_pad (the mini player bar's padding), the last child, after the shelf. All three are skipped
 * by the layouter while hidden. The list keeps its scroll position (clamped to the new
 * range): a page just opened is at the top, and the menu back in front (from a page it opened) stays where it was. Returns 0 when
 * the asset is not ours (nothing was changed). */
static int mn_arrange(void *win, int extras) {
    void *sv = widget_lookup(win, "pod_scrollview", 1), *row[POD_MENU_ROWS], *hdr[POD_EXTRAS_GROUPS],
         *seq[POD_MENU_ROWS + POD_EXTRAS_GROUPS + 2];
    void *pad = extras
                    ? (void *)0
                    : widget_lookup(
                          win, "pod_pad",
                          1); /* the menu's trailing spacer row (the mini player bar's padding), if the asset has it */
    void *shelf =
        extras ? (void *)0 : widget_lookup(win, "pod_shelf", 1); /* the Recently Played shelf, if the asset has it */
    void *daily =
        extras ? (void *)0
               : widget_lookup(win, "pod_daily", 1); /* the Daily Mix section (patch/dailymix.c), if the asset has it */
    unsigned total = extras ? POD_EXTRAS_ROWS : POD_MENU_ROWS, i, pos = 0, k = 0;
    int vh, max, shelf_h, daily_h, rows_h;
    if (!sv) return 0;
    for (i = 0; i < total; i++) {
        row[i] = mn_find(win, "pod_row", i);
        if (!row[i]) return 0; /* not our asset: leave it as it is */
    }
    mn_load();
    shelf_h = shelf && widget_get_visible(shelf)
                  ? widget_get_prop_int(shelf, "h", SH_HMAX)
                  : 0; /* its own height: one to three rows of covers (patch/recent.c sets it) */
    daily_h = daily && widget_get_visible(daily) ? widget_get_prop_int(daily, "h", DM_SEC_H)
                                                 : 0; /* the card's section: a fixed DM_SEC_H */
    if (extras) { /* the rows the menu does not show and the list did not turn off, in the fixed Extras order, under the headers of their groups; the others hidden, last */
        for (i = 0; i < POD_EXTRAS_GROUPS; i++)
            hdr[i] = mn_find(win, "pod_hdr", i); /* (a missing header: that group has none) */
        k = mn_extras(row, hdr, 0, seq, &vh);
        for (i = 0; i < k; i++) widget_restack(seq[i], i);
        rows_h = vh;
    } else {
        for (i = 0; i < mn.n; i++) {
            seq[k++] = row[mn.order[i]];
            mn_place(row[mn.order[i]], pos++, 1);
        }
        seq[k++] = row[N];
        mn_place(row[N], pos++, 1); /* Extras: always shown, always the last row */
        rows_h = (int)pos * POD_ROW_H;
        if (daily) {
            widget_move(daily, 0, rows_h);
            seq[k++] = daily; /* right after the shown rows (hidden, the layouter skips it) */
        }
        if (shelf) {
            widget_move(shelf, 0, rows_h + daily_h);
            seq[k++] = shelf; /* then the shelf (hidden, the layouter skips it) */
        }
        for (i = 0; i < N; i++)
            if (!mn_shown(i)) {
                seq[k++] = row[i];
                mn_place(row[i], 0, 0);
            }
        if (pad) seq[k++] = pad; /* last: after the shown rows (the layouter skips the hidden ones in between) */
        for (i = 0; i < k; i++) widget_restack(seq[i], i);
    }
    mn_plain_paint(sv);
    /* the spacer row is visible only while the mini player bar shows (patch/minibar.c mb_pad); then it is the last row, MB_PAD high, and the
     * stock layout, which sums the heights of the visible children, keeps it */
    if (pad) widget_move(pad, 0, rows_h + daily_h + shelf_h);
    vh = rows_h + daily_h + shelf_h + (pad && widget_get_visible(pad) ? MB_PAD : 0);
    widget_set_prop_int(sv, "virtual_h", vh);
    max = vh - widget_get_prop_int(sv, "h", 0); /* a shorter list may not stay scrolled past its end */
    if (max < 0) max = 0;
    if (widget_get_prop_int(sv, "yoffset", 0) > max) widget_set_prop_int(sv, "yoffset", max);
    widget_invalidate_force(sv, (void *)0);
    return 1;
}

void menu_arrange(void *win, int extras) { mn_arrange(win, extras); }

/* A section of the Home list (the Recently Played shelf, patch/recent.c; the Daily Mix card, patch/dailymix.c) shows or hides: visible and sensitive together;
 * the list keeps its place. Nothing changes when the asset has no such section or is not ours. */
static void mn_section(void *win, const char *name, int on) {
    void *sec = widget_lookup(win, name, 1);
    int was;
    if (!sec) return;
    was = widget_get_visible(sec);
    if (!was && !on)
        return; /* still hidden: nothing to do (a visible section is arranged again: its height may have changed) */
    mn_show(sec, on);
    if (!mn_arrange(win, 0)) mn_show(sec, was);
}

void menu_shelf(void *win, int on) { mn_section(win, "pod_shelf", on); }
void menu_daily(void *win, int on) { mn_section(win, "pod_daily", on); }

/* ---- the Main Menu page */

static void cm_rebuild(void) {
    unsigned i, k = mn.n;
    for (i = 0; i < mn.n; i++) cm.order[i] = mn.order[i];
    for (i = 0; i < N; i++)
        if (!mn_shown(i)) cm.order[k++] = (unsigned char)i;
}

/* Arrange the rows from cm.order (the same pass at open and after every change): y, switch image, arrow. Then keep
 * the row of item `focus` (255: none) inside the scroll view's window, and repaint the whole page (a change moves
 * rows under the finger; the dirty rectangles of single widgets are not relied on). */
static void cm_layout(unsigned focus) {
    unsigned pos;
    for (pos = 0; pos < N; pos++) {
        unsigned id = cm.order[pos];
        int on = pos < mn.n;
        widget_move(cm.row[id], 0, (int)pos * POD_ROW_H);
        image_base_set_image(cm.sw[id], on ? "sset_on" : "sset_off");
        widget_set_visible(cm.up[id], on && pos > 0, 0); /* a picture only: never a touch target */
        widget_set_sensitive(cm.up[id], 0);
    }
    for (pos = 0; pos < N; pos++)
        widget_restack(cm.row[cm.order[pos]],
                       pos); /* the children in page order: a relayout keeps it (see menu_arrange) */
    if (cm.sv && focus < N) {
        int vh = widget_get_prop_int(cm.sv, "h", 0), off = widget_get_prop_int(cm.sv, "yoffset", 0), top = 0,
            max = (int)N * POD_ROW_H - vh;
        for (pos = 0; pos < N; pos++)
            if (cm.order[pos] == focus) top = (int)pos * POD_ROW_H;
        if (vh > 0) {
            if (top < off) off = top;
            if (top + POD_ROW_H > off + vh) off = top + POD_ROW_H - vh;
            if (off > max) off = max;
            if (off < 0) off = 0;
            widget_set_prop_int(cm.sv, "yoffset", off);
        }
    }
    if (cm.win) widget_invalidate_force(cm.win, (void *)0);
}

/* Keep the change if it saved, else put the list back (and leave the page as it is). */
static void cm_commit(const unsigned char *old, unsigned old_n, unsigned old_off, unsigned id) {
    unsigned i;
    if (mn_save() != 0) {
        mn.off = old_off;
        for (i = 0; i < old_n; i++) mn.order[i] = old[i];
        mn.n = old_n;
        return;
    }
    cm_rebuild();
    cm_layout(id);
}

/* One touch target per row. The up arrow is only a picture (insensitive): a stock button would answer the pointer
 * DOWN and UP with RET_OK and the row, a list_item, would be clicked as well (one tap would move the item and
 * toggle it). So the row decides by where the finger went down: inside the arrow's rectangle (the arrow button's x
 * and w in the row, the full 52 px height) the tap moves the item up, anywhere else it shows or hides the item. A
 * row without an arrow (hidden, or first) takes the whole width as a toggle. The pointer event carries screen
 * coordinates; widget_to_local turns them into the row's. */
static int cm_has_arrow(unsigned id) { return mn.n > 1 && mn.order[0] != id && mn_shown(id); }

static int cm_in_zone(unsigned id, void *e) {
    int pt[2], x, w;
    if (!e || !cm_has_arrow(id)) return 0;
    pt[0] = *(int *)((char *)e + PE_X);
    pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(cm.row[id], pt);
    x = widget_get_prop_int(cm.up[id], "x", 0);
    w = widget_get_prop_int(cm.up[id], "w", 0);
    return pt[0] >= x && pt[0] < x + w;
}

static void cm_release(void) { /* the arrow that shows its pressed look goes back to normal */
    if (cm.pressed) widget_set_state(cm.up[cm.pressed - 1], "normal");
    cm.pressed = 0;
}

static void cm_toggle(unsigned id) {
    unsigned i, k = 0;
    unsigned char old[N];
    unsigned old_n = mn.n, old_off = mn.off;
    for (i = 0; i < mn.n; i++) old[i] = mn.order[i];
    if (mn_shown(id)) { /* hidden: it shows on Extras (its off flag was clear while it was shown) */
        for (i = 0; i < old_n; i++)
            if (old[i] != id) mn.order[k++] = old[i];
        mn.n = k;
    } else if (mn.n < N) { /* shown again at the end of the menu: no longer turned off */
        mn.order[mn.n++] = (unsigned char)id;
        mn.off &= ~(1u << id);
    }
    cm_commit(old, old_n, old_off, id);
}

static void cm_up(unsigned id) {
    unsigned i, k;
    unsigned char old[N];
    unsigned old_n = mn.n, old_off = mn.off;
    for (i = 0; i < mn.n; i++) old[i] = mn.order[i];
    for (k = 1; k < mn.n; k++) {
        if (mn.order[k] != id) continue;
        mn.order[k] = mn.order[k - 1];
        mn.order[k - 1] = (unsigned char)id;
        cm_commit(old, old_n, old_off, id);
        break;
    }
}

/* The row's pointer DOWN, UP and ABORT: remember where this touch began and show the arrow pressed while it is
 * down inside its rectangle. */
static int cm_on_touch(void *ctx, void *e) {
    unsigned id = (unsigned)(long)ctx;
    int type = e ? *(int *)e : 0;
    if (type == EVT_POINTER_DOWN) {
        cm_release();
        cm.down = id + 1;
        cm.zone = cm_in_zone(id, e);
        if (cm.zone) {
            widget_set_state(cm.up[id], "pressed");
            cm.pressed = id + 1;
        }
    } else {
        cm_release();
    }
    return RET_OK;
}

static int cm_on_row(void *ctx, void *e) {
    unsigned id = (unsigned)(long)ctx;
    int zone = cm.down == id + 1 ? cm.zone : cm_in_zone(id, e);
    cm_release();
    cm.down = 0;
    if (zone && cm_has_arrow(id))
        cm_up(id);
    else
        cm_toggle(id);
    return RET_OK;
}

static int cm_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    memset(&cm, 0, sizeof cm);
    return RET_OK;
}

/* The Main Menu page is up (patch/m1plus.c open_page): lay it out from the saved list and bind its rows. */
void menu_custom_opened(void *win) {
    unsigned i;
    for (i = 0; i < N; i++) {
        cm.row[i] = mn_find(win, "pod_row", i);
        cm.sw[i] = mn_find(win, "pod_switch", i);
        cm.up[i] = mn_find(win, "pod_up", i);
        if (!cm.row[i] || !cm.sw[i] || !cm.up[i]) { /* not our asset: leave it as it is */
            memset(&cm, 0, sizeof cm);
            return;
        }
    }
    cm.win = win;
    cm.sv = widget_lookup(win, "pod_scrollview", 1);
    if (cm.sv) mn_plain_paint(cm.sv);
    mn_load();
    cm_rebuild();
    cm_layout(255);
    for (i = 0; i < N; i++) {
        widget_on(cm.row[i], EVT_CLICK, cm_on_row, (void *)(long)i);
        widget_on(cm.row[i], EVT_POINTER_DOWN, cm_on_touch, (void *)(long)i);
        widget_on(cm.row[i], EVT_POINTER_UP, cm_on_touch, (void *)(long)i);
        widget_on(cm.row[i], EVT_POINTER_ABORT, cm_on_touch, (void *)(long)i);
    }
    widget_on(win, EVT_DESTROY, cm_on_destroy, (void *)0);
}

/* ---- the Settings > Extras page */

/* Lay the rows out: the items the menu does not show, in the Extras order, the others hidden (last); each switch is on when the
 * Extras page lists the item. The list is scrolled to the top when the page opens, and clamped later. */
static void xc_layout(void) {
    unsigned i, k;
    void *seq[N + POD_EXTRAS_GROUPS];
    int vh, max;
    for (i = 0; i < N; i++) {
        unsigned id = EX_ORDER[i];
        if (id != CUSTOMIZE && !mn_shown(id))
            image_base_set_image(xc.sw[id], mn.off >> id & 1 ? "sset_off" : "sset_on");
    }
    k = mn_extras(xc.row, xc.hdr, 1, seq, &vh); /* the rows under their group's header, the others hidden last */
    for (i = 0; i < k; i++) widget_restack(seq[i], i);
    widget_set_prop_int(xc.sv, "virtual_h", vh);
    max = vh - widget_get_prop_int(xc.sv, "h", 0);
    if (max < 0) max = 0;
    if (widget_get_prop_int(xc.sv, "yoffset", 0) > max) widget_set_prop_int(xc.sv, "yoffset", max);
    widget_invalidate_force(xc.win, (void *)0);
}

/* A tap on a row: turn the item off the Extras page or back on, saved at once (a failed save is undone). */
static int xc_on_row(void *ctx, void *e) {
    unsigned id = (unsigned)(long)ctx, old_off = mn.off;
    (void)e;
    if (id == CUSTOMIZE || mn_shown(id)) return RET_OK;
    mn.off ^= 1u << id;
    if (mn_save() != 0) mn.off = old_off;
    image_base_set_image(xc.sw[id], mn.off >> id & 1 ? "sset_off" : "sset_on");
    widget_invalidate_force(xc.win, (void *)0);
    return RET_OK;
}

static int xc_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    memset(&xc, 0, sizeof xc);
    return RET_OK;
}

/* The Settings > Extras page is up (patch/m1plus.c open_page): lay it out from the saved list and bind its rows. */
void menu_extras_opened(void *win) {
    unsigned i;
    memset(&xc, 0, sizeof xc);
    for (i = 0; i < N; i++) {
        if (i == CUSTOMIZE) continue; /* Settings has no row: it is never turned off */
        xc.row[i] = mn_find(win, "pod_row", i);
        xc.sw[i] = mn_find(win, "pod_switch", i);
        if (!xc.row[i] || !xc.sw[i]) { /* not our asset: leave it as it is */
            memset(&xc, 0, sizeof xc);
            return;
        }
    }
    for (i = 0; i < POD_EXTRAS_GROUPS; i++) xc.hdr[i] = mn_find(win, "pod_hdr", i);
    xc.win = win;
    xc.sv = widget_lookup(win, "pod_scrollview", 1);
    if (!xc.sv) {
        memset(&xc, 0, sizeof xc);
        return;
    }
    mn_plain_paint(xc.sv);
    mn_load();
    xc_layout();
    for (i = 0; i < N; i++)
        if (xc.row[i]) widget_on(xc.row[i], EVT_CLICK, xc_on_row, (void *)(long)i);
    widget_on(win, EVT_DESTROY, xc_on_destroy, (void *)0);
}
