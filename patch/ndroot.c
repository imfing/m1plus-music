/* The Subsonic root page (docs/modules/subsonic.md, task ND-11): the menu of the library source and its shared empty state.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opened by the menu row Subsonic (patch/m1plus.c ACT_SUBSONIC). With a server saved the page is the large title, a grey status line under it (a 14 px glyph, then "Synced 5m ago": the check circle
 * when connected, the spinner and "Syncing..." while a sync runs, the unplugged plug and the same line when offline, "Not Connected" when the server does not answer), six menu rows (Albums, Artists, Songs,
 * Playlists, Favorites, Downloaded: each opens the library's own page on lib_nd) and the library's grey footer under them ("2431 songs", nothing before the first sync). The large title scrolls away and the navbar's small
 * title fades in (pod_title_gone, as on every large-title page). The navbar's Search button (btn_search, the capsule's left cap at NAV_CF_X, the Songs page's place: shown with a server saved when lib_nd has
 * LS_CAP_SEARCH) opens the library's search on the source (search_open_src). The navbar's "..." (btn_more) opens the shared view-sort card with two action rows: Sync Now (slot VS_SEARCH; inactive while a sync runs, the Wi-Fi toast
 * when there is none) and Server Settings (slot VS_SELECT; the Server page, as the Add Server pill). With none saved the list is hidden and the shared empty state shows: a plug, "Not Connected", one
 * sentence, the Add Server pill and, under it, a Downloaded pill (the card's downloads stay reachable); the card then holds Server Settings alone. The page's asset is tools/pod_nd.py (window m1plus_ndroot: rows pod_row0..5,
 * the status line nd_status with nd_st_icon / nd_st_spin, nd_foot, nd_es_*).
 *
 * Opening asks for a sync when the cache is older than a quarter of an hour (sba_sync_auto; nothing without Wi-Fi). The page only READS the status record: a 500 ms timer re-reads it when
 * sba_gen moved and, once in four seconds, anyway (the Wi-Fi state has no counter). Downloaded needs no network (sba_downloaded reads the manifest), so it opens with Wi-Fi off.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "podcasts.h"
#include "libsrc.h"
#include "albums.h"
#include "artists.h"
#include "playlists.h"
#include "sbapi.h"
#include "sbsrc.h"
#include "viewsort.h"
#include "search.h"

extern int songs_open_src(const lib_src_t *src, int which, const char *title); /* patch/songs.c */
extern int nd_server_open(void); /* patch/ndserver.c */
extern void nd_sync_now(void); /* patch/ndserver.c: asks first, then syncs */
extern int nd_signin_open(void); /* patch/ndserver.c: the Sign In page on the Server URL row */

#define NR_TICK_MS 500
#define NR_FORCE_TICKS 8 /* the Wi-Fi state is read again every 4 s */
#define NR_ROWS 6

enum { NR_ALBUMS, NR_ARTISTS, NR_SONGS, NR_PLAYLISTS, NR_FAVORITES, NR_DOWNLOADED };
enum { NR_CONNECTED, NR_OFFLINE, NR_NOT_CONNECTED, NR_SYNCING }; /* the status line's glyph */

static struct {
    void *win, *list, *status, *es_big, *es_icon, *es_title, *es_text, *es_pill, *es_dl;
    unsigned timer, gen, ticks;
    int guard; /* sba_guard() as the last tick saw it: a refusal ending (Wi-Fi back, the clock set, the card in) asks for the sync that was due */
    int sync; /* the sync state (SBA_ST_*) the last tick saw: a run that ended in failure is told once */
    int shown; /* -1 nothing set yet, 0 the list, 1 the empty state */
    char s[128]; /* the status line last put on the label: only a change is written */
    void *icon, *spin, *foot, *sv, *title, *fade,
        *more; /* the status glyph and spinner, the footer, the scroll view, the navbar's small title, the fade, the "..." button */
    vs_t vs; /* the "..." card */
    int kind, title_on, noscroll,
        dim; /* the glyph shown (-1 none), the small title shown, no scroll events, the Sync Now row dimmed */
    char f[48]; /* the footer last put on its label */
    void *
        search; /* the navbar's Search button (the capsule's left cap at NAV_CF_X): with a server saved, on a source that searches */
    int nav; /* -1 nothing set yet, 0 the capsule is [... | Now Playing], 1 it is [Search | ... | Now Playing] */
} nr __attribute__((section(".scratch")));

