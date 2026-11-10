# Pull-down

Sources: `tools/mod_pulldown.py`, `tools/mod_icons.py` (look); `patch/pulldown.c`, `tools/pod.py` `PULLDOWN_*`, `tools/pod_pages.py` (tile order and page); tests `test/pod/pulldown.py` (look), `test/pod/pdtiles.py` (tiles).

## Look (`tools/mod_pulldown.py`, `mod_icons.py`)

Runs after the font step on `ui/dialog/dropdown_dialog.bin` (no style file):
its status bar (`view_sysbar`) is laid out from the same table as the real bar (`tools/statusbar.py`, section 4: volume number
16 px middle, clock 18 px at x 104, left group from x 10, right group 4 px, black), so the two are identical in 12 h and 24 h mode; the tile captions (`label_wifi`, `label_bt`, `label_lock`,
`label_gain`, `label_usbmode`, `label_outputway`, `label_playset`, `label_sysset`; word-wrapped)
18 -> 16 px normal, 16 -> 14 disabled/focused. The caption boxes are 71 x 40 instead of 57 x 40 (same centre,
x - 7; the tiles are 74 px apart), because `Bluetooth` is 60 px at 16 and AWTK broke it as "Bluetoot/h" and
"Playbac/k Setting". The tool now also refuses a Latin word wider than the box in English or Chinese. Nothing else
moves; alignment stays centred. Measured with
the text model: `100` at 16 px fits the 30 px label; `12:59 PM` is 66-72 px of 90; every English and
Chinese caption fits its box without a mid-word break (the tool refuses otherwise). 22 captions in other languages (long Russian, Ukrainian, Polish, Italian, Spanish, German words in
a 57 px tile) still overflow, as clipped in stock.
**Tile art:** every tile image is one 50x50 ring style, 2 px ring, 24 px glyph: off `#777777` ring +
glyph (`drop_wifi`, `bt`, `keylock`, `eq`, `lowgain`, `po`, `playset`, `sysset`), on a filled white disc +
`#141414` glyph (the `*open` images, `highgain`, `lo`, `usbaudio`, `usbdac`, `usbstorage`, the pressed
`playsetdown`/`syssetdown`), disabled `#444444` (`lowgaindisable`, `highgaindisable`). Gain uses custom
2-/5-bar glyphs, Output the text "PO"/"LO" in Inter Medium 17 px. White disc was chosen over a white ring
(only a brightness step from the grey ring; the disc is what stock does with its orange fill). With an accent the ON tiles' disc is the accent and the glyph stays `#141414` ([accent](accent.md), `ACCENT_DISC`).

## Tiles: hide, show and reorder (`patch/pulldown.c`)

