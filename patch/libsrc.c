/* The stock library as a lib_src_t (patch/libsrc.h; docs/modules/subsonic.md "The seam"). Every member wraps the call a page makes today, so a page handed &lib_stock behaves as one handed NULL:
 * list = the stock queries copied (cc_albums, cc_songs, loadLocalClassList / loadAlbumList / loadAlbumdetailList into *pdeq_showlist, cc_copy_list), play = so_play, cover = the cache file
 * the Cover Flow worker makes, seconds = the durations table. Nothing here is a hook or a timer.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "covercache.h"
#include "durations.h"
#include "i18n.h"
#include "songops.h"
#include "libsrc.h"
#include "sbapi.h"

#define I(w, off) (*(int *)((char *)(w) + (off)))

/* A stock list copied; NULL when empty or the copy failed. */
static void *ls_copy(void *list) {
    void *copy;
    if (!list || !deque_size(list)) return (void *)0;
    copy = cc_copy_list(list);
    if (copy && !deque_size(copy)) {
        deque_destroy(copy);
        copy = (void *)0;
    }
    return copy;
}
#define ls_copy_show() ls_copy(*(void **)PDEQ_SHOWLIST)

/* loadLocalClassList(cls) and the copy of the list it left in `slot` (*pdeq_showlist, or *pdeq_playlist for the playlists). */
static void *ls_class(int cls, int slot) { return loadLocalClassList(cls) > 0 ? ls_copy(*(void **)slot) : (void *)0; }

static void *ls_list(const lib_src_t *s, int which, void *scope) {
    (void)s;
    switch (which) {
    case LS_ALBUMS:
        if (!scope) return cc_albums();
        loadAlbumList(CLASS_ARTISTS, scope); /* an artist's albums (coverflow_artist_albums' query) */
        return ls_copy_show();
    case LS_ARTISTS:
        return scope ? (void *)0 : ls_class(CLASS_ARTISTS, PDEQ_SHOWLIST);
    case LS_SONGS:
        if (!scope) return cc_songs();
        loadAlbumdetailList(I(scope, REC_ID) == ID_ALL_SONGS ? CLASS_ARTIST_ALBUMS : CLASS_ALBUMS,
                            scope); /* the album page's and songs_artist_list's query */
        return ls_copy_show();
    case LS_PLAYLISTS:
        if (!scope) return ls_class(CLASS_PLAYLISTS, PDEQ_PLAYLIST);
        *(int *)(CLASSINFO + CLASSINFO_ARG) = I(scope, REC_DISC); /* pl_scan's query: classinfo[1] = the playlist id */
        loadLocalClassList(CLASS_PLAYLIST_SONGS);
        return ls_copy_show();
    }
    return (void *)0; /* Favorites, Downloaded: Navidrome's */
}

static const char *ls_rec_id(const lib_src_t *s, void *rec) {
    (void)s, (void)rec;
    return "";
}

static int ls_play(const lib_src_t *s, void *list, int at, int how, void (*open)(void *queue, int idx, int cls),
                   int cls) {
    (void)s;
    return so_play(cls, list, at, how, open); /* LS_PLAY_* are SO_* */
}

static int ls_cover(const lib_src_t *s, void *rec, unsigned key, char *path, unsigned cap) {
    (void)s, (void)rec;
    cc_path(path, cap, key, "");
    return cc_file_size(path) > 0 ? 1 : -1; /* the page's own worker (cc_build_add) makes a missing file */
}

static unsigned ls_seconds(const lib_src_t *s, void *rec) {
    unsigned size;
    int v;
    (void)s;
    v = dur_song(rec, &size);
    return v > 0 ? (unsigned)v : 0; /* -1 (not yet measured) and 0 (unreadable): unknown */
}

static void ls_row(const lib_src_t *s, void *rec, ls_row_t *out) {
    (void)s, (void)rec;
    memset(out, 0, sizeof *out);
}

static int ls_act(const lib_src_t *s, void *rec, int what) {
    (void)s, (void)rec, (void)what;
    return -1; /* the stock row menu has no extra actions */
}

static unsigned ls_gen(const lib_src_t *s) {
    (void)s;
    return 0;
}

/* ---------------------------------------------------------------------------
 * Row marks
 */
#define LS_MK_H PA_DSD_H /* both marks sit in a PA_DSD_H high cell: the disc one pixel down */
#define LS_MK_DSD_X (PA_BADGE_PX + 4) /* the DSD tag's x in the bitmap */
#define LS_MK_W (LS_MK_DSD_X + PA_DSD_W)
#define LS_MK_BW \
    (PA_DL_PX * \
     PA_DL_COLS) /* the bitmap: the disc and the DSD tag in the top LS_MK_H rows, the download ring's cells under them (steps, then the marks: the atlas' rows copied as they are) */
