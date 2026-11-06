# Navbars: one reference, every page on it

Goal: moving between pages never makes the Back arrow, the title or the right-hand icons jump. The reference is the M1+ Music pages' navbar
(`tools/pod_ui.py` `navbar()`, window coordinates inside the 50 px bar):

| Element | Reference |
|---|---|
| Back | button (0, 0, 80, 50), `navbar_btnreturn_style`: chevron glyph columns 14..22 |
| Title | label (36, 14, w, 22), 20 px white, left aligned (`navbar_label_white`) |
| Right slots | 46 wide, `img_btn_style` (icon centred): x 122 / 168 / 214 (`NAV_CF_X`, `NAV_VIEW_X`, `NAV_VIEW_W` in `patch/offsets.inc`), glyph centres 152 / 198 / 244 (7 px right of each slot's centre: 46 apart up to Now Playing's 290) |
| Now Playing | (260, 0, 60, 50), `img_btn_style`: glyph columns 280..299 (centre 290) |
| Bottom line | `navigationbar_line_style`, y 49, where a page has it |

Buttons from the right: Now Playing, then 214, 168, 122. A page with fewer buttons leaves the left slots empty.

## Rendering rules (AWTK `widget_draw_icon_text` 0x67235c, `widget_calc_icon_text_rect` 0x666f04; device shots)

- `navbar_btnreturn_style`: `icon_at` 1, `x_offset` -6: the icon is drawn in an h x h square at the button's left, centre x + h / 2 - 6.
  Any width keeps the glyph at 14..22 for h 50 (a 44 px button needs x 3).
- `navbar_btnbackplayer_style` (`icon_at` 5): measured on the device, its glyph sits 2 px left of where an `img_btn_style` button of the
  same box puts ours (278..297 against 280..299), so a stock Now Playing is 60 wide at x 262. `navbar_btnmulselect_style` is `icon_at` 5 too,
  but its glyph at x 214, 46 wide, lands exactly on the Pod toggle's columns (227..245 in both shots): no correction. So the shift is not a
  rule of `icon_at` 5; each style is placed by what the shots show, and an unmeasured `icon_at` 5 button (the folder picker's select-all,
  `navbar_btnunselect_style`) takes the plain slot like multi-select.
- `img_btn_style`, `search_style` (a `bg_image`): centred in the button.
- Stock titles built by code use `srlabel_leftwhite22_style` (22 px); the page theme (`tools/mod_lists.py` recipe `navtitle`) makes it 20 px.
  `navbar_label_white` and the other `navbar_*label_white` styles are 20 px since `mod_polish`.

## Survey

"Source" is where the bar's children come from: an asset (`ui/*.bin`, fixed rectangles) or code (builder address, the stock symbol names are
unreliable there: `cdripper_page_init+...`, `home_page_init+...`, `playing_page_init+...` are inside other pages' builders). The Back button is
(0, 0, 80, 50) and the title (36, 14) wherever it is not listed. Glyph centres are x of the glyph, the reference's in the header above.

