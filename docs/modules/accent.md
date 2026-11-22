# Accent and the palette

**Sources:** `patch/palette.c`, `patch/palette.h`, `tools/palette.py` (the model),
`tools/palette_audit.py`, `tools/pod.py` (`STYLE_COLOR`, `IMAGE_ADD`, `STYLE_GRADIENT`,
`LIGHT_PINS`), `patch/offsets.inc` (`ROLE_*`, `ACC_*`, `LIGHT_*`).
The user picks a system accent colour and a page background (Black or Tinted). Both go through **one
palette layer**: every colour the painter gets passes `pal_map(colour)`, which knows the
background and the accent. Black + Neutral is the identity: every hook is a pass-through and the
device renders as stock. Based on q2-pod's Light Mode and accents.

Three hooks serve the layer ([payload](payload.md) hooks 10 - 12): `style_get_color`,
`style_get_gradient` and `image_manager_add`. Stock's theme1 is forced off, so the palette maps only
the modded default theme ([theme](theme.md)).

## Settings

Settings > Appearance (a link row, glyph `palette`) opens `m1plus_appearance`: a **Background** row
(`ACT_BG` 46) above an **Accent** row (`ACT_ACCENT` 48).

| File (`/mnt/data/m1plus/`) | Values |
|---|---|
| `appearance-accent` | one digit 0..6 (Neutral, Red, Orange, Green, Teal, Purple, Champagne); anything else or missing is Neutral |
| `appearance-background` | `0` Black, `1` Tinted, `2` Light, `3` Light Auto; others Black |

- The Accent picker `m1plus_accent` has one check row per accent with a round swatch (`pod_sw<i>`;
  Neutral `#EEEEEC`). A tap calls `pal_accent_set`: saved atomically, applied at once. A failed save
  changes nothing. The swatches are never flipped or tinted.
- The Background picker `m1plus_background` offers Black and Tinted. Light is reachable only by
  editing the file.
- Both files are written through `home_write_atomic`.

## Accents

**Neutral is the default and looks as it always did; no default is ever blue.** The accents:
Red `#FF453A`, Orange `#FF9F0A`, Green `#30D158`, Teal `#40C8E0`, Purple `#BF5AF2`, Champagne
`#C8A96A`. Neutral swatches and fills use `#EEEEEC`.

| Role | With an accent |
|---|---|
| pressed row / card | soft tint `mix(surface, accent, 22 %)`; the text stays white |
| row glyphs (M1+ Music, Folders, Settings cards, the track sheet) | the accent at rest |
| switch on | track is the accent, knob white |
| Podcasts Library tiles | glyph is the accent; the `#1C1C1E` square stays |
| pull-down ON tiles | disc is the accent, glyph stays `#141414` (white on Orange or Teal would be about 2:1) |
| pressed Play / Shuffle | see below |
| slider fill, progress fills, picker check, playing wave marker | the accent |
| **never accent** | chevrons, secondary text, the navbar, body text, card backgrounds |

Cover-tinted pages (Now Playing, album page, Podcasts Show page, Daily Mix, Radio Now Playing, idle
lyrics) keep their cover background exactly; their controls (progress fill, wave) may take the
accent. This holds in Light too.

Contrast of the accent on black: Red 6.16, Purple 5.96, Champagne 9.34, Orange, Green and Teal
about 10. On the pressed card tint the lowest is Purple 3.61.

## The palette API

`patch/palette.h`:

| Function | Meaning |
|---|---|
| `pal_map(c)` | the one entry point: an accent's role colour, else the background (alpha kept) |
| `pal_active()` | not Black + Neutral; hooks are pass-throughs while 0 |
| `pal_background()`, `pal_accent()` | effective values (kill switch or bad-boot note give Black + Neutral) |
| `pal_accent_set(i)`, `pal_accent_saved()` | the setter (0..6, atomic, applies at once; -1 on a bad index or failed save) and the saved index |
| `pal_accent_color(i)`, `pal_fill()` | an accent as a colour word (swatches); the fills' colour now |
| `pal_bg_mode()`, `pal_bg_set()`, `pal_light()`, `pal_tone()` | the background setting; the cover-tinted pages' tone |
| `ui_ink(c)`, `ui_fill_color(canvas, c)` | the payload's own drawing: `pal_map` unless inactive or clear (alpha 0) |

