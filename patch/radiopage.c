/* M1+ Music Radio: the stations page (docs/modules/radio.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One window, ui/m1plus_radio.bin (tools/pod_ui.py build_radio_page): the Folders page's structure (patch/folders.c): the glass navbar (Back, the small title, [Search | Now Playing]) over
 * a stock list whose ONE child, view_grid, holds the large title and paints the rows itself in its EVT_AFTER_PAINT. Levels are one window swapping its rows:
 *   root      Now Playing (while a station is up or Recently Played has one), Stations (favourites.m3u), Recently Played, Radio Browser
 *   browser   Top Stations, By Country, By Genre (the directory's levels; the search starts here and below)
 *   pick      the countries (A-Z with section letters, the rail and the pinned header of the Genres page: patch/azlist.c) or the genres (name, "N stations")
 *   list      stations as the Albums list (the default) or grid (patch/grid.c: the logo, the name, "Country · CODEC 128k"), the navbar toggle, RD_VIEW_FILE; a tap plays and opens Radio's Now Playing
 *   note      a caption over no rows: Loading, No Wi-Fi, Directory unavailable (a tap tries again), nothing found
 * The directory fetch is patch/radio.c's one worker; this page polls it on a 250 ms page timer that exists only while it loads. The page owns no playback: the engine and its timer
 * outlive the window (docs/modules/radio.md).
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "keyboard.h"
#include "search.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "pcjson.h"
#include "pcopml.h"
#include "pcnet.h"
#include "radio.h"

extern int rn_open(void); /* patch/radionp.c: Radio's Now Playing page */

#define RP_ASSET "m1plus_radio"
#define RP_W 320
#define RP_ROW_ROOT POD_ROW_H /* the menu rows' pitch (52); the countries' rows too (the Genres page's) */
#define RP_ROW_PICK 64 /* a genre: name over caption */
#define RP_TOP 60 /* the first row, under the large title */
#define RP_TEXT_W \
    224 /* the search field runs the page's width (296, no round X beside it): its text may take this up to the clear button */
#define RP_TOP_SEARCH 48 /* the search page's: the field (window y 56) lies over the list's first 42 px */
#define RP_FIELD_Y 56
#define RP_END 24
#define RP_GROUP_GAP 24
#define RP_CREDIT_GAP 12 /* under the last row */
#define RP_CREDIT_H 56 /* the directory's credit under its rows */
#define RP_ICON 24
#define RP_ICON_X 16
#define RP_TEXT_X 56 /* root rows: after the glyph */
#define RP_LIST_X 16 /* a genre's rows: no glyph */
#define RP_TEXT_END 296
#define RP_CHEV_X 289
#define RP_AZ_TEXT_X 24 /* the countries: the Genres page's numbers (patch/artists.c AR_*) */
#define RP_AZ_TEXT_END 252
#define RP_AZ_CHEV_X 262
#define RP_AZ_TEXT_Y ((RP_ROW_ROOT - LIST_TITLE_H) / 2)
#define RP_GLYPH 96 /* the radio glyph of a logo-less tile (pod_ic_rd_art) */
#define RP_INK 147 /* its ink's brightest channel (#8E8E93 is 0x93) */
#define RP_CARD 0x2e2c2cu /* #2C2C2E as a pixel word (R in the low byte): the card of a station without a logo */
#define RP_AHEAD 2 /* the list mode loads two rows beyond the view in the scroll direction (the Albums list's) */
#define RP_WAIT_LOGO 32 /* 250 ms ticks a directory fetch waits for our own logo job to end (about 8 s) */
#define RP_WAIT_POD 80 /* and for a podcast job (about 20 s) */
#define RP_QUERY "order=votes&reverse=true&limit=100&hidebroken=true"

enum { L_ROOT, L_PICK, L_LIST, L_DIR, L_N };
enum { RR_NOW, RR_MY, RR_RECENT, RR_BROWSER, RR_TOP, RR_COUNTRY, RR_GENRE, RR_N };
enum { RI_STATIONS, RI_TOP, RI_COUNTRY, RI_GENRE, RI_NOW, RI_RECENT, RI_BROWSER, RI_N };
static const char *const RP_ICON_NAME[RI_N] = {"pod_ic_rd_stations", "pod_ic_rd_top",     "pod_ic_rd_country",
                                               "pod_ic_rd_genre",    "pod_ic_nowplaying", "pod_ic_recent",
                                               "pod_ic_rd_browser"};
static const char *const RP_ROW_TEXT[RR_N] = {"Now Playing",  "My Stations", "Recently Played", "Radio Browser",
                                              "Top Stations", "By Country",  "By Genre"};
static const int RP_ROW_ICON[RR_N] = {RI_NOW, RI_STATIONS, RI_RECENT, RI_BROWSER, RI_TOP, RI_COUNTRY, RI_GENRE};

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *lv, *status, *title, *big, *fade, *back, *np, *find, *st_title, *st_sub, *st_gtitle,
        *st_gsub, *credit, *field, *view_btn, *more, *sh_scrim, *sh_card, *sh_row, *sh_hr, *sh_clear, *sh_clear_hr;
    void *chev, *ic[RI_N];
    az_t al; /* the countries' sections, rail and pinned header */
    grid_t g; /* the text ring of the rows and the stations' tiles */
    int level, from, nrows, note, loading, genre, fg, press, down, down_x, down_y, title_on, noscroll, favs, sheet;
    int vlist, seen,
        dir; /* the station lists' mode (1 list, 0 grid), the offset the logo tick last saw, the way it went */
    int want, want_from,
        want_genre; /* the fetch in flight: the level it makes, where Back goes from there, countries or genres */
    char want_caption[72];
    int rows[RR_N];
    int sel[L_N]; /* the scroll offset each level was left at */
    unsigned timer, serial;
    rd_list_t pick, list, keep; /* keep: the level's stations while the search page uses list */
    char caption[72], want_path[360], keep_caption[72];
    int keep_off, keep_from, keep_genre, keep_local, keep_favs; /* the level the search began on, as it was */
    unsigned char rank[RD_MAX + 1]; /* the countries' section ranks */
    int want_kind, retry, search, search_from, credit_on, local, ltimer_on;
    int again; /* the caption is a failure a tap tries again (no Wi-Fi, no date, the directory) */
    unsigned ltimer;
} rp __attribute__((section(".scratch")));

static void rp_show_level(int level, int keep);
static void rp_placeholder(void);
static void rp_note(const char *text);
static int rp_on_tick(const void *unused);
static void rp_search_layout(void);

