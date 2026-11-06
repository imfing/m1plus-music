/* Find Cover & Lyrics: our page over Now Playing (docs/modules/onlineart.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opened from the More sheet's page 2 (patch/playmore.c): the playing track's album and title are looked up online by ONE worker thread (patch/pcnet.c "Find Cover & Lyrics": the iTunes Search
 * API, then Deezer, the thumbnails one by one, then LRCLIB). The page never calls into the network: it asks pn_art / pn_art_fetch / pn_art_pick (UI thread: the guards, then the thread) and
 * afterwards only READS the status record from its own 250 ms timer, so AWTK is not touched from the thread.
 *
 * ui/m1plus_onlineart.bin is the Search page's frame: the stock navbar, the chip row (Covers, Lyrics; one is selected, a tap switches, both lookups run from the open), the line, and the list
 * (list_view > scroll_view holding ONE content view, oa_view, that this file paints: the cover thumbnails of the Covers tab, the candidate rows of the Lyrics tab). The window has three modes:
 *   0  the tabs;
 *   1  a cover's confirmation (a tap on a thumbnail): the larger picture (downloaded by pn_art_fetch, decoded to OA_DC_SIDE px), the album, the artist, the source and the pill; nothing is written until
 *      the pill (pn_art_pick); then back to the grid with that thumbnail marked current;
 *   2  a lyrics candidate (a tap on a row): its text, the [mm:ss.xx] tags removed and the lines wrapped, in the list; the pill writes <track>.lrc (pn_lyr_save); then back to the rows with that one marked saved.
 * Back (btn_return) leaves a mode 1 or 2 for 0 and, from 0, the page; hidden widgets are visible=false and sensitive=false.
 *
 * Content coordinates (the view is 320 wide): Covers: three 88 px thumbnails a row (x 16, 12 px apart) from y 8, the row pitch 98; Lyrics: rows SE_ROW_H high (the Search page's: title, grey line, the
 * Synced / Saved badge on the right of the title).
 */
#include "offsets.inc"
#include "stock.h"
#include "azlist.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "home.h"
#include "i18n.h"
#include "podcasts.h"
#include "pcjson.h"
#include "pcnet.h"
#include "pcdetail.h"
#include "search.h"

#define I(w, off) (*(int *)((char *)(w) + (off)))

#define OA_TILE 88
#define OA_GAP 12
#define OA_X0 16
#define OA_Y0 8
#define OA_PITCH 98 /* row to row */
#define OA_COLS 3
#define OA_BOTTOM 12 /* air under the last row */
#define OA_FRAME_RGB 0xffffffffu /* the current cover's frame */
#define OA_BADGE_RGB 0xff2e2c2cu /* #2C2C2E: the Synced badge (the Search page's line colour) */
#define OA_BADGE_ON_RGB 0xffeae5e5u /* #E5E5EA: the Saved badge (the selected chip's pill) */
#define OA_BADGE_H 18
#define OA_BADGE_PAD 7 /* either side of a badge's text */
#define OA_ROW_X 16 /* a row's text starts here and ends at OA_ROW_END */
#define OA_ROW_END 304
#define OA_TICK_MS 250
#define OA_PATH 400
#define OA_DC_SIDE 240 /* the confirmation's cover (oa_dc_art, container x 40 y 8) */
#define OA_DC_R 8
/* The empty / failed state's block (tools/pod_ui.py OA_ES_*: the same numbers), window y: the glyph, the title (oa_status), the explanation (two lines) and the Try Again pill, centred on OA_ES_CENTRE as a whole */
#define OA_ES_CENTRE 260
#define OA_ES_ICON 40
#define OA_ES_ICON_GAP 14
#define OA_ES_TITLE_H 26
#define OA_ES_TITLE_GAP 4
#define OA_ES_TEXT_H 40
#define OA_ES_PILL_GAP 18
#define OA_ES_PILL_H 36
#define OA_ES_PILL_W 168
#define OA_ES_TEXT_W 260
#define OA_LY_PITCH 24 /* the lyrics detail's lines */
#define OA_LY_X 16
#define OA_LY_W 288
#define OA_LY_TOP 8
#define OA_LY_GAP 12 /* a blank line of the text */
#define OA_LY_H 300 /* the text lies in the list's top 300 px; the pill is below */
#define OA_LY_WIDE 14000 /* wide chars kept of a text */
#define OA_LY_LINES 700 /* wrapped lines kept */
#define OA_LY_SRC 400 /* wide chars of one text line (a longer one ends there) */
#define OA_LY_WRAP \
    40 /* lines one text line may take: 400 chars of the widest glyph (about 20 px) need 28, so the wrapper never closes a line with an ellipsis */

typedef struct {
    int off; /* the line's first char in oa.lw */
    short len, y; /* chars; top in content coordinates */
} oa_ln_t;

static struct {
    void *win, *chips, *chl, *sep, *list, *sv, *view, *l_status, *l_hint, *l_head, *l_sub, *lpill, *dc, *dc_art,
        *l_name, *l_artist, *l_source, *pill, *es_icon, *es_text, *retry;
    void *st_title, *st_sub, *st_chip, *st_chip_on, *st_badge, *st_badge_on, *st_line;
    unsigned timer, gen;
    grid_t g, gl, gd; /* thumbnails; the candidate rows' texts; the confirmation's cover */
    char artist[256], album[256], title[256]; /* (the worker's copies are cut on a character boundary) */
    char dir[OA_PATH], lrc[OA_PATH];
    unsigned secs;
    int mode, chip, off[2]; /* 0 tabs, 1 cover, 2 lyrics; the tab; each tab's scroll offset while a detail is up */
    int chip_x[3], chip_len[2], chip_down;
    unsigned chip_text[2][24];
    int bw; /* the badges' width */
    int want; /* the parts (PN_PART_*) whose lookup has not started: a download is being paused, or another job ends */
    int loaded; /* thumbnails turned into tiles so far */
    int pend; /* a tapped cover waiting for the worker to end (its larger picture, or the save): its index, -1 none */
    int di; /* the detail's candidate (a cover or a lyrics row) */
    int fetching, fpend; /* the larger picture is downloading; it waits for the worker to end */
    int ready; /* the confirmation's picture is decoded */
    int saving, picked; /* the pick runs; the current cover (index, -1 none) */
    int hint_code; /* the fetch's or the pick's failure (PN_*), 0 none */
    unsigned saved; /* lyrics rows (display index) written as the .lrc */
    int save_failed, exists; /* the lyrics could not be written; the .lrc is already there */
    int replace; /* the album already has a picked cover */
    int fail[2]; /* the covers' / the lyrics' lookup could not start: its PN_* */
    int down, down_x, down_y, press;
    int drop; /* the larger picture is to be removed once no worker runs */
    unsigned *lw; /* the lyrics detail's text (wide), its lines, the content height */
    oa_ln_t *ln;
    int nln, lh;
} oa __attribute__((section(".scratch")));

