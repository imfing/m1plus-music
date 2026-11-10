/* M1+ Music Queue page: the play queue, our own page in place of the stock queue drawer (docs/modules/queue.md has the design and the geometry).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_queue.bin (tools/pod_ui.py build_queue_page): the stock list (list_view > scroll_view) holding ONE content view, view_queue, that is the window's whole
 * 450 px with the glass Back floating over it. The content view holds the header's widgets (the playing track's title and artist, the icon-only Shuffle and Repeat buttons,
 * the "Queue" line with its Clear button, the "No upcoming songs" line) and paints the rest itself in its EVT_AFTER_PAINT: the playing track's rounded cover and the rows (cover, title, artist, press fill,
 * hairline).
 *
 *   entry     queue_open(), called by Now Playing's queue button (a click handler bound after the stock init, patch/nowplaying.c: RET_STOP when this page opened, else the stock drawer
 *             opens as before). An empty queue, a stream (mclGetPlayType 2, 3, 0xf0, 0xf1: the stock drawer's own offline test) and a window that will not open leave
 *             the stock drawer.
 *   queue     the stock play queue, the deque at PLAY_QUEUE (stSongInfo rows start_player copied) and the play position mclGetPlayPos, exactly what the stock drawer reads
 *             (@0x47a8f0, row bind @0x47a19c). Rows are read from it while painting; the page notices a queue that was replaced (another pointer, size or first record).
 *   rows      Up Next: the tracks after the play position, in queue order (the real order, shuffled or not: Shuffle reorders the queue itself, patch/shuffle.c); the playing track is only in the header.
 *   play      a row tap: start_playqueue(queue index) (the stock drawer's row handler, @0x47a0c8), then force_refreshflag; the page stays, Now Playing below follows.
 *   modes     Shuffle (the payload's flag, pod_set_shuffle) and Repeat (stock's mode 0, 3, 1: pod_set_repeat) are independent: Shuffle toggles the flag; Repeat cycles off, all, one whatever the flag is.
 *   clear     the Clear button (btn_qclear, right of the "Queue" line, shown while songs follow): pod_clear_upnext removes the tracks after the play position, the page reads the queue again.
 *   covers    the Cover Flow cache file of the row's artist and album, else the file of the library album of that name (cc_cmap_*: a collab), one per tick on the page's timer, none while the list
 *             moves (the Songs page's loader); else the placeholder. The first miss builds the cover map (ONE getAllAlbum query, no file opened); an album's file is looked
 *             at once, when first asked for, and the answer kept (2 bits an album, 8 bytes an album kept, at most 4096 albums).
 *             A podcast episode is never looked up as an album: its show folder's picture (pc_show_cover, the Podcasts page's choice), else the placeholder.
 *             A server track (its REC_ID is in the queue map) is never looked up as an album either: its cover is the source's file, the one Now Playing draws (sba_rec_cover; asked for when it
 *             is not cached, the tile waits and the page's tick looks again), else the placeholder. A server queue is this page's: its play type is a list's, not a stream's (qp_stream).
 * No hook of its own; everything runs from the page's widgets and timers.
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
#include "podcasts.h"
#include "sbapi.h"

#define ROW LIST_ROW_H
#define QP_AHEAD 2 /* rows kept beyond the view in the scroll direction */
#define QP_MORE_MS 16

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *status;
    void *back, *btn_shuffle, *btn_repeat, *btn_clear;
    void *st_title, *st_sub; /* hidden labels whose styles are the rows' title and artist */
    void *htitle, *hartist, *empty; /* the header's labels, and the line shown when nothing follows */
    void *list; /* the stock play queue the page is of (*PLAY_QUEUE when valid) */
    void *first; /* its first record: with the size, tells a queue that was replaced */
    unsigned count; /* the queue's size */
    int base; /* the queue index of the first row (the play position + 1) */
    unsigned n; /* the rows */
    int row; /* the playing row, -1 for none */
    int mode; /* what the pills show: stock's repeat mode, plus 0x100 while the Shuffle flag is on */
    unsigned hkey; /* the cover key of the header's track */
    int press; /* the row under the finger, + 1 */
    int down, down_x, down_y; /* the row a press began on, + 1, and where */
    int dir, seen; /* the scroll direction (+1 down), and the offset it was last read at */
    int noscroll; /* the scroll events could not be registered: the loader runs from its own timer only */
    int clear_on; /* the Clear button is shown */
    int fg; /* 1 from the page's start and EVT_WINDOW_TO_FG, 0 after EVT_WINDOW_TO_BG */
    unsigned more_timer, stale_timer, tick_timer;
    unsigned tick_ms;
    cc_cmap_t
        *map; /* the library's album name -> cover key map (qp_key), built by the first miss; freed with the page */
    int map_tried; /* the map was asked for (built or not): never built twice in the page's life */
    int hpend; /* the header's server cover is on its way: the tick looks again */
    unsigned pshow; /* the show (pc_show_of) whose picture purl is, 0 for none looked at yet */
    int purl_ok; /* purl holds that show's picture */
    char purl[408]; /* "file://" and the picture's path */
    grid_t hg; /* the header's cover: one tile, QP_COVER px with QP_COVER_R px corners cut in the alpha */
    grid_t g; /* the rows' covers and texts: the ring */
} qp __attribute__((section(".scratch")));

