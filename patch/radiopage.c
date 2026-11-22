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
#include "rowmenu.h"
#include "selmode.h"
#include "viewsort.h"

#define RP_ASSET "m1plus_radio"
#define RP_W 320
#define RP_ROW_ROOT POD_ROW_H /* the menu rows' pitch (52); the countries' rows too (the Genres page's) */
#define RP_ROW_PICK 64 /* a genre: name over caption */
#define RP_TOP 60 /* the first row, under the large title */
#define RP_TEXT_W \
    224 /* the search field runs the page's width (296, no round X beside it): its text may take this up to the clear button */
#define RP_TOP_SEARCH 48 /* the search page's: the field (window y 56) lies over the list's first 42 px */
#define RP_END 24
#define RP_GROUP_GAP 24
#define RP_CREDIT_GAP 12 /* under the last row */
#define RP_CREDIT_H 56 /* the directory's credit under its rows */
#define RP_ICON 24
#define RP_ICON_X 16
#define RP_TEXT_X 56 /* root rows: after the glyph */
#define RP_LIST_X 16 /* a genre's rows: no glyph */
#define RP_TEXT_END 296
#define RP_CHEV_X LIST_CHEV_X
#define RP_AZ_TEXT_X 24 /* the countries: the Genres page's numbers (patch/artists.c AR_*) */
#define RP_AZ_TEXT_END (LIST_TEXT_X + LIST_TEXT_W_CHEV) /* the list-row spec, less az_inset while the rail is shown */
#define RP_AZ_CHEV_X LIST_CHEV_X
#define RP_AZ_TEXT_Y ((RP_ROW_ROOT - LIST_TITLE_H) / 2)
#define RP_GLYPH 96 /* the radio glyph of a logo-less tile (pod_ic_rd_art) */
#define RP_INK 147 /* its ink's brightest channel (#8E8E93 is 0x93) */
#define RP_CARD 0x2b2b2bu /* THUMB_RGB #2B2B2B, the placeholder grey: the card of a station without a logo */
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
/* The sheet's row (tools/pod_ui.py RS_SHEET_ROWS): a long press on a My Stations row, Remove. */
enum { SH_REMOVE, SH_N };
static const char *const RP_SH_ID[SH_N] = {"remove"};
#define RP_SCHEME "http://" /* what an empty Add by URL address starts as, and what its clear button leaves */
#define RP_KB_X \
    48 /* the field over the search capsule: after its magnifier (tools/pod_ui.py RD_KB_X, RD_KB_W; the capsule is rd_capsule) */
#define RP_KB_W 260
#define RP_ADD_Y 56 /* Add by URL's card: the Sign In page's, two 48 px rows (tools/pod_ui.py RD_ADD_*) */
#define RP_ADD_ROW 48
#define RP_ADD_X 24 /* the field on a row: its left edge, 6 px down (the 36 px field centred in the row) */
#define RP_ADD_DY 6
#define RP_ADD_FIELD_W 281 /* its clear button centred on x 287, the Sign In page's trailing column */
#define RP_ADD_TW 232 /* the text room of a row (the Sign In page's NL_TW) */

#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *lv, *status, *title, *big, *fade, *back, *np, *find, *st_title, *st_sub, *st_gtitle,
        *st_gsub, *credit, *field, *view_btn, *more, *sh_scrim, *sh_card, *btn_selall, *bar, *del;
    void *capsule, *add_card, *add_hair, *add_v[2], *add_h[2],
        *add_hit[2]; /* the search capsule; Add by URL's card, its rows' values, names and buttons */
    void *sh[SH_N], *sh_hr[SH_N]; /* the sheet's row and its hairline */
    vs_t vs; /* the "..." card (patch/viewsort.c) */
    void *chev, *ic[RI_N];
    m1_sel_t ms; /* My Stations' select mode (patch/selmode.c) */
    int select, entry,
        hold; /* the select mode is on; Add by URL's step (1 the address, 2 the name); the row a long press holds */
    char add_url[KB_MAX_LONG + 1], add_name[KB_MAX + 1]; /* Add by URL: the address, the name typed (empty: the host) */
    az_t al; /* the countries' sections, rail and pinned header */
    grid_t g; /* the text ring of the rows and the stations' tiles */
    int level, from, nrows, note, loading, genre, press, down, title_on, noscroll, favs, sheet;
    m1_tap_t tap;
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
    int want_kind, retry, search, search_from, local;
    int again; /* the caption is a failure a tap tries again (no Wi-Fi, no date, the directory) */
    unsigned ltimer;
} rp __attribute__((section(".scratch")));

static void rp_show_level(int level, int keep);
static void rp_placeholder(void);
static void rp_note(const char *text);
static int rp_on_tick(const void *unused);
static void rp_search_layout(void);

