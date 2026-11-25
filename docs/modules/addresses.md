# Known addresses of stock V2.1 demo

**Sources:** stock V2.1 `demo`; pins in `tools/pod.py` and `tools/pod_pins.py`.

Payload `PT_LOAD`: `0xb00000`; `$gp`: `0xa03ed0`. The `*_PINS` tables in `tools/` are the
authoritative list and the build fails on a mismatch. Inspect the binary with `tools/stock.py` or
`tools/disasm.py`. Behaviour belongs to the feature docs; hook numbers and fallbacks are in
[payload](payload.md).

## Hook prologues

Every prologue hook pins `$gp` and three words: `0x3c1c....`, `0x279c....` and `0x0399e021`
(`lui $gp; addiu $gp; addu $gp,$gp,$t9`). The table gives the first two and the resume address.

| # | Function | Address | Words | Resume |
|---|---|---|---|---|
| 1 | Home icon dispatcher | `0x533b80` | `0x3c1c004d, 0x279c0350` | `0x533b8c` |
| 2 | `home_page_init` | `0x534cd4` | `0x3c1c004d, 0x279cf1fc` | `0x534ce0` |
| 3 | `playing_page_init` | `0x53d1e4` | `0x3c1c004c, 0x279c6cec` | `0x53d1f0` |
| 4 | `get_id3info` | `0x4dfd58` | `0x3c1c0052, 0x279c4178` | call site `0x4dff4c` |
| 5 | folder lister | `0x5ea364` | `0x3c1c0042, 0x279c9b6c` | call site `0x5ea6a8` |
| 6 | `toolsQueryDbTable` / `...AndSort` | `0x5ee77c` / `0x5ee9ac` | `0x3c1c0041, 0x279c5754` / `0x279c5524` | +12 |
| 7 | `dialog_playmore_dialog_init` | `0x479cc4` | `0x3c1c0059, 0x279ca20c` | `0x479cd0` |
| 8 | `show_sysbar_face` | `0x544b48` | `0x3c1c004c, 0x279cf388` | call site `0x5450f8` |
| 9 | `select_timezone` | `0x4d6b2c` | `0x3c1c0053, 0x279cd3a4` | `0x4d6b38` |
| 10 | `style_get_color` | `0x659fcc` | `0x3c1c003b, 0x279c9f04` | `0x659fd8` |
| 11 | `style_get_gradient` (leaf) | `0x659f9c` | `0x10800009, 0, 0x8c820000` | none |
| 12 | `image_manager_add` | `0x655638` | `0x3c1c003b, 0x279ce898` | `0x655644` |
| 13 | `mclSetPlayMode` | `0x5d278c` | `0x3c1c0043, 0x279c1744` | `0x5d2798` |
| 14 | `mclLoadPlayList` | `0x5d1f28` | `0x3c1c0043, 0x279c1fa8` | `0x5d1f34` |
| 15 | `dialog_dropdown_dialog_init` | `0x475f04` | `0x3c1c0059, 0x279cdfcc` | `0x475f10` |
| 16 | `mclStartPlayer` | `0x5d5300` | `0x3c1c0043, 0x279cebd0` | `0x5d530c` |
| 17 | `on_backtoplayer_onclick` | `0x4cd58c` | `0x3c1c0053, 0x279c6944` | `0x4cd598` |
| 18 | `save_stop_player` / `save_start_player` | `0x4e2304` / `0x4e23e8` | `0x3c1c0052, 0x279c1bcc` / `0x279c1ae8` | +12 |
| 19 | `toolsGetFileCreateTime` | `0x5e4ac8` | `0x3c1c0042, 0x279cf408` | `0x5e4ad4` |
| 21 | Wi-Fi hub row thunk | `0x4b1440` | `0x3c1c0055, 0x279c2a90` | call site `0x4b1460` |
| 23 | `bigcover_page_init` | `0x529a24` | `0x3c1c004e, 0x279ca4ac` | `0x529a30` |
| 24 | Now Playing timer callback | `0x53cf48` | `0x3c1c004c, 0x279c6f88` | call site `0x53d0ec` |
| 25 | `screensaver_page_init` | `0x53fd44` | `0x3c1c004c, 0x279c418c` | `0x53fd50` |
| 29 | `loadLocalClassList` | `0x4ee504` | `0x3c1c0051, 0x279c59cc` | `0x4ee510` |
| 30 | `on_wm_tsdown_fun` | `0x4cd6e8` | `0x3c1c0053, 0x279c67e8` | `0x4cd6f4` |
| 32 | Bluetooth hub row thunk | `0x4b1408` | `0x3c1c0055, 0x279c2ac8` | call site `0x4b1428` |
| 41 | `check_cpumem` | `0x50b810` | `0x3c1c0050, 0x279c86c0` | `0x50b81c` |

