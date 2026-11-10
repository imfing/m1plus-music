# Lyrics page

Now Playing shows synchronized lyrics with a highlighted current line, staggered spring
scrolling, drag-to-browse, tap-to-seek and intro dots. Latin lines use 30 px Inter Bold;
other scripts use the default font. Stock still loads and parses local and online lyrics.

**Sources:** `patch/lyrics.c`, `patch/lyrics.h`, `patch/nowplaying.c`,
`tools/mod_nowplaying.py`, `tools/mod_font.py`, `tools/font_inter.py`.
**Validation:** `test/pod/lyrics.py`, `LYRICS_PINS` in `tools/pod.py`,
`tools/preview_lyrics.py` (pass `--shot PATH` for the background screenshot;
`--mode scrim` and `--mode intro` select those previews).
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

A row's text is read with `pod_text_utf8` (`patch/common.c`) into `LY_BUF` (256) bytes: a longer line is cut at a character, and at most `LY_LINES_MAX` rows of it are drawn anyway.
Stock `widget_get_text_utf8` ignores its size for a wide text and wrote a ~350 byte line over this stack buffer (the player rebooted; see [payload](payload.md)), so the payload never calls it.

## Layout and appearance

- The current line's top is anchored at 85 px (0.35 of the 244 px view).
  Labels have up to three wrapped rows, 34 px per row and a 12 px gap.
- Row height follows AWTK's font size plus `spacer`: 30 + 4 px. The page breaks lines itself
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
  (or a text without spaces, CJK) by code point, at most three rows; the text beyond them is cut.
  A space at a break becomes the `\n`, else the `\n` is inserted (`ly_wrapped`; the label text
  is at most `LY_BUF` + 1 bytes). Widths add up (no kerning): one measure of the line, one of a
  space, and for a wrapped line one per word (per code point of a long word), at most the three
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
The upcoming lines sit one 46 px pitch lower. The dots fill by thirds, breathe over 2.4 seconds
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
