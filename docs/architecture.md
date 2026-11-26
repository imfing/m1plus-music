# Architecture

The build copies the official V2.1 rootfs, compiles a fixed-address MIPS payload into
`/release/bin/demo`, applies pinned code and asset edits and repacks the kernel and rootfs as
`update.bin`. Input mismatches and an oversized rootfs fail the build.

Read [payload](modules/payload.md) and [addresses](modules/addresses.md) before searching the
binary. See [workflow](workflow.md) for commands, [UI](ui.md) for layout and assets, and
[history](history.md) for device findings.

## Modules

### Build and runtime

| Module | Contents |
|---|---|
| [Build pipeline](modules/pipeline.md) | Build stages, ordering, package validation |
| [Payload](modules/payload.md) | Segment, trampolines, stock calls, hook inventory |
| [Addresses](modules/addresses.md) | Stock symbols, offsets, record layouts |
| [Safety](modules/safety.md) | Allowed entry points, required invariants |
| [Validation](modules/validation.md) | Test boundaries and what they prove |
| [Home and boot guard](modules/home-guard.md) | Startup marker, grid entry, window stack, fallback |
| [Boot assets](modules/boot.md) | Boot logo, quotes, settings slides |
| [Library loading](modules/libload.md) | List hand-over and memory peaks |
| [Updater version compare](modules/version.md) | Why official V2.1 installs over the mod |
| [Software Update](modules/update.md) | Wi-Fi update from GitHub releases |
| [UI rules](modules/ui-rules.md) | Rules every UI step follows |
| [Navbars](modules/navbar.md) | One reference for every page navbar |
| [Select mode](modules/selmode.md) | Shared multi-select: marks, navbar, bottom bar |
| [Overlays](modules/overlays.md) | Dialogs, popups and sheets |
| [Theme](modules/theme.md) | Config clamp and theme assets |
| [Accent and palette](modules/accent.md) | Three paint hooks, background, accent |
| [Fonts](modules/fonts.md) | Inter, Source Han Sans, CJK forms |
| [Icons](modules/icons.md) | Lucide icon set and generated assets |
| [Languages](modules/i18n.md) | Translation tables, keys, width checks |
| [List gestures](modules/gestures.md) | Drag cancellation, stopping coasting lists |
| [Keyboard](modules/keyboard.md) | Own QWERTY page, Pinyin layer |
| [Tidal keyboard](modules/tidalkb.md) | Keyboard in stock Tidal search |

### Library and browsing

| Module | Contents |
|---|---|
| [Cover Flow](modules/coverflow.md) | Renderer, gestures, landscape mode |
| [Cover cache](modules/covercache.md) | Shared cover builder, resampling, .bad retry |
| [Home cover build](modules/homecover.md) | Background cover build and progress pill |
| [Albums](modules/albums.md) | Grid/list page, sorts, view card |
| [Album page](modules/album-page.md) | Own album page and playback actions |
| [Artists](modules/artists.md) | Artists, Album Artists, Genres, Composers, split |
| [Songs](modules/songs.md) | A-Z sections, rail, sort, selection |
| [Recently Added](modules/recent-albums.md) | Newest songs and albums |
| [Recently Played](modules/recent.md) | History file, covers, shelf |
| [Daily Mix](modules/dailymix.md) | Selection job, stored mix, page |
| [Playlists](modules/playlists.md) | Mosaics, list mode, cleanup |
| [Playlist covers](modules/plcover.md) | Generated cover styles from album tones |
| [Add to Playlist](modules/picker.md) | Own picker replacing stock |
| [Folders](modules/folders.md) | Own Folders page over stock state |
| [Library rows](modules/rows.md) | Stock row edits, layout, text sizing |
| [Row menu](modules/rowmenu.md) | Track "..." sheet: Play Next, Favorite |
| [Get Info](modules/songinfo.md) | Track details sheet |
| [Search](modules/search.md) | Library search, chips, live results |
| [Menu](modules/menu.md) | Home and Extras layout, customization |
| [Home pins](modules/pins.md) | Pinned albums, playlists, songs and artists on Home |
| [Line Out pill](modules/lineout.md) | LO pill, EQ mark, sync icon |

