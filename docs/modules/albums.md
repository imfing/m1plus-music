# Albums

**Sources:** `patch/albums.c`, `patch/viewsort.c` (the "..." card), `patch/grid.c`,
`patch/covercache.c`, `patch/azlist.c`, `tools/pod_ui.py` (`navbar(albums=True)`,
`view_sort_card`).

Albums opens a grid or list in the last selected mode. A tap on an album calls `cc_open_album`; Back
returns to the same position. Cover Flow opens above this page. If the window cannot open, the Home
dispatcher opens stock Albums. No hook.

**"Unknown Album" row.** Stock `getAllAlbum` appends a last row (`REC_ID` -1, "Unknown Album" /
"Unknown Artist") to every non-empty list, whether or not a track lacks an album tag. The library
list (`cc_albums`, so Albums, Cover Flow, Home, Daily Mix and the rest, and the Pod's Albums rows
and cover pane) keeps it only when one query finds such a track:
`select * from songtable where album is null or album = '' limit 1`, run through the hooked
`toolsQueryDbTable` (the Library filter applies) by `cc_drop_unknown_album`. Otherwise the row is
popped with libcstl's `deque_pop_back` (`cstl_pop_back`, [queue](queue.md) "Clear"). A failed query
or an unpinned libcstl keeps the row. An artist's or composer's list never has the row (stock adds
only its "All songs" row).

## Scoped to an artist

A tap on a row of the Artists page (`albums_open_artist(list, row, scope)`) opens the same window
and mode on that artist's or composer's albums.

- The page holds a copy of the artist's row and the album list and cache keys from
  `coverflow_artist_albums` (`loadAlbumList(0xf004 / 0xf005, artist)`; each album keyed like the
  library album of the same name; the case-insensitive index from 24 albums is shared with Cover
  Flow's scoped page, [artists](artists.md)).
- **"All songs" tile.** The stock trailing "All songs" row (id -2) is kept as the last tile with two
  albums or more, dropped with one. Same tile size, the placeholder disc (key 0: no cache file,
  never scanned or built), "All Songs" (stock key `local_allsong`) over the artist's name. Its tap
  opens our Songs page on every song of the artist (`songs_open_artist(row, scope)`; a composer's on
  class `0xff14`, [songs](songs.md)), or the stock page on the All songs row if that will not open.
- An album tap is `cc_open_album(row, scope, index)`: class `0xff01` / `0xff02`.
- The Cover Flow button opens Cover Flow scoped to the same artist (`coverflow_artist`) above the
  page; Back returns here, then to the Artists page. The mode file is shared with Home > Albums,
  toggling writes it, and Cover Flow is never stored. If the window cannot open the caller opens
  Cover Flow on the artist.
- The cache scan uses the scoped keys and skips the All songs row. The deque, list and keys are
  freed on destroy. The large title is the name (296 px, ellipsis; the small title is fitted to 110
  px); an empty list keeps the large title with "No albums" (or "Update Library first") under it; an artist's header page without a source shows the navbar title instead.

### Artist header

An **artist's** or **composer's** page has the artist header in place of the large title. A
composer's never has the circle (no photo is looked up for a composer). The library page keeps the
large title.

| Part | Geometry |
|---|---|
| circle | `AL_PHOTO_D` 88 px at x `AL_PHOTO_X` 116 (centred), y `AL_PHOTO_Y` 8; only with a photo in the cache |
| name | `al_name`, 22 px white in a 286 px box at x 17, y `AL_NAME_Y` 110 (`PH_NAME_X/_W/_H`), ellipsis; `al_title` hidden and insensitive |
| pills | Play and Shuffle at y 148 (`AL_HEAD_PILL_Y`, moved with `widget_move`) |
| rows start | `AL_HEAD_END` 188 (`al_top()`: 188, plus `GRID_ROW_GAP` in the list) |
| small title | shows from `AL_HEAD_COLLAPSE` 132 |
| no photo | the same widgets `PH_SHIFT` 96 higher: name y 14, pills y 52, block ends `AL_PILLS_END` 92, small title from 36; `albums.c` asserts the relations (`_Static_assert`) |

- Every offset goes through `al_top()` (paint, hit test, loader window, `al_first`, `al_set_mode`,
  content height).
- The circle is the artist's -168 photo, or the lead artist's (`ap_lookup`,
  [artists](artists.md) "Artist photos"). The loader's first tick (`al_head_load`, before covers, not
  while the list moves) decodes it (`cc_decode` box 2: the centred square of a square or landscape
  file, a portrait one cut from its top third as `pv_square` does) and cuts the circle (`ap_circle`).
  A photo that does not decode takes the circle away (`al_layout(0)`: no placeholder on this page).
