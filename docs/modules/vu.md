# VU Meter Mode

**Sources:** `patch/peq_player.c` and `patch/vu.c` (the level tap), `patch/vu.h` (the shared level record),
`patch/vupage.c` (the page), `tools/vu_art.py` (the art: drawing code shared by the preview and the build,
the reference needle), `tools/pod_ui.py` (`build_vu_page`), `VU_*` in `offsets.inc`.

A fullscreen portrait Now Playing page: two needle VU meters (left above right) that follow the playing
audio. Opened from the More sheet's Display Mode page (**VU Meter Mode**, between Vinyl Mode and Lyrics
Mode; [playmore](playmore.md)) or by the Idle Display timer (**VU Meter**; [bigcover](bigcover.md)). No
setting, no hook, no pinned stock word beyond the player tap's.

## Look

Cream dials in a brushed aluminium faceplate, lit softly by three bulbs above, a black needle with a
shadow, a PEAK lamp per meter, a small black hood per dial, and the Vinyl page's
chevron, status line, text lines and round keys (its 'white' key theme). The dials carry no mirror arc, no
percent scale, no dust and no screws. **0 VU is an automatic reference level** that follows the programme (below), starting at -12 dBFS rms.

## The level tap

- In `play()` of `patch/peq_player.c`, after the stages, so the meters show what is sent to the output
  (after EQ, Mono, Crossfeed; before the DAC's volume, which is hardware). It is read-only: it never
  changes a sample, and playback with everything off stays bit-exact.
- It also measures in `pass_native` (EQ, Mono and Crossfeed all off), where blocks arrive in the track's
  native integer format and are passed through untouched.
- Per block and channel: peak (max |x|) and the sum of squares, normalised to full scale 1.0. Mono tracks:
  both meters show the one channel. DSD and special formats: no levels (the page parks the needles).
- **Only while watched:** the mark is the file `VU_FILE` (`/tmp/m1plus-vu`). The player measures only
  while it exists and starts with `VU_MAGIC`; the cost without it is one failed `fopen` per block. The
  page creates it with just the 8 magic bytes while it is in front and the screen is lit, and `unlink`s
  it when the screen goes dark, another window covers it or it closes.
- **The record:** the same file (tmpfs, never fsynced). The player rewrites it whole, in place, with one
  `fwrite` per block (open, check magic, seek, write, close). `patch/vu.h` is shared like
  `patch/stereo.h`; the player side is `patch/vu.c`.
- **Timing:** each entry carries `due_us`, the CLOCK_MONOTONIC time its first frame is audible: the time
  the block was filtered plus the audio output's delay then. The delay is read from hciplayer's own
  output: `mpctx->audio_out` (`mpctx + 8`) `->get_delay` (+0x1c), a `float ()` returning seconds queued,
  the same call stock's `playing_audio_pts` (`0x4300f4`) makes. It is called only while watched, from the
  playback thread that normally calls it. No hciplayer word is edited; seven words are pinned (`PINS`,
  `0x42686c`..`0x43018c`); `fseek` and `fwrite` join the `LIBC` table through slots hciplayer already
  imports. Not included: bytes the decoder holds ahead of the output (under one block); the filter chain
  after ours.
- **Stopped or paused:** nothing is written, so `seq` and `now_us` stand still. The page parks at once
  when the player is not playing.

### The record (`patch/vu.h`)

`vu_record`, 2096 bytes, little endian: `magic[8]`, `seq` (+1 per write), `rate` (Hz of the stream
playing, 0: no levels), `channels` (1 or 2), `count` (0..64), `head` (newest entry), `pad`, `now_us`
(CLOCK_MONOTONIC us of the write; 8-aligned, offset 32), `ring[64]` (offset 40), `seq_end`, `pad2`.
`vu_entry`, 32 bytes: `due_us` (8), `dur_us`, `frames`, `peak[2]` (float, max |x|), `sumsq[2]` (float, sum
of x*x; rms = `sqrt(sumsq / frames)`). Levels are full scale 1.0 (above: over; NaN and infinity count as
0). Mono streams: both channels equal; more than two: the first two.

- Blocks shorter than 10 ms join the entry before them (when within 20 ms of its end), so the 64 entries
  cover at least 640 ms and normally seconds. A gap or a new stream opens a new entry.
- The ring continues across tracks (it lives in the payload's `.data`): the end of a track stays until it
  has played. A stream with no levels (DSD, a special format, a rate out of range) writes
  `rate 0 / channels 0` and no entries; the kill switch leaves the file alone.
- Measured: float blocks after the stages; the native pass-through for little-endian float, signed 16, 24
  and 32 bit and unsigned 8 bit PCM. Other formats give no levels.
- **Reading:** open `VU_FILE` and take the whole record; keep the read when `seq == seq_end`, else read
  again. With `t` = `clock_gettime(CLOCK_MONOTONIC)` in us, the audible block is the newest entry with
  `due_us <= t`; it is current while `t < due_us + dur_us`, else there is silence or no new blocks
  (compare `now_us` and `seq` between reads to tell a stall from a quiet passage: a quiet passage still
  writes entries). `rate == 0`: park.

## The art (`tools/vu_art.py`)

Drawn at 3x and reduced; `images()` makes the pictures, `tools/mod_icons.py` installs them
(`vu_art.NAMES`, `png_pack`: palette with tRNS where the colours fit, else RGBA).

| Picture | Holds |
| --- | --- |
| `vu_base` 320 x 480 opaque | faceplate, both dials without needles, hoods, unlit PEAK lamps, the dial print, keys at rest (play glyph), chevron |
| `vu_hood` 84 x 18 | the hood, alpha its mask; the same over each dial; drawn over the needle's root |
| `vu_lamp` 33 x 31 | the lit PEAK lamp and its glow (premultiplied-reduced alpha); the same over each dial |
| `vu_keys` 286 x 58 | the key band cells, same `KEY_CELLS` / `KEY_COLS` / `BAND_Y` as `vinyl_keys`: play with the pause glyph (shown while playing), play and previous / next pressed |

- **Print:** numerals, -, +, VU, LEFT, RIGHT, PEAK are drawn at 1x on the reduced base with Jost
  (OFL, `assets/vu/`: `Jost-Medium-vu.ttf`, and `Jost-Bold-vu.ttf` for the major numerals, VU,
  LEFT / RIGHT, PEAK; the wght 500 and 700 instances of the variable font cut to the print's
  characters, used at build time only and not installed) through `tools/stb_raster.py`, AWTK's own rasteriser: integer px, no
  system font.
- **Text labels** are the page's, not in the base: `vu_art.TEXT` (title 22 px, artist 15, times 12,
  status 10; x, line middle y, width), colours of the Vinyl 'white' theme. The title is drawn once: in the
  bold `lyrics` face when all its code points are in `lyrics.ttf`, else in the default font
  (`ly_title_face`, [vinyl](vinyl.md) "Title face"); `text` draws it that way.
- **Layout constants** (all in `vu_art.py`): `BOXES`, `WINDOWS` (286 x 144 dials at (17, 31) and (17,
  193): what a needle is clipped to), `PIVOTS` (160, 211) and (160, 373), `R0` / `R1` (20 / 151: the
  radius range drawn), `HW_ROOT` / `HW_TIP` (half widths 1.1 / 0.5), `SHADOW_*` (offset (4, 5), sigma 1.6,
  alpha 120), `SWEEP` 46 degrees, `REST` (-48.5 degrees), `HOOD_RECT` / `HOOD_AT`, `LAMP_RECT` /
  `LAMP_AT` (meter 1 is `METER_DY` 162 lower), `KEYS`, `KEY_Y`, `CHEVRON`, `CLOSE_RECT` (the Vinyl
  page's).
- **Law:** angle = -SWEEP + min(1.03, `10^(VU/20) / 10^(3/20)`) * 2 SWEEP, -20 .. +3 VU (`frac`, `angle`).
- **Reference needle:** `draw_needle` (analytic coverage per pixel, an erf-blurred shadow offset by (4,
  5), clipped to the window; the geometry is in the module docstring), `needle_rect(m, a)` the dirty
  rectangle of one angle, `move_rect(m, a0, a1)` the union for a move. `compose(f)` is the page as the
  build composes it: base, pause glyph while playing, per meter the lit lamp, the needle, then the hood;
  `design` adds the text.

## The page (`patch/vupage.c`)

The Vinyl page's structure (`vp_*` for `vn_*`): page asset `m1plus_vu` (`pod_pages.VU_PAGE`,
`build_vu_page`: the window, `vu_view`, labels `vu_title`, `vu_artist`, `vu_times`,
`vu_status` from `vu_art.TEXT`, window background the faceplate colour), five bitmaps (frame, `vu_base`,
`vu_keys`, `vu_hood`, `vu_lamp`), one view that takes DOWN, UP and ABORT and paints the frame, one timer
(`vp_first` after `VN_FIRST_MS`, then `vp_tick` at `VU_TICK_MS` (33 ms, 30 fps) while anything moves (the player plays, a needle is not at its target or at rest, a lamp is lit or fading), `VN_IDLE_MS` at rest, `POD_DARK_MS` with
the screen off and then nothing is read or drawn). The Vinyl page's `VN_PLAY_MS` is not used. Key band, chevron rectangle, tap distance,
`VN_DT_MAX` and the key cells are the Vinyl page's `VN_*`. The page is in `PAGE_ORDER` just before
`m1plus_general`; no row holds its index: the payload opens it by name.

- **Entries.** `vupage_open()` and `vupage_open_idle()` (`patch/entries.h`) return 0 once the page is up
  (or already open) and -1 when it could not open. The Display Mode row calls the first (the page first,
  then the sheet closes, as Vinyl); the Idle Display dispatcher calls the second.
- **The mark.** `vp_watch` keeps `VU_FILE` (holding `VU_MAGIC`, `vp_mark`) in step with "in front and lit", acting only on a change: open, `vp_first`, each `vp_tick` and the
  window's foreground event call it; a dark tick or the background event `unlink`s it (a window such as the lock screen
  can cover the page as the screen goes dark, and no tick runs behind it), the first lit tick creates it
  again before `vp_update`; destroy `unlink`s it. A mark that cannot be created is tried again by the next
  call. A new mark holds only the magic, which reads as no
  signal, so the needles settle towards rest until the player writes a record.
  `vupage_boot` unlinks a stale one and is called from `home_boot` (the existing Home init hook).