static int rp_off(void) { return grid_sv_off(rp.sv); }
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
static int rp_content(void) {
    return rp_rows_end() + (rp_credit() ? RP_CREDIT_H : RP_END) +
           (rp.select ? SG_BAR_H : 0); /* the last row clears the select bar */
}
static int rp_max_scroll(void) {
    int m = rp_content() - GRID_VIEW_H;
    return m > 0 ? m : 0;
}
/* The row (root, countries, genres) under content y, -1 for the title, a gap or the air below. */
static int rp_at(int y) {
    int g, rel, r;
    if (rp_az()) return az_pin_hit(&rp.al, y) ? -1 : az_at(&rp.al, y);
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
        if (rp.genre) m1_fmt(sub, sizeof sub, TR("%d stations"), (int)v);
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
    grid_blit_from(canvas, bmp, 0, 0, w, h, x, y, GRID_VIEW_H);
}

static grid_tile_t *rp_tile_of(void *ctx, int a) {
    (void)ctx;
    return rp_tile(a);
}

/* The stations in the list mode: the Albums list's rows (grid_list_paint), the first one rp_top() down the content. */
static void rp_paint_list(void *canvas) {
    int r0, r1, r, co = rp_off() - rp_top();
    rp_span(&r0, &r1);
    if (r1 < r0) return;
    for (r = r0; rp.select && r <= r1; ++r) /* the select look under the cover and text (the Playlists list's) */
        m1_sel_paint(&rp.ms, canvas, r, r * LIST_ROW_H - co, LIST_ROW_H, RP_W,
                     LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, GRID_VIEW_H);
    grid_list_paint(canvas, &rp.g, rp.st_title, rp.st_sub, r0, r1, co, GRID_VIEW_H, rp.select ? 0 : rp.press,
                    rp.select ? SG_SEL_COL : 0, 0, rp_tile_of, (void *)0);
}

/* The stations in the grid mode: the Albums grid's cells (covers, then names, then captions); in select mode a mark at each cover's bottom right (the Playlists grid's). */
static void rp_paint_grid(void *canvas) {
    int c0, c1, a, y0 = rp_top() - rp_off();
    rp_gspan(&c0, &c1);
    if (c1 < c0) return;
    grid_paint(canvas, &rp.g, c0, c1 + 1, y0, GRID_VIEW_H, rp_tile_of, (void *)0);
    for (a = c0; rp.select && a <= c1; ++a)
        grid_mark_draw(canvas, rp.ms.mark[m1_sel_is(&rp.ms, a)], grid_cell_x(a) + GRID_COVER - SG_MARK - 6,
                       grid_cell_y(a, y0) + GRID_COVER - SG_MARK - 6, GRID_VIEW_H);
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
            rp_blit(canvas, rp.chev, POD_CHEV_W, POD_CHEV_H, az ? RP_AZ_CHEV_X - az_inset(&rp.al) : RP_CHEV_X,
                    y + (h - POD_CHEV_H) / 2);
            az_fill(canvas, az ? RP_AZ_TEXT_X : RP_LIST_X, y + h - 1, y + h,
                    (az ? az_end(&rp.al) : RP_W - 10) - (az ? RP_AZ_TEXT_X : RP_LIST_X), LIST_HAIR);
        }
    }
    if (rp_rows_lvl() || az) {
        int x0 = az ? RP_AZ_TEXT_X : RP_TEXT_X, end = az ? RP_AZ_TEXT_END - az_inset(&rp.al) : RP_TEXT_END;
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
    m1_show(rp.credit, rp_credit() && rp.nrows);
}

