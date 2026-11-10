/* M1+ Music lock screen layout: stock's screensaver_page shows the playing track as a large glass card with the 264 px cover. With the setting
 * /mnt/data/m1plus/lockscreen-layout = "1" the same widgets are laid out as the Home mini player bar at the bottom of the screen instead, and drawn like it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One hook, screensaver_page_init (0x53fd44, tools/pod.py LOCKSCREEN_INIT, payload hook 25): the page's init, run by the navigator's page-init dispatcher whenever the lock screen
 * is built. It runs the stock init to completion and returns its result. Only when that result is RET_OK, the window is valid, /mnt/mmc/m1plus-off is absent and the setting file
 * reads "1", the six stock widgets of the track card (view_bottomview, view_img_icon, view_scrlabel_title, view_scrlabel_artist, btn_play, btn_next) are moved and resized to the
 * mini layout (offsets.inc LK_*, MB_*), the card gets the mb_glass image and the two labels their sizes and colours. Every widget is looked up before any geometry changes: a missing one
 * leaves the large layout as the asset has it. Then lk_start takes the bar over like patch/minibar.c's: our own rounded cover bitmap (mb_art_*), the Home glyphs on play and next,
 * one-line labels, the backdrop blur (mb_blur_*), driven by one page timer and the window's events. Stock's refresh, play and next handlers, and its hiding (and disabling) of the card
 * while nothing is queued, keep working on the same widgets; stock's own cover widget is hidden. Any refused registration or timer leaves the moved stock widgets with their own cover
 * and glyphs. The file is read once per page init and never written here; a change applies the next time the lock screen opens. docs/modules/lockscreen.md.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "minibar.h"
#include "common.h"
#include "palette.h"

#define LK_N 6

/* The widgets in the order lk_find fills them, and the rectangles they take (card in window coordinates, the others in the card). */
static const char *const lk_names[LK_N] = {"view_bottomview",      "view_img_icon", "view_scrlabel_title",
                                           "view_scrlabel_artist", "btn_play",      "btn_next"};
static const int lk_rect[LK_N][4] = {
    {LK_MINI_X, LK_MINI_Y, MB_W, MB_H},
    {MB_ART_X, MB_ART_Y, MB_ART, MB_ART},
    {MB_TEXT_X, MB_TITLE_Y, MB_TEXT_W, MB_TITLE_H},
    {MB_TEXT_X, MB_ARTIST_Y, MB_TEXT_W, MB_ARTIST_H},
    {MB_PLAY_X, 0, MB_BTN_W, MB_H},
    {MB_NEXT_X, 0, MB_BTN_W, MB_H},
};

/* The three states the asset's card and labels set: their style names are "<state>:<property>" for widget_set_style and "style:<state>:<property>" for the string setter. */
static void lk_font(void *w, int px) {
    static const char *const key[3] = {"normal:font_size", "disable:font_size", "focused:font_size"};
    unsigned v[4];
    int i;
    for (i = 0; i < 3; ++i) {
        memset(v, 0, sizeof v);
        value_set_uint32(v, (unsigned)px);
        widget_set_style(w, key[i], v);
    }
}

static void lk_str(void *w, const char *prop, const char *val) {
    static const char *const state[3] = {"normal", "disable", "focused"};
    char name[40];
    int i;
    for (i = 0; i < 3; ++i) {
        snprintf(name, sizeof name, "style:%s:%s", state[i], prop);
        widget_set_prop_str(w, name, val);
    }
}

/* The mini layout, the widgets left in w; false (nothing changed) when a widget is missing. */
static int lk_mini(void *win, void **w) {
    int i;
    for (i = 0; i < LK_N; ++i) {
        w[i] = widget_lookup(win, lk_names[i], 1);
        if (!w[i]) return 0;
    }
    for (i = 0; i < LK_N; ++i) {
        widget_move(w[i], lk_rect[i][0], lk_rect[i][1]);
        widget_resize(w[i], lk_rect[i][2], lk_rect[i][3]);
    }
    lk_str(w[0], "bg_image", "mb_glass"); /* the asset's card already has a transparent bg_color */
    lk_font(w[2], LK_TITLE_PX);
    lk_font(w[3], LK_ARTIST_PX);
    lk_str(w[3], "text_color", LK_ARTIST_RGB);
    return 1;
}

int lk_layout(void);

