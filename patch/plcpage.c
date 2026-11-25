/* The Cover page: a stock playlist's generated cover, chosen from Edit mode (docs/modules/plcover.md "Cover page").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The Songs page (patch/songs.c) hands over the playlist (id, name) and the keys of its albums' covers (grid_mosaic_keys) through plcpage_open and opens the page. The page holds one card (pod_cover, a view
 * we paint): six thumbnails, Albums (the 2x2 mosaic of the albums, drawn by the grid's own code) and the five styles of plc_art at the thumbnail's size, from the playlist's current tones, each with a name under it
 * (pod_covl<k> labels); the chosen one has the ring image (pod_covring) round it. Under the card the generic rows: the Name on Cover switch (PLC_FLAG_NAME; dimmed and inert while Albums is chosen, for which nothing is
 * stored) and the note.
 *
 * Drawing is one thumbnail a 30 ms tick (a Mesh tile at this size is a few million instructions), after the tones have been collected in a tick of their own: the first three of the playlist's cover keys, each from
 * the tone cache (m1_tone_get) or, when it is not there, the key's cache file reduced to one pixel (the Daily Mix's way). Until a thumbnail is drawn its place is grey.
 *
 * A tap on a thumbnail stores it at once (plc_set; Albums removes the entry) with the current tones and flags; a tap on the chosen one stores it again, which takes the colours the playlist has now. The switch
 * changes the flag alone (the stored tones stay). A write that fails
 * (no card) toasts and moves nothing. The Songs page remakes its header from plc_get when it comes back to the front.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "grid.h"
#include "covercache.h"
#include "peqpage.h"
#include "entries.h"
#include "plcover.h"

#define PC_TICK_MS 30
#define PCV_TILES 6
#define PC_LAB_H \
    18 /* (tools/pod_settings.py COVER_LAB_Y, COVER_LAB_H: a cell's hit height is the thumbnail and its name) */
#define PC_CELL_H (98 + PC_LAB_H)

static struct {
    void *win, *view, *ring;
    int id, nk, style, nt, tones_done, open, page;
    unsigned flags, key[4], tones[3], seed, timer;
    char name[PLC_NAME_MAX];
    grid_t g;
    unsigned *tmp;
    m1_tap_t tap;
    int down; /* the cell pressed + 1 */
} pc __attribute__((section(".scratch")));

int plcpage_open(int id, const char *name, const unsigned *key, int nk) {
    plc_t c;
    int i;
    if (!name || !*name || nk < 0 || nk > 4 || (nk && !key)) return -1;
    memset(&pc, 0, sizeof pc);
    pc.id = id, pc.nk = nk;
    snprintf(pc.name, sizeof pc.name, "%s", name);
    for (i = 0; i < nk; ++i) pc.key[i] = key[i];
    if (plc_get(id, pc.name, &c)) pc.style = c.style, pc.flags = c.flags;
    pc.open = 1;
    if (pod_open_plcover() < 0) { /* (the page did not open: nothing to keep) */
        memset(&pc, 0, sizeof pc);
        return -1;
    }
    return 0;
}

/* The tones of the playlist's albums: the first three non-zero cover keys (m1_tone words). */
static void pc_collect(void) {
    int i;
    if (pc.tones_done) return;
    pc.tones_done = 1, pc.nt = 0;
    for (i = 0; i < pc.nk && pc.nt < 3; ++i) {
        unsigned tone, px;
        char url[80];
        const char *file;
        if (!pc.key[i]) continue;
        if (m1_tone_get(pc.key[i], &tone))
            pc.tones[pc.nt++] = tone;
        else if (pc.win && (file = cc_url(url, pc.key[i])) != (const char *)0 &&
                 cc_decode(pc.win, file, 1, 1, 1, &px)) {
            tone = m1_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
            m1_tone_put(pc.key[i], tone);
            pc.tones[pc.nt++] = tone;
        }
    }
}

int plcpage_style(void) { return pc.style; }

static void pc_labels(void) {
    char name[16];
    int k;
    for (k = 0; k < PCV_TILES; ++k) {
        void *l;
        snprintf(name, sizeof name, "pod_covl%d", k);
        l = pc.win ? widget_lookup(pc.win, name, 1) : (void *)0;
        if (l) peq_label_colors(l, k == pc.style ? "#FFFFFF" : "#8E8E93");
    }
}

