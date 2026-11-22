/* LibriVox on the Internet Archive: the catalog (patch/bknet.h, docs/modules/audiobooks.md "LibriVox").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The pure parts come first: the query, the docs parser over pcjson.c's flat-record reader, and the files scanner, which reads the answer from a file chunk by chunk and keeps only the object it is in. The jobs follow
 * the podcast search and charts (patch/pcnet.c): the UI thread starts a worker in pcnet.c's one slot, the worker writes the record the page reads on its own timer and touches no widget.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "podcasts.h"
#include "pcjson.h"
#include "pcnet.h"
#include "pcnetw.h"
#include "books.h"
#include "bknet.h"

#define BN_CHUNK 4096 /* bytes read from the answer file at a time */
#define BN_DEPTH 32 /* nesting the scanner follows; a deeper answer is malformed */
#define BN_KEY 8 /* bytes of a depth-1 string kept to tell "result" */

/* ---------------------------------------------------------------------------
 * The query
 */
static int bn_special(unsigned c) {
    return c < 0x20 || c == 0x7f || c == ' ' || c == '+' || c == '-' || c == '&' || c == '|' || c == '!' || c == '(' ||
           c == ')' || c == '{' || c == '}' || c == '[' || c == ']' || c == '^' || c == '"' || c == '~' || c == '*' ||
           c == '?' || c == ':' || c == '\\' || c == '/';
}

/* The length of the well formed UTF-8 sequence at s (0: none: a stray continuation byte, a lead byte without its continuations, a byte that is no lead). */
unsigned bn_seq(const unsigned char *s) {
    unsigned need = s[0] >= 0xf0 ? 3 : s[0] >= 0xe0 ? 2 : s[0] >= 0xc2 ? 1 : 0, i;
    if (s[0] < 0x80) return 1;
    if (!need || s[0] > 0xf4) return 0;
    for (i = 1; i <= need; ++i)
        if ((s[i] & 0xc0) != 0x80) return 0;
    return need + 1;
}

int bn_clean_term(const char *term, char *out, unsigned size) {
    const unsigned char *s = (const unsigned char *)term;
    unsigned n = 0, w, k;
    int gap = 0;
    if (!size) return 0;
    out[0] = 0;
    if (!term) return 0;
    while (*s) {
        unsigned len = bn_seq(s);
        if (!len) {
            ++s; /* not UTF-8: dropped */
            continue;
        }
        if (len == 1 && bn_special(*s)) {
            gap = n > 0;
            ++s;
            continue;
        }
        if (n + (gap ? 1u : 0u) + len + 1 > size) break; /* the sequence does not fit: whole or not at all */
        if (gap) out[n++] = ' ', gap = 0;
        for (k = 0; k < len; ++k) out[n++] = (char)*s++;
    }
    out[n] = 0;
    for (w = 0; w < n;) { /* AND, OR and NOT are operators in capitals only */
        unsigned e = w;
        while (e < n && out[e] != ' ') ++e;
        if ((e - w == 3 && out[w] == 'A' && out[w + 1] == 'N' && out[w + 2] == 'D') ||
            (e - w == 2 && out[w] == 'O' && out[w + 1] == 'R') ||
            (e - w == 3 && out[w] == 'N' && out[w + 1] == 'O' && out[w + 2] == 'T'))
            for (k = w; k < e; ++k) out[k] = (char)(out[k] + 32);
        w = e + 1;
    }
    return (int)n;
}

#define BN_SEARCH_URL "/advancedsearch.php?q="
#define BN_SEARCH_TAIL "&fl[]=identifier&fl[]=title&fl[]=creator&fl[]=runtime&sort[]=downloads+desc&rows=25&output=json"

