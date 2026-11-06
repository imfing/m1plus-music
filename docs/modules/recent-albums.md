# Recently Added albums

**Sources:** `patch/songs.c` (`rv_*`, `sg_on_view`), `patch/grid.c`, `patch/covercache.c`, `tools/pod_ui.py` (`build_songs_page`, `navbar(songs=True)`),
`patch/home.h` (`RECENTADD_VIEW_FILE`), `patch/setfiles.c`. **Tests:** `test/pod/recentalbums.py`. **Preview:** `tools/preview_recent_albums.py` (a PIL approximation
that `make preview` writes beside the sheet as `recent-songs-view.png` and `recent-album-view.png`; the songs preview path draws no real page).

The Recently Added list (stock `allmusic_page`, class `0xf009`, shown on our Songs page: [songs](songs.md) "The other lists") has a navbar **view toggle** like the Albums
page's grid / list toggle ([albums](albums.md) "Navbar"; glyphs `pod_nav_grid` / `pod_nav_list`). The page stays the Songs page; the toggle switches in place (nothing opens
or closes) between the songs and the newest-first Albums grid. Only this list has it: the library, Favourites, Hi-Res, the other lists, playlists, genres and artists are unchanged.

## What the user sees

- **Songs view** (the default): the page as before. Capsule **Search 122 | Select 168 | toggle 214 (`pod_nav_grid`, "show as albums") | Now Playing 260**: the library Songs
  page's four-piece capsule with Select in Sort's slot (Recently Added has no Sort) and the toggle on the Albums page's slot. Below: large title, Play / Shuffle pills, rows.
- **Album view**: capsule **Search 168 | toggle 214 (`pod_nav_list`, "show as songs") | Now Playing 260**, the Albums page's three-piece shape; Select is hidden and
  insensitive (no multi-select on a grid). Content: the large title "Recently Added", then the 2-column Albums grid ([albums](albums.md): 144 px covers, the same cell geometry,
  cover corners, loader and cover-cache build) from y 52 where the pills begin, newest first. No Play / Shuffle pills and no song count. A tap opens our album page.
  No albums (every recent song untagged): the "No albums" line.
- The capsules are the real glass pieces (`mod_icons.py`: left cap `pod_nav_search`, middles `pod_nav_select` and `pod_nav_grid` / `pod_nav_list`, right cap `ah_nav_play`).
- **Small navbar title**: collapses in like the other lists'. "Recently Added" is 127 px at 20 px in English and the room before the capsule (x 122) is 64 px, so it is cut with an
  ellipsis to that room (`az_fit`).
- **Remembered choice**: `/mnt/data/m1plus/recently-added-view` (`RECENTADD_VIEW_FILE`): `1` albums; anything else, or missing, the songs. Written on every toggle with `home_write_atomic`.
  Read when the page opens (an open in the album view runs the 0xf009 query first, then the album query). A Settings Files row (after `playlists-view`).

## Data

- **Query**: the full `select * from songtable ORDER BY time_create desc` (stock `sort_time_desc`, not the `limit 100` of class `0xf009`, which would give too few albums).
  `rv_load` sets `sort_flag` to 3 ("Time added (descending)", `RV_SORT_TIME_DESC`), runs `loadLocalClassList(0xf001)` (getAllMusic) and puts the flag back at once;
  nothing is saved (`write_int_config` is not called) and the library's order is untouched. `REC_TIME_CREATE` (`+0x50`, `offsets.inc`) names the field the order comes from;
  the page reads the rows in query order and never the field.
- **Grouping**: each song is resolved to the library album row of its album name (`cc_albums`, the stock getAllAlbum copy: one row per album name, NOCASE), the first
  `RV_MAX` 60 distinct rows in the order of each album's newest song. A compilation's tracks under different artists, and the same album in another case, are one tile;
  a song with no album is skipped (it is in the songs view only). The tile's text, cover key (`cc_album_key` of the library row: the cache file's name) and album-page row come from
  that row, so no cover-key fallback (`cc_cover_key`) is needed. Compared with the design's "group by `cc_album_key`": equal for single-artist albums, and one tile instead
  of several for an album whose tracks carry different artists.
