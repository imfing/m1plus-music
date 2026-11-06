# Virtual iPod

The optional Pod item opens a fullscreen iPod Classic-style page: a 240 px display above a
240 px touch-wheel area. It is hidden from the main menu by default. Code keeps the `ipod`
and `IP_*` names; the device label is Pod. Hardware validation is tracked in the checklist.

Sources: `patch/ipod.c`, `tools/pod_ui.py` (`build_ipod_page`, `ui/m1plus_ipod.bin`),
`tools/mod_icons.py` (`ipod_wheel`) and `IP_*` in `offsets.inc`. Tests: `test/pod/ipod.py`;
preview: `tools/preview_ipod.py` (light/dark menus, library rows, Now Playing, a transition
contact sheet and GIF, the cross-fading cover pane and the reference palette).

The Pod row's glyph (`pod_ic_ipod`) is `assets/icons/custom/ipod.svg`: Lucide's `smartphone` body
with a screen bar and a click wheel, the pick from `tools/preview_pod_icon.py` (candidate B).

The page adds no stock hook or boot work. It owns its `EVT_AFTER_PAINT`, pointer grab,
foreground/background/destroy events and one page timer, using stock calls already shared
with Albums, Songs, the mini player and Cover Flow.

## Layout (320 x 480, `IP_*`)

- **The window** is `fullscreen = true`, as the lock screen's `screensaver_page`: 480 px, the stock status bar is not drawn (the bar window is still
  alive; the page reads its battery, below). Colour `#C6C9CE`, the wheel body. No close animation.
- **The screen** `ipod_screen` (320 x 240, insensitive: it takes no touch; the payload paints it). A 24 px title bar (the reference's four-stop gradient, a 1 px divider `#6A6A6A`), seven 30 px text rows (24 + 7 x 30 = 234: a row is never cut at the bottom) or four 54 px cover rows (24 + 4 x 54 = 240). Painted by `ip_on_paint` with `canvas_fill_rect`, `canvas_draw_text_in_rect` (the
  text styles are ten hidden labels in the asset, `label_ip_*`: rows 18 px, white on the selection, a left-aligned 16 px title, 16 px grey and selected white small
  text, 18 / 16 px Now Playing lines, a 15 px right-aligned time, 16 px blue values, a 14 px queue line) and `canvas_draw_image` for the cover. Every text is cut with an ellipsis (the Albums grid's
  search) to its box, measured by the canvas' own font. Text padding is 8 px (`IP_TEXT_X`).
- **Title bar**, after the reference's status bar: the title **on the left** (16 px, x 8: `Pod` on the main menu (the item's own name, a brand, plain in every language), the list's name, `Cover Flow`, `Now Playing`), **no clock**, and on the right the
  12 x 14 play-state glyph (a triangle while playing, two bars paused, nothing otherwise: `mclGetPlayStatus`; in the selection's blue, a row at a time down its gradient) 8 px before the battery, the battery 8 px from the edge. The gradient stops are `#FDFDFD` 0, `#E7E7E7` 0.42, `#D8D8D8` 0.47 (the hard glassy break), `#ABABAB` 1. The text box starts at y 1, because AWTK's metric centring put the caps 1 px high on the device (screenshot shot-0014).
- **Battery:** read from the real status bar, no new stock function: `*system_bar` (`0xa06f90`, the window the app keeps) holds `pgbar_battery` (its `value`,
  0 / 20 / 40 / 60 / 80 / 100) and `img_battery` (`bar_charge` while charging). Drawn with fills as the reference's: a 24 x 12 frame with a 3 x 5 nub (outline `#636364`), the empty well a three-stop grey (`#53585B`, `#717479`, `#A0A4A6`), the charge a ten-row two-band green fill (red at 20 % or less, the reference's below 20 %: the stock value moves in steps of 20), full green while charging. No bar (the pointer is NULL): no fill.
- **Selection:** the reference's five blue stops `#3EABE3` .. `#1584D3` over the whole row (a 1 px highlight `#9ADDF8` on top, a 1 px rule `#154F81` below), white text, a white chevron; only the selected row has a chevron
  (other rows: black text, no chevron). A track row has none. An unselected track matching the playing path and cue start has the speaker at the right: the Lucide `volume-2` (the image `ipod_playing`, a heavy white glyph at 28 px, 14 px after the box filter), in the title bar play glyph's blue gradient, decoded once into a page-owned bitmap like the play mode marks (`ip_mode_bitmap`, coverage mixed onto white) and copied in paint. Settings values are 14 px regular, blue (`#0C62D2`) on a white row and white on the selection.
