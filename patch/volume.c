/* The Volume page: our full-page volume screen for the status bar tap (docs/modules/volume.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Stock opens its volume dialog (dialog/volume_dialog, modal) when the status bar's top strip is tapped (on_wm_tsup_fun 0x4cd8dc, `navigator_to_with_context(name, 2)` at 0x4cd964). That call becomes vol_tap_open
 * (tools/pod.py VOLUME_SITE, payload hook 33, tap only, never on the boot path): our page is left alone when it is in front, brought to the front (its sub-pages closed) when it is in the stack, opened when it is
 * not, and stock's own call is made when it will not open or when stock's volume dialog is the window in front (its strip, opened by the volume keys, keeps stock's behaviour). The keys' strip is untouched.
 *
 * The page holds the dialog's widgets by stock's names (vol_label, vol_slider, btn_dec, btn_add) and stock's own handlers are bound to them with the window as their context, as stock's dialog init binds them
 * (VOLUME_PINS): the slider's EVT_VALUE_CHANGING, the two buttons' EVT_CLICK, the window's EVT_KEY_UP (the hardware volume keys; the key handler is wrapped). The steps, the Max Volume cap, the Bluetooth volume,
 * set_devicevolume, the saves and reset_poweroptions_timer are stock's code; nothing of them is repeated here. Stock's refresh (0x47d664) writes vol_label and sets the slider from the volume word; the number
 * (pod_volnum) and the grey line (pod_volinfo) are ours, written from the same words after stock's code ran.
 *
 * Two traps of running the dialog's code on another window. Stock's refresh branches on the word volume_showpage (1: the key strip's widgets, otherwise the page's), so the page stores 2 before every refresh (the
 * only write of ours into stock's state). And every stock handler ends in the reset 0x47de2c, which adds the dialog's 3 s auto-close timer to the window (its callback closes the window, id in the property
 * "timer_idex"): our handler is bound to the same events first, so it runs after stock's, and removes that timer with stock's own stop (0x47d9f8); the key wrapper does it itself because stock's key handler
 * returns RET_STOP. If our handler cannot be bound, stock's is not bound either. The dialog's own timer, 0x12c / 0x12d and pointer-up handlers are never bound.
 *
 * The bar: vol_slider is stock's and invisible (it keeps the touch and the drag); over it pod_volbar, an insensitive view, is painted in its own EVT_BEFORE_PAINT from four baked images (a capsule track, a capsule fill
 * blitted up to the value so its edge is a straight cut, the speaker glyph in white and in black, split at the edge) and a Max tick. Every refresh invalidates it. Under the card, three rows (Max Volume, Equalizer, Volume &
 * Sound) are the generic Settings rows (patch/m1plus.c); volpage_go opens their pages without a second window.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "peqout.h"
#include "entries.h"

#define volume_word (*(volatile int *)G_VOLUME)
#define bt_volume (*(volatile int *)BT_VOLUME)
#define max_volume (*(volatile int *)MAX_VOLUME)
#define headset_output (*(volatile int *)HEADSET_OUTPUT)
#define vol_showpage (*(volatile int *)VOLP_SHOWPAGE)
#define VOLP_WINDOW "m1plus_volume_page" /* the page's window (the asset's root name) */
#define VOLP_BLUETOOTH 2 /* headset_output: stock's Bluetooth output */

/* The number and the grey line: "Headphones", or "Headphones · Max 80" while Max Volume is below 100 (stock does not apply Max Volume on Bluetooth, so no Max there). */
static void vp_text(void *win) {
    void *num = widget_lookup(win, "pod_volnum", 1), *info = widget_lookup(win, "pod_volinfo", 1);
    char buf[80];
    int bt = headset_output == VOLP_BLUETOOTH, out, n;
    const char *name;
    if (num) {
        snprintf(buf, sizeof buf, "%d", bt ? bt_volume : volume_word);
        widget_set_text_utf8(num, buf);
    }
    if (!info) return;
    out = peqout_current();
    name = bt ? TR("Bluetooth") : out == PO_LINEOUT ? TR("Line Out") : out == PO_USB ? TR("USB DAC") : TR("Headphones");
    n = snprintf(buf, sizeof buf, "%s", name);
    if (n > 0 && (unsigned)n < sizeof buf && !bt && max_volume < 100)
        snprintf(buf + n, sizeof buf - (unsigned)n, " \xc2\xb7 %s %d", TR("Max"), max_volume);
    widget_set_text_utf8(info, buf);
}

