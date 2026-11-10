/* M1+ Music album page: an album's tracks, our own page in place of the stock albuminfo_page (docs/modules/album-page.md has the design and the geometry).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_album.bin (tools/pod_ui.py build_album_page): the stock list (list_view > scroll_view) holding ONE content view, view_grid, as the Songs page, which
 * reaches the window's top (450 px) with the glass controls floating over it (Back, a Select | Now Playing capsule; in select mode the all / none toggle, Add, Delete and
 * Cancel), so the rows scroll under them. The content view holds the header's widgets (the title, the artist and the "year . N tracks" line, the Shuffle disc and the
 * Play pill with its glyph and text) and paints the rest itself in its EVT_AFTER_PAINT: the rounded cover, the tracks' numbers and titles, the press fill, the hairlines
 * and the select marks. The window is tinted from the cover as Now Playing is (pod_tone under the gradient image img_ah_tint), and so is the status bar (pod_bar_tint).
 *
 *   entry     album_open(class, row), called by cc_open_album (patch/covercache.c) with the album row of the list the caller loaded: loadAlbumdetailList(class, row) leaves
 *             the album's tracks in *pdeq_showlist and the browsing record in classinfo (class 0xff10 an album of the library, 0xff11 an album of an artist, 0xff14 a composer's),
 *             which the page snapshots and puts back before every query and play (another page's query overwrites it). Anything the page cannot show (the
 *             "All albums" card, a window that will not open) returns -1 and the caller opens the stock albuminfo_page.
 *   cover     the Cover Flow cache file of the album (/mnt/mmc/.m1plus/covers/<key>-168.jpg, the key of the album row), box-reduced to 160 px with its corners cut in the alpha;
 *             a file that is not there is made by the cache worker (one job, polled), an empty "no art" marker leaves the placeholder disc and a black page.
 *   tint      the tone cache (pod_tone_get) or the cover file's average colour; none for a page without a cover.
 *   rows      the stock row's number (position + 1) and title (the stock is_playing: a playing track's number is the wave marker), 64 px, from the stock list while painting.
 *   play      Play / Shuffle / a track: patch/songops.c, and Now Playing opens the way the stock album page's rows do (pod_open_player: with songerinfoflag set the
 *             pages above the Now Playing in the stack are popped first).
 *   source    album_open_src(src, cls, row): the page of an album of a library source (patch/libsrc.h; docs/modules/subsonic.md): tracks from src->list(LS_SONGS, row) (our own deque,
 *             freed with the page), cover from src->cover (polled, no cache worker), the footer's total from src->seconds, Play / Shuffle / a tap through so_play_src, the playing
 *             marker by the record's "nd://" url, a re-read when src->gen moves. No select mode: the Select button is hidden and a "..." takes its place, opening the shared card with one row, Download Album (src->act(LS_ACT_DOWNLOAD_ALL) on the page's list). NULL or &lib_stock is album_open.
 * No hook; everything runs from the page's widgets and timers.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "palette.h"
#include "scroll.h"
#include "covercache.h"
#include "durations.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "songops.h"
#include "rowmenu.h"
#include "nextalbum.h"
#include "libsrc.h"
#include "viewsort.h"

#define ROW LIST_ROW_H

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *status;
    void *back, *np, *btn_select, *btn_selall, *btn_add, *btn_del, *btn_cancel, *btn_play, *btn_shuffle;
    void *btn_more; /* a source's page: the "..." (Select's place on the library's), opening the card below */
    vs_t vs; /* the shared "..." card with one row, Download Album (a source's page only) */
    void *st_num, *st_title; /* hidden labels whose styles are the number's and the title's */
    void *
        st_dim; /* a source's: the title of a row that cannot play (NULL: the asset has none, the row is drawn as the others) */
    void *
        foot; /* the footer under the last row (ab_foot, a label of the content view): "13 tracks, 49 minutes", hidden while the duration is unknown */
    void *hname, *hartist, *hmeta; /* the header's labels */
    pod_pill_t
        pill; /* the Play pill's glyph and its hidden text label (the text style and the translated text; the page paints it), patch/common.c */
    void *list; /* the stock list the page is of (*pdeq_showlist when valid) */
    void *first; /* its first record: with the size, tells a list another query replaced */
    unsigned count;
    unsigned char *sel; /* the select mode's bitset */
    unsigned nsel;
    int select;
    int press; /* the row under the finger, + 1 */
    int down, down_x, down_y; /* the row a press began on, + 1, and where */
    int picker; /* the stock playlist picker is open over this page */
    char title_save[0x200]; /* nagvation_title across the picker */
    int cls; /* the class listed: 0xff10, 0xff11 or 0xff14 */
    unsigned char ci
        [CLASSINFO_SIZE]; /* the browsing record of the album (CLASSINFO, as loadAlbumdetailList left it), put back before every query and play */
    unsigned cover_key; /* cc_album_key of the album row: the cache file's name; also the tone cache's key */
    unsigned stale_timer, build_timer, dur_timer;
    int own; /* the page holds the cache worker's job set */
    int lown; /* ... or the durations set (a CC_DURATIONS one: the missing tracks of this album) */
    int lheld; /* the durations table is acquired */
    int ltried; /* a durations set ran since the list was read: no second one */
    unsigned dur; /* the album's total seconds when every track's length is known, else 0 */
    unsigned tone; /* the window's colour as 0x00BBGGRR once tinted */
    int tinted;
    int fg; /* 1 from the page's start and EVT_WINDOW_TO_FG, 0 after EVT_WINDOW_TO_BG */
    int barok; /* both window events are registered: the status bar may be tinted */
    int bar; /* the status bar's bg_color is ours and must go back to black */
    void *mark[2]; /* the select marks: unselect, selected */
    void *wave; /* the playing track's marker (ah_wave, AB_WAVE px), NULL when it did not decode: the number stays */
    rowmenu_t rm; /* the rows' "..." menu (patch/rowmenu.c) */
    const lib_src_t *
        src; /* the library source the page is of (patch/libsrc.h); NULL: the stock library, every line below that mentions it is skipped */
    void *
        srow_d; /* src: a one-record deque holding our copy of the album row (the scope of src->list); list is our own copy, freed with the page */
    unsigned gen,
        grows; /* src: src->gen and ls_gen_rows when the list was read; the timer reads them again: gen alone moving repaints the rows, grows moving reads the list */
    unsigned gen_timer;
    void *
        spin; /* src: the loading spinner (ab_spin, optional: the status label says Loading... without it) in the track area */
    int wait; /* src: the album's tracks are not cached yet (lib_src_t.state): the header and the spinner show, not the empty text */
    int down_more; /* the press began in a row's "..." zone */
    ls_cpoll_t
        cp; /* src: the shared cover poll (patch/libsrc.c ls_cover_poll): asks for the header cover again and turns its spinner */
    grid_t hg; /* the cover: one tile, AH_ART px with AH_CORNER px corners cut in the alpha */
    grid_t g; /* the tracks' texts: the ring (a tile holds a title cut to its width; no cover) */
} ab __attribute__((section(".scratch")));

static int ab_on_stale(const void *unused);
static int ab_on_gen(const void *unused);

