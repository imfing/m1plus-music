# Now Playing

**Sources:** `patch/nowplaying.c`, `tools/mod_nowplaying.py`, `patch/common.c`.
The stock `playing_page` gets cover-coloured backgrounds, rounded artwork, elapsed/remaining time
and reformatted track information. Playback, the slider and stock lyric loading stay stock.
[Lyrics](lyrics.md), [Queue](queue.md), [More](playmore.md) and [podcasts](podcasts.md) have their
own docs.

## Hook and lifecycle

The init hook calls `playing_page_init` through its trampoline and returns the stock result. After
a successful init with a window, `np_start` attaches page listeners and a repeating timer: 500 ms
lit, 1000 ms dark. A refused timer or listener leaves stock behaviour. Every tick also notes the
seconds heard for [scrobbling](scrobble.md).

- A replacement page stops the previous timer.
- Destroy acts only on the current window: it restores the status bar, removes timers and clears
  state. Stale callbacks end without touching widgets.
- A covered normal page skips cover, time and info work. A dialog can leave the page partly
  visible, so its data keeps updating beneath it.
- While the screen is off (`bp_light_off` -> `np_on_dark`, with `np_tick` as fallback), stock's
  500 ms timer (`player_timer_clear`) and the title/artist marquee timers (`hscroll_label_stop` on
  `scrlabel_title` / `scrlabel_artist`) are paused even when Now Playing is covered. On wake
  (`bp_light_on` -> `np_on_wake`), `player_timer_start` and `hscroll_label_start` always resume
  synchronously (preserving stock's lit behaviour such as its stream disconnect check), and
  `show_player_face(win, 0)` plus our lit refresh run before the backlight turns on when the page
  is visible.

## Layout and assets

The window is 320 x 450 px. `tools/mod_nowplaying.py` defines widget geometry and page styles;
`tools/mod_icons.py` supplies the transport, mode, queue and favourite glyphs. The 264 px cover
has 12 px corners. Existing widget names are kept.

- Art page: `np_tint.png`, a black gradient with alpha 38..235 over the window tone.
- Info page: `np_scrim.png`, 320 x 364 at y 8, alpha 128 in the centre, 36-row linear edges.
- Lyrics page: `np_scrim_lyrics.png`, 320 x 378 at y 0, alpha 68, 42-row smoothstep edges.
- Notes page: `img_np_scrim_notes` (the info scrim again) and `np_n_scroll` in `view_lyrics`, both hidden and
  insensitive in the asset, so without the payload the page is the lyrics page.
- Decorative images and time labels are insensitive.
- `label_index` (stock's `%d/%d` queue position) sits centred between the two 72 px time labels, 14 px grey,
  invisible and insensitive; only the payload shows it, see "Track position".
- Mode and queue glyphs are `#C8C8C8` (repeat-off `#6E6E6E`).
- The stock `slider_play` keeps its 30 px seek target and 6 px track (30% white track,
  `#FFFFFFEB` fill, radius 4). From a touch on it to the touch's end (release, abort, or another
  window coming over) `np_on_scrub` makes it `NP_BAR_SCRUB` (12 px, radius 7) thick, centred, as
  Apple Music's scrubber does. It eases there and back over `NP_SCRUB_MS` (250 ms, ease-in-out cubic,
  a frame every `NP_FRAME_MS`); another window coming over sets the thin bar at once. It listens to the slider's own `EVT_POINTER_DOWN_BEFORE`,
  `EVT_POINTER_UP_BEFORE` and `EVT_POINTER_ABORT`; only `bar_size` and `round_radius` change, the
  drag and the seek stay stock's.
- While the finger is on the bar the times follow it: the slider's `EVT_VALUE_CHANGING` (stock's
  handler, bound first, has set the value and stopped stock's timer) calls `np_time`, which takes
  the position from the slider's `value` scaled from its `max` (stock sets the length there) to
  the player's length (`np_scrub_pos`). The release gives the times back to the player.
- The mode button keeps its four steps and looks; the shown mode follows the Shuffle flag, see
  [shuffle](shuffle.md). While an episode or an audiobook part plays it is the speed button, see
  "Spoken audio controls".
- The star and More buttons are children of the art page (slide page 1), as the title and artist
  are, so a swipe takes them away with the cover.
- Favourite is a filled or outline star. While a podcast plays it is a saved/unsaved bookmark.
  While a server track plays it is the server's favourite ([subsonic](subsonic.md)); stock's
  `manage_myfav` never writes the stream record.

## Paused cover