static void rp_title_update(void) {
    m1_title_set(rp.title, &rp.title_on,
                 rp.noscroll || rp.note || rp.search || rp.entry || rp.select || !rp.nrows ||
                     m1_title_gone(rp_off(), 0));
    if (rp.fade) {
        grid_fade(rp.fade, rp_off() > 0);
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
static int rp_toggle_on(void) {
    return !rp.entry && rp.level == L_LIST && rp.nrows && !rp.note &&
           (rp.search || !rp.local); /* (My Stations and Recently Played keep the view in the "..." card) */
}

/* The capsule, right to left: Now Playing (the right cap), the toggle on the 214 slot (the middle piece), Search on the 168 slot (the left cap). My Stations and Recently Played have "..." alone
 * on the 214 slot (the left cap, the Artists page's capsule; the view is in its card). Without the toggle the left cap takes the 214 slot; on the search page Search is gone and the toggle
 * (the left cap piece) takes 214 beside Now Playing, or Now Playing is the glass disc alone. */
static int rp_find_on(void) {
    return !rp.search && !rp.entry && (rp.level == L_DIR || rp.level == L_PICK || (rp.level == L_LIST && !rp.local));
}
static int rp_more_on(void) {
    return !rp.search && !rp.entry && rp.level == L_LIST && rp.local;
} /* My Stations and Recently Played (also with their caption) */

static void rp_nav(void) {
    int tog = rp_toggle_on(), more = rp_more_on(), find = rp_find_on() || more, cap = tog || find;
    const char *img = cap ? "ah_nav_play" : "ah_nav_np", *g = rp.vlist ? "pod_nav_grid" : "pod_nav_list";
    char n[32], nd[32];
    m1_show(rp.find, find && !more);
    m1_show(rp.more, more);
    widget_move(rp.find, tog ? NAV_CF_X : NAV_VIEW_X, 0);
    widget_move(rp.more, NAV_VIEW_X, 0);
    m1_show(rp.view_btn, tog);
    snprintf(n, sizeof n, "%s%s", g, find ? "" : "l");
    snprintf(nd, sizeof nd, "%s_down", n);
    grid_icons(rp.view_btn, n, nd);
    grid_title_end(rp.title, tog && find ? NAV_CF_X : NAV_VIEW_X); /* the small title ends at the capsule */
    grid_icons(rp.np, img, cap ? "ah_nav_play_down" : "ah_nav_np_down");
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
    m1_show(rp.view, 1);
    m1_show(rp.status, 0);
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
    grid_sv_redraw(rp.sv);
}

/* A caption over no rows (loading, a failure, nothing found): the level's rows stay where they were for Back. */
static void rp_note(const char *text) {
    rp.again = 0;
    if (!rp.view) return;
    if (!rp.note) rp.sel[rp.level] = rp_off();
    rp.note = 1;
    rp.press = rp.down = 0;
    m1_show(rp.view, 0);
    m1_show(rp.credit, 0);
    rp.al.count = 0, rp.al.nsec = 0;
    az_rail_fit(&rp.al, GRID_VIEW_H);
    widget_set_text_utf8(rp.status, text);
    m1_show(rp.status, 1);
    widget_set_prop_int(rp.sv, "yoffset", 0);
    widget_set_prop_int(rp.sv, "virtual_h", GRID_VIEW_H);
    rp_nav();
    rp.title_on = -1;
    rp_title_update();
}

static void rp_timer_on(void) {
    if (!rp.timer) rp.timer = timer_add(rp_on_tick, (void *)0, 250);
}

static void rp_timer_off(void) { m1_timer_stop(&rp.timer); }

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
        grid_sv_redraw(rp.sv);
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
    if (!m1_screen_lit() || !m1_is_top(rp.win) || rp.note || rp.level != L_LIST || !rp.list.n || !rp.g.tiles ||
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
static void rp_select(int on);
static void rp_stations(int keep) {
    rp_select(0); /* the marks were of the list read before */
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
    int pad = (rp.search || rp.entry) && keyboard_shown() ? KB_H : 0;
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
    m1_show(rp.capsule, 1);
    m1_show(rp.field, 1);
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
    m1_show(rp.capsule, 0);
    m1_show(rp.field, 0);
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
    if (e && *(int *)e == EVT_POINTER_UP && (rp.search || rp.entry) && !keyboard_shown()) {
        keyboard_show(1);
        rp_search_layout();
        grid_sv_redraw(rp.sv);
    }
    return RET_OK;
}

static int rp_on_find(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.view && !rp.note && rp_find_on()) rp_search_enter();
    return RET_OK;
}

/* The station lists' mode, list or grid, in place (the Albums page's: a coasting list stops), the first station in view stays at the top, the choice saved. */
static void rp_set_view(int list) {
    int first, off;
    void *wa;
    if (!rp.view || (rp.vlist != 0) == list) return;
    wa = P(rp.sv, SC_WA);
    if (wa && I(wa, SC_AN_STATE) == SC_AN_RUNNING &&
        P(wa, SC_AN_WIDGET) == rp.sv) { /* a coasting list stops (patch/scroll.c sc_down) */
        widget_animator_destroy(wa);
        stock_scroll_done(rp.sv, (void *)0);
    }
    first = rp_first(), off = rp_off();
    rp.vlist = list, rp.dir = 1, rp.seen = off;
    rp.sel[L_LIST] =
        off - rp_top() <= 0 ? off : rp_top() + (rp.vlist ? first * LIST_ROW_H : first / GRID_COLS * GRID_PITCH);
    rp_show_level(L_LIST, 1);
    rp.seen = rp_off();
    home_write_atomic(RD_VIEW_FILE, rp.vlist ? "0\n" : "1\n");
}

/* The navbar toggle: the other mode. */
static int rp_on_view(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.view && rp_toggle_on()) rp_set_view(!rp.vlist);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows
 */
static int rp_item_of(void *e) {
    int pt[2];
    grid_ev_local(rp.view, e, pt);
    return rp_item_at(pt[0], pt[1]);
}

/* The My Stations level as a list of the card's file (not the search results over it, not Recently Played). */
static int rp_my(void) { return rp.level == L_LIST && rp.local && rp.favs && !rp.search && !rp.note; }

static void rp_sheet_open(const int *ids, int n);

/* A long press on a My Stations row: its one-row sheet, Remove from My Stations. */
static void rp_on_hold(int a) {
    static const int ids[] = {SH_REMOVE};
    grid_press_end(&rp.down, &rp.press, rp.sv);
    if (!rp.win || !rp_my() || rp.select || rp.entry || rp.sheet || a < 0 || a >= rp.list.n) return;
    rp.hold = a;
    rp_sheet_open(ids, 1);
}

static int rp_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    rp.down = 0;
    if (!e || !rp.view || !rp.nrows || rp.note) return RET_OK;
    a = rp_item_of(e);
    rp.down = a + 1, m1_tap_at(&rp.tap, e);
    if (!rp.select) grid_set_press(&rp.press, a + 1, rp.sv);
    if (a >= 0 && rp_my() && !rp.select) rowmenu_hold_start(a, rp_on_hold);
    return RET_OK;
}

static int rp_on_move(void *ctx, void *e) {
    (void)ctx;
    if (rp.down && e) rowmenu_hold_move(&rp.tap, e); /* a drift is a drag, not a long press */
    return RET_OK;
}

static int rp_on_up(void *ctx, void *e) {
    int a = rp.down - 1;
    (void)ctx;
    rowmenu_hold_stop();
    grid_press_end(&rp.down, &rp.press, rp.sv);
    if (a < 0 || !e || !rp.view || rp.note) return RET_OK;
    if (!m1_tap_near(&rp.tap, e) || rp_item_of(e) != a || a >= rp.nrows) return RET_OK;
    if (rp.select) {
        if (m1_sel_toggle(&rp.ms, a)) {
            m1_sel_head(&rp.ms);
            grid_sv_redraw(rp.sv);
        }
    } else if (rp_rows_lvl())
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
    rowmenu_hold_stop();
    grid_press_end(&rp.down, &rp.press, rp.sv);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * My Stations' select mode (the sheet's Select), in the Playlists page's manner: Back becomes the x, the title "N Selected", Select All at the right, a mark on every row or
 * cell, the bar with one Delete pill. Delete asks, then takes the marked stations out of favourites.m3u.
 */
static int rp_select_ok(void) { return rp.btn_selall && rp.bar && rp.del && rp.ms.mark[0] && rp.ms.mark[1]; }

static void rp_select(int on) {
    if (on == rp.select) return;
    if (on && (!rp_select_ok() || !rp_my() || !rp.list.n || !m1_sel_reset(&rp.ms, (unsigned)rp.list.n))) return;
    rowmenu_hold_stop();
    rp.select = on;
    rp.press = rp.down = 0;
    m1_sel_enter(&rp.ms, on, NAV_VIEW_X);
    if (on) {
        m1_show(rp.np, 0);
        m1_show(rp.more, 0);
        m1_show(rp.view_btn, 0);
        rp_size();
        rp.title_on = -1;
        rp_title_update();
        grid_sv_redraw(rp.sv);
        return;
    }
    m1_show(rp.np, 1);
    rp.sel[L_LIST] = rp_off();
    rp_show_level(L_LIST, 1); /* the level's own navbar, title and height */
}

static int rp_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!rp.select) return RET_OK;
    m1_sel_toggle_all(&rp.ms);
    m1_sel_head(&rp.ms);
    grid_sv_redraw(rp.sv);
    return RET_OK;
}

