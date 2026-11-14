# Cassette Mode

A fullscreen 480 × 320 cassette-style Now Playing page, opened from the More sheet's Display Mode page.
Tap the cassette to pause/resume; tap the top-left screw to close. It adds no hook or boot work
and owns one page timer. Art is generic, without brand names or logos. The visual references
are Sony's NW-A100/NW-ZX500 cassette screen and FiiO Tape mode.

Sources: `patch/tape.c`, `tools/tape_art.py`, `tools/pod_ui.py` (`build_tape_page`),
`tools/mod_icons.py`, and `TP_*` in `offsets.inc`. Tests: `test/pod/tape.py`; preview:
`tools/preview/preview_tape.py`. Emulated frames are written to `out/preview/tape-emu-*.png`.
Use the final checklist for validation of a new build.

## Themes and assets

Settings → Now Playing → Theme offers Normal, Chrome, Metal and Auto (the tape follows the track's quality,
"Quality" below). The order is `tape_art.THEME_NAMES`, then Auto (`TP_THEME_AUTO` 3);
`/mnt/data/m1plus/cassette-theme` stores `0\n` .. `3\n` atomically.
`tape_theme` accepts `0` .. `3` with an optional newline and defaults to Auto (3) for all other data and for no file.
A failed save changes neither file nor label. The Tape page reads the setting once at open.

Shared assets are `tape_top`, `tape_screw`, `tape_tex` and `tape_badge`. Each theme has `tape_shell_<theme>`,
`tape_hubs_<theme>` and `tape_marks_<theme>`, plus text colours and TYPE I NORMAL / TYPE II CHROME /
TYPE IV METAL fine print. Current sizes and rootfs headroom come from the build output;
`fwtool` enforces the stock limit.

Cover-derived band tint, a control strip, rewind/fast-forward, track-skip swipes, a lock-screen
skin and hardware Back handling are not implemented. Seek needs a reviewed stock path; see
[virtual iPod limits](ipod.md#playback-limits).

## Landscape and rotation

The panel is portrait 320 x 480; the page is drawn **landscape, 480 x 320** (the player held sideways). The landscape picture is turned **90 degrees clockwise** into the framebuffer: the
landscape top edge ends up on the portrait's right edge (the player is held with its right edge up; `out/preview/tape-1-portrait.png`). **Landscape pixel (x, y) is the framebuffer's row x,
column 319 - y** (`tp_pix`; `tools/tape_art.py` `rot`). The touch is mapped back the same way: a portrait event at (column c, row r) is the landscape point (r, 319 - c) (`tp_local`).
The cassette is 470 x 300 at (5, 10) (a real one is 100 x 63.8 mm, 1.57:1) on a #111 surface with a soft drop shadow.

### Why this rotated-text path

AWTK's text drawing does not rotate (`canvas_draw_text` has no angle). The ways looked at: (1) `vgcanvas` rotate + text: the stock demo is built for the software `lcd_mem` canvas
and the payload never touches a vgcanvas, nothing is pinned, no precedent; (2) draw the text through the canvas into an offscreen bitmap and copy it rotated: needs a canvas on that
bitmap (not pinned) and an extra buffer; (3) **the font's glyph bitmaps, blended into a bitmap of ours through the turned pixel map**: `font_get_glyph` and `font_get_vmetrics` are
already pinned and used by **Cover Flow's landscape captions** (`patch/coverflow.c` `caption`), which are on the device and accepted. The page uses (3): each glyph's 8-bit alpha is
blended into the frame at (pen + glyph.x + c, top + glyph.y + ascent + r), landscape, written through `tp_pix`. Advance and vertical metrics are AWTK's own (advance + 1 px a glyph,
`ascent` = `font_get_vmetrics`), so text lays out as `StbText` measures it. The font object comes from the paint's canvas after `widget_prepare_text_style` of a hidden label
(`label_tp_font`), so the page needs no new stock function. The emulation test (`test/pod/tape.py`) runs the payload with the shipped font's glyphs through the stb model
(`tools/stb_raster.py`) and compares the frame, turned back, **pixel for pixel** with a reference picture computed from the design.

## The page