Settings > System > Appearance > **Control Center** (iOS's name and translations; a link row in its own card on the Appearance page, `m1plus_appearance` `PAGES[40]`, under the Background and Accent card; our page `m1plus_pulldown`, `PAGES[41]`) edits the eight tiles of the stock pull-down
(`view_switchs`). It is the Main Menu page's twin ([menu](menu.md) "Main Menu"): one row per tile with a switch and, on every shown row but the first, an up arrow
(both pictures, insensitive); the row takes every tap and decides by where it landed (the arrow's rectangle moves the tile one place up, elsewhere it shows or
hides it; a tile shown joins the end). Shown tiles come first in order, hidden ones after them in stock order. Each change is saved at once and atomically; a
failed save is undone and the page stays as it was. The code is its own (`pg_*`, a copy of `menu.c`'s `cm_*` on eight rows; `menu.c` shares only `menu_plain_paint`).
Row labels are short texts of ours (`pod_pages.PULLDOWN_TILES`): Wi-Fi, Bluetooth, Button Lock, Gain, USB Mode, Output, Playback, System. The tiles' stock
captions ("Playback Setting", "Output Options", up to 256 px in Russian) did not fit beside the arrow, and Gain and USB Mode show the state in stock
(High / Low, USB AUDIO / DAC / Storage). Each row has its tile's glyph, the Main Menu page's 24 px row glyph (`mod_icons.POD_ROWS`, page in `POD_UI`): wifi, bluetooth,
lock, the gain bars, usb, headphones for Output (its tile shows the text PO / LO; stock's Output setting uses headphones), sliders for Playback, the gear for System. The label is then 135 px;
`test/pod/i18n.py` measures every label in all 13 languages, and the one that does not fit, Russian Playback (Воспроизведение, 158 px), ends in an ellipsis and scrolls while focused
(accepted). The Settings row's glyph is Lucide `layout-grid`.

**File** `/mnt/data/m1plus/pulldown-tiles`: `<shown ids in order>[-<hidden ids>]` and an optional newline, ids `0`-`7` in stock slot order (Wi-Fi, Bluetooth, buttons
lock, gain, USB mode, output, playback settings, system settings). A tile not in the shown part is hidden. Invalid or missing = the default, all eight shown in stock
order: an unknown character, an id twice (also across the parts), a second `-`, an empty file, 12 bytes or more. A bare newline or `-` hides all eight. The page writes
`<shown>-<hidden in stock order>`. Model `pod_pages.parse_pulldown` / `format_pulldown`; the Settings Files page lists the file (first 12 characters, like `home-menu`).

## The hook

`dialog_dropdown_dialog_init` `0x475f04`, pinned prologue `(0x3c1c0059, 0x279cdfcc, 0x0399e021)` (`$gp` checked), overwritten with `j m1plus_pulldown_init; nop`;
the trampoline resumes at `0x475f10` (`beqz $a0`). Its only caller is the navigator's dialog-init dispatcher (`0x4d1c7c` / `0x4d1c84`, behind the `strcmp` with
`"dialog/dropdown_dialog"`; the other reference to the name, `on_wm_tsmove_fun` `0x4cd868`, opens the dialog by name), so it runs only when the pull-down is built;
`tools/reach.py` finds it only behind the navigator cut, never from `main` / `platform_init`. `tools/pod.py` `PULLDOWN_PINS` pins the resume word, the dispatcher, the
four pointer binds of the init and the tile visitor's `EVT_CLICK` bind. The stock init runs first and its result is returned; then the eight tile images (`img_wifiswitch`, `img_btswitch`, `img_keylockswitch`, `img_gainswitch`, `img_usbmode`, `img_outputswitch`, `img_playset`,
`img_sysset`) and captions (`label_wifi`, `label_bt`, `label_lock`, `label_gain`, `label_usbmode`, `label_outputway`, `label_playset`, `label_sysset`) are looked up and
their places read; **if any lookup fails nothing changes**. The file is read; shown tile k takes the place of stock tile k (images x 24 / 98 / 172 / 246, y 14 and 114,
read from the widgets) and its caption keeps its own offset from its tile (stock: -10, +54, boxes 71 x 40); the other tiles and captions get `visible=false` **and**
`sensitive=false`. The default file moves nothing. No widget is renamed or deleted; the dialog's size, the status bar and the brightness slider stay.

**Constraints.** The stock handlers find the tiles by name and set their images and captions, so a moved or hidden tile keeps working (gain, output, USB and
Wi-Fi/Bluetooth state still update; on a hidden tile nobody sees it). The stock code never sets a tile's visibility or position (`widget_set_visible` / `widget_move`
appear only for the status bar and the dialog's own drag). The dialog binds pointer events only (`0xff` down, `0x101` move, `0x103` up for the drag-to-close,
`0x12e`, and `EVT_CLICK` on the tile images): no key event is bound and the tile images are plain `image` widgets with no focus handling, and `set_dialog_highlight`
only sets the dialog's `highlight` property (the dim). Hardware keys therefore neither move a highlight across the tiles nor activate one; a hidden tile can
only have been hit by a touch, which `sensitive=false` stops (this AWTK hit-tests hidden widgets, [UI rules](ui-rules.md)). The dialog keeps its stock height, so hiding
tiles leaves empty room; resizing it and the slider is out of scope here. Replacement actions for the freed slots are not part of this.

