/* Navidrome / Subsonic data layer: conf, guard, cache files, the metadata worker, requests, covers, stream addresses and the queue map (see patch/sbapi.h and
 * docs/modules/subsonic.md "Data and cache").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). Navidrome support began as a pull request by Gaurav Mishra (its patch/subsonic.c, MIT, removed in the rebuild); the credentials file and the filename and
 * queue-id rules here are that work's.
 *
 * The model is patch/pcnet.c's: the pages read cache files and the status record on their own timers; one detached worker thread runs the queued requests one at a time and then ends;
 * it touches no widget and calls no stock function, writes every cache file atomically (.tmp, fsync, rename) and moves the generation counter after each (a store barrier first).
 * Only demo's own imports are used (libcurl through patch/sbnet.c, pthread_create / pthread_detach, open / read / write / lseek / fsync / rename / unlink / mkdir / opendir).
 *
 * The cache file: a 16-byte header (the letters "SBA1", the kind, the row size, flags), then the rows of the sba_*_t struct as they are in memory. The row count is the size; a file whose
 * size, kind or row size does not fit is read as empty. flags: songs.idx bit 0 = the last page was full (more to ask).
 */
#include <limits.h>
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "covercache.h"
#include "sbnet.h"
#include "sbapi.h"

extern int pn_free_kb(const char *path, unsigned *kb);

#define SBA_MIN_EPOCH 1750000000u /* a clock before this was never set (as patch/pcnet.h PN_MIN_EPOCH) */
#define SBA_SLOTS SBA_QMAX
#define SBA_STATS 48
#define SBA_CONF_URL 256
#define SBA_CONF_USER 64
#define SBA_CONF_PASS 128
#define SBA_CONF_MAX 500
#define SBA_PATH 192
#define SBA_TERM 80
#define SBA_STARRED_MAX 3000 /* tracks of getStarred2 kept (the answer is one response of at most SBN_RESPONSE_MAX) */
#define SBA_ARTISTS_MAX 6000
#define SBA_PLAYLISTS_MAX 500
#define SBA_ALBUM_TRACKS 3000 /* tracks of one getAlbum / getPlaylist kept */
#define SBA_KEEP_BODY \
    (256u * \
     1024) /* a response buffer larger than this is freed after the request; a phase-2 page (about 140 KB) is kept */
#define SBA_SEARCH_N 20
#define SBA_CHUNK_BYTES 16384u /* bytes copied at a time when songs.part is cut back to whole rows */
#define SBA_CHUNK 16 /* rows read at a time when a file is walked */
#define SBA_COPY_BUF 32768
#define SBA_STAR_EV 16 /* star events kept while phase 2 pages the songs */
#define SBA_OV 32 /* stars the page side shows before the worker has written them (the star overlay) */

/* A trial ping (sba_ping_try) carries its own login in a heap block (the slot's arg, freed by the worker or by a cancel) and its own request id (the slot's id "t<n>"). */
typedef struct {
    char url[SBA_CONF_URL], user[SBA_CONF_USER], auth[SBA_CONF_PASS];
} sba_trial_t;

enum { SBK_TRACK = 1, SBK_ALBUM, SBK_ARTIST, SBK_PLAYLIST, SBK_ACOV }; /* the cache file kinds */
enum { SLOT_FREE = 0, SLOT_WAIT = 1, SLOT_ACTIVE = 2, SLOT_FILL = 3 };

typedef struct {
    char magic[4];
    unsigned kind, rowsize, flags;
} sba_head_t;

typedef struct {
    volatile unsigned state;
    unsigned seq, arg;
    int kind;
    char id[SBA_ID];
    char term[SBA_TERM];
} sba_slot_t;

typedef struct {
    int kind;
    unsigned key;
    volatile int state, code;
} sba_stat_t;

typedef struct {
    char id[SBA_ID], cover[SBA_ID], album_id[SBA_ID], suffix[SBA_SUFFIX];
    int rec;
    unsigned size; /* the track's bytes on the server, 0 unknown (Now Playing's File Size line) */
} sba_map_t;

/* albcov.idx, written with albums.idx by every sync: one row per album, in albums.idx order, so a track finds its album's cover without reading the 0.65 KB album rows. The album id is two hashes
 * (h1 sba_fnv, h2 sba_hash2: a clash of both is not a worry at 20,000 albums), cover is sba_fnv of the album's coverArt id (0 = the album has none), row is its place in albums.idx (read back only to
 * ask for the cover id when the file is not cached). The page side loads it whole, sorted by (h1, h2): 16 bytes an album, 80 KB for 5,000 albums, 320 KB at SBA_MAX_ALBUMS. */
typedef struct {
    unsigned h1, h2, cover, row;
} sba_acov_t;

/* The ids of starred.idx as the page side holds them: two hashes each (sba_fnv, sba_hash2), sorted. */
typedef struct {
    unsigned h1, h2;
} sba_hh_t;

static struct {
    int loaded; /* the conf was read (or set) */
    char url[SBA_CONF_URL], user[SBA_CONF_USER], auth[SBA_CONF_PASS];
    sba_slot_t q[SBA_SLOTS];
    unsigned seq, stat_next;
    sba_stat_t st[SBA_STATS];
    volatile int busy, net;
    volatile unsigned gen, cancel, mine,
        cgen; /* mine: the cancel count the running request started at; cgen: covers finished (kept apart from gen, which a list change moves) */
    void
        *volatile sink; /* the running request's sink: the cancel check answers only for it (a download's sink is sbdl.c's) */
    sba_map_t *map;
    int map_n, map_cap;
    char now[SBA_PATH];
    char host[SBA_CONF_URL];
    unsigned trial_n,
        trial_last; /* trial pings asked (the next request id), and the id of the latest one that was queued */
    volatile unsigned
        search_done; /* the hash of the term of the search3 that finished last (an answer or a failure), see sba_search_is */
    /* Phase 2 (the background fill, below "Phase 2"); appended last so the members above keep their offsets. bg_want: phase 2 has work to look for (set by a sync and by sba_bg_kick, cleared by the worker
     * when it has none, by an error run and by sba_cancel); bg_kind / bg_done / bg_total: the progress the root page reads; bg_run: the worker is inside a request of phase 2 (a waiting request cuts it off) */
    volatile int bg_want, bg_kind, bg_run;
    volatile unsigned bg_done, bg_total, bg_gen;
    volatile unsigned
        star_n; /* stars and unstars the cache took: the last SBA_STAR_EV are kept for a songs.idx that phase 2 replaces */
    struct {
        char id[SBA_ID];
        unsigned char on;
    } star_ev[SBA_STAR_EV];
    sba_acov_t *
        acov; /* albcov.idx as the page side holds it (sorted; NULL = none or no memory), its row count, and the agen it was read at + 1 (0 = never read) */
    unsigned acov_n, acov_seen;
    /* The star overlay: a star the page side took and the worker has not finished (files edited, answer in). pend = requests of that id not finished; on = the latest wish; a free entry has id[0] 0.
     * Guarded by ov_lock (the page side sets and reads it, the worker drops it). */
    struct {
        char id[SBA_ID];
        unsigned char on, pend;
    } ov[SBA_OV];
    volatile int ov_lock;
    volatile unsigned
        agen; /* moves whenever a sync replaced albcov.idx or the cache was cleared: the page side reads it again */
    /* The starred ids (starred.idx is the truth for every heart; page side only): the sorted hashes, their count, the sgen they were read at + 1 (0 = never read) and whether the file was readable
     * (sset_ok 0: apply nothing). sgen moves whenever the worker commits starred.idx (the sync's store, sba_track_edit) and on a cache clear. */
    sba_hh_t *sset;
    unsigned sset_n, sset_seen;
    int sset_ok;
    volatile unsigned sgen;
} sba __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Small helpers
 */
static unsigned sba_len(const char *s) { return sbn_len(s); }

static void sba_copy(char *out, unsigned cap, const char *s) {
    unsigned n = sba_len(s);
    if (!cap) return;
    if (n >= cap) n = cap - 1;
    memcpy(out, s, n);
    out[n] = 0;
}

static int sba_same(const char *x, const char *y) {
    while (*x && *x == *y) ++x, ++y;
    return *x == *y;
}

static unsigned sba_fnv(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h;
}

static unsigned sba_hash2(const char *s) {
    unsigned h = 5381;
    while (*s) h = h * 33 ^ (unsigned char)*s++;
    return h;
}

static void sba_bump(void) {
    __sync_synchronize();
    ++sba.gen;
}

static void sba_sbump(void) {
    __sync_synchronize();
    ++sba.sgen;
}

static void sba_cbump(void) {
    __sync_synchronize();
    ++sba.cgen;
}

unsigned sba_gen(void) { return sba.gen; }
unsigned sba_cover_gen(void) { return sba.cgen; }

/* "<dir>/<id><ext>" with the id made filename-safe: an id with anything but letters, digits, '-' and '_' (or one that is too long) is replaced by x<hash>. */
static int sba_idpath(char *out, unsigned cap, const char *dir, const char *id, const char *ext) {
    char name[SBA_ID + 12];
    unsigned i, n = sba_len(id);
    int safe = n > 0 && n < SBA_ID;
    for (i = 0; safe && i < n; ++i) {
        char c = id[i];
        safe = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
    }
    if (safe)
        sba_copy(name, sizeof name, id);
    else
        snprintf(name, sizeof name, "x%08x", sba_fnv(id));
    i = (unsigned)snprintf(out, cap, "%s/%s%s", dir, name, ext);
    return i < cap ? 0 : -1;
}

/* ---------------------------------------------------------------------------
 * Files
 */
static void sba_dirs(void) {
    mkdir(CARD_DIR, 0755);
    mkdir(SBA_DIR, 0755);
    mkdir(SBA_DIR "/al", 0755);
    mkdir(SBA_DIR "/ar", 0755);
    mkdir(SBA_DIR "/pl", 0755);
    mkdir(SBA_COVER_DIR, 0755);
}

static int sba_read_all(int fd, void *buf, unsigned n) {
    unsigned got = 0;
    while (got < n) {
        int r = read(fd, (char *)buf + got, n - got);
        if (r <= 0) return 0;
        got += (unsigned)r;
    }
    return 1;
}

/* The header of a cache file and its row count: 1 and *rows when it fits kind and rowsize. */
static int sba_head(int fd, unsigned kind, unsigned rowsize, unsigned *rows, unsigned *flags) {
    sba_head_t h;
    long size;
    if (read(fd, &h, sizeof h) != (int)sizeof h) return 0;
    if (h.magic[0] != 'S' || h.magic[1] != 'B' || h.magic[2] != 'A' || h.magic[3] != '1' || h.kind != kind ||
        h.rowsize != rowsize)
        return 0;
    size = lseek(fd, 0, 2);
    if (size < (long)sizeof h || (unsigned)(size - (long)sizeof h) % rowsize) return 0;
    if (lseek(fd, (long)sizeof h, 0) != (long)sizeof h) return 0;
    *rows = (unsigned)(size - (long)sizeof h) / rowsize;
    if (flags) *flags = h.flags;
    return 1;
}

/* A whole cache file into the heap: the row count (0 when it is missing or does not fit), -1 for no memory. *v is NULL for 0. */
static int sba_load(const char *path, unsigned kind, unsigned rowsize, unsigned max, void **v, unsigned *flags) {
    unsigned rows;
    int fd = open(path, O_RDONLY, 0);
    *v = (void *)0;
    if (flags) *flags = 0;
    if (fd < 0) return 0;
    if (!sba_head(fd, kind, rowsize, &rows, flags) || !rows) {
        close(fd);
        return 0;
    }
    if (rows > max) rows = max;
    *v = calloc(rows, rowsize);
    if (!*v) {
        close(fd);
        return -1;
    }
    if (!sba_read_all(fd, *v, rows * rowsize)) {
        free(*v);
        *v = (void *)0;
        rows = 0;
    }
    close(fd);
    return (int)rows;
}

typedef struct {
    int fd;
    char path[SBA_PATH], tmp[SBA_PATH + 8];
} sba_w_t;

/* A cache file being written: a temp file next to path with the header. SBA_OK, SBA_STORAGE, SBA_CARDFULL. */
static int sba_wopen(sba_w_t *w, const char *path, unsigned kind, unsigned rowsize, unsigned flags) {
    sba_head_t h;
    unsigned kb = 0;
    w->fd = -1;
    if (!pod_card_mounted()) return SBA_STORAGE;
    sba_dirs();
    if (pn_free_kb(SBA_DIR, &kb) && kb < SBA_CACHE_RESERVE_KB) return SBA_CARDFULL;
    sba_copy(w->path, sizeof w->path, path);
    if (snprintf(w->tmp, sizeof w->tmp, "%s.tmp", path) >= (int)sizeof w->tmp) return SBA_STORAGE;
    w->fd = open(w->tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (w->fd < 0) return SBA_STORAGE;
    h.magic[0] = 'S', h.magic[1] = 'B', h.magic[2] = 'A', h.magic[3] = '1';
    h.kind = kind, h.rowsize = rowsize, h.flags = flags;
    if (!sbn_write_all(w->fd, &h, sizeof h)) {
        close(w->fd);
        unlink(w->tmp);
        w->fd = -1;
        return SBA_STORAGE;
    }
    return SBA_OK;
}

static int sba_wput(sba_w_t *w, const void *rows, unsigned bytes) {
    return !bytes || sbn_write_all(w->fd, rows, bytes);
}

static void sba_wabort(sba_w_t *w) {
    if (w->fd < 0) return;
    close(w->fd);
    unlink(w->tmp);
    w->fd = -1;
}

/* fsync, close and rename onto the file. SBA_OK or SBA_STORAGE (nothing left behind). */
static int sba_wcommit(sba_w_t *w) {
    int ok = fsync(w->fd) == 0;
    ok = close(w->fd) == 0 && ok;
    w->fd = -1;
    if (ok && !pod_card_mounted()) ok = 0;
    if (ok && rename(w->tmp, w->path)) ok = 0;
    if (!ok) unlink(w->tmp);
    return ok ? SBA_OK : SBA_STORAGE;
}

/* A whole list in one go. */
static int sba_wlist(const char *path, unsigned kind, unsigned rowsize, unsigned flags, const void *rows, unsigned n) {
    sba_w_t w;
    int code = sba_wopen(&w, path, kind, rowsize, flags);
    if (code) return code;
    if (!sba_wput(&w, rows, n * rowsize)) {
        sba_wabort(&w);
        return SBA_STORAGE;
    }
    return sba_wcommit(&w);
}

/* A small text file (the conf, sync.txt) atomically, mode given. */
static int sba_wtext(const char *path, const char *tmp, const char *text, unsigned n, unsigned mode) {
    int fd, ok;
    if (!pod_card_mounted()) return SBA_STORAGE;
    mkdir(CARD_DIR, 0755);
    fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, mode);
    if (fd < 0) return SBA_STORAGE;
    ok = sbn_write_all(fd, text, n) && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (ok && rename(tmp, path)) ok = 0;
    if (!ok) unlink(tmp);
    return ok ? SBA_OK : SBA_STORAGE;
}

/* The id (the struct's first member) of the row a walk is on. */
static int sba_row_is(const void *row, const char *id) { return sba_same((const char *)row, id); }

/* Set the starred flag of the track rows with that id in a cache file, in place: the file is read to find the rows and only the flag byte of a row that must change is written (lseek + write at
 * its offset). Nothing is copied, so a star costs a read of the file and no rewrite (a 50,000-song songs.idx is 41 MB), and a file that does not have the row is left untouched. A one-byte
 * write at a fixed offset is atomic for every reader (a page loading the file sees the old or the new flag), and the file is only ever appended to (songs.part) or replaced whole by rename,
 * both by the metadata worker, which is also the only caller of this (sba_star_files), so nothing replaces the file under the descriptor. 1 changed, 0 not, -1 failed. */
