/* M1+ Music Internet Radio: the engine (docs/modules/radio.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The playlist (.m3u / .pls) and CSV parsers, the percent-escape and the favourites file follow q2-pod's patch/radio.c (https://github.com/ubcprogrammers/q2-pod, MIT; README.md
 * acknowledges it). Playing is stock's: hciplayer (MPlayer) opens the stream through mcl_tidalStartPlayer, so the DAC, the wheel volume and the screen-off playback are stock's own.
 * The directory fetch is a libcurl worker like the Podcasts one.
 *
 *   playing   rd_play: the DAC readied as stock's start_player / q2-pod's dac_take do, then mcl_tidalStartPlayer. A table-driven state machine (rd_step) takes events from the taps, the
 *             mclStartPlayer hook and rd_poll, which reconciles with stock's own status (running byte, socket fd, mclGetPlayStatus, mclGetHciplayerStatus) every 500 ms while a station
 *             connects, plays or is paused, and holds the standby timers.
 *   hand-over mclStartPlayer's hook (rd_start_player) stops the stream (mclStop) before any local track starts; the radio's own start stops local music first.
 *   output    save_stop_player / save_start_player hooks (rd_save_stop, rd_save_start): an output change under a running station restarts it (Reroute) instead of stock restarting the old local track.
 *   directory one detached-free worker (rd_fetch), never beside a podcast refresh, search or download; the UI polls rd_fetch_state and takes the answer.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "curlopts.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "pcjson.h"
#include "pcopml.h"
#include "pcnet.h"
#include "peqout.h"
#include "pccover.h"
#include "radio.h"

#define RD_NAME_KEEP 120

/* ---------------------------------------------------------------------------
 * Strings
 */
/* src into dst (n bytes), cut before a UTF-8 continuation byte; invalid UTF-8 becomes '?'. */
static void rd_copy(char *dst, unsigned n, const char *src) {
    unsigned o = 0, i = 0;
    if (!n) return;
    while (src[i] && o + 1 < n) {
        unsigned char c = (unsigned char)src[i];
        unsigned len = c < 0x80                ? 1
                       : c >= 0xc2 && c < 0xe0 ? 2
                       : c >= 0xe0 && c < 0xf0 ? 3
                       : c >= 0xf0 && c < 0xf5 ? 4
                                               : 0,
                 k;
        if (c < 0x20 || c == 0x7f) c = ' ', len = 1;
        for (k = 1; len > 1 && k < len; ++k)
            if (((unsigned char)src[i + k] & 0xc0) != 0x80) len = 0; /* (a NUL ends the check too) */
        if (!len) {
            dst[o++] = '?', ++i;
            continue;
        }
        if (o + len >= n) break;
        if (len == 1) {
            dst[o++] = (char)c, ++i;
            continue;
        }
        for (k = 0; k < len; ++k) dst[o++] = src[i++];
    }
    dst[o] = 0;
}

static int rd_prefix_ci(const char *s, const char *p) { return strncasecmp(s, p, strlen(p)) == 0; }

/* The line at s cut off; returns the next one's start. */
static char *rd_line(char *s) {
    while (*s && *s != '\n' && *s != '\r') ++s;
    if (*s) *s++ = 0;
    return s;
}

/* ---------------------------------------------------------------------------
 * The parsers
 */
int rd_playlist(char *buf, unsigned *name, unsigned *url, unsigned *info, int max) {
    int n = 0;
    char *end = buf + strlen(buf);
    unsigned named = 0, meta = 0; /* 1 + the pending #EXTINF name's offset; 1 + the pending info's */
    char *s, *next, *first = buf; /* offsets stay relative to buf; only the scan skips a BOM */
    if ((unsigned char)buf[0] == 0xef && (unsigned char)buf[1] == 0xbb && (unsigned char)buf[2] == 0xbf) first += 3;
    for (s = first; *s; s = next) {
        char *v, *comma;
        int file;
        next = rd_line(s);
        while (*s == ' ' || *s == '\t') ++s;
        v = strchr(s, '=');
        comma = strchr(s, ',');
        file = v && rd_prefix_ci(s, "File");
        if (rd_prefix_ci(s, "#EXTINF:"))
            named = comma && comma[1] ? (unsigned)(comma + 1 - buf) + 1 : 0;
        else if (rd_prefix_ci(s, "#M1+:"))
            meta = (unsigned)(s + 5 - buf) + 1;
        else if (n < max && *s != '#' && !(v && rd_prefix_ci(s, "Title")) && strstr(file ? v : s, "://")) {
            url[n] = (unsigned)((file ? v + 1 : s) - buf);
            name[n] = named ? named - 1 : url[n];
            info[n] = meta ? meta - 1 : 0;
            named = meta = 0, ++n;
        }
    }
    for (s = first; s < end; s += strlen(s) + 1) { /* TitleN= names FileN= */
        char *v;
        int i;
        while (*s == ' ' || *s == '\t') ++s;
        v = strchr(s, '=');
        if (!v || !rd_prefix_ci(s, "Title") || v <= s + 5 || !v[1]) continue;
        for (i = 0; i < n; ++i) {
            char *f = buf + url[i];
            while (f > buf && f[-1]) --f;
            while (*f == ' ' || *f == '\t') ++f;
            if (rd_prefix_ci(f, "File") && !strncasecmp(f + 4, s + 5, (unsigned)(v - s - 4)))
                name[i] = (unsigned)(v + 1 - buf); /* through the '=': FileN= for TitleN= */
        }
    }
    return n;
}

/* The CSV record at *pp, decoded in place into NUL-terminated fields (offsets from base in off[0..max)); *pp moves past its line end. The write point never passes the read point. Returns
 * the field count, 0 at the end of the text. */
static int rd_csv_record(char **pp, char *base, unsigned *off, int max) {
    char *r = *pp, *w;
    int n = 0;
    while (*r == '\n' || *r == '\r') ++r;
    w = r;
    if (!*r) {
        *pp = r;
        return 0;
    }
    for (;;) {
        char end;
        if (n < max) off[n] = (unsigned)(w - base);
        if (*r == '"') {
            ++r;
            while (*r) {
                if (*r == '"') {
                    if (r[1] == '"') {
                        *w++ = '"', r += 2;
                        continue;
                    }
                    ++r;
                    break;
                }
                *w++ = *r++;
            }
        }
        while (*r && *r != ',' && *r != '\n' && *r != '\r') *w++ = *r++;
        end = *r;
        *w++ = 0;
        ++n;
        if (end == ',') {
            ++r;
            continue;
        }
        if (end == '\r' && r[1] == '\n') ++r;
        if (end) ++r;
        break;
    }
    *pp = r;
    return n;
}

static void rd_trim(char *s) {
    unsigned n = (unsigned)strlen(s), a = 0;
    while (n && (s[n - 1] == ' ' || s[n - 1] == '\t')) s[--n] = 0;
    while (s[a] == ' ' || s[a] == '\t') ++a;
    if (a) memmove(s, s + a, n - a + 1);
}