| Page (how reached) | Source | Before | Fix |
|---|---|---|---|
| M1+ Music pages: Menu, Albums, Playlists, Artists, Cover Flow's artist/albums page, Extras, Settings, Main Menu, Shuffle, Cover Flow settings | assets `m1plus_*.bin` (`pod_ui.navbar()`) | the reference | none |
| Settings pages `systemset/*` (33), `playset/*` (all but Equalizer), `audiosetting_page`, the keyboard / edit dialogs: Back 80, title (36, 14) 20 px, Now Playing (260, 0, 60, 50) | assets | stock glyphs: a plain chevron and Now Playing glyph, the title at 36 | the glass navbar (`mod_ipodrows.glass_navbar`, every ui file with the stock Back, both themes; not the Bluetooth receiver): Back keeps its 80 px button and gets `ah_nav_back` with `x_offset` +4 (the disc at 8 .. 50), Now Playing the disc `ah_nav_np` (glyph 290), the title from 58, its right end kept or before the bar's next widget (a switch: 135 / 145 px on Atmosphere LED / Equalizer) |
| Settings > Equalizer (`playset/equalizer_page`) | asset | Now Playing (270, 0, 50, 50): glyph 295 | Now Playing (260, 0, 60, 50): `mod_ipodrows.edit_equalizer` |
| Update music > folder picker (`systemset/specfolder_page`) | asset | Now Playing (279, 0, 41, 50): glyph 299; select-all (229, 0, 38, 50), `icon_at` 5: glyph 246 | Now Playing (260, 0, 60, 50); select-all (214, 0, 46, 50), the multi-select slot; `mod_ipodrows.edit_specfolder` |
| Full-page volume screen (`dialog/volume_dialog`, the status bar tap): glass Back disc at y 34 .. 76 | asset | the root dialog is a 42 px strip stock never resizes, its 1 px black border (after the children, not clipped) ran across the page at y 41, through the disc | the border colour is transparent in normal / disable / focused: `mod_ipodrows.edit_volume` |
| Settings > Screen saver, Atmosphere LED: an on/off image `image_switch` (193, 11, 57, 28) in the bar | asset | a control, not a button | left alone: it has no Pod counterpart, and a switch at the 214 slot would overlap Now Playing |
| Equalizer's `img_switch` (203, 11, 57, 28) | asset | as above | left alone, same reason |
| Songs, Hi-Res, Favourites, Recently played / added, Most played, a playlist's songs (`allmusic_page`) and an album's page (`albuminfo_page`) | code, builder 0x526a3c (shared) | 50 px buttons, 22 px title, slots at 120 / 170 / 220 / 270 | done before this document: 44 px buttons, slots 122 / 168 / 214, Now Playing 262 x 60, Back x 3, title 20 px, the bar view of `allmusic_page` and `albuminfo_page` at y 3 (`mod_ipodrows.center_navbar`). The multi-select button stays at 214: the device shots put its glyph on the Pod toggle's columns |
| Folders (`folder_page`) | code, builder 0x5312dc | multi-select (224, 60 wide): glyph 252; search (178, 60): 208; Now Playing (270, 60): 298; title 22 px | multi-select 214 x 46, search 168 x 46, Now Playing 262 x 60 (`patch/rows.json`), title 20 px (`navtitle`) |
| Artists / Genres / Composers, stock page (`localclass_page`; Genres and Composers from Extras) | code, builder 0x535188 | artist switch / search (183, 60): 213; multi-select (224): 252; Now Playing (270): 298; title 22 px | the left button 168 x 46 (glyph 191), multi-select 214 x 46, Now Playing 262 x 60, title 20 px |
| Playlists, stock page (`playlist_page`, "Delete Playlists") | code, builder 0x53d5f8 | multi-select (224, 60): 252; Now Playing (270): 298; title 22 px | multi-select 214 x 46, Now Playing 262 x 60, title 20 px |
| An artist's albums (`album_page`, from the stock Artists page; the Pod's Albums page is its own) | code, builder 0x524e4c | multi-select (224, 60): 252; Now Playing (270): 298; no title | multi-select 214 x 46, Now Playing 262 x 60 |
| Search (`search_page`) | code, `search_page_init` (inline), edit field in the asset | Back 33 wide (glyph on the reference); go button `search_style` (273, 47): glyph 296 | go button (260, 60): glyph 290 (the edit field's list_item lies over its left 13 px, 47 px stay) |
| Queue / jump list (`playerjumpinfo_page`) | code, `playerjumpinfo_page_init` | title 22 px | title 20 px (before this document); Back only |

Not in scope and left alone: Now Playing's own full-screen header (`playing_page`), Now Playing's More sheet and the dialogs, the stock Home
(`home_page`: no navbar), Tidal, HiFi (`hifi/*`), Airplay, DLNA/online search, CD ripper (`cdripper_page`, `searchcdripper_page`, `rippingset_page`,
the builder 0x52c5e8), USB mode (its Back and DAC settings are the glass discs on the navbar's row: `mod_ipodrows.edit_usbmode`).

## Left alone, and why

- **Select mode of the stock lists.** Folders, Artists/Genres/Composers, Playlists and an artist's albums rebuild their bar when the
  multi-select button is tapped: a select-all button (0, 50 wide), an "All" label, add / delete / cancel buttons (116 / 191 / 268, 60 wide).
  It is a transient mode with a different set of buttons and no Pod counterpart; moving it would need new slots for three actions.
- **The Artists branch of `localclass_page`** keeps its artist-type switch on the 168 slot (the Pod's own Artists page has its `btn_artisttype`
  at 214): the multi-select button is built by code the Artists and Genres branches share, so only one of them can take 214. The stock Artists page
  is not reached from the Pod menu (the Pod's Artists page is `m1plus_artists`).
- **Search's Back** is 33 wide (the stock edit field starts at x 33 in the asset). The glyph is on the reference; the touch target stays.
- Title widths of the code-built labels stay stock (153 Folders, 147 Genres, 200 Playlists ...): they only decide where a long title ends.
  Nothing is hooked: every change is a pinned immediate of a button builder (`patch/rows.json`), a page theme or an asset rectangle.

## Mechanisms

- Immediates: `patch/rows.json` `immediates` (`addiu rt, $zero, imm` before `button_create(parent, x, y, w, h-on-stack)`: a1 x, a3 w), applied
  by `tools/pod.py patch_rows`, all checked against stock. 20 words for the pages above; the shared builder `0x526a3c`'s (the stock album page, `allmusic_page`, Songs) are the `NAV_H` group of `rows.json`.
- Titles: `tools/mod_lists.py` `PAGES`, recipe `navtitle` on `folder_page`, `localclass_page`, `allmusic_page`, `playerjumpinfo_page`,
  `playlist_page`.
- Assets: `tools/mod_ipodrows.py` `NAVBAR_UI_EDITS` (stock rectangles asserted).
- Tests: `test/pod/rows.py` (every `rows.json` word) and `test/pod/navbars.py` (the stock pages' builders byte-identical to main's).

## Small titles

Every page with a large heading (Songs and its lists incl. Recently Added, Artists, Genres, Composers, Folders, Radio, Podcasts' Shows / Downloads / Subscriptions / Saved) shows the navbar's small title by one rule, `pod_title_gone(off, head)` (`patch/common.c`): once the scroll offset reaches `SG_COLLAPSE` (46); a page whose heading is a header's name passes its threshold (a playlist `PH_COLLAPSE` 204, a podcast show `hdr->collapse`). `pod_title_set` shows or hides the label. The large title is `SG_TITLE_X` 12, `SG_TITLE_W` 296 wide, 32 px, on every page. The small title runs from `NAV_TITLE_X` 58 to the leftmost button and is always cut with an ellipsis (`az_fit`), never hidden for width. Each page adds its own conditions (select mode, empty list, no scroll events).

## Glass navbars on our pages

Scope: **only the M1+ Music pages** (menu, Settings and its card pages (the fade stays hidden there), Main Menu, Shuffle, Extras, Albums, Artists, Playlists, Cover Flow's
bar) and the album page's own controls (`album-page.md`). Stock pages keep main's title bars on main's slots: the shared `return` / `back_to_player` images, the
navbar styles and every stock ui / style / image file and builder are byte-identical to main's build (`test/pod/navbars.py`, digests in `test/navbars-stock.sha256`).

Look: an **opaque bar**, a **glass Back disc** (`ah_nav_back`, 42 px, x 8 .. 50, y 4 .. 46: an `img_btn_style` 44 x 50 button at x 7), the **title from x 58**, the right-hand
actions as **one glass capsule on main's slots**, a soft fade under the bar. Nothing but page assets and per-widget images (`tools/pod_ui.py` `navbar`, `nav_fade`;
`tools/mod_icons.py` `glass_piece`, `capsule_piece`, `NAV_VIEW_POS`, `AH_NAV_PIECES`).

| page | buttons (window x; 46 wide, Now Playing 60) |
|---|---|
| Albums | Cover Flow 168 (left cap), grid / list toggle 214 (middle), Now Playing 260 (right cap `ah_nav_play`) |
| Playlists | "..." 168 (left cap), toggle 214 (middle), Now Playing 260 |
| Songs | Search 122 (left cap), Sort 168 and Select 214 (middles), Now Playing 260: a capsule of four, glass 131 .. 311 (`docs/modules/songs.md`); the title (small, shown when the large one has scrolled away) ends at 122. The other lists on that page (Favourites ..., a playlist) have no Sort: Search 168 (left cap), Select 214, Now Playing 260, the title ends at 168 |
| Songs, a genre's songs (class `0xff09`) | no Search, no Sort: Select 214 (left cap `pod_nav_selectl`, set at run time), Now Playing 260 (right cap): a capsule of two, glass 223 .. 311 (the stock builder leaves Search out for this class); the title ends at 214 |
| Artists | Artist / Album Artist switch 214 (left cap), Now Playing 260 |
| Radio (`m1plus_radio`), station lists | Search 168 (left cap `pod_nav_search`, moved from 214 at run time), grid / list toggle 214 (middle, `pod_nav_grid` / `pod_nav_list`), Now Playing 260 (right cap); other levels: Search 214, Now Playing 260; the search page's results: toggle 214 as the left cap (`pod_nav_gridl` / `pod_nav_listl`) and Now Playing (`docs/modules/radio.md`) |
| Extras (`m1plus_extras`) | Settings 214 (left cap `pod_nav_settings`, Lucide `sliders-horizontal`; opens the Settings page), Now Playing 260 (right cap): glass 223 .. 311; the title ends at 214. Settings > Extras and the other pages have no button |
| Genres, Composers (the Artists page on another class) | the switch is hidden (`visible=false` and `sensitive=false`) and Now Playing, which the asset builds as the capsule's right cap, is set at run time to the glass disc `ah_nav_np` (`_down` pressed), as on every page with no toggle; the title ends at 214 |
| Cover Flow | main page and a composer's page: Now Playing disc `ah_nav_np` at 260 (glass 269 .. 311). An artist page with songs: the capsule Songs (`btn_songs`, Lucide `list`, left cap, x 214) \| Now Playing (`ah_nav_play` set at run time), glass 223 .. 311, the Artists page's shape |
| menu, Settings, sub-pages | Now Playing disc |
| album page (ours) | glass controls as window children: Back disc, Select (left cap `pod_nav_selectl`) \| Now Playing (right cap `ah_nav_play`); select mode swaps in all / none, Add, Delete, Cancel (`album-page.md`) |

**Capsule on the real slots.** Every image is cut to the button it sits in (46 / 46 / 60 px, 42 high), centred by `img_btn_style`: slices of ONE capsule (glass x 177 .. 311 for three pieces,
radius 21), so adjacent pieces abut exactly (tested: the three glue into the capsule byte for byte) and the glass ends 21 px right of Now Playing's glyph column 290. The Songs page's capsule starts at the 122 slot (180 px, glass 131 .. 311, Search | Sort | Select | Now Playing): the same left cap, middles and right cap (a pane's straight parts and ends do not depend on its width), tested to glue byte for byte (`test/pod/glassbtn.py`). Select mode swaps Back's glyph for `ah_nav_close` (a 42 px disc with an x) and hides the capsule.
The 46 px buttons declare `dirty_rect_tolerance=7`: their centred 60 px icons extend seven pixels beyond the touch rectangle. Stock's child painter (`0x674690`, tolerance at widget `+0x36`) and invalidation expand by this value. Without it, a narrow repaint can cull the preceding button and erase its overhang, leaving a black vertical seam. `test/pod/navpaint.py` reproduces this with stock child culling and BGR565 icon painting, then checks the built assets in both Albums modes and pressed/rest states. Device appearance remains unverified.
**Pressed.** A lone disc is the lighter glass. A capsule piece keeps the rest glass (the capsule stays one pane, no lit block with square ends) with a **round highlight** on its glyph: a white disc of 36 px at 14 % (`NAV_PRESS_D`, `NAV_PRESS_ALPHA`), concentric with the cap ends (every glyph is 21 px from a cap's edge), 3 px of glass above and below, inside its own button (`test/pod/glassbtn.py`).
**Even spacing.** Main's slots are 46 apart but Now Playing's 60 px button puts its glyph 53 right of the last slot's (stock's 290), so every slot's glass and glyph is drawn `NAV_SHIFT` (7 px) right of its button: its image is 60 wide, centred on the 46 px button (AWTK centres an icon at its own size), the content in its right 46 columns. Glyph columns 152 / 198 / 244 / 290, 46 apart; the buttons (the touch) stay on main's slots. A left cap's glass starts 21 px left of its glyph (177 = 198 - 21); the Artists capsule starts at 223. The album page's stock-built search and multi-select take the same shift (198, 244).

**The fade.** Nothing is darkened at rest (scroll offset 0; test `navbars.py`, alpha <= 8 over each page's first content): `nb_fade.png` 320 x 20, black, alpha 255 (1 - t)^3.6 (<= 8 from row 12: a text page's first row has its ink from row 15, a switch from row 12). The cover pages (Albums grid / list, Playlists: covers from row 10 / 4) build the fade **hidden** and `al_fade` / `pl_fade` (`patch/albums.c`, `patch/playlists.c`, from the scroll view's EVT_SCROLL they already hold and after a mode switch) show it only while `yoffset > 0`; visible only, it stays insensitive; no `img_nb_fade` = nothing happens (hidden). Preview: `tools/preview_fade.py`. An insensitive, unclickable `img_nb_fade` at (0, 50) right
after the list on every Pod page with a list under the bar (not Cover Flow). No blur, no paint code. **Home instance** (device bug V2.1oAB: a dark band across the covers):
`home.c` hides the navbar but not the fade, so `minibar_start` (`docs/modules/minibar.md`) hides and desensitises `img_nb_fade` with it; `home.c` is untouched.

Device-only checks: the disc and capsule positions, the fade over real rows (rest and scrolled), the Home instance without the band, a tap on every piece, the pressed pieces.
