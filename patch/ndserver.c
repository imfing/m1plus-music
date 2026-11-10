/* The Subsonic Server page (docs/modules/subsonic.md, task ND-12): the saved server as three rows (Server URL, Username, Password), two action rows (Sync Now, Sign Out), and the Sign In page
 * that the three field rows open. The Server page's asset is tools/pod_ndserver.py (window m1plus_ndserver: the Settings cards, rows pod_row0..pod_row4, the values pod_value0..2); the Sign In
 * page's is its build_login (window m1plus_ndlogin).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The login follows the setup chain of the pull request's patch/subsonic.c, removed in the rebuild (Gaurav Mishra, MIT).
 *
 * Sign In is the Join Wi-Fi Network page's design (patch/wifipage.c wo_*): three rows on one page with our keyboard embedded (one field that moves to the row tapped; the other rows show their value in a
 * label), the password dots with an eye, the action key reading Next until the whole login is valid and Sign In after, dimmed while the field cannot go on. Sign In checks the login (sba_conf_check: a refused
 * value is the error line), asks for a ping with it (sba_ping_try, patch/sbapi.h: nothing is saved yet) and shows a spinner and "Connecting..." under the card while it runs; a failed ping is a grey line under the card (wrong user or
 * password, no answer, certificate, clock, Wi-Fi) and the page stays; a good one saves the login (the cache goes only if the server or user changed), starts a sync and goes back to the page it was opened from (the Server page, or the root page when no server was saved); a failed one leaves the saved login and cache alone. A password left empty keeps the saved one.
 * Sync Now and Sign Out ask first (the confirm dialog). Sign Out is sba_conf_clear: the login and the cache go, the downloaded music stays. Both pages read sba_* only on the UI thread; Sign In has a timer of
 * its own only while it waits for the ping.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "azlist.h"
#include "i18n.h"
#include "keyboard.h"
#include "libsrc.h"
#include "sbapi.h"
#include "sbsrc.h"

#define NS_ROWS 5
#define NS_VALUES 3
/* The value box's right edge in its row (tools/pod_ndserver.py VALUE_RIGHT: the chevron's left edge less the gap). */
#define NS_VALUE_RIGHT 280
#define NS_LABEL_X 24 /* the labels' left edge (card inset + padding) */
#define NS_GAP 10 /* the room kept between a label and its value */
#define NS_TICK_MS 500 /* the Server page re-reads the sync state (the root page's tick) */
#define NS_FORCE_TICKS 8 /* and, anyway, every 4 s (the age text moves on) */
#define NS_SPIN_PX 14 /* the Sync Now row's spinner (tools/pod_ndserver.py SYNC_SPIN_PX) and the gap after it */
#define NS_SPIN_GAP 6

extern void nd_synced_line(char *out,
                           unsigned size); /* patch/ndroot.c: "Synced 5m ago" / "Synced just now" / "Not synced yet" */

enum { NS_URL, NS_USER, NS_PASS, NS_SYNC, NS_OUT };

static struct {
    void *win;
    void *sv, *title,
        *fade; /* the scroll view, the navbar's small title and the fade under the bar (the large title's collapse) */
    int title_on, noscroll;
    void *spin; /* the Sync Now row's spinner */
    unsigned timer, gen, ticks;
    int state; /* the Sync Now row as last written: -1 nothing yet, else conf * 2 + running */
    char text[64]; /* the Sync Now row's value as last written */
} ns __attribute__((section(".scratch")));

static void *ns_find(const char *base, int i) {
    char name[24];
    snprintf(name, sizeof name, "%s%d", base, i);
    return widget_lookup(ns.win, name, 1);
}

/* A label's width: its text measured (0 for none) and 6 px of slack. */
static int ns_width(void *w) {
    const unsigned *t = widget_get_text(w);
    return t && *t ? (int)(widget_measure_text(w, t) + 0.999f) + 6 : 0;
}

