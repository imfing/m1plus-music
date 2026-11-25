/* M1+ Music iPod: the Cover Flow screen of the virtual iPod (patch/ipod.c) -- the iPod Classic's Cover Flow in the 320 x 240 screen.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/ipod-coverflow.md has the design. This file holds only what Cover Flow adds to the iPod page: the slide's position and its easing, the
 * covers' textures and the screen's paint. The albums, the wheel, the levels and the one page timer stay in patch/ipod.c, which calls in here when its
 * Cover Flow level (K_CF) is in front. No hook, no widget, no timer of its own: the page's ONE timer runs ipcf_tick (patch/ipod.c sets its interval in place, ip_want_ms / ip_retime).
 *
 *   renderer   Cover Flow's own depth renderer (patch/coverflow.c coverflow_render, header coverflow.h), with a shelf scaled to the 240 px screen (IPCF_*
 *              in offsets.inc) and seven covers visible (cfg.tail). The textures are the 168 px cache files (/mnt/mmc/.m1plus/covers, patch/covercache.c) the
 *              Cover Flow page and the Albums grid share; the placeholder is the Pod's own (`ipod_placeholder`, the iTunes one).
 *   textures   8 slots (the 7 of the ring and a spare), decoded one a tick on the page's timer (UI thread, cc_decode), nearest the centre first, the side
 *              the slide is moving towards first. Paint renders from what is resident and never decodes, queries or touches a file.
 *   slide      pos / target in 16.16 album units: the wheel moves the target and kicks the velocity (ipcf_goto); each fast tick steps a critically damped spring.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "coverflow.h"
#include "common.h"
#include "i18n.h"
#include "ipod_theme.h"
#include "ipod_render.h"
#include "entries.h"
#undef widget_prepare_text_style
#undef canvas_draw_text_in_rect
#undef canvas_draw_image
#define widget_prepare_text_style ip_render_prepare
#define canvas_draw_text_in_rect ip_render_text
#define canvas_draw_image ip_render_image

#define IPCF_SLOTS (CF_RING + 1)
#define TEXELS (ART_SIZE * ART_SIZE)
#define PLACE (ipcf.tex + IPCF_SLOTS * TEXELS)
#define FACE (PLACE + TEXELS) /* the card's picture, IPCF_CARD_W x IPCF_CARD_H, that the flip turns (ipcf_face) */

static const cfg_t shelf = {IP_W,      IPCF_FRAME_H, IP_W / 2, IPCF_TOP, IPCF_ART,     IPCF_EYE,
                            IPCF_X1,   IPCF_XS,      IPCF_Z1,  IPCF_ZS,  IPCF_REFLECT, 0,
                            IPCF_TURN, IPCF_TAIL,    IPCF_BG,  0,        IPCF_SPREAD,  IPCF_DECK_Z,
                            0};

static struct {
    int pos, target; /* the slide's position and where it goes, 16.16 albums (first: test/pod/ipod_cf.py reads them) */
    int vel; /* its velocity, 1/1024 of a 16.16 album per ms */
    int fold; /* the shelf laid flat into a deck for a glide, 0 .. 256 (cfg_t fold): 0 at a smoothed speed of IPCF_FOLD_V0 or less, 256 at IPCF_FOLD_V1 or more */
    int spd; /* the slide's speed |vel| smoothed with time constant IPCF_SPD_MS (a single step stays under IPCF_FOLD_V0) */
    int flip, flip_from, flip_to; /* 3D album flip 0 (cover) .. 256 (tracklist card) */
    unsigned flip_t0, flip_last; /* its clock's start and last tick (anim_dt) */
    int flip_row; /* highlighted track row remembered for the closing flip */
    const unsigned
        *flip_ring[CF_RING]; /* resident textures captured when flipping open (while ip.list is the tracks list) */
    char album[64], artist[64]; /* the flipped album's title and artist for the card header */
    void *win, *frame;
    unsigned *tex; /* IPCF_SLOTS textures, then the placeholder, then the card's face */
    unsigned key[IPCF_SLOTS]; /* the album key each slot holds, 0 empty */
    int idx[IPCF_SLOTS]; /* the album's row when it was decoded (only to pick the farthest slot to reuse) */
    const unsigned *art[IPCF_SLOTS]; /* its texture: the slot's own, or the placeholder (the album has no art) */
    int dir; /* the way it last went: 1 towards later albums, -1 back */
    int more; /* a wanted cover is not decoded yet */
    int drawn, dc, dfrac, dfold, ddir, dflip, drow; /* the position the frame holds, once drawn */
    void *list; /* the stock list and its size the frame was drawn from */
    unsigned count;
    unsigned bg;
    unsigned t0; /* the last time the slide moved (ms) */
    int go, go_from,
        go_to; /* Cover Flow <-> Now Playing: the centre cover 0 on the shelf .. 256 at Now Playing's place */
    int go_card; /* it goes from the flipped card (the card turning away, the cover turning in), not from the shelf */
    int go_hold; /* it has arrived and stays alone there IPCF_GO_HOLD_MS before Now Playing's text comes */
    int rush; /* the finger left the wheel: the slide closes what is left quicker (IPCF_RUSH_*) until it rests */
    unsigned go_t0, go_last; /* its clock's start and last tick (anim_dt) */
    const unsigned
        *go_ring[CF_RING]; /* the textures around the album that went (resident while it goes: nothing decodes) */
    int face; /* FACE holds the card's picture (patch/ipod.c ip_cf_face); 0: the flip turns a sketch of it */
    unsigned *
        order; /* the shelf's order (ipcf_order_load: the Albums page's, shared with the Cover Flow page) for a list of order_n rows; NULL: the stock order */
    unsigned order_n;
    int ordered; /* looked up this visit */
    unsigned centre; /* the key of the album last painted in the centre (0 none): the shared position, saved at close */
} ipcf __attribute__((section(".scratch")));