static void rp_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int rp_abs(int v) { return v < 0 ? -v : v; }
static int rp_off(void) { return rp.sv ? I(rp.sv, SC_YOFF) : 0; }
static void rp_redraw(void) { widget_invalidate_force(rp.sv, (void *)0); }
static int rp_rows_lvl(void) { return rp.level == L_ROOT || rp.level == L_DIR; } /* the levels of menu rows */
static int rp_az(void) { return rp.level == L_PICK && !rp.genre; } /* the countries: the A-Z list */
static int rp_grid(void) { return rp.level == L_LIST && !rp.vlist; } /* the stations as the Albums grid */
static int rp_row_h(void) { return rp_rows_lvl() || rp_az() ? RP_ROW_ROOT : RP_ROW_PICK; }
static int rp_top(void) { return rp.search ? RP_TOP_SEARCH : RP_TOP; }
/* The root's Now Playing row is a group of its own: a gap under it. */
static int rp_gap(void) { return rp.level == L_ROOT && rp.nrows > 1 && rp.rows[0] == RR_NOW ? RP_GROUP_GAP : 0; }
static int rp_row_y(int r) {
    return rp_az() ? az_row_y(&rp.al, r) : rp_top() + r * rp_row_h() + (r > 0 ? rp_gap() : 0);
}
static int rp_credit(void) {
    return rp.level == L_DIR || (rp.level == L_LIST && rp.search && !rp.local);
} /* Radio Browser and the search results only */
/* The content y under the last row (the stations are the grid's rows). */
static int rp_rows_end(void) {
    if (rp_az()) return az_rows_end(&rp.al);
    if (rp_grid()) return rp_top() + (rp.nrows + GRID_COLS - 1) / GRID_COLS * GRID_PITCH - GRID_ROW_GAP;
    return rp_top() + rp.nrows * rp_row_h() + rp_gap();
}
static int rp_content(void) { return rp_rows_end() + (rp_credit() ? RP_CREDIT_H : RP_END); }
static int rp_max_scroll(void) {
    int m = rp_content() - GRID_VIEW_H;
    return m > 0 ? m : 0;
}
/* The row (root, countries, genres) under content y, -1 for the title, a gap or the air below. */
static int rp_at(int y) {
    int g, rel, r;
    if (rp_az()) return az_at(&rp.al, y);
    g = rp_gap(), rel = y - rp_top();
    if (rel < 0) return -1;
    if (g && rel >= rp_row_h()) {
        if (rel < rp_row_h() + g) return -1; /* the gap */
        rel -= g;
    }
    r = rel / rp_row_h();
    return r >= rp.nrows ? -1 : r;
}

static void rp_span(int *r0, int *r1) {
    int off = rp_off(), n = rp.nrows, h = rp_row_h(), r;
    if (rp_az()) {
        az_span(&rp.al, r0, r1);
        return;
    }
    *r0 = n, *r1 = -1;
    for (r = 0; r < n; ++r) { /* the rows that touch the view */
        int y = rp_row_y(r);
        if (y + h <= off) continue;
        if (y >= off + GRID_VIEW_H) break;
        if (r < *r0) *r0 = r;
        *r1 = r;
    }
    if (*r1 < 0) *r0 = 0;
}

/* The first station in view (the grid's row start in the grid), 0 while the large title is. */
static int rp_first(void) {
    int off = rp_off() - rp_top(), a = off <= 0 ? 0 : rp_grid() ? off / GRID_PITCH * GRID_COLS : off / LIST_ROW_H;
    return a > rp.nrows - 1 ? rp.nrows - 1 : a < 0 ? 0 : a;
}

/* The stations' cells that touch the view: [*c0, *c1], whole grid rows (none: *c1 < *c0). */
static void rp_gspan(int *c0, int *c1) {
    int off = rp_off() - rp_top(), r0 = off < 0 ? 0 : off / GRID_PITCH, r1 = (off + GRID_VIEW_H) / GRID_PITCH;
    if (r1 < 0) r1 = 0;
    *c0 = r0 * GRID_COLS;
    *c1 = r1 * GRID_COLS + GRID_COLS - 1;
    if (*c1 > rp.nrows - 1) *c1 = rp.nrows - 1;
}

/* The row or cell under a point of the content view. */
static int rp_item_at(int x, int y) { return rp_grid() ? grid_cell_at(x, y, rp_top(), rp.nrows) : rp_at(y); }

/* ---------------------------------------------------------------------------
 * The rows' texts
 */
static void rp_prep(grid_tile_t *t, int r) {
    char sub[96];
    if (rp_rows_lvl()) {
        grid_set(t, TR(RP_ROW_TEXT[rp.rows[r]]), "", 0);
    } else if (rp.level == L_PICK) {
        const char *c = rd_info(&rp.pick, r);
        unsigned v = 0;
        while (*c >= '0' && *c <= '9') v = v * 10 + (unsigned)(*c++ - '0');
        sub[0] = 0;
        if (rp.genre) pod_fmt(sub, sizeof sub, TR("%d stations"), (int)v);
        grid_set(t, rd_name(&rp.pick, r), sub, 0);
    } else {
        char fav[RD_FAV_MAX + 1];
        rd_caption(rd_info(&rp.list, r), sub, sizeof sub);
        grid_set(t, rd_name(&rp.list, r), sub,
                 rd_favicon(rd_info(&rp.list, r), fav, sizeof fav) ? rd_logo_hash(fav) : 0);
    }
}

/* The tile of row or cell r; the ring keeps the rows in view, the cells in view and a grid row each side. */
static grid_tile_t *rp_tile(int r) {
    int lo, hi, fresh;
    grid_tile_t *t;
    if (rp_grid()) {
        rp_gspan(&lo, &hi);
        lo -= GRID_COLS, hi += GRID_COLS;
    } else {
        rp_span(&lo, &hi);
        if (rp.level == L_LIST)
            lo -= rp.dir < 0 ? RP_AHEAD : 1, hi += rp.dir < 0 ? 1 : RP_AHEAD; /* the rows loaded ahead */
    }
    t = grid_tile(&rp.g, r, lo, hi, &fresh);
    if (fresh) rp_prep(t, r);
    return t;
}

/* ---------------------------------------------------------------------------
 * Paint
 */
