# Album page

**Sources:** `patch/albumpage.c`, `patch/songops.c`, `patch/covercache.c`,
`tools/pod_ui.py` (`build_album_page`).
**Tests:** `test/pod/albumpage.py`, `test/pod/shared.py`.
Preview: `tools/ah_ink.py` measures header typography.

Albums, Cover Flow, Recently Played and Look up album open `m1plus_album_page`
(`ui/m1plus_album.bin`) through `cc_open_album`.
Stock Shanling library pages retain their stock album-details page.

## Opening and fallback

`album_open(class, row)` loads details for library albums (`0xff10`), artist albums
(`0xff11`) or composer albums (`0xff14`). The browsing record is snapshotted and
restored before each query/play operation.

Kill switch, an already-open page or missing window/assets falls back to
`albuminfo_page`. Cover Flow's All albums card opens the artist's Songs page;
unsupported composer/all-songs cases use the stock fallback.

The stock fallback requires `albumcoverinfo_init` followed by
`batchadd_albumcover_task(0, 0)`: initialization parks the cover worker at state 2,
and the batch call releases it to state 1 before the page queues its task.
The relevant state is `albumcover_taskstate` at `0xa05a18`.
Stock album artwork retains its 100 px size.

## Layout

A stock list fills the 320 × 450 px window. Its content view paints a 344 px header
and 64 px track rows. Glass navigation controls are direct window children above the
list so an enclosing view cannot intercept the whole navigation band.

| Element | Geometry / appearance |
|---|---|
| Navigation | Back; Select / Now Playing capsule; selection mode adds All/None, Add, Delete, Cancel |
| Cover | 160 × 160 at (80, 50), 10 px corners |
| Album | Centered 22 px white at y 224 |
| Artist | Centered 18 px grey at y 247 |
| Metadata | 15 px at y 267: year, track count and length (`1959 · 8 tracks · 47 min`); year and length only when known |
| Playback | Shuffle target 44 × 44 at x 42; Play all target 180 × 44 at x 95; y 292 |
| Tracks | Number column, 19 px title, gold playing title, 20% white press fill, 13% white hairline |

Year is the first track year in 1000..2999.
Track numbers use a wider column from 100 onward. CUE titles use the file name.

## Album length

The library stores no track lengths (`time/time_end` are CUE offsets), so the page reads each
track's header, chosen by extension (any case):

| Format | Length |
|---|---|
| `.flac` | STREAMINFO total samples / sample rate, after a leading ID3v2 tag |
| `.mp3` | First layer III frame after an ID3v2 tag (within `AB_MP3_SCAN`, 2048 bytes; the next frame header must follow where the frame's length says, when in the buffer). Xing/Info or VBRI frame count × samples per frame / rate; without one (CBR), bytes to the end less an ID3v1 tag / bitrate |
| `.m4a` | `mvhd` duration / time scale (version 0 or 1). Top-level atoms from `ftyp` are walked to `moov` wherever it is (64-bit atom sizes up to 4 GB), then `moov`'s children |
| `.wav` | `data` size / `fmt ` bytes per second; chunks in any order, odd sizes padded. A `data` size of 0 or ~0 (a stream) does not read |

Atom and chunk walks stop after `AB_ATOMS` (64). Each track is whole seconds, rounded down.
A page timer reads `AB_LEN_STEP` (4) headers per `AB_LEN_MS` (20 ms) tick, from the page's open
or reload. It stops on destroy and when another query replaced the stock list, and the reload
starts it again. The line gains ` · 47 min` (whole minutes, at least 1; `1 h 12 min`, `2 h`
from 59.5 min), with the translated keys `%d min` and `%d h`.

No length is shown, and nothing is read, when a track has another extension or is a CUE track.
A header that does not read as its format's, or a missing file, ends the job without a length
and without caching. A VBR MP3 without a Xing/Info or VBRI header reads as CBR from its first
frame's bitrate, so its length is an estimate.

`/mnt/mmc/.m1plus/album-lengths` caches results: the magic `MAL1`, then 12-byte records
`{cover key, signature, seconds}`, newest first, at most `AB_LEN_KEEP` (512). The signature is
FNV-1a over the tracks' paths, so a changed track list is read again; a file replaced under the
same path keeps its cached length. A hit shows the length on open without reading any track.
The cache is written with `pod_card_write` (only while the card is mounted); a file without
the magic is ignored and replaced.

## Artwork and shared tint

The page uses the 168 px Cover Flow cache; missing art starts one shared cache-worker
job, polled at `AB_COVER_MS`, with a placeholder until ready.
`pod_tone_get/put` supplies a 64-entry RAM-only LRU cache keyed by
`cc_album_key` (artist + album FNV-1a). Each entry holds key, tone and use stamp:
768 bytes total, no card writes.

A cache miss averages the centered cover square and applies `pod_tone`.
`ah_tint.png` overlays black alpha 64 at the top, rising to 200 at header row 343
and held below it. No art, an empty cache marker or an All albums card leaves black.
The gradient stays fixed while content scrolls.

At rest, the tested header contrast is at least 8.59:1 for the title, 4.06:1 for the
artist and 3.78:1 for metadata. Track numbers over the held tint keep 3.31:1 when pressed.
Rows passing over the brighter top of the gradient have lower transient contrast.

Status-bar tint uses the same single-owner helpers as [Now Playing](nowplaying.md#status-bar).
Background/destroy restore black only while this page owns the bar; foreground retints.
Bright tones may require a darker bar than the top window row to preserve 4.5:1 contrast.

## Playback and selection

Track taps, Play all and Shuffle use `so_play` in `patch/songops.c`.
A missing starting file shows Storage unavailable. An unresolved queue starts nothing
and changes no play mode.

Play all sets an in-order mode: Shuffle and Repeat one become List play; List play and
Repeat all are retained. Shuffle chooses a random starting track and sets the stock
Shuffle mode for this album queue. Mode changes use the stock notification/config path.
Selection shares Add/Delete operations with [Songs](songs.md).

`pod_open_player` follows the stock row handler's navigation sequence. With
`songerinfoflag` (`0xa04737`) set, it removes windows above an existing
`playing_page`, closes that page, then opens Now Playing with the new queue/context.
The pop loop is bounded at 16; a window that does not close cannot cause an infinite loop.
Library and playback windows must not have close animations that defer this stack change.

## Stock pages

Stock artist/genre/composer rows hide their placeholder icon and use the freed width;
the playing row reserves space for the wave marker. Stock playlist songs retain the
common 64 px library rows; our Playlists entry opens [Songs](songs.md).

The fallback queue drawer (`dialog/playqueue_dialog.bin`) has 44 px rows, muted 18 px
non-playing text and white 20 px playing text, plus a mode-header hairline and left border.
It has no added playing image or header count. The stock `playerjumpinfo_page` uses the
shared wave marker and a 20 px navbar title. See [Queue](queue.md) and [rows](rows.md).

## Pins and validation

`SONGS_PINS` checks `is_playing` (`0x4d9d64`) and album row-builder calls
at `0x524c40..0x524ca4`. This page adds no hook.
Tests cover layout, tint contrast, tone-cache bounds/LRU, playback mode changes, stack
navigation and failures; `len_tests` covers the length (headers, rounding, cache, the albums
without one and the line's width in all languages). Hardware appearance and input remain unverified by those models;
use [device checks](device-checks.md).