void ipcf_close(void) {
    coverflow_position_save(ipcf.centre); /* (the Cover Flow page's file: both shelves open where either was left) */
    free(ipcf.order);
    if (ipcf.frame) bitmap_destroy(ipcf.frame);
    if (ipcf.tex) free(ipcf.tex);
    memset(&ipcf, 0, sizeof ipcf);
}

/* The frame and the textures, or neither (0: the caller falls back to the Cover Flow page). The slide stands on album 0. */
int ipcf_open(void *win) {
    unsigned *p, i;
    if (ipcf.frame) return 1;
    memset(&ipcf, 0, sizeof ipcf);
    ipcf.win = win;
    ipcf.frame = bitmap_create_ex(IP_W, IPCF_FRAME_H, IP_W * 4, BITMAP_RGBA8888);
    ipcf.tex = ipcf.frame ? calloc((IPCF_SLOTS + 1) * TEXELS + IPCF_CARD_W * IPCF_CARD_H, 4) : (unsigned *)0;
    if (!ipcf.tex) {
        ipcf_close();
        return 0;
    }
    *(unsigned short *)((char *)ipcf.frame + BITMAP_FLAGS) |= 1; /* OPAQUE: every pixel is */
    p = PLACE;
    for (i = 0; i < TEXELS; ++i) p[i] = 0xff2b2b2bu; /* until the theme's disc loads */
    cc_decode(win, "ipod_placeholder", 0, ART_SIZE, 1, p);
    ipcf.dir = 1, ipcf.more = 1;
    return 1;
}

int ipcf_flipping(void) { return ipcf.frame && ipcf.flip != ipcf.flip_to; }
int ipcf_going(void) { return ipcf.frame && (ipcf.go != ipcf.go_to || ipcf.go_hold); }
int ipcf_gone(void) { return ipcf.frame && ipcf.go_to == 256; }
int ipcf_busy(void) {
    return ipcf.frame && (ipcf.pos != ipcf.target || ipcf.vel != 0 || ipcf.fold || ipcf.flip != ipcf.flip_to ||
                          ipcf.go != ipcf.go_to || ipcf.go_hold || (!ipcf.flip && ipcf.more));
}
const char *ipcf_album(void) { return ipcf.album; }
const char *ipcf_artist(void) { return ipcf.artist; }

/* ---------------------------------------------------------------------------
 * Textures
 */
static unsigned key_of(void *r) {
    return r && I(r, REC_ID) != ID_ALL_SONGS && *cc_str(r, REC_ALBUM) ? cc_album_key(r) : 0;
}

static int resident(unsigned key) {
    int i;
    for (i = 0; i < IPCF_SLOTS; ++i)
        if (ipcf.key[i] == key) return i;
    return -1;
}

static const unsigned *tex_of(void *list, unsigned count, int a) {
    unsigned key = (unsigned)a < count ? key_of(deque_at(list, (unsigned)a)) : 0;
    int i = key ? resident(key) : -1;
    return i < 0 ? PLACE : ipcf.art[i];
}

/* The k-th album wanted around c, nearest first (c, then each ring distance ahead of the travel, then behind it); -1 for none. */
static int wanted(int c, int n, int k) {
    int a = k == 0 ? c : c + (k + 1) / 2 * (k & 1 ? ipcf.dir : -ipcf.dir);
    return a >= 0 && a < n ? a : -1;
}

