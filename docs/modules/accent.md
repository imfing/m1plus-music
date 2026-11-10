# Accent and the palette

**Sources:** `patch/palette.c`, `patch/palette.h`, `tools/palette.py` (the model), `tools/palette_audit.py`, `tools/pod.py` (`STYLE_COLOR`, `IMAGE_ADD`, `STYLE_GRADIENT`, `LIGHT_PINS`), `tools/preview_settings.py`
(`settings-light.png`), `tools/preview_accent.py` (the mock-up sheet), test `test/pod/palette.py`. After q2-pod's Light Mode and accents (`ringnav_style_color`, `ringnav_style_gradient`,
`ringnav_image_add`, `ui_ink`; `README.md`).

The Accent feature lets the user pick the system accent colour, as the stock OS once had (its pressed row was `#362221`, from orange). It is built on **one palette layer**: every colour the painter gets
goes through `pal_map(colour)`, which takes the **background** (Black, or Light: Light Mode's neutral flip) and the **accent**. Phase 1 built the layer and brought Light Mode onto it; phase 2 added the accent mapping and its saved setting, phase 3 the picker, the pressed glyph and the previews. The Light Mode row is hidden from Settings. Black + Neutral is the identity: every hook is a plain pass-through and the
device renders as before.

The stock theme1 is forced off (`tools/themeoff.py`, [theme](theme.md) "theme1 is off"): the palette maps the modded default theme only.

## Design (the whole feature)

Settings picker: **Neutral** (default, today's look exactly), **Red** `#FF453A`, **Orange** `#FF9F0A`, **Green** `#30D158`, **Teal** `#40C8E0`, **Purple** `#BF5AF2`, **Champagne** `#C8A96A`.
Mock-up: `tools/preview_accent.py WORKDIR` (`out/preview/accent-black.png`): rows are the accents, columns the screens. The background stays Black (no Graphite); Light is a later "background" option.

Roles (Neutral keeps today's colour for every one):

| Role | With an accent |
|---|---|
| pressed row / card | soft tint `mix(surface, accent, 0.22)` (surface = the card `#1C1C1C` or the page black); the text stays white |
| row glyphs | the M1+ Music rows (`pod_ic_*`) and the Folders list's own glyphs (`fo_ic_*`), and the Settings cards' glyphs (`pod_ci_*`) are the accent at rest (tinted at decode from the one white image: no per-accent image files, rootfs headroom is tight); the row text stays white, a pressed row is the 22 % tint |
| switch on | the track is the accent, the knob white |
| Podcasts Library tiles (Discover, Downloads, Subscriptions, Saved) | the glyph is the accent, the 44 px `#1E1E1E` square stays exactly (kind TILE: white goes to the accent, the square's grey stays, the glyph's antialiased edge blends by lightness; `ACCENT_TILE`, `ACC_TILE_R` 30; each is an image of its own, `pod_ic_dltile` since the atlas can not be tinted by name) |
| pull-down ON tiles | the disc is the accent, the glyph stays `#141414` |
| pressed Play / Shuffle button | accent on press, glyph and label unchanged. Dark buttons (the flat pills of Songs, Folders and playlist pages, the Queue's Shuffle and Repeat while off) press as the soft tint of their own rest colour, `mix(rest, accent, 22 %)` (role colours `ROLE_PRESS_PILL` `#333335` over `#1E1E1E`, `ROLE_PRESS_QPILL` `#3A3A3D` over `#2C2C2E`); the album, playlist and Daily Mix pages' Shuffle disc (`ah_shuffle_down`) the same over its `#2A2A2A` rest (image kind SHUFDOWN); the white Play pills (`ah_pill_down` on the album and playlist pages, `dp_pill_down`) press as the solid accent, their dark glyph and label stay dark |
| slider fill, progress fill, picker check, playing wave marker | the accent |
| never accent | chevrons, secondary text, the navbar, body text, card backgrounds |

Pages whose background is the album/cover tint (Now Playing, the album page, the Podcasts Show page, the Daily Mix page, Radio Now Playing (`m1plus_radionp_page`, `PAL_COVER_RN`; its window colour goes through `pal_tone`)) keep that background exactly; their controls (the progress fill, ...) may take
the accent.

## What phase 1 did

- Brought in Light Mode (commit `7edddccf` of `feat/light-mode`, single commit on `22352999`, not device-tested) and rebased it onto main: the settings file follows the settings folder
  (`/mnt/data/m1plus/appearance-light`, `LIGHT_FILE` in `patch/home.h`; read and written through `home_write_atomic`, the directory fsync is the folder's); its ids and hook numbers have since moved (now
  `ACT_BG` 46 / `ACT_BGSET` 47, hooks 10 - 12 after main's battery and time-zone hooks; the pages are appended after `RELNOTES`: `BG_PAGE_INDEX` 38 .. `APPEARANCE_PAGE_INDEX` 40).
- Generalised the flip into the palette layer (`patch/palette.c`, former `light.c`): `pal_map` (below), `pal_active`, `pal_background`, `pal_accent`. The hooks test `pal_active` (was `light_on`) and
  call `pal_map` (was `light_flip`); `ui_ink` / `ui_fill_color` too. Renames: `light_on` -> `pal_light`, `light_mode` / `light_set` -> `pal_bg_mode` / `pal_bg_set`, `light_tone` -> `pal_tone`,
  `tools/light.py` -> `tools/palette.py`, `test/pod/light.py` -> `test/pod/palette.py`. `LIGHT_*` constants and the Light flip functions (`light_flip`, `light_is_neutral`, `light_image`) keep their names:
  they are the Light background's mapping.
- Hid the Light Mode row from Settings > System (the picker page, its actions and strings stay; `test/pod/palette.py` opens the picker through a row it builds itself).
- Merged the mock-up (`feat/accent-mockup`: `tools/preview_accent.py`, `preview_settings.draw_page(pal=..., pressed=...)`).
- No visible change with the defaults; no golden changed beyond what the cherry-pick needed (the new payload symbols and the new page).

### The palette API

C (`patch/palette.h`):

```
enum { PAL_BLACK, PAL_LIGHT };  enum { PAL_NEUTRAL, PAL_RED, ... PAL_CHAMPAGNE, PAL_ACCENTS };   /* the effective background, and the accent's saved index */
int pal_background(void);  int pal_accent(void);           /* effective: kill switch / bad-boot note give Black + Neutral */
int pal_active(void);                                       /* not Black + Neutral: the hooks are pass-throughs while this is 0 */
unsigned pal_map(unsigned c);                               /* THE entry point: an accent's role colour, else the background (color_t word, alpha kept) */
unsigned ui_ink(unsigned c);  ui_fill_color(canvas, c)      /* the payload's own drawing: pal_map unless inactive or clear (alpha 0) */
int pal_light(void);  unsigned pal_tone(unsigned tone);     /* background is Light; the cover-tinted pages' tone (neutral in Light; never a role colour: pal_not_role) */
int pal_bg_mode(void);  int pal_bg_set(int mode);           /* the Light setting 0 Off, 1 On, 2 Auto: saved atomically, applied at once */
int pal_accent_set(int i);   /* THE phase 3 setter: saves 0..6 atomically, applies at once; returns i, or -1 (bad index / failed save: nothing changes) */
int pal_accent_saved(void);  /* the saved index (what a picker checks; pal_accent() is the effective one) */
unsigned pal_accent_color(int i);  /* accent i as an opaque color_t word (swatches; Neutral: #EEEEEC) */
unsigned pal_fill(void);     /* the fills' colour now: the effective accent's, or #EEEEEC (pages that bake it into a bitmap) */
```

Python model (`tools/palette.py`): `map_colour(c, bg='black', ac='neutral')` with `BACKGROUNDS`, `ACCENTS`, `ACCENT_RGB`, `role`, `row_press`, `card_press`, `accent_pixel`, `render_image` (the accent's
and Light's image rule), the name lists `ACCENT_FILL` / `ACCENT_SWITCH` / `ACCENT_PRESS`, the Light helpers (`flip`, `ink`, `image_flips`, `flip_image`). `test/pod/palette.py` runs the
compiled `pal_map` against it.

## What phase 2 did (the mapping, no UI)

Built the accent into the palette layer. There is no picker and no Settings row yet, and the Light row stays hidden; with the saved accent Neutral (the default, no file) every hook is a pass-through and the
device renders as on main, apart from the one-level role-colour tweaks below.

- **Role colours are unique** (`ROLE_*`, `ACC_*` in `patch/offsets.inc`, read by `tools/palette.py`). A pressed row is `#333334` (was `#333333`): `PRESSED` in `tools/mod_theme.py` (the list rows, the table rows,
  the two keyboard keys, and the page style files that copy them: Playlists' row, the Search tabs), `LIST_PRESS` `0xff343333` (every payload list: Songs, Artists, Albums list, Folders, Queue, Search, Podcasts,
  Online Art), `PRESS_RGB` in `tools/pod_search.py`. The Now Playing progress fill is `#FFFFFEEB` (was `#FFFFFFEB`, which the page dots share): `FILL` in `tools/mod_nowplaying.py`. Both are one level off a grey
  or white that stays; `#333333` (hairline in cards, track, the select bars' and Online Art pills, tiles) and `#FFFFFF` map to nothing. The Play / Shuffle pills' pressed colour is the third role colour, `#333335`; see "Pressed Play / Shuffle buttons". The pressed card is an image (`pod_cd_*_down`, `#2C2C2E`), found by name, so it needs no
  unique colour. `roles_tests` scans every built style and page (default theme) and the payload/tool sources: the role colours are only where they are defined; a grid of dark cover tones and the neutral tone
  are not role colours (the cover-tinted backgrounds are untouched).
- **`pal_map`** looks for a role colour first (rgb compared, alpha kept) and, if it is one, returns the accent's: pressed row `mix(black, accent, 22 %)` (Red: `#380F0D`), progress fill = the accent. Otherwise the
  background (Light's flip) as before. Order differs from phase 1's "background, then accent": a role colour is neutral, and Light's flip would change it before the accent could find it. Model `map_colour`/`role`.
- **The setting** `/mnt/data/m1plus/appearance-accent` (`ACCENT_FILE`/`ACCENT_TMP` in `patch/home.h`): one digit 0..6 (`set_read`; anything else or missing = Neutral), written by `pal_accent_set` through
  `home_write_atomic`. The state is `pal.acc` (saved) and `pal.acc_on` (effective: 0 under the kill switch `/mnt/mmc/m1plus-off`, the flash one or `/mnt/data/m1plus-bad`). One `pal_refresh` computes both
  that and Light's `pal.on`; a change goes through `pal_apply` (cached images dropped, tinted pages relit, window manager repainted). The one UI-thread timer (a minute) now lives while the background is not
  Black **or** the accent is not Neutral (the tick re-evaluates the kill switch for either), and ends when both are back.
- **Image tint** (`accent_image`, `pal_image`): exact names, generated into `stock.h` from `tools/palette.py` as `ACCENT_FILL`, `ACCENT_SWITCH`, `ACCENT_PRESS`. A tinted name is tinted *instead of* flipped (the
  accent wins over Light). FILL (`vol_progress`, `volume_fg`, `drop_fg`, `eq_plan`, `other_progress`, `cdprogress_bar`, `datetime_back`, `pod_check`, `np_row_playing`): each pixel goes from its colour to the
  accent by how light its red is (51 -> 238), so a track keeps its grey and antialiased edges blend. SWITCH (`sset_on`): the `#EEEEEC` track to the accent, the `#141414` knob to white (the blend through the
  pixel's darkness). PRESS (`pod_cd_single/top/mid/bot_down`): the pressed settings card, `mix(#1C1C1C, accent, 22 %)`. DISC (`ACCENT_DISC`): the pull-down's ON tiles (`drop_wifiopen`, `drop_btopen`, `drop_keylockopen`, `drop_eqopen`, `drop_usbaudio`, `drop_usbdac`, `drop_usbstorage`, `drop_playsetdown`, `drop_syssetdown`, `drop_highgain`, `drop_lo`; [pull-down](pulldown.md)): a pixel goes from `#141414` (stays) to white (the accent) by its lightness, so the disc is the accent, the glyph stays dark (white on Orange or Teal would be about 2:1) and the antialiased edges blend; off (`#777777`) and disabled (`#444444`) tiles are untouched. Glyph on the accent: Red 5.41, Orange 8.96, Green 9.11, Teal 9.26, Purple 5.23, Champagne 8.19. Tint cost about 0.31 M instructions per tile, once per decode. Premultiplied pixels are converted to straight and back; formats 1..4. `ah_wave` (the
  album page's playing marker) is baked by `ab_make_wave` when the page opens, in `pal_fill()` (the accent, else `AB_WAVE_COLOR`); it does not follow a change under an open page (like the Daily Mix art).
  `tools/palette_audit.py WORKDIR` lists the tinted names with their size and what Light would have done.
- **Exempt windows**: the style hooks' `pal_styled` is shared, so the lock screen, the full-screen cover, the power-off splash, the Pod and Cassette Mode keep their colours under an accent too. Images are
  global: none of the accent names is in `KEEP`, and those pages do not use them.
- **Cover-tinted pages** are unchanged (their window colour is the cover tone, never a role colour); their progress fill (Now Playing) and wave (album page) take the accent. The Show and Daily Mix pages have
  no control the accent changes yet (no progress fill; their pressed rows are `LIST_PRESS`).
- **Not done in phase 2 (phase 3 did it, below)**: the pressed row's **glyph in the accent**. The build has no `_down` twin of a row glyph (the `_down` images are navbar/pill glyphs, which never take the accent, and the
  Home grid's discs); a settings row's `pod_icon` is one image in every state. The phase 3 picker work (or a later pass) needs a press handler that swaps the glyph, plus images that the hook tints.
  Chevrons, secondary text, navbar, body text, card and page backgrounds are not touched.
- **Cost** (Unicorn instruction counts, `test/pod/palette.py`): the style hook, a role colour with an accent on 646 instructions, any other colour 558 (stock's own part included; Light on is under 900,
  Black + Neutral about 600 with no work of ours); the image hook on a name it does not tint 1165 (the three name lists, once per decoded image); a tint is once per decode: `datetime_back` 5.4 M (280 x 150),
  `pod_cd_*_down` 1.6 M each, `vol_progress` 1.4 M, `other_progress` 1.1 M, `cdprogress_bar` 1.0 M, `sset_on` 0.14 M, the rest under 0.3 M. Cached by the image manager; a change of accent unloads them all.
- **Tests** (`test/pod/palette.py`: `accent_map_tests`, `accent_image_tests`, `accent_setting_tests`, `roles_tests`): `pal_map` for every accent and both backgrounds against the model, the style, gradient
  and `ui_ink` paths, exempt windows, Black + Neutral identity, every tinted image of the tree for all six accents pixel for pixel, the other images unchanged, premultiplied and formats, the setting (read,
  atomic save, bad values, round trip to the next boot, kill switch, the tick, one timer with Light).

## Pressed Play / Shuffle buttons

On our own pages every Play / Shuffle button presses in the accent, one rule; Neutral keeps today's pressed greys (the three pressed role colours are one blue level off today's, so a Neutral device differs by one LSB, as the pressed row's `#333334` does).

| Page | Button | Rest | Pressed before | Pressed with an accent |
|---|---|---|---|---|
| Songs, playlist pages, Folders (`btn_play`, `btn_shuffle`; `tools/pod_ui.py` `sg_pill(..., down=SG_PILL_PRESS_RGB)`) | flat pill 129 x 40 | `#1E1E1E` | `#333333` | `ROLE_PRESS_PILL` `#333335` becomes `mix(#1E1E1E, accent, 22 %)` (Tinted: the tinted rest first); glyph and label white |
| Queue (`btn_shuffle`, `btn_repeat`, `qp_pill`) | icon-only pill, off | `#2C2C2E` | `#3A3A3C` | `ROLE_PRESS_QPILL` `#3A3A3D` becomes `mix(#2C2C2E, accent, 22 %)`; the lit (on) state `#C8C8C8` / `#A8A8A8` is an on-state and is left |
| Album page, a playlist's page, Daily Mix page (`ah_shuffle_down`) | Shuffle disc | `#2A2A2A` | `#444444` disc | image kind SHUFDOWN: the disc becomes `mix(#2A2A2A, accent, 22 %)`, the white glyph stays (antialiased edge by lightness) |
| Album page, a playlist's page (`ah_pill_down`) | white Play pill | `#FFFFFF` | `#BEBEBE` | solid accent (`ACCENT_GLYPH_STOCK`: every pixel the accent, alpha kept); the dark glyph and the label are drawn apart and stay dark |
| Daily Mix page (`dp_pill_down`) | white Play pill | `#FFFFFF` | `#D6D6D8` | solid accent, as above |

The images are tinted by name at decode, which is global, so the cover-tinted pages (album page, Daily Mix) get them too; only their background is left alone. `pal_not_role` moves a cover colour equal to a pill role one blue level off it. Not changed on purpose: the select bars' pills (Delete, Add to Playlist, Unsubscribe) and Online Art's pills are not Play / Shuffle and keep `#333333`; the Daily Mix page's Add disc (`dp_add_down`); the Podcasts Show page's Latest Episode pill (painted by the payload, it has no pressed look to colour); Now Playing's and Radio's transport buttons. Tests: `press_tests` in `test/pod/palette.py`.

## What phase 3 did (picker, row glyphs, previews)

- **Picker.** Settings > System > **Appearance** (`ACT_PAGE`, a link row with glyph `palette`, between Display and Keyboards where the hidden Light row sat) opens `m1plus_appearance` (`APPEARANCE_PAGE`, page index 40, the last of
  `PAGES`): one card with the **Accent** value row (`ACT_ACCENT` 48, the accent's name, glyph `palette`; the shared value refresh sets it on whichever page it sits). The hidden Light row will become a "Background" row on this page. The Accent row opens `m1plus_accent`
  (`ACCENT_PAGE`, page index 39; back returns to Appearance): Neutral, Red, Orange, Green, Teal, Purple, Champagne (`ACT_ACCENTSET` 49, arg = the saved index), one check row each with a round swatch (`pod_sw<i>`, 20 px disc in a
  24 px canvas, the child `pod_swatch` at the glyph's place; Neutral `#EEEEEC`) and the check on `pal_accent_saved()`. A tap calls `pal_accent_set` (saved atomically, applied at once; a failed save changes
  nothing). The swatches are in `KEEP` (never flipped) and in no accent list (never tinted). Strings are in `tools/pod_i18n.py` (all tables). The Light row stays hidden.
- **Row glyphs.** The M1+ Music rows' glyphs (`pod_ic_*`: the main menu, Shuffle, Extras and Main Menu pages) are the accent at rest: `pal_image` tints them when they are decoded (kind GLYPH, name prefix
  `ACCENT_GLYPH` (`pod_ic_`, `fo_ic_`, `pod_ci_` and `rm_ic_`, the track rows' "..." sheet's six glyphs: a prefix, because six exact names cost the hook on every untinted image about 200 instructions more) generated from `tools/palette.py` into `stock.h`, minus the four Library tiles `ACCENT_GLYPH_NOT` (`ACCENT_TILE`: `pod_ic_dltile`, `pod_ic_subtile`, `pod_ic_savetile`, `pod_ic_discovertile`, kind TILE, below) and the Radio placeholder art `pod_ic_rd_art`, secondary art that stays neutral; plus stock and sheet glyphs by exact name, `ACCENT_GLYPH_STOCK`: the More sheet's `player_albuminfo`, `player_songerinfo`, `p_add`, `p_multiple`, `p_abrepeat`, `p_delete`; the Podcasts sheets' `pc_ic_import`, `pc_ic_speed`, `pc_ic_refresh`, `pc_ic_select`, `pc_ic_check`, `pc_ic_down`, `pc_ic_undo`, `pc_ic_trash` (also Radio's Clear row); the Playlists "..." menu's `pl_ic_new`, `pl_ic_import`, `pl_ic_export`, `pl_ic_delete`; the Add dialog's `batchadd_fav`, `batchadd_playlist`; the checks `sg_tick` (Songs sort card) and `mulselected` (stock Select All, checked); the red `pc_ic_unsub` is not tinted (labels keep their colour); the stock `selected` is not tinted: besides our select marks it is the Delete dialog's "also delete the file" checkbox), every colour becomes the accent, alpha kept, premultiplied
  handled (`accent_pixel('glyph')`). Nothing is kept and nothing is pinned: an evicted glyph decodes and tints again, an accent or background change drops the cache (`pal_apply`'s
  `image_manager_unload_all`), Neutral is untouched, and the glyph kind wins over Light's flip as the other accent kinds do. The Folders list's own glyphs `fo_ic_sd`, `fo_ic_usb`, `fo_ic_file` (patch/folders.c, `FOLDER_ROWS`: plain white 24 px glyphs, used nowhere else) are in `ACCENT_GLYPH` too (prefix `fo_ic_`), so the whole Folders list is one colour scheme. Other users of `pod_ic_*` in the build, which are tinted too: the Folders list
  (`pod_ic_folders`, `pod_ic_playlists`, `pod_ic_cdripper`, `pod_ic_nowplaying`; patch/folders.c), Now Playing's More sheet (`pod_ic_extras`, `pod_ic_tape`, `pod_ic_vinyl`, `pod_ic_art`, `pod_ic_sleep`, `pod_ic_podcasts`),
  the Export OPML / Save Episode rows (`pod_ic_export`, `pod_ic_save`). Cost: 64.6 k instructions per 24 x 24 decode (`rest_glyph_tests`), once per decode.
- **One decode-time rule for every row glyph** (the pressed-glyph copy path is gone). The Settings cards' `pod_ci_*` (tools/mod_icons.py `CARD_GLYPHS`: Wi-Fi, Bluetooth, Home Screen, Library, ... Battery
  Percentage, 35 images incl. the Shanling mark) are in `ACCENT_GLYPH` (prefix `pod_ci_`), so `pal_image` tints them at decode like `pod_ic_*` and `fo_ic_*`: a Settings row shows the accent glyph at rest and
  pressed (the pressed row is the 22 % tint, `pod_cd_*_down`), the text stays white. No exclusion was needed: every `pod_ci_*` is a plain white single-colour glyph, only shown on the Settings card rows
  (`cards_row`), none on a cover-tinted page (Now Playing, album page, Show, Daily Mix show none). `ACCENT_GLYPH_NOT` is the three tiles and `pod_ic_rd_art`. The accent swatches `pod_sw*` (and `pod_chev`, `pod_check`'s
  fill rule) are other names and untouched; the stock Settings pages' 40 px disc icons are stock images, not in scope.
  **Removed:** `glyph_down` / `glyph_make` / `glyph_ensure` / `glyph_base` / `glyph_set` / `glyph_restore` / `glyph_touch` / `glyph_gone` / `pal_glyph_bind` (and its call in `open_page`, `patch/m1plus.c`), the
  `<name>_acc` copies, `glyph_state`, the row's DOWN / UP / ABORT and the glyph's DESTROY handlers, the `image_manager_lookup` / `image_manager_get_bitmap` bindings in `tools/pod.py` (`FUNCTIONS`), the
  direct `stock_image_add_trampoline` use (the hook still ends in it) and the `0x30` free-data handling, `palette.glyph_image` / `GLYPH_SUFFIX` in the model, `glyph_tests`. Nothing needs a press-time swap
  now: no glyph is white-until-pressed. **Eviction findings** (kept as knowledge, `docs/modules/addresses.md`: lookup versus get_bitmap, `image_manager_unload_unused`, the cache entry's access time): stock's
  `image_manager_unload_unused(imm, age)` (`0x655f58`) has one caller, the main loop's memory handler (`0x5f2790`): level 1 age 10 s, level 2 age 0 (everything), level 3 also `font_manager_unload_all`; it
  keeps an entry only when `now - last access` is under `age`, and every lookup hit sets the access time to now. A decoded, tinted glyph needs no protection: an evicted one decodes and tints again.
  Cost: 64.6 k instructions per 24 x 24 decode (`rest_glyph_tests`), once per decode; a press costs nothing.
- **Tiles.** The Podcasts page's four Library tiles (`patch/podcasts.c`, `pg_dltile` / `pg_subtile` / `pg_savetile` / `pg_srchtile`, all decoded by `pg_rgba` and blitted the same way) are kind TILE (`accent_pixel('tile')`, C kind 5 in `accent_image`): the disc rule with `ACC_TILE_R` (30) as the fixed end, so white is the accent and the `#1E1E1E` square is exactly `#1E1E1E`. Downloads' tile left `pc_atlas` for `pod_ic_dltile` for this (the atlas has no tile any more; `PA_TILE_X/Y` are gone). `in_names` rejects on the first letter before `strcmp`, which keeps the untinted-image hook under its budget (3248 instructions after the row sheet's glyphs, test limit 3400). A tile is decoded once, when the page's first paint needs it, so an accent changed while the Podcasts page is alive shows at its next open.
- **Mixed pixels.** `other_progress` and `datetime_back` rendered per accent (`out/preview/accent-tints.png`): `datetime_back` only has its selector line to tint; `other_progress`'s antialiased edge pixels
  (fill over its grey track) were lightened towards grey by the old blend. FILL now sends a pixel as light as the fill to the accent, leaves one at the track or darker, and moves one between by its
  share of the way fill -> accent (`v + (accent - fill) * t`), which is the accent over the track.
- **Previews.** `accent-picker.png` starts with the Appearance page. `tools/preview_accent.py` draws through the model (`map_colour`, `render_image`, which also tints the row glyphs; the neutral pressed row is `#333334`): `accent-black.png` (Settings, the M1+ menu, a song list, controls,
  Now Playing), `accent-picker.png`, `accent-tints.png` and the contrast table; `make preview` runs it.
- **Contrast** (accent on the pressed card tint / on black / on the pressed row tint): Red 3.82 / 6.16 / 4.96, Orange 5.31 / 10.22 / 7.25, Green 5.41 / 10.39 / 7.34, Teal 5.43 / 10.56 / 7.42,
  Purple 3.61 / 5.96 / 4.77, Champagne 4.93 / 9.34 / 6.75.
- **Not covered by the row-glyph tint:** payload-painted lists (Songs, Albums, Artists, Folders, Queue, Search, Podcasts, Playlists, Online Art; their rows have a cover or no glyph), the Home grid, the
  stock pages (Display, All Settings, Wi-Fi), the More sheets and dialogs, the navbar buttons, the stock Settings pages' 40 px disc icons.

## What the Background step did (Tinted, menu glyphs)

- **Setting.** `/mnt/data/m1plus/appearance-background` (`BG_FILE`, replaces the never-shipped `appearance-light`): `0` Black, `1` Tinted, `2` Light, `3` Light Auto; others Black. Picker `m1plus_background` (`BG_PAGE`, `ACT_BG` 46 / `ACT_BGSET` 47) offers Black and Tinted, opened from the Background row of Appearance (above Accent). Light is only reachable by editing the file.
- **Tinted** (`pal_wash`, model `wash`): in `pal_map`, after the role step, a dark neutral colour (channels within `LIGHT_SPREAD`, none above `ACC_DARK` 0x40) takes `ACC_WASH` 12 % of the accent: page black Teal `#08181B`, Red `#1F0807`, Purple `#170B1D`, Champagne `#18140D`; card `#1C1C1C` -> `mix(card, accent, 12 %)`. The pressed role is `mix(tinted surface, accent, 22 %)` (row, and `pod_cd_*_down` via `accent_image`). Images: `TINT_SURFACE` (the `WHOLE` list without `np_tint`, `np_scrim`, `ah_tint`) get the same per-pixel wash (`tint_image`, premultiplied handled); covers (names with `/` or `:`), KEEP and the exempt windows are untouched. Tinted + Neutral is Black (`tint_on` needs an accent). Slider/switch/disc images keep their own tint rules.
- **Cover-tinted pages are left by window, not by colour.** While the top main window is Now Playing (`playing_page`), the Daily Mix page (`m1plus_dailymix_page`), the album page (`m1plus_album_page`) showing a tone (`ab_has_tone`: tinted) or the Podcasts Show page (`m1plus_podcasts_page`, `pg_has_tone`: a Show, not the shows list or an episode) the wash does not apply to any colour (`pal_cover_page`, `COVER_PAGES` in `tools/palette.py` -> `LIGHT_COVER`, cached per top window and name pointer with the exempt check; model `map_colour(cover=True)`). Only the background wash is dropped: the accent roles (progress fill, pressed rows) and the images (global) still apply. This covers `pod_corners` on Now Playing (the corners match the cover tone behind them) and the status bar while one of these pages is in front. A window opened over a page follows its own name; during a slide the page that is leaving is painted by the rule of the page in front. The old colour registry (`pal_keep`, `pal_kept`, the keep table, the `NP_NEUTRAL` special case) is gone: a cover that averaged a grey no longer left that colour untinted on other pages. The black fades `np_tint`, `np_scrim`, `ah_tint` are not tinted.
- **A cover colour is never a role colour.** `pal_not_role` (`pal_tone`, `pod_shade`, `pod_bar_color`; model `not_role`) moves a cover-derived colour that equals `ROLE_PRESS_ROW`, `ROLE_PROGRESS`, `ROLE_PRESS_PILL` or `ROLE_PRESS_QPILL` one LSB of blue (`#333334` -> `#333333`, `#FFFFFE` -> `#FFFFFF`), so a cover averaging (31, 31, 32) is not a pressed row. Pure, applied in every state. Tests `findings_tests`.
- **Menu glyphs.** The `pod_ic_*`, `fo_ic_*` and `pod_ci_*` glyphs are all tinted at decode (see Row glyphs).
- **Cost** (Unicorn): style hook with Tinted 752 instr on a dark neutral, 623 on any other (Light on 916, was under 900; Black + Neutral about 650); image hook 2075 on a non-surface name; tint once per decode: `pod_cd_mid` 2.25 M, `mb_glass` 2.30 M, `nb_fade` 0.74 M, `pc_sheet`/`pm_sheet` up to 13.6 M, pressed pieces 1.65 M; glyph tint 64.6 k per 24 x 24 decode.
- **Previews:** `tools/preview_accent.py` draws through the model; `accent-tinted.png` (Tinted x accents: menu, Settings, Appearance, songs, pull-down, Now Playing). The mock-up sheets were removed. Contrast (8C grey on page / card, Teal) 5.40 / 4.03.
- **Not covered / risks:** device untested; the at-rest glyph tint is device untested (open the menu right after boot; leave it behind another page and come back); the navbar fade `nb_fade` is global, so on a cover-tinted page it is a tinted black over the cover tone; slider/progress tracks (`#333`) stay neutral; Tinted + Light is not a combination.

## Open / later

- Device: nothing of the Accent has run on hardware ([device checks](device-checks.md), ACCENT-01..04); the Settings glyphs' tint at decode (ACCENT-06) is untested on hardware.
- Graphite and Light in the picker; Light + an accent (the pressed card piece mixes with the dark card colour, so it is wrong on Light).
- Stock pages using `btn_tab_style` / `btn_tablerow_style` press in the accent; the one-minute timer exists whenever an accent is saved.

## Background: Light (the hooks)

The Light background is the former Light Mode, hidden for now. Its setting: Off (default, Black), On, Auto; the picker is `m1plus_light` (three check rows, `ACT_LIGHT` / `ACT_LIGHTSET`), saved atomically
in `/mnt/data/m1plus/appearance-light` (`1` On, `2` Auto, optional newline; anything else or missing Off) and applied at once. Auto is light from 07:00 to 18:59 by the device clock (`localtime`), dark
otherwise. Not verified on the device. The hooks below serve both backgrounds and the accent.

The UI is dark by construction (stock theme edits, our own pages), so Light Mode flips colours at the three places the painter gets them, instead of editing assets.

- **The flip.** A neutral colour (channels within `LIGHT_SPREAD` 16 of each other) flips per channel: black becomes `LIGHT_PAPER` (`#F4F4F4`), white `LIGHT_INK` (`#161616`), linearly in between; alpha is kept, a
  colour with a hue stays, a clear colour (alpha 0) stays clear (stock tests for it). The numbers are in `patch/offsets.inc` (`LIGHT_*`), read by `tools/palette.py`.
- **`style_get_color`** (hook 10, payload.md) maps every colour a style gives. Only the outermost call maps (a mutable style, `widget_set_style`, answers through `style_get_color` again and the flip is not idempotent:
  `pal.depth`). `selected_text_color` is never mapped (a text input's pending letter on its light blue selection).
- **`style_get_gradient`** (hook 10, a leaf: its first two words become the jump, the payload does all of it) maps the stops `widget_fill_rect` asks for (`bg_color`). `style_get_color`'s own call to it (return address
  `STYLE_COLOR_GRADIENT_RET` 0x65a050) stays unmapped: its colour is mapped once, by the colour hook.
- **`image_manager_add`** (hook 11) maps a decoded theme image before the manager copies and caches it (the copy shares the pixel buffer). Only a plain asset name is the theme's: a `/` or `:` is a cover by path or URL and
  never changes. Rules (`light_image`, modelled by `tools/palette.py image_flips`): names in `KEEP` stay (the cassette `tape_*`, the Pod's `ipod_*`, `np_shadow`, `lk_card`, `dm_disc`); names in `WHOLE` (the Settings
  cards `pod_cd_*`, the bottom sheets `pc_sheet*` / `pm_sheet*`, the mini player's glass `mb_glass*`, the fades `nb_fade`, `np_tint`, `np_scrim`, `ah_tint`) flip every neutral pixel; any other image flips whole when it
  has no colour (no opaque pixel more than `LIGHT_CHROMA` 40 saturated) and is mostly glyph (under 1/`LIGHT_SURFACE` of its area opaque and darker than `LIGHT_GLYPH`). So white marks, chevrons and status icons turn
  dark, and a grey or dark disc keeps its white glyph, as on the Home grid. `tools/palette_audit.py WORKDIR --sheet X.png [--kept] [--only P1,P2]` draws what flips and what stays.
- **The payload's own drawing** goes through `ui_ink` (`ui_fill_color`: the list hairlines and press fills, the rail dots, Daily Mix fills, the cover corners) and the Cover Flow shelf is composited over paper
  (`cfg_t.bg`; the landscape captions' ink flips). Album art, covers, wallpapers, photos and videos never change; neither do the placeholders drawn into cover bitmaps.
- **Exempt windows** (`EXEMPT` in `tools/palette.py`): while the top main window is the lock screen (`screensaver_page`: a wallpaper under text and a dark glass card), the full-screen cover (`bigcover_page`), the power-off
  splash, the Pod (`m1plus_ipod_page`, which has its own light and dark theme) or Cassette Mode (`m1plus_tape_page`), the style hooks pass through (`pal_exempt`: the answer is cached per top window and its name
  pointer; a page that slides in over a light one is painted dark for the transition). Images are global, so exempt pages' own pictures are in `KEEP`.
- **Cover-tinted pages** (Now Playing, the album page, the Podcasts Show page, the Daily Mix page) put white text on a dark chromatic tone of the cover. A chromatic colour does not flip but its text does, so the tone
  would be dark under dark ink. Decision: in Light Mode these pages have **no tint**: the tone is the page's neutral colour (`pal_tone`, `NP_NEUTRAL`), which the style hook flips to a light grey, and the black fades over
  them become paper fades. The pages keep the tone as chosen (`np_tone_raw`, `ab_tone_raw` in `patch/albumpage.c`, `pg_tone_raw`) and tint again (`*_relight`) when the mode changes while they are open. The Daily Mix page's card art fades into paper
  and its greys are neutral; its art is made once when the page opens, so a mode change under an open Daily Mix page shows at its next open. A light tint (pastel final colours the hook must not flip) would need a
  marker the hooks respect; not done.
- **The clock and the timer.** One UI-thread timer (`LIGHT_TICK_MS`, a minute, answering `RET_REPEAT`) exists while the setting is not Off. Each tick re-evaluates the setting's effect: Auto's hour, the kill switch and
  the bad-boot note. A change drops the cached images (`image_manager_unload_all`, which the window manager's locale handler also calls), lets the open tinted pages tint again and repaints the window manager.
  Nothing is done per paint but a flag test (and, in Light Mode, a top-window look in the style hooks). This timer is the one global timer of the payload; it exists only while Light Mode or an accent is chosen.

## Safety

Hooks 10 - 12 are the accepted relaxation of "nothing at paint": pinned (`LIGHT_PINS`, the three prologues / leaf words, the words each trampoline resumes at, the gradient `bal`, `image_manager_add`'s two callers),
each falls back to stock (the trampolines run stock's own code; the gradient hook reimplements the leaf exactly), and each is a pass-through while the palette is inactive (Black + Neutral) (the setting, `/mnt/mmc/m1plus-off` or the flash
kill switch, or `/mnt/data/m1plus-bad`, the bad-boot note that sends the next boot to stock). The setting is read at the first call (the first paint), the kill switch again at each tick. A crash in a hook before the boot
guard arms is not covered by the guard: the SD kill switch is the way out.

## Limits and device checks

- Not verified on the device. Check: Settings and its pages, Home (menu, Recently Played, Daily Mix card whose text sits on art), Songs / Albums / Artists / Playlists lists, the keyboard, Cover Flow (portrait and landscape),
  Now Playing and its More sheet, the album and Show pages, the lock screen (must stay dark), the pull-down, dialogs, stock Settings pages, the Auto switch at 07:00 / 19:00 with a page open.
- Stock pages with colours of their own (Tidal, Hi-Res store, guides) keep their hues; their neutral parts flip.
- The mini player's backdrop blur and the Daily Mix card's text over art are drawn from white label styles: in Light Mode their text is ink over art.
- `tools/preview_settings.py` draws the Settings pages in Light Mode with the model; other pages have no light preview.