static void rp_blit(void *canvas, void *bmp, int w, int h, int x, int y) {
    int top = y < 0 ? -y : 0, bottom = y + h > GRID_VIEW_H ? GRID_VIEW_H - y : h;
    int src[4], dst[4];
    if (!bmp || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = w, src[3] = bottom - top;
    dst[0] = x, dst[1] = y + top, dst[2] = w, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

static grid_tile_t *rp_tile_of(void *ctx, int a) {
    (void)ctx;
    return rp_tile(a);
}

/* The stations in the list mode: the Albums list's rows (grid_list_paint), the first one rp_top() down the content. */
static void rp_paint_list(void *canvas) {
    int r0, r1;
    rp_span(&r0, &r1);
    if (r1 < r0) return;
    grid_list_paint(canvas, &rp.g, rp.st_title, rp.st_sub, r0, r1, rp_off() - rp_top(), GRID_VIEW_H, rp.press, 0, 0,
                    rp_tile_of, (void *)0);
}

/* The stations in the grid mode: the Albums grid's cells (covers, then names, then captions). */
static void rp_paint_grid(void *canvas) {
    int c0, c1;
    rp_gspan(&c0, &c1);
    if (c1 < c0) return;
    grid_paint(canvas, &rp.g, c0, c1 + 1, rp_top() - rp_off(), GRID_VIEW_H, rp_tile_of, (void *)0);
}

static void rp_paint_rows(void *canvas) {
    int r0, r1, r, pass, off = rp_off(), h = rp_row_h(), az = rp_az();
    rp_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = rp_row_y(r) - off;
        if (rp.press == r + 1) az_fill(canvas, 0, y, y + h - 1, RP_W, LIST_PRESS);
        if (rp_rows_lvl()) {
            rp_blit(canvas, rp.ic[RP_ROW_ICON[rp.rows[r]]], RP_ICON, RP_ICON, RP_ICON_X, y + (h - RP_ICON) / 2);
            rp_blit(canvas, rp.chev, POD_CHEV_W, POD_CHEV_H, RP_CHEV_X, y + (h - POD_CHEV_H) / 2);
            if (!(r == 0 && rp_gap())) /* a group of one row ends without a separator */
                az_fill(canvas, RP_TEXT_X, y + h - 1, y + h, RP_W - 10 - RP_TEXT_X, LIST_HAIR);
        } else {
            rp_blit(canvas, rp.chev, POD_CHEV_W, POD_CHEV_H, az ? RP_AZ_CHEV_X : RP_CHEV_X, y + (h - POD_CHEV_H) / 2);
            az_fill(canvas, az ? RP_AZ_TEXT_X : RP_LIST_X, y + h - 1, y + h,
                    (az ? SG_TEXT_END : RP_W - 10) - (az ? RP_AZ_TEXT_X : RP_LIST_X), LIST_HAIR);
        }
    }
    if (rp_rows_lvl() || az) {
        int x0 = az ? RP_AZ_TEXT_X : RP_TEXT_X, end = az ? RP_AZ_TEXT_END : RP_TEXT_END;
        widget_prepare_text_style(rp.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, rp_tile(r), 0, x0, rp_row_y(r) - off + (az ? RP_AZ_TEXT_Y : (h - LIST_TITLE_H) / 2),
                      end - x0, LIST_TITLE_H, GRID_VIEW_H);
        if (az) az_paint_heads(&rp.al, canvas); /* the section letters, then over everything the pinned header */
        return;
    }
    for (pass = 0; pass < 2; ++pass) { /* a genre: the name, then the count; one text style at a time */
        widget_prepare_text_style(pass ? rp.st_sub : rp.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, rp_tile(r), pass, RP_LIST_X, rp_row_y(r) - off + (pass ? LIST_SUB_Y : LIST_TITLE_Y),
                      RP_CHEV_X - 12 - RP_LIST_X, pass ? LIST_SUB_H : LIST_TITLE_H, GRID_VIEW_H);
    }
}

static int rp_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = rp_off();
    (void)ctx;
    if (!canvas || !rp.view || !rp.g.tiles || !rp.nrows || rp.note) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    if (rp.level == L_LIST)
        rp.vlist ? rp_paint_list(canvas) : rp_paint_grid(canvas);
    else
        rp_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Titles and sizes
 */
static const char *rp_title(void) {
    if (rp.level == L_ROOT) return TR("Radio");
    if (rp.level == L_DIR) return TR("Radio Browser");
    if (rp.level == L_PICK) return rp.genre ? TR("Genres") : TR("Countries");
    return rp.caption;
}

/* The countries A-Z by name (the directory's own order puts "The United Kingdom ..." under T): an insertion sort of the three offset tables, stable, near-sorted input is cheap. */
static void rp_pick_sort(void) {
    rd_list_t *l = &rp.pick;
    int i, j;
    for (i = 1; i < l->n; ++i) {
        unsigned n = l->name[i], u = l->url[i], f = l->info[i];
        for (j = i; j > 0 && cc_name_cmp(l->buf + l->name[j - 1], l->buf + n) > 0; --j)
            l->name[j] = l->name[j - 1], l->url[j] = l->url[j - 1], l->info[j] = l->info[j - 1];
        l->name[j] = n, l->url[j] = u, l->info[j] = f;
    }
}

/* The sections of the countries: the rank of the first letter of the name (a leading "The " dropped, as the Genres page ranks), az_sections' labelling. */
static void rp_sections(void) {
    int i;
    rp.al.nsec = 0;
    for (i = 0; i < rp.nrows; ++i)
        rp.rank[i] = (unsigned char)az_rank_of((unsigned char)*cc_name_key(rd_name(&rp.pick, i)));
    az_sections(&rp.al, rp.rank, 1);
}

/* The credit's place: under the last row, left at the rows' text inset. */
static void rp_credit_place(void) {
    int x = rp_rows_lvl()        ? RP_TEXT_X
            : rp_az()            ? RP_AZ_TEXT_X
            : rp.level == L_PICK ? RP_LIST_X
            : rp.vlist           ? LIST_TEXT_X
                                 : GRID_MARGIN;
    widget_move(rp.credit, x, rp_rows_end() + RP_CREDIT_GAP);
    widget_resize(rp.credit, RP_TEXT_END - x, 20);
    rp_show(rp.credit, rp_credit() && rp.nrows);
}

static void rp_title_update(void) {
    pod_title_set(rp.title, &rp.title_on,
                  rp.noscroll || rp.note || rp.search || !rp.nrows || pod_title_gone(rp_off(), 0));
    if (rp.fade) {
        widget_set_visible(rp.fade, rp_off() > 0, 0);
        widget_set_sensitive(rp.fade, 0);
    }
}

static int rp_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.view) rp_title_update();
    return RET_OK;
}

static void rp_size(void) {
    int h = rp.nrows ? rp_content() : GRID_VIEW_H;
    rp.al.content = h;
    widget_resize(rp.view, RP_W, h);
    widget_set_prop_int(rp.sv, "virtual_h", h);
}

/* The view toggle is for the station lists (rows in view, no caption); it shows the other mode's glyph. */
static int rp_toggle_on(void) { return rp.level == L_LIST && rp.nrows && !rp.note; }

/* The capsule, right to left: Now Playing (the right cap), the toggle on the 214 slot (the middle piece), Search on the 168 slot (the left cap), or on the Stations level "..." in
 * Search's place (also with no toggle: an empty Stations). Without the toggle the left cap takes the 214 slot; on the search page Search is gone and the toggle (the left cap piece)
 * takes 214 beside Now Playing, or Now Playing is the glass disc alone. */
static int rp_find_on(void) {
    return !rp.search && (rp.level == L_DIR || rp.level == L_PICK || (rp.level == L_LIST && !rp.local));
}
static int rp_more_on(void) {
    return !rp.search && rp.level == L_LIST && rp.local;
} /* My Stations and Recently Played (also with their caption) */

