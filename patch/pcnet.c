/* M1+ Music Podcasts on the network: import, refresh one show or all (docs/modules/podcasts.md "Feeds").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * See patch/pcnet.h. One detached worker thread per job: for each show it reads the show file's feed url, streams the feed through libcurl into the push parser (patch/pcfeed.c;
 * verification ON with the CA bundle on the card, redirects followed, gzip accepted, time-outs and a size cap on every request), then writes .episodes and .show atomically (a temp file,
 * fsync, rename) and records the result. The thread touches no widget and calls no stock function; the status record is plain words the page reads on its own timer (a store barrier
 * before the generation counter moves). Only demo's own imports are used (libcurl's easy interface, pthread_create / pthread_detach, open / write / fsync / rename / access).
 *
 * Episode downloads (pn_dl_*, "Downloads" below) run on a thread of their own, one episode at a time, beside whatever job runs (pcnet.h "Two lanes"). The download policy follows q2-podcasts (MIT licence,
 * github.com/m-d-e-v/q2-podcasts): chunked writes, Range resume, stall limit, retries after 10, 20 and 40 s, a 32 MB free-space margin. The code is our own.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "pcjson.h"
#include "pcopml.h"
#include "pcnet.h"
#include "pccover.h"
#include "pcnotes.h"
#include "upver.h"
#include "curlopts.h"
#include "net.h"
#include "covercache.h"
#include "artistphoto.h"
#include "pcregion.h"

#define PN_PATH 400
#define PN_SHOW_MAX 4096 /* bytes of a show file read */
#define PN_URLS_MAX 16384 /* bytes of subscriptions.txt read */
#define PN_ARCH_BUF 16384 /* the refresh's archive merge writes this much at a time */
#define PN_EPS_MAX 65536 /* bytes of .episodes read and written (the model reads at most this much) */
#define PN_CARD "/mnt/mmc" /* the card: its root is searched for *.opml */
#define PN_DNAME 11 /* struct dirent (32-bit, MIPS o32): d_name at 11 (pcmodel.c PM_DNAME) */
#define PN_OPML_MAX 8 /* OPML files read by one import */

struct pn_job {
    char root[PC_FILE + 20];
    int n;
    char dirs[PC_MAX_SHOWS][PC_FILE];
};

typedef struct {
    unsigned feed, fresh;
    int code;
} pn_stat_t;

static struct {
    volatile int busy, done, total;
    volatile unsigned gen, cur;
    pn_stat_t st[PC_MAX_SHOWS]; /* (the poke of test/pod/pcfeeds.py knows the offsets above; new fields go below) */
    volatile unsigned part, base,
        span; /* the running show: how far along (0..1000, never back), and the part of 1000 the request in progress covers */
    volatile int cancel,
        stopped; /* cancel: asked by the page (read by the worker); stopped: the last job ended because of it */
    volatile unsigned ok, fail; /* the last job: shows refreshed, shows that failed */
    /* Downloads (new fields go below the ones the tests poke). kind: what the running job thread does (PN_KIND_*); dbusy: the download thread runs (a lane of its own, beside a job); dkey / dgot / dtotal / dwait: the one
     * being fetched; dgen / dstep: progress steps; dseq: the queue's order; fails: the words of the failed ones. q: the queue; a slot's state (PN_Q_*) is the whole life of its download and moves
     * only through pn_q_after's table, under pn_dmutex ("The life of a download" below); the page fills a slot under the same mutex. */
    volatile int kind, dbusy, dwait;
    volatile unsigned dkey, dgot, dtotal, dgen, dstep, dseq, nfail;
    char droot[PC_FILE + 20];
    struct {
        volatile unsigned state, seq, key;
        char dir[PC_FILE], file[PC_FILE];
    } q[PN_QMAX];
    struct {
        unsigned key;
        int code;
        char dir[PC_FILE], file[PC_FILE]; /* the names, for the Downloads page's rows */
    } fails[PN_FAILS];
    /* Search and preview (docs/modules/podcasts.md "Search"; new fields go below). sstate: PN_S_*; scode: the query's result; sgen: moves with the answer, each thumbnail and the end; sn: results (written before sstate leaves PN_S_QUERY);
     * sthumb[i]: 0 not yet, 1 the file is there (sext[i]: 1 jpg, 2 png), 2 none; pstate: 0 none, 1 running, 2 done; pcode: the preview's result; prev: the held feed (the page frees it); purl: the feed's address; pid: the Apple id to look up (0: purl is the feed). */
    volatile int sstate, scode, sn, pstate, pcode;
    volatile unsigned sgen;
    char pid[16];
    char surl[PN_PATH];
    char purl[PC_URL];
    pj_result_t sres[PJ_MAX];
    volatile unsigned char sthumb[PJ_MAX], sext[PJ_MAX];
    pf_parser_t *volatile prev;
    /* Find Cover & Lyrics (docs/modules/onlineart.md; new fields go below). astate: PN_A_*; acode: the cover lookup's result; an: covers (written before astate leaves PN_A_COVERS); agen: moves with every step; athumb / aext as sthumb /
     * sext; ares: iTunes' results first, then Deezer's (art: the picture the thumbnail is made from); asrc: PN_SRC_* of each; lstate: 0 not yet, 1 answered; lcode, ln (candidates, written before lstate is 1), lcand / lslot (the display order: slot of display index i; the text of slot s is PN_ART_DIR/l<s>.txt);
     * pkstate: 0 none, 1 running, 2 done, pkcode; pkmode: 0 fetch the larger picture only, 1 save it; fidx / fext: the cover whose larger picture is held as full.jpg|png (fidx + 1, 0 none; fext 1 jpg, 2 png);
     * the query and the pick's targets are copied here by the UI thread before the worker starts. */
    volatile int astate, acode, an, lstate, lcode, ln, pkstate, pkcode, pkidx, pkmode, fidx, fext;
    volatile unsigned agen;
    volatile unsigned char athumb[PN_ART_MAX], aext[PN_ART_MAX], asrc[PN_ART_MAX], lslot[PN_LYR_MAX];
    pj_result_t ares[PN_ART_MAX];
    pn_lyr_t lcand[PN_LYR_MAX];
    char aq[3][PN_ART_Q], pkdir[PN_PATH];
    unsigned adur, pkkey[2];
    int amask; /* the parts the worker looks up: PN_PART_COVERS | PN_PART_LYRICS */
    unsigned akey; /* pn_artist's: ap_key of the whole name asked for (aq[0] is cut) */
    int aartist; /* the lookup is pn_artist's: Deezer's artists (their photos) in place of the album covers, no lyrics */
    /* Software Update (docs/modules/update.md; new fields go below). ustate: PN_U_*; ucode: the PN_* of a failure; ustage: what the last failure or the running job was (1 the check, 2 the download); ures: the check's verdict
     * (PN_U_CURRENT, PN_U_AVAILABLE, 0 none); umode: 0 the worker checks, 1 it downloads; utag: the release the check offered (held for the download). The state is written after the code and the tag. */
    volatile int ustate, ucode, ustage, ures, umode;
    char utag[UP_TAG];
    char *
        unotes; /* the offered release's notes (heap, UP_NOTES_MAX + 1 bytes, set by the check before its state, freed by the next check), NULL for none */
    /* Podcast charts (docs/modules/podcasts.md "Discover"; new fields go below). Per chart, kind 0 the top shows and 1 the top episodes: cstate: 0 none (or the fetch was cancelled), 1 the answer is being fetched, 2 answered;
     * ccode: the answer's result; cn: rows (written before cstate is 2); creq / cshown: the storefront asked and the one the answer is of (it falls back to the United States); cthumb / cext as sthumb / sext; cres: the rows, in rank order.
     * ckind: the chart the running job is for; cgen: moves with every answer, thumbnail and end. The answers stay for the session (a changed region asks again). */
    volatile int cstate[2], ccode[2], cn[2], ckind;
    volatile unsigned cgen;
    char creq[2][4], cshown[2][4];
    volatile unsigned char cthumb[2][PJ_CHART], cext[2][PJ_CHART];
    pj_chart_t cres[2][PJ_CHART];
    char pcc[4]; /* the preview's lookup country: a chart row's, "" for a typed address or Apple link */
    char pfb
        [PJ_ART]; /* the preview's fallback picture: the store's artworkUrl600 (from the search result or the lookup), "" = none (a typed address) */
    char peid
        [16]; /* a chart's episode row: its own id (the store's episode lookup of its show names it); "" for a show row */
    volatile int pmatch; /* the kept feed item that episode is (pf_match), -1 = none: the show's preview only */
    /* AutoEq (docs/modules/peq.md "AutoEq download"; new fields go below). estate: PN_E_*; ecode: the PN_* of a failure; emode: what the worker does (0 the list, 1 a preset); epath: the preset's place below PN_EQ_BASE
     * ("Source/Kind/Name", as the index writes it); estamp: the comment line that goes first into the file. The state is written after the code. */
    volatile int estate, ecode, emode;
    char epath[PN_PATH], estamp[PN_PATH];
    /* The archive job (docs/modules/podcasts.md "All episodes"): arstate PN_AR_*, arcode the PN_* of a failure, arhash the show's hash (pc_show_t.hash), ardir its folder, arroot the Podcasts folder. */
    volatile int arstate, arcode;
    volatile unsigned arn; /* the items the running attempt has written */
    volatile unsigned
        arfh; /* the show whose job failed last (not a cancel) and the PN_* why: kept while the app runs, so that the show's row can offer a retry; 0 = none */
    volatile int arfc;
    unsigned arhash;
    char ardir[PC_FILE], arroot[PC_FILE + 20];
} pn __attribute__((section(".scratch")));

/* The life of a download: its slot's state. FREE: no download. WAIT: queued. ACTIVE: the thread fetches it. STOPPING: the page paused it (the transfer is to end, the .part stays for a later tap).
 * DROPPING: the page took it away (Remove Download, Delete, Unsubscribe: the transfer is to end, the thread writes nothing more, never puts the file in place and removes the .part). PUBLISHED: the file
 * is in place (the thread may still sync the folder): a downloaded episode, which no cancel or drop touches. */
enum { PN_Q_FREE = 0, PN_Q_WAIT = 1, PN_Q_ACTIVE = 2, PN_Q_STOPPING = 3, PN_Q_DROPPING = 4, PN_Q_PUBLISHED = 5 };
/* What happens to a download. The page: ADD (pn_dl_add fills a free slot), CANCEL, DROP, RESUME (an add of one being paused). The thread: CLAIM (it takes the next waiting one up), PUBLISH (the
 * rename), END (the run is over: done or failed), HALT (the run is over because the thread heard a pause or a drop and stopped its transfer). */
enum { PN_EV_ADD, PN_EV_CLAIM, PN_EV_CANCEL, PN_EV_DROP, PN_EV_RESUME, PN_EV_PUBLISH, PN_EV_END, PN_EV_HALT };

static int pn_starts(const char *s, const char *prefix) {
    while (*prefix && *s == *prefix) ++s, ++prefix;
    return !*prefix;
}

static int pn_join(char *out, unsigned size, const char *a, const char *b, const char *c) {
    unsigned o = 0, k;
    const char *parts[3];
    int p;
    parts[0] = a, parts[1] = b, parts[2] = c;
    for (p = 0; p < 3; ++p) {
        if (!parts[p]) continue;
        if (p) {
            if (o + 1 >= size) return 0;
            out[o++] = '/';
        }
        for (k = 0; parts[p][k]; ++k) {
            if (o + 1 >= size) return 0;
            out[o++] = parts[p][k];
        }
    }
    out[o] = 0;
    return 1;
}

static void pn_bump(void) { __sync_fetch_and_add(&pn.gen, 1); /* (two threads bump it: a job's and the downloads') */ }

static void pn_set(unsigned feed, int code, unsigned fresh) {
    int i, free_slot = -1;
    for (i = 0; i < PC_MAX_SHOWS; ++i) {
        if (pn.st[i].feed == feed) break;
        if (free_slot < 0 && !pn.st[i].feed) free_slot = i;
    }
    if (i == PC_MAX_SHOWS) i = free_slot < 0 ? 0 : free_slot;
    pn.st[i].feed = feed, pn.st[i].code = code, pn.st[i].fresh = fresh;
    if (code == PN_OK)
        ++pn.ok;
    else
        ++pn.fail;
    pn_bump();
}

int pn_busy(void) { return pn.busy && (pn.kind == PN_KIND_REFRESH || !pn.kind); }
int pn_job_busy(void) {
    return pn.busy && (pn.kind == PN_KIND_SEARCH || pn.kind == PN_KIND_PREVIEW || pn.kind == PN_KIND_ART ||
                       pn.kind == PN_KIND_PICK || pn.kind == PN_KIND_UPDATE || pn.kind == PN_KIND_CHART ||
                       pn.kind == PN_KIND_EQ || pn.kind == PN_KIND_ARCH);
}
/* (A job that ends between the look and the flag leaves the flag set with no job: the next start, on this thread, clears it.) */
void pn_cancel(unsigned kinds) {
    int kind = pn.kind ? pn.kind : PN_KIND_REFRESH; /* (as pn_busy: a slot with no kind is a refresh) */
    if (pn.busy && (kinds & PN_K(kind))) pn.cancel = 1;
}
int pn_cancelling(void) { return pn_busy() && pn.cancel; }
unsigned pn_part(void) { return pn.part; }

void pn_summary(unsigned *ok, unsigned *failed, int *cancelled) {
    *ok = pn.ok, *failed = pn.fail, *cancelled = pn.stopped;
}
unsigned pn_gen(void) { return pn.gen; }
unsigned pn_current(void) { return pn.cur; }

void pn_progress(int *done, int *total) {
    *done = pn.done;
    *total = pn.total;
}

int pn_status(unsigned feed, int *code, unsigned *fresh) {
    int i;
    for (i = 0; i < PC_MAX_SHOWS; ++i)
        if (feed && pn.st[i].feed == feed) {
            *code = pn.st[i].code, *fresh = pn.st[i].fresh;
            return 1;
        }
    return 0;
}

int pn_guard(void) {
    if (!m1_card_mounted()) return PN_STORAGE;
    if (get_wifisignal() <= 0) return PN_NOWIFI;
    if ((unsigned)time((long *)0) < PN_MIN_EPOCH) return PN_NOCLOCK;
    if (access(PN_CA, F_OK)) return PN_NOCERT;
    return PN_OK;
}

/* ---------------------------------------------------------------------------
 * Files
 */

/* ---------------------------------------------------------------------------
 * The request
 */
struct fx {
    pf_parser_t *p;
    unsigned long long total;
    int capped; /* the cap was reached: the transfer was stopped there */
    char err[160];
};

/* A feed over PN_FEED_CAP is parsed up to the cap and the transfer stopped there (a write error); feeds list the newest items first, so what was parsed is
 * kept when it holds a feed and an item (pn_fetch). The item cut by the cap is not kept: the parser keeps an item at its end tag only. */
static unsigned pn_write(char *d, unsigned size, unsigned nmemb, void *user) {
    struct fx *f = user;
    unsigned len = size * nmemb;
    if (f->total + len > PN_FEED_CAP) {
        pf_push(f->p, d, (unsigned)(PN_FEED_CAP - f->total));
        f->total = PN_FEED_CAP, f->capped = 1;
        return 0;
    }
    f->total += len;
    pf_push(f->p, d, len);
    return len;
}

/* libcurl's transfer-info callback (about once a second, and with every chunk): non-zero aborts the transfer (CURLE_ABORTED_BY_CALLBACK). The 64-bit counts are scaled down to
 * 32 bits first (no 64-bit division in the payload). The progress of the show is what the request in progress covers (pn.base, pn.span of 1000) times its share of the answer, when
 * the server told the length; never moves back. */
struct dx { /* one download attempt (the write callback's and the transfer-info callback's data) */
    net_req_t *req; /* the request while it runs */
    char *buf; /* PN_DL_BUF bytes waiting for their chunk write */
    int slot; /* the queue slot this download runs in (its state says pause and drop) */
    int halted; /* a callback of this attempt stopped the transfer on the page's say (a pause may be taken back after it: the transfer stays stopped) */
    unsigned used, have, base, seen,
        bad; /* have: bytes of the episode got (on the card and in buf); base: where this request's data starts; bad: the PN_* the callbacks refused with */
    int misfit; /* the answer to a Range is another part of the file than the one asked for */
    net_head_t head; /* the response's status, strong ETag and Content-Range (patch/netfile.h) */
    char etag
        [128]; /* the strong ETag of the file the bytes of this run came from ("" when the server gave none): the next attempt's If-Range */
    char part[PN_PATH];
    char dir[PN_PATH];
    char err[160];
};

/* ---- The life of a download: every move of a slot's state, in one table and under one mutex. */
static unsigned pn_dmutex[8] __attribute__((section(".scratch"), aligned(8)));

/* The state a slot in `state` has after `ev`, -1 when the event does not apply to it (nothing moves). */
static int pn_q_after(unsigned state, int ev) {
    switch (ev) {
    case PN_EV_ADD:
        return state == PN_Q_FREE ? PN_Q_WAIT : -1;
    case PN_EV_CLAIM:
        return state == PN_Q_WAIT ? PN_Q_ACTIVE : -1;
    case PN_EV_CANCEL: /* a waiting one leaves the queue; a running one is paused */
        return state == PN_Q_WAIT ? PN_Q_FREE : state == PN_Q_ACTIVE ? PN_Q_STOPPING : -1;
    case PN_EV_DROP: /* as a cancel, and a running or pausing one leaves nothing; a published one is a downloaded episode */
        return state == PN_Q_WAIT ? PN_Q_FREE : state == PN_Q_ACTIVE || state == PN_Q_STOPPING ? PN_Q_DROPPING : -1;
    case PN_EV_RESUME: /* a pause not yet taken is undone; a drop is not (its .part is gone) */
        return state == PN_Q_STOPPING ? PN_Q_ACTIVE : -1;
    case PN_EV_PUBLISH: /* (a pause that came with the last byte does not undo a whole file) */
        return state == PN_Q_ACTIVE || state == PN_Q_STOPPING ? PN_Q_PUBLISHED : -1;
    case PN_EV_END:
        return state == PN_Q_WAIT || state == PN_Q_FREE ? -1 : PN_Q_FREE;
    case PN_EV_HALT: /* the transfer was stopped for a pause the page has taken back since (RESUME): the episode waits again, and the thread goes on with it from the .part */
        return state == PN_Q_ACTIVE ? PN_Q_WAIT : state == PN_Q_STOPPING || state == PN_Q_DROPPING ? PN_Q_FREE : -1;
    }
    return -1;
}

/* ev on slot i, with pn_dmutex held: 1 when the state moved. */
static int pn_q_move(int i, int ev) {
    int next = pn_q_after(pn.q[i].state, ev);
    if (next < 0) return 0;
    pn.q[i].state = (unsigned)next;
    return 1;
}

/* ev on slot i: 1 when the state moved. */
static int pn_q_fire(int i, int ev) {
    int moved;
    pthread_mutex_lock(pn_dmutex);
    moved = pn_q_move(i, ev);
    pthread_mutex_unlock(pn_dmutex);
    return moved;
}

/* The running download of slot i is to stop (the page paused or dropped it); it is to leave nothing (dropped). */
static int pn_dl_stopped(int i) { return pn.q[i].state == PN_Q_STOPPING || pn.q[i].state == PN_Q_DROPPING; }
static int pn_dl_dropped(int i) { return pn.q[i].state == PN_Q_DROPPING; }

