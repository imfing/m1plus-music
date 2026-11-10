/* The own Wi-Fi page: Settings > Wi-Fi (docs/modules/wifi.md "The Wi-Fi page").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * ui/m1plus_wifi.bin (tools/pod_ui.py build_wifi_page) has the Settings pages' grouped cards under our navbar: the Wi-Fi switch row (with the connected network's row under it in the same card), the My Networks
 * header and card (saved networks), the Networks header (a small spinner after its text while a scan runs) and card (the other networks, then Other...). A network row holds the name, a lock (secured networks), a
 * Wi-Fi fan signal and an info glyph; the connected network has a check at the left, a spinner in its place while it joins. Every row is a pooled widget (WP_CUR / WP_MY / WP_OTH of them) in display order; the
 * payload shows the ones it needs, moves them (widget_move; virtual_h) and gives each its picture piece (single, top, mid, bottom of its card), so no widget is made at run time.
 *
 * What it says to the supplicant it says over the control socket (patch/wifictl.c), never by editing a file: PING / STATUS / LIST_NETWORKS / SCAN / SCAN_RESULTS to look,
 * ADD_NETWORK / SET_NETWORK / ENABLE_NETWORK / SELECT_NETWORK / REMOVE_NETWORK / DISCONNECT / SAVE_CONFIG to act. An SSID is the bytes the supplicant printed (escapes decoded) and goes
 * back as hex. After SAVE_CONFIG the saved configuration is split (wf_split): the networks a stock 2.9 supplicant reads stay in /mnt/data/wpa_supplicant.conf, the others (WPA3,
 * Enhanced Open, Enterprise) go to /mnt/data/m1plus/wifi-networks, which /usr/bin/wifi_connect.sh adds to a copy only the newer supplicant reads. The stock supplicant never sees them.
 * The Wi-Fi switch, the Bluetooth question, and the confirmations are the stock ones (a secured network's password is typed on our own page, wk_open, below; Other... is our own flow of three pages, wo_open, ws_open, wk_open); the stock player's own monitor
 * (network_checkstatus) still finds a connection by the supplicant's state and starts DHCP, so nothing of its state is written here.
 *
 * The info glyph of a row opens the network's info page (window m1plus_wifiinfo, wi_open): the name as the navbar's title, Forget This Network (a saved network), a card with the security, the address
 * and the router (the last two while it is the connected network), the Auto-Join switch (a saved network) or Join (any other). It has no timer of its own: the list's timer refreshes it (wi_refresh) from the
 * state it already reads, so a network that leaves the scan stays on the page and Forget still works.
 *
 * One 250 ms timer owned by the page (spinner, status every second, a scan every 12 s while idle and in front). Taps run on the UI thread; every control call answers at once
 * (a missing supplicant at most 1.5 s).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "wifictl.h"
#include "keyboard.h"

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define WP_CUR \
    1 /* the asset's row pools (tools/pod_ui.py WF_CUR, WF_MY, WF_OTH): the connected network, My Networks, Networks */
#define WP_MY 16
#define WP_OTH WF_MAX
#define WP_ROWS (WP_CUR + WP_MY + WP_OTH)
#define WP_ROW_H 52 /* the Settings pages' numbers (tools/pod_settings.py) */
#define WP_HDR_H 40
#define WP_TOP 10
#define WP_END 10
#define WP_HDR_X 24 /* the header's label; its text starts 2 px in */
#define WP_HDR_TW 76 /* the width of the Networks header's text when it cannot be measured */
#define WP_INFO_X 264 /* a tap right of this on a network row is its info glyph's (the signal ends at 262) */
#define WP_TICK_MS 250
#define WP_POLL 4 /* ticks between two STATUS / LIST_NETWORKS */
#define WP_SCAN_IDLE 48 /* ticks between two scans while idle */
#define WP_SCAN_LEN 16 /* ticks a scan's spinner runs; the results are read at the half and at the end */
#define WP_WANT 80 /* ticks a connect may take before the page stops showing it as asked for */
#define WP_KNOWN 16
#define WP_NETS \
    (WF_MAX + \
     WP_KNOWN) /* scanned networks kept before the merge cuts the list to WF_MAX (saved ones weaker than the 32nd stay in range) */
#define WP_CONF_MAX 12288

static struct {
    void *win, *sv, *fade;
    void *sw_row, *sw_img, *sw_hair, *hdr_my, *hdr_net, *spin_img, *other_row;
    struct {
        void *row, *chk, *name, *lock, *sig, *hair;
    } r[WP_ROWS];
    int map[WP_ROWS]; /* the net (index in nets) each shown row slot holds, -1 unused */
    unsigned char
        piece[WP_ROWS + 2]; /* the picture piece each row has now (WP_P_*), the switch row and Other... last */
    int crow; /* the slot whose check place shows the spinner (the network is joining), -1 none */
    wf_net scan[WP_NETS], known[WP_KNOWN], nets[WP_NETS + WP_KNOWN];
    struct {
        int id;
        unsigned char sec;
    } ksec[WP_KNOWN]; /* the saved networks' security as GET_NETWORK key_mgmt said (by id) */
    unsigned char offmap[WF_OFF_IDS / 8]; /* the saved networks whose Auto-Join is off, by id (wp_snap_off) */
    int snapped; /* offmap is current */
    int nscan, nknown, n, nsec;
    wf_status st;
    unsigned timer, tick, sig;
    int on; /* Wi-Fi as the page shows it */
    int alive; /* the supplicant answered the last command */
    int caps; /* GET_CAPABILITY key_mgmt was read since the supplicant answered */
    int cap_sae, cap_owe;
    int scan_t, idle_t, spin; /* the scan under way (ticks since SCAN, -1 none), ticks idle, the spinner's frame */
    int want_id, want_t; /* the network just chosen, and the tick it was chosen at */
    int modal, fg;
    int cur; /* the id the rows show as the current network */
    int want_pw; /* the network just chosen was joined from the password page: a failure removes it and asks again */
    int pop_info; /* the password page was opened from the info page and joined: the info page goes back when the password page is gone */
    int pop_other; /* Wi-Fi went off with the Security picker up: the Join Wi-Fi Network page under it goes when the picker is gone */
    int want_hid; /* the network just chosen is an open hidden one from the Join Wi-Fi Network page: a failure removes it */
    int pwhid; /* the network just joined with a password came from the Join Wi-Fi Network page (hidden, scan_ssid): it is asked again there, not on the password page */
    wf_net pwnet; /* that network, for asking again */
} wp __attribute__((section(".scratch")));

/* The password page (window m1plus_wifipass, wk_open): the network it asks for, the eye, the error line. */
#define WK_TW 118 /* the field's room for the text and the caret's y (tools/pod_ui.py WK_FIELD_W, WK_CARET_Y) */
#define WK_CY 15
static struct {
    void *win, *eye, *err, *line;
    wf_net net;
    int shown; /* the text is shown (the eye is open) */
    int bad; /* the "Incorrect password" line is up */
    int ok; /* the Join key is enabled */
} wk __attribute__((section(".scratch")));
static int wk_open(const wf_net *w, int bad);

/* The Join Wi-Fi Network page (window m1plus_wifiother, wo_open) and the Security picker it opens (m1plus_wifisec, ws_open). The keyboard has one field: kb_field moves to the row being typed in, the other
 * row shows its value in a static label. Geometry: tools/pod_ui.py WO_*. */
#define WO_NAME_Y 56
#define WO_PASS_Y 164
#define WO_NAME_X 100
#define WO_PASS_X 144
#define WO_NAME_TW 156 /* the text room of each field (the Name field's less its clear button) */
#define WO_PASS_TW 118
#define WO_CY 13 /* the caret's y in the field (a 48 px row) */
static struct {
    void *win, *field, *card_a, *card_b, *hair, *secv, *namev, *nameh, *passv, *passl, *eye, *err, *hit_pass;
    unsigned char ssid[KB_MAX + 1]; /* the name typed (bytes; 1..WF_SSID_MAX is a name, the keyboard holds KB_MAX) */
    unsigned len;
    char pass
        [KB_PASS_MAX +
         1]; /* the password typed (up to KB_PASS_MAX bytes: a WPA3 password, a 64 digit PSK): wiped when the page ends and when it joins (the supplicant's configuration is the only place it stays) */
    int sec; /* WF_OPEN, WF_TRANS (WPA2/WPA3, the default) or WF_SAE (WPA3) */
    int focus; /* 0 the keyboard types the name, 1 the password */
    int shown; /* the password is shown (the eye is open) */
    int bad; /* the "Incorrect password" line is up */
    int ok; /* the action key is enabled */
    int kb; /* the keyboard is attached */
} wo __attribute__((section(".scratch")));
static struct {
    void *win, *sv, *fade;
} ws __attribute__((section(".scratch")));
static void wo_open(const wf_net *again);
static int wp_save(void);