int rd_stations(char *src, unsigned len, char *pool, unsigned size, unsigned *name, unsigned *url, unsigned *info,
                int max) {
    unsigned f[64];
    char *p = src;
    int n = 0, cols = rd_csv_record(&p, src, f, 64), c_name = -1, c_url = -1, c_res = -1, c_country = -1, c_codec = -1,
        c_rate = -1, c_fav = -1, i;
    unsigned o = 1; /* offset 0 is "no info": the pool starts with a NUL */
    (void)len;
    if (cols > 64) cols = 64;
    for (i = 0; i < cols; ++i) {
        const char *h = src + f[i];
        if (!strcmp(h, "name"))
            c_name = i;
        else if (!strcmp(h, "url"))
            c_url = i;
        else if (!strcmp(h, "url_resolved"))
            c_res = i;
        else if (!strcmp(h, "country"))
            c_country = i;
        else if (!strcmp(h, "codec"))
            c_codec = i;
        else if (!strcmp(h, "bitrate"))
            c_rate = i;
        else if (!strcmp(h, "favicon"))
            c_fav = i;
    }
    if (c_name < 0 || (c_url < 0 && c_res < 0) || size < 2) return 0;
    pool[0] = 0;
    while (n < max) {
        int k = rd_csv_record(&p, src, f, 64);
        const char *nm, *u, *country, *codec, *rate, *fav;
        unsigned need, ln, lu, lc;
        if (!k) break;
        if (k < cols || k > 64) continue; /* a short or odd row (the answer was cut) is skipped */
        nm = src + f[c_name];
        u = c_res >= 0 && src[f[c_res]] ? src + f[c_res] : c_url >= 0 ? src + f[c_url] : "";
        country = c_country >= 0 ? src + f[c_country] : "";
        codec = c_codec >= 0 ? src + f[c_codec] : "";
        rate = c_rate >= 0 ? src + f[c_rate] : "";
        fav = c_fav >= 0 ? src + f[c_fav] : "";
        if (strlen(fav) > RD_FAV_MAX || (strncasecmp(fav, "http://", 7) && strncasecmp(fav, "https://", 8))) fav = "";
        if (!*nm || !*u || !strstr(u, "://") || strlen(u) > 1000) continue;
        ln = (unsigned)strlen(nm), lu = (unsigned)strlen(u),
        lc = (unsigned)(strlen(country) + strlen(codec) + strlen(rate) + strlen(fav)) + 4;
        if (ln > RD_NAME_KEEP) ln = RD_NAME_KEEP;
        need = ln + 1 + lu + 1 + lc + 1;
        if (o + need > size) break;
        name[n] = o;
        rd_copy(pool + o, ln + 1, nm), rd_trim(pool + o);
        if (!pool[o]) continue; /* a name that was only spaces */
        o += (unsigned)strlen(pool + o) + 1;
        url[n] = o;
        memcpy(pool + o, u, lu + 1);
        o += lu + 1;
        info[n] = o;
        {
            char c1[64], c2[32], c3[16];
            rd_copy(c1, sizeof c1, country), rd_copy(c2, sizeof c2, codec), rd_copy(c3, sizeof c3, rate);
            o += (unsigned)snprintf(pool + o, size - o, "%s\t%s\t%s\t%s", c1, c2, c3, fav) + 1;
        }
        ++n;
    }
    return n;
}

int rd_choices(char *buf, unsigned *name, unsigned *key, unsigned *count, int max, int coded) {
    unsigned f[8];
    char *p = buf;
    int n = 0, k = rd_csv_record(&p, buf, f, 8); /* past the header */
    (void)k;
    while (n < max && (k = rd_csv_record(&p, buf, f, 8)) > 0) {
        char *nm;
        if (k < 2 || k > 8) continue;
        nm = buf + f[0];
        rd_trim(nm);
        if (!*nm || (buf[f[k - 1]] == '0' && !buf[f[k - 1] + 1])) continue; /* (no name, or no stations) */
        name[n] = f[0];
        key[n] = coded && k >= 3 && buf[f[1]] ? f[1] : f[0];
        count[n] = f[k - 1];
        ++n;
    }
    return n;
}

