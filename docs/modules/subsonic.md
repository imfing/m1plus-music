# Subsonic (Navidrome)

**Sources:** `patch/sbnet.c`, `patch/sbparse.c`, `patch/sbapi.c`, `patch/sbdl.c`,
`patch/libsrc.c`, `patch/sbsrc.c`, `patch/ndroot.c`, `patch/ndserver.c`; builders
`tools/pod_nd.py`, `tools/pod_ndserver.py`.

Subsonic (Navidrome, Gonic, Airsonic and any Subsonic-compatible server) is a **library
source**: the root page is a menu, and the library pages are our own Albums, album, Artists,
Playlists, Songs and search pages, showing the server's music beside the card's. Strings say
"Subsonic"; card folders and files keep the Navidrome names. Downloads go to the card
(`/mnt/mmc/Subsonic`) and play offline. Navidrome support began as a pull request by Gaurav Mishra, with work by shivaluma (MIT); the code was rebuilt since.

Playback streams the server's original file (`format=raw` only: no transcoding, no quality
setting), so sample rate and bit depth are the file's. DSD tracks never stream: they play only
after a download.

## What the user sees

- **Root page** (`ACT_SUBSONIC`): a large title and a grey status line: a 14 px glyph plus "Synced
  5m ago" / "Synced just now" / "Not synced yet". The glyph is a check circle when connected,
  the Wi-Fi spinner with "Syncing…" while a sync runs (then "Updating library… 1200/2431",
  "Loading covers… 300/812", "Loading artist images… 40/190" during the Background fill, and
  "Downloading 12 songs" or "12 downloads waiting"), and a plug when offline ("Not Connected" when the server does not answer). The status is
  re-read every 4 s. Rows: Albums, Artists, Songs, Playlists, Favorites, Downloaded, then a grey
  footer with the song total. The large title collapses like every large-title page.
- The navbar is [Search | "..." | Now Playing]; Search shows only with `LS_CAP_SEARCH` and a
  saved server. The "..." opens the shared view-sort card ([albums](albums.md)) with **Sync Now**
  (no question; a refusal is the toast "Connect to Wi-Fi first") and **Server Settings**. Signed
  out, the card holds Server Settings alone.
- **No server saved**: the list is hidden and an empty state shows "Not Connected", a grey line
  naming the supported servers, an **Add Server** pill (opens the Sign In page, then syncs) and a
  **Downloaded** pill, because downloads and their manifest stay on the card after Sign Out.
- **Server page**: URL (no "Server" prefix in any language), Username and Password (shown as dots), each opening the Sign In page on
  that row; **Sync Now** (shows Syncing… then "Synced just now"); **Sign Out** (red, asks first,
  returns to the root). Sync Now and Sign Out are hidden while no server is saved.
- **Sign In page** (the Join Wi-Fi Network design, [wifi](wifi.md)): one card of URL, Username
  and Password with our keyboard embedded; empty rows show a grey placeholder naming the row.
  The URL starts as `http://` (its clear button leaves that scheme); the password has an eye
  while one is being typed; an empty password keeps the saved one ("Leave empty to keep"), but
  one typed and emptied does not. Address and password are English-layout fields of up to 127
  bytes. The action key reads Next until the
  login is whole, then Sign In (dimmed while connecting).
  - Sign In validates the fields (`sba_conf_check`), then pings the server with that login
    (`sba_ping_try`) before anything is saved. Each ping has its own id and copy of the login, so
    a second sign-in while the first is in flight cannot save the wrong fields.
  - A 20 px line shows the spinner and "Connecting…" (40 s at most). On success the login is saved
    (the cache is cleared only if the server or user differ), the page goes back and a sync starts.
    On failure the line gives the reason (wrong user or password, "Can't connect to the server",
    certificate, clock never set, no Wi-Fi, a conf that cannot be written) and nothing changes.
- **Library pages** on the source: Albums (grid or list), album page, Artists (A-Z) and an
  artist's albums, Playlists (a mosaic of track covers when the playlist has none), Songs,
  Favorites, Downloaded. Their bars show only what `lib_src_t.caps` allows: no Cover Flow, no
  Select. Recently Added and Year orders sort by the album records' own creation time and year.
  Playlist tiles show the sync's `songCount` at once. An artist's albums show the album
  records' year.
- **Artists**: rows and the artist page use the library's artist layout. The picture is the
  server's artist image (`getArtists` / `search3` give a `coverArt` id `ar-<id>_<time>`),
  fetched like any cover and cropped square like a local photo. While it is on its way the row
  shows the placeholder with a spinner; a missing picture is the placeholder alone. The Play /
  Shuffle pills play the artist's songs through the All Songs record. The artist page has the
  88 px circle header once the picture is there and the plain header (no circle, no placeholder)
  while it is on its way or missing; the page switches in place. Until `getArtist` answers, the
  artist's albums come from `albums.idx` (by `artist_id`) and their tracks from the derived album
  files.
