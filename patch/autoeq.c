/* M1+ Music AutoEq download: the Presets page's "Download from AutoEq" (docs/modules/peq.md "AutoEq download").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The data is Jaakko Pasanen's AutoEq project (github.com/jaakkopasanen/AutoEq, MIT licence): its results/INDEX.md and each headphone's ParametricEQ.txt.
 *
 * Its own window (ui/m1plus_autoeq.bin: Radio's search level's top, the glass Back, the field, one list holding ONE content view this file paints, our keyboard embedded by keyboard_attach) over the AutoEq index on the
 * card (PN_EQ_INDEX, downloaded by patch/pcnet.c's AutoEq job the first time the page opens and again when it is older than PN_EQ_MAX_AGE; the page works offline once it is there).
 *
 *   index    "- [Name](./Source/Kind/Name) by Source[ on Target]", one line a result, 8,850 of them (0.85 MB). Never held in memory: each query reads the file again in 1 KB pieces and keeps at most AE_MAX results
 *            (the best tier first, then the file's order: its names are sorted). A result is a name, its source, its target, its kind and the path below PN_EQ_BASE.
 *   search   every word of the field is a case-insensitive substring of the name (any order), whatever the source (no filter: the source is in each row's grey line). Tier 0: the name is the whole query, 1: it starts with the first word, 2: the rest.
 *   rows     the name, "Source · Kind[ · Target]" in grey, and at the right a download glyph; while its file comes a ring and "Downloading…"; once it is in the card's EQ folder a check and
 *            "In use" for the one that plays, "Saved to EQ · Tap to use" for the rest. A finished download plays at once (peq_select). A tap on a result that is not saved asks the worker for its file; a tap on a saved one selects it (peq_select).
 *   files    the first line of a downloaded file is "# AutoEq: <path>" (a comment, which the parser and Equalizer APO ignore): the page finds a result's file again by it. The name is the headphone's, cut and cleaned for the
 *            card; when another file has it, "<name> (<source>)", then "<name> (<source> 2)" ...; a file of the same name that has this stamp is the result's own.
 *   job      the worker writes PN_EQ_PRESET; this page parses it with the Equalizer's parser (peq_import_file) and only a file that parses is renamed into PEQ_DIR.
 * One page-scoped timer (the debounce, the job's state, the ring); nothing else runs. No hook, no import.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "azlist.h"
#include "grid.h"
#include "keyboard.h"
#include "search.h"
#include "i18n.h"
#include "podcasts.h"
#include "peqpage.h"
#include "pcjson.h"
#include "pcnet.h"
#include "peq.h"
#include "autoeq.h"
#include "home.h"

#define AE_MAX 20 /* results kept (the Podcasts' search shows 25; sonix 20) */
#define AE_NAME 64
#define AE_SRC 24
#define AE_PATH 200
#define AE_LINE 256 /* the longest index line looked at (the longest there is has 219 bytes) */
#define AE_TERMS 4
#define AE_TERM 32
#define AE_QMAX 64
#define AE_LIST_Y \
    98 /* under the glass bar (50) with Radio's search list top (RP_TOP_SEARCH 48) below it: the rows start under the field (ui/m1plus_autoeq.bin, AE_LIST_Y in tools/pod_ui.py) */
#define AE_LIST_H (SE_LIST_H + SE_LIST_Y - AE_LIST_Y) /* to the window's bottom, as the Search page's list */
#define AE_TEXT_W \
    224 /* the field's text: the page's width less the text's start and the clear button (Radio's RP_TEXT_W) */
#define AE_TICK_MS 40
#define AE_DEBOUNCE 5
#define AE_SPIN 3 /* ticks to a frame of the ring */
#define AE_ROW_H \
    52 /* a result row: the title (LIST_TITLE_H) over the grey line (LIST_SUB_H), 8 px lower than Search's AE_ROW_H, and no thumbnail */
#define AE_TEXT_X 16 /* the text and the separator start here, as Search's text-only rows (SE_REC_TEXT_X) */
#define AE_TITLE_Y 3
#define AE_SUB_Y 29
#define AE_GLYPH 22 /* the download glyph, the check and the ring */
#define AE_ACC_X 284 /* where they start */
#define AE_TEXT_END 276 /* the texts are cut here */
#define AE_ICON_GREY 0xaa /* the download glyph */
#define AE_HINT_Y 96 /* the failure's "Try Again", content coordinates: under the state line */
#define AE_VARIANTS 9 /* names tried for one result */

enum { P_LIST, P_READY, P_FAIL };
enum { ROW_NEW, ROW_BUSY, ROW_SAVED };

typedef struct {
    char name[AE_NAME], src[AE_SRC], tgt[AE_SRC];
    unsigned char form; /* 0 unknown, 1 over-ear, 2 in-ear, 3 earbud */
    unsigned char tier;
    char path[AE_PATH]; /* below PN_EQ_BASE: "Source/Kind/Name", percent-encoded as the index has it */
} ae_ent;

typedef struct {
    ae_ent e;
    char file
        [PEQ_NAME]; /* the card's file name for it: its own when saved, the free one when not; "" when no name is free */
    unsigned char state;
} ae_row;

static const char *const ae_form_key[4] = {"", "Over-ear", "In-ear", "Earbud"};