/* The value takes the room its text needs and the label keeps the rest, right aligned at the same edge (patch/m1plus.c value_fit). */
static void ns_value(int i, const char *text, int reserve) {
    void *val = ns_find("pod_value", i), *lab = ns_find("pod_label", i);
    int vw, max;
    if (!val || !lab) return;
    widget_set_text_utf8(val, text);
    max = NS_VALUE_RIGHT - NS_LABEL_X - ns_width(lab) - NS_GAP - reserve;
    vw = ns_width(val);
    if (vw < 8) vw = 8;
    if (vw > max) vw = max;
    widget_move(val, NS_VALUE_RIGHT - vw, widget_get_prop_int(val, "y", 0));
    widget_resize(val, vw, widget_get_prop_int(val, "h", 0));
    widget_resize(lab, NS_VALUE_RIGHT - vw - 8 - reserve - NS_LABEL_X, widget_get_prop_int(lab, "h", 0));
}

/* The three values: the host, the user and four dots when a password is saved. */
static void ns_refresh(void) {
    if (!ns.win) return;
    ns_value(NS_URL, sba_host(), 0);
    ns_value(NS_USER, sba_user(), 0);
    ns_value(NS_PASS, sba_password_saved() ? "\xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2" : "", 0);
}

static void ns_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* A label's text colour, in every state it can show (the root card's Sync Now row greys the same way). */
static void ns_colour(void *w, const char *rgb) {
    static const char *const prop[3] = {"style:normal:text_color", "style:disable:text_color",
                                        "style:focused:text_color"};
    int i;
    for (i = 0; i < 3; ++i) widget_set_prop_str(w, prop[i], rgb);
}

/* Sign In and Sync Now / Sign Out belong together: with no server saved the page is the three rows alone (Sync Now, Sign Out and the gap between are hidden). The Sync Now row tells its run: while a sync runs
 * the shared spinner and "Syncing..." (the row inactive and grey, as the root card's), after it the grey "Synced 5m ago" (the root's wording). Written only on a change. */
static void ns_sync_show(int force) {
    int conf = sba_configured(), busy = conf && sba_state(SBA_K_SYNC, "", (int *)0) == SBA_ST_LOAD,
        state = conf * 2 + busy;
    char line[sizeof ns.text];
    void *row = ns_find("pod_row", NS_SYNC), *lab = ns_find("pod_label", NS_SYNC);
    if (!ns.win || !row) return;
    if (force) ns.state = -1, ns.text[0] = 1, ns.text[1] = 0; /* (a text no real one equals) */
    if (state != ns.state) {
        ns_show(ns_find("pod_row", NS_OUT), conf);
        ns_show(row, conf);
        ns_show(widget_lookup(ns.win, "pod_gap0", 1), conf);
        widget_set_sensitive(row, conf && !busy);
        if (lab) ns_colour(lab, busy ? "#6C6C70" : "#FFFFFF");
        ls_spin(ns.spin, busy);
        if (ns.spin) widget_set_visible(ns.spin, busy, 0); /* (it takes no touch) */
    }
    ns.state = state;
    line[0] = 0;
    if (busy)
        snprintf(line, sizeof line, "%s", TR("Syncing…"));
    else if (conf)
        nd_synced_line(line, sizeof line);
    if (!strcmp(ns.text, line)) return;
    snprintf(ns.text, sizeof ns.text, "%s", line);
    ns_value(NS_SYNC, line, busy ? NS_SPIN_PX + NS_SPIN_GAP : 0);
    if (ns.spin) {
        void *val = ns_find("pod_value", NS_SYNC);
        if (val)
            widget_move(ns.spin, widget_get_prop_int(val, "x", 0) - NS_SPIN_PX - NS_SPIN_GAP,
                        widget_get_prop_int(ns.spin, "y", 0));
    }
}

/* The navbar's small title once the large one has scrolled away (pod_title_gone, the rule every large-title page shares; docs/modules/navbar.md); the fade shows while the list is scrolled. */
static void ns_title_update(void) {
    int off = ns.sv ? *(int *)((char *)ns.sv + SC_YOFF) : 0;
    pod_title_set(ns.title, &ns.title_on, ns.noscroll || pod_title_gone(off, 0));
    if (ns.fade) {
        widget_set_visible(ns.fade, off > 0, 0);
        widget_set_sensitive(ns.fade, 0);
    }
}