static void wp_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int wp_wifi_on(void) { return *(volatile unsigned char *)WIFI_FLAG != 0; }

/* A shown row or header at *y (headers stay insensitive: never a touch target). */
static void wp_put(void *row, int *y, int h, int touch) {
    widget_move(row, 0, *y);
    if (touch)
        wp_show(row, 1);
    else
        widget_set_visible(row, 1, 0);
    *y += h;
}

/* A child of a row: its visibility alone (it is insensitive in the asset: the row takes the tap). */
static void wp_vis(void *w, int on) {
    if (w) widget_set_visible(w, on, 0);
}

/* The picture piece of a card row (pod_cd_<piece>, the pressed twin _down); the style is set only when it changed. */
enum { WP_P_NONE, WP_P_SINGLE, WP_P_TOP, WP_P_MID, WP_P_BOT };
static void wp_piece(void *row, unsigned char *have, int p) {
    static const char *const up[] = {"", "pod_cd_single", "pod_cd_top", "pod_cd_mid", "pod_cd_bot"};
    static const char *const dn[] = {"", "pod_cd_single_down", "pod_cd_top_down", "pod_cd_mid_down", "pod_cd_bot_down"};
    static const char *const st[] = {"style:normal:bg_image", "style:over:bg_image", "style:focused:bg_image",
                                     "style:disable:bg_image"};
    int i;
    if (*have == p) return;
    *have = (unsigned char)p;
    for (i = 0; i < 4; i++) widget_set_prop_str(row, st[i], up[p]);
    widget_set_prop_str(row, "style:pressed:bg_image", dn[p]);
}

/* The piece of the i-th of n rows of a card. */
static int wp_pos(int i, int n) { return n == 1 ? WP_P_SINGLE : i == 0 ? WP_P_TOP : i == n - 1 ? WP_P_BOT : WP_P_MID; }

/* A reply that is a number (ADD_NETWORK), -1 when it is not. */
static int wp_num(const char *cmd) {
    char r[32];
    int n, v = 0, i;
    n = wf_cmd(cmd, r, sizeof r);
    if (n < 1 || r[0] < '0' || r[0] > '9') return -1;
    for (i = 0; i < n && r[i] >= '0' && r[i] <= '9'; i++) v = v * 10 + (r[i] - '0');
    return v;
}

/* The saved network id's security: the cache, else GET_NETWORK id key_mgmt. */
static int wp_ksec(int id) {
    char c[32], r[96];
    int i;
    for (i = 0; i < wp.nsec; i++)
        if (wp.ksec[i].id == id) return wp.ksec[i].sec;
    snprintf(c, sizeof c, "GET_NETWORK %d key_mgmt", id);
    if (wf_cmd(c, r, sizeof r) < 0) return WF_PSK;
    if (wp.nsec < WP_KNOWN)
        wp.ksec[wp.nsec].id = id, wp.ksec[wp.nsec].sec = (unsigned char)wf_security_keymgmt(r), wp.nsec++;
    return wf_security_keymgmt(r);
}

/* The page's signature: what a row shows, so the rows are laid out again only when it changed. */
static unsigned wp_sig(void) {
    unsigned h = 2166136261u, i, k;
    h = (h ^ (unsigned)wp.on) * 16777619u;
    h = (h ^ (unsigned)wp.st.state ^ (unsigned)wp.st.ip << 4) * 16777619u;
    for (i = 0; wp.on && i < (unsigned)wp.n; i++) {
        const wf_net *w = &wp.nets[i];
        h = (h ^ w->len ^ (unsigned)w->sec << 8 ^ (unsigned)w->level << 12 ^ (unsigned)w->known << 16 ^
             (unsigned)w->current << 17) *
            16777619u;
        for (k = 0; k < w->len; k++) h = (h ^ w->ssid[k]) * 16777619u;
    }
    return h;
}

/* The scroll_view's offset moves back into [0, content - the view's height] after the content shrank. */
static void wp_clamp(void *sv, int content) {
    int h = widget_get_prop_int(sv, "h", 400), off = I(sv, SC_YOFF), max = content - h, at;
    if (max < 0) max = 0;
    at = off < 0 ? 0 : off > max ? max : off;
    if (at != off) widget_set_prop_int(sv, "yoffset", at);
}

static void wp_spinner(void);
static void wi_refresh(void);

/* The wf_sig N of a level 0..4 (0: not in range): N = 3 wifi, 2 wifi-high, 1 wifi-low (levels 1 and 2), 0 all dim. */
static int wp_bars(int level) { return level >= 4 ? 3 : level == 3 ? 2 : level > 0 ? 1 : 0; }

/* A network row's content: name, lock (a network that needs a key), the signal, the check or the spinner (the connected one). */
static void wp_fill(int s, const wf_net *w, int joining) {
    char u[WF_SSID_MAX * 4 + 1], sig[12];
    wf_utf8(w->ssid, w->len, u, sizeof u);
    widget_set_text_utf8(wp.r[s].name, u);
    snprintf(sig, sizeof sig, "wf_sig%d", wp_bars(w->level));
    image_base_set_image(wp.r[s].sig, sig);
    wp_vis(wp.r[s].lock, w->sec != WF_OPEN && w->sec != WF_OWE);
    wp_vis(wp.r[s].chk, s < WP_CUR);
    if (s < WP_CUR) {
        image_base_set_image(wp.r[s].chk, joining ? "wf_spin0" : "wf_check");
        wp.crow = joining ? s : -1;
    }
}

/* A card's rows from slot `first`: the n nets in map get their piece and place; `extra` rows (Other...) follow in the same card. */
static void wp_card(int first, int n, int extra, int *y) {
    int i, total = n + extra;
    for (i = 0; i < n; i++) {
        int s = first + i;
        wp_piece(wp.r[s].row, &wp.piece[s], wp_pos(i, total));
        wp_vis(wp.r[s].hair, i < total - 1);
        wp_put(wp.r[s].row, y, WP_ROW_H, 1);
    }
}

/* The rows as the state says, moved into place; unused ones hidden. */
static void wp_layout(void) {
    int y = WP_TOP, i, on = wp.on, ncur = 0, nm = 0, no = 0;
    wp.sig = wp_sig();
    for (i = 0; i < WP_ROWS; i++) wp.map[i] = -1;
    wp.crow = -1;
    for (i = 0; on && i < wp.n; i++) {
        const wf_net *w = &wp.nets[i];
        if (w->current && ncur < WP_CUR)
            wp.map[ncur++] = i;
        else if (w->known && nm < WP_MY)
            wp.map[WP_CUR + nm++] = i;
        else if (no < WP_OTH)
            wp.map[WP_CUR + WP_MY + no++] = i;
    }
    image_base_set_image(wp.sw_img, on ? "sset_on" : "sset_off");
    wp_piece(wp.sw_row, &wp.piece[WP_ROWS], ncur ? WP_P_TOP : WP_P_SINGLE);
    wp_vis(wp.sw_hair, ncur);
    wp_put(wp.sw_row, &y, WP_ROW_H, 1);
    for (i = 0; i < WP_ROWS; i++) {
        int j = wp.map[i], joining;
        if (j < 0) {
            wp_show(wp.r[i].row, 0);
            continue;
        }
        joining = i < WP_CUR && wp.nets[j].current && !(wp.st.state == WF_ST_CONNECTED && wp.st.ip);
        wp_fill(i, &wp.nets[j], joining);
    }
    if (ncur) { /* the switch row is the card's top, the connected row its bottom */
        wp_piece(wp.r[0].row, &wp.piece[0], WP_P_BOT);
        wp_vis(wp.r[0].hair, 0);
        wp_put(wp.r[0].row, &y, WP_ROW_H, 1);
    }
    if (nm)
        wp_put(wp.hdr_my, &y, WP_HDR_H, 0);
    else
        wp_vis(wp.hdr_my, 0);
    wp_card(WP_CUR, nm, 0, &y);
    if (on) {
        wp_put(wp.hdr_net, &y, WP_HDR_H, 0);
        wp_card(WP_CUR + WP_MY, no, 1, &y);
        wp_piece(wp.other_row, &wp.piece[WP_ROWS + 1], wp_pos(no, no + 1));
        wp_put(wp.other_row, &y, WP_ROW_H, 1);
    } else {
        wp_vis(wp.hdr_net, 0);
        wp_show(wp.other_row, 0);
    }
    y += WP_END;
    widget_set_prop_int(wp.sv, "virtual_h", y);
    wp_clamp(wp.sv, y);
    wp_spinner();
    widget_invalidate_force(wp.sv, (void *)0);
}