static void nr_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The connection state: what the status record and the Wi-Fi say. */
static int nr_state(void) {
    int sync = sba_state(SBA_K_SYNC, "", (int *)0);
    unsigned songs, when;
    int trunc;
    if (sync == SBA_ST_LOAD || sba_bg_progress((unsigned *)0, (unsigned *)0))
        return NR_SYNCING; /* (phase 2 shows its progress in the same style) */
    if (sba_guard() == SBA_NOWIFI) return NR_OFFLINE;
    if (sync == SBA_ST_FAIL) return NR_NOT_CONNECTED;
    if (sync == SBA_ST_OK) return NR_CONNECTED;
    return sba_summary(&songs, &when, &trunc) ? NR_CONNECTED : NR_NOT_CONNECTED;
}

/* "Synced 5m ago" (the age as the Podcasts dates say it), "Synced just now" under a minute, or "Not synced yet". */
void nd_synced_line(char *out, unsigned size) {
    unsigned songs, when, now = (unsigned)time((long *)0);
    int trunc;
    char age[40];
    if (!sba_summary(&songs, &when, &trunc)) {
        snprintf(out, size, "%s", TR("Not synced yet"));
        return;
    }
    age[0] = 0;
    if (when <= now && now - when >= 60) pc_when(when, now, age, sizeof age);
    if (age[0])
        snprintf(out, size, TR("Synced %s"), age);
    else /* under a minute (or a clock set back) */
        snprintf(out, size, "%s", TR("Synced just now"));
}

/* The status line's text for a state: "Syncing..." and "Not Connected" stand alone, the others tell the sync. */
static void nr_line(int state, char *out, unsigned size) {
    switch (state) {
    case NR_SYNCING: {
        unsigned done, total;
        int kind = sba_bg_progress(&done, &total);
        if (kind && sba_state(SBA_K_SYNC, "", (int *)0) !=
                        SBA_ST_LOAD) { /* the background fill after the sync: songs, covers, artist images */
            if (kind == 1)
                snprintf(out, size, TR("Updating library… %d/%d"), (int)done, (int)total);
            else if (kind == 2)
                snprintf(out, size, TR("Loading covers… %d/%d"), (int)done, (int)total);
            else
                snprintf(out, size, TR("Loading artist images… %d/%d"), (int)done, (int)total);
            return;
        }
        snprintf(out, size, "%s", TR("Syncing…"));
        return;
    }
    case NR_NOT_CONNECTED:
        snprintf(out, size, "%s", TR("Not Connected"));
        return;
    default:
        nd_synced_line(out, size);
        return;
    }
}

/* The footer under the rows: the library's "2431 songs" (the sync's total); nothing before the first sync. */
static void nr_footer(char *out, unsigned size) {
    unsigned songs, when;
    int trunc;
    out[0] = 0;
    if (sba_summary(&songs, &when, &trunc)) pod_fmt(out, size, TR(songs == 1 ? "%d song" : "%d songs"), (int)songs);
}

/* The glyph before the status text: the spinner while syncing, else the check circle (connected) or the unplugged plug (offline, not connected). */
static void nr_glyph(int state) {
    int kind = state == NR_SYNCING ? 2 : state == NR_CONNECTED ? 0 : 1;
    if (kind == nr.kind) return;
    nr.kind = kind;
    widget_set_visible(nr.icon, kind != 2, 0);
    if (kind != 2) image_base_set_image(nr.icon, kind ? "nd_st_off" : "nd_st_ok");
    ls_spin(nr.spin, kind == 2);
}

static void nr_text(void *w, char *kept, unsigned size, const char *text) {
    if (!w || !strcmp(kept, text)) return;
    snprintf(kept, size, "%s", text);
    widget_set_text_utf8(w, text);
}

