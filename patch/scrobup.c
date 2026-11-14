/* M1+ Music scrobble upload: the card's .scrobbler.log sent to ListenBrainz and Last.fm on one worker thread, through demo's libcurl (docs/modules/scrobble.md "Upload").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The line rules, the batches, the archive and the log's rewrite follow q2-pod (patch/scrobble.c, docs/internals.md "Scrobbling"); the log is rewritten once an upload, not once a batch.
 *
 * No hook, no timer, nothing on the boot path: nothing here runs unless scrobup_start is called (the UI thread: the settings pages of patch/scrobpage.c, owner SCROBUP_UI, or
 * the automatic upload of patch/scrobble.c, owner SCROBUP_AUTO; each polls only the job it started). The thread
 *   reads the log SU_WIN bytes at a time under the log's lock (scrobble_lock, the lock of the UI thread's append) and takes its whole lines: a comment, a line over SU_LINE,
 *     one not rated L, one without an artist, a title or a time of 1 to 10 digits from SU_TIME_MIN on is skipped;
 *   sends the others SU_BATCH (or SU_RAW bytes of them) at a time, with no lock held: su_flush, to every service that is set up and not refused (su_lb_batch, su_lf_batch).
 *     ListenBrainz: a batch counts on HTTP 200; one the service refuses for good (400) is sent again one listen a request, and only the listens that are refused alone are
 *     refused. Last.fm: one signed form a batch, its answer says which listens it ignored. A listen leaves the log once every one of those services took it or refused it
 *     for good: for the archive when one took it, set aside when all refused it. Any other answer, or the kill switch seen between two requests, ends the upload;
 *   then, once, under the lock (su_retire): the log's bytes as far as the last listen that was answered 200 or 400 (skipped lines with them) are appended to SU_SENT, those
 *     of the refused listens to SU_REJECTED, both less the comments, and the log becomes the header and what follows those bytes (SU_TMP, then a rename). The new log is
 *     written first, so a full card fails before an archive gains anything; the archives are synced before the rename drops the lines. A listen appended meanwhile is
 *     behind those bytes, so it stays.
 * A failure of an archive or the rewrite leaves the log as it was: the listens go again with the next upload (the service drops a listen it has).
 *
 * The account (the UI thread): the card's SU_INI is its only store, nothing of it is on flash. Its [LISTENBRAINZ] section holds TOKEN= and, once the service has
 * confirmed the token, USER= (a display cache). The user writes TOKEN= on a computer: nothing here sets a token. A valid check's USER= is the device's only write to the file, in place,
 * every other byte kept (su_ini_set); there is no sign-out here: the user takes the token out of the file.
 * scrobup_account keeps what was read in RAM until scrobup_forget, a write or a start, so a file edited on a computer is seen by the next page that opens, the next
 * start and the automatic upload's next look without a usable token. scrobup_check_start asks the service (validate-token) on the same one thread, so an upload and a
 * check never run together; the poll that takes a valid answer writes the name.
 * Last.fm's account is the same file's [LASTFM] section (USER=, PASSWORD=, API_KEY=, API_SECRET=, all the user's, never written here). Its session
 * key is asked of the service when a job needs one and kept in RAM only, with the credentials it was made from.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "curlopts.h"
#include "pcjson.h"
#include "scrobble.h"
#include "scrobup.h"

#define SU_LB_URL "https://api.listenbrainz.org/1/submit-listens"
#define SU_LB_CHECK "https://api.listenbrainz.org/1/validate-token"
#define SU_SENT SC_LOG ".sent"
#define SU_REJECTED SC_LOG ".rejected"
#define SU_TMP SC_LOG ".tmp"
#define SU_LF_URL "https://ws.audioscrobbler.com/2.0/"
#define SU_INI \
    "/mnt/mmc/scrobble.ini" /* the accounts, on the card only: [LISTENBRAINZ] TOKEN= and USER=, [LASTFM] USER=, PASSWORD=, API_KEY= and API_SECRET= */
#define SU_INI_TMP SU_INI ".tmp"
#define SU_INI_ROOM 256 /* what an edit adds at most: a USER line of SU_NAME with a line end before and behind it */
#define SU_KEYS 4 /* the most keys a section has */
#define SU_AUTH "Authorization: Token "
#define SU_ENOENT 2 /* errno: no such file (the same number on MIPS o32) */
#define SU_HASH0 2166136261u /* su_hash of no bytes */
#define SU_REJECT (-4) /* a sender's answer, never a result: the service refused the batch for good (400) */
#define SU_RENEW (-5) /* Last.fm's answer, never a result: the session key is not valid (error 9) */
#define SU_LF_LIMIT \
    5 /* Last.fm's ignoredMessage code "daily scrobble limit exceeded": the only one that is not for good */

/* The Last.fm credentials, as the card's file has them. */
typedef struct {
    char user[SU_NAME], pass[SU_LF_PASS + 1], key[SU_LF_KEY + 1], secret[SU_LF_KEY + 1];
} su_cred_t;

typedef struct {
    char *p;
    unsigned n, cap; /* the request body: n == cap, it did not fit */
} su_buf_t;

typedef struct {
    const char *artist, *album, *title;
    unsigned track, length, time; /* 0: none (the time is never 0) */
} su_entry_t;

static struct {
    unsigned long thread;
    volatile int running; /* the UI thread's: from a start to the poll that joined the thread */
    volatile int done, res, sent, rejected; /* the thread's: done is the last thing it sets */
    int kind; /* SCROBUP_UPLOAD or SCROBUP_CHECK: set before the thread starts */
    int owner; /* SCROBUP_UI or SCROBUP_AUTO: who started it, and so who polls it */
    char auth[sizeof SU_AUTH + SU_TOKEN]; /* the header line with the token, read at the start */
    char name[SU_NAME]; /* a check's user name (the thread's, read after done) */
    int use; /* the services this job asks (SCROBUP_LB | SCROBUP_LF), and skip: those set up and left out because they stood refused */
    int skip;
    volatile int authm,
        okm; /* the thread's: the services that refused the account, and those that answered a request well */
    su_cred_t lf; /* the Last.fm credentials, read at the start */
    char sk
        [SU_LF_KEY +
         1]; /* the Last.fm session key: the one kept, at the start; the thread's while it runs ("" none); the poll keeps what the thread left */
} su __attribute__((section(".scratch")));

/* The Last.fm account as the card's SU_INI had it when it was last read, and the session (the UI thread's). */
static struct {
    int state; /* as sa.state: 1 not set up, 2 the four keys are there (c) */
    int invalid, hasbad; /* c is what the service refused (bad). RAM only */
    su_cred_t c, bad, skc; /* skc: what the session key sk was made from */
    char sk[SU_LF_KEY + 1]; /* "" none. RAM only: dropped when the file has other credentials than skc */
} sl __attribute__((section(".scratch")));

/* The account as the card's SU_INI had it when it was last read (the UI thread's). */
static struct {
    int state; /* 0 not read (or to be read again: scrobup_forget, a write), 1 no token, 2 a token */
    int invalid; /* tok is the token the service refused (bad). RAM only: until another token is in the file, a valid check, a listen taken, a sign-out or a restart */
    char tok[SU_TOKEN + 1], name[SU_NAME];
    char bad[SU_TOKEN + 1]; /* the token the service refused, "" none */
} sa __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * The request body
 */