static int qp_on_stale(const void *unused);
static int qp_on_load(const void *unused);
static int qp_stream(void);

static void qp_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int qp_off(void) { return qp.sv ? I(qp.sv, SC_YOFF) : 0; }
static void qp_redraw(void) { widget_invalidate_force(qp.sv, (void *)0); }
static int qp_abs(int v) { return v < 0 ? -v : v; }

/* The index is of the stock queue `list` as long as that queue is still the player's, as big, and starts with the same record. */
static int qp_valid(void) {
    void *cur = *(void **)PLAY_QUEUE;
    return qp.list && cur == qp.list && deque_size(cur) == qp.count && (!qp.count || deque_at(cur, 0) == qp.first);
}

/* The play position in the queue the page is of, -1 for none. */
static int qp_playing_row(void) {
    int pos = mclGetPlayPos();
    return pos >= 0 && (unsigned)pos < qp.count ? pos : -1;
}

/* ---------------------------------------------------------------------------
 * Geometry: the header is QP_TOP high, then one ROW per queued track and QP_BOTTOM of air
 */
static int qp_row_y(int i) { return QP_TOP + i * ROW; }
static int qp_content(void) { return QP_TOP + (int)qp.n * ROW + QP_BOTTOM; }

static int qp_max_scroll(void) {
    int m = qp_content() - QP_WIN_H;
    return m > 0 ? m : 0;
}

/* The row under content point y, -1 for the header and the air below the last row. */
static int qp_at(int y) {
    int i = (y - QP_TOP) / ROW;
    return y < QP_TOP || i >= (int)qp.n ? -1 : i;
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none). */
static void qp_span(int *r0, int *r1) {
    int s = qp_off(), n = (int)qp.n;
    *r0 = s <= QP_TOP ? 0 : (s - QP_TOP) / ROW;
    *r1 = s + QP_WIN_H - 1 < QP_TOP ? -1 : (s + QP_WIN_H - 1 - QP_TOP) / ROW;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The rows the tiles are kept for: those in view and QP_AHEAD beyond them in the scroll direction. */
static void qp_window(int *lo, int *hi) {
    int r0, r1;
    qp_span(&r0, &r1);
    if (qp.dir < 0)
        r0 -= QP_AHEAD;
    else
        r1 += QP_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > (int)qp.n - 1) r1 = (int)qp.n - 1;
    *lo = r0, *hi = r1;
}

/* The text of a track as the stock drawer shows it (@0x47a22c): the file name for a CUE track, else the title, else the file name. */
static const char *qp_text(void *rec) {
    const char *t;
    if (I(rec, REC_CUE_START) > 0 || I(rec, REC_CUE_END) > 0) return cc_str(rec, REC_NAME);
    t = cc_str(rec, REC_TITLE);
    return *t ? t : cc_str(rec, REC_NAME);
}

