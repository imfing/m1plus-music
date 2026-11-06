# Home cover build

Sources: `patch/homecover.c`, `patch/durations.c`, `tools/pod_ui.py` (`cache_pill`), `HC_*` in `patch/offsets.inc`, `Preparing covers` in
`tools/pod_i18n.py`; test `test/pod/homecover.py`. The shared builder is described in [Cover Flow](coverflow.md) (`cc_build_*`),
its Albums-page use in [Albums](albums.md) "Cache building".

The Home page ([menu](menu.md)) builds the album covers that have no cache file in the background, with the same shared worker as
the Albums page, and shows a progress pill at the top of the page while it runs: `Preparing covers 120/840` with a bar and a stop button.

## The pill

- Placement: a window child of the menu asset, `pod_cache_pill` (`tools/pod_ui.py` `cache_pill`, constants `HC_*` in `patch/offsets.inc`): a view at (`HC_X` 12, `HC_Y` 10) of
  `HC_W` 296 x `HC_PH` 40, fill `#1C1C1C`, `round_radius` 20 (a capsule). The asset has it on the Normal menu too, hidden and insensitive; only Home ever shows it.
- Children (pill coordinates): the label `pod_cover_prog` at (18, 5), 230 x 18, 15 px (`HC_PX`) `#AAAAAA` (the grey of the Recently Played subtitles), left, middle; under it
  a 4 px progress bar at y 26, the track `pod_cache_track` (`#FFFFFF33`) and the fill `pod_cache_fill` (`#EBEBEB`), both 230 wide at most and fully rounded, the same pair as the Podcasts refresh card's;
  at the right end the stop button `pod_cache_x`, a 40 x 40 touch box drawing the 28 px disc `pod_cache_x` / `pod_cache_x_down` (`#2C2C2E`, pressed `#3A3A3C`, a white 14 px x; `tools/mod_icons.py` `CACHE_X`).
  No Accent tint: neutral.
- The bar is a resized child view: the payload sets the fill's width to `HC_BW * done / total` (230 px at most, never under 4 px) with `widget_resize` each time the counter moved.
- Showing it makes room instead of overlapping: the stock `list_view` (`pod_listview`) and its `pod_scrollview` / `scroll_bar_m` move
  down to `HOME_PAD + HC_H` (10 + 48 = 58: the pill and 8 px of air) and shrink by `HC_H` (392 px), then `menu_arrange` clamps the scroll offset; hiding it puts them back
  to 10 / 430. So the first row is never covered, and the pill ends 8 px above where the list starts.
- Hidden = `visible=false` + `sensitive=false` together, on the pill (its children follow). Shown only when the worker runs with at least one job: a library whose
  albums all have a picture or the empty "no art" marker never shows it, and it is hidden again when the done counter reaches the total,
  on background and on destroy. No first-run flag.
- Text: `TR("Preparing covers")` (a key of our own, 13 languages) + `" done/total"`, the count formatted in code and rewritten at each poll that saw
  the counter move (`widget_set_text_utf8`, rebuilt each time as the Cover Flow progress is). `test/pod/i18n.py` checks the widest
  `... 4000/4000` fits the label in every language.
- **The x** (`hc_on_stop`, `EVT_CLICK` on `pod_cache_x`, ctx = the window): `hc_off` is set and `hc_end` runs: the timers go, a half-scanned copy is freed, the durations done so far are saved,
  a set Home owns is `cc_build_stop`ped (never joined here; a worker still inside a job is orphaned as ever) and the pill hides. While `hc_off` is set Home starts nothing: `hc_later`, `hc_on_start` and `hc_dur_begin` return at once,
  also for a Home window opened later (the flag is a static in memory: a reboot clears it). Settings > Library > Rebuild Covers clears it when its request file is written (`homecover_rebuild_asked`, called from `rebuild_ask`),
  so the explicit rebuild runs at the next Home foreground. A build another page owns (Albums, Songs, Cover Flow, an album page) is never touched by the x.
- A static sync icon in the status bar shows on every page while any set runs: [Line Out pill and sync icon](lineout.md).

## The check and the stamp

Whether Home has work is decided before anything is queried or scanned (`hc_expect`, `hc_later`), from two cheap facts:

