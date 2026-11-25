# The iPod page's Cover Flow screen

**Sources:** `patch/ipod_cf.c` (the screen), the level `K_CF` and a few call-ins in
`patch/ipod.c`, the shared renderer `patch/coverflow.c` / `patch/coverflow.h`, `IPCF_*` in
`patch/offsets.inc`.
The iPod Classic's Cover Flow inside the virtual iPod ([ipod](ipod.md)): the iPod main menu's and Music menu's
**Cover Flow** rows open a screen of the iPod page, not the full-screen Cover Flow page
([coverflow](coverflow.md), which the Home menu and the Artists page still open). No new hook,
widget, timer or event: the screen is a level of the iPod page, painted in the page's one
`EVT_AFTER_PAINT`, steered by the page's wheel, run by the page's one timer. The shelf's numbers are
tuned against a photo of an iPod classic's Cover Flow.

It shares the depth renderer, the cache files and keys, the decode (`cc_decode`), the wheel, the
albums query, the tracks level and the play path with the rest of the Pod and the full-screen page;
its own parts are `ipod_cf.c`, the shelf struct's `tail` and `bg` fields, `K_CF` and the 33 ms pace
in `ip_want_ms`.

## The screen

The 320 x 240 screen follows Pod's Light/Dark appearance under its own title bar (**Cover Flow**
left, play glyph and battery right). The covers are rendered in a 320 x 220 frame at y 20 (filling
the screen below the title bar so the 3D album flip also fits inside it).

| Part | Value |
|---|---|
| Centre cover | faces you at 128 px (`IPCF_ART`), top at frame y 22 (screen y 42..170) |
| Side covers | turned 75 degrees (`IPCF_TURN`), 62 px back (`IPCF_Z1`), outer edges as tall as the centre; 34 px apart, three either side, running to the screen edges |
| Covers shown | seven: a light linear dim to `IPCF_TAIL` three out, fading out by 3.5 out (the full-screen page shows five and a half and keeps the stock fade) |
| Reflection | 40 px at the centre (`IPCF_REFLECT`), ending at screen y 210, fading into the background |
| Captions | album title (y 192) over artist (y 214), 18 px, centred, ellipsis; they follow the centre album, which changes at the slide's half-way point |
| Background | `IPCF_BG` white in Light; Pod's dark background in Dark, including the distance fade and reflections |

Textures are the 168 px cache files shared with the Cover Flow page and Albums grid
([covercache](covercache.md)), drawn nearest-neighbour. An album without a cached cover shows the
Pod placeholder; this screen never builds the cache. Memory: the 275 KB frame and 9 textures
(1.0 MB), one `calloc` at entry, freed on leaving Cover Flow and at destroy. If the allocation
fails, the row opens the full-screen Cover Flow page instead.

## Albums, wheel and flip

Entering pushes `K_CF` over the main menu or the Music menu. Its list is the stock albums list
(`loadLocalClassList(0xf003)`), read and re-read by the iPod page's machinery; paint never queries.

- **Order:** the shared Albums order (`albums-sort`, which the Albums page's and the Cover Flow page's
  "..." cards change). `ipcf_order_load` sorts a copy once a visit, before the level's list is read
  (`cc_albums`, `cc_album_order`; Recently Added and Year read the song list once); `ipcf_arrange`
  then moves the records of every read of the list into that order in place (whole records, a
  cycle walk). A list of another size than the sorted copy keeps the stock order.
- **Start:** `ipcf_start` follows Settings > Library > Cover Flow > **Start At**
  ([coverflow](coverflow.md) "Shelf"): the playing track's album (its album key, else its album
  name, as the full-screen page's `find_playing`), the last position, or the first album.
- **Last position:** the album the shelf stops on (`ipcf.centre`, from the tick and the paint) is
  saved when the screen closes, in the full-screen page's `coverflow-position` file, so either shelf
  opens where the other was left.

- **Wheel:** the page's own (20 degrees a step, reversal hysteresis, chord dead zone). Cover Flow
  caps wheel acceleration at `IPCF_MAX_TIER` (tiers 1, 2, 3, 5 albums a step on more than 16 albums,
  fewer always one) so fast turns glide smoothly instead of jumping across dozens of albums at once.
  **Hard stop** at the first and last album.
- **Centre button (album flip):** pushes `K_CF_TRACKS` over `K_CF` with a 300 ms eased-out (`IPCF_FLIP_MS`)
  3D Y-axis flip in place (`coverflow_flip`; at 0, before the first tick, the shelf's cover, never a blank frame): the side covers stay where they are behind it while
  the centre cover rotates 0..90 degrees, then the floating back card rotates -90..0 degrees into
  (`IPCF_CARD_X`, `IPCF_CARD_Y`, `IPCF_CARD_W`, `IPCF_CARD_H`). Once settled at 180 degrees, the
  side covers remain visible along both edges behind the floating card (no shadow; a 1 px edge),
  which renders live with a sky-blue glossy album + artist header (white text), seven crisp white
  track rows (`IPCF_CARD_ROWS`, no scrollbar), blue selection bar and playing speaker icon,
  keeping the **Cover Flow** title bar on top.
  The turning card is the card's own picture, text included (`ipcf_face`, `IPCF_CARD_W` x `IPCF_CARD_H`
  after the textures): `ip_cf_face` lays the card's paint (`ip_paint_card_body`) into it through
  `ip_render_raster` whenever what the card shows changes while it is in front (album, rows, selection,
  playing track, list validity), so the opening flip shows the titles from its first card frame and
  closing or going to Now Playing turns the card as it was last. Without a face (a paint that did not
  fit the display model) the flip turns a sketch of the card.
  The wheel scrolls tracks inside the card; the centre button plays the track (`ip_cf_play`): the
  card turns away, its right edge first, while its axis eases left to `IPCF_TURN_IN_X`, and what turns in
  there, the same way round, is the album's cover, so the two halves are one turn,
  straight from edge-on to Now Playing's turned cover while the side covers fade (`ipcf_go_card`,
  `coverflow_turn_in`, `IPCF_GO_CARD_MS` 280 ms, from column `IPCF_TURN_IN_X`), then the same hold;
  Now Playing opens over the covers, not over the card.
