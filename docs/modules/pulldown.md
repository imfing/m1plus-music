# Pull-down

**Sources:** `tools/mod_pulldown.py`, `tools/mod_icons.py` (look), `patch/pulldown.c`,
`tools/pod.py` (`PULLDOWN_*`), `tools/pod_pages.py` (tile order and page), `PULLDOWN_PINS`,
`PULLDOWN_FLAG_PINS`, `TSDOWN_PINS` in `tools/pod_pins.py`.

The stock pull-down (`dialog/dropdown_dialog`) restyled, with tiles the user can hide, show and
reorder, eight tiles of ours, and two repairs for a pull-down that stops opening. One hook on the
dialog's init and one on touch down ([payload](payload.md)).

## Look

`mod_pulldown.py` runs after the font step on `ui/dialog/dropdown_dialog.bin`.

- The status bar (`view_sysbar`) is laid out from the same table as the real bar
  ([theme](theme.md) "Status bar"), so the two are identical in 12 h and 24 h mode.
- **Panel:** the dialog's background is black at 92 % opacity (`mod_pulldown.PANEL_ALPHA`, stock
  `#141414`), so the page below shows faintly through its own dimming. The status bar copy keeps
  the real bar's opaque black. Cards and discs are opaque.
- **Brightness card:** stock's `view_backlight` (its black pill image `backlight_bg` and corner styles
  removed), a flat `#1C1C1E` card, radius 26, 300 x 52 at x 10 .. 310, y 265 .. 317 (stock 300 x 50 at
  266). It holds stock's own `image0`, `image1` and `slider_backlight` by name (range, value and
  handlers are stock's), laid out by `pod_ui.bright_control`, the same code that builds the
  [Display](display.md) page's brightness card: suns at x 14 and 266 in the card, slider x 48 .. 248
  (200 wide), 6 px `drop_bg` / `drop_fg` track and fill, the white capsule thumb `pod_sl_thumb`.
  The slider keeps stock's screen y 266 .. 316 (the card is one px taller at the top and 1 at the
  bottom); the card sits 17 px under a two-row caption's last row and 11 px over the grabber (y 328).
  `mod_pulldown.restyle_backlight` pins the stock geometry and refuses anything else.
- **Tile layout:** the tile images are 56 x 56 (stock 50) round the stock centres, columns x 21 / 95
  / 169 / 243, rows y 11 and 111 in view_switchs (screen 51 and 151; 100 apart as stock). The discs sit
  directly on the panel, no card under them. The hook reads positions from the widgets, so it did not change.
- **Captions:** the stock keys and texts, 16 px `#B0B0B0` (disabled `#555555`; stock 18 / 16 px
  white), 71 x 36 boxes centred on the tile, top aligned, 5 px under the disc, word-wrapped (two
  lines fit). AWTK wraps a label to its box less the left and right margins and drops a row that
  ends below the bottom margin; rows are the font + spacer 2 apart and every margin defaults to 2.
  The captions set the left, right and bottom margins to 0 (`mod_pulldown.CAP_MARGINS`), so the
  text is 71 px wide and two 16 px rows need 2 + 16 + 2 + 16 = 36 px. `Bluetooth` is 60 px at 16, which AWTK broke mid-word in a 57 px box; the 71 px box
  stays. The tool refuses a Latin word wider than the box, or a caption that does not fit two
  lines, in English or Chinese. A few long captions in other languages still overflow, clipped as
  in stock.
- **Tile art:** every tile image is one flat 56 x 56 disc, 26 px glyph, no ring. Off is a `#2C2C2E`
  disc with a white glyph, on a white disc with a `#141414` glyph, disabled a `#1E1E1E` disc with a
  `#555555` glyph. Gain has custom 2- and 5-bar glyphs, Output the text "PO" / "LO" in Inter Medium
  20 px. With an accent the ON disc is the accent ([accent](accent.md)).
- **Grabber:** `pod_grabber`, an image widget showing `drop_grabber` (a baked, antialiased 36 x 5 pill) at
  (142, 328) in the dialog, white at alpha 110 like Now Playing's grabber (`mod_icons.GRABBER`, the `ghost` tone), insensitive.

## Tiles: hide, show and reorder