static int ns_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (ns.win) ns_title_update();
    return RET_OK;
}

/* Sync Now (this page's row and the root page's card): asks first, then queues the sync; a refusal such as no Wi-Fi is the toast. */
void nd_sync_now(void) {
    int rc;
    if (!sba_configured()) {
        pod_toast(TR("Add a server first"));
        return;
    }
    rc = sba_guard();
    if (rc != SBA_OK) { /* no Wi-Fi, no clock...: said at once, nothing to confirm */
        pod_toast(sbs_request_message(rc, 0));
        return;
    }
    if (!pod_confirm(TR("Sync your Subsonic library now?"))) return;
    rc = sba_sync();
    if (rc != SBA_OK) pod_toast(sbs_request_message(rc, 0));
}

/* The sync state, re-read on a timer while the page is up (the callback gets stock's timer_info_t, not a context). */
static int ns_tick(const void *timer) {
    unsigned g = sba_gen();
    (void)timer;
    if (!ns.win) return RET_OK; /* (the destroy handler removes the timer: this only ends a stray one) */
    if (g != ns.gen || ++ns.ticks % NS_FORCE_TICKS == 0) {
        ns.gen = g;
        ns_sync_show(0);
    }
    return RET_REPEAT;
}

static void ns_out(void) {
    int playing;
    if (!sba_host()[0] && !sba_user()[0] && !sba_password_saved()) {
        pod_toast(TR("Add a server first"));
        return;
    }
    if (!pod_confirm(TR("Sign out of Subsonic? Downloaded songs stay on the card."))) return;
    playing = sbs_playing_server();
    if (sba_conf_clear() != SBA_OK) {
        pod_toast(TR("Could not save settings"));
        ns_refresh();
        return;
    }
    sba_dl_cancel_all(); /* no waiting or running download outlives the sign-out (the files already on the card stay) */
    if (playing)
        stop_player(); /* a stream of the signed-out server stops with it (stock's own stop; a no-op when nothing plays) */
    navigator_back(); /* signed out: the root page shows its empty state, and Add Server there is the Sign In page */
}

/* ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 * The Sign In page (window m1plus_ndlogin, tools/pod_ndserver.py build_login)
 */
#define NL_Y0 56 /* the first row's top; rows are NL_PITCH apart (tools/pod_ndserver.py NL_Y0, NL_ROW_H) */
#define NL_PITCH 48
#define NL_X 24 /* the field's left edge */
#define NL_TW 232 /* the text room of each field (NL_TW) */
#define NL_CY 13 /* the caret's y in the field (a 48 px row) */
#define NL_MAX KB_PASS_MAX /* the longest field text (the keyboard's cap for a KB_PASSWORD field) */
#define NL_TICK_MS 250
#define NL_WAIT 160 /* ticks (40 s) the page waits for the ping before it gives up */

static struct {
    void *win, *field, *eye, *err, *busy, *spin, *v[3], *h[3];
    char text[3][NL_MAX + 1]; /* the three fields: wiped when the page ends */
    int focus; /* the row the keyboard types in */
    int shown; /* the password is shown (the eye is open) */
    int saved_pw; /* a password is saved: an empty password field keeps it */
    int touched; /* the password field was typed in (an emptied one is empty, not kept) */
    int ok; /* the action key works */
    int kb; /* the keyboard is attached */
    int connecting; /* the ping is asked and not answered */
    int ticks;
    unsigned timer;
    unsigned rid; /* the trial ping this page waits for (sba_trial_id at the ask): only its answer counts */
    char snap[3][NL_MAX + 1]; /* the login that ping was asked with: what an answer may save */
} nl __attribute__((section(".scratch")));

static void nl_vis(void *w, int on) {
    if (w) widget_set_visible(w, on, 0);
}