/* Opt-in log (the file /mnt/mmc/m1plus-log turns it on, as the Home log): what building the cover map cost, once per build, to measure it on the device. The time is the query
 * and the build only (the stock records read, hashed, sorted and cleared; no cover file is opened); the existence checks of the covers come later, one per album when it is first asked for. */
static void qp_log(const cc_cmap_stat_t *st, unsigned ms) {
    char line[120];
    int fd, n;
    if (access(LOG_ENABLE, F_OK)) return;
    fd = open(LOG_FILE, O_WRONLY | O_APPEND | O_CREAT, 0644);
    if (fd < 0) return;
    n = snprintf(line, sizeof line, "queue: cover map %u ms, %u albums, %u kept, %u ambiguous, %u queued\n", ms,
                 st->rows, st->kept, st->ambiguous, qp.count);
    if (n > 0 && n < (int)sizeof line) write(fd, line, (unsigned)n);
    close(fd);
}

/* The cover key of a queued track: its own file (cc_album_key, the artist and album of the record), else the file of the library album of that name (a collab "A; B" or a
 * feature has no file under its own artist: the cache is keyed by the album's row, which stock lists under one track's artist). The albums come from the cover map
 * (cc_cmap_build, ONE getAllAlbum query that leaves *pdeq_showlist alone: cc_albums would replace it, and the page under Now Playing draws from it), started by the page's FIRST
 * miss and kept until it closes. The one query of the page's life: map_tried is set before it runs, so a query that fails, an empty library, no memory and a full map are
 * never retried; later misses use the map as it is (none: the own key, the placeholder). A queue with a cover for every track pays nothing, a shuffled library of thousands pays
 * one pause (the query and the map, no file opened) however many rows miss, and scrolling back asks nothing. Whether the album's file exists is looked at by cc_cmap_key the first
 * time the album is asked for and remembered (an album with no picture answers the placeholder without another look); a tile shown again after it was evicted still opens and
 * decodes its image in grid_art, only that existence check is not repeated. Called by the loader and the header, never by paint. */
static unsigned qp_key(void *rec) {
    unsigned own = cc_album_key(rec), key, t0;
    char url[80];
    if (cc_url(url, own) || !*cc_str(rec, REC_ALBUM)) return own;
    if (!qp.map_tried) {
        cc_cmap_stat_t st;
        qp.map_tried = 1;
        t0 = (unsigned)time_now_ms();
        qp.map = cc_cmap_build(&st);
        qp_log(&st, (unsigned)time_now_ms() - t0);
    }
    key = cc_cmap_key(qp.map, cc_str(rec, REC_ALBUM));
    return key ? key : own;
}

/* An episode's cover: its show folder's picture (pc_show_cover, the Podcasts page's), the folder read once per show while the page is open (a queue of one show reads it once).
 * NULL for a track that is not an episode, or a show with no picture (the placeholder). */
static const char *qp_ep_url(void *rec) {
    const char *path = cc_str(rec, REC_PATH);
    unsigned show = pc_show_of(path);
    if (!show) return (const char *)0;
    if (show != qp.pshow) qp.pshow = show, qp.purl_ok = pc_show_cover(path, qp.purl, sizeof qp.purl) != (const char *)0;
    return qp.purl_ok ? qp.purl : (const char *)0;
}

/* A server track's record (streamed or downloaded)? Its cover is the source's file by the record's REC_ID, never a key of the library. */
static int qp_srv(void *rec) { return rec && sba_rec_track(I(rec, REC_ID))[0] != 0; }

/* A server track's cover for a tile: its file when it is there (the tile decodes it), the placeholder when the server has none, and a wait (1) when it was asked for and is on its way. */
static int qp_srv_art(grid_t *g, grid_tile_t *t, void *rec) {
    char url[120];
    int r;
    memcpy(url, "file://", 8);
    r = sba_rec_cover(rec, url + 7, sizeof url - 7);
    if (r == 0) return 1;
    grid_art_url(g, t, r == 1 ? url : (const char *)0);
    return 0;
}

