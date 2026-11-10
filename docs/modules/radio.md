# Radio

Internet radio: My Stations (one saved list, with Import from Card), Recently Played and the [radio-browser.info](https://api.radio-browser.info)
directory (Radio Browser: top stations, countries, genres, name search) on one stations page, and a Now Playing
page of its own. Station logos come from the directory's `favicon`. The parsers and the favourites file follow q2-pod's
`patch/radio.c` (MIT, README acknowledgement); the playback path is ours: stock's hciplayer plays the stream.
The start recipe was proven on a device (a probe, 2026-11-03: HTTP and HTTPS MP3, HTTP AAC; Wi-Fi off mid-stream did not
auto-advance to a local track); the state machine is not yet: see [Validation limits](#validation-limits).

## Sources

| Area | Files |
|---|---|
| Engine: parsers, card files, playback state machine, directory worker | `patch/radio.c`, `patch/radio.h` |
| Stations page | `patch/radiopage.c`, `tools/pod_ui.py` `build_radio_page` (`ui/m1plus_radio.bin`) |
| Now Playing | `patch/radionp.c`, `tools/pod_ui.py` `build_radionp_page` (`ui/m1plus_radionp.bin`) |
| Station Info | `patch/radioinfo.c`, `tools/pod_ui.py` `build_radioinfo_page` (`ui/m1plus_radioinfo.bin`), `tools/pod_pages.py` `RADIOINFO` |
| Hooks, pins, imports | `tools/pod.py` `START_PLAYER`, `SAVE_STOP`, `SAVE_START`, `BACKTOPLAYER`, `RADIO_PINS`, `LIBC`, `DATA` (`RESUME_POS`, `HCI_RUNNING`, `HCI_SOCK_FD`) |
| Entries | `tools/pod_pages.py` item 22 `Radio` (`ACT_RADIO`) |
| Tests | `test/pod/radio.py` (`check.py --list`: `radio/*`) |

## Entries

Radio is menu item 22 (saved as `n`), hidden by default; Extras lists it in Library, between
Podcasts and Search. The Pod has no Radio row: its main menu never opens a page of ours. The kill switch `/mnt/mmc/m1plus-off` leaves the menu itself closed (the only radio entry that reads it). Settings > Developer > Tools > Settings Files shows `radio-recent`.

## Stations page

One window, the Folders page's structure (glass navbar, large title, rows painted in `view_grid`). Levels share it:

| Level | Rows |
|---|---|
| Radio | Now Playing (shown while a station is up, or when Recently Played has an entry: the first one is the station last played; a group of its own, 24 px above the rest; a tap opens Radio Now Playing while a station is active, else toasts "No radio is playing" and starts nothing), My Stations (Lucide `radio-tower`, `pod_ic_rd_stations`), Recently Played, Radio Browser (Lucide `globe`, `pod_ic_rd_browser`); no credit |
| Radio Browser | Top Stations (`trending-up`), By Country (`earth`, `pod_ic_rd_country`), By Genre (`tag`): the root's rows and numbers; ends with the credit caption (below) |
| Countries | the Genres page's A-Z list (`patch/azlist.c`, `docs/modules/artists.md`; the rail and the headers follow the Index Rail and Section Headers switches): every country with stations, sorted by name with a leading "The " and leading punctuation dropped (`cc_name_cmp`) (an insertion sort of the three offset tables, `rp_pick_sort`), section letters, the pinned header, the A-Z rail and bubble; 52 px rows, the name 21 px white at x 24 (cut at 278), the `#8A8A8A` chevron at x 288, a `#222222` hairline to x 310 (all three 26 px further left, `SG_RAIL_INSET`, while the rail is shown), `#333333` pressed; no count |
| Genres | name, "N stations" (64 px rows, the 60 most used tags) |
| My Stations | the Albums page's list (default) or grid, one mode for every station list (below); the logo, else a `#2C2C2E` tile with the grey radio glyph (the grid's placeholder bitmap, made by `rp_placeholder` at the mode's size: the glyph is two thirds of the tile); a tap plays and opens Now Playing; no per-station "..." or sheet (Add to / Remove from My Stations is on Now Playing; the My Stations level has a "..." of its own, below); the first row or cell's top is at y 60 (48 in search) |
| Search | the page's own field (the Search page's `kb_field`) and pad, `keyboard_attach`; the action key fetches `byname`, the results are the station grid below the field (from y 48), the pad goes; a tap on the field brings it back; no live search (one network request per OK) |
| Caption | Loading…, No Wi-Fi, Set the date first, "Directory unavailable. Tap to try again.", No stations, No recently played stations (a note over the Recently Played level, as My Stations' below: its "..." stays, Back goes to the root), and for an empty My Stations "Add stations from Radio Browser or import .m3u files from the card." (a note over the My Stations level, not over the root: its "..." stays, Back goes to the root). The status label (`label_status`) is 18 px `#8E8E93`, 280 px wide and 120 px tall (centred on y 225), `line_wrap` with `word_wrap` set by the payload so lines break at spaces, not mid-word (Thai has no spaces and breaks by character). Every caption in the 13 languages wraps to at most five lines (the test measures them with the built font); the hint is three lines or fewer in English. A failure caption (No Wi-Fi, Set the date first, Directory unavailable) is also a button: a tap on the caption or the area around it fetches the same level again (`rp_on_retry`; the request is kept in `want_*`); No stations is final |

### Station list modes

Top Stations, a country's or a genre's stations, Stations, Recently Played and the search results share the Albums page's two modes (`patch/grid.c`, [Albums](albums.md)); the choice is `/mnt/data/m1plus/radio-view` (`RD_VIEW_FILE`, `home_write_atomic`): `1` grid, `0` list, missing or anything else the list.

| Mode | Geometry |
|---|---|
| List | 64 px rows under the large title (`grid_list_paint` with the offset `yoffset - rp_top()`): 52 px logo at (10, 4) with 4 px corners cut in the bitmap alpha, the name 21 px white (`label_row_title`) and "Country · CODEC 128k" 18 px `#AAAAAA` (`label_row_sub`) from x 74, 234 px wide, one ellipsized line each; a full-width `#222222` hairline, `#333333` pressed fill; a hit is the whole row |
| Grid | 2 columns of 144 px covers with 8 px corners from x 12, 200 px apart, the name 18 px white 4 px under the cover, the caption 15 px `#AAAAAA` (`label_grid_title` / `label_grid_sub`) |

The toggle `btn_radioview` (hidden and insensitive in the asset) shows on the station levels only, with rows in view and no caption (`rp_toggle_on`), never on the root, Radio Browser, countries or genres. It shows the glyph of the other mode (`pod_nav_grid` / `pod_nav_list`, the Albums ones). A tap stops a running scroll animation, keeps the first visible station (list row n is grid row n / 2; with the large title still showing the offset stays), redraws in place and saves the file. Navbar slots (`rp_nav`): Search shows only on Radio Browser, its countries, genres and online station lists (Top Stations, a country's, a genre's; `rp_find_on`), never on the root, My Stations or Recently Played. Root: no Search, Now Playing the glass disc alone; Radio Browser, countries, genres and their captions: Search 214, Now Playing 260; online station lists: Search 168 (left cap), toggle 214 (middle), Now Playing 260 (right cap), the small title ends at 168; My Stations: `btn_more` ("...", `pod_nav_more`, `rp_more_on`) in Search's place, 168 (left cap) with the toggle on 214 (middle, `pod_nav_grid` / `pod_nav_list`), or on 214 when the list is empty (a caption), Now Playing 260 (right cap); Recently Played: the same slots as My Stations (`rp_more_on` holds on both local levels, with rows or with the caption), no Search; search page: no Search, the toggle is the left cap on 214 (`pod_nav_gridl` / `pod_nav_listl`) once results show, else Now Playing is the glass disc alone.

The magnifier (Lucide `search`, the capsule's left cap) enters the Search level from Radio Browser or a level under it; Back leaves it for the
level it began on (a Loading caption first returns to the search page). Back stops a fetch and
returns to the level a caption covers, then goes up a level (a country's stations to the countries, the countries to Radio Browser, Radio Browser to the root); at the root it closes the page. Only
Radio Browser's level and the search results (not the root, countries, genres, Top Stations, Stations or Recently Played) end with a small grey
caption "Stations from radio-browser.info" (14 px, `#8E8E93`) 12 px under the last row or cell, left at that level's text inset (x 56 Radio Browser, 74 search list, 12 search grid). Each level keeps its scroll offset. The row glyphs
are bitmaps made by `rp_bitmap`: `cc_decode` flattens the white glyph over black, so the ink's brightness becomes the alpha and the colour white (no black square behind a pressed row); a
group of one row (Now Playing) draws no separator under it. Coming back to the front, the My Stations list reads the file again when `rd_serial` moved (a station added or removed on Now Playing follows; an emptied list shows the hint). The UI says "My Stations" for the list and its actions
(the file keeps q2's `favourites.m3u`); every row shows "Country · CODEC 128k" as any station row.

### My Stations and Import from Card

The My Stations level lists `favourites.m3u` in file order; new stations are appended at the end. No card file is read live. The "..." (`btn_more`) opens a bottom sheet in Radio Now Playing's style (`rd_sh_scrim`, `rd_sh_card`, row `rd_sh_import`, Lucide `import`; Back or the scrim closes it first) with one row, Import from Card (`rd_fav_import`, run on the UI thread, files capped by the read limit): every `.m3u`, `.m3u8` and `.pls` in `/mnt/mmc/Radio` by file name (case-insensitive; not `favourites.m3u`, dot files; at most 64 files), the stations whose address is not in `favourites.m3u` yet (nor earlier in the import) appended in file order up to `RD_MAX`, the file written once through `pod_card_write`; the user's files are never modified, renamed or deleted, so importing again adds nothing. Toasts: "Added N stations" / "Added 1 station", "No new stations", "No playlists in the Radio folder", "Stations is full" (the cap stopped it; what fitted is added), "Could not save Stations" (no card, write failed, a cut or NUL-holding file); then the list is read again in place (an empty Stations loses its caption).

### Recently Played and Clear Recently Played

The Recently Played level (`rp_recent`) lists `radio-recent` (the last 10 stations, newest first) in the station list modes. Opening it with nothing in the file keeps the level (the root does not stay): the caption "No recently played stations" over it and the "..." on the 214 slot. The "..." (`btn_more`, the My Stations code: `rp_on_more`, `rp_sheet_close`, the scrim, Back closing the sheet first) opens the same one-row sheet card with the row of the level: here Clear Recently Played (`rd_sh_clear`, the `pc_ic_trash` glyph the other delete rows use, tinted by the accent like the other glyphs; the repo's red is for Unsubscribe only), My Stations' Import from Card (`rd_sh_import`) on that level; one widget set, the payload shows the row of the level (`rp.favs`). The row calls `rd_recent_clear` (`home_write_atomic` of the header `#EXTM3U` alone, the way `rd_recent_push` writes the file), toasts "Cleared Recently Played" (or "Could not clear Recently Played" when the write fails: the list stays), closes the sheet and reads the level again in place, which shows the caption. A station that plays goes on playing and the root keeps its Now Playing row; with nothing running the row goes with the history (clearing it clears "last played"). Tests: `radio/favs_tests` (`recent_tests`).

## Directory

`rd_fetch` runs one libcurl worker (`pthread`, joined by the page's 250 ms timer that exists
only while loading; Back sets a cancel flag the transfer callback returns). Requests go to
`https://all.api.radio-browser.info`, verified with `/etc/m1plus-cacert.pem` (the Podcasts
bundle; ISRG Root X1 is in it), 10 s to connect, 30 s in all, 5 redirects limited to http(s),
256 KB cap (a cut answer is used up to its last whole row). Guards, in this order: Wi-Fi (`RD_E_WIFI`), a clock after
`PN_MIN_EPOCH` (`RD_E_CLOCK`), the CA file, then the busy ones: the radio's own logo job is asked to end
(`rd_logo_cancel`, it stops within a transfer callback; the directory goes first) and a podcast refresh, search, art job or download
(`pn_busy`, `pn_job_busy`, `pn_dl_running`) is never cut short (`RD_E_PODBUSY`). Podcast jobs do not check for a radio fetch.

Retries (`rd_fetch_retry`, the worker): a network or TLS failure (any libcurl code but a cancel, 42 or 23) or an HTTP 5xx is tried
again up to twice, 1 s then 2 s later, each attempt on a fresh libcurl handle so the round-robin name may resolve to another mirror and
a half-read answer is dropped. A 4xx, any other answer, the size cap and a cancel are not retried; Back ends a wait within a second. The
page keeps its Loading… caption throughout. If the opt-in log file exists (`/mnt/mmc/m1plus-log`, the Home log), a fetch that ends without
an answer appends `radio: directory <path> failed: curl <code>, http <status>, attempts <n>` to `/mnt/mmc/m1plus.log`.

The page asks again every 250 ms while a fetch is busy: about 8 s for our logo job (in practice under a second after the cancel),
about 20 s for a podcast job, then "Directory unavailable. Tap to try again." A failure caption (No Wi-Fi, Set the date first,
Directory unavailable) is tapped to fetch the same level again; every caller of `rd_fetch` (`rp_fetch`: levels, search) shows No Wi-Fi at once and never starts a Loading timer for it;
the logo jobs refuse without Wi-Fi.

Endpoints (each station list with `order=votes&reverse=true&limit=100&hidebroken=true`):
`/csv/stations/topvote/100?hidebroken=true`, `/csv/stations/bycountrycodeexact/CODE`,
`/csv/stations/bytagexact/TAG`, `/csv/stations/byname/TEXT`,
`/csv/tags?order=stationcount&reverse=true&limit=60`; countries are `/csv/countries?order=name&hidebroken=true` (all of them; a row whose count is 0 is dropped by `rd_choices`). Deviation from q2's `/m3u/...`: the m3u answer has no country, codec or
bitrate, which the caption needs. `rd_stations` reads the CSV by header (`name`, `url`,
`url_resolved`, `country`, `codec`, `bitrate`, `favicon`; the info string is `country<TAB>codec<TAB>bitrate<TAB>favicon`, the favicon kept only as an http(s) address of at most 200 bytes), prefers `url_resolved`, decodes quoted fields.
Lists hold at most 300 rows (`RD_MAX`); names are cut at 120 bytes, invalid UTF-8 becomes `?`.

## Card files

| File | Contents |
|---|---|
| `/mnt/mmc/Radio/favourites.m3u` | the My Stations list: `#EXTM3U`, per station `#EXTINF:-1,NAME`, optional `#M1+:country<TAB>codec<TAB>bitrate`, the address; rewritten whole through `pod_card_write` (`.tmp`, fsync, rename; nothing without the card, never when it holds more than 300 rows or a NUL) |
| `/mnt/mmc/Radio/*.m3u`, `*.m3u8`, `*.pls` | the user's own playlists, read only by Import from Card (above), never edited; `.pls` `FileN=` / `TitleN=` match by N |
| `/mnt/mmc/Radio/.logos/<hash>.jpg` | a station's logo (hash of its favicon address), a baseline JPEG of at most 192 px; `<hash>.no`: no picture to be had; past 400 files the folder is emptied |
| `/mnt/data/m1plus/radio-recent` | the last 10 stations, newest first (the first is the station last played: whether the root shows its Now Playing row when idle, `rd_last_read`; the row never starts it), an `.m3u`, a station played again moves to the front (`home_write_atomic`) |

## Station logos

A page timer (300 ms, `rp_on_ltick`, exists with the stations page) looks at the cells or rows in view, then one grid row or two list rows beyond them in the scroll direction (read from the offset change between ticks), only with the screen lit, the page on top, no caption and the list still (no drag, no scroll animation):
a made logo is decoded into its tile (one a tick, `grid_art_url`, the Podcasts cover size check `pc_cover_ok`); the first row in view without one starts the logo
worker (`rd_logo_start`, one job at a time, never beside the directory fetch or a podcast job, guarded by Wi-Fi, clock, CA bundle and the mounted card). The worker fetches the
favicon with libcurl (5 s to connect, 10 s in all, 3 redirects, HTTP errors fail, 256 KB cap, verification on) to `/tmp/m1plus-logo.src`, takes JPEG (`pv_shrink`) and PNG
(`pv_shrink_png`; interlaced ones are skipped) through the Podcasts cover shrink into `<hash>.tmp` and renames it to `<hash>.jpg`; GIF, ICO, SVG, WebP, pages, HTTP errors and
oversize answers leave `<hash>.no`; a network failure only a note for the session (16 kept); a card that refuses the marker (full or locked) stops new logo downloads for the session, cached logos still show. `Radio/` and `.logos/` are created
on the first save (a fresh card has neither). The mini bar asks again each tick while its radio logo is pending and the worker idle. Radio Now Playing shows the same logo (decoded to 192 px, drawn on the white art card
(see Radio Now Playing) and asks for it when it is missing; the glyph stays until then. Stations keep the logo address in their `#M1+:` line.

## Playing

Stock's audio daemon (hciplayer, MPlayer 1.3.0) opens the stream, so the DAC, the wheel volume, pause and screen-off playback are stock's own. The start, proven on the device (HTTP and HTTPS MP3 through lavf + OpenSSL, HTTP AAC), is exactly this (`rd_begin`):

1. `rd_dac()`: `set_outputchannel(output, 2, 0)` (`0x4d6f68`) for every output, as stock's `start_player` does (it also moves `mclSetOutputWay`, which sends `{mcl-setoutputway\N}` to hciplayer, to 0 for the jacks, 1 for Bluetooth, 2 for USB audio). Then, for the built-in DAC only (way 0): `mclSetDacPwr(1)` when only the idle timer cut it, `mclSetPcmMode`, `mclSetMute(0)`, `set_devicevolume`. Without it hciplayer logs "Audio device got stuck!" and is silent. A USB DAC keeps its own power and volume (not tried on a device). Bluetooth (selector 2, way 1) is readied by `set_outputchannel(2, 2, 0)` alone: it sets way 1 and `mclSetDacPwr(0)` (the DAC off), exactly what stock's `start_player` and `start_playqueue` do for local music; nothing else in `mclStartPlayer` / `mcl_tidalStartPlayer` looks at the way, so hciplayer picks the Bluetooth (bluealsa) PCM itself from the way message, and the volume is the headset's. Not settled statically: that hciplayer's MPlayer opens that PCM for an http stream as it does for a file (device check).
2. Speed: `mclSetPlaySpeed(0)` when stock's Multiple Speed (`playspeed_mode` `0xa05acc`) is not 1x (a live stream plays at 1x; `config_mplayer` would otherwise resend the mode). The mode itself is never written; `rd_apply` sends it back with `mclSetPlaySpeed(mode)` (when non-zero) after the stop on every transition from running to not running (Stop, Local track, the Error cells). A podcast's override (`patch/pcmodel.c`) writes the same variable and restores its own original; the radio only reads it and sends whatever it holds, so neither clobbers the other's variable (an override still active when the radio starts is what comes back).
3. `*(int *)RESUME_POS = 0` (`0xa0abc4`; a value >= 0 keeps `mcl_tidalStartPlayer` from asking the play queue).
4. `mcl_tidalStartPlayer(url)` (`0x5d5184`; sends `{set-songurl\URL|...}`; returns 1 when sent). Stock's own Now Playing shows a placeholder for it; Radio Now Playing is the UI.
5. `mclSetMute(0)` again: the DAC type 15 routine at `0x5d4e00` mutes before it sends the URL.

Stop is `mclStop()` (`0x5d244c`): it sends `{mcl-stop}` and waits (synchronous, stock's own `stop_player` waits the same way) for hciplayer's exit reply; with stock's running byte (`0xa0ab8a`) at 0 it returns -1 at once, so it is safe in any state. `rd_play` refuses addresses that are not `http://` / `https://`, or contain `|` (hciplayer splits its fields on it) or `}`; it copies the list (previous / next step along it, round its ends), runs stock `stop_player` when the radio is not already running (local music holds the PCM), then sends the Play event. Titles: ICY `StreamTitle` does not reach demo in this design, so the line under the name is "Country · CODEC 128k" from the directory. Next step: a relay on 127.0.0.1 or a side metadata connection.

### What the tick reads

`rd_poll` (the engine's own 500 ms timer, started by `rd_play`, gone when the radio is not connecting, playing or paused) holds standby and auto power-off (`reset_poweroptions_timer(1, 1, 0)`) and zeroes a counting `dacoff_time` while connecting or playing (paused lets the player sleep, as paused local music does), then reconciles with stock instead of trusting its own state. Verified in the disassembly (`mclSyncPlayerStatus` `0x5d144c`, `mclWaitAccept`):

| Input | Meaning |
|---|---|
| running byte `0xa0ab8a` | 1 from `mcl_tidalStartPlayer` until an `exit` reply of hciplayer (stop, end) clears it; `error` replies also drop the status to 1 |
| socket fd `0xa0abec` | -1 = no hciplayer; a different fd than at the start = demo restarted hciplayer |
| `mclGetPlayStatus` `0x5d3640` (word `0xa0abe4`) | stock's own flag: 1 stopped, 2 playing (set optimistically by the start), 3 paused (stock's pause call) |
| `mclGetHciplayerStatus` `0x5d436c` (byte `0xa0ab8b`) | refreshed every 200 ms by a stock thread (`mclSyncPlayerStatus`) from `{player-status\request}` while the running byte is 1: 1 only when hciplayer's reply is `playing` |

The `{media-info\...}` fields (bitrate, rate, codec) are stored by the same thread, but their layout is not decoded and not used. Unverified on a device: that hciplayer answers `playing` for a live stream while it buffers and plays (the Connecting to Playing step and the stall rule depend on it), and that an `error` reply reaches the flags without a stock request in flight. If `playing` never arrived the engine would end a working stream with "No response" after 20 s: the first checklist item below catches it.

### State table

States: **Idle** (nothing started yet), **Connecting**, **Playing**, **Paused** (stock's pause), **Error** (words in `rd_error`), **Stopped**. `rd_running` is Connecting, Playing or Paused. The table is `RD_TABLE` in `patch/radio.c`, a pure function `rd_step(state, event, tries, wifi)` the tests walk cell by cell (14 events, 6 states). Actions: `stop` = `mclStop()`, `start` = the proven start, `retry` = the start again 1 s later, `pause` = `mclSetPause()` after the start (only if the start worked). "Stays" = no change, no action.

| Event (source) | Idle | Connecting | Playing | Paused | Error | Stopped |
|---|---|---|---|---|---|---|
| Play (tap, station switch, double tap, Play button, previous / next) | Connecting, start | Connecting, stop + start | Connecting, stop + start | Connecting, stop + start | Connecting, start | Connecting, start |
| Bad address (`rd_play`) | Error "Unsupported address" | Error, stop | Error, stop | Error, stop | Error | Error |
| Start failed (no socket: "Player not ready"; `mcl_tidalStartPlayer` not 1: "Could not start") | Error, stop | Error, stop | Error, stop | Error, stop | Error, stop | Error, stop |
| Stop (large button) | stays | Stopped, stop | Stopped, stop | Stopped, stop | Stopped | stays |
| Local track (`mclStartPlayer` hook) | stays | Stopped, stop | Stopped, stop | Stopped, stop | stays | stays |
| Reroute (`save_start_player(0)`: the output changed under a running station, stock would resume playing) | stays | Connecting, stop + start | Connecting, stop + start | Paused, stop + start + pause | stays | stays |
| Reroute paused (`save_start_player(1)`: stock restarts its track and leaves it paused) | stays | Paused, stop + start + pause | Paused, stop + start + pause | Paused, stop + start + pause | stays | stays |
| Heard (hciplayer status 1, status not paused) | stays | Playing | stays | Playing | stays | stays |
| Paused (play status 3) | stays | Paused | Paused | stays | stays | stays |
| Resumed (play status 2 while Paused) | stays | stays | stays | Playing | stays | stays |
| Ended (running byte 0, socket -1 or changed, or status 1 with hciplayer not playing) | stays | once per play, Wi-Fi up: Connecting, retry after 1 s; else Error "Could not connect", stop | Error "Playback ended", stop | Error "Playback ended", stop | stays | stays |
| Stall (Playing, hciplayer not playing for 10 s) | stays | stays | once per play, Wi-Fi up: Connecting, stop + start; else Error "Stream stalled", stop | stays | stays | stays |
| Time-out (Connecting for 20 s with no "playing") | stays | Error "No response", stop | stays | stays | stays | stays |
| No Wi-Fi (a start with no connection: `rd_play` for a tap in any list, Retry and play on Now Playing, the mini bar's play and retry, the previous / next buttons; `rd_resume` from Paused; Reroute and Reroute paused, which send this instead) | Error "No Wi-Fi" | Error "No Wi-Fi", stop | Error "No Wi-Fi", stop | Error "No Wi-Fi", stop | Error "No Wi-Fi" | Error "No Wi-Fi", stop |

Rules around the table:

- A start with Wi-Fi down (`get_wifisignal() <= 0`) is the No Wi-Fi event: no attempt and no 20 s wait, no `stop_player` (local music keeps playing), the list and position are kept so the next tap or Retry after Wi-Fi is back starts normally (Error accepts Play). Ended, Stall and Time-out with Wi-Fi down also give Error "No Wi-Fi" and restart nothing. The restart allowance (`tries`) is 1 per play; it resets on a new Play and after a stream has played for 60 s.
- The first 1.5 s after a start the flags are not read (the start sets them); a pending retry is waited for before anything else is read. A hardware or stock Stop key while the radio plays shows as Ended: stock's stop and hciplayer's own end set the same flags, so it cannot be told apart and gives Error "Playback ended" (the Play button retries).
- Stock status 1 while hciplayer still says playing is ignored: the audio wins and nothing is stopped.
- Screen off / on, a closed or re-opened page and sleep change nothing in the machine: the engine timer runs while the radio is running, the pages only read the state. USB / storage mode and a changed output way are seen through the same flags; a switch of the output under a running station is the Reroute event (next section).
- Not done: media keys outside our pages act on stock's player; a stock auto-advance after hciplayer ends calls `mclStartPlayer`, which stops the radio first (Local track), then plays the local track.

Invariants (tested; a Reroute restarts the same station and never counts against `tries`): Stop works from every state and is idempotent (`mclStop` is harmless with nothing running; the state ends Stopped, Idle stays Idle); every non-terminal state has an exit (Connecting: Heard, Ended or Time-out; Playing: Ended, Stall, Stop or Local; Paused: Resumed, Ended, Stop or Local); a play tap works from every state (Error and Stopped included, which is the retry); local playback always wins (the hook runs `mclStop`, sets Stopped and never waits for the timer); the timer exists only while `rd_running` (a stop, error or hook ends it, `rd_tick` returns `RET_OK` and clears the handle); a station switch is a stop then a start, never two streams.

## Output changes

Stock runs the same sequence for every output change while something plays: `save_stop_player` `0x4e2304`, `set_outputchannel` (and `set_devicevolume`), `save_start_player` `0x4e23e8`, all in one UI-thread handler (`check_otg_status` USB OTG, `set_hs_po_output` / `set_hs_bal_output` the jacks, `switchBluetooth`, `checkBluetoothStatus`, the DSD mode switch on USB audio, `into_standby`; `handleBluetoothLink` / `handleBluetoothPair` and the Bluetooth reconnect dialog only stop). Disassembled: `save_stop_player` returns at once when `mclGetPlayStatus` is 1, else saves that status (`mclSetSavePlayStatus`) and the play time, `mclSetMute(1)`, sleeps 150 ms, `mclStop`, notifies; `save_start_player(paused)` calls `mclStartPlayer` (`0x4e2458`) when the saved status is not 1 and below the play queue's size, calls `mclSetPause` (and sets the byte at `0xa04736`) when the argument is non-zero (stock restarts its local track and leaves it paused: ear safety, 4.4 mm is louder). Callers (`demo.dis`): argument 1 from `set_hs_po_output` and `set_hs_bal_output` (both ways), `check_otg_status` (USB plug and unplug), `switchBluetooth`, `checkBluetoothStatus` (two of three sites), `into_standby` (standby wake) and `btdevice_listitem_layout`; argument 0 from `systemset_display_page_init`, one `checkBluetoothStatus` site, and `dialog_msginfo_dialog_init` (0 or 1 by a condition), resets the saved status to 1 and notifies. While a station plays (play status 2) that second call is the old local track starting through hook 9, which would stop the radio.

Hook 18 (`tools/pod.py` `SAVE_STOP`, `SAVE_START`, pinned prologues, resume words `0x4e2310` / `0x4e23f4`, `$gp`; payload hooks in [payload](payload.md)):

- `rd_save_stop`: with a station connecting, playing or paused, `mclStop()` and nothing else (no state change, stock's saved status and notifications are skipped, so nothing of stock's restarts later); otherwise stock's function.
- `rd_save_start(paused)`: with a station running, the Reroute event (Reroute paused when `paused` is non-zero) (no Bluetooth event: Bluetooth is a Reroute like the jacks): the table restarts the same station through `rd_begin`, which readies whatever output the selector and `mclGetOutputWay` now say (`rd_dac`, so the built-in DAC gets its volume from `set_devicevolume` as for local music, a USB DAC its own, Bluetooth way 1 with the DAC off). The restart is not counted against the restart allowance. Reroute paused (what the jacks, USB, Bluetooth switch and standby wake pass): from Connecting, Playing or Paused the station is restarted and then `mclSetPause()` leaves it Paused, as stock leaves local music paused, so the user presses play (the tick sees play status 2 while Paused as Resumed; a local pick still stops the radio, and a failed start's Error wins). Plain Reroute (argument 0): Connecting / Playing restart playing; Paused is restarted and paused again (a live stream cannot hold a position, so this only keeps the user's pause). Otherwise stock's function.
- The tick cannot fall between the two halves (same UI-thread handler). A stop with no start (Bluetooth linking) leaves the state Playing for the next tick, which reads the dead stream as Ended. The tick no longer looks at the output way: Bluetooth is not refused. Bluetooth connecting or dropping mid-stream goes through the same pair as the jacks (`switchBluetooth`, `checkBluetoothStatus`, `btdevice_listitem_layout` pass argument 1 in the cases listed above), so the station restarts on the new output and stays Paused.
- Not hooked: `reconfig_player` `0x4d8760` (called from `on_wm_idle_status`): it calls `mclStartPlayer` only when the saved status is 2, which `rd_save_stop` never sets, so it cannot start a local track behind the radio; a reconfiguration of hciplayer while a station plays shows as Ended. `mclSetPause` for removed headphones is the existing Paused event. `into_standby` uses the same pair: after a wake (`save_start_player(1)`) the station restarts at once, probably before the network is back (the retry and the error words apply), and ends Paused.

## Hand-over

Hook 16, `mclStartPlayer` `0x5d5300` (every local track's start; q2-pod's `ringnav_start_player` hooks it too): `rd_start_player` sends the Local-track event when the radio is running (Connecting, Playing or Paused): `mclStop()` (stock sends `{set-nexturl\...}` while its running byte is 1, and hciplayer does not leave a stream for it; once it died), state Stopped, no widget and no timer call (it may run off the UI thread; the engine's timer sees the state and ends), then resumes stock past the prologue. With no radio it is one comparison, also at boot (Memory Playback). Pinned: prologue `(0x3c1c0043, 0x279cebd0, 0x0399e021)`, resume word `0x5d530c`, `$gp`; fallback is stock (a mismatch fails the build). Our own play paths reach `mclStartPlayer`, so they stop the radio. The radio's own start runs stock's `stop_player` first when it is not itself running. Not done: media keys outside our pages (a hardware Play/Pause while the radio plays acts on stock's player and, if it starts a track, stops the radio).

## Now Playing entries

While a station connects or plays (`rd_running`; a stopped radio is not active, whatever Recently Played holds), every Now Playing entry opens Radio Now Playing (`rn_open`; if the page is up, on top and not closing nothing opens, Back returns to the page it was opened from; a page that is closing or under another window is replaced by a fresh one: AWTK destroys a closed window later, so `rn_on_destroy` is bound with its window and ignores a window that is no longer `rn.win`) and a failed open (no memory) opens stock's player:
`pod_open_now_playing` (`patch/common.c`) for our pages (`pod_on_player`: the navbar buttons and the mini bar card; the Home menu's Now Playing row, `patch/m1plus.c`); and hook 10, `on_backtoplayer_onclick` `0x4cd58c`, for stock pages (`rn_backtoplayer`, `docs/modules/payload.md`). The Home mini bar keeps a stopped station (`rd_owns_bar`: set when `rd_play` starts a station, kept through Stop and Error, cleared by `rd_start_player` when a local track starts; the Stopped bar shows "Stopped" with the play glyph, a tap plays the same station again with the usual Wi-Fi check, and the card opens Radio Now Playing). Stock's Now Playing button for a stopped station is unchanged (`rd_running`). The stations page's Now Playing row (`RR_NOW`, `rp_root_action`) opens Radio Now Playing only while `rd_running`; Idle, Stopped and Error (a local song playing or not) toast "No radio is playing" (`pod_toast`) and do nothing else: the row never starts a station, not even the last played one. Idle (nothing played this session, so the flag is 0) and Clear Recently Played (the flag is not touched) leave the bar as before. Tracks the Pod starts itself still open its own screen (local music stops the radio first). Test: `entry_tests`.

## Radio Now Playing

`ui/m1plus_radionp.bin`, Apple Music's radio page on the Now Playing numbers (`tools/mod_nowplaying.py`): grabber
(Back); a 264 px art card with 10 px corners and the Now Playing shadow (the station's logo, decoded to 192 px, on a white
card; else a grey card `#2C2C2E` with the broadcast glyph); the window tinted from the logo (the mean of its pixels that are
neither near-white nor near-black, `pod_tone`, then the Now Playing gradient `np_tint`; no logo: the neutral `#202020`);
the station's name (22 px, white) over one line (17 px, grey); the round "..." (`np_more`) where the More disc is, which
opens the bottom sheet (`pc_sheet2`, two rows) with Add to My Stations (Lucide `plus`, `pod_ic_rd_add`), or Remove from My Stations (`minus`, `pod_ic_rd_remove`) when the address is in `favourites.m3u`; (every station has it, also one started from Recently Played) and, under a hairline, Station Info (Lucide `info`, `pod_ic_rd_info`; `rd_sh_info`, below); toasts "Added to My Stations" / "Removed from My Stations" / "Could not save My Stations" (Back or the scrim closes the sheet first); a LIVE divider
(`rn_live`: 4 px capsule images (`rn_live_l`/`rn_live_r`, white 45 % at the outer end fading to 5 % at LIVE) either side of a small LIVE, shown while connecting or playing, hidden when paused); one 64 px centred
button (`rn_stop` white rounded square while connecting or playing, `rn_play` triangle when stopped or paused: a tap while Paused resumes with `rd_resume`, as the mini bar's play does; the mini bar shows the same Stop square, `mb_stop`). `btn_fav`, `btn_prev`, `btn_next`,
`rn_station`, `rn_info`, `rn_elapsed` stay in the asset hidden and insensitive. The line under the name: error "Can't play:
reason"; Connecting…; Paused; Stopped; playing: "Country · CODEC 128k" (the directory's words; no stream title yet). No volume slider (the local page has none) and no elapsed time. Preview: `tools/preview_radionp.py`.
A 500 ms page timer refreshes the labels only while the screen is lit and the page is on top and writes a label only when its
text changed. No star anywhere; the file is read when the sheet opens and the My Stations list again only when `rd_serial` moves. The page owns no playback: closing it leaves the station playing.

## Station Info

`ui/m1plus_radioinfo.bin` (`patch/radioinfo.c`, `sinfo_open`, called by the Now Playing sheet's Station Info row after the sheet closes): a plain text page built like Release Notes (`patch/relnotes.c`): the stock navbar (Back, the Now Playing disc, the small title "Station Info") over a stock list (`ri_listview` > `ri_scrollview` > `ri_view`, 400 px) holding one content view that the payload paints in its `EVT_AFTER_PAINT`, the texts wrapped once by the episode page's wrapper (`pd_lines`, `patch/pcwrap.c`: at spaces, a word longer than the line anywhere, CJK anywhere), so the stock scroll view does the dragging; black, neutral. Three hidden label styles carry the fonts (`label_head` 28 px white, `label_key` 14 px `#8E8E93`, `label_val` 18 px white); the navbar fade is hidden at rest and shown while scrolled. The heading is the station's name (at most three lines, an ellipsis ends a longer one), then label / value pairs, 16 px apart, x 16, 288 px wide, in this order, a pair with an empty value left out:

| Label | Value |
|---|---|
| Stream URL | the address, in full (up to 1,100 characters; 40 lines) |
| Logo URL | the favicon of the station's info (`rd_favicon`) |
| Country, Codec | the info's fields |
| Bitrate | the info's bitrate and " kbps" (omitted for 0) |
| Source | "Radio Browser" when the station has `#M1+:` info (it came from the directory or a saved copy of it), else "Imported" |
| Status | Connecting… / Playing / Paused / Stopped, or the engine's error text (`rd_error`, else "Can't play") |

The station is the one the engine has when the page opens (name, address and info are copied). Status is the last block: the 500 ms page timer (`sinfo_tick`, only with the screen lit and the page on top) reads the engine and, when the words changed, lays out that block again and resizes the content (the other blocks are made once). Text only: nothing is copied, shared or written. Back returns to Radio Now Playing (its sheet was closed by the tap); the disc is the usual Now Playing entry (`pod_on_player`). A page that is closing is replaced by a fresh one, its late `EVT_DESTROY` ignored (as `rn_open`); no station or a missing asset widget opens nothing. Tests: `radio/info_tests`, `radio/asset_tests`.

## Safety

- Entry points added: Radio's pages from menu, Extras and Pod taps; the mclStartPlayer hook
  above. No boot, paint or main-loop work.
- One timer outside a page: the engine's 500 ms timer (UI thread, `timer_add` at a tap in
  `rd_play`, gone when the radio is no longer connecting, playing or paused). It exists so standby and
  the DAC timer are held and stock's status is read while the station plays with no radio page open. The pages' timers
  (250 ms loading, 300 ms logos, 500 ms Now Playing) end with their pages.
- No process is started: no `fork`/`exec`, no files in `/tmp`.
- Imports added to `LIBC`, all already imported by demo: `strlen`, `strstr`, `strchr`, `strrchr`, `strncasecmp`.
- Stock calls added (`FUNCTIONS`, pinned prologues in `RADIO_PINS`): `stop_player` `0x4e08c4`,
  `set_outputchannel` `0x4d6f68`, `set_devicevolume` `0x4d6cf8`, `mclSetPcmMode` `0x5d6080`,
  `mclSetMute` `0x5d4dac`, `mclGetOutputWay` `0x5d45a4`, `mclSetDacPwr` `0x5d5c1c`, `mcl_tidalStartPlayer` `0x5d5184`,
  `mclStop` `0x5d244c`, `mclGetHciplayerStatus` `0x5d436c` (its load of byte `0xa0ab8b` pinned), `mclGetPlayStatus` `0x5d3640` (its load of word `0xa0abe4` pinned). Data:
  output selector `0xa05a10`, `dacoff_time` `0x97cae0`, `volume` `0x97cb10`, resume position `0xa0abc4`, running byte `0xa0ab8a`, hciplayer socket fd `0xa0abec`; the idle counter code
  (`on_wm_idle_status` `0x4cf04c..0x4cf06c`, `0x4cee3c`) is pinned.
- The volume is the DAC's own (wheel, volume dialog, screen-off wheel); no soft volume.
- `mclStop` blocks the calling thread until hciplayer answers (stock's `stop_player` does the same on the UI thread); the hook and the Stop tap call it.

## Validation limits

Tests (`test/pod/radio.py`) run the compiled payload under Unicorn: parsers, the whole state table cell by cell (`rd_step`), the
scenarios (start order and arguments, refusals, switch, double tap, error while switching, Stop from every state, the hook in
every running state, stall, end, time-out, pause, socket change, Wi-Fi off), the fetch options and answers, card
files, both pages and their taps. Stock's calls are mocks that set the flags stock sets. They do not run hciplayer, the network,
ALSA or the DAC. The probe (2026-11-03) proved on a device: the start recipe above plays HTTP MP3, HTTPS MP3 and HTTP AAC; Stop is
`mclStop()`; Wi-Fi off mid-stream did not auto-advance to a local track; without `rd_dac()` hciplayer is silent. Once, right after boot,
plain-HTTP MP3 failed in hciplayer with "Couldn't resolve name" while HTTPS worked; it did not repeat, hence the one restart on an early end.
Unverified on hardware:

- the status inputs of the table: that `mclGetHciplayerStatus` is 1 while a stream plays (Connecting to Playing), that an hciplayer error clears the running byte or sets status 1, and what pause (stock key) does to them;
- a local song chosen while the radio plays starting at once after the hook's `mclStop` (the earlier trace showed `set-nexturl` not switching a stream);
- standby, screen-off playback, Low Power (CPU1 offline) and CPU load of mp3/aac/opus decode;
- the USB output and every output change mid-stream (the Output changes section is emulated only: that the pair is the radio's whole path on a real switch, that hciplayer accepts a new stream right after `mclStop` and the output change); Bluetooth output, which is no longer refused (way 1; whether the stream reaches bluealsa, and the stutter beside Wi-Fi, are device checks);
- HTTPS to the directory and to stations (clock, CA bundle); the CSV answers of the live service;
- the hardware Back key on the stations page (as the Folders page: unverified);
- real favicons: ICO/SVG/huge/broken ones are skipped by design but unseen; the stretch of a non-square logo to its square; the Podcasts cover code run beside a podcast job (it is not checked from that side);
- a local song's position after the radio started: not kept (`mclStop` ends the song).

## Device checks

Not run. Radio-browser reachable with Wi-Fi on and off; the new root (My Stations, Recently Played, Radio Browser with Top Stations, By Country, By Genre and the credit under them; no magnifier on the root, My Stations or Recently Played, the magnifier on Radio Browser and below; an empty My Stations shows the grey hint (whole words on every line) and keeps the "..."; the My Stations "..." capsule [... | toggle | Now Playing]); each list, a country, a genre, a search,
Stations add/remove from Now Playing's sheet (Add to My Stations / Remove from My Stations, the list under it follows, also for a station started from Recently Played), restart; Import from Card with a `jazz.m3u`, a `.m3u8` and a `.pls` in `Radio` (sorted by file name, duplicates once, the files untouched, a second import says No new stations, an empty folder says No playlists in the Radio folder), a card without a `Radio` folder; Recently Played's "..." capsule [... | toggle | Now Playing], Clear Recently Played (the toast, the caption "No recently played stations" in whole words, the "..." still there, a playing station goes on and keeps the root's Now Playing row, with nothing running the row goes; nothing there after a restart); Now Playing's "..." sheet with Station Info under Add to / Remove from My Stations: the page with a directory station (all pairs, a very long stream URL wrapped in full and scrolling), an imported one (Source Imported, no Country / Codec / Bitrate), Status changing live (connect, pause, stop, a dead station's error), Back to Now Playing with the sheet closed, the Now Playing disc; then the radio itself:

1. Play and stop: an mp3, an aac and an https station reach "Country · CODEC" within a few seconds (not "No response" after 20 s: that means `mclGetHciplayerStatus` never says playing); the large button stops, a second tap plays again.
2. Station switch: tap another station while one plays, twice in a row, and while still connecting; one stream, the right name.
3. Local song while the radio plays: pick a song from the library, it plays at once without pressing Stop; then the radio again.
4. Wheel volume while it plays, and with the screen off.
5. Pause (hardware key): "Paused", then play: back to "Country · CODEC", no error.
6. Screen off for ten minutes: no standby, no silence; screen on: the page shows the real state.
7. Wi-Fi drop: Wi-Fi off mid-stream gives "No Wi-Fi" error (after about 10 s) and no local track starts; Wi-Fi back and Play works.
8. Wi-Fi off before starting: a tap on a station (every list), Retry and play on Radio Now Playing, the Home mini bar's play and retry, and Resume from Paused each say "No Wi-Fi" at once (no 20 s wait); with Wi-Fi back the same tap plays. Local music keeps playing when a station is tapped without Wi-Fi.
9. Radio Browser with Wi-Fi off: Top Stations, By Country, By Genre and a search say "No Wi-Fi" at once; Wi-Fi back and a tap on the caption loads. Switch the output (jack, USB) with Wi-Fi off while a station plays: "No Wi-Fi".
10. Directory retries: on a flaky connection the caption stays "Loading…" through up to two more tries (about 3 s) before "Directory unavailable. Tap to try again."; a tap fetches again; Back cancels at once. With the log file on the card (`m1plus-log`) a failure line shows the curl code. While a logo job runs a directory tap starts almost at once; during a podcast refresh it waits up to 20 s.
11. The empty My Stations hint and every caption break at whole words (not "i" / "mort" mid-word) on the device in English and one other language; icons: By Country is the globe-with-meridians `earth`, My Stations the `radio-tower`.
8. Multiple Speed: set it to 1.5x, play a station (1x), stop, play a local song (1.5x again); switch stations while at 1.5x (still 1x).
9. Home's mini bar while a station connects, plays, is paused and in error: the station's name and Connecting… / Live / Paused / the error, its logo (else the radio glyph), the next button greyed and dead (it stays, a tap does nothing, white again with a local song); the button is a Stop square while connecting or playing (a tap stops, never pauses), play when paused from outside (the key: a tap resumes) and after an error (a tap retries); a tap opens radio Now Playing; a local song never shows while the radio owns the output. After a Stop (bar or Now Playing) the bar keeps the station with "Stopped", the play glyph and the grey next; play connects the same station again; picking a song (or the hardware play key starting a track) brings the local track back.
10. USB audio: with a USB DAC as the output, play a station (sound from the USB DAC, its volume as for local music), switch stations, stop, play a local song; unplug the USB DAC mid-stream (see 12).
11. A dead station: an error with words within 20 s; Back and the page are never stuck; Back and re-entry (Now Playing row); with nothing running (idle, stopped, error) the row toasts "No radio is playing" and starts nothing.
12. Output changes mid-stream: switch 3.5 mm to 4.4 mm and back while a station plays (the same station restarts on the new jack and stays Paused, as local music does; press play: Connecting then "Country · CODEC", the volume of that output, no local track starts); the same while already paused (stays Paused, play resumes); plug a USB DAC mid-stream and unplug it (restarts Paused on each, play gives sound from the right output); a local song picked while the radio is Paused after a switch plays and stops the radio; standby and wake mid-stream (Paused after the wake); connect a Bluetooth headset mid-stream (the station restarts on it and stays Paused, stock's old track does not start; press play: sound in the headset) and disconnect it (back on the jack, Paused); unplug headphones mid-stream (Paused). Bluetooth output: with a headset connected, play a station (sound in the headset, no Error; pause, resume, Stop, previous / next); with Wi-Fi on 2.4 GHz and again on 5 GHz, listen for stutter.
13. Logos: on a card without `Radio/`, Radio Browser logos appear and `Radio/.logos/` is made; the Home mini bar shows a station's logo shortly after a busy download ends. A full or locked card: once a marker write fails, no new logo downloads start (the radio glyph stays), cached logos still show, nothing downloads again and again.

