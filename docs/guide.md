# M1+ Music user guide

For installation, updates and restore, see [Install](install.md).

## Start listening

1. Copy music to the card.
2. Open **Extras → Update Library** to scan it.
3. Open **Albums**, **Artists** or **Songs**, then tap a track to play.

Tap the mini player's cover to open Now Playing. Its buttons pause/resume or skip.

## Find your way around

M1+ Music opens at startup and from its icon on Shanling Home. The default menu shows Cover Flow,
Albums, Artists, Songs, Playlists and Extras. Daily Mix and Recently Played appear below it;
the mini player appears while a track is queued.
Open **Extras → Settings** to customize the player. To return to the stock grid, use
**Settings → Developer → Open Shanling Home**. Change **Boot to M1+ Music** under
**Settings → Developer → Startup** to choose what opens at startup.

## Browse and play

| Page | Controls |
|---|---|
| Cover Flow | Drag to browse, tap a side cover to centre it, tap the centre cover to open its album |
| Albums | Switch grid/list mode with the navbar button; the choice is remembered |
| Artists | Switch Artist/Album Artist in the navbar, then open an artist's albums |
| Songs | Jump with the A–Z rail; use Search, Sort or Select from the navbar |
| Recently Added | The newest songs; the navbar's grid button switches to the newest albums |
| Album | Play all, shuffle the album, or tap a track; the footer shows the track count and length once measured |
| Playlists | Open a playlist or use its menu to create, import, export or delete |
| Shuffle | Shuffle songs, albums or folders from Extras |

In Now Playing, tap **…** for playback options, Look up album, Cassette Mode and Vinyl Mode.
Open its **More** page for the online cover and lyrics lookup (Wi-Fi required).

A track row's **…** on the album page and the Songs lists offers **Play Next**, **Play After** and
**Add to Playlist**. Shuffle reorders the queue itself, so the Queue page's Up Next shows what
plays next; **Clear** in its header removes the songs after the playing one.

While Line Out is on, the status bar shows an amber **LO** pill.

Drag a list to scroll; tap a row to open or play it.

## Settings

Grey values show the current setting.

To show, hide or reorder menu items, open **Settings → Home Screen → Main Menu**.
Use **Home Screen → Extras** to hide items from Extras. Settings stays accessible.

To show, hide or reorder the tiles of the pull-down, open **Settings → System → Appearance → Control Center**.

| Page | Options |
|---|---|
| Wi-Fi / Bluetooth | Stock connection pages; values show On/Off |
| Home Screen | Recent Albums, Daily Mix, menu items and Battery Percentage (off by default); Regenerate Daily Mix takes effect next Home visit |
| Library | Update Library, Album Order (Artist/Album, for Albums and Cover Flow), Rebuild Covers and landscape Cover Flow |
| Now Playing | Cassette Theme: Normal, Chrome or Metal; applies next time Cassette Mode opens |
| Playback | Stock Play Mode and EQ pages; All Playback Settings includes Gapless |
| System | Display, **Appearance** > **Background** (Black, or Tinted: with an accent chosen, the dark greys of every page, card and sheet take a 12 % wash of it; covers and cover-coloured pages keep their look) and **Accent** (the main menu's icons show in the accent; Neutral, Red, Orange, Green, Teal, Purple or Champagne: tints pressed rows and their icons, switches that are on, the lit pull-down tiles, sliders, progress bars and the picker check; applies at once) and **Control Center** (show, hide and reorder the eight tiles of the status bar swipe-down panel), Language (under All System Settings), Keyboards and About (firmware, device, network and storage details; **Software Update** is the row under the version) |
| Keyboards | English always enabled; Chinese (Pinyin) adds a language key and candidates above the keys. Swipe candidates sideways; space selects the first |
| Developer → Startup | Boot to M1+ Music; Open Shanling Home |
| Developer → Tools | Screenshot, Cover Cache, Clear Track Durations and stock System Update |

Home builds missing album covers (and measures track lengths) in the background. A pill at the top
of Home shows the progress, and a sync icon in the status bar shows while it runs; the pill's **×**
stops it until the next restart. Nothing is scanned when the library has not changed, and an
album whose cover hangs the build is skipped. **Rebuild Covers** asks for confirmation, then
Home rebuilds every cover the same way. **Cover Cache**
shows cached/missing/stale counts and current work; **Clear Cover Cache** asks before deleting,
then Home regenerates covers.

**Software Update** (Settings → System → About, the row under the version; needs Wi-Fi) checks GitHub for a newer release: **Check for Update**, then **Download and Install**; **Release Notes** shows what changed.
A dialog asks first (about 55 MB, replaces the card's `update.bin`; 110 MB of free card space needed); a popup shows the progress and **Cancel** (Back is Cancel too; the card's old `update.bin` stays). When the download
is complete the firmware's own TF card update takes over with its confirmation, battery check and checksums; the flashing is unchanged. If you say No there, the page offers **Install** again and **Check Again**.
A development build is always offered the latest release.

**Screenshot** asks first: leave the page within five seconds to capture another screen.
Cancel during the countdown if needed. Pictures are saved in the card's `screenshots` folder.

## Extras

**Radio** (Settings > Main Menu shows it; it is also on the Pod's main menu) plays internet stations: My Stations (your saved list), Recently Played and,
with Wi-Fi, Radio Browser: the Top Stations, countries, genres and a name search of radio-browser.info. Tap a station to play it; the `...` on
Radio Now Playing adds it to or removes it from My Stations. The Radio Now Playing page shows the song, the stream and previous/next along the list; local
music stops the radio. Stations are `Radio/favourites.m3u` on the card; the `...` on the My Stations page has Import from Card, which adds the stations of
every other `.m3u`, `.m3u8` or `.pls` in `Radio/` that are not there yet (your files are never changed).

**Cassette Mode** is a landscape Now Playing screen. Tap the cassette to pause/resume and the
top-left screw to close. Change its theme under Settings.

**Vinyl Mode** is a turntable Now Playing screen: the cover turns as the record's label while
playing. Tap the record or the large key to pause/resume, the side keys to skip, the top-left
chevron to close.

**Cover & Lyrics** (Now Playing > ... > More > Cover & Lyrics, needs Wi-Fi) looks up the playing album's covers
(iTunes, then Deezer) and its lyrics (LRCLIB). Tap a cover to use it for the album everywhere; Save Lyrics writes
`<song>.lrc` next to the song (Replace Lyrics when one is there).

**Pod** opens a virtual iPod. Slide around the wheel to browse and tap its centre to select.
Tap MENU to go back; hold it to return to the Pod's main menu, then tap it to close.
The bottom button pauses/resumes; the side buttons skip tracks. The wheel does not seek
or change volume on its Now Playing screen.

**Podcasts** reads local episodes from `Podcasts/<Show>/` on the card. Open a show, then an
episode; its button offers Play or Download. Use an episode's **…** menu to mark it played
or unplayed. To find shows online, enable **Settings → Library → Podcast Search**, connect
to Wi-Fi, then use **Search** on the Podcasts page and **Subscribe** on a show's preview.

**Search** opens the same library search as the Songs page's Search button. It is hidden from
the main menu by default.

For a missing feature, enable it through **Settings → Home Screen → Main Menu**, or find it under Extras.
