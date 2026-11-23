# Mini player

**Sources:** `patch/minibar.c`, `patch/minibar.h`, `tools/pod_ui.py` (`minibar()` in
`ui/m1plus_menu.bin`), `tools/pod_blur.py` (blur model), `MB_*` in `offsets.inc`,
`tools/mod_icons.py` (`glass_image`, `pil_glyph`).
The Home menu's floating card shows cover, title, artist, play/pause and next. The normal menu
keeps its navbar and has no mini player. Window and widget events plus one page timer drive the bar;
no stock hook. The look follows Apple Music's floating dark mini player.

## Layout

The window is 450 px tall. Geometry is card-local unless noted.

| Part | Geometry |
|---|---|
| pill `pod_minibar` | 304 x 56 at window (8, 384), radius 28; 10 px (`HOME_PAD`) from the window bottom, ending exactly where the list does (y 440) |
| cover | 36 px at (14, 10), corner radius 5 |
| text | x 60..190; title 17 px white (y 7..29), artist 16 px `#D0D0D0` (y 29..49) |
| play / pause | 48 x 56 target at x 194; pause 22 px tall, play 19 x 22 |
| next | 48 x 56 target at x 245; glyph 30 x 17 |

- The pill is a view that is hidden and insensitive in the asset.
- **Glass.** `pod_mb_card` is a stock `button` the size of the pill whose look is the `bg_image`
  `mb_glass` (pressed `mb_glass_down`) in every state. It is the tap target that opens Now Playing
  and the widget whose `EVT_AFTER_PAINT` draws the cover. The images come from
  `mod_icons.glass_image` (shared with the lock screen's card and the More sheet), and
  `test/pod/assets.py` pins both PNGs to the generator. A dark translucent fill, a 1 px rim light
  and a faint inner highlight line. Not tinted by the album.
- **Content behind the pill.** The list is not shortened: `pod_listview` stays 430 px and the pill
  floats over its bottom rows. A trailing spacer row `pod_pad` (`MB_PAD` 64 px, hidden in the asset)
  is made visible while the bar shows, so the last row can scroll to 8 px above the pill.
  `menu_arrange` keeps it the last child and adds its height to `virtual_h`; a relayout recomputes
  the same value.
- **Cover** corners are rounded in the bitmap's alpha (`m1_corner_fill`), so they show the pill in
  any state.
- `pod_mb_title` / `pod_mb_artist` are `hscroll_label`s that never scroll (their parent is never
  focused) and take no touch. Contrast behind the glass over pure white: title 7.4:1, artist 4.8:1;
  the test asks 7:1 and 4.5:1.
- `pod_mb_play` / `pod_mb_pause` (one shows) and `pod_mb_next` are `img_btn_style` buttons with bare
  white glyphs (pressed 55 % white) drawn by `tools/mod_icons.py`, not rescaled at paint time.
- **Title weight:** Apple's title is bold, but a second Latin-only font would draw blanks for CJK,
  kana, Hangul and Thai titles ([fonts](fonts.md): no per-glyph fallback). Title and artist differ by
  colour and size instead.
- Hit testing (demo's own `widget_find_target`): each control is reached at its centre and 14 px
  from its top and bottom; title, cover and corners fall to the card; the pause button takes play's
  place only while playing; a hidden bar takes none.

## Backdrop blur

The glass is translucent, so rows scrolling behind it would show through sharp. The payload blurs
what is under the pill in the card's own `EVT_BEFORE_PAINT`, reading and writing the lcd's drawing
buffer directly. `mb_blur_t` and its functions (`patch/minibar.h`) are one implementation; the lock
screen's mini bar ([lockscreen](lockscreen.md)) uses the same routine with its own plane and the
same guards. `tools/pod_blur.py` is the bit-exact model and `test/pod/minibar.py` runs the compiled
code against it.

- **Algorithm:** fixed point, no allocation per frame. The pill's 304 x 56 RGB565 rectangle is
  reduced 2 x 2 into a packed plane (17 KB, allocated once at start and freed with the page),
  blurred with two 4-tap box passes along rows and two along columns, darkened by 1/8 and written
  back, only inside the pill's rounded shape. The rounding matters: without it the 5-bit red and
  blue fell behind the 6-bit green.
- **Guards, checked at every call:** the lcd's begin word (only the 565 memory lcd is accepted), a
  non-null aligned buffer, a lcd size, pitch and even x origin that fit, and the pill wholly on
  screen. A mismatch turns the blur off for the page and leaves the glass over sharp rows. Any other
  lcd type gets no blur, and a 5551 panel would never run it.
- **Switch:** the SD file `/mnt/mmc/m1plus-noblur` turns it off at start. No memory for the plane,
  or a refused `widget_on`, leaves it off too.
- **Dirty rectangles:** AWTK repaints a dirty rectangle from the window down, so the rows are
  fresh only when the clip covers the whole pill. A partial frame is not blurred (a blur across the
  clip edge would show a seam); `mb.fix` makes the next tick invalidate the whole pill. Everything
  the payload changes inside the pill invalidates the whole pill (labels, cover, glyph, a press on
  a button). `mb_on_scroll` on the scroll view's `EVT_SCROLL` does the same while scrolling, and
  pointer events on the scroll view cover a row's press under the pill. A rare partial repaint from
  stock code shows sharp rows for one frame; the tick repairs it within 500 ms.

## Data and timer

`minibar_start(win)` is called by `home_menu_opened` for the Home instance, after the menu is laid
out. It also hides and desensitises `img_nb_fade` (the navbar fade would float over the Recently
Played shelf as a dark band, since the Home instance hides the navbar but not the fade). It looks up
the widgets, registers its events and arms a one-shot `MB_FIRST_MS` (120 ms). It shows and decodes
nothing, so the menu's first paint at boot is unchanged.

- **Timer:** `mb_first` arms the repeating `mb_tick` (500 ms lit, 1000 ms dark). It runs while the
  window is in front or only a dialog covers it (`mb_live`: the Control Center shows the bar under
  its panel, so a skip from page 2 shows at once). After `EVT_WINDOW_TO_BG` the next tick ends it
  when the top window is not a dialog (read on the tick: the event can come before the new window
  is the top one); `EVT_WINDOW_TO_FG` re-arms the one-shot if none runs, `EVT_DESTROY` removes it and
  frees the cover.
- **`mb_work`:** if nothing is queued (`cc_playing()` is NULL) the bar is hidden and the list is
  430 px again. Otherwise the bar shows and the list is 366 px. Labels and cover are redone only
  when the track changes (a hash of path, title, file name and cue start). The play / pause glyph
  follows `mclGetPlayStatus() == 2` and is swapped only when that changes.
- **Cover** is decoded on the timer, never in paint (paint only blits the resident 36 x 36 bitmap).
  Order: the album's Cover Flow cache file; else the `/tmp` picture demo wrote for the playing
  track (demo writes it a little after the track changes, so for `MB_SETTLE` ticks the file's hash
  is read again); else the stock placeholder disc, else flat grey.
- **Server track:** the cover is the server's file, the one Now Playing draws (`sba_rec_cover`),
  never the library's album cache file. While it is fetched the card shows the placeholder disc and
  `mb_art_settle` keeps asking ([subsonic](subsonic.md)).
- **Touch:** the card opens Now Playing; play / pause calls `playpause_quick_click()` and rereads
  the glyph; next calls `next_quick_click(e, 0)` with the click's own event (stock ignores a click
  within 1 s of the last one) and then `mb_work`.
- **Recording and the shelf:** `mb_work` calls `recent_note(track)` ([recent](recent.md)) before the
  labels. When the album changed it records it in `/mnt/mmc/.m1plus/recently-played` and refreshes
  the Recently Played shelf at the foot of the list. The spacer follows the shelf; both add to
  `virtual_h`. While dark the timer records album changes and defers visual work.

## Radio mode

Radio plays through hciplayer and never touches stock's play queue, so `mb_work` asks the engine
first (`mb_radio`, [radio](radio.md)). The bar shows the station while `rd_running()` and in Error
or Stopped after a session, unless a local song is really playing or paused. Stopped counts only
while the engine owns the bar (`rd_owns_bar`: set when a station starts, cleared when a local track
starts); Idle, and Stopped after a local track, use the local logic.

| | Connecting | Playing | Paused | Error | Stopped |
|---|---|---|---|---|---|
| Title | station name ("Radio" without one) | track title when split ICY metadata, else station name | station name | same | same |
| Second line | Connecting… | artist when split, else ICY text, else Live | Paused | Can't play: <error> | Stopped |
| Glyph | stop | stop | play | play | play |
| Button does | `rd_stop` | `rd_stop` | `rd_resume` | `rd_play` (retry) | `rd_play` |

- A station has no pause: the pause button shows a Stop square and stops. Paused is reached only
  from outside (hardware key, unplugged headphones, an output switch).
- Next is greyed (`mb_next_off`, `#6E6E6E`) and insensitive (no station skipping). The card tap
  opens radio Now Playing in every state.
- Cover: the station's cached logo (`rd_logo_file`; the logo worker starts when it is missing), else
  the radio glyph on Now Playing's card grey, else the stock disc.

## Stock calls relied on

| Function | Use |
|---|---|
| `playpause_quick_click()` | the same entry as the lock screen, Now Playing and the hardware key; it checks the play type, toggles pause and toasts for a non-song list itself |
| `next_quick_click(e, flag)` | reads `e->time` and does nothing within 1000 ms of the last click; `flag` != 0 only sets refresh flags |
| `mclGetPlayStatus()` | 2 = playing, 3 = paused |

Addresses: the `FUNCTIONS` table in `tools/pod.py`.

## Failure behaviour

Every failure leaves the plain menu. A missing widget, a refused `widget_on` or no timer: the bar is
never shown and the list is not moved. No bitmap: the bar shows without a cover. A cover that does
not decode: the placeholder, else grey. Nothing is shown at boot unless a track is queued, and then
only after the one-shot.
