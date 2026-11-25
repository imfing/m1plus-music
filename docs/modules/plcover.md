# Generated playlist covers

**Sources:** `patch/plcover.c` and `patch/plcover.h` (`plc_art`, `plc_get` and the rest of the stored choice), `patch/plcpage.c` (the Cover page), `grid_plc` in `patch/grid.c`, `patch/dmart.h` (the Daily Mix art
pieces it shares, defined in `patch/dailymix.c`), `tools/pod_plcover.py` (the integer model, the
tables), `tools/preview/preview_plcover.py` (the preview), `PLC_*` in `offsets.inc`,
`test/pod/plcover.py`.

A playlist cover drawn from colours taken from the playlist's albums, the Daily Mix way: a style, a
palette and for Mesh a seed. `plc_art` is a pure function of its arguments: it reads no file, touches no
widget and allocates nothing. The rest of `patch/plcover.c` is the stored choice (below); the Cover page that
chooses a style is `patch/plcpage.c` (last section).

## Interface

```c
void plc_art(unsigned *px, int side, int style, const unsigned *tones, int nt, unsigned seed);
```

Writes `side` x `side` opaque RGBA words (red lowest, RGB565 values expanded, the Daily Mix's 4 x 4
Bayer dither) for the styles below; `side` is 1..`PLC_MAX` (320). Any other style or side draws
nothing. `tones` are `m1_tone` words (`0xAABBGGRR`), at most four used, none gives a grey
(`0x787878`). The styles are an enum (`PLC_STYLE_*`) whose numbers are stored, so they never change:

| # | Style | Look |
|---|---|---|
| 0 | Albums | the grid's 2x2 mosaic; never drawn here |
| 1 | Solid | the tone, a little lighter at the top than at the bottom |
| 2 | Mesh | the Daily Mix's blob field of the tones |
| 3 | Sunburst | seven rays fanning up from a point below the cover's right of centre |
| 4 | Stripes | five columns, each a vertical dark-to-light gradient with its own step height |
| 5 | Band | a light band across the lower middle on a dark-to-tone ground |

## Palette

`A` is the first tone prepared as the Daily Mix does (`dm_prep`: a colourful tone gets at least 0.55
saturation and a lightness in [0.30, 0.56], a grey one [0.25, 0.66]). `K` is `A` at 16 % (a tinted
near-black), `L` is `A` 70 % toward white. The ramp `ramp[0..256]` runs K, A, L: `mix(K, A,
smoothstep(2i))` below 128, `mix(A, L, smoothstep(2i - 256))` above. Ratios are /256, a mix is
`a + ((b - a) * t >> 8)`. A second tone is used by Mesh only.

## Styles

Positions are in 1/256 of the side, taken at pixel centres (`v = (2y + 1) * 256 / (2 side)`); no
style has a hard curved edge, so nothing is anti-aliased.

- **Solid:** per row `mix(A x 1.12, A x 0.82, v)`.
- **Mesh:** `dm_blobs_wh` and `dm_field_wh` (the card's field, no scrim) on the first four tones and
  the seed. One tone (or none) is completed as `[A, L]`, packed back through `dm_prep` as the field
  does. The seed is the field's art seed (0 is the field's default stream).
- **Sunburst:** the apex is at (0.7, 1.1) of the side. Per pixel the angle comes from an octant and
  a 65-step atan table with a reciprocal table (`2^22 / m`), so there is no division per pixel, in
  65536ths of a turn; `rays = 0.5 + 0.5 cos(7 a)` from a 256-entry table. The ramp position is
  `0.12 + 0.70 rays (1 - 0.45 far) + 0.18 (1 - near)`, where `far` and `near` are smoothsteps of
  `d^2 / R^2` (R = 1.0 and 0.4 of the side, a multiply by a per-call reciprocal; no sqrt).
- **Stripes:** column `i` holds `x * 5 / side`, its edges pixel aligned; position
  `0.12 + 0.78 smoothstep(v - level_i + 0.5)`, levels 0.50, 0.36, 0.60, 0.44, 0.30.
- **Band:** per row, ramp position `0.15 + 0.35 v` mixed toward L by `0.95 (1 - d^2 / R^2)^2`, `d`
  the distance from 0.6 of the height, R = 0.26 (the polynomial stands for exp(-x^2), no exp).

Styles that depend on the row only (Solid, Band, Stripes) build one row of colours and dither it;
only Sunburst and Mesh work per pixel.

