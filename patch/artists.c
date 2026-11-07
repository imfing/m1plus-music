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
#include "subsonic.h"

extern int coverflow_artist(void *artists, unsigned index, unsigned scope); /* patch/coverflow.c */
extern int albums_open_artist(void *artists, unsigned index, unsigned scope); /* patch/albums.c */
extern int songs_open_genre(const char *name, int unknown); /* patch/songs.c */
extern int songs_open_nav_filter(int filter, const char *name, const char *artist); /* patch/songs.c */
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

typedef struct {
    const char *name;
    unsigned local_index;
    unsigned char local, fixed, has_remote;
} ar_item_t;

typedef struct {
    unsigned hash, local_index;
} ar_name_slot_t;

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
    unsigned item_count, local_count, nav_cursor, nav_total, nav_slot_cap, nav_timer;
    int nav_scanning;
    ar_item_t *item;
    ar_name_slot_t *nav_slots;
    sb_library_index_t nav_index;
    unsigned cls; /* the stock class listed: CLASS_ARTISTS, CLASS_GENRES or CLASS_COMPOSERS */
    int album_artist; /* snapshot of ARTIST_TYPE for this list and its async server scan */
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

static unsigned ar_stock(unsigned i) { return ar.order ? ar.order[i] : i; }

static ar_item_t *ar_item_at(unsigned display) {
    unsigned index = ar_stock(display);
    return ar.item && index < ar.count ? &ar.item[index] : (ar_item_t *)0;
}

static int ar_filter(void) {
    if (ar.cls == CLASS_GENRES) return SB_LIBRARY_FILTER_GENRE;
    if (ar.cls == CLASS_COMPOSERS) return SB_LIBRARY_FILTER_COMPOSER;
    return ar.album_artist ? SB_LIBRARY_FILTER_ALBUM_ARTIST : SB_LIBRARY_FILTER_ARTIST;
}

static void ar_local_items(unsigned local_count);
static void ar_nav_schedule(void);

static const char *ar_item_name(unsigned display) {
    ar_item_t *item = ar_item_at(display);
    return item && item->name ? item->name : "";
}

/* A tap uses the virtual track list when this category has server entries; local-only rows retain their stock route. */
static __attribute__((noinline)) int ar_open(unsigned i) {
    ar_item_t *item = ar_item_at(i);
    void *r;
    if (!item || !item->name) return RET_OK;
    if (ar.cls == CLASS_ARTISTS) *(volatile int *)ARTIST_TYPE = ar.album_artist;
    if (item->has_remote || !item->local || ar.nav_index.mapping) {
        if (songs_open_nav_filter(ar_filter(), item->name, (const char *)0) == 0 || !item->local) return RET_OK;
    }
    r = deque_at(ar.artists, item->local_index);
    if (ar.cls == CLASS_GENRES)
        songs_open_genre(ar_name(r), *(int *)((char *)r + REC_ID) == -1);
    else if (albums_open_artist(ar.artists, item->local_index, ar.cls) == -1)
        coverflow_artist(ar.artists, item->local_index, ar.cls);
    return RET_OK;
}

/* The display order: all rows but the "Unknown Artist" row (id -1) are sorted as the album Artist order sorts names (cc_name_keys / cc_key_cmp: digit runs by
 * value, ASCII case aside, a leading "The " and white space dropped, a CJK name placed by its pinyin initials among the Latin ones; ties keep the stock order).
 * The Unknown rows keep their stock positions (stock puts them last) and the sorted rows fill the other positions in order, so "The Beatles" reaches B wherever
 * a fixed row sits. The stock rows are never reordered: order[] is the stock row number at each position; NULL (stock order) when there is no memory. */
static int ar_fixed(unsigned index) { return ar.item[index].fixed != 0; }

static const char **ar_key __attribute__((section(".scratch")));

static const char *ar_text(const void *ctx, unsigned i) {
    const ar_item_t *items = (const ar_item_t *)ctx;
    return items && items[i].name ? items[i].name : "";
}

static int ar_cmp(unsigned a, unsigned b) {
    const char *x = ar_key ? ar_key[a] : ar.item[a].name;
    const char *y = ar_key ? ar_key[b] : ar.item[b].name;
    int d = cc_key_cmp(x ? x : "", y ? y : "");
    return d ? d : a < b ? -1 : a > b;
}