- **`>||` on an album:** playing, it pauses and Cover Flow stays (`ip_cf_key`); paused on the centre
  album's track, it plays on and the cover goes to Now Playing (no new start). Otherwise it plays the
  centre album from its first track and opens Now Playing
  (`ip_cf_play`: the card's track query without the flip, the card level then dropped from under
  `K_NOW`), so MENU returns to the covers. On the card and elsewhere `>||` is play / pause.
  Instead of the level slide the cover **goes** to Now Playing's place, as on the iPod
  (`ipcf_go_open`, `coverflow_morph`, `IPCF_GO_MS` 640 ms): the captions go and the side covers fade
  out where they are (`CF_GO_FADE`, the first quarter), then the centre cover's near and far edges
  travel (smoothstep) to Now Playing's turned cover (`IP_NP_ART_*`, the `ip_tilt` geometry, its
  reflection shortening to `IP_NP_REFLECT`), stays there alone `IPCF_GO_HOLD_MS` (280 ms) under Cover
  Flow's title, and Now Playing itself takes over. MENU from that Now
  Playing runs it back (`ipcf_go_close`, `IPCF_GO_BACK_MS` 380 ms) with the captions already up, the side
  covers sliding in from both edges in its last 5/8 (`CF_GO_SLIDE`, easing out) instead of fading in.
  While it goes nothing slides or decodes (`go_ring` keeps the textures). The go's and the flip's clocks
  skip stalls (`anim_dt`: a gap over `IPCF_STALL_MS` between ticks, such as the first play after boot
  starting the player), so they run frame by frame instead of jumping to the end.
- **MENU:** Now Playing opened from Cover Flow returns to the covers (the cover going back);
  MENU on the flipped card runs the 3D flip back (`255 -> 0`: at 256 the frame holds no card, so the first closing frame would be a gap) to Cover Flow on the same album; MENU
  on Cover Flow returns to the main menu or Music (frame and textures freed). `|<<` and `>>|` keep
  their playback meaning.

## The slide and the timer

`pos` and `target` (16.16 albums) are the slide's position and goal; `vel` is its speed. The slide
is a critically damped spring (time constant `IPCF_TAU_MS` 85 ms), stepped per ms on each tick and
held to `IPCF_VMAX` (12 albums a second, about 0.4 covers per 33 ms frame). Steps move the spring's
target without an abrupt initial kick, so a single step eases smoothly in and out like a spring and
a steady turn glides smoothly past the covers. The shelf **folds** continuously with the speed
(`cfg_t` `fold`): the speed smoothed over `IPCF_SPD_MS` (130 ms) maps from open at `IPCF_FOLD_V0`
(13 albums a second) to full at `IPCF_FOLD_V1` (24). A steady turn (held to `IPCF_VMAX`) stays turned, as
on the iPod, where the covers lie flat only at the peak of a burst, here the release rush. Folded, the shelf lies flat
into a **deck**: every cover turns back to face front and lies back at `IPCF_DECK_Z` (70 px, about 80 %
of the centre cover's size, `cfg_t` `deck`), `IPCF_SPREAD` (40 px, `cfg_t` `spread`) apart with the
centre spaced like the rest (continuous at `t = 0`), so each shows a strip. From fold 192 the deck
stacks by the way it goes (`cfg_t` `dir`, the velocity's sign): the covers coming in lie over the
ones before them. A single step stays under the fold threshold. When the finger leaves the wheel
the rest of the slide closes quicker (`ipcf_rush`: `IPCF_RUSH_TAU_MS` 45 ms, `IPCF_RUSH_VMAX` 36 albums
a second) until it rests; a new step ends that. The slide settles within `IPCF_DONE` (1/128
album) and `IPCF_VSTOP`. A gap over `IPCF_NEAR` (8) albums is closed at once by whole albums,
keeping the fraction and the speed.

The page keeps **one timer** whose interval is chosen in one place (`ip_want_ms`) and changed in
place with `timer_modify`: 500 ms normally, `IP_DRIFT_MS` while the main menu's cover pans, and 33 ms
(`IPCF_FRAME_MS`) while Cover Flow is in front and busy (sliding, folding, flipping or decoding).
The timer is never removed or added while the page lives.

**Decoding** is one cover per tick on the UI thread (paused while flipped): nearest the centre
first, then alternately on the side the slide moves towards; 7 wanted in 8 slots, a slot reused
from the farthest cover, keyed by album key. **Paint** renders only from what is resident and
reuses the frame when nothing changed; it never decodes, queries or allocates.

Entering or leaving this screen uses the Pod's split transition (`SPLIT_MS` 200 ms in
`ipod_render.c`, see [ipod](ipod.md)). The outgoing display model owns a clone of the frame, so
Cover Flow's buffers can be freed during the slide. Decoding pauses during the slide.

## Limits

- No search-by-letter, no artist or sort setting.
- A gap beyond `IPCF_NEAR` (8) albums skips intermediate covers by whole albums so decoding stays
  near the visible shelf.
