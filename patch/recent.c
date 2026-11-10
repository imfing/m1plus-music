/* M1+ Music Recently Played: the albums played last, recorded by the payload, and a shelf of their covers at the foot of the Home instance
 * of the menu (docs/modules/recent.md): the Albums grid's cells (patch/grid.c) for the six albums the file keeps, 2 x 1..3.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * No stock function is hooked. The shelf is a widget of the menu's own asset (ui/m1plus_menu.bin, tools/pod_ui.py shelf(): pod_shelf, a
 * view that follows the last shown row (Settings) in the list's scroll view, hidden and insensitive; at its top the section header pod_sh_head, a stock
 * hscroll_label with the translation of "Recently Played" (the stock paint draws it, language included; it is insensitive, so a touch
 * on it falls to the shelf, which has no tile there), and two hidden labels that carry the two text styles of the tiles);
 * patch/home.c calls recent_start for the Home instance only (the menu opened from the grid icon never gets a shelf). Everything here
 * runs from the shelf's and the menu window's events and one page-scoped timer.
 *
 * Recording. recent_note(track) is called by the places that already see the playing track on a timer: the mini player bar's tick
 * (patch/minibar.c, the Home menu in front) and Now Playing's tick (patch/nowplaying.c). The album's IDENTITY is its title, ASCII case
 * folded (rc_id: the stock list groups albums by title alone), compared with the most recent one held in RAM first: nothing is read or
 * written while it is the same. An empty album tag is not recorded. A new album goes to the front of RECENT_FILE, an album already in
 * it moves there, at most RC_MAX are kept, and the file (on the card, pod_card_write) is written only then, from a fresh read of it (a card swap never carries a list over). The file (tools/pod_recent.py is the
 * model the tests compare with), strictly validated when read (anything else is an empty list):
 *     M1R2\n
 *     <id 8 hex>\t<cover key 8 hex>\t<0|1>\t<album>\t<artist>\t<path>\n      (one line per album, the most recent first)
 * The cover key is the Cover Flow cache key of the album ROW (rc_resolve loads the stock album list: only from the menu's to-foreground at
 * least RC_RESOLVE_MS after the menu opened, one entry each); until then the playing track's.
 *
 * The shelf. recent_start looks the widgets up, registers EVT_DESTROY / EVT_WINDOW_TO_BG / EVT_WINDOW_TO_FG on the window and the
 * shelf's EVT_AFTER_PAINT, pointer events and the list's EVT_SCROLL, arms a one-shot RC_FIRST_MS later and, when the list holds an
 * album and the Settings > Home Screen switch (SHELF_FILE) is on, sizes the shelf (ceil(albums / 2) rows of covers) and shows it (menu_shelf in patch/menu.c: visible and sensitive together, virtual_h grows). Any widget missing, any registration
 * or the timer failing: nothing is shown or moved, the menu is as it was. The menu's first paint decodes nothing.
 *   cells    the Albums grid's (patch/grid.c, the GRID_* geometry): cell i shows entry i, GRID_COVER px covers with GRID_R px rounded corners in
 *            the bitmap's own alpha (the Albums page's are square), the album and artist cut with an ellipsis once, a shared placeholder disc.
 *   decode   ONE cover per RC_TICK_MS tick on the page's timer, only once the shelf is in view or within one row of the viewport's bottom
 *            (rc_near: the shelf is at the foot of the list; the list's EVT_SCROLL and the to-foreground re-check it); paint never decodes.
 *   refresh  EVT_WINDOW_TO_FG reads the file and the switch again and redoes only the tiles whose album changed (a tile that moved to another
 *            cell keeps its cover); the mini bar's tick calls recent_refresh when it recorded a new album under a menu in front.
 *   touch    a cell is its cover and its two lines (grid_cell_at); a press that begins on one and is released closer than RC_TAP_PX to it on
 *            both axes, on the same cell, opens that album; the scroll view takes every drag and the shelf never consumes an event. A press that
 *            stopped a coasting list never reaches the shelf (patch/scroll.c).
 *   open     on a tap only: the stock album list is loaded and copied (cc_albums), the row found by the cover key, else the title, else the
 *            recorded track path, and opened through the Albums grid's sequence (cc_open_album). Not found: nothing happens.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "podcasts.h"

#if SH_TILES != GRID_COLS * SH_ROWS || SH_TILES != RC_MAX
#error the shelf shows every album the file keeps: SH_TILES = GRID_COLS * SH_ROWS = RC_MAX
#endif

#define RC_MAGIC "M1R2\n"
#define RC_MAGIC_LEN 5

typedef struct {
    unsigned
        key; /* the album's identity (rc_id: its title, ASCII case folded, as getAllAlbum groups albums), never 0 */
    unsigned
        ckey; /* the Cover Flow cache key of its cover (cc_album_key): the album row's once res, else the playing track's */
    int res; /* ckey (and the artist) come from the stock album row */
    char album[RC_STR], artist[RC_STR], path[RC_PATH];
} ent_t;

