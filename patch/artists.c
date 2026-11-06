/* M1+ Music Artists: the stock Local Music artists as an A-Z list in the Songs page's manner; a tap opens Cover Flow on that artist's albums.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The artist-to-Cover-Flow flow follows q2-pod: its Artists list hands an artist's albums to
 * coverflow_artist. On the M1 Plus the list is our own page instead of a hooked stock one.
 *
 * The list is the stock Artists list, sorted as the album Artist order is (ar_sort below):
 * loadLocalClassList(0xf004), which runs
 * GetAllAlbumArtist or getAllArtist as the stock Artists page's own artist/album-artist switch
 * (the artist_type global) says, each row named by REC_TITLE as the stock rows are.
 *
 * The page is the Songs page's structure (patch/songs.c, docs/modules/songs.md): the asset's stock list_view > scroll_view holds ONE content view, view_grid, that paints
 * the rows (a name and the chevron, no widget per row), the bare letter headers and the pinned header itself in its EVT_AFTER_PAINT; the large title is a label of the
 * content and the navbar shows the small one once it has scrolled away; the compact A-Z rail and its bubble (patch/azlist.c, shared with Songs) are widgets of the window
 * beside the scroll_view. Row text is the Albums page's tile text (patch/grid.c: a name cut once with an ellipsis).
 *
 * A navbar button (the Albums toggle's slot, NAV_VIEW_X) switches Artist and Album Artist: it makes the
 * same change the stock Artists page's own switch handler does (@0x535770): artist_type flipped,
 * [PLAYSET] ARTISTTYPE saved with write_int_config, and the stock page's reload flag (0xa06d20) raised so
 * a later stock Artists page rebuilds; the stock handler's toast and style swap are its own page's. The
 * title reads "Artists" or "Album Artists" and the button shows the other mode's glyph, the one a tap
 * switches to. The list is then queried again. Everything stock reads artist_type for (this list, an
 * artist's albums in Cover Flow and the album page) follows. Without the button or the title the page
 * still lists in the current mode.
 *
 * The same page lists Genres (class 0xf006) and Composers (0xf005) for the menu's Genres and Composers rows (artists_open's argument is the stock Home tile; 0 is
 * Artists): the title is the row's text, the Artist / Album Artist button is hidden and the order is the stock query's. A composer's tap is an artist's (Cover Flow on the
 * composer's albums: loadAlbumList(0xf005), class 0xff02); a genre's tap lists the genre's songs on our Songs page (songs_open_genre). Where the window will not open
 * the tile's stock page opens. docs/modules/artists.md.
 *
 * No stock function is hooked. The page is opened from the M1+ Music menu's Artists, Genres and Composers rows and
 * everything here runs from its own widgets; nothing of it outlives the window.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"

extern int coverflow_artist(void *artists, unsigned index, unsigned scope); /* patch/coverflow.c */
extern int albums_open_artist(void *artists, unsigned index, unsigned scope); /* patch/albums.c */
extern int songs_open_genre(const char *name, int unknown); /* patch/songs.c */
extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */

#define I(w, off) (*(int *)((char *)(w) + (off)))

#define AR_ROW \
    52 /* tools/pod_ui.py ROW_H: the menu's rows (the Artists rows were 52 px before the page took the Songs page's structure) */
#define AR_TOP \
    SG_TITLE_H /* the content y of the first header: right under the large title's row (Songs has the pills there too) */
#define AR_BOTTOM 12 /* air under the last row */
#define AR_TEXT_X 24
#define AR_TEXT_Y \
    ((AR_ROW - LIST_TITLE_H) / \
     2) /* the name's 24 px box (LIST_TITLE_H), centred in the row: a row cut by the window's edge has its name cut by the scroll_view's clip, as the Songs page's texts */
#define AR_TEXT_H LIST_TITLE_H
#define AR_TEXT_END \
    252 /* the names are cut here: the chevron stands between this and the rail's touch column (x 284) */