static const char *oa_word(int code) {
    switch (code) {
    case PN_NOWIFI:
        return TR("No Wi-Fi");
    case PN_NOCLOCK:
        return TR("Set the date first");
    case PN_NOCERT:
        return TR("Certificates missing");
    case PN_CERT:
        return TR("Certificate problem");
    case PN_HTTP:
    case PN_GONE:
    case PN_NOTFEED:
        return TR("Server error");
    case PN_STORAGE:
        return TR("Storage unavailable");
    case PN_MEM:
        return TR("Not enough memory");
    default:
        return TR("Can't connect");
    }
}

static void oa_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int oa_abs(int v) { return v < 0 ? -v : v; }
static int oa_off(void) { return oa.sv ? I(oa.sv, SC_YOFF) : 0; }
static void oa_redraw(void) { widget_invalidate_force(oa.sv, (void *)0); }

/* The tile of cover i, made on first use. */
static grid_tile_t *oa_tile(int i) {
    int fresh;
    grid_tile_t *t = grid_tile(&oa.g, i, 0, PN_ART_MAX - 1, &fresh);
    if (fresh) grid_set(t, "", "", 0);
    return t;
}

/* "m:ss" (a length in seconds). */
static void oa_clock(char *out, unsigned size, unsigned secs) { snprintf(out, size, "%u:%02u", secs / 60, secs % 60); }

/* The grey line of a candidate: "Artist · Album · 3:45" (parts that are empty left out). */
static void oa_lyr_sub(char *out, unsigned size, const pn_lyr_t *c) {
    char clk[16];
    unsigned o = 0;
    const char *part[3];
    int p;
    oa_clock(clk, sizeof clk, c->secs);
    part[0] = c->artist, part[1] = c->album, part[2] = c->secs ? clk : "";
    out[0] = 0;
    for (p = 0; p < 3; ++p) {
        if (!part[p][0]) continue;
        o += (unsigned)snprintf(out + o, o < size ? size - o : 0, "%s%s", o ? " \xc2\xb7 " : "", part[p]);
        if (o >= size) break;
    }
}

/* The candidate row r's tile: the title and the grey line, made on first use. */
static grid_tile_t *oa_ltile(int r) {
    int fresh;
    grid_tile_t *t = grid_tile(&oa.gl, r, 0, PN_LYR_MAX - 1, &fresh);
    if (fresh) {
        const pn_lyr_t *c = pn_lyr_get(r);
        char sub[200];
        sub[0] = 0;
        if (c) oa_lyr_sub(sub, sizeof sub, c);
        grid_set(t, c ? c->title : "", sub, 0);
    }
    return t;
}

/* One thumbnail per tick: the file the worker wrote, decoded into its tile (a failed one is the placeholder). */
static void oa_load_one(void) {
    char path[120], url[130];
    int n = pn_art_count(), i = oa.loaded, st;
    if (pn_art_state() == PN_A_COVERS || i >= n || i >= PN_ART_MAX) return;
    if (grid_moving(oa.sv)) return; /* nothing is decoded while the list moves; the next tick asks again */
    st = pn_art_thumb_state(i);
    if (st == 0 && pn_job_busy()) return; /* the worker has not come to it yet */
    if (st == 1 && pn_art_thumb(i, path, sizeof path)) {
        snprintf(url, sizeof url, "file://%s", path);
        grid_art_url(&oa.g, oa_tile(i), url);
    } else
        grid_art_url(&oa.g, oa_tile(i), (const char *)0); /* it could not be had: the placeholder */
    ++oa.loaded;
    oa_redraw();
}

static int oa_lrc_exists(void) {
    char p[OA_PATH];
    unsigned n = 0;
    while (oa.lrc[n]) ++n;
    if (n + 1 > sizeof p) return 0;
    memcpy(p, oa.lrc, n + 1);
    if (!access(p, F_OK)) return 1;
    if (n >= 4) memcpy(p + n - 4, ".LRC", 4);
    return access(p, F_OK) == 0;
}

/* ---------------------------------------------------------------------------
 * The lookup's state on the page
 */
static int oa_covers_ready(void) {
    return !oa.fail[0] && !(oa.want & PN_PART_COVERS) && pn_art_state() != PN_A_COVERS && pn_art_state() != PN_A_IDLE &&
           pn_art_code() == PN_OK;
}

static int oa_rows_ready(void) {
    return !oa.fail[1] && !(oa.want & PN_PART_LYRICS) && pn_lyr_state() == 1 && pn_lyr_code() == PN_OK;
}

/* What the empty list says: a glyph (an image of the theme, "" for none), a title, an explanation under it and whether the Try Again pill is offered. */
typedef struct {
    const char *glyph, *title, *text;
    int retry;
} oa_es_t;

/* A lookup that failed (a PN_* code) on the Covers or the Lyrics tab. Every failure that another try can cure offers the pill. */
static void oa_es_fail(oa_es_t *s, int code, int lyr) {
    s->retry = 1;
    switch (code) {
    case PN_OVERLOAD:
        s->glyph = "pod_es_timer";
        s->title = lyr ? TR("Lyrics Service Busy") : TR("Cover Service Busy");
        s->text = lyr ? TR("LRCLIB is under heavy load. Try again in a moment.")
                      : TR("iTunes and Deezer are busy. Try again in a moment.");
        break;
    case PN_NOWIFI:
        s->glyph = "pod_es_wifi", s->title = TR("No Wi-Fi"), s->text = TR("Turn on Wi-Fi to search online.");
        break;
    case PN_NOCLOCK:
        s->glyph = "pod_es_calendar", s->title = TR("Set the date first"),
        s->text = TR("Secure connections need the right date.");
        break;
    case PN_NOCERT:
        s->glyph = "pod_es_lock", s->title = TR("Certificates missing"),
        s->text = TR("This device has no certificate bundle."), s->retry = 0;
        break;
    case PN_CERT:
        s->glyph = "pod_es_lock", s->title = TR("Certificate problem"),
        s->text = TR("The server's certificate was not accepted.");
        break;
    case PN_HTTP:
    case PN_GONE:
    case PN_NOTFEED:
        s->glyph = "pod_es_info", s->title = TR("Server error"),
        s->text = TR("The server could not answer. Try again later.");
        break;
    case PN_STORAGE:
        s->glyph = "pod_es_card", s->title = TR("Storage unavailable"), s->text = TR("The SD card could not be used.");
        break;
    case PN_MEM:
        s->glyph = "pod_es_drive", s->title = TR("Not enough memory"),
        s->text = TR("There is not enough memory to search.");
        break;
    default:
        s->glyph = "pod_es_plug", s->title = TR("Can't connect"), s->text = TR("Check your Wi-Fi connection.");
        break;
    }
}

