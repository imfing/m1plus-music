/* LibriVox on the card: the book folder, its manifest and the download job (patch/bkdl.h, docs/modules/audiobooks.md "LibriVox").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The names and the manifest come first (pure over the card), then the download: a thread of its own (beside a job of pcnet.c's slot and beside the episode queue's thread) that fetches the missing parts one
 * by one through pnw_download, the way an episode is downloaded. The thread writes the record the page reads on its own timer and touches no widget.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "podcasts.h"
#include "pcjson.h"
#include "pcnet.h"
#include "pcnetw.h"
#include "net.h"
#include "books.h"
#include "bknet.h"
#include "bkdl.h"

#define BD_PATH 400
#define BD_HEAD 1024 /* bytes of a manifest read to find its identifier */
#define BD_DNAME 11 /* struct dirent (32-bit, MIPS o32): d_name at 11 */
#define BD_RESULTS 16

/* ---------------------------------------------------------------------------
 * Small helpers
 */
/* v in decimal (at least width digits, zero padded) appended to out. */
static int bd_catnum(char *out, unsigned size, unsigned v, unsigned width) {
    char t[12];
    unsigned n = 0;
    do t[n++] = (char)('0' + v % 10), v /= 10;
    while (v && n < sizeof t - 1);
    while (n < width && n < sizeof t - 1) t[n++] = '0';
    t[n] = 0;
    for (v = 0; v < n / 2; ++v) {
        char c = t[v];
        t[v] = t[n - 1 - v], t[n - 1 - v] = c;
    }
    return m1_cat(out, size, t);
}

/* root/a[/b] into out; 0 when it does not fit. */
static int bd_join(char *out, unsigned size, const char *root, const char *a, const char *b) {
    out[0] = 0;
    return m1_cat(out, size, root) && m1_cat(out, size, "/") && m1_cat(out, size, a) &&
           (!b || (m1_cat(out, size, "/") && m1_cat(out, size, b)));
}

/* s (to its NUL) into out of size bytes, cut before a UTF-8 continuation byte. */
static void bd_copy(char *out, unsigned size, const char *s) {
    unsigned len = strlen(s);
    if (len >= size) {
        len = size - 1;
        while (len && ((unsigned char)s[len] & 0xc0) == 0x80) --len;
    }
    memcpy(out, s, len);
    out[len] = 0;
}

static int bd_exists(const char *path) { return access(path, F_OK) == 0; }

/* ---------------------------------------------------------------------------
 * Names
 */
unsigned bd_fat(const char *in, unsigned max, char *out) {
    const unsigned char *s = (const unsigned char *)in;
    unsigned n = 0, len, k;
    out[0] = 0;
    while (*s) {
        len = bn_seq(s);
        if (!len) {
            ++s; /* not UTF-8: dropped */
            continue;
        }
        if (len == 1) {
            unsigned c = *s;
            if (c < 0x20 || c == 0x7f || c == '\\' || c == '/' || c == ':' || c == '*' || c == '?' || c == '"' ||
                c == '<' || c == '>' || c == '|')
                c = ' ';
            ++s;
            if (c == ' ' && (!n || out[n - 1] == ' ')) continue; /* no leading space, no run of them */
            if (c == '.' && !n) continue; /* no leading dot (a dot file is not listed) */
            if (n + 1 > max) break;
            out[n++] = (char)c;
            continue;
        }
        if (n + len > max) break; /* the sequence does not fit: whole or not at all */
        for (k = 0; k < len; ++k) out[n++] = (char)*s++;
    }
    while (n && (out[n - 1] == ' ' || out[n - 1] == '.')) --n;
    out[n] = 0;
    return n;
}

/* A title that starts with the part's own number ("001 - Marseilles" for part 1): what follows the number and its separator, so the file is not numbered twice. The title itself when it starts with
 * another number, or when nothing would be left. */
static const char *bd_unnumbered(const char *title, unsigned num) {
    const char *s = title;
    unsigned v = 0, digits = 0;
    while (*s == ' ') ++s;
    while (*s >= '0' && *s <= '9' && digits < 6) v = v * 10 + (unsigned)(*s++ - '0'), ++digits;
    if (!digits || v != num || (*s >= '0' && *s <= '9')) return title;
    if (*s != ' ' && *s != '-' && *s != '.' && *s != ':' && *s != '_') return title; /* ("1st", "12th Night") */
    while (*s == ' ' || *s == '-' || *s == '.' || *s == ':' || *s == '_') ++s;
    return *s ? s : title;
}