static struct {
    void *win, *view, *sv, *list, *status, *field, *st_title, *st_sub;
    char typed[AE_QMAX];
    char term[AE_TERMS][AE_TERM];
    int nterms, qn; /* words; the length of the query as the words joined by single spaces */
    int phase, fail; /* P_*; the list download's PN_* when P_FAIL */
    int want,
        bg; /* a job is to start when the slot is free: 1 the list, 2 a preset; the list's job is a refresh (the page stays as it is) */
    int running; /* our job runs (1 the list, 2 a preset) */
    char jobpath[AE_PATH], jobfile[PEQ_NAME], jobstamp[AE_PATH + 16]; /* the preset being fetched */
    int nres, press, down, pressing, wait, frame, spin, content;
    m1_tap_t tap;
    unsigned timer;
    ae_row *rows;
    grid_tile_t *tiles;
    peq_state *st;
    void *b_down, *b_check, *b_ring;
    unsigned hint[24], hint_w;
    int hint_n;
} ae __attribute__((section(".scratch")));

static int ae_off(void) { return ae.sv ? I(ae.sv, SC_YOFF) : 0; }
static void ae_redraw(void) { widget_invalidate_force(ae.sv, (void *)0); }

static int ae_same(const char *a, const char *b, unsigned n) { /* the first n bytes are equal */
    unsigned i;
    for (i = 0; i < n; ++i)
        if (a[i] != b[i]) return 0;
    return 1;
}

/* ---------------------------------------------------------------------------
 * The glyphs: drawn here, as the chevron is (4 x 4 samples a pixel, strokes 2 px wide on Lucide's 24 unit grid), so the page needs no image of its own.
 */
enum { G_DOWN, G_CHECK, G_RING };

static const float ae_dl[] = {
    12, 3,  12, 15, 7,  10,
    12, 15, 17, 10, 12, 15}; /* the arrow: the shaft, then the two strokes of the head (pairs of ends) */
static const float ae_tray[] = {3, 15, 3, 19, 3.6f, 20.4f, 5, 21, 19, 21, 20.4f, 20.4f, 21, 19, 21, 15};
static const float ae_ck[] = {4, 12, 9, 17, 20, 6};
static const float ae_cs[8][2] = {{1, 0},  {0.7071f, 0.7071f},   {0, 1},  {-0.7071f, 0.7071f},
                                  {-1, 0}, {-0.7071f, -0.7071f}, {0, -1}, {0.7071f, -0.7071f}};

static float ae_seg(float px, float py, float ax, float ay, float bx,
                    float by) { /* squared distance from a point to a segment */
    float dx = bx - ax, dy = by - ay, t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), cx, cy;
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    cx = ax + t * dx - px, cy = ay + t * dy - py;
    return cx * cx + cy * cy;
}

static int ae_poly(const float *p, int n, float x, float y) { /* inside the stroke of the polyline of n points */
    int i;
    for (i = 0; i + 1 < n; ++i)
        if (ae_seg(x, y, p[2 * i], p[2 * i + 1], p[2 * i + 2], p[2 * i + 3]) <= 1.0f) return 1;
    return 0;
}

/* Is the point (x, y) of the 24 unit grid on the glyph? bit 0: its ink; bit 1: the ring's faint track. */
static int ae_ink(int kind, int frame, float x, float y) {
    int i;
    float dx, dy, d2;
    switch (kind) {
    case G_DOWN:
        for (i = 0; i < 6; i += 2)
            if (ae_seg(x, y, ae_dl[2 * i], ae_dl[2 * i + 1], ae_dl[2 * i + 2], ae_dl[2 * i + 3]) <= 1.0f) return 1;
        return ae_poly(ae_tray, 8, x, y);
    case G_CHECK:
        return ae_poly(ae_ck, 3, x, y);
    default:
        dx = x - 12, dy = y - 12, d2 = dx * dx + dy * dy;
        if (d2 < 64 || d2 > 100) return 0;
        { /* the gap is the quarter turn from v0 (the frame's angle) to v1 = (-v0y, v0x): d is in it when cross(v0, d) >= 0 and cross(d, v1) >= 0, which is d . v0 >= 0 */
            float cx = ae_cs[frame & 7][0], cy = ae_cs[frame & 7][1];
            if (cx * dy - cy * dx >= 0 && dx * cx + dy * cy >= 0) return 2;
        }
        return 3;
    }
}

/* The alpha (0..255) of a size x size glyph (24 unit grid scaled to it) at pixel (x, y), written into px as a grey ink on that grey. */
static unsigned ae_cover(int kind, int frame, int size, int x, int y) {
    int i, j, ink = 0, track = 0;
    for (i = 0; i < 4; ++i)
        for (j = 0; j < 4; ++j) {
            int v = ae_ink(kind, frame, (x + (j + 0.5f) / 4) * 24.0f / size, (y + (i + 0.5f) / 4) * 24.0f / size);
            if (v & 1) ++ink;
            if (v & 2) ++track;
        }
    ink = ink * 255 / 16, track = track * 70 / 16;
    return (unsigned)(ink > track ? ink : track);
}