/* The bar's images (none: no memory or an asset that is not ours: nothing is painted). */
static struct {
    void *win, *track, *fill, *ink, *glyph;
} vb __attribute__((section(".scratch")));

static int vp_value(void) {
    int v = headset_output == VOLP_BLUETOOTH ? bt_volume : volume_word;
    return v < 0 ? 0 : v > 100 ? 100 : v;
}

/* One 1:1 blit of the part [sx, sx + w) of an image of height h at x, y. */
static void vp_blit(void *canvas, void *bmp, int sx, int w, int h, int x, int y) {
    int src[4], dst[4];
    if (!bmp || w <= 0) return;
    src[0] = sx, src[1] = 0, src[2] = w, src[3] = h;
    dst[0] = x, dst[1] = y, dst[2] = w, dst[3] = h;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* Half the tick's length in pixel column c: VB_H / 2 - VB_TICK_INSET in the straight part; in the half circles of the capsule's ends (radius VB_H / 2) the half chord at the column's centre, less 1 px, so the tick
 * stays inside the outline. 0: none fits. */
static int vp_chord(int c) {
    int r = VB_H / 2, half = r - VB_TICK_INSET, d = c < VB_W - 1 - c ? c : VB_W - 1 - c, dx2, v, h = 0;
    if (d >= r) return half;
    dx2 = 2 * r - (2 * d + 1); /* twice the distance from the circle's centre */
    v = r * r - dx2 * dx2 / 4; /* the half chord squared (floor) */
    while ((h + 1) * (h + 1) <= v) h++;
    return h - 1 < half ? h - 1 : half;
}

/* pod_volbar's EVT_BEFORE_PAINT: the track, the fill up to the value (a straight cut: the capsule's rounded ends come from the image), the Max tick (not on Bluetooth, where stock does not apply Max Volume), and the
 * speaker glyph: black where it is over the fill, white over the track. */
static int vp_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int fw, ix = VB_ICON_CX - VB_ICON / 2, iy = (VB_H - VB_ICON) / 2, cut;
    (void)ctx;
    if (!canvas || !vb.win || !vb.track || !vb.fill) return RET_OK;
    fw = vp_value() * VB_W / 100;
    vp_blit(canvas, vb.track, 0, VB_W, VB_H, 0, 0);
    vp_blit(canvas, vb.fill, 0, fw, VB_H, 0, 0);
    if (headset_output != VOLP_BLUETOOTH && max_volume >= 0 && max_volume < 100) {
        int tx = max_volume * VB_W / 100 - VB_TICK_W / 2;
        tx = tx < 0 ? 0 : tx > VB_W - VB_TICK_W ? VB_W - VB_TICK_W : tx;
        int half = vp_chord(tx), h2 = vp_chord(tx + VB_TICK_W - 1);
        half = h2 < half ? h2 : half; /* (the shorter of the tick's columns: it stays inside the capsule's end) */
        if (half > 0) {
            ui_fill_color(canvas, VB_TICK);
            canvas_fill_rect(canvas, tx, VB_H / 2 - half, VB_TICK_W, 2 * half);
        }
    }
    cut = fw - ix < 0 ? 0 : fw - ix > VB_ICON ? VB_ICON : fw - ix;
    vp_blit(canvas, vb.ink, 0, cut, VB_ICON, ix, iy);
    vp_blit(canvas, vb.glyph, cut, VB_ICON - cut, VB_ICON, ix + cut, iy);
    return RET_OK;
}

static int vp_gone(void *ctx, void *e) {
    (void)e;
    if (ctx != vb.win) return RET_OK;
    if (vb.track) bitmap_destroy(vb.track);
    if (vb.fill) bitmap_destroy(vb.fill);
    if (vb.ink) bitmap_destroy(vb.ink);
    if (vb.glyph) bitmap_destroy(vb.glyph);
    memset(&vb, 0, sizeof vb);
    return RET_OK;
}

/* Stock's refresh, then ours; the bar is painted again from the same words. */
static void vp_refresh(void *win) {
    void *bar = widget_lookup(win, "pod_volbar", 1);
    vol_showpage = 2;
    ((void (*)(void *))VOLP_REFRESH)(win);
    vp_text(win);
    if (bar) widget_invalidate_force(bar, (void *)0);
}

/* After stock's handler on the same event (ours is bound first): stock's reset has added the 3 s auto-close timer; stop it, then refresh. */
static int vp_after(void *win, void *e) {
    (void)e;
    ((void (*)(void *))VOLP_STOP)(win);
    vp_refresh(win);
    return RET_OK;
}