#define AR_CHEV_X 262
#define AR_CHEV_W POD_CHEV_W /* the chevron's bitmap, made by pod_make_chevron (patch/common.c) */
#define AR_CHEV_H POD_CHEV_H
#define AR_W 320 /* the content's width: the list_view's (the scroll_view clips at 310) */
#define MAX_ARTISTS 20000 /* one byte of rank and four of order each, no widget: bounded by the stock list's own size */
#define AR_TILES (GRID_VIEW_H / AR_ROW + 6) /* the text ring: the rows in view, two beyond and the history */

static struct {
    void *win, *view, *sv, *list, *status;
    void *title, *big, *toggle, *np, *fade,
        *st_title; /* label_title (the navbar's), ar_title (the large one), btn_artisttype, btn_backtoplayer, img_nb_fade, the row text style; any may be missing */
    void *artists; /* our copy of the stock artist rows */
    unsigned *order; /* stock row at each display position; NULL = stock order */
    unsigned char *rank; /* the section rank of each display position */
    unsigned count;
    unsigned cls; /* the stock class listed: CLASS_ARTISTS, CLASS_GENRES or CLASS_COMPOSERS */
    int home; /* its Home tile (HOME_GENRE, HOME_COMPOSER; 0 for Artists): where a window that will not open falls back */
    const char *key; /* the title's key: Artists, Album Artists, Genres, Composers */
    void *chev; /* the chevron bitmap */
    int press; /* the row under the finger, + 1 */
    int down, down_x, down_y; /* the row a press began on, + 1, and where */
    int title_on, noscroll;
    az_t al;
    grid_t g; /* the text ring (no covers) */
} ar __attribute__((section(".scratch")));

/* Hidden and out of the hit test together (this AWTK's widget_find_target ignores visible). */
static void ar_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int ar_abs(int v) { return v < 0 ? -v : v; }
static void ar_redraw(void) { widget_invalidate_force(ar.sv, (void *)0); }

static const char *ar_name(void *r) {
    const char *s = r ? *(const char **)((char *)r + REC_TITLE) : (const char *)0;
    return s ? s : "";
}

/* The stock row shown at display position i. */
static unsigned ar_stock(unsigned i) { return ar.order ? ar.order[i] : i; }

/* A tap: an artist's or a composer's albums on our Albums page (Cover Flow if that window will not open); a genre's songs on our Songs page (the stock row tap's classinfo and class 0xff09, songs_open_genre). */
static __attribute__((noinline)) int
ar_open(unsigned i) { /* (a symbol of its own: the tests call it with a display position) */
    if (!ar.artists || i >= ar.count) return RET_OK;
    if (ar.cls == CLASS_GENRES) {
        void *r = deque_at(ar.artists, ar_stock(i));
        songs_open_genre(ar_name(r), *(int *)((char *)r + REC_ID) == -1);
    } else if (albums_open_artist(ar.artists, ar_stock(i), ar.cls) == -1)
        coverflow_artist(ar.artists, ar_stock(i), ar.cls);
    return RET_OK;
}

/* The display order: all rows but the "Unknown Artist" row (id -1) are sorted as the album Artist order sorts names (cc_name_keys / cc_key_cmp: digit runs by
 * value, ASCII case aside, a leading "The " and white space dropped, a CJK name placed by its pinyin initials among the Latin ones; ties keep the stock order).
 * The Unknown rows keep their stock positions (stock puts them last) and the sorted rows fill the other positions in order, so "The Beatles" reaches B wherever
 * a fixed row sits. The stock rows are never reordered: order[] is the stock row number at each position; NULL (stock order) when there is no memory. */
static void **ar_rec __attribute__((section(".scratch")));
static const char **ar_key __attribute__((section(".scratch")));

static int ar_fixed(void *r) { return *(int *)((char *)r + REC_ID) == -1; }

static int ar_cmp(unsigned a, unsigned b) {
    int d = cc_key_cmp(ar_key[a], ar_key[b]);
    return d ? d : a < b ? -1 : a > b;
}

static const char *ar_text(const void *ctx, unsigned i) { return ar_name(((void *const *)ctx)[i]); }