static void su_put(su_buf_t *b, const char *s, unsigned n) {
    if (b->n + n >= b->cap) {
        b->n = b->cap;
        return;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
}

#define SU_LIT(b, s) su_put(b, s, sizeof(s) - 1)

static void su_dec(su_buf_t *b, unsigned v) {
    char d[10];
    unsigned n = 0;
    do {
        d[9 - n++] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    su_put(b, d + 10 - n, n);
}

/* The length of the well-formed UTF-8 sequence at s (2..4: no overlong form, no surrogate, nothing past U+10FFFF), 0 when there is none. */
static unsigned su_seq(const unsigned char *s) {
    unsigned c = s[0], n, i;
    if (c < 0xc2 || c > 0xf4) return 0;
    n = c < 0xe0 ? 2 : c < 0xf0 ? 3 : 4;
    for (i = 1; i < n; ++i)
        if ((s[i] & 0xc0) != 0x80) return 0; /* (the string's NUL ends it here) */
    if ((c == 0xe0 && s[1] < 0xa0) || (c == 0xed && s[1] >= 0xa0) || (c == 0xf0 && s[1] < 0x90) ||
        (c == 0xf4 && s[1] >= 0x90))
        return 0;
    return n;
}

/* A tag as the contents of a JSON string: a quote and a backslash escaped, a control byte as \u00XX, a byte that is not UTF-8 as U+FFFD (the service refuses a body
 * that is not UTF-8, and the batch with it). At most 6 bytes a byte. */
static void su_str(su_buf_t *b, const char *s) {
    static const char hex[] = "0123456789abcdef";
    const unsigned char *p = (const unsigned char *)s;
    while (*p) {
        unsigned c = *p, n = 1;
        char e[6] = {'\\', (char)c, '0', '0', 0, 0};
        if (c == '"' || c == '\\')
            su_put(b, e, 2);
        else if (c < 0x20) {
            e[1] = 'u', e[4] = hex[c >> 4], e[5] = hex[c & 15];
            su_put(b, e, 6);
        } else if (c < 0x80)
            su_put(b, (const char *)p, 1);
        else if ((n = su_seq(p)) != 0)
            su_put(b, (const char *)p, n);
        else {
            SU_LIT(b, "\xef\xbf\xbd");
            n = 1;
        }
        p += n;
    }
}

/* The number of a field of 1 to max digits; 0 for anything else, for 0 and for a number past 32 bits. */
static unsigned su_num(const char *s, unsigned max) {
    unsigned v = 0, n = 0;
    for (; s[n]; ++n) {
        unsigned d = (unsigned)(unsigned char)s[n] - '0';
        if (d > 9 || n >= max || v > (0xffffffffu - d) / 10) return 0;
        v = v * 10 + d;
    }
    return v;
}

/* One log line (NUL terminated; its tabs become NULs): artist, album, title, track number, length, rating, time, MusicBrainz ID. 1 when it is a listen to send: rated L,
 * with an artist, a title and a time. */
static int su_parse(char *line, su_entry_t *e) {
    char *f[8], *s;
    int n = 1;
    f[0] = line;
    for (s = line; *s && n < 8; ++s)
        if (*s == '\t') *s = 0, f[n++] = s + 1;
    if (n < 7 || !*f[0] || !*f[2] || f[5][0] != 'L') return 0;
    e->time = su_num(f[6], 10);
    if (e->time < SU_TIME_MIN) return 0;
    e->artist = f[0], e->album = f[1], e->title = f[2];
    e->track = su_num(f[3], 6), e->length = su_num(f[4], 6);
    return 1;
}

/* ---------------------------------------------------------------------------
 * The senders, one a service
 */
/* The answer's body: dropped without a ctx (without a callback libcurl would print it), else kept in the su_buf_t ctx; one that does not fit ends the transfer. */
static unsigned su_take(char *data, unsigned size, unsigned n, void *ctx) {
    su_buf_t *b = (su_buf_t *)ctx;
    unsigned k = size * n;
    if (!b) return k;
    if (k > b->cap - b->n) return 0;
    memcpy(b->p + b->n, data, k);
    b->n += k;
    return k;
}

static char su_json[] = "Content-Type: application/json";
static char su_form[] = "Content-Type: application/x-www-form-urlencoded";

/* One request to url with the header line auth (NULL: none): body POSTed as `type` (a Content-Type line), or a GET without one; the answer's body into ans when given. The
 * HTTP status, 0 when there was no whole answer. HTTPS only, the certificate verified against the firmware's bundle, no redirect followed (the account goes to the named
 * host only). */
static long su_http(const char *url, char *auth, char *type, const su_buf_t *body, su_buf_t *ans) {
    struct su_slist {
        char *data;
        struct su_slist *next;
    } hd[2]; /* libcurl's curl_slist: two headers at most, no allocation (as sbnet's) */
    void *h = curl_easy_init();
    long code = 0;
    int k = 0;
    if (!h) return 0;
    if (auth) hd[k].data = auth, hd[k++].next = (struct su_slist *)0;
    if (body) {
        hd[k].data = type, hd[k].next = (struct su_slist *)0;
        if (k) hd[0].next = &hd[1];
        ++k;
    }
    if (curl_easy_setopt(h, CURLOPT_URL, url) == CURLE_OK &&
        (!body || (curl_easy_setopt(h, CURLOPT_POSTFIELDS, body->p) == CURLE_OK &&
                   curl_easy_setopt(h, CURLOPT_POSTFIELDSIZE, (long)body->n) == CURLE_OK)) &&
        curl_easy_setopt(h, CURLOPT_HTTPHEADER, k ? &hd[0] : (struct su_slist *)0) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, su_take) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_WRITEDATA, ans) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1L) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_PROTOCOLS, (long)CURLPROTO_HTTPS) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT, (long)SU_CONNECT_S) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_TIMEOUT, (long)SU_TOTAL_S) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_USERAGENT, "M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)") == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_CAINFO, M1_CA) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_SSL_VERIFYPEER, 1L) == CURLE_OK &&
        curl_easy_setopt(h, CURLOPT_SSL_VERIFYHOST, 2L) == CURLE_OK && curl_easy_perform(h) == CURLE_OK &&
        curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &code) != CURLE_OK)
        code = 0;
    curl_easy_cleanup(h);
    return code;
}

/* ListenBrainz: submit-listens, listen_type import. */
static int su_lb_send(const su_entry_t *e, int n, su_buf_t *b) {
    long code;
    int i;
    b->n = 0;
    SU_LIT(b, "{\"listen_type\":\"import\",\"payload\":[");
    for (i = 0; i < n; ++i) {
        if (i) SU_LIT(b, ",");
        SU_LIT(b, "{\"listened_at\":");
        su_dec(b, e[i].time);
        SU_LIT(b, ",\"track_metadata\":{\"artist_name\":\"");
        su_str(b, e[i].artist);
        SU_LIT(b, "\",\"track_name\":\"");
        su_str(b, e[i].title);
        if (*e[i].album) {
            SU_LIT(b, "\",\"release_name\":\"");
            su_str(b, e[i].album);
        }
        SU_LIT(b, "\",\"additional_info\":{");
        if (e[i].length) {
            SU_LIT(b, "\"duration\":");
            su_dec(b, e[i].length);
            SU_LIT(b, ",");
        }
        if (e[i].track) {
            SU_LIT(b, "\"tracknumber\":");
            su_dec(b, e[i].track);
            SU_LIT(b, ",");
        }
        SU_LIT(b, "\"media_player\":\"M1+ Music\",\"submission_client\":\"M1+ Music\"}}}");
    }
    SU_LIT(b, "]}");
    if (b->n >= b->cap) return SCROBUP_FAIL; /* (SU_RAW bounds it: never) */
    code = su_http(SU_LB_URL, su.auth, su_json, b, (su_buf_t *)0);
    if (code == 200) su.okm |= SCROBUP_LB;
    return code == 200 ? SCROBUP_OK : code == 401 ? SCROBUP_AUTH : code == 400 ? SU_REJECT : SCROBUP_FAIL;
}

