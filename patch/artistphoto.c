/* Artist photos for the local library (docs/modules/artists.md "Artist photos").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * A photo is a picture the user keeps beside the music: artist.jpg|jpeg|png in an album's folder or in the folder above it, or folder.jpg|jpeg|png in the folder above when that
 * folder is named for the artist. A folder only counts when every album the library has under it (itself and below) is by that one artist (the purity check, on a snapshot of the
 * library's albums made by the UI thread before the worker starts). The result is cached in AP_DIR: a<key>-168.jpg, a<key>-44.jpg (written last; empty = no photo), a<key>.src.
 */
#include "offsets.inc"
#include "stock.h"
#include "podcasts.h"
#include "pccover.h"
#include "artistphoto.h"

#define AP_STR_(x) #x
#define AP_STR(x) AP_STR_(x)
#define AP_PATH 300 /* a folder or file path kept on the stack */
#define AP_SEEN 16384 /* the artists-seen table (a power of two over twice AP_LIB_MAX) */
#define AP_MAX_JPEG \
    0x600000 /* a source picture file over this many bytes is passed over (a JPEG: stock's folder-picture limit; a PNG: 1 MiB) */
#define AP_MAX_PNG 0x100000

typedef struct {
    char *dir; /* the album's first track's folder, no trailing slash */
    unsigned key; /* the artist key */
} ap_ent_t;

/* The purity map (folder hash -> the one artist key under it, 0 = more than one): what the snapshot says of every folder that holds an album, or has one below it. */
typedef struct {
    unsigned h, key;
} ap_pe_t;
#define AP_PUR_FILE \
    AP_DIR \
    "/purity" /* the map as the last Home pass left it: a header (magic, entry count, check) and the entries (hash, key) */
#define AP_PUR_SLOTS 32768 /* the table (a power of two) */
#define AP_PUR_MAX 24576 /* entries: three quarters of the table; more and the map is not kept */
#define AP_PUR_MAGIC 0x31555041u
#define AP_RC_MAX 64 /* album folders a re-check looks at */

static struct {
    ap_ent_t *e;
    unsigned n;
    unsigned *seen; /* AP_SEEN keys, 0 empty */
    unsigned *byf; /* entry numbers ordered by folder (worker, on the first job) */
    unsigned *bya; /* ... by artist key, then folder */
    int bad, sorted; /* bad: an add failed, the snapshot is not usable */
    ap_pe_t *pur; /* the purity map being made (AP_PUR_SLOTS), freed once it is saved */
    unsigned npur;
    int purbad; /* it overflowed or there was no memory: no file is kept */
} ap __attribute__((section(".scratch")));
static volatile unsigned ap_ep __attribute__((section(
    ".scratch"))); /* counts the re-checks that changed a photo (the worker bumps it; pages compare it with the value they saw) */