/* The tile of row a (cover key and the two texts), made from the stock record (the caller has checked qp_valid). */
static grid_tile_t *qp_tile(int a) {
    int lo, hi, fresh;
    grid_tile_t *t;
    qp_window(&lo, &hi);
    t = grid_tile(&qp.g, a, lo, hi, &fresh);
    if (fresh) {
        void *rec = deque_at(qp.list, (unsigned)(qp.base + a));
        grid_set(t, qp_text(rec), cc_str(rec, REC_ARTIST), cc_album_key(rec));
    }
    return t;
}

/* ---------------------------------------------------------------------------
 * Paint: the header's cover, and the rows, in one EVT_AFTER_PAINT of the content view. Coordinates are the window's (its top is 0): the scroll_view
 * has moved the canvas up by yoffset, which the paint adds back (CANVAS_OY) for its duration, as the Songs page does.
 */
static void qp_paint(void *canvas) {
    int r0, r1, r, pass, off = qp_off(), room = QP_TEXT_END - LIST_TEXT_X;
    grid_tile_t *h = qp.hg.tiles ? grid_find(&qp.hg, 0) : (grid_tile_t *)0;
    if (h) grid_blit(canvas, &qp.hg, h, QP_COVER_X, QP_COVER_Y - off, QP_WIN_H);
    qp_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        grid_tile_t *t = qp_tile(r);
        int y = qp_row_y(r) - off;
        if (qp.press == r + 1) az_fill_h(canvas, 0, y, y + ROW - 1, QP_ROW_W, LIST_PRESS, QP_WIN_H);
        grid_blit(canvas, &qp.g, t, LIST_ART_X, y + LIST_ART_Y, QP_WIN_H);
        az_fill_h(canvas, LIST_TEXT_X, y + ROW - 1, y + ROW, room, LIST_HAIR, QP_WIN_H);
    }
    for (
        pass = 0; pass < 2;
        ++pass) { /* titles, then artists: one text style at a time; the scroll_view's clip cuts a text at the window's edges, as a cover */
        widget_prepare_text_style(pass ? qp.st_sub : qp.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, qp_tile(r), pass, LIST_TEXT_X, qp_row_y(r) - off + (pass ? LIST_SUB_Y : LIST_TITLE_Y),
                      room, pass ? LIST_SUB_H : LIST_TITLE_H, 0);
    }
}

static int qp_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = qp_off();
    (void)ctx;
    if (!canvas || !qp.view || !qp.g.tiles) return RET_OK;
    if (qp.list &&
        !qp_valid()) { /* the player's queue was replaced: nothing of it is read; the page reads it again when it is on top */
        if (!qp.stale_timer) qp.stale_timer = timer_add(qp_on_stale, (void *)0, 100);
        return RET_OK;
    }
    I(canvas, CANVAS_OY) += off;
    qp_paint(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The loader: one cover per tick on the page's own timer, none while the scroll_view moves (the Songs page's)
 */
