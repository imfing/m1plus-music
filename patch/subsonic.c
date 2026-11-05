/* Navidrome/Subsonic response handling. Bounded JSON reads only. */
#include "offsets.inc"
#include "stock.h"
#include "subsonic.h"
#include "common.h"
#include "covercache.h"
#include "keyboard.h"
#include "curlopts.h"
#include "home.h"
#include "i18n.h"
#include "palette.h"
extern int pn_free_kb(const char *path, unsigned *kb);
extern int pod_confirm(const char *text);

static unsigned sb_len(const char *s) {
    unsigned n = 0;
    if (s)
        while (s[n]) ++n;
    return n;
}

static int sb_has_char(const char *s, char value) {
    unsigned i;
    if (!s) return 0;
    for (i = 0; s[i]; ++i)
        if (s[i] == value) return 1;
    return 0;
}

static int sb_eq(const char *a, unsigned n, const char *b) {
    unsigned i = 0;
    while (b[i] && i < n && a[i] == b[i]) ++i;
    return i == n && !b[i];
}

static int sb_ascii_lower(unsigned c) { return c >= 'A' && c <= 'Z' ? (int)(c + ('a' - 'A')) : (int)c; }

static int sb_is_dsd(const char *suffix) {
    unsigned n = sb_len(suffix);
    if (n != 3) return 0;
    return sb_ascii_lower((unsigned char)suffix[0]) == 'd' &&
           (sb_ascii_lower((unsigned char)suffix[1]) == 's' || sb_ascii_lower((unsigned char)suffix[1]) == 'f') &&
           sb_ascii_lower((unsigned char)suffix[2]) == 'f';
}

static int sb_hex(unsigned c) {
    if (c >= '0' && c <= '9') return (int)(c - '0');
    if (c >= 'a' && c <= 'f') return (int)(c - 'a' + 10);
    if (c >= 'A' && c <= 'F') return (int)(c - 'A' + 10);
    return -1;
}

static int sb_prefix(const char *value, const char *prefix) {
    unsigned i = 0;
    if (!value) return 0;
    while (prefix[i] && value[i] == prefix[i]) ++i;
    return !prefix[i];
}

static int sb_https(const char *url) { return sb_prefix(url, "https://"); }

static int sb_http_url(const char *url) { return sb_prefix(url, "http://") || sb_https(url); }

static int sb_put(char *out, unsigned cap, unsigned *used, unsigned c) {
    unsigned n = c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
    if (*used + n >= cap) return 0;
    if (n == 1)
        out[(*used)++] = (char)c;
    else if (n == 2)
        out[(*used)++] = (char)(0xc0 | (c >> 6)), out[(*used)++] = (char)(0x80 | (c & 63));
    else if (n == 3)
        out[(*used)++] = (char)(0xe0 | (c >> 12)), out[(*used)++] = (char)(0x80 | (c >> 6 & 63)),
        out[(*used)++] = (char)(0x80 | (c & 63));
    else
        out[(*used)++] = (char)(0xf0 | (c >> 18)), out[(*used)++] = (char)(0x80 | (c >> 12 & 63)),
        out[(*used)++] = (char)(0x80 | (c >> 6 & 63)), out[(*used)++] = (char)(0x80 | (c & 63));
    return 1;
}

static const char *sb_ws(const char *p, const char *end) {
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
    return p;
}

/* Decode one JSON string, bounded to its containing response. */
static const char *sb_string(const char *p, const char *end, char *out, unsigned cap) {
    unsigned used = 0;
    if (p >= end || *p != '"') return 0;
    ++p;
    while (p < end && *p != '"') {
        unsigned c = (unsigned char)*p++;
        int decoded = 0;
        if (c == '\\') {
            decoded = 1;
            if (p >= end) return 0;
            c = (unsigned char)*p++;
            if (c == 'u') {
                int a, b, d, e;
                if (end - p < 4 || (a = sb_hex(p[0])) < 0 || (b = sb_hex(p[1])) < 0 || (d = sb_hex(p[2])) < 0 ||
                    (e = sb_hex(p[3])) < 0)
                    return 0;
                c = (unsigned)((a << 12) | (b << 8) | (d << 4) | e);
                p += 4;
                if (c >= 0xd800 && c <= 0xdbff && end - p >= 6 && p[0] == '\\' && p[1] == 'u') {
                    int x = sb_hex(p[2]), y = sb_hex(p[3]), z = sb_hex(p[4]), w = sb_hex(p[5]);
                    unsigned lo =
                        x < 0 || y < 0 || z < 0 || w < 0 ? 0 : (unsigned)((x << 12) | (y << 8) | (z << 4) | w);
                    if (lo >= 0xdc00 && lo <= 0xdfff) c = 0x10000u + ((c - 0xd800u) << 10) + lo - 0xdc00u, p += 6;
                }
            } else if (c == 'n' || c == 'r' || c == 't' || c == 'b' || c == 'f')
                c = ' ';
        }
        /* JSON's unescaped UTF-8 bytes are already encoded; only \u escapes
         * need UTF-8 encoding here. */
        if (c && !decoded && c >= 0x80) {
            if (used + 1 >= cap) return 0;
            out[used++] = (char)c;
        } else if (c && !sb_put(out, cap, &used, c))
            return 0;
    }
    if (p >= end) return 0;
    out[used] = 0;
    return p + 1;
}

static const char *sb_skip(const char *p, const char *end) {
    unsigned depth = 0;
    int quote = 0, esc = 0;
    p = sb_ws(p, end);
    if (p >= end) return 0;
    if (*p != '{' && *p != '[') {
        if (*p == '"') {
            int esc = 0;
            for (++p; p < end; ++p) {
                if (esc)
                    esc = 0;
                else if (*p == '\\')
                    esc = 1;
                else if (*p == '"')
                    return p + 1;
            }
            return 0;
        }
        while (p < end && *p != ',' && *p != '}' && *p != ']') ++p;
        return p;
    }
    for (; p < end; ++p) {
        char c = *p;
        if (quote) {
            if (esc)
                esc = 0;
            else if (c == '\\')
                esc = 1;
            else if (c == '"')
                quote = 0;
            continue;
        }
        if (c == '"')
            quote = 1;
        else if (c == '{' || c == '[')
            ++depth;
        else if (c == '}' || c == ']') {
            if (!depth || --depth == 0) return p + 1;
        }
    }
    return 0;
}

/* Find an object-valued member and return its value's opening brace. */
static const char *sb_object(const char *obj, const char *end, const char *key) {
    const char *p = sb_ws(obj, end);
    if (p >= end || *p != '{') return 0;
    ++p;
    while ((p = sb_ws(p, end)) < end && *p != '}') {
        char name[48];
        const char *q = sb_string(p, end, name, sizeof name);
        if (!q) return 0;
        p = sb_ws(q, end);
        if (p >= end || *p++ != ':') return 0;
        p = sb_ws(p, end);
        if (sb_eq(name, sb_len(name), key)) return p < end && *p == '{' ? p : 0;
        p = sb_skip(p, end);
        if (!p) return 0;
        p = sb_ws(p, end);
        if (p < end && *p == ',')
            ++p;
        else if (p < end && *p != '}')
            return 0;
    }
    return 0;
}

static int sb_member(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num) {
    const char *p = sb_ws(obj, end);
    if (p >= end || *p != '{') return 0;
    ++p;
    while ((p = sb_ws(p, end)) < end && *p != '}') {
        char name[48];
        const char *q = sb_string(p, end, name, sizeof name);
        if (!q) return 0;
        p = sb_ws(q, end);
        if (p >= end || *p++ != ':') return 0;
        p = sb_ws(p, end);
        if (sb_eq(name, sb_len(name), key)) {
            if (*p == '"') {
                q = sb_string(p, end, out, cap);
                if (!q) return -1;
                return 1;
            }
            if (*p >= '0' && *p <= '9') {
                unsigned v = 0;
                while (p < end && *p >= '0' && *p <= '9') {
                    if (v < 0x10000000u) v = v * 10 + (unsigned)(*p - '0');
                    ++p;
                }
                if (num) *num = v;
                if (out && cap) out[0] = 0;
                return 1;
            }
            if (*p == 'n' || *p == 't' || *p == 'f') {
                if (out && cap) out[0] = 0;
                return 1;
            }
            return 0;
        }
        p = sb_skip(p, end);
        if (!p) return 0;
        p = sb_ws(p, end);
        if (p < end && *p == ',')
            ++p;
        else if (p < end && *p != '}')
            return 0;
    }
    return 0;
}

static unsigned sb_urlenc(char *out, unsigned cap, unsigned used, const char *s) {
    static const char hex[] = "0123456789ABCDEF";
    unsigned i;
    if (!s) return 0;
    for (i = 0; s[i]; ++i) {
        unsigned c = (unsigned char)s[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' ||
            c == '.' || c == '~') {
            if (used + 1 >= cap) return 0;
            out[used++] = (char)c;
        } else {
            if (used + 3 >= cap) return 0;
            out[used++] = '%', out[used++] = hex[c >> 4], out[used++] = hex[c & 15];
        }
    }
    return used;
}

/* Subsonic's token authentication is MD5(password + random salt). The salt is
 * generated per request so neither the password nor a reusable token appears
 * in the URL passed to the stock player. */