Other hook sites (call-site words and two-word stubs):

| Site | Address | Note |
|---|---|---|
| 20 Line Out text | `0x544f90` (`show_sysbar_face`), `0x475ad8` (`dropdown_showface`) | `jalr widget_set_text_utf8(label_volume)` |
| 40 SyncLink shown | `0x545068` (`show_sysbar_face`), `0x475bb0` (`dropdown_showface`) | `jalr widget_set_visible(img_synclink, 1)`, after the Bluetooth image is set |
| 22 pull-down page opens | `0x4cd894`, `0x4cd8bc`; pull-down open `0x4cd864` | `bal navigator_to` in `on_wm_tsmove_fun` |
| 26 `mclNextSong` end branch | `0x5d5988` | resumes `0x5d5990` or re-enters `0x5d5950` |
| 27 Tidal search focus | `0x4c2088` (callback `0x4c1f3c`) | `jalr edit_set_focus` |
| 28 play-history call | `0x4ce930` | `jalr add_playrecord` `0x4efb08` |
| 43 Local .lrc open | `0x5d3bdc` | `jalr fopen(path, "r")` in the .lrc reader `0x5d3670` (`mclLoadExLyric` `0x5d41e4` tail-calls it) |
| 33 Volume page open | `0x4cd964` | `bal navigator_to_with_context("dialog/volume_dialog", 2)` in `on_wm_tsup_fun` `0x4cd8dc` |
| 31 play-status call | `0x4ce968` | `jalr mclGetPlayStatus` `0x5d3640` |
| 35 event1 key table load | `0x637bc8` | `lw v0, (v0)`; `sw v0, 0x58(sp)` in the event1 thread `0x637870` (table `0x75b324`); resumes `0x637bd0` |
| 36 end-of-track call | `0x4ce834` | `jalr mclAutoChange` `0x5d621c` (its only caller) |
| 37 failure markers | `0x4cf5b0`, `0x4cf8d0` | `jalr access` of `/tmp/notfile`, `/tmp/notsupport` in `on_wm_timer_dialogresponse` `0x4cf178` |
| 38 USB poll call | `0x4cef08` | `bal check_usb_status` `0x4ce1e8` in `on_wm_idle_status` (its only caller) |
| 39 USB page request | `0x4cf254` | `lbu v1, 0x41b1(v0)`; `beqz v1, 0x4cf2cc` in `on_wm_timer_dialogresponse` `0x4cf178`; resumes `0x4cf260` (open) or `0x4cf2cc` |
| 34 scan dialog finish refresh | `0x47baec` | `bal 0x47b604` (refresh with `done = 1`) in the dialog's timer callback `0x47bab0`; state word `0xa03a40`, stop byte `0xa0b088`, Auto Update byte `0xa05aa9` ([libupdate](libupdate.md)) |
| Display page Lock Screen row | `0x4a5ca8` (row handler `0x4a5c10`) | resumes `0x4a5c88` or `0x4a5c94` |
| Equalizer row | `0x4a0210` | resumes epilogue `0x4a0070` |
| Empty `scroll_view` event slot | `0x97a330` | data word |

hciplayer (`$gp` `0xb16750`, payload `0xe10000`): equalizer `af_info` `0x893808` (open slot
`0x89381c`), rate gates `0x42ce34` / `0x42fa78`, `mcl-seteq` flag parse `0x42cd1c`, gains
`0xb10df4`, `mpctx` `0xaf9e30` (`audio_out` at +8, its `get_delay` at +0x1c: `playing_audio_pts` `0x4300f4`); see `PINS` in `tools/mod_player.py`. On demo's side:
`set_equalizer_value` `0x4d851c`, `equalizer_flag` `0xa05ac2`, `equalizer_mode` `0x97cb00`.

## Stock functions and data the payload calls

