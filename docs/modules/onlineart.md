# Find Cover & Lyrics

**Sources:** `patch/onlineart.c`, "Find Cover & Lyrics" in `patch/pcnet.c`, `patch/pcjson.c`,
`patch/artistphoto.c`; page asset `ui/m1plus_onlineart.bin` (`build_onlineart_page` in
`tools/pod_ui.py`). **Sources of data:**
iTunes Search API and Deezer (covers), LRCLIB (lyrics), Deezer and NetEase (artist photos).

An online lookup for the playing track: the album's cover from iTunes, then Deezer, and the
lyrics from LRCLIB. From an artist's page the same page finds the artist's photo ("Artist
photos" below). It is a row on page 2 of Now Playing's More sheet ([playmore](playmore.md)) and a
page of our own. Stock's hidden "Online search" row (Baidu / Kugou / NetEase over plain HTTP)
stays hidden and unused. No hook of its own: the row is the More dialog hook's, the network is
the Podcasts worker's libcurl client ([network](network.md)).

## What the user sees

- **The row** (More sheet, page 2, between A-B repeat and Delete): glyph `pod_ic_art` and
  **Cover & Lyrics**. With Wi-Fi off (checked each time page 2 shows) it is dimmed and
  insensitive. For a server track ([subsonic](subsonic.md)) it is always dimmed:
  `onlineart_open` refuses it (`oa_track`), as there is no local album key to write a cover
  under and no file beside which `.lrc` and `folder.jpg` go. A podcast episode or audiobook part
  has no such row: its More page leaves it out.
- **The page** has the Search page's frame: chip row **Covers** / **Lyrics** (opens on Covers),
  a state line, and a scrolling list. Both lookups start when the page opens; each tab keeps its
  scroll position. The lookup runs once, on open. Back (or Now Playing) cancels what is running;
  Back inside a detail or confirmation returns to the tabs first.
- **Covers**: thumbnails (88 px, three a row): the first six iTunes albums that have a picture,
  then Deezer's, twelve in all. **A tap saves nothing.** It opens the **confirmation**: the
  larger picture (600 px iTunes, 500 px Deezer, fetched by `pn_art_fetch`, never an upscaled
  thumbnail), album, artist, source, and the pill **Use This Cover** (**Replace Cover** when a
  `.pick` marker exists). The pill appears when the picture is decoded; a failed fetch says its
  word and shows no pill. The pill saves ("Saving…"), then the grid shows that thumbnail framed
  (current); a failed save says its word and gives the pill back. Back writes nothing, cancels a
  running fetch and removes the downloaded picture.
- **Lyrics**: one row per LRCLIB candidate (title, then `Artist · Album · m:ss` (the exact `api/get` match first, then `api/search`
  records by closeness of length, synced first among equals, at most 20), with a **Synced**
  badge when it has `syncedLyrics`). A tap opens the **detail**: the full text (time tags and `[ar:]` headers removed, every
  line wrapped, never cut with an ellipsis) and the pill **Save Lyrics** (**Replace Lyrics**
  when `<song>.lrc` or `.LRC` exists). An existing file is never touched before that pill. The
  saved row then wears a **Saved** badge. A failed write says "Storage unavailable" and leaves
  the pill.
- **Empty and failed states** are an Apple-style "content unavailable" block (glyph, title,
  explanation, optional **Try Again** pill). The states, texts and glyphs are
  `pod_ui.OA_ES_STATES` (13 languages): searching, lyrics / covers busy, no lyrics, no covers,
  no connection, certificate problem, certificates missing, server error, no Wi-Fi, no date, no
  card, no memory. Failures use the Podcasts page's words. Try Again shows for busy, no
  connection, certificate problem, server error, no Wi-Fi, no date, no card and no memory; not
  for searching, no lyrics, no covers and certificates missing.
- **Try Again** restarts only the selected tab's lookup (`pn_art_again(part)`); the other tab
  keeps its results. While another job holds the slot the tab shows "Searching…" and a 250 ms
  tick starts it when the slot is free.
- **Busy services**: a single HTTP 503 or 429 from LRCLIB, iTunes or Deezer is `PN_OVERLOAD`
  and shows the busy state at once, with no automatic retry. LRCLIB answers uncached queries
  with 503 when under load, so a busy `get` skips `search`; a busy iTunes still lets Deezer run.
  Fast failure plus a manual Try Again beats waiting 8 to 10 s.

## Services

All HTTPS with the firmware CA bundle `/etc/m1plus-cacert.pem`; verification is never switched
off. The user agent is `M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)`.

| Part | Request |
|---|---|
| Covers 1 | `itunes.apple.com/search?media=music&entity=album&limit=8&term=<artist album>`; first `PN_ART_ITUNES_MAX` 6 with a picture |
| Covers 2 | `api.deezer.com/search/album?limit=8&q=<artist album>`; up to `PN_ART_MAX` 12 covers in all |
| Thumbnails | each result's address, one after another, at most 256 KB, kept in `/mnt/mmc/.m1plus/art/` |
| Larger picture | `pn_art_full`: iTunes `100x100bb` becomes `600x600bb`, Deezer `250x250-` becomes `500x500-`; at most 3 MB |
| Lyrics 1 | `lrclib.net/api/get?track_name=&artist_name=[&album_name=][&duration=<s>]` |
| Lyrics 2 | `lrclib.net/api/search?track_name=&artist_name=` (unless `get` failed on the network); records of either answer with synced or plain lyrics are candidates, up to `PN_LYR_MAX` 20 |

- The `duration` is the track's length in seconds. The term is `artist album` (the title when there is no album tag), each field cut at 95 bytes
  on a character boundary, URL-encoded UTF-8 (`pn_urlenc`). iTunes gets no country.
- Answers are read into the 96 KB Podcasts buffer and taken apart by the bounded extractors of
  `patch/pcjson.c` (no recursion, no allocation). A lyrics text over `PN_LRC_CAP` 48 KB ends at
  its last whole line.
- The lyrics detail wraps once, when it opens (at most 14000 characters, 700 lines).

## The worker

- `pn_art`, `pn_art_fetch` and `pn_art_pick` use the **one job slot** of `patch/pcnet.c`
  (`PN_KIND_ART`, `PN_KIND_PICK`): never two jobs at once, `PN_BUSY` for the second. A running
  Podcasts download is no job and goes on beside the lookup. The page starts its lookup from its
  250 ms timer once the slot is free.
- `pn_art` runs the guards (card, Wi-Fi, clock, CA bundle), removes old scratch files and starts
  one detached thread. The thread touches no widget and no stock function; it writes a record the
  page reads on its timer, with a store barrier before every counter.
- Cancel is `pn_cancel`: the transfer-info callback stops the running transfer. On page destroy
  a running worker is cancelled and left to end; its scratch files go with the next lookup.
- Standby turns Wi-Fi off when nothing plays; a lookup that cannot connect ends at libcurl's
  time-outs with `Can't connect`. The page never waits on the thread, so the UI cannot hang.

## Where things are saved

- **The cover** (`pn_art_pick`, only from the confirmation's pill): for each key (the playing
  track's `cc_album_key`, and the library Albums row of that album name when its key differs, as
  the library groups albums by name) `pv_shrink` writes `r<key>-168.jpg` in the Cover Flow cache
  `/mnt/mmc/.m1plus/covers` (a JPEG fitted inside 192 px, never upscaled) and a
  `r<key>-168.jpg.pick` marker beside it. Our pages that show covers read it next time they
  load that cover ([covercache](covercache.md)). Chosen because the cache is what our pages
  read first, is keyed by artist and album (so it survives a library rescan) and needs no new
  reader. Rebuild Covers leaves an album with a `.pick` marker alone; delete the marker to
  let it be rebuilt.
- **The folder picture**: the original JPEG is also written into the track's folder as the first
  of `folder.jpg`, `folder.jpeg`, `cover.jpg`, `cover.jpeg` that exists, else `cover.jpg`
  (a `folder.png` still wins in stock's order and is never touched). Stock Now Playing, lock
  screen and Cover Flow show it for tracks without embedded art. Not written for a track in the
  card's root. Every track in the folder shares it. A PNG answer goes to the cache only.
- **The lyrics**: `<track path with its extension replaced>.lrc`, UTF-8, written by the UI
  thread (`pn_lyr_save`: `.tmp`, fsync, rename). Synced and plain lyrics are saved as LRCLIB
  gave them (carriage returns dropped); plain ones show unsynced ([lyrics](lyrics.md#unsynced-lyrics)). Stock reads the `.lrc` when a track loads, so after a
  save of the playing track's file (the name less its extension still matches the playing path)
  the page does what stock does after its own lyric download: `mclLoadExLyric()` (clears the
  lyric deque, reads the file; safe on the UI thread, `start_playqueue` runs it there) and
  `force_refreshflag` = 1, so Now Playing's next 500 ms tick rebuilds the `scroll_lrc` rows
  (also from none to some). It then calls `ly_reload`, because the [lyrics page](lyrics.md)'s
  row signature has no text and cannot see same-shaped replacement lyrics. A track change while the page is open skips the reload; a failed save does neither.
- Scratch in `/mnt/mmc/.m1plus/art/` (thumbnails, `pick.src`, `full.*`, `l<n>.txt`) is removed by
  the next lookup and by the page's destroy when no worker runs.

Stock limit, no hook: a track with embedded art keeps it on stock Now Playing, the lock screen
and the stock album pages. Only our pages show the picked cover.

## Artist photos (Find Artist Photo)

The same page, worker and scratch files for an artist of the library: `onlineart_open_artist(name)`,
reached from the "..." card of a library artist's page ([albums](albums.md); not on a
composer's, a source's or Unknown Artist's page). It needs no playing track and never touches a
track's cover, folder or lyrics.

- **The page**: title **Artist Photo**, no chips; the artist's name stands in the chip row's
  place. The list is the Covers grid of the photos found (500 px picture in the confirmation),
  with two states of its own: "No Photos Found" and "Photo Service Busy" (with Try Again). The
  confirmation names the service (`Deezer`, or NetEase, 网易云音乐 in Chinese). A tap opens the same confirmation with the pill **Use This
  Photo** (**Replace Photo** when the artist has a picked photo). Nothing is written before the
  pill.
- **Deezer** (`pn_artist`, `api.deezer.com/search/artist?limit=25&q=<name>`): artists with no
  picture of their own are left out. A 503 / 429 is the busy state. Offered: the artists of that very name first (`ap_key`
  equality: case, surrounding white space and a leading "The " do not count), then at most
  `PN_ARTIST_OTHER` 4 others, `PN_ARTIST_MAX` 6 in all; in each group the most followed first.
  The others are kept because the same artist under another spelling or script (`Eason Chan`
  for `陈奕迅`) is among them.
- **NetEase Cloud Music** (`music.163.com/api/search/get?type=100&limit=10&s=<name>`), asked
  after Deezer in the same job. It is the site's own search, not a documented service, so
  everything about it fails quietly. Offered: its artists of the very name that have a picture,
  at most `PN_ARTIST_NETEASE` 2; with none of that name, its first entry alone. Order on the
  page: Deezer's of the very name, NetEase's, then Deezer's others. A service that fails while
  the other answers is left out without a word.
- **Why two services**: Deezer needs no key, takes one request and matches names across scripts
  (周杰伦 finds Jay Chou), but misses some CJK artists; NetEase covers those. fanart.tv needs a
  MusicBrainz id and an API key, TheAudioDB found nothing Deezer lacked, and Wikidata's pictures
  are stage shots of any shape; the iTunes Search API has no artist pictures.
- **No setting**: both services are always asked.
- **The save** (`pn_artist_pick`, `ap_pick` in `patch/artistphoto.c`): writes the artist's cache
  files (`a<key>-168.jpg`, `a<key>-44.jpg`, cropped square) and the `a<key>.pick` marker in
  `/mnt/mmc/.m1plus/artists`, and bumps `ap_epoch` so the artist's page and the Artists list
  show it when they come back. The save is whole or nothing (`PN_STORAGE`). The marker keeps
  every automatic build off the artist ([artists](artists.md)). The photo is filed under the
  name as the library has it.

## Pins and hooks

None new: the sheet's hook is `dialog_playmore_dialog_init` (`PLAYMORE_PINS`). The row is
`pod_art` in both themes' `playmore_dialog.bin` (`tools/mod_lists.py`); translations are in
`tools/pod_i18n.py`.