static unsigned sb_rotl(unsigned x, unsigned n) { return (x << n) | (x >> (32 - n)); }
static void sb_md5(const unsigned char *msg, unsigned n, unsigned char out[16]) {
    static const unsigned k[64] = {
        0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
        0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be, 0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
        0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
        0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
        0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c, 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
        0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
        0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
        0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1, 0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391};
    static const unsigned char s[64] = {7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
                                        5, 9,  14, 20, 5, 9,  14, 20, 5, 9,  14, 20, 5, 9,  14, 20,
                                        4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
                                        6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21};
    unsigned char b[256];
    unsigned blocks = ((n + 9 + 63) / 64) * 64, i, j;
    unsigned a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    for (i = 0; i < n; ++i) b[i] = msg[i];
    b[n] = 0x80;
    for (i = n + 1; i < blocks; ++i) b[i] = 0;
    {
        unsigned long long bits = (unsigned long long)n * 8;
        for (i = 0; i < 8; ++i) b[blocks - 8 + i] = (unsigned char)(bits >> (8 * i));
    }
    for (i = 0; i < blocks; i += 64) {
        unsigned m[16], a = a0, bb = b0, c = c0, d = d0, q;
        for (j = 0; j < 16; ++j)
            m[j] = (unsigned)b[i + j * 4] | (unsigned)b[i + j * 4 + 1] << 8 | (unsigned)b[i + j * 4 + 2] << 16 |
                   (unsigned)b[i + j * 4 + 3] << 24;
        for (j = 0; j < 64; ++j) {
            unsigned f, g;
            if (j < 16)
                f = (bb & c) | (~bb & d), g = j;
            else if (j < 32)
                f = (d & bb) | (~d & c), g = (5 * j + 1) & 15;
            else if (j < 48)
                f = bb ^ c ^ d, g = (3 * j + 5) & 15;
            else
                f = c ^ (bb | ~d), g = (7 * j) & 15;
            q = d;
            d = c;
            c = bb;
            bb = bb + sb_rotl(a + f + k[j] + m[g], s[j]);
            a = q;
        }
        a0 += a;
        b0 += bb;
        c0 += c;
        d0 += d;
    }
    {
        unsigned v[4] = {a0, b0, c0, d0};
        for (i = 0; i < 4; ++i)
            for (j = 0; j < 4; ++j) out[i * 4 + j] = (unsigned char)(v[i] >> (8 * j));
    }
}

static int sb_auth(char *token, unsigned tcap, char *salt, unsigned scap, const char *password) {
    static const char hex[] = "0123456789abcdef";
    unsigned char raw[8], digest[16], input[SB_TEXT + 8];
    unsigned i, n = sb_len(password);
    int fd;
    if (!token || tcap < 33 || !salt || scap < 17 || n >= SB_TEXT) return -1;
    fd = open("/dev/urandom", O_RDONLY, 0);
    if (fd < 0) return -1;
    if (read(fd, raw, sizeof raw) != (int)sizeof raw) {
        close(fd);
        return -1;
    }
    close(fd);
    for (i = 0; i < 8; ++i) salt[2 * i] = hex[raw[i] >> 4], salt[2 * i + 1] = hex[raw[i] & 15];
    salt[16] = 0;
    memcpy(input, password, n);
    memcpy(input + n, salt, 16);
    sb_md5(input, n + 16, digest);
    for (i = 0; i < 16; ++i) token[2 * i] = hex[digest[i] >> 4], token[2 * i + 1] = hex[digest[i] & 15];
    token[32] = 0;
    memset(input, 0, sizeof input);
    memset(digest, 0, sizeof digest);
    return 0;
}

int sb_url(char *out, unsigned cap, const char *base, const char *method, const char *id, const char *user,
           const char *password, const char *extra) {
    unsigned n = 0, i;
    char token[33], salt[17];
    int k;
    if (!out || !cap || !base || !method || !user || !password || !sb_http_url(base)) return -1;
    k = snprintf(out, cap, "%s/rest/%s.view?u=", base, method);
    if (k < 0 || (unsigned)k >= cap) return -1;
    n = sb_urlenc(out, cap, (unsigned)k, user);
    if (!n) return -1;
    if (sb_auth(token, sizeof token, salt, sizeof salt, password)) return -1;
    k = snprintf(out + n, cap - n, "&t=%s&s=%s&v=1.16.1&c=m1plus-music&f=json", token, salt);
    if (k < 0 || (unsigned)k >= cap - n) return -1;
    n += (unsigned)k;
    if (id) {
        k = snprintf(out + n, cap - n, "&id=");
        if (k < 0 || (unsigned)k >= cap - n) return -1;
        n = sb_urlenc(out, cap, n + (unsigned)k, id);
        if (!n) return -1;
    }
    if (method[0] == 's' && method[1] == 't' && method[2] == 'r' && method[3] == 'e' && method[4] == 'a' &&
        method[5] == 'm' && !method[6]) {
        k = snprintf(out + n, cap - n, "&format=raw");
        if (k < 0 || (unsigned)k >= cap - n) return -1;
        n += (unsigned)k;
    }
    if (extra) {
        unsigned x = sb_len(extra);
        if (n + x >= cap) return -1;
        for (i = 0; i < x; ++i) out[n++] = extra[i];
        out[n] = 0;
    }
    return 0;
}

#define SB_SYNC_PAGE 64
int sb_sync_query(char *out, unsigned cap, unsigned offset) {
    int n;
    if (!out || !cap) return -1;
    n = snprintf(out, cap, "&query=&songCount=%u&albumCount=0&artistCount=0&songOffset=%u", SB_SYNC_PAGE, offset);
    return n < 0 || (unsigned)n >= cap ? -1 : n;
}

int sb_track_filename(char *out, unsigned cap, const sb_song_t *song) {
    const char *title;
    unsigned i, n = 0;
    if (!out || !cap || !song) return -1;
    title = song->title[0] ? song->title : TR("Untitled");
    while (title[n] && n + 1 < cap) out[n] = title[n], ++n;
    if (title[n]) return -1;
    if (!song->suffix[0]) {
        out[n] = 0;
        return (int)n;
    }
    if (n + 2 >= cap) return -1;
    out[n++] = '.';
    for (i = 0; song->suffix[i]; ++i) {
        unsigned c = (unsigned char)song->suffix[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return -1;
        if (n + 1 >= cap) return -1;
        out[n++] = (char)c;
    }
    out[n] = 0;
    return (int)n;
}

static void sb_field(const char *obj, const char *end, const char *name, char *out, unsigned cap) {
    (void)sb_member(obj, end, name, out, cap, (unsigned *)0);
}

static int sb_response(const char *json, unsigned n) {
    char status[16];
    const char *end = json + n;
    const char *p = sb_object(sb_ws(json, end), end, "subsonic-response");
    if (!p) return 0;
    if (sb_member(p, end, "status", status, sizeof status, (unsigned *)0) <= 0) return 0;
    return sb_eq(status, sb_len(status), "ok");
}

int sb_songs(const char *json, unsigned n, sb_song_t *out, int max) {
    const char *end, *p, *arr = 0, *arrend;
    unsigned depth = 0;
    int count = 0;
    if (!json || !out || max <= 0 || n > 1024 * 1024 || !sb_response(json, n)) return -1;
    end = json + n;
    /* Locate the first songs array emitted by search3, getAlbum, getPlaylist or getRandomSongs. */
    for (p = json; p + 7 < end; ++p)
        if (*p == '"' && p[1] == 's' && p[2] == 'o' && p[3] == 'n' && p[4] == 'g' &&
            (p[5] == '"' || (p[5] == 's' && p[6] == '"'))) {
            const char *q = sb_ws(p + (p[5] == 's' ? 7 : 6), end);
            if (q < end && *q == ':') {
                q = sb_ws(q + 1, end);
                if (q < end && *q == '[') {
                    arr = q + 1;
                    break;
                }
            }
        }
    if (!arr) return 0;
    p = arr;
    while (p < end && count < max) {
        const char *q;
        p = sb_ws(p, end);
        if (p >= end || *p == ']') break;
        if (*p == ',') {
            ++p;
            continue;
        }
        if (*p != '{' || depth++ > (unsigned)max) return -1;
        q = sb_skip(p, end);
        if (!q) return -1;
        arrend = q;
        {
            sb_song_t *s = out + count;
            unsigned v = 0;
            unsigned i;
            for (i = 0; i < sizeof(*s); ++i) ((unsigned char *)s)[i] = 0;
            sb_field(p, arrend, "id", s->id, sizeof s->id);
            sb_field(p, arrend, "title", s->title, sizeof s->title);
            sb_field(p, arrend, "artist", s->artist, sizeof s->artist);
            sb_field(p, arrend, "album", s->album, sizeof s->album);
            sb_field(p, arrend, "coverArt", s->cover, sizeof s->cover);
            sb_field(p, arrend, "suffix", s->suffix, sizeof s->suffix);
            (void)sb_member(p, arrend, "duration", (char *)0, 0, &v);
            s->duration = v;
            v = 0;
            (void)sb_member(p, arrend, "track", (char *)0, 0, &v);
            s->track = v;
            v = 0;
            (void)sb_member(p, arrend, "discNumber", (char *)0, 0, &v);
            s->disc = v;
            v = 0;
            (void)sb_member(p, arrend, "size", (char *)0, 0, &v);
            s->size = v;
            v = 0;
            (void)sb_member(p, arrend, "bitRate", (char *)0, 0, &v);
            s->bitrate = v;
            v = 0;
            (void)sb_member(p, arrend, "samplingRate", (char *)0, 0, &v);
            s->sample_rate = v;
            v = 0;
            (void)sb_member(p, arrend, "bitDepth", (char *)0, 0, &v);
            s->bit_depth = v;
            if (s->id[0]) ++count;
        }
        p = q;
    }
    return count;
}

/* Navidrome integration uses the stock MPlayer queue path. The player receives
 * the original Subsonic stream URL (format=raw); the payload never decodes or
 * re-encodes audio. Downloads use a .part file then rename onto the SD card.
 * The queue ABI was cross-checked against shivaluma/shanling-m1plus-navidrome
 * (MIT, Copyright 2026 shivaluma and contributors); this implementation is
 * native to this payload and does not copy its plugin or backend. */
#define SB_RESPONSE_MAX (512 * 1024)
#define SB_DOWNLOAD_MAX (512LL * 1024 * 1024)
#define SB_OFFLINE_DIR "/mnt/mmc/Navidrome"
#define SB_CONFIG_FILE "/mnt/mmc/.m1plus/navidrome.conf"
#define SB_CONFIG_TMP "/mnt/mmc/.m1plus/navidrome.conf.tmp"
#define SB_INDEX_FILE "/mnt/mmc/.m1plus/navidrome.index"
#define SB_INDEX_TMP "/mnt/mmc/.m1plus/navidrome.index.tmp"
#define SB_DSD_TMP "/mnt/mmc/.m1plus/navidrome.dsd.tmp"
#define SB_ART_DIR "/mnt/mmc/.m1plus/navidrome-art"
#define SB_ART_MAX (2LL * 1024 * 1024)
#define SB_VIEW_FILE "/mnt/mmc/.m1plus/navidrome-view"
#define SB_VIEW_TMP "/mnt/mmc/.m1plus/navidrome-view.tmp"
#define SB_INDEX_MAGIC "SBIDX2\0\0"
#define SB_SYNC_LIMIT 20000
#define SB_ROW_H 52
#define SB_GRID_PITCH 210
#define SB_GRID_COVER 136
#define SB_CA "/etc/m1plus-cacert.pem"
#define SB_VISIBLE 6
enum { SB_VIEW_TRACKS, SB_VIEW_SEARCH, SB_VIEW_DSD };
enum { SB_SETUP_USER = 1, SB_SETUP_PASSWORD = 2 };
typedef struct {
    char data[SB_RESPONSE_MAX];
    unsigned char prefix[8];
    unsigned prefix_used;
    unsigned used;
    int fd;
    long long written, last_check, limit;
} sb_sink_t;
static struct {
    void *win, *status, *scroll, *rows, *connect, *connect_label, *connected_dot, *view_button, *view_icon;
    void *row[SB_VISIBLE], *title[SB_VISIBLE], *sub[SB_VISIBLE], *art[SB_VISIBLE];
    void *grid_row[SB_VISIBLE], *grid_title[SB_VISIBLE], *grid_sub[SB_VISIBLE], *grid_art[SB_VISIBLE];
    void *row_play[SB_VISIBLE], *row_download[SB_VISIBLE], *row_download_icon[SB_VISIBLE];
    void *grid_play[SB_VISIBLE], *grid_download[SB_VISIBLE], *grid_download_icon[SB_VISIBLE];
    void *tab_label[2], *tab_mark[2];
    unsigned timer;
    volatile int busy, done, result, mode, sync_count;
    int sync_shown, setup_prompt, setup_tries;
    int count, selected, index_count, dsd_count, index_offset, indexed_view, loading, view;
    int row_data, row_base;
    int grid_mode, dsd_view, connected, index_valid, art_shown, switching_view;
    volatile int art_syncing, art_count, art_total;
    sb_song_t songs[SB_MAX];
    int play_ids[SB_MAX], play_count;
    char play_cover[SB_MAX][SB_ID], cover_file[256];
    char setup_base[256], setup_user[128];
    char base[256], user[128], password[128], query[256];
} sbp __attribute__((section(".scratch")));

typedef struct {
    char magic[8];
    unsigned count, dsd_count;
    char server[256], user[128];
} sb_index_head_t;

static unsigned sb_write(void *ptr, unsigned size, unsigned nmemb, void *ctx) {
    sb_sink_t *s = (sb_sink_t *)ctx;
    unsigned n = size * nmemb;
    if (!s || (size && n / size != nmemb)) return 0;
    if (s->fd >= 0) {
        unsigned done = 0;
        long long limit = s->limit ? s->limit : SB_DOWNLOAD_MAX;
        if (s->prefix_used < sizeof s->prefix) {
            unsigned take = (unsigned)sizeof s->prefix - s->prefix_used;
            if (take > n) take = n;
            memcpy(s->prefix + s->prefix_used, ptr, take);
            s->prefix_used += take;
        }
        if (s->written + n > limit) return 0;
        if (s->written - s->last_check >= 1024 * 1024) {
            unsigned free_kb = 0;
            if (!pn_free_kb("/mnt/mmc", &free_kb) || free_kb <= 32768) return 0;
            s->last_check = s->written;
        }
        while (done < n) {
            int wrote = write(s->fd, (const char *)ptr + done, n - done);
            if (wrote <= 0) return 0;
            done += (unsigned)wrote;
        }
        s->written += n;
        return n;
    }
    if (n >= sizeof(s->data) - s->used) return 0;
    memcpy(s->data + s->used, ptr, n);
    s->used += n;
    s->data[s->used] = 0;
    return n;
}

static int sb_http(const char *url, sb_sink_t *sink) {
    void *h = curl_easy_init();
    int rc;
    if (!h) return -1;
    curl_easy_setopt(h, CURLOPT_URL, url);
    curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, sb_write);
    curl_easy_setopt(h, CURLOPT_WRITEDATA, sink);
    curl_easy_setopt(h, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT, 15L);
    curl_easy_setopt(h, CURLOPT_TIMEOUT, 180L);
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_LIMIT, 512L);
    curl_easy_setopt(h, CURLOPT_LOW_SPEED_TIME, 45L);
    curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(h, CURLOPT_PROTOCOLS, sb_https(url) ? CURLPROTO_HTTPS : CURLPROTO_HTTP);
    if (sb_https(url)) curl_easy_setopt(h, CURLOPT_CAINFO, SB_CA);
    rc = curl_easy_perform(h);
    curl_easy_cleanup(h);
    return rc == 0 ? 0 : -1;
}

