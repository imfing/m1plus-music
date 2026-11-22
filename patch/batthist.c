/* M1+ Music Battery History: the last 24 hours of battery level and use, recorded by a thread of its own (docs/modules/batthist.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opt-in: Settings > Battery > Battery History (BH_FILE, off by default). While it is on one detached thread (bh_main) wakes every BH_PERIOD seconds (waiting in 1 s steps, and early when the History page asks: bh_request) and takes a sample:
 * the wall clock, CLOCK_MONOTONIC and CLOCK_BOOTTIME, the backlight byte (m1_screen_lit), stock's play state (mclGetPlayStatus == MB_PLAYING: a plain load of the word
 * the lock screen and the VU page read) and external power (patch/power.c pwr_external: the status text, the online files, the raw PD17 level; any source saying external counts); every BH_GAUGE seconds, and at once after a standby, also the AXP2101 gauge (battery_gauge). The thread
 * is not the status bar's tick on purpose: show_sysbar_face returns early in stock's standby (with the screen merely dark it keeps ticking, as the wake probe's logs show). The thread is started by
 * bh_poll (called from bp_capacity, patch/battery.c, with the kill switch absent: a cached compare per tick while the setting is off, no hook of its own) and by the switch.
 * It ends when the setting file says off (Reset All Settings deletes it too), after deleting the data.
 *
 * The ring: BH_BUCKETS buckets of BH_SECS wall-clock seconds (bucket number = wall / BH_SECS, slot = number % BH_BUCKETS), 8 bytes each (struct bh_bucket): the gauge at the bucket's
 * end, flags (BH_F_CHG on external power, BH_F_GAP no data), screen-on, playing-with-the-screen-off and known time in 8 s units, and the percent the gauge fell attributed to
 * screen on / playing with the screen off / idle-standby. Time is added from the clocks' differences, not from the sleep: awake = BOOTTIME - suspended, suspended = BOOTTIME -
 * MONOTONIC (MONOTONIC stops in suspend, BOOTTIME does not; at least BH_SUSP s counts). The awake part gets the state of the sample (screen on > playing > idle); the suspended
 * part is idle time, spread over the buckets of the wall-clock span it covered (the buckets nobody sampled still say "standby" that way).
 * Drops: while on battery the seconds per state are summed since the last drop; a gauge read that is lower than the last one gives the whole drop to the state with the most
 * seconds (screen on, then playing, then idle on a tie), and clears the sums; with BH_SUSP_DROP seconds or more of standby since the last read the drop is the standby's. On external
 * power the sums are cleared and nothing is attributed (BH_F_CHG, when charging was seen at any sample of the bucket); a rise is just a new level.
 * Time: the wall clock decides the bucket. BOOTTIME and the wall clock differing by more than BH_JUMP in one step: wall ahead = the clock was set forward, the buckets in between stay
 * BH_F_GAP; wall behind (or the buckets' numbers going back by 2 or more) = the history is dropped. A wall clock before BH_MIN_WALL is an unset RTC: nothing is recorded until it is set.
 * A reboot is found by the file: its newest bucket is older than now, so the buckets between are BH_F_GAP; a newest bucket in the future drops the file.
 * Since the last charge: the header keeps unplug_at (wall time the charger was removed, 0 = none seen yet), the gauge then, and the seconds on battery since: sc_play (playing with the screen off),
 * sc_on (screen on) and sc_total (awake plus standby), and sc_d_on / sc_d_play / sc_d_idle (percent the gauge fell, attributed as the buckets' drops are). The external power -> battery step starts a new run (counters to 0, since_on 0);
 * the first sample whose status says Discharging with no run starts one too (since_on 1, recording began on battery); on external power the counters stand still; nothing counts before a run exists. They outlive the 24 hour ring and reboots (the time the player was off is not counted) and a clock set back (bh_clear_ring); only no file, a bad file or the setting off clears them (bh_clear).
 *
 * The file (BH_DATA): struct bh_file, magic, version, the newest bucket's number, the since-charge fields, a checksum and the ring in slot order:
 * 820 bytes, always. It is written (m1_save: tmp, fsync, rename) when a bucket has just been opened (at most every 15 minutes) and read once at the thread's start; magic, version,
 * size, checksum and every value are checked, a bad file is dropped. A power loss costs at most the open bucket, and the since-charge counters with it (up to 15 minutes of them). When the setting goes off the ring is cleared and the files unlinked;
 * a write that was running meanwhile deletes its file again.
 *
 * Locking: the ring and the sampler's state sit behind a spin lock held for a few instructions (no I/O inside, but the setting file's read when the thread ends); bh_snapshot copies the ring under it. The stock calls
 * (mclGetPlayStatus is `lw`, the backlight byte, the sysfs reads) are made outside it.
 *
 * Cost, setting off: bp_capacity's call of bh_poll, a cached compare. On: a thread with a few KB of stack, one wakeup per 15 s (two syscalls for the clocks, a sysfs status read), a gauge
 * read per minute, one 820 byte file write per quarter hour.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "battery.h"
#include "power.h"
#include "batthist.h"

#define BH_MAGIC 0x31534842 /* "BHS1" */
#define BH_VERSION 4
#define BH_COV_MAX 120 /* a bucket's known time in 8 s units can not exceed this (900 s is 113) */