- **Materials:** the selection, the header, the battery, the progress fill (six glossy blue stops) and the wheel follow the reference's colour sets. Design reference: [iPlayr](https://github.com/keremersu35/ipod-player) (MIT, Copyright (c) 2026 Kerem Ersu, since added; we take values, metrics, timings and behaviour only; the code is ours), inspected at `76f9a730` and again for the title bar, battery, selection, Now Playing, navigation and artwork pane.
- **Library rows:** Albums, an artist's albums and Playlists use 54 px rows, four visible (`IP_TALL_H`). The 54 px cover **fills its row exactly**, flush top and left, so stacked covers leave no seam (it covers the left of the selection's gradient, which runs on under the text); text at x 62 (18 px, the subtitle 16 px grey). Albums show the artist below the title. **Song lists are plain text rows** (the song's title, 30 px, seven visible, the speaker on the playing one): Music > Songs and every list of tracks (an album's, an artist's All Songs, a playlist's) show no cover, and the row worker and the page timer do no cover work for them (`ip_tall`). All Pod text is the device font (Inter Medium, `default.ttf`, no Pod-only font): the hierarchy is size and colour, primary black (white on the selection), secondary grey. The text rows are `IP_ROWS` x `IP_ROW_H`. A list opened from a record is titled with it in the title bar: the album, the artist (an artist's albums), the playlist (`ip_push_titled`). The cursor and its scroll window use each level's row count; MENU restores both. Artwork loading is described below.
- **Main, Music and Settings menus:** the list and title bar in x 0 .. 160 (`IP_SPLIT_X`), and the right pane flush against it with no rule between (160 .. 320 x 0 .. 240, 160 x 240 px: `IP_PANE_X/W/H`), on which the menu casts a soft shadow (below) with the
  **cover pane** ("The cover pane", below).
- **Main menu:** Music, Cover Flow, **Podcasts**, Shuffle Songs, **Now Playing** (only while something plays or is paused, `mclGetPlayStatus` 2 or 3, as the reference), Settings. When the row appears or goes the cursor stays on the same item (`ip_look`, `ip_root_id`).
- **Now Playing screen:** the screen's white field with the playing cover at (10, 30), 150 px, flat and square, drawn as a straight 1:1 copy of the decoded square, and a 20 row reflection under it (`IP_NP_REFLECT`, y 180 .. 200: a mirror of the cover's last rows, 30 % opaque at the edge, fading into the background) made once per cover or appearance change into a 150 x 20 bitmap (`ip_reflect`); paint only copies both without allocating. If the reflection bitmap cannot be allocated, the cover is drawn alone. The text column (x 176): the title 18 px black, artist and album 16 px grey, and `n / N` (14 px grey) is the place in the queue (the translation table allows one
  `%d` a text, so no "n of N"). The active stock play mode is marked top right (right edge x 312, y 28) by a 16 px anti-aliased icon: shuffle, repeat or repeat one, the Lucide glyphs drawn heavy (4 px stroke at 32 px) into the built images `ipod_mode_shuffle` / `ipod_mode_repeat` / `ipod_mode_repeat1`, reduced with the box filter by `cc_decode` on first use into a page-owned bitmap whose pixels are the coverage mixed from the screen colour to black (`ip_mode_bitmap`; the screen is white in both appearances); none in list play. The progress bar is the reference's: a 14 px track (x 58 .. 262, white with its top and bottom edges shaded in, a 1 px outline), the fill the six glossy blue stops `#86ABFF` 0, `#6B99F5` 0.20, `#3D89EB` 0.58, `#3698F9` 0.58, `#37B0FF` 0.82, `#5CBBFF` 1, and a 6 px reflection under it (30 % fading out); the times are 15 px, zero padded `mm:ss` on the left and `-mm:ss` on the right in 50 px side columns
  (`get_playtimeandlength`, seconds). Nothing queued: `Not Playing`. It does not blink while the player changes track: for a moment the player has no time (`get_playtimeandlength` fails or says 0) or no track (`cc_playing` NULL), so the bar is always drawn from the last valid position and length (a new track starts empty at `00:00` with the last length, the song record has no duration), the last track's text and cover stay for `IP_NP_GONE` = 3 looks without one, and only then does it say `Not Playing` (and the cover become the placeholder).
- **The wheel** `ipod_wheel` (view 220 x 220 at (50, 250), the touch target) with the picture `ipod_wheel` as an insensitive image child (decorative overlays
  never take a touch): a light ring, a 90 px centre button, `MENU`, `|<<`, `>>|`, `>||` drawn in; the corners are transparent. The view is square, so the payload does the
  circle's hit test (touch outside radius 110: ignored, no grab). The window is 480 tall; wheel + margins fit the lower 240.

## The wheel

Touch events come from the wheel view's `EVT_POINTER_DOWN / MOVE / UP / ABORT` (`widget_on`, as Cover Flow's input layer); the view is grabbed
(`widget_grab(window, wheel)`) for the touch so moves and the release arrive wherever the finger goes. Positions are `widget_to_local` (demo's own) minus the
centre (110, 110).

- **Regions:** radius < 45 (`IP_HUB_R`): the centre button; 45 .. 110: the ring; beyond: nothing.
- **Angle:** `ip_angle(dx, dy)` = degrees clockwise from 12 o'clock in sixteenths, pure integer code: `atan(x) = x / (1 + 0.28125 x^2)` on the octant (error under
  0.2 degree on large coordinates; the test compares it with `math.atan2` at 1,800 points and the pixel rounding of a small radius allows 1.5 degrees). `ip_turn(a, b)` is the
  shorter way round, so crossing 12 o'clock is smooth.
- **Step: one row per 15 degrees** (`IP_STEP` = 240 sixteenths, 24 steps a turn). The unspent
  turn accumulates (`ip.acc`, signed, sixteenths of a degree); a step fires every time it passes +-`IP_STEP`, the **leftover carries** into the next step, and a new touch, a push or a pop
  of a level (`ip_wheel_reset`) clears it. The cursor moves, **no wrap** (the iPod stops at the ends; clamped: the hard stop below), and the window of 8 rows
  follows it (`top` is the first row shown; the cursor never leaves it).
- **Chord dead zone** (`ip_chord_near`, `IP_DEAD_R` = 11 px, 10 % of the 110 px ring): a move is rejected (no accumulation, the reference angle is taken again from the new
  point, the speed reset) when the straight line from the previous touch point to this one passes closer than 11 px to the centre, or ends there. Integer: `|a x b|^2 < R^2 |b - a|^2`
  for a closest point inside the segment, else the nearer end's `x^2 + y^2 < R^2`; coordinates are clamped to +-150 so the square fits 32 bits. A drag that **began** on the centre
  button (`R_CENTRE`) still turns nothing. (This replaces the old 18 px point test.)
- **Reversal hysteresis** (`IP_REVERSE` = 128 sixteenths = 8 degrees): the drag keeps a committed direction (`ip.dir`). Travel the other way is swallowed (`ip.rev`) until it reaches 8
  degrees; only then the direction flips, the accumulator restarts at 0 and the speed is reset, so the first reverse step comes after 8 + 15 degrees. Travel back in the committed
  direction first takes the swallowed travel back, so a small jitter at the turnaround nets zero and moves nothing.
