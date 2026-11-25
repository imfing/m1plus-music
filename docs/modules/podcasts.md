# Podcasts

**Sources:** `patch/pcmodel.c` / `podcasts.h` (model, resume, speed, order), `patch/podcasts.c`
(page, sheets), `patch/pcnet.c` / `curlopts.h` (network worker), `patch/pcregion.c`, `patch/pcfeed.c`
/ `pcjson.c` (feed and JSON parsing), `patch/pccover.c` / `pcpng.c` (covers), `patch/pcdetail.c` /
`pcnotes.c` / `pcwrap.c` (episode page, notes), `patch/pcfind.c` (search inside a show),
`m1_segmented` / `m1_capsule` in `patch/common.c`; `tools/pod_ui.py`, `tools/pod_show.py` (layout
model), `tools/pcregion.py`.

Local episodes, subscriptions, downloads, directory search, Discover charts, episode notes and
Saved episodes share the page `ui/m1plus_podcasts.bin`. The Pod interface exposes Podcasts too.
The download policy follows q2-podcasts (MIT, `internal/library/download.go`); the implementation
uses demo's libcurl. Shared request and download layer facts are in [network](network.md).

## Pages and controls

- **Shows level:** the refresh line, Continue Listening, a show grid, and rows for Discover (while
  Podcast Discover is on), Downloaded, Subscriptions and Saved. The Shows, Discover, Downloaded,
  Subscriptions and Saved levels open on a large title that collapses into the navbar's small
  title ([navbar](navbar.md)).
- **Refresh line:** a status, not a control: "Updated 1h ago", "Never refreshed" or "Refreshing
  2/5…". **Refresh All** is the first row of the Shows "..." sheet (then Import from Card while the
  card has something to import). Cancel is the refresh dialog's Cancel pill.
- **Captions** under a show's cover: "N new" after a refresh that found episodes; else "Updated
  today / 2d ago"; a never-refreshed subscription shows the failure of this session (No Wi-Fi,
  Feed not found ...); "12 episodes" for a show with no feed.
- Shows sort by newest episode. The grid shows the first 10; with more, **See All (N)** opens the
  All Shows page (the Subscriptions rows, every show).
- **Show page:** artwork, metadata, Latest Episode pill (always the newest episode) and the first
  20 episodes in the show's Episode Order, then a **See All** row. A body tap opens episode
  details; the pill plays, downloads, pauses, resumes or retries by state. A cell's date line is
  "date · length" for an episode not on the card (its pill says the size), else the date alone;
  the episode page's is "date · length · size". Length is the feed's `d=`, minutes rounded up, left
  out when the feed gave none. Downloaded rows keep "show · date · size".
- **Episode details:** long description and the same actions. The show row goes back to the show
  page the episode is on top of: from Downloaded or Subscriptions the show's page opens and Back
  goes on to that list; a search or Discover preview's episode returns to the preview.
- **Show sheet rows:** Playback Speed (a tap cycles), **Episode Order** (Newest / Oldest First;
  saved at once, loaded rows reversed in place; a failed save toasts `Storage unavailable`),
  **Filter** (below; the row is there while the show has an episode or a Filter is on), Refresh Feed, Select Episodes, Mark All as Played, Unsubscribe.