static void ab_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int ab_off(void) { return ab.sv ? I(ab.sv, SC_YOFF) : 0; }
static void ab_redraw(void) { widget_invalidate_force(ab.sv, (void *)0); }

/* The index is of the stock list `list` as long as that list is still in *pdeq_showlist, as big, and starts with the same record. */
static int ab_valid(void) {
    void *cur;
    if (ab.src) return ab.list != (void *)0; /* our own copy: nothing replaces it */
    cur = *(void **)PDEQ_SHOWLIST;
    return ab.list && cur == ab.list && deque_size(cur) == ab.count && (!ab.count || deque_at(cur, 0) == ab.first);
}

/* The browsing record put back (another page's query may have changed it). */
static void ab_classinfo(void) {
    if (!ab.src) memcpy((void *)CLASSINFO, ab.ci, CLASSINFO_SIZE);
}

/* The track plays now. A source whose queue records are not the page's (Navidrome's carry stream addresses, never the page's "nd://<id>") answers itself (lib_src_t.playing); NULL is the stock test. */
static int ab_playing(void *rec) {
    if (ab.src && ab.src->playing) return ab.src->playing(ab.src, rec);
    if (ab.src)
        return is_playing(
            *(int *)G_CLASS_TYPE, 0, "",
            cc_str(rec, REC_PATH)); /* a source that says nothing: by the record's own url (no file name, no CUE) */
    return is_playing(*(int *)G_CLASS_TYPE, I(rec, REC_CUE_START), (const char *)P(rec, REC_NAME),
                      (const char *)P(rec, REC_PATH));
}

/* ---------------------------------------------------------------------------
 * Geometry: the header is AH_HDR_H high (the cover at AH_ART_Y, the controls' band over its first rows), then one ROW per track
 */
static int ab_row_y(int i) { return AH_HDR_H + i * ROW; }
static int ab_content(void) {
    return AH_HDR_H + (int)ab.count * ROW + (ab.count && ab.dur ? AB_FOOT_GAP + AB_FOOT_TEXT_H + AB_FOOT_PAD : 0);
}

static int ab_max_scroll(void) {
    int m = ab_content() - AH_WIN_H;
    return m > 0 ? m : 0;
}

