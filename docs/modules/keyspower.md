# Buttons & Power

**Sources:** `patch/keyspower.c` (getters, setters), `patch/m1plus.c` (page wiring),
`KEYSPOWER_PAGE` in `tools/pod_pages.py`, `KEYSPOWER_PINS` and `KEYS_PINS` in `tools/pod_pins.py`, the
`pod_keys_site` stub in `tools/pod.py`.
Settings > Buttons & Power is one own cards page (`m1plus_keyspower`) that replaces four stock
controls the way [Display](display.md) replaced stock's Display list: our own rows, stock's own
state words and config saves, no row opening a stock page. Swap Prev / Next is ours (one file). Sleep Timer is
[its own page](sleeptimer.md); Screen Rotation is on [Display](display.md). Stock's pages stay under
All System Settings and show the same state. The emulator tests run stock's own handlers on the same
state and require the same final state, the same `write_int_config` / `reset_poweroptions_timer`
calls in the same order.

## Controls

| Control | Stock state | Config `[SYSSET]` | Our control |
|---|---|---|---|
| Button Lock | flag byte (0/1), mode word (1..3) | `LOCKFLAG`, `LOCKMODE` | value row + picker (Off, Volume, Buttons, Both) |
| Tap to Wake | byte (0/1) | `DOUBLEWAKE` | switch row |
| Auto-Standby | byte (0/1, 300 s fixed) | `STANDBYMODE` | switch row |
| Auto-Shutdown | word (0 off, 1..4 = 1/3/5/10 min) | `SAVEPOWERMODE` | value row + picker (Off, 1min, 3min, 5min, 10min) |
| Swap Prev / Next | ours: `/mnt/data/m1plus/buttons-swap` | none | switch row |
| Tap for Volume | ours: `/mnt/data/m1plus/volume-tap` (default on) | none | switch row ([volume](volume.md) "Entry") |

## Behaviour rules

**Button Lock.** Mode 1 locks volume only, 2 buttons only, 3 both. The mode word is clamped to 1..3
(default 1). Locks matter only while the screen is off (every stock gate tests the screen-on byte
first). The stock rows are not in key order (choice 1 = Volume, 2 = Buttons, 3 = both).

- Off is stock's switch while it is on: flag 0, save `LOCKFLAG`; the mode is kept.
- A mode is stock's two clicks: the switch when the flag is off (flag 1, save `LOCKFLAG`), then the
  choice (nothing if it is the mode already; else the word, then save `LOCKMODE`).
- The gates read the byte and word on every key, so a change is live at once. Nothing else is called.
- The Control Center tile `system_keylock` writes the same byte, so the page re-reads on every
  return to the foreground.

**Tap to Wake.** One byte, saved as `DOUBLEWAKE`; stock's click flips it, saves it and nothing else.
Screen off, screen on and standby entry tell the touch driver (sysfs nodes of the Goodix driver),
and the main loop wakes the screen on the gesture state, so toggling the byte is enough.

- Stock shows `sset_tswake` ("Tap the Screen to Activate Screen") or `sset_doublewake` ("Double Tap
  to Turn Screen On") depending on a board strap (GPIO `PA02`) read when the list is built. Both
  rows use the same byte and handler, and neither fits a 173 px switch label.
- **Our label is the own short text "Tap to Wake"**, valid for either board. Whether one tap or two
  wakes the screen is decided by the touch IC, not by anything in the player.

**Auto-Standby and Auto-Shutdown.**

- Standby: byte on and no playback, car mode off: after 300 s the player enters standby.
  Shutdown: word 1..4 gives 60, 180, 300, 600 s, then the Power Off page.
- **They are mutually exclusive.** Turning one on turns the other off, and the saves are written in
  stock's order. Stock's default is standby on, shutdown off.
- Auto-Shutdown is a duration picker; Auto-Standby has no duration.
- Setters repeat stock's clicks one at a time, with the same stores, saves and calls:
  - `kp_standby_toggle` is the standby switch. Turning it on with a shutdown set: unselect, word 0,
    save `SAVEPOWERMODE`, then save `STANDBYMODE`; then `reset_poweroptions_timer(1, 1, 0)`.
  - `kp_shutdown_set(0)` while on: word 0, save, `reset(1, 1, 0)`.
  - A duration from Off is the shutdown switch (word 1; a set standby byte cleared and
    `STANDBYMODE` 0 saved; `SAVEPOWERMODE` 1 saved; `reset(1, 1, 0)`), then unless it is 1min the
    choice (word stored, save, `reset(0, 1, 0)`).
  - A duration from another duration is the choice alone; the same duration does nothing.
- Never both on holds after every operation from every state stock can be in.
- Stock's page re-reads on return to the foreground (the other page can change the same state), so
  ours does too.

## Swap Prev / Next

Off by default. On, the physical previous and next buttons trade places: the upper one skips
forward, the lower one goes back. The setting is ours (`buttons-swap`, `1` = on, written
atomically); a change applies to the next key press.

- **Where the swap is made.** Stock reads the three track buttons (previous, play, next) in the
  input thread of `/dev/input/event1` (`0x637870`, started by `input_thread_run`). It maps the Linux
  code through the table `0x75b324` (`KEY_PREVIOUSSONG` 0xa5 to `0xd6`, `KEY_NEXTSONG` 0xa3 to
  `0xd7`) and stores the result in the event. Hook 35 replaces that load and store with
  `j pod_keys_site; nop`. The stub loads the table word and the event's value (`0x7c(sp)`: 1 down,
  2 repeat, 0 up), calls `kp_key_map`, stores its answer and resumes at `0x637bd0`. `kp_key_map`
  swaps `0xd6` and `0xd7` while the setting is on and returns every other code unchanged.
