# Search

**Sources:** `patch/search.c`, `patch/search.h` (entry points, page geometry), `patch/keyboard.c`
(`keyboard_attach`), `patch/songs.c` `sg_on_search`; asset `ui/m1plus_search.bin`
(`tools/pod_ui.py` `build_search_page`, `keyboard_pad_widgets`), `tools/pod_pages.py` `SEARCH`;
layout model `tools/pod_search.py` (parses the `#define`s of `patch/search.h`, shared by the builder,
the preview and the tests).
Our own library search in the Apple Music manner: a rounded field, a row of chips (Top Results,
Artists, Albums, Songs, Playlists; exactly one selected), rows with a thumbnail, a title and a grey
line, results that follow the typing, and our keyboard embedded at the bottom of the same page. It
replaces stock's `search_page` (a T9 dialog and SQL `LIKE '%x%'`). A Chinese title also matches the
initials of its pinyin (`zjl` finds 周杰伦).

No hook, no new import, no thread. One page-scoped timer; nothing runs outside the page's widgets.

## The page

Window 320 x 450 (numbers in `patch/search.h`).

- **Field** (x 12, y 8, 250 x 36, radius 18, `#1C1C1E`): the keyboard's own field widgets (`kb_*`)
  with the page's text x and room, so the keyboard code measures, cuts and moves the caret as on its
  own page. Placeholder `Search`. A tap on the field shows the keyboard.
- **X** (`btn_return`, x 270): a flat 36 px disc in the field's grey with a white x. Back, as the
  hardware Back key.
- **Chips** (y 52, 34 high): each as wide as its text plus 14 px a side, 6 px apart, measured at
  open. Five English chips are wider than the screen, so the row scrolls sideways (drag of 6 px; a
  tap selects). Selected chip: light grey pill with dark text. No accent colour.
- **List** (y 90 down, under a `#2C2C2E` line): a stock `list_view` with one content view that
  paints the rows itself. With the keyboard up the content is padded by the pad's height.
- **Rows** (60 px, no headers): 44 px thumbnail at x 12 (round for an artist, 4 px corners
  otherwise), title 21 px white and grey line 18 px `#AAAAAA` from x 68, chevron at x 288 on
  artists, albums and playlists (none on songs), hairline x 68..310. Grey line: `Artist`,
  `Album · <artist>`, `Song · <artist>`, `Playlist`.
- **Empty state**: keyboard up, the recent searches or a blank list. `No Results` for a query with
  no match.

**Thumbnails** use the cover cache, loaded lazily through the Albums grid's ring (`patch/grid.c`).

- Album and song: the cache file of artist + album (`cc_album_key`); a song without one takes the
  library album's (`cc_cover_key`). Artist: the first of their albums that has a cover. Playlist
  or no file: the placeholder disc.
- Texts are made on first paint. The cover key is resolved by the loader, never in a paint.
- One cover is decoded per timer tick, never while a query waits and never while the list moves
  (`grid_moving`). A paint that finds a tile without its picture restarts the ended timer.
- The only source size is the 168 px cache file, box-reduced to 44 px.

## Recent searches

The last 5 queries the user committed to, newest first. Committed means a tap on a result or the
keyboard's action key with a non-empty field. Typing saves nothing.

- Trimmed; an empty query is ignored. A query that folds the same (`se_fold`) moves to the top.
  The file is written only when the list changed.
- File `/mnt/data/m1plus/search-history`: UTF-8, one query per line, newest first, at most 63 bytes
  a line. Read once at open. A file that is oversized, has more than 5 lines, an empty line, a
  long line, a control character or a repeat is **no history at all** and is left alone until the
  next save (all or nothing). A failed write keeps the old file.
- Shown when the field has no terms and nothing is listed: header `Recently Searched`, then 50 px
  rows with the query and an x. Nothing is shown with no history. No Clear button.
- A tap on the x (44 x 50 zone) removes the entry. A tap elsewhere on a row puts the query into the
  field and applies it at once, without saving or reordering.
- With the payload off the page does not open, so the file is neither read nor written.

## Live search

`keyboard_attach` puts the keyboard's pad, strip and pop-up on this window, so nothing flashes when
the page opens or the user types.

1. `search_open()` opens the page, attaches the keyboard and starts the timer. It returns -1 when
   a Search page exists or the window is missing; callers then open the stock page.
