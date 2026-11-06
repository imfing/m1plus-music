/* M1+ Music Radio: Now Playing for a station (docs/modules/radio.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Our own window, ui/m1plus_radionp.bin (tools/pod_ui.py build_radionp_page), laid out like Apple Music's radio page on Now Playing's numbers (tools/mod_nowplaying.py): the grabber (Back), a
 * square art card (the station's logo on a white card, else a grey card with the radio glyph) over a window tinted from the logo, the station's name with the stream's "Artist – Song" (or
 * its country, codec and bitrate; the state's words replace that line), the round "..." that opens the bottom sheet (Add to / Remove from My Stations, Station Info), a LIVE divider in place of the progress
 * bar and one large play / stop button. Everything it shows is read from the engine
 * (patch/radio.c) on a 500 ms page timer that does nothing while the page is covered or the screen is dark; the page owns no playback.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "i18n.h"
#include "covercache.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "pcjson.h"
#include "pcopml.h"
#include "pcnet.h"
#include "radio.h"

#define RN_ASSET "m1plus_radionp"

static struct {
    void *win, *title, *artist, *station, *info, *elapsed, *fav, *play, *live, *art, *art_ic, *more, *sh_scrim,
        *sh_card, *sh_row, *sh_ic, *sh_tx, *sh_hr, *sh_info, *sh_info_hr,
        *logo; /* logo: the station's picture, a bitmap RN_LOGO px square */
    int sheet;
    int logo_bad;
    char favicon[RD_FAV_MAX + 1];
    unsigned timer, seen;
    int fav_on, running, init;
    char c_title[200], c_artist[200], c_station[160], c_info[40], c_elapsed[16];
} rn __attribute__((section(".scratch")));

#define RN_CARD_LOGO 0xffffffffu /* the white card a logo lies on (pv_shrink's PNG ground is white) */
#define RN_CARD_GLYPH 0xff2e2c2cu /* #2C2C2E, the card of the radio glyph */

/* A style colour of a widget (widget_set_style "normal:bg_color"). */
static void rn_color(void *w, unsigned color) {
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    widget_set_style(w, "normal:bg_color", v);
    widget_invalidate_force(w, (void *)0);
}

/* The window's tone from a decoded logo: the average of its pixels that are neither white ground nor black (transparency); none of them, or none at all: Now Playing's neutral grey. The same
 * tone rule as Now Playing and the album page (pod_tone, patch/common.c). */
static unsigned rn_tone(const unsigned *px, unsigned n) {
    unsigned long r = 0, g = 0, b = 0;
    unsigned i, k = 0;
    for (i = 0; i < n; ++i) {
        unsigned c = px[i], cr = c & 255, cg = c >> 8 & 255, cb = c >> 16 & 255,
                 hi = cr > cg ? (cr > cb ? cr : cb) : (cg > cb ? cg : cb),
                 lo = cr < cg ? (cr < cb ? cr : cb) : (cg < cb ? cg : cb);
        if ((c >> 24) < 128 || lo > 232 || hi < 24) continue;
        r += cr, g += cg, b += cb, ++k;
    }
    if (k < n / 50 || !k) return NP_NEUTRAL;
    return pod_tone((unsigned)(r / k), (unsigned)(g / k), (unsigned)(b / k));
}

#define RN_LOGO 192 /* the logo's size: the largest the cache keeps (PV_SIZE) */