void rd_url_escape(const char *s, char *out, unsigned n) {
    static const char hex[] = "0123456789ABCDEF";
    for (; *s && n > 3; ++s) {
        unsigned char c = (unsigned char)*s;
        if (((c | 32) >= 'a' && (c | 32) <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' ||
            c == '~')
            *out++ = (char)c, --n;
        else
            *out++ = '%', *out++ = hex[c >> 4], *out++ = hex[c & 15], n -= 3;
    }
    *out = 0;
}

void rd_caption(const char *info, char *out, unsigned n) {
    char country[64], codec[32], rate[16];
    unsigned o = 0, i;
    const char *p = info;
    const char *parts[3] = {country, codec, rate};
    char *dst[3] = {country, codec, rate};
    unsigned cap[3] = {sizeof country, sizeof codec, sizeof rate};
    if (!n) return;
    for (i = 0; i < 3; ++i) {
        unsigned q = 0;
        while (*p && *p != '\t') {
            if (q + 1 < cap[i]) dst[i][q++] = *p;
            ++p;
        }
        dst[i][q] = 0;
        if (*p == '\t') ++p;
    }
    out[0] = 0;
    for (i = 0; i < 2; ++i) { /* country, then the stream */
        const char *piece = parts[i];
        char tmp[48];
        unsigned q = 0;
        if (i == 1) {
            while (codec[q] && q < sizeof tmp - 8) tmp[q] = codec[q], ++q;
            if (rate[0] && strcmp(rate, "0")) {
                unsigned r = 0;
                if (q) tmp[q++] = ' ';
                while (rate[r] && q < sizeof tmp - 2) tmp[q++] = rate[r++];
                tmp[q++] = 'k';
            }
            tmp[q] = 0;
            piece = tmp;
        }
        if (!*piece) continue;
        if (o && o + 5 < n) out[o++] = ' ', out[o++] = (char)0xc2, out[o++] = (char)0xb7, out[o++] = ' ';
        while (*piece && o + 1 < n) out[o++] = *piece++;
        out[o] = 0;
    }
    out[o] = 0;
}

/* ---------------------------------------------------------------------------
 * Lists
 */
void rd_list_free(rd_list_t *l) {
    free(l->buf);
    memset(l, 0, sizeof *l);
}

int rd_list_copy(rd_list_t *to, const rd_list_t *from) {
    char *b;
    if (to == from) return 1;
    rd_list_free(to);
    if (!from->buf) return 1;
    b = calloc(from->len + 1, 1);
    if (!b) return 0;
    memcpy(b, from->buf, from->len);
    memcpy(to, from, sizeof *to);
    to->buf = b;
    return 1;
}

void rd_list_move(rd_list_t *to, rd_list_t *from) {
    if (to == from) return;
    rd_list_free(to);
    memcpy(to, from, sizeof *to);
    memset(from, 0, sizeof *from);
}

int rd_list_set(rd_list_t *l, const char *text, unsigned len, int kind) {
    unsigned key[RD_MAX + 1];
    int n;
    rd_list_free(l);
    if (kind == 1) { /* a pool apart: the stations' info is made, not cut */
        char *src = calloc(len + 1, 1), *pool = calloc(len + 2 * RD_MAX + 64, 1);
        if (!src || !pool) {
            free(src), free(pool);
            return 0;
        }
        memcpy(src, text, len);
        n = rd_stations(src, len, pool, len + 2 * RD_MAX + 64, l->name, l->url, l->info, RD_MAX + 1);
        free(src);
        l->buf = pool, l->len = len + 2 * RD_MAX + 64;
        if (n > 0) { /* only what the stations use stays (the CSV answer was far bigger) */
            unsigned used = 1, o;
            int i;
            for (i = 0; i < n; ++i) {
                o = l->name[i] + (unsigned)strlen(pool + l->name[i]) + 1;
                if (o > used) used = o;
                o = l->url[i] + (unsigned)strlen(pool + l->url[i]) + 1;
                if (o > used) used = o;
                o = l->info[i] + (unsigned)strlen(pool + l->info[i]) + 1;
                if (o > used) used = o;
            }
            char *exact = calloc(used + 1, 1);
            if (exact) { /* (if not, the big pool stays) */
                memcpy(exact, pool, used);
                free(pool);
                l->buf = exact, l->len = used + 1;
            }
        }
    } else {
        l->buf = calloc(len + 1, 1);
        if (!l->buf) return 0;
        memcpy(l->buf, text, len);
        l->len = len;
        if (kind == 0)
            n = rd_playlist(l->buf, l->name, l->url, l->info, RD_MAX + 1);
        else
            n = rd_choices(l->buf, l->name, key, l->info, RD_MAX + 1, kind == 2);
        if (kind != 0) {
            int i;
            for (i = 0; i < n; ++i) l->url[i] = key[i];
        }
    }
    l->truncated = n > RD_MAX;
    l->n = n > RD_MAX ? RD_MAX : n;
    return l->n > 0;
}

/* ---------------------------------------------------------------------------
 * The card: favourites, the user's lists, the station last played, the recent ones
 */
static struct {
    unsigned serial;
} rf __attribute__((section(".scratch")));

unsigned rd_serial(void) { return rf.serial; }

/* path's bytes appended to buf at *n, below cap, then a newline. 1 when read whole (or when the file is not there). */
static int rd_slurp(const char *path, char *buf, unsigned *n, unsigned cap) {
    void *f = *n + 2 <= cap ? fopen(path, "rb") : (void *)0;
    char extra;
    int ok;
    if (!f) return access(path, F_OK) != 0;
    *n += fread(buf + *n, 1, cap - *n - 2, f);
    ok = !fread(&extra, 1, 1, f);
    buf[(*n)++] = '\n';
    fclose(f);
    return ok;
}

int rd_favs_read(rd_list_t *l) {
    char *buf = calloc(RD_FETCH_MAX, 1);
    unsigned n = 0;
    int ok;
    rd_list_free(l);
    if (!buf) return 0;
    ok = rd_slurp(RD_FAVS, buf, &n, RD_FETCH_MAX);
    ok = ok && strlen(buf) == n; /* an embedded NUL would hide the stations after it */
    rd_list_set(l, buf, n, 0);
    free(buf);
    return l->buf != 0 && ok;
}

int rd_fav_index(const rd_list_t *favs, const char *url) {
    int k;
    for (k = 0; k < favs->n; ++k)
        if (!strcmp(rd_url(favs, k), url)) return k;
    return -1;
}

/* One .m3u text, a heap string (*len its length; NULL when there is no memory): the rows of a (only row a_only when it is >= 0, else every row but a_skip), then those of b the same
 * way, at most limit in all. A row is its #EXTINF name, its info as #M1+: (when it has any) and its address. */
static unsigned rd_row_size(const rd_list_t *l, int k) {
    return 24 + (unsigned)(strlen(rd_name(l, k)) + strlen(rd_info(l, k)) + strlen(rd_url(l, k)));
}

static int rd_info_empty(const char *s) {
    while (*s == '\t') ++s;
    return !*s;
}

static unsigned rd_row_put(char *out, unsigned cap, const rd_list_t *l, int k) {
    const char *info = rd_info(l, k);
    unsigned o = (unsigned)snprintf(out, cap, "#EXTINF:-1,%s\n", rd_name(l, k));
    if (!rd_info_empty(info)) o += (unsigned)snprintf(out + o, cap - o, "#M1+:%s\n", info);
    o += (unsigned)snprintf(out + o, cap - o, "%s\n", rd_url(l, k));
    return o;
}

static char *rd_m3u_make(const rd_list_t *a, int a_only, int a_skip, const rd_list_t *b, int b_only, int b_skip,
                         int limit, unsigned *len) {
    const rd_list_t *src[2] = {a, b};
    int only[2] = {a_only, b_only}, skip[2] = {a_skip, b_skip}, w, k, rows = 0;
    unsigned need = 16, o;
    char *out;
    for (w = 0; w < 2; ++w)
        for (k = 0; src[w] && k < src[w]->n; ++k)
            if (only[w] >= 0 ? k == only[w] : k != skip[w]) need += rd_row_size(src[w], k);
    out = calloc(need, 1);
    if (!out) return out;
    o = (unsigned)snprintf(out, need, "#EXTM3U\n");
    for (w = 0; w < 2; ++w)
        for (k = 0; src[w] && k < src[w]->n && rows < limit; ++k)
            if (only[w] >= 0 ? k == only[w] : k != skip[w]) o += rd_row_put(out + o, need - o, src[w], k), ++rows;
    *len = o;
    return out;
}

int rd_fav_toggle(const rd_list_t *l, int i) {
    rd_list_t favs;
    unsigned len = 0;
    int found, ok, added;
    char *text;
    memset(&favs, 0, sizeof favs);
    if (i < 0 || i >= l->n) return -1;
    ok = rd_favs_read(&favs);
    found = rd_fav_index(&favs, rd_url(l, i));
    if (favs.truncated || (found < 0 && favs.n >= RD_MAX)) ok = 0;
    text =
        ok ? rd_m3u_make(&favs, -1, found, found < 0 ? l : (const rd_list_t *)0, i, -1, RD_MAX + 1, &len) : (char *)0;
    ok = text != 0 && pod_card_write(RD_DIR, RD_FAVS, RD_FAVS_TMP, text, len, (const void *)0, 0) == 0;
    free(text);
    added = found < 0;
    rd_list_free(&favs);
    if (!ok) return -1;
    ++rf.serial;
    return added;
}

int rd_fav_has(const char *url) {
    rd_list_t favs;
    int has;
    memset(&favs, 0, sizeof favs);
    rd_favs_read(&favs);
    has = rd_fav_index(&favs, url) >= 0;
    rd_list_free(&favs);
    return has;
}

static int rd_read_whole(const char *path, rd_list_t *l) {
    char *buf = calloc(RD_FETCH_MAX, 1);
    unsigned n = 0;
    rd_list_free(l);
    if (!buf) return 0;
    rd_slurp(path, buf, &n, RD_FETCH_MAX);
    rd_list_set(l, buf, n, 0);
    free(buf);
    return l->n > 0;
}

#define RD_FILES_MAX 64 /* card playlists one import reads */
#define RD_NAMES_MAX 4096 /* their names */

/* A card file that is a playlist by its extension (.m3u, .m3u8, .pls), not a dot file and not favourites.m3u. */
static int rd_card_file(const char *name) {
    const char *dot = strrchr(name, '.');
    return name[0] != '.' && dot &&
           (!strcasecmp(dot, ".m3u") || !strcasecmp(dot, ".m3u8") || !strcasecmp(dot, ".pls")) &&
           strcasecmp(name, "favourites.m3u");
}

static int rd_name_cmp(const char *a, const char *b) {
    int c = strcasecmp(a, b);
    return c ? c : strcmp(a, b);
}

int rd_fav_import(int *full) {
    char *names = calloc(RD_NAMES_MAX, 1), *out = (char *)0, path[320];
    unsigned at[RD_FILES_MAX], used = 0, len = 0, cap = 0;
    int files = 0, added = 0, k, i, j, ok = 1;
    rd_list_t favs, f;
    void *dir;
    char *e;
    *full = 0;
    memset(&favs, 0, sizeof favs);
    memset(&f, 0, sizeof f);
    if (!names) return -1;
    if (!pod_card_mounted()) {
        free(names);
        return -1;
    }
    dir = opendir(RD_DIR);
    while (dir && (e = readdir(dir))) {
        const char *name = e + 11; /* struct dirent: d_name at +11 */
        unsigned n = (unsigned)strlen(name) + 1;
        if (!rd_card_file(name) || files >= RD_FILES_MAX || used + n > RD_NAMES_MAX) continue;
        memcpy(names + used, name, n);
        for (i = files++; i > 0 && rd_name_cmp(names + at[i - 1], name) > 0; --i)
            at[i] = at[i - 1]; /* sorted by file name */
        at[i] = used;
        used += n;
    }
    if (dir) closedir(dir);
    if (!files) {
        free(names);
        return -2;
    }
    ok = rd_favs_read(&favs) && !favs.truncated;
    if (ok) {
        out = rd_m3u_make(&favs, -1, -1, (const rd_list_t *)0, -1, -1, RD_MAX + 1, &len);
        cap = len + 1;
        ok = out != 0;
    }
    for (k = 0; ok && k < files && !*full; ++k) {
        snprintf(path, sizeof path, RD_DIR "/%s", names + at[k]);
        rd_read_whole(path, &f);
        for (j = 0; ok && j < f.n; ++j) {
            unsigned need = rd_row_size(&f, j), ul = (unsigned)strlen(rd_url(&f, j));
            char *probe = calloc(ul + 3, 1);
            if (!probe) {
                ok = 0;
                break;
            }
            snprintf(probe, ul + 3, "\n%s\n", rd_url(&f, j));
            if (strstr(out, probe)) { /* already a station, or imported from an earlier file */
                free(probe);
                continue;
            }
            free(probe);
            if (favs.n + added >= RD_MAX) {
                *full = 1;
                break;
            }
            if (len + need + 1 > cap) {
                char *bigger = calloc(cap = len + need + 1 + 4096, 1);
                if (!bigger) {
                    ok = 0;
                    break;
                }
                memcpy(bigger, out, len);
                free(out);
                out = bigger;
            }
            len += rd_row_put(out + len, cap - len, &f, j);
            ++added;
        }
    }
    rd_list_free(&f);
    if (ok && added) ok = pod_card_write(RD_DIR, RD_FAVS, RD_FAVS_TMP, out, len, (const void *)0, 0) == 0;
    free(out);
    free(names);
    rd_list_free(&favs);
    if (!ok) return -1;
    if (added) ++rf.serial;
    return added;
}

int rd_recent_read(rd_list_t *l) {
    int ok = rd_read_whole(RD_RECENT_FILE, l);
    if (l->n > RD_RECENT_MAX) l->n = RD_RECENT_MAX;
    return ok;
}

void rd_recent_push(const rd_list_t *l, int i) {
    rd_list_t old;
    unsigned len = 0;
    int k, same = -1;
    char *text;
    memset(&old, 0, sizeof old);
    if (i < 0 || i >= l->n) return;
    rd_recent_read(&old);
    for (k = 0; k < old.n; ++k)
        if (!strcmp(rd_url(&old, k), rd_url(l, i))) same = k; /* the station moves to the front */
    text = rd_m3u_make(l, i, -1, &old, -1, same, RD_RECENT_MAX, &len);
    if (text) home_write_atomic(RD_RECENT_FILE, RD_RECENT_TMP, text);
    free(text);
    rd_list_free(&old);
}

/* Clear Recently Played: radio-recent as it is written when no station is in it (the header alone), the way rd_recent_push writes it. */
int rd_recent_clear(void) { return home_write_atomic(RD_RECENT_FILE, RD_RECENT_TMP, "#EXTM3U\n") == 0; }

int rd_last_read(rd_list_t *l) {
    int ok = rd_recent_read(l);
    if (l->n > 1) l->n = 1;
    return ok && l->n == 1;
}

/* ---------------------------------------------------------------------------
 * Playing: stock's hciplayer (MPlayer) opens the stream; this is the state machine around it.
 */
static struct {
    int state, at, tries, fd;
    unsigned t_start, retry_at, last_hear, playing_since, timer;
    rd_list_t list;
    char error[72];
    int owns; /* after the error text: the tests poke the words before it by offset */
} rd __attribute__((section(".scratch")));

int rd_state(void) { return rd.state; }
int rd_running(void) { return rd.state == RD_CONNECTING || rd.state == RD_PLAYING || rd.state == RD_PAUSED; }
int rd_at(void) { return rd.at; }
/* The radio owns the Home mini bar: set when a station starts connecting, kept through Stop, Error and the like, cleared when a local track starts (rd_start_player). */
int rd_owns_bar(void) { return rd.owns; }
const rd_list_t *rd_list(void) { return &rd.list; }
const char *rd_error(void) { return rd.error; }

static const char *const RD_WHY[] = {"",
                                     "Unsupported address",
                                     "Could not start",
                                     "Playback ended",
                                     "Could not connect",
                                     "Stream stalled",
                                     "No response",
                                     "No Wi-Fi",
                                     "Player not ready"};

/* The state table (docs/modules/radio.md): next state, actions and the error's words (an index into RD_WHY) for each event in each state; Z = no change. RD_AGAIN marks a restart
 * that is allowed once per play (tries) and only with Wi-Fi; otherwise the cell becomes the error state with a stop. */
#define RD_AGAIN 0x80
#define N 0xff
#define Z {N, 0, 0}
#define C(next, act, why) {RD_##next, act, why}
typedef struct {
    unsigned char next, act, why;
} rd_cell;
#define ST 6
/*                         IDLE   CONNECTING                      PLAYING                         ERROR   STOPPED  PAUSED */
static const rd_cell RD_TABLE[RD_EV_N][ST] = {
    /* PLAY      */ {C(CONNECTING, RD_A_START, 0), C(CONNECTING, RD_A_STOP | RD_A_START, 0),
                     C(CONNECTING, RD_A_STOP | RD_A_START, 0), C(CONNECTING, RD_A_START, 0),
                     C(CONNECTING, RD_A_START, 0), C(CONNECTING, RD_A_STOP | RD_A_START, 0)},
    /* BAD       */
    {C(ERROR, 0, 1), C(ERROR, RD_A_STOP, 1), C(ERROR, RD_A_STOP, 1), C(ERROR, 0, 1), C(ERROR, 0, 1),
     C(ERROR, RD_A_STOP, 1)},
    /* FAILSTART */
    {C(ERROR, RD_A_STOP, 2), C(ERROR, RD_A_STOP, 2), C(ERROR, RD_A_STOP, 2), C(ERROR, RD_A_STOP, 2),
     C(ERROR, RD_A_STOP, 2), C(ERROR, RD_A_STOP, 2)},
    /* STOP      */
    {Z, C(STOPPED, RD_A_STOP, 0), C(STOPPED, RD_A_STOP, 0), C(STOPPED, 0, 0), Z, C(STOPPED, RD_A_STOP, 0)},
    /* LOCAL     */ {Z, C(STOPPED, RD_A_STOP, 0), C(STOPPED, RD_A_STOP, 0), Z, Z, C(STOPPED, RD_A_STOP, 0)},
    /* REROUTE   */
    {Z, C(CONNECTING, RD_A_STOP | RD_A_START, 0), C(CONNECTING, RD_A_STOP | RD_A_START, 0), Z, Z,
     C(PAUSED, RD_A_STOP | RD_A_START | RD_A_PAUSE, 0)},
    /* REROUTE_PAUSED: the same restart, then paused (stock's save_start_player(1)) */
    {Z, C(PAUSED, RD_A_STOP | RD_A_START | RD_A_PAUSE, 0), C(PAUSED, RD_A_STOP | RD_A_START | RD_A_PAUSE, 0), Z, Z,
     C(PAUSED, RD_A_STOP | RD_A_START | RD_A_PAUSE, 0)},
    /* HEAR      */ {Z, C(PLAYING, 0, 0), Z, Z, Z, C(PLAYING, 0, 0)},
    /* PAUSE     */ {Z, C(PAUSED, 0, 0), C(PAUSED, 0, 0), Z, Z, Z},
    /* RESUME    */ {Z, Z, Z, Z, Z, C(PLAYING, 0, 0)},
    /* ENDED     */ {Z, C(CONNECTING, RD_A_RETRY | RD_AGAIN, 4), C(ERROR, RD_A_STOP, 3), Z, Z, C(ERROR, RD_A_STOP, 3)},
    /* STALL     */ {Z, Z, C(CONNECTING, RD_A_STOP | RD_A_START | RD_AGAIN, 5), Z, Z, Z},
    /* TIMEOUT   */ {Z, C(ERROR, RD_A_STOP, 6), Z, Z, Z, Z},
    /* NOWIFI: a start (a tap, Retry, Resume, an output change) with no connection: no attempt, "No Wi-Fi" at once; a running stream is stopped */
    {C(ERROR, 0, 7), C(ERROR, RD_A_STOP, 7), C(ERROR, RD_A_STOP, 7), C(ERROR, 0, 7), C(ERROR, 0, 7),
     C(ERROR, RD_A_STOP, 7)},
};

/* The pure step: the new state | actions << 8 | why << 16. tries = restarts used by this play, wifi = a connection exists. */
int rd_step(int state, int ev, int tries, int wifi) {
    rd_cell c;
    int act, why;
    if (ev < 0 || ev >= RD_EV_N || state < 0 || state >= ST) return state;
    c = RD_TABLE[ev][state];
    if (c.next == N) c.next = (unsigned char)state;
    act = c.act & ~RD_AGAIN, why = c.why;
    if (c.act & RD_AGAIN && (tries || !wifi)) c.next = RD_ERROR, act = RD_A_STOP;
    if (c.next == RD_ERROR && !wifi && ev >= RD_EV_ENDED) why = 7; /* the network is gone: say so */
    return c.next | act << 8 | why << 16;
}

static void rd_begin(void);

/* One event through the table, then its actions. UI thread, or the mclStartPlayer hook's thread (EV_LOCAL: mclStop only). */
/* The radio always plays at 1x: rd_begin sends mode 0 when the user's Multiple Speed (playspeed_mode, never written here) is not 1x, and when the radio gives the output back
 * (the one place: rd_apply, after its stop) the saved mode goes to hciplayer again. A podcast's override (patch/pcmodel.c) writes playspeed_mode itself and restores its own original
 * later, so what this sends back is whatever the mode holds at that moment and the two never overwrite each other's variable. */
static int rd_was_running(int st) { return st == RD_CONNECTING || st == RD_PLAYING || st == RD_PAUSED; }

static void rd_speed_back(void) {
    int mode = *(volatile int *)PLAYSPEED_MODE;
    if (mode) mclSetPlaySpeed(mode);
}

static void rd_apply(int ev) {
    unsigned r = (unsigned)rd_step(rd.state, ev, rd.tries, ev >= RD_EV_ENDED ? get_wifisignal() > 0 : 1);
    unsigned act = r >> 8 & 255, why = r >> 16;
    int was = rd.state;
    rd.state = (int)(r & 255);
    if (rd.state == RD_ERROR) rd_copy(rd.error, sizeof rd.error, RD_WHY[why]);
    if (act & RD_A_STOP) mclStop(); /* synchronous; -1 at once when stock's running byte is 0, so it is idempotent */
    if (rd_was_running(was) && !rd_running())
        rd_speed_back(); /* the output goes back to local music at the user's speed */
    if (ev == RD_EV_PLAY) rd.tries = 0;
    if (rd.state == RD_CONNECTING && (ev == RD_EV_ENDED || ev == RD_EV_STALL)) ++rd.tries;
    if (rd.state == RD_PLAYING && was != RD_PLAYING) rd.last_hear = rd.playing_since = (unsigned)time_now_ms();
    if (act & RD_A_RETRY) rd.retry_at = (unsigned)time_now_ms() + 1000, rd.retry_at += !rd.retry_at;
    if (act & RD_A_START) rd_begin();
    if (act & RD_A_PAUSE && rd.state == RD_PAUSED)
        mclSetPause(); /* a paused station restarted on another output stays paused (as stock pauses its restarted track) */
}

/* hciplayer splits its command on '|' and ends it at '}'. */
static int rd_playable(const char *u) {
    if (strncasecmp(u, "http://", 7) && strncasecmp(u, "https://", 8)) return 0;
    return !strchr(u, '|') && !strchr(u, '}');
}

/* The output readied as stock's start_player does before each track: set_outputchannel(output, 2, 0) for every output (it also moves mclSetOutputWay to 0 for the jacks, 2 for
 * USB audio, 1 for Bluetooth, where it also switches the DAC off and hciplayer gets {mcl-setoutputway\1} and plays to bluealsa). For the built-in DAC, q2-pod's dac_take adds: its power
 * when only the idle timer cut it, PCM mode, unmuted (stop_player mutes), the volume. Without it hciplayer logs "Audio device got stuck!" and is silent. A USB DAC keeps its own power and
 * volume, and Bluetooth has no DAC to ready (the volume is the headset's). */
static void rd_dac(void) {
    int out = *(int *)G_HEADSET_OUTPUT;
    set_outputchannel(out, 2, 0);
    if (mclGetOutputWay() != 0) return;
    if (out >= 2 && *(int *)DACOFF_TIME < 0) mclSetDacPwr(1);
    mclSetPcmMode();
    mclSetMute(0);
    set_devicevolume(*(int *)G_VOLUME);
}

/* The start proven on the device: the DAC, the resume position 0 (>= 0 keeps mcl_tidalStartPlayer from asking the queue), the URL, then unmute (the DAC type 15 routine mutes before
 * it sends the URL). */
static void rd_begin(void) {
    int r;
    rd.retry_at = 0;
    rd.t_start = (unsigned)time_now_ms();
    if (*(volatile int *)HCI_SOCK_FD == -1) { /* hciplayer is not there: nothing would be sent */
        rd_apply(RD_EV_FAILSTART);
        rd_copy(rd.error, sizeof rd.error, RD_WHY[8]);
        return;
    }
    rd_dac();
    *(volatile int *)RESUME_POS = 0;
    if (*(volatile int *)PLAYSPEED_MODE != 0)
        mclSetPlaySpeed(0); /* the radio is live: 1x whatever Multiple Speed says */
    r = mcl_tidalStartPlayer(rd_url(&rd.list, rd.at));
    mclSetMute(0);
    rd.fd = *(volatile int *)HCI_SOCK_FD;
    rd.last_hear = rd.t_start;
    if (r != 1) rd_apply(RD_EV_FAILSTART);
}

static void rd_timer_off(void) {
    if (rd.timer) timer_remove(rd.timer);
    rd.timer = 0;
}

void rd_stop(void) {
    rd_apply(RD_EV_STOP);
    rd_timer_off();
    ++rf.serial;
}

/* mclStartPlayer's hook: local music takes the output. Stock sends set-nexturl while its running byte is 1 and hciplayer does not leave a stream for it, so the stream is stopped first
 * (mclStop waits for hciplayer's exit). No widget, no timer call here (it may run off the UI thread): the engine's timer sees the state and ends itself. */
int rd_start_player(void) {
    peqout_sync(0); /* the track starts on whatever output is plugged in now: its EQ (patch/peqout.c) */
    rd.owns = 0; /* local music takes the mini bar back */
    if (rd_running()) rd_apply(RD_EV_LOCAL);
    return stock_start_player_trampoline();
}

/* The output changes under a running station (a jack, a USB DAC, Bluetooth, the DSD mode): stock runs save_stop_player, set_outputchannel (and the volume), save_start_player in one
 * handler on the UI thread, and the second restarts the track it saved, which would stop the radio as a local track and play the old one. While a station runs, the first stops the
 * stream (mclStop, like the radio's own Stop; the state stays) and the second is the Reroute event: the same station again on the output stock just set (Bluetooth included), not
 * counted against the restart allowance. Stock's saved play status is never touched, so nothing of stock's restarts later. The UI-thread tick cannot fall between the two; a stop with no
 * start (Bluetooth pairing, linking) reads as an end in the next tick. With no radio both are one comparison and stock's function. */
void rd_save_stop(void) {
    if (rd_running())
        mclStop();
    else
        stock_save_stop_trampoline();
}

void rd_save_start(int paused) {
    peqout_sync(0); /* the output just changed under the track: its EQ is in place before stock restarts it */
    if (rd_running())
        rd_apply(get_wifisignal() <= 0 ? RD_EV_NOWIFI : paused ? RD_EV_REROUTE_PAUSED : RD_EV_REROUTE);
    else
        stock_save_start_trampoline(paused);
}

/* The engine's tick: reconcile with what stock says (never trust the flag alone). Inputs: the running byte (cleared by hciplayer's exit / error reply), the socket fd (changes when demo
 * restarts hciplayer), mclGetPlayStatus (1 stopped, 2 playing, 3 paused; set by stock's own stop / pause) and mclGetHciplayerStatus (1 while {player-status\request} answers playing). */
void rd_poll(void) {
    unsigned now = (unsigned)time_now_ms();
    int ev = -1, ps, hs, fd;
    if (!rd_running()) return;
    if (rd.state != RD_PAUSED) { /* a paused stream lets the player sleep as paused local music does */
        reset_poweroptions_timer(1, 1, 0);
        if (*(int *)DACOFF_TIME > 0) *(int *)DACOFF_TIME = 0;
    }
    if (rd.retry_at) { /* a restart after an early end is due */
        if ((int)(now - rd.retry_at) >= 0) rd_begin();
        return;
    }
    if (now - rd.t_start < RD_GRACE_MS) return;
    ps = mclGetPlayStatus();
    hs = mclGetHciplayerStatus() != 0;
    fd = *(volatile int *)HCI_SOCK_FD;
    if (!*(volatile unsigned char *)HCI_RUNNING || fd == -1 || fd != rd.fd || (ps == 1 && !hs))
        ev = RD_EV_ENDED;
    else if (ps == 3)
        ev = RD_EV_PAUSE;
    else if (rd.state == RD_PAUSED)
        ev = RD_EV_RESUME;
    else if (hs) {
        rd.last_hear = now;
        if (rd.state == RD_CONNECTING) ev = RD_EV_HEAR;
        if (rd.state == RD_PLAYING && now - rd.playing_since >= RD_STEADY_MS)
            rd.tries = 0; /* a stream that held for a minute earns a new restart */
    } else if (rd.state == RD_PLAYING && now - rd.last_hear >= RD_STALL_MS)
        ev = RD_EV_STALL;
    else if (rd.state == RD_CONNECTING && now - rd.t_start >= RD_SILENT_MS)
        ev = RD_EV_TIMEOUT;
    if (ev >= 0) rd_apply(ev);
}

static int rd_tick(const void *unused) {
    (void)unused;
    rd_poll();
    if (rd_running()) return RET_REPEAT;
    rd.timer = 0;
    return RET_OK;
}

/* Paused -> playing again (the mini bar's button): stock's resume, or with no Wi-Fi the Error "No Wi-Fi" (a paused live stream is dead without it). */
void rd_resume(void) {
    if (rd.state != RD_PAUSED) return;
    if (get_wifisignal() <= 0)
        rd_apply(RD_EV_NOWIFI);
    else
        mclSetResume();
}

int rd_play(const rd_list_t *l, int i) {
    if (!l || !l->n || i < 0 || i >= l->n) return 0;
    rd_timer_off();
    rd.error[0] = 0;
    rd.retry_at = 0;
    rd_list_copy(&rd.list, l);
    rd.at = rd.list.n > i ? i : 0;
    ++rf.serial;
    if (!rd.list.n) return 0;
    if (!rd_playable(rd_url(&rd.list, rd.at)))
        rd_apply(RD_EV_BAD);
    else if (get_wifisignal() <= 0)
        rd_apply(
            RD_EV_NOWIFI); /* no connection: no attempt, no 20 s wait; local music keeps playing, the next tap after Wi-Fi is back starts */
    else {
        if (!rd_running())
            stop_player(); /* stock's own stop (a no-op when nothing plays): local music holds the PCM even paused */
        rd_apply(RD_EV_PLAY);
    }
    if (rd.state != RD_CONNECTING) return 0;
    rd.owns = 1;
    rd.timer = timer_add(rd_tick, (void *)0, RD_POLL_MS);
    rd_recent_push(&rd.list, rd.at);
    return 1;
}

#undef N
#undef Z
#undef C
#undef ST

/* ---------------------------------------------------------------------------
 * The directory
 */
static struct {
    unsigned long thread;
    int state, kind, joined;
    volatile int cancel, done;
    long code,
        http; /* code: the answer's HTTP status (0 when the transfer failed); http: the raw status of the last attempt, for the log */
    int rc, tries; /* the last attempt's libcurl code and the attempts made */
    char *body;
    unsigned n;
    char url[400];
} fx __attribute__((section(".scratch")));

int rd_fetch_state(void) { return fx.state == RD_F_RUNNING && fx.done ? RD_F_DONE : fx.state; }

static void rd_fetch_reap(void) {
    if (fx.state == RD_F_RUNNING && fx.done) { /* the worker has ended (its answer is waiting, or was dropped) */
        pthread_join(fx.thread, (void **)0);
        fx.state = fx.cancel ? RD_F_NONE : RD_F_DONE;
        if (fx.cancel) free(fx.body), fx.body = (char *)0;
    }
}

static unsigned rd_fetch_write(char *data, unsigned size, unsigned nmemb, void *user) {
    unsigned len = size * nmemb;
    (void)user;
    if (fx.cancel || fx.n + len >= RD_FETCH_MAX) return 0; /* stops the transfer */
    memcpy(fx.body + fx.n, data, len);
    fx.n += len;
    return len;
}

static int rd_fetch_xfer(void *u, long long a, long long b, long long c, long long d) {
    (void)u, (void)a, (void)b, (void)c, (void)d;
    return fx.cancel;
}

/* Whether a failed attempt is tried again, and after how many seconds (0: no). attempt = attempts made so far (1 after the first). Network or TLS failures and a 5xx answer are tried
 * again twice (1 s, then 2 s); a cancel (the page's Back, rc 42 or 23), the 256 KB cap, an answer of 4xx or an answer at all are not. */
int rd_fetch_retry(int rc, long code, int attempt) {
    if (attempt < 1 || attempt > 2) return 0;
    if (rc == CURLE_ABORTED_BY_CALLBACK || rc == CURLE_WRITE_ERROR) return 0;
    if (rc == 0 && code < 500) return 0;
    return attempt; /* rc != 0, or an HTTP 5xx */
}

/* Opt-in log (the file /mnt/mmc/m1plus-log turns it on, as the Home log): the last attempt of a directory fetch that failed. */
static void rd_log(const char *path) {
    char line[160];
    int fd;
    if (access(LOG_ENABLE, F_OK)) return;
    fd = open(LOG_FILE, O_WRONLY | O_APPEND | O_CREAT, 0644);
    if (fd < 0) return;
    snprintf(line, sizeof line, "radio: directory %s failed: curl %d, http %d, attempts %d\n", path, fx.rc,
             (int)fx.http, fx.tries);
    write(fd, line, strlen(line));
    close(fd);
}

/* One attempt on a fresh libcurl handle (so the round-robin name can resolve to another mirror): libcurl's code, fx.code the HTTP status (0 on a failure; an answer cut at the cap is used). */
static int rd_fetch_once(void) {
    void *h = curl_easy_init();
    int rc = 2; /* CURLE_FAILED_INIT */
    if (fx.n) memset(fx.body, 0, fx.n); /* a failed try's bytes are gone (the parser wants a NUL after the answer) */
    fx.n = 0, fx.code = fx.http = 0;
    if (!h) return rc;
    curl_easy_setopt(h, CURLOPT_URL, fx.url);
    curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, rd_fetch_write);
    curl_easy_setopt(h, CURLOPT_WRITEDATA, (void *)0);
    curl_easy_setopt(h, CURLOPT_NOPROGRESS, 0);
    curl_easy_setopt(h, CURLOPT_XFERINFOFUNCTION, rd_fetch_xfer);
    curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1);
    curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 1);
    curl_easy_setopt(h, CURLOPT_MAXREDIRS, 5);
    curl_easy_setopt(h, CURLOPT_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
    curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
    curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT, 10);
    curl_easy_setopt(h, CURLOPT_TIMEOUT, 30);
    curl_easy_setopt(h, CURLOPT_USERAGENT, "M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)");
    curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING, "");
    curl_easy_setopt(h, CURLOPT_CAINFO, PN_CA); /* verification stays on: no SSL_VERIFY option is ever set */
    rc = curl_easy_perform(h);
    curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &fx.http);
    fx.code = fx.http;
    if (rc && !(rc == CURLE_WRITE_ERROR && fx.n)) fx.code = 0; /* an answer cut at the cap is used as it is */
    curl_easy_cleanup(h);
    return rc;
}