- **Acceleration, long lists only** (`ip_turn_move`, `ip_tier_rows`): a list of more than `IP_LONG` = 16 rows (Songs, Albums, Artists, long playlists) climbs tiers; 16 rows or fewer
  (the main menu, a short album) always move one row a step. The angular speed (sixteenths of a degree a second, from the event times) is clamped at `IP_VMAX` = 6400 (400 degrees a second) and smoothed `v += (instant - v) * 3 / 20`
  (0.15; `IP_SMOOTH_NUM` / `IP_SMOOTH_DEN`). A gap over `IP_PAUSE_MS` = 250 ms between two moves, or a reversal, sets it to 0. While `v` is above `IP_FAST` = 2880 (180 degrees a second) the tier index is the time
  held above it divided by `IP_TIER_MS` = 500 ms; rows a step by tier: **1, 2, 3, 5, 8, 13, 21, 34** (the last holds). Below `IP_FAST` the tier is 0 at once. These numbers (tiers, the 400 degrees a second clamp, the 0.15 smoothing, 180 degrees a second, 500 ms, 250 ms) follow the Apple Music 404-page iPod's; numbers only, the code is ours. At 375 degrees a second the first 2-row step comes about 0.6 s into the turn (the smoothed speed passes 180 on the 5th move).
- **Hard stop at the ends:** a step that wanted to go past the first or last row clamps there and nothing else happens: no wrap, no bump, no animation, the timer untouched,
  as the iPod (and the Apple Music 404 page iPod).
- **Tap:** a touch that turned no step and travelled less than 12 px (`IP_TAP_PX`) is a tap. On the centre button: **select**. On the ring, by where it began:
  the top sector (|dy| > |dx|, up) **MENU** (back; on the main menu it closes the page: `navigator_back`), the bottom sector **play / pause**
  (`playpause_quick_click`), the left sector **previous** (`prev_quick_click(e, 0)`), the right sector **next** (`next_quick_click(e, 0)`); the two skip calls read the
  event's time (stock ignores a click within a second of the last). A drag that began on the centre button turns nothing and is no tap. An abort (a window above, the
  scroll hook's abort) ends the touch and acts on nothing.
- **Long press of MENU** (`IP_LONG_MS` = 500 ms, a touch that began on the top sector and neither turned nor travelled): pops every level to the main menu with the slide of the last one (`ip_pop_root`). The page timer watches the clock at 100 ms while such a touch is held (`ip_want_ms`), and the release checks it too; on the main menu a held MENU does nothing (it does not close the page).
- **On Now Playing rotation does nothing** and select is play / pause: the iPod's centre-press cycle (scrubber with seek tiers of 1, 2, 3, 5 s a step, shuffle, rating; wheel volume on the default
  screen) was **not built**, because the stock setters cannot be called safely from here with the evidence at hand (“Playback limits” below).

## The cover pane (the reference's artwork pane)