2. `se_on_text` runs on every change of the committed text and sets a debounce of 5 ticks. Pinyin
   still being composed is not searched until a candidate is taken.
3. One timer (`se_tick`, 40 ms, started on demand) counts down and applies the text 200 ms after the
   last keystroke. Between queries it loads one cover.
4. The library is read once, by the first tick: artists (`0xf004`), albums (`cc_albums`),
   playlists (`0xf00b`), copied; songs (`0xf001`) left in `*pdeq_showlist`, not copied. The songs
   query is last and `g_class_type` is set back to `0xf001`, because the stock album page under
   this page re-runs its query when the class differs. Search never touches the cover-task list.
5. Another page's query replaces `*pdeq_showlist`. `se_valid` is checked on return, on a song tap
   and on paint; a stale list is re-read and searched again. A song tap that found it stale is lost.
6. The keyboard hides on a list drag and on the action key (reads `Search` here); a tap on the
   field shows it. Hidden, the pad is invisible and insensitive.

## Matching

Everything works on code points; the query and each record are folded the same way.

- Case: ASCII, Latin, Greek and Cyrillic.
- Latin diacritics through one range table: `é ü` give `e u`, `ß` gives `ss`, `ø` `o`, `æ œ þ ĳ`
  give `ae oe th ij`. NFD marks are dropped.
- Kana: katakana becomes hiragana; half-width katakana is composed with its dakuten. A dakuten
  stays a distinction (`か` is not `が`).
- Full-width Latin and digits become ASCII; all spaces `' '`; typographic quotes and dashes ASCII.

The query splits at spaces into at most 8 terms. A record matches when every term is a substring of
its key: the folded fields joined by a space, so a term cannot match across two fields. Keys are
cut at 160 code points.

| Type | Key fields |
|---|---|
| song | title (file name when none), artist, album |
| album | album, artist |
| artist, playlist | name |

`Unknown Artist` and `Unknown Album` are never results.

**Quality tiers** (`se_test`): 0 when the key's first field is the whole query, 1 when the key
starts with the first term, 2 otherwise.

**Incremental filtering.** Matches are kept per type, in library order, with their quality. A new
query that starts with the previous one can only match what matched before, so only those are
tested. Any other query (a deleted letter, a different word) scans the library.

**Pinyin initials.** For records with a character in U+4E00..U+9FFF a second key is built where each
such character is the set of its readings' initials. The better quality of the two keys is kept.
It is built only when the first key found nothing or only quality 2, so a Latin title that is the
query ranks above 周杰伦, and a library without Chinese costs nothing extra.

- The initials come from the keyboard's pinyin engine ([keyboard](keyboard.md) "Hanzi to pinyin").
  `pinyin_hold` opens it on the first tick (1 MB) and `pinyin_release` frees it with the page.
  Per character: `get_lemma_id` first (0 = not in the dictionary; never ask `get_splids_for_hanzi`,
  it crashes), then the splids, then the first letter of each spelling (Zh, Ch, Sh are z, c, s).
  The three members are pinned in `PINYIN_PINS` (`tools/pod_pins.py`).
- **Polyphones: every reading counts.** 行 gives h and x, so `yh` and `yx` both find 银行. More
  matches than the right reading, never fewer; the engine has no frequency to pick one.
- A term is initials only: `zhou` does not find 周. A term of 1 letter matches any character with
  that initial. A mixed Latin and initials query (`jay zjl`) does not match: accepted.
- Memory: a 20,992 byte table (one byte per character) and a palette of at most 254 initial sets,
  freed with the page. Without the dictionary or with an engine that fails to open, the search runs
  as before.

## Rows by chip

- **Top Results** (30 rows): best quality first, then types in the order artists, albums,
  playlists, songs, each in library order.
- **A type chip** (Artists 100, Albums 100, Songs 200, Playlists 100): that type's matches, best
  quality first. Selecting a chip builds its rows from the matches already known (no query), resets
  the list to the top and scrolls the chip row so the chip shows.

| Row | Tap |
|---|---|
| artist | `albums_open_artist(copy, row, CLASS_ARTISTS)`, as the Artists page's tap |
| album | `cc_open_album(NULL, 0, stock row)`, our album page |
| playlist | `songs_open_playlist(id, name)`; opened from a Songs page, `sg_stack` sets that page aside |
| song | the library in stock order as the queue (`loadSongList`, class `0xf001`), Now Playing at the song; a missing file toasts `Storage unavailable` |

