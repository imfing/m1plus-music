/* The scrobble upload settings (docs/modules/scrobble.md "Settings"): the Scrobbling page's ListenBrainz, Last.fm and Upload Scrobbles rows and the two account pages (one Account row each).
 * All are Settings cards pages of patch/m1plus.c (tools/pod_pages.py SCROBBLING_PAGE, LB_PAGE, LF_PAGE), which binds the rows and asks this file for their texts and their taps; the upload and the
 * accounts are patch/scrobup.c's (one worker thread, an upload or a check). The accounts are the card's scrobble.ini, written on a computer: nothing here sets or removes one.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One timer (LB_TICK_MS), only while one of the three pages is up and a job is in flight or its result is not shown yet: it polls the job this file started (lbs.job), and only that one.
 * scrobup_owner and scrobup_kind are asked before every poll: the automatic upload's job, a job of another kind, or none, means the result is not ours, and nothing is read. An
 * automatic upload (patch/scrobble.c) is only watched (scrobup_busy) so that the rows follow it; once it is over scrobble_auto_collect takes its result, without a toast, so that it
 * never blocks a start here. With the screen dark the tick polls and nothing else: the toast and the rows wait for the first lit tick. While our job runs the tick sets
 * stock's standby countdown again once a second (reset_poweroptions_timer(1, 1, 0), as the Software Update page: standby would stop the Wi-Fi). A job that ends after both pages closed is
 * polled when one opens again. Nothing here runs at boot, from the main loop or without a tap or a page.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "i18n.h"
#include "scrobble.h"
#include "scrobup.h"
#include "scrobpage.h"

#define LB_TICK_MS 500
#define LB_AWAKE_TICKS 2 /* the standby countdown is set again every second while our job runs */

static struct {
    unsigned timer, ticks;
    int pages; /* bit 0: the Scrobbling page is up, bit 1: the ListenBrainz page, bit 2: the Last.fm page */
    int job; /* the job this file started and has not polled the result of: 0 none, else 1 + SCROBUP_UPLOAD / SCROBUP_CHECK / SCROBUP_LFCHECK */
    int done, kind, res, sent, rej,
        auth; /* a result that was polled and is not shown yet (auth: scrobup_auth, the services that refused) */
} lbs __attribute__((section(".scratch")));

static int lb_tick(const void *timer);

void lb_row_text(char *out, unsigned n) {
    char name[SU_NAME];
    name[0] = 0;
    if (!scrobup_account(name, sizeof name))
        snprintf(out, n, "%s", TR("Not Set"));
    else if (scrobup_invalid())
        snprintf(out, n, "%s", TR("Invalid Token"));
    else
        snprintf(out, n, "%s", name);
}

void lb_account_text(char *out, unsigned n) {
    char name[SU_NAME];
    name[0] = 0;
    if (!scrobup_account(name, sizeof name))
        snprintf(out, n, "%s", TR("Not Set"));
    else if (scrobup_busy() && scrobup_kind() == SCROBUP_CHECK)
        snprintf(out, n, "%s", TR("Checking…"));
    else if (scrobup_invalid())
        snprintf(out, n, "%s", TR("Invalid Token"));
    else
        snprintf(out, n, "%s", name);
}

/* The Last.fm rows: the USER value of the file, or its state. */
void lf_row_text(char *out, unsigned n) {
    char name[SU_NAME];
    int st = scrobup_lastfm(name, sizeof name);
    snprintf(out, n, "%s", st == SCROBUP_LF_NONE ? TR("Not Set") : st == SCROBUP_LF_BAD ? TR("Sign-in Failed") : name);
}

void lf_account_text(char *out, unsigned n) {
    if (scrobup_lastfm((char *)0, 0) != SCROBUP_LF_NONE && scrobup_busy() && scrobup_kind() == SCROBUP_LFCHECK)
        snprintf(out, n, "%s", TR("Checking…"));
    else
        lf_row_text(out, n);
}

