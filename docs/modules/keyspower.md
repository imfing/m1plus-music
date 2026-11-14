# Buttons & Power

Settings > System > Buttons & Power is one own cards page (`m1plus_keyspower`, `KEYSPOWER_PAGE`, `patch/keyspower.c`) that replaces four stock controls the way
[Display](display.md) replaced stock's Display list: our own rows, stock's own state words and config saves, no row opening a stock
page, nothing of ours saved. Sections 1 to 3 are the static analysis of V2.1 `demo` and what our setters do (all addresses are `demo`
virtual addresses; disassembly by `tools/disasm.py`, cache `work/cache/demo.dis`). Not run on a device; the emulator tests run stock's
own handlers (`test/pod/keyspower.py`).

Sleep Timer (`view_sleep`) and Screen Rotation are out of scope and stay stock-only. Stock's pages stay under All System Settings
and show the same state.

## Summary

| Control | Stock state | Config `[SYSSET]` | Stock page | Our control |
|---|---|---|---|---|
| Buttons lock | flag byte `0xa05aa0` (0/1), mode word `0x97caec` (1..3) | `LOCKFLAG`, `LOCKMODE` | `systemset/keylock_page` | value row + picker (Off, Volume, Buttons, Both) |
| Tap to Wake | byte `0xa05aa1` (0/1) | `DOUBLEWAKE` | row 7 of `systemset/sysset_page` | switch row |
| Auto-standby | byte `0xa05a8c` (0/1, 300 s fixed) | `STANDBYMODE` | `powermanager_page`, `view_standby` | switch row |
| Auto-shutdown | word `0xa05a84` (0 off, 1..4 = 1/3/5/10 min) | `SAVEPOWERMODE` | the same view | value row + picker (Off, 1min, 3min, 5min, 10min) |

Auto-shutdown IS a duration picker (a switch plus four check rows `1min 3min 5min 10min`, no text selectors; the hour/minute
selectors belong to Sleep Timer only). Auto-standby has no duration. Auto-standby and Auto-shutdown are mutually exclusive in
stock's handlers (below). No row of any of the four is hidden by model or config, except the Buttons lock choices, which stock hides
while the flag is 0.

## 1. Buttons lock (`systemset/keylock_page`)

**Page** (`ui/systemset/keylock_page.bin`, `awtk_ui.py dump`): `listitem0` (`scrlabel0`, switch `img_switch`), `listitem1..3`
(`scrlabel1..3`, `img_choice1..3`), `listitem4` (`label_info`). Texts are set in code by the init's widget walk (`0x4a7460` callback,
init `0x4a7b30`): title `sset_keylock`, `scrlabel0` `sset_keylock`, `scrlabel1` `keylock_volume`, `scrlabel2` `keylock_key`,
`scrlabel3` `keylock_all`, `label_info` `keylock_info`. The rows are NOT in the order the keys sort in: choice 1 = Volume only,
choice 2 = Buttons only, choice 3 = Volume and Buttons.

**State.** `LOCKFLAG` byte `0xa05aa0` (config_init `0x4e62f8..0x4e6338`: values >= 2 become 0, `andi 1`; default file value 0).
`LOCKMODE` word `0x97caec` (config_init `0x4e635c..0x4e6398`: anything outside 1..3 becomes 1, the code's `s5` = 1; the shipped
`config.ini` has no `LOCKMODE`, so the default is 1). Mode meaning, read from the run-time gates:

- mode 1 = lock volume only, 2 = lock buttons only, 3 = both. Volume keys (`0xdc/0xdd`) pass only when mode == 2
  (`0x47e3a4..0x47e3b4`, `0x4cdc20..0x4cdc2c`, `volume_dialog` key filter); the play / prev / next keys pass only when mode == 1
  (`0x4cda60..0x4cda6c`, `0x4cdb48`, `0x4cdba8`, bluetooth-receive page `0x52a660`, `0x52a6b4`, `0x52a6f4`).
- Both only matter when the screen is off: every gate first tests the screen-on byte `0x97cae4` (non-zero = screen on = no lock).
  This is the stock note "Only effective when the screen is off" (`keylock_info`).

**Click handlers** (ctx = the window in `a0`, bound by the foreach `0x4a7bb0` through `widget_on(item, 0x10c, ...)`):

