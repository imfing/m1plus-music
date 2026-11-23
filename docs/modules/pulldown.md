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
- **Tile art:** every tile image is one flat 56 x 56 disc, 26 px glyph, no ring. Off is a `#3A3A3C`
  disc with a white glyph, on a white disc with a `#141414` glyph, disabled a `#2C2C2E` disc with a
  `#636366` glyph (lighter than the `#1C1C1E` cards for the panel). Gain has custom 2- and 5-bar glyphs, Output the text "PO" / "LO" in Inter Medium
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

## Two pages

The pull-down has two pages; a left / right swipe slides between them with the finger, as on
Now Playing. It opens on the page the last slide landed on (`pd_last`, memory only: page 1
after power-on), set before the first paint.

- **Page 1** is the dialog as above: `view_switchs` (the tiles and their captions) and
  `view_backlight` (the brightness card). **Page 2** is `pod_cc2`, a view at (10, 44), 300 x 274
  (x 10 .. 309, y 44 .. 317), hidden and insensitive in the asset, holding the Now Playing card
  `pod_cc2_top` and the lower cards `pod_cc2_left`, `_right1`, `_right2` (flat `#1C1C1E`, radius 26 / 22;
  below). The status bar copy and the grabber are on both pages.
- **Dots:** `pod_cc2_dot0` / `pod_cc2_dot1`, 4 px images, Now Playing's page dots (`drop_dot_on` white at alpha
  `0xEB`, `drop_dot_off` at `0x46`, baked: a tiny round fill renders square on the device) at (153 / 163, 320), centres 155
  and 165, hidden in the asset. The hook shows them and lights the current page's.
