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

## Layout and assets

The window is 320 x 450 px. `tools/mod_nowplaying.py` defines widget geometry and page styles;
`tools/mod_icons.py` supplies the transport, mode, queue and favourite glyphs. The 264 px cover
has 12 px corners. Existing widget names are kept.

- Art page: `np_tint.png`, a black gradient with alpha 38..235 over the window tone.
- Info page: `np_scrim.png`, 320 x 324 at y 8, alpha 128 in the centre, 36-row linear edges.
- Lyrics page: `np_scrim_lyrics.png`, 320 x 332 at y 0, alpha 68, 44-row smoothstep edges.
- Decorative images and time labels are insensitive.
- `label_index` (stock's `%d/%d` queue position) sits centred between the two 72 px time labels, 14 px grey,
  invisible and insensitive; only the payload shows it, see "Track position".
- Mode and queue glyphs are `#C8C8C8` (repeat-off `#6E6E6E`).
- The stock `slider_play` keeps its 30 px seek target and 6 px track (30% white track,
  `#FFFFFFEB` fill, radius 4).
- The mode button keeps its four steps and looks; the shown mode follows the Shuffle flag, see
  [shuffle](shuffle.md). While an episode or an audiobook part plays it is the speed button, see
  "Spoken audio controls".
- Favourite is a filled or outline star. While a podcast plays it is a saved/unsaved bookmark.
  While a server track plays it is the server's favourite ([subsonic](subsonic.md)); stock's
  `manage_myfav` never writes the stream record.

## Paused cover

While paused or stopped (`mclGetPlayStatus()` 3 or 1; Wi-Fi Transfer stops the player) the cover is 194 px (0.73, Apple Music's ratio), centred on the
full cover; `img_np_shadow` (drawn `scale`) and the corner radius (12 → 9 px) scale with it, and the
shadow fades with the size to opacity 64. Playing
and every other status keep 264 px.

- Motion: `np_art_size` steps a spring by elapsed time on a 16 ms frame timer: critically damped for 400 ms
  to the small size, underdamped (zeta 0.75) for 640 ms back, 2 px past 264 before it lands. A change
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

**Pages:** `np_pages_sync` keeps the cover page alone, since an episode or a part has no lyrics.
Every tick of spoken audio sets `slide_view`'s `value` to 0 when another page shows. Once the
cover page is confirmed, the slide view is made insensitive (no swipe; the controls are not its
children) and `slide_indicator` is hidden. A slide view that refuses the turn while it animates is
left unlocked and asked again at the next tick; a page reached after the lock is turned back the
same way. Music makes both live again; the page is not turned back.

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
inside one scroll container, `np_i_scroll` (y 36, 320 x 252), which clips it. Y values below are
at offset 0.

| part | layout |
|---|---|
| Header | cover (`mb_art_t`, 64 px, 8 px corners, at (16, 36), decoded on the tick, never in paint); title 20 px white at y 38, up to two lines 24 px apart; artist and album 16 px `#AAAAAA` below it. Text is `REC_TITLE` (else file name), `REC_ARTIST`, `REC_ALBUM`, cut below 200 bytes, x 92, 212 px wide |
| Badge | `HI-RES` or `DSD` (not translated): gold `#E3C16F` 1 px outline picture, 8 px left of the Format value, never tinted by the accent |
| Rows | hairline above each row, rows 33 px apart from y 112: Format, Sample Rate, Bit Depth, Bitrate, Genre, Year, File Size, Location. Label 16 px `#AAAAAA` at x 16, value 16 px white right-aligned to 304. A row with no value (empty, or zero for rate, bit depth and bitrate) is left out and the rows below move up |
| Location | label on its own line, the path below it wrapped to up to two 288 px lines; only the last 200 bytes are shown |

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
  `0..ih-252`. A vertical drag of 10 px or more moves the content with the finger; no overscroll
  and no fling. A swipe that goes sideways first still turns the page, and a tap does nothing.
  Once the drag is vertical its MOVEs return `RET_STOP`, so the slide view is aborted and a
  sideways drift turns no page (the direction lock in [lyrics](lyrics.md)). Only the container
  takes touches; the stock fallback labels do not move.
- **Reset.** The content goes back to the top when the page is entered, when Now Playing comes to
  the front, and on a track change. A content that got shorter pulls the offset back.
- **Edge fades.** The top and bottom 16 rows of the scroll area fade into the scrim, painted over
  the content in the colour behind it, and only where content lies beyond that edge. No decode;
  at most 32 one-row fills per paint.

## Pins and safety

`tools/pod.py` pins the init hook, called functions and `COVER_SRC`. The A-B marker geometry is a
separate pinned asset patch (`mod_nowplaying.patch_markers`) with prologue and call-site checks;
the affected functions are outside the boot path.

Runtime work is page-scoped, with no new thread or lock. Widgets and styles use stock setters, and
fallbacks keep stock behaviour. Only the cover widget has paint-time payload work.