static void *rd_fetch_worker(void *unused) {
    int rc, wait, i;
    (void)unused;
    fx.tries = 0;
    for (;;) {
        rc = rd_fetch_once();
        fx.rc = rc;
        ++fx.tries;
        wait = fx.cancel ? 0 : rd_fetch_retry(rc, fx.http, fx.tries);
        if (!wait) break;
        for (i = 0; i < wait && !fx.cancel; ++i) sleep(1); /* Back ends the wait within a second */
        if (fx.cancel) break;
    }
    if (!fx.cancel && fx.code != 200) rd_log(fx.url + sizeof RD_API - 1);
    fx.done = 1;
    return (void *)0;
}

static void rd_logo_poll(void);
int rd_logo_running(void);
void rd_logo_cancel(void);

int rd_fetch(const char *path, int kind) {
    rd_fetch_reap();
    if (fx.state == RD_F_RUNNING) return RD_E_BUSY;
    if (get_wifisignal() <= 0) return RD_E_WIFI; /* first: nothing below is worth waiting for without a connection */
    if ((unsigned)time((long *)0) < PN_MIN_EPOCH) return RD_E_CLOCK;
    if (access(PN_CA, F_OK)) return RD_E_FAIL;
    rd_logo_cancel(); /* the directory goes before the radio's own logo job: it is asked to end (within a transfer callback) and the page asks again */
    if (rd_logo_running()) return RD_E_BUSY;
    if (fx.state == RD_F_DONE) free(fx.body), fx.body = (char *)0, fx.state = RD_F_NONE; /* an answer nobody took */
    if (pn_busy() || pn_dl_running() || pn_job_busy()) return RD_E_PODBUSY; /* a podcast job is never cut short */
    fx.body = calloc(RD_FETCH_MAX + 1, 1);
    if (!fx.body) return RD_E_FAIL;
    snprintf(fx.url, sizeof fx.url, RD_API "%s", path);
    fx.n = 0, fx.cancel = fx.done = 0, fx.code = fx.http = 0, fx.rc = fx.tries = 0, fx.kind = kind;
    if (pthread_create(&fx.thread, (const void *)0, rd_fetch_worker, (void *)0)) {
        free(fx.body), fx.body = (char *)0;
        return RD_E_FAIL;
    }
    fx.state = RD_F_RUNNING;
    return RD_E_OK;
}