struct bh_file {
    unsigned magic;
    unsigned short version, count;
    unsigned head; /* the newest bucket's number */
    unsigned unplug_at; /* wall time the charger was last removed, 0 unknown */
    unsigned unplug_lvl; /* the gauge then (BH_NONE unknown) */
    unsigned sc_play, sc_on,
        sc_total; /* seconds on battery since then: playing with the screen off, screen on, everything (standby included) */
    unsigned sc_d_on, sc_d_play,
        sc_d_idle; /* percent the gauge fell since then (0..100 each), attributed to the screen on / playing with the screen off / idle and standby */
    unsigned
        since_on; /* 0 the run began when the charger was removed, 1 at the first sample (recording started on battery) */
    unsigned sum;
    struct bh_bucket b[BH_BUCKETS]; /* slot order: bucket n is in b[n % BH_BUCKETS] */
};

static struct {
    volatile int lock;
    int state; /* the setting: 0 not read yet, 1 off, 2 on */
    int run; /* the thread runs (or is being made) */
    int retry; /* ticks to wait before another try to make the thread */
    int loaded; /* the file was read (or there was none) */
    int dirty; /* a bucket was opened: the file wants writing */
    volatile int want; /* the History page asks for a sample now (bh_request): the thread's wait ends early */
    volatile unsigned seq; /* samples taken (bumped under the lock): the page redraws when it moved */
    struct bh_bucket b[BH_BUCKETS];
    unsigned head; /* 0: the ring is empty */
    long
        unplug_at; /* since last charge: the run that began when the charger was removed (0: none seen yet, nothing counts) */
    unsigned unplug_lvl, sc_play, sc_on, sc_total, sc_d_on, sc_d_play, sc_d_idle, since_on;
    /* the sampler's state */
    int have; /* a baseline exists: the last* fields */
    long lwall, lmono, lboot, lgauge; /* the last sample's clocks, and BOOTTIME of the last gauge read */
    int glast; /* the last gauge reading on this baseline, -1 none */
    int chg; /* on external power at the last sample (kept when the status is unreadable) */
    int susp_g; /* standby seconds since the last gauge read */
    int rem[3]; /* seconds not yet a whole unit of 8: on, play, cov */
    int acc[3]; /* seconds on battery since the last drop: on, play, idle */
} bh __attribute__((section(".scratch")));

static void bh_lock(void) {
    while (__sync_lock_test_and_set(&bh.lock, 1)) {
    }
}
static void bh_unlock(void) { __sync_lock_release(&bh.lock); }

int bh_setting(void) { return set_read(BH_FILE, 0) == '1'; }

static struct bh_bucket *bh_slot(unsigned n) { return &bh.b[n % BH_BUCKETS]; }

static void bh_gap(struct bh_bucket *k) {
    memset(k, 0, sizeof *k);
    k->level = BH_NONE;
    k->flags = BH_F_GAP;
}

/* The sampler starts over (the ring is kept): no baseline, no gauge, no sums. */
static void bh_rebase(void) {
    bh.have = 0, bh.glast = -1, bh.susp_g = 0;
    memset(bh.rem, 0, sizeof bh.rem);
    memset(bh.acc, 0, sizeof bh.acc);
}