/* The track under content point y, -1 for the header and the air below the last row. */
static int ab_at(int y) {
    int i = (y - AH_HDR_H) / ROW;
    return y < AH_HDR_H || i >= (int)ab.count ? -1 : i;
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none). */
static void ab_span(int *r0, int *r1) {
    int s = ab_off(), n = (int)ab.count;
    *r0 = s <= AH_HDR_H ? 0 : (s - AH_HDR_H) / ROW;
    *r1 = s + AH_WIN_H - 1 < AH_HDR_H ? -1 : (s + AH_WIN_H - 1 - AH_HDR_H) / ROW;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The select mode moves the rows' content right by one column. */
static int ab_shift(void) { return ab.select ? SG_SEL_COL : 0; }
static int ab_numw(int i) {
    return i + 1 >= 100 ? ROW_NUM_W3 : ROW_NUM_W;
} /* the number's column: 22 px, 32 for three digits */
static int ab_tx(int i) { return AB_NUM_X + ab_shift() + ab_numw(i) + AB_NUM_GAP; } /* the title's x */

/* The row's "..." (patch/rowmenu.c): shown outside select mode, at the list's right edge; the title ends before it. */
static int ab_more(void) { return !ab.select && rowmenu_on(&ab.rm); }
static int ab_text_end(void) { return ab_more() ? rowmenu_zone_x(RM_MORE_RIGHT) - RM_TEXT_GAP : AB_TEXT_END; }

static int ab_is_sel(int i) { return ab.sel && (ab.sel[i >> 3] >> (i & 7) & 1); }

/* The text of a track as the stock row shows it (@0x524b50): the file name for a CUE track, else the title, else the file name. */
static const char *ab_text(void *rec) {
    const char *t;
    if (I(rec, REC_CUE_START) > 0 || I(rec, REC_CUE_END) > 0) return cc_str(rec, REC_NAME);
    t = cc_str(rec, REC_TITLE);
    return *t ? t : cc_str(rec, REC_NAME);
}

/* The tile of track a (its text only), made from the stock record (the caller has checked ab_valid). */
static grid_tile_t *ab_tile(int a) {
    int r0, r1, fresh;
    grid_tile_t *t;
    ab_span(&r0, &r1);
    t = grid_tile(&ab.g, a, r0 - 2, r1 + 2, &fresh);
    if (fresh) grid_set(t, ab_text(deque_at(ab.list, (unsigned)a)), "", 0);
    return t;
}

/* The titles are cut to a width that the select mode changes: every tile's text is made again from the record. */
static void ab_retext(void) {
    int i;
    for (i = 0; ab.g.tiles && ab.list && i < ab.g.n; ++i) {
        grid_tile_t *t = &ab.g.tiles[i];
        if (t->album && t->album - 1 < (int)ab.count)
            grid_set(t, ab_text(deque_at(ab.list, (unsigned)(t->album - 1))), "", 0), t->fit = 0;
    }
}

/* ---------------------------------------------------------------------------
 * Paint: the cover, then the rows, in one EVT_AFTER_PAINT of the content view. Coordinates are the window's (its top is 0): the scroll_view has moved the canvas up by
 * yoffset, which the paint adds back (CANVAS_OY) for its duration, as the Songs page does.
 */
static void ab_number(void *canvas, int i, int y) {
    unsigned w[8], n = 0, d;
    int rect[4];
    for (d = 1; (unsigned)(i + 1) / d >= 10; d *= 10) {
    }
    for (; d; d /= 10) w[n++] = '0' + ((unsigned)(i + 1) / d) % 10;
    rect[0] = AB_NUM_X + ab_shift(), rect[1] = y + AB_TEXT_Y, rect[2] = ab_numw(i), rect[3] = AB_TEXT_H;
    canvas_draw_text_in_rect(canvas, w, n, rect); /* the scroll_view's clip cuts it at the window's edges */
}

/* The playing track's marker: the image ah_wave (white-ish bars on black, as cc_decode flattens it) as a bitmap whose alpha is the bars' coverage and whose colour is AB_WAVE_RGB. */
static void *ab_make_wave(void *win) {
    unsigned *px, i, col;
    void *b = bitmap_create_ex(AB_WAVE, AB_WAVE, AB_WAVE * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != AB_WAVE * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, "ah_wave", 1, AB_WAVE, 1, px);
    col = pal_fill() &
          0xffffffu; /* the accent's, or Neutral's AB_WAVE_COLOR (#EEEEEC): the wave is made when the page opens */
    for (i = 0; ok && i < AB_WAVE * AB_WAVE; ++i) px[i] = (px[i] & 0xff) * 255 / 0xee << 24 | col;
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

static void ab_paint_wave(void *canvas, int i, int y) {
    int src[4], dst[4];
    dst[0] = AB_NUM_X + ab_shift() + ab_numw(i) - AB_WAVE, dst[1] = y + AB_TEXT_Y + (AB_TEXT_H - AB_WAVE) / 2;
    dst[2] = dst[3] = AB_WAVE;
    src[0] = src[1] = 0, src[2] = src[3] = AB_WAVE;
    if (dst[1] >= 0 && dst[1] + AB_WAVE <= AH_WIN_H) canvas_draw_image(canvas, ab.wave, src, dst);
}

static void ab_paint_pill(void *canvas, int off);

/* A source's row marks. The group (downloaded disc or download ring, DSD tag) sits at the right, ending at ab_text_end(); the title is cut for the room it takes (grid_tile_t.xw). Painted only
 * for a non-stock source. */

static void ab_paint(void *canvas) {
    int r0, r1, r, pass, off = ab_off();
    unsigned playing = 0; /* bit r - r0: the track plays (at most 32 rows are ever in view) */
    unsigned dim = 0; /* bit r - r0: a source's row that cannot play now: its title in the dim style */
    ls_row_t xr[32]; /* a source's row extras, read once per paint (src only) */
    grid_tile_t *h = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    if (h) grid_blit(canvas, &ab.hg, h, AH_ART_X, AH_ART_Y - off, AH_WIN_H);
    ab_paint_pill(canvas, off);
    ab_span(&r0, &r1);
    if (r1 - r0 > 31) r1 = r0 + 31;
    for (r = r0; r <= r1; ++r) {
        void *rec = deque_at(ab.list, (unsigned)r);
        int y = ab_row_y(r) - off;
        if (ab_playing(rec)) playing |= 1u << (r - r0);
        if (ab.src) {
            ab.src->row(ab.src, rec, &xr[r - r0]);
            if (ab.st_dim && xr[r - r0].offline) dim |= 1u << (r - r0);
        }
        if (ab.press == r + 1 && !ab.select) az_fill_h(canvas, 0, y, y + ROW, AB_ROW_W, AB_PRESS, AH_WIN_H);
        if (ab.select && ab.mark[0]) {
            void *m = ab.mark[ab_is_sel(r)];
            int src[4], dst[4], top = y + (ROW - SG_MARK) / 2;
            if (top >= 0 && top + SG_MARK <= AH_WIN_H) {
                src[0] = 0, src[1] = 0, src[2] = SG_MARK, src[3] = SG_MARK;
                dst[0] = LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, dst[1] = top, dst[2] = SG_MARK, dst[3] = SG_MARK;
                canvas_draw_image(canvas, m, src, dst);
            }
        }
        az_fill_h(canvas, 0, y + ROW - 1, y + ROW, AB_ROW_W, AB_HAIR, AH_WIN_H);
        if (ab_more()) rowmenu_paint(canvas, &ab.rm, RM_MORE_RIGHT, 0, y, ROW, AH_WIN_H);
    }
    if (ab.src) { /* the marks */
        for (r = r0; r <= r1; ++r) {
            int g = ls_marks_w(&xr[r - r0]), y = ab_row_y(r) - off;
            if (g)
                ls_marks_draw(canvas, ab.win, &xr[r - r0], ab_text_end() - g, y + AB_TEXT_Y + AB_TEXT_H / 2, AH_WIN_H);
        }
    }
    for (
        pass = 0; pass < 3;
        ++pass) { /* numbers (the wave marker for the playing track), titles, the titles that cannot play (dim): one text style at a time */
        if (pass >= 2 && !ab.src) break;
        widget_prepare_text_style(pass == 0   ? ab.st_num
                                  : pass == 1 ? ab.st_title
                                              : (ab.st_dim ? ab.st_dim : ab.st_title),
                                  canvas);
        for (r = r0; r <= r1; ++r) {
            int y = ab_row_y(r) - off, d = (dim >> (r - r0)) & 1, g = ab.src ? ls_marks_w(&xr[r - r0]) : 0;
            if (pass == 0) {
                if (ab.wave && ((playing >> (r - r0)) & 1))
                    ab_paint_wave(canvas, r, y);
                else
                    ab_number(canvas, r, y);
            } else if (pass <= 2) {
                grid_tile_t *t;
                if (d != (pass == 2)) continue;
                t = ab_tile(r);
                g = g ? g + LS_MK_GAP : 0;
                if (t->xw != g) { /* the room the marks take changed: the title is cut again from the record */
                    t->xw = g;
                    grid_set(t, ab_text(deque_at(ab.list, (unsigned)r)), "", 0), t->fit = 0;
                }
                grid_text(canvas, t, 0, ab_tx(r), y + AB_TEXT_Y, ab_text_end() - ab_tx(r) - g, AB_TEXT_H, 0);
            }
        }
    }
}

static int ab_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = ab_off();
    (void)ctx;
    if (!canvas || !ab.view || !ab.g.tiles) return RET_OK;
    if (ab.count &&
        !ab_valid()) { /* another query replaced the stock list: nothing of it is read; the page reads it again when it is on top */
        if (!ab.stale_timer) ab.stale_timer = timer_add(ab_on_stale, (void *)0, 100);
        return RET_OK;
    }
    I(canvas, CANVAS_OY) += off;
    ab_paint(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The tint: the window's colour is the cover's tone under the gradient image of the asset (docs/modules/album-page.md "Cover tint"); the status bar takes the window's row 0
 * (Now Playing's rule, pod_bar_tint / pod_bar_black: the bar has one owner, the window that tinted it last) while the page is in front and tinted.
 */
static void ab_win_color(unsigned color) {
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    widget_set_style(ab.win, "normal:bg_color", v);
}

static void ab_bar_apply(void) {
    if (ab.barok && ab.fg && ab.tinted &&
        pod_bar_tint(ab.win, pod_shade(ab.tone, 0, AH_TINT_A_TOP, AH_TINT_A_BOT, AH_TINT_ROWS)))
        ab.bar = 1; /* a failed call keeps what the bar has (and owes) */
}

__attribute__((noinline)) static void ab_bar_black(void) {
    if (!ab.bar) return;
    ab.bar = 0;
    pod_bar_black(ab.win);
}

/* The tone as the page shows it: in Light Mode neutral (pal_tone: a chromatic dark tone cannot flip, and the page's white text does). ab_tone_raw is the tone as chosen,
 * for ab_relight when the mode changes while the page is open. */
static unsigned ab_tone_raw __attribute__((section(".scratch")));

static void ab_tint_set(unsigned tone) {
    unsigned color = pal_tone(tone);
    ab_tone_raw = tone;
    ab.tone = color & 0xffffff;
    ab.tinted = 1;
    ab_win_color(color);
    widget_invalidate_force(ab.win, (void *)0);
    ab_bar_apply();
}

/* The page shows a cover's tone now (patch/palette.c pal_cover_page: the Tinted wash leaves it alone). */
int ab_has_tone(void) { return ab.win && ab.tinted; }

void ab_relight(void) {
    if (ab.win && ab.tinted) ab_tint_set(ab_tone_raw); /* (patch/palette.c pal_apply) */
}

/* The page's tone: the tone cache, else the average colour of the cover file (one 168 px decode, box-averaged to one pixel), which is remembered. file: "file://<path>" (a source's own cover
 * file), NULL: the Cover Flow cache file of the page's key. */
static void ab_tint_cover(const char *file) {
    unsigned tone, px;
    char url[80];
    if (ab.tinted || !ab.cover_key) return;
    if (pod_tone_get(ab.cover_key, &tone)) {
        ab_tint_set(tone);
        return;
    }
    if (!file) file = cc_url(url, ab.cover_key);
    if (file && cc_decode(ab.win, file, 1, 1, 1, &px)) {
        tone = pod_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        pod_tone_put(ab.cover_key, tone);
        ab_tint_set(tone);
    }
}

/* ---------------------------------------------------------------------------
 * The cover: from the cache file, else from the cache worker (one job for this album), else the placeholder disc
 */
static void ab_build_end(void) {
    if (ab.build_timer) timer_remove(ab.build_timer);
    if (ab.dur_timer) timer_remove(ab.dur_timer);
    ab.build_timer = ab.dur_timer = 0;
    if (ab.hg.tiles)
        ab.hg.tiles[0].load = 0; /* (a source's cover is no longer polled: no spinner; the tick ends the timer) */
    if (ab.own || ab.lown) cc_build_stop();
    ab.own = ab.lown = 0;
}

/* The header's cover from what the cache has now. 1: a picture (decoded, the tint follows); 0: an empty "no art" marker, or no key (the placeholder, a black page); -1: no file. */
static int ab_cover_now(void) {
    grid_tile_t *t = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    char path[80], url[80];
    long size;
    if (!t || !ab.cover_key) return 0;
    ab_tint_cover((const char *)0); /* the tone cache may know the album without the file */
    if (cc_url(url, ab.cover_key)) {
        t->ckey = ab.cover_key;
        grid_art(&ab.hg, t);
        ab_tint_cover((const char *)0);
        return t->art == 1 ? 1 : 0;
    }
    size = cc_file_size(cc_path(path, sizeof path, ab.cover_key, ""));
    return size == 0 ? 0 : -1;
}

static int ab_on_cover(const void *unused);
static void ab_cp_arm(void);
static void ab_durations(void);

/* The header cover's spinner while a source's cover is asked for and polled (the shared poll, patch/libsrc.c ls_cover_poll): the 28 px frames (wf_spinL0..7) on the placeholder disc, turned and
 * redrawn by the poll's tick; it goes when the cover arrives, the source has none, or the poll gives up. */
static void ab_loading(grid_tile_t *t, int on) {
    t->load = on;
    if (on) grid_spin_open(&ab.hg, "wf_spinL", 28);
}
static int ab_cp_spin(void) {
    int n = grid_spin_turn(&ab.hg);
    if (ab.view) ab_redraw();
    return n;
}

/* A source's cover (src->cover, which asks for a file that is missing): the header's picture from the file it names (its own, not the Cover Flow cache key's), the same results as ab_cover_now:
 * 1 a picture (decoded, the tint follows), 0 none (the placeholder), -1 asked (polled every AB_COVER_MS). No cache worker. */
static int ab_cover_src(void) {
    grid_tile_t *t = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    char url[80];
    int r;
    if (!t) return 0;
    memcpy(url, "file://", 8);
    r = ab.src->cover(ab.src, deque_at(ab.srow_d, 0), ab.cover_key, url + 7, sizeof url - 7);
    if (r <= 0) return r ? 0 : -1;
    ab_tint_cover(url);
    grid_art_url(&ab.hg, t, url);
    return t->art == 1 ? 1 : 0;
}

/* The worker makes the album's file (CC_MISSING: one job, polled every AB_COVER_MS); nothing to build, no card, no space or another page's set held: the placeholder stays. */
static void ab_cover_build(void) {
    if (ab.own || ab.build_timer || !ab.count || !cc_build_open(1, CC_MISSING)) return;
    ab.own = 1;
    if (cc_build_add(cc_str(deque_at(ab.list, 0), REC_PATH), ab.cover_key) <= 0 || !cc_build_start()) {
        ab_build_end();
        return;
    }
    ab.build_timer = timer_add(ab_on_cover, (void *)0, AB_COVER_MS);
    if (!ab.build_timer) ab_build_end();
}

/* The page's cover, once per load: a decoded one stays. */
static void ab_cover(void) {
    grid_tile_t *t = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    int have;
    if (!t || t->art == 1) return;
    have = ab.src ? ab_cover_src() : ab_cover_now();
    if (have < 0) {
        if (!ab.src)
            ab_cover_build();
        else if (!ab.cp.on) {
            ab_loading(t, 1);
            ab_cp_arm();
        }
    }
    if (!ab.hg.placeholder && t->art != 1) grid_placeholder(&ab.hg);
}

static int ab_on_cover(const void *unused) {
    (void)unused;
    ab.build_timer = 0;
    if (!ab.view || !ab.own) return RET_OK;
    if (cc_build_done() >= cc_build_total()) { /* the worker is done: the file is there, or the marker */
        ab_build_end();
        ab_cover_now();
        if (!ab.hg.placeholder && ab.hg.tiles && grid_find(&ab.hg, 0)->art != 1) grid_placeholder(&ab.hg);
        ab_redraw();
        ab_durations(); /* the worker is free for the tracks' durations */
        return RET_OK;
    }
    ab.build_timer = timer_add(ab_on_cover, (void *)0, AB_COVER_MS);
    if (!ab.build_timer) ab_build_end();
    return RET_OK;
}

/* A source's cover was asked for: the file (or the empty marker) is there now, or the poll goes on. */
static void ab_cp_ask(void) {
    if (!ab.view || !ab.src) return;
    if (ab_cover_src() >= 0) {
        if (ab.hg.tiles) ab_loading(grid_find(&ab.hg, 0), 0);
        if (!ab.hg.placeholder && ab.hg.tiles && grid_find(&ab.hg, 0)->art != 1) grid_placeholder(&ab.hg);
        ab_redraw();
    } else
        ab_cp_arm();
}
/* The poll gave up: one last look (a file that landed since), then the placeholder, no spinner. */
static void ab_cp_giveup(void) {
    if (!ab.view || !ab.src) return;
    ab_cover_src();
    if (ab.hg.tiles) ab_loading(grid_find(&ab.hg, 0), 0);
    ab_redraw();
}
static void ab_cp_arm(void) { ls_cover_poll(&ab.cp, ab.win, ab_cp_ask, ab_cp_spin, ab_cp_giveup); }

/* ---------------------------------------------------------------------------
 * The album's length (docs/modules/album-page.md "Album length"): every track's seconds from the durations table (patch/durations.c); the missing ones are measured by the
 * cache worker when it is free (one set for this album, polled every AB_DUR_MS), and the duration is shown only when all are known.
 */
#define AB_DUR_MS 400

static int ab_on_dur(const void *unused);
static void ab_foot(void);

/* The footer under the last row, its own block at the number column's left edge (AB_NUM_X): "13 tracks, 49 minutes", AB_FOOT_GAP under the last row, only when the duration is
 * known; otherwise hidden and no band is kept. The content grows by AB_FOOT_GAP + AB_FOOT_TEXT_H + AB_FOOT_PAD when it appears; the scroll offset is untouched. */
static void ab_size(void);
static void ab_foot(void) {
    char dur[64], line[128];
    if (!ab.foot) return;
    if (ab.count && ab.dur) {
        dur_text(dur, sizeof dur, ab.dur);
        dur_subst(line, sizeof line, TR(ab.count == 1 ? "%d track, %s" : "%d tracks, %s"), (int)ab.count, dur,
                  (const char *)0);
        widget_set_text_utf8(ab.foot, line);
        widget_move(ab.foot, AB_NUM_X, ab_row_y((int)ab.count) + AB_FOOT_GAP);
        widget_resize(ab.foot, AB_VIEW_W - AB_NUM_X - AB_FOOT_R, AB_FOOT_TEXT_H);
    }
    widget_set_visible(ab.foot, ab.count != 0 && ab.dur != 0, 0); /* (never sensitive: the label takes no touch) */
    ab_size();
}

/* The album's total from the table, or its missing tracks queued for the worker. The line is rewritten when the total became known. */
static void ab_durations(void) {
    unsigned i, size, total = 0, miss = 0, bad = 0;
    int v;
    if (ab.src) { /* the source knows each track's length: the total when every one does (no table, no worker) */
        if (!ab.count || !ab.list || ab.dur) return;
        for (i = 0; i < ab.count; ++i) {
            v = (int)ab.src->seconds(ab.src, deque_at(ab.list, i));
            if (v <= 0) return;
            total += (unsigned)v;
        }
        ab.dur = total;
        ab_foot();
        ab_redraw();
        return;
    }
    if (!ab.count || !ab.list || ab.own || ab.lown || ab.dur_timer || ab.dur || !pod_card_mounted())
        return; /* (no card, or USB mode: no table, nothing measured) */
    if (!ab.lheld) {
        dur_acquire();
        ab.lheld = 1;
    }
    for (i = 0; i < ab.count; ++i) {
        v = dur_song(deque_at(ab.list, i), &size);
        if (v < 0)
            ++miss;
        else if (v == 0)
            ++bad; /* unreadable, or no file: no total (and nothing to measure) */
        else
            total += (unsigned)v;
    }
    if (bad) return;
    if (!miss) {
        ab.dur = total;
        ab_foot();
        ab_redraw();
        return;
    }
    if (ab.ltried || !cc_build_open(miss, CC_DURATIONS)) return; /* the worker is busy: no duration this time */
    ab.lown = 1, ab.ltried = 1;
    for (i = 0; i < ab.count; ++i) {
        void *rec = deque_at(ab.list, i);
        v = dur_song(rec, &size);
        if (v < 0 && cc_build_add_dur(cc_str(rec, REC_PATH), dur_key(cc_str(rec, REC_PATH)), size) < 0) {
            ab_build_end();
            return;
        }
    }
    if (!cc_build_start()) {
        ab_build_end();
        return;
    }
    ab.dur_timer = timer_add(ab_on_dur, (void *)0, AB_DUR_MS);
    if (!ab.dur_timer) ab_build_end();
}

/* The worker finished the album's files: their durations go into the table and the line is read again. */
static int ab_on_dur(const void *unused) {
    (void)unused;
    ab.dur_timer = 0;
    if (!ab.view || !ab.lown) return RET_OK;
    if (cc_build_done() >= cc_build_total()) {
        int n = cc_build_total(), i, k = 0;
        dur_ent_t *e = calloc(1, ((unsigned)(n > 0 ? n : 1) * sizeof *e));
        for (i = 0; e && i < n; ++i)
            if (cc_build_dur(i, &e[k].key, &e[k].size, &e[k].sec)) ++k;
        if (e) dur_merge(e, (unsigned)k);
        free(e);
        ab_build_end();
        ab_durations();
        return RET_OK;
    }
    ab.dur_timer = timer_add(ab_on_dur, (void *)0, AB_DUR_MS);
    if (!ab.dur_timer) ab_build_end();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The header's texts
 */
static const char *ab_artist(void) {
    return (const char *)ab.ci + (ab.cls == CLASS_14 ? CLASSINFO_ARTIST_14 : CLASSINFO_ARTIST);
}

/* "1959 . 8 tracks" when a track carries a year (the first that does), else "8 tracks". */
static void ab_meta(char *out, unsigned size) {
    int year = 0;
    unsigned o = 0, i;
    char count[48];
    for (i = 0; ab.list && i < ab.count && !year; ++i) {
        year = I(deque_at(ab.list, i), REC_YEAR);
        if (year < 1000 || year > 2999) year = 0;
    }
    pod_fmt(count, sizeof count, TR(ab.count == 1 ? "%d track" : "%d tracks"), (int)ab.count);
    if (year) o = (unsigned)snprintf(out, size, "%d \xc2\xb7 ", year);
    snprintf(out + o, size - o, "%s", count);
}

static void ab_texts(void) {
    char line[96];
    if (ab.src) { /* the album row's own texts (the title is REC_ALBUM, else REC_TITLE) */
        void *row = deque_at(ab.srow_d, 0);
        widget_set_text_utf8(ab.hname, *cc_str(row, REC_ALBUM) ? cc_str(row, REC_ALBUM) : cc_str(row, REC_TITLE));
        widget_set_text_utf8(ab.hartist, cc_str(row, REC_ARTIST));
    } else {
        widget_set_text_utf8(ab.hname, (const char *)ab.ci + CLASSINFO_ALBUM);
        widget_set_text_utf8(ab.hartist, ab_artist());
    }
    if (ab.wait)
        line[0] = 0; /* (the count is not known yet: not "0 tracks") */
    else
        ab_meta(line, sizeof line);
    widget_set_text_utf8(ab.hmeta, line);
}

/* The Play pill's text over its picture (cut at the window's edges by the scroll_view's clip, as the picture); the pair is centred by pod_pill_place (patch/common.c). */
static void ab_paint_pill(void *canvas, int off) {
    if (!ab.wait) pod_pill_paint(&ab.pill, canvas, AH_BTN_Y - off);
}

/* ---------------------------------------------------------------------------
 * Reading the stock list
 */
static void ab_size(void) {
    int h = ab.count ? ab_content() : AH_WIN_H;
    widget_resize(ab.view, AB_VIEW_W, h);
    widget_set_prop_int(ab.sv, "virtual_h", h);
}

/* While the tracks are on their way (src, LS_ST_LOADING) the page shows only what the tapped row told: the cover, the title and the artist, and the one spinner where the pills will be.
 * The Shuffle disc, the Play pill (the buttons, the glyph and the painted text) come with the tracks; the header does not move. */
static void ab_pills(int on) {
    if (!ab.src) return;
    ab_show(ab.btn_play, on);
    ab_show(ab.btn_shuffle, on);
    widget_set_visible(ab.pill.glyph, on, 0); /* (an insensitive image: taps reach btn_play) */
    if (ab.btn_more) { /* no tracks yet (loading, or none): the "..." keeps its place in the capsule but is dead, its one row (Download Album) has nothing to work on */
        widget_set_sensitive(ab.btn_more, on);
        if (!on && ab.vs.on) vs_menu(&ab.vs, 0, 0, 0, 0);
    }
}

/* The album's tracks again (the stock query of the class, the browsing record put back first) and the page rebuilt from them. */
static void ab_select_off(void);
static void ab_load(int keep) {
    int at = keep ? ab_off() : 0, st = LS_ST_READY;
    void *list = (void *)0;
    grid_drop(&ab.g);
    if (ab.src && ab.list) deque_destroy(ab.list); /* (our copy; the tiles above held texts, not records) */
    free(ab.sel);
    ab_build_end(); /* a set of an earlier read: the tracks may have changed */
    rowmenu_close(&ab.rm); /* (a menu's row is an index of the list that is read again) */
    ab.sel = (unsigned char *)0, ab.list = ab.first = (void *)0, ab.count = ab.nsel = 0, ab.press = ab.down = 0;
    ab.dur = 0, ab.ltried = 0, ab.wait = 0;
    if (ab.src) {
        ab.gen = ab.src->gen(ab.src); /* (before the read: a change during it is seen at the next tick) */
        ab.grows = ls_gen_rows(ab.src);
        list = ab.src->list(ab.src, LS_SONGS, deque_at(ab.srow_d, 0));
    } else {
        ab_classinfo();
        if (loadLocalClassList(ab.cls) > 0) list = *(void **)PDEQ_SHOWLIST;
    }
    if (list) ab.count = deque_size(list);
    if (ab.count) {
        ab.sel = calloc((ab.count + 7) / 8, 1);
        if (!ab.sel) ab.count = 0;
    }
    if (ab.count)
        ab.list = list, ab.first = deque_at(list, 0);
    else if (ab.src && list)
        deque_destroy(list);
    if (ab.src && !ab.count && !list && ab.src->state) st = ab.src->state(ab.src, LS_SONGS, deque_at(ab.srow_d, 0));
    ab.wait = st == LS_ST_LOADING;
    ab_show(ab.view,
            ab.count != 0 || ab.wait); /* (a source's album still loading: the header, with the spinner under it) */
    ab_show(ab.status, ab.count == 0 && !(ab.wait && ab.spin));
    if (!ab.count) widget_set_tr_text(ab.status, list ? "Not enough memory" : ls_empty_key(st, "No songs"));
    ls_spin(ab.spin, ab.wait && ab.spin);
    ab_pills(ab.count != 0);
    ab_foot(); /* (sizes the content: the footer's lines are part of it) */
    widget_set_prop_int(ab.sv, "yoffset", at < 0 ? 0 : at > ab_max_scroll() ? ab_max_scroll() : at);
    ab_texts();
    if (ab.count || ab.wait) ab_cover();
    ab_durations();
    ab_redraw();
}

/* A source's data moved (src->gen): the tracks are read again, the scroll position kept; select mode is left first (its marks are of the old list). */
static int ab_on_gen(const void *unused) {
    (void)unused;
    ab.gen_timer = 0;
    if (!ab.view || !ab.src) return RET_OK;
    if (ab.src->gen(ab.src) != ab.gen && !ab.down && !grid_moving(ab.sv) && pod_is_top(ab.win)) {
        if (ls_gen_rows(ab.src) ==
            ab.grows) { /* only a download's progress moved: the rows are the same, the visible ones are painted again */
            ab.gen = ab.src->gen(ab.src);
            ab_redraw();
        } else if (ab.rm.open)
            ab_redraw(); /* (the row menu stays: progress only redraws the rows' ring, the list is read once the menu has closed) */
        else {
            if (ab.select) ab_select_off();
            ab_load(1);
        }
    }
    ab.gen_timer = timer_add(ab_on_gen, (void *)0, LS_GEN_MS);
    return RET_OK;
}

/* Another query replaced the stock list under a page that is on top (a paint found it): read it again. A page behind another reads it when it comes back. */
static int ab_on_stale(const void *unused) {
    (void)unused;
    ab.stale_timer = 0;
    if (ab.view && ab.g.tiles && !ab_valid() && pod_is_top(ab.win)) ab_load(1);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Playing (patch/songops.c): the stock album page's Play all and track handlers; Now Playing opens the way the stock row handler opens it
 */
static void ab_play_at(int at, int how) {
    int r;
    if (!ab_valid()) {
        ab_load(1);
        return;
    }
    ab_classinfo(); /* loadSongList runs the class query again and keeps classinfo for the memory playback */
    na_arm(); /* the album order this page was opened from (patch/nextalbum.c) is the source of the queue the load below makes */
    r = so_play_src(ab.src, ab.cls, ab.list, at, how, pod_open_player);
    na_disarm();
    if (r ==
        -2) /* a DSD track that is not downloaded: the confirm, and the download if asked (the page's timer shows its progress) */
        ls_dsd_confirm(ab.src, ab.list, at);
}

static int ab_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ab.view && ab.count && !ab.select) ab_play_at(0, SO_IN_ORDER);
    return RET_OK;
}

static int ab_on_shuffle(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ab.view && ab.count && !ab.select) ab_play_at(-1, SO_SHUFFLE);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The select mode: the stock album page's controls, as glass (the all / none toggle, Add, Delete, Cancel in place of Back and the capsule)
 */
static void ab_selall_icon(void) {
    int all = ab.count &&
              ab.nsel == ab.count; /* the checked disc when every track is marked (stock has no pressed image for it) */
    widget_set_prop_str(ab.btn_selall, "style:normal:icon", all ? "ah_nav_sel" : "ah_nav_unsel");
    widget_set_prop_str(ab.btn_selall, "style:over:icon", all ? "ah_nav_sel" : "ah_nav_unsel");
    widget_set_prop_str(ab.btn_selall, "style:pressed:icon", all ? "ah_nav_sel" : "ah_nav_unsel_down");
}

static void ab_select(int on) {
    if (on == ab.select) return;
    ab.select = on;
    ab.nsel = 0;
    if (ab.sel) memset(ab.sel, 0, (ab.count + 7) / 8);
    ab.press = ab.down = 0;
    ab_show(ab.back, !on);
    ab_show(ab.btn_select,
            !on && !ab.src); /* (Add and Delete work on the stock selection: a source's page has no select mode yet) */
    ab_show(ab.np, !on);
    ab_show(ab.btn_selall, on);
    ab_show(ab.btn_add, on);
    ab_show(ab.btn_del, on);
    ab_show(ab.btn_cancel, on);
    widget_set_sensitive(ab.btn_play, !on); /* the header's buttons stay, dead */
    widget_set_sensitive(ab.btn_shuffle, !on);
    ab_selall_icon();
    ab_retext();
    ab_size();
    if (ab_off() > ab_max_scroll()) widget_set_prop_int(ab.sv, "yoffset", ab_max_scroll());
    ab_redraw();
}

static void ab_toggle(int i) {
    if (i < 0 || i >= (int)ab.count || !ab.sel) return;
    ab.sel[i >> 3] ^= (unsigned char)(1 << (i & 7));
    ab.nsel += ab_is_sel(i) ? 1 : (unsigned)-1;
    ab_selall_icon();
    ab_redraw();
}

static void ab_select_off(void) { ab_select(0); }

static int ab_on_select(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ab.view && ab.count) ab_select(1);
    return RET_OK;
}

static int ab_on_cancel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ab.select) ab_select(0);
    return RET_OK;
}

static int ab_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ab.select || !ab.sel) return RET_OK;
    if (ab.nsel < ab.count) { /* all, unless all are: then none */
        unsigned i;
        memset(ab.sel, 0, (ab.count + 7) / 8);
        for (i = 0; i < ab.count; ++i) ab.sel[i >> 3] |= (unsigned char)(1 << (i & 7));
        ab.nsel = ab.count;
    } else {
        memset(ab.sel, 0, (ab.count + 7) / 8);
        ab.nsel = 0;
    }
    ab_selall_icon();
    ab_redraw();
    return RET_OK;
}

