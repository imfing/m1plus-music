# Date & Time

**Sources:** `patch/datetime.c` (page), `patch/timezones.c` (zone hooks), `tools/timezones.py`
(table, order, pins), `tools/autotime.py` (RTC edits), `tools/pod.py` (`patch_timezones`),
`DATETIME_PINS` in `tools/pod_pins.py`; page `DATETIME_PAGE`.
Settings > General > Date & Time (`m1plus_datetime`) is an own cards page for what stock keeps
behind All System Settings > `system_time`: Set Automatically, Time Zone, manual date and time,
24-Hour Time. Every state is stock's own and nothing of ours is saved to a file; stock's three pages
stay under All System Settings and show the same state. No new hook for the page, nothing at boot
or paint. The zone table and the RTC edits come from q2-pod.

## Page

| Row | Kind | State | Opens |
|---|---|---|---|
| Set Automatically | switch (`ACT_DTAUTO`) | `auto_sync_nettime`, `[SYSSET] AUTOSYNCTIME` | |
| Time Zone | value (`ACT_DTZONE`), English label | `time_zone`, `[SYSSET] TIMEZONE` | `m1plus_timezone`: 43 check rows (`ACT_DTZONESET`), arg = saved index |
| Date | value (`ACT_DTDATE`), `2026-11-15` | the local clock | `m1plus_dtdate` |
| Time | value (`ACT_DTTIME`), `14:05` or `2:05 PM` | the local clock | `m1plus_dttime` |
| 24-Hour Time | switch (`ACT_DT24`) | `time24hflag`, `[SYSSET] TIME24H` | |

The Date page holds Year, Month, Day and a Set Date row; the Time page Hour, Minute and Set Time.
Each field opens a check-row picker (years 2022 to 2050). The pickers only change the date being
edited in memory; Set Date / Set Time write the clock and go back. A month or year that leaves the
day past the month's end moves the day to the month's last. A clock outside 2022..2050 starts at
2022-01-01, as stock's init does.

## Rules

- **Auto on:** the clock syncs over NTP by stock's thread. Date and Time are dimmed and `dt_apply`
  refuses.