Settings > Appearance > **Control Center** (`m1plus_pulldown`) edits the eight stock tiles and the
eight of ours (sixteen rows, at most eight shown). It is the Main Menu page's twin ([menu](menu.md)):
one row per tile with a switch and, on every shown row but the first, an up arrow. The row takes
every tap: the arrow moves the tile one place up, elsewhere shows or hides it, and a tile shown joins
the end. Each change is saved at once and atomically; a failed save is undone. The code is a copy of
`menu.c`'s (`pg_*`).

- Row labels are short texts of ours: Wi-Fi, Bluetooth, Button Lock, Gain, USB Mode, Output,
  Playback, System. Stock captions did not fit beside the arrow, and Gain and USB Mode show state in
  stock. Each row has its tile's 24 px glyph. The one label that does not fit (Russian Playback)
  ends in an ellipsis and scrolls while focused.
- Turning on a ninth tile is refused with the toast "Up to 8 controls".

**File** `/mnt/data/m1plus/pulldown-tiles`: `<shown ids in order>[-<hidden ids>]`, optional newline.
Ids `0`-`7` are the stock slots in order (Wi-Fi, Bluetooth, button lock, gain, USB mode, output,
playback settings, system settings); ours are `8` Sleep Timer, `9` Settings, `a` Equalizer,
`b` Power Off, `c` AirPlay, `d` DLNA, `e` Wi-Fi Transfer. A tile not in the shown part is hidden.

- Invalid or missing means the default: the eight stock tiles in stock order, ours hidden. Invalid
  is an unknown character, an id twice, a second `-`, an empty file, 20 bytes or more
  (`PULLDOWN_FILE_MAX`) or more than eight shown. A bare newline or `-` hides every tile.
- The page writes `<shown>-<hidden in id order>`. Model: `pod_pages.parse_pulldown` /
  `format_pulldown`. The Settings Files page lists the file (first 12 characters, like `home-menu`).

## The hook

`dialog_dropdown_dialog_init` is wrapped by `m1plus_pulldown_init` (pinned prologue, resumed by the
trampoline). Its only caller is the navigator's dialog-init dispatcher, so it runs only when the
pull-down is built and is never boot-reachable. `PULLDOWN_PINS` pins the resume word, the
dispatcher, the pointer binds and the tile visitor's click bind.

- The stock init runs first and its result is returned. Then the eight tile images and captions are
  looked up; **if any lookup fails nothing changes**.
- Without the kill switch, after the tiles: `bp_pulldown` fills the bar copy's Battery Percentage label and
  `lo_bar_refresh` sets its EQ mark and sleep timer icon (stock's face call has by then set `img_digital`), so all are in the
  first frame instead of one timer tick later.
- Also without the kill switch, `pd_clock` gives the bar copy's clock (`bar_dclock`, asset format
  `hh:mm`, 24 h) the real bar's 12 h format `HH:TT` (`9:41 AM`) when 24-Hour Time is off. Stock's
  switch (`change_time24h_12h`) only formats the real bar, so on stock the copy is 24 h whatever the setting.
- The file is read. Shown tile k takes the place of stock tile k (positions read from the widgets)
  and its caption keeps its own offset; the other tiles and captions get `visible=false` **and**
  `sensitive=false`. When **Control Labels** (Settings > Appearance, `/mnt/data/m1plus/pulldown-labels`,
  `0` off, missing/other on) is off, all sixteen tile captions get `visible=false` and `sensitive=false`
  while the discs stay in their stock positions. The default files move nothing. No widget is renamed or deleted.
- Stock handlers find tiles by name, so a moved or hidden tile keeps working. Stock code never sets
  a tile's visibility or position. The dialog binds pointer events only, so hardware keys cannot
  reach a hidden tile; `sensitive=false` stops a touch (this AWTK hit-tests hidden widgets,
  [ui-rules](ui-rules.md)).
- The dialog keeps its stock height, so hiding tiles leaves empty room.

## Settings tiles and the window stack

Stock marks "inside settings" in two flags (`syssetinto_flag`, `playsetinto_flag`). The page inits
set them to 1, Back clears them and Home's foreground callback clears both. The tile visitor
disables a tile and skips its click while its flag is positive. The Now Playing button opens the
player over the page and closes nothing, so the settings window stays in the stack with its flag
set. Both tiles then stayed disabled everywhere until Home cleared the flags.

- **Reconcile.** `m1plus_pulldown_init` first makes the flags match the window stack
  (`pd_reconcile`). A page is inside settings (flag 1) when its window is in the stack and none of
  `playing_page`, `m1plus_radionp` or `home_page` is above it; otherwise 0. So a page in front is
  stock (its tile disabled), and a page behind the player has its tile enabled.