/* A failed write keeps the list (and the select mode) as it was. */
static void rp_removed(int r, int one) {
    if (r < 0) {
        pod_toast(TR("Could not save My Stations"));
        return;
    }
    if (one && r > 0) pod_toast(TR("Removed from My Stations"));
    if (!rp.note) rp.sel[L_LIST] = rp_off();
    rp_stations(1);
}

static int rp_on_delete(void *ctx, void *e) {
    char q[160];
    (void)ctx;
    (void)e;
    if (!rp.select || !rp.ms.nsel) return RET_OK;
    m1_fmt(q, sizeof q,
           TR(rp.ms.nsel == 1 ? "Remove %d station from My Stations?" : "Remove %d stations from My Stations?"),
           (int)rp.ms.nsel);
    if (!pod_confirm(q)) return RET_OK;
    rp_removed(rd_fav_remove(&rp.list, rp.ms.bits), 0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Add by URL: the Sign In page's card (patch/ndserver.c): two rows, Stream URL and Station Name, the field and pad on the row being typed, the other row showing its value or, empty, its
 * grey name. The address first (Next), then the name (Done, the address's host to start with); a tap on the other row goes there (the name row only with an address that can be one). The
 * station is appended to My Stations. Back leaves it with nothing written.
 */
static void rp_on_add_text(const char *text);
static void rp_on_add_go(void);

/* The address's host (no user info, an IPv6 one without its brackets) into out (cut to n - 1 bytes); its length, 0 when there is none. */
static unsigned rp_url_host(const char *url, char *out, unsigned n) {
    const char *a = strstr(url, "://"), *e, *h, *t;
    unsigned k;
    a = a ? a + 3 : url;
    for (e = a; *e && !strchr("/?#", *e); ++e) {
    }
    for (h = a, t = a; t < e; ++t)
        if (*t == '@') h = t + 1; /* the host follows the last '@' of the authority */
    if (*h == '[') { /* [v6]: up to the bracket, then the end or a port */
        for (t = ++h; t < e && *t != ']'; ++t) {
        }
        if (t == e || (t + 1 < e && t[1] != ':')) t = h;
    } else
        for (t = h; t < e && *t != ':'; ++t) {
        }
    for (k = 0; n && k + 1 < n && h + k < t; ++k) out[k] = h[k];
    if (n) out[k] = 0;
    return (unsigned)(t - h);
}

/* An address the player can open (rd_playable) with a host, and no space. */
static int rp_url_ok(const char *s) {
    return (!strncasecmp(s, "http://", 7) || !strncasecmp(s, "https://", 8)) && rd_playable(s) && !strchr(s, ' ') &&
           rp_url_host(s, (char *)0, 0) > 0;
}

/* The field on the search capsule (row < 0, after its magnifier) or on row `row` of Add by URL's card: the text origin stays x 0 in the field, its clear button at its right end. */
static void rp_field_at(int row) {
    void *clear = widget_lookup(rp.field, "kb_clear", 1);
    int w = row < 0 ? RP_KB_W : RP_ADD_FIELD_W;
    widget_move(rp.field, row < 0 ? RP_KB_X : RP_ADD_X, RP_ADD_Y + (row < 0 ? 0 : row * RP_ADD_ROW + RP_ADD_DY));
    widget_resize(rp.field, w, SE_FIELD_H);
    if (clear) widget_move(clear, w - SE_CLEAR_W, 0);
}

/* Add by URL's card shown or hidden; shown, the row not typed in shows its value or its grey name. */
static void rp_add_card(int on) {
    int i;
    m1_show(rp.add_card, on);
    m1_show(rp.add_hair, on);
    for (i = 0; i < 2; ++i) {
        const char *t = i ? rp.add_name : rp.add_url;
        int other = on && i != rp.entry - 1;
        m1_show(rp.add_hit[i], on);
        m1_show(rp.add_v[i], other && t[0]);
        m1_show(rp.add_h[i], other && !t[0]);
        if (other && t[0]) az_fit(rp.add_v[i], t);
    }
}

static void rp_entry(int step) {
    char host[KB_MAX + 1];
    const char *name = rp.add_name;
    rp.entry = step;
    m1_show(rp.view, 0);
    m1_show(rp.status, 0);
    m1_show(rp.credit, 0);
    m1_show(rp.capsule, 0);
    widget_set_prop_int(rp.sv, "yoffset", 0);
    widget_set_prop_int(rp.sv, "virtual_h", GRID_VIEW_H);
    az_fit(rp.title, TR("Add by URL"));
    widget_set_visible(rp.big, 0, 0);
    rp.title_on = -1;
    rp_title_update();
    rp_nav(); /* Search, "..." and the toggle go: Now Playing is the glass disc alone */
    if (step == 1) { /* the Sign In page's address field: English only, no capitals, the scheme to type after */
        keyboard_refocus(TR("Stream URL"), RP_ADD_TW, KB_PASSWORD, RP_SCHEME, rp_on_add_text, rp_on_add_go);
        keyboard_set_mask(0);
        keyboard_set_clear(RP_SCHEME);
        keyboard_set_max(KB_MAX_LONG);
        if (rp.add_url[0])
            keyboard_set_text(rp.add_url); /* (after the limit: refocus cuts what it loads to KB_PASS_MAX) */
    } else {
        if (!name[0]) rp_url_host(rp.add_url, host, sizeof host), name = host;
        keyboard_refocus(TR("Station Name"), RP_ADD_TW, 0, name, rp_on_add_text, rp_on_add_go);
    }
    rp_field_at(step - 1);
    rp_add_card(1);
    m1_show(rp.field, 1);
    keyboard_show(1);
    rp_search_layout();
    rp_on_add_text(keyboard_text());
}

/* The field back to the search's, the card and the pad hidden, the My Stations level read again (keep: where it was). */
static void rp_entry_leave(void) {
    if (!rp.entry) return;
    rp.entry = 0;
    rp_add_card(0);
    rp_field_at(-1);
    keyboard_refocus(TR("Search Stations"), RP_TEXT_W, 0, "", rp_on_text, rp_on_go);
    keyboard_set_go("Search", 1);
    keyboard_show(0);
    m1_show(rp.field, 0);
    rp_search_layout();
    rp_stations(1);
}

static void rp_on_add_text(const char *text) {
    if (!rp.entry) return;
    keyboard_set_go(rp.entry == 1 ? "Next" : "Done", rp.entry == 1 ? rp_url_ok(text) : text[0] != 0);
}

static void rp_on_add_go(void) {
    const char *text = keyboard_text();
    int r;
    if (rp.entry == 1) {
        if (!rp_url_ok(text)) return;
        if (strcmp(rp.add_url, text)) { /* another address: a name not typed follows its host */
            char host[KB_MAX + 1];
            rp_url_host(rp.add_url, host, sizeof host);
            if (!strcmp(rp.add_name, host)) rp.add_name[0] = 0;
        }
        snprintf(rp.add_url, sizeof rp.add_url, "%s", text);
        rp_entry(2);
        return;
    }
    if (rp.entry != 2 || !text[0]) return;
    r = rd_fav_add(text, rp.add_url);
    pod_toast(TR(r == 1    ? "Added to My Stations"
                 : r == 0  ? "Already in My Stations"
                 : r == -2 ? "My Stations is full"
                           : "Could not save My Stations"));
    if (r == 1) rp.sel[L_LIST] = 1 << 20; /* the new station is the last row: in view (rp_show_level clamps) */
    rp_entry_leave();
}

/* ---------------------------------------------------------------------------
 * The long press sheet (Remove from My Stations): the same widget set as Radio Now Playing's sheet, one row
 */
static void rp_sheet_close(void) {
    int i;
    if (!rp.sheet) return;
    rp.sheet = 0;
    m1_show(rp.sh_scrim, 0);
    m1_show(rp.sh_card, 0);
    for (i = 0; i < SH_N; ++i) m1_show(rp.sh[i], 0);
}

/* The rows ids[0 .. n - 1] in that order (the others stay hidden). */
static void rp_sheet_open(const int *ids, int n) {
    void *rows[SH_N], *hrs[SH_N];
    int i;
    for (i = 0; i < n; ++i) rows[i] = rp.sh[ids[i]], hrs[i] = rp.sh_hr[ids[i]];
    rp.sheet = 1;
    m1_sheet_rows(rp.sh_scrim, rp.sh_card, RP_W, rows, hrs, n);
}

/* ---------------------------------------------------------------------------
 * The "..." card (patch/viewsort.c): My Stations: Select (with a station and the mode's widgets), Sort by Name (two stations or more), Add by URL, Import from Card, then Grid and List (with
 * stations in view); Recently Played: Grid and List (with stations in view), then Clear Recently Played, red, last (slot 9 retexted: the card's tail). Slots: 6 Select, 7 Sort, 8 Add, 9 Import / Clear.
 */
static int rp_view_rows(void) { return rp.nrows && !rp.note; }

static void rp_card(int on) {
    if (!rp.vs.card) return;
    if (on) {
        unsigned mask = rp_view_rows() ? VS_WITH_VIEWS : 0;
        static const char *const COL[3] = {"style:normal:text_color", "style:disable:text_color",
                                           "style:focused:text_color"};
        int i;
        if (rp.favs) {
            if (rp_my() && rp.list.n && rp_select_ok()) mask |= VS_WITH_SEARCH;
            if (rp_my() && rp.list.n > 1) mask |= VS_WITH_SELECT;
            mask |= VS_WITH_ACT2 | VS_WITH_ACT3;
        } else
            mask |= VS_WITH_ACT3 | VS_TAIL;
        widget_set_tr_text(rp.vs.label[VS_ACT3], rp.favs ? "Import from Card" : "Clear History");
        widget_set_prop_str(rp.vs.glyph[VS_ACT3 - VS_SORTS], "image", rp.favs ? "pod_ic_vsimport" : "pod_ic_vstrash");
        for (i = 0; i < 3; ++i)
            widget_set_prop_str(rp.vs.label[VS_ACT3], COL[i],
                                rp.favs ? "#FFFFFF" : "#FF6B6B"); /* (the red of every destructive row) */
        vs_offer(&rp.vs, mask);
    }
    vs_menu(&rp.vs, on, 0, 0, rp.vlist);
}

static int rp_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!rp.view || !rp_more_on() || rp.sheet) return RET_OK;
    rp_card(!rp.vs.on);
    return RET_OK;
}

static int rp_on_card_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp_card(0);
    return RET_OK;
}