static void rp_nav(void) {
    int tog = rp_toggle_on(), more = rp_more_on(), find = rp_find_on() || more, cap = tog || find;
    const char *img = cap ? "ah_nav_play" : "ah_nav_np", *g = rp.vlist ? "pod_nav_grid" : "pod_nav_list";
    char n[32], nd[32];
    rp_show(rp.find, find && !more);
    rp_show(rp.more, more);
    widget_move(rp.find, tog ? NAV_CF_X : NAV_VIEW_X, 0);
    widget_move(rp.more, tog ? NAV_CF_X : NAV_VIEW_X, 0);
    rp_show(rp.view_btn, tog);
    snprintf(n, sizeof n, "%s%s", g, find ? "" : "l");
    snprintf(nd, sizeof nd, "%s_down", n);
    widget_set_prop_str(rp.view_btn, "style:normal:icon", n);
    widget_set_prop_str(rp.view_btn, "style:over:icon", n);
    widget_set_prop_str(rp.view_btn, "style:pressed:icon", nd);
    widget_resize(rp.title, (tog && find ? NAV_CF_X : NAV_VIEW_X) - NAV_TITLE_X,
                  22); /* the small title ends at the capsule */
    widget_set_prop_str(rp.np, "style:normal:icon", img);
    widget_set_prop_str(rp.np, "style:over:icon", img);
    widget_set_prop_str(rp.np, "style:pressed:icon", cap ? "ah_nav_play_down" : "ah_nav_np_down");
}

/* The level's rows on the page: the large title, the heights, the offset (keep: the one the level was left at). */
static void rp_show_level(int level, int keep) {
    int i, n = 0;
    if (!rp.view) return;
    if (!rp.note && rp.level != level) rp.sel[rp.level] = rp_off();
    rp.level = level, rp.note = 0, rp.loading = 0, rp.press = rp.down = 0;
    grid_drop(&rp.g);
    rp.al.nsec = 0, rp.al.count = 0;
    if (level == L_ROOT) {
        if (rd_list()->n) {
            rp.rows[n++] = RR_NOW;
        } else {
            rd_list_t last;
            memset(&last, 0, sizeof last);
            if (rd_last_read(&last)) rp.rows[n++] = RR_NOW; /* the station last played: the first of Recently Played */
            rd_list_free(&last);
        }
        for (i = RR_MY; i <= RR_BROWSER; ++i) rp.rows[n++] = i;
        rp.nrows = n;
    } else if (level == L_DIR) {
        for (i = RR_TOP; i < RR_N; ++i) rp.rows[n++] = i;
        rp.nrows = n;
    } else
        rp.nrows = level == L_PICK ? rp.pick.n : rp.list.n;
    if (rp_az()) {
        rp.al.count = rp.nrows;
        rp_sections();
    }
    if (level == L_LIST) {
        grid_shape(&rp.g, rp.vlist ? LIST_ART : GRID_COVER, rp.vlist ? LIST_R : GRID_R, rp.vlist);
        rp_placeholder();
        rp.serial = rd_serial();
    }
    rp_show(rp.view, 1);
    rp_show(rp.status, 0);
    rp_size();
    rp_nav();
    az_fit(rp.big, rp_title());
    az_fit(rp.title, rp.search ? TR("Search Stations") : rp_title());
    widget_set_visible(rp.big, !rp.search, 0);
    if (rp.credit) rp_credit_place();
    az_rail_fit(&rp.al, GRID_VIEW_H);
    widget_set_prop_int(rp.sv, "yoffset",
                        keep ? (rp.sel[level] > rp_max_scroll() ? rp_max_scroll() : rp.sel[level]) : 0);
    rp.title_on = -1;
    rp_title_update();
    rp_redraw();
}

/* A caption over no rows (loading, a failure, nothing found): the level's rows stay where they were for Back. */
static void rp_note(const char *text) {
    rp.again = 0;
    if (!rp.view) return;
    if (!rp.note) rp.sel[rp.level] = rp_off();
    rp.note = 1;
    rp.press = rp.down = 0;
    rp_show(rp.view, 0);
    rp_show(rp.credit, 0);
    rp.al.count = 0, rp.al.nsec = 0;
    az_rail_fit(&rp.al, GRID_VIEW_H);
    widget_set_text_utf8(rp.status, text);
    rp_show(rp.status, 1);
    widget_set_prop_int(rp.sv, "yoffset", 0);
    widget_set_prop_int(rp.sv, "virtual_h", GRID_VIEW_H);
    rp_nav();
    rp.title_on = -1;
    rp_title_update();
}

static void rp_timer_on(void) {
    if (!rp.timer) rp.timer = timer_add(rp_on_tick, (void *)0, 250);
}

static void rp_timer_off(void) {
    if (rp.timer) timer_remove(rp.timer);
    rp.timer = 0;
}

static const char *rp_err_text(int e) {
    return e == RD_E_WIFI    ? TR("No Wi-Fi")
           : e == RD_E_CLOCK ? TR("Set the date first")
           : e == RD_E_EMPTY ? TR("No stations")
                             : TR("Directory unavailable. Tap to try again.");
}

/* A fetch that failed: its caption over the level, and a tap on it asks again (an answer with no station is final). */
static void rp_fail(int e) {
    rp_note(rp_err_text(e));
    rp.again = e != RD_E_EMPTY;
}

/* Fetch path as kind (1 stations, 2 countries, 3 genres) for level `want`, reached from `from`; the page says Loading until the worker is done (the worker tries again itself after a network
 * failure, radio.c). A failure leaves the level it covered, with a caption a tap answers by fetching the same thing again (the request is kept for it). Our own logo job in the way (RD_E_BUSY,
 * asked to end) is waited for about 8 s on the same timer, a podcast job (RD_E_PODBUSY) about 20 s. */
static void rp_fetch(const char *path, int kind, int want, int from, int genre, const char *caption) {
    int e = rd_fetch(path, kind);
    rp.want = want, rp.want_from = from, rp.want_genre = genre;
    if (caption != rp.want_caption) snprintf(rp.want_caption, sizeof rp.want_caption, "%s", caption);
    if (path != rp.want_path) snprintf(rp.want_path, sizeof rp.want_path, "%s", path);
    rp.want_kind = kind;
    if (e && e != RD_E_BUSY && e != RD_E_PODBUSY) {
        rp_fail(e);
        return;
    }
    rp.retry = e == RD_E_PODBUSY ? RP_WAIT_POD : e ? RP_WAIT_LOGO : 0;
    rp_note(TR("Loading…"));
    rp.loading = 1;
    rp_timer_on();
}