/* The nearest wanted cover that is not decoded yet goes into a free slot, else the farthest one's. Returns whether one was decoded; ipcf.more says whether any is left. */
static int fill(void *list, unsigned count, int c) {
    char url[80];
    const char *file;
    int k, done = 0, slot, dist, i;
    ipcf.more = 0;
    for (k = 0; k < CF_RING; ++k) {
        int a = wanted(c, (int)count, k);
        unsigned key = a < 0 ? 0 : key_of(deque_at(list, (unsigned)a));
        if (!key || resident(key) >= 0) continue;
        if (done) {
            ipcf.more = 1;
            break;
        }
        slot = -1, dist = -1;
        for (i = 0; i < IPCF_SLOTS && slot < 0; ++i)
            if (!ipcf.key[i]) slot = i;
        if (slot < 0)
            for (i = 0; i < IPCF_SLOTS; ++i) {
                int d = ipcf.idx[i] > c ? ipcf.idx[i] - c : c - ipcf.idx[i];
                if (d > dist) dist = d, slot = i;
            }
        ipcf.key[slot] = key, ipcf.idx[slot] = a;
        file = cc_url(url, key);
        ipcf.art[slot] = file && cc_decode(ipcf.win, file, 1, ART_SIZE, 0, ipcf.tex + slot * TEXELS)
                             ? ipcf.tex + slot * TEXELS
                             : PLACE; /* no art, or no cache file yet */
        done = 1;
    }
    if (done) ipcf.drawn = 0;
    return done;
}

/* ---------------------------------------------------------------------------
 * The slide and the 3D flip
 */

/* The wheel moved the cursor to album sel: the slide goes there via a critically damped spring (no harsh kick from rest:
 * smooth spring ease-in and ease-out, gliding evenly on steady turns). A gap over IPCF_NEAR albums is closed by whole
 * albums at once (keeping fraction and velocity). Turning the wheel cancels any closing flip immediately. */
/* The shared order (Settings' Albums sort, cc_sort_mode, which the Cover Flow page's "..." card changes too), looked up once a visit, before the
 * level's list is read: the albums copied and sorted as the Cover Flow page does (cc_albums, cc_album_order; Recently Added and Year read the
 * song list once). The copy takes the stock rows, so the caller reads the list again after this. */
void ipcf_order_load(void) {
    void *albums;
    if (!ipcf.frame || ipcf.ordered) return;
    ipcf.ordered = 1;
    albums = cc_albums();
    if (!albums) return;
    ipcf.order_n = deque_size(albums);
    ipcf.order = cc_album_order(albums);
    deque_destroy(albums);
}

/* Cover Flow's list (the stock album rows just read, Unknown Album dropped as cc_albums does) put in that order in place: row i becomes the order's
 * i-th, the records moved whole (each keeps its strings). A list of another size (the library changed under the visit) keeps the stock order. */
void ipcf_arrange(void *list) {
    unsigned n = list ? deque_size(list) : 0, i, j, k;
    unsigned char tmp[REC_SIZE], *done;
    if (!ipcf.order || !n || n != ipcf.order_n || !(done = calloc(n, 1))) return;
    for (i = 0; i < n; ++i) { /* each cycle of the permutation once: new[j] = old[order[j]] */
        if (done[i]) continue;
        memcpy(tmp, deque_at(list, i), REC_SIZE);
        for (j = i;; j = k) {
            done[j] = 1;
            k = ipcf.order[j];
            if (k == i || k >= n) {
                memcpy(deque_at(list, j), tmp, REC_SIZE);
                break;
            }
            memcpy(deque_at(list, j), deque_at(list, k), REC_SIZE);
        }
    }
    free(done);
}

/* Entering Cover Flow: the shelf opens at once (no slide) where Settings > Library > Cover Flow > Start At says, as the full-screen page does
 * (patch/coverflow.c pick_start): the playing track's album (find_playing there: the album key, else the album of that name), else the album
 * last centred on either shelf (coverflow_position), else the first. Its row, or -1: the shelf stays on the first album. */