Settings > Now Playing > Shrink on Pause (`nowplaying-shrink`, `0` off, default on; read when the page
starts and each time it returns to the front, the cover then put at its size at once). Off, the cover stays
264 px in every status and nothing below runs.

With it on, while paused or stopped (`mclGetPlayStatus()` 3 or 1; Wi-Fi Transfer stops the player) the cover is 212 px (0.80), centred on the
full cover; `img_np_shadow` (drawn `scale`) and the corner radius (12 → 10 px) scale with it, and the
shadow fades with the size to opacity 128. Playing
and every other status keep 264 px.

- Motion: `np_art_size` steps a spring by elapsed time on a 16 ms frame timer: critically damped for 280 ms
  to the small size, underdamped (zeta 0.75) for 460 ms back, 2 px past 264 before it lands. A change
  mid-spring turns it round from the current size. Every size is an even number of px from the target,
  so the cover stays centred and the bounce shows 1 px on each side.
- The cover springs only while the art page shows, lit and in front. Otherwise (opened while paused,
  screen dark, another page or the lyrics or info page in front, no timer) it is put at its size at once;
  a running spring that stops being seen lands on its next frame or tick.
- Triggers: the page tick, and a tap on `btn_play`. Our click handler runs before stock's, so it checks
  the status every 50 ms, up to 10 times, until it changes. Keys and the end of the queue wait for the tick.
- Each frame invalidates the shadow's old and new rectangles and moves and resizes the two widgets; stock
  `scale_auto` draws the art at the new size. A server or book cover of ours is drawn into the same box.
- Radio Now Playing, the Pod theme, Vinyl and the big cover page are unchanged.

## Track position

Settings > Now Playing > Track Position (`nowplaying-position`, `1` on, default off; read when the page starts and
each time it returns to the front). Stock writes `label_index` only on a track change; with the setting on, every
tick (`np_index`) writes `%d/%d` from `mclGetPlayPos() + 1` and the play queue size, only when the text changed,
so Play Next, Add to Queue and Clear show at once. The label is hidden when the setting is off, the queue holds
fewer than two tracks, or the position is outside it. A page without `label_index` is left alone.

