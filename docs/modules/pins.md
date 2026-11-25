# Home pins

**Sources:** `patch/pins.c` / `pins.h` (file, API, section), `patch/artists.c` / `albums.c` (artist entries), `patch/menu.c` (`menu_pins`, `mn_arrange`),
`patch/grid.c` (tiles), `patch/rowmenu.c` (the sheet), `patch/songs.c` (`sg_pin`, `sg_pin_row`),
`patch/albumpage.c`, `patch/recent.c`, `tools/pod_ui.py` (`pins()`, `row_menu(pins=True)`), `tools/pod_pins_home.py` (file model), `PIN_*` in
`patch/offsets.inc`, `tools/mod_icons.py` (`RM_PIN_ICONS`).

Albums and playlists pinned at the very top of the Home menu, above Cover Flow and the other rows, as
a grid of covers. They scroll with the list. Only the Home instance has them. No stock hook or address:
the section is the menu asset's own widgets, events and one page timer.

## Layout

`pod_pins` is a `view` 310 wide (`PIN_W`), the first child of `pod_scrollview` while shown. It is hidden
and insensitive in the asset, and has no header. Nothing pinned: it stays hidden, is skipped by layout and
hit tests, and Home is exactly the plain menu.

| part | geometry |
|---|---|
| tile | 3 columns (`PIN_COLS`) of 90 px covers (`PIN_COVER`) at x 12 (`PIN_MARGIN`), 8 px apart (`PIN_GAP`); cover = (310 - 2 x 12 - 2 x 8) / 3 |
| short row | with 1 or 2 pins the single row is centred in the section (same size and 8 px gap; first tile at x 110 or 61), as in Apple Music; from 3 pins on the grid starts at x 12 and a partial last row (4 or 5 pins) starts from the left |
| corners | 6 px (`PIN_R`), blended into black like the grid's; the tile is opaque |
| top | 6 px (`PIN_TOP`) above the first row |
| name | 6 px under the cover (`PIN_TGAP`), 20 px high (`PIN_TH`), 15 px white, centred under the cover, one line, ellipsis (style from hidden label `pod_pin_title`) |
| rows | `PIN_PITCH` 126 apart (cover + 6 + 20 + 10 `PIN_ROW_GAP`) |
| below | 8 px of air (`PIN_BOTTOM`) before the first menu row |
| height | `PIN_H(rows)` = 130 (1 row) or 256 (2 rows) |

At most six pins (`PIN_MAX` = `PIN_COLS` x `PIN_ROWS`), in the user's order (a new pin joins the end, the others keep their places), filled row by row. `menu.c` puts
`pod_pins` first in the child order, sets its height with `widget_resize` before the rows are arranged
and gives the rows a y offset of its height (`mn_arrange`); the Daily Mix section, shelf and spacer follow
as before, and `virtual_h` includes it.

## Covers

Covers come from the Cover Flow cache, as on the Albums grid, one per `PIN_TICK_MS` tick, never in paint,
`PIN_FIRST_MS` after the menu opened.

- **Album:** the cache file of its cover key, box-reduced to 90 px; no file gives the shared placeholder disc.
- **Playlist:** the Playlists page's 2 x 2 mosaic (`grid_mosaic`, one quarter a tick) of up to four album
  keys stored in the file when the playlist was pinned, so Home runs no query to draw it. None gives the
  placeholder. A playlist with a chosen cover ([plcover](plcover.md) "The stored choice", looked up by id and name) shows
  `plc_art` instead (`grid_plc`), and its tile follows a change of the file (`tcov`).

## Touch

A tile is its cover and its name; margins, gaps and empty places are dead. The section never consumes an
event and the scroll view takes every drag.