void rd_fetch_cancel(void) {
    if (fx.state == RD_F_RUNNING) {
        fx.cancel = 1;
        rd_fetch_reap(); /* a worker that has ended is joined now and its answer freed */
    } else if (fx.state == RD_F_DONE)
        free(fx.body), fx.body = (char *)0, fx.state = RD_F_NONE;
}

void rd_fetch_drop(void) { rd_fetch_cancel(); }

int rd_fetch_take(rd_list_t *l, int *err) {
    int ok = 0;
    rd_fetch_reap();
    *err = RD_E_FAIL;
    if (fx.state != RD_F_DONE) return 0;
    if (fx.code == 200 && fx.n) {
        rd_list_t got;
        memset(&got, 0, sizeof got);
        ok = rd_list_set(&got, fx.body, fx.n, fx.kind);
        *err = ok ? RD_E_OK : RD_E_EMPTY;
        if (ok)
            rd_list_free(l),
                memcpy(l, &got, sizeof got); /* (an answer with nothing in it leaves the list the page has) */
        else
            rd_list_free(&got);
    }
    free(fx.body), fx.body = (char *)0, fx.state = RD_F_NONE;
    return ok;
}

/* ---------------------------------------------------------------------------
 * Station logos: the CSV's favicon, fetched one at a time by a worker of its own (never beside the directory fetch or a podcast job), shrunk with the Podcasts cover code (pv_shrink / pv_shrink_png,
 * a baseline JPEG of at most 192 px) into RD_LOGO_DIR/<hash>.jpg. A picture that cannot be had or used leaves <hash>.no; a network failure only a session note.
 */
