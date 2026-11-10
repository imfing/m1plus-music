# Cassette Mode

A fullscreen 480 × 320 cassette-style Now Playing page, opened from page 1 of the More sheet.
Tap the cassette to pause/resume; tap the top-left screw to close. It adds no hook or boot work
and owns one page timer. Art is generic, without brand names or logos. The visual references
are Sony's NW-A100/NW-ZX500 cassette screen and FiiO Tape mode.

Sources: `patch/tape.c`, `tools/tape_art.py`, `tools/pod_ui.py` (`build_tape_page`),
`tools/mod_icons.py`, and `TP_*` in `offsets.inc`. Tests: `test/pod/tape.py`; preview:
`tools/preview_tape.py`. Emulated frames are written to `out/preview/tape-emu-*.png`.
The release status records flashed builds; use the final checklist for validation of a new build.

## Themes and assets

Settings → Now Playing → Theme cycles Normal, Chrome and Metal. The order is
`tape_art.THEME_NAMES`; `/mnt/data/m1plus/cassette-theme` stores `0\n`, `1\n` or `2\n` atomically.
`tape_theme` accepts `1`/`2` with an optional newline and defaults to Normal for all other data.
A failed save changes neither file nor label. The Tape page reads the setting once at open.

Shared assets are `tape_top` and `tape_screw`. Each theme has `tape_shell_<theme>`,
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
  | `tape_shell_<theme>` | 320 x 480, opaque (RGBA, alpha 255: the decoder gives 32 bit pixels for it, as for every picture the payload loads), 217 KB | the cassette: shell, screws, label paper, band, ruled lines, the panel, the holes, the clear window, the direction arrow. **No text, no marks, no tape, no rings, no hubs** |
  | `tape_top` | 74 x 280, RGBA | the holes' gear rings and lips, the clear window's scale and bevel (what lies over the tape), by alpha extraction (drawn on black and on white at 3x) |
  | `tape_hubs_<theme>` | 30 x 720, RGBA | the reel hub in **24 frames, 5 degrees apart**: a pale translucent plastic ring with six teeth round a dark opening and a pale disc with a dark 3-spoke drive; the ring repeats every 60 degrees, the drive every 120, so the picture repeats every **120 degrees** and 24 frames close the loop seamlessly (angle modulo 120 / 5; `tp.ang` counts sixteenths modulo 1920); stacked, pre-rotated with the picture |
  | `tape_marks_<theme>` | 26 x 78, RGBA | the printed play mark, pause mark and repeat arrow, in the theme's band ink (white, Metal's gold) |
  | `tape_screw` | 26 x 26, RGBA | the close screw pressed: darker, its slot turned 45 degrees (the same in every theme) |

  The sizes are above (the rebuilt rootfs may not exceed stock size and the build refuses otherwise).
