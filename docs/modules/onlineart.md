# Find Cover & Lyrics (`patch/onlineart.c`, `patch/pcnet.c` "Find Cover & Lyrics", `patch/pcjson.c`, `test/pod/onlineart.py`, `test/pod/onlineartpage.py`)

An online lookup for the playing track: the album's cover from the **iTunes Search API**, then **Deezer**, and the lyrics from **LRCLIB**. It is a row on page 2 of Now Playing's More
sheet (`docs/modules/playmore.md`) and a page of our own. Stock has a hidden "Online search" row (`listitem3`, Baidu / Kugou / NetEase over plain HTTP); it stays hidden and is not used.
No new hook and no new patched stock word: the row is the existing More dialog hook's, the page a new window asset, the network the Podcasts worker's libcurl client.

Preview: `uv run python -I tools/preview_onlineart.py work/mod-release out/preview/onlineart.png` (twenty-two states: loading, Covers (current framed, scrolled), the cover confirmation (Use / Replace / failure), Lyrics (a saved row), the lyrics detail with a long English and a long CJK line wrapped (Save / Replace), every empty and failed state; the page's asset widgets are walked by the shared painter of `tools/preview_nowplaying.py`, what the payload paints itself is drawn from the same numbers, the wrapping by `tools/pod_wrap.py`; not tracked) and `tools/preview_playmore.py` (page 2 with the row, also dimmed).

## What the user sees

- **The row** (More sheet, page 2, between A-B repeat and Delete): the glyph `pod_ic_art` (`assets/icons/custom/cover-lyrics.svg`, a picture over two text lines) and **Cover & Lyrics** (13 languages). With the **Wi-Fi off** (stock `get_wifisignal() <= 0`,
  looked at each time page 2 is shown) the row is dimmed (opacity 100 of 255) and insensitive.
- **The page** (black, the stock navbar with Back and Now Playing, neutral white and grey, no accent): the **Search page's frame**: its chip row (**Covers**, **Lyrics**: the same place, font and look, the selected chip a light grey pill with dark text; opens on Covers), its line, and its list (stock
  `list_view` > `scroll_view` holding one content view the payload paints; it scrolls with a drag, the chips stay). Both lookups start when the page opens, so a switch of tab costs no wait; each tab keeps its scroll position. The state line (17 px grey, centred, y 146) is the selected tab's.
  - **Covers**: `Searching…`, then the thumbnails (88 px, three a row, 8 px corners; the store's first six albums that have a picture, then Deezer's until twelve): the list scrolls when more than three rows. Nothing found: `No Covers Found`; a failure in the words of the Podcasts page (`No Wi-Fi`,
    `Set the date first`, `Certificates missing`, `Certificate problem`, `Can't connect`, `Server error`, `Storage unavailable`, `Not enough memory`). A drag or a tap in the gaps does nothing.
    **A tap on a cover saves nothing.** It opens the **confirmation** (the same window, the tabs and list hidden): the larger picture (the 600 / 500 px one, downloaded by `pn_art_fetch`, decoded by `grid_art_url` to 240 px with 8 px corners, never an upscaled thumbnail; the disc placeholder
    until it is there), the album, the artist, the source (`iTunes` / `Deezer`) and the pill **Use This Cover** (**Replace Cover** when the album already has a `.pick` marker). The pill appears when the picture is decoded; a fetch that fails says its word under the source line and shows no pill.
    The pill saves (`Saving…`), then the grid again with that thumbnail framed white (current). A failed save says its word and gives the pill back. Back, from the confirmation, writes nothing, cancels a running fetch and removes the downloaded picture.
  - **Lyrics**: `Searching…`, then a row per LRCLIB candidate (the exact `api/get` match first, then `api/search`'s records by how close their length is to the track's, a synced one first among equals, at most 20): the title (21 px), under it `Artist · Album · m:ss` (grey, 18 px) and a small **Synced** badge at the right of the title when the record has
    `syncedLyrics`. An empty or failed lookup shows the state block (below). A tap on a row opens the **detail**: the title and the grey line as a header (in the chip row's place), the full text in the list (the `[mm:ss.xx]` tags and `[ar:]` headers removed, lines wrapped, a blank line of a plain text a 12 px gap), and the pill **Save Lyrics**
    (**Replace Lyrics** when `<song>.lrc` or `.LRC` is already there: **an existing file is never touched until that pill is tapped**), under the text region. After the write the rows again, that row wearing a light **Saved** badge instead of Synced. A write that fails says `Storage unavailable` in the header's grey line and leaves the pill. Back writes nothing.
- **Empty and failed states** (an Apple-style "content unavailable" block, centred on window y 260 over the list: a muted grey 40 px Lucide glyph `pod_es_*` (`tools/mod_icons.py ES_ICONS`, the image of the `oa_es_icon` widget, set with `image_base_set_image`), the title (`oa_status`, white 18 px), a two-line explanation (`oa_es_text`, grey 14 px, line and word wrap) and, where a retry can help, the **Try Again** pill (`oa_es_retry`, the page's pill style, 168 x 36). The widgets are the asset's; the payload (`oa_es_apply`) stacks what a state has and centres the whole (`tools/pod_ui.py oa_es_layout` is the same rule for the preview). The glyph, title, text and pill of every state are `pod_ui.OA_ES_STATES` (13 languages; the test proves the payload shows exactly those):

  | State | Glyph | Title | Explanation | Pill |
  |---|---|---|---|---|
  | searching | none | Searching… | none | no |
  | lyrics busy (PN_OVERLOAD) | timer | Lyrics Service Busy | LRCLIB is under heavy load. Try again in a moment. | yes |
  | covers busy | timer | Cover Service Busy | iTunes and Deezer are busy. Try again in a moment. | yes |
  | no lyrics | music | No Lyrics Found | LRCLIB has no lyrics for this song. | no |
  | no covers | image | No Covers Found | Nothing on iTunes or Deezer for this album. | no |
  | no connection | plug | Can't connect | Check your Wi-Fi connection. | yes |
  | certificate | lock | Certificate problem | The server's certificate was not accepted. | yes |
  | no certificates | lock | Certificates missing | This device has no certificate bundle. | no |
  | server error | info | Server error | The server could not answer. Try again later. | yes |
  | no Wi-Fi | wifi-low | No Wi-Fi | Turn on Wi-Fi to search online. | yes |
  | no date | calendar | Set the date first | Secure connections need the right date. | yes |
  | no card | memory-stick | Storage unavailable | The SD card could not be used. | yes |
  | no memory | hard-drive | Not enough memory | There is not enough memory to search. | yes |

  **Try Again** restarts only the selected tab's lookup (`pn_art_again(part)`: `PN_PART_COVERS` or `PN_PART_LYRICS`, the query of the last `pn_art`); the other tab keeps its results, scroll position and decoded thumbnails. It follows the job-slot rules: while another job runs (the other lookup, a podcast search, a download being paused) the tab shows "Searching…" without the pill (`oa.want` bit set) and the 250 ms tick starts it when the slot is free; a guard that fails on the retry (Wi-Fi lost) says its state on that tab only.
- **Busy services** (finding of 2026-11-01 from the first device test, SPARKLE by RADWIMPS): LRCLIB under load answers uncached queries (`api/get` and `api/search`) with HTTP **503** `{"message":"The server is busy, please retry in a moment","name":"ServerOverloaded"}` after about 0.65 s while cached ones answer 200 quickly; the page said "Server error". The lookup now **fails fast**: no request is repeated. A single HTTP 503 or 429 of LRCLIB, iTunes or Deezer is `PN_OVERLOAD` (`pn_fetch_json_api`; a distinct code, `PN_BUSY` is the job slot), shown at once as the busy state of its tab with the Try Again pill. A busy LRCLIB `get` skips `search` (the same service is busy; `PN_OVERLOAD` is reported at once), so the worst case to the busy state is one request, about 0.7 s; a 404, plain-only or good `get` still runs `search`. For covers a busy iTunes still lets Deezer run (another service); busy is reported only when neither answered (two requests). Automatic retries (1 s / 3 s waits, `Retry-After`) were built first and removed on 2026-11-01 because the user preferred a fast failure plus the manual Try Again to waiting 8 to 10 s.
- **The lyrics detail wraps every line** onto as many lines as it needs (`OA_LY_WRAP` 40, a source line of at most `OA_LY_SRC` 400 characters; break at spaces, between CJK characters, anywhere for a word longer than a line): the wrapper's closing ellipsis can no longer happen (before, a line over six lines was cut with "…").
- The lookup runs once, on open. Back (or Now Playing) cancels what is running; the page can be opened again for a fresh lookup. Back inside a detail returns to the tabs first.

## Services (all HTTPS, the firmware CA bundle `/etc/m1plus-cacert.pem`, verification never switched off)

| Part | Request |
|---|---|
| Covers 1 | `https://itunes.apple.com/search?media=music&entity=album&limit=8&term=<artist album>`: `collectionName`, `artistName`, `artworkUrl100` (`pj_results`; the first `PN_ART_ITUNES_MAX` 6 with a picture) |
| Covers 2 | `https://api.deezer.com/search/album?limit=8&q=<artist album>`: `title`, `artist.name`, `cover_medium` 250 px (`pj_deezer`; up to `PN_ART_MAX` 12 covers in all; the source of each is kept for the confirmation) |
| Thumbnails | the `art` address of each result, one request after another, at most 256 KB (`PN_THUMB_CAP`), kept as `a<n>.jpg` / `.png` in `/mnt/mmc/.m1plus/art/` when `pc_pic_info` and `pc_cover_ok` accept them |
| Larger picture | `pn_art_full`: the store's `100x100bb` becomes `600x600bb`, Deezer's `250x250-` becomes `500x500-`; any other address as it is; at most 3 MB (`PN_PICK_CAP`). Fetched for the confirmation (`pn_art_fetch`: kept as `full.jpg` / `full.png` when `pc_pic_info` and `pc_cover_ok` accept it), then reused by the save |
| Lyrics 1 | `https://lrclib.net/api/get?track_name=&artist_name=[&album_name=][&duration=<seconds>]` |
| Lyrics 2 | always (unless `get` failed on the network): `https://lrclib.net/api/search?track_name=&artist_name=`. Every record of either answer that has synced or plain lyrics is a candidate (`pj_lrc_each`: `trackName`, `artistName`, `albumName`, `duration`, the text; a record `api/search` repeats from `get` is dropped); up to `PN_LYR_MAX` 20, each text in `l<slot>.txt`, the display order a table (`lslot`) |

The term is `artist album` (the title when the track has no album tag), each field cut at 95 bytes on a character boundary, URL-encoded UTF-8 (`pn_urlenc`: letters, digits and `-_.~` as they are, every other byte `%XX`: a space is `%20`,
`&` is `%26`, CJK is three escapes a character). The user agent is `M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)` for every request of `pn_easy` (LRCLIB asks for the app and its address; the Podcasts requests carry it too).
The track's length (`get_playtimeandlength`, seconds) is the `duration`. iTunes is not given a country: its default storefront.

Answers are collected in the 96 KB buffer of the Podcasts search (`PN_JSON_CAP`) and taken apart by the bounded extractors of `patch/pcjson.c` (no recursion, no allocation, every read and write bounded; `pj_deezer` and `pj_lrc_each` are new,
`pj_results` is the Podcasts one; a string's `\n` stays a line feed for lyrics, `\uXXXX` and surrogate pairs are decoded, a text that does not fit `PN_LRC_CAP` 48 KB ends at its last whole line). The lyrics detail wraps a text once, when it opens (`oa_ly_build`: at most 14000 chars and 700 lines on the heap, freed when the detail closes; `pd_lines`, the Podcasts episode page's wrapper).

## The worker

`pn_art` (UI thread: the guards of `pn_guard` (card, Wi-Fi, clock, CA bundle), the old files removed, one detached pthread), `pn_art_fetch` and `pn_art_pick` (one worker, `pkmode` 0 fetch / 1 save) use the **one job slot** of `patch/pcnet.c` (`PN_KIND_ART`, `PN_KIND_PICK` beside the Podcasts
refresh, download, search and preview kinds: `pn_busy` is the refresh only, `pn_job_busy` every other job): never two at once, `PN_BUSY` from the second. The page pauses a running Podcasts download first (`pn_dl_pause`; its queue stays) and starts the lookup
from its 250 ms timer once the download thread has stopped; once the lookup has ended, and nothing is being saved, the timer starts the queued downloads again (`pn_dl_start`), and so does the destroy handler. The thread touches no widget and no stock
function: it writes the record the page reads (`pn_art_state` / `_code` / `_count` / `_gen` / `_thumb`, `pn_art_name` / `_artist` / `_source`, `pn_lyr_state` / `_code` / `_count` / `_get` / `_text`, `pn_pick_state` / `_code`; a store barrier before every counter). Cancel is `pn_cancel` (the transfer-info
callback stops the transfer in progress, no later request is made); on destroy a running worker is cancelled and left to end, its scratch files go with the next lookup. Standby turns the Wi-Fi off when nothing plays: a lookup that cannot connect ends at
libcurl's time-outs (connect 20 s, 30 s under 1 kB/s, 120 s total) with `Can't connect`; the page never waits on the thread, so the UI cannot hang.

## Where things are saved

- **The cover**, `pn_art_pick` (worker; only from the confirmation's pill): the larger picture the confirmation fetched (`full.jpg|png`; else downloaded to `/mnt/mmc/.m1plus/art/pick.src`), then for **each key** (the playing track's own `cc_album_key`, and the library's Albums row of that album name when its key differs: the
  library groups albums by name and files one under the artist of a representative track, so a compilation's Albums grid tile has another key) `pv_shrink` writes `ART_DIR/r<key>-168.jpg.tmp` (the Podcasts shrink: a JPEG fitted inside 192 px, never
  upscaled) and renames it over `ART_DIR/r<key>-168.jpg`, the **Cover Flow cache** (`/mnt/mmc/.m1plus/covers`), and a `r<key>-168.jpg.pick` marker is created beside it. Every page that shows a cover through the cache (Albums grid and list, Cover Flow,
  the album page, the mini player, Vinyl, Recently Played, Daily Mix, Search, the Pod) takes it from there the next time it loads that cover; a page already open keeps the tile it decoded until it is opened again.
  **Chosen because** the cache is what our pages read first (`cc_url`), it is keyed by artist and album (so it survives a library rescan, which never touches `/mnt/mmc/.m1plus`) and needs no new reader. **Rebuild Covers** (`build_art`, `CC_REBUILD`)
  leaves an album whose `.pick` marker and cache file exist alone (the extraction of the embedded art would have replaced the chosen picture); deleting the marker (or the cache folder) lets it be rebuilt.
- **The folder picture**: the original JPEG (the 600 / 500 px picture, atomically through `.cover.tmp`) is also written into the track's folder as the first of `folder.jpg`, `folder.jpeg`, `cover.jpg`, `cover.jpeg` that is there, else `cover.jpg` (stock's
  `toolsGetExternCover` reads `folder.png`, `folder.jpg`, `folder.jpeg`, `cover.png`, `cover.jpg`, `cover.jpeg` in that order; a `folder.png` therefore still wins, and is never touched), so the **stock Now Playing, lock screen and Cover Flow builder** show it for
  tracks **without embedded art** (stock takes embedded art first). Not written for a track in the card's root. Every track in that folder shares it (a flat folder of several albums gets one picture for all: remove it by hand).
  A PNG answer is shrunk into the cache only (no folder picture).
- **The lyrics**: `<track path with its extension replaced>.lrc` (`02 Karma Police.flac` becomes `02 Karma Police.lrc`; no extension: `.lrc` appended), UTF-8, written by the UI thread (`pn_lyr_save`: `<file>.tmp`, fsync, rename; the card only). Synced
  lyrics are LRCLIB's text as it is (carriage returns dropped); plain lyrics are saved as they are too, as the same `.lrc` (without time tags: how stock's `mclLoadExLyric` shows lines that have none is not verified).
  Stock reads the `.lrc` when a track loads, so the playing track shows it the next time it starts.
- Scratch, in `/mnt/mmc/.m1plus/art/`: `a<n>.jpg|png` (thumbnails), `pick.src`, `full.jpg|png` (the larger picture of the confirmation), `l<n>.txt` (the lyrics candidates, until one is saved), `lyrics.tmp`; removed by the next lookup and by the page's destroy when no worker runs.

Not done (a stock limit, no hook): tracks **with embedded art** keep it on stock Now Playing, the lock screen and the stock album pages; only our pages (and the Cover Flow cache users above) show the picked cover.

## Pins and hooks

None new. `get_wifisignal`, `widget_set_opacity`, `get_playtimeandlength` and the widget calls were already pinned; the sheet's hook is `dialog_playmore_dialog_init` (`PLAYMORE_PINS`, unchanged). `tools/pod.py` `SOURCES` gains `onlineart.c`.
`pcnet.c` gains the job code; `covercache.c` one early return (`build_art`); `playmore.c` the row. The asset: `ui/m1plus_onlineart.bin` (`tools/pod_ui.py build_onlineart_page`, `pod_pages.ONLINEART`), the row `pod_art` in both
themes' `playmore_dialog.bin` (`tools/mod_lists.py`), `pod_ic_art` (`tools/mod_icons.py`), `pm_sheet` 320 x 250 (page 2 then had five rows; it now has six, `PM_PAGE2_N` 6, and uses `pm_sheet6`: playmore.md), translations (`tools/pod_i18n.py`: Cover & Lyrics, Covers, Lyrics,
Saving…, Synced, Use This Cover, Replace Cover, No Lyrics Found, No Covers Found, Lyrics Service Busy, Cover Service Busy, Try Again and the explanations (`pod_ui.OA_ES_STATES`), Save Lyrics, Replace Lyrics, and the Podcasts' Saved; the failure words are the Podcasts ones). `pcdetail.c` exports `pd_lines`; the Search page's `SE_*` numbers are used as they are.

## Tests

- `test/pod/onlineart.py` (network and storage, a scripted libcurl): the store's and Deezer's answers against `json.loads` (fixtures `test/data/onlineart/*.json`: an iTunes album answer with CJK, accents, `&` and an escaped quote, a Deezer one with a nested artist, LRCLIB's get / search / 404), the requests
  (URL encoding of `&`, spaces and CJK, 95-byte fields, no album / no length, the options, the user agent), the job's order (iTunes, Deezer, thumbnails to twelve, `get`, `search`), the covers' name / artist / source, the lyrics candidates (the exact match first, the rest by the closeness of
  their length, synced first among equals, repeats dropped, the cap of 20, cuts at 48 KB, truncated answers, bad escapes, their files), every failure of either service, the guards, one worker at a time, Cancel, the fetch of the larger picture (`full.jpg|png`, a PNG, failures, cancelled), the pick (reusing it,
  the 600 / 500 px address, cache file(s), `.pick`, folder picture naming, failures), `pn_lyr_save` of a candidate, and `build_art` honouring `.pick`.
- `test/pod/onlineartpage.py` (the page under Unicorn): the asset (the Search page's frame and numbers, hidden widgets, the confirmation's and the lyrics header's boxes, contrast, every text in 13 languages), the tabs and chips, the thumbnails one per tick, painting and scrolling, the state lines of both
  tabs, the confirmation (nothing written until the pill, Use / Replace, the current frame, compilation keys, no folder picture for the card's root, failures, the Wi-Fi lost, Back while it downloads, a busy slot), the lyrics rows (title, grey line, badges, scrolled taps) and detail (tags stripped, wrapped, gaps, scrolling,
  Save / Replace, the `.lrc` name rule, a failed write, Saved badge), the downloads pausing and resuming, destroy, no track, a wrong asset.
- Added with the states: `test/pod/onlineart.py` `busy_tests` (one 503 / 429 -> PN_OVERLOAD from exactly one request and no waiting, a busy get skips search, 404 / 500 get still searches, Cancel with a busy get, iTunes busy + Deezer OK, both busy, `pn_art_again` of each part), `test/pod/onlineartpage.py` `state_tests` (every state in 13 languages with its glyph, title, text and pill, the stacking, insensitive decorations) and `again_tests` (Try Again restarts only its tab, waits for a busy slot, a failing guard), and the wrapping of an English, a CJK and a space-less line without an ellipsis.
- `test/pod/playmore.py`: the row on page 2 (six rows, 300 px, the glass `pm_sheet6`), the Wi-Fi dimming looked at on each visit, the tap, a refusing page, a stale handler, the text fit; a server track (Subsonic, streamed or downloaded): the row is dimmed and insensitive whatever the Wi-Fi, and `onlineart_open` refuses it (`oa_track`: no local album key to write a cover under, no file beside which `.lrc` and `folder.jpg` go; its path may be a stream address with the login; `test/pod/onlineartpage.py`).

## Device checks (not run)

Open More > More > Cover & Lyrics on a playing track with Wi-Fi on: the page opens, the sheet is gone; the covers arrive within a few seconds (TLS to `itunes.apple.com`, `api.deezer.com`, `lrclib.net`, `*.mzstatic.com`, `*.dzcdn.net` with the firmware CA bundle: not tried; a `Certificate problem` says
a root is missing), the quality of the matches for an album with a plain name, a CJK album, a compilation; tap a cover: the confirmation with the large picture, Use This Cover, then Back to Albums / Cover Flow / the album page / the mini player / Vinyl (the new cover after reopening), the cover folder
(`cover.jpg` next to the tracks; a track without embedded art shows it on stock Now Playing after the next track change), Settings > Library > Rebuild Covers leaves it; Save Lyrics writes `<song>.lrc` and the lyrics page shows it from the next play
(also: plain lyrics and an existing `.lrc`: Replace Lyrics); Wi-Fi off in Settings: the row is dim and a tap does nothing; the Wi-Fi lost while the page is open (`Can't connect`, no hang); Back while searching, then reopen; a Podcasts download running while the page opens
(it pauses and resumes); standby while a lookup runs.
