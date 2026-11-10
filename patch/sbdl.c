/* Navidrome downloads (docs/modules/subsonic.md "Data and cache", "File split"): ONE detached download worker, a small queue, the manifest dl.idx of finished downloads and the
 * target files in SBA_MUSIC_DIR. The pages never block here: sba_dl_add queues a track and returns, the worker writes the file (sbn_download: a .part file, a Range resume, the PR's
 * stall limit of 512 B/s for 45 s and the 32 MB free-space floor), appends the manifest row, and the page's timer reads sba_dl_gen / sba_dl_state.
 * The worker never calls AWTK; the stock functions it calls are the library scan after a DSD download (scanSpecFolder, as the PR does) and, through sba_guard at the start of a download, get_wifisignal (the Wi-Fi check; sba_configured reads the saved login).
 *
 * The manifest holds the track's whole row (title, artist, album, suffix, ...) plus the file name, so Downloaded works offline and with the server gone. It is a text file, one
 * track a line of tab-separated key=value fields (the keys are in sbd_row_text), replaced whole and atomically; a torn or odd line is skipped. A copy of (id, file, size, DSD)
 * stays in memory after the first use so that painting a row's state never touches the card; a file that was deleted by hand is found out (and dropped) when the path or the
 * list is asked for.
 *
 * Locks: sbd.lock guards the memory (queue, index) and is held for a few instructions only, never across a call; sbd.mf serialises the writers of dl.idx (it is held across the
 * file work, and a waiting UI thread sleeps 1 ms at a time). Order: mf, then lock.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "curlopts.h"
#include "sbapi.h"
#include "sbnet.h"

extern int pn_free_kb(const char *path, unsigned *kb);

#define SBD_IDX SBA_DIR "/dl.idx"
#define SBD_IDX_TMP SBA_DIR "/dl.idx.tmp"
#define SBD_HEAD "M1PLUS-DL 1\n"
#define SBD_FILE 128 /* a file name in SBA_MUSIC_DIR, the NUL included */
#define SBD_PATH 200 /* a full path, the ".part" included */
#define SBD_LINE 1600 /* a manifest line (the longest is about 1100 bytes) */
#define SBD_IDX_MAX (4u << 20) /* a manifest larger than this is read as empty rather than loaded */
#define SBD_ROWS 8000 /* entries kept in memory */
#define SBD_FAIL_FRESH_S 30 /* a failure older than this is not announced */
#define SBD_TITLE 100 /* bytes of the title in a file name */

typedef struct {
    char id[SBA_ID];
    char file[SBD_FILE];
    unsigned size;
    unsigned char dsd;
} sbd_ent_t;

typedef struct {
    char id[SBA_ID];
    unsigned char state; /* 0 free, else SBA_DL_WAIT / ACTIVE / FAILED */
    int code;
    unsigned seq;
    sba_track_t *t; /* the track while it waits or runs */
} sbd_slot_t;

/* Writable state lives in .scratch (the payload has no .bss). */
static struct {
    volatile int lock, mf;
    int busy, loaded, stop;
    int status; /* the HTTP status of the last failed transfer (the worker writes it before it reports the failure) */
    int fail_code, fail_status; /* the newest failure nobody has been told of (0 none) */
    long fail_at; /* when it happened (time(), seconds) */
    unsigned seq, gen, got, total, step;
    sbn_sink_t *sink; /* the active transfer's sink: sba_dl_xfer answers only for it */
    sbd_slot_t q[SBA_DLMAX];
    sbd_ent_t *ix;
    int nix, capix;
} sbd __attribute__((section(".scratch")));

static void sbd_lock(void) {
    while (__sync_lock_test_and_set(&sbd.lock, 1)) {
    }
}
static void sbd_unlock(void) { __sync_lock_release(&sbd.lock); }
static void sbd_mf_lock(void) {
    while (__sync_lock_test_and_set(&sbd.mf, 1)) usleep(1000);
}
static void sbd_mf_unlock(void) { __sync_lock_release(&sbd.mf); }
static void sbd_bump(void) {
    __sync_synchronize();
    __sync_add_and_fetch(&sbd.gen, 1);
}

/* ---- small string helpers (the payload has no libc string set beyond the few stock.h declares) ---- */

static unsigned sbd_len(const char *s) { return sbn_len(s); }

static int sbd_same(const char *a, const char *b) { return strcmp(a, b) == 0; }

static void sbd_set(char *dst, unsigned cap, const char *src) {
    unsigned n = sbd_len(src);
    if (n >= cap) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = 0;
}

/* ---- manifest rows ---- */