static void ar_sort(void) {
    unsigned i, n = 0, *v;
    ar.order = (unsigned *)0;
    ar_key = (const char **)0;
    if (ar.count < 2) return;
    ar.order = calloc(ar.count, sizeof *ar.order);
    ar_rec = calloc(ar.count, sizeof *ar_rec);
    if (ar.order && ar_rec) {
        for (i = 0; i < ar.count; ++i) ar_rec[i] = deque_at(ar.artists, i);
        ar_key = cc_name_keys(ar.count, ar_text, ar_rec);
    }
    if (!ar.order || !ar_rec || !ar_key) {
        free(ar.order);
        ar.order = (unsigned *)0;
    } else {
        v = ar.order; /* the sorted rows first (their stock numbers), then spread over the positions the fixed rows leave */
        for (i = 0; i < ar.count; ++i)
            if (!ar_fixed(ar_rec[i])) v[n++] = i;
        cc_heapsort(v, n, ar_cmp);
        /* from the end: the next sorted row sits at or before i, so nothing still to read is overwritten */
        for (i = ar.count; i-- > 0;) v[i] = ar_fixed(ar_rec[i]) ? i : v[--n];
    }
    free(ar_rec);
    free((void *)ar_key);
    ar_rec = (void **)0, ar_key = (const char **)0;
}

/* The section ranks of the display order: the rank of the first character of the name the order compares (a leading "The " dropped, a CJK character as its pinyin
 * initial; a digit, a symbol and a name in another script are "#"), as the Songs page's Initial. The "Unknown ..." row (id -1; stock puts it last) takes the rank of the row before it: it is a stray by
 * nature and, as the last row of a run of single rows, could else tie with the row before it and swallow that row's section. The sections are then az_sections' (the
 * non-decreasing labelling: the list keeps its order, a row out of place stays in the section around it). No memory = a plain list. */
static void ar_sections(void) {
    unsigned i, prev = 0;
    ar.al.nsec = 0;
    ar.rank = calloc(ar.count, 1);
    if (!ar.rank) return;
    for (i = 0; i < ar.count; ++i) {
        void *r = deque_at(ar.artists, ar_stock(i));
        ar.rank[i] = *(int *)((char *)r + REC_ID) == -1 && i ? (unsigned char)prev
                                                             : (unsigned char)az_rank_of(cc_name_initial(ar_name(r)));
        prev = ar.rank[i];
    }
    az_sections(&ar.al, ar.rank, 1);
}

static int ar_content(void) { return az_rows_end(&ar.al) + AR_BOTTOM; }

/* The title: the mode's (or the row's) text, cut to the large title's 250 px and to the navbar's room, as the Songs lists' titles. */
static void ar_title_text(const char *key) {
    ar.key = key;
    az_fit(ar.title, TR(key));
    az_fit(ar.big, TR(key));
}

/* The small title is the navbar's once the large one has scrolled away; the fade is for rows passing under the bar (patch/songs.c sg_title_update). */
static void ar_title_update(void) {
    pod_title_set(ar.title, &ar.title_on, ar.noscroll || pod_title_gone(az_off(&ar.al), 0));
    if (ar.fade) {
        widget_set_visible(ar.fade, az_off(&ar.al) > 0, 0);
        widget_set_sensitive(ar.fade, 0);
    }
}

/* The title names the mode artist_type selects; the button shows the glyph of the other one. */
static void ar_mode_show(void) {
    int album = *(volatile int *)ARTIST_TYPE == 1;
    const char *icon = album ? "pod_nav_artist" : "pod_nav_albumartist";
    if (ar.cls !=
        CLASS_ARTISTS) { /* Genres and Composers: the menu row's text, and no Artist / Album Artist switch (hidden and out of the hit test) */
        ar_title_text(ar.cls == CLASS_GENRES ? "Genres" : "Composers");
        ar_show(ar.toggle, 0);
        if (ar.np) { /* Now Playing is the capsule's right cap in the asset (it has the switch to its left): alone it is the glass disc, as on every page with no toggle */
            widget_set_prop_str(ar.np, "style:normal:icon", "ah_nav_np");
            widget_set_prop_str(ar.np, "style:over:icon", "ah_nav_np");
            widget_set_prop_str(ar.np, "style:pressed:icon", "ah_nav_np_down");
        }
        return;
    }
    ar_title_text(album ? "Album Artists" : "Artists");
    if (ar.toggle) {
        widget_set_prop_str(ar.toggle, "style:normal:icon", icon);
        widget_set_prop_str(ar.toggle, "style:over:icon", icon);
        widget_set_prop_str(ar.toggle, "style:pressed:icon",
                            album ? "pod_nav_artist_down" : "pod_nav_albumartist_down");
        widget_invalidate_force(ar.toggle, (void *)0);
    }
}