static int sba_track_flag(const char *path, const char *id, int on) {
    sba_track_t *rows;
    unsigned n, i, row0 = 0, changed = 0;
    int fd, bad = 0;
    if (!pod_card_mounted()) return -1;
    fd = open(path, O_RDWR, 0);
    if (fd < 0) return 0;
    if (!sba_head(fd, SBK_TRACK, sizeof *rows, &n, (unsigned *)0)) {
        close(fd);
        return 0;
    }
    rows = calloc(SBA_CHUNK, sizeof *rows);
    if (!rows) {
        close(fd);
        return -1;
    }
    while (n && !bad) {
        unsigned take = n < SBA_CHUNK ? n : SBA_CHUNK, wrote = 0;
        unsigned char flag = (unsigned char)(on != 0);
        if (!sba_read_all(fd, rows, take * (unsigned)sizeof *rows)) {
            bad = 1;
            break;
        }
        for (i = 0; i < take && !bad; ++i) {
            long at = (long)(sizeof(sba_head_t) + (row0 + i) * sizeof *rows +
                             (unsigned)((char *)&rows[i].starred - (char *)&rows[i]));
            if (!sba_row_is(&rows[i], id) || rows[i].starred == flag) continue;
            if (lseek(fd, at, 0) != at || write(fd, &flag, 1) != 1)
                bad = 1;
            else
                ++changed, ++wrote;
        }
        if (wrote && !bad) { /* back to the row after this chunk */
            long next = (long)(sizeof(sba_head_t) + (row0 + take) * sizeof *rows);
            if (lseek(fd, next, 0) != next) bad = 1;
        }
        row0 += take;
        n -= take;
    }
    close(fd);
    free(rows);
    return bad ? -1 : changed ? 1 : 0;
}

/* Walk starred.idx and copy it to path.tmp without the rows with that id and, when on, with add (a track) at the end. Commits only when something changed. 1 changed, 0 not, -1 failed. The
 * Favorites list is small (SBA_STARRED_MAX rows) and rows come and go, so it is replaced whole. */
static int sba_track_edit(const char *path, const char *id, int on, const sba_track_t *add) {
    sba_track_t *rows;
    sba_w_t w;
    unsigned n, flags, i, changed = 0;
    int fd = open(path, O_RDONLY, 0), code;
    if (fd < 0 || !sba_head(fd, SBK_TRACK, sizeof *rows, &n, &flags)) {
        if (fd >= 0) close(fd);
        if (on && add) { /* a list not there yet: it starts with this track */
            sba_track_t one;
            memcpy(&one, add, sizeof one);
            one.starred = 1;
            if (sba_wlist(path, SBK_TRACK, sizeof one, 0, &one, 1) != SBA_OK) return -1;
            sba_sbump();
            return 1;
        }
        return 0;
    }
    rows = calloc(SBA_CHUNK, sizeof *rows);
    if (!rows) {
        close(fd);
        return -1;
    }
    code = sba_wopen(&w, path, SBK_TRACK, sizeof *rows, flags);
    if (code) {
        free(rows);
        close(fd);
        return -1;
    }
    while (n && !code) {
        unsigned take = n < SBA_CHUNK ? n : SBA_CHUNK, keep = 0;
        if (!sba_read_all(fd, rows, take * (unsigned)sizeof *rows)) {
            code = SBA_STORAGE;
            break;
        }
        for (i = 0; i < take; ++i) {
            if (sba_row_is(&rows[i], id)) {
                ++changed;
            } else {
                if (i != keep) memcpy(&rows[keep], &rows[i], sizeof rows[i]);
                ++keep;
            }
        }
        if (!sba_wput(&w, rows, keep * (unsigned)sizeof *rows)) code = SBA_STORAGE;
        n -= take;
    }
    if (!code && on && add) {
        sba_track_t one;
        memcpy(&one, add, sizeof one);
        one.starred = 1;
        if (!sba_wput(&w, &one, sizeof one)) code = SBA_STORAGE;
        ++changed;
    }
    close(fd);
    free(rows);
    if (code || !changed) {
        sba_wabort(&w);
        return code ? -1 : 0;
    }
    if (sba_wcommit(&w) != SBA_OK) return -1;
    sba_sbump();
    return 1;
}

/* Remove every file of a folder (dot names too), then the folder itself when remove. */
static void sba_empty_dir(const char *dir, int remove, int keep_dl) {
    void *d = opendir(dir);
    char *ent;
    if (!d) return;
    while ((ent = (char *)readdir(d)) != (char *)0) {
        const char *name = ent + 11; /* struct dirent (32-bit): d_name at 11 */
        char path[SBA_PATH];
        if (!name[0] || (name[0] == '.' && (!name[1] || (name[1] == '.' && !name[2])))) continue;
        if (keep_dl && name[0] == 'd' && name[1] == 'l' && name[2] == '.') continue;
        if (snprintf(path, sizeof path, "%s/%s", dir, name) >= (int)sizeof path) continue;
        unlink(path);
    }
    closedir(d);
    if (remove) rmdir(dir);
}

/* Sign Out and a changed server: the cache goes, the downloaded music and its manifest (dl.*) stay. */
static void sba_cache_clear(void) {
    sba_empty_dir(SBA_DIR "/al", 1, 0);
    sba_empty_dir(SBA_DIR "/ar", 1, 0);
    sba_empty_dir(SBA_DIR "/pl", 1, 0);
    sba_empty_dir(SBA_COVER_DIR, 1, 0);
    sba_empty_dir(SBA_DIR, 0, 1);
    ++sba.agen;
    sba_sbump();
    sba_bump();
}

/* The files of the pull request's original page (a whole-library index, its artwork folder and its view file), none of which this build reads: removed once, on the first open of the root
 * page, and only the ones that are there (a build that never had them does nothing). The conf and the downloaded music stay. Not done while the card is out, so it runs on the next open. */
static int sba_retired_done __attribute__((section(".scratch")));
void sba_retire_old(void) {
    static const char *const files[] = {
        "/mnt/mmc/.m1plus/navidrome.index",    "/mnt/mmc/.m1plus/navidrome.index.tmp",
        "/mnt/mmc/.m1plus/navidrome.dsd.tmp",  "/mnt/mmc/.m1plus/navidrome-view",
        "/mnt/mmc/.m1plus/navidrome-view.tmp",
    };
    unsigned i;
    if (sba_retired_done || !pod_card_mounted()) return;
    sba_retired_done = 1;
    for (i = 0; i < sizeof files / sizeof files[0]; i++)
        if (access(files[i], 0) == 0) unlink(files[i]);
    sba_empty_dir("/mnt/mmc/.m1plus/navidrome-art", 1, 0);
}

/* ---------------------------------------------------------------------------
 * The conf
 */
static int sba_conf_save(void);
static void sba_conf_load(void) {
    char text[SBA_CONF_MAX + 1];
    unsigned i, n, p1 = 0, p2 = 0;
    int fd, r;
    if (sba.loaded || !pod_card_mounted()) return;
    sba.loaded = 1;
    sba.url[0] = sba.user[0] = sba.auth[0] = 0;
    fd = open(SBA_CONF, O_RDONLY, 0);
    if (fd < 0) return;
    r = read(fd, text, SBA_CONF_MAX);
    close(fd);
    if (r <= 0) return;
    n = (unsigned)r;
    while (n && (text[n - 1] == '\n' || text[n - 1] == '\r')) --n;
    text[n] = 0;
    for (i = 0; i < n; ++i)
        if (text[i] == '|') {
            if (!p1)
                p1 = i;
            else {
                p2 = i;
                break;
            }
        }
    if (!p1 || !p2 || p1 >= SBA_CONF_URL || p2 - p1 - 1 >= SBA_CONF_USER || n - p2 - 1 >= SBA_CONF_PASS) return;
    memcpy(sba.url, text, p1);
    sba.url[p1] = 0;
    memcpy(sba.user, text + p1 + 1, p2 - p1 - 1);
    sba.user[p2 - p1 - 1] = 0;
    memcpy(sba.auth, text + p2 + 1, n - p2 - 1);
    sba.auth[n - p2 - 1] = 0;
    memset(text, 0, sizeof text);
    if (sba.auth[0] &&
        !sbn_auth_ok(
            sba.auth)) { /* a file written before the secret: its third field is the password itself. The secret is made from it and the file written again without it, once */
        char made[SBN_AUTH + 1];
        if (sbn_auth_make(made, sba.auth) == 0) {
            memset(sba.auth, 0, sizeof sba.auth);
            memcpy(sba.auth, made, sizeof made);
            sba_conf_save();
        } else
            memset(sba.auth, 0,
                   sizeof sba.auth); /* (no secret can be made: signed out, never a password kept in memory as one) */
        memset(made, 0, sizeof made);
    }
}

static int sba_conf_save(void) {
    char text[SBA_CONF_MAX + 1];
    int n = snprintf(text, sizeof text, "%s|%s|%s", sba.url, sba.user, sba.auth), code;
    if (n < 0 || n >= (int)sizeof text) return SBA_PARSE;
    code = sba_wtext(SBA_CONF, SBA_CONF ".tmp", text, (unsigned)n, 0600);
    memset(text, 0, sizeof text);
    return code;
}

int sba_configured(void) {
    sba_conf_load();
    return sba.url[0] && sba.user[0] && sba.auth[0];
}

const char *sba_host(void) {
    const char *s;
    unsigned i = 0;
    sba_conf_load();
    s = sba.url;
    if (sbn_prefix(s, "https://"))
        s += 8;
    else if (sbn_prefix(s, "http://"))
        s += 7;
    while (s[i] && s[i] != '/' && i + 1 < sizeof sba.host) sba.host[i] = s[i], ++i;
    sba.host[i] = 0;
    return sba.host;
}

const char *sba_user(void) {
    sba_conf_load();
    return sba.user;
}

int sba_password_saved(void) {
    sba_conf_load();
    return sba.auth[0] != 0;
}

const char *sba_url(void) {
    sba_conf_load();
    return sba.url;
}

static int sba_text_ok(const char *s, int pipe_ok, unsigned cap) {
    unsigned i, n = sba_len(s);
    if (!n || n >= cap) return 0;
    for (i = 0; i < n; ++i) {
        unsigned char c = (unsigned char)s[i];
        if (c < 32 || c == 127 || (c == '|' && !pipe_ok)) return 0;
    }
    return 1;
}

/* A server address: http(s)://host[:port][/base], no spaces, query or fragment. A trailing '/' and a trailing "/rest" are dropped. */
static int sba_url_clean(const char *url, char *out) {
    unsigned i, n, host;
    if (!sba_text_ok(url, 0, SBA_CONF_URL) || !sbn_http_url(url)) return 0;
    sba_copy(out, SBA_CONF_URL, url);
    n = sba_len(out);
    for (i = 0; i < n; ++i)
        if (out[i] == ' ' || out[i] == '?' || out[i] == '#') return 0;
    while (n > 8 && out[n - 1] == '/') out[--n] = 0;
    if (n >= 5 && sba_same(out + n - 5, "/rest")) out[n -= 5] = 0;
    host = sbn_prefix(out, "https://") ? 8 : 7;
    if (n <= host || out[host] == '/' || out[host] == ':') return 0;
    return 1;
}

int sba_conf_url_set(const char *url) {
    char clean[SBA_CONF_URL], old[SBA_CONF_URL];
    int code;
    sba_conf_load();
    if (!url || !sba_url_clean(url, clean)) return SBA_PARSE;
    if (sba_same(clean, sba.url)) return SBA_OK;
    sba_copy(old, sizeof old, sba.url);
    sba_copy(sba.url, sizeof sba.url, clean);
    code = sba_conf_save();
    if (code) {
        sba_copy(sba.url, sizeof sba.url, old);
        return code;
    }
    sba.loaded = 1;
    if (old[0]) { /* another server: what was cached belongs to the first */
        sba_cancel();
        sba_cache_clear();
    }
    return SBA_OK;
}

int sba_conf_user_set(const char *user) {
    char old[SBA_CONF_USER];
    int code;
    sba_conf_load();
    if (!user || !sba_text_ok(user, 0, SBA_CONF_USER)) return SBA_PARSE;
    if (sba_same(user, sba.user)) return SBA_OK;
    sba_copy(old, sizeof old, sba.user);
    sba_copy(sba.user, sizeof sba.user, user);
    code = sba_conf_save();
    if (code) {
        sba_copy(sba.user, sizeof sba.user, old);
        return code;
    }
    sba.loaded = 1;
    if (old[0]) {
        sba_cancel();
        sba_cache_clear();
    }
    return SBA_OK;
}

int sba_conf_password_set(const char *password) {
    char old[SBA_CONF_PASS], made[SBN_AUTH + 1];
    int code;
    sba_conf_load();
    if (!password || !sba_text_ok(password, 1, SBA_CONF_PASS) || sbn_auth_make(made, password)) return SBA_PARSE;
    sba_copy(old, sizeof old, sba.auth);
    sba_copy(sba.auth, sizeof sba.auth, made); /* the secret (salt and token), never the password */
    memset(made, 0, sizeof made);
    code = sba_conf_save();
    if (code) sba_copy(sba.auth, sizeof sba.auth, old);
    memset(old, 0, sizeof old);
    if (code) return code;
    sba.loaded = 1;
    return SBA_OK;
}

int sba_conf_clear(void) {
    int bad = 0;
    sba_cancel();
    if (pod_card_mounted() && access(SBA_CONF, 0) == 0 && unlink(SBA_CONF)) bad = 1;
    unlink(SBA_CONF ".tmp");
    sba.loaded = 1;
    sba.url[0] = sba.user[0] = 0;
    memset(sba.auth, 0, sizeof sba.auth);
    if (pod_card_mounted()) sba_cache_clear();
    return bad ? SBA_STORAGE : SBA_OK;
}

/* The conditions for the server at `url` (the saved one, or a trial login's). */
static int sba_guard_for(const char *url) {
    if (!pod_card_mounted()) return SBA_STORAGE;
    if (get_wifisignal() <= 0) return SBA_NOWIFI;
    if (sbn_https(url)) {
        if ((unsigned)time((long *)0) < SBA_MIN_EPOCH) return SBA_NOCLOCK;
        if (access(SBA_CA, 0)) return SBA_NOCERT;
    }
    return SBA_OK;
}

int sba_guard(void) {
    if (!pod_card_mounted()) return SBA_STORAGE;
    if (!sba_configured()) return SBA_NOCONF;
    return sba_guard_for(sba.url);
}

/* ---------------------------------------------------------------------------
 * The status record
 */
static sba_stat_t *sba_stat_find(int kind, const char *id) {
    unsigned i, key = sba_fnv(id);
    for (i = 0; i < SBA_STATS; ++i)
        if (sba.st[i].kind == kind + 1 && sba.st[i].key == key) return &sba.st[i];
    return (sba_stat_t *)0;
}

/* An entry whose result is still wanted: a request running or waiting, or the one entry of a singleton kind (the sync, the Songs pager, the search). */
static int sba_stat_held(const sba_stat_t *s) {
    int k = s->kind - 1;
    return s->kind && (s->state == SBA_ST_LOAD || k == SBA_K_SYNC || k == SBA_K_SONGS || k == SBA_K_SEARCH);
}