/* 1 when the n bytes at s, the white space around them dropped, are a token: 1 to max bytes of printable ASCII without a space (anything else could not be a
 * header's value, and a second line is none): *a its start, *len its length. */
static int su_shape(const char *s, unsigned n, unsigned max, unsigned *a, unsigned *len) {
    unsigned i = 0, j;
    while (i < n && (unsigned char)s[i] <= ' ') ++i;
    while (n > i && (unsigned char)s[n - 1] <= ' ') --n;
    if (n == i || n - i > max) return 0;
    for (j = i; j < n; ++j)
        if ((unsigned char)s[j] <= ' ' || (unsigned char)s[j] >= 0x7f) return 0;
    *a = i, *len = n - i;
    return 1;
}

/* ---------------------------------------------------------------------------
 * Last.fm (https://www.last.fm/api): every call is a form POSTed to SU_LF_URL with format=json, signed with api_sig = MD5 (hex) of every other parameter, name then
 * value as they are (UTF-8, not escaped), in the byte order of the names, then the API secret. MD5 is libcrypto's, which demo imports.
 */
/* Where a form's bytes go: into the signature (sig), or percent-encoded into the body. */
typedef struct {
    su_buf_t *b;
    int sig;
    unsigned md5[24]; /* an MD5_CTX (92 bytes) */
} su_formout_t;

static void su_fput(su_formout_t *f, const char *s, unsigned n) {
    static const char hex[] = "0123456789ABCDEF";
    if (f->sig) {
        if (n) MD5_Update(f->md5, s, n);
        return;
    }
    for (; n--; ++s) {
        unsigned c = (unsigned char)*s;
        char e[3] = {'%', hex[c >> 4], hex[c & 15]};
        if ((c >= '0' && c <= '9') || ((c | 32) >= 'a' && (c | 32) <= 'z') || c == '-' || c == '_' || c == '.' ||
            c == '~')
            su_put(f->b, s, 1);
        else
            su_put(f->b, e, 3); /* every other byte: '&', '=', '+', a space, the brackets of a name, UTF-8 */
    }
}

/* One parameter, name or name[i] (i >= 0), with the value val: a byte of it that is not well-formed UTF-8 goes as U+FFFD into the signature and the body alike (the
 * service reads the body as UTF-8: any other byte would be a signature that does not match, which is an account refused). At most 9 bytes a byte. */
static void su_field(su_formout_t *f, const char *name, int i, const char *val) {
    char nm[24];
    const unsigned char *p = (const unsigned char *)val, *a = p;
    unsigned k = (unsigned)(i < 0 ? snprintf(nm, sizeof nm, "%s", name) : snprintf(nm, sizeof nm, "%s[%d]", name, i));
    if (!f->sig && f->b->n) SU_LIT(f->b, "&");
    su_fput(f, nm, k);
    if (!f->sig) SU_LIT(f->b, "=");
    while (*p) {
        unsigned n = *p < 0x80 ? 1 : su_seq(p);
        if (n) {
            p += n;
            continue;
        }
        su_fput(f, (const char *)a, (unsigned)(p - a));
        su_fput(f, "\xef\xbf\xbd", 3);
        a = ++p;
    }
    su_fput(f, (const char *)a, (unsigned)(p - a));
}

/* The parameters of a call in the signature's order, which is the byte order of their names ("trackNumber[" is before "track[", and "artist[10]" before "artist[1]":
 * ']' is above the digits): track.scrobble for the n listens at e, auth.getMobileSession for n 0. A listen's album, length and track number are left out when it has none. */
static void su_lf_form(su_formout_t *f, const su_entry_t *e, int n) {
    unsigned char ord[SU_BATCH];
    char d[12];
    int k = 0, t, j, i;
    for (t = 0; t < 10; ++t) { /* 0, 10 .. 19, 1, 20 .. 29, 2, .. */
        for (j = 0; t && j < 10; ++j)
            if (t * 10 + j < n) ord[k++] = (unsigned char)(t * 10 + j);
        if (t < n) ord[k++] = (unsigned char)t;
    }
    for (i = 0; i < n; ++i)
        if (*e[ord[i]].album) su_field(f, "album", ord[i], e[ord[i]].album);
    su_field(f, "api_key", -1, su.lf.key);
    for (i = 0; i < n; ++i) su_field(f, "artist", ord[i], e[ord[i]].artist);
    for (i = 0; i < n; ++i)
        if (e[ord[i]].length) {
            snprintf(d, sizeof d, "%u", e[ord[i]].length);
            su_field(f, "duration", ord[i], d);
        }
    su_field(f, "method", -1, n ? "track.scrobble" : "auth.getMobileSession");
    if (!n) {
        su_field(f, "password", -1, su.lf.pass);
        su_field(f, "username", -1, su.lf.user);
        return;
    }
    su_field(f, "sk", -1, su.sk);
    for (i = 0; i < n; ++i) {
        snprintf(d, sizeof d, "%u", e[ord[i]].time);
        su_field(f, "timestamp", ord[i], d);
    }
    for (i = 0; i < n; ++i)
        if (e[ord[i]].track) {
            snprintf(d, sizeof d, "%u", e[ord[i]].track);
            su_field(f, "trackNumber", ord[i], d);
        }
    for (i = 0; i < n; ++i) su_field(f, "track", ord[i], e[ord[i]].title);
}

/* The number that is the len bytes at v (a JSON number, or a string of digits: Last.fm writes both): 0xffffffff when it is none. */
static unsigned su_jnum(const char *v, unsigned len) {
    unsigned i = len && v[0] == '"', x = 0, k = 0;
    for (; i < len && k < 9 && (unsigned)(v[i] - '0') <= 9; ++i, ++k) x = x * 10 + (unsigned)(v[i] - '0');
    return k ? x : 0xffffffffu;
}

/* One call: the form of su_lf_form(e, n), signed, POSTed with body b; the answer into a. SCROBUP_OK for an HTTP 200 whose object has no "error". Last.fm answers an
 * error with a status of its own choosing (403, 400, ..) and {"error":N,"message":".."}, so the body is read whatever the status: 4 (the user name or the password), 10
 * and 26 (the API key), 13 (the signature: the secret) are SCROBUP_AUTH, 9 (the session key) is SU_RENEW; every other one (8, 11, 16, 29 among them), any other status
 * and no answer are SCROBUP_FAIL. */