static struct {
    ent_t ent[RC_MAX];
    unsigned n; /* albums held, most recent first */
    int loaded; /* ent holds the file's content (the first note reads it) */
    void *win, *shelf, *sv, *st_title, *st_sub;
    unsigned timer; /* the one-shot or the decode tick, 0 none */
    int fg; /* the window is in front */
    int warm; /* the one-shot after start has run */
    int on; /* Settings > Home Screen > Recent Albums */
    int shown; /* the shelf is up */
    int noscroll; /* the scroll event could not be registered: the covers are made as soon as the shelf is shown */
    unsigned t0; /* time_now_ms at start: the album list is not loaded for covers before RC_RESOLVE_MS after it */
    unsigned tried[RC_MAX],
        tried_n; /* identities the album list had no row for (not asked again while the page lives) */
    int down; /* the tile a press began on, + 1; 0 none */
    int down_x, down_y; /* where it began (screen coordinates) */
    grid_t g; /* the tiles (SH_TILES, cell i shows entry i), the placeholder, the rounded corners: patch/grid.c */
    unsigned id[SH_TILES]; /* the identity of the album each tile was made for */
} rc __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * The file
 */
static int rc_bad(unsigned char c) { return c < 0x20 || c == 0x7f; }

static int rc_hex(unsigned c) {
    if (c - '0' < 10) return (int)(c - '0');
    if (c - 'a' < 6) return (int)(c - 'a' + 10);
    return -1;
}

/* 8 lowercase hex digits at p as a number; 0 when one is not (the caller refuses a zero key anyway). */
static unsigned rc_hex8(const char *p) {
    unsigned v = 0, k;
    int d;
    for (k = 0; k < 8; ++k) {
        d = rc_hex((unsigned char)p[k]);
        if (d < 0) return 0;
        v = v << 4 | (unsigned)d;
    }
    return v;
}

/* The field at *pp up to the byte `end` (a tab or a newline), at most max - 1 bytes, no control byte: copied to out, *pp after the end
 * byte; the length, or -1 when it is malformed. */
static int rc_field(const char **pp, const char *stop, char end, char *out, unsigned max) {
    const char *p = *pp;
    unsigned n = 0;
    while (p < stop && *p != end) {
        if (rc_bad((unsigned char)*p) || n + 1 >= max) return -1;
        out[n++] = *p++;
    }
    if (p >= stop) return -1; /* no end byte: the file stops inside the line */
    out[n] = 0;
    *pp = p + 1;
    return (int)n;
}

