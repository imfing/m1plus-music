/* M1+ Music Charge Limit: charging pauses at a chosen percentage while the player runs (docs/modules/charging.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Settings > Battery > Charge Limit picks 80, 85, 90, 95 or 100 % (100, the default, is no limit). The stock kernel's AXP2101 driver has a
 * charging request, /sys/class/power_supply/battery/charger: "0" sets its disable flag and zero charging current, "1" restores the configured current.
 * Two callers run the same check, serialised by a spin lock (the status bar's try-lock simply skips a tick while the worker holds it): bp_capacity (patch/battery.c, the hook on the status bar's 1 s call
 * of get_battery_capacity) calls chg_tick after stock's function, and chg_tick checks at most every CHG_PERIOD seconds of its own (time(); a clock that went back, or a release the worker left to it, checks at once); and one detached worker
 * thread (chg_main) checks every CHG_PERIOD seconds on its own (CHG_IDLE when its last check saw no external power), which covers the screen off and stock's standby (userspace still runs; the status bar does not tick). The worker is started by chg_tick /
 * chg_set while a limit under 100 is set, and ends when the limit is 100 or the kill switch is there (a hold is then the tick's to release).
 * External power is pwr_external (patch/power.c: battery/status, the online files and the raw PD17 level, any one saying external wins) or stock's POWER_EXT word equal to 1.
 *
 * A check reads the AXP2101 gauge (/sys/class/power_supply/battery/capacity, the real percentage; stock's power_capacity is a voltage bucket) and:
 *   - on external power with no hold of ours, a gauge at or over the limit writes "0" (the hold);
 *   - while held, a gauge at limit - CHG_RESUME or less writes "1" (the release); in between, the switch is read and a "1" (stock enabled charging again:
 *     the USB page's exit, the DAC toggle) writes "0" again;
 *   - stock's USB DAC mode with its charging choice off owns the switch (stock wrote "0" itself and writes "1" when the mode ends): the hold is forgotten,
 *     nothing is written;
 *   - the limit set to 100, the kill switch /mnt/mmc/m1plus-off, no external power or an unreadable gauge release a hold of ours. The worker never writes
 *     "1": the release is the status bar tick's (the UI thread, as stock's DAC toggle and USB page), so with the screen off it waits for the next tick.
 * Only a hold this file made is ever released, so "1" is written only after our own "0". A failed write keeps the old state and is tried again at the
 * next check. A reboot clears the driver's flag. Not covered: a real kernel suspend (no userspace runs, so a limit crossed meanwhile is only held after the wake) and
 * a powered-off player (the kernel's shutdown path selects its charging current without the flag), which charge as stock does.
 *
 * Cost with no limit (the default) and no hold: a cached compare, no call, no thread. With a limit: a time() per tick, and every CHG_PERIOD seconds (the worker's CHG_IDLE on battery) a few
 * open / read / close of the power sources, the gauge and, while held, of the switch, and a write on a change.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "battery.h"
#include "charging.h"
#include "power.h"

static struct {
    volatile int lock;
    int limit; /* 0: not read yet, else CHG_MIN .. CHG_OFF */
    int held; /* 1: we wrote "0" to the switch and have not released it */
    int checked; /* a check ran: last is its time */
    int now; /* the next tick checks whatever the time (a new limit, or a release the worker left to it) */
    long last; /* the status bar tick's last check (the worker's checks never move it) */
    int run; /* the worker runs (or is being made) */
    int retry; /* status bar ticks to wait before another try to make the worker */
    int ext; /* the last check saw external power (the worker's sleep: CHG_PERIOD, else CHG_IDLE) */
} chg __attribute__((section(".scratch")));

static void chg_lock(void) {
    while (__sync_lock_test_and_set(&chg.lock, 1)) {
    }
}
static int chg_trylock(void) { return !__sync_lock_test_and_set(&chg.lock, 1); }
static void chg_unlock(void) { __sync_lock_release(&chg.lock); }

static int chg_read(void) {
    int c = set_read(CHG_FILE, 0);
    return c >= '0' && c <= '0' + (CHG_OFF - CHG_MIN) / CHG_STEP - 1 ? CHG_MIN + (c - '0') * CHG_STEP : CHG_OFF;
}

/* Settings > Battery > Charge Limit: the saved limit, CHG_MIN .. CHG_OFF (CHG_OFF: no limit). */
int chg_limit(void) {
    if (!chg.limit) chg.limit = chg_read();
    return chg.limit;
}