static int rp_on_tick(const void *unused) {
    int e = RD_E_OK, ok;
    (void)unused;
    if (!rp.win || !rp.loading) {
        rp.timer = 0;
        return RET_OK;
    }
    if (rp.retry) {
        e = rd_fetch(rp.want_path, rp.want_kind);
        if ((e == RD_E_BUSY || e == RD_E_PODBUSY) && --rp.retry) return RET_REPEAT;
        rp.retry = 0;
        if (e) {
            rp.timer = 0, rp.loading = 0;
            rp_fail(e);
            return RET_OK;
        }
        return RET_REPEAT;
    }
    if (rd_fetch_state() != RD_F_DONE) return RET_REPEAT;
    ok = rd_fetch_take(rp.want == L_PICK ? &rp.pick : &rp.list, &e);
    rp.timer = 0;
    rp.loading = 0;
    if (ok) {
        rp.genre = rp.want_genre;
        if (rp.want == L_PICK && !rp.genre) rp_pick_sort();
        rp.from = rp.want_from;
        rp.local = 0;
        snprintf(rp.caption, sizeof rp.caption, "%s", rp.want_caption);
        rp_show_level(rp.want, 0);
    } else
        rp_fail(e);
    return RET_OK;
}

/* A tap on a failure's caption: the same request again. */
static int rp_on_retry(void *ctx, void *e) {
    (void)ctx;
    if (!e || *(int *)e != EVT_POINTER_UP || !rp.note || !rp.again || rp.loading || !rp.want_path[0]) return RET_OK;
    rp_fetch(rp.want_path, rp.want_kind, rp.want, rp.want_from, rp.want_genre, rp.want_caption);
    return RET_OK;
}

/* One station's logo: a made one is decoded into its tile (1: this tick's work is done), none yet starts the one worker (1: wait for it), a station with none to be had is
 * marked (0: go on to the next). */
static int rp_logo_step(int r) {
    grid_tile_t *t = rp_tile(r);
    char fav[RD_FAV_MAX + 1], path[48], url[64];
    int st;
    if (t->art || !t->ckey) {
        if (!t->ckey) t->art = 2;
        return 0;
    }
    if (!rd_favicon(rd_info(&rp.list, r), fav, sizeof fav)) {
        t->art = 2;
        return 0;
    }
    st = rd_logo_file(t->ckey, path, sizeof path);
    if (st == 1) {
        snprintf(url, sizeof url, "file://%s", path);
        if (pc_cover_ok(path))
            grid_art_url(&rp.g, t, url);
        else
            t->art = 2;
        rp_redraw();
        return 1;
    }
    if (st < 0) {
        t->art = 2;
        return 0;
    }
    if (!rd_logo_running()) rd_logo_start(fav);
    return 1;
}

/* The logos of the stations in view, then the rows ahead in the scroll direction (a grid row; two list rows): the one worker, a picture at a time; a made one is decoded into its
 * tile (one a tick, never while the list moves). The page timer ends with the page. */
static int rp_on_ltick(const void *unused) {
    int v0, v1, a0, a1, r, off = rp_off();
    (void)unused;
    if (!rp.win) {
        rp.ltimer = 0;
        return RET_OK;
    }
    if (off != rp.seen) rp.dir = off > rp.seen ? 1 : -1;
    rp.seen = off;
    if (!pod_screen_lit() || !pod_is_top(rp.win) || rp.note || rp.level != L_LIST || !rp.list.n || !rp.g.tiles ||
        grid_moving(rp.sv))
        return RET_REPEAT;
    if (rp_grid()) {
        rp_gspan(&v0, &v1);
        a0 = rp.dir < 0 ? v0 - GRID_COLS : v1 + 1, a1 = rp.dir < 0 ? v0 - 1 : v1 + GRID_COLS;
    } else {
        rp_span(&v0, &v1);
        a0 = rp.dir < 0 ? v0 - RP_AHEAD : v1 + 1, a1 = rp.dir < 0 ? v0 - 1 : v1 + RP_AHEAD;
    }
    for (r = v0; r <= v1 && r < rp.nrows; ++r)
        if (rp_logo_step(r)) return RET_REPEAT;
    for (r = a0 < 0 ? 0 : a0; r <= a1 && r < rp.nrows; ++r)
        if (rp_logo_step(r)) return RET_REPEAT;
    return RET_REPEAT;
}

/* ---------------------------------------------------------------------------
 * Actions
 */
static void rp_play(int i) {
    if (i < 0 || i >= rp.list.n) return;
    rd_play(&rp.list, i);
    rn_open();
}

/* The Stations level (favourites.m3u) read again and shown; empty it keeps the level, with the hint and the "..." (Import from Card). keep: the scroll offset it was left at. */
static void rp_stations(int keep) {
    rd_favs_read(&rp.list);
    snprintf(rp.caption, sizeof rp.caption, "%s", TR("My Stations"));
    rp_show_level(L_LIST, keep);
    if (!rp.list.n) rp_note(TR("Add stations from Radio Browser or import .m3u files from the card."));
}

/* The Recently Played level (radio-recent) read again and shown; empty it keeps the level, with its caption and the "..." (Clear Recently Played). */
static void rp_recent(void) {
    rd_recent_read(&rp.list);
    snprintf(rp.caption, sizeof rp.caption, "%s", TR("Recently Played"));
    rp_show_level(L_LIST, 0);
    if (!rp.list.n) rp_note(TR("No recently played stations"));
}

static void rp_root_action(int row) {
    switch (row) {
    case RR_NOW:
        if (rd_running())
            rn_open();
        else
            pod_toast(TR("No radio is playing")); /* never starts a station */
        break;
    case RR_BROWSER:
        rp_show_level(L_DIR, 0);
        break;
    case RR_MY:
        rp.from = L_ROOT;
        rp.local = 1, rp.favs = 1;
        rp_stations(0);
        break;
    case RR_RECENT:
        rp.from = L_ROOT;
        rp.local = 1, rp.favs = 0;
        rp_recent();
        break;
    case RR_TOP:
        rp_fetch("/csv/stations/topvote/100?hidebroken=true", 1, L_LIST, L_DIR, 0, TR("Top Stations"));
        break;
    default:
        rp_fetch(row == RR_GENRE ? "/csv/tags?order=stationcount&reverse=true&limit=60"
                                 : "/csv/countries?order=name&hidebroken=true",
                 row == RR_GENRE ? 3 : 2, L_PICK, L_DIR, row == RR_GENRE, "");
    }
}

/* A country or genre: its stations. */
static void rp_pick(int i) {
    char key[160], path[360];
    if (i < 0 || i >= rp.pick.n) return;
    rd_url_escape(rd_url(&rp.pick, i), key, sizeof key);
    snprintf(path, sizeof path,
             rp.genre ? "/csv/stations/bytagexact/%s?" RP_QUERY : "/csv/stations/bycountrycodeexact/%s?" RP_QUERY, key);
    rp_fetch(path, 1, L_LIST, L_PICK, rp.genre, rd_name(&rp.pick, i));
}

/* ---------------------------------------------------------------------------
 * Search: the page's own field and keyboard (the Search page's, patch/search.c), the results below the field
 */
/* The list's height with or without the pad under it. */
static void rp_search_layout(void) {
    int pad = rp.search && keyboard_shown() ? KB_H : 0;
    widget_resize(rp.lv, RP_W, GRID_VIEW_H - pad);
    widget_resize(rp.sv, 310, GRID_VIEW_H - pad);
}