### Playback

| Module | Contents |
|---|---|
| [Now Playing](modules/nowplaying.md) | Cover tint, remaining time, rounded art |
| [Timed cover page](modules/bigcover.md) | Enlarged cover with own 320 px art, Idle Display |
| [Lyrics page](modules/lyrics.md) | Own lyrics lines, text sizes |
| [Idle lyrics](modules/idlelyrics.md) | Lyrics idle display page |
| [More sheet](modules/playmore.md) | Playback options, Display Mode, Find entries |
| [Find Cover & Lyrics](modules/onlineart.md) | Online covers and lyrics lookup |
| [Queue page](modules/queue.md) | Playing track, Up Next, edit |
| [Shuffle](modules/shuffle.md) | Song, album and folder queues |
| [Continue Playing](modules/nextalbum.md) | Next Albums after the queue ends |
| [Mini player](modules/minibar.md) | Home overlay, controls, blur |
| [Lock screen](modules/lockscreen.md) | Own lock page, wallpaper, date |
| [Cassette Mode](modules/tape.md) | Landscape rendering, themes, timer |
| [Vinyl Mode](modules/vinyl.md) | Portrait turntable page |
| [VU Meter](modules/vu.md) | Display Mode meters, level tap |
| [Parametric EQ](modules/peq.md) | Engine, presets, Equalizer page |
| [Mono and Crossfeed](modules/stereo.md) | Stereo stage and hciplayer flag |
| [Crossfade](modules/crossfade.md) | Dual-decoder overlap in hciplayer, preload bridge, kept output with sample-rate conversion |
| [Non-MQA probe skip](modules/mqa.md) | Skip hciplayer's shadow MQA decoder on non-MQA FLAC/PCM tracks |
| [Playback settings](modules/playset.md) | Grouped Playback Settings page |
| [Volume page](modules/volume.md) | Status bar tap's own Volume page |
| [Scrobbling](modules/scrobble.md) | Card log, ListenBrainz and Last.fm upload |
| [Card script runner](modules/cardrun.md) | Card script runner, Card Script page |
| [Virtual iPod](modules/ipod.md) | Touch wheel, navigation, playback |
| [iPod Cover Flow](modules/ipod-coverflow.md) | Embedded carousel |

### Sources and network

| Module | Contents |
|---|---|
| [Network](modules/network.md) | Shared HTTP, download and CA layer |
| [Podcasts](modules/podcasts.md) | Episodes, feeds, directory, downloads |
| [Audiobooks](modules/audiobooks.md) | Book model, LibriVox find and download |
| [Radio](modules/radio.md) | Stations, directory, hciplayer playback |
| [Subsonic](modules/subsonic.md) | Remote library, streaming, downloads |
| [Wi-Fi](modules/wifi.md) | hostap 2.12, own Wi-Fi page |
| [Wi-Fi Transfer](modules/wifi-transfer.md) | Web server, api.cgi, thttpd limits |
| [Update Library](modules/libupdate.md) | Own page, scan time record, scan-finish hook |
| [Bluetooth](modules/bluetooth.md) | Own page, codec picker, devices |
| [USB DAC](modules/uac2.md) | XRUN recovery in `soc_aic.ko` (`start_threshold` prefill) |

### Settings and system

| Module | Contents |
|---|---|
| [Settings](modules/settings.md) | Pages and persisted choices |
| [Display](modules/display.md) | Brightness, timeout, LED Light |
| [Buttons and Power](modules/keyspower.md) | Own Buttons & Power page |
| [Language](modules/language.md) | Own language page |
| [Date and Time](modules/datetime.md) | Auto time, UTC RTC, 43 time zones |
| [Sleep Timer](modules/sleeptimer.md) | Own Sleep Timer page |
| [Pull-down](modules/pulldown.md) | Control Center tiles and order |
| [Charge Limit](modules/charging.md) | Charging pauses at 80-95 % |
| [Battery art](modules/battery.md) | Battery outline and fill |
| [Battery History](modules/batthist.md) | Opt-in 24 h recorder of battery level and use, and its own page of charts under Battery |
| [Screenshot](modules/screenshot.md) | Countdown, capture, import |
