# The battery art

The [Charge Limit](charging.md) runs on the same status bar hook, independently of the Battery
Percentage setting.

## One battery (`tools/battery_art.py`, `tools/mod_battery.py`, lock screen step)

The app swaps `img_battery`'s image between `bar_power`, `bar_charge` (charging) and `bar_lowpower`
(capacity 0 only, `bgtz` `0x475c94`) and feeds `pgbar_battery` the capacity (100 when charge is done),
in the status bar and in the pull-down's own bar (`dropdown_showface` `0x475c3c`, twin `0x545168`); the
fill is drawn under the image (stock child order). So the image is the outline and the fill lands inside.
**No number in stock:** `get_battery_capacity` (`0x4e6dd8`) buckets the battery voltage
(`toolsGetBatteryVoltage` `0x5e35b0`) at 3.535 / 3.595 / 3.705 / 3.865 / 3.995 V into 0/20/40/60/80/100
(another table while charging, `0x4e6f58`), so a percentage could only ever read those six values (the optional exact percentage below reads the gauge instead). One drawing,
two sizes: 1.5 px outline (the status-icon stroke), rounded body corners, a 2 px rounded nub, 8x
supersampled and box-reduced, written as a plain zlib PNG (bytes independent of Pillow). Normal: white
outline, the level is the white fill; charging: green `#34C759` outline and bolt with a 0.5 px black
keyline; low: red `#FF1448` outline. Status bar (`STATUS`): image 22x12 at (288,9), body 20x12, nub 2x6 at (20,3), corner radius 3, fill
16x8 at (290,11) (0.5 px gap), right edge at x 310 as stock (it was 18x11 at (292,10) with a 12x7 fill until the sizing change), the right icon group ending 4 px before it
(its box is x 183..284); the same in `dropdown_dialog.bin`. Lock screen (`LOCK`): 34x12, body 22x12 at x 9,
fill 16x6 at (12,3), for `screens_battery/charge/lowbattery`. `fill_gap` asserts the fill stays inside
the outline; `tools/preview_battery.py` draws empty/half/full/charging/low from the tree's files.

## The percentage (`patch/battery.c`, `patch/battery.h`, `test/pod/battery.py`; hook 8 in [payload](payload.md))

**Setting:** Settings > System > Battery > **Battery Percentage**, a switch, **off by default**, `/mnt/data/m1plus/battery-percentage` (`1` on, a missing file or anything else off; [settings](settings.md)).
On, the status bar shows the AXP2101 fuel gauge's charge as a number just left of the battery outline, and the fill, the charging picture's fill and the pull-down's fill use the same value.

**How.** Stock's `show_sysbar_face` (`0x544b48`, the status bar's 1 s timer and `system_bar_init`) calls `get_battery_capacity` (`0x4e6dd8`), drops the return value and draws from the
global `power_capacity` (`0xa059ec`) the function leaves (`0x545154` the fill and the low picture, `0x54536c` the charging value); the pull-down's face (`dropdown_showface`, on its own timer) reads
the same global. The one hook is the `jalr` at `0x5450f8` (now `jal bp_capacity`): stock's function runs first, so its side effects (the USB / charge state, the power-option timers, the RGB LED) are
untouched; then, if the setting is on, `/mnt/mmc/m1plus-off` is absent and `/sys/class/power_supply/battery/capacity` is a plain integer 0..100 (one to three digits and at most one newline; anything else,
a missing file or a read error is invalid), the percentage is written to `power_capacity` and returned, and the label `pod_pct` shows `N%`. Otherwise stock's value stays and the label is hidden
(`visible=false` and `sensitive=false`). The platform_init and power-off calls stay stock (the power-off screen's one-off value is stock's bucket; the next 1 s tick restores the percentage).

**Charging.** Stock adds 10 to `power_capacity` at every call while charging (a fill animation); with the setting on the real percentage replaces it at every tick, so a charging battery shows its
true level and the bolt picture (`bar_charge`, green) stays stock's logic. When charging is done stock's `100` is the same as the gauge's.

