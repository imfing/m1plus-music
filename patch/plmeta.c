/* The playlists' own times (patch/plmeta.h, docs/modules/playlists.md "Order").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The file PLAYLISTS_META_FILE (device data, written with home_write_atomic), strictly validated when read:
 *     M1PLMETA 1\n
 *     <id> <added> <updated> <played> <name>\n      (decimal; seconds, 0 = none; one line per playlist; the name to the end of the line)
 * Anything else (a bad magic, a field out of shape, a name with a control byte or over PLM_NAME - 1 bytes, an id twice, more than PLM_MAX lines, a file that stops inside a line) makes the file
 * unusable: nothing is shown from it and nothing is written over it (plm.good), so a file a later version wrote, or one a failing flash returned wrongly, is left as it is. A file that is not
 * there, or is empty, holds nothing to lose.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "plmeta.h"

#define PLM_MAGIC "M1PLMETA 1\n"
#define PLM_MAGIC_LEN 11
#define PLM_MAX \
    128 /* entries: one per playlist id that was ever stamped (a re-used id replaces its entry), at most PL_MAX playlists exist */
#define PLM_NAME 64 /* the name as keyed: at most 63 bytes (the keyboard's limit) */
#define PLM_LINE 107 /* id (9) + three times (10 each) + the spaces + the name (63) + the newline, at most */
#define PLM_FILE_MAX (PLM_MAGIC_LEN + PLM_MAX * PLM_LINE)
#define PLM_TIME_MAX 0x7fffffffu /* time_t is 32 bits signed on the device */
#define PLM_ID_MAX 999999999
#define PLM_ENOENT 2 /* errno values (the same numbers on MIPS o32): the file, or a folder above it, is not there */
#define PLM_ENOTDIR 20

typedef struct {
    int id;
    unsigned t[4]; /* [PLM_ADDED], [PLM_PLAYED], [PLM_UPDATED]; [0] unused */
    char name[PLM_NAME];
} plm_ent_t;

static struct {
    plm_ent_t ent[PLM_MAX];
    unsigned n;
    int good; /* the last load read the file (or found none): a save writes nothing else */
    char buf[PLM_FILE_MAX + 1];
} plm __attribute__((section(".scratch")));

/* The file's three time columns (added, updated, played) as the rows of plm_get. */
static const unsigned char plm_col[3] = {PLM_ADDED, PLM_UPDATED, PLM_PLAYED};

static int plm_bad(unsigned char c) { return c < 0x20 || c == 0x7f; }

/* The name as keyed: control bytes as spaces, at most PLM_NAME - 1 bytes, cut before a UTF-8 continuation byte that would be split. 0 for an empty name. */
static int plm_copy(char *out, const char *s) {
    unsigned n = 0;
    if (!s) return 0;
    while (s[n]) ++n;
    if (n >= PLM_NAME) {
        n = PLM_NAME - 1;
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    }
    for (unsigned i = 0; i < n; ++i) out[i] = plm_bad((unsigned char)s[i]) ? ' ' : s[i];
    out[n] = 0;
    return n != 0;
}