/* ---------------------------------------------------------------------------
 * The bar as the Home bar draws it (patch/minibar.c shares the cover and the blur): the cover is our own rounded bitmap, the glyphs are the Home bar's, the pill behind it is blurred.
 * One page-scoped timer; nothing runs after the window's destroy.
 */
#define LK_TICK_MS \
    100 /* lit: a stock glyph swap is put right within this; the blur's partial frames are repaired within it */
#define LK_PAUSE_STYLE "btn_imgpause1_style"

static struct {
    void *win, *card, *icon, *title, *artist, *play, *next;
    unsigned timer; /* the one-shot or the repeating timer, 0 none */
    unsigned interval; /* repeating timer interval last accepted by timer_modify */
    int fg; /* the window is in front */
    int playing; /* the glyph made: 1 pause, 0 play, -1 none yet */
    int kind; /* the style stock's play button used when it was made: 1 btn_imgpause1_style, 0 the other, -1 none yet */
    unsigned key; /* the track the cover was made for, 0 none */
    mb_art_t art;
    mb_blur_t bl;
} lk __attribute__((section(".scratch")));

/* The play button's glyph. Stock swaps the button's own style (widget_use_style) between its pause and play styles and only when the status changes; the glyphs are overrides in the
 * widget's mutable style (the way the Home bar sets them), so they hold over either theme style. Made again whenever the status differs from the one shown or stock's style name changed
 * since (a swap that cleared them would show the large np_ glyph for at most one tick). */
static void lk_play_look(int playing) {
    static const char *const key[3] = {"style:normal:icon", "style:over:icon", "style:pressed:icon"};
    const char *g = playing ? "mb_pause" : "mb_play", *d = playing ? "mb_pause_down" : "mb_play_down";
    int i;
    for (i = 0; i < 3; ++i) widget_set_prop_str(lk.play, key[i], i == 2 ? d : g);
}

static void lk_glyph(void) {
    int playing = mclGetPlayStatus() == MB_PLAYING;
    const char *name = *(const char *const *)((char *)lk.play + WIDGET_STYLE);
    int kind = name && strcmp(name, LK_PAUSE_STYLE) == 0;
    if (playing == lk.playing && kind == lk.kind) return;
    lk.playing = playing;
    lk.kind = kind;
    lk_play_look(playing);
    widget_invalidate_force(lk.card, (void *)0); /* the whole pill, not the glyph's rectangle (see the blur) */
}

/* The next button: the Home bar's glyph (the page's own is the bg_image np_next, cleared). */
static void lk_next_look(void) {
    static const char *const state[5] = {"normal", "disable", "focused", "over", "pressed"};
    char name[40];
    int i;
    for (i = 0; i < 5; ++i) {
        snprintf(name, sizeof name, "style:%s:bg_image", state[i]);
        widget_set_prop_str(lk.next, name, "");
    }
    widget_set_prop_str(lk.next, "style:normal:icon", "mb_next");
    widget_set_prop_str(lk.next, "style:over:icon", "mb_next");
    widget_set_prop_str(lk.next, "style:pressed:icon", "mb_next_down");
}

static void lk_work(void) {
    void *t = cc_playing();
    unsigned key;
    if (!t) { /* nothing queued: stock hides the card */
        lk.key = 0;
        return;
    }
    key = mb_track_key(t);
    if (key != lk.key) {
        lk.key = key;
        if (mb_art_cover(&lk.art, lk.win, t, 1)) widget_invalidate_force(lk.card, (void *)0);
    } else if (lk.art.settle > 0 && mb_art_settle(&lk.art, lk.win, t))
        widget_invalidate_force(lk.card, (void *)0);
    lk_glyph();
    if (widget_get_visible(lk.icon)) widget_set_visible(lk.icon, 0, 0); /* stock's cover never shows over ours */
    if (lk.bl.fix) { /* a frame under the pill was partial: the whole pill again, so the blur is not seamed */
        lk.bl.fix = 0;
        widget_invalidate_force(lk.card, (void *)0);
    }
}

static int lk_tick(const void *timer) {
    unsigned want;
    (void)timer;
    if (!lk.win || !lk.fg) {
        lk.timer = 0;
        return RET_OK;
    }
    want = pod_screen_lit()
               ? LK_TICK_MS
               : POD_DARK_MS; /* dark: a key compare a second, so the cover is right when the screen wakes */
    if (lk.timer && lk.interval != want && timer_modify(lk.timer, want) == RET_OK) lk.interval = want;
    lk_work();
    return RET_REPEAT;
}

