/* Charge Limit (patch/charging.c, docs/modules/charging.md): constants the payload and test/pod/charging.py share.
 * The test parses the #defines in this file, so a change cannot leave the mocks behind.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define CHG_FILE \
    "/mnt/data/m1plus/battery-charge-limit" /* one character: '0'..'3' = 80, 85, 90, 95 %; anything else or missing = 100 % (no limit) */
#define CHG_SWITCH \
    "/sys/class/power_supply/battery/charger" /* the AXP2101 driver's charging request: "0" stops charging, "1" restores the configured current */

#define CHG_MIN 80 /* the lowest limit; the picker steps by CHG_STEP up to CHG_OFF */
#define CHG_STEP 5
#define CHG_OFF 100 /* no limit (the default) */
#define CHG_RESUME 5 /* a held charger is released at limit - CHG_RESUME percent or less */
#define CHG_PERIOD 5 /* seconds between two checks on external power (the status bar ticks every second) */
#define CHG_IDLE \
    60 /* the worker's seconds between two checks on battery (nothing to hold; a plug-in is seen within this) */

int chg_limit(void); /* the saved limit, CHG_MIN .. CHG_OFF */
int chg_set(int limit); /* save and apply a limit: the limit, or -1 */
void chg_tick(int killed, int pct); /* from bp_capacity (patch/battery.c) every status bar tick */
void *chg_main(
    void *
        arg); /* the worker's loop (public so that the test runs it): a check every CHG_PERIOD seconds (CHG_IDLE on battery) while a limit or a hold exists */