static int plm_same(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* A canonical decimal (no leading zero but "0" itself, 1 to 10 digits, at most max) at *pp up to `end`: its value, *pp after it; -1 when it is not one. */
static long plm_num(const char **pp, const char *stop, char end, unsigned max) {
    const char *p = *pp;
    unsigned long long v = 0;
    unsigned d = 0;
    while (p < stop && *p >= '0' && *p <= '9' && d < 10) v = v * 10 + (unsigned)(*p++ - '0'), ++d;
    if (!d || p >= stop || *p != end || (d > 1 && **pp == '0') || v > max) return -1;
    *pp = p + 1;
    return (long)v;
}

static int plm_line(const char **pp, const char *stop, plm_ent_t *e) {
    const char *p = *pp, *q;
    long v;
    unsigned k, n = 0;
    v = plm_num(&p, stop, ' ', PLM_ID_MAX);
    if (v < 0) return 0;
    e->id = (int)v;
    for (k = 1; k < 4; ++k) {
        v = plm_num(&p, stop, ' ', PLM_TIME_MAX);
        if (v < 0) return 0;
        e->t[plm_col[k - 1]] = (unsigned)v;
    }
    for (q = p; q < stop && *q != '\n'; ++q, ++n)
        if (plm_bad((unsigned char)*q) || n + 1 >= PLM_NAME) return 0;
    if (q >= stop || !n) return 0; /* the file stops inside the line, or no name */
    for (k = 0; k < n; ++k) e->name[k] = p[k];
    e->name[n] = 0;
    *pp = q + 1;
    return 1;
}

static int plm_absent(void) {
    int e = *__errno_location();
    return e == PLM_ENOENT || e == PLM_ENOTDIR;
}

/* PLAYLISTS_META_FILE into plm.ent. 0: the table is in plm (no file, or an empty one, is no entries). -1: the file is there but unreadable or not ours: plm.n is 0 and plm.good 0. */
static int plm_load(void) {
    const char *p = plm.buf, *stop;
    int fd, n = 0, r = 1, ok = 1;
    unsigned i, j;
    plm.good = 0;
    plm.n = 0;
    fd = open(PLAYLISTS_META_FILE, O_RDONLY, 0);
    if (fd < 0) {
        if (!plm_absent()) return -1; /* an error is not "no entries" */
        plm.good = 1;
        return 0;
    }
    while (n < (int)sizeof plm.buf && (r = read(fd, plm.buf + n, sizeof plm.buf - (unsigned)n)) > 0) n += r;
    close(fd);
    if (r < 0) return -1;
    if (!n) {
        plm.good = 1;
        return 0;
    }
    if (n < PLM_MAGIC_LEN || n > PLM_FILE_MAX) return -1;
    stop = plm.buf + n;
    for (i = 0; i < PLM_MAGIC_LEN; ++i)
        if (plm.buf[i] != PLM_MAGIC[i]) return -1;
    p += PLM_MAGIC_LEN;
    while (ok && p < stop) {
        plm_ent_t *e = &plm.ent[plm.n];
        if (plm.n >= PLM_MAX || !plm_line(&p, stop, e)) {
            ok = 0;
            break;
        }
        for (j = 0; j < plm.n; ++j)
            if (plm.ent[j].id == e->id) ok = 0;
        if (ok) ++plm.n;
    }
    if (!ok) {
        plm.n = 0;
        return -1;
    }
    plm.good = 1;
    return 0;
}

static void plm_putdec(char **o, unsigned v) {
    char d[11];
    unsigned n = 0;
    do d[n++] = (char)('0' + v % 10), v /= 10;
    while (v);
    while (n) *(*o)++ = d[--n];
}

/* The table as the file holds it; 0 when written. -1 and nothing written while the last load did not read the file. */
static int plm_save(void) {
    char *o = plm.buf;
    unsigned i, k;
    if (!plm.good) return -1;
    for (i = 0; i < PLM_MAGIC_LEN; ++i) *o++ = PLM_MAGIC[i];
    for (
        i = 0; i < plm.n;
        ++i) { /* (the table was checked on the way in: every line is at most PLM_LINE bytes, there are at most PLM_MAX of them) */
        plm_putdec(&o, (unsigned)plm.ent[i].id);
        for (k = 1; k < 4; ++k) {
            *o++ = ' ';
            plm_putdec(&o, plm.ent[i].t[plm_col[k - 1]]);
        }
        *o++ = ' ';
        for (k = 0; plm.ent[i].name[k]; ++k) *o++ = plm.ent[i].name[k];
        *o++ = '\n';
    }
    *o = 0;
    return home_write_atomic(PLAYLISTS_META_FILE, plm.buf);
}

/* The stamp for the next change: the clock, or one past the largest stamp held when the clock is not past it (an unsynced clock, several changes in one second). 0 when there is no room above. */
static unsigned plm_stamp(void) {
    unsigned top = 0, i, k, now = (unsigned)time((long *)0);
    for (i = 0; i < plm.n; ++i)
        for (k = 1; k < 4; ++k)
            if (plm.ent[i].t[k] > top) top = plm.ent[i].t[k];
    if (top >= PLM_TIME_MAX) return 0;
    if (now > PLM_TIME_MAX || now <= top) now = top + 1;
    return now;
}

static int plm_find(int id) {
    unsigned i;
    for (i = 0; i < plm.n; ++i)
        if (plm.ent[i].id == id) return (int)i;
    return -1;
}

/* The entry of the playlist (id, nm): a stale one (the id's entry has another name: the playlist it was of is gone) is emptied and renamed; none is appended. -1 when the table is full. */
static int plm_slot(int id, const char *nm) {
    int at = plm_find(id);
    unsigned k;
    if (at < 0) {
        if (plm.n >= PLM_MAX) return -1;
        at = (int)plm.n++;
        plm.ent[at].id = id;
        plm.ent[at].name[0] = 0;
    }
    if (!plm_same(plm.ent[at].name, nm)) {
        for (k = 0; (plm.ent[at].name[k] = nm[k]) != 0; ++k) {
        }
        plm.ent[at].t[1] = plm.ent[at].t[2] = plm.ent[at].t[3] = 0;
    }
    return at;
}

/* Entry `at` out of the table (the ones after it move up). */
static void plm_drop(unsigned at) {
    unsigned i, k;
    for (i = at; i + 1 < plm.n; ++i) { /* (field by field: a struct assignment would call memcpy) */
        plm.ent[i].id = plm.ent[i + 1].id;
        for (k = 1; k < 4; ++k) plm.ent[i].t[k] = plm.ent[i + 1].t[k];
        for (k = 0; (plm.ent[i].name[k] = plm.ent[i + 1].name[k]) != 0; ++k) {
        }
    }
    --plm.n;
}

/* n changes in one write: row 0 = new playlists (all three times set), else the one time of that row; the other times stay. Each playlist gets its own stamp (strictly increasing). */
static int plm_set_many(unsigned n, const int *id, const char *const *name, int row) {
    char nm[PLM_NAME];
    unsigned i, t;
    int at;
    if (!n) return 0;
    if (plm_load() != 0) return -1;
    for (i = 0; i < n; ++i) {
        if (id[i] < 0 || id[i] > PLM_ID_MAX || !plm_copy(nm, name[i])) return -1;
        t = plm_stamp();
        at = t ? plm_slot(id[i], nm) : -1;
        if (at < 0) return -1;
        if (!row) {
            plm.ent[at].t[PLM_ADDED] = plm.ent[at].t[PLM_UPDATED] = t;
            plm.ent[at].t[PLM_PLAYED] = 0;
        } else
            plm.ent[at].t[row] = t;
    }
    return plm_save();
}

static int plm_set(int id, const char *name, int row) { return plm_set_many(1, &id, &name, row); }

int plm_added(int id, const char *name) { return plm_set(id, name, 0); }
int plm_updated(int id, const char *name) { return plm_set(id, name, PLM_UPDATED); }
int plm_played(int id, const char *name) { return plm_set(id, name, PLM_PLAYED); }

int plm_imported(unsigned n, const int *id, const char *const *name, const int *was) {
    char nm[PLM_NAME];
    unsigned i, t, done = 0;
    int at;
    if (!n) return 0;
    if (plm_load() != 0) return -1;
    for (
        i = 0; i < n;
        ++i) /* first every replaced playlist's entry under a key no playlist has (-1 - i): the new ids may be one another's old ones */
        if (was[i] >= 0 && plm_copy(nm, name[i]) && (at = plm_find(was[i])) >= 0 && plm_same(plm.ent[at].name, nm))
            plm.ent[at].id = -1 - (int)i;
    for (i = 0; i < n; ++i) {
        if (id[i] < 0 || id[i] > PLM_ID_MAX || !plm_copy(nm, name[i]))
            continue; /* (a name too long to key: that playlist has no times) */
        t = plm_stamp();
        if (!t) return -1;
        if (was[i] >= 0 && (at = plm_find(-1 - (int)i)) >=
                               0) { /* replaced, with times: they go to its id now (a stale entry there goes) */
            int old = plm_find(id[i]);
            if (old >= 0) {
                plm_drop((unsigned)old);
                if (old < at) --at;
            }
            plm.ent[at].id = id[i];
        } else if ((at = plm_slot(id[i], nm)) < 0)
            return -1;
        else if (was[i] < 0)
            plm.ent[at].t[PLM_ADDED] = t, plm.ent[at].t[PLM_PLAYED] = 0;
        plm.ent[at].t[PLM_UPDATED] = t;
        ++done;
    }
    for (i = 0; i < plm.n; ++i) /* a replaced playlist whose new id is out of range: its entry goes */
        if (plm.ent[i].id < 0) plm_drop(i--);
    return done ? plm_save() : 0;
}

int plm_rename(int id, const char *old, const char *name) {
    char o[PLM_NAME], nm[PLM_NAME];
    unsigned t, k;
    int at;
    if (id < 0 || id > PLM_ID_MAX || !plm_copy(o, old) || !plm_copy(nm, name)) return -1;
    if (plm_load() != 0) return -1;
    t = plm_stamp();
    at = plm_find(id);
    if (!t) return -1;
    if (at >= 0 &&
        plm_same(plm.ent[at].name, o)) /* the entry of this playlist: it keeps its times under the new name */
        for (k = 0; (plm.ent[at].name[k] = nm[k]) != 0; ++k) {
        }
    else
        at = plm_slot(id, nm); /* no entry: a playlist from before the file, or a stale one */
    if (at < 0) return -1;
    plm.ent[at].t[PLM_UPDATED] = t;
    return plm_save();
}

int plm_forget_many(unsigned n, const int *id, const char *const *name) {
    char nm[PLM_NAME];
    unsigned j, gone = 0;
    int at;
    if (!n) return 0;
    if (plm_load() != 0) return -1;
    for (j = 0; j < n; ++j) {
        if (id[j] < 0 || id[j] > PLM_ID_MAX || !plm_copy(nm, name[j])) return -1;
        at = plm_find(id[j]);
        if (at < 0 || !plm_same(plm.ent[at].name, nm))
            continue; /* nothing of this playlist is kept (a stale entry of the id is not its) */
        plm_drop((unsigned)at);
        ++gone;
    }
    return gone ? plm_save() : 0;
}

int plm_read(void) { return plm_load(); }

unsigned plm_get(int id, const char *name, int row) {
    char nm[PLM_NAME];
    int at;
    if (row < 1 || row > 3 || !plm_copy(nm, name)) return 0;
    at = plm_find(id);
    return at >= 0 && plm_same(plm.ent[at].name, nm) ? plm.ent[at].t[row] : 0;
}
