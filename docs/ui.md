# UI reference

The interface uses a minimal, iPod-inspired style for the 320 × 480 touchscreen. Asset steps
preserve widget names, pin the stock bytes they replace and run in `tools/build.py` order.
Runtime behaviour is documented in [architecture](architecture.md).

`make preview` renders the selected dev artifact without changing it. For a release sheet, use
`tools/preview.py WORKDIR [OUT.png]` (default `out/preview/release-preview.png`). It covers Home,
menus/settings, library views, portrait/landscape Cover Flow, pull-down controls, lock-screen
states and an enlarged battery. Feature tools (`preview_icons.py`, `preview_stock.py`,
`preview_battery.py`, `preview_nowplaying.py`, etc.) accept output paths; use gitignored
`out/preview/`.

Previews are approximate PIL mock-ups with sample data, not AWTK captures. Text uses the built
tree's `default.ttf` via stb_truetype (`tools/preview_font.py`, `tools/stb_raster.py`). See
[workflow](workflow.md) and [device checks](modules/device-checks.md) for validation.

## Before changing the UI

Read [UI rules](modules/ui-rules.md) and [text measurement](modules/text-width.md). Reproduce
bugs with an emulation test or device screenshot. Reuse the shared layout/text model in previews
and measure the font from the tree being built.

## References

| Area | Documentation |
|---|---|
| Fonts and theme | [Fonts](modules/fonts.md), [theme format/palette](modules/theme.md) |
| Navigation | [Menu](modules/menu.md), [settings](modules/settings.md), [navbars](modules/navbar.md) |
| Library | [Lists](modules/lists.md), [rows](modules/rows.md), [Albums](modules/albums.md) and its "..." sort card, [album page](modules/album-page.md), [track rows' menu](modules/rowmenu.md), [Get Info](modules/songinfo.md) (preview: `tools/preview_songinfo.py`), [queue](modules/queue.md) (preview: `tools/preview_queue.py`), [Folders](modules/folders.md), [search](modules/search.md) (preview: `tools/preview_search.py`) |
| Playback | [Now Playing](modules/nowplaying.md), [lyrics page](modules/lyrics.md), [More sheet](modules/playmore.md), [Find Cover & Lyrics](modules/onlineart.md), [Software Update](modules/update.md) (preview: `tools/preview_update.py`), [mini player](modules/minibar.md) |
| Home content | [Recently Played](modules/recent.md), [Daily Mix](modules/dailymix.md), [cover build line](modules/homecover.md), [Recently Added albums](modules/recent-albums.md) |
| Extras | [Playlists](modules/playlists.md), [Songs](modules/songs.md), [Podcasts](modules/podcasts.md), [Radio](modules/radio.md), [Cassette Mode](modules/tape.md), [Vinyl Mode](modules/vinyl.md), [virtual iPod](modules/ipod.md), [iPod Cover Flow](modules/ipod-coverflow.md), [Keyboard](modules/keyboard.md), [Tidal Search keyboard](modules/tidalkb.md) |
| System appearance | [Accent and palette](modules/accent.md), [Boot logo/slides](modules/boot.md), [icons](modules/icons.md), [battery](modules/battery.md), [Line Out pill](modules/lineout.md), [pull-down](modules/pulldown.md), [lock screen](modules/lockscreen.md), [wallpaper](modules/wallpaper.md), [About/polish](modules/polish.md), [dialogs, power-off splash](modules/overlays.md) |
| Languages | [Translation and sizing](modules/i18n.md) |

Older source comments refer to former UI sections: 1 rules, 2 text width, 3 fonts, 4 theme/lists/
Now Playing, 5 boot, 6 icons/battery, 7 stock pages and assets, 8 menu/Albums, 8a languages,
9 device checks. Detailed code and asset notes now share the corresponding module file.
