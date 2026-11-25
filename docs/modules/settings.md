# Settings and launcher

**Sources:** `patch/m1plus.c`, `patch/home.c`, `patch/setfiles.c`, `patch/keyspower.c`,
`patch/datetime.c`, `patch/playset.c`, `patch/battery.c`, `patch/pcregion.c`, `tools/pod_settings.py`,
`tools/pod_ui.py`, `tools/pod_pages.py`. User instructions are in
the [settings guide](../settings-guide.md).

Settings is main-menu item 18 (`j`), hidden by default. The Extras navbar always reaches it and it cannot
be turned off. It is an iOS-style page of grouped cards. This doc owns the page tree, the card layout, the
settings-file table and the stock pages we open; a page with its own doc is a pointer row.

## Page tree

| Group | Row | Opens | Doc |
|---|---|---|---|
| top | Wi-Fi | our Wi-Fi page | [wifi](wifi.md) |
| | Bluetooth | our Bluetooth page | [bluetooth](bluetooth.md) |
| | Network Services | AirPlay and DLNA switches, SyncLink, Wi-Fi Transfer; stock's page stays under All System Settings | [wifi-transfer](wifi-transfer.md) |
| | Home Screen | Recent Albums, Daily Mix, Main Menu / Extras, Regenerate Daily Mix | [dailymix](dailymix.md), [menu](menu.md) |
| | Library | [Update Library](libupdate.md), Rebuild rows, Split Artists, Split Genres, List Navigation, Folders, Cover Flow, Podcasts, Scrobbling | [albums](albums.md), [podcasts](podcasts.md), [scrobble](scrobble.md) |
| | Now Playing | Cassette Theme, Lyrics Text Size, Idle Display, Track Position, Shrink on Pause | [tape](tape.md), [bigcover](bigcover.md) |
| **Playback** | EQ | our Equalizer page | [peq](peq.md) |
| | Playback Settings | our hub `m1plus_playset` (modes) with sub-pages `m1plus_psvolume` (Volume & Sound) and `m1plus_psoutput` (Output) | [playset](playset.md), [crossfade](crossfade.md), [nextalbum](nextalbum.md) |
| (card) | General | About, Software Update; Date & Time, Keyboards, Language | [General](#general) |
| | Display | our page | [display](display.md) |
| | Buttons & Power | our page | [keyspower](keyspower.md) |
| | Appearance | Background, Accent, Control Center, Control Labels | [accent](accent.md), [pulldown](pulldown.md) |
| | Battery | Battery Percentage, Charge Limit, Battery History | [battery](battery.md), [charging](charging.md) |
| General | Software Update | our page `m1plus_update` (link row, glyph `download`) | [update](update.md) |
| | Date & Time | Set Automatically, Time Zone (43 zones), Date and Time, 24-Hour Time | [datetime](datetime.md) |
| | Keyboards | three switch rows | [Keyboards](#keyboards) |
| | Language | value row (the language's own name), our picker | [language](language.md) |
| | About | our page | [About](#about) |
| (last card) | All System Settings | stock's list (its Theme row is removed), the fallback to every stock page, incl. Firmware Update, Regulatory, Format Storage and Reset | [theme](theme.md) |
| **Developer** | Startup | Boot to M1+ Music, Open Shanling Home | [home guard](home-guard.md) |
| | Tools | Screenshot, Cache, Settings Files, Card Script | [screenshot](screenshot.md), [Cache](#cache), [Settings Files](#settings-files), [Card Script](cardrun.md#developer-page) |
| | Reset | Reset All Settings | [Reset All Settings](#reset-all-settings) |

## Cards

The design is `tools/preview/preview_settings.py` (it draws the built tree's own assets). The numbers are
in `tools/pod_settings.py`, shared by `tools/pod_ui.py build_cards_page`, the preview and the tests. A
page is a `Page(layout=[Row, Hdr, Note, GAP ...])` in `tools/pod_pages.py` of kind `cards`.

- The list is the stock `list_view` > `scroll_view` (310 wide) + `scroll_bar_m`; rows are stock
  `list_item`s.
- **The layouter stacks the children.** Stock's `list_view` layouter ignores a child's `y`: it puts every
  visible child at the running y in child order and sums the heights into `virtual_h`. So a page is only a
  column of full-width items in display order: a 10 px spacer (`pod_top`), the rows, headers
  (`pod_sec<n>`, 40), notes (`pod_note<n>`, 34), gaps (`pod_gap<n>`, 20) and a 10 px spacer (`pod_end`).
  Nothing relies on an asset's own x, y or width.
- **A card is drawn by its rows.** Each row's background is a picture piece, `pod_cd_single`, `_top`,
  `_mid` or `_bot` (320 x 52): the card (x 10..310, `#1C1C1E`, radius 12 on the corners the piece has) is
  baked in and the rest is transparent. `pod_cd_<piece>_down` is the pressed grey `#2C2C2E`. A piece
  depends only on the rows around it in the layout, so a hidden neighbour never breaks a card.
- Row children are row-relative: glyph at x 22, label at 58 (24 without glyph), a `#333333` hairline from
  the label to x 310 on every row but a card's last.
- **Right side, by ink:**

  | Kind | Look |
  |---|---|
  | link | chevron `pod_chev` (10 x 16, `#8A8A8A`) at x 288, label ending at 278 |
  | value | grey `#AAAAAA` 18 px text 8 px left of the chevron; the payload sizes it and gives the label the rest (`value_fit`) |
  | switch | stock `sset_on` / `sset_off` image |
  | picker row | no glyph; a check on the chosen row |
  | action | nothing (Update Library, Regenerate Daily Mix, Rebuild rows, Open Shanling Home, Screenshot) |

  `pod_pages.row_kind` says which a row is.
- **Headers and notes.** Headers are `#AAAAAA` 18 px, notes 15 px. Their grey label box starts at x 21 and
  the text ink at x 24, flush with the row glyphs' ink. The Now Playing navbar button is `ah_nav_np`; the
  navbar fade stays hidden because the first card sits 10 px under the bar.
- **Hidden** is `visible=false` and `sensitive=false` (the layouter then skips the item). Headers, notes,
  spacers, glyphs and accessories are never sensitive.
- **Wrapping notes.** A `Note` with `lines > 1`, a centred note or a `Hero` description is a plain label
  and wraps only after `label_set_line_wrap`. `tools/pod.py` writes `Page.wrap_notes()` as the page's
  `wrap_notes` field and `open_page` turns the wrap on, so no page or note number is hardcoded. Five layout
  items serve the Wi-Fi Transfer page ([wifi-transfer](wifi-transfer.md)): `Hero(glyph, title, text)` (a
  rounded tile with a white glyph, a 22 px title and a wrapping 14 px grey description, all centred),
  `QrCard(hero)` (a hidden view as high as the hero, placed at its y and adding no height: the payload shows
  one of the two), `BigCard()` (one tall card with a large centred label the payload fills),
  `Note(center=True)` (a centred wrapping footer at the note size) and `QrPill(text)` (a small flat pill the
  payload sizes to its label).

## Page notes

- **Home Screen.** The Recent Albums and Daily Mix switches (note "Shown on Home below the menu"), then
  Main Menu and Extras links, then **Regenerate Daily Mix** in a card of its own. It requests a new seed
  (toast "New mix when Home opens"; Home rebuilds when next foregrounded). The row and its note are hidden
  (`regen_show`) while no mix can be made: Daily Mix off, or a library under `MIX_MIN_LIB`. Shelf and mix
  visibility are reread when returning to Home.
- **Battery.** First row **Battery Percentage** (switch, off by default, `battpct_toggle`), note "The exact
  charge beside the battery icon". The status bar reads the payload's cached flag ([battery](battery.md)).
  Then Charge Limit ([charging](charging.md)).
  Then **Battery History**, a value row (On or Off, chevron; `ACT_BHPAGE`) like Charge Limit, opening its own page: the
  switch (`ACT_BATTHIST`, `bh_toggle`), its note (two items, one per state) and, while it is on, the card and
  the charts ([batthist](batthist.md) "History page": hidden items the payload shows, names `pod_sec0..2`,
  `pod_note0..3`, `pod_hist0..2`).
- **Library.**
  - Update Library (our page, a link row: [libupdate](libupdate.md)), then **Rebuild Covers** and **Rebuild Artist Photos**
    ([Rebuild rows](#rebuild-rows)).
  - **Tags:** one card of two value rows, **Split Artists** and **Split Genres** (On / Off), each opening
    its page (below).
  - **List Navigation:** **Index Rail** and **Section Headers** switches, note "Songs, Artists, Albums and
    Radio lists" ([songs](songs.md), [artists](artists.md)).
  - **Cover Flow:** Landscape and **Volume Buttons** (`coverflow_volkeys`; two-line note "In Cover Flow,
    the volume buttons move between albums.").
  - Last card: **Podcasts** (link row, no value) and **Scrobbling** (value row On / Off, opens
    [scrobble](scrobble.md#settings)).
  - The album order is set on the Albums "..." card ([albums](albums.md)), not here.
- **Library > Podcasts** (`m1plus_podcastsettings`): Podcast Discover switch (on by default; off hides the
  Discover row and the search level), Podcast Directory (Apple Podcasts or Podcast Index) and Podcast
  Region (Automatic and 34 storefronts; serves Discover's charts, which are always Apple's, and the Apple
  search, not Podcast Index) with the note
  "Search words go to the chosen directory." Directory and Region are dimmed and take no tap while Discover
  is off. Details: [podcasts](podcasts.md#settings-rows).
- **Library > Split Artists** (`m1plus_artistsplit`, ACT 172..): the **Split Artists** switch (off by
  default), a **Separators** header and ten switch rows `;` `/` `&` `,` `feat.` `vs.` `x` `+` `with` `and`
  (ACT 174 + k for `M1_SPLIT_*` bit k; labels are the separators, untranslated; default on for `;` `/`
  `&` `feat.`), and a wrapping note ("A track tagged A & B or A feat. B appears under each name in
  Artists. Names in artist-exceptions.txt on the card are never split."). While the switch is off the ten
  rows are dimmed and insensitive. A toggle saves first and changes only when the save worked. The file
  stores the mask even when off, so the separators survive off / on; turning the last separator off while on
  leaves the switch on and splits nothing. Artists, Search and Now Playing read the setting when they open,
  so an already open Artists page keeps its rows. Rules: [artists](artists.md).
- **Library > Split Genres** (`m1plus_genresplit`, last in `PAGE_ORDER`, ACT 197..): the same page for the
  Genres list: the **Split Genres** switch (ACT 198, off by default), **Separators** and five switch rows
  `;` `/` `&` `,` `+` (ACT 199 + k for bit k: 0-3 and 7; **default on for `;` alone**), and the note "A track tagged Rock; Pop appears under each
  name in Genres. Names in genre-exceptions.txt on the card are never split." Dimming, saving and the
  mask kept when off are as for Split Artists. Rules: [artists](artists.md#split-genres).
- **Library > Scrobbling** and its ListenBrainz and Last.fm pages: [scrobble](scrobble.md#settings).
  The account pages are read-only; the accounts live in `scrobble.ini` on the card, not in the settings
  folder.
- **Now Playing.** Under the Cassette Mode header, **Theme** (Normal / Chrome / Metal / Auto, picker with
  the note "Applies the next time Cassette Mode opens"; [tape](tape.md)). Then **Lyrics Text Size**
  (Small / Medium / Large; [lyrics](lyrics.md)) and last **Idle Display** (Off, Album Cover, Cassette,
  Vinyl or Lyrics; note "Shown after 10 seconds on Now Playing."; [bigcover](bigcover.md)). The last
  card is the **Track Position** switch (note "Shows the queue position, such as 5/10, between the times."; [nowplaying](nowplaying.md)), then the **Shrink on Pause** switch (on by default; note "The cover shrinks while paused and grows back when playing.").
- **Display, Buttons & Power, Sleep Timer, Language, Equalizer.** Own docs: [display](display.md),
  [keyspower](keyspower.md), [sleeptimer](sleeptimer.md), [language](language.md), [peq](peq.md). Each reads
  stock's state when it opens and each time it is back in front; nothing of ours is saved. The Sleep Timer
  page is not a Settings row: Now Playing's More sheet and the Control Center tile open it.

## Persisted choices

- Switches and pickers save before they update their image or check; a failed save changes neither the
  file nor the displayed state. Reading settings never writes them.
- One reader serves every one-character file below: `set_read(path, default)` (`patch/home.c`) returns the
  character of a file that is exactly `x` or `x\n`, and the default for a missing file, an empty one or
  anything longer. The values in the table are those characters. `home-menu`, `pulldown-tiles`,
  `search-history` and the boot guard's `m1plus-start` have their own parsers.
- Feature settings live in `/mnt/data/m1plus/` (`SET_DIR`). `home_write_atomic` makes the folder when a
  write finds it missing and fsyncs it after the rename.
- The boot guard's files stay directly in `/mnt/data/` (`m1plus-start`, `m1plus-run`, `m1plus-bad`,
  `m1plus-off`; [home guard](home-guard.md)), so the guard's crash path never depends on the folder.

**Our files under `/mnt/data/m1plus/`**, by file name. Every one is listed on Settings Files.

| File | Setting | Values / default |
|---|---|---|
| `albums-sort` | Albums order | one character: `0` Title, `1` Artist, `2` Recently Added, `3` Year, or `a` .. `d` for the same order reversed; missing/other Artist, not reversed ([albums](albums.md#album-order-and-initial-selection)) |
| `albums-view` | Albums view | `0` list; missing/other grid |
| `appearance-accent` | Accent | one digit, the index 0 Neutral (default) .. 6 Champagne; missing/other Neutral ([accent](accent.md)) |
| `appearance-background` | Background | `0` Black (default), `1` Tinted; missing/other Black ([accent](accent.md)) |
| `appearance-headers` | Section Headers | `0` off; missing/other on (the default); the section letters and pinned header of the A-Z lists, the rows close up when off |
| `appearance-index-rail` | Index Rail | `0` off; missing/other on (the default) ([artists](artists.md)) |
| `artists-rebuild` | Rebuild Artist Photos request | exists while requested; written as `1\n`; removed by Home's pass ([homecover](homecover.md#rebuild-covers), [artists](artists.md)) |
| `artists-sort`, `genres-sort`, `composers-sort` | Artists / Genres / Composers order | one character per page: `a` Name Z-A; missing/other Name A-Z ([artists](artists.md)) |
| `battery-charge-limit` | Charge Limit | `0` 80 %, `1` 85 %, `2` 90 %, `3` 95 %; missing/other 100 %, no limit (the default) ([charging](charging.md)) |
| `battery-history` | Battery History | `1` on; missing/other off (the default); the data file `battery-history.bin` (820 bytes) is deleted when it goes off ([batthist](batthist.md)) |
| `battery-percentage` | Battery Percentage | `1` on; missing/other off (the default) ([battery](battery.md)) |
| `cassette-theme` | Cassette Theme | `0` Normal, `1` Chrome, `2` Metal, `3` Auto (by the track's quality); missing/other Auto (the default) ([tape](tape.md)) |
| `covers-rebuild` | Rebuild Covers request | exists while requested; written as `1\n`; removed when Home's cover build completes ([homecover](homecover.md#rebuild-covers)) |
| `coverflow-landscape` | Cover Flow Landscape | `1` landscape; missing/other portrait ([coverflow](coverflow.md)) |
| `coverflow-volume-keys` | Cover Flow Volume Buttons | `1` the volume buttons step Cover Flow; missing/other off (the default) ([coverflow](coverflow.md) "Volume buttons") |
| `folders-sort` | Folders order | `0` Name, `1` Date Modified, `2` Type, or `a` `b` `c` for the same order reversed; missing/other Name A-Z; one order for every level ([folders](folders.md)) |
| `home-daily-mix` | Daily Mix | `0` off; missing/other on ([dailymix](dailymix.md)) |
| `home-menu` | Main Menu / Extras | item ids in order, optional `-` then the hidden ids; invalid = defaults ([menu](menu.md)) |
| `buttons-swap` | Swap Prev / Next | `1` on; missing/other off (the default) ([keyspower](keyspower.md) "Swap Prev / Next") |
| `volume-tap` | Tap for Volume | `0` off; missing/other on ([volume](volume.md) "Entry") |
| `home-recent-albums` | Recent Albums | `0` off; missing/other on |
| `keyboard-pinyin` | Chinese (Pinyin) keyboard | `1` on; missing/other off ([keyboard](keyboard.md)) |
| `keyboard-french` | French (AZERTY) keyboard | `1` on; missing/other off ([keyboard](keyboard.md)) |
| `keyboard-english` | English keyboard | `0` off; missing/other on ([keyboard](keyboard.md)) |
| `keyboard-last` | The layer the language key last chose | `0` English, `1` Chinese, `2` French; missing/other: the first keyboard on ([keyboard](keyboard.md)) |
| `library-genre-split` | Split Genres | The same format as `library-artist-split`; `1` is on with the semicolon alone ([artists](artists.md) "Split Genres") |
| `library-artist-split` | Split Artists | `0` or missing: off (the default); `1`: on with the default separators (`;` `/` `&` `feat.`); `m<decimal>`: on with that `M1_SPLIT_*` mask (bit k = the k-th separator of the page; `m0`: on, splits nothing); `o<decimal>`: off, keeping that mask (the page writes `m<mask>` and `o<mask>`, so the separators survive an off / on); anything else off ([artists](artists.md) "Split index") |
| `lockscreen-layout` | Lock Screen > Player Style | `1` Mini Player; missing/other Large Cover (the default); applies the next time the lock screen opens ([lockscreen](lockscreen.md)) |
| `nowplaying-idle` | Idle Display | `1` Cassette, `2` Vinyl, `3` Lyrics; missing/other Album Cover (Off is stock's Cover mode byte) ([bigcover](bigcover.md) "Idle view") |
| `nowplaying-position` | Track Position | `1` on; missing/other off (the default) ([nowplaying](nowplaying.md) "Track position") |
| `nowplaying-shrink` | Shrink on Pause | `0` off (the cover stays full size); missing/other on (the default) ([nowplaying](nowplaying.md) "Paused cover") |
| `nowplaying-lyrics-size` | Lyrics Text Size | `0` Small (22 px), `1` Medium (26), `2` Large (30); missing/other Large (the default) ([lyrics](lyrics.md) "Text size") |
| `playback-eq` | Equalizer curve | the `M1PEQ03` record ([peq](peq.md)); missing/invalid: 10-Band EQ, Flat, Auto. The switch is stock's `[PLAYSET] EQFLAG`. Per output ([peq](peq.md#per-output-eq-patchpeqoutc)): `playback-eq-headphones`, `-lineout`, `-usb` (the same record) and `playback-eq-output` (the owner and each output's switch) |
| `playback-mono` | Playback Settings > Mono Audio | `1` on; missing/other off ([stereo](stereo.md)) |
| `playback-crossfeed` | Playback Settings > Crossfeed | `0` Off .. `3` High; missing/other off (the user's level; the player reads `playback-stereo`, the effective record, which is derived and not listed) |
| `playback-crossfade` | Playback Settings > Crossfade | one character: `a`..`l` on with 1..12 s, `A`..`L` off with the duration kept; missing/other off, 5 s ([crossfade](crossfade.md)) |
| `playback-crossfade-auto` | Crossfade > Keep Albums Gapless | `0` Always; missing/other `1` Keep Albums Gapless (default) ([crossfade](crossfade.md)) |
| `playback-next-album` | Continue Playing | `1` Next Albums; missing/other Off (the default); `2` reserved for Auto Mix ([nextalbum](nextalbum.md)) |
| `playback-shuffle` | Shuffle (the payload's flag; stock's mode is never 2) | `1` songs, `2` albums; missing/other off ([shuffle](shuffle.md)) |
| `playlists-sort` | Playlists order | `a` Name Z-A; missing/other Name A-Z ([playlists](playlists.md)) |
| `playlists-view` | Playlists view | `0` list; missing/other grid |
| `pod-appearance` | Pod Appearance | `1` Dark; missing/other Light |
| `podcast-online-search` | Podcast Discover | `0` off; missing/other on (the default); gates Discover and the search level ([podcasts](podcasts.md)) |
| `podcast-directory` | Podcast Directory | `1` Podcast Index; missing/other Apple Podcasts (the default); where the search and the id lookup go ([podcasts](podcasts.md) "Podcast Directory") |
| `podcast-region` | Podcast Region | the storefront's two capital letters and a line feed (one of the 34 in `tools/pcregion.py`); missing/other Automatic ([podcasts](podcasts.md) "Region") |
| `pulldown-labels` | Control Labels | `0` hides the Control Center tile captions; missing/other shown (the default) ([pulldown](pulldown.md)) |
| `pulldown-tiles` | Control Center | tile ids `0`-`9`, `a` and `b` in order (at most eight), optional `-` then the hidden ids; invalid = the eight stock tiles in stock order ([pulldown](pulldown.md)) |
| `radio-recent` | Recent radio stations | an `.m3u` of up to 10 stations, newest first ([radio](radio.md)) |
| `radio-view` | Radio station lists view | `1` grid; missing/other list ([radio](radio.md)) |
| `recently-added-view` | Recently Added view | `1` albums grid; missing/other songs ([recent-albums](recent-albums.md)) |
| `scrobble-auto` | Auto Upload | `1` on; missing/other off (the default; read once, by the first status bar tick) ([Scrobbling](scrobble.md#automatic-upload)) |
| `scrobbling` | Scrobbling | `1` on; missing/other off (the default; read once by the first poll) ([Scrobbling](scrobble.md)) |
| `search-history` | Recent searches | up to 5 UTF-8 lines, newest first; malformed = none ([search](search.md)) |
| `songs-sort-rev` | Songs direction | `a` Title / File Name / Format run Z-A; missing/other A-Z; ignored for Recently Added, whose direction is the stock `sort_flag` 3 / 4 ([songs](songs.md)) |
| `vinyl-base` | Vinyl Base | `1` Snow; missing/other Graphite ([vinyl](vinyl.md)) |
| `vinyl-record` | Vinyl Record | `1` Cover; missing/other Black ([vinyl](vinyl.md)) |
| `wifi-networks` | Saved Wi-Fi networks stock cannot read | `network={}` blocks (WPA3, Enhanced Open, Enterprise) the Wi-Fi page writes and `wifi_connect.sh` adds to the copy only the newer supplicant reads; holds passwords; deleting it (or Reset All Settings) forgets those networks only ([wifi](wifi.md)) |

A leftover `album-order` file (`0` Title, else Artist) is moved into `albums-sort` once, when that file is
missing, and then deleted (`cc_sort_mode` runs `sort_migrate` in `patch/covercache.c`; [albums](albums.md)); Reset All Settings removes a leftover.

**Stock state we read and write** (no file of ours): stock's `[SYSSET]` words and bytes, read when the
page opens and written the way stock's handlers write them.

| Setting | Stock key | Values |
|---|---|---|
| Lock Screen > Enable | `[SYSSET] SCREENSAVER` (the byte `screensaver_mode`) | 1 on (stock's default), 0 never shows the lock screen; the same switch as stock's Lock Screen page ([lockscreen](lockscreen.md)) |
| Lock Screen > Wallpaper | `[SYSSET] SCREENSAVERPATH` (the global `screensaver_picture`) | `screensaver_default` or the path of one of the up to five 320 x 480 pictures in `/mnt/mmc/lockscreenimage`; the same choice as stock's Lock Screen page ([lockscreen](lockscreen.md) "Wallpaper picker") |
| Lock Screen > Show Time | `[SYSSET] SSAVERTIMESHOW` (the byte `screensaver_timeshow`) | 1 shows the clock and date (stock's default), 0 hides them ([lockscreen](lockscreen.md)) |
| Display > brightness slider | `[SYSSET] LIGHTNESS` (the word `lightness`) | 0 .. 100, written by stock's own slider handlers ([display](display.md)) |
| Display > Screen Timeout | `[SYSSET] LIGHTTIME` (the word `backlighttime_mode`) | 0 never, 1 15 s, 2 30 s, 3 1 min, 4 5 min ([display](display.md)) |
| Display > LED Light | `[SYSSET] ATMOSPHERELEDMODE` (the byte `atmosphereled_mode`) | 0 off, 1 green, 2 blue ([display](display.md)) |
| Display > LED Light > Dynamic, and its theme | `/mnt/data/m1plus/led-dynamic` | `0` or missing: off; `1` .. `6`: on (stock's lamp mode is then 0) with the theme Reference, Gentle Breathe, Heartbeat, Lighthouse, Candle or Wave ([display](display.md) "Sample Rate") |
| Display > LED Light > Follow Screen | `[SYSSET] LEDFOLLOWSCREEN` (the byte `ledfollowscreen_flag`) | 1 on, 0 off ([display](display.md)) |
| Display > Screen Rotation | `[SYSSET] ROTATEMODE` (the word `rotate_mode`) | 0 = 0 degrees, 1 = 180 degrees ([display](display.md) "Screen Rotation") |
| Buttons & Power > Car Mode | `[SYSSET] CARMODE` (the byte `car_mode`) | 1 on, 0 off ([keyspower](keyspower.md) "Car Mode") |

## Files on the card

Everything the payload keeps on the SD card (`grep -rnE 'CARD_DIR|"/mnt/mmc/' patch/*.h patch/*.c`).
`/mnt/mmc/.m1plus/` is `CARD_DIR`; writers make it only while the card is mounted. Reset All Settings
touches none of these.

| Path | Owner | Doc |
|---|---|---|
| `.m1plus/covers/` | Home's cover cache (`r<key>-168.jpg`, empty no-art markers) | [homecover](homecover.md) |
| `.m1plus/cache-stamp` | cover cache stamp (patch/homecover.c) | [homecover](homecover.md) |
| `.m1plus/scrobble-uploads` | one line for each upload that sent a request, about 8 KB kept (patch/scrobup.c) | [scrobble](scrobble.md#upload-record) |
| `.m1plus/artists/` | artist photo cache (`a<key>-44.jpg`, `-168.jpg`, `.pick`) | [artists](artists.md) |
| `.m1plus/durations` | measured track durations (patch/durations.c) | [album-page](album-page.md#album-length) |
| `.m1plus/recently-played` | Home's Recently Played albums (patch/recent.c) | [recent](recent.md) |
| `.m1plus/home-pins` | the Home pins (patch/pins.c) | [pins](pins.md) |
| `.m1plus/coverflow-position` | the Cover Flow position (patch/coverflow.c) | [coverflow](coverflow.md) |
| `.m1plus/daily-mix/` | Daily Mix tracks and art | [dailymix](dailymix.md) |
| `.m1plus/podcasts/` | `resume`, `speed`, `order`, `search/` (thumbnails) | [podcasts](podcasts.md) |
| `.m1plus/audiobooks/search/` | LibriVox scratch: thumbnails `p<i>` / `s<i>`, `preview.jpg\|png`, `files.json` while it is scanned | [audiobooks](audiobooks.md) |
| `Audiobooks/<book>/.librivox` | a downloaded LibriVox book's manifest (the parts still to fetch); the parts and `cover.jpg` sit beside it | [audiobooks](audiobooks.md) |
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
| `boot-logo.jpg` | the boot logo, imported at boot into `/mnt/data/m1plus/boot-logo*.jpg` | [boot](boot.md#card-logo) |

## Cache

Settings > Developer > Tools > **Cache** opens `m1plus_cache`, a read-only cards page of the About kind
with the cover, artist photo and track duration counts and the Clear Cover Cache and Clear Track
Durations rows ([homecover](homecover.md#cache-page)).

## Rebuild rows

**Rebuild Covers** and **Rebuild Artist Photos** are action rows in Library. Each asks in the stock confirm
dialog ([overlays](overlays.md)); only Yes writes its request file (`covers-rebuild` or `artists-rebuild`)
with `home_write_atomic` and shows a toast. Home's background pass does the rest
([homecover](homecover.md#rebuild-covers), [artists](artists.md)). The two requests are independent.

## Stock pages and state

Every stock row is `ACT_STOCK` (`pod_pages.STOCK_PAGES`): `m1_open_stock(name, window)` is stock's plain
`navigator_to(name)` with no context, unless a window of the page is still in the stack, which is then
brought to the front. Back is `navigator_back` and returns to our page. `tools/pod.py` `SETTINGS_PINS`
pins each call site; `STOCKROWS_PINS` in `tools/pod_pins.py` pins the direct rows.

- **Restack.** The Now Playing button restacks the player over a page and leaves it in the stack, so a
  plain `navigator_to` afterwards would stack a second window. Stock's restack sends `EVT_WINDOW_TO_BG` to
  the window it leaves and `EVT_WINDOW_TO_FG` to the restacked one; only a new open runs the page's init.
  A page that is restacked names its window (the third field of `STOCK_PAGES`); the two pages with no
  window events do (USB Mode, SyncLink).
- **Wi-Fi and Bluetooth are opened afresh, never restacked.** Their inits start the scan and the list
  timer, and their to-background handlers stop them, so a restacked page would find nothing new.
  Our own pages for both do the same work ([wifi](wifi.md), [bluetooth](bluetooth.md)).
- There is no Play Mode row on our page; the mode is reached from Now Playing, the More sheet, the Queue
  header and All Playback Settings.
- The stock Settings init sets `syssetinto_flag` (and `playsetinto_flag` for Playback Settings), which the
  pull-down reads. Our Playback Settings page never sets its flag; the payload sets and derives both for
  the pull-down ([pulldown](pulldown.md#settings-tiles-and-the-window-stack)), so a sub-page opened from
  our page needs nothing set first.
- Values come from the words the stock UI reads: Wi-Fi `wififlag`, Bluetooth `bluetoothflag`, EQ
  `equalizer_flag` or the preset's tr key. They are stock tr keys, so they follow Language. Nothing here
  toggles Wi-Fi or Bluetooth (`wifi_switch` sleeps on the UI thread): the rows are links.

| Row | Opens |
|---|---|
| Wi-Fi | [our page](wifi.md); `systemset/wifi_page` where ours will not open or with the kill switch (hub row: hook 21) |
| Bluetooth | [our page](bluetooth.md); `systemset/bluetooth_page` likewise (hub row: hook 32) |
| Display | `m1plus_display` ([display](display.md)); stock's page stays under All System Settings |
| Lock Screen | `m1plus_lockscreen` ([lockscreen](lockscreen.md)); `systemset/screensaver_page` with the kill switch or where ours will not open (hook: [payload](payload.md)). Its last row opens our `m1plus_lockinfo` instructions page |
| Language | our picker; stock's `language_page` shows the same word |
| Firmware Update | not linked: stock's TF-card update page stays under All System Settings (our online update is General > Software Update) |
| Power | not linked: the Sleep Timer page is ours ([sleeptimer](sleeptimer.md)); stock's shows the same state |
| EQ | our [Equalizer](peq.md); stock's Playback Settings EQ row opens our 10-Band editor |

## General

Settings > General (`m1plus_general`) is two cards of our pages: **About** and **Software Update** (a
chevron row with the `download` glyph); **Date & Time**, **Keyboards**, **Language**. **All System
Settings** (stock's whole list, the fallback to every stock page) is on the Settings root, in the last
card above Developer. Firmware Update, Regulatory, Format Storage and Reset are reachable only through it:
they are rarely used, and Software Update gets the top-level spot next to About.

- **USB Mode and SyncLink** are direct rows on other pages: USB Mode above USB Volume on
  Playback Settings, SyncLink the first row of Network Services'
  second card ([wifi-transfer](wifi-transfer.md)).
- **Labels:** USB Mode and SyncLink use stock's words.
- **Rows** are `ACT_STOCK` (a plain `navigator_to`, nothing saved):

  | Row | Opens |
  |---|---|
  | USB Mode | `systemset/usbset_page` (USB Storage / DAC / Audio) |
  | SyncLink | `systemset/synclink_page` |

## About

Settings > General > About (`m1plus_about`) is our cards page of the stock About page's seven values, plus
the build tag. Stock's page stays under All System Settings.

- Rows are `ACT_INFO`: a label and a grey 16 px value at the right (`value_fit`, at most 190 px), no
  chevron, no glyph, insensitive. Read-only, on the UI thread when the page opens and when it is back in
  front. No hook, no query, no write.
- No live row: Software Update is on General ([update](update.md)).
- Sections: **M1+ Music** (the build tag) and **Firmware**; **Device**: Model, Serial Number, Wi-Fi MAC,
  IP Address; **Storage**: Capacity, Available. An empty value reads "-". Library counts are not shown
  (they would need a query).
- Sources, read the way stock's widget walk reads them:

  | Row | Source |
  |---|---|
  | Model, Firmware | stock's literals (Firmware is never patched; only the updater's compare is repointed, [version](version.md)) |
  | Capacity, Available | `getDiskMemoryInfo("/mnt/mmc", ...)` (a `statfs`, in G), shown as `N.NN GB` made with integers |
  | Wi-Fi MAC, Serial Number | the strings `wifi_mac`, `product_sncode` |
  | IP Address | `networkGetIPAddr` while `networkGetConnectStatus()` is above 0, else empty |

  The build tag, the labels and the headers are the only things not from stock (13 languages). The sources
  are pinned in `SETTINGS_PINS`.

## Keyboards

Settings > General > Keyboards lists the keyboards the on-screen keyboard offers ([keyboard](keyboard.md))
as three switch rows, as on iOS: **English** (`ACT_KB_EN`, `keyboard-english`, on by default),
**French (AZERTY)** (`ACT_KB_FR`, `keyboard-french`) and **Chinese (Pinyin)** (`ACT_KB_ZH`,
`keyboard-pinyin`), both off by default. Each is saved atomically and read each time the keyboard
opens. Any of them can be turned off except the last one on: that row is dimmed to 60 % and takes no
tap (`kb_only_on`, refreshed after every toggle; `kb_toggle` refuses it too). With two or more on the
keyboard has a language key (and with Chinese a pinyin layer); turning one off also forgets it as the
saved layer (`keyboard-last`).

## Settings Files

Settings > Developer > Tools > **Settings Files** opens `m1plus_files`: the payload's own files as raw
values. Labels are the file names (identifiers, untranslated). Everything is read once by `setfiles_open`
as the page opens; a refresh on coming back reads nothing, and there is no timer.

- **Card 1:** the guard files in `/mnt/data` (`m1plus-start` its character; `m1plus-run`, `m1plus-bad`,
  `m1plus-off` present or missing).
- **Card 2:** `m1plus/` (present or missing), then one row per file in it. A one-character setting shows
  its character (`other` for anything longer, `empty`); `home-menu` and `pulldown-tiles` their first 12
  characters; `playback-eq` (binary) present or missing; `search-history` its line count; the two rebuild
  requests present or missing; an absent file reads `missing`.
- **Delete.** Only setting-file rows are tappable (`ACT_SFDEL`), and only while their file is there. A tap
  asks "Delete this settings file?"; Yes calls `setfiles_delete`, which unlinks that one file, reads that
  row again and toasts "Settings file deleted" ("Storage unavailable" if it is still there). The guard
  files and the folder rows stay information rows and `setfiles_delete` refuses them. A value the running
  player holds keeps until it is read again or the device restarts.
- Reset All Settings does not touch the card's `scrobble.ini`.

**Unsupported Files** is the last card: a count row (a chevron and a tap only while the count is not zero)
and **Delete Unsupported Files**. The retired files are old settings files nothing reads any more: the
fixed table `sf_retired` in `patch/setfiles.c` (mirrored as `RETIRED_FILES` in `tools/pod_pages.py`), each
name with its `.tmp` sibling. A renamed setting gets its old name added to that table, not a migration.
The table is checked with `access()` once as the page opens and the count is kept in memory; a delete
checks again. The tap opens a plain list (`covlist_open(2)`), one row per file that is there, with its
folder under it; a tap asks "Delete this unsupported file?", deletes that file and takes its row away (the
last one shows "No unsupported files"). Delete Unsupported Files asks "Delete all
unsupported files?", unlinks every entry and toasts "Unsupported files deleted" (or "Storage unavailable"
when one remains); with none it toasts "No unsupported files" and asks nothing.

### Reset All Settings

Settings > Developer > Reset > **Reset All Settings** asks "Reset all settings to their defaults?" in the
confirm dialog. Yes calls `setfiles_reset_all`: it unlinks every entry of `/mnt/data/m1plus/` (unknown
names and `.tmp` leftovers too; no recursion; the folder stays; at most 256 entries), then every retired
entry. The toast is "Settings reset. Restart to apply.", or "Storage unavailable" when an entry remains,
the folder cannot be opened, or a re-read still finds an entry.

Kept: the guard files in `/mnt/data`, and everything under `/mnt/mmc` (cover cache, durations, Cover Flow
position), which have their own clear rows. Nothing reboots or re-applies live: values the running player
holds keep until the device restarts.