int bn_query_url(const char *term, char *out, unsigned size) {
    char clean[BN_TERM], q[2 * BN_TERM + 80];
    unsigned used;
    int search = bn_clean_term(term, clean, sizeof clean) > 0;
    q[0] = 0;
    if (search) {
        if (!m1_cat(q, sizeof q, "collection:librivoxaudio AND (title:(") || !m1_cat(q, sizeof q, clean) ||
            !m1_cat(q, sizeof q, ") OR creator:(") || !m1_cat(q, sizeof q, clean) || !m1_cat(q, sizeof q, "))"))
            return -1;
    } else
        m1_cat(q, sizeof q, "collection:librivoxaudio");
    out[0] = 0;
    if (!m1_cat(out, size, BN_HOST BN_SEARCH_URL)) return -1;
    used = m1_urlenc(out, size, (unsigned)strlen(out), q);
    if (!used) return -1;
    out[used] = 0;
    if (!m1_cat(out, size, BN_SEARCH_TAIL)) return -1;
    return search;
}

int bn_id_ok(const char *id) {
    unsigned n = 0;
    if (!id || !id[0]) return 0;
    for (; id[n]; ++n) {
        unsigned c = (unsigned char)id[n];
        if (n + 1 >= BN_ID) return 0;
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_' ||
              c == '-'))
            return 0;
    }
    return !(n == 1 && id[0] == '.') && !(n == 2 && id[0] == '.' && id[1] == '.');
}

/* ---------------------------------------------------------------------------
 * The answers
 */
unsigned bn_secs(const char *text) {
    unsigned g[3] = {0, 0, 0}, ng = 0, digits;
    const char *s = text;
    if (!s) return 0;
    for (;;) {
        digits = 0;
        g[ng] = 0;
        while (*s >= '0' && *s <= '9') {
            if (g[ng] < 999999u) g[ng] = g[ng] * 10 + (unsigned)(*s - '0');
            if (g[ng] > 999999u) g[ng] = 999999u;
            ++digits, ++s;
        }
        if (!digits) return 0;
        ++ng;
        if (*s == ':' && ng < 3) {
            ++s;
            continue;
        }
        break;
    }
    if (*s == '.') { /* a fraction ends the last group */
        ++s;
        while (*s >= '0' && *s <= '9') ++s;
    }
    if (*s) return 0;
    return ng == 3 ? g[0] * 3600 + g[1] * 60 + g[2] : ng == 2 ? g[0] * 60 + g[1] : g[0];
}

static unsigned bn_digits(const char *s) {
    unsigned v = 0;
    if (!*s) return 0;
    for (; *s; ++s) {
        if (*s < '0' || *s > '9') return 0;
        if (v > (0xffffffffu - 9) / 10) return 0xffffffffu;
        v = v * 10 + (unsigned)(*s - '0');
    }
    return v;
}

struct bn_docs {
    bn_row_t *out;
    int max, n;
    char id[BN_ID], title[BK_TITLE], author[BN_AUTHOR], runtime[24];
    pj_field_t f[4];
};

static int bn_doc(void *ctx) {
    struct bn_docs *d = ctx;
    bn_row_t *r;
    if (d->f[0].found != 1 || d->f[0].cut || d->f[0].alt || !bn_id_ok(d->id) || d->f[1].found != 1 || !d->title[0])
        return 1;
    r = &d->out[d->n++];
    memcpy(r->id, d->id, strlen(d->id) + 1);
    memcpy(r->title, d->title, strlen(d->title) + 1);
    memcpy(r->author, d->f[2].found == 1 ? d->author : "", d->f[2].found == 1 ? strlen(d->author) + 1 : 1);
    r->secs = bn_secs(d->runtime);
    return d->n < d->max;
}

int bn_parse_docs(const char *json, unsigned n, bn_row_t *out, int max) {
    struct bn_docs d;
    int rc;
    if (max <= 0) return -1;
    memset(&d, 0, sizeof d);
    d.out = out, d.max = max;
    d.f[0].key = "identifier", d.f[0].dst = d.id, d.f[0].cap = sizeof d.id;
    d.f[1].key = "title", d.f[1].dst = d.title, d.f[1].cap = sizeof d.title;
    d.f[2].key = "creator", d.f[2].dst = d.author, d.f[2].cap = sizeof d.author;
    d.f[3].key = "runtime", d.f[3].dst = d.runtime, d.f[3].cap = sizeof d.runtime;
    rc = pj_records(json, n, "response", "docs", d.f, 4, bn_doc, &d);
    return rc < 0 ? -1 : d.n;
}