/* Append "<key>=<value>" to line at *n (a tab first unless it is the first field). */
static void sbd_put_s(char *line, unsigned cap, unsigned *n, char key, const char *v) {
    unsigned i = 0;
    if (*n + 4 >= cap) return;
    if (*n) line[(*n)++] = '\t';
    line[(*n)++] = key;
    line[(*n)++] = '=';
    while (v[i] && *n + 2 < cap) {
        unsigned char c = (unsigned char)v[i++];
        line[(*n)++] = c < 32 ? ' ' : (char)c;
    }
    line[*n] = 0;
}

static void sbd_put_u(char *line, unsigned cap, unsigned *n, char key, unsigned v) {
    char d[12];
    unsigned k = 0;
    if (!v) d[k++] = '0';
    while (v) d[k++] = (char)('0' + v % 10), v /= 10;
    {
        char out[12];
        unsigned i;
        for (i = 0; i < k; ++i) out[i] = d[k - 1 - i];
        out[k] = 0;
        sbd_put_s(line, cap, n, key, out);
    }
}

/* One manifest line (no newline) for track t stored in file with fsize bytes. Returns its length. */
static unsigned sbd_row_text(char *line, unsigned cap, const sba_track_t *t, const char *file, unsigned fsize) {
    unsigned n = 0;
    line[0] = 0;
    sbd_put_s(line, cap, &n, 'i', t->id);
    sbd_put_s(line, cap, &n, 't', t->title);
    sbd_put_s(line, cap, &n, 'a', t->artist);
    sbd_put_s(line, cap, &n, 'l', t->album);
    sbd_put_s(line, cap, &n, 'b', t->album_id);
    sbd_put_s(line, cap, &n, 'c', t->cover);
    sbd_put_s(line, cap, &n, 'x', t->suffix);
    sbd_put_u(line, cap, &n, 's', t->seconds);
    sbd_put_u(line, cap, &n, 'n', t->track);
    sbd_put_u(line, cap, &n, 'd', t->disc);
    sbd_put_u(line, cap, &n, 'y', t->year);
    sbd_put_u(line, cap, &n, 'z', t->size);
    sbd_put_u(line, cap, &n, 'r', t->bitrate);
    sbd_put_u(line, cap, &n, 'h', t->sample_rate);
    sbd_put_u(line, cap, &n, 'q', t->bit_depth);
    sbd_put_u(line, cap, &n, 'm', t->created);
    sbd_put_u(line, cap, &n, 'f', t->starred);
    sbd_put_u(line, cap, &n, 'w', fsize);
    sbd_put_s(line, cap, &n, 'p', file);
    return n;
}

/* The value of field key in the line [p, end): copied to out (cap), 1 when present. */
static int sbd_field(const char *p, const char *end, char key, char *out, unsigned cap) {
    const char *f = p;
    while (f < end) {
        const char *e = f;
        while (e < end && *e != '\t') ++e;
        if (e - f >= 2 && f[0] == key && f[1] == '=') {
            unsigned n = (unsigned)(e - f - 2);
            if (n >= cap) n = cap - 1;
            memcpy(out, f + 2, n);
            out[n] = 0;
            return 1;
        }
        f = e + 1;
    }
    out[0] = 0;
    return 0;
}

static unsigned sbd_num(const char *p, const char *end, char key) {
    char v[16];
    unsigned r = 0, i;
    sbd_field(p, end, key, v, sizeof v);
    for (i = 0; v[i] >= '0' && v[i] <= '9'; ++i) r = r * 10 + (unsigned)(v[i] - '0');
    return r;
}

/* Parse a line into t / file / fsize; 0 when it has no id or no file name. */
static int sbd_parse_row(const char *p, const char *end, sba_track_t *t, char *file, unsigned fcap, unsigned *fsize) {
    memset(t, 0, sizeof *t);
    if (!sbd_field(p, end, 'i', t->id, sizeof t->id) || !t->id[0]) return 0;
    if (!sbd_field(p, end, 'p', file, fcap) || !file[0]) return 0;
    sbd_field(p, end, 't', t->title, sizeof t->title);
    sbd_field(p, end, 'a', t->artist, sizeof t->artist);
    sbd_field(p, end, 'l', t->album, sizeof t->album);
    sbd_field(p, end, 'b', t->album_id, sizeof t->album_id);
    sbd_field(p, end, 'c', t->cover, sizeof t->cover);
    sbd_field(p, end, 'x', t->suffix, sizeof t->suffix);
    t->seconds = sbd_num(p, end, 's');
    t->track = sbd_num(p, end, 'n');
    t->disc = sbd_num(p, end, 'd');
    t->year = sbd_num(p, end, 'y');
    t->size = sbd_num(p, end, 'z');
    t->bitrate = sbd_num(p, end, 'r');
    t->sample_rate = sbd_num(p, end, 'h');
    t->bit_depth = sbd_num(p, end, 'q');
    t->created = sbd_num(p, end, 'm');
    t->starred = (unsigned char)(sbd_num(p, end, 'f') != 0);
    *fsize = sbd_num(p, end, 'w');
    return 1;
}