#define LS_MK_BH (LS_MK_H + PA_DL_PX * (PA_DL_STOP / PA_DL_COLS + 1))
static void *ls_marks_bmp __attribute__((section(".scratch")));

/* pc_atlas' disc, DSD tag and download rings copied into one small straight-alpha RGBA bitmap, once (the atlas is decoded with its alpha and dropped at once, as the Podcasts page does). NULL when it cannot be made. */
static void *ls_marks_get(void *win) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, x, y, *px;
    const unsigned char *data;
    void *b = (void *)0;
    if (ls_marks_bmp) return ls_marks_bmp;
    if (!win) return (void *)0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(win, "pc_atlas", bitmap)) return (void *)0;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data = format < 4 && bitmap[0] == PA_SIZE && bitmap[1] == PA_SIZE ? bitmap_lock_buffer_for_read(bitmap)
                                                                      : (const unsigned char *)0;
    if (data) b = bitmap_create_ex(LS_MK_BW, LS_MK_BH, LS_MK_BW * 4, BITMAP_RGBA8888);
    px = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
    if (px && bitmap_get_line_length(b) == LS_MK_BW * 4) {
        unsigned stride = bitmap_get_line_length(bitmap);
        memset(px, 0, LS_MK_BW * LS_MK_BH * 4);
        for (y = 0; y < LS_MK_BH; ++y)
            for (x = 0; x < LS_MK_BW; ++x) {
                unsigned sx, sy;
                const unsigned char *s;
                if (y >= LS_MK_H)
                    sx = PA_DL_X + x, sy = PA_DL_Y + y - LS_MK_H;
                else if (x >= LS_MK_W)
                    continue;
                else if (x >= LS_MK_DSD_X)
                    sx = PA_DSD_X + x - LS_MK_DSD_X, sy = PA_DSD_Y + y;
                else if (x < PA_BADGE_PX && y >= 1 && y <= PA_BADGE_PX)
                    sx = PA_BADGE_X + x, sy = PA_DOTS_Y + y - 1;
                else
                    continue;
                s = data + sy * stride + sx * 4;
                px[y * LS_MK_BW + x] = s[at[format][0]] | s[at[format][1]] << 8 | s[at[format][2]] << 16 |
                                       (unsigned)s[at[format][3]] << 24;
            }
    } else if (b) {
        bitmap_destroy(b);
        b = (void *)0;
    }
    if (px) bitmap_unlock_buffer(b);
    if (data) bitmap_unlock_buffer(bitmap);
    widget_unload_image(win, bitmap);
    ls_marks_bmp = b;
    return b;
}

/* The download ring a row shows: its step 0..PA_DL_N - 1 (the arc step / PA_DL_N of the circle, rounded to the nearest), 0 (no arc) for a queued track or an unknown progress; -1 when the row is not downloading. */
int ls_ring_step(const ls_row_t *r) {
    int p, k;
    if (r->dl != LS_DL_ACTIVE && r->dl != LS_DL_WAIT) return -1;
    if (r->dl == LS_DL_WAIT || r->pct < 0) return 0;
    p = r->pct > 100 ? 100 : r->pct;
    k = (p * PA_DL_N + 50) / 100;
    return k > PA_DL_N - 1 ? PA_DL_N - 1 : k;
}

int ls_marks_w(const ls_row_t *r) {
    int w = 0;
    if (r->dl == LS_DL_DONE) w += PA_BADGE_PX;
    if (ls_ring_step(r) >= 0) w += PA_DL_PX;
    if (r->dsd) w += (w ? LS_MK_GAP : 0) + PA_DSD_W;
    return w;
}