/* UI thread only: the entry of (kind, id), made if there is none (the next in turn is replaced, skipping the ones in use; all in use = the next in turn all the same). */
static sba_stat_t *sba_stat_make(int kind, const char *id) {
    sba_stat_t *s = sba_stat_find(kind, id);
    if (!s) {
        unsigned tries = 0;
        while (tries < SBA_STATS && sba_stat_held(&sba.st[sba.stat_next % SBA_STATS])) ++sba.stat_next, ++tries;
        if (tries == SBA_STATS) sba.stat_next -= tries; /* every entry is in use: the old behaviour */
        s = &sba.st[sba.stat_next++ % SBA_STATS];
        s->state = SBA_ST_NONE;
        s->kind = kind + 1, s->key = sba_fnv(id), s->code = 0; /* (kind + 1: 0 is an unused entry) */
    }
    return s;
}

static void sba_stat_set(int kind, const char *id, int state, int code) {
    sba_stat_t *s = sba_stat_find(kind, id);
    if (!s) return;
    s->code = code;
    __sync_synchronize();
    s->state = state;
}

int sba_state(int kind, const char *id, int *code) {
    sba_stat_t *s = sba_stat_find(kind, id ? id : "");
    if (code) *code = s ? s->code : 0;
    return s ? s->state : SBA_ST_NONE;
}

/* ---------------------------------------------------------------------------
 * The worker
 */
typedef struct {
    sbn_sink_t *sink;
    unsigned mine;
    char url[SBA_CONF_URL], user[SBA_CONF_USER], auth[SBA_CONF_PASS];
} sba_wk_t;

/* sbn_init takes one transfer-info hook for every transfer: the download's own check first (it answers 0 for any sink that is not its), then ours. */
static int sba_pick(void);
static int sba_sync_read(unsigned v[4]);
static void sba_bg_reset(void);
static int sba_xfer(void *sink, long long total, long long now, long long up_total, long long up_now) {
    if (sba_dl_xfer(sink, total, now, up_total, up_now)) return 1;
    /* a request of phase 2 is cut off when a page's request waits (phase 2 is the lowest priority) */
    return sink == sba.sink && (sba.cancel != sba.mine || (sba.bg_run && sba_pick() >= 0));
}

static int sba_net_ready(void) {
    if (!sba.net) sba.net = sbn_init(sba_xfer, (sbn_after_fn)0);
    return sba.net;
}

int sba_net_open(char *base, unsigned bcap, char *user, unsigned ucap, char *auth, unsigned pcap) {
    if (!sba_configured()) return SBA_NOCONF;
    if (sba_len(sba.url) >= bcap || sba_len(sba.user) >= ucap || sba_len(sba.auth) >= pcap) return SBA_NOCONF;
    if (!sba_net_ready()) return SBA_NOCONF;
    sba_copy(base, bcap, sba.url);
    sba_copy(user, ucap, sba.user);
    sba_copy(auth, pcap, sba.auth);
    return SBA_OK;
}

/* The result of the transfer sbn_get / sbn_http just ran. */
static int sba_net_code(const sba_wk_t *w, int rc) {
    const sbn_sink_t *s = w->sink;
    if (sba.cancel != w->mine) return SBA_CANCELLED;
    if (rc == 0) return SBA_OK;
    if (rc == SBN_E_URL) return SBA_PARSE;
    if (rc == SBN_E_INIT) return SBA_MEM;
    switch (s->curl_result) {
    case 51:
    case 58:
    case 60:
    case 77:
    case 83:
        return SBA_CERT;
    default:
        break;
    }
    if (s->http_status == 401 || s->http_status == 403) return SBA_AUTH;
    if (s->http_status == 404) return SBA_NOTFOUND;
    if (s->http_status >= 400) return SBA_HTTP;
    return SBA_NET;
}

static int sba_get(sba_wk_t *w, const char *view, const char *id, const char *extra) {
    sbn_server_t srv;
    srv.base = w->url, srv.user = w->user, srv.auth = w->auth;
    return sba_net_code(w, sbn_get(srv, view, id, extra, w->sink));
}

/* A Subsonic response that carries no rows (ping, star): SBA_OK for status ok, else the error it names (sbparse.c). */
static int sba_reply_code(const sbn_sink_t *s) {
    int err = 0;
    if (sba_parse_ping(s->data, s->used, &err) == 0) return SBA_OK;
    return err ? err : SBA_PARSE;
}

/* 0 to go on, SBA_CANCELLED when the page cancelled or the conf was cleared, SBA_STORAGE when the card is gone: checked before a cache file is committed. */
static int sba_stop(const sba_wk_t *w) {
    return sba.cancel != w->mine ? SBA_CANCELLED : pod_card_mounted() ? 0 : SBA_STORAGE;
}

/* A response's rows into a file; the parse functions are patch/sbparse.c's. */
typedef int (*sba_parse_fn)(const char *json, unsigned n, void *out, int max, int *err);

static int sba_parse_t(const char *j, unsigned n, void *out, int max, int *err) {
    return sba_parse_tracks(j, n, (sba_track_t *)out, max, err);
}
static int sba_parse_a(const char *j, unsigned n, void *out, int max, int *err) {
    return sba_parse_albums(j, n, (sba_album_t *)out, max, err);
}
static int sba_parse_r(const char *j, unsigned n, void *out, int max, int *err) {
    return sba_parse_artists(j, n, (sba_artist_t *)out, max, err);
}
static int sba_parse_p(const char *j, unsigned n, void *out, int max, int *err) {
    return sba_parse_playlists(j, n, (sba_playlist_t *)out, max, err);
}

/* Parse the current response as kind (rows of rowsize, at most max) and replace path with them. */
static int sba_store(sba_wk_t *w, const char *path, unsigned kind, unsigned rowsize, int max, unsigned flags,
                     unsigned *count) {
    sba_parse_fn fn = kind == SBK_TRACK    ? sba_parse_t
                      : kind == SBK_ALBUM  ? sba_parse_a
                      : kind == SBK_ARTIST ? sba_parse_r
                                           : sba_parse_p;
    void *rows = calloc((unsigned)max, rowsize);
    int n, err = 0, code;
    if (!rows) return SBA_MEM;
    n = fn(w->sink->data, w->sink->used, rows, max, &err);
    if (n < 0) {
        free(rows);
        return err ? err : SBA_PARSE;
    }
    if ((code = sba_stop(w)) != 0) {
        free(rows);
        return code;
    }
    code = sba_wlist(path, kind, rowsize, flags, rows, (unsigned)n);
    free(rows);
    if (!code) {
        if (count) *count = (unsigned)n;
        sba_bump();
    }
    return code;
}

/* The library's signature, the sync's own totals (no extra request): the track count, the seconds, the album count and the newest album's creation time, mixed (never 0). Phase 2 fills the library again when it changes. */
static unsigned sba_mix(unsigned h, unsigned v) {
    unsigned i;
    for (i = 0; i < 4; ++i) h = (h ^ ((v >> (8 * i)) & 0xff)) * 16777619u;
    return h;
}

static int sba_sync_albums(sba_wk_t *w, unsigned *songs, int *trunc, unsigned *sig) {
    sba_album_t *page = calloc(SBA_ALBUM_PAGE, sizeof *page);
    sba_acov_t *ent = calloc(SBA_ALBUM_PAGE, sizeof *ent);
    sba_w_t f, g;
    unsigned total = 0, i, secs = 0, newest = 0;
    int code;
    f.fd = g.fd = -1;
    code = page ? sba_wopen(&f, SBA_DIR "/albums.idx", SBK_ALBUM, sizeof *page, 0) : SBA_MEM;
    if (!code && ent)
        (void)sba_wopen(&g, SBA_DIR "/albcov.idx", SBK_ACOV, sizeof *ent,
                        0); /* (best effort: without it a track keeps its own cover) */
    *songs = 0, *trunc = 0, *sig = 0;
    while (!code) {
        char extra[96];
        int n, err = 0;
        snprintf(extra, sizeof extra, "&type=alphabeticalByName&size=%u&offset=%u", SBA_ALBUM_PAGE, total);
        code = sba_get(w, "getAlbumList2", 0, extra);
        if (code) break;
        n = sba_parse_albums(w->sink->data, w->sink->used, page, SBA_ALBUM_PAGE, &err);
        if (n < 0) {
            code = err ? err : SBA_PARSE;
            break;
        }
        for (i = 0; i < (unsigned)n; ++i) {
            *songs += page[i].songs;
            secs += page[i].seconds;
            if (page[i].created > newest) newest = page[i].created;
        }
        if ((code = sba_stop(w)) != 0) break;
        if (!sba_wput(&f, page, (unsigned)n * (unsigned)sizeof *page)) {
            code = SBA_STORAGE;
            break;
        }
        if (g.fd >= 0) { /* (row `total + i` is the album's place in albums.idx) */
            for (i = 0; i < (unsigned)n; ++i) {
                ent[i].h1 = sba_fnv(page[i].id), ent[i].h2 = sba_hash2(page[i].id);
                ent[i].cover = page[i].cover[0] ? sba_fnv(page[i].cover) : 0, ent[i].row = total + i;
            }
            if (!sba_wput(&g, ent, (unsigned)n * (unsigned)sizeof *ent)) sba_wabort(&g);
        }
        total += (unsigned)n;
        if (n < SBA_ALBUM_PAGE) break;
        if (total >= SBA_MAX_ALBUMS) {
            *trunc = 1;
            break;
        }
    }
    if (f.fd >= 0) {
        if (code)
            sba_wabort(&f);
        else if (!(code = sba_wcommit(&f))) {
            sba_bump();
            if (!(g.fd >= 0 && sba_wcommit(&g) == SBA_OK))
                unlink(SBA_DIR "/albcov.idx"); /* (never an albcov.idx of the albums before) */
            ++sba.agen;
        }
    }
    if (g.fd >= 0) sba_wabort(&g);
    if (!code) *sig = sba_mix(sba_mix(sba_mix(sba_mix(2166136261u, *songs), secs), total), newest) | 1u;
    free(ent);
    free(page);
    return code;
}

/* One of the sync's optional lists (everything but the albums): the request and the file it fills. The server refusing or not understanding THIS list (no rights to playlists:
 * an HTTP error, another Subsonic error, a body that does not parse) keeps the list's file from before (an empty one when there was none) and the sync goes on; Wi-Fi, certificate, login, storage and net errors still fail it all. */
static int sba_sync_list(sba_wk_t *w, const char *view, const char *path, unsigned kind, unsigned rowsize, int max) {
    char none = 0;
    int code = sba_get(w, view, 0, 0);
    if (!code) code = sba_store(w, path, kind, rowsize, max, 0, 0);
    if (code != SBA_NOTFOUND && code != SBA_HTTP && code != SBA_PARSE) return code;
    if (access(path, 0)) (void)sba_wlist(path, kind, rowsize, 0, &none, 0);
    return sba_stop(w); /* (a cancel or a card taken out meanwhile still ends the sync) */
}

static int sba_run_sync(sba_wk_t *w) {
    unsigned songs = 0, when, n, sig = 0;
    int trunc = 0, code;
    char text[64];
    code = sba_sync_albums(w, &songs, &trunc, &sig);
    if (!code)
        code =
            sba_sync_list(w, "getArtists", SBA_DIR "/artists.idx", SBK_ARTIST, sizeof(sba_artist_t), SBA_ARTISTS_MAX);
    if (!code)
        code = sba_sync_list(w, "getPlaylists", SBA_DIR "/playlists.idx", SBK_PLAYLIST, sizeof(sba_playlist_t),
                             SBA_PLAYLISTS_MAX);
    if (!code) {
        code = sba_sync_list(w, "getStarred2", SBA_DIR "/starred.idx", SBK_TRACK, sizeof(sba_track_t), SBA_STARRED_MAX);
        sba_sbump(); /* (whatever the answer: the file may be new, or an empty one made) */
    }
    if (code) return code;
    when = (unsigned)time((long *)0);
    n = (unsigned)snprintf(text, sizeof text, "%u %u %d %u\n", when, songs, trunc, sig);
    return sba_wtext(SBA_DIR "/sync.txt", SBA_DIR "/sync.tmp", text, n, 0644);
}

/* One page of the whole library's songs: search3 with an empty query, SBA_SONG_PAGE songs from offset, parsed into page (*n rows). Shared by the Songs list's pager and by phase 2. SBA_OK or the failure. */
static int sba_songs_page(sba_wk_t *w, unsigned offset, sba_track_t *page, int *n) {
    char extra[128];
    int err = 0, code;
    *n = 0;
    snprintf(extra, sizeof extra, "&query=&songCount=%u&albumCount=0&artistCount=0&songOffset=%u", SBA_SONG_PAGE,
             offset);
    code = sba_get(w, "search3", 0, extra);
    if (!code && (*n = sba_parse_tracks(w->sink->data, w->sink->used, page, SBA_SONG_PAGE, &err)) < 0) {
        *n = 0;
        code = err ? err : SBA_PARSE;
    }
    return code ? code : sba_stop(w);
}

/* A page of the Songs list. offset 0 starts again; otherwise the page is appended to what is cached. */
static int sba_run_songs(sba_wk_t *w, unsigned offset) {
    sba_track_t *page = calloc(SBA_SONG_PAGE, sizeof *page), *chunk = (sba_track_t *)0;
    sba_w_t f;
    unsigned have = 0, flags, left, more;
    int n = 0, code, fd = -1;
    f.fd = -1;
    if (!page) return SBA_MEM;
    code = sba_songs_page(w, offset, page, &n);
    if (!code && offset) {
        fd = open(SBA_DIR "/songs.idx", O_RDONLY, 0);
        if (fd < 0 || !sba_head(fd, SBK_TRACK, sizeof *page, &have, &flags) || have < offset) code = SBA_PARSE;
        if (!code && have > offset) { /* a stale page: the list already holds these rows (phase 2 finished it) */
            close(fd);
            free(page);
            return SBA_OK;
        }
        if (!code) chunk = calloc(SBA_CHUNK, sizeof *chunk);
        if (!code && !chunk) code = SBA_MEM;
    }
    more = (unsigned)n == SBA_SONG_PAGE && offset + (unsigned)n < SBA_MAX_TRACKS;
    if (!code) code = sba_wopen(&f, SBA_DIR "/songs.idx", SBK_TRACK, sizeof *page, more);
    for (left = offset; !code && left;) {
        unsigned take = left < SBA_CHUNK ? left : SBA_CHUNK;
        if (!sba_read_all(fd, chunk, take * (unsigned)sizeof *chunk) ||
            !sba_wput(&f, chunk, take * (unsigned)sizeof *chunk))
            code = SBA_STORAGE;
        left -= take;
    }
    if (!code && !sba_wput(&f, page, (unsigned)n * (unsigned)sizeof *page)) code = SBA_STORAGE;
    if (fd >= 0) close(fd);
    if (code && f.fd >= 0) sba_wabort(&f);
    if (!code) code = sba_wcommit(&f);
    free(chunk);
    free(page);
    if (!code) sba_bump();
    return code;
}

static int sba_run_search(sba_wk_t *w, const char *term) {
    char extra[SBA_TERM * 3 + 96];
    unsigned o = (unsigned)snprintf(extra, sizeof extra, "&query=");
    int code;
    o = sbn_urlenc(extra, sizeof extra, o, term);
    if (!o) return SBA_PARSE;
    snprintf(extra + o, sizeof extra - o, "&songCount=%u&albumCount=%u&artistCount=%u", SBA_SEARCH_N, SBA_SEARCH_N,
             SBA_SEARCH_N);
    code = sba_get(w, "search3", 0, extra);
    if (!code) code = sba_store(w, SBA_DIR "/search.idx", SBK_TRACK, sizeof(sba_track_t), SBA_SEARCH_N, 0, 0);
    if (!code) code = sba_store(w, SBA_DIR "/search-al.idx", SBK_ALBUM, sizeof(sba_album_t), SBA_SEARCH_N, 0, 0);
    if (!code) code = sba_store(w, SBA_DIR "/search-ar.idx", SBK_ARTIST, sizeof(sba_artist_t), SBA_SEARCH_N, 0, 0);
    return code;
}