/* The capsule: [Search | ... | Now Playing] with a server saved and a source that searches (LS_CAP_SEARCH), else [... | Now Playing]; the "..." is the middle piece (pod_nav_moremid) or the left cap, and the small title
 * ends at the first button (168 or 214). */
static void nr_nav(void) {
    int on = sba_configured() && (ls_caps(&lib_nd) & LS_CAP_SEARCH) != 0;
    const char *mid = on ? "pod_nav_moremid" : "pod_nav_more",
               *down = on ? "pod_nav_moremid_down" : "pod_nav_more_down";
    if (on == nr.nav) return;
    nr.nav = on;
    nr_show(nr.search, on);
    widget_set_prop_str(nr.more, "style:normal:icon", mid);
    widget_set_prop_str(nr.more, "style:over:icon", mid);
    widget_set_prop_str(nr.more, "style:pressed:icon", down);
    widget_resize(nr.title, (on ? NAV_CF_X : NAV_VIEW_X) - NAV_TITLE_X, 22);
}

/* The navbar's small title once the large one has scrolled away; the fade shows while the list is scrolled. The empty state has no scrolling list: its own large title stays. */
static void nr_title_update(void) {
    int off = nr.sv ? *(int *)((char *)nr.sv + SC_YOFF) : 0, list = nr.shown == 0;
    pod_title_set(nr.title, &nr.title_on, nr.noscroll || (list && pod_title_gone(off, 0)));
    if (nr.fade) {
        widget_set_visible(nr.fade, list && off > 0, 0);
        widget_set_sensitive(nr.fade, 0);
    }
}

static int nr_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (nr.win) nr_title_update();
    return RET_OK;
}

/* A label's text colour, in every state it can show. */
static void nr_colour(void *w, const char *rgb) {
    static const char *const prop[3] = {"style:normal:text_color", "style:disable:text_color",
                                        "style:focused:text_color"};
    int i;
    for (i = 0; i < 3; ++i) widget_set_prop_str(w, prop[i], rgb);
}

/* Sync Now is inactive (grey, no touch) while a sync runs; a tap with no Wi-Fi gets the toast instead. Written only on a change. */
static void nr_card_state(void) {
    int busy = sba_configured() && sba_state(SBA_K_SYNC, "", (int *)0) == SBA_ST_LOAD;
    if (!nr.vs.label[VS_SEARCH] || busy == nr.dim) return;
    nr.dim = busy;
    widget_set_sensitive(nr.vs.item[VS_SEARCH], !busy);
    nr_colour(nr.vs.label[VS_SEARCH], busy ? "#6C6C70" : "#FFFFFF");
}

/* Everything the page says, from the data layer; `force` writes the shown state again (a language change shows up on coming to the front). */
static void nr_refresh(int force) {
    int conf = sba_configured();
    if (force)
        nr.shown = -1, nr.kind = -1, nr.nav = -1, nr.s[0] = 1, nr.s[1] = 0, nr.f[0] = 1,
        nr.f[1] = 0; /* (a text no real one equals) */
    if (nr.shown != !conf) {
        nr.shown = !conf;
        nr_show(nr.list, conf);
        nr_show(nr.es_big, !conf);
        nr_show(nr.es_icon, !conf);
        nr_show(nr.es_title, !conf);
        nr_show(nr.es_text, !conf);
        nr_show(nr.es_pill, !conf);
        nr_show(nr.es_dl, !conf);
        vs_offer(&nr.vs,
                 conf ? VS_WITH_SEARCH | VS_WITH_SELECT : VS_WITH_SELECT); /* signed out: Server Settings alone */
        nr.dim = -1; /* (the offer made the Sync Now row sensitive again) */
    }
    if (conf) {
        char line[sizeof nr.s], foot[sizeof nr.f];
        int state = nr_state();
        nr_line(state, line, sizeof line);
        nr_text(nr.status, nr.s, sizeof nr.s, line);
        nr_glyph(state);
        nr_footer(foot, sizeof foot);
        nr_text(nr.foot, nr.f, sizeof nr.f, foot);
    }
    nr_nav();
    nr_title_update();
    nr_card_state();
}

