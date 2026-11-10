# Podcasts

Local episodes, subscriptions, downloads, Apple Podcasts directory search, episode notes
and Saved episodes share `ui/m1plus_podcasts.bin`. Discover and the search level are there while **Podcast Discover** is on in Settings (the default; `pcsearch_setting`); the Apple storefront they ask is the Podcast Region (a Settings picker, Automatic by default).
The iPod interface also exposes Podcasts.

## Sources

| Area | Files |
|---|---|
| Model, resume, speed, episode order, library filter | `patch/pcmodel.c`, `patch/podcasts.h` |
| Page, sheets, refresh dialog | `patch/podcasts.c`, `tools/pod_ui.py` |
| Network worker | `patch/pcnet.c`, `patch/curlopts.h` |
| Region | `patch/pcregion.c`, `tools/pcregion.py` |
| Segmented control | `pod_segmented`, `pod_capsule` in `patch/common.c`; model `pod_show.segmented`, `pod_show.capsule` |
| Feed / JSON parsing | `patch/pcfeed.c`, `patch/pcjson.c` |
| Covers | `patch/pccover.c`, `patch/pcpng.c` |
| Episode details / notes | `patch/pcdetail.c`, `patch/pcnotes.c`, `patch/pcwrap.c` |
| Shared layout model | `tools/pod_show.py` |
| Tests | `test/pod/podcasts.py` and feature-specific `test/pod/pc*.py` (`pcdiscover.py`, `pcregion.py`, `pcsearchui.py`) |

The download policy follows q2-podcasts (MIT,
github.com/m-d-e-v/q2-podcasts, `internal/library/download.go` and
`contrib/shanlingq2/README`); the implementation uses demo's libcurl.

## Pages and controls

