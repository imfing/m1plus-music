# Now Playing's More menu (`patch/playmore.c`, `tools/mod_lists.py`, `test/pod/playmore.py`)

The sheet Now Playing's "..." button opens is the stock `dialog/playmore_dialog` (`ui/dialog/playmore_dialog.bin`, a 320 x 350 dialog at
y 130: `list_view` `playmore_listview` > `scroll_view` `playmore_scrollview` > `list_item` rows `listitem0..6`, the scroll bar
`scroll_bar_m`). Stock order and rows: A-B repeat (0, a switch `img_switch`), Playback speed (1, the badges `img_1x`, `img_1_25x`,
`img_1_5x`, `img_2x` and `label1_msg`), Add to playlist (2), Online search (3), Look up album (4), Look up artist (5), Delete song (6).
The Playback speed row's icon (`image1`, stock `p_multiple`, used by no other widget) is the Lucide `gauge`, the glyph of the Podcasts sheet's speed row (`tools/mod_icons.py` `DIALOG_GLYPHS`, 28 px like the other rows).
M1+ Music makes it an iOS style bottom sheet with two pages.

Preview, both pages over Now Playing with the dim (each page with its own glass; the zoomed top edges are checked with `tools/peek.py crop`): `uv run python -I tools/preview_playmore.py work/mod-release out/preview/playmore.png` (not tracked).

## What the user sees

- **A bottom sheet.** The sheet is as high as its page's rows x 50: **300 px on both pages (6 rows each)**, always on the bottom of the screen (y 180, bottom 480; an episode's page 1, 2 rows, is 100 px at y 380). The page above it is
  dimmed (the AWTK dialog highlighter, below). A tap above the sheet closes it (stock behaviour, see "Positioning"); a tap on the sheet does not.
- **Page 1** (when it opens, every time): Look up album (`listitem4`), Look up artist (5), Add to playlist (2), **Cassette Mode** (`pod_tape`, below), **Vinyl Mode** (`pod_vinyl`, below) and **More** (`pod_more`: the Extras
  ellipsis glyph, the label, the grey chevron-right `right_arrow`, ink at x 288..298).
- **Page 1 of a podcast episode** (the playing record's path passes `pc_is_path`, tested at open; `pm.ep`): row set 2, only **Go to Podcasts** (`pod_goep`, the `pod_ic_podcasts` Lucide `podcast` glyph, no chevron, no hairline as the first row,
  label translated in 13 languages) and **More**. Look up album, Look up artist, Add to playlist, Cassette Mode and Vinyl Mode are `visible=false` + `sensitive=false`, parked under the sheet and stacked last like every hidden row
  (`pm_arrange` takes the shown rows from `pm_page[set]`, set = `pm_set()`: 0 music page 1, 1 More page, 2 episode page 1). The sheet is **2 rows, 100 px** (y 380) with the Podcasts page's own `pc_sheet2` glass (320 x 100, same pane,
  no new image): height, glass, dialog / list_view / scroll_view / bar sizes and virtual_h all follow the row count as for the other pages. More opens the usual page 2; its back header returns to the episode's page 1. A tap on Go to Podcasts calls
  `podcasts_go()` (patch/podcasts.c, docs/modules/podcasts.md "Pages and controls") and closes the sheet once the page is up (a page that will not open leaves the sheet). Songs: the sheet is unchanged. Test: `test/pod/playmore.py` section 7c.
- **Page 2** (a tap on More): a header row **< More** (`pod_back`: the stock chevron-left `return`, the label "More"; a tap returns to page 1), then
  Playback speed (1), **Sleep Timer** (`pod_sleep`, below), A-B repeat (0), **Cover & Lyrics** (`pod_art`, below) and **Delete song** (6, its label red `#FF5A4F`). The stock rows keep their own handlers (speed badges,
  A-B switch, delete, add to playlist): the payload moves rows, it replaces no behaviour but two (Look up album and Look up artist, next items) and adds four (Cassette Mode, Vinyl Mode, Cover & Lyrics, Sleep Timer). Switching only swaps which
  rows are visible and sensitive and sets the sheet to the page's height and glass picture (both pages 300 px `pm_sheet6`, an episode's page 1 `pc_sheet2`; below); there is no slide.