static int sb_make_search_url(char *url, unsigned cap, const char *query) {
    char extra[1024];
    unsigned n;
    int k;
    k = snprintf(extra, sizeof extra, "&query=");
    if (k < 0 || (unsigned)k >= sizeof extra) return -1;
    n = sb_urlenc(extra, sizeof extra, (unsigned)k, query);
    if (!n) return -1;
    k = snprintf(extra + n, sizeof extra - n, "&songCount=%u&albumCount=0&artistCount=0", SB_MAX);
    if (k < 0 || (unsigned)k >= sizeof extra - n) return -1;
    return sb_url(url, cap, sbp.base, "search3", 0, sbp.user, sbp.password, extra);
}

static int sb_write_all(int fd, const void *data, unsigned size) {
    const char *p = (const char *)data;
    unsigned done = 0;
    while (done < size) {
        int n = write(fd, p + done, size - done);
        if (n <= 0) return 0;
        done += (unsigned)n;
    }
    return 1;
}

static int sb_bytes_equal(const char *a, const char *b, unsigned n) {
    unsigned i;
    for (i = 0; i < n; ++i)
        if (a[i] != b[i]) return 0;
    return 1;
}

static int sb_write_song_records(int fd, const sb_song_t *songs, unsigned count) {
    return !count || sb_write_all(fd, songs, count * (unsigned)sizeof(*songs));
}

static int sb_fixed_equal(const char *field, unsigned cap, const char *value) {
    unsigned i;
    for (i = 0; i < cap; ++i) {
        if (field[i] != value[i]) return 0;
        if (!field[i]) return 1;
    }
    return 0;
}

static void sb_song_copy(sb_song_t *dst, const sb_song_t *src) {
    unsigned i;
    for (i = 0; i < sizeof *dst; ++i) ((unsigned char *)dst)[i] = ((const unsigned char *)src)[i];
}