static void *ae_make(int size, int kind, int frame, unsigned grey, void *into) {
    unsigned *px;
    int x, y;
    void *b = into ? into : bitmap_create_ex(size, size, size * 4, BITMAP_RGBA8888);
    if (!b) return (void *)0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != (unsigned)(size * 4)) {
        if (px) bitmap_unlock_buffer(b);
        if (!into) bitmap_destroy(b);
        return (void *)0;
    }
    for (y = 0; y < size; ++y)
        for (x = 0; x < size; ++x) px[y * size + x] = ae_cover(kind, frame, size, x, y) << 24 | grey * 0x010101u;
    bitmap_unlock_buffer(b);
    return b;
}

/* ---------------------------------------------------------------------------
 * The index
 */
/* One line of the index: "- [Name](./Source/Kind/Name) by Source[ on Target]". 1 and the entry, 0 for any other line (the heading, a line that is too long for the room). The name is cut on a character
 * boundary when it does not fit. Not static: test/pod/autoeq.py calls it with lines of its own. */
__attribute__((noinline)) int ae_parse(const char *l, unsigned n, ae_ent *e) {
    unsigned i, j, k, nameend, p0, p1, s0, s1, slashes = 0, sl0 = 0, sl1 = 0;
    memset(e, 0, sizeof *e);
    while (n && (l[n - 1] == '\r' || l[n - 1] == ' ')) --n;
    if (n < 12 || l[0] != '-' || l[1] != ' ' || l[2] != '[') return 0;
    for (i = 3; i + 3 < n && !(l[i] == ']' && l[i + 1] == '(' && l[i + 2] == '.' && l[i + 3] == '/'); ++i) {
    }
    if (i + 3 >= n || i == 3) return 0;
    nameend = i, p0 = i + 4;
    for (j = p0;
         j + 5 <= n && !(l[j] == ')' && l[j + 1] == ' ' && l[j + 2] == 'b' && l[j + 3] == 'y' && l[j + 4] == ' ');
         ++j) {
    }
    if (j + 5 > n || j == p0 || j - p0 >= AE_PATH) return 0;
    p1 = j, s0 = j + 5, s1 = n;
    for (k = s0; k + 4 <= n; ++k)
        if (l[k] == ' ' && l[k + 1] == 'o' && l[k + 2] == 'n' && l[k + 3] == ' ') {
            s1 = k;
            break;
        }
    if (s1 == s0 || s1 - s0 >= AE_SRC || (s1 < n && n - (s1 + 4) >= AE_SRC)) return 0;
    for (k = p0; k < p1; ++k)
        if (l[k] == '/') {
            if (++slashes == 1) sl0 = k;
            sl1 = k;
        }
    if (slashes != 2) return 0; /* "Source/Kind/Name" */
    memcpy(e->path, l + p0, p1 - p0);
    memcpy(e->src, l + s0, s1 - s0);
    if (s1 < n) memcpy(e->tgt, l + s1 + 4, n - (s1 + 4));
    k = nameend - 3;
    if (k >= AE_NAME) { /* cut at a character boundary */
        k = AE_NAME - 1;
        while (k && ((unsigned char)l[3 + k] & 0xc0) == 0x80) --k;
    }
    memcpy(e->name, l + 3, k);
    { /* the kind: how the directory under the source ends ("over-ear", "GRAS 43AG-7 in-ear") */
        const char *dir = e->path + (sl0 - p0) + 1;
        unsigned dn = sl1 - sl0 - 1;
        static const struct {
            const char *s;
            unsigned char f;
        } kinds[] = {{"over-ear", 1}, {"in-ear", 2}, {"earbud", 3}};
        for (k = 0; k < 3; ++k) {
            unsigned kn = strlen(kinds[k].s);
            if (dn >= kn && ae_same(dir + dn - kn, kinds[k].s, kn)) e->form = kinds[k].f;
        }
    }
    return 1;
}