/* A file name must be a plain name inside SBA_MUSIC_DIR (the manifest is a file on the card: never follow a path out of the folder). */
static int sbd_file_ok(const char *f) {
    unsigned i;
    if (!f[0] || f[0] == '.') return 0;
    for (i = 0; f[i]; ++i)
        if (f[i] == '/' || f[i] == '\\') return 0;
    return 1;
}

static int sbd_path(char *out, unsigned cap, const char *file) {
    int k = snprintf(out, cap, "%s/%s", SBA_MUSIC_DIR, file);
    return k > 0 && (unsigned)k < cap;
}

static int sbd_exists(const char *file) {
    char path[SBD_PATH];
    return sbd_file_ok(file) && sbd_path(path, sizeof path, file) && access(path, 0) == 0;
}

/* ---- reading and writing dl.idx ---- */

/* The whole file in a heap buffer (NUL terminated); NULL when it is missing, empty or too large. */
static char *sbd_slurp(const char *path, unsigned *n) {
    int fd = open(path, O_RDONLY, 0);
    long size;
    char *buf;
    unsigned got = 0;
    *n = 0;
    if (fd < 0) return (char *)0;
    size = lseek(fd, 0, 2);
    if (size <= 0 || (unsigned long)size > SBD_IDX_MAX || lseek(fd, 0, 0) < 0 ||
        !(buf = (char *)calloc((unsigned)size + 1, 1))) {
        close(fd);
        return (char *)0;
    }
    while (got < (unsigned)size) {
        int r = read(fd, buf + got, (unsigned)size - got);
        if (r <= 0) break;
        got += (unsigned)r;
    }
    close(fd);
    buf[got] = 0;
    *n = got;
    return buf;
}

/* 1 when the file exists and is larger than SBD_IDX_MAX (sbd_slurp reads it as empty). */
static int sbd_oversized(const char *path) {
    int fd = open(path, O_RDONLY, 0);
    long size;
    if (fd < 0) return 0;
    size = lseek(fd, 0, 2);
    close(fd);
    return size > 0 && (unsigned long)size > SBD_IDX_MAX;
}

/* The next line of [*p, end): its bounds without the newline; moves *p past it. 0 at the end. */
static int sbd_next(const char **p, const char *end, const char **ls, const char **le) {
    const char *s = *p, *e;
    if (s >= end) return 0;
    e = s;
    while (e < end && *e != '\n') ++e;
    *ls = s;
    *le = e;
    *p = e < end ? e + 1 : e;
    return 1;
}

/* Build an in-memory index from manifest text and swap it in. The caller holds mf. */
static void sbd_ix_set(const char *text, unsigned n) {
    sbd_ent_t *ix = (sbd_ent_t *)0, *old;
    int cnt = 0, cap = 0;
    const char *p = text, *end = text + n, *ls, *le;
    sba_track_t *t = (sba_track_t *)calloc(1, sizeof *t);
    if (t && n) {
        unsigned lines = 0, i;
        for (i = 0; i < n; ++i) lines += text[i] == '\n';
        cap = (int)(lines + 1 > SBD_ROWS ? SBD_ROWS : lines + 1);
        ix = (sbd_ent_t *)calloc((unsigned)cap, sizeof *ix);
        if (!ix) cap = 0;
        while (ix && sbd_next(&p, end, &ls, &le)) {
            char file[SBD_FILE];
            unsigned fsize;
            if (le - ls < 4 || ls[0] != 'i' || ls[1] != '=' || !sbd_parse_row(ls, le, t, file, sizeof file, &fsize) ||
                !sbd_file_ok(file))
                continue;
            if (cnt >= cap) break;
            sbd_set(ix[cnt].id, sizeof ix[cnt].id, t->id);
            sbd_set(ix[cnt].file, sizeof ix[cnt].file, file);
            ix[cnt].size = fsize;
            ix[cnt].dsd = (unsigned char)sba_is_dsd(t->suffix);
            ++cnt;
        }
    }
    free(t);
    sbd_lock();
    old = sbd.ix;
    sbd.ix = ix;
    sbd.nix = cnt;
    sbd.capix = cap;
    sbd.loaded = 1;
    sbd_unlock();
    free(old);
    sbd_bump();
}

static void sbd_load_locked(void) {
    unsigned n = 0;
    char *text = sbd_slurp(SBD_IDX, &n);
    sbd_ix_set(text ? text : "", text ? n : 0);
    free(text);
}

