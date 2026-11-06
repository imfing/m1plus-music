# Settings and launcher

Sources: `patch/m1plus.c`, `patch/home.c`, `patch/covercache.c`, `patch/tape.c`, `tools/pod_settings.py`, `tools/pod_ui.py` and
`tools/pod_pages.py`. User instructions are in the [guide](../guide.md#settings).

Settings is item 18 (`j`), hidden from the main menu by default. The Extras navbar always provides access, and it cannot be turned off. It is iOS-style grouped cards (below): **Wi-Fi**, **Bluetooth**; **Home Screen**, **Library**, **Now Playing**; under **Playback** Play Mode, EQ and **All Playback Settings** (stock playset page, Home dispatcher id 16; Gapless is on it); under **System** Display, **Appearance** (a page of its own, `m1plus_appearance`: the Background and Accent value rows opening their pickers, then a card with **Control Center**, the pull-down's tiles, [pulldown](pulldown.md)), Keyboards, **About** (our own page) and **All System Settings** (stock sysset page, id 17; its Theme row is removed, [theme](theme.md)); then **Developer** (Startup: Boot to M1+ Music, Open Shanling Home; Tools: Screenshot, Cover Cache, System Update (the stock firmware update page)). Keyboards sits under System: the design had no place for it, and dropping the pinyin switch would have lost a feature.

## Cards

The design is `tools/preview_settings.py` (it draws the built tree's own assets; `out/preview/settings-mock-3.png`). The numbers are `tools/pod_settings.py` (shared by `tools/pod_ui.py build_cards_page`, the preview and `test/pod/settings.py`); a page is a `Page(layout=[Row, Hdr, Note, GAP ...])` in `tools/pod_pages.py` and its kind is `cards`.

- The list is the stock `list_view` > `scroll_view` (310 wide) + `scroll_bar_m`, the rows stock `list_item`s (`list_item_style`, the stock 21 px `hscroll_label`).
- **The layouter stacks the children.** The stock `list_view` layouter (`children_layouter_list_view`, `0x60b12c..`; see [recent](recent.md) "The shelf after the rows") ignores a child's `y`: it puts every **visible** child of the scroll_view at the running y in **child order**, sets x (0) and the width, and sums the heights into `virtual_h`. V2.1zWZKWAAAB had the cards as views of their own placed by `y`, so the layouter stacked them as a block above the rows. So the page is now only a column of full-width items in display order, nothing relying on the asset's y/x/w: a 10 px spacer (`pod_top`), the rows, headers (`pod_sec<n>`, 40), notes (`pod_note<n>`, 34), gaps (`pod_gap<n>`, 20), all insensitive views except the rows, and a 10 px spacer (`pod_end`). The asset's y is the stacked y anyway.
- **A card is drawn by its rows.** Each row's background (`bg_image`, draw type `default`, `bg_color` transparent) is a picture piece, `pod_cd_single`, `_top`, `_mid` or `_bot` (320 x 52, `mod_icons.card_piece`): the card (x 10 .. 310, `#1C1C1C`, radius 12 only on the corners the piece has) is baked in and the rest is transparent; `pod_cd_<piece>_down` is the same shape in the pressed grey `#2C2C2E` (the highlight is clipped to the card's shape, corners included). The pieces are 320 wide because the layouter gives a child the list's width. A row of a hidden neighbour stays right because a row's piece depends only on the rows around it in the layout, and the one that hides (Regenerate Daily Mix) is a card of its own, a single piece. The row's children are row relative (the glyph image at x 22, the label at 58 or 24, a hairline `#333333` from the label to x 310, on every row but a card's last, the chevron / value / switch / check with their ink 14 px from x 310). Headers and notes are views whose grey label starts at x 24, the left of the row glyphs' ink.
- The right side by ink: **link** = the chevron `pod_chev` (the shared list chevron, 10 x 16, `#8A8A8A`, `mod_icons.pod_chevron`) at x 288, 12 px inside the card edge, centred above the card's hairline, the label's box ending 8 px before it (x 280, so its text ends at 278 after the label's 2 px inset); **value** = grey `#AAAAAA` 18 px text 8 px left of the chevron (`pod_value<i>`; the payload sizes it to its text and gives the row's label the rest: `value_fit`); **switch** = the stock `sset_on` / `sset_off` image; **picker row** = no glyph and a check (`pod_check<i>`, shown on the chosen row); **action** = nothing (Update Library, Regenerate Daily Mix, Rebuild Covers, Open Shanling Home, Screenshot). `pod_pages.row_kind` says which.
- Headers are `#AAAAAA` 18 px and notes 15 px. The Now Playing button is the round `ah_nav_np`. The navbar fade (`img_nb_fade`) stays hidden: the first card is 10 px under the bar and the fade would dim it at rest.
- Hidden is `visible=false` and `sensitive=false` (the layouter then skips the item); headers, notes, spacers, glyphs and accessories are never sensitive. `test/pod/settings.py` runs demo's own layouter (`window_manager_check_and_layout`) on every cards page as built, starting each child at a wrong x and y, and asserts every child's final x, y and height, `virtual_h`, and that with Daily Mix off the Regenerate row and its note are skipped and nothing else moves; it also hit-tests every visible row, header, note and gap.

## Persisted choices

Switches and pickers save before updating their image/check. A failed atomic save leaves the file and displayed state unchanged. Reading settings never writes them. One reader serves every one-character file below: `set_read(path, default)` (patch/home.c, declared in home.h) returns the character of a file that is exactly `x` or `x\n`, and the default for a missing file, an empty one or anything longer (trailing junk is the default, never a first-byte match). Each setting compares that character; the values below are those characters. The multi-value files (`home-menu`, `pulldown-tiles`, `search-history`) and the boot guard's `m1plus-start` have their own parsers.

Feature settings live in their own folder, `/mnt/data/m1plus/` (`SET_DIR`, patch/home.h). `home_write_atomic` makes the folder when a write finds it missing and fsyncs the folder after the rename. The boot guard's files stay directly in `/mnt/data/`: `m1plus-start` (Boot to M1+ Music: `0` stock Home; missing/other enables M1+ Music), the marker `m1plus-run`, the bad note `m1plus-bad` and the kill switch `m1plus-off` ([home guard](home-guard.md)). The guard's crash path therefore never depends on the folder.

| Setting | File under `/mnt/data/m1plus/` | Values/default |
|---|---|---|
| Recent Albums | `home-recent-albums` | `0` off; missing/other on |
| Daily Mix | `home-daily-mix` | `0` off; missing/other on |
| Albums / Playlists view | `albums-view`, `playlists-view` | `0` list; missing/other grid |
| Recently Added view | `recently-added-view` | `1` albums grid; missing/other songs ([recent-albums](recent-albums.md)) |
| Cover Flow Landscape | `coverflow-landscape` | `1` landscape; missing/other portrait |
| Album Order | `album-order` | `0` Album; missing/other Artist |
| Cassette Theme | `cassette-theme` | `1` Chrome, `2` Metal; missing/other Normal |
| Vinyl Record | `vinyl-record` | `1` Cover; missing/other Black |
| Vinyl Base | `vinyl-base` | `1` Snow; missing/other Graphite |
| Pod Appearance | `pod-appearance` | `1` Dark; missing/other Light |
| Chinese (Pinyin) keyboard | `keyboard-pinyin` | `1` on; missing/other off |
| Podcast Search | `podcast-online-search` | `1` on; missing/other off (the default) |
| Background | `appearance-background` | `0` Black (default), `1` Tinted; `2` Light and `3` Light Auto are not offered; missing/other Black; Settings > System > Appearance > Background ([accent](accent.md)) |
| Accent | `appearance-accent` | one digit, the index 0 Neutral (default) .. 6 Champagne; missing/other Neutral; Settings > System > Appearance > Accent ([accent](accent.md)) |
| Battery Percentage | `battery-percentage` | `1` on; missing/other off (the default) |
| Shuffle (the payload's flag; stock's mode is never 2) | `playback-shuffle` | `1` on; missing/other off ([shuffle](shuffle.md)) |
| Main Menu / Extras | `home-menu` | item ids in order, optional `-` then the hidden ids ([menu](menu.md)); invalid = defaults |
| Control Center | `pulldown-tiles` | tile ids `0`-`7` in order, optional `-` then the hidden ids ([pulldown](pulldown.md)); invalid = all eight in stock order |
| Recent searches | `search-history` | up to 5 UTF-8 lines, newest first ([search](search.md)); malformed = none |
| Radio station lists view | `radio-view` | `1` grid; missing/other list ([radio](radio.md)); not shown in Settings Files |
| Recent radio stations | `radio-recent` | an `.m3u` of up to 10 stations, newest first ([radio](radio.md)); shown present/missing in Settings Files |

**Home Screen** (also the menu's arrangement: Main Menu and Extras, two link rows with notes) has the Recent Albums and Daily Mix switches (one card, the note "Shown on Home below the menu"). Last on the page, after Battery Percentage and its note (below), is Regenerate Daily Mix in a card of its own with its note: an action that requests a new seed (a toast "New mix when Home opens" confirms an accepted tap), the Home page rebuilds when next foregrounded. That row and its note are hidden (`regen_show`: the last row, `pod_note4`; the layouter skips them and the page ends after Battery Percentage) while no mix can be made (Daily Mix off, or a library under `MIX_MIN_LIB`). Shelf and mix visibility are reread when returning to Home. The separate Recent Albums translation fits switch rows where Recently Played would overflow. Under a **Status Bar** header, **Battery Percentage** (a switch row, Lucide `battery-charging`, `ACT_BATTPCT` 36, `battpct_setting` / `battpct_toggle` in `patch/battery.c`, saved atomically in `m1plus-battpct`, **off by default**; a failed save changes neither the file nor the switch) with the note "The exact charge beside the battery icon". The status bar reads it through the payload's cached flag, which the switch updates at once; what it does is [battery](battery.md) "The percentage". Texts in the 13 languages (`Status Bar`, `Battery Percentage`, the note; no `%` in a text, `mod_strings` refuses one). Tests: `test/pod/battery.py`.

**Library**: Update Library (the stock updatemusic page, Home id 2, as the Update Library item), **Album Order** (a value row, Artist or Album; opens the picker `m1plus_albumorder`: two check rows, `ACT_SORTSET`, `cc_sort_set`), **Rebuild Covers** (between them, one card: Update Library, Rebuild Covers, Album Order; the Update Library note was dropped) and under the Cover Flow header Landscape. **Now Playing**: under the Cassette Mode header **Theme** (value Normal / Chrome / Metal, opens the picker `m1plus_tapetheme`: three check rows, `ACT_THEMESET`, `tape_theme_set`, the note "Applies the next time Cassette Mode opens."). `tape_theme` reads it when the Tape page opens; a change affects the next open. Value labels use translation keys, not fixed English text. The old tap-to-cycle value rows are gone.

**Library > Podcasts**: under a header of its own at the end of the Library page, **Podcast Search** (a switch row, Lucide `search`, `ACT_PCSEARCH` 34, `pcsearch_setting` / `pcsearch_toggle` in `patch/podcasts.c`, file `/mnt/data/m1plus/podcast-online-search`: `1` is on, a missing file or anything else is off, so it is **off by default**) and the note "Search words are sent to Apple." (the iTunes directory is queried with what is typed). The tap saves first (`home_write_atomic`: temp file, fsync, rename) and only then changes the switch: a failed save changes neither the file nor the switch. The Podcasts page reads the setting when it opens and each time it is back in front (`EVT_WINDOW_TO_FG`), so the Search button follows it: [Podcasts](podcasts.md) "Pages and controls". The row and its note have a text in the 13 languages (`Podcast Search`, `Search words are sent to Apple.`; French says `Recherche` under its `Podcasts` header, the full words did not fit the label). Tests: `test/pod/menu.py` `pcsearch_row_tests`.

## Stock pages and state

Every stock row is `ACT_STOCK` (`pod_pages.STOCK_PAGES`, `POD_STOCK` in `pages.h`): a plain `navigator_to(name)` with no context, which is exactly what stock's own lists do (`tools/pod.py SETTINGS_PINS` pins each call site's string load and the shared `jalr navigator_to`; the pages' inits read only globals, and Back is `navigator_back`, so it returns to our page). Verified in the disassembly of V2.1:

| Row | Page | Stock caller |
|---|---|---|
| Wi-Fi | `systemset/wifi_page` | the Wi-Fi hub's row thunk `0x4b1448` (the hub `systemset/wifiset_page` is the stock Settings' row 1; its Wi-Fi row goes straight to the list, so does ours) |
| Bluetooth | `systemset/bluetooth_page` | the hub's row thunk `0x4b1410` |
| Display | `systemset/display_page` | Settings row 3, string at `0x4ada74` (shared call `0x4ad830`) |
| (Language) | `systemset/language_page` | not linked from our page; stock reaches it through All System Settings |
| System Update (Developer > Tools) | `systemset/fwupdate_page` | Settings row 1, `0x4ada38` |
| Play Mode | `playset/playmode_page` | Play Settings row, `0x4a04a4` (shared call `0x4a0068`) |
| EQ | `playset/equalizer_page` | Play Settings row, `0x4a0218` (there is no EQ tile in the pull-down) |

The stock Settings' init sets `syssetinto_flag` (read only by the pull-down's tile handlers), so a sub-page opened from our page needs nothing set first. Values come from the words the stock UI reads (`DATA` in `tools/pod.py`): Wi-Fi `wififlag` (1 on; `wifi_switch` clears it and saves `[SYSSET] WIFI`), Bluetooth `bluetoothflag`, the play mode `mclGetPlayMode` 0..3 shown with the stock keys `playmode_listplay`, `playmode_repeattrack`, `playmode_shuffle`, `playmode_repeatall` (the keys the stock More dialog sets, `0x47a454..0x47a500`), EQ `equalizer_flag` (Off) or the preset's name from stock's `get_equalizer_preset_name` (`0x49daec`, a tr key `eq_*`). These are stock tr keys, so they follow Language. Nothing here toggles Wi-Fi or Bluetooth (`wifi_switch` sleeps on the UI thread): they are links. The values are read when the page opens and each time it is back in front (`EVT_WINDOW_TO_FG`, `page_refresh`).