static int su_lf_call(const su_entry_t *e, int n, su_buf_t *b, su_buf_t *a) {
    static const char hex[] = "0123456789abcdef";
    su_formout_t f;
    unsigned char d[16];
    char sig[32];
    const char *v;
    unsigned len, err, i;
    long code;
    f.b = b, b->n = 0, a->n = 0;
    f.sig = 1;
    MD5_Init(f.md5);
    su_lf_form(&f, e, n);
    MD5_Update(f.md5, su.lf.secret, strlen(su.lf.secret));
    MD5_Final(d, f.md5);
    for (i = 0; i < 16; ++i) sig[2 * i] = hex[d[i] >> 4], sig[2 * i + 1] = hex[d[i] & 15];
    f.sig = 0;
    su_lf_form(&f, e, n);
    SU_LIT(b, "&api_sig=");
    su_put(b, sig, 32);
    SU_LIT(b, "&format=json");
    if (b->n >= b->cap) return SCROBUP_FAIL; /* (SU_RAW bounds it: never) */
    code = su_http(SU_LF_URL, (char *)0, su_form, b, a);
    if (!code) return SCROBUP_FAIL;
    if (pj_span(a->p, a->n, "error", (char *)0, 0, &v, &len) != PJ_M_NONE) {
        err = su_jnum(v, len);
        return err == 9 ? SU_RENEW : err == 4 || err == 10 || err == 26 || err == 13 ? SCROBUP_AUTH : SCROBUP_FAIL;
    }
    return code == 200 ? SCROBUP_OK : SCROBUP_FAIL;
}

/* auth.getMobileSession: SCROBUP_OK with the session key in su.sk ({"session":{"name":"..","key":"..","subscriber":0}}); SCROBUP_AUTH when the service refuses the
 * credentials; SCROBUP_FAIL for anything else, an answer without a usable key among it. */
static int su_lf_session(su_buf_t *b, su_buf_t *a) {
    char key[SU_LF_KEY + 2];
    const char *v;
    unsigned len, at, klen;
    int res;
    su.sk[0] = 0;
    res = su_lf_call((const su_entry_t *)0, 0, b, a);
    if (res != SCROBUP_OK) return res == SU_RENEW ? SCROBUP_FAIL : res;
    if (pj_span(a->p, a->n, "session", (char *)0, 0, &v, &len) == PJ_M_NONE ||
        pj_member(v, len, "key", key, sizeof key) != PJ_M_STRING || !su_shape(key, strlen(key), SU_LF_KEY, &at, &klen))
        return SCROBUP_FAIL;
    memcpy(su.sk, key + at, klen);
    su.sk[klen] = 0;
    su.okm |= SCROBUP_LF;
    return SCROBUP_OK;
}

/* track.scrobble for the n listens at e. SCROBUP_OK: the service answered for each of them, ign[i] 0 for one it took, else its ignoredMessage code (the artist, the
 * track, a time too old or too new: for good). The answer is {"scrobbles":{"scrobble":[{..,"ignoredMessage":{"code":"0","#text":""},..}, ..],"@attr":{..}}}, the
 * scrobbles in the request's order, and one object instead of the array for one listen; a listen whose entry is not found there counts as taken (the request was).
 * A listen ignored for the daily limit is not for good: the batch failed (SCROBUP_FAIL). The call's other results are su_lf_call's. */
static int su_lf_send(const su_entry_t *e, int n, su_buf_t *b, su_buf_t *a, unsigned char *ign) {
    const char *v, *s, *el = (const char *)0, *m;
    unsigned len, slen, ellen = 0, mlen, at = 0, c;
    int res = su_lf_call(e, n, b, a), i;
    memset(ign, 0, (unsigned)n);
    if (res != SCROBUP_OK) return res;
    if (pj_span(a->p, a->n, "scrobbles", (char *)0, 0, &v, &len) == PJ_M_NONE) return SCROBUP_FAIL;
    su.okm |= SCROBUP_LF;
    if (pj_span(v, len, "scrobble", (char *)0, 0, &s, &slen) == PJ_M_NONE) return SCROBUP_OK;
    for (i = 0; i < n; ++i) {
        if (*s == '[') {
            if (!pj_next(s, slen, &at, &el, &ellen)) break;
        } else if (i)
            break;
        else
            el = s, ellen = slen;
        if (pj_span(el, ellen, "ignoredMessage", (char *)0, 0, &m, &mlen) == PJ_M_NONE ||
            pj_span(m, mlen, "code", (char *)0, 0, &m, &mlen) == PJ_M_NONE)
            continue;
        c = su_jnum(m, mlen);
        if (c == SU_LF_LIMIT) return SCROBUP_FAIL;
        ign[i] = (unsigned char)(c > 255 ? 255 : c);
    }
    return SCROBUP_OK;
}

/* A user name to keep and show from the n bytes at s (s[n] is no UTF-8 continuation byte: a NUL or a line's end), into dst (cap bytes with the NUL): control bytes,
 * DEL, C1 controls and bytes that are not UTF-8 dropped, no space at either end, cut on a character boundary. */
static void su_name(char *dst, unsigned cap, const char *s, unsigned n) {
    const unsigned char *p = (const unsigned char *)s;
    unsigned i = 0, o = 0;
    while (i < n) {
        unsigned c = p[i], k = 1;
        if (c >= 0x80) k = su_seq(p + i);
        if (c < 0x20 || c == 0x7f || !k || (c == 0xc2 && p[i + 1] < 0xa0) || (c == ' ' && !o)) {
            i += k ? k : 1;
            continue;
        }
        if (o + k + 1 > cap) break;
        memcpy(dst + o, p + i, k);
        o += k, i += k;
    }
    while (o && dst[o - 1] == ' ') --o;
    dst[o] = 0;
}

/* ListenBrainz: validate-token. SCROBUP_OK with the user name in name (cap bytes) for {"valid":true,"user_name":".."}; SCROBUP_AUTH for "valid":false or a 401;
 * SCROBUP_FAIL for no answer, another status, or an answer that is not that object (cut short, over SU_ANS, no valid member, no name). */
static int su_lb_check(char *name, unsigned cap) {
    char ans[SU_ANS], raw[2 * SU_NAME];
    su_buf_t b = {ans, 0, sizeof ans};
    long code = su_http(SU_LB_CHECK, su.auth, (char *)0, (const su_buf_t *)0, &b);
    int valid;
    name[0] = 0;
    if (code == 401) return SCROBUP_AUTH;
    if (code != 200) return SCROBUP_FAIL;
    valid = pj_member(ans, b.n, "valid", raw, sizeof raw);
    if (valid == PJ_M_FALSE) return SCROBUP_AUTH;
    if (valid != PJ_M_TRUE || pj_member(ans, b.n, "user_name", raw, sizeof raw) != PJ_M_STRING) return SCROBUP_FAIL;
    su_name(name, cap, raw, strlen(raw));
    return name[0] ? SCROBUP_OK : SCROBUP_FAIL;
}

/* ---------------------------------------------------------------------------
 * The log
 */
/* The log's bytes as the upload read them (FNV-1a, carried on from h): su_retire takes only the bytes it finds again. */
static unsigned su_hash(unsigned h, const char *p, unsigned n) {
    while (n--) h = (h ^ (unsigned char)*p++) * 16777619u;
    return h;
}

/* Up to SU_WIN bytes of the log from off into win; -1 when the card is gone, or the log does not open (for any reason but ENOENT), seek or read. No log: 0. */
static int su_window(char *win, unsigned off) {
    int fd, got = 0, r = 0;
    scrobble_lock();
    if (!m1_card_mounted())
        got = -1;
    else if ((fd = open(SC_LOG, O_RDONLY, 0)) < 0)
        got = *__errno_location() == SU_ENOENT ? 0 : -1; /* only "no such file" is nothing to upload */
    else {
        if (lseek(fd, (long)off, 0) != (long)off)
            r = -1;
        else
            while ((unsigned)got < SU_WIN && (r = read(fd, win + got, SU_WIN - (unsigned)got)) > 0) got += r;
        if (r < 0) got = -1;
        close(fd);
    }
    scrobble_unlock();
    return got;
}