static void rp_do_select(void) { rp_select(1); }

/* Sort by Name: favourites.m3u rewritten in name order, the list read again from its top. */
static void rp_do_sort(void) {
    int r;
    if (!rp_my()) return;
    r = rd_fav_sort();
    if (r < 0) {
        pod_toast(TR("Could not save My Stations"));
        return;
    }
    rp_stations(0);
}

static void rp_do_addurl(void) {
    if (!rp.view || !rp_more_on() || !rp.favs || !rp.field) return;
    if (!rp.note) rp.sel[L_LIST] = rp_off();
    rp.note = 0;
    rp.add_url[0] = rp.add_name[0] = 0;
    rp_entry(1);
}

/* A tap on a row of Add by URL's card: the row typed in brings the pad back; the name row goes on as Next does; the address row goes back to it, the name kept. */
static int rp_on_add_hit(void *ctx, void *e) {
    int row = (int)(long)ctx;
    (void)e;
    if (!rp.entry) return RET_OK;
    if (row == rp.entry - 1) {
        if (!keyboard_shown()) keyboard_show(1), rp_search_layout();
    } else if (row)
        rp_on_add_go();
    else {
        snprintf(rp.add_name, sizeof rp.add_name, "%s", keyboard_text());
        rp_entry(1);
    }
    return RET_OK;
}