/* The index is loaded on first use. */
static void sbd_ensure(void) {
    if (sbd.loaded) return;
    sbd_mf_lock();
    if (!sbd.loaded) sbd_load_locked();
    sbd_mf_unlock();
}

/* Rewrite dl.idx without the rows of remove_id and with row (a manifest line; NULL for none) added. 1 on success. Takes mf. */
static int sbd_edit(const char *remove_id, const char *row) {
    unsigned n = 0, out = 0, rn = row ? sbd_len(row) : 0;
    char *text, *buf, row_id[SBA_ID];
    const char *p, *end, *ls, *le;
    int ok;
    row_id[0] = 0;
    if (row) sbd_field(row, row + rn, 'i', row_id, sizeof row_id);
    sbd_mf_lock();
    if (sbd_oversized(SBD_IDX)) { /* never overwrite a manifest that cannot be read back */
        sbd_mf_unlock();
        return 0;
    }
    text = sbd_slurp(SBD_IDX, &n);
    buf = (char *)calloc(n + rn + sizeof SBD_HEAD + 4, 1);
    if (!buf) {
        free(text);
        sbd_mf_unlock();
        return 0;
    }
    memcpy(buf, SBD_HEAD, sizeof SBD_HEAD - 1);
    out = sizeof SBD_HEAD - 1;
    p = text ? text : "";
    end = p + n;
    while (sbd_next(&p, end, &ls, &le)) {
        char id[SBA_ID];
        if (le - ls < 4 || ls[0] != 'i' || ls[1] != '=') continue; /* the head line, blank or odd lines go */
        if (remove_id && sbd_field(ls, le, 'i', id, sizeof id) && sbd_same(id, remove_id)) continue;
        if (row_id[0] && sbd_field(ls, le, 'i', id, sizeof id) && sbd_same(id, row_id))
            continue; /* the row being added replaces an older one of the same track */
        memcpy(buf + out, ls, (unsigned)(le - ls));
        out += (unsigned)(le - ls);
        buf[out++] = '\n';
    }
    if (row) {
        memcpy(buf + out, row, rn);
        out += rn;
        buf[out++] = '\n';
    }
    ok = pod_card_write(SBA_DIR, SBD_IDX, SBD_IDX_TMP, buf, out, (const void *)0, 0) == 0;
    if (ok) sbd_ix_set(buf, out);
    free(buf);
    free(text);
    sbd_mf_unlock();
    return ok;
}

/* The index entry of a track, copied out (the array can move). 1 found. */
static int sbd_find(const char *id, sbd_ent_t *out) {
    int i, r = 0;
    sbd_ensure();
    sbd_lock();
    for (i = 0; i < sbd.nix; ++i)
        if (sbd_same(sbd.ix[i].id, id)) {
            memcpy(
                out, &sbd.ix[i],
                sizeof *out); /* (no struct assignment: the compiler would call a memcpy the payload does not have) */
            r = 1;
            break;
        }
    sbd_unlock();
    return r;
}

/* The index entry that owns a file name (a name collision between two tracks). */
static int sbd_owner(const char *file, char *id, unsigned cap) {
    int i, r = 0;
    sbd_lock();
    for (i = 0; i < sbd.nix; ++i)
        if (sbd_same(sbd.ix[i].file, file)) {
            sbd_set(id, cap, sbd.ix[i].id);
            r = 1;
            break;
        }
    sbd_unlock();
    return r;
}

/* ---- the file name of a track (the PR's layout: <8 hex of the id>-<title>.<suffix>) ---- */

static unsigned sbd_hash(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h;
}

/* variant 0: "<hash>-<title>.<ext>"; n > 0: "<hash>-<title> (n+1).<ext>". 1 on success. */
static int sbd_file_name(const sba_track_t *t, int variant, char *out, unsigned cap) {
    char title[SBD_TITLE + 4], ext[SBA_SUFFIX];
    unsigned i, n = 0, k;
    for (i = 0; t->title[i] && n < SBD_TITLE; ++i) {
        unsigned c = (unsigned char)t->title[i];
        title[n++] = (c < 32 || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' ||
                      c == '>' || c == '|')
                         ? '_'
                         : (char)c;
    }
    while (n && ((unsigned char)t->title[n] & 0xc0) == 0x80) --n; /* the cut fell inside a character: drop it */
    if (!n) {
        memcpy(title, "track", 5);
        n = 5;
    }
    title[n] = 0;
    for (i = 0, k = 0; t->suffix[i] && k + 1 < sizeof ext; ++i) {
        unsigned c = (unsigned char)t->suffix[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) ext[k++] = (char)c;
    }
    if (!k) {
        memcpy(ext, "audio", 5);
        k = 5;
    }
    ext[k] = 0;
    if (variant > 0)
        k = (unsigned)snprintf(out, cap, "%08x-%s (%d).%s", sbd_hash(t->id), title, variant + 1, ext);
    else
        k = (unsigned)snprintf(out, cap, "%08x-%s.%s", sbd_hash(t->id), title, ext);
    return (int)k > 0 && k < cap;
}