static int sb_sync_library(sb_sink_t *sink) {
    sb_index_head_t head;
    char url[SB_URL], extra[128];
    sb_song_t dsd[SB_MAX];
    unsigned offset = 0, regular = 0, dsd_count = 0, free_kb = 0, i;
    int fd = -1, dfd = -1, rc = -1, n, k;
    if (!pod_card_mounted() || !pn_free_kb("/mnt/mmc", &free_kb) || free_kb < 32768) return -1;
    mkdir(CARD_DIR, 0755);
    fd = open(SB_INDEX_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    dfd = open(SB_DSD_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0 || dfd < 0) goto done;
    memset(&head, 0, sizeof head);
    memcpy(head.magic, SB_INDEX_MAGIC, sizeof head.magic);
    memcpy(head.server, sbp.base, sizeof head.server);
    memcpy(head.user, sbp.user, sizeof head.user);
    if (!sb_write_all(fd, &head, sizeof head)) goto done;
    for (;;) {
        if (!pod_card_mounted()) goto done;
        memset(sink, 0, sizeof *sink);
        sink->fd = -1;
        k = sb_sync_query(extra, sizeof extra, offset);
        if (k < 0 ||
            sb_url(url, sizeof url, sbp.base, "search3", 0, sbp.user, sbp.password, extra) || sb_http(url, sink))
            goto done;
        n = sb_songs(sink->data, sink->used, sbp.songs, SB_MAX);
        if (n < 0) goto done;
        if (!n) {
            rc = 0;
            break;
        }
        if (offset + (unsigned)n > SB_SYNC_LIMIT) goto done;
        {
            unsigned ndsd = 0, nregular = 0;
            for (i = 0; i < (unsigned)n; ++i) {
                if (sb_is_dsd(sbp.songs[i].suffix)) sb_song_copy(&dsd[ndsd++], &sbp.songs[i]);
                else sb_song_copy(&sbp.songs[nregular++], &sbp.songs[i]);
            }
            if (!sb_write_song_records(fd, sbp.songs, nregular) || !sb_write_song_records(dfd, dsd, ndsd)) goto done;
            regular += nregular;
            dsd_count += ndsd;
        }
        offset += (unsigned)n;
        sbp.sync_count = (int)offset;
        if ((unsigned)n < SB_SYNC_PAGE) {
            rc = 0;
            break;
        }
        if (!pn_free_kb("/mnt/mmc", &free_kb) || free_kb < 32768) goto done;
    }
    if (!offset) goto done;
    head.count = regular;
    head.dsd_count = dsd_count;
    if (!pod_card_mounted() || lseek(fd, 0, 0) < 0 || !sb_write_all(fd, &head, sizeof head) || fsync(dfd) ||
        lseek(dfd, 0, 0) < 0 || lseek(fd, 0, 2) < 0)
        goto done;
    {
        char copy[4096];
        int got;
        close(dfd);
        dfd = open(SB_DSD_TMP, O_RDONLY, 0);
        if (dfd < 0) goto done;
        while ((got = read(dfd, copy, sizeof copy)) > 0)
            if (!sb_write_all(fd, copy, (unsigned)got)) goto done;
        if (got < 0 || fsync(fd)) goto done;
    }
    close(dfd);
    dfd = -1;
    if (close(fd)) {
        fd = -1;
        goto done;
    }
    fd = -1;
    if (!pod_card_mounted() || rename(SB_INDEX_TMP, SB_INDEX_FILE)) goto done;
    unlink(SB_DSD_TMP);
    {
        int dir = open(CARD_DIR, O_RDONLY, 0);
        if (dir < 0) goto done;
        rc = fsync(dir) ? -1 : 1;
        close(dir);
    }
done:
    if (fd >= 0) close(fd);
    if (dfd >= 0) close(dfd);
    if (rc != 1) unlink(SB_INDEX_TMP);
    if (rc != 1) unlink(SB_DSD_TMP);
    return rc == 1 ? (int)offset : -1;
}

static unsigned sb_art_hash(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h;
}

static int sb_art_path(char *out, unsigned cap, const char *id) {
    unsigned h = sb_art_hash(sbp.base);
    char name[16];
    h = (h ^ sb_art_hash(sbp.user)) * 16777619u;
    h = (h ^ sb_art_hash(id)) * 16777619u;
    snprintf(name, sizeof name, "%08x.jpg", h);
    return snprintf(out, cap, SB_ART_DIR "/%s", name) < (int)cap ? 0 : -1;
}

static int sb_offline_path(const sb_song_t *song, char *out, unsigned cap, int unique_dsd) {
    char name[112], ext[12];
    unsigned i, n = 0;
    if (!song || !out || !cap) return -1;
    if (unique_dsd && sb_is_dsd(song->suffix)) {
        unsigned h = sb_art_hash(song->id);
        int k = snprintf(name, sizeof name, "%08x-", h);
        if (k < 0 || (unsigned)k >= sizeof name) return -1;
        n = (unsigned)k;
    }
    for (i = 0; song->title[i] && n < 100; ++i) {
        unsigned c = (unsigned char)song->title[i];
        name[n++] = (c < 32 || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' ||
                     c == '<' || c == '>' || c == '|') ? '_' : (char)c;
    }
    if (!n) { memcpy(name, "track", 5); n = 5; }
    name[n] = 0;
    n = 0;
    for (i = 0; song->suffix[i] && n + 1 < sizeof ext; ++i) {
        unsigned c = (unsigned char)song->suffix[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) ext[n++] = (char)c;
    }
    if (!n) { memcpy(ext, "audio", 5); n = 5; }
    ext[n] = 0;
    {
        int k = snprintf(out, cap, "%s/%s.%s", SB_OFFLINE_DIR, name, ext);
        return k >= 0 && (unsigned)k < cap ? 0 : -1;
    }
}

static int sb_offline_find(const sb_song_t *song, char *out, unsigned cap) {
    if (sb_offline_path(song, out, cap, 1) == 0 && access(out, 0) == 0) return 1;
    if (sb_offline_path(song, out, cap, 0) == 0 && access(out, 0) == 0) return 1;
    return 0;
}

static void sb_set_active_tab(int active) {
    unsigned c = pal_fill();
    char ink[8];
    unsigned i;
    snprintf(ink, sizeof ink, "#%02x%02x%02x", c & 255u, (c >> 8) & 255u, (c >> 16) & 255u);
    for (i = 0; i < 2; ++i) {
        if (sbp.tab_label[i]) widget_set_prop_str(sbp.tab_label[i], "style:normal:text_color", (int)i == active ? ink : "#FFFFFF");
        if (sbp.tab_mark[i]) {
            widget_set_prop_str(sbp.tab_mark[i], "style:normal:bg_color", ink);
            widget_set_visible(sbp.tab_mark[i], (int)i == active, 0);
        }
    }
}

static void sb_set_connected(int connected) {
    sbp.connected = !!connected;
    if (sbp.connected_dot)
        widget_set_prop_str(sbp.connected_dot, "style:normal:bg_color", sbp.connected ? "#34C759" : "#8E8E93");
    if (sbp.connect_label)
        widget_set_text_utf8(sbp.connect_label, TR(sbp.connected ? "Connected" : "Server"));
}

static int sb_fetch_art(sb_sink_t *sink, const char *id) {
    char url[SB_URL], path[256], part[272], extra[32];
    unsigned free_kb = 0;
    int fd, ok = 0;
    if (!id[0] || !pod_card_mounted() || !pn_free_kb("/mnt/mmc", &free_kb) || free_kb < 34816 ||
        sb_art_path(path, sizeof path, id) || access(path, 0) == 0) return 0;
    mkdir(CARD_DIR, 0755);
    mkdir(SB_ART_DIR, 0755);
    snprintf(extra, sizeof extra, "&size=240");
    if (sb_url(url, sizeof url, sbp.base, "getCoverArt", id, sbp.user, sbp.password, extra) ||
        snprintf(part, sizeof part, "%s.part", path) >= (int)sizeof part) return 0;
    fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    memset(sink, 0, sizeof *sink);
    sink->fd = fd;
    sink->limit = SB_ART_MAX;
    if (!sb_http(url, sink) && sink->written > 4 && sink->prefix_used >= 4 &&
        sink->prefix[0] == 0xff && sink->prefix[1] == 0xd8 && sink->prefix[2] == 0xff &&
        fsync(fd) == 0 && close(fd) == 0) {
        fd = -1;
        ok = rename(part, path) == 0;
    }
    if (fd >= 0) close(fd);
    if (!ok) unlink(part);
    sink->fd = -1;
    return ok;
}

static void sb_sync_art(sb_sink_t *sink) {
    sb_index_head_t head;
    sb_song_t song;
    unsigned i, total;
    int fd = open(SB_INDEX_FILE, O_RDONLY, 0);
    if (fd < 0 || read(fd, &head, sizeof head) != sizeof head) { if (fd >= 0) close(fd); return; }
    total = head.count + head.dsd_count;
    sbp.art_syncing = 1;
    sbp.art_count = sbp.art_total = 0;
    for (i = 0; i < total && pod_card_mounted(); ++i) {
        if (read(fd, &song, sizeof song) != sizeof song) break;
        if (song.cover[0]) (void)sb_fetch_art(sink, song.cover);
        sbp.art_count = (int)i + 1;
        sbp.art_total = (int)total;
    }
    close(fd);
    sbp.art_syncing = 0;
}

const char *sb_cover_file(void *track) {
    unsigned i;
    int id;
    if (!track) return (const char *)0;
    id = *(int *)((char *)track + REC_ID);
    for (i = 0; i < (unsigned)sbp.play_count; ++i) {
        char path[256];
        if (sbp.play_ids[i] != id || !sbp.play_cover[i][0] || sb_art_path(path, sizeof path, sbp.play_cover[i]) ||
            access(path, 0) != 0) continue;
        memcpy(sbp.cover_file, path, sizeof path);
        return sbp.cover_file;
    }
    return (const char *)0;
}

static int sb_index_load(unsigned offset, int dsd_view) {
    sb_index_head_t head;
    unsigned count, base;
    int fd = open(SB_INDEX_FILE, O_RDONLY, 0), n, i, file_size;
    if (fd < 0) return -1;
    n = read(fd, &head, sizeof head);
    if (n != sizeof head || !sb_bytes_equal(head.magic, SB_INDEX_MAGIC, sizeof head.magic) ||
        !(head.count + head.dsd_count) ||
        head.count + head.dsd_count > SB_SYNC_LIMIT || !sb_fixed_equal(head.server, sizeof head.server, sbp.base) ||
        !sb_fixed_equal(head.user, sizeof head.user, sbp.user)) {
        close(fd);
        return -1;
    }
    count = dsd_view ? head.dsd_count : head.count;
    base = dsd_view ? head.count : 0;
    if (offset > count || (count && offset == count)) {
        close(fd);
        return -1;
    }
    file_size = (int)lseek(fd, 0, 2);
    if (file_size != (int)(sizeof head + (head.count + head.dsd_count) * sizeof(sb_song_t)) ||
        lseek(fd, (int)(sizeof head + (base + offset) * sizeof(sb_song_t)), 0) < 0) {
        close(fd);
        return -1;
    }
    sbp.count = 0;
    for (i = 0; i < SB_MAX && offset + (unsigned)i < count; ++i) {
        if (read(fd, &sbp.songs[i], sizeof(sb_song_t)) != sizeof(sb_song_t)) {
            sbp.count = 0;
            close(fd);
            return -1;
        }
        ++sbp.count;
    }
    close(fd);
    sbp.dsd_count = (int)head.dsd_count;
    sbp.index_count = (int)count;
    sbp.index_offset = (int)offset;
    sbp.indexed_view = 1;
    sbp.dsd_view = dsd_view;
    sbp.view = dsd_view ? SB_VIEW_DSD : SB_VIEW_TRACKS;
    sbp.selected = -1;
    sbp.index_valid = 1;
    return sbp.count;
}

static void sb_resize_rows(void);
static void sb_place_rows(unsigned first);
static void sb_render_rows(void);

static int sb_show_library(int dsd_view) {
    int n;
    sbp.switching_view = 1;
    n = sb_index_load(0, dsd_view);
    if (n < 0) {
        sbp.count = sbp.index_count = sbp.index_offset = 0;
        sbp.indexed_view = 1;
        sbp.dsd_view = dsd_view;
        sbp.view = dsd_view ? SB_VIEW_DSD : SB_VIEW_TRACKS;
        sbp.selected = -1;
        sbp.index_valid = 0;
    }
    sbp.row_data = 0;
    sbp.row_base = -1;
    widget_set_prop_int(sbp.scroll, "yoffset", 0);
    sb_resize_rows();
    sb_place_rows(0);
    sb_render_rows();
    sb_set_active_tab(dsd_view);
    sbp.switching_view = 0;
    return n;
}

static unsigned sb_first_row(void) {
    int offset = sbp.scroll ? widget_get_prop_int(sbp.scroll, "yoffset", 0) : 0;
    if (offset < 0) offset = 0;
    return sbp.grid_mode ? (unsigned)offset / SB_GRID_PITCH * 2u : (unsigned)offset / SB_ROW_H;
}

static void sb_place_rows(unsigned first) {
    unsigned i;
    sbp.row_base = (int)first;
    for (i = 0; i < SB_VISIBLE; ++i) {
        unsigned cell = first + i;
        widget_move(sbp.row[i], 0, (int)cell * SB_ROW_H);
        widget_move(sbp.grid_row[i], (int)(cell % 2) * 160, (int)(cell / 2) * SB_GRID_PITCH);
        widget_set_visible(sbp.row[i], !sbp.grid_mode, 0);
        widget_set_visible(sbp.grid_row[i], sbp.grid_mode, 0);
        widget_set_sensitive(sbp.row[i], !sbp.grid_mode);
        widget_set_sensitive(sbp.grid_row[i], sbp.grid_mode);
    }
}

static void sb_resize_rows(void) {
    unsigned count = sbp.indexed_view ? (unsigned)sbp.index_count : (unsigned)sbp.count;
    unsigned height;
    if (!count) count = 1;
    if (count > SB_SYNC_LIMIT) count = SB_SYNC_LIMIT;
    height = sbp.grid_mode ? ((count + 1) / 2) * SB_GRID_PITCH : count * SB_ROW_H;
    if (height < SB_VISIBLE * SB_ROW_H) height = SB_VISIBLE * SB_ROW_H;
    if (sbp.rows) widget_resize(sbp.rows, 320, (int)height);
}

static void sb_render_rows(void) {
    int i;
    for (i = 0; i < SB_VISIBLE; ++i) {
        char detail[SB_TEXT + 24];
        int local_dsd = 0;
        int source = sbp.row_data + i;
        int track_actions = source >= 0 && source < sbp.count &&
                            (sbp.view == SB_VIEW_SEARCH || sbp.view == SB_VIEW_DSD ||
                             (sbp.view == SB_VIEW_TRACKS && sbp.indexed_view));
        int is_dsd = track_actions && sb_is_dsd(sbp.songs[source].suffix);
        if (is_dsd) {
            char path[320];
            local_dsd = sb_offline_find(&sbp.songs[source], path, sizeof path);
            widget_set_prop_str(sbp.row_download_icon[i], "image", local_dsd ? "pod_ic_rd_remove" : "pod_sb_download");
            widget_set_prop_str(sbp.grid_download_icon[i], "image", local_dsd ? "pod_ic_rd_remove" : "pod_sb_download");
        } else {
            widget_set_prop_str(sbp.row_download_icon[i], "image", "pod_sb_download");
            widget_set_prop_str(sbp.grid_download_icon[i], "image", "pod_sb_download");
        }
        widget_resize(sbp.title[i], track_actions ? 152 : 278, 24);
        widget_resize(sbp.sub[i], track_actions ? 152 : 278, 20);
        widget_set_visible(sbp.art[i], track_actions, 0);
        widget_set_visible(sbp.row_play[i], track_actions && !sbp.grid_mode && (!is_dsd || local_dsd), 0);
        widget_set_sensitive(sbp.row_play[i], track_actions && !sbp.grid_mode && (!is_dsd || local_dsd));
        widget_set_visible(sbp.row_download[i], track_actions && !sbp.grid_mode, 0);
        widget_set_sensitive(sbp.row_download[i], track_actions && !sbp.grid_mode);
        widget_set_visible(sbp.grid_play[i], track_actions && sbp.grid_mode && (!is_dsd || local_dsd), 0);
        widget_set_sensitive(sbp.grid_play[i], track_actions && sbp.grid_mode && (!is_dsd || local_dsd));
        widget_set_visible(sbp.grid_download[i], track_actions && sbp.grid_mode, 0);
        widget_set_sensitive(sbp.grid_download[i], track_actions && sbp.grid_mode);
        if (source >= 0 && source < sbp.count) {
            char art[256], uri[272];
            widget_set_text_utf8(sbp.title[i], sbp.songs[source].title[0] ? sbp.songs[source].title : TR("Untitled"));
            snprintf(detail, sizeof detail, "%s  •  %s", sbp.songs[source].artist, sbp.songs[source].album);
            widget_set_text_utf8(sbp.sub[i], detail);
            widget_set_text_utf8(sbp.grid_title[i], sbp.songs[source].title[0] ? sbp.songs[source].title : TR("Untitled"));
            widget_set_text_utf8(sbp.grid_sub[i], sbp.songs[source].artist);
            if (sbp.songs[source].cover[0] && !sb_art_path(art, sizeof art, sbp.songs[source].cover) && access(art, 0) == 0) {
                snprintf(uri, sizeof uri, "file://%s", art);
                widget_set_prop_str(sbp.art[i], "image", uri);
                widget_set_prop_str(sbp.grid_art[i], "image", uri);
            } else {
                widget_set_prop_str(sbp.art[i], "image", "pod_ic_songs");
                widget_set_prop_str(sbp.grid_art[i], "image", "pod_ic_songs");
            }
            widget_set_visible(sbp.title[i], 1, 0);
            widget_set_visible(sbp.sub[i], 1, 0);
        } else {
            widget_set_text_utf8(sbp.title[i], "");
            widget_set_text_utf8(sbp.sub[i], "");
            widget_set_text_utf8(sbp.grid_title[i], "");
            widget_set_text_utf8(sbp.grid_sub[i], "");
            widget_set_visible(sbp.art[i], 0, 0);
            widget_set_visible(sbp.title[i], 0, 0);
            widget_set_visible(sbp.sub[i], 0, 0);
        }
    }
}

static void *sb_worker(void *unused) {
    sb_sink_t *sink;
    char url[SB_URL];
    int rc = -1;
    (void)unused;
    sink = (sb_sink_t *)calloc(1, sizeof *sink);
    if (!sink) goto finished;
    sink->fd = -1;
    if (sbp.mode == 8 && !sb_url(url, sizeof url, sbp.base, "ping", 0, sbp.user, sbp.password, 0) &&
        !sb_http(url, sink) && sb_response(sink->data, sink->used))
        rc = 1;
    else if (sbp.mode == 1 && !sb_make_search_url(url, sizeof url, sbp.query)) {
        if (!sb_http(url, sink)) {
            int n = sb_songs(sink->data, sink->used, sbp.songs, SB_MAX), i, regular = 0;
            if (n >= 0) {
                for (i = 0; i < n; ++i)
                    if (!sb_is_dsd(sbp.songs[i].suffix)) {
                        if (regular != i) sb_song_copy(&sbp.songs[regular], &sbp.songs[i]);
                        ++regular;
                    }
                rc = regular;
            }
        }
    } else if (sbp.mode == 2 && sbp.selected >= 0 && sbp.selected < sbp.count) {
        sb_song_t *song = &sbp.songs[sbp.selected];
        char part[336], final[320];
        int fd;
        unsigned free_kb = 0;
        if ((!mkdir(SB_OFFLINE_DIR, 0775) || access(SB_OFFLINE_DIR, 0) == 0) && pn_free_kb("/mnt/mmc", &free_kb) &&
            free_kb > 32768) {
            if (sb_url(url, sizeof url, sbp.base, "download", song->id, sbp.user, sbp.password, 0))
                rc = -1;
            else if (sb_offline_path(song, final, sizeof final, 1) == 0 &&
                     snprintf(part, sizeof part, "%s.part", final) < (int)sizeof part && access(final, 0) != 0 &&
                     (fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644)) >= 0) {
                sink->fd = fd;
                if (!sb_http(url, sink) && fsync(fd) == 0 && close(fd) == 0) {
                    fd = -1;
                    if (rename(part, final) == 0) rc = 1;
                }
                if (fd >= 0) close(fd);
                if (rc != 1) unlink(part);
            }
        }
    } else if (sbp.mode == 3) {
        rc = sb_sync_library(sink);
        if (rc > 0) sb_sync_art(sink);
    }
    free(sink);
finished:
    sbp.result = rc;
    __sync_synchronize();
    sbp.done = 1;
    sbp.busy = 0;
    return 0;
}