| Row | Handler | Does, in order |
|---|---|---|
| switch (`listitem0`) | `0x4a7a04` | byte `0xa05aa0` ^= 1 (stored at `0x4a7a38`); refresh `0x4a770c(win, mode, 1)`; `write_int_config(byte, "SYSSET", "LOCKFLAG")` |
| choice 1 / 2 / 3 | `0x4a7a7c` / `0x4a7ab8` / `0x4a7af4` | refresh `0x4a770c(win, 1|2|3, 0)` only |

Refresh `0x4a770c(win, idx, show)`: with `show` != 0 (the switch and the init) sets `img_switch` to `sset_on`/`sset_off` from the
flag and shows or hides `listitem1..4` by the flag; then `img_choice<idx>` = `selected`; if `idx` differs from the mode word
(`0x4a7900 beq s1, s3`): `img_choice<old>` = `unselect`, word = idx (`sw s1,(s4)` in the delay slot of the call at `0x4a7988`) and
`write_int_config(idx, "SYSSET", "LOCKMODE")`. No other side effect: no timer reset, no key-lock apply call, no driver or sysfs
write. The gates above read the byte and word on every key, so the change is live at once.

**Our setter** (`kp_lock_set(v)`, one merged row as LED Light merged the lamp's switch and colour). Off is stock's switch while it is
on: byte 0, then `write_int_config(0, "SYSSET", "LOCKFLAG")`; the mode is kept, so stock's page then shows the switch off and the last
mode checked. A mode is stock's two clicks: the switch when the flag is off (byte 1, save `LOCKFLAG`), then the choice (nothing when it
is the mode already; else the word, then the save of `LOCKMODE`). Stock's handlers are not called: their refresh needs stock's widget
names.

**Other writers/readers to follow while the page is open.** The Control Center tile `system_keylock` writes the same byte
(`0x4745c4..0x4745fc`, `LOCKFLAG`), so our page re-reads on every return to the foreground (`disp_refresh` pattern; the pull-down is a
dialog above it). The tile and the key gates need no change.

## 2. Tap to Wake (`sset_doublewake` / `sset_tswake`)

**Which row the device shows.** `systemset_sysset_page_init` (`0x4ada7c`) builds rows `0 .. count-1` of the identity table `0x97c8c0`
(`count` = `0xf` + 1 when the language word `0xa05ab8` is 3, else 15; `addiu v0,v0,0xf` at `0x4adb1c`; the Theme patch makes it one
less, theme.md). Row 7 (value 7, kept at position 7 by the Theme patch) is always built; it is a switch row (image `sset_on`/`sset_off`
from byte `0xa05aa1`, image named `img_doublewake%d` at `0x7489c0`). Its label and icon text come from
`get_systemset_showinfo` (`0x4da084`), which reads the GPIO named `PA02` (`toolsGpioGetValue` `0x5e5cac`, string `0x74acf4`, at
`0x4da0c8`) each time the list is built:

- `PA02` == 1: the name table at `0x97c988`: row 7 = **`sset_tswake`** ("Tap the Screen to Activate Screen")
- otherwise: the table at `0x97c9c8`: row 7 = **`sset_doublewake`** ("Double Tap to Turn Screen On")

The two tables are otherwise identical (checked all 16 entries; only index 7 differs). So the label is chosen by a board strap read at
run time; static analysis cannot say which value the M1 Plus reads. The user's device shows a single tap, which means `PA02` reads 1
there and the row is `sset_tswake`; this is consistent with the code but not proven (the Chinese tables: `sset_tswake` = 触摸屏幕亮屏
"touch the screen to turn it on", `sset_doublewake` = 双击屏幕亮屏 "double-tap"). Both rows use the same byte, key and handler: the
setting means the same thing to the code, only the words differ. Stock strings per language: `sset_tswake` is translated in every
table; `sset_doublewake` is untranslated English in `it_IT` and `uk_UK`. Neither fits a 173 px switch label in most languages (English
"Double Tap to Turn Screen On" is 259 px at 21 px, "Tap the Screen to Activate Screen" 289 px).

**Our label is the short own text "Tap to Wake"** (key = English text, `pod_i18n.TEXT`, 12 translations), not either stock key. It
names the feature for either board. The stock icon of both keys is the same picture
(`sset_doublewake.png` == `sset_tswake.png`, same SHA-256 in `tools/mod_theme.py`).