/* The selected tab's state over the empty list; 0 when the tab has content (or nothing to say). */
static int oa_es_state(oa_es_t *s) {
    int lyr = oa.chip == 1, code;
    s->glyph = s->title = s->text = "";
    s->retry = 0;
    if (oa.fail[lyr]) {
        oa_es_fail(s, oa.fail[lyr], lyr);
        return 1;
    }
    if (!lyr) {
        int astate = pn_art_state();
        code = pn_art_code();
        if ((oa.want & PN_PART_COVERS) || astate == PN_A_COVERS || astate == PN_A_IDLE) {
            s->title = TR("Searching…");
            return 1;
        }
        if (code == PN_CANCELLED) return 0;
        if (code != PN_OK) {
            oa_es_fail(s, code, 0);
            return 1;
        }
        if (pn_art_count() > 0) return 0;
        s->glyph = "pod_es_image", s->title = TR("No Covers Found"),
        s->text = TR("Nothing on iTunes or Deezer for this album.");
        return 1;
    }
    if ((oa.want & PN_PART_LYRICS) || pn_lyr_state() == 0) {
        if (!(oa.want & PN_PART_LYRICS) && !pn_job_busy()) return 0;
        s->title = TR("Searching…");
        return 1;
    }
    code = pn_lyr_code();
    if (code == PN_OK || code == PN_CANCELLED) return 0;
    if (code == PN_NOLYRICS) {
        s->glyph = "pod_es_music", s->title = TR("No Lyrics Found"),
        s->text = TR("LRCLIB has no lyrics for this song.");
        return 1;
    }
    oa_es_fail(s, code, 1);
    return 1;
}

static void oa_vis(void *w, int on) {
    if (w) widget_set_visible(w, on, 0);
}

/* The block on the page: the parts it has, stacked and centred on OA_ES_CENTRE (the pill is the only one that takes touches). s NULL: nothing. */
static void oa_es_apply(const oa_es_t *s) {
    int g = s && s->glyph[0], t = s && s->text[0], p = s && s->retry, y;
    if (!s) {
        oa_vis(oa.l_status, 0);
        oa_vis(oa.es_icon, 0);
        oa_vis(oa.es_text, 0);
        oa_show(oa.retry, 0);
        return;
    }
    y = OA_ES_CENTRE - ((g ? OA_ES_ICON + OA_ES_ICON_GAP : 0) + OA_ES_TITLE_H +
                        (t ? OA_ES_TITLE_GAP + OA_ES_TEXT_H : 0) + (p ? OA_ES_PILL_GAP + OA_ES_PILL_H : 0)) /
                           2;
    if (g) {
        image_base_set_image(oa.es_icon, s->glyph);
        widget_move(oa.es_icon, (320 - OA_ES_ICON) / 2, y);
        y += OA_ES_ICON + OA_ES_ICON_GAP;
    }
    widget_set_text_utf8(oa.l_status, s->title);
    widget_move(oa.l_status, 16, y);
    y += OA_ES_TITLE_H;
    if (t) {
        y += OA_ES_TITLE_GAP;
        widget_set_text_utf8(oa.es_text, s->text);
        widget_move(oa.es_text, (320 - OA_ES_TEXT_W) / 2, y);
        y += OA_ES_TEXT_H;
    }
    if (p) {
        widget_set_text_utf8(oa.retry, TR("Try Again"));
        widget_move(oa.retry, (320 - OA_ES_PILL_W) / 2, y + OA_ES_PILL_GAP);
    }
    oa_vis(oa.es_icon, g);
    oa_vis(oa.l_status, 1);
    oa_vis(oa.es_text, t);
    oa_show(oa.retry, p);
}

/* The content view's height for what it shows, the list told so, the offset kept inside. */
static void oa_resize(void) {
    int h, off = oa_off(), rows;
    if (oa.mode == 2)
        h = oa.lh + (SE_LIST_H - OA_LY_H);
    else if (oa.chip == 0) {
        rows = oa_covers_ready() ? (pn_art_count() + OA_COLS - 1) / OA_COLS : 0;
        h = OA_Y0 + rows * OA_PITCH + OA_BOTTOM;
    } else
        h = (oa_rows_ready() ? pn_lyr_count() : 0) * SE_ROW_H + OA_BOTTOM;
    if (h < SE_LIST_H) h = SE_LIST_H;
    widget_resize(oa.view, 320, h);
    widget_set_prop_int(oa.sv, "virtual_h", h);
    if (off > h - SE_LIST_H) widget_set_prop_int(oa.sv, "yoffset", h - SE_LIST_H);
}

/* The widgets of the mode. */
static void oa_modes(void) {
    int m = oa.mode;
    oa_show(oa.chips, m == 0);
    oa_show(oa.sep, m != 1);
    oa_show(oa.list, m != 1);
    oa_show(oa.dc, m == 1);
    oa_show(oa.l_head, m == 2);
    oa_show(oa.l_sub, m == 2);
    if (m != 2) oa_show(oa.lpill, 0);
    if (m != 0) oa_es_apply((const oa_es_t *)0);
}

/* Everything the worker's record says, put on the page's labels and pills. */
static void oa_sync(void) {
    if (oa.mode == 0) {
        oa_es_t es;
        oa_es_apply(oa_es_state(&es) ? &es : (const oa_es_t *)0);
        oa_resize();
    } else if (oa.mode == 1) {
        const char *hint = oa.saving || (oa.pend >= 0 && oa.ready) ? "" : oa.hint_code ? oa_word(oa.hint_code) : "";
        int on = oa.ready;
        widget_set_text_utf8(oa.l_hint, hint);
        oa_show(oa.l_hint, *hint != 0);
        widget_set_text_utf8(oa.pill, oa.saving || oa.pend >= 0 ? TR("Saving…")
                                      : oa.replace              ? TR("Replace Cover")
                                                                : TR("Use This Cover"));
        oa_show(oa.pill, on);
    } else {
        const char *err = oa.save_failed ? oa_word(PN_STORAGE) : (const char *)0;
        if (err) widget_set_text_utf8(oa.l_sub, err);
        widget_set_text_utf8(oa.lpill, oa.exists ? TR("Replace Lyrics") : TR("Save Lyrics"));
        oa_show(oa.lpill, oa.lw != (unsigned *)0 && oa.nln > 0);
        oa_resize();
    }
    oa_redraw();
}