#define RD_LOGO_SRC "/tmp/m1plus-logo.src"
#define RD_LOGO_CAP (256u << 10)
#define RD_LOGO_FILES 400

static struct {
    unsigned long thread;
    int running, fd, result;
    volatile int cancel, done;
    unsigned hash, n, failed[16], nfailed, refused; /* refused: the card took no marker, so no more downloads */
    char url[RD_FAV_MAX + 1];
} lg __attribute__((section(".scratch")));

unsigned rd_logo_hash(const char *url) {
    unsigned h = 2166136261u;
    for (; *url; ++url) h = (h ^ (unsigned char)*url) * 16777619u;
    return h ? h : 1;
}

int rd_favicon(const char *info, char *out, unsigned n) {
    int tabs = 0;
    out[0] = 0;
    while (*info && tabs < 3) tabs += *info++ == '\t';
    if (tabs < 3 || strlen(info) >= n || (strncasecmp(info, "http://", 7) && strncasecmp(info, "https://", 8)))
        return 0;
    memcpy(out, info, strlen(info) + 1);
    return 1;
}

int rd_logo_file(unsigned hash, char *path, unsigned n) {
    char no[48];
    unsigned i;
    snprintf(path, n, RD_LOGO_DIR "/%08x.jpg", hash);
    if (!access(path, F_OK)) return 1;
    snprintf(no, sizeof no, RD_LOGO_DIR "/%08x.no", hash);
    if (!access(no, F_OK) || lg.refused) return -1;
    for (i = 0; i < lg.nfailed && i < 16; ++i)
        if (lg.failed[i] == hash) return -1;
    return 0;
}