- **Cover & Lyrics** (`pod_art`, page 2, between A-B repeat and Delete: the glyph `pod_ic_art`, a custom Lucide-style SVG `assets/icons/custom/cover-lyrics.svg` (a picture over two text lines), the label "Cover & Lyrics", translated in all 13 languages, no chevron). It is not for a server (Subsonic) track, streamed or downloaded (`pm.srv`, `sba_rec_track` at open; the row is dimmed and insensitive as with no Wi-Fi, and `onlineart_open` refuses it too). It needs the Wi-Fi, which is looked at **each time page 2 is shown** (`pm_arrange`, stock's `get_wifisignal() > 0`, the Podcasts guard's test): connected, the row is as the others; not connected, the row is drawn at opacity 100 of 255 (`widget_set_opacity`, the Main Menu's English row is dimmed the same way) and insensitive, so a tap does nothing. A tap opens our page (`patch/onlineart.c` `onlineart_open`, `docs/modules/onlineart.md`) first and closes the sheet once it is up (`pm_on_art`, which looks at the Wi-Fi again); a page that cannot open leaves the sheet as it was.
- **Sleep Timer** (`pod_sleep`, page 2, under Playback speed: the Lucide `moon` glyph `pod_ic_sleep` (`assets/icons/lucide/svg/moon.svg`, `POD_ROWS['Sleep Timer']`, accent tinted like the other `pod_ic_*`), the label, the grey chevron-right `pod_sleep_chev` (ink at x 288..298) as the row opens a page). The label is the **stock key `powerm_sleep`** (`pod_i18n.STOCK`), the text of the Power page's own row, so it follows Language and reads as the page it opens (stock's Italian is "Sveglia", Thai "เวลาพักหน้าจอ"; the test checks that it fits before the chevron in all 13 languages). A tap (`pm_on_sleep`) brings the Power page to the front **first** and closes the sheet once it is up; a page that cannot open leaves the sheet as it was. The page (window `powermanager_page`, the asset's root name; `systemset/powermanager_page` is only the navigator path) has no `single_instance` property, so stock's `navigator_to` stacks a new window every time, and the top-right Now Playing button (`on_powermanagertoplayer_onclick`: stores the selected time, then `navigator_switch_to_with_context("playing_page")`) restacks the player and leaves the Power window under it. A tap therefore first looks for an opened `powermanager_page` in the window manager (`pod_open_stock`, `patch/common.c`, which calls `pod_restack_window`, the helper the Settings tiles and the Settings Display row use too (Wi-Fi and Bluetooth are opened afresh), [pulldown.md](pulldown.md), [settings.md](settings.md)): found, it is restacked with stock's `window_manager_switch_to(wm, top window, page, 0)` (nothing closed); not found, closing, or the restack refused, it is stock's plain `navigator_to("systemset/powermanager_page")` (a refused open leaves the sheet). However often the cycle Sleep Timer, Now Playing button, Sleep Timer is repeated, the stack holds one Power window. A restacked page runs no init, but it does not show stale values: stock's restack delivers `EVT_WINDOW_TO_FG` (0x12d) to it, also with no animation (`window_manager_switch_to` @0x67891c, the dispatch at 0x6789e8..0x6789f4), and the page's init registered a handler for that event (`widget_on(win, 0x12d, 0x4a9b2c)` at 0x4a9d34..0x4a9d50) whose body calls the page's refresh (`0x4a9924`: switch image, selector visibility, hour and minute from the timer words `0xa05a90` seconds / `0xa05a94` on/off; the init calls the same function at 0x4a9d80). The restacked page therefore refreshes itself and `pm_on_sleep` calls nothing. The mechanism is pinned in `PLAYMORE_PINS` (the dispatch of 0x12d in the restack, the init's registration of 0x4a9b2c, the handler's call of 0x4a9924), so a different stock binary fails the build instead of silently showing old values; no hook, no binary edit. It shows with or without Wi-Fi, and on page 2 of an episode too (More leads to the same page 2). No timer logic of ours: the Power page's Sleep Timer switch and hour / minute selectors are stock; Back there (`btn_return0`, stock handler @0x4a91d0) saves the picker values and calls `navigator_back` (closes the top window); with Now Playing directly below the page that returns to Now Playing (the test models this stack order; it does not run the stock Back handler). The pile-up needs the page's top-right Now Playing button and then reopening Sleep Timer; a plain Back closes the page.
- **Cassette Mode** (`pod_tape`, page 1, between Add to playlist and Vinyl Mode: the cassette glyph `pod_ic_tape`, the label "Cassette Mode", translated in all 13 languages, no chevron). A tap opens the landscape
  cassette page over Now Playing (`patch/tape.c` `tape_open`, `docs/modules/tape.md`) **first** and closes the sheet once the page is up (`pm_on_tape`: `window_close` of a window under the
  top one, as Settings > Developer > Open Shanling Home closes the menu under the Settings page); a page that cannot open leaves the sheet as it was.
- **Vinyl Mode** (`pod_vinyl`, page 1, under Cassette Mode: the turntable glyph `pod_ic_vinyl`, a custom Lucide-style SVG `assets/icons/custom/turntable.svg`, the label "Vinyl Mode" in all 13 languages,
  no chevron). The same order as Cassette Mode: `pm_on_vinyl` opens the turntable page (`patch/vinyl.c` `vinyl_open`, `docs/modules/vinyl.md`) first and closes the sheet once it is
  up; a page that cannot open leaves the sheet as it was.
- **Look up album opens our album page** (`pm_on_lookup_album`, a click handler on `listitem4` bound after the stock init, so the emitter runs it first;
  RET_STOP (11, `emitter_dispatch` @0x6f450c) keeps the stock one, RET_OK lets it run). The stock handler (0x4795cc) opened `playerjumpinfo_page`. Ours reads
  the playing track (`cc_playing`) and looks its album up in the library Albums list (`cc_find_album`: `loadAlbumList(0xf003)`, album name compared
  ASCII case-insensitively as the list groups, the Unknown Album row never matches) BEFORE changing anything; found: it does what the stock Look up artist
  (0x4793ac) does: `window_close` the sheet, `navigator_close("albuminfo_page")` if one is in the stack (0x4d2118), set `songerinfoflag` (0xa04737),
  `cc_open_album(NULL, 0, row)` (the Albums grid's sequence, class 0xf003 | row << 16). With the flag set, a track tap or Play on that page unwinds
  to the Now Playing already in the stack and closes it before opening the new one (no second Now Playing, `docs/modules/album-page.md`), and the
  page's navbar has no multi-select and no Now Playing button; Back returns to Now Playing. Stock clears the flag only on `album_page`'s window event
  (0x522c64), so a destroy handler on the new page clears it (restoring the byte as it was: a Look up artist page below keeps it set); the window it was set for is
  remembered, so an older page's late destroy never clears a newer page's flag. Nothing playing, a track without an album tag, or an album the list lacks:
  RET_OK, nothing closed or opened, the stock handler runs (its message / page). A page window that cannot be found or watched after the open: the flag is not left set.
- **Look up artist opens our Albums page scoped to the artist** (`pm_on_lookup_artist`, a click handler on `listitem5` bound after the stock init like Look up album's; stock `0x4793ac` opened the stock `album_page`). Same hook, no new pin or hook. The artist is the playing track's `REC_ARTIST`; it is looked up (ASCII case-insensitive, the Unknown Artist row never matches) in the list the Artists page shows, `loadLocalClassList(0xf004)`, which follows Settings' Artist / Album Artist switch (`artist_type`): the track record carries no album artist, so in Album Artist mode a track whose artist is not an album artist (a featured artist) is not found and the stock handler runs; that was chosen over changing the setting or guessing. The row goes into a one-row carrier deque and `albums_open_artist(carrier, 0, CLASS_ARTISTS)` (`docs/modules/artists.md`) opens the page, as a tap on the Artists page does (`coverflow_artist` on the same artist if that returns -1, the Albums window not opening; -2, an asset that is not ours, is a failure); the carrier is freed (the page copies the row). The page opens FIRST (as Cassette Mode) and the sheet closes after it is up, so every failure leaves the sheet and the stock handler (RET_OK): nothing playing, no artist tag, Unknown artist, artist not in the list, Cover Flow already open (`coverflow_artist` refuses a second open: e.g. Now Playing reached through an artist page), the page failing to open. On success: `songerinfoflag` set (an album page above the artist page unwinds to the Now Playing in the stack on a track tap), released by the page's destroy through `pm_on_album_gone` (the page is the new top window, compared with the top before the open; a window that cannot be watched leaves the flag as it was), an `albuminfo_page` in the stack is closed, RET_STOP. Back from the Albums page returns to Now Playing (an album page or Cover Flow opened from it returns to it first); the flag is released when the Albums page is destroyed.
- **Online search** (3) is never shown (`visible=false` and `sensitive=false`).
- **Playback speed's row.** The stock label box is 60 px wide (the badges start at x 122), so "Multiple Speed" was cut. The label now reads **Speed**
  (our key `Speed`, set by the payload after the stock binder wrote `player_multiple`; 13 translations, `tools/pod_i18n.py`), its box is 96 px
  (x 48..144), and the four badges moved right (x 148, 188, 228, 268, 36 px each, 40 px apart, the last ends at 304 of the 310 px row).
  The note under it (`label1_msg`, 14 px; stock "*Affecting only files below 48khz", 138 px wide and cut in most languages) reads **Files below 48 kHz only**
  (our key, 13 translations) in a 262 px box: it fits in all 13 languages (test), so it stays visible.
- The stock layouter keeps a row's own height: the asset has Look up artist (5) and Delete (6) at 60 px (stock: 370 px of rows in the 350 px sheet, so
  the stock list scrolled by 20 px). The payload resizes every row to `PM_ROW_H` 50, so both pages are exact and nothing scrolls.
- The red: `#FF5A4F` (a label in a pressed row keeps its normal state). Its ratios are in "Glass" below. The Delete label stays red. With an accent, the rows' stock glyphs (`player_albuminfo`, `player_songerinfo`, `p_add`, `p_multiple`, `p_abrepeat`, and the Delete glyph `p_delete`) are tinted at decode by exact name (`ACCENT_GLYPH_STOCK`, `docs/modules/accent.md`), like our rows' `pod_ic_*`.

## Glass

The sheet is the glass of the Home mini player bar and the lock screen's card (`docs/modules/minibar.md` "Glass", `docs/modules/lockscreen.md`), like an iOS bottom sheet.

- **The image.** Two pictures, each its own height (a taller picture cropped for the shorter page showed a wrong top edge on the device): `pm_sheet6.png` (`assets/icons/png/`, 320 x 300: both pages, 6 rows each) and `pm_sheet.png` (320 x 250, no page uses it now: it is only `pod_glass`'s picture in the asset, a failed start's look), both installed by `mod_nowplaying` with the `np_*` images. Each =
  `mod_icons.glass_image(320, h, 18, fill=GLASS_SHEET_FILL, top_only=True)` (`GLASS_SHEET`, `GLASS_SHEET6`): the same pane (dark gradient `#2A2A2C` to `#1E1E20`, 1 px rim light, faint inner
  line) with **only the top corners rounded** (r 18; `top_only` draws the shape past the foot, so the bottom corners and the foot are opaque and carry no rim
  line: the sheet sits on the screen edge; the mini bar and the card are unchanged byte for byte). **Fill alpha 0.88** (bar 0.82, card 0.76): the labels, the
  grey badges and the chevrons sit straight on it, and the Now Playing page (title, stars, transport glyphs) only ghosts through. It is not the dialog's `bg_image` (a style cannot change with the page): the dialog is transparent (`bg_color` `#00000000`, `border` `none`, the stock `#666666` top line gone: the rim is in the image, no radius) and its **first child `pod_glass`** is an insensitive image (320 x 200, `pm_sheet` in the asset, so a failed start keeps the old look) under the list; `pm_arrange` sets its size and picture (`widget_resize`, `image_base_set_image`) for the page. The window event walk now visits `pod_glass` (no handlers) before the list_view; the order of ours after the stock handler is unchanged.
- **Transparent rows, this dialog only.** The list_view and scroll_view `bg_color` `#00000000`; every one of the fourteen rows carries inline styles (no shared style name,
  the global `list_item_style` and every other page untouched, test): `bg_color` transparent in every state but `pressed`, `#FFFFFF10` (6 % white), and `border_color`
  `#FFFFFF22` (13 % white; AWTK blends a 1 px line's alpha like a fill, `test/awtk_fill.py`). The album page's 20 % band (`docs/modules/album-page.md`) would take the
  red under 3:1 (2.14:1 over white-under-the-dim), hence 6 %. Widget names and handlers untouched.
- **What is behind.** The highlighter dims the whole page by 130/255; the glass lies on that. Under the sheet (window rows 250..450) the tint is a tone of at most
  192 under `np_tint` alpha >= 148 (81), 40 after the dim: nearly black; the brightest things are the transport glyphs (off-white, 125 after the dim).
- **Contrast** (worst over each label's box, measured by `test/pod/playmore.py`): glass over black / over white under the dim (125) / over pure white with no dim
  (a stress case the highlighter never shows): white row labels at rest 15.5 / 12.6 / 9.9, pressed 12.8 / 10.3 / 8.2 (floor 7:1 over the first two); red Delete label
  at rest 5.53 / 4.59 / 3.63, pressed 4.66 / 3.75 / 3.01 (floor 4.5:1 at rest over both, pressed 4.5:1 over black and 3:1 over the dimmed white; the red, luminance 0.29, is
  the weak one and sets the alpha: 0.78 gave 4.04); the Speed note `#AAAAAA` 6.93 / 5.68 / 4.46 (floor 4.5:1 over the first two); unselected badges (grey outlines
  by design) 3.55 / 2.90 / 2.27, chevrons 5.06 / 4.20 / 3.32 at rest (floors 3:1 over black, 2.5:1 over the dimmed white).
- **RAM.** The larger image decodes to 320 x 300 x 4 = 384,000 bytes (the card: 384,768, the pill 68 KB), only while the image manager holds it; not a concern. It is drawn 1:1
  by `canvas_draw_image_ex`. A 9-patch (`bg_image_draw_type` patch3 / patch9) is not used: `canvas_draw_image_patch9` is at `0x647d20` but no style value is pinned (as for
  the lock card), and a stretched middle would smear the gradient and rim.
- **Failed start.** The asset keeps its look (as with the dim): the stock seven 50-60 px rows are transparent over a 320 x 200 glass in a 350 px dialog, so
  the rows below the glass lie directly on the dimmed page (legible, not pretty).
- Preview: `tools/preview_playmore.py` draws the `bg_image`, the dim over the whole screen, the hairlines and a pressed Delete row: `out/preview/playmore-glass.png`.

## Positioning (the bottom sheet)

The dialog's coordinates are the screen's (the window manager sits at 0,0 and is 320 x 480; stock 130 + 350 ends at 480). The stock init moves the
dialog to y 130 (`widget_move(dialog, 0, 130)`, `0x479d10`, pinned); `pm_arrange` moves it to `PM_SCREEN_H` minus the page's height (300, or 100 for an episode's page 1; `pm_rows`) = 180 or 380 after the stock init and resizes
it to 320 x that (the list_view's `self_layout` `h=100%` follows). Pins touched: none changed; added read-only pins `0x479ce0` (the stock init binds
`EVT_WINDOW_TO_BG 0x12c` to `0x4789f0`) and `0x478a1c` (that handler's `widget_move(dialog, 0, 130)`), next to the existing `0x478ac8` / `0x478acc`.

- **Tap above closes.** The stock handler `0x478abc` (bound to `EVT_POINTER_UP` by the stock init, kept) compares the pointer's y with `dialog->y` and
  closes when it is smaller. With the sheet at y 230 that is exactly "a tap above the sheet": nothing of ours is involved (the old `pm_on_up`, which
  closed on a tap *below* a top-anchored short sheet, is gone: the sheet touches the bottom edge).
- **Another dialog opens over it** (Delete's confirm): the window manager sends `EVT_WINDOW_TO_BG` and the stock handler `0x4789f0` (on the dialog) moves
  the dialog back to y 130, which would drop the sheet in mid screen. The payload's handler puts the sheet back on the bottom in the same dispatch, before
  any paint, so it has to run after the stock one. **It is bound on the list_view, not on the dialog**: this AWTK's emitter runs the *newest* handler
  first (`emitter_on_with_tag` puts a new one at the head, `0x6f466c` / `0x6f4670`), so a handler bound later on the dialog runs before the stock one
  (V2.1nN did that: the sheet sat mid screen after the confirm). The window event goes through `widget_dispatch_recursive` (`0x678870`), whose
  `widget_foreach` visits a widget and then its children (`0x668ae4` / `0x668af0`, if the visit returned `RET_OK`, which the dialog's emitter
  returns after its last handler, `0x6f45a0`); the list_view is the dialog's first child and `list_view_on_event` returns `RET_OK` for the event
  (`0x60c53c`), so its emitter runs ours right after the stock one. All pinned in `PLAYMORE_PINS`. (The stock init also adds a 200 ms timer, `0x478a48`,
  that moves the dialog to y 130 when `scr_rotateflag` is set: a screen rotation, which this firmware's UI does not do while a dialog is open; not handled.)
- **The dim** is the dialog's own `highlight` property in the asset, `highlight="default(alpha=130)"`: the stock window manager (the function at `0x690100`, its
  `widget_get_prop(dialog, "highlight")` at `0x6901c4`) reads it when the dialog opens and builds the "default" dialog highlighter (registered at tk init, `0x68e8bc`) with `dialog_highlighter_factory`,
  which draws the page under the dialog dimmed by that alpha; no widget is added and no touch is involved (a highlighter paints, it does not hit-test). The
  stock dialogs of this app never set one (their init calls `set_dialog_highlight`, `0x4cd344`, with an empty string), and the highlight has to be in the
  asset: the navigator runs the dialog's init after `window_open_and_close` (`0x4d0158`), too late for the window manager's setup. After a failed start the
  asset's look stays (the dim over the stock menu), as for every look step. **Not verifiable in the emulator (a paint path): check on the device.**

## The hook

`dialog_playmore_dialog_init` `0x479cc4`, pinned prologue `(0x3c1c0059, 0x279ca20c, 0x0399e021)` (`$gp` checked), overwritten with
`j m1plus_playmore_init; nop`; the trampoline resumes at `0x479cd0` (`beqz $a0`). It is called only by the navigator's dialog-init dispatcher
(`0x4d1244` / `0x4d124c`, behind the `strcmp` with `"dialog/playmore_dialog"` `0x749f78`), when the sheet is built; `tools/reach.py` finds it
only behind the navigator cut (`0x4d00c0`), so it never runs at boot or in the main loop. `tools/pod.py` `PLAYMORE_PINS` also pins the dispatcher's
words and the stock handlers' words (above). The stock init (it binds every row and badge through the `widget_foreach` visitor `0x478b44`, sets the
texts, binds the to-background and tap-above handlers, moves the sheet to y 130) runs first and its result is returned; then `pm_start` looks up the dialog's widgets by name and checks the asset is the one it knows (fourteen rows under the scroll_view,
each row's parent, `pod_glass`, the labels), sets the texts (`widget_set_tr_text`: `More` twice, `Speed`, `Files below 48 kHz only`, `Cassette Mode`, `Vinyl Mode`, `Go to Podcasts`, `Cover & Lyrics` and the stock key `powerm_sleep`) and registers twelve
handlers (the More row's, the back header's, the Cassette Mode row's, the Vinyl Mode row's, the Go to Podcasts row's, the Cover & Lyrics row's and the Sleep Timer row's `EVT_CLICK`, Look up album's, Look up artist's and Delete's, the dialog's `EVT_DESTROY` and the list_view's `EVT_WINDOW_TO_BG`). **Everything fallible happens before the
first row moves**; any failure leaves the stock seven rows (`pod_more`, `pod_back`, `pod_tape`, `pod_vinyl`, `pod_goep`, `pod_art` and `pod_sleep` are `visible=false` and `sensitive=false` in the asset, so they do
not show; a text already set stays, and fits the stock label). The state is one `.scratch` struct (handles, `page`), cleared by the destroy handler; each
handler checks that its context is the dialog the state belongs to, so a handler a failed start left behind does nothing.

`pm_arrange` (open, and every page switch): every row `widget_resize(310, 50)` and back to the `normal` state (the row whose click switched the page
is hidden by its own click); the page's rows (6 on page 1 and page 2, 2 on an episode's page 1) `widget_move(0, position x 50)` and shown; the others `widget_move(0, the sheet's height)` (parked under the sheet) and
hidden (`visible=false` **and** `sensitive=false`: a hidden widget would still take touches); the children `widget_restack`ed shown rows first, hidden last
(the stock list_view layouter re-stacks the visible children in child order at every relayout and gives each `y` = the sum of the heights above,
`docs/modules/home-guard.md` "The stock list code under the menu's hand-placed rows", so the order survives it); the dialog, list_view (320),
scroll_view (310) and scroll bar (10 wide) `widget_resize`d to the page's height, the dialog moved to y 480 minus it, `virtual_h` the height, `yoffset` 0, the dialog invalidated before
and after.

## Assets (`tools/mod_lists.py` `edit_playmore`)

`ui/dialog/playmore_dialog.bin` exists in `default`; `build_ui` asserts that
every stock widget keeps its type, name and rectangle (`ADD_EDITS`: only the `pod_more*` / `pod_back*` / `pod_tape*` / `pod_vinyl*` / `pod_art*` widgets are new, and the six speed row widgets of
`PM_SPEED` change their rectangle, asserted from the stock values). The dialog gets `highlight`. `pod_more` and `pod_back` are `list_item`s styled as the Add to
playlist row (`pod_back`: no hairline, it is the first row of its page), appended as the eighth and ninth children: `pod_more_icon` (24 x 24 at 14,13: the
Extras glyph `pod_ic_extras`), `pod_more_label` (`hscroll_label`, `srlabel_item_white_style`, 200 px at x 48, no text in the asset: the payload sets it) and
`pod_more_chev` (13 x 22 at 285,14, `right_arrow`: ink at 288..298); `pod_back_chev` (13 x 22 at 14,14, `return`) and `pod_back_label` (200 px at x 40). `pod_tape` is the same (a `list_item` styled as the Add to playlist row, so with its top hairline), the tenth child: `pod_tape_icon` (24 x 24 at 14,13: the cassette glyph `pod_ic_tape`, a custom Lucide-style SVG `assets/icons/custom/cassette-tape.svg`, listed in `tools/mod_icons.py` `POD_ROWS['Tape']`) and
`pod_tape_label` (200 px at x 48). `pod_art`, the twelfth child, is the same (a top hairline) with `pod_art_icon` (`pod_ic_art`) and `pod_art_label`. `pod_sleep`, the fourteenth, is the same with `pod_sleep_icon` (`pod_ic_sleep`), `pod_sleep_label` and the chevron `pod_sleep_chev` (13 x 22 at 285,14, `right_arrow`). `pod_vinyl`, the eleventh child, is the same with `pod_vinyl_icon` (the turntable glyph `pod_ic_vinyl`, `assets/icons/custom/turntable.svg`) and `pod_vinyl_label`. The pictures are insensitive. Three new row images, `pod_ic_tape`, `pod_ic_vinyl` and `pod_ic_art`. The hairlines follow the new order (Look up album and the back header, the first rows, have none; A-B repeat has one); with
a failed start the stock order shows with those two hairlines and the red label. `scrlabel6` (Delete) takes the red as an inline text colour in every state.

## Findings

- **Delete asks first.** The stock Delete handler (`0x4791f4`, bound to `listitem6`) opens `dialog/confirminfo_dialog` with the text `msg_delsong`
  ("Delete Song?") through `navigator_to_with_context`; only on the dialog's yes (`0xa`) does it call `delete_playqueue_file(0)` and show
  `msg_delsongsuccess` / `msg_delsongfailed`. The call is **modal** (it returns the answer, 0xa yes / 0x14 no) and the handler never reads its ctx (the sheet). The glass
  confirm card is translucent, so the sheet that stayed behind it showed through: **Dialogs over the sheet** (`pm_on_delete`, a click handler on `listitem6` bound after the stock one, so it runs first):
  `window_close` of the sheet, RET_OK, and the stock handler runs on unchanged (delete only on Yes). A No leaves Now Playing without the sheet. The other rows need nothing: stock's Add to playlist closes the
  sheet itself (`window_close` @0x47994c, then `playlist_page`), Speed and A-B open no dialog, Look up album / artist, Cassette Mode and Vinyl Mode close it themselves. The to-background handler (below) stays for any other window opening over the sheet.
- **Sleep timer.** Stock has one: Settings > Power (`systemset/powermanager_page`, `on_powermanagertoplayer_onclick`): the row `listitem_sleep` ("Sleep Timer", `powerm_sleep`, `imgswitch_sleep`: a switch) with an hour / minute text selector (`tselector_hour`, `tselector_min`), the auto-shutdown countdown dialog
  `dialog/dialog_autoshutdown` (`msg_autoshutdown`, shown from `on_wm_idle_status`) and the SyncLink `GetAutoShutdown` / `SetAutoShutdown` messages. The More sheet's **Sleep Timer** row (above) only links to that page. Findings: stock opens it with a plain `navigator_to("systemset/powermanager_page")` (the All System Settings hub's Power case, @0x4ad92c); its init (`systemset_powermanager_page_init` @0x4a9d18) binds the handlers and reads the saved time and sets no `syssetinto_flag` / `playsetinto_flag` and needs nothing from a Settings page, so opening it over Now Playing leaves no settings window in the stack (docs/modules/pulldown.md "Settings tiles and the window stack"); Back stores the time and returns to Now Playing, and its Now Playing button restacks the player (no flag set either way) and leaves the Power window under it, which a later Sleep Timer tap reuses (above).

## Tests (`test/pod/playmore.py`)

The dialog is the built asset as real widget structs under demo's own window code (the `pulldown.py` machine): `widget_move` / `_resize` / `_set_visible` /
`_set_sensitive` / `_restack`, the list_view layouter (`window_manager_check_and_layout`), `widget_find_target` and the pointer path run unmocked, and so do
the stock to-background (`0x4789f0`) and tap-above (`0x478abc`) handlers. The stock init is run as far as its binding goes (the stock visitor per widget, the
two dialog handlers registered as the stock init does, in order), so `m.bound` / `m.reg` hold the stock handlers before the hook runs. Checks: the hook words,
pins and `$gp`; the premise of the dim (the window manager's `highlight` read and the registered `default` highlighter); the stock layout (the 60 px rows,
370 px); page 1 and page 2 order, visibility, sensitivity, stacking, heights, sheet size and y + h = 480; every stock handler unchanged and first in order and
only the six of ours added; hit tests per page (a tap lands on the row drawn there, no touch ever lands on a hidden widget, the badges and A-B are reachable only on
page 2, the page 1 rows only on page 1); More -> page 2, back header -> page 1 through real taps (list_item click -> our handler), relayouts on both pages,
repeated switching; the stock tap handler closing above the sheet and not on it, on both pages; the to-background window event dispatched as demo does it (the tree
walked widget first, then its children; each emitter newest handler first, the words pinned): the stock handler on the dialog, then ours on the
list_view (the sheet back on the bottom, the rows unmoved), and the same handler bound on the dialog leaving the sheet at y 130 (the V2.1nN bug); destroy and reopen (starts on page 1); Look up artist (`coverflow_artist` trapped: match without case, scope, page first then sheet closed, flag set and released by the page's destroy, albuminfo closed, nine fallbacks to the stock handler); stock failure, no dialog, each missing widget, wrong parent, 7, 8
9 or 11 children, each text and each bind failure: the stock menu, nothing moved, leftover handlers inert; the five texts in all 16 tables and their fit in 13
languages (More before its chevron, Speed in 96 px, the note in 262 px, Cassette Mode, Vinyl Mode and Cover & Lyrics in 200 px, Sleep Timer before its chevron); the Sleep Timer row (the navigator modelled as the device keeps it: `navigator_to` always adds a window, the to-player button restacks the player and leaves the Power page under it, `window_manager_switch_to` moves a window to the top: a tap opens `systemset/powermanager_page` then closes the sheet; five cycles Sleep Timer, to-player button, Sleep Timer end with one Power window, restacked and refreshed by its own foreground handler (the mock delivers `EVT_WINDOW_TO_FG` on a successful restack and runs the handler the init bound; our handler's direct call of the refresh is trapped and must not happen), then the sheet closed; Back over the player; a Power window deep in the stack; a refused restack, a closing window and no window manager fall back to `navigator_to`; a refused restack and a refused page leave page 2; no Wi-Fi needed, a stale handler); the Cover & Lyrics row (`onlineart_open` trapped, the page itself is `test/pod/onlineartpage.py`: a tap opens the page then closes the sheet, a page that will not open leaves page 2, the Wi-Fi off dims the row to opacity 100 and takes its touches, looked at again on each visit, a stale handler); the Cassette Mode and Vinyl Mode rows (`tape_open` trapped: the page itself is `test/pod/tape.py`): a tap opens the page and then closes the sheet, a page that will not open leaves the sheet on page 2; both asset themes (stock widgets unchanged but the speed row, highlight, hidden
start, styles, hairlines, the stock chevron images); the glass: `pm_sheet.png` and `pm_sheet6.png` byte for byte vs the generator, each its own height (both pages set `pm_sheet6`), the same top edge, `pod_glass` the first child and its size and picture per page, top corners transparent and the foot opaque, the
dialog / list / rows' inline styles, no other asset uses the image and the shared `list_item_style` is still opaque, and the contrast table of "Glass" with its floors.

## Device check

Open More on Now Playing: the page above the sheet is dimmed (if not, the highlight is not taking effect: the paint path is the one thing the emulator cannot
show) and the sheet is dark glass with rounded top corners, the page ghosting faintly through it, no square corner or black rectangle (the bottom corners
sit on the screen edge); labels, badges and chevrons legible, a pressed row only faintly lighter; six rows on the bottom edge of the screen (Look up album, Look up artist, Add to playlist, Cassette Mode, Vinyl Mode, More with a grey chevron), the top edge of both pages a clean rounded rim; tap above the sheet closes it; tap
More: the sheet shrinks a row (top edge down) and shows "< More", Speed (readable, the four badges tappable, the note under it), AB Repeat and a red Delete Song; tap "< More": page 1; tap Cassette Mode: the cassette page opens over Now Playing and the sheet is gone (`docs/modules/tape.md` has the page's checklist), back (the screw) returns to Now Playing without the sheet; tap
Cover & Lyrics (Wi-Fi on): the page opens and the sheet is gone; with the Wi-Fi off (Settings > Wi-Fi) the row is visibly dim and a tap does nothing; Delete: the sheet closes and "Delete Song?" opens alone on Now Playing (no sheet behind the glass card); on No you are back on Now Playing, on Yes the song is deleted; speed badges and the A-B
switch work; a new language shows the translated texts.
