/* Software Update: our page (docs/modules/update.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opened from Settings > System > About > Software Update. The design follows q2-pod's Network Update (github.com/DiamondBond/q2-pod; patch/netupdate.c, docs/internals.md "Network Update"): ask GitHub for the
 * latest release, download its update.bin to the card, then hand over to the firmware's own TF card update. The code is our own. The network is ONE worker thread of patch/pcnet.c (pn_up_*): the page asks
 * (UI thread: the guards, then the thread) and afterwards only READS the status record from its own 250 ms timer, so AWTK is not touched from the thread.
 *
 * ui/m1plus_update.bin is the stock navbar over one block the payload fills and centres (a glyph, a title, an explanation and one or two pills; tools/pod_ui.py build_update_page) and, hidden, the Podcasts
 * refresh dialog's scrim and card (up_pd_*): the modal popup of a download. "Download and Install" asks in the stock confirm dialog (modal; Cancel starts nothing and touches no network), the popup shows the progress
 * and a Cancel button (Cancelling… until the worker has really stopped), and a finished download goes straight to the firmware's TF card update (its own confirmation, battery check and flash). Hidden widgets are
 * visible=false and sensitive=false. Back while the popup is up is its Cancel; Now Playing leaves the page and cancels what runs.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "podcasts.h"
#include "pcjson.h"
#include "pcnet.h"
#include "shot.h"
#include "upver.h"
#include "entries.h"

#define UP_TICK_MS 250
#define UP_AWAKE_TICKS 4 /* the standby and auto power-off countdowns are set again once a second */
#define UP_PD_BAR_H 6 /* the popup's bar (tools/pod_ui.py podcasts_dialog big=True) */

enum { UA_NONE = 0, UA_CHECK, UA_ASK, UA_RETRY, UA_INSTALL, UA_NOTES };

typedef struct {
    const char *glyph, *pill, *pill2;
    char title[96], text[160];
    int act, act2; /* the pills' actions (UA_*), UA_NONE: no pill */
} up_view_t;

static struct {
    void *win, *icon, *title, *text, *pill, *pill2;
    void *pd_scrim, *pd_card, *pd_title, *pd_name, *pd_count, *pd_fill, *pd_cancel;
    unsigned timer, ticks, sig, tries;
    int want; /* UA_CHECK / UA_RETRY: asked, waiting for the job slot (the Podcasts downloads are pausing) */
    int cancelling; /* the user cancelled (or the page was left): the worker ends by itself */
    int fg; /* this page is the front window */
    int install_wait; /* ticks until stock's TF card update is called after a download (the popup has closed and been painted) */
    int fetched; /* this page started the download that is running: when it completes, the firmware's update opens */
    int modal; /* inside a stock dialog (a modal call): the timer and the pills leave everything alone */
    int pop; /* the popup is up */
    int act, act2;
    unsigned px;
} up __attribute__((section(".scratch")));

/* tpl with its %s replaced by val, into out (the translations are printf-like, never a format). */
static void up_subst(char *out, unsigned size, const char *tpl, const char *val) {
    unsigned o = 0;
    while (*tpl && o + 1 < size) {
        if (tpl[0] == '%' && tpl[1] == 's') {
            while (*val && o + 1 < size) out[o++] = *val++;
            tpl += 2;
        } else
            out[o++] = *tpl++;
    }
    out[o] = 0;
}

static void up_set(char *out, unsigned size, const char *s) { up_subst(out, size, s, ""); }

