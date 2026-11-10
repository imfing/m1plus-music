# Vinyl Mode

A fullscreen portrait turntable Now Playing page, opened from page 1 of the More sheet (the row under Cassette Mode). The record lies off the left edge,
its label is the playing track's cover and turns at 33 1/3 rpm while playing; a tonearm on a raised plate rests on the groove (outer to inner as the track
plays) and is parked straight down beside the record when paused. Three round keys at the bottom right: previous, play / pause, next. Tap the record to pause
or resume; tap the top-left chevron to close. No hook, no boot work, one page timer. Neutral greys only; no brand marks.

Sources: `patch/vinyl.c`, `tools/vinyl_art.py` (the design's drawing code and the installed layers), `tools/pod_ui.py` (`build_vinyl_page`),
`tools/mod_icons.py` (installs the pictures and the row glyph `pod_ic_vinyl`, `assets/icons/custom/turntable.svg`), and `VN_*` in `offsets.inc`. Tests:
`test/pod/vinyl.py`; preview: `tools/preview_vinyl.py` (frames J1 playing / J2 paused, the approved design). Emulated frames are written to
`out/preview/vinyl-emu-*.png`, each next to the design drawn at the same state (`vinyl-emu-*-design.png`).

## The page

- **The window** is `fullscreen = true` (480 px, no status bar), one view `vinyl_view` (320 x 480: the touch target, painted by the payload in its own
  `EVT_AFTER_PAINT`) and the text as **ordinary AWTK labels** over it: `vn_title` (22 px, #F4F4F6) and its twin `vn_title2` one pixel right (the weight of the
  mock's title), `vn_artist` (15 px), `vn_times` (12 px, `m:ss  -m:ss`), `vn_status` (10 px, `VOL 42 | FLAC | 21:07`). They are insensitive
  `hscroll_label`s that never scroll and end in an ellipsis (the mini bar's), placed from `vinyl_art.TEXT` (`label_box`). Portrait, so no rotated-text path
  (unlike Cassette Mode). `label_title` (hidden) carries the name for the i18n and asset tests.
- **The frame** is a 320 x 480 RGBA bitmap the page owns (614 KB, freed on destroy), composed from the layers below; the paint blits it 1:1 and the timer
  invalidates only what changed (`widget_invalidate_force` with a rectangle, pinned for the Tape page).

| Picture | Size | Holds |
| --- | --- | --- |
| `vinyl_base` | 320 x 480, opaque | the plinth (grey 0x46, a gentle vertical gradient; no grain: the page adds it, see "Grain"), the arm's pill plate and base, the record (grooves, smooth gaps, a weak static sheen 0.22, its shadow), the keys at rest, the chevron |
| `vinyl_lid` | 160 x 160 RGBA at (16, 116) | over the turning label, fixed: the pressed step at its edge, a soft paper gloss, the white rim, the spindle |
| `vinyl_arm` | 353 x 59 RGBA | the arm pointing +x, its pivot at (73, 22) of the picture (a pixel corner); loaded premultiplied |
| `vinyl_armsh` | 353 x 59 | its shadow: the arm's alpha blurred, alpha <= 150, drawn 5 px right and 7 px down of the arm |
| `vinyl_cap` | 32 x 32 RGBA at (262, 56) | the gimbal cap over the pivot (round: it does not turn) |
| `vinyl_keys` | 286 x 58, opaque | the key band (rows 420 .. 478) cut in cells: the play key at rest and pressed with the play or pause glyph (x 0, 46, 92, 138), previous pressed (184), next pressed (237) |
| `vinyl_label` | 152 x 152, opaque | the label of a track without a cover: light grey paper |
| `vinyl_grain` | 320 x 480 RGBA, Graphite only | the grain's weight in the red channel: 255 the plinth, 0 the record, plate, arm base, keys and chevron (soft at their edges) |
| `vinyl_rec` | 258 x 324 RGBA at (0, 34) | the record map t of the Cover record in the red channel, 0 where the base stays (see "Record colours") |

Installed sizes (Graphite's names; Snow's `_white` are 62 KB base, 9 KB lid, 3 KB arm, 2 KB shadow, 2 KB cap, 8 KB keys): base 58 KB, lid 10 KB, arm 3 KB, armsh 2 KB, cap 2 KB, keys 13 KB, `vinyl_grain` 2.4 KB, `vinyl_label` 2.6 KB, `vinyl_rec` 28 KB; 208 KB for the 15 pictures of both themes.

**Grain.** Film grain is noise no PNG packs (it was 66 KB of Graphite's base), so the page adds it once, when it loads the base (`vn_grain`): each pixel where `vinyl_grain` weighs is soft-light blended with a hash of its place (amplitude `VN_GRAIN` 6, the sum of three hash bytes: gaussian-like), by the weight, all integer (`vinyl_art.grain_apply`, `grain_n`, `soft_light`; the test model grains the installed base the same way). The soft-light values are a 37 x 256 table in `.scratch` (9.5 KB), made at the first grain. The key cells in `vinyl_keys` are cut from the grained frame, so they match. Snow has no grain (amplitude 0: no `vinyl_grain`, no pass). The test prints the sizes and the build output the rootfs headroom.

**Encoding.** `tools/png_pack.py` writes the Vinyl PNGs (`mod_icons.py --generate` and `vinyl_art.py` use it for these names only): pure Python, each picture the smallest of RGBA or, when it has at most 256 colours (`vinyl_label`, `vinyl_rec`, both shadows), an 8 bit palette picture **with a tRNS chunk** (stb_image gives a palette picture four channels only when tRNS is there, which the payload's `vn_load` / `vn_recolour` need; stock ships such pictures, `scover_wait*`), over every filter plan and two zlib strategies. The pictures of few colours want no row filter (deflate repeats whole pixels). Every picture decodes to the same RGBA pixels as the plain `optimize=True` PNG it replaced (the packer asserts it, the test compares the pixels). Not done: Zopfli-class deflate (pinned `pyoxipng`) would save a few percent more; grey, RGB or LA pictures (the loader would give 1, 3 or 2 channels, the payload reads 4); cropping margins (the arm is 3 KB, the lid 10 KB: little to gain); sharing a layer between the themes (no layer is identical).

- **Composition** (`vn_compose`, per pixel of a rectangle above the key band): the base; inside radius 77 of the record's centre (96, 196) the label,
  **inverse-mapped** through the label's turn (fixed point: sines from a 91 entry table, 1/16384, angles in 1/16 degree), bilinear over the 152 px picture;
  the lid by its alpha; the arm's shadow (black by its alpha) and the arm (premultiplied over), both sampled bilinear through the arm's turn about the pivot
  (276, 70); the cap. The keys are copied cell by cell (`vn_key`). `test/pod/vinyl.py` has the same arithmetic in python and compares whole frames pixel for
  pixel.
- **The label** is the album's cached cover (`/mnt/mmc/.m1plus/covers/<key>-168.jpg`, the album page's and the mini bar's, decoded with `cc_decode` box
  reduced to 152 px), else the playing track's `/tmp` cover once demo has written it (`np_cover_file`, `np_file_key`; looked at again every 500 ms,
  8 times, after a track change, as the mini bar does), else `vinyl_label`. The grooves and the sheen are static (the light does not turn with the record), so
  only the label's 155 px square is composed while it turns.
- **The record** turns clockwise at 33 1/3 rpm (200 degrees a second, `VN_SPEED`) while playing, speeding up over `VN_SPINUP_MS` (700 ms) and slowing
  to a stop over `VN_SPINDOWN_MS` (2 s); a tick at full speed turns it 10 degrees. Paused: it stands still.
- **The arm**: playing, the stylus on the groove at the track's fraction (`vn_groove`, 33 turns from the outer groove to the inner one, made by
  `vinyl_art.groove_table16` from the design's geometry and compared by the test); paused, it stays on the groove until the record has stopped, then parks straight down (`VN_PARK`), so its swing never shares a tick with the label's
  and comes well after stock's pause stall; nothing playing, parked. It is
  redrawn when its turn changes by a quarter degree (on a 4 minute track every 2 to 3 s); a change of more than a degree (play, pause, a new track, next from pause) swings
  it there, eased in and out (smoothstep) over `VN_SWING_MS` (300 ms) + 1 ms a 1/16 degree (park to the outer groove about 0.7 s), on the page's capped clock, so a
  stall holds the swing instead of jumping it; a target that moves a little on the way is followed, one that jumps starts a new swing from where the arm is
  (`vn_arm_next`). Each redraw composes the rows the old and new arm cross.
- **The text** is set only when it changes: the title (the file name without one; `Not Playing` with no track), the artist, the times each second, the
  status line from the status bar's volume (read only, as the Tape page does), the file extension and the clock (`HH:MM`). No status bar: `VOL 0`. No battery: the status bar only has it in 20 % steps, which reads as false precision.
  At 10 px the widest line fits the 200 px label (test), so nothing is dropped. The status colour is #BCBCC2 (the mock's #ACACB2 is 4.2:1 on the plinth; the
  build's contrast scan wants 4.5:1).

## Record colours

Settings > Now Playing > Vinyl Mode > **Record** (a value row opening the picker `m1plus_vinylrec`, a check on the chosen row, "Applies the next time Vinyl Mode opens."):
**Black** (default, the installed look) or **Cover** (the record tinted from the playing track's cover; black for a grey cover or none). Saved as `0` or `1` (optional
newline; anything else or no file is Black) in `/mnt/data/m1plus/vinyl-record` by `vinyl_record_set` (atomic, as the Cassette Theme); the page reads it once when it opens
(`vinyl_record`). `vinyl_art.RECORD_NAMES` is the order. Red, Smoke and Clear were mocked and device-tried, then dropped: no code, strings or tables of them remain. Nothing
changed for Black: `vinyl_base` is pixel for pixel what V2.1qD installed, `vinyl_rec` is not even loaded, and the page costs what it did.

- **The picture.** `vinyl_rec` (258 x 324 at (0, 34), RGBA, 39 KB) holds one 8 bit map t in its red channel: the record outside the label, its grooves, track gaps, a slightly
  darker rim (no bead: a bright bead read as a white outline on the device) and a weak static sheen baked into a luma (`SHEEN_COVER` 0.30, `GLOW_COVER` 0.06: the highlight
  goes only a little lighter than the tint); 0 where the base stays. It carries no plinth (the first design did, 47 KB, and would have needed one a theme): the record is opaque,
  and the rim's anti-aliasing uses the base itself.
- **The colour.** Five stops (r, g, b) at t = 0, 118, 190, 235, 255 (`tint_stops`: the tint x 225/256, 77/256 of that in the troughs, lifted by 26, 51 and 72 of 256 towards white at
  t = 190, 235, 255) made into a 256 entry table (`vn_ramp`, `ramp_table`: piecewise linear, rounded half up; 1 KB of `.scratch`). Inside the rim a pixel is the table's colour. A
  pixel the disc covers only in part (coverage from an integer square root, 1/8 pixel) is the base's plus the colour's difference from the black record's rim grey
  (`VN_REC_K` 15) by the coverage: the base already holds the plinth and the record's shadow there, so the edge blends into whatever the theme is. The base's rim pixels
  (about 1020) are kept at the first recolour (`vr.rim`, scan order, 6 KB of `.scratch`, `vn.rim_saved`) and every later recolour blends from those, never from the rim a previous tint left
  in `vn.base` (a track change from one tint to another used to carry the old rim over; the test `cover_change_tests` compares every change with a fresh compose, per theme).
- **Where it runs.** `vn_recolour` composes the record into `vn.base`, which is the page's own copy (`vn_load` makes one; the image manager's bitmap is never written), at the
  first look and whenever the cover changes (`vn_retint`), then `vn_compose` redraws the record's box of the frame. Every later look reads that base exactly as before: a
  playing tick costs what Black's does. `vinyl_rec` is decoded, read and freed at once (no bitmap kept; 334 KB transient). A `vinyl_rec` that will not load or has another size
  leaves the page Black.
- **Cover.** `vn_tint` runs when the label's cover changes (a new track, and when demo's /tmp cover arrives): a 16 x 16 grid of cell means of the decoded 152 px label cover; the
  chroma-weighted mean of the cells whose chroma (max - min) is at least the grid's mean; saturation clamped to 170 .. 235, value to 125 .. 190, the hue kept; a mean chroma
  under 24 is grey: black. The same tint as the record already has changes nothing (a new track of the same album); a grey or missing cover puts the installed black
  record back from a fresh decode of `vinyl_base` (the box's rows; a 614 KB transient). `vinyl_art.cover_tint_px` and `tint_stops` are the python mirror (the mock's float
  `cover_tint` is within a few levels).
- **Cost** (emulation, `test/pod/vinyl.py` `record_tests`, `cover_record_tests`, budgets enforced): a playing tick with Cover 2.21 M instructions, exactly Black's. The first
  look with Cover about 1.9 M more than Black's once (budget 6 M). A track change with a new tint about 12.4 M once, from black or from another tint (a Black record's is 5.5 M: the cover decode, the new text and
  label), to a grey cover about 16.4 M (the black restore decodes `vinyl_base` and writes back only the disc: inside the rim from it, the rim the pixels `vn_recolour` saved; the plinth keeps its grain, nothing is grained again), to a track of the same tint 5.9 M, as Black's (budget 18 M). The frames are the python model
  (`rec_base`) pixel for pixel and within a few levels of the mock.