/* The lookup, once no other job (a refresh, a download, a search) is running: downloads are asked to pause first, as a Podcasts search does. */
static void oa_start(void) {
    int rc, part = oa.want;
    if (!part) return;
    if (pn_dl_running()) {
        pn_dl_pause();
        return;
    }
    if (pn_busy() || pn_job_busy()) return;
    rc = part == (PN_PART_COVERS | PN_PART_LYRICS)
             ? pn_art(oa.artist, oa.album, oa.title, oa.secs)
             : pn_art_again(part); /* (one tab's Try Again: the other's results stay) */
    if (rc == PN_BUSY) return;
    oa.want = 0;
    if (part & PN_PART_COVERS) oa.fail[0] = rc, oa.loaded = 0;
    if (part & PN_PART_LYRICS) oa.fail[1] = rc;
    oa.gen = pn_art_gen() - 1;
}

/* The Try Again pill: the selected tab's lookup again, when the job slot is free (a tick starts it otherwise). */
static int oa_on_retry(void *ctx, void *e) {
    int part = 1 << oa.chip;
    (void)ctx;
    (void)e;
    if (oa.mode != 0 || (oa.want & part)) return RET_OK;
    oa.want |= part;
    oa.fail[oa.chip] = 0;
    oa_start();
    oa_sync();
    return RET_OK;
}

/* The key(s) the album's cover cache is under: the playing track's own, and the library's Albums row of that name when its (the compilation's representative artist's) key differs. */
static void oa_keys(unsigned *k0, unsigned *k1) {
    void *rec = cc_playing(), *list;
    int row;
    *k0 = rec ? cc_album_key(rec) : 0;
    *k1 = 0;
    if (!rec) return;
    row = cc_find_album(oa.album);
    list = *(void **)PDEQ_SHOWLIST;
    if (row >= 0 && list) {
        unsigned k = cc_album_key(deque_at(list, (unsigned)row));
        if (k != *k0) *k1 = k;
    }
}

/* Whether the album's cover is one the user picked (the .pick marker beside its cache file). */
static int oa_has_pick(void) {
    unsigned k[2];
    char p[80];
    int i;
    oa_keys(&k[0], &k[1]);
    for (i = 0; i < 2; ++i)
        if (k[i]) {
            cc_path(p, sizeof p, k[i], ".pick");
            if (!access(p, F_OK)) return 1;
        }
    return 0;
}

/* ---------------------------------------------------------------------------
 * The cover's confirmation (mode 1)
 */
static grid_tile_t *oa_dtile(void) {
    int fresh;
    return grid_tile(&oa.gd, 0, 0, 0, &fresh);
}

/* Ask for the larger picture, or wait for the worker (the lookup may still be on its lyrics) to end. */
static void oa_fetch_start(void) {
    int rc;
    if (pn_dl_running()) pn_dl_pause(); /* downloads give way, as they do to the lookup */
    if (pn_job_busy() || pn_dl_running() || pn_busy()) {
        oa.fpend = 1;
        return;
    }
    rc = pn_art_fetch(oa.di);
    if (rc == PN_BUSY) {
        oa.fpend = 1;
        return;
    }
    oa.fpend = 0;
    if (rc) {
        oa.hint_code = rc;
        return;
    }
    oa.fetching = 1;
}

/* The larger picture is there: decoded to the confirmation's size, off the worker's file. */
static void oa_dc_decode(void) {
    char path[120], url[130];
    grid_tile_t *t = oa_dtile();
    if (!pn_art_full_path(oa.di, path, sizeof path)) {
        oa.hint_code = PN_NOTFEED;
        return;
    }
    snprintf(url, sizeof url, "file://%s", path);
    grid_free_art(t);
    grid_art_url(&oa.gd, t, url);
    if (t->art != 1) {
        oa.hint_code = PN_NOTFEED; /* (the picture did not decode) */
        return;
    }
    oa.ready = 1;
    widget_invalidate_force(oa.dc_art, (void *)0);
}

static void oa_cover_open(int i) {
    const char *name = pn_art_name(i), *artist = pn_art_artist(i);
    oa.off[0] = oa_off();
    oa.mode = 1, oa.di = i;
    oa.ready = oa.saving = oa.fetching = oa.fpend = 0;
    oa.pend = -1;
    oa.hint_code = 0;
    oa.replace = oa_has_pick();
    widget_set_text_utf8(oa.l_name, name);
    widget_set_text_utf8(oa.l_artist, artist);
    widget_set_text_utf8(oa.l_source, pn_art_source(i) == PN_SRC_DEEZER ? "Deezer" : "iTunes");
    oa_show(oa.pill, 0);
    oa_show(oa.l_hint, 0);
    grid_drop(&oa.gd);
    grid_placeholder(&oa.gd);
    oa_dtile()->art = 2;
    oa_modes();
    oa_fetch_start();
    oa_sync();
}

/* The pill: the picture the confirmation shows becomes the album's cover. */
static void oa_pick_start(void) {
    unsigned k0, k1;
    int rc;
    oa_keys(&k0, &k1);
    rc = pn_art_pick(oa.di, oa.dir[0] ? oa.dir : (const char *)0, k0, k1);
    if (rc == PN_BUSY) {
        oa.pend = oa.di;
        return;
    }
    oa.pend = -1;
    oa.hint_code = rc;
    if (rc) return;
    oa.saving = 1;
}

/* ---------------------------------------------------------------------------
 * The lyrics' detail (mode 2): the text without its tags, wrapped
 */
static int oa_wide(unsigned *dst, int cap, const char *s, unsigned len) {
    int n = 0;
    if (len > 4u * (unsigned)cap) len = 4u * (unsigned)cap;
    tk_utf8_to_utf16_ex(s, len, dst, (unsigned)cap);
    while (n < cap && dst[n]) ++n;
    return n;
}

static void oa_ly_free(void) {
    free(oa.lw);
    free(oa.ln);
    oa.lw = (unsigned *)0, oa.ln = (oa_ln_t *)0;
    oa.nln = 0, oa.lh = 0;
}

/* The lines of the lyrics text: each text line without its leading [..] tags (a line of tags only, the [ar:..] headers and the empty timestamps, is not shown), wrapped to OA_LY_W; an empty
 * line of a plain text is a gap. The text is cut where the wide buffer or the line table is full. */