- **Reading.** Each tick, while the player plays, `fopen`/`fread`/`fclose` the whole record (3 tries
  until `seq == seq_end`; all torn: the last levels stay). A file shorter than a record, another magic or
  no file (the kill switch leaves only the mark) is no signal. The levels are those of the entries
  audible since the last tick (at most 100 ms): `due_us <= now` and `due_us + dur_us` after the
  window's start, on `CLOCK_MONOTONIC` (`clock_gettime(1)`, imported by demo, in `LIBC`). Their sums of
  squares and frames are added, so a tick takes the rms of everything that played since the last one;
  the peak is the largest. No signal also when `rate == 0`, when `now_us` is older than `VU_STALL_MS`
  (500 ms: no new block), and at once when the player is not playing (`mclGetPlayStatus() != 2`). No
  signal: every needle's target is `REST`.
- **RMS convention.** rms = `sqrt(sumsq / frames)` per channel, on the player's output. A full-scale
  sine is -3 dBFS rms = +11 VU, so it pegs the needle at its stop (3 % past +3 VU). The deflection
  follows the voltage, so the needle angle is linear in the rms: `-SWEEP + min(1.03, rms / full) * 2
  SWEEP`, `full` the rms at +3 VU (`vu_art.angle` with 0 VU at the reference). A silent block gives
  `-SWEEP` (-46 degrees), not the parked rest (-48.5).