- **Memory.** Nothing kept beyond the 1 KB table, the 6 KB of saved rim and the 15 byte stops; transient 334 KB (`vinyl_rec`), 614 KB for the restore to black (and the decoded `vinyl_grain` while it grains).

## Themes (the plinth)

Settings > Now Playing > Vinyl Mode > **Base**: **Graphite** (default, the installed look) or **Snow** (a
matte off-white plinth, silver arm, grey keys, dark text). A value row opening the picker `m1plus_vinyltheme` (a check on the chosen row, "Applies the next time Vinyl Mode opens.");
saved as `0` or `1` (optional newline; only `1` is Snow, anything else or no file is Graphite) in `/mnt/data/m1plus/vinyl-base` (`vinyl_theme`, `vinyl_theme_set`), read once when the page opens.
The designs are `vinyl_art.THEMES` (selected by `use(theme)`; the mocks are `tools/preview_vinyl_themes.py`).

- **Pictures.** A theme changes six (and Graphite has `vinyl_grain`): `vinyl_base`, `vinyl_lid` (the rim colour), `vinyl_arm`, `vinyl_armsh` (Snow's shadow is lighter), `vinyl_cap`, `vinyl_keys`. Graphite's keep their
  names and are pixel for pixel what V2.1qD installed; Snow's end in `_white` (`vinyl_art.tname`, `vn_names`). `vinyl_label` and `vinyl_rec` are shared: the Cover record carries
  no plinth (its rim blends into the base already loaded), so it is the same under every theme.
- **Text.** The labels' colours are in the page asset, so each theme has its own: `m1plus_vinyl` (Graphite), `m1plus_vinyl_white` (the same tree, `vinyl_art.text_rgb`;
  `vn_pages` opens the saved one). No stock call is needed to recolour a label. The chevron is in the base.