static unsigned nr_gen(void) { return sba_gen() + sba_dl_gen() + sba_bg_gen(); }

static int nr_on_row(void *ctx, void *e) {
    (void)e;
    switch ((int)(long)ctx) {
    case NR_ALBUMS:
        albums_open_src(&lib_nd, (void *)0);
        break;
    case NR_ARTISTS:
        artists_open_src(&lib_nd);
        break;
    case NR_SONGS:
        songs_open_src(&lib_nd, LS_SONGS, TR("Songs"));
        break;
    case NR_PLAYLISTS:
        playlists_open_src(&lib_nd);
        break;
    case NR_FAVORITES:
        songs_open_src(&lib_nd, LS_FAVORITES, TR("Favorites"));
        break;
    case NR_DOWNLOADED:
        songs_open_src(&lib_nd, LS_DOWNLOADED, TR("Downloaded"));
        break;
    }
    return RET_OK;
}

/* The empty state's Downloaded pill: the downloads and their manifest stay on the card after Sign Out, and Downloaded needs no server. */
static int nr_on_downloaded(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    songs_open_src(&lib_nd, LS_DOWNLOADED, TR("Downloaded"));
    return RET_OK;
}

/* The card's Server Settings row and the empty state's Add Server pill: the Server page with a server saved, the Sign In page straight away without one (a sign-in first, then the sync;
 * its success comes back here). */
static int nr_on_server(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    vs_menu(&nr.vs, 0, 0, 0, 0);
    if (sba_configured())
        nd_server_open();
    else
        nd_signin_open();
    return RET_OK;
}

/* The navbar's "...": the card opens and closes. */
static int nr_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    nr_card_state();
    vs_menu(&nr.vs, !nr.vs.on, 0, 0, 0);
    return RET_OK;
}

/* Search: the library's search page on the source (patch/search.c; never the card's). */
static int nr_on_search(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sba_configured()) search_open_src(&lib_nd);
    return RET_OK;
}

static int nr_on_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    vs_menu(&nr.vs, 0, 0, 0, 0);
    return RET_OK;
}

/* A tap on a card row (the slots of the Search and Select rows: Sync Now, Server Settings). Sync Now is the Server page's (it asks first, a refusal such as no Wi-Fi is the toast). */
static int nr_on_card(void *ctx, void *e) {
    (void)e;
    if ((int)(long)ctx == VS_SELECT) return nr_on_server((void *)0, (void *)0);
    if ((int)(long)ctx != VS_SEARCH) return RET_OK;
    vs_menu(&nr.vs, 0, 0, 0, 0);
    if (!sba_configured()) return RET_OK;
    nd_sync_now();
    nr_refresh(0);
    return RET_OK;
}

static int nr_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    nr.gen = nr_gen();
    nr_refresh(1);
    return RET_OK;
}

static int nr_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != nr.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    if (nr.timer) timer_remove(nr.timer);
    ls_spin_end(nr.spin);
    memset(&nr, 0, sizeof nr);
    return RET_OK;
}

static int nr_tick(const void *timer) {
    unsigned g;
    (void)timer;
    if (!nr.win) return RET_OK; /* (the destroy handler removes the timer: this only ends a stray one) */
    {
        int code = 0, st = sba_state(SBA_K_SYNC, "", &code);
        if (nr.sync == SBA_ST_LOAD && st == SBA_ST_FAIL)
            pod_toast(sbs_request_message(code, 0)); /* the sync this page watched ran and failed */
        nr.sync = st;
    }
    {
        int guard = sba_guard();
        if (nr.guard != SBA_OK && guard == SBA_OK)
            sba_sync_auto(); /* Wi-Fi came back while the page is up (or the clock got set after it, or the card is back): a due sync runs now, not at the next visit */
        nr.guard = guard;
    }
    g = nr_gen();
    if (g != nr.gen || ++nr.ticks % NR_FORCE_TICKS == 0) {
        nr.gen = g;
        nr_refresh(0);
    }
    return RET_REPEAT;
}