static int qp_next_load(void) {
    int lo, hi, a, best = -1, bd = 0x7fffffff, s = qp_off();
    if (!qp.g.tiles || !qp.n || !qp_valid()) return -1;
    qp_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        grid_tile_t *t = grid_find(&qp.g, a);
        int top = qp_row_y(a) - s, d;
        if (t && (t->art || t->load)) continue; /* (load: a server cover on its way, the tick clears it) */
        d = qp_abs(top + ROW / 2 - QP_WIN_H / 2);
        if (top >= QP_WIN_H || top + ROW <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int qp_moving(void) { return grid_moving(qp.sv); }

static void qp_kick(void) {
    if (!qp.more_timer && qp.view && (qp.noscroll || qp_next_load() >= 0))
        qp.more_timer = timer_add(qp_on_load, (void *)0, QP_MORE_MS);
}

static void qp_dir(void) {
    int s = qp_off();
    if (s != qp.seen) qp.dir = s > qp.seen ? 1 : -1;
    qp.seen = s;
}

static int qp_on_load(const void *unused) {
    int a;
    (void)unused;
    qp.more_timer = 0;
    if (!qp.view) return RET_OK;
    qp_dir();
    if (qp_moving()) { /* nothing is decoded while it moves: look again next tick */
        qp_kick();
        return RET_OK;
    }
    a = qp_next_load();
    if (a >= 0) {
        grid_tile_t *t = qp_tile(a);
        int top = qp_row_y(a) - qp_off();
        void *rec = deque_at(qp.list, (unsigned)(qp.base + a)); /* (qp_next_load checked qp_valid) */
        if (pc_is_path(cc_str(rec, REC_PATH)))
            grid_art_url(&qp.g, t, qp_ep_url(rec)); /* an episode: no album to look up */
        else if (qp_srv(rec))
            t->load = qp_srv_art(&qp.g, t, rec);
        else
            t->ckey = qp_key(rec), grid_art(&qp.g, t);
        if (top < QP_WIN_H && top + ROW > 0) qp_redraw();
    }
    qp_kick();
    return RET_OK;
}

static int qp_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!qp.view) return RET_OK;
    qp_dir();
    qp_kick();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The header: the playing track's cover, title and artist, and the song count
 */
/* The header's cover for track rec (NULL: none, the placeholder): an episode's show picture (keyed by the show), else the album's cache file. */
static void qp_cover(void *rec) {
    grid_tile_t *t = qp.hg.tiles ? grid_find(&qp.hg, 0) : (grid_tile_t *)0;
    unsigned show = rec ? pc_show_of(cc_str(rec, REC_PATH)) : 0, srv = qp_srv(rec),
             key = show  ? show
                   : srv ? (unsigned)I(rec, REC_ID) | 1u
                   : rec ? qp_key(rec)
                         : 0;
    if (!t || key == qp.hkey) return;
    qp.hkey = key;
    grid_free_art(t);
    t->ckey = show || srv ? 0 : key;
    qp.hpend = 0;
    if (show)
        grid_art_url(&qp.hg, t, qp_ep_url(rec));
    else if (srv)
        qp.hpend = qp_srv_art(&qp.hg, t, rec);
    else
        grid_art(&qp.hg, t);
    if (!qp.hg.placeholder && t->art != 1) grid_placeholder(&qp.hg);
}

static void qp_header(void) {
    void *t = qp.list && qp.row >= 0 ? deque_at(qp.list, (unsigned)qp.row) : cc_playing();
    widget_set_text_utf8(qp.htitle, t ? qp_text(t) : "");
    widget_set_text_utf8(qp.hartist, t ? cc_str(t, REC_ARTIST) : "");
    qp_cover(t);
}

/* ---------------------------------------------------------------------------
 * The pills: one stock play mode shown as two switches (a pill that is on is lighter; Repeat's glyph is repeat-1 for Repeat one)
 */
static void qp_pill(void *btn, int on, const char *icon) {
    static const char *const state[4] = {"normal", "over", "pressed", "focused"};
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    char name[40], picture[24];
    int i;
    snprintf(picture, sizeof picture, on ? "%s_on" : "%s",
             icon); /* the dark glyph on the light fill, the white one on the dark fill */
    for (i = 0; i < 4; ++i) {
        memset(v, 0, sizeof v);
        value_set_uint32(v, i == 2 ? (on ? QP_PILL_ON_DOWN : QP_PILL_OFF_DOWN) : (on ? QP_PILL_ON : QP_PILL_OFF));
        snprintf(name, sizeof name, "%s:bg_color", state[i]);
        widget_set_style(btn, name, v);
        snprintf(name, sizeof name, "style:%s:icon", state[i]);
        widget_set_prop_str(btn, name, picture);
    }
}

static int qp_mode(void) { return mclGetPlayMode() | (pod_shuffle_on() ? 0x100 : 0); }

static void qp_pills(void) {
    int mode = mclGetPlayMode();
    qp.mode = qp_mode();
    qp_pill(qp.btn_shuffle, pod_shuffle_on(), "sg_shuffle");
    qp_pill(qp.btn_repeat, mode == MODE_REPEAT_ALL || mode == MODE_REPEAT_ONE,
            mode == MODE_REPEAT_ONE ? "sg_repeat1" : "sg_repeat");
    widget_invalidate_force(qp.btn_shuffle, (void *)0);
    widget_invalidate_force(qp.btn_repeat, (void *)0);
}

static void qp_load(int keep);

/* Clear: shown only while songs follow and the engine can run (libcstl as pinned, no DLNA service). Read again on the page's tick, so it hides when the DLNA service starts under the page. */
static void qp_clear_sync(void) {
    int on = qp.n != 0 && !qp_stream() && pod_clear_ready();
    if (on == qp.clear_on) return;
    qp.clear_on = on;
    qp_show(qp.btn_clear, on);
}

/* The play mode changed (our buttons, the refresh tick finding another page's change): turning Shuffle on or off reorders the queue, so the rows are read again; a repeat change only touches the buttons. */
static void qp_mode_changed(void) {
    if (((qp.mode ^ qp_mode()) & 0x100) != 0)
        qp_load(0);
    else
        qp_pills();
}

static int qp_on_shuffle(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!qp.view) return RET_OK;
    pod_set_shuffle(!pod_shuffle_on());
    qp_mode_changed();
    return RET_OK;
}