- **Automatic level** (`vp_level`, state `vp_lv`: `lt`, `peg`, `fast`). The reference `ref` (dBFS rms that
  reads 0 VU) is one value for both channels, so the L/R relation is kept. It follows the programme so
  that the long-term average sits 3 dB below 0 VU: `ref = lt + 3 dB`, `lt` the slow average of the
  louder channel's rms power. It is kept in the power domain (`ref` power = `lt * VP_G3`, `full` =
  `sqrt(lt) * VP_G3`; no log or pow). `lt` moves only on a look that has a signal above `VP_FLOOR`
  (power 1e-5, -50 dBFS rms): silence, a pause or a stopped player leave it alone. It follows the
  louder channel's power with `VP_TAU_SLOW` (12 s), up and down; once the needle has read above +3 VU
  for `VP_PEG_MS` (1 s) it rises with `VP_TAU_FAST` (2 s) until the level is under 0 VU again, so a
  loud track leaves the stop within a couple of seconds (about 1 s when it was slightly loud, 1.3 s at
  -4 dBFS rms). `lt` is clamped to `VP_LT_MIN` .. `VP_LT_MAX`, that is `ref` -24 .. -6 dBFS (a
  clamped `lt` cannot wind up: a quiet passage after a loud one answers at once). Start value
  `VP_LT0` (`ref` -12 dBFS) when the page opens; kept across track changes (the next track adapts from
  there) and while the page is open; reset only by the next open. The look reads the reference as it
  was before it and learns from the look after it. Steady signals settle (measured in `auto_tests`):
  -10 dBFS rms within 1 dB of -3 VU at 14.5 s and at -3 VU after a minute; -20 dBFS rms passes -4 VU
  at 25 s and reaches -3 VU; -8 dBFS rms leaves the stop at 0.8 s and ends at -2 VU, `ref` being at
  its -6 ceiling; a +6 dB burst of half a second in a settled track swings the needle about 6 dB and
  back.