## About

Settings > System > About (`m1plus_about`, `ABOUT_PAGE`) is our own cards page: the stock About page's seven values in sections, plus the build tag, so the stock page is no longer linked (it stays under All System Settings, unchanged; `tools/mod_about.py`, which added a tag row to it, is gone). Rows are `ACT_INFO` (`row_kind` info): a label and a grey 16 px value at the right, no chevron, no glyph, insensitive (not bound, `sensitive=false` in the asset), the value taking the room its text needs (`value_fit`, at most 190 px) and the label the rest. Read-only, on the UI thread when the page opens and each time it is back in front, no hook, no query, no write. The one exception is the **Software Update** link row right below the version row (`ACT_UPDATE`, a chevron, no glyph, bound to `update_open`: our own update page, [update](update.md); the rows stay insensitive but this one). Sections: the card with **M1+ Music** (the build tag, `M1PLUS_TAG`) and **Firmware**; **Device**: Model, Serial Number, Wi-Fi MAC, IP Address; **Storage**: Capacity, Available. Library counts are not shown: they would need a database query. An empty value reads "-".

The sources are what the stock page's widget walk reads (the callback of `systemset_about_page_init`, `0x4a1240..0x4a170c` (the symbol table calls it `on_sn_qrcode_onclick`; the init is `0x4a170c`..; it matches the rows by widget name and sets each label `"<key>:<value>"` with `getFormatString`):