/* The long press's Remove from My Stations: that one station out of the file. */
static int rp_on_remove(void *ctx, void *e) {
    unsigned char bits[(RD_MAX + 8) / 8];
    (void)ctx;
    (void)e;
    rp_sheet_close();
    if (!rp_my() || rp.hold < 0 || rp.hold >= rp.list.n) return RET_OK;
    memset(bits, 0, sizeof bits);
    bits[rp.hold >> 3] = (unsigned char)(1 << (rp.hold & 7));
    rp_removed(rd_fav_remove(&rp.list, bits), 1);
    return RET_OK;
}

static int rp_on_sheet_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rp_sheet_close();
    return RET_OK;
}

/* Import from Card: the card's playlists appended to favourites.m3u, a toast, the list read again where it is. */
static void rp_do_import(void) {
    char msg[64];
    int full = 0, r;
    if (!rp.view || !rp_more_on() || !rp.favs) return;
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
        m1_fmt(msg, sizeof msg, TR(r == 1 ? "Added %d station" : "Added %d stations"), r);
        pod_toast(msg);
    }
    if (r > 0) {
        if (!rp.note) rp.sel[L_LIST] = rp_off();
        rp_stations(1);
    }
}

/* Clear Recently Played: radio-recent emptied, a toast, the level read again in place (its caption). A station that plays goes on (and keeps the root's Now Playing row); with none playing the row goes. */
static void rp_do_clear(void) {
    if (!rp.view || !rp_more_on() || rp.favs) return;
    if (!rd_recent_clear()) {
        pod_toast(TR("Could not clear Recently Played"));
        return;
    }
    pod_toast(TR("Cleared Recently Played"));
    rp_recent();
}