static int nl_prefix(const char *s, const char *p) {
    while (*p)
        if (*s++ != *p++) return 0;
    return 1;
}

/* http(s)://host[:port][/path] with no space, query, fragment or bar: what sba_conf_url_set accepts (it decides; this only keeps the key dimmed while the address cannot be one). */
static int nl_url_ok(const char *u) {
    int i = nl_prefix(u, "https://") ? 8 : nl_prefix(u, "http://") ? 7 : 0;
    if (!i || !u[i] || u[i] == '/' || u[i] == ':') return 0;
    for (; u[i]; i++)
        if ((unsigned char)u[i] <= ' ' || u[i] == 127 || u[i] == '?' || u[i] == '#' || u[i] == '|') return 0;
    return 1;
}

/* Field f can be saved: an address, a name without a bar, a password (an empty one only when the saved one is kept). */
static int nl_field_ok(int f) {
    const char *t = nl.text[f];
    int i;
    if (f == 0) return nl_url_ok(t);
    if (!t[0]) return f == 2 && nl.saved_pw && !nl.touched;
    if (f == 1)
        for (i = 0; t[i]; i++)
            if (t[i] == '|') return 0;
    return 1;
}

static int nl_all_ok(void) { return nl_field_ok(0) && nl_field_ok(1) && nl_field_ok(2); }

/* The action key: Sign In when the whole login is valid, else Next on a field that can go on (the last row has none); dimmed while connecting. */
static void nl_set_go(void) {
    int all = nl_all_ok();
    nl.ok = !nl.connecting && (all || (nl.focus < 2 && nl_field_ok(nl.focus)));
    keyboard_set_go(all ? "Sign In" : "Next", nl.ok);
}

/* One dot a character of s (four when s is NULL: the saved password's), at most 3 * NL_MAX + 1 bytes. */
static void nl_dots(char *out, const char *s) {
    unsigned n = 0, i;
    if (!s)
        for (i = 0; i < 4; i++) out[n++] = (char)0xe2, out[n++] = (char)0x80, out[n++] = (char)0xa2;
    else
        for (i = 0; s[i]; i++)
            if (((unsigned char)s[i] & 0xc0) != 0x80)
                out[n++] = (char)0xe2, out[n++] = (char)0x80, out[n++] = (char)0xa2;
    out[n] = 0;
}

/* The rows that are not typed in show their value (the dots of a password, or its text with the eye open) or, empty, the grey placeholder; the field sits on the typed row. */
static void nl_layout(void) {
    char dots[NL_MAX * 3 + 1];
    int i;
    for (i = 0; i < 3; i++) {
        const char *t = nl.text[i];
        int blank = !t[0] || (i == 0 && nl_prefix(t, "http://") && !t[7]);
        int kept = i == 2 && !t[0] && nl.saved_pw && !nl.touched;
        int on = i != nl.focus;
        nl_vis(nl.v[i], on && (!blank || kept));
        nl_vis(nl.h[i], on && blank && !kept);
        if (on && !blank) {
            if (i == 2 && !nl.shown) nl_dots(dots, t);
            az_fit(nl.v[i], i == 2 && !nl.shown ? dots : t);
        } else if (on && kept) {
            nl_dots(dots, (const char *)0);
            az_fit(nl.v[i], dots);
        }
    }
    widget_move(nl.field, NL_X, NL_Y0 + nl.focus * NL_PITCH);
    memset(dots, 0, sizeof dots);
}

static int nl_tick(const void *timer);

static void nl_stop(void) {
    if (nl.timer) timer_remove(nl.timer);
    nl.timer = 0;
    nl.connecting = 0;
    ls_spin(nl.spin, 0);
    nl_vis(nl.busy, 0);
}

/* What a failed save or ping says under the card (already translated); bad = the line for a refused value (SBA_PARSE). */
static const char *nl_message(int code, const char *bad) {
    switch (code) {
    case SBA_PARSE:
        if (bad) return bad;
        return TR("Can't connect to the server");
    case SBA_AUTH:
        return TR("Incorrect username or password");
    case SBA_NOWIFI:
        return TR("Connect to Wi-Fi first");
    case SBA_NOCLOCK:
        return TR("Set the date and time first");
    case SBA_CERT:
    case SBA_NOCERT:
        return TR("Server certificate not trusted");
    case SBA_STORAGE:
        return TR("Could not save settings");
    default:
        return TR("Can't connect to the server");
    }
}

