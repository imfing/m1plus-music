/* M1+ Music Podcasts on the network: import, refresh one show or all (docs/modules/podcasts.md "Feeds").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * See patch/pcnet.h. One detached worker thread per job: for each show it reads the show file's feed url, streams the feed through libcurl into the push parser (patch/pcfeed.c;
 * verification ON with the CA bundle on the card, redirects followed, gzip accepted, time-outs and a size cap on every request), then writes .episodes and .show atomically (a temp file,
 * fsync, rename) and records the result. The thread touches no widget and calls no stock function; the status record is plain words the page reads on its own timer (a store barrier
 * before the generation counter moves). Only demo's own imports are used (libcurl's easy interface, pthread_create / pthread_detach, open / write / fsync / rename / access).
 *
 * Episode downloads (pn_dl_*, "Downloads" below) run on the same kind of thread, one at a time and never beside a refresh. The download policy follows q2-podcasts (MIT licence,
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
#include "covercache.h"

#define PN_PATH 400
#define PN_SHOW_MAX 4096 /* bytes of a show file read */
#define PN_URLS_MAX 16384 /* bytes of subscriptions.txt read */
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
    /* Downloads (new fields go below the ones the tests poke). kind: what the running thread does (PN_KIND_*); dpause: the page asked the download thread to stop for a refresh; dcancel: key of the download
     * the page cancelled; dkey / dgot / dtotal / dwait: the one being fetched; dgen / dstep: progress steps; dseq: the queue's order; fails: the words of the failed ones. The page writes slot
     * fields and the thread reads them (a barrier, then the state); the state moves only by compare-and-swap. */
    volatile int kind, dpause, dwait;
    volatile unsigned dcancel, dkey, dgot, dtotal, dgen, dstep, dseq, nfail;
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
    /* Software Update (docs/modules/update.md; new fields go below). ustate: PN_U_*; ucode: the PN_* of a failure; ustage: what the last failure or the running job was (1 the check, 2 the download); ures: the check's verdict
     * (PN_U_CURRENT, PN_U_AVAILABLE, 0 none); umode: 0 the worker checks, 1 it downloads; utag: the release the check offered (held for the download). The state is written after the code and the tag. */
    volatile int ustate, ucode, ustage, ures, umode;
    char utag[UP_TAG];
    char *
        unotes; /* the offered release's notes (heap, UP_NOTES_MAX + 1 bytes, set by the check before its state, freed by the next check), NULL for none */
} pn __attribute__((section(".scratch")));

enum {
    PN_KIND_REFRESH = 1,
    PN_KIND_DL = 2,
    PN_KIND_SEARCH = 3,
    PN_KIND_PREVIEW = 4,
    PN_KIND_ART = 5,
    PN_KIND_PICK = 6,
    PN_KIND_UPDATE = 7
};
enum { PN_Q_FREE = 0, PN_Q_WAIT = 1, PN_Q_ACTIVE = 2 };

static int pn_eq(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

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

static void pn_bump(void) {
    __sync_synchronize();
    ++pn.gen;
}

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
                       pn.kind == PN_KIND_PICK || pn.kind == PN_KIND_UPDATE);
}
void pn_cancel(void) { pn.cancel = 1; }
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
    if (!pod_card_mounted()) return PN_STORAGE;
    if (get_wifisignal() <= 0) return PN_NOWIFI;
    if ((unsigned)time((long *)0) < PN_MIN_EPOCH) return PN_NOCLOCK;
    if (access(PN_CA, F_OK)) return PN_NOCERT;
    return PN_OK;
}

/* ---------------------------------------------------------------------------
 * Files
 */

/* Up to cap bytes of a file into a heap buffer (a NUL after them); NULL when it is missing or empty. */
static char *pn_slurp(const char *path, unsigned cap, unsigned *n) {
    char *buf;
    int fd = open(path, O_RDONLY, 0), got = 0, r;
    if (fd < 0) return (char *)0;
    buf = calloc(cap + 1, 1);
    while (buf && (unsigned)got < cap && (r = read(fd, buf + got, cap - (unsigned)got)) > 0) got += r;
    close(fd);
    if (!buf || got <= 0) {
        free(buf);
        return (char *)0;
    }
    *n = (unsigned)got;
    return buf;
}

/* data into path atomically: written to tmp, fsynced, renamed over path. 1 on success; a failure leaves no temp file. */
static int pn_save(const char *path, const char *tmp, const char *data, unsigned n) {
    unsigned at = 0;
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644), ok = fd >= 0;
    while (ok && at < n) {
        int w = write(fd, data + at, n - at);
        if (w <= 0)
            ok = 0;
        else
            at += (unsigned)w;
    }
    ok = ok && fsync(fd) == 0;
    if (fd >= 0) ok = close(fd) == 0 && ok;
    if (ok && rename(tmp, path)) ok = 0;
    if (!ok) unlink(tmp);
    return ok;
}

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
    void *h;
    char *buf; /* PN_DL_BUF bytes waiting for their chunk write */
    unsigned used, have, base, key, seen,
        bad; /* have: bytes of the episode got (on the card and in buf); base: where this request's data starts; bad: the PN_* the callbacks refused with */
    char part[PN_PATH];
    char dir[PN_PATH];
    char err[160];
};

/* A download is to stop: the page cancelled it, or asked the thread to pause for a refresh. */
static int pn_dl_stopped(unsigned key) { return pn.dcancel == key || pn.dpause; }

