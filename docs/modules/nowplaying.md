# Now Playing

**Sources:** `patch/nowplaying.c`, `tools/mod_nowplaying.py`, `patch/common.c`.
**Tests:** `test/pod/nowplaying.py`, `test/pod/shared.py`.
Preview: `tools/preview_nowplaying.py`.

The stock `playing_page` has cover-colored backgrounds, rounded artwork, elapsed/remaining
time and reformatted track information. Playback, the slider and stock lyric loading remain
stock services. [Lyrics](lyrics.md), [Queue](queue.md), [More](playmore.md) and
[podcast metadata](podcasts.md) have their own references.

## Hook and lifecycle

The init hook calls `playing_page_init` (`0x53d1e4`) through its trampoline and returns
the stock result. After successful initialization, with a window,
`np_start` attaches page listeners and a repeating timer: 500 ms lit, 1000 ms dark.
A refused timer or listener leaves stock behavior.

A replacement page stops the previous timer. Destroy acts only on the current window,
restores its status bar, removes timers and clears state; stale callbacks end without
touching widgets. A covered normal page skips cover, time and info work. Dialogs can leave
the page partly visible, so its data continues updating beneath them.

## Layout and assets

The window is 320 × 450 px. `tools/mod_nowplaying.py` defines widget geometry and page
styles; `tools/mod_icons.py` supplies the transport, mode, queue and favorite glyphs.
The 264 px cover has 12 px corners. Existing widget names are preserved.

The art page uses `np_tint.png`, a black gradient with alpha 38..235 over the window tone.
The info page adds `np_scrim.png`: 320 × 324 at y 8, alpha 128 in the center,
with 36-row linear edges. The lyrics page uses `np_scrim_lyrics.png`: 320 × 332 at y 0,
alpha 68 with 44-row smoothstep edges. Decorative images and time labels are insensitive.

Favorite is a filled/outline star; while a podcast plays it becomes a saved/unsaved bookmark. While a server (Subsonic) track plays, streamed or downloaded, it is the server's favourite: `np_on_fav` (bound after
stock's, so it runs first) calls `ls_favorite(&lib_nd, ...)` and returns `RET_STOP`, so stock's `manage_myfav` (`0x4ef884`) never writes the stream record into `myfav`; `np_server_fav` reads the flag through `nd_row` (cached, re-read when the
track or `sba_gen` changes) and `np_fav_sync` keeps the star's style on it ([subsonic](subsonic.md)).
Mode and queue glyphs use `#C8C8C8` (repeat-off `#6E6E6E`).
The stock mode button (`btn_playmode`) keeps its four steps and looks. Its picture (`0x539888`) and click handler (`0x53b5fc`) read the *shown* mode,
which is Shuffle while the payload's Shuffle flag is on (also with Repeat all, set from the Queue page): the Shuffle step turns the flag on (stock mode 0),
the next step (Repeat all) turns it off. Two call sites and the mode hook make this ([shuffle](shuffle.md) "Where the mode is shown"); the page itself is unchanged.
The stock `slider_play` retains a 30 px seek target with a 6 px track, 30% white track,
`#FFFFFFEB` fill and radius 4.

## Cover tone and corners