- **The window** is `fullscreen = true` (480 px, the stock status bar not drawn, as the Pod's), colour #111112, with one view `tape_view` (320 x 480, the touch target, painted by the
  payload in its own `EVT_AFTER_PAINT`) and a hidden, insensitive holder with `label_tp_font` (the font) and `label_title` (the name Tape, for the tests).
- **The frame** is a 320 x 480 RGBA bitmap the page owns (614 KB, freed on destroy), the picture turned. It starts as the shell and only what changes is drawn into it. The paint blits it
  1:1 with one `canvas_draw_image` (the canvas clips it to the dirty rectangle); the timer invalidates **only the rectangle that changed** (`widget_invalidate_force(view, rect)`: a 16 byte
  rectangle in the view's own coordinates, `TAPE_PINS`), a hub tick the two 30 px squares' bounding box, a text change its field.
- **Pictures** (made at build time by `tools/tape_art.py`, installed as PNGs, decoded once at open by `widget_load_image` and copied as RGBA8888 whatever order the decoder gives, the way
  `cc_decode` does; a picture that is missing or of another size fails the open):

  | Picture | Size (turned) | Holds |
  | --- | --- | --- |
  | `tape_shell_<theme>` | 320 x 480, opaque (RGBA, alpha 255: the decoder gives 32 bit pixels for it, as for every picture the payload loads), 26 - 31 KB | the cassette, **smooth** (the page adds grain and knurl): shell, screws, label paper, band, ruled lines, the panel, the holes, the clear window, the direction arrow. **No text, no marks, no tape, no rings, no hubs** |
  | `tape_top` | 74 x 280, RGBA | the holes' gear rings and lips, the clear window's scale and bevel (what lies over the tape), by alpha extraction (drawn on black and on white at 3x) |
  | `tape_hubs_<theme>` | 30 x 720, RGBA | the reel hub in **24 frames, 5 degrees apart**: a pale translucent plastic ring with six teeth round a dark opening and a pale disc with a dark 3-spoke drive, lit from the top left with a soft shadow under it (about 24 KB a theme); the ring repeats every 60 degrees, the drive every 120, so the picture repeats every **120 degrees** and 24 frames close the loop seamlessly (angle modulo 120 / 5; `tp.ang` counts sixteenths modulo 1920); stacked, pre-rotated with the picture |
  | `tape_marks_<theme>` | 26 x 78, RGBA | the printed play mark, pause mark and repeat arrow, in the theme's band ink (white, Metal's gold) |
  | `tape_tex` | 320 x 480, RGBA, 13 KB | the shell's texture as two maps, the same for every theme: **red the knurl's strength** (128 is the cell's own alpha, in steps of 4), **green the grain's amplitude** (alpha of 255, at most 24); see "Grain and knurl" |
  | `tape_badge` | 24 x 52, RGBA, 0.5 KB | the quality sticker, 52 x 24 in landscape: a gold foil rectangle with a soft shadow, no text (the page writes `HI-RES` or `DSD` on it); missing: the page opens without a sticker |
  | `tape_screw` | 26 x 26, RGBA | the close screw pressed: darker, its slot turned 45 degrees (the same in every theme) |

  The sizes are above (the rebuilt rootfs may not exceed stock size and the build refuses otherwise).
- **The reels** (`tp_reel_px`): per landscape pixel, the shell, then the **tape packs** (a disc of the pack's radius around each reel, seen only through the two holes and the clear window,
  integer distance from a table `sqrt(d2h) * 8` made at open: 1/16 px, an anti-aliased edge, the look below), then
  `tape_top` by its alpha, then the hub sprite by its alpha. The pack radii follow the position: `r_supply^2 + r_takeup^2 = 66^2 + 16^2` (the tape's area), the take-up's area growing
  linearly with `pos / len` (`tp_radii`, fixed point). A pack is redrawn when its radius changes by 1/4 px, so about every 0.4 s on a 5 minute track; a hub when its 5 degree frame changes.
- **The hubs turn while playing**, counterclockwise, both the same way, at the speed of constant tape speed: angular speed x pack radius = 76,800 sixteenths of a degree x px a second
  (`TP_SPIN`), so the take-up reel (16 px of tape at the start) turns at 300 degrees a second and the supply reel (66 px) slower, and they swap places as the tape moves. A 70 ms tick turns the
  fastest reel at most 21 degrees, under half the 60 degree period: no wagon wheel. **Paused: they stand still** and the timer idles. A tick that comes late (a stalled loop) turns the
  reels as 250 ms would.
- **The marks**: the play triangle or the pause bars (`mclGetPlayStatus`: 2 is playing) and the repeat arrow (`mclGetPlayMode` 1 or 3), the band restored under them and the sprite over it.
- **The text** (drawn by the paint, which has the font; the fields below restore their rectangle from the shell, clip the glyphs to it and are cut with an ellipsis to their room):

  | Field | Where (landscape) | Source |
  | --- | --- | --- |
  | title | x 40, line middle 49, 22 px | the playing track's title (else its file name; `Not Playing` with no track) |
  | artist, album | 40 / 70, 16 px (262 px room); 40 / 89, 13 px (190 px room) | the playing track's tags |
  | bias line | right end 435, 70, 11 px (124 px room) | fixed per theme, in the print colour: `NORMAL BIAS · 120µs EQ`, `HIGH BIAS · 70µs EQ`, `METAL BIAS · 70µs EQ` (what a real tape of the type prints) |
  | sticker | the shell's lower left, cell 33 .. 85 x 237 .. 261, text 11 px bold, middle 58 / 248 | `HI-RES` or `DSD` on `tape_badge`, nothing for other tracks ("Quality" below) |
  | elapsed, -remaining | right end 428, 89, 12 px | `get_playtimeandlength`, `m:ss  -m:ss` |
  | A, fine print | 58 / 146, 54 px bold; 40 / 206, 12 px | fixed per theme (`TYPE I NORMAL`, `TYPE II CHROME`, `TYPE IV METAL`; drawn once, in the theme's print colour, flat) |
  | status line | right end 428, 206, 12 px (11), 212 px room | below |

  The status line is `VOL 42 | FLAC 16/44.1 | 21:07 | 60%`: the **volume** is the status bar's `label_volume` text, **read only, never set**; the **format** is the upper-case file extension of the
  playing track's path with the stream's figures from the player (`FLAC 24/96`, `MP3 320`, `DSD64`; the extension alone while the player has none: "Quality" below); the **clock** is `localtime` as `HH:MM` (24 h); the **battery** is read as the Pod does (`*system_bar` `0xa06f90` > `pgbar_battery` `value`, 20 % steps,
  `img_battery` = `bar_charge` while charging: a `+` before the number). It is set at 12 px if it fits 212 px (the advance + 1 px a glyph, the font's own), else 11 px, dropping the **clock
  first, then the format** (`tape_art.status_line`, the same function the mock and the test use). A missing status bar gives `VOL 0`.
- **Refresh only on change**: the timer looks at the track, the position, the play state, the repeat mode, the battery, the volume text and the clock minute each tick and redraws only what
  differs; the text itself is drawn by the next paint, not by the timer.

### Grain and knurl (laid on by the page)

The shell pictures hold the cassette **smooth**: shapes, colours and the light, but neither the paper's and plastic's grain nor the knurl. Both are texture no PNG packs (with them baked in,
the three shells were 695 KB: about two thirds of each was the grain, a fifth the knurl), so the page lays them on its own copy of the shell **once, when it opens** (`tp_finish`; `tape_art.finish`
is the same arithmetic in Python, integer for integer, and the test's reference). The shells and `tape_tex` together are about 100 KB.

- **Grain**: for pixel i = row x 320 + column of the turned picture, n = a byte of a hash of i (the multiply-xorshift hash Vinyl Mode's grain uses); the pixel moves towards white (n >= 128) or
  black by alpha `|n - 128| * amplitude >> 7` (of 256), the amplitude from `tape_tex`'s green: 14 on the shell, 16 on the paper, 13 on the band, 22 on the panel, 20 on the arrow, 0 on the
  screws, the holes, the window and off the cassette. The map is **measured**, not drawn (`shell_parts`: the picture drawn with flat white and flat black where the grain goes differs from
  the clean one by exactly the grain's alpha, whatever was drawn over it later).
- **Knurl**: the 4 x 4 cell at the landscape place (row, 319 - column): the groove (black, alpha 78), the lit top and left edge (white, 58), the shaded bottom and right edge (black, 64), the
  face (white, 14), each times `tape_tex`'s red `>> 7`. The red is the knurl's mask times the light's gain (the knurl's contrast follows the light), told for the lit pixel.
- **One map for every theme** (the Normal theme's: the themes share the geometry). Metal's two gold hairlines take the band's grain (13) instead of the arrow's (20).
- **Against the baked pictures**: the knurl and the light are within 11 levels of the pictures the material pass installed (mean 0.6); the grain is other noise of the same amplitude.
- **Cost**: about 14 M instructions once at open (emulation; the whole open 20.6 M, budget `OPEN_MAX` in `test/pod/tape.py` `life_tests`), nothing a tick. No memory beyond the decoded
  `tape_tex` while it is read (614 KB, transient). A `tape_tex` that is missing or of another size leaves the shell smooth; the page still opens.

## Touch

**Taps only.** The page binds pointer DOWN, UP and ABORT of its view and nothing else: **no MOVE handler, no `widget_grab`, no swipe detection**, and every handler returns RET_OK, so the stock
window manager's touch hook (`0x4cd788`, the pull-down from the top edge: a touch that began at y <= 80 and moved more than 10 px down, `docs/modules/home-guard.md`) sees every drag as on any other
page (the first build grabbed the pointer, which broke it). Portrait (c, r) is read as landscape (r, 319 - c); decided on the UP from where the touch began:

| Touch (landscape) | Does |
| --- | --- |
| began on the **top left screw**, the 50 x 50 area (0, 0) - (50, 50) around the screw at (24, 25) (the panel's top right corner: columns 270 .. 319, rows 0 .. 49), and ends in it | `navigator_back()`: the page closes, Now Playing is under it |
| began on the screw and the finger left it before lifting | nothing; the screw is let go |
| a move under 14 px in both axes anywhere else (a tap), page opened from the More sheet | `playpause_quick_click`, then the page looks again at once (the mark and the timer's pace follow without waiting a tick) |
| the same tap, page **opened by Now Playing's timer** (Idle Display, `tape_open_idle`) | `navigator_back()`, like the screw (as stock's Album Cover page closes on a tap); nothing plays or pauses |
| anything else (a long drag, a swipe in any direction), an abort | nothing |

**Auto-opened flag.** `tape_open_idle` (called only by `bc_timed_open`, [bigcover](bigcover.md) "Idle view") is `tape_open` plus `tp.idle = 1` once the page is up; `tape_open` (the More sheet) never sets it. The flag is part of the page's state, so destroy clears it and a later More open starts without it. A timed open on a page that already exists (0, nothing opened) leaves its flag as it was, both ways. The screw, its pressed look, drags and aborts behave the same either way. Tests: `test/pod/tape.py` `idle_touch_tests`.

While the finger is on the screw it is drawn **darker and turned** (`tape_screw`, drawn over the shell's screw by `tp_marks(4)`, only its 26 px square invalidated) and the normal screw comes back on
release, so it reads as a control. The screw's top left corner is inside the pull-down zone: a drag down from it opens the control centre like anywhere at the top edge. No click sound (`hciplayer`
owns the PCM).

## Timer and the page's life

`tp_first` (a 50 ms one-shot, armed at open) makes the first look and starts `tp_tick` at **70 ms while playing, 500 ms paused** (`TP_PLAY_MS`, `TP_IDLE_MS`); `tp_retime` changes the one timer's
interval in place with `timer_modify` (never a second timer, `IPOD_PINS` pin it). The timer is removed on `EVT_WINDOW_TO_BG` (another window over the page: the More sheet, a dialog, the
lock screen) and added again on `TO_FG`; destroy removes it, frees the five bitmaps and the distance table and clears the state; a destroy of another window leaves the page alone.
**Nothing here stops the stock screen-off**: the page sets no idle state, holds no wake lock and reads no input but its own touches; a repaint or a timer is not input, so the stock idle path is not reset by them (this is by construction; it is on the checklist).

### Idle power

Following the other page timers (`m1_screen_lit()` in `patch/common.c`, the stock `backlight_status` byte, already pinned; no new pin): a 14 frames a second tick is not free (FiiO's reviewers note the same for Tape mode), so **while the screen is off `tp_tick` does no visual work** (no `tp_update`: no reels, no text, no invalidation, no player or status-bar reads) and `tp_want_ms` returns `POD_DARK_MS` (1 s), set in place with `timer_modify` (once, not again while dark). The first tick after the light is back runs `tp_update` and returns the interval to 70 ms playing / 500 ms paused; the reel step is capped by the usual 250 ms and the text compares with what it shows, so it catches up without a jump. A page opened with the screen off (`tp_first`) waits for the light with a 1 s one-shot before its first full draw. Lit and paused it idles at 2 ticks a second and repaints nothing when nothing changed. Tests: `test/pod/tape.py` (`life_tests`).

## Safety and fallbacks

- No hook, no patched word. `TAPE_PINS` (`tools/pod.py`) pins the stock words the page newly relies on (`widget_invalidate_force` passing its rectangle on, the rectangle's 16 bytes in widget
  coordinates); every other stock call is one the payload already pins (Cover Flow's glyph path, the Pod's timer, battery and quick clicks).
- A page that fails to open (no window, no view or label, a picture missing or of another size, no memory for the frame) frees what it made, goes back with `navigator_back` and returns -1; the
  More sheet, which closes only after the page is up (`pm_on_tape`), stays as it was.
- Hidden stays `visible=false` + `sensitive=false`; the only visible, sensitive widget is `tape_view`; the picture is painted, not widgets.

## Quality (the format, the sticker, the Auto theme)

The player keeps a record of the stream it plays; stock's `mclGetInfo` (`0x5d3518`: a mutex, then a copy of 0x34 bytes) gives it: the bit rate in bit/s at 0, the sample
rate in Hz at 4, the codec's name at 0x10, the bits a sample at 0x30 (1 for DSD). It is the record stock's own quality line prints (`show_player_face`,
`%s|%.1fkHz|%dbit|%dkbps`) and `get_hrflag` (`0x4dfbc4`) reads. `tp_quality` turns it into three things:

| Stream | Status line | Auto's tape | Sticker |
| --- | --- | --- | --- |
| lossy (MP3, AAC, OGG ...) | `MP3 320` (the extension and kbit/s) | Normal | none |
| lossless up to 16 bit / 48 kHz | `FLAC 16/44.1` (bits / kHz, one decimal when there is one) | Chrome | none |
| lossless over 48 kHz, or 24 bit from 44.1 kHz (`get_hrflag`'s rule) | `FLAC 24/96` | Metal | `HI-RES` |
| DSD (1 bit) | `DSD64`, `DSD128` .. (the rate / 44.1 kHz) | Metal | `DSD` |

- **Lossless** is the codec's name as `get_hrflag` spells it (`FLAC`, `ALAC`, `WAV`, `APE`, `AIFF`, `DSD`, `DSF`, `ISO`) or the file's extension (those and `AIF`, `DFF`, `WV`), so an
  ALAC `.m4a` is lossless by its codec and an AAC one is not.
- **No record** (no rate or no name: nothing playing yet, a stream the player does not describe): everything follows the extension: `FLAC` alone on the status line, Chrome for a
  lossless extension, Metal and `DSD` for `.dsf` / `.dff`, Normal otherwise.
- **The record's writer:** one thread, `mclSyncPlayerStatus` (`0x5d144c`), asks the player process for `get-music-info` every 200 ms and writes the whole record from the reply
  in one lock section (`0x5d1588` .. `0x5d17f0`), with the position at 8 and the length at 0xc (`PLAYINFO_POS`, `PLAYINFO_LEN`; `mclGetPlayTime` returns them). A copy is
  always one reply. `mclStartPlayer`, `mclNextSong` and `mclPrevSong` zero only the position and the length when another track is started; the rate, bits and name stay the
  last track's until a later reply.
- **A change of track is one event:** the page holds the last track (title, artist, album, time, packs, format, sticker, tape; the hubs go on turning) until the record is the
  new track's, then everything changes in that update. The record is read at every look meanwhile and is the new track's when it has a stream (rate, name), a length, and
  that length is not the last track's (`tp.r_len`, the last one seen before the change) or its position is below the last track's (`tp.r_pos`). No length: not yet. The old
  length and a position not below the old one: the last track's, arriving late. `TP_INFO_MS` (600 ms) is the fallback, after which the record is taken as it is (tracks of
  equal length, a skip while paused, a player that says nothing). Not held: the page's first look, a full redraw, nothing playing, and the same file as the track shown
  (`tp.p_hash`: the next track of a CUE image is the same stream). A second change inside the hold starts it again for the newest track; the skipped one is never shown. Back to the track shown inside the hold ends the wait (changes are told by `tp.q_key`, the track the quality is for, not by the track shown).
  After the hold the format, the sticker and the tape follow when the record's rate, bits or name differ from the ones
  last used. The bit rate is not part of that: a VBR file shows the bit rate of the first look and the line is not redrawn as it moves. The exception is a record that is
  still the one read at the change of track (`tp.unsure`; one `mclGetInfo` at the change keeps it): it may be the last track's, arriving late, so until a record differs from
  it the bit rate is compared too. A track after one of the same codec, rate and bits then gets its own bit rate when its record arrives; a VBR track whose record was already
  there at the change redraws the line once. All of this belongs to the track (`tp.q_key`), not to the drawing: a full redraw of the same track (the page back in front)
  keeps the wait and the doubt, and the page's first look, which asks at once, starts in doubt too, since the page may open right after a change.
- **Auto** (`tp.automatic`, the saved theme 3): the page opens with the playing track's tape (one shell loaded; nothing playing: Normal). When the tape changes `tp_theme_load`
  loads the new theme's shell (with `tp_finish`), hubs and marks, copies the shell into the frame, frees the old three and the page draws everything again (reels, marks, all
  text, the whole view invalidated): about 20.5 M instructions in that tick, as much as an open. A theme whose pictures will not load leaves the tape shown and is not tried
  again for that track. A chosen theme (Normal, Chrome, Metal) never changes its tape; the format and the sticker follow the stream in every theme.
- **The tape's colour** follows the theme too (`theme_pack`, `THEMES[..]['pack']`): ferric brown for Normal (#22150E to #6C4F38, as before), a darker, greyer brown for Chrome
  (#1A1412 to #5A4C46), blue-black for Metal (#121215 to #505058), the same sheen and windings.

Open: how soon after a track starts the player's record is the new track's (the hold ends with it: a poll of 200 ms and the player's time to open the file), whether the player
answers a poll with the last track's record after the start (the rule holds through it), what name it gives an ALAC or AAC `.m4a`, and how
long the tick that changes the tape takes on the panel.

## Themes

The look is a **theme the user chooses**: **Settings > Now Playing > Theme: Normal, Chrome, Metal, or Auto (default)**, as FiiO's "Tape mode theme" (above). With a
chosen theme the same cassette is shown for every track; a theme is a complete look (shell colour, label paper and print, band, hub ring, the tape's own colour). **Auto** makes
it the tape grade of the music, as Sony does ("Quality" above). More themes can be added later as data (`THEMES` in the mock).

| Theme | Shell | Label | Band | Hub |
| --- | --- | --- | --- | --- |
| Normal | smoky dark grey | off-white paper, dark ink | blue (tinted by the cover's tone) | white |
| Chrome | black-graphite | silver paper | red (tinted by the cover's tone) | silver |
| Metal | black | black label, gold print | dark with gold hairlines | gold |

Background only: Sony picks its tape from the codec and bitrate (9 real tapes: lossy up to 128 kbps CHF, up to 160 BHF, up to 256 AHF, up to
320 JHF; CD-quality FLAC / ALAC / APE UCX, AIFF UCX-S, WAV DUAD ferrichrome; hi-res PCM METAL; DSD Metal Master). Our Auto has three tapes for
the same idea (lossy, lossless, hi-res / DSD) and keeps the fixed themes as choices. Sources: av.watch.impress.co.jp/docs/review/review/1222109.html,
news.mynavi.jp/article/20191016-910000/, the FiiO M21 manual (Tape mode, Settings > Tape mode theme), the FIIO_official post on X about Cassette Mode.

## The cassette (follows a real one and Sony's screen turned sideways)

- **Symmetry:** everything static is symmetric about x 240 (the cassette 5 .. 475, the label 37 .. 443 with 32 px of shell each side, the panel, the window, the reels 132 / 348, the screws 24 / 456, the bottom section and its holes, the knurl mask); `test/pod/tape.py` `symmetry_tests` checks the constants and the shell picture. V2.1oXTR had the label at 30 .. 436 (25 px left, 39 right); the text, marks, arrow and the A moved 7 px with it. The intended asymmetries are the light (the drop shadow falls right and down, a hole's highlight and the bevels are lit from the top left; since the material pass also the shell's light falloff, the frame's shadow on the paper, the sheen, the lit hubs and the screws' slot angles); `symmetry_tests` finds the shapes by colour with a tolerance wide enough for that shading and asserts the left rim is lighter than the right.
- **Shell (material pass, after Sony's METALLIC 46 as the reference):** a matte moulded plastic with a **crisp knurl of raised squares on a 4 px pitch, laid on at 1:1 on the pixel grid** by the page ("Grain and knurl"; `KNURL`: a 3 x 3 square with a 1 px light top and left edge, a 1 px dark bottom and right edge and a 1 px groove; never downsampled from 3x, which smeared the old one), a **smooth flat rim band** inside the outer edge, fine deterministic grain, a 1.8 px bevel, a moulded step, one soft light from the top left that falls off across the shell (`shell_parts`: brightness 1.18 at the top left to about 0.72 at the bottom right, the knurl's contrast following it, a faint diagonal sheen on shell and label; deterministic, per pixel). The label has the paper's grain and a soft shade on the band, the frame's shadow on the paper (top and left) and the panel's cut-edge shadow. The knurl is masked off the label, the screws and the holes. No brand mark; the moulded word on the side rim was left out (nothing is better than a generic one the font cannot carry at build time).
- **Screws:** four recessed Phillips screws in the corners and one at the bottom centre: a dark countersunk ring, a metal head, a cross slot (each screw has its own slot angle, `SCREW_TURN`; the close screw's is 0), a specular spot.
- **Label:** paper (faint grain) on a raised frame, covering most of the upper face. Index lines with the title (22 px), artist and album written on them,
  elapsed and -remaining in small type on the album line, plain paper at the top right (the title may use the full width), a colour band across the middle with a big "A",
  below it the fine print (type and grade, 12 px), the direction arrow (**printed ink**, `foil()`: the theme's print colour with a hint of light at the top (+10 % white) and shade at the bottom (-12 % black) and the paper's grain, flat and not glossy, sharp edge; the Metal band's gold hairlines too) and a status line.
  Play / pause (a triangle or two bars) and the repeat (auto-reverse) arrow are printed marks at the band's right end.
- **Live label fields** (printed in the label's ink and small type, so the label still reads as a label; each is refreshed on the page timer only when its value changed):

  | Field | Where | Source on the device |
  | --- | --- | --- |
  | battery, a number at the end of the status line (`60%`, 20 .. 100 in 20 % steps; `+60%` while charging: the device font has `+`) | status line | `*system_bar` (`0xa06f90`) > `pgbar_battery` `value` (0 / 20 / 40 / 60 / 80 / 100) and `img_battery` (`bar_charge` while charging), as `ipod.md` reads it; no bar: no cells |
  | `VOL n` | status line, bottom right of the band row | the status bar's `label_volume` text (0 .. 100), **read only, never set** |
  | format (`FLAC 16/44.1`, `MP3 320`) | status line | the playing track's info (information only; it does not choose the theme) |
  | clock (`21:07`) | status line | the system time |
  | title, artist, album, elapsed, -remaining | index lines | the playing track and `get_playtimeandlength`, as the Pod's Now Playing |

  The status line is `VOL 42 | MP3 320 | 21:07 | 60%`, measured with the device font (`StbText`) against 212 px right of the direction arrow: 12 px if it fits, else 11 px;
fields dropped in this order when it does not fit: the clock, then the format (`status_line` in the mock). In the mock all four frames fit at 12 px with every field.
- **Window inside the label:** a black inner panel in the band with two round reel holes (gear ring, 28 px radius, a 28 px wide hub with six teeth) and a **clear window**
  between them with a centre scale. The tape packs show **progress** through the holes and the clear window: `r_supply^2 + r_takeup^2 = 66^2 + 16^2` (tape
  area conserved), the supply shrinking from 66 to 16 px and the take-up growing from 16 to 66 px (clipped to the holes and the window). Sony's pack does not change with position; ours does.
- **Depth:** the label is set into the shell (a soft shadow round its frame); the bottom section is a raised, separately moulded trapezoid with its own shadow and a visible 3 px thickness edge, the same knurl and bevel; two pinch-roller holes, two small square holes and the head opening with real depth (dark inside, an inner shadow, a lit lower lip on whole pixels). The Metal shell is warm brown-black, Chrome and Normal get the same depth in their own colours.
- Nothing off the cassette: no LED, no counter box. Paused: the reels stand still and the label shows the pause mark.
- **Hub, packs, window:** `hub_sprite(angle, colour)` is one function of the angle, quantised to 24 frames (5 degree steps, the 120 degree cycle above). The tape pack is a smooth near-black brown (#22150E) with the static bow-tie sheen of wound tape towards #6C4F38 (see "The pack" below). The centre window is smoked glass: a dark gradient (`#3E4044` to `#141518`) in `tape_shell`, and in `tape_top` a soft diagonal reflection, an inner shadow at the frame edge and a printed scale (a 1 px centre line and ticks on whole pixels, #D8DADE, with its shadow a pixel right and down). `tape_top` also has the lip's shadow on the tape, the hole ring lit at the lower right and shaded at the upper left, the reflection fading top to bottom, and three faint hairline scratches.

## Frames (the mock)

1 Normal, near the start, playing; 2 Chrome, mid-track, repeat on; 3 Metal, near the end, paused; 4 Chrome with the tap control strip (not built). The page shows frame 1's look
(`out/preview/tape-emu-*.png` are the emulated device frames).

## The pack (materials)

The tape packs are drawn at run time per pixel by `tp_pack` (`patch/tape.c`), the arithmetic being `pack_rgb` in `tools/tape_art.py` (the test's `py_pack` and the preview's `packs()` call it,
so the emulated frame and the preview are the payload to the bit). Visual target: `packs2` of the approved scratch mock (the pixels agree with its float version within 1 - 2 levels almost
everywhere, a few near the hub up to 36):

- base #22150E, highlight #6C4F38. `s = -dx - dy` (half pixels from the reel's centre); `u = s^2 << 15 / (dx^2 + dy^2)` is cos^2 of the angle from the upper-left / lower-right axis, 16 bits;
  `lobe = u^7` (four 16 bit multiplies, = |cos|^14), times 115 / 256 (0.45) where `s < 0`. No table; the sheen is static, the light does not turn with the reel. Where `s^2 < dx^2 + dy^2`
  (cos^2 < 1/2) the lobe is below 513 / 65536 and adds nothing, so the division and the multiplies are skipped there (identical pixels).
- Windings: `w = pk_wind[d & 31]` = 32 + 32 sin(2 pi d / 32) (`d` in 1/16 px: a 2 px period; a 32 byte rodata table, mirrored by `PK_WIND`); base x (236 + 26 w / 64) / 256 (0.92 .. 1.02),
  lobe x (179 + 77 w / 64) / 256 (0.70 .. 1.00).
- Edge: x 287 / 256 (1.12) from `R - 35` (r - 2.2 px), x 115 / 256 (0.45) from `R - 16` (r - 1 px), clamped at 255; the rim is the coverage blend as before (1 px).
- The old two arcs and the 3 px winding lines are gone; the hub radius no longer limits the windings. Cost (emulated instructions, whole `tp_tick`): a hub-only tick 279,639 before, 459,656 after
  (about +0.4 ms on the 70 ms tick: two 30 px squares); a pack redraw (`tp_reels(1)`, the radius changed) 2.43 M before, 2.95 M after. A pack is still redrawn only when a radius changes by 1/4 px.
  No new memory: the payload gained the 32 byte table, `.scratch` is unchanged.
