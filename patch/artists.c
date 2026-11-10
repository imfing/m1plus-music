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
 * The navbar's "..." (the capsule's left cap, NAV_VIEW_X) opens the shared card (patch/viewsort.c): Search Artists (Artists only), the Show group (Artists, Album Artists: Artists
 * only) and the Name order, which a tap on the ticked row reverses (A-Z, Z-A; saved per page in artists-sort, genres-sort, composers-sort). A Show row makes the same change the stock
 * Artists page's own switch handler does (@0x535770): artist_type set, [PLAYSET] ARTISTTYPE saved with write_int_config, and the stock page's reload flag (0xa06d20) raised so
 * a later stock Artists page rebuilds; the stock handler's toast and style swap are its own page's. The title reads "Artists" or "Album Artists". The list is then queried again.
 * Everything stock reads artist_type for (this list, an artist's albums in Cover Flow and the album page) follows.
 *
 * The same page lists Genres (class 0xf006) and Composers (0xf005) for the menu's Genres and Composers rows (artists_open's argument is the stock Home tile; 0 is
 * Artists): the title is the row's text, the card has the Name order alone and the order is the stock query's (Z-A reversed). A composer's tap is an artist's (Cover Flow on the
 * composer's albums: loadAlbumList(0xf005), class 0xff02); a genre's tap lists the genre's songs on our Songs page (songs_open_genre). Where the window will not open
 * the tile's stock page opens. docs/modules/artists.md.
 *
 * Artists and Album Artists rows carry the artist's photo (docs/modules/artists.md "Artist photos"): a 40 px circle at x 16, the name from x 68; the circle is decoded by the page's own timer, one a tick
 * (ar_on_photo, patch/artistphoto.c ap_lookup / grid ring), never in a paint; a row without one shows the shared placeholder.
 *
 * No stock function is hooked. The page is opened from the M1+ Music menu's Artists, Genres and Composers rows and
 * everything here runs from its own widgets; nothing of it outlives the window.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "viewsort.h"
#include "search.h"
#include "artistphoto.h"

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
#define AR_PHOTO AP_ROW_D /* the artist's circle (Artists and Album Artists only), 40 px at x 16, centred in the row */
#define AR_PHOTO_X 16
#define AR_NAME_X \
    68 /* the name and the hairline of a row with a circle start here (AR_TEXT_X on Genres and Composers) */
#define AR_PHOTO_MS 16 /* the photo loader's tick */
#define AR_RETRY_MS 1000
#define AR_TEXT_Y \
    ((AR_ROW - LIST_TITLE_H) / \
     2) /* the name's 24 px box (LIST_TITLE_H), centred in the row: a row cut by the window's edge has its name cut by the scroll_view's clip, as the Songs page's texts */
#define AR_TEXT_H LIST_TITLE_H
#define AR_TEXT_END \
    (LIST_TEXT_X + \
     LIST_TEXT_W_CHEV) /* the names are cut here (278), the chevron at AR_CHEV_X: the list-row spec; both move left by az_inset while the rail is shown (x 252 and 262) */
#define AR_CHEV_X LIST_CHEV_X
#define AR_CHEV_W POD_CHEV_W /* the chevron's bitmap, made by pod_make_chevron (patch/common.c) */
#define AR_CHEV_H POD_CHEV_H
#define AR_W 320 /* the content's width: the list_view's (the scroll_view clips at 310) */
#define MAX_ARTISTS 20000 /* one byte of rank and four of order each, no widget: bounded by the stock list's own size */
#define AR_TILES (GRID_VIEW_H / AR_ROW + 6) /* the text ring: the rows in view, two beyond and the history */

static struct {
    void *win, *view, *sv, *list, *status;
    void *title, *big, *fade,
        *st_title; /* label_title (the navbar's), ar_title (the large one), img_nb_fade, the row text style; any may be missing */
    vs_t vs; /* the "..." card */
    int rev; /* the Name order is Z-A (the saved page setting) */
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
    int photo; /* Artists and Album Artists: rows with a circle (the ring decodes it, ar_on_photo) */
    unsigned char *
        pst; /* 2 bits per display position: AP_UNKNOWN / AP_PHOTO / AP_NONE / AP_LEAD (ap_lookup's answer once it is known) */
    unsigned photo_timer; /* the loader's */
    unsigned
        epoch; /* ap_epoch() when the circles were last looked at: a re-check on an artist's page that changed a photo shows here when the page is in front again */
    unsigned
        retry_timer; /* while the Home pass makes photos: asks, every AR_RETRY_MS, whether it is over, then the rows without a file look again */
    az_t al;
    grid_t g; /* the text ring; with photo, the circles too (AR_PHOTO px, the corners cut in the alpha) */
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
    int keyed = ar.cls ==
                CLASS_ARTISTS; /* Genres and Composers keep stock's order (the in-memory title sort) unless reversed */
    ar.order = (unsigned *)0;
    ar_key = (const char **)0;
    if (ar.count < 2 || (!keyed && !ar.rev)) return;
    ar.order = calloc(ar.count, sizeof *ar.order);
    ar_rec = calloc(ar.count, sizeof *ar_rec);
    if (ar.order && ar_rec) {
        for (i = 0; i < ar.count; ++i) ar_rec[i] = deque_at(ar.artists, i);
        if (keyed) ar_key = cc_name_keys(ar.count, ar_text, ar_rec);
    }
    if (!ar.order || !ar_rec || (keyed && !ar_key)) {
        free(ar.order);
        ar.order = (unsigned *)0;
    } else {
        v = ar.order; /* the sorted rows first (their stock numbers), then spread over the positions the fixed rows leave */
        for (i = 0; i < ar.count; ++i)
            if (!ar_fixed(ar_rec[i])) v[n++] = i;
        if (keyed) cc_heapsort(v, n, ar_cmp);
        if (ar.rev) /* Z-A: the sorted rows the other way round; the Unknown rows still keep their stock (last) positions */
            for (i = 0; i < n / 2; ++i) {
                unsigned t = v[i];
                v[i] = v[n - 1 - i], v[n - 1 - i] = t;
            }
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
        int k = az_rank_of(cc_name_initial(ar_name(r)));
        if (ar.rev)
            k = k ? 26 - k
                  : 26; /* Z-A: Z is rank 0 .. A rank 25 and "#" (symbols, digits) last, so the ranks still rise down the list */
        ar.rank[i] = *(int *)((char *)r + REC_ID) == -1 && i ? (unsigned char)prev : (unsigned char)k;
        prev = ar.rank[i];
    }
    az_sections(&ar.al, ar.rank, 1);
    if (ar.rev) /* the headers and the rail show the letters of those ranks: rank 0 is Z, 25 is A, 26 is "#" */
        for (i = 0; i < (unsigned)ar.al.nsec; ++i) {
            int t = ar.al.sec_letter[i] == '#'
                        ? 0
                        : ar.al.sec_letter[i] - 'A' + 1; /* (the rank az_sections labelled it with) */
            ar.al.sec_letter[i] = (unsigned char)(t == 26 ? '#' : 'Z' - t);
        }
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

/* The title names the mode artist_type selects (Artists / Album Artists), or the page (Genres, Composers). */
static void ar_mode_show(void) {
    if (ar.cls != CLASS_ARTISTS) {
        ar_title_text(ar.cls == CLASS_GENRES ? "Genres" : "Composers");
        return;
    }
    ar_title_text(*(volatile int *)ARTIST_TYPE == 1 ? "Album Artists" : "Artists");
}

/* ---------------------------------------------------------------------------
 * Paint: the rows, the headers and the pinned header in one EVT_AFTER_PAINT of the content view, in window coordinates (patch/songs.c sg_paint_rows)
 */
/* The photo state of display position i (2 bits each). */
static unsigned ar_st(unsigned i) { return ar.pst ? (unsigned)(ar.pst[i >> 2] >> (i & 3) * 2) & 3u : AP_UNKNOWN; }

static void ar_st_set(unsigned i, unsigned v) {
    if (ar.pst) ar.pst[i >> 2] = (unsigned char)((ar.pst[i >> 2] & ~(3u << (i & 3) * 2)) | v << (i & 3) * 2);
}

static grid_tile_t *ar_tile(int a) {
    int lo, hi, fresh;
    grid_tile_t *t;
    az_span(&ar.al, &lo, &hi);
    t = grid_tile(&ar.g, a, lo, hi, &fresh);
    if (fresh) {
        void *rec = deque_at(ar.artists, ar_stock((unsigned)a));
        grid_set(t, ar_name(rec), "", 0);
        if (ar.photo && (ar_fixed(rec) || ar_st((unsigned)a) == AP_NONE))
            t->art = 2; /* no photo: the placeholder, nothing to load */
    }
    return t;
}

static void ar_paint_rows(void *canvas) {
    int r0, r1, r, off = az_off(&ar.al), tx = ar.photo ? AR_NAME_X : AR_TEXT_X;
    az_span(&ar.al, &r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = az_row_y(&ar.al, r) - off;
        if (ar.press == r + 1) az_fill(canvas, 0, y, y + AR_ROW - 1, AR_W, LIST_PRESS);
        az_fill(canvas, tx, y + AR_ROW - 1, y + AR_ROW, az_end(&ar.al) - tx, LIST_HAIR);
        if (ar.photo) grid_blit(canvas, &ar.g, ar_tile(r), AR_PHOTO_X, y + (AR_ROW - AR_PHOTO) / 2, GRID_VIEW_H);
        if (ar.chev) {
            int src[4], dst[4], top = y + (AR_ROW - AR_CHEV_H) / 2;
            if (top >= 0 && top + AR_CHEV_H <= GRID_VIEW_H) {
                src[0] = src[1] = 0, src[2] = AR_CHEV_W, src[3] = AR_CHEV_H;
                dst[0] = AR_CHEV_X - az_inset(&ar.al), dst[1] = top, dst[2] = AR_CHEV_W, dst[3] = AR_CHEV_H;
                canvas_draw_image(canvas, ar.chev, src, dst);
            }
        }
    }
    widget_prepare_text_style(ar.st_title, canvas);
    for (r = r0; r <= r1; ++r)
        grid_text(canvas, ar_tile(r), 0, tx, az_row_y(&ar.al, r) - off + AR_TEXT_Y, AR_TEXT_END - az_inset(&ar.al) - tx,
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
 * The photo loader: one circle per tick on the page's own timer, none while the list moves (the Albums page's loader; paint never opens a file)
 */
/* Row r still needs a look: its tile was not tried, or it has none yet and its state is not "no photo". */
static int ar_wants(int r) {
    grid_tile_t *t = grid_find(&ar.g, r);
    if (t) return !t->art;
    return ar_st((unsigned)r) != AP_NONE && !ar_fixed(deque_at(ar.artists, ar_stock((unsigned)r)));
}

/* The row to look at next, or -1: of the rows in view the one nearest the middle of the window. */
static int ar_next_photo(void) {
    int lo, hi, r, best = -1, bd = 0x7fffffff;
    if (!ar.photo || !ar.g.tiles || !ar.count || !ar.artists) return -1;
    az_span(&ar.al, &lo, &hi);
    for (r = lo; r <= hi; ++r) {
        int d;
        if (!ar_wants(r)) continue;
        d = ar_abs(az_row_y(&ar.al, r) - az_off(&ar.al) + AR_ROW / 2 - GRID_VIEW_H / 2);
        if (d < bd) bd = d, best = r;
    }
    return best;
}

static int ar_on_retry(const void *unused);

/* A row whose file is missing is looked for again once the Home pass that makes the photos is over (the Albums page's al_retry): while a set runs a slow timer waits for its end. */
static void ar_retry_arm(void) {
    if (!ar.retry_timer && ar.view && cc_build_active())
        ar.retry_timer = timer_add(ar_on_retry, (void *)0, AR_RETRY_MS);
}

/* Row r's circle: the -44 file of the name's key (the lead artist's when the name has none), decoded; no file leaves the placeholder, and an empty marker (or a file that does not decode) is remembered as "no photo". */
static void ar_photo_row(int r) {
    grid_tile_t *t = ar_tile(r);
    char url[80];
    int st;
    if (t->art) return;
    st = ap_lookup(ar_name(deque_at(ar.artists, ar_stock((unsigned)r))), AP_LIST, url);
    if (st == AP_PHOTO || st == AP_LEAD) {
        grid_art_url(&ar.g, t, url);
        if (t->art == 1) {
            ar_st_set((unsigned)r, (unsigned)st);
            return;
        }
        st = AP_NONE;
    } else
        t->art = 2;
    if (st == AP_NONE) ar_st_set((unsigned)r, AP_NONE);
    if (st == AP_UNKNOWN) ar_retry_arm();
}

static int ar_on_photo(const void *unused);

static void ar_kick(void) {
    if (ar.photo && !ar.photo_timer && ar.view && ar_next_photo() >= 0)
        ar.photo_timer = timer_add(ar_on_photo, (void *)0, AR_PHOTO_MS);
}

static int ar_on_retry(const void *unused) {
    int i;
    (void)unused;
    ar.retry_timer = 0;
    if (!ar.view || !ar.g.tiles) return RET_OK;
    if (cc_build_active()) { /* still making photos (or covers): ask again */
        ar_retry_arm();
        return RET_OK;
    }
    for (i = 0; i < ar.g.n; ++i) {
        grid_tile_t *t = &ar.g.tiles[i];
        if (t->album && t->art == 2 && ar_st((unsigned)(t->album - 1)) == AP_UNKNOWN) t->art = 0;
    }
    ar_kick();
    return RET_OK;
}

static int ar_on_photo(const void *unused) {
    int r;
    (void)unused;
    ar.photo_timer = 0;
    if (!ar.view || !ar.g.tiles) return RET_OK;
    if (grid_moving(
            ar.sv)) { /* a decode is a few ms on the UI thread and the next touch would wait behind it: look again next tick */
        ar_kick();
        return RET_OK;
    }
    r = ar_next_photo();
    if (r >= 0) {
        ar_photo_row(r);
        ar_redraw();
    }
    ar_kick();
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
    if (ar.view) ar_title_update(), ar_kick();
    return RET_OK;
}

/* The page is in front again: a re-check on an artist's page since the circles were last looked at made, replaced or removed a photo, so every circle is looked for again (the tiles dropped, the answers forgotten; one decode a tick as ever). */
static int ar_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ar.photo || !ar.view || ar.epoch == ap_epoch()) return RET_OK;
    ar.epoch = ap_epoch();
    if (ar.pst) memset(ar.pst, 0, (ar.count + 3) / 4);
    grid_drop(&ar.g);
    ar.g.placeholder = ap_placeholder(ar.win, AR_PHOTO);
    ar_redraw();
    ar_kick();
    return RET_OK;
}

static int ar_on_bg(void *ctx, void *e) {
    az_rail_end(&ar.al);
    return ar_on_abort(ctx, e);
}

static int ar_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ar.photo_timer) timer_remove(ar.photo_timer);
    if (ar.retry_timer) timer_remove(ar.retry_timer);
    if (ar.artists) deque_destroy(ar.artists);
    grid_free(&ar.g);
    az_free(&ar.al);
    if (ar.chev) bitmap_destroy(ar.chev);
    free(ar.order);
    free(ar.rank);
    free(ar.pst);
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
    free(ar.pst);
    ar.order = (unsigned *)0, ar.rank = (unsigned char *)0, ar.pst = (unsigned char *)0;
    ar.count = 0, ar.press = ar.down = 0;
    ar.al.count = 0, ar.al.nsec = 0;
    grid_drop(&ar.g); /* (the circles, the placeholder too) */
    if (ar.photo) ar.g.placeholder = ap_placeholder(ar.win, AR_PHOTO);
    widget_set_prop_int(ar.sv, "yoffset", 0);
    list = loadLocalClassList(ar.cls) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    if (list && deque_size(list) && (ar.artists = _create_deque("stSongInfo"))) {
        deque_init(ar.artists);
        deque_assign(ar.artists, list);
        ar.count = deque_size(ar.artists);
        if (ar.count > MAX_ARTISTS) ar.count = MAX_ARTISTS;
        ar_sort(); /* Genres and Composers stay in stock's order (toolsQueryDbTable's in-memory title sort) unless Z-A */
    }
    ar.al.count = (int)ar.count;
    if (ar.photo && ar.count)
        ar.pst = calloc((ar.count + 3) / 4, 1); /* (no memory = every row unknown: the circles are looked for again) */
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
    ar_kick();
}