- **Search**: entry points are the Songs search button (all types), Albums "..." > Search Albums
  and Artists "..." > Search Artists, over the library's own search page ([search](search.md));
  `search3` does the matching with the server's
  rules (no pinyin or kana folding; no Playlists search, `search3` returns none). Results are 20 artists, 20 albums, 20 songs,
  no playlists. A request goes out 480 ms after the last key; a newer query is never overwritten
  by an older answer. An empty answer reads "No Results"; a failure shows its `sbs_message` line.
  Recent searches use their own `<cache>/search-history` (not a Settings Files row).
- **Row marks** (grey): on the album page the downloaded disc, a progress ring (12 steps) and the
  DSD tag sit at the title's end; on Songs they lead the grey line. A running download draws a
  stop square over its ring, a waiting one a down arrow. Marks are not tappable (Cancel Download
  stays in the sheet) and there is no "Downloading" text. An undownloaded
  row offline dims its title.
- **Row sheet** (a track's "..."): Play Next, Play After, Download / Cancel Download / Remove
  Download, Favorite / Undo Favorite (the server's star) and Get Info ([songinfo](songinfo.md),
  read from the cache).
- **DSD confirm**: tapping an undownloaded DSD track (row, Play, Shuffle, Play Next / After)
  asks "Download to Play?" ("DSD tracks play from the card. <title>, <size> MB."; a title over
  24 bytes is cut, an unknown size reads "?"). Cancel or Download; Download queues the file.
- **Download Album**: a server album page has no Select; its "..." opens a card with **Download
  Album**. It queues each track that is neither on the card nor waiting (DSD included; a failed
  one is retried), then toasts once: "Downloading n songs", "Already downloaded", the first
  refusal's message, or "Downloading n, queue full" ("Download queue is full" when none fit).
  While the page has no tracks the "..." is insensitive.
- **Server playlists** use the local playlist page, and an artist's All Songs the local artist's
  songs page (no A-Z, no Search). The Songs footer count shows once the paged list is complete.

### Playback-side pages treat a server track as a source track

A server track (streamed or downloaded; its `REC_ID` is in the queue map, `sba_rec_track`) is
never treated as a local one. Its `REC_PATH` is a stream address carrying the login token: it is
never shown, hashed, looked up or used as a key.

- **Cover**: `sba_rec_cover` gives 1 with the cached file, 0 asked, -1 none. Now Playing (which
  decodes the cached 168 px file into its own 264 px bitmap, as stock draws only
  `/tmp/coverpic.jpg`), Queue, mini bar, lock screen, timed cover page, Vinyl and the Pod cover
  use it, never the library's album key (a local album of the same name would show its cover).
  Pages ask again on their own ticks while it is pending. The main menu's cover pane skips a
  server track (the rotation shows) instead of a same-named library album. Now Playing keeps the
  previous cover until the new one is decoded.
- **Favorite**: Now Playing's star is the server's (`ls_favorite`); stock's handler is kept away
  with `RET_STOP` because it would write the stream address and token into the local `myfav`.
  The star follows the cache, so a refused star puts itself back.
- **Find Cover & Lyrics** is dimmed and refuses to open ([onlineart](onlineart.md)): a stream has
  no album key or file to write beside. Lyrics show what stock loaded (nothing for a stream).
- **Queue page**: `qp_stream` tests the player's class word for stock streams; a server queue is
  opened from a list class, so it is this page's.
- **Info page**: File Size and Location show the server size (`sba_rec_size`) and address, never
  the stream address.
- **Recently Played**: `recent_note` skips a record whose path is a stream address, so the
  credential never reaches the card.
- **Stock's play history**: `add_playrecord` would write the stream record (with the token) into
  `recentplay` and `oftenplay`. `jal sbs_play_record` ([payload](payload.md) hook 28) skips a
  record whose path is an http address (the test is the path alone) and calls stock for
  everything else, and always with the kill switch.
- **Reboot**: stock tests the saved playing file with `access`, which a stream address fails, so
  a stream does not resume; the queue map is memory only.

## Architecture

```
sbnet  ->  sbparse  ->  sbapi / sbdl  ->  sbsrc (lib_nd)  ->  pages, through lib_src_t
 HTTP,      JSON to      cache files,      records, queue,      Albums, album, Artists,
 auth, JSON records      metadata worker,  row state, row       Playlists, Songs, search,
 walker                  download worker   actions              row sheet
                                                                ndroot.c, ndserver.c (root, Server)
```

| File | Content |
|---|---|
| `patch/sbnet.c` | HTTP (`sbn_http`, a request of [network](network.md)), salted-token auth, URL building, JSON walker, MD5, `sbn_download` |
| `patch/sbparse.c` | `sba_parse_*` (pure: no network, no files) |
| `patch/sbapi.c` | conf, guard, cache files, the metadata worker, requests, status record, the queue map, covers |
| `patch/sbdl.c` | download worker, manifest `dl.idx`, queue `dlq.idx`, stall and free-space rules |
| `patch/libsrc.c` | `lib_src_t` (the seam) and `lib_stock`, the stock library as a source; shared page helpers |
| `patch/sbsrc.c` | `lib_nd`: records from `sba_*`, the queue builder, row state, row-menu actions, `ls_dsd_confirm` |
| `patch/ndroot.c`, `patch/ndserver.c` | root page and empty state; Server page, Sign In page, Sync Now, Sign Out |
| existing pages | `src` plumbing in `albums.c`, `albumpage.c`, `artists.c`, `songs.c`, `playlists.c`, `songops.c`, `rowmenu.c`, `search.c`, `songinfo.c` |

Entry points take a source argument (`albums_open_src`, `album_open_src`, `artists_open_src`,
`songs_open_src`, `playlists_open_src`, `search_open_src`); the existing entries pass NULL, the
unchanged stock path. Asset pages: `m1plus_ndroot`, `m1plus_ndserver`, `m1plus_ndlogin`.

### The seam

**One `lib_src_t` seam; pages hold a pointer.** A page keeps `const lib_src_t *src` (NULL =
stock) and calls it where it called a stock query. Separate pages for sources would be copies of
500 to 1,650 line pages that drift from every later restyle. Cover Flow keeps its stock code and
a source page hides its entry through `caps`.

| Member | Use |
|---|---|
| `list`, `play`, `cover`, `seconds` | the deque of records, play, the cover file, a row's seconds |
| `row` | download state, DSD, favourite, offline; read while painting, from memory only |
| `act`, `queue_row` | Download / Delete / Cancel / Favorite (Download All takes the page's list); Play Next / After |
| `gen`, `gen_rows` | change counters the page's timer reads; `gen_rows` moves only with the lists |
| `rec_id`, `playing`, `count` | the server id; the playing marker; a row's list size before its list is cached |
| `state` | `LS_ST_READY` / `LOADING` / `FAILED` / `OFFLINE`; NULL = ready |
| `caps` | `LS_CAP_COVERFLOW`, `LS_CAP_SEARCH`, `LS_CAP_SELECT`; `lib_nd` has `LS_CAP_SEARCH` only |
| `dl_rows` | how many leading rows of Downloaded are still to come |

Source records have a synthetic `REC_ID` <= -3 (-2 is an artist's All Songs row), `REC_PATH`
`nd://<id>`, and one string at `+0x28` with the row's own data, so a record is enough to play,
download, star, draw extras or find its cover even after a page copied it. Records stay
stock-shaped, so painters, sorts and hit tests are shared. Pages skip `cc_build_add` and the
duration table when `src` is set.

### Shared source-page helpers (`patch/libsrc.c`)

- `ls_cover_poll` / `ls_cover_tick` / `ls_cover_end`: one 250 ms timer polls the pending covers
  of every source page (top window, screen lit); gives up after `LS_COVER_POLLS` 1200 asks.
- `ls_spin`: the Wi-Fi page's 14 px spinner, one timer, used for loading and "Connecting…".
- `grid_spin_*`: the grey cover spinner drawn on a tile that is still downloading.
- `gen_rows` / `ls_gen_rows`: list changes without download steps; Songs, Albums, Artists and
  Playlists read their list again only on it. All gen timers run at `LS_GEN_MS` 500 ms.
- `ls_same_list`: a page that reads again and finds the same rows keeps its tiles.

**Loading.** `state` is asked only when `list` returned no rows (cached rows always show at once).
While `LOADING` a page shows the tapped row's data and one spinner, nothing else, and keeps its
title and navbar. `READY` with no rows is the empty text; `OFFLINE` is "Connect to Wi-Fi first",
`FAILED` "Can't connect to the server". The Artists page does not read while the finger is down
or the list is flinging.

**Playlists scan.** The Playlists page reads every playlist for its mosaic and count
(`sbs_playlist_scan`) and asks the server only for one that is not cached; opening a playlist
refreshes it once per run.

**Wi-Fi off.** Browsing works from the cache. A request made offline returns `SBA_NOWIFI` and
toasts "Connect to Wi-Fi first". Downloaded tracks play; an undownloaded streamable row is dimmed
and its tap toasts. A stream that loses Wi-Fi is the stock player's problem.

**Sign Out** clears the cache, cancels every download (`sba_dl_cancel_all`) and stops the player
when it is on a server stream. **Music files and their manifest are kept**, so Downloaded still
works.

### Cache and requests

| Data | Fetched | Cached |
|---|---|---|
| Albums, Artists, Playlists, Favorites | the sync: root opens with a cache over 15 min old and Wi-Fi up, or Sync Now | `albums.idx`, `artists.idx`, `playlists.idx`, `starred.idx`, replaced whole (`getAlbumList2`, 250 a call) |
| An album's, artist's or playlist's tracks | when its page opens (cache first, refresh follows); an album's also from the Background fill | `al/<id>.idx`, `ar/<id>.idx`, `pl/<id>.idx` |
| Songs | the Background fill (`search3`, empty query, 100 a page); the Songs list also pages as it is scrolled | `songs.idx`, `songs.part` while paging |
| Covers | `getCoverArt` at 168 px (`SBA_COVER_PX`): visible rows, plus every album and artist picture after a sync | `covers/<hash of coverArt id>-168.jpg`; an empty file = no art |
| Album cover by id | with the sync | `albcov.idx` (per album: hashes of its id and cover id, its row) |
| Fill cursor | with the fill | `bg.txt` |
| Search | `search3`, 20 each | `search.idx`, `search-al.idx`, `search-ar.idx`, `search-history` |
| Downloaded tracks | no request | `dl.idx` and the files in `/mnt/mmc/Subsonic` |
| Star / unstar | at once | flag edited in place in `songs.idx`, `search.idx`, the album file; `starred.idx` replaced; all revert on a refusal |

**A track shows its album's cover.** `sba_track_cover(album_id, ...)` gives the ALBUM's file
through `albcov.idx` (a song's own `mf-<song id>_<time>` id differs from its album's
`al-<album id>_<time>` and would fetch one file per song) and asks for the album's cover only if
the file is missing; the track's own id is used only when the album is unknown or has no
coverArt. `albcov.idx` is written beside `albums.idx`, removed when it cannot be written, and
searched by bisection (16 bytes an album). Albums, artists and playlists keep `sba_cover_get`.

**Sync.** It needs only `getAlbumList2`. A refusal of the artists, playlists or favourites
list keeps that list's old file (or writes an empty one) and the sync still commits and starts
the fill. A login, certificate, Wi-Fi, network or storage error fails the whole sync.

**Requests** run on one detached metadata worker (a queue of 8: lists, covers, star, search; the
next request when full is `SBA_QFULL`; the fill runs on the same worker behind them). A list
asked for that did not appear is asked again 10 s later (1.5 s after a full queue), so a failing
server is not hammered; an answer with no rows is final. A cover does not move `sba_gen`
(`sba_cover_gen` does), or a grid would blank while it scrolls.

**Cache writes** are atomic (temporary file, then rename) and only the metadata worker writes
them; the UI thread never does. The cache keeps 4 MiB free. A star goes through a 32-entry
**star overlay** so the heart flips at once; the worker edits the files, asks the server and puts
the files back if it refuses. **`starred.idx` is the truth for every heart**: the page side holds
its ids as sorted 32-bit hash pairs (at most 3,000) and sets `starred` from them on every track
list read, so a song starred from another client shows a heart.

### Background fill

After the sync the same worker keeps loading metadata while nothing else asks for it, so pages
open on data instead of a spinner. It runs only with Wi-Fi, in stages kept in `bg.txt`:

1. **Songs.** `search3` pages appended to `songs.part` (append-only, one write and an fsync a
   page), ended by an empty page, a page that repeats the previous one's first song (the server
  ignores the offset), `SBA_MAX_TRACKS`, or a short page once the rows reach the sync's
   song total. A first page that is empty for a library with songs is a failure of the run. The
   end renames it to `songs.idx` and replays the last 16 stars onto it. **Derive:** `al/<id>.idx`
   for each album whose songs are all in the list (only when the row count equals the album's
   `songCount`), 16 albums a step, from an in-memory index of 8 bytes a song.
2. **Covers.** Every album's cover, one `getCoverArt` a step; files already there and empty
   markers are skipped. A cover that fails three times in a run is left for the next run.
3. **Artist pictures.** The same over `artists.idx` (at most 6,000).
4. **Done.** Nothing runs until the library signature changes (song count, seconds, album count
   and the newest album's creation time, stored in `sync.txt`) or `SBA_BG_MAX_AGE` (7 days)
   passes.

**Navidrome's stand-in picture.** For an artist or album with no art Navidrome answers 200 with
its own WebP placeholder, not 404. `sba_run_cover` takes a `RIFF....WEBP` body as "no art" (the
same empty marker as a 404). `artistImageUrl` is not used: Navidrome fills it for every artist.
A server that answers a stand-in as JPEG or PNG cannot be told from a picture; it is shown.

**Not used:** `getIndexes?ifModifiedSince` and `getScanStatus`: their meaning differs between
Navidrome, Gonic and Airsonic and they change with scans that changed nothing.

**Priority: the fill is low priority and yields to pages.** It runs only when no request waits,
one bounded step at a time, and a transfer in flight is cut off when a request arrives. It waits
while a download runs. One worker, no extra concurrency.

**Stops and resume.** Each step re-checks the cancel counter (Sign Out or a changed server clears
the cache, `bg.txt` and `songs.part` with it), the card (the 32 MiB floor) and the guard. Login,
certificate, full-card and storage errors end the run at once. Other errors pause 10, 20, 40, 60 s;
`SBA_BG_FAILS` 5 in a row end it. A picture whose answer is 404, a WebP, or a body that is no
picture leaves the empty marker at once; one that keeps failing is skipped after three tries (a
skip is progress); a request with no answer (`SBA_NET`) is never a skip. An ended run keeps its
state (`songs.part` is the page cursor, a half-written row is cut away), so the next kick
continues without fetching again.

### Downloads (`patch/sbdl.c`)

The shared request and file layer (`.part` + rename, Range resume, CA bundle, free-space floor,
the stall rule) is in [network](network.md). Subsonic's own behaviour:

- **One worker, a queue of up to 1024** (`SBA_DLMAX`; `SBA_QFULL` when it is full; the oldest
  waiting entry runs first). Rows wait in `dlq.idx` on the card (one `O_APPEND` write, no sync: a lost
  line is a download asked for again); memory holds only a slot a track (id, state, failure
  code). A full queue toasts "Download queue is full" (the play queue's "Queue is full" is
  another text).
- **The queue is the worker's** (`patch/m1job.h`). Slots in memory and `dlq.idx` are changed by
  the worker thread only. The UI thread posts ordered messages (add with the track's row, cancel,
  cancel all, resume) through `sbd_post`; the worker applies them in the order posted, also
  inside a transfer, so an add or cancel made mid-file is on the card within about a second.
  The last message posted holds. This is why the queue is not a shared state table: it rules
  out the races that model brings ([network](network.md)).
- What the UI reads is the slots with the unapplied messages laid over them (`sbd_view`), so a
  tapped row shows waiting, or gone, at once. `sba_dl_add` answers only what needs reading: the
  guard, the card, free space, a full queue (`SBA_MEM` when the box is full or no thread can be
  made). What the card refuses while the worker writes is reported as a failed transfer.
- **The queue survives a reboot**: the first use reads `dlq.idx` and every row whose track is not
  downloaded waits again, in the file's order. Nothing starts by itself: `sba_dl_resume` (the
  root's open, or its tick when the guard clears) or the next add starts fetching. Finished,
  cancelled and given-up rows are dropped when the queue drains.
- A `dlq.idx` that cannot be read is `SBA_STORAGE`, not a missing row: fetching stops and the row
  is kept. A cancel appends a line `-=<id>` first, so a cancelled track does not wait again after
  a restart; the last line for a track is the track's.
- **The worker stops at a failure that is not the track's** (no server, no Wi-Fi, clock,
  certificate, network, login, card, memory, full card): that track is `FAILED`, the rest stay
  waiting and the worker ends, so a lost Wi-Fi does not fail the whole queue and the device may
  go to standby. `sba_dl_resume` puts the stopped track behind the others. A failure of the
  track itself (404, not audio, a refused write) leaves it `FAILED` and the worker goes on.
- **Files**: `/mnt/mmc/Subsonic/<artist>/<album>/<nn> <title>.<suffix>`. The artist is the
  ALBUM's artist so a compilation shares a folder; `<nn>` is the track number (`<disc>-<nn>` from
  the second disc). Names are cut (64 bytes a folder, 100 the title), `/ \ : * ? " < > |` and
  control characters become `_`. An unknown file of that name is adopted, never overwritten; a
  name owned by another track gets ` (2)`. Names compare case-folded (exFAT folds), and the card
  itself is asked (`st_dev`/`st_ino`) before adopting, so a second track never adopts and later
  deletes the first one's file. Remove Download removes empty folders.
- **Cancel** of the running transfer drops its `.part`; a network fault keeps it for the resume.
- **Safe resume** (`sbn_download`; the shared range rules are in [network](network.md)): the first body byte saves a record `<part>.etag` (server,
  user, track id and the response's strong ETag; no strong ETag keeps no `.part`). A `.part` is
  continued only with that record: `Range: bytes=N-` plus `If-Range`, accepted only for a 206
  whose Content-Range starts at N, ends at the file's last byte and carries the recorded ETag.
  Anything else restarts from byte 0. A text, JSON or XML type, a redirect body or a wrong
  status is refused (`SBA_NOTAUDIO`); the finished file needs the announced length and a first
  byte that is not `<`, `{` or `[`. A resume that wrote nothing and got no usable answer keeps the
  `.part` and its record as they were.
- **Keep awake**: a successful add arms `nl_awake_tick` (see Keep awake below), so stock standby
  does not stop Wi-Fi mid-file.
- **Failure words** (`sbs_message`): "Storage unavailable", "Card is full", "Write failed",
  "Server error 503", "Song not found on the server", "Incorrect username or password", "Server
  certificate not trusted", "Unexpected server response", "Download interrupted", "Not enough
  memory". The page toasts a failure once (older than 30 s: dropped). A refused request (Download,
  Favorite, Sync Now) uses the same words.
- **Manifest** `dl.idx`: one line a finished track (the row, file name, size), replaced
  atomically; over 4 MiB (`SBD_IDX_MAX`) it is read as empty and never overwritten. Row state reads
  a memory copy. A file deleted by hand is dropped when found gone.
- **Downloads are in the local library too**: the worker calls stock's `scanSpecFolder` once a
  folder (when it moves on, when the queue drains, when it stops), so the files show under the
  local Albums, Artists and Songs as well as in Subsonic > Downloaded. Remove Download does not
  take a track out of stock's library until the next scan.
- **Downloaded page**: `nd_list(LS_DOWNLOADED)` puts the downloads still to come first (the
  running one, the waiting ones in order), then the manifest's rows. With rows to come, Songs
  shows two sections ("Downloading", "Downloaded") with a grey **Clear** at the right of the first
  header (`LS_ACT_CANCEL_ALL_DL`). `dl_rows` moves only when a track joins or leaves the queue,
  never with progress. The footer counts finished downloads only; Play and Shuffle take the
  whole list.

### Playback and the queue

A row tap or Play builds the queue as the local library does (`so_play_with`): the list in its own
order, opened at the tapped track.

- A list longer than `SBA_QUEUE_MAX` (500) gives a 500-row window from the tapped row, moved back
  near the end so it still holds 500 rows.
- Rows that cannot play (a DSD track not on the card, a stream offline, a non-track) are left out.
  The tapped row's own checks come first: an undownloaded DSD track asks to download, an
  undownloaded one offline toasts "Connect to Wi-Fi first". The Play pill starts at the first
  later row that can play.
- Previous goes to the track before the tapped one; nothing wraps to the top.
- Play Next / Play After insert one record (`pod_queue_insert`, `upnext_add`); an undownloaded DSD
  row, or a stream offline, gives no record.
- An artist page's Play / Shuffle with no songs list yet toasts "Loading…" while the fill derives
  it, "Can't play" otherwise.
- Shuffle walks the list by a random stride coprime with its length, queueing up to 500 distinct
  tracks spread over the list, and opens at index 0.
- Records are `stSongInfo` with the stream address in `REC_PATH`, or the local file for a
  downloaded track, loaded through `mclLoadPlayList`. Each record's id is noted in the **queue
  map** (`sba_queue_note`; up to `SBA_MAP_MAX` 1024: id, cover id, album id, suffix, size), which
  lets Now Playing find the cover, the star find the track and the playing marker find the server
  track (`sbs_playing`; `REC_PATH` cannot be compared, the stream address is salted). A build that
  fails calls `sba_queue_undo`, so the playing stream keeps its map.
- A queue with no stream address or a full map toasts "Can't play".

**Scrobble.** A server track that has played for half its length, or four minutes if sooner or the length is
unknown, is
reported to the server once (`sba_scrobble`, `scrobble.view?submission=true`), so the server's
play count moves and it forwards the play where set up. `nl_scrobble` runs in the keep-awake tick
and counts the clock between two ticks that saw the player on the same server track. A report
that the guard refuses is made again at the next tick. A play that ends with no Wi-Fi is not
reported later; there is no "now playing" notification; a track on repeat is one play.

**Keep awake.** `nl_awake_tick` (a 1 s timer, armed by a play, Play Next / After or a queued
download) calls `reset_poweroptions_timer(1, 1, 0)` while the player plays a server stream or
`sba_dl_busy`. It ends once neither holds, after a 5 s grace. No new hook.

### Songs memory

`songs.idx` rows are 820 bytes (41 MB at 50,000), so the Songs list is read 32 rows at a time
(`sba_songs_window`) and holds records for the first `SBS_SONGS_MAX` 10,000 rows (about 3.4 MB).
Past the cap `songs.idx` is not read further, the list counts as complete and the A-Z rail
appears.

## Files on the card

| Path | Content |
|---|---|
| `/mnt/mmc/.m1plus/subsonic.conf` | one line `url\|user\|secret` (salt and token, 48 hex digits; never the password), mode 0600 where the card allows |
| `/mnt/mmc/.m1plus/subsonic/` | the cache: `albums.idx`, `albcov.idx`, `artists.idx`, `playlists.idx`, `starred.idx`, `songs.idx`, `search*.idx`, `sync.txt`, `bg.txt`, `songs.part`, `al/`, `ar/`, `pl/` |
| `.../subsonic/covers/` | covers in the Cover Flow file format, separate from Cover Flow's own folder (Rebuild Covers and Developer > Cover Cache do not see them) |
| `.../subsonic/dl.idx`, `dlq.idx` (+ `.tmp`) | the download manifest; the downloads that wait (removed when the queue drains and by Sign Out) |
| `/mnt/mmc/Subsonic/` | downloaded music, `.part` until complete; kept by Sign Out; scanned into the local library |

## Limits

| Limit | Value |
|---|---|
| Songs list | first 10,000 rows held (`SBS_SONGS_MAX`); `songs.idx` cut at 50,000 (`SBA_MAX_TRACKS`) |
| Albums / artists / playlists | 20,000 (`SBA_MAX_ALBUMS`) / 6,000 / 500 |
| Favorites | 3,000 tracks (`SBA_STARRED_MAX`) |
| Playlist / album tracks | 3,000 a list (`SBA_ALBUM_TRACKS`), parsed whole |
| Play queue | 500 tracks; queue map 1,024 ids |
| Response | 4 MiB (`SBN_RESPONSE_MAX`); a larger one fails whole |
| Download queue | 1,024 files (`SBA_DLMAX`), one at a time |
| Download stall | 512 B/s for 45 s |
| Free-space floor | 32 MiB (`SBA_RESERVE_KB`); the cache keeps 4 MiB |
| Background fill | stops below the floor; five errors in a row end a run |

DSD plays only from a finished download. No transcoding. A server that only takes the plain
password (LDAP and the like) cannot be used.

## Credentials and network

**The password is not kept; the token is stored.** Sign In makes the login secret once
(`sbn_auth_make`): a random salt from `/dev/urandom` and the token MD5(password + salt), which
`subsonic.conf` and memory hold and every request sends as `s` and `t`. Whoever reads the card
gets a login for that one server (the token can be replayed), but not the password. HTTPS
verifies the server certificate against `/etc/m1plus-cacert.pem`; plain HTTP is allowed for a
LAN server. `patch/sbnet.c` holds no page or playback state: the caller registers a progress hook
and an after-transfer observer through `sbn_init`.

## Songs cap and the sign-in token

- `subsonic.conf` travels with the card and is as good as the password for the Subsonic API; it
  is not in the settings folder rule (`/mnt/data/m1plus/...`), which is for small settings.
- A server's `getPlaylist` and `getStarred2` have no paging, so a list over 4 MiB fails (Limits).

## Folders

**Sources:** `patch/ndfolders.c` (the page), `patch/sbsrc.c` (`sbs_folder_list`, `LS_FOLDERS`), `tools/pod_nd.py` `build_folders`.
A **Folders** row after Playlists on the Subsonic root (every server type, Navidrome included: its tree
is tag-built, artist, album, songs) opens a folder browser over the Subsonic API. On Gonic, Airsonic and
LMS the levels are the real directories. A directory child has `isDir`, `title`, `coverArt` and
`parent`; a song child has the usual song fields.

### Behaviour

- Root: one music folder lists its `getIndexes` entries directly (A-Z sections); several list the music
  folders as plain rows first, one tap enters that folder's index.
- Directory rows: 40 px square cover when the entry has `coverArt`, else the folder glyph (artists
  square too). Song rows: file glyph, title and the existing Subsonic row marks.
- No "..." on any Folders level (navbar: Back and Now Playing only). No Download Folder.
- Each level is cached as `nd/dir/<key>.idx` under the Subsonic cache dir; the page shows the cache
  first and refreshes in the background.
- A song tap plays the level's songs from the tapped index, by the rules of the other source rows (list
  order, window around the tapped row, `SBA_QUEUE_MAX`).