/* The header's spinner while a scan runs, and the connecting network's spinner in its check's place: one frame of eight per tick. */
static void wp_spinner(void) {
    char n[12];
    int busy = wp.on && wp.scan_t >= 0;
    if (!busy && wp.crow < 0) {
        wp_vis(wp.spin_img, 0);
        return;
    }
    snprintf(n, sizeof n, "wf_spin%d", wp.spin++ & 7);
    if (wp.spin_img) {
        wp_vis(wp.spin_img, busy);
        if (busy) image_base_set_image(wp.spin_img, n);
    }
    if (wp.crow >= 0) image_base_set_image(wp.r[wp.crow].chk, n);
}

/* The page's list: the scan's networks with the saved ones merged in. */
static void wp_merge(void) {
    int i;
    for (i = 0; i < wp.nscan; i++) memcpy(&wp.nets[i], &wp.scan[i], sizeof wp.nets[i]);
    wp.n = wp.nscan;
    wf_merge(wp.nets, &wp.n, WF_MAX, wp.known, wp.nknown,
             wp.cur); /* (nets has room for the WP_NETS scanned and the WP_KNOWN saved) */
    wi_refresh();
}

static void wp_caps(void) {
    char r[256];
    if (wf_cmd("GET_CAPABILITY key_mgmt", r, sizeof r) < 0) return;
    wp.cap_sae = 0, wp.cap_owe = 0;
    {
        int i;
        for (i = 0; r[i]; i++) {
            if (r[i] == 'S' && r[i + 1] == 'A' && r[i + 2] == 'E') wp.cap_sae = 1;
            if (r[i] == 'O' && r[i + 1] == 'W' && r[i + 2] == 'E') wp.cap_owe = 1;
        }
    }
    wp.caps = 1;
}

/* STATUS and LIST_NETWORKS, then the rows (laid out again only when they changed). */
static void wp_poll(void) {
    char r[WF_REPLY];
    int i, cur;
    if (!wp.on) return;
    if (wf_cmd("STATUS", r, sizeof r) < 0) {
        wp.alive = 0, wp.caps = 0;
        memset(&wp.st, 0, sizeof wp.st);
        wp.st.id = -1;
        wp.nknown = 0;
    } else {
        wp.alive = 1;
        wf_parse_status(r, &wp.st);
        if (!wp.caps) wp_caps();
        if (wf_cmd("LIST_NETWORKS", r, sizeof r) >= 0) {
            wp.nknown = wf_parse_list(r, wp.known, WP_KNOWN);
            for (i = 0; i < wp.nknown; i++) wp.known[i].sec = (unsigned char)wp_ksec(wp.known[i].id);
        }
    }
    cur = wp.st.state >= WF_ST_CONNECTING ? wp.st.id : -1;
    if (wp.want_id >=
        0) { /* a network was just chosen: shown as connecting until the supplicant says otherwise, and a failure told */
        int bad = 0;
        for (i = 0; i < wp.nknown; i++)
            if (wp.known[i].id == wp.want_id && wp.known[i].bad) bad = 1;
        if (wp.st.state == WF_ST_CONNECTED && wp.st.id == wp.want_id) {
            wp.want_id = -1;
            wp.want_pw = 0;
        } else if (bad || wp.tick - (unsigned)wp.want_t > WP_WANT) {
            int id = wp.want_id, pw = wp.want_pw, hid = wp.want_hid;
            wp.want_id = -1;
            wp.want_pw = 0;
            wp.want_hid = 0;
            if (pw ||
                hid) { /* a password typed on the page was wrong, or the network never answered: nothing wrong stays saved, and the password page asks again (an open hidden network only gets the word) */
                char c[40];
                snprintf(c, sizeof c, "REMOVE_NETWORK %d", id);
                wf_ok(c);
                wp_save();
                wp.nsec = 0;
            }
            if (pw && wp.fg && !wp.modal && !wk.win && !wo.win) {
                if (wp.pwhid)
                    wo_open(&wp.pwnet);
                else
                    wk_open(&wp.pwnet, 1);
            } else
                pod_toast(TR("Couldn't connect"));
        } else if (cur < 0)
            cur = wp.want_id;
    }
    wp.cur = cur;
    wp_merge();
    if (wp_sig() != wp.sig) wp_layout();
}

static void wp_fetch(void) {
    char r[WF_REPLY];
    if (wf_cmd("SCAN_RESULTS", r, sizeof r) < 0) return;
    wp.nscan = wf_parse_scan(r, wp.scan, WP_NETS);
    wp_merge();
    if (wp_sig() != wp.sig) wp_layout();
}

static void wp_scan(void) {
    char r[32];
    wp.idle_t = 0;
    if (wf_cmd("SCAN", r, sizeof r) < 0) {
        wp.scan_t = -1;
        wp.idle_t = WP_SCAN_IDLE - 4; /* the supplicant is not there yet: ask again in a second */
        return;
    }
    wp.scan_t = 0;
    wp_spinner();
}

static void wp_confirm_begin(void) { wp.modal = 1; }
static void wp_confirm_end(void) { wp.modal = 0; }

static int wp_yes(const char *text) {
    int yes;
    wp_confirm_begin();
    yes = pod_confirm(text);
    wp_confirm_end();
    return yes;
}

/* The saved configuration (SAVE_CONFIG wrote it, to the copy ours runs on or to the stock file) split in two files. 0 when both are written. */
static int wp_files(void) {
    int copy = access(WF_COPY, F_OK) == 0, fd, n, m = 0, r = -1;
    unsigned ns = 0, no = 0, k;
    char *in = calloc(WP_CONF_MAX, 4), *stock, *ours, *old;
    if (!in) return -1;
    stock = in + WP_CONF_MAX, ours = stock + WP_CONF_MAX, old = ours + WP_CONF_MAX;
    fd = open(copy ? WF_COPY : WF_CONF, O_RDONLY, 0);
    n = fd >= 0 ? read(fd, in, WP_CONF_MAX - 1) : -1;
    if (fd >= 0) close(fd);
    if (n > 0 && n < WP_CONF_MAX - 1 && wf_split(in, (unsigned)n, stock, &ns, ours, &no, WP_CONF_MAX) == 0 && ns) {
        if (!copy) { /* the supplicant ran on the stock file: what it kept there is new, the ours-only networks saved earlier stay */
            fd = open(WIFINET_FILE, O_RDONLY, 0);
            m = fd >= 0 ? read(fd, old, WP_CONF_MAX - 1) : 0;
            if (fd >= 0) close(fd);
            if (m < 0 || (unsigned)m + no >= WP_CONF_MAX) goto out;
            for (k = 0; k < no; k++) old[(unsigned)m + k] = ours[k];
            old[(unsigned)m + no] = 0;
            ours = old, no += (unsigned)m;
        }
        if ((copy || no) && home_write_atomic(WIFINET_FILE, WIFINET_TMP, ours) != 0) goto out;
        if (home_write_atomic(WF_CONF, WF_CONF_TMP, stock) == 0) r = 0;
    }
out:
    free(in);
    return r;
}

static int wp_save(void) {
    if (!wf_ok("SAVE_CONFIG")) return -1;
    return wp_files();
}

static int wp_prio(void) { return (int)(time((long *)0) / 60); }

/* One SET_NETWORK of id with a value; the value is used as it is (the caller quotes). */
static int wp_set(int id, const char *key, const char *val) {
    char c[256];
    snprintf(c, sizeof c, "SET_NETWORK %d %s %s", id, key, val);
    return wf_ok(c);
}

/* SELECT_NETWORK disables every other network (in memory, and SAVE_CONFIG would write disabled=1 for all of them). The ids the supplicant lists as [DISABLED] (Auto-Join off) are noted before
 * the select, from the whole of LIST_NETWORKS (read page by page, whatever the page lists), and after it every network is enabled and those are disabled again: the saved file keeps only what
 * the user chose and a select that fails leaves the others usable. */
static void wp_snap_off(void) {
    char r[WF_REPLY];
    wp.snapped = wf_list_off(r, sizeof r, wp.offmap) >= 0;
}

static void wp_reenable(int sel) {
    char c[40];
    unsigned i;
    if (!wp.snapped) return;
    wf_ok("ENABLE_NETWORK all");
    for (i = 0; i < WF_OFF_IDS; i++)
        if (wp.offmap[i >> 3] >> (i & 7) & 1 && (int)i != sel) {
            snprintf(c, sizeof c, "DISABLE_NETWORK %u", i);
            wf_ok(c);
        }
}

