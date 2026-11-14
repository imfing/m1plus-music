# Lyrics page

Now Playing shows synchronized lyrics with a highlighted current line, staggered spring
scrolling, drag-to-browse, tap-to-seek and intro dots. Latin lines use Inter Bold and
other scripts the default font, at 22, 26 or 30 px (Settings > Now Playing > Lyrics Text Size; Large, 30 px, is the default). Stock still loads and parses local and online lyrics.

**Sources:** `patch/lyrics.c`, `patch/lyrics.h`, `patch/nowplaying.c`,
`tools/mod_nowplaying.py`, `tools/mod_font.py`, `tools/font_inter.py`, `tools/pod_pages.py`; the idle page's second view: [idlelyrics](idlelyrics.md).
**Validation:** `test/pod/lyrics.py`, `LYRICS_PINS` in `tools/pod.py`,
`tools/preview/preview_lyrics.py` (pass `--shot PATH` for the background screenshot;
`--mode scrim` and `--mode intro` select those previews; `--mode size` writes one image a text size, `OUT_small.png`, `OUT_medium.png`, `OUT_large.png`).
Previews use the shared layout model and real fonts; the tests draw the label text the way
stock's wrap does (`stock_rows`, a model of the inspected path).

## Stock integration

Local lyrics are loaded by `mclLoadExLyric` (`0x5d41e4`); online lyrics by
`online_lyricthd` (`0x50a048`) and `online_loadexlyric` (`0x508a00`).
Both build children of `scroll_lrc` with text and an integer `lrc_time` property.
The payload reads those rows and compares their times with `get_playtime()` in seconds.
It does not read the lyric deque, take its mutex or change the stock loaders and timers.

`np_lyrics` is a sensitive, non-slidable `scroll_view` at (28, 44, 264, 244) in
`view_lyrics`. It clips its children. `ly_start` creates 20 reusable labels and a
measurement label, then hides `view_lrc` with both `visible=false` and
`sensitive=false`, and installs the coverage gamma on the `lyrics` font (`tg_apply`, fonts.md "Coverage gamma"). Stock's no-lyrics message stays stock's. Missing widgets or failed
label creation leave the stock list available.

There is no additional hook: `np_start` calls `ly_start`, the 500 ms `np_work`
tick calls `ly_tick`, and `np_stop` calls `ly_stop`. A row signature (count,
first and last handles and times) detects replacement lyrics; at most 400 rows are read.

