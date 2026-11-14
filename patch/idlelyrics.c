/* M1+ Music: the idle lyrics page, a full-screen page of our own that opens over Now Playing (docs/modules/idlelyrics.md). A header (the cover, the title and the artist: no controls)
 * over the lyrics, which the lyrics engine (patch/lyrics.c, retargeted at this page's view by ly_retarget) lays out in a 372 px view.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The page is ui/m1plus_idlelyrics.bin (tools/pod_ui.py build_idlelyrics_page): a fullscreen 320 x 480 window (no status bar) with Now Playing's theme, the cover tint and the lyrics scrim as insensitive images, il_view (the
 * touch target over the window, which paints the rounded cover in its own EVT_AFTER_PAINT: the mini bar's mb_art_* machinery at 56 px, patch/minibar.c), the title and the artist (hscroll_labels that
 * end in an ellipsis), il_lyrics (the engine's view) and the hint "No Lyrics Found". Like the Cassette page (patch/tape.c): no hook, one page-scoped timer set in place with timer_modify, an
 * EVT_DESTROY handler that gives everything back, nothing at boot; every failure of the open leaves nothing behind (-1). The lines are Now Playing's stock rows, which stock keeps building under
 * another window; Now Playing's own lyrics pane is parked by ly_retarget and comes back at ly_release (the destroy, or Now Playing in front again: ly_refresh).
 *
 * Touch: a tap anywhere closes the page (window_close on its own window); a vertical drag over the lyrics browses them (the engine's listeners on il_lyrics); no tap seeks. The keys keep their stock actions.
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "common.h"
#include "covercache.h"
#include "minibar.h"
#include "lyrics.h"
#include "entries.h"

static struct {
    void *win, *view, *title, *artist, *box, *hint;
    unsigned timer, key, color;
    int first, closing, hint_on, down, moved, sx, sy;
    mb_art_t art;
} il __attribute__((section(".scratch")));

static void il_free(void) {
    m1_timer_stop(&il.timer);
    mb_art_free(&il.art);
}

/* The window's colour, as Now Playing sets its own (np_set_color). */
static void il_color(unsigned c) {
    unsigned v[4];
    if (c == il.color) return;
    memset(v, 0, sizeof v);
    value_set_uint32(v, c);
    if (widget_set_style(il.win, "normal:bg_color", v) != RET_OK) return;
    il.color = c;
    widget_invalidate_force(il.win, (void *)0);
}

/* Closes the page's own window, not whatever is on top: Now Playing may be in front when the tick finds the engine gone (navigator_back would close it). */
static void il_close(void) {
    void *w = il.win;
    if (il.closing || !w) return;
    il.closing = 1;
    window_close(w);
}

/* The title, the artist and the cover follow the playing track. */
static void il_track(void *t) {
    unsigned key = t ? mb_track_key(t) : 0;
    if (key != il.key) {
        const char *title = t ? cc_str(t, REC_TITLE) : "";
        if (t && !*title) title = cc_str(t, REC_NAME);
        il.key = key;
        widget_set_text_utf8(il.title, title);
        widget_set_text_utf8(il.artist, t ? cc_str(t, REC_ARTIST) : "");
        if (t)
            mb_art_cover(&il.art, il.win, t, 1);
        else
            mb_art_free(&il.art);
        widget_invalidate_force(il.view, (void *)0);
    } else if (t && il.art.settle > 0 && mb_art_settle(&il.art, il.win, t)) {
        widget_invalidate_force(il.view, (void *)0);
    }
}

/* The one thing the timer does. The engine gone (Now Playing ended, or took its view back) closes the page. */
static void il_work(void) {
    int none;
    if (ly_target() != il.box) {
        il_close();
        return;
    }
    if (!m1_screen_lit()) return;
    il_color(np_idle_color());
    il_track(cc_playing());
    ly_tick();
    none = ly_lines() == 0;
    if (none != il.hint_on) {
        il.hint_on = none;
        widget_set_visible(il.hint, none, 0);
        widget_set_sensitive(
            il.hint, 0); /* (hidden and insensitive; shown, it still takes no touch: the page's tap is il_view's) */
    }
}

static int il_tick(const void *timer) {
    (void)timer;
    if (!il.win) return RET_OK; /* not ours any more: a timer that returns RET_OK ends */
    il_work();
    if (il.first) { /* the first look came early (the window's first paint is not delayed); from here on twice a second */
        il.first = 0;
        timer_modify(il.timer, IL_TICK_MS);
    }
    return RET_REPEAT;
}

