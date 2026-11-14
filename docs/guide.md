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
| Artists | Switch Artist/Album Artist in the navbar's **…**, then open an artist's albums: Play or Shuffle all the artist's songs, each album with its year; the **…** finds a photo of the artist online, switches grid/list and sets the album order; the rows and the artist's page show [artist photos](#artist-photos). A composer's page (Extras → Composers) looks the same, without a photo; its All Songs lists the composer's songs |
| Songs | Jump with the A–Z rail (Settings → Library → Index Rail, on by default); Search in the navbar; the **…** has Select and Sort (Title, File Name, Format, Recently Added; tap the ticked order to reverse it) |
| Recently Added | The newest songs; the navbar's **…** switches to the newest albums |
| Album | Play, shuffle the album, or tap a track; the footer shows the track count and length once measured |
| Playlists | Open a playlist (Play, Shuffle, or tap a track); the list-plus button creates, imports, exports or deletes; the **…** switches grid/list and the name order. Inside a playlist, **…** → **Clean Up Playlist** repairs songs whose files were moved to another folder (run Update Library first) and offers to remove the ones that are no longer on the card; only that playlist changes and no file is deleted |
| Folders | Extras → Folders lists the card's folders and audio files. With the Playback setting **Folder cover** on, a row with a cover shows it (40 px) in place of its icon: a file's is its album's, a folder's is the album of the first song of the library inside it (also in sub-folders); rows without one keep their icon. Only music in the library gets a cover; the covers are the ones the app has already made (Albums, Cover Flow), none are made here |
| Shuffle | Shuffle songs, albums or folders from Extras |

In Now Playing, tap **…** for playback options, Look up album, Look up artist, Cassette Mode and Vinyl Mode. For a song playing from Subsonic the two Look up rows open the server's album and the server's artist; while it is streaming (not downloaded), Add to playlist and Delete are dimmed, and it is not added to the card's Recently Played and Most Played lists.
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

No picture on the card? Open the artist's page, tap **…** → **Find Artist Photo** (needs Wi-Fi): it
shows up to six photos from Deezer and NetEase Cloud Music, those under that exact name first. Tap one, then **Use This Photo**.
A photo picked this
way stays until you pick another: Rebuild Artist Photos and an `artist.jpg` added later do not
replace it.

A Subsonic server's artists show the server's own artist picture instead, fetched in the background after a sync (the Subsonic page's status line says "Loading artist images…"); an artist the server has no picture for shows the grey placeholder in the list and the page without a circle.

## Settings

Grey values show the current setting.

To show, hide or reorder menu items, open **Settings → Home Screen → Main Menu**.
Use **Home Screen → Extras** to hide items from Extras. Settings stays accessible.

To show, hide or reorder the tiles of the pull-down, open **Settings → System → Appearance → Control Center**. The pull-down's Playback Settings tile opens the Playback Settings page below (and is dimmed while you are on it).

| Page | Options |
|---|---|
| Wi-Fi / Bluetooth | Wi-Fi: the Wi-Fi switch, the connected network, My Networks and nearby networks with their security, and Other… for a hidden network; a long network name ends in an ellipsis in the list, and the network's page (the info glyph) shows the whole name under the title; a saved network's page has Forget This Network and Auto-Join. WPA3 and Enhanced Open networks join. All System Settings > Wi-Fi opens the same page (the stock page with `/mnt/mmc/m1plus-off`, the only route for WEP). Bluetooth: the stock page. Wi-Fi and Bluetooth can be on together: turning one on warns that Bluetooth audio may stutter while Wi-Fi is on and leaves the other on (also from the Control Center tiles). Values show On/Off |
| Home Screen | Recent Albums, Daily Mix, menu items; Regenerate Daily Mix takes effect next Home visit |
| Library | Update Library, Rebuild Covers, Rebuild Artist Photos, under **List Navigation** (the Songs, Artists, Albums and Radio lists) **Index Rail** (on by default: the A–Z rail on Songs, Artists, Radio countries and the Albums list in Title order) and **Section Headers** (on by default: the section letters and the pinned header; off closes the rows up), **Folder Album Cover** (on by default: Folders rows show a cover where the folder has one), landscape Cover Flow, Volume Buttons (the volume buttons move between albums in Cover Flow; off by default), **Podcasts** (opens a page: **Podcast Discover**; **Directory**, Apple Podcasts, the default, or Podcast Index, where podcast searches and show look-ups go, never both, Discover's charts always come from Apple; and **Podcast Region**; Directory and Region are dimmed while Podcast Discover is off) and **Scrobbling** (see below) |
| Now Playing | Cassette Theme: Normal, Chrome, Metal or Auto (the default), applies next time Cassette Mode opens. Auto picks the tape by the track: Normal for MP3 and other lossy files, Chrome for CD-quality lossless, Metal for hi-res and DSD (those two also get a gold sticker in every theme); Vinyl Record and Base; Lyrics Text Size (its own card): Small, Medium or Large (the default) for the lines of the lyrics page, 22, 26 or 30 px (an open Now Playing takes a change when you return to it); Idle Display (last card): what Now Playing shows after 10 seconds, Off, Album Cover, Cassette, Vinyl or Lyrics (Off is the same switch as Playback Settings > Cover mode) |
| Playback | **EQ** opens the [Equalizer](#equalizer). **Playback Settings** is one page of three cards (the settings stock keeps in its Playback Settings list, now in our style): Playback has **Play Mode** (List Play, Repeat Track, Shuffle, Repeat All), **Gapless**, **Resume** (Off, Track, Location: where playback resumes after a restart), **Folder Skip** and **Continue Playing**: Off (the default) or Next Albums: when an album you started from Albums, an artist's albums or Cover Flow ends, the next album in that page's order plays on (with a short gap between albums; not with Repeat or Shuffle on, and not from Songs or Search); Volume has **Gain** (Low or High; dimmed while Line Out is on, as in stock), **Max Volume** (a page showing the number with a slider, 0 to 100, and - and + buttons: the volume keys stop there, and a volume above it is lowered to it at once; 0 is allowed), **Default Volume** (the volume at the next start: a Volume Memory switch, on keeps the last volume, and a slider 0 to 100 that is dimmed while the switch is on; the row says Memory or the number), **Channel Balance** (a slider from L to R, the centre in the middle, with L and R buttons; the row says L3, 0 or R2; it does nothing on Line Out or USB audio, as in stock) and **ReplayGain** (Off, Track, Album); Output has **Digital Filter** (the DAC's eight filters), **DSD Output Mode** (D2P, DOP, Native; on a USB DAC the song restarts where it was), **USB Volume** (Fixed or Variable) and **Digital Output**. Every setting is the same one stock's pages show and takes effect at once (Default Volume at the next start); the three volume pages use stock's own slider code, so a drag saves as often as stock's did |
| System | **Display** (the brightness slider; Screen Timeout: Never, 15s, 30s, 1min or 5min; **Lock Screen**, below; LED Light: Off, Green or Blue; Follow Screen: the light goes dark with the screen), **Buttons & Power** (**Button Lock**: Off, Lock Volume Only, Lock Buttons Only or Lock Volume & Buttons, only while the screen is off, the same setting as the Control Center key-lock tile and All System Settings; **Tap to Wake**: touch the screen to wake it, the touch panel decides whether one or two taps; **Auto-Standby**, off after 5 minutes with nothing playing, and **Auto-Shutdown**: Off, 1, 3, 5 or 10 minutes with nothing playing; only one of the two is on at a time, turning one on turns the other off), **Appearance** > **Background** (Black, or Tinted: with an accent chosen, the dark greys of every page, card and sheet take a 12 % wash of it; covers and cover-coloured pages keep their look) and **Accent** (the main menu's icons show in the accent; Neutral, Red, Orange, Green, Teal, Purple or Champagne: tints pressed rows and their icons, switches that are on, the lit pull-down tiles, sliders, progress bars (including the Home cache pill and the refresh and update download dialogs), the pressed rows of the menu sheets and cards, the picker check, the selected marks when you select songs, the index rail's selected letter, the EQ pages' sliders and curve and the download progress rings; applies at once), Display > **Lock Screen** (Enable; the lock screen shows a short date in your language over the clock, such as Wed, Nov 11; Wallpaper: the default or one of up to five pictures you copy to `lockscreenimage` on the card, JPG or PNG, 320 x 480, under 1 MB, the chosen one framed in the accent; Show Time; Player Style: Large Cover or Mini Player, a bar like Home's at the bottom; Custom Wallpaper explains the pictures. All System Settings > Display > Lock Screen opens the same page) and **Control Center** (show, hide and reorder the eight tiles of the status bar swipe-down panel), Language (under All System Settings; texts the original firmware showed in English in other languages, such as Look up Artist, Look up Album, the sort orders and the digital filters, are translated), Keyboards, **Battery** (**Battery Percentage**, off by default, shows the exact charge beside the battery icon, in the status bar and on the lock screen; **Charge Limit** stops charging at 80, 85, 90 or 95 % while the player is on and resumes about 5 % lower, 100 % (the default) is no limit, and a switched-off player charges fully) and About (firmware, device, network and storage details; **Software Update** is the row under the version) |
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

**Screenshot** asks first: leave the page within five seconds to capture another screen.
Cancel during the countdown if needed. Pictures are saved in the card's `screenshots` folder.

## Equalizer

**Settings → Playback → EQ** opens the Equalizer. Its switch turns the EQ on or off; off, playback
is unchanged. The EQ works at every sample rate and on every output; DSD plays without it.
While the switch is on, the status bar shows **EQ** after the volume.

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
music stops the radio. Stations play over Bluetooth too. Stations are `Radio/favourites.m3u` on the card; the `...` on the My Stations page has Import from Card, which adds the stations of
every other `.m3u`, `.m3u8` or `.pls` in `Radio/` that are not there yet (your files are never changed).

**Subsonic** (main menu Extras > Subsonic) plays from a Subsonic-compatible server such as Navidrome, Gonic or Airsonic. Tap **Add Server** and enter the server address (start it with `http://` or `https://`; a port and a subpath are fine), your username and your password, then tap **Sign In** (the password itself is not kept on the card, only a sign-in token for that server). A line under the card says what went wrong: "Incorrect username or password", "Can't connect to the server", or a certificate error. A certificate that is not trusted (a self-signed server) is not supported; on a home network use `http://`. To change the address or the name later, leave the password field empty and the saved sign-in is kept. The token is stored on the card (`.m1plus/subsonic.conf`) and opens the server like the password does, so make a dedicated server account for the device.
The root page's status line under the title reads **Synced** (with its age), **Syncing…**, **Updating library…**, **Loading covers…**, **Loading artist images…** (the library keeps filling in the background; you can browse meanwhile) or **Not Connected**; while songs download it reads **Downloading 12 songs**, and **12 downloads waiting** when they wait for Wi-Fi. The six rows are Albums, Artists, Songs, Playlists, Favorites and Downloaded. The `...` card has **Sync Now** and **Server Settings** (server, username, password, Sync Now and Sign Out); the magnifier searches the server. Tap a song to stream the original file (nothing is transcoded). DSD files do not stream: tapping one asks **Download to Play?**.
A server album's page has a `...` with **Download Album**, which queues every track not yet on the card (one message tells how many). A song's `...` sheet has Play Next, Play After, Download, Favorite and Get Info. Favorites are the server's own stars and stay in sync with it. Downloads go to `Subsonic/<artist>/<album>/` on the card (files named by track number and title), one at a time, and show up in the local library as well, like music you copied. A small ring shows progress and Cancel Download or Remove Download from the sheet stops it or deletes the file. The waiting downloads are kept on the card: when Wi-Fi drops or the device restarts they wait, and they go on when you open the Subsonic page with Wi-Fi up (a download that stopped half-way resumes where it was). **Downloaded** lists them and works offline; while songs are still to come they are at its top under **Downloading** (the one that runs first, then the ones that wait, in order), and **Clear** beside that title cancels them all (the finished downloads stay; one song is cancelled from its `...` sheet). It works also after **Sign Out**, which keeps the downloads and clears only the server's cache. Without Wi-Fi, songs that are not downloaded are dimmed. A song you play for half its length (or four minutes) is reported to the server as played, so its play count there, and Last.fm or ListenBrainz if the server is linked to them, stay up to date; this needs Wi-Fi while the song plays.
Limits: the Songs list shows the first 10,000 songs, a play queue holds the list in its order, up to 500 songs (from the one you tapped when the list is longer), and a playlist or favourites list up to 3,000 songs.

**Cassette Mode** is a landscape Now Playing screen. Tap the cassette to pause/resume and the
top-left screw to close. The status line shows the format (FLAC 24/96, MP3 320, DSD64). Change its
theme under Settings → Now Playing, where **Idle Display** can also open it (or Vinyl Mode, or the
lyrics page) after 10 idle seconds on Now Playing.

**Lyrics idle display** (Settings → Now Playing → Idle Display → Lyrics) fills the screen (no status bar) with the cover, title and
artist over the synchronized lyrics after 10 idle seconds. Tap anywhere to close it, drag to browse
the lyrics (they come back to the current line after 3 seconds). The text size follows **Lyrics Text
Size**. A track without lyrics at that moment opens the Album Cover page instead.

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

**Podcasts** reads local episodes from `Podcasts/<Show>/` on the card (up to 100 shows). The page shows the 10 most recently updated shows; with more, **See All (N)** under them opens the list of every show. Open a show, then an
episode; its button offers Play or Download. The Podcasts page's **…** menu has **Refresh All** (it shows when any show has a feed; its grey value is how long ago the shows were refreshed) and, with a subscriptions or OPML file on the card, **Import from Card**; the grey line under the page title only tells when the last refresh was (or **Refreshing 2/5…** while one runs). A show that was refreshed before keeps its **Updated …** line under its cover when a refresh fails (the reason is shown briefly); one never refreshed shows the reason. Use an episode's **…** menu to mark it played
or unplayed. A show's **…** menu has **Episode Order**: **Newest First** (the default) or **Oldest First**, the order of its list and of the queue that follows the episode you start (Oldest First suits a series); a tap switches it. **Filter** (also in the **…** menu) hides what you do not need on a long list: **All**, **Unplayed** (every episode not marked played, a half-played one included) or **Downloaded** (the ones on the card); each tap goes to the next. The list keeps the show's order and everything on the page (a tap, Select Episodes, Mark All as Played, Delete, the queue after the episode you start) works on the rows that are shown; with nothing to show it says **No unplayed episodes** or **No downloaded episodes** and the **…** menu is there to switch back. An episode you mark as played stays in the list until it is made again (a filter change, a refresh or a finished download). The Filter is not saved: opening another show, or going back to Podcasts, starts at All; the episode page and Now Playing keep it. The Latest Episode button, the search in the show and Continue Listening ignore it. The **Downloaded** row on the Podcasts page opens the list of what is downloading and what is on the card; while something is downloading and something is on the card, the downloads come first under an **In Progress** header and the downloaded episodes follow (with one kind alone the list simply follows the title). A download that runs or waits has a small ring before its line (the arc shows the progress, a square inside it means it is running) with the percentage beside it; a tap on the row pauses it (the part already loaded is kept) and another tap resumes it. Each of these rows has a **…** with **Pause**, **Resume** or **Retry** (by its state) and **Cancel Download**, which stops the download and deletes the part already loaded, without asking. A download keeps going while you search, refresh, browse Discover, look up a cover or check for an update. A show's page lists its 20 most recent episodes; the last row, **See All**, opens a page with every episode (the show's name at the top, **Back** returns to where you were on the show's page; the page has the same episodes, buttons, Select Episodes, Mark All as Played, Episode Order and Filter, which are the show's own). A subscription keeps only its newest episodes at first: the first tap on **See All** fetches the show's feed again (Wi-Fi needed) and opens the page when it has arrived, with every episode the feed has, up to 2000. The row counts the episodes as they arrive (**Loading… 340**) with a small spinner turning beside it (also on **Search All Episodes** while it loads); if the fetch fails it says why and **Tap to Retry** (for example **Can't connect · Tap to Retry**). Going to another page of Podcasts lets it carry on (the page does not open then; **See All (93)** is there next time); closing Podcasts stops it. Once the episodes are fetched the row reads **See All (93)**, the number of episodes, and a tap opens the page at once; a refresh adds the new episodes to that list. A show of copied files with more than 20 episodes has **See All (N)** too. Downloads, played marks and the queue work on those as on any episode; downloaded old episodes also show on the show's page. To find one episode of a show, tap the magnifier at the top right of its page and type: the list follows the typing (letters and spaces match anywhere in the title, a number such as 37 matches Ep 37 and not 137, Chinese titles match by the initials of their pinyin), a tap opens the episode and Back returns to the results, and playing queues the show's own order from that episode. The search covers every episode once they are fetched. For a subscription that has not fetched every episode yet, the results end with **Search All Episodes**: a tap does what the first **See All** does (the row reads **Loading…** and the count; typing and opening results go on meanwhile), and when the list arrives the same search shows the matches among all of them. To find shows online, connect to Wi-Fi, then use the **Discover** row on the Podcasts page (on unless **Settings → Library → Podcasts → Podcast Discover** is off): the top 25 shows and top 25 episodes of your region (**Settings → Library → Podcasts → Podcast Region**, Automatic by default), the magnifier to search (the Podcasts page's globe opens the same search directly), and **Subscribe** on a show's preview.

**Wi-Fi Transfer:** turn it on under **System settings → Network Service → Wifi file transfer**,
then open the address it shows (port 8888)
in a browser on the same network. M1+ Music replaces the stock page: it lists the whole card: sort, filter, select files to
download, rename, move or delete, create folders, and upload files or folders (drag them onto the
page). The eye button in the header shows hidden files.

**Search** opens the same library search as the Songs page's Search button. It is hidden from
the main menu by default.

**Scrobbling** (off by default; turn it on in **Settings → Library → Scrobbling**, whose page holds all the scrobbling settings; the row on the Library page says On or Off): every song you listen to
(half of it, or 4 minutes) is added to `.scrobbler.log` at the root of the card. Upload it to Last.fm or ListenBrainz from a computer with any
`.scrobbler.log` uploader, or send it to ListenBrainz and Last.fm from the player (below). Songs played only while a stock Shanling screen is open may be missed; see [details](modules/scrobble.md).

**ListenBrainz and Last.fm**: the player can send the log to your ListenBrainz account, your Last.fm account, or both, over Wi-Fi.
You sign in with one plain text file on the card; nothing is typed on the player.

1. On a computer, make a plain text file named `scrobble.ini` at the root of the card. Put in the section of each service you use:

   ```
   [LISTENBRAINZ]
   TOKEN=0f8fad5b-d9cb-469f-a165-70867728950e

   [LASTFM]
   USER=your-user-name
   PASSWORD=your-password
   API_KEY=0123456789abcdef0123456789abcdef
   API_SECRET=fedcba9876543210fedcba9876543210
   ```

   - **ListenBrainz**: sign in at listenbrainz.org, open your settings and copy the **User token** (36 letters, digits and dashes) after `TOKEN=`.
   - **Last.fm**: your user name and password, and an API key and secret of your own: create an API account at last.fm/api
     (any name will do) and copy the two values it shows. All four lines are needed.

   One value a line, nothing else on the line, no quotes. Capitals, spaces around `=`, Windows line ends and comment lines
   starting with `;` or `#` are all fine; keep the file small (under 4 KB) and saved as plain text (UTF-8).
2. Put the card back and open **Settings → Library → Scrobbling**. No restart is needed: the player reads the file whenever that page opens
   and before every upload. With Wi-Fi connected the accounts are checked at once, and the **ListenBrainz** and **Last.fm** rows
   show your user names. "Not Set" means the player found no complete account in the file; "Invalid Token" (ListenBrainz) or
   "Sign-in Failed" (Last.fm) means the service refused it: correct the file. Each row opens a page with the account's state and a
   reminder of what goes in the file.
3. Tap **Upload Scrobbles** whenever you want to send the log. It goes to every service that is set up. It needs Wi-Fi, and the
   card must not be in use by a computer over USB. A message tells how many listens were sent. The Scrobbling switch does not
   have to be on for this: with it off, the account rows, Auto Upload and Upload Scrobbles still work, so a log already on the card can be sent.
4. Or turn on **Auto Upload** (above Upload Scrobbles, off by default) and the player sends the log by itself: while music plays
   and Wi-Fi is connected, about ten minutes after a new listen was logged, so an album goes up in one or two uploads. It works in
   the background and shows no message; it never switches Wi-Fi on, and without a connection the listens simply wait for the next
   time you play music on Wi-Fi. It needs an account and the Scrobbling switch on (only songs logged since the player was switched
   on start it; older ones in the log go along). A service that refuses its account is left out until you correct the file. After
   an upload that failed the player waits half an hour before it tries again. Upload Scrobbles still works at any time; while an
   automatic upload runs it answers "Already uploading".

The file is the only place the player keeps your sign-in, so it travels with the card, and anyone who has the card can read it.
To sign out, delete the service's lines (or the whole file) on a computer. The player never shows the token or the password and
changes only one thing in the file: it adds a `USER` line under `[LISTENBRAINZ]` with your user name once ListenBrainz has
confirmed the token.

Listens that were sent leave `.scrobbler.log` and are kept in `.scrobbler.log.sent` on the card. With two services a listen
leaves the log once both have answered for it; if one of them cannot be reached the listens wait and go to both again next time
(neither counts a listen twice). A listen every service refuses for good is moved to `.scrobbler.log.rejected`, where you can
look at it. If an upload fails, what was not sent stays in the log for the next try.

For a missing feature, enable it through **Settings → Home Screen → Main Menu**, or find it under Extras.