static int sba_png_or_jpeg(const unsigned char *d, unsigned n) {
    return n > 8 && ((d[0] == 0xff && d[1] == 0xd8 && d[2] == 0xff) ||
                     (d[0] == 0x89 && d[1] == 'P' && d[2] == 'N' && d[3] == 'G'));
}

/* A WebP ("RIFF" size "WEBP"): Navidrome answers a getCoverArt for an artist or album with no art of any kind with its own stand-in picture (artist-placeholder.webp / album-placeholder.webp), served
 * as it is (the server resizes and re-encodes real art, into JPEG or PNG; the stand-in is never resized and goes out with Cache-Control: no-store). So a WebP reply means "no art". */
static int sba_webp(const unsigned char *d, unsigned n) {
    return n > 12 && d[0] == 'R' && d[1] == 'I' && d[2] == 'F' && d[3] == 'F' && d[8] == 'W' && d[9] == 'E' &&
           d[10] == 'B' && d[11] == 'P';
}

static int sba_run_cover(sba_wk_t *w, const char *cover) {
    char path[SBA_PATH], extra[32], tmp[SBA_PATH + 8];
    int code, fd, have;
    unsigned kb = 0;
    if (sba_cover_path(path, sizeof path, cover)) return SBA_PARSE;
    have = sba_cover_have(cover);
    if (have) return have > 0 ? SBA_OK : SBA_NOTFOUND;
    if (!pod_card_mounted()) return SBA_STORAGE;
    sba_dirs();
    if (pn_free_kb(SBA_DIR, &kb) && kb < SBA_CACHE_RESERVE_KB) return SBA_CARDFULL;
    snprintf(extra, sizeof extra, "&size=%u", SBA_COVER_PX);
    code = sba_get(w, "getCoverArt", cover, extra);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    if ((code == SBA_NOTFOUND && w->sink->http_status == 404) ||
        (!code && sba_webp((const unsigned char *)w->sink->data,
                           w->sink->used))) { /* no art: an empty marker, so the page does not ask again */
        sba_wtext(path, tmp, "", 0, 0644);
        sba_cbump();
        return SBA_NOTFOUND;
    }
    if (code) return code;
    if (w->sink->used > SBA_COVER_MAX || !sba_png_or_jpeg((const unsigned char *)w->sink->data, w->sink->used))
        return SBA_PARSE;
    if ((code = sba_stop(w)) != 0) return code;
    fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return SBA_STORAGE;
    code = sbn_write_all(fd, w->sink->data, w->sink->used) && fsync(fd) == 0 ? SBA_OK : SBA_STORAGE;
    if (close(fd)) code = SBA_STORAGE;
    if (!code && rename(tmp, path)) code = SBA_STORAGE;
    if (code)
        unlink(tmp);
    else
        sba_cbump();
    return code;
}

/* The empty "no art" marker for a cover id (what a 404 leaves): 1 when it is there. */
static int sba_cover_mark(const char *cover) {
    char path[SBA_PATH], tmp[SBA_PATH + 8];
    if (sba_cover_path(path, sizeof path, cover)) return 0;
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    if (sba_wtext(path, tmp, "", 0, 0644)) return 0;
    sba_cbump();
    return 1;
}

/* The star overlay: the heart flips on the page the moment sba_star is called, but the cache files are edited by the worker (the only thread that writes them), a moment later. Until
 * the worker has written the files (or put them back after a refusal) the id is held here, and every track list read (sba_tracks_at) and sbs_track (sba_star_pending) shows the held
 * flag over the file's. A second star of the same id while the first is in flight only moves the wish (on) and counts one more request (pend). */
static void sba_ov_lock(void) {
    while (__sync_lock_test_and_set(&sba.ov_lock, 1)) {
    }
}

static void sba_ov_unlock(void) { __sync_lock_release(&sba.ov_lock); }

/* Hold a star: 1, or 0 when the overlay is full (the caller refuses the star). */
static int sba_ov_hold(const char *id, int on) {
    int i, free_at = -1, ok = 1;
    sba_ov_lock();
    for (i = 0; i < SBA_OV; ++i) {
        if (!sba.ov[i].id[0]) {
            if (free_at < 0) free_at = i;
        } else if (sba_same(sba.ov[i].id, id))
            break;
    }
    if (i == SBA_OV) i = free_at;
    if (i < 0 || sba.ov[i].pend == 255)
        ok = 0;
    else {
        if (!sba.ov[i].id[0]) sba_copy(sba.ov[i].id, sizeof sba.ov[i].id, id), sba.ov[i].pend = 0;
        sba.ov[i].on = (unsigned char)(on != 0);
        ++sba.ov[i].pend;
    }
    sba_ov_unlock();
    return ok;
}

/* One request of that id is over (the files are final, or it never ran): the entry goes when it was the last. */
static void sba_ov_release(const char *id) {
    int i;
    sba_ov_lock();
    for (i = 0; i < SBA_OV; ++i)
        if (sba.ov[i].id[0] && sba_same(sba.ov[i].id, id)) {
            if (sba.ov[i].pend > 1)
                --sba.ov[i].pend;
            else
                sba.ov[i].id[0] = 0, sba.ov[i].pend = 0;
            break;
        }
    sba_ov_unlock();
}

int sba_star_pending(const char *id) {
    int i, r = -1;
    sba_ov_lock();
    for (i = 0; i < SBA_OV; ++i)
        if (sba.ov[i].id[0] && sba_same(sba.ov[i].id, id)) {
            r = sba.ov[i].on;
            break;
        }
    sba_ov_unlock();
    return r;
}

/* Show the held stars on a list read from a file. */
static void sba_ov_apply(sba_track_t *v, int n) {
    int i, j;
    struct {
        char id[SBA_ID];
        unsigned char on;
    } snap[SBA_OV];
    int held = 0;
    sba_ov_lock();
    for (i = 0; i < SBA_OV; ++i)
        if (sba.ov[i].id[0])
            sba_copy(snap[held].id, sizeof snap[held].id, sba.ov[i].id), snap[held++].on = sba.ov[i].on;
    sba_ov_unlock();
    if (!held) return;
    for (i = 0; i < n; ++i)
        for (j = 0; j < held; ++j)
            if (sba_same(v[i].id, snap[j].id)) v[i].starred = snap[j].on;
}

/* A star in the cache files, on the worker (it is the only thread that writes them): the starred flag flips in place in the files that have the row (songs.idx, search.idx, the album's
 * file) and the Favorites list gains or loses the track. Also done with !on when the server refused (or could not be asked) the star: the request's row is kept in its slot. The event is
 * logged for a songs.idx that phase 2 is still paging (sba_bg_commit replays it); only the worker writes and reads the log. */
static void sba_star_files(const sba_track_t *t, int on) {
    char path[SBA_PATH];
    unsigned k = sba.star_n % SBA_STAR_EV;
    sba_copy(sba.star_ev[k].id, sizeof sba.star_ev[k].id, t->id);
    sba.star_ev[k].on = on != 0;
    __sync_synchronize();
    ++sba.star_n;
    sba_track_flag(SBA_DIR "/songs.idx", t->id, on);
    sba_track_flag(SBA_DIR "/search.idx", t->id, on);
    if (t->album_id[0] && !sba_idpath(path, sizeof path, SBA_DIR "/al", t->album_id, ".idx"))
        sba_track_flag(path, t->id, on);
    sba_track_edit(SBA_DIR "/starred.idx", t->id, on, t);
}

static void *sba_main(void *arg);

typedef struct {
    sba_track_t row;
    int on;
} sba_star_arg_t;

static void sba_fin(sba_slot_t *s, int code) {
    int cover = s->kind == SBA_K_COVER; /* (read before the slot is free: a new request may take it) */
    if (s->kind == SBA_K_SEARCH && code != SBA_CANCELLED) sba.search_done = sba_fnv(s->term);
    if (code == SBA_CANCELLED)
        sba_stat_set(s->kind, s->id, SBA_ST_NONE, 0);
    else
        sba_stat_set(s->kind, s->id, code ? SBA_ST_FAIL : SBA_ST_OK, code);
    __sync_synchronize();
    s->state = SLOT_FREE;
    if (cover)
        sba_cbump();
    else
        sba_bump();
}

/* The slot with the lowest sequence among the waiting ones: lists first, covers when no list waits. */
static int sba_pick(void) {
    int i, best = -1, cover = -1;
    for (i = 0; i < SBA_SLOTS; ++i) {
        if (sba.q[i].state != SLOT_WAIT) continue;
        if (sba.q[i].kind == SBA_K_COVER) {
            if (cover < 0 || sba.q[i].seq < sba.q[cover].seq) cover = i;
        } else if (best < 0 || sba.q[i].seq < sba.q[best].seq)
            best = i;
    }
    return best >= 0 ? best : cover;
}

/* One request on the worker. A star's row travels in a heap block (the slot's arg), freed here. */
static int sba_run(sba_wk_t *w, sba_slot_t *s) {
    char path[SBA_PATH];
    switch (s->kind) {
    case SBA_K_PING: {
        int code = sba_get(w, "ping", 0, 0);
        return code ? code : sba_reply_code(w->sink);
    }
    case SBA_K_SYNC: {
        int code;
        sba_bg_reset(); /* phase 2 reads its state again: the library it was filling may be another now */
        code = sba_run_sync(w);
        if (code) sba.bg_want = 0; /* a failed sync: no phase 2 behind it */
        return code;
    }
    case SBA_K_ALBUM:
    case SBA_K_ARTIST:
    case SBA_K_PLAYLIST: {
        int code, album = s->kind == SBA_K_ALBUM, artist = s->kind == SBA_K_ARTIST;
        if (sba_idpath(path, sizeof path,
                       album    ? SBA_DIR "/al"
                       : artist ? SBA_DIR "/ar"
                                : SBA_DIR "/pl",
                       s->id, ".idx"))
            return SBA_PARSE;
        code = sba_get(w, album ? "getAlbum" : artist ? "getArtist" : "getPlaylist", s->id, 0);
        if (code) return code;
        return artist ? sba_store(w, path, SBK_ALBUM, sizeof(sba_album_t), SBA_ALBUM_TRACKS, 0, 0)
                      : sba_store(w, path, SBK_TRACK, sizeof(sba_track_t), SBA_ALBUM_TRACKS, 0, 0);
    }
    case SBA_K_SONGS:
        return sba_run_songs(w, s->arg);
    case SBA_K_SEARCH:
        return sba_run_search(w, s->term);
    case SBA_K_COVER:
        return sba_run_cover(w, s->id);
    case SBA_K_STAR: {
        sba_star_arg_t *st = (sba_star_arg_t *)(unsigned long)s->arg;
        int code;
        sba_star_files(&st->row,
                       st->on); /* the cache changes first, here: the page already shows the heart (the overlay) */
        code = sba_get(w, st->on ? "star" : "unstar", s->id, 0);
        if (!code) code = sba_reply_code(w->sink);
        if (code && code != SBA_CANCELLED)
            sba_star_files(
                &st->row,
                !st->on); /* refused or failed: the heart goes back (not after a cancel: the cache is being cleared, and putting an unstar back would write a starred.idx of the old server) */
        sba_ov_release(st->row.id);
        free(st);
        s->arg = 0;
        return code;
    }
    default:
        return SBA_PARSE;
    }
}

/* ---------------------------------------------------------------------------
 * Phase 2: the background fill (docs/modules/subsonic.md "Background fill"). Runs on the metadata worker when no request waits, one bounded step at a time (a request, a few dozen rows of file work), so a
 * request a page makes waits for at most one step (and a transfer of phase 2 is cut off for it, sba_xfer). Stages, kept in bg.txt with the library signature: PAGE (songs.part grows a page a step, then becomes
 * songs.idx), DERIVE (al/<id>.idx for every album whose songs are all there), COVERS (every album's cover), ARTISTS (every artist's picture), DONE.
 */
#define SBA_BG_STATE SBA_DIR "/bg.txt"
#define SBA_BG_PART SBA_DIR "/songs.part"
#define SBA_BG_ROWS 8 /* chunks of SBA_CHUNK songs read in a step while the album index is built */
#define SBA_BG_COUNT 256 /* albums looked at in a step while the covers to fetch are counted */
#define SBA_BG_TRIES 3 /* tries of one cover in a run before it is left for the next */

enum { BGS_NONE = 0, BGS_PAGE, BGS_DERIVE, BGS_COVERS, BGS_ARTISTS, BGS_DONE };

typedef struct {
    unsigned sig, stage, gcur,
        when; /* the library signature, the stage, the album the derive reached, when the fill started / finished */
} sba_bgs_t;

typedef struct {
    unsigned hash, row; /* a song of songs.idx: the hash of its album id and its row number */
} sba_ent_t;

/* The worker's runtime for phase 2 (single worker: no lock). Cleared whenever the worker has nothing left to do, so the heap goes back. */
static struct {
    int loaded;
    unsigned cancel0, fails, star0;
    sba_bgs_t s;
    sba_ent_t *e; /* the derive's index of songs.idx by album, 8 bytes a song (at most SBA_MAX_TRACKS) */
    unsigned en, eread, esorted;
    char pfirst
        [SBA_ID]; /* the first song id of the last page appended to songs.part (a server that ignores the offset sends it again) */
    unsigned cphase, ccount, btotal, bdone, bcur, cfail, skip,
        cskip; /* covers / artist pictures: the stage's counting phase, rows counted, to fetch, fetched, cursor, tries, left for the next run; cskip: the covers' */
} bg __attribute__((section(".scratch")));

static int sba_bg_read(sba_bgs_t *s) {
    char text[64];
    unsigned i, v[4] = {0, 0, 0, 0}, k = 0;
    int fd = open(SBA_BG_STATE, O_RDONLY, 0), r;
    memset(s, 0, sizeof *s);
    if (fd < 0) return 0;
    r = read(fd, text, sizeof text - 1);
    close(fd);
    if (r <= 0) return 0;
    text[r] = 0;
    for (i = 0; text[i] && k < 4; ++i) {
        if (text[i] >= '0' && text[i] <= '9')
            v[k] = v[k] * 10 + (unsigned)(text[i] - '0');
        else if (text[i] == ' ')
            ++k;
    }
    s->sig = v[0], s->stage = v[1], s->gcur = v[2], s->when = v[3];
    return s->sig != 0;
}

static void sba_bg_write(const sba_bgs_t *s) {
    char text[64];
    unsigned n = (unsigned)snprintf(text, sizeof text, "%u %u %u %u\n", s->sig, s->stage, s->gcur, s->when);
    sba_wtext(SBA_BG_STATE, SBA_DIR "/bg.tmp", text, n, 0644);
}

/* 1 when phase 2 has something to do for the library the last sync found: no finished fill for its signature, or one older than SBA_BG_MAX_AGE. */
static int sba_bg_pending(void) {
    unsigned v[4], now = (unsigned)time((long *)0);
    sba_bgs_t s;
    if (!sba_sync_read(v) || !v[3]) return 0;
    if (!sba_bg_read(&s) || s.sig != v[3] || s.stage != BGS_DONE) return 1;
    return now >= SBA_MIN_EPOCH && now >= s.when && now - s.when >= SBA_BG_MAX_AGE;
}