/* A tap on a card row (the slot in ctx): the card closes first. */
static int rp_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx;
    (void)e;
    rp_card(0);
    if (k == VS_SORTS || k == VS_SORTS + 1) {
        if (rp_view_rows() && rp_more_on()) rp_set_view(k == VS_SORTS + 1);
    } else if (k == VS_SEARCH)
        rp_do_select();
    else if (k == VS_SELECT)
        rp_do_sort();
    else if (k == VS_ACT2)
        rp_do_addurl();
    else if (k == VS_ACT3) {
        if (rp.favs)
            rp_do_import();
        else
            rp_do_clear();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
static int rp_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rp.sheet || rp.vs.on) { /* the long press sheet or the "..." card: Back closes it only */
        rp_sheet_close();
        rp_card(0);
        return RET_OK;
    }
    if (rp.select) { /* the x: the select mode ends, nothing removed */
        rp_select(0);
        return RET_OK;
    }
    if (rp.entry) { /* Add by URL: left, nothing written */
        rp_entry_leave();
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
    if (!rp.view) return RET_OK;
    if (rp.entry) return RET_OK; /* (Add by URL keeps its field) */
    if (rp.level == L_ROOT && !rp.note)
        rp_show_level(L_ROOT, 1); /* Now Playing may have appeared */
    else if (rp.level == L_LIST && rp.local && rp.favs && rd_serial() != rp.serial) {
        if (!rp.note)
            rp.sel[L_LIST] =
                rp_off(); /* Stations changed (Now Playing's sheet): read again, a removed station leaves */
        rp_stations(1);
    } else
        grid_sv_redraw(rp.sv);
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
    rowmenu_hold_stop();
    return rp_on_abort(ctx, e);
}

