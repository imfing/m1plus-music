/* The album grid shared by the Albums page and the Recently Played shelf (patch/grid.h has the design).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Moved from patch/albums.c (the Albums grid's tiles, loader, paint and hit test) with one addition: the corner radius.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"

void grid_shape(grid_t *g, int side, int round, int blend) {
    if (round > GRID_MAX_ROUND) round = GRID_MAX_ROUND;
    if (round < 0) round = 0;
    g->side = side, g->round = round, g->blend = blend;
    if (round) pod_corner_fill(g->corner, (unsigned)round);
}

int grid_init(grid_t *g, void *win, int n, int side, int round) {
    memset(g, 0, sizeof *g);
    g->win = win, g->n = n;
    grid_shape(g, side, round, 0);
    g->tiles = calloc((unsigned)n, sizeof(grid_tile_t));
    return g->tiles != (grid_tile_t *)0;
}

void grid_free_art(grid_tile_t *t) {
    if (t->bmp) bitmap_destroy(t->bmp);
    t->bmp = (void *)0;
}

void grid_drop(grid_t *g) {
    int i;
    for (i = 0; g->tiles && i < g->n; ++i) grid_free_art(&g->tiles[i]);
    if (g->tiles) memset(g->tiles, 0, (unsigned)g->n * sizeof(grid_tile_t));
    if (g->placeholder) bitmap_destroy(g->placeholder);
    g->placeholder = (void *)0;
}

void grid_free(grid_t *g) {
    grid_drop(g);
    if (g->chev) bitmap_destroy(g->chev);
    g->chev = (void *)0;
    free(g->tiles);
    g->tiles = (grid_tile_t *)0;
}

/* A side x side RGBA bitmap, its pixels locked in *px for the caller to fill (then bitmap_unlock_buffer), flagged opaque (a plain blit: the
 * rounded corners are blended into black in the pixels, grid_round) unless the corners are cut in the alpha (g->blend); NULL if it cannot be made. */