/* ---- the queue ---- */

/* The slot of an id (any state), -1 none. The caller holds lock. */
static int sbd_slot(const char *id) {
    int i;
    for (i = 0; i < SBA_DLMAX; ++i)
        if (sbd.q[i].state && sbd_same(sbd.q[i].id, id)) return i;
    return -1;
}

static void sbd_slot_free(sbd_slot_t *s) {
    sba_track_t *t = s->t;
    memset(s, 0, sizeof *s);
    free(t);
}

/* ---- progress ---- */

/* The transfer-info hook for the download sink (sbapi.c's hook gives every sink to this first). Non-zero aborts. */
int sba_dl_xfer(void *ctx, long long total, long long now, long long up_total, long long up_now) {
    sbn_sink_t *s = (sbn_sink_t *)ctx;
    long long resume, got;
    unsigned g, t, step;
    (void)up_total;
    (void)up_now;
    if (!s || s != sbd.sink) return 0;
    if (sbd.stop) return 1;
    if (now < 0) return 0;
    resume = s->resume_offset;
    got = now + (resume > 0 ? resume : 0);
    if (resume > 0) { /* only a 206 for exactly our range tells the whole size */
        if (!s->range_seen || s->range_start != resume || s->range_total <= 0)
            total = 0;
        else
            total = s->range_total;
    }
    if (total < got) total = 0;
    g = got > 0xffffffffLL ? 0xffffffffu : (unsigned)got;
    t = total > 0xffffffffLL ? 0xffffffffu : (unsigned)total;
    sbd.got = g;
    sbd.total = t;
    step = t ? (g >> 10) * 50 / ((t >> 10) ? (t >> 10) : 1)
             : 1000 + (g >> 20); /* every 2 % of the file, a MB when its size is not known */
    if (step != sbd.step) {
        sbd.step = step;
        sbd_bump();
    }
    return 0;
}

/* ---- the worker ---- */

static int sbd_http_code(const sbn_sink_t *s, unsigned free_kb_known, unsigned free_kb) {
    long st = s->http_status;
    int rc = s->curl_result;
    if (rc == CURLE_SSL_CACERT || rc == CURLE_SSL_CONNECT_ERROR || rc == CURLE_PEER_FAILED_VERIFICATION ||
        rc == CURLE_SSL_CERTPROBLEM || rc == CURLE_SSL_CIPHER || rc == CURLE_SSL_ISSUER_ERROR)
        return SBA_CERT;
    if (rc == CURLE_SSL_CACERT_BADFILE) return SBA_NOCERT;
    switch (s->werr) { /* what the card side said (sbnet.h SBN_W_*), before what the network said */
    case SBN_W_SPACE:
        return SBA_CARDFULL;
    case SBN_W_CARD:
        return SBA_STORAGE;
    case SBN_W_IO:
        return SBA_WRITE;
    case SBN_W_RESPONSE: /* the headers were not those of the audio file asked for (a page, a JSON error, a resume the server answered differently): nothing was written */
        if (st >= 200 && st < 300) return SBA_NOTAUDIO;
        break;
    }
    if (rc == CURLE_WRITE_ERROR && free_kb_known && free_kb <= SBA_RESERVE_KB) return SBA_CARDFULL;
    if (rc == 0 && st == 0)
        return SBA_STORAGE; /* sbn_download stopped before it sent anything: the .part file could not be opened */
    if (rc == 0) return SBA_NOTAUDIO; /* the answer was 2xx but not the whole audio file */
    if (st == 401 || st == 403) return SBA_AUTH;
    if (st == 404 || st == 410) return SBA_NOTFOUND;
    if (st >= 400) return SBA_HTTP;
    if (rc == CURLE_WRITE_ERROR) return SBA_WRITE;
    return SBA_NET;
}