static void oa_ly_build(const char *text) {
    pd_t *d = calloc(1, sizeof *d);
    int wn = 0, y = OA_LY_TOP, gap = 1;
    oa_ly_free();
    oa.lw = calloc(OA_LY_WIDE + 1, sizeof *oa.lw);
    oa.ln = calloc(OA_LY_LINES, sizeof *oa.ln);
    if (!d || !oa.lw || !oa.ln) {
        free(d);
        oa_ly_free();
        return;
    }
    while (*text && oa.nln + OA_LY_WRAP < OA_LY_LINES && wn + OA_LY_SRC + 2 < OA_LY_WIDE) {
        const char *e = text, *s = text;
        unsigned len;
        int tagged = 0, n, k, nl;
        pw_line_t pl[OA_LY_WRAP];
        while (*e && *e != '\n') ++e;
        for (;;) {
            if (s < e && *s == '[') {
                const char *c = s;
                while (c < e && *c != ']') ++c;
                if (c < e) {
                    s = c + 1;
                    tagged = 1;
                    continue;
                }
            }
            if (s < e && (*s == ' ' || *s == '\t')) {
                ++s;
                continue;
            }
            break;
        }
        len = (unsigned)(e - s);
        while (len && (s[len - 1] == ' ' || s[len - 1] == '\r' || s[len - 1] == '\t')) --len;
        text = *e ? e + 1 : e;
        if (!len) {
            if (!tagged && !gap) y += OA_LY_GAP, gap = 1;
            continue;
        }
        gap = 0;
        n = oa_wide(oa.lw + wn, OA_LY_SRC, s, len);
        if (!n) continue;
        nl = pd_lines(d, oa.st_line, oa.lw + wn, n, OA_LY_W, OA_LY_WRAP, pl);
        for (k = 0; k < nl; ++k) {
            oa.ln[oa.nln].off = wn + pl[k].start, oa.ln[oa.nln].len = pl[k].len, oa.ln[oa.nln].y = (short)y;
            ++oa.nln;
            y += OA_LY_PITCH;
        }
        wn += n + 1;
    }
    oa.lh = y + OA_BOTTOM;
    free(d);
}

static void oa_lyrics_open(int r) {
    const pn_lyr_t *c = pn_lyr_get(r);
    char sub[200], *text;
    unsigned n = 0;
    if (!c) return;
    oa.off[1] = oa_off();
    oa.mode = 2, oa.di = r;
    oa.save_failed = 0;
    oa.exists = oa_lrc_exists();
    widget_set_text_utf8(oa.l_head, c->title);
    oa_lyr_sub(sub, sizeof sub, c);
    widget_set_text_utf8(oa.l_sub, sub);
    text = pn_lyr_text(r, &n);
    oa_ly_build(text ? text : "");
    free(text);
    widget_set_prop_int(oa.sv, "yoffset", 0);
    oa_modes();
    oa_sync();
}

/* Back to the tabs: the detail's memory freed, the tab's scroll position back. */
static void oa_leave(void) {
    int was = oa.mode;
    if (was == 0) return;
    oa.mode = 0;
    if (was == 1) {
        if (oa.fetching || oa.saving) pn_cancel(); /* (it ends by itself) */
        oa.fetching = oa.fpend = oa.saving = oa.ready = 0;
        oa.pend = -1;
        oa.hint_code = 0;
        grid_drop(&oa.gd);
        oa.drop = 1;
    } else
        oa_ly_free();
    oa_modes();
    oa_sync();
    widget_set_prop_int(oa.sv, "yoffset", oa.off[oa.chip]);
}

static int oa_on_back(void *ctx, void *e) {
    if (oa.mode) {
        oa_leave();
        return RET_OK;
    }
    return pod_on_back(ctx, e);
}

/* ---------------------------------------------------------------------------
 * The tick
 */
static int oa_tick(const void *timer) {
    int changed = 0;
    (void)timer;
    if (!oa.win) return RET_OK; /* (the destroy handler removes the timer: this only ends a stray one) */
    if (oa.want) {
        oa_start();
        changed = 1;
    }
    if (oa.mode == 1 && oa.fpend) {
        oa_fetch_start();
        changed = 1;
    }
    if (oa.mode == 1 && oa.pend >= 0) {
        oa_pick_start();
        changed = 1;
    }
    if (oa.mode == 1 && oa.fetching && pn_pick_state() == 2) {
        oa.fetching = 0;
        if (pn_pick_code() == PN_OK)
            oa_dc_decode();
        else
            oa.hint_code = pn_pick_code();
        changed = 1;
    }
    if (oa.mode == 1 && oa.saving && pn_pick_state() == 2) {
        oa.saving = 0;
        if (pn_pick_code() == PN_OK) {
            oa.picked = oa.di;
            oa_leave();
            changed = 1;
        } else {
            oa.hint_code = pn_pick_code();
            changed = 1;
        }
    }
    if (oa.drop && !pn_job_busy()) {
        pn_art_full_drop();
        oa.drop = 0;
    }
    if (oa.gen != pn_art_gen()) {
        oa.gen = pn_art_gen();
        changed = 1;
    }
    if (oa.loaded < pn_art_count() && !(oa.want & PN_PART_COVERS)) oa_load_one();
    if (changed) oa_sync();
    if (!oa.want && !oa.fetching && !oa.fpend && oa.pend < 0 && !oa.saving && !pn_job_busy() && pn_dl_waiting() &&
        !pn_dl_running())
        pn_dl_start();
    return RET_REPEAT;
}

/* ---------------------------------------------------------------------------
 * The chips (the Search page's: a pill behind the selected chip, the texts painted here, the selected one in the dark style)
 */
static int oa_chip_w(int i) { return oa.chip_x[i + 1] - oa.chip_x[i] - SE_CHIP_GAP; }

static void oa_chip_fx(void) {
    widget_move(oa.chl, oa.chip_x[oa.chip], SE_CHIP_Y);
    widget_resize(oa.chl, oa_chip_w(oa.chip), SE_CHIP_H);
    widget_set_visible(oa.chl, 1, 0);
    widget_invalidate_force(oa.chips, (void *)0);
}

static int oa_on_chips_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int i, pass;
    (void)ctx;
    if (!canvas || !oa.chips) return RET_OK;
    for (pass = 0; pass < 2; ++pass) {
        widget_prepare_text_style(pass ? oa.st_chip_on : oa.st_chip, canvas);
        for (i = 0; i < 2; ++i) {
            int rect[4];
            if ((i == oa.chip) != pass) continue;
            rect[0] = oa.chip_x[i], rect[1] = SE_CHIP_Y, rect[2] = oa_chip_w(i), rect[3] = SE_CHIP_H;
            canvas_draw_text_in_rect(canvas, oa.chip_text[i], (unsigned)oa.chip_len[i], rect);
        }
    }
    return RET_OK;
}

/* The chips' places from the texts' widths in the chip font (the page's language). */
static void oa_chips_setup(void) {
    static const char *const key[2] = {"Covers", "Lyrics"};
    int i, x = SE_CHIP_X;
    for (i = 0; i < 2; ++i) {
        const char *s = TR(key[i]);
        unsigned n = 0;
        float f;
        while (s[n] && n < 60) n++;
        memset(oa.chip_text[i], 0, sizeof oa.chip_text[i]);
        tk_utf8_to_utf16_ex(s, n, oa.chip_text[i], 23);
        oa.chip_len[i] = 0;
        while (oa.chip_text[i][oa.chip_len[i]]) oa.chip_len[i]++;
        f = widget_measure_text(oa.st_chip, oa.chip_text[i]);
        oa.chip_x[i] = x;
        x += (f > 0.0f ? (int)(f + 0.999f) : oa.chip_len[i] * 9) + 2 * SE_CHIP_PAD + SE_CHIP_GAP;
    }
    oa.chip_x[2] = x;
}