static void ar_sort(void) {
    unsigned i, n = 0, *v;
    ar.order = (unsigned *)0;
    ar_key = (const char **)0;
    if (ar.count < 2 || !ar.item) return;
    /* Genre and Composer queries already have their own stock order. Keep that order (and the
     * appended Navidrome-only values) unless the user explicitly selects Z-A. Artists use the
     * existing name sort on both directions. */
    if (ar.cls != CLASS_ARTISTS && !ar.rev) return;
    ar.order = (unsigned *)calloc(ar.count, sizeof *ar.order);
    if (ar.cls == CLASS_ARTISTS) ar_key = cc_name_keys(ar.count, ar_text, ar.item);
    if (!ar.order || (ar.cls == CLASS_ARTISTS && !ar_key)) {
        free(ar.order), free((void *)ar_key);
        ar.order = (unsigned *)0, ar_key = (const char **)0;
        return;
    }
    v = ar.order;
    for (i = 0; i < ar.count; ++i)
        if (!ar_fixed(i)) v[n++] = i;
    if (ar.cls == CLASS_ARTISTS) cc_heapsort(v, n, ar_cmp);
    if (ar.rev)
        for (i = 0; i < n / 2; ++i) {
            unsigned t = v[i];
            v[i] = v[n - 1 - i], v[n - 1 - i] = t;
        }
    for (i = ar.count; i-- > 0;) v[i] = ar_fixed(i) ? i : v[--n];
    free((void *)ar_key);
    ar_key = (const char **)0;
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
        ar_item_t *item = ar_item_at(i);
        int k = az_rank_of(cc_name_initial(ar_item_name(i)));
        if (ar.rev) k = k ? 26 - k : 26;
        ar.rank[i] = item && item->fixed && i ? (unsigned char)prev : (unsigned char)k;
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
static grid_tile_t *ar_tile(int a) {
    int lo, hi, fresh;
    grid_tile_t *t;
    az_span(&ar.al, &lo, &hi);
    t = grid_tile(&ar.g, a, lo, hi, &fresh);
    if (fresh) grid_set(t, ar_item_name((unsigned)a), "", 0);
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
    if (!canvas || !ar.view || !ar.g.tiles || !ar.count || !ar.item) return RET_OK;
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

static int ar_on_scroll(void *ctx, void *e);

static int ar_on_rail(void *ctx, void *e) {
    (void)ctx;
    if (ar.view) {
        az_rail_event(&ar.al, e);
        /* AWTK builds that do not emit EVT_SCROLL for a direct yoffset set
         * still need to update the pinned title and repaint the new rows. */
        ar_on_scroll((void *)0, (void *)0);
        ar_redraw();
    }
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
    if (ar.nav_timer) timer_remove(ar.nav_timer);
    ar.nav_timer = 0;
    return ar_on_abort(ctx, e);
}

static int ar_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ar_nav_schedule();
    return RET_OK;
}

static unsigned ar_name_hash(const char *name) {
    unsigned h = 2166136261u, i;
    if (!name) name = "";
    for (i = 0; name[i]; ++i) {
        unsigned c = (unsigned char)name[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        h = (h ^ c) * 16777619u;
    }
    return h ? h : 1u;
}

static const char *ar_server_name(const sb_song_t *song) {
    if (ar.cls == CLASS_GENRES) return song->genre;
    if (ar.cls == CLASS_COMPOSERS) return song->composer;
    return ar.album_artist ? song->album_artist : song->artist;
}

static void ar_layout(void) {
    int h;
    ar.al.count = (int)ar.count;
    ar.al.content =
        ar_content(); /* section headers are added after the async server scan; keep rail clamping in sync */
    h = ar.count ? ar.al.content : GRID_VIEW_H;
    widget_resize(ar.view, AR_W, h);
    widget_set_prop_int(ar.sv, "virtual_h", h);
    ar_show(ar.list, ar.count != 0);
    ar_show(ar.status, ar.count == 0);
    if (!ar.count) widget_set_tr_text(ar.status, ar.nav_scanning ? SB_LIBRARY_LOADING_HINT : SB_LIBRARY_EMPTY_HINT);
    az_rail_fit(&ar.al, GRID_VIEW_H);
    ar_title_update();
    ar_redraw();
}

static void ar_nav_finish(void) {
    unsigned i;
    if (ar.nav_timer) timer_remove(ar.nav_timer);
    ar.nav_timer = 0;
    ar.nav_scanning = 0;
    for (i = 0; i < ar.local_count; ++i) {
        void *record = deque_at(ar.artists, i);
        ar_item_t *item;
        if (*(int *)((char *)record + REC_ID) != -1) continue;
        item = &ar.item[ar.count++];
        item->name = ar_name(record), item->local_index = i, item->local = 1, item->fixed = 1;
    }
    ar.al.count = (int)ar.count;
    free(ar.nav_slots);
    ar.nav_slots = (ar_name_slot_t *)0, ar.nav_slot_cap = 0;
    if (ar.count) ar_sort();
    free(ar.rank);
    ar.rank = (unsigned char *)0;
    if (ar.count) ar_sections();
    ar_layout();
}

#define AR_NAV_BATCH 256
#define AR_NAV_MS 16

static int ar_nav_step(const void *unused) {
    unsigned end;
    (void)unused;
    ar.nav_timer = 0;
    if (!ar.nav_scanning || !ar.view) return RET_OK;
    end = ar.nav_cursor + AR_NAV_BATCH;
    if (end < ar.nav_cursor || end > ar.nav_total) end = ar.nav_total;
    while (ar.nav_cursor < end) {
        const sb_song_t *song = &ar.nav_index.songs[ar.nav_cursor++];
        const char *name;
        unsigned hash, at;
        int found_local = 0, found_remote = 0;
        if (sb_library_is_dsd(song)) continue;
        name = ar_server_name(song);
        if (!name || !*name) continue;
        hash = ar_name_hash(name), at = hash & (ar.nav_slot_cap - 1);
        while (ar.nav_slots[at].hash) {
            ar_item_t *item = &ar.item[ar.nav_slots[at].local_index];
            if (ar.nav_slots[at].hash == hash && !cc_nocase(item->name, name)) {
                if (item->local)
                    item->has_remote = 1, found_local = 1;
                else
                    found_remote = 1;
            }
            at = (at + 1) & (ar.nav_slot_cap - 1);
        }
        if (!found_local && !found_remote && ar.count < ar.item_count) {
            ar_item_t *item = &ar.item[ar.count];
            item->name = name;
            ar.nav_slots[at].hash = hash, ar.nav_slots[at].local_index = ar.count;
            ++ar.count;
        }
    }
    if (ar.nav_cursor >= ar.nav_total) {
        ar_nav_finish();
        return RET_OK;
    }
    ar_layout();
    ar_nav_schedule();
    return RET_OK;
}

static void ar_nav_schedule(void) {
    if (ar.nav_scanning && !ar.nav_timer && ar.view) {
        ar.nav_timer = timer_add(ar_nav_step, (void *)0, AR_NAV_MS);
        if (!ar.nav_timer) ar_nav_finish(); /* retain local rows if the UI cannot schedule background work */
    }
}

static int ar_nav_start(unsigned local_count) {
    unsigned total, capacity, cap = 1, target, i;
    if (local_count > MAX_ARTISTS) local_count = MAX_ARTISTS;
    ar.local_count = local_count;
    if (sb_library_index_open(&ar.nav_index)) {
        ar_local_items(local_count);
        return 0;
    }
    total = ar.nav_index.count + ar.nav_index.dsd_count;
    if (total > 100000u || local_count > (unsigned)-1 - total) {
        sb_library_index_close(&ar.nav_index);
        ar_local_items(local_count);
        return 0;
    }
    capacity = local_count + total;
    ar.item = capacity ? (ar_item_t *)calloc(capacity, sizeof *ar.item) : (ar_item_t *)0;
    target = capacity * 2u;
    while (cap < target && cap < 0x80000000u) cap <<= 1;
    if ((capacity && !ar.item) ||
        (target && (cap < target || !(ar.nav_slots = (ar_name_slot_t *)calloc(cap, sizeof *ar.nav_slots))))) {
        free(ar.item), ar.item = (ar_item_t *)0;
        free(ar.nav_slots), ar.nav_slots = (ar_name_slot_t *)0;
        sb_library_index_close(&ar.nav_index);
        ar_local_items(local_count);
        return 0;
    }
    ar.item_count = capacity;
    ar.nav_slot_cap = target ? cap : 0;
    for (i = 0; i < local_count; ++i) {
        void *record = deque_at(ar.artists, i);
        ar_item_t *item;
        unsigned hash, at;
        if (*(int *)((char *)record + REC_ID) == -1) continue;
        item = &ar.item[ar.count];
        item->name = ar_name(record), item->local_index = i, item->local = 1;
        hash = ar_name_hash(item->name), at = hash & (ar.nav_slot_cap - 1);
        while (ar.nav_slots[at].hash) at = (at + 1) & (ar.nav_slot_cap - 1);
        ar.nav_slots[at].hash = hash, ar.nav_slots[at].local_index = ar.count;
        ++ar.count;
    }
    if (!total) {
        ar_nav_finish();
        return 0;
    }
    ar.item_count = capacity;
    ar.nav_total = total, ar.nav_cursor = 0, ar.nav_scanning = 1;
    return 1;
}

static void ar_local_items(unsigned local_count) {
    unsigned i;
    if (local_count > MAX_ARTISTS) local_count = MAX_ARTISTS;
    free(ar.item);
    ar.item = local_count ? (ar_item_t *)calloc(local_count, sizeof *ar.item) : (ar_item_t *)0;
    ar.count = 0, ar.item_count = local_count;
    if (local_count && !ar.item) return;
    for (i = 0; i < local_count; ++i) {
        void *record = deque_at(ar.artists, i);
        ar_item_t *item = &ar.item[ar.count++];
        item->name = ar_name(record), item->local_index = i, item->local = 1;
        item->fixed = *(int *)((char *)record + REC_ID) == -1;
    }
}

static int ar_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ar.nav_timer) timer_remove(ar.nav_timer);
    if (ar.artists) deque_destroy(ar.artists);
    grid_free(&ar.g);
    az_free(&ar.al);
    if (ar.chev) bitmap_destroy(ar.chev);
    free(ar.order);
    free(ar.rank);
    free(ar.item);
    free(ar.nav_slots);
    sb_library_index_close(&ar.nav_index);
    memset(&ar, 0, sizeof ar);
    return RET_OK;
}