/* One track to the card. Returns SBA_OK, SBA_CANCELLED or the failure; *size the file's bytes. */
static int sbd_run(const sba_track_t *t, char *file, unsigned *size) {
    sbn_server_t srv;
    char base[SBA_URL], user[SBA_TEXT], auth[SBA_TEXT], url[SBA_URL + 128], part[SBD_PATH], final[SBD_PATH],
        owner[SBA_ID], identity[SBN_IDENTITY];
    unsigned kb = 0, need;
    int free_ok;
    int v, g, ok, resumable = -1, rc, code;
    sbn_sink_t *sink;
    g = sba_guard();
    if (g) return g;
    if (sba_net_open(base, sizeof base, user, sizeof user, auth, sizeof auth) != SBA_OK) return SBA_NOCONF;
    if (!pod_card_mounted() || !pn_free_kb("/mnt/mmc", &kb)) return SBA_STORAGE;
    mkdir("/mnt/mmc/.m1plus", 0755);
    mkdir(SBA_MUSIC_DIR, 0775);
    /* the name: a free one, or the one an earlier download of this track left (the file is never overwritten) */
    for (v = 0, ok = 0; v < 9; ++v) {
        if (!sbd_file_name(t, v, file, SBD_FILE) || !sbd_path(final, sizeof final, file)) return SBA_STORAGE;
        if (access(final, 0) != 0) {
            ok = 1;
            break;
        }
        if (!sbd_owner(file, owner, sizeof owner) ||
            sbd_same(owner,
                     t->id)) { /* ours, or a file the manifest does not know: it stays as it is, the track is done */
            ok = 2;
            break;
        }
    }
    if (!ok) return SBA_STORAGE;
    if (ok == 2) { /* adopt: the file is on the card */
        int fd = open(final, O_RDONLY, 0);
        long len = fd >= 0 ? lseek(fd, 0, 2) : 0;
        if (fd >= 0) close(fd);
        *size = len > 0 ? (unsigned)len : 0;
        sbd.got = sbd.total = *size;
        return SBA_OK;
    }
    if (snprintf(part, sizeof part, "%s.part", final) >= (int)sizeof part) return SBA_STORAGE;
    need = t->size >> 10;
    if (kb <= SBA_RESERVE_KB || (need && kb - SBA_RESERVE_KB < need)) return SBA_CARDFULL;
    srv.base = base, srv.user = user, srv.auth = auth;
    if (sbn_url(url, sizeof url, srv, "download", t->id, (const char *)0)) return SBA_STORAGE;
    sink = (sbn_sink_t *)calloc(1, sizeof *sink);
    if (!sink) return SBA_MEM;
    sbn_sink_reset(sink);
    sbd.sink = sink;
    /* who the .part file is for: a resume record of another server, user or track is not followed */
    identity[0] = 0;
    if (snprintf(identity, sizeof identity, "%s\n%s\n%s", base, user, t->id) >= (int)sizeof identity) identity[0] = 0;
    rc = sbn_download(url, part, final, SBA_MUSIC_DIR, identity[0] ? identity : (const char *)0, sink, &resumable);
    sbd.sink = (sbn_sink_t *)0;
    if (rc == 1) {
        *size = (unsigned)(sink->resume_offset + sink->written);
        sbd.got = sbd.total = *size;
        sbn_sink_free(sink);
        free(sink);
        return SBA_OK;
    }
    free_ok = pn_free_kb("/mnt/mmc", &kb);
    code = sbd_http_code(sink, free_ok, kb);
    sbd.status = (int)sink->http_status;
    if (sbd.stop || sink->curl_result == CURLE_ABORTED_BY_CALLBACK) code = SBA_CANCELLED;
    sbn_sink_free(sink);
    free(sink);
    return code;
}

static void *sbd_main(void *arg) {
    (void)arg;
    for (;;) {
        int i, best = -1, code;
        unsigned size = 0;
        char file[SBD_FILE];
        sba_track_t *t;
        sbd_lock();
        for (i = 0; i < SBA_DLMAX; ++i)
            if (sbd.q[i].state == SBA_DL_WAIT && (best < 0 || (int)(sbd.q[i].seq - sbd.q[best].seq) < 0)) best = i;
        if (best < 0) { /* nothing left: the worker ends under the lock, so an add that follows starts a new one */
            sbd.busy = 0;
            sbd_unlock();
            sbd_bump();
            return (void *)0;
        }
        sbd.q[best].state = SBA_DL_ACTIVE;
        sbd.q[best].code = 0;
        sbd.stop = 0;
        sbd.got = sbd.total = 0;
        sbd.step = ~0u;
        t = sbd.q[best].t;
        sbd_unlock();
        sbd_bump();
        file[0] = 0;
        code = t ? sbd_run(t, file, &size) : SBA_MEM;
        if (code == SBA_OK) {
            char *row = (char *)calloc(SBD_LINE, 1);
            if (!row)
                code = SBA_MEM;
            else {
                sbd_row_text(row, SBD_LINE, t, file, size);
                if (!sbd_edit((const char *)0, row))
                    code = SBA_STORAGE; /* the file is on the card; the next add finds and adopts it */
                free(row);
            }
        }
        if (code == SBA_OK && sba_is_dsd(t->suffix) && pod_card_mounted())
            scanSpecFolder(SBA_MUSIC_DIR, 0); /* stock's library learns the new DSD file, as the PR does */
        sbd_lock();
        if (code == SBA_OK || code == SBA_CANCELLED)
            sbd_slot_free(&sbd.q[best]);
        else {
            sbd.q[best].state = SBA_DL_FAILED;
            sbd.q[best].code = code;
            sbd.fail_code = code;
            sbd.fail_status = code == SBA_HTTP ? sbd.status : 0;
            sbd.fail_at = time((long *)0);
            free(sbd.q[best].t);
            sbd.q[best].t = (sba_track_t *)0;
        }
        sbd_unlock();
        sbd_bump();
    }
}