int ipcf_start(void *list, unsigned count) {
    void *t = cc_playing();
    const char *album = t ? cc_str(t, REC_ALBUM) : "";
    int mode = coverflow_start(), at = -1;
    unsigned key, i;
    if (!ipcf.frame || !list) return -1;
    if (mode == CF_START_PLAYING && *album) {
        key = cc_album_key(t);
        for (i = 0; i < count && at < 0; ++i)
            if (key_of(deque_at(list, i)) == key) at = (int)i;
        for (i = 0; i < count && at < 0; ++i) {
            void *r = deque_at(list, i);
            if (key_of(r) && !cc_nocase(cc_str(r, REC_ALBUM), album)) at = (int)i;
        }
    }
    if (at < 0 && mode != CF_START_FIRST && (key = coverflow_position()) != 0)
        for (i = 0; i < count && at < 0; ++i)
            if (key_of(deque_at(list, i)) == key) at = (int)i;
    if (at < 0) return -1;
    ipcf.pos = ipcf.target = at << 16;
    ipcf.vel = ipcf.fold = ipcf.spd = 0;
    ipcf.drawn = 0;
    return at;
}

void ipcf_goto(int sel) {
    ipcf.rush = 0; /* turning again */
    int t = sel << 16, d = t - ipcf.pos;
    if (!ipcf.frame) return;
    if (ipcf.flip || ipcf.flip_to) ipcf.flip = ipcf.flip_to = 0;
    if (ipcf.pos == ipcf.target && ipcf.vel == 0) ipcf.t0 = time_now_ms();
    ipcf.target = t;
    if (d > IPCF_NEAR << 16)
        ipcf.pos += (d - (IPCF_NEAR << 16) + 0xffff) & ~0xffff;
    else if (d < -(IPCF_NEAR << 16))
        ipcf.pos -= (-d - (IPCF_NEAR << 16) + 0xffff) & ~0xffff;
    if (d) ipcf.dir = d < 0 ? -1 : 1;
    ipcf.drawn = 0;
}

/* The time since an animation's start t0, not counting stalls: a gap between ticks over IPCF_STALL_MS (the first play
 * after boot starting the player cold, a first cover load) moves t0 on so the animation goes on from where it was, frame
 * by frame, instead of jumping to its end. last: the previous tick. */
static int anim_dt(unsigned *t0, unsigned *last) {
    unsigned now = time_now_ms();
    if ((int)(now - *last) > IPCF_STALL_MS) *t0 += now - *last - IPCF_FRAME_MS;
    *last = now;
    return (int)(now - *t0) < 0 ? 0 : (int)(now - *t0);
}

static int flip_step(void) {
    unsigned dt;
    int dur, p, e, next;
    if (ipcf.flip == ipcf.flip_to) return 0;
    dur = ipcf.flip_to > ipcf.flip_from ? ipcf.flip_to - ipcf.flip_from : ipcf.flip_from - ipcf.flip_to;
    dur = dur * IPCF_FLIP_MS / 256;
    if (dur < 1) dur = 1;
    dt = (unsigned)anim_dt(&ipcf.flip_t0, &ipcf.flip_last);
    if ((int)dt >= dur) {
        ipcf.flip = ipcf.flip_to;
        ipcf.drawn = 0;
        return 1;
    }
    p = (int)(dt * 256 / (unsigned)dur);
    e = 256 - ((256 - p) * (256 - p) >> 8); /* ease out 0 .. 256: quick from the press, settling (the iPod's) */
    next = ipcf.flip_from + ((ipcf.flip_to - ipcf.flip_from) * e >> 8);
    if (next == ipcf.flip) next += ipcf.flip_to > ipcf.flip ? 1 : -1;
    ipcf.flip = next;
    ipcf.drawn = 0;
    return 1;
}

/* One step of the go (linear in time, coverflow_morph eases it): IPCF_GO_MS out to Now Playing, IPCF_GO_BACK_MS back. */
static int go_step(void) {
    int dur = ipcf.go_card ? IPCF_GO_CARD_MS
              : ipcf.go_to ? IPCF_GO_MS
                           : IPCF_GO_BACK_MS,
        span = ipcf.go_to - ipcf.go_from, dt;
    dur = dur * (span < 0 ? -span : span) / 256;
    dt = anim_dt(&ipcf.go_t0, &ipcf.go_last);
    if (ipcf.go_hold) { /* arrived: the cover alone at Now Playing's place, then Now Playing */
        if (dt < dur + IPCF_GO_HOLD_MS) return 0;
        ipcf.go_hold = 0;
        return 1;
    }
    if (ipcf.go == ipcf.go_to) return 0;
    ipcf.go = dur < 1 || dt >= dur ? ipcf.go_to : ipcf.go_from + span * dt / dur;
    if (ipcf.go == 256) ipcf.go_hold = 1;
    ipcf.drawn = 0;
    return 1;
}