static void pc_redraw(void) {
    if (pc.view) widget_invalidate_force(pc.view, (void *)0);
}

/* The next thumbnail to draw, in order: the mosaic (a source a tick), then the styles. */
static int pc_next(void) {
    int k;
    if (!pc.g.tiles) return -1;
    for (k = 0; k < PCV_TILES; ++k)
        if (!pc.g.tiles[k].art) return k;
    return -1;
}

static void pc_arm(void);

static int pc_tick(const void *unused) {
    int k;
    (void)unused;
    pc.timer = 0;
    if (!pc.win || !pc.g.tiles) return RET_OK;
    if (!pc.tones_done) {
        pc_collect();
        pc_arm();
        return RET_OK;
    }
    k = pc_next();
    if (k >= 0) {
        grid_tile_t *t = &pc.g.tiles[k];
        if (k == 0) {
            if (!pc.nk)
                t->art = 2;
            else {
                if (!t->nq) t->nq = pc.nk, t->qi = 0, memcpy(t->qkey, pc.key, sizeof t->qkey);
                grid_mosaic(&pc.g, t, pc.tmp);
            }
        } else {
            plc_t c;
            int i;
            memset(&c, 0, sizeof c);
            c.style = k, c.seed = pc.seed, c.nt = pc.nt;
            for (i = 0; i < pc.nt; ++i) c.tones[i] = pc.tones[i];
            grid_plc(&pc.g, t, &c);
        }
        pc_redraw();
    }
    pc_arm();
    return RET_OK;
}

static void pc_arm(void) {
    if (!pc.timer && pc.win && (!pc.tones_done || pc_next() >= 0)) pc.timer = timer_add(pc_tick, (void *)0, PC_TICK_MS);
}

static void pc_blit(void *canvas, void *bmp, int w, int h, int x, int y) {
    int src[4], dst[4];
    if (!bmp) return;
    src[0] = 0, src[1] = 0, src[2] = w, src[3] = h;
    dst[0] = x, dst[1] = y, dst[2] = w, dst[3] = h;
    canvas_draw_image(canvas, bmp, src, dst);
}

static int pc_x(int k) { return PLP_X + k % 3 * PLP_PX; }
static int pc_y(int k) { return k / 3 * PLP_PY + PLP_TY; }

/* pod_cover's EVT_BEFORE_PAINT: the thumbnails (grey where not drawn yet), then the ring round the chosen one. */
static int pc_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int k;
    (void)ctx;
    if (!canvas || !pc.win || !pc.g.tiles) return RET_OK;
    for (k = 0; k < PCV_TILES; ++k) {
        grid_tile_t *t = &pc.g.tiles[k];
        if (t->art) {
            grid_blit(canvas, &pc.g, t, pc_x(k), pc_y(k), 0);
            t->nm = k && plcpage_name_on(); /* (the switch moves no bitmap) */
            grid_plc_name(canvas, &pc.g, t, pc.name, pc_x(k), pc_y(k), 0);
        } else {
            ui_fill_color(canvas, GRID_GREY);
            canvas_fill_rect(canvas, pc_x(k), pc_y(k), PLP_T, PLP_T);
        }
    }
    pc_blit(canvas, pc.ring, PLP_RING, PLP_RING, pc_x(pc.style) - PLP_GROW, pc_y(pc.style) - PLP_GROW);
    return RET_OK;
}

/* The thumbnail (its name too) under a point of the card, or -1. */
static int pc_cell(const int *pt) {
    int cx = pt[0] - PLP_X, cy = pt[1], col, row;
    if (cx < 0 || cy < 0) return -1;
    col = cx / PLP_PX, row = cy / PLP_PY;
    if (col > 2 || row > 1 || cx % PLP_PX >= PLP_T || cy % PLP_PY >= PC_CELL_H) return -1;
    return row * 3 + col;
}

static int pc_on_down(void *ctx, void *e) {
    int pt[2];
    (void)ctx;
    pc.down = 0;
    if (!e || !pc.view) return RET_OK;
    grid_ev_local(pc.view, e, pt);
    pc.down = pc_cell(pt) + 1;
    m1_tap_at(&pc.tap, e);
    return RET_OK;
}

