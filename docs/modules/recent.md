# Recently Played

**Sources:** `patch/recent.c` (recording, file, shelf), `patch/grid.c` / `grid.h` (cells),
`patch/menu.c` (`menu_shelf`), `tools/pod_ui.py` (`shelf()`), constants `SH_*`, `RC_*`, `GRID_*` in
`offsets.inc`, file model `tools/pod_recent.py`.
The Home menu shows up to six recent albums in a two-column shelf below Daily Mix. The covers use
the shared Albums grid, with album and artist labels. The shelf scrolls with the menu and is absent
from the normal menu instance. No stock hook or address: it uses its own window, widgets, events
and one page timer.

## Layout

`pod_shelf` is a `view` 310 wide (`SH_W`), a child of `pod_scrollview` after the last shown row
(Settings) and before the mini bar's spacer. It is hidden and insensitive in the asset. Its height
depends on the albums: `ceil(albums / 2)` rows, `SH_H(n)` = 234, 434 or 634 for 1, 2 or 3 rows.
The asset has the largest (`SH_HMAX`); the payload sets the real one with `widget_resize` before
the rows are arranged, and `menu.c` sums it into `virtual_h`.

| part | geometry |
|---|---|
| header `pod_sh_head` | label at (10, 17), 300 x 22, 20 px white, never scrolls (ellipsis), insensitive; text key `Recently Played`, so all 13 languages follow. Ink 20..36: 20 px of air above, 8 px below |
| cell | the Albums grid's own: `GRID_COVER` 144 at x 12 and 164 (`GRID_GAP` 8), first row at y 44 (`SH_TOP`), pitch `GRID_CELL_H` 190 + `GRID_ROW_GAP` 10 |
| cover | 144 x 144, four 8 px (`GRID_R`) corners blended into black, tile opaque |
| album line | 4 px under the cover, 144 x 22, 18 px white, one line, ellipsis (style from hidden label `pod_sh_title`) |
| artist line | directly under, 144 x 20, 15 px `#AAAAAA`, one line, ellipsis (`pod_sh_sub`) |
| below | none (`SH_BOTTOM` 0): scrolled to the end with the bar up, the last line is `MB_GAP` (8) above the pill |

Cells fill row by row. `SH_TILES` = `GRID_COLS` x `SH_ROWS` (3) = `RC_MAX` = 6, so the shelf shows every
album the file keeps (`recent.c` `#error`s if they differ). The header is a stock label; the
covers and text lines are painted by the shelf itself. The widest header translation fits the
label in all 13 languages.

## The list file

`/mnt/mmc/.m1plus/recently-played` (model: `tools/pod_recent.py`):

```
M1R2\n
<id: 8 hex>\t<cover key: 8 hex>\t<0|1>\t<album>\t<artist>\t<path of a track of the album>\n
```

One line per album, most recent first, at most 6.

- **Identity:** the id is FNV-1a of the album title with ASCII letters folded to lower case
  (`rc_id`), and not the artist. Stock's album list (`getAllAlbum`) groups by album title alone,
  NOCASE. An album is therefore the same album exactly when stock has one row for both: a
  compilation is one entry, and two albums of one title are one entry (a tap opens that row).
- **Cover key:** the Cover Flow cache key (`cc_album_key`) of the album row. Until the row is
  looked up (flag `0`) it is the playing track's own key; after (flag `1`, `rc_resolve`) the row's.
- **Strict read** (`rc_load`): exact magic line, at most 6 lines of exactly six tab-separated
  fields, non-zero id and key, no repeated id, flag 0 or 1, non-empty album, no control bytes,
  every line newline-terminated, album/artist under `RC_STR` (96) bytes, path under `RC_PATH`
  (256), file under `RC_FILE_MAX` (3072). Anything else, or no file, is an empty list.
- **Writing:** control bytes in tags become spaces and over-long fields are cut on a UTF-8
  boundary, so a tag can never make the file invalid. The path is the last way to find the stock
  album row.

## Recording

`recent_note(track)` is the shared helper. Callers are the mini bar's `mb_work` (Home menu in
front, every 500 ms) and Now Playing's `np_work`. It compares the album key with the most recent
one held in RAM first and returns without touching a file or calling stock.