`tools/palette.py` is the Python model (`map_colour(c, bg, ac)`, `role`, `render_image`, the name
lists). `test/pod/palette.py` runs the compiled `pal_map` against it.

## How the mapping works

**Role colours are unique** (`ROLE_*`, `ACC_*` in `offsets.inc`) so `pal_map` can tell them apart
from the neutrals that stay. Each is one blue level off a grey or white that stays:

| Role | Colour | Neutral it replaces |
|---|---|---|
| pressed row / key | `#333334` | `#333333` |
| Now Playing progress fill | `#FFFFFEEB` | `#FFFFFFEB` |
| flat pill pressed | `#333335` | `#333333` |
| Queue pill pressed | `#3A3A3D` | `#3A3A3C` |
| own progress fills | `#EBEBEC` | `#EBEBEB` |
| sheet row pressed | `#FFFFFD10` | `#FFFFFF10` |

`#333333` (card hairlines, tracks, select bars) and `#FFFFFF` map to nothing. The pressed card is an
image found by name, so it needs no unique colour. `roles_tests` scans every built style, page and
source: the role colours appear only where defined. A cover-derived colour equal to a role colour
is moved one blue level (`pal_not_role`), so a cover averaging (31, 31, 32) is not a pressed row.

**Order:** `pal_map` looks for a role colour first and returns the accent's colour for it; otherwise
it applies the background. Role first, because a role colour is neutral and the background step
would change it before the accent could find it.

**Images** are tinted by exact name or name prefix at decode (`accent_image` / `pal_image`; the
lists are generated into `stock.h` from `tools/palette.py`). A tinted name is tinted *instead of*
flipped, so the accent wins over Light. Tints are cached by the image manager and dropped on a
change. `tools/palette_audit.py WORKDIR` lists the tinted names.

| Kind | What is tinted | Rule |
|---|---|---|
| FILL | slider and progress fills, `pod_check`, `np_row_playing` | each pixel goes from its colour to the accent by how light its red is (51 to 238): the grey track stays and edges blend |
| SWITCH | `sset_on` | the `#EEEEEC` track becomes the accent, the `#141414` knob white |
| PRESS | `pod_cd_*_down` (pressed settings card) | `mix(#1C1C1E, accent, 22 %)` |
| DISC | the pull-down's ON tiles | `#141414` stays, white becomes the accent, by lightness; off (`#2C2C2E`) and disabled (`#1E1E1E`) tiles are untouched |
| GLYPH | row glyphs (below) | every colour becomes the accent, alpha kept |
| TILE | the four Podcasts Library tiles | the disc rule with `#1C1C1E` as the fixed end: white becomes the accent, the square stays exactly |
| SHUFDOWN | the Shuffle disc's pressed image | the disc becomes `mix(rest, accent, 22 %)`, the glyph stays |