static void rp_search_enter(void) {
    if (rp.search || !rp.field) return;
    rp.keep_off = rp_off(), rp.keep_from = rp.from, rp.keep_genre = rp.genre, rp.keep_local = rp.local,
    rp.keep_favs = rp.favs;
    snprintf(rp.keep_caption, sizeof rp.keep_caption, "%s", rp.caption);
    rd_list_move(&rp.keep, &rp.list); /* the search results replace the list: the level's own stays here for Back */
    rp.search_from = rp.level, rp.search = 1, rp.local = 0;
    keyboard_set_text("");
    rp_show(rp.field, 1);
    keyboard_show(1);
    rp_search_layout();
    rp_show_level(L_LIST, 0);
}

static void rp_search_leave(void) {
    int from = rp.search_from;
    rd_fetch_cancel();
    rp_timer_off();
    rp.search = 0, rp.loading = 0, rp.retry = 0;
    keyboard_show(0);
    rp_show(rp.field, 0);
    rp_search_layout();
    rd_list_move(&rp.list, &rp.keep); /* the level it began on, exactly as it was */
    rp.from = rp.keep_from, rp.genre = rp.keep_genre, rp.local = rp.keep_local, rp.favs = rp.keep_favs;
    snprintf(rp.caption, sizeof rp.caption, "%s", rp.keep_caption);
    rp.note = 0;
    rp.sel[from] = rp.keep_off;
    rp_show_level(from, 1);
}

/* The keyboard's action key: the stations whose name has the text; the pad goes, the results come below the field. */
static void rp_on_go(void) {
    const char *text = keyboard_text();
    char key[200], path[360];
    if (!rp.search || !text[0]) return;
    keyboard_show(0);
    rp_search_layout();
    rd_url_escape(text, key, sizeof key);
    snprintf(path, sizeof path, "/csv/stations/byname/%s?" RP_QUERY, key);
    rp_fetch(path, 1, L_LIST, rp.from, 0, "");
}

static void rp_on_text(const char *text) { (void)text; }

/* A tap on the field brings the pad back. */
static int rp_on_field(void *ctx, void *e) {
    (void)ctx;
    if (e && *(int *)e == EVT_POINTER_UP && rp.search && !keyboard_shown()) {
        keyboard_show(1);
        rp_search_layout();
        rp_redraw();
    }
    return RET_OK;
}

static int rp_on_find(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.view && !rp.note && rp_find_on()) rp_search_enter();
    return RET_OK;
}

/* The view toggle: the other mode in place (the Albums page's: a coasting list stops), the first station in view stays at the top, the choice saved. */
static int rp_on_view(void *ctx, void *e) {
    int first, off;
    void *wa;
    (void)ctx;
    (void)e;
    if (!rp.view || !rp_toggle_on()) return RET_OK;
    wa = P(rp.sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING &&
        P(wa, SC_AN_WIDGET) == rp.sv) { /* a coasting list stops (patch/scroll.c sc_down) */
        widget_animator_destroy(wa);
        stock_scroll_done(rp.sv, (void *)0);
    }
    first = rp_first(), off = rp_off();
    rp.vlist = !rp.vlist, rp.dir = 1, rp.seen = off;
    rp.sel[L_LIST] =
        off - rp_top() <= 0 ? off : rp_top() + (rp.vlist ? first * LIST_ROW_H : first / GRID_COLS * GRID_PITCH);
    rp_show_level(L_LIST, 1);
    rp.seen = rp_off();
    home_write_atomic(RD_VIEW_FILE, RD_VIEW_TMP, rp.vlist ? "0\n" : "1\n");
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows
 */
static int rp_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(rp.view, pt);
    return rp_item_at(pt[0], pt[1]);
}

static void rp_set_press(int p) {
    if (rp.press == p) return;
    rp.press = p;
    rp_redraw();
}

static int rp_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    rp.down = 0;
    if (!e || !rp.view || !rp.nrows || rp.note) return RET_OK;
    a = rp_item_of(e);
    rp.down = a + 1, rp.down_x = I(e, PE_X), rp.down_y = I(e, PE_Y);
    rp_set_press(a + 1);
    return RET_OK;
}

static int rp_on_up(void *ctx, void *e) {
    int a = rp.down - 1, x, near;
    (void)ctx;
    rp.down = 0;
    rp_set_press(0);
    if (a < 0 || !e || !rp.view || rp.note) return RET_OK;
    x = I(e, PE_X);
    near = rp_abs(x - rp.down_x) < SC_DRAG_PX && rp_abs(I(e, PE_Y) - rp.down_y) < SC_DRAG_PX;
    if (!near || rp_item_of(e) != a || a >= rp.nrows) return RET_OK;
    if (rp_rows_lvl())
        rp_root_action(rp.rows[a]);
    else if (rp.level == L_PICK)
        rp_pick(a);
    else
        rp_play(a);
    return RET_OK;
}

static int rp_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp.down = 0;
    rp_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The "..." sheet of the My Stations level (Import from Card) and of Recently Played (Clear Recently Played): the same widget set as Radio Now Playing's sheet, one row shown
 */
static void rp_sheet_close(void) {
    if (!rp.sheet) return;
    rp.sheet = 0;
    rp_show(rp.sh_scrim, 0);
    rp_show(rp.sh_card, 0);
    rp_show(rp.sh_row, 0);
    rp_show(rp.sh_clear, 0);
}

static int rp_on_more(void *ctx, void *e) {
    void *row = rp.favs ? rp.sh_row : rp.sh_clear; /* the level's row */
    (void)ctx;
    (void)e;
    if (!rp.view || !rp_more_on() || rp.sheet) return RET_OK;
    rp.sheet = 1;
    widget_set_visible(rp.sh_hr, 0, 0);
    widget_set_visible(rp.sh_clear_hr, 0, 0);
    widget_move(row, 0, 0);
    widget_move(rp.sh_card, 0, AH_WIN_H - PM_ROW_H);
    widget_resize(rp.sh_card, RP_W, PM_ROW_H);
    widget_set_prop_str(rp.sh_card, "style:normal:bg_image", "pc_sheet1");
    rp_show(row, 1);
    rp_show(rp.sh_scrim, 1);
    rp_show(rp.sh_card, 1);
    return RET_OK;
}

static int rp_on_sheet_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp_sheet_close();
    return RET_OK;
}

/* Import from Card: the card's playlists appended to favourites.m3u, a toast, the list read again where it is. */
static int rp_on_import(void *ctx, void *e) {
    char msg[64];
    int full = 0, r;
    (void)ctx;
    (void)e;
    rp_sheet_close();
    if (!rp.view || !rp_more_on() || !rp.favs) return RET_OK;
    r = rd_fav_import(&full);
    if (r == -1)
        pod_toast(TR("Could not save My Stations"));
    else if (r == -2)
        pod_toast(TR("No playlists in the Radio folder"));
    else if (full)
        pod_toast(TR("My Stations is full"));
    else if (!r)
        pod_toast(TR("No new stations"));
    else {
        pod_fmt(msg, sizeof msg, TR(r == 1 ? "Added %d station" : "Added %d stations"), r);
        pod_toast(msg);
    }
    if (r > 0) {
        if (!rp.note) rp.sel[L_LIST] = rp_off();
        rp_stations(1);
    }
    return RET_OK;
}

