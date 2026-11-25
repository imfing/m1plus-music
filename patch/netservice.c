/* M1+ Music Settings > Network Services and Wi-Fi Transfer (docs/modules/wifi-transfer.md): the state behind our two pages.
 *
 * AirPlay and DLNA are stock's own switches, the bytes airplayflag and dlnaflag (the Control Center tiles flip the same two): the toggles call stock's airplay_switch and dlna_switch, which flip the byte and
 * write the settings ini, and nothing else, as stock's page does (its click handlers, 0x4a8a84 and 0x4a8b14, test nothing before the call). The service itself follows the byte within the network-status
 * timer's second. Turning one on without Wi-Fi says why nothing starts, as the tiles do.
 *
 * Wi-Fi Transfer repeats stock's systemset/wifitransport_page (init 0x4b1664, tools/pod_pins.py NETSERVICE_PINS): it binds the key filter and the close handler, then stop_player and
 * switch_wifitransport(1), which runs thttpd and sets the byte wifitransport_flag. Every way the window goes (Back, Home, the window destroyed) calls switch_wifitransport(0), as stock's close handler does;
 * the Now Playing button also stops it (stock leaves it running under the player), and the page starts it again when it is back in front. Nothing is saved.
 *
 * The Show QR Code pill swaps the hero for the address as a QR code (patch/qr.c) of the same height, so nothing else moves; every open starts with the hero. */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "entries.h"

#define airplay_flag (*(volatile unsigned char *)AIRPLAY_FLAG)
#define dlna_flag (*(volatile unsigned char *)DLNA_FLAG)

int ns_airplay(void) { return airplay_flag != 0; }

int ns_dlna(void) { return dlna_flag != 0; }

static int ns_after(int on) {
    if (on && networkGetConnectStatus() <= 0) pod_toast(TR("Connect to Wi-Fi first"));
    return on;
}

int ns_airplay_toggle(void) {
    airplay_switch();
    return ns_after(ns_airplay());
}

int ns_dlna_toggle(void) {
    dlna_switch();
    return ns_after(ns_dlna());
}

/* The Wi-Fi Transfer row: stock asks networkGetConnectStatus (0x4a8c48) and opens its page on a nonzero answer, a dialog otherwise (0x4a8ba4). Ours opens the page when the status is above 0 and else toasts. 1: open it. */
int ns_transfer_ok(void) {
    if (networkGetConnectStatus() > 0) return 1;
    pod_toast(TR("Connect to Wi-Fi first"));
    return 0;
}

/* The address the page shows: "<ip>:8888" (stock's init, 0x4b1794, prints "http://%s:8888"; the page's big card leaves the scheme out), or "-" with no address (Wi-Fi gone while the page is open). */
void wt_url_text(char *buf, unsigned n) {
    char ip[32];
    memset(ip, 0, sizeof ip);
    if (networkGetConnectStatus() > 0) networkGetIPAddr(0, ip);
    if (ip[0])
        snprintf(buf, n, "%s:8888", ip);
    else
        snprintf(buf, n, "-");
}

static struct {
    void *win;
    int up; /* switch_wifitransport(1) is in force for this window */
    int qr_can; /* the code's paint and the pill's click are bound */
    int qr_ok; /* qr holds the code of the address shown */
    int qr_on; /* the code is shown in the hero's place */
    unsigned char qr[QR_BYTES]; /* patch/qr.c's symbol of "HTTP://<ip>:8888" */
    unsigned char corner[WT_QR_R * WT_QR_R]; /* the paper's corner coverage (m1_corner_fill) */
    char url[64]; /* the address the code was made for */
} wt __attribute__((section(".scratch")));

/* The pill sized to its label and centred (x WT_PILL_MID of its item), the glyph and the label centred as a pair. */
static void wt_pill_fit(void *btn) {
    const unsigned *t = widget_get_text(btn);
    int tw = t && *t ? m1_text_w(btn, t) : 0, w = 2 * WT_PILL_PAD + WT_PILL_GLYPH + WT_PILL_GAP + (tw > 0 ? tw : 0);
    if (w > 2 * (WT_PILL_MID - 10)) w = 2 * (WT_PILL_MID - 10);
    widget_resize(btn, w, WT_PILL_H);
    widget_move(btn, WT_PILL_MID - w / 2, WT_PILL_Y);
    m1_pill_styles(btn, w, WT_PILL_H, WT_PILL_GLYPH, WT_PILL_GAP, tw > 0 ? tw : 0);
}

/* The code in the hero's place (on) or the hero (off), and the pill's label to match. Without a code (no address) the hero stays and the pill is gone. */
static void wt_qr_set(void *win, int on) {
    void *btn = widget_lookup(win, "pod_qrbtn", 1);
    wt.qr_on = on && wt.qr_ok;
    m1_show(widget_lookup(win, "pod_qr", 1), wt.qr_on);
    m1_show(widget_lookup(win, "pod_hero", 1), !wt.qr_on);
    m1_show(widget_lookup(win, "pod_qrpill", 1), wt.qr_ok);
    if (!btn) return;
    widget_set_text_utf8(btn, wt.qr_on ? TR("Hide QR Code") : TR("Show QR Code"));
    wt_pill_fit(btn);
}

