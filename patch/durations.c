/* Track durations: the table, the CUE math and the measurement (docs/modules/album-page.md "Album length").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The database keeps no length for an ordinary file (time / time_end are CUE offsets), so each file's is measured once through stock's TagLib
 * on the shared worker (patch/covercache.c, CC_DURATIONS) and kept in DUR_FILE by path hash. The idea and the vtable call follow q2-pod's Long
 * Songs cache (see patch/durations.h); the format below is this project's: a 12 byte header {magic, count, FNV-1a of the entries}, then count
 * {key, size, seconds} entries sorted by key, read whole and looked up by bisection. A file of the wrong size, magic, order or checksum is
 * ignored (and replaced by the next write). 0 seconds records a file TagLib could not read; it is not measured again until its size changes.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "covercache.h"
#include "i18n.h"
#include "durations.h"
#include "fnv.h"

#define P(w, off) (*(void **)((char *)(w) + (off)))

#define DUR_MAGIC 0x4e4c314du /* "M1LN" */
#define DUR_HDR 12

static struct {
    dur_ent_t *tab;
    unsigned n, users;
    unsigned char *seen; /* the pass's bitmap over tab */
    unsigned named;
} ln __attribute__((section(".scratch")));

unsigned dur_key(const char *path) {
    unsigned k = cc_fnv(FNV_SEED, path);
    return k ? k : 1;
}

static unsigned dur_sum(const dur_ent_t *e, unsigned n) {
    const unsigned char *p = (const unsigned char *)e;
    unsigned h = FNV_SEED, i;
    for (i = 0; i < n * sizeof *e; ++i) h = (h ^ p[i]) * FNV_PRIME;
    return h;
}

/* The file into ln.tab; anything wrong with it reads as an empty table. */
static void dur_read(void) {
    long size = m1_card_mounted() ? cc_file_size(DUR_FILE)
                                  : 0; /* no card, or the computer holds it (USB mode): no table, nothing read */
    unsigned char *buf;
    unsigned n, i, *h;
    int fd, got = 0, r = 1;
    ln.tab = (dur_ent_t *)0;
    ln.n = 0;
    if (size < DUR_HDR || size > DUR_HDR + (long)DUR_MAX_ENTRIES * (long)sizeof(dur_ent_t)) return;
    if ((size - DUR_HDR) % (long)sizeof(dur_ent_t)) return;
    buf = calloc(1, ((unsigned)size));
    fd = buf ? open(DUR_FILE, O_RDONLY, 0) : -1;
    if (fd < 0) {
        free(buf);
        return;
    }
    while (r > 0 && got < size) {
        r = read(fd, buf + got, (unsigned)(size - got));
        if (r > 0) got += r;
    }
    close(fd);
    h = (unsigned *)buf;
    n = (unsigned)(size - DUR_HDR) / (unsigned)sizeof(dur_ent_t);
    if (got == size && h[0] == DUR_MAGIC && h[1] == n && h[2] == dur_sum((const dur_ent_t *)(buf + DUR_HDR), n)) {
        const dur_ent_t *e = (const dur_ent_t *)(buf + DUR_HDR);
        for (i = 1; i < n; ++i)
            if (e[i - 1].key >= e[i].key) break; /* strictly ascending, or it is not ours */
        if (i >= n || n == 0) {
            ln.tab = n ? calloc(1, n * sizeof *e) : (dur_ent_t *)0;
            if (n && !ln.tab) {
                free(buf);
                return;
            }
            if (n) memcpy(ln.tab, e, n * sizeof *e);
            ln.n = n;
        }
    }
    free(buf);
}

void dur_acquire(void) {
    if (ln.users++ == 0) dur_read();
}

void dur_release(void) {
    if (!ln.users || --ln.users) return;
    free(ln.tab);
    free(ln.seen);
    memset(&ln, 0, sizeof ln);
}

static unsigned dur_clears __attribute__((section(".scratch")));

unsigned dur_epoch(void) { return dur_clears; }

void dur_clear(void) {
    if (m1_card_mounted())
        unlink(DUR_FILE), unlink(DUR_FILE ".tmp"); /* (never touch the mount point while the card is out) */
    ++dur_clears;
    free(ln.seen);
    ln.seen = (unsigned char *)0;
    ln.n = 0;
}

