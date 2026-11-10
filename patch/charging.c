/* M1+ Music Charge Limit: charging pauses at a chosen percentage while the player runs (docs/modules/charging.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Settings > System > Battery > Charge Limit picks 80, 85, 90, 95 or 100 % (100, the default, is no limit). The stock kernel's AXP2101 driver has a
 * charging request, /sys/class/power_supply/battery/charger: "0" sets its disable flag and zero charging current, "1" restores the configured current.
 * There is no timer of ours: bp_capacity (patch/battery.c, the hook on the status bar's 1 s call of get_battery_capacity) calls chg_tick after stock's
 * function, and chg_tick checks at most every CHG_PERIOD seconds (time(); a clock that went back checks at once).
 *
 * A check reads the AXP2101 gauge (/sys/class/power_supply/battery/capacity, the real percentage; stock's power_capacity is a voltage bucket) and:
 *   - on external power with no hold of ours, a gauge at or over the limit writes "0" (the hold);
 *   - while held, a gauge at limit - CHG_RESUME or less writes "1" (the release); in between, the switch is read and a "1" (stock enabled charging again:
 *     the USB page's exit, the DAC toggle) writes "0" again;
 *   - stock's USB DAC mode with its charging choice off owns the switch (stock wrote "0" itself and writes "1" when the mode ends): the hold is forgotten,
 *     nothing is written;
 *   - the limit set to 100, the kill switch /mnt/mmc/m1plus-off, no external power or an unreadable gauge release a hold of ours.
 * Only a hold this file made is ever released, so "1" is written only after our own "0". A failed write keeps the old state and is tried again at the
 * next check. A reboot clears the driver's flag. Not covered: the status bar not ticking (show_sysbar_face returns early while standby_mode is 2) and
 * a powered-off player (the kernel's shutdown path selects its charging current without the flag), which charge as stock does.
 *
 * Cost with no limit (the default) and no hold: a cached compare, no call. With a limit: a time() per tick, and every CHG_PERIOD seconds at most one
 * open / read / close of the gauge and, while held, of the switch, and a write on a change.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "battery.h"
#include "charging.h"

static struct {
    int limit; /* 0: not read yet, else CHG_MIN .. CHG_OFF */
    int held; /* 1: we wrote "0" to the switch and have not released it */
    int checked; /* a check ran: last is its time */
    int now; /* the next tick checks whatever the time (a new limit) */
    long last;
} chg __attribute__((section(".scratch")));

static int chg_read(void) {
    int c = set_read(CHG_FILE, 0);
    return c >= '0' && c <= '0' + (CHG_OFF - CHG_MIN) / CHG_STEP - 1 ? CHG_MIN + (c - '0') * CHG_STEP : CHG_OFF;
}

/* Settings > System > Battery > Charge Limit: the saved limit, CHG_MIN .. CHG_OFF (CHG_OFF: no limit). */
int chg_limit(void) {
    if (!chg.limit) chg.limit = chg_read();
    return chg.limit;
}

/* Choose a limit (the picker's rows: CHG_MIN .. CHG_OFF in CHG_STEP steps); saved atomically first, then the next tick checks at once. The limit or -1. */
int chg_set(int limit) {
    char t[3];
    if (limit < CHG_MIN || limit > CHG_OFF || (limit - CHG_MIN) % CHG_STEP) return -1;
    t[0] = (char)('0' + (limit - CHG_MIN) / CHG_STEP), t[1] = '\n', t[2] = 0;
    if (home_write_atomic(CHG_FILE, CHG_TMP, t) != 0) return -1;
    chg.limit = limit;
    chg.now = 1;
    return limit;
}

/* Write the charging request: 0 on success. */
static int chg_write(int on) {
    int fd = open(CHG_SWITCH, O_WRONLY, 0), n;
    if (fd < 0) return -1;
    n = write(fd, on ? "1\n" : "0\n", 2);
    close(fd);
    return n == 2 ? 0 : -1;
}

/* The switch as the driver reports it: 0 (disabled), 1 (enabled), or -1 unreadable. */
static int chg_state(void) {
    char b[4];
    int fd = open(CHG_SWITCH, O_RDONLY, 0), n;
    if (fd < 0) return -1;
    n = read(fd, b, sizeof b - 1);
    close(fd);
    if (n < 1 || (b[0] != '0' && b[0] != '1') || (n > 1 && b[1] != '\n') || n > 2) return -1;
    return b[0] - '0';
}

/* Stock's USB DAC mode with its charging choice off (show_sysbar_face's own test, patch/battery.c): stock wrote "0" itself and owns the switch. */
static int chg_dac_off(void) {
    return *(int *)POWER_USBSTATE == 2 && *(char *)POWER_FLAG == 1 && *(int *)USBDAC_CHARGEFLAG == 0;
}

/* Every release goes through here: while stock owns the switch the hold is only forgotten, never "1" written over the user's choice. */
static void chg_release(void) {
    if (!chg.held) return;
    if (chg_dac_off() || chg_write(1) == 0) chg.held = 0;
}

/* From bp_capacity, after stock's get_battery_capacity. killed: the kill switch is there; pct: the gauge if bp_capacity read it, else -1. */
void chg_tick(int killed, int pct) {
    long t;
    if (killed) {
        chg_release();
        return;
    }
    if (chg_limit() >= CHG_OFF && !chg.held) return;
    t = time((long *)0);
    if (chg.checked && !chg.now && t >= chg.last && t - chg.last < CHG_PERIOD) return;
    chg.checked = 1, chg.now = 0, chg.last = t;
    if (chg.limit >= CHG_OFF || *(int *)POWER_EXT != 1 || chg_dac_off()) {
        chg_release(); /* (with stock owning the switch: the hold forgotten, nothing written) */
        return;
    }
    if (pct < 0) pct = battery_gauge();
    if (pct < 0) {
        chg_release();
        return;
    }
    if (chg.held) {
        if (pct <= chg.limit - CHG_RESUME)
            chg_release();
        else if (chg_state() != 0)
            chg_write(0); /* stock enabled charging again (or the switch reads oddly): hold again */
    } else if (pct >= chg.limit && chg_write(0) == 0)
        chg.held = 1;
}