**State and handler.** Byte `0xa05aa1` (config_init `0x4e6298..0x4e62d8`: values >= 2 become 0; default 0, `config.ini` `DOUBLEWAKE=0`).
The click is a case of the shared sysset click handler `0x4ad7b0` (row name `atoi` -> table `0x97c8c0` -> jump table `0x748ae0`,
entry 7 = `0x4ad930`): `write_int_config(byte ^ 1, "SYSSET", "DOUBLEWAKE")` with `sb a0,(s2)` (the new byte) in the call's delay slot
(`0x4ad944..0x4ad95c`), then it only sets the row's switch image (`img_doublewake%d`). Nothing else: no sysfs write at the click. This is
the same shape as `disp_follow_toggle`.

**Where the byte takes effect** (all in stock code that already runs, no call from our row):

- screen off (`disable_fb` `0x4e7088`, byte read `0x4e7098`): byte 1 -> `double_onclick_wake(1)` (`0x4d6920`: `echo 1 >
  /sys/class/tpconfig/ges_control`), byte 0 -> `tp_power(0)` (`0x4d6860`: `echo 0 > /sys/class/tpconfig/tp_switch`, touch panel off);
- screen on (`enable_fb` `0x4e6cac`, byte read `0x4e6d68`): byte 1 -> `double_onclick_wake(0)`, byte 0 -> `tp_power(1)`;
- standby entry (`0x4e76d8`): `config_doublewake_switch` (`0x4d68b4`: `echo <byte> > /sys/class/tpconfig/ges_switchflag`);
- the 1 Hz-ish main loop wake test (`0x4cffd8..0x4d0008`): with the byte set and the screen off, `get_doubleclick_state` (`0x4d6994`
  reads `/sys/class/tpconfig/ges_state`, true when it is 1) wakes the screen (`awake_screen`).

So toggling the byte is enough; the driver is told at the next screen off. The sysfs nodes belong to the Goodix `gt9xx_touch.ko`
(`ges_control_store`, `ges_switchflag_store`, `ges_state_show`; `ges_control` writes one of two 16-bit commands, 0x1c0 or 0xc, to the
IC). **Single or double tap is decided by the touch IC / its firmware and board strap, not by anything in `demo`**: the code has one
setting and one polled state called "doubleclick". Not verified: what the IC does per board.

## 3. Auto-standby and 4. Auto-shutdown (`systemset/powermanager_page`)

**Page** (`ui/systemset/powermanager_page.bin`): a `slide_view` with `view_sleep` (out of scope) and `view_standby`. In
`view_standby`'s `standby_listview`: `standby_listitem0` (label `standby_scrlable0` = `powerm_standby`, switch `imgswitch_standby`),
`standby_listitem1` (`standby_scrlabel1` = `powerm_saver`, switch `imgswitch_saver`), `standby_listitem2..5` (plain asset texts
`1min`, `3min`, `5min`, `10min`, `standby_imgchoice2..5`), `standby_listitem6` (`standby_labelinfo` = `powerm_standbyinfo`). Init
`0x4a9d18`; the title of the page is `powerm_deep_off` ("standby/shutdown"). Texts are set by the foreach `0x4a8dcc` (names at
`0x4a8fd8..0x4a9178`).

**State, loaded by config_init** (`0x4e5fe4..0x4e6050`):

| Setting | Address | Load rule | Default (`config.ini`) |
|---|---|---|---|
| Auto-standby on/off | byte `0xa05a8c` | `[SYSSET] STANDBYMODE`, >= 2 -> 0, `andi 1` | 1 (on) |
| Auto-shutdown level | word `0xa05a84` | `SAVEPOWERMODE`, >= 5 -> 0 | 0 (off) |

**Run time** (`to_poweroptions` `0x4ce5a8`, a periodic tick; guards: not playing (`mclGetPlayStatus` != 2), car mode byte
`0xa05aa6` == 0, plus a few busy flags). Standby: byte `0xa05a8c` != 0 and countdown `0xa05a88` > 0 -> decrement; at 0 `into_standby`
(`0x4e7508`). Auto-shutdown: word `0xa05a84` > 0 and countdown `0xa05a80` > 0 -> decrement; at 0 `navigator_to("poweroff_page")`. The
countdowns are set from `reset_poweroptions_timer(standby, shutdown, screen)` (`0x4d7874`, documented in addresses.md): standby
`setstandby_time` `0x4d782c` = 300 s when the byte is 1 else 0; shutdown `setsavepower_time` `0x4d783c` = `s16[0x74b87c + (word-1)*2]`
= **60, 180, 300, 600 s** for 1..4.

