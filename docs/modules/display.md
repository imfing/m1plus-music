# Display

Sources: `patch/display.c`, `tools/pod_pages.py` (`DISPLAY_PAGE`), tests `test/pod/display.py`. Part of [settings](settings.md); the Lock Screen row opens [lockscreen](lockscreen.md).

Settings > System > Display (`m1plus_display`, `DISPLAY_PAGE`, `patch/display.c`) replaces stock's Display list and its four pages with one cards page of three cards: the brightness slider; **Screen Timeout** and **Lock Screen** (a link to our [Lock Screen](lockscreen.md) page); **LED Light** and **Follow Screen**. No row opens a stock page, every state is stock's own and nothing of ours is saved. Stock's pages stay under All System Settings and show the same state.

## Brightness

A card of a row's height with the pull-down's control in it, the small sun (`drop_lighticon0`) in the glyph column, the slider from the label column (200 x 50: the pull-down slider's 6 px track and fill, `drop_bg` / `drop_fg`, so the fill takes the accent, under a white capsule thumb of our own, `pod_sl_thumb`, 38 x 24 with a soft shadow, `tools/mod_icons.py slider_thumb`) and the large sun at the card's right padding. The view is `pod_bright`, built by `pod_pages.Brightness` and `tools/pod_ui.py cards_brightness`. The slider is named `slider_brightness` with stock's range 0 .. 100, and a hidden, insensitive `label_brightness` is beside it, because the code behind it is stock's: `disp_opened` calls stock's refresh `0x4a4450(window)` (it looks both widgets up by name, writes the percentage and sets the slider from the word `lightness`, `0x97caf0`) and then binds stock's two handlers to the slider with the window as their context, as stock's `systemset/brightness_page` does (`0x4a43ac..0x4a43d8`): `0x4a4744` on `EVT_VALUE_CHANGING` (0x11d: the word, `backlight_changeflag` 1, the refresh, `reset_poweroptions_timer(1, 1, 1)`) and `0x4a4678` on `EVT_VALUE_CHANGED` (0x11c: the flag 0, the word, `toolSetBackLight(value + 1)`, `write_int_config(value, "SYSSET", "LIGHTNESS")`, the refresh, the timers). The payload repeats none of it. The refresh runs again each time the page is back in front (`disp_refresh`), so the slider follows the pull-down's. The card is a sensitive view (stock's hit test does not look into an insensitive parent) with nothing bound; a page without either widget binds and calls nothing.

## LED Light and Follow Screen

**LED Light** is stock's lamp mode, the byte `atmosphereled_mode` (`0xa05a75`, `LED_MODE`; `[SYSSET] ATMOSPHERELEDMODE`, `config_init` keeps 0 .. 2): 0 off, 1 green, 2 blue. Stock names mode 1 orange (`img_orange`, `led_orange.png`), but the lamp is green: `reset_atmosphereled_rgb` sets only the green channel for it (13; saved as `LEDGREEN`) and the image is a green disc. A value row (`ACT_LED` 99) and the picker `m1plus_ledlight` (`ACT_LEDSET` 100: Off, Green, Blue). `disp_led_set` does what stock's `systemset/atmosphereled_page` handlers do: the navbar switch `0x4a1c30` stores 0 (from non-zero) or 1 (from 0, so on is green), `img_orange` `0x4a1e14` stores 1 and `img_blue` `0x4a1d8c` stores 2 unless it is the mode already, and each then calls `write_int_config(mode, "SYSSET", "ATMOSPHERELEDMODE")` and `reset_atmosphereled_rgb()` (`0x4e6b9c`). Blue from off is one step on our page (stock: the switch, then the colour). **Follow Screen** (`ACT_LEDFOLLOW` 101, a switch row) is stock's switch of that name: `disp_follow_toggle` stores the byte `ledfollowscreen_flag` (`0xa05a74`) xor 1 and then calls `write_int_config(new, "SYSSET", "LEDFOLLOWSCREEN")`, as stock's `0x4a1940` does (the byte in the call's delay slot), and nothing else. The row stays usable while the lamp is off (stock hides it then).

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
| Display > Follow Screen | none: stock's `[SYSSET] LEDFOLLOWSCREEN` (the byte `ledfollowscreen_flag`) | 1 on, 0 off |
