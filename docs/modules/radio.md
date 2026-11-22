# Radio

**Sources:** `patch/radio.c` / `radio.h` (parsers, card files, playback state machine, directory
worker), `patch/icy.h` / `patch/icy.c` (read-only hciplayer ICY metadata tap), `patch/radiopage.c`
(stations page), `patch/radionp.c` (Now Playing), `patch/radioinfo.c` (Station Info);
`build_radio_page`, `build_radionp_page`, `build_radioinfo_page` in `tools/pod_ui.py`; hooks
`START_PLAYER`, `SAVE_STOP`, `SAVE_START`, `AUTOCHANGE_SITE`, `NOTICE_SITES` in `tools/pod.py`;
`ICY_CALLS` in `tools/mod_player.py`; pins `RADIO_PINS` in `tools/pod_pins.py`.

Internet radio: My Stations (one saved list, with Import from Card), Recently Played and the
[radio-browser.info](https://api.radio-browser.info) directory (top stations, countries, genres,
name search) on one stations page, plus a Now Playing page of its own. Station logos come from the
directory's `favicon`. The parsers and the favourites file follow q2-pod's `patch/radio.c` (MIT);
the playback path is ours: **stock's hciplayer plays the stream**, so the DAC, wheel volume, pause
and screen-off playback are stock's own.

## Entries

