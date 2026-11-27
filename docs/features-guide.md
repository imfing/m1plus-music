# Features and extras

[User guide](guide.md) · [Settings](settings-guide.md) · [Equalizer](equalizer-guide.md)

[Radio](#radio) · [Subsonic](#subsonic) · [Display modes and Pod](#display-modes-and-pod) ·
[Podcasts](#podcasts) · [Audiobooks](#audiobooks) · [Search](#search) ·
[Scrobbling](#scrobbling) · [Wi-Fi Transfer](#wi-fi-transfer)

For a missing feature, enable it through **Settings → Home Screen → Main Menu**, or find it under Extras.

## Radio

Open **Extras → Radio** to play internet stations over Wi-Fi. To put it on the main menu, use
**Settings → Home Screen → Main Menu**.

1. Choose **My Stations**, **Recently Played** or **Radio Browser**. Radio Browser lets you browse
   top stations, countries and genres, or search radio-browser.info by name.
2. Tap a station to play. When the station sends the playing song as "Artist - Title", Radio Now
   Playing, the mini player and the lock screen show it as a song: the title on top, the artist
   under it. Otherwise they show the station's name over its text or stream. Previous/next moves
   along the list. Starting local music stops the radio. Bluetooth audio is supported too.
3. Use **…** on Radio Now Playing to add or remove the station from **My Stations**.

To manage **My Stations**, use its **…** menu:

- **Select** marks stations; **Delete** removes them after asking.
- **Sort by Name** puts the list in A–Z order.
- **Add by URL** takes a stream address (`http://` or `https://`), then a name, on a two-row card.
  Tap a row to go back to it.
- **Import from Card** adds the playlists in `Radio/` (below).
- **Grid** and **List** switch the station view. **Recently Played** has the same two rows and
  **Clear History**.

You can also hold a station and choose **Remove from My Stations**.

Saved stations live in `Radio/favourites.m3u` on the card. To import your own lists, copy `.m3u`,
`.m3u8` or `.pls` files into `Radio/`, then choose **My Stations → … → Import from Card**.
It adds stations not already saved and leaves your source files unchanged.

## Subsonic

**Extras → Subsonic** plays music from a Subsonic-compatible server such as Navidrome, Gonic or Airsonic.

### Connect a server

1. Connect to Wi-Fi and open **Extras → Subsonic → Add Server**.
2. Enter the server address, username and password. Start the address with `http://` or `https://`;
   a port and a subpath are supported.
3. Tap **Sign In**, then browse while the library, covers and artist images load in the background.

A message under the card explains sign-in, connection or certificate errors. Untrusted certificates,
including self-signed certificates, are not supported. Use trusted HTTPS where possible; use HTTP
only on a trusted home network, as it is unencrypted.

The card stores a sign-in token, not the password, in `.m1plus/subsonic.conf`. Anyone with that token
can access the server, so use a dedicated server account for the player. To edit the address or name
without replacing the saved sign-in, leave the password field empty.

### Browse and play

- Open **Albums**, **Artists**, **Songs**, **Playlists**, **Folders** or **Favorites**, or use the magnifier to search.
- **Folders** browses the server's own folder tree. One music folder starts with an A–Z index;
  several show the music folders first. Tap a folder to enter it, or Back to return. A level with
  songs offers Play and Shuffle; a tap plays from that song, and its **…** opens the song menu.
  Previously loaded levels appear at once and refresh in the background.
- Tap a song to stream the original file; there is no transcoding. DSD needs a download first:
  tapping it asks **Download to Play?**.
- A song's **…** menu offers **Play Next**, **Play After**, **Download**, **Favorite** and **Get Info**.
  Favorites use the server's stars and stay in sync with it.
- The main page's **…** menu has **Sync Now** and **Server Settings**, where you can edit the account
  or **Sign Out**.

The status under the title shows the sync age, sync/library/artwork progress, or **Not Connected**.
During downloads it shows how many songs are downloading or waiting for Wi-Fi.

A song played for half its length or four minutes is reported to the server. This updates its play
count and any scrobbling services linked to the server; Wi-Fi must be connected while it plays.

### Download and listen offline

1. Choose **… → Download Album** on an album, or **… → Download** on a song.
2. Open **Downloaded** to see finished files and the **Downloading** queue. A ring shows progress;
   the active song comes first, followed by waiting songs in order.
3. Play downloaded songs with or without Wi-Fi. Songs not downloaded are dimmed when offline.

Files download one at a time to `Subsonic/<artist>/<album>/`, named by track number and title.
They also appear in the local library. Downloads survive a restart or lost connection: open Subsonic
with Wi-Fi connected to continue, including partially downloaded files.

- **Cancel Download** in a song's **…** menu stops it; **Remove Download** deletes its downloaded file.
- **Clear** beside **Downloading** cancels the whole queue but keeps finished downloads.
- **Sign Out** clears the server cache but keeps downloads, which remain accessible in **Downloaded**.

### Limits

- Songs lists show up to 10,000 songs.
- A play queue holds up to 500 songs in list order; for a longer list it starts at the song you tapped.
- Playlists and favorites lists hold up to 3,000 songs.

## Display modes and Pod

Open **Now Playing → … → Display Mode** to choose Cassette, Vinyl, VU Meter or Lyrics Mode.
To open one automatically after 10 idle seconds, choose it under **Settings → Now Playing → Idle
Display**. Scrolling Now Playing's lyrics counts as activity: the countdown starts when the lyrics
return to the current line.

### Cassette Mode

Cassette Mode shows a landscape cassette and a status line with the audio format.

- Tap the cassette to pause or resume; tap the top-left screw to close.
- Choose a theme under **Settings → Now Playing → Cassette Theme**.

### Vinyl Mode

Vinyl Mode shows a turntable with the cover as the spinning record label.

- Tap the record or the large key to pause or resume; use the side keys to skip.
- Tap the top-left chevron to close.

### VU Meter Mode

VU Meter Mode shows two needle meters that follow the playing audio. The PEAK lamps light briefly
on peaks, and the reference level adjusts to the music.

- Use the keys to pause, resume or skip. Tap above them to pause or resume, or tap the top-left
  chevron to close. When Idle Display opened the mode, tapping above the keys closes it instead.
- The needles rest while paused and do not move for DSD.

### Lyrics Mode

Lyrics Mode fills the screen with the cover, title and artist over synchronized lyrics; there is no
status bar.

- Drag to browse the lyrics; they return to the current line after 3 seconds. Tap anywhere to close.
- Change the size under **Settings → Now Playing → Lyrics Text Size**.
- If a track has no lyrics, Lyrics Mode is unavailable; Idle Display opens Album Cover instead.

### Cover and lyrics lookup

**Cover & Lyrics** (Now Playing → … → More → Cover & Lyrics, needs Wi-Fi) looks up the playing
album's covers (iTunes, then Deezer) and its lyrics (LRCLIB). It is not offered for podcast episodes or audiobooks. Tap a cover to use it for the album
everywhere; Save Lyrics writes `<song>.lrc` next to the song (Replace Lyrics when one is there).
The playing song shows saved lyrics at once.

### Pod

Open **Extras → Pod** for a virtual iPod.

- Slide around the wheel to browse and tap its centre to select.
- The main menu follows the iPod classic: Music, Cover Flow, Podcasts, Settings, Shuffle Songs, and
  Now Playing while something plays. Music holds Cover Flow, Playlists, Artists, Albums, Songs,
  Genres and Composers.
- In **Cover Flow**, turn the wheel to slide through the albums (it follows Cover Flow's sort order
  and **Start At** setting). Tap the centre to flip the album
  over and see its songs; tap a song to play it, or tap MENU to flip back. Press the bottom button
  on an album to play it from the first song.
- Tap MENU to go back. Hold it to return to the Pod's main menu, then tap it to close Pod.
- Use the bottom button to pause or resume and the side buttons to skip tracks. On the Pod's Now
  Playing screen, hold a side button to rewind or fast-forward; let go to play from there.
- On Now Playing, turn the wheel to change the volume; the bar shows the level for 2 seconds.
- On Now Playing, tap the centre to step through more screens, then back to the progress bar:
  - **Scrubber:** turn the wheel to move through the song; the song jumps there when you lift your finger.
  - **Shuffle:** turn the wheel to choose Off, Songs or Albums. Albums plays each album in order,
    the albums in random order.
  - **Lyrics:** shown when the song has a `.lrc` file beside it. Turn the wheel to scroll.
  The scrubber and shuffle screens go back to the progress bar after 3 seconds without a turn.

## Podcasts

Play local episodes from `Podcasts/<Show>/` on the card, or subscribe to shows over Wi-Fi.
The library supports up to 100 shows. The main page shows the 10 most recently updated;
**See All (N)** opens the rest.

### Start listening or subscribe

1. Open **Podcasts**, choose a show, then an episode.
2. Tap **Play** for an episode on the card, or **Download** to get it first. An episode's page
   shows its date, length and size; the list shows its date and length.
3. To find shows online, connect to Wi-Fi and open **Discover**. Browse the region's top 25 shows
   and episodes, or tap the magnifier to search, then **Subscribe** on a show's preview.

The Podcasts page's globe opens online search directly. Discovery, search directory and region
are set under **Settings → Library → Podcasts**; the region defaults to Automatic.
Discover is hidden when **Podcast Discover** is off.

### Refresh and import shows

Open the Podcasts page's **…** menu:

- **Refresh All** checks shows with feeds for new episodes. It appears when at least one show has a feed.
- **Import from Card** appears when a subscriptions or OPML file is on the card.

The grey line under the page title shows the last refresh age or progress, such as **Refreshing 2/5…**.
If a show fails to refresh, the reason appears briefly; its previous **Updated …** date stays.
A show never refreshed shows the error instead.

### Order, filter and played marks

Use a show's **…** menu to change its list:

| Option | What it does |
|---|---|
| Episode Order | Switch between **Newest First** (default) and **Oldest First**, for both the list and playback queue. Oldest First suits a series. |
| Filter | Cycle through **All**, **Unplayed** (including partially played episodes) and **Downloaded**. |

Use an episode's **…** menu to mark it played or unplayed. While an episode plays, Now Playing's **…**
offers Go to Podcasts, Playback Speed, Sleep Timer and A-B Repeat. Now Playing's bottom row becomes
speed, back 15 seconds, play, forward 30 seconds and queue: tap the speed (**1×**) to step through
1×, 1.25×, 1.5× and 2× for that show. The hardware keys still change episode. Swipe across the
cover for the episode's notes, and swipe again for file details.

Selection, Mark All as Played, deletion and the queue after the episode you start apply to the
visible rows. If a filter leaves no results, use **…** to switch back. An episode marked played
stays visible until the list rebuilds, for example after a filter change, refresh or finished download.

The filter stays while you visit an episode or Now Playing, but resets to All when you open another
show or return to Podcasts. **Latest Episode**, search within a show and **Continue Listening**
ignore the filter.

### Manage episode downloads

Open **Downloaded** on the Podcasts page. When both active downloads and finished episodes are
present, downloads appear first under **In Progress**.

- A ring and percentage show download progress; a square inside the ring means it is running.
- Tap a download row to pause it, keeping the partial file; tap again to resume.
- Its **…** menu offers **Pause**, **Resume** or **Retry**, depending on its state.
- **Cancel Download** stops it and deletes the partial file **without asking**.
- To free space, tap **…** at the top right, then **Delete Played Episodes**. After you confirm,
  every downloaded episode you have finished is deleted, except the one playing. The episodes stay
  in their shows and can be downloaded again. This option appears once the list has loaded and at
  least one downloaded episode is played.

Downloads continue while you search, refresh, browse Discover, look up covers or check for an update.

### Browse all episodes

A show's page lists its 20 most recent episodes, plus downloaded older episodes.
Tap **See All** for the complete list; it shares the show's order, filter, selection and playback
controls. Back returns to your previous position on the show's page.

For a subscription, only the newest episodes are kept at first:

1. Connect to Wi-Fi and tap **See All** to fetch the feed's full list, up to 2,000 episodes.
2. The row shows a spinner and a count, such as **Loading… 340**. If it fails, tap **Tap to Retry**.
3. Once loaded, **See All (N)** opens the list immediately. Later refreshes add new episodes.

You can browse other Podcasts pages while it loads; the full list will not open automatically
if you leave the show's page. Closing Podcasts stops the fetch.
A show of copied files with more than 20 episodes also has **See All (N)**.

### Find an episode within a show

Tap the magnifier on the show's page and type. Results update as you type:

- Letters and spaces match anywhere in the title.
- A number such as 37 matches Ep 37, not 137.
- Chinese titles match by pinyin initials.

Tap a result to open it; Back returns to the results. Playing starts the queue from that episode
in the show's order, not just among search results.

If a subscription's full list has not loaded, tap **Search All Episodes** at the end of the results
(Wi-Fi needed). You can keep typing and opening results while it loads. Once complete, the same
search covers every fetched episode.

## Audiobooks

Open **Extras → Audiobooks** (in the Library section) to listen to books on the card or download
public-domain books from LibriVox.

### Add your own books

1. Create `Audiobooks/` on the card.
2. Put each book in its own folder, with its parts as audio files. A single audio file also works.
3. For artwork, add `cover.jpg` or `folder.jpg` inside the book's folder. Without one, the player
   uses the picture embedded in the first file, or another picture in that file's folder.

Very long single `.m4b` or `.m4a` files can stall the player and are refused with a message.
Split such books into parts or chapters first.

### Play and resume

- **Continue Listening** resumes the book in progress you played most recently.
- Under **Books**, each row shows its progress or state, such as **Part 14 of 41 · 33%**, **Finished**
  or **Not started · 12 parts**. With more than 20 books, **See All (N)** opens the full list.
- Open a book and tap **Play**, **Resume** or **Play Again**. Resume returns to your saved position
  in the part you were listening to; tapping a part plays from it to the end of the book.
- **… → Playback Speed** cycles through 1x, 1.25x, 1.5x and 2x. The playing part shows a wave icon.
- While a part plays, Now Playing's bottom row is speed, back 15 seconds, play, forward 30 seconds
  and queue. Tap the speed (**1×**) to step through the speeds; the book plays its parts in order,
  and the hardware keys still change part. Swipe across the cover for the book's notes, and swipe
again for file details. Its **…** offers Display Mode, Playback Speed, Sleep
  Timer and A-B Repeat.

### Find and download LibriVox books

1. Connect to Wi-Fi and open **LibriVox** under **Discover** at the bottom of Audiobooks.
2. Browse Popular books, or tap the magnifier to search. Back returns to your position in Popular.
3. Open a book to see all its parts, then tap **Download**. The book and cover are saved in
   `Audiobooks/` and appear alongside your own books.

Parts not yet downloaded show their length and size; tap one to start downloading.
A ring and percentage show the active part's progress, and the book's row shows the current part
number. Finished parts can be played while the remaining parts download.

### Pause, resume or delete downloads

- Use **… → Pause Download** or **Resume Download** on the book's page.
- Before any part is available, the main button also offers **Pause**, **Resume** or **Retry**.
  Once parts are available, the status under the title shows download progress or why it stopped.
- **Delete Book** asks for confirmation, then removes downloaded files. It is unavailable while
  that book is playing. A folder containing files of your own is kept.

### Queue and download limits

- Tap **Download** on another book to queue it. Up to 16 books can wait; **Pause** removes a book
  from the waiting queue. Books download one after another.
- A shared problem, such as lost Wi-Fi or a full card, stops the queue and pauses waiting books.
- You can search, listen and download podcasts while a book downloads.
- **Keep Audiobooks or Podcasts open while downloading.** Otherwise the player may sleep and stop
  the download. Tap a part or **Resume** to continue.

Books stay out of the music Library, Shuffle, Recently Played and Daily Mix.
For technical details, see [Audiobooks](modules/audiobooks.md).

## Search

**Search** opens the same library search as the Songs page's Search button. Touch and hold a result
for its action menu (song, album, playlist or artist). It is hidden from the main menu by default.

## Scrobbling

Turn on **Settings → Library → Scrobbling → Scrobbling** to record listens; it is off by default.
A song longer than 30 seconds is added to `.scrobbler.log` at the card root once you have heard
half of it or four minutes. Seeks and pauses do not count as listening. Podcasts and songs with
an empty or Unknown artist are not logged; songs played entirely on a stock Shanling screen may also
be missed.
See [details](modules/scrobble.md).

You can upload that log from a computer, or send it to ListenBrainz, Last.fm or both from the player.

### Set up accounts

1. On a computer, create a plain-text file named `scrobble.ini` at the card root. Include the section
   for each service you use:

   ```
   [LISTENBRAINZ]
   TOKEN=0f8fad5b-d9cb-469f-a165-70867728950e

   [LASTFM]
   USER=your-user-name
   PASSWORD=your-password
   API_KEY=0123456789abcdef0123456789abcdef
   API_SECRET=fedcba9876543210fedcba9876543210
   ```

2. Replace the example values:
   - **ListenBrainz:** copy the **User token** from your settings at listenbrainz.org.
   - **Last.fm:** enter your username and password. Create an API account at last.fm/api and enter
     its key and secret; all four values are required.
3. Save as UTF-8, under 4 KB. Use one value per line without quotes; spaces around `=`, Windows
   line endings and comment lines starting with `;` or `#` are supported.
4. Reinsert the card and open **Settings → Library → Scrobbling**. With Wi-Fi connected, the
   account rows are checked and show your usernames. No restart is needed.

**Not Set** means no complete account was found; **Invalid Token** or **Sign-in Failed** means
the service refused it. Correct the file and reopen the page. Each account row also opens a page
with its state and a reminder of the required values.

The file contains your token and password in plain text: anyone with the card can read them. To
sign out, delete that service's section or the whole file on a computer. The player adds a `USER`
line under `[LISTENBRAINZ]` once the token is confirmed; it does not display the secrets.

### Upload listens

- **Manually:** connect to Wi-Fi, ensure the card is not in use by a computer over USB, then tap
  **Upload Scrobbles**. A message reports how many listens were sent. This works even if the
  Scrobbling switch is off, so an existing log can still be uploaded.
- **Automatically:** turn on **Auto Upload** (off by default). With an account set up, the player
  sends the log in the background whenever Wi-Fi is connected and listens wait in it, within about
  ten seconds, with music playing or not. A listen logged on Wi-Fi goes up right away. Listens
  logged without a connection, also before the player was last switched off, go up the next time
  Wi-Fi connects while the screen is on, for example when you wake the player at home. It never
  turns Wi-Fi on. A failed upload waits five minutes before retrying. A refused account is left
  out until you correct the file. Manual upload is still available; during an automatic upload it
  reports **Already uploading**.

The note under **Upload Scrobbles** shows the last upload, for example "Last upload: Today 14:32 ·
12 sent to ListenBrainz and Last.fm", also for automatic uploads. Every upload that sent something
is also one line in `scrobble-uploads` in the hidden `.m1plus` folder on the card (a text file; the
newest lines are kept, about 8 KB).

Sent listens move to `.scrobbler.log.sent`, those refused for good to `.scrobbler.log.rejected`;
unsent listens stay in the log for the next attempt. Details: [scrobbling](modules/scrobble.md).

## Wi-Fi Transfer

1. Connect to Wi-Fi and open **Settings → Network Services → Wi-Fi Transfer**, or tap the
   **Wi-Fi Transfer** tile in Control Center if you have added it. Playback stops while the page is open.
2. Open the address shown (port 8888) in a browser on the same network. On a phone, tap
   **Show QR Code** and scan the code with the camera instead of typing the address.
3. Leave the player page to turn Wi-Fi Transfer off.

The browser page lists the whole card: sort, filter, select files to download, rename, move or
delete, create folders, and upload files or folders (drag them onto the page). The eye button in
the header shows hidden files.