static unsigned rd_logo_write(char *data, unsigned size, unsigned nmemb, void *user) {
    unsigned len = size * nmemb, at = 0;
    (void)user;
    if (lg.cancel || len > RD_LOGO_CAP || lg.n > RD_LOGO_CAP - len) return 0;
    while (at < len) {
        int w = write(lg.fd, data + at, len - at);
        if (w <= 0) return 0;
        at += (unsigned)w;
    }
    lg.n += len;
    return len;
}

static int rd_logo_xfer(void *u, long long a, long long b, long long c, long long d) {
    (void)u, (void)a, (void)b, (void)c, (void)d;
    return lg.cancel;
}

/* The files of the logo folder: past RD_LOGO_FILES they are all removed (they are only a cache). */
static void rd_logo_trim(void) {
    void *dir = opendir(RD_LOGO_DIR);
    char *e, path[64];
    int n = 0, pass;
    for (pass = 0; pass < 2 && dir; ++pass) {
        while ((e = readdir(dir))) {
            const char *name = e + 11;
            if (name[0] == '.') continue;
            if (!pass)
                ++n;
            else {
                snprintf(path, sizeof path, RD_LOGO_DIR "/%s", name);
                unlink(path);
            }
        }
        if (pass || n < RD_LOGO_FILES) break;
        closedir(dir);
        dir = opendir(RD_LOGO_DIR);
    }
    if (dir) closedir(dir);
}