/* An empty ring and a new sampler (under the lock). The since-charge counters stay: they are seconds on battery, not wall time, so a clock set back does not touch them. */
static void bh_clear_ring(void) {
    unsigned i;
    for (i = 0; i < BH_BUCKETS; i++) bh_gap(&bh.b[i]);
    bh.head = 0, bh.dirty = 0;
    bh_rebase();
}

/* Everything gone, the since-charge run too (no file, a bad file, the setting off). */
static void bh_clear(void) {
    bh_clear_ring();
    bh.unplug_at = 0, bh.unplug_lvl = BH_NONE, bh.sc_play = bh.sc_on = bh.sc_total = 0;
    bh.sc_d_on = bh.sc_d_play = bh.sc_d_idle = bh.since_on = 0;
}

/* The bucket n, opened when it is new (under the lock): the buckets between the newest and n are BH_F_GAP, n starts with the last level. A number a little behind the newest is the
 * newest; one two or more behind means the clock went back: the history is dropped. */
static struct bh_bucket *bh_open(unsigned n) {
    struct bh_bucket *k;
    unsigned i, first;
    int carry;
    if (bh.head && n + 1 < bh.head) bh_clear_ring();
    if (bh.head && n < bh.head) n = bh.head;
    if (!bh.head) {
        for (i = 0; i < BH_BUCKETS; i++) bh_gap(&bh.b[i]);
        carry = BH_NONE;
        first = n;
    } else if (n > bh.head) {
        carry = bh_slot(bh.head)->level;
        first = n - bh.head > BH_BUCKETS - 1 ? n - (BH_BUCKETS - 1) : bh.head + 1;
    } else
        return bh_slot(n);
    for (i = first; i < n; i++) bh_gap(bh_slot(i));
    k = bh_slot(n);
    memset(k, 0, sizeof *k);
    k->level = (unsigned char)carry;
    bh.head = n, bh.dirty = 1;
    return k;
}

/* secs seconds to field f (0 on, 1 play, 2 cov) of bucket k, in units of 8 s with the rest carried. */
static void bh_add(struct bh_bucket *k, int f, int secs) {
    unsigned char *p = f == 0 ? &k->on : f == 1 ? &k->play : &k->cov;
    int v;
    if (secs <= 0) return;
    bh.rem[f] += secs;
    v = *p + bh.rem[f] / 8;
    bh.rem[f] %= 8;
    *p = (unsigned char)(v > 255 ? 255 : v);
}

static void bh_drop(struct bh_bucket *k, int state, int pct) {
    unsigned char *p = state == 0 ? &k->d_on : state == 1 ? &k->d_play : &k->d_idle;
    int v = *p + pct;
    *p = (unsigned char)(v > 255 ? 255 : v);
}

/* A new run since the last charge begins at wall (under the lock): the gauge then is g, else the last reading; since_on 1 when no charger removal began it. */
static void bh_run(long wall, int g, int since_on) {
    bh.unplug_at = wall;
    bh.unplug_lvl = g >= 0 ? (unsigned)g : bh.glast >= 0 ? (unsigned)bh.glast : BH_NONE;
    bh.sc_play = bh.sc_on = bh.sc_total = 0, bh.sc_d_on = bh.sc_d_play = bh.sc_d_idle = 0;
    bh.since_on = (unsigned)since_on;
    memset(bh.acc, 0, sizeof bh.acc); /* the run's drops are attributed by the run's own seconds */
    bh.susp_g = 0;
}

