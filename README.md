<p align="center">
  <img src="docs/m1plus-music.jpg" alt="M1+ Music on the Shanling M1 Plus, showing iPod mode, Now Playing and Vinyl Mode" width="100%">
</p>

<p align="center">
  A modern music-player interface for the <b>Shanling M1 Plus</b>.<br>
  Built on official V2.1 firmware.
</p>

<p align="center">
  <b><a href="https://github.com/imfing/m1plus-music/releases/latest">Download</a></b> ·
  <b><a href="#install-and-update">Install</a></b> ·
  <b><a href="docs/guide.md">User guide</a></b> ·
  <b><a href="#screenshots">Screenshots</a></b> ·
  <b><a href="#documentation">Development</a></b>
</p>

## Features

- **Browse:** Cover Flow, album grids and lists, artist photos, A–Z indexes, playlists and folders.
- **Search:** music and podcasts with an on-screen QWERTY or French AZERTY keyboard, also in Tidal.
- **Home:** pinned albums, playlists, songs and artists, Daily Mix, Recently Played and a floating mini player.
- **Now Playing:** cover-colour backgrounds, rounded artwork, three lyrics sizes, an idle display, Continue Playing into the next album, Cassette, Vinyl and Lyrics Mode.
- **Extras:** album and folder shuffle, a virtual iPod and online cover and lyrics lookup.
- **Podcasts:** feeds, directory search, episode downloads, filters and per-show order.
- **Audiobooks:** books from the card, plus LibriVox search and download.
- **Radio:** internet radio with a station browser.
- **Scrobbling:** ListenBrainz and Last.fm, logged offline on the card.
- **Subsonic:** browse, search, stream and download from Navidrome, Gonic or Airsonic.
- **Equalizer:** 10-band editor, AutoEq downloads and a separate EQ per output.
- **Wi-Fi:** WPA3 and Enhanced Open, plus a browser page to manage the card.
- **Settings:** menu and pull-down tiles, a Volume page, playback, display, charge limit and a music-driven LED.
- **Appearance:** accent colours, a lock screen with mini player, Inter and Source Han Sans.
- **Languages:** 13 translations following the player's language setting.

Stock settings and Tidal remain accessible. See the [user guide](docs/guide.md) for controls.

## Screenshots

**Library:** Cover Flow, albums and playlists.

![Cover Flow, the album grid and playlist mosaics](docs/screenshots/library.jpg)

**Playback:** Now Playing, synced lyrics and album details.

![Now Playing, synced lyrics and an album's track list](docs/screenshots/playback.jpg)

**Extras:** iPod mode, Vinyl Mode and podcasts.

![The touch-wheel iPod interface, a cover-tinted record and the podcast library](docs/screenshots/extras.jpg)

**Home, settings and search:** Daily Mix, grouped settings and QWERTY search.

![Daily Mix on Home, the Settings page and music search with the QWERTY keyboard](docs/screenshots/settings-and-search.jpg)

## Install and update

Download `update.bin` and `SHA256SUMS` from the [latest release](https://github.com/imfing/m1plus-music/releases/latest).
Verify the checksum, then install `update.bin` from the TF card using the player's System Update menu.
Once installed, later releases can be installed over Wi-Fi from **Settings → General → Software Update**.
Follow the [installation guide](docs/install.md) for preparation, updates and restoring stock.

## Documentation

Start with [installation](docs/install.md) and the [user guide](docs/guide.md). For building or
contributing, see the [development workflow](docs/workflow.md) and the
[documentation index](docs/README.md).

## Support

If M1+ Music is useful to you, you can support its development on [Ko-fi](https://ko-fi.com/imfing).

## License

[MIT](LICENSE). Shanling firmware is not included. Font and icon licenses accompany their assets.

## Acknowledgements

Inspired by Diamond Bond's [q2-pod](https://github.com/DiamondBond/q2-pod) for the Shanling Q2, which
also supplied the parametric EQ design, the UTC RTC fix and the charge-limit idea. Other borrowed
code and artwork is credited in its source file and module doc.
