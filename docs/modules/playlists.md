# Playlists

**Sources:** `patch/playlists.c`, `patch/plmeta.c` (the playlists' times), `patch/grid.c` (`grid_mosaic`, `grid_list_paint`),
`tools/pod_ui.py` (`build_playlists_page`), `tools/pod_pages.py` (`PLAYLISTS`, `ACT_PLAYLISTS`),
`PLAYLIST_PINS` in `tools/pod_pins.py`.
The menu opens `ui/m1plus_playlists.bin` through `ACT_PLAYLISTS`. No hook. A failed open falls back
through `pod_home_open(14)` to stock `playlist_page`. The same page is the Add to Playlist picker
([picker](picker.md)): list mode, a New Playlist row and a Favorites row pinned first, then the
playlists in the saved order; no list-plus button, "..." or Now Playing; a tap adds the selection.

## What the user sees

- **Large title** (the Albums page's, [albums](albums.md) "Layout and state"): `pl_title`, first
  child of `view_grid`, "Playlists" (the picker: "Add to Playlist"). Rows start `PL_TOP` (52 px)
  down. The small navbar title shows from `SG_COLLAPSE` 46, in select mode ("N Selected") and
  when scroll events cannot be registered.
- **Navbar**: Back, the small title, and the capsule **list-plus | "..." | Now Playing**
  (`btn_plactions` with `pod_nav_listplus`, the left cap at x 168; `btn_more` at x 214). The small
  title runs to x 168.
- **Grid** (default): two columns of 144 px tiles with 8 px corners; under a tile the name (18 px
  white) and "N tracks" (15 px `#AAAAAA`). A tap on a cell opens the playlist; a long press opens the
  playlist sheet (Play, Shuffle | Pin Playlist / Unpin Playlist, Add to Playlist | Play Next, Play After), in list mode too.
- **List**: 64 px rows (`LIST_ROW_H`), 52 px mosaic at (10, 6), name 21 px white and "N tracks"
  18 px grey from x 74, hairline to x 310, chevron at x 288 (none in select mode or the picker),
  pressed row `#333333`. The painter is `grid_list_paint`, shared with Albums.
- **The tile** is a 2 x 2 mosaic of the playlist's albums (a local playlist with a stored cover, [plcover](plcover.md), draws that instead: `pl_art`; its scan still runs for the counts): four fill the quadrants (A B / C D),
  three repeat the first (A B / C A), two (A B / B A), one is that cover full size, none (empty
  playlist, or no album has a cache file) is the placeholder disc.
- Empty: the large title stays with a centred "No playlists" under it; the card is still there.

The view is saved in `/mnt/data/m1plus/playlists-view` (`1` grid, `0` list, else the grid), apart
from Albums' file. A switch is in place (`pl_set_mode`: tiles remade, first playlist kept).

### The two cards

Both are the shared view-sort card on one `vs_card` ([albums](albums.md) "View sort card"),
offered again at each open (`pl_menu_kind`: `vs_offer` with the rows, then `vs_menu`). Right edge
311, top y 52, fitted to the language (`vs_fit`).

| Card | Button | Rows | Glass |
|---|---|---|---|
| actions | list-plus (`pl_on_actions`) | New Playlist, Import, Export, Delete Playlists; no hairline, no tick column | `vs_glass4` |
| view and order | "..." (`pl_on_more`) | View: Grid, List (tick on the current); hairline; Order: Title, Date Added, Last Played, Updated (tick on the current, direction under it) | `vs_glass6` (a source's page: Grid, List, Title, `vs_glass3`) |

- The four actions are slots 6..9 (`VS_SEARCH`, `VS_SELECT`, `VS_ACT2`, `VS_ACT3`); slots 8 and 9
  exist only in this page's asset. Glyphs `pl_ic_*` (`mod_icons.PL_MENU_ICONS`).
- One card at a time (`pl.menu` 0, 1 or 2). The list-plus button is hidden in select mode and the
  picker. `New Playlist`, `Import`, `Export` are short translations of ours (the stock "Import
  playlist" does not fit beside the glyph in es, de, ja).
- `vs_offer` takes Name's top border away while the actions card is offered and gives it back
  (`vs_t.bare`).

### Order

The card's four sort rows are Title, Date Added, Last Played and Updated. Tapping another row selects
it in its default direction (Title A-Z, the dates Newest First); tapping the ticked row reverses it
(Z-A, Oldest First). The direction line under the tick reads A-Z / Z-A for Title and
Newest First / Oldest First for the dates (`vs_dated`, rows 1..3).

- Saved first in `/mnt/data/m1plus/playlists-sort` (`PLAYLISTS_SORT_FILE`): `0` Title, `1` Date Added,
  `2` Last Played, `3` Updated, or `a`..`d` for the same order reversed (the Albums codes); missing or
  anything else is Title A-Z. A failed save changes nothing. Listed in Settings Files.
- The default is Title A-Z, **not** the stock order. The page, the picker (Favourites and New
  Playlist stay pinned first) and every list follow it. Title is `cc_name_keys` / `cc_key_cmp`, as the
  Artists page ([artists](artists.md)); ties keep the stock order and Z-A is the whole order reversed.
- A date order puts the playlist with the larger time first (Oldest First: the smaller); equal times
  go by Title A-Z. A playlist with no time for the chosen date:
  - **Last Played**: after the others in both directions, by Title A-Z. When no playlist at all has a
    time, picking the order (or reversing it) from the card shows "No playlists played yet" (`pl_unplayed`,
    set by `pl_sort`, shown by the card's tap only; opening the page shows nothing) and the order is Title A-Z.
  - **Date Added, Updated**: ranked by a key of stock's `playlist` table (`pl_keys`), below every stamped
    playlist. Key = the lowest (Date Added) or highest (Updated) row id of its songs; an empty playlist
    has its own header id (0..100), below every song id. Keys compare by value, equal ones by Title A-Z;
    Oldest First is the exact reverse (keys first, smallest first, then the stamped ones oldest first).
    Nothing is written. One statement for all playlists (not run when every playlist has a time),
    `select cd_num,min(id),max(id) from playlist where id>100 group by cd_num`, through the hooked
    `toolsQueryDbTable` with the payload's own row callback (`pl_key_row`, text columns; `sqlite3_exec`'s
    argument is NULL and the tools deque is cleared and left empty); `pq_filter` passes it untouched (not a
    songtable select). A failed statement or no memory: no keys, and the order is Last Played's rule (a
    playlist with no time after the others in both directions, by Title).
- **The stock list is never reordered**: `pl.pls` is the copy of the stock rows and `pl.ord` maps
  each displayed position to its stock row (`pl_slot`, `pl_rec`). Taps, select marks and the picker
  follow the order shown; stock calls keep stock positions. A re-sort (`pl_reorder`) carries every
  scan over, so no count is read again.
- A source's playlists (Navidrome) offer Title only; whatever the saved order says, the effective one
  there is Title (`pl_sort_now`, `pl_rev_now`).
- Number of Tracks is not offered: a playlist's count is known only after the loader has read its
  songs (one query per playlist, each replacing `*pdeq_showlist`), so a count order would have to read
  every playlist before showing a row.

**The times** (`patch/plmeta.c`, `patch/plmeta.h`). Stock's `playlist` table has no time columns and
`createPlayListItem` reuses the lowest free id, so the page keeps its own in
`/mnt/data/m1plus/playlists-meta` (`PLAYLISTS_META_FILE`, device data, not the card; listed in Settings
Files as present or missing). No SQLite writes.

- Format: the line `M1PLMETA 1`, then one line per playlist, `<id> <added> <updated> <played> <name>`
  (decimal seconds, 0 = none; the name is the rest of the line, 1 to 63 bytes, no control byte). At
  most 128 lines.
- **Keyed by id and name**, as the Home pins are (`pn_pl_at`): an entry whose name differs from the
  playlist with that id is stale (the id was reused) and is ignored; the next stamp for that id
  replaces it.
- **Strict.** Every call reads the file, changes it and writes it back (`home_write_atomic`); a failed
  write changes nothing. A file that is there but unreadable or not ours (bad magic, a field out of
  shape, a repeated id, a long name, too many lines) gives no times and is never written over; a
  missing or empty file is no entries.
- **A stamp** is `max(time(NULL), the largest stamp in the file + 1)`, so the order is strict with an
  unsynced clock and with several changes in one second. Limits: a clock that jumped far ahead pins
  every later stamp at +1 from that value until the clock passes it; a playlist made before this file
  existed has no Date Added (and no Last Played or Updated until it is played or changed): it sorts by
  its table key (above) after the stamped ones, and Last Played after the played ones. The key is
  approximate: new song rows take the highest id + 1, so the ids of deleted top rows are reused, and removing
  an old playlist's earliest-added song moves its Date Added key.
- **Stamp points.**

| Time | Where |
|---|---|
| Date Added (and Updated) | `pl_named` (New Playlist, also from the picker and Now Playing), `dp_save` (Daily Mix's Add), Import (`pl_stamp_imported`: the playlists whose names the page's copy did not have; one write with the replacements below) |
| Updated | `picker_add` (any Add to Playlist; not Favourites), Add Songs (`sg_pick_tap`), Remove from Playlist (`sg_remove_one`, `sg_remove_marked`), Reorder (`sg_reorder`), Rename (`sg_renamed`: `plm_rename` keeps the times under the new name), Clean Up (`sg_clean`, only when something was repaired or removed), Import of a file named like a playlist (stock deletes it and makes it again, maybe under another id: `plm_imported` moves its times to the new id; only after Yes and an import that ran) |
| Last Played | a row, Play or Shuffle on a stock playlist's Songs page (`sg_play_at`), Play and Shuffle from the long-press sheet and the Home pins' sheet (`pn_play_playlist`), the Pod's playlist tracks (`ip_play`); only when a song started |
| removed | Delete Playlists (`pl_forget_deleted`: `plm_forget_many` for the marked playlists the stock delete took out) |

- A date order sorts again when the times file changed while the page was behind another window and
  nothing else did (`pl_metasig`, `pl_resort`: only when the order is another one). A playlist's
  Songs page played from the Playlists page returns to the new order.

### Select mode

Started by the card's Delete Playlists, on the shared select module ([selmode](selmode.md): `pl.sel`,
`m1_sel_*`; "Select Items" at 0 marked, "Deselect All", the pill dim at 0). List rows get the faint
fill and the mark through `m1_sel_paint`; grid cells keep the page's own mark (`pl_mark`, bottom
right of the cover) and no fill.
It exists for deleting (stock's multi-select only exports and deletes; export stays the menu row).

- Back becomes the glass x, the title reads "N Selected", Select All is at the right, "..." and
  Now Playing go. Every cell has a 26 px mark (`m1_make_mark`, cut to a circle) at its cover's
  bottom right; in list mode a 30 px column (`SG_SEL_COL`) opens left of each row and cover, texts
  and hairline shift right. A tap marks; a drag marks nothing.
- A 64 px bar holds one icon-only glass **Delete** capsule (60 x 42, centred). The content is 64 px longer.
- Back (the x) leaves the mode. A page read again (returning to the front, after a delete) is out
  of it, since the marks were of the old list.
- Where the page cannot do it (no `btn_selall`, `pl_bar` or `pl_del`, marks that do not decode)
  the row opens the stock Playlists page (`pod_home_open(14)`); with no playlist it only closes the
  menu.

**Delete** (`pl_on_delete`; evidence below): nothing marked shows `msg_delplaylistfailed`; the stock
confirm dialog with `msg_delplaylist` (Yes = 0xa; anything else ends it, the mode stays); then the
stock list is read again and must match what the page shows (same ids, same order, else nothing is
deleted); the stock vector is filled from the marks; `batch_delete_file(0xf00b, *pdeq_playlist,
vector, 0, 0)`; the stock list is read once more and the stored covers ([plcover](plcover.md)) of the selected playlists it
no longer has are forgotten (`pl_forget_deleted`); `msg_delplaylistsuccess`; the mode ends and the page reads again.

## The stock database calls

- Playlists are rows of the `playlist` table of `/mnt/data/database.db`. A row with `id <= 100` is a
  playlist (`getAllPlayList`: name in `REC_TITLE`, id in `REC_ID` and `REC_DISC`, type 4). Its name
  is in two columns: `createPlayListItem` copies it into the record's `+8` and `+0x10`, which
  `toolsInsertDbTable` writes as `filename` and `name` (`REC_NAME`, `REC_TITLE` when read back). A row
  with `id > 100` is a song linked by `cd_num` = the playlist id (`getMusicByPlayList`, no ORDER BY:
  insertion order). Rows have the 18 columns of a library song, `REC_ALBUM` and `REC_ARTIST` as when
  added.
- That album/artist pair gives the Cover Flow key only when the track's artist is the one SQLite
  picked for the album (`getAllAlbum` groups by album), so a compilation track can miss. The page
  then takes the key of the library album of that name (`cc_nocase` over `cc_albums()`).
- `loadLocalClassList(0xf00b)` lists the playlists into `*pdeq_playlist`; with `classinfo[1]` = a
  playlist id, `loadLocalClassList(0xff13)` lists its songs into `*pdeq_showlist`.
- **Opening a playlist.** Stock (`playlist_page_init`, mode 0) copies the name into
  `nagvation_title`, sets `classinfo[1]` = `REC_DISC`, and calls `navigator_to_with_context(
  "allmusic_page", 0xff13)`. `pl_open` does the same three steps when our Songs page will not open.

### Create

Stock runs `dialog/kbaddplaylist_dialog`, then `createPlayListItem(*pdeq_playlist, buf)` (-1 full:
`msg_playlistfull`; -2 exists: `msg_playlistexist`; else the new id). Ours opens our own keyboard
instead (`pl_create`, [keyboard](keyboard.md); title `playlist_create`, hint `msg_newplaylists`,
action key **Done**).

- The keyboard is not modal. Done with a non-empty trimmed name closes it, then `pl_named(name)`
  reads the stock list first (`createPlayListItem` needs it for the free id and the duplicate
  check), creates, shows the two messages, and calls `pl_load` if the page is up. Back creates
  nothing. The name is at most 63 bytes.
- A playlist made there (not in the picker) then opens on its own page, empty, with its Add Songs
  row ([songs](songs.md) "A playlist's header"): `pl_new_later` waits `PL_PICK_MS` on a timer (the
  keyboard's close, as `pl_pick_later`) and `pl_new_fire` calls `songs_open_playlist(id, name)` when
  the Playlists page is the front window.

### Import and Export

Export is the stock row handler (static, `PLAYLIST_PINS`), **called as it is**: it asks with
`confirminfo_dialog`, runs `exportPlayList` into `/mnt/mmc/_explaylist_data` and reports in the stock
message box. It reads `navigation_status` (1 = multi-select) to pick all or selected playlists, so the
page stores 0 there first.

Import runs the stock handler's sequence (@0x53dedc) in the page (`pl_import`), because the stamps
need to know that Yes was answered: `pl_ask(msg_importplaylist)`, then `importPlayList` (pinned
prologue), then `msg_nottf` (-2), `msg_notplaylist` (-6) or `msg_importsuccess`. `importPlayList`
takes each regular `.m3u8` / `.m3u` file of that folder, in readdir order, as the playlist named after
the file without its last extension. `createPlayListItem` cuts that name to 63 bytes (an empty one
becomes `Playlist<id>`) and uses the lowest free id. Before that, `checkPlayListByName` deletes the
playlist whose name is the whole uncut one, with its songs. So a name over 63 bytes is never a
replacement: each Import makes another playlist. Import stops at the first file it cannot make a
playlist of (100 playlists) and returns 1 all the same.

`pl_stamp_imported` compares the (id, name) pairs before and after: a pair that is new was made by
Import. It then walks the folder in the same order, and each file takes the row it produced:
- A cut or empty name takes one made row (new: Date Added).
- An uncut name whose old playlist is gone takes one made row of that name. That row is the
  replacement: the times move to its id, and it is Updated.
- An uncut name whose old playlist is still there marks it as made again under its own id: Updated.
- Otherwise the file takes a made row (new).

The first file with no playlist of its name (for a cut or empty name: no made row left to take) is
where stock stopped, and the files from there on stamp nothing.

### Delete

The stock handler touches no widget. Its sequence: `select_recordempty()`; nothing selected is
`msg_delplaylistfailed`; else a kind 1 confirm (`msg_delplaylist`; the Songs delete uses kind 3 with
a checkbox); then `batch_delete_file(*g_class_type, *pdeq_playlist, *SEL_VEC, 0, 0)` (`delete_file`
0: no file belongs to a playlist); then `msg_delplaylistsuccess`. For class `0xf00b` the loop calls
`deletePlaylist` and `deleteAllMusicByPlaylist` per marked row. The page passes the class itself,
so it does not depend on `g_class_type`. The selection vector is the Songs page's
([songs](songs.md) "Select").

## The page (`patch/playlists.c`)

- **Widgets**: `playlists_listview` > `playlists_scrollview` > `view_grid` + `scroll_bar_m` (the
  Albums structure, [albums](albums.md)), the large title first in the content, the navbar's
  hidden `label_title` and `img_nb_fade`, hidden text styles, then last the shared card's
  `vs_scrim` and `vs_card` with ten row buttons `vs_item0..9`. Hide = `visible=false` +
  `sensitive=false`.
- **Data.** `pl_load` (at open and on `EVT_WINDOW_TO_FG`) runs `loadLocalClassList(0xf00b)`, copies
  the rows and sizes the content. At most `PL_MAX` 100 playlists.
  - Scans and tiles are **kept** when nothing changed: same rows (`pl_same_list`) and same
    `pl_dbsig` (mtime, nanoseconds and size of `database.db` and its `-wal` / `-journal`, taken at
    each load). Every playlist's songs live in that one file, so any edit changes the signature.
    A return from a playlist's songs page then queries only the playlist list.
  - The cover cache is not in the signature. A scan that found an album with a key but no cache
    file (`PL_SCAN_MISS`) is read again on return; its tile is rebuilt only when the albums found
    differ (`pl_same_art`).
  - Per playlist the loader's **scan** (`pl_scan`, one a tick) sets `classinfo[1]`, runs
    `loadLocalClassList(0xff13)`, takes the count and, from the first `PL_SCAN` (50) songs, the
    first four **distinct** albums with a cache file (`grid_mosaic_keys`, which the Songs page's
    playlist header also calls). The page holds only four keys per playlist (`info_t`).
- **Tiles and loader.** The Albums ring (`GRID_TILES` 12 tiles of 144 x 144) plus one 72 x 72
  quadrant buffer. `grid_mosaic` decodes one source per call, box-reduced to 72 px, and rounds the
  corners at the last one. The 16 ms timer (`pl_on_load`) does one step a tick for the cell
  nearest the middle, nothing while the list moves (`pl_moving`). Paint never decodes or queries.
  - **It stops when the window goes behind another** (`EVT_WINDOW_TO_BG`) and restarts with the
    to-foreground read, because a scan sets `classinfo[1]` and replaces `*pdeq_showlist`, which the
    playlist's songs page draws and plays from. A tap before the visible mosaics were done once
    played another playlist's songs.
- **On a library source** (`playlists_open_src`) the scan reads `src->list(LS_PLAYLISTS, row)`;
  until cached the tile shows `src->count`, so an unread playlist never reads "0 tracks". The
  signature is a hash of the rows' ids and names, so a moved gen keeps tiles and covers
  (`pl_carry`). While the source is loading a scan is marked `PL_SCAN_MISS` and read again. The
  "..." takes the left cap (`pod_nav_more`) on a source page.
- **Touch.** As the Albums grid: UP within `SC_DRAG_PX` of the press on the same cell opens the
  playlist in our Songs page (`songs_open_playlist`, [songs](songs.md) "The other lists"), the
  stock page only if that will not open. A press held `RM_LONG_MS` (`pl_on_down` arms
  `rowmenu_hold_start`, `pl_on_move` cancels on a drift) opens the six-row sheet (`pl_on_hold`, `rowmenu_open_playlist`,
  `pl_sheet`; [pins](pins.md)) on the library's page only: none in select mode, the picker, a
  source's page or under a card. The hold forgets the press, so the release opens nothing. Every
  row but Pin goes through `pins_playlist_act` (the Home pin's actions); Pin takes the keys of `info_t`.
  `pl_on_bg` closes the sheet; the page reads again at the to-foreground.
- **Menu.** Every row closes the card first, then: slot 6 New Playlist -> `pl_create`; 7 / 8 Import
  / Export -> `pl_import` / `stock_playlist_export` with `navigation_status` 0; 9 Delete Playlists ->
  `pl_select(1)`; 4 / 5 Grid / List -> `pl_set_mode` and the save; 0..3 Title, Date Added, Last Played, Updated -> the order. The page
  runs `pl_load` after Import and Export.
- **Glass.** The actions card uses `vs_glass4`, the "..." card `vs_glass6` (`vs_glass3` on a source's page). `pl_glass.png` stays
  in the tree only for the Podcasts refresh and Software Update dialogs that borrow it.
- **Pins** (`tools/pod.py`): `createPlayListItem` (named), data words `pdeq_playlist`,
  `nagvation_title`, `navigation_status`, and `PLAYLIST_PINS` for the two static click handlers.

## Pin Playlist (`patch/songs.c` `sg_pin`)

A stock playlist's songs page also has **Pin Playlist** / **Unpin Playlist** as the fourth row of the "..." card (slot 9,
`VS_ACT3`, `pod_ic_vspin` / `pod_ic_vsunpin`): the playlist is pinned to the top of Home ([pins](pins.md)).

## Clean Up Playlist (`patch/songs.c` `sg_clean`, `patch/songops.c`)

**Why.** A playlist song is a row of the `playlist` table with its own copy of the song's columns,
the path (`fileurl`) among them. Stock Update Library rebuilds `songtable` and leaves `playlist`
alone, so a song whose file was deleted or moved stays with a path that no longer exists: the
library shows it at its new place, the playlist row does not play. (A tap, Play Next / After and
Shuffle check the first file with `access` and toast **"File not found"** with the card in, or
"Storage unavailable" without it: `so_missing`.)

**The row.** A stock playlist's songs page has the "..." in place of Select (`sg_cleans`); its card
is three rows in `vs_glass3`: **Edit** (the Select row, [songs](songs.md) "A playlist's header"), **Clean Up** (slot 8, `VS_ACT2`, glyph
`pod_ic_vsclean`, Lucide broom), **Pin Playlist**. A server playlist keeps the Select button. It works on this playlist only:

1. **Check** (`sg_gone`, `so_gone_mark`): each row whose path starts with `/mnt/mmc/` is tested
   with `access`. Other paths (USB, none) are never tested, marked or written.
2. **Guards**, nothing written: no card (`/tmp/mmc_add`) shows `msg_nottf`; nothing missing, "All
   songs are on the card"; the card is in but `/mnt/mmc` is not its own file system
   (`m1_card_mounted`), "Card not readable, nothing removed".
3. **Repair**, unasked (`so_relink`): the library is asked for the missing rows' file names (40 a
   query, `SO_RELINK_ROWS`). A library row is the missing row's song when file name, CUE start and
   end, title, album and artist are equal, its path is another one under `/mnt/mmc/` and its file
   exists (`so_same_song`; a USB copy is no twin). The row gets that path through
   `toolsUpdateDbTable` (`so_set_path`) and the page reads again. A re-tagged or renamed song has
   no twin and stays missing.
4. **Removal**, asked: `pod_confirm` "Remove N missing song(s) from this playlist?". Yes: rows are
   marked again from what is missing now and cut down to the ids the dialog counted
   (`so_marked_ids`, `so_keep_ids`: a file that went missing under the dialog stays for the next
   run; one that came back keeps its row). Each leaves by its own id through
   `toolsDeleteItemById("playlist", db, id)` (`so_clean`), then stock's `delete_flag` is set as
   `batch_delete_file` leaves it, "Playlist cleaned up". No removes nothing.
5. Repaired rows with nothing removed: "N song(s) updated".

**Stock calls** (pinned in `PLAYLIST_PINS`). A playlist song's `REC_ID` is its own row id; the
columns are `songtable`'s and only `fileurl` holds the path. `so_row_id` writes no row whose id is
100 or less (the playlists themselves). `toolsUpdateDbTable` runs `sqlite3_exec` (1 ran, -1 not).
`toolsDeleteItemById` formats `delete from %s where id=%d`. Neither takes a lock; both run on the UI
thread from a tap, as stock's do.

**Why not the stock delete.** `batch_delete_file(0xff13, ...)` runs `deleteMusicFromPlaylist`, whose
WHERE has `filename`, `fileurl`, `time`, `time_end` and no id or `cd_num`: it removes the song from
every playlist that holds it. The clean-up removes this playlist's row alone.

## Remove from Playlist (`patch/songs.c` `sg_remove_one`, `sg_remove_marked`)

Only on a stock playlist's songs page (`sg_cleans`: not Favorites, other lists or a server
playlist). Both take this playlist's rows out by their own row ids through `so_remove_ids`
(`toolsDeleteItemById("playlist", db, id)`, ids over 100 only, then stock's `delete_flag`), as the
clean-up does. No file is ever deleted and no other playlist's copy of the song goes.

- **Row sheet**: **Remove from Playlist** (the red `pod_ic_remove_red`, Lucide `list-x`, red label),
  last and in a group of its own ([rowmenu](rowmenu.md)). The page
  registers it with `rowmenu_set_remove`; a tap removes the row the menu's record copy is of (its
  `REC_ID`, refused when its `REC_DISC` is not this playlist), without a dialog, toasts "Removed
  from Playlist" and reads the list again with its scroll offset kept. A list read again under the
  sheet closes it, so a stale row is never removed by index.
- **Select mode trash**: `pod_confirm` "Remove N song(s) from this playlist?" (the key by 1 / more),
  the marked rows' ids taken before the dialog (`so_marked_ids`), then "Removed from Playlist",
  select mode ends and the list is read again. No keeps select mode. Every other list's trash is
  still `so_delete`.
- A statement that removed nothing toasts "Can't remove from playlist".
- A pinned playlist keeps the cover keys it was pinned with; the Playlists page sees the changed
  database (`pl_dbsig`) and reads its list and mosaics again when it is back in front.

## Reorder (`patch/songs.c` `sg_reorder`, `patch/songops.c` `so_reorder_rows`)

Dragging a row by its handle in Edit mode ([songs](songs.md) "Reorder"). Stock reads a playlist's
songs with `select * from playlist where id > 100 and cd_num=%d` and no ORDER BY, so they come back in
`id` order (`id` is `INTEGER PRIMARY KEY`, the rowid): the order is the ids'. Only the rows between the
drag's two indexes change. Their ids (`REC_ID`, taken from the list, strictly ascending and over 100)
stay in the table; the moved row takes the id of the slot it lands in and the rows between shift by one.
`toolsUpdateDbTable` runs `sqlite3_exec` on the shared handle, and when a statement fails it closes
the handle (`sqlite3_close`, which rolls back whatever is open on it) and clears it (`0xa0ac74`).
Stock's scan insert keeps its own transaction open there between its `BEGIN` and the `COMMIT` every
100 rows, counting the rows in `DB_TX` (`0xa0b080`; it sends `BEGIN` only while the word is 0).
While `DB_TX` is above 0 nothing is sent, so a move does not ride in the scan's transaction. That
check is only a preference: the worker can `BEGIN` right after it is read. What makes the write safe
is one `toolsUpdateDbTable` call for the whole move: `SAVEPOINT so_reorder;`, per row `update
playlist set id=-OLD where id=OLD and cd_num=N;` (negative ids are never used, so no PRIMARY KEY
clash), per row `update playlist set id=NEW where id=-OLD;`, then `RELEASE so_reorder;`.
- SQLite 3.19.3 is built `THREADSAFE=1` and demo opens with plain `sqlite3_open` (serialized), so no
  other thread's statement runs inside one `sqlite3_exec`.
- `SAVEPOINT` is never refused for an open transaction (a `BEGIN` was, and its failure closed the
  handle under the scan). Alone it begins a transaction and `RELEASE` commits it. Inside the scan's
  it nests, and `RELEASE` leaves the rows to the scan's `COMMIT` (a scan that rolls back later
  takes the move with it).
- The string is built in a `calloc`ed buffer (O(rows); no memory: nothing changes). A statement that
  failed closed the handle, which rolled ours back; no `ROLLBACK` is sent.

Playlist inserts (`toolsInsertDbTable`, Add Songs) run without a transaction and never move `DB_TX`.
Any failure toasts "Can't reorder playlist". Nothing else depends on a playlist row's id: resume matches name and path, the stock delete
matches columns and Remove reads the list fresh.

## Rename Playlist (`patch/songs.c` `sg_rename`, `patch/songops.c` `so_rename_pl`)

In Edit mode on a stock playlist, a tap on the header's name (a grey pencil after it says so; the
card has no Rename row). It opens our keyboard as New Playlist does
(a name on the keyboard's card row, no magnifier; title "Rename Playlist", hint `msg_newplaylists`, action key **Done**, the current name in the
field). The keyboard is not modal; `sg_renamed` runs on Done for the playlist it was opened for
(`sg_rn_id`; `sg_rn_on` says one is waiting, since stock's ids start at 0), with the name trimmed and 1 to 63 bytes:

- The same name changes nothing. A name another playlist has (`REC_TITLE` or `REC_NAME` of the
  stock list `loadLocalClassList(0xf00b)` reads) shows stock's `msg_playlistexist`. That read
  writes "Playlists" into `nagvation_title`; `sg_pl_taken` puts the title back.
- Else one statement through `toolsUpdateDbTable`:
  `update playlist set filename='..',name='..' where id=N and id<=100`, quotes doubled. A statement
  that did not run toasts "Can't rename playlist" and changes nothing.
- Then `sg.name`, the header name (one or two lines, `sg_name_place`; the list is read again for
  the new row offset), the small title, stock's `nagvation_title` when it held the old name, and a
  Home pin of this playlist (`pins_rename_playlist`: same place and cover keys) and its stored cover (`plc_rename`) take the new name.
  The Playlists page reads the list again when it is back in front. Edit mode and its marks stay
  (`sg_edit_reload`).

**Add Songs.** The + in Edit mode adds library songs to this playlist, one tap each, through the stock
`batch_add_file` (appended at the end, duplicates skipped); see [songs](songs.md) "Add Songs".

**Pins** (`PLAYLIST_PINS`): `getMusicByPlayList` passes the song row callback (a song record's
`REC_DISC` is its `cd_num`, the playlist id); `createPlayListItem`'s two name copies and
`toolsInsertDbTable`'s loads and value order for `filename` and `name`, and its insert statement.

## Limits

- A clean-up while Update Library runs is not guarded (the shared database handle has no lock).
- A check is one `access` per row on the UI thread, so a playlist of thousands of rows takes a
  while.
