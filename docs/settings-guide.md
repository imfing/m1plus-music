# Settings guide

[User guide](guide.md) · [Equalizer](equalizer-guide.md) · [Features](features-guide.md)

## Find a setting

Open **Extras → Settings**, then follow the path below. Paths start at Settings.

| To change… | Open |
|---|---|
| Wi-Fi or Bluetooth | **Wi-Fi** or **Bluetooth** |
| AirPlay, DLNA or Wi-Fi Transfer | **Network Services** |
| Main menu or Extras | **Home Screen → Main Menu** or **Home Screen → Extras** |
| Pull-down tiles | **Appearance → Control Center** |
| Library, covers, list navigation or Cover Flow | **Library** |
| Podcast discovery or scrobbling | **Library → Podcasts** or **Library → Scrobbling** |
| Cassette, vinyl, lyrics or idle display | **Now Playing** |
| Equalizer | **Playback → EQ**; see [Equalizer](equalizer-guide.md) |
| Playback, volume or output | **Playback → Playback Settings** |
| Brightness, lock screen or LED | **Display** |
| Button lock, track buttons, wake or shutdown | **Buttons & Power** |
| Accent colour or background | **Appearance** |
| Battery percentage, charge limit or history | **Battery** |
| Software updates, keyboard, date or language | **General** |
| Startup, screenshots or reset | **Developer** |

<!-- Screenshot: Settings overview showing categories and current values. -->

## Settings reference

Grey values on the right show the current setting. **All System Settings** opens the player's full
stock list, including Firmware Update, Regulatory, Format Storage and Reset.

### Wi-Fi

1. Open **Settings → Wi-Fi** and turn it on.
2. Choose a nearby network, or **Other…** for a hidden one.
3. Tap a network's info icon to see its full name. A saved network also offers **Auto-Join** and
   **Forget This Network**.

WPA3 and Enhanced Open are supported. WEP requires the stock Wi-Fi page with the kill switch
[enabled](install.md#disable-m1-music). All System Settings → Wi-Fi opens the same page (stock
with the kill switch).

### Bluetooth

Open **Settings → Bluetooth** to turn it on and choose **Audio Codec**: LDAC HQ, Standard or
Connection, aptX HD, aptX, AAC, SBC HQ or SBC. Changing the codec while connected asks before
reconnecting the device.

- **My Devices** lists paired devices; tap one to connect or disconnect. A check marks the connection.
- **Other Devices** lists nearby devices; tap one to pair and connect, or use **Search Again**.
- A paired device's info icon opens Connect or Disconnect, **Headset Volume** while connected,
  **Forget This Device**, and its full name.

Wi-Fi and Bluetooth can run together. Turning one on while the other is on warns that Bluetooth
audio may stutter. All System Settings → Bluetooth opens the same page (stock with the kill switch).

### Network Services