- **Open.** The two `navigator_to` calls in `on_wm_tsmove_fun` are `pd_open_settings` (payload hook
  22). If the page's window is still in the stack it is brought to the front with
  `m1_restack_window` ([playmore](playmore.md)) and its flag set to 1; otherwise, or if the restack
  fails, stock's `navigator_to` runs, and a failed open clears the flag.
- **The Playback tile opens our page** ([playset](playset.md)): restacked if in the stack, else
  opened like the Settings row, and stock's list only when ours will not open. `pd_reconcile` treats
  either window as the Playback page; the hub's sub-pages (Volume & Sound, Output) and their pickers are windows above it, so the tile is disabled over them too. Before restacking, its sub-pages left in the stack are closed
  (`pd_close_subpages`), because a page of ours keeps one window and a second instance would leave
  the first without its refresh. The System tile is unchanged.
- **Opener table** (`pd_op`, `patch/pulldown.c`): 16 `(window, opener)` pairs in `.scratch`, no
  allocation. `open_page` (`patch/m1plus.c`) records the window in front as the opener of every page
  it opens (a row tap is on the page in front); the Volume status bar tap and the Equalizer tile
  record NULL ("rooted": opened by no page). An entry is cleared by its window's `EVT_DESTROY`,
  which also turns the entries opened from it into orphans; a full table drops the entries of
  windows that are gone first, and a window left without an entry is nobody's child (never closed).
  `pd_open_page(window, open_it, rooted)` is the one policy for the Equalizer and Wi-Fi Transfer tiles (and the Wi-Fi Transfer row), the Wi-Fi and Bluetooth tile long presses (and their Settings / stock hub rows), the Volume tap,
  the Volume page's rows and Settings' Gain / Equalizer / Volume & Sound rows: in front, left alone;
  else every window whose opener chain leads to it is closed (wherever it sits in the stack, and
  nothing else), then it is restacked, else opened. Restacking re-records the opener: the page in
  front for a row tap, NULL for a tile or the status bar.
  `pd_open_own` (Sleep Timer, Settings tiles) and the Playback tile (`pd_close_subpages`) still close
  the windows above their page, as before, except a window that hangs from a rooted one (the Volume
  page or Equalizer a tile or the status bar opened over it, and what those opened): reproducible
  with Volume over Settings, so Back returns to it. `pd_open_own` records its page as rooted too:
  a tile's page is not the sub-page of the window that was in front (Volume, then the Settings
  tile, then the status bar keeps Settings); so does the Playback tile (`pd_open_settings`).
  `pd_window_open` is `window_open` plus the opener record: `open_page`, the AutoEq page and the
  keyboard open through it, so a window above a reopened page is closed with it (Equalizer >
  Presets > Download from AutoEq, then the Equalizer tile).
- No flag is touched on a Now Playing tap, in the main loop or on paint.

## Tiles of ours

Eight tiles can take any of the eight slots (hidden by default): six are actions, two are switches.