static int qp_on_repeat(void *ctx, void *e) {
    int mode;
    (void)ctx;
    (void)e;
    if (!qp.view) return RET_OK;
    mode = mclGetPlayMode();
    pod_set_repeat(mode == MODE_REPEAT_ALL ? MODE_REPEAT_ONE : mode == MODE_REPEAT_ONE ? MODE_ORDER : MODE_REPEAT_ALL);
    qp_mode_changed();
    return RET_OK;
}

/* Clear: every track after the play position goes (patch/shuffle.c pod_clear_upnext); the playing track plays on. The page reads the queue again: the header stays, Up Next is empty. */
static int qp_on_clear(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!qp.view || !qp.n || !qp_valid() || qp_stream() || !pod_clear_ready()) return RET_OK;
    pod_clear_upnext();
    qp_load(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Reading the stock queue
 */
static void qp_size(void) {
    int h = qp.n ? qp_content() : QP_WIN_H;
    widget_resize(qp.view, QP_VIEW_W, h);
    widget_set_prop_int(qp.sv, "virtual_h", h);
}

/* The queue again (the player's deque, the position and mode read) and the page rebuilt from it: the rows are the tracks after the play position, in queue order. keep: the scroll offset stays; else the page opens at the top. */
static void qp_load(int keep) {
    int at = keep ? qp_off() : 0;
    void *list = *(void **)PLAY_QUEUE;
    grid_drop(&qp.g);
    qp.list = qp.first = (void *)0, qp.count = 0, qp.press = qp.down = 0;
    if (list) qp.count = deque_size(list);
    if (qp.count) qp.list = list, qp.first = deque_at(list, 0);
    qp.row = qp_playing_row();
    qp.base = qp.row + 1; /* -1 (no track): from the first */
    qp.n = qp.count > (unsigned)qp.base ? qp.count - (unsigned)qp.base : 0;
    qp.hkey = 0;
    qp_show(qp.empty, qp.n == 0);
    qp.clear_on = -1; /* qp_clear_sync decides */
    qp_clear_sync();
    qp_size();
    widget_set_prop_int(qp.sv, "yoffset", at < 0 ? 0 : at > qp_max_scroll() ? qp_max_scroll() : at);
    qp.seen = qp_off();
    grid_placeholder(&qp.g);
    qp_header();
    qp_pills();
    qp_redraw();
    qp_kick();
}

/* The queue was replaced under a page that is on top (a paint found it): read it again. A page behind another reads it when it comes back. */
static int qp_on_stale(const void *unused) {
    (void)unused;
    qp.stale_timer = 0;
    if (qp.view && qp.g.tiles && !qp_valid() && pod_is_top(qp.win)) qp_load(1);
    return RET_OK;
}

/* What the player does under the page: another track (the header and the rows after it), another mode (the buttons), another queue. */
static void qp_sync(void) {
    int row;
    if (!qp.view || !qp.g.tiles) return;
    qp_clear_sync();
    if (!qp_valid()) {
        if (qp.fg && pod_is_top(qp.win)) qp_load(1);
        return;
    }
    row = qp_playing_row();
    if (qp_mode() != qp.mode) qp_mode_changed();
    if (row != qp.row) qp_load(0);
}

/* Server covers that were asked for: their tiles (and the header) look again, once per tick, until the file is there or the source says there is none. */
static void qp_srv_retry(void) {
    int i, any = 0;
    if (qp.hpend) qp.hkey = 0, qp_header(), qp_redraw();
    for (i = 0; qp.g.tiles && i < qp.g.n; ++i)
        if (qp.g.tiles[i].load) qp.g.tiles[i].load = 0, any = 1;
    if (any) qp_kick();
}

static int qp_on_tick(const void *unused) {
    unsigned want;
    (void)unused;
    if (!qp.view) return RET_OK;
    want = pod_screen_lit() ? QP_TICK_MS : POD_DARK_MS;
    if (qp.tick_timer && qp.tick_ms != want && timer_modify(qp.tick_timer, want) == RET_OK) qp.tick_ms = want;
    if (qp.fg) qp_sync();
    qp_srv_retry();
    return RET_REPEAT;
}

/* ---------------------------------------------------------------------------
 * Playing: the stock drawer's row handler (@0x479f60): start_playqueue(row); Now Playing below follows (force_refreshflag, as the handler sets it)
 */
static void qp_play_at(int at) {
    if (!qp_valid()) {
        qp_load(1);
        return;
    }
    start_playqueue(qp.base + at);
    *(unsigned char *)FORCE_REFRESH = 1;
    qp_load(0); /* the rows are the ones after the new track */
}

/* ---------------------------------------------------------------------------
 * Touch on the rows (the Songs page's: DOWN remembers, ABORT forgets, UP within the drag threshold on the same row acts)
 */
static int qp_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(qp.view, pt);
    return qp_at(pt[1]);
}