/* The station's logo in the art box: made by the engine's logo worker (radio.c), decoded here once; the glyph stays until then and when there is none. */
static void rn_logo(void) {
    const rd_list_t *l = rd_list();
    char fav[RD_FAV_MAX + 1], path[48], url[64];
    int st;
    fav[0] = 0;
    if (l->n && rd_at() < l->n) rd_favicon(rd_info(l, rd_at()), fav, sizeof fav);
    if (strcmp(fav, rn.favicon)) { /* another station: its logo, or the glyph */
        snprintf(rn.favicon, sizeof rn.favicon, "%s", fav);
        if (rn.logo) bitmap_destroy(rn.logo);
        rn.logo = (void *)0, rn.logo_bad = 0;
        rn_color(rn.win, pal_tone(NP_NEUTRAL));
        rn_color(rn.art, RN_CARD_GLYPH);
        widget_set_visible(rn.art_ic, 1, 0);
        widget_invalidate_force(rn.art, (void *)0);
    }
    if (!fav[0] || rn.logo || rn.logo_bad) return;
    st = rd_logo_file(rd_logo_hash(fav), path, sizeof path);
    if (st == 1 && pc_cover_ok(path)) {
        unsigned *px;
        void *b = bitmap_create_ex(RN_LOGO, RN_LOGO, RN_LOGO * 4, BITMAP_RGBA8888);
        snprintf(url, sizeof url, "file://%s", path);
        px = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
        if (px && bitmap_get_line_length(b) == RN_LOGO * 4 && cc_decode(rn.win, url, 1, RN_LOGO, 1, px)) {
            bitmap_unlock_buffer(b);
            rn.logo = b;
            rn_color(rn.win, pal_tone(rn_tone((const unsigned *)bitmap_lock_buffer_for_read(b), RN_LOGO * RN_LOGO)));
            bitmap_unlock_buffer(b);
            rn_color(rn.art, RN_CARD_LOGO);
            widget_set_visible(rn.art_ic, 0, 0);
            widget_invalidate_force(rn.art, (void *)0);
            return;
        }
        if (px) bitmap_unlock_buffer(b);
        if (b) bitmap_destroy(b);
        rn.logo_bad = 1;
    } else if (st == 0) {
        if (!rd_logo_running()) rd_logo_start(fav);
    } else
        rn.logo_bad = 1;
}

static int rn_on_art_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int src[4], dst[4];
    (void)ctx;
    if (!canvas || !rn.logo) return RET_OK;
    src[0] = src[1] = 0, src[2] = src[3] = RN_LOGO;
    dst[0] = dst[1] = (264 - RN_LOGO) / 2, dst[2] = dst[3] = RN_LOGO;
    canvas_draw_image(canvas, rn.logo, src, dst);
    return RET_OK;
}

/* A label's text, written only when it changed, so a scrolling one keeps its place. */
static void rn_set(void *w, char *cache, unsigned size, const char *s) {
    if (!w || (rn.init && !strcmp(cache, s))) return;
    snprintf(cache, size, "%s", s);
    widget_set_text_utf8(w, s);
}

static void rn_sheet_close(void);

static void rn_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static void rn_button(void *btn, const char *normal, const char *pressed) {
    static const char *const state[] = {"normal", "over", "focused", "disable"};
    char prop[40];
    int i;
    for (i = 0; i < 4; ++i) {
        snprintf(prop, sizeof prop, "style:%s:bg_image", state[i]);
        widget_set_prop_str(btn, prop, normal);
    }
    widget_set_prop_str(btn, "style:pressed:bg_image", pressed);
}

/* The station's line under its name: "Country · CODEC 128k" while it plays; the state's words replace it (no stream title yet: ICY metadata does not reach demo). */
static void rn_line(char *out, unsigned n, const rd_list_t *l, int at) {
    int st = rd_state();
    out[0] = 0;
    if (st == RD_ERROR)
        snprintf(out, n, rd_error()[0] ? "%s: %s" : "%s", TR("Can't play"), rd_error());
    else if (st == RD_CONNECTING)
        snprintf(out, n, "%s", TR("Connecting…"));
    else if (st == RD_PAUSED)
        snprintf(out, n, "%s", TR("Paused"));
    else if (st != RD_PLAYING)
        snprintf(out, n, "%s", TR("Stopped"));
    else if (l->n && at < l->n)
        rd_caption(rd_info(l, at), out, n);
}

static void rn_refresh(void) {
    const rd_list_t *l = rd_list();
    int at = rd_at(), running = rd_running() && rd_state() != RD_PAUSED; /* Paused shows play, as the mini bar does */
    const char *station = l->n && at < l->n ? rd_name(l, at) : "";
    char line[200];
    rn_line(line, sizeof line, l, at);
    rn_set(rn.title, rn.c_title, sizeof rn.c_title, station[0] ? station : TR("Radio"));
    rn_set(rn.artist, rn.c_artist, sizeof rn.c_artist, line);
    if (!rn.init || running != rn.running) {
        rn.running = running;
        rn_button(rn.play, running ? "rn_stop" : "rn_play", running ? "rn_stop_down" : "rn_play_down");
        widget_set_visible(rn.live, running, 0);
    }
    rn.init = 1;
    rn_logo();
}

