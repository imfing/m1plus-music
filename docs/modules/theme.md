# Theme

**Sources:** `tools/mod_theme.py`, `tools/awtk_style.py`, `tools/statusbar.py`, `tools/themeoff.py`.
The static look of the default theme, built at asset time, plus the status bar and the removal of
stock's theme1. The colours here are the Black background with the Neutral accent; the run-time
accent and background mapping is in [accent](accent.md).

## Default theme

`styles/*.bin` is AWTK's compiled theme. All stock theme files round-trip byte-exact
(`tools/awtk_style.py`). Only the **default theme** is modded; stock's theme1 is forced off (below).

| Role | Colour | Stock |
|---|---|---|
| row surface | `#000000` | `#131313` |
| row hairline | `#222222`, 1 px bottom (M1+ Music rows: from x 56, under the title) | 4 px black gap |
| pressed row / key | `#333334` (see below) | `#362221` |
| title text | `#FFFFFF` | same |
| former accent text | `#FFFFFF` | `#FE7E40` / `#FA7268` |
| muted partner text | `#8C8C8C` | `#FFFFFF` |
| secondary text | `#AAAAAA` | same |
| settings icon | bare white glyph (no disc; the Home grid keeps its `#777777` discs) | coloured discs |
| list chevron | `#8A8A8A` (pressed `#6E6E6E`) | white |
| status glyph on / off | `#FFFFFF` / `#5A5A5A` | white / grey |
| slider fill / track / thumb disc | `#EEEEEC` / `#333333` / `#777777` | orange / `#333333` / orange disc |
| toggle on / off | light track, dark knob / dark grey track, grey knob | orange track / grey track |
| Home page dots | `#EEEEEE` / `#555555` | `#FFFFFF` / `#666666` |

Two colours exist only for the accent mapping and are one blue level off their neutral: the pressed
row/key `#333334` and the Now Playing progress fill `#FFFFFEEB`. No other style or source has
them.

- **Edits are pinned** (file SHA-256, the old value and state count per edit, `STYLE_EDITS`): the
  list item and row styles, `btn_tablerow_style`, the keyboard key styles, and the gold label styles
  (accent text becomes white, the partner style muted grey so a selection still reads).
- **Kept:** red error text, the green/red battery states, the red `icon_playing` disc, and every
  AWTK light default style (`window`, `dialog`, `list_view`, `label`, `button`). Stock pages set
  their dark colours inline, and a global change of those defaults is how white-on-white happens.
- **Images:** the 46 settings icons (40 x 40) get the `#777777` disc with the glyph kept
  (q2-pod's `ringnav_image_add` rule); the status bar's glyphs are one filled 14 px set ([icons](icons.md)).
- **Contrast gates, every build:** `audit()` checks every state of the row styles against every
  label style a row can hold (no light row surface; worst text at least 4.5:1 at rest and pressed).
  `page_audit()` checks every text widget of every `ui/*.bin` against its nearest opaque ancestor,
  stock vs mod, and fails if a pair falls below 4.5:1 and got worse. `mod_theme.py --scan TREE STOCK`
  repeats the scan on the finished tree.

### Stock art recoloured at build time

The orange left in stock art is recoloured (`ACCENT_ART`, `accent_to`; each file pinned by SHA-256,
alpha kept bit for bit). A pixel's saturation says how orange it is and its value keeps shading and
dark text; the grey part stays.

- Fills (`vol_progress`, `volume_fg`, `drop_fg`, `eq_plan`, `other_progress`, `cdprogress_bar`, the
  date selector's `datetime_back` edge) become `#EEEEEC` on the stock `#333333` tracks.
- The brightness and balance thumbs and the default-cover corner flag become `#777777` discs with
  the white glyph kept. The default cover tiles take `#333333` with the white logo.
- **Switches** (`sset_on`, `sset_off`) are redrawn without text on the stock 57 x 28 canvas: a 46 x 24
  pill track with an 18 px round knob. On = `#EEEEEC` track, dark `#141414` knob on the right; off =
  `#3A3A3A` track, `#8C8C8C` knob on the left. Our Settings, Main Menu and Cover Flow rows use them
  too, at the same size and anchor, so no row moves. `pset_dual` / `pset_high` keep their words
  ("Dual", "High") on a white track with dark text. States read by brightness and knob side, not hue.
- **Left orange on purpose:** the CD ripper art (its page styles hard-code orange text), the Online
  search button, `chargebg`'s red bolt, the hidden `p_hr`, and the salmon store and bit-depth
  badges (brand art).

## Status bar

`system_bar.bin` follows `mod_battery`'s layout; the table is `tools/statusbar.py`. It also lays out
the pull-down's own copy of the bar (`view_sysbar`): same widgets, positions, images, fonts and
colours, at y 0 of the dialog on the real bar's black. `test/pod/assets.py` compares the two files.

- `view_bar_left` x 10; `label_volume` 16 px; `bar_dclock` 115,0, 90 px wide, 18 px, centred on
  the bar with its text centred (`10:59 AM` 74 px, `23:59` 45 px; the sync icon and the moon yield to keep the right group
  clear of it, [lineout](lineout.md)); `view_bar_right` (3 px spacing) ends 5 px before the
  battery outline.
- **Home** (`home_page.bin`): the strip is black with a 1 px `#222222` top border, the artist line
  `#AAAAAA`, dots `#EEEEEE` / `#555555`. The icon grid is built in code.

## theme1 is off

The palette ([accent](accent.md)) maps only the modded default theme, so stock's System > Theme
choice is gone. Stock keeps it in `/mnt/data/config.ini [SYSSET] THEME` (0 default, 1 theme1). Three
pinned word edits in demo (`tools/themeoff.py`), with no payload code and no boot hook, so the kill
switch cannot undo them:

- **The clamp in `config_init`:** any stored THEME other than 0 is read as 0, so the first and only
  theme load of the boot picks `"default"`. A device that was on theme1 comes up on default. The
  file keeps `THEME=1`, never rewritten, so a stock restore brings theme1 back as it was.
- **The row table of the stock System page:** the Theme entry moves to the end of the table and the
  row count is one less. The rows are built in code, so no asset has a Theme row.
- `systemset/theme_page` is then unreachable. Addresses: [addresses](addresses.md).

The stock `release/assets/theme1` tree (2.3 MB) is deleted from the rootfs by `tools/mod_space.py`
(`remove_theme1`), and no build step, preview or test handles it (`test/pod/navbars.py` asserts the
directory is absent). A stock restore brings the tree back with the stock rootfs.

**The clamp must stay:** a demo without it would ask for `theme1` when `THEME=1` is in `config.ini`.