/* A failed job: the glyph, the title, the explanation and whether another try can help. */
static void up_fail(up_view_t *v, int code, int stage) {
    int retry = 1;
    switch (code) {
    case PN_NOWIFI:
        v->glyph = "pod_es_wifi";
        up_set(v->title, sizeof v->title, TR("Connect to Wi-Fi first"));
        up_set(v->text, sizeof v->text, TR("Turn on Wi-Fi and try again."));
        break;
    case PN_NOCLOCK:
        v->glyph = "pod_es_calendar";
        up_set(v->title, sizeof v->title, TR("Set the date first"));
        up_set(v->text, sizeof v->text, TR("Secure connections need the right date."));
        break;
    case PN_NOCERT:
        v->glyph = "pod_es_lock";
        up_set(v->title, sizeof v->title, TR("Certificates missing"));
        up_set(v->text, sizeof v->text, TR("This device has no certificate bundle."));
        retry = 0;
        break;
    case PN_CERT:
        v->glyph = "pod_es_lock";
        up_set(v->title, sizeof v->title, TR("Certificate problem"));
        up_set(v->text, sizeof v->text, TR("The server's certificate was not accepted."));
        break;
    case PN_UPCHECK:
        v->glyph = "pod_es_info";
        up_set(v->title, sizeof v->title, TR("Can't check for updates"));
        up_set(v->text, sizeof v->text, TR("GitHub did not name a release. Try again later."));
        break;
    case PN_UPBAD:
        v->glyph = "pod_es_info";
        up_set(v->title, sizeof v->title, TR("Download doesn't match"));
        up_set(v->text, sizeof v->text, TR("The file was not the version offered. Nothing was changed."));
        break;
    case PN_CARDFULL:
        v->glyph = "pod_es_card";
        up_set(v->title, sizeof v->title, TR("Card is full"));
        up_set(v->text, sizeof v->text, TR("Free at least 110 MB on the card."));
        break;
    case PN_STORAGE:
        v->glyph = "pod_es_card";
        up_set(v->title, sizeof v->title, TR("Can't write to the card"));
        up_set(v->text, sizeof v->text, TR("Check the TF card and try again."));
        break;
    case PN_MEM:
        v->glyph = "pod_es_drive";
        up_set(v->title, sizeof v->title, TR("Not enough memory"));
        break;
    case PN_CANCELLED:
        v->glyph = "pod_es_download";
        up_set(v->title, sizeof v->title, TR("Download cancelled"));
        v->pill = TR("Download and Install");
        v->act = UA_ASK;
        return;
    default:
        v->glyph = "pod_es_plug";
        up_set(v->title, sizeof v->title, TR("Can't reach GitHub"));
        up_set(v->text, sizeof v->text, TR("Check your Wi-Fi connection."));
        break;
    }
    if (retry) v->pill = TR("Try Again"), v->act = stage == 2 ? UA_RETRY : UA_CHECK;
}

/* The offered release: its glyph, title and the installed version. */
static void up_offer_view(up_view_t *v) {
    v->glyph = "pod_es_download";
    up_subst(v->title, sizeof v->title, TR("Version %s available"), pn_up_tag());
    up_subst(v->text, sizeof v->text, TR("Current version: %s"), M1PLUS_TAG);
}

/* What the worker's record says, as the block shows it (the download itself is the popup's). */
static void up_state(up_view_t *v) {
    int st = pn_up_state();
    v->glyph = v->pill = v->pill2 = "";
    v->title[0] = v->text[0] = 0;
    v->act = v->act2 = UA_NONE;
    if (up.want == UA_CHECK || st == PN_U_CHECKING) {
        up_set(v->title, sizeof v->title, TR("Checking…"));
        return;
    }
    if (up.want == UA_RETRY || st == PN_U_DOWNLOADING) {
        up_offer_view(v); /* under the popup */
        return;
    }
    if (st == PN_U_CHECKED && pn_up_result() == PN_U_AVAILABLE) {
        up_offer_view(v);
        v->pill = TR("Download and Install");
        v->act = UA_ASK;
        if (pn_up_notes()[0])
            v->pill2 = TR("Release Notes"), v->act2 = UA_NOTES; /* only when the check kept the notes */
    } else if (st == PN_U_CHECKED) {
        v->glyph = "pod_es_check";
        up_set(v->title, sizeof v->title, TR("Up to Date"));
        up_set(v->text, sizeof v->text, TR("You have the latest version."));
        v->pill = TR("Check for Update");
        v->act = UA_CHECK;
    } else if (st == PN_U_DOWNLOADED) {
        v->glyph = "pod_es_check";
        up_set(v->title, sizeof v->title, TR("Update Downloaded"));
        up_subst(v->text, sizeof v->text, TR("Version %s is ready to install."), pn_up_tag());
        v->pill = TR("Install");
        v->act = UA_INSTALL;
        v->pill2 = TR("Check Again");
        v->act2 = UA_CHECK;
    } else if (st == PN_U_FAILED)
        up_fail(v, pn_up_code(), pn_up_stage());
    else {
        v->glyph = "pod_es_download";
        up_set(v->title, sizeof v->title, "M1+ Music"); /* the brand: not translated */
        up_subst(v->text, sizeof v->text, TR("Version %s"), M1PLUS_TAG);
        v->pill = TR("Check for Update");
        v->act = UA_CHECK;
    }
}