/* Measured Tracks: the header's count and the file's size, as the Cache page opened (dur_stat_open). */
static struct {
    unsigned count, bytes;
    int ok;
} ds __attribute__((section(".scratch")));

void dur_stat_open(void) {
    unsigned h[3];
    long size;
    int fd;
    memset(&ds, 0, sizeof ds);
    if (!m1_card_mounted()) return; /* no card, or the computer holds it (USB mode) */
    fd = open(DUR_FILE, O_RDONLY, 0);
    if (fd < 0) return;
    if (read(fd, h, DUR_HDR) == DUR_HDR && h[0] == DUR_MAGIC) {
        size = lseek(fd, 0, 2); /* SEEK_END */
        ds.ok = 1;
        ds.count = h[1];
        ds.bytes = size > 0 ? (unsigned)size : 0;
    }
    close(fd);
}

void dur_stat(char *buf, unsigned n) {
    char size[24];
    if (!ds.ok) {
        snprintf(buf, n, "0");
        return;
    }
    if (ds.bytes < 1024 * 1024)
        snprintf(size, sizeof size, "%u KB", (ds.bytes + 512) / 1024);
    else
        cc_size_text(size, sizeof size, ds.bytes);
    snprintf(buf, n, "%u \xc2\xb7 %s", ds.count, size);
}