/* The play key on album sel: its cover goes to Now Playing's place (the textures around it kept for the way back). */
void ipcf_go_open(void *list, unsigned count, int sel) {
    int j;
    if (!ipcf.frame) return;
    ipcf.pos = ipcf.target = sel << 16;
    ipcf.vel = ipcf.fold = ipcf.spd = 0;
    for (j = 0; j < CF_RING; ++j) {
        int a = sel + j - CF_REACH;
        ipcf.go_ring[j] = list && a >= 0 && a < (int)count ? tex_of(list, count, a) : (const unsigned *)0;
    }
    ipcf.go_from = ipcf.go, ipcf.go_to = 256, ipcf.go_card = 0, ipcf.go_hold = 0,
    ipcf.go_t0 = ipcf.go_last = time_now_ms(), ipcf.drawn = 0;
}

/* A track played from the flipped card (row: its row on the card): the card turns on away, and what turns in is its
 * album's cover, straight to Now Playing's place (the iPod's own way). */
void ipcf_go_card(int row) {
    int j;
    if (!ipcf.frame) return;
    for (j = 0; j < CF_RING; ++j) ipcf.go_ring[j] = ipcf.flip_ring[j];
    ipcf.flip_row = row;
    ipcf.go = ipcf.go_from = 0, ipcf.go_to = 256, ipcf.go_card = 1, ipcf.go_hold = 0,
    ipcf.go_t0 = ipcf.go_last = time_now_ms();
    ipcf.drawn = 0;
}

/* MENU from Now Playing that the cover went to: it comes back (from wherever it is); quiet: at once (nothing played). */
void ipcf_go_close(int quiet) {
    if (!ipcf.frame) return;
    ipcf.go_from = quiet ? 0 : ipcf.go, ipcf.go_to = 0, ipcf.go_card = 0, ipcf.go_hold = 0,
    ipcf.go_t0 = ipcf.go_last = time_now_ms(), ipcf.drawn = 0;
    if (quiet) ipcf.go = 0;
}

int ipcf_go_tick(void) { return ipcf.frame ? go_step() : 0; }

/* The finger left the wheel: what is left of the slide closes quicker (the iPod's catch-up when the turning stops). */
void ipcf_rush(void) {
    if (ipcf.frame && (ipcf.pos != ipcf.target || ipcf.vel)) ipcf.rush = 1;
}

static void caption(void *canvas, const char *utf8, int y);

/* The going frame (the caller has filled the screen): the shelf fading and the centre cover moving
 * (coverflow_morph), on the way back with the album's captions already up. */
void ipcf_paint_go(void *canvas, void *list, unsigned count, void *style) {
    int src[4], dst[4];
    if (!ipcf.frame) return;
    if (!ipcf.drawn || ipcf.dflip != -1 - ipcf.go || ipcf.bg != ip_theme_colors()->bg) {
        cfg_t themed;
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ipcf.frame);
        if (!d) return;
        memcpy(&themed, &shelf, sizeof themed);
        themed.bg = ip_theme_colors()->bg;
        int pitch = (int)(bitmap_get_line_length(ipcf.frame) / 4), cy = IP_NP_ART_Y + IP_NP_ART_W / 2 - IPCF_FRAME_Y;
        if (!ipcf.go_card)
            coverflow_morph(&themed, d, pitch, ipcf.go, ipcf.go_ring, IP_NP_ART_X, IP_NP_ART_X + IP_NP_ART_W,
                            IP_NP_ART_W, IP_NP_ART_HR, cy, IP_NP_REFLECT, ipcf.go_to == 0);
        else if (ipcf.go < 128) /* the card turning on, away (its right edge first), its axis easing to where the cover
                                   turns in, so the two halves are one turn */
            coverflow_flip(&themed, d, pitch, 255 - ipcf.go, ipcf.go_ring, IPCF_CARD_Y - IPCF_FRAME_Y, IPCF_CARD_W,
                           IPCF_CARD_H, IPCF_CARD_HDR, IPCF_CARD_ROWS, ipcf.flip_row,
                           themed.cx + (IPCF_TURN_IN_X - themed.cx) * ipcf.go * ipcf.go / (128 * 128), -1,
                           ipcf.face ? FACE : (const unsigned *)0);
        else /* and the cover turning in, to Now Playing's place */
            coverflow_turn_in(&themed, d, pitch, (ipcf.go - 128) * 2, ipcf.go_ring, IPCF_TURN_IN_X, IP_NP_ART_X,
                              IP_NP_ART_X + IP_NP_ART_W, IP_NP_ART_W, IP_NP_ART_HR, cy, IP_NP_REFLECT);
        bitmap_unlock_buffer(ipcf.frame);
        ipcf.drawn = 1, ipcf.dflip = -1 - ipcf.go, ipcf.bg = themed.bg; /* (dflip below 0: a going frame) */
    }
    src[0] = 0, src[1] = 0, src[2] = IP_W, src[3] = IPCF_FRAME_H;
    dst[0] = 0, dst[1] = IPCF_FRAME_Y, dst[2] = IP_W, dst[3] = IPCF_FRAME_H;
    canvas_draw_image(canvas, ipcf.frame, src, dst);
    if (!ipcf.go_to && list && count) {
        void *r = deque_at(list, (unsigned)(ipcf.pos >> 16) < count ? (unsigned)(ipcf.pos >> 16) : count - 1);
        widget_prepare_text_style(style, canvas);
        caption(canvas, cc_str(r, REC_ALBUM), IPCF_CAP_Y);
        caption(canvas, cc_str(r, REC_ARTIST), IPCF_CAP_Y + IPCF_CAP_H);
    }
}