static void nl_fail(int code, const char *bad) {
    nl_stop();
    az_fit(nl.err, nl_message(code, bad));
    nl_vis(nl.err, 1);
    nl_set_go();
}

/* The keyboard's text changed: it is the typed field's value (kept here: the other rows come and go), the action key works or not, the error line goes with a new character, and a ping being waited for
 * is no longer the login on screen. */
static void nl_change(const char *text) {
    char *d = nl.text[nl.focus];
    unsigned i;
    int same = 1;
    for (i = 0; text[i] && i < NL_MAX; i++)
        if (d[i] != text[i]) same = 0;
    if (d[i]) same = 0;
    if (same) {
        nl_set_go();
        return;
    }
    for (i = 0; text[i] && i < NL_MAX; i++) d[i] = text[i];
    memset(d + i, 0, NL_MAX + 1 - i);
    if (nl.focus == 2 && d[0]) nl.touched = 1;
    if (nl.connecting) nl_stop();
    nl_vis(nl.err, 0);
    nl_set_go();
}

static void nl_go(void);

/* The keyboard types row f: the same pad and field moved to that row, the address and the password with the English-only layout (a name keeps the language key), the password masked unless the eye is open. */
static void nl_focus(int f) {
    static const unsigned flags[3] = {KB_PASSWORD, KB_LITERAL, KB_PASSWORD};
    const char *ph = f == 0 ? TR("Server URL") : f == 1 ? TR("Username") : TR("Password");
    nl.focus = f;
    keyboard_refocus(ph, NL_TW, flags[f], nl.text[f], nl_change, nl_go);
    keyboard_set_mask(f == 2 && !nl.shown);
    nl_layout();
    nl_set_go();
}

/* The ping answered: save the login. The setters clear the cache only when the server or the user differ from the saved ones; the password only when typed (an empty field keeps the saved one). */
static int nl_save(void) {
    int rc = sba_conf_url_set(nl.text[0]);
    if (rc == SBA_OK) rc = sba_conf_user_set(nl.text[1]);
    if (rc == SBA_OK && nl.text[2][0]) rc = sba_conf_password_set(nl.text[2]);
    return rc;
}

/* Sign In: ask for a ping with the typed login and wait for it (nl_tick); only an answered ping saves it (nl_save). Nothing is written or cleared before, so a typo leaves the working login and
 * its cache alone. A refused value or a missing condition is the error line at once. */
static void nl_connect(void) {
    int rc = sba_conf_check(0, nl.text[0]);
    const char *bad = TR("Enter a valid server address");
    if (rc == SBA_OK) {
        rc = sba_conf_check(1, nl.text[1]);
        bad = TR("Enter a valid username");
    }
    if (rc == SBA_OK && nl.text[2][0]) {
        rc = sba_conf_check(2, nl.text[2]);
        bad = TR("Enter a valid password");
    }
    if (rc == SBA_OK) rc = sba_ping_try(nl.text[0], nl.text[1], nl.text[2]);
    if (rc != SBA_OK) {
        nl_fail(rc, bad);
        return;
    }
    nl.connecting = 1;
    nl.rid = sba_trial_id();
    memcpy(nl.snap, nl.text, sizeof nl.snap);
    nl.ticks = 0;
    nl_vis(nl.err, 0);
    ls_spin(nl.spin, 1);
    nl_vis(nl.busy, 1);
    nl.timer = timer_add(nl_tick, (void *)0, NL_TICK_MS);
    if (!nl.timer) nl_fail(SBA_MEM, (const char *)0);
    nl_set_go();
}

static void nl_go(void) {
    if (!nl.ok || nl.connecting) return;
    if (nl_all_ok())
        nl_connect();
    else if (nl.focus < 2)
        nl_focus(nl.focus + 1);
}

