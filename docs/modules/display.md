# Display

Sources: `patch/display.c`, `tools/pod_pages.py` (`DISPLAY_PAGE`), tests `test/pod/display.py`. Part of [settings](settings.md); the Lock Screen row opens [lockscreen](lockscreen.md).

Settings > System > Display (`m1plus_display`, `DISPLAY_PAGE`, `patch/display.c`) replaces stock's Display list and its four pages with one cards page of three cards: the brightness slider; **Screen Timeout** and **Lock Screen** (a link to our [Lock Screen](lockscreen.md) page); **LED Light** alone (its page holds the lamp choices, **Follow Screen** and the Dynamic theme). No row opens a stock page, every state is stock's own and nothing of ours is saved. Stock's pages stay under All System Settings and show the same state.

## Brightness

A card of a row's height with the pull-down's control in it, the small sun (`drop_lighticon0`) in the glyph column, the slider from the label column (200 x 50: the pull-down slider's 6 px track and fill, `drop_bg` / `drop_fg`, so the fill takes the accent, under a white capsule thumb of our own, `pod_sl_thumb`, 38 x 24 with a soft shadow, `tools/mod_icons.py slider_thumb`) and the large sun at the card's right padding. The view is `pod_bright`, built by `pod_pages.Brightness` and `tools/pod_ui.py cards_brightness`. The slider is named `slider_brightness` with stock's range 0 .. 100, and a hidden, insensitive `label_brightness` is beside it, because the code behind it is stock's: `disp_opened` calls stock's refresh `0x4a4450(window)` (it looks both widgets up by name, writes the percentage and sets the slider from the word `lightness`, `0x97caf0`) and then binds stock's two handlers to the slider with the window as their context, as stock's `systemset/brightness_page` does (`0x4a43ac..0x4a43d8`): `0x4a4744` on `EVT_VALUE_CHANGING` (0x11d: the word, `backlight_changeflag` 1, the refresh, `reset_poweroptions_timer(1, 1, 1)`) and `0x4a4678` on `EVT_VALUE_CHANGED` (0x11c: the flag 0, the word, `toolSetBackLight(value + 1)`, `write_int_config(value, "SYSSET", "LIGHTNESS")`, the refresh, the timers). The payload repeats none of it. The refresh runs again each time the page is back in front (`disp_refresh`), so the slider follows the pull-down's. The card is a sensitive view (stock's hit test does not look into an insensitive parent) with nothing bound; a page without either widget binds and calls nothing.

## LED Light and Follow Screen

**LED Light** is stock's lamp mode, the byte `atmosphereled_mode` (`0xa05a75`, `LED_MODE`; `[SYSSET] ATMOSPHERELEDMODE`, `config_init` keeps 0 .. 2): 0 off, 1 green, 2 blue. Stock names mode 1 orange (`img_orange`, `led_orange.png`), but the lamp is green: `reset_atmosphereled_rgb` sets only the green channel for it (13; saved as `LEDGREEN`) and the image is a green disc. A value row (`ACT_LED` 99) and the picker `m1plus_ledlight` (`ACT_LEDSET` 100: Off, Green, Blue). `disp_led_set` does what stock's `systemset/atmosphereled_page` handlers do: the navbar switch `0x4a1c30` stores 0 (from non-zero) or 1 (from 0, so on is green), `img_orange` `0x4a1e14` stores 1 and `img_blue` `0x4a1d8c` stores 2 unless it is the mode already, and each then calls `write_int_config(mode, "SYSSET", "ATMOSPHERELEDMODE")` and `reset_atmosphereled_rgb()` (`0x4e6b9c`). Blue from off is one step on our page (stock: the switch, then the colour). **Follow Screen** (`ACT_LEDFOLLOW` 101, a switch row on the LED Light page, in a card of its own under the choices, with no glyph like the Theme row) is stock's switch of that name: `disp_follow_toggle` stores the byte `ledfollowscreen_flag` (`0xa05a74`) xor 1 and then calls `write_int_config(new, "SYSSET", "LEDFOLLOWSCREEN")`, as stock's `0x4a1940` does (the byte in the call's delay slot), and nothing else. The row stays usable while the lamp is off (stock hides it then).

## Sample Rate

A fourth LED Light choice, shown as **Dynamic** (the user-facing name: two of the themes do not show the rate; `ACT_LEDSET` argument 3; `patch/tracklamp.c`, constants in `patch/tracklamp.h`; contributed in PR #5). The lamp shows the playing track's sample rate as a colour. Choosing it saves the setting and sets stock's lamp mode to 0 (so stock lights nothing of its own); it opens no page. While Dynamic is the chosen lamp the LED Light page shows one more row in a card of its own, Theme, below the Follow Screen card (a hidden row keeps the gap before it, so Theme comes last and nothing moves when it shows; the page's spacers are fixed). The row is (`ACT_RGBROW` 143, a value row whose value is the theme's name), which opens the picker `m1plus_rgbtheme` (titled Theme: six check rows `ACT_RGBTHEME` 140 in two cards, Ambient (Candle, Wave) above Sample Rate, with a one-line note under the last card, the Sample Rate card: the colour changes with the file's sample rate; the page may be a little taller than one screen); `page_refresh` (`patch/m1plus.c`) shows or hides the row, like the Regenerate Daily Mix row, each time a choice is made and each time the page is back in front. Choosing Off, Green or Blue saves `0`, lets the lamp go and then does what the stock choice does. The one setting file is `led-dynamic` ([settings](settings.md)): `0` or missing is off, `1` .. `6` is on with the theme of that row.

**Opt in.** Off (the default) the feature costs one compare of a cached int on the hook's path and nothing else: no file, no timer, no lamp write. Everything below runs only after the user chose Dynamic.

**The hook** (payload hook 30, [payload](payload.md)): `tl_play_status` replaces `on_wm_idle_status`'s call of `mclGetPlayStatus` (`0x4ce968`) and returns its result unchanged. `on_wm_idle_status` is an AWTK idle (`idle_add`, `home_page_init` `0x535048`), so the function runs on every pass of the main loop. With the setting on it does one more thing: when the module's timer is not running it adds it. All other work is the timer's.

**The timer** (`tl_tick`, one AWTK timer). Every `TL_POLL_MS` (250 ms) it asks what to show: the card's kill switch (`access`), Follow Screen with a dark screen, the radio, then USB DAC mode (`POWER_USBSTATE` 2 and `POWER_FLAG` 1: the host's rate from `/sys/class/uac2/uac2_samprate`) or the player (`mclGetPlayStatus` 2: `mclGetInfo`'s rate; a DSD stream, known by 1 bit, the codec's name or the file's extension, counts as its rate divided by 16, so DSD64 shows as 176.4 kHz). Every tick it draws the theme's frame. The timer runs `TL_FAST_MS` (50 ms) apart while a theme other than Reference plays and during the pause fade, and `TL_POLL_MS` apart otherwise; it changes pace by ending and adding a timer at the new one. When the setting goes off the timer ends on its next tick.

**The lamp.** A channel has 18 levels (0 .. `TL_LEVEL` 17, `0x11`, the level stock uses for its red). A frame is a colour (each channel 0 .. 100) and a brightness (0 .. 100), rounded to levels; the lamp file is written only when a level differs from stock's lamp state, so a fast timer does not mean many writes (Gentle Breathe: about 10 a second at most). It is written as stock's `config_atmosphere_light` (`0x4e6fec`) writes it, the decimal number `r << 16 | g << 8 | b` to `/sys/class/led_ktd2026/led_config_rgb`, but with `open` / `write` (stock runs `echo` through `system`), and stock's lamp state (`0xa038b8`: red, blue, green, a pending byte its 100 ms timer `0x4cff40` acts on) is set to the same levels with the pending byte 0. If stock changes the lamp under a playing track (power is plugged in), the next tick writes the theme's frame again.

**Letting go.** The lamp is stock's again when playback stops (after `TL_GONE` 4 polls, so the gap between two tracks does not blink), `TL_PAUSE_MS` (2.5 s) after a pause (the frame first fades to a fifth in `TL_FADE_MS` 500 ms, and a moving theme stands still), with the kill switch, with the radio, with a dark screen while Follow Screen is on, and when another LED Light choice is made. The module then shows what stock shows with its mode Off, the first rule of `reset_atmosphereled_rgb` (`0x4e6b9c`, pinned): red at level 17 while external power is there (`POWER_EXT` 1) and `pmucharge_status` (`0xa059e8`) is not 2 (full), dark otherwise. Stock's function itself is not called, because it also saves `LEDRED` / `LEDGREEN` / `LEDBLUE` to the config every time. While a track plays the lamp shows the theme, so stock's red light for external power does not show then.

**Themes** (`TL_REFERENCE` .. `TL_OCEAN`, 0 .. 5; Reference, 0, is the default). The Theme page lists Ambient (Candle, Wave) first and Sample Rate (the other four) under it; a row's argument is its theme, and `pick_chosen` compares the argument, so the order of the rows does not matter.

| Theme | Colour | Movement |
|---|---|---|
| Reference | the rate's colour, palette 0 | none |
| Gentle Breathe | the rate's colour, palette 1 | 4 s: brightness up and down between 15 % and full |
| Heartbeat | the rate's colour, palette 2 | 1.6 s: a beat, a softer one (65 %), 0.9 s dark |
| Lighthouse | the rate's colour, palette 0 | 6 s: a 2 s rise to 65 %, a 0.2 s flash to full, a 2.8 s fall, 1 s dark |
| Candle | red over a little green (its own) | brightness (55 .. 100 %) and warmth walk a step a tick towards random targets |
| Wave | six colours around a wheel (its own) | 12 s a turn, full brightness |

A palette has ten colours, one per rate band: up to 44.1, 48, 88.2, 96, 176.4, 192, 352.8, 384 kHz, up to 1411.199 kHz, above. Palette 0 runs from red-pink (44.1 kHz) through blue (96 kHz) to green (the highest rates). A theme's clock stands still while paused and starts again when the theme is chosen.

**Tests:** `test/pod/tracklamp.py`: `hook_tests` (off: stock's call alone on every pass; on: one timer, the poll's pace), `colour_tests` (every band, DSD, USB DAC mode, a failed lamp write, stock changing the lamp), `theme_tests` (each theme's range and pace; Gentle Breathe, Candle and Wave never skip a level), `pause_tests` (the fade, the stop's grace, the kill switch, Follow Screen, the radio, what the let-go lamp shows), `setting_tests` (the file, LED Light's four modes, the picker).

**Not verified on a device:** every part of this section (the colours on the real lamp, the timer's cost, Follow Screen, USB DAC mode, the let-go rule).

## Screen Timeout

Screen Timeout is stock's backlight time: a value row (`ACT_LIGHT` 97) and the picker `m1plus_lighttime` (`ACT_LIGHTSET` 98, the argument is stock's index) with stock's five choices in stock's order: Never (index 0; our key, stock's English is "Off"), `15s`, `30s`, `1min`, `5min` (stock's plain texts, the same in every language). The state is the word `backlighttime_mode` (`0xa05a7c`, `LIGHT_MODE`), which `config_init` loads from `[SYSSET] LIGHTTIME` (`0x4e60d4`; a value outside 0 .. 4 becomes 0). `disp_light_set` repeats a row of stock's `systemset/lighttime_page`: each row's click handler (`0x4a8708` row 1 .. `0x4a8578` row 5) returns when its index is the word already, else calls the shared `0x4a8410` (the row images, then the word stored before `write_int_config(index, "SYSSET", "LIGHTTIME")`) and then `reset_poweroptions_timer(0, 0, 1)`, which sets the screen's countdown from the new word (`setlight_time` `0x4d77f4`).

## Pins and tests

Every word relied on is pinned (`LOCKSCREEN_PINS`). `test/pod/display.py` runs stock's handlers under the emulator on the same state and compares the stored value and the calls with ours: the five backlight rows for all 25 changes, the lamp's switch and two colours for every change stock's page can make, Follow Screen both ways; for brightness it checks the bindings and runs stock's refresh and both handlers on our widget names. Not verified on a device: the slider's drag inside the list.

## State

The Display rows of the persisted choices (the files and values are the ones in [settings](settings.md) "Persisted choices"; nothing of these is saved by us).

| Setting | State | Values/default |
|---|---|---|
| Display > brightness slider | none: stock's `[SYSSET] LIGHTNESS` (the word `lightness`) | 0 .. 100, written by stock's own slider handlers (see Brightness above) |
| Display > Screen Timeout | none: stock's `[SYSSET] LIGHTTIME` (the word `backlighttime_mode`) | 0 never, 1 15 s, 2 30 s, 3 1 min, 4 5 min; the same choice as stock's backlight time page (see Screen Timeout above) |
| Display > LED Light | none: stock's `[SYSSET] ATMOSPHERELEDMODE` (the byte `atmosphereled_mode`) | 0 off, 1 green, 2 blue |
| Display > LED Light > Follow Screen | none: stock's `[SYSSET] LEDFOLLOWSCREEN` (the byte `ledfollowscreen_flag`) | 1 on, 0 off |