/* Adds a network and joins it: ssid (bytes), the security, the password (WF_OPEN / WF_OWE: none), hidden (a scan_ssid probe). The network is saved, then selected.
 * 0 when it is joined, -1 when the supplicant refused a step (the network is removed again). */
static int wp_join(const unsigned char *ssid, unsigned len, int sec, const char *pass, int hidden) {
    char c[300], hex[WF_SSID_MAX * 2 + 1], q[WF_SAE_MAX + 4];
    int id, ok;
    if ((sec == WF_PSK || sec == WF_TRANS || sec == WF_SAE) && !wf_pass_ok(pass, sec))
        return -1; /* (never a password the supplicant would refuse, nor one that does not fit q and c) */
    id = wp_num("ADD_NETWORK");
    if (id < 0) return -1;
    wf_hex(ssid, len, hex);
    ok = wp_set(id, "ssid", hex);
    if (hidden && ok) ok = wp_set(id, "scan_ssid", "1");
    if (sec == WF_OPEN && ok) ok = wp_set(id, "key_mgmt", "NONE");
    if (sec == WF_OWE && ok) ok = wp_set(id, "key_mgmt", "OWE") && wp_set(id, "ieee80211w", "2");
    if ((sec == WF_PSK || sec == WF_TRANS) && ok) {
        snprintf(q, sizeof q, wf_pass_hex(pass) ? "%s" : "\"%s\"",
                 pass); /* a 64 digit PSK is sent as it is, a passphrase quoted */
        ok = wp_set(id, "psk", q);
        if (ok && sec == WF_TRANS && wp.cap_sae && !wf_pass_hex(pass)) /* (a raw PSK has no password for SAE) */
            ok = wp_set(id, "key_mgmt", "WPA-PSK SAE") && wp_set(id, "ieee80211w", "1");
        else if (ok)
            ok = wp_set(id, "key_mgmt", "WPA-PSK");
    }
    if (sec == WF_SAE && ok) {
        snprintf(q, sizeof q, "\"%s\"", pass);
        ok = wp_set(id, "sae_password", q) && wp_set(id, "key_mgmt", "SAE") && wp_set(id, "ieee80211w", "2");
    }
    if (ok) {
        snprintf(q, sizeof q, "%d", wp_prio());
        ok = wp_set(id, "priority", q);
    }
    if (ok) {
        snprintf(c, sizeof c, "ENABLE_NETWORK %d", id);
        ok = wf_ok(c);
    }
    if (!ok) {
        snprintf(c, sizeof c, "REMOVE_NETWORK %d", id);
        wf_ok(c);
        return -1;
    }
    wp_save();
    wp_snap_off();
    snprintf(c, sizeof c, "SELECT_NETWORK %d", id);
    if (!wf_ok(c)) { /* nothing stays saved of a join that did not start (a retry would add the name twice) */
        snprintf(c, sizeof c, "REMOVE_NETWORK %d", id);
        wf_ok(c);
        wp_save();
        return -1;
    }
    wp_reenable(id);
    wp.want_id = id, wp.want_t = (int)wp.tick, wp.want_pw = 0, wp.want_hid = 0;
    return 0;
}

/* A saved network is chosen: it is made the preferred one, saved and selected. */
static int wp_join_known(int id) {
    char c[96], q[16];
    snprintf(q, sizeof q, "%d", wp_prio());
    wp_set(id, "priority", q);
    snprintf(c, sizeof c, "ENABLE_NETWORK %d", id);
    wf_ok(c);
    wp_save();
    wp_snap_off();
    snprintf(c, sizeof c, "SELECT_NETWORK %d", id);
    if (!wf_ok(c)) return -1;
    wp_reenable(id);
    wp.want_id = id, wp.want_t = (int)wp.tick, wp.want_pw = 0, wp.want_hid = 0;
    return 0;
}

static void wp_after(void) {
    wp.scan_t = -1;
    wp.idle_t = 0;
    wp_spinner();
    wp_poll();
}

/* Whether a network that is not saved can be joined with the supplicant that runs; else the toast says why. */
static int wp_can(const wf_net *w) {
    if (w->sec == WF_EAP) {
        pod_toast(TR("Enterprise isn't supported yet"));
        return 0;
    }
    if (w->sec == WF_WEP) {
        pod_toast(TR("WEP isn't supported"));
        return 0;
    }
    if ((w->sec == WF_SAE && !wp.cap_sae) || (w->sec == WF_OWE && !wp.cap_owe)) {
        pod_toast(TR("This network isn't supported"));
        return 0;
    }
    return 1;
}

/* Delete Record?, then the saved network id is removed and the file saved. 1 when it was forgotten. */
static int wp_forget(int id) {
    char c[40];
    if (!wp_yes(TR("msg_wificancelsave"))) return 0;
    snprintf(c, sizeof c, "REMOVE_NETWORK %d", id);
    wf_ok(c);
    wp_save();
    if (wp.want_id == id) wp.want_id = -1;
    wp.nsec = 0;
    return 1;
}

/* The network is chosen: a saved one joins, an open one too, a secured one that is not saved opens the password page (the join is sent from it). 1 when something was sent to the supplicant (the page
 * reads it again), 0 when nothing was (refused, or the password page is up). */
static int wp_connect(const wf_net *w) {
    if (w->known) {
        if (wp_join_known(w->id) != 0) pod_toast(TR("Couldn't connect"));
        return 1;
    }
    if (!wp_can(w)) return 0;
    if (w->sec != WF_OPEN && w->sec != WF_OWE) {
        wk_open(w, 0);
        return 0;
    }
    if (wp_join(w->ssid, w->len, w->sec, "", 0) != 0) pod_toast(TR("Couldn't connect"));
    return 1;
}

static void wi_open(const wf_net *w);

static int wp_on_net(void *ctx, void *e) {
    int s = (int)(long)ctx - 1, i, pt[2];
    wf_net w;
    if (wp.modal || s < 0 || s >= WP_ROWS || !wp.on) return RET_OK;
    i = wp.map[s];
    if (i < 0 || i >= wp.n) return RET_OK;
    memcpy(&w, &wp.nets[i], sizeof w);
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(wp.r[s].row, pt);
    if (pt[0] >= WP_INFO_X) { /* the info glyph: the network's info page */
        wi_open(&w);
        return RET_OK;
    }
    if (w.current && wp.st.state >= WF_ST_CONNECTING) { /* the connected one: disconnect */
        if (!wp_yes(TR("msg_wifidisconnect"))) return RET_OK;
        wf_ok("DISCONNECT");
        wp.want_id = -1;
    } else if (!wp_connect(&w))
        return RET_OK;
    wp_after();
    return RET_OK;
}