static void *grid_bitmap(grid_t *g, unsigned **px) {
    void *b = bitmap_create_ex(g->side, g->side, g->side * 4, BITMAP_RGBA8888);
    unsigned *d = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
    if (b && (!d || bitmap_get_line_length(b) != (unsigned)g->side * 4)) {
        if (d) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    if (b && !(g->blend && g->round)) *(unsigned short *)((char *)b + BITMAP_FLAGS) |= 1; /* OPAQUE: every pixel is */
    *px = d;
    return b;
}

/* The four corners blended into black, the colour both grids lie on (the Albums view, the menu's list): each channel keeps 255 less the
 * coverage outside the arc, alpha stays 255. Done once per tile, so a frame blits opaque tiles and blends nothing. Pixels the arc leaves
 * whole are skipped; v * a / 255 is (t + 1 + (t >> 8)) >> 8 with t = v * a, exact for every t up to 255 * 255 (no division). */
#define GRID_DIV255(t) (((t) + 1 + ((t) >> 8)) >> 8)
static void grid_round(grid_t *g, unsigned *px) {
    unsigned k, x, y, r = (unsigned)g->round, s = (unsigned)g->side;
    for (k = 0; r && k < 4; ++k)
        for (y = 0; y < r; ++y)
            for (x = 0; x < r; ++x) {
                unsigned *p = px + (k & 2 ? s - 1 - y : y) * s + (k & 1 ? s - 1 - x : x),
                         a = 255u - g->corner[y * r + x];
                if (a == 255) continue;
                if (g->blend)
                    *p = (*p & 0xffffff) | a << 24; /* cut in the alpha: whatever lies behind shows */
                else
                    *p = 0xff000000u | GRID_DIV255((*p & 255) * a) | GRID_DIV255((*p >> 8 & 255) * a) << 8 |
                         GRID_DIV255((*p >> 16 & 255) * a) << 16;
            }
}

void grid_placeholder(grid_t *g) {
    unsigned *px;
    int i;
    g->placeholder = grid_bitmap(g, &px);
    if (!g->placeholder) return;
    for (i = 0; i < g->side * g->side; ++i) px[i] = GRID_GREY;
    cc_decode(g->win, GRID_PLACEHOLDER, 0, (unsigned)g->side, 1, px);
    grid_round(g, px);
    bitmap_unlock_buffer(g->placeholder);
}

static int grid_width(void *canvas, const unsigned *s, unsigned n) {
    float w = canvas_measure_text(canvas, s, n);
    return (int)(w + 0.999f);
}

/* The wide string s (NUL-terminated), cut with an ellipsis to maxw px: the longest prefix whose width with the ellipsis fits (the widths
 * grow with the prefix, so a binary search). The canvas has the text's style. Its length. */
static int grid_fit(void *canvas, unsigned *s, int maxw) {
    unsigned len = 0, lo, hi;
    while (s[len]) len++;
    if (len && grid_width(canvas, s, len) > maxw) {
        lo = 0, hi = len - 1; /* the prefix kept; the last char never fits with the ellipsis after it */
        while (lo < hi) {
            unsigned mid = (lo + hi + 1) / 2, keep = s[mid];
            s[mid] = ELLIPSIS;
            if (grid_width(canvas, s, mid + 1) <= maxw)
                lo = mid;
            else
                hi = mid - 1;
            s[mid] = keep;
        }
        s[lo] = ELLIPSIS;
        s[lo + 1] = 0;
        len = lo + 1;
    }
    return (int)len;
}

static void grid_wide(unsigned *dst, const char *s) {
    unsigned n = 0;
    while (s[n] && n < 255) n++;
    tk_utf8_to_utf16_ex(s, n, dst, GRID_TEXT);
}

grid_tile_t *grid_find(grid_t *g, int a) {
    int i;
    for (i = 0; i < g->n; ++i)
        if (g->tiles[i].album == a + 1) return &g->tiles[i];
    return (grid_tile_t *)0;
}

int grid_moving(void *sv) {
    void *wa;
    if (!sv) return 0;
    if (*(unsigned char *)((char *)sv + SC_PRESSED) && *(unsigned char *)((char *)sv + SC_DRAGGED)) return 1;
    wa = *(void **)((char *)sv + SC_WA);
    return wa && *(int *)((char *)wa + SC_AN_STATE) == SC_AN_RUNNING && *(void **)((char *)wa + SC_AN_WIDGET) == sv;
}

grid_tile_t *grid_tile(grid_t *g, int a, int lo, int hi, int *fresh) {
    grid_tile_t *t = g->tiles, *victim = (grid_tile_t *)0, *any = g->tiles;
    int i;
    *fresh = 0;
    for (i = 0; i < g->n; ++i, ++t) {
        if (t->album == a + 1) {
            t->stamp = ++g->clock;
            return t;
        }
        if (!t->album) {
            if (!victim || victim->album) victim = t;
        } else {
            if (t->stamp < any->stamp || !any->album) any = t;
            if ((t->album - 1 < lo || t->album - 1 > hi) && (!victim || (victim->album && t->stamp < victim->stamp)))
                victim = t;
        }
    }
    t = victim ? victim : any;
    grid_free_art(t);
    memset(t, 0, sizeof *t);
    t->album = a + 1;
    t->stamp = ++g->clock;
    *fresh = 1;
    return t;
}

void grid_set(grid_tile_t *t, const char *album, const char *artist, unsigned ckey) {
    t->ckey = ckey;
    grid_wide(t->title, album);
    grid_wide(t->artist, artist);
}

void grid_art(grid_t *g, grid_tile_t *t) {
    char url[80];
    grid_art_url(g, t, cc_url(url, t->ckey));
}

void grid_art_url(grid_t *g, grid_tile_t *t, const char *file) {
    unsigned *px;
    void *b;
    t->art = 2;
    if (!file || !(b = grid_bitmap(g, &px))) return;
    if (cc_decode(g->win, file, 1, (unsigned)g->side, 1, px)) {
        grid_round(g, px);
        t->bmp = b, t->art = 1;
    }
    bitmap_unlock_buffer(b);
    if (!t->bmp) bitmap_destroy(b);
}

void grid_mosaic(grid_t *g, grid_tile_t *t, unsigned *tmp) {
    static const unsigned char QUAD[5][4] = {{0, 0, 0, 0},
                                             {0, 0, 0, 0},
                                             {0, 1, 1, 0},
                                             {0, 1, 2, 0},
                                             {0, 1, 2, 3}}; /* the source in each quadrant (row-major) */
    int half = g->side / 2, side = g->side, q, r, i = t->qi;
    char url[80];
    const char *file;
    unsigned *px;
    if (t->nq < 2) { /* no cover: the placeholder; one: the cover itself */
        t->ckey = t->nq ? t->qkey[0] : 0;
        grid_art(g, t);
        return;
    }
    if (t->nq > 4) t->nq = 4;
    if (!t->bmp) {
        int k;
        t->bmp = grid_bitmap(g, &px);
        if (!t->bmp) {
            t->art = 2;
            return;
        }
        for (k = 0; k < side * side; ++k) px[k] = GRID_GREY;
    } else
        px = (unsigned *)bitmap_lock_buffer_for_write(t->bmp);
    file = cc_url(url, t->qkey[i]);
    if (!file || !cc_decode(g->win, file, 1, (unsigned)half, 1, tmp))
        for (r = 0; r < half * half; ++r) tmp[r] = GRID_GREY;
    for (q = 0; q < 4; ++q) {
        if (QUAD[t->nq][q] != i) continue;
        for (r = 0; r < half; ++r)
            memcpy(px + ((q >> 1) * half + r) * side + (q & 1) * half, tmp + r * half, (unsigned)half * 4);
    }
    t->qi = ++i;
    if (i >= t->nq) {
        grid_round(g, px);
        t->art = 1;
    }
    bitmap_unlock_buffer(t->bmp);
}

int grid_cell_x(int i) { return GRID_MARGIN + i % GRID_COLS * GRID_COL_PITCH; }
int grid_cell_y(int i, int origin_y) { return origin_y + i / GRID_COLS * GRID_PITCH; }

int grid_cell_at(int x, int y, int origin_y, int count) {
    int cy = y - origin_y, cx = x - GRID_MARGIN, row, col, a;
    if (cy < 0 || cx < 0) return -1;
    row = cy / GRID_PITCH, col = cx / GRID_COL_PITCH;
    if (cy % GRID_PITCH >= GRID_CELL_H || cx % GRID_COL_PITCH >= GRID_COVER || col >= GRID_COLS) return -1;
    a = row * GRID_COLS + col;
    return a < count ? a : -1;
}

void grid_blit(void *canvas, grid_t *g, grid_tile_t *t, int x, int y, int view_h) {
    void *bmp = t->art == 1 ? t->bmp : g->placeholder;
    int top = y < 0 ? -y : 0, bottom = view_h > 0 && y + g->side > view_h ? view_h - y : g->side;
    int src[4], dst[4];
    if (!bmp || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = g->side, src[3] = bottom - top;
    dst[0] = x, dst[1] = y + top, dst[2] = g->side, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

void grid_text(void *canvas, grid_tile_t *t, int pass, int x, int y, int w, int h, int view_h) {
    unsigned *s = pass ? t->artist : t->title;
    int *len = pass ? &t->aw : &t->tw, fit = pass ? GRID_FIT_ARTIST : GRID_FIT_TITLE;
    int rect[4];
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    if (!(t->fit & fit)) *len = grid_fit(canvas, s, w), t->fit |= fit;
    if (*len && (view_h <= 0 || (y >= 0 && y + h <= view_h))) canvas_draw_text_in_rect(canvas, s, (unsigned)*len, rect);
}

void grid_paint(void *canvas, grid_t *g, int first, int last, int origin_y, int view_h,
                grid_tile_t *(*tile_of)(void *, int), void *ctx) {
    int a, pass;
    for (a = first; a < last; ++a)
        grid_blit(canvas, g, tile_of(ctx, a), grid_cell_x(a), grid_cell_y(a, origin_y), view_h);
    for (
        pass = 0; pass < 2;
        ++pass) { /* albums, then artists: one text style at a time, cut at the view's edges by the scroll_view's clip */
        widget_prepare_text_style(pass ? g->st_sub : g->st_title, canvas);
        for (a = first; a < last; ++a)
            grid_text(canvas, tile_of(ctx, a), pass, grid_cell_x(a),
                      grid_cell_y(a, origin_y) + GRID_COVER + GRID_TITLE_GAP + (pass ? GRID_TITLE_H : 0), GRID_COVER,
                      pass ? GRID_SUB_H : GRID_TITLE_H, 0);
    }
}

/* Fills x0..x1 of the rows [y0, y1) of the window with colour c (cut to the window by hand). */
static void grid_fill(void *canvas, int x0, int x1, int y0, int y1, unsigned c, int view_h) {
    if (y0 < 0) y0 = 0;
    if (y1 > view_h) y1 = view_h;
    if (y1 <= y0 || x1 <= x0) return;
    ui_fill_color(canvas, c);
    canvas_fill_rect(canvas, x0, y0, x1 - x0, y1 - y0);
}

/* The y of list row r in the content: after the section headers above it when the page has them (g->az), else r * LIST_ROW_H. */
static int grid_row_y(const grid_t *g, int r) { return g->az ? az_row_y((const az_t *)g->az, r) : r * LIST_ROW_H; }

void grid_list_paint(void *canvas, grid_t *g, void *st_title, void *st_sub, int r0, int r1, int off, int view_h,
                     int press, int shift, int chev, grid_tile_t *(*tile_of)(void *, int), void *ctx) {
    int r, pass,
        inset =
            g->az
                ? az_inset((const az_t *)g->az)
                : 0; /* the A-Z rail's footprint (patch/azlist.c): hairline end, chevron and text end move left by it */
    if (chev && !g->chev) g->chev = pod_make_chevron();
    for (r = r0; r <= r1; ++r) {
        grid_tile_t *t = tile_of(ctx, r);
        int y = grid_row_y(g, r) - off;
        if (press == t->album) grid_fill(canvas, 0, GRID_LIST_W, y, y + LIST_ROW_H - 1, LIST_PRESS, view_h);
        grid_blit(canvas, g, t, LIST_ART_X + shift, y + LIST_ART_Y, view_h);
        grid_fill(canvas, LIST_TEXT_X + shift, LIST_HAIR_END - inset, y + LIST_ROW_H - 1, y + LIST_ROW_H, LIST_HAIR,
                  view_h);
        if (chev && !t->nochev && g->chev) { /* centred on the row above its hairline, cut to the window by hand */
            int cy = y + (LIST_ROW_H - 1 - POD_CHEV_H) / 2, top = cy < 0 ? -cy : 0,
                bottom = view_h > 0 && cy + POD_CHEV_H > view_h ? view_h - cy : POD_CHEV_H, src[4], dst[4];
            if (bottom > top) {
                src[0] = 0, src[1] = top, src[2] = POD_CHEV_W, src[3] = bottom - top;
                dst[0] = LIST_CHEV_X - inset, dst[1] = cy + top, dst[2] = POD_CHEV_W, dst[3] = bottom - top;
                canvas_draw_image(canvas, g->chev, src, dst);
            }
        }
    }
    for (
        pass = 0; pass < 2;
        ++pass) { /* titles, then subtitles: one text style at a time, cut at the view's edges by the scroll_view's clip */
        widget_prepare_text_style(pass ? st_sub : st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, tile_of(ctx, r), pass, LIST_TEXT_X + shift,
                      grid_row_y(g, r) - off +
                          (pass                   ? LIST_SUB_Y
                           : tile_of(ctx, r)->mid ? (LIST_ROW_H - LIST_TITLE_H) / 2
                                                  : LIST_TITLE_Y),
                      (chev && !tile_of(ctx, r)->nochev ? LIST_TEXT_W_CHEV : LIST_TEXT_W) - shift - inset,
                      pass ? LIST_SUB_H : LIST_TITLE_H, 0);
    }
}

int grid_mosaic_keys(void *songs, void *albums, unsigned *key, int *miss) {
    unsigned tried[16];
    char url[80];
    int n = songs ? (int)deque_size(songs) : 0, k, i, ntried = 0, nk = 0, nofile = 0;
    for (k = 0; k < n && k < PL_SCAN && nk < 4; ++k) {
        void *r = deque_at(songs, (unsigned)k);
        unsigned own = cc_album_key(r), c;
        for (i = 0; i < ntried && tried[i] != own; ++i) {
        }
        if (i < ntried) continue; /* a later song of an album looked at: its cover is in, or there is none */
        if (ntried < 16) tried[ntried++] = own;
        c = cc_cover_key(albums, own, cc_str(r, REC_ALBUM),
                         url); /* its own file, else the library album of that name's */
        if (!*url) {
            if (own) nofile = 1; /* a key without a file: the file may be written later */
            continue;
        }
        for (i = 0; i < nk && key[i] != c; ++i) {
        }
        if (i == nk) key[nk++] = c;
    }
    if (miss) *miss = nofile;
    return nk;
}