- **Select mode** (the shared module, [selmode](selmode.md): `pg.msel` over `pg.pick`; the bar's pill is Delete or, on Subscriptions, Unsubscribe) supports bulk deletion; the playing file is kept. Deleting an episode clears
  its resume and played state. Unsubscribing keeps local files.
- **Saved episodes** are stock `myfav` records; there is no separate database. The Now Playing
  favourite becomes a bookmark for podcast paths, and its More sheet can return to the show.
- **Subscriptions** support card import and export, including OPML, and `Podcasts/subscriptions.txt`
  (one http(s) feed URL per line, `#` comments).

### Search level

Reached from the Shows level's globe or the Discover level's magnifier; only while Podcast
Discover is on. The Shows level's navbar is `[Globe | ... | Now Playing]`: the "..." shows while a
show has a feed or there is something to import. The search level accepts directory terms, feed
URLs and Apple Podcasts links. Results open a preview (a result with no feed is dimmed "Not
available", no chevron, no tap). Subscribe creates the show folder and metadata. Previews do not
play remote episodes. Back (and the keyboard's Back with nothing typed) returns to where it was
entered, Shows or Discover; Back from an address's or link's preview shows the level as it was.

The preview's picture is the feed's channel image shrunk to a thumbnail. If that cannot be
fetched or decoded (some feeds serve progressive JPEGs over `PC_COVER_MAX_PX`), the store's
`artworkUrl600` is used. A typed feed address, OPML import or Deezer result has no such fallback.
Subscribe moves the preview's picture to `cover.jpg`; a later refresh never replaces a cover.

## Discover

Apple's top 25 charts for the Podcast Region (`rss.marketingtools.apple.com`), as the **Shows |
Episodes** segmented control selects. The level has the large title, a grey line ("Top 25 Shows in
United States"), the control, then ranked rows (rank, cover, title, author or show). The navbar is
Back, the magnifier and Now Playing.

- **Segmented control** (`m1_segmented`): a rounded track with a light thumb for the selected
  segment (dark label), white labels on the rest. Neutral, no accent colour; the font has one
  weight.
- **Fetch:** a chart is fetched on its first view and kept in memory for the session (no card
  cache). A chart held for another region is asked again. The worker makes up to three requests
  (20 s time-out, one second apart). A **404 or an empty answer for a region other than the United
  States asks the United States chart silently**, and the grey line names the storefront actually
  shown. A failed chart is not asked again by the ticks; a tap or re-entering asks. Each chart
  keeps its own scroll offset.
- **Statuses** are the page's words (Loading..., No Wi-Fi, Set the date first, Certificates
  missing, Can't connect, Server error, No results ...), centred in the room under the control.
- **A tap on a row** opens the show's preview (an iTunes lookup of its Apple id in the chart's
  store, then the feed). A show whose lookup has no feed is remembered for the session as Not
  available (no toast); any other failure is the toast "Can't subscribe: why". Back returns to the
  same chart at its offset.
- **An episode row** also opens that episode's page over the preview. After the feed is held, the
  worker looks the show's episodes up in the store and matches the record to a kept feed item: by
  enclosure URL, else by publish minute, else by title (a leading "586. " dropped, case and runs of
  spaces ignored). `episodeGuid` is not the feed's guid and is not used. Only the 20 kept items can
  match. No match leaves the preview alone.

## Region

`patch/pcregion.c`, model `tools/pcregion.py`: 34 storefronts by English name, saved as two capital
letters in `/mnt/data/m1plus/podcast-region` (anything else is Automatic). Automatic is the UI
language's country (ja JP, ko KR, zh_CN CN, zh_HK HK, zh_TW TW, ge DE, fr FR, it IT, po PL, th TH, ru
RU, uk UA), and for English and Spanish the Settings time zone's place (London GB; Adelaide,
Sydney, Brisbane, Eucla, Lord Howe AU; Auckland, Chatham NZ; Kolkata IN; the US zones US; Mexico
City MX; Halifax, St. John's CA; Buenos Aires AR; Amsterdam NL; Bangkok TH; Tokyo JP) unless it is
stock's default (Shanghai), else the United States. The region drives the directory search (`country=`) and the
chart address; the lookup of a typed Apple link has no country, a chart row's is made in the
chart's store. Nothing runs at paint.

## Podcast Directory

Where the search and the lookup of a show's id go: **Apple Podcasts** (default) or **Podcast
Index**, chosen in **Settings > Library > Podcasts > Podcast Directory** (`ACT_PCDIR` 137, picker
`m1plus_podcastdirectory`, file `/mnt/data/m1plus/podcast-directory`, `1` is Podcast Index). Both
use **keyless endpoints**. A tap saves first and only then moves the check.

Exactly one directory is asked, never both.

- **Search:** `https://api.podcastindex.org/search?limit=25&term=<term>`, parsed as the store's
  shape. The Podcast Region has no effect on it.
- **Result pictures:** Podcast Index names the feed's own picture (up to 3000 x 3000, 2 MB), not a
  thumbnail, so it is fetched up to 2 MiB and shrunk. The placeholder stays for a progressive JPEG,
  an oversized picture or a dead address. A search therefore downloads a few MB.
- **Lookup by id:** a result with no feed, or a pasted Apple link, is looked up at
  `.../lookup?entity=podcast&id=<id>` of the chosen directory.
- **Charts stay Apple's** (Podcast Index has no keyless chart): Discover, a chart row's lookup and
  the episode match are Apple's whatever the picker says.
- **A change of choice** keeps one invariant: the rows the search level shows are the chosen
  directory's, or there are none. `pg_srch_dir_sync` enforces it: a queued term search of the other
  directory is dropped, a running one stopped, the state reset. A field holding a directory term
  is then asked of the chosen directory once; an address, a link or an empty field submits nothing.
- The search level follows the choice: the navbar title, the field hint ("Search Podcast Index") and
  the keyboard page's words.
- Both services refuse a request whose User-Agent does not name the application, so every request
  carries `NET_AGENT` (`M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)`).

## Settings rows

**Library > Podcasts** (`PCSET_PAGE`, opened by the Podcasts row in the Library page's last card)
has two cards: card 1 holds **Podcast Discover**, card 2 holds
the Directory and Region rows and the note "Search words go to the chosen directory."

- **Podcast Discover** (`ACT_PCSEARCH` 34, file `/mnt/data/m1plus/podcast-online-search`, `0` is off,
  a missing file or anything else is **on**): off hides the Shows level's Discover row and globe,
  and Discover and the search level cannot be opened (a page in front with the switch off is sent
  back to the Shows level). The Shows "..." has no Search row. A tap saves first and only then
  changes the switch.
- **Podcast Directory** (above) and **Podcast Region** (`ACT_REGION` 55, picker `m1plus_podcastregion`:
  **Automatic**, shown as "Automatic (United States)", then the 34 storefronts) are dimmed and inert
  while Discover is off. The directory never dims the Region, since Region also decides Discover's
  charts. A region tap saves first (`pcregion_set`; Automatic removes the file).
- The rows have no glyph because label and value share the room; the storefront is "UK", not
  United Kingdom, for the same reason.

## Files and model

Shows live under `/mnt/mmc/Podcasts/<Show>/` (root matching is case-insensitive). Supported
extensions: mp3, m4a, m4b, aac, ogg, opus, flac, wav, wma. A show can supply `cover.*` or `folder.*`.

| File | Contract |
|---|---|
| `.show` | UTF-8 `M1PLUS-SHOW 1`; key=value lines for title, feed, image, checked, modified, author, category and desc |
| `.episodes` | UTF-8 `M1PLUS-EPISODES 1`; tab-separated key=value fields: g guid, p epoch date, d duration seconds, l bytes, f filename, t title, u enclosure URL, x short description |
| `.archive` | The complete list, written by the See All fetch and kept complete by every refresh: the `.episodes` format, newest first, at most 2000 lines and 1.5 MiB |
| `.notes` | Long descriptions keyed by episode identity (`patch/pcnotes.c`) |
| `<filename>.part` | Incomplete download, kept for resume |
| `.m1plus/podcasts/resume` | PCR1 ring: count plus 16-byte hash/position/length/flags slots, most recent first |
| `.m1plus/podcasts/speed` | PCS1: count plus show-hash/mode pairs |
| `.m1plus/podcasts/order` | PCO1: count plus show-hash/value pairs (0 newest first, 1 oldest first). The key is the show folder's hash, so renaming a folder resets its order. Same 64 slots and eviction as speed |

- Metadata permits LF or CRLF, ignores unknown fields and strips tabs and newlines from values.
- The model reads at most 64 KB of `.episodes` and keeps the newest 300 entries (the recent list,
  `pc_load_show`). It returns episodes already in the show's order, so the Show page, the iPod level,
  Downloads, Continue Listening and the queue agree. The cap keeps the newest 300 under either
  order, so the order never changes which episodes are listed. A missing file, entry or bad value
  in `order` is newest first. With no memory a list is not returned at all (no unsorted fallback).
- `pc_ep_of(path, out)` looks up one playing episode: the `.episodes` entry (else `.archive`'s) whose
  `f=` is the file name, parsed like any entry (guid, date, duration, title, description). Without
  an entry it returns 0 with the title from the file name and the date from mtime. It reads files,
  so Now Playing calls it on a track change only.
- `pm_merge` combines feed entries and files into local, partial or remote episodes. Without
  metadata the title comes from the file name and the date from mtime. Newest first is date
  descending, then file name descending (digit runs by value, case ignored), then entry order;
  Oldest First is the exact reverse. A show with no metadata entry (copied files) sorts by natural
  file name alone, descending for Newest First; a feed show keeps its publication-date sort.
- Refresh preserves old entries whose completed or partial file remains on the card.
- Titles fit 95 bytes, local file names 127, feed and image URLs 320. Short descriptions are at most
  200 UTF-8 bytes, episode notes 4096.
- **Limits:** 100 shows ("Too many shows" at the limit; of more folders the first 100 are read), 300 feed entries per show (an archive
  holds 2000), a list of at most 2700 episodes, 400 examined files (2400 with an archive), 4096
  resume slots, 64 speed and 64 order records.
- State writes require `m1_card_mounted` and use temporary files, fsync and rename. An unmounted
  card directory never receives persistent writes.

## Search inside a show

A magnifier in the Show page's navbar (`[Search | ... | Now Playing]`) opens a search over that
show's episodes. It shows on a subscribed show and on a show of copied files (with at least one
episode), not on a preview, the episode page or in select mode. It is independent of Podcast
Discover. Purely local.

- **Page:** `m1plus_pcfind`, a window over the Show page: the search field ("Search Episodes"), our
  keyboard, and compact 60 px rows (title, then date and "· Downloaded"). Empty field: no rows. No
  match: "No results". The X and hardware Back close the page.
- **Matching** (the library search's engine, [search](search.md)): titles only. The field is
  folded (case, Latin diacritics, kana, width) and split at spaces; every term must be in the
  title. A term of only digits is a **whole number**: `37` finds "Ep 37", "EP037" and "第37集" but not
  "137" or "370". A Chinese title also matches by pinyin initials (`zjl` finds 周杰伦). Results
  are in the show's order, at most 2000, matched anew on every change.
- **Memory:** the 1 MB pinyin engine is held only when some title has a CJK character, and
  only while the page is open. The page does not open while a library Search page exists (they
  share the matcher's state).
- **Tap and Back:** a tap keeps the text and scroll, opens that episode's page over the Show page
  and closes the search. Back from the episode page reopens the search with the text and scroll,
  the keyboard down. Playing queues from that episode down in the show's order.
- **Search All Episodes:** for a subscribed show with no `.archive` and a non-empty field, one extra
  row ends the results. Its text and spinner are the Show page's (`pg_more_line`), and a tap starts
  the same archive job; leaving the search leaves the job running. When the archive appears, the
  query runs again over the complete list and the row goes.
- For a show with an archive the complete list is swapped in before the page opens and the Show
  page reads the recent list again once the search and any result's episode page are closed. With
  no match, the Search All Episodes row stands alone at the top, above "No results".
- The search ignores the Show page's Filter and the queue is the show's full order.

## All episodes

A subscription keeps the 20 newest feed items in `.episodes` (`PF_KEEP`; entries whose file is on
the card stay besides). Two files, two roles:

- `.episodes` is the **recent** window. The Show page and every cross-show reader (Shows level,
  Continue Listening, the Downloaded scan, the iPod level, Latest Episode, the queue) read only it
  and the files on the card.
- `.archive` is the **complete** list. Only the All Episodes page, the search inside a show and
  Unsubscribe (which must find every `.part`) read it whole, and the Show page's count reads it
  once.

The Show page ends with one row:

| Show | Row | A tap |
|---|---|---|
| subscription with no `.archive` | "See All" | fetches the archive (guards, Loading… with the count and a spinner, "Can't connect · Tap to Retry", keep-awake; survives leaving the page); when it ends well while this page is in front and this tap started it, the All Episodes page opens |
| show with `.archive` | "See All (N)", hidden when N is not more than the rows shown and no Filter is on | opens the All Episodes page, no request |
| show with no feed, over 20 rows | "See All (N)" | opens the All Episodes page over the local list |
| preview | none | |

- **The All Episodes page** is the Show level over the complete list, with no header and the show's
  name in the navbar. Rows, the state pill, select mode, the "..." sheet (no Refresh Feed or
  Unsubscribe), the magnifier and the episode page are the Show page's own code. Filter and Episode
  Order are the show's (one state). Mark All as Played marks the complete list and a play queues
  the local files of the page's rows. Back reads the recent list again and returns to the Show page's
  offset.
- **Memory:** one list at a time. A recent list is at most 300 entries plus every file (room for
  700 episodes, 2700 with an archive); the complete list exists only while the All Episodes page or
  a search with an archive is open.
- **Nothing is cut from a recent list** under the room above. A complete list past 2700 episodes
  keeps, in order: the newest feed-only episodes, then episodes with a file on the card, then the rest
  by date. The Downloaded page takes the newest 300 downloads by file date. For a show with an archive, `.archive` is also read when a file or `.part` on the card has
  no `.episodes` entry, so a downloaded old episode keeps its title, date and place; its download
  finds the URL in `.archive` (`.episodes` first). The complete list is `.episodes`, then the
  archive entries an earlier entry does not have (guid, else file name), merged with the files.
- **Refresh keeps the archive complete:** a show with an `.archive` gets the refreshed lines it
  lacks, placed by date, written to a temp file and committed. The oldest lines drop past 2000 lines
  or 1.5 MiB. A failure leaves `.archive` as it was and the refresh still succeeds. A show with no
  archive gets none.
- **Job** (`pn_arch_*`): one worker job in the shared slot, up to three requests one second apart
  for a network error, time-out, stall, 5xx, 408 and 429; other errors are final. A 300 s and 60 s
  per-attempt limit, a 32 MiB decoded cap, newest 2000 items. Refresh and Unsubscribe are refused
  while it runs. Long descriptions are not written for archive items (the episode page shows the
  short description).
- **The hint** (`pg_paint_hint`): an empty page's words (No downloads, No subscriptions, No saved
  episodes, a Filter's No unplayed / No downloaded episodes) and the Discover and search status
  line are one painter, wrapped to the margins and centred in the room under the header. A busy
  line has the spinner before the first line.

## Filter

**Filter** is the show sheet's row after Episode Order, with values **All**, **Unplayed**,
**Downloaded**; a tap cycles and the sheet stays.

- **Rows:** an index array over the episode list, allocated only while a Filter is on (no memory:
  the Filter is All and a toast says so). Everything that takes a row maps through it; what takes
  an episode (episode page, sheet, Latest Episode pill, Unsubscribe, the search) uses the whole list.
- **Predicates:** Unplayed is not done (a partly played one is unplayed); Downloaded is a file on the
  card. The show's order is kept.
- **State** is page state, not saved. Leaving the Show level or opening another show resets it; a
  reload keeps it. A mark made while Unplayed shows does not move the row until the list is made again.
- **Queue:** playing from a filtered list queues the rows shown. Mark All as Played marks the rows
  shown. An episode opened from the search plays with the whole list.
- An empty Filter shows the hint under the header; the "..." and **See All** stay.
- **Ignored by:** the Latest Episode pill, Continue Listening, the iPod level, the Downloaded page,
  the Shows counts and the search.

## The Downloaded page

Large title, a storage line ("7 episodes · 217 MB · 18 GB free") and two sections: **In Progress**
(what the worker holds, then failed and paused) and **Downloaded** (files on the card, newest
first).

- **Section header:** only In Progress has one, drawn only when both sections have rows. With one
  section alone there is no header. Rows, hit testing and select mode all go through one place
  computation, so the three cases agree.
- **In Progress rows** are marked as the Subscriptions pages' download rows are
  ([subsonic](subsonic.md)): a 14 px ring (arc in 12 steps, the stop square while running, the
  arrow while waiting), and "42%" or "Waiting". A failed or paused row has no ring and says
  "Failed: <why>" or "Paused".
- **"..." sheet** on every In Progress row: **Pause** (running or waiting), **Resume** (paused) or
  **Retry** (failed), then **Cancel Download** (unlinks the `.part`, no confirm). The sheet keeps
  the download's key, so a row moving under it is safe. A tap on the row toggles it. Downloaded rows
  have no "...".

## Playback, resume and speed

- Episodes and book parts play as class `0xf001` (All Songs, as Daily Mix) with copied song
  records; playback needs no library scan. Not folder playback (class 1): stock rebuilds a folder
  queue at its end, so the Queue page's Clear and row actions would not hold. The queue ends after
  its last episode (Repeat All wraps).
- **Boot resume:** stock's Memory Playback reloads a class 1 track's folder from disk, but for
  `0xf001` runs `getAllMusic`, which never lists spoken audio. Hook 42 `pc_mem_type`
  ([payload](payload.md), `patch/pcmodel.c`) saves type 1 in the record when the play type is
  `0xf001` and the playing path is spoken audio; anything else is saved as stock does. The resumed
  track is therefore a folder queue (the show's folder in file order) until played from its page.
- The
  tag-reader hook supplies show and episode text only for podcast paths. Library query filtering
  removes podcast and audiobook paths from music lists and Favourites; Daily Mix, Recently Played
  and custom Shuffle queues exclude them too. Folders and stock history tables can still contain
  episodes.
- **Audiobooks** ([audiobooks](audiobooks.md)) use the same resume ring and speed records, with a
  played threshold of 30 s from the end (no 95 % rule) and positions saved at any length. A book's
  speed key is its own, so a book and a show of the same name never share a speed.
- `pc_note`, called by Now Playing, the mini player and the Podcasts page timer, records positions
  only while those pages tick. Positions from 30 s are saved; within 30 s of the end or past 95 %
  the episode is marked played. Writes are limited to every 30 s, with immediate flushes on pause,
  track change, page actions and backgrounding.
- A saved position resumes once playback reaches 1..4 s; it is abandoned after 15 s if it cannot be
  applied. Played episodes restart at zero. Starting the episode the player is already on
  (`pc_restart`) saves its current position first and resumes there, unless it was marked
  played or new since: then it starts at zero. For 2 s the player's old second is neither
  recorded nor taken as the new start.
- **Speeds** are 1x, 1.25x, 1.5x and 2x per show. They change RAM and player state without writing
  stock's PLAYSPEED configuration, and music restores the previous mode. A speed change is applied
  at the next track open.
- Now Playing's button row for an episode or a book part is speed, back 15 s, play, forward 30 s
  and a plain queue glyph ([nowplaying](nowplaying.md) "Spoken audio controls"). Its speed button
  restarts the player, so that change is heard at once.

## Network and feeds

Two lanes (`patch/pcnet.h`), each a detached thread that never touches widgets; the UI reads
generation and status records.

- **Jobs:** a refresh, a search or preview, a chart, the archive fetch and other pages' jobs share
  one slot; one at a time, `PN_BUSY` to the next ([network](network.md)). The LibriVox catalog jobs
  ([audiobooks](audiobooks.md)) share it. A book's download has a thread of its own beside the
  slot and the episode queue. The Radio directory fetch ([radio](radio.md)) is refused while a job
  runs; the reverse is not checked.
- **Downloads:** the episode queue has a thread of its own, one episode at a time, beside a job. No
  page pauses the downloads. A download stops only when its row cancels it (the `.part` stays, a
  later tap resumes it) or takes it away (Remove Download, select-mode Delete, Unsubscribe).
  The queue holds 32 entries in RAM; a reboot leaves partial files paused.

**A download's life is its slot's state**, and every move is one row of one table, made under one
mutex:

| Event | Who | From → to |
|---|---|---|
| ADD | page | FREE → WAIT (the look in the queue, the RESUME below and the new entry are one hold of the mutex) |
| CLAIM | thread | WAIT → ACTIVE |
| CANCEL | page | WAIT → FREE; ACTIVE → STOPPING |
| DROP | page | WAIT → FREE; ACTIVE, STOPPING → DROPPING |
| RESUME (an add of one being paused) | page | STOPPING → ACTIVE |
| PUBLISH (the rename) | thread | ACTIVE, STOPPING → PUBLISHED |
| END (done or failed) | thread | ACTIVE, STOPPING, DROPPING, PUBLISHED → FREE |
| HALT (the thread stopped its transfer for a pause or a drop) | thread | STOPPING, DROPPING → FREE; ACTIVE → WAIT |

- **STOPPING is a pause:** the transfer ends, held bytes are flushed and the `.part` stays. A tap
  again is kept in both orders: before the run's end (HALT requeues the episode and the same thread
  takes it up from the `.part`) and after it (the add finds the slot free).
- **DROPPING is a cancel that leaves nothing:** the page unlinks the `.part` at once and the thread
  writes none of its memory, never renames, removes its `.part` and keeps no failure. The only way
  out is END; a new add of the same episode is queued behind it.
- **PUBLISHED** is a downloaded episode: no cancel or drop moves it. Delete and Remove Download
  unlink the file; Unsubscribe keeps it.
- An episode queued while the thread ends is taken up by that thread; the downloads' timer starts a
  queue whose thread could not be made.

**Requests** use the firmware CA bundle with verification on, bounded HTTP(S) redirects and
connection and transfer guards. Missing Wi-Fi, an invalid clock or missing certificates give
explicit errors. Feed requests have an 8 MiB cap and a 120 s timeout. **Conditional requests use the
server's Last-Modified, never the device clock.** A 304 preserves episodes; a missing episodes
file forces an unconditional retry.

**Feed parser:** a streaming RSS parser keeps the 20 newest enclosed items, handles arbitrary chunk
splits, entities and CDATA, and strips HTML from descriptions. Descriptions, titles, the author and
the category are entity-decoded a second time (`pf_unent` for the last three), because some feeds
escape twice (Arte Radio's `s&amp;#x27;empare`, or `&#x27;` inside CDATA). Unknown entities stay
as written. A refresh rewrites the stored episode titles. The show title is kept after the first
refresh, except a stored one that, decoded once more and normalized, is the feed's (`pf_title_healed`). Local file
names keep the old text. Unicode spaces count as white
space, U+2028 and U+2029 as paragraph breaks, and zero-width characters are dropped. **No Atom.**
Refresh writes episodes before show metadata and preserves local file names. Cover failures do not
fail the feed or replace user-supplied artwork. Large JPEG and PNG art is reduced to 192 px with
bounded-memory decoders; display decoding refuses images over 2.1 million pixels.

## Download safety

The shared rules (`.part`, rename, reserve, Range, If-Range) are in [network](network.md).

- Downloads request the stored enclosure URL, not an expiring redirect URL. Data is flushed in 512
  KB chunks, then the show's folder is synced on completion.
- A partial file requests `Range: N-`: 206 appends, 200 restarts, and 416 or a range error restarts
  once. A 206 whose Content-Range starts elsewhere than N counts as a refused range.
- **If-Range safety:** within one run, an attempt that came with a strong ETag makes the next
  attempt's Range carry `If-Range`, so a file that changed on the server comes whole instead of
  being joined to the old bytes. No record is kept on the card: a `.part` of an earlier run resumes
  on its size alone.
- A `text/*`, JSON or XML Content-Type is no episode. The card keeps `NET_RESERVE_KB` (32 MiB) free
  (`net_room`, as Subsonic does). Bodies over 2 GiB and paths over 240 bytes are refused.
- Transient failures retry after 10, 20 and 40 s. Certificate, storage and terminal HTTP errors
  fail at once. A non-empty partial survives errors and cancellation; an empty one is removed.
- **Pause keeps the `.part`.** There is no automatic new-episode download or persistent retry queue.
- Active transfers use the stock power timer to prevent standby while allowing screen-off. Visual
  work stops while dark; status and covers update on the first lit page tick. Stock standby
  otherwise stops Wi-Fi and CPU.

## Pins

`PODCAST_PINS` in `tools/pod.py` pins the stock seek and play-speed calls, the speed variable and the
tag-reader hook. Library query hooks are in [payload](payload.md). Every hook preserves stock
behaviour outside its matching podcast path or query.

## Limits

- A recent list is cut at 300 entries, so a show with an archive and more than 300 downloaded old
  episodes shows the newest 300 of them (the Downloaded page's cap is 300 rows).
- A feed of more than 2000 items keeps the newest 2000.
- A refresh that adds an item whose file name equals an older archive item's (two items of one day
  with one title) does not number it "(2)" as the full fetch does.
- A subscribed show's chart row opens the show's page only; an episode beyond the 20 kept items
  falls back to the preview.
- A show set to Oldest First with no archive has its See All row at the end of the list, and
  nothing fetches the archive automatically; leaving the page, Discover or search cancels the fetch.
- A chart's country is shown only on its grey line; a failed chart has no Try Again (switch the
  control or re-enter). Country and storefront names stay English.
- Shows without an Apple id (typed URL, OPML) get no cover from a feed whose image is a
  progressive JPEG.