| Row (stock key) | Stock source | Pinned (`SETTINGS_PINS`, `DATA`) |
|---|---|---|
| Model (`about_model`, scrlabel0) | the literal `"Shanling M1 Plus"` at `0x747718` | `addiu v0` at `0x4a145c`, the word at `0x747718` |
| Firmware (`about_version`, scrlabel1) | the literal `"V2.1"` at `0x74773c` (never patched: the row follows stock; only the updater's compare is repointed, `modules/version.md`) | `0x4a14cc`, `0x74773c` |
| Capacity (`about_cardcap`, scrlabel2) | float at `0xa03e74`, set by `getDiskMemoryInfo("/mnt/mmc", &cap, &free)` (`0x5b30e0`: `statfs`, in G) at init, only while `access("/tmp/mmc_add")` succeeds (else 0); stock prints `%.2fG` | `lwc1` at `0x4a1514`, the call at `0x4a1778` and its arguments `0x4a176c..0x4a177c`, `access` string `0x4a1754` |
| Wi-Fi MAC (`about_wifimac`, scrlabel3) | the string `wifi_mac` (`0xa061a8`, 32 bytes); empty when not set (stock shows only the label) | symbol `wifi_mac` |
| Available (`about_cardremain`, scrlabel4) | float at `0xa03e70`, the same call | `lwc1` at `0x4a1634` |
| Serial Number (`about_sn`, scrlabel5) | the string `product_sncode` (`0xa0553c`, 16 bytes) | symbol `product_sncode` |
| IP Address (`about_ipaddr`, scrlabel6) | `networkGetIPAddr(0, buf)` (`0x5d753c`) while `networkGetConnectStatus()` (`0x5d7cac`) is above 0, else empty | the two `jalr`s at `0x4a16dc`, `0x4a16f4` |

Capacity and Available are shown as `N.NN GB` made with integers (the payload prints no floats); our page calls `getDiskMemoryInfo` itself on each refresh (a `statfs`, as stock does at the page's init). The build tag, the labels and the section headers are the only things not from stock; the labels are our translation keys (13 languages).

## Keyboards

Settings > Keyboards (`m1plus_keyboards`) lists the keyboards the on-screen keyboard ([keyboard](keyboard.md)) offers as two switch rows: **English**, always on (its switch shows on, the
row is dimmed to 60 % and takes no tap: `bind_switch` sets its opacity and sensitivity, nothing is bound), and **Chinese (Pinyin)**, a normal switch row (`ACT_KB_ZH`, `kb_zh_toggle`, saved atomically in
`m1plus-kbzh`, off by default; the keyboard reads it each time it opens, `kb_zh_setting`). With it on the keyboard has a language key and a pinyin layer; turning it off also forgets the layer the last keyboard
ended on. A failed save changes neither the file nor the switch. The three strings are in all 13 languages (`Keyboards`, `English`, `Chinese (Pinyin)`); the rows' glyphs are the Lucide `languages`
(`pod_ci_languages`). More keyboards would be more rows and a bit each in the layer table of `patch/keyboard.c`.

## Rebuild Covers

`ACT_REBUILD` calls `rebuild_ask`, which opens stock `dialog/confirminfo_dialog` through
`navigator_to_with_context`. The context is `{kind, ms, text[0x200], text2[0x200]}`; text starts
at +8. Kind 5 gives wrapped 20 px text in a 260 × 80 box at y 25. Kind 1 scrolls one line and
must not be used for this message. Evidence: `dialog_confirminfo_dialog_init` `0x472cec`,
branch `0x472e1c`; stock equalizer reset `on_eqreset_onclick` `0x49dd6c` uses the same dialog.

Only `CONFIRM_YES` (`0xa`, `btn_enter`) acts; No or a failed dialog does nothing. Yes stays on Settings: it writes the request
file `/mnt/data/m1plus/covers-rebuild` (`REBUILD_FILE`, `"1\n"`, `home_write_atomic`, so it survives a reboot) and shows the toast
"Covers will rebuild on Home" (`pod_toast`; a failed write shows "Storage unavailable"). Home's cover build does the rest
([homecover.md](homecover.md)): every cover is extracted again in the background, including no-art markers, and the file is
removed when it completes. The translated message and toast are checked in all 16 tables. The kind-5 appearance still needs
device confirmation.

## Cover Cache

Settings > Developer > Tools > **Cover Cache** (a link row, glyph `hard-drive`) opens `m1plus_cache`, a cards page of the About kind (`ACT_INFO` rows: a label and a grey right-aligned value, no chevron, no touch; `INFO_CC_*` kinds, values from `homecover_stat`). Card 1: **Albums** (library albums), **Covers** (`r<key>-168.jpg` with size > 0), **No art** (empty `r` markers), **Missing** (albums with neither, by the `CC_MISSING` rule: a track path and no file), **Old files** (every other file: unprefixed, `f`-prefixed, `.tmp`, the old Cover Flow position `album`), **Size** (all files, MB with one decimal under 10 MB). Card 2: **Status**: Idle, Preparing n/m or Rebuilding n/m (Home's own set; in practice Home is in the background while Settings is open, so these show only if it ever holds the worker here), Building [n/m] (another page's set), Rebuild requested (the request file exists, nothing builds), Clearing. Card 3: **Clear Cover Cache**.

Counting never blocks and only runs while the page is open (`homecover_cache_open`, `patch/homecover.c`): the folder is read `CP_N` 64 entries per 20 ms tick (`cc_file_size` per file), then `cc_albums` is loaded once and checked 64 albums per tick; until a count is known its value is an ellipsis. A 500 ms poll refreshes the page when the Status text changed. Background and destroy remove both timers and free the directory handle and album copy; the foreground and a finished clear count again from nothing. No folder: zeros (every album missing), Status Idle. Tests: `test/pod/homecover.py` `cache_tests`.

**The two lists.** **No art** and **Missing** are value rows (`ACT_CCLIST`, no glyph): the chevron shows and the row takes a tap only when the count is counted and above 0 (while an ellipsis or 0 they are plain values; the payload sets the chevron's visibility and the row's sensitivity at each refresh). A tap opens a plain list (`patch/covlist.c`, window `m1plus_covlist`, title No Art / Missing Covers): the Albums page's own asset pattern (`build_grid_page` without the toggle and Cover Flow button: plain navbar, stock list_view > scroll_view, one content view) and its list-mode painter (`grid_list_paint`, moved left over the cover's room, no bitmap so nothing is decoded or drawn as a disc): each row is the album's title (21 px white) and the artist (18 px grey), 64 px rows with a hairline from the text and the list chevron, in the Albums order. A tap on a row (a release within the scroll threshold of the press) opens that album with `cc_open_album`; Back returns to the list and Back again to Cover Cache. The rows are display positions collected by the count's album scan (empty marker = No art, no file = Missing; at most `CC_MAX_JOBS` each) and copied into the list page, which loads `cc_albums` once for the texts; the copy, the order and the rows are freed with the window. Nothing to show: "No albums". The No art count is the folder's empty markers (including ones no album has), the list the albums that have one, so they can differ. The value text on this page is the standard 18 px (About's rows stay the stock About's 16 px). Tests: `covlist_tests` in `test/pod/homecover.py`, the Developer path in `test/pod/menu.py`.

### Clear Cover Cache (card 3)

`ACT_CLEARCACHE`, glyph `trash`. `clear_ask` first refuses with the toast "Covers are being made, try later" when the shared cover worker is held (`cc_build_busy`; nothing is stopped, since a set may belong to Albums or Cover Flow). Otherwise it asks in the same stock confirm dialog (kind 5) "Delete all cached covers? They will be made again on Home."; No does nothing. Yes calls `homecover_clear` (`patch/homecover.c`): it removes a pending Rebuild Covers request and deletes every regular file in `/mnt/mmc/.m1plus/covers` except `album` (Cover Flow's position): the `r<key>-168.jpg` pictures, their empty no-art markers, `.tmp` leftovers and the stale old-format files. Deletion is 32 unlinks per 20 ms tick of a self-ending timer (the directory handle is kept between ticks), so nothing blocks; the timer needs no page, so leaving Settings mid-way lets it finish, and a build starting meanwhile stops it quietly (a partial clear is fine). The toast "Cover cache cleared" shows at the end. Home's build then finds every album missing at its next foreground. Tests: `test/pod/homecover.py` `clear_tests`.

### Clear Track Durations

Settings > Developer > Tools > **Clear Track Durations** (`ACT_CLEARDUR` 44, glyph `trash`, after Cover Cache) asks "Delete all measured
track durations? They will be measured again on Home." in the same confirm dialog. Yes calls `dur_clear` (`patch/durations.c`): it deletes
`/mnt/mmc/.m1plus/durations` (and its `.tmp`; nothing is touched while the card is out), empties a table held by an open page and counts the clear (Home reads the library again
at its next foreground), then toasts "Track durations cleared". It does not wait for the worker. See [Album length](album-page.md#album-length).

## Settings Files

Settings > Developer > Tools > **Settings Files** (a link row, glyph Lucide `file-cog`) opens `m1plus_files`, a cards page of the Cover Cache kind (`ACT_INFO` rows, `INFO_SF + k`, values from `setfiles_stat`, `patch/setfiles.c`). It shows the payload's own files as raw values: the labels are the file names themselves (identifiers, untranslated; only the title is translated). Card 1: the guard files in `/mnt/data` (`m1plus-start` the character, `m1plus-run`, `m1plus-bad`, `m1plus-off` present or missing). Card 2: `m1plus/` (the settings folder: present or missing), then one row per file in it (the Albums, Playlists and Recently Added views among them): a single-character setting shows its character (`other` for anything longer, `empty`), `home-menu` and `pulldown-tiles` their first 12 characters (an ellipsis after), `search-history` its number of lines, `covers-rebuild` present or missing; a file that is not there reads `missing`. Everything is read once by `setfiles_open` as the page opens (open, read, close, access); a refresh on coming back to the page shows those values again and reads nothing, no timer. No hook or pin. Tests: `files_tests` in `test/pod/homecover.py`.

## Album ordering and initial selection

`cc_album_order` keeps the stock deque unchanged and creates an `order[]` of stock row numbers:

- **Album:** the stock list (`getAllAlbum` `group by album COLLATE NOCASE`, then `toolsQueryDbTable`'s in-memory title sort).
- **Artist:** representative track's `songer`, then album title, each by the name order of
  `docs/modules/artists.md` (digit runs by value, ASCII case folded, digits and symbols before letters, CJK
  by pinyin initials among the Latin names, leading white space and `The ` removed); ties resolved by stock position. There is no album-artist fallback
  because the query does not fetch that field. Unknown Album (ID -1) goes last.

The permutation uses heapsort; access goes through `cc_row`, and stock album opens receive
`order[i]`. Albums and main Cover Flow share it. Per-artist Cover Flow retains its stock album
title order. Cache keys remain artist + album title. Cost: 4000 albums sort in 30.8 M payload instructions
(two keys per row; stock's own in-memory sort of the same list, which runs first, is over 10x that:
`docs/modules/artists.md` "Cost against stock's sort").

At open, `find_playing` checks `cc_playing`: `mclGetPlayPos` `0x5d4290` and `PLAY_QUEUE`
`0xa0394c`, bounded by `deque_size`. It matches the album by `cc_album_key` (FNV of artist/title),
then title ignoring ASCII case for compilations. Selection priority is playing album, saved
`coverflow-position`, then first album. This is a one-time lookup, not polling.

## Open Shanling Home and startup

Open Shanling Home (Developer > Startup) sets the session's `grid` flag, shows the stock grid and closes the recorded menu,
Extras and Settings windows by handle before navigating back from the Developer page. It does not
issue repeated `navigator_back` calls against a closing window. Destroy handlers forget the
recorded handles.

When startup is enabled and the guard is armed, tapping grid icon 99 clears `grid` and opens
the Home menu instance; a failed open restores the prior state. With startup disabled, it opens
the normal instance. The Home instance hides the navbar (invisible and insensitive) and uses
`HOME_PAD` 10 with a 430 px list. The normal instance retains Back, title and Now Playing.
Missing widgets leave the stock layout. See [boot guard](home-guard.md) for startup safety.