- An empty album tag is not recorded.
- A new album goes to the front; one already in the list moves there; the list is capped at six.
- The file is written by `m1_card_write` after a fresh read (a card swap never carries the old
  card's list over). With no card nothing is recorded. That is one write per change of the most
  recent album.
- A failed write loses only that entry.
- When `recent_note` returns 1, the bar's tick calls `recent_refresh()`, so a new album shows at
  once.
- Recording runs whether or not the shelf is switched on.

## The shelf

`home_menu_opened` (`patch/home.c`) calls `recent_start(win)` after `minibar_start`, for the Home
instance only.

- **Start:** looks up `pod_shelf`, `pod_scrollview` and the two style labels, registers the window
  and shelf events, arms a one-shot `RC_FIRST_MS` (150 ms) and `EVT_SCROLL` on the list, makes the
  grid, then reads the file and the setting. If there is an album and the switch is on, it sizes
  and shows the shelf (`menu_shelf`). Nothing is decoded at first paint. Any missing widget,
  refused registration or timer means the shelf is never shown and nothing moves.
- **Cells** (`patch/grid.c`, shared with the Albums page): 144 x 144 RGBA bitmaps, 81 KB each,
  plus one shared placeholder disc when some tile has no picture. The cover is the Cover Flow
  cache file of the entry's cover key, box-reduced to 144 px, corners blended once. No file or
  undecodable picture gives the shared disc.
- **Resolving the cover key** (`rc_resolve`): `cc_albums()` loads the stock album list and matches
  the row by title (NOCASE; "Unknown Album" never), then by the recorded path. It runs only from
  the menu's to-foreground, one unresolved entry per event, at least `RC_RESOLVE_MS` (5000 ms)
  after the menu opened. It never runs at boot, in a tick or in paint, and never from Now Playing's
  tick: the query leaves the album list in `*pdeq_showlist`, which a stock song list under Now
  Playing would then draw (folder icons, wrong playback). An album the library has no row for is
  asked once and stays unresolved.
- **Re-keying** (`recent_rekey`): the Home cover build ([homecover.md](homecover.md)) hands over its
  album list, and every entry takes its row's key and artist again, so the tile never keeps a disc
  for a key the builder does not make.
- **Lazy decode:** a cell is made only when its top is less than one row (`POD_ROW_H` 52) below
  the viewport's bottom. Cells go row by row, top first, one cover per `RC_TICK_MS` (30 ms) tick,
  never in paint. `EVT_SCROLL` and the to-foreground re-check. At the top of the default menu only
  row 0 is resident. `EVT_WINDOW_TO_BG` removes the timer; destroy frees the grid.
- **Paint** (`rc_on_paint`, the shelf's `EVT_AFTER_PAINT`): resident bitmaps, then the album and
  artist texts, cut with an ellipsis once. It allocates and decodes nothing. The scroll view
  clips the shelf like any row, and the mini bar's pill paints over it.
- **Refresh:** `EVT_WINDOW_TO_FG` re-reads the file and the switch and rebuilds the tiles. A tile
  whose album moved to another cell keeps its cover; the rest are made again.

## Touch

The shelf is one `view` with its own hit areas. A cell is its cover and two text lines
(`grid_cell_at`); the header, margins, gaps and empty places are dead.

- The shelf never consumes an event, takes no grab and draws no pressed look. The scroll view
  takes every drag (it grabs at 10 px and sends `EVT_POINTER_ABORT`).
- A press on a tile released closer than `RC_TAP_PX` (10) on both axes, on the same tile, opens
  that album. Ten pixels is the scroll view's own drag threshold, so a press taken as a drag
  never opens an album.
- **Long press** (`RM_LONG_MS`, `rowmenu_hold_start` from `rc_on_down`; drift of `SC_DRAG_PX`, an abort or an early release cancels it): `pins_album_sheet` opens the Home pins' sheet (`rm_scrim` / `rm_card`, owned by `patch/pins.c`) for the tile's album: the album sheet, **Play**, **Shuffle** | **Pin Album** / **Unpin Album**, **Add to Playlist** | **Play Next**, **Play After** ([pins](pins.md)). The hold forgets the press, so the release opens no album. Without the pins' widgets (or the card's pins unavailable) nothing opens and a tap still opens the album.
- A touch that stops a coasting list presses nothing (`sc_down` in `patch/scroll.c` swallows it).
- The menu going to the background forgets a press.

**Opening** (`rc_open`, on a tap only): `cc_albums()` loads the stock album list. The row is found
by the entry's cover key, else by album title (NOCASE; "Unknown Album" never), else by the
recorded track path. Then `cc_open_album(NULL, row)` runs the Albums grid's own sequence. If the
album is gone, nothing happens and there is no toast.

## Menu order (`patch/menu.c`)

Stock's `list_view` layouter stacks visible children in child order and sums their heights into
`virtual_h`. The scroll view's children are: the shown rows (menu items, Extras, Settings), the
Daily Mix section `pod_daily` ([dailymix.md](dailymix.md)), the shelf, the hidden rows, the
spacer `pod_pad`. `mn_arrange` restacks them with `widget_restack`.

`menu_shelf(win, on)` shows, hides or re-arranges the shelf and keeps `yoffset` (clamped), so a
list at the top does not jump. A hidden shelf (no album, switch off) is skipped by layout and hit
test, so the menu is exactly the plain one. If the asset is not ours it puts the visibility back.

## Setting

**Settings > Home Screen > Recent Albums** is a switch row (`ACT_SHELF` 16, `HOMESET_PAGE` row 1),
on by default, saved in `/mnt/data/m1plus/home-recent-albums` (`0` off, `1` on; no file or
anything but `0` is on). The menu reads it at start and at every to-foreground. The label is its
own key "Recent Albums", because "Recently Played" is too wide for the switch row in Spanish and
Ukrainian.

## Failure behaviour

Every failure gives the plain menu: a missing widget, a refused `widget_on`, no timer, a foreign
asset, an unreadable or malformed file, or the switch off. A cover that does not decode shows the
placeholder or grey. A gone album does nothing on tap.

## Limits

The shelf checks once per second while covers are pending and the screen is off, resumes on its
first lit check, and stops when the covers are loaded.