| Name | Address | Use |
|---|---|---|
| `widget_lookup` / `widget_on` / `widget_set_text_utf8` | `0x666a74` / `0x666d20` / `0x66f720` | widget access |
| `widget_set_visible` / `widget_set_sensitive` / `widget_set_opacity` | `0x66c394` / `0x666b9c` / `0x669140` | hide, disable, dim |
| `window_open` / `navigator_back` / `navigator_to` | `0x679fd4` / `0x4d20dc` / `0x4d1d80` | `navigator_to` is `navigator_to_with_context(name, 0)` |
| `navigator_to_with_context` | `0x4d1d48` | context is an integer, not a pointer |
| `window_manager` / `window_manager_get_top_main_window` / `window_manager_switch_to` | `0x6774b4` / `0x6774f0` / `0x67891c` | switch is `(wm, current, target, close)` |
| `widget_is_window_opened` / `slide_menu_set_value` | `0x66aa04` / `0x61399c` | |
| `widget_to_local` / `widget_prepare_text_style` | `0x669b88` / `0x66a214` | Albums grid |
| `canvas_draw_text_in_rect` / `canvas_measure_text` | `0x6496a0` / `0x644544` | `canvas_measure_text` returns a float in `$f0` |
| `tk_utf8_to_utf16_ex` / `button_create` | `0x70eb24` / `0x622adc` | `wchar_t` is 32 bit |
| `widget_invalidate_force` / `widget_invalidate` | `0x6691d0` / `0x668d9c` | non-NULL `rect_t` is x, y, w, h in the widget's coordinates |
| `playpause_quick_click` / `next_quick_click` / `prev_quick_click` | `0x4cd150` / `0x4ccf00` / `0x4cccb0` | the quick-click handlers; next and prev ignore a click within 1 s of the last |
| `mclGetPlayStatus` | `0x5d3640` | 2 = playing, 3 = paused |
| `get_playtime` | `0x4e02e4` | seconds; compared with each lyric row's `lrc_time` |
| `mclLoadExLyric` | `0x5d41e4` | no arguments: clears the lyric deque, reads the play position's `.lrc` (tail call `0x5d3670`); stock follows it with `force_refreshflag` = 1 (`0x537cbc`) |
| `loadAlbumdetailList(class, album record)` | `0x4eea98` | `0xf003` -> `0xff10`, `0xff01` -> `0xff11`, `0xff02` -> `0xff14` |
| `system_bar` (data) | `0xa06f90` | the status bar window |
| `backlight_status` (data) | `0x97cae4` | 1 once the framebuffer is on; page timers use it to defer visual work |
| `player_timer_start` / `player_timer_clear` / `show_player_face` | `0x53c210` / `0x53c758` / `0x53bab4` | Now Playing 500 ms timer and immediate refresh on wake (`NP_IDLE_PINS`) |
| `hscroll_label_start` / `hscroll_label_stop` / `widget_add_timer` | `0x609648` / `0x6097e8` / `0x668c78` | Now Playing marquee pause while dark; lock screen timer replacement |
| lock screen timer (`0x53fc68`), refresh (`0x53f520`), cover (`0x53f9b4`) | `0x97ccf0` / `0xa05a60` / `0xa05a5c` | startup delay counter, track-dirty and cover-dirty flags (`LOCKSCREEN_PINS`) |
| `COVER_SRC` / `COVER_PARSED` (`savecover_path`) | `0x97cad8` / `0xa04c3c` | timed cover page |
| `COVER_MODE` | `0xa05aa5` | Cover mode byte; the Playback Settings row `0x4a0098` toggles it with `write_int_config(v, "SYSSET", "COVERMODE")` `0x4d6a2c` |
| idle countdown | `0x97ccd0` | reset to 20 at `0x53d0f4` |
| `sort_flag` | `0xa059d4` | Songs order of `0xf001`; saved by `write_int_config(.., "SORTSELECT")` |
| `*0xa045e0`, `select_recordinit` `0x4da3b0`, `set_selectindex` `0x4da434` | | the stock multi-select (a `vector<int>` per `*pdeq_showlist` row) |
| `batch_delete_file` / `batch_add_file` | `0x4e1408` / `0x4da7dc` | see "Deleting by class" |
| `stSongInfo + 0x54` | | the Initial byte (`*` digit, `A`..`Z`, `#`) |
| play queue deque | `*0xa0394c` | `PLAY_QUEUE`; `mclGetPlayType` `0x5d3658` |
| `songerinfoflag` | `0xa04737` | set by Look up artist; cleared by `album_page`'s window handler `0x522c64` |
| More sheet handlers | `0x4795cc` (Look up album), `0x4793ac` (Look up artist), `0x4798f0` (Add to playlist: `player_addplayList` `0x4efdcc`, then `playlist_page` `0x2f001`) | binder `0x478b44`; `patch/playmore.c` replaces the album one |

Pins by page: `LYRICS_PINS` (`scroll_lrc` `0x751c3c`, `lrc_time` `0x751c80`, the online timer
`0x537fec` and the lyric deque `*0xa062e8`), `IDLE_PINS`, `TAPE_PINS`, `PLAYLIST_PINS`
(`createPlayListItem` `0x4eeca8`, `getPlayListMaxId` `0x4ee184`, `checkPlayListExist` `0x4ee1a8`,
`addPlayList` `0x4ee1cc`, the name columns in `createPlayListItem` and `toolsInsertDbTable` `0x5ee2fc`, `nagvation_title` `0xa0533c`, `navigation_status` `0xa05a24`, `*pdeq_playlist`
`0xa045d0`), `SHUFFLE_PINS`, `NEXTALBUM_PINS`, `TSDOWN_PINS`, `LOCKSCREEN_PINS`, `RADIO_PINS`,
`JPEG_PINS`, `COVER_PINS`, `LIGHT_PINS`, `TEXTGAMMA_PINS`, `NP_IDLE_PINS`, `CHECK_CPUMEM_PINS`.