/* The name of part i of count (0 based), into out (BK_FILE bytes): NNN <title>.mp3 within fm bytes. */
static void bd_part_file(unsigned i, unsigned count, const bn_part_t *p, unsigned fm, char *out) {
    char t[BK_FILE], stem[BK_FILE];
    unsigned width = count >= 100 ? 3 : count >= 10 ? 2 : 1, room, k, dot;
    out[0] = 0;
    bd_catnum(out, BK_FILE, i + 1, width);
    room = fm > width + 1 + 4 ? fm - width - 1 - 4 : 0;
    bd_fat(bd_unnumbered(p->title, i + 1), room < BK_FILE ? room : BK_FILE - 1, t);
    if (!t[0]) { /* no title: the archive name's stem */
        k = strlen(p->name), dot = k;
        while (dot > 0 && p->name[dot - 1] != '.') --dot;
        if (dot > 1) k = dot - 1;
        if (k >= sizeof stem) k = sizeof stem - 1;
        memcpy(stem, p->name, k), stem[k] = 0;
        bd_fat(stem, room < BK_FILE ? room : BK_FILE - 1, t);
    }
    if (!t[0] && room >= 4 + 6) {
        m1_cat(t, sizeof t, "Part ");
        bd_catnum(t, sizeof t, i + 1, 0);
    }
    if (t[0]) m1_cat(out, BK_FILE, " "), m1_cat(out, BK_FILE, t);
    m1_cat(out, BK_FILE, ".mp3");
}

/* ---------------------------------------------------------------------------
 * The manifest
 */
static int bd_field_ok(const char *s, int dot_ok) {
    unsigned n = 0;
    if (!s[0] || (!dot_ok && s[0] == '.')) return 0;
    if (s[0] == '.' && (!s[1] || (s[1] == '.' && !s[2]))) return 0;
    for (; s[n]; ++n)
        if ((unsigned char)s[n] < 0x20 || s[n] == 0x7f || s[n] == '/' || s[n] == '\\') return 0;
    return n < BK_FILE;
}

/* digits only, at most 2^32 - 1 */
static int bd_num(const char *s, unsigned *v) {
    unsigned n = 0, i;
    if (!s[0]) return 0;
    for (i = 0; s[i]; ++i) {
        unsigned d = (unsigned)(s[i] - '0');
        if (d > 9 || n > (0xffffffffu - d) / 10) return 0;
        n = n * 10 + d;
    }
    *v = n;
    return 1;
}

/* The text (n bytes, NUL after them; it is edited) of a manifest. id / title / author get the header; b (NULL: the header only, which stops at the first part line and ignores a last line without its LF)
 * gets the parts. 1 when well formed. */
