/* M1+ Music Battery Percentage: the fuel gauge's exact charge, as a number in the battery (docs/modules/battery.md "The percentage").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Stock never reads the AXP2101 gauge: get_battery_capacity (0x4e6dd8) buckets the battery voltage into 0/20/40/60/80/100 (another table, and a +10 animation, while
 * charging) and leaves the result in the global power_capacity (0xa059ec), which show_sysbar_face (0x544b48, the status bar's 1 s timer) and the pull-down's face read
 * for the fill; the return value is dropped there. The one hook is the call-site word `jalr get_battery_capacity` at 0x5450f8 in show_sysbar_face, now `jal bp_capacity`.
 * bp_capacity runs stock's function first, and then, only while Settings > Battery > Battery Percentage is on and the kill switch /mnt/mmc/m1plus-off is absent and
 * /sys/class/power_supply/battery/capacity reads a plain integer 0..100, stores that percentage in power_capacity (so the fill, the charging picture's fill and the
 * pull-down's bar use the real level, charging included) and shows the number in the label pod_pct in the battery's body (its twin pod_pct_dd in the pull-down's bar), over the lighter grey pod_pct_bg.
 * At BP_LOW (5) percent or less on battery (and when stock's own bucket is 0) the stored value is 0, which is how stock's own test shows the red bar_lowpower (battery.md "BP_LOW").
 * The lock screen (screensaver_page) draws its gauge from the same power_capacity; its label pod_pct_lk is set by the same tick and, at once, by bp_lock at the page's init. The pull-down's label pod_pct_dd is set at once the same way, by bp_pulldown at its init.
 * In every other case the stock value stays and the labels are hidden (visible and sensitive off). The icon pictures stay stock's (charging, low). While stock shows the
 * charging picture, with or without the setting, the same tick shows the green level pod_chg_lvl over stock's white one and a bolt (bp_face; battery.md "Charging").
 * The same tick then runs the Charge Limit's check (patch/charging.c chg_tick: the kill switch and, when it was read here, the gauge).
 * Two more hooks, the call-site words `jalr toolSetBackLight` at 0x4e71cc (on) and 0x4e71fc (off) in screen_action (0x4e71a4), now `jal bp_light_on` / `jal bp_light_off`, repaint the
 * status bar when the screen wakes (battery.md "The wake repaint"): cost on a wake only (one access, ~34 ms), none while the screen stays lit.
 *
 * Cost: one access (the kill switch), and, with the setting on, one open / read / close of a 4 byte file and a few lookups in the small status bar tree per second; the setting
 * is cached (read at the first tick, kept by the Settings switch). Not on the boot path (tools/reach.py), but the first call comes with the status bar window at UI start, so with the setting off (the default) it adds only stock's own call, the access and the cached flag.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "battery.h"
#include "charging.h"
#include "batthist.h"
#include "scrobble.h"

static struct {
    int state; /* the setting: 0 not read yet, 1 off, 2 on */
    int shown; /* a label may be showing: the hide path has work to do */
    int chg; /* the charging look may be showing: the same */
    int white; /* bitmask (1 bar, 2 pull-down, 4 lock): that face's label was painted white and has not been reset to black yet */
    int dark; /* the backlight went off (bp_light_off) and has not come on since: the wake repaint is due */
} bp __attribute__((section(".scratch")));

static int bp_read_setting(void) { return set_read(BP_FILE, 0) == '1'; }

/* Settings > Battery > Battery Percentage: 1 on, 0 off (the default). */
int battpct_setting(void) { return bp_read_setting(); }

int battpct_toggle(void) {
    int next = !bp_read_setting();
    if (home_set_digit(BP_FILE, next, 1) < 0) return -1;
    bp.state = next ? 2 : 1;
    return next;
}

/* The battery voltage (BP_VOLT, microvolts, the file stock's toolsGetBatteryVoltage reads) is below stock's empty level BP_EMPTY_UV: 1, else 0 (unreadable too). */
static int bp_volt_empty(void) {
    char b[12];
    int fd = open(BP_VOLT, O_RDONLY, 0), n, i = 0, v = 0;
    if (fd < 0) return 0;
    n = read(fd, b, sizeof b - 1);
    close(fd);
    while (i < n && b[i] >= '0' && b[i] <= '9' && i < 8) v = v * 10 + (b[i++] - '0');
    if (i == 0 || i > 7 || (i < n && b[i] != '\n')) return 0;
    return v < BP_EMPTY_UV;
}

