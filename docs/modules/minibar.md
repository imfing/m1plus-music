# Mini player

The Home menu's floating card shows cover, title, artist, play/pause and next. The normal
menu keeps its navbar and has no mini player. Window/widget events and one page timer drive
the bar; it adds no stock hook.

Sources: `patch/minibar.c`, `tools/pod_ui.py` (`minibar()` in `ui/m1plus_menu.bin`) and `MB_*`
in `offsets.inc`. Tests check the shared geometry: `test/pod/minibar.py`. Preview:
`tools/preview.py` (`minibar_page`). The visual reference is Apple Music's floating dark mini player.

## Layout (window y; the window is 450 px; `tools/pod_ui.py` MB_*, `patch/offsets.inc` MB_*)

| part | geometry (card-local unless noted) | Apple's proportion (h = 56) |
|---|---|---|
| pill `pod_minibar` | 304 x 56 at window (8, 384), radius 28; 8 px from the sides, 10 px (HOME_PAD) from the window bottom, ending exactly where the list does (y 440) | full pill, radius h / 2 |
| cover | 36 px, at (14, 10), corner radius 5, centred vertically | 0.62 h, left inset 0.33 h |
| text | x 60..190 (130 px; 10 px after the cover, ends 4 px before the play target); title 17 px white y 7..29, artist 16 px `#D0D0D0` y 29..49 | 0.18 h after the cover |
| play / pause | 48 x 56 target at x 194 (centre 218); glyph: pause 22 px tall, play 19 x 22 | pause 0.40 h |
| next | 48 x 56 target at x 245 (centre 269, 35 px from the right end); glyph 30 x 17 | 0.53 x 0.30 h; centres 0.92 h apart, 0.62 h from the end |

- The pill `pod_minibar` is a view that is **hidden and insensitive in the asset**.
- **Glass.** `pod_mb_card` is a stock `button` the size of the pill whose whole look is `bg_image` `mb_glass` (pressed `mb_glass_down`) in every state, no fill, border or
  radius of its own; it is the tap target that opens Now Playing and the widget whose own `EVT_AFTER_PAINT` draws the cover. The images are generated
  (`tools/mod_icons.py glass_image(w, h, r, pressed, fill, top_only)`, shared with the lock screen's card (`docs/modules/lockscreen.md`) and, with `top_only` (top corners only), Now Playing's More sheet (`docs/modules/playmore.md` "Glass"); the pill is `GLASS` = 304, 56, 28 and
  `test/pod/assets.py` pins both PNGs to the generator byte for byte; deterministic PIL, 8x supersampled, committed like the other `np_*` PNGs, installed with them: 2.2 KB each):
  304 x 56 straight-alpha RGBA, a dark translucent fill (`#2D2D2F` at the top to `#232325` at the bottom, alpha 0.82; pressed `#3A3A3C` to
  `#303032`, 0.86), a 1 px rim light (white 30 % along the top arc fading to 8 % at the bottom row; pressed 40 % to 14 %) and a faint inner highlight line
  one pixel inside the top edge (7 % fading out by mid height). Not tinted by the album. `test/awtk_fill.py` draws the committed image with demo's own
  `canvas_draw_image_ex` on a bgr565 framebuffer: every pixel is the straight-alpha blend over what is under it within one 565 step (16,423 translucent
  pixels), nothing outside. The earlier flat pill (style `bg_color` + `round_radius` 28 + `border_color`) was checked the same way and works too (the stock
  `canvas_fill_rounded_rect_ex` / `canvas_stroke_rounded_rect_ex`, anti-aliased, the stroke full strength on straight edges and fainter on arcs); the image
  replaced it because it gives the sheen and the rim light.