static int ab_on_delete(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ab.select) return RET_OK;
    if (so_delete(ab.cls, ab.list, ab.count, ab.sel, ab.nsel, ab_valid())) {
        ab_select(0);
        ab_load(1);
    }
    return RET_OK;
}

static int ab_on_add(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ab.select) return RET_OK;
    if (so_add(ab.cls, ab.count, ab.sel, ab.nsel, ab_valid(), ab.title_save, &ab.picker) < 0) {
        ab_select(0);
        ab_load(1);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows (the Songs page's: DOWN remembers, ABORT forgets, UP within the drag threshold on the same row acts)
 */
static int ab_abs(int v) { return v < 0 ? -v : v; }

static int ab_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(ab.view, pt);
    return ab_at(pt[1]);
}

static void ab_set_press(int p) {
    if (ab.press == p) return;
    ab.press = p;
    ab_redraw();
}

/* The press or release is in a row's "..." zone. */
static int ab_in_zone(void *e) {
    int pt[2], x0;
    if (!ab_more()) return 0;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(ab.view, pt);
    x0 = rowmenu_zone_x(RM_MORE_RIGHT);
    return pt[0] >= x0 && pt[0] < x0 + RM_MORE_W;
}

/* Add to Playlist for one track (the menu's third row): the page's picker with a selection of that track alone. */
static void ab_add_one(int row) {
    int r;
    if (ab.src || !ab.sel || row < 0 || row >= (int)ab.count)
        return; /* (a source's third row is Download: the sheet never calls this) */
    ab.sel[row >> 3] |= (unsigned char)(1 << (row & 7));
    r = so_add(ab.cls, ab.count, ab.sel, 1, ab_valid(), ab.title_save, &ab.picker);
    memset(ab.sel, 0, (ab.count + 7) / 8); /* (the picker and the stock vector have their own copies) */
    if (r < 0) ab_load(1);
}

static void ab_open_menu(int a) {
    if (!ab_valid()) {
        ab_load(1);
        return;
    }
    rowmenu_open_src(&ab.rm, a, deque_at(ab.list, (unsigned)a), ab_add_one, ab.src);
}

static int ab_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    ab.down = ab.down_more = 0;
    if (!e || !ab.view || !ab.count || !ab_valid()) return RET_OK;
    a = ab_item_of(e);
    ab.down = a + 1, ab.down_x = I(e, PE_X), ab.down_y = I(e, PE_Y);
    ab.down_more = a >= 0 && ab_in_zone(e);
    if (!ab.select && !ab.down_more) ab_set_press(a + 1);
    return RET_OK;
}