static void oa_chip_set(int k) {
    oa.off[oa.chip] = oa_off();
    oa.chip = k;
    oa_chip_fx();
    oa_sync();
    widget_set_prop_int(oa.sv, "yoffset", oa.off[k]);
    oa_redraw();
}

static int
oa_chip_at(int x) { /* the chip under x (the row's coordinates), the nearest one for a gap, -1 past the ends */
    int i;
    for (i = 0; i < 2; ++i)
        if (x < oa.chip_x[i + 1]) return x >= oa.chip_x[i] - SE_CHIP_GAP / 2 ? i : -1;
    return -1;
}

static int oa_on_chips(void *ctx, void *e) {
    int pt[2], type = e ? *(int *)e : 0, k;
    (void)ctx;
    if (!oa.win || !e || oa.mode) return RET_OK;
    if (type == EVT_POINTER_DOWN) {
        oa.chip_down = 1;
    } else if (type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) {
        int tap = oa.chip_down && type == EVT_POINTER_UP;
        oa.chip_down = 0;
        pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
        widget_to_local(oa.chips, pt);
        k = tap ? oa_chip_at(pt[0]) : -1;
        if (k >= 0 && k != oa.chip) oa_chip_set(k);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Paint and touch of the list
 */
static void oa_cell(int i, int *x, int *y) {
    *x = OA_X0 + (i % OA_COLS) * (OA_TILE + OA_GAP);
    *y = OA_Y0 + (i / OA_COLS) * OA_PITCH;
}

/* The cover under the view point (x, y) (content coordinates), else -1. */
static int oa_at(int x, int y) {
    int i, n = pn_art_count();
    if (n > PN_ART_MAX) n = PN_ART_MAX;
    for (i = 0; i < n; ++i) {
        int cx, cy;
        oa_cell(i, &cx, &cy);
        if (x >= cx && x < cx + OA_TILE && y >= cy && y < cy + OA_TILE) return i;
    }
    return -1;
}

static int oa_row_at(int y) {
    int n = oa_rows_ready() ? pn_lyr_count() : 0;
    return y >= 0 && y / SE_ROW_H < n ? y / SE_ROW_H : -1;
}

/* A badge: a box with its corners cut in steps, filled, its text over it (drawn by the caller with the badge style). */
static void oa_badge_fill(void *canvas, int x, int y, int w, unsigned colour) {
    canvas_set_fill_color(canvas, colour);
    canvas_fill_rect(canvas, x + 2, y, w - 4, OA_BADGE_H);
    canvas_fill_rect(canvas, x + 1, y + 1, w - 2, OA_BADGE_H - 2);
    canvas_fill_rect(canvas, x, y + 2, w, OA_BADGE_H - 4);
}

static int oa_row_saved(int r) { return (oa.saved >> r & 1) != 0; }

static void oa_paint_covers(void *canvas, int off) {
    int i, n = pn_art_count();
    if (!oa_covers_ready()) return;
    if (n > PN_ART_MAX) n = PN_ART_MAX;
    for (i = 0; i < n; ++i) {
        int x, y;
        oa_cell(i, &x, &y);
        y -= off;
        if (y + OA_TILE <= 0 || y >= SE_LIST_H) continue;
        grid_blit(canvas, &oa.g, oa_tile(i), x, y, SE_LIST_H);
        if (i == oa.picked && y >= 3 && y + OA_TILE + 3 <= SE_LIST_H) {
            canvas_set_fill_color(canvas, OA_FRAME_RGB);
            canvas_fill_rect(canvas, x - 3, y - 3, OA_TILE + 6, 2);
            canvas_fill_rect(canvas, x - 3, y + OA_TILE + 1, OA_TILE + 6, 2);
            canvas_fill_rect(canvas, x - 3, y - 1, 2, OA_TILE + 2);
            canvas_fill_rect(canvas, x + OA_TILE + 1, y - 1, 2, OA_TILE + 2);
        }
    }
}

static void oa_paint_rows(void *canvas, int off) {
    int r, n, r0, r1, pass, tw = OA_ROW_END - OA_ROW_X - oa.bw - 8;
    if (!oa_rows_ready()) return;
    n = pn_lyr_count();
    r0 = off < 0 ? 0 : off / SE_ROW_H;
    r1 = (off + SE_LIST_H - 1) / SE_ROW_H;
    if (r1 > n - 1) r1 = n - 1;
    for (r = r0; r <= r1; ++r) {
        int y = r * SE_ROW_H - off;
        const pn_lyr_t *c = pn_lyr_get(r);
        if (oa.press == r + 1) az_fill_h(canvas, 0, y, y + SE_ROW_H - 1, 320, LIST_PRESS, SE_LIST_H);
        az_fill_h(canvas, OA_ROW_X, y + SE_ROW_H - 1, y + SE_ROW_H, OA_ROW_END - OA_ROW_X, LIST_HAIR, SE_LIST_H);
        if (c && (c->synced || oa_row_saved(r)) && y + SE_TITLE_Y >= 0 && y + SE_TITLE_Y + LIST_TITLE_H <= SE_LIST_H)
            oa_badge_fill(canvas, OA_ROW_END - oa.bw, y + SE_TITLE_Y + (LIST_TITLE_H - OA_BADGE_H) / 2, oa.bw,
                          oa_row_saved(r) ? OA_BADGE_ON_RGB : OA_BADGE_RGB);
    }
    for (pass = 0; pass < 2; ++pass) { /* the titles, then the grey lines: one text style at a time */
        widget_prepare_text_style(pass ? oa.st_sub : oa.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, oa_ltile(r), pass, OA_ROW_X, r * SE_ROW_H - off + (pass ? SE_SUB_Y : SE_TITLE_Y),
                      pass ? OA_ROW_END - OA_ROW_X : tw, pass ? LIST_SUB_H : LIST_TITLE_H, SE_LIST_H);
    }
    for (pass = 0; pass < 2; ++pass) { /* the badges' texts: Synced (grey), Saved (dark on the light fill) */
        widget_prepare_text_style(pass ? oa.st_badge_on : oa.st_badge, canvas);
        for (r = r0; r <= r1; ++r) {
            const pn_lyr_t *c = pn_lyr_get(r);
            int y = r * SE_ROW_H - off + SE_TITLE_Y + (LIST_TITLE_H - OA_BADGE_H) / 2, rect[4];
            if (!c || oa_row_saved(r) != pass || (!pass && !c->synced) || y < 0 || y + OA_BADGE_H > SE_LIST_H) continue;
            rect[0] = OA_ROW_END - oa.bw, rect[1] = y, rect[2] = oa.bw, rect[3] = OA_BADGE_H;
            {
                const char *s = TR(pass ? "Saved" : "Synced");
                unsigned w[24], k = 0;
                while (s[k] && k < 60) ++k;
                tk_utf8_to_utf16_ex(s, k, w, 23);
                k = 0;
                while (w[k]) ++k;
                canvas_draw_text_in_rect(canvas, w, k, rect);
            }
        }
    }
}

/* The lyrics detail's lines: the visible ones, each wholly inside the text region. */
static void oa_paint_text(void *canvas, int off) {
    int i;
    if (!oa.lw || !oa.ln) return;
    widget_prepare_text_style(oa.st_line, canvas);
    for (i = 0; i < oa.nln; ++i) {
        int y = oa.ln[i].y - off, rect[4];
        if (y + OA_LY_PITCH <= 0) continue;
        if (y >= OA_LY_H) break;
        if (y < 0 || y + OA_LY_PITCH > OA_LY_H) continue;
        rect[0] = OA_LY_X, rect[1] = y, rect[2] = OA_LY_W, rect[3] = OA_LY_PITCH;
        canvas_draw_text_in_rect(canvas, oa.lw + oa.ln[i].off, (unsigned)oa.ln[i].len, rect);
    }
}

/* The content view's EVT_AFTER_PAINT, in the list's coordinates (the Search page's: the scroll offset taken off the canvas). */
static int oa_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = oa_off();
    (void)ctx;
    if (!canvas || !oa.win || oa.mode == 1) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    if (oa.mode == 2)
        oa_paint_text(canvas, off);
    else if (oa.chip == 0)
        oa_paint_covers(canvas, off);
    else
        oa_paint_rows(canvas, off);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* The confirmation's cover, in its own view's coordinates. */
static int oa_on_dc_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (!canvas || !oa.win || oa.mode != 1 || !oa.gd.tiles) return RET_OK;
    grid_blit(canvas, &oa.gd, oa_dtile(), 0, 0, 0);
    return RET_OK;
}

static void oa_local(void *e, int *x, int *y) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(oa.view, pt);
    *x = pt[0], *y = pt[1];
}