- **The stamp** `/mnt/mmc/.m1plus/cache-stamp` (`STAMP_FILE`, on the card like the cache): one line per part, `covers <albums> <hash>` and `tracks <albums> <hash>` (decimal count, 8 hex digits). The signature of the library is the stock Albums
  count and the order-independent sum of `cc_album_key` over its albums (`hc_lib_of`). A line is written when its part ran to the end (`hc_stamp`, atomic `pod_card_write`): covers when every album has a file or a marker
  (also an empty library; **not** a set that **stalled**: the hung album has its `.bad`, but the watchdog ended the pass with other albums unlooked at, so the next foreground scans again and skips it; a stalled Rebuild Covers keeps its request file too), tracks when the duration pass found
  the table complete or finished measuring (also no songs). A part that did not run to the end (card full, no thread, held worker, a save error) leaves its line as it was. Three more passes that look finished but are not:
  a **truncated** cover pass (more albums missing than one set holds, `CC_MAX_JOBS` 4000, or a path copy failed: `cc_build_truncated`, set by `cc_build_near_step`) writes no covers line and chains the next chunk (see "Chunks"),
  a **failed list copy** (`cc_list_failed`: rows but no memory for the copy) writes no line and hides the pill (Home asks again), and **no songs although there are albums** (stock `loadLocalClassList` returns the deque's size, so a query that failed before
  any row reads as an empty list, not as -1) is a failed song read: no tracks line, the pill hides, Home asks again.
  An **empty album list** may equally be a failed query. It is stamped (`covers 0 00000000`, and `tracks 0 00000000` when the song list is empty too; the signature 0/0 matches no real library, so any later successful read sees work) but never trusted:
  `hc_lib_of` leaves `lib.sigok` 0 for it, so `hc_expect` answers 4 at every foreground and the library is asked again silently at `HC_START_MS`. A still empty library matches its 0/0 stamp there: no pill, no scan. **The x writes nothing**, so after a reboot the pill comes back.
  Developer > Clear Cover Cache drops the covers line (`homecover_stamp_drop(1)`), Clear Track Durations the tracks line (`(2)`); no line left removes the file.
- **The database file's state** (`hc_dbsig`): `__xstat` of `/mnt/data/database.db` and its `-wal` and `-journal` (mtime, nanoseconds, size) as it was when the signature was last taken (`lib`, in memory, taken by every pass at HC_START_MS).

On Home open and on every foreground (not `hc_off`), `hc_expect` answers without a query or a per-album `access`:

- a missing stamp line or a pending `REBUILD_FILE`: work (covers, or tracks when only the tracks line is missing); no card: nothing;
- the database file changed since the signature was taken (a play changes it too), or nothing taken yet since the boot, both lines present: **not certain work**. The 5 s one-shot is armed silently (`hc.probe`, no pill) and the library is asked once then; equal to the stamp: done (the state is remembered, nothing was ever shown); different: the pill appears and the scan runs;
- otherwise (database as it was, signature equal to the stamp): nothing. No pill, no timer, no `hc_on_start`, no album query, no duration pass.

Work certain (a missing line, a pending rebuild, or a stale stamp left by an unfinished pass): the pill shows **at once** in its waiting state (`hc_wait_text`): `Checking library…` (covers or tracks pending, also when the cover pass found nothing and the duration pass begins), or `Rebuilding covers…` while a Rebuild Covers request (`REBUILD_FILE`) is pending, the bar's fill hidden, no count; the list makes room as usual. **The dots move:** the label drops the translation's trailing ellipsis (`…`, or three ASCII dots) and shows 1, 2, 3 ASCII dots, back to 1, one step every `HC_DOTS_MS` 400 ms, on its own page-scoped timer (`hc.dots`, `hc_on_dots`, RET_REPEAT; only the label is invalidated). The label is left-aligned at a fixed x, so the text does not shift as the dots change. The timer is removed when the count text takes over, in `hc_end` (x, background, destroy); a tick that finds the wait over or the pill hidden ends it by answering RET_OK. A translation without a trailing ellipsis is shown as it is and starts no timer. `test/pod/i18n.py` checks the waiting texts fit with three ASCII dots. The 5 s one-shot is armed as before;
the x in this state just removes it (`hc_end`) and hides the pill. The status-bar sync icon is untouched: it follows the worker (`cc_build_active`). At 5 s `hc_on_start` queries the albums once, takes the signature and compares it with the stamp (`hc_stale`): equal and no Rebuild
Covers: the pill hides, no scan; the covers line stale: today's scan and worker (the first `Preparing covers n/m` swaps the label and shows the fill); only the tracks stale: the duration pass; a silent probe shows the pill only when the signature differs; the scan finding nothing missing writes the stamp and hides the pill.
A worker held by another page at 5 s hides the waiting pill (the next foreground offers again).
**Returning to Home** while the pill was up when it left (`hc.resume = hc.shown` in `hc_on_background`: a build or its wait was in progress) arms the one-shot `HC_RESUME_MS` (1 s) out instead of `HC_START_MS`: it only has to cover the page's return transition, not the first open's menu and Recently Played load. `hc_later` spends the flag. A silent probe (no pill), a finished build (pill hidden) and the x (`hc_off`) keep or skip the 5 s as before; an orphaned worker still inside its last album is retried every `HC_POLL_MS` as ever.