- **Size.** Snow adds 86 KB of PNG (Walnut, 197 KB, was dropped for the rootfs headroom); see the table above.
- **Cost.** None at run time: the page loads its theme's six pictures instead of Graphite's; a playing tick is identical (test).

## Touch

**Taps only.** The view binds pointer DOWN, UP and ABORT and nothing else: no MOVE handler, no `widget_grab`, every handler returns RET_OK, so the stock
pull-down from the top edge works as on any page (see `tape.md` "Touch"). What a touch began on decides; it must end on the same thing:

| Began and ended on | Does |
| --- | --- |
| the chevron, (0, 0) .. (52, 44) | `navigator_back()`: Now Playing is under the page |
| the play key's column (x 223 .. 269, y 420 .. 480) | `playpause_quick_click()` |
| the previous / next key's column (170 .. 223 / 269 .. 318) | `prev_quick_click(e, 0)` / `next_quick_click(e, 0)` with the UP event (stock reads its time and ignores a click within 1 s of the last) |
| the record (inside radius 162, above the band), moving under 14 px, page opened from the More sheet | `playpause_quick_click()` |
| the same tap, page **opened by Now Playing's timer** (Idle Display, `vinyl_open_idle`) | `navigator_back()`, like the chevron (as stock's Album Cover page closes on a tap) |
| anything else, a drag, an abort | nothing |