static int oa_item_at(int x, int y) { return oa.chip == 0 ? oa_at(x, y) : oa_row_at(y); }

static int oa_on_down(void *ctx, void *e) {
    (void)ctx;
    oa.down = -1;
    if (!e || !oa.view || oa.mode) return RET_OK;
    oa_local(e, &oa.down_x, &oa.down_y);
    oa.down = oa_item_at(oa.down_x, oa.down_y);
    if (oa.chip == 1 && oa.down >= 0) {
        oa.press = oa.down + 1;
        oa_redraw();
    }
    return RET_OK;
}

static void oa_unpress(void) {
    if (!oa.press) return;
    oa.press = 0;
    oa_redraw();
}

static int oa_on_up(void *ctx, void *e) {
    int x, y, a = oa.down;
    (void)ctx;
    oa.down = -1;
    oa_unpress();
    if (a < 0 || !e || !oa.view || oa.mode) return RET_OK;
    oa_local(e, &x, &y);
    if (oa_abs(x - oa.down_x) >= SC_DRAG_PX || oa_abs(y - oa.down_y) >= SC_DRAG_PX || oa_item_at(x, y) != a)
        return RET_OK;
    if (oa.fail[oa.chip] || (oa.want >> oa.chip & 1)) return RET_OK;
    if (oa.chip == 0)
        oa_cover_open(a);
    else
        oa_lyrics_open(a);
    return RET_OK;
}

/* The scroll_view took the gesture as a drag: the press is gone. */
static int oa_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    oa.down = -1;
    oa_unpress();
    return RET_OK;
}

static int oa_on_use(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (oa.mode != 1 || !oa.ready || oa.saving || oa.pend >= 0) return RET_OK;
    oa.hint_code = 0;
    if (pn_dl_running()) pn_dl_pause();
    oa_pick_start();
    oa_sync();
    return RET_OK;
}

static int oa_on_save(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (oa.mode != 2 || !oa.lw || oa.nln <= 0) return RET_OK;
    if (pn_lyr_save(oa.di, oa.lrc)) {
        oa.saved |= 1u << oa.di;
        oa.save_failed = 0;
        oa_leave();
    } else {
        oa.save_failed = 1;
        oa_sync();
    }
    return RET_OK;
}

static int oa_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != oa.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    if (oa.timer) timer_remove(oa.timer);
    if (pn_job_busy())
        pn_cancel(); /* the worker ends by itself; its scratch files are removed by the next lookup */
    else
        pn_art_clean();
    if (!pn_job_busy() && pn_dl_waiting() && !pn_dl_running()) pn_dl_start();
    oa_ly_free();
    grid_free(&oa.g);
    grid_free(&oa.gl);
    grid_free(&oa.gd);
    memset(&oa, 0, sizeof oa);
    return RET_OK;
}

/* The playing track's fields: artist, album, title, the folder (for the folder picture) and the .lrc path (the file name with its extension replaced). */
static int oa_track(void) {
    void *rec = cc_playing();
    const char *path, *slash, *dot;
    unsigned n = 0, k;
    if (!rec) return 0;
    path = cc_str(rec, REC_PATH);
    if (!*path) return 0;
    while (path[n] && n + 5 < OA_PATH) ++n;
    if (path[n]) return 0; /* a path that does not fit */
    slash = path;
    for (k = 0; path[k]; ++k)
        if (path[k] == '/') slash = path + k;
    dot = (const char *)0;
    for (k = (unsigned)(slash - path); path[k]; ++k)
        if (path[k] == '.') dot = path + k;
    k = dot ? (unsigned)(dot - path) : n;
    memcpy(oa.lrc, path, k);
    memcpy(oa.lrc + k, ".lrc", 5);
    k = (unsigned)(slash - path);
    if (*slash == '/' && k > 0 && k < n) { /* the folder: nothing of the card's root is made a folder picture */
        memcpy(oa.dir, path, k);
        oa.dir[k] = 0;
        if (!strcmp(oa.dir, "/mnt/mmc")) oa.dir[0] = 0;
    } else
        oa.dir[0] = 0;
    snprintf(oa.artist, sizeof oa.artist, "%s", cc_str(rec, REC_ARTIST));
    snprintf(oa.album, sizeof oa.album, "%s", cc_str(rec, REC_ALBUM));
    snprintf(oa.title, sizeof oa.title, "%s", cc_str(rec, REC_TITLE));
    if (!oa.title[0]) snprintf(oa.title, sizeof oa.title, "%s", cc_str(rec, REC_NAME));
    {
        int pos = 0, len = 0;
        oa.secs = get_playtimeandlength(&pos, &len) == 1 && len > 0 ? (unsigned)len : 0;
    }
    return 1;
}