/* Clear Recently Played: radio-recent emptied, a toast, the level read again in place (its caption). A station that plays goes on (and keeps the root's Now Playing row); with none playing the row goes. */
static int rp_on_clear(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp_sheet_close();
    if (!rp.view || !rp_more_on() || rp.favs) return RET_OK;
    if (!rd_recent_clear()) {
        pod_toast(TR("Could not clear Recently Played"));
        return RET_OK;
    }
    pod_toast(TR("Cleared Recently Played"));
    rp_recent();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
static int rp_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.sheet) { /* the Stations sheet: Back closes it only */
        rp_sheet_close();
        return RET_OK;
    }
    if (rp.search && !rp.note) { /* the search page: Back leaves it for the level it began on */
        rp_search_leave();
        return RET_OK;
    }
    if (rp.note &&
        !(rp.level == L_LIST &&
          rp.local)) { /* Loading or a caption (not the empty My Stations' hint or the empty Recently Played's caption, which are levels of their own): the transfer stops and the level it covered is back */
        rd_fetch_cancel();
        rp_timer_off();
        rp.loading = 0, rp.retry = 0;
        rp_show_level(rp.level, 1);
        return RET_OK;
    }
    if (rp.level == L_ROOT) {
        navigator_back();
        return RET_OK;
    }
    rp_show_level(rp.level == L_LIST ? rp.from : rp.level == L_PICK ? L_DIR : L_ROOT, 1);
    return RET_OK;
}

static int rp_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp.fg = 1;
    if (!rp.view) return RET_OK;
    if (rp.level == L_ROOT && !rp.note)
        rp_show_level(L_ROOT, 1); /* Now Playing may have appeared */
    else if (rp.level == L_LIST && rp.local && rp.favs && rd_serial() != rp.serial) {
        if (!rp.note)
            rp.sel[L_LIST] =
                rp_off(); /* Stations changed (Now Playing's sheet): read again, a removed station leaves */
        rp_stations(1);
    } else
        rp_redraw();
    return RET_OK;
}

static int rp_on_rail(void *ctx, void *e) {
    (void)ctx;
    if (rp.view) az_rail_event(&rp.al, e);
    return RET_OK;
}

static int rp_on_rail_paint(void *ctx, void *e) {
    (void)ctx;
    if (rp.view) az_rail_paint(&rp.al, e);
    return RET_OK;
}

static int rp_on_bg(void *ctx, void *e) {
    az_rail_end(&rp.al);
    rp.fg = 0;
    return rp_on_abort(ctx, e);
}

static int rp_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    rp_timer_off();
    if (rp.ltimer) timer_remove(rp.ltimer);
    rd_fetch_drop();
    keyboard_detach();
    grid_free(&rp.g);
    az_free(&rp.al);
    if (rp.chev) bitmap_destroy(rp.chev);
    for (i = 0; i < RI_N; ++i)
        if (rp.ic[i]) bitmap_destroy(rp.ic[i]);
    rd_list_free(&rp.pick);
    rd_list_free(&rp.list);
    rd_list_free(&rp.keep);
    memset(&rp, 0, sizeof rp);
    return RET_OK;
}