/* Stores what is drawn on the chosen thumbnail: -1 (nothing changed) when the card did not take it. */
static int pc_store(int style, unsigned flags) {
    pc_collect();
    if (plc_set(pc.id, pc.name, style, flags, pc.tones, pc.nt) < 0) {
        pod_toast(TR("Can't change cover"));
        return -1;
    }
    return 0;
}

/* Albums removed the entry, and with it the seed a rename kept (plc_rename): the next style stored takes the seed of the name as it is now
 * (plc_seed), so the thumbnails of the styles are drawn again with it, and the preview stays what a tap stores. */
static void pc_reseed(void) {
    unsigned seed = plc_seed(pc.id, pc.name);
    int k;
    if (seed == pc.seed || !pc.g.tiles) return;
    pc.seed = seed;
    for (k = 1; k < PCV_TILES; ++k) grid_free_art(&pc.g.tiles[k]), pc.g.tiles[k].art = 0;
    pc_arm();
}

static int pc_on_up(void *ctx, void *e) {
    int pt[2], k = pc.down - 1;
    (void)ctx;
    pc.down = 0;
    if (k < 0 || !e || !pc.view || !m1_tap_near(&pc.tap, e)) return RET_OK;
    grid_ev_local(pc.view, e, pt);
    if (pc_cell(pt) != k || pc_store(k, k ? pc.flags : 0) < 0) return RET_OK;
    pc.style = k;
    if (!k) pc.flags = 0, pc_reseed();
    pc_labels();
    pc_redraw();
    pod_page_refresh(pc.page); /* the switch follows: dimmed and off for Albums */
    return RET_OK;
}

static int pc_gone(void *ctx, void *e) {
    (void)e;
    if (ctx != pc.win) return RET_OK;
    m1_timer_stop(&pc.timer);
    grid_free(&pc.g);
    if (pc.tmp) free(pc.tmp);
    if (pc.ring) bitmap_destroy(pc.ring);
    memset(&pc, 0, sizeof pc);
    return RET_OK;
}

void plcpage_opened(void *win, int page) {
    void *v;
    if (!win || !pc.open) return;
    v = widget_lookup(win, "pod_cover", 1);
    pc.win = win, pc.view = v, pc.page = page;
    pc.seed = plc_seed(pc.id, pc.name);
    pc.tmp = calloc((PLP_T / 2) * (PLP_T / 2), 4);
    pc.ring = m1_asset_rgba(win, "pod_covring", PLP_RING, PLP_RING, 0);
    if (!v || !pc.tmp || !grid_init(&pc.g, win, PCV_TILES, PLP_T, PLP_R)) {
        pc_gone(win, (void *)0);
        return;
    }
    grid_placeholder(&pc.g);
    pc.g.st_title = widget_lookup(win, "pod_covname", 1);
    widget_on(v, EVT_BEFORE_PAINT, (void *)pc_paint, (void *)0);
    widget_on(v, EVT_POINTER_DOWN, (void *)pc_on_down, (void *)0);
    widget_on(v, EVT_POINTER_UP, (void *)pc_on_up, (void *)0);
    widget_on(win, EVT_DESTROY, (void *)pc_gone, win);
    pc_labels();
    pc_arm();
}

/* Name on Cover (the switch): PLC_FLAG_NAME of the stored cover; the switch row is inert for Albums. */
int plcpage_name_on(void) { return pc.style != 0 && (pc.flags & PLC_FLAG_NAME) != 0; }

/* The flag alone changes: the stored tones stay (the playlist's current ones may differ: emptied, it has none, and the cover would turn grey). */
int plcpage_name_toggle(void) {
    unsigned flags = pc.flags ^ PLC_FLAG_NAME;
    plc_t c;
    if (!pc.style) return -1;
    if (!plc_get(pc.id, pc.name, &c)) {
        if (pc_store(pc.style, flags) < 0) return -1;
    } else if (plc_set(pc.id, pc.name, c.style, flags, c.tones, c.nt) < 0) {
        pod_toast(TR("Can't change cover"));
        return -1;
    }
    pc.flags = flags;
    pc_redraw(); /* the names on the thumbnails come or go now (the switch row repaints only itself) */
    return (flags & PLC_FLAG_NAME) != 0;
}