/* Other...: a hidden network, by its name, security and password on the Join Wi-Fi Network page. */
static int wp_on_other(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (wp.modal || !wp.on) return RET_OK;
    wo_open((const wf_net *)0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 * The info page (window m1plus_wifiinfo, tools/pod_ui.py build_wifiinfo_page): one network's Security, address, Forget / Auto-Join / Join
 */
#define WI_FIELDS \
    4 /* the info card's rows: Security, IP Address, Router; one more is room for the enterprise rows (username, password, certificate) of a later stage */
#define WI_GAP_H 20 /* tools/pod_settings.py GAP_H: the space between two cards */
#define WI_ROUTE "/proc/net/route"

static struct {
    void *win, *sv, *fade, *title;
    void *forget, *auto_row, *auto_img, *join, *gap[3];
    struct {
        void *row, *label, *val, *hair;
    } f[WI_FIELDS];
    unsigned char
        piece[WI_FIELDS + 3]; /* the picture piece each row has now: the fields, then Forget, Auto-Join and Join */
    wf_net net; /* the network as the page last saw it (the name never changes; the rest follows the list) */
    int conn; /* it is the connected network and has an address */
    char ip[20], gw[20];
    unsigned sig;
} wi __attribute__((section(".scratch")));

/* wlan0's default gateway as text; empty when there is none. */
static void wi_route(char *out) {
    char *t = calloc(2048, 1);
    int fd, n = -1;
    out[0] = 0;
    if (!t) return;
    fd = open(WI_ROUTE, O_RDONLY, 0);
    if (fd >= 0) n = read(fd, t, 2047), close(fd);
    if (n > 0) wf_parse_route(t, out, 20);
    free(t);
}

static int wi_same(const wf_net *a, const wf_net *b) {
    unsigned i;
    if (a->len != b->len) return 0;
    for (i = 0; i < a->len; i++)
        if (a->ssid[i] != b->ssid[i]) return 0;
    return 1;
}

static void wi_field(int i, const char *label, const char *val) {
    widget_set_text_utf8(wi.f[i].label, label);
    widget_set_text_utf8(wi.f[i].val, val);
}

/* The rows as the network's state says: a saved network has Forget, the info card and Auto-Join; any other the info card and Join. */
static void wi_layout(void) {
    int y = WP_TOP, n = 0, i, saved = wi.net.known;
    if (saved) {
        wp_piece(wi.forget, &wi.piece[WI_FIELDS], WP_P_SINGLE);
        wp_put(wi.forget, &y, WP_ROW_H, 1);
    } else
        wp_show(wi.forget, 0);
    wi_field(n++, TR("Security"), TR(wf_sec_label(wi.net.sec)));
    if (wi.conn) {
        wi_field(n++, TR("IP Address"), wi.ip);
        if (wi.gw[0]) wi_field(n++, TR("Router"), wi.gw);
    }
    if (saved)
        wp_put(wi.gap[0], &y, WI_GAP_H, 0);
    else
        wp_vis(wi.gap[0], 0);
    for (i = 0; i < WI_FIELDS; i++) {
        if (i >= n) {
            wp_show(wi.f[i].row, 0);
            continue;
        }
        wp_piece(wi.f[i].row, &wi.piece[i], wp_pos(i, n));
        wp_vis(wi.f[i].hair, i < n - 1);
        wp_put(wi.f[i].row, &y, WP_ROW_H, 0);
    }
    if (saved) {
        wp_put(wi.gap[1], &y, WI_GAP_H, 0);
        image_base_set_image(wi.auto_img, wi.net.off ? "sset_off" : "sset_on");
        wp_piece(wi.auto_row, &wi.piece[WI_FIELDS + 1], WP_P_SINGLE);
        wp_put(wi.auto_row, &y, WP_ROW_H, 1);
        wp_vis(wi.gap[2], 0), wp_show(wi.join, 0);
    } else {
        wp_vis(wi.gap[1], 0), wp_show(wi.auto_row, 0);
        wp_put(wi.gap[2], &y, WI_GAP_H, 0);
        wp_piece(wi.join, &wi.piece[WI_FIELDS + 2], WP_P_SINGLE);
        wp_put(wi.join, &y, WP_ROW_H, 1);
    }
    y += WP_END;
    widget_set_prop_int(wi.sv, "virtual_h", y);
    wp_clamp(wi.sv, y);
    widget_invalidate_force(wi.sv, (void *)0);
}

/* The network's state from the list's (the name is the key): a saved network, its Auto-Join and whether it is connected. A network that left the scan stays as it was, a forgotten one becomes an unsaved one. */
static void wi_refresh(void) {
    unsigned h = 2166136261u, i;
    int j;
    if (!wi.win || !wp.on || !wp.alive) return;
    for (j = 0; j < wp.n && !wi_same(&wp.nets[j], &wi.net); j++) {
    }
    if (j < wp.n)
        memcpy(&wi.net, &wp.nets[j], sizeof wi.net);
    else
        wi.net.known = 0, wi.net.current = 0, wi.net.off = 0, wi.net.id = -1, wi.net.level = 0;
    wi.conn = wi.net.current && wp.st.state == WF_ST_CONNECTED && wp.st.ipaddr[0];
    memset(wi.ip, 0, sizeof wi.ip);
    if (wi.conn) {
        memcpy(wi.ip, wp.st.ipaddr, sizeof wi.ip - 1);
        wi_route(wi.gw);
    } else
        wi.gw[0] = 0;
    h = (h ^ wi.net.known ^ (unsigned)wi.net.off << 1 ^ (unsigned)wi.net.sec << 2 ^ (unsigned)wi.conn << 6) * 16777619u;
    for (i = 0; wi.conn && wi.ip[i]; i++) h = (h ^ (unsigned char)wi.ip[i]) * 16777619u;
    for (i = 0; wi.conn && wi.gw[i]; i++) h = (h ^ (unsigned char)wi.gw[i] ^ 0x100) * 16777619u;
    if (h != wi.sig) wi.sig = h, wi_layout();
}

static int wi_on_forget(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (wp.modal || !wi.net.known) return RET_OK;
    if (!wp_forget(wi.net.id)) return RET_OK;
    navigator_back();
    wp_after();
    return RET_OK;
}

/* Auto-Join: ENABLE_NETWORK / DISABLE_NETWORK, saved. (The supplicant disconnects when the network it is on is disabled.) */
static int wi_on_auto(void *ctx, void *e) {
    char c[40];
    (void)ctx;
    (void)e;
    if (wp.modal || !wi.net.known) return RET_OK;
    snprintf(c, sizeof c, wi.net.off ? "ENABLE_NETWORK %d" : "DISABLE_NETWORK %d", wi.net.id);
    if (wf_ok(c)) wp_save();
    if (wi.net.off == 0 && wp.want_id == wi.net.id) wp.want_id = -1;
    wp_poll();
    return RET_OK;
}

static int wi_on_join(void *ctx, void *e) {
    wf_net w;
    (void)ctx;
    (void)e;
    if (wp.modal || wi.net.known) return RET_OK;
    memcpy(&w, &wi.net, sizeof w);
    if (!wp_connect(&w)) return RET_OK;
    navigator_back();
    wp_after();
    return RET_OK;
}

static int wi_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!wi.fade) return RET_OK;
    widget_set_visible(wi.fade, I(wi.sv, SC_YOFF) > 0, 0);
    widget_set_sensitive(wi.fade, 0);
    return RET_OK;
}

static int wi_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != wi.win) return RET_OK;
    memset(&wi, 0, sizeof wi);
    return RET_OK;
}

/* A row's info glyph: the network's page. */
static void wi_open(const wf_net *w) {
    char n[24], u[WF_SSID_MAX * 4 + 1];
    int i;
    if (wi.win) return;
    memset(&wi, 0, sizeof wi);
    memcpy(&wi.net, w, sizeof wi.net);
    wi.win = window_open("m1plus_wifiinfo");
    if (!wi.win) {
        memset(&wi, 0, sizeof wi);
        return;
    }
    widget_on(wi.win, EVT_DESTROY, wi_on_destroy, wi.win);
    pod_bind(wi.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(wi.win, "btn_backtoplayer", pod_on_player, (void *)0);
    wi.sv = widget_lookup(wi.win, "wifiinfo_scrollview", 1);
    wi.fade = widget_lookup(wi.win, "img_nb_fade", 1);
    wi.title = widget_lookup(wi.win, "label_title", 1);
    wi.forget = pod_bind(wi.win, "wi_row_forget", wi_on_forget, (void *)0);
    wi.auto_row = pod_bind(wi.win, "wi_row_auto", wi_on_auto, (void *)0);
    wi.auto_img = widget_lookup(wi.win, "wi_auto_img", 1);
    wi.join = pod_bind(wi.win, "wi_row_join", wi_on_join, (void *)0);
    for (i = 0; i < 3; i++) {
        snprintf(n, sizeof n, "wi_gap%d", i);
        wi.gap[i] = widget_lookup(wi.win, n, 1);
    }
    for (i = 0; i < WI_FIELDS; i++) {
        snprintf(n, sizeof n, "wi_f%d", i);
        wi.f[i].row = widget_lookup(wi.win, n, 1);
        snprintf(n, sizeof n, "wi_fl%d", i);
        wi.f[i].label = widget_lookup(wi.win, n, 1);
        snprintf(n, sizeof n, "wi_fv%d", i);
        wi.f[i].val = widget_lookup(wi.win, n, 1);
        snprintf(n, sizeof n, "wi_fh%d", i);
        wi.f[i].hair = widget_lookup(wi.win, n, 1);
        if (!wi.f[i].row || !wi.f[i].label || !wi.f[i].val || !wi.f[i].hair) wi.sv = (void *)0;
    }
    if (!wi.sv || !wi.title || !wi.forget || !wi.auto_row || !wi.auto_img || !wi.join || !wi.gap[0] || !wi.gap[1] ||
        !wi.gap[2]) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return;
    }
    wf_utf8(wi.net.ssid, wi.net.len, u, sizeof u);
    az_fit(wi.title, u);
    widget_on(wi.sv, EVT_SCROLL, wi_on_scroll, (void *)0);
    widget_on(wi.sv, EVT_SCROLL_END, wi_on_scroll, (void *)0);
    wi.sig = 0;
    wi_refresh();
    if (!wi.sig) wi.sig = 1, wi_layout(); /* the list had nothing to say (no supplicant): the page as it was opened */
}

/* ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 * The password page (window m1plus_wifipass, tools/pod_ui.py build_wifipass_page): "Enter Password" for a secured network that is not saved, with our keyboard embedded (KB_PASSWORD)
 */

