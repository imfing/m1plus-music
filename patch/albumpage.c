/* M1+ Music album page: an album's tracks, our own page in place of the stock albuminfo_page (docs/modules/album-page.md has the design and the geometry).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One page, ui/m1plus_album.bin (tools/pod_ui.py build_album_page): the stock list (list_view > scroll_view) holding ONE content view, view_grid, as the Songs page, which
 * reaches the window's top (450 px) with the glass controls floating over it (Back, a Select | Now Playing capsule; in select mode the all / none toggle, Add, Delete and
 * Cancel), so the rows scroll under them. The content view holds the header's widgets (the title, the artist and the "year . N tracks" line, the Shuffle disc and the
 * Play all pill with its glyph and text) and paints the rest itself in its EVT_AFTER_PAINT: the rounded cover, the tracks' numbers and titles, the press fill, the hairlines
 * and the select marks. The window is tinted from the cover as Now Playing is (pod_tone under the gradient image img_ah_tint), and so is the status bar (pod_bar_tint).
 *
 *   entry     album_open(class, row), called by cc_open_album (patch/covercache.c) with the album row of the list the caller loaded: loadAlbumdetailList(class, row) leaves
 *             the album's tracks in *pdeq_showlist and the browsing record in classinfo (class 0xff10 an album of the library, 0xff11 an album of an artist, 0xff14 a composer's),
 *             which the page snapshots and puts back before every query and play (another page's query overwrites it). Anything the page cannot show (the kill switch, the
 *             "All albums" card, a window that will not open) returns -1 and the caller opens the stock albuminfo_page.
 *   cover     the Cover Flow cache file of the album (/mnt/mmc/.m1plus/covers/<key>-168.jpg, the key of the album row), box-reduced to 160 px with its corners cut in the alpha;
 *             a file that is not there is made by the cache worker (one job, polled), an empty "no art" marker leaves the placeholder disc and a black page.
 *   tint      the tone cache (pod_tone_get) or the cover file's average colour; none for a page without a cover.
 *   rows      the stock row's number (position + 1) and title (gold when the track plays: the stock is_playing), 64 px, from the stock list while painting.
 *   play      Play all / Shuffle / a track: patch/songops.c, and Now Playing opens the way the stock album page's rows do (pod_open_player: with songerinfoflag set the
 *             pages above the Now Playing in the stack are popped first).
 * No hook; everything runs from the page's widgets and timers.
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
#include "songops.h"

#define ROW LIST_ROW_H

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *status;
    void *back, *np, *btn_select, *btn_selall, *btn_add, *btn_del, *btn_cancel, *btn_play, *btn_shuffle;
    void *st_num, *st_title,
        *st_gold; /* hidden labels whose styles are the number's, the title's and the playing title's */
    void *hname, *hartist, *hmeta, *glyph,
        *ptext; /* the header's labels, the Play all pill's glyph and its hidden text label (the text style and the translated text; the page paints it) */
    int ptx, ptw; /* where the pill's text is painted: x, and its width */
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
    unsigned stale_timer, build_timer;
    unsigned len_timer, len_at, len_sum,
        len_sig; /* the album's length: the next track to read, the seconds so far, the tracks' signature */
    int len_secs; /* the album's length in seconds, -1 while unknown (not all FLAC, a CUE track, a header that does not read) */
    int own; /* the page holds the cache worker's job set */
    unsigned tone; /* the window's colour as 0x00BBGGRR once tinted */
    int tinted;
    int fg; /* 1 from the page's start and EVT_WINDOW_TO_FG, 0 after EVT_WINDOW_TO_BG */
    int barok; /* both window events are registered: the status bar may be tinted */
    int bar; /* the status bar's bg_color is ours and must go back to black */
    void *mark[2]; /* the select marks: unselect, selected */
    grid_t hg; /* the cover: one tile, AH_ART px with AH_CORNER px corners cut in the alpha */
    grid_t g; /* the tracks' texts: the ring (a tile holds a title cut to its width; no cover) */
} ab __attribute__((section(".scratch")));