static int sb_start(int mode) {
    unsigned long th = 0;
    if (get_wifisignal() <= 0) {
        sb_set_connected(0);
        if (sbp.status) {
            widget_set_text_utf8(sbp.status, TR("Connect to Wi-Fi before using Navidrome."));
            widget_set_prop_str(sbp.status, "style:normal:text_color", "#FF453A");
        }
        return -1;
    }
    if (sbp.busy || !sbp.user[0] || !sbp.password[0]) return -1;
    sbp.mode = mode;
    if (mode == 3) sbp.sync_count = sbp.sync_shown = sbp.art_shown = 0;
    sbp.done = 0;
    sbp.result = -1;
    curl_global_init(CURL_GLOBAL_ALL); /* initialize libcurl on the UI thread before this worker */
    __sync_synchronize();
    sbp.busy = 1;
    if (pthread_create(&th, (void *)0, sb_worker, (void *)0) != 0) {
        sbp.busy = 0;
        return -1;
    }
    pthread_detach(th);
    return 0;
}

static void sb_set_status(const char *text) {
    if (sbp.status) {
        widget_set_text_utf8(sbp.status, text);
        widget_set_prop_str(sbp.status, "style:normal:text_color", sbp.connected ? "#34C759" : "#AAAAAA");
    }
}
static void sb_config_done(const char *text);
static void sb_setup_user_done(const char *text);
static void sb_setup_password_done(const char *text);

/* keyboard_open refuses a second prompt until the previous keyboard's destroy
 * event clears its state. Chain the login fields after that close completes. */
static int sb_setup_next_prompt(const void *timer) {
    int rc = -1;
    (void)timer;
    if (!sbp.win || !sbp.setup_prompt) return RET_OK;
    if (sbp.setup_prompt == SB_SETUP_USER)
        rc = keyboard_open(TR("Navidrome"), TR("Username"), sbp.user, sb_setup_user_done, 0, KB_LONG);
    else if (sbp.setup_prompt == SB_SETUP_PASSWORD)
        rc = keyboard_open(TR("Navidrome"), TR("Server password"), 0, sb_setup_password_done, 0, KB_LONG);
    if (rc == 0) {
        sbp.setup_prompt = sbp.setup_tries = 0;
        return RET_OK;
    }
    if (++sbp.setup_tries < 40) return RET_REPEAT;
    sbp.setup_prompt = sbp.setup_tries = 0;
    pod_toast(TR("Could not open login field"));
    return RET_OK;
}

