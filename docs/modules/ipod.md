# Virtual iPod

**Sources:** `patch/ipod.c`, `patch/ipod_render.c` (slides), `patch/ipod_theme.c` (appearance),
`patch/ipod_cf.c` ([Cover Flow screen](ipod-coverflow.md)), `tools/pod_ui.py` (`build_ipod_page`,
`ui/m1plus_ipod.bin`), `tools/mod_icons.py` (`ipod_wheel`, `ipod_placeholder`, `ipod_podcasts_pane`),
`IP_*` in `offsets.inc`.
The optional Pod item opens a fullscreen iPod Classic-style page: a 240 px display above a 240 px
touch-wheel area. It is hidden from the main menu by default. Code keeps the `ipod` and `IP_*`
names; the device label is Pod (a brand, plain text in every language). The row's glyph
(`pod_ic_ipod`) is `assets/icons/custom/ipod.svg`.

**No stock hook and no boot work.** The page owns its `EVT_AFTER_PAINT`, pointer grab,
foreground/background/destroy events and one page timer, using stock calls shared with Albums,
Songs, the mini player and Cover Flow.

**The Pod shows only Pod levels.** Every row opens a Pod level, never one of our full pages; a
function without a Pod-designed level is left out.

Borrowed numbers, own code: the look follows [iPlayr](https://github.com/keremersu35/ipod-player)
(MIT, Kerem Ersu: values, metrics, timings, behaviour) and the wheel's tiers and thresholds follow
Apple's Music 404-page iPod; q2-pod was navigation research only. No code or media was copied. The navigation display model and timer
integration are specific to this firmware.

## Layout (320 x 480)

The window is fullscreen (as the lock screen's `screensaver_page`; the stock status bar is not
drawn), colour `#C6C9CE`. The screen `ipod_screen` (320 x 240, insensitive) is painted by
`ip_on_paint`; the wheel view `ipod_wheel` (220 x 220 at (50, 250)) is the touch target with a
decorative insensitive picture over it.

| Part | Rule |
|---|---|
| Title bar | 20 px, four-stop gradient (`#FDFDFD`, `#E7E7E7`, `#D8D8D8`, `#ABABAB`), 1 px divider `#6A6A6A`; title on the left (16 px, x `IP_TEXT_X` 6, the rows' inset too: the nano photos' text sits close to the left edge), no clock; play-state glyph and battery on the right |
| Text rows | nine rows sharing the 220 px under the title bar exactly (row i at `20 + i x 220 / 9`, 24 or 25 px, no blank strip); 18 px, padding 8 px (`IP_TEXT_X`); every text cut with an ellipsis; all Pod text in the soft coverage gamma 1.15 while the page is in front (`tg_soften`, [fonts](fonts.md)) |
| Cover rows | four 55 px rows sharing the 220 px under the title bar (Albums, an artist's albums, Playlists, Genres); the cover fills the row's left 55 px, text at x 63; Playlists and Genres rows have no cover (text at the text inset, the line from x 0) and the small line is the song count (`%d song` / `%d songs`) or the genre's `%d Artists, %d Albums` (groups of the stock genre query `style like '<name>'`, Unknown Genre `ifnull(style,'')=''`, through the hooked `toolsQueryDbTable`, raw tags whatever Split Genres says), blank until the row has been read; the title is in the regular face, Latin or not, so a list never mixes weights (the bold face has no CJK); a 1 px `rule` line runs under every unselected row from x 55 to the right edge, except at the bottom of the screen |
| Selection | five blue stops `#3EABE3`..`#1584D3`, highlight and rule lines, white text and chevron; only the selected row has a chevron |
| Split menus | list x 0..160 (`IP_SPLIT_X`), cover pane x 160..320, no rule between, soft shadow over the pane's left edge |
| Battery | read from `*system_bar` (`pgbar_battery`, `img_battery`): 24 x 12 frame, green fill (red at 20 % or less), full green while charging; no bar, no fill |

Decisions:

- **The screen is white in both appearances** (as the reference and a real iPod).
- The window is fullscreen, no close animation.
- Battery from the system bar: no new stock function.
- **Song lists have no cover**, and the row worker does no cover work for them; a speaker marks the playing
  track. Music > Songs shows five two-line rows (`IP_SONG_ROWS`, 44 px each): the title (regular, as every
  list row) over the artist (`IP_SONG_SUB_Y`), with a hairline under each row. Every other list of tracks uses the
  nine plain title rows.
- All text is the device font (Inter Medium); hierarchy is size and colour only.
- A list opened from a record is titled with it (album, artist, playlist).

Text styles are thirteen hidden labels in the asset (`label_ip_*`). Values in settings are 14 px blue on
white, white on the selection.

**Main menu:** Music, Cover Flow, Podcasts, Settings, Shuffle Songs, **Now Playing** (last, only while something
plays or is paused). The order is the iPod classic's default; Cover Flow is also in Music. When the Now
Playing row appears or goes the cursor stays on the same item (on Now Playing, it moves up to Shuffle Songs).

**Now Playing screen:** placed by Apple's iPod classic Now Playing screenshot (user guide,
320 x 240), pixel for pixel:

- The cover turned as on the iPod: x 10 .. 144, the near (left) edge y 35 .. 169, the far (right)
  edge y 44 .. 159, perspective columns, and a 36 row reflection under it (to just over the bar, as on the user's nano photo), shorter towards the far
  edge. `ip_tilt` makes it as one opaque bitmap once per cover or appearance change; paint copies it.

- Text column at x 157 (13 px right of the cover, as the user's nano photo), cap tops at about
  y 60, 80, 98 and 134: title 18 px black in the bold face when it has every character
  (`ly_title_face`, else the default font), artist and album 16 px dark grey (`np_text` `#3C3C3C`, the nano photo's lighter lines), then `n / N` (14 px, the same grey) for
  the queue place one row lower, the rating row left empty as on the iPod.
- The active stock play mode is marked top right, 3 px under the title bar, right edge x 311
  (shuffle, repeat or repeat one; none in list play). The shuffle mark is the slider's own drawing
  at `IPOD_MODE_SRC` (`ipod_shuffle_big(n)`), so the two match.
- The progress bar is y 206 .. 219, x 58 .. 262, row by row the screenshot's colours: a 1 px
  darker rim, the fill a light upper half over a saturated lower half with a dark then a light
  column where it ends, the empty track a sunken grey with no outline. One clear row, then an 8
  row reflection from 22 %.
- `m:ss` elapsed, right aligned 11 px left of the track, and `-m:ss` remaining 11 px right of it.

- **Now Playing never blinks.** While the player changes track it briefly has no time or no track,
  so the bar is drawn from the last valid position and length, and the last text and cover stay for
  `IP_NP_GONE` (3) looks. Only then does it say `Not Playing` and the cover becomes the placeholder.
- **A song started from a list is shown at once.** `start_player` returns before the player moves,
  so `ip_play` and `ip_pc_play` keep their queue and the started record (`ip_np_track`): Now Playing
  slides in with its text, cover and an empty bar until the player reports that track, or for at most
  `IP_NP_PEND_MS` (3 s), then follows the player.
- Nothing queued: `Not Playing`.

## The wheel

Touch events come from the wheel view (`EVT_POINTER_DOWN/MOVE/UP/ABORT`); the view is grabbed for
the touch so the release arrives wherever the finger goes. Touch outside radius 110 is ignored.

| Rule | Value |
|---|---|
| Regions | radius < 45 (`IP_HUB_R`): centre button; 45..110: ring |
| Angle | `ip_angle`, degrees clockwise from 12 o'clock in sixteenths, integer code (error under 0.2 degree) |
| Step | one row per 20 degrees (`IP_STEP`); the leftover carries; a push or pop clears it |
| Ends | **hard stop**: no wrap, no bump, no timer touched |
| Chord dead zone | `IP_DEAD_R` 11 px: a move whose line passes closer than that to the centre is rejected; a drag that began on the centre button turns nothing |
| Reversal | `IP_REVERSE` 8 degrees: opposite travel is swallowed until it reaches 8, so the first reverse step comes after 8 + 20 degrees |
| Long lists (> `IP_LONG` 16 rows) | tiers of 1, 2, 3, 5, 8, 13, 21, 34 rows a step, climbing every `IP_TIER_MS` 500 ms while speed stays above `IP_FAST` 240 degrees a second; speed clamped at `IP_VMAX` 400 degrees a second, smoothed by 0.15, reset by a gap over `IP_PAUSE_MS` 250 ms or a reversal; shorter lists always move one row |
| Tap | a touch that turned no step and moved under `IP_TAP_PX` 12 px |
| Long press of MENU | `IP_LONG_MS` 500 ms: pops every level to the main menu; on the main menu it does nothing |
| Hold of `|<<` / `>>|` (Now Playing only) | `IP_LONG_MS` 500 ms: scans back / forward, 1 s a tick for `IP_SCAN_SLOW_TICKS` ticks (10x), then 3 s (30x); on other levels a hold is the tap |

A tap on the centre button selects. On the ring, by sector: top MENU (back; on the main menu
`navigator_back` closes the page), bottom play/pause, left previous, right next (the skip calls read
the event time, as stock ignores a click within a second of the last). An abort ends the touch and
acts on nothing. On Now Playing, rotation is the volume and select the scrubber (below).

**Hold-to-scan** (`ip_scan_tick`, `ip_scan_seek`, `ip_scan_commit`): the scan moves a target of its
own (never re-read from the player), clamped to 0 .. length - 1, and the bar and times show it.
Every `IP_SCAN_SEEK_MS` (300 ms), when the target moved, it calls `mclSetSeek(target + CUE start)`,
which only sends `{mcl-seek%d}` to hciplayer: no wait, no resume, no DLNA. A paused player stays
paused and the UI never blocks. Release seeks once more if the target moved and skips nothing; the
target stays on the bar until the player is within 1 s of it or `IP_SCAN_HOLD_MS` ends. A turn, an
abort, a track change or leaving Now Playing cancels. Stopped, nothing queued, no length, Radio or
DLNA: a hold does nothing, not even the tap. The Pod never calls `seek_time`.

**The Now Playing wheel** (`ip_np_turn`, `ip_np_select`, `ip_np_tick`), as the iPod classic's:

- **Volume.** A step runs stock's volume dialog steps `VOLP_ADD` / `VOLP_DEC` `IP_VOL_STEPS`
  times with the Pod window as the context, then stock's stop `VOLP_STOP` removes the 3 s
  auto-close timer they add to it (as [volume](volume.md) does). The cap, Bluetooth's volume word,
  `set_devicevolume` and the saves stay stock's. The bar shows the volume (Bluetooth's word on
  Bluetooth) with a quiet and a loud speaker instead of the times for `IP_VOL_SHOW_MS`; it slides
  in from the right over the progress bar going left, and out again to the right
  (`ip.vs_t0`, `ip.vs_back`, `IP_SCRUB_SLIDE_MS`). Line Out
  does nothing (fixed level, as the volume keys).
- **The centre** cycles the views (`ip_np_select`, `ip_np_go`): progress bar, scrubber, shuffle
  slider, lyrics, then the progress bar again, skipping a view that cannot come up
  (`ip_np_can`). Each new view slides in from the right edge over `IP_SCRUB_SLIDE_MS`
  (smoothstep), pushing the old one out to the left, an idle end's return to the progress bar too
  (`ip_np_slide`). Between the bar views only the bar strip moves; to or from the
  lyrics the whole page does. A turn to the volume or a dropped view ends a slide at once. A track
  change, leaving the level or the page going to the back drops the scrubber and the slider.
- **Scrubber.** Comes up when a hold scan could run (`ip_scan_ok`): an empty track (no fill) with
  a diamond knob (`IP_NP_KNOB`) on the scan's target, as the iPod's: each row in the bar's blue of
  that row with the rim colour as outline, and a reflection mirrored with the bar's
  (`ip_np_strip`). A step moves it `IP_SCRUB_S` seconds times the wheel's speed tier; only the
  knob moves while the finger is on the wheel, and its release seeks there once
  (`ip_scrub_send`), as the iPod does. Leaving it, or `IP_SCRUB_IDLE_MS` without a turn, sends a
  seek still due and holds the target as the scan's release does. A hold scan drops it.
  Play / pause is only the bottom sector.
- **Shuffle slider** (`ip_shuf_strip`), with a track: in the bar's place our own shuffle mark
  (`ipod_shuffle_big`, drawn at its size by `tools/mod_icons.py`) `IP_SHUF_ICON` px where the elapsed time was, then Off, Songs and Albums in three equal slots
  over one rail, `IP_SHUF_X` and `IP_SHUF_W` (narrower than the track) by `IP_SHUF_H`, from the user's nano photos: a faint rim
  with cut corners round a groove shaded under its top, no dividers, and a raised thumb (the progress
  bar's gloss row for row: its track's greys with a little of its blue; no outline, soft sides; the rail's full height over its rim, with its cut corners) over the chosen third that glides there in `IP_SHUF_THUMB_MS`. The names never move: all
  are drawn in left-aligned 14 px styles at fixed boxes (`label_ip_np3`, the chosen one `label_ip_shuf` in the selection blue). A step moves the choice and sets it at once
  with `pod_set_shuffle_kind` ([shuffle](shuffle.md)); `IP_SCRUB_IDLE_MS` without a turn slides
  the progress bar back.
- **Lyrics** (`ip_lyr_load`, `ip_lyr_parse`, `ip_lyr_layout`, `ip_lyr_paint`), when the track has
  a `.lrc` (or `.LRC`) beside it with a line of text (stock's file, [online art](onlineart.md)):
  the iPod's plain text. The file is read whole (at most `IP_LY_BUF` - 1 bytes, a cut file loses
  its partial last line) into one calloc'd block kept until the page closes; time tags and tag
  lines (`[ar:...]`) are dropped, blank lines kept single. The title bar names the song; a small
  cover (`IP_LY_ART`), the album (14 px) and the artist (18 px, bold when the face has it) beside
  it; the lines under it in 14 px, `IP_LY_LINE` apart, wrapped to `IP_LY_W` at the last space
  (at the first paint). The wheel scrolls the whole page a line a step with the list speed tiers;
  a thin scroll bar (`IP_LY_SB_W`) at the right edge. A track change reads the new track's file,
  or goes back to the progress bar. No idle end.

## The cover pane

The split pages (main, Music, Settings) show album art in the right pane (160 x 240) edge to edge.
The menu casts a 10-column shadow on it (52 % opaque at x 160, falling like a gaussian), one RGBA
bitmap made at open. All pane work is on the page's one timer; paint only copies.

- **Pan:** a cover pans across a 24 px margin in 7.5 s, every other cover the other way, at 1/256 px
  fixed point and counting only time shown. The placeholder stands still.
- **Rotation:** up to 8 random albums that already have a cached cover; a cross-fade of 1.5 s
  every 6 s. The playing album's cover replaces the rotation: it fades in gliding half the margin to the centre, then stays still. No cached covers: the placeholder.
- **Sharp sources:** the playing album uses stock's own `/tmp/coverpic.jpg` or `externpic.jpg` when
  ready; the next rotation album is extracted at 264 px into one RAM file `/tmp/m1plus-pane.jpg`
  by the shared builder's worker, never onto the card. Otherwise the 168 px cache file is used (see
  [covercache](covercache.md)).
- Slots: two 264 x 264 bitmaps and one pane-sized mix bitmap (about 710 KB), freed at destroy.
- **Timer:** 40 ms while a split page is in front with a cover, 50 ms during a fade, 500 ms
  otherwise, 1 s while the screen is off (no pan, decode or repaint). A frame invalidates only the
  pane's rectangle.

On the main menu, the Podcasts row shows the still asset `ipod_podcasts` (`No Podcasts` when no
show has an episode file) instead of the slideshow. After a wheel step it waits until the selection
has rested on the row for 250 ms, so a fast turn past it does not flash the picture, then cross-fades
in over 250 ms (smoothstep, blended into the covers' frame on the timer; `No Podcasts` appears when
the fade ends). Off the row it fades out the same way at once. MENU back onto the row shows it
without a fade.

## Levels and the stock library

A stack of at most 7 levels (`IP_DEPTH`). Music holds Cover Flow, Playlists, Artists, Albums,
Songs, Genres and Composers (the iPod classic's order, then the two extra lists); Shuffle Songs is a main menu row. An artist leads to albums, tracks, then
Now Playing. A list level keeps only its cursor; rows are read from the stock list while it is the
one the stock queries last made (`ip_valid`).

| Level | Query | Rows |
|---|---|---|
| Albums | `loadLocalClassList(0xf003)` | album |
| Artists | `loadLocalClassList(0xf004)` (the stock Artist / Album Artist setting applies) | title |
| An artist's albums | the artists query, then `loadAlbumList(0xf004, record)`; the stock "All Songs" record is shown first | album |
| An album's tracks | the albums query, then `loadAlbumdetailList(0xf003 or 0xff01, record)` | title, else file name |
| Songs | `loadLocalClassList(0xf001)` | title, else file name |
| Genres | `loadLocalClassList(0xf006)` | title |
| A genre's songs | genres query, `songs_genre_record(name, unknown)` (the stock row tap's record; stock tags, no genre split), `loadLocalClassList(0xff09)` | title, else file name |
| Composers | `loadLocalClassList(0xf005)` | title |
| A composer's albums | composers query, then `loadAlbumList(0xf005, record)`; the tracks use `loadAlbumdetailList(0xff02, record)`; a composer with one album opens its tracks, as an artist does | album |
| Playlists | `loadLocalClassList(0xf00b)` | title |
| A playlist's tracks | playlists query, `classinfo[1]` = id, `loadLocalClassList(0xff13)` | title, else file name |

- **Artist single-album shortcut:** an artist with exactly one album (besides All Songs) skips the
  album list and opens the tracks, titled with the album as a real iPod does; MENU returns to Artists.
- Empty lists say No albums, No artists, No playlists or No songs (also for an empty Genres or Composers list); an empty episode list says No
  downloaded episodes.
- **Cover Flow** is the Pod's own screen (level `K_CF`, [ipod-coverflow](ipod-coverflow.md)); the
  existing page opens only when its memory is refused.
- Going back runs the chain of queries again, keeping each level's cursor.
- **Queries run only from the foreground page:** its open, a wheel step or tap, its window coming
  back to the front, and its tick while it is the top normal window (`m1_is_top`), as in
  [payload](payload.md). **Paint never queries and never reads a stale list.**
- Albums are in the stock query's order, not the Albums "..." card's order.
- **Play:** a track does what the stock Songs row does (`loadSongList`, then `start_player` and
  `force_refreshflag`), and the Pod pushes its own Now Playing level. A missing file shows the
  stock message box.
- **Shuffle Songs** loads the Songs query, picks a random first song, then plays as a tapped track
  with `pod_set_mode(MODE_SHUFFLE)` first ([shuffle](shuffle.md)). An empty library: stock's
  `Update Library first`; a missing first file: `Storage unavailable`, and the mode is left
  untouched.
- **Podcasts** (`K_PODCASTS`, `K_PC_EPS`) over the podcast model (`patch/pcmodel.c`): shows with at
  least one episode file, then local episodes in the show's Episode Order ([podcasts](podcasts.md)).
  An 8 px blue dot marks unplayed episodes. Play goes through `pg_episode_queue`. Local files only.

## Settings level

Three rows; a value shows right aligned instead of a chevron.

| Row | Value | Centre press |
|---|---|---|
| Shuffle | Off / Songs / Albums | `pod_set_mode(MODE_SHUFFLE)`; on, `pod_set_in_order()` (Albums only from the Now Playing slider) |
| Repeat | Off / One / All | cycles with `pod_set_mode` |
| Appearance | Light / Dark | saves the Pod appearance, updates the live page |

**Shuffle and Repeat are one stock setting** (modes 0 List, 1 Repeat one, 2 Shuffle, 3 Repeat all),
so turning one on turns the other off; Repeat reads Off in Shuffle mode. The row's press only
flips Off / Songs; Albums is chosen on Now Playing's shuffle slider ([shuffle](shuffle.md)). Other
settings are absent: their setters are not pinned.

## Appearance

Light is the default. Dark turns only the case behind the wheel (`#111111`) and the wheel image
(`ipod_wheel_dark`); the screen stays white. `/mnt/data/m1plus/pod-appearance` holds `0` or `1`
(atomic write; missing or malformed is Light; a failed save leaves the live appearance). Changing
appearance invalidates pre-rendered cover projections and Cover Flow frames.

## The placeholder cover

Anything without art shows one picture: the classic iTunes Cover Flow placeholder (a grey note on a
dark gradient, supplied by the user), scaled to 256 px as `assets/icons/ipod-placeholder-256.png`
and written as `ipod_placeholder`. It serves the All Songs record, albums with no cached cover,
Now Playing, the pane and Cover Flow's textures.

## Library artwork

A pool of `IP_ROW_SLOTS` (12) page-owned 55 x 55 bitmaps holds cover-row artwork. A slot is keyed by
(kind, index, id), not by screen position: a row that stays on screen, or comes back, finds the slot that already holds its cover, so a scroll step decodes only
the newly exposed row. The timer works through the wanted rows in order: the four visible ones, then `IP_ROW_AHEAD` (3) rows beyond them in the direction of the
last scroll, then 3 on the other side (prefetch, in idle ticks only; visible rows always come first). A new row takes the least recently wanted slot, never one
wanted now, and prepares and decodes its first part in the same tick; every tick decodes at most one cover, and paint only copies. The fast
timer (`ip_rows_more`) runs until every wanted row is drawn. Albums use `cc_album_key`; a playlist row's slot holds no bitmap, only its song count, read
once (`CLASS_PLAYLIST_SONGS`) when the row first comes into view. A slot is looked up by its record identity, so scrolling cannot show another row's cover. Cached 168 px covers are
shared with Albums and Cover Flow ([covercache](covercache.md)); missing ones are submitted to the shared builder for the visible rows only, and only when it is
idle; Pod stops only its own worker. A row not decoded yet shows the placeholder (one row-size copy, `row_ph`), and so does a
cover that is not cached; without card, art or memory it stays and navigation works. The page frees all slots on exit.

## Page slides (`patch/ipod_render.c`)

Push and MENU pop use a 280 ms slide eased out (`SLIDE_MS`; quick from the press, as a real iPod nano filmed at 30 fps): 160 px between split menus (the pane
stays still), 320 px between full-width lists. A full-width list opened from a split menu (Music >
Songs) uses the cover slide (`ip_paint_cover`, width -1, 300 ms `COVER_MS`, at a steady speed as the
real iPod's, not eased): the pane stays still, the
list comes in over it from the right, and its left edge pushes the menu half out on the left; MENU
back runs it backwards. The menu half is cut at its own edge (its white fill is full width) and its
shadow is drawn alone over the pane (`ip_cover_shadow`). Fullscreen pages (Now Playing, Cover Flow) open with
the split (200 ms, `SPLIT_MS`): the page is drawn still while the outgoing menu half slides left and the
pane right; closing runs it backwards. During the split the shadow fades with the slide
(`ip_render_shadow_skip`: its leading columns left out, none to all as the halves part, all to none
as they close), so it is whole only at rest and there is no seam when the halves meet. The slide's time counts from when the new level's list has loaded
(`ip_render_restart`), so a slow query (Music > Songs on a big library) does not eat the slide. Wheel movement, rapid navigation, appearance changes, background and
destroy cancel a transition.

The title bar: between split menus it stays put over the slide, already titled for the new level;
into or out of a full-width page (Music > Artists, an album, and MENU back) it slides with its
page, the split menu's bar with the menu half. Into or out of a full-screen page (Now Playing, Cover Flow) it waits: the
picture comes without it, then the whole bar drops in from above the screen in
`IP_BAR_DROP_MS` (100 ms); opening one it first waits `IP_BAR_WAIT_MS` (250 ms) after the split, as the iPod (`ip_bar_wait`,
`ip.bar_hold`, `ip.bar_t0`, `ip_paint_bar` shifting the canvas's y). The drop's end counts as the
transition's end for the timer's playback look.

The renderer records a bounded display model (192 commands, 2,048 text words, three buffers, about 60
KB) and clones at most eight referenced images, never sampling the framebuffer. Overflow or
allocation failure falls back to immediate navigation. Paint never allocates, decodes or queries.
`ip_render_raster` records a paint dry (nothing drawn on the canvas) into a third buffer and lays it
into pixels: fills and images as the canvas draws them, text from the style's font with each glyph's
alpha blended as `canvas_draw_text_in_rect` places it (left, vertically middle). Cover Flow's card face
uses it.
The page timer runs at 33 ms during a slide; cover work pauses.

## Entry, exit and timer

- **Entry:** `ACT_IPOD`, menu item id 19, hidden by default (Settings > Main Menu shows it; the
  Extras page lists it).
- **Exit:** MENU on the main menu (`navigator_back`). There is no hardware back key in the payload.
- **Timer:** `ip_first` (50 ms one-shot) starts `ip_tick`. Its interval is set in one place
  (`ip_want_ms`) and changed in place with `timer_modify`, never removed or added while the page
  lives. The tick steps the pane and checks battery, play state and mode, the playing track, the
  position and the queue size; a change repaints. The timer stops on `EVT_WINDOW_TO_BG` and returns
  on `TO_FG`, which also re-reads the list. State is one struct in `.scratch`.

## Playback limits

The centre has no rating view (the library has no ratings). The lyrics view reads UTF-8 `.lrc`
files only (no embedded tags, no other encodings) and does not follow the playing line.

- **The wheel is silent:** `hciplayer` owns the PCM (no dmix); a second opener can race a track change, give EBUSY or power the DAC/amp.

## Limits

- No search or Folders; no clock in the title bar.
- The cover pane does not follow the row and shows only covers already in the cache.
- Long translated labels are cut with an ellipsis to the 130 px root text box.
- The play queue is the stock one: `start_player` copies the shown list, so a Songs list of
  thousands of rows is copied once per play, as the Songs page does.