static int lk_first(const void *timer) {
    (void)timer;
    lk.timer = 0; /* this one ends with the return */
    if (!lk.win || !lk.fg) return RET_OK;
    lk.timer = timer_add(lk_tick, (void *)0, LK_TICK_MS);
    lk.interval = LK_TICK_MS;
    if (lk.timer) lk_work();
    return RET_OK;
}

static void lk_unarm(void) {
    if (lk.timer) timer_remove(lk.timer);
    lk.timer = 0;
}

static void lk_stop(void) {
    lk_unarm();
    mb_art_free(&lk.art);
    mb_blur_free(&lk.bl);
    memset(&lk, 0, sizeof lk);
}

static int lk_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == lk.win) lk_stop(); /* an earlier window's end leaves the new one alone */
    return RET_OK;
}

static int lk_on_background(void *ctx, void *e) {
    (void)e;
    if (!lk.win || ctx != lk.win) return RET_OK;
    lk.fg = 0;
    lk_unarm();
    return RET_OK;
}

static int lk_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!lk.win || ctx != lk.win) return RET_OK;
    lk.fg = 1;
    if (!lk.timer) lk.timer = timer_add(lk_first, (void *)0, MB_FIRST_MS);
    return RET_OK;
}

/* The card's EVT_AFTER_PAINT: the resident cover, as the Home bar draws it. Nothing is decoded here. */
static int lk_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (canvas && lk.win && lk.key) mb_art_paint(&lk.art, canvas);
    return RET_OK;
}

static int lk_on_before_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (canvas && lk.win) mb_blur_paint(&lk.bl, canvas);
    return RET_OK;
}

/* A press, release or abort on a button repaints only its rectangle: the whole pill is invalidated so the frame is not partial. */
static int lk_on_touch(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (lk.win && lk.bl.on) widget_invalidate_force(lk.card, (void *)0);
    return RET_OK;
}

/* The blur is optional and last (no plane, the SD file m1plus-noblur or a refused handler: the glass over the sharp wallpaper). */
static void lk_blur_setup(void) {
    static void *const *btn[2] = {&lk.play, &lk.next};
    static const int ev[3] = {EVT_POINTER_DOWN, EVT_POINTER_UP, EVT_POINTER_ABORT};
    int ok, i, j;
    if (!mb_blur_alloc(&lk.bl)) return;
    ok = widget_on(lk.card, EVT_BEFORE_PAINT, lk_on_before_paint, (void *)0) != 0;
    for (i = 0; ok && i < 2; ++i)
        for (j = 0; ok && j < 3; ++j) ok = widget_on(*btn[i], ev[j], lk_on_touch, (void *)0) != 0;
    if (ok)
        mb_blur_enable(&lk.bl);
    else
        mb_blur_free(&lk.bl);
}

/* The lock page's bar is laid out (lk_mini): take over its cover and glyphs. Anything missing or refused leaves stock's cover and glyphs as lk_mini left them (the moved stock widgets). */
static void lk_start(void *win, void *const *w) {
    if (lk.win) { /* an earlier page that never said it was gone */
        lk_stop();
    }
    lk.win = win;
    lk.card = w[0], lk.icon = w[1], lk.title = w[2], lk.artist = w[3], lk.play = w[4], lk.next = w[5];
    lk.playing = lk.kind = -1;
    lk.fg = 1;
    if (!widget_on(win, EVT_DESTROY, lk_on_destroy, win) || !widget_on(win, EVT_WINDOW_TO_BG, lk_on_background, win) ||
        !widget_on(win, EVT_WINDOW_TO_FG, lk_on_foreground, win) ||
        !widget_on(lk.card, EVT_AFTER_PAINT, lk_on_paint, (void *)0)) {
        lk_stop(); /* a handler that was registered finds no window of ours any more */
        return;
    }
    lk.timer = timer_add(lk_first, (void *)0, MB_FIRST_MS);
    if (!lk.timer) {
        lk_stop();
        return;
    }
    lk_blur_setup();
    /* the look is taken over only now that everything runs: the Home bar's one-line labels, glyphs and no stock cover */
    widget_set_prop_int(lk.title, "ellipses", 1);
    widget_set_prop_int(lk.title, "only_parent_focus", 1);
    widget_set_prop_int(lk.artist, "ellipses", 1);
    widget_set_prop_int(lk.artist, "only_parent_focus", 1);
    lk_next_look();
    widget_set_visible(lk.icon, 0, 0);
}