- **Now Playing card** (`cc2_*` in `patch/pulldown.c`): `pod_cc2_top` is a button over the dialog's
  (10, 44)-(309, 163), `#1C1C1E`, radius 26. In it: the 96 px cover at (22, 56), painted in the
  card's `EVT_AFTER_PAINT` from a `mb_art_t` (size 96, corner radius 8; the Home bar's `mb_art_*`,
  made once per track on `mb_track_key`, freed with the dialog); `pod_cc2_title` (18 px white) and
  `pod_cc2_artist` (15 px `#8A8A8E`), 134 px wide from x 130, ellipsis; the favourite disc
  `pod_cc2_fav` (32 px, centre (282, 70)); the transport `pod_cc2_prev` / `_play` / `_next`
  (centres x 170 / 214 / 258, y 113; 24 px glyphs on 44 px images, `drop_cc_*`); the progress bar
  (130, 134)-(297, 138), track `#48484A`, fill `#F2F2F2` by elapsed / length, drawn by rows so its
  ends are round; `pod_cc2_elapsed` and `pod_cc2_remain` (12 px `#8A8A8E`, "1:47" and "-1:26") at
  y centre 151.
  - One 500 ms timer (`cc2_tick` -> `cc2_work`) runs only while page 2 shows: a swipe's start or
    `pd_page_set(1)` runs `cc2_work` once and arms it; landing on page 1, the dialog's `EVT_DESTROY` and `pd_open_dialog` stop it.
    `cc2_work` is the only code that reads the player and changes the card.
  - **Local track** (`cc_playing`): title (else the file name), artist, cover, play / pause by
    `mclGetPlayStatus`, the bar and times from `get_playtimeandlength` (none when it has no length).
    The star is filled white (`drop_cc_fav_on`) for a favourite (`checkFavExist`, asked on a track
    change and after a tap) and an outline otherwise; a tap does what Now Playing's star does for a
    local track (`checkFavExist`, then `deleteMusicFromFav` or `addMyFav`). A server track
    (`sba_rec_track`) has no star here (hidden, so also insensitive): stock's would write its stream
    record, whose address carries the login token, into the local favourites.
  - Buttons: play / pause `playpause_quick_click`; next / prev `next_quick_click` /
    `prev_quick_click` with the click's own event (a synthesized one stamped `time_now_ms` when
    there is none); a tap elsewhere on the card quits the dialog with 0xd like a tile, and
    `pd_run` opens Now Playing (`m1_open_now_playing`: Radio's page while a station plays).
  - **Nothing queued:** "Not Playing", no artist, a grey (`#3A3A3C`) cover, the three transport
    buttons and the star greyed (`drop_cc_*_off`) and insensitive, an empty bar, no times.
  - **Radio** (`mb_radio_active`): the station and its two lines as Radio Now Playing shows them
    (`rd_meta_head`, `mb_radio_line`), the station's logo as the Home bar gets it (`mb_radio_art`
    at 96 px, else Radio Now Playing's grey card with the broadcast glyph; re-made when the logo
    file appears), no star, no previous / next (hidden): the one button at x 214 is the stop square
    (`drop_cc_stop`) while connecting or playing and the play triangle otherwise
    (`mb_radio_play_click`). In the bar's place stands Radio Now Playing's LIVE divider: the two
    fading capsules (`drop_cc_live_l` / `_r`, 54 px, `mod_nowplaying.live_bar_image`) and a 13 px
    white LIVE (`pod_cc2_live`), shown only while connecting or playing. A tap on the card opens
    Radio Now Playing (`rn_open`, also for a stopped station).
  - **Episode or book part** (`cc2.kind` 1 / 2, from the track's path: `pc_is_path` / `bk_is_path`, read at
    every tick, so a change of kind restyles the page within 500 ms): title and sub line as the queue
    record has them (an episode: its title, then the show; a part: the book, then the part's name); no
    star (hidden); the transport is Now Playing's spoken-audio row at the same centres: back 15 s, play /
    pause, forward 30 s (`drop_cc_back15` / `drop_cc_fwd30`: Now Playing's glyphs at 30 px on the 44 px
    image, so the digits read). The skip buttons seek with `np_spoken_seek` (`patch/nowplaying.c`, the
    function Now Playing's own buttons use) and stay on the pull-down.
- **Lower cards** (`cc2_lower`, on the same timer): the left card (10, 173)-(153, 317) holds four 54 px
  discs centred at (46, 209) (117, 209) (46, 281) (117, 281), the two right cards (162, 173) and
  (162, 250), 148 x 68, a 44 px disc 12 px in from the card, a 17 px white title at x + 66 and a 14 px
  `#8A8A8E` sub line under it (`hscroll_label`s 74 px wide, centres 10 above and 12 below the card's
  middle). The discs are baked images (`drop_cc_*`, `tools/mod_icons.py DROP_CC_DISCS`; a small round
  fill renders square on the device) in page 1's tile look: off `#3A3A3C` with a white glyph, lit
  white with a `#141414` glyph, disabled `#2C2C2E` with `#636366`. Their images and the sub lines
  change only when the state does; the Equalizer's name is read (`peq_playing_name`) at most every
  2 s. Lit discs (`drop_cc_pm_one`, `_pm_shuffle`, `_pm_all`, `_eq_on`, `_sleep_on`, `_speed_on`, `_station_on`) are in
  `palette.ACCENT_DISC` like page 1's ON tiles: an accent recolours them ([accent](accent.md)); the
  favourite star stays white. `cc_disc` places every glyph by its ink box.
  - **Play Mode** (`pod_cc2_playmode`): shows `pod_play_mode()` (List play `repeat-off` unlit, Repeat
    one, Shuffle, Repeat all lit). A tap sets the next of Now Playing's four modes (0, 1, 2, 3) with
    `pod_set_mode`, which keeps the Shuffle flag ([shuffle](shuffle.md)); the pull-down stays.
  - **Up Next, Go to Artist, Go to Album** (`pod_cc2_upnext`, `_artistgo`, `_albumgo`): quit the dialog
    with 0xd; `pd_run` then calls `queue_open` (our Queue page; the stock drawer when its window will
    not open, as Now Playing's queue button) or `pm_goto` (`patch/playmore.c`: the More sheet's Look
    up artist / album with no sheet to close; a Subsonic track goes to the source's page; a miss
    toasts "Not found"). From the pull-down `pm_goto` holds `songerinfoflag` only when a
    `playing_page` is in the stack.
  - These four discs are live for a queued local or server track; with nothing queued they are greyed
    and insensitive. For a station they take the radio layout below.
  - **Equalizer** (`pod_cc2_right1`): lit while the Equalizer switch (`EQ_FLAG`) is on, the sub line
    the preset or curve name, else "Off". **Sleep** (`pod_cc2_right2`): lit while a sleep timer runs,
    the sub line the minutes left ("25m left", `pc_left_text`), else "Off". Both cards are buttons and
    always live; a tap quits the dialog and `pd_run` runs page 1's Equalizer / Sleep Timer tile
    action (`PD_EQ`, `PD_SLEEP`: same window-stack handling).
  - **Lower half for an episode or a part** (`cc2_spoken_lower`; the widgets are the same, the images, the
    taps and the Equalizer card's texts change): the Equalizer card is **Speed** (`circle-gauge`, title
    "Speed", sub line 1x / 1.25x / 1.5x / 2x from `playspeed_mode`; lit when it is not 1x); a tap calls
    `np_speed_step` (Now Playing's speed button: the next speed saved for the show or the book, applied,
    the player restarted at its place) and stays. Sleep is the music's. There is no Equalizer card. The
    four discs, all live:

    | | Podcast episode | Audiobook part |
    |---|---|---|
    | top left | Podcasts (`podcast`) -> `podcasts_goto(0, 0)`: the Shows level | Audiobooks (`book-headphones`) -> `books_goto(0)`: the Library |
    | top right | the queue (`drop_cc_queue`, Lucide `list`, Now Playing's queue glyph for an episode, `np_playlist`) -> `queue_open`, as music's Up Next | the same |
    | bottom left | Show Notes (`info`) -> `podcasts_goto(path, 1)`: the episode's own page | Book Info (`info`) -> `books_goto(path)`: the book's page (it has no page of its own for info) |
    | bottom right | Next Episode (`skip-forward`): `next_quick_click` as the next key does; stays | Next Part: the same |

    The page-opening discs quit the dialog like the music ones; `pd_run` then opens the page from the
    track playing at that moment (`PD_ACT_PODS`, `_BOOKS`, `_NOTES`; "Not found" for a track of
    neither kind). `podcasts_goto` / `books_goto` use a page already in the stack as `podcasts_go` does
    (every window above it is closed, `m1_uncover`; the page is put back to its root, then opened to the show, the episode or the book), else open the page; a
    show or book no longer on the card leaves the root.
  - **Radio layout** (`cc2_radio_*`, `cc2.mode` 2): the same slots, restyled at the next tick when
    the player kind changes (`cc2.mode` 2 is a station, `cc2.mode` 1 with `cc2.kind` 1 / 2 an episode or a part). Discs: My Stations (top left, `radio`), Recently Played (`history`),
    Station Info (`info`), Search (`search`), images `drop_cc_rd_*`. Each quits the dialog and
    `pd_run` calls `radio_open_at` (`patch/radiopage.c`: the Radio page opened on My Stations, on
    Recently Played, or on Radio Browser with its search field up; Back returns to the Radio root)
    or `sinfo_open` (Station Info). The Equalizer card becomes the **Station** card (`list-plus`):
    "Saved" with a lit disc when the station is in My Stations (`rd_fav_has`, read when the station
    or `rd_serial` changes), else "Not Saved" unlit; a tap runs Radio Now Playing's Add to /
    Remove from My Stations (`rd_fav_toggle`, the same toasts) and the pull-down stays. There is
    no Equalizer card for a station. Sleep is as for music. A Radio page already in the stack (a
    station started from it stays under Radio Now Playing) is uncovered and put back to its root
    (`rp_to_root`) first.
  - The two cards' discs are insensitive pictures: a tap on one reaches the card.
- **Slide:** page 1's containers (`view_switchs`, `view_backlight`) and page 2's (`pod_cc2`) move
  together by one offset (`pd_slide_place`): page 1 at its asset x plus the offset, page 2 320 px to
  its right, both at their asset y. A page entirely off the dialog is hidden (`m1_show`: also
  insensitive). Only the containers move, so what the tile hook set inside `view_switchs` (tiles
  shown, places, Control Labels) returns exactly as it was. The status bar copy, the grabber and the
  dots stay.
  - During a swipe the pages follow the finger; past either end they move a third as far.
  - On release (`pd_slide_release`) a flick faster than 300 px/s picks the page in its direction,
    otherwise the page more than half in view wins. A finger that stood 100 ms before the release
    has no speed; an abort is a release with no speed. The dots change at once.
  - The pages then slide there with an ease-out cubic, 300 ms for a whole page and its share for
    less, at least 120 ms, one frame every `NP_FRAME_MS` (16 ms, `pd_slide_frame`). On landing
    `pd_page_set` puts them in place, hides the other page and starts or stops page 2's timer. A
    refused frame timer lands at once; the dialog's end (`cc2_stop`) stops the slide.
  - A press above y 280 on sliding pages catches them where they are: it is swallowed (no tile under
    it sees it), its moves drag at once, and its release picks the page again.
  - Page 2's timer starts as soon as a swipe begins, so its card is current while it slides in.
- **Swipe rule:** `pd_on_swipe` is bound on the dialog's *before children* pointer events
  (`EVT_POINTER_DOWN_BEFORE` 0x100, `_MOVE_BEFORE` 0x102, `_UP_BEFORE` 0x104, which
  `widget_on_pointer_down / _move / _up` dispatch ahead of the children and the dialog's own
  listeners; `RET_STOP` ends the dispatch) and `EVT_POINTER_ABORT`. A press above y 280 is watched.
  Once its travel exceeds 20 px horizontally and more than vertically it is a page swipe: that
  move, the later moves and the release return `RET_STOP`, so the tile or slider under the finger
  gets no move and no release (no click, no hold) and stock's handlers see nothing. A press that goes vertical first is
  left to stock whole. The Wi-Fi / Bluetooth long-press timer is stopped when the swipe is
  recognised.
- **Stock's drag:** the dialog's handlers (`0x47514c` down, `0x4755e8` move, `0x4752f0` up) act only
  for a press at y >= 280 (`0x118`, `pressdown_y`) moving up: the down only cancels the 10 ms slide
  timer (`0x47535c`), the move drags the dialog (states 1, 2), the up starts the slide timer only in
  states 1 and 2. A press above 280 never puts stock there, so swallowing its moves and release
  leaves nothing to settle. A press at y >= 280 (the lower brightness card, the dots, the grabber)
  is stock's drag-to-close zone and is not a page swipe. The tiles' long press, `RET_STOP` clicks and
  the swipe gates below are unchanged.
- **Fallback:** the kill switch (`/mnt/mmc/m1plus-off`), a missing widget (the dots, the card's
  widgets) or a refused bind (the card's, the swipe's): no swipe is bound, the dots stay hidden and page 2 is never shown, the dialog is exactly the stock one. The
  down is bound last, so a half-bound swipe cannot start. A swipe that ends in an abort (the dialog
  goes to the background) is read like a release.
- **Known limitation:** a swipe's pressed tile never gets its release, so it keeps its pressed
  state until the next press; the tiles have no pressed look.

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