static void qp_set_press(int p) {
    if (qp.press == p) return;
    qp.press = p;
    qp_redraw();
}

static int qp_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    qp.down = 0;
    if (!e || !qp.view || !qp.n || !qp_valid()) return RET_OK;
    a = qp_item_of(e);
    qp.down = a + 1, qp.down_x = I(e, PE_X), qp.down_y = I(e, PE_Y);
    qp_set_press(a + 1);
    return RET_OK;
}

static int qp_on_up(void *ctx, void *e) {
    int a = qp.down - 1;
    (void)ctx;
    qp.down = 0;
    qp_set_press(0);
    if (a < 0 || !e || !qp.view) return RET_OK;
    if (qp_abs(I(e, PE_X) - qp.down_x) < SC_DRAG_PX && qp_abs(I(e, PE_Y) - qp.down_y) < SC_DRAG_PX &&
        qp_item_of(e) == a)
        qp_play_at(a);
    return RET_OK;
}

static int qp_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    qp.down = 0;
    qp_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
static int qp_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    navigator_back();
    return RET_OK;
}

static int qp_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!qp.view || !qp.g.tiles) return RET_OK;
    qp.fg = 1;
    if (!qp_valid())
        qp_load(1);
    else
        qp_sync();
    qp_kick();
    return RET_OK;
}

static int qp_on_bg(void *ctx, void *e) {
    qp.fg = 0;
    return qp_on_abort(ctx, e);
}

static int qp_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (qp.more_timer) timer_remove(qp.more_timer);
    if (qp.stale_timer) timer_remove(qp.stale_timer);
    if (qp.tick_timer) timer_remove(qp.tick_timer);
    grid_free(&qp.g);
    grid_free(&qp.hg);
    cc_cmap_free(qp.map);
    memset(&qp, 0, sizeof qp);
    return RET_OK;
}