/* The scanner: a state machine over the bytes of the answer. depth counts the open containers (1: the top-level object, 2: the "result" array, 3: one of its objects); the bytes of an object at depth 3 are
 * kept in obj (BN_OBJ at most: a larger one is skipped) and taken apart by pj_object at its closing brace. */
struct bn_sc {
    bn_part_t *out;
    int max, n, more;
    char *obj;
    unsigned olen;
    int over, capture, depth, instr, esc, arr, entered, lastres, done, bad, complete;
    unsigned klen;
    char key[BN_KEY];
    char prev;
    char format[24], name[BK_FILE], title[BK_TITLE], length[24], size[16];
    pj_field_t f[5];
};

static int bn_is_result(const struct bn_sc *sc) {
    static const char want[] = "result";
    unsigned i;
    if (sc->klen != 6) return 0;
    for (i = 0; i < 6; ++i)
        if (sc->key[i] != want[i]) return 0;
    return 1;
}

static void bn_keep(struct bn_sc *sc, char c) {
    if (!sc->capture) return;
    if (sc->olen < BN_OBJ)
        sc->obj[sc->olen++] = c;
    else
        sc->over = 1;
}

/* The part the object describes, put in order among the n kept (the first max in natural order of the name survive whatever the file's order). */
static void bn_add(struct bn_sc *sc) {
    bn_part_t *p;
    unsigned i, dot;
    int at;
    if (sc->f[0].found != 1 || strcmp(sc->format, BN_FORMAT) || sc->f[1].found != 1 || sc->f[1].cut || sc->f[1].alt ||
        !sc->name[0])
        return;
    for (i = 0; sc->name[i]; ++i)
        if ((unsigned char)sc->name[i] < 0x20 || sc->name[i] == 0x7f || sc->name[i] == '/') return;
    at = sc->n;
    while (at > 0 && bk_natcmp(sc->name, sc->out[at - 1].name) < 0) --at;
    if (at >= sc->max) {
        sc->more = 1;
        return;
    }
    if (sc->n >= sc->max)
        sc->more = 1;
    else
        ++sc->n;
    if (sc->n - 1 > at) memmove(&sc->out[at + 1], &sc->out[at], (unsigned)(sc->n - 1 - at) * sizeof *sc->out);
    p = &sc->out[at];
    memset(p, 0, sizeof *p);
    memcpy(p->name, sc->name, sizeof p->name);
    if (sc->f[2].found == 1 && sc->title[0])
        memcpy(p->title, sc->title, sizeof p->title);
    else {
        unsigned len = (unsigned)strlen(sc->name);
        dot = len;
        for (i = 1; i < len; ++i)
            if (sc->name[i] == '.') dot = i; /* the last dot after the first byte: the extension */
        if (dot > sizeof p->title - 1) {
            dot = sizeof p->title - 1;
            while (dot && ((unsigned char)sc->name[dot] & 0xc0) == 0x80) --dot; /* a cut ends on a character boundary */
        }
        memcpy(p->title, sc->name, dot);
        p->title[dot] = 0;
    }
    p->secs = bn_secs(sc->length);
    p->bytes = bn_digits(sc->size);
}

static void bn_object(struct bn_sc *sc) {
    if (!sc->over && pj_object(sc->obj, sc->olen, sc->f, 5)) bn_add(sc);
    sc->capture = sc->over = 0;
    sc->olen = 0;
}