/* RECENT_FILE into rc.ent; anything malformed reads as an empty list. */
static void rc_load(void) {
    char buf[RC_FILE_MAX + 1];
    const char *p = buf, *stop;
    int fd, n, ok = 1;
    unsigned i, j, key, ckey;
    rc.n = 0;
    rc.loaded = 1;
    if (!pod_card_mounted()) return; /* the list belongs to the card: no card, no list */
    fd = open(RECENT_FILE, O_RDONLY, 0);
    if (fd < 0) return;
    n = read(fd, buf, sizeof buf);
    close(fd);
    if (n < RC_MAGIC_LEN || n > RC_FILE_MAX) return;
    stop = buf + n;
    for (i = 0; i < RC_MAGIC_LEN; ++i)
        if (buf[i] != RC_MAGIC[i]) return;
    p += RC_MAGIC_LEN;
    while (ok && p < stop) {
        ent_t *e = &rc.ent[rc.n];
        if (rc.n >= RC_MAX || stop - p < 21) {
            ok = 0;
            break;
        }
        key = rc_hex8(p); /* identity, tab, cover key, tab, 0 or 1, tab */
        ckey = rc_hex8(p + 9);
        if (!key || !ckey || p[8] != '\t' || p[17] != '\t' || (p[18] != '0' && p[18] != '1') || p[19] != '\t') {
            ok = 0;
            break;
        }
        for (j = 0; j < rc.n; ++j)
            if (rc.ent[j].key == key) ok = 0;
        e->res = p[18] == '1';
        p += 20;
        e->key = key;
        e->ckey = ckey;
        ok = ok && rc_field(&p, stop, '\t', e->album, RC_STR) > 0 && rc_field(&p, stop, '\t', e->artist, RC_STR) >= 0 &&
             rc_field(&p, stop, '\n', e->path, RC_PATH) >= 0;
        if (ok) ++rc.n;
    }
    if (!ok) rc.n = 0;
}

static void rc_put(char **o, const char *end, const char *s) {
    while (*s && *o < end) *(*o)++ = *s++;
}

static void rc_puthex(char **o, const char *end, unsigned v) {
    char hex[9];
    unsigned k;
    for (k = 0; k < 8; ++k) hex[k] = "0123456789abcdef"[v >> (28 - 4 * k) & 15];
    hex[8] = 0;
    rc_put(o, end, hex);
}

/* The list as the file holds it, on the card (pod_card_write); 0 when it was written. */
static int rc_save(void) {
    char buf[RC_FILE_MAX + 1], *o = buf;
    const char *end = buf + RC_FILE_MAX;
    unsigned i;
    rc_put(&o, end, RC_MAGIC);
    for (i = 0; i < rc.n; ++i) {
        rc_puthex(&o, end, rc.ent[i].key);
        rc_put(&o, end, "\t");
        rc_puthex(&o, end, rc.ent[i].ckey);
        rc_put(&o, end, rc.ent[i].res ? "\t1\t" : "\t0\t");
        rc_put(&o, end, rc.ent[i].album);
        rc_put(&o, end, "\t");
        rc_put(&o, end, rc.ent[i].artist);
        rc_put(&o, end, "\t");
        rc_put(&o, end, rc.ent[i].path);
        rc_put(&o, end, "\n");
    }
    *o = 0;
    return pod_card_write(CARD_DIR, RECENT_FILE, RECENT_TMP, buf, (unsigned)(o - buf), (const void *)0, 0);
}

/* s into out (size bytes with the NUL), control bytes as spaces, cut before a UTF-8 continuation byte that would be split. */
static void rc_copy(char *out, unsigned size, const char *s) {
    unsigned n = 0, j;
    while (s[n]) ++n;
    if (n >= size) {
        n = size - 1;
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    }
    for (j = 0; j < n; ++j) out[j] = rc_bad((unsigned char)s[j]) ? ' ' : s[j];
    out[n] = 0;
}

/* The album's identity: FNV-1a of its title with ASCII letters folded to lower case, never 0. The stock album list (getAllAlbum @0x4ea3c4:
 * "select id,album,songer,fileurl from %s group by album COLLATE NOCASE") groups albums by title alone, NOCASE, whatever the artists of
 * the tracks are, so this is the same album exactly when the stock list has one row for both: a compilation's every track is one album. */
static unsigned rc_id(const char *album) {
    unsigned h = FNV_SEED;
    for (; *album; ++album)
        h = (h ^ (unsigned char)((unsigned char)*album - 'A' < 26u ? *album + 32 : *album)) * 16777619u;
    return h | !h;
}