/* One sample's bookkeeping (under the lock). chg: the status text said external power 1, battery 0, or -1 (unreadable); g: the gauge or -1 when it was not read. */
static void bh_account(long wall, long mono, long boot, int lit, int playing, int chg, int g) {
    struct bh_bucket *k;
    unsigned cur = (unsigned)wall / BH_SECS;
    int was = bh.chg, ch, state = lit ? 0 : playing ? 1 : 2;
    if (chg >= 0) bh.chg = chg;
    if (bh.have) {
        long dm = mono - bh.lmono, db = boot - bh.lboot;
        if (dm < 0 || db < dm) /* the clocks went back: not the same run */
            bh_rebase();
        else if ((wall - bh.lwall) - db < -BH_JUMP) /* the wall clock was set back */
            bh_clear_ring();
        else {
            int susp = (int)(db - dm), awake;
            unsigned long t, end;
            if (susp < BH_SUSP) susp = 0;
            awake = (int)db - susp;
            ch = was || bh.chg;
            if (was &&
                !bh.chg) /* the charger was removed: a new run since the last charge (this step's time is still the charger's) */
                bh_run(wall, g, 0);
            /* the standby: idle known time over the wall span before the sample's end (anchored there, so a clock set forward leaves the gap before it) */
            t = (unsigned long)(wall - db), end = t + (unsigned)susp;
            while (t < end) {
                unsigned long edge = ((t / BH_SECS) + 1) * BH_SECS, to = edge < end ? edge : end;
                k = bh_open((unsigned)(t / BH_SECS));
                bh_add(k, 2, (int)(to - t));
                if (ch) k->flags |= BH_F_CHG;
                t = to;
            }
            k = bh_open(cur);
            if (bh.chg || (was && (unsigned)(wall - db) / BH_SECS == cur))
                k->flags |= BH_F_CHG; /* (a charger that ended in an earlier bucket does not flag this one) */
            bh_add(k, 2, awake);
            if (state < 2) bh_add(k, state, awake);
            if (ch)
                memset(bh.acc, 0, sizeof bh.acc);
            else {
                bh.acc[state] += awake;
                bh.acc[2] += susp;
                if (bh.unplug_at) { /* the same precedence as the state: screen on, then playing with the screen off; the total takes the idle and standby too */
                    if (state == 1) bh.sc_play += awake;
                    if (state == 0) bh.sc_on += awake;
                    bh.sc_total += awake + susp;
                }
            }
            bh.susp_g += susp;
            if (g >= 0) {
                if (!ch && bh.glast >= 0 && g < bh.glast) {
                    int to_state = 2;
                    if (bh.susp_g < BH_SUSP_DROP) {
                        if (bh.acc[0] >= bh.acc[1] && bh.acc[0] >= bh.acc[2])
                            to_state = 0;
                        else if (bh.acc[1] >= bh.acc[2])
                            to_state = 1;
                    }
                    bh_drop(k, to_state, bh.glast - g);
                    if (bh.unplug_at) { /* the run's share, the same attribution (at most 100: a gauge that wobbles can fall more than once over the same percent) */
                        unsigned *d = to_state == 0 ? &bh.sc_d_on : to_state == 1 ? &bh.sc_d_play : &bh.sc_d_idle;
                        *d += (unsigned)(bh.glast - g);
                        if (*d > 100) *d = 100;
                    }
                    memset(bh.acc, 0, sizeof bh.acc);
                }
                k->level = (unsigned char)g;
                bh.glast = g, bh.lgauge = boot, bh.susp_g = 0;
            }
            if (!bh.unplug_at &&
                chg ==
                    0) /* no run yet and the status says Discharging (it was unreadable before): the run begins here, after this step's time and drop */
                bh_run(wall, -1, 1);
            bh.lwall = wall, bh.lmono = mono, bh.lboot = boot;
            return;
        }
    }
    /* a new baseline: nothing is added (no time has passed that we know of); the buckets since the file's newest one are gaps */
    bh_rebase();
    k = bh_open(cur);
    bh.chg = chg >= 0 ? chg : 0;
    if (bh.chg) k->flags |= BH_F_CHG;
    if (!bh.unplug_at && chg == 0) /* recording started on battery (the status said Discharging): the run begins here */
        bh_run(wall, g, 1);
    if (g >= 0) {
        k->level = (unsigned char)g;
        bh.glast = g, bh.lgauge = boot;
    }
    bh.have = 1, bh.lwall = wall, bh.lmono = mono, bh.lboot = boot;
}

/* External power (patch/power.c pwr_external: the status text, the online files and the raw PD17 level, any one saying external wins): 1 external, 0 battery, -1 unknown (the last state stays). */
static int bh_status(void) { return pwr_external(); }