A tap is a press and lift within `SC_DRAG_PX` on the same row. Back returns to Search.

**Long press.** A press held `RM_LONG_MS` on a result row opens that row's sheet over the page (the
keyboard may stay up under it); the release afterwards opens nothing. There is no "..." glyph.
Only the library's page has it: no hold in the recent searches, none on a source's results (the
sheet is bound only when `se.src` is unset; `se.sheet`, the `row_menu()` widgets last in
`build_search_page`). A drift of `SC_DRAG_PX`, an abort, a release or the page going to the
background stops the hold or closes the sheet.

| Row | Sheet |
|---|---|
| song | the track sheet of the Songs page (`rowmenu_open_src`; Add to Playlist is `picker_open_rec` on the record) |
| album | the album sheet (`rowmenu_open_album`, acts `pins_album_act`, key `cc_album_key`); not for "Unknown Album" |
| playlist | the playlist sheet (`rowmenu_open_playlist`, acts `pins_playlist_act`); Pin Playlist writes no cover keys, so the Home tile shows the placeholder |
| artist | Play, Shuffle \| Pin Artist / Unpin Artist (`rowmenu_open_rows`; `songs_play_artist`); the pin row only for a name the Artists page can pin |

The sheet's `row` is the record's place in `se.lists[kind]` and the acts read the record from there,
so a rebuilt row list changes nothing. `se_free_data` (the library read again) closes the sheet, and
a stale song list (`se_valid`) leaves Add to Playlist doing nothing.

## `keyboard_attach` (`patch/keyboard.c`)

`keyboard_open` is unchanged for its callers (Playlists New, the Developer Keyboard page). Its body
is split: `kb_init` finds and binds the widgets, `keyboard_open` adds the window, title, `KB_DONE`
and Back.

`keyboard_attach(win, placeholder, text_x, text_w, caret_y, flags, on_change, on_go)` runs
`kb_init` on another page's window (`kb.embedded`). The field geometry is the caller's,
`on_change` gets the text after every refresh, the action key calls `on_go` (no page closes), and
the page's destroy handler calls `keyboard_detach`. Also `keyboard_show`, `keyboard_shown`,
`keyboard_text`, `keyboard_set_text`. One keyboard at a time: an attach or open refuses while one
exists. The asset side is `keyboard_pad_widgets()`, shared by both pages under the same names.

## Entry points

- **`search_open_in(scope)`**: `SEARCH_ALL`, `_ARTISTS`, `_ALBUMS`, `_SONGS`, `_PLAYLISTS` (0..4,
  the chip order); another value returns -1. A scoped page shows only that chip and matches only
  that type; recent searches are shared. The Albums and Artists "..." cards use it.
- **Songs page**: `sg_on_search` calls `search_open()`; the stock page opens when it returns < 0.
  Other lists on that page search the whole library.
- **Menu and Extras**: the Search item (ID 21, `ACT_SEARCH`; hidden by default, listed on Extras, movable to the Main Menu in Settings)
  calls `search_open()`, falling back to the stock page. Back returns to the menu at the same place.
- **Album page**: untouched. Stock's own search disc there still opens the stock page.

## Over a library source

`search_open_src(src)` / `search_open_src_in(src, scope)` (`NULL` or `&lib_stock` = the local
search; Navidrome: [subsonic](subsonic.md) "What the user sees") keep the page but let the server match.

- The debounced text (480 ms) calls `sba_search`; rows are the cached `LS_SEARCH_*` lists in the
  server's order, all one quality. `se_tick` loads them when the request leaves LOAD.
- A spinner (`se_spin`, the shared `ls_spin` timer) shows while a request is out. An empty answer
  says `No Results`, offline (`SBA_NOWIFI`) "Connect to Wi-Fi first", a failure the source's line.
- Taps: artist `albums_open_src`, album `album_open_src`, song `so_play_src` (an undownloaded DSD
  track asks `ls_dsd_confirm`). No playlists results.
- Recent searches live in `<Navidrome cache>/search-history`, apart from the local file.

## Titles of another list

`search_titles_open / _hold / _query / _match / _close` give the Podcasts search inside a show
([podcasts](podcasts.md) "Search inside a show") this page's folding, terms and pinyin initials
for a list of titles: one key per title, no page, no library. It refuses while a Search page
exists, and the Search page refuses while it is held. The initials engine is held only on request.
A term of only digits is a whole number there (`se_num_find`); the library search keeps the plain
substring test.