/* A play type the page leaves to the stock drawer: a stream (the drawer refuses its rows while offline and plays them through the network state). */
static int qp_stream(void) {
    int t = mclGetPlayType();
    return t == QP_STREAM_A || t == QP_STREAM_B || t == QP_STREAM_C || t == QP_STREAM_D;
}

/* Open the page on the player's queue (Now Playing's queue button). 0 once the page is up; -1 when it was not tried (the stock drawer opens); -2 when the window did not open
 * or the asset is not ours (the stock drawer opens). */
int queue_open(void) {
    void *list = *(void **)PLAY_QUEUE;
    int fresh;
    if (qp.win || !list || !deque_size(list) || !cc_playing() || qp_stream()) return -1;
    memset(&qp, 0, sizeof qp);
    qp.win = window_open(QP_ASSET);
    if (!qp.win) {
        memset(&qp, 0, sizeof qp);
        return -2;
    }
    widget_on(qp.win, EVT_DESTROY, qp_on_destroy, (void *)0);
    qp.back = pod_bind(qp.win, "btn_return", qp_on_back, (void *)0);
    qp.btn_shuffle = pod_bind(qp.win, "btn_shuffle", qp_on_shuffle, (void *)0);
    qp.btn_repeat = pod_bind(qp.win, "btn_repeat", qp_on_repeat, (void *)0);
    qp.btn_clear = pod_bind(qp.win, "btn_qclear", qp_on_clear, (void *)0);
    qp.view = widget_lookup(qp.win, "view_queue", 1);
    qp.sv = widget_lookup(qp.win, "queue_scrollview", 1);
    qp.status = widget_lookup(qp.win, "label_status", 1);
    qp.st_title = widget_lookup(qp.win, "label_row_title", 1);
    qp.st_sub = widget_lookup(qp.win, "label_row_sub", 1);
    qp.htitle = widget_lookup(qp.win, "qp_title", 1);
    qp.hartist = widget_lookup(qp.win, "qp_artist", 1);
    qp.empty = widget_lookup(qp.win, "qp_empty", 1);
    if (!qp.back || !qp.btn_shuffle || !qp.btn_repeat || !qp.btn_clear || !qp.view || !qp.sv || !qp.status ||
        !qp.st_title || !qp.st_sub || !qp.htitle || !qp.hartist || !qp.empty) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    qp.fg = 1;
    widget_on(qp.win, EVT_WINDOW_TO_FG, qp_on_fg, (void *)0);
    widget_on(qp.win, EVT_WINDOW_TO_BG, qp_on_bg, (void *)0);
    qp.noscroll = !widget_on(qp.sv, EVT_SCROLL, qp_on_scroll, (void *)0) ||
                  !widget_on(qp.sv, EVT_SCROLL_END, qp_on_scroll, (void *)0);
    widget_on(qp.view, EVT_POINTER_DOWN, qp_on_down, (void *)0);
    widget_on(qp.view, EVT_POINTER_UP, qp_on_up, (void *)0);
    widget_on(qp.view, EVT_POINTER_ABORT, qp_on_abort, (void *)0);
    widget_on(qp.view, EVT_AFTER_PAINT, qp_on_paint, (void *)0);
    if (!grid_init(&qp.hg, qp.win, 1, QP_COVER, QP_COVER_R) || !grid_init(&qp.g, qp.win, GRID_TILES, LIST_ART, 0)) {
        grid_free(&qp.hg);
        grid_free(&qp.g);
        qp_show(qp.view, 0);
        qp_show(qp.status, 1);
        widget_set_tr_text(qp.status, "Not enough memory");
        return 0;
    }
    grid_shape(&qp.hg, QP_COVER, QP_COVER_R, 1); /* the corners are cut in the alpha */
    grid_shape(&qp.g, LIST_ART, LIST_R, 1);
    grid_tile(&qp.hg, 0, 0, 0, &fresh);
    qp.tick_ms = QP_TICK_MS;
    qp.tick_timer = timer_add(qp_on_tick, (void *)0, QP_TICK_MS);
    qp_load(0);
    return 0;
}
