# Known addresses of stock V2.1 demo

**Sources:** stock V2.1 `demo`.

Payload `PT_LOAD`: `0xb00000`; `$gp`: `0xa03ed0`. `tools/pod.py` is the authoritative pin list.
Use `tools/stock.py` or `tools/disasm.py` to inspect it; see [payload](payload.md) for prologues,
resumes and call boundaries.

| Site | Address |
|---|---|
| Home icon dispatcher | `0x533b80` (`widget_on`; GOT slot `0x9fe700`) |
| `home_page_init` | `0x534cd4` |
| `playing_page_init` | `0x53d1e4` |
| `dialog_playmore_dialog_init` | `0x479cc4` |
| `dialog_dropdown_dialog_init` | `0x475f04` |
| `get_id3info` tag-copy call | `0x4dff4c` |
| `mclStartPlayer` (Radio hand-over) | `0x5d5300` |
| `on_backtoplayer_onclick` (Radio Now Playing hook) | `0x4cd58c` |
| Empty `scroll_view` event slot | `0x97a330` |

Only `demo`'s unloaded `.pdr` is zeroed. Stock About stays `V2.1`; our own About page (docs/modules/settings.md) shows
the build tag beside it, without a hook.

Pinned stock functions, beyond those in the sections below: `widget_lookup` `0x666a74`, `widget_on`
`0x666d20`, `widget_set_text_utf8` `0x66f720`, `navigator_back` `0x4d20dc`, `on_backtoplayer_onclick`
`0x4cd58c`, `window_open` `0x679fd4`, `widget_set_visible` `0x66c394`, `widget_set_sensitive`
`0x666b9c`, `widget_set_opacity` `0x669140` (stores the byte at `+0x34`, then `widget_invalidate`; the dimmed Regenerate Daily Mix row), `slide_menu_set_value` `0x61399c`, `window_manager` `0x6774b4`,
`window_manager_get_top_main_window` `0x6774f0`, `widget_is_window_opened` `0x66aa04`. Also pinned:
the stock `slide_menu` constructor `0x613914` stores `value = 1` (`sw 1, 0x78` at `0x613970`);
`slide_menu_set_value` -> `0x6120ac` (events `0x11b`, `0x11c`); `songtable` record fields `year`
`+0x30`, `track` `+0x3c`, `cd_num` `+0x40`, `time`/`time_end` `+0x48`/`+0x4c` (CUE offsets, 0 for
ordinary files; no duration column); `toolsLoadAllFile` `0x5efd98` and its insert `0x5edb18`;
`get_screensaver_image` `0x4d7524` (`screensaver_default`, the default wallpaper). Pinned for the Albums grid (section 5a):
`widget_to_local` `0x669b88` (walks the parent chain subtracting each `x`, `y`; the payload runs stock's own), `widget_prepare_text_style`
`0x66a214`, `canvas_draw_text_in_rect` `0x6496a0`, `canvas_measure_text` `0x644544` (returns a float in `$f0`),
`tk_utf8_to_utf16_ex` `0x70eb24` (`wchar_t` is 32 bit), `button_create` `0x622adc`.

Pinned for the mini player bar (`docs/modules/minibar.md`, evidence there): `playpause_quick_click` `0x4cd150` (no arguments; what the lock
screen's play button, Now Playing's and the hardware key call), `next_quick_click(e, 0)` `0x4ccf00` (reads `e->time` at `+8`, ignores a click within 1 s of
the last one: global `0xa05a40`), `mclGetPlayStatus` `0x5d3640` (2 = playing, 3 = paused after `mclSetPause`).

Pinned for the iPod page (`docs/modules/ipod.md`): `prev_quick_click` `0x4cccb0` (the twin of `next_quick_click`: same prologue and 1 s guard on `e->time`, `prev_music` `0x4e428c`), `loadAlbumdetailList(class, album record)` `0x4eea98` (class `0xf003` -> `0xff10`, `0xff01` -> `0xff11`, `0xff02` -> `0xff14`; the second argument is the album record of the shown list: `lw v0, (a1)` the id, `0x14(a1)` the name), and the data word `system_bar` `0xa06f90` (the status bar window; `pgbar_battery` `value` and `img_battery` `image` are what the real bar shows).

Pinned for the lyrics page (`docs/modules/lyrics.md`, `tools/pod.py` `LYRICS_PINS`): `get_playtime` `0x4e02e4` (the position the stock lyric timers compare each row's int property `lrc_time` with; seconds), the strings `scroll_lrc` `0x751c3c` / `lrc_time` `0x751c80`, the online timer `0x537fec`'s row builder (`0x5384bc`) and reads (`0x538654`, `0x5385cc`, `0x5385e0`, `0x5386a8`), the lyric deque `*0xa062e8` (elements `{int32 time; char *text}`; `online_loadexlyric` `0x508a00`, `toolsTimeConvert` `0x5e3020`); the local deque (`*0xa0aae4`, mutex `0xa0aaf0`) is not read.

Pinned for the Tape page (`docs/modules/tape.md`, `tools/pod.py` `TAPE_PINS`; everything else it calls is pinned above for Cover Flow's landscape captions, the Pod and the mini player bar): `widget_invalidate_force` `0x6691d0` ends in `b widget_invalidate` `0x668d9c` with its rectangle untouched, and `widget_invalidate` uses a non-NULL `rect_t` (four 32 bit words x, y, w, h, 16 bytes, in the widget's own coordinates; NULL: `0, 0, w, h`), `widget_get_text_utf8` `0x667d84`.

Pinned for the Playlists page (`docs/modules/playlists.md`) and the Daily Mix page's Add disc (`checkPlayListExist` `0x4ee1a8` (rec, playlist id), `getPlayListMaxId` `0x4ee184`, `addPlayList` `0x4ee1cc`(rec), thin wrappers on `playlist` in `/mnt/data/database.db` (`0x5ef768`, `0x5ef968`, and `toolsInsertDbTable` `0x5ee2fc`); prologues pinned, with `batch_add_file`'s `0x4db34c..0x4db3d0` words, `tools/pod.py` `PLAYLIST_PINS`): `createPlayListItem` `0x4eeca8` (the stock list, a name or NULL: the new id, -1 full, -2 exists), `loadLocalClassList(0xf00b)` the playlists into `*pdeq_playlist` `0xa045d0`
and `(0xff13)` a playlist's songs (`classinfo[1]` = its id) into `*pdeq_showlist`, `nagvation_title` `0xa0533c`, `navigation_status` `0xa05a24`, the stock Playlists page's static Import / Export click handlers `0x53dedc` /
`0x53dd34` (and its row handler `0x53d300`, create handler `0x53e8e4`, multi-select delete handler `0x53dbcc`, which the page does not call).

Library Search (`docs/modules/search.md`): the toggle navbar builder `0x526a3c` (album page, `allmusic_page`) takes the page window as its argument, destroys the children of `navigationbar_view` and refills them, and makes the search disc (not for class `0xff09`, after a select cycle on the album page) with `widget_on(btn, 0x10c, 0x52704c, window)` @0x526f78 .. 0x526f90; nothing of ours reads or pins it. The album page's to-foreground handler `0x5266d4` (bound @0x526870) re-runs `loadLocalClassList(saved class)` and its list when `g_class_type` (`0x97cad4`) differs from the class saved in `0x97cc40` (the search page leaves `0xf001`).

Pinned for the Songs page (`docs/modules/songs.md`, evidence there): `sort_flag` `0xa059d4` (the list order of class `0xf001`: 0 alphabetical, 1 file name, 2 file format, 3 newest first, 4 oldest first; the sort dialog's row handler `0x47d114` stores it and calls
`write_int_config(v, "SYSSET", "SORTSELECT")` `0x4d6a2c`; `config_init` reads it back), the stock Songs page's click handlers `0x527014` (Sort: `navigator_to("dialog/sortselect_dialog")`) and `0x52704c` (Search: `navigator_to("search_page")`; `navigator_to` `0x4d1d80` is `navigator_to_with_context(name, 0)`),
the stock multi-select's selection `*0xa045e0` (a `vector<int>`, one entry per row of `*pdeq_showlist`, 1 = selected) with `select_recordinit(n)` `0x4da3b0` and `set_selectindex(i)` `0x4da434` (a toggle), `batch_delete_file(class, list, vector, 0, delete_file)` `0x4e1408` (`0xf001`: the generic loop `0x4e1664`; ends with `*0xa05a5a = 1`),
the delete handler `0x527f48`, the add handler `0x5280c0` (`dialog/batchadd_dialog`, then `navigator_to_with_context("playlist_page", 0x10000 | class)`: the playlist picker, row handler `0x53d300`, which runs `batch_add_file` `0x4da7dc` and closes itself), the multi-select button `0x52823c`; and `stSongInfo + 0x54`, the Initial byte (`'*'` digit, `'A'..'Z'`, `'#'`; scan `0x5edb18` / `0x5edcb8`, row callback `0x4e936c`, copy `0x5db9ac`, the stock letter index `getsidebarbyoffset` `0x4d94a4`).

The queue (`docs/modules/queue.md`): Now Playing's queue button handler `0x53b14c` (idle countdown `0x97ccd0` = 0x14, then `navigator_to("dialog/playqueue_dialog")` `0x53b178`), the drawer's init `0x47a7cc`, row bind `0x47a19c` (marked row: `mclGetPlayStatus` != 1 and `mclGetPlayPos` = row; not pinned any more), row handler `0x479f60` (`start_playqueue` `0x4e47d0`, then `force_refreshflag`; refuses a stream while offline), the play queue deque `*0xa0394c` (`PLAY_QUEUE`), `mclGetPlayType` `0x5d3658`; `playerjumpinfo_page_init` `0x5393bc` is opened only by the stock Look up album.

The More sheet's rows (`playmore_dialog`, bound by the binder `0x478b44` with `widget_on(row, 0x10c, handler, dlg)`): Look up album `0x4795cc` (empty album string at `0xa0d88c + 0x404` -> the msginfo error via `0x479544`; else `window_close(dlg)`, fills the browsing record `0xa0c768` and `navigator_to("playerjumpinfo_page")`), Look up artist `0x4793ac` (`window_close(dlg)`, `navigator_close` `0x4d2118` of `album_page` and of `albuminfo_page` when `navigator_window_is_exist`, `songerinfoflag` `0xa04737` = 1, `navigator_to_with_context("album_page")`); `songerinfoflag` is cleared only by `album_page`'s window event handler `0x522c64` (bound @0x5248a0). `patch/playmore.c` replaces the album handler (docs/modules/playmore.md).

## Home icons and their conditions

The Home grid is built by `home_page_init` (`0x534cd4`) -> the page builder (`0x534064`) -> the icon
builder (`0x533d8c`), which walks a `deque` of 8-byte records `{int id; char shown; ...}` at
**`0xa045c0`**, six icons per slide page. For each record it calls `get_homemenu_showinfo(id, buf)`
(`0x4d9ffc`), indexing an 18-entry table at **`0x97c940`** for the name; the style is
`home_<name>_style`, the label `widget_set_tr_text(<name>)`, and the widget **name is the decimal id**
(`tk_snprintf("%d", id)`), which the dispatcher `0x533b80` reads back and `atoi`s.

| id | name | opens |
|---|---|---|
| 0 | `hifimusic` | `hifi/hifimusic_page`, or the `msg_notnetwork` dialog offline |
| 1 | `tidal` | `tidal/tidal_main`, or the `msg_notnetwork` dialog offline |
| 2 | `sset_updatemusic` | `systemset/updatemusic_page` (Update Library) |
| 3 | `mymusic` | `allmusic_page` ctx `0xf001` (All Songs) |
| 4 | `folder` | `folder_page` |
| 5 | `album` | `album_page` ctx `{0xf003, 0}` |
| 6 | `songer` | `localclass_page` `0xf004` (Artists) |
| 7 | `genre` | `localclass_page` `0xf006` |
| 8 | `composer` | `localclass_page` `0xf005` |
| 9 | `hr` | `allmusic_page` `0xf002` (Hi-Res) |
| 10 | `fav` | `allmusic_page` `0xf00a` (Favourites) |
| 11 | `many` | `allmusic_page` `0xf008` (Most played) |
| 12 | `recent` | `allmusic_page` `0xf007` (Recently played) |
| 13 | `recentadd` | `allmusic_page` `0xf009` (Recently added) |
| 14 | `playlist` | `playlist_page` |
| 15 | `cdripper` | `cdripper_page` (sets GPIO `PA11` first; needs the CD drive accessory) |
| 16 | `playset` | `playset/playset_page` |
| 17 | `sysset` | `systemset/sysset_page` |

Which ids are in that deque:

- `reset_homemenu_index(0)` (`0x4d8114`, the defaults) clears it and pushes every id of `main_allmenu`
  (`0x97ca88`, exactly `0..17`) with `shown = 1`, except that when the `language` global (`0xa05ab8`) is
  non-zero it skips `id == 0` (`lw $v1, language; beqz $v1, push; lw $v0, id; beqz $v0, skip` at `0x4d8170`).
- `reset_homemenu_index(non-zero)` loads the saved list (`get_menu_file`, config `[MAIN] HOMEMENU`); if
  `change_lanflag` is set it removes ids 0 and 1 and pushes them back at the front (both when
  `language == 0`, only one otherwise), then saves. A language change therefore puts Tidal first.
- `load_home_menu` (`0x4d7dc4`) builds the customisation dialog's list (`0xa045c4`) from the saved list
  plus every `main_allmenu` id not in it with `shown = 0`, with the same `language != 0` skip for id 0.
- The user can show/hide any other id in Home customisation (`dialog/homemenu_dialog`).

`language` values (`switch_language` `0x4cca40`, jump table indexed by `language - 1`, Simplified
Chinese the default case): 0 (and anything outside 1-12) `zh_CN`, 1 `zh_HK`, 2 `en_US`, 3 `ja_JP`, 4
`ko_KR`, 5 `fr_FR`, 6 `ge_DE`, 7 `sp_ES`, 8 `it_IT`, 9 `th_TH`, 10 `po_PL`, 11 `ru_RU`, 12 `uk_UK`. The
HiFi icon exists only in Simplified Chinese; in English the default list is ids `1..17`.

## The stock library flow (record layout)

Browsing records are `stSongInfo` (0x58 bytes, `REC_*` in `offsets.inc`; read from the row callback
`0x4e93c8` / `0x4e908c`): `REC_ID`, `REC_TITLE` `+0x10` (an artist row's name too), `REC_ALBUM`,
`REC_ARTIST`, `REC_PATH` (`fileurl`), `REC_NAME`, `REC_CLASS` `+0x38` (stamped by `loadSongList`),
`REC_TRACK` `0x3c`, `REC_DISC` `0x40`, `REC_YEAR` `0x30`, `REC_CUE_START` `0x48`, `REC_TYPE` (8 = song,
4 = a card row), `REC_SIZE` `0x58` (`memset(local, 0, 0x58)` in `loadSongList` `0x4e2e4c`). The type's
copy function `0x5db54c` (registered by `_type_register(0x58, "stSongInfo", ...)` at `0x5dbc7c`)
duplicates every string at `+0x04..+0x2c` (the album artist at `+0x24` included) and copies the words
at `+0x00`, `+0x30..+0x50`, so `deque_assign` / `_deque_push_back` give a page its own copy.
Stock queries the payload runs:

| step | call | evidence |
|---|---|---|
| albums | `loadLocalClassList(0xf003)` (`0x4ee504`) -> `getAllAlbum` (`0x4ea3c4`) into `*pdeq_showlist` | what the Albums page runs |
| songs | `loadLocalClassList(0xf001)` -> `getAllMusic` | `allmusic_page_init` `0x528a44` |
| artists | `loadLocalClassList(0xf004)`: `GetAllAlbumArtist` (`0x4ea6e4`) when `artist_type` (`0xa05a14`) == 1, else `getAllArtist` (`0x4ea9d8`) | jump table `0x74c5b8` entry `0xf004` -> `0x4ee6e8`; `localclass_page_init` `0x536bb0` |
| an artist's albums | `loadAlbumList(0xf004, row)` (`0x4ee8d8`) -> class `0xff01` (`getAlbumByAlbumArtist` `0x4eb0e4` / `getAlbumByArtist` `0x4eaccc`) | `album_page_init` `0x5248b8`; clears `classinfo_save`, stores the artist (row `+0x24` when `artist_type` == 1 else `+0x18`) |
| the All songs row | the list's last row: `REC_ID` -2, type 4, `REC_ARTIST` = the artist | `getAlbumByArtist` appends it always (`0x4eae30`) |
| an album's tracks | `loadAlbumdetailList(0xf003, row)` (`0x4eea98`) -> `loadLocalClassList(0xff10)` -> `getMusicByAlbum` | `albuminfo_page_init` `0x5268bc`; fills the browsing record `0xa0c768`; an artist's album: `0xff01` -> `0xff11` (`getMusicByAlbumAnd[Album]Songer` `0x4ed008` / `0x4ecd3c`); All songs row (`classinfo[8]` = 1, `0x4eebec`) -> every song of the artist. `loadAlbumdetailList`'s second argument is the album RECORD pointer (not an index; `loadAlbumList` leaves the All songs row last in `*pdeq_showlist`, `REC_ID` -2); the whole state is the 0x390 byte record (`loadAlbumList` memsets it; name +0x10d, album +0xd, all-songs byte +8, Unknown Artist byte +0xa), which a list that outlives the page snapshots (`patch/songs.c` `sg.ci`) |
| opening the album page | `navigator_to_with_context("albuminfo_page", class \| row << 16)`: the context is an integer, not a pointer. The Albums row handler `0x523d94` builds it from `g_class_type` (`0xf003` Albums, `0xff01` an artist's albums) and the row; the Search handler `0x540588` assigns its albums into `*pdeq_showlist` first and passes `0xf003`. `albuminfo_page_init` (`0x526828`) reads the album row from `*pdeq_showlist`, runs `loadAlbumdetailList(class, row)`, `add_albumcover_task(row, 1)` and stores `classinfo[0]` in `g_class_type` | the page expects `*pdeq_showlist` to be the album list the row came from and the cover-task list (`albumcoverinfo_init` `0x4dcf9c`, which `album_page_init` `0x5248d0` runs right after `loadAlbumList`) built from it |
| the stock album page's header (not hooked) | `albuminfo_listitem0_layout` `0x526264`: a 100 px `list_item` (`list_item_notpress_style`) holding the `img_albumcover_m` image 100x100 (draw type scale-auto, file `/tmp/abp/<md5>1.jpg` set by `0x525a38` once the cover task has made it), the title `hscroll_label` (`0x524990`, `srlabel_item_white_style`, text `classinfo+0xd`), the artist (`0x524a64`, `srlabel_item_gray18_style`, `classinfo+0x20d`) and the Play all `button` 90x28 (`btn_imgplayall_style`: an orange pill image with its text baked in); row 0 of the scroll_view, the 64 px track rows follow | the cover thread (`parse_albumcovertask_thd`) renders the flag-1 file at `0x64` px (`addiu s3, zero, 0x64` at `0x4dd670`, unchanged; the flag-0 files of the Albums rows at `0x3c` become 52); the file's only reader is this page |
| Play all | the button handler `0x525d48`: the list's first track, `loadSongList(queue, name, cue, g_class_type)`, `start_player(queue, index, class, 2)` (`0x4e4648`), `force_refreshflag` `0xa05a63` = 1; the page stays up | what ours copies (Play all and Shuffle then open Now Playing like a track tap; the hook takes this handler off the button, `widget_off_by_func` `0x666ec0`) |
| play | `loadSongList(queue, name, cue_start, cls)` (`0x4e2ce0`) then `navigator_to_with_context("playing_page", {queue, index, cls, 2})` (`0x4d1d48`) | the row handler `0x5275a4`; `loadSongList` also fills `g_memory_info` `0xa0caf8` for memory playback |
| art | `toolsGetAlbumCover` `0x5eaee0` (embedded) then `toolsGetExternCover` `0x5eafec` (folder image) | order and lock of `parse_albumcovertask_thd` `0x4dd68c` |
| libjpeg use | decoder `0x5dd5ec` (picture info / decode at scale 1/d: scale_num `cinfo+0x30`, scale_denom `+0x34`, output_width `+0x70`, output_height `+0x74`, num_components `+0x24`; `jpeg_CreateDecompress(cinfo, 70, 0x1d8)`), encoder `0x5de554` (`jpeg_CreateCompress(cinfo, 70, 0x1a8)`; width `+0x1c`, height `+0x20`, input_components `+0x24`, in_color_space `+0x28`), `error_exit` `0x5dbfe0` (output_message, then `longjmp(err + 0x88, 1)`); `toolsGetExternCover` refuses a JPEG above 1,048,576 pixels (`0x5eb768`) and a PNG above 6,291,456 | `JPEG_PINS` in `tools/pod.py`; `patch/pccover.c` |
| cover extraction | `taglib_album_picture` (libtag_c, imported; GOT slot) `(track, dst, 0x100000, 0x600000)`: 2 JPEG, 1 PNG, 0 none, picture saved to `/tmp/.tmp_picture` (`0x757838`); loaders `0x5de714` (JPEG: whole up to 1024, else scale by longer side) and `0x5de1a8` (PNG, refused over 1024), resize `0x5e00bc` (fit by float division `0x5e0200..0x5e0228`, `0x5e02c4..0x5e02ec`; bilinear `0x5dc020`; writer `0x5de554`, `jpeg_set_quality(90)` at `0x5de680`); `toolsGetExternCover` file limits `0x5eb760` (PNG 1 MiB), `0x5eb7bc` (JPEG 6 MiB) | `COVER_PINS` in `tools/pod.py`; `patch/covercache.c`, `patch/pccover.c` |
| Most Played, Recently Played, Favourites | `loadLocalClassList(0xf008)` -> `getAllOftenRecord` `0x4ec690` (`select * from oftenplay`, then sorted; `REC_TRACK` = plays - 1), `(0xf007)` -> `getAllRecentRecord` `0x4ec578` (`select * from recentplay ORDER BY id DESC`: the last played first, at most 100), `(0xf00a)` -> `getAllFav` `0x4ec45c` (`myfav`) | jump table `0x74c5b8`; the Daily Mix reads the three and the library |
| the playlist headers | `loadLocalClassList(0xf00b)` -> `getAllPlayList` `0x4ec4e8` (`select * from playlist where id <= 100`) into `*pdeq_playlist` (`0xa045d0`; the temporary list `0xa03964` is assigned to it and cleared, `0x4ee638..0x4ee664`), then `musicNagvationTitle` | `playlist_page_init` `0x53eb24`, `checkPlayListByName` `0x4ef2e4` |
| a playlist's songs | `loadLocalClassList(0xff13)` -> `getMusicByPlayList(classinfo[1])` `0x4eddac` (`select * from playlist where id > 100 and cd_num=%d`, no ORDER BY: row order = insertion order) into `*pdeq_showlist`, at `0x4ee744..0x4ee754` | the Songs page, `allmusic_page_init` `0x528968` |
| the other song lists of `allmusic_page` (our Songs page lists them too, docs/modules/songs.md "The other lists") | Home tiles 9 / 10 / 11 / 12 / 13 open it with `0xf002` Hi-Res, `0xf00a` Favourites, `0xf008` Most played, `0xf007` Recently played, `0xf009` Recently added (the table above); its navbar builder `0x526a3c` adds Sort only for `0xf001` (`0x526d04`) and Search for every class but `0xff09` (`0x526cf0`) | `0x526ce0..0x526e78` |
| a Genres row (`localclass_page` `0xf006`) | the row tap `0x535c4c`: `classinfo[0]` = `0xff09`, the genre's name (row `+0x1c`) into `classinfo + 0x30d`, `classinfo + 0xc` = (row id == -1), then `navigator_to_with_context("allmusic_page", 0xff09)`: the genre's songs | `0x535c4c..0x535cfc` |
| a composer's albums (our Artists page on `0xf005`, `coverflow_artist(.., CLASS_COMPOSERS)`) | `loadAlbumList(0xf005, row)` (`0x4ee8d8`; the branch `0x4ee9c0`): classinfo cleared, `classinfo[0]` = `0xff02`, the composer's name (row `+0x20`) into `classinfo + 0x20d` (0x100 bytes), the byte `classinfo + 0xb` = (row id == -1), then `loadLocalClassList(0xff02)` = `getAlbumByComposer` `0x4eb514` (`select id,album,composer,fileurl from songtable where composer=".." group by album COLLATE NOCASE`, NULL name for the unknown row; it appends the same last "All songs" row as `getAlbumByArtist`: id -2, type 4, "local_allsong", `0x4eb668..0x4eb690`, so the All albums card works unchanged). `loadAlbumdetailList(0xff02, row)` (`0x4eeb70`): `classinfo[8]` = (row id == -2), title from `row + 0x14`, class `0xff14` (`getMusicByAlbumAndComposer` `0x4ed2d4`; the album page's artist line is `classinfo + 0x20d` for `0xff14`, `CLASSINFO_ARTIST_14`, which the stock header reads). So a composer's tap is an artist's with `0xf005` / `0xff02` for `0xf004` / `0xff01` | `0x4ee9c0..0x4eea2c`, `0x4ee810..0x4ee830`, `0x4eeb70..0x4eebc4`; not run on a device |
| a genre's name in the Genres rows | `getAllGenre` `0x4ec0dc` (`select id,style from songtable group by style COLLATE NOCASE`, an "Unknown Genre" row id -1) with its row callback `0x4e9b80`: the one string is copied twice, to `+0x1c` (what the row tap reads) and `+0x10` (`REC_TITLE`, what the rows show); `loadAlbumList(0xf006, row)` (`0x4eea2c`, class `0xff03`, name into `classinfo + 0x30d`, byte `+0xc`) is the stock album list of a genre, not used by ours (a genre's tap lists its songs) | `0x4e9bd8..0x4e9c64` |
| the title of a genre's songs | the page's title is made by the stock query itself (`loadLocalClassList` calls `musicNagvationTitle` `0x4ee2e4..`; `allmusic_page_init` copies `nagvation_title` `0xa0533c` into `0xa06690` after the query, `0x528a40..0x528a6c`), so the fallback to the stock page needs only the browsing record and `navigator_to_with_context("allmusic_page", 0xff09)` | `0x528a40` |
| an Artists / Composers row (`localclass_page` `0xf004` / `0xf005`) | the same handler's other branch `0x535d04`: `navigator_to_with_context("album_page", {g_class_type, row record})`: the stock list of that artist's or composer's albums | `0x535d04..0x535d54` |
| the stock Add button of `allmusic_page` | `0x5280c0`: `dialog/batchadd_dialog` (0 playlist, 1 favourites), then `navigator_to_with_context("playlist_page", 1 << 16 \| g_class_type)` (`0x52817c..0x528194`); favourites: `batch_add_file(.., 0xf00a, ..)` (`0x5281c8`) | `batch_add_file` (`0x4da7dc`) with class `0xff11` takes the generic path (rows of type 8), like the library's: an artist's songs list needs nothing special for Add (nor for Delete: `0xff11` is in the generic loop below) |
| opening a playlist | the Playlists row's tap `0x53d578..0x53d5f4`: `memset(0xa0533c, 0, 0x200)`, `snprintf(0xa0533c, 0x200, "%s", header->title)`, `classinfo[1]` (`0xa0c768 + 4`) = `header->cd_num`, `navigator_to_with_context("allmusic_page", 0xff13)`: the context is the class, a value. The page copies the title (`0xa0533c` -> `0xa06690`, `0x528a6c`) | what `patch/playlists.c` repeats (Daily Mix no longer opens a stock playlist: it has no playlist) |
| the playlist table | `playlist` in `/mnt/data/database.db`, the `songtable` columns: a header has `id <= 100`, type 4 (`+0x34`), the name at `+8` and `+0x10`, `cd_num` (`+0x40`) = its id; a song row has `id > 100` and `cd_num` = the header's id. `createPlayListItem` `0x4eeca8(deque, name)`: -1 for no deque, 100 or more headers or ids, -2 for a name already there, else the first id from 0 the headers (in id order) do not have, inserted with `addPlayList` | `0x4eed1c..0x4eeeb4` |
| the Daily Mix page (`dp_*`, docs/modules/dailymix.md "The page") | **no new address**: it uses calls already pinned above (`window_open` `0x679fd4`, `widget_set_style` `0x66c448` for the tint, `widget_move`, `widget_measure_text` `0x66c7e0`, the canvas calls, `loadLocalClassList(0xf001)` for the library, `loadSongList`, `_deque_push_back`); the asset is ours (`ui/m1plus_dailymix.bin`) | |
| the stock import sequence (`importPlayList` `0x4ef394`; the Daily Mix does not use it, but its files must never be importable: it reads only `/mnt/mmc/_explaylist_data` through `toolsGetDirectoryM3u8` `0x5e9794`, names ending `.m3u8` / `.m3u`; `checkPlayListExist`, `getPlayListMaxId` and `addPlayList` below ARE pinned since the Daily Mix page's Add disc, `docs/modules/dailymix.md` "The Add disc"; `deletePlaylist`, `deleteAllMusicByPlaylist` are not) | per playlist file: `checkPlayListByName` -> `deletePlaylist(id)` `0x4edf98` + `deleteAllMusicByPlaylist(id)` `0x4edfdc` + `loadLocalClassList(0xf00b)`; `createPlayListItem`; then per song `checkPlayListExist(rec, id)` `0x4ee1a8` (1 = already in), `getPlayListMaxId()` `0x4ee184` (the row id is `max(100, that) + 1`, `0x4ef614..0x4ef62c`), `get_songid3_info` `0x4da694` (tags from the file; the Daily Mix has them from the library), `addPlayList(rec)` `0x4ee1cc` (= `toolsInsertDbTable(rec, "playlist", db, 1)` `0x5ee2fc`: the row keeps `rec + 0`; strings `+8 +0xc +0x10 +0x14 +0x18 +0x1c +0x20 +0x24`, ints `+0x30 +0x3c +0x40 +0x48 +0x4c +0x50`, byte `+0x54`; returns 1). Addresses from the disassembly (no longer pinned by a test) | `0x4ef4b0..0x4ef83c` |

## Deleting by class

`batch_delete_file(class, list, selection, 0, delete_file)` (`0x4e1408`, pinned) is what every stock list's Delete runs, with `g_class_type` (the `allmusic_page` handler
`0x527f48`, after the one confirm dialog for all classes: `0xa` the list only, `0x14` with the file). It dispatches on the class: `0xf003..0xf00b` through the jump table
`0x74b7b0`, `0xff01..0xff14` through `0x74b7d4` (target = word + gp `0xa03ed0`), anything below `0xf003` (the library `0xf001`, Hi-Res `0xf002`) to the generic loop. Each loop
runs one table delete per marked row and then `remove_file` `0x4e1264` (`access`, `remove`, `sync`, then a look at the player's state) when `delete_file` is set:

| class | loop | per row |
|---|---|---|
| `0xf001` library, `0xf002` Hi-Res, `0xf009` Recently added, `0xff09` a genre's songs, `0xff10..0xff12`, `0xff14` | `0x4e1664` | `deleteMusicFromMusicDb` `0x4ede44` (`songtable`) |
| `0xf00a` Favourites | `0x4e1710` | `0x4ede88` (`myfav`: unfavourite) |
| `0xf008` Most played | `0x4e17b4` | `0x4edf10` (`oftenplay`) |
| `0xf007` Recently played | `0x4e1858` | `0x4edecc` (`recentplay`) |
| `0xff13` a playlist's songs | `0x4e18fc` | `deleteMusicFromPlaylist` `0x4edf54` (`playlist`) |
| `0xff04..0xff08`, `0xff0a..0xff0f` | none | nothing |

Screen state: exported byte `backlight_status` at `0x97cae4` is pinned in `tools/pod.py`. Stock `awake_screen` sets it to 1 before enabling the framebuffer; zero means off. Existing page-owned timers use it to defer visual work.

## Library scan and queries (patch/common.c `pod_scan_dir`, patch/pcmodel.c `pc_library_query`; `SCAN_PINS`, `QUERY_PINS` in tools/pod.py)

| What | Address | Evidence |
|---|---|---|
| `toolsLoadAllFile` | `0x5efd98` | recursive walk (calls itself through `0x418(sp)`); lists each folder with `0x5ea364`; callers `scanAllMusicFile` `0x4e9e5c`, `scanSpecFolder` `0x4e9f74`; not boot-reachable |
| the folder lister | `0x5ea364` | prologue `(0x3c1c0042, 0x279c9b6c, 0x0399e021)`; readdir loop at `0x5ea600`; a directory entry (`d_type` 4) goes through `strcmp` tests against `.`, `..`, `lost+found`, `System Volume Information`, `RECYCLER`, `$RECYCLE.BIN`, `.LOST.DIR`, `.fseventsd`, `.Spotlight-V100`, `.Trashes` (a zero result: back to `0x5ea600`), then `._` for files |
| the folder test's hook site | `0x5ea6a8` | `jalr strcmp(name, ".")` (words @`0x5ea69c..0x5ea6b0` pinned, the delay slot `0x24a53ed4` loads `"."` `0x743ed4`): replaced by `jal pod_scan_dir`; docs/modules/payload.md hook 5 |
| `toolsQueryDbTable` | `0x5ee77c` | prologue `(0x3c1c0041, 0x279c5754, 0x0399e021)`; `(db, sql, row cb, sort)`; `sqlite3_exec` @`0x5ee7fc`; 36 callers (every `getAll*` / `getMusicBy*` / `getAlbumBy*` / `Search*`, the fav / recent / often / playlist lists); hooked: `pc_library_query`, payload.md hook 6; **called by the payload** (`dm_rows`, dailymix.md) with the db string `0x745a34`, the song row callback `0x4e9058` (18 columns, pushes into `*tools_pdeq_directory` `0xa03964`, `PDEQ_TOOLS_TMP`: `toolsQueryDbTable` clears it first, `loadLocalClassList` then assigns it to `*pdeq_showlist` and clears it; `getAllMusic` -> `sort_first_alphabet` `0x4ea0ac` passes sort 1), pinned in `QUERY_PINS` |
| `getAllFav` / `checkFavExist` / `addMyFav` / `deleteMusicFromFav` | `0x4ec45c` / `0x4ee210` / `0x4ee234` / `0x4ede88` | prologues pinned (`QUERY_PINS`); `getAllFav` is `sprintf "select * from %s"` of `myfav` + `toolsQueryDbTable` (jalr @`0x4ec4d0`); the other three take a song record (`+8` name, `+0xc` path) and are `toolsCheckItemExist` / `toolsInsertDbTable` / `toolsDeleteDbTable` on `myfav`; the star's `manage_myfav` `0x4ef884` = check, then delete or add; Saved (podcasts.md) calls them for episodes |
| `utf8_to_pinyin` | `0x73a5f0` | `(in, out)`: appends to `out` (found with `strlen`, so the buffer starts zeroed) one byte per ASCII char and, per 3-byte char U+4E00..U+9FA5, its pinyin initial (lower case, table `0x9e2310`); other 3-byte chars drop, a 2-byte char is read as three bytes; `toolsQueryDbTable`'s title comparator `0x5e0dac` and the scan's Initial call it; **called by the payload** (`cc_name_keys`, one CJK character at a time) |
| `toolsQueryDbTableAndSort` | `0x5ee9ac` | prologue `(0x3c1c0041, 0x279c5524, 0x0399e021)`; callers `sort_filename` `0x4ea18c`, `sort_format` `0x4ea218` (via `getAllMusic`); hooked: `pc_sorted_query` |
| the SQL texts | `0x74ba4c`.. | `"songtable"` `0x74ba4c`, `"myfav"` `0x74ba58`, formats from `0x74ba6c` (`select * from %s ...`) to `0x74c510`; sprintf'd by the `getAll*` / `getMusicBy*` wrappers; `toolsCheckItemExist` `0x5ef578` (the scan's duplicate check) runs its own `sqlite3_exec` |

## Status bar and battery (patch/battery.c, `BATTERY_PINS` in tools/pod.py; docs/modules/battery.md "The percentage")

| What | Address | Evidence |
|---|---|---|
| `show_sysbar_face` | `0x544b48` | prologue `(0x3c1c004c, 0x279cf388, 0x0399e021)`; the status bar's refresh: called by `system_bar_init` `0x545490` (once, with the window) and by the 1 s timer `0x545394` (`widget_add_timer(.., 0x3e8)` in `systembar_timer_start` `0x5453c8`); fills `img_battery` / `pgbar_battery` from `power_capacity`; not on the reach.py boot path (system_bar_init is a navigator page-init call, `0x4d1cb8`) |
| the hook site | `0x5450f8` | `jalr get_battery_capacity` (`lw t9` GOT `0x8f99be60` @`0x5450f4`, delay slot nop @`0x5450fc`, `beqz s3` `0x12600089` @`0x545100`, `lw gp, 0x10(sp)` `0x8fbc0010` @`0x5450f0` and `0x545104`): replaced by `jal bp_capacity`; the return value is dropped by stock; docs/modules/payload.md hook 8 |
| `get_battery_capacity` | `0x4e6dd8` | prologue `(0x3c1c0052, 0x279cd0f8, 0x0399e021)`; buckets `toolsGetBatteryVoltage` `0x5e35b0` (the `0x97cad0` copy) into 0/20/40/60/80/100, or, charging (`toolsGetChargeStatus` `0x5e37a0` is 1), adds 10 per call (wraps to 0 past 100); stores the result in `power_capacity` and returns it; callers `platform_init` `0x50bf00` (boot, stock), `on_poweroff_keyup_fun` `0x53ed08`, `show_sysbar_face` |
| `power_capacity` | `0xa059ec` | int, `lw s0, GOT` `0x8f90a9dc` @`0x4e6e88` and `0x545120`; read by `show_sysbar_face` (`0x545154` the fill / low picture, `0x54536c` the charging value), `dropdown_showface` `0x475c5c` (the pull-down's own timer), `poweroff_page_init` `0x53f5dc` / `0x53f670`, `on_poweroff_keyup_fun` `0x53eec0` / `0x53efb8`, `check_updatefw_exist` `0x4d8c1c` and `check_otginfo` `0x4d91dc` (only `capacity \| charge_status != 0`) |
| `widget_t` fields | `+8` w, `+0xc` h, `+0x44` parent | `widget_resize` `lw v0, 8(s0)` @`0x66d194`, `lw v1, 0xc(s0)` @`0x66d1a0`; `widget_set_visible` hands `lw a0, 0x44(s0)` @`0x66c428` to `widget_set_need_relayout_children` `0x66c338` |
| the gauge | `/sys/class/power_supply/battery/capacity` | AXP2101 (`axp2101_charger`), an integer 0..100 and a newline (read 100 on a charged device); stock never opens it |

## Song dates (patch/filetime.c, `FILETIME_PINS` in tools/pod.py; docs/modules/songs.md "Recently Added dates")

| What | Address | Evidence |
|---|---|---|
| `toolsGetFileCreateTime(path)` | `0x5e4ac8` (size `0x9c`) | prologue `(0x3c1c0042, 0x279cf408, 0x0399e021)`; `bnez a0` `0x14800008` @`0x5e4ae4` (null: 0); `access(path, R_OK)` then `stat(path, sp+0x18)`; calls at `0x5e7a8c`, `0x5e8494`, `0x5eae84` (inside the stock directory loader, `toolsLoadDirectory` side; the result is stored as the song record's `time_create`, stSongInfo `+0x50`, per `recent-albums` notes) |
| st_atime / st_ctime choice | `0x5e4b3c`..`0x5e4b5c` | `lw v1, 0x58(sp)` (stat's `st_atime`, `0x40` into the mips32 stat) @`0x5e4b40`, `lw v0, 0x68(sp)` (`st_ctime`, `0x50`) @`0x5e4b48`, `lbu s0, 0xa0ac7c` (the filesystem format byte) @`0x5e4b44`, `addiu/andi/sltiu s0, s0, 2` (format 1 or 2), `movn v0, v1, s0` `0x0070100b` @`0x5e4b58`: exFAT / NTFS return the access time |
| `statx` | o32 syscall 4366 | demo imports no `statx`; `struct statx` is 256 bytes, `stx_mask` at 0, `stx_btime.tv_sec` at 80 (`STATX_BTIME` `0x800`) |

## Podcasts (patch/pcmodel.c, `PODCAST_PINS` in tools/pod.py)

| What | Address | Evidence |
|---|---|---|
| `seek_time(sec)` (q2-pod's `player_seek_time`) | `0x4e0544` | prologue `(0x3c1c0052, 0x279c398c, 0x0399e021)`; `move s0,a0` @`0x4e0560`; `lw a0,0x48(v0)` (the record's CUE start) @`0x4e05f0`; `addu s0,s0,a0` @`0x4e05fc`; `jalr mclSetSeek` @`0x4e0608`; it returns 0 at once when `mclGetPlayStatus` is 1, resumes a paused player, waits up to 2 s for the second |
| `reset_poweroptions_timer(standby, auto_off, screen)` | `0x4d7874` (size `0xa0`) | prologue `(0x3c1c0053, 0x279cc65c, 0x0399e021)`; `move s0,a2` @`0x4d788c`, `move s1,a1` @`0x4d7894`; `beqz a0` @`0x4d7898` guards `bal setstandby_time 0x4d782c` @`0x4d78a8` (300 s when the setting byte at `0xa05a8c` is 1, else 0 = never; the result is stored in the standby counter `0xa05a88`), `beqz s1` @`0x4d78bc` guards `bal setsavepower_time 0x4d783c` @`0x4d78c8` (auto power-off: the table at `0x74b87c`, counter `0xa05a80`), `beqz s0` @`0x4d78dc` guards `bal setlight_time 0x4d77f4` @`0x4d78ec` (the screen's light: table `0x74b884`, counter `0xa05a78`). A non-zero argument sets that countdown again, zero leaves it: the Podcast downloads call `(1, 1, 0)` from the page's timer (UI thread only). 78 references in stock (the volume / touch / dialog handlers call it on activity) |
| `mclSetPlaySpeed(mode)` | `0x5d281c` | prologue `(0x3c1c0043, 0x279c16b4, 0x0399e021)`; `move a2,a0` @`0x5d2830` is the `%d` of `{mcl-playspeed\%d}` (`0x756510`) |
| `playspeed_mode` (data, dynsym) | `0xa05acc` | 0..3 = 1x, 1.25x, 1.5x, 2x; the Multiple Speed handlers (`0x479970`.. ) store 3, 2, 1, 0 and call `mclSetPlaySpeed`; `config_mplayer` `0x4d869c` sends it at set-up; `config_init` reads a value >= 4 as 0 |
| `get_id3info` | `0x4dfd58` | prologue `(0x3c1c0052, 0x279c4178, 0x0399e021)`; fills `playsong_id3info` from `toolsGetMusicInfo` `0x5ec6a8` (call @`0x4e0000`, `addiu a1,s1,0x404` @`0x4dfff8`) unless `mclGetCueFlag` (record `+0x48` or `+0x4c` > 0); title `lb 0x684(s1)` @`0x4dff74`, artist `lb 0x504(s1)` @`0x4dffac` |
| the tag reader's hook site | `0x4dff4c` | `jalr strcpy(info, path)` (words @`0x4dff40..0x4dff50` pinned): replaced by `jal pc_id3_path`; docs/modules/payload.md hook 4 |
| `playsong_id3info` (data, dynsym) | `0xa0d88c` | 0xa9c bytes: path (cache key) `+0`, CUE start `+0x400`, album `+0x404` (0x100), artist `+0x504` (0x100), composer `+0x604` (0x80), title `+0x684` (0x200) |
| `song_name` / `song_artist` (data, dynsym) | `0xa0513c` (0x200) / `0xa0503c` (0x100) | built by `get_id3info` after the site from the struct: title (else the file name `rec+8`), artist (else `"Unknown"` @`0x7466e8`); read by the Now Playing page (`0x5397a0`), the lock screen (`0x53f77c`), the Home guide page |

## Fonts and locale (patch/fontregion.c, `FONT_PINS` in tools/pod.py; docs/modules/fonts.md "Regional forms")

| What | Address | Evidence |
|---|---|---|
| `font_stb_create_ex` | `0x67ee74` | `tk_calloc(1, 0xd4)` @`0x67ef14`: font_t (name[32], match `+0x20` = `0x67d2d4` (name only), get_glyph `+0x24` = `0x680228`, get_vmetrics `+0x28`, shrink_cache `+0x2c`, destroy `+0x30`, desc `+0x34`), then `stbtt_fontinfo` at `+0x38` (data `+0x3c` @`0x67f030`, fontstart `+0x40` @`0x67f038`, index_map `+0x64` @`0x67f758`: cmap + the last record of platform 0 or 3/1, 3/10), glyph cache `+0xb4`, vmetrics `+0xc4..0xcc`, mono `+0xd0` |
| `stbtt_FindGlyphIndex` | `0x67c3b4` | `lw a3,4(a0)` / `lw t0,0x2c(a0)` @`0x67c3c0`: data and index_map read on every lookup (a0 = font + 0x38, from `font_stb_get_glyph` `move a0,s6` @`0x680300`, after its glyph cache misses) |
| `font_manager()` / `font_manager_get_font(fm, name, size)` | `0x650ad0` / `0x650dc4` | global `0xa0be30`; lookup by name (`font_manager_lookup` `0x650cc0`), else load and add; one stb object serves every size; `"default"` @`0x74a988` |
| `font_manager_shrink_cache(fm, keep)` | `0x6510b8` | every font's `glyph_cache_shrink` (`0x6a43b4`); keep 0 frees every glyph; stock calls it with 10 from the main loop (`0x5f27ec`) |
| `image_manager_lookup(imm, name, out)` / `image_manager_get_bitmap(imm, name, out)` | `0x655850` / `0x655ccc` | lookup is cache only (memset `0x60`, `darray_find`, `memcpy 0x48`, `sb 0,0x30(out)`, access time and use count updated, else 9). get_bitmap (dynsym) calls the static helper `0x655944`: lookup, else `assets_manager_ref` + decode + `image_manager_add` (`bal` `0x655adc`, through the hook) |
| `image_manager_unload_unused(imm, age)` | `0x655f58` | `thr = time_now_s() - age` (64 bit: `subu` `0x655f88`, borrow `sltu` `0x655f90`, stored as a key at `sp+0x18` with the time at `+0x58` / `+0x5c`), then `darray_remove_all(imm, 0, key)` with the callback `0x6553e0`; one caller, the main loop's memory handler (`0x5f2790`; `jalr` @`0x5f27c4` level 1 age 10, @`0x5f282c` level 2 age 0; level 3 also `font_manager_unload_all`) |
| image manager darray and cache entry | `imm` | `imm` is a `darray_t`: size `+0`, element pointers `+8`, compare `+0x10`. An element is a 0x60 byte entry: bitmap_t copy `+0` (0x48), name `+0x48` (`image_manager_add` `0x6556f8`, strdup), use count `+0x4c`, created `+0x50` / `+0x54`, **last access `+0x58` (low) / `+0x5c` (high), u64 seconds** (add `0x655708` / `0x655700`; **every `image_manager_lookup` hit sets it to now**, `0x655918` / `0x655920`). `darray_remove_all` calls `cmp(element, key)` and **removes the element when it answers 0, keeps it when non-zero**. The callback `0x6553e0` compares the u64s unsigned, high word first, and answers -1 (keep) only when `threshold < entry time` (strict): an entry exactly `age` old goes, and at age 0 only an entry ahead of now stays. `image_manager_unload_all` (`0x655fdc`, tail `jr darray_clear` `0x6f1b28`) ignores the times. `image_manager_add`'s mem-limit sort (`0x65542c`) orders by the low word's 32 bit difference, newest first, and pops the last. All pinned in `LIGHT_PINS` (`tools/pod.py`), the comparison run from the stock words by `test/pod/palette.py evict_tests` |
| `font_manager_unload_all` | `0x650f74` | frees the font objects: the window manager's locale handler (`0x6772dc`) and `widget_set_theme` (@`0x66d550`) call it, so a language or theme change recreates the font |
| `locale_info()` / `locale_info_on(locale, type, cb, ctx)` | `0x6588b0` / `0x658ba8` | locale_info_t: country[3] `+0`, language[3] `+3` (`locale_info_reload` `"%s_%s"` from `+3`, `+0` @`0x658970`), emitter `+0x10`; `locale_info_on` = `emitter_on(+0x10, 0x122, cb, ctx)`; `locale_info_change` dispatches `EVT_LOCALE_CHANGED` 0x122 (@`0x658a7c`) only when it changes; emitter handlers run newest first |
| `font_manager_get_font` retry / `font_manager_load` / `font_get_glyph` | `0x650ebc` (`bnez v0, 0x650dfc`) / `0x650d00` / `0x6508b0` | a font name that cannot be loaded (`assets_manager_ref` of `fonts/<name>.ttf`) is retried once with the default font name; `font_get_glyph` is one vtable call: no per-glyph fallback. The lyrics' second font `lyrics.ttf` relies on both (`LYRICS_PINS`, docs/modules/fonts.md) |
| label paint row pitch | `0x62e9f8` / `0x62ea04` / `0x62ea24` | `"spacer"` (`0x75add8`, default 2) + canvas font size (`lhu s5, 0xc(s0)`) = the pitch of the rows of a wrapped label (`LY_LINE_H`, docs/modules/lyrics.md) |
| `EVT_THEME_CHANGED` | 0x14a | `widget_set_theme` `0x66d444` (@`0x66d4bc`), dispatched on the window manager after the font unload and theme load (`0x66d618`) |

## Pinyin engine (patch/keyboard.c Chinese layer, `PINYIN_PINS` in tools/pod.py; docs/modules/keyboard.md "Pinyin engine")

AOSP's PinyinIME (`ime_pinyin::*`, `0x5bf9b0`..`0x5ceb40`) over one global. All the C entry points are `.dynsym` names with PIC prologues `(0x3c1c0044, 0x279c.... , 0x0399e021)` (pinned).

| What | Address | Evidence |
|---|---|---|
| the engine global `MatrixSearch*` (data) | `0xa0a360` (GOT word `0xa00410`) | NULL until `im_open_decoder`; byte `+0` is `inited_` (tested `lbu` by `search` `0x5c5740`, `get_candidate` `0x5c5128`, `get_candidate_num` `0x5c3094`; set by `sb v0,(s0)` @`0x5c2ed0` / `0x5c2ff8`); sizeof `0x30d8` |
| `im_open_decoder(sys, user)` | `0x5c7350` | destroys the object at the global (`0x5c7384`), `new` (`0x30d8` bytes), `MatrixSearch::init(sys, user)` `0x5c2ddc` (NULL path: fails); returns its result |
| `im_open_decoder_fd` | `0x5c743c` | `init_fd(fd, start, len, user)` `0x5c2ef0`; no caller in demo; not used |
| `im_close_decoder` | `0x5c7534` | `close()`, destroy, `*global = 0` @`0x5c7594` |
| `im_set_max_lens(sps, hzs)` / `im_flush_cache` | `0x5c75a8` / `0x5c75dc` | thin wrappers; stock's wrapper uses 9 / 12 |
| `im_search(buf, len)` | `0x5c760c` | `MatrixSearch::search(buf, len)` `0x5c5710` (len clamped to 39), then the candidate count |
| `im_delsearch(pos, is_pos_in_splid, clear_fixed)` / `im_reset_search` | `0x5c7678` / `0x5c76e8` | `delsearch` `0x5c5880`, `reset_search` `0x5c3018` |
| `im_get_sps_str(&len)` | `0x5c7720` | the pinyin string the engine read |
| `im_get_candidate(i, buf, max_len)` | `0x5c7754` | `get_candidate` `0x5c5104`; UTF-16 into `buf`, returns `buf` or NULL |
| `im_get_spl_start_pos(const char16 **)`, `im_choose(i)`, `im_cancel_last_choice`, `im_get_fixed_len` | `0x5c778c`, `0x5c77c0`, `0x5c77f4`, `0x5c7824` | `get_spl_start` `0x5c37b8` (returns the syllable count `+0x2dc`, `*out = this + 0x2e0`: the start offsets, one more than the count), `choose` `0x5c6244`, `cancel_last_choice` `0x5c5ba8`, `get_fixedlen` `0x5c32bc`; pinned: prologues of `im_get_spl_start_pos`, `im_get_fixed_len` |
| hanzi to pinyin (called by the search page's initials index, patch/search.c; pinned prologues in PINYIN_PINS) | `DictList::get_splids_for_hanzi(this, hanzi, half_splid, splids, max)` `0x5bffd4`, `SpellingTrie::get_spelling_str(this, splid)` `0x5c922c`, `DictList::get_lemma_id(this, str, len)` `0x5c01a4` | the `DictTrie` is `*(MatrixSearch + 0xc)` (vtable `0x978e7c`), the `DictList` `*(DictTrie + 4)`, the `SpellingTrie` `*(DictTrie + 8)` (also the global `0xa0a370`); `get_splids_for_hanzi` dereferences the result of its binary search (`mybsearch` `0x5c69f8`) and **crashes for a character that is not in the dictionary**: test `get_lemma_id(&ch, 1) != 0` first; `get_spelling_str` gives the spelling in upper case with a capital-and-lower head for initials (`ZhOU`) |
| `MatrixSearch::get_predicts(this, history, out[][8], n)` | `0x5c6834` | 1..7 character history (`utf16_strlen` `0x5cec6c`, then `inner_predict` `0x5c65d4`); no C wrapper |
| `inputmethod_module` (stock's wrapper), its global object | `0xa0c2bc` (`0xa10000 - 0x7d44`) | constructor `0x5bf2d0` sets byte `+4`; `dequeinit` `0x5bf230`; `init` `0x5bf460` (path argument ignored: opens `/usr/dict_pinyin.dat` `0x755fd0` and `/usr/dict/dict_pinyin_user.dat` `0x755fb0`, then `im_set_max_lens(9, 12)`); `search` `0x5bf32c` (`+0x10` = the count `0x5bf104` keeps); `get_candidate` `0x5bf768` (malloc'd UTF-8, `utf16_to_utf8` `0x5bf568`; `0x8aed58` when empty); `choose` `0x5bf908` |
| who initialises it | `keyboard_init` `0x5b25d4` <- `user_keyboard_init` `0x547b9c` (`0x547cd0`) <- the page-init dispatcher (`on_wm_timer_rgbled_state`, `0x4d06cc`) for the window `user_keyboard` `0x744968` | opened by `dialog_kbaddnet_dialog_init` `0x477a7c` (Wi-Fi), the playlist-name and keyword search dialogs; not at boot |
| the dictionary asset | `/release/assets/default/raw/data/gpinyin.dat` (1,068,442 bytes) | referenced by no code; stock's init asks for `/usr/dict_pinyin.dat`, absent from the rootfs |

## Settings (patch/m1plus.c, `SETTINGS_PINS` in tools/pod.py; docs/modules/settings.md "Stock pages and state")

| What | Address | Evidence |
|---|---|---|
| the stock pages the rows open | strings `0x748f1c` `systemset/wifi_page`, `0x748f00` `bluetooth_page`, `0x748ab4` `display_page`, `0x748a34` `language_page`, `0x7475a0` `playset/playmode_page`, `0x7474d4` `equalizer_page` | each a plain `navigator_to` (`0x4d1d80`) from the Wi-Fi hub's row thunks `0x4b1448` / `0x4b1410`, the Settings list's row handler (shared call `0x4ad830`, rows 3 / 0) and the Play Settings list's (shared call `0x4a0068`); the pins check the string loads and the calls |
| About page values | model literal `0x747718`, firmware literal `0x74773c`, `product_sncode` `0xa0553c`, `wifi_mac` `0xa061a8`, card floats `0xa03e74` (capacity) / `0xa03e70` (free), `getDiskMemoryInfo(path, &cap, &free)` `0x5b30e0`, `networkGetConnectStatus()` `0x5d7cac`, `networkGetIPAddr(0, buf)` `0x5d753c` | the stock About page's widget walk (callback `0x4a1240..0x4a170c`, init `0x4a170c`): rows scrlabel0..6 = model, firmware, capacity, Wi-Fi MAC, free space, serial number, IP; docs/modules/settings.md "About" |
| `get_equalizer_preset_name(i, buf)` | `0x49daec` | prologue `(0x3c1c0056, 0x279c63e4, 0x0399e021)`; `sltiu v1, a0, 12`; copies the tr key of `equalizer preset i` (table `0x97c7a0`: 1..3 `eq_custom1..3`, `eq_pop`, `eq_rock`, `eq_dance`, `eq_blues`, `eq_metal`, `eq_vocal`, `eq_classical`, `eq_jazz`) |
| the EQ switch handler | `0x49d750` | flips `equalizer_flag` and saves `[PLAYSET] EQFLAG` |
| `wififlag` / `bluetoothflag` / `equalizer_flag` / `equalizer_mode` / `language` (data, dynsym) | `0x97caf8` / `0xa05ac0` / `0xa05ac2` / `0x97cb00` / `0xa05ab8` | `wifi_switch` `0x507a8c` clears `wififlag` and saves `[SYSSET] WIFI`; the language index is `switch_language`'s (0 zh_CN .. 12 uk_UK), its names the `lan_*` keys |
| the play mode (Shuffle hooks, `SHUFFLE_PINS`; [shuffle](shuffle.md)) | `mclSetPlayMode` `0x5d278c` (mode word `0xa0abe0`, gapless state `0xa0abd0`), `mclLoadPlayList` `0x5d1f28` (position `0xa0abdc`), `mclSetPlayPos` `0x5d42d8`; raw mode readers `0x5d58fc` (`mclNextSong`), `0x5d5748` (`mclPrevSong`), `0x5d0edc` | the display sites `MODE_SITES` (19 `jalr mclGetPlayMode`, loaded by `lw t9 0x8f99aab0`) become `jal sh_display_mode` |
| the play mode's keys | `0x47a454`, `0x47a4d4`, `0x47a4e8`, `0x47a500` | the stock More dialog sets `playmode_listplay`, `playmode_repeattrack`, `playmode_shuffle`, `playmode_repeatall` for `mclGetPlayMode` 0..3 |

## Theme setting (`tools/themeoff.py` `EDITS`; docs/modules/theme.md "theme1 is off")

| What | Address | Evidence |
|---|---|---|
| theme flag (data, dynsym-less) | `0xa05a98` | read by `awtk_configinit` `0x4ccb88` (`widget_set_theme(wm, flag ? "theme1" : "default")`), set by `config_init` `0x4e63f4`, by the theme page `0x4ae6ac`; `[SYSSET] THEME` `0x748b8c`, `"theme1"` `0x748b84` |
| `config_init` clamp | `0x4e63d8` / `0x4e63dc` | `sltiu v1, v0, 2` (now `, 1`) / `movz v0, zero, v1` after `atoi` |
| System page row table / count | `0x97c8c0` (16 words) / `0x4adb1c` | read only by `systemset_sysset_page_init` (`0x4adb0c`) and the click handler `0x4ad7f0`; jump table `0x748ae0` (index 10 -> `0x4ad9f4`, `systemset/theme_page`), labels `0x97c988` (index 10 `sset_theme`) |

## Automatic time (`tools/autotime.py` `EDITS`; docs/modules/autotime.md)

| What | Address | Evidence |
|---|---|---|
| `AUTOSYNCTIME` key / byte / need-sync byte | `0x747a2c` / `0xa05ab1` / `0xa05a66` | `config_init` `0x4e6558` reads it (default text `"0"` `0x74c728`); `network_checkstatus` `0x5068e0` sets `0xa05a66` at `0x506a04` only when on |
| `networktime_adjust_thd` | `0x4d92bc` (thread created `0x50bd2c`) | 1 s loop; server literals `0x74ab24` time.nist.gov, `0x74ab34` time.apple.com, `0x74ab44` cn.pool.ntp.org, `0x74ab54` time.windows.com (all stock) |
| `toolsGetNetworkTime` | `0x5e32d4` | `ntpdate %s &> /tmp/result_ntpdate` slot `0x756f38` (stock), file `0x756f5c`, `"no server"` `0x756f70` |
| `toolsGetRtcTime` / `toolsSetRtcTime` | `0x5e34d8` / `0x5e34f4` | `hwclock -s` slot `0x756f7c` (12 bytes, now `hwclock -su`), `date -s` format `0x756f88`, `hwclock -w` slot `0x756fa4` (12, now `hwclock -wu`); callers `0x50be94` (`platform_init`), `0x4d77cc` (`set_systime`), `0x4d9470` |
| `select_timezone` / `toolsSetTimeZone` | `0x4d6b2c` / `0x5e3288` | `config_init` calls the first at `0x4e65ec`; the second is `setenv("TZ", name, 1)` |
| default config | `/release/assets/default/raw/config.ini` | `AUTOSYNCTIME=1`, `TIMEZONE=22`; copied to `/mnt/data/config.ini` only when missing (`config_init` `0x4e507c`) |

## Time zones (`tools/timezones.py` `PINS`; docs/modules/timezones.md)

| What | Address | Evidence |
|---|---|---|
| `time_zone` / picker | `0xa05ab4` / page builder `0x4a2424`, row builder `timezone_listitem_layout` `0x4a21c8`, click `0x4a25b8` | [timezones](timezones.md): clamp `0x4e65dc`, rows `0x4a246c`, click limit `0x4a2604`, row call `0x4a25a8`, label `0x4a2248`/`0x4a224c`; label key array `0x97c810` (27 pointers, strings from `0x747834`); row height `0x4a2518`, label style `0x4a22a4` (`srlabel_leftwhite18_style` `0x745f2c`), label y `0x4a225c`, tick y `0x4a2308` |
