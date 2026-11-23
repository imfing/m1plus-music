/* M1+ Music external power: one reading of the sources, shared by Battery History and the Charge Limit (docs/modules/charging.md "External power").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * pwr_external looks at every source and any one saying external power wins (a source that errs or says nothing is unknown, never "battery"):
 *   - battery/status: Charging, Full, Not charging = external, Discharging = battery, anything else (Unknown) = unknown;
 *   - usb/online and ac/online, fixed paths (the kernel's strings show a "battery" supply only, so they may not exist): 1 external, 0 battery;
 *   - PD17 through /dev/gpio, as stock's usb_detect (0x4d6f30) reads it for POWER_EXT: open(O_RDWR), ioctl(PWR_GPIO_GET, "PD17"), close; 0 = external, 1 = battery. A read of an input line, no
 *     lock of stock's (its toolsGpioGetValue mutex only serialises its own users), no write. tools/pod.py pins the stock words and the library words it repeats.
 * The result is 1 when any source says 1, else 0 when any says 0, else -1. Stock's POWER_EXT word (refreshed only by get_battery_capacity, which the status bar skips in standby) is not read here.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "power.h"
#include "entries.h"

extern void *stock_check_cpumem_trampoline(void *);

/* The first characters of a sysfs file: bytes read (NUL terminated), or -1 when it does not open or read. */
static int pwr_file(const char *path, char *b, int max) {
    int fd = open(path, O_RDONLY, 0), n;
    if (fd < 0) return -1;
    n = read(fd, b, max - 1);
    close(fd);
    if (n < 1) return -1;
    b[n] = 0;
    return n;
}

/* PD17's level: the ioctl's return (0 / 1), -1 when it failed or the device did not open. */
static int pwr_gpio(void) {
    char name[32];
    int fd = open(PWR_GPIO_DEV, O_RDWR, 0), r, i;
    if (fd < 0) return -1;
    for (i = 0; i < (int)sizeof name; i++) name[i] = 0;
    memcpy(name, PWR_GPIO_NAME, sizeof PWR_GPIO_NAME);
    r = ioctl(fd, PWR_GPIO_GET, name);
    close(fd);
    return r < 0 ? -1 : r;
}

static int pwr_vote_online(char c) { return c == '1' ? 1 : c == '0' ? 0 : -1; }

int pwr_external(void) {
    char b[16];
    int i, one = 0, zero = 0, v;
    v = pwr_file(PWR_STATUS, b, sizeof b) < 0       ? -1
        : b[0] == 'D'                               ? 0
        : b[0] == 'C' || b[0] == 'F' || b[0] == 'N' ? 1
                                                    : -1;
    one += v == 1, zero += v == 0;
    for (i = 0; i < 2; i++) {
        v = pwr_file(i ? PWR_ONLINE_AC : PWR_ONLINE_USB, b, sizeof b) < 0 ? -1 : pwr_vote_online(b[0]);
        one += v == 1, zero += v == 0;
    }
    v = pwr_gpio();
    one += v == 0, zero += v == 1;
    return one ? 1 : zero ? 0 : -1;
}

/* Payload hook 41 (tools/pod.py CHECK_CPUMEM, 0x50b810): stock's detached boot thread opens /proc/sys/vm/drop_caches once
 * and writes "3" every ~6 s without checking free memory, evicting clean page cache and forcing continuous NAND SquashFS
 * re-reads. Linux reclaims page cache on demand, so exiting cleanly leaves caching intact; the kill switch is checked
 * immediately and once more after 15 s (in case mdev mounts /mnt/mmc asynchronously after platform_init) before exiting. */
void *m1plus_check_cpumem(void *arg) {
    if (access(KILL_SD, F_OK) == 0) return stock_check_cpumem_trampoline(arg);
    sleep(15);
    if (access(KILL_SD, F_OK) == 0) return stock_check_cpumem_trampoline(arg);
    return (void *)0;
}