/* The gauge as a plain integer 0..100 (digits, then the end or a newline): the value, else -1. Also the Charge Limit's input (patch/charging.c). A 0 is believed only
 * while the voltage says empty: an uncalibrated gauge reads 0 with a healthy battery (issue 19, battery.md "A zero gauge"). */
int battery_gauge(void) {
    char b[8];
    int fd = open(BP_GAUGE, O_RDONLY, 0), n, i = 0, v = 0;
    if (fd < 0) return -1;
    n = read(fd, b, sizeof b - 1);
    close(fd);
    if (n < 1) return -1;
    b[n] = 0;
    while (i < n && b[i] >= '0' && b[i] <= '9' && i < 4) v = v * 10 + (b[i++] - '0');
    if (i == 0 || i > 3 || v > 100) return -1;
    if (i < n && b[i] == '\n') i++;
    if (i != n || (v == 0 && !bp_volt_empty())) return -1;
    return v;
}

/* Stock's three battery faces (show_sysbar_face 0x54510c..0x54514c, dropdown_showface, the lock screen) leave the low / normal test for the charging pictures: 1, else 0. */
static int bp_external(void) {
    return *(int *)POWER_EXT == 1 &&
           !(*(int *)POWER_USBSTATE == 2 && *(char *)POWER_FLAG == 1 && *(int *)USBDAC_CHARGEFLAG == 0);
}

/* Stock's faces show the charging picture (external power and not full: 0x5452e4..0x54535c): 1, else 0. */
static int bp_charging(void) { return bp_external() && *(int *)PMUCHARGE_STATUS != 2; }

#define BP_NAMES(s) BP_LABEL##s, BP_BG##s, BP_LEVEL##s, BP_BOLT##s, BP_BOLT_S##s

/* One battery of root (BP_NAMES: the status bar's, the pull-down's or the lock screen's). The percentage in the label `name` (the number as its text) over the lighter grey
 * `bg`, or both hidden for pct < 0 (while chg the number is white over the body's own darker grey, without `bg`). While chg (stock shows the charging picture): the green level `lvl` with power_capacity's value over stock's white one, and a bolt:
 * `bolt` in the body's middle without the number, the small `bolt_s` right of a number of one or two digits, whose label is BP_W_CHG wide then (BP_W otherwise).
 * Everything stays insensitive. */
static void bp_face(void *root, const char *name, const char *bg, const char *lvl, const char *bolt, const char *bolt_s,
                    int mask, int pct, int chg) {
    char t[4];
    int n = 0, small = chg && pct >= 0 && pct < 100, width;
    void *w = root ? widget_lookup(root, name, 1) : (void *)0, *b;
    if (!w) return;
    if ((b = widget_lookup(root, bg, 1))) widget_set_visible(b, pct >= 0 && !chg, 0);
    if ((b = widget_lookup(root, lvl, 1))) {
        if (chg) widget_set_prop_int(b, "value", *(int *)POWER_CAPACITY);
        widget_set_visible(b, chg, 0);
    }
    if ((b = widget_lookup(root, bolt, 1))) widget_set_visible(b, chg && pct < 0, 0);
    if ((b = widget_lookup(root, bolt_s, 1))) widget_set_visible(b, small, 0);
    if (pct < 0) {
        widget_set_visible(w, 0, 0);
        return;
    }
    width = *(int *)((char *)w + 8); /* widget_t.w (BATTERY_PINS) */
    if (small ? width != BP_W_CHG : width == BP_W_CHG)
        widget_resize(w, small ? BP_W_CHG : BP_W, *(int *)((char *)w + 12));
    if (pct >= 100)
        t[n++] = '1', t[n++] = '0', t[n++] = '0';
    else {
        if (pct >= 10) t[n++] = (char)('0' + pct / 10);
        t[n++] = (char)('0' + pct % 10);
    }
    t[n] = 0;
    if (chg ||
        (bp.white & mask)) { /* white digits while charging, black again whenever this face next shows on battery */
        unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
        memset(v, 0, sizeof v);
        value_set_uint32(v, chg ? BP_INK_CHG : BP_INK);
        widget_set_style(w, "normal:text_color", v);
        if (chg)
            bp.white |= mask;
        else
            bp.white &= ~mask;
    }
    widget_set_text_utf8(w, t);
    widget_set_visible(w, 1, 0);
}