/* The timer, while a page is up and there is a job to wait for or a result to show. */
static void lb_watch(void) {
    if (!lbs.timer && lbs.pages && (lbs.job || lbs.done || scrobup_busy()))
        lbs.timer = timer_add(lb_tick, (void *)0, LB_TICK_MS);
}

/* Our job's result, once: only while the job that runs is the one this file started (its owner and its kind are asked first). An automatic upload that is over is collected
 * first, silently (Invalid Token, if it found that, is on the rows at their next refresh). */
static void lb_poll(void) {
    int sent = 0, r;
    scrobble_auto_collect();
    if (!lbs.job || lbs.done) return;
    if (!scrobup_busy() || scrobup_owner() != SCROBUP_UI || scrobup_kind() != lbs.job - 1) {
        lbs.job = 0; /* its result went to another caller: nothing to read, nothing to say */
        return;
    }
    r = scrobup_poll(&sent);
    if (!r) return;
    lbs.kind = lbs.job - 1;
    lbs.job = 0;
    /* (SCROBUP_AUTH: the poll keeps Invalid Token, scrobup_invalid; the token stays in the file until another one is written there) */
    lbs.done = 1, lbs.res = r, lbs.sent = sent, lbs.rej = scrobup_rejected(), lbs.auth = scrobup_auth();
}

static void lb_check(int lf);

/* The polled result on screen: an upload's toast (a check says nothing: the rows show the name or the refusal); a refusal names its service. After the ListenBrainz
 * check a Last.fm account that waits for its own is asked next (one job at a time). */
static void lb_show(void) {
    char t[128];
    int r = lbs.res;
    if (!lbs.done) return;
    lbs.done = 0;
    if (lbs.kind == SCROBUP_UPLOAD) {
        if (r == SCROBUP_AUTH && (lbs.auth & SCROBUP_LB))
            snprintf(t, sizeof t, "ListenBrainz: %s", TR("Invalid Token"));
        else if (r == SCROBUP_AUTH)
            snprintf(t, sizeof t, "Last.fm: %s", TR("Sign-in Failed"));
        else if (r == SCROBUP_DISK)
            snprintf(t, sizeof t, TR("Card error, %d sent"), lbs.sent);
        else if (r != SCROBUP_OK)
            snprintf(t, sizeof t, TR("Upload failed, %d sent"), lbs.sent);
        else if (lbs.rej > 0)
            snprintf(t, sizeof t, TR("%d sent, %d rejected"), lbs.sent, lbs.rej);
        else if (lbs.sent > 0)
            snprintf(t, sizeof t, TR("Scrobbles sent: %d"), lbs.sent);
        else
            snprintf(t, sizeof t, "%s", TR("Nothing to upload"));
        pod_toast(t);
    } else if (lbs.kind == SCROBUP_CHECK)
        lb_check(1);
    pod_lb_refresh();
}

static int lb_tick(const void *timer) {
    (void)timer;
    if (!lbs.pages) { /* (the destroy handler removes the timer: this only ends a stray one) */
        lbs.timer = 0;
        return RET_OK;
    }
    lb_poll();
    if (lbs.job) {
        if (++lbs.ticks % LB_AWAKE_TICKS == 0) reset_poweroptions_timer(1, 1, 0);
        return RET_REPEAT;
    }
    if (!lbs.done && scrobup_busy()) return RET_REPEAT; /* an automatic upload: watched, collected when it is over */
    if (!m1_screen_lit()) return RET_REPEAT; /* what is left is the toast and the rows: at the first lit tick */
    lbs.timer = 0;
    if (lbs.done)
        lb_show();
    else
        pod_lb_refresh();
    return RET_OK;
}

/* An account no check has confirmed is asked of the service, when the Wi-Fi is connected and no job runs: ListenBrainz a token without a name (and not refused),
 * Last.fm credentials not asked since the boot. */