/* The hook (tools/pod.py LOCKSCREEN_INIT): stock first, then ours. */
int m1plus_lockscreen_init(void *win, void *ctx) {
    int ret = stock_lockscreen_init_trampoline(win, ctx);
    void *w[LK_N];
    if (ret == RET_OK && win && access(KILL_SD, F_OK) != 0 && lk_layout() == 1 && lk_mini(win, w)) lk_start(win, w);
    return ret;
}

/* The lock screen switch is stock's own state: the byte screensaver_mode (LOCK_ON, loaded from [SYSSET] SCREENSAVER by config_init; into_standby and the key handler read it each time the screen
 * goes dark, 0 = no lock screen) and the saved key. Stock's click handler (0x4aba34) only works inside its own page (it looks image_switch up there), so this repeats its two steps in its order. */
int lk_enabled(void) { return *(volatile unsigned char *)LOCK_ON != 0; }

int lk_enabled_toggle(void) {
    int next = !lk_enabled();
    *(volatile unsigned char *)LOCK_ON = (unsigned char)next;
    write_int_config(next, "SYSSET", "SCREENSAVER");
    return next;
}

/* Show Time is stock's own state too: the byte screensaver_timeshow (LOCK_TIMESHOW, loaded from [SYSSET] SSAVERTIMESHOW by config_init, 0 or 1) that the lock screen's visitor reads each time the lock screen is built
 * (view_timeinfo shown and enabled, or hidden). Stock's click handler 0x4ab984 stores the byte xor 1 in the delay slot of write_int_config(new, "SYSSET", "SSAVERTIMESHOW"): the byte first, then the save. Like Enable's,
 * it only works inside stock's page (it looks img_timeswitch up there), so this repeats its two steps in its order. The new state, there is no failed save (stock ignores write_int_config's result too). */
int lk_time(void) { return *(volatile unsigned char *)LOCK_TIMESHOW != 0; }

int lk_time_toggle(void) {
    int next = *(volatile unsigned char *)LOCK_TIMESHOW ^ 1;
    *(volatile unsigned char *)LOCK_TIMESHOW = (unsigned char)next;
    write_int_config(next, "SYSSET", "SSAVERTIMESHOW");
    return next != 0;
}

/* Stock's Display page Lock Screen row (the pod_lock_site stub, tools/pod.py LOCKROW) opens our Lock Screen page instead of systemset/screensaver_page. 1 once ours is opening; 0 on the kill switch or when the page
 * will not open: the stub then does stock's own navigator_to. A row tap only, not on the boot path. */
extern int pod_open_lock(void);
int lk_redirect(void) { return access(KILL_SD, F_OK) != 0 && pod_open_lock() == 0; }

/* The saved layout: 1 Mini Player ('1', an optional newline), anything else or no file 0 Large Cover; reading never writes. */
int lk_layout(void) { return set_read(LK_LAYOUT_FILE, 0) == '1'; }

/* Choose the layout (0 Large Cover, 1 Mini Player), saved atomically; the layout, or -1 (unknown, or not saved: the saved one is unchanged). It applies the next time the lock screen opens. */
int lk_layout_set(int layout) {
    static const char *const text[2] = {"0\n", "1\n"};
    if (layout < 0 || layout > 1) return -1;
    return home_write_atomic(LK_LAYOUT_FILE, LK_LAYOUT_TMP, text[layout]) == 0 ? layout : -1;
}

