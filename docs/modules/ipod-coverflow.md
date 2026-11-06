# The iPod page's Cover Flow screen (`patch/ipod_cf.c`)

The iPod Classic's Cover Flow inside the virtual iPod (`docs/modules/ipod.md`): the iPod main menu's **Cover Flow** row opens a screen of the iPod page, not the full-screen
Cover Flow page (`docs/modules/coverflow.md`, which stays what the Home menu and the Artists page open). Source: `patch/ipod_cf.c` (the screen), the level `K_CF` and a few
call-ins in `patch/ipod.c`, the shared renderer `patch/coverflow.c` with its header `patch/coverflow.h`, the numbers `IPCF_*` in `patch/offsets.inc` (next to the Cover Flow
`CF_*`), tests `test/pod/ipod_cf.py`. **Not seen on a device**: the shelf's numbers are tuned against a photo of an iPod classic's Cover Flow (no device numbers exist).

No new hook, widget, timer or event: the screen is a level of the iPod page, painted in the page's one `EVT_AFTER_PAINT`, steered by the page's wheel, run by the page's ONE timer.

## What is on the screen

The 320 x 240 screen follows Pod's Light/Dark appearance under its own title bar (`ip_paint_bar`: **Cover Flow** on the left, the play glyph and battery on the right; `ip_title` K_CF). The light appearance keeps the classic white page with the bar; Dark uses the Pod dark background, including the distance fade and reflections:

