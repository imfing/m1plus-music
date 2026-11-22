# Library and playback

[User guide](guide.md) · [Settings](settings-guide.md) · [Features and extras](features-guide.md)

[Browse](#browse-your-library) · [Playback and queue](#playback-and-queue) ·
[Artist photos](#artist-photos) · [Split Artists](#split-artists) · [Split Genres](#split-genres)

## Browse your library

Drag a list to scroll; tap a row to open it or play a track.

| Page | What you can do |
|---|---|
| Cover Flow | Drag through albums. Tap a side cover to centre it, then tap it again to open the album. |
| Albums | Use **…** to switch grid/list or sort by Title, Artist, Recently Added or Year. |
| Artists | Use **…** to switch Artist/Album Artist. Open an artist to play or shuffle their songs. |
| Songs | Use Search or the A–Z rail. Use **…** to select songs or change the sort order. |
| Playlists | Open a playlist to play or shuffle it. Use the list-plus button to create, import, export or delete playlists. |
| Folders | Open **Extras → Folders** to browse the card's folders and audio files. |
| Shuffle | Open **Extras → Shuffle** to shuffle songs, albums or folders. |

**Recently Added** lists new songs; its **…** switches to new albums. The Artists page's **…**
also offers artist photos, grid/list and album order. Composers are under Extras.

In Albums, Year order groups the list by year and the grid by decade. The list has a decades rail;
albums without a year appear under Unknown. View and sort choices are remembered.

An album whose tracks carry disc numbers in their tags shows a **Disc 1**, **Disc 2**… heading
before each disc, and numbers each disc's tracks from 1. Run **Update Library** after tagging.

### Edit a playlist

Open a playlist and tap **… → Rename** to give it a new name; a pinned playlist keeps its pin. To
take one song out, tap its **…** (or long-press it) and choose **Remove from Playlist**. To take out
several, choose **… → Select**, mark them and tap the trash can. Only this playlist changes; the
songs stay in your library and on the card.

### Repair a playlist

After moving music files, run **Update Library**, then open the playlist and choose **… → Clean Up
Playlist**. It repairs moved paths and offers to remove entries no longer on the card. Only that
playlist changes; no music files are deleted.

### Folder covers

**Settings → Library → Folder Album Cover** shows cached album art in Folders when available. A
folder uses the cover of the first library song inside it, including subfolders; a file uses its
album's cover. Rows without a cached cover keep their icon.

## Playback and queue

### Now Playing

- Tap **…** for playback options, **Look up album**, **Look up artist** and **Display Mode**.
  For display controls, see [Display modes](features-guide.md#display-modes-and-pod).
- Swipe to the third page for track details, including format, quality and file location. Drag to
  scroll; the page returns to the top when reopened.
- Open **… → More** for **Sleep Timer** and online [cover and lyrics lookup](features-guide.md#cover-and-lyrics-lookup).
- An amber **LO** in the status bar means Line Out is on.

For Subsonic streams, the lookup options open the server's album and artist. Streaming tracks
cannot be added to a local playlist or deleted, and are not added to local Recently Played or Most
Played lists.

### Set a sleep timer

Open **Now Playing → … → More → Sleep Timer**, or use the Sleep Timer Control Center tile. Choose
Off or a time from 15 minutes to 2 hours. The player turns off when time runs out; **Time Left**
shows the remaining hours and minutes. This is the same timer as **All System Settings → Power**.

### Track actions

On an album or Songs list, tap a track's **…** or long-press its row. The menu is in groups:
**Pin Song**, **Add to Playlist**, **Favorite** and **Get Info**, then **Play Next** and **Play After**. A
favorited track offers **Undo Favorite** instead. In a playlist, **Remove from Playlist** (in red) is the last choice.

### Album actions

Touch and hold an album on **Albums**, the **Recently Added** album grid, **Recently Played** or a Home pin for
**Play** and **Shuffle**, then **Pin Album** and **Add to Playlist** (the whole album), then **Play Next** and
**Play After**. On an album's page, **…** has the same choices without Play and Shuffle (the buttons under
the cover), and **Select** last. Get Info shows the track's format, quality, length, size and path.

### Manage Up Next

Open the Queue page to see tracks in their playback order, including when Shuffle is on.

- Tap **…** on an Up Next row to move it to Play Next or Play After, or remove it from the queue.
  Removing it does not delete the file.
- Tap **Clear** to remove all songs after the playing one.
- Row actions and Clear are unavailable during folder playback (from Folders, Podcasts or
  Audiobooks) or while DLNA is on.

## Artist photos

### Add a photo from the card

1. Name the photo `artist.jpg`, `artist.jpeg` or `artist.png`.
2. Put it in an album folder, or in a parent folder containing only that artist's albums. For
   example, put `artist.jpg` in `Music/Adele/` beside `21/` and `25/`.
3. Open the artist's page, or choose **Settings → Library → Rebuild Artist Photos** to check every
   artist. Home also looks for photos after a library change.

A mixed-artist folder such as `Music/` or `Various Artists/` is not used; disc folders such as
`CD1` are skipped. Photos follow the artist tags. A square image fits best; other shapes are cropped.

### Find a photo online

1. Connect to Wi-Fi and open the artist's page.
2. Choose **… → Find Artist Photo**, tap a result, then **Use This Photo**.

Results come from Deezer and NetEase Cloud Music. Your choice stays until you pick another;
rebuilding photos or adding a card image does not replace it. A Subsonic server supplies its own
artist photos, loaded in the background after a sync.

## Split Artists

Turn on **Settings → Library → Split Artists** to list a song tagged with multiple artists under
each name. Search, Look up artist and playback from an artist page use the split names too; Look up
artist opens the first name.

- Choose separators on the same settings page. The defaults are `;`, `/`, `&` and `feat.`; word
  separators need spaces around them.
- Names such as `AC/DC` and `Simon & Garfunkel` are protected. Add your own exceptions, one per
  line, to `artist-exceptions.txt` at the card root; blank lines and `#` comments are ignored.
- Reopen an already open Artists page to see a change. After changing the switch, use **Rebuild
  Artist Photos**. A name appearing only after another needs an online photo; a combined name
  without its own photo can use the first artist's.
- Album Artist view, Genres, Composers, Subsonic, Pod and Continue Playing order are not split.
  After a restart, Memory Playback resumes the same track in the whole library, not the artist list.

## Split Genres

Turn on **Settings → Library → Split Genres** to list a song whose genre tag names several genres,
such as `Rock; Pop`, under each name on the Genres page. A genre opens the songs of every tag that
names it.

- Choose separators on the same settings page: `;`, `/`, `&`, `,` and `+`. Only `;` is on by
  default, so `Rock/Pop` and `Jazz, Blues` stay whole; turn on the others if your tags use them.
- Common genres that contain a separator, such as `R&B`, `Drum & Bass`, `Rock & Roll`,
  `Stage & Screen`, `Singer/Songwriter` and `Folk, World, & Country`, are never split. Names
  that join two genres, such as `Hip-Hop/Rap` or `Pop/Rock`, split once `/` is on.
- Add more names that must never split, one per line, to `genre-exceptions.txt` at the card root; blank
  lines and `#` comments are ignored. Names are matched ignoring upper and lower case.
- Reopen an already open Genres page to see a change. Genres on albums and in Search are not
  split. After a restart, Memory Playback resumes the same track in the whole library, not the
  genre list.