/* The page's saved order: artists-sort, genres-sort or composers-sort, one character: '0' Name A-Z (the default and any other content), 'a' Name Z-A. */
static const char *ar_sort_file(int tmp) {
    return ar.cls == CLASS_GENRES      ? (tmp ? GENRES_SORT_TMP : GENRES_SORT_FILE)
           : ar.cls == CLASS_COMPOSERS ? (tmp ? COMPOSERS_SORT_TMP : COMPOSERS_SORT_FILE)
                                       : (tmp ? ARTISTS_SORT_TMP : ARTISTS_SORT_FILE);
}

static void ar_card(int on) { vs_menu(&ar.vs, on, 0, ar.rev, *(volatile int *)ARTIST_TYPE == 1); }

/* The Show group's rows (Artists only): flip the stock setting the way the stock switch does, then list again; the row already ticked does nothing. */
static void ar_set_type(int type) {
    if (ar.cls != CLASS_ARTISTS || type == (*(volatile int *)ARTIST_TYPE == 1)) return;
    *(volatile int *)ARTIST_TYPE = type;
    write_int_config(type, "PLAYSET", "ARTISTTYPE");
    *(volatile unsigned char *)ARTIST_RELOAD = 1;
    ar_mode_show();
    ar_load();
}

/* The card's rows: Search Artists opens the Search page scoped to artists (the library search where that will not open); Artists / Album Artists set the type; the Name row reverses the order
 * (saved first: a save that fails leaves the order and its tick). The card closes. */
