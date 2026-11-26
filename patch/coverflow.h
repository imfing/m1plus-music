/* Cover Flow's depth renderer, shared by the Cover Flow page (patch/coverflow.c) and the iPod page's Cover Flow screen (patch/ipod_cf.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The renderer follows q2-pod's design, after Rockbox PictureFlow (see coverflow.c).
 */
#pragma once

#define CF_ONE 65536
#define CF_REACH 3 /* ring slots either side of the centre that can show (fading in) or preload */
#define CF_RING (2 * CF_REACH + 1)

/* A shelf's geometry: w x h logical columns and rows (the cover's x right, y down), the centre line
 * cx, the centre cover's top and size on screen (art; its texture is always ART_SIZE), the eye
 * distance, the first side cover's offset x1 and depth z1, the spacing xs and zs of the rest, the
 * reflection's length in px at the cover's own size. rot: the frame is the logical one turned a
 * quarter clockwise (logical (x, y) is physical (h - 1 - y, x)), see coverflow_render. turn: how far a side cover turns,
 * in 3.75 degree steps (CF_TURN 16 = 60 degrees; at most 24).
 * tail: 0 = the stock fade (CF_BRIGHT2 at two out, gone at three out); else a light dim from 256 at the centre to tail
 * three out, then gone by 3.5 out (the iPod page's seven visible covers, nearly as bright as the centre).
 * bg: 0 = the frame is over black (the distance fade darkens the covers); else the colour (r | g << 8 | b << 16) it is over (the covers fade
 * towards it and stay opaque, the reflections fade into it, and the frame ends composited on bg: the iPod page's white Cover Flow).
 * fold (0 .. 256): 0 the normal shelf; 256 a flat deck: every cover facing front at depth deck, spread px apart, the
 * covers on dir's side (1 later albums, -1 earlier, 0 nearest first) lying over the ones before them (from fold 192, nearly flat):
 * the iPod page's fast glide, continuous across t = 0, opening back as it slows. */
typedef struct {
    int w, h, cx, top, art, eye, x1, xs, z1, zs, reflect, rot, turn, tail;
    unsigned bg;
    int fold, spread, deck,
        dir; /* fold 0 .. 256 towards the glide's flat deck: covers spread px apart at depth deck, dir's side on top */
} cfg_t;

void coverflow_render(const cfg_t *g, unsigned *d, int pitch, int frac, const unsigned *const ring[CF_RING]);
/* The centre cover going to Now Playing's turned cover (u 0 the shelf .. 256: near edge at column xl hl px tall, far edge
 * at xr hr px tall, centred on row cy, the reflection reflect px under the near edge); the side covers fade out first. */
void coverflow_morph(const cfg_t *g, unsigned *d, int pitch, int u, const unsigned *const ring[CF_RING], int xl, int xr,
                     int hl, int hr, int cy, int reflect, int back);
/* The flipped card's second half when a track plays from it: the cover turns in from edge-on at column xs to Now
 * Playing's turned cover (xl, xr, hl, hr, cy, reflect as coverflow_morph), u 0 .. 256. */
void coverflow_turn_in(const cfg_t *g, unsigned *d, int pitch, int u, const unsigned *const ring[CF_RING], int xs,
                       int xl, int xr, int hl, int hr, int cy, int reflect);
/* 3D Y-axis flip of the centre cover (u 1..127: front cover 0..90 deg; u 128..255: back card -90..0 deg;
 * u 256: the parted side covers only, the caller paints the card) with side covers remaining visible behind the floating card.
 * The turning cover or card turns about column axis (g->cx in place); spin -1 turns it the other way. face: the card's picture
 * (card_w x card_h, its text in it) the back shows, or NULL for a sketch of it (sel_row its selection bar). */
void coverflow_flip(const cfg_t *g, unsigned *d, int pitch, int u, const unsigned *const ring[CF_RING], int card_y,
                    int card_w, int card_h, int card_hdr, int card_rows, int sel_row, int axis, int spin,
                    const unsigned *face);

enum {
    CF_START_PLAYING,
    CF_START_LAST,
    CF_START_FIRST
}; /* Settings > Library > Cover Flow > Start At (coverflow_start) */
int coverflow_start(void); /* the saved Start At mode; the main page and the Pod's Cover Flow open by it */
int coverflow_start_set(int mode); /* the picker's rows: save it; the mode or -1 */
int coverflow_bar(
    void); /* Settings > Library > Cover Flow > Slider: the main page shows its row of ticks (the default) */
int coverflow_bar_toggle(void); /* flip it; the new state, or -1 when it could not be saved */
unsigned coverflow_position(void); /* the key of the album last centred (the card's coverflow-position file), 0 none */
void coverflow_position_save(unsigned key); /* save it (a zero key is not saved) */
int coverflow_open(void); /* the menu's Cover Flow row, opened over this page */
int coverflow_artist(void *artists, unsigned index,
                     unsigned scope); /* Cover Flow scoped to an artist; 0 once the page is up */
int coverflow_artist_albums(void *artist_row, unsigned scope, int keep_card, void **albums,
                            unsigned **keys); /* one artist's album rows and their cache keys */
void *coverflow_artist_page(void); /* the artist's covers window, NULL when there is none */