**The label and the layout.** `pod_pct` is a hidden, insensitive `label` appended to the right icon group `view_bar_right` of `ui/system_bar.bin` (before the Screenshot camera `pod_shot`, which stays
the group's last child, against the outline), and `pod_pct_dd` the same in `view_sysbar` of `dropdown_dialog.bin` (the pull-down covers the real bar, so it needs its own; the hook sets both by
name: the system bar by a lookup in its window, the pull-down's through the window manager only when the dialog is open, so it can show the number up to a second after it opens). White `#FFFFFF`,
13 px (`statusbar.PCT_PX`), right-aligned and vertically centred in every style state, so the text's right edge is the group's right edge, 4 px before the outline (x 284, outline x 288). The group's layouter skips an
invisible child, so the label **makes room**: the icons to its left move left by its width + 4. The width follows the text: the stock AWTK text width (`StbText`: truncated advances + 1 px per glyph; Inter's
digits are tabular, 7 px at 13 px) is `BP_W2` 18, `BP_W3` 25, `BP_W4` 32 px for `5%`, `87%`, `100%` (`tools/pod_ui.py pct_widths`, written into `stock.h` at build time), and when the width changes the
hook calls `widget_resize` and asks the group to lay out again (`widget_set_need_relayout_children` on `widget_t.parent`, as `widget_set_visible` does). The Bluetooth image is 47 px wide with its
glyph in the right 11 px, so with Bluetooth, SyncLink and Wi-Fi all lit and `100%` the ink starts at x 189, 3 px clear of the 12 h clock's end (186); with the Screenshot camera too (a developer's
5 s countdown) and SyncLink off, the same 189 (the tests require at least 3 px) (`test/pod/battery.py` computes both). `tools/preview.py` shows the bar with 100%, 87%, 5% and 87% with the camera (`preview.shot_bars`).

**Cost and safety.** Setting off (the default): stock's call, one `access` (the kill switch) and a cached flag, read once from a 1 byte file at the first tick (the Settings switch keeps it; a file edited by
hand applies after a restart): no lookup, no label touched. On: one open / read / close of the 4 byte gauge and two `widget_lookup`s per second, `widget_set_text_utf8` (an invalidate of a 25 px box). No allocation,
no timer, no thread; a missing label or window just skips that label. Boot path: `tools/reach.py` does not reach `0x5450f8`, `show_sysbar_face`, `system_bar_init` or `systembar_timer_start` from `main` /
`platform_init` except through the navigator's page-init dispatcher (the cut; `system_bar_init` is its call `0x4d1cb8`), so the hook first runs when the UI starts, with stock's value as the result unless the user
turned the setting on.

**Other readers of `power_capacity`.** `poweroff_page_init` (the low-battery screen at 0), `check_updatefw_exist` / `check_otginfo` (only whether capacity or charge status is non-zero), `on_poweroff_keyup_fun`.
With the setting on they see the stored value, which is **0 at a gauge reading of 5% or less on battery** (`BP_LOW`), and also whenever stock's own bucket is 0 (so never later than stock), else the percentage.
Stock chooses `bar_lowpower` only for `power_capacity <= 0` (`bgtz` at `0x545158`, twin `0x475c94`), re-sets the picture every tick, and only on the path that is not the charging / full picture (`POWER_EXT` `0xa059f8` != 1,
or `POWER_USBSTATE` `0xa059f4` == 2 with `POWER_FLAG` `0xa05aa8` == 1 and `usbdac_chargeflag` == 0; pinned in `BATTERY_PINS`); the hook mirrors that test and stores 0 only when stock would reach the `bgtz`, so a charging
battery keeps the real value (3% charging: `bar_charge`, fill 3). The label always shows the real number. Analysis of every reader of 0: none shuts down or auto-opens a page. `poweroff_page_init` (opened by the power key)
picks the `screens_lowbattery` title and a 0 bar; `check_updatefw_exist` refuses an on-device update (-0xf) and `check_otginfo` refuses OTG when the external-power word and the capacity are both 0; `on_poweroff_keyup_fun`
only formats the value into a progress bar. These are stock's low-battery behaviours, now from 5% instead of below 3.535 V when not charging, and accepted. The 0 fill is empty (5% of 16 px is under 1 px).

**Accuracy is a device question.** `capacity` is the AXP2101's own estimate (read 100 on a charged device); how well it tracks a discharge, and whether it drifts without a learning cycle, needs a discharge test on the device.
