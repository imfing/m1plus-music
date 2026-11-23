# Volume page

**Sources:** `patch/volume.c`, `tools/pod_pages.py` (`VOLUME_PAGE`, `VolumeCard`), `tools/pod_ui.py`
(`cards_volume`), `tools/pod_settings.py` (`VOLUME_*`), `tools/mod_icons.py` (`VOLBAR_*`,
`vol_capsule`, `vol_ink`), `tools/pod_pins.py` (`VOLUME_PINS`), `tools/pod.py` (hook 33); stock
`dialog_volume_dialog_init` (`0x47e41c`) and its handlers `0x47d664` .. `0x47e330`, `on_wm_tsup_fun`
(`0x4cd8dc`). **Tests:** `test/pod/volume.py`.

Our own page (`m1plus_volume`, window `m1plus_volume_page`, title Volume) replaces stock's full-page
volume screen (`dialog/volume_dialog`) when the status bar is tapped. Stock's volume logic is not
repeated: the page holds stock's widgets by stock's names and binds stock's own handlers to them with
the window as context, as the [Max Volume page](playset.md#loudness-pages) does. Stock's dialog stays
the fallback, and the strip that the hardware volume keys open over other pages is untouched.

## Page

- **Volume card** (card pieces stacked, 168 px with 12 px padding all round, and a 10 px gap under it in the same list
  item): the number `pod_volnum` (60 px, the bold face) at the left of the first row with the round
  minus and plus buttons (`btn_dec`, `btn_add`) at the right; under it the grey line `pod_volinfo`,
  "Headphones", "Line Out", "USB DAC" or "Bluetooth", plus " · Max 80" while Max Volume is below 100
  and the output is not Bluetooth (stock does not enforce Max Volume there); below that the bar.
  Stock's `vol_label` is hidden and insensitive: stock's refresh writes "VOL: 42" into it.
- **Bar** (x 22 .. 298, 52 px high, y 98): stock's `vol_slider` (0 .. 100) is invisible and keeps the
  touch and the drag (hit testing ignores `visible`; `dragger_size` 2, so the finger and the fill's
  edge agree). Over it `pod_volbar`, an insensitive transparent view, is painted in its own
  `EVT_BEFORE_PAINT` (`vp_paint`) from baked images, decoded once as the page opens
  (`m1_asset_rgba`) and freed on `EVT_DESTROY`:
  - `pod_vol_track` and `pod_vol_fill`: 276 x 52 capsules (both ends half circles, radius 26), the
    track `#3A3A3C`, the fill white. The fill is blitted from x 0 up to `value * 276 / 100`, so its
    edge is a straight vertical cut clipped by the capsule outline (at low values only a sliver of
    the left cap). No thumb.
  - **Max tick**: a 2 px line `#6A6A6E`, 12 px short of the top and bottom, at `max_volume * 276 /
    100` (centred, kept inside the bar), shortened in the capsule's end caps to the chord at its
    column less 1 px (`vp_chord`; none if nothing fits), so it never leaves the outline; only while Max Volume is below 100 and the output is not
    Bluetooth, as the "Max" text.
  - **Speaker glyph**: `pod_ci_volume` (white) and its black twin `pod_vol_ink`, 24 px, centred 26
    px from the bar's left end, split at the fill's edge: dark over the fill, white over the track.
  - The value is `volume`, or `btsource_volume` on Bluetooth. Every refresh invalidates the bar.
  - A failed decode leaves the bar unpainted (nothing leaks).
- **Second card** (10 px under the first): the generic Settings rows Max Volume (value: the
  number; opens the Max Volume slider page), Equalizer (value: the current EQ name, Off) and Volume
  & Sound (no value). Their values refresh on `EVT_WINDOW_TO_FG`
  (`page_refresh`). A tap runs `volpage_go` (from `on_row`, `patch/m1plus.c`), which opens the
  target through `pd_open_page` (`patch/pulldown.c`): in front, left alone; in the stack, the windows
  it opened are closed and it is restacked; else it is opened. A page of ours keeps one window.
  The Settings rows for Gain, Max Volume, Equalizer and Volume & Sound (`open_shared`, `patch/m1plus.c`), the
  Control Center Equalizer tile and the status bar tap take the same helper, so a picker opened
  from any route is never doubled. What a page "opened" is recorded, not inferred from the stack
  (opener table, [pulldown](pulldown.md)): a window above or below it that another route opened is
  never closed, so Back returns to where the user came from.
- **Entry:** a tap on the top 42 px of any page (stock's window-manager pointer-up handler, x 80 ..
  269) calls `vol_tap_open` (hook 33, tap only, never reads the kill switch). Our page in front: left
  alone; in the stack: the windows it opened (its Max Volume / Equalizer / Volume & Sound pages and their
  pickers) are closed and it is restacked, whatever else is above it; else opened (rooted: no
  opener). Stock's
  `navigator_to_with_context` runs when ours will not open, and when stock's own volume dialog is the
  window in front (its strip keeps stock's behaviour). The Tap for Volume switch (Settings > Buttons &
  Power, `volume-tap`, default on, read at each tap) off makes the tap do nothing, unless stock's
  strip is in front.
- **Keys:** the hardware volume keys keep working on the page: a wrapper on the window's
  `EVT_KEY_UP` runs stock's key handler (`RET_STOP` when it stepped).
- **Refresh:** `volume_showpage` is set to 2, then stock's refresh (`0x47d664`) runs, then our number,
  line and bar are written from the same words: on open, after every change, on `EVT_WINDOW_TO_FG`.

## Interfaces

Stock state read or written only by stock's handlers: `volume` `0x97cb10`, `btsource_volume`
`0x97cb0c` (used instead of `volume` while `headset_output == 2`), `max_volume` `0x97cb08`,
`headset_output` `0xa05a10`, `dacoff_time` `0x97cae0`; saves `PLAYSET VOLUME` / `BTVOLUME`. The
page's only own write is `volume_showpage` `0x97c790`. The bar's constants are `VB_*` in
`patch/offsets.inc` (checked against `tools/mod_icons.py`); the second card's rows are
`POD_PAGES[POD_VOLUME_PAGE].rows` (Max Volume, Equalizer, Volume & Sound).

## Constraints

- Stock widget names are kept; hidden widgets are insensitive (the slider is invisible but must stay
  sensitive).
- No volume arithmetic, clamp, save or `set_devicevolume` call of ours.
- Page-owned paint only: no global paint hook, no main-loop or timer work. Round shapes come from
  baked images (a small or translucent `round_radius` view renders square on the device).
- Every stock handler ends in `0x47de2c`, which adds the dialog's 3 s auto-close timer to the window
  (callback `0x47d630` closes it). Ours is bound to the same events first, so it runs after stock's,
  and calls stock's stop `0x47d9f8` (then refreshes); the key wrapper does the same itself. If our
  handler cannot be bound, stock's is not bound. The dialog's `0x12c` / `0x12d` / pointer-up handlers
  (`0x47dad4`, `0x47dd64`, `0x47dd9c`) are never bound.
- The page is a normal window, not modal: the hook returns at once.
- Stock's refresh branches on `volume_showpage` (1 = the key strip's widgets): it must be 2 before
  every refresh.