## Home icons and their conditions

`home_page_init` -> the page builder `0x534064` -> the icon builder `0x533d8c` walks a deque of
8-byte records `{int id; char shown; ...}` at `0xa045c0`, six icons per slide page. Each icon's
widget name is its decimal id, which the dispatcher `0x533b80` `atoi`s; `get_homemenu_showinfo`
`0x4d9ffc` indexes an 18-entry name table at `0x97c940`.

| id | name | opens |
|---|---|---|
| 0 | `hifimusic` | `hifi/hifimusic_page` (`msg_notnetwork` offline) |
| 1 | `tidal` | `tidal/tidal_main` (`msg_notnetwork` offline) |
| 2 | `sset_updatemusic` | `systemset/updatemusic_page` (our page opens instead: [libupdate](libupdate.md)) |
| 3 | `mymusic` | `allmusic_page` `0xf001` |
| 4 | `folder` | `folder_page` |
| 5 | `album` | `album_page` `{0xf003, 0}` |
| 6 / 7 / 8 | `songer` / `genre` / `composer` | `localclass_page` `0xf004` / `0xf006` / `0xf005` |
| 9 | `hr` | `allmusic_page` `0xf002` |
| 10 / 11 / 12 / 13 | `fav` / `many` / `recent` / `recentadd` | `allmusic_page` `0xf00a` / `0xf008` / `0xf007` / `0xf009` |
| 14 | `playlist` | `playlist_page` |
| 15 | `cdripper` | `cdripper_page` (sets GPIO `PA11`; needs the CD drive) |
| 16 / 17 | `playset` / `sysset` | `playset/playset_page` / `systemset/sysset_page` |
| 42 saved play type | `0x4e3384` | `jalr mclGetPlayType` in `save_memoryplay_info` `0x4e3340`; the result goes to `s2` (`0x4e338c`) and `g_memory_info[0]` (`0x4e3440`) |

- `reset_homemenu_index(0)` `0x4d8114` pushes every id of `main_allmenu` (`0x97ca88`, `0..17`),
  skipping id 0 when the `language` global (`0xa05ab8`) is non-zero.
- `reset_homemenu_index(non-zero)` loads `[MAIN] HOMEMENU`; if `change_lanflag` is set it moves ids
  0 and 1 to the front, so a language change puts Tidal first.
- `load_home_menu` `0x4d7dc4` builds the customisation list from the saved list plus every other
  id with `shown = 0`.
- `switch_language` `0x4cca40` maps `language` 0..12 to `zh_CN`, `zh_HK`, `en_US`, `ja_JP`,
  `ko_KR`, `fr_FR`, `ge_DE`, `sp_ES`, `it_IT`, `th_TH`, `po_PL`, `ru_RU`, `uk_UK`. The HiFi icon
  exists only in Simplified Chinese.

## The stock library flow

Browsing records are `stSongInfo` (`REC_SIZE` 0x58 bytes, `REC_*` in `offsets.inc`). The type's
copy function `0x5db54c` duplicates every string at `+0x04..+0x2c`, so `deque_assign` and
`_deque_push_back` give a page its own copy. The state of a browse is the 0x390 byte record at
`0xa0c768` (`classinfo`).