/* The block on the page: the parts the state has, each at its FIXED place (tools/pod_ui.py UP_YS: the same in every state, centred in the 400 px under the navbar), so nothing jumps between states. */
static void up_apply(const up_view_t *v) {
    int g = v->glyph[0], t = v->text[0], p = v->act != UA_NONE, p2 = v->act2 != UA_NONE;
    if (g) image_base_set_image(up.icon, v->glyph);
    widget_set_text_utf8(up.title, v->title);
    widget_set_visible(up.title, 1, 0);
    if (t) widget_set_text_utf8(up.text, v->text);
    if (p) widget_set_text_utf8(up.pill, v->pill);
    if (p2) widget_set_text_utf8(up.pill2, v->pill2);
    m1_show(up.icon, g);
    m1_show(up.text, t);
    m1_show(up.pill, p);
    m1_show(up.pill2, p2);
    up.act = v->act;
    up.act2 = v->act2;
    widget_invalidate_force(up.win, (void *)0);
}
/* The popup of a download: shown while the worker downloads (or the download waits for the job slot), its title, grey line, bar and percentage from the record, Cancel live unless it was pressed. */
static int up_popup_wanted(void) { return up.want == UA_RETRY || pn_up_state() == PN_U_DOWNLOADING; }

static void up_popup(void) {
    int on = up_popup_wanted();
    unsigned pct = up.want ? 0u : pn_up_pct(), px;
    char s[64];
    if (on) {
        up_subst(s, sizeof s, TR("Downloading %s"), pn_up_tag());
        widget_set_text_utf8(up.pd_title, s);
        widget_set_text_utf8(up.pd_name, TR("This may take a few minutes."));
        if (up.cancelling)
            widget_set_text_utf8(up.pd_count, TR("Cancelling…"));
        else {
            snprintf(s, sizeof s, "%u%%", pct);
            widget_set_text_utf8(up.pd_count, s);
        }
        px = PD_BAR_W * pct / 100;
        if (px < 1) px = 1;
        if (px != up.px || !up.pop) {
            up.px = px;
            widget_resize(up.pd_fill, (int)px, UP_PD_BAR_H);
        }
        widget_set_sensitive(up.pd_cancel, !up.cancelling);
    }
    if (on != up.pop) {
        m1_show(up.pd_scrim, on);
        m1_show(up.pd_card, on);
        if (on) widget_set_sensitive(up.pd_cancel, !up.cancelling);
        up.pop = on;
    }
}

static unsigned up_sig(void) {
    return (unsigned)pn_up_state() | (unsigned)pn_up_code() << 4 | (unsigned)pn_up_result() << 9 |
           (unsigned)pn_up_stage() << 11 | (unsigned)up.want << 13 | (unsigned)up.cancelling << 16 |
           (pn_up_state() == PN_U_DOWNLOADING ? pn_up_pct() << 17 : 0);
}

static void up_sync(void) {
    up_view_t v;
    up_state(&v);
    up_apply(&v);
    up_popup();
    up.sig = up_sig();
}

/* The job, once no other job (a refresh, a search) holds the slot; a podcast download goes on beside it. */
static void up_start(void) {
    int kind = up.want, rc;
    if (!kind) return;
    if (pn_busy() || pn_job_busy()) return;
    rc = kind == UA_CHECK ? pn_up_check() : pn_up_download();
    if (rc == PN_BUSY) return;
    up.want = 0; /* started, or refused (the state says why) */
    up.fetched = kind == UA_RETRY && rc == 0;
}

/* The page's block cleared (visible=false and sensitive=false: glyph, texts, both pills) while a stock dialog is up: the dialog is translucent, so the page behind would show through it. up_sync puts it back. */
static void up_hide_block(void) {
    m1_show(up.icon, 0);
    m1_show(up.text, 0);
    m1_show(up.pill, 0);
    m1_show(up.pill2, 0);
    widget_set_visible(up.title, 0, 0);
}