### Look (rows are the local [Folders page](folders.md)'s with its `--covers` geometry)

- Root with one folder: A-Z index (section letters 20 px at x 10, 28 px high, and the rail; rows,
  hairline and chevron give up `SG_RAIL_INSET`, as Artists). Title "Folders".
- A level shows the directory's name as the large title. Play / Shuffle pills only when the level holds
  songs (first row at `SG_TOP`, else `FO_TOP_PLAIN`).
- A song row carries the source marks ending at the text end (256): downloaded disc, download ring with
  stop square, DSD tag (`ls_marks_draw`); the title is cut for their room.
- Loading is `ls_spin` centred under the kept large title and navbar; offline and failed reuse the
  source pages' texts ("Connect to Wi-Fi first", "Can't connect to the server").

### Data layer (`patch/sbapi.c`, `sbparse.c`)

Page-facing API (`patch/sbapi.h`):

- A level is named by a **key**: `SBA_FOLDER_ROOT` ("/") for the top, `SBA_FOLDER_MF` ("mf:") plus a
  music folder id for the index of one of several music folders, otherwise a directory's server id.
  Rows carry the key to pass back: a music folder row's `id` already starts with "mf:", an artist or
  directory row's `id` is its directory id.
- `sba_fetch_folder(key)` queues a refresh on the metadata worker (kind `SBA_K_FOLDER`): returns at once
  with `SBA_OK` or the guard (`SBA_NOWIFI`, `SBA_NOCONF`, `SBA_QFULL`...); asking for a key already
  queued is one request. Never writes on the UI thread.