- **Tap** (released within `SC_DRAG_PX` of the press, same tile): an album opens our album page
  (`cc_open_album`, as Recently Played); a playlist opens our Songs page (`songs_open_playlist`, the
  Playlists page's tap, the stock page if ours will not open). An item the library does not list now (or an empty or failed list)
  says "Not found"; the pin stays.
- **Long press** (`RM_LONG_MS`, `rowmenu_hold_start`) lifts the tile (see Reorder) and opens at once the bottom sheet (a drag of `SC_DRAG_PX` closes it again; a release where it was leaves it open) bound with `rowmenu_bind_album` (`rm_scrim` and `rm_card` are the window's last two children, over the bar, `row_menu(album=True)`). The rows follow the tile (`pn_open_sheet`, tables through `rowmenu_open_rows`, [rowmenu](rowmenu.md) "Sheets from a table"; acts `RMA_*`, Unpin is `RMA_PIN` for every kind): an album has the album sheet,
  **Play**, **Shuffle** | **Unpin Album**, **Add to Playlist** | **Play Next**, **Play After** (glyphs `play`, `shuffle`, `pin-off`, `list-plus`, `list-start`, `list-end`; `pc_sheet6`); a playlist the same with **Unpin Playlist** (`rowmenu_open_playlist`; Add to Playlist, Play Next and Play After act on its songs through `pins_playlist_act`, in the order of the playlist, "Not found" when it is gone or empty); an artist **Play**, **Shuffle** | **Unpin Artist**; a song **Play** | **Unpin Song**.
  Play and Shuffle start the whole album or playlist as the album page's Play pill and Shuffle disc do
  (`so_play`, Now Playing opens): album via `loadAlbumList`, `loadAlbumdetailList`, `loadLocalClassList`;
  playlist via classinfo[1] and `loadLocalClassList(CLASS_PLAYLIST_SONGS)`.
  Play Next and Play After on an album load every track of the album in order (`pn_album_tracks`) and pass them to `upnext_add` ([queue](queue.md)), toasting the result with `rowmenu_upnext_toast` (or "Not found" when the library lacks the album; the pin stays).

## Reorder

Hold a tile `RM_LONG_MS` without moving (`pn_on_hold`): it **lifts**, drawn `PIN_LIFT` (4) px larger on each side over
the others (`pn_lifted`; no colour, no dimming). From then on the scroll view must not slide, so the lift turns the list's
`yslidable` off (`pn_scroll`: `widget_get_prop_int` / `widget_set_prop_int` on `pod_scrollview`, as the 10-Band editor does)
and grabs the touch (`widget_grab(sv, section)`; stock refuses a second grab, then the moves go where they go and only the
sliding stays off). `pn_lift_end` gives both back on release, EVT_POINTER_ABORT, the window leaving the front and its end.
Without `pod_scrollview` there is no lift: the hold only opens the sheet.

- **The hold** takes the grab, turns the list's sliding off and opens the sheet (`pn_open_sheet`). **Released where it was** (within `SC_DRAG_PX` of the press): the sheet stays open. A drag closes it (`rowmenu_close`).
- **`yslidable` off does not last on its own.** The sheet showing or hiding (`widget_set_visible`) marks the window for layout, and stock's list_view layouter turns `yslidable` back on at every layout (`scroll_view_set_yslidable(sv, 1)`, `0x60b1e4`). The grab only routes the events to the section first; the scroll_view's own handler still runs after it, so the list scrolled with the drag and flung at the release. While a tile is lifted `m1_lift_sv` (patch/scroll.c, shared with Edit mode's reorder on playlists) names the list, and the list gesture hook (`m1plus_scroll_event`, [gestures](gestures.md)), which sees every pointer event before the list does, clears the `yslidable` byte again. That also keeps its late-drag abort away from the drop.
- **Abort** (`EVT_POINTER_ABORT`) while lifted closes the sheet too, as well as ending the lift; the window leaving the front already did.
- **Dragged** (a move of `SC_DRAG_PX` or more after the lift; `pn_follow`): the sheet closes (`rowmenu_close`); the tile follows the finger and
  the others close up live around the slot the finger is over (`pn_slot`: the grid cell under it by the same
  `pn_x0` / `pn_x` / row geometry, a point beside or above the grid its nearest cell, clamped to the pins there are;
  `pn_tile_in(slot)` is the tile each slot shows; the target slot is left empty).
- **Release** (`pn_drop_lift`, `pn_commit`): a release `SC_DRAG_PX` or more from the press is a drag even when no move event reported it (sheet closed, slot under the release point). Inside the section, the file is read again, the pin moved to the slot and
  saved atomically; a failed save puts the old order back; the section is redone (covers kept). Released outside the section
  (above or below), or aborted: the old order, nothing saved.
- A move beyond `SC_DRAG_PX` **before** the hold fires cancels it (`rowmenu_hold_move`) and the list scrolls as usual.

`tools/pod_pins_home.py`: `pin` appends, `move(entries, i, j)` is the model of a reorder.

## The file

`/mnt/mmc/.m1plus/home-pins` (on the card, like `recently-played`: no card, no pins and nothing written, a pin action answers failure; another card has its own pins; model `tools/pod_pins_home.py`):

```
M1P1\n
<kind>\t<key: 8 hex>\t<cover key x 4: 8 hex each, tab-separated>\t<name>\t<path>\n
```

One line per pin, in the user's order (a new pin is appended), at most six.

- **Kind** `a` album, `p` playlist, `s` song or `r` artist. The kind field is the type: a later kind adds a
  letter and the rules for its fields; every other reader still rejects the file.
- **Album:** key = `pn_album_id`, FNV-1a of the title with ASCII letters folded (the same identity as
  Recently Played's `rc_id`: stock groups albums by title alone). First cover key = `cc_album_key` of the
  album row (never 0; the other three 0). Path = a track of the album (to find the row again; may be empty).
- **Playlist:** key = the stock playlist id (`REC_DISC`, from 0). Cover keys = distinct album keys of its
  songs, non-zero first then zeros. Path empty. A playlist pin is its id **and** its name, because
  `createPlayListItem` reuses the lowest free id after a delete: the stock row is matched on both (`pn_pl_find`),
  and `pins_has_playlist` / `pins_unpin_playlist` / `pins_label_playlist` take the page's name (`sg.name`), so a
  replacement playlist of the same id is not pinned by the deleted one's pin. Pinning the replacement replaces the
  stale entry in place (never two entries for one id).
- **Strict read** (`pn_load`): exact magic, at most 6 lines of exactly eight fields, known kind, non-zero key (a playlist's id may be 0),
  no (kind, key) twice, eight lowercase hex digits per cover key, non-empty name, no control bytes, every line
  newline-terminated, names under `PIN_STR` (96) bytes, paths under `PIN_PATH` (256), file under
  `PIN_FILE_MAX` (3072). Anything else shows no pins.
- **Read errors never overwrite** (`pn_load` returns 0 or -1; `pn.good`): an absent file (`ENOENT` / `ENOTDIR`) or one
  with no bytes is an empty list. A failed open (any other errno), a read error, or a file that does not parse
  (junk, a short or cut file, a later version's kind, a seventh pin, too big) is **unreadable**: the display keeps
  its list (a read error) or shows none (a malformed file), and `pn_save` refuses while the last load did not
  succeed, so a pin, unpin, reorder or library check leaves the file as it is. Pin and Unpin show "Can't update
  pins" (`PINS_FAIL`). A malformed file is not
  repaired or backed up: it may be one a later version wrote, and a guess could erase pins. The user deletes
  `.m1plus/home-pins` (Settings > Files, Wi-Fi Transfer) to start again.
- **A failed write changes nothing** (`pn_pin`, `pn_unpin`, `pn_check`, `pn_commit`): the list in memory is put back as
  the file has it, so the section redone from it keeps the tile. Pin and Unpin (API and the sheet's Unpin) say "Can't
  update pins" and answer failure; the library check's re-key stays silent and waits.
- **Writing** (`home_write_atomic`): control bytes in tags become spaces and long fields are cut on a UTF-8
  boundary, so a tag never makes the file invalid.

## Interfaces (`patch/pins.h`)

`pins_pin_album(album, ckey, path)`, `pins_pin_playlist(id, name, keys, nk)`, `pins_unpin_album(album)`,
`pins_unpin_playlist(id, name)`, `pins_has_album`, `pins_has_playlist(id, name)`, `pins_label_album`, `pins_label_playlist(id, name)`
(the translation key for a "Pin" / "Unpin" row), `pins_rename_playlist(id, old, name)` (Rename Playlist: the pin keeps its place and cover keys; a file that cannot be written says "Can't update pins"). Each reads the file fresh and writes it back; none needs a
menu. A pin that would be the seventh shows the toast "Unpin an item first" and returns `PINS_FULL`; a pin
already there returns `PINS_OK` and changes nothing. A live menu shows the change at its next to-foreground
(`pn_on_foreground` reads the file and redoes only the tiles that changed).

**Playlist entry:** the Songs page of a playlist: "..." card, the fourth row (slot `VS_ACT3`, under Select, Rename and Clean
Up) **Pin Playlist** / **Unpin Playlist** (`pod_ic_vspin` / `pod_ic_vsunpin`). `sg_pin_row` sets
words and glyph at each open; `sg_pin` takes the mosaic keys from the list the page holds
(`grid_mosaic_keys`). The Playlists page's row long press (`pl_on_hold`: the playlist sheet, Play, Shuffle | Pin Playlist /
Unpin Playlist, Add to Playlist | Play Next, Play After; [playlists](playlists.md)) is another entry; it pins with the page's mosaic keys and
runs the other rows through `pins_playlist_act(id, name, act)` (Play and Shuffle are `pins_play_playlist(id, name, shuffle)`).

## Checks against the library

Once per menu, at the first to-foreground at least `PIN_CHECK_MS` (5 s) after the menu opened
(`pn_check`; the stock album list is loaded there, as for Recently Played's key resolve, never at boot,
in a tick or in paint), an album pin whose row has another cover key takes it.

No pin is ever removed for a missing item, by the check or by a tap: only Unpin removes. A list read
while Auto Update rebuilds `songtable` (after a card insert or the end of a USB transfer, 100 rows
per commit) is short but not empty, so it cannot tell a gone item from one not scanned yet. A tap
on an item the library does not list (or with no list at all, empty or failed) says "Not found" (album, playlist, artist) or "Can't play"
(Play / Shuffle); a song whose file is gone (`ENOENT` / `ENOTDIR` with the card in, `pn_missing`)
says "File not found".

## Failure behaviour

A missing widget, refused registration, no timer or no memory leaves the plain menu. An unreadable or malformed file shows no pins (or the last list) and is never written (see "Read errors never overwrite"). No card in: no pins are read, a pin action answers `PINS_FAIL` and writes nothing. A failed write leaves the old file. A cover that does not decode shows the placeholder.

## Album long press and song pins

- **Albums long press** (`patch/albums.c`, `al_on_hold`, library page only, grid and list): a press held `RM_LONG_MS` on an
  album (not the All Songs tile, not "Unknown Album") opens the album sheet (`rowmenu_open_album` on `rowmenu_bind_album`'s
  widgets, `row_menu(album=True)`): **Play**, **Shuffle** | **Pin Album** / **Unpin Album** (by `pins_has_album`), **Add to Playlist** |
  **Play Next**, **Play After**. A row goes to `pins_album_act(album, ckey, path, act)`: `pins_play_album`, the pin, `pins_queue_album`,
  or for Add to Playlist `pn_add_album`: the album's tracks (`pn_album_tracks`, into `*pdeq_showlist`), every one marked, `picker_open`
  (our picker over the page; "Not found" without the album, "Adding Failed" when the picker cannot open).
  The hold clears the press, so the release opens nothing; a drift of `SC_DRAG_PX`, an abort or an early release cancels it.
- **Recently Added album grid** (`patch/songs.c`, `rv_on_hold` / `rv_sheet`): the same hold and the same sheet on the
  Songs page's track sheet widgets (`rowmenu_open_album`), for the tile's library album row ([recent-albums](recent-albums.md)).
- **Song pins**, kind `s`: key = FNV-1a of the file path (case as written, `pn_song_id`), first cover key = the album's cover
  key (`cc_album_rep_key`, else the record's own key), name = title (the file's name without one), path = the file (never
  empty, under `PIN_PATH`). A track of a CUE image shares its file with the others, so a song is its path **and
  `REC_CUE_START`**: the key hashes the path, then `(h ^ start) * 16777619` when the start is above 0 (a plain file
  keeps the old key), and the path field is `<start>@/path` (1 to 9 digits, no leading zero; a field starting with `/`
  is start 0; `pins_song_ok(path, cue)` counts the prefix in the 255 bytes). Tile = album cover + title. Tap and sheet
  **Play** start the album from that track (`pn_play_album` finds the track by path and start). The album is found
  from the song's own library record first: `pn_song_album` queries `select * from songtable where fileurl='<path>'`
  (every row of the file, the CUE rows told apart by start) and `pn_find` looks the record's album title up in the album
  list before the saved cover key, the title and the representative path (the whole tag is compared, up to
  `PN_TAG` 512 bytes; a record with no album tag is the stock **Unknown Album** row, `REC_ID` -1), so a changed representative track or cover
  key of the album does not break the pin. A file that is gone says "File not found" (card in, `ENOENT` only); one that
  fails to open otherwise, or an album the library cannot find, says "Can't play". The pin stays. The sheet is **Play** | **Unpin Song**.
- **Entry:** the track row sheet (row "..." and row long press) has **Pin Song** / **Unpin Song** first
  (`rm_item5`, glyph `rm_ic_pin` / `rm_ic_unpin`) for a song of the card; a source's row (Navidrome) has none
  ([rowmenu](rowmenu.md)). API: `pins_pin_song(rec)` (the start from the record), `pins_has_song(path, cue)`, `pins_unpin_song(path, cue)`,
  `pins_song_ok(path, cue)`; callers pass `REC_CUE_START`.

## More entry points

- **Album page "...":** the library's album page "..." (`btn_more`, 214) opens the row menu's popup (`ab_on_more`, `ab_sheet`, under the button as the other "..." cards): **Pin Album** /
  **Unpin Album** (title and a track path copied at open, cover key `cover_key`), **Add to Playlist** | **Play Next**, **Play After** | **Select**.
  Play / Shuffle are the page's pill and disc. Select mode hides the "..."; an album with no title has no pin row; a source's page
  keeps the view-sort card with Download Album only.
- **Recently Played tile on Home:** a press held `RM_LONG_MS` opens the Home sheet (`pins_album_sheet`, reusing `pn.rm`) for the
  tile's album: the album sheet (Play, Shuffle | Pin Album / Unpin Album, Add to Playlist | Play Next, Play After). See [recent](recent.md).

## Artist pins

Kind `r`: key = `pn_artist_id`, FNV-1a of the artist's name as the Artists page lists it (ASCII case folded, as an album's title; a name of `PIN_STR` bytes or more, or one with no photo key, cannot be pinned), first cover key = `ap_key(name)`, the artist
photo's cache key (`patch/artistphoto.c`), name = the artist, path = the **scope**: the artist list it was pinned from, `0` Artists or `1` Album Artists (the stock `artist_type` at that moment; a line with it empty is tried against both lists; the model: `artist_key`). The name is the row's `REC_TITLE`: with Split Artists on it is the first name of the field, so a tile opens the same page the Artists row does.

- **Tile:** a circle (`pn_artist_art`, `pn_circle`): the artist's `-168` photo (the lead artist's when the name has none; `ap_lookup`, nothing is fetched from Home), decoded to the 90 px cell, a portrait from its top third, cut to the circle (`ap_circle`)
  and blended into black into an opaque bitmap (a small translucent round shape renders square on the device). No photo yet: the Artists page's circle placeholder (`ap_placeholder`), `tph` set so the next to-foreground looks again and a photo
  that appeared replaces it. The name line, lift and reorder are the other tiles'.
- **Scope:** `pn_artist_row` sets `artist_type` (and `ARTIST_RELOAD`) to the pin's scope while `artists_find` and the stock queries run; a pin with no scope tries the list shown, then the other. The row is therefore found even when the shown list lacks the artist (a guest artist is in Artists, not in Album Artists).
- **Tap:** `pn_open_artist`: `artists_find(name)`, `albums_open_artist(row, 0, CLASS_ARTISTS)` (Cover Flow when that window will not open), as an Artists row. The albums page reads its albums by `artist_type` each time it loads, so a pin from the other list leaves the setting at the pin's scope, saved (`write_int_config`) as the Show group does; Play / Shuffle (`pn_play_artist`) put it back after the call. **Sheet** (hold): Play, Shuffle (`songs_play_artist`, all the artist's songs; the toast
  "Can't play" when there are none), **Unpin Artist**.
- **Missing:** with no row of the artist the tile names in the pin's list (gone, the library mid-scan or unreadable, or a joined name "Lead; Guest" that Split Artists turned on since answers with its first name's row, which `pn_artist_row` refuses), a tap says "Not found" and Play / Shuffle "Can't play"; the pin stays.
- **Entries:** the Artists page row long press (`ar_on_hold`: Play, Shuffle, Pin Artist / Unpin Artist; [artists](artists.md)) and the artist's Albums page "..." card, Select's slot 7 (`al_pin_row`; [albums](albums.md)). API: `pins_pin_artist(name)`, `pins_has_artist`, `pins_unpin_artist`.
  Strings "Pin Artist", "Unpin Artist".