static int ae_lower(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

/* The field's text as words: lower-cased (ASCII), split at spaces, at most AE_TERMS of AE_TERM bytes. */
static void ae_set_terms(const char *q) {
    int t = 0, o = 0;
    ae.nterms = 0, ae.qn = 0;
    memset(ae.term, 0, sizeof ae.term);
    for (; *q && t < AE_TERMS; ++q) {
        if (*q == ' ' || *q == '\t') {
            if (o) t++, o = 0;
            continue;
        }
        if (o < AE_TERM - 1) ae.term[t][o++] = (char)ae_lower((unsigned char)*q);
    }
    ae.nterms = o ? t + 1 : t;
    for (t = 0; t < ae.nterms; ++t) ae.qn += (int)strlen(ae.term[t]) + (t ? 1 : 0);
}

static int ae_has(const char *name, unsigned n,
                  const char *term) { /* the term is a substring of the name (n bytes), ignoring ASCII case */
    unsigned i, j;
    for (i = 0; i < n; ++i) {
        for (j = 0; term[j] && i + j < n && ae_lower((unsigned char)name[i + j]) == (unsigned char)term[j]; ++j) {
        }
        if (!term[j]) return 1;
    }
    return 0;
}

/* The tier of a name that holds every word: 0 it is the whole query (the words joined by single spaces), 1 it starts with the first word, 2 otherwise. */
static int ae_tier(const char *name) {
    unsigned n = strlen(name), i, k = 0;
    int t;
    if ((int)n == ae.qn) {
        for (t = 0, i = 0; t < ae.nterms; ++t) {
            unsigned j;
            if (t && ae_lower((unsigned char)name[i++]) != ' ') break;
            for (j = 0; ae.term[t][j]; ++j, ++i)
                if (ae_lower((unsigned char)name[i]) != (unsigned char)ae.term[t][j]) break;
            if (ae.term[t][j]) break;
        }
        if (t == ae.nterms) return 0;
    }
    for (k = 0; ae.term[0][k]; ++k)
        if (ae_lower((unsigned char)name[k]) != (unsigned char)ae.term[0][k]) return 2;
    return 1;
}

/* A line of the index: when it is a result that holds every word, it goes in its place (the tier, then the file's order) unless AE_MAX better ones are there. */
static void ae_consider(const char *l, unsigned n) {
    ae_ent t;
    int tier, pos, k;
    unsigned i;
    for (i = 3; i + 3 < n && !(l[i] == ']' && l[i + 1] == '(' && l[i + 2] == '.' && l[i + 3] == '/'); ++i) {
    }
    if (n < 12 || l[0] != '-' || i + 3 >= n) return;
    for (k = 0; k < ae.nterms;
         ++k) /* the words first, on the line as it is: most lines end here, before anything is copied */
        if (!ae_has(l + 3, i - 3, ae.term[k])) return;
    if (!ae_parse(l, n, &t)) return;
    for (k = 0; k < ae.nterms; ++k)
        if (!ae_has(t.name, strlen(t.name), ae.term[k])) return; /* (the name as kept: cut at 63 bytes) */
    tier = ae_tier(t.name);
    for (pos = ae.nres; pos > 0 && ae.rows[pos - 1].e.tier > tier; --pos) {
    }
    if (pos >= AE_MAX) return;
    if (ae.nres < AE_MAX) ae.nres++;
    for (k = ae.nres - 1; k > pos; --k) ae.rows[k] = ae.rows[k - 1];
    memset(&ae.rows[pos], 0, sizeof ae.rows[pos]);
    ae.rows[pos].e = t;
    ae.rows[pos].e.tier = (unsigned char)tier;
}

/* The results of the field's words, read from the index in place: -1 when it cannot be opened. */
static int ae_scan(void) {
    char buf[2048], line[AE_LINE];
    unsigned ll = 0;
    int fd, r, k, over = 0;
    ae.nres = 0;
    fd = open(PN_EQ_INDEX, O_RDONLY, 0);
    if (fd < 0) return -1;
    while ((r = read(fd, buf, sizeof buf)) > 0)
        for (k = 0; k < r; ++k) {
            if (buf[k] == '\n') {
                if (!over) ae_consider(line, ll);
                ll = 0, over = 0;
            } else if (ll < sizeof line)
                line[ll++] = buf[k];
            else
                over = 1;
        }
    if (ll && !over) ae_consider(line, ll);
    close(fd);
    return ae.nres;
}

/* ---------------------------------------------------------------------------
 * Files: the name a result has on the card, and whether the card has it already
 */
/* Name variant k of result e as a card file name (".txt" included, below PEQ_NAME bytes, none of the characters FAT refuses, no leading dot): k 0 the headphone's name, 1 "<name> (<source>)", more "<name> (<source> k)". */
static void ae_cand(const ae_ent *e, int k, char *out) {
    char suf[AE_SRC + 8], base[PEQ_NAME];
    unsigned room, i, o = 0;
    suf[0] = 0;
    if (k == 1)
        snprintf(suf, sizeof suf, " (%s)", e->src);
    else if (k > 1)
        snprintf(suf, sizeof suf, " (%s %d)", e->src, k);
    room = PEQ_NAME - 1 - 4 - strlen(suf);
    for (i = 0; e->name[i] && o < room; ++i) {
        unsigned char c = (unsigned char)e->name[i];
        if (c < ' ' || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' ||
            c == '|')
            c = '-';
        if (!o && c == '.') c = '_';
        base[o++] = (char)c;
    }
    if (e->name[i]) { /* cut: not inside a character */
        while (o && ((unsigned char)e->name[o] & 0xc0) == 0x80) --o;
    }
    while (o && (base[o - 1] == ' ' || base[o - 1] == '.')) --o;
    base[o] = 0;
    snprintf(out, PEQ_NAME, "%s%s.txt", base, suf);
}

static void ae_stamp(const ae_ent *e, char *out, unsigned size) { snprintf(out, size, PEQ_STAMP "%s", e->path); }

static int ae_stamped(const char *file, const ae_ent *e) { /* the file's first line is the result's stamp */
    char path[PEQ_NAME + 16], want[AE_PATH + 16], buf[AE_PATH + 32];
    int fd, n;
    unsigned w;
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, file);
    ae_stamp(e, want, sizeof want);
    w = strlen(want);
    fd = open(path, O_RDONLY, 0);
    if (fd < 0) return 0;
    n = read(fd, buf, sizeof buf);
    close(fd);
    return n >= (int)w && ae_same(buf, want, w) && ((int)w == n || buf[w] == '\n' || buf[w] == '\r');
}