/* tpl with its %s replaced by name (a template of the translation table, never a printf format). */
static void wk_subst(char *out, unsigned size, const char *tpl, const char *name) {
    unsigned o = 0;
    for (; *tpl && o + 1 < size; tpl++) {
        if (tpl[0] == '%' && tpl[1] == 's') {
            const char *n = name;
            while (*n && o + 1 < size) out[o++] = *n++;
            tpl++;
        } else
            out[o++] = *tpl;
    }
    out[o] = 0;
}

/* The keyboard's text changed: the Join key works while the password can be one (8..63 printable ASCII characters or 64 hex digits; WPA3: 1..127); a line about a wrong password goes at the first key. */
static void wk_change(const char *text) {
    int ok = wf_pass_ok(text, wk.net.sec);
    if (text[0] && wk.bad) wk.bad = 0, wp_vis(wk.err, 0);
    if (ok != wk.ok) {
        wk.ok = ok;
        keyboard_set_go((const char *)0, ok);
    }
}

/* Join: the password goes to the supplicant (wp_join: SET_NETWORK psk / sae_password, saved) and nowhere else; the page goes back and the list shows the network joining. The network is kept for asking
 * again when the password was wrong (wp_poll). */
static void wk_go(void) {
    char pass[KB_PASS_MAX + 1];
    unsigned i;
    int r;
    const char *t = keyboard_text();
    if (!wk.ok || wp.modal) return;
    for (i = 0; t[i] && i < KB_PASS_MAX; i++) pass[i] = t[i];
    pass[i] = 0;
    r = wf_pass_ok(pass, wk.net.sec) ? wp_join(wk.net.ssid, wk.net.len, wk.net.sec, pass, 0) : -1;
    for (i = 0; i <= KB_PASS_MAX; i++) pass[i] = 0;
    if (r != 0) {
        pod_toast(TR("Couldn't connect"));
        return;
    }
    wp.want_pw = 1;
    memcpy(&wp.pwnet, &wk.net, sizeof wp.pwnet);
    wp.pwhid = 0;
    wp.pop_info = wi.win != (void *)0;
    navigator_back();
    wp_after();
}

static int wk_on_eye(void *ctx, void *e) {
    static const char *const st[] = {"style:normal:icon", "style:over:icon", "style:pressed:icon"};
    int i;
    (void)ctx;
    (void)e;
    wk.shown = !wk.shown;
    keyboard_set_mask(!wk.shown);
    for (i = 0; i < 3; i++) widget_set_prop_str(wk.eye, st[i], wk.shown ? "wf_eye" : "wf_eyeoff");
    widget_invalidate_force(wk.eye, (void *)0);
    return RET_OK;
}

static int wk_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != wk.win) return RET_OK;
    keyboard_detach(); /* the typed text goes with the keyboard's state */
    memset(&wk, 0, sizeof wk);
    return RET_OK;
}

/* The page for the secured network w; bad = it was just refused (the field is empty, a grey "Incorrect password" under the card). 0 once it is up. */
static int wk_open(const wf_net *w, int bad) {
    char u[WF_SSID_MAX * 4 + 1], line[WF_SSID_MAX * 4 + 120];
    if (wk.win) return 0;
    memset(&wk, 0, sizeof wk);
    wk.win = window_open("m1plus_wifipass");
    if (!wk.win) {
        memset(&wk, 0, sizeof wk);
        return -1;
    }
    memcpy(&wk.net, w, sizeof wk.net);
    widget_on(wk.win, EVT_DESTROY, wk_on_destroy, wk.win);
    pod_bind(wk.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(wk.win, "btn_backtoplayer", pod_on_player, (void *)0);
    wk.eye = pod_bind(wk.win, "wk_eye", wk_on_eye, (void *)0);
    wk.err = widget_lookup(wk.win, "wk_err", 1);
    wk.line = widget_lookup(wk.win, "wk_line", 1);
    if (!wk.eye || !wk.err || !wk.line ||
        keyboard_attach(wk.win, (const char *)0, 0, WK_TW, WK_CY, KB_PASSWORD, wk_change, wk_go) != 0) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    keyboard_set_go("Join", 0);
    wf_utf8(wk.net.ssid, wk.net.len, u, sizeof u);
    wk_subst(line, sizeof line, TR("Enter the password for “%s”"), u);
    az_fit(wk.line, line);
    wk.bad = bad;
    wp_vis(wk.err, bad);
    return 0;
}

/* ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 * The Join Wi-Fi Network page (tools/pod_ui.py build_wifiother_page, build_wifisec_page): a hidden network's Name, Security (a picker page) and Password on one page, with our keyboard embedded
 */

/* The name can be one: 1..32 bytes (an SSID's limit). */
static int wo_name_ok(void) { return wo.len >= 1 && wo.len <= WF_SSID_MAX; }

/* The action key can work: on the Name field the name is a name, on the Password field the name and the password both are. */
static int wo_can_go(void) { return wo_name_ok() && (!wo.focus || wf_pass_ok(wo.pass, wo.sec)); }

/* The action key reads Next on the Name field of a secured network (it moves to the password) and Join where it joins; dimmed and inert until it can work. */
static void wo_set_go(void) {
    wo.ok = wo_can_go();
    keyboard_set_go(wo.focus || wo.sec == WF_OPEN ? "Join" : "Next", wo.ok);
}

/* The password as the static label shows it while the keyboard types the name: one dot a character, or the text with the eye open (cut with an ellipsis). */
static void wo_pass_label(void) {
    char dots[KB_PASS_MAX * 3 + 1];
    unsigned i, n = 0;
    for (i = 0; wo.pass[i]; i++)
        if (((unsigned char)wo.pass[i] & 0xc0) != 0x80)
            dots[n++] = (char)0xe2, dots[n++] = (char)0x80, dots[n++] = (char)0xa2;
    dots[n] = 0;
    az_fit(wo.passv, wo.shown ? wo.pass : dots);
    memset(dots, 0, sizeof dots);
}

/* Everything the page shows that depends on the security and on the field being typed in: card 2 (one row for None, two otherwise) with the Password row, the Security value, the keyboard's field on its row
 * and the other row's static label (the Name's placeholder while the name is empty), the error line. */
static void wo_layout(void) {
    int sec = wo.sec != WF_OPEN, pass = wo.focus == 1;
    wp_vis(wo.card_a, !sec);
    wp_vis(wo.card_b, sec);
    wp_vis(wo.hair, sec);
    wp_vis(wo.passl, sec);
    wp_show(wo.eye, sec);
    wp_show(wo.hit_pass, sec);
    widget_set_text_utf8(wo.secv, TR(wo.sec == WF_OPEN ? "None" : wo.sec == WF_TRANS ? "WPA2/WPA3" : "WPA3"));
    widget_move(wo.field, pass ? WO_PASS_X : WO_NAME_X, pass ? WO_PASS_Y : WO_NAME_Y);
    wp_vis(wo.namev, pass && wo.len);
    wp_vis(wo.nameh, pass && !wo.len);
    wp_vis(wo.passv, sec && !pass);
    if (pass && wo.len) az_fit(wo.namev, (const char *)wo.ssid);
    if (sec && !pass) wo_pass_label();
    wp_vis(wo.err, sec && wo.bad);
}

/* The keyboard's text changed: it is the active field's value (kept here: the other field and the Security page come and go), the action key works or not, and a line about a wrong password goes at the
 * first character of a new one. */
static void wo_change(const char *text) {
    unsigned i;
    if (wo.focus) {
        for (i = 0; text[i] && i < KB_PASS_MAX; i++) wo.pass[i] = text[i];
        memset(wo.pass + i, 0, sizeof wo.pass - i);
        if (text[0] && wo.bad) wo.bad = 0, wp_vis(wo.err, 0);
    } else {
        for (i = 0; text[i] && i < KB_MAX; i++) wo.ssid[i] = (unsigned char)text[i];
        wo.len = i;
        memset(wo.ssid + i, 0, sizeof wo.ssid - i);
    }
    if (wo_can_go() != wo.ok) wo_set_go();
}

static void wo_go(void);

/* The keyboard types the Name (0) or the Password (1; not with Security None): the same pad and field moved to that row, the mode of the field (plain text with Chinese when it is on, or a masked English
 * password), the other field's value kept by the page. */
static void wo_focus(int f) {
    if (f && wo.sec == WF_OPEN) f = 0;
    wo.focus = f;
    keyboard_refocus(f ? (const char *)0 : TR("Network Name"), f ? WO_PASS_TW : WO_NAME_TW,
                     f ? KB_PASSWORD : KB_LITERAL, f ? wo.pass : (const char *)wo.ssid, wo_change, wo_go);
    if (f) keyboard_set_mask(!wo.shown);
    wo_layout();
    wo_set_go();
}

/* Join (on the Password field, or on the Name field with Security None): the hidden-network join. Next (the Name field of a secured network) moves to the password. */
static void wo_go(void) {
    wf_net w;
    if (!wo.ok || wp.modal) return;
    if (!wo.focus && wo.sec != WF_OPEN) {
        wo_focus(1);
        return;
    }
    memset(&w, 0, sizeof w);
    memcpy(w.ssid, wo.ssid, wo.len);
    w.len = (unsigned char)wo.len;
    w.sec = (unsigned char)wo.sec;
    w.id = -1;
    if (!wp_can(&w)) return;
    if (wp_join(w.ssid, w.len, wo.sec, wo.sec == WF_OPEN ? "" : wo.pass, 1) != 0) {
        pod_toast(TR("Couldn't connect"));
        return;
    }
    memset(wo.pass, 0, sizeof wo.pass);
    if (wo.sec == WF_OPEN)
        wp.want_hid = 1;
    else
        wp.want_pw = 1;
    memcpy(&wp.pwnet, &w, sizeof wp.pwnet);
    wp.pwhid = 1;
    navigator_back();
    wp_after();
}

static void ws_open(void);

static int wo_on_name(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!wp.modal && wo.win && wo.focus != 0) wo_focus(0);
    return RET_OK;
}