static int ab_on_up(void *ctx, void *e) {
    int a = ab.down - 1, more = ab.down_more;
    (void)ctx;
    ab.down = ab.down_more = 0;
    ab_set_press(0);
    if (a < 0 || !e || !ab.view) return RET_OK;
    if (ab_abs(I(e, PE_X) - ab.down_x) < SC_DRAG_PX && ab_abs(I(e, PE_Y) - ab.down_y) < SC_DRAG_PX &&
        ab_item_of(e) == a) {
        if (ab.select)
            ab_toggle(a);
        else if (more) {
            if (ab_in_zone(e)) ab_open_menu(a); /* (a press that began on the "..." and ended off it does nothing) */
        } else
            ab_play_at(a, SO_KEEP);
    }
    return RET_OK;
}

static int ab_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ab.down = ab.down_more = 0;
    ab_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
/* A source's "...": the card opens and closes. */
static int ab_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    vs_menu(&ab.vs, !ab.vs.on, 0, 0, 0);
    return RET_OK;
}

static int ab_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    vs_menu(&ab.vs, 0, 0, 0, 0);
    return RET_OK;
}

/* The card's one row, Download Album: the source queues the page's tracks and toasts the outcome (LS_ACT_DOWNLOAD_ALL). */
static int ab_on_card(void *ctx, void *e) {
    (void)e;
    if ((int)(long)ctx != VS_SEARCH) return RET_OK;
    vs_menu(&ab.vs, 0, 0, 0, 0);
    if (ab.src && ab.list) ab.src->act(ab.src, ab.list, LS_ACT_DOWNLOAD_ALL);
    return RET_OK;
}