A row's text is read with `m1_text_utf8` (`patch/common.c`) into `LY_BUF` (256) bytes: a longer line is cut at a character, and at most `LY_LINES_MAX` (6) rows of it are drawn anyway.
Leading blanks are then dropped (`ly_lead`: space, tab, U+00A0, U+2000..U+200B, U+202F, U+3000, U+FEFF); blanks inside and at the end stay. Why: stock's loader keeps everything after the time stamp's `]` (`0x5d3f28`), so a file written `[00:12.34] text` (LRCLIB's form) gave every line a leading space: the first row was indented by a space and the rows the page breaks were not.
Stock `widget_get_text_utf8` ignores its size for a wide text and wrote a ~350 byte line over this stack buffer (the player rebooted; see [payload](payload.md)), so the payload never calls it.

## Layout and appearance

- The current line's top is anchored at 85 px (0.35 of the 244 px view).
  Labels have up to six wrapped rows (`LY_LINES_MAX`), `LYH` px per row and a `LYG` px gap (34 and 12 at Large; see "Text size").
- A line of more than three rows is anchored higher (`ly_anchor`): its top sits where the next
  line's first row still ends 8 px (`LY_ANCHOR_ROOM`) above the view's bottom, but not above
  20 px (`LY_ANCHOR_MIN`): 85 px up to three rows, 54 for four, 20 for five and six (six rows end
  at 224 of 244 and the next line is out of the view). Why: LRC files that put several sentences
  under one time stamp (1.3.2 report, The Lie Eternal from LRCLIB: 11 of 22 lines need four rows,
  one six) lost everything after the third row. `ly.man` counts from the anchored line's own
  anchor: `ly_move` adds the two anchors' difference to the move's distance and `ly_rebase` picks
  the line nearest the 85 px anchor, so nothing jumps in a move or a drag. The layout keeps
  lines up to `LY_OFF_MAX` (976 px, 4 x the view, also the cap of a spring's offset) outside the
  view laid out: the longest move that does not snap, four lines of six rows, is 929 px, and a
  line that was on the screen must stay laid out until its spring has taken it out (with the
  former 400 px the old current line vanished at the start of such a move). With the intro dots a
  first line of six rows starts one pitch (`LYH + LYG`, 46 px at Large) lower and its last row is clipped until the dots go.
- Row height follows AWTK's font size plus `spacer`: 30 + 4 px at Large. The page breaks lines itself
  (`ly_break`) and sets the label's text with explicit `\n`s, and the rows, the label height and the
  breaks come from that one result (cached per line, `ly.brk`). Why: the style sets no margin, so
  stock `widget_get_content_area` (`0x672978`) gives the 264 px label a 260 px content width, and
  stock's wrap helper (`0x62dbb0`, called from label paint `0x62e8a0`) wraps at the first character
  whose row so far, itself and 1 px (`0x62ddf0`) pass that width, except when it is the text's last
  character (`0x62de10`): that stays on the row and the label clips it ("Time is a valuable
  thing", 268 px, lost the end of its `g`). It treats `\n` as a forced break (`0x62dd7c`). Rows
  that fit never reach the overflow check, so the exception never fires and stock's row count
  matches ours. This was chosen over a trailing space (it can hide a word, so stock draws more rows
  than allocated) and over margins or a wider view (the last-character case remains).
- `ly_break`: a line measuring at most `LY_FIT_W` (260, the content width) is one row and left to
  stock (its last character may reach 260, its ink ends before the label's edge). Otherwise greedy
  at spaces with rows at most `LY_ROW_W` (259: stock's check adds 1 px), a word wider than a row
  (or a text without spaces, CJK) by code point, at most six rows; the text beyond them is cut
  and the last row ends in `…` (`LY_MARK`). The last row keeps the mark's width free: what does
  not fit beside it is cut, unless the whole rest of the line fits the row without the mark (one
  more measure, of the rest).
  A space at a break becomes the `\n`, else the `\n` is inserted (`ly_wrapped`; the label text
  is at most `LY_BUF` + 7 bytes). Widths add up (no kerning): one measure of the line, one of a
  space and one of the mark, and for a wrapped line one per word (per code point of a long word), at most the six
  rows' worth, once per line. Each line is measured once and kept, except a measure of 0 for
  non-empty text (any piece): that line stays one row, is not cached, and later page ticks measure
  it again and redo the layout (after the first failed measure a layout measures nothing more; at
  most 20 ticks' layouts, 10 s, per lyrics load can fail, then one row is kept). A label's text is
  set again when its row count changes (a line placed before it was measured had no breaks).
- The measuring label measures only in its resolved style. `widget_use_style` resolves a style
  only in an opened window (stage 3/5). Otherwise it just marks the widget, and
  `widget_measure_text` measures in the old style. The window resolves every widget's style at
  `EVT_WINDOW_WILL_OPEN` (stage 2), which stock dispatches from an idle after
  `playing_page_init`. So `np_start`'s first tick ran before it and measured the lines around
  the playing one in the label's default style, a width too small that stayed cached (1.3.0
  report, Wake Up: "Still knee-deep in the system's shit" was cut after "in the", the '66 line
  lost its last row). Now nothing is measured before stage 2 (that tick's lines are retried
  like a measure of 0). From stage 2 the probe calls `widget_update_style` itself before each
  measure, as stock `label_resize_to_content` does, so a face switch during the open
  animation is measured in the new face.
- `np_lyric_style` selects `lyrics.ttf` (the Inter Bold subset).
  `np_lyric_cjk_style` uses the default font for mixed scripts, unsupported characters
  or malformed UTF-8. AWTK has no per-glyph font fallback.
- Lines are white with opacities 1.0, 0.45, 0.32, 0.24 and 0.18 by distance
  from the current line. A 56 px edge fade applies at both ends of the view.
  While browsing, non-current lines use opacity 0.6 before the edge fade.
- `np_scrim_lyrics.png` is 27% black (alpha 68), with eased 44 px edges.
  Contrast floors over the tested cover tones are 4.5 / 2.3 / 1.8 / 1.55 / 1.4.
  See [Now Playing](nowplaying.md) for the tint and scrim assets.

## Text size

Settings > Now Playing > **Lyrics Text Size** (a value row of its own card, [settings](settings.md); picker `m1plus_lyrsize`: Small / Medium / Large) is saved in `/mnt/data/m1plus/nowplaying-lyrics-size` (`0\n`, `1\n`, `2\n`, written atomically by `ly_size_set`; a missing or invalid file is Large, which is the original 30 px layout; a Settings Files row). `ly_size` reads it.

| Size | Font | Row pitch `LYH` (font + `spacer`) | Gap `LYG` | Intro pad `LYH + LYG` | Styles |
|---|---|---|---|---|---|
| Small | 22 | 25 (3) | 9 | 34 | `np_lyric_style_s`, `np_lyric_cjk_style_s` (both the default font) |
| Medium | 26 | 29 (3) | 10 | 39 | `np_lyric_style_m`, `np_lyric_cjk_style_m` |
| Large | 30 | 34 (4) | 12 | 46 | `np_lyric_style`, `np_lyric_cjk_style` |

- **Face by size.** Large and Medium draw a line of Latin, Greek and Cyrillic in the bold face (`np_lyric_style[_m]` names `lyrics.ttf`). Small has no bold face: `np_lyric_style_s` names no font, like the CJK style, so every line is in the default font (the bold look is too heavy at 22 px). `ly_latin` and `ly.fc` still pick the style per line, and the probe still measures in the chosen style (`LYSTYLE`), so the wrap is measured in the face drawn: the two Small styles are identical, no code path differs. `LYR_BOLD_SIZES` in `tools/mod_nowplaying.py` lists the sizes with the bold face; the preview (`preview_lyrics.sized`, `latin_bold`) follows it.
- **Styles, not a runtime override.** The size reaches the labels as a style pair per size (`LYRIC_SIZE_STYLES`, `LYR_SIZES`, `LYR_GAPS` in `tools/mod_nowplaying.py`; `ly_sizes` in `patch/lyrics.c` is the same table). Every `widget_use_style` call (the labels, the measuring label) takes the name from `LYSTYLE(face)`, so the probe measures in the size it is drawn in; no new stock address or pin is used. The row pitch is each style's font plus `spacer`, which AWTK's label paint uses (pins above), and `LYH` is that sum, so layout and paint agree.
- **What follows the size:** the row pitch, the gap, the intro pad and the dot centring, the anchor rule (`ly_anchor`), the edge fade's row centres, the tap map and the label heights. Not changed: the 85 px anchor (`LY_ANCHOR`), the 6-row cap, `LY_ANCHOR_MIN`/`LY_ANCHOR_ROOM`, `LY_OFF_MAX` (976, a bound that the smaller pitches stay under: a move of `LY_SNAP_LINES` six-row lines is at most 929 px at Large), the pool of 20 labels (at the smallest pitch, 34 px with the gap, a view holds at most 8 one-row lines), the 259 / 260 px row widths (width is not a size). At 22 px six rows end at 52 + 150 = 202 of 244, so all six show with the next line's first row.
- **When it is read.** `ly_start` reads the file when the page starts. `ly_refresh` (called from `np_on_foreground`, one file read) takes a changed size when Now Playing is in front again, e.g. after Settings: it resets every label's style, height and place and the probe's style, clears the signature so the next tick drops the break cache (`ly.ht`, `ly.brk`) like new lyrics and lays the lines out again from the current line. No label is made again. A size that did not change does nothing.
- **Vertical margins.** Stock's label paint draws a row of a wrapped label only while `y + font size` is at most the content area's bottom (`0x62eb4c`); the first row is at the top margin and the content area is the label less `margin_top` / `margin_bottom` (default 2 each, `0x672978`). A label of n rows is n x (font + spacer) high, so its last row is drawn only when the two margins are at most the spacer. Large (spacer 4) fits the default 2 + 2; Medium and Small (spacer 3) set `margin_top` and `margin_bottom` to 1 (`lyr_vmargin` in `tools/mod_nowplaying.py`). Why: with the default margins every wrapped line at Medium and Small lost its last row (device screenshot of the idle Lyrics page; also the earlier "dreams" report at Small). The side margins stay 2 (the 260 px content width); a one-row label is painted by another path and does not move.

- Tests: `test/pod/lyrics.py` `size_tests` (the paint rule above for 2..6 rows at each size, the six styles, `ly_size` / `ly_size_set`, each size's layout, anchors, taps, intro pad, refresh), `size_setting_tests` (the row, the picker, the file). `preview_lyrics.py --mode size`. Not verified without a device: AWTK's real wrap and baseline at 22 and 26 px, the gap's look, the refresh on return from Settings.

## A second view (the idle lyrics page)

The engine is one static state, bound to one view at a time. `ly_start(win)` binds it to Now Playing's `np_lyrics` (264 x 244, `LY_VIEW_H`); the [idle lyrics page](idlelyrics.md) takes it with `ly_retarget(win, box, h)` and gives it back with `ly_release()`. **Design: a rebind, not two live instances.** Only one view is ever in front, so the engine is stopped on one target and started on the other: `ly_retarget` makes the 20 labels, the probe and the three dots in the page's box first (a refused label returns -1 with the engine untouched), then parks Now Playing's widget pointers (`lyp`: window, box, probe, pool, dots, height, anchor, size; the widgets stay alive, hidden) and restarts the engine's state on the new box, keeping `src` (Now Playing's `scroll_lrc`) and the stock list `view`. `ly_release` stops the timers, puts the parked widgets back, hides them and forgets every cached fact about them (line, style, rows, opacity, visibility), so the next tick lays the lines out from the stock rows as for new lyrics. Chosen over two instances because the state is large (several KB of scratch plus the pool) and the lines, the clock and the timers would all need an owner; the rebind adds about 130 lines and one 200 byte struct and leaves Now Playing's own code path unchanged. `ly_release` is idempotent and also runs at the top of `ly_refresh` (Now Playing's foreground), so an engine bound to a closing page is never ticked by Now Playing; `ly_stop` (Now Playing's end) clears the parked widgets too.

- **What follows the view's height:** `ly.vh` (`LYVH`: `LY_VIEW_H` for Now Playing, 372 for the page), the anchor `ly.anc` (`LYANC`: `LY_ANCHOR` 85 = 0.35 x 244; 0.35 x 372 = 130), `ly_anchor`'s limit (`LYVH - LY_ANCHOR_ROOM - ...`), `ly_edge`'s bottom, the layout's visible and laid-out windows, `ly_rebase`, and the offset bound `LYOFF` = 4 x the height (`LY_OFF_MAX` 976 for Now Playing; 1488 on the page, still inside a `short`). A stopped engine reads as Now Playing's numbers. Not changed: the 20 label pool (at the smallest pitch a 372 px view holds about 12 one-row lines of which about 11 are visible, inside the pool's window round the anchor), the width, the row widths.
- **Touch.** The pointer listeners carry their view as context and ignore events when it is not the engine's current one, so Now Playing's listeners (kept registered while parked) do nothing and are never added twice. `ly.noseek` (set by `ly_retarget`) makes a tap on a line seek nothing; dragging and the 3 s return are unchanged.
- **Source rows.** The page reads Now Playing's `scroll_lrc` while another window covers it; Now Playing's own `np_tick` does no work then (`np.fg`), so the page's timer calls `ly_tick` itself. Stock's rebuild of the rows under another window: [idlelyrics](idlelyrics.md) "Stock facts".
- Tests: `test/pod/lyrics.py` `retarget_tests` (the take-over and return, the 372 px layout and edge fade at the three sizes, a six-row line's anchor, taps and drags, a touch for the parked view, release / refresh / stop, every refusal), `test/pod/idlelyrics.py`.

## Motion and touch

The motion is inspired by amll-dev/applemusic-like-lyrics (anchor, falloff and staggered
spring). It uses integer arithmetic without blur. A 640 ms damped spring (zeta 0.72,
wn 12/s, 65-entry table) has a 6 px overshoot cap. Lines start in sequence with delays
of 50, 97, 141, 182 ms and so on. One 40 ms timer moves visible labels while needed.
Moves of more than four lines and refused timers snap into place.

Pointer listeners on `np_lyrics` return `RET_OK`, leaving sideways swipes to the slide view.
Labels are insensitive. A vertical move over 10 px starts browsing; after 3 seconds without
touches (checked by the page tick), the lines return to the current position.
The highlight continues following playback during browsing.

A tap seeks with stock `seek_time(seconds)` at `0x4e0544`; it is ignored while stopped
or within the first 200 ms of an animation. A 1 second hold lets the player catch up.
The stock seek can block the UI thread for up to 2 seconds. Stock row taps only toggled
the lyric display flag; those rows are hidden and receive no touches.

## Intro dots

Three 10 px image dots appear at the anchor when the first line starts at 4 seconds or later.
The upcoming lines sit one pitch (`LYH + LYG`, 46 px at Large) lower; the dots keep their 18 px spacing and are centred on the anchor row's `LYH`. The dots fill by thirds, breathe over 2.4 seconds
and fade over the final 500 ms; the lines then spring into the anchor.
An 80 ms timer runs only while the dots show and playback is active.

`ly_clock` interpolates whole-second playback readings with the monotonic clock, bounded
within the reported second. Pauses freeze it; seeks reset it. Dots move with the lines during
a drag and are insensitive. Dots between lyric lines are not enabled.

## Pins and safety

`LYRICS_PINS` checks the row properties, stock timer reads, row-click flag accesses,
font fallback and label pitch instructions. Key evidence includes `lrc_time` at
`0x751c80`, its write at `0x5384bc`, timer reads at `0x538654` / `0x5386a8`,
row-click words at `0x536e3c` / `0x536e50`, pitch instructions at
`0x62e9f8` / `0x62ea04` / `0x62ea24` and font fallback at `0x650ebc`. Style resolution:
`widget_use_style`'s opened-window test at `0x66aac0`, `widget_update_style`'s no-op test
at `0x6667a8`, and the WILL_OPEN stage store and recursive style update at `0x676bb8` /
`0x676bc8` / `0x676bd4`.
Called functions are also checked against `FUNCTIONS`; consult `tools/pod.py` for the full set.

All work runs on the UI thread from page timers and listeners. No stock words are written,
no stock widget is renamed or removed, and no thread or lock is added.
Startup failures preserve the stock list; animation failures snap.
Destroy removes timers and ignores stray events.

## Validation

The emulation tests cover assets and pins, lifecycle failures, line following, font selection,
wrapping, spring and opacity models, drag and seek gestures, intro timing, pause/resume,
song changes and instruction cost. They verify unchanged hooks and stock widget names.
Asset checks include scrim alpha, dot shape, font coverage and contrast.

Device checks remain necessary for actual AWTK wrapping, font loading and baseline placement,
clip and opacity behavior, local and online timing, seek latency, gesture interaction,
animation smoothness and the lighter scrim over bright covers. Emulation and previews do
not establish those results. Blur, translation, per-word fill and a larger current line
are not implemented.