static void bn_feed(struct bn_sc *sc, const char *data, unsigned len) {
    unsigned i;
    for (i = 0; i < len && !sc->done; ++i) {
        char c = data[i];
        if (sc->instr) {
            bn_keep(sc, c);
            if (sc->esc)
                sc->esc = 0, sc->klen = BN_KEY; /* (an escape in a key: it is not "result") */
            else if (c == '\\')
                sc->esc = 1;
            else if (c == '"') {
                sc->instr = 0;
                if (sc->depth == 1) sc->lastres = bn_is_result(sc);
                sc->prev = '"';
            } else if (sc->depth == 1 && sc->klen < BN_KEY)
                sc->key[sc->klen++] = c;
            else if (sc->depth == 1)
                sc->klen = BN_KEY + 1;
            continue;
        }
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
            bn_keep(sc, c);
            continue;
        }
        if (!sc->depth && c != '{') {
            sc->bad = sc->done = 1;
            return;
        }
        if (c == '"') {
            bn_keep(sc, c);
            sc->instr = 1, sc->esc = 0, sc->klen = 0;
            continue;
        }
        if (c == '{' || c == '[') {
            if (sc->depth == 2 && sc->arr && c == '{') {
                sc->capture = 1, sc->olen = 0, sc->over = 0;
            }
            if (sc->depth == 1 && c == '[' && sc->lastres && sc->prev == ':' && !sc->arr && !sc->complete)
                sc->arr = sc->entered = 1;
            bn_keep(sc, c);
            if (++sc->depth > BN_DEPTH) {
                sc->bad = sc->done = 1;
                return;
            }
        } else if (c == '}' || c == ']') {
            bn_keep(sc, c);
            if (--sc->depth < 0) {
                sc->bad = sc->done = 1;
                return;
            }
            if (sc->capture && sc->depth == 2)
                bn_object(sc);
            else if (c == ']' && sc->arr && sc->depth == 1)
                sc->arr = 0, sc->complete = sc->done = 1;
            else if (!sc->depth)
                sc->done = 1;
        } else
            bn_keep(sc, c);
        sc->prev = c;
    }
}

int bn_scan_files(const char *path, bn_part_t *out, int max, int *complete, int *more) {
    struct bn_sc *sc;
    char *buf;
    int fd, n;
    unsigned total = 0;
    *complete = *more = 0;
    if (max > BK_MAX_PARTS) max = BK_MAX_PARTS;
    if (max <= 0) return -1;
    sc = calloc(1, sizeof *sc);
    buf = calloc(BN_CHUNK + BN_OBJ, 1);
    fd = open(path, O_RDONLY, 0);
    if (!sc || !buf || fd < 0) {
        if (fd >= 0) close(fd);
        free(sc);
        free(buf);
        return -1;
    }
    sc->out = out, sc->max = max, sc->obj = buf + BN_CHUNK;
    sc->f[0].key = "format", sc->f[0].dst = sc->format, sc->f[0].cap = sizeof sc->format;
    sc->f[1].key = "name", sc->f[1].dst = sc->name, sc->f[1].cap = sizeof sc->name;
    sc->f[2].key = "title", sc->f[2].dst = sc->title, sc->f[2].cap = sizeof sc->title;
    sc->f[3].key = "length", sc->f[3].dst = sc->length, sc->f[3].cap = sizeof sc->length;
    sc->f[4].key = "size", sc->f[4].dst = sc->size, sc->f[4].cap = sizeof sc->size;
    while (!sc->done && total < BN_FILES_CAP) {
        int got = read(fd, buf, BN_CHUNK);
        if (got <= 0) break;
        if ((unsigned)got > BN_FILES_CAP - total) got = (int)(BN_FILES_CAP - total);
        total += (unsigned)got;
        bn_feed(sc, buf, (unsigned)got);
    }
    close(fd);
    n = sc->entered ? sc->n : -1; /* -1: no "result" array was ever entered */
    *complete = sc->complete && !sc->bad;
    *more = sc->more;
    free(sc);
    free(buf);
    return n;
}

/* ---------------------------------------------------------------------------
 * The jobs
 *
 * set 0 is the popular list, set 1 the last search; the rows of each are heap records made on first use and kept (6 KB each). A job writes n and the rows before it moves the state; the page reads only past
 * BN_S_QUERY. The popular answer stays for the session; the search is dropped by the next search.
 */
static struct {
    volatile int cstate, ccode, cur, jset, jquery, pstate, pcode;
    volatile unsigned gen;
    volatile int n[2], held[2], pn, pcov, ptrunc;
    volatile unsigned char thumb[2][BN_ROWS], ext[2][BN_ROWS];
    bn_row_t *volatile rows[2];
    bn_part_t *volatile parts;
    char url[BN_URL];
    char pid[BN_ID];
} bn __attribute__((section(".scratch")));