Shows contains Continue Listening, a show grid and Discover/Downloads/Subscriptions/Saved rows, in that order (Discover, tile `pod_ic_discovertile` (Lucide `compass`) with Apple Podcasts in grey, there while Podcast Discover is on (otherwise the Library rows close up: Downloads first); it opens the Discover level; text ends at x 278, the shared list chevron `pod_make_chevron` at x 288, hairline to 310; the episode page's show row likewise).
The Shows, Discover, Downloads, Subscriptions and Saved levels open on the large title (`pg_big`, x `SG_TITLE_X` 12, `SG_TITLE_W` wide, 32 px, cut with an ellipsis); the navbar's small title (the same words, `label_title`) shows once the offset reaches `SG_COLLAPSE` (`pod_title_gone`, `pg_collapse`), as on every large-title page ([navbar](navbar.md) "Small titles"). Its width runs from x 58 to the leftmost visible button (`pg_nav`): the globe (Shows level, while Podcast Discover is on), the Discover level's magnifier or the "...", else Now Playing. The refresh line, section headers and rows keep their own x (14-16).
Shows sort by newest remote or local episode date. The show page has artwork, metadata,
Latest Episode and all known episodes in the show's Episode Order (newest first unless set to Oldest First). The Latest Episode pill is always the newest episode: the first row, the last under Oldest First. A body tap opens episode details;
the pill plays, downloads, pauses, resumes or retries according to state.

Episode details include the long description and the same playback/download actions. Their show row (cover, name, the list chevron) goes back to the show page the episode is on top of: a subscribed show's episode returns to that show's page (it is Back when the page was opened from that show; from Downloads or Subscriptions the show's page opens and Back goes on to that list), a search or Discover preview's episode returns to the preview.
Show and episode sheets provide refresh, unsubscribe, played marks and download removal. The show's sheet rows, in order: Playback Speed (grey value, a tap cycles), **Episode Order** (grey value Newest First / Oldest First, a tap switches to the other, saved at once, then the loaded rows are turned round in place (Oldest First is the exact reverse over the same newest 300, so nothing can fail after the save and the value, the list, the queue and Latest Episode always agree), the sheet stays; a failed save is the toast `Storage unavailable` and no change), Refresh Feed, Select Episodes, Mark All as Played, Unsubscribe (up to six rows, glass `pc_sheet6` for six; the row is `order` last in the asset's fixed rows, glyph `pod_ic_order`, Lucide arrow-down-wide-narrow). The Shows level's "..." is there only while the card has something to import (its one row is Import from Card).
Selection supports bulk deletion; the currently playing file is retained.
Deleting an episode clears its saved resume/played state. Unsubscribing preserves local files.

The search level is reached from the Shows level's globe (`btn_globe`, `pg_on_globe`) or from the Discover level's magnifier (`btn_search`, the navbar's left cap beside Now Playing): its navbar title is Apple Podcasts in the empty and the results states, as the keyboard page's; Back (and the keyboard's Back with nothing typed) returns to where it was entered, Shows or Discover (`from_disc`). The Shows level's navbar is `[Globe | ... | Now Playing]`, `[Globe | Now Playing]` or `[... | Now Playing]` (pieces 46 px apart right-aligned to Now Playing; the globe is shown only while Podcast Discover is on, the "..." only when there is something to import, and then is the middle piece `pod_nav_moremid`).
Search accepts directory terms, feed URLs and Apple Podcasts links. Results open a preview (rows of the shared list painter: the hairline from the text to x 310 and the list chevron at x 288, on a result that has a feed only: a dimmed Not available row opens nothing, so it has no chevron and its text runs to x 308 (`grid_tile_t.nochev`));
Subscribe creates a show folder and its metadata. Search previews do not play remote episodes.
Subscriptions supports card import/export, including OPML. The import also accepts
`Podcasts/subscriptions.txt`: one HTTP(S) feed URL per line, with `#` comments.

Saved episodes use stock `myfav` records. The Now Playing favorite control becomes a
bookmark for podcast paths. Its More sheet can return to the playing show's Podcasts page.
There is no separate Saved database.

## Discover

The Discover level (`L_DISC`, `pg_load_disc` and the `pg_disc_*` functions of `patch/podcasts.c`) is Apple's top 25 charts for the Podcast Region (`rss.marketingtools.apple.com/api/v2/<cc>/podcasts/top/25/podcasts.json` and `podcast-episodes.json`). Content from the list top, geometry `patch/offsets.inc` `DC_*`, model `pod_show.discover_layout`:
the large title Discover, the grey line under it (15 px `label_ps_meta`, the Downloads storage line's place: "Top 25 Shows in United States" / "Top 25 Episodes in ...", following the control), the **Shows | Episodes** segmented control (below), then the ranked rows from y 128: the list painter (`grid_list_paint`) shifted 26 px right for the rank (18 px grey `label_row_sub`, right aligned to x 28), so the cover is at x 36, the text from x 100 to 278 (the title, and the grey line: a show's author, an episode's show), the list chevron at x 288, the hairline from the text to 310; thumbnails arrive as for search results (placeholder first). The navbar is Back, the magnifier (`btn_search`, the Radio page's piece, hidden except here) and Now Playing as the capsule's right cap; the small title Discover shows from `SG_COLLAPSE` as on the other levels.

The **segmented control** is one shared painter, `pod_segmented` (`patch/common.c`, with `pod_capsule`; any number of segments): a fully rounded track `SEG_TRACK` (#1C1C1E) 296 x 36 at x 12 (under the large title, as the grey line above it), the selected segment a fully rounded thumb `SEG_THUMB` (#D1D1D6) floating `SEG_PAD` 3 px inside the track on every side with a dark label (`label_ps_latest`), the other labels white (`label_ps_latestw`), a `SEG_SEP` hairline half the track high between two segments that are both unselected (none beside the thumb; with two segments there is none), labels centred in their segments. Neutral: no accent colour. The capsule is painted a row at a time (the chord of the circle, one pixel of partial cover at each end), cut to the view's rows. The font has one weight, so the selected label differs by ink only (no bolder face). No soft shadow around the thumb. A tap on a half (touch 6 px taller than the control) selects that chart.

Each chart is fetched on its first view (the tick asks: `pg_disc_sync`; the downloads that run pause first, a running job is cancelled, a refresh is waited for) and its answer kept in memory for the session (`pn.cres`; no card cache): entering Discover again, the other chart and Back from a show page find it held and fetch nothing; the rows' artwork that was not tried (a job was cancelled) is fetched when the chart is in view again. A chart held for another region (changed in Settings meanwhile) is asked again. The worker (`patch/pcnet.c` "Charts", `PN_KIND_CHART`, one worker like search and preview, never touching widgets) makes up to three requests (20 s time-out each, one second apart) for a network or server error or an answer that is not a chart; a **404 or an answer with no rows for a region other than the United States asks the United States chart silently** and the line under the title names the storefront actually shown (`pn_chart_country`). Statuses are the page's words: Loading..., No Wi-Fi, Set the date first, Certificates missing, Storage unavailable, Can't connect, Certificate problem, Server error, Feed not found, No results (the status text is painted in the content under the control, at content y `DC_TOP` + 8, in the dim 20 px grey wrapped to the margins, by `pg_paint_hint` from `pg.htext`, the already translated words; so it scrolls with the title and the control, the content is `DC_TOP` + `PG_HINT_H` and `label_status` is not used; the Apple Podcasts search level does the same under its field at `PQ_TOP`); a failed chart is not asked again by the ticks, a tap on its half or entering the level again asks.

A tap on a row opens the show's preview as a search result does: the iTunes lookup of its Apple id in the store the chart is of (`pn_preview_chart`, `&country=`; a show row's `id`, an episode row's show id parsed from `/id<digits>` of its url: ids pass 32 bits, so they are digit strings), then the feed it names (`pg_open_preview`); the row's grey line reads Loading... meanwhile. A show whose lookup has no feed (PN_NOFEED) is remembered for the session (`pg.dna`, by the id's hash): its row says Not available, is dimmed and has no chevron, as a search result with no feed, and takes no tap, with no toast; any other failure is the toast "Can't subscribe: why" and the row as it was. Back from the preview, from Subscribe's page or from a show that is subscribed already returns to the same chart at its offset (`pg.pv_disc`); Back from the search level returns to Discover too (`pg.from_disc`), from Discover to the Shows level. Each chart keeps its own scroll offset.

An episode row also opens that episode's page on top of the show's preview, once the feed is held. After the feed, the worker makes the store's episode lookup of the show (`pn_pmatch`: `https://itunes.apple.com/lookup?id=<show>&entity=podcastEpisode&limit=20&country=<cc>`, in the chart's store; the row's own id is `pj_chart_t.eid`, the record's `trackId`, parsed by `pj_episodes`), and matches the record to a kept feed item (`pf_match`, `pn_preview_match`): the first item whose enclosure is the record's `episodeUrl`; else the first whose pubDate is in the minute of its `releaseDate` (`pf_iso`); else the first whose title is the same once a leading "586. " is dropped and case and runs of spaces are ignored. The record's `episodeGuid` is not the feed's guid and is not used. `pg_open_preview` opens the match with `pg_det_open`, so Back returns to the show's preview and then to Discover. No match, a failed lookup or an answer without the episode leave the show's preview alone; a Cancel during the lookup cancels the preview (the worker checks it after). Only the 20 kept items can match. Show rows make no lookup. Checked on 2026-11-06 with the 25 rows of the GB Top Episodes: all 25 match by enclosure (the store's `episodeUrl` and the feed's enclosure are the same pdst.fm address), and the date and title rules pick the same item. Fixtures: `test/data/discover/episodes-gb-top3.json`, `lookup-episodes-1611374685.json`, `feed-rest-is-politics-5items.xml`.

The preview's picture is the feed's channel image shrunk to `PN_PREVIEW_COVER`; when that cannot be fetched, decoded or shrunk (some feeds, e.g. The Rest Is Politics, serve progressive JPEGs of 2.25 to 9 MP, which `PC_COVER_MAX_PX` refuses), the store's `artworkUrl600` (a baseline 600 x 600 JPEG of about 100 KB; `pj_result_t.art6`, parsed by `pj_results`, "" when absent or longer than `PJ_ART`) is used through the same shrink path (`pn_preview_picture`). The URL comes with a search result (`pg.sp_art`, passed to `pn_preview`) or from the lookup an Apple id (link or chart row) makes in `pn_pmain`; a typed feed address, an OPML import and Deezer results have none and keep the old behaviour (no picture). Subscribe moves the preview's picture to `cover.jpg`, so the fallback is the show's first cover; `pn_cover` does nothing when the folder has a cover, so a later refresh whose image fails (or succeeds) neither deletes nor replaces it. Tests: `pcjson` (the field), `pcsearch/fallback_tests`.

## Region

`patch/pcregion.c`, model `tools/pcregion.py` (the table is generated into `stock.h` as `PCREGION_*`): 34 storefronts by English name (names are English in every language: no localised country-name table exists here or in the stock tables), saved as two capital letters and a line feed in `/mnt/data/m1plus/podcast-region` (anything else, a missing file included, is Automatic) by the Settings picker ([settings](settings.md)). `pcregion_code()` is the storefront in use: the saved one, else Automatic's: the UI language's country (`ja` JP, `ko` KR, zh_CN CN, zh_HK HK, zh_TW TW, `ge` DE, `fr` FR, `it` IT, `po` PL, `th` TH, `ru` RU, `uk` UA; the tokens are the locale's language and country, `locale_info`), for English and Spanish the Settings time zone's place by its index (London GB, Adelaide / Sydney / Brisbane / Eucla / Lord Howe AU, Auckland / Chatham NZ, Kolkata IN, the US zones US, Mexico City MX, Halifax / St. John's CA, Buenos Aires AR, Amsterdam NL, Bangkok TH, Tokyo JP) unless it is the stock default (22, Shanghai, which names nothing), else the United States. It drives the directory search (`country=<CODE>`) and the chart address (`<cc>` in lower case); the lookup of a typed Apple link is unchanged (no country), that of a chart row is made in the store the chart is of. Nothing runs at paint: the search and a chart ask when they start. Tests: `test/pod/pcregion.py` (every language against every zone against the model), `test/pod/menu.py` `region_row_tests`.

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
| `.m1plus/podcasts/order` | PCO1: count plus show-hash/value pairs (0 newest first, 1 oldest first); a missing file, entry or bad value is newest first. The key is the show folder's hash, so renaming a folder resets its order. Same 64 slots and eviction as speed (`pm_tab_*`, shared with it) |

Metadata permits LF or CRLF, ignores unknown fields and strips tabs/newlines from values.
The model reads at most 64 KB of `.episodes`, keeping the newest 300 entries. `pc_load_show` returns the episodes already in the show's order (`pc_order_get`; pcmodel.c `pm_ep_cmp`), so the Show page, the iPod episode level, the Downloads scan, Continue Listening and the queue (`pg_episode_queue`: from the tapped episode down the rows) agree; the cap of 300 keeps the newest 300 under either order (Oldest First lists those, oldest first), so the order never changes which episodes are listed. The sort's index lives in the same allocation as the merged entries, so a list is either in the show's order or not returned at all (no memory: no episodes, as before); there is no unsorted fallback.
Titles fit 95 bytes; local filenames must fit 127. Show feed/image URLs use `PC_URL` 320.
Short descriptions contain at most 200 UTF-8 bytes; episode notes at most 4096.

`pm_merge` combines feed entries and files into local, partial or remote episodes.
Without metadata, title comes from the filename and date from mtime.
Sort (newest first) is date descending, filename descending (digit runs by value, case ignored: `cc_key_cmp`, so Ep 10 is later than Ep 2), then entry order; Oldest First is the exact reverse. A show with no metadata entry (only copied files; the dates are copy order) sorts by that natural file name alone: descending for Newest First, ascending for Oldest First. A feed show keeps its publication-date sort.
Refresh preserves old entries whose completed or partial file remains on the card.

Limits: 40 shows, 300 episodes per show, 400 examined files, 512 resume slots and
64 speed records and 64 order records. State writes require `pod_card_mounted` and use temporary files,
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

One worker handles refresh, search/subscription, charts or downloads; it never touches widgets. The Radio directory fetch (`rd_fetch`, [radio](radio.md)) is refused while one of these runs; the reverse is not checked.
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
resume, speed, layout, search, Discover and its region, notes, selection, translations and stock tag-reader execution.
Models do not establish actual playback, Wi-Fi persistence, filesystem or frame-time results.

## Device checks

Check library exclusion and dot-folder scanning; file dates and m4b playback; queue navigation,
tag/cover display, resume across pause/reboot and music-speed restoration.
Exercise refresh/search/import with Wi-Fi loss, wrong clock, malformed feeds and screen-off.
Verify partial Range resume, servers ignoring Range, card-full/removal, queued downloads,
cancellation and reboot. Check large covers, long/CJK notes, Saved actions, currently playing
file protection, subscription removal, OPML round trips and responsive scrolling with 300 episodes.
Check Discover with Wi-Fi on and off, a region whose chart is missing (falls back to the United States), the Shows chart's failures and retries, taps on shows and episodes, a show with no feed, scrolling the 25 rows, the control's look and the magnifier.
Record results by build; these checks are not claims of completed hardware validation.

## Open items (Discover)

Episode rows (2026-11-06): a Top Episodes row opens its show's preview with the episode's page on top (matching in the Discover section); the episode page's show row returns to the preview. Built and tested under Unicorn, not flashed, not device-tested. Open: a subscribed show's chart row opens the show's page only (no episode jump); an episode beyond the 20 kept feed items falls back to the preview; the show row of an episode from a preview has the chevron now (it was not drawn there before).

State: built and tested under Unicorn, not device-tested. Open items:
- Device check: the capsule painter's cost while scrolling (about 100 one-row fills per capsule per frame, two capsules; not measured: if it shows, cache the control in a bitmap), the thumbnail rate (the worker fetches the 25 pictures of a chart one by one in order, the rows in view are not first), the shows chart's flakiness (the real timeout is 20 s, three tries), the "UK" / Region row widths, Wi-Fi loss mid-chart.
- Preview: `tools/preview_podcasts_revamp.py` has no Discover frames yet (only the Settings Library frame was updated); the design mockups were not kept.
- Not done: a chart's country is not shown anywhere else; no pull-to-refresh or Try Again on a failed chart (switch the control or re-enter the level); names stay English; the font has no medium weight for the control's labels; no shadow on the thumb.
- Not done: a DC-only decoder for progressive feed images (the store's `artworkUrl600` stands in for shows that have an Apple id); shows without one (typed URL, OPML) still get no cover from such a feed. Device check: the Rest Is Politics / News Agents / Rest Is History previews and subscribing to one show a cover.
- Podcast Discover switch (`ACT_PCSEARCH` 34, `podcast-online-search`, `pg.searchon`): Settings > Library > Podcasts, on by default ("0" is off, a missing file is on); off hides the Discover row and makes `pg_load_disc` / `pg_load_search` land on the Shows level, and `pg_on_fg` sends a Discover or search level back to the Shows level when the page is in front again with the switch off. The switch also gates the Shows level's globe; the Shows "..." has no Search row. Tested in `pcsearchui` `entry_tests` and `menu` `pcsearch_row_tests`; not device-tested.