/* A badge's width: the wider of Synced and Saved in the badge font, and the padding. */
static void oa_badge_width(void) {
    static const char *const key[2] = {"Synced", "Saved"};
    int i, w = 0;
    for (i = 0; i < 2; ++i) {
        const char *s = TR(key[i]);
        unsigned t[24], n = 0;
        float f;
        while (s[n] && n < 60) ++n;
        tk_utf8_to_utf16_ex(s, n, t, 23);
        f = widget_measure_text(oa.st_badge, t);
        if ((int)(f + 0.999f) > w) w = (int)(f + 0.999f);
    }
    oa.bw = w + 2 * OA_BADGE_PAD;
}

/* Open: the More sheet's Find Cover & Lyrics row. 0 once the page is up (or already open); -1 when it could not open (nothing is left of it). */
int onlineart_open(void) {
    if (oa.win) return 0;
    if (access(KILL_SD, F_OK) == 0) return -1;
    memset(&oa, 0, sizeof oa);
    if (!oa_track()) {
        memset(&oa, 0, sizeof oa);
        return -1;
    }
    oa.win = window_open("m1plus_onlineart");
    if (!oa.win) {
        memset(&oa, 0, sizeof oa);
        return -1;
    }
    widget_on(oa.win, EVT_DESTROY, oa_on_destroy, oa.win);
    pod_bind(oa.win, "btn_return", oa_on_back, (void *)0);
    pod_bind(oa.win, "btn_backtoplayer", pod_on_player, (void *)0);
    oa.chips = widget_lookup(oa.win, "oa_chips", 1);
    oa.chl = widget_lookup(oa.win, "oa_chip_hl", 1);
    oa.sep = widget_lookup(oa.win, "oa_sep", 1);
    oa.list = widget_lookup(oa.win, "oa_listview", 1);
    oa.sv = widget_lookup(oa.win, "oa_scrollview", 1);
    oa.view = widget_lookup(oa.win, "oa_view", 1);
    oa.l_status = widget_lookup(oa.win, "oa_status", 1);
    oa.es_icon = widget_lookup(oa.win, "oa_es_icon", 1);
    oa.es_text = widget_lookup(oa.win, "oa_es_text", 1);
    oa.l_hint = widget_lookup(oa.win, "oa_hint", 1);
    oa.l_head = widget_lookup(oa.win, "oa_dh_title", 1);
    oa.l_sub = widget_lookup(oa.win, "oa_dh_sub", 1);
    oa.dc = widget_lookup(oa.win, "oa_dc", 1);
    oa.dc_art = widget_lookup(oa.win, "oa_dc_art", 1);
    oa.l_name = widget_lookup(oa.win, "oa_dc_name", 1);
    oa.l_artist = widget_lookup(oa.win, "oa_dc_artist", 1);
    oa.l_source = widget_lookup(oa.win, "oa_dc_source", 1);
    oa.st_title = widget_lookup(oa.win, "label_row_title", 1);
    oa.st_sub = widget_lookup(oa.win, "label_row_sub", 1);
    oa.st_chip = widget_lookup(oa.win, "label_chip", 1);
    oa.st_chip_on = widget_lookup(oa.win, "label_chip_on", 1);
    oa.st_badge = widget_lookup(oa.win, "label_badge", 1);
    oa.st_badge_on = widget_lookup(oa.win, "label_badge_on", 1);
    oa.st_line = widget_lookup(oa.win, "label_line", 1);
    oa.lpill = pod_bind(oa.win, "oa_lsave", oa_on_save, (void *)0);
    oa.pill = pod_bind(oa.win, "oa_save", oa_on_use, (void *)0);
    oa.retry = pod_bind(oa.win, "oa_es_retry", oa_on_retry, (void *)0);
    if (!oa.chips || !oa.chl || !oa.sep || !oa.list || !oa.sv || !oa.view || !oa.l_status || !oa.l_hint || !oa.l_head ||
        !oa.l_sub || !oa.dc || !oa.dc_art || !oa.l_name || !oa.l_artist || !oa.l_source || !oa.st_title || !oa.st_sub ||
        !oa.st_chip || !oa.st_chip_on || !oa.st_badge || !oa.st_badge_on || !oa.st_line || !oa.lpill || !oa.pill ||
        !oa.es_icon || !oa.es_text || !oa.retry || !grid_init(&oa.g, oa.win, PN_ART_MAX, OA_TILE, 8) ||
        !grid_init(&oa.gl, oa.win, PN_LYR_MAX, 8, 0) || !grid_init(&oa.gd, oa.win, 1, OA_DC_SIDE, OA_DC_R)) {
        navigator_back(); /* an asset that is not ours, or no memory: the destroy handler frees what exists */
        return -1;
    }
    grid_placeholder(&oa.g);
    label_set_line_wrap(oa.es_text, 1);
    widget_set_prop_bool(oa.es_text, "word_wrap", 1); /* (as the lyrics page's lines: break at spaces) */
    oa.down = -1, oa.pend = -1, oa.picked = -1;
    oa.want = PN_PART_COVERS | PN_PART_LYRICS;
    widget_on(oa.view, EVT_POINTER_DOWN, oa_on_down, (void *)0);
    widget_on(oa.view, EVT_POINTER_UP, oa_on_up, (void *)0);
    widget_on(oa.view, EVT_POINTER_ABORT, oa_on_abort, (void *)0);
    widget_on(oa.view, EVT_AFTER_PAINT, oa_on_paint, (void *)0);
    widget_on(oa.dc_art, EVT_AFTER_PAINT, oa_on_dc_paint, (void *)0);
    widget_on(oa.chips, EVT_AFTER_PAINT, oa_on_chips_paint, (void *)0);
    widget_on(oa.chips, EVT_POINTER_DOWN, oa_on_chips, (void *)0);
    widget_on(oa.chips, EVT_POINTER_UP, oa_on_chips, (void *)0);
    widget_on(oa.chips, EVT_POINTER_ABORT, oa_on_chips, (void *)0);
    oa_chips_setup();
    oa_badge_width();
    oa_chip_fx();
    oa_show(oa.l_hint, 0);
    oa_show(oa.pill, 0);
    oa_show(oa.lpill, 0);
    oa_modes();
    oa_sync();
    oa.timer = timer_add(oa_tick, (void *)0, OA_TICK_MS);
    if (!oa.timer) {
        navigator_back();
        return -1;
    }
    oa_start();
    oa_sync();
    return 0;
}
