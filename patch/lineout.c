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
 * The same call also hides the screenshot camera pod_shot when the row loses its room (lo_shot), toggles the status bar's sync icon pod_sync (lo_sync) from one volatile flag of patch/covercache.c, and the Sleep Timer moon pod_sleep (lo_sleep). Cost: one access and a few lookups by name per second per bar
 * (six or seven more while the camera, a build or a Sleep Timer shows, for the room test); no allocation, no state. Not on the boot path. On the real bar it also lets the palette repaint the bar when the window in front
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

/* A visible peer in the bar's right group: its box and the gap before it; 0 when absent or hidden. */
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
    if (!strcmp(n, SLEEP_BT_APTX)) return SLEEP_INK_APTX;
    if (!strcmp(n, SLEEP_BT_APTXHD)) return SLEEP_INK_APTXHD;
    return ((int *)bt)[W_W / 4];
}

/* Room for a mark of the right group (lineout.h BAR_ROOM_12H / BAR_ROOM_24H, by stock's 24-Hour Time byte): the mark's box, every visible peer above it, the Wi-Fi glyph and the Bluetooth box's ink stay within
 * the room left of the clock. `rank` orders the marks that yield: stock's SyncLink (LO_RANK_LINK) counts Bluetooth and Wi-Fi only, the camera (LO_RANK_SHOT) SyncLink too, the sync icon (LO_RANK_SYNC) the
 * camera too, the moon (LO_RANK_MOON) the sync icon too; so the moon yields first and SyncLink last. */
#define LO_RANK_LINK 0
#define LO_RANK_SHOT 1
#define LO_RANK_SYNC 2
#define LO_RANK_MOON 3
static int lo_fits(void *bar, void *ind, int rank) {
    void *bt = widget_lookup(bar, SLEEP_BT, 1);
    int used = ((int *)ind)[W_W / 4];
    used += lo_peer(bar, SLEEP_WIFI);
    if (rank > LO_RANK_LINK) used += lo_peer(bar, SLEEP_SYNCLINK);
    if (rank > LO_RANK_SHOT) used += lo_peer(bar, SLEEP_SHOT);
    if (rank > LO_RANK_SYNC) used += lo_peer(bar, SYNC_IND);
    if (bt && widget_get_visible(bt)) used += SLEEP_GAP + lo_bt_ink(bt);
    return used <= (*(volatile unsigned char *)TIME_24H ? BAR_ROOM_24H : BAR_ROOM_12H);
}

/* Hook 40 (tools/pod_pins.py SYNCLINK_SITES): stock's widget_set_visible(img_synclink, 1) in both bars' face ticks, which run it after setting the Bluetooth image. SyncLink yields when stock's own marks would run
 * into the centred clock (only aptX HD + SyncLink + Wi-Fi under a 12 h clock: 82 px of 77): hidden and insensitive, else shown and sensitive. Hiding, or no group, or the kill switch: stock's call. Wi-Fi's
 * visibility is the previous tick's (stock sets it next), so a change there reaches SyncLink one tick late. */
int lo_link_show(void *w, int on, int recursive) {
    void *group = w ? (void *)((int *)w)[LO_W_PARENT / 4] : (void *)0;
    if (!on || !group || access(KILL_SD, F_OK) == 0) return widget_set_visible(w, on, recursive);
    m1_show(w, lo_fits(group, w, LO_RANK_LINK));
    return RET_OK;
}

/* patch/shot.c, as the countdown shows the camera: room beside stock's marks in its group (view_bar_right holds every peer); no group, room. */
int lo_shot_fits(void *ind) {
    void *group = (void *)((int *)ind)[LO_W_PARENT / 4];
    return !group || lo_fits(group, ind, LO_RANK_SHOT);
}

/* The screenshot camera while it counts: hidden if the row loses its room (a Bluetooth badge appears). Only ever hides; patch/shot.c shows it and hides it before the grab. */
static void lo_shot(void *bar) {
    void *ind = widget_lookup(bar, SLEEP_SHOT, 1);
    if (ind && widget_get_visible(ind) && !lo_fits(bar, ind, LO_RANK_SHOT)) widget_set_visible(ind, 0, 0);
}

/* The sync icon (docs/modules/lineout.md "Sync icon"): pod_sync in the bar's right group, shown while the cover worker has a cover or duration set with work left (cc_build_active: volatile reads, no lock, no file),
 * the kill switch is absent and the row has room for it (lo_fits). `parent` is label_volume's parent (view_bar_left); the bar is its parent. Set only when it changes, so a steady state costs no relayout.
 * A bar without the widget is left alone. Runs before lo_sleep, which counts it. */
static void lo_sync(void *parent, int kill) {
    void *bar = (void *)((int *)parent)[LO_W_PARENT / 4], *ind;
    int on = !kill && cc_build_active();
    if (!bar) return;
    ind = widget_lookup(bar, SYNC_IND, 1);
    if (!ind) return;
    if (on) on = lo_fits(bar, ind, LO_RANK_SYNC);
    if (!widget_get_visible(ind) != !on) m1_show(ind, on);
}

/* The sleep timer icon (docs/modules/lineout.md "Sleep Timer icon"): pod_sleep in the bar's right group, shown while stock's sleep timer is running (sleepflag != 0 and sleep_time > 0, the same test
 * patch/sleeptimer.c uses), the kill switch is absent and the row has room for it (lo_fits). Stock sets the Bluetooth image on the same tick, possibly after this
 * call, so a change there reaches the moon one tick late. Set only when it changes, so a steady state costs no relayout. A bar without the widget is left alone. */
static void lo_sleep(void *bar, int kill) {
    void *ind;
    int on = !kill && *(volatile unsigned char *)SLEEP_FLAG != 0 && *(volatile int *)SLEEP_TIME > 0;
    if (!bar) return;
    ind = widget_lookup(bar, SLEEP_IND, 1);
    if (!ind) return;
    if (on) on = lo_fits(bar, ind, LO_RANK_MOON);
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
    bar = (void *)((int *)parent)[LO_W_PARENT / 4];
    if (bar)
        lo_shot(bar); /* our marks by rank: the camera, the sync icon, then the moon, each counting the ones before */
    lo_sync(parent, kill);
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