- `sba_folder_rows(key, &list)` reads the cached level (heap, `sba_free_tracks`; star hearts applied
  like every track list); 0 rows when never cached. Call it first, then `sba_fetch_folder`.
- `sba_state(SBA_K_FOLDER, key, &code)`: `SBA_ST_NONE` / `LOAD` / `OK` / `FAIL`, `code` is the `SBA_*`
  reason (`sbs_request_message`). Offline with nothing cached: the ask returns `SBA_NOWIFI` and the state
  stays NONE (show the offline text). `sba_gen()` moves when a level file is replaced or a status
  changes; re-read the rows when it moves.
- Rows are `sba_track_t`. New byte `dir` (in the struct's padding; row size unchanged): 1 = directory
  (use `id`, `title`, `cover`, `starred`), 0 = a song row parsed by the same `sp_track` as every other
  list (suffix, size, album id, DSD, favourite all work). At the **root index** a dir row's `album` is the
  server's index letter ("#", "B"...; "The Knife" sits under K on Navidrome): use it for the A-Z sections
  instead of guessing from the title. Max `SBA_FOLDER_MAX` (6000) rows a level.
- Order: the server's, never sorted. Root index: `index[].artist[]`, then `shortcut[]` entries the index
  lacks, then loose `child[]` songs. A directory: `child[]` as sent (Navidrome never mixes dirs and
  songs; a Gonic-style mixed directory is kept in the server's order, which we have not seen on a real
  Gonic: do not re-sort or group).
- Root with several music folders: `getMusicFolders` rows only (nothing else is asked); with one (or
  none listed) it goes on to `getIndexes` and the root level is the index. A music folder key asks
  `getIndexes&musicFolderId=<id>`.
- A failed refresh (any `SBA_*`) writes nothing: the cached file stays and the state is FAIL. A level
  with no children is an empty cached level (OK).
- Cache: `nd/dir/<key>.idx` (a key that is not letters, digits, '-' or '_' is hashed, `x<8 hex>`),
  written by the worker (tmp, fsync, rename). Sign Out and a changed user or address remove `nd/dir`
  and `nd` with the rest of the cache.

### The page (`patch/ndfolders.c`)

A standalone page (`m1plus_ndfolders`, last in `PAGE_ORDER`), not a source list page: rows mix directories with covers and song rows, which no existing list page paints. It still goes through the source seam: `lib_nd.list(LS_FOLDERS, scope)` (scope NULL = root, a directory record = that level) and `sbs_folder_list(key)` / `sbs_folder_state(key)` give records (directory: type 4, REC_TITLE, REC_ALBUM = index letter on index levels, cover in the row data `d\t<cover>`; song: type 8 as every track list), so play (`so_play_src`: list order, `SBA_QUEUE_MAX` window, DSD "Download to Play?"), marks (`lib_nd.row`), covers (`lib_nd.cover`, shared `ls_cover_poll`) and the row "..." sheet (`rowmenu_open_src`) are the source's own. The refresh is asked once a run per level (`nl_ask`), as albums.

- One window; a stack of (key, name, offset): a directory tap pushes, Back pops with the offset kept, at the root it closes. Navbar: Back and Now Playing's disc only; the large title is "Folders" at the root, else the directory's name; the small title takes over once scrolled.
- Rows are the local Folders page's: 52 px, 24 px glyph or 40 px cover (LIST_R corners) at x 8, name at x 56 cut at 256, chevron on directories. Songs: file glyph, title, marks ending at the text end, and the row "..." (the Songs page's zone; the text then ends before it). Pills only when the level holds a song; the rows then start at `SG_TOP`, also on an index level with loose songs (sections below the pills). A directory's cover not yet ready shows the folder glyph. Play queues the level's songs only (directories are left out before the `SBA_QUEUE_MAX` window).
- A-Z sections and rail on index levels (the root with one music folder, one music folder's index; keys `/` and `mf:`), from the index letters, respecting Settings > Library > List Navigation; every other level is plain.
- No rows: spinner under the title while loading, else "Connect to Wi-Fi first", "Can't connect to the server" or "Empty folder". The page re-reads when `sba_gen` moves (same rows only swap the records).
- Rows have no playing-now wave and offline rows are not dimmed (a tap says "Connect to Wi-Fi first"). A level of thousands of rows is held as records (about 350 bytes a row).
