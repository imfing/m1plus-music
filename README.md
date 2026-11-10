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

- **Browse:** Cover Flow, album grids/lists, Artists, an A–Z Songs list and Playlists.
- **Search:** find music and podcasts with an on-screen QWERTY keyboard.
- **Home:** Daily Mix, Recently Played and a floating mini player.
- **Now Playing:** cover-colour backgrounds, rounded artwork and remaining time.
- **Podcasts:** local episodes, top shows and episodes for your region, directory search, feed subscriptions and episode downloads.
- **Extras:** album/folder shuffle, internet radio, a virtual iPod, Cassette Mode, Vinyl Mode and an online cover and lyrics lookup.
- **Appearance:** an accent colour, a translucent lock screen, minimal theme, Lucide icons and Inter + Source Han Sans fonts.
- **Equalizer:** a 10-band EQ editor, AutoEq headphone corrections downloaded over Wi-Fi, parametric presets from the card and a separate EQ for headphones, line out and USB DACs.
- **Wi-Fi:** a new Wi-Fi page with WPA3 and Enhanced Open, and a redesigned Wi-Fi Transfer page to browse, upload, download and organise the card from a browser.
- **Settings:** choose menu items, pull-down tiles, startup behaviour, Cover Flow orientation.
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

Still early in development and tested only on my own M1 Plus.

Download `update.bin` and `SHA256SUMS` from the [latest release](https://github.com/imfing/m1plus-music/releases/latest).
Verify the checksum, then install `update.bin` from the TF card using the player's System Update menu.
Once installed, later releases can be installed over Wi-Fi from **Settings → System → About → Software Update**.
Follow the [installation guide](docs/install.md) for preparation, updates and restoring stock.

## Documentation

Start with [installation](docs/install.md), then the [user guide](docs/guide.md).
For building or contributing, see the [development workflow](docs/workflow.md).
The [documentation index](docs/README.md) lists technical references.

## Support

If M1+ Music is useful to you, you can support its development on [Ko-fi](https://ko-fi.com/imfing).

## License

[MIT](LICENSE). Shanling firmware is not included. Font and icon licenses accompany their assets.

## Acknowledgements

Inspired by Diamond Bond's [q2-pod](https://github.com/DiamondBond/q2-pod) for the Shanling Q2.
The radio placeholder glyph derives from [IconPark](https://github.com/bytedance/IconPark) `radio` (Apache-2.0).