static int pn_xfer(void *user, long long dt, long long dn, long long ut, long long un) {
    unsigned t, n, p;
    (void)ut, (void)un;
    if (user) { /* a download: stop on the page's say; the length the server announced (what follows base) is the total */
        struct dx *d = user;
        if (pn_dl_stopped(d->key)) return 1;
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

/* A configured easy handle for url (NULL: no memory): every request of the worker, feed or picture, is made with these options. Verification stays ON: no SSL_VERIFYPEER / SSL_VERIFYHOST
 * option is ever set. */
static void *pn_easy(const char *url, unsigned (*write_cb)(char *, unsigned, unsigned, void *), void *user, char *err,
                     void *xdata) {
    void *h = curl_easy_init();
    if (!h) return h;
    curl_easy_setopt(h, CURLOPT_URL, url);
    curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(h, CURLOPT_WRITEDATA, user);
    curl_easy_setopt(h, CURLOPT_ERRORBUFFER, err);
    curl_easy_setopt(h, CURLOPT_NOPROGRESS,
                     0); /* the transfer-info callback below: the dialog's progress and its Cancel */
    curl_easy_setopt(h, CURLOPT_XFERINFOFUNCTION, pn_xfer);
    curl_easy_setopt(h, CURLOPT_XFERINFODATA, xdata); /* 0: a refresh's request; the attempt of a download otherwise */
    curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1); /* a thread: no SIGALRM resolver time-outs */
    curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 1);
    curl_easy_setopt(h, CURLOPT_MAXREDIRS, 16); /* tracking chains reach 8 hops (podtrac, Art19 through 4 counters) */
    curl_easy_setopt(h, CURLOPT_PROTOCOLS, CURLPROTO_HTTP_HTTPS); /* a redirect to file:// or ftp:// is refused */
    curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
    curl_easy_setopt(h, CURLOPT_FAILONERROR, 1);
    curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT, 20);
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_LIMIT, 1000);
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_TIME, 30);
    curl_easy_setopt(h, CURLOPT_TIMEOUT, 120);
    curl_easy_setopt(
        h, CURLOPT_USERAGENT,
        "M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)"); /* LRCLIB asks for the app's name and its address */
    curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING,
                     ""); /* every encoding libcurl has (gzip: a 3 MB feed is 400 kB on the wire) */
    curl_easy_setopt(h, CURLOPT_CAINFO, PN_CA);
    return h;
}

/* The PN_* code of a finished libcurl request that did not succeed (rc != 0), from curl's result and the HTTP code. */
static int pn_rc(int rc, long http) {
    if (rc == CURLE_HTTP_RETURNED_ERROR) return http == 404 || http == 410 ? PN_GONE : PN_HTTP;
    if (rc == CURLE_ABORTED_BY_CALLBACK) return PN_CANCELLED;
    if (rc == CURLE_SSL_CACERT || rc == CURLE_SSL_CONNECT_ERROR || rc == CURLE_PEER_FAILED_VERIFICATION ||
        rc == CURLE_SSL_CERTPROBLEM || rc == CURLE_SSL_CIPHER || rc == CURLE_SSL_ISSUER_ERROR)
        return PN_CERT;
    if (rc == CURLE_SSL_CACERT_BADFILE) return PN_NOCERT;
    return PN_NET;
}

#define PN_NOTMOD \
    100 /* pn_fetch: HTTP 304, the feed is as the last refresh left it (not an error, not a PN_ code of the page) */

/* The feed at url through the parser. since: the server's own Last-Modified of the copy we hold (.show's modified=, never the device clock), 0 for no condition (If-Modified-Since). *modified: the
 * server's Last-Modified of this answer (CURLINFO_FILETIME), 0 when it sent none. Returns a PN_* code (PN_OK: the answer was a feed; PN_NOTMOD: 304). */
static int pn_fetch(const char *url, pf_parser_t *p, long since, unsigned *modified) {
    struct fx f;
    void *h;
    long http = 0, ft = -1;
    int rc;
    memset(&f, 0, sizeof f);
    f.p = p;
    *modified = 0;
    h = pn_easy(url, pn_write, &f, f.err, (void *)0);
    if (!h) return PN_MEM;
    curl_easy_setopt(h, CURLOPT_FILETIME, 1); /* the Last-Modified header, read back below */
    if (since) {
        curl_easy_setopt(h, CURLOPT_TIMECONDITION, CURL_TIMECOND_IFMODSINCE);
        curl_easy_setopt(h, CURLOPT_TIMEVALUE, since);
    }
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_getinfo(h, CURLINFO_FILETIME, &ft);
    if (ft > 0) *modified = (unsigned)ft;
    curl_easy_cleanup(h);
    if (rc == 0 && http == 304 && since) return PN_NOTMOD;
    if (rc == 0) return pf_is_feed(p) ? PN_OK : PN_NOTFEED;
    if (rc == CURLE_WRITE_ERROR) return f.capped && pf_is_feed(p) && pf_items(p) > 0 ? PN_OK : PN_NOTFEED;
    return pn_rc(rc, http);
}

/* ---------------------------------------------------------------------------
 * The cover picture (docs/modules/podcasts.md "Cover art")
 */
struct cx {
    int fd;
    unsigned total, cap;
};

static unsigned pn_cwrite(char *d, unsigned size, unsigned nmemb, void *user) {
    struct cx *c = user;
    unsigned len = size * nmemb, at = 0;
    if (len > c->cap || c->total > c->cap - len) return 0; /* a write error: the transfer stops */
    c->total += len;
    while (at < len) {
        int w = write(c->fd, d + at, len - at);
        if (w <= 0) return 0;
        at += (unsigned)w;
    }
    return len;
}