**Auto-opened flag.** `vinyl_open_idle` (called only by `bc_timed_open`, [bigcover](bigcover.md) "Idle view") is `vinyl_open` plus `vn.idle = 1` once the page is up; `vinyl_open` (the More sheet) never sets it. The flag is part of the page's state, so destroy clears it; a timed open on a page that already exists leaves its flag as it was. The chevron, the three keys (and their pressed looks), drags and aborts behave the same either way. Tests: `test/pod/vinyl.py` `idle_touch_tests`.

A key is drawn pressed (darker, smaller shadow, its glyph a pixel lower) from DOWN until the touch ends; only its cell is invalidated. After an action the
page looks again at once (the play glyph, the arm, the record follow without waiting a tick). Previous / next are the stock functions the Now Playing buttons
and the hardware keys call, already pinned for the Pod (`IPOD_PINS`: `prev_quick_click` `0x4cccb0`, its `e->time` read and 1 s guard; `next_quick_click`
`0x4ccf00` for the mini bar). No click sound.

## Timer and idle power

`vn_first` (a 50 ms one-shot) makes the first full draw and starts `vn_tick` at **50 ms while anything moves** (playing, the record slowing, the arm
swinging) and **500 ms at rest**, changed in place with `timer_modify`. Removed on `EVT_WINDOW_TO_BG`, added again on `TO_FG`; destroy removes it and frees the
nine bitmaps. While the screen is off (`pod_screen_lit`) a tick reads and draws nothing and the interval is `POD_DARK_MS` (1 s); the first lit tick catches up
(a tick's step is capped at `VN_DT_MAX`, 100 ms). A page opened dark waits for the light. Nothing here stops the stock screen-off (by construction; on the checklist).

### Cost

Measured in emulation (`test/pod/vinyl.py` `motion_tests`, instructions a tick, budgets enforced): a playing tick (the label turned) about 2.1 M; a tick that
swings the arm about 6 M while the label turns too (play, a new track) and about 4 M after a pause (the arm waits for the record to stop). The first build spent 25 to 36 M on each of the ~11 swing ticks after a pause (two whole diagonal arm boxes composed, every
sampler a call under `-Oz`), more than a 50 ms tick on the device: the swing stuttered until the arm parked (device report on V2.1zDEZGAAAI). Now `vn_arm_draw` composes
each row once over the columns the old or new arm or their shadows can touch (`vn_cols`, from `vn_sprite`'s bounds), the seven layers are locked once a look (`vn_lock`),
and the per-pixel helpers are forced inline (`VN_HOT`). `vn_row` composes a row in passes, one a layer, each over its own columns (the label's from an integer square
root, the arm's from `vn_cols` for the arm as drawn), so every loop keeps its few sums in registers; the samplers' rotated sums step by a constant along the row (no
multiply a pixel, the same sums exactly); a sprite sample whose four taps are clear returns at once; turning the label composes only its circle, not its square's corners.

Stock adds a pause of its own: `play_pause_music` (0x4e43b4), going from playing to paused, mutes, then `usleep(150000)` (0x4e4460) on the UI thread before
`mclSetPause`. No page can draw during it (stock's Now Playing has nothing moving to show it). `VN_DT_MAX` keeps the tick after it from leaping: the label and the arm
carry on from where they were.

## Safety and fallbacks

- No hook, no patched word, no new pin: every stock call is already pinned (the Tape page's invalidate and label read, the Pod's timer and quick clicks,
  Now Playing's cover file, the cover cache's decode).
- A page that fails to open (no window, a widget missing, a picture missing or of another size, no memory) frees what it made, goes back with
  `navigator_back` and returns -1; the More sheet closes only after the page is up (`pm_on_vinyl`), so it stays as it was.
- The labels are insensitive; the only visible, sensitive widget is `vinyl_view`.

## Not implemented

Seek by dragging the arm, a scratch / cue gesture, picture-disc records, a speed (45 rpm) choice, a lock-screen skin, hardware Back handling.

## Device checklist

Now Playing on a playing track, More: six rows (Look up album, Look up artist, Add to playlist, Cassette Mode, **Vinyl Mode**, More), the sheet 300 px with a
clean rounded top. Tap Vinyl Mode: the sheet closes and the turntable appears, the status bar gone.
- Is the cover on the label, turning smoothly clockwise (about 20 frames a second)? Any tearing, shimmer or lag? Does it slow to a stop on pause and speed up on
  play? Is the 50 ms tick warm (relax `VN_PLAY_MS` if so)?
- Does the arm sit on the record while playing and creep inward over the track, swing out to its park on pause and back in on play, jump back to the outer
  groove on a track change? Is its shadow right?
- Title (with weight), artist, times, status line readable; long titles cut with an ellipsis; the status line updates with the volume keys.
- Keys: pressed look while held; play / pause, previous, next work (a second press within 1 s is ignored by stock). A tap on the record pauses / resumes (closes the page when it was opened by the Now Playing timer); a
  drag does nothing; the chevron closes; a pull-down from the top edge still opens the control centre.
- A track with no cover: the grey label; an album with a cover cached: its cover at once; a track whose cover demo extracts: the label changes within a few
  seconds.
- Record colour Cover (Settings > Now Playing > Vinyl Mode > Record, then open Vinyl Mode): with a colourful cover the record takes its colour (mock: `out/preview/vinyl-emu-rec-cover.png`),
  with no white line at the edge and only a faint highlight; the fine groove rings show. A new track of another cover changes it (watch for a hitch of a few tens of ms on the
  change: 15 M instructions); a grey or missing cover leaves it black, and back to black is exactly the installed look. Turning, the arm and the tick are as smooth as with Black.
- The screen still sleeps with the page open, wakes and catches up; back to Now Playing, Vinyl again: opens every time.