static int ar_on_item(void *ctx, void *e) {
    int k = (int)(long)ctx;
    (void)e;
    if (!ar.view) return RET_OK;
    ar_card(0);
    if (k == VS_SEARCH) {
        if (search_open_in(SEARCH_ARTISTS) < 0) search_open();
    } else if (k == VS_SORTS || k == VS_SORTS + 1) {
        ar_set_type(k == VS_SORTS + 1);
    } else if (k == 0) {
        int rev = !ar.rev;
        if (home_write_atomic(ar_sort_file(0), ar_sort_file(1), rev ? "a\n" : "0\n") == 0) {
            ar.rev = rev;
            ar_load();
        }
    }
    return RET_OK;
}

static int ar_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ar_card(0);
    return RET_OK;
}

static int ar_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ar.win && ar.vs.card) ar_card(!ar.vs.on);
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
    ar.fade = widget_lookup(ar.win, "img_nb_fade", 1);
    ar.st_title = widget_lookup(ar.win, "label_row_title", 1);
    ar.al.win = ar.win, ar.al.sv = ar.sv, ar.al.top = AR_TOP, ar.al.row = AR_ROW;
    az_prefs(&ar.al);
    ar.al.st_hdr = widget_lookup(ar.win, "label_hdr", 1);
    ar.al.st_rail = widget_lookup(ar.win, "label_rail", 1);
    ar.al.st_rail_on = widget_lookup(ar.win, "label_rail_on", 1);
    ar.al.rail = widget_lookup(ar.win, "sg_rail", 1);
    ar.al.bubble = widget_lookup(ar.win, "sg_bubble", 1);
    ar.al.bubble_letter = widget_lookup(ar.win, "sg_bubble_letter", 1);
    pod_bind(ar.win, "btn_more", ar_on_more, (void *)0);
    if (!ar.list || !ar.sv || !ar.view || !ar.status || !ar.st_title || !ar.al.st_hdr || !ar.al.st_rail ||
        !ar.al.st_rail_on || !ar.al.rail || !ar.al.bubble || !ar.al.bubble_letter) {
        int h = ar.home;
        navigator_back(); /* an asset that is not ours */
        return h ? pod_home_open(h) : -1;
    }
    ar.photo =
        ar.cls == CLASS_ARTISTS; /* Genres and Composers rows stay as they were: no circle, the name at AR_TEXT_X */
    if (!grid_init(&ar.g, ar.win, AR_TILES, ar.photo ? AR_PHOTO : 0, ar.photo ? AR_PHOTO / 2 : 0)) {
        int h = ar.home;
        grid_free(&ar.g);
        navigator_back();
        return h ? pod_home_open(h) : -1;
    }
    if (ar.photo)
        grid_shape(&ar.g, AR_PHOTO, AR_PHOTO / 2,
                   1); /* the corners cut in the alpha: the pressed row's fill shows behind the circle */
    if (vs_bind(&ar.vs, ar.win, ar_on_item, ar_on_scrim,
                ar.cls == CLASS_ARTISTS
                    ? (1u << 0) | VS_WITH_VIEWS | VS_WITH_SEARCH
                    : (1u << 0))) { /* (Name alone on Genres and Composers; they have no Search scope or Show group) */
        int h = ar.home;
        grid_free(&ar.g);
        navigator_back(); /* an asset that is not ours */
        return h ? pod_home_open(h) : -1;
    }
    ar.rev = set_read(ar_sort_file(0), '0') == 'a';
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
    ar.epoch = ap_epoch();
    widget_on(ar.win, EVT_WINDOW_TO_FG, ar_on_fg, (void *)0);
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