/* Open the Subsonic page (the menu row). 0 once it is up (or already open); -1 when it could not open. */
int nd_root_open(void) {
    int i;
    if (nr.win) return 0;
    memset(&nr, 0, sizeof nr);
    nr.shown = -1;
    nr.win = window_open("m1plus_ndroot");
    if (!nr.win) {
        memset(&nr, 0, sizeof nr);
        return -1;
    }
    widget_on(nr.win, EVT_DESTROY, nr_on_destroy, nr.win);
    widget_on(nr.win, EVT_WINDOW_TO_FG, nr_on_fg, (void *)0);
    pod_bind(nr.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(nr.win, "btn_backtoplayer", pod_on_player, (void *)0);
    nr.list = widget_lookup(nr.win, "nd_list", 1);
    nr.status = widget_lookup(nr.win, "nd_status", 1);
    nr.es_big = widget_lookup(nr.win, "nd_es_big", 1);
    nr.es_icon = widget_lookup(nr.win, "nd_es_icon", 1);
    nr.es_title = widget_lookup(nr.win, "nd_es_title", 1);
    nr.es_text = widget_lookup(nr.win, "nd_es_text", 1);
    nr.es_pill = pod_bind(nr.win, "nd_es_pill", nr_on_server, (void *)0);
    nr.es_dl = pod_bind(nr.win, "nd_es_dl", nr_on_downloaded, (void *)0);
    nr.icon = widget_lookup(nr.win, "nd_st_icon", 1);
    nr.spin = widget_lookup(nr.win, "nd_st_spin", 1);
    nr.foot = widget_lookup(nr.win, "nd_foot", 1);
    nr.sv = widget_lookup(nr.win, "pod_scrollview", 1);
    nr.title = widget_lookup(nr.win, "label_title", 1);
    nr.fade = widget_lookup(nr.win, "img_nb_fade", 1);
    nr.more = pod_bind(nr.win, "btn_more", nr_on_more, (void *)0);
    nr.search = pod_bind(nr.win, "btn_search", nr_on_search, (void *)0);
    if (!nr.list || !nr.status || !nr.es_big || !nr.es_icon || !nr.es_title || !nr.es_text || !nr.es_pill ||
        !nr.es_dl || !nr.icon || !nr.spin || !nr.foot || !nr.sv || !nr.title || !nr.fade || !nr.more || !nr.search ||
        vs_bind(&nr.vs, nr.win, nr_on_card, nr_on_scrim, VS_WITH_SELECT)) {
        navigator_back(); /* an asset that is not ours: the destroy handler clears the state */
        return -1;
    }
    for (i = 0; i < NR_ROWS; ++i) {
        char name[24];
        snprintf(name, sizeof name, "pod_row%d", i);
        if (!pod_bind(nr.win, name, nr_on_row, (void *)(long)i)) {
            navigator_back();
            return -1;
        }
    }
    nr.noscroll = !widget_on(nr.sv, EVT_SCROLL, nr_on_scroll, (void *)0) ||
                  !widget_on(nr.sv, EVT_SCROLL_END, nr_on_scroll,
                             (void *)0); /* without the scroll events the navbar keeps its title */
    if (nr.noscroll) widget_set_visible(nr.title, 1, 0);
    nr.title_on = nr.noscroll;
    nr.kind = -1;
    nr.nav = -1;
    label_set_line_wrap(nr.es_text, 1);
    widget_set_prop_bool(nr.es_text, "word_wrap", 1);
    sba_retire_old(); /* the pull request's old files, once */
    nr.guard = sba_guard();
    if (sba_configured()) sba_sync_auto();
    nr.gen = nr_gen();
    nr_refresh(0);
    nr.timer = timer_add(nr_tick, (void *)0, NR_TICK_MS);
    if (!nr.timer) {
        navigator_back();
        return -1;
    }
    return 0;
}