- **Content behind the pill.** The list is no longer shortened: `pod_listview` stays 430 px (y 10..440) and the translucent pill floats over its bottom rows.
  A trailing **spacer row `pod_pad`** (a plain `view`, `MB_PAD` = 64 px high, the last child of `pod_scrollview`, hidden and insensitive in the asset) is the
  padding: `minibar.c mb_pad` makes it visible while the bar shows (visible only, it stays insensitive: it never takes a tap), so the list can scroll until
  the last row ends `MB_GAP` (8) above the pill (440 - 64 = 376). The stock layouter keeps it: `children_layouter_list_view` (`0x60b12c..`) puts every visible
  child at the running y and `virtual_h` is the sum of the children's own heights, so a relayout recomputes the same value. `menu_arrange` (patch/menu.c)
  parks the spacer right after the shown rows, keeps it the last child (`widget_restack`) and adds its height to `virtual_h` when `widget_get_visible` says it
  is shown; `mb_pad` also sets `virtual_h` at once and keeps `yoffset` inside the new range when the bar goes. `test/pod/pulldown.py` section 6 runs demo's own
  relayout under Unicorn (shown, `menu_arrange` again, repeated relayouts, hidden) for four saved menus; `test/pod/minibar.py` checks the hit tests: the pill takes the
  touch over a row under it, the row just above it is reached. A menu of 8 rows (416 px; the default menu is 6 rows, 312 px, and does not scroll) scrolls 48 px with the bar up.
- Cover: four `MB_ART_R` px corners rounded **in the bitmap's alpha** (`pod_corner_fill`, the table of Now Playing's corners), so they show the pill in any state.
- `pod_mb_title` / `pod_mb_artist`: `hscroll_label`s (`ellipses`, `only_parent_focus`: their parent is never focused, so they never scroll;
  `sensitive=false`), Inter Medium (the one font; see Fonts). **Contrast, worst case behind the glass**: a white row label right under the translucent fill
  (the glass over pure white is about `#555555`): the white title keeps 7.4:1, the artist (`#D0D0D0`) 4.8:1 (`test/pod/minibar.py` asks for 7:1 and 4.5:1 over every text pixel
  of both images); over black they have 15:1+ and 9:1+.
