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
| Albums | The navbar's **…** switches grid/list and sorts by Title, Artist, Recently Added or Year; the choices are remembered |
| Artists | Switch Artist/Album Artist in the navbar's **…**, then open an artist's albums |
| Songs | Jump with the A–Z rail; Search in the navbar; the **…** has Select and Sort (Title, File Name, Format, Recently Added; tap the ticked order to reverse it) |
| Recently Added | The newest songs; the navbar's **…** switches to the newest albums |
| Album | Play, shuffle the album, or tap a track; the footer shows the track count and length once measured |
| Playlists | Open a playlist (Play, Shuffle, or tap a track); the list-plus button creates, imports, exports or deletes; the **…** switches grid/list and the name order |
| Shuffle | Shuffle songs, albums or folders from Extras |

In Now Playing, tap **…** for playback options, Look up album, Cassette Mode and Vinyl Mode.
Open its **More** page for the online cover and lyrics lookup (Wi-Fi required).

A track row's **…** on the album page and the Songs lists offers **Play Next**, **Play After**,
**Add to Playlist**, **Favorite** (Undo Favorite when it is one) and **Get Info**: the track's
format, sample rate and bit depth, bitrate, length, size and path. Shuffle reorders the queue itself, so the Queue page's Up Next shows what
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
| Wi-Fi / Bluetooth | Wi-Fi: the Wi-Fi switch, the connected network, My Networks and nearby networks with their security, and Other… for a hidden network; a saved network's page has Forget This Network and Auto-Join. WPA3 and Enhanced Open networks join. All System Settings > Wi-Fi opens the same page (the stock page with `/mnt/mmc/m1plus-off`, the only route for WEP). Bluetooth: the stock page. Values show On/Off |
| Home Screen | Recent Albums, Daily Mix, menu items and Battery Percentage (off by default); Regenerate Daily Mix takes effect next Home visit |
| Library | Update Library, Rebuild Covers, landscape Cover Flow, Podcast Discover and Podcast Region |
| Now Playing | Cassette Theme: Normal, Chrome or Metal; applies next time Cassette Mode opens |
| Playback | Stock Play Mode page; **EQ** opens the [Equalizer](#equalizer). All Playback Settings includes Gapless, and its Equalizer row opens the 10-Band EQ |
| System | Display, **Sample Rate RGB** (on/off playback-format wheel-lamp colours; brightness follows volume), **Appearance** > **Background** (Black, or Tinted: with an accent chosen, the dark greys of every page, card and sheet take a 12 % wash of it; covers and cover-coloured pages keep their look) and **Accent** (the main menu's icons show in the accent; Neutral, Red, Orange, Green, Teal, Purple or Champagne: tints pressed rows and their icons, switches that are on, the lit pull-down tiles, sliders, progress bars and the picker check; applies at once) and **Control Center** (show, hide and reorder the eight tiles of the status bar swipe-down panel), Language (under All System Settings), Keyboards and About (firmware, device, network and storage details; **Software Update** is the row under the version) |
| Keyboards | English always enabled; Chinese (Pinyin) adds a language key and candidates above the keys. Swipe candidates sideways; space selects the first |
| Developer → Startup | Boot to M1+ Music; Open Shanling Home |
| Developer → Tools | Screenshot, Cache (Covers, then Track Durations: its last row is Clear Track Durations), Settings Files (tap a file to delete it; Unsupported Files removes leftovers of older builds) |
| Developer → Reset | Reset All Settings |

Home builds missing album covers (and measures track lengths) in the background. A pill at the top
of Home shows the progress, and a sync icon in the status bar shows while it runs; the pill's **×**
stops it until the next restart. Nothing is scanned when the library has not changed, and an
album whose cover hangs the build is skipped. **Rebuild Covers** asks for confirmation, then
Home rebuilds every cover the same way. **Cache**
shows cached/missing/stale counts, current work and the measured tracks; **Clear Cover Cache** asks before deleting,
then Home regenerates covers.

**Software Update** (Settings → System → About, the row under the version; needs Wi-Fi) checks GitHub for a newer release: **Check for Update**, then **Download and Install**; **Release Notes** shows what changed.
A dialog asks first (about 55 MB, replaces the card's `update.bin`; 110 MB of free card space needed); a popup shows the progress and **Cancel** (Back is Cancel too; the card's old `update.bin` stays). When the download
is complete the firmware's own TF card update takes over with its confirmation, battery check and checksums; the flashing is unchanged. If you say No there, the page offers **Install** again and **Check Again**.
A development build is always offered the latest release.

**Screenshot** asks first: leave the page within five seconds to capture another screen.
Cancel during the countdown if needed. Pictures are saved in the card's `screenshots` folder.

## Equalizer

**Settings → Playback → EQ** opens the Equalizer. Its switch turns the EQ on or off; off, playback
is unchanged. The EQ works at every sample rate and on every output; DSD plays without it.

Headphones, Line Out and a USB DAC each keep their own EQ (on or off, and what plays), and it
switches by itself when the output changes. The grey line under the switch names the output you
are setting.

Tap **10-Band EQ** or a preset in the list to play it. Below the list:

- **Edit 10-Band EQ:** drag anywhere in a band's column to set it (±12 dB in 0.5 dB steps); the
  graph and the sound follow. **Curve** picks Flat, a genre curve or Custom (moving a slider on a
  genre curve copies it into Custom). **Preamp** is Auto, which lowers the level by the largest
  boost to prevent distortion, or a fixed cut. **Reset** returns to Flat. **Save as Preset** saves
  the curve as a preset file.
- **Presets:** **Download from AutoEq** searches the AutoEq database by headphone name (with
  Wi-Fi); tap a result to save its correction, then tap it again to use it. Your presets are
  listed under AutoEq and On Card. Open one to see its curve and bands; tap a band to change its
  type, frequency, gain or Q (the values can be typed on a number keypad). Leaving with unsaved
  changes asks whether to **Save**, **Save As New…** or **Don't Save**. **Delete Preset** removes the file.

Presets are Equalizer APO / AutoEq parametric `.txt` files in the `EQ` folder on the card (up to
64; `Preamp`, `Channel` and `Filter` lines with peak and shelf filters), so you can also copy your
own there.

## Extras

**Radio** (Settings > Main Menu shows it) plays internet stations: My Stations (your saved list), Recently Played and,
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
or unplayed. To find shows online, connect to Wi-Fi, then use the **Discover** row on the Podcasts page (on unless **Settings → Library → Podcast Discover** is off): the top 25 shows and top 25 episodes of your region (**Settings → Library → Podcast Region**, Automatic by default), the magnifier to search (the Podcasts page's globe opens the same search directly), and **Subscribe** on a show's preview.

**Wi-Fi Transfer:** turn it on under **System settings → Network Service → Wifi file transfer**,
then open the address it shows (port 8888)
in a browser on the same network. M1+ Music replaces the stock page: it lists the whole card: sort, filter, select files to
download, rename, move or delete, create folders, and upload files or folders (drag them onto the
page). The eye button in the header shows hidden files.

**Search** opens the same library search as the Songs page's Search button. It is hidden from
the main menu by default.

For a missing feature, enable it through **Settings → Home Screen → Main Menu**, or find it under Extras.