- **Auto off:** Date and Time are live (stock's Manual row is likewise disabled while auto is on).
- **Zone:** always live, whatever Set Automatically says. Stock builds the zone rows only while auto
  is on, but that is layout only: its click handler does not test the byte. Ours never dims the row,
  so someone without Wi-Fi can pick a zone.
- Choosing a zone stores `time_zone`, saves `TIMEZONE` and calls `select_timezone`. Choosing the
  zone already chosen does nothing.
- Set Date keeps the clock's time of day and Set Time its date. Both call stock's `set_systime`
  with the same five numbers as stock's confirm handler (checked under the emulator).
- 24-Hour Time stores the byte, calls stock's `change_time24h_12h` (the status bar clock format)
  and saves `TIME24H`. `config_init` keeps 0 and 1; anything else is 1 (default). The lock screen
  clock and the pull-down's bar copy read the byte when they open ([lockscreen](lockscreen.md#the-clock),
  [pull-down](pulldown.md#the-hook)); 12-hour times show
  no leading zero (`9:41 AM`).
- **UI thread:** `set_systime` runs `system()` twice (`date`, `hwclock`), so the page freezes for
  that moment, as under stock.

## Stock flows

- **Set Automatically:** stock stores the byte and the need-sync flag together and saves
  `AUTOSYNCTIME`; `dt_auto_toggle` repeats this in order. `networktime_adjust_thd` (a thread, every
  second) acts on the flag once Wi-Fi is up: `ntpdate` against four servers (time.nist.gov,
  time.apple.com, cn.pool.ntp.org, time.windows.com), stopping at the first success and clearing the
  flag even if all fail, then `toolsSetRtcTime`.
- **Manual:** `get_systime` reads the clock after `tzset`; `set_systime` calls `date -s` then
  `hwclock -wu`.
- **Boot:** `platform_init` runs `hwclock -s` after `config_init` has exported `TZ`.

## Time zones

The picker lists 43 zones (stock 27) west to east; the saved index maps to a `TZ` value from our
table (`tools/timezones.py` `ORDER`, `TIMEZONES`).

- **Indices 0-26 keep stock's order**, so a saved zone keeps its meaning. 27-42 are added
  (Marquesas, South Georgia, Colombo, Kathmandu, Yangon, Eucla, Lord Howe, Noumea, Chatham,
  Tongatapu, Kiritimati, Chicago, Phoenix, Kolkata, Brisbane, Auckland).
- **Corrected stock zones:** 0 `<-12>12` (stock Kwajalein is +12), 4 Los Angeles (stock Tijuana),
  6 `CST6` (Mexico City dropped DST), 8 Halifax, 16 `<+0330>-3:30` (Tehran dropped DST), 20 Dhaka
  (stock Almaty), 26 `<+12>-12` (Fiji suspended DST). Every zoneinfo name exists in the stock
  rootfs; POSIX rules stand in where its tzdata is out of date.
- **Labels are English in every language** (`GMT+5:30 Kolkata`, at most 31 characters); stock's
  translated labels named the old zones. They show the standard offset and are not relabelled in
  daylight saving.
- Config clamps: stock's `config_init` turns an index of 27 or more into 22 (Shanghai); ours keeps
  an index below 43.

### Hooks

All pinned in `tools/timezones.py` (`PINS`, `edits`); the build refuses on a mismatch.

| Site | Change |
|---|---|
| `select_timezone` prologue | jumps to `tz_select` |
| `config_init` index clamp | keeps indices below 43 |
| Picker page builder | 45 rows instead of 30; click limit raised to match |
| Picker row builder | `tz_row` builds the row of zone `ORDER[row - 2]` through stock's builder, so row name, tick and click decode stay stock's |
| Picker label copy | `tz_label` writes the English literal instead of an i18n key |
| Zone row height and text | 48 px rows (stock 64), 18 px label style (stock 21), label y 13, tick y 11; the switch and header rows keep their words |

- `tz_select` reads `time_zone`; for an index below 43 and no `/mnt/mmc/m1plus-off` it calls
  `toolsSetTimeZone(name)` (`setenv("TZ")`); otherwise stock's function runs. **Under the kill switch
  a saved index of 27 or more maps to Shanghai**, as on stock. It runs at boot and after a tap.
- **A device whose saved index is 27 or more boots on a stock build with Shanghai.**
- The picker's row, count and label edits are static words, not hooks; the kill switch affects only
  `tz_select`.
- No `tzset` follows `setenv`; `localtime` re-reads `TZ`, `localtime_r` does not.

## Clock and RTC

Stock V2.1 already syncs the clock over NTP. The mod changes only how the RTC is stored, as q2-pod
does, with two pinned string edits (`tools/autotime.py`, applied by `tools/pod.py`). Stock's
`ntpdate` command and servers are untouched.

| Slot | Stock | New | Reason |
|---|---|---|---|
| RTC write (`toolsSetRtcTime`) | `hwclock -w` | `hwclock -wu` | the RTC holds UTC (q2-pod) |
| RTC read (boot, `toolsGetRtcTime`) | `hwclock -s` | `hwclock -su` | the player's own boot read must not take UTC as local time |

Each is a NUL-padded literal replaced by text of the same slot length. `EDITS` pins the stock bytes
and `NEIGHBOURS` the following literal of each slot; a mismatch fails the build before anything is
written.

**Why the read changes too:** q2-pod changes only the write because its kernel's `hctosys` sets the
clock from the RTC as UTC at boot. The M1 kernel has no `hctosys` and no RTC driver strings;
instead the player runs `hwclock -s` itself at every start, after `TZ` is exported. The rootfs has
no `adjtime`, so without `-u` it would read a UTC RTC as local time and shift the clock by the zone
offset. `-su` is required for `-wu` to be consistent.

**Default:** `config_init` copies the default `config.ini` only when `/mnt/data/config.ini` is
missing, and the default has `AUTOSYNCTIME=1` and `TIMEZONE=22`. A fresh device has auto time on; a
saved `0` stays off; a config without the key reads off. The mod does not touch `config.ini`.

## Limits

- **An RTC last written by stock holds local time.** After the update `hwclock -su` reads it as
  UTC, so the clock is off by the zone offset until the next sync (automatic when Wi-Fi connects
  with auto time on) or a manual set.
- The sync runs once per connection event, not periodically.
- Stock `time_t` is 32-bit; dates after January 2038 are wrong.
- The status bar clock and the lock screen read the byte and the clock on their own; nothing here
  repaints them.
- No date format, week day, or calendar entry: the pickers are plain check lists.
- BusyBox ash may not support the `&>` in stock's `ntpdate` command; left as in stock.
