# Icons

`tools/mod_icons.py` draws every replaced image at its exact stock size and mode. The build only copies the
committed PNGs (`assets/icons/png/`, 568 files), so there is no rasteriser in the build and it stays deterministic.

- `--generate` re-renders the PNGs (`rsvg-convert` + Pillow).
- `--pins` writes the stock SHA-256 pins (`tools/mod_icons_pins.txt`).
- `--check [WORKDIR]` verifies pins, size and mode.
- `--fetch TGZ` copies the used SVGs out of a pinned npm tarball (parsed as data: whitelisted tags and attributes).

Text badges are drawn with Pillow, so a regenerate on another Pillow/FreeType can shift their pixels; commit only
the PNGs you meant to change.

## Sources

| set | where | licence |
|---|---|---|
| Lucide (lucide-static 1.61.0, tarball SHA-256 `62773cd2...ba75f1`) | `assets/icons/lucide/svg/` | ISC, `assets/icons/lucide/LICENSE` |
| Tabler (`@tabler/icons` 3.49.0), `T:` prefix, only where Lucide lacks one: `brand-tidal`, `circle-check` filled, `a-b` | `assets/icons/tabler/svg/` | MIT, `assets/icons/tabler/LICENSE` |
| custom, drawn in Lucide's style (24 grid, 2 px stroke, round caps): `badge-hr`, `dac`, `gain-low`/`gain-high`, `volume-3waves`, `turntable` (the More sheet's Vinyl Mode row: a plinth, a record and an arm), `cover-lyrics` (its Find Cover & Lyrics row: a picture over two text lines), `coverflow` (Lucide `gallery-horizontal` with side covers 10 units tall, 3 units out) | `assets/icons/custom/` | ours |
| `radio-set` (`assets/icons/custom/radio-set.svg`; the logo-less placeholder of Radio, `pod_ic_rd_art`): IconPark `radio` redrawn on the 24 grid and centred | `assets/icons/custom/` | Apache-2.0, Copyright ByteDance (https://github.com/bytedance/IconPark), noted in the file and the README |
| the Shanling mark (`pod_ci_shanling`, the Settings > Developer > Open Shanling Home row): the swoosh cut from stock `shutdown.png` (SHA-256 pinned), isolated by whiteness, 24 px wide, dilated to about a 2 px stroke | stock art | |

**Rule:** an icon gets a real Lucide glyph (Tabler where Lucide has none), or is drawn in Lucide's style, or keeps
its stock image when that is decent. Lucide has no filled style: `name:filled` fills the outline (star, play,
pause, skip, lock); `ellipsis` is always filled.

## Sizes and colours

- **Strokes:** 2 px. 1.5 px under 22 px, and 1.75 grid units on the 66 px Home discs.
- **Fitting:** glyphs are fitted to the stock canvas by ink size.
- **List icons:** a bare white glyph on a 24 px canvas, centred in the stock 40x40 image, no disc.
- **Navbar and other glyph buttons (`SMALL_GLYPHS`):** a 20 px ink box (stock 22), pressed `#777777`.
- **Dialog glyphs and selection marks:** dialog glyphs (`DIALOG_GLYPHS`) and selection marks (`MARK_GLYPHS`) are drawn at 0.88 x.
- **Chevrons:** `right_arrow`, `expansion`, `expansion_2` are `#8A8A8A`, pressed `#6E6E6E`. `right_arrow` (13 x 22) and `pod_chev` (10 x 16) hold the shared list chevron of `patch/common.c` `pod_make_chevron` pixel for pixel (`mod_icons.pod_chevron`, same 4 x 4 sampling), right aligned in the 13 px canvas: a 13 px image at x 285 lands the ink at 288..298, as every list chevron does (see `ui-rules.md`).
- **Translucent discs:** 32 px, white at 20 % (pressed 35-40 %). Glyphs are centred optically: box and centroid are averaged, placed in quarter-pixel steps (`np_glyph`).
- **Unchanged:** every touch target.

## What is replaced

| area | images | design |
|---|---|---|
| settings | all 46 (40x40) | bare 24 px glyph; DAC, DSD output (2) and ReplayGain are text badges (Inter in a 24x16 rounded rectangle, 1.5 px line, `badge()`); labels stay at x 60 |
| Home grid | 18 + 18 `_down` (66x66) | 38 px glyph on `#777777` (pressed `#555555`); HiFi (zh_CN) a store; Tidal Tabler `brand-tidal` |
| M1+ Music Home icon | added `m1plus`, `m1plus_down` (66x66) | Lucide `smartphone` on the same disc; style `home_m1plus_style` (a copy of `home_tidal_style`) added to `styles/home_page.bin` in stock sort order; widget built at run time (`home-guard.md`) |
| M1+ Music rows | added `pod_ic_*` (24x24) | menu, Shuffle, Extras and Main Menu rows: glyph x 16..40, title x 56, a 1 px `#222222` hairline from x 56 (child `pod_hair`, insensitive; the theme's bottom border off, `border_width` 0); image insensitive |
| Settings cards | added `pod_ci_*` (24x24, a 20 px glyph), `pod_chev`, `pod_check` | the Settings pages' rows (`CARD_GLYPHS`, `settings.md` "Cards"); the grey chevron and the picker's check; with an accent the `pod_ci_*` glyphs are tinted at decode ([accent](accent.md)) |
| navbar extras | added `pod_nav_coverflow`, `pod_nav_settings`, `pod_nav_grid`, `pod_nav_list` (+ `_down`) | Cover Flow button (`coverflow`); Settings capsule cap (`sliders-horizontal`); Albums view toggle (`layout-grid` / `list`, showing the mode a tap switches to; `pod_nav_gridl` / `pod_nav_listl` are the left-cap pieces for the Radio search results) |
| navbar and dialogs | 110 | add, cancel, delete, multi-select, sort, search, back, chevron, more, settings, `back_to_player` (`audio-lines`, 23x24); selection circles and squares, expanders, queue-dialog modes, dialog actions, Now Playing more-dialog and batch-add icons, Bluetooth/USB page transport |
| Folders, Playlists, CD | 24 bare glyphs (40x40) | 16 audio formats share `file-music`; SD, USB; New / Import / Export; CD track dialog (`guitar`, microphone, calendar) |
| list placeholders | 6 glyphs (40x40), 3 "no cover" tiles (60/90/100) | the tile colour with a muted glyph at 0.52 of the tile |
| artist photo placeholder | `pod_ic_ar_art` (96 px, Lucide `mic-vocal` #8C8C8C, stroke 2, transparent; `ARTIST_ART`) | not a tile: `patch/artistphoto.c` `ap_placeholder` draws the #333333 circle (40 px on the Artists rows, 160 px on the artist page) and this glyph on it at 0.52 of the diameter; accent-neutral (`ACCENT_GLYPH_NOT`) |
| pull-down | 17 (50x50, 20x20 suns) | one ring style (`pulldown.md`); "PO" / "LO" 17 px Inter |
| status bar | 15 | white, unlit Wi-Fi arcs `#666666`; 1.5 px at 14-16 px, 2 px at 20 |
| Now Playing | `np_*` (21) | solid PIL transport shapes (`transport_mask`); star and More on a translucent disc (`nowplaying.md`) |
| screensaver transport | `play1`, `pause1` (+ `_down`, 36x36) | solid transport shapes (`transport_mask('ss_play' / 'ss_pause')`, play corners `SS_PLAY_R` 0.16) on a translucent disc |
| playing marker | `icon_playing` (40x40) | bare `audio-lines`, 24 px ink |
| queue | `p_playqueue`, `p_playqueuedown` (24x22) | `list-music` in the `SMALL_GLYPHS` box |
| text badges | speed (8), the stock fallback's Play all pills (4, the PLAYALL images), `p_hr` (28x18), `16bit`, `24bit` (40x18), `replaygain` (40x40) | white outline badges (`badge(text, size=)`); the stock fallback's Play all an off-white pill with dark text (our Play is the album page's `ah_pill`) |
| step buttons | `vol_add`, `vol_dec` (+ `down`, 44x44), `bt_add`, `bt_dec` (+ `_down`, 100x100) | `plus` / `minus` on a translucent disc; pressed glyph 80 % white |
| LED, backlight | `led_select` (80x80), `light_lefticon`, `light_righticon` (24x24) | Tabler `circle-check` filled on a 30 % white disc; `sun-dim` / `sun` |
| mode screens | `usb_dac`, `usb_storage`, `wifits_icon`, `btrecv_icon` | grey gradient disc (`#303030` to `#1A1A1A`, 1 px rim) in soft rings (lines 32 / 23 / 14 % white over a faint glow); `usb`, `hard-drive`, `wifi`, `bluetooth` in `#C0C0C0` (`HERO_GLYPH`), softer than white so it sits in the disc |
| Update Library spinner | `scan1`..`scan12` (200x200, `scanmusic_dialog` `img_animation`, 100 ms a frame) | a white arc (5 px, radius 84) with a 240 degree fading tail sweeping round a faint 12 % track (`scan_frame`); the song count sits in the middle |
| charging | `chargebg` (86x124) | the stock frame (`charge_big`, SHA-256 pinned, read at generation) with a centred white bolt |
| recoloured | 9 `eq_*` presets white; 15 orange to neutral (toggles, slider fills and thumbs, default covers, `theme.md`); 4 secured Wi-Fi rows (fan + lock) | |

`icons` runs late in the build, so it overrides the theme step's grey discs.

## Row glyphs

| page | rows |
|---|---|
| M1+ Music menu | Now Playing `audio-lines`, Cover Flow custom `coverflow`, Shuffle `shuffle`, Songs `music`, Albums `disc-3`, Artists `mic-vocal`, Genres `guitar`, Folders `folder`, Playlists `list-music`, Settings `sliders-horizontal`, Extras `ellipsis` |
| Settings (cards, 20 px) | `CARD_GLYPHS` in `tools/mod_icons.py`: Wi-Fi `wifi`, Bluetooth `bluetooth`, Home Screen `house`, Library `disc-3`, Now Playing `audio-lines`, EQ `sliders-vertical`, Display `sun`, Language `languages`, Developer `code`; sub-pages: Landscape `rotate-cw-square`, Rebuild Covers `image-up`, Boot to M1+ Music `power`, Open Shanling Home the mark |
| Extras | the Home grid's glyphs: `star`, `clock-plus`, `history`, `flame`, `feather`, `badge-hr`, `refresh-cw`, `globe`, `disc` |
| Shuffle | the song, album and folder glyphs |

The rows live in `ui/m1plus_menu.bin`, `m1plus_shuffle.bin`, `m1plus_extras.bin` and `m1plus_mainmenu.bin`; the Settings cards pages are built by `tools/pod_ui.py` `build_cards_page`.

## Audit (`tools/audit_images.py`)

`audit_images.py STOCK [TREE]` lists every `images/xx` file referenced by a `ui/**/*.bin` property, a style file or
a name string in `demo` (560), and with TREE only those still byte-identical to stock: **270**. All are kept on
purpose:

- 100 keyboard keys
- about 70 backgrounds, scroll arrows and unused AWTK check/radio art
- brand, codec and protocol badges (all MQA, AAC/aptX/LDAC/SBC, SyncLink, AirPlay, DLNA, Sony)
- 55 Tidal / HiFi store / purchase / guide images (Chinese or account only)
- 14 CD ripper images
- the equaliser's `eq_off`, `eq_tape`, `eq_back` and `eq_plandot`
- slider dots and tracks (`vol_dot`, `vol_progressbak`, `volume_bg`), which are already neutral
- `charge_big` and `dac_charge`, which are already white

`tools/preview_icons.py STOCK_TREE RELEASE_TREE OUT.png` draws before and after at 1:1 with a 3x status strip
(blue **C** = custom glyph, orange **K** = stock kept). `test/navbars-stock.sha256` holds the digest of the images
directory, so an intended image change updates it.