/* Row r's state: fetching now, saved (the file that has its stamp), or new (the first free name; "" when all AE_VARIANTS are taken by other files). */
static void ae_resolve(int r) {
    ae_row *w = &ae.rows[r];
    char path[PEQ_NAME + 16], cand[PEQ_NAME], first[PEQ_NAME];
    int k, free_ = 0;
    w->state = ROW_NEW, w->file[0] = 0;
    if ((ae.running == 2 || ae.want == 2) && !strcmp(ae.jobpath, w->e.path)) {
        w->state = ROW_BUSY;
        memcpy(w->file, ae.jobfile, sizeof w->file);
        return;
    }
    for (k = 0; k < AE_VARIANTS; ++k) {
        ae_cand(&w->e, k, cand);
        snprintf(path, sizeof path, "%s/%s", PEQ_DIR, cand);
        if (access(path, F_OK)) {
            if (!free_)
                free_ = 1,
                memcpy(first, cand, sizeof first); /* the first free name; a later variant may still be this result's */
        } else if (ae_stamped(cand, &w->e)) {
            w->state = ROW_SAVED;
            memcpy(w->file, cand, sizeof w->file);
            return;
        }
    }
    if (free_)
        memcpy(w->file, first, sizeof w->file);
    else
        w->file[0] = 0;
}

/* ---------------------------------------------------------------------------
 * The rows' texts, the layout, the paint
 */
static void ae_prep(int r) {
    ae_row *w = &ae.rows[r];
    char sub[96];
    if (w->state == ROW_BUSY)
        snprintf(sub, sizeof sub, "%s", TR("Downloading…"));
    else if (w->state == ROW_SAVED) {
        int use = ae.st && ae.st->mode == PEQ_FILE && !strcmp(ae.st->name, w->file);
        snprintf(sub, sizeof sub, "%s", use ? TR("In use") : TR("Saved to EQ · Tap to use"));
    } else {
        const char *k = w->e.form ? TR(ae_form_key[w->e.form]) : "";
        int o = snprintf(sub, sizeof sub, "%s", w->e.src);
        if (*k && o < (int)sizeof sub) o += snprintf(sub + o, sizeof sub - (unsigned)o, " \xc2\xb7 %s", k);
        if (w->e.tgt[0] && o < (int)sizeof sub) snprintf(sub + o, sizeof sub - (unsigned)o, " \xc2\xb7 %s", w->e.tgt);
    }
    memset(&ae.tiles[r], 0, sizeof ae.tiles[r]);
    grid_set(&ae.tiles[r], w->e.name, sub, 0);
}

static void ae_prep_all(void) {
    int r;
    for (r = 0; r < ae.nres; ++r) ae_prep(r);
}

/* The words of a failed job, the Podcasts' (the keys of the translation tables). */
static const char *ae_word(int code) {
    switch (code) {
    case PN_NOWIFI:
        return "No Wi-Fi";
    case PN_NOCLOCK:
        return "Set the date first";
    case PN_NOCERT:
        return "Certificates missing";
    case PN_CERT:
        return "Certificate problem";
    case PN_HTTP:
    case PN_GONE:
    case PN_NOTFEED:
    case PN_NOFEED:
        return "Server error";
    case PN_STORAGE:
    case PN_CARDFULL:
        return "Storage unavailable";
    case PN_MEM:
        return "Not enough memory";
    default:
        return "Can't connect";
    }
}

static void ae_layout(void) {
    int pad = keyboard_shown() ? KB_H : SE_BOTTOM, h, off = ae_off(), msg = 0;
    const char *key = (const char *)0;
    ae.content = ae.phase == P_READY ? ae.nres * AE_ROW_H + pad : AE_LIST_H;
    h = ae.content < AE_LIST_H ? AE_LIST_H : ae.content;
    widget_resize(ae.view, 320, h);
    widget_set_prop_int(ae.sv, "virtual_h", h);
    if (off > h - AE_LIST_H) widget_set_prop_int(ae.sv, "yoffset", h - AE_LIST_H);
    if (ae.phase == P_LIST)
        key = "Downloading List…", msg = 1;
    else if (ae.phase == P_FAIL)
        key = ae_word(ae.fail), msg = 1;
    else if (ae.nterms && !ae.nres)
        key = "No Results", msg = 1;
    m1_show(ae.list, ae.nres != 0 || ae.phase == P_FAIL);
    m1_show(ae.status, msg);
    if (key) widget_set_tr_text(ae.status, key);
}

static void ae_span(int *r0, int *r1) {
    int off = ae_off();
    *r0 = off < 0 ? 0 : off / AE_ROW_H;
    *r1 = (off + AE_LIST_H - 1) / AE_ROW_H;
    if (*r1 > ae.nres - 1) *r1 = ae.nres - 1;
}

static void ae_icon(void *canvas, void *bmp, int x, int y, int size) {
    if (!bmp || y < 0 || y + size > AE_LIST_H) return;
    peq_blit(canvas, bmp, size, size, x, y);
}

static void ae_paint_rows(void *canvas) {
    int r0, r1, r, off = ae_off(), pass;
    ae_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = r * AE_ROW_H - off, st = ae.rows[r].state;
        if (ae.press == r + 1) az_fill(canvas, 0, y, y + AE_ROW_H - 1, 320, LIST_PRESS);
        ae_icon(canvas,
                st == ROW_BUSY    ? ae.b_ring
                : st == ROW_SAVED ? ae.b_check
                                  : ae.b_down,
                AE_ACC_X, y + (AE_ROW_H - AE_GLYPH) / 2, AE_GLYPH);
        az_fill(canvas, AE_TEXT_X, y + AE_ROW_H - 1, y + AE_ROW_H, SE_SEP_END - AE_TEXT_X, LIST_HAIR);
    }
    for (pass = 0; pass < 2; ++pass) {
        widget_prepare_text_style(pass ? ae.st_sub : ae.st_title, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, &ae.tiles[r], pass, AE_TEXT_X, r * AE_ROW_H - off + (pass ? AE_SUB_Y : AE_TITLE_Y),
                      AE_TEXT_END - AE_TEXT_X, pass ? LIST_SUB_H : LIST_TITLE_H, AE_LIST_H);
    }
}