static int il_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (il.win) mb_art_paint_at(&il.art, canvas, IL_ART_X, IL_ART_Y);
    return RET_OK;
}

/* DOWN, MOVE, UP and ABORT of il_view and of il_lyrics (the engine's own listeners on il_lyrics see the same events): a touch that stays under LY_TAP_PX closes the page. Nothing is grabbed,
 * every answer is RET_OK, so the pull-down and the window manager see every drag as on any page. */
static int il_on_touch(void *ctx, void *e) {
    int type, x, y;
    (void)ctx;
    if (!e || !il.win) return RET_OK;
    type = *(int *)e;
    x = *(int *)((char *)e + PE_X), y = *(int *)((char *)e + PE_Y);
    if (type == EVT_POINTER_DOWN) {
        il.down = 1, il.moved = 0, il.sx = x, il.sy = y;
    } else if (type == EVT_POINTER_MOVE && il.down) {
        if (m1_abs(x - il.sx) >= LY_TAP_PX || m1_abs(y - il.sy) >= LY_TAP_PX) il.moved = 1;
    } else if (type == EVT_POINTER_UP && il.down) {
        il.down = 0;
        if (!il.moved && m1_abs(x - il.sx) < LY_TAP_PX && m1_abs(y - il.sy) < LY_TAP_PX) il_close();
    } else if (type == EVT_POINTER_ABORT) {
        il.down = 0;
    }
    return RET_OK;
}

static int il_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != il.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    ly_release();
    il_free();
    memset(&il, 0, sizeof il);
    return RET_OK;
}

/* 0 once the page is up (or already open); -1 when it could not open, with nothing left of it and Now Playing's lyrics as they were. */
static int il_open(void) {
    void *np = np_window();
    if (il.win) return 0;
    memset(&il, 0, sizeof il);
    if (!np || !ly_target())
        return -1; /* no Now Playing to open over, or its lyrics engine is not running: nothing was made */
    il.win = window_open("m1plus_idlelyrics");
    if (!il.win) {
        memset(&il, 0, sizeof il);
        return -1;
    }
    if (widget_on(il.win, EVT_DESTROY, il_on_destroy, il.win)) {
        il.view = widget_lookup(il.win, "il_view", 1);
        il.title = widget_lookup(il.win, "il_title", 1);
        il.artist = widget_lookup(il.win, "il_artist", 1);
        il.box = widget_lookup(il.win, "il_lyrics", 1);
        il.hint = widget_lookup(il.win, "il_hint", 1);
        if (il.view && il.title && il.artist && il.box && il.hint && ly_retarget(il.win, il.box, IL_BOX_H) == 0) {
            mb_art_size(&il.art, IL_ART, IL_ART_R);
            il.timer = timer_add(il_tick, (void *)0, IL_FIRST_MS);
            if (il.timer) {
                il.first = 1;
                widget_on(il.view, EVT_AFTER_PAINT, il_on_paint, (void *)0);
                widget_on(il.view, EVT_POINTER_DOWN, il_on_touch, (void *)0);
                widget_on(il.view, EVT_POINTER_MOVE, il_on_touch, (void *)0);
                widget_on(il.view, EVT_POINTER_UP, il_on_touch, (void *)0);
                widget_on(il.view, EVT_POINTER_ABORT, il_on_touch, (void *)0);
                widget_on(il.box, EVT_POINTER_DOWN, il_on_touch, (void *)0);
                widget_on(il.box, EVT_POINTER_MOVE, il_on_touch, (void *)0);
                widget_on(il.box, EVT_POINTER_UP, il_on_touch, (void *)0);
                widget_on(il.box, EVT_POINTER_ABORT, il_on_touch, (void *)0);
                return 0;
            }
            ly_release(); /* the engine back to Now Playing; the page's own pool goes with its window */
        }
    }
    il_free();
    il.win = (void *)0; /* (its destroy handler leaves a newer page alone) */
    navigator_back();
    memset(&il, 0, sizeof il);
    return -1;
}

/* Open for Now Playing's idle timer (patch/bigcover.c bc_timed_open): 0 once the page is up or already open, else -1. Whether the track has lyrics is the dispatcher's question (ly_has_rows);
 * once the page is up a track without lyrics keeps it, with its hint. */
int idlelyrics_open_idle(void) { return il_open(); }

/* The page is up (the dispatcher leaves it alone even when the track has no rows). */
int idlelyrics_up(void) { return il.win != (void *)0; }