Premultiplied pixels are handled. Images are global, so cover-tinted pages get the tinted images
too; only their background is left alone. `ah_wave` (the album page's marker) is baked when the page
opens with `pal_fill()` and does not follow a change under an open page.

**Exempt windows:** the lock screen, the full-screen cover, the power-off splash, the Pod and
Cassette Mode keep their colours under any accent or background. The style hooks pass through while
one is the top main window (`pal_exempt`, cached per top window). Their own pictures are in `KEEP`.

## Row glyphs

One decode-time rule, no press-time swap. `pal_image` tints a glyph when it is decoded; an evicted
glyph decodes and tints again, and a change drops the cache. Neutral is untouched.

- **By prefix** (`ACCENT_GLYPH`): `pod_ic_*` (M1+ Music rows, Folders, More sheet, Export OPML and
  Save Episode rows), `fo_ic_*` (Folders list's own glyphs), `pod_ci_*` (the Settings cards' 35
  glyphs) and `rm_ic_*` (the track sheet). A prefix, because many exact names cost the hook on every
  untinted image.
- **By exact name** (`ACCENT_GLYPH_STOCK`): stock and sheet glyphs: the More sheet, the Podcasts and
  Playlists menus, the Add dialog, and the checks `sg_tick` and `mulselected`.
- **Not tinted** (`ACCENT_GLYPH_NOT`): the four Library tiles (kind TILE), the Radio placeholder
  art `pod_ic_rd_art`, the red `pc_ic_unsub` (labels keep their colour), and the stock `selected`
  (it is also the Delete dialog's checkbox).
- **Not covered:** payload-painted lists (their rows have a cover or no glyph), the Home grid, stock
  pages (Display, All Settings, Wi-Fi), the navbar buttons, the stock Settings pages' 40 px discs.

## Pressed Play / Shuffle buttons

Every Play / Shuffle button on our pages presses in the accent. Neutral keeps today's greys, one
blue level off.

| Button | Rest | Pressed with an accent |
|---|---|---|
| flat pill (Songs, playlist pages, Folders) | `#1C1C1E` | `mix(rest, accent, 22 %)`; glyph and label white |
| Queue icon pill, off | `#2C2C2E` | `mix(rest, accent, 22 %)`; the lit on-state `#C8C8C8` / `#A8A8A8` is left |
| Shuffle disc (album, playlist, Daily Mix) | `#2A2A2A` | `mix(rest, accent, 22 %)`; glyph stays white |
| white Play pill (album, playlist, Daily Mix) | `#FFFFFF` | solid accent; the dark glyph and label stay dark |

Left alone on purpose: the select bars' and Online Art's pills (`#333333`), the Daily Mix Add disc,
the Show page's Latest Episode pill, Now Playing's and Radio's transport buttons.

## Other accent users

| Element | Rule |
|---|---|
| Own progress fills (Home cache pill, Podcasts refresh dialog, Update download popup) | role `#EBEBEC` becomes the accent; the track stays neutral |
| Pressed rows of bottom sheets and floating cards | role `#FFFFFD10` (white at 6 % alpha over glass) becomes the accent at 22 % alpha, so the glass shows through |
| Index rail selected-letter disc | `pal_fill()`; the letter on it stays black (the rule of every accent fill) |
| Per-row select mark (Songs, album page, Folders, Playlists, Podcasts) | tinted when baked: white becomes the accent, the black tick stays; follows at the next open |
| EQ value parts (10-Band thumbs, band slider fill, graph curve and fill) | baked with the accent (`tb_acc()`); tracks, grid, cards, value pill stay; not followed under an open page |
| Podcasts progress ring and Navidrome download ring | the arc is tinted in our own RGBA copy, not by name; the marks inside it stay |

Stock pages using `btn_tab_style` / `btn_tablerow_style` press in the accent.

Still neutral on purpose: on-states drawn as light grey (Queue lit, selected chip, segmented
thumb, keyboard shift), navbar glyphs, chevrons, text, hairlines, card backgrounds, the keyboard,
lyrics, the Wi-Fi bars and spinner, the stock pages' 40 px icons, the EQ cards' tracks and grid.

## Background

**Black** is the default. **Tinted** washes dark neutrals with the accent (`pal_wash`, model `wash`).

- In `pal_map`, after the role step, a dark neutral colour (channels within `LIGHT_SPREAD`, none
  above `ACC_DARK`) takes `ACC_WASH` (12 %) of the accent: page black becomes for example Teal
  `#08181B`; the card `#1C1C1E` becomes `mix(card, accent, 12 %)`. The pressed role is
  `mix(tinted surface, accent, 22 %)`.
- Images in `TINT_SURFACE` get the same per-pixel wash. Covers (names with `/` or `:`), `KEEP` and
  the exempt windows do not. The black fades `np_tint`, `np_scrim`, `ah_tint` are not tinted.
- Tinted + Neutral is Black: Tinted needs an accent.
- **Cover-tinted pages are left by window, not by colour.** While the top main window is Now
  Playing, the idle lyrics page, the Daily Mix page, an album page showing a tone, or a Show page,
  the wash applies to no colour (`pal_cover_page`). The accent roles and images still apply. A
  window opened over a page follows its own name. Why not a colour registry: a cover that averaged
  a grey would leave that grey untinted on other pages.
- **The status bar follows the window in front.** The bar is a window of its own, painted with the
  answer for the top main window of the moment, and the window manager repaints only what is
  invalidated. A page opened from a dialog over Now Playing (its More sheet, the pull-down) found
  the bar as painted under Now Playing, its black not washed. The bar's own `EVT_BEFORE_PAINT`
  (`pal_bar_paint`, any paint of it, a part such as the clock too) records the answer it was
  painted with (`pal_kind`: inactive, exempt, cover page; one bit each). `pal_bar_follow` (the real
  bar's 1 s tick, `lo_set_text` in [lineout](lineout.md)) adds that listener on its first call and
  repaints the whole bar once when it holds a paint made under another answer than the window in
  front gets. So the bar can lag the page by up to a second. Black + Neutral and the kill switch add
  no listener.
- Limits: the global `nb_fade` is a tinted black over the cover tone on a cover page; slider and
  progress tracks (`#333`) stay neutral.

## Light background (hidden)

Light is the former Light Mode, hidden from the UI; only the file can set it (`2` On, `3` Auto:
light 07:00 to 18:59 by the device clock). The UI is dark by construction, so Light flips colours
at the three places the painter gets them instead of editing assets.

- **The flip:** a neutral colour (channels within `LIGHT_SPREAD` 16) flips per channel, black to
  `LIGHT_PAPER` `#F4F4F4`, white to `LIGHT_INK` `#161616`, linearly between. A coloured colour stays
  and a clear one stays clear.
- **`style_get_color`** (hook 10) maps every style colour. Only the outermost call maps, because the
  flip is not idempotent. `selected_text_color` is never mapped. **`style_get_gradient`** maps the
  gradient stops. **`image_manager_add`** (hook 12) maps a decoded theme image: `KEEP` names stay;
  `WHOLE` names (settings cards, sheets, the mini player's glass, fades) flip every neutral pixel;
  any other image flips whole if it has no colour and is mostly glyph, so white marks turn dark and
  a grey disc keeps its white glyph.
- The payload's own drawing goes through `ui_ink`; the Cover Flow shelf is composited over paper.
  Album art, covers, wallpapers, photos and videos never change.
- **Cover-tinted pages have no tint in Light:** the tone becomes the page's neutral colour, which
  the style hook flips to a light grey, and the black fades become paper fades. A pastel tint would
  need a marker the hooks respect.
- Stock pages with colours of their own (Tidal, Hi-Res store, guides) keep their hues; their
  neutral parts flip. The mini player's blur and the Daily Mix card's text over art draw from white
  label styles, so their text is ink over art in Light.
- `tools/preview/preview_settings.py` draws the Settings pages in Light; other pages have no light
  preview. Light with an accent is not supported (the pressed card piece mixes with the dark card).

## The timer

One UI-thread timer (`LIGHT_TICK_MS`, a minute) exists while the background is not Black or the
accent is not Neutral. Each tick re-evaluates Auto's hour, the kill switch and the bad-boot note.
A change goes through `pal_apply`: cached images dropped, open tinted pages relit, the window
manager repainted. Nothing runs per paint but a flag test. This is the payload's one global timer.

## Safety

- Hooks 10 - 12 are the accepted relaxation of "nothing at paint". They are pinned (`LIGHT_PINS`),
  fall back to stock (the trampolines run stock's own code; the gradient hook reimplements the leaf
  exactly) and are pass-throughs while the palette is inactive.
- The palette is inactive under the **kill switch** (`/mnt/mmc/m1plus-off` or the flash one) and
  under the **bad-boot note** `/mnt/data/m1plus-bad`, which sends the next boot to stock. The
  setting is read at the first paint, the kill switch again at each tick.
- A crash in a hook before the boot guard arms is not covered by the guard: the SD kill switch is
  the way out.