The split pages (main, Music, Settings) show album art in the right pane (x 160 .. 320, 160 x 240: `IP_PANE_X/W/H`), flush against the white menu (no divider line), edge to edge. **The menu casts a shadow on the pane** as on a real iPod Classic and in iPlayr (`.shadow(black 0.7, radius 8, x 4)` on the menu background): `IP_SHADOW_W` = 10 columns of black over the pane's left edge, 52 % opaque at x 160 (alpha 132) and falling like a gaussian (sigma 3.6: 132, 122, 105, 83, 61, 41, 26, 15, 8, 4) to nothing beyond x 170, the full pane height, over the cover and over the plain fill alike. It is one straight-alpha RGBA bitmap made once at open (`ip_shadow_make`, no allocation in paint), drawn by `ip_paint_pane` after the pane with `canvas_draw_image`; demo's canvas alpha-blends RGBA images over the screen (`test/awtk_fill.py`, `canvas_draw_image_ex` of a translucent image). It belongs to the menu half: while two split menus swap it stays with the pane, in the split open and close it travels with the menu half (`ip_render_edge`: the renderer replays it with the left half, `ip_paint_split` widens that half's clip by its width and the pass that draws the pane's right half skips it), and fullscreen pages have none. The pane uses **whole-pixel copies of one pre-scaled cover**, nothing resampled while it moves (`test/awtk_fill.py` proves with demo's own code that a same-size window is copied pixel for pixel at any offset). The timing is the reference's. All on the page's **one timer** (`ip_tick`); no hook, no event, no new timer; paint only copies.

- **Slots:** two 264 x 264 RGBA bitmaps (`IP_PANE_ART`: the pane's height zoomed 110%, one scale made once per cover with `cc_decode` from the 168 px cache file, `cc_box` averaging) and one pane-sized `mix` bitmap for fade frames; made on first use, freed at destroy (about 710 KB).
- **Pan** (`ip_pane_pos`, in 1/256 px): a cover pans linearly across the margin (`IP_PANE_R` = 24 px, about +-8 % of the pane: the reference's slow drift, kept) in `IP_PANE_PAN_MS` = 7.5 s from its own start, every other cover the other way; vertically centred. That is 3.2 px a second, so each 40 ms frame is a step of about 0.13 px: **the position is fixed point (1/256 px) and the frame is built at the fraction**. The phase counts only time shown (`time_now_ms`, a step at most `IP_DRIFT_MAX_MS` = 250 ms, so a stall never jumps). The placeholder stands still (one frame, no more work).
- **Sharp sources** (the 168 px cache files stretched to the pane's 264 px read soft): every cover is decoded straight to `IP_PANE_ART` with the box filter, each on a tick of its own and never during a fade, from the sharpest source there is. No second cache tier is written to the card.
  - *The playing album:* demo's own file for the playing track (`np_cover_file`: `/tmp/coverpic.jpg` embedded art or `/tmp/externpic.jpg` folder art, fitted inside 264 px, JPEG q90; the same file Now Playing reads), used when demo is done with it (`COVER_SRC` not busy) and it is not a stale file of the last track: the pane saw demo make a cover since the track changed (`busy_seen`, watched every pane tick) or `IP_PANE_SHARP_MS` = 4 s have passed (a page opened on a playing track trusts the file at once). Until then the 168 px file shows; when the file is ready (looked for twice a second) it is decoded once into the other slot and **fades in over the same album at the same pan phase**.
  - *The rotation:* at `IP_PANE_NEXT_MS` the next album's art is asked of the shared builder's worker (`cc_build_add_file`: a one-job set, the same stock art calls under `parse_cover_mutex`, extracted at 264 px into ONE reused RAM file `/tmp/m1plus-pane.jpg` through `.tmp` and a rename, never under `/mnt/mmc`, no cache file, no marker). The tick that sees the worker done joins it, decodes the file into the other slot and deletes it. Only while the page is in front on a split level with the screen on and the job set free (`cc_build_busy`: not while another page, or the row worker, holds it) and the card mounted; otherwise, or when the extraction fails or yields a picture whose longer side is under 264 (a small source; the stock call fits inside the request and never upscales, so 264 is the most it returns), the 168 px file is used as before. A level without the pane, the screen going off, the background and destroy stop (`cc_build_stop`: cancel, never waits) the worker and remove the file. The fade waits for the picture if it is late.
- **Rotation** (`ip_pane_step`): a rotation of up to `IP_PANE_KEYS` = 8 random albums that have a cached cover (`ip_pane_pick`: `loadLocalClassList(0xf003)` once a visit of the main menu, `IP_PANE_TRIES` = 48 draws, `pod_rand`; only covers already in the Cover Flow cache are used). The first cover appears at once. `IP_PANE_NEXT_MS` = 3 s after a fade began the next cover is **decoded into the other slot on a tick of its own, never during a fade**; `IP_PANE_HOLD_MS` = 6 s after it began the **cross-fade** starts: `IP_PANE_FADE_MS` = 1.5 s, smoothstep, the next cover pans from its start while both pan. The playing album's cached cover (`cc_playing`, `cc_album_key`, one cache file test when the playing album changes) replaces the rotation: it is decoded at once, fades in and stays, panning back and forth. A cache file that does not decode leaves the placeholder and is not tried again. No cached covers: the placeholder, still.
- **The frame** (`ip_pane_frame`, on the timer; paint only copies it 1:1 and allocates nothing): one pass over the 160 x 240 pane, each pixel the linear mix of its source column and the next by the fraction (`ip_lerp8`, integer maths on the R/B and G lanes at once); while fading both covers are interpolated at their own fractions and mixed by the eased fade (smoothstep, 1.5 s) in the same pass, one frame per tick (the stock canvas has no pinned global alpha). Cost per frame: 38,400 pixels, about 15 integer operations each (about 45 while fading), roughly 0.6 M cycles, 1 to 3 ms on the device's CPU (an estimate; the first thing to check on the device). The earlier whole-pixel window moved one pixel every 312 ms sampled by a 100 ms timer, so it stepped after 3, 3, 4 ticks: an irregular judder. If the frame bitmap cannot be made the pane falls back to the whole-pixel window of the cover (no fade).
- **The timer's interval** (`ip_retime`, `timer_modify` `0x663840`: it sets the timer's duration and restarts its clock, nothing else; never removed or added): `IP_PAN_MS` (40 ms, 25 frames a second) while a split page is the level, the page is in front and the top window (`pod_is_top`) and the pane has a cover (or is being made, or a rotation is armed), `IP_FADE_TICK_MS` (50 ms) during a fade, `IP_TICK_MS` (500 ms) on every other level, with a window above (a message box), with the placeholder, and `POD_DARK_MS` (1 s) while the screen is off (`pod_screen_lit`: the idle-power rule, no pan, no decode, no repaint), and after `EVT_WINDOW_TO_BG` (the timer is removed then). While it ticks fast, the battery / play state / track look runs every `IP_DRIFT_LOOK` = 12 ticks. A frame invalidates **only the pane's rectangle** (`ip_redraw_pane`: `widget_invalidate_force` with a `rect_t` x 160, y 0, 160 x 240, which includes the menu's shadow strip; the function ends in `widget_invalidate`, which uses a given rectangle: `docs/modules/addresses.md`), and a paint whose clip is only that rectangle paints the pane and the shadow but not the menu and leaves the recorded model of the whole page as it was; a tick that moves nothing repaints nothing.
- The cover of the **playing track** for the Now Playing level is decoded separately (`ip_cover`, 150 px).

## Levels and the stock library

A stack of at most 7 levels (`IP_DEPTH`): the root has Music, Cover Flow, Shuffle Songs, Now Playing and Settings; Music contains Cover Flow, Albums, Artists, Songs, Navidrome, Playlists and Shuffle Songs. An artist leads to albums, then tracks, then Now Playing. List labels, subtitles, empty messages and the title bar share a 6 px left margin. Shuffle Songs and Now Playing on the root follow the [iPod classic guide](https://cdsassets.apple.com/live/6GJYWVAV/user/ma1195_ipod_classic_160gb_user_guide.pdf); the root Cover Flow shortcut is an additional convenience, while the guide places it in Music.
A list level keeps only its cursor (`sel`, `top`); its rows are read from the **stock list** while it is the one the stock queries last made (`ip_valid`: the
pointer, the size, the first record, as the Songs page checks). The queries are the ones the stock pages and our other pages run (`docs/modules/addresses.md`):

Empty lists say No albums, No artists, No playlists or No songs as appropriate, using the page's translations.

| level | query | rows |
|---|---|---|
| Albums | `loadLocalClassList(0xf003)` | `REC_ALBUM` |
| Artists | `loadLocalClassList(0xf004)` (the stock Artist / Album Artist setting applies) | `REC_TITLE` |
| an artist's albums | the artists query, then `loadAlbumList(0xf004, the artist's record)` (class `0xff01`) | `REC_ALBUM`; the stock "All songs" record (last in the stock list) is shown **first**, as the stock `local_allsong` "All Songs" with the placeholder cover (`ip_stock_index` maps the displayed row to the stock one: selection, scroll, cover loading, the tap and the query all use it) |
| an album's tracks | the albums (or the artist's albums) query, then `loadAlbumdetailList(0xf003 or 0xff01, the album's record)` (pinned: its second argument is the album **record**, not a row number); `g_class_type` = classinfo[0] (`0xff10` / `0xff11`) as `albuminfo_page_init` leaves it | title, else file name |
| Songs | `loadLocalClassList(0xf001)` (the stock sort order, `sort_flag`) | title, else file name |
| Playlists | `loadLocalClassList(0xf00b)` into `*pdeq_playlist` | `REC_TITLE` |
| a playlist's tracks | the playlists query, `classinfo[1]` = the playlist's id (`REC_DISC`), `loadLocalClassList(0xff13)` | title, else file name |

**Artists.** The first row of an artist's albums is **All Songs** (`TR("local_allsong")`, the stock key "All Songs", translated in every stock table and listed in `pod_i18n.STOCK`): selecting it is the stock path of the Songs page's artist list, `loadAlbumList(0xf004, artist)` then `loadAlbumdetailList(0xff01, the All songs record)` (class `0xff11`, the browsing record left as `albuminfo_page_init` leaves it; the chain is run again before every list read and play, so no other page's query can leave it stale), and the songs are a plain list that plays in that order. An artist with **exactly one album** (the list holds that album and the All Songs record) skips the album list: `ip_open_artist` runs the query to count, then pushes the track level (`K_TRACKS`, whose parent is the Artists level: `ip_run` runs `loadAlbumList`, takes the one album's record and `loadAlbumdetailList(0xff01, it)`), titled with the album as the real iPod does; MENU returns to Artists on the same row.

Going back (MENU) **runs the chain of queries again** (a child's query replaces the parent's list), keeping each level's cursor. The rule of `docs/modules/payload.md`
holds: stock queries run only from the page in front: its open, a wheel step or tap, its window coming back to the front (`EVT_WINDOW_TO_FG`), and the page's tick **only
while the page is the top normal window** (`pod_is_top`; the Songs page's stale timer). **Paint never queries and never reads a stale list** (it draws no rows
until the tick or the next action reads it again).

**Play:** a track in a track list does what the stock Songs row does (`loadSongList` of the shown list, the row's own index winning over a duplicate file name) and then
`start_player(queue, index, class, PLAY_MODE)` + `force_refreshflag = 1`, exactly what the stock album page's Play all button does (`0x525d48`; the page stays where it is, the
queue is copied). No stock Now Playing page opens: the iPod page pushes its own Now Playing level. A file that is gone: the stock message box, nothing starts.

**Navidrome** is a Music menu shortcut to the shared Songs library (`songs_open`), which merges local tracks with the synced Navidrome index, filters unavailable DSD streams, and uses the existing raw stream/offline queue path. It opens over Pod; Back returns to the same Pod screen and cursor. The other Pod-only Albums, Artists and Songs rows keep their stock-local behavior.

**Cover Flow** is the iPod's own screen (level `K_CF`, `docs/modules/ipod-coverflow.md`; the existing page only when its memory is refused).

**Shuffle Songs** (`ip_shuffle_all`) stays on the iPod page: `loadLocalClassList(0xf001)` (the Songs query), a random row (`pod_rand`, the Shuffle page's generator) is the first song, then
`ip_play` as for a tapped track with one addition: `pod_set_mode(MODE_SHUFFLE)` (`patch/shuffle.c`: `mclSetPlayMode(2)`, `notifyPlayMode`, `dmrSendPlayMode`, `write_int_config`, exactly the Play settings
page's sequence, nothing written when Shuffle is already on; the hook turns the request into the payload's flag with stock in List play, [shuffle](shuffle.md)) before `start_player`. The queue is the whole library, the load hook shuffles the songs after the first, and the
iPod's Now Playing level opens (no stock page). An empty library: the stock message `Update Local Music first`; a missing first file: `Storage unavailable`; the mode is then untouched.

## Podcasts (main menu, after Cover Flow)

The main menu's **Podcasts** row (`ROOT_PODCASTS`) pushes `K_PODCASTS`; Music has no Podcasts row (Cover Flow, Albums, Artists, Songs, Navidrome, Playlists, Shuffle Songs). **The pane:** while the main menu's selection is the Podcasts row (`ip_pc_pane`) the right pane shows the asset `ipod_podcasts` (160 x 240 opaque RGB, `tools/mod_icons.py` `ipod_podcasts_pane`, loaded once by `ip_pc_pane_look` from `ip_redraw`) instead of the cover slideshow, still, a vertical gradient in the reference's info pane colours (iPlayr `infoPaneTop` #A7C1D6 to `infoPaneBottom` #3E4D5C; the reference has no Podcasts pane) with a white glyph and glow, and `No Podcasts` (`label_ip_sel`, centred, the 30 px row at `IP_PC_TEXT_Y` under the glyph at `IP_PC_GLYPH_Y`) when no show folder has an episode file. That is `pc_any_episode` (patch/pcmodel.c, stops at the first episode), looked once per visit of the main menu (`ip.pc_any`, reset by `ip_pane_reset` and at open). The pane's timer work is paused while it shows (`ip_pane_step` returns 0, `ip_want_ms` gives `IP_TICK_MS`); off the row the cover pane is back. `test/pod/ipod.py` `podcasts_pane_tests`.

Two levels of our own, `K_PODCASTS` and `K_PC_EPS`, over the podcast model (`patch/pcmodel.c`), not stock deques: `ip_pc_run` fills malloc'd arrays (`ip.pc_shows`, `ip.pc_eps`), `ip.list` is only their non-null marker and `ip_valid` compares the count. **Shows**: `pc_scan_shows` (the Podcasts page's order, newest episode first), the shows with at least one episode file (`count`), row = show title (else the folder). **Episodes**: `pc_load_show` of the selected show, only `PC_LOCAL` ones, newest first, row = episode title (else the file name). **Unplayed dot**: an 8 px blue disc (white on the selection) left of the title when `pc_state` says `PC_NEW` (not played, no place saved; an episode in progress or played has none); every row of the level is indented 16 px for it. No chevron on episodes. **Play**: `ip_pc_play` -> `pg_episode_queue` (patch/podcasts.c, shared with the page's `pg_play`: the show's local episodes as a class 1 queue, `pc_restart`, `pc_speed_apply`, List play), then `start_player` and the Pod's own Now Playing level. Empty: the line `No downloaded episodes`. The model is freed (`ip_pc_trim`) once no Podcasts level is in the stack, and on destroy; it is read again on every `ip_load` (foreground, pop). Local files only: no refresh, download or subscription UI. No new hook, no timer, no new string. Test: `test/pod/ipod.py podcasts_tests`. Device checks: the row on the Music menu (7 rows fit exactly), a show with and without episodes, the dot going away after playing an episode, the queue continuing to the next (older) episode, MENU back through the levels.

## Settings (a list level)

The main menu's **Settings** row pushes `K_SETTINGS`, a static list of three rows (no stock query, no list state). A row with a value shows it **right aligned within the 160 px menu instead of a chevron**
(the label is cut before it); the centre press changes it. Only settings that code already sets are here:

| row | value | centre press |
|---|---|---|
| Shuffle | `Off` / `Songs` (Shuffle on: the payload's flag, shown as mode 2) | `pod_set_mode(MODE_SHUFFLE)`; on `pod_set_in_order()` (List play, or Repeat all kept) |
| Repeat | `Off` / `One` (mode 1) / `All` (mode 3) | cycles Off -> One -> All -> Off with `pod_set_mode` |
| Appearance | `Light` / `Dark` | atomically saves the Pod appearance, then updates the live page |

Shuffle and Repeat are **one stock setting** (the play mode 0 List play, 1 Repeat one, 2 Shuffle, 3 Repeat all; shuffle mode has no repeat of its own), so turning Repeat on turns Shuffle off and the
reverse; Repeat reads `Off` in Shuffle mode. The iPod's Shuffle `Albums` value is not offered (stock has no such mode: Shuffle Albums is a queue order, `patch/shuffle.c`). No backlight or other settings:
their setters are not pinned in this payload. Keys: `Shuffle`, `Songs`, `Off`, `Repeat`, `One`, `All` (our keys, 13 languages, `tools/pod_i18n.py`); the row title is stock `cdrippersettings`.
About and Settings are absent. Appearance, Light and Dark have translations in all 13 languages.

## Appearance (`patch/ipod_theme.c`)

Light is the default. Dark is the black iPod Classic: **the screen stays white** (the reference and the real one do the same); only the case behind the wheel (`#111111`) and the wheel image turn dark (ring `#252526` to `#1D1D1E`, white glyphs; the silver wheel is `#F6F6F6` to `#EEEEEE` with `#9FA9B3` glyphs, MENU in 16 px); it is confined to Pod. The existing insensitive wheel image switches between `ipod_wheel` and `ipod_wheel_dark`, with no widget replacement. `/mnt/data/m1plus/pod-appearance` stores `0` or `1` through `home_write_atomic` and a sibling `.tmp`; missing or malformed content selects Light. A failed save leaves the live appearance unchanged. The palette updates the ten existing hidden text labels, and changing appearance invalidates pre-rendered cover projections and Cover Flow frames.

## The placeholder cover

Anything without art shows one picture: the classic iTunes Cover Flow placeholder, a grey note on a dark gradient, **supplied by the user** (`iTunes-CoverFlow-placeholder-1200.png`, 1200 x 1200). It is scaled once to 256 px with a good filter, kept as `assets/icons/ipod-placeholder-256.png` and written by `tools/mod_icons.py` as the opaque image `ipod_placeholder` (about 15 KB, in the `IPOD` list; Pod only, no stock image or page changes). Users: the cover rows (the All Songs record, an album with no cached cover, a playlist with no art), the Now Playing cover (`ip_cover`) and the artwork pane when no cached cover exists, and Cover Flow's textures for albums without art (`ipod_cf.c`; the stock shelves keep the stock disc). Each is `cc_decode` of the image name down to the size needed, over the usual flat grey guard.

## Library artwork

Four page-owned 54 x 54 RGBA bitmaps (about 47 KB; the mosaic quadrants are 27 px) hold visible covers. The page timer prepares one row or decodes one cover part per tick; paint only copies resident images. Albums and an artist's albums use `cc_album_key`; a row without art (the All Songs record, an album with no cached cover) shows the placeholder; Playlists inspect at most 16 songs and retain up to four distinct album keys for a mosaic. One album fills the cover; two or three repeat a quadrant to fill the square. Source paths are copied before another stock query can replace the deque, and playlist inspection preserves the foreground playlist deque. A reused row is checked against its record identity before paint, so scrolling or a changed library cannot show another row's cover.

Cached 168 px covers are shared with Albums and Cover Flow. On a mounted card, missing visible covers are submitted to the existing `CC_MISSING` builder only when it is idle. Pod tracks ownership and stops only its own worker when backgrounded, leaving artwork lists or destroying the page. New cache files replace placeholders on the timer. No card, no art, allocation failure or a worker owned by another page leaves a placeholder and working navigation. The timer runs at 33 ms while preparing/decoding, 100 ms while waiting for its worker, then returns to the normal idle pace.

## Internal page slides (`patch/ipod_render.c`)

Push and MENU pop use a 280 ms integer smoothstep slide (the reference's ease in and out): 160 px between split menus (the cover pane stays still), 320 px when opening or leaving a full-width list. **Fullscreen pages (Now Playing, Cover Flow) open with the split** (`ip_render_transition(dir, 0)`, `ip_paint_split`): the fullscreen page is drawn still, over it the outgoing menu half slides 160 px left and the pane 160 px right (the old display model's commands left and right of `IP_SPLIT_X`, each replayed at its own offset under its own clip); closing runs it backwards (the old fullscreen model drawn still, the live split page painted twice, its halves clipped as they slide in). A long press of MENU pops to the main menu with the slide of the last level. Root MENU still closes immediately. Wheel movement, rapid repeated navigation, appearance changes, background and destruction cancel a transition.

The renderer records a bounded display model (192 commands and 2,048 owned text words in each of two buffers, about 40 KB total). At navigation, it clones at most eight referenced RGBA images before their owners can change or free them. It never samples the framebuffer. Allocation failure, unsupported images or model overflow falls back to immediate navigation. Paint replays the outgoing model and draws the incoming page through intersected viewport/page clips, then restores the canvas origin and clip. Paint never allocates, decodes or queries. The existing page timer runs at 33 ms during the slide (`timer_modify`); cover work pauses until it finishes. Snapshots are released at completion, cancellation and destroy; there is no additional timer or hook.

## Entry and exit

- Entry: `ACT_IPOD` (22), the menu item id 19 (`pod_pages.ITEMS`, after Settings, saved as `k`, hidden by default: Settings > Main Menu shows it, the Extras page lists it (Play group)
  with the default menu's items). The label is the name `Pod`, a plain text in every language (like `M1+ Music`); no translation key.
- Exit: MENU on the main menu (`navigator_back`; the stock window under it and its status bar come back). There is no hardware back key in this payload (the stock key handler
  `on_wm_keyup_fun` handles the media keys; nothing here changes it).
- Open again while up: nothing. A window that will not open, an asset missing a widget: the page returns -1 and leaves what it did not make.

## Timer and the page's life

`ip_first` (50 ms one-shot) starts `ip_tick` (`IP_DRIFT_MS` on the main menu, else 500 ms; `ip_retime` changes it with `timer_modify`, above). The tick steps the cover pane (`ip_pane_step`) and looks at the battery, the play state, play mode, the playing track, the position (on Now Playing) and the
queue size; a change repaints the screen. A new track makes the cover (the decode is on the timer, never in paint: the Cover Flow cache file via `cc_url`, else the `/tmp`
file demo writes a little after the track changes, else the placeholder). The timer goes on `EVT_WINDOW_TO_BG` and returns on `TO_FG` (which also reads the list again); destroy removes it
and frees the cover. State is one struct in `.scratch`, cleared at open and destroy; a destroy of another window leaves the page alone.

## Playback limits

Now Playing rotation has no action; select toggles play/pause. Scrubbing, wheel volume and
a center-press mode cycle are unsupported. Stock `seek_time` (`0x4e0544`) can block
the UI thread for 2 seconds; direct `mclSetSeek` bypasses the stock pause/DLNA handshake.
`set_devicevolume` (`0x4d6cf8`) depends on output-specific state without a verified
universal volume readback. Hardware volume keys retain the tested stock path.

The wheel is silent. `hciplayer` owns the PCM at the track's exact format/rate; there
is no dmix configuration. A second PCM opener can race a track transition, cause EBUSY
or power the DAC/amp unexpectedly. No process is spawned for wheel sounds and no audio
daemon patch is added.

## Research sources (ideas and constants only, no code)

- **Apple's Music 404-page iPod** (a web page that mimics the wheel): the ideas of a reversal threshold, a dead zone judged on the chord of a move rather than the point, a
  smoothed angular speed with a threshold, tiers of rows per step that climb with the time held fast, and a nudge at the end of a list. Its code is proprietary: nothing is
  copied, and only its numbers are followed (tiers 1, 2, 3, 5, 8, 13, 21, 34; speed clamp 400 degrees a second; smoothing 0.15; 180 degrees a second; 500 ms a tier; 250 ms reset).
- **q2-pod**: navigation research only; no code borrowed.
- **iPlayr / keremersu35/ipod-player**, inspected at `76f9a730db27d0ce281e89a46db018c432178e6c`: the equal-width split menu with a full-height cover pane, primary black and secondary grey text, glossy materials and light/dark appearance inform the appearance, title bar, battery, selection, Now Playing, 280 ms slides, split navigation, long-press MENU and artwork timing. No reference code or media was copied or executed. The navigation display model and timer integration are specific to this firmware.

## Addresses used

Pinned in `tools/pod.py`: `prev_quick_click` `0x4cccb0` (the twin of `next_quick_click`; prologue, the `e->time` read and the 1 s guard pinned), `loadAlbumdetailList` `0x4eea98`
(prologue, the Albums class compare, the record argument), `timer_modify` `0x663840` (prologue, the duration store `sw s1, 0x40(s0)`), the data word `system_bar` `0xa06f90` (checked against `.dynsym`). Already pinned and used: `window_open`, `widget_grab` /
`widget_ungrab`, `widget_to_local`, `widget_prepare_text_style`, `canvas_fill_rect`, `canvas_set_fill_color`, `canvas_draw_text_in_rect`, `canvas_measure_text`, `canvas_draw_image`,
`tk_utf8_to_utf16_ex`, `loadLocalClassList`, `loadAlbumList`, `loadSongList`, `start_player`, `force_refreshflag`, `playpause_quick_click`, `next_quick_click`, `mclGetPlayStatus`,
`mclGetPlayPos`, `get_playtimeandlength`, `mclGetPlayMode` and the `patch/shuffle.c` setters (`pod_set_mode`, `pod_set_in_order`, `pod_rand`), `timer_add`, `timer_remove`, `bitmap_*`, libc `time` / `localtime`.

## Known limits

- Not run on a device: the canvas calls, the fullscreen window (the status bar must be hidden by `fullscreen`, as for the lock screen), the touch feel (the 15 degree step, the chord dead zone, the reversal and tier constants, the 12 px tap slop are guesses to tune), the cover pane's pan and cross-fade (the repaint cost, the mix of 38 K pixels at 15 fps) and Cover Flow's frame rate are only proven under emulation and with demo's own AWTK code (`test/awtk_fill.py`).
- The page timer's interval is set in one place (`ip_want_ms`: `IPCF_FRAME_MS` while a page slides, row art prepares/decodes or Cover Flow is busy; `IP_DRIFT_MS` while the cover pane pans or the owned row-art worker runs; else `IP_TICK_MS`) and changed in place
  with `timer_modify`; the timer is never removed or added while the page lives.
- No sound (above). No rotation action on Now Playing (above), no scrubber. No cover flip in Cover Flow (the centre opens the tracks as a list). No search, no Genres,
  Composers or Folders, no Shuffle Albums value. The cover pane does not follow the row and shows only covers already in the Cover Flow cache (from its 168 px file, upscaled to 264). Not built from the reference: the volume overlay and wheel volume (no safe stock volume read-back, “Playback limits”), the progress / scrubber cycle, held next / previous seeking (`seek_time` blocks the UI thread; `mclSetSeek` alone is unpinned and untested), and the Cover Flow to Now Playing cover flip (80 to 5 degrees: the Cover Flow renderer has no cheap rotation of a single cover).
- No clock in the title bar (the iPod's has none); long translated labels are cut with an ellipsis to the 130 px root text box (Spanish, Russian and Ukrainian Shuffle Songs; the Settings rows French Shuffle and Appearance, German Repeat and Appearance, Polish Repeat, Spanish Shuffle and Repeat values, Russian Shuffle and Appearance, Ukrainian Shuffle: `test/pod/ipod.py` i18n_tests lists them).
- Albums are in the stock query's order, not Settings > Library > Album Order.
- The play queue is the stock one: `start_player` copies the shown list; a Songs list of thousands of rows is copied once per play, as the Songs page does.

## Device checklist

- Appearance: Settings > Appearance changes only the case and the wheel (the screen stays white). MENU and reopening retain it.
- Artwork: start with no cover cache; Albums and Songs fill their visible thumbnails without visiting another page. Playlists show a full cover or a four-quadrant mosaic. Scroll rapidly, remove the card, background and reopen; no stale covers, crash or growing heap.
- Page slides: enter Music, Settings, library lists and Now Playing; MENU reverses the slide. Text and cover pixels stay sharp, no outgoing fragments remain, quick input settles immediately and playback stays smooth. Check memory by repeatedly opening/closing Cover Flow during transitions. Now Playing and Cover Flow open with the split (menu half left, pane right, the page uncovered) and MENU closes it; a held MENU (0.5 s) goes to the main menu. Check the 280 ms pace feels like the reference.
- Menu: Settings > Main Menu > Pod on; the Pod row opens the page; the status bar is gone (the page is 480 tall: nothing under the bottom edge); MENU closes it and the bar returns.
- Wheel: drag round the ring: one row per 15 degrees, both ways, the selection stops at the ends and never wraps, a hard stop with no bump (the music does not stutter); the window scrolls with the cursor in a long list; a drag across
  12 o'clock does not jump; a drag that starts on the centre button does nothing; a tap on the centre selects; taps on MENU / `|<<` / `>>|` / `>||` act; a touch in the square's corners does nothing.
- Feel (tune `IP_STEP` first): a slow turn is one row per 15 degrees (neither too jumpy nor too heavy; try 12 / 18); turning round at the end of a drag does not flicker the cursor
  (8 degrees of hysteresis; if the first reverse step feels late lower `IP_REVERSE`); a finger that crosses the centre does not jump the list; on Songs a fast sustained turn
  speeds up after about half a second (1, 2, 3, 5, 8, 13, 21, 34 rows), slowing or stopping brings one row back at once, a pause or turning back resets; a list of 16 rows or fewer never
  accelerates; at the first and last row the cursor stops dead (no bump, no wrap).
- Lists: Albums -> an album -> a track plays and Now Playing shows title, artist, album, `n / N`, the bar moves, the time counts; MENU returns to the tracks (same cursor); Artists -> albums
  -> tracks; Songs; Playlists -> tracks; Cover Flow and Settings open and Back returns; Shuffle Songs plays.
- Title bar: the title on the left, no clock; the battery agrees with the real one (charge it); the blue play glyph next to it follows play / pause.
- Cover pane: the cover fills the pane edge to edge and pans about 3 px a second with **no jiggle**; every 6 s the next random cached cover cross-fades in over 1.5 s (check the fade is smooth, not choppy, and the wheel stays responsive during it: if it is too slow, raise `IP_FADE_TICK_MS` or cut instead); it is the playing album's cover (play a track from a
  cached album, MENU back: it changes and stays), else the random rotation, new after MENU back to the main menu; the wheel and music stay responsive; with no cover cache (never opened Cover Flow / Albums)
  the placeholder, still; the pane stops moving on every other level (the timer slows to 500 ms) and in a message box.
- Shuffle Songs: playback starts at a random song with shuffle on, the iPod's Now Playing shows it, Next picks another random song. Settings: Shuffle and Repeat values change on the centre press and agree with
  Settings > Playback; MENU returns to the root.
- Idle: nothing queued shows `Not Playing`; the placeholder in Now Playing; sleep / wake and the lock screen do not leave the page broken; a language change re-draws in the new language.
- Music keeps playing (no glitch) while the wheel turns; the page leaves no timer (go to Home and back).