/* ---------------------------------------------------------------------------
 * Paint: the rows, the headers and the pinned header in one EVT_AFTER_PAINT of the content view, in window coordinates (patch/songs.c sg_paint_rows)
 */
static grid_tile_t *ar_tile(int a) {
    int lo, hi, fresh;
    grid_tile_t *t;
    az_span(&ar.al, &lo, &hi);
    t = grid_tile(&ar.g, a, lo, hi, &fresh);
    if (fresh) grid_set(t, ar_name(deque_at(ar.artists, ar_stock((unsigned)a))), "", 0);
    return t;
}

static void ar_paint_rows(void *canvas) {
    int r0, r1, r, off = az_off(&ar.al);
    az_span(&ar.al, &r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = az_row_y(&ar.al, r) - off;
        if (ar.press == r + 1) az_fill(canvas, 0, y, y + AR_ROW - 1, AR_W, LIST_PRESS);
        az_fill(canvas, AR_TEXT_X, y + AR_ROW - 1, y + AR_ROW, SG_TEXT_END - AR_TEXT_X, LIST_HAIR);
        if (ar.chev) {
            int src[4], dst[4], top = y + (AR_ROW - AR_CHEV_H) / 2;
            if (top >= 0 && top + AR_CHEV_H <= GRID_VIEW_H) {
                src[0] = src[1] = 0, src[2] = AR_CHEV_W, src[3] = AR_CHEV_H;
                dst[0] = AR_CHEV_X, dst[1] = top, dst[2] = AR_CHEV_W, dst[3] = AR_CHEV_H;
                canvas_draw_image(canvas, ar.chev, src, dst);
            }
        }
    }
    widget_prepare_text_style(ar.st_title, canvas);
    for (r = r0; r <= r1; ++r)
        grid_text(canvas, ar_tile(r), 0, AR_TEXT_X, az_row_y(&ar.al, r) - off + AR_TEXT_Y, AR_TEXT_END - AR_TEXT_X,
                  AR_TEXT_H, 0);
    az_paint_heads(&ar.al, canvas); /* the section letters, then over everything the pinned band and its letter */
}

static int ar_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = az_off(&ar.al);
    (void)ctx;
    if (!canvas || !ar.view || !ar.g.tiles || !ar.count || !ar.artists) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    ar_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows (patch/songs.c: DOWN remembers, ABORT forgets, UP within the drag threshold on the same row acts)
 */
static int ar_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(ar.view, pt);
    return az_at(&ar.al, pt[1]);
}

static void ar_set_press(int p) {
    if (ar.press == p) return;
    ar.press = p;
    ar_redraw();
}

static int ar_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    ar.down = 0;
    if (!e || !ar.view || !ar.count) return RET_OK;
    a = ar_item_of(e);
    ar.down = a + 1, ar.down_x = I(e, PE_X), ar.down_y = I(e, PE_Y);
    ar_set_press(a + 1);
    return RET_OK;
}

static int ar_on_up(void *ctx, void *e) {
    int a = ar.down - 1;
    (void)ctx;
    ar.down = 0;
    ar_set_press(0);
    if (a < 0 || !e || !ar.view) return RET_OK;
    if (ar_abs(I(e, PE_X) - ar.down_x) < SC_DRAG_PX && ar_abs(I(e, PE_Y) - ar.down_y) < SC_DRAG_PX &&
        ar_item_of(e) == a)
        ar_open((unsigned)a);
    return RET_OK;
}

static int ar_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ar.down = 0;
    ar_set_press(0);
    return RET_OK;
}