static int wo_on_pass(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!wp.modal && wo.win && wo.sec != WF_OPEN && wo.focus != 1) wo_focus(1);
    return RET_OK;
}

static int wo_on_sec(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!wp.modal && wo.win) ws_open();
    return RET_OK;
}

static int wo_on_eye(void *ctx, void *e) {
    static const char *const st[] = {"style:normal:icon", "style:over:icon", "style:pressed:icon"};
    int i;
    (void)ctx;
    (void)e;
    wo.shown = !wo.shown;
    if (wo.focus)
        keyboard_set_mask(!wo.shown);
    else
        wo_pass_label();
    for (i = 0; i < 3; i++) widget_set_prop_str(wo.eye, st[i], wo.shown ? "wf_eye" : "wf_eyeoff");
    widget_invalidate_force(wo.eye, (void *)0);
    return RET_OK;
}

static int wo_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != wo.win) return RET_OK;
    if (wo.kb) keyboard_detach(); /* the typed text goes with the keyboard's state, the page's copy with the page */
    memset(&wo, 0, sizeof wo);
    return RET_OK;
}

/* Security was chosen on the picker: a password cannot be typed with None (the keyboard goes back to the Name). */
static void wo_set_sec(int sec) {
    wo.sec = sec;
    if (sec == WF_OPEN && wo.focus)
        wo_focus(0);
    else {
        wo_layout();
        wo_set_go();
    }
}

/* The page: empty with WPA2/WPA3 and the Name field typed in, or (again, a network that was refused) its name and security with an empty password field and the "Incorrect password" line. */
static void wo_open(const wf_net *again) {
    if (wo.win) return;
    memset(&wo, 0, sizeof wo);
    wo.win = window_open("m1plus_wifiother");
    if (!wo.win) {
        memset(&wo, 0, sizeof wo);
        return;
    }
    wo.sec = WF_TRANS;
    if (again) {
        memcpy(wo.ssid, again->ssid, again->len);
        wo.len = again->len;
        wo.sec = again->sec;
        wo.bad = 1;
    }
    widget_on(wo.win, EVT_DESTROY, wo_on_destroy, wo.win);
    pod_bind(wo.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(wo.win, "btn_backtoplayer", pod_on_player, (void *)0);
    wo.field = widget_lookup(wo.win, "kb_field", 1);
    wo.card_a = widget_lookup(wo.win, "wo_card1a", 1);
    wo.card_b = widget_lookup(wo.win, "wo_card1b", 1);
    wo.hair = widget_lookup(wo.win, "wo_hair", 1);
    wo.secv = widget_lookup(wo.win, "wo_sec_v", 1);
    wo.namev = widget_lookup(wo.win, "wo_name_v", 1);
    wo.nameh = widget_lookup(wo.win, "wo_name_h", 1);
    wo.passv = widget_lookup(wo.win, "wo_pass_v", 1);
    wo.passl = widget_lookup(wo.win, "wo_pass_l", 1);
    wo.err = widget_lookup(wo.win, "wo_err", 1);
    wo.eye = pod_bind(wo.win, "wo_eye", wo_on_eye, (void *)0);
    wo.hit_pass = pod_bind(wo.win, "wo_hit_pass", wo_on_pass, (void *)0);
    if (!wo.field || !wo.card_a || !wo.card_b || !wo.hair || !wo.secv || !wo.namev || !wo.nameh || !wo.passv ||
        !wo.passl || !wo.err || !wo.eye || !wo.hit_pass || !pod_bind(wo.win, "wo_hit_name", wo_on_name, (void *)0) ||
        !pod_bind(wo.win, "wo_hit_sec", wo_on_sec, (void *)0) ||
        keyboard_attach(wo.win, TR("Network Name"), 0, WO_NAME_TW, WO_CY, KB_LITERAL, wo_change, wo_go) != 0) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return;
    }
    wo.kb = 1;
    wo_focus(again ? 1 : 0);
}

/* A security row of the picker: None, WPA2/WPA3 or WPA3 (only with the newer supplicant) becomes the page's choice and the picker goes back. */
static int ws_on_row(void *ctx, void *e) {
    int k = (int)(long)ctx - 1;
    wf_net w;
    (void)e;
    if (wp.modal || !ws.win || !wo.win || k < 0 || k > 2) return RET_OK;
    memset(&w, 0, sizeof w);
    w.sec = k == 0 ? WF_OPEN : k == 1 ? WF_TRANS : WF_SAE;
    w.id = -1;
    if (!wp_can(&w)) return RET_OK;
    wo_set_sec(w.sec);
    navigator_back();
    return RET_OK;
}

static int ws_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!ws.fade) return RET_OK;
    widget_set_visible(ws.fade, I(ws.sv, SC_YOFF) > 0, 0);
    widget_set_sensitive(ws.fade, 0);
    return RET_OK;
}

static int ws_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != ws.win) return RET_OK;
    memset(&ws, 0, sizeof ws);
    return RET_OK;
}