Known limit: a song added to an existing album changes neither the album count nor the key sum, so the signature stays; its duration is measured by the album page, not by Home (a changed database alone, without a changed signature, starts no pass). After a reboot the first
Home open, and each one after a database change such as a play, costs one stock album query at 5 s even when nothing changed (no pill).

## The build

Called from `home_menu_opened` beside `recent_start` / `dailymix_start` (`homecover_start`, the Home instance only; no kill switch, no
widget: nothing). **No new hook, nothing at boot:** `homecover_start` looks up two widgets, registers `EVT_DESTROY`, `EVT_WINDOW_TO_BG`,
`EVT_WINDOW_TO_FG` on the window and arms one one-shot `HC_START_MS` (= `RC_RESOLVE_MS`, 5 s) out when `hc_expect` says work is expected (see "The check and the stamp"); a refused registration or timer leaves Home as it was.

- `hc_on_start` (page-scoped timer; reached only when work is expected): if the worker is held (`cc_build_busy`: Cover Flow, the Albums page, anything) it does nothing and
  the next foreground offers again. Otherwise it copies the library's albums (`cc_albums`, one stock query like the Albums page's open; `recent_rekey` first corrects Recently Played's cover keys from it, `docs/modules/recent.md`, and names the shelf's rows: `hc_order` moves them to the front of the scan, most recent first, so the shelf's placeholders are the first covers made),
  opens a `CC_MISSING` set (capacity min(albums, `CC_MAX_JOBS`)) and scans in steps of `HC_BATCH` 64 albums with `cc_build_near_step(centre 0)`
  (the displayed album order, no "in view" centre), re-arming itself `HC_SCAN_MS` 20 ms later so input is served between steps. After the
  last step the album copy is freed (the jobs hold their own path copies) and `cc_build_start` runs: nothing missing, no card, under 16 MB
  free or no thread frees the set and nothing is shown. Otherwise the pill shows `0/total` and the poll starts.