static int bd_parse(char *text, unsigned n, char *id, char *title, char *author, bd_book_t *b) {
    char *s = text, *end = text + n;
    int line = 0, parts = 0;
    id[0] = title[0] = author[0] = 0;
    if (b) b->n = 0;
    while (s < end) {
        char *e = s, *le, *f[6];
        int tabs = 0;
        unsigned k, len;
        while (e < end && *e != '\n') ++e;
        if (e == end && !b) break; /* a line cut short by the read */
        le = e > s && e[-1] == '\r' ? e - 1 : e;
        *le = 0;
        if (e < end) *e = 0;
        if (!line++) {
            if (strcmp(s, BD_MAGIC)) return 0;
        } else if (*s) {
            f[0] = s, len = (unsigned)(le - s);
            for (k = 0; k < len; ++k)
                if (s[k] == '\t') {
                    if (tabs < 5)
                        f[++tabs] = s + k + 1;
                    else
                        tabs = 6;
                    s[k] = 0;
                }
            if (tabs) { /* a part */
                bd_part_t *p;
                unsigned secs, bytes;
                int j;
                if (!b) break;
                if (tabs != 4 || b->n >= BK_MAX_PARTS) return 0;
                if (!bd_field_ok(f[0], 0) || !bd_num(f[1], &secs) || !bd_num(f[2], &bytes) || !bd_field_ok(f[3], 1))
                    return 0;
                for (j = 0; j < b->n; ++j)
                    if (!strcmp(b->parts[j].file, f[0])) return 0;
                p = &b->parts[b->n++];
                bd_copy(p->file, sizeof p->file, f[0]);
                bd_copy(p->name, sizeof p->name, f[3]);
                bd_copy(p->title, sizeof p->title, f[4]);
                p->secs = secs, p->bytes = bytes;
                parts = 1;
            } else { /* key=value */
                char *v = s;
                while ((*v >= 'a' && *v <= 'z') || (*v >= 'A' && *v <= 'Z') || (*v >= '0' && *v <= '9') || *v == '_')
                    ++v;
                if (v == s || *v != '=' || parts) return 0;
                *v++ = 0;
                if (!strcmp(s, "i")) {
                    if (!bn_id_ok(v)) return 0;
                    bd_copy(id, BN_ID, v);
                } else if (!strcmp(s, "t"))
                    bd_copy(title, BK_TITLE, v);
                else if (!strcmp(s, "a"))
                    bd_copy(author, BN_AUTHOR, v);
            }
        }
        s = e + 1;
    }
    return line > 0 && id[0];
}

void bd_free(bd_book_t *b) { free(b); }

bd_book_t *bd_open(const char *dir) {
    char path[BD_PATH], *text;
    unsigned n = 0;
    bd_book_t *b;
    int ok;
    if (!bd_field_ok(dir, 0)) return (bd_book_t *)0;
    b = calloc(1, sizeof *b);
    if (!b) return b;
    if (!bk_root(b->root) || !bd_join(path, sizeof path, b->root, dir, BD_MANIFEST)) {
        free(b);
        return (bd_book_t *)0;
    }
    text = m1_read_file(path, BD_MAN_CAP, &n);
    ok = text && n < BD_MAN_CAP && bd_parse(text, n, b->id, b->title, b->author, b);
    free(text);
    if (!ok) {
        free(b);
        return (bd_book_t *)0;
    }
    bd_copy(b->dir, sizeof b->dir, dir);
    return b;
}

static int bd_part_path(const bd_book_t *b, int i, char *out, unsigned size) {
    char sub[BD_PATH];
    return bd_join(sub, sizeof sub, b->root, b->dir, (const char *)0) &&
           bd_join(out, size, sub, b->parts[i].file, (const char *)0);
}

int bd_present(const bd_book_t *b, int i) {
    char path[BD_PATH];
    return i >= 0 && i < b->n && bd_part_path(b, i, path, sizeof path) && bd_exists(path);
}

void bd_counts(const bd_book_t *b, unsigned *present, unsigned *missing, unsigned *bytes) {
    int i;
    *present = *missing = *bytes = 0;
    for (i = 0; i < b->n; ++i) {
        if (bd_present(b, i)) {
            ++*present;
            continue;
        }
        ++*missing;
        *bytes = b->parts[i].bytes > 0xffffffffu - *bytes ? 0xffffffffu : *bytes + b->parts[i].bytes;
    }
}

int bd_find(const char *id, char *dir, unsigned size) {
    char root[BK_FILE + 20], path[BD_PATH], name[BK_FILE], hid[BN_ID], ht[BK_TITLE], ha[BN_AUTHOR];
    void *d;
    char *ent;
    int seen = 0, found = 0;
    if (!bk_root(root) || !(d = opendir(root))) return 0;
    while (!found && seen < BK_MAX_BOOKS && (ent = readdir(d)) != (char *)0) {
        char *text;
        unsigned n = 0;
        if (!bd_field_ok(ent + BD_DNAME, 0)) continue;
        ++seen;
        memcpy(name, ent + BD_DNAME, strlen(ent + BD_DNAME) + 1);
        if (!bd_join(path, sizeof path, root, name, BD_MANIFEST)) continue;
        text = m1_read_file(path, BD_HEAD, &n);
        if (text && bd_parse(text, n, hid, ht, ha, (bd_book_t *)0) && !strcmp(hid, id) && strlen(name) < size)
            memcpy(dir, name, strlen(name) + 1), found = 1;
        free(text);
    }
    closedir(d);
    return found;
}