/* Static rows (None, WPA2/WPA3, WPA3) with the check on the page's current choice, and the list's scroll fade: the payload binds them and puts the check. */
static void ws_open(void) {
    char n[16];
    int i, cur = wo.sec == WF_OPEN ? 0 : wo.sec == WF_TRANS ? 1 : 2;
    if (ws.win) return;
    memset(&ws, 0, sizeof ws);
    ws.win = window_open("m1plus_wifisec");
    if (!ws.win) {
        memset(&ws, 0, sizeof ws);
        return;
    }
    widget_on(ws.win, EVT_DESTROY, ws_on_destroy, ws.win);
    pod_bind(ws.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(ws.win, "btn_backtoplayer", pod_on_player, (void *)0);
    ws.sv = widget_lookup(ws.win, "wifisec_scrollview", 1);
    ws.fade = widget_lookup(ws.win, "img_nb_fade", 1);
    for (i = 0; i < 3; i++) {
        snprintf(n, sizeof n, "ws_row%d", i);
        if (!pod_bind(ws.win, n, ws_on_row, (void *)(long)(i + 1))) ws.sv = (void *)0;
        snprintf(n, sizeof n, "ws_check%d", i);
        wp_vis(widget_lookup(ws.win, n, 1), i == cur);
    }
    if (!ws.sv) {
        navigator_back();
        return;
    }
    widget_on(ws.sv, EVT_SCROLL, ws_on_scroll, (void *)0);
    widget_on(ws.sv, EVT_SCROLL_END, ws_on_scroll, (void *)0);
}

/* The switch row: stock's sequence. Turning Wi-Fi on while Bluetooth is on shows the coex warning (msg_wifi_open, docs/modules/overlays.md) and leaves Bluetooth on. */
static int wp_on_switch(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (wp.modal) return RET_OK;
    if (!wp_wifi_on() && *(volatile unsigned char *)BT_FLAG && !wp_yes(TR("msg_wifi_open"))) return RET_OK;
    wifi_switch(1);
    wp.on = wp_wifi_on();
    wp.alive = 0, wp.caps = 0, wp.nscan = 0, wp.nknown = 0, wp.n = 0, wp.nsec = 0;
    wp.want_id = -1, wp.cur = -1, wp.scan_t = -1, wp.idle_t = 0;
    memset(&wp.st, 0, sizeof wp.st);
    wp.st.id = -1;
    wp_spinner();
    wp_layout();
    return RET_OK;
}

static int wp_tick(const void *timer) {
    int on;
    (void)timer;
    if (!wp.win) return RET_OK;
    if (wp.modal) return RET_REPEAT; /* a stock dialog is up: the main loop runs under it, nothing here changes */
    wp.tick++;
    if (wp.pop_info &&
        !wk.win) { /* the password page joined a network that the info page offered: the info page goes too */
        wp.pop_info = 0;
        if (wi.win) navigator_back();
    }
    if (wp.pop_other &&
        !ws.win) { /* Wi-Fi went off with the Security picker up: the Join Wi-Fi Network page under it goes when the picker is gone */
        wp.pop_other = 0;
        if (wo.win) navigator_back();
    }
    on = wp_wifi_on();
    if (on != wp.on) { /* turned on or off elsewhere (the pull-down) */
        wp.on = on;
        wp.alive = 0, wp.caps = 0, wp.nscan = 0, wp.nknown = 0, wp.n = 0, wp.nsec = 0, wp.want_id = -1, wp.cur = -1,
        wp.scan_t = -1, wp.idle_t = 0;
        memset(&wp.st, 0, sizeof wp.st);
        wp.st.id = -1;
        wp_layout();
        if (!wp.on &&
            (wk.win || ws.win || wo.win ||
             wi.win)) { /* Wi-Fi went off under an open password, Join Wi-Fi Network, Security or info page: the one on top goes, the rest follow */
            wp.pop_info = wk.win && wi.win;
            wp.pop_other = wo.win && ws.win;
            navigator_back();
        }
    }
    if (!wp.on) return RET_REPEAT;
    if (wp.scan_t >= 0) {
        wp_spinner();
        wp.scan_t++;
        if (wp.scan_t == WP_SCAN_LEN / 2) wp_fetch();
        if (wp.scan_t >= WP_SCAN_LEN) {
            wp_fetch();
            wp.scan_t = -1;
            wp.idle_t = 0;
            wp_spinner();
        }
    } else {
        if (wp.crow >= 0) wp_spinner(); /* no scan runs while connecting: the row's circle still turns */
        if (++wp.idle_t >= WP_SCAN_IDLE && wp.fg && wp.st.state != WF_ST_CONNECTING && wp.want_id < 0) wp_scan();
    }
    if (wp.tick % WP_POLL == 0) {
        int was = wp.alive;
        wp_poll();
        if (wp.alive && !was) { /* the supplicant came up: the first scan, and the cached list is read at once */
            wp_scan();
            wp_fetch();
        } else if (wp.alive && wp.crow >= 0 && wp.scan_t < 0)
            wp_fetch(); /* connecting, so no scan of ours: the supplicant's own scans fill its table, read for the row's signal */
    }
    return RET_REPEAT;
}

static int wp_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!wp.fade) return RET_OK;
    widget_set_visible(wp.fade, I(wp.sv, SC_YOFF) > 0, 0);
    widget_set_sensitive(wp.fade, 0);
    return RET_OK;
}

static int wp_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    wp.fg = 1;
    wp.idle_t = WP_SCAN_IDLE - 4;
    return RET_OK;
}

static int wp_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    wp.fg = 0;
    return RET_OK;
}

static int wp_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != wp.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    if (wp.timer) timer_remove(wp.timer);
    memset(&wp, 0, sizeof wp);
    return RET_OK;
}

/* The Networks header's spinner goes after the header's text (measured, so it follows the language; 76 px when it cannot be measured). */
static void wp_spin_place(void) {
    void *lab = widget_lookup(wp.win, "wf_hdr_net_t", 1);
    const unsigned *t = lab ? widget_get_text(lab) : (const unsigned *)0;
    int tw = t && *t ? (int)(widget_measure_text(lab, t) + 0.999f) : 0;
    if (tw <= 0) tw = WP_HDR_TW;
    widget_move(wp.spin_img, WP_HDR_X + 2 + tw + 8, widget_get_prop_int(wp.spin_img, "y", 0));
}

/* The hook at the Wi-Fi row of the stock All System Settings hub (tools/pod.py WIFIHUB_SITE, docs/modules/payload.md hook 21): stock's row is `navigator_to("systemset/wifi_page")` and this call takes
 * its place with the same argument (the delay slot still loads it). Our page opens unless the kill switch exists (then the stock page and stock's supplicant, the only route for WEP) or the page will not open;
 * both leave stock's page, opened with stock's navigator_to each time (never restacked: its init scans on every open, 0x4b115c, and a restack runs no init; its EVT_WINDOW_TO_FG handler 0x4b0a34 only rebuilds the list from the old results). Stock ignores the result. A tap on the row only: no state, no timer, not on the boot path. */
int wifipage_open(void);
int wifi_hub_open(const char *name) {
    if (access(KILL_SD, F_OK) != 0 && wifipage_open() == 0) return 0;
    return navigator_to(name); /* a new stock page, its init scans (the result is unused by stock's row) */
}

/* Settings > Wi-Fi. 0 once the page is up (or already open); -1 when it could not open (nothing is left of it): the caller opens the stock page. */
int wifipage_open(void) {
    char n[24];
    int i;
    if (wp.win) return 0;
    memset(&wp, 0, sizeof wp);
    wp.win = window_open("m1plus_wifi");
    if (!wp.win) {
        memset(&wp, 0, sizeof wp);
        return -1;
    }
    widget_on(wp.win, EVT_DESTROY, wp_on_destroy, wp.win);
    widget_on(wp.win, EVT_WINDOW_TO_FG, wp_on_fg, (void *)0);
    widget_on(wp.win, EVT_WINDOW_TO_BG, wp_on_bg, (void *)0);
    pod_bind(wp.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(wp.win, "btn_backtoplayer", pod_on_player, (void *)0);
    wp.sv = widget_lookup(wp.win, "wifi_scrollview", 1);
    wp.fade = widget_lookup(wp.win, "img_nb_fade", 1);
    wp.sw_row = pod_bind(wp.win, "wf_row_sw", wp_on_switch, (void *)0);
    wp.sw_img = widget_lookup(wp.win, "wf_sw_img", 1);
    wp.sw_hair = widget_lookup(wp.win, "wf_hair_sw", 1);
    wp.hdr_my = widget_lookup(wp.win, "wf_hdr_my", 1);
    wp.hdr_net = widget_lookup(wp.win, "wf_hdr_net", 1);
    wp.spin_img = widget_lookup(wp.win, "wf_hdr_net_spin", 1);
    wp.other_row = pod_bind(wp.win, "wf_row_other", wp_on_other, (void *)0);
    for (i = 0; i < WP_ROWS; i++) {
        snprintf(n, sizeof n, "wf_row%d", i);
        wp.r[i].row = pod_bind(wp.win, n, wp_on_net, (void *)(long)(i + 1));
        snprintf(n, sizeof n, "wf_chk%d", i);
        wp.r[i].chk = widget_lookup(wp.win, n, 1);
        snprintf(n, sizeof n, "wf_name%d", i);
        wp.r[i].name = widget_lookup(wp.win, n, 1);
        snprintf(n, sizeof n, "wf_lock%d", i);
        wp.r[i].lock = widget_lookup(wp.win, n, 1);
        snprintf(n, sizeof n, "wf_sig%d", i);
        wp.r[i].sig = widget_lookup(wp.win, n, 1);
        snprintf(n, sizeof n, "wf_hair%d", i);
        wp.r[i].hair = widget_lookup(wp.win, n, 1);
        if (!wp.r[i].row || !wp.r[i].chk || !wp.r[i].name || !wp.r[i].lock || !wp.r[i].sig || !wp.r[i].hair)
            wp.sv = (void *)0;
    }
    if (!wp.sv || !wp.sw_row || !wp.sw_img || !wp.sw_hair || !wp.hdr_my || !wp.hdr_net || !wp.spin_img ||
        !wp.other_row) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    wp_spin_place();
    widget_on(wp.sv, EVT_SCROLL, wp_on_scroll, (void *)0);
    widget_on(wp.sv, EVT_SCROLL_END, wp_on_scroll, (void *)0);
    wp.fg = 1, wp.want_id = -1, wp.cur = -1, wp.crow = -1, wp.scan_t = -1, wp.idle_t = 0;
    wp.on = wp_wifi_on();
    memset(&wp.st, 0, sizeof wp.st);
    wp.st.id = -1;
    wp_layout();
    if (wp.on) {
        wp_poll();
        if (wp.alive) {
            wp_fetch(); /* the supplicant's table as it is: the list is not empty while the scan runs */
            wp_scan();
        }
    }
    wp_spinner();
    wp.timer = timer_add(wp_tick, (void *)0, WP_TICK_MS);
    if (!wp.timer) {
        navigator_back();
        return -1;
    }
    return 0;
}