/* ---------------------------------------------------------------------------
 * The Wallpaper picker (Settings > Lock Screen > Wallpaper, page m1plus_lockwall; docs/modules/lockscreen.md "Wallpaper picker").
 *
 * Stock's systemset/screensaver_page lists the wallpaper in a grid it builds in code (init 0x4abe04, cell builder 0x4abb3c, tap handler 0x4ab52c). This is the same grid under our navbar, with the same entries
 * and the same writes, so stock's page, stock's lock screen and ours always agree; no file of ours.
 *  - The entries are stock's: get_screensaver_image (0x4d7524, the call stock's init makes first) fills the deque pdeq_screensaverlist (LOCK_LIST) with the name "screensaver_default" and then the pictures of
 *    /mnt/mmc/lockscreenimage that stock accepts (up to five .jpg / .png / .jpeg of exactly 320 x 480 under 1 MiB, in directory order), and puts a chosen picture that can no longer be read back to the default.
 *    The strings are copied (lw.path): a later stock page that rebuilds the deque cannot change what a tap of ours writes.
 *  - A tap on another entry than the chosen one does what stock's handler does, in its order: the old mark off, the new mark on, the global screensaver_picture (LOCK_PICTURE) = the entry, then
 *    toolsWriteConfig("/mnt/data/config.ini", "SYSSET", "SCREENSAVERPATH", picture). No refresh flag. The lock screen reads the global every time it is built; config_init reads the key at boot.
 *  - The chosen entry is found by comparing the strings with screensaver_picture (stock's way). When it is none of the entries (a readable picture that is no longer accepted) no cell is marked, and a tap on
 *    Default writes (stock's handler does nothing then: it takes cell 0 as the old one and returns at once).
 *  - Thumbnails are the widgets' own images (image_base_set_image: the resource name for Default, "file://<path>" for a picture, drawn by AWTK's scale_auto into 90 x 135 as stock draws them). Stock decodes each picture
 *    twice before its page is shown; here a picture is set per timer tick (LW_TICK_MS) so the page is up at once and the decodes (the first paint after each set) come one at a time between touches.
 */
#define LW_N 6 /* the Default entry and up to five pictures */
#define LW_PATH 208 /* stock's own limit: directory + name < 201 characters, and a NUL */
#define LW_TICK_MS 40
#define LW_CLEAR_RGB "#00000000"
#define LW_CONFIG "/mnt/data/config.ini"
#define LW_DEFAULT "screensaver_default"
#define LW_PICTURE_SIZE 0x100 /* the size stock gives screensaver_picture */

static struct {
    void *win, *cell[LW_N], *mark[LW_N];
    unsigned timer; /* the thumbnail timer, 0 none */
    int n; /* entries shown */
    int next; /* the next entry whose picture is still to be set */
    int fg; /* the page is in front */
    char path[LW_N][LW_PATH];
} lw __attribute__((section(".scratch")));

/* The entry that is the chosen picture, -1 when none of them is. */
static int lw_chosen(void) {
    int i;
    for (i = 0; i < lw.n; ++i)
        if (strcmp(lw.path[i], (const char *)LOCK_PICTURE) == 0) return i;
    return -1;
}

/* Stock: widget_use_style(cell, picture_selected_style / picture_unselect_style), then image_base_set_image(mark, screensaver_selected / screensaver_unselect).
 * Stock's selected border is orange (#FE7E40); ours is the accent (pal_fill: Neutral's #EEEEEC by default and under the kill switch), as the payload draws it (ui_ink: dark in Light Mode when neutral). */
static void lw_mark(int i, int on) {
    static const char hex[] = "0123456789ABCDEF";
    char rgb[8];
    unsigned c = ui_ink(pal_fill()); /* color_t: bytes r, g, b, a */
    int k;
    rgb[0] = '#';
    for (k = 0; k < 3; ++k) {
        unsigned b = (c >> (8 * k)) & 0xff;
        rgb[1 + 2 * k] = hex[b >> 4];
        rgb[2 + 2 * k] = hex[b & 15];
    }
    rgb[7] = 0;
    lk_str(lw.cell[i], "border_color", on ? rgb : LW_CLEAR_RGB);
    image_base_set_image(lw.mark[i], on ? "screensaver_selected" : "screensaver_unselect");
}

static void lw_marks(void) {
    int i, c = lw_chosen();
    for (i = 0; i < lw.n; ++i) lw_mark(i, i == c);
}

static void lw_load(int i) {
    char url[LW_PATH + 8];
    if (i == 0) {
        image_base_set_image(lw.cell[0], lw.path[0]); /* the resource */
        return;
    }
    snprintf(url, sizeof url, "file://%s", lw.path[i]);
    image_base_set_image(lw.cell[i], url);
}

static int lw_tick(const void *timer) {
    (void)timer;
    if (!lw.win || !lw.fg) {
        lw.timer = 0;
        return RET_OK;
    }
    if (lw.next < lw.n) lw_load(lw.next++);
    if (lw.next < lw.n) return RET_REPEAT;
    lw.timer = 0;
    return RET_OK;
}

static void lw_unarm(void) {
    if (lw.timer) timer_remove(lw.timer);
    lw.timer = 0;
}