/* The firmware's own TF card update (its click handler on systemset/fwupdate_page: its confirmation, the battery check, the flash) over the cleared page. The confirmation is modal (navigator_to_with_context, 0x4a71cc: the
 * call returns the answer, 0xa for Yes), so the call returns after it; the flash dialog after a Yes is opened by navigator_to (0x4a7208) and the call returns. The block is restored whatever came back. */
static void up_install(void) {
    up_hide_block();
    up.modal = 1;
    tf_update_click((void *)0, (void *)0);
    if (!up.win) return;
    up.modal = 0;
    up_sync();
}

/* The confirm dialog's two buttons become Cancel (left, btn_cancel) and Download (right, btn_enter), found by the dialog's name once it is up (the Screenshot dialog's way: patch/shot.c). */
static int up_relabel(const void *timer) {
    void *wm = window_manager(), *dlg = wm ? widget_lookup(wm, SHOT_DIALOG, 1) : (void *)0, *b;
    (void)timer;
    if (!dlg) return ++up.tries < SHOT_RELABEL_TRIES ? RET_REPEAT : RET_OK;
    if ((b = widget_lookup(dlg, SHOT_BTN_SHORT, 1)) != (void *)0) widget_set_text_utf8(b, TR("Cancel"));
    if ((b = widget_lookup(dlg, SHOT_BTN_LONG, 1)) != (void *)0) widget_set_text_utf8(b, TR("Download"));
    return RET_OK;
}

/* Download and Install: the release, its size and what it replaces are asked first; Cancel does nothing at all (no request is made). */
static void up_ask(void) {
    char text[200];
    int code;
    up_subst(text, sizeof text, TR("Download %s (55 MB)? It replaces update.bin on the card."), pn_up_tag());
    up.tries = 0;
    up_hide_block(); /* the stock dialog is translucent: the page behind it is cleared, so its text does not show through */
    timer_add(up_relabel, (void *)0, SHOT_RELABEL_MS); /* a refused timer only leaves the buttons Yes / No */
    up.modal = 1;
    code = pod_confirm_code(text);
    if (!up.win) return; /* the page was closed under the dialog */
    up.modal = 0;
    if (code != CONFIRM_YES) {
        up_sync();
        return;
    }
    up.want = UA_RETRY, up.cancelling = 0;
    up_start();
    up_sync();
}

static void up_do(int act) {
    if (up.modal || up.install_wait || up.want || pn_up_state() == PN_U_CHECKING || pn_up_state() == PN_U_DOWNLOADING)
        return;
    switch (act) {
    case UA_CHECK:
        up.want = UA_CHECK, up.cancelling = 0;
        up_start();
        break;
    case UA_RETRY:
        up.want = UA_RETRY, up.cancelling = 0;
        up_start();
        break;
    case UA_ASK:
        up_ask();
        return;
    case UA_INSTALL:
        up_install();
        return;
    case UA_NOTES:
        relnotes_open(); /* (this page stays as it is; Back returns to it) */
        return;
    default:
        return;
    }
    up_sync();
}

static int up_on_pill(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    up_do(up.act);
    return RET_OK;
}

static int up_on_pill2(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    up_do(up.act2);
    return RET_OK;
}

/* The popup's Cancel: a download still waiting for the slot is dropped; a running one is asked to stop and the popup says Cancelling… until the worker has. */
static int up_on_cancel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!up.pop || up.modal) return RET_OK;
    if (up.want)
        up.want = 0;
    else if (!up.cancelling)
        up.cancelling = 1, up.fetched = 0, pn_cancel(PN_K_UPDATE);
    up_sync();
    return RET_OK;
}

static int up_on_back(void *ctx, void *e) {
    if (up.pop) return up_on_cancel(ctx, e); /* Back under the popup is its Cancel */
    return m1_on_back(ctx, e);
}

static int up_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    up.fg = 1;
    return RET_OK;
}

static int up_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    up.fg = 0;
    return RET_OK;
}

static int up_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != up.win) return RET_OK; /* an earlier window's end leaves a newer page alone */
    m1_timer_stop(&up.timer);
    if (pn_up_state() == PN_U_CHECKING || pn_up_state() == PN_U_DOWNLOADING)
        pn_cancel(PN_K_UPDATE); /* the worker ends by itself and removes its .part */
    memset(&up, 0, sizeof up);
    return RET_OK;
}