/* ---------------------------------------------------------------------------
 * The folder
 */
static int bd_put(char *buf, unsigned cap, const char *s) { return m1_cat(buf, cap, s); }

/* A manifest field: control bytes (a tab, a line feed) become spaces. */
static int bd_putf(char *buf, unsigned cap, const char *s) {
    unsigned o = strlen(buf), k;
    for (k = 0; s[k]; ++k) {
        if (o + 1 >= cap) return 0;
        buf[o++] = (unsigned char)s[k] < 0x20 || s[k] == 0x7f ? ' ' : s[k];
    }
    buf[o] = 0;
    return 1;
}

static int bd_copy_cover(const char *dirpath) {
    char src[200], dst[BD_PATH];
    char *data;
    unsigned n = 0;
    int ok;
    unsigned len;
    if (!bn_preview_cover(src, sizeof src)) return 0;
    len = strlen(src);
    if (!bd_join(dst, sizeof dst, dirpath, len > 3 && src[len - 3] == 'p' ? "cover.png" : "cover.jpg", (const char *)0))
        return 0;
    data = m1_read_file(src, PN_THUMB_CAP, &n);
    ok = data && m1_save(dst, 0644, data, n);
    free(data);
    return ok;
}

int bd_create(const char *id, const char *title, const char *author, char *dir, unsigned size) {
    char root[BK_FILE + 20], base[BD_BASE_MAX + 1], name[BK_FILE], path[BD_PATH], mpath[BD_PATH];
    char *man;
    unsigned fm, n, k, i;
    int g, ok;
    n = (unsigned)bn_preview_count();
    if (!bn_id_ok(id) || strcmp(id, bn_preview_id()) || !n) return PN_NOBOOK;
    if (!m1_card_mounted()) return PN_STORAGE;
    if (!bk_root(root)) {
        mkdir(root, 0755);
        if (!bd_exists(root)) return PN_STORAGE;
    }
    if (bd_find(id, name, sizeof name)) { /* a folder of this book is on the card: it is the book */
        if (strlen(name) >= size) return PN_STORAGE;
        memcpy(dir, name, strlen(name) + 1);
        return PN_OK;
    }
    if (!bd_fat(title, BD_BASE_MAX, base)) bd_copy(base, sizeof base, BD_DEFAULT_TITLE);
    for (k = 1; k <= 99; ++k) {
        name[0] = 0;
        m1_cat(name, sizeof name, base);
        if (k > 1) m1_cat(name, sizeof name, " ("), bd_catnum(name, sizeof name, k, 0), m1_cat(name, sizeof name, ")");
        if (!bd_join(path, sizeof path, root, name, (const char *)0)) return PN_STORAGE;
        if (!bd_exists(path)) break;
    }
    if (k > 99 || strlen(name) >= size) return PN_STORAGE;
    if (mkdir(path, 0755)) return PN_STORAGE;
    man = calloc(BD_MAN_CAP, 1);
    if (!man) {
        rmdir(path);
        return PN_MEM;
    }
    if (strlen(path) + 40 > PN_DL_PATH_MAX) {
        free(man);
        rmdir(path);
        return PN_STORAGE;
    }
    fm = PN_DL_PATH_MAX - (unsigned)sizeof(".part") - (unsigned)strlen(path) - 1;
    if (fm > BK_FILE - 1) fm = BK_FILE - 1;
    ok = bd_put(man, BD_MAN_CAP, BD_MAGIC "\ni=") && bd_put(man, BD_MAN_CAP, id) && bd_put(man, BD_MAN_CAP, "\nt=") &&
         bd_putf(man, BD_MAN_CAP, title) && bd_put(man, BD_MAN_CAP, "\na=") && bd_putf(man, BD_MAN_CAP, author) &&
         bd_put(man, BD_MAN_CAP, "\n");
    for (i = 0; ok && i < n; ++i) {
        const bn_part_t *p = bn_part((int)i);
        char file[BK_FILE];
        bd_part_file(i, n, p, fm, file);
        ok = bd_put(man, BD_MAN_CAP, file) && bd_put(man, BD_MAN_CAP, "\t") && bd_catnum(man, BD_MAN_CAP, p->secs, 0) &&
             bd_put(man, BD_MAN_CAP, "\t") && bd_catnum(man, BD_MAN_CAP, p->bytes, 0) &&
             bd_put(man, BD_MAN_CAP, "\t") && bd_putf(man, BD_MAN_CAP, p->name) && bd_put(man, BD_MAN_CAP, "\t") &&
             bd_putf(man, BD_MAN_CAP, p->title) && bd_put(man, BD_MAN_CAP, "\n");
    }
    g = PN_STORAGE;
    if (ok && bd_join(mpath, sizeof mpath, path, BD_MANIFEST, (const char *)0)) {
        bd_copy_cover(path); /* (the picture may be missing: the placeholder stays) */
        if (m1_save(mpath, 0644, man, (unsigned)strlen(man))) g = PN_OK;
    }
    free(man);
    if (g != PN_OK) { /* nothing is left: no manifest, no folder */
        char cover[BD_PATH];
        if (bd_join(cover, sizeof cover, path, "cover.jpg", (const char *)0)) unlink(cover);
        if (bd_join(cover, sizeof cover, path, "cover.png", (const char *)0)) unlink(cover);
        rmdir(path);
        return g;
    }
    memcpy(dir, name, strlen(name) + 1);
    return PN_OK;
}

