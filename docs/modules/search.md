# Search

Our own library search, in the Apple Music manner (the reference is the iOS search screen): a rounded field with a clear disc and a round X, a row of chips (**Top Results, Artists, Albums,
Songs, Playlists**) of which exactly one is selected, and rows with a thumbnail, a title and a grey line, results that follow the typing, and **our keyboard embedded at the bottom of the same
page**. It replaces stock's `search_page` (a T9 dialog, then `SearchMusicByName` and its siblings, SQLite `LIKE '%x%'`) on the Songs page. A Chinese title also matches the
initials of its pinyin (`zjl` finds 周杰伦, below).

Code: `patch/search.c` (all of it), `patch/search.h` (the entry point and the page's geometry), `patch/keyboard.c` (`keyboard_attach`, below), `patch/songs.c` `sg_on_search`. Asset: `ui/m1plus_search.bin` (`tools/pod_ui.py` `build_search_page` and `keyboard_pad_widgets`), `tools/pod_pages.py` `SEARCH`. Layout
model: `tools/pod_search.py` (parses the `#define`s of `patch/search.h`: one set of numbers for the builder, `tools/preview_search.py` and the tests). Tests: `test/pod/search.py` (sections
`fold_tests`, `query_tests`, `rank_tests`, `incremental_tests`, `page_tests`, `chips_tests`, `live_tests`, `tap_tests`, `perf_tests`, `recent_tests`, `entry_tests`, `embed_tests`, `asset_tests`).
Preview: `uv run python -I tools/preview_search.py work/mod-release out/preview/search.png` (Top Results with the keyboard up, the Albums chip with it hidden, the empty state, the empty state with recent searches, the Songs chip;
each panel also as `search-<name>.png`; thumbnails are stand-in colours). **No hook, no new import, no thread; one page-scoped timer; nothing else runs from outside the page's widgets.**
Strings: `Top Results`, `Song`, `Playlist`, `Recently Searched` (new, 13 languages), `No Results`, `Artist`, `Search`, `Artists`, `Albums`, `Songs`, `Playlists` and the stock `album` (existing keys).

## The page

Window 320 x 450 (the numbers are `patch/search.h`; `pod_search.py` mirrors them):

* **Field** (x 12, y 8, 250 x 36, radius 18, `#1C1C1E`): the keyboard's own field widgets (`kb_field`, `kb_mag`, `kb_hint`, `kb_text`, `kb_caret`, `kb_clear`) with the page's text x (36) and room (178),
  so the keyboard code measures, cuts with an ellipsis and moves the caret exactly as on its own page. The placeholder is `Search`. A tap on the field (a pointer-up on `kb_field`) shows the keyboard.
* **X** (`btn_return`, x 270, 46 x 44 touch, drawing `se_close`: a flat 36 px disc in the field's grey (#1C1C1E, pressed #3A3A3C) with a white 13 px x, as high as the field and on its centre line; the 42 px glass disc of the navbars looked larger than the 36 px field beside it): Back (`pod_on_back`). The hardware Back key does the same.
* **Chips** (`se_chips`, y 52, 34 high): each chip is as wide as its text plus 14 px a side, 6 px apart from x 12 (`PS.chip_layout`, texts measured in the 16 px chip font at open: the page's
  language); with the five of English the row is wider than the screen, so it **scrolls sideways** (a drag of 6 px, clamped to the ends; a tap selects). The selected chip is a light grey pill
  (`se_chip_hl`, `#E5E5EA`, radius 15, a view behind, moved under the chip) with dark text (`label_chip_on`); the others are white text. The texts are painted by the row's
  `EVT_AFTER_PAINT`; no accent colour anywhere (the reference's blue chip is grey).
* **Line** under the chips (y 88, `#2C2C2E`), then the **list** (y 90 to the window's bottom): a stock `list_view` > `scroll_view` holding ONE content view that paints the rows itself (the Artists
  page's pattern; the keyboard covers the list's lower part, so with it up the content is padded by the pad's height and the list scrolls clear of it).
* **Rows** (60 px, no headers): a 44 px thumbnail at x 12 (**round for an artist**, 4 px corners for an album, a song and a playlist), the title (21 px white) and the grey line (18 px, `#AAAAAA`)
  from x 68, a chevron (the Artists page's, `pod_make_chevron`) at x 288 on artists, albums and playlists and none on songs, and a hairline from x 68 to 310 under every row. The grey line is
  `Artist`, `Album · <artist>`, `Song · <artist>` or `Playlist` (translated; the album word is the stock key `album`).
* **Thumbnails** use the covers we already have and are loaded lazily: an album's and a song's is the Cover Flow cache file of its artist + album (`cc_album_key`, `cc_url`; a song whose own file is
  missing takes the library album of that name's, `cc_cover_key`), an artist's the cover of the first album of theirs that has one, a playlist's and anything without a file the stock placeholder disc (`p_default`),
  all through the Albums grid's ring (`patch/grid.c`; `grid_art` decodes one cover; `GRID_MAX_ROUND` is 22 for the round ones). The texts of a row are made when it is first painted (`se_prep`: formatting only, 16 tiles
  of each shape: the rows in view, two beyond and the history); **the cover key is resolved by the loader** (`se_art`: `cc_cover_key` / `se_artist_cover`, the cache file lookups on the SD card, one probe per key: `cc_cover_key` hands back the url it found to `grid_art_url`), never in a paint. **One cover is decoded per tick of the page's timer**, never while a query is waiting, so typing is not blocked by decoding, and **nothing is read or decoded while the list moves** (`grid_moving`: a finger dragging it or its fling; the tick keeps looking while a tile is missing and loads when the list stops, as the Songs and Albums loaders do). A row with no cover file ends as the placeholder (`grid_art` sets `art` 2), so `se_cover_next` does not pick it again and the timer ends. The timer ends when nothing is left, so **a paint that finds a tile without its thumbnail starts it again** (`se_cover_next` in `se_on_paint`): a chip change or a scroll makes
  new tiles after the timer ended. The source is the cache's only size (168 px JPEG, the Songs page's rows read the same file), box-reduced to 44 px per decode; there is no smaller tier.
* **Empty state** (the page as it opens): the keyboard up on its capital page, the field with its placeholder and caret, the chips, and **the recent searches** (below) or, with none, an empty list and no text. **No Results** (`label_status`) shows
  for a query that matches nothing; an emptied field goes back to the empty state.

## Recent searches

The last `SE_REC_MAX` (5) queries the user **committed to**, newest first: a tap on a result (`se_open_row`, the applied query) or the keyboard's action key with a non-empty field (`se_on_go`, `keyboard_text()`). Typing saves nothing.
The text is trimmed (spaces, tabs); an empty one is ignored. An entry that folds the same (`se_fold`: case, diacritics, kana, width) moves to the top, replaced by the new spelling; the sixth drops the oldest. The file is written
**only when the list changed** (the same query again at the top writes nothing).

* **Storage:** `/mnt/data/m1plus/search-history` (`SEARCH_RECENT_FILE`, patch/home.h; `.tmp` beside it, `home_write_atomic`): UTF-8, one query per line, newest first, each a `\n` end, at most 63 bytes a line. It is read once when the page opens
  (`se_rec_load`); a file that is oversized, has more than 5 lines, an empty line, a line of 64 bytes or more, a control character or a repeat (by the same fold) is **no history at all** and is left as it is until the next save. A failed write keeps the old file.
* **Shown** when the field has no terms and nothing is listed (`se.rm`, set by `se_layout`): the list view is the same content view, now painting `se_paint_recent`: a header `Recently Searched` (grey, 18 px, in a `SE_REC_HEAD_H` 40 px band,
  x 16), then rows `SE_REC_ROW_H` 50 px high: the query (white, 21 px, the results' title style, cut with an ellipsis at `SE_REC_TEXT_END` 262), an x (`pod_make_cross`, a 12 px grey stroke drawn like the chevron, no image file, centre x 292) and the
  hairline from x 16. Texts are the grid's tiles (`se.rt`, cut once). Nothing is shown with no history: the page stays blank as before. No Clear button.
* **Touch** (the same press / lift rule as the results, `SC_DRAG_PX`, the press must start and end in the same row **and the same zone**): the x zone is `SE_REC_X` 266 .. +44 px (44 x 50 px); a tap there removes the entry (`se_rec_remove`, the file is rewritten, the list laid out again;
  nothing is searched). A tap elsewhere on a row puts the query into the field and the keyboard's text (`keyboard_set_text`, patch/keyboard.c, as if typed) and applies it at once (no debounce); it does not save or reorder. The header and the air
  under the rows are dead; a drag does nothing (and hides the keyboard, as everywhere on the list).
* **Kill switch:** the page does not open with the payload off, so nothing reads or writes the file then.

## Live search

The keyboard is not a page of its own here: `keyboard_attach` (below) puts its pad, candidate strip and key pop-up on this window, so **nothing flashes** when the page opens or when the user types
or searches. The flow:

1. `search_open()` (the Songs page's Search button) opens `m1plus_search`, attaches the keyboard (`se_on_text` for the text, `se_on_go` for the action key), lays the
   chips out and starts the page's timer with `wait` 1. It returns -1 when a Search page exists already or the window or its widgets are not there; both callers then open the stock search page.
2. Every change of the field's **committed** text calls `se_on_text`: it ignores a repeat (a layer or page switch re-reports the same text), keeps the text and sets `wait` to `SE_DEBOUNCE` (5).
   The Chinese layer's pinyin still being composed is not in the field, so it is not searched until a candidate is taken (space, a tap on a candidate or the action key commits it).
3. **One page-scoped timer** (`se_tick`, `SE_TICK_MS` 40 ms, started on demand, removed with the page, ended by the tick that has nothing to do): each tick counts `wait` down; at zero the text is
   applied (`se_apply`: the library is read if it has not been, the query searched, the rows of the selected chip built). That is **200 ms after the last keystroke**. Between queries the same
   tick loads one cover; it returns the timer's end (RET_OK) when there is nothing to load.
4. **The library is read once**, by the first tick (the page has been shown by then): `loadLocalClassList(0xf004)` copied (the Artists page's list), `cc_albums()` (the Albums page's, copied),
   `loadLocalClassList(0xf00b)` into `*pdeq_playlist` copied (patch/playlists.c's way) and `loadLocalClassList(0xf001)` left in `*pdeq_showlist` (the Songs page's list, not copied: the rows are
   record numbers). Stock queries are page state, run only from this page in front (its timer, never a key's handler). The songs query is last, and `g_class_type` is then set to `0xf001`: the stock
   album page under this page compares `g_class_type` with the class it saved (its to-foreground handler `0x5266d4`) and re-runs its own query when they differ, and rebuilds its header, whose cover then stays the placeholder (stock shows the cover file only when the cover thread finishes). Search is never over a live album page (it opens from the Songs page; an album page opened from a result is destroyed by Back), so this does not happen with ours. Search never touches the cover-task list: only the tap that opens an album does (`cc_open_album`).
5. **A replaced list.** Another page's query replaces `*pdeq_showlist` (an album or an artist was opened from a result). `se_valid` (the pointer and the size) is checked when the page comes back
   (`EVT_WINDOW_TO_FG`), when a song tap is made and when paint needs the list; a stale list re-reads the library on the timer and searches again at the same query, and a song tap that found
   it stale is lost. Artist, album and playlist rows use the page's own copies.
6. **Hiding the keyboard**: dragging the list (the scroll_view takes the gesture and aborts the press: `se_on_abort` with a press in progress), and the keyboard's action key (`kb_go`, which reads
   `Search` here). A tap on the field shows it again. Hidden, the pad is invisible **and insensitive** (it takes no touch), the caret goes, a held key or a pop-up in the air is let go, the content
   is no longer padded. Going behind another page leaves the keyboard as it is.

## Matching

Everything is code points. `se_next` decodes UTF-8 (a byte that is not UTF-8 is its own code point), `se_cp` folds one, `se_cat` appends a text's folding to a key, `se_fold` is the test entry
(external, so the compiler keeps its general form). **Folding and multi-term matching:**

* Case: ASCII, Latin, Greek (capitals and small letters, final sigma, tonos) and Cyrillic (`ё` is `е`).
* Latin diacritics: Latin-1, Extended-A, the Extended-B letters songs use, Extended Additional and the Vietnamese block, as one table of ranges (`se_latin`): `é ü` give `e u`, `ß` gives `ss`,
  `ø` gives `o`, `æ œ þ ĳ` give `ae oe th ij`, `ł đ ð` give `l d d`, `ı İ` give `i`. NFD input (the combining marks U+0300..036F) loses its marks.
* Kana: katakana and `ヽヾ` become hiragana; half-width katakana become the hiragana of the full-width form, with a following `ﾞ` / `ﾟ` (or U+3099, U+309A, U+309B, U+309C) composed onto the
  letter before it. A dakuten stays a distinction (`か` is not `が`); `ー` stays. Full-width Latin and digits become ASCII, every kind of space is `' '`, typographic quotes and dashes become ASCII.

The query is folded and split at spaces into at most `SE_TERMS` (8) terms. A record matches when every term is a substring of its key: the record's fields folded and joined by a space (a term has
no space, so it cannot match across two fields): a song's title (its file name when it has none), artist and album; an album's album and artist; an artist's or a playlist's name. A key is cut
at 160 code points. The rows `Unknown Artist` / `Unknown Album` (id -1) are never results.

**Quality** (`se_test`): 0 when the key's first field is the whole query (the terms joined by single spaces), 1 when the key starts with the first term, 2 otherwise. **Incremental filtering:** the
records that match are kept per type in library order with their quality (`cand`, `sc`, `nc`; every match, not just the rows shown). A new query whose folding **starts with** the folding of the
one they are of (`se_search`: the previous code points compared) can only match what matched before, so only those are tested, in place (a match is written at or before where it was read); any
other query (a deleted letter, a different word) scans the library. `have_prev` is cleared whenever the library is read again.

**Pinyin initials.** Where a record has a character of U+4E00 .. U+9FFF (`se.seen`, set by `se_cat` while the first key is built), `se_search` builds a second key, `se_key(.., py=1)`:
the same folding, but a character with readings is an entry `SE_MASK | set of initials` (bit 0 `a` .. bit 25 `z`). `se_test` runs on it as on the first key; `se_find` takes an entry with the mask bit
as a match for any letter in its set. The better quality of the two is kept. It is built only when the first key found nothing or only quality 2 (an initials match is never quality 0 and a
prefix of initials is quality 1: a Latin title that is the query ranks above 周杰伦), and only when the engine is held, so a library without Chinese costs nothing extra.

* **Where the initials come from:** the keyboard's engine (`keyboard.md` "Hanzi to pinyin"). `se_load` (first tick) calls `pinyin_hold` (patch/keyboard.c): the engine is opened (1 MB, about 76 ms)
  or taken over from the Chinese layer, and stays open for the page's life, whatever the layer does; `se_on_destroy` calls `pinyin_release` after `keyboard_detach`. Per character
  `se_read_hanzi`: `get_lemma_id` first (0 means not in the dictionary: no reading, never `get_splids_for_hanzi`, which crashes), then `get_splids_for_hanzi`, then the first letter of each
  `get_spelling_str` (Zh, Ch, Sh are z, c, s). The three members are pinned prologues in `tools/pod.py` (`PINYIN_PINS`, `py_lemma_id` / `py_splids` / `py_spelling` in stock.h); no new hook.
* **Polyphones: every reading counts.** 行 (hang heng xing) is h and x, so `yh` and `yx` both find 银行 and `xz` and `hz` find 行走. More matches than the right reading alone (`yz` is not one),
  never fewer; the engine gives no frequency to pick one by. A term is initials only: `zhou` does not find 周 (the initial of 周 is `z`); a mixed Latin and initials query (`jay zjl`) does not match on the device (accepted; the scripted test's mix passes, the real dictionary's does not), and any term of 1 letter matches any character with that initial.
* **Memory:** one 20,992 byte table (a byte per character: not asked, no reading, or an index) allocated with the library and freed with the page, and a palette of at most 254 distinct sets
  (1 KB; the 26 single letters first, a full palette falls back to the first reading's letter). Keys stay on the stack (2 x 162 words). Each distinct character asks the engine once.
* **Cost** (emulation, payload instructions of the first scan): 20,000 songs with Chinese titles and artists 44.1 M without initials, 79.2 M with (5,000: 11.4 M, 20.1 M; the engine's own
  calls are stock code and not counted); a Latin library adds nothing. Without the dictionary file, with an engine that fails to open or with no dictionary objects the search runs as before and
  nothing calls the engine (`pinyin_tests`: `test/pod/search.py`, the engine scripted in `harness.py` by `py_dict`; the real engine's functions are tested in `test/pod/pinyin.py`).
* On the device (build zEQLAAAAB): `zjl` finds 周杰伦 against the real dictionary; a mixed `jay zjl` does not match (accepted). Not verified: the first tick's extra 76 ms.

## Rows by chip

* **Top Results** (`SE_CAP_TOP` 30): the best quality first (0, 1, 2) and inside a quality the types in the order artists, albums, playlists, songs, each in library order. So an artist or album
  named exactly what was typed comes first, then names that start with it, then the rest, interleaved by match quality.
* **A type chip** (Artists 100, Albums 100, Songs 200, Playlists 100): that type's matches, best quality first, library order inside a quality. Selecting a chip builds its rows from the matches
  already known (no query, no library read), resets the list to the top and scrolls the chip row so that the chip shows.

| Row | Tap |
|---|---|
| artist | `albums_open_artist(copy, row, CLASS_ARTISTS)`: the Albums page scoped to that artist, as the Artists page's tap (Cover Flow on the artist if the window will not open). Back returns to Search |
| album | `cc_open_album(NULL, 0, stock row)`: our album page, as the Albums page's tap |
| playlist | `songs_open_playlist(id, name)` (the id is `REC_DISC`), else the stock Songs page with the playlist class, as the Playlists page's tap. Search opened from a Songs page has that page under it: `sg_stack` (patch/songs.c) sets its state aside so ours opens over it (the stock page only if the window will not open); Back returns to Search, and the Songs page below is restored when ours is destroyed |
| song | the library in its stock order as the queue (`loadSongList`, class `0xf001`, the row's own index wins for duplicate file names), Now Playing at the song (`se_play`, the Songs page's `sg_play_at`); a missing file toasts `Storage unavailable` |

A tap is a press and a lift within `SC_DRAG_PX` on the same row (a drag, an abort or a background take it back).

## `keyboard_attach` (patch/keyboard.c)

`keyboard_open` is unchanged for its callers (Playlists New, the Developer Keyboard page: same asset, API and tests). Its body is split: `kb_init` finds the widgets by name and binds them, sets the
first page and layers (the same for both ways of having the pad); `keyboard_open` adds the window, the title, `KB_DONE`, Back and the destroy handler. `keyboard_attach(win, placeholder, text_x,
text_w, caret_y, flags, on_change, on_go)` (flags 0 for Search and Radio; `KB_PASSWORD` is the Wi-Fi password page's, [keyboard](keyboard.md)) runs the same `kb_init` on another page's window (`kb.embedded`): the field's inner geometry is the caller's (`kb.tx`, `kb.tw`, `kb.cy` instead of the page's
constants), `kb_refresh` ends by calling `on_change` with the text, the action key calls `on_go` (after committing a pending candidate; no page is closed), and the page's destroy handler calls
`keyboard_detach` (the timer, the engine's megabyte, the state). `keyboard_show(0/1)`, `keyboard_shown()`, `keyboard_text()` and `keyboard_set_text(s)` (the field replaced as if typed; a recent search tapped) are the rest of it. One keyboard at a time: an attach or an open
refuses while one exists. The asset side is `keyboard_pad_widgets()` in `tools/pod_ui.py`, which both pages end with: the pad, the strip and the pop-up are the same widgets by the same names
(a test compares the two assets' copies byte for byte).

## Entry points

* **`search_open_in(scope)`** (patch/search.h; `search_open()` is `search_open_in(SEARCH_ALL)`): `SEARCH_ALL`, `SEARCH_ARTISTS`, `SEARCH_ALBUMS`, `SEARCH_SONGS`, `SEARCH_PLAYLISTS` (0..4, the chip order); any other value returns -1. A scoped page opens with that chip selected and is the same page otherwise: the chip row draws and hit-tests only that chip (`se.lo` .. `se.hi`, the chips' places start at `SE_CHIP_X`, so a tap where another chip would be does nothing), `se_search` matches only that type (the other types' counts stay 0), recent searches are shared. Same -1 fallback as `search_open`; no caller uses a scope yet (`scope_tests`).

* **Songs page**: `sg_on_search` calls `search_open()` instead of `navigator_to("search_page")`; the button does nothing in select mode or with the sort card open, as before. The other lists on
  that page (Favourites, a playlist, an artist's songs ...) search the whole library as the stock search did. When ours will not open the stock page does (`search_open() < 0`).
* **Menu and Extras**: the **Search** item (ID 21, `m`, `ACT_SEARCH`; hidden from the menu by default, listed on Extras, movable to the Main Menu in Settings > Home Screen > Main Menu) calls `search_open()` from `on_row`, and the stock `search_page` when that returns < 0, as the Songs page does. The menu or Extras page stays under the Search page untouched, so Back returns to it at the same scroll place.
* **Album page**: untouched. Stock's search disc (made by the toggle navbar builder `0x526a3c` after a select cycle) still opens the stock search page; a custom album page will replace it. A result's album row opens the album page.

## Cost

Test `perf_tests` (`m.icount`, payload instructions; the stock queries cost extra, and are made once): reading the library (the first tick) is 0.5 M besides the stock queries; a **full scan** of
5,000 songs (with 300 artists, 800 albums) is 20 M, of 20,000 songs 76 M (about 3,800 a song; some tens of milliseconds to a few hundred on the device); a query that extends the last one costs only
its matches (a query matching one title in eight: 2.4 M and 8.2 M); typing a query letter by letter runs one full scan for the first letter at most and the rest on the shrinking matches, a
deleted letter one scan.

## Not verified on a device

Tried on the device with zEQLAAAAB and working: the embedded keyboard on the page, scrolling results with thumbnails, the chips, the menu item, pinyin initials, recent searches with the x.

1. The time of the first query on a 20,000 song library (the emulation says about 76 M instructions), with the first tick's stock queries and pinyin engine.
2. The texts in the 13 languages (widths checked against the font, not seen).
3. The CJK text cut in recent rows (the test's measure is the harness's 8 / 16 px per character).
4. The scoped mode (`search_open_in`, below): emulation only, and nothing opens it yet.

## Over a library source

`search_open_src(src)` (NULL or `&lib_stock` = `search_open`). For Navidrome the page keeps its field, chips, rows and covers, but does not match in memory: the debounced text calls
`sba_search`, the rows are the cached `LS_SEARCH_ARTISTS / ALBUMS / SONGS` lists (sbsrc.c, in the server's order, all one quality), and `se_tick` loads them when `sba_state(SBA_K_SEARCH)`
leaves LOAD (rows are empty meanwhile). Offline (`SBA_NOWIFI`) the status line reads "Connect to Wi-Fi first", otherwise "No Results". Taps: artist `albums_open_src`, album `album_open_src`,
song `so_play_src` with the song results. No playlists chip results, and no recent searches for a source (not read, not written).

## Deferred

Highlighting the matched text, a "show all" row past the caps, a Clear button for the recent searches, the Folders and stock Artists / Albums
pages' own search buttons (stock pages; the Albums grid and Artists pages have none), album and song covers beyond the cache (no extraction here), playlist mosaics.

## Over a library source

`search_open_src(src)` / `search_open_src_in(src, scope)` (Navidrome, `subsonic.md` "Search") run this page over a source: the server matches (`sba_search`, debounced 480 ms), the rows are the cached answer in the
server's order, taps open `albums_open_src` / `album_open_src` / `so_play_src` (a song that is an undownloaded DSD track asks the `ls_dsd_confirm`, as the other pages do). Recent searches use `<Navidrome cache>/search-history` instead of the settings file. A spinner (`se_spin`, turned by the shared `ls_spin` timer) shows while a request is
out; an empty answer says `No Results`, a failure the source's line.