/* (Re)build the list from the stock query, with artist_type as it is: a copy of the stock rows, so Cover
 * Flow's own queries cannot pull it away. */
static void ar_load(void) {
    void *list;
    unsigned local_count;
    int scanning, h;
    if (ar.nav_timer) timer_remove(ar.nav_timer);
    ar.nav_timer = 0, ar.nav_scanning = 0;
    ar.album_artist = ar.cls == CLASS_ARTISTS && *(volatile int *)ARTIST_TYPE == 1;
    if (ar.artists) deque_destroy(ar.artists);
    ar.artists = (void *)0;
    free(ar.order);
    free(ar.rank);
    free(ar.item);
    free(ar.nav_slots);
    sb_library_index_close(&ar.nav_index);
    ar.order = (unsigned *)0, ar.rank = (unsigned char *)0;
    ar.item = (ar_item_t *)0;
    ar.nav_slots = (ar_name_slot_t *)0, ar.nav_slot_cap = 0;
    ar.count = ar.item_count = ar.local_count = ar.nav_cursor = ar.nav_total = 0, ar.press = ar.down = 0;
    ar.al.count = 0, ar.al.nsec = 0;
    grid_drop(&ar.g);
    widget_set_prop_int(ar.sv, "yoffset", 0);
    list = loadLocalClassList(ar.cls) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    if (list && deque_size(list) && (ar.artists = _create_deque("stSongInfo"))) {
        deque_init(ar.artists);
        deque_assign(ar.artists, list);
    }
    local_count = ar.artists ? deque_size(ar.artists) : 0;
    scanning = ar_nav_start(local_count);
    ar.al.count = (int)ar.count;
    if (!scanning && !ar.nav_index.mapping) {
        if (ar.count) ar_sort();
        free(ar.rank), ar.rank = (unsigned char *)0;
        if (ar.count) ar_sections();
    }
    ar.nav_scanning = scanning;
    ar.al.count = (int)ar.count;
    ar.al.content = ar_content();
    h = ar.count ? ar.al.content : GRID_VIEW_H;
    widget_resize(ar.view, AR_W, h);
    widget_set_prop_int(ar.sv, "virtual_h", h);
    ar_show(ar.list, ar.count != 0);
    ar_show(ar.status, ar.count == 0);
    if (!ar.count) widget_set_tr_text(ar.status, scanning ? SB_LIBRARY_LOADING_HINT : SB_LIBRARY_EMPTY_HINT);
    az_rail_fit(&ar.al, GRID_VIEW_H);
    ar_title_update();
    ar_redraw();
    ar_nav_schedule();
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
    if (ar.status) label_set_line_wrap(ar.status, 1), widget_set_prop_bool(ar.status, "word_wrap", 1);
    ar.title = widget_lookup(ar.win, "label_title", 1);
    ar.big = widget_lookup(ar.win, "ar_title", 1);
    ar.fade = widget_lookup(ar.win, "img_nb_fade", 1);
    ar.st_title = widget_lookup(ar.win, "label_row_title", 1);
    ar.al.win = ar.win, ar.al.sv = ar.sv, ar.al.top = AR_TOP, ar.al.row = AR_ROW;
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
    if (!grid_init(&ar.g, ar.win, AR_TILES, 0, 0)) {
        int h = ar.home;
        grid_free(&ar.g);
        navigator_back();
        return h ? pod_home_open(h) : -1;
    }
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