/* ---------------------------------------------------------------------------
 * The job: one thread, one transfer at a time, and a queue of books waiting for it.
 *
 * bd is the book that runs (what the page reads); bq is the queue and its mutex. Every move of the queue and of the running book's identity (a book enters, leaves, is claimed, ends, the thread ends) is one hold of
 * bq.mutex, the UI thread's (bd_start, bd_pause, bd_state) and the thread's, as the episode queue's pn_dmutex is held: a book is seen either waiting (it leaves the queue and is never started) or running (its stop
 * flag is set), never in between, and the thread decides that nothing waits and ends in the same hold that bd_start looks at it in, so a book queued while the thread ends starts a new one. No file is touched under
 * the mutex; the worker's record (the book it fetches) is its own and never read by the page.
 */
#define BD_QMAX 16 /* books waiting behind the running one; a seventeenth is PN_QFULL */

static struct {
    volatile int run;
    volatile unsigned key, part, parts;
    volatile unsigned res_key[BD_RESULTS];
    volatile int res_kind[BD_RESULTS], res_code[BD_RESULTS];
    volatile int next;
    volatile unsigned gen; /* bd_gen: never reset, so a page that compares it misses no job */
    pnw_dl_t dl;
    bd_book_t *volatile book;
} bd __attribute__((section(".scratch")));

static struct {
    unsigned mutex[8];
    int n; /* books waiting, in the order asked: key[0] is next */
    unsigned key[BD_QMAX];
    char dir[BD_QMAX][BK_FILE];
} bq __attribute__((section(".scratch"), aligned(8)));

static void bd_lock(void) { pthread_mutex_lock(bq.mutex); }
static void bd_unlock(void) { pthread_mutex_unlock(bq.mutex); }

static unsigned bd_key(const char *dir) {
    char key[sizeof BK_KEY_PREFIX + BK_FILE];
    memcpy(key, BK_KEY_PREFIX, sizeof BK_KEY_PREFIX);
    m1_cat(key, sizeof key, dir);
    return pc_hash(key);
}

/* With bq.mutex held. */
static void bd_set_result(unsigned key, int kind, int code) {
    int i, at = -1;
    for (i = 0; i < BD_RESULTS; ++i)
        if (bd.res_key[i] == key) at = i;
    if (at < 0) {
        for (i = 0; i < BD_RESULTS; ++i)
            if (!bd.res_key[i]) at = i;
        if (at < 0) at = bd.next, bd.next = (bd.next + 1) % BD_RESULTS;
    }
    bd.res_kind[at] = kind, bd.res_code[at] = code;
    __sync_synchronize();
    bd.res_key[at] = key;
}

int bd_result(unsigned key, int *code) {
    int i;
    for (i = 0; i < BD_RESULTS; ++i)
        if (key && bd.res_key[i] == key) {
            *code = bd.res_code[i];
            return bd.res_kind[i];
        }
    *code = 0;
    return BD_R_NONE;
}

