/* Battery Percentage (patch/battery.c, docs/modules/battery.md "The percentage"): constants the payload and test/pod/battery.py share.
 * The test parses the #defines in this file, so a change cannot leave the mocks behind.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define BP_FILE \
    "/mnt/data/m1plus/battery-percentage" /* "1" = on, anything else or missing = off (Settings > Battery) */
#define BP_GAUGE \
    "/sys/class/power_supply/battery/capacity" /* the AXP2101 fuel gauge: an integer 0..100 and a newline */
#define BP_VOLT \
    "/sys/class/power_supply/battery/voltage_now" /* microvolts and a newline: read only when the gauge says 0 */
#define BP_EMPTY_UV \
    3535001 /* below this, stock's get_battery_capacity buckets the battery as 0 (0x35f099 at 0x4e6ec4): a gauge 0 is believed */
#define BP_LABEL "pod_pct" /* the hidden number in the status bar's battery (tools/statusbar.py battery_parts) */
#define BP_LABEL_DD "pod_pct_dd" /* its twin in the pull-down's own bar (dropdown_dialog.bin) */
#define BP_LABEL_LK "pod_pct_lk" /* the lock screen's (tools/mod_lockscreen.py) */
#define BP_BG "pod_pct_bg" /* the lighter grey under the level, shown with the number so that its black digits read */
#define BP_BG_DD "pod_pct_bg_dd"
#define BP_BG_LK "pod_pct_bg_lk"
#define BP_LEVEL "pod_chg_lvl" /* the green level over stock's white one, shown while charging */
#define BP_LEVEL_DD "pod_chg_lvl_dd"
#define BP_LEVEL_LK "pod_chg_lvl_lk"
#define BP_BOLT "pod_chg_bolt" /* the bolt in the body's middle: charging without the number */
#define BP_BOLT_DD "pod_chg_bolt_dd"
#define BP_BOLT_LK "pod_chg_bolt_lk"
#define BP_BOLT_S "pod_chg_bolts" /* the small bolt at the body's right end: charging with a one or two digit number */
#define BP_BOLT_S_DD "pod_chg_bolts_dd"
#define BP_BOLT_S_LK "pod_chg_bolts_lk"
#define BP_INK \
    0xff000000u /* the number's colour (0xAABBGGRR): black, as the asset has it (tools/statusbar.py PCT_RGB) */
#define BP_INK_CHG 0xffffffffu /* and white while charging, like the small bolt */
#define BP_W 26 /* the number's label: the body's width (tools/battery_art.py STATUS.body) */
#define BP_W_CHG 21 /* and while the small bolt shows (tools/battery_art.py PCT_W_CHG) */

#define BP_LOW \
    5 /* a gauge reading of at most this, on battery, is stored as 0: stock's red bar_lowpower (and its other low-battery readers) */

void bp_lock(
    void *win); /* the lock screen's init: show the percentage in its label at once (setting on, gauge readable) */
void bp_pulldown(void *dlg); /* the pull-down's init: the same for its label BP_LABEL_DD */
int battery_gauge(void); /* the gauge, 0..100, or -1 (patch/battery.c; the Charge Limit's input too) */
int bp_light_on(
    int level); /* the hooks at screen_action's two toolSetBackLight calls (tools/pod.py LIGHT_ON_SITE, LIGHT_OFF_SITE): repaint at once on wake */
int bp_light_off(int level);