static void ae_paint_hint(void *canvas) { /* after a failure: "Try Again", grey, centred under the state line */
    int rect[4];
    if (!ae.hint_n) return;
    widget_prepare_text_style(ae.st_sub, canvas);
    rect[0] = (320 - (int)ae.hint_w) / 2, rect[1] = AE_HINT_Y - ae_off(), rect[2] = (int)ae.hint_w,
    rect[3] = LIST_SUB_H;
    canvas_draw_text_in_rect(canvas, ae.hint, (unsigned)ae.hint_n, rect);
}

static int ae_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = ae_off();
    (void)ctx;
    if (!canvas || !ae.view || !ae.rows) return RET_OK;
    if (ae.phase == P_FAIL) {
        I(canvas, CANVAS_OY) += off;
        ae_paint_hint(canvas);
        I(canvas, CANVAS_OY) -= off;
        return RET_OK;
    }
    if (ae.phase != P_READY || !ae.nres) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    ae_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The query, the jobs, the timer
 */
static void ae_kick(void);

/* The typed text is applied: the index read for it, every result's state found, the rows laid out. */
static void ae_apply(void) {
    int r;
    ae.press = ae.down = 0;
    ae_set_terms(ae.typed);
    ae.nres = 0;
    if (ae.phase == P_READY && ae.nterms && ae_scan() < 0) { /* the list is gone from the card: it is fetched again */
        ae.nres = 0;
        ae.phase = P_LIST, ae.want = 1, ae.bg = 0;
        keyboard_show(0);
        ae_kick();
    }
    for (r = 0; r < ae.nres; ++r) ae_resolve(r);
    ae_prep_all();
    widget_set_prop_int(ae.sv, "yoffset", 0);
    ae_layout();
    ae_redraw();
}

/* The job slot is free (the Podcasts' downloads have a thread of their own and go on). */
static int ae_slot_free(void) { return !(pn_busy() || pn_job_busy()); }

/* A job did not start, or ended badly: the list's failure is the page's state; a preset's is a message box and the row as it was. */
static void ae_row_failed(int code) {
    if (code != PN_CANCELLED) pod_toast(TR(ae_word(code)));
}

static void ae_start(void) {
    int g;
    if (ae.want == 1)
        g = pn_eq_index();
    else
        g = pn_eq_get(ae.jobpath, ae.jobstamp);
    if (g == PN_BUSY) return;
    if (g) {
        if (ae.want == 1 && !ae.bg) {
            ae.phase = P_FAIL, ae.fail = g;
            keyboard_show(0);
        } else if (ae.want == 2) {
            ae_row_failed(g);
            ae.jobpath[0] = 0;
        }
        ae.want = 0, ae.bg = 0;
        ae_apply();
        return;
    }
    ae.running = ae.want, ae.want = 0;
}

/* The preset came: it must parse as the Equalizer's own files do, and only then is it renamed into the card's EQ folder. */
static void ae_installed(void) {
    peq_preset p;
    peq_error err;
    char dest[PEQ_NAME + 16];
    int ok;
    snprintf(dest, sizeof dest, "%s/%s", PEQ_DIR, ae.jobfile);
    ok = peq_import_file(PN_EQ_PRESET, &p, &err);
    if (!ok)
        pod_toast(TR("Cannot read this preset"));
    else {
        mkdir(PEQ_DIR, 0755);
        if (rename(PN_EQ_PRESET, dest)) {
            ok = 0;
            pod_toast(TR("Storage unavailable"));
        }
    }
    if (!ok)
        unlink(PN_EQ_PRESET);
    else if (
        peq_select(
            ae.jobfile)) /* the preset that came plays, as a tap on its row makes it play (its row then says "In use") */
        peq_state_load(ae.st);
}

static void ae_poll(void) {
    int st = pn_eq_state(), mode, code;
    if (st == PN_E_RUNNING) return;
    mode = pn_eq_mode(), code = pn_eq_code();
    pn_eq_reset();
    ae.running = 0;
    if (mode == 0) {
        if (st == PN_E_DONE) {
            ae.phase = P_READY;
            if (!ae.bg) keyboard_show(1);
        } else if (!ae.bg)
            ae.phase = P_FAIL, ae.fail = code;
        ae.bg = 0;
    } else {
        if (st == PN_E_DONE)
            ae_installed();
        else
            ae_row_failed(code);
        ae.jobpath[0] = 0;
    }
    ae_apply();
}

static int ae_tick(const void *timer) {
    (void)timer;
    if (!ae.win) return RET_OK;
    if (ae.want && ae_slot_free()) ae_start();
    if (ae.running) {
        ae_poll();
        if (ae.running == 2 && ae.b_ring && ++ae.spin >= AE_SPIN) { /* the ring turns a step */
            ae.spin = 0;
            ae.frame = (ae.frame + 1) & 7;
            ae_make(AE_GLYPH, G_RING, ae.frame, AE_ICON_GREY, ae.b_ring);
            ae_redraw();
        }
    }
    if (ae.wait > 0 && --ae.wait == 0) ae_apply();
    if (ae.want || ae.running || ae.wait > 0) return RET_REPEAT;
    ae.timer = 0;
    return RET_OK;
}