static void *rp_bitmap(void *win, const char *name) {
    unsigned *px, n;
    void *b = bitmap_create_ex(RP_ICON, RP_ICON, RP_ICON * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != RP_ICON * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, name, 1, RP_ICON, 1, px);
    if (ok) /* cc_decode flattens the white glyph over black: the ink's brightness is its coverage, so the bitmap is white with that alpha (no black square behind a pressed row) */
        for (n = 0; n < RP_ICON * RP_ICON; ++n) {
            unsigned c = px[n], a = c & 255, g = c >> 8 & 255, bl = c >> 16 & 255;
            if (g > a) a = g;
            if (bl > a) a = bl;
            px[n] = a ? a << 24 | 0xffffffu : 0;
        }
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

/* The tile of a station without a logo (the grid's placeholder bitmap): a #2C2C2E card with the grey radio glyph, its corners as the covers' are (grid_round: blended into black, cut in the alpha in the list mode). */
static void rp_placeholder(void) {
    unsigned *px, *gl;
    int s, gs, i, x, y, k, o;
    grid_placeholder(&rp.g);
    if (!rp.g.placeholder) return;
    px = (unsigned *)bitmap_lock_buffer_for_write(rp.g.placeholder);
    if (!px) return;
    s = rp.g.side;
    gs = s * 2 / 3; /* the glyph is two thirds of the tile: RP_GLYPH in the grid's, 34 px in the list's */
    for (i = 0; i < s * s; ++i) px[i] = 0xff000000u | RP_CARD;
    gl = calloc((unsigned)(gs * gs), 4);
    if (gl && cc_decode(rp.win, "pod_ic_rd_art", 1, (unsigned)gs, 1, gl)) {
        o = (s - gs) / 2;
        for (y = 0; y < gs; ++y)
            for (x = 0; x < gs; ++x) {
                unsigned c = gl[y * gs + x], m = c & 255, ch, cov;
                int sh;
                if ((c >> 8 & 255) > m) m = c >> 8 & 255;
                if ((c >> 16 & 255) > m) m = c >> 16 & 255;
                if (!m) continue;
                cov = m * 255 / RP_INK;
                if (cov > 255) cov = 255;
                for (ch = 0, sh = 0; sh < 24; sh += 8)
                    ch |= (((c >> sh & 255) + (RP_CARD >> sh & 255) * (255 - cov) / 255) & 255) << sh;
                px[(y + o) * s + x + o] = 0xff000000u | ch;
            }
    }
    free(gl);
    for (k = 0; k < 4; ++k)
        for (y = 0; y < rp.g.round; ++y)
            for (x = 0; x < rp.g.round; ++x) {
                unsigned *q = px + (k & 2 ? s - 1 - y : y) * s + (k & 1 ? s - 1 - x : x),
                         a = 255u - rp.g.corner[y * rp.g.round + x];
                if (a == 255) continue;
                if (rp.g.blend) { /* the list's: cut in the alpha, the pressed row's fill shows behind */
                    *q = (*q & 0xffffff) | a << 24;
                    continue;
                }
                *q = 0xff000000u | (*q & 255) * a / 255 | (*q >> 8 & 255) * a / 255 << 8 |
                     (*q >> 16 & 255) * a / 255 << 16;
            }
    bitmap_unlock_buffer(rp.g.placeholder);
}

/* The Radio page (the Radio items of Home's menu, Extras and the Pod). 0 once it is up, -1 when it could not open. */
int radio_open(void) {
    int i;
    if (rp.win || home_off()) return -1;
    memset(&rp, 0, sizeof rp);
    rp.win = window_open(RP_ASSET);
    if (!rp.win) return -1;
    widget_on(rp.win, EVT_DESTROY, rp_on_destroy, (void *)0);
    rp.back = pod_bind(rp.win, "btn_return", rp_on_back, (void *)0);
    rp.np = pod_bind(rp.win, "btn_backtoplayer", pod_on_player, (void *)0);
    rp.find = pod_bind(rp.win, "btn_search", rp_on_find, (void *)0);
    rp.view_btn = pod_bind(rp.win, "btn_radioview", rp_on_view, (void *)0);
    rp.more = pod_bind(rp.win, "btn_more", rp_on_more, (void *)0);
    rp.sh_scrim = pod_bind(rp.win, "rd_sh_scrim", rp_on_sheet_scrim, (void *)0);
    rp.sh_card = widget_lookup(rp.win, "rd_sh_card", 1);
    rp.sh_row = pod_bind(rp.win, "rd_sh_import", rp_on_import, (void *)0);
    rp.sh_hr = widget_lookup(rp.win, "rd_sh_import_hr", 1);
    rp.sh_clear = pod_bind(rp.win, "rd_sh_clear", rp_on_clear, (void *)0);
    rp.sh_clear_hr = widget_lookup(rp.win, "rd_sh_clear_hr", 1);
    rp.title = widget_lookup(rp.win, "label_title", 1);
    rp.big = widget_lookup(rp.win, "sg_title", 1);
    rp.fade = widget_lookup(rp.win, "img_nb_fade", 1);
    rp.view = widget_lookup(rp.win, "view_grid", 1);
    rp.sv = widget_lookup(rp.win, "radio_scrollview", 1);
    rp.lv = widget_lookup(rp.win, "radio_listview", 1);
    rp.credit = widget_lookup(rp.win, "rd_credit", 1);
    rp.field = widget_lookup(rp.win, "kb_field", 1);
    rp.status = widget_lookup(rp.win, "label_status", 1);
    rp.st_title = widget_lookup(rp.win, "label_row_title", 1);
    rp.st_sub = widget_lookup(rp.win, "label_row_sub", 1);
    rp.st_gtitle = widget_lookup(rp.win, "label_grid_title", 1);
    rp.st_gsub = widget_lookup(rp.win, "label_grid_sub", 1);
    rp.al.win = rp.win, rp.al.sv = rp.sv, rp.al.top = SG_TITLE_H, rp.al.row = RP_ROW_ROOT;
    rp.al.st_hdr = widget_lookup(rp.win, "label_hdr", 1);
    rp.al.st_rail = widget_lookup(rp.win, "label_rail", 1);
    rp.al.st_rail_on = widget_lookup(rp.win, "label_rail_on", 1);
    rp.al.rail = widget_lookup(rp.win, "sg_rail", 1);
    rp.al.bubble = widget_lookup(rp.win, "sg_bubble", 1);
    rp.al.bubble_letter = widget_lookup(rp.win, "sg_bubble_letter", 1);
    if (!rp.back || !rp.np || !rp.find || !rp.view_btn || !rp.more || !rp.sh_scrim || !rp.sh_card || !rp.sh_row ||
        !rp.sh_hr || !rp.sh_clear || !rp.sh_clear_hr || !rp.lv || !rp.credit || !rp.field || !rp.title || !rp.big ||
        !rp.view || !rp.sv || !rp.status || !rp.st_title || !rp.st_sub || !rp.st_gtitle || !rp.st_gsub ||
        !rp.al.st_hdr || !rp.al.st_rail || !rp.al.st_rail_on || !rp.al.rail || !rp.al.bubble || !rp.al.bubble_letter) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    label_set_line_wrap(rp.status, 1);
    widget_set_prop_bool(rp.status, "word_wrap", 1); /* break at spaces (a character break cut the hint mid-word) */
    widget_on(rp.status, EVT_POINTER_UP, rp_on_retry, (void *)0);
    widget_on(rp.sv, EVT_POINTER_UP, rp_on_retry, (void *)0);
    rp.chev = pod_make_chevron();
    for (i = 0; i < RI_N; ++i) rp.ic[i] = rp_bitmap(rp.win, RP_ICON_NAME[i]);
    rp.noscroll = !widget_on(rp.sv, EVT_SCROLL, rp_on_scroll, (void *)0) ||
                  !widget_on(rp.sv, EVT_SCROLL_END, rp_on_scroll, (void *)0);
    if (rp.noscroll) widget_set_visible(rp.title, 1, 0);
    rp.title_on = rp.noscroll;
    widget_on(rp.win, EVT_WINDOW_TO_FG, rp_on_fg, (void *)0);
    widget_on(rp.win, EVT_WINDOW_TO_BG, rp_on_bg, (void *)0);
    widget_on(rp.view, EVT_POINTER_DOWN, rp_on_down, (void *)0);
    widget_on(rp.view, EVT_POINTER_UP, rp_on_up, (void *)0);
    widget_on(rp.view, EVT_POINTER_ABORT, rp_on_abort, (void *)0);
    widget_on(rp.view, EVT_AFTER_PAINT, rp_on_paint, (void *)0);
    rp.fg = 1;
    rp.vlist = set_read(RD_VIEW_FILE, '0') != '1'; /* the list unless the file says the grid */
    rp.dir = 1;
    widget_on(rp.field, EVT_POINTER_UP, rp_on_field, (void *)0);
    if (keyboard_attach(rp.win, TR("Search Stations"), SE_TEXT_X, RP_TEXT_W, SE_CARET_Y, rp_on_text, rp_on_go) != 0) {
        navigator_back(); /* an asset that is not ours, or a keyboard already up */
        return -2;
    }
    keyboard_show(0);
    rp_show(rp.field, 0);
    if (!grid_init(&rp.g, rp.win, GRID_TILES, GRID_COVER, GRID_R)) {
        grid_free(&rp.g);
        rp_note(TR("Not enough memory"));
        return 0;
    }
    rp.g.st_title = rp.st_gtitle, rp.g.st_sub = rp.st_gsub;
    az_make_disc(&rp.al);
    widget_on(rp.al.rail, EVT_POINTER_DOWN, rp_on_rail, (void *)0);
    widget_on(rp.al.rail, EVT_POINTER_MOVE, rp_on_rail, (void *)0);
    widget_on(rp.al.rail, EVT_POINTER_UP, rp_on_rail, (void *)0);
    widget_on(rp.al.rail, EVT_POINTER_ABORT, rp_on_rail, (void *)0);
    widget_on(rp.al.rail, EVT_AFTER_PAINT, rp_on_rail_paint, (void *)0);
    rp.ltimer = timer_add(rp_on_ltick, (void *)0, 300);
    rp.level = L_ROOT;
    rp_show_level(L_ROOT, 0);
    return 0;
}