static int rp_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    rp_timer_off();
    m1_timer_stop(&rp.ltimer);
    rowmenu_hold_stop();
    m1_sel_free(&rp.ms);
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
    int i, az_ok, sh_ok = 1;
    if (rp.win) return -1;
    memset(&rp, 0, sizeof rp);
    rp.win = window_open(RP_ASSET);
    if (!rp.win) return -1;
    widget_on(rp.win, EVT_DESTROY, rp_on_destroy, (void *)0);
    rp.back = m1_bind(rp.win, "btn_return", rp_on_back, (void *)0);
    rp.np = m1_bind(rp.win, "btn_backtoplayer", m1_on_player, (void *)0);
    rp.find = m1_bind(rp.win, "btn_search", rp_on_find, (void *)0);
    rp.view_btn = m1_bind(rp.win, "btn_radioview", rp_on_view, (void *)0);
    rp.more = m1_bind(rp.win, "btn_more", rp_on_more, (void *)0);
    rp.sh_scrim = m1_bind(rp.win, "rd_sh_scrim", rp_on_sheet_scrim, (void *)0);
    rp.sh_card = widget_lookup(rp.win, "rd_sh_card", 1);
    for (i = 0; i < SH_N; ++i) {
        static int (*const RP_SH_FN[SH_N])(void *, void *) = {rp_on_remove};
        char name[24];
        snprintf(name, sizeof name, "rd_sh_%s", RP_SH_ID[i]);
        rp.sh[i] = m1_bind(rp.win, name, RP_SH_FN[i], (void *)0);
        snprintf(name, sizeof name, "rd_sh_%s_hr", RP_SH_ID[i]);
        rp.sh_hr[i] = widget_lookup(rp.win, name, 1);
        sh_ok = sh_ok && rp.sh[i] && rp.sh_hr[i];
    }
    if (vs_bind(&rp.vs, rp.win, rp_on_item, rp_on_card_scrim,
                VS_WITH_VIEWS | VS_WITH_SEARCH | VS_WITH_SELECT | VS_WITH_ACT2 | VS_WITH_ACT3))
        sh_ok = 0;
    vs_dated(&rp.vs, 0);
    rp.btn_selall = m1_bind(rp.win, "btn_selall", rp_on_selall, (void *)0); /* the select mode's widgets */
    rp.bar = widget_lookup(rp.win, "rd_bar", 1);
    rp.del = m1_bind(rp.win, "rd_del", rp_on_delete, (void *)0);
    rp.title = widget_lookup(rp.win, "label_title", 1);
    rp.big = widget_lookup(rp.win, "sg_title", 1);
    rp.fade = widget_lookup(rp.win, "img_nb_fade", 1);
    rp.view = widget_lookup(rp.win, "view_grid", 1);
    rp.sv = widget_lookup(rp.win, "radio_scrollview", 1);
    rp.lv = widget_lookup(rp.win, "radio_listview", 1);
    rp.credit = widget_lookup(rp.win, "rd_credit", 1);
    rp.field = widget_lookup(rp.win, "kb_field", 1);
    rp.capsule = widget_lookup(rp.win, "rd_capsule", 1);
    rp.add_card = widget_lookup(rp.win, "rd_add_card", 1);
    rp.add_hair = widget_lookup(rp.win, "rd_add_hair", 1);
    for (i = 0; i < 2; ++i) {
        char n[16];
        snprintf(n, sizeof n, "rd_add_v%d", i);
        rp.add_v[i] = widget_lookup(rp.win, n, 1);
        snprintf(n, sizeof n, "rd_add_h%d", i);
        rp.add_h[i] = widget_lookup(rp.win, n, 1);
        snprintf(n, sizeof n, "rd_add_hit%d", i);
        rp.add_hit[i] = m1_bind(rp.win, n, rp_on_add_hit, (void *)(long)i);
        if (!rp.add_v[i] || !rp.add_h[i] || !rp.add_hit[i]) sh_ok = 0;
    }
    rp.status = widget_lookup(rp.win, "label_status", 1);
    rp.st_title = widget_lookup(rp.win, "label_row_title", 1);
    rp.st_sub = widget_lookup(rp.win, "label_row_sub", 1);
    rp.st_gtitle = widget_lookup(rp.win, "label_grid_title", 1);
    rp.st_gsub = widget_lookup(rp.win, "label_grid_sub", 1);
    rp.al.win = rp.win, rp.al.sv = rp.sv, rp.al.top = SG_TITLE_H, rp.al.row = RP_ROW_ROOT;
    az_prefs(&rp.al);
    az_ok = az_bind(&rp.al, rp.win);
    if (!rp.back || !rp.np || !rp.find || !rp.view_btn || !rp.more || !rp.sh_scrim || !rp.sh_card || !sh_ok || !rp.lv ||
        !rp.credit || !rp.field || !rp.capsule || !rp.add_card || !rp.add_hair || !rp.title || !rp.big || !rp.view ||
        !rp.sv || !rp.status || !rp.st_title || !rp.st_sub || !rp.st_gtitle || !rp.st_gsub || !az_ok) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    m1_sel_init(&rp.ms, rp.win, rp.back, rp.title, rp.btn_selall, rp.bar, rp.del, (void *)0, (void *)0, (void *)0);
    label_set_line_wrap(rp.status, 1);
    widget_set_prop_bool(rp.status, "word_wrap", 1); /* break at spaces (a character break cut the hint mid-word) */
    widget_on(rp.status, EVT_POINTER_UP, rp_on_retry, (void *)0);
    widget_on(rp.sv, EVT_POINTER_UP, rp_on_retry, (void *)0);
    rp.chev = m1_make_chevron();
    for (i = 0; i < RI_N; ++i) rp.ic[i] = rp_bitmap(rp.win, RP_ICON_NAME[i]);
    rp.noscroll = grid_scroll_bind(rp.sv, rp_on_scroll, rp.title, &rp.title_on);
    widget_on(rp.win, EVT_WINDOW_TO_FG, rp_on_fg, (void *)0);
    widget_on(rp.win, EVT_WINDOW_TO_BG, rp_on_bg, (void *)0);
    widget_on(rp.view, EVT_POINTER_DOWN, rp_on_down, (void *)0);
    widget_on(rp.view, EVT_POINTER_MOVE, rp_on_move, (void *)0);
    widget_on(rp.view, EVT_POINTER_UP, rp_on_up, (void *)0);
    widget_on(rp.view, EVT_POINTER_ABORT, rp_on_abort, (void *)0);
    widget_on(rp.view, EVT_AFTER_PAINT, rp_on_paint, (void *)0);
    rp.vlist = set_read(RD_VIEW_FILE, '0') != '1'; /* the list unless the file says the grid */
    rp.dir = 1;
    widget_on(rp.field, EVT_POINTER_UP, rp_on_field, (void *)0);
    widget_on(rp.capsule, EVT_POINTER_UP, rp_on_field, (void *)0); /* (the magnifier's end of the capsule) */
    if (keyboard_attach(rp.win, TR("Search Stations"), 0, RP_TEXT_W, SE_CARET_Y, 0, rp_on_text, rp_on_go) != 0) {
        navigator_back(); /* an asset that is not ours, or a keyboard already up */
        return -2;
    }
    keyboard_show(0);
    m1_show(rp.field, 0);
    if (!grid_init(&rp.g, rp.win, GRID_TILES, GRID_COVER, GRID_R)) {
        grid_free(&rp.g);
        rp_note(TR("Not enough memory"));
        return 0;
    }
    rp.g.st_title = rp.st_gtitle, rp.g.st_sub = rp.st_gsub;
    az_make_disc(&rp.al);
    az_bind_rail(&rp.al, rp_on_rail, rp_on_rail_paint);
    rp.ltimer = timer_add(rp_on_ltick, (void *)0, 300);
    rp.level = L_ROOT;
    rp_show_level(L_ROOT, 0);
    return 0;
}