static void ae_kick(void) {
    if (!ae.timer) ae.timer = timer_add(ae_tick, (void *)0, AE_TICK_MS);
}

/* ---------------------------------------------------------------------------
 * Touch
 */
static int ae_at(int y) { return ae.phase == P_READY && y >= 0 && y / AE_ROW_H < ae.nres ? y / AE_ROW_H : -1; }

static int ae_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(ae.view, pt);
    return ae_at(pt[1]);
}

static void ae_set_press(int p) {
    if (ae.press == p) return;
    ae.press = p;
    ae_redraw();
}

/* A tap on a result (a symbol of its own: the tests call it): one that is saved is selected, one that is not is asked for. */
static __attribute__((noinline)) void ae_tap_row(int i) {
    ae_row *w;
    if (i < 0 || i >= ae.nres) return;
    w = &ae.rows[i];
    if (w->state == ROW_BUSY) return;
    if (w->state == ROW_SAVED) {
        if (peq_select(w->file)) {
            peq_state_load(ae.st);
            ae_prep_all();
            ae_redraw();
        }
        return;
    }
    if (!w->file[0]) { /* every name is another file's */
        pod_toast(TR("Storage unavailable"));
        return;
    }
    if (ae.want == 2 || ae.running == 2) return; /* one preset at a time (a list refresh in the background gives way) */
    ae.want = 2, ae.bg = 0;
    snprintf(ae.jobpath, sizeof ae.jobpath, "%s", w->e.path);
    snprintf(ae.jobfile, sizeof ae.jobfile, "%s", w->file);
    ae_stamp(&w->e, ae.jobstamp, sizeof ae.jobstamp);
    w->state = ROW_BUSY;
    ae.frame = ae.spin = 0;
    ae_make(AE_GLYPH, G_RING, 0, AE_ICON_GREY, ae.b_ring);
    ae_prep(i);
    ae_redraw();
    ae_kick();
}

static int ae_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    ae.down = 0;
    ae.pressing = 1;
    if (!e || !ae.view) return RET_OK;
    a = ae_item_of(e);
    ae.down = a + 1, m1_tap_at(&ae.tap, e);
    ae_set_press(a + 1);
    return RET_OK;
}

static int ae_on_up(void *ctx, void *e) {
    int a = ae.down - 1, drag, was = ae.pressing;
    (void)ctx;
    drag = e && !m1_tap_near(&ae.tap, e);
    ae.pressing = 0;
    ae_set_press(0);
    if (!e || !ae.view || drag) {
        ae.down = 0;
        return RET_OK;
    }
    if (ae.phase == P_FAIL && was) { /* a tap on the failure's page: the list again */
        ae.down = 0;
        ae.phase = P_LIST, ae.want = 1, ae.bg = 0;
        ae_layout();
        ae_kick();
        return RET_OK;
    }
    ae.down = 0;
    if (a >= 0 && ae_item_of(e) == a) ae_tap_row(a);
    return RET_OK;
}

static void ae_kb_hide(void) {
    keyboard_show(0);
    ae_layout();
    ae_redraw();
}

static int ae_on_abort(void *ctx, void *e) { /* the scroll_view took the gesture as a drag: the keyboard goes away */
    int drag = ae.pressing;
    (void)ctx;
    (void)e;
    ae.down = ae.pressing = 0;
    ae_set_press(0);
    if (drag && keyboard_shown()) ae_kb_hide();
    return RET_OK;
}

static int ae_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    ae.down = ae.pressing = 0;
    ae_set_press(0);
    return RET_OK;
}

static int ae_on_field(void *ctx, void *e) { /* a tap on the field brings the keyboard back */
    (void)ctx;
    if (e && *(int *)e == EVT_POINTER_UP && ae.phase == P_READY && !keyboard_shown()) {
        keyboard_show(1);
        ae_layout();
        ae_redraw();
    }
    return RET_OK;
}

static int ae_on_fg(void *ctx,
                    void *e) { /* back from the Presets page or the Equalizer page: the record may have changed */
    (void)ctx;
    (void)e;
    if (ae.win && ae.st) {
        peq_state_load(ae.st);
        ae_prep_all();
        ae_redraw();
    }
    return RET_OK;
}

static void ae_on_text(const char *text) {
    if (!ae.win || ae.phase != P_READY || !strcmp(text, ae.typed)) return;
    snprintf(ae.typed, sizeof ae.typed, "%s", text);
    ae.wait = AE_DEBOUNCE;
    ae_kick();
}

static void ae_on_go(void) { /* the action key: put the keyboard away (a failed list is asked for again) */
    if (ae.phase == P_FAIL) {
        ae.phase = P_LIST, ae.want = 1, ae.bg = 0;
        ae_layout();
        ae_kick();
        return;
    }
    ae_kb_hide();
}