/* A page's battery at its init (after stock's init and only without the kill switch): the percentage and the charging look at once, where the status bar's tick would show
 * them up to a second later. All of it is hidden in the asset, so on battery with the setting off or an unreadable gauge nothing is touched. */
static void bp_init_face(void *win, const char *name, const char *bg, const char *lvl, const char *bolt,
                         const char *bolt_s, int mask) {
    int pct = -1, chg = bp_charging();
    if (bp.state == 0) bp.state = bp_read_setting() ? 2 : 1;
    if (bp.state == 2) pct = battery_gauge();
    if (pct < 0 && !chg) return;
    bp_face(win, name, bg, lvl, bolt, bolt_s, mask, pct, chg);
    if (pct >= 0) bp.shown = 1;
    if (chg) bp.chg = 1;
}

/* The lock screen's battery (patch/lockscreen.c). */
void bp_lock(void *win) { bp_init_face(win, BP_NAMES(_LK), 4); }

/* The pull-down's battery (patch/pulldown.c m1plus_pulldown_init). */
void bp_pulldown(void *dlg) { bp_init_face(dlg, BP_NAMES(_DD), 2); }

/* The hook (tools/pod.py BATTERY_SITE): stock's get_battery_capacity, then the real percentage when asked for. Returns what stock's function returned, or the percentage. */
int bp_capacity(void) {
    int cap = get_battery_capacity(), pct = -1, killed = access(KILL_SD, F_OK) == 0;
    int chg = !killed && bp_charging(); /* get_battery_capacity has just refreshed the power state */
    void *bar, *wm;
    if (!killed) {
        if (bp.state == 0) bp.state = bp_read_setting() ? 2 : 1;
        if (bp.state == 2) pct = battery_gauge();
    }
    chg_tick(killed, pct); /* the Charge Limit (patch/charging.c), on the same tick */
    if (!killed) bh_poll(); /* Battery History (patch/batthist.c): starts its recorder thread while the setting is on */
    if (!killed)
        scrobble_auto_tick(); /* the automatic scrobble upload (patch/scrobble.c): a compare while Auto Upload is off */
    if (pct < 0 && !bp.shown && !chg && !bp.chg)
        return cap; /* off, on battery and nothing to hide: stock, no lookups */
    if (pct >= 0) {
        /* stock picks bar_lowpower only for power_capacity <= 0, and only when it reaches that test (not on the charging / full pictures: show_sysbar_face 0x54510c..0x54514c) */
        *(int *)POWER_CAPACITY = cap = !bp_external() && (pct <= BP_LOW || cap <= 0) ? 0 : pct;
    }
    if (bp.dark && !*(volatile unsigned char *)BACKLIGHT_STATUS)
        return cap; /* the screen is off: no lookups, no labels (the wake repaint's call below shows them before the backlight comes on) */
    bar = *(void **)SYSTEM_BAR;
    bp_face(bar, BP_NAMES(), 1, pct, chg);
    wm = window_manager();
    bp_face(wm, BP_NAMES(_DD), 2, pct, chg);
    bp_face(wm, BP_NAMES(_LK), 4, pct, chg);
    bp.shown = pct >= 0;
    bp.chg = chg;
    return cap;
}

/* The wake repaint (tools/pod_pins.py LIGHT_ON_SITE / LIGHT_OFF_SITE): screen_action's two toolSetBackLight calls, the one place every path (awake_screen, the power key) turns the backlight
 * on or off. Off: remember it (bp.dark). On, after an off: before the backlight comes on, on the UI thread, show_sysbar_face(0) (the status bar's own timer call; it runs bp_capacity, so the
 * battery labels follow), widget_invalidate_force(wm, null) (the whole screen dirty), then the main loop's own pair window_manager_check_and_layout (a label whose width
 * changed asks its group to lay out again) and window_manager_paint, so the first frame the panel shows is a fresh one. A screen_action(1)
 * while lit paints nothing. The kill switch present: toolSetBackLight only. */
int bp_light_on(int level) {
    int dark = bp.dark;
    bp.dark = 0; /* (first: bp_capacity skips the faces while it is set) */
    if (dark && access(KILL_SD, F_OK) != 0) {
        void *wm = window_manager();
        show_sysbar_face(0);
        if (wm) widget_invalidate_force(wm, (void *)0), window_manager_check_and_layout(wm), window_manager_paint(wm);
    }
    return toolSetBackLight(level);
}

int bp_light_off(int level) {
    bp.dark = 1;
    return toolSetBackLight(level);
}