/* 1 for a stream address (a Subsonic server track's queue path). */
static int rc_is_stream(const char *p) {
    static const char *const pre[] = {"http://", "https://", "nd://"};
    unsigned k, j;
    for (k = 0; k < 3; ++k) {
        for (j = 0; pre[k][j] && p[j] == pre[k][j]; ++j) {
        }
        if (!pre[k][j]) return 1;
    }
    return 0;
}

/* The track the player is on: its album to the front of the list. 1 when the list changed (and was written). */
int recent_note(void *t) {
    const char *album;
    unsigned key, i, at;
    ent_t e;
    pc_note(
        t); /* Podcasts: the place, the played mark, the speed (patch/pcmodel.c); every page that sees the playing track on a timer calls this */
    if (!t) return 0;
    if (pc_is_path(cc_str(t, REC_PATH))) return 0; /* an episode is not an album of the shelf */
    if (rc_is_stream(cc_str(t, REC_PATH)))
        return 0; /* a server track's path is its stream address (a credential, dead on the shelf): never written to the card */
    album = cc_str(t, REC_ALBUM);
    if (!*album) return 0; /* an untagged album is not recorded */
    key = rc_id(album);
    if (rc.loaded && rc.n && rc.ent[0].key == key) return 0; /* the common case: nothing changed, nothing read */
    if (!pod_card_mounted()) return 0; /* the list lives on the card: no card, nothing recorded */
    rc_load(); /* a change is rare: start from what the card in the slot holds now, never from a list kept from another card */
    if (rc.n && rc.ent[0].key == key) return 0;
    for (at = 0; at < rc.n && rc.ent[at].key != key; ++at) {
    }
    if (at <
        rc.n) { /* an album already in the list moves to the front as it is (a resolved cover key and artist stay) */
        memcpy(&e, &rc.ent[at], sizeof e);
    } else {
        e.key = key;
        e.ckey = cc_album_key(t); /* the track's own key until the stock album row says better (rc_resolve) */
        e.res = 0;
        rc_copy(e.album, sizeof e.album, album);
        rc_copy(e.artist, sizeof e.artist, cc_str(t, REC_ARTIST));
        rc_copy(e.path, sizeof e.path, cc_str(t, REC_PATH));
    }
    if (at == rc.n) { /* a new album: the oldest one goes when the list is full */
        if (rc.n < RC_MAX) ++rc.n;
        at = rc.n - 1;
    }
    for (i = at; i > 0; --i)
        memcpy(&rc.ent[i], &rc.ent[i - 1],
               sizeof e); /* (an explicit call: the payload links no compiler-made memcpy) */
    memcpy(&rc.ent[0], &e, sizeof e);
    rc_save(); /* a failed write loses nothing but this entry: the list in RAM is current until the next read */
    return 1;
}

/* ---------------------------------------------------------------------------
 * The setting (Settings > Home Screen > Recent Albums): the file holds "0" for off, anything else or no file is on.
 */
int recent_setting(void) { return set_read(SHELF_FILE, '1') != '0'; }

int recent_toggle(void) {
    int next = !recent_setting();
    return home_write_atomic(SHELF_FILE, SHELF_TMP, next ? "1\n" : "0\n") == 0 ? next : -1;
}

/* ---------------------------------------------------------------------------
 * Tiles (the grid's, patch/grid.c: cell i shows entry i)
 */
static const ent_t *rc_ent(unsigned key) {
    unsigned i;
    for (i = 0; key && i < rc.n; ++i)
        if (rc.ent[i].key == key) return &rc.ent[i];
    return (const ent_t *)0;
}

static int rc_cells(void) { return rc.n < SH_TILES ? (int)rc.n : SH_TILES; }

/* The tiles for the first SH_TILES albums of the list. A tile whose album (and cover key) moved to another place keeps its cover; the
 * others are made again (grid_set: texts and key; a tick makes the cover); a tile whose cover was only the placeholder tries again when its
 * cache file exists now. */