static int wt_qr_click(void *ctx, void *e) {
    (void)e;
    if (ctx == wt.win) wt_qr_set(ctx, !wt.qr_on);
    return RET_OK;
}

/* pod_qr_code's EVT_AFTER_PAINT, in its own coordinates: the paper, the dark modules a run at a time, then the corners in the page's colour. The paper and the modules are raw colours
 * (not ui_ink): a code reads dark on light whatever the background, so Light Mode keeps them. */
static int wt_qr_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    const int side = (QR_SIZE + 2 * WT_QR_QUIET) * WT_QR_MOD;
    int x, y;
    (void)ctx;
    if (!canvas || !wt.qr_ok) return RET_OK;
    canvas_set_fill_color(canvas, WT_QR_PAPER);
    canvas_fill_rect(canvas, 0, 0, side, side);
    canvas_set_fill_color(canvas, WT_QR_DARK);
    for (y = 0; y < QR_SIZE; ++y)
        for (x = 0; x < QR_SIZE;) {
            int i = y * QR_SIZE + x, n = 0;
            while (x + n < QR_SIZE && (wt.qr[(i + n) >> 3] >> (7 - ((i + n) & 7)) & 1)) ++n;
            if (n)
                canvas_fill_rect(canvas, (WT_QR_QUIET + x) * WT_QR_MOD, (WT_QR_QUIET + y) * WT_QR_MOD, n * WT_QR_MOD,
                                 WT_QR_MOD);
            x += n ? n : 1;
        }
    m1_corners(canvas, wt.corner, WT_QR_R, (unsigned)side, 0, 0, 0, 0, 1);
    return RET_OK;
}

/* The address into the page's big card (tools/pod_pages.py BigCard: the label pod_big0_t), and its code made again when it changed. */
static void wt_show(void *win) {
    void *lab = widget_lookup(win, "pod_big0_t", 1);
    char url[64], text[80];
    wt_url_text(url, sizeof url);
    if (lab) widget_set_text_utf8(lab, url);
    if (wt.qr_can && (!wt.qr_ok || strcmp(url, wt.url))) {
        void *code = widget_lookup(win, "pod_qr_code", 1);
        snprintf(wt.url, sizeof wt.url, "%s", url);
        snprintf(text, sizeof text, "HTTP://%s", url);
        wt.qr_ok = url[0] != '-' && qr_make(text, -1, wt.qr) == QR_SIZE;
        if (code) widget_invalidate_force(code, (void *)0);
    }
    wt_qr_set(win, wt.qr_on);
}

/* Stock's key filter (0x4b14d0, bound to the window's EVT_KEY_UP): the key codes 0xd5 .. 0xd7 are stopped before the window manager's key handler, every other key passes. */
static int wt_key(void *ctx, void *e) {
    (void)ctx;
    return (unsigned)(*(int *)((char *)e + EV_KEY) - 0xd5) < 3 ? RET_STOP : RET_OK;
}

/* Stock's close handler (0x4b14ec) stops the server whatever the byte says. The destroy event is the same exit seen later (a window that never saw the close event); the server is stopped once per window. */
static int wt_on_gone(void *ctx, void *e) {
    (void)e;
    if (ctx != wt.win) return RET_OK;
    switch_wifitransport(0);
    wt.win = (void *)0;
    wt.up = 0;
    return RET_OK;
}

/* Now Playing restacks the player over this window, which stays in the stack: stop the server now (the byte also blocks the pull-down and the standby countdown). */
static int wt_on_player(void *ctx, void *e) {
    (void)e;
    if (ctx == wt.win && wt.up) {
        switch_wifitransport(0);
        wt.up = 0;
    }
    return RET_OK;
}

/* Back in front (the player's Back, a window above gone): the server again, without stopping the player a second time. */
void wt_front(void) {
    if (wt.win) wt_show(wt.win); /* the address as it is now */
    if (wt.win && !wt.up) {
        switch_wifitransport(1);
        wt.up = 1;
    }
}

/* The window is up: stock's init, in its order (the two binds first, then stop_player and switch_wifitransport(1)). A bind that fails starts nothing: no way to stop it later. */
void wt_opened(void *win) {
    void *code = widget_lookup(win, "pod_qr_code", 1);
    memset(&wt, 0, sizeof wt); /* the code starts hidden on every open */
    m1_corner_fill(wt.corner, WT_QR_R);
    wt.qr_can =
        code && widget_on(code, EVT_AFTER_PAINT, wt_qr_paint, win) && m1_bind(win, "pod_qrbtn", wt_qr_click, win);
    wt_show(win);
    if (!widget_on(win, EVT_KEY_UP, wt_key, win)) return;
    if (!widget_on(win, EVT_WINDOW_CLOSE, wt_on_gone, win)) return;
    if (!widget_on(win, EVT_DESTROY, wt_on_gone, win)) return;
    m1_bind(win, "btn_backtoplayer", wt_on_player, win);
    wt.win = win;
    stop_player();
    switch_wifitransport(1);
    wt.up = 1;
}