/* With bq.mutex held. */
static void bd_forget(unsigned key) {
    int i;
    for (i = 0; i < BD_RESULTS; ++i)
        if (bd.res_key[i] == key) bd.res_key[i] = 0;
}

unsigned bd_active(void) { return bd.run ? bd.key : 0; }
unsigned bd_gen(void) { return bd.gen + bd.dl.gen; }

int bd_progress(unsigned *part, unsigned *parts, unsigned *got, unsigned *total, int *wait) {
    unsigned g, t;
    if (!bd.run || !bd.key) return 0;
    *part = bd.part, *parts = bd.parts;
    g = bd.dl.got, t = bd.dl.total;
    *got = g, *total = t < g ? 0 : t;
    *wait = bd.dl.wait;
    return 1;
}

/* With bq.mutex held: the place of key in the queue, -1 for none. */
static int bd_at(unsigned key) {
    int i;
    for (i = 0; i < bq.n; ++i)
        if (bq.key[i] == key) return i;
    return -1;
}

/* With bq.mutex held: entry i leaves the queue. */
static void bd_remove(int i) {
    for (; i + 1 < bq.n; ++i) {
        bq.key[i] = bq.key[i + 1];
        memcpy(bq.dir[i], bq.dir[i + 1], BK_FILE);
    }
    --bq.n;
}

int bd_state(unsigned key) {
    int s;
    if (!key) return BD_S_NONE;
    bd_lock();
    s = bd.run && bd.key == key ? BD_S_RUN : bd_at(key) >= 0 ? BD_S_WAIT : BD_S_NONE;
    bd_unlock();
    return s;
}

void bd_pause(unsigned key) {
    int i;
    if (!key) return;
    bd_lock();
    if (bd.run && bd.key == key) bd.dl.stop = 1; /* (the transfer ends at once; the thread goes on to the next book) */
    while ((i = bd_at(key)) >= 0) { /* a book waiting leaves the queue and shows as paused */
        bd_remove(i);
        bd_set_result(key, BD_R_PAUSED, 0);
        ++bd.gen;
    }
    bd_unlock();
}

/* A failure that every book would meet the same way: the link, the clock, the certificates, the card, memory. The queue is not worth going on with. A part whose own path is too long is not one. */
static int bd_global(int code) {
    return code == PN_NOWIFI || code == PN_NOCLOCK || code == PN_NOCERT || code == PN_CERT || code == PN_NET ||
           code == PN_STORAGE || code == PN_CARDFULL || code == PN_MEM;
}

/* The missing parts of b in manifest order, to the end or to the first that does not come. PN_OK, PN_CANCELLED (a pause), else the failure; *local 1 when the failure is this book's alone. */
static int bd_fetch(bd_book_t *b, int *local) {
    int i, code = PN_OK;
    for (i = 0; i < b->n && code == PN_OK; ++i) {
        char path[BD_PATH], url[BN_URL];
        if (bd.dl.stop) {
            code = PN_CANCELLED;
            break;
        }
        if (!bd_part_path(b, i, path, sizeof path) || strlen(path) + sizeof(".part") > PN_DL_PATH_MAX) {
            code = PN_STORAGE, *local = 1;
            break;
        }
        if (bd_exists(path)) continue;
        bd.part = (unsigned)i;
        url[0] = 0;
        if (!m1_cat(url, sizeof url, BN_HOST "/download/") || !m1_cat(url, sizeof url, b->id) ||
            !m1_cat(url, sizeof url, "/")) {
            code = PN_STORAGE, *local = 1;
            break;
        }
        {
            unsigned used = m1_urlenc(url, sizeof url, (unsigned)strlen(url), b->parts[i].name);
            if (!used) {
                code = PN_STORAGE, *local = 1;
                break;
            }
            url[used] = 0;
        }
        bd.dl.got = 0, bd.dl.total = b->parts[i].bytes;
        __sync_synchronize();
        ++bd.dl.gen;
        code = pnw_download(&bd.dl, url, path, b->parts[i].bytes);
    }
    return code;
}