void ipcf_flip_open(void *list, unsigned count, int sel) {
    int j;
    void *r;
    if (!ipcf.frame) return;
    ipcf.pos = ipcf.target = sel << 16;
    ipcf.vel = ipcf.fold = ipcf.spd = 0;
    ipcf.album[0] = ipcf.artist[0] = 0;
    ipcf.face = 0; /* another album's card: patch/ipod.c paints its face before the first frame turns it */
    if (list && (unsigned)sel < count) {
        r = deque_at(list, (unsigned)sel);
        snprintf(ipcf.album, sizeof ipcf.album, "%s", cc_str(r, REC_ALBUM));
        snprintf(ipcf.artist, sizeof ipcf.artist, "%s", cc_str(r, REC_ARTIST));
    }
    for (j = 0; j < CF_RING; ++j) {
        int a = sel + j - CF_REACH;
        ipcf.flip_ring[j] = list && a >= 0 && a < (int)count ? tex_of(list, count, a) : (const unsigned *)0;
    }
    ipcf.flip_from = ipcf.flip;
    ipcf.flip_to = 256;
    ipcf.flip_t0 = ipcf.flip_last = time_now_ms();
    ipcf.flip_row = 0;
    ipcf.drawn = 0;
}

void ipcf_flip_close(int row) {
    if (!ipcf.frame) return;
    ipcf.flip_row = row;
    if (ipcf.flip >= 256)
        ipcf.flip =
            255; /* at 256 the frame holds no card (ip_paint_cf_card paints it), so the first closing frame would be a blank gap */
    ipcf.flip_from = ipcf.flip;
    ipcf.flip_to = 0;
    ipcf.flip_t0 = ipcf.flip_last = time_now_ms();
    ipcf.drawn = 0;
}

/* The card's face for patch/ipod.c to paint into (NULL without Cover Flow), and that it holds the card now (ok 1) or not. */
unsigned *ipcf_face(void) { return ipcf.frame ? FACE : (unsigned *)0; }
int ipcf_face_ok(void) { return ipcf.face; }
void ipcf_face_done(int ok) {
    ipcf.face = ok;
    ipcf.drawn = 0; /* the flip frame turns the new face */
}

void ipcf_flip_settle(void) {
    if (!ipcf.frame) return;
    if (ipcf.flip != ipcf.flip_to) ipcf.flip = ipcf.flip_to, ipcf.drawn = 0;
}

int ipcf_flip_tick(void) { return ipcf.frame ? flip_step() : 0; }

/* One tick of the page's timer: the slide moves, any closing flip advances, and one wanted cover is decoded.
 * list / count are the front level's stock list (valid). 1: the screen needs painting.
 * The slide is a critically damped spring (time constant IPCF_TAU_MS) stepped per ms, its speed held to IPCF_VMAX. */