| Step | Call | Address and use |
|---|---|---|
| albums | `loadLocalClassList(0xf003)` -> `getAllAlbum` | `0x4ea3c4`, into `*pdeq_showlist` |
| songs | `loadLocalClassList(0xf001)` -> `getAllMusic` | `allmusic_page_init` `0x528a44` |
| artists | `0xf004`: `GetAllAlbumArtist` `0x4ea6e4` if `artist_type` (`0xa05a14`) = 1, else `getAllArtist` `0x4ea9d8` | jump table `0x74c5b8` |
| an artist's albums | `loadAlbumList(0xf004, row)` `0x4ee8d8` -> `0xff01` | `getAlbumByAlbumArtist` `0x4eb0e4` / `getAlbumByArtist` `0x4eaccc`; the last row is "All songs" (`REC_ID` -2, type 4) |
| an album's tracks | `loadAlbumdetailList(0xf003, row)` -> `0xff10` -> `getMusicByAlbum` | `albuminfo_page_init` `0x5268bc`; the second argument is the album record pointer |
| open the album page | `navigator_to_with_context("albuminfo_page", class \| row << 16)` | Albums row handler `0x523d94`, Search handler `0x540588`; `albuminfo_page_init` `0x526828` |
| Play all | button handler `0x525d48` | `loadSongList` then `start_player` `0x4e4648` |
| play a row | `loadSongList(queue, name, cue, cls)` `0x4e2ce0` -> `navigator_to_with_context("playing_page", ...)` | row handler `0x5275a4`; fills `g_memory_info` `0xa0caf8` |
| art | `toolsGetAlbumCover` `0x5eaee0` (embedded), then `toolsGetExternCover` `0x5eafec` (folder image) | `parse_albumcovertask_thd` `0x4dd68c`; stock album header cover is 100 px (`0x4dd670`) |
| Most / Recent / Favourites | `0xf008` `getAllOftenRecord` `0x4ec690`, `0xf007` `getAllRecentRecord` `0x4ec578`, `0xf00a` `getAllFav` `0x4ec45c` | jump table `0x74c5b8` |
| playlist headers | `0xf00b` -> `getAllPlayList` `0x4ec4e8` into `*pdeq_playlist` | `playlist_page_init` `0x53eb24` |
| a playlist's songs | `0xff13` -> `getMusicByPlayList(classinfo[1])` `0x4eddac` | no ORDER BY: insertion order |
| a genre row | tap `0x535c4c`: `classinfo[0]` = `0xff09`, then `allmusic_page` `0xff09` | `getAllGenre` `0x4ec0dc`, row callback `0x4e9b80` |
| an artist / composer row | tap branch `0x535d04` -> `album_page` | |
| a composer's albums | `loadAlbumList(0xf005, row)` -> `0xff02` -> `getAlbumByComposer` `0x4eb514` | tracks: `loadAlbumdetailList(0xff02, row)` `0x4eeb70` -> `0xff14`, `getMusicByAlbumAndComposer` `0x4ed2d4` |
| Add button of `allmusic_page` | `0x5280c0`: `dialog/batchadd_dialog`, then `playlist_page` | `batch_add_file` takes the generic path for rows of type 8 |
| the playlist table | `playlist` in `/mnt/data/database.db`, `songtable` columns | header: `id <= 100`, type 4, `cd_num` = its id; song: `id > 100`, `cd_num` = header id |
| stock import | `importPlayList` `0x4ef394`, reads only `/mnt/mmc/_explaylist_data` | `toolsGetDirectoryM3u8` `0x5e9794` |
| libjpeg | decoder `0x5dd5ec`, encoder `0x5de554`, `error_exit` `0x5dbfe0` | `JPEG_PINS`; `toolsGetExternCover` refuses JPEG above 1,048,576 pixels |
| cover extraction | `taglib_album_picture` `(track, dst, 0x100000, 0x600000)`: 2 JPEG, 1 PNG, 0 none | `COVER_PINS`; loaders `0x5de714` (JPEG), `0x5de1a8` (PNG), resize `0x5e00bc`, quality 90 |

The browse record `classinfo` (`0xa0c768`) keeps `classinfo[0]` = the class, `classinfo[1]` = a
playlist's id, `classinfo[8]` = 1 for an artist's All songs row, the artist or composer name at
`+0x20d` (0x100 bytes), the genre name at `+0x30d`, and the flag bytes `+0xb` (composer) / `+0xc`
(genre) = (row id == -1). A genre row's tap fills it for `allmusic_page` `0xff09` (`0x535c4c`);
`loadAlbumList(0xf005, row)` fills it for a composer (`0xff02`, branch `0x4ee9c0`).

The Memory Playback record `g_memory_info` (`0xa0caf8`, `0xd94` bytes) is saved by
`save_memoryplay_info` `0x4e3340`. The boot resume `memeory_startplayer` `0x4e34dc` re-runs the
saved class's query and matches name and path; no match resumes nothing. The payload only avoids
it: `so_play_own` queues as class `0xf001` ([artists](artists.md)).

## Deleting by class

`batch_delete_file(class, list, selection, 0, delete_file)` (`0x4e1408`) is what every stock
list's Delete runs, after one confirm dialog (handler `0x527f48`). It dispatches on class through
jump tables `0x74b7b0` (`0xf003..0xf00b`) and `0x74b7d4` (`0xff01..0xff14`); anything below
`0xf003` takes the generic loop. With `delete_file` set, each row also runs `remove_file`
`0x4e1264`.

| Class | Loop | Per row |
|---|---|---|
| `0xf001`, `0xf002`, `0xf009`, `0xff09`, `0xff10..0xff12`, `0xff14` | `0x4e1664` | `deleteMusicFromMusicDb` `0x4ede44` |
| `0xf00a` Favourites | `0x4e1710` | `0x4ede88` (`myfav`) |
| `0xf008` Most played | `0x4e17b4` | `0x4edf10` (`oftenplay`) |
| `0xf007` Recently played | `0x4e1858` | `0x4edecc` (`recentplay`) |
| `0xff13` a playlist's songs | `0x4e18fc` | `deleteMusicFromPlaylist` `0x4edf54` |
| `0xff04..0xff08`, `0xff0a..0xff0f` | none | nothing |

## Library scan and queries