/* With bq.mutex held: the running book is b, key (a new record of the progress: the sum of the generation never goes back). */
static void bd_claim(bd_book_t *b, unsigned key) {
    bd_forget(key);
    bd.gen += bd.dl.gen + 1;
    memset((void *)&bd.dl, 0, sizeof bd.dl);
    bd.book = b, bd.key = key, bd.part = 0, bd.parts = (unsigned)b->n;
    ++bd.dl.gen;
}

/* The next waiting book, claimed (its record opened here, off the mutex, and taken only if it is still the head), or NULL with the thread's end made in the same hold that saw the queue empty. */
static bd_book_t *bd_next(void) {
    for (;;) {
        char dir[BK_FILE];
        unsigned key;
        bd_book_t *b;
        bd_lock();
        if (!bq.n) {
            bd.run = 0, bd.key = 0;
            ++bd.dl.gen;
            bd_unlock();
            return (bd_book_t *)0;
        }
        key = bq.key[0];
        memcpy(dir, bq.dir[0], BK_FILE);
        bd_unlock();
        b = bd_open(dir);
        bd_lock();
        if (bq.n &&
            bq.key[0] == key) { /* (it may have been paused, or the queue emptied, while the manifest was read) */
            bd_remove(0);
            if (b) {
                bd_claim(b, key);
                bd_unlock();
                return b;
            }
            bd_set_result(key, BD_R_FAILED, PN_NOBOOK);
            ++bd.gen;
        }
        bd_unlock();
        free(b);
    }
}

static void *bd_main(void *arg) {
    bd_book_t *b = bd.book;
    (void)arg;
    while (b) {
        int local = 0, code = bd_fetch(b, &local);
        free(b);
        bd_lock();
        bd.book = (bd_book_t *)0;
        if (code == PN_OK)
            bd_set_result(bd.key, BD_R_DONE, 0);
        else if (code == PN_CANCELLED)
            bd_set_result(bd.key, BD_R_PAUSED, 0);
        else
            bd_set_result(bd.key, BD_R_FAILED, code);
        bd.key = 0; /* (its files are let go of: a Delete Book that waits for the book goes on) */
        if (code != PN_OK && code != PN_CANCELLED && !local && bd_global(code)) {
            while (bq.n) { /* every book would fail as this one did: the rest leave the queue as paused */
                bd_set_result(bq.key[bq.n - 1], BD_R_PAUSED, 0);
                --bq.n;
            }
        }
        ++bd.dl.gen;
        bd_unlock();
        b = bd_next();
    }
    return (void *)0;
}

int bd_start(const char *dir) {
    bd_book_t *b;
    unsigned present, missing, bytes, key;
    unsigned long th = 0;
    int g;
    b = bd_open(dir);
    if (!b) return PN_NOBOOK;
    key = bd_key(b->dir);
    bd_counts(b, &present, &missing, &bytes);
    if (!missing) { /* nothing to fetch */
        bd_lock();
        bd_set_result(key, BD_R_DONE, 0);
        ++bd.gen;
        bd_unlock();
        free(b);
        return PN_OK;
    }
    g = pn_guard(); /* (asked before the mutex is taken; it counts only for a book that is not in the queue already) */
    bd_lock();
    if (bd.run && bd.key == key &&
        !bd.dl.stop) { /* it runs already (one that is being paused is asked again behind the others) */
        bd_unlock();
        free(b);
        return PN_OK;
    }
    if (bd_at(key) >= 0) { /* it waits already */
        bd_unlock();
        free(b);
        return PN_OK;
    }
    if (g) {
        bd_unlock();
        free(b);
        return g;
    }
    if (bd.run) {
        if (bq.n >= BD_QMAX) {
            bd_unlock();
            free(b);
            return PN_QFULL;
        }
        bd_forget(key);
        bq.key[bq.n] = key;
        memcpy(bq.dir[bq.n], b->dir, BK_FILE);
        ++bq.n;
        ++bd.gen;
        bd_unlock();
        free(b);
        return PN_OK;
    }
    bd_claim(b, key);
    bd.run = 1;
    net_init();
    if (pthread_create(&th, (const void *)0, bd_main, (void *)0)) {
        bd.run = 0, bd.book = (bd_book_t *)0, bd.key = 0;
        ++bd.dl.gen;
        bd_unlock();
        free(b);
        return PN_MEM;
    }
    pthread_detach(th);
    bd_unlock();
    return PN_OK;
}