**Click handlers** (ctx = window, bound by the foreach on `standby_listitem0..5`):

| Row | Handler | Does, in order |
|---|---|---|
| Auto-standby switch | `0x4a97c4` | byte on -> byte = 0, `write_int_config(0, "SYSSET", "STANDBYMODE")`. Byte off -> byte = 1; if the shutdown word > 0: `img` `standby_imgchoice<w+1>` unselected, word = 0, `write_int_config(0, "SYSSET", "SAVEPOWERMODE")`; then `write_int_config(byte, ... "STANDBYMODE")`; both paths: refresh `0x4a92a4(win, word)`, `reset_poweroptions_timer(1, 1, 0)` |
| Auto-shutdown switch | `0x4a966c` | word > 0 -> unselect `standby_imgchoice<w+1>`, word = 0, `write_int_config(0, ..., "SAVEPOWERMODE")`. Word 0 -> word = 1; if the standby byte is set: byte = 0, `write_int_config(0, ..., "STANDBYMODE")`; `write_int_config(word, ..., "SAVEPOWERMODE")`; both paths: refresh `0x4a92a4(win, word)`, `reset_poweroptions_timer(1, 1, 0)` |
| choice 1min / 3min / 5min / 10min | `0x4a9cb4` / `0x4a9c50` / `0x4a9bec` / `0x4a9b88` | return if the word already is 1/2/3/4; else refresh `0x4a92a4(win, v)` (which marks `standby_imgchoice<v+1>`, unmarks the old one, stores the word and `write_int_config(v, "SYSSET", "SAVEPOWERMODE")`), then `reset_poweroptions_timer(0, 1, 0)` |

Refresh `0x4a92a4(win, idx)` also keeps the switches in step (`imgswitch_standby` from the byte, `imgswitch_saver` on while the word
> 0 or `idx` > 0, `listitem2..5` shown only while it is on, `listitem6` the standby note shown only while the byte is on). No other
side effect: no sleep timer touch, no key or driver write.

**Coupling.** (a) Mutual exclusion: turning Auto-standby on turns Auto-shutdown off and the reverse; stock's default is standby on,
shutdown off. Our rows must repeat both writes (above), in that order. (b) Init registers `0x12d` (EVT_WINDOW_TO_FG) handler `0x4a9b2c`
at `0x4a9d34..0x4a9d50`: it only repeats the two refreshes (`0x4a9924` sleep switch and selectors from the sleep timer words, then
`0x4a92a4(win, word)`), so the stock page redraws when it comes back to the front. It changes no state. Our page needs the same
re-read on return to the foreground (the Now Playing More sheet's Sleep Timer row opens this stock page over everything and can change
the same state: `docs/modules/playmore.md`). No other writer of `0xa05a8c` / `0xa05a84` exists in `demo` (xrefs: this page,
config_init, `reset_poweroptions_timer`, `to_poweroptions`).