/* Arm the thumbnail timer; a refused timer loads the rest at once (stock's own way). */
static void lw_arm(void) {
    if (lw.next >= lw.n || lw.timer) return;
    lw.timer = timer_add(lw_tick, (void *)0, LW_TICK_MS);
    while (!lw.timer && lw.next < lw.n) lw_load(lw.next++);
}

static int lw_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != lw.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    lw_unarm();
    memset(&lw, 0, sizeof lw);
    return RET_OK;
}

static int lw_on_background(void *ctx, void *e) {
    (void)e;
    if (!lw.win || ctx != lw.win) return RET_OK;
    lw.fg = 0;
    lw_unarm();
    return RET_OK;
}

/* Back in front: the choice may have been changed on stock's page meanwhile (the entries are the ones listed when the page opened). */
static int lw_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!lw.win || ctx != lw.win) return RET_OK;
    lw.fg = 1;
    lw_marks();
    lw_arm();
    return RET_OK;
}

/* Stock's tap handler 0x4ab52c for cell i. */
static int lw_on_click(void *ctx, void *e) {
    int i = (int)(unsigned long)ctx - 1, old;
    (void)e;
    if (!lw.win || i < 0 || i >= lw.n) return RET_OK;
    old = lw_chosen();
    if (i == old) return RET_OK; /* the chosen one again: nothing */
    if (old >= 0) lw_mark(old, 0);
    lw_mark(i, 1);
    snprintf((char *)LOCK_PICTURE, LW_PICTURE_SIZE, "%s", lw.path[i]);
    toolsWriteConfig(LW_CONFIG, "SYSSET", "SCREENSAVERPATH", (const char *)LOCK_PICTURE);
    return RET_OK;
}

/* Open the picker from the Lock Screen page's Wallpaper row. 0 once it is up (or already open); -1 when it could not open (nothing is left of it). */
int lkwp_open(void) {
    char name[16];
    void *list;
    int i, n, ok = 1;
    if (lw.win) return 0;
    memset(&lw, 0, sizeof lw);
    lw.win = window_open("m1plus_lockwall");
    if (!lw.win) {
        memset(&lw, 0, sizeof lw);
        return -1;
    }
    lw.fg = 1;
    for (i = 0; i < LW_N && ok; ++i) {
        snprintf(name, sizeof name, "imgcover%d", i);
        lw.cell[i] = widget_lookup(lw.win, name, 1);
        snprintf(name, sizeof name, "img_choice%d", i);
        lw.mark[i] = widget_lookup(lw.win, name, 1);
        ok = lw.cell[i] && lw.mark[i];
    }
    if (ok)
        ok = widget_on(lw.win, EVT_DESTROY, lw_on_destroy, lw.win) &&
             widget_on(lw.win, EVT_WINDOW_TO_BG, lw_on_background, lw.win) &&
             widget_on(lw.win, EVT_WINDOW_TO_FG, lw_on_foreground, lw.win);
    if (!ok) {
        navigator_back(); /* an asset that is not ours, or a refused handler: the destroy handler (if bound) forgets the state */
        if (lw.win) memset(&lw, 0, sizeof lw);
        return -1;
    }
    pod_bind(lw.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(lw.win, "btn_backtoplayer", pod_on_player, (void *)0);
    get_screensaver_image(); /* stock's list, first (it may set an unreadable chosen picture back to the default) */
    list = *(void **)LOCK_LIST;
    n = list ? (int)deque_size(list) : 0;
    if (n > LW_N) n = LW_N;
    for (i = 0; i < n; ++i) {
        const char *s = (const char *)deque_at(list, (unsigned)i);
        snprintf(lw.path[i], LW_PATH, "%s", s ? s : "");
    }
    if (n < 1) { /* no list at all: the Default entry alone */
        n = 1;
        snprintf(lw.path[0], LW_PATH, "%s", LW_DEFAULT);
    }
    lw.n = n;
    for (i = 0; i < n; ++i) {
        widget_on(lw.cell[i], EVT_CLICK, lw_on_click,
                  (void *)(unsigned long)(i + 1)); /* (a refused one leaves that cell without a tap) */
        widget_set_visible(lw.cell[i], 1, 0);
        widget_set_sensitive(lw.cell[i], 1);
    }
    lw_marks();
    lw_load(0); /* Default: a resource, cheap */
    lw.next = 1;
    lw_arm();
    widget_invalidate_force(lw.win, (void *)0);
    return 0;
}