static unsigned ap_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static int ap_fold(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

unsigned ap_key(const char *name) {
    char b[260];
    unsigned n = 0, s = 0, h;
    if (!name) return 0;
    while (*name == ' ' || *name == '\t') ++name;
    for (; *name && n < sizeof b - 1; ++name) b[n++] = (char)ap_fold((unsigned char)*name);
    while (n && (b[n - 1] == ' ' || b[n - 1] == '\t')) --n;
    b[n] = 0;
    if (n > 4 && b[0] == 't' && b[1] == 'h' && b[2] == 'e' && b[3] == ' ') {
        s = 4;
        while (b[s] == ' ' || b[s] == '\t') ++s;
    }
    if (!b[s]) return 0;
    h = cc_fnv(FNV_SEED, b + s);
    return h | !h;
}

static char *ap_path(char *out, unsigned key, const char *suffix) {
    snprintf(out, 72, AP_DIR "/a%08x%s", key, suffix);
    return out;
}

/* ---- showing a photo (UI thread) */

static const char *const ap_seps[] = {" feat. ", " ft. ", " featuring ", " & ", " x ", ", ", "; "};

int ap_lead(const char *name, char *out, unsigned n) {
    unsigned len = ap_len(name), best = len, i, k, s;
    for (s = 0; s < sizeof ap_seps / sizeof *ap_seps; ++s) {
        unsigned l = ap_len(ap_seps[s]);
        for (i = 0; i + l <= len && i < best; ++i) {
            for (k = 0; k < l && ap_fold((unsigned char)name[i + k]) == (unsigned char)ap_seps[s][k]; ++k);
            if (k == l) {
                best = i;
                break;
            }
        }
    }
    if (best >= len || best >= n) return 0;
    memcpy(out, name, best);
    out[best] = 0;
    return 1;
}

static long ap_size(unsigned key, unsigned size) {
    char p[72];
    return cc_file_size(ap_path(p, key, size == AP_HEAD ? "-" AP_STR(AP_HEAD) ".jpg" : "-" AP_STR(AP_LIST) ".jpg"));
}

static void ap_url(char *url, unsigned key, unsigned size) {
    memcpy(url, "file://", 8);
    ap_path(url + 7, key, size == AP_HEAD ? "-" AP_STR(AP_HEAD) ".jpg" : "-" AP_STR(AP_LIST) ".jpg");
}

int ap_lookup(const char *name, unsigned size, char *url) {
    unsigned key = ap_key(name), lk = 0;
    char lead[260];
    long a, b = -1;
    if (!key) return AP_NONE;
    a = ap_size(key, size);
    if (a > 0) {
        ap_url(url, key, size);
        return AP_PHOTO;
    }
    if (ap_lead(name, lead, sizeof lead)) {
        lk = ap_key(lead);
        if (lk == key) lk = 0;
    }
    if (lk) {
        b = ap_size(lk, size);
        if (b > 0) {
            ap_url(url, lk, size);
            return AP_LEAD;
        }
    }
    return a == 0 && (!lk || b == 0) ? AP_NONE : AP_UNKNOWN;
}

void *ap_bitmap(int d, unsigned **px) {
    void *b = bitmap_create_ex(d, d, d * 4, BITMAP_RGBA8888);
    unsigned *p = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
    if (b && (!p || bitmap_get_line_length(b) != (unsigned)d * 4)) {
        if (p) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    *px = p;
    return b;
}

/* The coverage (0..255) of pixel (x, y) of the circle of diameter d: units of 1/16 px; the radius is 8 d, a pixel's centre at (16 x + 8, 16 y + 8). Away from the edge a distance test; on it 8 x 8 samples. */
static unsigned ap_cover(int d, int x, int y) {
    int c = d * 8, dx = x * 16 + 8 - c, dy = y * 16 + 8 - c, i, j, n = 0;
    int q = dx * dx + dy * dy;
    if (q <= (c - 16) * (c - 16)) return 255;
    if (q >= (c + 16) * (c + 16)) return 0;
    for (i = 0; i < 8; ++i)
        for (j = 0; j < 8; ++j) {
            int sx = x * 16 + 2 * i + 1 - c, sy = y * 16 + 2 * j + 1 - c;
            n += sx * sx + sy * sy <= c * c;
        }
    return (unsigned)((n * 255 + 32) / 64);
}

void ap_circle(unsigned *px, int d) {
    int x, y;
    for (y = 0; y < d; ++y)
        for (x = 0; x < d; ++x) px[y * d + x] = (px[y * d + x] & 0xffffffu) | ap_cover(d, x, y) << 24;
}

#define AP_CARD 0x333333u /* the album no-cover tile's colour (tools/mod_icons.py: the stock tile) */
#define AP_INK 0x8c /* the glyph's colour: the brightest channel of its ink */

void *ap_placeholder(void *win, int d) {
    unsigned *px, *gl;
    int gs = d * 52 / 100, i, x, y, o = (d - gs) / 2;
    void *b = ap_bitmap(d, &px);
    if (!b) return b;
    for (i = 0; i < d * d; ++i) px[i] = 0xff000000u | AP_CARD;
    gl = calloc((unsigned)(gs * gs), 4);
    if (gl && cc_decode(win, AP_GLYPH, 1, (unsigned)gs, 1, gl))
        for (y = 0; y < gs; ++y)
            for (x = 0; x < gs; ++x) {
                unsigned c = gl[y * gs + x], m = c & 255, cov, ch = 0, sh;
                if ((c >> 8 & 255) > m) m = c >> 8 & 255;
                if ((c >> 16 & 255) > m) m = c >> 16 & 255;
                if (!m) continue;
                cov = m * 255 / AP_INK;
                if (cov > 255) cov = 255;
                for (sh = 0; sh < 24; sh += 8)
                    ch |= (((c >> sh & 255) + (AP_CARD >> sh & 255) * (255 - cov) / 255) & 255) << sh;
                px[(y + o) * d + x + o] = 0xff000000u | ch;
            }
    free(gl);
    ap_circle(px, d);
    bitmap_unlock_buffer(b);
    return b;
}

/* ---- the snapshot (UI thread) */

int ap_lib_ok(void) { return !ap.bad; }

void ap_lib_free(void) {
    unsigned i;
    for (i = 0; ap.e && i < ap.n; ++i) free(ap.e[i].dir);
    free(ap.e);
    free(ap.seen);
    free(ap.byf);
    free(ap.bya);
    free(ap.pur);
    memset(&ap, 0, sizeof ap);
}

static void ap_pur_add(const char *dir, unsigned key);

int ap_lib_add(const char *track, unsigned key) {
    unsigned slash = ap_len(track);
    char *d;
    if (ap.bad) return 0; /* (key 0: an album with no artist, which makes every folder it is in impure) */
    while (slash && track[slash - 1] != '/') --slash;
    if (!ap.e) {
        ap.e = calloc(AP_LIB_MAX, sizeof *ap.e);
        ap.seen = calloc(AP_SEEN, sizeof *ap.seen);
    }
    if (!ap.e || !ap.seen || ap.n >= AP_LIB_MAX || slash < 2) {
        ap.bad = 1;
        return 0;
    }
    d = calloc(1, slash);
    if (!d) {
        ap.bad = 1;
        return 0;
    }
    memcpy(d, track, slash - 1);
    ap.e[ap.n].dir = d, ap.e[ap.n].key = key;
    ++ap.n;
    ap_pur_add(d, key);
    return 1;
}

/* A folder's hash (the map's key): FNV of its path, never 0. */
static unsigned ap_hf(unsigned h) { return h | !h; }

static int ap_pur_put(unsigned h, unsigned key) {
    unsigned i;
    for (i = h & (AP_PUR_SLOTS - 1); ap.pur[i].h; i = (i + 1) & (AP_PUR_SLOTS - 1))
        if (ap.pur[i].h == h) {
            if (ap.pur[i].key != key) ap.pur[i].key = 0; /* two artists (or an untagged album) under it */
            return 1;
        }
    if (ap.npur >= AP_PUR_MAX) return 0;
    ap.pur[i].h = h, ap.pur[i].key = key;
    ++ap.npur;
    return 1;
}

/* The album folder and every folder above it, with the album's artist. */
static void ap_pur_add(const char *dir, unsigned key) {
    unsigned h = FNV_SEED, i;
    if (ap.purbad) return;
    if (!ap.pur) ap.pur = calloc(AP_PUR_SLOTS, sizeof *ap.pur);
    if (!ap.pur) {
        ap.purbad = 1;
        return;
    }
    for (i = 0;; ++i) {
        char c = dir[i];
        if (((c == '/' && i) || !c) && !ap_pur_put(ap_hf(h * 16777619u), key)) {
            ap.purbad = 1;
            return;
        }
        if (!c) break;
        h = (h ^ (unsigned char)c) * 16777619u;
    }
}

static unsigned ap_pur_sum(const ap_pe_t *e, unsigned n) {
    unsigned i, c = n;
    for (i = 0; i < n; ++i) c = (c << 1 | c >> 31) ^ (e[i].h * 3 + e[i].key);
    return c;
}

void ap_lib_drop(void) { unlink(AP_PUR_FILE); }

/* The Home pass has the whole snapshot: its purity map goes to AP_PUR_FILE (tmp, then rename) for the re-check of one artist, which has no database access on the worker. An unusable map removes the old file. */
int ap_lib_save(void) {
    char tmp[sizeof AP_PUR_FILE + 8];
    unsigned i, n = 0, hdr[3];
    void *f;
    if (ap.bad || ap.purbad || !ap.pur || !ap.npur) {
        ap_lib_drop();
        return 0;
    }
    for (i = 0; i < AP_PUR_SLOTS;
         ++i) /* compacted in place: the order does not matter, the reader makes its own table */
        if (ap.pur[i].h) ap.pur[n++] = ap.pur[i];
    mkdir(CARD_DIR, 0755);
    mkdir(AP_DIR, 0755);
    snprintf(tmp, sizeof tmp, "%s.tmp", AP_PUR_FILE);
    f = fopen(tmp, "w");
    if (!f) return 0;
    hdr[0] = AP_PUR_MAGIC, hdr[1] = n, hdr[2] = ap_pur_sum(ap.pur, n);
    if (fwrite(hdr, sizeof hdr, 1, f) == 1 && fwrite(ap.pur, sizeof *ap.pur, n, f) == n) {
        fclose(f);
        if (rename(tmp, AP_PUR_FILE))
            unlink(tmp);
        else
            return 1;
    } else {
        fclose(f);
        unlink(tmp);
    }
    ap_lib_drop();
    return 0;
}

int ap_first(unsigned key) {
    unsigned i;
    if (!ap.seen) return 1;
    for (i = key & (AP_SEEN - 1); ap.seen[i]; i = (i + 1) & (AP_SEEN - 1))
        if (ap.seen[i] == key) return 0;
    ap.seen[i] = key;
    return 1;
}

/* ---- discovery (worker) */

static int ap_cmp_f(unsigned a, unsigned b) {
    int d = strcmp(ap.e[a].dir, ap.e[b].dir);
    return d ? d : a < b ? -1 : a > b;
}

static int ap_cmp_a(unsigned a, unsigned b) {
    if (ap.e[a].key != ap.e[b].key) return ap.e[a].key < ap.e[b].key ? -1 : 1;
    return ap_cmp_f(a, b);
}

static void ap_sort(void) {
    unsigned i;
    if (ap.sorted) return;
    ap.sorted = 1;
    ap.byf = calloc(ap.n ? ap.n : 1, sizeof(unsigned));
    ap.bya = calloc(ap.n ? ap.n : 1, sizeof(unsigned));
    if (!ap.byf || !ap.bya) {
        ap.bad = 1;
        return;
    }
    for (i = 0; i < ap.n; ++i) ap.byf[i] = ap.bya[i] = i;
    cc_heapsort(ap.byf, ap.n, ap_cmp_f);
    cc_heapsort(ap.bya, ap.n, ap_cmp_a);
}

static int ap_starts(const char *s, const char *p) {
    while (*p && *s == *p) ++s, ++p;
    return !*p;
}

/* Every album the snapshot has in dir (the folder itself or below it) is by key. */
static int ap_pure(const char *dir, unsigned key) {
    unsigned lo = 0, hi = ap.n, i, n = ap_len(dir);
    int seen = 0;
    while (lo < hi) { /* the first folder not before dir */
        unsigned mid = (lo + hi) / 2;
        if (strcmp(ap.e[ap.byf[mid]].dir, dir) < 0)
            lo = mid + 1;
        else
            hi = mid;
    }
    for (i = lo; i < ap.n; ++i) {
        const ap_ent_t *e = &ap.e[ap.byf[i]];
        if (!ap_starts(e->dir, dir)) break;
        if (e->dir[n] && e->dir[n] != '/') continue; /* "Music/Abba - Live" is not under "Music/Abba" */
        if (e->key != key) return 0;
        seen = 1;
    }
    return seen;
}

static const char *ap_base(const char *p) {
    const char *b = p;
    for (; *p; ++p)
        if (*p == '/') b = p + 1;
    return b;
}

/* A disc folder of a multi-disc album: CD1, CD 2, Disc 1, Disk2, disc-03 (any case). */
static int ap_disc(const char *name) {
    unsigned n = 0, digits = 0;
    char c;
    if (ap_fold((unsigned char)name[0]) == 'c' && ap_fold((unsigned char)name[1]) == 'd')
        n = 2;
    else if ((ap_fold((unsigned char)name[0]) == 'd' && ap_fold((unsigned char)name[1]) == 'i') &&
             (ap_fold((unsigned char)name[2]) == 's') &&
             (ap_fold((unsigned char)name[3]) == 'c' || ap_fold((unsigned char)name[3]) == 'k'))
        n = 4;
    else
        return 0;
    while (name[n] == ' ' || name[n] == '_' || name[n] == '-' || name[n] == '.') ++n;
    for (; (c = name[n]) >= '0' && c <= '9'; ++n) ++digits;
    return digits && digits <= 3 && !name[n];
}

/* Cut dir back to its parent. 0 when there is none (a top-level name). */
static int ap_up(char *dir) {
    unsigned n = ap_len(dir);
    while (n && dir[n - 1] != '/') --n;
    if (n < 2) return 0;
    dir[n - 1] = 0;
    return 1;
}

/* dir/<stem>.jpg|.jpeg|.png (any case; a regular file; .jpg before .jpeg before .png, equal ranks by name) into out: the first candidate after the one in prev (rank in *prank,
 * name in pname; pname[0] 0 = none yet), which is updated to the one found. 1 when found. */
static int ap_find(const char *dir, const char *stem, char *out, int *prank, char *pname) {
    static const char *const ext[3] = {".jpg", ".jpeg", ".png"};
    char want[40], best[256];
    int rank = 3, r;
    void *d = opendir(dir);
    char *ent;
    if (!d) return 0;
    while ((ent = readdir(d)) != (char *)0) {
        const char *name = ent + 11; /* struct dirent: d_type at 10, d_name at 11 */
        if (ent[10] != 8 || ap_len(name) >= sizeof best) continue;
        for (r = 0; r < 3; ++r) {
            snprintf(want, sizeof want, "%s%s", stem, ext[r]);
            if (cc_nocase(name, want)) continue;
            if (pname[0] && (r < *prank || (r == *prank && strcmp(name, pname) <= 0))) break; /* already tried */
            if (r < rank || (r == rank && strcmp(name, best) < 0)) {
                rank = r;
                memcpy(best, name, ap_len(name) + 1);
            }
            break;
        }
    }
    closedir(d);
    if (rank == 3) return 0;
    *prank = rank;
    memcpy(pname, best, ap_len(best) + 1);
    snprintf(out, AP_PATH, "%s/%s", dir, best);
    return 1;
}

static void ap_empty_marker(unsigned key) {
    char p[72];
    void *f;
    unlink(ap_path(p, key, "-" AP_STR(AP_HEAD) ".jpg"));
    unlink(ap_path(p, key, ".src"));
    f = fopen(ap_path(p, key, "-" AP_STR(AP_LIST) ".jpg"), "w");
    if (f) fclose(f);
}

/* .src: where the photo came from (the path, its size and modification time), so a later check can tell a changed or removed file. */
static void ap_write_src(unsigned key, const char *src) {
    char p[72], t[72], b[AP_PATH + 80];
    unsigned st[40], n;
    void *f;
    memset(st, 0, sizeof st);
    if (__xstat(3, src, st)) return;
    n = (unsigned)snprintf(b, sizeof b, "m1plus artist 1\nsrc: %s\nsize: %u\nmtime: %u\nend\n", src, st[0x30 / 4],
                           st[0x40 / 4]);
    ap_path(p, key, ".src"), ap_path(t, key, ".src.tmp");
    f = fopen(t, "w");
    if (!f) return;
    if (fwrite(b, n, 1, f) == 1) {
        fclose(f);
        if (rename(t, p)) unlink(t);
    } else {
        fclose(f);
        unlink(t);
    }
}

/* The source picture at both sizes, each a square (cropped by pv_square), made from one decode of it (the 44 px file from the 168 px one). 1 when both files are published (the -44 file last). */
static int ap_make(const char *src, unsigned key) {
    char t168[72], t44[72], p168[72], p44[72];
    unsigned w, h, sof;
    long size = cc_file_size(src);
    int kind = pc_pic_info(src, &w, &h, &sof), r;
    if (!((kind == 1 && (sof == 0xc0 || sof == 0xc1 || sof == 0xc2) && size > 0 && size <= AP_MAX_JPEG) ||
          (kind == 2 && size > 0 && size <= AP_MAX_PNG)))
        return 0;
    ap_path(t168, key, "-" AP_STR(AP_HEAD) ".jpg.tmp"), ap_path(t44, key, "-" AP_STR(AP_LIST) ".jpg.tmp");
    ap_path(p168, key, "-" AP_STR(AP_HEAD) ".jpg"), ap_path(p44, key, "-" AP_STR(AP_LIST) ".jpg");
    r = pv_square(src, t168, AP_HEAD); /* a square, whatever the picture's shape */
    if (r != 1 || cc_file_size(t168) <= 0) {
        unlink(t168);
        return 0;
    }
    r = pv_cover(t168, t44, AP_LIST);
    if (r == -1) r = pv_shrink(t168, t44);
    if (r != 1 || cc_file_size(t44) <= 0) {
        unlink(t168), unlink(t44);
        return 0;
    }
    if (rename(t168, p168)) {
        unlink(t168), unlink(t44);
        return 0;
    }
    ap_write_src(key, src);
    if (rename(t44, p44)) {
        unlink(t44), unlink(p168);
        return 0;
    }
    return 1;
}

/* How a folder's purity is judged: the Home pass's snapshot (mode 0), the saved map (mode 1: tab, mask), or not at all (mode 2: only the album folders themselves are looked in). */
typedef struct {
    int mode;
    const ap_pe_t *tab;
    unsigned mask;
} ap_orc_t;

static int ap_judge(const ap_orc_t *o, const char *dir, unsigned key) {
    unsigned h, i;
    if (o->mode == 0) return ap_pure(dir, key);
    if (o->mode == 2) return 1;
    h = ap_hf(cc_fnv(FNV_SEED, dir));
    for (i = h & o->mask; o->tab[i].h; i = (i + 1) & o->mask)
        if (o->tab[i].h == h) return key && o->tab[i].key == key;
    return 0;
}

/* The photo of the artist whose albums' folders are dirs[0..n) (sorted): tier 0 artist.* in the folder above the album folder, 1 artist.* in the album folder, 2 folder.* above it
 * when that folder carries the artist's name. A disc folder is stepped over first. 1 when a photo was made. */
static int ap_walk(unsigned key, const char *const *dirs, unsigned n, const ap_orc_t *o) {
    unsigned i;
    int tier, rank;
    char prev[AP_PATH], dir[AP_PATH], src[AP_PATH], tried[256];
    for (tier = 0; tier < 3; ++tier) {
        if (o->mode == 2 && tier != 1) continue;
        prev[0] = 0;
        for (i = 0; i < n; ++i) {
            const char *d = dirs[i];
            if (ap_len(d) >= sizeof dir) continue;
            memcpy(dir, d, ap_len(d) + 1);
            if (ap_disc(ap_base(dir)) && !ap_up(dir)) continue;
            if (tier != 1 && !ap_up(dir)) continue; /* the folder above (tier 1 stays in the album folder) */
            if (!strcmp(dir, prev)) continue;
            memcpy(prev, dir, ap_len(dir) + 1);
            if (!ap_judge(o, dir, key)) continue;
            if (tier == 2 && ap_key(ap_base(dir)) != key) continue;
            tried[0] = 0, rank = 0;
            while (ap_find(dir, tier == 2 ? "folder" : "artist", src, &rank,
                           tried)) /* a picture that does not decode leaves the others of the folder to try */
                if (ap_make(src, key)) return 1;
        }
    }
    return 0;
}

/* The snapshot's albums of key. */
static int ap_discover(unsigned key) {
    unsigned lo = 0, hi = ap.n, i, n;
    const char **dirs;
    ap_orc_t o;
    int r;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (ap.e[ap.bya[mid]].key < key)
            lo = mid + 1;
        else
            hi = mid;
    }
    for (n = 0; lo + n < ap.n && ap.e[ap.bya[lo + n]].key == key; ++n);
    dirs = calloc(n ? n : 1, sizeof *dirs);
    if (!dirs) {
        ap.bad = 1; /* no memory: no marker, the next pass retries */
        return 0;
    }
    for (i = 0; i < n; ++i) dirs[i] = ap.e[ap.bya[lo + i]].dir;
    memset(&o, 0, sizeof o);
    r = ap_walk(key, dirs, n, &o);
    free(dirs);
    return r;
}

void ap_job(const char *track, unsigned key, int force, const volatile int *cancelled) {
    char p44[72], pick[72], try[72];
    int found;
    void *f;
    if (!key || ap.bad || access(track, F_OK))
        return; /* storage gone, or the snapshot is unusable: no marker, the next pass retries */
    ap_path(p44, key, "-" AP_STR(AP_LIST) ".jpg"), ap_path(pick, key, ".pick"), ap_path(try, key, ".try");
    if (!access(pick, F_OK) && !access(p44, F_OK))
        return; /* a manual pick (reserved): never overwritten by an automatic build */
    if (!force && !access(p44, F_OK)) return;
    if (!access(try, F_OK)) { /* the last attempt on this artist died or hung: no photo until a rebuild */
        ap_empty_marker(key);
        unlink(try);
        return;
    }
    f = fopen(try, "w");
    if (f) fclose(f);
    ap_sort();
    found = ap.bad ? 0 : ap_discover(key);
    unlink(try);
    if (ap.bad || *cancelled) return;
    if (!found) ap_empty_marker(key);
}

/* ---- the re-check of one artist (worker; an artist's page asks for it when it opens) */

/* The line `name` of a text record, as a pointer to its value, or NULL. */
static const char *ap_field(const char *b, const char *name) {
    while (*b) {
        if (ap_starts(b, name)) return b + ap_len(name);
        while (*b && *b != '\n') ++b;
        if (*b) ++b;
    }
    return (const char *)0;
}

static unsigned ap_num(const char *s) {
    unsigned v = 0;
    for (; *s >= '0' && *s <= '9'; ++s) v = v * 10 + (unsigned)(*s - '0');
    return v;
}

/* The source the artist's photo was made from, its size and modification time then (.src). 0 when the record is not there or not complete. */
static int ap_src_read(unsigned key, char *path, unsigned n, unsigned *size, unsigned *mtime) {
    char p[72], b[AP_PATH + 120];
    const char *s, *z, *m;
    unsigned len, i;
    void *f = fopen(ap_path(p, key, ".src"), "rb");
    if (!f) return 0;
    len = (unsigned)fread(b, 1, sizeof b - 1, f);
    fclose(f);
    b[len] = 0;
    s = ap_field(b, "src: "), z = ap_field(b, "size: "), m = ap_field(b, "mtime: ");
    if (!s || !z || !m || !ap_field(b, "end\n")) return 0;
    for (i = 0; s[i] && s[i] != '\n' && i < n - 1; ++i) path[i] = s[i];
    path[i] = 0;
    *size = ap_num(z), *mtime = ap_num(m);
    return i > 0;
}

/* The purity map the last Home pass saved, as a hash table (AP_PUR_FILE); NULL when it is missing, cut or does not check. */
static ap_pe_t *ap_load_map(unsigned *mask) {
    unsigned hdr[3], n, slots = 16, i, j;
    long size = cc_file_size(AP_PUR_FILE);
    ap_pe_t *e, *t;
    void *f;
    if (size <= 12 || size > 12 + 8 * AP_PUR_MAX || (size - 12) % 8) return (ap_pe_t *)0;
    n = (unsigned)(size - 12) / 8;
    e = calloc(n, sizeof *e);
    f = e ? fopen(AP_PUR_FILE, "rb") : (void *)0;
    if (!f || fread(hdr, sizeof hdr, 1, f) != 1 || fread(e, sizeof *e, n, f) != n || hdr[0] != AP_PUR_MAGIC ||
        hdr[1] != n || hdr[2] != ap_pur_sum(e, n)) {
        if (f) fclose(f);
        free(e);
        return (ap_pe_t *)0;
    }
    fclose(f);
    while (slots < 2 * n) slots *= 2;
    t = calloc(slots, sizeof *t);
    for (i = 0; t && i < n; ++i) {
        if (!e[i].h) continue;
        for (j = e[i].h & (slots - 1); t[j].h && t[j].h != e[i].h; j = (j + 1) & (slots - 1));
        if (t[j].h && t[j].key != e[i].key) e[i].key = 0;
        t[j] = e[i];
    }
    free(e);
    *mask = slots - 1;
    return t;
}

/* One artist: a photo is looked for again when it has none (the empty marker, or no file yet), or its source is gone or no longer the file the photo was made from (size or modification time).
 * Unchanged is one stat and nothing else. dirs: the track paths of the artist's albums, one per line. The purity of the folders above an album folder comes from the saved map; without it only the album
 * folders themselves are looked in and nothing is ever concluded from that (no marker, no removal). */
void ap_recheck_job(const char *tracks, unsigned key, const volatile int *cancelled) {
    char p44[72], pick[72], try[72], old[AP_PATH], *copy, *c, *dirs[AP_RC_MAX];
    unsigned n = 0, i, j, osz = 0, omt = 0, mask = 0, st[40];
    long sz;
    int found = 0, full;
    ap_pe_t *tab;
    ap_orc_t o;
    void *f;
    if (!key || !tracks || !*tracks || !(copy = strdup(tracks))) return;
    for (c = copy; *c && n < AP_RC_MAX;) {
        char *e = c, *sl, more;
        while (*e && *e != '\n') ++e;
        more = *e, *e = 0;
        if (!n && access(c, F_OK)) { /* storage gone: nothing is concluded */
            free(copy);
            return;
        }
        for (sl = e; sl > c && *sl != '/'; --sl);
        if (sl > c) *sl = 0, dirs[n++] = c;
        c = more ? e + 1 : e;
    }
    for (i = 1; i < n; ++i) { /* sorted, as the walk skips a folder it has just seen */
        char *d = dirs[i];
        for (j = i; j && strcmp(dirs[j - 1], d) > 0; --j) dirs[j] = dirs[j - 1];
        dirs[j] = d;
    }
    ap_path(p44, key, "-" AP_STR(AP_LIST) ".jpg"), ap_path(pick, key, ".pick"), ap_path(try, key, ".try");
    sz = cc_file_size(p44);
    if (!n || (!access(pick, F_OK) && sz >= 0)) { /* a manual pick (reserved): never replaced */
        free(copy);
        return;
    }
    if (!access(try, F_OK)) { /* the last attempt on this artist died or hung: no photo until a rebuild */
        ap_empty_marker(key);
        unlink(try);
        if (sz > 0) ++ap_ep;
        free(copy);
        return;
    }
    old[0] = 0;
    if (sz > 0) {
        memset(st, 0, sizeof st);
        if (!ap_src_read(key, old, sizeof old, &osz, &omt) ||
            (!__xstat(3, old, st) && st[0x30 / 4] == osz && st[0x40 / 4] == omt)) {
            free(copy); /* (no record to compare with, or the same file) */
            return;
        }
    }
    f = fopen(try, "w");
    if (f) fclose(f);
    tab = ap_load_map(&mask);
    full = tab != (ap_pe_t *)0;
    memset(&o, 0, sizeof o);
    o.mode = full ? 1 : 2, o.tab = tab, o.mask = mask;
    found = ap_walk(key, (const char *const *)dirs, n, &o);
    if (!found && sz > 0 && !*cancelled && !access(old, F_OK))
        found = ap_make(old, key); /* the file is still there: changed in place, and still the photo */
    unlink(try);
    free(tab);
    free(copy);
    if (*cancelled) return;
    if (found)
        ++ap_ep;
    else if (full && sz != 0) {
        ap_empty_marker(key); /* nothing found where the whole library was weighed: no photo (a removed source) */
        if (sz > 0) ++ap_ep;
    }
}

unsigned ap_epoch(void) { return ap_ep; }

int ap_recheck(const char *name, const char *tracks) {
    unsigned key = ap_key(name);
    if (!key || key == ap_key("Unknown Artist") || !tracks || !*tracks) return 0;
    if (!cc_build_open(1, CC_MISSING))
        return 0; /* the worker is busy (Home's pass, Cover Flow, ...): the Home pass will cover it */
    if (cc_build_add_recheck(tracks, key) != 1) {
        cc_build_stop();
        return 0;
    }
    return cc_build_start();
}