**Tests** (`test/pod/pdtiles.py`): the hook words, the manifest and the pins; the built assets' grid; the stock layout for no file, the default, ten
kinds of invalid file, a failed stock init, a null dialog and each of the sixteen widgets missing (nothing moved, hidden or re-stacked); a custom
order, some hidden, hidden-part variants, all hidden (positions at the stock places, captions at their offset, hidden = invisible and insensitive, nothing renamed);
300 random files against the Python parser; the Settings page (layout from a saved file, taps, arrows, atomic saves, failed save or rename undone, scroll, a page
that is not ours, the row in the Settings page, the asset's rows) and the Settings Files row. Device: [UI-04](device-checks.md).

## Settings tiles and the window stack (`pd_reconcile`, `pd_open_settings`)

Stock marks "inside settings" in `syssetinto_flag` (`0xa05a48`, System Settings) and `playsetinto_flag` (`0xa05a4c`, Playback Settings): the page inits (`0x4ada78`, `0x4a0c88`) store 1, the Back handlers (`0x4ad550`, `0x49fec0`) clear a positive flag and
Home's foreground callback (`0x534b88`) clears both. The tile visitor (`0x473f30`) disables a tile and skips its click bind while its flag is positive; the tile handlers (`0x4754c8` System, `0x475558` Playback) do nothing for a nonzero flag and
otherwise (also after the USB / network-mode tests) store 2 and quit the dialog, and `on_wm_tsmove_fun` (`0x4cd7f0`) then opens the page by `navigator_to` for a flag of 2. The top-right Now Playing button (`on_backtoplayer_onclick`) calls
`navigator_switch_to_with_context("playing_page", ctx, 0)`: the player is opened or restacked over the page and **nothing is closed**, so the settings window stays in the window stack behind the player with its flag set (Back from the player
returns to it). Both tiles then stayed disabled on the player and everywhere else until Home cleared the flags (user report, release 1.3; System Settings -> Playback sub-page -> Now Playing leaves both).

The windows are named `sysset_page` and `playset_page` (the assets' roots; `navigator_to` opens them by `systemset/sysset_page` / `playset/playset_page`, which is not their window name, so stock's open never finds a page already in the stack).
`m1plus_pulldown_init` first makes the flags match the window stack (`pd_reconcile`, two words, before the stock init reads them): a page is **inside settings** (flag 1) when its window is in the window manager, opened, and none of
`playing_page`, `m1plus_radionp` (Radio Now Playing) or `home_page` is above it (windows between it and the front are its sub-pages); otherwise (no window, or the player or Home above it, or a flag left at 2) the flag is 0. A page in front
is therefore stock (its tile disabled, also when the user comes back to it from the player and the flag had been cleared), and a page behind the player has its tile enabled and bound by stock's own visitor, whose handler does what it always does.
The two `navigator_to` calls of `on_wm_tsmove_fun` that open the chosen page are `pd_open_settings` (payload hook 22): when the page's window is still in the stack it is brought to the front with `pod_restack_window` (`patch/common.c`, shared through `pod_open_stock` with the More sheet's Sleep Timer row and the Settings Display row, [playmore.md](playmore.md): the topmost opened window of that name, `window_manager_switch_to(wm, top window, page, 0)`)
(what stock does for the player; Back then returns to the player) and its flag set to 1 (no init runs); otherwise, or if the restack fails, stock's `navigator_to(name)` (the init sets the flag), and a failed open clears the flag instead of leaving 2.
No flag is touched on a Now Playing tap, in the main loop or on paint; Home's reset is unchanged. Tests: `flags_tests` in `test/pod/pdtiles.py` (both pages and both visit orders, repeated cycles, Radio Now Playing, no window, a failed open or restack,
the pins and call sites). Device check: [UI-04](device-checks.md).