/* The index of key in the table, or -1. */
static int dur_find(unsigned key) {
    unsigned lo = 0, hi = ln.n;
    while (lo < hi) {
        unsigned mid = lo + (hi - lo) / 2;
        if (ln.tab[mid].key < key)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo < ln.n && ln.tab[lo].key == key ? (int)lo : -1;
}

int dur_file(const char *path, unsigned size) {
    int at = path && *path ? dur_find(dur_key(path)) : -1;
    return at >= 0 && ln.tab[at].size == size ? (int)ln.tab[at].sec : -1;
}

int dur_has(const char *path) { return path && *path && dur_find(dur_key(path)) >= 0; }

int dur_song(void *rec, unsigned *size) {
    int start = I(rec, REC_CUE_START), end = I(rec, REC_CUE_END), v;
    const char *path = (const char *)P(rec, REC_PATH);
    long sz;
    if (end > start) return end - start; /* a CUE track with both ends: nothing to measure */
    if (!path || !*path) return 0;
    sz = cc_file_size(path);
    if (sz <= 0 || sz > 0x7fffffff) return 0; /* gone, empty, or a size that does not fit the entry */
    v = dur_file(path, (unsigned)sz);
    if (v < 0) {
        if (size) *size = (unsigned)sz;
        return -1;
    }
    if (start < 0) start = 0;
    return v > start ? v - start : 0;
}

static int dur_write(void) {
    unsigned h[3];
    h[0] = DUR_MAGIC, h[1] = ln.n,
    h[2] = dur_sum(
        ln.tab,
        ln.n); /* (m1_card_write: CARD_DIR made, DUR_FILE ".tmp", fsync, rename; -1 and nothing written while the card is out) */
    return m1_card_write(CARD_DIR, DUR_FILE, h, DUR_HDR, ln.tab, ln.n * (unsigned)sizeof *ln.tab);
}

/* Shell sort by key (stable enough: equal keys are one file measured twice, with one answer). */
static void dur_sort(dur_ent_t *v, unsigned n) {
    unsigned gap, i, j;
    for (gap = n / 2; gap; gap /= 2)
        for (i = gap; i < n; ++i) {
            dur_ent_t t = v[i];
            for (j = i; j >= gap && v[j - gap].key > t.key; j -= gap) v[j] = v[j - gap];
            v[j] = t;
        }
}

int dur_merge(const dur_ent_t *add, unsigned n) {
    dur_ent_t *a, *out;
    unsigned i = 0, j = 0, k = 0;
    if (!ln.users || !add || !n) return 0;
    a = calloc(1, (n * sizeof *a));
    out = calloc(1, ((ln.n + n + 1) * sizeof *out));
    if (!a || !out) {
        free(a);
        free(out);
        return -1;
    }
    memcpy(a, add, n * sizeof *a);
    dur_sort(a, n);
    while (i < ln.n || j < n) {
        dur_ent_t e;
        if (j >= n || (i < ln.n && ln.tab[i].key < a[j].key))
            e = ln.tab[i++];
        else {
            e = a[j];
            if (i < ln.n && ln.tab[i].key == e.key) ++i; /* the new measurement replaces the old entry */
            ++j;
        }
        if (k && out[k - 1].key == e.key)
            out[k - 1] = e; /* one file twice in add */
        else
            out[k++] = e;
    }
    free(a);
    free(ln.tab);
    free(ln.seen);
    ln.seen = (unsigned char *)0;
    ln.tab = out;
    ln.n = k;
    return dur_write();
}

void dur_pass_begin(void) {
    free(ln.seen);
    ln.seen = ln.n ? calloc((ln.n + 7) / 8, 1) : (unsigned char *)0;
    ln.named = 0;
}

void dur_pass_seen(const char *path) {
    int at;
    if (!path || !*path) return;
    ++ln.named;
    at = ln.seen ? dur_find(dur_key(path)) : -1;
    if (at >= 0) ln.seen[at >> 3] |= (unsigned char)(1 << (at & 7));
}

unsigned dur_pass_end(void) {
    unsigned i, k = 0, gone;
    if (!ln.seen || !ln.named) { /* an empty list proves nothing: a library that did not load must not wipe the table */
        free(ln.seen);
        ln.seen = (unsigned char *)0;
        return 0;
    }
    for (i = 0; i < ln.n; ++i)
        if (ln.seen[i >> 3] >> (i & 7) & 1) ln.tab[k++] = ln.tab[i];
    gone = ln.n - k;
    free(ln.seen);
    ln.seen = (unsigned char *)0;
    if (gone) {
        ln.n = k;
        dur_write();
    }
    return gone;
}

int dur_probe(const char *path) {
    unsigned n = 0;
    void *f, *p;
    int sec = 0;
    if (!path) return 0;
    while (path[n]) ++n;
    if (n >= 4 && !cc_nocase(path + n - 4, ".iso")) return 0; /* stock never reads a disc image's properties */
    f = taglib_file_new(path, 1);
    p = f ? taglib_file_audioproperties(f) : (void *)0;
    if (p)
        sec = ((int (*)(void *))(*(void ***)p)[3])(
            p); /* AudioProperties::length(), as libtag_c's taglib_audioproperties_length calls it: vtable +0xc */
    if (f) taglib_file_free(f);
    return sec > 0 && sec < 100 * 3600 ? sec : 0;
}

void dur_subst(char *out, unsigned size, const char *f, int n, const char *s1, const char *s2) {
    char num[12];
    unsigned o = 0, d = 0, v = (unsigned)(n < 0 ? 0 : n);
    int k = 0;
    do num[d++] = (char)('0' + v % 10);
    while ((v /= 10) != 0);
    while (*f && o + 1 < size) {
        if (f[0] == '%' && (f[1] == 'd' || f[1] == 's')) {
            if (f[1] == 'd') {
                while (d && o + 1 < size) out[o++] = num[--d];
            } else {
                const char *s = k++ ? s2 : s1;
                while (s && *s && o + 1 < size) out[o++] = *s++;
            }
            f += 2;
        } else
            out[o++] = *f++;
    }
    out[o] = 0;
}

static void dur_subst2(char *out, unsigned size, const char *f, int n1, int n2) {
    unsigned o = 0;
    int k = 0;
    while (*f && o + 1 < size) {
        if (f[0] == '%' && f[1] == 'd') {
            char num[12];
            int n = k++ ? n2 : n1;
            unsigned d = 0, v = (unsigned)(n < 0 ? 0 : n);
            do num[d++] = (char)('0' + v % 10);
            while ((v /= 10) != 0);
            while (d && o + 1 < size) out[o++] = num[--d];
            f += 2;
        } else
            out[o++] = *f++;
    }
    out[o] = 0;
}

void dur_text(char *out, unsigned size, unsigned sec) {
    unsigned m = (sec + 30) / 60, h;
    if (m < 1) m = 1;
    h = m / 60;
    m %= 60;
    if (!h) {
        m1_fmt(out, size, TR(m == 1 ? "%d minute" : "%d minutes"), (int)m);
        return;
    }
    if (!m) {
        m1_fmt(out, size, TR(h == 1 ? "%d hour" : "%d hours"), (int)h);
        return;
    }
    dur_subst2(out, size,
               TR(h == 1 ? (m == 1 ? "%d hour, %d minute" : "%d hour, %d minutes")
                         : (m == 1 ? "%d hours, %d minute" : "%d hours, %d minutes")),
               (int)h, (int)m);
}