static void sb_setup_defer_prompt(int prompt) {
    sbp.setup_prompt = prompt;
    sbp.setup_tries = 0;
    if (!timer_add(sb_setup_next_prompt, (void *)0, 50)) {
        sbp.setup_prompt = 0;
        pod_toast(TR("Could not open login field"));
    }
}

static void sb_setup_url_done(const char *text) {
    unsigned n = sb_len(text);
    if (get_wifisignal() <= 0) {
        sb_set_status("Connect to Wi-Fi before adding a server.");
        if (sbp.status) widget_set_prop_str(sbp.status, "style:normal:text_color", "#FF453A");
        return;
    }
    if (!n || n >= sizeof sbp.setup_base || !sb_http_url(text) || sb_has_char(text, '|')) {
        pod_toast(TR("Enter a valid HTTP or HTTPS server URL"));
        return;
    }
    memcpy(sbp.setup_base, text, n + 1);
    while (n > 8 && sbp.setup_base[n - 1] == '/') sbp.setup_base[--n] = 0;
    sb_setup_defer_prompt(SB_SETUP_USER);
}

static void sb_setup_user_done(const char *text) {
    unsigned n = sb_len(text);
    if (!n || n >= sizeof sbp.setup_user || sb_has_char(text, '|')) {
        pod_toast(TR("Enter a valid username"));
        return;
    }
    memcpy(sbp.setup_user, text, n + 1);
    sb_setup_defer_prompt(SB_SETUP_PASSWORD);
}

static void sb_setup_password_done(const char *text) {
    char config[512];
    int n;
    if (!text[0]) {
        pod_toast(TR("Enter a server password"));
        return;
    }
    if (sb_has_char(text, '|')) {
        pod_toast(TR("Password cannot contain |"));
        return;
    }
    n = snprintf(config, sizeof config, "%s|%s|%s", sbp.setup_base, sbp.setup_user, text);
    memset(sbp.setup_base, 0, sizeof sbp.setup_base);
    memset(sbp.setup_user, 0, sizeof sbp.setup_user);
    if (n < 0 || (unsigned)n >= sizeof config) {
        pod_toast(TR("Server settings are too long"));
        return;
    }
    sb_config_done(config);
    memset(config, 0, sizeof config);
}

static void sb_setup_start(void) {
    if (get_wifisignal() <= 0) {
        sb_set_connected(0);
        sb_set_status("Connect to Wi-Fi before adding a server.");
        if (sbp.status) widget_set_prop_str(sbp.status, "style:normal:text_color", "#FF453A");
        return;
    }
    const char *initial = sbp.base[0] ? sbp.base : "http://";
    keyboard_open(TR("Navidrome"), TR("Server URL"), initial, sb_setup_url_done, 0, KB_LONG);
}

static int sb_scroll_event(void *ctx, void *e) {
    unsigned first = sb_first_row();
    (void)ctx;
    (void)e;
    if (sbp.busy || sbp.switching_view) return RET_OK;
    if (sbp.indexed_view && (sbp.view == SB_VIEW_TRACKS || sbp.view == SB_VIEW_DSD)) {
        unsigned base = first / SB_MAX * SB_MAX;
        if (first >= (unsigned)sbp.index_count) return RET_OK;
        if ((int)first == sbp.row_base) return RET_OK;
        sbp.selected = -1;
        if ((int)base != sbp.index_offset && sb_index_load(base, sbp.dsd_view) < 0) return RET_OK;
        sbp.row_data = (int)first - sbp.index_offset;
        sb_place_rows(first);
        sb_render_rows();
        return RET_OK;
    }
    if (sbp.view == SB_VIEW_SEARCH) {
        if (first >= (unsigned)sbp.count) return RET_OK;
        if ((int)first == sbp.row_base) return RET_OK;
        sbp.selected = -1;
        sbp.row_data = (int)first;
        sb_place_rows(first);
        sb_render_rows();
        return RET_OK;
    }
    return RET_OK;
}

static int sb_tracks_click(void *ctx, void *e) {
    int n;
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("A request is still running"));
        return RET_OK;
    }
    n = sb_show_library(0);
    if (n > 0) sb_set_status(TR("Songs"));
    else if (n == 0) sb_set_status(TR("No regular songs in the synced library"));
    else
        sb_set_status("Sync the library after connecting to the server.");
    return RET_OK;
}

static int sb_dsd_click(void *ctx, void *e) {
    int n;
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    n = sb_show_library(1);
    if (n >= 0) {
        sb_set_status(n ? "DSD downloads · original files only" : "No DSD tracks in the synced library");
    } else
        sb_set_status("Sync the library after connecting to the server.");
    return RET_OK;
}

static int sb_view_click(void *ctx, void *e) {
    unsigned first;
    const char *icon;
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    first = sb_first_row();
    sbp.grid_mode = !sbp.grid_mode;
    if (sbp.grid_mode) first = first / 2u * 2u;
    if (sbp.indexed_view && sbp.index_count) {
        unsigned base;
        if (first >= (unsigned)sbp.index_count) first = (unsigned)sbp.index_count - 1;
        if (sbp.grid_mode) first = first / 2u * 2u;
        base = first / SB_MAX * SB_MAX;
        sbp.switching_view = 1;
        if (sb_index_load(base, sbp.dsd_view) < 0) {
            sbp.grid_mode = !sbp.grid_mode;
            sbp.switching_view = 0;
            sb_set_status(TR("Could not refresh this song page"));
            return RET_OK;
        }
        sbp.row_data = (int)(first - base);
    } else {
        sbp.row_data = (int)first;
        sbp.switching_view = 1;
    }
    icon = sbp.grid_mode ? "pod_nav_list" : "pod_nav_grid";
    widget_set_prop_str(sbp.view_icon, "image", icon);
    widget_set_prop_str(sbp.view_button, "style:normal:icon", icon);
    widget_set_prop_str(sbp.view_button, "style:over:icon", icon);
    widget_set_prop_str(sbp.view_button, "style:pressed:icon", sbp.grid_mode ? "pod_nav_list_down" : "pod_nav_grid_down");
    (void)home_write_atomic(SB_VIEW_FILE, SB_VIEW_TMP, sbp.grid_mode ? "1\n" : "0\n");
    sb_resize_rows();
    sbp.row_base = -1;
    widget_set_prop_int(sbp.scroll, "yoffset", sbp.grid_mode ? (int)(first / 2) * SB_GRID_PITCH : (int)first * SB_ROW_H);
    sb_place_rows(first);
    sb_render_rows();
    sbp.switching_view = 0;
    return RET_OK;
}

static int sb_sync_click(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    if (!sbp.user[0] || !sbp.password[0]) {
        sb_setup_start();
        return RET_OK;
    }
    if (!pod_confirm(TR("Sync Navidrome songs and artwork to the SD card now?"))) return RET_OK;
    if (sb_start(3) == 0)
        sb_set_status("Syncing library to SD card…");
    else
        sb_set_status("Library sync could not start");
    return RET_OK;
}

static int sb_play_click(void *ctx, void *e);

static int sb_play_local_dsd(const sb_song_t *song, const char *path) {
    unsigned rec[REC_SIZE / 4];
    void *q;
    char *fields[5];
    const char *name = strrchr(path, '/');
    unsigned h;
    if (!name) name = path;
    else ++name;
    fields[0] = strdup(name);
    fields[1] = strdup(path);
    fields[2] = strdup(song->title[0] ? song->title : TR("Untitled"));
    fields[3] = strdup(song->album);
    fields[4] = strdup(song->artist);
    if (!fields[0] || !fields[1] || !fields[2] || !fields[3] || !fields[4]) {
        unsigned i;
        for (i = 0; i < 5; ++i) free(fields[i]);
        return -1;
    }
    memset(rec, 0, sizeof rec);
    h = sb_art_hash(song->id);
    *(int *)((char *)rec + REC_ID) = -(int)((h & 0x3fffffffu) + 2u);
    *(char **)((char *)rec + REC_NAME) = fields[0];
    *(char **)((char *)rec + REC_PATH) = fields[1];
    *(char **)((char *)rec + REC_TITLE) = fields[2];
    *(char **)((char *)rec + REC_ALBUM) = fields[3];
    *(char **)((char *)rec + REC_ARTIST) = fields[4];
    *(char **)((char *)rec + 0x24) = fields[4];
    *(char **)((char *)rec + 0x1c) = "";
    *(char **)((char *)rec + 0x20) = "";
    *(int *)((char *)rec + REC_TYPE) = 8;
    *(int *)((char *)rec + REC_CLASS) = 0;
    q = _create_deque("stSongInfo");
    if (!q) {
        unsigned i;
        for (i = 0; i < 5; ++i) free(fields[i]);
        return -1;
    }
    deque_init(q);
    _deque_push_back(q, rec);
    if (deque_size(q) != 1) {
        deque_destroy(q);
        {
            unsigned i;
            for (i = 0; i < 5; ++i) free(fields[i]);
        }
        return -1;
    }
    mclLoadPlayList(q, 0, 0);
    deque_destroy(q);
    mclSetStartSeekTime(0);
    start_playqueue(0);
    on_backtoplayer_onclick((void *)0, (void *)0);
    {
        unsigned i;
        for (i = 0; i < 5; ++i) free(fields[i]);
    }
    return 0;
}