Stock's `parseplaycover_thd` writes `/tmp/coverpic.jpg` or `/tmp/externpic.jpg`.
A playing Navidrome track has no such file: `np_server_art` draws its cached cover (`sba_now_cover`, docs/modules/subsonic.md) over `img_playcover` from `np_on_art_paint`, before the corners; local tracks keep stock's picture.
On a track change the previous server cover stays drawn (never stock's placeholder) until the new one is decoded: while a server track (`REC_ID <= -2`) plays, `np_on_art_paint` draws `sbmp`,
and when it sees a `REC_ID` that `np_server_art` has not looked at it starts a 30 ms one-shot (`np_art_once`, ctx 0; the decode is never in the paint). A track with no cover file yet (or none at all) keeps the previous cover
for `NP_SB_WAIT` (10) ticks, then stock's picture shows. Two tracks with the same cover file only change `sbrec`. A local track draws nothing of ours at once. While a server track plays,
`np_prefetch` asks `sba_now_cover` for the queue record after the playing one (`PLAY_QUEUE` at `mclGetPlayPos()+1`), once per such record.
`COVER_SRC` (`0x97cad8`) is 1 while busy, 2 for embedded art, 3 for folder art,
or 5 for cached art. The payload reads files only in the ready states and never waits on
the extraction mutex. Unreadable or empty files are retried; a rejected decode is retried
only after the file changes.

A cheap signature of source, file length and track path avoids rereading unchanged art.
Changed art first checks the shared album-tone cache, then decodes the 168 px cover cache,
falling back to the playing cover file. The full file key hashes at most 512 KiB plus length.
A same-length replacement under the same track/source without an observed busy state can
remain undetected until the track changes.

`pod_tone` maps maximum channel value to 32..192 and retains 23/25 of saturation;
black uses `#202020`. `pod_tone_get/put` caches 64 album tones in RAM, shared with
the [album page](album-page.md). A failed style update preserves the previous color.

`img_playcover`'s own `EVT_AFTER_PAINT` blends a precomputed 12 × 12 corner mask
against the gradient at that row. Only cover repaints run it. There is no global paint hook;
without the payload the cover is square.

## Status bar

`pod_bar_tint` and `pod_bar_black` in `patch/common.c` share one owner between
Now Playing and the album page. Only the owning window can restore black.
The bar uses the page's top-row tone, darkened until white text keeps at least 4.5:1 contrast.
It is found by the `system_bar` type; no widget pointer is cached.

Background/foreground listeners restore black or apply the tint. A top-window check in
the timer covers missed events. Foreground work refreshes page data before retinting.
Missing bars, failed style calls or refused lifecycle listeners leave the bar untouched.
Real status-bar appearance remains a device-validation concern.

## Time and information

`get_playtimeandlength` (`0x4e015c`) supplies seconds.
`np_elapsed` shows `m:ss` or `h:mm:ss`; `np_remaining` shows the negative
remaining value, clamped at zero. They replace the visibility of stock time labels rather
than competing with stock text writes. Invalid lengths restore stock labels.
Missing time widgets disable that portion without disabling tint.

The page tick reads the stock info labels and rewrites changed, complete strings only.
It spaces colons and units and translates Genre/Year.
While the playing record is a server stream (`REC_ID <= -2`, mapped by `sba_rec_track`, and `REC_PATH` an `http` address) `np_stream_text` writes the size and location lines itself, since stock's come from the
stream address (token and salt included) and a file that does not exist: stock's label, then `N.NN MB` from the server size kept in the queue map (`sba_rec_size`; "Unknown" when none) or the saved server's scheme and
host[:port] (`sba_url`, user info, path and query dropped; "Unknown" with no server). A downloaded track plays from its own path and keeps stock's lines. The same `np.done` hashes keep it from looping. Failed reads, truncation or output
overflow leave stock text. Stock text can appear for up to one 500 ms tick after a track change.

The quality line differs: stock rewrites `label_info` with the compact text on every tick, so
rewriting it would alternate two widths in a centred label. The asset adds `np_quality`
(same rectangle, size 18, centred, hidden, insensitive). The tick reads `label_info`, formats
it (spaced separators when the result fits), writes `np_quality` only when that text changes,
and then shows it while `label_info` is hidden and made insensitive. Stock keeps writing
`label_info`, the data source. A page without `np_quality` leaves `label_info` visible and
untouched. A failed read or write, or a text too long to read whole, hides `np_quality` and
shows `label_info` again (so a stale line never stays up); the next good text takes it back.

## Pins, safety and validation

`tools/pod.py` pins the init hook, called functions and `COVER_SRC`.
Important calls include `widget_set_style` (`0x66c448`),
`value_set_uint32` (`0x711858`) and `get_playtimeandlength` (`0x4e015c`).

A-B marker geometry is a separate pinned asset patch: `mod_nowplaying.patch_markers`
changes width/offset at `0x53b8d4` / `0x53b8ec` and y at
`0x53b9c4`, `0x53ba48`, `0x53ba64`, with prologue/call-site checks.
The affected functions are outside the boot path.

Runtime work is page-scoped, with no new thread or lock. Widgets/styles use stock setters;
fallbacks preserve stock behavior. Only the cover widget has paint-time payload work.
Tests check lifecycle, tone/corner models, cover caching, time formatting, translated info,
contrast and stock hit targets. Real repaint behavior, slider rounding, corner blending,
intro dots and frame timing require [device checks](device-checks.md).