static void sba_bg_pub(int kind, unsigned done, unsigned total) {
    sba.bg_done = done;
    sba.bg_total = total;
    __sync_synchronize();
    sba.bg_kind = kind;
    ++sba.bg_gen;
}

static void sba_bg_reset(void) {
    free(bg.e);
    memset(&bg, 0, sizeof bg);
    sba.bg_run = 0;
    sba_bg_pub(0, 0, 0);
}

/* Nothing (more) to do for now: the next kick or sync starts it again. Returns 0 for sba_bg_step. */
static int sba_bg_stop(void) {
    sba.bg_want = 0;
    sba_bg_reset();
    return 0;
}

/* Wait up to secs seconds, a second at a time, for the end of the pause or a request that wants the worker. */
static void sba_bg_wait(const sba_wk_t *w, unsigned secs) {
    sba_bg_pub(0, 0, 0);
    while (secs--) {
        if (sba_pick() >= 0 || sba.cancel != w->mine || !sba.bg_want) return;
        sleep(1);
    }
}

/* A step of phase 2 failed: 1 to go on (after a pause, or at once when a page's request cut it off), 0 to end the run (the stage and the files stay; the next kick resumes). */
static int sba_bg_fail(const sba_wk_t *w, int code) {
    unsigned secs;
    sba.bg_run = 0;
    if (code == SBA_CANCELLED ||
        sba.cancel != w->mine) { /* Sign Out or another server: the state is read again (if phase 2 is still wanted) */
        sba_bg_reset();
        return 1;
    }
    if (sba_pick() >= 0) return 1; /* a request of a page went first: not a failure */
    if (code == SBA_CARDFULL || code == SBA_STORAGE || code == SBA_AUTH || code == SBA_CERT || code == SBA_NOCERT ||
        code == SBA_NOCLOCK || code == SBA_NOCONF || code == SBA_MEM || ++bg.fails >= SBA_BG_FAILS)
        return sba_bg_stop();
    secs = 5u << bg.fails; /* 10, 20, 40, then a minute (the cap) */
    sba_bg_wait(w, secs > 60 ? 60 : secs);
    return 1;
}

/* Phase 2 keeps the card's free space above the downloads' floor (SBA_RESERVE_KB). */
static int sba_bg_room(void) {
    unsigned kb = 0;
    return pn_free_kb(SBA_DIR, &kb) && kb < SBA_RESERVE_KB ? SBA_CARDFULL : SBA_OK;
}

/* Leave for another stage (and write it down). */
static int sba_bg_to(unsigned stage) {
    free(bg.e);
    bg.e = (sba_ent_t *)0;
    bg.en = bg.eread = bg.esorted = 0;
    bg.s.stage = stage, bg.s.gcur = 0;
    bg.cphase = bg.ccount = bg.btotal = bg.bdone = bg.bcur = bg.cfail = bg.skip = 0;
    if (stage == BGS_DONE) bg.s.when = (unsigned)time((long *)0);
    sba_bg_write(&bg.s);
    return 1;
}

/* Up to n album rows of albums.idx from row `from`; the rows read. *total is the file's row count (0 when it is not there). */
static unsigned sba_bg_albums(unsigned from, unsigned n, sba_album_t *out, unsigned *total) {
    unsigned rows = 0, got = 0;
    int fd = open(SBA_DIR "/albums.idx", O_RDONLY, 0);
    *total = 0;
    if (fd < 0) return 0;
    if (sba_head(fd, SBK_ALBUM, sizeof *out, &rows, (unsigned *)0)) {
        *total = rows;
        if (from < rows) {
            if (n > rows - from) n = rows - from;
            if (lseek(fd, (long)(sizeof(sba_head_t) + from * sizeof *out), 0) >= 0 &&
                sba_read_all(fd, out, n * (unsigned)sizeof *out))
                got = n;
        }
    }
    close(fd);
    return got;
}

/* songs.part is the whole library, a page at a time: the page is the Songs pager's request; the rows are appended (the file is only ever read by this worker), the last page makes it songs.idx. */
static int sba_bg_commit(sba_wk_t *w) {
    unsigned i, n = sba.star_n, first = n - bg.star0 > SBA_STAR_EV ? n - SBA_STAR_EV : bg.star0;
    int code = sba_stop(w);
    if (!code && rename(SBA_BG_PART, SBA_DIR "/songs.idx")) code = SBA_STORAGE;
    if (code) return sba_bg_fail(w, code);
    for (i = first; i != n;
         ++i) /* stars taken while the pages came in: the server's answers of the first pages may predate them */
        sba_track_flag(SBA_DIR "/songs.idx", sba.star_ev[i % SBA_STAR_EV].id, sba.star_ev[i % SBA_STAR_EV].on);
    sba_bump();
    return sba_bg_to(BGS_DERIVE);
}