static int ab_on_stale(const void *unused);

static void ab_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int ab_off(void) { return ab.sv ? I(ab.sv, SC_YOFF) : 0; }
static void ab_redraw(void) { widget_invalidate_force(ab.sv, (void *)0); }

/* The index is of the stock list `list` as long as that list is still in *pdeq_showlist, as big, and starts with the same record. */
static int ab_valid(void) {
    void *cur = *(void **)PDEQ_SHOWLIST;
    return ab.list && cur == ab.list && deque_size(cur) == ab.count && (!ab.count || deque_at(cur, 0) == ab.first);
}

/* The browsing record put back (another page's query may have changed it). */
static void ab_classinfo(void) { memcpy((void *)CLASSINFO, ab.ci, CLASSINFO_SIZE); }

/* ---------------------------------------------------------------------------
 * Geometry: the header is AH_HDR_H high (the cover at AH_ART_Y, the controls' band over its first rows), then one ROW per track
 */
static int ab_row_y(int i) { return AH_HDR_H + i * ROW; }
static int ab_content(void) { return AH_HDR_H + (int)ab.count * ROW; }

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
    if (rect[1] >= 0 && rect[1] + AB_TEXT_H <= AH_WIN_H) canvas_draw_text_in_rect(canvas, w, n, rect);
}

static void ab_paint_pill(void *canvas, int off);

