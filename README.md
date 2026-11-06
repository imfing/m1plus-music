<p align="center">
  <img src="docs/m1plus-music.jpg" alt="M1+ Music on the Shanling M1 Plus, showing iPod mode, Now Playing and Vinyl Mode" width="100%">
</p>

<p align="center">
  A modern music-player interface for the <b>Shanling M1 Plus</b>.<br>
  Built on official V2.1 firmware, with Navidrome/Subsonic support.
</p>

<p align="center">
  <b><a href="https://github.com/iamgauravmishra/m1plus-music-navidrome/releases/latest">Download</a></b> ·
  <b><a href="#install-and-update">Install</a></b> ·
  <b><a href="docs/guide.md">User guide</a></b> ·
  <b><a href="#screenshots">Screenshots</a></b> ·
  <b><a href="#documentation">Development</a></b>
</p>

This project builds on [imfing/m1plus-music](https://github.com/imfing/m1plus-music), retaining its player features and adding Navidrome/Subsonic support. See [Acknowledgements](#acknowledgements) for credit.

## Features

- **Browse:** Cover Flow, album grids/lists, Artists, an A–Z Songs list and Playlists.
- **Search:** find music and podcasts with an on-screen QWERTY keyboard.
- **Home:** Daily Mix, Recently Played and a floating mini player.
- **Now Playing:** cover-colour backgrounds, rounded artwork and remaining time.
- **Podcasts:** local episodes, Apple Podcasts directory search, feed subscriptions and episode downloads.
- **Extras:** album/folder shuffle, internet radio, a virtual iPod, Cassette Mode, Vinyl Mode and an online cover and lyrics lookup.
- **Navidrome:** keep server credentials on the SD card, sync a paged library index, browse and search tracks, and stream supported audio over Wi-Fi without requesting transcoding. Download songs to SD with progress and resume support. Shared album artwork, server status, and a Songs/DSD Downloads grid or list are included.
- **Navidrome in Libraries:** merge server tracks into Songs, Albums, Artists, Album Artists, Genres and Composers; include them in global search and the virtual iPod/Cover Flow. Stream-only tracks carry a small green source dot. Local matches and downloaded files remain local entries. Mixed queues follow the current view's order.
- **Appearance:** an accent colour, a translucent lock screen, minimal theme, Lucide icons and Inter + Source Han Sans fonts.
- **Settings:** choose menu items, pull-down tiles, startup behaviour, Cover Flow orientation and album order.
- **Languages:** the added UI follows the player's language setting, with 13 translations.

Stock settings and Tidal remain accessible. See the [user guide](docs/guide.md) for controls and options.

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

Download `update.bin` and `SHA256SUMS` from the [latest release](https://github.com/iamgauravmishra/m1plus-music-navidrome/releases/latest).
Verify the checksum, then install `update.bin` from the TF card using the player's System Update menu. Read the [release notes](docs/releases/1.2.1.md) and [installation guide](docs/install.md) first.
The built-in Software Update can fetch releases only when this repository's releases are public; while the repository is private, use the TF card for updates.
The update changes the app payload and UI assets through the existing kernel/rootfs update path; it does not patch the bootloader or recovery. Keep a stock restore package available and do not interrupt an update.

This is unofficial third-party firmware. Install it at your own risk. Back up your card and keep the player charged during updates. I am not responsible for damage caused by installing or using this firmware.

## Documentation

Start with [installation](docs/install.md), then the [user guide](docs/guide.md).
For building or contributing, see the [development workflow](docs/workflow.md).
The [documentation index](docs/README.md) lists technical references.

## License

[MIT](LICENSE). Shanling firmware is not included. Font and icon licenses accompany their assets.

## Acknowledgements

This repository is based on [imfing/m1plus-music](https://github.com/imfing/m1plus-music) by imfing and its contributors. It retains the upstream project and adds Navidrome/Subsonic integration; upstream features such as Tidal remain included. See the upstream repository for its original project history and credits.

Inspired by Diamond Bond's [q2-pod](https://github.com/DiamondBond/q2-pod) for the Shanling Q2.
The radio placeholder glyph derives from [IconPark](https://github.com/bytedance/IconPark) `radio` (Apache-2.0).