/* The window's EVT_KEY_UP: stock's key handler, which steps the volume on the volume keys and returns RET_STOP for them (else 0, the key is not ours). */
static int vp_key(void *win, void *e) {
    int ret;
    if (!e) return RET_OK;
    ret = ((int (*)(void *, void *))VOLP_KEY)(win, e);
    if (ret == RET_STOP) vp_after(win, e);
    return ret;
}

static int vp_fg(void *win, void *e) {
    (void)e;
    vp_refresh(win); /* a picker or Volume & Sound may have changed the volume, or a strip left volume_showpage at 1 */
    return RET_OK;
}

/* Our handler first, then stock's: a refused bind of ours leaves stock's unbound (it would add a timer nothing removes). */
static void vp_bind(void *w, int evt, unsigned stock, void *win) {
    if (w && widget_on(w, evt, (void *)vp_after, win)) widget_on(w, evt, (void *)stock, win);
}

void volpage_opened(void *win) {
    void *bar;
    if (!win) return;
    if (vb.win) vp_gone(vb.win, (void *)0); /* (a window of ours that was never told: not expected) */
    bar = widget_lookup(win, "pod_volbar", 1);
    if (bar) {
        vb.win = win;
        vb.track = m1_asset_rgba(win, "pod_vol_track", VB_W, VB_H, 0);
        vb.fill = m1_asset_rgba(win, "pod_vol_fill", VB_W, VB_H, 0);
        vb.ink = m1_asset_rgba(win, "pod_vol_ink", VB_ICON, VB_ICON, 0);
        vb.glyph = m1_asset_rgba(win, "pod_ci_volume", VB_ICON, VB_ICON, 0);
        widget_on(bar, EVT_BEFORE_PAINT, (void *)vp_paint, (void *)0);
        widget_on(win, EVT_DESTROY, (void *)vp_gone, win);
    }
    vp_refresh(win); /* before the handlers are bound: setting the slider is not a change to save */
    vp_bind(widget_lookup(win, "vol_slider", 1), EVT_VALUE_CHANGING, VOLP_SLIDER, win);
    vp_bind(widget_lookup(win, "btn_add", 1), EVT_CLICK, VOLP_ADD, win);
    vp_bind(widget_lookup(win, "btn_dec", 1), EVT_CLICK, VOLP_DEC, win);
    widget_on(win, EVT_KEY_UP, (void *)vp_key, win);
    widget_on(win, EVT_WINDOW_TO_FG, (void *)vp_fg, win);
}

/* The second card's rows (k: 0 Max Volume, 1 Equalizer, 2 Volume & Sound; the generic row handler of patch/m1plus.c calls this for the Volume page's rows): the target page by its window, as the pull-down's tiles do: in the stack, its
 * sub-pages are closed and it is restacked; else it is opened. */
void volpage_go(int k) {
    if (k == 0)
        pd_open_page("m1plus_psmaxvol_page", pod_open_psmaxvol, 0);
    else if (k == 1)
        pd_open_page("m1plus_peq_page", pod_open_peq, 0);
    else if (k == 2)
        pd_open_page("m1plus_psvolume_page", pod_open_psvolume, 0);
}

static int vp_top_is(const char *name) {
    void *wm = window_manager(), *top = wm ? window_manager_get_top_window(wm) : (void *)0;
    const char *nm = top ? *(const char **)((char *)top + WIDGET_NAME) : (const char *)0;
    return nm && !strcmp(nm, name);
}

/* Tap for Volume (VOLTAP_FILE, ours): 0 off, anything else on (the default). */
int vol_tap_on(void) { return set_read(VOLTAP_FILE, '1') != '0'; }

int vol_tap_toggle(void) { return home_set_digit(VOLTAP_FILE, !vol_tap_on(), 1); }

/* The hook at on_wm_tsup_fun's navigator_to_with_context("dialog/volume_dialog", 2) (the arguments are stock's: the delay slot still loads the name).
 * Stock's strip in front: stock's call. Tap for Volume off: nothing. Else our page, or stock's call if it will not open. */
int vol_tap_open(const char *name, int ctx) {
    if (vp_top_is("volume_dialog")) return navigator_to_with_context(name, (const void *)(long)ctx);
    if (!vol_tap_on()) return RET_OK;
    if (pd_open_page(VOLP_WINDOW, pod_open_volume, 1)) return RET_OK;
    return navigator_to_with_context(name, (const void *)(long)ctx);
}
