# UI rules

**Sources:** `tools/pod_roles.py` (colour and size roles), `tools/awtk_text.py` (text model),
`tools/pod_ui.py`, `tools/mod_polish.py`, `patch/common.c`. **Tests:** `test/pod/` (hit tests in
`test/pod/harness.py`, widths in `test/pod/i18n.py`).

## Widgets and layout

- **Preserve names.** Restyle, move or hide named widgets; never rename or delete.
  `widget_lookup(win, name, TRUE)` is recursive, so reparenting is safe.
- **Hit testing ignores `visible`.** Hide = `visible=false` + `sensitive=false`; decorative overlays
  `sensitive=false`. AWTK takes the first child (from the top) that is enabled, sensitive and
  contains the point. Tools model it (`check_touch` in `mod_lockscreen.py` / `mod_nowplaying.py`:
  every control's centre reaches it, at least 44 px each way); `test/pod/` runs demo's own hit test
  on the built page trees.
- **A button inside an insensitive parent never gets its touch.** Keyboard field `kb_field` is
  sensitive for its clear button; a page puts its eye button after the field, so over it. Page
  tests ask the hit test, on the page as the payload left it (`touch_misses` in
  `test/pod/harness.py`); paint order proves nothing.
- **Trailing controls of a card are one column; a control with nothing to do is hidden.** Clear
  disc and eye glyph share a centre (x 287); the eye shows only while typed text is behind dots.
- **Normal windows 450 px tall** (under the 30 px `system_bar`); only fullscreen (`screensaver_page`)
  480. Lists use stock structure `list_view` > `scroll_view` + `scroll_bar_m` with stock `list_item`
  rows: an `hscroll_label` themed `srlabel_leftwhite21_style` and the `right_arrow` image, a 13 px
  widget at x 285 (ink = shared chevron, x 288..298). Text ends at 278, hairline at 310. Bare
  `list_item`s fall to the light default theme (white on white).
- **Window theme first.** A widget's style resolves in its window's theme (`styles/<window
  name>.bin`, or its `theme` property) before `styles/default.bin`. Page-local styles change one
  page only.
- **No close animation on windows a "play from here" loop can pop:** library pages, album detail,
  jump list, Now Playing, M1+ Music pages. See
  [slides audit](boot.md#settings-slide-safety-audit-static-on-stock-demo).
- **Naming:** user sees "M1+ Music"; internal names (`m1plus-*` files, `m1plus_*.bin`, widget and C
  identifiers) are `m1plus`.
- Rebuilt rootfs must not exceed stock (`fwtool` enforces); one change per package where possible.
- **The Pod is its own view:** every Pod row opens a Pod level, never one of our full pages. A
  function without a Pod-designed level is left out of the Pod ([ipod](ipod.md)).

## Text width

`demo` links AWTK statically with stb_truetype; no FreeType. `canvas_draw_text` draws glyph by glyph,
`x += advance + 1`; `canvas_measure_text` adds the same.

- **Width = truncated glyph advance + 1 px per glyph.** Scale = `font_size / (hhea ascender -
  descender)`, each advance truncated. Stock font (256 units/em, ascender 230, descender -69): size
  18 draws an em at 15.4 px.
- No hinting, kerning, OpenType features or per-glyph fallback (one font file covers every script).
  Composite glyphs only with plain offsets.
- `canvas_measure_text` counts a glyph the font lacks as 4 px. Only `glyf` outlines; cmap format 4
  is looked up by binary search trusting `searchRange` / `entrySelector` / `rangeShift`
  (`mod_boot.stb_lookup` is a line-for-line port, used by font checks).
- `hscroll_label` clips to its box inset by `margin_left` / `margin_right` (default 2).
- Use `StbText` (`tools/awtk_text.py`): `StbText(ttf, px).layout(text)` returns each glyph's pen and
  AWTK's width. `awtk_width`, `fit_size`, `worst_case_text` size the lock clock and date. Always
  measure the font of the tree being built. `tools/stb_raster.py` rasterises the same way for
  previews.

## Text and colour roles

Role names live in `tools/pod_roles.py`; page constants take them.

| Role | Value |
|---|---|
| ink (`INK_RGB`) | `#FFFFFF` |
| rest surface (`SURFACE_RGB`: Settings cards, cache pill, fields, flat pills, dialog buttons, EQ cards) | `#1C1C1E` |
| raised surface (`RAISED_RGB`) | `#2C2C2E` |
| line (`LINE_RGB`) | `#333333` |
| thumbnail placeholder (`THUMB_RGB`: grids, cover flow, a logo-less station) | `#2B2B2B` |
| secondary text (`SUB_RGB`, `HINT_RGB`: sub lines, footers, values, keys, credits, hints) | `#AAAAAA` |
| album page meta line (15 px; least that passes 4.5:1 scan on a pressed row) | `#9C9C9C` |
| field placeholder (`PLACEHOLDER_RGB`) | `#8E8E93` |
| list chevron (`CHEV_RGB`) | `#8A8A8A` |
| a row that cannot be chosen (`DIM_RGB`: title and sub line) | `#7A7A7A` |
| a row's "..." and the muted partner / pressed glyph grey | `#8C8C8C` |
| the one red (`RED_RGB`: a row that deletes or loses data: label and glyph, with or without a confirm) | `#FF6B6B` |

- **Pressed surfaces `#333333`** (list rows on black, keys, queue drawer's bottom button); a row
  on a `SURFACE_RGB` card (Settings, Wi-Fi, Bluetooth) presses to `RAISED_RGB`. Stored as role colour
  `#333334` so the accent can map it ([accent](accent.md)). `#3A3A3A` = edge colour (hairline
  borders, index letter); `#555555` = pressed disc and inactive dot.
- **Toggles:** on = light grey pill with black glyph/knob; off = dark grey with white or grey
  glyph/knob. Read by brightness and knob side, not hue ([theme](theme.md) "Switches").
- **Album page track rows:** number and title use the list title size (`LIST_TITLE_PX` 21).

## Headings

- **Group caption** names a group of rows (Settings, Wi-Fi, Search, Extras pages): 18 px `SUB_RGB` in a
  40 px strip, label 22 px high 14 px down it, text left of the rows' glyph ink (x 24 on a card
  page, 18 on Extras) (`pod_roles.CAPTION_*`).
- **Content section title** heads the content (Songs' A-Z letters, Podcasts sections, Recently
  Played and Made for You shelves): 20 px `INK_RGB` (`pod_roles.SECTION_PX`).
- Never mix: a new heading takes one of the two.

## Empty and loading states

A page with no rows shows one grey line (`HINT_RGB`: 20 px, 18 px when it wraps) or its loading
spinner, centred across the page and in the room between the kept header and the window bottom:

- navbar's bottom when content is hidden (library pages, Radio captions, Podcasts with no shows:
  `room_y` in `tools/pod_ui.py`, window y 250);
- large title's bottom on a source page that keeps the title (`ls_room`, `patch/libsrc.c`);
- header's bottom on a Podcasts level (`pg_paint_hint`, [podcasts](podcasts.md)).

Exceptions: keyboard pages (Search, AutoEq) centre the line between field and keyboard. A status
belonging to a row stays in the row (Navidrome status line and Sync Now, Wi-Fi rows, login page's
Connecting line).

## Bottom sheets and segmented control

- **Bottom sheets** (track rows' menu, Podcasts and Radio sheets, Now Playing's More sheet): 50 px
  rows, 24 px glyph at x 14, 18 px label from x 48, scrim `PL_DIM`. The Albums "..." sort card
  (50 px rows) and Playlists menu (20 px glyphs) are floating cards, not sheets.
- **Scrims** (`modal_scrim`, any page-window dim) are shown and hidden with `m1_scrim`, never
  `m1_show`: the status bar is a window of its own above the page and dims with it
  ([accent](accent.md) "Background").
- **Item sheets** (an item's actions: the row menu's forms, [rowmenu](rowmenu.md)) are in groups, top to
  bottom, each only when the item has it: Play, Shuffle | Pin, Add to Playlist (or Download), Favorite,
  Get Info | Play Next, Play After | Select | the destructive row. One `#FFFFFF22` hairline between two
  groups, none inside a group. A destructive row (Remove from Playlist / Queue, Delete Book, Remove
  from My Stations) has the red label `RED_RGB` and a red glyph (`pod_ic_*_red`, in `ACCENT_GLYPH_NOT`).
  A long press or a row's "..." opens a bottom sheet; a navbar "..." opens a floating card under the
  button (the view-sort card's look, the popup form; Select first, as on the view-sort cards) unless its rows
  do not fit there.

## Segmented control

One painter, `m1_segmented` (`patch/common.c`; constants `SEG_*`, model `tools/pod_show.py
segmented`): fully rounded `#1C1C1E` track; selected segment a fully rounded `#D1D1D6` thumb (black
label) floating 3 px inside; other labels white; short `#3A3A3C` hairline (half track high) between
two unselected segments, none beside the thumb. Neutral (no accent). First user: Podcasts Discover
level's Shows | Episodes ([podcasts](podcasts.md)).

## Confirm dialog

Yes/no questions use the stock confirm dialog: [overlays](overlays.md) "Confirm dialog".

## Polish decisions

Navbar title facts: [navbar](navbar.md). Consistency-audit decisions (do not re-litigate):

- **Applied:** secondary text grey `#AAAAAA` everywhere (Home artist line, Now Playing times, artist
  and album lines, `bigcover_page` artist line); `#8C8C8C` stays the muted partner grey. Pressed surfaces `#333333`.
- **Rejected:** lock screen's `#DDDDDD` artist line (sits on a wallpaper); queue's stock muted rows
  (derived from stock style).
- **Rejected:** merging disc greys `#777777` / `#555555` / `#666666` / `#444444` (disc, pressed disc,
  unlit glyph, disabled tile: one job each).
- **Rejected:** unifying glyph stroke scaling (Home discs 3.2 px, 40 px discs 2.2 px, tiles 2.3 px,
  status 1.5 px). Strokes are 2 px on the icon sets' 24 grid scaled to glyph size, so weight ratio
  is equal.
- **Rejected:** unifying the font size ladder (22/20 titles, 21 rows, 18 second lines, 16 captions,
  15/16 meta), row heights (52, 60/64, 56, 50, 44) and margins 12 vs 16 (code-built geometry or
  stock dialogs; changing one moves hit targets).