**AirPlay** and **DLNA** are switches; **SyncLink** opens the stock page. For card management in
a browser, open **Wi-Fi Transfer**; see [Wi-Fi Transfer](features-guide.md#wi-fi-transfer).

### Home Screen and Control Center

Recent Albums and Daily Mix are under **Home Screen**. Settings remains accessible when Extras items are hidden. **Regenerate Daily Mix** takes effect
on the next Home visit.

Control Center holds up to eight tiles. Sleep Timer, Settings, Equalizer, Power Off, AirPlay,
DLNA, Wi-Fi Transfer and Screenshot are available but hidden until enabled here. The **Wi-Fi Transfer** tile opens the Wi-Fi Transfer page (offline it says "Connect to Wi-Fi first"). **Sleep Timer** opens the same page as Now Playing's
More page. **Screenshot** works like Developer → Screenshot: it asks first, then counts down 5 or 10
seconds. **Power Off** asks for confirmation. AirPlay and DLNA require Wi-Fi; the pull-down
stays open after a tap, and those tiles cannot be used during an AirPlay session. The Playback
Settings tile opens its hub and is dimmed on the hub and its Volume & Sound and Output pages. Hold the Wi-Fi or Bluetooth tile to open its Settings page.

### Library

| Setting | What it does |
|---|---|
| Update Library | Opens the Update Library page: the number of songs and when the library was last updated, **Update Now** (scans the whole card, and removes songs you deleted), **Choose Folders** (a list of the card's folders: tick the circle of each folder to scan, open a folder with a chevron to pick inside it, **Select All** ticks the folders of the level you are in, and **Scan N Folders** adds their new music) and the **Auto Update** switch (scans after a card is inserted or a USB transfer ends). |
| Rebuild Covers / Rebuild Artist Photos | Rebuild cached artwork; see [artist photos](library-guide.md#artist-photos). |
| Split Artists | List songs under each tagged artist; choose separators. See [Split Artists](library-guide.md#split-artists). |
| Split Genres | List songs under each name of a genre tag such as `Rock; Pop`; choose separators (`;` by default). See [Split Genres](library-guide.md#split-genres). |
| Index Rail / Section Headers | Show the rail and section letters on supported lists; both are on by default. Albums in Year order use a decades rail in the list. |
| Folder Album Cover | Show available covers in Folders; on by default. |
| Cover Flow / Volume Buttons / Start At / Scroll Bar | Choose landscape orientation, use the volume buttons to browse albums, choose where Cover Flow opens (the playing album, the last position or the first album), or turn off the row of ticks under the covers. |
| Podcasts | Choose discovery, directory and region. Directory and region are unavailable when discovery is off. |
| Scrobbling | Configure listening history uploads; see [Scrobbling](features-guide.md#scrobbling). |

Podcast searches use the chosen directory, Apple Podcasts or Podcast Index; Discover charts
always come from Apple.

Home builds missing covers and measures track lengths in the background. Its progress pill's **×**
stops the work until the next restart. **Rebuild Covers** asks first and rebuilds every cover.

### Now Playing

| Setting | Choices |
|---|---|
| Cassette Theme | Normal, Chrome, Metal or Auto (default). Auto chooses by audio quality; a change applies when Cassette Mode next opens. Hi-res and DSD get a gold sticker in every theme. |
| Vinyl Record / Base | Choose the record and base colours. |
| Lyrics Text Size | Small, Medium or Large (default); an open Now Playing updates when you return to it. |
| Idle Display | Off, Album Cover, Cassette, Vinyl, Lyrics or VU Meter after 10 seconds. Off is the same switch as Playback Settings → Cover mode. |
| Track Position | Off (default) or On. On shows the queue position, such as 5/10, between the elapsed and remaining times; it is hidden when the queue holds one track. An open Now Playing updates when you return to it. |
| Shrink on Pause | On (default) or Off. On, the cover shrinks while paused and springs back when the music resumes; off, it stays full size. |

### Playback

Open **Settings → Playback → EQ** for the [equalizer](equalizer-guide.md), or
**Playback Settings** for these options:

| Page | Settings |
|---|---|
| Playback Settings | Queue: Play Mode, Continue Playing, Folder Skip and Resume. Transitions: Gapless and Crossfade. Audio: Volume & Sound and Output. |
| Volume & Sound | Gain, Max Volume, Default Volume, ReplayGain, Channel Balance, Mono Audio and Crossfeed. |
| Output | Digital Filter, DSD Output Mode, USB Mode, USB Volume and Digital Output. |

| Setting | What it does |
|---|---|
| Play Mode | List Play, Repeat Track, Shuffle or Repeat All. |
| Crossfade | A switch (off by default) and, while it is on, a slider for the duration (1 to 12 s, 5 s by default); overlaps the end of one track with the start of the next. **Keep Albums Gapless** (on by default) keeps consecutive tracks from the same album gapless while crossfading album changes, playlists and shuffle. Not applied to DSD, CUE, podcasts or audiobooks. While tracks follow one another, the output keeps its sample rate and later tracks are resampled to it, so the sound never stops between them; pausing or skipping returns to the track's own rate. While a track is resampled, Now Playing's information page shows both rates in its Sample Rate row (`44.1 → 96 kHz`). |
| Resume | Off, Track or Location: choose where playback resumes after a restart. |
| Continue Playing | **Next Albums** continues through the current album order after an album started from Albums, an artist's albums or Cover Flow. It does not apply to Songs or Search, or while Repeat or Shuffle is on. There is a short gap between albums. |
| Gain | Low or High; unavailable on Line Out. |
| Max Volume | Set a limit from 0 to 100. The volume keys stop there, and a higher current volume is lowered immediately. |
| Default Volume | Set the volume for the next start, or enable **Volume Memory** to keep the last volume instead. |
| ReplayGain | Off, Track or Album. |
| Channel Balance | Move the balance left or right; no effect on Line Out or USB audio. |
| Mono Audio | Both channels play the same mix on every output, even with EQ off. |
| Crossfeed | Off, Low, Medium or High; mixes a little of the other channel into each ear. For headphones and Bluetooth, not Line Out, USB DAC or DSD. |
| DSD Output Mode | D2P, DOP or Native. On a USB DAC, changing it restarts the song at the current position. |
| USB Volume | Fixed or Variable. |

### General

- **About** shows firmware, device, network and storage details. **Software Update** is a separate
  row beside it; see [Software update](#software-update).
- **Date & Time**: Set Automatically syncs over Wi-Fi. Time Zone can always be changed; Date and
  Time can be set while automatic time is off. **24-Hour Time** changes the clock display.
- **Keyboards**: English, French (AZERTY) and Chinese (Pinyin); English is on by default, and any of
  them can be turned off as long as one stays on (so French alone gives an AZERTY-only keyboard).
  French (AZERTY) is an AZERTY letter layout. On the English
  and French letters, hold a key such as e, a, c, u, i, o, y or n for half a second to get its accents:
  slide to one and lift to type it. Chinese
  (Pinyin) adds candidates above the keys: swipe sideways, or press space to select the first. With
  more than one on, a language key next to 123 cycles English, French and Chinese, and the
  keyboard opens on the one used last, also after a restart. Passwords use English, or French when
  English is off. Tidal Search uses this keyboard too;
  Search hides it and a tap on the search bar brings it back.
- **Language** lists the 13 languages in their own writing. A choice switches the player and returns
  to Home.

### Display

- Brightness and **Screen Timeout**: Never, 15 s, 30 s, 1 min or 5 min.
- **Lock Screen**: enable it, show the time and choose Large Cover or Mini Player. For wallpaper,
  put up to five JPG or PNG pictures in `lockscreenimage` on the card, each 320 × 480 and under
  1 MB, then choose one under Wallpaper.
- **Screen Rotation** turns the screen upside down and keeps the choice after a restart.
- **LED Light**: Off, Green, Blue or Dynamic; **Follow Screen** turns it off with the screen.
  Dynamic follows the music and offers six themes. Reference shows sample rate as colour; Gentle
  Breathe, Heartbeat and Lighthouse animate it, while Candle and Wave use their own colours. The
  light fades on pause and replaces the charging light during playback.

### Appearance

**Background** is Black or Tinted; Tinted washes the dark greys with the chosen accent. **Accent**
chooses Neutral, Red, Orange, Green, Teal, Purple or Champagne and applies at once. **Control Center**
customizes the pull-down tiles, and **Control Labels** toggles the text under them; see
[Home Screen and Control Center](#home-screen-and-control-center).

### Buttons & Power

**Button Lock** applies while the screen is off, and is the same setting as the Control Center
key-lock tile. **Tap to Wake** uses one or two taps depending on the touch panel. **Swap Prev /
Next** makes the upper track button skip forward and the lower one go back; Bluetooth controls are
unchanged. **Tap for Volume** turns off the status bar tap that opens Volume, if you keep hitting it by
mistake; the volume keys still work. Auto-Standby and
Auto-Shutdown cannot both be on. **Car Mode** resumes the last track at start, disables those
automatic power options and ignores USB connections.

### Battery

**Battery Percentage** shows the exact charge inside the battery icon, in the status bar and on the lock screen; it is off
by default. **Charge Limit** stops charging at 80, 85, 90 or 95% while the player is on and resumes
about 5% lower, also with the screen off (after a pause, charging resumes once the screen is next
on). At 100% there is no limit; a switched-off player charges fully.

**Battery History** opens its own page. Its switch is off by default; enabling it records the last
24 hours of battery level and activity, and turning it off deletes the history. Once recording:

- **Since Last Charge** shows the unplugged time and level (or when recording began on battery),
  current level and time on battery. Its bar estimates time and battery used for Screen On,
  Playing with Screen Off and Standby. While charging the card shows "Charging" with the level and
  the counters stop.
- **Last 24 Hours** shows half-hour battery level bars, green while charging and red at 20% or less.
  Missing data leaves a gap.
- **Activity** shows screen-on and screen-off playing time by hour, with charging hours marked.

The estimates use the gauge's whole percentages. The card and charts appear once the first
15-minute interval with data has closed.

### Developer

- **Startup**: Boot to M1+ Music chooses the startup screen; Open Shanling Home returns to stock Home.
- **Tools → Screenshot**: confirm with a 5 s or 10 s delay, then leave the page to capture another
  screen. Cancel during the countdown if needed. Pictures go in the card's `screenshots` folder.
- **Tools → Cache**: view cover counts and current work, artists with or without photos, and
  measured track durations. Clear Track Durations removes stored measurements. Clear Cover Cache
  asks first and Home regenerates covers; artist photos stay.
- **Tools → Settings Files**: tap a file to delete it. Unsupported Files removes leftovers of older builds.
- **Tools → Card Script**: runs `m1plus-run.sh` from the card root by hand (nothing runs at boot). Status reads No Script, Ready, Running with the elapsed time, Done, Stopped or Failed with the exit status, and follows a run while the page is open. One row starts it (Run Now, with a toast when the card has no script) and reads Stop while it runs, to end it. View Script shows the card's script, View Log its output.
- **Reset → Reset All Settings** asks for confirmation and deletes the settings files. Restart the
  player to apply the reset.

### Software update

Connect to Wi-Fi and open **Settings → General → Software Update** (the row under About).

1. Tap **Check for Update**. Open **Release Notes** to see what changed.
2. Tap **Download and Install**, then confirm the download.
3. Follow the firmware's update confirmation when the download finishes.

The download is about 55 MB and needs 110 MB of free card space. A completed download replaces
`update.bin` on the card. The progress popup's **Cancel** button (or Back) stops the download
and keeps the old file.

The firmware's own TF card update handles confirmation, battery checks, checksums and flashing.
If you decline its confirmation, the page offers **Install** again and **Check Again**.