- The page refreshes only on its own changes and on `EVT_WINDOW_TO_FG`; a volume change made under
  it (Bluetooth remote volume, SyncLink) shows on the next refresh. Any timer would have to be
  page-owned and stopped on `EVT_WINDOW_TO_BG` / destroy.
- The tap hook also fires on our page's own top strip (x 80 .. 269): left alone. The navbar's Back
  (0 .. 80) and Now Playing (260 ..) overlap 260 .. 269.

## Stock facts

**Openers of `dialog/volume_dialog`** (name string `0x749a94`; window name `0x749aac`). The status
bar tap is hook 33 ([addresses](addresses.md)): `on_wm_tsup_fun` `0x4cd8dc` (`widget_on(wm, 0x103)`
from `home_page_init`, every page, not boot-reachable) calls `navigator_to_with_context(name, 2)`
`0x4d1d48`, which opens the dialog modally; ours is a plain `window_open`. Gates: `standby_mode`
`0xa059e0` != 2, `boot_guidestep` `0xa06d00` <= 0, `carmode_startflag` `0xa059dc` != 2, event x in
80 .. 269, event y and `pressdown_y` `0xa05a30` < 42; after it `reset_poweroptions_timer(1,1,1)`
and `dacoff_time` cleared. The volume keys (`0xdc` / `0xdd`, `on_wm_keyup_fun` `0x4cd9ac`, site
`0x4cdc44`) open it with ctx 1. `0x4cdd00` and `0x4e799c` close it when it is the top window.

**The dialog** (320 x 42 root; init `0x47e41c` stores `ctx` in `volume_showpage`: 1 = the 30 px
strip `view_page1`, 2 = the full page `view_page2`): `btn_return`, `label_title`, `vol_label`
(24 px, "VOL: 100"), `slider vol_slider`, `btn_dec`, `btn_add`. Handlers: `btn_return` click
`0x47db0c`, `btn_add` `0x47e034`, `btn_dec` `0x47e180`, `vol_slider` EVT_VALUE_CHANGING (`0x11d`)
`0x47e1b8`; the window's KEY_UP `0x47e330`, POINTER_UP `0x47dd9c`, TO_BG `0x47dad4`, TO_FG
`0x47dd64`. `slider_set_value` fires `0x11b` then `0x11c`, never `0x11d`, so the refresh does not
re-enter the slider handler.

**Stepping:** inc `0x47df08` / dec `0x47e06c` step by 1 (guards `volume < 100` and `< max_volume`,
`volume > 0`; on Bluetooth `btsource_volume`, no Max Volume), call `set_devicevolume`, save
`VOLUME` / `BTVOLUME`, refresh, `0x47de2c`, `reset_poweroptions_timer`. The slider handler pulls the
slider back to `max_volume` when above it (off Bluetooth). The key handler swaps `0xdc` / `0xdd`
under `ROTATEMODE` `0xa05a9c` == 1, passes the gate (`backlight_status` `0x97cae4` != 0,
`keylock_flag` `0xa05aa0` == 0 or `keylock_mode` `0x97caec` == 2) and returns `RET_STOP`. The
refresh `0x47d664` writes `vol_label` and the slider on the page branch, every lookup null-checked.
Back stops the timer and closes. The value is the volume itself (0 .. 100); the Max Volume cap is
in the handlers, so the bar may show a value above the tick for an instant while dragging. Nothing
is saved on close.

**Output and value texts** (our existing code): `peqout_current()` (`patch/peqout.c`) names the
output (`mclGetOutputWay() == 2` USB DAC; way 0 with `LINEOUT_FLAG` `0xa05aa7` Line Out; else
Headphones); Bluetooth is `headset_output == 2`. Gain: `ps_value_key(PS_CTL_GAIN)` and
`ps_gain_locked()`; Equalizer: `value_text(label, VK_EQ)`; pages `m1plus_psgain`, `m1plus_peq`,
`m1plus_psvolume`.