static int up_tick(const void *timer) {
    int st;
    (void)timer;
    if (!up.win) return RET_OK; /* (the destroy handler removes the timer: this only ends a stray one) */
    if (up.modal) return RET_REPEAT; /* a stock dialog is up: the main loop runs under it, nothing here changes */
    if (up.install_wait && --up.install_wait == 0) {
        if (up.fg)
            up_install(); /* the tick after the popup closed and the block was cleared: both have been painted */
        else
            up_sync(); /* another window came in front meanwhile: the block comes back, the Install pill does it later */
    }
    if (up.want) up_start();
    st = pn_up_state();
    if ((st == PN_U_CHECKING || st == PN_U_DOWNLOADING) && ++up.ticks % UP_AWAKE_TICKS == 0)
        reset_poweroptions_timer(
            1, 1, 0); /* a download must not meet standby or auto power-off (stock standby stops the Wi-Fi) */
    if (up.cancelling && !pn_job_busy()) up.cancelling = 0;
    if (up.sig != up_sig()) up_sync();
    if (up.fetched && st == PN_U_DOWNLOADED) {
        up.fetched = 0;
        up_sync(); /* the popup goes, the page says it */
        if (up.fg) up_hide_block(); /* and the block is cleared now, so it is painted cleared before the dialog opens */
        if (up.fg)
            up.install_wait =
                1; /* the file is there: stock's TF card update takes over at its own confirmation, one tick later, the block cleared and painted before the dialog opens */
    } else if (up.fetched && st != PN_U_DOWNLOADING)
        up.fetched = 0;
    return RET_REPEAT;
}

/* Open: Settings > System > About > Software Update. 0 once the page is up (or already open); -1 when it could not open (nothing is left of it). */
int update_open(void) {
    int st;
    if (up.win) return 0;
    memset(&up, 0, sizeof up);
    up.win = window_open("m1plus_update");
    if (!up.win) {
        memset(&up, 0, sizeof up);
        return -1;
    }
    widget_on(up.win, EVT_DESTROY, up_on_destroy, up.win);
    widget_on(up.win, EVT_WINDOW_TO_FG, up_on_fg, (void *)0);
    widget_on(up.win, EVT_WINDOW_TO_BG, up_on_bg, (void *)0);
    m1_bind(up.win, "btn_return", up_on_back, (void *)0);
    m1_bind(up.win, "btn_backtoplayer", m1_on_player, (void *)0);
    up.icon = widget_lookup(up.win, "up_icon", 1);
    up.title = widget_lookup(up.win, "up_title", 1);
    up.text = widget_lookup(up.win, "up_text", 1);
    up.pill = m1_bind(up.win, "up_pill", up_on_pill, (void *)0);
    up.pill2 = m1_bind(up.win, "up_pill2", up_on_pill2, (void *)0);
    up.pd_scrim = widget_lookup(up.win, "up_pd_scrim", 1);
    up.pd_card = widget_lookup(up.win, "up_pd_card", 1);
    up.pd_title = widget_lookup(up.win, "up_pd_title", 1);
    up.pd_name = widget_lookup(up.win, "up_pd_name", 1);
    up.pd_count = widget_lookup(up.win, "up_pd_count", 1);
    up.pd_fill = widget_lookup(up.win, "up_pd_fill", 1);
    up.pd_cancel = m1_bind(up.win, "up_pd_cancel", up_on_cancel, (void *)0);
    if (!up.icon || !up.title || !up.text || !up.pill || !up.pill2 || !up.pd_scrim || !up.pd_card || !up.pd_title ||
        !up.pd_name || !up.pd_count || !up.pd_fill || !up.pd_cancel) {
        navigator_back(); /* an asset that is not ours: the destroy handler frees what exists */
        return -1;
    }
    label_set_line_wrap(up.text, 1);
    widget_set_prop_bool(up.text, "word_wrap", 1);
    up.fg = 1;
    st = pn_up_state();
    up.cancelling =
        st == PN_U_CHECKING || st == PN_U_DOWNLOADING; /* a job of the page left a moment ago is still ending */
    if (!up.cancelling) pn_up_reset(); /* an old answer or failure is not shown again */
    up_sync();
    up.timer = timer_add(up_tick, (void *)0, UP_TICK_MS);
    if (!up.timer) {
        navigator_back();
        return -1;
    }
    return 0;
}