static int ar_on_rail(void *ctx, void *e) {
    (void)ctx;
    if (ar.view) az_rail_event(&ar.al, e);
    return RET_OK;
}

static int ar_on_rail_paint(void *ctx, void *e) {
    (void)ctx;
    if (ar.view) az_rail_paint(&ar.al, e);
    return RET_OK;
}

static int ar_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ar.view) ar_title_update();
    return RET_OK;
}

static int ar_on_bg(void *ctx, void *e) {
    az_rail_end(&ar.al);
    return ar_on_abort(ctx, e);
}

static int ar_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ar.artists) deque_destroy(ar.artists);
    grid_free(&ar.g);
    az_free(&ar.al);
    if (ar.chev) bitmap_destroy(ar.chev);
    free(ar.order);
    free(ar.rank);
    memset(&ar, 0, sizeof ar);
    return RET_OK;
}

/* (Re)build the list from the stock query, with artist_type as it is: a copy of the stock rows, so Cover
 * Flow's own queries cannot pull it away. */
static void ar_load(void) {
    void *list;
    int h;
    if (ar.artists) deque_destroy(ar.artists);
    ar.artists = (void *)0;
    free(ar.order);
    free(ar.rank);
    ar.order = (unsigned *)0, ar.rank = (unsigned char *)0;
    ar.count = 0, ar.press = ar.down = 0;
    ar.al.count = 0, ar.al.nsec = 0;
    grid_drop(&ar.g);
    widget_set_prop_int(ar.sv, "yoffset", 0);
    list = loadLocalClassList(ar.cls) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    if (list && deque_size(list) && (ar.artists = _create_deque("stSongInfo"))) {
        deque_init(ar.artists);
        deque_assign(ar.artists, list);
        ar.count = deque_size(ar.artists);
        if (ar.count > MAX_ARTISTS) ar.count = MAX_ARTISTS;
        if (ar.cls == CLASS_ARTISTS)
            ar_sort(); /* Genres and Composers stay in stock's order (toolsQueryDbTable's in-memory title sort) */
    }
    ar.al.count = (int)ar.count;
    if (ar.count) ar_sections();
    ar.al.content = ar_content();
    h = ar.count ? ar.al.content : GRID_VIEW_H;
    widget_resize(ar.view, AR_W, h);
    widget_set_prop_int(ar.sv, "virtual_h", h);
    ar_show(ar.list, ar.count != 0);
    ar_show(ar.status, ar.count == 0);
    if (!ar.count) widget_set_tr_text(ar.status, "Update Local Music first");
    az_rail_fit(&ar.al, GRID_VIEW_H);
    ar_title_update();
    ar_redraw();
}

/* The button: flip the stock setting the way the stock switch does, then list again. */
static int ar_on_toggle(void *ctx, void *e) {
    int type = *(volatile int *)ARTIST_TYPE != 1;
    (void)ctx;
    (void)e;
    if (ar.cls != CLASS_ARTISTS)
        return RET_OK; /* Genres and Composers have no switch (the button is hidden; a stray click changes nothing) */
    *(volatile int *)ARTIST_TYPE = type;
    write_int_config(type, "PLAYSET", "ARTISTTYPE");
    *(volatile unsigned char *)ARTIST_RELOAD = 1;
    ar_mode_show();
    ar_load();
    return RET_OK;
}

/* The M1+ Music menu's Artists row (home 0), or Genres (HOME_GENRE) or Composers (HOME_COMPOSER): the same page on another stock class. 0 once the page is up, -1 if
 * it could not open (Genres and Composers then open the tile's stock page, as the Songs lists do). */