/* ---- the API ---- */

int sba_dl_add(const sba_track_t *t) {
    sbd_ent_t e;
    int i, slot = -1, g, start = 0;
    unsigned kb = 0, seq;
    sba_track_t *copy;
    if (!t || !t->id[0]) return SBA_PARSE;
    if (sbd_find(t->id, &e)) {
        if (sbd_exists(e.file)) return SBA_OK; /* on the card already */
        sbd_edit(t->id, (const char *)0); /* deleted by hand: the row goes and the track downloads again */
    }
    sbd_lock();
    i = sbd_slot(t->id);
    if (i >= 0 && sbd.q[i].state != SBA_DL_FAILED) { /* waiting or running: asked twice is once */
        if (sbd.q[i].state == SBA_DL_ACTIVE && sbd.stop)
            sbd.stop = 0; /* (a cancel the worker has not seen yet is withdrawn) */
        sbd_unlock();
        return SBA_OK;
    }
    sbd_unlock();
    g = sba_guard();
    if (g) return g;
    if (!pod_card_mounted() || !pn_free_kb("/mnt/mmc", &kb)) return SBA_STORAGE;
    if (kb <= SBA_RESERVE_KB || (t->size >> 10) > kb - SBA_RESERVE_KB) return SBA_CARDFULL;
    copy = (sba_track_t *)calloc(1, sizeof *copy);
    if (!copy) return SBA_MEM;
    memcpy(copy, t, sizeof *copy);
    sbd_lock();
    i = sbd_slot(t->id); /* (the same id is now a failed slot, or nothing) */
    if (i >= 0) slot = i;
    for (i = 0; slot < 0 && i < SBA_DLMAX; ++i)
        if (!sbd.q[i].state) slot = i;
    for (i = 0; slot < 0 && i < SBA_DLMAX; ++i) /* the oldest failed one gives way */
        if (sbd.q[i].state == SBA_DL_FAILED && (slot < 0 || (int)(sbd.q[i].seq - sbd.q[slot].seq) < 0)) slot = i;
    if (slot < 0) {
        sbd_unlock();
        free(copy);
        return SBA_QFULL;
    }
    sbd_slot_free(&sbd.q[slot]);
    seq = ++sbd.seq;
    sbd_set(sbd.q[slot].id, sizeof sbd.q[slot].id, t->id);
    sbd.q[slot].t = copy;
    sbd.q[slot].seq = seq;
    sbd.q[slot].state = SBA_DL_WAIT;
    if (!sbd.busy) sbd.busy = 1, start = 1;
    sbd_unlock();
    sbd_bump();
    if (start) {
        unsigned long th = 0;
        if (pthread_create(&th, (const void *)0, sbd_main, (void *)0) != 0) {
            sbd_lock();
            sbd.busy = 0;
            sbd_slot_free(&sbd.q[slot]);
            sbd_unlock();
            sbd_bump();
            return SBA_MEM;
        }
        pthread_detach(th);
    }
    return SBA_OK;
}

static void sbd_cancel_locked(int i) {
    if (sbd.q[i].state == SBA_DL_ACTIVE)
        sbd.stop = 1;
    else
        sbd_slot_free(&sbd.q[i]); /* waiting or failed */
}

void sba_dl_cancel(const char *id) {
    int i;
    if (!id) return;
    sbd_lock();
    i = sbd_slot(id);
    if (i >= 0) sbd_cancel_locked(i);
    sbd_unlock();
    sbd_bump();
}

void sba_dl_cancel_all(void) {
    int i;
    sbd_lock();
    for (i = 0; i < SBA_DLMAX; ++i)
        if (sbd.q[i].state) sbd_cancel_locked(i);
    sbd_unlock();
    sbd_bump();
}

