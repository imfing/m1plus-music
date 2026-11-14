# Settings and launcher

Sources: `patch/m1plus.c`, `patch/home.c`, `patch/setfiles.c`, `patch/keyspower.c`, `patch/playset.c`, `patch/battery.c`, `patch/pcregion.c`, `tools/pod_settings.py`, `tools/pod_ui.py` and `tools/pod_pages.py`. User instructions are in the [guide](../guide.md#settings).

Settings is main-menu item 18 (`j`), hidden by default. The Extras navbar always reaches it and it cannot be turned off. It is an iOS-style page of grouped cards.

## Page tree

| Group | Row | Opens | Doc |
|---|---|---|---|
| (top card) | Wi-Fi | our Wi-Fi page (`m1plus_wifi`) | [wifi](wifi.md) |
| | Bluetooth | stock Bluetooth page | [stock pages](#stock-pages-and-state) |
| (top card) | Home Screen | our page: Recent Albums, Daily Mix, Main Menu / Extras, Regenerate Daily Mix | [dailymix](dailymix.md), [menu](menu.md) |
| | Library | our page: Update Library, Rebuild rows, List Navigation, Folders (Folder Album Cover), Cover Flow, Podcasts | [albums](albums.md), [podcasts](podcasts.md) |
| | Now Playing | our page: Cassette Theme, Idle Display | [tape](tape.md), [bigcover](bigcover.md) |
| **Playback** | EQ | our Equalizer page | [peq](peq.md) |
| | Playback Settings | our page `m1plus_playset`: Play Mode, Gapless, Resume, Folder Skip, Continue Playing, Gain, Max Volume, Default Volume, Channel Balance (three slider pages with stock's own handlers), ReplayGain, Digital Filter, DSD Output Mode, USB Volume, Digital Output | [playset](playset.md), [nextalbum](nextalbum.md) |
| **System** | Display | our page `m1plus_display` | [display](display.md) |
| | Buttons & Power | our page `m1plus_keyspower` | [keyspower](keyspower.md) |
| | Appearance | our page `m1plus_appearance`: Background, Accent, Control Center | [accent](accent.md), [pulldown](pulldown.md) |
| | Keyboards | our page `m1plus_keyboards` | [keyboard](keyboard.md) |
| | Battery | our page `m1plus_battery`: Battery Percentage, Charge Limit | [battery](battery.md), [charging](charging.md) |
| | About | our page `m1plus_about` | [About](#about) |
| | All System Settings | stock sysset page (its Theme row is removed) | [theme](theme.md) |
| **Developer** (same card as All System Settings) | Startup | Boot to M1+ Music, Open Shanling Home | [home guard](home-guard.md) |
| | Tools | Screenshot, Cache, Settings Files | [screenshot](screenshot.md), [Cache](#cache), [Settings Files](#settings-files) |
| | Reset | Reset All Settings | [Reset All Settings](#reset-all-settings) |

Keyboards sits under System because the design had no place for it, and dropping the pinyin switch would have lost a feature.

## Cards

The design is `tools/preview/preview_settings.py` (it draws the built tree's own assets; `out/preview/settings-mock-3.png`). The numbers are `tools/pod_settings.py` (shared by `tools/pod_ui.py build_cards_page`, the preview and `test/pod/settings.py`); a page is a `Page(layout=[Row, Hdr, Note, GAP ...])` in `tools/pod_pages.py` and its kind is `cards`.

- The list is the stock `list_view` > `scroll_view` (310 wide) + `scroll_bar_m`, the rows stock `list_item`s (`list_item_style`, the stock 21 px `hscroll_label`).
- **The layouter stacks the children.** The stock `list_view` layouter (`children_layouter_list_view`, `0x60b12c..`; see [recent](recent.md) "The shelf after the rows") ignores a child's `y`: it puts every **visible** child of the scroll_view at the running y in **child order**, sets x (0) and the width, and sums the heights into `virtual_h`. V2.1zWZKWAAAB had the cards as views of their own placed by `y`, so the layouter stacked them as a block above the rows. So the page is now only a column of full-width items in display order, nothing relying on the asset's y/x/w: a 10 px spacer (`pod_top`), the rows, headers (`pod_sec<n>`, 40), notes (`pod_note<n>`, 34), gaps (`pod_gap<n>`, 20), all insensitive views except the rows, and a 10 px spacer (`pod_end`). The asset's y is the stacked y anyway.
- **A card is drawn by its rows.** Each row's background (`bg_image`, draw type `default`, `bg_color` transparent) is a picture piece, `pod_cd_single`, `_top`, `_mid` or `_bot` (320 x 52, `mod_icons.card_piece`): the card (x 10 .. 310, `#1C1C1E`, radius 12 only on the corners the piece has) is baked in and the rest is transparent; `pod_cd_<piece>_down` is the same shape in the pressed grey `#2C2C2E` (the highlight is clipped to the card's shape, corners included). The pieces are 320 wide because the layouter gives a child the list's width. A row of a hidden neighbour stays right because a row's piece depends only on the rows around it in the layout, and the one that hides (Regenerate Daily Mix) is a card of its own, a single piece. The row's children are row relative (the glyph image at x 22, the label at 58 or 24, a hairline `#333333` from the label to x 310, on every row but a card's last, the chevron / value / switch / check with their ink 14 px from x 310). Headers and notes are views whose grey label starts at x 24, the left of the row glyphs' ink.
- The right side by ink: **link** = the chevron `pod_chev` (the shared list chevron, 10 x 16, `#8A8A8A`, `mod_icons.pod_chevron`) at x 288, 12 px inside the card edge, centred above the card's hairline, the label's box ending 8 px before it (x 280, so its text ends at 278 after the label's 2 px inset); **value** = grey `#AAAAAA` 18 px text 8 px left of the chevron (`pod_value<i>`; the payload sizes it to its text and gives the row's label the rest: `value_fit`); **switch** = the stock `sset_on` / `sset_off` image; **picker row** = no glyph and a check (`pod_check<i>`, shown on the chosen row); **action** = nothing (Update Library, Regenerate Daily Mix, Rebuild Covers, Open Shanling Home, Screenshot). `pod_pages.row_kind` says which.
- Headers are `#AAAAAA` 18 px and notes 15 px. The Now Playing button is the round `ah_nav_np`. The navbar fade (`img_nb_fade`) stays hidden: the first card is 10 px under the bar and the fade would dim it at rest.
- Hidden is `visible=false` and `sensitive=false` (the layouter then skips the item); headers, notes, spacers, glyphs and accessories are never sensitive. `test/pod/settings.py` runs demo's own layouter (`window_manager_check_and_layout`) on every cards page as built, starting each child at a wrong x and y, and asserts every child's final x, y and height, `virtual_h`, and that with Daily Mix off the Regenerate row and its note are skipped and nothing else moves; it also hit-tests every visible row, header, note and gap.

## Page notes

**Home Screen** has the Recent Albums and Daily Mix switches (one card, the note "Shown on Home below the menu"). The menu's arrangement (Main Menu and Extras, two link rows with notes) follows. Last on the page, after Extras and its note, is Regenerate Daily Mix in a card of its own with its note: an action that requests a new seed (a toast "New mix when Home opens" confirms an accepted tap); the Home page rebuilds when next foregrounded. That row and its note are hidden (`regen_show`: the last row, `pod_note3`; the layouter skips them and the page ends after Extras) while no mix can be made (Daily Mix off, or a library under `MIX_MIN_LIB`). Shelf and mix visibility are reread when returning to Home. The separate Recent Albums translation fits switch rows where Recently Played would overflow.

**System > Battery** has, as its first row above Charge Limit, **Battery Percentage** (a switch row, Lucide `battery-charging`, `battpct_setting` / `battpct_toggle` in `patch/battery.c`, off by default) with the note "The exact charge beside the battery icon". The status bar reads it through the payload's cached flag, which the switch updates at once; what it does is [battery](battery.md) "The percentage". Texts in the 13 languages (no `%` in a text, `mod_strings` refuses one). Tests: `test/pod/battery.py`.

**Library**: Update Library (the stock updatemusic page, as the Update Library item), then one card with **Rebuild Covers** and **Rebuild Artist Photos** (glyph `mic-vocal`; see "Rebuild rows"). Under the grey header **List Navigation** are the **Index Rail** and **Section Headers** switches of the A-Z lists, with a grey note "Songs, Artists, Albums and Radio lists" (translated in every UI language). Index Rail is the A-Z rail and its bubble on Songs, Artists, Radio countries and the Albums list; the rows leave room for it ([artists](artists.md)). Under the Cover Flow header are Landscape and **Volume Buttons** (two switch rows, Lucide `volume-2`, `coverflow_volkeys` / `coverflow_volkeys_toggle` in `patch/coverflow.c`; the note "In Cover Flow, the volume buttons move between albums." is a two-line wrapping note, see "Wrapping notes"). The album order is set on the Albums "..." card; the old Album Order row and its picker are gone.

**Library > Podcasts** is a page of its own (`PCSET_PAGE`, `m1plus_podcastsettings`, a cards page placed before `m1plus_podcastdirectory` in `PAGE_ORDER`; titled Podcasts; no new action: the Library row is a plain `ACT_PAGE` link). Card 1 is Podcast Discover (a switch, on by default; off hides the Podcasts Discover row and the search level). Card 2 is Podcast Directory (a picker: Apple Podcasts, the default, or Podcast Index; where the search and the id lookup go) and Podcast Region (a picker of Automatic and the 34 storefronts; it serves Discover's charts, which are always Apple's, and the Apple search, not Podcast Index), with the note "Search words go to the chosen directory.". Both rows of card 2 are dimmed and take no tap while Discover is off (`pcdir_show`, on open, on the switch and when the page is back in front); Region is never dimmed because of the chosen directory. The Library page keeps only the row Podcasts (a plain chevron row, Lucide `podcast`, no value: the page has no one state to show) in the last card above Scrobbling. Details and the settings rows are in [podcasts](podcasts.md#settings-rows).

**Now Playing**: under the Cassette Mode header, **Theme** (value Normal / Chrome / Metal / Auto, opens the picker `m1plus_tapetheme` with four check rows and the note "Applies the next time Cassette Mode opens."). `tape_theme` reads it when the Tape page opens. Value labels use translation keys, not fixed English text. After Cassette Mode and Vinyl Mode comes a card with one value row, **Lyrics Text Size** (`ACT_LYRSIZE` 115, glyph `mic-vocal`: Small, Medium or Large, read from `nowplaying-lyrics-size`; it opens the picker `m1plus_lyrsize`, `ACT_LYRSIZESET` 116, three check rows, `ly_size` / `ly_size_set` in `patch/lyrics.c`; [lyrics](lyrics.md) "Text size"). The last card is **Idle Display** (a value row: Off, Album Cover, Cassette, Vinyl or Lyrics, read live from stock's Cover mode byte and `nowplaying-idle`; it opens the picker `m1plus_idleview` (five check rows) with the note "Shown after 10 seconds on Now Playing."; [bigcover](bigcover.md) "Idle view").

## Persisted choices

Switches and pickers save before they update their image or check; a failed save changes neither the file nor the displayed state. Reading settings never writes them. One reader serves every one-character file below: `set_read(path, default)` (patch/home.c, declared in home.h) returns the character of a file that is exactly `x` or `x\n`, and the default for a missing file, an empty one or anything longer (trailing junk is the default, never a first-byte match). Each setting compares that character; the values below are those characters. The multi-value files (`home-menu`, `pulldown-tiles`, `search-history`) and the boot guard's `m1plus-start` have their own parsers.

Feature settings live in their own folder, `/mnt/data/m1plus/` (`SET_DIR`, patch/home.h). `home_write_atomic` makes the folder when a write finds it missing and fsyncs the folder after the rename. The boot guard's files stay directly in `/mnt/data/`: `m1plus-start` (Boot to M1+ Music: `0` stock Home; missing/other enables M1+ Music), the marker `m1plus-run`, the bad note `m1plus-bad` and the kill switch `m1plus-off` ([home guard](home-guard.md)). The guard's crash path therefore never depends on the folder.

**Our files under `/mnt/data/m1plus/`**, by file name. Every one is listed on Settings Files.

| File | Setting | Values / default |
|---|---|---|
| `albums-sort` | Albums order | one character: `0` Title, `1` Artist, `2` Recently Added, `3` Year, or `a` .. `d` for the same order reversed; missing/other Artist, not reversed ([albums](albums.md#album-order-and-initial-selection)) |
| `albums-view` | Albums view | `0` list; missing/other grid |
| `appearance-accent` | Accent | one digit, the index 0 Neutral (default) .. 6 Champagne; missing/other Neutral ([accent](accent.md)) |
| `appearance-background` | Background | `0` Black (default), `1` Tinted; `2` Light and `3` Light Auto are not offered; missing/other Black ([accent](accent.md)) |
| `appearance-headers` | Section Headers | `0` off; missing/other on (the default); the section letters and pinned header of the A-Z lists, the rows close up when off |
| `appearance-index-rail` | Index Rail | `0` off; missing/other on (the default) ([artists](artists.md)) |
| `artists-rebuild` | Rebuild Artist Photos request | exists while requested; written as `1\n`; removed by Home's pass ([homecover](homecover.md#rebuild-covers), [artists](artists.md)) |
| `artists-sort`, `genres-sort`, `composers-sort` | Artists / Genres / Composers order | one character per page: `a` Name Z-A; missing/other Name A-Z ([artists](artists.md)) |
| `battery-charge-limit` | Charge Limit | `0` 80 %, `1` 85 %, `2` 90 %, `3` 95 %; missing/other 100 %, no limit (the default) ([charging](charging.md)) |
| `battery-percentage` | Battery Percentage | `1` on; missing/other off (the default) ([battery](battery.md)) |
| `cassette-theme` | Cassette Theme | `0` Normal, `1` Chrome, `2` Metal, `3` Auto (by the track's quality); missing/other Auto (the default) ([tape](tape.md)) |
| `covers-rebuild` | Rebuild Covers request | exists while requested; written as `1\n`; removed when Home's cover build completes ([homecover](homecover.md#rebuild-covers)) |
| `coverflow-landscape` | Cover Flow Landscape | `1` landscape; missing/other portrait ([coverflow](coverflow.md)) |
| `coverflow-volume-keys` | Cover Flow Volume Buttons | `1` the volume buttons step Cover Flow; missing/other off (the default) ([coverflow](coverflow.md) "Volume buttons") |
| `folders-sort` | Folders order | `0` Name, `1` Date Modified, `2` Type, or `a` `b` `c` for the same order reversed; missing/other Name A-Z; one order for every level ([folders](folders.md)) |
| `home-daily-mix` | Daily Mix | `0` off; missing/other on ([dailymix](dailymix.md)) |
| `home-menu` | Main Menu / Extras | item ids in order, optional `-` then the hidden ids; invalid = defaults ([menu](menu.md)) |
| `home-recent-albums` | Recent Albums | `0` off; missing/other on |
| `keyboard-pinyin` | Chinese (Pinyin) keyboard | `1` on; missing/other off ([keyboard](keyboard.md)) |
| `lockscreen-layout` | Lock Screen > Player Style | `1` Mini Player; missing/other Large Cover (the default); applies the next time the lock screen opens ([lockscreen](lockscreen.md)) |
| `nowplaying-idle` | Idle Display | `1` Cassette, `2` Vinyl, `3` Lyrics; missing/other Album Cover. Off is stock's Cover mode byte, not this file ([bigcover](bigcover.md) "Idle view") |
| `nowplaying-lyrics-size` | Lyrics Text Size | `0` Small (22 px), `1` Medium (26), `2` Large (30); missing/other Large (the default) ([lyrics](lyrics.md) "Text size") |
| `playback-eq` | Equalizer curve | the `M1PEQ02` record ([peq](peq.md)); missing/invalid: 10-Band EQ, Flat, Auto. The switch is stock's `[PLAYSET] EQFLAG`. Per output ([peq](peq.md#per-output-eq-patchpeqoutc-patchpeqouth)): `playback-eq-headphones`, `-lineout`, `-usb` (the same record) and `playback-eq-output` (the owner and each output's switch) |
| `playback-next-album` | Continue Playing | `1` Next Albums; missing/other Off (the default); `2` reserved for Auto Mix ([nextalbum](nextalbum.md)) |
| `playback-shuffle` | Shuffle (the payload's flag; stock's mode is never 2) | `1` on; missing/other off ([shuffle](shuffle.md)) |
| `playlists-sort` | Playlists order | `a` Name Z-A; missing/other Name A-Z (the retired `1` / `b` read as A-Z) ([playlists](playlists.md)) |
| `playlists-view` | Playlists view | `0` list; missing/other grid |
| `pod-appearance` | Pod Appearance | `1` Dark; missing/other Light |
| `podcast-online-search` | Podcast Discover | `0` off; missing/other on (the default); gates Discover and the search level ([podcasts](podcasts.md)) |
| `podcast-directory` | Podcast Directory | `1` Podcast Index; missing/other Apple Podcasts (the default); where the search and the id lookup go ([podcasts](podcasts.md) "Podcast Directory"); the last setting file (row 41) |
| `podcast-region` | Podcast Region | the storefront's two capital letters and a line feed (one of the 34 in `tools/pcregion.py`); missing/other Automatic ([podcasts](podcasts.md) "Region") |
| `pulldown-tiles` | Control Center | tile ids `0`-`7` in order, optional `-` then the hidden ids; invalid = all eight in stock order ([pulldown](pulldown.md)) |
| `radio-recent` | Recent radio stations | an `.m3u` of up to 10 stations, newest first ([radio](radio.md)) |
| `radio-view` | Radio station lists view | `1` grid; missing/other list ([radio](radio.md)) |
| `recently-added-view` | Recently Added view | `1` albums grid; missing/other songs ([recent-albums](recent-albums.md)) |
| `scrobble-auto` | Auto Upload | `1` on; missing/other off (the default; read once, by the first poll after a listen was logged); the Scrobbling page's switch ([Scrobbling](scrobble.md#automatic-upload)) |
| `scrobbling` | Scrobbling | `1` on; missing/other off (the default; read once by the first poll) ([Scrobbling](scrobble.md)) |
| `search-history` | Recent searches | up to 5 UTF-8 lines, newest first; malformed = none ([search](search.md)) |
| `songs-sort-rev` | Songs direction | `a` Title / File Name / Format run Z-A; missing/other A-Z; ignored for Recently Added, whose direction is the stock `sort_flag` 3 / 4 ([songs](songs.md)) |
| `vinyl-base` | Vinyl Base | `1` Snow; missing/other Graphite ([vinyl](vinyl.md)) |
| `vinyl-record` | Vinyl Record | `1` Cover; missing/other Black ([vinyl](vinyl.md)) |
| `wifi-networks` | Saved Wi-Fi networks stock cannot read | `network={}` blocks (WPA3, Enhanced Open, Enterprise) the Wi-Fi page writes and `wifi_connect.sh` adds to the copy only the newer supplicant reads; holds passwords; deleting it (or Reset All Settings) forgets those networks only ([wifi](wifi.md)) |

The retired Settings > Library > Album Order file `album-order` (`0` Title, else Artist) is moved into `albums-sort` once, when that file is missing, and then deleted (`sort_migrate`, run by `cc_sort_mode`; no table entry; Reset All Settings removes a leftover).

**Stock state we read and write** (no file of ours). These are stock's `[SYSSET]` words and bytes; the page reads them when it opens and writes them the way stock's own handlers do.

| Setting | Stock key | Values |
|---|---|---|
| Lock Screen > Enable | `[SYSSET] SCREENSAVER` (the byte `screensaver_mode`) | 1 on (stock's default), 0 never shows the lock screen; the same switch as stock's Lock Screen page ([lockscreen](lockscreen.md)) |
| Lock Screen > Wallpaper | `[SYSSET] SCREENSAVERPATH` (the global `screensaver_picture`) | `screensaver_default` or the path of one of the up to five 320 x 480 pictures in `/mnt/mmc/lockscreenimage`; the same choice as stock's Lock Screen page ([lockscreen](lockscreen.md) "Wallpaper picker") |
| Lock Screen > Show Time | `[SYSSET] SSAVERTIMESHOW` (the byte `screensaver_timeshow`) | 1 shows the clock and date (stock's default), 0 hides them ([lockscreen](lockscreen.md)) |
| Display > brightness slider | `[SYSSET] LIGHTNESS` (the word `lightness`) | 0 .. 100, written by stock's own slider handlers ([display](display.md)) |
| Display > Screen Timeout | `[SYSSET] LIGHTTIME` (the word `backlighttime_mode`) | 0 never, 1 15 s, 2 30 s, 3 1 min, 4 5 min ([display](display.md)) |
| Display > LED Light | `[SYSSET] ATMOSPHERELEDMODE` (the byte `atmosphereled_mode`) | 0 off, 1 green, 2 blue ([display](display.md)) |
| Display > Follow Screen | `[SYSSET] LEDFOLLOWSCREEN` (the byte `ledfollowscreen_flag`) | 1 on, 0 off ([display](display.md)) |

## Files on the card

Everything the payload keeps on the SD card (found with `grep -rnE 'CARD_DIR|"/mnt/mmc/' patch/*.h patch/*.c`). The folder `/mnt/mmc/.m1plus/` is `CARD_DIR` (patch/covercache.h); writers make it only while the card is mounted. Reset All Settings touches none of these.

| Path | Owner | Doc |
|---|---|---|
| `.m1plus/covers/` | Home's cover cache (`r<key>-168.jpg`, empty no-art markers) | [homecover](homecover.md) |
| `.m1plus/cache-stamp` | cover cache stamp (patch/homecover.c) | [homecover](homecover.md) |
| `.m1plus/artists/` | artist photo cache (`a<key>-44.jpg`, `-168.jpg`, `.pick`) | [artists](artists.md) |
| `.m1plus/durations` | measured track durations (patch/durations.c) | [album-page](album-page.md#album-length) |
| `.m1plus/recently-played` | Home's Recently Played albums (patch/recent.c) | [recent](recent.md) |
| `.m1plus/coverflow-position` | the Cover Flow position (patch/coverflow.c) | [coverflow](coverflow.md) |
| `.m1plus/daily-mix/` | Daily Mix tracks and art | [dailymix](dailymix.md) |
| `.m1plus/podcasts/` | `resume`, `speed`, `order`, `search/` (thumbnails) | [podcasts](podcasts.md) |
| `.m1plus/art/` | Find Cover & Lyrics scratch (thumbnails `a<n>`, the larger picture, lyrics `l<n>.txt`) | [onlineart](onlineart.md) |
| `.m1plus/autoeq/` | AutoEq download list and presets | [peq](peq.md) |
| `.m1plus/subsonic/`, `subsonic.conf` | Subsonic / Navidrome cache and the one-line server file | [subsonic](subsonic.md) |
| `.m1plus/navidrome.index`, `navidrome-view`, `navidrome-art` | Navidrome index, view and art | [subsonic](subsonic.md) |
| `m1plus-off` | kill switch on the card (`KILL_SD`, patch/home.h) | [home guard](home-guard.md) |
| `m1plus-noblur` | mini player bar's backdrop blur off | [minibar](minibar.md) |
| `m1plus-log`, `m1plus.log` | opt-in log: the empty marker, then the log it appends to | [home guard](home-guard.md) |
| `m1plus-update-url` | the update channel's URL (`UP_CHAN_FILE`, patch/upver.h) | [update](update.md) |
| `.scrobbler.log`, `.scrobbler.log.sent`, `.scrobbler.log.rejected` | the listens that wait for an upload, those a service took and those every service refused (patch/scrobble.c, patch/scrobup.c) | [scrobble](scrobble.md) |
| `scrobble.ini` | the ListenBrainz and Last.fm accounts, written by the user; the device writes only the ListenBrainz `USER=` line (patch/scrobup.c) | [scrobble](scrobble.md#upload) |
| `Radio/` | `favourites.m3u` (the Stations list) and the user's `.m3u` / `.pls` | [radio](radio.md) |
| `Subsonic/` | downloaded Subsonic files | [subsonic](subsonic.md) |
| `EQ/` | the APO / AutoEQ presets the Equalizer page lists (`PEQ_DIR`) | [peq](peq.md) |
| the Podcasts folder | episode folders (its name as the card spells it, patch/podcasts.h) | [podcasts](podcasts.md) |
| `screenshots/` | screenshots (`shot-NNNN.bmp`) | [screenshot](screenshot.md) |
| `lockscreenimage/` | the lock screen pictures (up to five) | [lockscreen](lockscreen.md) |

## Cache

Settings > Developer > Tools > **Cache** (a link row, glyph `hard-drive`) opens `m1plus_cache`, a read-only cards page of the About kind with the cover, artist photo and track duration counts, the Clear Cover Cache and Clear Track Durations rows. See [homecover](homecover.md#cache-page) and [track durations](homecover.md#track-durations).

## Rebuild rows

**Rebuild Covers** and **Rebuild Artist Photos** are action rows in Library. Each asks in the stock confirm dialog ([confirm dialog](ui-rules.md#confirm-dialog)); only Yes acts, and it writes its request file (`covers-rebuild` or `artists-rebuild`, see the table above) with `home_write_atomic` and shows a toast. Home's background pass does the rest: [homecover](homecover.md#rebuild-covers) for covers, [artists](artists.md) for the photos. The two requests are separate; nothing of one is requested or cleared by the other.

## Display

Settings > System > Display (`m1plus_display`, `DISPLAY_PAGE`, `patch/display.c`) is one cards page of three cards: the brightness slider, Screen Timeout and Lock Screen, LED Light and Follow Screen. No row opens a stock page, every state is stock's own, and nothing of ours is saved; see [display](display.md).

**Library > Scrobbling**: the second row of the last card, under **Podcasts**, **Scrobbling** (a value row, Lucide `list-music`, `ACT_SCROBPAGE` 139, `VK_SCROB`: On or Off from `scrobble_setting`, the value read again when the Library page is back in front; it opens the Scrobbling page). The Library page keeps none of the scrobbling rows or notes.

**Library > Scrobbling page** (`SCROBBLING_PAGE`, `m1plus_scrobbling`, a cards page; its place comes from `PAGE_ORDER`, macro `POD_SCROBBLING_PAGE`): card 1, **Scrobbling** (a switch row, Lucide `list-music`, `ACT_SCROBBLE` 96, `scrobble_setting` / `scrobble_toggle` in `patch/scrobble.c`, file `/mnt/data/m1plus/scrobbling`, **off by default**) and the note "Saved to .scrobbler.log on the card." Saved like Podcast Discover. The payload reads the file once, at the first poll, and keeps it in RAM: [Scrobbling](scrobble.md). Tests: `test/pod/scrobble.py` `setting_tests`. Card 2: **ListenBrainz** (a value row, the MusicBrainz mark in one colour, `pod_ci_musicbrainz`, `ACT_LB` 108, `VK_LB`: the account's user name, Not Set, Invalid Token, or nothing for a token no check has confirmed; opens the ListenBrainz page) and **Last.fm** (a value row, the Last.fm mark, `pod_ci_lastdotfm`, `ACT_LF` 113, `VK_LF`: the file's `USER`, Not Set or Sign-in Failed; opens the Last.fm page). Card 3: **Auto Upload** (a switch row, Lucide `clock`, `ACT_LBAUTO` 112, a row of `sw_tab`: `scrobble_auto_setting` / `scrobble_auto_toggle` in `patch/scrobble.c`, file `/mnt/data/m1plus/scrobble-auto`, **off by default**; one switch for both services) and **Upload Scrobbles** (an action row, Lucide `upload`, `ACT_SCROBUP` 109: the log is sent now to every service that is set up, toasts only), with the note "Uploads on Wi-Fi while music plays." Nothing is dimmed while Scrobbling is off (a log already on the card can still be uploaded). Back in front, the page refreshes its rows and the `scrobble.ini` watch (`on_page_fg` → `lb_on_front`, shared with the two account pages).

**Library > Scrobbling > ListenBrainz** (`LB_PAGE`, `m1plus_listenbrainz`) and **Library > Scrobbling > Last.fm** (`LF_PAGE`, `m1plus_lastfm`), two cards pages of the same shape: one card of one row without a glyph, **Account** (an info row, `ACT_INFO` with `INFO_LBACCT` = `INFO_DUR + 3` or `INFO_LFACCT` = `INFO_DUR + 4`: Not Set, the user name, Checking…, Invalid Token / Sign-in Failed, or empty for a ListenBrainz token no check has confirmed), and a wrapping note that says what goes into the card's file ("Put your token from listenbrainz.org in scrobble.ini on the card.", three lines of room; "Put USER, PASSWORD, API_KEY and API_SECRET under [LASTFM] in scrobble.ini on the card. Get an API key at last.fm/api.", five). The pages show the accounts and change nothing: the user writes `scrobble.ini` on the card, the accounts' only store (nothing of them is in the settings folder), and signs out by taking the lines out of it. The former Token row (`ACT_LBTOKEN` 110) and Sign Out row (`ACT_LBOUT` 111) are gone and their ids are not reused. The rows' texts are `patch/scrobpage.c`'s (`lb_*`, `lf_*`); the behaviour is in [Scrobbling](scrobble.md#settings). Tests: `test/pod/scrobpage.py`.

## Stock pages and state

Every stock row is `ACT_STOCK` (`pod_pages.STOCK_PAGES`, `POD_STOCK` in `pages.h`): `m1_open_stock(name, window)` (`patch/common.c`): stock's plain `navigator_to(name)` with no context, which is what stock's own lists do, unless a window of the page is still in the stack, which is then brought to the front (`m1_restack_window`, nothing opened). Display, Bluetooth and the stock Wi-Fi page have no `single_instance` property and bind the top-right Now Playing button (`btn_backtoplayer`), which restacks the player over the page and leaves it in the stack, so a plain `navigator_to` after that button stacks a second window of the same page; a plain Back closes the page. Stock's restack (`window_manager_switch_to` with a3 0, `0x678a04`..`0x6789f4`) sends `EVT_WINDOW_TO_BG` (0x12c) to the window it leaves and `EVT_WINDOW_TO_FG` (0x12d) to the restacked one; only a new open runs the page's init. A page that is restacked names its window, the asset's root name (`POD_STOCK.window`, `STOCK_PAGES`' third field); no row names one now (stock's Display list, `display_page`, did until our Display page took its row; `test/pod/pdtiles.py` keeps it as the model of the restack). Two pages, **Wi-Fi** and **Bluetooth**, are opened afresh (window `0`) and never restacked: **Wi-Fi** (`wifi_page`), whose init (`0x4b1048`) calls `wifi_scan` (`0x4b115c`, when Wi-Fi is on and byte `0xa062cc` is 0) on every open, while its 0x12d handler `0x4b0a34` only rebuilds the list from the old results (`0x4b0814`) and restores the timer (`0x4affac`) and its 0x12c handler `0x4afec8` clears the scan countdown byte `0xa062c8` and removes the timer, so a restacked page would not find new networks and would lose a running scan's animation; **Bluetooth**, whose init (`0x4a411c`) calls `btStartSearch` (`0x4a423c`, when Bluetooth is on) and adds the list timer, while its 0x12c handler `0x4a2a20` removes the timer and calls `btStopSearch` and its 0x12d handler `0x4a3a28` only rebuilds the list (`0x4a3734`) and restores the timer (`0x4a2b68`), so a restacked page would not discover devices again (a second Bluetooth window is stacked by the Now Playing button cycle, as in stock; the payload makes no Bluetooth call). There is no Play Mode row on our page (the mode is reached from Now Playing, the More sheet, the Queue header and All Playback Settings). Verified in the disassembly of V2.1 (`tools/pod.py SETTINGS_PINS` pins each call site's string load and the shared `jalr navigator_to`; the pages' inits read only globals, and Back is `navigator_back`, so it returns to our page). Tests: `stockopen_tests` in `test/pod/pdtiles.py`.

| Row | Page | Stock caller |
|---|---|---|
| Wi-Fi | `m1plus_wifi` (ours, [wifi](wifi.md)); `systemset/wifi_page` where ours will not open | the Wi-Fi hub's row thunk `0x4b1440` (the hub `systemset/wifiset_page` is the stock Settings' row 1; its Wi-Fi row goes straight to the list, so did ours). Our row is `ACT_STOCK` with `wifipage_open()` first; the stock hub's row has its `jalr navigator_to` at `0x4b1460` hooked (`wifi_hub_open`, [payload](payload.md) hook 21): our page, the stock page with `/mnt/mmc/m1plus-off` or where ours will not open |
| Bluetooth | `systemset/bluetooth_page` | the hub's row thunk `0x4b1410` |
| Display | `m1plus_display` ([display](display.md)); stock's `systemset/display_page` is not linked and stays under All System Settings | Settings row 3, string at `0x4ada74` (shared call `0x4ad830`) |
| Lock Screen | `m1plus_lockscreen` (ours, [lockscreen](lockscreen.md)); `systemset/screensaver_page` with the kill switch or where ours will not open | the Display page's row 2, the click handler `0x4a5c10` (case 2 at `0x4a5ca8`, redirected: [payload](payload.md) "Display page Lock Screen row"). Our Lock Screen page's last row opens our own `m1plus_lockinfo` page (stock's instructions text, `ACT_PAGE`) |
| (Language) | `systemset/language_page` | not linked from our page; stock reaches it through All System Settings |
| (System Update) | `systemset/fwupdate_page` | not linked from Developer (its row was removed); reached only through All System Settings, Settings row 1, `0x4ada38` |
| (EQ) | `playset/equalizer_page` | Play Settings row, `0x4a0218` (there is no EQ tile in the pull-down); the EQ row opens our [Equalizer](peq.md) instead, and the stock row under stock's Playback Settings list (now reached only from stock's Home grid, [playset](playset.md) "Reaching stock's list") opens our 10-Band EQ editor (`0x4a0210` redirected, [peq](peq.md) "Retiring stock's slider page"); stock's page is not linked |

The stock Settings' init sets `syssetinto_flag` (`playset_page`'s init sets `playsetinto_flag`, our `m1plus_playset_page` never does: `pd_open_settings` sets it when the tile opens our page and `pd_reconcile` derives it from either window; both are read by the pull-down: its tile visitor disables a tile and skips its click bind while the flag is positive, the tile handlers `0x4754c8` / `0x475558` do nothing for a nonzero flag, `on_wm_tsmove_fun` opens the page for a flag of 2, and the Home foreground callback `0x534b88` clears both; the payload also writes them, [pulldown](pulldown.md) "Settings tiles and the window stack"), so a sub-page opened from our page needs nothing set first. Values come from the words the stock UI reads (`DATA` in `tools/pod.py`): Wi-Fi `wififlag` (1 on; `wifi_switch` clears it and saves `[SYSSET] WIFI`), Bluetooth `bluetoothflag`, the play mode `mclGetPlayMode` 0..3 shown with the stock keys `playmode_listplay`, `playmode_repeattrack`, `playmode_shuffle`, `playmode_repeatall` (the keys the stock More dialog sets, `0x47a454..0x47a500`), EQ `equalizer_flag` (Off) or the preset's name from stock's `get_equalizer_preset_name` (`0x49daec`, a tr key `eq_*`). These are stock tr keys, so they follow Language. Nothing here toggles Wi-Fi or Bluetooth (`wifi_switch` sleeps on the UI thread): they are links. The values are read when the page opens and each time it is back in front (`EVT_WINDOW_TO_FG`, `page_refresh`).

## Buttons & Power

Settings > System > Buttons & Power (`m1plus_keyspower`, `KEYSPOWER_PAGE`, `patch/keyspower.c`, [keyspower](keyspower.md)) is a cards page built like Display: **Button Lock** (value row, picker `m1plus_keylock`) with its note, **Tap to Wake** (switch), **Auto-Standby** (switch) and **Auto-Shutdown** (value row, picker `m1plus_shutdown`) with a note that only one of the two is on. Every state is stock's own (`[SYSSET]` `LOCKFLAG`, `LOCKMODE`, `DOUBLEWAKE`, `STANDBYMODE`, `SAVEPOWERMODE`), written the way stock's own pages write it (`test/pod/keyspower.py` runs stock's handlers on the same state), nothing of ours is saved, and stock's pages under All System Settings show the same state. The page reads the words again when it opens and each time it is back in front (the Control Center key-lock tile writes the same byte). The labels are our own short texts (Tap to Wake in place of stock's long "Double Tap to Turn Screen On" / "Tap the Screen to Activate Screen", which one the device builds depends on a board strap).

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

Settings > Keyboards (`m1plus_keyboards`) lists the keyboards the on-screen keyboard ([keyboard](keyboard.md)) offers as two switch rows. **English** is always on: its switch shows on, the row is dimmed to 60 % and takes no tap (`bind_switch` sets its opacity and sensitivity, nothing is bound). **Chinese (Pinyin)** is a normal switch row (`ACT_KB_ZH`, `kb_zh_toggle`), saved atomically in `/mnt/data/m1plus/keyboard-pinyin` (off by default; the keyboard reads it each time it opens, `kb_zh_setting`). With it on the keyboard has a language key and a pinyin layer; turning it off also forgets the layer the last keyboard ended on. The three strings are in all 13 languages (`Keyboards`, `English`, `Chinese (Pinyin)`); the rows' glyphs are the Lucide `languages` (`pod_ci_languages`). More keyboards would be more rows and a bit each in the layer table of `patch/keyboard.c`.

## Settings Files

Settings > Developer > Tools > **Settings Files** (a link row, glyph Lucide `file-cog`) opens `m1plus_files`, a cards page of the Cache kind (`ACT_INFO` rows for the guard files and the folder, `ACT_SFDEL` rows for the setting files, `INFO_SF + k`, values from `setfiles_stat`, `patch/setfiles.c`). It shows the payload's own files as raw values: the labels are the file names themselves (identifiers, untranslated; only the title is translated). Card 1: the guard files in `/mnt/data` (`m1plus-start` the character, `m1plus-run`, `m1plus-bad`, `m1plus-off` present or missing). Card 2: `m1plus/` (the settings folder: present or missing), then one row per file in it (the Albums, Playlists and Recently Added views among them): a single-character setting shows its character (`appearance-accent`, `appearance-background` and `radio-view` among them; `other` for anything longer, `empty`), `home-menu` and `pulldown-tiles` their first 12 characters (an ellipsis after), `playback-eq` (the Equalizer's state record, binary) present or missing, `search-history` its number of lines, `covers-rebuild` and `artists-rebuild` (the rebuild requests, [Rebuild rows](#rebuild-rows)) present or missing; a file that is not there reads `missing`. Everything is read once by `setfiles_open` as the page opens (open, read, close, access); a refresh on coming back to the page shows those values again and reads nothing, no timer. The ListenBrainz account has no row: it is not in this folder but in `scrobble.ini` on the card ([Scrobbling](scrobble.md#the-accounts-file)).

Delete: only the setting-file rows are tappable (`ACT_SFDEL`, arg `INFO_SF + k`; no glyph or chevron, otherwise like an info row), and only while their file is there (`setfiles_present`); a missing one is insensitive. A tap asks "Delete this settings file?" Yes calls `setfiles_delete`, which unlinks that one file (a file already gone counts as deleted), reads only that row again and refreshes the page: the row reads `missing` and takes no tap; the toast "Settings file deleted". If the file is still there after the unlink, the toast is "Storage unavailable". The guard files and the `m1plus/` folder rows stay information rows and `setfiles_delete` refuses them. A value the running player already holds in memory keeps it until the setting is read again or the device restarts. Reset All Settings does not touch the ListenBrainz account (the card's `scrobble.ini`). The page has 42 setting-file rows (`INFO_SF + 5` to `INFO_SF + 46`, `scrobble-auto` after `scrobbling`; `INFO_SFOLD` = `INFO_SF + 47`, `INFO_DUR` 63). No hook or pin. Tests: `files_tests` in `test/pod/homecover.py`.

**Unsupported Files** is the last card: a count row (`ACT_SFOLD`, `INFO_SFOLD`, the number of retired files there) with a chevron and a tap only while the count is not zero, and **Delete Unsupported Files** (`ACT_SFDELALL`, trash glyph). The retired files are the settings files of older builds that nothing reads any more: the fixed table `sf_retired` in `patch/setfiles.c` (mirrored as `RETIRED_FILES` in `tools/pod_pages.py`), each name with its `.tmp` sibling, `m1plus/recently-played` among them. Not in the table: the guard files and the current settings. `scrobbling` and `appearance-light` appear in no source under `patch/`, so no entry names them. A setting renamed later gets its old name added to the table, not a migration. The table is checked with `access()` once as the page opens and the result is kept in memory, so the count and the list read nothing; a delete checks again. The tap opens the plain list (`covlist_open(2)`, `patch/covlist.c`): one row per file that is there, in table order, its name and under it its folder. A tap on a row asks "Delete this unsupported file?", deletes that file and takes its row away; the last one shows "No unsupported files". Delete Unsupported Files asks "Delete all unsupported files?", unlinks every entry, recounts, refreshes the page and toasts "Unsupported files deleted" (or "Storage unavailable" when one remains); with no file it toasts "No unsupported files" and asks nothing. Tests: `unsupported_tests` in `test/pod/homecover.py`, which also checks the table against `RETIRED_FILES` and that no other source names these paths.

### Reset All Settings

Settings > Developer > Reset > **Reset All Settings** (`ACT_RESETALL` 54, glyph `rotate-ccw`, the Reset card's only row) asks "Reset all settings to their defaults?" in the same confirm dialog; No does nothing. Yes calls `setfiles_reset_all` (`patch/setfiles.c`): it unlinks every entry of `/mnt/data/m1plus/` except `.` and `..` (unknown names and `.tmp` leftovers too; no recursion; the folder itself stays; at most 256 entries), then every retired entry of Unsupported Files. A missing folder is nothing to do. The toast "Settings reset. Restart to apply." shows on success, "Storage unavailable" when an entry remains, when the folder exists but cannot be opened, or when a re-read after the unlinks still finds an entry (readdir may have stopped early). It is kept: the guard files in `/mnt/data` (`m1plus-start`, `m1plus-run`, `m1plus-bad`, `m1plus-off`, the boot guard's own), and everything under `/mnt/mmc` (cover cache, track durations, Cover Flow position), which have their own clear rows. Nothing reboots or re-applies live: values the running player holds in memory keep until the device restarts. Tests: `reset_tests` in `test/pod/homecover.py`.

## Wrapping notes

A `Note` with `lines > 1` is built as a plain (wrapping-capable) label, not an hscroll_label, and AWTK wraps only after `label_set_line_wrap`. `tools/pod.py` writes each page's `Page.wrap_notes()` (bit n: the page's nth Note, `pod_note<n>_t` in layout order, has `lines > 1`) as the `wrap_notes` field of `POD_PAGES`, and `open_page` in `patch/m1plus.c` turns the wrap on for those labels as any page opens: no page index or note number is hardcoded (Library's Volume Buttons note, the Equalizer page's hint, the preset page's skipped-lines note, the Preamp page's note). `test/pod/i18n.py` checks that every such note wraps within its `lines` in all 13 languages.