static int pn_xfer(void *user, long long dt, long long dn, long long ut, long long un) {
    unsigned t, n, p;
    (void)ut, (void)un;
    if (user) { /* a download: stop on the page's say; the length the server announced (what follows base) is the total */
        struct dx *d = user;
        if (pn_dl_stopped(d->slot)) return d->halted = 1;
        if (dt > 0 && dt <= (long long)PN_DL_MAX_BYTES) pn.dtotal = d->base + (unsigned)dt;
        return 0;
    }
    if (pn.cancel) return 1;
    if (dt > 0 && dn >= 0) {
        while (dt > 0xffffff) dt >>= 8, dn >>= 8;
        t = (unsigned)dt, n = (unsigned)dn;
        if (n > t) n = t;
        if (t) {
            p = pn.base + pn.span * n / t;
            if (p > pn.part) pn.part = p;
        }
    }
    return 0;
}

/* What every request of the worker asks, feed or picture, into r (patch/net.h runs it): an HTTP error fails it, pn_xfer is its progress and its Cancel (xdata 0: a job's request; the
 * attempt of a download otherwise), a stall is under 1000 bytes a second for 30 s, 16 redirect hops (tracking chains reach 8: podtrac, Art19 through 4 counters), 20 s to connect and
 * 120 s in all. The caller changes what its own request needs, then net_perform; a result of NET_NOHANDLE is PN_MEM. */
static void pn_req(net_req_t *r, const char *url, net_write_fn write_cb, void *user, char *err, void *xdata) {
    memset(r, 0, sizeof *r);
    r->url = url, r->write = write_cb, r->wdata = user, r->err = err;
    r->xfer = pn_xfer, r->xdata = xdata;
    r->flags = NET_FAIL;
    r->low_limit = 1000, r->low_time = 30;
    r->redirs = 16, r->connect_s = 20, r->total_s = 120;
}

/* The PN_* code of a finished libcurl request that did not succeed (rc != 0), from curl's result and the HTTP code. */
static int pn_rc(int rc, long http) {
    if (rc == CURLE_HTTP_RETURNED_ERROR) return http == 404 || http == 410 ? PN_GONE : PN_HTTP;
    if (rc == CURLE_ABORTED_BY_CALLBACK) return PN_CANCELLED;
    if (net_tls(rc)) return net_tls(rc) == 2 ? PN_NOCERT : PN_CERT;
    return PN_NET;
}

#define PN_NOTMOD \
    100 /* pn_fetch: HTTP 304, the feed is as the last refresh left it (not an error, not a PN_ code of the page) */

/* The feed at url through the parser. since: the server's own Last-Modified of the copy we hold (.show's modified=, never the device clock), 0 for no condition (If-Modified-Since). *modified: the
 * server's Last-Modified of this answer (CURLINFO_FILETIME), 0 when it sent none. Returns a PN_* code (PN_OK: the answer was a feed; PN_NOTMOD: 304). */
static int pn_fetch(const char *url, pf_parser_t *p, long since, unsigned *modified) {
    struct fx f;
    net_req_t r;
    long http;
    int rc;
    memset(&f, 0, sizeof f);
    f.p = p;
    *modified = 0;
    pn_req(&r, url, pn_write, &f, f.err, (void *)0);
    r.flags |= NET_FILETIME; /* the Last-Modified header, read back below */
    r.since = since;
    rc = net_perform(&r);
    if (rc == NET_NOHANDLE) return PN_MEM;
    http = r.http;
    if (r.filetime > 0) *modified = (unsigned)r.filetime;
    if (rc == 0 && http == 304 && since) return PN_NOTMOD;
    if (rc == 0) return pf_is_feed(p) ? PN_OK : PN_NOTFEED;
    if (rc == CURLE_WRITE_ERROR) return f.capped && pf_is_feed(p) && pf_items(p) > 0 ? PN_OK : PN_NOTFEED;
    return pn_rc(rc, http);
}

/* ---------------------------------------------------------------------------
 * The cover picture (docs/modules/podcasts.md "Cover art")
 */
/* The write callback of a request whose body is a file with a size limit (user: a net_file_t, patch/netfile.h): a byte over the limit or a failed write stops the transfer. */
static unsigned pn_fwrite(char *d, unsigned size, unsigned nmemb, void *user) {
    return net_file_write(user, d, size * nmemb);
}

/* The picture at url into the file path (a plain file, not yet a cover), at most cap bytes. 1 when the whole answer was written; else 0 and no file. */
static int pn_fetch_file(const char *url, const char *path, unsigned cap) {
    net_file_t c;
    char err[160];
    net_req_t r;
    int rc, ok;
    memset(&c, 0, sizeof c);
    c.fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    c.cap = cap;
    if (c.fd < 0) return 0;
    pn_req(&r, url, pn_fwrite, &c, err, (void *)0);
    rc = net_perform(&r);
    ok = close(c.fd) == 0 && rc == 0 && c.written > 0;
    if (!ok) unlink(path);
    return ok;
}

/* Whether the show folder has a picture the page would use (the names pc_cover_rank knows; the card is case-insensitive). */
static int pn_has_cover(const char *dir) {
    static const char *const names[] = {"cover.jpg",  "cover.png",  "cover.jpeg",
                                        "folder.jpg", "folder.png", "folder.jpeg"};
    char file[PN_PATH];
    unsigned i;
    for (i = 0; i < sizeof names / sizeof *names; ++i)
        if (pn_join(file, sizeof file, dir, names[i], (const char *)0) && !access(file, F_OK)) return 1;
    return 0;
}

/* The show's cover when its folder has none: the picture at url (the channel image the feed named), downloaded to a hidden file, a JPEG shrunk by pv_shrink (a PNG by pv_shrink_png) to a hidden temp file and
 * renamed to cover.jpg (the page never sees a half file); only an interlaced PNG the page can decode as it is is renamed to cover.png. Whatever fails leaves nothing
 * behind and changes nothing else: the feed's status is its own, the next refresh tries again. */
static void pn_cover(const char *dir, const char *url) {
    char src[PN_PATH], tmp[PN_PATH], dst[PN_PATH];
    unsigned w, h, sof;
    int kind, ok = 0;
    if (!pn_starts(url, "http://") && !pn_starts(url, "https://")) return;
    if (pn_has_cover(dir)) return;
    pn.base = 900, pn.span = 100;
    if (!pn_join(src, sizeof src, dir, ".cover.src", (const char *)0) ||
        !pn_join(tmp, sizeof tmp, dir, ".cover.tmp", (const char *)0))
        return;
    if (!pn_fetch_file(url, src, PN_COVER_CAP)) return;
    kind = pc_pic_info(src, &w, &h, &sof);
    if (kind == 1) {
        ok = pn_join(dst, sizeof dst, dir, "cover.jpg", (const char *)0) && pv_shrink(src, tmp) && !rename(tmp, dst);
        unlink(tmp);
    } else if (kind == 2) {
        int r = pv_shrink_png(src, tmp);
        if (r > 0)
            ok = pn_join(dst, sizeof dst, dir, "cover.jpg", (const char *)0) && !rename(tmp, dst);
        else if (r < 0)
            ok = pc_cover_ok(src) && pn_join(dst, sizeof dst, dir, "cover.png", (const char *)0) &&
                 !rename(src, dst); /* interlaced: only a small one, as it is */
        unlink(tmp);
    }
    unlink(src);
    if (ok) pn_bump();
}

/* The show's .notes (the kept items' long descriptions, docs/modules/podcasts.md "The notes file"), written before .episodes so that a new .episodes has its notes; a failure is not the refresh's (the page falls back to x=). */
static void pn_notes(const char *dir, const pf_parser_t *p) {
    char file[PN_PATH], tmp[PN_PATH];
    if (pn_join(file, sizeof file, dir, ".notes", (const char *)0) &&
        pn_join(tmp, sizeof tmp, dir, ".notes.tmp", (const char *)0))
        pno_save(file, tmp, (const struct pf_parser *)p);
}

/* The refresh's part of a show's .archive (docs/modules/podcasts.md "All episodes"): the items of the refreshed .episodes text (eps, n bytes) that the archive lacks are merged into it, newest first, at most PC_ARCH_MAX
 * lines and PC_ARCH_BYTES bytes (the oldest are dropped), through .archive.tmp and m1_commit. A show with no archive gets none; a failure of any kind leaves the archive as it was and is nobody's status. */
struct pn_am {
    int fd, fail;
    unsigned used;
    const char *tmp;
    char buf[PN_ARCH_BUF];
};

static int pn_am_flush(struct pn_am *w) {
    if (w->used && !m1_write_all(w->fd, w->buf, w->used)) w->fail = 1;
    w->used = 0;
    return !w->fail;
}

/* The merge's writer: the temp file is made at the first line (a refresh with nothing to add touches no file). */
static int pn_am_put(void *ctx, const char *data, unsigned n) {
    struct pn_am *w = ctx;
    if (w->fail) return 0;
    if (w->fd < 0 && (w->fd = open(w->tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644)) < 0) return w->fail = 1, 0;
    if (w->used + n > sizeof w->buf && !pn_am_flush(w)) return 0;
    memcpy(w->buf + w->used, data, n);
    w->used += n;
    return 1;
}

static void pn_arch_merge(const char *dir, const char *eps, unsigned n) {
    char file[PN_PATH], tmp[PN_PATH], *old;
    struct pn_am *w;
    unsigned oldn = 0;
    int r;
    if (!m1_card_mounted() || !pn_join(file, sizeof file, dir, ".archive", (const char *)0) || access(file, F_OK) ||
        !pn_join(tmp, sizeof tmp, dir, ".archive.tmp", (const char *)0))
        return;
    old = m1_read_file(file, PC_ARCH_BYTES, &oldn);
    w = old ? calloc(1, sizeof *w) : (struct pn_am *)0;
    if (!w) {
        free(old);
        return;
    }
    w->fd = -1, w->tmp = tmp;
    r = pc_archive_merge(eps, n, old, oldn, pn_am_put, w, PC_ARCH_MAX, PC_ARCH_BYTES);
    if (w->fd >= 0) m1_commit(w->fd, r > 0 && pn_am_flush(w) && m1_card_mounted(), tmp, file);
    free(w);
    free(old);
}

/* ---------------------------------------------------------------------------
 * One show
 */
static void pn_refresh_one(const struct pn_job *j, const char *dir) {
    char path[PN_PATH], file[PN_PATH], tmp[PN_PATH];
    pc_show_t s;
    pf_parser_t *p;
    char *buf, *old = (char *)0, *eps, shown[PC_TITLE];
    unsigned n, oldn = 0, fresh = 0, feed, modified = 0;
    int code, first;
    if (!pn_join(path, sizeof path, j->root, dir, (const char *)0) ||
        !pn_join(file, sizeof file, path, ".show", (const char *)0))
        return;
    memset(&s, 0, sizeof s);
    buf = m1_read_file(file, PN_SHOW_MAX, &n);
    if (!buf) return;
    pc_parse_show(buf, n, &s);
    free(buf);
    if (!s.feed[0]) return;
    feed = pc_hash(s.feed);
    pn.cur = feed;
    pn.part = 0, pn.base = 0, pn.span = 900; /* the feed is nine tenths of the show, its picture the last tenth */
    pn_bump();
    p = pf_new();
    if (!p) {
        pn_set(feed, PN_MEM, 0);
        pn.cur = 0;
        return;
    }
    /* the condition only while the local copy is whole: a show with no .episodes would answer 304 and stay empty */
    pn_join(file, sizeof file, path, ".episodes", (const char *)0);
    code = pn_fetch(s.feed, p, access(file, F_OK) ? 0 : (long)s.modified, &modified);
    if (code == PN_NOTMOD &&
        access(file,
               F_OK)) { /* a 304 with nothing to keep (the file went in the meantime): once more, unconditionally */
        pf_free(p);
        p = pf_new();
        if (!p) {
            pn_set(feed, PN_MEM, 0);
            pn.cur = 0;
            return;
        }
        code = pn_fetch(s.feed, p, 0, &modified);
    }
    if (code ==
        PN_CANCELLED) { /* Cancel: the transfer was aborted, nothing written, the show keeps the status it had */
        pf_free(p);
        pn.cur = 0;
        return;
    }
    if (code ==
        PN_NOTMOD) { /* 304: .episodes stays as it is, only the time of the check moves; a missing cover is still fetched */
        char *txt = calloc(PN_SHOW_MAX + 1, 1);
        code = PN_OK;
        if (!txt)
            code = PN_MEM;
        else {
            n = pf_render_show(s.title, s.feed, s.image, (unsigned)time((long *)0), s.modified, s.author, s.category,
                               s.desc, txt, PN_SHOW_MAX); /* modified= stays: it is the server's, of the copy we hold */
            pn_join(file, sizeof file, path, ".show", (const char *)0);
            pn_join(tmp, sizeof tmp, path, ".show.tmp", (const char *)0);
            if (!m1_save(file, tmp, 0644, txt, n))
                code = PN_STORAGE;
            else {
                if (pn.part < 900) pn.part = 900;
                pn_cover(path, s.image);
            }
            free(txt);
        }
        pf_free(p);
        pn_set(feed, code, 0);
        pn.cur = 0;
        return;
    }
    if (code == PN_OK) {
        eps = calloc(PN_EPS_MAX + 1, 1);
        if (!eps)
            code = PN_MEM;
        else {
            pn_join(file, sizeof file, path, ".episodes", (const char *)0);
            old = m1_read_file(file, PN_EPS_MAX, &oldn);
            n = pf_render_episodes(p, path, old, oldn, eps, PN_EPS_MAX, &fresh);
            first = s.checked == 0;
            pn_notes(path, p);
            pn_join(tmp, sizeof tmp, path, ".episodes.tmp", (const char *)0);
            if (!m1_save(file, tmp, 0644, eps, n))
                code = PN_STORAGE;
            else {
                pn_arch_merge(
                    path, eps,
                    n); /* (the archive, when the show has one, gets the items it lacks; the refresh does not depend on it) */
                /* the show file: the feed's title the first time (the import wrote the host), its picture url; the time of this refresh */
                pn_join(file, sizeof file, path, ".show", (const char *)0);
                pn_join(tmp, sizeof tmp, path, ".show.tmp", (const char *)0);
                memcpy(shown, first && pf_title(p)[0] ? pf_title(p) : s.title, PC_TITLE);
                n = pf_render_show(
                    shown, s.feed, pf_image(p)[0] ? pf_image(p) : s.image, (unsigned)time((long *)0),
                    modified, /* the new answer's Last-Modified; 0 (none sent) drops the key: the next request is unconditional */
                    pf_author(p)[0] ? pf_author(p) : s.author, pf_category(p)[0] ? pf_category(p) : s.category,
                    pf_summary(p)[0] ? pf_summary(p) : s.desc, eps, PN_EPS_MAX);
                if (!m1_save(file, tmp, 0644, eps, n))
                    code = PN_STORAGE;
                else {
                    if (pn.part < 900) pn.part = 900;
                    if (first &&
                        !old) { /* nothing of the folder is anyone's yet: it takes the show's name instead of the import's */
                        char name[PC_FILE], to[PN_PATH];
                        pf_folder_name(name, sizeof name, shown);
                        if (name[0] && strcmp(name, dir) && pn_join(to, sizeof to, j->root, name, (const char *)0) &&
                            access(to, F_OK) && !rename(path, to))
                            pn_join(path, sizeof path, to, (const char *)0, (const char *)0);
                    }
                    pn_cover(
                        path,
                        pf_image(p)[0]
                            ? pf_image(p)
                            : s.image); /* the feed is done: its picture, when the folder has none; its result is nobody's status */
                }
            }
            free(eps);
            free(old);
        }
    }
    pf_free(p);
    pn_set(feed, code, code == PN_OK ? fresh : 0);
    pn.cur = 0;
}

