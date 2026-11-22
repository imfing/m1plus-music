/* M1+ Music Line Out pill: an amber pill instead of the status bar's white "LO" text (docs/modules/lineout.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * While Line Out is on (the byte 0xa05aa7), stock's show_sysbar_face (0x544b48, the status bar's 1 s timer) and dropdown_showface (0x475c3c, the pull-down's own bar copy, its own timer)
 * put the text "LO" in label_volume instead of the volume number, then call widget_set_text_utf8(label_volume, text) (0x544f90 / 0x475ad8), having shown the label
 * (widget_set_visible 1) earlier in the same call. Both call-site words `jalr widget_set_text_utf8` are now `jal lo_set_text` (the delay slot `move a0, s7` and a1 = the text stay stock's).
 * lo_set_text runs stock's function first; then, if the text is exactly "LO" and the kill switch /mnt/mmc/m1plus-off is absent, it hides label_volume (visible and sensitive off) and shows the sibling pill
 * `pod_lo` (an image in the same group, hidden and insensitive in the UI files); otherwise it restores the label and hides the pill. It runs in both timers right where stock sets the text, so
 * nothing lags and nothing flickers (the label is shown and hidden inside one timer call, before any paint). The group's layouter skips an invisible child, so the pill takes the label's place.
 * The same call also toggles the status bar's sync icon pod_sync (lo_sync) from one volatile flag of patch/covercache.c, and the Sleep Timer moon pod_sleep (lo_sleep). Cost: one access and a few lookups by name per second per bar
 * (seven more while a Sleep Timer runs, for the moon's room test); no allocation, no state. Not on the boot path. On the real bar it also lets the palette repaint the bar when the window in front
 * is painted otherwise (pal_bar_follow, patch/palette.c: one top-window lookup per second).
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "lineout.h"
#include "covercache.h"
#include "peqout.h"
#include "palette.h"

/* The sync icon (docs/modules/lineout.md "Sync icon"): pod_sync in the bar's right group, shown while the cover worker has a cover or duration set with work left (cc_build_active: volatile reads, no lock, no file) and the
 * kill switch is absent. `parent` is label_volume's parent (view_bar_left); the bar is its parent. Set only when it changes, so a steady state costs no relayout. A bar without the widget is left alone. */
static void lo_sync(void *parent, int kill) {
    void *bar = (void *)((int *)parent)[LO_W_PARENT / 4], *ind;
    int on = !kill && cc_build_active();
    if (!bar) return;
    ind = widget_lookup(bar, SYNC_IND, 1);
    if (ind && !widget_get_visible(ind) != !on) m1_show(ind, on);
}

/* A visible peer of the moon in the bar's right group: its box and the gap before it; 0 when absent or hidden. */
static int lo_peer(void *bar, const char *name) {
    void *w = widget_lookup(bar, name, 1);
    return w && widget_get_visible(w) ? ((int *)w)[W_W / 4] + SLEEP_GAP : 0;
}

/* The ink width of the Bluetooth box's image (glyph or codec badge, right-aligned in the box); an image not listed counts the whole box. */
static int lo_bt_ink(void *bt) {
    const char *n = widget_get_prop_str(bt, "image", "");
    if (!strcmp(n, SLEEP_BT_GLYPH) || !strcmp(n, SLEEP_BT_CON)) return SLEEP_INK_GLYPH;
    if (!strcmp(n, SLEEP_BT_AAC)) return SLEEP_INK_AAC;
    if (!strcmp(n, SLEEP_BT_SBC)) return SLEEP_INK_SBC;
    if (!strcmp(n, SLEEP_BT_LDAC)) return SLEEP_INK_LDAC;
    return ((int *)bt)[W_W / 4];
}

/* Room for the moon (lineout.h SLEEP_ROOM): the moon's box, every visible peer, and the Bluetooth box's ink stay within the room left of the clock. The moon yields to everything else. */
static int lo_sleep_fits(void *bar, void *ind) {
    void *bt = widget_lookup(bar, SLEEP_BT, 1);
    int used = ((int *)ind)[W_W / 4];
    used += lo_peer(bar, SYNC_IND) + lo_peer(bar, SLEEP_SYNCLINK) + lo_peer(bar, SLEEP_WIFI) + lo_peer(bar, SLEEP_SHOT);
    if (bt && widget_get_visible(bt)) used += SLEEP_GAP + lo_bt_ink(bt);
    return used <= SLEEP_ROOM;
}