- `pod_mb_play` / `pod_mb_pause` (one shows, the other is hidden and insensitive) and `pod_mb_next`: stock `button`s, `img_btn_style`, bare white
  glyphs `mb_play`, `mb_pause`, `mb_next` and `_down` (55 % white), drawn by `tools/mod_icons.py` (`pil_glyph`, the shapes of the `np_*` transport
  glyphs at the bar's sizes, `MB_PLAY_INK`, `MB_PAUSE_H`, `MB_SKIP_H/W`; the play triangle is as tall as the pause bars) and installed with the `np_*`
  images (32 / 34 x 24 px canvases, centred in the button). Not rescaled at paint time.
- **Fonts.** The title would read best bold (Apple's is), but the UI font is the single merged `default.ttf` (Inter Medium for Latin/Greek/Cyrillic, Source Han
  for CJK): AWTK takes a style's `font_name` from a second file and has no per-glyph fallback, so a second, Latin-only SemiBold subset would draw blanks for
  every CJK, kana, Hangul and Thai title; a SemiBold that covers them is another 9 MB the rootfs does not have. Not done. Title and artist are told
  apart by colour (white vs `#D0D0D0`) and size (17 / 16 px).
- Hit testing (`test/pod/minibar.py`, demo's own `widget_find_target`): each control is reached at its centre and 14 px from its top and bottom; the
  title, cover, corners and the gap before play fall to the card; the pause button takes play's place only while playing; a hidden bar takes none.

## Backdrop blur (experimental)

Shared code: `mb_blur_t` and `mb_blur_alloc` / `mb_blur_enable` / `mb_blur_paint` / `mb_blur_free` (`patch/minibar.h`) are the one implementation; the lock screen's mini bar ([lock screen](lockscreen.md)) uses the same routine with its own plane and the same guards and `m1plus-noblur`. The cover is shared the same way (`mb_art_t`, `mb_art_*`).

The glass is translucent, so the rows scrolling behind it show through sharp. The payload blurs what is under the pill in the card's own
`EVT_BEFORE_PAINT` (`0x11f`: `widget_paint` dispatches it right after `canvas_translate` to the widget and before the background, `0x66dd98`; the glass image is painted by the
background step, after it) by reading and writing the lcd's drawing buffer directly. `tools/pod_blur.py` is the bit-exact model; `test/pod/minibar.py`
runs the compiled code against it.

- **Algorithm** (fixed point, no allocation per frame): the pill's rectangle (304 x 56 RGB565 pixels at the canvas origin) is reduced 2 x 2 into a 152 x 28 plane
  of packed words (the three channel sums in 10-bit fields at bits 20 / 10 / 0: four taps of at most 252 never carry), blurred with two 4-tap box passes along the rows
  and two along the columns (running sums, replicated edges, one rounded shift and one mask per pass handle all three channels at once; the rounding matters: without it the
  5-bit red and blue fell behind the 6-bit green, a green cast, found by the flat-grey test), darkened by 1/8 and written back 2 x 2 (a 32-bit store of two pixels per row),
  only inside the pill (a per-half-row first block from the arc, one pixel of margin: the glass image's anti-aliased edge covers the border and the rounded ends are
  never touched). The plane (`MB_HW` x `MB_HH` words, 17 KB) is `calloc`ed once at start and freed with the page. Cost: **619k instructions for one full pill under Unicorn**
  (about 0.6 ms on the 1.2 GHz core at an IPC of 0.8; unmeasured on the device), per frame in which the pill repaints (a scroll, a glyph swap, a press).
- **Pins** (`patch/offsets.inc`, every one proved in `test/pod/minibar.py` by running demo's own code or by its instruction word): `canvas_t` ox / oy at 0 / 4
  (`canvas_translate` `0x6434d4`), the clip left / top / right / bottom (inclusive) at `0x10..0x1c` (`canvas_get_clip_rect` `0x643718`), its lcd at `0x30` (`canvas_get_width`
  `0x64352c`); `lcd_t`: `begin_frame` at `+0` (`lcd_begin_frame` `0x657b28`), width / height at `0xb0` / `0xb4` (`lcd_get_width` `0x658484`), line length at `0x120`
  (`set_line_length` `0x695034`), the drawing buffer at `0x110` (`lcd_mem_set_fb` `0x695d9c`; the double-buffered create gives the offline one to it and keeps the online one at
  `0x114`). The 565 memory lcd is recognised by its `begin_frame` word `0x695cb0` (what its init `0x695dc8`, reached by `lcd_mem_bgr565_init`, stores at `+0`); every
  other lcd type fails that word and gets no blur: that includes the `lcd_mem_special` one `lcd_linux_fb_create` makes for a 16 bit frame buffer with a 1 bit alpha
  (`bgra5551`, `0x639f34`) and the 24 / 32 bit ones. **Which lcd the device really has is unknown** (`docs/modules/screenshot.md`: the format the panel reports is unverified): on a
  5551 panel the blur simply never runs.
- **Guards, at every call**: the begin word, a non-null 4-byte aligned buffer, the lcd at least as big as the pill and at most 2048 x 2048, a pitch of at least 2 x width, at most 8192
  and a multiple of 4, an even x origin and the pill wholly on the screen. A mismatch clears `mb.blur` for the page (no blur, the glass over sharp rows: exactly the commit before). An
  SD file `/mnt/mmc/m1plus-noblur` turns it off at start; no memory for the plane, or a refused `widget_on` of any of its ten handlers, leave it off too.
- **Dirty rectangles.** AWTK repaints a dirty rectangle from the window down, so inside the clip the rows are freshly painted when the pill's before-paint runs. The blur is
  done only when the clip covers the whole pill; a partial frame (a row's press highlight that reaches under the pill) is not blurred, because the pixels outside the clip
  are the last frame's blurred ones and a blur across that edge would show a seam. Instead `mb.fix` makes the next tick invalidate the whole pill. Everything the payload
  changes inside the pill invalidates the whole pill, not the widget's rectangle: `mb_labels`, `mb_cover`, `mb_glyph`; and a press, release or abort on the play, pause or next button
  (`mb_on_touch`, three events each) does the same, since a button's press state repaints only its own rectangle. Not covered: any other partial repaint of the pill by stock code
  shows the glass over sharp rows for one frame (the tick repairs it within 500 ms).
- **Scrolling** (review fix). The list's dirty rectangle is the scroll view's own (window y 10..440, x 0..309 beside the scroll bar); the pill is x 8..311, so the list alone never covers
  it, and with the pill at y 386 it also ended below the list. Two fixes: the pill is at y 384 and ends at 440 exactly where the list does (10 px below, as the top margin; `MB_PAD`
  is 64), and `mb_on_scroll` on the scroll view's `EVT_SCROLL` (0x152) invalidates the whole pill while the bar and the blur are up, so the frame's dirty rectangle (the bounding
  box of both) always contains it. Evidence: the scroll view's yoffset setter `0x60ff08` builds `offset_change_event_init(e, 0x152, ..)` and `widget_dispatch`es it
  (`0x60ff38..0x60ff74`); it is called by `scroll_view_scroll_delta_to` (the drag, `0x610b9c`), `scroll_view_set_offset` (flings and `scroll_to` animations, `0x6116b4`) and the
  property setter (`0x611dfc`), so every way the offset changes. The handler does not touch the offset: no loop. `test/pod/minibar.py` replays a scroll frame (clip = bounding box
  of the list's rectangle in screen coordinates and the pill): without the handler the clip is partial (not blurred: the old behaviour), with it the blur runs, bit for bit, for a
  list 310 or 320 px wide.
- **Row press under the pill.** A row's highlight repaints only the row's rectangle. The scroll view also gets the pointer down / up / abort (`mb_on_touch`, the same handler as the buttons),
  which invalidates the pill in the same frame, so the frame is row + pill and is blurred. A row wholly under the pill takes no touch (the pill does). Frames that can still be sharp:
  a partial repaint from stock code not listed here (a toast, a dialog's close, the status bar over it does not reach the pill); the next tick (500 ms at most) invalidates the pill once.
- **Not verified on a device**: the lcd type and the double-buffer behaviour (the model is the AWTK sources and the disassembly), the cost, and how the blur looks (the model drives the
  preview's third panel and the crops under `out/peek`). `docs/modules/device-checks.md` lists what to look at; `m1plus-noblur` is the escape hatch.

## Recording and the shelf

`mb_work` also calls `recent_note(track)` (`patch/recent.c`, `docs/modules/recent.md`) before the labels: it records the playing album in `/mnt/mmc/.m1plus/recently-played` when the album changed (a key compare in RAM first, nothing else on a tick that changed nothing) and, when it did, `recent_refresh()` shows
the new album on the Recently Played shelf at the foot of the list. The shelf follows the last shown row and the spacer `pod_pad` follows the shelf (the list's last child); both add to `virtual_h` (`mb_pad` adds and removes `MB_PAD` itself, `menu_arrange` / `menu_shelf` add the shelf's own
height: 234, 434 or 634), the default menu with both is 416 + 634 + 64 = 1114 px in the 430 px list (six albums); scrolled to the end the shelf's last line ends `MB_GAP` above the pill, as the last row did.

## Data and timer

`minibar_start(win)` is called by `home_menu_opened` (patch/home.c) for the Home instance, after `hm_fill_window` laid the list out (it is not
called when that found no navbar or list).
- **Fade.** First it hides and desensitises `img_nb_fade` (the fade under the glass navbar, `navbar.md`; at y 50 it would float over the Recently Played shelf as a dark band with a sharp top edge, since `hm_fill_window` hides the navbar but not it). Test: `test/pod/minibar.py`.

- **Start** looks up the seven bar widgets and the list (the scroll bar is optional: a short custom menu has none), registers `EVT_DESTROY`,
  `EVT_WINDOW_TO_BG`, `EVT_WINDOW_TO_FG` on the window, `EVT_AFTER_PAINT` and `EVT_CLICK` on the card, `EVT_CLICK` on the three buttons, and
  arms a **one-shot `MB_FIRST_MS` (120 ms)**. It shows, moves and decodes nothing: the menu's first paint at boot (inside the boot
  guard's 5 s window) is exactly today's.
- **Timer**: `mb_first` arms the repeating `mb_tick` (500 ms lit, 1000 ms dark) and does the first work. Only while the window is
  in front: `EVT_WINDOW_TO_BG` removes the timer (Now Playing, any page, the pull-down or a dialog above), `EVT_WINDOW_TO_FG` arms the
  one-shot again (the state is current a moment after Back), `EVT_DESTROY` removes it and frees the cover bitmap. A window started over
  one that never said it was gone replaces its state.
- **`mb_work`**: `cc_playing()` (the play queue row at `mclGetPlayPos`, the lock screen's "queued" test) is NULL: the bar is hidden
  (`visible=false` + `sensitive=false`) and the list is 430 px again (a list scrolled past its new end is brought back: `yoffset` clamped to
  `virtual_h - h`). A track is queued: the bar shows and the list is 366 px. **Only when the track changes** (a hash of path, title, file
  name and cue start) the labels (title, else the file name; artist) and the cover are redone. The play / pause button follows
  `mclGetPlayStatus() == 2` and is swapped only when that changes.
- **Cover** (decoded on the timer, never in paint: paint only `canvas_draw_image`s the resident 36 x 36 bitmap): 1. the album's Cover Flow cache
  file (`cc_url`, the album key as the album page's tint uses it), 2. for a track without a cache file the `/tmp` picture demo wrote for the
  playing track (`np_cover_file` / `COVER_SRC`, as Now Playing reads it) - demo writes it a little after the track changes, so for `MB_SETTLE`
  (3) ticks the file's hash (`np_file_key`) is read again and the cover redone if it changed (a file being made, `COVER_SRC` 1, is skipped
  and not counted), 3. the stock placeholder disc `p_default`, else flat grey. Box filter (`cc_box`).
- **Touch**: the card -> `pod_on_player` (`on_backtoplayer_onclick`, the menu's Now Playing row); play / pause -> `playpause_quick_click()` then the
  glyph is read again; next -> `next_quick_click(e, 0)` (the click's own event: stock reads its time and ignores a click within 1 s of the last
  one, the same debounce the lock screen has) then `mb_work`.

## Radio mode

Radio plays through hciplayer and never touches stock's play queue, so `mb_work` asks the engine first (`mb_radio`, `patch/radio.h`). The bar shows the station while `rd_running()` (Connecting, Playing, Paused) and in Error or Stopped after a session unless a local song is really playing or paused (status 3, or 2 with `mclGetHciplayerStatus`). Stopped counts only while the engine owns the bar (`rd_owns_bar`: set when a station starts, cleared when a local track starts through the `mclStartPlayer` hook); Idle, and Stopped after a local track, use the local logic. Look unchanged; content:

| | Connecting | Playing | Paused | Error | Stopped |
|---|---|---|---|---|---|
| Title | station name ("Radio" without one) | same | same | same | same |
| Second line | Connecting… | Live | Paused | Can't play: <error> | Stopped |
| Glyph | stop (`mb_stop`) | stop | play | play | play |
| Play / pause button | `rd_stop` | `rd_stop` | `rd_resume` (`mclSetResume`) | `rd_play` of the same station (retry) | `rd_play` of the same station |

A station has no pause here: the pause button shows the Stop square (`mb_stop` / `mb_stop_down`, 18 px ink in the 32 px canvas, set on all three styles by `mb_pause_look`) and stops; after the stop the state is Stopped and the bar keeps the station with a play glyph until a local track starts. Paused is only reached from outside (hardware key, unplugged headphones, an output switch); the play glyph resumes it. A local track gets `mb_pause` / `mb_pause_down` back.

| Next | visible but greyed (`mb_next_off`, `NP_OFF` #6E6E6E, set on the normal / over / pressed styles by `mb_next_look`) and insensitive in every state (no station skipping); white `mb_next` / `mb_next_down` and sensitive again when the bar returns to a track | | | |
| Card tap | radio Now Playing (`rn_open`) in every state | | | |

Cover: the station's cached logo (`rd_logo_file`; the logo worker is started when it is missing and the cover redone when the file appears), else the radio glyph on Now Playing's card grey, else the stock disc. Key: (station address, state, error text) redoes the labels; the cover only follows the station. After a tap the glyph follows stock's status (3 / 2) at once; the engine's tick moves the state.

## Pinned stock addresses (`tools/pod.py` FUNCTIONS, checked against `.dynsym`)

| function | address | evidence |
|---|---|---|
| `playpause_quick_click()` | `0x4cd150` | the lock screen's `btn_play` handler `0x53f964` (bound by name, `strcmp(name, "btn_play")` `0x53f3d4` -> `0x53f3f4`: `jalr playpause_quick_click` `0x53f984`, then its refresh `0x53f520`), Now Playing's button (`0x53b6e4`) and the hardware key (`on_wm_keyup_fun` `0x4cda78`). It checks the play type and network, calls `play_pause_music` `0x4e43b4` (`mclSetMute`, `mclSetPause` / `mclSetResume`, `notifyPlayStatus`, `dmrNotifyPlayStatus`, `sendBtHeadsetPlayStatus`) and toasts "not a song list / file" itself; returns 1 |
| `next_quick_click(e, flag)` | `0x4ccf00` | the lock screen's `btn_next` handler `0x53f900` (`move a0, a1; jalr next_quick_click` `0x53f928`, `a1 = 0`), Now Playing `show_player_face+0x6b8` (`0x53c16c`, `a1 = 0`), `on_wm_keyup_fun`. Reads `e->time` (u64 at `+8`: `lw a1, 8(a0); lw a2, 0xc(a0)` `0x4ccf2c`) against the global `0xa05a40` and returns without doing anything when within 1000 ms; else `next_music` `0x4e4338` (queue check, `mclNextSong`). `flag` != 0 only sets the refresh flags `0xa05a63` / `0xa05a60` |
| `mclGetPlayStatus()` | `0x5d3640` | `lw v0, status` (`0xa10000 - 0x541c`); the lock screen's refresh `0x53f82c` shows `btn_imgpause1_style` for 2 and `btn_imgplay1_style` for anything else; `mclSetPause` stores 3 (`0x5d2658`), `mclSetResume` 2 (`0x5d26c8`) |

`widget_set_style`, `value_set_uint32`, `bitmap_*`, `canvas_draw_image`, `timer_add` / `timer_remove` and the rest were pinned already (Now
Playing, Albums). **Verified in emulation only** (`test/pod/minibar.py` mocks the three stock calls and checks the call, its arguments and what
the bar does after it): that `mclGetPlayStatus` 2 means playing in every source (local files, DLNA, AirPlay, Tidal) and that a click handler's
`e` carries the time stock expects need the device (`docs/modules/device-checks.md`).

## Failure behaviour (every one is the plain menu)

A missing widget (any of the seven, the list or its scroll view), a refused `widget_on`, no timer, a refused later timer:
the bar is never shown and the list is not moved (`mb_stop` clears the state; a handler that was registered finds no window of ours). No
bitmap: the bar still shows (title, artist, buttons) without a cover, paint draws nothing. A cover that
does not decode: the placeholder, else grey. Nothing is shown at boot unless a track is queued, and then only after the one-shot.

The page timer runs every 500 ms lit and 1000 ms dark; it records album changes while dark, defers visual work, and refreshes the shelf on the first lit tick (up to one second after waking).