- **Ballistics.** Second order, `x'' = w^2 (target - x) - 2 z w x'` with `VP_OMEGA` 14.05 and `VP_ZETA`
  0.826, integrated in 1 ms steps by the real elapsed time (capped at `VN_DT_MAX`): 99 % of a step at
  about 300 ms, 0.9 % overshoot. A needle that has all but arrived (error < 2e-5 rad, speed < 1e-4) lands
  on the target and stops, so the tail never decays into denormals (they trap on the MIPS FPU). A needle never goes below `REST`: the step stops it there with speed 0.
  **Kick on open:** `vupage_open` (and so `vupage_open_idle`) starts each needle at `REST` with the speed `VP_KICK` (13.62 rad/s), and the same ballistics do the rest, like a meter that is powered up. With the target at `REST` the swing is `v0 / wd * exp(-z w t) sin(wd t)`, `wd` = 7.92: it peaks at 76 ms, 23.1 degrees above `REST`, the -10 VU mark (-25.4 degrees), crosses `REST` again at 397 ms (where the stop holds it) and is drawn still then. With a signal the kick only joins the rise to the level.
  Doubles, `sin`, `cos` and `sqrt` come from the libc imports `peq.c` already uses.
- **PEAK lamp.** Lit when an entry's peak is at least `ref` + 8 dB (8 dB above 0 VU: `peak^2 >= lt *
  VP_G11`), and always at `VP_PEAK_FS` (-0.1 dBFS, digital full scale); stays fully lit `VU_HOLD_MS` (400 ms) after the
  last such entry, each peak restarting the hold, then fades out over `VU_GLOW_MS` (180 ms), linear in alpha (`lvl` 255 .. 0, `vu_lamp` composited with its alpha scaled); a peak during the fade relights it fully at once. The lamp rectangle is redrawn only when `lvl` changes, and at the end of the fade it is `vu_base` exactly. With `ref` at its -6 ceiling the relative rule is +2
  dBFS, out of reach: only full scale lights the lamp there. The numbers come from running the level
  model over four real tracks in 50 ms blocks: + 14 dB with a 1 s hold lit the lamp 0 to 2 % of the time
  on three of them (under one flash a minute); + 8 dB with 400 ms lights it 7 to 30 % (3 to 20 flashes a
  minute), + 6 dB over 60 %.
- **Needle drawing** (`vp_needle`, ported from `vu_art.draw_needle`): the same analytic coverage; the
  shadow's gaussian edge from a 129-entry table (`vp_phi_t`), 16.16 fixed point, doubles for the rest;
  only the columns of a row the needle or its shadow can reach are visited. `vp_rect` is `needle_rect`.
  A meter whose needle moved by `VP_SEE` (0.0008 rad, 0.12 px at the tip) or came to rest, or whose lamp
  level changed, restores its rectangle (old and new needle, the lamp's) from `vu_base`, draws the lamp when
  lit, the needle, then `vu_hood` over what each touches, and invalidates that rectangle (one per
  meter, never the union of both). The first look also draws the hoods, so the frame is always
  `vu_art.compose`.
- **Keys, text, taps** as the Vinyl page: the chevron closes; the keys play / pause (pause glyph from
  `vu_keys` while playing), previous, next, drawn pressed; a tap on the page above the keys plays /
  pauses, or closes the page when it was opened by `vupage_open_idle`; a drag, an abort or leaving the
  touch's target does nothing; no MOVE handler, no grab.
- **Cost budget:** 1.5 M instructions per 33 ms tick (the Vinyl page's is 2.3 M per 50 ms). Both needles
  sweeping with a lamp changing 1.39 M at the worst (1.26 M typical), a tick with nothing to draw 3 k, the
  first full draw 1.1 M. The page's pixels match `vu_art.compose` within 2 per channel.

## Wiring

- **Display Mode row** (`pod_vu`, the seventeenth row of the More sheet's asset, label key "VU Meter
  Mode", glyph `pod_ic_vu` = Lucide `gauge`): handler `pm_on_vu` in `patch/playmore.c`, shown fourth of
  the Display Mode page's five rows (250 px, `pc_sheet5`).
- **Idle Display:** picker row "VU Meter" (`ACT_IDLESET` arg 5); the saved value in
  `nowplaying-idle` is `4\n`; `bc_timed_open` calls `vupage_open_idle`. No new setting file or action
  id.
- **Strings:** "VU Meter Mode" (row and page title) and "VU Meter" (picker, value) in `tools/pod_i18n.py`,
  all 13 languages.