| Name | Address | Use |
|---|---|---|
| `toolsLoadAllFile` | `0x5efd98` | recursive scan walk; callers `scanAllMusicFile` `0x4e9e5c`, `scanSpecFolder` `0x4e9f74` |
| folder lister | `0x5ea364` | readdir loop `0x5ea600`; the folder test at `0x5ea6a8` is hook 5 (delay slot `0x24a53ed4` loads `"."` at `0x743ed4`) |
| `toolsQueryDbTable` | `0x5ee77c` | `(db, sql, row cb, sort)`; `sqlite3_exec` at `0x5ee7fc`; db string `0x745a34`; song row callback `0x4e9058` pushes into `*tools_pdeq_directory` `0xa03964` |
| `toolsQueryDbTableAndSort` | `0x5ee9ac` | callers `sort_filename` `0x4ea18c`, `sort_format` `0x4ea218` |
| `getAllFav`, `checkFavExist`, `addMyFav`, `deleteMusicFromFav` | `0x4ec45c`, `0x4ee210`, `0x4ee234`, `0x4ede88` | `myfav`; star handler `manage_myfav` `0x4ef884` |
| `utf8_to_pinyin` | `0x73a5f0` | `(in, out)`: one pinyin initial per CJK character |
| SQL texts | `0x74ba4c`.. | `"songtable"`, `"myfav"`, the `select * from %s ...` formats to `0x74c510` |
| `toolsCheckItemExist` | `0x5ef578` | the scan's duplicate check |

## Status bar and battery

| Name | Address | Use |
|---|---|---|
| `show_sysbar_face` | `0x544b48` | the status bar refresh, 1 s timer `0x545394`; hook site `0x5450f8` |
| `get_battery_capacity` | `0x4e6dd8` | voltage buckets, or +10 per call while charging; callers `platform_init` `0x50bf00`, the poweroff timer `0x53ecd8` |
| `power_capacity` | `0xa059ec` | read by `show_sysbar_face`, `dropdown_showface` `0x475c5c`, the battery refresh helper `0x53f520`, the poweroff page |
| `widget_t` fields | `+8` w, `+0xc` h, `+0x44` parent | pinned in `widget_resize` / `widget_set_visible` |
| gauge | `/sys/class/power_supply/battery/capacity` | AXP2101, integer 0..100; stock never opens it |

## Library list hand-over

| Name | Address | Use |
|---|---|---|
| `loadLocalClassList(cls)` | `0x4ee504` (size `0x3d4`) | jump tables `0x74c5b8` (`0xf002..0xf00b`) and `0x74c5e0` (`0xff01..0xff24`) |
| the tail | `0x4ee638`..`0x4ee684` | `deque_assign` call at `0x4ee650` is hook 29 |
| destinations | `0xa045d8` (`pdeq_showlist`), `0xa045d0` (`pdeq_playlist`), `0xa05fb4` | `LCL_PINS`, `LCL_TABLES` |
| libcstl `deque_swap` | lib `0x3ac1c` | the layout proof (`CSTL_SWAP`); the allocator has no pool or state |

## Song dates

| Name | Address | Use |
|---|---|---|
| `toolsGetFileCreateTime(path)` | `0x5e4ac8` (size `0x9c`) | callers `0x5e7a8c`, `0x5e8494`, `0x5eae84` in the stock directory loader; stores `time_create` (`stSongInfo + 0x50`) |
| `st_atime` / `st_ctime` choice | `0x5e4b3c`..`0x5e4b5c` | exFAT / NTFS return the access time |
| `statx` | syscall 4366 | not imported by `demo`; `stx_btime.tv_sec` at 80 (`STATX_BTIME` `0x800`) |

## Podcasts

| Name | Address | Use |
|---|---|---|
| `seek_time(sec)` | `0x4e0544` | q2-pod's `player_seek_time` |
| `reset_poweroptions_timer(standby, auto_off, screen)` | `0x4d7874` | a non-zero argument restarts that countdown; the download page timer calls `(1, 1, 0)` |
| `mclSetSeek(sec)` | `0x5d26dc` | sends `{mcl-seek\%d}` (absolute s, CUE start included); no wait, no resume; -1 when hciplayer is not connected |
| `mclSetPlaySpeed(mode)` | `0x5d281c` | `{mcl-playspeed\%d}` string `0x756510` |
| `playspeed_mode` (data) | `0xa05acc` | 0..3 = 1x, 1.25x, 1.5x, 2x |
| `get_id3info` | `0x4dfd58` | fills `playsong_id3info` from `toolsGetMusicInfo` `0x5ec6a8`; tag-copy hook site `0x4dff4c` |
| `playsong_id3info` (data) | `0xa0d88c` | `0xa9c` bytes: path `+0`, CUE start `+0x400`, album `+0x404`, artist `+0x504`, composer `+0x604`, title `+0x684` |
| `song_name` / `song_artist` (data) | `0xa0513c` / `0xa0503c` | built by `get_id3info` after the site |