- **Stock list ownership**: the query replaces `*pdeq_showlist`. The album view copies the 60 row numbers (`sg.rrow`, 240 bytes) and reads only them and the page's own
  album copy, so it never depends on the stock list (`sg_valid` is not consulted; a replaced list is not stale for it; paint, foreground and the stale timer skip the check).
  Entering invalidates the songs view's list pointer (`sg.list`), and leaving runs `sg_load(0)`: class `0xf009` is read again, so the songs view never shows the album view's
  list. The songs view's index and tiles are kept, and reused when the rows are the same.
- **Tile ring**: a second `grid_t` (`sg.rg`, `GRID_TILES` x 144 px, about 1.1 MB with the placeholder) exists only in the album view: made on entering, freed on leaving and at destroy.
  The grid text styles are the hidden labels `label_grid_title` / `label_grid_sub` of the page. Loader and cache build as the Albums page: one cover per 16 ms tick, none while the
  scroll_view moves; the build (`rv_on_build_start`) queues the at most 60 albums' first tracks and `sg_on_build` polls it (one worker app-wide, as everywhere).
- **Tap**: `cc_open_album(NULL, 0, row)` with the library album row (the Albums page's call; our album page, the stock page when it will not open). A drag, the title block, a gap
  and the margins open nothing.

## Tests and what is not device-verified

`test/pod/recentalbums.py` (emulation of the compiled payload): the asset (toggle, grid text styles, setting file), the songs view (capsule moves, no small title, other lists
and the library page unchanged, an asset without the toggle keeps the plain list), the album view (the query under `sort_flag` 3 with the flag restored and nothing saved,
the atomic file, the glyph, the navbar, grouping and order, the grid geometry, a stale stock list ignored, Select refused), the way back (class `0xf009` read again, the songs
shown are its own list), taps (the album page's call with the right library row; the title, a drag and the margin open nothing), the 60 cap, a compilation, no albums, no memory, the
remembered choice at open (`1`, `1` + newline, `0`, garbage, missing), select mode and the toggle, and destroy in the album view.

Not verified on a device: the real `time_create desc` order after a rescan (see the date notes in [songs](songs.md)), the time of the full query and the grouping on a
20,000-song library (a scan until the 60th distinct album, at most 60 name compares per song), the look and scroll feel of the grid under the large title (the PIL
preview is an approximation), the cover build for new albums, the album page opened from this page and Back returning to the grid at the same place.

## Probe findings

Static reading of stock `bin/demo`'s query paths (`tools/stock.py`, `tools/disasm.py`); the device was not used.

**The SQL of `0xf009`.** `loadLocalClassList` (`0x4ee504`) dispatches `0xf009` at `0x4ee6b8..0x4ee6c4`: `bal`
`getAllRecentAddRecord` (`0x4ec604`, size `0x8c`), then `a0 = 0xf009` and the common tail `0x4ee5d0`. That function
`sprintf`s string `0x74bfb8` `select * from %s ORDER BY time_create desc limit 100;` (loaded at `0x4ec658`) with table
`songtable` (`0x74ba4c`) and runs it through `toolsQueryDbTable` (`0x5ee77c`, our podcast-filter hook) on
`/mnt/data/database.db` with the same row callback address (`0x4e9058`, annotated `curl_http_request+0x274` by the symbolizer; the stSongInfo
callback body is `0x4e908c`) as `sort_time_desc`, so the rows are full stSongInfo records as on Songs.
**At most 100 songs**: the albums of the page would come from 100 rows only, so the Albums side needs its own
unlimited query. Other users of the strings:

| string | address | used at |
|---|---|---|
| `select * from %s ORDER BY time_create desc;` | `0x74ba80` | `sort_time_desc` `0x4ea250` (`0x4ea2a4`), called by `getAllMusic` `0x4ea368` for `sort_flag` 3 (Songs "newest first") |
| `select * from %s ORDER BY time_create asc;` | `0x74baac` | `sort_time_asc` `0x4ea2dc` (`0x4ea330`), `sort_flag` 4 |
| `select * from %s ORDER BY id DESC` | `0x74bf94` | `getAllRecentRecord` `0x4ec578` (`0x4ec5cc`), class `0xf007` Recently Played (table `recentplay`) |
| `select * from %s where id <= %d` | `0x74bf74` | `getAllPlayList` `0x4ec4e8` (`0x4ec540`), class `0xf00b` |

So `0xf009` is **only** the `limit 100` query (also `memeory_startplayer` `0x4e374c`, Memory Playback's list for the
class). `sort_time_desc`'s text is the full, unlimited `time_create desc` on `songtable`.

**How `time_create` is filled.** Column 14 of `songtable` (`id, filename, fileurl, album, songer, style, name,
composer, albumsonger, year, track, cd_num, time, time_end, time_create, Initial, bitdepth, samprate`; create string
`0x757aec`, insert `0x757cb4`). The scan (`toolsLoadAllFile` `0x5efd98` -> the per-file parser; call sites `0x5e7a88`
and `0x5e8490`) stores `toolsGetFileCreateTime(path)` (`0x5e4ac8`) into its song record. That function
`access(R_OK)`, then `__xstat64` (via the stub `0x741bb0`) into a stack buffer and picks by the mount's format byte
(`0xa0ac7c`, written by `toolsSetMountDevFormat` `0x5e6ab0` from `getDiskMemoryInfoSetFormat` `0x4d8cd4`: `statfs`
`f_type` `0x4d44` MSDOS (FAT) -> 0, `0x2011bab0` (exFAT) -> 2, anything else -> 1):

- format 0 (FAT): `buf + 0x50` = `st_ctime` (kernel `stat64` o32 layout: `st_size` at `0x38`, which `toolsGetFileSize`
  `0x5e4a94` reads as `sp + 0x50`; `st_atime` `0x40`, `st_mtime` `0x48`, `st_ctime` `0x50`). On Linux vfat `st_ctime` is
  the FAT **creation** time, i.e. when the host OS copied the file.
- format 1 or 2 (exFAT, anything but FAT): `buf + 0x40` = **`st_atime`** (read at `0x5e4b40`, selected by the `movn`
  at `0x5e4b58`).

**A rescan rewrites it.** Update Library (`wait_scan` `0x47b410`) calls `scanAllMusicFile(/mnt/mmc, 1)` (`0x4e9df4`)
-> `toolsInitDatabase(db, "songtable", drop = 1)` (`0x5ed734`, `drop table %s` `0x757938` at `0x5ed828`, then
`create table`) -> `toolsLoadAllFile`: the table is dropped and rebuilt, so every `time_create` (and every `id`) is
re-derived from the files' stat times; nothing is kept. `scanSpecFolder` (`0x4e9e90`) does the same.

**stSongInfo.** The row callback (`0x4e908c..0x4e9384`, record at `sp + 0x18`) `atoi`s column 14 into the record at
**`+0x50`** (`atoi(argv[14])` at `0x4e9344`, stored by `sw $v0, 0x68($sp)` at `0x4e9358`, the delay slot of the next `atoi`; the columns around it
land on `REC_YEAR` `+0x30`, `REC_TRACK` `+0x3c`, `REC_DISC` `+0x40`, `REC_CUE_START` `+0x48` (time), `REC_CUE_END`
`+0x4c` (time_end), `REC_INITIAL` `+0x54`). `+0x50` is inside `REC_SIZE` (`0x58`) and has no name in
`patch/offsets.inc` yet: **`REC_TIME_CREATE 0x50`** (seconds since the epoch, `int`). Every list that goes through
that callback (`getAllMusic`, the recent-add query, `sort_time_*`) carries it, so the albums can be ordered by it
without a second query only if the list is the unlimited one.

**Uncertainties.**

- Stock's exFAT `st_atime` above is replaced by `patch/filetime.c` (`ft_created`, the `statx` creation stamp;
  `docs/modules/songs.md` "Recently Added dates"): `time_create` is the creation time on FAT32 and exFAT after a
  rescan, so the Albums side reads it as it is (no per-file stat of its own).
- The struct layout reading is from the kernel `stat64` o32 layout, confirmed only by `toolsGetFileSize` reading
  `st_size` at `buf + 0x38`.
- The scan's own store site of the time into the record (`0x5e7a9c`, `sp + 0x1468`) was not followed to the insert
  (`0x5edfc4`); the column order of the insert is the create string's.