static void ab_paint(void *canvas) {
    int r0, r1, r, pass, off = ab_off();
    unsigned playing = 0; /* bit r - r0: the track plays (at most 32 rows are ever in view) */
    grid_tile_t *h = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    if (h) grid_blit(canvas, &ab.hg, h, AH_ART_X, AH_ART_Y - off, AH_WIN_H);
    ab_paint_pill(canvas, off);
    ab_span(&r0, &r1);
    if (r1 - r0 > 31) r1 = r0 + 31;
    for (r = r0; r <= r1; ++r) {
        void *rec = deque_at(ab.list, (unsigned)r);
        int y = ab_row_y(r) - off;
        if (is_playing(*(int *)G_CLASS_TYPE, I(rec, REC_CUE_START), (const char *)P(rec, REC_NAME),
                       (const char *)P(rec, REC_PATH)))
            playing |= 1u << (r - r0);
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
    }
    for (pass = 0; pass < 3; ++pass) { /* numbers, titles, the playing title: one text style at a time */
        widget_prepare_text_style(pass == 0 ? ab.st_num : pass == 1 ? ab.st_title : ab.st_gold, canvas);
        for (r = r0; r <= r1; ++r) {
            int y = ab_row_y(r) - off, gold = (playing >> (r - r0)) & 1;
            if (pass == 0)
                ab_number(canvas, r, y);
            else if (gold == (pass == 2))
                grid_text(canvas, ab_tile(r), 0, ab_tx(r), y + AB_TEXT_Y, AB_TEXT_END - ab_tx(r), AB_TEXT_H, AH_WIN_H);
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

static void ab_tint_set(unsigned tone) {
    ab.tone = tone & 0xffffff;
    ab.tinted = 1;
    ab_win_color(tone);
    widget_invalidate_force(ab.win, (void *)0);
    ab_bar_apply();
}

/* The page's tone: the tone cache, else the average colour of the cover file (one 168 px decode, box-averaged to one pixel), which is remembered. */
static void ab_tint_cover(void) {
    unsigned tone, px;
    char url[80];
    if (ab.tinted || !ab.cover_key) return;
    if (pod_tone_get(ab.cover_key, &tone)) {
        ab_tint_set(tone);
        return;
    }
    if (cc_url(url, ab.cover_key) && cc_decode(ab.win, url, 1, 1, 1, &px)) {
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
    ab.build_timer = 0;
    if (ab.own) cc_build_stop();
    ab.own = 0;
}

/* The header's cover from what the cache has now. 1: a picture (decoded, the tint follows); 0: an empty "no art" marker, or no key (the placeholder, a black page); -1: no file. */
static int ab_cover_now(void) {
    grid_tile_t *t = ab.hg.tiles ? grid_find(&ab.hg, 0) : (grid_tile_t *)0;
    char path[80], url[80];
    long size;
    if (!t || !ab.cover_key) return 0;
    ab_tint_cover(); /* the tone cache may know the album without the file */
    if (cc_url(url, ab.cover_key)) {
        t->ckey = ab.cover_key;
        grid_art(&ab.hg, t);
        ab_tint_cover();
        return t->art == 1 ? 1 : 0;
    }
    size = cc_file_size(cc_path(path, sizeof path, ab.cover_key, ""));
    return size == 0 ? 0 : -1;
}

static int ab_on_cover(const void *unused);

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
    have = ab_cover_now();
    if (have < 0) ab_cover_build();
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
        return RET_OK;
    }
    ab.build_timer = timer_add(ab_on_cover, (void *)0, AB_COVER_MS);
    if (!ab.build_timer) ab_build_end();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The header's texts
 */
static const char *ab_artist(void) {
    return (const char *)ab.ci + (ab.cls == CLASS_14 ? CLASSINFO_ARTIST_14 : CLASSINFO_ARTIST);
}

/* The album's length as "47 min", "1 h 12 min" or "2 h" (rounded to the minute, at least 1 min). */
static void ab_len_text(char *out, unsigned size, unsigned secs) {
    unsigned m = (secs + 30) / 60, o;
    char h[24];
    if (!m) m = 1;
    if (m < 60) {
        pod_fmt(out, size, TR("%d min"), (int)m);
        return;
    }
    pod_fmt(h, sizeof h, TR("%d h"), (int)(m / 60));
    o = (unsigned)snprintf(out, size, "%s", h);
    if (m % 60 && o + 1 < size) {
        out[o++] = ' ';
        pod_fmt(out + o, size - o, TR("%d min"), (int)(m % 60));
    }
}

/* "1959 . 8 tracks . 47 min" when a track carries a year (the first that does) and the length is known; the year and the length are left out when not. */
static void ab_meta(char *out, unsigned size) {
    int year = 0;
    unsigned o = 0, i;
    char count[48], len[48];
    for (i = 0; ab.list && i < ab.count && !year; ++i) {
        year = I(deque_at(ab.list, i), REC_YEAR);
        if (year < 1000 || year > 2999) year = 0;
    }
    pod_fmt(count, sizeof count, TR(ab.count == 1 ? "%d track" : "%d tracks"), (int)ab.count);
    if (year) o = (unsigned)snprintf(out, size, "%d \xc2\xb7 ", year);
    o += (unsigned)snprintf(out + o, size - o, "%s", count);
    if (ab.len_secs >= 0 && o < size) {
        ab_len_text(len, sizeof len, (unsigned)ab.len_secs);
        snprintf(out + o, size - o, " \xc2\xb7 %s", len);
    }
}

static void ab_texts(void) {
    char line[128];
    widget_set_text_utf8(ab.hname, (const char *)ab.ci + CLASSINFO_ALBUM);
    widget_set_text_utf8(ab.hartist, ab_artist());
    ab_meta(line, sizeof line);
    widget_set_text_utf8(ab.hmeta, line);
}

/* The Play all pill's glyph and text, centred as a pair for the page's language: the pill is a picture, the glyph an image over it and the text painted by the page; the pair's
 * width is the glyph, the gap and the measured text (the stock pill's numbers: AH_PILL_*). A text that cannot be measured, or does not fit, is centred as the English one. */
static void ab_pill(void) {
    const unsigned *text = widget_get_text(ab.ptext);
    float w = text && *text ? widget_measure_text(ab.ptext, text) : 0.0f;
    int tw = (int)(w + 0.999f), x;
    if (tw <= 0 || AH_PILL_GLYPH + AH_PILL_GAP + tw > AH_PLAY_W) tw = AB_PLAY_TEXT_W;
    x = AH_PLAY_X + (AH_PLAY_W - (AH_PILL_GLYPH + AH_PILL_GAP + tw)) / 2;
    widget_move(ab.glyph, x, AH_BTN_Y + (AH_BTN_H - AH_PILL_GLYPH) / 2);
    ab.ptx = x + AH_PILL_GLYPH + AH_PILL_GAP, ab.ptw = tw + AB_TEXT_SLACK;
}

/* The pill's text over its picture (inside the window only, as every text of the payload's pages). */
static void ab_paint_pill(void *canvas, int off) {
    const unsigned *text = widget_get_text(ab.ptext);
    unsigned n = 0;
    int rect[4];
    while (text && text[n]) ++n;
    rect[0] = ab.ptx, rect[1] = AH_BTN_Y + (AH_BTN_H - AB_TEXT_H) / 2 - off, rect[2] = ab.ptw, rect[3] = AB_TEXT_H;
    widget_prepare_text_style(ab.ptext, canvas);
    if (n && rect[1] >= 0 && rect[1] + AB_TEXT_H <= AH_WIN_H) canvas_draw_text_in_rect(canvas, text, n, rect);
}

/* ---------------------------------------------------------------------------
 * The album's length: the library has no track lengths (songtable's time / time_end are CUE offsets), so the page reads each track's FLAC STREAMINFO (total samples / sample
 * rate), AB_LEN_STEP files per AB_LEN_MS tick, and keeps the sum in a card cache keyed by the cover key and a signature of the tracks' paths. An album with a track that is not
 * a .flac, a CUE track or a header that does not read shows no length.
 */
#define AB_LEN_FILE CARD_DIR "/album-lengths"
#define AB_LEN_TMP CARD_DIR "/album-lengths.tmp"
static const char ab_len_magic[4] = {'M', 'A', 'L', '1'};

/* The cache file's first 4 bytes read from fd are its magic. */
static int ab_len_head(int fd) {
    char m[4];
    return read(fd, m, 4) == 4 && m[0] == ab_len_magic[0] && m[1] == ab_len_magic[1] && m[2] == ab_len_magic[2] &&
           m[3] == ab_len_magic[3];
}

/* hi:lo (36 bits) / d, bit by bit (no 64 bit division in the payload); the quotient fits 32 bits for d >= 16. */
static unsigned ab_div36(unsigned hi, unsigned lo, unsigned d) {
    unsigned r = 0, q = 0, bit;
    int i;
    for (i = 35; i >= 0; --i) {
        bit = i >= 32 ? (hi >> (i - 32)) & 1 : (lo >> i) & 1;
        r = (r << 1) | bit;
        q <<= 1;
        if (r >= d) r -= d, q |= 1;
    }
    return q;
}

/* The whole seconds of a FLAC file from its STREAMINFO (after an ID3v2 tag, if one leads), -1 when it does not read as one. */
static int ab_flac_secs(const char *path) {
    unsigned char b[26]; /* "fLaC", the block header, STREAMINFO up to the end of the total samples */
    unsigned at, rate, hi, lo;
    int fd = open(path, O_RDONLY, 0), n;
    if (fd < 0) return -1;
    n = read(fd, b, sizeof b);
    if (n >= 10 && b[0] == 'I' && b[1] == 'D' && b[2] == '3') {
        at = 10 + ((b[6] & 0x7fu) << 21 | (b[7] & 0x7fu) << 14 | (b[8] & 0x7fu) << 7 | (b[9] & 0x7fu)) +
             (b[5] & 0x10 ? 10 : 0);
        n = lseek(fd, (long)at, 0) == (long)at ? read(fd, b, sizeof b) : -1;
    }
    close(fd);
    if (n != (int)sizeof b || b[0] != 'f' || b[1] != 'L' || b[2] != 'a' || b[3] != 'C' || (b[4] & 0x7f) != 0 || b[5] ||
        b[6] || b[7] != 34)
        return -1;
    rate = (unsigned)b[18] << 12 | (unsigned)b[19] << 4 | b[20] >> 4;
    hi = b[21] & 0x0fu;
    lo = (unsigned)b[22] << 24 | (unsigned)b[23] << 16 | (unsigned)b[24] << 8 | b[25];
    if (rate < 16 || (!hi && !lo)) return -1;
    return (int)ab_div36(hi, lo, rate);
}

/* 1 when the path ends in .flac (any case). */
static int ab_is_flac(const char *p) {
    unsigned n = 0;
    while (p[n]) ++n;
    return n > 5 && strcasecmp(p + n - 5, ".flac") == 0;
}

/* The tracks' signature (FNV-1a over the paths, each ended by a 0); 0 when one is not a plain FLAC track (a CUE track, another format): no length then. */
static unsigned ab_len_sig(void) {
    unsigned h = 2166136261u, i;
    for (i = 0; i < ab.count; ++i) {
        void *r = deque_at(ab.list, i);
        const char *p = cc_str(r, REC_PATH);
        if (I(r, REC_CUE_START) || I(r, REC_CUE_END) || !ab_is_flac(p)) return 0;
        do h = (h ^ (unsigned char)*p) * 16777619u;
        while (*p++);
    }
    return h ? h : 1;
}

/* The cached length of the album with these tracks; -1 when the cache does not have it. */
static int ab_len_cached(unsigned sig) {
    unsigned rec[64 * 3], i;
    int fd = open(AB_LEN_FILE, O_RDONLY, 0), n, secs = -1;
    if (fd < 0) return -1;
    if (ab_len_head(fd))
        while (secs < 0 && (n = read(fd, rec, sizeof rec)) >= 12)
            for (i = 0; i + 3 <= (unsigned)n / 4; i += 3)
                if (rec[i] == ab.cover_key && rec[i + 1] == sig) {
                    secs = (int)rec[i + 2];
                    break;
                }
    close(fd);
    return secs;
}

/* The album's length first in the cache, its older entry and the oldest beyond AB_LEN_KEEP dropped. Best effort: a card that is not there or a failed write leaves the old file. */
static void ab_len_put(unsigned sig, unsigned secs) {
    unsigned head[4], *old = calloc(AB_LEN_KEEP - 1, 12), n = 0, i, k;
    int fd;
    if (!old) return;
    fd = open(AB_LEN_FILE, O_RDONLY, 0);
    if (fd >= 0) {
        if (ab_len_head(fd)) {
            int got = read(fd, old, (AB_LEN_KEEP - 1) * 12);
            n = got > 0 ? (unsigned)got / 12 : 0;
        }
        close(fd);
    }
    for (i = k = 0; i < n; ++i)
        if (old[i * 3] != ab.cover_key) {
            old[k * 3] = old[i * 3], old[k * 3 + 1] = old[i * 3 + 1], old[k * 3 + 2] = old[i * 3 + 2];
            ++k;
        }
    memcpy(head, ab_len_magic, 4);
    head[1] = ab.cover_key, head[2] = sig, head[3] = secs;
    pod_card_write(CARD_DIR, AB_LEN_FILE, AB_LEN_TMP, head, sizeof head, old, k * 12);
    free(old);
}

static void ab_len_stop(void) {
    if (ab.len_timer) timer_remove(ab.len_timer);
    ab.len_timer = 0;
}

static int ab_on_len(const void *unused) {
    unsigned end;
    int s;
    (void)unused;
    if (!ab.view || !ab.len_timer) return RET_OK;
    if (!ab_valid()) { /* another query replaced the list: its records are gone; the reload starts again */
        ab.len_timer = 0;
        return RET_OK;
    }
    end = ab.len_at + AB_LEN_STEP < ab.count ? ab.len_at + AB_LEN_STEP : ab.count;
    for (; ab.len_at < end; ++ab.len_at) {
        s = ab_flac_secs(cc_str(deque_at(ab.list, ab.len_at), REC_PATH));
        if (s < 0) {
            ab.len_timer = 0;
            return RET_OK;
        }
        ab.len_sum += (unsigned)s;
    }
    if (ab.len_at < ab.count) return RET_REPEAT;
    ab.len_timer = 0;
    ab.len_secs = (int)ab.len_sum;
    ab_len_put(ab.len_sig, ab.len_sum);
    ab_texts();
    return RET_OK;
}

/* The length of the album now listed: from the cache, else read in steps (the header line shows it when done). */
static void ab_len_start(void) {
    ab_len_stop();
    ab.len_secs = -1, ab.len_at = ab.len_sum = 0;
    ab.len_sig = ab.count ? ab_len_sig() : 0;
    if (!ab.len_sig) return;
    ab.len_secs = ab_len_cached(ab.len_sig);
    if (ab.len_secs < 0) ab.len_timer = timer_add(ab_on_len, (void *)0, AB_LEN_MS);
}

/* ---------------------------------------------------------------------------
 * Reading the stock list
 */
static void ab_size(void) {
    int h = ab.count ? ab_content() : AH_WIN_H;
    widget_resize(ab.view, AB_VIEW_W, h);
    widget_set_prop_int(ab.sv, "virtual_h", h);
}

/* The album's tracks again (the stock query of the class, the browsing record put back first) and the page rebuilt from them. */
static void ab_load(int keep) {
    int at = keep ? ab_off() : 0;
    void *list = (void *)0;
    grid_drop(&ab.g);
    free(ab.sel);
    ab.sel = (unsigned char *)0, ab.list = ab.first = (void *)0, ab.count = ab.nsel = 0, ab.press = ab.down = 0;
    ab_classinfo();
    if (loadLocalClassList(ab.cls) > 0) list = *(void **)PDEQ_SHOWLIST;
    if (list) ab.count = deque_size(list);
    if (ab.count) {
        ab.sel = calloc((ab.count + 7) / 8, 1);
        if (!ab.sel) ab.count = 0;
    }
    if (ab.count) ab.list = list, ab.first = deque_at(list, 0);
    ab_show(ab.view, ab.count != 0);
    ab_show(ab.status, ab.count == 0);
    if (!ab.count) widget_set_tr_text(ab.status, list ? "Not enough memory" : "No songs");
    ab_size();
    widget_set_prop_int(ab.sv, "yoffset", at < 0 ? 0 : at > ab_max_scroll() ? ab_max_scroll() : at);
    ab_len_start();
    ab_texts();
    if (ab.count) ab_cover();
    ab_redraw();
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
    if (!ab_valid()) {
        ab_load(1);
        return;
    }
    ab_classinfo(); /* loadSongList runs the class query again and keeps classinfo for the memory playback */
    so_play(ab.cls, ab.list, at, how, pod_open_player);
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
    ab_show(ab.btn_select, !on);
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

static int ab_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    ab.down = 0;
    if (!e || !ab.view || !ab.count || !ab_valid()) return RET_OK;
    a = ab_item_of(e);
    ab.down = a + 1, ab.down_x = I(e, PE_X), ab.down_y = I(e, PE_Y);
    if (!ab.select) ab_set_press(a + 1);
    return RET_OK;
}

static int ab_on_up(void *ctx, void *e) {
    int a = ab.down - 1;
    (void)ctx;
    ab.down = 0;
    ab_set_press(0);
    if (a < 0 || !e || !ab.view) return RET_OK;
    if (ab_abs(I(e, PE_X) - ab.down_x) < SC_DRAG_PX && ab_abs(I(e, PE_Y) - ab.down_y) < SC_DRAG_PX &&
        ab_item_of(e) == a) {
        if (ab.select)
            ab_toggle(a);
        else
            ab_play_at(a, SO_KEEP);
    }
    return RET_OK;
}

static int ab_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ab.down = 0;
    ab_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
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
    return ab_on_abort(ctx, e);
}

static int ab_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    if (ab.stale_timer) timer_remove(ab.stale_timer);
    ab_len_stop();
    ab_build_end();
    ab_bar_black();
    grid_free(&ab.g);
    grid_free(&ab.hg);
    for (i = 0; i < 2; ++i)
        if (ab.mark[i]) bitmap_destroy(ab.mark[i]);
    free(ab.sel);
    memset(&ab, 0, sizeof ab);
    return RET_OK;
}

/* Open the page on the album `row` of the list the caller has loaded (cc_open_album). 0 once the page is up; -1 when it was not tried (the caller opens the stock page); -2 when
 * it did not open and nothing is left of it (the caller opens the stock page): the tracks' query replaced the stock list, so the caller loads its album list again first. */
int album_open(unsigned cls, void *row) {
    unsigned key;
    int fresh;
    if (ab.win || !row || home_off() || I(row, REC_ID) == ID_ALL_SONGS) return -1;
    key = cc_album_key(row);
    loadAlbumdetailList((int)cls, row);
    memset(&ab, 0, sizeof ab);
    ab.cover_key = key;
    ab.cls = *(int *)CLASSINFO; /* what loadAlbumdetailList left: 0xff10 / 0xff11 / 0xff14 */
    memcpy(ab.ci, (void *)CLASSINFO, CLASSINFO_SIZE);
    ab.win = window_open(AB_ASSET);
    if (!ab.win) {
        memset(&ab, 0, sizeof ab);
        return -2;
    }
    widget_on(ab.win, EVT_DESTROY, ab_on_destroy, (void *)0);
    ab.back = pod_bind(ab.win, "btn_return", ab_on_back, (void *)0);
    ab.np = pod_bind(ab.win, "btn_backtoplayer", pod_on_player, (void *)0);
    ab.btn_select = pod_bind(ab.win, "btn_select", ab_on_select, (void *)0);
    ab.btn_selall = pod_bind(ab.win, "btn_selall", ab_on_selall, (void *)0);
    ab.btn_add = pod_bind(ab.win, "sg_add", ab_on_add, (void *)0);
    ab.btn_del = pod_bind(ab.win, "sg_del", ab_on_delete, (void *)0);
    ab.btn_cancel = pod_bind(ab.win, "btn_cancel", ab_on_cancel, (void *)0);
    ab.btn_play = pod_bind(ab.win, "btn_play", ab_on_play, (void *)0);
    ab.btn_shuffle = pod_bind(ab.win, "btn_shuffle", ab_on_shuffle, (void *)0);
    ab.view = widget_lookup(ab.win, "view_grid", 1);
    ab.sv = widget_lookup(ab.win, "songs_scrollview", 1);
    ab.status = widget_lookup(ab.win, "label_status", 1);
    ab.st_num = widget_lookup(ab.win, "label_row_num", 1);
    ab.st_title = widget_lookup(ab.win, "label_row_title", 1);
    ab.st_gold = widget_lookup(ab.win, "label_row_gold", 1);
    ab.hname = widget_lookup(ab.win, "ab_title", 1);
    ab.hartist = widget_lookup(ab.win, "ab_artist", 1);
    ab.hmeta = widget_lookup(ab.win, "ab_meta", 1);
    ab.glyph = widget_lookup(ab.win, "ab_glyph", 1);
    ab.ptext = widget_lookup(ab.win, "ab_play_text", 1);
    if (!ab.back || !ab.np || !ab.btn_select || !ab.btn_selall || !ab.btn_add || !ab.btn_del || !ab.btn_cancel ||
        !ab.btn_play || !ab.btn_shuffle || !ab.view || !ab.sv || !ab.status || !ab.st_num || !ab.st_title ||
        !ab.st_gold || !ab.hname || !ab.hartist || !ab.hmeta || !ab.glyph || !ab.ptext) {
        navigator_back(); /* an asset that is not ours */
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
    widget_on(ab.view, EVT_POINTER_DOWN, ab_on_down, (void *)0);
    widget_on(ab.view, EVT_POINTER_UP, ab_on_up, (void *)0);
    widget_on(ab.view, EVT_POINTER_ABORT, ab_on_abort, (void *)0);
    widget_on(ab.view, EVT_AFTER_PAINT, ab_on_paint, (void *)0);
    ab_pill();
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
    *(int *)G_CLASS_TYPE = ab.cls; /* as albuminfo_page_init leaves it */
    ab_load(0);
    return 0;
}