static unsigned bh_sum(const struct bh_file *f) {
    const unsigned char *p = (const unsigned char *)f->b;
    unsigned s = f->head * 2654435761u + f->unplug_at * 31 + f->unplug_lvl + f->sc_play * 7 + f->sc_on * 13 +
                 f->sc_total * 17 + f->sc_d_on * 19 + f->sc_d_play * 23 + f->sc_d_idle * 29 + f->since_on * 37,
             i;
    for (i = 0; i < sizeof f->b; i++) s = s * 31 + p[i];
    return s;
}

/* The ring as a file image (under the lock). */
static void bh_pack(struct bh_file *f) {
    f->magic = BH_MAGIC, f->version = BH_VERSION, f->count = BH_BUCKETS;
    f->head = bh.head;
    f->unplug_at = (unsigned)bh.unplug_at, f->unplug_lvl = bh.unplug_lvl;
    f->sc_play = bh.sc_play, f->sc_on = bh.sc_on, f->sc_total = bh.sc_total;
    f->sc_d_on = bh.sc_d_on, f->sc_d_play = bh.sc_d_play, f->sc_d_idle = bh.sc_d_idle, f->since_on = bh.since_on;
    memcpy(f->b, bh.b, sizeof f->b);
    f->sum = bh_sum(f);
}

/* 1 when the image is a file this build wrote and every value is possible. */
static int bh_valid(const struct bh_file *f) {
    unsigned i;
    if (f->magic != BH_MAGIC || f->version != BH_VERSION || f->count != BH_BUCKETS || f->sum != bh_sum(f)) return 0;
    if (f->head < BH_MIN_WALL / BH_SECS) return 0;
    /* (unplug_at is not checked against head: a clock set back drops the ring but keeps the run, so it may be later) */
    if ((f->unplug_lvl > 100 && f->unplug_lvl != BH_NONE) || f->sc_on + f->sc_play > f->sc_total ||
        (!f->unplug_at && (f->sc_total || f->sc_d_on || f->sc_d_play || f->sc_d_idle || f->since_on)))
        return 0;
    if (f->since_on > 1 || f->sc_d_on > 100 || f->sc_d_play > 100 || f->sc_d_idle > 100) return 0;
    for (i = 0; i < BH_BUCKETS; i++) {
        const struct bh_bucket *k = &f->b[i];
        if ((k->level > 100 && k->level != BH_NONE) || k->flags > (BH_F_CHG | BH_F_GAP) || k->on > BH_COV_MAX ||
            k->play > BH_COV_MAX || k->cov > BH_COV_MAX || k->d_on > 100 || k->d_play > 100 || k->d_idle > 100)
            return 0;
    }
    return 1;
}

void bh_load(void) {
    unsigned n = 0;
    char *raw = m1_read_file(BH_DATA, sizeof(struct bh_file) + 1, &n);
    bh_lock();
    bh.loaded = 1;
    if (raw && n == sizeof(struct bh_file) && bh_valid((const struct bh_file *)raw)) {
        const struct bh_file *f = (const struct bh_file *)raw;
        memcpy(bh.b, f->b, sizeof bh.b);
        bh.head = f->head;
        bh.unplug_at = f->unplug_at, bh.unplug_lvl = f->unplug_lvl;
        bh.sc_play = f->sc_play, bh.sc_on = f->sc_on, bh.sc_total = f->sc_total;
        bh.sc_d_on = f->sc_d_on, bh.sc_d_play = f->sc_d_play, bh.sc_d_idle = f->sc_d_idle, bh.since_on = f->since_on;
    } else
        bh_clear();
    bh_unlock();
    if (raw) free(raw);
}

/* Write the ring if a bucket was opened. The setting going off meanwhile deletes the file again. */
static void bh_save(void) {
    struct bh_file f;
    int write;
    bh_lock();
    write = bh.dirty && bh.head;
    if (write) bh_pack(&f), bh.dirty = 0;
    bh_unlock();
    if (!write) return;
    m1_save(BH_DATA, 0644, &f, sizeof f);
    if (bh.state != 2) unlink(BH_DATA);
}