## Fonts and locale

| Name | Address | Use |
|---|---|---|
| `font_stb_create_ex` | `0x67ee74` | `font_t` is 0xd4 bytes; `stbtt_fontinfo` at `+0x38`, glyph cache `+0xb4` |
| `glyph_cache_lookup` / `glyph_cache_add` | `0x6a4204` / `0x6a40bc` | `TEXTGAMMA_PINS`; `font_stb_get_glyph` calls the lookup first |
| `stbtt_FindGlyphIndex` | `0x67c3b4` | reads data and `index_map` on every lookup |
| `font_manager()` / `font_manager_get_font` | `0x650ad0` / `0x650dc4` | global `0xa0be30`; one stb object serves every size |
| `font_manager_shrink_cache` / `font_manager_unload_all` | `0x6510b8` / `0x650f74` | a language or theme change recreates the font |
| `image_manager_lookup` / `image_manager_get_bitmap` | `0x655850` / `0x655ccc` | lookup is cache only; a hit sets the entry's last access to now |
| `image_manager_unload_unused` / `image_manager_unload_all` | `0x655f58` / `0x655fdc` | age eviction (`LIGHT_PINS`, callback `0x6553e0`) / clear |
| `locale_info()` / `locale_info_on` | `0x6588b0` / `0x658ba8` | `EVT_LOCALE_CHANGED` `0x122` |
| `font_manager_get_font` retry | `0x650ebc` | an unloadable font name is retried once with the default |
| label paint row pitch | `0x62e9f8` / `0x62ea04` / `0x62ea24` | `"spacer"` (default 2) + font size |
| `EVT_THEME_CHANGED` | `0x14a` | dispatched by `widget_set_theme` `0x66d444` |

## Pinyin engine

AOSP's PinyinIME (`ime_pinyin::*`, `0x5bf9b0`..`0x5ceb40`) over one global `MatrixSearch*` at
`0xa0a360`, NULL until `im_open_decoder`. The C entry points are `.dynsym` names with PIC
prologues pinned in `PINYIN_PINS`.

| Name | Address |
|---|---|
| `im_open_decoder` / `im_close_decoder` | `0x5c7350` / `0x5c7534` |
| `im_search` / `im_delsearch` / `im_reset_search` | `0x5c760c` / `0x5c7678` / `0x5c76e8` |
| `im_get_candidate` / `im_get_sps_str` | `0x5c7754` / `0x5c7720` |
| `im_get_spl_start_pos` / `im_choose` / `im_cancel_last_choice` / `im_get_fixed_len` | `0x5c778c` / `0x5c77c0` / `0x5c77f4` / `0x5c7824` |
| `MatrixSearch::get_predicts` | `0x5c6834` |
| `DictList::get_splids_for_hanzi` / `get_lemma_id`, `SpellingTrie::get_spelling_str` | `0x5bffd4` / `0x5c01a4`, `0x5c922c` |
| `inputmethod_module` object | `0xa0c2bc` |
| `keyboard_init` | `0x5b25d4` |

- `im_search` clamps the length to 39; stock's wrapper sets the max lengths 9 / 12.
  `im_get_candidate` returns UTF-16 in `buf` (or NULL). `im_get_spl_start_pos` returns the syllable
  count and sets `*out` to the start offsets (one more than the count).
- `get_splids_for_hanzi` crashes for a character not in the dictionary: test
  `get_lemma_id(&ch, 1) != 0` first.
- Stock's init opens `/usr/dict_pinyin.dat`, which is absent from the rootfs; the dictionary asset
  is `/release/assets/default/raw/data/gpinyin.dat`.

## Settings