static int ab_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    navigator_back();
    return RET_OK;
}

static int ab_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ab.view || !ab.g.tiles) return RET_OK;
    ab.fg = 1;
    ab_bar_apply();
    if (ab.picker) { /* back from the stock playlist picker: its title and class put back, the add done (it changed the records it added), select mode over */
        ab.picker = 0;
        *(int *)G_CLASS_TYPE = ab.cls;
        memcpy((void *)NAV_TITLE, ab.title_save, sizeof ab.title_save);
        ab_select(0);
        ab_load(1);
    } else if (!ab_valid())
        ab_load(1);
    return RET_OK;
}

static int ab_on_bg(void *ctx, void *e) {
    ab.fg = 0;
    ab_bar_black();
    rowmenu_close(&ab.rm);
    return ab_on_abort(ctx, e);
}

static int ab_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    if (ab.stale_timer) timer_remove(ab.stale_timer);
    if (ab.gen_timer) timer_remove(ab.gen_timer);
    ls_cover_end(&ab.cp);
    ls_spin_end(ab.spin);
    ab_build_end();
    if (ab.lheld) dur_release();
    na_page_close();
    ab_bar_black();
    grid_free(&ab.g);
    grid_free(&ab.hg);
    for (i = 0; i < 2; ++i)
        if (ab.mark[i]) bitmap_destroy(ab.mark[i]);
    if (ab.wave) bitmap_destroy(ab.wave);
    free(ab.sel);
    rowmenu_free(&ab.rm);
    if (ab.src && ab.list) deque_destroy(ab.list);
    if (ab.src && ab.srow_d) deque_destroy(ab.srow_d);
    memset(&ab, 0, sizeof ab);
    return RET_OK;
}