static void rc_tiles(void) {
    grid_tile_t old[SH_TILES];
    unsigned oid[SH_TILES], i, j, used = 0;
    char url[80];
    if (!rc.g.tiles) return;
    memcpy(old, rc.g.tiles, sizeof old);
    memcpy(oid, rc.id, sizeof oid);
    memset(rc.g.tiles, 0, sizeof old);
    memset(rc.id, 0, sizeof rc.id);
    for (i = 0; i < SH_TILES && i < rc.n; ++i) {
        const ent_t *e = &rc.ent[i];
        for (j = 0; j < SH_TILES; ++j)
            if (!(used >> j & 1) && oid[j] == e->key && old[j].ckey == e->ckey) {
                used |= 1u << j;
                memcpy(&rc.g.tiles[i], &old[j], sizeof old[j]);
                if (old[j].art == 2 && cc_url(url, e->ckey)) rc.g.tiles[i].art = 0; /* the cover exists now */
                break;
            }
        if (j == SH_TILES) grid_set(&rc.g.tiles[i], e->album, e->artist, e->ckey);
        rc.g.tiles[i].album = (int)i + 1;
        rc.id[i] = e->key;
    }
    for (j = 0; j < SH_TILES; ++j)
        if (!(used >> j & 1)) grid_free_art(&old[j]); /* the bitmaps of the tiles that were not kept */
}

/* The cover of tile i (patch/grid.c: the album's cache file box-reduced to the cell's size, else the placeholder disc). */
static void rc_make(unsigned i) {
    grid_art(&rc.g, &rc.g.tiles[i]);
    if (rc.g.tiles[i].art == 2 && !rc.g.placeholder)
        grid_placeholder(
            &rc.g); /* the disc is made when a tile needs it (one bitmap shared by the tiles without a cover) */
    widget_invalidate_force(rc.shelf, (void *)0);
}

/* The shelf lies below the list, so a cell's cover is made only once the cell is in view or about to be: its top is less than one row
 * (POD_ROW_H) below the bottom of the viewport. Row by row, so the rows still far below the viewport wait (at most the rows within reach
 * are ever in memory) and the first one made is the nearest to the viewport, i.e. the top row. Without the scroll event (its registration
 * refused) the covers are made as soon as the shelf is shown. */
static int rc_near(int i) {
    if (rc.noscroll) return 1;
    return widget_get_prop_int(rc.shelf, "y", 0) + SH_TOP + i / GRID_COLS * GRID_PITCH <
           widget_get_prop_int(rc.sv, "yoffset", 0) + widget_get_prop_int(rc.sv, "h", 0) + POD_ROW_H;
}

static int rc_next(void) {
    unsigned i;
    if (!rc.shown) return -1; /* a shelf that is not shown needs no covers */
    for (i = 0; i < SH_TILES; ++i)
        if (rc.g.tiles && rc.g.tiles[i].album && !rc.g.tiles[i].art && rc_near((int)i)) return (int)i;
    return -1;
}

/* ---------------------------------------------------------------------------
 * The timer: a one-shot after start, then one tile per tick until none is left
 */
static void rc_unarm(void) {
    if (rc.timer) timer_remove(rc.timer);
    rc.timer = 0;
}

/* The one thing the timer does: the next waiting tile's cover. 1 while another waits. */
static int rc_work(void) {
    int i = rc_next();
    if (i >= 0) rc_make((unsigned)i);
    return rc_next() >= 0;
}

static int rc_dark(const void *timer);