static void *pn_main(void *arg) {
    struct pn_job *j = arg;
    int i;
    for (i = 0; i < j->n && !pn.cancel; ++i) {
        pn_refresh_one(j, j->dirs[i]);
        pn.done = i + 1;
        pn_bump();
    }
    free(j);
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

int pn_refresh(const char *root, const pc_show_t *shows, const int *idx, int n) {
    struct pn_job *j;
    unsigned long th = 0;
    int i, g = pn_guard();
    if (pn.busy) return PN_BUSY;
    if (g) return g;
    j = calloc(1, sizeof *j);
    if (!j) return PN_MEM;
    for (i = 0; i < n && j->n < PC_MAX_SHOWS; ++i) {
        const pc_show_t *s = &shows[idx[i]];
        if (!s->feed[0]) continue;
        memcpy(j->dirs[j->n++], s->dir, PC_FILE);
    }
    if (!j->n) {
        free(j);
        return PN_OK;
    }
    pn_join(j->root, sizeof j->root, root, (const char *)0, (const char *)0);
    net_init(); /* (on the UI thread) */
    pn.busy = 1, pn.kind = PN_KIND_REFRESH, pn.done = 0, pn.total = j->n;
    pn.cancel = pn.stopped = 0, pn.ok = pn.fail = pn.part = 0;
    pn_bump();
    if (pthread_create(&th, (const void *)0, pn_main, j)) {
        pn.kind = 0;
        pn.busy = 0;
        pn_bump();
        free(j);
        return PN_MEM;
    }
    pthread_detach(th);
    return PN_OK;
}

/* ---------------------------------------------------------------------------
 * Downloads (docs/modules/podcasts.md "Downloads")
 *
 * The policy follows q2-podcasts (MIT licence, github.com/m-d-e-v/q2-podcasts: internal/library/download.go and contrib/shanlingq2/README): one episode at a time; the data is gathered
 * in 512 KB chunks and each chunk is written with open, write, fsync, close, so the card is rarely held busy; a break resumes with an HTTP Range request (a 200 answer starts the file
 * again); 60 s without a byte is a stall; a network failure is retried after 10, 20 and 40 s, while a 404, a web page instead of audio and a full card fail at once; the card keeps
 * 32 MB free (checked before the download and before every chunk); the finished file is renamed into the show folder. The code is our own, over demo's libcurl.
 */
static void pn_folder(const char *url, char *out, unsigned size, char *host, unsigned hsize);
static int pn_cat(char *out, unsigned size, const char *s) {
    unsigned o = strlen(out), k;
    for (k = 0; s[k]; ++k) {
        if (o + 1 >= size) return 0;
        out[o++] = s[k];
    }
    out[o] = 0;
    return 1;
}

unsigned pn_dl_key(const char *dir, const char *file) {
    char path[PC_FILE * 2 + 2];
    if (!pn_join(path, sizeof path, dir, file, (const char *)0)) return 0;
    return pc_hash(path);
}

static void pn_fail_set(unsigned key, int code, const char *dir, const char *file) {
    unsigned i;
    for (i = 0; i < PN_FAILS; ++i)
        if (pn.fails[i].key == key) break;
    if (i == PN_FAILS) i = pn.nfail++ % PN_FAILS;
    pn.fails[i].key = 0; /* (not a half record while the page reads) */
    memcpy(pn.fails[i].dir, dir, strlen(dir) + 1);
    memcpy(pn.fails[i].file, file, strlen(file) + 1);
    pn.fails[i].code = code;
    __sync_synchronize();
    pn.fails[i].key = key;
}

static void pn_fail_clear(unsigned key) {
    unsigned i;
    for (i = 0; i < PN_FAILS; ++i)
        if (pn.fails[i].key == key) pn.fails[i].key = 0;
}

/* The queued download that came first (the lowest sequence number), -1 for none. */
static int pn_next_slot(void) {
    int i, best = -1;
    for (i = 0; i < PN_QMAX; ++i)
        if (pn.q[i].state == PN_Q_WAIT && (best < 0 || (int)(pn.q[i].seq - pn.q[best].seq) < 0)) best = i;
    return best;
}

/* The thread takes the next waiting download up (PN_EV_CLAIM): the slot is chosen, its key read and its state made running in one hold of pn_dmutex, the one the page fills a slot and stops a download under
 * (pn_dl_add, pn_dl_stop). So the key is the key of the names the slot holds: a slot the page emptied and filled with another episode while the thread waited is taken up as that episode, and a cancel or a drop
 * sees a download waiting or running, never between. The slot's index, -1 for none. */
static int pn_claim(unsigned *key) {
    int i;
    pthread_mutex_lock(pn_dmutex);
    i = pn_next_slot();
    if (i >= 0) {
        *key = pn.q[i].key;
        pn_q_move(i, PN_EV_CLAIM);
    }
    pthread_mutex_unlock(pn_dmutex);
    return i;
}

/* Another step of progress for the page (a percent, or a MB when the length is not known): the generation moves. */
static void pn_dl_step(void) {
    unsigned t = pn.dtotal, g = pn.dgot, s;
    s = t > g ? (g >> 10) * 100 / ((t >> 10) ? (t >> 10) : 1) : 1000 + (g >> 20);
    if (s == pn.dstep) return;
    pn.dstep = s;
    __sync_synchronize();
    ++pn.dgen;
}

/* The gathered bytes into the .part file as a chunk of their own (open for append, write, fsync, close), the card keeping its margin. 1 on success, else 0 and d->bad. */
static int pn_dflush(struct dx *d) {
    int fd, ok;
    if (!d->used) return 1;
    fd = net_room(d->dir, d->used >> 10);
    if (fd) return d->bad = fd == NET_W_SPACE ? PN_CARDFULL : PN_STORAGE, 0;
    fd = open(d->part, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) return d->bad = PN_STORAGE, 0;
    ok = m1_write_all(fd, d->buf, d->used) && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (!ok) return d->bad = PN_STORAGE, 0;
    d->used = 0;
    return 1;
}

static unsigned pn_dwrite(char *data, unsigned size, unsigned nmemb, void *user) {
    struct dx *d = user;
    unsigned len = size * nmemb, at = 0;
    if (pn_dl_stopped(d->slot))
        return d->halted = 1,
               0; /* (before anything is written or made; a write error ends the transfer, the caller knows why) */
    if (!d->seen) { /* the first bytes: the headers are in */
        long code = net_status(d->req);
        d->seen = 1;
        if (net_text_type(net_type(d->req))) return d->bad = PN_NOTAUDIO, 0; /* a page, an error document */
        if (d->base && code == 206 && d->head.range_seen && d->head.range_start != (long long)d->base)
            return d->misfit = 1, 0; /* another part of the file than the one asked for: nothing is appended */
        memcpy(d->etag, d->head.etag, sizeof d->etag);
        if (d->base && code != 206) { /* the server ignored the Range: the file starts again */
            int fd = open(d->part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd < 0 || close(fd)) return d->bad = PN_STORAGE, 0;
            d->base = d->have = 0;
        }
    }
    if (len > PN_DL_MAX_BYTES - d->have) return d->bad = PN_HTTP, 0;
    while (at < len) {
        unsigned n = len - at;
        if (n > PN_DL_BUF - d->used) n = PN_DL_BUF - d->used;
        memcpy(d->buf + d->used, data + at, n);
        d->used += n, at += n;
        if (d->used == PN_DL_BUF && !pn_dflush(d)) return 0;
    }
    d->have += len;
    pn.dgot = d->have;
    pn_dl_step();
    return len;
}

/* The header callback of a download: the shared reader keeps the status, the strong ETag and the Content-Range for pn_dwrite. */
static unsigned pn_dhead(char *line, unsigned size, unsigned nmemb, void *user) {
    net_head_line(&((struct dx *)user)->head, line, size * nmemb);
    return size * nmemb;
}

/* One request for the rest of the episode (a Range from the bytes the file has; If-Range when this run knows the file's strong ETag). Returns PN_OK (the whole answer arrived), PN_CANCELLED (the page's say), or the failure; *retry: worth trying
 * again after a wait (the network, a 5xx); *again: the server refused the range (416, a range error): the file may start again, once. The bytes got are on the card when this returns. */
static int pn_dl_attempt(struct dx *d, const char *url, int *retry, int *again) {
    net_req_t r;
    char range[16], if_range[144];
    void *if_range_list[2];
    long http;
    int rc;
    d->seen = d->bad = 0, d->base = d->have, d->used = 0;
    d->misfit = d->halted = 0;
    memset(&d->head, 0, sizeof d->head);
    pn_req(&r, url, pn_dwrite, d, d->err, d);
    r.low_limit = 1, r.low_time = PN_DL_STALL; /* a stall: under 1 byte a second for PN_DL_STALL seconds */
    r.total_s = 0; /* no limit on the whole transfer */
    r.flags |= NET_IDENTITY; /* audio is sent as it is: a range of an encoded body would not resume */
    if (d->have) {
        pc_fmt(range, sizeof range, "%d-", d->have);
        r.range = range;
        /* the bytes of an attempt of this run came with a strong ETag: the rest is asked of that same file, and a server whose file changed sends it whole (a 200: the file starts again) */
        if (net_if_range(if_range, sizeof if_range, if_range_list, d->etag)) r.headers = if_range_list;
    }
    r.header = pn_dhead, r.hdata = d;
    d->req = &r;
    rc = net_perform(&r);
    d->req = (net_req_t *)0;
    if (rc == NET_NOHANDLE) return PN_MEM;
    http = r.http;
    if (pn_dl_dropped(d->slot))
        return PN_CANCELLED; /* the page took the .part away: the bytes held are not a file's start */
    if (!d->bad)
        pn_dflush(d); /* what arrived goes to the card whatever ended the transfer: the next attempt resumes after it */
    if (d->bad) return d->bad;
    if (d->misfit) return *again = 1, PN_HTTP; /* (as a refused range: from the start, once) */
    if (rc == 0) return d->have ? PN_OK : PN_HTTP; /* an empty answer is no episode */
    if (d->halted || pn_dl_stopped(d->slot))
        return PN_CANCELLED; /* (halted: stopped for a pause, even one taken back since; not a failure of the network to wait after) */
    if (rc == CURLE_HTTP_RETURNED_ERROR) {
        if (http == 404 || http == 410) return PN_GONE;
        if (http == 416) *again = 1;
        if (net_http_passing(http)) *retry = 1;
        return PN_HTTP;
    }
    if (rc == CURLE_RANGE_ERROR) return *again = 1, PN_HTTP;
    if (net_tls(rc)) return net_tls(rc) == 2 ? PN_NOCERT : PN_CERT;
    return *retry = 1, PN_NET;
}

/* The bytes the .part file has (it is made when missing: the next chunk appends to it); 0 when it cannot be opened. */
static int pn_part_size(const char *part, unsigned *size) {
    int fd = open(part, O_WRONLY | O_CREAT | O_APPEND, 0644);
    long off;
    if (fd < 0) return 0;
    off = lseek(fd, 0, 2);
    close(fd);
    if (off < 0 || (unsigned long)off > PN_DL_MAX_BYTES) return 0;
    *size = (unsigned)off;
    return 1;
}

/* The enclosure url and length of the episode whose file is name: from the show's .episodes, else (an episode of the feed's archive) from its .archive. 1 when found. dir: the show folder's path. */
static int pn_find_url(const char *dir, const char *name, char *url, unsigned usize, unsigned *length) {
    static const char *const files[2] = {".episodes", ".archive"};
    static const unsigned caps[2] = {PN_EPS_MAX, PC_ARCH_BYTES};
    char path[PN_PATH];
    int k, found = 0;
    for (k = 0; k < 2 && !found; ++k) {
        unsigned n = 0;
        char *buf =
            pn_join(path, sizeof path, dir, files[k], (const char *)0) ? m1_read_file(path, caps[k], &n) : (char *)0;
        found = buf && pf_find_episode(buf, n, name, url, usize, length);
        free(buf);
    }
    return found;
}

/* The slot's episode, to the end: PN_OK when the file is in place, PN_CANCELLED for the page's say, else the failure. */
static int pn_dl_run(struct dx *d, const char *show, const char *name, int slot) {
    char file[PN_PATH], url[PF_URL];
    unsigned n, length = 0, tries = 0, start, i;
    int code, retry, again, restarted = 0;
    d->etag[0] = 0;
    if (!pn_join(d->dir, sizeof d->dir, pn.droot, show, (const char *)0) ||
        !pn_join(file, sizeof file, d->dir, name, (const char *)0) || strlen(file) + sizeof(".part") > PN_DL_PATH_MAX)
        return PN_STORAGE;
    memcpy(d->part, file, strlen(file) + 1);
    pn_cat(d->part, sizeof d->part, ".part");
    d->slot = slot;
    if (!access(file, F_OK)) { /* it is on the card already: nothing to fetch, a leftover .part goes */
        unlink(d->part);
        return PN_OK;
    }
    i = pn_find_url(d->dir, name, url, sizeof url, &length);
    if (!i || !(pn_starts(url, "http://") || pn_starts(url, "https://")))
        return PN_GONE; /* the entry is gone, or has no address */
    d->buf = calloc(PN_DL_BUF, 1);
    if (!d->buf) return PN_MEM;
    for (;;) {
        if (!pn_part_size(d->part, &start)) {
            code = PN_STORAGE;
            break;
        }
        d->have = start;
        pn.dgot = start, pn.dtotal = length, pn.dwait = 0, pn.dstep = ~0u;
        pn_dl_step();
        code = net_room(d->dir, length > start ? (length - start) >> 10 : 0);
        if (code == NET_W_CARD) {
            code = PN_STORAGE;
            break;
        }
        if (code && length > start) { /* the rest of the file would eat into the reserve */
            code = PN_CARDFULL;
            break;
        }
        retry = again = 0;
        code = pn_dl_attempt(d, url, &retry, &again);
        if (code == PN_OK) {
            pthread_mutex_lock(
                pn_dmutex); /* the rename and PN_EV_PUBLISH in one hold: a drop comes before both or after both */
            if (pn_q_after(pn.q[slot].state, PN_EV_PUBLISH) < 0)
                code = PN_CANCELLED; /* dropped before the file was in place: it never is */
            else if (rename(d->part, file))
                code = PN_STORAGE;
            else
                pn_q_move(slot, PN_EV_PUBLISH); /* from here it is a downloaded episode: a drop no longer touches it */
            pthread_mutex_unlock(pn_dmutex);
            if (code == PN_OK) net_sync_dir(d->dir); /* (a folder that could not be synced does not fail the file) */
            break;
        }
        if (code == PN_CANCELLED) break;
        if (again && !restarted) { /* the range was refused: from the start, once */
            restarted = 1;
            unlink(d->part);
            continue;
        }
        if (!retry) break;
        if (d->have > start) tries = 0; /* it went on a while before it broke: the count starts again */
        if (tries >= PN_DL_RETRIES) break;
        n = 10u << tries++;
        pn.dwait = 1;
        pn_bump();
        for (i = 0; i < n && !pn_dl_stopped(slot); ++i) sleep(1);
        pn.dwait = 0;
        if (pn_dl_stopped(slot)) {
            code = PN_CANCELLED;
            break;
        }
    }
    if (pn_dl_dropped(
            slot)) { /* dropped (so the file was not put in place): nothing of this run stays, and no failure is kept */
        unlink(d->part);
        code = PN_CANCELLED;
    } else if (code != PN_OK && (!pn_part_size(d->part, &start) || !start))
        unlink(d->part); /* nothing on the card: no file to say "Paused" */
    free(d->buf);
    return code;
}

/* The worker: the queued downloads in the order they were asked, one at a time, until none is left. It runs beside a job's thread (a refresh, a search, ...): the two share no field but the
 * generation counter. A download queued while the thread was ending is seen by the last look below (the page's pn_dl_start found the thread still there), so none is left waiting. */
static void *pn_dmain(void *arg) {
    unsigned key = 0;
    int i;
    (void)arg;
    do {
        while ((i = pn_claim(&key)) >= 0) {
            struct dx *d;
            int code;
            pn.dkey = key, pn.dgot = pn.dtotal = 0, pn.dwait = 0;
            pn_bump();
            d = calloc(1, sizeof *d);
            code = d ? pn_dl_run(d, pn.q[i].dir, pn.q[i].file, i) : PN_MEM;
            free(d);
            if (code != PN_OK && code != PN_CANCELLED) pn_fail_set(key, code, pn.q[i].dir, pn.q[i].file);
            /* (the pause or the drop ends with the slot: nothing is left for the key's next download. A run stopped for a pause that was taken back before this hold waits again: the next look takes it up) */
            pn_q_fire(i, code == PN_CANCELLED ? PN_EV_HALT : PN_EV_END);
            pn.dkey = 0;
            pn_bump();
        }
        pn.dbusy = 0;
        __sync_synchronize();
    } while (pn_next_slot() >= 0 && __sync_bool_compare_and_swap(&pn.dbusy, 0, 1));
    pn_bump();
    return (void *)0;
}

int pn_dl_start(void) {
    unsigned long th = 0;
    int g, i;
    if (pn.dbusy || pn_next_slot() < 0) return PN_OK; /* the thread is on it, or nothing waits */
    g = pn_guard();
    if (g) { /* the downloads cannot start: they fail now, with the words of the guard on their rows */
        pthread_mutex_lock(pn_dmutex); /* (an ending thread that took the queue up again takes none of these) */
        for (i = 0; i < PN_QMAX; ++i)
            if (pn.q[i].state == PN_Q_WAIT) {
                pn_q_move(i, PN_EV_CANCEL);
                pn_fail_set(pn.q[i].key, g, pn.q[i].dir, pn.q[i].file);
            }
        pthread_mutex_unlock(pn_dmutex);
        pn_bump();
        return g;
    }
    net_init();
    if (!__sync_bool_compare_and_swap(&pn.dbusy, 0, 1)) return PN_OK; /* (the ending thread took the queue up again) */
    pn_bump();
    if (pthread_create(&th, (const void *)0, pn_dmain, (void *)0)) {
        pn.dbusy = 0;
        pn_bump();
        return PN_MEM;
    }
    pthread_detach(th);
    return PN_OK;
}

int pn_dl_add(const char *root, const char *dir, const char *file) {
    unsigned key = pn_dl_key(dir, file), i;
    int free_slot = -1, there = 0, g;
    char path[PN_PATH];
    if (!key || !file[0] || !pn_join(path, sizeof path, root, dir, file) ||
        strlen(path) + sizeof(".part") > PN_DL_PATH_MAX)
        return PN_STORAGE;
    g = pn_guard(); /* (asked before the mutex is taken; it counts only for a new entry) */
    /* The look for the episode in the queue, the resume of one being paused and the new entry are one hold of the mutex: a download that ends while the page waits for it is seen ended, and the episode is
     * queued as a new one (not taken for one that is still there). The thread takes a slot up under the same mutex, so it never reads one half filled. */
    pthread_mutex_lock(pn_dmutex);
    for (i = 0; i < PN_QMAX; ++i) {
        if (pn.q[i].state == PN_Q_FREE) {
            if (free_slot < 0) free_slot = (int)i;
            continue;
        }
        if (pn.q[i].key != key) continue;
        if (pn.q[i].state == PN_Q_DROPPING)
            continue; /* being dropped (its .part is gone, it cannot go on): the episode is queued afresh behind it */
        pn_q_move(
            (int)i,
            PN_EV_RESUME); /* asked again before the pause ended the slot: it goes on (the transfer itself, or after HALT a new one from the .part) */
        there = 1;
    }
    if (!there && !g && free_slot >= 0) {
        pn_fail_clear(key);
        if (strcmp(pn.droot, root)) pn_join(pn.droot, sizeof pn.droot, root, (const char *)0, (const char *)0);
        memcpy(pn.q[free_slot].dir, dir, strlen(dir) + 1);
        memcpy(pn.q[free_slot].file, file, strlen(file) + 1);
        pn.q[free_slot].key = key;
        pn.q[free_slot].seq = ++pn.dseq;
        pn_q_move(free_slot, PN_EV_ADD);
    }
    pthread_mutex_unlock(pn_dmutex);
    if (there) return PN_OK;
    if (g) return g;
    if (free_slot < 0) return PN_QFULL;
    pn_bump();
    return pn_dl_start();
}

/* The page stops the downloads of key, all under pn_dmutex, which the thread holds when it takes a waiting one up: each is seen either waiting (it leaves the queue and is never started) or running (it is
 * flagged: the cancel, and for a drop of one whose file is not in place the drop), never in between. */
static void pn_dl_stop(unsigned key, int drop) {
    int i, freed = 0;
    pthread_mutex_lock(pn_dmutex);
    for (i = 0; i < PN_QMAX; ++i) {
        if (pn.q[i].key != key) continue;
        freed |= pn.q[i].state == PN_Q_WAIT;
        pn_q_move(i, drop ? PN_EV_DROP : PN_EV_CANCEL);
    }
    pthread_mutex_unlock(pn_dmutex);
    if (freed) pn_bump();
}

void pn_dl_cancel(unsigned key) { pn_dl_stop(key, 0); }

void pn_dl_drop(unsigned key) { pn_dl_stop(key, 1); }

int pn_dl_running(void) { return pn.dbusy; }

int pn_dl_count(void) {
    int i, n = 0;
    for (i = 0; i < PN_QMAX; ++i) n += pn.q[i].state != PN_Q_FREE;
    return n;
}

int pn_dl_waiting(void) {
    int i, n = 0;
    for (i = 0; i < PN_QMAX; ++i) n += pn.q[i].state == PN_Q_WAIT;
    return n;
}

unsigned pn_dl_gen(void) { return pn.dgen; }

int pn_dl_state(unsigned key, int *code, unsigned *got, unsigned *total) {
    int i;
    unsigned g, t;
    for (i = 0; i < PN_QMAX; ++i)
        if (pn.q[i].state != PN_Q_FREE && pn.q[i].key == key) {
            if (pn.q[i].state == PN_Q_DROPPING) continue; /* being dropped: not this episode's state any more */
            if (pn.q[i].state == PN_Q_WAIT || pn.dwait) return PN_DL_WAIT;
            if (pn.q[i].state == PN_Q_STOPPING) return PN_DL_NONE; /* paused: the worker is about to let it go */
            g = pn.dgot, t = pn.dtotal;
            *got = g, *total = t < g ? 0 : t; /* a length that is too small was wrong: unknown */
            return PN_DL_ACTIVE;
        }
    for (i = 0; i < PN_FAILS; ++i)
        if (pn.fails[i].key == key) {
            *code = pn.fails[i].code;
            return PN_DL_FAILED;
        }
    return PN_DL_NONE;
}

unsigned pn_dl_current(unsigned *got, unsigned *total) {
    unsigned key = pn.dkey;
    int code;
    return key && pn_dl_state(key, &code, got, total) == PN_DL_ACTIVE ? key : 0;
}

void pn_dl_clear(unsigned key) {
    pn_fail_clear(key);
    pn_bump();
}

unsigned pn_dl_listed(int n, char *dir, char *file, int *code) {
    unsigned last = 0;
    int have = 0, i, k;
    for (k = 0;; ++k) { /* the queue in the order it was asked: the lowest sequence number after the last one given */
        int best = -1;
        for (i = 0; i < PN_QMAX; ++i)
            if (pn.q[i].state != PN_Q_FREE && (!have || (int)(pn.q[i].seq - last) > 0) &&
                (best < 0 || (int)(pn.q[i].seq - pn.q[best].seq) < 0))
                best = i;
        if (best < 0) break;
        if (k == n) {
            memcpy(dir, pn.q[best].dir, strlen(pn.q[best].dir) + 1);
            memcpy(file, pn.q[best].file, strlen(pn.q[best].file) + 1);
            *code = 0;
            return pn.q[best].key;
        }
        last = pn.q[best].seq, have = 1;
    }
    n -= k;
    for (i = 0; i < PN_FAILS; ++i) /* then the failed ones */
        if (pn.fails[i].key && n-- == 0) {
            memcpy(dir, pn.fails[i].dir, strlen(pn.fails[i].dir) + 1);
            memcpy(file, pn.fails[i].file, strlen(pn.fails[i].file) + 1);
            *code = pn.fails[i].code;
            return pn.fails[i].key;
        }
    return 0;
}

/* ---------------------------------------------------------------------------
 * Search (docs/modules/podcasts.md "Search")
 *
 * One worker job under the same rule as a refresh: one job thread at a time. The query (the store's JSON, at most PN_JSON_CAP bytes, taken apart by pj_results into pn.sres), then the
 * artwork of each result one by one into PN_SEARCH_DIR; or a preview: the lookup of an Apple Podcasts id when there is one, the feed through the push parser (held in pn.prev for the page), its
 * picture shrunk to PN_PREVIEW_COVER. The thread touches no widget; the page reads the record on its own timer.
 */
static int pn_ci(unsigned c) { return c >= 'A' && c <= 'Z' ? (int)(c + 32) : (int)c; }

/* s starts with the lower-case prefix, in any case. */
static int pn_starts_ci(const char *s, const char *prefix) {
    while (*prefix && pn_ci((unsigned char)*s) == *prefix) ++s, ++prefix;
    return !*prefix;
}

int pn_classify(const char *text, char *id, unsigned size) {
    const char *h, *p;
    id[0] = 0;
    if (!pn_starts_ci(text, "http://") && !pn_starts_ci(text, "https://")) return 0;
    h = text;
    while (*h && *h != '/') ++h;
    while (*h == '/') ++h;
    for (p = h; *p && *p != '/' && *p != ':' && *p != '?' && *p != '#'; ++p)
        if (pn_starts_ci(p, "podcasts.apple.com") &&
            (p[18] == 0 || p[18] == '/' || p[18] == ':' || p[18] == '?' || p[18] == '#')) {
            const char *q;
            for (q = p + 18; *q; ++q)
                if (q[0] == '/' && pn_ci((unsigned char)q[1]) == 'i' && pn_ci((unsigned char)q[2]) == 'd' &&
                    q[3] >= '0' && q[3] <= '9') {
                    unsigned n = 0, nz = 0;
                    for (q += 3; *q >= '0' && *q <= '9'; ++q) {
                        if (n + 1 >= size) return id[0] = 0, 1; /* (more digits than any id the store has) */
                        id[n++] = *q;
                        nz |= *q != '0';
                    }
                    id[n] = 0;
                    if (!nz) return id[0] = 0, 1;
                    return 2;
                }
            return 1;
        }
    return 1;
}

/* The URL-encoded UTF-8 text s appended to out: the unreserved characters (letters, digits, - _ . ~) as they are, every other byte as %XX. 0 when it does not fit. */
static int pn_urlenc(char *out, unsigned size, const char *s) {
    unsigned n = m1_urlenc(out, size, strlen(out), s); /* (0 is also the whole answer for no text and no out) */
    if (!n && *s) return 0;
    out[n] = 0;
    return 1;
}

/* The state directory and the files in it. */
static void pn_search_dir(void) {
    mkdir("/mnt/mmc/.m1plus", 0755);
    mkdir("/mnt/mmc/.m1plus/podcasts", 0755);
    mkdir(PN_SEARCH_DIR, 0755);
}

static int pn_thumb_path(int i, const char *ext, char *out, unsigned size) {
    char name[24];
    pc_fmt(name, sizeof name, "/t%d.", (unsigned)i);
    out[0] = 0;
    return pn_cat(out, size, PN_SEARCH_DIR) && pn_cat(out, size, name) && pn_cat(out, size, ext);
}

void pn_search_clean(void) {
    char path[PN_PATH];
    int i;
    for (i = 0; i < PJ_MAX; ++i) {
        if (pn_thumb_path(i, "jpg", path, sizeof path)) unlink(path);
        if (pn_thumb_path(i, "png", path, sizeof path)) unlink(path);
        if (pn_thumb_path(i, "src", path, sizeof path)) unlink(path);
        if (pn_thumb_path(i, "tmp", path, sizeof path)) unlink(path);
        pn.sthumb[i] = pn.sext[i] = 0;
    }
    pn.sn = 0;
}

int pn_search_state(void) { return pn.sstate; }
int pn_search_code(void) { return pn.scode; }
unsigned pn_search_gen(void) { return pn.sgen; }
int pn_search_count(void) { return pn.sn; }
const pj_result_t *pn_search_result(int i) { return i >= 0 && i < pn.sn ? &pn.sres[i] : (const pj_result_t *)0; }

int pn_search_thumb(int i, char *path, unsigned size) {
    if (i < 0 || i >= PJ_MAX || pn.sthumb[i] != 1) return 0;
    return pn_thumb_path(i, pn.sext[i] == 2 ? "png" : "jpg", path, size);
}

struct jx { /* the answer of the store: the bytes so far, up to PN_JSON_CAP */
    char *buf;
    unsigned n;
    int capped;
    char err[160];
};

static unsigned pn_jwrite(char *d, unsigned size, unsigned nmemb, void *user) {
    struct jx *f = user;
    unsigned len = size * nmemb;
    if (len > PN_JSON_CAP - f->n) {
        memcpy(f->buf + f->n, d, PN_JSON_CAP - f->n);
        f->n = PN_JSON_CAP, f->capped = 1;
        return 0; /* a write error ends the transfer; what came is parsed */
    }
    memcpy(f->buf + f->n, d, len);
    f->n += len;
    return len;
}

/* The answer at url into buf (PN_JSON_CAP + 1 bytes), *got bytes of it. PN_OK also for one cut at the cap. A 404 or 410 is PN_GONE here (LRCLIB's "no such record"). */
static int pn_fetch_json_once(const char *url, char *buf, unsigned *got, long *http_out, int timeout) {
    struct jx f;
    net_req_t r;
    long http;
    int rc;
    memset(&f, 0, sizeof f);
    f.buf = buf;
    pn_req(&r, url, pn_jwrite, &f, f.err, (void *)0);
    if (timeout) r.total_s = timeout; /* (a chart that hangs: asked again sooner than a feed's 120 s) */
    rc = net_perform(&r);
    if (rc == NET_NOHANDLE) return PN_MEM;
    http = r.http;
    *got = f.n;
    if (http_out) *http_out = http;
    if (rc == 0 || (rc == CURLE_WRITE_ERROR && f.capped)) return PN_OK;
    return pn_rc(rc, http);
}

static int pn_fetch_json_raw(const char *url, char *buf, unsigned *got) {
    return pn_fetch_json_once(url, buf, got, (long *)0, 0);
}

/* The answer at url of a lookup service, one request, never repeated (a failure shows at once and the page's Try Again asks again). A busy answer (HTTP 503 or 429: LRCLIB under load answers uncached queries so) is
 * PN_OVERLOAD. The other codes as pn_fetch_json_raw (a 404 is PN_GONE). */
static int pn_fetch_json_api(const char *url, char *buf, unsigned *got) {
    long http = 0;
    int code = pn_fetch_json_once(url, buf, got, &http, 0);
    return code == PN_HTTP && (http == 503 || http == 429) ? PN_OVERLOAD : code;
}

/* The same, but a 404 is no news of a feed here: PN_HTTP. */
static int pn_fetch_json(const char *url, char *buf, unsigned *got) {
    int code = pn_fetch_json_raw(url, buf, got);
    return code == PN_GONE ? PN_HTTP : code;
}

/* A job's thread, started on the UI thread. */
static int pn_spawn(void *(*fn)(void *), int kind) {
    unsigned long th = 0;
    net_init();
    pn.busy = 1, pn.kind = kind, pn.cancel = pn.stopped = 0, pn.part = 0, pn.base = 0, pn.span = 1000, pn.cur = 0;
    pn_bump();
    if (pthread_create(&th, (const void *)0, fn, (void *)0)) {
        pn.kind = 0;
        pn.busy = 0;
        pn_bump();
        return PN_MEM;
    }
    pthread_detach(th);
    return PN_OK;
}

/* Result i's picture into PN_SEARCH_DIR/t<i>.jpg|png, when the answer is a picture the page can decode; else none (the placeholder stays). */
static void pn_thumb(int i) {
    char src[PN_PATH], dst[PN_PATH];
    unsigned w, h, sof;
    int kind, index = pn_starts(pn.surl, PN_INDEX_SEARCH_URL); /* the directory this job asked, not the setting now */
    const char *url = pn.sres[i].art;
    if ((pn_starts(url, "http://") || pn_starts(url, "https://")) && pn_thumb_path(i, "src", src, sizeof src) &&
        pn_fetch_file(url, src, index ? PN_INDEX_THUMB_CAP : PN_THUMB_CAP)) {
        kind = pc_pic_info(src, &w, &h, &sof);
        if (index && kind && (w > PV_SIZE || h > PV_SIZE)) { /* the feed's own picture: shrunk as a show's cover is */
            int r = !pn_thumb_path(i, "tmp", dst, sizeof dst) ? 0
                    : kind == 1                               ? pv_shrink(src, dst)
                                                              : pv_shrink_png(src, dst);
            if (r > 0 && !rename(dst, src))
                kind = 1; /* src is the small JPEG now */
            else if (r >= 0)
                kind = 0; /* (r < 0, an interlaced PNG: kept as it is when it is small enough, below) */
            unlink(dst);
        }
        if (kind && pc_cover_ok(src) && pn_thumb_path(i, kind == 2 ? "png" : "jpg", dst, sizeof dst) &&
            !rename(src, dst)) {
            pn.sext[i] = (unsigned char)kind;
            __sync_synchronize();
            pn.sthumb[i] = 1;
        } else
            unlink(src);
    }
    if (pn.sthumb[i] != 1) pn.sthumb[i] = 2;
    __sync_synchronize();
    ++pn.sgen;
}

static void *pn_smain(void *arg) {
    char *buf = calloc(PN_JSON_CAP + 1, 1);
    unsigned got = 0;
    int code = PN_MEM, n = 0, i;
    (void)arg;
    if (buf) {
        code = pn_fetch_json(pn.surl, buf, &got);
        if (code == PN_OK) {
            n = pj_results(buf, got, pn.sres, PJ_MAX);
            if (n < 0) code = PN_HTTP, n = 0; /* not an answer of the store */
        }
    }
    free(buf);
    pn.sn = code == PN_OK ? n : 0;
    pn.scode = code;
    __sync_synchronize();
    pn.sstate = code == PN_OK ? PN_S_THUMBS : PN_S_DONE;
    ++pn.sgen;
    pn_bump();
    for (i = 0; code == PN_OK && i < pn.sn && !pn.cancel; ++i) pn_thumb(i);
    __sync_synchronize();
    pn.sstate = PN_S_DONE;
    ++pn.sgen;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

int pn_search(const char *term) {
    int g;
    if (pn.busy) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    pn_search_dir();
    pn_search_clean();
    pn.surl[0] = 0;
    if (pcdir_index()) { /* Podcast Index instead of the store: no country */
        if (!pn_cat(pn.surl, sizeof pn.surl, PN_INDEX_SEARCH_URL) || !pn_urlenc(pn.surl, sizeof pn.surl, term))
            return PN_MEM;
    } else if (!pn_cat(pn.surl, sizeof pn.surl, PN_SEARCH_URL) || !pn_cat(pn.surl, sizeof pn.surl, pcregion_code()) ||
               !pn_cat(pn.surl, sizeof pn.surl, "&term=") || !pn_urlenc(pn.surl, sizeof pn.surl, term))
        return PN_MEM;
    pn.scode = PN_OK;
    pn.sstate = PN_S_QUERY;
    ++pn.sgen;
    g = pn_spawn(pn_smain, PN_KIND_SEARCH);
    if (g) pn.sstate = PN_S_IDLE;
    return g;
}

/* ---- Charts (patch/podcasts.c "Discover", docs/modules/podcasts.md "Discover"): Apple's top 25 shows and top 25 episodes of the Podcast Region. One job fetches a chart that is not held (up to PN_CHART_TRIES requests: a network or server
 * error is asked again; a 404, or an answer with no rows, for a region that is not the United States asks the United States chart instead and the chart says which it is of), then each row's artwork that has not been tried, one by one. */
#define PN_CHART_TRIES 3 /* requests for one chart before its error shows */
#define PN_CHART_WAIT 1 /* seconds between two of them */
#define PN_CHART_TIMEOUT 20 /* seconds one request may take (the shows chart was seen to hang) */

/* The chart's address for the storefront cc (two capitals, sent in lower case). 0 when it does not fit. */
static int pn_chart_url(char *out, unsigned size, const char *cc, int kind) {
    char c[3];
    unsigned i;
    for (i = 0; i < 2 && cc[i]; ++i) c[i] = cc[i] >= 'A' && cc[i] <= 'Z' ? (char)(cc[i] + 32) : cc[i];
    c[i] = 0;
    out[0] = 0;
    return pn_cat(out, size, PN_CHART_URL) && pn_cat(out, size, c) &&
           pn_cat(out, size, kind ? PN_CHART_EPISODES : PN_CHART_SHOWS);
}

static int pn_cthumb_path(int k, int i, const char *ext, char *out, unsigned size) {
    char name[24];
    pc_fmt2(name, sizeof name, "/c%d_%d.", (unsigned)k, (unsigned)i);
    out[0] = 0;
    return pn_cat(out, size, PN_SEARCH_DIR) && pn_cat(out, size, name) && pn_cat(out, size, ext);
}

/* The artwork files go and every row's artwork is untried again (the answers stay: the next job fetches the pictures once more). The page does this when it closes. */
void pn_chart_clean(void) {
    char path[PN_PATH];
    int k, i;
    for (k = 0; k < 2; ++k)
        for (i = 0; i < PJ_CHART; ++i) {
            if (pn_cthumb_path(k, i, "jpg", path, sizeof path)) unlink(path);
            if (pn_cthumb_path(k, i, "png", path, sizeof path)) unlink(path);
            if (pn_cthumb_path(k, i, "src", path, sizeof path)) unlink(path);
            pn.cthumb[k][i] = pn.cext[k][i] = 0;
        }
}

/* A storefront code (two capitals) into a 4 byte field. */
static void pn_cc_copy(char *dst, const char *src) {
    dst[0] = src[0], dst[1] = src[0] ? src[1] : 0, dst[2] = dst[3] = 0;
}

int pn_chart_state(int kind) { return kind >= 0 && kind < 2 ? pn.cstate[kind] : 0; }
int pn_chart_code(int kind) { return kind >= 0 && kind < 2 ? pn.ccode[kind] : PN_MEM; }
int pn_chart_count(int kind) { return kind >= 0 && kind < 2 && pn.cstate[kind] == 2 ? pn.cn[kind] : 0; }
unsigned pn_chart_gen(void) { return pn.cgen; }
const char *pn_chart_country(int kind) { return kind >= 0 && kind < 2 ? pn.cshown[kind] : ""; }
const pj_chart_t *pn_chart_item(int kind, int i) {
    return kind >= 0 && kind < 2 && pn.cstate[kind] == 2 && i >= 0 && i < pn.cn[kind] ? &pn.cres[kind][i]
                                                                                      : (const pj_chart_t *)0;
}

/* The chart is held: answered with rows, for the storefront in use now. */
int pn_chart_held(int kind) {
    return kind >= 0 && kind < 2 && pn.cstate[kind] == 2 && pn.ccode[kind] == PN_OK && pn.cn[kind] > 0 &&
           !strcmp(pn.creq[kind], pcregion_code());
}

int pn_chart_thumb(int kind, int i, char *path, unsigned size) {
    if (kind < 0 || kind > 1 || i < 0 || i >= PJ_CHART || pn.cthumb[kind][i] != 1) return 0;
    return pn_cthumb_path(kind, i, pn.cext[kind][i] == 2 ? "png" : "jpg", path, size);
}

/* The rows whose artwork has not been tried (the job fetches those). */
int pn_chart_pending(int kind) {
    int i, n = 0;
    if (!pn_chart_held(kind)) return 0;
    for (i = 0; i < pn.cn[kind]; ++i) n += pn.cthumb[kind][i] == 0;
    return n;
}

/* Row i's picture into PN_SEARCH_DIR/c<kind>_<i>.jpg|png, when the answer is a picture the page can decode; else none (the placeholder stays). */
static void pn_cthumb(int k, int i) {
    char src[PN_PATH], dst[PN_PATH];
    unsigned w, h, sof;
    int kind;
    const char *url = pn.cres[k][i].art;
    if ((pn_starts(url, "http://") || pn_starts(url, "https://")) && pn_cthumb_path(k, i, "src", src, sizeof src) &&
        pn_fetch_file(url, src, PN_THUMB_CAP)) {
        kind = pc_pic_info(src, &w, &h, &sof);
        if (kind && pc_cover_ok(src) && pn_cthumb_path(k, i, kind == 2 ? "png" : "jpg", dst, sizeof dst) &&
            !rename(src, dst)) {
            pn.cext[k][i] = (unsigned char)kind;
            __sync_synchronize();
            pn.cthumb[k][i] = 1;
        } else
            unlink(src);
    }
    if (pn.cthumb[k][i] != 1) pn.cthumb[k][i] = 2;
    __sync_synchronize();
    ++pn.cgen;
}

/* The chart's answer for storefront use into pn.cres[k]: the rows (>= 0), or -1 with *code the failure. The requests stop when the page cancels. */
static int pn_chart_ask(int k, const char *use, char *buf, int *code) {
    char url[PN_PATH];
    int attempt, n = 0;
    *code = PN_MEM;
    if (!pn_chart_url(url, sizeof url, use, k)) return -1;
    for (attempt = 0; attempt < PN_CHART_TRIES && !pn.cancel; ++attempt) {
        unsigned got = 0;
        n = 0;
        *code = pn_fetch_json_once(url, buf, &got, (long *)0, PN_CHART_TIMEOUT);
        if (*code == PN_OK) {
            n = pj_chart(buf, got, k, pn.cres[k], PJ_CHART);
            if (n < 0) *code = PN_HTTP, n = 0; /* not an answer of the store */
        }
        if (*code == PN_GONE || (*code != PN_NET && *code != PN_HTTP))
            break; /* only a failure that may pass is asked again */
        if (attempt + 1 < PN_CHART_TRIES && !pn.cancel) sleep(PN_CHART_WAIT);
    }
    return *code == PN_OK ? n : -1;
}

static void *pn_cmain(void *arg) {
    int k = pn.ckind, i;
    (void)arg;
    if (pn.cstate[k] == 1) {
        char *buf = calloc(PN_JSON_CAP + 1, 1);
        const char *use = pn.creq[k];
        int code = PN_MEM, n = -1;
        if (buf) {
            n = pn_chart_ask(k, use, buf, &code);
            if (!pn.cancel && strcmp(use, PCREGION_FALLBACK) &&
                (code == PN_GONE ||
                 (code == PN_OK && n == 0))) { /* this storefront has no such chart: the United States' */
                use = PCREGION_FALLBACK;
                n = pn_chart_ask(k, use, buf, &code);
            }
        }
        free(buf);
        if (pn.cancel) {
            pn.cstate[k] = 0; /* (nothing is held: the page asks again) */
        } else {
            pn.cn[k] = n > 0 ? n : 0;
            for (i = 0; i < PJ_CHART; ++i) pn.cthumb[k][i] = pn.cext[k][i] = 0;
            pn_cc_copy(pn.cshown[k], use);
            pn.ccode[k] = code;
            __sync_synchronize();
            pn.cstate[k] = 2;
        }
        ++pn.cgen;
        pn_bump();
    }
    for (i = 0; pn.cstate[k] == 2 && pn.ccode[k] == PN_OK && i < pn.cn[k] && !pn.cancel; ++i)
        if (pn.cthumb[k][i] == 0) pn_cthumb(k, i);
    __sync_synchronize();
    ++pn.cgen;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

int pn_chart(int kind) {
    int g, held;
    if (kind < 0 || kind > 1) return PN_MEM;
    if (pn.busy) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    pn_search_dir();
    held = pn_chart_held(kind);
    if (!held) {
        pn.cstate[kind] = 1;
        pn.cn[kind] = 0;
        pn_cc_copy(pn.creq[kind], pcregion_code());
    }
    pn.ckind = kind;
    ++pn.cgen;
    g = pn_spawn(pn_cmain, PN_KIND_CHART);
    if (g && !held) pn.cstate[kind] = 0;
    return g;
}

/* ---- Find Cover & Lyrics (patch/onlineart.c is the page; docs/modules/onlineart.md) */
#define PN_ART_URL 1280 /* a request's address: three fields of 95 bytes, each at most three times as long encoded */

static void pn_art_dir(void) {
    mkdir("/mnt/mmc/.m1plus", 0755);
    mkdir(PN_ART_DIR, 0755);
}

static int pn_art_path(int i, const char *ext, char *out, unsigned size) {
    char name[24];
    pc_fmt(name, sizeof name, "/a%d.", (unsigned)i);
    out[0] = 0;
    return pn_cat(out, size, PN_ART_DIR) && pn_cat(out, size, name) && pn_cat(out, size, ext);
}

/* s into d (PN_ART_Q bytes): cut before a character that does not fit whole. */
static void pn_art_field(char *d, const char *s) {
    unsigned n = 0;
    while (s[n] && n + 1 < PN_ART_Q) ++n;
    if (s[n])
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    memcpy(d, s, n);
    d[n] = 0;
}

static int pn_lyr_path(int slot, char *out, unsigned size) {
    char name[24];
    pc_fmt(name, sizeof name, "/l%d.txt", (unsigned)slot);
    out[0] = 0;
    return pn_cat(out, size, PN_ART_DIR) && pn_cat(out, size, name);
}

void pn_art_full_drop(void) {
    unlink(PN_ART_DIR "/full.jpg");
    unlink(PN_ART_DIR "/full.png");
    unlink(PN_ART_DIR "/pick.src");
    pn.fidx = pn.fext = 0;
}

/* The files and results of the parts in mask (PN_PART_*). */
static void pn_art_clean_parts(int mask) {
    char path[PN_PATH];
    int i;
    if (mask & PN_PART_COVERS) {
        for (i = 0; i < PN_ART_MAX; ++i) {
            if (pn_art_path(i, "jpg", path, sizeof path)) unlink(path);
            if (pn_art_path(i, "png", path, sizeof path)) unlink(path);
            if (pn_art_path(i, "src", path, sizeof path)) unlink(path);
            pn.athumb[i] = pn.aext[i] = 0;
        }
        pn_art_full_drop();
        pn.an = 0;
    }
    if (mask & PN_PART_LYRICS) {
        for (i = 0; i < PN_LYR_MAX; ++i)
            if (pn_lyr_path(i, path, sizeof path)) unlink(path);
        unlink(PN_ART_DIR "/lyrics.tmp");
        pn.ln = 0;
        pn.lstate = 0;
    }
}

void pn_art_clean(void) { pn_art_clean_parts(PN_PART_COVERS | PN_PART_LYRICS); }

int pn_art_state(void) { return pn.astate; }
int pn_art_code(void) { return pn.acode; }
int pn_art_count(void) { return pn.an; }
unsigned pn_art_gen(void) { return pn.agen; }
int pn_lyr_state(void) { return pn.lstate; }
int pn_lyr_code(void) { return pn.lcode; }
int pn_lyr_count(void) { return pn.ln; }
const char *pn_art_name(int i) { return i >= 0 && i < pn.an ? pn.ares[i].name : ""; }
const char *pn_art_artist(int i) { return i >= 0 && i < pn.an ? pn.ares[i].author : ""; }
int pn_art_source(int i) { return i >= 0 && i < PN_ART_MAX ? pn.asrc[i] : 0; }
int pn_pick_state(void) { return pn.pkstate; }
int pn_pick_code(void) { return pn.pkcode; }

int pn_art_thumb_state(int i) { return i >= 0 && i < PN_ART_MAX ? pn.athumb[i] : 0; }

int pn_art_thumb(int i, char *path, unsigned size) {
    if (i < 0 || i >= PN_ART_MAX || pn.athumb[i] != 1) return 0;
    return pn_art_path(i, pn.aext[i] == 2 ? "png" : "jpg", path, size);
}

const pn_lyr_t *pn_lyr_get(int i) { return i >= 0 && i < pn.ln ? &pn.lcand[pn.lslot[i]] : (const pn_lyr_t *)0; }

char *pn_lyr_text(int i, unsigned *n) {
    char path[PN_PATH];
    if (i < 0 || i >= pn.ln || !pn_lyr_path(pn.lslot[i], path, sizeof path)) return (char *)0;
    return m1_read_file(path, PN_LRC_CAP, n);
}

int pn_art_full_path(int i, char *path, unsigned size) {
    if (i < 0 || i >= pn.an || pn.fidx != i + 1 || !pn.fext) return 0;
    path[0] = 0;
    return pn_cat(path, size, PN_ART_DIR) && pn_cat(path, size, pn.fext == 2 ? "/full.png" : "/full.jpg");
}

int pn_art_full(const char *thumb, char *out, unsigned size) {
    static const char *const from[3] = {"100x100bb", "250x250-", "250y250"},
                             *const to[3] = {"600x600bb", "500x500-", "500y500"}; /* iTunes, Deezer, NetEase */
    unsigned n = strlen(thumb), i;
    int k;
    if (n + 1 > size) return 0;
    memcpy(out, thumb, n + 1);
    for (k = 0; k < 3; ++k)
        for (i = 0; i < n; ++i)
            if (pn_starts(thumb + i, from[k])) {
                memcpy(out + i, to[k], strlen(to[k])); /* the same length: the address is changed in place */
                return 1;
            }
    return 1;
}

/* The covers' query into url (after its base): "artist album", else "artist title". */
static int pn_art_term(char *url, unsigned size) {
    char term[PN_ART_Q * 2 + 2];
    term[0] = 0;
    pn_cat(term, sizeof term, pn.aq[0]);
    if (term[0]) pn_cat(term, sizeof term, " ");
    pn_cat(term, sizeof term, pn.aq[1][0] ? pn.aq[1] : pn.aq[2]);
    return pn_urlenc(url, size, term);
}

/* Both stores' answers into pn.ares: the first PN_ART_ITUNES_MAX albums of the iTunes Search API that have a picture, then Deezer's up to PN_ART_MAX in all. The code is PN_OK when an answer came (even with
 * no result); else the first failure. */
static int pn_art_covers(char *buf) {
    char *url = calloc(PN_ART_URL, 1);
    pj_result_t *tmp = calloc(PJ_MAX, sizeof *tmp);
    int n = 0, k, bad = 0, ok = 0;
    if (!url || !tmp) {
        free(url);
        free(tmp);
        pn.an = 0;
        return PN_MEM;
    }
    for (k = 0; k < 2 && !pn.cancel; ++k) {
        unsigned got = 0;
        int c, m, i;
        url[0] = 0;
        if (!pn_cat(url, PN_ART_URL, k ? PN_ART_DEEZER : PN_ART_ITUNES) || !pn_art_term(url, PN_ART_URL)) {
            if (!bad) bad = PN_MEM;
            continue;
        }
        c = pn_fetch_json_api(url, buf, &got);
        if (c == PN_GONE) c = PN_HTTP;
        if (c == PN_OK) {
            m = k ? pj_deezer(buf, got, tmp, PJ_MAX) : pj_results(buf, got, tmp, PJ_MAX);
            if (m < 0)
                c = PN_HTTP; /* not an answer of that service */
            else {
                ok = 1;
                for (i = 0; i < m && n < (k ? PN_ART_MAX : PN_ART_ITUNES_MAX); ++i)
                    if (pn_starts(tmp[i].art, "https://") || pn_starts(tmp[i].art, "http://")) {
                        memcpy(&pn.ares[n], &tmp[i], sizeof pn.ares[n]);
                        pn.asrc[n] = (unsigned char)k;
                        ++n;
                    }
            }
        }
        if (c != PN_OK && !bad) bad = c;
    }
    free(url);
    free(tmp);
    pn.an = n;
    if (pn.cancel) return PN_CANCELLED;
    return ok || n ? PN_OK : bad ? bad : PN_OK;
}

/* part occurs in s. */
static int pn_has(const char *s, const char *part) {
    for (; *s; ++s)
        if (pn_starts(s, part)) return 1;
    return 0;
}

/* The artist search at base for the name in pn.aq[0]: the answer into buf, *got bytes. The code as pn_fetch_json_api's, a 404 PN_HTTP. */
static int pn_artist_ask(char *url, const char *base, char *buf, unsigned *got) {
    int c;
    url[0] = 0;
    if (!pn_cat(url, PN_ART_URL, base) || !pn_urlenc(url, PN_ART_URL, pn.aq[0])) return PN_MEM;
    c = pn_fetch_json_api(url, buf, got);
    return c == PN_GONE ? PN_HTTP : c;
}

/* NetEase's artists (nt, m of them, in the service's order: the best match first) that are offered, into ne (PN_ARTIST_NETEASE): those of the very name that have a picture of their own (an artist without one is
 * given PN_NETEASE_BLANK), else the first one (the name in another script or with a suffix, "BTS (...)"; the ones after it are other people). art becomes the square picture's address at 250 px. Returns how many. */
static int pn_netease_take(pj_result_t *nt, int m, pj_result_t *ne) {
    unsigned key = pn.akey;
    int n = 0, i, pass;
    for (pass = 0; pass < 2 && !n; ++pass)
        for (i = 0; i < (pass ? m > 0 : m) && n < PN_ARTIST_NETEASE; ++i) {
            pj_result_t *r = &nt[i];
            const char *pic = r->art[0] && !pn_has(r->art, PN_NETEASE_BLANK)
                                  ? r->art
                                  : r->art6; /* (the square one, else the other) */
            if (!pass && !(key && ap_key(r->feed) == key)) continue;
            if ((!pn_starts(pic, "https://") && !pn_starts(pic, "http://")) || pn_has(pic, PN_NETEASE_BLANK)) continue;
            if (pic != r->art) memcpy(r->art, pic, PJ_ART);
            if (!pn_cat(r->art, PJ_ART, PN_NETEASE_THUMB)) continue;
            memcpy(&ne[n++], r, sizeof *r);
        }
    return n;
}

/* The artists for the name in pn.aq[0] into pn.ares, from Deezer's answer, then NetEase's.
 * Deezer's: those that have a picture of their own (an artist without one is given the service's blank, whose address has an empty picture id: ".../artist//250x250..."), the most followed first (the service lists a
 * name's duplicates, most of them empty shells, in no useful order), a picture once. The search is a loose one (other artists with a like name, the more followed of them above the one asked for), so the artists of
 * that very name (ap_key of the whole names, before either is cut: the case, a leading "The ") come first, then NetEase's (pn_netease_take), then at most PN_ARTIST_OTHER of Deezer's others (the same artist under another
 * spelling or script is among them), PN_ARTIST_MAX in all. The code is PN_OK when a service answered (even with no artist); else the first failure. */
static int pn_artist_covers(char *buf) {
    char *url = calloc(PN_ART_URL, 1);
    pj_result_t *tmp = calloc(PJ_MAX + PN_NETEASE_MAX + PN_ARTIST_NETEASE, sizeof *tmp), *nt = tmp + PJ_MAX,
                *ne = nt + PN_NETEASE_MAX;
    unsigned char ord[PJ_MAX], same[PJ_MAX];
    unsigned got = 0, key = pn.akey;
    int n = 0, m = 0, nn = 0, others = 0, ok = 0, bad = 0, i, j, c, pass;
    pn.an = 0;
    if (!url || !tmp) {
        free(url);
        free(tmp);
        return PN_MEM;
    }
    c = pn_artist_ask(url, PN_ART_DEEZER_ARTIST, buf, &got);
    if (c == PN_OK && (m = pj_deezer_artists(buf, got, tmp, PJ_MAX)) < 0) c = PN_HTTP, m = 0;
    if (c == PN_OK)
        ok = 1;
    else
        bad = c;
    if (!pn.cancel) {
        int k = 0;
        c = pn_artist_ask(url, PN_ART_NETEASE_ARTIST, buf, &got);
        if (c == PN_OK && (k = pj_netease_artists(buf, got, nt, PN_NETEASE_MAX)) < 0) c = PN_HTTP, k = 0;
        if (c == PN_OK)
            ok = 1, nn = pn_netease_take(nt, k, ne);
        else if (!bad)
            bad = c;
    }
    for (i = 0; i < m; ++i) { /* (stable: equal counts keep the service's order) */
        same[i] = key && ap_key(tmp[i].feed) == key; /* (the whole name: name is cut at PJ_NAME) */
        for (j = i; j; --j) {
            int k = ord[j - 1];
            if (same[k] > same[i] || (same[k] == same[i] && tmp[k].id >= tmp[i].id)) break;
            ord[j] = ord[j - 1];
        }
        ord[j] = (unsigned char)i;
    }
    for (pass = 0; pass < 2;
         ++pass) { /* Deezer's of the very name (room is kept for NetEase's), NetEase's, Deezer's others */
        for (i = 0; i < m && n < PN_ARTIST_MAX - (pass ? 0 : nn); ++i) {
            const pj_result_t *r = &tmp[ord[i]];
            if (same[ord[i]] == pass) continue;
            if (!pn_starts(r->art, "https://") || pn_has(r->art, "/artist//")) continue;
            for (j = 0; j < n && strcmp(pn.ares[j].art, r->art); ++j);
            if (j < n) continue;
            if (pass && others++ >= PN_ARTIST_OTHER) break;
            memcpy(&pn.ares[n], r, sizeof pn.ares[n]);
            pn.asrc[n] = PN_SRC_DEEZER;
            ++n;
        }
        for (i = 0; !pass && i < nn && n < PN_ARTIST_MAX; ++i) {
            memcpy(&pn.ares[n], &ne[i], sizeof pn.ares[n]);
            pn.asrc[n] = PN_SRC_NETEASE;
            ++n;
        }
    }
    free(url);
    free(tmp);
    pn.an = n;
    if (pn.cancel) return PN_CANCELLED;
    return ok ? PN_OK : bad ? bad : PN_OK;
}

/* Cover i's thumbnail into PN_ART_DIR/a<i>.jpg|png, when the answer is a picture the page can decode; else none (the placeholder stays). */
static void pn_art_thumb_get(int i) {
    char src[PN_PATH], dst[PN_PATH];
    unsigned w, h, sof;
    int kind;
    const char *url = pn.ares[i].art;
    if ((pn_starts(url, "http://") || pn_starts(url, "https://")) && pn_art_path(i, "src", src, sizeof src) &&
        pn_fetch_file(url, src, PN_THUMB_CAP)) {
        kind = pc_pic_info(src, &w, &h, &sof);
        if (kind && pc_cover_ok(src) && pn_art_path(i, kind == 2 ? "png" : "jpg", dst, sizeof dst) &&
            !rename(src, dst)) {
            pn.aext[i] = (unsigned char)kind;
            __sync_synchronize();
            pn.athumb[i] = 1;
        } else
            unlink(src);
    }
    if (pn.athumb[i] != 1) pn.athumb[i] = 2;
    __sync_synchronize();
    ++pn.agen;
}

/* Lyrics candidates: every LRCLIB record that has lyrics, its text in PN_ART_DIR/l<slot>.txt (slots in arrival order, written atomically) and its fields in pn.lcand[slot]. A record equal to one held (the same
 * fields and kind: api/search repeats what api/get gave) is skipped. *ctx counts the texts that could not be written. */
_Static_assert(sizeof(((pn_lyr_t *)0)->title) == PJ_NAME && sizeof(((pn_lyr_t *)0)->artist) == PJ_AUTHOR &&
                   sizeof(((pn_lyr_t *)0)->album) == PJ_NAME,
               "pn_lyr_t holds a pj_lrc_t's strings");

static int pn_lyr_add(void *ctx, const pj_lrc_t *r, const char *text) {
    char path[PN_PATH];
    unsigned n = strlen(text);
    int i, slot = pn.ln;
    if (slot >= PN_LYR_MAX) return 0;
    for (i = 0; i < slot; ++i) {
        const pn_lyr_t *c = &pn.lcand[i];
        if (c->secs == r->secs && c->synced == r->synced && !strcmp(c->title, r->title) &&
            !strcmp(c->artist, r->artist) && !strcmp(c->album, r->album))
            return 1;
    }
    pn_art_dir();
    if (!pn_lyr_path(slot, path, sizeof path) || !m1_save(path, PN_ART_DIR "/lyrics.tmp", 0644, text, n)) {
        ++*(int *)ctx;
        return 1;
    }
    memcpy(pn.lcand[slot].title, r->title, sizeof r->title);
    memcpy(pn.lcand[slot].artist, r->artist, sizeof r->artist);
    memcpy(pn.lcand[slot].album, r->album, sizeof r->album);
    pn.lcand[slot].secs = r->secs, pn.lcand[slot].synced = r->synced;
    ++pn.ln;
    return 1;
}

/* How far a candidate's length is from the track's (unknown lengths last once the track's is known; all equal when it is not). */
static unsigned pn_lyr_dist(const pn_lyr_t *c) {
    if (!pn.adur) return 0;
    if (!c->secs) return 0x7fffffffu;
    return c->secs > pn.adur ? c->secs - pn.adur : pn.adur - c->secs;
}

/* The display order: the first nex candidates (api/get's exact match) stay first, the rest by the closeness of their length to the track's, a synced one before a plain one among equals, otherwise in arrival order. */
static void pn_lyr_order(int nex) {
    int i, j, n = pn.ln;
    unsigned char ord[PN_LYR_MAX];
    for (i = 0; i < n; ++i) ord[i] = (unsigned char)i;
    for (i = nex + 1; i < n; ++i) {
        unsigned char s = ord[i];
        unsigned ds = pn_lyr_dist(&pn.lcand[s]);
        for (j = i; j > nex; --j) {
            unsigned dp = pn_lyr_dist(&pn.lcand[ord[j - 1]]);
            if (!(ds < dp || (ds == dp && pn.lcand[s].synced && !pn.lcand[ord[j - 1]].synced))) break;
            ord[j] = ord[j - 1];
        }
        ord[j] = s;
    }
    for (i = 0; i < n; ++i) pn.lslot[i] = ord[i];
}

/* LRCLIB's records for the track: api/get (the artist, title, album and length: the exact match) and api/search (the title and artist) as candidates. Sets lcode and the candidates. buf: the answer's buffer. */
static void pn_lyrics(char *buf) {
    char *url = calloc(PN_ART_URL, 1), *a = calloc(2 * (PN_LRC_CAP + 1), 1);
    unsigned got = 0;
    int code = PN_MEM, code2 = PN_OK, nex = 0, fail = 0;
    pn.ln = 0;
    if (!url || !a) goto out;
    url[0] = 0;
    if (pn_cat(url, PN_ART_URL, PN_ART_LRCLIB "get?track_name=") && pn_urlenc(url, PN_ART_URL, pn.aq[2]) &&
        pn_cat(url, PN_ART_URL, "&artist_name=") && pn_urlenc(url, PN_ART_URL, pn.aq[0]) &&
        (!pn.aq[1][0] || (pn_cat(url, PN_ART_URL, "&album_name=") && pn_urlenc(url, PN_ART_URL, pn.aq[1])))) {
        if (pn.adur) {
            char num[24];
            pc_fmt(num, sizeof num, "&duration=%d", pn.adur);
            pn_cat(url, PN_ART_URL, num);
        }
        code = pn_fetch_json_api(url, buf, &got);
        if (code == PN_OK) pj_lrc_each(buf, got, PN_LRC_CAP, a, a + PN_LRC_CAP + 1, pn_lyr_add, &fail);
    }
    nex = pn.ln;
    if (!pn.cancel &&
        (code == PN_OK || code == PN_GONE || code == PN_HTTP)) { /* (a busy get is PN_OVERLOAD at once: no search) */
        url[0] = 0;
        if (pn_cat(url, PN_ART_URL, PN_ART_LRCLIB "search?track_name=") && pn_urlenc(url, PN_ART_URL, pn.aq[2]) &&
            pn_cat(url, PN_ART_URL, "&artist_name=") && pn_urlenc(url, PN_ART_URL, pn.aq[0])) {
            code2 = pn_fetch_json_api(url, buf, &got);
            if (code2 == PN_OK) pj_lrc_each(buf, got, PN_LRC_CAP, a, a + PN_LRC_CAP + 1, pn_lyr_add, &fail);
        } else
            code2 = PN_MEM;
        if (!pn.ln) code = code2;
    }
    if (pn.cancel)
        code = PN_CANCELLED;
    else if (pn.ln)
        code = PN_OK;
    else if (fail)
        code = PN_STORAGE;
    else if (code == PN_OK || code == PN_GONE)
        code = PN_NOLYRICS; /* answered, and no record has any */
    if (code == PN_OK) pn_lyr_order(nex);
out:
    free(url);
    free(a);
    if (code != PN_OK) pn.ln = 0;
    pn.lcode = code;
    __sync_synchronize();
    pn.lstate = 1;
    ++pn.agen;
}

static void *pn_amain(void *arg) {
    char *buf = calloc(PN_JSON_CAP + 1, 1);
    int code = PN_MEM, i;
    (void)arg;
    if (pn.amask & PN_PART_COVERS) {
        if (buf) code = pn.aartist ? pn_artist_covers(buf) : pn_art_covers(buf);
        pn.acode = code;
        __sync_synchronize();
        pn.astate = code == PN_OK && pn.an > 0 ? PN_A_THUMBS : PN_A_DONE;
        ++pn.agen;
        pn_bump();
        for (i = 0; code == PN_OK && i < pn.an && !pn.cancel; ++i) pn_art_thumb_get(i);
        __sync_synchronize();
        pn.astate = PN_A_DONE;
        ++pn.agen;
    }
    if (pn.amask & PN_PART_LYRICS) {
        if (buf && !pn.cancel)
            pn_lyrics(buf);
        else {
            pn.ln = 0, pn.lcode = pn.cancel ? PN_CANCELLED : PN_MEM;
            __sync_synchronize();
            pn.lstate = 1;
            ++pn.agen;
        }
    }
    free(buf);
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

/* The worker for the parts in mask, with the query already in pn.aq / pn.adur. */
static int pn_art_run(int mask) {
    int g = pn_guard();
    if (g) return g;
    pn_art_dir();
    pn_art_clean_parts(mask);
    pn.amask = mask;
    if (mask & PN_PART_COVERS) pn.acode = PN_OK, pn.astate = PN_A_COVERS;
    if (mask & PN_PART_LYRICS) pn.lcode = PN_OK;
    pn.pkstate = 0;
    ++pn.agen;
    g = pn_spawn(pn_amain, PN_KIND_ART);
    if (g && (mask & PN_PART_COVERS)) pn.astate = PN_A_IDLE;
    return g;
}

int pn_art(const char *artist, const char *album, const char *title, unsigned seconds) {
    if (pn.busy) return PN_BUSY;
    pn_art_field(pn.aq[0], artist ? artist : "");
    pn_art_field(pn.aq[1], album ? album : "");
    pn_art_field(pn.aq[2], title ? title : "");
    pn.adur = seconds;
    pn.aartist = 0;
    return pn_art_run(PN_PART_COVERS | PN_PART_LYRICS);
}

int pn_artist(const char *name) {
    if (pn.busy) return PN_BUSY;
    pn_art_field(pn.aq[0], name ? name : "");
    pn.aq[1][0] = pn.aq[2][0] = 0;
    pn.adur = 0;
    pn.akey = ap_key(name);
    pn.aartist = 1;
    return pn_art_run(PN_PART_COVERS);
}

int pn_art_again(int part) {
    if (pn.busy) return PN_BUSY;
    if (part != PN_PART_COVERS && (part != PN_PART_LYRICS || pn.aartist)) return PN_MEM;
    return pn_art_run(part);
}

/* The name the folder's picture gets: the first of folder.jpg, folder.jpeg, cover.jpg and cover.jpeg that is there (stock's Now Playing takes the first image it finds in that order, so the new one replaces it), else cover.jpg. */
static int pn_art_side(const char *dir, char *out, unsigned size) {
    static const char *const names[4] = {"folder.jpg", "folder.jpeg", "cover.jpg", "cover.jpeg"};
    int k;
    for (k = 0; k < 4; ++k)
        if (pn_join(out, size, dir, names[k], (const char *)0) && !access(out, F_OK)) return 1;
    return pn_join(out, size, dir, "cover.jpg", (const char *)0);
}

/* The larger picture of cover pkidx. Fetch (pkmode 0): downloaded to full.jpg|png when it is a picture the page can decode (pn.fidx / pn.fext say which cover). Save (pkmode 1): that picture (or one downloaded now),
 * shrunk into each key's cover cache file (and a .pick marker beside it), the original JPEG into the track's folder. */
static void *pn_kmain(void *arg) {
    char url[PN_PATH], src[PN_PATH], dst[64], tmp[64], mark[72], side[PN_PATH];
    unsigned w, h, sof, wrote = 0, k;
    int kind = 0, code = PN_NET, held = 0;
    (void)arg;
    src[0] = 0;
    mkdir(CARD_DIR, 0755);
    mkdir(ART_DIR, 0755);
    pn_art_dir();
    if (pn.pkmode && pn.fidx == pn.pkidx + 1 && pn.fext && pn_art_full_path(pn.pkidx, src, sizeof src))
        held = 1, kind = pn.fext;
    else {
        pn_art_full_drop();
        pn_cat(src, sizeof src, PN_ART_DIR "/pick.src");
        if (pn_art_full(pn.ares[pn.pkidx].art, url, sizeof url) && pn_fetch_file(url, src, PN_PICK_CAP)) {
            kind = pc_pic_info(src, &w, &h, &sof);
            code = PN_NOTFEED;
        }
    }
    if (!pn.pkmode) {
        if (kind && !held) {
            if (pc_cover_ok(src) && !pn.cancel &&
                !rename(src, kind == 2 ? PN_ART_DIR "/full.png" : PN_ART_DIR "/full.jpg")) {
                pn.fext = kind;
                pn.fidx = pn.pkidx + 1;
                code = PN_OK;
            } else
                code = PN_NOTFEED;
        }
        if (pn.cancel) code = PN_CANCELLED;
    } else if (pn.pkmode == 2) { /* an artist's photo: the cache files of patch/artistphoto.c and its .pick marker */
        if (kind) code = pn.cancel ? PN_CANCELLED : ap_pick(src, pn.pkkey[0]) ? PN_OK : PN_STORAGE;
    } else if (kind) {
        code = PN_NOTFEED;
        for (k = 0; k < 2; ++k) {
            unsigned key = pn.pkkey[k];
            int ok;
            if (!key || pn.cancel) continue;
            cc_path(dst, sizeof dst, key, "");
            cc_path(tmp, sizeof tmp, key, ".tmp");
            cc_path(mark, sizeof mark, key, ".pick");
            ok = kind == 1 ? pv_shrink(src, tmp) : pv_shrink_png(src, tmp) > 0;
            if (ok && !rename(tmp, dst)) {
                int fd = open(mark, O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (fd >= 0) close(fd);
                ++wrote;
            } else {
                unlink(tmp);
                code = PN_STORAGE;
            }
        }
        if (wrote && kind == 1 && pn.pkdir[0] && !pn.cancel && pn_art_side(pn.pkdir, side, sizeof side)) {
            unsigned n = 0;
            char *data = m1_read_file(src, PN_PICK_CAP, &n);
            char stmp[PN_PATH];
            stmp[0] = 0;
            if (data && pn_join(stmp, sizeof stmp, pn.pkdir, ".cover.tmp", (const char *)0))
                m1_save(side, stmp, 0644, data, n);
            free(data); /* (a folder that cannot be written keeps the cache's cover: the sidecar is the extra) */
        }
        if (wrote) code = PN_OK;
        if (pn.cancel) code = PN_CANCELLED;
    }
    if (!held) unlink(src);
    pn.pkcode = code;
    __sync_synchronize();
    pn.pkstate = 2;
    ++pn.agen;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

static int pn_pick_spawn(int i, int mode, const char *dir, unsigned key0, unsigned key1) {
    int g;
    if (i < 0 || i >= pn.an || pn.athumb[i] != 1) return PN_NOFEED;
    if (pn.busy) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    pn.pkdir[0] = 0;
    if (dir && !pn_cat(pn.pkdir, sizeof pn.pkdir, dir)) pn.pkdir[0] = 0;
    pn.pkkey[0] = key0, pn.pkkey[1] = key1, pn.pkidx = i, pn.pkmode = mode;
    pn.pkstate = 1, pn.pkcode = PN_OK;
    ++pn.agen;
    g = pn_spawn(pn_kmain, PN_KIND_PICK);
    if (g) pn.pkstate = 0;
    return g;
}

int pn_art_fetch(int i) { return pn_pick_spawn(i, 0, (const char *)0, 0, 0); }

int pn_art_pick(int i, const char *dir, unsigned key0, unsigned key1) {
    if (!key0 && !key1) return PN_NOFEED;
    return pn_pick_spawn(i, 1, dir, key0, key1);
}

int pn_artist_pick(int i, unsigned key) {
    if (!key) return PN_NOFEED;
    return pn_pick_spawn(i, 2, (const char *)0, key, 0);
}

int pn_lyr_save(int i, const char *path) {
    unsigned n = 0;
    char tmp[PN_PATH];
    char *data = pn_lyr_text(i, &n);
    int ok;
    tmp[0] = 0;
    ok = data && pn_cat(tmp, sizeof tmp, path) && pn_cat(tmp, sizeof tmp, ".tmp") && m1_card_mounted() &&
         m1_save(path, tmp, 0644, data, n);
    free(data);
    return ok;
}

/* ---- Preview */
void pn_preview_drop(void) {
    pf_parser_t *p = pn.prev;
    pn.prev = (pf_parser_t *)0;
    if (p) pf_free(p);
    unlink(PN_PREVIEW_COVER);
    pn.pstate = 0;
}

int pn_preview_state(void) { return pn.pstate; }
int pn_preview_code(void) { return pn.pcode; }
void *pn_preview_parser(void) { return pn.prev; }
int pn_preview_match(void) { return pn.pmatch; }
const char *pn_preview_feed(void) { return pn.purl; }
int pn_preview_cover(void) { return !access(PN_PREVIEW_COVER, F_OK); }

/* The picture at url downloaded, shrunk (the Show page's own path: pv_shrink, pv_shrink_png) to PN_PREVIEW_COVER. 1 when it is there; whatever fails leaves no file. */
static int pn_preview_one(const char *url) {
    static const char src[] = PN_SEARCH_DIR "/preview.src", tmp[] = PN_SEARCH_DIR "/preview.tmp";
    unsigned w, h, sof;
    int kind, ok = 0;
    if (!pn_starts(url, "http://") && !pn_starts(url, "https://")) return 0;
    if (!pn_fetch_file(url, src, PN_COVER_CAP)) return 0;
    kind = pc_pic_info(src, &w, &h, &sof);
    if (kind == 1)
        ok = pv_shrink(src, tmp) && !rename(tmp, PN_PREVIEW_COVER);
    else if (kind == 2)
        ok = pv_shrink_png(src, tmp) > 0 && !rename(tmp, PN_PREVIEW_COVER);
    unlink(tmp);
    unlink(src);
    return ok;
}

/* The preview's picture: the feed's image, else (it cannot be fetched, decoded or shrunk: a progressive JPEG of over 2.1 MP is refused) the store's 600 x 600 one when the show came from the store; with neither the
 * preview has the placeholder. pn_subscribe keeps this file as the show's cover.jpg, so the fallback is the first cover; a refresh never replaces a cover (pn_cover). */
static void pn_preview_picture(const char *url) {
    if (!pn_preview_one(url) && pn.pfb[0]) pn_preview_one(pn.pfb);
}

/* A chart's episode row: the store's episode lookup of its show (the chart's store, &entity=podcastEpisode&limit=20) names the episode by its trackId, and pf_match finds the kept feed item it is (its
 * enclosure, else its pubDate's minute, else its title). A failed or empty lookup, or no match, leaves pn.pmatch -1: the show's preview, as before. A cancel is the caller's to see. */
static void pn_pmatch(const pf_parser_t *p) {
    char *buf = calloc(PN_JSON_CAP + 1, 1);
    pj_ep_t *eps = calloc(PJ_EPS, sizeof *eps);
    char url[PN_PATH];
    unsigned got = 0;
    int i, n;
    pn.pmatch = -1;
    if (!buf || !eps) {
        free(buf);
        free(eps);
        return;
    }
    url[0] = 0;
    pn_cat(url, sizeof url, PN_LOOKUP_URL);
    pn_cat(url, sizeof url, pn.pid);
    pn_cat(url, sizeof url, "&entity=podcastEpisode&limit=20&country=");
    pn_cat(url, sizeof url, pn.pcc);
    if (pn_fetch_json(url, buf, &got) == PN_OK && (n = pj_episodes(buf, got, eps, PJ_EPS)) > 0)
        for (i = 0; i < n; ++i)
            if (!strcmp(eps[i].id, pn.peid)) {
                pn.pmatch = pf_match(p, eps[i].url, pf_iso(eps[i].date), eps[i].name);
                break;
            }
    free(buf);
    free(eps);
}

static void *pn_pmain(void *arg) {
    pf_parser_t *p = (pf_parser_t *)0;
    char feed[PC_URL];
    int code = PN_OK;
    unsigned unused; /* the answer's Last-Modified: a preview keeps none (its first refresh is unconditional) */
    (void)arg;
    feed[0] = 0;
    if (pn.pid[0]) { /* an Apple Podcasts link: the store's lookup names the feed */
        char *buf = calloc(PN_JSON_CAP + 1, 1);
        char url[PN_PATH];
        pj_result_t *r = calloc(1, sizeof *r);
        unsigned got = 0;
        url[0] = 0;
        pn_cat(url, sizeof url,
               !pn.pcc[0] && pcdir_index() ? PN_INDEX_LOOKUP_URL
                                           : PN_LOOKUP_URL); /* (a chart row: the store, whatever the choice) */
        pn_cat(url, sizeof url, pn.pid);
        if (pn.pcc
                [0]) { /* a chart row: the store the chart is of (a show of another store has no record in this one's) */
            pn_cat(url, sizeof url, "&country=");
            pn_cat(url, sizeof url, pn.pcc);
        }
        if (!buf || !r)
            code = PN_MEM;
        else if ((code = pn_fetch_json(url, buf, &got)) == PN_OK) {
            if (pj_results(buf, got, r, 1) < 1 || !r->feed[0])
                code = PN_NOFEED;
            else {
                memcpy(feed, r->feed, sizeof feed);
                memcpy(pn.pfb, r->art6, sizeof pn.pfb);
            }
        }
        free(buf);
        free(r);
    } else
        memcpy(feed, pn.purl, sizeof feed);
    if (code == PN_OK) {
        p = pf_new();
        code = p ? pn_fetch(feed, p, 0, &unused) : PN_MEM;
    }
    if (code == PN_OK && pn.pid[0] && pn.pcc[0] && pn.peid[0]) pn_pmatch(p);
    if (code == PN_OK && pn.cancel) code = PN_CANCELLED;
    if (code == PN_OK) {
        memcpy(pn.purl, feed, sizeof pn.purl);
        unlink(PN_PREVIEW_COVER);
        pn_preview_picture(pf_image(p));
        if (pn.cancel) code = PN_CANCELLED;
    }
    if (code == PN_OK)
        pn.prev = p;
    else if (p)
        pf_free(p);
    pn.pcode = code;
    __sync_synchronize();
    pn.pstate = 2;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

static int pn_preview_start(const char *url, const char *id, const char *cc, const char *art, const char *eid) {
    int g;
    if (pn.busy) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    pn_search_dir();
    pn_preview_drop();
    pn.purl[0] = 0;
    pn.pid[0] = 0;
    pn_cc_copy(pn.pcc, cc);
    pn.pfb[0] = 0;
    if (strlen(art) < sizeof pn.pfb) pn_cat(pn.pfb, sizeof pn.pfb, art);
    pn.peid[0] = 0;
    pn.pmatch = -1;
    if (strlen(eid) < sizeof pn.peid) pn_cat(pn.peid, sizeof pn.peid, eid);
    if (id[0]) {
        if (strlen(id) >= sizeof pn.pid) return PN_NOTFEED;
        pn_cat(pn.pid, sizeof pn.pid, id);
    } else if (strlen(url) >= sizeof pn.purl || !pn_cat(pn.purl, sizeof pn.purl, url))
        return PN_NOTFEED;
    pn.pcode = PN_OK;
    pn.pstate = 1;
    g = pn_spawn(pn_pmain, PN_KIND_PREVIEW);
    if (g) pn.pstate = 0;
    return g;
}

int pn_preview(const char *url, const char *id, const char *art) { return pn_preview_start(url, id, "", art, ""); }
int pn_preview_chart(const char *id, const char *cc, const char *eid) { return pn_preview_start("", id, cc, "", eid); }

/* ---- Subscribe */
int pn_subscribe(const char *root, const pc_show_t *shows, int nshows, char *dir, unsigned dsize) {
    pf_parser_t *p = pn.prev;
    char folder[PC_FILE], host[PC_FILE], path[PN_PATH], file[PN_PATH], tmp[PN_PATH], cover[PN_PATH];
    char *eps;
    unsigned n, fresh = 0;
    int made = 0, ok = 0;
    if (!p || !pn.purl[0]) return PN_NOTFEED;
    if (nshows >= PC_MAX_SHOWS || !m1_card_mounted()) return PN_STORAGE;
    eps = calloc(PN_EPS_MAX + 1, 1);
    if (!eps) return PN_MEM;
    (void)shows;
    pn_folder(pn.purl, folder, sizeof folder, host,
              sizeof host); /* the import's name: the host and the address' hash (only for a feed with no title) */
    if (pf_title(p)[0]) {
        char name[PC_FILE];
        pf_folder_name(name, sizeof name, pf_title(p));
        if (name[0]) {
            memcpy(folder, name, strlen(name) + 1);
            if (pn_join(path, sizeof path, root, folder, (const char *)0) &&
                !access(path, F_OK)) /* a folder of that name is someone else's: the import's name */
                pn_folder(pn.purl, folder, sizeof folder, host, sizeof host);
        }
    }
    mkdir(root, 0755);
    if (!pn_join(path, sizeof path, root, folder, (const char *)0) || !access(path, F_OK)) goto done;
    if (mkdir(path, 0755)) goto done;
    made = 1;
    if (!pn_join(file, sizeof file, path, ".episodes", (const char *)0) ||
        !pn_join(tmp, sizeof tmp, path, ".episodes.tmp", (const char *)0))
        goto done;
    n = pf_render_episodes(p, path, (const char *)0, 0, eps, PN_EPS_MAX, &fresh);
    pn_notes(path, p);
    if (!m1_save(file, tmp, 0644, eps, n)) goto done;
    pn_join(file, sizeof file, path, ".show", (const char *)0);
    pn_join(tmp, sizeof tmp, path, ".show.tmp", (const char *)0);
    n = pf_render_show(pf_title(p)[0] ? pf_title(p) : host, pn.purl, pf_image(p), (unsigned)time((long *)0), 0,
                       pf_author(p), pf_category(p), pf_summary(p), eps, PN_EPS_MAX);
    if (!m1_save(file, tmp, 0644, eps, n)) goto done;
    if (pn_join(cover, sizeof cover, path, "cover.jpg", (const char *)0))
        rename(PN_PREVIEW_COVER, cover); /* (no picture: the next refresh fetches it) */
    ok = 1;
done:
    free(eps);
    if (!ok) {
        if (made) { /* nothing is left behind */
            const char *own[] = {".episodes", ".episodes.tmp", ".show",    ".show.tmp",
                                 ".notes",    ".notes.tmp",    "cover.jpg"};
            unsigned i;
            for (i = 0; i < sizeof own / sizeof *own; ++i)
                if (pn_join(file, sizeof file, path, own[i], (const char *)0)) unlink(file);
            rmdir(path);
        }
        return PN_STORAGE;
    }
    if (dir) {
        dir[0] = 0;
        pn_cat(dir, dsize, folder);
    }
    pn_preview_drop();
    pn_bump();
    return PN_OK;
}

/* ---------------------------------------------------------------------------
 * Import
 */
static int pn_ws(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

/* The folder name of a new subscription: the host (letters, digits, dot and dash), a dash and the url's hash in hex. */
static void pn_folder(const char *url, char *out, unsigned size, char *host, unsigned hsize) {
    static const char hex[] = "0123456789abcdef";
    const char *h = url;
    unsigned o = 0, k;
    unsigned hash = pc_hash(url);
    while (*h && *h != '/') ++h; /* "http:" */
    while (*h == '/') ++h;
    for (k = 0; h[k] && h[k] != '/' && h[k] != ':' && h[k] != '?' && h[k] != '#' && k + 1 < hsize; ++k) host[k] = h[k];
    host[k] = 0;
    for (k = 0; host[k] && o + 12 < size && o < 40; ++k) {
        char c = host[k];
        out[o++] = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '.' || c == '-'
                       ? c
                       : '-';
    }
    out[o++] = '-';
    for (k = 0; k < 8; ++k) out[o++] = hex[hash >> (28 - 4 * k) & 15];
    out[o] = 0;
}

/* The addresses an import has taken so far (this call), and the room: one source after another shares them. */
struct pn_imp {
    const char *root;
    const pc_show_t *shows;
    int nshows, subs, added, nseen;
    unsigned seen[PC_MAX_SHOWS];
};

enum { PN_SUB_SKIP = 0, PN_SUB_ADDED = 1, PN_SUB_FULL = 2 };

/* One feed address (checked: http(s), shorter than PC_URL, no byte under 33; line is NUL terminated) as a subscription: the folder <host>-<hash8> with a .show (title: the name when there is one, else the host;
 * checked=0). A feed already subscribed or taken in this import is SKIP, as is a folder of that name that is already a subscription and a write that fails; with 40 shows PN_SUB_FULL. */
static int pn_sub_one(struct pn_imp *im, char *line, const char *name) {
    char dir[PC_FILE], host[PC_FILE], show[PN_PATH], file[PN_PATH], tmp[PN_PATH], text[PC_URL + PC_TITLE + 160];
    unsigned hash, n;
    int i, dup = 0;
    for (i = 0; i < im->nshows; ++i)
        if (!strcmp(im->shows[i].feed, line)) dup = 1;
    hash = pc_hash(line);
    for (i = 0; i < im->nseen; ++i)
        if (im->seen[i] == hash) dup = 1;
    if (dup) return PN_SUB_SKIP;
    if (im->subs >= PC_MAX_SHOWS) return PN_SUB_FULL;
    pn_folder(line, dir, sizeof dir, host, sizeof host);
    if (!pn_join(show, sizeof show, im->root, dir, (const char *)0)) return PN_SUB_SKIP;
    mkdir(show, 0755);
    if (!pn_join(file, sizeof file, show, ".show", (const char *)0) ||
        !pn_join(tmp, sizeof tmp, show, ".show.tmp", (const char *)0))
        return PN_SUB_SKIP;
    if (!access(file, F_OK)) return PN_SUB_SKIP; /* a folder of this name is already a subscription */
    n = pf_render_show(name && name[0] ? name : host, line, "", 0, 0, "", "", "", text, sizeof text);
    if (!m1_save(file, tmp, 0644, text, n)) return PN_SUB_SKIP;
    im->seen[im->nseen++] = hash;
    ++im->added, ++im->subs;
    return PN_SUB_ADDED;
}

/* The lines of subscriptions.txt: one http(s) address each, # comments; over-long, spaced and duplicate lines are skipped. */
static void pn_import_lines(struct pn_imp *im, char *buf, unsigned n) {
    char *p, *stop = buf + n;
    for (p = buf; p < stop;) {
        char *line = p, *e;
        unsigned len;
        int i, ok = 1;
        while (p < stop && *p != '\n') ++p;
        e = p;
        if (p < stop) ++p;
        while (line < e && pn_ws(*line)) ++line;
        while (e > line && pn_ws(e[-1])) --e;
        len = (unsigned)(e - line);
        if (!len || line[0] == '#') continue;
        if (!((len > 7 && pn_starts(line, "http://")) || (len > 8 && pn_starts(line, "https://"))) || len >= PC_URL)
            continue;
        for (i = 0; i < (int)len; ++i)
            if ((unsigned char)line[i] <= 32) ok = 0;
        if (!ok) continue;
        line[len] = 0;
        if (pn_sub_one(im, line, (const char *)0) == PN_SUB_FULL) break;
    }
}

/* The OPML files an import reads, into paths (PN_PATH each, at most max): Podcasts/subscriptions.opml, then every *.opml in the card's root, a dot file excepted (macOS leaves ._name.opml beside
 * each file it copies). Returns how many. */
static int pn_opml_files(const char *root, char (*paths)[PN_PATH], int max) {
    void *d;
    char *ent;
    int n = 0;
    if (pn_join(paths[n], PN_PATH, root, PN_OPML_FILE, (const char *)0) && !access(paths[n], F_OK)) ++n;
    d = opendir(PN_CARD);
    while (d && n < max && (ent = readdir(d)) != (char *)0) {
        const char *name = ent + PN_DNAME;
        unsigned len = strlen(name);
        if (len > 5 && name[0] != '.' && !strcasecmp(name + len - 5, ".opml") &&
            pn_join(paths[n], PN_PATH, PN_CARD, name, (const char *)0))
            ++n;
    }
    if (d) closedir(d);
    return n;
}

int pn_import_found(const char *root) {
    char txt[PN_PATH], paths[PN_OPML_MAX][PN_PATH];
    return (pn_join(txt, sizeof txt, root, PN_IMPORT_FILE, (const char *)0) && !access(txt, F_OK)) +
           pn_opml_files(root, paths, PN_OPML_MAX);
}

/* One OPML file: its outlines with a feed address as subscriptions. Renamed to <name>.imported when it held at least one and every one of them was seen (a cap that stopped it leaves the file
 * for a later import). Returns whether the file could be read. */
static int pn_import_opml(struct pn_imp *im, const char *path) {
    char *buf, to[PN_PATH];
    unsigned n;
    int items = 0, complete = 1;
    po_t p;
    po_item_t *it;
    buf = m1_read_file(path, PO_FILE_MAX, &n);
    if (!buf) return 0;
    it = calloc(1, sizeof *it);
    if (it) {
        po_open(&p, buf, n);
        while (po_next(&p, it)) {
            ++items;
            if (pn_sub_one(im, it->url, it->title) == PN_SUB_FULL) {
                complete = 0;
                break;
            }
        }
        free(it);
    } else
        complete = 0;
    free(buf);
    if (items && complete && pn_join(to, sizeof to, path, (const char *)0, (const char *)0) &&
        pn_cat(to, sizeof to, ".imported"))
        rename(path, to);
    return 1;
}

int pn_import(const char *root, const pc_show_t *shows, int nshows) {
    char path[PN_PATH], paths[PN_OPML_MAX][PN_PATH], *buf;
    unsigned n;
    int found = 0, i, nfiles;
    struct pn_imp *im = calloc(1, sizeof *im);
    if (!im) return -1;
    im->root = root, im->shows = shows, im->nshows = im->subs = nshows;
    if (pn_join(path, sizeof path, root, PN_IMPORT_FILE, (const char *)0) &&
        (buf = m1_read_file(path, PN_URLS_MAX, &n)) != (char *)0) {
        found = 1;
        pn_import_lines(im, buf, n);
        free(buf);
    }
    nfiles = pn_opml_files(root, paths, PN_OPML_MAX);
    for (i = 0; i < nfiles; ++i) found |= pn_import_opml(im, paths[i]);
    i = found ? im->added : -1;
    free(im);
    return i;
}

/* Export (the Subscriptions page's sheet): OPML 2.0 of every show with a feed, by title, into Podcasts/subscriptions-export.opml, atomically. *count is the number of shows written. 1 when written
 * (an export of no show is written too), 0 when it was not (no memory, a card that cannot be written). */
int pn_export(const char *root, const pc_show_t *shows, int nshows, int *count) {
    char file[PN_PATH], tmp[PN_PATH], *text;
    int order[PC_MAX_SHOWS], n = po_order(shows, nshows > PC_MAX_SHOWS ? PC_MAX_SHOWS : nshows, order), ok = 0;
    unsigned len;
    *count = 0;
    text = calloc(PO_EXPORT_MAX, 1);
    if (!text) return 0;
    len = po_render(shows, order, n, text, PO_EXPORT_MAX);
    if (len && pn_join(file, sizeof file, root, PN_EXPORT_FILE, (const char *)0) &&
        pn_join(tmp, sizeof tmp, root, "." PN_EXPORT_FILE ".tmp", (const char *)0) && m1_card_mounted() &&
        m1_save(file, tmp, 0644, text, len)) {
        ok = 1;
        *count = n;
    }
    free(text);
    return ok;
}

/* Unsubscribe (the Show page's sheet, docs/modules/podcasts.md "The Show page"): the show's .show again without its feed address, the rest as it was (title, picture, author, category,
 * description, last refresh), written atomically; the .episodes stay (the caller removes what else goes). UI thread; no worker runs a refresh of this show (the page is not refreshing).
 * 1 when written, 0 when the file could not be. */
int pn_unsubscribe(const char *root, const pc_show_t *s) {
    char file[PN_PATH], tmp[PN_PATH], text[PC_URL + PC_URL + 2 * PC_DESC + 320];
    unsigned n;
    if (!pn_join(file, sizeof file, root, s->dir, ".show") || !pn_join(tmp, sizeof tmp, root, s->dir, ".show.tmp"))
        return 0;
    n = pf_render_show(s->title, "", s->image, s->checked, s->modified, s->author, s->category, s->desc, text,
                       sizeof text);
    return m1_save(file, tmp, 0644, text, n);
}

/* Unsubscribe from a show without its page (the Subscriptions page's Unsubscribe, once for each marked show; the Show page's sheet does the same for the show open): pn_unsubscribe, then the .part files and the queued
 * downloads of the show go; with no episode file left on the card the show's own files (.show, .episodes, cover.jpg) and its folder (rmdir: one with anything else in it is left) go too. No audio file is ever
 * deleted, so the playing episode stays. 0: the .show could not be written (nothing else was touched); 1: the show stays on the card (episode files are left); 2: it is gone. */
int pn_unsubscribe_show(const char *root, const pc_show_t *s) {
    static const char *const own[] = {".show", ".episodes", ".archive", "cover.jpg"};
    char path[PN_PATH];
    pc_ep_t *all;
    int m, i, left = 0, cap = pc_all_cap(s); /* (the complete list: a .part of an archive-only episode goes too) */
    if (!pn_unsubscribe(root, s)) return 0;
    all = calloc((unsigned)cap, sizeof *all);
    if (!all) return 1; /* (what is left is not known: everything stays) */
    m = pc_load_show_all(s, all, cap);
    for (i = 0; i < m; ++i) {
        unsigned key;
        if (!all[i].file[0]) continue;
        key = pn_dl_key(s->dir, all[i].file);
        pn_dl_drop(key);
        if (pn_join(path, sizeof path, root, s->dir, all[i].file)) {
            /* (a download that finished since the list was read is an episode on the card: it stays, and so does the show) */
            if (all[i].state != PC_LOCAL && !access(path, F_OK)) ++left;
            if (pn_cat(path, sizeof path, ".part")) unlink(path);
        }
        pn_dl_clear(key);
        left += all[i].state == PC_LOCAL;
    }
    free(all);
    if (left) return 1;
    for (i = 0; i < (int)(sizeof own / sizeof *own); ++i)
        if (pn_join(path, sizeof path, root, s->dir, own[i])) unlink(path);
    if (pn_join(path, sizeof path, root, s->dir, (const char *)0)) rmdir(path);
    return 2;
}

/* ---------------------------------------------------------------------------
 * Software Update (patch/update.c is the page; docs/modules/update.md)
 *
 * Two jobs of the one worker slot (PN_KIND_UPDATE). The check asks GitHub where /releases/latest goes and reads the tag from that address: the answer is not followed and nothing else is read. The download fetches
 * that tag's update.bin (/releases/download/<tag>/update.bin, never "latest": the file is the version the page showed) into /mnt/mmc/update.bin.part, checks that the package says it is that version, and only
 * then renames it over update.bin. A failure removes the .part and leaves the card's update.bin as it was. Every request keeps verification on; the addresses, the verdict and https-only come from
 * patch/upver.c (GitHub, or the development channel).
 */

static unsigned pn_unull(char *d, unsigned size, unsigned nmemb, void *user) {
    (void)d, (void)user;
    return size * nmemb;
}

/* The job is over: the code, then the state, then the slot is free. */
static void pn_job_end(volatile int *st, volatile int *cd, int state, int code) {
    *cd = code;
    __sync_synchronize();
    *st = state;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
}
#define pn_up_end(state, code) pn_job_end(&pn.ustate, &pn.ucode, state, code)
#define pn_eq_end(state, code) pn_job_end(&pn.estate, &pn.ecode, state, code)

/* An address that is not https, or a redirect to one, is refused (upver.c says where the jobs ask). */
static void pn_up_https(net_req_t *r) {
    if (up_https_only()) r->flags |= NET_HTTPS;
}

struct un { /* the notes request's write callback's data: the answer, cut off at PN_UP_API_CAP */
    char *buf;
    unsigned total;
};

static unsigned pn_unwrite(char *d, unsigned size, unsigned nmemb, void *user) {
    struct un *x = user;
    unsigned len = size * nmemb, k;
    if (len > PN_UP_API_CAP - x->total) return 0; /* too big: the transfer fails (CURLE_WRITE_ERROR) */
    for (k = 0; k < len; ++k) x->buf[x->total + k] = d[k];
    x->total += len;
    return len;
}

/* The notes of the release the check just offered: GitHub's JSON of that tag (never "latest"), its top-level body for the screen, kept in pn.unotes. Only HTTP 200 counts; every failure (a 403 rate limit, a 404, the
 * network, a certificate, too big an answer, JSON without a body, null, empty) just leaves no notes: the offer stands. */
static void pn_up_notes_fetch(const char *tag) {
    char url[160], err[160];
    struct un x;
    net_req_t r;
    char *notes;
    x.total = 0;
    x.buf = calloc(PN_UP_API_CAP + 1, 1);
    notes = calloc(UP_NOTES_MAX + 1, 1);
    up_url(UP_URL_NOTES, tag, url, sizeof url);
    if (x.buf && notes) {
        pn_req(&r, url, pn_unwrite, &x, err, (void *)0);
        pn_up_https(&r);
        if (net_perform(&r) == 0 && r.http == 200 && !pn.cancel && up_notes(x.buf, x.total, notes, UP_NOTES_MAX + 1)) {
            pn.unotes = notes;
            notes = (char *)0;
        }
    }
    free(notes);
    free(x.buf);
}

static void pn_up_check_run(void) {
    char url[128], err[160], tag[UP_TAG], loc[PN_UP_LOC];
    net_req_t r;
    long http;
    int rc, code = PN_UPCHECK, res = 0;
    up_url(UP_URL_LATEST, "", url, sizeof url);
    pn_req(&r, url, pn_unull, (void *)0, err, (void *)0);
    r.flags |= NET_NOFOLLOW | NET_HEAD; /* the redirect's address is the answer */
    r.loc = loc, r.loc_size = sizeof loc;
    pn_up_https(&r);
    rc = net_perform(&r);
    if (rc == NET_NOHANDLE) {
        pn_up_end(PN_U_FAILED, PN_MEM);
        return;
    }
    http = r.http;
    if (rc == 0) {
        if (http == 301 || http == 302 || http == 303 || http == 307 || http == 308)
            res = up_latest(loc, tag, sizeof tag);
        if (res) code = PN_OK;
    } else {
        code = pn_rc(rc, http);
        if (code == PN_GONE || code == PN_HTTP) code = PN_UPCHECK; /* an HTTP error is no release news */
    }
    if (!pn.cancel && !code && res == 2) pn_up_notes_fetch(tag); /* (its failure is no failure of the check) */
    if (pn.cancel) {
        free(pn.unotes);
        pn.unotes = (char *)0;
        pn_up_end(PN_U_IDLE, PN_CANCELLED);
        return;
    }
    if (code) {
        pn_up_end(PN_U_FAILED, code);
        return;
    }
    pn.ures = res == 2 ? PN_U_AVAILABLE : PN_U_CURRENT;
    if (res == 2) memcpy((char *)pn.utag, tag, sizeof tag);
    pn_up_end(PN_U_CHECKED, PN_OK);
}

static void pn_up_download_run(void) {
    char url[160], err[160], tag[UP_TAG];
    net_file_t x; /* the package file: at most PN_UP_CAP bytes (patch/netfile.h) */
    net_req_t r;
    long http;
    long long clen;
    unsigned kb = 0;
    int rc, code = PN_OK, put = 0;
    memcpy(tag, (const char *)pn.utag, sizeof tag);
    memset(&x, 0, sizeof x);
    unlink(PN_UP_PART); /* nothing is resumed: the half file of another try is not trusted */
    x.fd = open(PN_UP_PART, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    x.cap = PN_UP_CAP;
    if (x.fd < 0) {
        pn_up_end(PN_U_FAILED, PN_STORAGE);
        return;
    }
    up_url(UP_URL_ASSET, tag, url, sizeof url);
    pn_req(&r, url, pn_fwrite, &x, err, (void *)0);
    r.total_s =
        0; /* no limit on the whole transfer (55 MB on a slow link); the low-speed limit still ends a stalled one */
    r.flags |= NET_NOENCODING; /* a package is sent as it is */
    pn_up_https(&r);
    rc = net_perform(&r);
    if (rc == NET_NOHANDLE) {
        close(x.fd);
        unlink(PN_UP_PART);
        pn_up_end(PN_U_FAILED, PN_MEM);
        return;
    }
    http = r.http, clen = r.length;
    if (rc) {
        if (x.why == NET_W_IO)
            code = pn_free_kb(PN_UP_DIR, &kb) && kb < 1024 ? PN_CARDFULL : PN_STORAGE;
        else
            code = x.why == NET_W_CAP ? PN_UPBAD : pn_rc(rc, http);
    } else if (http != 200 || x.written == 0 || (clen > 0 && clen != x.written))
        code = PN_UPBAD; /* not the whole answer */
    if (!net_file_close(&x) && !code) code = PN_STORAGE;
    if (!code && !up_info_ok(PN_UP_PART, tag)) code = PN_UPBAD; /* the package is not the version the page offered */
    if (!code) put = net_publish(PN_UP_PART, PN_UP_FILE, PN_UP_DIR);
    if (!code && !put) code = PN_STORAGE;
    if (code) {
        unlink(PN_UP_PART);
        pn_up_end(PN_U_FAILED, code);
        return;
    }
    code = put > 0 ? PN_OK : PN_STORAGE; /* (renamed, so the file stays; the page says the card is not right) */
    pn_up_end(code ? PN_U_FAILED : PN_U_DOWNLOADED, code);
}

static void *pn_umain(void *arg) {
    (void)arg;
    if (pn.umode)
        pn_up_download_run();
    else
        pn_up_check_run();
    return (void *)0;
}

/* The guards, then the worker. A guard that fails is the job's failure too, so the page reads one place. */
static int pn_up_start(int mode) {
    unsigned kb = 0;
    int g;
    if (pn.busy) return PN_BUSY;
    pn.ustage = mode + 1;
    g = pn_guard();
    if (!g && !mode && up_source() < 0) g = PN_UPCHECK; /* a channel file that names no address */
    if (!g && mode) {
        if (pn.ures != PN_U_AVAILABLE || !up_tag_ok((const char *)pn.utag))
            g = PN_UPCHECK; /* no release was offered */
        else if (!pn_free_kb(PN_UP_DIR, &kb))
            g = PN_STORAGE;
        else if (kb < PN_UP_NEED_KB)
            g = PN_CARDFULL;
    }
    if (g) {
        pn.ucode = g;
        __sync_synchronize();
        pn.ustate = PN_U_FAILED;
        pn_bump();
        return g;
    }
    if (!mode) {
        pn.ures = 0, pn.utag[0] = 0; /* a new check forgets the offer and its notes */
        free(pn.unotes);
        pn.unotes = (char *)0;
    }
    pn.umode = mode, pn.ucode = 0;
    __sync_synchronize();
    pn.ustate = mode ? PN_U_DOWNLOADING : PN_U_CHECKING;
    g = pn_spawn(pn_umain, PN_KIND_UPDATE);
    if (g) {
        pn.ucode = g;
        __sync_synchronize();
        pn.ustate = PN_U_FAILED;
    }
    return g;
}

void pn_up_reset(void) {
    if (pn.busy || (pn.ustate == PN_U_DOWNLOADED && !access(PN_UP_FILE, F_OK))) return;
    pn.ustate = PN_U_IDLE, pn.ures = 0, pn.ucode = 0, pn.utag[0] = 0;
    free(pn.unotes);
    pn.unotes = (char *)0;
}
const char *pn_up_notes(void) { return pn.ures == PN_U_AVAILABLE && pn.unotes ? pn.unotes : ""; }
int pn_up_check(void) { return pn_up_start(0); }
int pn_up_download(void) { return pn_up_start(1); }
int pn_up_state(void) { return pn.ustate; }
int pn_up_code(void) { return pn.ucode; }
int pn_up_stage(void) { return pn.ustage; }
int pn_up_result(void) { return pn.ures; }
const char *pn_up_tag(void) { return pn.ures ? (const char *)pn.utag : ""; }
unsigned pn_up_pct(void) { return pn.part >= 1000 ? 100 : pn.part / 10; }

/* ---------------------------------------------------------------------------
 * AutoEq (docs/modules/peq.md "AutoEq download"): the index of the project's results, and one headphone's ParametricEQ.txt. Two modes of one worker in the job slot, the update's way: written to a part file under
 * PN_EQ_DIR, checked, and only then made the file the page reads (the list renamed over index.md here; a preset left at PN_EQ_PRESET for the page to parse and move into the card's EQ folder). Every request keeps verification on
 * and allows https only.
 */
static const char PN_EQ_HEAD[] = "# Index";
struct ex { /* the write callback's data */
    int fd, werr, capped, bad, check;
    unsigned total, cap, head; /* head: the bytes of the heading seen so far */
};

static unsigned pn_ewrite(char *d, unsigned size, unsigned nmemb, void *user) {
    struct ex *x = user;
    unsigned len = size * nmemb, at = 0;
    if (x->check &&
        x->head <
            sizeof PN_EQ_HEAD -
                1) { /* the list starts with its heading (it may arrive in pieces): an answer that is a web page or a redirect is not the list */
        while (at < len && x->head < sizeof PN_EQ_HEAD - 1) {
            if (d[at] != PN_EQ_HEAD[x->head]) {
                x->bad = 1;
                return 0;
            }
            ++at, ++x->head;
        }
        at = 0;
    }
    if (len > x->cap - x->total) {
        x->capped = 1;
        return 0;
    }
    if (!m1_write_all(x->fd, d, len)) {
        x->werr = 1;
        return 0;
    }
    x->total += len;
    return len;
}

static void pn_eq_run(void) {
    char url[PN_PATH + 160], err[160];
    const char *part = pn.emode ? PN_EQ_PRESET : PN_EQ_PART, *name;
    struct ex x;
    long http = 0;
    unsigned kb = 0, base = 0; /* base: the bytes of the stamp, which are not the answer */
    int rc, code = PN_OK;
    net_req_t r;
    memset(&x, 0, sizeof x);
    x.check = !pn.emode, x.cap = pn.emode ? PN_EQ_FILE_CAP : PN_EQ_INDEX_CAP;
    mkdir("/mnt/mmc/.m1plus", 0755);
    mkdir(PN_EQ_DIR, 0755);
    unlink(part);
    x.fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (x.fd < 0) {
        pn_eq_end(PN_E_FAILED, PN_STORAGE);
        return;
    }
    if (pn.emode) { /* the first line of the file, the entry it came from (the page finds the file again by it) */
        unsigned n = 0;
        while (pn.estamp[n]) ++n;
        if (!m1_write_all(x.fd, pn.estamp, n) || write(x.fd, "\n", 1) != 1) x.werr = 1;
        x.total = base = n + 1;
        for (name = pn.epath; *name; ++name) {
        }
        while (name > pn.epath && name[-1] != '/') --name; /* the folder and the file carry the same name */
        snprintf(url, sizeof url, "%s%s/%s%%20ParametricEQ.txt", PN_EQ_BASE, pn.epath, name);
    } else
        snprintf(url, sizeof url, "%sINDEX.md", PN_EQ_BASE);
    pn_req(&r, url, pn_ewrite, &x, err, (void *)0);
    pn_up_https(&r);
    rc = x.werr ? NET_NOHANDLE : net_perform(&r);
    if (rc == NET_NOHANDLE) {
        close(x.fd);
        unlink(part);
        pn_eq_end(PN_E_FAILED, x.werr ? PN_STORAGE : PN_MEM);
        return;
    }
    http = r.http;
    if (rc) {
        if (x.werr)
            code = pn_free_kb(PN_EQ_DIR, &kb) && kb < 1024 ? PN_CARDFULL : PN_STORAGE;
        else
            code = x.bad || x.capped ? PN_NOTFEED : pn_rc(rc, http);
    } else if (http != 200 || x.total <= base || (x.check && x.head < sizeof PN_EQ_HEAD - 1))
        code = PN_NOTFEED; /* (a body that ended inside the heading is not the list) */
    if (!code && fsync(x.fd)) code = PN_STORAGE;
    if (close(x.fd) && !code) code = PN_STORAGE;
    if (!code && !pn.emode && rename(PN_EQ_PART, PN_EQ_INDEX)) code = PN_STORAGE;
    if (!code &&
        !pn.emode) { /* the day it came, for the page's age rule (a failed write only makes the next open ask again) */
        char day[16];
        int n = snprintf(day, sizeof day, "%u\n", (unsigned)time((long *)0));
        m1_save(PN_EQ_STAMP, PN_EQ_STAMP ".part", 0644, day, (unsigned)n);
    }
    if (code || !pn.emode) unlink(part); /* (a renamed list has no part file left) */
    pn_eq_end(code ? PN_E_FAILED : PN_E_DONE, code);
}

static void *pn_emain(void *arg) {
    (void)arg;
    pn_eq_run();
    return (void *)0;
}

/* The place of a preset below PN_EQ_BASE as the index writes it ("Source/Kind/Name"): printable, no spaces, no dot segments, nothing that is an address of its own. */
static int pn_eq_path_ok(const char *p) {
    unsigned n = 0, seg = 0, slashes = 0;
    for (; p[n]; ++n) {
        unsigned char c = (unsigned char)p[n];
        if (c <= ' ' || c >= 0x7f || c == '"' || c == '\\' || c == '?' || c == '#') return 0;
        if (c == '/') {
            if (!seg) return 0;
            seg = 0, ++slashes;
        } else if (++seg == 1 && p[n] == '.' &&
                   (p[n + 1] == '/' || !p[n + 1] || (p[n + 1] == '.' && (p[n + 2] == '/' || !p[n + 2]))))
            return 0;
    }
    return n && n < PN_PATH && seg && slashes == 2 && p[0] != ':' && !pn_starts(p, "http");
}

static int pn_eq_start(int mode, const char *path, const char *stamp) {
    int g;
    if (pn.busy) return PN_BUSY;
    if (mode && (!path || !stamp || !pn_eq_path_ok(path) || strlen(stamp) >= sizeof pn.estamp)) return PN_NOFEED;
    g = pn_guard();
    if (!g) {
        pn.emode = mode;
        if (mode) {
            pn.epath[0] = 0;
            pn_cat(pn.epath, sizeof pn.epath, path);
            pn.estamp[0] = 0;
            pn_cat(pn.estamp, sizeof pn.estamp, stamp);
        }
        pn.ecode = 0;
        __sync_synchronize();
        pn.estate = PN_E_RUNNING;
        g = pn_spawn(pn_emain, PN_KIND_EQ);
    }
    if (g) {
        pn.emode = mode;
        pn.ecode = g;
        __sync_synchronize();
        pn.estate = PN_E_FAILED;
        pn_bump();
    }
    return g;
}

int pn_eq_index(void) { return pn_eq_start(0, (const char *)0, (const char *)0); }
int pn_eq_get(const char *path, const char *stamp) { return pn_eq_start(1, path, stamp); }
int pn_eq_state(void) { return pn.estate; }
int pn_eq_code(void) { return pn.ecode; }
int pn_eq_mode(void) { return pn.emode; }
void pn_eq_reset(void) {
    if (!pn.busy) pn.estate = PN_E_IDLE, pn.ecode = 0;
}

/* ---------------------------------------------------------------------------
 * All episodes (docs/modules/podcasts.md "All episodes")
 *
 * One job of the worker slot (PN_KIND_ARCH): the show's feed is fetched again and every enclosed item (at most PC_ARCH_MAX, PC_ARCH_BYTES) is written as a line of the show's .archive, in the .episodes format, as the parser
 * reads it (pf_set_sink: nothing is held; the sink writes). An item whose guid the show's .episodes has takes that line's file name and description, so a downloaded episode keeps its file; the others are named as a refresh names them
 * (pf_item_file, a number when two of one day have one title: the names are looked up by their hash). The text goes to .archive.tmp and replaces .archive at the end (m1_commit); a failed or cancelled job leaves none.
 */
#define PN_ARCH_CAP 33554432u /* a feed this large (decoded) is parsed up to here and cut */
#define PN_ARCH_OUT 16384
#define PN_ARCH_TRIES 3 /* requests for the feed before its error shows (as the charts) */
#define PN_ARCH_WAIT 1 /* seconds between two of them */
#define PN_ARCH_LIMIT 300 /* seconds for one request */

struct ax {
    int fd, werr, full, capped;
    unsigned n, bytes, used, nknown;
    unsigned long long total;
    pc_ep_t *known; /* the .episodes entries: guid hash, file name, description */
    unsigned *names; /* pc_hash of every file name written (PC_ARCH_MAX) */
    char *out; /* PN_ARCH_OUT bytes waiting for their write */
    pf_parser_t *p;
};

static int pn_ax_flush(struct ax *x) {
    if (x->used && !m1_write_all(x->fd, x->out, x->used)) x->werr = 1;
    x->used = 0;
    return !x->werr;
}

static int pn_ax_sink(void *ctx, const pf_item_t *it) {
    struct ax *x = ctx;
    char f[PC_FILE], od[PC_DESC], ln[1536];
    unsigned g, i, lo, h, tries;
    if (x->full || x->werr) return 0;
    if (x->n >= PC_ARCH_MAX) return x->full = 1, 0;
    f[0] = od[0] = 0;
    g = pc_guid_hash(it->guid, strlen(it->guid));
    for (i = 0; i < x->nknown; ++i)
        if (x->known[i].guid == g) {
            memcpy(f, x->known[i].file, sizeof f), memcpy(od, x->known[i].desc, sizeof od);
            break;
        }
    for (tries = 1; !f[0] && tries < 10;
         ++tries) { /* a name no earlier line has (the .episodes names are the earlier lines' own) */
        pf_item_file(it, tries, f, sizeof f);
        h = pc_hash(f);
        for (i = 0; i < x->n; ++i)
            if (x->names[i] == h) {
                f[0] = 0;
                break;
            }
    }
    if (!f[0]) pf_item_file(it, 1, f, sizeof f); /* (ten of one day and one title: the last two share a name) */
    lo = pf_item_line(it, f, od, ln, sizeof ln);
    if (x->bytes + lo > PC_ARCH_BYTES) return x->full = 1, 0;
    if (x->used + lo > PN_ARCH_OUT && !pn_ax_flush(x)) return 0;
    memcpy(x->out + x->used, ln, lo);
    x->used += lo, x->bytes += lo;
    x->names[x->n++] = pc_hash(f);
    pn.arn = x->n; /* (the page's count) */
    return 1;
}

static unsigned pn_ax_write(char *d, unsigned size, unsigned nmemb, void *user) {
    struct ax *x = user;
    unsigned len = size * nmemb;
    if (x->full || x->werr) return 0; /* (the archive is complete, or the card failed: the transfer stops) */
    if (x->total + len > PN_ARCH_CAP) {
        pf_push(x->p, d, (unsigned)(PN_ARCH_CAP - x->total));
        x->total = PN_ARCH_CAP, x->capped = 1;
        return 0;
    }
    x->total += len;
    pf_push(x->p, d, len);
    return x->full || x->werr ? 0 : len;
}

/* One attempt at the feed: a fresh .archive.tmp and parser, the count back at 0, the transfer; the temp file replaces dst (m1_commit) when the attempt succeeded and is removed when it did not. *retry: the failure may pass (the network,
 * a time-out, a stall, a 5xx, 408, 429); a 404, a page that is not a feed, storage, memory and a cancel are final. */
static int pn_arch_try(struct ax *x, const char *feed, const char *tmp, const char *dst, int *retry) {
    char err[160];
    net_req_t r;
    long http = 0;
    int rc = 0, code = 0, ok;
    *retry = 0;
    x->werr = x->full = x->capped = 0;
    x->n = x->bytes = x->used = 0;
    x->total = 0;
    pn.arn = 0;
    x->p = pf_new();
    x->fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (!x->p)
        code = PN_MEM;
    else if (x->fd < 0 || !m1_write_all(x->fd, "M1PLUS-EPISODES 1\n", 18))
        code = PN_STORAGE;
    else {
        pf_set_sink(x->p, pn_ax_sink, x);
        pn_req(&r, feed, pn_ax_write, x, err, (void *)0);
        r.total_s = PN_ARCH_LIMIT; /* (a feed of two thousand items is 10 MB and more) */
        r.low_limit = 1,
        r.low_time = PN_DL_STALL; /* a stall: under 1 byte a second for PN_DL_STALL seconds, as the downloads */
        rc = net_perform(&r);
        http = r.http;
        if (rc == NET_NOHANDLE)
            code = PN_MEM;
        else {
            if (x->werr)
                code = PN_STORAGE;
            else if (rc == 0 || (rc == CURLE_WRITE_ERROR && (x->full || x->capped)))
                code = pf_is_feed(x->p) ? PN_OK : PN_NOTFEED;
            else
                code = pn_rc(rc, http);
            if (!code && !x->n) code = PN_NOTFEED; /* (a feed with no enclosed item gives no archive) */
            if (code == PN_NET || (rc == CURLE_HTTP_RETURNED_ERROR && net_http_passing(http))) *retry = 1;
        }
    }
    if (!code && pn.cancel) code = PN_CANCELLED; /* (it arrived all the same: a cancel leaves no archive) */
    if (x->fd >= 0) {
        ok = !code && pn_ax_flush(x) && m1_card_mounted();
        if (!m1_commit(x->fd, ok, tmp, dst) && !code) code = PN_STORAGE;
        x->fd = -1;
    }
    pf_free(x->p);
    x->p = (pf_parser_t *)0;
    return code;
}

#define pn_arch_end(state, code) pn_job_end(&pn.arstate, &pn.arcode, state, code)

static void pn_arch_run(void) {
    struct ax x;
    char dir[PN_PATH], file[PN_PATH], tmp[PN_PATH], dst[PN_PATH];
    char *buf;
    unsigned n = 0;
    pc_show_t s;
    int code = 0, attempt, retry = 0;
    memset(&x, 0, sizeof x);
    memset(&s, 0, sizeof s);
    x.fd = -1;
    if (!pn_join(dir, sizeof dir, pn.arroot, pn.ardir, (const char *)0) ||
        !pn_join(file, sizeof file, dir, ".show", (const char *)0))
        return pn_arch_end(PN_AR_FAILED, PN_STORAGE);
    buf = m1_read_file(file, PN_SHOW_MAX, &n);
    if (!buf) return pn_arch_end(PN_AR_FAILED, PN_STORAGE);
    pc_parse_show(buf, n, &s);
    free(buf);
    if (!s.feed[0]) return pn_arch_end(PN_AR_FAILED, PN_NOTFEED);
    x.known = calloc(PC_MAX_EPS, sizeof *x.known);
    x.names = calloc(PC_ARCH_MAX + 1, sizeof *x.names);
    x.out = calloc(1, PN_ARCH_OUT);
    if (!x.known || !x.names || !x.out)
        code = PN_MEM;
    else if (!m1_card_mounted() || !pn_join(file, sizeof file, dir, ".episodes", (const char *)0) ||
             !pn_join(tmp, sizeof tmp, dir, ".archive.tmp", (const char *)0) ||
             !pn_join(dst, sizeof dst, dir, ".archive", (const char *)0))
        code = PN_STORAGE;
    if (!code) {
        buf = m1_read_file(file, PN_EPS_MAX, &n);
        if (buf) x.nknown = (unsigned)pc_parse_eps(buf, n, x.known, PC_MAX_EPS);
        free(buf);
        for (attempt = 0; attempt < PN_ARCH_TRIES; ++attempt) {
            if (pn.cancel) {
                code = PN_CANCELLED;
                break;
            }
            code = pn_arch_try(&x, s.feed, tmp, dst, &retry);
            if (!code || !retry) break;
            if (attempt + 1 < PN_ARCH_TRIES && !pn.cancel) sleep(PN_ARCH_WAIT);
        }
    }
    free(x.known);
    free(x.names);
    free(x.out);
    if (code && code != PN_CANCELLED)
        pn.arfc = code, pn.arfh = pn.arhash;
    else if (pn.arfh == pn.arhash)
        pn.arfh = 0; /* (a success or a cancel: nothing to retry) */
    pn_arch_end(code ? PN_AR_FAILED : PN_AR_DONE, code);
}

static void *pn_armain(void *arg) {
    (void)arg;
    pn_arch_run();
    return (void *)0;
}

int pn_arch_start(const char *root, const pc_show_t *s) {
    int g;
    if (pn.busy) return PN_BUSY;
    if (!s->feed[0]) return PN_NOFEED;
    g = pn_guard();
    if (g) return g;
    pn.arroot[0] = pn.ardir[0] = 0;
    pn_cat(pn.arroot, sizeof pn.arroot, root);
    pn_cat(pn.ardir, sizeof pn.ardir, s->dir);
    pn.arhash = s->hash, pn.arcode = 0, pn.arn = 0;
    if (pn.arfh == s->hash) pn.arfh = 0;
    __sync_synchronize();
    pn.arstate = PN_AR_RUNNING;
    g = pn_spawn(pn_armain, PN_KIND_ARCH);
    if (g) pn.arstate = PN_AR_IDLE;
    return g;
}
int pn_arch_state(void) { return pn.arstate; }
int pn_arch_code(void) { return pn.arcode; }
int pn_arch_failed(unsigned hash) { return pn.arfh == hash ? pn.arfc : 0; }
unsigned pn_arch_count(void) { return pn.arn; }
unsigned pn_arch_hash(void) { return pn.arhash; }
void pn_arch_reset(void) {
    if (!pn.busy) pn.arstate = PN_AR_IDLE, pn.arcode = 0;
}