int ipcf_tick(void *list, unsigned count) {
    unsigned now = time_now_ms();
    int changed = 0, c;
    if (!ipcf.frame) return 0;
    if (list && count) /* the album the shelf stops on: the position kept for both shelves */
        ipcf.centre =
            key_of(deque_at(list, (unsigned)(ipcf.target >> 16) < count ? (unsigned)(ipcf.target >> 16) : count - 1));
    if (ipcf.go != ipcf.go_to || ipcf.go_hold)
        return go_step(); /* coming back from Now Playing: nothing slides or decodes meanwhile */
    if (flip_step()) changed = 1;
    if (ipcf.pos != ipcf.target || ipcf.vel != 0) {
        int dt = (int)(now - ipcf.t0), start = ipcf.pos, max_pos = count ? ((int)count - 1) << 16 : 0;
        if (dt < 1) dt = 1;
        if (dt > 100) dt = 100;
        int tau = ipcf.rush ? IPCF_RUSH_TAU_MS : IPCF_TAU_MS, vmax = ipcf.rush ? IPCF_RUSH_VMAX : IPCF_VMAX;
        while (dt--) {
            int gap = ipcf.target - ipcf.pos, tau2 = tau * tau;
            int acc = (gap / tau2) * 1024 + (gap % tau2) * 1024 / tau2 - 2 * ipcf.vel / tau;
            ipcf.vel += acc;
            if (ipcf.vel > vmax) ipcf.vel = vmax;
            if (ipcf.vel < -vmax) ipcf.vel = -vmax;
            ipcf.pos += ipcf.vel / 1024;
            if (ipcf.pos < 0) ipcf.pos = 0, ipcf.vel = 0;
            if (ipcf.pos > max_pos) ipcf.pos = max_pos, ipcf.vel = 0;
        }
        if (ipcf.pos == start && ipcf.pos != ipcf.target) ipcf.pos += ipcf.target > ipcf.pos ? 1 : -1;
        {
            int gap = ipcf.target - ipcf.pos, av = ipcf.vel < 0 ? -ipcf.vel : ipcf.vel;
            if (gap < IPCF_DONE && -gap < IPCF_DONE && av < IPCF_VSTOP)
                ipcf.pos = ipcf.target, ipcf.vel = 0, ipcf.rush = 0;
        }
        changed = 1;
    }
    { /* the fold follows the smoothed speed: laid flat into a deck on a glide, opening back as it slows */
        int dt = (int)(now - ipcf.t0), v = ipcf.vel < 0 ? -ipcf.vel : ipcf.vel, was = ipcf.fold;
        if (dt < 1) dt = 1;
        if (dt > 100) dt = 100;
        ipcf.spd += (v - ipcf.spd) * dt / (dt + IPCF_SPD_MS);
        ipcf.fold = ipcf.spd <= IPCF_FOLD_V0   ? 0
                    : ipcf.spd >= IPCF_FOLD_V1 ? 256
                                               : (ipcf.spd - IPCF_FOLD_V0) / ((IPCF_FOLD_V1 - IPCF_FOLD_V0) >> 8);
        if (!ipcf.fold && ipcf.pos == ipcf.target && ipcf.vel == 0)
            ipcf.spd = 0; /* at rest under the fold: no residue for the next step */
        if (ipcf.fold != was) changed = 1;
    }
    ipcf.t0 = now;
    if (count && !ipcf.flip) {
        c = (ipcf.pos + CF_ONE / 2) >> 16;
        if (c < 0) c = 0;
        if (c >= (int)count) c = (int)count - 1;
        if (fill(list, count, c)) changed = 1;
    } else if (!count)
        ipcf.more = 0;
    return changed;
}

/* ---------------------------------------------------------------------------
 * Paint
 */

/* The utf-8 text centred in the screen's width in the style the canvas has (dark 18 px: label_ip_row), cut with an ellipsis, in the line at y. */
static void caption(void *canvas, const char *utf8, int y) {
    unsigned wide[64], n = 0, len;
    int rect[4], w;
    while (utf8[n]) n++;
    if (!n) return;
    tk_utf8_to_utf16_ex(utf8, n, wide, 64);
    len = ip_fit(canvas, wide, IP_W - 24);
    if (!len) return;
    w = (int)(canvas_measure_text(canvas, wide, len) + 0.999f);
    rect[0] = (IP_W - w) / 2, rect[1] = y, rect[2] = w + 2, rect[3] = IPCF_CAP_H;
    canvas_draw_text_in_rect(canvas, wide, len, rect);
}

static void draw_flip_frame(void *canvas, const unsigned *const ring[CF_RING], int sel_row) {
    int src[4], dst[4];
    if (!ipcf.drawn || ipcf.dflip != ipcf.flip || ipcf.drow != sel_row || ipcf.bg != ip_theme_colors()->bg) {
        cfg_t themed;
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ipcf.frame);
        if (!d) return;
        memcpy(&themed, &shelf, sizeof themed);
        themed.bg = ip_theme_colors()->bg;
        coverflow_flip(&themed, d, (int)(bitmap_get_line_length(ipcf.frame) / 4), ipcf.flip, ring,
                       IPCF_CARD_Y - IPCF_FRAME_Y, IPCF_CARD_W, IPCF_CARD_H, IPCF_CARD_HDR, IPCF_CARD_ROWS, sel_row,
                       themed.cx, 1, ipcf.face ? FACE : (const unsigned *)0);
        bitmap_unlock_buffer(ipcf.frame);
        ipcf.drawn = 1, ipcf.dflip = ipcf.flip, ipcf.drow = sel_row, ipcf.bg = themed.bg;
    }
    src[0] = 0, src[1] = 0, src[2] = IP_W, src[3] = IPCF_FRAME_H;
    dst[0] = 0, dst[1] = IPCF_FRAME_Y, dst[2] = IP_W, dst[3] = IPCF_FRAME_H;
    canvas_draw_image(canvas, ipcf.frame, src, dst);
}