static int rc_tick(const void *timer) {
    (void)timer;
    if (!rc.win || !rc.fg) {
        rc.timer = 0;
        return RET_OK;
    }
    if (!pod_screen_lit()) {
        rc.timer = timer_add(rc_dark, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    if (!rc_work()) {
        rc.timer = 0;
        return RET_OK;
    } /* nothing left: the timer ends with the return */
    return RET_REPEAT;
}

static int rc_dark(const void *timer) {
    (void)timer;
    rc.timer = 0;
    if (!rc.win || !rc.fg) return RET_OK;
    if (!pod_screen_lit()) {
        rc.timer = timer_add(rc_dark, (void *)0, POD_DARK_MS);
    } else if (rc_next() >= 0) {
        rc.timer = timer_add(rc_tick, (void *)0, RC_TICK_MS);
        if (rc.timer && !rc_work()) rc_unarm();
    }
    return RET_OK;
}

static int rc_first(const void *timer) {
    (void)timer;
    rc.timer = 0; /* this one ends with the return */
    if (!rc.win || !rc.fg) return RET_OK;
    rc.warm = 1;
    if (rc_next() < 0) return RET_OK;
    if (!pod_screen_lit())
        rc.timer = timer_add(rc_dark, (void *)0, POD_DARK_MS);
    else {
        rc.timer = timer_add(rc_tick, (void *)0, RC_TICK_MS);
        if (rc.timer && !rc_work()) rc_unarm();
    }
    return RET_OK;
}

/* Arms the timer when a tile waits for its cover and none runs: the one-shot before the first work (nothing is decoded while the menu
 * paints for the first time), then the tick itself. */
static void rc_kick(void) {
    if (rc.timer || !rc.win || !rc.fg || rc_next() < 0) return;
    rc.timer = rc.warm ? timer_add(rc_tick, (void *)0, RC_TICK_MS) : timer_add(rc_first, (void *)0, RC_FIRST_MS);
}

/* The list scrolled (EVT_SCROLL of the scroll view, every offset change): the shelf may have come within a row of the viewport. */
static int rc_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rc.win) rc_kick();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The shelf as the list and the switch say
 */
static void rc_apply(void) {
    int want = rc.on && rc.n > 0;
    rc_tiles();
    if (want)
        widget_resize(rc.shelf, SH_W,
                      SH_H((rc_cells() + GRID_COLS - 1) /
                           GRID_COLS)); /* ceil(albums / 2) rows of covers: set before the rows are arranged */
    if (want || want != rc.shown) menu_shelf(rc.win, want);
    rc.shown = want;
    if (want) {
        widget_invalidate_force(rc.shelf, (void *)0);
        rc_kick();
    }
}

void recent_refresh(void) {
    if (rc.win && rc.fg) rc_apply();
}

/* ---------------------------------------------------------------------------
 * Paint: the resident covers and the texts (the grid's cell paint). Nothing is decoded here.
 */
static grid_tile_t *rc_tile_of(void *ctx, int a) {
    (void)ctx;
    return &rc.g.tiles[a];
}

/* The shelf's own EVT_AFTER_PAINT, in the shelf's coordinates, after the stock paint drew the header. The scroll view clips its children
 * to its own rectangle (scroll_view_on_paint_children sets the canvas clip, canvas_set_clip_rect @0x610ec4), so a cover or a line that
 * lies below the list's bottom edge, or behind the mini bar's pill (a later sibling, painted over it), is cut exactly as a row is. */
static int rc_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (!canvas || !rc.win || !rc.shown || !rc.g.tiles) return RET_OK;
    grid_paint(canvas, &rc.g, 0, rc_cells(), SH_TOP, 0, rc_tile_of, (void *)0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch
 */
static int rc_pe(void *e, int field) { return *(int *)((char *)e + field); }

/* The tile under the shelf point (x, y), or -1: the cover and the two lines under it; the margins, the gaps between tiles and the air
 * above and below are dead, and so is a place with no album. */
static int rc_tile_at(int x, int y) { return grid_cell_at(x, y, SH_TOP, rc_cells()); }

static int rc_local(void *e) {
    int pt[2];
    pt[0] = rc_pe(e, PE_X), pt[1] = rc_pe(e, PE_Y);
    widget_to_local(rc.shelf,
                    pt); /* screen to shelf: the window sits under the 30 px status bar, the list may be scrolled */
    return rc_tile_at(pt[0], pt[1]);
}

/* The stock row of the album: by the key, else the title (ASCII case aside; the "Unknown Album" row never), else the recorded track
 * path. -1 when the library has none. */
static int rc_find(void *albums, const ent_t *e, int by_key) {
    unsigned n = deque_size(albums), i;
    for (i = 0; by_key && i < n; ++i)
        if (cc_album_key(deque_at(albums, i)) == e->ckey) return (int)i;
    for (i = 0; i < n; ++i) {
        void *r = deque_at(albums, i);
        if (*(int *)((char *)r + REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), e->album)) return (int)i;
    }
    for (i = 0; *e->path && i < n; ++i)
        if (!strcmp(cc_str(deque_at(albums, i), REC_PATH), e->path)) return (int)i;
    return -1;
}

/* Opens tile i's album the way the Albums grid does. Only here is the stock album list loaded. */
static void rc_open(int i) {
    const ent_t *e = rc_ent(rc.id[i]);
    void *albums;
    int row;
    if (!e) return;
    albums = cc_albums();
    if (!albums) return;
    row = rc_find(albums, e, 1);
    deque_destroy(albums);
    if (row >= 0) cc_open_album((void *)0, 0, row);
}

/* The cover key from the stock album row: the Cover Flow cache files are named by the album ROW's key (the artist of the album's first
 * track), which a track of a compilation or with a featured artist does not give. Loads the stock album list (cc_albums: getAllAlbum, the
 * query plus a copy; it grows with the library, so it is never done at boot, in a tick or in paint) only from the menu's to-foreground,
 * one entry each, 5 s after the menu opened or later. Never with another page in front: the query leaves the album list in *pdeq_showlist
 * (and its title in nagvation_title), which a stock song list under Now Playing draws its rows from and plays.
 * An album the library does not list is not asked again while the page lives (rc.tried). The entry gets the row's key and artist and the
 * file is written once more. */
static int rc_tried(unsigned id) {
    unsigned i;
    for (i = 0; i < RC_MAX; ++i)
        if (rc.tried[i] == id) return 1;
    return 0;
}

static void rc_resolve(unsigned i) {
    ent_t *e = &rc.ent[i];
    void *albums, *row;
    int at;
    if (e->res || rc_tried(e->key)) return;
    rc.tried[rc.tried_n++ % RC_MAX] = e->key;
    albums = cc_albums();
    if (!albums) return;
    at = rc_find(albums, e, 0);
    row = at >= 0 ? deque_at(albums, (unsigned)at) : (void *)0;
    if (row) {
        e->ckey = cc_album_key(row);
        e->res = 1;
        rc_copy(e->artist, sizeof e->artist, cc_str(row, REC_ARTIST));
    }
    deque_destroy(albums);
    if (row) rc_save();
}

/* The cover keys checked against an album list someone else loaded (patch/homecover.c's scan, from the menu's to-foreground): every entry
 * gets its row's key and artist, resolved or not. A key resolved under an earlier row rule (the album's first track since V2.1qH) or the
 * playing track's key names a file the builder never makes, so the tile kept the placeholder while a tap (by title) opened the album.
 * rows gets the shelf's albums as indices into albums, most recent first (the build queues them first); returns their count. */
int recent_rekey(void *albums, unsigned *rows) {
    unsigned i, changed = 0;
    int n = 0;
    if (!albums) return 0;
    if (!rc.loaded) rc_load();
    for (i = 0; i < rc.n; ++i) {
        ent_t *e = &rc.ent[i];
        int at = rc_find(albums, e, 0);
        void *row = at >= 0 ? deque_at(albums, (unsigned)at) : (void *)0;
        if (!row) continue;
        if (rows && i < SH_TILES) rows[n++] = (unsigned)at;
        if (e->res && e->ckey == cc_album_key(row)) continue;
        e->ckey = cc_album_key(row);
        e->res = 1;
        rc_copy(e->artist, sizeof e->artist, cc_str(row, REC_ARTIST));
        changed = 1;
    }
    if (changed) {
        rc_save();
        recent_refresh();
    }
    return n;
}

static int rc_on_down(void *ctx, void *e) {
    (void)ctx;
    rc.down = 0;
    if (!e || !rc.win) return RET_OK;
    rc.down = rc_local(e) + 1;
    rc.down_x = rc_pe(e, PE_X), rc.down_y = rc_pe(e, PE_Y);
    return RET_OK;
}

static int rc_on_up(void *ctx, void *e) {
    int a = rc.down - 1, dx, dy;
    (void)ctx;
    rc.down = 0;
    if (a < 0 || !e || !rc.win || !rc.shown) return RET_OK;
    dx = rc_pe(e, PE_X) - rc.down_x;
    dy = rc_pe(e, PE_Y) - rc.down_y;
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    if (dx < RC_TAP_PX && dy < RC_TAP_PX && rc_local(e) == a) rc_open(a);
    return RET_OK;
}

static int rc_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rc.down = 0;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window's events
 */
static void rc_stop(void) {
    rc_unarm();
    grid_free(&rc.g);
    memset(&rc, 0, sizeof rc);
}

static int rc_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == rc.win) rc_stop(); /* an earlier window's end leaves the new one alone */
    return RET_OK;
}

