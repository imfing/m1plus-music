# Display

**Sources:** `patch/display.c`, `patch/tracklamp.c`, `patch/tracklamp.h`, `tools/pod_pages.py`
(`DISPLAY_PAGE`), `LOCKSCREEN_PINS`.Part of [settings](settings.md).

Settings > Display (`m1plus_display`) replaces stock's Display list and its four pages with one
cards page: the brightness slider; **Screen Timeout** and **Lock Screen** (a link to
[lockscreen](lockscreen.md)); **Screen Rotation**; and **LED Light**. No row opens a stock page.
Every state is stock's own and nothing of ours is saved, except the Dynamic LED setting. The
persisted values are in [settings](settings.md) "Persisted choices". Stock's pages stay under All
System Settings and show the same state.

Each row repeats what stock's page handlers do, in the same order (value stored, then saved, then
the dependent call). `test/pod/display.py` runs stock's handlers in the emulator on the same state
and compares the stored value and the calls with ours.

## Brightness

A card with the pull-down's control (the pull-down's own card is laid out by the same code, `pod_ui.bright_control`; [pulldown](pulldown.md)): the small sun, a 200 x 50 slider (the pull-down's track and
fill, so the fill takes the accent, under our own white capsule thumb `pod_sl_thumb`) and the large
sun. The slider is named `slider_brightness` (range 0 .. 100) and a hidden `label_brightness` sits
beside it, because the code behind it is stock's: `disp_opened` calls stock's refresh and binds
stock's two handlers (value changing, value changed) to the slider. The payload repeats none of it.
The refresh runs again each time the page returns to the front, so the slider follows the
pull-down's.

## LED Light and Follow Screen

**LED Light** is stock's lamp mode `[SYSSET] ATMOSPHERELEDMODE`: 0 off, 1 green, 2 blue. Stock
labels mode 1 orange, but the lamp is green, so the picker says Green. A value row and the picker
`m1plus_ledlight` (Off, Green, Blue; Dynamic below) call what stock's handlers call: store the mode,
`write_int_config`, `reset_atmosphereled_rgb`. Blue from off is one step here (stock: the switch,
then the colour).

**Follow Screen** is stock's switch `[SYSSET] LEDFOLLOWSCREEN`, in a card of its own under the
choices with the note "The light is off while the screen is off". It stays usable while the lamp is
off (stock hides it then). The Theme row (below) is the page's last item.

## Screen Timeout

Stock's backlight time: a value row and the picker `m1plus_lighttime` with stock's five choices
(Never, 15s, 30s, 1min, 5min in stock's order; the times are plain text, the same in every
language; `[SYSSET] LIGHTTIME`). Choosing one stores the word, saves it and
resets the screen's countdown from it, as stock's page does.

## Screen Rotation

A switch row in a card of its own, with the note "Turns the screen upside down"; on = 180 degrees.
It is stock's `[SYSSET] ROTATEMODE` (0 or 1), the same choice as stock's rotation page. The label is
our short key `Screen Rotation` (stock's Spanish text does not fit the switch row).

- A toggle repeats stock's four steps in order: store the word, save it, call
  `tk_set_lcd_orientation(0 or 0xb4)`, set the byte `scr_rotateflag`. Boot applies the word, and the
  boot logo follows it too ([boot](boot.md)).
- The rotation is global: pages keep their 320 x 480 coordinates, so our pages need no layout of
  their own. Cover Flow's volume buttons swap with the word, as stock's key handler does.
- `scr_rotateflag` is read by a dozen stock dialogs, which move themselves once. Our switch sets it
  as stock does and nothing of ours reads it.

## Sample Rate

A fourth LED Light choice, shown as **Dynamic** (two of its themes do not show the rate). The lamp
shows the playing track's sample rate as a colour.
- Choosing it saves the setting and sets stock's lamp mode to 0, so stock lights nothing of its
  own. It opens no page. Choosing Off, Green or Blue saves `0`, lets the lamp go and then does what
  the stock choice does.
- While Dynamic is chosen, a **Theme** row (value row) appears in its own card below Follow Screen.
  It opens the picker `m1plus_rgbtheme`: six check rows in two cards, Ambient (Candle, Wave) above
  Sample Rate. A two-line note above the first card describes the chosen theme's palette: "Red to
  blue to green as the sample rate rises" (Reference, Gentle Breathe, Lighthouse), "Rose to
  lavender to lime as the sample rate rises" (Heartbeat), "Warm amber, the same for every file"
  (Candle), "All colors in turn, the same for every file" (Wave).
- The setting file is `led-dynamic` ([settings](settings.md)): `0` or missing is off, `1` .. `6` is
  on with that theme.
- **Opt-in:** with the setting off the feature costs one compare of a cached int on the hook's
  path: no file, no timer, no lamp write.
- **Hook:** payload hook 31 ([payload](payload.md)) wraps the idle handler's play-status call and
  returns its result unchanged. With the setting on, it starts the module's timer if it is not
  running. All other work is the timer's.
- **Kill switch:** the card's kill switch makes the lamp stock's again.

The timer polls every 250 ms (`TL_POLL_MS`) and runs every 50 ms (`TL_FAST_MS`) while a theme other
than Reference plays or during the pause fade. While the lamp is stock's (nothing plays, the radio, a dark
screen with Follow Screen on) it polls every second (`TL_IDLE_MS`); the hook swaps in a 250 ms timer as
soon as a track starts or the screen comes on. What it shows, in order: the radio and a dark screen with Follow Screen on (stock's lamp),
USB DAC mode (the host's rate), else the player's rate. A DSD stream counts as its rate divided by
16, so DSD64 shows as 176.4 kHz.

**The lamp.** A channel has 18 levels (the level stock uses for its red). The lamp file is written
only when a level differs from stock's lamp state, in the format stock uses, so a fast timer does
not mean many writes. If stock changes the lamp under a playing track, the next tick writes the
theme's frame again.

**Letting go.** The lamp is stock's again when playback stops (after a short grace, so the gap
between tracks does not blink), 2.5 s after a pause (the frame fades first), with the kill switch,
with the radio, with a dark screen while Follow Screen is on, and when another LED Light choice is
made. The lamp then shows stock's mode-Off rule: red while external power is there and the battery
is not full, dark otherwise. While a track plays the theme wins over stock's red charging light.

**Themes** (default Reference):

| Theme | Colour | Movement |
|---|---|---|
| Reference | the rate's colour, palette 0 | none |
| Gentle Breathe | the rate's colour, palette 1 | 4 s: brightness up and down between 15 % and full |
| Heartbeat | the rate's colour, palette 2 | 1.6 s: a beat, a softer one (65 %), 0.9 s dark |
| Lighthouse | the rate's colour, palette 0 | 6 s: a 2 s rise to 65 %, a 0.2 s flash to full, a 2.8 s fall, 1 s dark |
| Candle | warm amber, the same for every file | brightness (55 .. 100 %) and warmth drift towards random targets |
| Wave | six colours around a wheel, the same for every file | 12 s a turn, full brightness |

A palette has ten colours, one per rate band (44.1, 48, 88.2, 96, 176.4, 192, 352.8, 384 kHz, up to
1411.199 kHz, above). Palette 0 runs from red-pink at 44.1 kHz through blue at 96 kHz to green at
the highest rates. A theme's clock stands still while paused.

## Limits

- The landscape Cover Flow and Cassette frames turn inside the page's portrait bitmap and map touch
  by hand. Nothing there reads the rotation word, so their frame and touch mapping under 180 degrees are
  unchecked.