- A touch on the circle, name or pills' block opens nothing. A page without `al_name` (an asset that
  is not ours) keeps the large title and the pills at y 52.

## Long press

On the library page (grid and list) an album held `RM_LONG_MS` opens the album sheet, Play, Shuffle | Pin Album, Add to Playlist | Play Next, Play After (`al_on_hold`, `al_sheet`); see `docs/modules/pins.md`.

## Layout and state

| Element | Contract |
|---|---|
| Window | `ui/m1plus_albums.bin`; 320 x 450 px with a 50 px navbar |
| Scrolling | `albums_listview` > `albums_scrollview` > `view_grid`, plus `scroll_bar_m` |
| Large title | `al_title`, first child of `view_grid`: 32 px white at x 12, 296 wide, `SG_TITLE_H` 52 px high, insensitive; "Albums", or the artist's name. It scrolls with the content, so every row, cell and hit test starts `AL_TOP` (= `SG_TITLE_H`) down; `al_coff()` (offset less 52) is what paint, loader and `al_first` use. A touch on it opens nothing. A mode switch keeps the first album at the top |
| Small title | `label_title` in the navbar, hidden at rest; shown from `SG_COLLAPSE` 46 (`m1_title_gone`; 204 under the photo header, 36 without a photo) from the scroll_view's `EVT_SCROLL`, with `img_nb_fade` while the offset is above 0. Without scroll events it stays shown |
| Grid | two 144 px covers, 12 px margins, 8 px column gap; 190 px cells on a 200 px pitch; album 18 px white, artist 15 px grey, one ellipsized line each; corners 8 px blended into black |
| List | 64 px rows, 52 px covers at (10, 6), text from x 74 to x 278 (`LIST_TEXT_W_CHEV`), title 21 px, artist 18 px; hairline to x 310 (`LIST_HAIR_END`); grey chevron at x 288 (`LIST_CHEV_X`) marks that a row opens a page; corners 4 px in the bitmap alpha |
| Navbar | Back, small title (x 58 to 168), one glass capsule: Cover Flow 168, "..." 214, Now Playing 260 (46 / 46 / 60 px). No Search button (it is the card's first row). A library source without Cover Flow (`LS_CAP_COVERFLOW`) hides 168, the "..." takes the left cap at 214 and the title runs to 214; without `LS_CAP_SEARCH` the card has sorts and Grid / List only |
| Mode file | `/mnt/data/m1plus/albums-view`: 1 grid, 0 list; otherwise `ALBUMS_DEFAULT_GRID` |
| Order file | `/mnt/data/m1plus/albums-sort`: one character, `0` Title, `1` Artist, `2` Recently Added, `3` Year, or `a`..`d` for the same reversed; missing or anything else is Artist, not reversed. The retired `album-order` file is moved into it once and deleted by `cc_sort_mode` ([settings](settings.md)) |
| A-Z list | list mode, Title order, whole library: section headers, pinned header, rail (below) |
| Year list / grid | Year order, whole library: headers by year / decade (below) |

The stock mobile scrollbar is required: the list-view layouter enables vertical scrolling through
it. The content view and `virtual_h` both hold the full content height as 32-bit integers. Empty
content is hidden and insensitive.

Switching the mode (the card's Grid or List row) stops a running scroll animation, drops tiles,
changes geometry and keeps the first visible album. It moves the tick and writes the choice with
`home_write_atomic`. Missing required style labels or content widgets close the page.

## A-Z list (list mode, Title order)

The Songs page's furniture ([songs](songs.md) "The A-Z rail", `patch/azlist.c`): `al.az` with `top`
= `al_top()` and the 64 px rows; `az_row_y` (28 px headers between sections), `az_at` (a header and
the title block are dead), `az_span`, `az_rows_end`; `grid_t.az` makes `grid_list_paint` read it.

- Sections are the initial of the title by the name order ("The " and leading punctuation skipped):
  `cc_name_initial`, CJK by pinyin initial, kana by Hepburn initial. "#" first holds digit and symbol
  titles; Z-A mirrors. A stray stays in the section around it. `al_sections` runs at open and after
  each sort (`al_resort`).
- The Artist and Recently Added orders, the grid, and an artist's own albums are plain lists.
- Rows: text to x 278, chevron 288, hairline to 310 with no rail; with the rail shown
  (`SG_RAIL_INSET` 26) all three move left by it. The grid has no rail; the card's Grid row hides
  rail and bubble, List shows them (`al_rail`).
- **Index Rail** and **Section Headers** (Settings > Library) are read at open (`az_prefs`).
- A mode switch keeps the first album under the pinned header (`al_first`, `al_set_mode`). The
  asset has the furniture's hidden labels, rail and bubble (`build_grid_page(az=True)`); a page
  without them stays a plain list.

## Year

**Year list** (list mode, Year order): the same furniture with years in place of letters
(`az_year_sections`, `az.years`).

- One scan gives the years: `cc_album_order_years` is `cc_album_order_mode(.., CC_SORT_YEAR, rev)`
  that also hands back `so_year` (the earliest year tag 1000..2999 by stock row, 0 none) in
  `al.ykey`. A changed year with the same order re-sections the page (`al_reload_with`).
- A section is a run of equal years, newest first (reversed: oldest first). Albums with no year (and
  the "Unknown Album" row, when kept) form one last section headed "Unknown"; no such albums, no section.
- The rail has an entry per decade that has albums, labelled by its first year ("2020", "2010",
  ...), and one per century before 1900; an entry jumps to the first section of its decade. The
  Unknown section has none. Labels are the rail's 12 px style centred in the 36 px column; the
  touched entry's disc stretches to a pill. A finger's y maps to an entry directly (no dots). The
  bubble shows four digits at `SG_BUBBLE_PX_YEAR` 40 px.
- With fewer than two entries there is no rail and rows keep the full width (headers stay), unlike
  the A-Z list. At most `SG_RAIL_ITEMS` 20 entries are drawn; surplus oldest centuries go to the
  last entry. `SG_MAX_SEC` is 128: more distinct years, or no memory, gives a plain list.
- A tap on a header or the pinned band opens nothing (`az_pin_hit`). The artist's and composer's
  pages and a library source's page stay plain lists.

### Year grid (grid mode, Year order)

Headers are **by decade, not by year**: one album per year must not put a header over every
half-empty row.

- `al_sections` hands the display-order years to `az_decade_sections`, which fills `al.gz` (an
  `az_t` with `years` 2, `row` = `PITCH`, `count` = the grid rows, so `az_hdr_y`, `az_row_y`,
  `az_at`, `az_span`, `az_paint_heads` work unchanged on rows of `GRID_COLS` albums) and
  `al.gstart[s]`, the first album of section s.
- A section is a run of equal `az_year_key` values (a decade from 1900, a century before: "2020s"
  .. "1900s", "1800s" ..; no year is "Unknown", last) and **starts a grid row of its own**, so the
  last row of the section before may hold one tile. Tiles keep their size, columns and gaps.
- The header is the list header's (`SG_HDR_H` 28 px) directly above its section's first row,
  scrolls with the content, and the section at the window's top stays pinned.
- `al_g_row`, `al_g_first`, `al_g_last` and `al_cell_y` map an album to its row and back; paint
  (`al_paint_grid`), `al_span`, `al_window`, `al_next_load`, `al_on_load` and the hit test
  (`al_cell_at`: a header, the pinned band, the gaps and the empty slot of a partial row are dead)
  use the same map. Nothing is computed per paint.
- Section Headers off, the other orders, the artist's and composer's pages, a source's page, or no
  memory leave `gz.nsec` 0: the plain grid. The grid has no rail. Decades never exceed `SG_MAX_SEC`
  (at most 23 keys).

## View sort card

Every page with a "..." menu uses `patch/viewsort.c` (`vs_bind`, `vs_view`, `vs_menu`,
`vs_offer`, `vs_fit`) and `tools/pod_ui.py` `view_sort_card`. Users: Albums (this page), Artists /
Genres / Composers ([artists](artists.md)), Songs ([songs](songs.md)), [folders](folders.md),
[playlists](playlists.md).

**This page's card** (`btn_more`, x 214): an Apple-style grouped menu on the card's own glass
(`vs_glass7`, `mod_icons.GLASS_VIEWSORT`). Full-window scrim `#00000082` (a tap closes it), right
edge 311, top y 52, seven 50 px rows, pressed 6 % white.

1. **Search Albums** (slot 6, glyph `pod_ic_vssearch`): closes the card, then
   `search_open_in(SEARCH_ALBUMS)` ([search](search.md)), the library search if that will not open.
2. **View**: Grid, List (glyphs `pod_ic_vsgrid` / `pod_ic_vslist`), tick on the current view; a tap on
   the other switches.
3. **Sort**: Title, Artist, Recently Added, Year, a tick on the current one with its direction line
   (15 px `#AAAAAA`) under it.

Hairlines (13 % white) sit between groups only. The tick column is x 14 on every row; a card of
action rows only (nothing tickable) has none, and `vs_fit` moves glyphs to x 14 and labels to x 42.
The card is as wide as its widest label from its own x plus 20 px (`VS_TEXT_SLACK` 4, then the
16 px margin: a label exactly as wide as its text gets an ellipsis on the device), 206 (`VS_CARD_MIN`) to 292,
measured again at every open. Strings: `Search Albums`, `Title`, `Grid`, `List`, `A–Z`, `Z–A`,
`Newest First`, `Oldest First` (13 languages in `tools/pod_i18n.py`).

**Order and direction.** A sort row saves `albums-sort` (`cc_sort_mode_set(mode, rev)`, **atomic; a
failed save changes nothing**), rebuilds `al.order` and restarts the list at the top. A row not
ticked starts in the order's default direction; **tapping the ticked row reverses it**. Defaults:
Title and Artist A-Z, Recently Added and Year newest first.

`cc_album_order` (`patch/covercache.c`) builds `order[]`, an array of stock row numbers, by
`cc_heapsort`; the stock deque is unchanged. Grid, list, Cover Flow and Home's cover scan all use it.

- **Title**: an explicit order over album titles by the name rule (`cc_name_keys` / `cc_key_cmp`:
  white space and "The " dropped, CJK and kana by initial, accented Latin by base letter, digit runs
  by value, symbols and scripts with no initial first under "#"; ties keep the stock position; with no memory for the keys, the stock list, backwards for Z-A).
  Stock's own title comparator puts symbol-led titles after Z and kana after Latin, which no section
  labelling can show.
- **Artist**: the album row's artist, then title, each by the name order
  ([artists](artists.md) "Order and the album Artist rule"). Unknown Album (id -1) is last.
- **Recently Added** ranks each album by its newest song (`time_create`), **Year** by the earliest
  year tag (1000..2999) among its tracks, newest first, albums with no year last. Both read the
  library song list once (`loadLocalClassList(0xf001)` under `sort_flag` 3; the flag and browsing
  class are put back). A song with no album is ignored.
- Reversed, the key comparison flips. "Unknown Album" (-1), the scoped All Songs row (-2), albums
  with no year and albums with no song stay last in either direction. Recently Added and Year depend
  on `time_create`, which a rescan rewrites ([recent-albums](recent-albums.md)).
- `songtable.year` is the file's tag (`taglib_tag_year`); an untagged album sorts last.

**Scoped artist page.** One shared order (`albums-sort`, direction included); the All Songs row
stays last. The scoped card has no Search Albums row (it searched every album, not the artist's) and, since one artist
has one artist name, no Artist row: `vs_bind(.., sorts)`
takes the set of sort rows offered, hides the rest, packs the card from the top and picks the glass
of its row count.

| Page | Card |
|---|---|
| a library artist (`al_can_find`: not a composer, not a source, not Unknown Artist) | Find Artist Photo (slot 6, glyph `pod_ic_vsphoto`), Pin Artist / Unpin Artist (the Select slot 7, `al_pin_row`, glyph `pod_ic_vspin` / `pod_ic_vsunpin`; see [pins](pins.md)), hairline, Grid, List, Title, Recently Added, Year: seven rows, 350 px, `vs_glass7` |
| a composer, or a source's artist | the same without the action row: five rows, `vs_glass5` |

- Find Artist Photo closes the card and calls `onlineart_open_artist(name)`
  ([onlineart](onlineart.md) "Artist photos"). `al.finding` is set while that page is up, and
  `al_on_fg` compares `ap_epoch()` with the value kept: a picked photo switches the header in place
  (`al_recheck_done`).
- A row still reports its own number (Recently Added 2, Year 3). When the saved order is Artist the
  page shows Title order and ticks Title (`cc_scoped_sort`); a tap on that ticked row reverses the
  direction and saves Title. A row of this card writes `albums-sort`, so it changes the library
  Albums page too.
- The artist-scoped Cover Flow reads the same order (`load_artist`: `cf.order`, Artist as Title), so
  the shelf and the grid list albums alike. Its cache keys stay by stock row.

**Artist page: pills and years** (a composer's page runs the same code on the composer queries).

- Under the large title the Songs page's **Play** and **Shuffle** pills (`btn_play` / `btn_shuffle`,
  flat `#1C1C1E`, pressed `#333335`, 40 px high, radius 20): Play 145 wide at x 10, Shuffle 145 at
  x 165. In the artist header they sit at y 148 ([Artist header](#artist-header)). Play is every song
  of the artist in order, Shuffle the same list in stock Shuffle mode from a random song, both
  `songs_play_artist` (`patch/songs.c`): the two stock queries of `songs_open_artist` then
  `so_play(0xff11, list, 0 / -1, SO_IN_ORDER / SO_SHUFFLE, sg_open_player)`. A composer's page plays
  class `0xff14`.
- The grey line under each album is its **year**: `al_open` reads the artist's songs once
  (`songs_artist_list`) and `cc_album_years` fills `al.years` by stock row (earliest year tag among
  the album's songs). An album with no year has an empty second line; so does the All Songs tile.
  Cost is bounded by the artist's songs, nothing per paint. An album shared with other artists takes
  the earliest year among this artist's tracks, which can differ from the library-wide year of the
  Year order.

**Design.** Each page gets its own order file (listed in `pod_pages.SETTING_FILES` and
`patch/setfiles.c`, in the same order) and its own order function.

- `tools/pod_ui.py` `view_sort_card`: the page's asset appends the card last (names `vs_*`); the
  page binds it at open and keeps its own state. The asset always has four sort rows, two view rows,
  the Search row and the Select row (`VS_SORTS` 4, `VS_ROWS` 8). `vs_bind`'s `sorts` mask offers
  rows (`VS_WITH_VIEWS`, `VS_WITH_SEARCH` -> `VS_SEARCH`, `VS_WITH_SELECT` -> `VS_SELECT`); sort row
  0 must stay. `vs_offer(v, mask)` changes the mask later and repacks an open card. A row not
  offered is hidden and insensitive. The hairline under the first group sits under the last of it and
  hides when nothing follows.
- Glass is height-specific (`VS_GLASS_FMT`: `vs_glass1`..`vs_glass7`, `mod_icons.GLASS_VIEWSORT*`);
  another height needs its own picture.
- A page keeps its sort and direction (`vs_menu(on, sort, rev, list)`) and its handler reverses the
  ticked row. `vs_dated(v, mask)` picks which sort rows read Newest First / Oldest First (default
  rows 2 and 3; Songs passes row 3 alone).
- The Artists page's Show group uses view rows 4 and 5 (a click arrives as `VS_SORTS` or `+1`).
- `VS_TAIL` in the offered mask moves slot 9 after the view rows as the card's last row, the
  hairline above it (Radio's Clear History, retexted and red by the page).
- Widget names are per window, so the same `vs_*` names work on every page.
- Per page: Songs ([songs](songs.md)) folds Search, Sort, Select and Recently Added's view toggle
  into one card; Folders: Select + Name, Date Modified, Type (`vs_glass4`); Playlists: two cards on
  one `vs_card` ([playlists](playlists.md)).

## Album order and initial selection


At open, `find_playing` (`patch/coverflow.c`) checks `cc_playing` (`mclGetPlayPos` and the play
queue at `PLAY_QUEUE`, bounded by `deque_size`). It matches the album by `cc_album_key` (FNV of
artist/title), then by title ignoring ASCII case, for compilations. Selection priority: the playing
album, then the saved centre album key (`POSITION_FILE`, `coverflow-position`, kept only by the main
Cover Flow: an artist's shelf does not read or write it), then the first album. One lookup, no
polling.

## Covers and painting

The shared grid supplies tile records, rounded artwork, ellipsis fitting, painting and hit testing.
Recently Played uses the same helpers. Covers come from `r<album-key>-168.jpg`, reduced by an area
average of the centred square. An absent file or empty "no art" marker uses the placeholder disc. A
`.bad` marker (an album whose extraction hung, [coverflow](coverflow.md)) also keeps it out of the
missing set.

- Twelve resident tiles cover visible cells, prefetch and recent history. Grid artwork uses about 1.1
  MB including the placeholder; list artwork about 130 KB.
- Paint draws resident covers and text only: no decoding, bitmap allocation or timer creation. Text
  is measured and ellipsized once per tile. Drawing is limited to the 400 px viewport.
- The 16 ms loader decodes at most one cover per tick, visible cells nearest the viewport centre
  first, then one grid row or two list rows ahead in the scroll direction. Visible tiles are
  retained; others use LRU. Decoding pauses during a stock drag or scroll animation (`grid_moving`).
  Backgrounding stops the loader; foregrounding restarts missing work. If scroll events cannot be
  registered, the loader polls while the page is open.

## Cache building

The page starts the shared cover worker and its scan ([covercache](covercache.md)): a 50 ms startup
timer scans in batches of 64 albums, nearest the initial viewport first; a 500 ms poll makes
placeholder tiles eligible for reload as files arrive. Only one page owns the worker, so opening
Cover Flow releases the Albums build first. Destroy stops owned work and removes timers.

`cc_build_stop` never waits for the thread: an exited worker is joined and freed; one still inside a
job (stock's art call cannot be interrupted) is cancelled and orphaned, and joined by the next
`cc_build_open` / `cc_build_busy` / `cc_build_orphan` after it exits. Meanwhile `cc_build_open`
refuses and the Albums and Songs start timers ask again every 500 ms for up to 10 s. A refused
timer or thread, a busy worker or under 16 MB free space leaves placeholders. A scan with nothing
missing is not repeated in that page's life.

**A source's artist page** (`al.src`, [subsonic](subsonic.md) "What the user sees") decides the layout
by the server's picture: `al_head_url` asks `src->cover` for the artist record (key 0; `al_has_photo`
is 1 when the file is there). There is no cache worker re-check. A picture on its way gives the plain
header and arms the shared cover poll; when the file is there `al_layout(1)` switches the circle in
place. None (-1) is remembered in `al.rk` 2. Never a placeholder circle on this page.

## Artist photo re-check

The header layout is decided when the page opens from the cache (`al_has_photo`: `ap_lookup` finds a
non-empty -168 file, the artist's or the lead artist's). Once the page's own cover build is over, or
at once when it had nothing to build (`al_recheck`, once per open), the page asks the cover worker
to look at this artist again (`ap_recheck`, [artists](artists.md) "Re-check on open"): the job holds
the first track of each of the artist's albums (the page's album copy; no library query) and uses the
page's set and its 500 ms poll (`al_on_build`), so a page that closes cancels it. A busy worker
means no re-check. When the set is over `al_recheck_done` asks the cache again: a photo that
appeared or went switches the layout in place (`al_layout`: name and pills move by `PH_SHIFT`, the
content is resized, the offset kept inside it); a replaced photo (`ap_epoch` moved) is read again.
The Artists page behind compares `ap_epoch` when it is in front again (`ar_on_fg`).

## Input

The stock scroll view owns drag, fling and end stops; [gestures](gestures.md) handles coasting
catches. A release on the original cell within 10 px on both axes opens the album. Drag, abort,
backgrounding or a touch that stops coasting clears the press and opens nothing. List presses use
`#333334` (`LIST_PRESS`). See [album-page](album-page.md) for album opening, [coverflow](coverflow.md)
for the shared cache worker and [rows](rows.md) for common library styling.

## Returning to the page

The local library's lists are read once at open and again each time the page returns to the
foreground (`al_on_fg`, `al_reload_with`): the unscoped list (`cc_albums`) and an artist's or
composer's (`al_scoped_reload`: albums, cache keys and years). Songs deleted on an album page opened
from it remove that album, and a tile never opens a stale row. The same albums in the same order with
the same years and keys swap the records only; a different order, year or cover key makes the tiles
again. A failed read of the unscoped list keeps the grid. A source's page keeps its gen-driven reload.