## The stored choice

A local playlist's cover is a line in `/mnt/mmc/.m1plus/playlist-covers` (`PLC_FILE`; the card, like the other state that
references library items). A playlist is its stock id and its name, as a Home pin is: the stock ids are reused, so another
name is another playlist. A source's playlist (`pl.src`, `songs_open_src`, Subsonic) never looks the file up. The colours
are frozen when the style is chosen: the line keeps the tones and the seed, so the cover does not change with the songs.

```
M1PC1\n
<id>\t<style 1..5>\t<flags hex>\t<seed hex8>\t<0..3 tones rrggbb, a space between>\t<name>\n
```

The reader is strict: a bad header, a file over `PLC_FILE_MAX` (12288 bytes) or a card that is not mounted is no covers; a
line that does not read (id with a sign, leading zero or over 2^31 - 1, style 0 or 6, flags not 1 or 2 lowercase hex digits
without a leading zero, a seed not 8 lowercase hex digits, more than three tones, an empty or control-byte name, a name of 64
bytes or more) is dropped; the first line of an id stays; at most `PL_MAX` (100) lines. Names are kept as the pins keep them
(control bytes as spaces, cut before a split UTF-8 character; here 63 bytes). `flags` bit 0 (`PLC_FLAG_NAME`, the name on
the cover) is stored and read (the Cover page's switch sets it) and drawn on the cover ("Where it is drawn"); the other bits are kept as read. `tools/pod_plcover.py` (`parse`,
`dump`, `set_`, `rename`, `forget`) is the model the tests compare with.

The text is the state: one buffer holds the lines that read, found by id and name and edited in place, and a write
(`m1_card_write`, atomic) sends it as it is. The buffer is read again when the file's modification time and size changed (no file,
the usual case, is a state too: a call costs one stat); a failed write leaves the file and the buffer is read again from it. Nothing is
written without a card.

```c
typedef struct { int style; unsigned flags, seed; int nt; unsigned tones[3]; unsigned sig; } plc_t;
int plc_get(int id, const char *name, plc_t *out);
int plc_set(int id, const char *name, int style, unsigned flags, const unsigned *tones, int nt);
unsigned plc_seed(int id, const char *name);
int plc_rename(int id, const char *old, const char *name);
int plc_forget(int id, const char *name);
```

`plc_get` is 1 when a style other than Albums is stored (`out` may be NULL); `sig` is a hash of style, flags, seed and tones
(never 0), so a rename keeps it and any change to the picture changes it. `plc_seed` is the seed a playlist's Mesh cover has: the stored one, else the one `plc_set` would make. `plc_set` stores the cover (tones are `m1_tone`
words, the first three; flags one byte) and returns 0, or -1 for a bad argument, no card, a full file or a failed write; style 0
removes the entry; the seed is made once from the id and the name (`make_seed` in the model) and kept; a stale entry of the same
id under another name is replaced. `plc_rename` and `plc_forget` answer 1 when they changed the file. `plc_rename` is called next to
`pins_rename_playlist` in `sg_renamed`; `plc_forget` runs in the Playlists page's Delete for the selected playlists the stock list no
longer has (the stock list is read again after `batch_delete_file`).

## Where it is drawn

`grid_plc(g, t, c)` (`patch/grid.c`) is the whole tile in one call: `plc_art` at `g->side`, `grid_round`, `art` 1 (at most about 6
million instructions at 160 px, one tile a tick). It replaces the mosaic in the three places that draw it:

- the Playlists page (`pl_art` from `pl_on_load`, grid and list): the scan still runs for the counts;
- the playlist's Songs header (`sg_head_prep`, `sg_on_load`; 160 px);
- a playlist's Home pin (`pn_make`; the pin's own size, corners in the alpha).

`grid_tile_t.cov` holds the `sig` a tile was made for (0: the mosaic). Each owner compares it with the file's at its
refresh (`pl_load` when the database is unchanged, `sg_head_prep`, `pn_tiles`), so a set, a removal or a change of name shows at
the next return to the front without a stale tile, and an unchanged cover keeps its bitmap.