/* songs.part whose size is not a whole number of rows (a row half written by a power loss): the header must fit, then the whole rows are copied to a new file that replaces it (no ftruncate among the imports). 1 and *rows, or 0 (start again). */
static int sba_part_trim(int fd, unsigned *rows) {
    sba_head_t h;
    long size = lseek(fd, 0, 2), left, whole;
    char *buf;
    int out, ok = 1;
    if (size < (long)sizeof h || lseek(fd, 0, 0) != 0 || read(fd, &h, sizeof h) != (int)sizeof h) return 0;
    if (h.magic[0] != 'S' || h.magic[1] != 'B' || h.magic[2] != 'A' || h.magic[3] != '1' || h.kind != SBK_TRACK ||
        h.rowsize != sizeof(sba_track_t))
        return 0;
    *rows = (unsigned)(size - (long)sizeof h) / (unsigned)sizeof(sba_track_t);
    whole = (long)*rows * (long)sizeof(sba_track_t);
    buf = calloc(SBA_CHUNK_BYTES, 1);
    if (!buf) return 0;
    out = open(SBA_DIR "/songs.cut", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    ok = out >= 0 && sbn_write_all(out, &h, sizeof h);
    for (left = whole; ok && left;) {
        unsigned take = left < (long)SBA_CHUNK_BYTES ? (unsigned)left : SBA_CHUNK_BYTES;
        ok = sba_read_all(fd, buf, take) && sbn_write_all(out, buf, take);
        left -= (long)take;
    }
    ok = ok && fsync(out) == 0;
    if (out >= 0 && close(out)) ok = 0;
    free(buf);
    ok = ok && rename(SBA_DIR "/songs.cut", SBA_BG_PART) == 0;
    if (!ok) unlink(SBA_DIR "/songs.cut");
    return ok;
}

static int sba_bg_page(sba_wk_t *w) {
    sba_track_t *page;
    unsigned rows = 0, v[4], total;
    int n = 0, code, fd, ok;
    if ((code = sba_bg_room()) != 0) return sba_bg_fail(w, code);
    fd = open(SBA_BG_PART, O_RDONLY, 0);
    ok = fd >= 0 && sba_head(fd, SBK_TRACK, sizeof(sba_track_t), &rows, (unsigned *)0);
    if (fd >= 0 && !ok) /* torn by a power loss in the last row: cut back to the whole rows and go on from there */
        ok = sba_part_trim(fd, &rows);
    if (fd >= 0) close(fd);
    if (!ok) { /* none yet, or torn by a power loss: from the first page */
        sba_head_t h;
        h.magic[0] = 'S', h.magic[1] = 'B', h.magic[2] = 'A', h.magic[3] = '1';
        h.kind = SBK_TRACK, h.rowsize = sizeof(sba_track_t), h.flags = 0;
        rows = 0;
        fd = open(SBA_BG_PART, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        ok = fd >= 0 && sbn_write_all(fd, &h, sizeof h);
        if (fd >= 0) close(fd);
        if (!ok) {
            unlink(SBA_BG_PART);
            return sba_bg_fail(w, SBA_STORAGE);
        }
    }
    sba_sync_read(v);
    total = v[1] > rows ? v[1] : rows;
    sba_bg_pub(1, rows, total);
    page = calloc(SBA_SONG_PAGE, sizeof *page);
    if (!page) return sba_bg_fail(w, SBA_MEM);
    sba.bg_run = 1;
    code = sba_songs_page(w, rows, page, &n);
    sba.bg_run = 0;
    if (!code && n && !strcmp(page[0].id, bg.pfirst)) n = 0; /* the page again: the end of what the server will give */
    if (!code && n) sba_copy(bg.pfirst, sizeof bg.pfirst, page[0].id);
    if (!code) {
        fd = open(SBA_BG_PART, O_WRONLY | O_APPEND, 0);
        ok = fd >= 0 && (!n || sbn_write_all(fd, page, (unsigned)n * (unsigned)sizeof *page)) && fsync(fd) == 0;
        if (fd >= 0 && close(fd)) ok = 0;
        if (!ok) code = SBA_STORAGE;
    }
    free(page);
    if (code) return sba_bg_fail(w, code);
    rows += (unsigned)n;
    /* The sync's song total says when the list is whole: a short page before it (the server's own limit) goes on by offset, an empty one ends the paging, and no rows at all for a library that has songs is a failed run, never a finished empty list. */
    if (!n && !rows && v[1]) return sba_bg_fail(w, SBA_PARSE);
    bg.fails = 0;
    sba_bg_pub(1, rows, total > rows ? total : rows);
    if (rows < SBA_MAX_TRACKS && (n == SBA_SONG_PAGE || (n && v[1] && rows < v[1]))) return 1;
    return sba_bg_commit(w);
}

/* Shell sort by (hash, row): no qsort among the imports. */
static void sba_ent_sort(sba_ent_t *a, unsigned n) {
    static const unsigned gaps[] = {701, 301, 132, 57, 23, 10, 4, 1};
    unsigned g, i, j;
    for (g = 0; g < sizeof gaps / sizeof gaps[0]; ++g) {
        unsigned gap = gaps[g];
        for (i = gap; i < n; ++i) {
            sba_ent_t t = a[i];
            for (j = i; j >= gap && (a[j - gap].hash > t.hash || (a[j - gap].hash == t.hash && a[j - gap].row > t.row));
                 j -= gap)
                a[j] = a[j - gap];
            a[j] = t;
        }
    }
}

/* al/<id>.idx from the songs of songs.idx that name this album, when all of them are there (the album's own count, from albums.idx): the rows are the getAlbum path's, the file the same kind. SBA_OK or a write failure. */
static int sba_derive_one(const sba_album_t *a, int sfd) {
    unsigned h = sba_fnv(a->id), lo = 0, hi = bg.en, i, got = 0;
    char path[SBA_PATH];
    sba_track_t t;
    sba_w_t f;
    int code;
    if (!a->id[0] || !a->songs || a->songs > SBA_ALBUM_TRACKS) return SBA_OK;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (bg.e[mid].hash < h)
            lo = mid + 1;
        else
            hi = mid;
    }
    for (i = lo; i < bg.en && bg.e[i].hash == h; ++i) {
    }
    if (i - lo < a->songs || sba_idpath(path, sizeof path, SBA_DIR "/al", a->id, ".idx")) return SBA_OK;
    code = sba_wopen(&f, path, SBK_TRACK, sizeof t, 0);
    if (code) return code;
    for (i = lo; i < bg.en && bg.e[i].hash == h && !code; ++i) {
        if (lseek(sfd, (long)(sizeof(sba_head_t) + bg.e[i].row * sizeof t), 0) < 0 || !sba_read_all(sfd, &t, sizeof t))
            code = SBA_STORAGE;
        else if (sba_same(t.album_id, a->id)) {
            if (sba_wput(&f, &t, sizeof t))
                ++got;
            else
                code = SBA_STORAGE;
        }
    }
    if (code ||
        got !=
            a->songs) { /* a count that does not match (a library cut at SBA_MAX_TRACKS, a server that miscounts): getAlbum answers when the page opens */
        sba_wabort(&f);
        return code;
    }
    return sba_wcommit(&f);
}

static int sba_bg_derive(sba_wk_t *w) {
    unsigned srows = 0, total = 0, got, i;
    sba_album_t *al = (sba_album_t *)0;
    sba_track_t *rows = (sba_track_t *)0;
    int code, fd = open(SBA_DIR "/songs.idx", O_RDONLY, 0);
    if (fd < 0 || !sba_head(fd, SBK_TRACK, sizeof(sba_track_t), &srows, (unsigned *)0)) {
        if (fd >= 0) close(fd);
        return sba_bg_to(BGS_COVERS);
    }
    if (srows > SBA_MAX_TRACKS) srows = SBA_MAX_TRACKS;
    if ((code = sba_stop(w)) != 0 || (code = sba_bg_room()) != 0) {
        close(fd);
        return sba_bg_fail(w, code);
    }
    if (!bg.e) {
        bg.e = calloc(srows ? srows : 1, sizeof *bg.e);
        bg.en = bg.eread = bg.esorted = 0;
        if (!bg.e) { /* no memory for the index: the albums are fetched as pages open them */
            close(fd);
            return sba_bg_to(BGS_COVERS);
        }
    }
    sba_bg_pub(1, srows, srows);
    if (!bg.esorted) { /* the index of songs.idx by album, a few chunks a step */
        rows = calloc(SBA_CHUNK, sizeof *rows);
        for (i = 0; rows && i < SBA_BG_ROWS && bg.eread < srows; ++i) {
            unsigned take = srows - bg.eread < SBA_CHUNK ? srows - bg.eread : SBA_CHUNK, k;
            if (lseek(fd, (long)(sizeof(sba_head_t) + bg.eread * sizeof *rows), 0) < 0 ||
                !sba_read_all(fd, rows, take * (unsigned)sizeof *rows)) {
                srows = bg.eread; /* (cannot happen: the file was just sized) */
                break;
            }
            for (k = 0; k < take; ++k)
                if (rows[k].album_id[0]) bg.e[bg.en].hash = sba_fnv(rows[k].album_id), bg.e[bg.en++].row = bg.eread + k;
            bg.eread += take;
        }
        close(fd);
        if (!rows) return sba_bg_fail(w, SBA_MEM);
        free(rows);
        if (bg.eread >= srows) {
            sba_ent_sort(bg.e, bg.en);
            bg.esorted = 1;
        }
        return 1;
    }
    al = calloc(SBA_CHUNK, sizeof *al);
    if (!al) {
        close(fd);
        return sba_bg_fail(w, SBA_MEM);
    }
    got = sba_bg_albums(bg.s.gcur, SBA_CHUNK, al, &total);
    code = SBA_OK;
    for (i = 0; i < got && !code; ++i) code = sba_derive_one(&al[i], fd);
    free(al);
    close(fd);
    if (code) return sba_bg_fail(w, code);
    bg.fails = 0;
    bg.s.gcur += got;
    if (!got || bg.s.gcur >= total) { /* all the albums: the pages that waited for a track list read again */
        sba_bump();
        return sba_bg_to(BGS_COVERS);
    }
    sba_bg_write(&bg.s);
    return 1;
}

/* The coverArt ids of up to n rows (at most SBA_CHUNK) of albums.idx (art 0) or artists.idx (art 1) from row `from`, read through buf (SBA_CHUNK rows of the larger kind); the rows read. *total is the file's row
 * count (0 when it is not there). */
static unsigned sba_bg_cids(int art, unsigned from, unsigned n, void *buf, char (*ids)[SBA_ID], unsigned *total) {
    unsigned rows = 0, got = 0, i, size = art ? (unsigned)sizeof(sba_artist_t) : (unsigned)sizeof(sba_album_t);
    int fd = open(art ? SBA_DIR "/artists.idx" : SBA_DIR "/albums.idx", O_RDONLY, 0);
    *total = 0;
    if (fd < 0) return 0;
    if (sba_head(fd, art ? SBK_ARTIST : SBK_ALBUM, size, &rows, (unsigned *)0)) {
        *total = rows;
        if (from < rows) {
            if (n > rows - from) n = rows - from;
            if (lseek(fd, (long)(sizeof(sba_head_t) + from * size), 0) >= 0 && sba_read_all(fd, buf, n * size)) got = n;
        }
    }
    close(fd);
    for (i = 0; i < got; ++i)
        sba_copy(ids[i], SBA_ID, art ? ((sba_artist_t *)buf)[i].cover : ((sba_album_t *)buf)[i].cover);
    return got;
}

/* Covers (art 0: every album's, progress kind 2) and then artist pictures (art 1: every artist's, kind 3), the same way: first the ones whose file is missing are counted (the progress total, a few hundred a
 * step), then one a step, in the file's order. A picture that fails three times in a run is left for the next run. The stage after the covers is the artists'; after those, done. */
static int sba_bg_covers(sba_wk_t *w, int art) {
    void *buf =
        calloc(SBA_CHUNK, sizeof(sba_album_t) > sizeof(sba_artist_t) ? sizeof(sba_album_t) : sizeof(sba_artist_t));
    char ids[SBA_CHUNK][SBA_ID];
    unsigned total = 0, got, i, upto;
    int code = sba_stop(w), kind = art ? 3 : 2;
    if (code) {
        free(buf);
        return sba_bg_fail(w, code);
    }
    if (!buf) return sba_bg_fail(w, SBA_MEM);
    if (!bg.cphase) {
        upto = bg.ccount + SBA_BG_COUNT;
        do {
            got = sba_bg_cids(art, bg.ccount, SBA_CHUNK, buf, ids, &total);
            for (i = 0; i < got; ++i)
                if (ids[i][0] && !sba_cover_have(ids[i])) ++bg.btotal;
            bg.ccount += got;
        } while (got && bg.ccount < upto);
        free(buf);
        if (!got || bg.ccount >= total) bg.cphase = 1;
        if (!art || bg.btotal)
            sba_bg_pub(kind, 0, bg.btotal); /* (no "0/0" line for a library whose artists all have their files) */
        return 1;
    }
    got = sba_bg_cids(art, bg.bcur, SBA_CHUNK, buf, ids, &total);
    for (i = 0; i < got; ++i) {
        int have = 0;
        if (!ids[i][0] || sba_cover_have(ids[i])) continue;
        if ((code = sba_bg_room()) != 0) break;
        sba.bg_run = 1;
        code = sba_run_cover(w, ids[i]);
        sba.bg_run = 0;
        have = sba_cover_have(ids[i]);
        if (code == SBA_PARSE && w->sink->http_status == 200 && w->sink->used && sba_cover_mark(ids[i])) {
            code = SBA_NOTFOUND,
            have =
                1; /* an answer that is no picture (a Subsonic error in JSON, an HTML page): no art for this one, never retried, no pause */
        }
        if (code == SBA_OK || (code == SBA_NOTFOUND && have)) { /* the file, or the marker for "no art" */
            code = SBA_OK;
            ++bg.bdone, bg.fails = bg.cfail = 0;
            bg.bcur += i + 1;
            sba_bg_pub(kind, bg.bdone, bg.btotal > bg.bdone ? bg.btotal : bg.bdone);
            free(buf);
            return 1;
        }
        if (code ==
            SBA_NET) /* no answer from the server (Wi-Fi gone, unreachable): not a try of this cover and never a skip, only a failure of the run (sba_bg_fail ends it after SBA_BG_FAILS) */
            bg.bcur += i;
        else if (
            sba_pick() < 0 &&
            ++bg.cfail >=
                SBA_BG_TRIES) { /* this one will not come: the next run tries it again (a cut-off by a page's request is not a try) */
            ++bg.skip, bg.cfail = 0, bg.fails = 0; /* (a skip is progress: the next one starts with its own tries) */
            bg.bcur += i + 1;
            code = SBA_OK;
        } else
            bg.bcur += i;
        break;
    }
    free(buf);
    if (code) return sba_bg_fail(w, code);
    if (i >= got) { /* a chunk with nothing to fetch */
        bg.bcur += got;
        if (!got || bg.bcur >= total) { /* done: every picture has a file or a marker (or was left for the next run) */
            if (!art) { /* on to the artists, remembering the covers left for the next run */
                unsigned left = bg.skip;
                sba_bg_to(BGS_ARTISTS);
                bg.cskip = left;
                return 1;
            }
            if (bg.cskip) /* the covers that failed come first in the next run */
                bg.s.stage = BGS_COVERS, bg.s.gcur = 0, sba_bg_write(&bg.s);
            else if (!bg.skip)
                sba_bg_to(BGS_DONE);
            else
                sba_bg_write(&bg.s);
            return sba_bg_stop();
        }
    }
    return 1;
}

/* Fill the worker's request fields from the saved login for a request of phase 2 (a page's request does the same in sba_main). */
static void sba_wk_open(sba_wk_t *w, sbn_sink_t *sink) {
    w->sink = sink;
    w->mine = sba.cancel;
    sba.mine = w->mine;
    sba.sink = sink;
    sba_copy(w->url, sizeof w->url, sba.url);
    sba_copy(w->user, sizeof w->user, sba.user);
    sba_copy(w->auth, sizeof w->auth, sba.auth);
}

/* One step of phase 2, called by the worker when no request waits. 1: look again (it did something, or waited a second); 0: nothing to do, the worker may end. */
static int sba_bg_step(sba_wk_t *w, sbn_sink_t *sink) {
    unsigned v[4], now;
    int r;
    if (!sba.bg_want) return sba_bg_stop();
    if (!w || !sink || !pod_card_mounted() || !sba.url[0]) return sba_bg_stop();
    if (bg.loaded && bg.cancel0 != sba.cancel) sba_bg_reset(); /* Sign Out or another server meanwhile */
    if (sba_dl_busy()) { /* a download goes first */
        sba_bg_pub(0, 0, 0);
        sleep(1);
        return 1;
    }
    if (!bg.loaded) {
        unsigned old;
        bg.cancel0 = sba.cancel;
        now = (unsigned)time((long *)0);
        sba_dirs(); /* (the cache folders, for songs.part, bg.txt and al/) */
        if (!sba_sync_read(v) || !v[3] || !sba_bg_read(&bg.s)) {
            if (!v[3]) return sba_bg_stop(); /* no finished sync, so no library to fill from */
            bg.s.sig = 0;
        }
        old = now >= SBA_MIN_EPOCH && now >= bg.s.when && now - bg.s.when >= SBA_BG_MAX_AGE;
        if (bg.s.sig == v[3] && bg.s.stage == BGS_DONE && !old) return sba_bg_stop(); /* done for this library */
        if (bg.s.sig != v[3] || bg.s.stage == BGS_NONE ||
            bg.s.stage == BGS_DONE) { /* a new library, or a week old: from the start */
            unlink(SBA_BG_PART);
            bg.s.sig = v[3], bg.s.stage = BGS_PAGE, bg.s.gcur = 0, bg.s.when = now;
            sba_bg_write(&bg.s);
        }
        bg.star0 = sba.star_n;
        bg.loaded = 1;
    }
    sba_wk_open(w, sink);
    switch (bg.s.stage) {
    case BGS_PAGE:
        r = sba_bg_page(w);
        break;
    case BGS_DERIVE:
        r = sba_bg_derive(w);
        break;
    case BGS_COVERS:
        r = sba_bg_covers(w, 0);
        break;
    case BGS_ARTISTS:
        r = sba_bg_covers(w, 1);
        break;
    default:
        r = sba_bg_stop();
        break;
    }
    sba.sink = (void *)0;
    return r;
}

/* A search3 other than slot `i` is waiting (the user typed on while this one queued). */
static int sba_search_newer(int i) {
    int k;
    for (k = 0; k < SBA_SLOTS; ++k)
        if (k != i && sba.q[k].state == SLOT_WAIT && sba.q[k].kind == SBA_K_SEARCH) return 1;
    return 0;
}

static void *sba_main(void *arg) {
    sba_wk_t *w = calloc(1, sizeof *w);
    sbn_sink_t *sink = calloc(1, sizeof *sink);
    (void)arg;
    for (;;) {
        int i = sba_pick(), trial;
        sba_slot_t *s;
        if (i < 0) {
            if (sba_bg_step(w, sink)) {
                sbn_sink_trim(sink, SBA_KEEP_BODY);
                continue; /* phase 2, with no request waiting */
            }
            sba.busy = 0;
            __sync_synchronize();
            if ((sba_pick() >= 0 || sba.bg_want) && __sync_bool_compare_and_swap(&sba.busy, 0, 1)) continue;
            break;
        }
        s = &sba.q[i];
        if (!__sync_bool_compare_and_swap(&s->state, SLOT_WAIT, SLOT_ACTIVE)) continue;
        if (s->kind == SBA_K_SEARCH &&
            sba_search_newer(
                i)) { /* a later search waits: this one is superseded and never goes out (the status stays the later one's) */
            __sync_synchronize();
            s->state = SLOT_FREE;
            continue;
        }
        if (!w || !sink) {
            if (s->kind == SBA_K_PING && s->arg) free((void *)(unsigned long)s->arg), s->arg = 0;
            if (s->kind == SBA_K_STAR && s->arg) free((void *)(unsigned long)s->arg), s->arg = 0;
            sba_fin(s, SBA_MEM);
            continue;
        }
        sba_wk_open(w, sink);
        trial = s->kind == SBA_K_PING && s->arg;
        if (trial) { /* a trial ping: the login this request was asked with, not the saved one */
            sba_trial_t *t = (sba_trial_t *)(unsigned long)s->arg;
            sba_copy(w->url, sizeof w->url, t->url);
            sba_copy(w->user, sizeof w->user, t->user);
            sba_copy(w->auth, sizeof w->auth, t->auth);
            memset(t, 0, sizeof *t);
            free(t);
            s->arg = 0;
        }
        if (sba.cancel !=
            w->mine) { /* cancelled before it ran: a star's block and overlay entry go (the trial ping's block was freed above) */
            if (s->kind == SBA_K_STAR && s->arg) {
                sba_star_arg_t *st = (sba_star_arg_t *)(unsigned long)s->arg;
                sba_ov_release(st->row.id);
                free(st);
                s->arg = 0;
            }
            sba_fin(s, SBA_CANCELLED);
        } else
            sba_fin(s, sba_run(w, s));
        sba.sink = (void *)0;
        sbn_sink_trim(sink, SBA_KEEP_BODY);
    }
    if (w) memset(w->auth, 0, sizeof w->auth);
    free(w);
    if (sink) sbn_sink_free(sink);
    free(sink);
    return (void *)0;
}

/* Queue a request: the guard first, then a free slot; the worker is started when none is running. SBA_OK = queued (or the same request is already waiting). */
static int sba_enqueue(int kind, const char *id, unsigned arg, const char *term, int covers_cap, int code) {
    int i, slot = -1, covers = 0;
    unsigned long th = 0;
    sba_slot_t *s;
    if (code) return code;
    if (!sba_net_ready()) return SBA_MEM;
    for (i = 0; i < SBA_SLOTS; ++i) {
        unsigned st = sba.q[i].state;
        if (st == SLOT_FREE) {
            if (slot < 0) slot = i;
            continue;
        }
        if (sba.q[i].kind == SBA_K_COVER) ++covers;
        if ((st == SLOT_WAIT || st == SLOT_ACTIVE) && sba.q[i].kind == kind && kind != SBA_K_STAR &&
            sba_same(sba.q[i].id, id) && (kind != SBA_K_SEARCH || sba_same(sba.q[i].term, term ? term : "")) &&
            (kind != SBA_K_SONGS || sba.q[i].arg == arg) && (kind != SBA_K_PING || sba.q[i].arg == arg))
            return SBA_OK;
    }
    if (slot < 0 || (covers_cap && covers >= SBA_SLOTS - 2)) return SBA_QFULL;
    s = &sba.q[slot];
    if (!__sync_bool_compare_and_swap(&s->state, SLOT_FREE, SLOT_FILL)) return SBA_QFULL;
    s->kind = kind, s->arg = arg, s->seq = ++sba.seq;
    sba_copy(s->id, sizeof s->id, id ? id : "");
    sba_copy(s->term, sizeof s->term, term ? term : "");
    sba_stat_make(kind, s->id);
    sba_stat_set(kind, s->id, SBA_ST_LOAD, 0);
    __sync_synchronize();
    s->state = SLOT_WAIT;
    if (kind != SBA_K_COVER) sba_bump(); /* (a cover is not a change of any list: the pages poll for theirs) */
    if (__sync_bool_compare_and_swap(&sba.busy, 0, 1) && pthread_create(&th, (const void *)0, sba_main, (void *)0)) {
        unsigned st = SLOT_WAIT;
        sba.busy = 0;
        if (__sync_bool_compare_and_swap(&s->state, st, SLOT_FREE)) {
            sba_stat_set(kind, s->id, SBA_ST_NONE, 0);
            return SBA_MEM;
        }
        return SBA_OK; /* a worker took it after all */
    }
    if (th) pthread_detach(th);
    return SBA_OK;
}

static int sba_ask(int kind, const char *id, unsigned arg, const char *term, int covers_cap) {
    return sba_enqueue(kind, id, arg, term, covers_cap, sba_guard());
}

void sba_cancel(void) {
    int i;
    ++sba.cancel;
    sba.bg_want = 0; /* phase 2 ends with the request it is in */
    __sync_synchronize();
    for (i = 0; i < SBA_SLOTS; ++i)
        if (__sync_bool_compare_and_swap(&sba.q[i].state, SLOT_WAIT, SLOT_FREE)) {
            if (sba.q[i].kind == SBA_K_PING && sba.q[i].arg) {
                free((void *)(unsigned long)sba.q[i].arg);
                sba.q[i].arg = 0;
            }
            if (sba.q[i].kind == SBA_K_STAR && sba.q[i].arg) {
                sba_star_arg_t *st = (sba_star_arg_t *)(unsigned long)sba.q[i].arg;
                sba_ov_release(
                    st->row
                        .id); /* a star not sent is taken back: the worker never edited the files, so only the overlay goes */
                free(st);
                sba.q[i].arg = 0;
            }
            sba_stat_set(sba.q[i].kind, sba.q[i].id, SBA_ST_NONE, 0);
        }
    sba_bump();
}

/* ---------------------------------------------------------------------------
 * Asking
 */
int sba_conf_check(int field, const char *text) {
    char clean[SBA_CONF_URL];
    if (!text) return SBA_PARSE;
    if (field == 0) return sba_url_clean(text, clean) ? SBA_OK : SBA_PARSE;
    return sba_text_ok(text, field == 2, field == 1 ? SBA_CONF_USER : SBA_CONF_PASS) ? SBA_OK : SBA_PARSE;
}

int sba_ping_try(const char *url, const char *user, const char *password) {
    char clean[SBA_CONF_URL], id[16];
    int code;
    sba_trial_t *t;
    sba_conf_load();
    if (!url || !sba_url_clean(url, clean) || sba_conf_check(1, user)) return SBA_PARSE;
    if (password && password[0] && sba_conf_check(2, password)) return SBA_PARSE;
    code = sba_guard_for(clean);
    if (code) return code;
    t = calloc(1, sizeof *t);
    if (!t) return SBA_MEM;
    sba_copy(t->url, sizeof t->url, clean);
    sba_copy(t->user, sizeof t->user, user);
    if (password &&
        password
            [0]) { /* a typed password: its own secret, for this try (Sign In makes the saved one when the ping answers) */
        if (sbn_auth_make(t->auth, password)) t->auth[0] = 0;
    } else
        sba_copy(t->auth, sizeof t->auth, sba.auth);
    if (!t->auth[0]) {
        free(t);
        return SBA_PARSE;
    }
    snprintf(id, sizeof id, "t%u", sba.trial_n + 1);
    code = sba_enqueue(SBA_K_PING, id, (unsigned)(unsigned long)t, 0, 0, SBA_OK);
    if (code) {
        memset(t, 0, sizeof *t);
        free(t);
        return code;
    }
    sba.trial_last = ++sba.trial_n;
    return SBA_OK;
}

unsigned sba_trial_id(void) { return sba.trial_last; }

int sba_trial_state(unsigned id, int *code) {
    char name[16];
    snprintf(name, sizeof name, "t%u", id);
    return id ? sba_state(SBA_K_PING, name, code) : SBA_ST_NONE;
}

int sba_sync(void) {
    int was = sba.bg_want, rc;
    sba.bg_want =
        1; /* phase 2 follows the sync on the worker (it refreshes songs.idx itself when the library changed); set first, the worker may be quick */
    rc = sba_ask(SBA_K_SYNC, "", 0, 0, 0);
    if (rc != SBA_OK) sba.bg_want = was;
    return rc;
}
int sba_fetch_album(const char *id) { return id && id[0] ? sba_ask(SBA_K_ALBUM, id, 0, 0, 0) : SBA_NOTFOUND; }
int sba_fetch_artist(const char *id) { return id && id[0] ? sba_ask(SBA_K_ARTIST, id, 0, 0, 0) : SBA_NOTFOUND; }
int sba_fetch_playlist(const char *id) { return id && id[0] ? sba_ask(SBA_K_PLAYLIST, id, 0, 0, 0) : SBA_NOTFOUND; }
int sba_fetch_songs(unsigned offset) { return sba_ask(SBA_K_SONGS, "", offset, 0, 0); }
int sba_search(const char *term) { return term && term[0] ? sba_ask(SBA_K_SEARCH, "", 0, term, 0) : SBA_PARSE; }
int sba_search_is(const char *term) { return term && sba.search_done == sba_fnv(term); }

int sba_sync_due(void) {
    unsigned songs, when, now = (unsigned)time((long *)0);
    int trunc;
    if (!sba_summary(&songs, &when, &trunc)) return 1;
    return now < SBA_MIN_EPOCH || now < when || now - when >= SBA_SYNC_MAX_AGE;
}

int sba_sync_auto(void) {
    if (sba_sync_due()) return sba_sync();
    sba_bg_kick(); /* a fresh cache: phase 2 resumes if it has anything left */
    return SBA_OK;
}

/* Start (or resume) phase 2 with no sync before it: Wi-Fi up, a finished sync whose library has not been filled. The worker is started if it is not running; it ends when there is nothing left. */
void sba_bg_kick(void) {
    unsigned long th = 0;
    if (sba_guard() != SBA_OK || !sba_net_ready() || !sba_bg_pending()) return;
    sba.bg_want = 1;
    __sync_synchronize();
    if (__sync_bool_compare_and_swap(&sba.busy, 0, 1)) {
        if (pthread_create(&th, (const void *)0, sba_main, (void *)0)) {
            sba.busy = 0;
            return;
        }
        pthread_detach(th);
    }
}

int sba_bg_progress(unsigned *done, unsigned *total) {
    int kind = sba.bg_kind;
    if (done) *done = sba.bg_done;
    if (total) *total = sba.bg_total;
    return kind;
}

unsigned sba_bg_gen(void) { return sba.bg_gen; }

/* sync.txt: "<when> <songs> <truncated> <signature>" (the signature is phase 2's; a file without it reads 0). 1 when there is a finished sync. */
static int sba_sync_read(unsigned v[4]) {
    char text[64];
    unsigned i, k = 0;
    int fd = open(SBA_DIR "/sync.txt", O_RDONLY, 0), r;
    v[0] = v[1] = v[2] = v[3] = 0;
    if (fd < 0) return 0;
    r = read(fd, text, sizeof text - 1);
    close(fd);
    if (r <= 0) return 0;
    text[r] = 0;
    for (i = 0; text[i] && k < 4; ++i) {
        if (text[i] >= '0' && text[i] <= '9')
            v[k] = v[k] * 10 + (unsigned)(text[i] - '0');
        else if (text[i] == ' ')
            ++k;
    }
    return v[0] != 0;
}

int sba_summary(unsigned *songs, unsigned *when, int *truncated) {
    unsigned v[4];
    if (!sba_sync_read(v)) return 0;
    if (when) *when = v[0];
    if (songs) *songs = v[1];
    if (truncated) *truncated = (int)v[2];
    return 1;
}

int sba_star(const sba_track_t *t, int on) {
    sba_star_arg_t *st;
    int code = sba_guard();
    if (code) return code;
    if (!t || !t->id[0]) return SBA_NOTFOUND;
    st = calloc(1, sizeof *st);
    if (!st) return SBA_MEM;
    memcpy(&st->row, t, sizeof st->row);
    st->on = on != 0;
    if (!sba_ov_hold(t->id, on != 0)) { /* the heart flips at once through the overlay; the worker edits the files */
        free(st);
        return SBA_QFULL;
    }
    sba_bump();
    code = sba_ask(SBA_K_STAR, t->id, (unsigned)(unsigned long)st, 0, 0);
    if (code) {
        sba_ov_release(t->id);
        sba_bump();
        free(st);
    }
    return code;
}

/* ---------------------------------------------------------------------------
 * Covers
 */
static int sba_hash_path(char *out, unsigned cap, unsigned hash) {
    if (!out || cap < sizeof SBA_COVER_DIR + 17) return -1; /* "/" + 8 hex + "-168.jpg" + NUL */
    return snprintf(out, cap, SBA_COVER_DIR "/%08x-%u.jpg", hash, SBA_COVER_PX) < (int)cap ? 0 : -1;
}

int sba_cover_path(char *out, unsigned cap, const char *cover) {
    if (!cover || !cover[0]) return -1;
    return sba_hash_path(out, cap, sba_fnv(cover));
}

/* 1 the file at path has a picture, -1 it is an empty marker, 0 it is not there. */
static int sba_file_have(const char *path) {
    long size;
    int fd = open(path, O_RDONLY, 0);
    if (fd < 0) return 0;
    size = lseek(fd, 0, 2);
    close(fd);
    return size > 0 ? 1 : -1;
}

int sba_cover_have(const char *cover) {
    char path[SBA_PATH];
    if (sba_cover_path(path, sizeof path, cover)) return 0;
    return sba_file_have(path);
}

int sba_cover_hash_path(unsigned hash, char *out, unsigned cap) { return sba_hash_path(out, cap, hash); }

unsigned sba_cover_hash(const char *path) {
    unsigned h = 0;
    int i;
    const char *name = path;
    while (*path)
        if (*path++ == '/') name = path;
    for (i = 0; i < 8; ++i) {
        char c = name[i];
        unsigned v = c >= '0' && c <= '9' ? (unsigned)(c - '0') : c >= 'a' && c <= 'f' ? (unsigned)(c - 'a' + 10) : 16u;
        if (v > 15) return 0;
        h = h << 4 | v;
    }
    return h;
}

int sba_cover(const char *cover) {
    int have = sba_cover_have(cover);
    if (!cover || !cover[0]) return SBA_NOTFOUND;
    if (have) return have > 0 ? SBA_OK : SBA_NOTFOUND;
    return sba_ask(SBA_K_COVER, cover, 0, 0, 1);
}

/* A coverArt id's file for a page: 1 (path set), -1 (no art: an empty id, an empty marker, a failed or refused ask) or 0 (asked for, or on its way; the caller polls). ask 0 only looks at the card. */
static int sba_cover_id(const char *cover, char *path, unsigned cap, int ask) {
    int have, code;
    if (!cover || !cover[0] || sba_cover_path(path, cap, cover)) return -1;
    have = sba_file_have(path);
    if (have || !ask) return have;
    if (sba_state(SBA_K_COVER, cover, (int *)0) == SBA_ST_FAIL) return -1;
    code = sba_cover(cover);
    return code == SBA_OK || code == SBA_QFULL ? 0 : -1;
}

int sba_cover_get(const char *cover, char *path, unsigned cap) { return sba_cover_id(cover, path, cap, 1); }

static void sba_acov_sort(sba_acov_t *a, unsigned n) {
    static const unsigned gaps[] = {701, 301, 132, 57, 23, 10, 4, 1};
    unsigned g, i, j;
    for (g = 0; g < sizeof gaps / sizeof gaps[0]; ++g) {
        unsigned gap = gaps[g];
        for (i = gap; i < n; ++i) {
            sba_acov_t t = a[i];
            for (j = i; j >= gap && (a[j - gap].h1 > t.h1 || (a[j - gap].h1 == t.h1 && a[j - gap].h2 > t.h2)); j -= gap)
                a[j] = a[j - gap];
            a[j] = t;
        }
    }
}

/* The album's row of albcov.idx (read again when a sync or a cache clear moved agen), NULL when the file or the album is not there. Page side only. */
static const sba_acov_t *sba_acov_find(const char *id) {
    unsigned h1, h2, lo = 0, hi, seen = sba.agen + 1u;
    if (sba.acov_seen != seen) {
        void *v;
        int n = sba_load(SBA_DIR "/albcov.idx", SBK_ACOV, sizeof(sba_acov_t), SBA_MAX_ALBUMS, &v, (unsigned *)0);
        free(sba.acov);
        sba.acov = n > 0 ? (sba_acov_t *)v : (sba_acov_t *)0;
        sba.acov_n = n > 0 ? (unsigned)n : 0;
        sba.acov_seen = seen;
        if (sba.acov) sba_acov_sort(sba.acov, sba.acov_n);
    }
    h1 = sba_fnv(id), h2 = sba_hash2(id), hi = sba.acov_n;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (sba.acov[mid].h1 < h1 || (sba.acov[mid].h1 == h1 && sba.acov[mid].h2 < h2))
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo < sba.acov_n && sba.acov[lo].h1 == h1 && sba.acov[lo].h2 == h2 ? &sba.acov[lo] : (const sba_acov_t *)0;
}

int sba_track_cover(const char *album_id, const char *own, char *path, unsigned cap, int ask) {
    const sba_acov_t *e = album_id && album_id[0] ? sba_acov_find(album_id) : (const sba_acov_t *)0;
    if (e && e->cover && !sba_hash_path(path, cap, e->cover)) {
        sba_album_t a;
        unsigned total;
        int have = sba_file_have(path);
        if (have || !ask) return have; /* (the file phase 2 fetched for the album: nothing else is read) */
        if (sba_bg_albums(e->row, 1, &a, &total) == 1 && sba_row_is(&a, album_id) && a.cover[0])
            return sba_cover_id(a.cover, path, cap, 1);
    }
    return sba_cover_id(own, path, cap, ask);
}

/* ---------------------------------------------------------------------------
 * Reading the cache
 */
void sba_free_tracks(sba_tracks_t *l) {
    free(l->v);
    l->v = (sba_track_t *)0;
    l->n = 0;
}
void sba_free_albums(sba_albums_t *l) {
    free(l->v);
    l->v = (sba_album_t *)0;
    l->n = 0;
}
void sba_free_artists(sba_artists_t *l) {
    free(l->v);
    l->v = (sba_artist_t *)0;
    l->n = 0;
}
void sba_free_playlists(sba_playlists_t *l) {
    free(l->v);
    l->v = (sba_playlist_t *)0;
    l->n = 0;
}

/* The starred ids: starred.idx (the Favorites list, replaced by every sync) is the truth for a heart, whatever flag a row of another file was written with. Loaded here in chunks as two hashes an id
 * (8 bytes, at most SBA_STARRED_MAX; never the whole 2.4 MB file), sorted, and read again when the worker committed the file (sgen). A missing or unreadable file (no sync yet, the list was refused,
 * no memory) leaves sset_ok 0: nothing is applied and the rows keep their own flags. Page side only. */
static void sba_sset_sort(sba_hh_t *a, unsigned n) {
    static const unsigned gaps[] = {701, 301, 132, 57, 23, 10, 4, 1};
    unsigned g, i, j;
    for (g = 0; g < sizeof gaps / sizeof gaps[0]; ++g) {
        unsigned gap = gaps[g];
        for (i = gap; i < n; ++i) {
            sba_hh_t t = a[i];
            for (j = i; j >= gap && (a[j - gap].h1 > t.h1 || (a[j - gap].h1 == t.h1 && a[j - gap].h2 > t.h2)); j -= gap)
                a[j] = a[j - gap];
            a[j] = t;
        }
    }
}

static void sba_sset_load(void) {
    unsigned seen = sba.sgen + 1u, rows = 0, n = 0, left, i;
    sba_track_t *buf = (sba_track_t *)0;
    int fd, ok = 0;
    if (sba.sset_seen == seen) return;
    free(sba.sset);
    sba.sset = (sba_hh_t *)0, sba.sset_n = 0, sba.sset_ok = 0, sba.sset_seen = seen;
    fd = open(SBA_DIR "/starred.idx", O_RDONLY, 0);
    if (fd < 0) return;
    if (sba_head(fd, SBK_TRACK, sizeof *buf, &rows, (unsigned *)0)) {
        if (rows > SBA_STARRED_MAX) rows = SBA_STARRED_MAX;
        buf = calloc(SBA_CHUNK, sizeof *buf);
        if (rows) sba.sset = calloc(rows, sizeof *sba.sset);
        ok = buf && (!rows || sba.sset);
    }
    for (left = rows; ok && left;) {
        unsigned take = left < SBA_CHUNK ? left : SBA_CHUNK;
        if (!sba_read_all(fd, buf, take * (unsigned)sizeof *buf)) {
            ok = 0;
            break;
        }
        for (i = 0; i < take; ++i) sba.sset[n].h1 = sba_fnv(buf[i].id), sba.sset[n++].h2 = sba_hash2(buf[i].id);
        left -= take;
    }
    close(fd);
    free(buf);
    if (!ok) {
        free(sba.sset);
        sba.sset = (sba_hh_t *)0;
        return;
    }
    sba_sset_sort(sba.sset, n);
    sba.sset_n = n, sba.sset_ok = 1;
}

/* Every row's starred flag := its id is in starred.idx; nothing when that file is not usable. */
static void sba_starred_apply(sba_track_t *v, int n) {
    int i;
    sba_sset_load();
    if (!sba.sset_ok) return;
    for (i = 0; i < n; ++i) {
        unsigned h1 = sba_fnv(v[i].id), h2 = sba_hash2(v[i].id), lo = 0, hi = sba.sset_n;
        while (lo < hi) {
            unsigned mid = (lo + hi) / 2;
            if (sba.sset[mid].h1 < h1 || (sba.sset[mid].h1 == h1 && sba.sset[mid].h2 < h2))
                lo = mid + 1;
            else
                hi = mid;
        }
        v[i].starred = lo < sba.sset_n && sba.sset[lo].h1 == h1 && sba.sset[lo].h2 == h2;
    }
}

void sba_hearts(sba_track_t *v, int n) {
    if (!v || n <= 0) return;
    sba_starred_apply(v, n);
    sba_ov_apply(v, n);
}

static int sba_tracks_at(const char *path, unsigned max, sba_tracks_t *out) {
    int n = sba_load(path, SBK_TRACK, sizeof(sba_track_t), max, (void **)&out->v, (unsigned *)0);
    out->n = n < 0 ? 0 : n;
    if (n > 0) {
        if (!sba_same(path, SBA_DIR "/starred.idx")) sba_starred_apply(out->v, n); /* (its own rows are starred) */
        sba_ov_apply(out->v, n);
    }
    return n;
}
static int sba_albums_at(const char *path, sba_albums_t *out) {
    int n = sba_load(path, SBK_ALBUM, sizeof(sba_album_t), SBA_MAX_ALBUMS, (void **)&out->v, (unsigned *)0);
    out->n = n < 0 ? 0 : n;
    return n;
}

int sba_albums(sba_albums_t *out) { return sba_albums_at(SBA_DIR "/albums.idx", out); }
int sba_search_albums(sba_albums_t *out) { return sba_albums_at(SBA_DIR "/search-al.idx", out); }
int sba_starred_tracks(sba_tracks_t *out) { return sba_tracks_at(SBA_DIR "/starred.idx", SBA_STARRED_MAX, out); }
int sba_search_tracks(sba_tracks_t *out) { return sba_tracks_at(SBA_DIR "/search.idx", SBA_SEARCH_N, out); }
int sba_songs(sba_tracks_t *out) { return sba_tracks_at(SBA_DIR "/songs.idx", SBA_MAX_TRACKS, out); }

int sba_artists(sba_artists_t *out) {
    int n = sba_load(SBA_DIR "/artists.idx", SBK_ARTIST, sizeof(sba_artist_t), SBA_ARTISTS_MAX, (void **)&out->v,
                     (unsigned *)0);
    out->n = n < 0 ? 0 : n;
    return n;
}
int sba_search_artists(sba_artists_t *out) {
    int n = sba_load(SBA_DIR "/search-ar.idx", SBK_ARTIST, sizeof(sba_artist_t), SBA_SEARCH_N, (void **)&out->v,
                     (unsigned *)0);
    out->n = n < 0 ? 0 : n;
    return n;
}
int sba_playlists(sba_playlists_t *out) {
    int n = sba_load(SBA_DIR "/playlists.idx", SBK_PLAYLIST, sizeof(sba_playlist_t), SBA_PLAYLISTS_MAX,
                     (void **)&out->v, (unsigned *)0);
    out->n = n < 0 ? 0 : n;
    return n;
}

int sba_album_tracks(const char *id, sba_tracks_t *out) {
    char path[SBA_PATH];
    int n, i, j;
    out->n = 0, out->v = (sba_track_t *)0;
    if (sba_idpath(path, sizeof path, SBA_DIR "/al", id, ".idx")) return 0;
    n = sba_tracks_at(path, SBA_ALBUM_TRACKS, out);
    for (i = 1; i < n; ++i) { /* disc, then track (stable) */
        sba_track_t t;
        memcpy(&t, &out->v[i], sizeof t);
        for (j = i - 1; j >= 0 && (out->v[j].disc > t.disc || (out->v[j].disc == t.disc && out->v[j].track > t.track));
             --j)
            memcpy(&out->v[j + 1], &out->v[j], sizeof t);
        memcpy(&out->v[j + 1], &t, sizeof t);
    }
    return n;
}

/* An artist's albums: ar/<id>.idx (getArtist) when it is there; until then the albums of albums.idx that name the artist (the sync has them all), so the artist's page and its All Songs open without waiting
 * for the first getArtist. The page asks for the real list as before. A streaming scan: 16 rows at a time, the matches only are kept. */
int sba_artist_albums(const char *id, sba_albums_t *out) {
    char path[SBA_PATH];
    sba_album_t *chunk;
    unsigned from = 0, got, total = 0, i;
    int cap = 0;
    out->n = 0, out->v = (sba_album_t *)0;
    if (sba_idpath(path, sizeof path, SBA_DIR "/ar", id, ".idx")) return 0;
    if (access(path, 0) == 0 || !id || !id[0]) return sba_albums_at(path, out);
    chunk = calloc(SBA_CHUNK, sizeof *chunk);
    if (!chunk) return 0;
    do {
        got = sba_bg_albums(from, SBA_CHUNK, chunk, &total);
        for (i = 0; i < got; ++i) {
            if (!sba_same(chunk[i].artist_id, id)) continue;
            if (out->n == cap) {
                sba_album_t *v = calloc((unsigned)cap + 64, sizeof *v);
                if (!v) {
                    sba_free_albums(out);
                    free(chunk);
                    return 0;
                }
                if (out->n) memcpy(v, out->v, (unsigned)out->n * sizeof *v);
                free(out->v);
                out->v = v;
                cap += 64;
            }
            memcpy(&out->v[out->n++], &chunk[i], sizeof *chunk);
        }
        from += got;
    } while (got && from < total);
    free(chunk);
    return out->n;
}

int sba_playlist_tracks(const char *id, sba_tracks_t *out) {
    char path[SBA_PATH];
    out->n = 0, out->v = (sba_track_t *)0;
    if (sba_idpath(path, sizeof path, SBA_DIR "/pl", id, ".idx")) return 0;
    return sba_tracks_at(path, SBA_ALBUM_TRACKS, out);
}

int sba_songs_more(void) {
    unsigned rows, flags = 0;
    int fd = open(SBA_DIR "/songs.idx", O_RDONLY, 0), ok;
    if (fd < 0) return 0;
    ok = sba_head(fd, SBK_TRACK, sizeof(sba_track_t), &rows, &flags);
    close(fd);
    return ok && (flags & 1) && rows < SBA_MAX_TRACKS;
}

/* Rows [offset, offset + n) of songs.idx into out (the caller's array of n rows), without loading the file: the Songs list is read a few dozen rows at a time. The rows read (0 past the end or no file). */
int sba_songs_window(unsigned offset, int n, sba_track_t *out) {
    unsigned rows, flags;
    int fd = open(SBA_DIR "/songs.idx", O_RDONLY, 0), got = 0;
    if (fd < 0) return 0;
    if (n > 0 && sba_head(fd, SBK_TRACK, sizeof(sba_track_t), &rows, &flags) && offset < rows) {
        if (rows > SBA_MAX_TRACKS) rows = SBA_MAX_TRACKS;
        if (offset < rows) {
            if ((unsigned)n > rows - offset) n = (int)(rows - offset);
            if (lseek(fd, (long)(sizeof(sba_head_t) + offset * sizeof(sba_track_t)), 0) >= 0 &&
                sba_read_all(fd, out, (unsigned)n * (unsigned)sizeof(sba_track_t)))
                got = n;
        }
    }
    close(fd);
    if (got > 0) sba_starred_apply(out, got);
    return got;
}

int sba_songs_cached(void) {
    unsigned rows, flags;
    int fd = open(SBA_DIR "/songs.idx", O_RDONLY, 0), ok;
    if (fd < 0) return 0;
    ok = sba_head(fd, SBK_TRACK, sizeof(sba_track_t), &rows, &flags);
    close(fd);
    return ok ? (int)rows : 0;
}

/* ---------------------------------------------------------------------------
 * Playing
 */
int sba_stream_url(char *out, unsigned cap, const char *id) {
    sbn_server_t srv;
    if (!sba_configured() || !id || !id[0]) return -1;
    srv.base = sba.url, srv.user = sba.user, srv.auth = sba.auth;
    return sbn_url(out, cap, srv, "stream", id, (const char *)0) ? -1 : 0;
}

int sba_is_dsd(const char *suffix) {
    if (!suffix || sba_len(suffix) != 3) return 0;
    return sbn_ascii_lower((unsigned char)suffix[0]) == 'd' &&
           (sbn_ascii_lower((unsigned char)suffix[1]) == 's' || sbn_ascii_lower((unsigned char)suffix[1]) == 'f') &&
           sbn_ascii_lower((unsigned char)suffix[2]) == 'f';
}

/* "<title>.<suffix>": '/' and control characters in the title become '_', the title is cut at a UTF-8 boundary to leave room for the suffix; a suffix with anything but letters and
 * digits is left off. Returns the length, -1 for no room at all. */
int sba_track_filename(char *out, unsigned cap, const sba_track_t *t) {
    const char *title;
    char suffix[SBA_SUFFIX + 1];
    unsigned i, n = 0, room, sl = 0;
    if (!out || cap < 2 || !t) return -1;
    title = t->title[0] ? t->title : "Untitled";
    for (i = 0; t->suffix[i] && i < SBA_SUFFIX; ++i) {
        unsigned char c = (unsigned char)t->suffix[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) {
            sl = 0;
            break;
        }
        suffix[sl++] = (char)c;
    }
    suffix[sl] = 0;
    room = cap - 1 - (sl ? sl + 1 : 0);
    if (room > cap) room = 0;
    while (title[n] && n < room) {
        unsigned char c = (unsigned char)title[n];
        out[n] = c < 32 || c == 127 || c == '/' ? '_' : (char)c;
        ++n;
    }
    if (title[n]) /* cut mid-character: back to the character's first byte */
        while (n && ((unsigned char)title[n] & 0xc0) == 0x80) --n;
    if (!n) return -1;
    if (sl) {
        out[n++] = '.';
        memcpy(out + n, suffix, sl);
        n += sl;
    }
    out[n] = 0;
    return (int)n;
}

/* The synthetic REC_ID of a track id: -(FNV-1a & 0x3fffffff) - 2 (always <= -2), as the PR makes it. */
static int sba_rec_of(const char *id) { return -(int)((sba_fnv(id) & 0x3fffffffu) + 2u); }

/* The map a sba_queue_note replaced, kept until sba_queue_keep (the queue was built) or sba_queue_undo (it could not be): a failed play leaves the playing stream its map. */
static struct {
    sba_map_t *map;
    int n, cap, have;
} sba_prevq __attribute__((section(".scratch")));

void sba_queue_keep(void) {
    free(sba_prevq.map);
    memset(&sba_prevq, 0, sizeof sba_prevq);
}

void sba_queue_undo(void) {
    if (!sba_prevq.have) return;
    free(sba.map);
    sba.map = sba_prevq.map, sba.map_n = sba_prevq.n, sba.map_cap = sba_prevq.cap;
    memset(&sba_prevq, 0, sizeof sba_prevq);
}

void sba_queue_note(const sba_track_t *t, int n, int *rec_id) {
    sba_map_t *m;
    int i, j;
    if (n > SBA_QUEUE_MAX) n = SBA_QUEUE_MAX;
    if (n < 0) n = 0;
    m = calloc(SBA_QUEUE_MAX, sizeof *m);
    if (!m) { /* no memory: the ids are still made, the map is just empty */
        sba_queue_keep();
        free(sba.map);
        sba.map = (sba_map_t *)0;
        sba.map_n = sba.map_cap = 0;
    }
    for (i = 0; i < n; ++i) {
        int rec = sba_rec_of(t[i].id), clash;
        do {
            clash = 0;
            for (j = 0; j < i; ++j)
                if (rec_id[j] == rec) {
                    clash = 1;
                    break;
                }
            if (clash) rec = rec == -1073741825 ? -2 : rec - 1;
        } while (clash);
        rec_id[i] = rec;
        if (m) {
            sba_copy(m[i].id, sizeof m[i].id, t[i].id);
            sba_copy(m[i].cover, sizeof m[i].cover, t[i].cover);
            sba_copy(m[i].album_id, sizeof m[i].album_id, t[i].album_id);
            sba_copy(m[i].suffix, sizeof m[i].suffix, t[i].suffix);
            m[i].rec = rec;
            m[i].size = t[i].size;
        }
    }
    if (!m) return;
    sba_queue_keep();
    sba_prevq.map = sba.map, sba_prevq.n = sba.map_n, sba_prevq.cap = sba.map_cap, sba_prevq.have = 1;
    sba.map = m;
    sba.map_n = n;
    sba.map_cap = SBA_QUEUE_MAX;
}

int sba_queue_add(const sba_track_t *t) {
    int rec, i, clash;
    if (!t || !t->id[0]) return 0;
    for (i = 0; i < sba.map_n; ++i)
        if (!strcmp(sba.map[i].id, t->id))
            return sba.map[i].rec; /* already known (the same track queued again): the same id */
    if (sba.map_n >= sba.map_cap) { /* Play Next / Play After grow the queue past what a play noted */
        int cap = sba.map_cap ? sba.map_cap * 2 : SBA_QUEUE_MAX;
        sba_map_t *m;
        if (cap > SBA_MAP_MAX) return 0;
        m = calloc((unsigned)cap, sizeof *m);
        if (!m) return 0;
        if (sba.map_n) memcpy(m, sba.map, (unsigned)sba.map_n * sizeof *m);
        free(sba.map);
        sba.map = m, sba.map_cap = cap;
    }
    rec = sba_rec_of(t->id);
    do {
        clash = 0;
        for (i = 0; i < sba.map_n; ++i)
            if (sba.map[i].rec == rec) {
                clash = 1;
                break;
            }
        if (clash) rec = rec == -1073741825 ? -2 : rec - 1;
    } while (clash);
    memset(&sba.map[sba.map_n], 0, sizeof sba.map[0]);
    sba_copy(sba.map[sba.map_n].id, sizeof sba.map[0].id, t->id);
    sba_copy(sba.map[sba.map_n].cover, sizeof sba.map[0].cover, t->cover);
    sba_copy(sba.map[sba.map_n].album_id, sizeof sba.map[0].album_id, t->album_id);
    sba_copy(sba.map[sba.map_n].suffix, sizeof sba.map[0].suffix, t->suffix);
    sba.map[sba.map_n].rec = rec;
    sba.map[sba.map_n].size = t->size;
    ++sba.map_n;
    return rec;
}

const char *sba_rec_track(int rec_id) {
    int i;
    if (rec_id > -2) return "";
    for (i = 0; i < sba.map_n; ++i)
        if (sba.map[i].rec == rec_id) return sba.map[i].id;
    return "";
}

unsigned sba_rec_size(int rec_id) {
    int i;
    if (rec_id > -2) return 0;
    for (i = 0; i < sba.map_n; ++i)
        if (sba.map[i].rec == rec_id) return sba.map[i].size;
    return 0;
}

int sba_rec_cover(void *track, char *path, unsigned cap) {
    int rec, i;
    if (!track) return -1;
    rec = *(int *)((char *)track + REC_ID);
    if (rec > -2) return -1;
    /* the album's cover file, else the track's own; not cached: asked for (the caller polls again; a queued ask is not repeated) */
    for (i = 0; i < sba.map_n; ++i)
        if (sba.map[i].rec == rec) return sba_track_cover(sba.map[i].album_id, sba.map[i].cover, path, cap, 1);
    return -1;
}

const char *sba_now_cover(void *track) {
    return sba_rec_cover(track, sba.now, sizeof sba.now) == 1 ? sba.now : (const char *)0;
}

int sba_rec_row(int rec_id, sba_track_t *out) {
    int i;
    if (rec_id > -2) return 0;
    for (i = 0; i < sba.map_n; ++i)
        if (sba.map[i].rec == rec_id) {
            memset(out, 0, sizeof *out);
            sba_copy(out->id, sizeof out->id, sba.map[i].id);
            sba_copy(out->cover, sizeof out->cover, sba.map[i].cover);
            sba_copy(out->album_id, sizeof out->album_id, sba.map[i].album_id);
            sba_copy(out->suffix, sizeof out->suffix, sba.map[i].suffix);
            out->size = sba.map[i].size;
            return 1;
        }
    return 0;
}