/* One sample (the thread's loop calls it every BH_PERIOD seconds, or sooner after bh_request; the test calls it directly). */
void bh_sample(void) {
    struct {
        int sec, nsec;
    } m, b;
    long wall = time((long *)0), boot;
    int lit = m1_screen_lit(), playing = mclGetPlayStatus() == MB_PLAYING, chg = bh_status(), g = -1;
    if (clock_gettime(1, &m)) return;
    if (clock_gettime(7, &b)) b = m;
    boot = b.sec;
    if (wall < BH_MIN_WALL) { /* an unset RTC: nothing is recorded, and a later time starts a new baseline */
        bh.have = 0;
        return;
    }
    if (!bh.have || boot - bh.lgauge >= BH_GAUGE || (boot - bh.lboot) - (m.sec - bh.lmono) >= BH_SUSP)
        g = battery_gauge();
    bh_lock();
    bh_account(wall, m.sec, boot, lit, playing, chg, g);
    bh.seq++;
    bh_unlock();
    bh_save();
}

void *bh_main(void *arg) {
    (void)arg;
    for (;;) {
        if (!bh.loaded) bh_load();
        while (bh_setting()) {
            int i;
            bh.want = 0; /* (before the sample: a request that comes during it samples again) */
            bh_sample();
            /* BH_PERIOD in 1 s steps: sleep does not count a kernel suspend, so a long wait would end late after a wake; a request from the page ends it at the next step */
            for (i = 0; i < BH_PERIOD && !bh.want; i++) sleep(1);
        }
        /* the setting is off (the switch, or its file was deleted): nothing of ours stays. A switch turned on again meanwhile is seen under the lock that also ends the thread
         * (bh_start looks at `run` under it), so the recorder never ends with the setting on. */
        bh_lock();
        bh.loaded = 0;
        bh_clear();
        bh_unlock();
        unlink(BH_DATA);
        unlink(BH_DATA ".tmp");
        bh_lock();
        if (!bh_setting()) {
            bh.state = 1, bh.run = 0;
            bh_unlock();
            return (void *)0;
        }
        bh_unlock();
    }
}

static void bh_start(void) {
    unsigned long th = 0;
    bh_lock();
    if (bh.run) {
        bh_unlock();
        return;
    }
    bh.run = 1;
    bh_unlock();
    if (pthread_create(&th, (const void *)0, bh_main, (void *)0)) {
        bh.run = 0, bh.retry = 30;
        return;
    }
    pthread_detach(th);
}

void bh_poll(void) {
    if (bh.state == 0) bh.state = bh_setting() ? 2 : 1;
    if (bh.state != 2 || bh.run) return;
    if (bh.retry) {
        bh.retry--;
        return;
    }
    bh_start();
}

int bh_toggle(void) {
    int next = !bh_setting();
    if (home_set_digit(BH_FILE, next, 1) < 0) return -1;
    if (next) {
        bh.state = 2, bh.retry = 0;
        bh_start();
        return 1;
    }
    bh_lock();
    bh.state = 1, bh.loaded = 0;
    bh_clear();
    bh_unlock();
    unlink(BH_DATA);
    unlink(BH_DATA ".tmp");
    return 0;
}

/* The History page asks the thread for a sample now (the page opened or came back to front); the page itself never samples. */
void bh_request(void) { bh.want = 1; }

/* The number of samples taken: the page's timer redraws when it changed. */
unsigned bh_seq(void) { return bh.seq; }

int bh_snapshot(struct bh_view *out) {
    unsigned i;
    memset(out, 0, sizeof *out);
    bh_lock();
    if (bh.state != 2 || !bh.head) {
        bh_unlock();
        return 0;
    }
    out->head = bh.head;
    for (i = 0; i < BH_BUCKETS; i++) out->b[i] = *bh_slot(bh.head - (BH_BUCKETS - 1) + i);
    out->unplug_at = bh.unplug_at, out->unplug_lvl = bh.unplug_lvl, out->level = bh_slot(bh.head)->level;
    out->sc_play = bh.sc_play, out->sc_on = bh.sc_on, out->sc_total = bh.sc_total;
    out->sc_d_on = bh.sc_d_on, out->sc_d_play = bh.sc_d_play, out->sc_d_idle = bh.sc_d_idle,
    out->since_on = bh.since_on, out->chg = bh.chg != 0;
    bh_unlock();
    return 1;
}
