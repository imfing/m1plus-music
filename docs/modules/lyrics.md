# Lyrics page

**Sources:** `patch/lyrics.c`, `patch/lyrics.h`, `patch/nowplaying.c`, `tools/mod_nowplaying.py`,
`tools/mod_font.py`, `tools/font_inter.py`, `tools/pod_pages.py`. `LYRICS_PINS` in `tools/pod.py`.

Now Playing shows synchronized lyrics with a highlighted current line, staggered spring scrolling,
drag-to-browse, tap-to-seek and intro dots. Latin lines use Inter Bold and other scripts the
default font. Stock still loads and parses local and online lyrics. No hook of its own: `np_start`
calls `ly_start`, the 500 ms `np_work` tick calls `ly_tick`, `np_stop` calls `ly_stop`.

## Stock integration

- Stock builds children of `scroll_lrc` with text and an integer `lrc_time` property (local:
  `mclLoadExLyric`; online: `online_lyricthd`, `online_loadexlyric`). The payload reads those rows
  and compares their times with `get_playtime()`. It never reads the lyric deque, takes its mutex
  or changes the stock loaders and timers. At most 400 rows are read; a row signature (count, first
  and last handles and times; no text) detects replacement lyrics. Replacement that can keep the
  signature (Save / Replace Lyrics rebuilds the rows with the same handles, count and times) is
  announced by `ly_reload`: the mark waits until stock clears `force_refreshflag` (its rebuild
  ran), then the next tick reads the rows as new lyrics. The mark survives `ly_release` and
  `ly_retarget`; `ly_stop` and `ly_start` drop it.
- `np_lyrics` is a sensitive, non-slidable, clipping `scroll_view` at (28, 44, 264, 292) in
  `view_lyrics`. `ly_start` creates 20 reusable labels and a measurement label, hides `view_lrc`
  (`visible=false`, `sensitive=false`) and installs the coverage gamma on the `lyrics` font
  ([fonts](fonts.md)). Stock's no-lyrics message stays stock's. Missing widgets or a failed label leave stock's list in
  place.
- Row text is read with `m1_text_utf8` into `LY_BUF` (256) bytes, cut at a character. Stock's
  `widget_get_text_utf8` ignores its size for wide text and overran the stack (a reboot), so the
  payload never calls it ([payload](payload.md)).
- Leading blanks are dropped (`ly_lead`: space, tab, U+00A0, U+2000..U+200B, U+202F, U+3000,
  U+FEFF) because stock keeps everything after the time stamp's `]`, so LRCLIB's `[00:12.34] text`
  indented the first row. Blanks inside and at the end stay.

## Layout and appearance

- The current line's top is anchored at 102 px (0.35 of the 292 px view). A label has up to six
  wrapped rows (`LY_LINES_MAX`), `LYH` px per row and a `LYG` px gap (see "Text size").
- A line of more than four rows is anchored higher (`ly_anchor`): its top sits where the next
  line's first row still ends 8 px (`LY_ANCHOR_ROOM`) above the view's bottom, not above 20 px
  (`LY_ANCHOR_MIN`). At Large that is 102 px up to four rows, 68 for five and 34 for six.
  Why: LRC files with several sentences under one time stamp lost everything after row three.
- `ly.man` counts from the anchored line's own anchor; `ly_move` adds the two anchors' difference
  to a move and `ly_rebase` picks the line nearest the 102 px anchor, so nothing jumps.