/* Tapping a row starts playback, or downloads when it is in the DSD section. */
static int sb_select_click(void *ctx, void *e) {
    int at = (int)(long)ctx;
    (void)e;
    at += sbp.row_data;
    if (at < 0 || at >= sbp.count) return RET_OK;
    sbp.selected = at;
    if (sbp.dsd_view || sb_is_dsd(sbp.songs[at].suffix)) {
        char path[320];
        if (sb_offline_find(&sbp.songs[at], path, sizeof path)) {
            if (sb_play_local_dsd(&sbp.songs[at], path) == 0) return RET_OK;
            sb_set_status(TR("Could not play the downloaded DSD file"));
            return RET_OK;
        }
        if (sb_start(2) == 0) sb_set_status("Downloading original DSD file to SD…");
        else sb_set_status("DSD download could not start");
        return RET_OK;
    }
    return sb_play_click(0, 0);
}

static void sb_search_done(const char *text) {
    unsigned i;
    unsigned n = sb_len(text);
    if (n >= sizeof sbp.query) n = sizeof sbp.query - 1;
    for (i = 0; i < n; ++i) sbp.query[i] = text[i];
    sbp.query[n] = 0;
    if (sbp.busy) {
        sb_set_status(TR("A request is still running"));
        return;
    }
    sbp.indexed_view = 0;
    sbp.dsd_view = 0;
    sbp.view = SB_VIEW_SEARCH;
    sbp.row_data = 0;
    sbp.row_base = -1;
    sbp.count = 0;
    sbp.selected = -1;
    widget_set_prop_int(sbp.scroll, "yoffset", 0);
    if (sb_start(1) == 0)
        sb_set_status(TR("Searching Navidrome…"));
    else
        sb_set_status(TR("Search could not start"));
}

static void sb_config_done(const char *text) {
    char *a = 0, *b = 0;
    unsigned i, n = sb_len(text);
    if (n >= 500) {
        pod_toast(TR("Configuration is too long"));
        return;
    }
    for (i = 0; i < n; ++i)
        if (text[i] == '|') {
            if (!a)
                a = (char *)text + i;
            else {
                b = (char *)text + i;
                break;
            }
        }
    if (!a || !b) {
        pod_toast(TR("Enter URL|username|password"));
        return;
    }
    n = (unsigned)(a - text);
    if (n >= sizeof sbp.base) return;
    memcpy(sbp.base, text, n);
    sbp.base[n] = 0;
    while (n > 8 && sbp.base[n - 1] == '/') sbp.base[--n] = 0;
    n = (unsigned)(b - a - 1);
    if (n >= sizeof sbp.user) return;
    memcpy(sbp.user, a + 1, n);
    sbp.user[n] = 0;
    n = sb_len(b + 1);
    if (n >= sizeof sbp.password) return;
    memcpy(sbp.password, b + 1, n + 1);
    if (!sbp.loading) sbp.index_valid = 0;
    if (sb_url(sbp.query, sizeof sbp.query, sbp.base, "ping", 0, sbp.user, sbp.password, 0)) {
        memset(sbp.password, 0, sizeof sbp.password);
        pod_toast(TR("Server URL must use HTTP or HTTPS"));
        return;
    }
    if (!sbp.loading && get_wifisignal() <= 0) {
        sb_set_status("Connect to Wi-Fi before adding a server.");
        if (sbp.status) widget_set_prop_str(sbp.status, "style:normal:text_color", "#FF453A");
        memset(sbp.password, 0, sizeof sbp.password);
        return;
    }
    /* Credentials are stored only on the SD card, in a hidden app folder. The file is
     * plain text because the player has no device secret with which to encrypt it. */
    if (!sbp.loading && pod_card_mounted()) {
        int fd, dir, ok;
        mkdir(CARD_DIR, 0755);
        fd = open(SB_CONFIG_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        ok = fd >= 0;
        if (ok) {
            ok = sb_write_all(fd, text, sb_len(text)) && fsync(fd) == 0;
            ok = close(fd) == 0 && ok;
            if (ok) ok = pod_card_mounted() && rename(SB_CONFIG_TMP, SB_CONFIG_FILE) == 0;
            if (!ok) unlink(SB_CONFIG_TMP);
            dir = ok ? open(CARD_DIR, O_RDONLY, 0) : -1;
            if (dir >= 0) {
                ok = fsync(dir) == 0;
                close(dir);
            }
        }
        if (!ok)
            sb_set_status("Connected for this session; could not save settings to SD.");
        else
            sb_set_status("Navidrome settings saved on SD. Tap Search.");
    } else if (!sbp.loading)
        sb_set_status("Connected for this session; insert SD to save settings.");
    if (!sbp.loading) {
        sbp.indexed_view = 0;
        sbp.index_count = sbp.index_offset = 0;
        sbp.sync_count = 0;
        sb_set_connected(0);
        (void)sb_show_library(0);
        if (sb_start(8) == 0)
            sb_set_status("Checking Navidrome server…");
        else
                sb_set_status(TR("Could not check Navidrome server."));
    }
}

static void sb_config_load(void) {
    char text[500];
    int fd, n;
    if (sbp.user[0] || !pod_card_mounted()) return;
    fd = open(SB_CONFIG_FILE, O_RDONLY, 0);
    if (fd < 0) return;
    n = read(fd, text, sizeof text);
    close(fd);
    if (n <= 0 || n >= (int)sizeof text) return;
    text[n] = 0;
    /* Refuse truncated or multi-line files; the saved entry is exactly the setup form. */
    if (sb_len(text) != (unsigned)n || text[n - 1] == '\n') return;
    sbp.loading = 1;
    sb_config_done(text);
    sbp.loading = 0;
}

static int sb_connect_click(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    sb_setup_start();
    return RET_OK;
}
static int sb_search_click(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    if (!sbp.user[0] || !sbp.password[0]) {
        sb_setup_start();
        return RET_OK;
    }
    keyboard_open(TR("Navidrome Search"), TR("Search songs"), 0, sb_search_done, 0, KB_LONG);
    return RET_OK;
}

static int sb_play_click(void *ctx, void *e) {
    int at = sbp.selected;
    char *fields[5];
    unsigned rec[REC_SIZE / 4];
    int ids[SB_MAX];
    void *q;
    int i, n = sbp.count, queued = 0, play_at = -1, collision;
    (void)ctx;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("A request is still running"));
        return RET_OK;
    }
    if (at < 0 || at >= sbp.count) {
        pod_toast(TR("Select a song first"));
        return RET_OK;
    }
    if (sb_is_dsd(sbp.songs[at].suffix)) {
        sb_set_status("DSD streaming is disabled; download the original file for local playback.");
        return RET_OK;
    }
    sbp.selected = at;
    q = _create_deque("stSongInfo");
    if (!q) return RET_OK;
    deque_init(q);
    for (i = 0; i < n; ++i) {
        sb_song_t *song = &sbp.songs[i];
        char url[SB_URL], file_name[SB_TEXT + 16];
        unsigned h = 2166136261u, j;
        if (sb_is_dsd(song->suffix)) continue;
        if (sb_url(url, sizeof url, sbp.base, "stream", song->id, sbp.user, sbp.password, 0) ||
            sb_track_filename(file_name, sizeof file_name, song) < 0) break;
        for (j = 0; j < 5; ++j) fields[j] = 0;
        fields[0] = strdup(file_name[0] ? file_name : TR("Untitled"));
        fields[1] = strdup(url);
        fields[2] = strdup(song->title[0] ? song->title : TR("Untitled"));
        fields[3] = strdup(song->album);
        fields[4] = strdup(song->artist);
        if (!fields[0] || !fields[1] || !fields[2] || !fields[3] || !fields[4]) {
            for (j = 0; j < 5; ++j) free(fields[j]);
            break;
        }
        memset(rec, 0, sizeof rec);
        for (j = 0; song->id[j]; ++j) h = (h ^ (unsigned char)song->id[j]) * 16777619u;
        ids[queued] = -(int)((h & 0x3fffffffu) + 2u);
        do {
            collision = 0;
            for (j = 0; j < (unsigned)queued; ++j)
                if (ids[j] == ids[queued]) {
                    collision = 1;
                    break;
                }
            if (collision) ids[queued] = ids[queued] == -1073741825 ? -2 : ids[queued] - 1;
        } while (collision);
        *(int *)((char *)rec + REC_ID) = ids[queued];
        *(char **)((char *)rec + REC_NAME) = fields[0];
        *(char **)((char *)rec + REC_PATH) = fields[1];
        *(char **)((char *)rec + REC_TITLE) = fields[2];
        *(char **)((char *)rec + REC_ALBUM) = fields[3];
        *(char **)((char *)rec + REC_ARTIST) = fields[4];
        *(char **)((char *)rec + 0x24) = fields[4]; /* album artist */
        *(char **)((char *)rec + 0x1c) = "";
        *(char **)((char *)rec + 0x20) = "";
        *(int *)((char *)rec + REC_TYPE) = 8;
        *(int *)((char *)rec + REC_CLASS) = 0;
        *(int *)((char *)rec + REC_TRACK) = (int)song->track;
        *(int *)((char *)rec + REC_DISC) = (int)song->disc;
        if (i == at) play_at = queued;
        _deque_push_back(q, rec);
        ++queued;
        for (j = 0; j < 5; ++j) free(fields[j]);
    }
    if ((int)deque_size(q) != queued || play_at < 0) {
        deque_destroy(q);
        pod_toast(TR("Could not prepare stream queue"));
        return RET_OK;
    }
    sbp.play_count = queued;
    queued = 0;
    for (i = 0; i < n; ++i) {
        sb_song_t *song = &sbp.songs[i];
        unsigned h = 2166136261u, j;
        if (sb_is_dsd(song->suffix)) continue;
        for (j = 0; song->id[j]; ++j) h = (h ^ (unsigned char)song->id[j]) * 16777619u;
        sbp.play_ids[queued] = -(int)((h & 0x3fffffffu) + 2u);
        memcpy(sbp.play_cover[queued], song->cover, sizeof sbp.play_cover[queued]);
        ++queued;
    }
    mclLoadPlayList(q, play_at, 0);
    deque_destroy(q);
    mclSetStartSeekTime(0);
    start_playqueue(play_at);
    on_backtoplayer_onclick((void *)0, (void *)0);
    return RET_OK;
}
static int sb_row_play_click(void *ctx, void *e) {
    int at = (int)(long)ctx + sbp.row_data;
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    if (at < 0 || at >= sbp.count) {
        pod_toast(TR("Select a song first"));
        return RET_OK;
    }
    sbp.selected = at;
    if (sb_is_dsd(sbp.songs[at].suffix)) {
        char path[320];
        if (!sb_offline_find(&sbp.songs[at], path, sizeof path)) {
            sb_set_status(TR("Download this DSD track first"));
            return RET_OK;
        }
        if (sb_play_local_dsd(&sbp.songs[at], path) < 0)
            sb_set_status(TR("Could not play the downloaded DSD file"));
        return RET_OK;
    }
    return sb_play_click(0, 0);
}

