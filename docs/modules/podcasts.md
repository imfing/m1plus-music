# Podcasts

Local episodes, subscriptions, downloads, Apple Podcasts directory search, episode notes
and Saved episodes share `ui/m1plus_podcasts.bin`. Podcast Search is enabled in Settings.
The iPod interface also exposes Podcasts.

## Sources

| Area | Files |
|---|---|
| Model, resume, speed, library filter | `patch/pcmodel.c`, `patch/podcasts.h` |
| Page, sheets, refresh dialog | `patch/podcasts.c`, `tools/pod_ui.py` |
| Network worker | `patch/pcnet.c`, `patch/curlopts.h` |
| Feed / JSON parsing | `patch/pcfeed.c`, `patch/pcjson.c` |
| Covers | `patch/pccover.c`, `patch/pcpng.c` |
| Episode details / notes | `patch/pcdetail.c`, `patch/pcnotes.c`, `patch/pcwrap.c` |
| Shared layout model | `tools/pod_show.py` |
| Tests | `test/pod/podcasts.py` and feature-specific `test/pod/pc*.py` |

The download policy follows q2-podcasts (MIT,
github.com/m-d-e-v/q2-podcasts, `internal/library/download.go` and
`contrib/shanlingq2/README`); the implementation uses demo's libcurl.

## Pages and controls