| Name | Address | Use |
|---|---|---|
| stock pages the rows open | `0x748f1c` `systemset/wifi_page`, `0x748f00` `bluetooth_page`, `0x748ab4` `display_page`, `0x748a34` `language_page`, `0x7474d4` `equalizer_page` | plain `navigator_to`; hub row thunks `0x4b1440` (hook 21) / `0x4b1408` (hook 32), the Settings list's row handler (shared call `0x4ad830`) |
| About values | model `0x747718`, firmware `0x74773c`, `product_sncode` `0xa0553c`, `wifi_mac` `0xa061a8`, card floats `0xa03e74` / `0xa03e70`, `getDiskMemoryInfo` `0x5b30e0`, `networkGetConnectStatus` `0x5d7cac`, `networkGetIPAddr` `0x5d753c` | stock About walk `0x4a1240..0x4a170c` |
| `get_equalizer_preset_name` | `0x49daec` | preset key table `0x97c7a0` |
| EQ switch handler | `0x49d750` | flips `equalizer_flag`, saves `[PLAYSET] EQFLAG` |
| `wififlag` / `bluetoothflag` / `language` | `0x97caf8` / `0xa05ac0` / `0xa05ab8` | `wifi_switch` `0x507a8c` toggles Wi-Fi and saves `[SYSSET] WIFI` |
| play mode | `mclSetPlayMode` `0x5d278c` (mode word `0xa0abe0`), `mclSetPlayPos` `0x5d42d8`, position `0xa0abdc`, gapless state `0xa0abd0` | `SHUFFLE_PINS`; raw mode readers `0x5d58fc`, `0x5d5748`, `0x5d0edc` |
| play mode keys | `0x47a454`, `0x47a4d4`, `0x47a4e8`, `0x47a500` | the More dialog's `playmode_*` labels |
| lock screen | `screensaver_mode` `0xa05aa3`, `screensaver_timeshow` `0xa05aa2`, `screensaver_picture` `0xa0473c`, `pdeq_screensaverlist` `0xa045cc` | `LOCKSCREEN_PINS`; wallpaper helpers `get_screensaver_image` `0x4d7524`, `toolsGetScreenSaverPic` `0x5e4b64` |
| pull-down state | `syssetinto_flag` / `playsetinto_flag` `0xa05a48` / `0xa05a4c`; `lockscreen_pageflag` `0xa059fc`; `dropdown_menu_state` `0xa05a2c`; `pressdown_y` `0xa05a30`; `usblink_status` `0xa059f4`, USB page pending byte `0xa041b1` | `TSDOWN_PINS`, `USBPOLL_PINS`, `USBTAKE_PINS`; `on_wm_tsmove_fun` `0x4cd788`, slide timer callback `0x47535c`, close handler `0x4750ec`; `check_usb_status` `0x4ce1e8`, `usbmode_exit` state 3 `0x545808` |

## Theme setting

`tools/themeoff.py` `EDITS`; [theme](theme.md) "theme1 is off".

| Name | Address | Use |
|---|---|---|
| theme flag | `0xa05a98` | read by `awtk_configinit` `0x4ccb88`; `[SYSSET] THEME` `0x748b8c` |
| `config_init` clamp | `0x4e63d8` / `0x4e63dc` | `sltiu v1, v0, 2` becomes `, 1` |
| System page row table / count | `0x97c8c0` / `0x4adb1c` | read by `systemset_sysset_page_init` `0x4adb0c` and the click handler `0x4ad7f0` |

## Wi-Fi and Bluetooth together

`tools/coex.py` `EDITS`, `PINS`; [overlays](overlays.md).

| Name | Address | Use |
|---|---|---|
| `msg_bt_open` / `msg_wifi_open` | `0x7445a8` / `0x7445dc` | the confirm dialogs at `0x474d6c`, `0x4a3b38` / `0x474fb0`, `0x4b0b74` |
| patched words | `0x474d98`, `0x4a3b64` (`beqz v0` -> `b`); `0x474fd8`, `0x4b0b9c` (`lw` -> `b`) | skip the other radio's switch-off after the dialog returned 10 |
| `wifi_switch` / `switchBluetooth` | `0x507a8c` / `0x4d516c` | the skipped calls; stock handlers: Control Center tile `0x474ec8`, Wi-Fi row `0x4b0a88` |

## Automatic time

[datetime](datetime.md); `tools/autotime.py` `EDITS`.

| Name | Address | Use |
|---|---|---|
| `AUTOSYNCTIME` key / byte / need-sync byte | `0x747a2c` / `0xa05ab1` / `0xa05a66` | `config_init` `0x4e6558`; `network_checkstatus` `0x5068e0` |
| `networktime_adjust_thd` | `0x4d92bc` | 1 s loop; stock ntp servers at `0x74ab24`.. |
| `toolsGetNetworkTime` | `0x5e32d4` | `ntpdate` command slot `0x756f38` |
| `toolsGetRtcTime` / `toolsSetRtcTime` | `0x5e34d8` / `0x5e34f4` | `hwclock -s` slot `0x756f7c` and `hwclock -w` slot `0x756fa4`, both patched to `-su` / `-wu` |
| `select_timezone` / `toolsSetTimeZone` | `0x4d6b2c` / `0x5e3288` | `setenv("TZ")` |

## Time zones

[datetime](datetime.md); `tools/timezones.py` `PINS`.

| Name | Address | Use |
|---|---|---|
| `time_zone` | `0xa05ab4` | saved zone index |
| picker | page builder `0x4a2424`, row builder `0x4a21c8`, click `0x4a25b8` | |
| patched sites | clamp `0x4e65dc`, row count `0x4a246c`, click limit `0x4a2604`, row call `0x4a25a8`, label `0x4a2248` / `0x4a224c` | |
| label key array | `0x97c810` | 27 pointers; strings from `0x747834` |