| Id | Tile | Art (`mod_icons.PD_OWN`) | Action |
|---|---|---|---|
| `8` | Sleep Timer | `drop_sleep` / `drop_sleepopen` (Lucide `moon`) | our Sleep Timer page ([sleeptimer](sleeptimer.md)) via `pd_open_own`; lit (`drop_sleepopen`, in `ACCENT_DISC`) while a timer is running (`sleepflag != 0` and `sleep_time > 0`); a page behind the player is restacked, one in front is left alone |
| `9` | Settings | `drop_settings` (`layout-grid`) | our Settings root (`pod_open_settings`) |
| `a` | Equalizer | `drop_equalizer` (`sliders-vertical`) | our Equalizer page (`pod_open_peq`) |
| `b` | Power Off | `drop_power` (`power`) | the power key's long-press confirm, then `poweroff_page` ([Power Off](#power-off)) |
| `c` | AirPlay | `drop_airplay` / `drop_airplayopen` | a switch ([AirPlay and DLNA](#airplay-and-dlna)) |
| `d` | DLNA | `drop_dlna` / `drop_dlnaopen` (Simple Icons mark) | a switch |
| `e` | Wi-Fi Transfer | `drop_transfer` (`folder-sync`) | Wi-Fi Transfer page ([wifi-transfer](wifi-transfer.md)): `ns_transfer_ok()` (a toast "Connect to Wi-Fi first" and nothing else when offline), then `pd_open_page` (rooted) with `pod_open_wifitransfer`, as Network Services' row does, so both open one window; a page behind the player is restacked, and its `EVT_WINDOW_TO_FG` (`wt_front`) restarts the file server without a second `wt_opened` |
| `f` | Screenshot | `drop_shot` (`camera`) | `shot_start()` ([screenshot](screenshot.md)): the same two-step confirm as Settings > Developer > Screenshot, no page; a second tap while counting asks to cancel |

Captions are keys of ours in 13 languages; AirPlay and DLNA are brand text. Wi-Fi Transfer's caption is the Network Services row's full text; its row on the Control Center page is the shorter `Transfer` (the full text is too long for the row label in six languages). Sleep Timer is too long
for the row label in ja, fr, pl and ru (it ends in an ellipsis and scrolls when focused) and for the
caption box in ru; both are accepted. The Screenshot row label is too long in ja, fr and es and is cut the same way. The Screenshot caption is set at 15 px (`mod_pulldown.CAPTION_OWN_PX`): the word is 74 px wide at 16 in the 71 px text width (en, de, it). In pl, AWTK keeps "Zrzut ekranu" on one 78 px line and the box clips it (accepted, like ru Sleep Timer). Our other captions fit the 71 x 36 box in every language.

- **Widgets are in the asset.** `mod_pulldown.py` adds to `view_switchs` an image (`pod_tile_*`,
  56 x 56, clickable) and a caption (`pod_cap_*`, a copy of `label_playset`) for each, **hidden and
  insensitive**. So the default file, the kill switch or a failed hook leave them invisible, and no
  widget is created at run time. The hook looks up all 28 widgets (any missing: nothing changes),
  moves a shown tile with its caption, binds a tap and makes it visible. Stock's tile visitor knows
  tiles by name and ignores ours.
- Art is the flat disc, off look only for the five plain actions; Sleep Timer switches between
  `drop_sleep` and `drop_sleepopen` (`ACCENT_DISC`) when the dialog opens (`pd_sleep_art`), and
  remains an action (tapping closes the dialog and opens the Sleep Timer page).
- **The page** has sixteen rows (`pod_row0..15`) with glyphs from `POD_ROWS`.
- **Tap** (`pd_on_tile`, `pd_open_dialog`, payload hook 22). Stock's tiles never open a page from
  their click handler. They check three words (`DROPDOWN_BUSY`, `POWER_USBSTATE`,
  `airplayGetFlag()`; any equal to 2 = do nothing), call `dialog_quit(dialog, 0xd)` and set a flag.
  `on_wm_tsmove_fun` opened the dialog modally and acts on the result. Ours do the same: the click
  checks the same three words, stores the tile in `pd_pending` and quits with `0xd`; the modal call
  is wrapped, and for the result `0xd` with a pending tile it runs `pd_run(id)` once the dialog is
  gone. `pd_run` is the one place to add an action. The pending id is cleared after every modal
  call, so a stock tile's `0xd` or a drag-close never runs it.
- Because the dialog is already gone when the action runs, **a page that will not open leaves
  nothing on screen**.
- **Adding a tile:** an id in `pod_pages.PULLDOWN_CHARS` and `PULLDOWN_TILES`, `PD_N` and
  `PD_IMG` / `PD_LAB` in `patch/pulldown.c`, an image and caption in `mod_pulldown.OWN`, a `drop_*`
  art image, a `POD_ROWS` glyph, a caption key in 13 languages and a case in `pd_run` (a switch has
  none). `m1plus_pulldown_init` hides tiles that are not shown, so a new pair only needs to be in
  the asset and the arrays.
- **Wi-Fi and Bluetooth long press** (`pd_bind_hold`, `pd_on_hold_*`, `pd_run` `PD_ACT_WIFI` /
  `PD_ACT_BT`): while shown, `img_wifiswitch` and `img_btswitch` bind pointer and click handlers
  with the same `RM_LONG_MS` (500 ms) hold and `SC_DRAG_PX` (10 px) drag-cancel limit as Home
  Screen pins ([pins](pins.md)). Holding quits the dialog with `0xd` while the finger is down,
  resets `pressdown_y` (`0xa05a30`, pinned) past `on_wm_tsmove_fun`'s `< 81` gate so a residual drag
  on row 1 cannot re-open the pull-down, and suppresses stock's toggle click on release (`RET_STOP`).
  Once the modal dialog returns, `pd_open_page` (rooted) opens or restacks our Wi-Fi / Bluetooth
  page (closing its `pd_window_open` sub-pages), falling back to stock's page on kill switch or open
  failure. Short taps stay stock's toggles.

## Power Off

Tile `b`, caption **Power Off** (a key of ours: stock has only "Shutdown" and "Confirm
Shutdown?"). The tap (`pd_poweroff`) does what the power key's long press does, minus the key-code
test: nothing happens while `standby_mode` is nonzero (a confirm is already up) or `POWERKEY_BLOCK`
is 2. Otherwise it wakes the screen, sets `standby_mode` 1, opens the stock confirm "Confirm
Shutdown?" through `pod_confirm_dialog` (so our scrim dims the page below), and on Yes opens
`poweroff_page`, which does the whole stock shutdown (resume record, stop the player, DAC off,
network stop, splash, `poweroff`). Any other answer, or a `poweroff_page` that will not open, sets
`standby_mode` back to 0.

**Our code never calls `system()` or `device_reboot`:** every stock shutdown goes through
`poweroff_page`, and a direct call would skip the resume save. Pinned in `PULLDOWN_FLAG_PINS`.

## AirPlay and DLNA

Tiles `c` and `d` are **switches** for the two service settings the Network Services page has
([settings](settings.md)). Captions are the brand texts `AirPlay` and `DLNA`.

- **Stock:** `airplay_switch` and `dlna_switch` only flip a setting byte and save it
  (`[SYSSET] AIRPLAY` / `DLNA`). Nothing starts or stops: the network-status timer starts or stops
  the services to match the byte, every tick, only while Wi-Fi is connected.
- **Tap** (`pd_on_tile` -> `pd_switch`): the same three guards, so **while an AirPlay session is
  playing both tiles refuse taps**, as stock's do. Otherwise it calls the switch function, sets the
  picture from the byte and invalidates the image. **Nothing is pending and the dialog is not
  quit**: a page-opening tile has to close it, a switch does not. Our code starts no service.
- If the byte is now on and Wi-Fi is not connected, the toast "Connect to Wi-Fi first" says why
  nothing starts. The byte is still flipped: it is a stored preference. Turning off never toasts.
- **Lit look:** when the dialog is built, a shown switch tile gets its picture from the byte. The on
  pictures are the disc style's on look and are in `ACCENT_DISC`, so with an accent the lit disc is
  the accent. The picture shows the setting, not whether the service is running yet.

## Swipe gates and the window stack

A stale word in stock's state can stop the pull-down opening until a reboot.

**Gates.** `on_wm_tsmove_fun` opens the pull-down only while `lockscreen_pageflag` is not 1 and
`dropdown_menu_state` is 0 (and the press began high on the screen with a move of at least 11 px
down). It stores state 1 before the open. `on_wm_tsdown_fun` stores `pressdown_y` only for state 0
or 3. The lock flag is set by the lock page's init and cleared by its close handler; the state is
set by the dialog's handlers and cleared only by its close handler. A window that goes away without
its close event leaves its word set for ever.

**A window can go without its close event** (from the disassembly): a close during an animation is
only stored in one pending slot, which a second close replaces; a forced close of the animation's
current window only ends the animation; `dialog_quit` does nothing unless the dialog's stage is
opened. While charging the device never enters standby, so the lock page is opened at wake with a
close animation.

**Rule: payload hook 30, `m1plus_tsdown`** (the prologue of `on_wm_tsdown_fun`, before stock's code
on every touch down) clears a word whose window is gone: `lockscreen_pageflag` when there is no
`screensaver_page`, `dropdown_menu_state` when there is no `dropdown_dialog` anywhere in the window
stack.

- A window under another page keeps its word: its init does not run again when the page above
  closes, so a word cleared while it was covered would stay 0 once it is in front again (a second
  pull-down over the first). Such a covered window still blocks the swipe above it, as in stock.
- The two words are only cleared, never set; nothing is closed, destroyed or opened.
- Reconciling at touch down makes stock's own tsdown store `pressdown_y` for this touch, so the first
  swipe after a stale word already works.
- **Cost:** both words 0 and no possible lost USB page (the normal case) is at most five loads and
  the stock call, with no window-manager call, file, syscall or allocation. A nonzero word, or state 2
  with the cable in and no page pending (also every touch while USB Storage or USB DAC is open),
  reads the kill switch once and walks the window stack. On the kill switch the hook is stock. Pins:
  `TSDOWN_PINS`.

**The USB gate (third word).** `on_wm_tsmove_fun` also refuses while `usblink_status`
(`POWER_USBSTATE`) is 2, a computer has the card. Stock's card-mount check and auto standby /
power-off countdown skip it too. Only `check_usb_status` writes 0, 1 and 2, and only `usbmode_exit`
writes 3. On the host's answer the poll stores 2 and sets the USB page's pending byte
(`USB_PAGE_PENDING`). The response timer clears the byte, then opens `usbmode_page` and ignores the
result. The page's close runs `usbmode_exit` (state 3). On an unplug the poll resets only states 1
(with `storage_config.sh stop`) and 3, so a page that never opened, or one that went without its
close event, leaves state 2 for good, even after the cable is out. The byte can also stay set:
Auto Update's modal scan dialog runs inside the response timer, which does not fire again until the
scan returns, so a reconnect during the scan leaves state 2 and the byte waiting (then the page
opens late, cable or not).

**Rule: payload hook 38, `pd_usb_poll`** (the idle pass's `check_usb_status` call becomes a call to
it, then stock's poll). With state 2, no cable and no `usbmode_page` anywhere in the stack (also
under the lock page) it clears the byte and stores 1, and the same call runs stock's own unplug
branch for 1: `storage_config.sh stop`, `toolsSetpclinkStatus(0)` (the kernel keeps `pc_check` at 1
after an enumeration until firmware writes 0) and state 0. The swipe, the card-mount check and auto
standby come back without a touch, over the scan dialog too: stock's own scan, after a USB page's
close or from Settings, already runs with state 0 or 3 and the swipe open. A replug during the same
scan then runs through stock's 0 → 1 → 2: a PC asks for the page again (opened once the scan
returns), a charger leaves state 1. With `usbmode_page` in the stack (a normal unplug) the state is
left for its own close, `usbmode_exit`.

**Rule: payload hook 39, `pd_usb_take`** (the response timer's read of the byte, through the asm
stub `pod_usb_site`). A request whose cable is gone (`POWER_EXT` 0) is cleared and read as none, so
the timer neither closes a lock page or pull-down for it nor opens USB Storage. With state 2 it then
calls `pd_usb_poll` at once, so a cable back before the next idle pass meets stock's 0 → 1 → 2, not a
stale 2. Otherwise the branch is stock's.

- **Cost:** one load and stock's call per idle pass and per timer pass; while state 2 has no cable
  (also the second or so a normal unplug takes to close `usbmode_page`), the kill switch (read once)
  and a window stack walk per idle pass. Pins: `USBPOLL_PINS`, `USBTAKE_PINS`.

With the cable in, the touch hook asks again for a lost page: state 2, no page pending and no
`usbmode_page` in the stack set the byte, so the response timer's next tick opens the page as stock
meant to. The swipe stays refused until the page is used and closed. State 3 is not stored instead:
stock's unplug skips `storage_config.sh stop` on 3. A pending page or the page in the stack leaves the
state to stock.

**The slide timer after the close (second cause, same symptom).** The dialog's close handler stores
state 0 and removes only the 500 ms refresh timer. The 10 ms slide timer is not removed, and the
dialog's destruction is only scheduled. A tick after the close stores state 3 on its last opening
frame with no check that the dialog is closing, so state 3 is left with no dialog and every swipe is
refused. **Repair:** `m1plus_pulldown_init` binds one more handler, `pd_on_close`, to the dialog's
close event (no new hook). It cancels the slide timer as stock's pointer-down handler does (read
the `timer_idex` property; unless it is `0xffffffff`, remove that timer and reset the property). It
stores no global and returns OK. A refused bind leaves stock's behaviour. The two repairs are
independent: the touch hook repairs a stale state, this one stops one being made.

**Limits.** A dialog on top of the stack but off-screen, a lock page on top but not shown, and a
lock page or dialog left under another page (its word stays set and blocks the swipe there) are left
to stock. With the cable in, a response timer held by the scan dialog still delays the USB page, and
the swipe waits for it or the unplug. While the byte at `0xa05aa6` is set (car mode) stock's poll returns at once, so a
state 2 reset to 1 there waits for car mode to end before stock's unplug runs. A USB page that opened and then went without its close event
leaves the card as `usbmode_exit` would have found it.