/* An upload's state (the thread's). */
typedef struct {
    su_entry_t e[SU_BATCH]; /* the pending batch: n listens, their lines the first rawn bytes of raw */
    char *raw;
    su_buf_t b, a; /* a request's body; Last.fm's answer */
    unsigned char st
        [SU_BATCH]; /* the services that took each listen of the batch (SCROBUP_LB | SCROBUP_LF), and << 4 those that refused it for good */
    unsigned char ign[SU_BATCH]; /* Last.fm's answer for each */
    int reqs, renewed; /* requests made; a Last.fm session was made again after an error 9 (once an upload) */
    unsigned end[SU_BATCH]; /* the log's offset behind each listen's line */
    unsigned eh[SU_BATCH]; /* su_hash of the log as far as that offset */
    unsigned h, dh; /* su_hash of the log's bytes looked at, and of its first done bytes */
    unsigned rawn, done; /* done: the log's bytes that may leave (up to the last listen answered 200 or 400) */
    unsigned rej[SU_REJ][2],
        nrej; /* the bytes of the refused listens among them: [from, to), in order, runs in a row joined */
    int n, sent, rejected, res;
} su_run_t;

/* k bytes appended to the archive path, opened at its first bytes (*fd, -1 before). */
static int su_arc(int *fd, const char *path, const char *buf, unsigned k) {
    if (*fd < 0 && (*fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644)) < 0) return 0;
    return m1_write_all(*fd, buf, k);
}

/* The log's first run->done bytes into the archives (less the comments: the refused listens' bytes to SU_REJECTED, the others to SU_SENT), the log left as the header and
 * what follows them. Only when those bytes are the ones the upload read (run->dh): a log replaced or changed meanwhile, of whatever length, is left alone. buf: SU_WIN
 * bytes to copy with. 1 on success; any failure leaves the log as it was (an archive may have gained some of the lines by then: they go
 * again, and are archived again). */