static int rc_on_background(void *ctx, void *e) {
    (void)e;
    if (!rc.win || ctx != rc.win) return RET_OK;
    rc.fg = 0;
    rc.down = 0;
    rc_unarm();
    return RET_OK;
}

/* The menu is in front again: the list and the switch are read again, and only the tiles whose album changed are redone. */
static int rc_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!rc.win || ctx != rc.win) return RET_OK;
    rc.fg = 1;
    rc_load();
    rc.on = recent_setting();
    rc_apply();
    if (rc.on && (unsigned)time_now_ms() - rc.t0 >=
                     RC_RESOLVE_MS) { /* one unresolved album per to-foreground, never in the boot window */
        unsigned i;
        for (i = 0; i < rc.n && i < SH_TILES; ++i)
            if (!rc.ent[i].res && !rc_tried(rc.ent[i].key)) {
                rc_resolve(i);
                rc_apply();
                break;
            }
    }
    return RET_OK;
}

/* The Home instance of the menu is up (patch/home.c, after the list took the whole window). */
void recent_start(void *win) {
    if (!win) return;
    if (rc.win) rc_stop(); /* an earlier window that never said it was gone */
    rc.win = win;
    rc.shelf = widget_lookup(win, "pod_shelf", 1);
    rc.sv = widget_lookup(win, "pod_scrollview", 1);
    rc.st_title =
        widget_lookup(win, "pod_sh_title",
                      1); /* (the header pod_sh_head is the asset's own label; the payload needs nothing of it) */
    rc.st_sub = widget_lookup(win, "pod_sh_sub", 1);
    rc.fg = 1;
    if (!rc.shelf || !rc.sv || !rc.st_title || !rc.st_sub || !widget_on(win, EVT_DESTROY, rc_on_destroy, win) ||
        !widget_on(win, EVT_WINDOW_TO_BG, rc_on_background, win) ||
        !widget_on(win, EVT_WINDOW_TO_FG, rc_on_foreground, win) ||
        !widget_on(rc.shelf, EVT_AFTER_PAINT, rc_on_paint, (void *)0) ||
        !widget_on(rc.shelf, EVT_POINTER_DOWN, rc_on_down, (void *)0) ||
        !widget_on(rc.shelf, EVT_POINTER_UP, rc_on_up, (void *)0) ||
        !widget_on(rc.shelf, EVT_POINTER_ABORT, rc_on_abort, (void *)0)) {
        rc_stop(); /* a handler that was registered finds no window of ours any more */
        return;
    }
    rc.timer = timer_add(rc_first, (void *)0, RC_FIRST_MS);
    if (!rc.timer) {
        rc_stop();
        return;
    }
    rc.noscroll = !widget_on(rc.sv, EVT_SCROLL, rc_on_scroll, (void *)0);
    rc.t0 = (unsigned)time_now_ms();
    if (!grid_init(&rc.g, win, SH_TILES, GRID_COVER,
                   GRID_R)) { /* the Albums grid's cells, the covers' corners rounded (GRID_R px) */
        rc_stop();
        return;
    }
    rc.g.st_title = rc.st_title, rc.g.st_sub = rc.st_sub;
    rc_load();
    rc.on = recent_setting();
    rc_apply(); /* the shelf is up (with its texts) from the first paint; the covers come with the ticks */
}