/* Open the page on the album `row` of the list the caller has loaded (cc_open_album). 0 once the page is up; -1 when it was not tried (the caller opens the stock page); -2 when
 * it did not open and nothing is left of it (the caller opens the stock page): the tracks' query replaced the stock list, so the caller loads its album list again first. */
static int ab_open(const lib_src_t *src, unsigned cls, void *row) {
    unsigned key;
    int fresh;
    void *copy = (void *)0;
    if (ab.win || !row || (!src && I(row, REC_ID) == ID_ALL_SONGS))
        return -1; /* (a source's synthetic ids reach -2 too) */
    key = cc_album_key(row);
    if (src) { /* the page keeps its own copy of the row: it is the scope of every read of the tracks */
        copy = _create_deque("stSongInfo");
        if (!copy) return -1;
        deque_init(copy);
        _deque_push_back(copy, row); /* a copy, as the stock queries push rows */
    } else
        loadAlbumdetailList((int)cls, row);
    memset(&ab, 0, sizeof ab);
    ab.cover_key = key;
    if (src) {
        ab.src = src, ab.srow_d = copy;
        ab.cls = CLASS_ALBUM_TRACKS; /* (what Now Playing is opened with; a source ignores it) */
    } else {
        ab.cls = *(int *)CLASSINFO; /* what loadAlbumdetailList left: 0xff10 / 0xff11 / 0xff14 */
        memcpy(ab.ci, (void *)CLASSINFO, CLASSINFO_SIZE);
    }
    ab.win = window_open(AB_ASSET);
    if (!ab.win) {
        if (copy) deque_destroy(copy);
        memset(&ab, 0, sizeof ab);
        return -2;
    }
    na_page_open(key); /* the order the opener noted, when this album is in it */
    widget_on(ab.win, EVT_DESTROY, ab_on_destroy, (void *)0);
    ab.back = pod_bind(ab.win, "btn_return", ab_on_back, (void *)0);
    ab.np = pod_bind(ab.win, "btn_backtoplayer", pod_on_player, (void *)0);
    ab.btn_select = pod_bind(ab.win, "btn_select", ab_on_select, (void *)0);
    ab.btn_selall = pod_bind(ab.win, "btn_selall", ab_on_selall, (void *)0);
    ab.btn_add = pod_bind(ab.win, "sg_add", ab_on_add, (void *)0);
    ab.btn_del = pod_bind(ab.win, "sg_del", ab_on_delete, (void *)0);
    ab.btn_cancel = pod_bind(ab.win, "btn_cancel", ab_on_cancel, (void *)0);
    ab.btn_more = src ? pod_bind(ab.win, "btn_more", ab_on_more, (void *)0) : (void *)0;
    ab.btn_play = pod_bind(ab.win, "btn_play", ab_on_play, (void *)0);
    ab.btn_shuffle = pod_bind(ab.win, "btn_shuffle", ab_on_shuffle, (void *)0);
    ab.view = widget_lookup(ab.win, "view_grid", 1);
    ab.sv = widget_lookup(ab.win, "songs_scrollview", 1);
    ab.status = widget_lookup(ab.win, "label_status", 1);
    ab.st_num = widget_lookup(ab.win, "label_row_num", 1);
    ab.st_title = widget_lookup(ab.win, "label_row_title", 1);
    ab.st_dim = widget_lookup(ab.win, "label_row_dim", 1);
    ab.hname = widget_lookup(ab.win, "ab_title", 1);
    ab.hartist = widget_lookup(ab.win, "ab_artist", 1);
    ab.hmeta = widget_lookup(ab.win, "ab_meta", 1);
    ab.foot = widget_lookup(ab.win, "ab_foot", 1);
    ab.spin = widget_lookup(ab.win, "ab_spin", 1); /* (optional) */
    ab.pill.glyph = widget_lookup(ab.win, "ab_glyph", 1);
    ab.pill.ptext = widget_lookup(ab.win, "ab_play_text", 1);
    if (!ab.back || !ab.np || !ab.btn_select || !ab.btn_selall || !ab.btn_add || !ab.btn_del || !ab.btn_cancel ||
        !ab.btn_play || !ab.btn_shuffle || !ab.view || !ab.sv || !ab.status || !ab.st_num || !ab.st_title ||
        !ab.hname || !ab.hartist || !ab.hmeta || !ab.foot || !ab.pill.glyph || !ab.pill.ptext) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    if (src && (!ab.btn_more || vs_bind(&ab.vs, ab.win, ab_on_card, ab_on_scrim, VS_WITH_SEARCH))) {
        navigator_back();
        return -2;
    }
    ab.fg = 1;
    ab.barok = widget_on(ab.win, EVT_WINDOW_TO_FG, ab_on_fg, (void *)0) &&
               widget_on(ab.win, EVT_WINDOW_TO_BG, ab_on_bg, (void *)0);
    ab.mark[0] = pod_make_mark(ab.win, "unselect");
    ab.mark[1] = pod_make_mark(ab.win, "selected");
    if (!ab.mark[0] || !ab.mark[1])
        ab.mark[0] = ab.mark[1] =
            (void *)0; /* (one that did not decode is freed with the other at destroy: the pair is all or none) */
    ab.wave = ab_make_wave(ab.win);
    rowmenu_bind(&ab.rm, ab.win); /* the rows' "..." menu (optional: no widgets means no "...") */
    widget_on(ab.view, EVT_POINTER_DOWN, ab_on_down, (void *)0);
    widget_on(ab.view, EVT_POINTER_UP, ab_on_up, (void *)0);
    widget_on(ab.view, EVT_POINTER_ABORT, ab_on_abort, (void *)0);
    widget_on(ab.view, EVT_AFTER_PAINT, ab_on_paint, (void *)0);
    pod_pill_place(&ab.pill, AH_BTN_Y);
    if (src) { /* (no select mode on a source's page yet: the "..." takes Select's place) */
        ab_show(ab.btn_select, 0);
        ab_show(ab.btn_more, 1);
    }
    if (!grid_init(&ab.hg, ab.win, 1, AH_ART, AH_CORNER) || !grid_init(&ab.g, ab.win, GRID_TILES, LIST_ART, 0)) {
        grid_free(&ab.hg);
        grid_free(&ab.g);
        ab_show(ab.view, 0);
        ab_show(ab.status, 1);
        widget_set_tr_text(ab.status, "Not enough memory");
        return 0;
    }
    grid_shape(&ab.hg, AH_ART, AH_CORNER, 1); /* the corners are cut in the alpha: the tint shows behind them */
    grid_tile(&ab.hg, 0, 0, 0, &fresh);
    if (!src) *(int *)G_CLASS_TYPE = ab.cls; /* as albuminfo_page_init leaves it */
    ab_load(0);
    if (src) ab.gen_timer = timer_add(ab_on_gen, (void *)0, LS_GEN_MS);
    return 0;
}

/* The same page on the album `row` of a library source (patch/libsrc.h): its tracks from src->list(LS_SONGS, row), the cover from src->cover, the length from src->seconds, a tap or
 * Play / Shuffle through so_play_src, a re-read when src->gen moves. src NULL or &lib_stock is album_open(cls, row) (cls is the stock class of the row's list; a source ignores it).
 * The row is copied; the caller keeps its own. Returns as album_open (-1: not tried, -2: did not open). The rows' download state and the "..." sheet are src->row and src->act (ab_paint / ab_open_menu). */
int album_open_src(const lib_src_t *src, unsigned cls, void *row) {
    return ab_open(src == &lib_stock ? (const lib_src_t *)0 : src, cls, row);
}

int album_open(unsigned cls, void *row) {
    return album_open_src((const lib_src_t *)0, cls, row);
} /* (this also keeps album_open_src linked until a page calls it) */