- `hc_on_poll` (`HC_POLL_MS` 500 ms): reads `cc_build_done`; when it moved, rewrites the text and the bar and calls `recent_refresh`, which lets the
  Recently Played tiles that showed the placeholder because their file was missing try again (`rc_tiles`: `art == 2` and the file exists now,
  then the shelf's own one-per-tick loader decodes it; paint never touches files). The Daily Mix card's art is its own render and the
  Made for You tiles pick the new covers up on the next foreground. At done == total the set is stopped (joined, freed), the pill hidden. A Rebuild Covers request is deleted then only if the set did not end by stall (`cc_build_stalled`) and the scan reached the end of the list (not truncated); a stalled one keeps it for the next foreground, which skips the hung album (its `.bad`).
- `EVT_WINDOW_TO_BG`: `hc_end` removes the timer, frees a half-scanned copy, `cc_build_stop`s a set Home owns (only then: a set held by
  anyone else is never touched) and hides the pill, so the worker never runs beside Cover Flow's or the Albums page's own build.
  `EVT_WINDOW_TO_FG` runs the check again and arms the one-shot (5 s) only if work is expected and nothing runs or is pending. A page that goes to the background and comes back
  with the stamp current and the database untouched does nothing; otherwise it scans again (about one `access` per album, 64 per 20 ms step). `EVT_DESTROY` ends it likewise
  and clears the state (an earlier window's destroy is ignored).

## Chunks

A library with more missing covers than one set holds (`CC_MAX_JOBS`) is built in chunks, each resuming where the last one's scan stopped, never from the first album (the worker leaves no file for an album whose track is gone or whose rename failed, so a rescan from 0 would queue the same albums for ever).

- `cc_build_near_step` stops at the first album the set cannot take and leaves `*cursor` on it (the cursor is 2 x distance + side around the centre; Home's centre is 0, so only even values occur and the album index is `cursor >> 1`); `cc_build_truncated` tells the caller.
- The resume record `rs` (static, `.scratch`: it outlives the window) holds the library signature (`lib.n`, `lib.h`), the mode (missing / rebuild), the cursor, a position-sensitive hash of the cover keys in stored order (`lib.oh`, made in the signature's own pass at no extra cost) and the shelf's rows. It is written when a truncated chunk's set **finished** (`hc_on_poll`), so a chunk Home leaves is redone from its own start (the record still holds it; the first chunk has none, and starts at 0 anyway).
  Then the next chunk is chained at once (`hc_on_start`, `HC_SCAN_MS`): it queries the albums again, and resumes only if signature, mode and the order hash match (otherwise it starts from 0 and the record is dropped). Each chunk queues at least one album, so the cursor moves on and the chain ends.
- **Order:** the scan runs in the stored order (not the Albums page's display order: Album Order by artist would sort the whole library on the UI thread at every chunk, and Albums and Cover Flow build what they show themselves), with the Recently Played shelf's albums first. The shelf changes when a song is played, so the record keeps the shelf's rows and the next chunks use them; the hash catches what remains (a swapped pair of albums, a changed list) by starting again from 0. Album Order does not affect the chain. When the shelf's order cannot be allocated, the pass is deferred to the next foreground rather than scanned in the stored order (a chain's cursor fits only the order it was taken in).
- Only a scan that reaches the end of the list with no stall writes the covers line, clears the record and (Rebuild Covers) deletes the request. Albums whose tracks are gone stay missing, as in a pass that fits one set. Starting a truncated chunk drops a covers line that is present (`homecover_stamp_drop(1)`),
  so a matching line can never skip an interrupted chain (the next foreground sees the missing line and shows the waiting pill). Rebuild Covers asked again and Clear Cover Cache clear the record. The durations start after the last chunk.

**UI-thread cost** (`test/pod/homecover.py` 7d4, harness instructions of the payload only; the stock query is mocked and not counted): at 1,000 / 4,000 albums the first `hc_on_start` callback of a chunk (query copy, signature and order hash in one pass, first `HC_BATCH` step) is 227 k / 875 k, a later scan step 25 k, the silent probe at `HC_START_MS` 202 k / 850 k, arming it 1.4 k. At 4,002 albums the step that truncates is 15 k and the next chunk's first callback 852 k: every chunk repeats the query, copy and signature, nothing more. Measured with Album Order by artist (Home does not sort). For scale, the Albums page's open of 4,000 albums is 2.0 M.

## Track durations

After the cover phase (or at once when no cover is missing), the same pill shows `Measuring tracks n/m` (key `Measuring tracks`,
13 languages; `test/pod/i18n.py` checks the widest `... 4000/4000`) while the worker measures the library's songs the
durations table lacks ([Album length](album-page.md#album-length)). The pill, its placement and the hide/show rules are the
cover phase's.

- `hc_dur_begin` runs when the page is in front, Home owns no set and the worker is free: `cc_songs` copies the stock Songs list
  (one query), a `CC_DURATIONS` set is opened (up to `CC_MAX_LEN_JOBS` 30000 files; a longer library runs more passes) and
  `hc_on_dscan` walks it in steps (`HC_LBATCH` 1024 songs looked up, `HC_LSTAT` 64 files `stat`ed, `HC_SCAN_MS` apart).
  A song is queued when its path has no table entry (CUE tracks with both ends and repeated paths are not queued).
  Home does not `stat` songs already in the table, so a replaced file is re-measured when its album page opens, not by Home.
- **Prune:** each pass names the paths of the in-memory song list (`dur_pass_seen`); entries nobody names are dropped and the
  table is rewritten (`dur_pass_end`). An empty list prunes nothing. No file is touched.
- `hc_on_dpoll` (500 ms) updates the pill and saves the finished jobs every `HC_LSAVE` 500 songs (merge, sort, atomic write).
  At the end the rest is saved and the set stopped. `EVT_WINDOW_TO_BG`, destroy and `hc_end` save what was finished and stop
  the worker (the job in flight is lost). The next foreground resumes with the songs still missing.
- A pass that finds every song in the table is not repeated until the library signature (album count and key sum) changes or Developer > Clear Track
  Durations is used (`hl_clean`, `dur_epoch`), and writes the tracks stamp line; songs added to existing albums are found by the album page (the stamp does not see them).
- The set needs the card (the table is `/mnt/mmc/.m1plus/durations`; without it the pass does not start) but not 16 MB free. The kill switch stops Home's start.
- Cost: not measured on hardware. Per file, TagLib reads the header and tags (an ID3v2 tag with a multi-MB cover is read
  whole); the work runs in the background worker, beside the player.

## Rebuild Covers

Settings > Library > Rebuild Covers ([settings](settings.md)) no longer opens Cover Flow. Its Yes writes the request file
`/mnt/data/m1plus/covers-rebuild` (`REBUILD_FILE`) and shows a toast. When `hc_on_start` begins a scan it checks the file (`access`):

- present: the set is opened in `CC_REBUILD` mode, so `cc_build_near_step` queues EVERY album with a track path (existing pictures and
  markers too; the shelf's albums first, as always), and the pill reads `Rebuilding covers n/m` (key `Rebuilding covers`, 13 languages);
- absent: the normal missing-only build above.

The request is removed only when the scan has reached the end of the list and the set completed (`done == total` in the poll, no truncation, no stall), or at once when no album has a track path (nothing
to extract). A library over `CC_MAX_JOBS` albums rebuilds in chunks, each in `CC_REBUILD` mode and each starting at the cursor the last one stopped at ("Chunks"); without the cursor every chunk would rebuild the first 4000 again. Interruption (Home to the background, destroy, a held worker,
no card or space, no thread) leaves the file, and the next foreground (5 s later) starts the rebuild again: from the beginning when the first chunk was interrupted, from the unfinished chunk's start after that; the worker replaces each file atomically, so a
restart only repeats work. Files already replaced stay new. The worker is the one at a time, so a
rebuild never runs beside Cover Flow's or Albums' own build.

Settings > Developer > Cover Cache shows the cache's counts and this build's status, and its Clear Cover Cache row is the opposite request: it deletes the cache (and this request file) in steps, see [settings](settings.md) "Clear Cover Cache"; the next Home open then shows the waiting pill (the covers line is dropped) and the scan queues every album as missing.

## Worker priority

`cc_worker` (`patch/covercache.c`) first calls `setpriority(PRIO_PROCESS, 0, 10)` through a six-instruction asm stub (`cc_setprio`, o32 syscall 4097: no import, the same way as `patch/filetime.c`'s statx). On Linux `who` 0 is the calling thread only,
so every cover and duration worker (any owner) runs at nice 10 while the UI and the player keep their priority; a refused call changes nothing. Tested with the harness's syscall answer (`Machine.sys`), not measured on hardware.

## Notes

- The scan's `cc_albums` runs `loadLocalClassList` like the other pages' opens do; it happens 5 s after Home is in front, never in the
  boot window.
- Tests (`test/pod/homecover.py`, Unicorn on the real payload with the harness's cache-file and worker mocks): hidden with nothing missing
  (also an empty library), `0/2` then `1/2` then hidden with the list restored, scan bounded at 64 albums a step, stop on background and
  destroy (also mid-scan), foreground re-offers once, a held worker / full card / refused thread / refused timer / asset without the pill.
  `test/pod/homecover.py` `pill_tests`: the pill's widgets in the asset, the fill width, the x (stops, suppresses a later start and a rebuilt Home, Rebuild Covers clears it), the worker's `setpriority`.
  `homecover/check_tests`: the waiting pill (no stamp, tracks only, Rebuild request), nothing when the stamp matches and the database is untouched, a changed database (silent; same library: nothing shown; one more album: pill and scan), the WAL, the x while waiting, the stamp at the end (a stalled set writes no covers line), a truncated pass (no line, a second chunk, then the line), a chain over 4002 albums whose first 4000 tracks are gone (the second chunk queues the two left, no third), a chain interrupted in its second chunk (resumed at its start; another album order starts again), a failed list copy and no songs with albums (no tracks line), an empty library (stamped 0/0, asked again silently at each foreground, no pill; then albums appear: the pill and the build), Rebuild Covers over 4002 albums (two chunks, the request kept until the second ends), Clear Cover Cache / Clear Track Durations dropping their lines.
  `test/pod/durations.py` covers the song phase (phases, saves, prune, stop, resume, held worker).