static int nl_on_hit(void *ctx, void *e) {
    int f = (int)(long)ctx;
    (void)e;
    if (nl.win && f != nl.focus) nl_focus(f);
    return RET_OK;
}

static int nl_on_eye(void *ctx, void *e) {
    static const char *const st[] = {"style:normal:icon", "style:over:icon", "style:pressed:icon"};
    int i;
    (void)ctx;
    (void)e;
    nl.shown = !nl.shown;
    if (nl.focus == 2)
        keyboard_set_mask(!nl.shown);
    else
        nl_layout();
    for (i = 0; i < 3; i++) widget_set_prop_str(nl.eye, st[i], nl.shown ? "wf_eye" : "wf_eyeoff");
    widget_invalidate_force(nl.eye, (void *)0);
    return RET_OK;
}

static int nl_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != nl.win) return RET_OK;
    if (nl.timer) timer_remove(nl.timer);
    ls_spin_end(nl.spin);
    if (nl.kb) keyboard_detach(); /* the typed text goes with the keyboard's state, the page's copy with the page */
    memset(&nl, 0, sizeof nl);
    return RET_OK;
}

static int nl_snap_same(void) {
    const char *a = &nl.snap[0][0], *b = &nl.text[0][0];
    unsigned i;
    for (i = 0; i < sizeof nl.snap; i++)
        if (a[i] != b[i]) return 0;
    return 1;
}

/* The wait for the ping (the spinner turns on the shared ls_spin timer), then the answer. */
static int nl_tick(const void *timer) {
    int st, code = 0;
    (void)timer;
    if (!nl.win || !nl.connecting) {
        if (nl.win) nl.timer = 0;
        return RET_OK;
    }
    st = sba_trial_state(nl.rid, &code);
    if (st == SBA_ST_OK) {
        int rc;
        nl.timer = 0;
        nl.connecting = 0;
        /* the fields changed since the ping was asked: that login was not the one verified */
        if (!nl_snap_same()) {
            nl_stop();
            return RET_OK;
        }
        rc = nl_save();
        if (rc != SBA_OK) {
            nl_fail(rc, (const char *)0); /* the conf could not be written: the old login stays */
            return RET_OK;
        }
        sba_sync(); /* the library; the root page's status line shows the answer */
        navigator_back();
        return RET_OK;
    }
    if (st == SBA_ST_FAIL || st == SBA_ST_NONE || ++nl.ticks >= NL_WAIT) {
        nl.timer = 0;
        nl_fail(st == SBA_ST_FAIL && code ? code : SBA_NET, (const char *)0);
        return RET_OK;
    }
    return RET_REPEAT;
}