- **One mapping per press.** The mapping is chosen at a key down while neither track button is
  marked down, and kept until both are released. A toggle or the kill switch mid-press can neither turn one
  press into a previous down and a next up nor make both held buttons send the same key (stock
  keeps one held slot and one long-press timer per key). A lost key up keeps the old mapping
  until that button's next key up arrives, so stock releases the code it still holds.
- **Everything after it is stock's.** Key down, key up and long press all come from the same
  event, so `on_wm_keyup_fun`, the Button Lock gates and Now Playing's handler all see the swapped
  key. Screen Rotation's own swap (`ROTATEMODE` 1, in `on_wm_keyup_fun` and `player_timer_clear`)
  still applies on top, so the upper button is next in both orientations.
- **Not swapped:** the volume keys (`/dev/input/event2`, table `0x75b7f8`, which has no previous or
  next) and Bluetooth or remote controls, which `on_wm_idle_status` posts as keys of its own.
- **Thread rules.** `kp_key_map` runs on the input thread and calls no stock function. The setting
  is one word (0 not read, 1 off, 2 on), read from the file on the first previous or next press.
  Both threads use atomic loads and stores on it. The toggle on the UI thread stores it after the
  save; the input thread publishes its first read with a compare-and-swap from 0, so a stale read
  never overwrites a toggle. Each choice of the mapping while the setting is on also checks the kill
  switch (two stats); present, the press is stock's.

## The page

In the Display, Appearance, Buttons & Power, Battery card (`Row('Buttons & Power', ACT_PAGE,
KEYSPOWER_PAGE_INDEX)`, glyph `power`). Five cards:

| Card | Row | Kind | Action |
|---|---|---|---|
| 1 | Button Lock | value row (Off, Volume, Buttons, Both) opening picker `m1plus_keylock` | `ACT_KEYLOCK` |
| | "Only effective when the screen is off" | note | |
| 2 | Tap to Wake | switch | `ACT_TAPWAKE` |
| 3 | Swap Prev / Next | switch | `ACT_SWAPKEYS` |
| | "Next moves to the upper button" | note | |
| 4 | Tap for Volume | switch | `ACT_VOLTAP` |
| | "Tapping the top of the screen opens the Volume page" | note, two lines | |
| 5 | Auto-Standby | switch | `ACT_STANDBY` |
| 5 | Auto-Shutdown | value row opening picker `m1plus_shutdown` | `ACT_SHUTDOWN` |
| | "Only one of Auto-Standby and Auto-Shutdown is on at a time" | note, two lines | |

The pickers are check rows: Button Lock (Off, Lock Volume Only, Lock Buttons Only, Lock Volume &
Buttons; `ACT_KEYLOCKSET`, arg 0 = Off, else stock's mode) and Auto-Shutdown (`ACT_SHUTDOWNSET`,
arg = stock's word 0..4).

`m1plus.c` wires the actions like Display's. Every value is read by `page_refresh`, on open and on
every `EVT_WINDOW_TO_FG`, so a change made by the Control Center tile or on stock's pages shows when
the page returns. The Auto-Standby switch also refreshes at once, because it can turn Auto-Shutdown
off. The state words are checked against the dynsym; `keyspower.c` calls nothing of stock but
`write_int_config` and `reset_poweroptions_timer`. The handlers' stores, saves and calls, the key
gates and config_init's clamps are pinned in `KEYSPOWER_PINS`; a mismatch fails the build.

## Labels

Stock's translations of these rows are unusable (`keylock_volume` is "album" in Korean,
`powerm_saver` is English in Japanese and "screen saver" in Thai, `powerm_standbyinfo` is broken in
several tables), so the rows are English-text keys in `pod_i18n.TEXT` with 12 translations each, as
on Display; `Button Lock` and `Off` are the existing keys.

Row rooms (`label_box`, 21 px label): switch 173 px, check row 211, value row 222 shared by label,
6 px and value. `test/pod/i18n.py` measures every row, title and note in all 13 languages. Three
texts are abbreviated to fit: fr `Verrouiller vol. et touches`, es `Autoapagado`, it `Spegni auto`.