static int su_retire(const su_run_t *run, char *buf) {
    int in, out = -1, arc[2] = {-1, -1}, to = 0, ok, r = 0, bol = 1, com = 0;
    unsigned done = run->done, pos, ri = 0, i, h = SU_HASH0;
    scrobble_lock();
    in = m1_card_mounted() ? open(SC_LOG, O_RDONLY, 0) : -1;
    ok = in >= 0 && lseek(in, 0, 2) >= (long)done && lseek(in, 0, 0) == 0;
    for (pos = 0; ok && pos < done; pos += (unsigned)r) {
        r = read(in, buf, done - pos < SU_WIN ? done - pos : SU_WIN);
        if (r <= 0) {
            ok = 0;
            break;
        }
        h = su_hash(h, buf, (unsigned)r);
    }
    ok = ok && h == run->dh; /* else it is not the log that was sent: nothing of it is retired */
    pos = 0;
    if (ok) out = open(SU_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    ok = out >= 0 && m1_write_all(out, SC_HEADER, sizeof SC_HEADER - 1);
    while (ok && (r = read(in, buf, SU_WIN)) != 0) ok = r > 0 && m1_write_all(out, buf, (unsigned)r);
    ok = ok && fsync(out) == 0; /* a full card fails here, before an archive gains anything */
    ok = ok && lseek(in, 0, 0) == 0;
    for (; ok && pos < done; pos += (unsigned)r) {
        unsigned lim, k = 0;
        while (ri < run->nrej && pos >= run->rej[ri][1]) ++ri;
        to = ri < run->nrej && pos >= run->rej[ri][0];
        lim = (to               ? run->rej[ri][1]
               : ri < run->nrej ? run->rej[ri][0]
                                : done) -
              pos; /* as far as one archive takes it */
        r = read(in, buf, lim < SU_WIN ? lim : SU_WIN);
        if (r <= 0) {
            ok = 0;
            break;
        }
        for (i = 0; i < (unsigned)r; ++i) {
            if (bol) com = buf[i] == '#';
            bol = buf[i] == '\n';
            if (!com) buf[k++] = buf[i];
        }
        ok = !k || su_arc(&arc[to], to ? SU_REJECTED : SU_SENT, buf, k);
    }
    if (ok && !bol && !com)
        ok = su_arc(&arc[to], to ? SU_REJECTED : SU_SENT, "\n",
                    1); /* (an over-long line without an end, at the log's end) */
    for (i = 0; i < 2; ++i)
        if (arc[i] >= 0) {
            ok = fsync(arc[i]) == 0 && ok;
            ok = close(arc[i]) == 0 && ok;
        }
    if (in >= 0) close(in);
    if (out >= 0) ok = m1_commit(out, ok, SU_TMP, SC_LOG);
    scrobble_unlock();
    return ok;
}

/* A request of n listens, the log's bytes from run->done to `to` (h: su_hash of the log as far as `to`), was answered res: taken or refused for good, they may leave the log (1); anything else ends the upload
 * (0, run->res) with them, and all that follows, still in it. */
static int su_answer(su_run_t *run, int res, int n, unsigned to, unsigned h) {
    if (res == SU_REJECT) {
        if (run->nrej && run->rej[run->nrej - 1][1] == run->done)
            run->rej[run->nrej - 1][1] = to;
        else if (run->nrej < SU_REJ)
            run->rej[run->nrej][0] = run->done, run->rej[run->nrej++][1] = to;
        else
            res = SCROBUP_FAIL; /* refused and taken listens took turns SU_REJ times: the rest waits */
    }
    if (res == SU_REJECT)
        run->rejected += n;
    else if (res > 0)
        run->sent += n;
    else {
        run->res = res;
        return 0;
    }
    run->done = to, run->dh = h;
    return 1;
}

/* The kill switch, looked at before every request of an upload but the first (the start has just looked). */
static int su_off(su_run_t *run) { return run->reqs++ && home_off(); }

/* The pending batch to ListenBrainz: run->st gets its answer for each listen. A batch of several answered 400 is narrowed: one listen may be the cause, so each goes again
 * alone, and only those refused alone are refused. SCROBUP_OK when every listen has an answer, else the failure (the listens before it keep theirs). */
static int su_lb_batch(su_run_t *run) {
    int res = su_off(run) ? SCROBUP_FAIL : su_lb_send(run->e, run->n, &run->b), i;
    if (res == SU_REJECT && run->n > 1) {
        for (i = 0; i < run->n; ++i) {
            res = su_off(run) ? SCROBUP_FAIL : su_lb_send(run->e + i, 1, &run->b);
            if (res != SCROBUP_OK && res != SU_REJECT) return res;
            run->st[i] |= res == SCROBUP_OK ? SCROBUP_LB : SCROBUP_LB << 4;
        }
        return SCROBUP_OK;
    }
    if (res != SCROBUP_OK && res != SU_REJECT) return res;
    for (i = 0; i < run->n; ++i) run->st[i] |= res == SCROBUP_OK ? SCROBUP_LB : SCROBUP_LB << 4;
    return SCROBUP_OK;
}

/* The pending batch to Last.fm, in one request (the answer has a line for each listen: nothing to narrow). A session key is asked for first when none is kept; one the
 * service no longer takes (error 9) is dropped, and the batch goes again with a new one, once an upload. */
static int su_lf_batch(su_run_t *run) {
    int res, i;
    for (;;) {
        if (!su.sk[0] && (res = su_off(run) ? SCROBUP_FAIL : su_lf_session(&run->b, &run->a)) != SCROBUP_OK) return res;
        res = su_off(run) ? SCROBUP_FAIL : su_lf_send(run->e, run->n, &run->b, &run->a, run->ign);
        if (res != SU_RENEW) break;
        su.sk[0] = 0;
        if (run->renewed++) return SCROBUP_FAIL;
    }
    if (res != SCROBUP_OK) return res;
    for (i = 0; i < run->n; ++i) run->st[i] |= run->ign[i] ? SCROBUP_LF << 4 : SCROBUP_LF;
    return SCROBUP_OK;
}

/* The pending batch is sent to every service of the job (su.use); end: the log's offset behind its lines, which is as far as the log was looked at (run->h). A listen
 * may leave the log once every one of those services has taken it or refused it for good: for the archive when one took it, for SU_REJECTED when all refused it. A
 * listen's bytes run from the end of the one before it (the batch's start for the first) to its line's end (the batch's end for the last), so a skipped line goes with
 * the listen after it. 1 when the whole batch left the log's pending part and the upload goes on; 0 when the upload ends here (run->res): a service failed, and the
 * listens it has not answered for stay, with all that follows, for every service (each drops a listen it has). */
static int su_flush(su_run_t *run, unsigned end) {
    int res = SCROBUP_OK, i;
    memset(run->st, 0, sizeof run->st);
    if (su.use & SCROBUP_LB) {
        res = su_lb_batch(run);
        if (res == SCROBUP_AUTH) su.authm |= SCROBUP_LB;
    }
    if (res == SCROBUP_OK && (su.use & SCROBUP_LF)) {
        res = su_lf_batch(run);
        if (res == SCROBUP_AUTH) su.authm |= SCROBUP_LF, su.sk[0] = 0;
    }
    for (i = 0; i < run->n; ++i) {
        unsigned st = run->st[i];
        int last = i + 1 == run->n;
        if (((st | st >> 4) & 15) != (unsigned)su.use) break;
        if (!su_answer(run, st & 15 ? SCROBUP_OK : SU_REJECT, 1, last ? end : run->end[i], last ? run->h : run->eh[i]))
            return 0;
    }
    if (res != SCROBUP_OK) {
        run->res = res;
        return 0;
    }
    run->n = 0, run->rawn = 0;
    return 1;
}

static void *su_worker(void *arg) {
    su_run_t run;
    char *win; /* a window of the log */
    unsigned off = 0; /* log bytes looked at */
    int any = 0, leave, skip = 0,
        more = 1; /* any: a line that is no comment was passed; skip: inside an over-long line */
    (void)arg;
    if (su.kind !=
        SCROBUP_UPLOAD) { /* a check: the token (validate-token), or the Last.fm credentials (a session, kept when there is one) */
        char body[SU_ANS], ans[SU_ANS];
        su_buf_t b = {body, 0, sizeof body}, a = {ans, 0, sizeof ans};
        int res = su.kind == SCROBUP_CHECK ? su_lb_check(su.name, sizeof su.name) : su_lf_session(&b, &a);
        memset(body, 0, sizeof body); /* (the password) */
        if (res == SCROBUP_AUTH) su.authm = su.use;
        su.sent = su.rejected = 0;
        su.res = res;
        su.done = 1;
        return (void *)0;
    }
    memset(&run, 0, sizeof run);
    run.h = SU_HASH0;
    win = calloc(1, SU_WIN);
    run.raw = calloc(1, SU_RAW);
    run.b.p = calloc(1, SU_BODY), run.b.cap = SU_BODY;
    if (su.use & SCROBUP_LF) run.a.p = calloc(1, SU_BODY), run.a.cap = SU_BODY;
    run.res = win && run.raw && run.b.p && (run.a.p || !(su.use & SCROBUP_LF)) ? SCROBUP_OK : SCROBUP_FAIL;
    while (run.res > 0 && more) {
        int got = su_window(win, off);
        unsigned at = 0, size = (unsigned)got;
        if (got < 0) {
            run.res = SCROBUP_DISK;
            break;
        }
        while (at < size) {
            unsigned j = at, len, hn;
            while (j < size && win[j] != '\n') ++j;
            if (j ==
                size) { /* no end here: the next window starts with it, unless it is too long to be a line: junk as far as its end */
                if (skip || size - at > SU_LINE)
                    skip = 1, any = 1, run.h = su_hash(run.h, win + at, size - at), at = size;
                break;
            }
            len = j - at;
            hn = su_hash(run.h, win + at,
                         j + 1 - at); /* run.h stays at this line's start until a flush before it is done */
            if (skip)
                skip = 0;
            else if (win[at] != '#') {
                any = 1;
                if (len && win[j - 1] == '\r') --len;
                if (len && len <= SU_LINE) {
                    if ((run.n == SU_BATCH || run.rawn + len + 1 > SU_RAW) && !su_flush(&run, off + at)) break;
                    memcpy(run.raw + run.rawn, win + at, len);
                    run.raw[run.rawn + len] = 0;
                    if (su_parse(run.raw + run.rawn, &run.e[run.n]))
                        run.eh[run.n] = hn, run.end[run.n++] = off + j + 1, run.rawn += len + 1;
                }
            }
            run.h = hn;
            at = j + 1;
        }
        off += at;
        more = size == SU_WIN;
    }
    if (run.res > 0 && run.n) su_flush(&run, off);
    leave = run.done > 0;
    if (run.res > 0)
        run.done = off, run.dh = run.h,
        leave = any; /* all of it, the skipped lines after the last listen too; a log of comments only is left alone */
    if (leave && !su_retire(&run, win)) run.res = SCROBUP_DISK;
    free(win);
    free(run.raw);
    if (run.a.p) {
        if (run.b.p) memset(run.b.p, 0, SU_BODY); /* (the password, in a session's request) */
        free(run.a.p);
    }
    free(run.b.p);
    su.sent = run.sent;
    su.rejected = run.rejected;
    su.res = run.res;
    su.done = 1;
    return (void *)0;
}

/* ---------------------------------------------------------------------------
 * The accounts (the UI thread's side)
 */
/* A service's part of the card's file: its section and the keys read there. key[0] is its secret, the value a sign-out empties. */
typedef struct {
    const char *sec;
    const char *key[SU_KEYS];
    unsigned nk;
} su_svc_t;

#define SU_SVC_LB 0
#define SU_SVC_LF 1
static const su_svc_t su_svc[2] = {{"LISTENBRAINZ", {"TOKEN", "USER"}, 2},
                                   {"LASTFM", {"PASSWORD", "USER", "API_KEY", "API_SECRET"}, 4}};

/* Where a service's account is in the card's file (offsets into its bytes). */
typedef struct {
    unsigned sec; /* the first section of its name: the offset behind its header's line, 0 when there is none */
    struct {
        unsigned l, v, e, n; /* the line's start, the value's start and end, the next line's start (0: no such line) */
    } k[SU_KEYS]; /* the first line of each key of the service, in su_svc_t's order */
    int crlf; /* the file's first line ends with CR LF: so do the lines an edit adds */
} su_ini_t;

/* The n bytes at s are key (capitals), in either case. */
static int su_ieq(const char *s, unsigned n, const char *key) {
    unsigned i;
    for (i = 0; i < n && key[i]; ++i) {
        unsigned c = (unsigned char)s[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (c != (unsigned char)key[i]) return 0;
    }
    return i == n && !key[i];
}

/* The file's lines: a UTF-8 BOM at its start, a CR before a line's end and blanks at a line's start dropped; an empty line and one that starts with ';' or '#' are
 * comments; "[name]" starts a section (blanks inside the brackets dropped, the name in either case, what follows the bracket ignored); "key = value" (blanks around both
 * dropped, the key in either case) is looked at only inside the first section named svc->sec, and only the first line of each of svc's keys there. Every other line,
 * section and key is passed over. */
static void su_ini_scan(const char *t, unsigned n, const su_svc_t *svc, su_ini_t *r) {
    unsigned i =
        n >= 3 && (unsigned char)t[0] == 0xef && (unsigned char)t[1] == 0xbb && (unsigned char)t[2] == 0xbf ? 3 : 0;
    unsigned q;
    int first = 1;
    memset(r, 0, sizeof *r);
    while (i < n) {
        unsigned ls = i, le, a, b, v, e;
        while (i < n && t[i] != '\n') ++i;
        le = i;
        if (i < n) ++i;
        if (le > ls && t[le - 1] == '\r') {
            --le;
            r->crlf |= first;
        }
        first = 0;
        for (a = ls; a < le && (unsigned char)t[a] <= ' '; ++a) {
        }
        if (a == le || t[a] == ';' || t[a] == '#') continue;
        if (t[a] == '[') {
            if (r->sec) break; /* the section is over (a second one of its name is not read) */
            for (b = ++a; b < le && t[b] != ']'; ++b) {
            }
            while (a < b && (unsigned char)t[a] <= ' ') ++a;
            while (b > a && (unsigned char)t[b - 1] <= ' ') --b;
            if (su_ieq(t + a, b - a, svc->sec)) r->sec = i;
            continue;
        }
        if (!r->sec) continue;
        for (b = a; b < le && t[b] != '='; ++b) {
        }
        if (b == le) continue;
        for (v = b + 1; v < le && (unsigned char)t[v] <= ' '; ++v) {
        }
        for (e = le; e > v && (unsigned char)t[e - 1] <= ' '; --e) {
        }
        while (b > a && (unsigned char)t[b - 1] <= ' ') --b;
        for (q = 0; q < svc->nk; ++q)
            if (!r->k[q].n && su_ieq(t + a, b - a, svc->key[q])) {
                r->k[q].l = ls, r->k[q].v = v, r->k[q].e = e, r->k[q].n = i;
                break;
            }
    }
}

static void su_ini_free(char *t) {
    memset(t, 0, SU_INI_MAX + 2 + SU_INI_ROOM); /* (the token, the password) */
    free(t);
}

/* The card's file in a heap buffer with room for an edit (su_ini_free): *n its bytes, SU_INI_MAX + 1 for a longer file; 0 bytes for no file. 0 when it is there and
 * cannot be read, or there is no memory. */
static int su_ini_read(char **t, unsigned *n) {
    int fd = open(SU_INI, O_RDONLY, 0), r = 0;
    unsigned got = 0;
    *n = 0;
    *t = calloc(SU_INI_MAX + 2 + SU_INI_ROOM, 1);
    if (*t && fd < 0 && access(SU_INI, F_OK) != 0) return 1;
    while (*t && fd >= 0 && got <= SU_INI_MAX && (r = read(fd, *t + got, SU_INI_MAX + 1 - got)) > 0) got += (unsigned)r;
    if (fd >= 0) close(fd);
    if (!*t || fd < 0 || r < 0) {
        if (*t) su_ini_free(*t);
        return 0;
    }
    *n = got;
    return 1;
}

static int su_lf_same(const su_cred_t *a, const su_cred_t *b) {
    return !strcmp(a->user, b->user) && !strcmp(a->pass, b->pass) && !strcmp(a->key, b->key) &&
           !strcmp(a->secret, b->secret);
}

/* The Last.fm credentials of the scanned section r of the file t into c: 1 when all four are there and usable. USER as su_name keeps a name; PASSWORD 1 to SU_LF_PASS
 * bytes, none of them a control byte (the blanks around it are not part of it); API_KEY and API_SECRET 1 to SU_LF_KEY bytes of printable ASCII without a space. */
static int su_lf_read(const char *t, const su_ini_t *r, su_cred_t *c) {
    unsigned a, len, i, pn = r->k[0].e - r->k[0].v;
    memset(c, 0, sizeof *c);
    if (!r->k[0].n || !r->k[1].n || !r->k[2].n || !r->k[3].n || !pn || pn > SU_LF_PASS) return 0;
    for (i = 0; i < pn; ++i)
        if ((unsigned char)t[r->k[0].v + i] < ' ' || t[r->k[0].v + i] == 0x7f) return 0;
    memcpy(c->pass, t + r->k[0].v, pn);
    su_name(c->user, sizeof c->user, t + r->k[1].v, r->k[1].e - r->k[1].v);
    if (!c->user[0] || !su_shape(t + r->k[2].v, r->k[2].e - r->k[2].v, SU_LF_KEY, &a, &len)) return 0;
    memcpy(c->key, t + r->k[2].v + a, len);
    if (!su_shape(t + r->k[3].v, r->k[3].e - r->k[3].v, SU_LF_KEY, &a, &len)) return 0;
    memcpy(c->secret, t + r->k[3].v + a, len);
    return 1;
}

/* The card's file into sa and sl, in one read. ListenBrainz: the token (TOKEN's value when it has a token's shape) and the user name (USER's value, as su_name keeps
 * it); no mounted card, no file, no section, no TOKEN line, an empty value or one that is no token: no token. Last.fm: the four values (su_lf_read), or not set up. Of a
 * file over SU_INI_MAX the whole lines of its first SU_INI_MAX bytes are read. A file that is there but could not be read (no memory) is no account now and is read again
 * by the next call. What the service refused follows the file: Invalid Token stands while the file holds the refused token, Last.fm's refusal while it holds the refused
 * credentials; and the Last.fm session is dropped as soon as the file holds other credentials than those it was made from. */
static void su_load(void) {
    su_ini_t r;
    unsigned n = 0, a, len;
    char *t;
    sa.name[0] = 0;
    sa.state = sl.state = 0;
    if (!m1_card_mounted()) {
        sa.state = sl.state = 1; /* (the mount point is not opened) */
        memset(&sl.c, 0, sizeof sl.c);
    } else if (su_ini_read(&t, &n)) {
        if (n > SU_INI_MAX)
            for (n = SU_INI_MAX; n && t[n - 1] != '\n'; --n) {
            }
        su_ini_scan(t, n, &su_svc[SU_SVC_LB], &r);
        sa.state = 1;
        if (r.k[0].n && su_shape(t + r.k[0].v, r.k[0].e - r.k[0].v, SU_TOKEN, &a, &len)) {
            memcpy(sa.tok, t + r.k[0].v + a, len);
            sa.tok[len] = 0;
            if (r.k[1].n) su_name(sa.name, sizeof sa.name, t + r.k[1].v, r.k[1].e - r.k[1].v);
            sa.state = 2;
        }
        su_ini_scan(t, n, &su_svc[SU_SVC_LF], &r);
        sl.state = 1 + su_lf_read(t, &r, &sl.c);
        if (sl.state == 1) memset(&sl.c, 0, sizeof sl.c);
        su_ini_free(t);
    }
    sa.invalid = sa.state == 2 && sa.bad[0] && !strcmp(sa.tok, sa.bad);
    sl.invalid = sl.state == 2 && sl.hasbad && su_lf_same(&sl.c, &sl.bad);
    if (sl.state && !su_lf_same(&sl.c, &sl.skc)) sl.sk[0] = 0;
}

/* The n bytes at t with the del bytes at off replaced by the k bytes at ins: the new length (the buffer has SU_INI_ROOM for it). */
static unsigned su_splice(char *t, unsigned n, unsigned off, unsigned del, const char *ins, unsigned k) {
    memmove(t + off + k, t + off + del, n - off - del);
    memcpy(t + off, ins, k);
    return n - del + k;
}

/* The card's file with a valid check's user name in the ListenBrainz section, every other byte kept: the device's only write to the file (it never writes a secret, its
 * line, a section or the file: those are the user's, and so is signing out, by taking the token out of the file). USER=name (never empty): an existing USER line gets its
 * value replaced (its key, its blanks and its line end stay), a missing one is added behind the TOKEN line with the file's line ends; 0 when the section has no TOKEN line
 * (a name belongs to a token). Written as SU_INI_TMP, synced, then renamed. 1 on success; 0, and the file as it was, with no mounted card, a file that cannot be read or
 * is over SU_INI_MAX (before or after the edit: never cut), or a card that does not take it. */
static int su_ini_set(const char *name) {
    su_ini_t r;
    char line[SU_INI_ROOM], *t;
    unsigned n = 0, k;
    int ok;
    sa.state = 0; /* read again by the next look */
    if (!m1_card_mounted() || !su_ini_read(&t, &n)) return 0;
    su_ini_scan(t, n, &su_svc[SU_SVC_LB], &r);
    ok = n <= SU_INI_MAX && r.k[0].n;
    if (ok && r.k[1].n)
        n = su_splice(t, n, r.k[1].v, r.k[1].e - r.k[1].v, name, strlen(name));
    else if (ok) {
        const char *eol = r.crlf ? "\r\n" : "\n";
        k = (unsigned)snprintf(line, sizeof line, "%sUSER=%s%s", t[r.k[0].n - 1] != '\n' ? eol : "", name, eol);
        n = su_splice(t, n, r.k[0].n, 0, line, k);
    }
    ok = ok && n <= SU_INI_MAX && m1_save(SU_INI, SU_INI_TMP, 0644, t, n);
    su_ini_free(t);
    return ok;
}

void scrobup_forget(void) { sa.state = 0; }

int scrobup_account(char *name, unsigned n) {
    if (!sa.state) su_load();
    if (name && n) snprintf(name, n, "%s", sa.state == 2 ? sa.name : "");
    return sa.state == 2;
}

int scrobup_lastfm(char *name, unsigned n) {
    if (!sa.state) su_load();
    if (name && n) snprintf(name, n, "%s", sl.state == 2 ? sl.c.user : "");
    return sl.state != 2 ? SCROBUP_LF_NONE : sl.invalid ? SCROBUP_LF_BAD : sl.sk[0] ? SCROBUP_LF_IN : SCROBUP_LF_NEW;
}

int scrobup_configured(void) {
    if (!sa.state) su_load();
    return sa.state == 2 || sl.state == 2;
}

int scrobup_usable(void) {
    if (!sa.state) su_load();
    return (sa.state == 2 && !sa.invalid) || (sl.state == 2 && !sl.invalid);
}

/* ---------------------------------------------------------------------------
 * The jobs (the UI thread's side)
 */
static int su_begin(int kind, int owner) {
    int lb, lf, use;
    if (su.running) return 0;
    if (home_off() || !m1_card_mounted()) return -1; /* (a check too: the accounts are on the card) */
    su_load(); /* the card's file as it is now, whatever was kept */
    lb = sa.state == 2 ? SCROBUP_LB : 0, lf = sl.state == 2 ? SCROBUP_LF : 0;
    if (kind == SCROBUP_CHECK)
        use = lb;
    else if (kind == SCROBUP_LFCHECK)
        use = lf;
    else { /* an upload: a service that stands refused is left out, unless that leaves none (then they are asked again) */
        use = (sa.invalid ? 0 : lb) | (sl.invalid ? 0 : lf);
        if (!use) use = lb | lf;
    }
    if (!use) return -1;
    su.use = use, su.skip = kind == SCROBUP_UPLOAD ? (lb | lf) & ~use : 0;
    su.authm = su.okm = 0;
    if (use & SCROBUP_LB) snprintf(su.auth, sizeof su.auth, SU_AUTH "%s", sa.tok);
    if (use & SCROBUP_LF) {
        memcpy(&su.lf, &sl.c, sizeof su.lf);
        memcpy(su.sk, sl.sk, sizeof su.sk); /* (a check asks for a new one) */
    }
    curl_global_init(
        CURL_GLOBAL_ALL); /* (stock has done it at boot; the worker threads of pcnet and sbnet repeat it too) */
    su.done = 0;
    su.kind = kind, su.owner = owner;
    if (pthread_create(&su.thread, (void *)0, su_worker, (void *)0) != 0) return -1;
    su.running = 1;
    return 1;
}

int scrobup_start(int owner) { return su_begin(SCROBUP_UPLOAD, owner); }
int scrobup_check_start(int owner) { return su_begin(SCROBUP_CHECK, owner); }
int scrobup_lastfm_check_start(int owner) { return su_begin(SCROBUP_LFCHECK, owner); }
int scrobup_busy(void) { return su.running; }
int scrobup_kind(void) { return su.kind; }
int scrobup_owner(void) { return su.owner; }
int scrobup_invalid(void) { return sa.invalid; }
int scrobup_rejected(void) { return su.rejected; }
int scrobup_auth(void) { return su.authm | su.skip; }

int scrobup_poll(int *sent) {
    int res, lb, lf;
    if (!su.running || !su.done) return 0;
    pthread_join(su.thread, (void **)0);
    su.running = 0;
    res = su.res;
    lb = su.use & SCROBUP_LB, lf = su.use & SCROBUP_LF;
    if (su.kind == SCROBUP_CHECK && res == SCROBUP_OK) { /* the name goes beside the token it was given for */
        su_load();
        if (sa.state != 2 || strcmp(sa.tok, su.auth + sizeof SU_AUTH - 1))
            res = SCROBUP_FAIL;
        else if (strcmp(sa.name, su.name) && !su_ini_set(su.name))
            res = SCROBUP_DISK;
    }
    if ((su.authm & SCROBUP_LB) || lf) su_load(); /* is the account still the one that was asked about? */
    if (su.authm & SCROBUP_LB) { /* Invalid Token, when the account still has the token that was refused */
        if (sa.state == 2 && !strcmp(sa.tok, su.auth + sizeof SU_AUTH - 1)) {
            memcpy(sa.bad, sa.tok, sizeof sa.bad);
            sa.invalid = 1;
        }
    } else if (lb && (su.kind == SCROBUP_CHECK ? res == SCROBUP_OK : su.okm & SCROBUP_LB))
        sa.bad[0] = 0, sa.invalid = 0;
    if (lf) { /* Last.fm: the session the thread left (a new one, the one it had, or none) is kept for the credentials it was made from, and so is their refusal */
        if (sl.state == 2 && su_lf_same(&sl.c, &su.lf)) {
            memcpy(sl.sk, su.sk, sizeof sl.sk);
            memcpy(&sl.skc, &su.lf, sizeof sl.skc);
            if (su.authm & SCROBUP_LF)
                memcpy(&sl.bad, &su.lf, sizeof sl.bad), sl.hasbad = sl.invalid = 1;
            else if (su.okm & SCROBUP_LF)
                sl.hasbad = sl.invalid = 0;
        } else if (su.kind == SCROBUP_LFCHECK && res == SCROBUP_OK)
            res = SCROBUP_FAIL; /* another account's answer */
        memset(&su.lf, 0, sizeof su.lf);
        memset(su.sk, 0, sizeof su.sk);
    }
    if (sent) *sent = su.sent;
    return res;
}