- **The covers**, a 320 x 192 frame (`IPCF_FRAME_H`) drawn at y 24 under the bar (`IPCF_FRAME_Y`) on white (`IPCF_BG`). The centre cover faces you at 128 px (`IPCF_ART`) with its top at frame y 18 (screen y 42 .. 170, its middle at 106), the largest thing on the screen as in the iPod photo; the covers on either side turn 75 degrees (`IPCF_TURN`)
  inward and stand 62 px back (`IPCF_Z1`), so their outer (nearer) edges are as tall as the centre cover (the iPod's look), their inner edges tucked behind it, and three either side, 34 px apart, run to the screen edges; each has a reflection (40 px at the centre, `IPCF_REFLECT`, ending at screen y 204) fading into the white, behind the captions. **Seven covers show**: the centre and three either side
  (as on the iPod they barely dim: a light linear dim from the centre to `IPCF_TAIL` 208 of 256 three out, then the cover three out fades out by 3.5 out; the full-screen page shows five and a half and keeps the stock fade).
- **Under the covers** the album title (y 192, 18 px black) over the artist (y 214, the same style), both centred and cut with an ellipsis (`label_ip_row`'s style: the iPod page's list text; the last line ends at y 236 of 240).
  They follow the covers: the album under the centre cover, which changes as the slide passes the half-way point. No scrolling text.
- The title bar is the page's (the title, the play state, the battery); the wheel below has MENU, `|<<`, `>>|`, `>||`.

## The renderer is Cover Flow's

`coverflow_render` (q2-pod's depth renderer after Rockbox PictureFlow, `docs/modules/coverflow.md`) draws the frame: nothing is written again. Its shelf geometry `cfg_t` moved to
`patch/coverflow.h` and got two fields, `tail` and `bg` (last) (0 = the stock fade, CF_BRIGHT2 at two out and gone at three; the iPod's `IPCF_TAIL` replaces it with a light dim to the cover three out and fades it
out by 3.5 out, so seven covers show with no pop at the ring's edge). The two stock shelves leave `tail` and `bg` 0, so their frames are unchanged (`test/coverflow.py`). `bg` 0 is over black; the iPod shelf's `IPCF_BG` 0xffffff makes the distance fade
blend the cover towards white (still opaque, so a nearer cover hides the ones behind it; only the reflections fade by transparency) and composites the frame over white at the end (`docs/modules/coverflow.md`). The iPod shelf is Cover
Flow's with the iPod photo's numbers: eye 272, first side cover 84 out and 62 back, the rest 34 / 6 apart, centre top 18, turned 75 degrees. The textures are the **168 px cache files** the Cover Flow page and the
Albums grid share (`/mnt/mmc/.m1plus/covers/<key>-168.jpg`, `patch/covercache.c`): drawn smaller than their size, nearest neighbour as there; an album with no cached cover (or a
cache not built yet) shows the Pod placeholder (`ipod_placeholder`, docs/modules/ipod.md "The placeholder cover"). Cover Flow here never builds the cache (open the Cover Flow page or the Albums page once).

**Memory**: the frame 240 KB and 9 textures of 168^2 x 4 (1.0 MB: 8 slots and the placeholder), one `calloc` at entry, freed when Cover Flow is left (MENU) and at destroy. If a
bitmap or the block does not come, the row opens the existing full-screen Cover Flow page instead (`coverflow_open`: the old behaviour is the fallback).

## The albums, the wheel

Entering pushes the level `K_CF` over the main menu; its list starts with the stock **albums list** (`loadLocalClassList(0xf003)`, in the stock query's order, not
Settings > Library > Album Order). When a synced Navidrome index is available, the page timer merges regular server albums into it, matching local albums by album artist and album name; DSD-only server albums are skipped. The combined list is read, validated and re-read by the iPod page's machinery (`ip_valid`, `ip_ensure`, the page timer's stale check): paint never queries and shows only the bar
while the list is stale. The level's `sel` is the album the cursor is on.

Virtual album rows keep ordinary owned strings in `stSongInfo`. Their artwork sources stay in a separate array while the index mapping is open, so deque teardown never frees an mmap pointer. Cover Flow closes the row deque before releasing that mapping. The centre button on a Navidrome-only album opens its matching track list through the shared Songs library; Back returns to Pod Cover Flow.

- **Wheel:** the iPod page's: a step per 15 degrees, the reversal hysteresis, the chord dead zone, the tiers **1, 2, 3, 5, 8, 13, 21, 34 albums a step on more than 16 albums**,
  fewer always one. A step calls `ipcf_goto(sel)`. **Hard stop** at the first and the last album: nothing moves, no timer is touched.
- **Centre button:** a local album opens its **track list** (`K_TRACKS` over `K_CF`: `loadAlbumdetailList(0xf003, the album's record)`, the same level the Albums level opens), an iPod
  list in the iPod page's look (title bar, blue selection). A Navidrome-only album opens its filtered tracks in the shared Songs library. **Not done: the iPod's flip of the cover to show tracks on its back** (an animation of the centre cover turning
  180 degrees and a track list drawn on it; the renderer has no flip pose): the list replaces the screen. The wheel selects a track, the centre button plays it (the
  album's tracks as the queue, `start_player`, the iPod's Now Playing level: `docs/modules/ipod.md` "Play").
- **MENU** (the top of the ring): Now Playing -> the tracks -> **Cover Flow on the same album** (the albums query runs again; the slide, the cursor and the textures were kept) ->
  the iPod main menu (Cover Flow's frame and textures freed) -> closes the page. `|<<`, `>>|`, `>||` keep their playback meaning (taps on the ring's left, right and bottom).

## The slide, and the page's one timer

`pos` and `target` (16.16 albums) are the slide's position and where it goes. A wheel step sets the target. Each tick of the page's timer eases `pos` towards it by
`dt / (dt + IPCF_TAU_MS)` of the gap (70 ms: an exponential approach, about 150 ms for one album, 15 ticks at most; `dt` from `time_now_ms`, clamped to 1 .. 100 ms; it ends within
`IPCF_DONE` = 1/64 album, exactly on the target). A far target (the tiers) starts the slide at most `IPCF_NEAR` = 4 albums short of it, so the covers on screen are the ones the
loader is decoding. The centre album and the captions follow `pos` (the album whose cover is nearest the middle).
The page keeps **one timer** (`ip.timer`, `ip.ival` its interval): it runs at `IP_TICK_MS` (500 ms: the battery, the play state, the track), at `IP_DRIFT_MS` while the main menu's cover pans
runs (`docs/modules/ipod.md`), and **while Cover Flow is in front and busy** (the slide moving, or a wanted cover not decoded) at `IPCF_FRAME_MS` (33 ms). The interval is chosen in one
place (`ip_want_ms`) and set in place with `timer_modify` (`ip_retime`: from the wheel handlers, `ip_push` / `ip_pop`, and the end of every tick); the timer is never removed or added while
the page lives. A fast tick runs the slow look (the battery, the play state, the track) only every `IP_DRIFT_LOOK` ticks. Leaving Cover Flow (MENU, or a track list above it): the main menu's or
the list's interval; the background, the destroy: the timer is gone as before.

**Decoding** is on the same tick, one cover per tick (`cc_decode`, UI thread, as Cover Flow's `on_load`): nearest the centre first, then alternately on the side the slide is
moving towards and the other, 7 wanted (the ring) in 8 slots; a slot is reused from the cover farthest from the centre. A slot is keyed by the album key (`cc_album_key`), so a
re-read of the list does not drop what was decoded. **Paint** renders from what is resident only (the placeholder for the rest): it never decodes, never queries, never allocates; an
unchanged position reuses the frame (the render, about 2.4 M payload instructions under Unicorn, only when the position, a texture or the appearance background changed; the page's own render is 3.5 M). The per-frame shelf configuration copies the selected Pod background without changing the other Cover Flow pages. Captions use the themed Pod text styles.

Entering or leaving this screen also uses the Pod's 200 ms full-width navigation slide (`ipod_render.c`, `docs/modules/ipod.md`). The outgoing display model owns a clone of the frame before Cover Flow's buffers can be freed; its image data is not borrowed across page changes. Decoding pauses during the page slide and resumes on the existing page timer afterward.

## What was reused, what is new

Reused: the depth renderer, the cache files and keys, the decode (`cc_decode`), the iPod page's wheel (angle, step, hysteresis, dead zone, tiers), levels, albums query, tracks level,
play path, MENU, the page's paint event and its one timer. New: `patch/ipod_cf.c` (slide, textures, paint), `patch/coverflow.h` (the shared shelf struct, the new `tail` field),
`IPCF_*`, `K_CF` and the 33 ms pace in `ip_want_ms` (`patch/ipod.c`) (below), the tests. `ip_fit` (the ellipsis cut) is now exported from `ipod.c` for the captions.

Where `patch/ipod.c` calls in: the enum (`K_CF`), the externs, `ip_run` (`K_CF` is an albums list; its tracks query), `ip_on_paint` (the first lines), `ip_want_ms` (the 33 ms
pace), `ip_pop` (closes Cover Flow), `ip_step` (the `K_CF` branch), `ip_select` (the Cover Flow row, the centre button on `K_CF`), `ip_tick` (`ipcf_tick`), `ip_on_destroy`.

## Not done

- The flip of the cover to the track list (above). No click sound (`docs/modules/ipod.md`). No search-by-letter; no artist or sort setting (the stock album order). The cache is not
  built here. Landscape: the screen is the iPod's 320 x 240.
- The wheel's tiers move the cursor, the slide only follows (a 34-album step shows the last four albums slide in, not 34 covers flying by).

## Device checklist

- iPod > Cover Flow: a white screen with the iPod title bar (Cover Flow), the centre cover, three covers either side tilted, overlapping and paler with distance, their reflections, the album and the artist centred under it;
  the first frame may show the placeholder for a moment, then the real covers fill in nearest first (about 0.25 s). Albums with no cached cover show the placeholder.
- Wheel: one album per 15 degrees, the slide eases (about 150 ms, no stutter, the covers do not tear or flicker), the caption changes as the cover passes the middle; on a long
  library a sustained fast turn speeds up (the tiers); at the first and last album the wheel does nothing (no bounce); reversing does not jump. The music does not stutter
  during the slide or while covers decode (the decode is one cover per 33 ms tick: if it does, make it every other tick).
- Frame time: the slide must look smooth; if it stutters, lower `IPCF_ART` or lengthen `IPCF_FRAME_MS`.
- Centre button: local album tracks open as an iPod list; Navidrome album tracks open in the shared Songs library. Back returns to Pod Cover Flow on the same album with its covers, then to the
  main menu; MENU there closes the page and the status bar returns. `|<<` `>>|` `>||` work in Cover Flow. Memory: open and close it ten times; nothing grows.
- If the heap is tight (`calloc` refused), the row opens the old full-screen Cover Flow page.