static int sb_delete_dsd(int at) {
    char path[320];
    if (at < 0 || at >= sbp.count || !sb_is_dsd(sbp.songs[at].suffix) ||
        !sb_offline_find(&sbp.songs[at], path, sizeof path)) return -1;
    if (!pod_confirm(TR("Delete this downloaded DSD track from the SD card?"))) return 0;
    if (!pod_card_mounted() || unlink(path)) {
        sb_set_status(TR("Could not delete the downloaded DSD file"));
        return -1;
    }
    sb_render_rows();
    sb_set_status(TR("Downloaded DSD track deleted"));
    return 1;
}

static int sb_row_download_click(void *ctx, void *e) {
    int at = (int)(long)ctx + sbp.row_data;
    char path[320];
    (void)e;
    if (sbp.busy) {
        sb_set_status(TR("Wait for the current request to finish"));
        return RET_OK;
    }
    if (at < 0 || at >= sbp.count) {
        pod_toast(TR("Select a song first"));
        return RET_OK;
    }
    sbp.selected = at;
    if (sb_is_dsd(sbp.songs[at].suffix) && sb_offline_find(&sbp.songs[at], path, sizeof path)) {
        (void)sb_delete_dsd(at);
        return RET_OK;
    }
    if (sb_start(2) == 0)
        sb_set_status("Downloading original file to SD card…");
    else
        sb_set_status("Download could not start");
    return RET_OK;
}
static int sb_tick(const void *unused) {
    (void)unused;
    if (!sbp.win) return RET_OK;
    if (sbp.busy && sbp.mode == 3 && sbp.sync_count != sbp.sync_shown) {
        char msg[64];
        sbp.sync_shown = sbp.sync_count;
        snprintf(msg, sizeof msg, TR("%d tracks synced…"), sbp.sync_shown);
        sb_set_status(msg);
    }
    if (sbp.busy && sbp.mode == 3 && sbp.art_syncing && !sbp.art_shown) {
        sbp.art_shown = 1;
        sb_set_status(TR("Syncing cover artwork to SD…"));
    }
    if (sbp.done) {
        __sync_synchronize();
        sbp.done = 0;
        if (sbp.mode == 8) {
            if (sbp.result > 0) {
                sb_set_connected(1);
                sb_set_status("Connected to Navidrome");
                if (!sbp.index_valid) {
                    if (sb_start(3) == 0) sb_set_status("Connected · syncing songs and artwork…");
                }
            } else {
                sb_set_connected(0);
                sb_set_status("Could not connect. Check Wi-Fi, URL and login.");
            }
        } else if (sbp.mode == 1) {
            sbp.count = sbp.result < 0 ? 0 : sbp.result;
            sbp.view = SB_VIEW_SEARCH;
            sbp.row_data = 0;
            sbp.selected = -1;
            sb_resize_rows();
            sb_place_rows(0);
            sb_render_rows();
            if (sbp.result < 0)
                sb_set_status("Search failed. Check Wi-Fi, server, and credentials.");
            else if (!sbp.count)
                sb_set_status("No songs found");
            else {
                char msg[64];
                snprintf(msg, sizeof msg, "%d results. Use a row's play or download icon.", sbp.count);
                sb_set_status(msg);
            }
        } else if (sbp.mode == 3) {
            if (sbp.result > 0 && sb_index_load(0, 0) > 0) {
                sbp.row_data = 0;
                sbp.dsd_view = 0;
                widget_set_prop_int(sbp.scroll, "yoffset", 0);
                sb_resize_rows();
                sb_place_rows(0);
                sb_render_rows();
                {
                    sb_set_status(TR("Sync complete. Artwork cached when available."));
                }
            } else
                sb_set_status("Library sync failed; check Wi-Fi, server and SD space.");
        } else {
            if (sbp.mode == 2 && sbp.result > 0) sb_render_rows();
            sb_set_status(sbp.result > 0 ? TR("Original song downloaded to /mnt/mmc/Navidrome")
                                         : TR("Download failed; check card space and server permission"));
        }
    }
    return RET_REPEAT;
}

static int sb_destroy_event(void *ctx, void *event) {
    (void)ctx;
    (void)event;
    sb_page_close();
    return RET_OK;
}

void sb_page_open(void *win) {
    char name[24], detail[64];
    int i;
    if (sbp.win) return;
    sb_config_load();
    sbp.grid_mode = set_read(SB_VIEW_FILE, '0') == '1';
    sb_set_connected(0);
    sbp.win = win;
    if (!sbp.count && !sbp.user[0]) sbp.selected = -1;
    sbp.status = widget_lookup(win, "sb_status", 1);
    sbp.scroll = widget_lookup(win, "sb_scrollview", 1);
    sbp.rows = widget_lookup(win, "sb_rows", 1);
    sbp.connect = widget_lookup(win, "sb_connect", 1);
    sbp.connect_label = widget_lookup(win, "sb_connect_label", 1);
    sbp.connected_dot = widget_lookup(win, "sb_connected_dot", 1);
    sbp.view_button = widget_lookup(win, "sb_view", 1);
    sbp.view_icon = widget_lookup(win, "sb_view_icon", 1);
    sbp.tab_label[0] = widget_lookup(win, "sb_tracks_label", 1);
    sbp.tab_label[1] = widget_lookup(win, "sb_dsd_label", 1);
    sbp.tab_mark[0] = widget_lookup(win, "sb_tracks_mark", 1);
    sbp.tab_mark[1] = widget_lookup(win, "sb_dsd_mark", 1);
    pod_bind(win, "sb_connect", sb_connect_click, 0);
    pod_bind(win, "sb_sync", sb_sync_click, 0);
    pod_bind(win, "sb_search", sb_search_click, 0);
    pod_bind(win, "sb_tracks", sb_tracks_click, 0);
    pod_bind(win, "sb_dsd", sb_dsd_click, 0);
    pod_bind(win, "sb_view", sb_view_click, 0);
    widget_set_prop_str(sbp.view_button, "style:normal:icon", sbp.grid_mode ? "pod_nav_list" : "pod_nav_grid");
    widget_set_prop_str(sbp.view_button, "style:over:icon", sbp.grid_mode ? "pod_nav_list" : "pod_nav_grid");
    widget_set_prop_str(sbp.view_button, "style:pressed:icon", sbp.grid_mode ? "pod_nav_list_down" : "pod_nav_grid_down");
    for (i = 0; i < SB_VISIBLE; ++i) {
        snprintf(name, sizeof name, "sb_title%d", i);
        sbp.title[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_sub%d", i);
        sbp.sub[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_row%d", i);
        sbp.row[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_select_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_art%d", i);
        sbp.art[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_grid_row%d", i);
        sbp.grid_row[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_select_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_grid_title%d", i);
        sbp.grid_title[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_grid_sub%d", i);
        sbp.grid_sub[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_grid_art%d", i);
        sbp.grid_art[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_row_play%d", i);
        sbp.row_play[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_play_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_row_download%d", i);
        sbp.row_download[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_download_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_row_download_icon%d", i);
        sbp.row_download_icon[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_grid_play%d", i);
        sbp.grid_play[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_play_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_grid_download%d", i);
        sbp.grid_download[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_download_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_grid_download_icon%d", i);
        sbp.grid_download_icon[i] = widget_lookup(win, name, 1);
    }
    widget_on(sbp.scroll, EVT_SCROLL, sb_scroll_event, 0);
    (void)sb_show_library(0);
    sbp.timer = timer_add(sb_tick, 0, 100);
    widget_on(win, EVT_DESTROY, sb_destroy_event, 0);
    if (sbp.user[0]) {
        if (sb_start(8) == 0)
            sb_set_status("Checking Navidrome server…");
        else
            sb_set_status("Connect to Wi-Fi to check Navidrome.");
    } else if (sbp.view == SB_VIEW_SEARCH && sbp.count) {
        snprintf(detail, sizeof detail, "%d results. Use a row's play or download icon.", sbp.count);
        sb_set_status(detail);
    } else if (sbp.indexed_view) {
        char msg[64];
        snprintf(msg, sizeof msg, "Synced library: %d songs. Choose Songs or DSD.", sbp.index_count);
        sb_set_status(msg);
    }
}
void sb_page_close(void) {
    if (sbp.timer) timer_remove(sbp.timer);
    sbp.win = 0;
    sbp.status = 0;
    sbp.scroll = 0;
    sbp.rows = 0;
    sbp.timer = 0;
    sbp.connect = 0;
    sbp.view_button = 0;
    sbp.view_icon = 0;
    memset(sbp.row, 0, sizeof sbp.row);
    memset(sbp.art, 0, sizeof sbp.art);
    memset(sbp.grid_row, 0, sizeof sbp.grid_row);
    memset(sbp.grid_title, 0, sizeof sbp.grid_title);
    memset(sbp.grid_sub, 0, sizeof sbp.grid_sub);
    memset(sbp.grid_art, 0, sizeof sbp.grid_art);
    memset(sbp.row_play, 0, sizeof sbp.row_play);
    memset(sbp.row_download, 0, sizeof sbp.row_download);
    memset(sbp.grid_play, 0, sizeof sbp.grid_play);
    memset(sbp.grid_download, 0, sizeof sbp.grid_download);
    memset(sbp.title, 0, sizeof sbp.title);
    memset(sbp.sub, 0, sizeof sbp.sub);
}