static int rn_tick(const void *unused) {
    (void)unused;
    if (!rn.win) {
        rn.timer = 0;
        return RET_OK;
    }
    if (pod_screen_lit() && pod_is_top(rn.win)) rn_refresh();
    return RET_REPEAT;
}

int rn_open_if_active(void) { return rd_running() && rn_open() == 0; }

/* Hook 17: stock's on_backtoplayer_onclick, every stock page's Now Playing button; anything but an open Radio page runs stock. */
int rn_backtoplayer(void *ctx, void *e) {
    if (rn_open_if_active()) return RET_OK;
    return stock_backtoplayer_trampoline(ctx, e);
}

static int rn_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rn.sheet) {
        rn_sheet_close();
        return RET_OK;
    }
    navigator_back();
    return RET_OK;
}

static int rn_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (rd_state() == RD_PAUSED)
        rd_resume(); /* (no Wi-Fi: the Error "No Wi-Fi") */
    else if (rd_running())
        rd_stop();
    else if (rd_list()->n)
        rd_play(rd_list(), rd_at());
    rn_refresh();
    return RET_OK;
}

/* Previous / next station along the list the one playing was started from, round its ends. */
static void rn_step(int d) {
    const rd_list_t *l = rd_list();
    int n = l->n;
    if (!n) return;
    rd_play(l, ((rd_at() + d) % n + n) % n);
    rn_refresh();
}

static int rn_on_prev(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rn_step(-1);
    return RET_OK;
}

static int rn_on_next(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rn_step(1);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The sheet of the round "...": Add to / Remove from My Stations, Station Info
 */
static void rn_sheet_close(void) {
    rn.sheet = 0;
    rn_show(rn.sh_scrim, 0);
    rn_show(rn.sh_card, 0);
    rn_show(rn.sh_row, 0);
    rn_show(rn.sh_info, 0);
}

static int rn_on_more(void *ctx, void *e) {
    const rd_list_t *l = rd_list();
    int has;
    (void)ctx;
    (void)e;
    if (!l->n || rn.sheet) return RET_OK;
    has = rd_fav_has(rd_url(l, rd_at()));
    rn.sheet = 1;
    widget_set_tr_text(rn.sh_tx, has ? "Remove from My Stations" : "Add to My Stations");
    image_base_set_image(rn.sh_ic, has ? "pod_ic_rd_remove" : "pod_ic_rd_add");
    widget_set_visible(rn.sh_hr, 0, 0);
    widget_set_visible(rn.sh_info_hr, 1, 0);
    widget_move(rn.sh_row, 0, 0);
    widget_move(rn.sh_info, 0, PM_ROW_H);
    widget_move(rn.sh_card, 0, AH_WIN_H - 2 * PM_ROW_H);
    widget_resize(rn.sh_card, 320, 2 * PM_ROW_H);
    widget_set_prop_str(rn.sh_card, "style:normal:bg_image", "pc_sheet2");
    rn_show(rn.sh_row, 1);
    rn_show(rn.sh_info, 1);
    rn_show(rn.sh_scrim, 1);
    rn_show(rn.sh_card, 1);
    return RET_OK;
}

static int rn_on_sheet_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rn_sheet_close();
    return RET_OK;
}

static int rn_on_sheet_row(void *ctx, void *e) {
    int r;
    (void)ctx;
    (void)e;
    rn_sheet_close();
    if (!rd_list()->n) return RET_OK;
    r = rd_fav_toggle(rd_list(), rd_at());
    pod_toast(TR(r < 0 ? "Could not save My Stations" : r ? "Added to My Stations" : "Removed from My Stations"));
    return RET_OK;
}

/* Station Info: the sheet closes, the page of the station's address, logo and state opens over this one (Back returns here). */
static int rn_on_sheet_info(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rn_sheet_close();
    sinfo_open();
    return RET_OK;
}