static void *rd_logo_worker(void *unused) {
    void *h;
    int rc = -1;
    (void)unused;
    lg.n = 0;
    lg.fd = open(RD_LOGO_SRC, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    h = lg.fd >= 0 ? curl_easy_init() : (void *)0;
    if (h) {
        curl_easy_setopt(h, CURLOPT_URL, lg.url);
        curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, rd_logo_write);
        curl_easy_setopt(h, CURLOPT_WRITEDATA, (void *)0);
        curl_easy_setopt(h, CURLOPT_NOPROGRESS, 0);
        curl_easy_setopt(h, CURLOPT_XFERINFOFUNCTION, rd_logo_xfer);
        curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1);
        curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 1);
        curl_easy_setopt(h, CURLOPT_MAXREDIRS, 3);
        curl_easy_setopt(h, CURLOPT_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
        curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
        curl_easy_setopt(h, CURLOPT_FAILONERROR, 1);
        curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT, 5);
        curl_easy_setopt(h, CURLOPT_TIMEOUT, 10);
        curl_easy_setopt(h, CURLOPT_USERAGENT, "M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)");
        curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING, "");
        curl_easy_setopt(h, CURLOPT_CAINFO, PN_CA);
        rc = curl_easy_perform(h);
        curl_easy_cleanup(h);
    }
    if (lg.fd >= 0) close(lg.fd);
    /* 0: a network failure (tried again next session); 1: made; 2: the answer is no picture we can use */
    lg.result = rc == 0 ? 2 : (rc == CURLE_HTTP_RETURNED_ERROR || (rc == CURLE_WRITE_ERROR && !lg.cancel)) ? 2 : 0;
    if (rc == 0 && !lg.cancel) {
        unsigned char head[8];
        int fd = open(RD_LOGO_SRC, O_RDONLY, 0), got = fd >= 0 ? read(fd, head, sizeof head) : 0;
        char tmp[64], dst[64];
        if (fd >= 0) close(fd);
        snprintf(tmp, sizeof tmp, RD_LOGO_DIR "/%08x.tmp", lg.hash);
        snprintf(dst, sizeof dst, RD_LOGO_DIR "/%08x.jpg", lg.hash);
        mkdir(RD_DIR, 0755); /* (a fresh card has neither) */
        mkdir(RD_LOGO_DIR, 0755);
        rd_logo_trim();
        if (got == 8 && head[0] == 0xff && head[1] == 0xd8 && head[2] == 0xff && pv_shrink(RD_LOGO_SRC, tmp) == 1)
            lg.result = rename(tmp, dst) == 0 ? 1 : 2;
        else if (got == 8 && head[0] == 0x89 && head[1] == 'P' && head[2] == 'N' && head[3] == 'G' &&
                 pv_shrink_png(RD_LOGO_SRC, tmp) == 1)
            lg.result = rename(tmp, dst) == 0 ? 1 : 2;
        else
            unlink(tmp); /* (GIF, ICO, SVG, WebP, a page: not decodable here) */
    }
    unlink(RD_LOGO_SRC);
    if (lg.result == 2 && !lg.cancel) {
        char no[48];
        int fd;
        snprintf(no, sizeof no, RD_LOGO_DIR "/%08x.no", lg.hash);
        mkdir(RD_DIR, 0755);
        mkdir(RD_LOGO_DIR, 0755);
        fd = open(no, O_WRONLY | O_CREAT, 0644);
        if (fd >= 0)
            close(fd);
        else
            lg.refused = 1; /* a full or locked card: the cached logos still show, no new download this session */
    }
    if (lg.result == 0 && !lg.cancel && lg.nfailed < 16) lg.failed[lg.nfailed++] = lg.hash;
    lg.done = 1;
    return (void *)0;
}

static void rd_logo_poll(void) {
    if (lg.running && lg.done) {
        pthread_join(lg.thread, (void **)0);
        lg.running = 0;
    }
}

int rd_logo_running(void) {
    rd_logo_poll();
    return lg.running;
}

void rd_logo_cancel(void) {
    if (lg.running) lg.cancel = 1;
    rd_logo_poll();
}

int rd_logo_start(const char *url) {
    char path[48];
    unsigned hash;
    rd_logo_poll();
    if (lg.running || fx.state == RD_F_RUNNING || strlen(url) > RD_FAV_MAX ||
        (strncasecmp(url, "http://", 7) && strncasecmp(url, "https://", 8)))
        return 0;
    hash = rd_logo_hash(url);
    if (rd_logo_file(hash, path, sizeof path) != 0 || !pod_card_mounted()) return 0;
    if (pn_busy() || pn_dl_running() || pn_job_busy() || get_wifisignal() <= 0 ||
        (unsigned)time((long *)0) < PN_MIN_EPOCH || access(PN_CA, F_OK))
        return 0;
    memcpy(lg.url, url, strlen(url) + 1);
    lg.hash = hash, lg.cancel = lg.done = 0, lg.result = 0;
    if (pthread_create(&lg.thread, (const void *)0, rd_logo_worker, (void *)0)) return 0;
    lg.running = 1;
    return 1;
}