int artists_open(int home) {
    if (ar.win) return -1;
    memset(&ar, 0, sizeof ar);
    ar.cls = home == HOME_GENRE ? CLASS_GENRES : home == HOME_COMPOSER ? CLASS_COMPOSERS : CLASS_ARTISTS;
    ar.home = ar.cls == CLASS_ARTISTS ? 0 : home;
    ar.win = window_open("m1plus_artists");
    if (!ar.win) {
        int h = ar.home;
        memset(&ar, 0, sizeof ar);
        return h ? pod_home_open(h) : -1;
    }
    widget_on(ar.win, EVT_DESTROY, ar_on_destroy, (void *)0);
    pod_bind(ar.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(ar.win, "btn_backtoplayer", pod_on_player, (void *)0);
    ar.list = widget_lookup(ar.win, "artists_listview", 1);
    ar.sv = widget_lookup(ar.win, "artists_scrollview", 1);
    ar.view = widget_lookup(ar.win, "view_grid", 1);
    ar.status = widget_lookup(ar.win, "label_status", 1);
    ar.title = widget_lookup(ar.win, "label_title", 1);
    ar.big = widget_lookup(ar.win, "ar_title", 1);
    ar.toggle = widget_lookup(ar.win, "btn_artisttype", 1);
    ar.np = widget_lookup(ar.win, "btn_backtoplayer", 1);
    ar.fade = widget_lookup(ar.win, "img_nb_fade", 1);
    ar.st_title = widget_lookup(ar.win, "label_row_title", 1);
    ar.al.win = ar.win, ar.al.sv = ar.sv, ar.al.top = AR_TOP, ar.al.row = AR_ROW;
    ar.al.st_hdr = widget_lookup(ar.win, "label_hdr", 1);
    ar.al.st_rail = widget_lookup(ar.win, "label_rail", 1);
    ar.al.st_rail_on = widget_lookup(ar.win, "label_rail_on", 1);
    ar.al.rail = widget_lookup(ar.win, "sg_rail", 1);
    ar.al.bubble = widget_lookup(ar.win, "sg_bubble", 1);
    ar.al.bubble_letter = widget_lookup(ar.win, "sg_bubble_letter", 1);
    if (ar.toggle) widget_on(ar.toggle, EVT_CLICK, ar_on_toggle, (void *)0);
    if (!ar.list || !ar.sv || !ar.view || !ar.status || !ar.st_title || !ar.al.st_hdr || !ar.al.st_rail ||
        !ar.al.st_rail_on || !ar.al.rail || !ar.al.bubble || !ar.al.bubble_letter) {
        int h = ar.home;
        navigator_back(); /* an asset that is not ours */
        return h ? pod_home_open(h) : -1;
    }
    if (!grid_init(&ar.g, ar.win, AR_TILES, 0, 0)) {
        int h = ar.home;
        grid_free(&ar.g);
        navigator_back();
        return h ? pod_home_open(h) : -1;
    }
    az_make_disc(&ar.al);
    ar.chev = pod_make_chevron();
    ar.noscroll = !widget_on(ar.sv, EVT_SCROLL, ar_on_scroll, (void *)0) ||
                  !widget_on(ar.sv, EVT_SCROLL_END, ar_on_scroll, (void *)0);
    if (ar.noscroll && ar.title)
        widget_set_visible(
            ar.title, 1,
            0); /* the large title's collapse needs the scroll events: without them the navbar keeps its title */
    ar.title_on = ar.noscroll;
    widget_on(ar.win, EVT_WINDOW_TO_BG, ar_on_bg, (void *)0);
    widget_on(ar.view, EVT_POINTER_DOWN, ar_on_down, (void *)0);
    widget_on(ar.view, EVT_POINTER_UP, ar_on_up, (void *)0);
    widget_on(ar.view, EVT_POINTER_ABORT, ar_on_abort, (void *)0);
    widget_on(ar.view, EVT_AFTER_PAINT, ar_on_paint, (void *)0);
    widget_on(ar.al.rail, EVT_POINTER_DOWN, ar_on_rail, (void *)0);
    widget_on(ar.al.rail, EVT_POINTER_MOVE, ar_on_rail, (void *)0);
    widget_on(ar.al.rail, EVT_POINTER_UP, ar_on_rail, (void *)0);
    widget_on(ar.al.rail, EVT_POINTER_ABORT, ar_on_rail, (void *)0);
    widget_on(ar.al.rail, EVT_AFTER_PAINT, ar_on_rail_paint, (void *)0);
    ar_mode_show();
    ar_load();
    return 0;
}