Shows contains Continue Listening, a show grid and Downloads/Subscriptions rows (text ends at x 278, the shared list chevron `pod_make_chevron` at x 288, hairline to 310; the episode page's show row likewise).
The Shows, Downloads, Subscriptions and Saved levels open on the large title (`pg_big`, x `SG_TITLE_X` 12, `SG_TITLE_W` wide, 32 px, cut with an ellipsis); the navbar's small title (the same words, `label_title`) shows once the offset reaches `SG_COLLAPSE` (`pod_title_gone`, `pg_collapse`), as on every large-title page ([navbar](navbar.md) "Small titles"). Its width runs from x 58 to the leftmost visible button (`pg_nav`): the globe, else the "...", else Now Playing. The refresh line, section headers and rows keep their own x (14-16).
Shows sort by newest remote or local episode date. The show page has artwork, metadata,
Latest Episode and all known episodes, newest first. A body tap opens episode details;
the pill plays, downloads, pauses, resumes or retries according to state.

Episode details include the long description and the same playback/download actions.
Show and episode sheets provide refresh, unsubscribe, played marks and download removal.
Selection supports bulk deletion; the currently playing file is retained.
Deleting an episode clears its saved resume/played state. Unsubscribing preserves local files.

Search accepts directory terms, feed URLs and Apple Podcasts links. Results open a preview (rows of the shared list painter: the hairline from the text to x 310 and the list chevron at x 288, on a result that has a feed only: a dimmed Not available row opens nothing, so it has no chevron and its text runs to x 308 (`grid_tile_t.nochev`));
Subscribe creates a show folder and its metadata. Search previews do not play remote episodes.
Subscriptions supports card import/export, including OPML. The import also accepts
`Podcasts/subscriptions.txt`: one HTTP(S) feed URL per line, with `#` comments.

Saved episodes use stock `myfav` records. The Now Playing favorite control becomes a
bookmark for podcast paths. Its More sheet can return to the playing show's Podcasts page.
There is no separate Saved database.

## Files and model

Shows live under `/mnt/mmc/Podcasts/<Show>/`. Root matching is case-insensitive.
Supported file extensions are mp3, m4a, m4b, aac, ogg, opus, flac, wav and wma.
A show can supply `cover.jpg/png/jpeg` or `folder.*`.

| File | Contract |
|---|---|
| `.show` | UTF-8 `M1PLUS-SHOW 1`; key=value lines for title, feed, image, checked, modified, author, category and desc |
| `.episodes` | UTF-8 `M1PLUS-EPISODES 1`; tab-separated key=value fields: g guid, p epoch date, d duration seconds, l bytes, f filename, t title, u enclosure URL, x short description |
| `.notes` | Long descriptions keyed by episode identity; format/read/write implementation in `patch/pcnotes.c` |
| `<filename>.part` | Incomplete download; retained for resume |
| `.m1plus/podcasts/resume` | PCR1 ring: count plus 16-byte hash/position/length/flags slots, most recent first |
| `.m1plus/podcasts/speed` | PCS1: count plus show-hash/mode pairs |

Metadata permits LF or CRLF, ignores unknown fields and strips tabs/newlines from values.
The model reads at most 64 KB of `.episodes`, keeping the newest 300 entries.
Titles fit 95 bytes; local filenames must fit 127. Show feed/image URLs use `PC_URL` 320.
Short descriptions contain at most 200 UTF-8 bytes; episode notes at most 4096.

`pm_merge` combines feed entries and files into local, partial or remote episodes.
Without metadata, title comes from the filename and date from mtime.
Sort is date descending, filename descending, then entry order.
Refresh preserves old entries whose completed or partial file remains on the card.

Limits: 40 shows, 300 episodes per show, 400 examined files, 512 resume slots and
64 speed records. State writes require `pod_card_mounted` and use temporary files,
fsync and rename. An unmounted card directory must never receive persistent writes.

## Playback, resume and speed

Episodes use class-1 folder queues with copied song records; playback needs no library scan.
The tag-reader hook supplies show/episode text only for podcast paths.
Library query filtering removes podcast paths from music lists and music Favourites;
Daily Mix, Recently Played and custom Shuffle queues also exclude them.
Folders and stock history tables can still contain episodes.

`pc_note`, called by Now Playing, the mini player and the Podcasts page timer, records
positions only while those pages provide ticks. Positions from 30 seconds are saved;
within 30 seconds of the end or past 95% the episode is marked played.
Writes are limited to every 30 seconds, with immediate flushes on pause, track change,
page actions and backgrounding.

A saved position resumes once playback reaches 1..4 seconds; it is abandoned after 15 seconds
if it cannot be applied. Played episodes restart at zero.
Per-show speeds are 1×, 1.25×, 1.5× and 2×. They change RAM/player state without writing
stock PLAYSPEED configuration; music restores the previous mode. Actual application of
speed changes can depend on the stock player's next track open.

## Network and feeds

One worker handles refresh, search/subscription or downloads; it never touches widgets. The Radio directory fetch (`rd_fetch`, [radio](radio.md)) is refused while one of these runs; the reverse is not checked.
The UI reads generation/status records. Downloads pause for other network jobs and resume
afterward. The queue holds 32 entries in RAM; reboot leaves partial files paused.

Requests use the firmware CA bundle with certificate verification enabled, bounded HTTP(S)
redirects and connection/transfer guards. Missing Wi-Fi, an invalid clock or missing
certificates produce explicit errors. Feed requests have an 8 MiB cap and 120 second timeout.
Conditional requests use the server's Last-Modified time, never the device clock.
A 304 preserves episodes; a missing episodes file forces an unconditional retry.

The streaming RSS parser keeps the 20 newest enclosed items, handles arbitrary chunk splits,
entities and CDATA, and strips HTML from descriptions. Atom is unsupported.
Refresh writes episodes before show metadata and preserves local filenames.
Cover failures do not fail the feed or replace user-supplied artwork.
Large JPEG/PNG art is reduced to 192 px with bounded-memory decoders; malformed images
fail without exiting the app. Display decoding refuses images over 2.1 million pixels.

## Download safety

Downloads request the stored enclosure URL, not an expiring redirect URL.
Data is flushed in 512 KB chunks and renamed only on completion.
A partial file requests Range N-: HTTP 206 appends, 200 restarts, and 416/range errors
restart once. Content-Range offsets are not validated.

Transient failures retry after 10, 20 and 40 seconds. Certificate, storage and terminal
HTTP errors fail immediately; text responses are rejected as non-audio.
Downloads keep 32 MB free, reject bodies over 2 GiB and enforce a 240-byte path limit.
Nonempty partial files survive errors and cancellation; empty ones are removed.
There is no automatic new-episode download or persistent retry queue.

Active transfers use the stock power timer to prevent standby while allowing screen-off.
Visual work stops while dark; status and covers update on the first lit page tick.
Stock standby otherwise stops Wi-Fi and CPU execution.

## Pins and validation

`PODCAST_PINS` in `tools/pod.py` checks `seek_time` (`0x4e0544`),
`mclSetPlaySpeed` (`0x5d281c`), `playspeed_mode` (`0xa05acc`) and the
tag-reader hook. Library query hooks are documented in [payload](payload.md).
Every hook preserves stock behavior outside its matching podcast path/query.

Tests cover parsing, metadata merge, file writes, malformed input, network/queue failures,
resume, speed, layout, search, notes, selection, translations and stock tag-reader execution.
Models do not establish actual playback, Wi-Fi persistence, filesystem or frame-time results.

## Device checks

Check library exclusion and dot-folder scanning; file dates and m4b playback; queue navigation,
tag/cover display, resume across pause/reboot and music-speed restoration.
Exercise refresh/search/import with Wi-Fi loss, wrong clock, malformed feeds and screen-off.
Verify partial Range resume, servers ignoring Range, card-full/removal, queued downloads,
cancellation and reboot. Check large covers, long/CJK notes, Saved actions, currently playing
file protection, subscription removal, OPML round trips and responsive scrolling with 300 episodes.
Record results by build; these checks are not claims of completed hardware validation.
