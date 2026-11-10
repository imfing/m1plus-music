# Charge Limit

Settings > System > **Battery** (with Battery Percentage, first on the page) > **Charge Limit** pauses charging at 80, 85, 90 or 95 %
while the player runs; 100 % (the default) is no limit. Charging resumes 5 points lower.
Powered-off charging and the status bar's charging picture stay stock's. Not yet tested on
the device: see [Validation limits](#validation-limits).

## Behaviour (`patch/charging.c`, `patch/charging.h`)

`chg_tick` runs on the status bar's 1 s tick: the Battery Percentage hook `bp_capacity`
(`patch/battery.c`, [payload](payload.md) hook 8) calls it after stock's `get_battery_capacity`,
with the kill switch result and the gauge when Battery Percentage already read it. No timer
or hook of its own. With no limit and no hold it is a cached compare. Otherwise a check runs at
most every `CHG_PERIOD` (5) seconds of `time()`; a clock that went back checks at once, and a new
limit checks at the next tick.

A check reads the AXP2101 gauge (`/sys/class/power_supply/battery/capacity`, `battery_gauge`;
stock's `power_capacity` is a voltage bucket) and writes the driver's charging request
`/sys/class/power_supply/battery/charger` with `open` / `write` / `close` (no shell):

| State | Action |
|---|---|
| External power (`POWER_EXT` `0xa059f8` = 1), not held, gauge >= limit | write `0`: our hold |
| Held, gauge <= limit - 5 | write `1`: release |
| Held, in between | read the switch; anything but `0` (stock enabled charging: the USB page's exit `0x545988`, the DAC toggle) writes `0` again |
| Stock's USB DAC mode with charging off (`POWER_USBSTATE` 2, `POWER_FLAG` 1, `usbdac_chargeflag` 0: the same test as `show_sysbar_face`'s picture) | nothing written; a hold is forgotten (stock wrote `0` and its exit writes `1`) |
| Limit 100, `/mnt/mmc/m1plus-off`, no external power, unreadable gauge | release a hold of ours |

`1` is only ever written after our own `0`, and every release (limit 100, kill switch, unplug,
bad gauge, resume level) first checks the DAC state: while stock owns the switch the hold is only
forgotten, so the user's USB DAC charging-off choice is never overridden. A failed write keeps the old state and is retried at the next check (the kill
switch's release at every tick). A reboot resets the driver's disable flag.

The setting is `/mnt/data/m1plus/battery-charge-limit`, one character `0`..`3` = 80..95 %;
anything else or missing is 100 % ([settings](settings.md)). `chg_limit` caches it;
`chg_set` (the picker) saves atomically and then applies. The pages are `m1plus_battery`
(the Charge Limit value row, `ACT_CHGLIM` 80, Lucide `battery-medium`, note "Applies while the
player is on") and the picker `m1plus_chargelimit` (`ACT_CHGLIMSET` 81, arg = the limit,
note "Resumes a little below the limit"); the Settings row is Lucide `battery-full`.

Not covered: `show_sysbar_face` returns early while `standby_mode` (`0xa059e0`) is 2 or the
bar is missing, so no check runs then (a hold stays, a release waits); external power
normally keeps `to_poweroptions` (`0x4ce5a8`) from that standby. Whether the timer keeps running
with the screen off (`screen_action` `0x4e71a4`) is a device question.

Tests: `test/pod/charging.py` (the saved limit and `chg_set`; hold, release and re-hold at each
limit; the rate and a clock going back; stock enabling charging while held; unplug, bad gauge,
kill switch, the USB DAC choice, limit changes while held; failed hold and release; one gauge
read with Battery Percentage on; the pages, picker, texts and assets).

## Interfaces (static evidence)

Stock `demo` SHA-256 `29e23119bc2a0f153f3ea0ba942a39754d1aab0879c1040fae2269df8bd9b3f1`,
stock `xImage` SHA-256 `3b326f04f20690af82fd7b2d3d61f9d01478c75081f30e99973a4e11b58fbcd8`.
Only the `POWER_*` / `USBDAC_CHARGEFLAG` words are pinned (by Battery Percentage).

| Interface | Evidence |
|---|---|
| `battery/charger` | `0` sets the driver's disable flag and zero charging current; nonzero restores the configured runtime current. Its read is the inverse of the disable flag, not a current measurement |
| `toolsSetChargeSwitch(int)` `0x5ec2c8` | stock's writer: `echo %d > .../charger` through `system` |
| `toolsGetChargeStatus()` `0x5e37a0` | `battery/status`: Charging 1, Full 2, else -1; `get_battery_capacity` stores only 0..2 in `pmucharge_status` (`0xa059e8`), so that word can be stale |
| USB DAC charging choice | `usbdac_chargeflag` `0x97cae8`; handlers `0x473960`, `0x528cb4`; USB page `0x545f24` (on) / `0x545ff8` (off), exit `0x545988` (on). Stock's toggle also writes `0x1600` / `0x1605` to `/sys/class/axp/axp_reg` (register `0x16`, USB input current); the limit does not |

The uImage header says uncompressed, but its payload holds a gzip stream at file offset
`0x4260` (12,051,904 bytes inflated, base `0x80010000`, DTB at `0xb6cba0`). In it: the `charger`
attribute `0x80b20ba4` (mode `0644`; show `0x8052f714`, store `0x805301d0`: zero sets the flag at
driver state `+0x278` and clears register `0x62` mask `0x1f`; nonzero clears it and restores the
current through `0x80530158`). Suspend `0x80530318` keeps an explicit disable; resume `0x80530298`
reapplies it; shutdown `0x80530390` selects the shutdown current without the flag. DT
`/i2c@0/pmu@34/charger@0` (`x-powers,axp2101-power-supply`): runtime, suspend and shutdown current
1000 mA, termination 100 mA, 4350 mV, USB input limit 2000 mA (unchanged).

q2-pod ([q2pod](q2pod.md), `patch/system.c` `charge_poll` at `75843484`) stops at 80 % and resumes at
75 % from a 5 s main-loop poll on the Q2's active-low GPIO PE22. Neither that poll (outside
[safety](safety.md) scope) nor its GPIO or addresses apply to the M1 Plus.

## Validation limits

Needs the device (CHG-01 in [device checks](device-checks.md)): that `charger` `0` stops battery
current while USB powers playback (readback and the icon prove neither), the stop and resume
levels, cable reinsertion, USB DAC with charging on and off, screen-off and standby, the kill
switch, reboot and shutdown.