**Page dots.** `slide_indicator` (`DOTS`, 4 px dots) sits in the same place, centred on the times' digits. With the
middle free the dots show. While the position shows, `np_dots_sync` (each tick, after `np_index`) keeps the dots at
opacity 0 and the label at 255. A page change (the slide view's `EVT_VALUE_CHANGED`, `np_dots_flash`) brings the dots
in over `NP_DOTS_FADE_MS` (200), holds them until `NP_DOTS_MS` (1500) after the change, and fades them out again;
`label_index` always has 255 minus the dots' opacity (`np_dots_set`). A change during a fade restarts from the
opacity it has. The frame timer (`np_dots_frame`, every `NP_FRAME_MS`) ends when the dots are out, or at once when
the position goes away (the dots then stay). Without a frame timer the position keeps the middle. A page without
`slide_indicator` leaves `label_index` alone. Without the payload the dots always show and `label_index` is hidden.

## Spoken audio controls

While an episode or an audiobook part plays (`pc_spoken_path`), the button row is a podcast
player's: speed, back 15 s, play, forward 30 s, queue. The widgets keep their names, slots and
stock handlers; music keeps stock's buttons.

**Speed** (`btn_playmode`):

- `np_mode_sync` (each tick, and after `stock_np_mode_button` when the page returns to the front)
  puts the page theme's `btn_imgspeed<n>_style` on the button for stock's `playspeed_mode` n
  (0..3: 1×, 1.25×, 1.5×, 2×; out of range reads as 0). The styles copy `btn_imgrandom_style` with
  the 52 x 30 text images `np_speed0..3` (`speed_mask` in `tools/mod_icons.py`). Stock sets the
  button's style itself, so the tick compares the name. Back on music, `stock_np_mode_button`
  restores the play mode's picture once.
- `np_on_mode`, bound after the stock init, saves the show's or the book's next speed
  (`pc_speed_set`, key `pc_show_of` / `bk_book_of`) and applies it (`pc_speed_apply`). The decoder
  takes a speed only when it starts, so a playing or paused player is restarted at its place as
  stock's Multiple Speed handlers do: `save_stop_player`, then `save_start_player(1)` when it was
  paused, else `(0)`. A refused save toasts "Storage unavailable" and changes nothing. `RET_STOP`
  keeps stock's play mode handler away, so an episode queue or a book never gets Shuffle or Repeat
  one from this button.

**Queue** (`btn_queue`): `np_skip_sync` sets the plain list `np_playlist` (Lucide `list`) in place
of `np_playqueue`; the tap is unchanged.

**Pages:** spoken audio swipes like music: the slide view and `slide_indicator` are never touched.
Page 2 is the lyrics slot, which shows the [episode notes page](#episode-notes-page) instead of lyrics;
page 3 is the [information page](#information-page), which differs for spoken audio (below).

**Skip** (`btn_prev`, `btn_next`): back `NP_SKIP_BACK` (15) and forward `NP_SKIP_FWD` (30) seconds.

- `np_skip_sync` (each tick) sets the five states' `bg_image` to `np_back15` / `np_fwd30` (pressed:
  `_down`), and back to `np_prev` / `np_next` for music. The glyphs are `skip_mask` in
  `tools/mod_icons.py`: an open ring, an arrowhead and the seconds in the tile font.
- `np_on_skip` is bound to both buttons after the stock init, so it runs before stock's click
  handler. While the skip glyphs show it seeks with stock's `seek_time` and returns `RET_STOP`;
  otherwise `RET_OK` leaves the tap to stock.
- Back stops at 0. Forward lands at most `NP_SKIP_END` (5) seconds before the end and does nothing
  inside them, so a track ends by playing. No time or length from the player: no seek.
- `seek_time` resumes a paused player and waits up to 2 s for the position, as the slider does.
- The hardware keys, the mini player, the lock screen and the other display modes still change
  track.

## Cover tone and corners

Stock's `parseplaycover_thd` writes `/tmp/coverpic.jpg` or `/tmp/externpic.jpg`. A playing
Navidrome track has no such file, so its cached server cover is drawn over `img_playcover`, see
[subsonic](subsonic.md). The previous server cover stays (never stock's placeholder) until the new
one is decoded, and the decode is never in paint: a 30 ms one-shot starts it on a new record. A
track with no cover file yet keeps the previous cover for `NP_SB_WAIT` (10) ticks, then stock's
picture shows. While a server track plays, `np_prefetch` asks for the next queue record's cover
once. A local track draws nothing of ours, except an audiobook part stock has no picture of (`COVER_SRC` not
busy, not 2, 3 or 5): `np_cover_file` then answers the book's cover (`np_book_cover`: `bk_art_cover`, asked once per
track path, so one folder read per track change; `np_cover_file` forgets the answer whenever the playing track
is not the one it is for, whatever the stock source, and while stock is busy, so an art cache file built
meanwhile shows when the part plays again), the
tone comes from it, and `np_server_art` decodes it into the same bitmap (`sbbook`), drawn over stock's placeholder.
A part with a picture of its own keeps stock's. The mini player bar, the Pod theme, Vinyl and the
[big cover page](bigcover.md) read `np_cover_file`, so they show the book cover too (the bar and Pod cover first
use the album's cache file when one exists). `COVER_SRC` is 1 while busy, 2 for embedded art, 3 for folder art, 5
for cached art. The payload reads files only in the ready states and never waits on the extraction
mutex. Unreadable or empty files are retried; a rejected decode is retried only after the file
changes.

A cheap signature of source, file length and track path avoids rereading unchanged art. Changed
art first checks the shared album-tone cache, then decodes the 168 px cover cache, falling back to
the playing cover file. The full file key hashes at most 512 KiB plus length. A same-length
replacement under the same track and source can go unnoticed until the track changes.

`m1_tone` maps the maximum channel value to 32..192 and keeps 23/25 of saturation; black uses
`#202020`. `m1_tone_get/put` caches 64 album tones in RAM, shared with the
[album page](album-page.md). A failed style update keeps the previous colour.

`img_playcover`'s own `EVT_AFTER_PAINT` blends a precomputed 12 x 12 corner mask against the
gradient at that row. Only cover repaints run it. There is no global paint hook; without the
payload the cover is square.

## Status bar

`m1_bar_tint` and `m1_bar_black` in `patch/common.c` share one owner between Now Playing and the
album page. Only the owning window can restore black. The bar uses the page's top-row tone,
darkened until white text keeps at least 4.5:1 contrast. It is found by the `system_bar` type; no
widget pointer is cached.

Background and foreground listeners restore black or apply the tint. A top-window check in the
timer covers missed events. Foreground work refreshes page data before retinting. Missing bars,
failed style calls or refused listeners leave the bar untouched.

## Information page

Page 3 (`view_info`) is text and hairlines on the existing `np_scrim`. Everything but the scrim is
inside one scroll container, `np_i_scroll` (y 36, 320 x 300), which clips it. Y values below are
at offset 0.

| part | layout |
|---|---|
| Header | cover (`mb_art_t`, 64 px, 8 px corners, at (16, 36), decoded on the tick, never in paint); title 20 px white at y 38, up to two lines 24 px apart; artist and album 16 px `#AAAAAA` below it. Text is `REC_TITLE` (else file name), `REC_ARTIST`, `REC_ALBUM`, cut below 200 bytes, x 92, 212 px wide. For a podcast episode the third line is its date and length ("Nov 18 · 52m", `pc_when` and `pc_len_text`, the length left out when unknown) instead of the album, which is the show again; a book part keeps its album. The episode's entry comes from `pc_ep_of`, once per track change, and is kept in `np.ep` |
| Badge | `HI-RES` or `DSD` (not translated): gold `#E3C16F` 1 px outline picture, 8 px left of the Format value, never tinted by the accent |
| Rows | hairline above each row, rows 33 px apart from y 112: Format, Sample Rate, Bit Depth, Bitrate, Genre, Year, File Size, Location. Label 16 px `#AAAAAA` at x 16, value 16 px white right-aligned to 304. A row with no value (empty, or zero for rate, bit depth and bitrate) is left out and the rows below move up. Spoken audio (episode or book part) leaves out Genre and Year, and stock's labels of them are hidden |
| Location | label on its own line, the path below it wrapped to up to two 288 px lines; only the last 200 bytes are shown |

- **Bare page.** While the notes page shows (spoken audio, `np.nok`), this page has no header
  (`np_bare`, `np_ihead_vis`): the notes page already shows the same one. The header's widgets are
  hidden, the rows start at `NPI_BARE_Y` (30, the first label's text at the notes title's y 38),
  and the first row shown has no hairline. The five rows and a two-line path end at y 267, inside
  the 300 px view, so the page does not scroll. The header's text is still written. Model:
  `flow(..., bare=True)`; preview `page=2,notes=NAME`.
- **Title.** One line when it fits; otherwise it breaks at the last space that fits 212 px, even
  when line 2 then ends in an ellipsis. Only with no such space (CJK, a first word wider than the
  line) does it break at the last character that fits. With a two-line title the artist and album
  and everything below move 24 px down.
- **Plain labels.** Every text of ours on this page is a plain `label`, and `m1_fit` cuts a long
  title line 2, artist, album or value to its room with `...` after it. Stock's `hscroll_label`
  clips to its resting screen position (`widget_to_screen` in its paint, `0x609e54`), not to the
  canvas offset, so its text was cut off while the `slide_view` dragged the page sideways.
- **Badge rule** is the cassette theme's `tape_badge` (`patch/tape.c`, one `mclGetInfo`): lossless
  and (over 48 kHz, or 24 bit from 44.1 kHz) is HI-RES, 1 bit is DSD, nothing for CD quality or
  lossy. DSD files are also recognised by extension when the player has no stream yet.
- Format, Sample Rate, Bit Depth and Bitrate are read from stock's quality line (`label_info`).
- While the player converts the track to the rate its output is kept at (Crossfade,
  [crossfade](crossfade.md) `xfade_out_rate`, one read of a tmpfs file per tick), the Sample Rate
  value is `44.1 → 96 kHz`. A label that leaves no room for both rates (French, Polish) gets
  `→ 96 kHz` (`np_resampled`, `np_set_row`'s `alt`; model `mod_nowplaying.resampled`).
  Genre, Year and File Size are our keys; Location is stock's word in the app language.
- Stock's `label_*` widgets stay as the data source, never rewritten, and are hidden once ours
  show.
- The tick (`np_info`) lays a part out when its stock text or the track changed (`mb_track_key`).
  Header labels are shown after the page opens, and for `NP_RELAY` (3) ticks after it starts or
  returns, because a label measures in its own style only once the window is open.
- While the playing record is a server stream (`REC_ID <= -2`), `np_stream_text` writes the size
  and location lines itself, since stock's come from the stream address (with token and salt).
  Size is `N.NN MB` from the server size in the queue map, else "Unknown". Location is the saved
  server's scheme and host[:port] ([subsonic](subsonic.md)). A downloaded track keeps stock's lines.
- Fallback is per part: a part whose widgets the asset lacks, or whose stock text is unreadable,
  shows stock's label again. The next good text takes it back.
- **Scrolling.** `np_info_scroll(off)` is the one place that moves the content, clamped to
  `0..ih-300`. A vertical drag of 10 px or more moves the content with the finger; no overscroll
  and no fling. A swipe that goes sideways first still turns the page, and a tap does nothing.
  Once the drag is vertical its MOVEs return `RET_STOP`, so the slide view is aborted and a
  sideways drift turns no page (the direction lock in [lyrics](lyrics.md)). Only the container
  takes touches; the stock fallback labels do not move.
- **Reset.** The content goes back to the top when the page is entered, when Now Playing comes to
  the front, and on a track change. A content that got shorter pulls the offset back.
- **Edge fades.** The top and bottom 16 rows of the scroll area fade into the scrim, painted over
  the content in the colour behind it, and only where content lies beyond that edge. No decode;
  at most 32 one-row fills per paint.

## Episode notes page

While spoken audio plays (`np.spoken`: a podcast episode or a book part) the lyrics slot (page 2) shows
an episode notes page; music keeps the lyrics page. It is the information page's look: the same
`np_scrim` (`img_np_scrim_notes`), the same header, one hairline, then the notes, all inside one
clipping scroll container `np_n_scroll` (y 36, 320 x 300). The asset has them hidden, and hidden
widgets are insensitive; only the container is made sensitive while the page shows. A page with
any of the widgets missing (`np.nok` is 0) keeps the lyrics page, and the information page keeps
its header; otherwise the information page is bare. Model: `notes_layout` in
`tools/mod_nowplaying.py`; the preview (`page=1,notes=feed|short|local`) draws it.

| part | layout |
|---|---|
| Header | as the information page's (`np_head_place`, `np_head_text` serve both): a 64 px cover from the same `np.ia` bitmap at (16, 36), the title up to two lines, line 2 the show (the artist), line 3 "date · length" ("Nov 18 · 52m"; a book part: the album). Widgets `np_n_art`, `np_n_title`, `np_n_title2`, `np_n_artist`, `np_n_album` |
| Hairline | `np_n_hair`, 288 wide at x 16, y `NPI_ROW_Y` (112) plus the title's 24 px shift |
| Notes | 16 px `#DCDCDC`, x 16, 288 wide, from `NPN_GAP` (12) under the hairline; line pitch `PD_PITCH` (22), `PD_PGAP` (10) more between paragraphs; `NPN_GAP` of air under the last line ends the content |
| Hint | no notes and no description (a book part, a local file with no entry): one grey line, the episode page's "No description", in `np_n_hint` where the notes would start |

- **Text.** `np_ep_load` runs once per track change (the key `np.epkey`; the relay ticks never reread):
  `pc_ep_of` for the entry, then `pno_read` of the guid's line in the show folder's `.notes`
  (`PF_NOTE` + 1 bytes, `'\n'` between paragraphs), else the entry's `desc`. The text (`np.ntext`) and
  the layout (`np.npd`, a `pd_t`) are heap blocks that live while spoken audio plays and are freed on a
  switch to music and at stop; a refused allocation shows the hint.
- **Layout.** `np_notes_layout` (track change, relay ticks; never per tick) wraps with
  `pd_paras` (`patch/pcdetail.c`, the episode page's paragraph wrapper over `pw_wrap`: the font's own
  advances, kinsoku, CJK anywhere) using `np_n_body`'s style, and sets the container's `virtual_h`.
  Each layout clears `pd_t`'s advance cache first: it is keyed by the label, and the label's style
  may resolve after the first layout (the relay ticks exist for that).
- **Paint.** `np_n_body` is one label of the container's size whose `EVT_AFTER_PAINT` draws the lines
  (`np_on_notes_paint`): only lines wholly inside the view, as the episode page does (AWTK does not
  clip a text), each in a 20 px rect so the text top is the line's y. No file is read or decoded there.
- **Scrolling** is the information page's: one `np_on_info_touch` and `np_on_info_fade` serve both
  containers (`np_scr_t`, found from the listener's widget), with the same drag threshold, direction
  lock, no fling and edge fades. `np_notes_scroll(off)` moves the header, hairline and hint and
  repaints the body. The offset resets on a page change away from page 1, when Now Playing comes
  to the front, and on a track change.
- **Lyrics.** `np_notes_sync` (each tick) shows the page and calls `ly_standdown(1)` while spoken
  audio plays, and the reverse for music ([lyrics](lyrics.md) "Second view").

## Pins and safety

`tools/pod.py` pins the init hook, called functions and `COVER_SRC`. The A-B marker geometry is a
separate pinned asset patch (`mod_nowplaying.patch_markers`) with prologue and call-site checks;
the affected functions are outside the boot path.

Runtime work is page-scoped, with no new thread or lock. Widgets and styles use stock setters, and
fallbacks keep stock behaviour. Only the cover widget has paint-time payload work.
