# The code payload: segment, trampolines, hooks, the entry

**Sources:** `tools/pod.py` (`SOURCES`, `FUNCTIONS`, `DATA`, `LIBC`, the hook pins), `tools/pod_pins.py`, `patch/link.ld`, `patch/m1plus.c`.
M1+ Music adds pages through a MIPS payload appended to `/release/bin/demo`. The M1 Plus uses an
X2000, Linux 5.10, Buildroot glibc and AWTK; `demo` has a spare `PT_NULL` program header. All stock
addresses and patch words are specific to the pinned V2.1 binary; the pinned words themselves
live in `tools/pod.py` / `tools/pod_pins.py` and the stock addresses in [addresses](addresses.md).

## The segment

`pod.py append_payload` pads `demo` to 64 KiB, appends `patch.bin` and rewrites the unused
`PT_NULL` (`PH[10]`) into a file-backed RWX `PT_LOAD` at va `0xb00000`. The mapping is checked not
to overlap any segment, and the ELF still parses.

- No `.bss`: writable state is a zero-filled `PROGBITS` `.scratch` section, so `memsz == filesz`;
  `pod.py` rejects a non-empty `.bss` / `.sbss`.
- Anything large (Cover Flow's frame and textures, job arrays, album copies) is heap, allocated
  when the page opens and freed on close.
- Compilation is non-PIC MIPS32r2 (`-Oz`, `-Wall -Wextra -Werror`), linked by `patch/link.ld` at
  `0xb00000` with `--gc-sections`. `SOURCES` in `tools/pod.py` is the source order.

## $gp and the trampolines

Every stock PIC function starts with three words that set `$gp = 0xa03ed0`. The payload needs no
`$gp` of its own and reaches stock code and data by absolute address. A hook overwrites the three
prologue words with `j hook; nop`; its trampoline restores `$gp` and resumes the stock function
past them (`lui $gp; ori $gp; j <fn+12>; nop`). A call-site hook replaces one `jalr` with `jal`.

## Calling stock code and libc

- **Stock functions** are absolute-address macros in the generated `stock.h`; the callee sets up
  its own `$gp`. `FUNCTIONS` in `tools/pod.py` lists every one and checks each against `.dynsym`
  before writing; `DATA` pins the exported data.
- **libc only through slots `demo` already imports.** A stub tail-calls the resolved pointer
  (`LIBC` in `tools/pod.py`). No import is ever added. Each feature's code shows the slots it uses.
- **Never `widget_get_text_utf8`.** It ignores its size for a wide text, so any text longer than
  the buffer overruns it. It is not in `FUNCTIONS`, so a call does not compile. Read text with
  `m1_text_utf8(widget, buf, size)` (`patch/common.c`): cut at a character, always NUL
  terminated, returning the length the whole text needs.
- **Stock list queries are page state.** `loadLocalClassList` / `loadAlbumList` replace
  `*pdeq_showlist` (and may set `nagvation_title` and `classinfo`), which every stock list page
  draws and plays from, and which their to-foreground does not re-read while the class is
  unchanged. Run them only from the page in front (its open, its tap, its own to-foreground),
  never from a timer or tick that runs while another page is in front. A page goes quiet on
  `EVT_WINDOW_TO_BG`.
- **Worker threads** (feeds, downloads, updates, cover jobs) touch no widget and call no stock
  function. Stock calls such as `reset_poweroptions_timer` come from page-scoped timers on the UI
  thread ([podcasts](podcasts.md), [update](update.md), [network](network.md)).

## Hook sites

One table owns the inventory. "Boot" marks a hook that stock reaches at boot (`tools/reach.py`);
those do only bounded work (no thread, timer, loop over files or network) and run stock's code
on the kill switch or any failure. Every hook is pinned (`pod.py` asserts the three prologue words and the resulting `$gp`, checks
that no row edit touches a hook site, and pins the input `demo` by SHA-256), and every fallback is
stock's own behaviour.

| # | Site | Owner | Fallback |
|---|---|---|---|
| 1 | Home icon click dispatcher `0x533b80` | [menu](menu.md), this page | stock click; opens the menu for icon id 99, and for id 1 (Tidal) while `/mnt/data/m1plus-bad` exists |
| 2 | `home_page_init` `0x534cd4` (boot guard) | [home-guard](home-guard.md) | stock init (boot) |
| 3 | `playing_page_init` `0x53d1e4` | [nowplaying](nowplaying.md), [queue](queue.md) | stock page; stock runs first |
| 4 | `get_id3info` tag copy, call site `0x4dff4c` | [podcasts](podcasts.md), [scrobble](scrobble.md) | stock copy (boot); podcast path only under `/mnt/mmc/Podcasts/` |
| 5 | library scan folder test, call site `0x5ea6a8`: a directory whose name starts with `.` is neither listed nor walked (so `/mnt/mmc/.m1plus/` audio stays out of Songs); files unaffected | `patch/common.c` `m1_scan_dir` | stock `strcmp`; one first-byte compare, no I/O |
| 6 | `toolsQueryDbTable` `0x5ee77c` and `toolsQueryDbTableAndSort` `0x5ee9ac` | [songs](songs.md), [albums](albums.md), [podcasts](podcasts.md) | stock SQL (boot); rewrite over 1 KB goes to stock |
| 7 | `dialog_playmore_dialog_init` `0x479cc4` | [playmore](playmore.md) | stock rows; stock runs first |
| 8 | status bar battery call, call site `0x5450f8` | [battery](battery.md), [charging](charging.md), [scrobble](scrobble.md#automatic-upload) | stock value; a cached flag when off |
| 9 | `select_timezone` `0x4d6b2c` | [datetime](datetime.md) | stock function (boot) |
| 10 | `style_get_color` `0x659fcc` | [accent](accent.md) | stock answer; pass-through while the palette is inactive |
| 11 | `style_get_gradient` `0x659f9c` (leaf, no trampoline) | [accent](accent.md) | the same function in the payload |
| 12 | `image_manager_add` `0x655638` | [accent](accent.md) | stock; pass-through while the palette is inactive |
| 13 | `mclSetPlayMode` `0x5d278c` | [shuffle](shuffle.md) | stock function (boot) |
| 14 | `mclLoadPlayList` `0x5d1f28` | [shuffle](shuffle.md) | queue as loaded (boot) |
| 15 | `dialog_dropdown_dialog_init` `0x475f04` | [pulldown](pulldown.md) | stock tiles; stock runs first |
| 16 | `mclStartPlayer` `0x5d5300` | [radio](radio.md) | one comparison, then stock (boot) |
| 17 | `on_backtoplayer_onclick` `0x4cd58c` | [radio](radio.md) | stock handler |
| 18 | `save_stop_player` `0x4e2304` / `save_start_player` `0x4e23e8` | [radio](radio.md) | one comparison, then stock |
| 19 | `toolsGetFileCreateTime` `0x5e4ac8` | [songs](songs.md) | stock date (boot) |
| 20 | Line Out text, call sites `0x544f90` / `0x475ad8` | [lineout](lineout.md) | stock text |
| 21 | Wi-Fi row of the All System Settings hub, call site `0x4b1460` | [wifi](wifi.md) | stock `navigator_to` |
| 22 | pull-down Playback / System tiles, call sites `0x4cd894` / `0x4cd8bc`; the pull-down open, `0x4cd864` | [pulldown](pulldown.md) | stock `navigator_to` |
| 23 | `bigcover_page_init` `0x529a24` | [bigcover](bigcover.md) | stock page |
| 24 | timed open in Now Playing's timer, call site `0x53d0ec` | [bigcover](bigcover.md) | stock `navigator_to` |
| 25 | `screensaver_page_init` `0x53fd44` | [lockscreen](lockscreen.md) | stock lock screen |
| 26 | `mclNextSong` List-play end branch `0x5d5988` (mid-function) | [nextalbum](nextalbum.md) | stock's end |
| 27 | Tidal search page focus call, call site `0x4c2088` | [tidalkb](tidalkb.md) | stock `edit_set_focus` |
| 28 | `on_wm_idle_status` play-history call, call site `0x4ce930` | [subsonic](subsonic.md) | stock `add_playrecord` |
| 29 | `loadLocalClassList` `0x4ee504` and its tail `deque_assign` call `0x4ee650` | [libload](libload.md) | stock copy (boot) |
| 30 | `on_wm_tsdown_fun` `0x4cd6e8` (every touch down) | [pulldown](pulldown.md) | a few loads (`lockscreen_pageflag`, `dropdown_menu_state`, the USB state), then stock; clears a stale nonzero word or asks again for a lost USB page, nothing else |
| 31 | `on_wm_idle_status` play-status call, call site `0x4ce968` | [display](display.md) | stock `mclGetPlayStatus` |
| 32 | Bluetooth row of the All System Settings hub, call site `0x4b1428` | [bluetooth](bluetooth.md) | stock `navigator_to` |
| 33 | status bar tap's open of the volume dialog, call site `0x4cd964` (`on_wm_tsup_fun`) | [volume](volume.md) | stock `navigator_to_with_context` |
| 34 | scan dialog timer's finish refresh, call site `0x47baec` (`bal 0x47b604`; `lu_scan_finish` records a completed scan) and the commit calls `0x4e9e70`, `0x4e9f9c` (`lu_commit` flags it) and the insert path's batch COMMIT `0x5ee090` (`lu_batch_exec` flags a failure) | [libupdate](libupdate.md) | stock refresh and commit, no record |
| 35 | event1 input thread's key table load, `0x637bc8` (two words, asm stub `pod_keys_site`) | [keyspower](keyspower.md) | stock's key (boot); previous / next swapped only while Swap Prev / Next is on (one byte read, the file read once) |
| 36 | `on_wm_idle_status` end-of-track call, call site `0x4ce834` | [radio](radio.md) | stock `mclAutoChange` |
| 37 | home timer's checks of hciplayer's failure markers, call sites `0x4cf5b0` (`/tmp/notfile`), `0x4cf8d0` (`/tmp/notsupport`) (`on_wm_timer_dialogresponse`) | [radio](radio.md) | stock `access` |
| 38 | `on_wm_idle_status` USB poll call, call site `0x4cef08` | [pulldown](pulldown.md) | stock `check_usb_status` |
| 39 | `on_wm_timer_dialogresponse` read of the USB page request, `0x4cf254` (two words, asm stub `pod_usb_site`) | [pulldown](pulldown.md) | stock's read; drops the request when the cable is gone |
| 40 | SyncLink shown, call sites `0x545068` / `0x475bb0` | [lineout](lineout.md) | stock `widget_set_visible`; hides SyncLink only when stock's marks would reach the clock |
| 41 | `check_cpumem` `0x50b810` | `patch/power.c` | stock `check_cpumem` (boot); skips the 6 s `drop_caches=3` thread unless `/mnt/mmc/m1plus-off` exists (checked at boot and once after 15 s for async SD mount) |

Sites without a number:

| Site | Owner | Fallback |
|---|---|---|
| Display page Lock Screen row `0x4a5ca8` (two words, asm stub `pod_lock_site`) | [lockscreen](lockscreen.md) | stock page |
| `screen_action` backlight calls `0x4e71cc` (on) and `0x4e71fc` (off) (`bp_light_on`, `bp_light_off`) | [battery](battery.md) | stock `toolSetBackLight` |
| All Playback Settings Equalizer row `0x4a0210` (two words, asm stub `pod_eq_site`) | [peq](peq.md) | stock page |
| `mclGetPlayMode` display sites (19 call-site words) | [shuffle](shuffle.md) | stock mode |
| `scroll_view` `on_event_before_children` slot, data word `0x97a330` (empty in stock; runs for touches inside a `scroll_view` only, including the Albums page) | [albums](albums.md) | empty slot |
| hciplayer (second binary, own payload at `0xe10000` through its spare `PT_NULL`, `tools/mod_player.py`): equalizer `af_info` open slot `0x89381c`, two 48 kHz gates, `mcl-seteq` flag parse; a data word and branch words, no prologue hook | [peq](peq.md), [stereo](stereo.md) | filter passes audio through (also with `/mnt/mmc/m1plus-off`) |

Rules for the table:

- Library rows use call-site and immediate edits, not extra prologue hooks.
- Page-owned paint events and timers follow their feature's lifetime; there is no added global
  paint or main-loop hook beyond the table. Hooks 10 - 12 are the one accepted relaxation of the
  no-paint-hook rule.
- Hooks 26 and 28 sit on the main loop's idle path but run only at an album end or a track start
  (bounded work, stock's call on any refusal). Hook 31 runs on every idle pass and does one
  compare of a cached int when LED Light is not Dynamic; hook 36 runs on every idle pass and does
  two compares of the radio's state before stock, plus at most two file checks (the kill switch)
  while the radio owns the player; hook 38 runs on every idle pass and does one load before stock,
  plus a window stack walk only while a USB state 2 outlives its cable; hook 39 does one load per
  timer pass (two while a USB page is requested); hook 37 runs on every home timer pass and does stock's `access`,
  then the same checks only when a marker exists.
- Kill switch `/mnt/mmc/m1plus-off`: scope in [safety](safety.md#kill-switch). Hooks 5, 6, 22 and 33
  never read it (bounded work or tap-only, stock fallback); 13 and 14 use stock's own switch; 16, 36
  and 37 read both switch files (`home_off`) only while the radio owns the player; 30, 38 and 39 read
  them once (cached) at the first stale word or USB state.
- `tools/reach.py` decides boot reachability; hooks not marked "boot" are reached only through the navigator's page-init dispatcher, a tap or the status bar, never from `main` / `platform_init`.
- Credit: hooks 4, 5, 6, 9 - 12, 16 and 19 follow q2-pod's equivalents; hook 31's lamp pins came
  from PR #5.

## Hook 4 and hook 6 detail

**Hook 4** (`pc_id3_path`, after q2-pod's `ID3_PATH`): stock's `strcpy(info, path)` runs, then for a
path under `/mnt/mmc/Podcasts/` (and no kill switch) the episode, show and album are written into
the struct and stock builds `song_name` / `song_artist` from them. Any other path calls
`scrobble_started` ([scrobble](scrobble.md)). Boot-safe: no file I/O except the kill-switch check
for a podcast path, no allocation.

**Hook 6** (`pc_library_query` / `pc_sorted_query`, after q2-pod's `dbquery` / `sorted_query`):
arguments `(db, sql, callback, sort)` pass through. For a statement starting `select ` and
containing ` from songtable` it adds the filter
`ifnull(fileurl,'') not like '/mnt/mmc/podcasts/%' and ifnull(fileurl,'') not like '/mnt/mmc/audiobooks/%'`
(SQLite LIKE is ASCII case-insensitive: `/mnt/mmc/pOdCaStS/x.mp3` goes, `/mnt/mmc/Podcasts Extra/`
stays), applied before stock's grouping, so an album shared by music and an episode keeps the music
row and artwork and untagged episodes add no Unknown rows.

- **An album is its first track:** lowest `track` (NULL or <= 0 after the tagged), then lowest
  `fileurl`. An album list (`select <columns> from songtable[ where <c>] group by album COLLATE
  NOCASE`, no `(` in the columns: getAllAlbum, getAlbumBy{Artist,AlbumArtist,Composer,Genre},
  SearchAlbumByName) becomes `... where [(<c>) and ]<filter> group by album COLLATE NOCASE having
  min(printf('%d%08x%d%s', ifnull(track,0)<=0, ifnull(track,0)+2147483648, fileurl is not null,
  fileurl)) is not null`. The `min()` gives the bare columns the minimum-key row and, in HAVING,
  leaves stock's column list (callbacks check its count) untouched; printf is never NULL.
- **An album's tracks** (`select * from songtable where album...`, not `albumsonger`) become
  `... where (<c>) and <filter> order by (ifnull(track,0)<=0), ifnull(track,0), fileurl`, so `deque_at(list, 0)`
  is the first. Any other statement keeps stock's text with the table replaced by
  `(select * from songtable where <filter>)`.
- Cover cache files carry a leading `f` (`covers/r<key>-168.jpg`) so covers made from an older
  query's first track are never read.
- `getAllFav`'s exact text `select * from myfav` excludes the Podcasts and Audiobooks paths; with
  `pc_saved_scope` set (around one `loadLocalClassList(0xf00a)` of the Saved page) it lists only them,
  last saved first (`QUERY_PINS`).
- Any other text, a missing SQL pointer or a rewrite over 1 KB (stack buffer) goes to stock
  untouched. The filter is not scoped to a page.
- Tests: `test/pod/scan.py` (SQLite).

## Features without a hook

Library Search, the Wi-Fi page's controls, the keyboard's Chinese layer and the workers have no
hook of their own; their feature docs describe them.

## What the entry does (`patch/m1plus.c`)

`m1plus_home_click(icon, e)` reads the icon's name (stock stores the Home id as a decimal string)
and `atoi`s it. It tails into stock's click (through the trampoline) if the id is not the entry id
(`POD_ENTRY_ID` = 99, the icon `patch/home.c` adds), if the kill-switch file exists, or if the
page fails to open. Otherwise it opens the entry page with `window_open`, binds `btn_return` to
`navigator_back`, `btn_backtoplayer` to `on_backtoplayer_onclick` and each `pod_rowN` to its
action, and returns 0.

`tools/pod_pages.py` defines `PAGES`, `ITEMS` and the actions once. A page's number is its place in
`PAGE_ORDER`, the one table of page keys, in the order of the C `POD_PAGES`; a key with no page, a
page missing from the table or a key used twice stops the import. `pod_ui.py` builds the assets
and `pod.py` emits the C tables into `stock.h`. Tests name pages
(`P.PAGES[P.X_PAGE_INDEX] is P.X_PAGE`), never numbers. See [menu](menu.md) and
[settings](settings.md) for persisted state and navigation.

To add a page:

1. Define it with `Page('m1plus_<key>', ...)` in `pod_pages.py` and list its key in `PAGE_ORDER`
   (append at the end unless there is a reason not to).
2. Implement its action, rebuild the assets and tables, and add a `test/pod/` module.
3. A `POD_<NAME>_PAGE` macro for C is one more name in the loop in `tools/pod.py gen_stock_h`.
4. Keep widget names and the stock fallback intact.

## Why the entry is an added icon

The entry is an icon of its own, id 99 ("M1+ Music"), which `patch/home.c` adds to the stock grid;
Tidal opens Tidal. The icon has no stock id, so Home customisation cannot hide it (the grid
rebuild drops it; `hm_fg` puts it back), and the dispatcher's bounds check sends an id outside
0..17 to its default (nothing), so a tap that reaches stock with the kill switch on is harmless.
The HiFi store (id 0) was never usable: `demo` only shows it when the `language` global is 0, and
patching that needs branch patches on the boot path.