/* The page for row `focus` (the tapped one): the saved login in the rows (an empty address starts as "http://", the password stays out of it), the keyboard on that row. */
static int nl_open(int focus) {
    char name[16];
    int i;
    if (nl.win) return -1;
    memset(&nl, 0, sizeof nl);
    nl.win = window_open("m1plus_ndlogin");
    if (!nl.win) {
        memset(&nl, 0, sizeof nl);
        return -1;
    }
    widget_on(nl.win, EVT_DESTROY, nl_on_destroy, nl.win);
    pod_bind(nl.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(nl.win, "btn_backtoplayer", pod_on_player, (void *)0);
    nl.field = widget_lookup(nl.win, "kb_field", 1);
    nl.err = widget_lookup(nl.win, "nl_err", 1);
    nl.busy = widget_lookup(nl.win, "nl_busy", 1);
    nl.spin = widget_lookup(nl.win, "nl_spin", 1);
    nl.eye = pod_bind(nl.win, "nl_eye", nl_on_eye, (void *)0);
    for (i = 0; i < 3; i++) {
        snprintf(name, sizeof name, "nl_v%d", i);
        nl.v[i] = widget_lookup(nl.win, name, 1);
        snprintf(name, sizeof name, "nl_h%d", i);
        nl.h[i] = widget_lookup(nl.win, name, 1);
        snprintf(name, sizeof name, "nl_hit%d", i);
        if (!pod_bind(nl.win, name, nl_on_hit, (void *)(long)i)) nl.field = (void *)0;
    }
    if (!nl.field || !nl.err || !nl.busy || !nl.spin || !nl.eye || !nl.v[0] || !nl.v[1] || !nl.v[2] || !nl.h[0] ||
        !nl.h[1] || !nl.h[2] ||
        keyboard_attach(nl.win, (const char *)0, 0, NL_TW, NL_CY, KB_PASSWORD, nl_change, nl_go) != 0) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    nl.kb = 1;
    snprintf(nl.text[0], sizeof nl.text[0], "%s", sba_url()[0] ? sba_url() : "http://");
    snprintf(nl.text[1], sizeof nl.text[1], "%s", sba_user());
    nl.saved_pw = sba_password_saved();
    nl_focus(focus);
    return 0;
}

static int ns_on_row(void *ctx, void *e) {
    (void)e;
    switch ((int)(long)ctx) {
    case NS_URL:
    case NS_USER:
    case NS_PASS:
        nl_open((int)(long)ctx);
        break;
    case NS_SYNC:
        nd_sync_now();
        ns_sync_show(0); /* the row shows the run at once, not at the next tick */
        break;
    case NS_OUT:
        ns_out();
        break;
    }
    return RET_OK;
}

static int ns_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ns_refresh();
    ns_sync_show(1);
    return RET_OK;
}

static int ns_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != ns.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    if (ns.timer) timer_remove(ns.timer);
    ls_spin_end(ns.spin);
    memset(&ns, 0, sizeof ns);
    return RET_OK;
}

/* Open the Server page (the Subsonic root's Server row). 0 once it is up (or already open); -1 when it could not open. */
int nd_server_open(void) {
    int i;
    if (ns.win) return 0;
    memset(&ns, 0, sizeof ns);
    ns.win = window_open("m1plus_ndserver");
    if (!ns.win) {
        memset(&ns, 0, sizeof ns);
        return -1;
    }
    widget_on(ns.win, EVT_DESTROY, ns_on_destroy, ns.win);
    widget_on(ns.win, EVT_WINDOW_TO_FG, ns_on_fg, (void *)0);
    pod_bind(ns.win, "btn_return", pod_on_back, (void *)0);
    pod_bind(ns.win, "btn_backtoplayer", pod_on_player, (void *)0);
    for (i = 0; i < NS_ROWS; ++i) {
        char name[24];
        snprintf(name, sizeof name, "pod_row%d", i);
        if (!pod_bind(ns.win, name, ns_on_row, (void *)(long)i)) {
            navigator_back(); /* an asset that is not ours: the destroy handler clears the state */
            return -1;
        }
    }
    ns.sv = widget_lookup(ns.win, "pod_scrollview", 1);
    ns.title = widget_lookup(ns.win, "label_title", 1);
    ns.fade = widget_lookup(ns.win, "img_nb_fade", 1);
    ns.noscroll = !ns.sv || !ns.title || !widget_on(ns.sv, EVT_SCROLL, ns_on_scroll, (void *)0) ||
                  !widget_on(ns.sv, EVT_SCROLL_END, ns_on_scroll,
                             (void *)0); /* without the scroll events the navbar keeps its title */
    if (ns.noscroll && ns.title) widget_set_visible(ns.title, 1, 0);
    ns.title_on = ns.noscroll;
    ns.spin = widget_lookup(ns.win, "ns_spin", 1);
    ns.state = -1;
    ns.gen = sba_gen();
    ns_refresh();
    ns_sync_show(1);
    ns.timer = timer_add(ns_tick, (void *)0, NS_TICK_MS);
    if (!ns.timer) {
        navigator_back();
        return -1;
    }
    return 0;
}

/* Add Server (the root page, with no server saved): the Sign In page on the Server URL row, with no Server page under it; a login that works goes back to the page it came from. */
int nd_signin_open(void) { return nl_open(0); }