static void chg_start(void);

/* Choose a limit (the picker's rows: CHG_MIN .. CHG_OFF in CHG_STEP steps); saved atomically first, then the next tick checks at once. The limit or -1. */
int chg_set(int limit) {
    if (limit < CHG_MIN || limit > CHG_OFF || (limit - CHG_MIN) % CHG_STEP) return -1;
    if (home_set_digit(CHG_FILE, (limit - CHG_MIN) / CHG_STEP, 9) < 0) return -1;
    chg_lock();
    chg.limit = limit;
    chg.now = 1, chg.retry = 0;
    chg_unlock();
    if (limit < CHG_OFF) chg_start();
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

/* Every release goes through here: while stock owns the switch the hold is only forgotten, never "1" written over the user's choice. The "1" is written only
 * from the status bar's tick (ui), the thread of stock's DAC toggle and USB page, so the test and the write cannot straddle the user's change; the worker
 * only forgets, and leaves the release to the next tick. */
static void chg_release(int ui) {
    if (!chg.held) return;
    if (chg_dac_off())
        chg.held = 0;
    else if (!ui)
        chg.now = 1; /* the next tick, without its CHG_PERIOD wait */
    else if (chg_write(1) == 0)
        chg.held = 0;
}

/* External power for the limit: any source of patch/power.c, or stock's POWER_EXT word (what the status bar last saw) equal to 1. */
static int chg_external(void) { return *(int *)POWER_EXT == 1 || pwr_external() == 1; }

/* One check (under the lock). killed: the kill switch is there; pct: the gauge if the caller has it, else -1; force: the worker's, no CHG_PERIOD wait. */
static void chg_step(int killed, int pct, int force) {
    long t;
    if (killed) {
        chg_release(!force);
        return;
    }
    if (chg_limit() >= CHG_OFF && !chg.held) return;
    t = time((long *)0);
    if (!force) {
        if (chg.checked && !chg.now && t >= chg.last && t - chg.last < CHG_PERIOD) return;
        chg.checked = 1, chg.now = 0, chg.last = t;
    }
    chg.ext = 0;
    if (chg.limit >= CHG_OFF || chg_dac_off() || !(chg.ext = chg_external())) {
        chg_release(!force); /* (with stock owning the switch: the hold forgotten, nothing written) */
        return;
    }
    if (pct < 0) pct = battery_gauge();
    if (pct < 0) {
        chg_release(!force);
        return;
    }
    if (chg.held) {
        if (pct <= chg.limit - CHG_RESUME)
            chg_release(!force);
        else if (chg_state() != 0)
            chg_write(0); /* stock enabled charging again (or the switch reads oddly): hold again */
    } else if (pct >= chg.limit && chg_write(0) == 0)
        chg.held = 1;
}

/* The worker: a check every CHG_PERIOD seconds on external power, CHG_IDLE on battery, until the limit is 100 or the kill switch is there. */
void *chg_main(void *arg) {
    (void)arg;
    for (;;) {
        int killed = access(KILL_SD, F_OK) == 0, done, ext;
        chg_lock();
        chg_step(killed, -1, 1);
        ext = chg.ext;
        done = chg_limit() >= CHG_OFF || killed; /* (a hold is the status bar tick's to release) */
        if (done) chg.run = 0;
        chg_unlock();
        if (done) return (void *)0;
        sleep(ext ? CHG_PERIOD : CHG_IDLE);
    }
}

static void chg_start(void) {
    unsigned long th = 0;
    if (chg.run) return;
    if (chg.retry) {
        chg.retry--;
        return;
    }
    chg_lock();
    if (chg.run) {
        chg_unlock();
        return;
    }
    chg.run = 1;
    chg_unlock();
    if (pthread_create(&th, (const void *)0, chg_main, (void *)0)) {
        chg.run = 0, chg.retry = 30;
        return;
    }
    pthread_detach(th);
}

/* From bp_capacity, after stock's get_battery_capacity. killed: the kill switch is there; pct: the gauge if bp_capacity read it, else -1. */
void chg_tick(int killed, int pct) {
    if (killed) {
        if (chg.held && chg_trylock()) chg_release(1), chg_unlock();
        return;
    }
    if (chg_limit() >= CHG_OFF && !chg.held) return;
    if (chg.limit < CHG_OFF) chg_start();
    if (!chg_trylock()) return; /* the worker is checking */
    chg_step(0, pct, 0);
    chg_unlock();
}