/* Paint the 3D opening flip while K_CF_TRACKS is in front and flip < 256 (uses the textures captured before the tracks query); at 0, before
 * the first tick, it is the shelf's cover, so the screen never paints blank between the press and the flip. */
void ipcf_paint_flip(void *canvas, int sel_row) {
    if (!ipcf.frame || ipcf.flip < 0 || ipcf.flip >= 256) return;
    draw_flip_frame(canvas, ipcf.flip_ring, sel_row);
}

/* Paint the visible Cover Flow side covers + drop shadow behind the settled floating tracklist card (flip == 256). */
void ipcf_paint_bg(void *canvas) {
    if (!ipcf.frame) return;
    draw_flip_frame(canvas, ipcf.flip_ring, -1);
}

/* The screen under the title bar (the caller has filled it white and paints the bar after): the frame (covers and reflections on white) at IPCF_FRAME_Y, the album under the
 * centre cover and its artist in style (the list rows' dark text). list is NULL while the stock list is stale (nothing). */
void ipcf_paint(void *canvas, void *list, unsigned count, void *style) {
    const unsigned *ring[CF_RING];
    int c, frac, dir, j, src[4], dst[4];
    void *r;
    if (!ipcf.frame || !list) return;
    widget_prepare_text_style(style, canvas);
    if (!count) {
        caption(canvas, TR("No songs"), IP_SCREEN_H / 2 - IPCF_CAP_H / 2);
        return;
    }
    c = (ipcf.pos + CF_ONE / 2) >> 16;
    if (c < 0) c = 0;
    if (c >= (int)count) c = (int)count - 1;
    ipcf.centre = key_of(deque_at(list, (unsigned)c));
    if (ipcf.flip > 0) {
        for (j = 0; j < CF_RING; ++j) {
            int a = c + j - CF_REACH;
            ring[j] = a >= 0 && a < (int)count ? tex_of(list, count, a) : (const unsigned *)0;
        }
        draw_flip_frame(canvas, ring, ipcf.flip_row);
        return;
    }
    frac = ipcf.pos - (c << 16);
    dir = ipcf.vel > 0 ? 1 : ipcf.vel < 0 ? -1 : 0; /* the deck's covers coming in lie on top */
    if (list != ipcf.list || count != ipcf.count) ipcf.list = list, ipcf.count = count, ipcf.drawn = 0;
    if (!ipcf.drawn || ipcf.dflip != 0 || c != ipcf.dc || frac != ipcf.dfrac || ipcf.fold != ipcf.dfold ||
        dir != ipcf.ddir || ipcf.bg != ip_theme_colors()->bg) {
        cfg_t themed;
        memcpy(&themed, &shelf, sizeof themed);
        unsigned *d = (unsigned *)bitmap_lock_buffer_for_write(ipcf.frame);
        if (!d) return;
        for (j = 0; j < CF_RING; ++j) {
            int a = c + j - CF_REACH;
            ring[j] = a >= 0 && a < (int)count ? tex_of(list, count, a) : (const unsigned *)0;
        }
        themed.bg = ip_theme_colors()->bg;
        themed.fold = ipcf.fold, themed.dir = dir;
        coverflow_render(&themed, d, (int)(bitmap_get_line_length(ipcf.frame) / 4), frac, ring);
        bitmap_unlock_buffer(ipcf.frame);
        ipcf.drawn = 1, ipcf.dc = c, ipcf.dfrac = frac, ipcf.dfold = ipcf.fold, ipcf.ddir = dir, ipcf.dflip = 0;
        ipcf.bg = themed.bg;
    }
    src[0] = 0, src[1] = 0, src[2] = IP_W, src[3] = IPCF_FRAME_H;
    dst[0] = 0, dst[1] = IPCF_FRAME_Y, dst[2] = IP_W, dst[3] = IPCF_FRAME_H;
    canvas_draw_image(canvas, ipcf.frame, src, dst);
    r = deque_at(list, (unsigned)c);
    caption(canvas, cc_str(r, REC_ALBUM), IPCF_CAP_Y);
    caption(canvas, cc_str(r, REC_ARTIST), IPCF_CAP_Y + IPCF_CAP_H);
}
