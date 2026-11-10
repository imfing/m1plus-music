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
| Cover Flow | Drag to browse, tap a side cover to centre it, tap the centre cover to open its album; with Settings > Library > Volume Buttons on, volume down / up moves to the next / previous album |
| Albums | The navbar's **…** switches grid/list and sorts by Title, Artist, Recently Added or Year; the choices are remembered; the list in Title order has section letters |
| Artists | Switch Artist/Album Artist in the navbar's **…**, then open an artist's albums: Play or Shuffle all the artist's songs, each album with its year; the **…** switches grid/list and the album order; the rows and the artist's page show [artist photos](#artist-photos). A composer's page (Extras → Composers) looks the same, without a photo; its All Songs lists the composer's songs |
| Songs | Jump with the A–Z rail (Settings → Library → Index Rail, on by default); Search in the navbar; the **…** has Select and Sort (Title, File Name, Format, Recently Added; tap the ticked order to reverse it) |
| Recently Added | The newest songs; the navbar's **…** switches to the newest albums |
| Album | Play, shuffle the album, or tap a track; the footer shows the track count and length once measured |
| Playlists | Open a playlist (Play, Shuffle, or tap a track); the list-plus button creates, imports, exports or deletes; the **…** switches grid/list and the name order |
| Shuffle | Shuffle songs, albums or folders from Extras |

In Now Playing, tap **…** for playback options, Look up album, Cassette Mode and Vinyl Mode.
Open its **More** page for **Sleep Timer** (opens Settings > Power, where the timer is set) and the
online cover and lyrics lookup (Wi-Fi required).

A track row's **…** on the album page and the Songs lists offers **Play Next**, **Play After**,
**Add to Playlist**, **Favorite** (Undo Favorite when it is one) and **Get Info**: the track's
format, sample rate and bit depth, bitrate, length, size and path. Shuffle reorders the queue itself, so the Queue page's Up Next shows what
plays next; **Clear** in its header removes the songs after the playing one.

While Line Out is on, the status bar shows an amber **LO** pill.

Drag a list to scroll; tap a row to open or play it.

### Artist photos

The Artists list and an artist's page show a photo you put on the card:

- Name it `artist.jpg` (`artist.jpeg` and `artist.png` work too).
- Put it in one of the artist's album folders, or in the folder above them if that folder holds only
  this artist's albums, e.g. `Music/Adele/artist.jpg` next to `Music/Adele/21/` and
  `Music/Adele/25/`. A folder that mixes artists (`Music/`, `Various Artists/`) is not used, and
  `CD1` / `Disc 2` folders are skipped.
- The photo belongs to the artist in the album's tags. "A feat. B" with no photo of its own shows A's.
- A square picture fits best. Other shapes are cut to a square: a wide one at the centre, a tall one
  near the top so a face stays in.

Home looks for photos while it builds covers after a library change. To pick up a photo added
later, open that artist's page, or use **Settings → Library → Rebuild Artist Photos**, which checks
every artist again in the background.

A Subsonic server's artists show the server's own artist picture instead, fetched in the background after a sync (the Subsonic page's status line says "Loading artist images…"); an artist the server has no picture for shows the grey placeholder in the list and the page without a circle.

## Settings

Grey values show the current setting.

To show, hide or reorder menu items, open **Settings → Home Screen → Main Menu**.
Use **Home Screen → Extras** to hide items from Extras. Settings stays accessible.

To show, hide or reorder the tiles of the pull-down, open **Settings → System → Appearance → Control Center**.

| Page | Options |
|---|---|
| Wi-Fi / Bluetooth | Wi-Fi: the Wi-Fi switch, the connected network, My Networks and nearby networks with their security, and Other… for a hidden network; a saved network's page has Forget This Network and Auto-Join. WPA3 and Enhanced Open networks join. All System Settings > Wi-Fi opens the same page (the stock page with `/mnt/mmc/m1plus-off`, the only route for WEP). Bluetooth: the stock page. Values show On/Off |
| Home Screen | Recent Albums, Daily Mix, menu items; Regenerate Daily Mix takes effect next Home visit |
| Library | Update Library, Rebuild Covers, Rebuild Artist Photos, under **List Navigation** (the Songs, Artists, Albums and Radio lists) **Index Rail** (on by default: the A–Z rail on Songs, Artists, Radio countries and the Albums list in Title order) and **Section Headers** (on by default: the section letters and the pinned header; off closes the rows up), landscape Cover Flow, Volume Buttons (the volume buttons move between albums in Cover Flow; off by default), Podcast Discover and Podcast Region |
| Now Playing | Cassette Theme: Normal, Chrome or Metal, applies next time Cassette Mode opens; Vinyl Record and Base; Idle Display (last card): what Now Playing shows after 10 seconds, Off, Album Cover, Cassette or Vinyl (Off is the same switch as Playback Settings > Cover mode) |
| Playback | **EQ** opens the [Equalizer](#equalizer). All Playback Settings includes Gapless, and its Equalizer row opens the Equalizer |
| System | Display, **Appearance** > **Background** (Black, or Tinted: with an accent chosen, the dark greys of every page, card and sheet take a 12 % wash of it; covers and cover-coloured pages keep their look) and **Accent** (the main menu's icons show in the accent; Neutral, Red, Orange, Green, Teal, Purple or Champagne: tints pressed rows and their icons, switches that are on, the lit pull-down tiles, sliders, progress bars and the picker check; applies at once), **Lock Screen** (Enable; Wallpaper: the default or one of up to five pictures you copy to `lockscreenimage` on the card, JPG or PNG, 320 x 480, under 1 MB, the chosen one framed in the accent; Show Time; Player Style: Large Cover or Mini Player, a bar like Home's at the bottom; Custom Wallpaper explains the pictures. Display > Lock Screen opens the same page) and **Control Center** (show, hide and reorder the eight tiles of the status bar swipe-down panel), Language (under All System Settings), Keyboards, **Battery** (**Battery Percentage**, off by default, shows the exact charge beside the status bar's battery icon; **Charge Limit** stops charging at 80, 85, 90 or 95 % while the player is on and resumes about 5 % lower, 100 % (the default) is no limit, and a switched-off player charges fully) and About (firmware, device, network and storage details; **Software Update** is the row under the version) |
| Keyboards | English always enabled; Chinese (Pinyin) adds a language key and candidates above the keys. Swipe candidates sideways; space selects the first. Tidal > Search uses this keyboard too: it sits at the bottom of Tidal's own page, Search hides it and a tap on the search bar brings it back |
| Developer → Startup | Boot to M1+ Music; Open Shanling Home |
| Developer → Tools | Screenshot, Cache (Covers, Artist Photos: how many artists have a photo and how many have none, then Track Durations: its last row is Clear Track Durations), Settings Files (tap a file to delete it; Unsupported Files removes leftovers of older builds) |
| Developer → Reset | Reset All Settings |

Home builds missing album covers (and measures track lengths) in the background. A pill at the top
of Home shows the progress, and a sync icon in the status bar shows while it runs; the pill's **×**
stops it until the next restart. Nothing is scanned when the library has not changed, and an
album whose cover hangs the build is skipped. **Rebuild Covers** asks for confirmation, then
Home rebuilds every cover the same way. **Cache**
shows cached/missing/stale counts, current work, the artist photo counts and the measured tracks; **Clear Cover Cache** asks before deleting,
then Home regenerates covers (artist photos are kept).

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

**Subsonic** (main menu Extras > Subsonic) plays from a Subsonic-compatible server such as Navidrome, Gonic or Airsonic. Tap **Add Server** and enter the server address (start it with `http://` or `https://`; a port and a subpath are fine), your username and your password, then tap **Sign In** (the password itself is not kept on the card, only a sign-in token for that server). A line under the card says what went wrong: "Incorrect username or password", "Can't connect to the server", or a certificate error. A certificate that is not trusted (a self-signed server) is not supported; on a home network use `http://`. The password is stored unencrypted on the card (`.m1plus/subsonic.conf`), so make a dedicated server account for the device.
The root page's status line under the title reads **Synced** (with its age), **Syncing…**, **Updating library…**, **Loading covers…**, **Loading artist images…** (the library keeps filling in the background; you can browse meanwhile) or **Not Connected**. The six rows are Albums, Artists, Songs, Playlists, Favorites and Downloaded. The `...` card has **Sync Now** (it asks first) and **Server Settings** (server, username, password, Sync Now and Sign Out); the magnifier searches the server. Tap a song to stream the original file (nothing is transcoded). DSD files do not stream: tapping one asks **Download to Play?**.
A server album's page has a `...` with **Download Album**, which queues every track not yet on the card (one message tells how many). A song's `...` sheet has Play Next, Play After, Download, Favorite and Get Info. Favorites are the server's own stars and stay in sync with it. Downloads go to `Subsonic/` on the card, one at a time; a small ring shows progress, a stopped download (Wi-Fi lost) resumes where it was, and Cancel Download or Remove Download from the sheet stops it or deletes the file. **Downloaded** lists them and works offline, also after **Sign Out**, which keeps the downloads and clears only the server's cache. Without Wi-Fi, songs that are not downloaded are dimmed.
Limits: the Songs list shows the first 10,000 songs, a play queue holds the list in its order, up to 64 songs (from the one you tapped when the list is longer), and a playlist or favourites list up to 3,000 songs.

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
or unplayed. A show's **…** menu has **Episode Order**: **Newest First** (the default) or **Oldest First**, the order of its list and of the queue that follows the episode you start (Oldest First suits a series); a tap switches it. To find shows online, connect to Wi-Fi, then use the **Discover** row on the Podcasts page (on unless **Settings → Library → Podcast Discover** is off): the top 25 shows and top 25 episodes of your region (**Settings → Library → Podcast Region**, Automatic by default), the magnifier to search (the Podcasts page's globe opens the same search directly), and **Subscribe** on a show's preview.

**Wi-Fi Transfer:** turn it on under **System settings → Network Service → Wifi file transfer**,
then open the address it shows (port 8888)
in a browser on the same network. M1+ Music replaces the stock page: it lists the whole card: sort, filter, select files to
download, rename, move or delete, create folders, and upload files or folders (drag them onto the
page). The eye button in the header shows hidden files.

**Search** opens the same library search as the Songs page's Search button. It is hidden from
the main menu by default.

For a missing feature, enable it through **Settings → Home Screen → Main Menu**, or find it under Extras.