static void bn_dir(void) {
    mkdir("/mnt/mmc/.m1plus", 0755);
    mkdir("/mnt/mmc/.m1plus/audiobooks", 0755);
    mkdir(BN_DIR, 0755);
}

static int bn_tpath(int set, int i, const char *ext, char *out, unsigned size) {
    char name[24];
    pc_fmt(name, sizeof name, set ? "/s%d." : "/p%d.", (unsigned)i);
    out[0] = 0;
    return m1_cat(out, size, BN_DIR) && m1_cat(out, size, name) && m1_cat(out, size, ext);
}

static void bn_unthumb(int set) {
    char path[160];
    int i;
    for (i = 0; i < BN_ROWS; ++i) {
        if (bn_tpath(set, i, "jpg", path, sizeof path)) unlink(path);
        if (bn_tpath(set, i, "png", path, sizeof path)) unlink(path);
        if (bn_tpath(set, i, "src", path, sizeof path)) unlink(path);
        bn.thumb[set][i] = bn.ext[set][i] = 0;
    }
}

void bn_catalog_clean(void) {
    if (pnw_busy()) return;
    bn_unthumb(0);
    bn_unthumb(1);
    bn.n[1] = bn.held[1] = 0;
    if (bn.cur == 1) bn.cur = 0, bn.cstate = BN_S_IDLE;
}

int bn_catalog_state(void) { return bn.cstate; }
int bn_catalog_code(void) { return bn.ccode; }
int bn_catalog_search(void) { return bn.cur == 1; }
unsigned bn_gen(void) { return bn.gen; }
int bn_catalog_count(void) {
    return bn.cstate >= BN_S_THUMBS && bn.ccode == PN_OK && bn.held[bn.cur] ? bn.n[bn.cur] : 0;
}
const bn_row_t *bn_row(int i) {
    return i >= 0 && i < bn_catalog_count() && bn.rows[bn.cur] ? &bn.rows[bn.cur][i] : (const bn_row_t *)0;
}
int bn_thumb_state(int i) { return i >= 0 && i < BN_ROWS ? bn.thumb[bn.cur][i] : 0; }
int bn_thumb(int i, char *path, unsigned size) {
    if (i < 0 || i >= BN_ROWS || bn.thumb[bn.cur][i] != 1) return 0;
    return bn_tpath(bn.cur, i, bn.ext[bn.cur][i] == 2 ? "png" : "jpg", path, size);
}

/* The picture of the item id into the file dst (.jpg or .png as it is), through src: 1 and *ext (1 jpg, 2 png) when the answer is a picture the page can decode. */
static int bn_picture(const char *id, const char *src, const char *dstbase, int *ext) {
    char url[200], dst[160];
    unsigned w, h, sof;
    int kind;
    url[0] = 0;
    if (!m1_cat(url, sizeof url, BN_HOST "/services/img/") || !m1_cat(url, sizeof url, id)) return 0;
    if (pnw_file(url, src, PN_THUMB_CAP) != PN_OK) return 0;
    kind = pc_pic_info(src, &w, &h, &sof);
    dst[0] = 0;
    if (kind && pc_cover_ok(src) && m1_cat(dst, sizeof dst, dstbase) &&
        m1_cat(dst, sizeof dst, kind == 2 ? "png" : "jpg") && !rename(src, dst)) {
        *ext = kind;
        return 1;
    }
    unlink(src);
    return 0;
}

static void bn_thumb_get(int set, int i) {
    char src[160], base[160];
    int ext = 0;
    if (bn_tpath(set, i, "src", src, sizeof src) && bn_tpath(set, i, "", base, sizeof base) &&
        bn_picture(bn.rows[set][i].id, src, base, &ext)) {
        bn.ext[set][i] = (unsigned char)ext;
        __sync_synchronize();
        bn.thumb[set][i] = 1;
    }
    if (bn.thumb[set][i] != 1)
        bn.thumb[set][i] = pnw_cancelled() ? 0 : 2; /* a picture cut off by Cancel is untried, not failed */
    __sync_synchronize();
    ++bn.gen;
}