/* ctx is the window the handler was bound to: a closed page is destroyed later, after rn_open may have opened its successor,
 * whose state this must not clear. */
static int rn_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != rn.win) return RET_OK;
    if (rn.timer) timer_remove(rn.timer);
    if (rn.logo) bitmap_destroy(rn.logo);
    memset(&rn, 0, sizeof rn);
    return RET_OK;
}

/* Radio's Now Playing: the station the engine has. 0 once it is up (or was), -1 when it could not open. */
int rn_open(void) {
    void *back;
    if (rn.win && pod_is_top(rn.win) && widget_is_window_opened(rn.win)) return 0;
    if (home_off()) return -1;
    if (rn.win) { /* closing (destroyed later) or under another window: let it go, its late EVT_DESTROY finds rn.win changed */
        if (widget_is_window_opened(rn.win)) window_close(rn.win);
        if (rn.timer) timer_remove(rn.timer);
        if (rn.logo) bitmap_destroy(rn.logo);
    }
    memset(&rn, 0, sizeof rn);
    rn.win = window_open(RN_ASSET);
    if (!rn.win) return -1;
    widget_on(rn.win, EVT_DESTROY, rn_on_destroy, rn.win);
    back = pod_bind(rn.win, "btn_return", rn_on_back, (void *)0);
    rn.play = pod_bind(rn.win, "btn_play", rn_on_play, (void *)0);
    rn.fav = widget_lookup(rn.win, "btn_fav", 1); /* (hidden: Add to / Remove from My Stations lives in the sheet) */
    rn.more = pod_bind(rn.win, "rn_more", rn_on_more, (void *)0);
    rn.sh_scrim = pod_bind(rn.win, "rd_sh_scrim", rn_on_sheet_scrim, (void *)0);
    rn.sh_card = widget_lookup(rn.win, "rd_sh_card", 1);
    rn.sh_row = pod_bind(rn.win, "rd_sh_add", rn_on_sheet_row, (void *)0);
    rn.sh_ic = widget_lookup(rn.win, "rd_sh_add_ic", 1);
    rn.sh_tx = widget_lookup(rn.win, "rd_sh_add_tx", 1);
    rn.sh_hr = widget_lookup(rn.win, "rd_sh_add_hr", 1);
    rn.sh_info = pod_bind(rn.win, "rd_sh_info", rn_on_sheet_info, (void *)0);
    rn.sh_info_hr = widget_lookup(rn.win, "rd_sh_info_hr", 1);
    if (!pod_bind(rn.win, "btn_prev", rn_on_prev, (void *)0) || !pod_bind(rn.win, "btn_next", rn_on_next, (void *)0))
        back = (void *)0;
    rn.title = widget_lookup(rn.win, "rn_title", 1);
    rn.artist = widget_lookup(rn.win, "rn_artist", 1);
    rn.station = widget_lookup(rn.win, "rn_station", 1);
    rn.info = widget_lookup(rn.win, "rn_info", 1);
    rn.elapsed = widget_lookup(rn.win, "rn_elapsed", 1);
    rn.live = widget_lookup(rn.win, "rn_live", 1);
    rn.art = widget_lookup(rn.win, "rn_art", 1);
    rn.art_ic = widget_lookup(rn.win, "rn_art_ic", 1);
    if (!back || !rn.play || !rn.fav || !rn.title || !rn.artist || !rn.station || !rn.info || !rn.elapsed || !rn.live ||
        !rn.art || !rn.art_ic || !rn.more || !rn.sh_scrim || !rn.sh_card || !rn.sh_row || !rn.sh_ic || !rn.sh_tx ||
        !rn.sh_hr || !rn.sh_info || !rn.sh_info_hr) {
        navigator_back(); /* an asset that is not ours */
        return -1;
    }
    rn.seen = rd_serial();
    widget_on(rn.art, EVT_AFTER_PAINT, rn_on_art_paint, (void *)0);
    rn_refresh();
    rn.timer = timer_add(rn_tick, (void *)0, 500);
    return 0;
}