**Our setters** (`kp_standby_toggle`, `kp_shutdown_set(v)`, v = stock's word 0..4) repeat stock's clicks one at a time, with the same
stores, saves and calls in the same order:

- `kp_standby_toggle` is the switch `0x4a97c4` as in the table.
- `kp_shutdown_set(0)` while it is on is the switch `0x4a966c`: word 0, save `SAVEPOWERMODE`, `reset_poweroptions_timer(1, 1, 0)`.
- A duration from Off is the switch (word 1 stored; a set standby byte cleared and `STANDBYMODE` 0 saved; `SAVEPOWERMODE` 1 saved;
  `reset(1, 1, 0)`) and then, unless it is 1min, the choice (word stored, `SAVEPOWERMODE` saved, `reset(0, 1, 0)`). So 10min from Off
  with Auto-Standby on saves `STANDBYMODE` 0, `SAVEPOWERMODE` 1, `SAVEPOWERMODE` 4 and calls `reset(1, 1, 0)`, `reset(0, 1, 0)`.
- A duration from another duration is the choice alone; the same duration does nothing.

Never both on holds after every operation from every state stock can be in.

## The page

Settings > System, the row after Display (`Row('Buttons & Power', ACT_PAGE, KEYSPOWER_PAGE_INDEX)`, glyph `power`). `m1plus_keyspower`
(`KEYSPOWER_PAGE`), three cards:

| Card | Row | Kind | Action |
|---|---|---|---|
| 1 | Button Lock (lock-keyhole glyph) | value row: Off, Volume, Buttons or Both; opens the picker `m1plus_keylock` (74) | `ACT_KEYLOCK` 102 |
| (note) | "Only effective when the screen is off" | `Note` | - |
| 2 | Tap to Wake (pointer glyph) | switch | `ACT_TAPWAKE` 104 |
| 3 | Auto-Standby (moon glyph) | switch | `ACT_STANDBY` 105 |
| 3 | Auto-Shutdown (power glyph) | value row: Off, 1min, 3min, 5min, 10min; opens the picker `m1plus_shutdown` (75) | `ACT_SHUTDOWN` 106 |
| (note) | "Only one of Auto-Standby and Auto-Shutdown is on at a time" | `Note`, two lines | - |

The pickers are check rows: Button Lock (Off, Lock Volume Only, Lock Buttons Only, Lock Volume & Buttons; `ACT_KEYLOCKSET` 103, arg 0 =
Off, else stock's mode 1 / 2 / 3; the note repeated) and Auto-Shutdown (`ACT_SHUTDOWNSET` 107, arg = stock's word 0..4; the times are
plain texts, `SHUTDOWN_VALUES` in `BRANDS`).

`patch/m1plus.c` wires the actions like Display's (value rows, check rows, `sw_tab`, `row_value`, `pick_chosen`, `pick_choose`). Every
value is read by `page_refresh`, which runs when the page opens and on every `EVT_WINDOW_TO_FG`, so a change made by the Control Center
tile or on stock's pages shows when our page returns to the front. The Auto-Standby switch also refreshes the page at once, because it
can turn Auto-Shutdown off.

The state words are `DATA` entries checked against demo's dynsym (`keylock_flag`, `keylock_mode`, `doublewake_flag`, `standbyflag`,
`savepowermode`). `patch/keyspower.c` holds the getters (clamped like config_init) and the setters; it calls nothing of stock but
`write_int_config` and `reset_poweroptions_timer`. The stock words the setters rely on (the handlers' stores, saves and calls, the key
gates, config_init's clamps for all five values) are pinned in `tools/pod.py` `KEYSPOWER_PINS`; a mismatch fails the build.

## Labels

Stock keys exist for every row, but their translations are not usable (`keylock_volume` is "album" in Korean, `powerm_saver` is English
in Japanese and "screen saver" in Thai, `powerm_standbyinfo` is broken in several tables), so the rows are English-text keys in
`pod_i18n.TEXT` with 12 translations each, as on Display; `Button Lock` and `Off` are the existing keys. The stock texts for Tap to Wake
are also too long for a switch row (259 and 289 px in English against 173).

Row rooms (`tools/pod_settings.py label_box`, 21 px label, a glyph row): switch 173 px, check row 211, value row 222 shared by label +
6 + value. `test/pod/i18n.py` measures every row, title and note of the three pages in all 13 languages in the built font. Three texts
are abbreviated to fit: fr `Verrouiller vol. et touches`, es `Autoapagado`, it `Spegni auto`.

## Tests

`test/pod/keyspower.py`, sections `lock_tests`, `tap_tests`, `power_tests`, `settings_tests`. Stock's own handlers run under the emulator
(the refreshes' widget lookups, `memset`, `tk_snprintf` and `atoi` mocked) on the same state; ours must reach the same final state, the
same `write_int_config` / `reset_poweroptions_timer` calls in the same order, and the same four state words at each call:

- the lock: every (flag, mode) x target, 24 changes;
- Tap to Wake: both states (stock's case reached with a row item named "7");
- every (standby, shutdown) state x the standby switch and x the five Auto-Shutdown choices, 40 changes;
- the invalid arguments and the getters' clamps.

`settings_tests` covers the Settings row, the three pages' layout, kinds, actions and glyphs, both pickers (checks per state, taps and
their saves, the Standby tap turning the shutdown row to Off), the value texts, the switch images, the refresh on return to the front
and the built assets.

## Not verified

- Anything on a device: that the lock gates and the countdowns take the stores live,
  and that a Control Center tile tap shows on the open page after the pull-down closes.
- Which value `PA02` has on the M1 Plus, and whether the touch IC wakes on one tap or two; what `ges_control`'s two commands do in the IC.
- `to_poweroptions`'s guard list was read only as far as the play status, car mode and the two counters; `poweroff_page` and
  `into_standby` were not read.
- That no other writer of the state words is reached through data pointers (only direct GOT-based xrefs were searched).
- The translations' tone (checked for fit only).