static void *bn_cmain(void *arg) {
    int set = bn.jset, i, code = PN_OK, n = 0;
    (void)arg;
    if (bn.jquery) {
        char *buf = calloc(PN_JSON_CAP + 1, 1);
        unsigned got = 0;
        code = PN_MEM;
        if (!bn.rows[set]) bn.rows[set] = calloc(BN_ROWS, sizeof(bn_row_t));
        if (buf && bn.rows[set]) {
            code = pnw_json(bn.url, buf, &got);
            if (code == PN_OK) {
                n = bn_parse_docs(buf, got, bn.rows[set], BN_ROWS);
                if (n < 0) code = PN_HTTP, n = 0; /* not an answer of the archive */
            }
        }
        free(buf);
        if (pnw_cancelled()) code = PN_CANCELLED;
        if (code != PN_OK) n = 0;
        for (i = 0; i < BN_ROWS; ++i) bn.thumb[set][i] = bn.ext[set][i] = 0;
        bn.n[set] = n;
        bn.held[set] = code == PN_OK;
        bn.ccode = code;
        __sync_synchronize();
        bn.cstate = code == PN_OK ? BN_S_THUMBS : BN_S_DONE;
        ++bn.gen;
    }
    for (i = 0; code == PN_OK && i < bn.n[set] && !pnw_cancelled(); ++i)
        if (bn.thumb[set][i] == 0) bn_thumb_get(set, i);
    __sync_synchronize();
    bn.cstate = BN_S_DONE;
    ++bn.gen;
    pnw_end();
    return (void *)0;
}

/* Rows of the held popular list whose picture has not been tried. */
static int bn_pending(void) {
    int i, p = 0;
    for (i = 0; i < bn.n[0]; ++i) p += bn.thumb[0][i] == 0;
    return p;
}

int bn_catalog(const char *term) {
    char clean[BN_TERM];
    int g, search, set, query;
    search = bn_clean_term(term, clean, sizeof clean) > 0;
    set = search;
    if (!search && bn.held[0] &&
        !bn_pending()) { /* nothing to fetch: the held list is the current one again (also while another worker runs, a book download say) */
        bn.cur = 0, bn.ccode = PN_OK, bn.cstate = BN_S_DONE;
        ++bn.gen;
        return PN_OK;
    }
    if (pnw_busy()) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    query = search || !bn.held[0];
    if (query && bn_query_url(term, bn.url, sizeof bn.url) < 0) return PN_MEM;
    bn_dir();
    if (search) {
        bn_unthumb(1);
        bn.n[1] = bn.held[1] = 0;
    }
    bn.jset = set, bn.jquery = query, bn.cur = set;
    bn.ccode = PN_OK;
    bn.cstate = query ? BN_S_QUERY : BN_S_THUMBS;
    ++bn.gen;
    g = pnw_spawn(bn_cmain, PN_KIND_BOOKS);
    if (g) bn.cstate = BN_S_IDLE;
    return g;
}

/* The current rows' untried pictures (a Cancel cut them): fetched with no query, so the rows, a search's too, stay as they are. */
int bn_thumbs(void) {
    int g, set = bn.cur;
    if (!bn.held[set]) return PN_OK;
    if (pnw_busy()) return PN_BUSY;
    g = pn_guard();
    if (g) return g;
    bn_dir();
    bn.jset = set, bn.jquery = 0;
    bn.cstate = BN_S_THUMBS;
    ++bn.gen;
    g = pnw_spawn(bn_cmain, PN_KIND_BOOKS);
    if (g) bn.cstate = BN_S_DONE, ++bn.gen; /* (the rows are still the answer) */
    return g;
}

/* ---- The preview */
static int bn_pcov_path(int ext, char *out, unsigned size) {
    out[0] = 0;
    return m1_cat(out, size, BN_DIR) && m1_cat(out, size, ext == 2 ? "/preview.png" : "/preview.jpg");
}