- **The reels** (`tp_reel_px`): per landscape pixel, the shell, then the **tape packs** (a disc of the pack's radius around each reel, seen only through the two holes and the clear window,
  integer distance from a table `sqrt(d2h) * 8` made at open: 1/16 px, an anti-aliased edge, a dark edge ring, 1 px winding lines every 3 px, the highlight arc in the upper left), then
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
  | artist, album | 40 / 70, 16 px; 40 / 89, 13 px (190 px room) | the playing track's tags |
  | elapsed, -remaining | right end 428, 89, 12 px | `get_playtimeandlength`, `m:ss  -m:ss` |
  | A, fine print | 58 / 146, 54 px bold; 40 / 206, 12 px | fixed per theme (`TYPE I NORMAL`, `TYPE II CHROME`, `TYPE IV METAL`; drawn once, in the theme's print colour, flat) |
  | status line | right end 428, 206, 12 px (11), 212 px room | below |

  The status line is `VOL 42 | FLAC | 21:07 | 60%`: the **volume** is the status bar's `label_volume` text, **read only, never set**; the **format** is the upper-case file extension of the
  playing track's path (`FLAC`, `MP3`, `WAV`, `M4A`; the track's record has no bitrate or bit depth we know of, so the mock's `FLAC 16/44.1` is not reachable: this is the one piece of
  information that source gives); the **clock** is `localtime` as `HH:MM` (24 h); the **battery** is read as the Pod does (`*system_bar` `0xa06f90` > `pgbar_battery` `value`, 20 % steps,
  `img_battery` = `bar_charge` while charging: a `+` before the number). It is set at 12 px if it fits 212 px (the advance + 1 px a glyph, the font's own), else 11 px, dropping the **clock
  first, then the format** (`tape_art.status_line`, the same function the mock and the test use). A missing status bar gives `VOL 0`.
- **Refresh only on change**: the timer looks at the track, the position, the play state, the repeat mode, the battery, the volume text and the clock minute each tick and redraws only what
  differs; the text itself is drawn by the next paint, not by the timer.

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
**Nothing here stops the stock screen-off**: the page sets no idle state, holds no wake lock and reads no input but its own touches; a repaint or a timer is not input, so the stock idle path is not reset by them (this is by construction, **not yet seen on the device**: it is on the checklist).

### Idle power

Following the other page timers (`pod_screen_lit()` in `patch/common.c`, the stock `backlight_status` byte, already pinned; no new pin): a 14 frames a second tick is not free (FiiO's reviewers note the same for Tape mode), so **while the screen is off `tp_tick` does no visual work** (no `tp_update`: no reels, no text, no invalidation, no player or status-bar reads) and `tp_want_ms` returns `POD_DARK_MS` (1 s), set in place with `timer_modify` (once, not again while dark). The first tick after the light is back runs `tp_update` and returns the interval to 70 ms playing / 500 ms paused; the reel step is capped by the usual 250 ms and the text compares with what it shows, so it catches up without a jump. A page opened with the screen off (`tp_first`) waits for the light with a 1 s one-shot before its first full draw. Lit and paused it idles at 2 ticks a second and repaints nothing when nothing changed. Tests: `test/pod/tape.py` (`life_tests`).

## Safety and fallbacks

- No hook, no patched word. `TAPE_PINS` (`tools/pod.py`) pins the stock words the page newly relies on (`widget_invalidate_force` passing its rectangle on, the rectangle's 16 bytes in widget
  coordinates); every other stock call is one the payload already pins (Cover Flow's glyph path, the Pod's timer, battery and quick clicks).
- A page that fails to open (no window, no view or label, a picture missing or of another size, no memory for the frame) frees what it made, goes back with `navigator_back` and returns -1; the
  More sheet, which closes only after the page is up (`pm_on_tape`), stays as it was.
- Hidden stays `visible=false` + `sensitive=false`; the only visible, sensitive widget is `tape_view`; the picture is painted, not widgets.

## Themes

The look is a **theme the user chooses**: **Settings > Now Playing > Theme: Normal (default), Chrome, Metal**, as FiiO's "Tape mode theme" (above). The same
cassette is shown for every track; a theme is a complete look (shell colour, label paper and print, band, hub ring), not a tape grade tied to the
music. More themes can be added later as data (`THEMES` in the mock).

| Theme | Shell | Label | Band | Hub |
| --- | --- | --- | --- | --- |
| Normal | smoky dark grey | off-white paper, dark ink | blue (tinted by the cover's tone) | white |
| Chrome | black-graphite | silver paper | red (tinted by the cover's tone) | silver |
| Metal | black | black label, gold print | dark with gold hairlines | gold |

Background only: Sony picks its tape from the codec and bitrate (9 real tapes: lossy up to 128 kbps CHF, up to 160 BHF, up to 256 AHF, up to
320 JHF; CD-quality FLAC / ALAC / APE UCX, AIFF UCX-S, WAV DUAD ferrichrome; hi-res PCM METAL; DSD Metal Master). We chose a fixed user theme instead;
Sony's mapping stays the reference should a format-driven option ever be wanted. Sources: av.watch.impress.co.jp/docs/review/review/1222109.html,
news.mynavi.jp/article/20191016-910000/, the FiiO M21 manual (Tape mode, Settings > Tape mode theme), the FIIO_official post on X about Cassette Mode.

## The cassette (follows a real one and Sony's screen turned sideways)

- **Symmetry:** everything static is symmetric about x 240 (the cassette 5 .. 475, the label 37 .. 443 with 32 px of shell each side, the panel, the window, the reels 132 / 348, the screws 24 / 456, the bottom section and its holes, the knurl mask); `test/pod/tape.py` `symmetry_tests` checks the constants and the shell picture. V2.1oXTR had the label at 30 .. 436 (25 px left, 39 right); the text, marks, arrow and the A moved 7 px with it. The only intended asymmetries are the light (the drop shadow falls right and down, a hole's highlight and the bevels are lit from the top left).
- **Shell (material pass, after Sony's METALLIC 46 as the reference):** a matte moulded plastic with a **crisp knurl of raised squares on a 4 px pitch, drawn at 1:1 on the pixel grid** (`knurl`: a 3 x 3 square with a 1 px light top and left edge, a 1 px dark bottom and right edge and a 1 px groove; never downsampled from 3x, which smeared the old one), a **smooth flat rim band** inside the outer edge, fine deterministic grain, a 1.8 px bevel, a moulded step, one soft light from the top left. The knurl is masked off the label, the screws and the holes. No brand mark; the moulded word on the side rim was left out (nothing is better than a generic one the font cannot carry at build time).
- **Screws:** four recessed Phillips screws in the corners and one at the bottom centre: a dark countersunk ring, a metal head, a cross slot, a specular spot.
- **Label:** paper (faint grain) on a raised frame, covering most of the upper face. Index lines with the title (22 px), artist and album written on them,
  elapsed and -remaining in small type on the album line, plain paper at the top right (the title may use the full width), a colour band across the middle with a big "A",
  below it the fine print (type and grade, 12 px), the direction arrow (**foil**: a metallic light-to-dark gradient of the theme's print colour, a faint diagonal highlight, very fine grain, sharp edge; the Metal band's hairlines too) and a status line.
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
- **Hub, packs, window:** `hub_sprite(angle, colour)` is one function of the angle, quantised to 24 frames (5 degree steps, the 120 degree cycle above). The tape pack is near-black brown (#24160E, windings a shade lighter) with a subtle circular sheen: two soft lobes on the circle, upper left (stronger) and lower right (`PK_LIGHT`, `PK_LIGHT2`). The centre window is smoked glass: a dark gradient (`#3E4044` to `#141518`) in `tape_shell`, and in `tape_top` a soft diagonal reflection, an inner shadow at the frame edge and a fine white scale (a 1 px centre line and ticks on whole pixels).

## Frames (the mock)

1 Normal, near the start, playing; 2 Chrome, mid-track, repeat on; 3 Metal, near the end, paused; 4 Chrome with the tap control strip (not built). The page shows frame 1's look
(`out/preview/tape-emu-*.png` are the emulated device frames).

## Device checklist

Open Now Playing on a playing track, More (page 1), tap **Cassette Mode**: the sheet closes and the cassette appears, readable when the player is held with its **right edge up**.
- Is the sheet's top edge right now on both pages (page 1 five rows with its own 250 px glass, page 2 four rows, 200 px, rounded corners and rim)?
- Is the picture the right way up (title at the top, the label's text readable, not mirrored)? If it is upside down, the rotation sign is wrong (`tp_pix` / the touch map).
- Do the reels turn smoothly while playing (about 14 frames a second; the left one slower at the start, the right one faster) and **stop** when paused? Any shimmer, tearing or lag? Does the tape pack grow on the right and shrink on the left as the track plays?
- Is the text readable rotated: title 22 px, artist 16, album 13, times 12, status 12 (11)? Any clipped descender or leftover glyph when the track changes?
- Tap the middle: pause / play, with the pause bars shown at once? Tap the top left screw: does it darken and turn while held, and close the page on release? Is a swipe from the top edge still opening
  the control centre (pull-down) with the page open, playing and paused? Does a long drag do nothing? Is 14 px too easy / too hard for a tap, is the 50 px screw area right?
- Material: is the knurl crisp (4 px cells, no moire), the foil arrow and hairlines metallic, the smoked window, the pale hubs with their 3-spoke drive, and the reels still smooth at 24 frames? Does the pack's sheen look right?
- Settings > Now Playing > Theme: tap cycles Normal, Chrome, Metal; reopen the page: the new look (shell, hubs, ink, fine print)? It survives a reboot?
- Battery number, `+` while charging, volume (change it with the keys: the line follows within half a second while paused), the format (file extension), the clock?
- Does the screen still sleep after the usual idle time with the page open (playing and paused)? Does it wake and keep going, the reels on the right turn and the text current at once (no jump)? Battery: leave it playing with the screen off for an hour (screen-off ticks are 1 s and draw nothing) and compare the drain with Now Playing; is the lit 70 ms tick warm?
- Back to Now Playing, More again, Tape again: opens every time, no leaked state. Does the page keep playing through a track change and a phone-style lock / unlock?
Open questions: the cost of the 70 ms tick on battery (relax `TP_PLAY_MS` to 100 if warm); whether to drop 5 degree frames for fewer redraws; whether 24 h time is wanted.