Radio is menu item 22, hidden by default; Extras lists it in Library between Podcasts and Search.
The Pod has no Radio row: its main menu never opens a page of ours. The kill switch
(`/mnt/mmc/m1plus-off` or `/mnt/data/m1plus-off`, `home_off`) is read by the menu entry and, only
while the radio owns the player, by hooks 16, 36 and 37 ([Hand-over](#hand-over)); with it they run stock.

## Stations page

One window with the Folders page's structure (glass navbar, large title, rows in `view_grid`).

| Level | Rows |
|---|---|
| Radio | Now Playing (while a station is up or Recently Played has an entry), My Stations, Recently Played, Radio Browser |
| Radio Browser | Top Stations, By Country, By Genre; ends with the grey caption "Stations from radio-browser.info" (the search results end with it too, no other level) |
| Countries | the A-Z list ([songs](songs.md): rail, section headers, pinned band), every country with stations, no count |
| Genres | name and "N stations" (the 60 most used tags) |
| My Stations | the station list (below) |
| Recently Played | the last 10 stations, newest first, in the station list |
| Search | the page's own field and pad; the action key fetches `byname` (one request per OK, no live search) |
| Caption | Loading…, No Wi-Fi, Set the date first, "Directory unavailable. Tap to try again.", No stations; over an empty Recently Played "No recently played stations"; over an empty My Stations "Add stations from Radio Browser or import .m3u files from the card." (the level's "..." stays, Back goes to the root) |

- **Now Playing row:** opens Radio Now Playing while a station is connecting, playing or paused.
  Otherwise it toasts "No radio is playing" and starts nothing, not even the last played station.
- **Captions** are 18 px grey, word-wrapped (every language fits five lines). A failure caption
  (No Wi-Fi, Set the date first, Directory unavailable) is a button that fetches the level again.
  No stations is final.
- **Back** stops a fetch, returns to the level a caption covers, then goes up a level; at the
  root it closes the page. Each level keeps its scroll offset. The magnifier enters Search from
  Radio Browser or a level under it.
- **Station list modes:** Top Stations, a country's or genre's stations, My Stations, Recently
  Played and search results use the Albums page's list and grid ([albums](albums.md)). The choice is
  one file, `/mnt/data/m1plus/radio-view` (`1` grid, otherwise list). The navbar toggle shows on the
  online station levels with rows in view (never on the root, Radio Browser, countries, genres, My
  Stations or Recently Played, whose "..." card has Grid and List). It shows the other mode's glyph; a
  tap or a card row keeps the first visible station. List rows are 64 px (52 px logo, name, "Country · CODEC 128k"); the
  grid is two columns of 144 px covers. A station without a logo gets a grey tile with the radio
  glyph.
- **Navbar:** the magnifier shows only on Radio Browser, its countries, genres and the online
  station lists (Top Stations, a country's, a genre's); never on the root, My Stations or Recently
  Played. My Stations and Recently Played have the "..." alone on the 214 slot (the capsule's left
  cap, as the Artists page) and no toggle; it opens the shared floating view-sort card
  ([albums](albums.md) "View sort card", `rp_card`), right edge and width as there.
- **My Stations** lists `favourites.m3u` in file order; new stations are appended. Add to and
  Remove from My Stations are on Now Playing. The level's "..." card has, top to bottom, **Select**
  (with a station and the mode's widgets), **Sort by Name** (with two or more; a one-shot action, not
  a ticked sort), **Add by URL** and **Import from Card** (slots 6..9), a hairline, then **Grid** and
  **List** (tick on the current one; only with rows in view). A long
  press on a station (`rowmenu_hold_start`, list or grid) opens a one-row sheet, **Remove from My
  Stations** (toast "Removed from My Stations").
- **Select** is the shared select mode ([select mode](selmode.md)): Back becomes the x, Select All,
  a mark per row (list) or cover (grid), one Delete pill (`rd_bar`, `rd_del`). Delete asks "Remove N
  stations from My Stations?" and then `rd_fav_remove` takes out, per marked row, the file row of
  the same name, address and info and the same occurrence of them (an unmarked twin stays). A failed write
  toasts "Could not save My Stations" and the mode stays. A file replaced whose folder sync failed
  (`m1_card_write` 1) counts as written. A list read again (Now Playing's sheet changed the file) ends the mode.
- **Sort by Name** rewrites the file in `cc_name_cmp` order (stable, info kept). A file already in
  order is not written.
- **Add by URL** is the Sign In page's card ([subsonic](subsonic.md)): two 48 px rows, Stream URL and
  Station Name, under a navbar with Now Playing as the lone disc. The page's one `kb_field` has no fill
  and its text at x 0; the search capsule's fill and magnifier are `rd_capsule` under it, and
  `rp_field_at` moves the field onto the capsule (x 48) or onto a card row (x 24, 6 px down), with its
  clear button at its right end (`keyboard_refocus` sets the text room). The row not typed in shows
  its value (`rd_add_v<i>`, cut with an ellipsis) or its grey name (`rd_add_h<i>`). A tap on the name
  row goes on as Next; a tap on the address row goes back to it, keeping the typed name. A name
  left as the old host follows a new address. First the address: the Sign In
  page's field (English, no capitals, starts at `http://`, up to `KB_MAX_LONG` bytes). Next is dimmed
  until it is an address `rd_play` takes (`rd_playable`: `http://` or `https://`, no `|` or `}`)
  with a host (after any `user@`; `[v6]` in brackets) and no space; `rp_url_host` parses it once for
  this check and for the name's start (the host alone, an IPv6 one without brackets). Then the name, which starts as the
  host; Done is dimmed while it is empty. `rd_fav_add` appends the station with no info.
  Toasts: "Added to My Stations", "Already in My Stations" (same address), "My Stations is full" (300
  stations, or a file that would pass `RD_FETCH_MAX`, the most read back), "Could not save My Stations". Back leaves with nothing written.
- **Import from Card** reads every `.m3u`, `.m3u8` and `.pls` in `/mnt/mmc/Radio` (at most 64
  files) and appends the stations not yet listed, up to 300, writing the file once. The user's
  files are never modified, so importing again adds nothing. Toasts say "Added N stations" / "Added 1 station", or why not ("No new stations", "No playlists in the Radio folder", "Stations is full", "Could not
  save Stations").
- **Recently Played**'s "..." card has **Grid**, **List** (with rows in view), a hairline and
  **Clear History** last, in red (slot 9 retexted, `VS_TAIL`; toast "Cleared Recently
  Played", or "Could not clear Recently Played" and the list stays); it keeps the root's Now
  Playing row if a station is running, else clearing the history clears "last played".

The UI says "My Stations"; the file keeps q2's name `favourites.m3u`.

## Directory

`rd_fetch` runs one libcurl worker, ended by Back through a cancel flag. Requests go to
`https://all.api.radio-browser.info` with the Podcasts CA bundle, 10 s to connect, 30 s in all,
256 KB cap (a cut answer is used up to its last whole row). Shared request facts are in
[network](network.md).

- **Guards**, in order: Wi-Fi, a valid clock, the CA file. The radio's own logo job is asked to
  end first. A podcast refresh, search or art job is never cut short (the page waits about 20 s,
  then shows "Directory unavailable"). A podcast download is no job and runs beside it.
- **Retries:** a network or TLS failure or HTTP 5xx is tried up to twice more, 1 s then 2 s later,
  each on a fresh handle so the round-robin name can reach another mirror. A 4xx, the size cap
  and a cancel are final. With the opt-in log `/mnt/mmc/m1plus-log`, a failed fetch is logged.
- **Endpoints** are CSV, not q2's `/m3u/...`, because the m3u answer has no country, codec or
  bitrate: `topvote/100`, `bycountrycodeexact/CODE`, `bytagexact/TAG`, `byname/TEXT`, `tags`,
  `countries` (all, a row with no stations dropped), each station list ordered by votes, 100 rows
  (`tags`: the 60 most used), broken hidden. The parser reads by
  header and prefers `url_resolved`.
- Lists hold at most 300 rows; names are cut at 120 bytes.

## Card files

| File | Contents |
|---|---|
| `/mnt/mmc/Radio/favourites.m3u` | My Stations: `#EXTM3U`, per station `#EXTINF:-1,NAME`, optional `#M1+:country<TAB>codec<TAB>bitrate`, the address. Rewritten whole and atomically; never when it would hold over 300 rows |
| `/mnt/mmc/Radio/*.m3u`, `*.m3u8`, `*.pls` | the user's own playlists, read only by Import from Card; `.pls` `FileN=` / `TitleN=` match by N |
| `/mnt/mmc/Radio/.logos/<hash>.jpg` | a station's logo (hash of its favicon address), at most 192 px; `<hash>.no` means no picture to be had; past 400 files the folder is emptied |
| `/mnt/data/m1plus/radio-recent` | the last 10 stations, newest first; a station played again moves to the front |

## Station logos

A 300 ms page timer looks at the rows in view and one row beyond them, only with the screen lit,
the page on top and the list still. It decodes a made logo into its tile, and starts the logo
worker for the first row without one. The worker (one job at a time, never beside the directory
fetch or a podcast job) fetches the favicon, shrinks JPEG and PNG through the Podcasts cover code
and renames the result into place. Other formats, pages, HTTP errors and oversized answers leave
`<hash>.no`; a card that refuses the marker stops new logo downloads for the session. Radio Now
Playing and the mini bar show the same logo.

## Playing

`rd_play` refuses addresses that are not `http://` or `https://`, or that contain `|` or `}`
(hciplayer splits its fields on them). It copies the list (previous and next step along it), stops
stock's player if the radio is not already running (local music holds the PCM), then starts.

The start (`rd_begin`) does what stock's own start does, and was proven on a device for HTTP and
HTTPS MP3 and HTTP AAC:

1. Ready the output as stock does. The built-in DAC also needs power, PCM mode, mute off and the
   device volume, otherwise hciplayer is silent. A USB DAC keeps its own power and volume.
   Bluetooth is readied by the output selector alone, and the volume is the headset's.
2. If stock's Multiple Speed is not 1x, send speed 1x (a live stream plays at 1x). The mode is
   never written, and is sent back after the stop on every transition to not running. A podcast's
   speed override writes the same variable and restores its own original; the radio only reads it.
3. Make the start not ask the play queue, send the URL, then unmute again.

**Stop, not Pause:** a live stream cannot hold a position, so Stop is `mclStop()`, which waits for
hciplayer's exit reply and is safe in any state. While playing, live ICY stream titles show on Radio Now
Playing, the mini bar and the lock screen ([ICY metadata](#icy-metadata)).

### ICY metadata

Stock hciplayer already requests `Icy-MetaData: 1` on both HTTP (`stream/http.c`) and HTTPS
(`libavformat/http.c`). A read-only tap in `patch/icy.c` (`tools/mod_player.py`, `ICY_CALLS`)
hooks two pinned calls — MPlayer's `mp_msg("\nICY Info: %s\n", ...)` (`0x4be4d0`) and FFmpeg's
`av_opt_set(..., "icy_metadata_packet", ...)` (`0x5020cc`) — copies the raw packet into
`/tmp/m1plus-icy` (`icy_record`, `patch/icy.h`), and always forwards to the stock function unchanged:

- **Only while radio plays:** `rd_begin` writes a fresh mark (`ICY_MAGIC`, `seq = 0`, monotonic
  `gen`); stop, error, local handover and `rd_icy_boot` (called from `home_boot`) unlink it. Local
  playback pays zero writes and the kill switch skips publishing.
- **Reading and parsing:** `rd_poll` reads `/tmp/m1plus-icy` (retrying on `seq != seq_end`,
  ignoring stale `gen` values) while connecting or playing. `rd_icy_parse` extracts `StreamTitle`
  (preserving unescaped apostrophes, falling back from invalid UTF-8 to CP1252/Latin-1, ignoring
  empty/placeholder strings and matches to the station name) and splits `"Artist - Title"` /
  `"Artist – Title"` into Artist, Title and `"Artist – Title"` (en-dash). Packets with other ICY
  keys and no `StreamTitle` keep the current track; an empty `StreamTitle=''` clears it back to the
  station caption / "Live". State words (`Connecting…`, `Paused`, `Stopped`, errors) always take
  precedence over track metadata.
- **Layout, as a song:** `rd_meta_head` / `rd_meta_sub` give the two lines of Radio Now Playing,
  the mini bar and the lock screen. Split metadata puts the title on top and the artist under it;
  unsplit metadata keeps the station's name on top with the text under it. Outside `RD_PLAYING`
  both fall back, so the station's name and the state's words come back.

### What the tick reads

`rd_poll` is the engine's own 500 ms timer (2 s, `RD_DARK_MS`, while the screen is off, so an end is
read up to 2 s late), alive only while a station is connecting, playing or paused. It holds standby and auto power-off (paused lets the player sleep, as paused music does)
and reconciles with stock rather than trusting its own state. It reads hciplayer's running flag,
its socket (gone or changed means hciplayer restarted), stock's play status (stopped, playing,
paused) and whether hciplayer answers `playing`. The first 1.5 s after a start are not read.

### State table

States: **Idle**, **Connecting**, **Playing**, **Paused** (stock's pause), **Error** (words in
`rd_error`), **Stopped**. Running means Connecting, Playing or Paused. The table is `RD_TABLE`, a
pure function `rd_step(state, event, tries, wifi)`.

| Event | Idle | Connecting | Playing | Paused | Error | Stopped |
|---|---|---|---|---|---|---|
| Play (tap, station switch, previous / next) | Connecting | Connecting, restart | Connecting, restart | Connecting, restart | Connecting | Connecting |
| Bad address ("Unsupported address") | Error | Error, stop | Error, stop | Error, stop | Error | Error |
| Start failed ("Player not ready", "Could not start") | Error, stop | Error, stop | Error, stop | Error, stop | Error, stop | Error, stop |
| Stop | stays | Stopped | Stopped | Stopped | Stopped | stays |
| Local track starts | stays | Stopped | Stopped | Stopped | stays | stays |
| Reroute (output changed) | stays | Connecting, restart | Connecting, restart | Paused, restart | stays | stays |
| Reroute paused | stays | Paused, restart | Paused, restart | Paused, restart | stays | stays |
| Heard (hciplayer playing) | stays | Playing | stays | Playing | stays | stays |
| Paused (stock status) | stays | Paused | Paused | stays | stays | stays |
| Resumed | stays | stays | stays | Playing | stays | stays |
| Ended (flag cleared, socket gone) | stays | Connecting once per play, retry after 1 s; else Error "Could not connect" | Error "Playback ended" | Error "Playback ended" | stays | stays |
| Stall (not playing for 10 s) | stays | stays | Connecting once per play; else Error "Stream stalled" | stays | stays | stays |
| Time-out (Connecting 20 s) | stays | Error "No response" | stays | stays | stays | stays |
| No Wi-Fi | Error | Error, stop | Error, stop | Error, stop | Error | Error, stop |

- **Start with Wi-Fi down** is the No Wi-Fi event: no attempt, no 20 s wait, and no stop, so local
  music keeps playing. The list and position are kept, so a tap after Wi-Fi returns starts normally.
  Ended, Stall and Time-out with Wi-Fi down also give "No Wi-Fi".
- **Restart allowance:** one per play; it resets on a new Play and after 60 s of playing. A
  Reroute never counts against it.
- A hardware or stock Stop key while the radio plays looks like Ended (same flags) and shows
  "Playback ended"; the Play button retries.
- If stock says stopped while hciplayer still says playing, the audio wins and nothing is stopped.
- Screen off, a closed page and sleep change nothing: the engine timer runs, pages only read.
- Invariants (tested): Stop works from every state and is idempotent; every running state has
  an exit; a play tap works from every state; local playback always wins and never waits for the
  timer; a station switch is a stop then a start, never two streams.

## Output changes

Stock stops and restarts its player around every output change (jacks, USB, Bluetooth, standby
wake). Hook 18 ([payload](payload.md)) turns that pair into the radio's Reroute event:

- **Stop half:** with a station running, only `mclStop()`; stock's saved status and notifications
  are skipped, so nothing of stock's restarts later. Otherwise stock's function.
- **Start half:** with a station running, the same station restarts on the new output. Stock
  restarts local music paused after a switch (ear safety), so a station is restarted and left
  Paused (Reroute paused). The plain Reroute keeps Connecting and Playing playing and re-pauses a
  paused station.
- Bluetooth is a Reroute like the jacks. After a standby wake the station restarts at once,
  probably before the network is back, so the retry and error words apply.
- A stop with no start (Bluetooth linking) leaves the state Playing; the next tick reads the dead
  stream as Ended. A reconfiguration of hciplayer while a station plays shows as Ended.

## Hand-over

Hook 16 ([payload](payload.md)) intercepts every local track's start. With the radio running it sends
`mclStop()`, sets Stopped and resumes stock, with no widget or timer call (it may run off the UI thread).
Our own play paths reach the same function, so they stop the radio too.

Hook 36 keeps the opposite direction out: `mcl_tidalStartPlayer` leaves stock's play type and position
on the local queue, so when hciplayer exits (a dead station, an ended stream) stock's idle pass
(`mclAutoChange`) takes it for the local track's end and would call `mclNextSong(1)` and play the next
queue song, one per failed station. `rd_auto_change` skips that call while the radio owns the player
(a station started and no local track since, in any state but Idle); the tick reads the end itself.

Hook 37 keeps stock's failure dialog out: hciplayer touches `/tmp/notfile` (or `/tmp/notsupport`)
when a stream does not open, and home's timer turns the file into a modal "File Not Found" dialog. A
retry or a new tap wrote the next one while the first was up, and the nested dialogs could stick.
`rd_notice` removes the marker and reports it absent under the same condition as hook 36; the radio
shows its own error words. A marker left while stock's timer skipped it (no valid play position) is
removed when a local track takes over (hook 16, not with the kill switch), so it never reads as that track's error. Both hooks
run stock with either kill switch file present (`home_off`).

## Now Playing entries

While a station connects or plays (a stopped radio is not active, whatever Recently Played holds),
every Now Playing entry opens Radio Now Playing: the navbar
buttons and mini bar card of our pages, the Home menu's row, and for stock pages hook 10
([payload](payload.md)). A page that is closing is replaced by a fresh one. A failed open opens
stock's player. The Home mini bar keeps a stopped station: it shows "Stopped" with the play glyph,
a tap plays the same station again, and the card opens Radio Now Playing. Tracks the Pod starts
itself open its own screen (local music stops the radio first).

## Radio Now Playing

`ui/m1plus_radionp.bin` is the Now Playing page's layout for radio:

- grabber, a 264 px art card (the station's logo on white, else a grey card with the broadcast
  glyph), the window tinted from the logo (neutral grey without one);
- two lines: the track title over its artist while split ICY metadata plays; else the station's
  name over one grey line: "Can't play: reason", Connecting…, Paused, Stopped, unsplit ICY text,
  or "Country · CODEC 128k";
- a round "..." that opens a two-row sheet: **Add to My Stations** / **Remove from My Stations**,
  and **Station Info**; every station has the Add row, also one started from Recently Played.
  Toasts: "Added to My Stations", "Removed from My Stations", "Could not save My Stations";
- a LIVE divider while connecting or playing, and one 64 px button: a white Stop square while
  connecting or playing, a Play triangle when stopped or paused (a tap while Paused resumes).

No volume slider, no elapsed time and no star. A 500 ms timer refreshes the labels only while the
screen is lit and the page is on top. The page owns no playback: closing it leaves the station
playing.

## Station Info

`ui/m1plus_radioinfo.bin`, opened by the Now Playing sheet's Station Info row. A plain text page
built like Release Notes: the stock navbar over one content view the payload paints, black and
neutral. The heading is the station's name, then label / value pairs in this order, a pair with
an empty value left out:

| Label | Value |
|---|---|
| Stream URL | the address in full |
| Logo URL | the station's favicon |
| Country, Codec | the directory's fields |
| Bitrate | with " kbps", omitted for 0 |
| Source | "Radio Browser" when the station has `#M1+:` info, else "Imported" |
| Status | Connecting… / Playing / Paused / Stopped, or the error text |
| Title, Artist (or Now Playing) | live ICY track metadata while playing (split into Title and Artist when `"Artist - Title"`, else Now Playing; omitted when none) |

The station is the one the engine has when the page opens. Status and live ICY metadata update while
the page is open. Text only: nothing is copied or written. Back returns to Radio Now Playing.

## Safety

- The engine's 500 ms timer (UI thread) is the only timer outside a page; it exists only while a
  station is running, so standby and the DAC timer are held with no radio page open.
- No process is started and no file goes to `/tmp` other than the logo's temporary download and
  `/tmp/m1plus-icy` while a station runs.
- Stock functions called are pinned in `RADIO_PINS` with a stock fallback; the two hciplayer ICY
  calls are pinned in `tools/mod_player.py` and always call stock.
- The volume is the DAC's own; there is no soft volume.
- `mclStop` blocks the calling thread until hciplayer answers (stock's own stop does the same).

## Limits

- Media keys outside our pages act on stock's player; a hardware Play/Pause while the radio plays
  may start a track, which stops the radio.
- Non-ICY metadata (e.g. chained Ogg Vorbis/Opus comments or HLS ID3 tags) is not read.
- A local song's position is not kept after the radio started: stop ends the song.