static int ae_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    keyboard_detach();
    m1_timer_stop(&ae.timer);
    if (ae.running && pn_job_busy())
        pn_cancel(PN_K_EQ); /* the worker ends by itself; its part file is removed by the next job */
    if (ae.b_down) bitmap_destroy(ae.b_down);
    if (ae.b_check) bitmap_destroy(ae.b_check);
    if (ae.b_ring) bitmap_destroy(ae.b_ring);
    free(ae.rows);
    free(ae.tiles);
    free(ae.st);
    memset(&ae, 0, sizeof ae);
    return RET_OK;
}

/* Is the list older than PN_EQ_MAX_AGE (or has it no date)? A clock that was never set is no judge. */
static __attribute__((noinline)) int ae_stale(void) {
    char b[24];
    unsigned t = 0, now = (unsigned)time((long *)0), i;
    int fd = open(PN_EQ_STAMP, O_RDONLY, 0), n;
    if (now < PN_MIN_EPOCH) return 0;
    if (fd < 0) return 1;
    n = read(fd, b, sizeof b - 1);
    close(fd);
    for (i = 0; n > 0 && i < (unsigned)n && b[i] >= '0' && b[i] <= '9'; ++i) t = t * 10 + (unsigned)(b[i] - '0');
    return !i || t > now || now - t > PN_EQ_MAX_AGE;
}

int autoeq_open(void) {
    if (ae.win) return -1;
    memset(&ae, 0, sizeof ae);
    ae.win = window_open("m1plus_autoeq");
    if (!ae.win) {
        memset(&ae, 0, sizeof ae);
        return -1;
    }
    widget_on(ae.win, EVT_DESTROY, ae_on_destroy, (void *)0);
    m1_bind(ae.win, "btn_return", m1_on_back, (void *)0);
    m1_bind(ae.win, "btn_backtoplayer", m1_on_player, (void *)0);
    ae.list = widget_lookup(ae.win, "se_listview", 1);
    ae.sv = widget_lookup(ae.win, "se_scrollview", 1);
    ae.view = widget_lookup(ae.win, "view_grid", 1);
    ae.status = widget_lookup(ae.win, "label_status", 1);
    ae.field = widget_lookup(ae.win, "kb_field", 1);
    ae.st_title = widget_lookup(ae.win, "label_row_title", 1);
    ae.st_sub = widget_lookup(ae.win, "label_row_sub", 1);
    ae.rows = calloc(AE_MAX, sizeof *ae.rows);
    ae.tiles = calloc(AE_MAX, sizeof *ae.tiles);
    ae.st = calloc(1, sizeof *ae.st);
    ae.b_down = ae_make(AE_GLYPH, G_DOWN, 0, AE_ICON_GREY, (void *)0);
    ae.b_check = ae_make(AE_GLYPH, G_CHECK, 0, 0xff, (void *)0);
    ae.b_ring = ae_make(AE_GLYPH, G_RING, 0, AE_ICON_GREY, (void *)0);
    if (!ae.rows || !ae.tiles || !ae.st || !ae.list || !ae.sv || !ae.view || !ae.status || !ae.field || !ae.st_title ||
        !ae.st_sub || !ae.b_down || !ae.b_check || !ae.b_ring) {
        navigator_back(); /* an asset that is not ours, or no memory: the destroy handler frees what exists */
        return -1;
    }
    if (keyboard_attach(ae.win, TR("Search"), SE_TEXT_X, AE_TEXT_W, SE_CARET_Y, 0, ae_on_text, ae_on_go) != 0) {
        navigator_back();
        return -1;
    }
    widget_on(ae.win, EVT_WINDOW_TO_FG, ae_on_fg, (void *)0);
    widget_on(ae.win, EVT_WINDOW_TO_BG, ae_on_bg, (void *)0);
    widget_on(ae.view, EVT_POINTER_DOWN, ae_on_down, (void *)0);
    widget_on(ae.view, EVT_POINTER_UP, ae_on_up, (void *)0);
    widget_on(ae.view, EVT_POINTER_ABORT, ae_on_abort, (void *)0);
    widget_on(ae.view, EVT_AFTER_PAINT, ae_on_paint, (void *)0);
    widget_on(ae.field, EVT_POINTER_UP, ae_on_field, (void *)0);
    widget_move(ae.list, 0, AE_LIST_Y);
    widget_resize(ae.list, 320, AE_LIST_H);
    widget_resize(ae.sv, 320, AE_LIST_H);
    {
        const char *h = TR("Try Again");
        float f;
        memset(ae.hint, 0, sizeof ae.hint);
        tk_utf8_to_utf16_ex(h, strlen(h) < 40 ? strlen(h) : 40, ae.hint, 23);
        while (ae.hint[ae.hint_n]) ae.hint_n++;
        f = widget_measure_text(ae.st_sub, ae.hint);
        ae.hint_w = (unsigned)(f > 0.0f ? (int)(f + 0.999f) : ae.hint_n * 9);
    }
    peq_state_load(ae.st);
    pn_eq_reset();
    if (!access(PN_EQ_INDEX, F_OK)) {
        ae.phase = P_READY;
        if (ae_stale()) ae.want = 1, ae.bg = 1; /* the old list serves while the new one comes */
    } else {
        ae.phase = P_LIST, ae.want = 1;
        keyboard_show(0);
    }
    m1_show(ae.list, 0);
    m1_show(ae.status, 0);
    ae_layout();
    if (ae.want) ae_kick();
    return 0;
}