/* The picture at url into the file path (a plain file, not yet a cover), at most cap bytes. 1 when the whole answer was written; else 0 and no file. */
static int pn_fetch_file(const char *url, const char *path, unsigned cap) {
    struct cx c;
    char err[160];
    void *h;
    int rc, ok;
    c.fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    c.total = 0, c.cap = cap;
    if (c.fd < 0) return 0;
    h = pn_easy(url, pn_cwrite, &c, err, (void *)0);
    rc = h ? curl_easy_perform(h) : -1;
    if (h) curl_easy_cleanup(h);
    ok = close(c.fd) == 0 && rc == 0 && c.total > 0;
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
    buf = pn_slurp(file, PN_SHOW_MAX, &n);
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
            if (!pn_save(file, tmp, txt, n))
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
            old = pn_slurp(file, PN_EPS_MAX, &oldn);
            n = pf_render_episodes(p, path, old, oldn, eps, PN_EPS_MAX, &fresh);
            first = s.checked == 0;
            pn_notes(path, p);
            pn_join(tmp, sizeof tmp, path, ".episodes.tmp", (const char *)0);
            if (!pn_save(file, tmp, eps, n))
                code = PN_STORAGE;
            else { /* the show file: the feed's title the first time (the import wrote the host), its picture url; the time of this refresh */
                pn_join(file, sizeof file, path, ".show", (const char *)0);
                pn_join(tmp, sizeof tmp, path, ".show.tmp", (const char *)0);
                memcpy(shown, first && pf_title(p)[0] ? pf_title(p) : s.title, PC_TITLE);
                n = pf_render_show(
                    shown, s.feed, pf_image(p)[0] ? pf_image(p) : s.image, (unsigned)time((long *)0),
                    modified, /* the new answer's Last-Modified; 0 (none sent) drops the key: the next request is unconditional */
                    pf_author(p)[0] ? pf_author(p) : s.author, pf_category(p)[0] ? pf_category(p) : s.category,
                    pf_summary(p)[0] ? pf_summary(p) : s.desc, eps, PN_EPS_MAX);
                if (!pn_save(file, tmp, eps, n))
                    code = PN_STORAGE;
                else {
                    if (pn.part < 900) pn.part = 900;
                    if (first &&
                        !old) { /* nothing of the folder is anyone's yet: it takes the show's name instead of the import's */
                        char name[PC_FILE], to[PN_PATH];
                        pf_folder_name(name, sizeof name, shown);
                        if (name[0] && !pn_eq(name, dir) && pn_join(to, sizeof to, j->root, name, (const char *)0) &&
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
    curl_global_init(
        CURL_GLOBAL_ALL); /* counted, and not thread safe: made here, on the UI thread (stock's own curl_init did it once already) */
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
static unsigned pn_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static int pn_cat(char *out, unsigned size, const char *s) {
    unsigned o = pn_len(out), k;
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
    memcpy(pn.fails[i].dir, dir, pn_len(dir) + 1);
    memcpy(pn.fails[i].file, file, pn_len(file) + 1);
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

/* KB free for a non-root user on the file system of path (MIPS o32 statfs: f_bsize is word 1, f_bavail word 7); 0 when statfs fails. */
int pn_free_kb(const char *path, unsigned *kb) {
    unsigned fs[32];
    unsigned long long b;
    memset(fs, 0, sizeof fs);
    if (statfs(path, fs)) return 0;
    b = (unsigned long long)fs[7] * fs[1] >> 10;
    *kb = b > 0xffffffffull ? 0xffffffffu : (unsigned)b;
    return 1;
}

/* A page instead of audio: any Content-Type of text/..., in any case. */
static int pn_is_text(const char *t) {
    return t && (t[0] | 32) == 't' && (t[1] | 32) == 'e' && (t[2] | 32) == 'x' && (t[3] | 32) == 't' && t[4] == '/';
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
    unsigned kb, at = 0;
    int fd, ok = 1;
    if (!d->used) return 1;
    if (!pn_free_kb(d->dir, &kb)) return d->bad = PN_STORAGE, 0;
    if (kb < PN_DL_MARGIN_KB || kb - PN_DL_MARGIN_KB < (d->used >> 10)) return d->bad = PN_CARDFULL, 0;
    fd = open(d->part, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) return d->bad = PN_STORAGE, 0;
    while (at < d->used) {
        int w = write(fd, d->buf + at, d->used - at);
        if (w <= 0) {
            ok = 0;
            break;
        }
        at += (unsigned)w;
    }
    ok = ok && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (!ok) return d->bad = PN_STORAGE, 0;
    d->used = 0;
    return 1;
}

static unsigned pn_dwrite(char *data, unsigned size, unsigned nmemb, void *user) {
    struct dx *d = user;
    unsigned len = size * nmemb, at = 0;
    if (!d->seen) { /* the first bytes: the headers are in */
        long code = 0;
        const char *ctype = (const char *)0;
        d->seen = 1;
        curl_easy_getinfo(d->h, CURLINFO_RESPONSE_CODE, &code);
        curl_easy_getinfo(d->h, CURLINFO_CONTENT_TYPE, &ctype);
        if (pn_is_text(ctype)) return d->bad = PN_NOTAUDIO, 0;
        if (d->base && code != 206) { /* the server ignored the Range: the file starts again */
            int fd = open(d->part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd < 0 || close(fd)) return d->bad = PN_STORAGE, 0;
            d->base = d->have = 0;
        }
    }
    if (pn_dl_stopped(d->key)) return 0; /* a write error ends the transfer; the caller knows why */
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

/* One request for the rest of the episode (a Range from the bytes the file has). Returns PN_OK (the whole answer arrived), PN_CANCELLED / PN_PAUSED (the page's say), or the failure; *retry: worth trying
 * again after a wait (the network, a 5xx); *again: the server refused the range (416, a range error): the file may start again, once. The bytes got are on the card when this returns. */
static int pn_dl_attempt(struct dx *d, const char *url, int *retry, int *again) {
    void *h;
    char range[16];
    long http = 0;
    int rc;
    d->seen = d->bad = 0, d->base = d->have, d->used = 0;
    h = pn_easy(url, pn_dwrite, d, d->err, d);
    if (!h) return PN_MEM;
    d->h = h;
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_LIMIT, 1); /* a stall: under 1 byte a second for PN_DL_STALL seconds */
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_TIME, PN_DL_STALL);
    curl_easy_setopt(h, CURLOPT_TIMEOUT, 0); /* no limit on the whole transfer */
    curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING,
                     "identity"); /* audio is sent as it is: a range of an encoded body would not resume */
    if (d->have) {
        pc_fmt(range, sizeof range, "%d-", d->have);
        curl_easy_setopt(h, CURLOPT_RANGE, range);
    }
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_cleanup(h);
    d->h = (void *)0;
    if (!d->bad)
        pn_dflush(d); /* what arrived goes to the card whatever ended the transfer: the next attempt resumes after it */
    if (d->bad) return d->bad;
    if (rc == 0) return d->have ? PN_OK : PN_HTTP; /* an empty answer is no episode */
    if (pn_dl_stopped(d->key)) return pn.dcancel == d->key ? PN_CANCELLED : PN_PAUSED;
    if (rc == CURLE_HTTP_RETURNED_ERROR) {
        if (http == 404 || http == 410) return PN_GONE;
        if (http == 416) *again = 1;
        if (http >= 500 || http == 408 || http == 429) *retry = 1;
        return PN_HTTP;
    }
    if (rc == CURLE_RANGE_ERROR) return *again = 1, PN_HTTP;
    if (rc == CURLE_SSL_CACERT || rc == CURLE_SSL_CONNECT_ERROR || rc == CURLE_PEER_FAILED_VERIFICATION ||
        rc == CURLE_SSL_CERTPROBLEM || rc == CURLE_SSL_CIPHER || rc == CURLE_SSL_ISSUER_ERROR)
        return PN_CERT;
    if (rc == CURLE_SSL_CACERT_BADFILE) return PN_NOCERT;
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

/* The slot's episode, to the end: PN_OK when the file is in place, PN_CANCELLED / PN_PAUSED for the page's say, else the failure. */
static int pn_dl_run(struct dx *d, const char *show, const char *name, unsigned key) {
    char file[PN_PATH], eps_path[PN_PATH], url[PF_URL];
    char *eps;
    unsigned n = 0, length = 0, tries = 0, start, kb, i;
    int code, retry, again, restarted = 0;
    if (!pn_join(d->dir, sizeof d->dir, pn.droot, show, (const char *)0) ||
        !pn_join(file, sizeof file, d->dir, name, (const char *)0) || pn_len(file) + sizeof(".part") > PN_DL_PATH_MAX)
        return PN_STORAGE;
    memcpy(d->part, file, pn_len(file) + 1);
    pn_cat(d->part, sizeof d->part, ".part");
    d->key = key;
    if (!access(file, F_OK)) { /* it is on the card already: nothing to fetch, a leftover .part goes */
        unlink(d->part);
        return PN_OK;
    }
    pn_join(eps_path, sizeof eps_path, d->dir, ".episodes", (const char *)0);
    eps = pn_slurp(eps_path, PN_EPS_MAX, &n);
    i = eps && pf_find_episode(eps, n, name, url, sizeof url, &length);
    free(eps);
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
        if (!pn_free_kb(d->dir, &kb)) {
            code = PN_STORAGE;
            break;
        }
        if (length > start &&
            kb < PN_DL_MARGIN_KB + ((length - start) >> 10)) { /* the rest of the file would eat into the margin */
            code = PN_CARDFULL;
            break;
        }
        retry = again = 0;
        code = pn_dl_attempt(d, url, &retry, &again);
        if (code == PN_OK) {
            if (rename(d->part, file)) code = PN_STORAGE;
            break;
        }
        if (code == PN_CANCELLED || code == PN_PAUSED) break;
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
        for (i = 0; i < n && !pn_dl_stopped(key); ++i) sleep(1);
        pn.dwait = 0;
        if (pn_dl_stopped(key)) {
            code = pn.dcancel == key ? PN_CANCELLED : PN_PAUSED;
            break;
        }
    }
    if (code != PN_OK && (!pn_part_size(d->part, &start) || !start))
        unlink(d->part); /* nothing on the card: no file to say "Paused" */
    free(d->buf);
    return code;
}

/* The worker: the queued downloads in the order they were asked, one at a time, until none is left (or the page asked it to pause for a refresh: then the queue stays). */
static void *pn_dmain(void *arg) {
    int i;
    (void)arg;
    while (!pn.dpause && (i = pn_next_slot()) >= 0) {
        unsigned key = pn.q[i].key;
        struct dx *d;
        int code;
        if (!__sync_bool_compare_and_swap(&pn.q[i].state, PN_Q_WAIT, PN_Q_ACTIVE)) continue; /* the page took it back */
        pn.dkey = key, pn.dgot = pn.dtotal = 0, pn.dwait = 0;
        pn_bump();
        d = calloc(1, sizeof *d);
        code = d ? pn_dl_run(d, pn.q[i].dir, pn.q[i].file, key) : PN_MEM;
        free(d);
        if (code == PN_PAUSED)
            pn.q[i].state = PN_Q_WAIT;
        else {
            if (code != PN_OK && code != PN_CANCELLED) pn_fail_set(key, code, pn.q[i].dir, pn.q[i].file);
            if (pn.dcancel == key) pn.dcancel = 0;
            pn.q[i].state = PN_Q_FREE;
        }
        pn.dkey = 0;
        pn_bump();
    }
    pn.dpause = 0;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
    return (void *)0;
}

int pn_dl_start(void) {
    unsigned long th = 0;
    int g, i;
    if (pn.busy || pn_next_slot() < 0)
        return PN_OK; /* a worker is on it (a refresh: the page starts this again when it ends) */
    g = pn_guard();
    if (g) { /* the downloads cannot start: they fail now, with the words of the guard on their rows */
        for (i = 0; i < PN_QMAX; ++i)
            if (pn.q[i].state == PN_Q_WAIT) {
                unsigned key = pn.q[i].key;
                if (__sync_bool_compare_and_swap(&pn.q[i].state, PN_Q_WAIT, PN_Q_FREE))
                    pn_fail_set(key, g, pn.q[i].dir, pn.q[i].file);
            }
        pn_bump();
        return g;
    }
    curl_global_init(CURL_GLOBAL_ALL);
    pn.busy = 1, pn.kind = PN_KIND_DL, pn.dpause = 0;
    pn_bump();
    if (pthread_create(&th, (const void *)0, pn_dmain, (void *)0)) {
        pn.kind = 0;
        pn.busy = 0;
        pn_bump();
        return PN_MEM;
    }
    pthread_detach(th);
    return PN_OK;
}

int pn_dl_add(const char *root, const char *dir, const char *file) {
    unsigned key = pn_dl_key(dir, file), i;
    int free_slot = -1, g;
    char path[PN_PATH];
    if (!key || !file[0] || !pn_join(path, sizeof path, root, dir, file) ||
        pn_len(path) + sizeof(".part") > PN_DL_PATH_MAX)
        return PN_STORAGE;
    for (i = 0; i < PN_QMAX; ++i) {
        if (pn.q[i].state != PN_Q_FREE && pn.q[i].key == key) {
            if (pn.dcancel == key) pn.dcancel = 0; /* asked again before the worker took the cancel: it goes on */
            return PN_OK;
        }
        if (pn.q[i].state == PN_Q_FREE && free_slot < 0) free_slot = (int)i;
    }
    g = pn_guard();
    if (g) return g;
    if (free_slot < 0) return PN_QFULL;
    pn_fail_clear(key);
    if (!pn_eq(pn.droot, root)) pn_join(pn.droot, sizeof pn.droot, root, (const char *)0, (const char *)0);
    memcpy(pn.q[free_slot].dir, dir, pn_len(dir) + 1);
    memcpy(pn.q[free_slot].file, file, pn_len(file) + 1);
    pn.q[free_slot].key = key;
    pn.q[free_slot].seq = ++pn.dseq;
    __sync_synchronize();
    pn.q[free_slot].state = PN_Q_WAIT;
    pn_bump();
    return pn_dl_start();
}

void pn_dl_cancel(unsigned key) {
    int i;
    for (i = 0; i < PN_QMAX; ++i) {
        if (pn.q[i].key != key) continue;
        if (pn.q[i].state == PN_Q_WAIT && __sync_bool_compare_and_swap(&pn.q[i].state, PN_Q_WAIT, PN_Q_FREE)) {
            pn_bump();
            return;
        }
        if (pn.q[i].state == PN_Q_ACTIVE) pn.dcancel = key; /* the worker aborts the transfer and drops it */
    }
}

void pn_dl_pause(void) {
    if (pn_dl_running()) pn.dpause = 1;
}

int pn_dl_running(void) { return pn.busy && pn.kind == PN_KIND_DL; }

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
            if (pn.q[i].state == PN_Q_WAIT || pn.dwait) return PN_DL_WAIT;
            if (pn.dcancel == key) return PN_DL_NONE; /* cancelled: the worker is about to drop it */
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
            memcpy(dir, pn.q[best].dir, pn_len(pn.q[best].dir) + 1);
            memcpy(file, pn.q[best].file, pn_len(pn.q[best].file) + 1);
            *code = 0;
            return pn.q[best].key;
        }
        last = pn.q[best].seq, have = 1;
    }
    n -= k;
    for (i = 0; i < PN_FAILS; ++i) /* then the failed ones */
        if (pn.fails[i].key && n-- == 0) {
            memcpy(dir, pn.fails[i].dir, pn_len(pn.fails[i].dir) + 1);
            memcpy(file, pn.fails[i].file, pn_len(pn.fails[i].file) + 1);
            *code = pn.fails[i].code;
            return pn.fails[i].key;
        }
    return 0;
}

/* ---------------------------------------------------------------------------
 * Search (docs/modules/podcasts.md "Search")
 *
 * One worker job under the same rule as a refresh and the downloads: one thread at a time. The query (the store's JSON, at most PN_JSON_CAP bytes, taken apart by pj_results into pn.sres), then the
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
    static const char hex[] = "0123456789ABCDEF";
    unsigned o = pn_len(out);
    for (; *s; ++s) {
        unsigned char c = (unsigned char)*s;
        int plain = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '-' ||
                    c == '_' || c == '.' || c == '~';
        if (o + (plain ? 1 : 3) + 1 > size) return 0;
        if (plain)
            out[o++] = (char)c;
        else
            out[o++] = '%', out[o++] = hex[c >> 4], out[o++] = hex[c & 15];
    }
    out[o] = 0;
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
static int pn_fetch_json_once(const char *url, char *buf, unsigned *got, long *http_out) {
    struct jx f;
    void *h;
    long http = 0;
    int rc;
    memset(&f, 0, sizeof f);
    f.buf = buf;
    h = pn_easy(url, pn_jwrite, &f, f.err, (void *)0);
    if (!h) return PN_MEM;
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_cleanup(h);
    *got = f.n;
    if (http_out) *http_out = http;
    if (rc == 0 || (rc == CURLE_WRITE_ERROR && f.capped)) return PN_OK;
    return pn_rc(rc, http);
}

static int pn_fetch_json_raw(const char *url, char *buf, unsigned *got) {
    return pn_fetch_json_once(url, buf, got, (long *)0);
}

/* The answer at url of a lookup service, one request, never repeated (a failure shows at once and the page's Try Again asks again). A busy answer (HTTP 503 or 429: LRCLIB under load answers uncached queries so) is
 * PN_OVERLOAD. The other codes as pn_fetch_json_raw (a 404 is PN_GONE). */
static int pn_fetch_json_api(const char *url, char *buf, unsigned *got) {
    long http = 0;
    int code = pn_fetch_json_once(url, buf, got, &http);
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
    curl_global_init(CURL_GLOBAL_ALL);
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
    int kind;
    const char *url = pn.sres[i].art;
    if ((pn_starts(url, "http://") || pn_starts(url, "https://")) && pn_thumb_path(i, "src", src, sizeof src) &&
        pn_fetch_file(url, src, PN_THUMB_CAP)) {
        kind = pc_pic_info(src, &w, &h, &sof);
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
    if (!pn_cat(pn.surl, sizeof pn.surl, PN_SEARCH_URL) || !pn_urlenc(pn.surl, sizeof pn.surl, term)) return PN_MEM;
    pn.scode = PN_OK;
    pn.sstate = PN_S_QUERY;
    ++pn.sgen;
    g = pn_spawn(pn_smain, PN_KIND_SEARCH);
    if (g) pn.sstate = PN_S_IDLE;
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
    return pn_slurp(path, PN_LRC_CAP, n);
}

int pn_art_full_path(int i, char *path, unsigned size) {
    if (i < 0 || i >= pn.an || pn.fidx != i + 1 || !pn.fext) return 0;
    path[0] = 0;
    return pn_cat(path, size, PN_ART_DIR) && pn_cat(path, size, pn.fext == 2 ? "/full.png" : "/full.jpg");
}

int pn_art_full(const char *thumb, char *out, unsigned size) {
    static const char *const from[2] = {"100x100bb", "250x250-"}, *const to[2] = {"600x600bb", "500x500-"};
    unsigned n = pn_len(thumb), i;
    int k;
    if (n + 1 > size) return 0;
    memcpy(out, thumb, n + 1);
    for (k = 0; k < 2; ++k)
        for (i = 0; i < n; ++i)
            if (pn_starts(thumb + i, from[k])) {
                memcpy(out + i, to[k], pn_len(to[k])); /* the same length: the address is changed in place */
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
    unsigned n = pn_len(text);
    int i, slot = pn.ln;
    if (slot >= PN_LYR_MAX) return 0;
    for (i = 0; i < slot; ++i) {
        const pn_lyr_t *c = &pn.lcand[i];
        if (c->secs == r->secs && c->synced == r->synced && pn_eq(c->title, r->title) && pn_eq(c->artist, r->artist) &&
            pn_eq(c->album, r->album))
            return 1;
    }
    pn_art_dir();
    if (!pn_lyr_path(slot, path, sizeof path) || !pn_save(path, PN_ART_DIR "/lyrics.tmp", text, n)) {
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
        if (buf) code = pn_art_covers(buf);
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
    return pn_art_run(PN_PART_COVERS | PN_PART_LYRICS);
}

int pn_art_again(int part) {
    if (pn.busy) return PN_BUSY;
    if (part != PN_PART_COVERS && part != PN_PART_LYRICS) return PN_MEM;
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
            char *data = pn_slurp(src, PN_PICK_CAP, &n);
            char stmp[PN_PATH];
            stmp[0] = 0;
            if (data && pn_join(stmp, sizeof stmp, pn.pkdir, ".cover.tmp", (const char *)0))
                pn_save(side, stmp, data, n);
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

int pn_lyr_save(int i, const char *path) {
    unsigned n = 0;
    char tmp[PN_PATH];
    char *data = pn_lyr_text(i, &n);
    int ok;
    tmp[0] = 0;
    ok = data && pn_cat(tmp, sizeof tmp, path) && pn_cat(tmp, sizeof tmp, ".tmp") && pod_card_mounted() &&
         pn_save(path, tmp, data, n);
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
const char *pn_preview_feed(void) { return pn.purl; }
int pn_preview_cover(void) { return !access(PN_PREVIEW_COVER, F_OK); }

/* The preview's picture: downloaded, shrunk (the Show page's own path: pv_shrink, pv_shrink_png) to PN_PREVIEW_COVER. Whatever fails leaves no file; the preview has the placeholder. */
static void pn_preview_picture(const char *url) {
    static const char src[] = PN_SEARCH_DIR "/preview.src", tmp[] = PN_SEARCH_DIR "/preview.tmp";
    unsigned w, h, sof;
    int kind, ok = 0;
    if (!pn_starts(url, "http://") && !pn_starts(url, "https://")) return;
    if (!pn_fetch_file(url, src, PN_COVER_CAP)) return;
    kind = pc_pic_info(src, &w, &h, &sof);
    if (kind == 1)
        ok = pv_shrink(src, tmp) && !rename(tmp, PN_PREVIEW_COVER);
    else if (kind == 2)
        ok = pv_shrink_png(src, tmp) > 0 && !rename(tmp, PN_PREVIEW_COVER);
    (void)ok;
    unlink(tmp);
    unlink(src);
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
        pn_cat(url, sizeof url, PN_LOOKUP_URL);
        pn_cat(url, sizeof url, pn.pid);
        if (!buf || !r)
            code = PN_MEM;
        else if ((code = pn_fetch_json(url, buf, &got)) == PN_OK) {
            if (pj_results(buf, got, r, 1) < 1 || !r->feed[0])
                code = PN_NOFEED;
            else
                memcpy(feed, r->feed, sizeof feed);
        }
        free(buf);
        free(r);
    } else
        memcpy(feed, pn.purl, sizeof feed);
    if (code == PN_OK) {
        p = pf_new();
        code = p ? pn_fetch(feed, p, 0, &unused) : PN_MEM;
    }
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

int pn_preview(const char *url, const char *id) {
    int g;
    if (pn.busy) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    pn_search_dir();
    pn_preview_drop();
    pn.purl[0] = 0;
    pn.pid[0] = 0;
    if (id[0]) {
        if (pn_len(id) >= sizeof pn.pid) return PN_NOTFEED;
        pn_cat(pn.pid, sizeof pn.pid, id);
    } else if (pn_len(url) >= sizeof pn.purl || !pn_cat(pn.purl, sizeof pn.purl, url))
        return PN_NOTFEED;
    pn.pcode = PN_OK;
    pn.pstate = 1;
    g = pn_spawn(pn_pmain, PN_KIND_PREVIEW);
    if (g) pn.pstate = 0;
    return g;
}

/* ---- Subscribe */
int pn_subscribe(const char *root, const pc_show_t *shows, int nshows, char *dir, unsigned dsize) {
    pf_parser_t *p = pn.prev;
    char folder[PC_FILE], host[PC_FILE], path[PN_PATH], file[PN_PATH], tmp[PN_PATH], cover[PN_PATH];
    char *eps;
    unsigned n, fresh = 0;
    int made = 0, ok = 0;
    if (!p || !pn.purl[0]) return PN_NOTFEED;
    if (nshows >= PC_MAX_SHOWS || !pod_card_mounted()) return PN_STORAGE;
    eps = calloc(PN_EPS_MAX + 1, 1);
    if (!eps) return PN_MEM;
    (void)shows;
    pn_folder(pn.purl, folder, sizeof folder, host,
              sizeof host); /* the import's name: the host and the address' hash (only for a feed with no title) */
    if (pf_title(p)[0]) {
        char name[PC_FILE];
        pf_folder_name(name, sizeof name, pf_title(p));
        if (name[0]) {
            memcpy(folder, name, pn_len(name) + 1);
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
    if (!pn_save(file, tmp, eps, n)) goto done;
    pn_join(file, sizeof file, path, ".show", (const char *)0);
    pn_join(tmp, sizeof tmp, path, ".show.tmp", (const char *)0);
    n = pf_render_show(pf_title(p)[0] ? pf_title(p) : host, pn.purl, pf_image(p), (unsigned)time((long *)0), 0,
                       pf_author(p), pf_category(p), pf_summary(p), eps, PN_EPS_MAX);
    if (!pn_save(file, tmp, eps, n)) goto done;
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
        if (pn_eq(im->shows[i].feed, line)) dup = 1;
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
    if (!pn_save(file, tmp, text, n)) return PN_SUB_SKIP;
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
        unsigned len = pn_len(name);
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
    buf = pn_slurp(path, PO_FILE_MAX, &n);
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
        (buf = pn_slurp(path, PN_URLS_MAX, &n)) != (char *)0) {
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
        pn_join(tmp, sizeof tmp, root, "." PN_EXPORT_FILE ".tmp", (const char *)0) && pod_card_mounted() &&
        pn_save(file, tmp, text, len)) {
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
    return pn_save(file, tmp, text, n);
}

/* Unsubscribe from a show without its page (the Subscriptions page's Unsubscribe, once for each marked show; the Show page's sheet does the same for the show open): pn_unsubscribe, then the .part files and the queued
 * downloads of the show go; with no episode file left on the card the show's own files (.show, .episodes, cover.jpg) and its folder (rmdir: one with anything else in it is left) go too. No audio file is ever
 * deleted, so the playing episode stays. 0: the .show could not be written (nothing else was touched); 1: the show stays on the card (episode files are left); 2: it is gone. */
int pn_unsubscribe_show(const char *root, const pc_show_t *s) {
    static const char *const own[] = {".show", ".episodes", "cover.jpg"};
    char path[PN_PATH];
    pc_ep_t *all;
    int m, i, left = 0;
    if (!pn_unsubscribe(root, s)) return 0;
    all = calloc(PC_MAX_EPS, sizeof *all);
    if (!all) return 1; /* (what is left is not known: everything stays) */
    m = pc_load_show(s, all, PC_MAX_EPS);
    for (i = 0; i < m; ++i) {
        unsigned key;
        if (!all[i].file[0]) continue;
        key = pn_dl_key(s->dir, all[i].file);
        pn_dl_cancel(key);
        if (pn_join(path, sizeof path, root, s->dir, all[i].file) && pn_cat(path, sizeof path, ".part")) unlink(path);
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

struct ux { /* the download's write callback's data */
    int fd, werr, capped;
    unsigned total;
};

static unsigned pn_uwrite(char *d, unsigned size, unsigned nmemb, void *user) {
    struct ux *x = user;
    unsigned len = size * nmemb, at = 0;
    if (len > PN_UP_CAP - x->total) {
        x->capped = 1;
        return 0;
    }
    while (at < len) {
        int w = write(x->fd, d + at, len - at);
        if (w <= 0) {
            x->werr = 1;
            return 0;
        }
        at += (unsigned)w;
    }
    x->total += len;
    return len;
}

/* The job is over: the code, then the state, then the slot is free. */
static void pn_up_end(int state, int code) {
    pn.ucode = code;
    __sync_synchronize();
    pn.ustate = state;
    pn.stopped = pn.cancel;
    pn.kind = 0;
    pn.busy = 0;
    pn_bump();
}

static void pn_up_https(void *h) {
    if (!up_https_only()) return; /* (upver.c says where the jobs ask) */
    curl_easy_setopt(h, CURLOPT_PROTOCOLS,
                     CURLPROTO_HTTPS); /* an address that is not https, or a redirect to one, is refused */
    curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTPS);
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
    long http = 0;
    int rc;
    void *h;
    char *notes;
    x.total = 0;
    x.buf = calloc(PN_UP_API_CAP + 1, 1);
    notes = calloc(UP_NOTES_MAX + 1, 1);
    up_url(UP_URL_NOTES, tag, url, sizeof url);
    h = x.buf && notes ? pn_easy(url, pn_unwrite, &x, err, (void *)0) : (void *)0;
    if (h) {
        pn_up_https(h);
        rc = curl_easy_perform(h);
        curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
        curl_easy_cleanup(h);
        if (rc == 0 && http == 200 && !pn.cancel && up_notes(x.buf, x.total, notes, UP_NOTES_MAX + 1)) {
            pn.unotes = notes;
            notes = (char *)0;
        }
    }
    free(notes);
    free(x.buf);
}

static void pn_up_check_run(void) {
    char url[128], err[160], tag[UP_TAG];
    const char *loc = (const char *)0;
    long http = 0;
    int rc, code = PN_UPCHECK, res = 0;
    void *h;
    up_url(UP_URL_LATEST, "", url, sizeof url);
    h = pn_easy(url, pn_unull, (void *)0, err, (void *)0);
    if (!h) {
        pn_up_end(PN_U_FAILED, PN_MEM);
        return;
    }
    curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 0); /* the redirect's address is the answer */
    curl_easy_setopt(h, CURLOPT_NOBODY, 1);
    pn_up_https(h);
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_getinfo(h, CURLINFO_REDIRECT_URL, &loc);
    if (rc == 0) {
        if (http == 301 || http == 302 || http == 303 || http == 307 || http == 308)
            res = up_latest(loc, tag, sizeof tag);
        if (res) code = PN_OK;
    } else {
        code = pn_rc(rc, http);
        if (code == PN_GONE || code == PN_HTTP) code = PN_UPCHECK; /* an HTTP error is no release news */
    }
    curl_easy_cleanup(h);
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

/* The card's root directory made durable after the rename. */
static int pn_up_sync_dir(void) {
    int fd = open(PN_UP_DIR, O_RDONLY, 0), ok;
    if (fd < 0) return 0;
    ok = fsync(fd) == 0;
    close(fd);
    return ok;
}

static void pn_up_download_run(void) {
    char url[160], err[160], tag[UP_TAG];
    struct ux x;
    long http = 0;
    long long clen = -1;
    unsigned kb = 0;
    int rc, code = PN_OK;
    void *h;
    memcpy(tag, (const char *)pn.utag, sizeof tag);
    memset(&x, 0, sizeof x);
    unlink(PN_UP_PART); /* nothing is resumed: the half file of another try is not trusted */
    x.fd = open(PN_UP_PART, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (x.fd < 0) {
        pn_up_end(PN_U_FAILED, PN_STORAGE);
        return;
    }
    up_url(UP_URL_ASSET, tag, url, sizeof url);
    h = pn_easy(url, pn_uwrite, &x, err, (void *)0);
    if (!h) {
        close(x.fd);
        unlink(PN_UP_PART);
        pn_up_end(PN_U_FAILED, PN_MEM);
        return;
    }
    curl_easy_setopt(
        h, CURLOPT_TIMEOUT,
        0); /* no limit on the whole transfer (55 MB on a slow link); the low-speed limit still ends a stalled one */
    curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING, (void *)0); /* a package is sent as it is */
    pn_up_https(h);
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &http);
    curl_easy_getinfo(h, CURLINFO_CONTENT_LENGTH_DOWNLOAD_T, &clen);
    curl_easy_cleanup(h);
    if (rc) {
        if (x.werr)
            code = pn_free_kb(PN_UP_DIR, &kb) && kb < 1024 ? PN_CARDFULL : PN_STORAGE;
        else
            code = x.capped ? PN_UPBAD : pn_rc(rc, http);
    } else if (http != 200 || x.total == 0 || (clen > 0 && (unsigned long long)clen != x.total))
        code = PN_UPBAD; /* not the whole answer */
    if (!code && fsync(x.fd)) code = PN_STORAGE;
    if (close(x.fd) && !code) code = PN_STORAGE;
    if (!code && !up_info_ok(PN_UP_PART, tag)) code = PN_UPBAD; /* the package is not the version the page offered */
    if (!code && rename(PN_UP_PART, PN_UP_FILE)) code = PN_STORAGE;
    if (code) {
        unlink(PN_UP_PART);
        pn_up_end(PN_U_FAILED, code);
        return;
    }
    code =
        pn_up_sync_dir() ? PN_OK : PN_STORAGE; /* (renamed, so the file stays; the page says the card is not right) */
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