int sba_dl_failure(int *status) {
    int code;
    sbd_lock();
    code = sbd.fail_code;
    if (status) *status = sbd.fail_status;
    if (code && (long)time((long *)0) - sbd.fail_at > SBD_FAIL_FRESH_S)
        code = 0; /* nobody was looking: too old to be news */
    sbd.fail_code = sbd.fail_status = 0;
    sbd_unlock();
    return code;
}

int sba_dl_state(const char *id, int *code, unsigned *got, unsigned *total) {
    int i, r = SBA_DL_NONE;
    sbd_ent_t e;
    unsigned g = 0, tt = 0;
    if (!id || !id[0]) return SBA_DL_NONE;
    sbd_lock();
    i = sbd_slot(id);
    if (i >= 0) {
        r = sbd.q[i].state;
        if (r == SBA_DL_FAILED && code) *code = sbd.q[i].code;
        if (r == SBA_DL_ACTIVE) {
            if (sbd.stop)
                r = SBA_DL_NONE; /* cancelled: the worker is about to drop it */
            else
                g = sbd.got, tt = sbd.total;
        }
    }
    sbd_unlock();
    if (r == SBA_DL_NONE &&
        sbd_find(id,
                 &e)) { /* (memory only: a file deleted by hand shows until sba_dl_path or sba_downloaded finds out) */
        r = SBA_DL_DONE;
        g = tt = e.size;
    }
    if (got) *got = g;
    if (total) *total = tt < g ? 0 : tt;
    return r;
}

unsigned sba_dl_gen(void) { return sbd.gen; }

int sba_dl_busy(void) { return sbd.busy; }

int sba_dl_path(const char *id, char *path, unsigned cap) {
    sbd_ent_t e;
    char full[SBD_PATH];
    if (!id || !sbd_find(id, &e)) return 0;
    if (!sbd_path(full, sizeof full, e.file) || !sbd_file_ok(e.file)) return 0;
    if (access(full, 0) != 0) {
        if (pod_card_mounted())
            sbd_edit(
                id,
                (const char
                     *)0); /* gone: the row goes (never while the card is out: it would look like all files are gone) */
        return 0;
    }
    if (path) {
        unsigned n = sbd_len(full);
        if (n >= cap) return 0;
        memcpy(path, full, n + 1);
    }
    return 1;
}

int sba_dl_delete(const char *id) {
    sbd_ent_t e;
    char full[SBD_PATH], part[SBD_PATH + 16];
    int r = 0;
    if (!id || !id[0]) return 0;
    sba_dl_cancel(id);
    if (!sbd_find(id, &e)) return 0;
    if (sbd_file_ok(e.file) && sbd_path(full, sizeof full, e.file)) {
        if (unlink(full) != 0 && access(full, 0) == 0) return -1;
        if (snprintf(part, sizeof part, "%s.part", full) < (int)sizeof part) unlink(part);
        if (snprintf(part, sizeof part, "%s.part.etag", full) < (int)sizeof part) unlink(part);
    }
    if (!sbd_edit(id, (const char *)0)) r = -1;
    sbd_bump();
    return r;
}

int sba_downloaded(sba_tracks_t *out) {
    unsigned n = 0, lines = 0, i, cnt = 0, fsize, ngone = 0;
    char *text;
    const char *p, *end, *ls, *le;
    sba_track_t *v, *t;
    char file[SBD_FILE], gone[8][SBA_ID];
    out->n = 0;
    out->v = (sba_track_t *)0;
    sbd_ensure();
    text = sbd_slurp(SBD_IDX, &n);
    if (!text) return 0;
    for (i = 0; i < n; ++i) lines += text[i] == '\n';
    v = (sba_track_t *)calloc(lines + 1, sizeof *v);
    t = (sba_track_t *)calloc(1, sizeof *t);
    if (!v || !t) {
        free(v);
        free(t);
        free(text);
        return -1;
    }
    p = text;
    end = text + n;
    while (sbd_next(&p, end, &ls, &le)) {
        if (le - ls < 4 || ls[0] != 'i' || ls[1] != '=' || !sbd_parse_row(ls, le, t, file, sizeof file, &fsize) ||
            !sbd_file_ok(file))
            continue;
        if (!sbd_exists(
                file)) { /* deleted by hand: dropped below (some at a time; never while the card is out, when every file looks gone) */
            if (ngone < 8 && pod_card_mounted()) sbd_set(gone[ngone++], SBA_ID, t->id);
            continue;
        }
        memcpy(&v[cnt++], t, sizeof *t);
    }
    free(t);
    free(text);
    for (i = 0; i < ngone; ++i) sbd_edit(gone[i], (const char *)0);
    out->n = (int)cnt;
    if (cnt)
        out->v = v;
    else
        free(v);
    return (int)cnt;
}