static void lb_check(int lf) {
    char name[SU_NAME];
    if (get_wifisignal() > 0 && !lbs.job && !scrobup_busy()) {
        if (lf) {
            if (scrobup_lastfm((char *)0, 0) == SCROBUP_LF_NEW && scrobup_lastfm_check_start(SCROBUP_UI) == 1)
                lbs.job = 1 + SCROBUP_LFCHECK;
        } else if (scrobup_account(name, sizeof name) && !name[0] && !scrobup_invalid() &&
                   scrobup_check_start(SCROBUP_UI) == 1)
            lbs.job = 1 + SCROBUP_CHECK;
    }
    lb_watch();
}

/* Upload Scrobbles. In this order: a job that runs, USB mode, no card (the token is on the card: neither is "no token"), no token (the card's scrobble.ini is read again first, as scrobup_start does), no Wi-Fi; then the start. The
 * Scrobbling switch is not asked. */
void lb_upload_tap(void) {
    int r;
    lb_poll(); /* a job of ours that ended while no page was up: its result first (and an automatic upload that is over is out of the way) */
    if (lbs.done) {
        lb_show();
        return;
    }
    if (scrobup_busy()) {
        pod_toast(TR("Already uploading"));
        lb_watch();
        return;
    }
    scrobup_forget(); /* the file as it is now */
    if (navigator_window_is_exist(SCROBUP_USB_PAGE))
        pod_toast(TR("Not available in USB mode")); /* (the computer has the card, and the token with it) */
    else if (!m1_card_mounted())
        pod_toast(TR("Storage unavailable")); /* (no card is no account, but not one to set up) */
    else if (!scrobup_configured()) /* (either service: the upload goes to every one that is set up) */
        pod_toast(TR("Set up an account first"));
    else if (get_wifisignal() <= 0)
        pod_toast(TR("Connect to Wi-Fi first"));
    else if ((r = scrobup_start(SCROBUP_UI)) == 1) {
        lbs.job = 1 + SCROBUP_UPLOAD;
        pod_toast(TR("Uploading scrobbles"));
        lb_watch();
    } else if (r == 0)
        pod_toast(TR("Already uploading"));
    else
        pod_toast(TR("Storage unavailable")); /* (-1 with a card and a token: the kill switch, or no thread) */
    pod_lb_refresh();
}

static int lb_on_destroy(void *ctx, void *e) {
    (void)e;
    lbs.pages &= ~(int)(long)ctx;
    if (!lbs.pages) m1_timer_stop(&lbs.timer); /* a job that still runs is polled when a page opens again */
    return RET_OK;
}

/* Back in front (patch/m1plus.c on_page_fg, the one EVT_WINDOW_TO_FG handler of the scrobble pages). */
void lb_on_front(void) { lb_watch(); }

/* A page opens (0 the Scrobbling page, 1 ListenBrainz, 2 Last.fm): the card's scrobble.ini is read again (a computer may have changed it; only here and at an Upload
 * Scrobbles tap, never from the timer or when a page comes back in front), and an account no check has confirmed yet is asked of the service: the page's own first, the
 * other one when that needs no check (lb_show asks Last.fm after a ListenBrainz check). */
void lb_opened(void *win, int page) {
    char was[SU_NAME], now[SU_NAME], lwas[SU_NAME], lnow[SU_NAME];
    int had, has, bad, job, lst;
    lbs.pages |= 1 << page;
    widget_on(win, EVT_DESTROY, lb_on_destroy, (void *)(long)(1 << page));
    lb_poll();
    had = scrobup_account(was, sizeof was), bad = scrobup_invalid(), job = lbs.job,
    lst = scrobup_lastfm(lwas, sizeof lwas);
    scrobup_forget();
    has = scrobup_account(now, sizeof now);
    lb_check(page == 2);
    lb_check(page != 2);
    if (has != had || strcmp(was, now) || bad != scrobup_invalid() || job != lbs.job ||
        lst != scrobup_lastfm(lnow, sizeof lnow) || strcmp(lwas, lnow))
        pod_lb_refresh(); /* (the page read its rows before this; a result polled above is shown, and the rows read again, at the first tick) */
    lb_watch();
}