- Lines up to `LY_OFF_MAX` (1168 px, 4 x the view, also the cap of a spring's offset) outside the
  view stay laid out. The longest move that does not snap is 929 px, and a line on screen must stay
  laid out until its spring has taken it out.
- With the intro dots a six-row first line starts one pitch (`LYH + LYG`) lower and its last row
  is clipped until the dots go.
- The page breaks lines itself (`ly_break`) and sets the label text with explicit `\n`s. Rows,
  label height and breaks come from that one result, cached per line (`ly.brk`). Why: stock's
  wrap puts the text's last character on the row and clips it when it overflows the 260 px content
  width ("Time is a valuable thing" lost the end of its `g`). Breaking ourselves means rows that fit
  never reach that check. A trailing space (can hide a word) and wider margins were rejected.
- `ly_break`:
  - A line measuring at most `LY_FIT_W` (260) is one row, left to stock.
  - Otherwise greedy at spaces, rows at most `LY_ROW_W` (259, stock adds 1 px). A word wider than a
    row, or text without spaces (CJK), breaks by code point. At most six rows.
  - Text beyond six rows is cut and the last row ends in `…` (`LY_MARK`), keeping the mark's width
    free unless the rest of the line fits without it.
  - Widths add up (no kerning). Each line is measured once and cached, except a measure of 0 for
    non-empty text: that line stays one row, uncached, and is retried on later ticks (at most 20
    failed layouts per lyrics load, then one row is kept).
  - A label's text is set again when its row count changes.
- The measuring label measures only in its resolved style, and a window resolves styles at
  `EVT_WINDOW_WILL_OPEN`. Nothing is measured before that stage (those lines are retried), and the
  probe calls `widget_update_style` before each measure, so a face switch during the open animation
  is measured in the new face.
- `np_lyric_style` selects `lyrics.ttf` (the Inter Bold subset). `np_lyric_cjk_style` uses the
  default font for mixed scripts, unsupported characters or malformed UTF-8. AWTK has no per-glyph
  font fallback.
- Lines are white with opacities 1.0, 0.45, 0.32, 0.24, 0.18 by distance from the current line, with
  a 56 px edge fade at both ends. While browsing, non-current lines use 0.6 before the fade.
- `np_scrim_lyrics.png` is 27% black (alpha 68) with eased 44 px edges. See
  [Now Playing](nowplaying.md) for the tint and scrim assets.

## Text size

Settings > Now Playing > **Lyrics Text Size** (picker `m1plus_lyrsize`: Small / Medium / Large, see
[settings](settings.md)) is saved atomically by `ly_size_set` in `/mnt/data/m1plus/nowplaying-lyrics-size`
(`0\n`, `1\n`, `2\n`; missing or invalid = Large).

| Size | Font | Row pitch `LYH` (font + `spacer`) | Gap `LYG` | Intro pad `LYH + LYG` |
|---|---|---|---|---|
| Small | 22 | 25 (3) | 9 | 34 |
| Medium | 26 | 29 (3) | 10 | 39 |
| Large | 30 | 34 (4) | 12 | 46 |

- **Face.** Large and Medium use the bold face for Latin, Greek and Cyrillic. Small uses the
  default font for every line (bold is too heavy at 22 px). `LYR_BOLD_SIZES` in
  `tools/mod_nowplaying.py` lists the bold sizes.
- **Styles, not a runtime override.** Each size has a style pair (`np_lyric_style[_m|_s]`,
  `np_lyric_cjk_style[_m|_s]`; tables `LYRIC_SIZE_STYLES`, `LYR_SIZES`, `LYR_GAPS`, and `ly_sizes`
  in `patch/lyrics.c`). Every `widget_use_style` call takes the name from `LYSTYLE(face)`, so the
  probe measures in the size it draws in. `LYH` is the font plus `spacer`, which AWTK's label paint
  uses, so layout and paint agree.
- **Follows the size:** pitch, gap, intro pad, dot centring, `ly_anchor`, edge-fade row centres,
  the tap map and label heights. Fixed: the 102 px anchor, the 6-row cap, `LY_ANCHOR_MIN/ROOM`,
  `LY_OFF_MAX`, the pool of 20 labels and the 259 / 260 px row widths.
- **When read.** `ly_start` reads the file. `ly_refresh` (from `np_on_foreground`) takes a changed
  size when Now Playing is in front again: it resets every label's style, height and place and drops
  the break cache, then lays out from the current line. No label is recreated.
- **Vertical margins.** Stock's label paint draws a wrapped row only while `y + font size` is at
  most the content area's bottom, so the last row shows only if both margins fit in the spacer.
  Large (spacer 4) keeps the default 2 + 2. Medium and Small (spacer 3) set `margin_top` and
  `margin_bottom` to 1 (`lyr_vmargin`); with the defaults every wrapped line lost its last row.
- **Side margins.** Stock paints a one-row label through `widget_draw_icon_text`, whose `margin`
  defaults to 0, and a wrapped one through the content area, whose default is 2. Every style sets
  `margin_left` 0 and `margin_right` 4 (`LYR_MARGIN_L/R`), so both start at the page's 28 px edge,
  in line with the progress bar and the intro dots (`LY_DOT_X` 0), and keep 260 px of width.
  Without them a one-row line sat 2 px left of a wrapped one.

## Second view

**Stand-down.** While spoken audio plays, Now Playing shows its [episode notes page](nowplaying.md#episode-notes-page)
in the lyrics slot and calls `ly_standdown(1)`; `ly_standdown(0)` returns the page to lyrics. The
flag is only a wish: `ly_tick` applies it (`ly_stand`). Standing down hides `np_lyrics` (and makes it
insensitive) and `img_np_scrim_lyrics`, makes stock's `label_lyricmsg` transparent (opacity 0), and the
tick does no other work. The message's visible flag stays stock's, set as each track loads, so
standing up (opacity 255) shows it exactly when stock has it for the track playing then. Standing up
also shows the box and scrim and lays the lines out from the stock rows. While the idle page has the engine the flag is not
applied.


The engine is one static state bound to one view at a time. `ly_start(win)` binds it to Now
Playing's `np_lyrics`; the [idle lyrics page](idlelyrics.md) takes it with `ly_retarget(win, box, h)`
and gives it back with `ly_release()`. Decision: rebind rather than run two instances, since the
state is large and the lines, clock and timers would each need an owner.

- `ly_retarget` makes the 20 labels, the probe and the three dots in the page's box first (a refused
  label returns -1 with the engine untouched), then parks Now Playing's widgets (hidden, alive) and
  restarts the state on the new box, keeping `src` (Now Playing's `scroll_lrc`) and the stock list.
- `ly_release` stops the timers, restores the parked widgets hidden and forgets every cached fact
  about them, so the next tick lays out from the stock rows. It is idempotent and also runs at the
  top of `ly_refresh`, so Now Playing never ticks an engine bound to a closing page. `ly_stop` clears
  the parked widgets too.
- **Follows the view's height** (`ly.vh`): the anchor (`ly.anc`: 102 on Now Playing, 130 on the page),
  `ly_anchor`'s limit, `ly_edge`'s bottom, the laid-out windows, `ly_rebase` and the offset bound
  (4 x the height: 1168, and 1488 on the page). Fixed: the pool of 20 labels and the row widths.
- **Source rows.** The page reads Now Playing's `scroll_lrc` while another window covers it. Now
  Playing's own `np_tick` does no work then (`np.fg`), so the page timer calls `ly_tick` itself.
  See [idlelyrics](idlelyrics.md) for the page.

## Motion and touch

The motion is inspired by amll-dev/applemusic-like-lyrics (anchor, falloff, staggered spring), in
integer arithmetic without blur.

- A 640 ms damped spring (zeta 0.72, wn 12/s, 65-entry table), 6 px overshoot cap.
- Lines start in sequence with delays of 50, 97, 141, 182 ms and so on.
- One 40 ms timer moves visible labels while needed. Moves of more than four lines, and refused
  timers, snap into place.
- Pointer listeners on `np_lyrics` return `RET_OK`, leaving sideways swipes to the slide view. Labels
  are insensitive. A vertical move over 10 px starts browsing, and after 3 s without touches the
  lines return. The highlight keeps following playback.
- **Direction lock.** Once a drag is vertical, each of its MOVEs returns `RET_STOP`. Stock's
  `widget_on_pointer_move` (`0x6716f8`) then sends the slide view an ABORT in place of the move, so
  a finger that drifts sideways turns no page. The slide view starts a page drag only at 11 px
  sideways (`0x618d38`), later than the 10 px that decides the direction here. Same rule on the
  information page ([nowplaying](nowplaying.md)).
- A tap seeks with stock `seek_time(seconds)`. It is ignored while stopped or within the first
  200 ms of an animation, and a 1 s hold lets the player catch up. The stock seek can block the UI thread for up to 2 s.
- **Idle countdown.** Stock restarts Now Playing's ten idle seconds only from its button handlers
  (`NP_IDLE_COUNT`, [bigcover](bigcover.md)), never for a touch, so the Idle Display view opened in
  the middle of a drag. `ly_awake` stores 20 for every pointer event on the lines, and `ly_tick`
  does while the finger is down or the lines are scrolled away.
- The pointer listeners carry their view as context and ignore events when it is not the engine's
  current one. `ly.noseek` makes taps seek nothing (idle page).

## Intro dots

Three 10 px image dots appear at the anchor when the first line starts at 4 s or later. Upcoming
lines sit one pitch lower. The dots keep 18 px spacing, fill by thirds, breathe over 2.4 s and fade
over the final 500 ms, then the lines spring into the anchor. An 80 ms timer runs only while the
dots show, playback is active and the screen is lit (it ends itself in the dark; the lit page tick starts it again).

`ly_clock` interpolates whole-second playback readings with the monotonic clock, bounded within the
reported second. Pauses freeze it and seeks reset it. Dots move with the lines during a drag.

## Unsynced lyrics

Stock's `.lrc` reader (`0x5d3670`, tail-called by `mclLoadExLyric`) keeps only lines with a time
tag: a line without `[` is skipped (`0x5d3eec`). Plain lyrics (LRCLIB's `plainLyrics`, which
[Cover & Lyrics](onlineart.md) saves as given, or a text file of the user's) gave no rows.

- **The reader's `fopen`** (hook 43, `ly_lrc_open`): a file of at most 64 KB with no time tag
  (`[`, one to three digits, `:`, a digit; `[ar:…]`, `[Chorus]` are not tags) and some text is
  handed over as a copy in `/tmp/m1plus-plain.lrc`, opened, then unlinked (the reader's `fclose`
  frees it). Each line gets `[mm:ss.00]` with its index in whole seconds, the unit of `lrc_time`,
  so the keys are distinct and the reader's sort keeps the order. The BOM and blank lines at the
  ends go, and a run of blank lines becomes one blank row (the reader stores `" "`, `ly_lead`
  strips it). The reader takes the text after a line's last `]` (`0x5d3ef8`), so `[` and `]`
  become `(` and `)`. A line is cut at 1000 bytes on a character, at most 5999 lines (99:59).
  Encodings are stock's: it converts UTF-16 and GB18030 files before this `fopen`. Any failure,
  a file with a tag, or the kill switch `/mnt/mmc/m1plus-off` (checked before the file is read):
  stock `fopen` on the path. `ly_plain_n` keeps the copy's line count (0 otherwise).
- **The page**: `ly.plain` is set for new rows when their count is `ly_plain_n` (or `LY_MAX` for
  a longer copy), the local lyric deque still holds the copy's lines (`mclGetLyricSize`) and the
  rows' times are 0, 1, 2 and so on. `mclLoadExLyric` empties that deque for every track, also
  one whose `.lrc` is missing (the reader returns before its `fopen`, so `ly_plain_n` stays),
  and online lyrics have their own deque: neither a short synced file nor online rows after a
  plain file pass. Then no line is current, every line is white (only the edge
  fades), the first line's row centre sits where the top fade ends (`LY_PLAIN_TOP`, `ly_anchor`),
  the lines never move with the song, a tap seeks nothing and the lines stay where a drag leaves
  them (`browse` still ends after 3 s, so the idle countdown is stock's again). `ly_norm` picks
  the anchored line around `LY_PLAIN_TOP` instead of `LY_ANCHOR`, so a drag stops at
  the first line's place and when the last line is whole above the bottom fade
  (`ly_plain_floor`); lines shorter than the view stay at the top. The idle page reads them the
  same way.

## Pins and safety

`LYRICS_PINS` checks the row properties, stock timer reads, row-click flag accesses, font fallback,
label pitch instructions and style resolution. `LRCOPEN_PINS` checks hook 43's site and the
reader's steps the copy relies on. Called functions are checked against `FUNCTIONS`.

All work runs on the UI thread from page timers and listeners (hook 43 in the reader, which
`mclLoadExLyric` runs there). No stock code word is written but hook 43's site; the
one stock data word written is Now Playing's idle countdown, with the value stock's own handlers
store. No stock widget is renamed or removed, and no thread or lock is added. Startup failures keep
the stock list; animation failures snap. Destroy removes timers and ignores stray events.

## Limits

Blur, line translation, per-word fill and a larger current line are not implemented. Dots between
lyric lines are not enabled.