static void ls_mark_draw(void *canvas, void *bmp, int mark, int x, int y_mid, int view_h) {
    int src[4], dst[4], w = mark == LS_MK_DSD ? PA_DSD_W : PA_BADGE_PX, top = y_mid - LS_MK_H / 2;
    if (view_h > 0 && (top < 0 || top + LS_MK_H > view_h)) return;
    src[0] = mark == LS_MK_DSD ? LS_MK_DSD_X : 0, src[1] = 0, src[2] = w, src[3] = LS_MK_H;
    dst[0] = x, dst[1] = top, dst[2] = w, dst[3] = LS_MK_H;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* A download ring cell (a step, or the arrow / stop mark), PA_DL_PX square, centred on y_mid. */
static void ls_ring_draw(void *canvas, void *bmp, int cell, int x, int y_mid, int view_h) {
    int src[4], dst[4], top = y_mid - PA_DL_PX / 2;
    if (view_h > 0 && (top < 0 || top + PA_DL_PX > view_h)) return;
    src[0] = cell % PA_DL_COLS * PA_DL_PX, src[1] = LS_MK_H + cell / PA_DL_COLS * PA_DL_PX, src[2] = src[3] = PA_DL_PX;
    dst[0] = x, dst[1] = top, dst[2] = dst[3] = PA_DL_PX;
    canvas_draw_image(canvas, bmp, src, dst);
}

void ls_marks_draw(void *canvas, void *win, const ls_row_t *r, int x, int y_mid, int view_h) {
    void *bmp = ls_marks_w(r) ? ls_marks_get(win) : (void *)0;
    int ring = ls_ring_step(r);
    if (!bmp) return;
    if (r->dl == LS_DL_DONE) ls_mark_draw(canvas, bmp, LS_MK_DONE, x, y_mid, view_h), x += PA_BADGE_PX + LS_MK_GAP;
    if (ring >= 0)
        ls_ring_draw(canvas, bmp, ring, x, y_mid, view_h),
            ls_ring_draw(canvas, bmp, r->dl == LS_DL_ACTIVE ? PA_DL_STOP : PA_DL_ARROW, x, y_mid, view_h),
            x += PA_DL_PX + LS_MK_GAP;
    if (r->dsd) ls_mark_draw(canvas, bmp, LS_MK_DSD, x, y_mid, view_h);
}

const lib_src_t lib_stock = {"stock",
                             ls_list,
                             ls_rec_id,
                             ls_play,
                             ls_cover,
                             ls_seconds,
                             ls_row,
                             ls_act,
                             ls_gen,
                             (int (*)(const lib_src_t *, int))0,
                             (int (*)(const lib_src_t *, void *))0,
                             (void *(*)(const lib_src_t *, void *))0,
                             LS_CAP_ALL,
                             (int (*)(const lib_src_t *, int, void *))0,
                             (int (*)(const lib_src_t *, int, void *))0,
                             (unsigned (*)(const lib_src_t *))0};

static int ls_same_str(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* The list just read has the rows the page shows, in the same order: the same address (REC_PATH), title and artist in each (the page's tiles and scroll stay as they are). */
int ls_same_list(void *old, unsigned oldn, void *fresh, unsigned n) {
    unsigned i;
    if (!old || !fresh || oldn != n) return 0;
    for (i = 0; i < n; ++i) {
        void *a = deque_at(old, i), *b = deque_at(fresh, i);
        if (!ls_same_str(cc_str(a, REC_PATH), cc_str(b, REC_PATH)) ||
            !ls_same_str(cc_str(a, REC_TITLE), cc_str(b, REC_TITLE)) ||
            !ls_same_str(cc_str(a, REC_ARTIST), cc_str(b, REC_ARTIST)))
            return 0;
    }
    return 1;
}

#define LS_SPIN_MS 250 /* the spinner's frame (the Wi-Fi page's pace) */
typedef struct {
    void *img;
    int n, on;
} ls_sp_t;
static ls_sp_t ls_sp[4] __attribute__((section(".scratch")));
static unsigned ls_sp_timer __attribute__((section(".scratch")));

/* One timer turns every spinner up. Its argument is stock's timer_info_t (timer_info_on_timer 0x716ebc passes the timer, the ctx is a field of it),
 * so the slots are found here, not through the argument. A hidden spinner leaves its slot at the next tick; the timer ends with the last one. */
int ls_spin_tick(const void *arg) {
    char name[12];
    int k, live = 0;
    (void)arg;
    for (k = 0; k < 4; ++k) {
        ls_sp_t *p = &ls_sp[k];
        if (!p->img) continue;
        if (!p->on) {
            p->img = (void *)0;
            continue;
        }
        snprintf(name, sizeof name, "wf_spin%d", ++p->n & 7);
        image_base_set_image(p->img, name);
        widget_invalidate_force(p->img, (void *)0);
        live = 1;
    }
    if (!live) ls_sp_timer = 0;
    return live ? RET_REPEAT : RET_OK;
}

void ls_spin(void *img, int on) {
    int k, free_k = -1;
    if (!img) return;
    widget_set_visible(img, on, 0);
    for (k = 0; k < 4; ++k) {
        if (ls_sp[k].img == img) break;
        if (!ls_sp[k].img && free_k < 0) free_k = k;
    }
    if (k == 4) {
        if (!on || free_k < 0) return;
        k = free_k, ls_sp[k].img = img, ls_sp[k].n = 0;
    }
    ls_sp[k].on = on;
    if (on && !ls_sp_timer) ls_sp_timer = timer_add(ls_spin_tick, (void *)0, LS_SPIN_MS);
    if (!on && !ls_sp_timer) ls_sp[k].img = (void *)0;
}

void ls_spin_end(void *img) {
    int k, live = 0;
    for (k = 0; img && k < 4; ++k)
        if (ls_sp[k].img == img) memset(&ls_sp[k], 0, sizeof ls_sp[k]);
    for (k = 0; k < 4; ++k) live |= ls_sp[k].img != (void *)0;
    if (!live && ls_sp_timer) {
        timer_remove(ls_sp_timer);
        ls_sp_timer = 0;
    }
}

/* The shared cover poll (patch/libsrc.h ls_cover_poll): up to LS_CP_N pages at once (the pages stacked), one timer. */
#define LS_CP_N 6
static ls_cpoll_t *ls_cp[LS_CP_N] __attribute__((section(".scratch")));
static unsigned ls_cp_timer __attribute__((section(".scratch")));

static void ls_cp_drop(int k) {
    ls_cpoll_t *p = ls_cp[k];
    ls_cp[k] = (ls_cpoll_t *)0;
    p->on = p->pend = p->idle = 0;
}

int ls_cover_tick(const void *arg) {
    int k, live = 0;
    (void)arg;
    for (k = 0; k < LS_CP_N; ++k) {
        ls_cpoll_t *p = ls_cp[k];
        int n = 0;
        if (!p) continue;
        live = 1;
        if (!pod_screen_lit() || !pod_is_top(p->win)) continue;
        if (p->pend) {
            p->pend = 0, p->idle = 0;
            if (++p->polls > LS_COVER_POLLS) { /* the one give-up rule */
                ls_cp_drop(k);
                p->polls = 0;
                if (p->giveup) p->giveup();
                continue;
            }
            if (p->ask) p->ask();
            if (ls_cp[k] != p) continue; /* (the page went) */
        } else if (p->idle < 2)
            ++p->idle;
        if (p->spin) n = p->spin();
        if (ls_cp[k] != p) continue;
        if (!p->pend &&
            p->idle >=
                2) { /* two quiet ticks: nothing is on its way any more (a spinner still turning is stale: cleared) */
            ls_cp_drop(k);
            p->polls = 0;
            if (n && p->giveup) p->giveup();
        }
    }
    for (k = 0, live = 0; k < LS_CP_N; ++k) live |= ls_cp[k] != (ls_cpoll_t *)0;
    if (!live) ls_cp_timer = 0;
    return live ? RET_REPEAT : RET_OK;
}

void ls_cover_poll(ls_cpoll_t *p, void *win, void (*ask)(void), int (*spin)(void), void (*giveup)(void)) {
    int k, free_k = -1;
    p->win = win, p->ask = ask, p->spin = spin, p->giveup = giveup;
    p->pend = 1, p->idle = 0;
    for (k = 0; k < LS_CP_N; ++k) {
        if (ls_cp[k] == p) break;
        if (!ls_cp[k] && free_k < 0) free_k = k;
    }
    if (k == LS_CP_N) {
        if (free_k < 0) return;
        ls_cp[free_k] = p, p->on = 1;
    }
    if (!ls_cp_timer) ls_cp_timer = timer_add(ls_cover_tick, (void *)0, LS_COVER_MS);
}

void ls_cover_end(ls_cpoll_t *p) {
    int k, live = 0;
    for (k = 0; k < LS_CP_N; ++k) {
        if (ls_cp[k] == p) ls_cp_drop(k), p->polls = 0;
        live |= ls_cp[k] != (ls_cpoll_t *)0;
    }
    if (!live && ls_cp_timer) {
        timer_remove(ls_cp_timer);
        ls_cp_timer = 0;
    }
}

int ls_rec_server(void *rec) { return rec && sba_rec_track(*(int *)((char *)rec + REC_ID))[0] != 0; }

int ls_rec_cover(void *rec, char *url, unsigned cap, int *server) {
    *server = ls_rec_server(rec);
    if (!*server) return -1;
    memcpy(url, "file://", 8);
    return sba_rec_cover(rec, url + 7, cap - 7);
}

const char *ls_empty_key(int st, const char *empty) {
    return st == LS_ST_LOADING   ? "Loading…"
           : st == LS_ST_OFFLINE ? "Connect to Wi-Fi first"
           : st == LS_ST_FAILED  ? "Can't connect to the server"
                                 : empty;
}

unsigned ls_gen_rows(const lib_src_t *src) { return src->gen_rows ? src->gen_rows(src) : src->gen(src); }

unsigned ls_caps(const lib_src_t *src) { return !src || src == &lib_stock ? LS_CAP_ALL : src->caps; }

/* Favorite / Undo Favorite through the source (LS_ACT_FAVORITE): the source toasts a refusal, a success toasts "Added to Favorites" or "Removed from Favorites" by `was` (the state the caller showed). The row sheet and Now Playing's star share it. The act result: 0 done. */
int ls_favorite(const lib_src_t *src, void *rec, int was) {
    int r = src->act(src, rec, was ? LS_ACT_UNFAVORITE : LS_ACT_FAVORITE);
    if (r == 0) pod_toast(TR(was ? "Removed from Favorites" : "Added to Favorites"));
    return r;
}