/* The sleep timer icon (docs/modules/lineout.md "Sleep Timer icon"): pod_sleep in the bar's right group, shown while stock's sleep timer is running (sleepflag != 0 and sleep_time > 0, the same test
 * patch/sleeptimer.c uses), the kill switch is absent and the row has room for it (lo_sleep_fits). Stock sets the Bluetooth image on the same tick, possibly after this
 * call, so a change there reaches the moon one tick late. Set only when it changes, so a steady state costs no relayout. A bar without the widget is left alone. */
static void lo_sleep(void *bar, int kill) {
    void *ind;
    int on = !kill && *(volatile unsigned char *)SLEEP_FLAG != 0 && *(volatile int *)SLEEP_TIME > 0;
    if (!bar) return;
    ind = widget_lookup(bar, SLEEP_IND, 1);
    if (!ind) return;
    if (on) on = lo_sleep_fits(bar, ind);
    if (!widget_get_visible(ind) != !on) m1_show(ind, on);
}

/* The EQ mark (docs/modules/lineout.md "EQ mark"): pod_eq in the bar's left group, shown while the Equalizer switch is on (stock's equalizer_flag, the byte the Equalizer page and the per-output EQ keep) and the kill
 * switch is absent. Hidden while stock's digital-out glyph shows: with both, the group would run into the clock. Stock sets that glyph later in the same tick, so on the timer path the mark follows it one tick late; a window's init covers its first paint (lo_bar_refresh).
 * Set only when it changes. A bar without the widget is left alone. */
static void lo_eq(void *parent, int kill) {
    void *ind = widget_lookup(parent, EQ_IND, 0), *dig;
    int on;
    if (!ind) return;
    on = !kill && *(volatile unsigned char *)EQ_FLAG != 0;
    if (on && (dig = widget_lookup(parent, EQ_DIGITAL, 0)) != 0 && widget_get_visible(dig)) on = 0;
    if (!widget_get_visible(ind) != !on) m1_show(ind, on);
}

/* The pull-down's init (patch/pulldown.c, after stock's init, whose face call has set the digital-out glyph, and only without the kill switch): the EQ mark and the sleep timer icon at once, where its first
 * face tick would come 500 ms later. The pill and the per-output EQ are the timer's. A window without the bar is left alone. */
void lo_bar_refresh(void *win) {
    void *left = widget_lookup(win, LO_GROUP, 1);
    if (left) lo_eq(left, 0);
    lo_sleep(win, 0);
}

/* The hooks (tools/pod.py LINEOUT_SITES): stock's widget_set_text_utf8(label, text), then the pill swap. */
int lo_set_text(void *label, const char *text) {
    int r = widget_set_text_utf8(label, text);
    void *parent, *pill, *bar;
    int kill;
    if (!label) return r;
    parent = (void *)((int *)label)[LO_W_PARENT / 4];
    if (!parent) return r;
    kill = access(KILL_SD, F_OK) == 0;
    lo_sync(parent, kill);
    bar = (void *)((int *)parent)[LO_W_PARENT / 4];
    lo_sleep(bar, kill);
    if (bar && m1_is_type(bar, "system_bar"))
        pal_bar_follow(
            bar); /* the real bar (not the pull-down's copy) repainted when the window in front is painted otherwise */
    if (!kill) peqout_sync(1); /* the per-output EQ follows Line Out and a USB DAC within a second (patch/peqout.c) */
    lo_eq(parent, kill); /* after the sync above, which can turn the switch for the new output */
    pill = widget_lookup(parent, LO_PILL, 0);
    if (!pill) return r; /* no pill in this bar: stock's "LO" text stays */
    if (text && text[0] == 'L' && text[1] == 'O' && !text[2] && !kill) {
        m1_show(label, 0);
        m1_show(pill, 1);
    } else {
        m1_show(label, 1);
        m1_show(pill, 0);
    }
    return r;
}