int bn_preview_state(void) { return bn.pstate; }
int bn_preview_code(void) { return bn.pcode; }
const char *bn_preview_id(void) { return bn.pid; }
int bn_preview_count(void) { return bn.pstate == 2 && bn.pcode == PN_OK && bn.parts ? bn.pn : 0; }
const bn_part_t *bn_part(int i) { return i >= 0 && i < bn_preview_count() ? &bn.parts[i] : (const bn_part_t *)0; }
int bn_preview_cover(char *path, unsigned size) {
    return bn.pstate == 2 && bn.pcov && bn_pcov_path(bn.pcov, path, size);
}

int bn_preview_totals(unsigned *parts, unsigned *secs, unsigned *bytes, int *more) {
    int i, n = bn_preview_count();
    *parts = (unsigned)n, *secs = *bytes = 0, *more = bn.ptrunc;
    for (i = 0; i < n; ++i) {
        *secs += bn.parts[i].secs;
        *bytes = bn.parts[i].bytes > 0xffffffffu - *bytes ? 0xffffffffu : *bytes + bn.parts[i].bytes;
    }
    return n > 0;
}

void bn_preview_drop(void) {
    char path[160];
    if (pnw_busy()) return;
    free(bn.parts);
    bn.parts = (bn_part_t *)0;
    bn.pn = bn.ptrunc = bn.pcov = 0;
    bn.pstate = 0, bn.pcode = PN_OK, bn.pid[0] = 0;
    if (bn_pcov_path(1, path, sizeof path)) unlink(path);
    if (bn_pcov_path(2, path, sizeof path)) unlink(path);
}

static void *bn_pmain(void *arg) {
    char url[200], src[160], base[160];
    bn_part_t *parts;
    int code = PN_MEM, n = 0, complete = 0, more = 0, ext = 0;
    (void)arg;
    url[0] = 0;
    parts = calloc(BK_MAX_PARTS, sizeof(bn_part_t));
    if (parts && m1_cat(url, sizeof url, BN_HOST "/metadata/") && m1_cat(url, sizeof url, bn.pid) &&
        m1_cat(url, sizeof url, "/files")) {
        code = pnw_file(url, BN_FILES_PATH, BN_FILES_CAP);
        if (code == PN_OK) {
            n = bn_scan_files(BN_FILES_PATH, parts, BK_MAX_PARTS, &complete, &more);
            code = n < 0 ? PN_NOBOOK : !complete ? PN_NOTFEED : !n ? PN_NOBOOK : PN_OK;
        }
        unlink(BN_FILES_PATH);
    }
    if (pnw_cancelled()) code = PN_CANCELLED;
    if (code == PN_OK) { /* the picture: a failure leaves the page its placeholder */
        src[0] = base[0] = 0;
        m1_cat(src, sizeof src, BN_DIR "/preview.src");
        m1_cat(base, sizeof base, BN_DIR "/preview.");
        if (bn_picture(bn.pid, src, base, &ext)) bn.pcov = ext;
        if (pnw_cancelled()) code = PN_CANCELLED;
    }
    if (code != PN_OK) {
        free(parts);
        parts = (bn_part_t *)0;
        n = 0;
    }
    bn.parts = parts;
    bn.pn = code == PN_OK ? n : 0;
    bn.ptrunc = more;
    bn.pcode = code;
    __sync_synchronize();
    bn.pstate = code == PN_CANCELLED ? 0 : 2;
    ++bn.gen;
    pnw_end();
    return (void *)0;
}

int bn_preview(const char *id) {
    int g;
    if (pnw_busy()) return PN_BUSY;
    if (!bn_id_ok(id)) return PN_NOBOOK;
    g = pn_guard();
    if (g) return g;
    bn_preview_drop();
    bn_dir();
    memcpy(bn.pid, id, strlen(id) + 1);
    bn.pcode = PN_OK;
    bn.pstate = 1;
    ++bn.gen;
    g = pnw_spawn(bn_pmain, PN_KIND_BOOKPREV);
    if (g) bn.pstate = 0, bn.pid[0] = 0;
    return g;
}