**Name on Cover.** A tile made with the flag (`grid_plc` sets `grid_tile_t.nm`, `grid_free_art` clears it) has the playlist's name drawn over it by
`grid_plc_name(canvas, g, t, name, x, y, view_h)`, called by the owner right after the tile's blit with the name it has now (a rename needs no new
tile: the sig is kept and the next paint shows the new name): the Songs header (`sg_paint_rows`, and `sg_paint_add` for an empty playlist; not a source's), the Playlists grid (`pl_on_paint`, not
the list rows), a Home pin (`pn_on_paint`, the lifted tile too) and the Cover page's thumbnails 1..5 (`pc_paint`, while the switch is on; never Albums).
The text is white (the grid's own text style `g->st_title`: `label_grid_title` 18 px on the header and the grid, `pod_pin_title` 15 px on the pins,
`pod_covname` 14 px on the thumbnails), top left, inset 8 % of the side, lines 22 px apart (18 below a 120 px side), at most two lines wrapped by `pw_wrap`
(latin at spaces, CJK between characters, a last line cut with an ellipsis) into the side less both insets. It is not drawn when the side is under
`GRID_NAME_MIN` (64 px: the Playlists list rows' 52 px show none), without the style label, or for a line not wholly in the view. No shadow: the
styles' tops are dark enough for white text. `tools/preview/preview_plcover.py` renders the styles with a short, a long and a CJK name
(`out/preview/plcover-names.png`).

## Cover page

A local stock playlist's cover is chosen on its own page (`m1plus_plcover`, title "Playlist Cover", `PLCOVER_PAGE` in `tools/pod_pages.py`), reached from
the Songs page's Edit mode ([songs](songs.md) "Edit mode"). It is not a Settings row, so it has no place in the page tree.

- **Layout.** A card (`CoverCard`, the view `pod_cover`, `COVER_ITEM_H` high) with six `PLP_T` (88) px thumbnails in two rows of three,
  `PLP_PX` / `PLP_PY` apart, each with its name under it (`pod_covl<k>`: Albums, Solid, Mesh, Sunburst, Stripes, Band, the style numbers). The chosen
  one has the ring (`pod_covring`, a baked white ring with a black gap, `PLP_GROW` px outside the thumbnail) and a white name; the others are grey.
  Under the card the generic switch row Name on Cover (`ACT_COVNAME`: `PLC_FLAG_NAME`; dimmed and inert while Albums is chosen, for which nothing is
  stored) and the note "Colours come from the albums in this playlist.".
- **Hand-over.** `sg_cover` (the Songs page, a tap on the header cover in Edit) calls `plcpage_open(id, name, keys, nk)` with the keys of
  `grid_mosaic_keys` and opens the page; the page reads the stored choice with `plc_get`. The Songs page sets `cover_due`, and when it is back in the
  front (`sg_on_fg`) `sg_head_prep` makes the header again: in Edit the tile stays only while its `cov` is the stored `sig`.
- **Thumbnails.** One a 30 ms tick, in order (`pc_tick`): the tones first (the first three non-zero keys, each from `m1_tone_get` or its cache file
  reduced to one pixel with `cc_decode`, then `m1_tone_put`; the full `m1_tone` word is kept), then Albums (the grid's `grid_mosaic`, a source a
  tick; the placeholder with no keys), then Solid to Band with `grid_plc` at the thumbnail size and `plc_seed`, so each shows what a tap would store.
  Grey until drawn. No keys: no tones, `plc_art` greys it.
- **Taps.** A tap on a thumbnail (or its name) calls `plc_set(id, name, style, flags, tones, nt)` at once; Albums (style 0) removes the entry and
  clears the flags; the styles are then drawn again with `plc_seed` of the name as it is now (`pc_reseed`: a rename kept the old seed, which the
  entry took with it). The chosen one stored again takes the colours the playlist has now. The ring and names move and the page stays open. A
  `plc_set` that returns -1 (no card, a failed write) toasts "Can't change cover" and moves nothing. The switch (`plcpage_name_toggle`) stores the
  stored entry with the flag flipped, its tones and seed kept (an emptied playlist would grey them), and repaints the card (the switch row repaints only itself).

## Cost

Instructions a pixel at 160 px on the emulated MIPS (`make test TEST=plcover PERF=1`): Solid,
Stripes and Band about 120 (nearly all the dither), Sunburst about 220, Mesh about 230 with three
tones. A 160 px tile is about 3.5 to 6 million instructions. The stack holds about 5 KB (the ramp,
a row, the reciprocal table).

## Preview

`uv run python -I tools/preview/preview_plcover.py WORKDIR` writes `out/preview/plcover.png`, the styles over six palettes with the grid's
rounded corners.
