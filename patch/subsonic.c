/* Navidrome/Subsonic response handling. Bounded JSON reads only. */
#include <limits.h>
#include "offsets.inc"
#include "stock.h"
#include "subsonic.h"
#include "common.h"
#include "azlist.h"
#include "covercache.h"
#include "keyboard.h"
#include "curlopts.h"
#include "home.h"
#include "palette.h"
#include "songops.h"
extern int pn_free_kb(const char *path, unsigned *kb);
extern int pod_confirm(const char *text);
extern void pod_set_mode_for_queue(int mode);
extern void pod_set_in_order_for_queue(void);
extern unsigned pod_rand(unsigned n);
extern void pod_toast(const char *text);
static void sb_config_load(void);

/* Keep the Navidrome feature's own prompts in English regardless of the stock UI locale. */
#define SB_ENGLISH(text) (text)

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
    if (!out || !cap) {
        int escaped = 0;
        for (; p < end; ++p) {
            if (escaped)
                escaped = 0;
            else if (*p == '\\')
                escaped = 1;
            else if (*p == '"')
                return p + 1;
        }
        return 0;
    }
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

static void sb_trim_utf8(char *out, unsigned cap) {
    unsigned n, start, lead, need;
    unsigned c;
    if (!out || !cap) return;
    n = sb_len(out);
    if (n >= cap) n = cap - 1;
    out[n] = 0;
    if (!n) return;
    start = n;
    while (start && (((unsigned char)out[start - 1] & 0xc0u) == 0x80u)) --start;
    if (start == n)
        lead = n - 1;
    else if (start)
        lead = start - 1;
    else {
        out[0] = 0;
        return;
    }
    c = (unsigned char)out[lead];
    need = c < 0x80 ? 1 : c >= 0xf0 ? 4 : c >= 0xe0 ? 3 : c >= 0xc0 ? 2 : 1;
    if (need > n - lead) out[lead] = 0;
}

static int sb_member_mode(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num,
                          int truncate_text) {
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
                if (!q) {
                    if (!truncate_text || !out || !cap || !sb_string(p, end, (char *)0, 0)) return -1;
                    sb_trim_utf8(out, cap);
                }
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

static int sb_member(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num) {
    return sb_member_mode(obj, end, key, out, cap, num, 0);
}

static int sb_member_truncate(const char *obj, const char *end, const char *key, char *out, unsigned cap) {
    return sb_member_mode(obj, end, key, out, cap, (unsigned *)0, 1);
}

/* Locate a songs array structurally so text inside a title cannot look like a JSON key. */
static int sb_array_member(const char *obj, const char *end, const char *key, const char **array) {
    const char *p = sb_ws(obj, end);
    int found = 0;
    *array = 0;
    if (p >= end || *p != '{') return -1;
    ++p;
    for (;;) {
        char name[48];
        const char *q, *value;
        p = sb_ws(p, end);
        if (p >= end) return -1;
        if (*p == '}') return found;
        q = sb_string(p, end, name, sizeof name);
        if (!q) return -1;
        p = sb_ws(q, end);
        if (p >= end || *p++ != ':') return -1;
        value = sb_ws(p, end);
        if (sb_eq(name, sb_len(name), key)) {
            if (value >= end || *value != '[' || found) return -1;
            *array = value + 1;
            found = 1;
        }
        p = sb_skip(value, end);
        if (!p) return -1;
        p = sb_ws(p, end);
        if (p >= end) return -1;
        if (*p == ',') {
            p = sb_ws(p + 1, end);
            if (p >= end || *p == '}') return -1;
        } else if (*p != '}')
            return -1;
    }
}

static int sb_song_array(const char *obj, const char *end, const char **container, const char **array) {
    static const char *keys[] = {"searchResult3", "album", "randomSongs", "songsByGenre"};
    const char *value;
    int found;
    unsigned i;
    *container = 0;
    *array = 0;
    found = sb_array_member(obj, end, "song", array);
    if (found != 0) {
        *container = obj;
        return found;
    }
    for (i = 0; i < sizeof keys / sizeof keys[0]; ++i) {
        value = sb_object(obj, end, keys[i]);
        if (!value) continue;
        if (!sb_skip(value, end)) return -1;
        *container = value;
        return sb_array_member(value, end, "song", array);
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
    unsigned char raw[8], digest[16], input[SB_TEXT + 16];
    unsigned i, n = sb_len(password);
    int fd;
    if (!token || tcap < 33 || !salt || scap < 17 || n >= SB_TEXT || n > sizeof input - 16) return -1;
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
static int sb_sync_query_variant(char *out, unsigned cap, unsigned offset, unsigned variant) {
    int n;
    if (!out || !cap) return -1;
    if (variant == 1)
        n = snprintf(out, cap, "&songCount=%u&albumCount=0&artistCount=0&songOffset=%u", SB_SYNC_PAGE, offset);
    else if (variant == 2)
        n = snprintf(out, cap, "&query=%%2A&songCount=%u&albumCount=0&artistCount=0&songOffset=%u", SB_SYNC_PAGE,
                     offset);
    else
        n = snprintf(out, cap, "&query=&songCount=%u&albumCount=0&artistCount=0&songOffset=%u", SB_SYNC_PAGE, offset);
    return n < 0 || (unsigned)n >= cap ? -1 : n;
}

int sb_sync_query(char *out, unsigned cap, unsigned offset) { return sb_sync_query_variant(out, cap, offset, 0); }

int sb_track_filename(char *out, unsigned cap, const sb_song_t *song) {
    const char *title;
    unsigned i, n = 0;
    if (!out || !cap || !song) return -1;
    title = song->title[0] ? song->title : SB_ENGLISH("Untitled");
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

static int sb_field(const char *obj, const char *end, const char *name, char *out, unsigned cap) {
    return sb_member_truncate(obj, end, name, out, cap);
}

static int sb_date_digits(const char *s, unsigned at, unsigned count, unsigned *value) {
    unsigned i, n = 0;
    for (i = 0; i < count; ++i) {
        unsigned c = (unsigned char)s[at + i];
        if (c < '0' || c > '9') return 0;
        n = n * 10 + c - '0';
    }
    *value = n;
    return 1;
}

/* Subsonic's created timestamp is RFC3339. Store UTC seconds for the
 * Recently Added / Oldest First library order; malformed dates sort last. */
static unsigned sb_created_time(const char *s) {
    unsigned year, month, day, hour, minute, second, off_h = 0, off_m = 0, i;
    int sign = 0, y, era;
    unsigned yoe, doy, doe;
    long long days, seconds;
    if (!s || sb_len(s) < 19 || s[4] != '-' || s[7] != '-' || (s[10] != 'T' && s[10] != 't') || s[13] != ':' ||
        s[16] != ':' || !sb_date_digits(s, 0, 4, &year) || !sb_date_digits(s, 5, 2, &month) ||
        !sb_date_digits(s, 8, 2, &day) || !sb_date_digits(s, 11, 2, &hour) || !sb_date_digits(s, 14, 2, &minute) ||
        !sb_date_digits(s, 17, 2, &second) || !year || month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 ||
        minute > 59 || second > 60)
        return 0;
    for (i = 19; s[i] && s[i] != 'Z' && s[i] != 'z' && s[i] != '+' && s[i] != '-'; ++i) {
    }
    if (s[i] == '+' || s[i] == '-') {
        sign = s[i] == '+' ? 1 : -1;
        if (!sb_date_digits(s, i + 1, 2, &off_h) || !s[i + 3] || s[i + 3] != ':' ||
            !sb_date_digits(s, i + 4, 2, &off_m) || off_h > 23 || off_m > 59)
            return 0;
    }
    y = (int)year - (month <= 2);
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = (unsigned)(y - era * 400);
    doy = (153u * (month > 2 ? month - 3u : month + 9u) + 2u) / 5u + day - 1u;
    doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
    days = (long long)era * 146097 + doe - 719468;
    seconds = days * 86400 + hour * 3600 + minute * 60 + second - sign * (int)(off_h * 3600 + off_m * 60);
    return seconds > 0 && seconds <= UINT_MAX ? (unsigned)seconds : 0;
}

static int sb_response(const char *json, unsigned n) {
    char status[16];
    const char *end, *root, *after, *p;
    if (!json || !n) return 0;
    end = json + n;
    root = sb_ws(json, end);
    if (root >= end || *root != '{') return 0;
    after = sb_skip(root, end);
    if (!after || sb_ws(after, end) != end) return 0;
    p = sb_object(root, end, "subsonic-response");
    if (!p || !sb_skip(p, end)) return 0;
    if (sb_member(p, end, "status", status, sizeof status, (unsigned *)0) <= 0) return 0;
    return sb_eq(status, sb_len(status), "ok");
}

int sb_songs(const char *json, unsigned n, sb_song_t *out, int max) {
    const char *end, *p, *arr, *close, *response, *container;
    unsigned depth = 0;
    int count = 0, closed = 0, array_state;
    if (!json || !out || max <= 0 || n > 1024 * 1024 || !sb_response(json, n)) return -1;
    end = json + n;
    response = sb_object(sb_ws(json, end), end, "subsonic-response");
    if (!response || !sb_skip(response, end)) return -1;
    array_state = sb_song_array(response, end, &container, &arr);
    if (!container || array_state < 0) return -1;
    if (!array_state) return 0;
    close = sb_skip(arr - 1, end);
    if (!close) return -1;
    --close;
    p = arr;
    while (p <= close && count < max) {
        const char *q, *arrend;
        p = sb_ws(p, close + 1);
        if (p == close && *p == ']') {
            closed = 1;
            break;
        }
        if (p >= close) return -1;
        if (*p != '{' || depth++ > (unsigned)max) return -1;
        q = sb_skip(p, close + 1);
        if (!q || q > close) return -1;
        arrend = q;
        {
            sb_song_t *s = out + count;
            char created[40];
            unsigned v = 0;
            unsigned i;
            for (i = 0; i < sizeof(*s); ++i) ((unsigned char *)s)[i] = 0;
            created[0] = 0;
            if (sb_member(p, arrend, "id", s->id, sizeof s->id, (unsigned *)0) < 0 ||
                sb_field(p, arrend, "title", s->title, sizeof s->title) < 0 ||
                sb_field(p, arrend, "artist", s->artist, sizeof s->artist) < 0 ||
                sb_field(p, arrend, "album", s->album, sizeof s->album) < 0 ||
                sb_field(p, arrend, "displayAlbumArtist", s->album_artist, sizeof s->album_artist) < 0 ||
                sb_field(p, arrend, "displayComposer", s->composer, sizeof s->composer) < 0 ||
                sb_field(p, arrend, "genre", s->genre, sizeof s->genre) < 0 ||
                sb_field(p, arrend, "created", created, sizeof created) < 0 ||
                sb_field(p, arrend, "coverArt", s->cover, sizeof s->cover) < 0 ||
                sb_field(p, arrend, "suffix", s->suffix, sizeof s->suffix) < 0)
                return -1;
            s->created = sb_created_time(created);
            if (!s->artist[0] && sb_field(p, arrend, "displayArtist", s->artist, sizeof s->artist) < 0) return -1;
            if (!s->composer[0] && sb_field(p, arrend, "composer", s->composer, sizeof s->composer) < 0) return -1;
            if (!s->album_artist[0]) {
                if (sb_field(p, arrend, "albumArtist", s->album_artist, sizeof s->album_artist) < 0) return -1;
            }
            if (!s->album_artist[0]) {
                unsigned j;
                for (j = 0; j + 1 < sizeof s->album_artist && s->artist[j]; ++j) s->album_artist[j] = s->artist[j];
                s->album_artist[j] = 0;
            }
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
            if (!s->id[0]) return -1;
            ++count;
        }
        p = sb_ws(q, close + 1);
        if (p == close && *p == ']') {
            closed = 1;
            break;
        }
        if (p >= close || *p != ',') return -1;
        p = sb_ws(p + 1, close + 1);
        if (p >= close || *p == ']') return -1;
    }
    if (!closed) {
        p = sb_ws(p, close + 1);
        if (p == close && *p == ']') closed = 1;
    }
    return closed ? count : -1;
}

/* Navidrome integration uses the stock MPlayer queue path. The player receives
 * the original Subsonic stream URL (format=raw); the payload never decodes or
 * re-encodes audio. Downloads use a .part file then rename onto the SD card.
 * The queue ABI was cross-checked against shivaluma/shanling-m1plus-navidrome
 * (MIT, Copyright 2026 shivaluma and contributors); this implementation is
 * native to this payload and does not copy its plugin or backend. */
#define SB_RESPONSE_MAX (512 * 1024)
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
#define SB_INDEX_MAGIC "SBIDX3\0\0"
#define SB_SYNC_LIMIT 100000
#define SB_SYNC_RESERVE_KB 2048u
#define SB_ROW_H 52
#define SB_GRID_PITCH 210
#define SB_LIST_TOP 174
#define SB_VIEWPORT_H 276
#define SB_GRID_COVER 136
#define SB_DL_BAR_W 296
#define SB_DL_BAR_H 6
#define SB_CA "/etc/m1plus-cacert.pem"
#define SB_VISIBLE 6
enum { SB_VIEW_TRACKS, SB_VIEW_SEARCH, SB_VIEW_DSD };
enum {
    SB_SYNC_ERR_NONE,
    SB_SYNC_ERR_CARD,
    SB_SYNC_ERR_SPACE,
    SB_SYNC_ERR_STORAGE,
    SB_SYNC_ERR_NETWORK,
    SB_SYNC_ERR_REQUEST,
    SB_SYNC_ERR_AUTH,
    SB_SYNC_ERR_SERVER,
    SB_SYNC_ERR_RESPONSE,
    SB_SYNC_ERR_EMPTY,
    SB_SYNC_ERR_MEMORY
};
enum { SB_SETUP_USER = 1, SB_SETUP_PASSWORD = 2 };
enum {
    SB_DL_ERR_NONE,
    SB_DL_ERR_CARD,
    SB_DL_ERR_SPACE,
    SB_DL_ERR_STORAGE,
    SB_DL_ERR_FILE_LIMIT,
    SB_DL_ERR_PATH,
    SB_DL_ERR_EXISTS,
    SB_DL_ERR_REQUEST,
    SB_DL_ERR_SERVER,
    SB_DL_ERR_RESPONSE,
    SB_DL_ERR_NETWORK,
    SB_DL_ERR_MEMORY
};
typedef struct {
    char data[SB_RESPONSE_MAX];
    char content_type[64];
    unsigned char prefix[8];
    unsigned prefix_used;
    unsigned used;
    int fd;
    int curl_result;
    long http_status;
    long long content_length;
    long long range_start, range_end, range_total;
    int range_seen;
    long long written, last_check, limit;
} sb_sink_t;
static struct {
    void *win, *status, *scroll, *rows, *connect, *connect_label, *connected_dot, *view_button, *view_icon;
    void *download_bar, *download_fill;
    void *row[SB_VISIBLE], *title[SB_VISIBLE], *sub[SB_VISIBLE], *art[SB_VISIBLE];
    void *grid_row[SB_VISIBLE], *grid_title[SB_VISIBLE], *grid_sub[SB_VISIBLE], *grid_art[SB_VISIBLE];
    void *row_download[SB_VISIBLE], *row_download_icon[SB_VISIBLE];
    void *grid_download[SB_VISIBLE], *grid_download_icon[SB_VISIBLE];
    void *tab_label[2], *tab_mark[2];
    az_t az;
    unsigned char *az_rank;
    unsigned timer;
    unsigned stream_timer;
    volatile int busy, done, result, mode, sync_count, connection_lost, sync_limit_hit, sync_error;
    volatile int http_status;
    volatile int library_refreshing, library_refresh_result;
    int sync_shown, setup_prompt, setup_tries;
    int count, selected, index_count, dsd_count, index_offset, indexed_view, loading, view;
    int row_data, row_base;
    int grid_mode, dsd_view, connected, index_valid, art_shown, switching_view, ping_after_work;
    int refresh_index_after_download, library_refresh_shown, download_is_dsd;
    volatile int download_active, download_percent, download_percent_known, download_kb;
    volatile int download_resumable, download_error;
    long long download_offset;
    int download_status_kind, download_status_value, download_anim_x, download_anim_dir, download_anim_ticks;
    volatile int art_syncing, art_count, art_total, art_cached, art_failed, art_pause_request;
    int pending_download_at, download_song_valid, stream_queue_active, art_pause_for_playback, curl_ready;
    unsigned stream_grace_until;
    sb_song_t download_song;
    sb_song_t songs[SB_MAX];
    int play_ids[SB_QUEUE_MAX], play_count;
    char play_cover[SB_QUEUE_MAX][SB_ID], cover_file[256];
    char setup_base[256], setup_user[128];
    char base[256], user[128], password[128], query[256];
} sbp __attribute__((section(".scratch")));

static void sb_az_rebuild(void);
static int sb_on_az_rail(void *ctx, void *event);
static int sb_on_az_paint(void *ctx, void *event);
static int sb_scroll_event(void *ctx, void *e);

static int sb_atomic_load(volatile int *value) { return __sync_fetch_and_add(value, 0); }
static void sb_atomic_store(volatile int *value, int next) { (void)__sync_lock_test_and_set(value, next); }

static void sb_download_set_error(int error) { sb_atomic_store(&sbp.download_error, error); }

typedef struct {
    char magic[8];
    unsigned count, dsd_count;
    char server[256], user[128];
} sb_index_head_t;

static unsigned sb_write(void *ptr, unsigned size, unsigned nmemb, void *ctx) {
    sb_sink_t *s = (sb_sink_t *)ctx;
    unsigned n = size * nmemb;
    if (!s || (size && n / size != nmemb)) {
        if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_RESPONSE);
        return 0;
    }
    if (s->fd >= 0) {
        unsigned done = 0;
        if (s->prefix_used < sizeof s->prefix) {
            unsigned take = (unsigned)sizeof s->prefix - s->prefix_used;
            if (take > n) take = n;
            memcpy(s->prefix + s->prefix_used, ptr, take);
            s->prefix_used += take;
        }
        if (s->limit > 0 && (s->written >= s->limit || (long long)n > s->limit - s->written)) {
            if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_FILE_LIMIT);
            return 0;
        }
        if ((long long)n > LLONG_MAX - s->written) {
            if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_FILE_LIMIT);
            return 0;
        }
        if (s->written - s->last_check >= 1024 * 1024) {
            unsigned free_kb = 0;
            if (!pn_free_kb("/mnt/mmc", &free_kb)) {
                if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_CARD);
                return 0;
            }
            if (free_kb <= 32768) {
                if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_SPACE);
                return 0;
            }
            s->last_check = s->written;
        }
        while (done < n) {
            int wrote = write(s->fd, (const char *)ptr + done, n - done);
            if (wrote <= 0) {
                if (sbp.mode == 2) sb_download_set_error(SB_DL_ERR_STORAGE);
                return 0;
            }
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

static unsigned sb_header(void *ptr, unsigned size, unsigned nmemb, void *ctx) {
    sb_sink_t *sink = (sb_sink_t *)ctx;
    const char *line = (const char *)ptr;
    static const char key[] = "content-range:";
    unsigned n = size * nmemb, i;
    if (!sink || (size && n / size != nmemb)) return 0;
    if (n >= 5 && line[0] == 'H' && line[1] == 'T' && line[2] == 'T' && line[3] == 'P' && line[4] == '/') {
        sink->range_seen = 0;
        sink->range_start = sink->range_end = sink->range_total = -1;
        return n;
    }
    if (n < sizeof key - 1) return n;
    for (i = 0; i < sizeof key - 1; ++i)
        if (sb_ascii_lower((unsigned char)line[i]) != key[i]) return n;
    sink->range_seen = 1;
    sink->range_start = sink->range_end = sink->range_total = -1;
    i = sizeof key - 1;
    while (i < n && (line[i] == ' ' || line[i] == '\t')) ++i;
    if (i + 6 > n || sb_ascii_lower((unsigned char)line[i++]) != 'b' ||
        sb_ascii_lower((unsigned char)line[i++]) != 'y' || sb_ascii_lower((unsigned char)line[i++]) != 't' ||
        sb_ascii_lower((unsigned char)line[i++]) != 'e' || sb_ascii_lower((unsigned char)line[i++]) != 's' ||
        line[i++] != ' ')
        return n;
    if (i < n && line[i] == '*') return n;
    {
        long long start = 0, end = 0;
        unsigned digits = 0;
        while (i < n && line[i] >= '0' && line[i] <= '9') {
            unsigned digit = (unsigned)(line[i++] - '0');
            if (start > 922337203685477580LL || (start == 922337203685477580LL && digit > 7)) return n;
            start = start * 10 + digit;
            ++digits;
        }
        if (!digits || i >= n || line[i++] != '-') return n;
        digits = 0;
        while (i < n && line[i] >= '0' && line[i] <= '9') {
            unsigned digit = (unsigned)(line[i++] - '0');
            if (end > 922337203685477580LL || (end == 922337203685477580LL && digit > 7)) return n;
            end = end * 10 + digit;
            ++digits;
        }
        if (!digits || i >= n || line[i++] != '/' || end < start) return n;
        sink->range_start = start;
        sink->range_end = end;
        if (i < n && line[i] != '*') {
            long long total = 0;
            digits = 0;
            while (i < n && line[i] >= '0' && line[i] <= '9') {
                unsigned digit = (unsigned)(line[i++] - '0');
                if (total > 922337203685477580LL || (total == 922337203685477580LL && digit > 7)) {
                    sink->range_total = -2;
                    return n;
                }
                total = total * 10 + digit;
                ++digits;
            }
            if (digits)
                sink->range_total = total > end ? total : -2;
            else
                sink->range_total = -2;
        }
    }
    return n;
}

/* libcurl's worker callback: real percent when the server gives a length, bytes otherwise. */
static int sb_download_xfer(void *ctx, long long total, long long now, long long upload_total, long long uploaded) {
    sb_sink_t *sink = (sb_sink_t *)ctx;
    unsigned scaled_total, scaled_now;
    (void)upload_total;
    (void)uploaded;
    if (sbp.mode == 4 && sb_atomic_load(&sbp.art_pause_request)) return 1;
    if (!sb_atomic_load(&sbp.download_active) || sbp.mode != 2) return 0;
    if (now >= 0) {
        long long bytes = now;
        if (sbp.download_offset > 0 && bytes <= LLONG_MAX - sbp.download_offset) bytes += sbp.download_offset;
        long long kb = bytes >> 10;
        sb_atomic_store(&sbp.download_kb, kb > INT_MAX ? INT_MAX : (int)kb);
    }
    if (sbp.download_offset > 0) {
        if (!sink || !sink->range_seen || sink->range_start != sbp.download_offset || sink->range_total <= 0 ||
            now < 0) {
            sb_atomic_store(&sbp.download_percent_known, 0);
            return 0;
        }
        total = sink->range_total;
        if (now > total - sink->range_start) now = total - sink->range_start;
        now += sink->range_start;
    }
    if (total <= 0 || now < 0) {
        sb_atomic_store(&sbp.download_percent_known, 0);
        return 0;
    }
    while (total > 0xffffff) total >>= 8, now >>= 8;
    scaled_total = (unsigned)total;
    scaled_now = now > total ? scaled_total : (unsigned)now;
    if (!scaled_total) {
        sb_atomic_store(&sbp.download_percent_known, 0);
        return 0;
    }
    {
        int percent = (int)(100u * scaled_now / scaled_total);
        if (percent > 99) percent = 99;
        sb_atomic_store(&sbp.download_percent, percent);
        sb_atomic_store(&sbp.download_percent_known, 1);
    }
    return 0;
}

static int sb_curl_init(void) {
    if (sbp.curl_ready) return 1;
    if (curl_global_init(CURL_GLOBAL_ALL) != CURLE_OK) return 0;
    sbp.curl_ready = 1;
    return 1;
}

#define SB_CURL_SETOPT(option, value) \
    do { \
        if (curl_easy_setopt(h, option, value) != CURLE_OK) { \
            rc = CURLE_FAILED_INIT; \
            goto cleanup; \
        } \
    } while (0)

static int sb_http_timeout_range(const char *url, sb_sink_t *sink, long timeout, const char *range) {
    void *h = curl_easy_init();
    int rc = CURLE_FAILED_INIT;
    long status = 0;
    char *content_type = (char *)0;
    long long content_length = -1;
    if (!h) {
        if (sink) sink->curl_result = -1, sink->http_status = 0;
        return -1;
    }
    SB_CURL_SETOPT(CURLOPT_URL, url);
    SB_CURL_SETOPT(CURLOPT_WRITEFUNCTION, sb_write);
    SB_CURL_SETOPT(CURLOPT_WRITEDATA, sink);
    SB_CURL_SETOPT(CURLOPT_HEADERFUNCTION, sb_header);
    SB_CURL_SETOPT(CURLOPT_HEADERDATA, sink);
    SB_CURL_SETOPT(CURLOPT_FAILONERROR, 1L);
    SB_CURL_SETOPT(CURLOPT_CONNECTTIMEOUT, 12L);
    SB_CURL_SETOPT(CURLOPT_TIMEOUT, timeout);
    SB_CURL_SETOPT(CURLOPT_LOW_SPEED_LIMIT, 512L);
    SB_CURL_SETOPT(CURLOPT_LOW_SPEED_TIME, timeout > 0 && timeout < 45L ? timeout / 2L : 45L);
    SB_CURL_SETOPT(CURLOPT_NOPROGRESS, 0L);
    SB_CURL_SETOPT(CURLOPT_XFERINFOFUNCTION, sb_download_xfer);
    SB_CURL_SETOPT(CURLOPT_XFERINFODATA, sink);
    SB_CURL_SETOPT(CURLOPT_NOSIGNAL, 1L);
    SB_CURL_SETOPT(CURLOPT_FOLLOWLOCATION, 1L);
    SB_CURL_SETOPT(CURLOPT_MAXREDIRS, 5L);
    SB_CURL_SETOPT(CURLOPT_REDIR_PROTOCOLS, sb_https(url) ? CURLPROTO_HTTPS : CURLPROTO_HTTP_HTTPS);
    SB_CURL_SETOPT(CURLOPT_PROTOCOLS, CURLPROTO_HTTP_HTTPS);
    SB_CURL_SETOPT(CURLOPT_CAINFO, SB_CA);
    SB_CURL_SETOPT(CURLOPT_SSL_VERIFYPEER, 1L);
    SB_CURL_SETOPT(CURLOPT_SSL_VERIFYHOST, 2L);
    if (range && *range) SB_CURL_SETOPT(CURLOPT_RANGE, range);
    rc = curl_easy_perform(h);
cleanup:
    if (curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &status) != CURLE_OK) status = 0;
    if (curl_easy_getinfo(h, CURLINFO_CONTENT_TYPE, &content_type) != CURLE_OK) content_type = (char *)0;
    if (curl_easy_getinfo(h, CURLINFO_CONTENT_LENGTH_DOWNLOAD_T, &content_length) != CURLE_OK) content_length = -1;
    if (sink) {
        unsigned i;
        sink->curl_result = rc;
        sink->http_status = status;
        sink->content_length = content_length;
        sink->content_type[0] = 0;
        if (content_type)
            for (i = 0; i + 1 < sizeof sink->content_type && content_type[i]; ++i)
                sink->content_type[i] = content_type[i];
        if (content_type) sink->content_type[i] = 0;
    }
    curl_easy_cleanup(h);
    sb_atomic_store(&sbp.http_status, (int)status);
    if ((rc != 0 && rc != CURLE_HTTP_RETURNED_ERROR && rc != CURLE_WRITE_ERROR &&
         !(rc == CURLE_ABORTED_BY_CALLBACK && sbp.mode == 4 && sb_atomic_load(&sbp.art_pause_request))) ||
        status >= 500 || status == 401 || status == 403)
        sbp.connection_lost = 1;
    return rc == 0 ? 0 : -1;
}

#undef SB_CURL_SETOPT

static int sb_http_timeout(const char *url, sb_sink_t *sink, long timeout) {
    return sb_http_timeout_range(url, sink, timeout, (const char *)0);
}

static int sb_http(const char *url, sb_sink_t *sink) { return sb_http_timeout(url, sink, 180L); }

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

static int sb_terminated(const char *field, unsigned cap) {
    unsigned i;
    for (i = 0; i < cap; ++i)
        if (!field[i]) return 1;
    return 0;
}

static int sb_song_record_valid(const sb_song_t *song) {
    return song && song->id[0] && sb_terminated(song->id, sizeof song->id) &&
           sb_terminated(song->title, sizeof song->title) && sb_terminated(song->artist, sizeof song->artist) &&
           sb_terminated(song->album, sizeof song->album) &&
           sb_terminated(song->album_artist, sizeof song->album_artist) &&
           sb_terminated(song->composer, sizeof song->composer) && sb_terminated(song->genre, sizeof song->genre) &&
           sb_terminated(song->cover, sizeof song->cover) && sb_terminated(song->suffix, sizeof song->suffix);
}

static int sb_index_counts_valid(sb_index_head_t head) {
    return head.count <= SB_SYNC_LIMIT && head.dsd_count <= SB_SYNC_LIMIT &&
           !(head.count + head.dsd_count > SB_SYNC_LIMIT);
}

static int sb_index_head_valid(sb_index_head_t head) {
    return sb_bytes_equal(head.magic, SB_INDEX_MAGIC, sizeof head.magic) && sb_index_counts_valid(head) &&
           sb_fixed_equal(head.server, sizeof head.server, sbp.base) &&
           sb_fixed_equal(head.user, sizeof head.user, sbp.user);
}

static int sb_index_file_size(int fd, sb_index_head_t head, long *size_out) {
    unsigned total;
    long long expected;
    long actual, position;
    if (!sb_index_counts_valid(head)) return 0;
    position = lseek(fd, 0, 1);
    if (position < 0) return 0;
    total = head.count + head.dsd_count;
    expected = (long long)sizeof(head) + (long long)total * sizeof(sb_song_t);
    if (expected > LONG_MAX) {
        (void)lseek(fd, position, 0);
        return 0;
    }
    actual = lseek(fd, 0, 2);
    if (lseek(fd, position, 0) < 0 || actual < 0 || actual != (long)expected) return 0;
    if (size_out) *size_out = actual;
    return 1;
}

static void sb_song_copy(sb_song_t *dst, const sb_song_t *src) {
    unsigned i;
    for (i = 0; i < sizeof *dst; ++i) ((unsigned char *)dst)[i] = ((const unsigned char *)src)[i];
}

static int sb_sync_fetch_page(sb_sink_t *sink, unsigned offset) {
    char url[SB_URL], extra[128];
    unsigned variant;
    int n, saw_body = 0;
    /* Servers differ on the empty search query; the final form is Navidrome's
     * documented trailing-wildcard equivalent for older server versions. */
    for (variant = 0; variant < 3; ++variant) {
        int k;
        memset(sink, 0, sizeof *sink);
        sink->fd = -1;
        k = variant ? sb_sync_query_variant(extra, sizeof extra, offset, variant)
                    : sb_sync_query(extra, sizeof extra, offset);
        if (k < 0 || sb_url(url, sizeof url, sbp.base, "search3", 0, sbp.user, sbp.password, extra)) {
            sbp.sync_error = SB_SYNC_ERR_REQUEST;
            return -1;
        }
        if (sb_http(url, sink)) {
            int status = sb_atomic_load(&sbp.http_status);
            sbp.sync_error = status == 401 || status == 403           ? SB_SYNC_ERR_AUTH
                             : status >= 400                          ? SB_SYNC_ERR_SERVER
                             : sink->curl_result == CURLE_WRITE_ERROR ? SB_SYNC_ERR_RESPONSE
                                                                      : SB_SYNC_ERR_NETWORK;
            return -1;
        }
        if (sink->used) saw_body = 1;
        n = sb_songs(sink->data, sink->used, sbp.songs, SB_MAX);
        if (n >= 0) return n;
    }
    sbp.sync_error = saw_body ? SB_SYNC_ERR_RESPONSE : SB_SYNC_ERR_EMPTY;
    return -1;
}

static int sb_sync_library(sb_sink_t *sink) {
    sb_index_head_t head;
    sb_song_t *dsd = 0;
    unsigned offset = 0, regular = 0, dsd_count = 0, free_kb = 0, i;
    unsigned page_kb = 0;
    int fd = -1, dfd = -1, rc = -1, n;
    sbp.sync_error = SB_SYNC_ERR_NONE;
    if (!pod_card_mounted()) {
        sbp.sync_error = SB_SYNC_ERR_CARD;
        return -1;
    }
    if (!pn_free_kb("/mnt/mmc", &free_kb)) {
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        return -1;
    }
    if (free_kb < SB_SYNC_RESERVE_KB) {
        sbp.sync_error = SB_SYNC_ERR_SPACE;
        return -1;
    }
    dsd = (sb_song_t *)calloc(SB_MAX, sizeof *dsd);
    if (!dsd) {
        sbp.sync_error = SB_SYNC_ERR_MEMORY;
        return -1;
    }
    mkdir(CARD_DIR, 0755);
    fd = open(SB_INDEX_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    dfd = open(SB_DSD_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0 || dfd < 0) {
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        goto done;
    }
    memset(&head, 0, sizeof head);
    memcpy(head.magic, SB_INDEX_MAGIC, sizeof head.magic);
    memcpy(head.server, sbp.base, sizeof head.server);
    memcpy(head.user, sbp.user, sizeof head.user);
    if (!sb_write_all(fd, &head, sizeof head)) {
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        goto done;
    }
    for (;;) {
        if (!pod_card_mounted()) {
            sbp.sync_error = SB_SYNC_ERR_CARD;
            goto done;
        }
        if (!pn_free_kb("/mnt/mmc", &free_kb)) {
            sbp.sync_error = SB_SYNC_ERR_STORAGE;
            goto done;
        }
        if (free_kb < SB_SYNC_RESERVE_KB) {
            sbp.sync_error = SB_SYNC_ERR_SPACE;
            goto done;
        }
        n = sb_sync_fetch_page(sink, offset);
        if (n < 0) goto done;
        if (!n) {
            rc = 0;
            break;
        }
        if (offset + (unsigned)n > SB_SYNC_LIMIT) {
            sbp.sync_limit_hit = 1;
            goto done;
        }
        page_kb = ((unsigned)n * (unsigned)sizeof(sb_song_t) + 1023u) >> 10;
        if (!pn_free_kb("/mnt/mmc", &free_kb)) {
            sbp.sync_error = SB_SYNC_ERR_STORAGE;
            goto done;
        }
        if (free_kb < SB_SYNC_RESERVE_KB + page_kb) {
            sbp.sync_error = SB_SYNC_ERR_SPACE;
            goto done;
        }
        {
            unsigned ndsd = 0, nregular = 0;
            for (i = 0; i < (unsigned)n; ++i) {
                if (sb_is_dsd(sbp.songs[i].suffix))
                    sb_song_copy(&dsd[ndsd++], &sbp.songs[i]);
                else
                    sb_song_copy(&sbp.songs[nregular++], &sbp.songs[i]);
            }
            if (!sb_write_song_records(fd, sbp.songs, nregular) || !sb_write_song_records(dfd, dsd, ndsd)) {
                sbp.sync_error = SB_SYNC_ERR_STORAGE;
                goto done;
            }
            regular += nregular;
            dsd_count += ndsd;
        }
        offset += (unsigned)n;
        sbp.sync_count = (int)offset;
        if ((unsigned)n < SB_SYNC_PAGE) {
            rc = 0;
            break;
        }
    }
    head.count = regular;
    head.dsd_count = dsd_count;
    if (!pod_card_mounted()) {
        sbp.sync_error = SB_SYNC_ERR_CARD;
        goto done;
    }
    {
        unsigned copy_kb = (dsd_count * (unsigned)sizeof(sb_song_t) + 1023u) >> 10;
        if (!pn_free_kb("/mnt/mmc", &free_kb)) {
            sbp.sync_error = SB_SYNC_ERR_STORAGE;
            goto done;
        }
        if (free_kb < SB_SYNC_RESERVE_KB + copy_kb) {
            sbp.sync_error = SB_SYNC_ERR_SPACE;
            goto done;
        }
    }
    if (lseek(fd, 0, 0) < 0 || !sb_write_all(fd, &head, sizeof head) || fsync(dfd) || lseek(dfd, 0, 0) < 0 ||
        lseek(fd, 0, 2) < 0) {
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        goto done;
    }
    {
        char copy[4096];
        int got;
        close(dfd);
        dfd = open(SB_DSD_TMP, O_RDONLY, 0);
        if (dfd < 0) {
            sbp.sync_error = SB_SYNC_ERR_STORAGE;
            goto done;
        }
        while ((got = read(dfd, copy, sizeof copy)) > 0)
            if (!sb_write_all(fd, copy, (unsigned)got)) {
                sbp.sync_error = SB_SYNC_ERR_STORAGE;
                goto done;
            }
        if (got < 0 || fsync(fd)) {
            sbp.sync_error = SB_SYNC_ERR_STORAGE;
            goto done;
        }
    }
    close(dfd);
    dfd = -1;
    if (close(fd)) {
        fd = -1;
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        goto done;
    }
    fd = -1;
    if (!pod_card_mounted()) {
        sbp.sync_error = SB_SYNC_ERR_CARD;
        goto done;
    }
    if (rename(SB_INDEX_TMP, SB_INDEX_FILE)) {
        sbp.sync_error = SB_SYNC_ERR_STORAGE;
        goto done;
    }
    rc = 1; /* rename commits the new index; removable filesystems may reject directory fsync */
    unlink(SB_DSD_TMP);
    {
        int dir = open(CARD_DIR, O_RDONLY, 0);
        if (dir >= 0) {
            (void)fsync(dir);
            close(dir);
        }
    }
done:
    if (fd >= 0) close(fd);
    if (dfd >= 0) close(dfd);
    if (rc != 1) unlink(SB_INDEX_TMP);
    if (rc != 1) unlink(SB_DSD_TMP);
    free(dsd);
    return rc == 1 ? (int)offset : -1;
}

static unsigned sb_art_hash(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h;
}

static int sb_art_path_ext(char *out, unsigned cap, const char *id, const char *ext) {
    unsigned h = sb_art_hash(sbp.base);
    char name[20];
    h = (h ^ sb_art_hash(sbp.user)) * 16777619u;
    h = (h ^ sb_art_hash(id)) * 16777619u;
    snprintf(name, sizeof name, "%08x.%s", h, ext);
    return snprintf(out, cap, SB_ART_DIR "/%s", name) < (int)cap ? 0 : -1;
}

static int sb_art_path(char *out, unsigned cap, const char *id) {
    char jpg[256];
    char png[256];
    if (sb_art_path_ext(jpg, sizeof jpg, id, "jpg")) return -1;
    if (access(jpg, 0) == 0) return sb_art_path_ext(out, cap, id, "jpg");
    if (sb_art_path_ext(png, sizeof png, id, "png")) return -1;
    if (access(png, 0) == 0) return sb_art_path_ext(out, cap, id, "png");
    return sb_art_path_ext(out, cap, id, "jpg");
}

static int sb_offline_path(const sb_song_t *song, char *out, unsigned cap) {
    char name[112], ext[12];
    unsigned i, n = 0;
    if (!song || !out || !cap) return -1;
    {
        unsigned h = sb_art_hash(song->id);
        int k = snprintf(name, sizeof name, "%08x-", h);
        if (k < 0 || (unsigned)k >= sizeof name) return -1;
        n = (unsigned)k;
    }
    for (i = 0; song->title[i] && n < 100; ++i) {
        unsigned c = (unsigned char)song->title[i];
        name[n++] = (c < 32 || c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' ||
                     c == '>' || c == '|')
                        ? '_'
                        : (char)c;
    }
    if (!n) {
        memcpy(name, "track", 5);
        n = 5;
    }
    name[n] = 0;
    n = 0;
    for (i = 0; song->suffix[i] && n + 1 < sizeof ext; ++i) {
        unsigned c = (unsigned char)song->suffix[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) ext[n++] = (char)c;
    }
    if (!n) {
        memcpy(ext, "audio", 5);
        n = 5;
    }
    ext[n] = 0;
    {
        int k = snprintf(out, cap, "%s/%s.%s", SB_OFFLINE_DIR, name, ext);
        return k >= 0 && (unsigned)k < cap ? 0 : -1;
    }
}

static int sb_offline_find(const sb_song_t *song, char *out, unsigned cap) {
    if (sb_offline_path(song, out, cap) == 0 && access(out, 0) == 0) return 1;
    return 0;
}

int sb_library_index_open(sb_library_index_t *index) {
    sb_index_head_t head;
    long size;
    int fd, n;
    void *map;
    if (!index) return -1;
    memset(index, 0, sizeof *index);
    sb_config_load();
    if (!sbp.base[0] || !sbp.user[0] || !sbp.password[0] || !pod_card_mounted()) return -1;
    fd = open(SB_INDEX_FILE, O_RDONLY, 0);
    if (fd < 0) return -1;
    n = read(fd, &head, sizeof head);
    if (n != sizeof head || !sb_index_head_valid(head) || !sb_index_file_size(fd, head, &size) || size <= 0) {
        close(fd);
        return -1;
    }
    map = mmap((void *)0, (size_t)size, PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    if (map == MAP_FAILED) return -1;
    index->mapping = map;
    index->mapping_size = (size_t)size;
    index->songs = (const sb_song_t *)((const char *)map + sizeof head);
    index->count = head.count;
    index->dsd_count = head.dsd_count;
    return 0;
}

static void sb_hash_sift(unsigned *values, unsigned root, unsigned end) {
    unsigned child, value;
    while ((child = root * 2u + 1u) < end) {
        if (child + 1u < end && values[child] < values[child + 1u]) ++child;
        if (values[root] >= values[child]) return;
        value = values[root], values[root] = values[child], values[child] = value;
        root = child;
    }
}

static void sb_hash_sort(unsigned *values, unsigned count) {
    unsigned i, value;
    for (i = count / 2u; i > 0; --i) sb_hash_sift(values, i - 1u, count);
    for (i = count; i > 1u; --i) {
        value = values[0], values[0] = values[i - 1u], values[i - 1u] = value;
        sb_hash_sift(values, 0, i - 1u);
    }
}

int sb_library_downloads_open(sb_library_downloads_t *downloads) {
    void *dir;
    char *entry;
    unsigned cap = 0;
    if (!downloads) return -1;
    memset(downloads, 0, sizeof *downloads);
    if (!pod_card_mounted()) return -1;
    dir = opendir(SB_OFFLINE_DIR);
    if (!dir) return 0;
    while ((entry = readdir(dir)) != (char *)0) {
        const char *name = entry + 11; /* the stock MIPS dirent: d_name at byte 11 */
        unsigned i, hash = 0, len = sb_len(name);
        if (len < 10 || name[8] != '-') continue;
        if (len >= 5 && !strcmp(name + len - 5, ".part")) continue;
        for (i = 0; i < 8; ++i) {
            int digit = sb_hex((unsigned char)name[i]);
            if (digit < 0) break;
            hash = (hash << 4) | (unsigned)digit;
        }
        if (i != 8) continue;
        if (downloads->count == cap) {
            unsigned next = cap ? cap * 2 : 32;
            unsigned *grown;
            if (next < cap || next > 200000u) {
                closedir(dir);
                sb_library_downloads_close(downloads);
                return -1;
            }
            grown = (unsigned *)calloc(next, sizeof *grown);
            if (!grown) {
                closedir(dir);
                sb_library_downloads_close(downloads);
                return -1;
            }
            if (downloads->count) memcpy(grown, downloads->hashes, downloads->count * sizeof *grown);
            free(downloads->hashes);
            downloads->hashes = grown;
            cap = next;
        }
        downloads->hashes[downloads->count++] = hash;
    }
    closedir(dir);
    if (downloads->count > 1) {
        unsigned read, write = 1;
        sb_hash_sort(downloads->hashes, downloads->count);
        for (read = 1; read < downloads->count; ++read)
            if (downloads->hashes[read] != downloads->hashes[write - 1])
                downloads->hashes[write++] = downloads->hashes[read];
        downloads->count = write;
    }
    return 0;
}

void sb_library_downloads_close(sb_library_downloads_t *downloads) {
    if (!downloads) return;
    free(downloads->hashes);
    memset(downloads, 0, sizeof *downloads);
}

int sb_library_downloads_contains(const sb_library_downloads_t *downloads, const sb_song_t *song) {
    unsigned lo = 0, hi, hash;
    if (!downloads || !song || !song->id[0]) return 0;
    hash = sb_art_hash(song->id);
    hi = downloads->count;
    while (lo < hi) {
        unsigned mid = lo + (hi - lo) / 2;
        if (downloads->hashes[mid] < hash)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo < downloads->count && downloads->hashes[lo] == hash;
}

void sb_library_index_close(sb_library_index_t *index) {
    if (!index) return;
    if (index->mapping && index->mapping_size) munmap(index->mapping, index->mapping_size);
    memset(index, 0, sizeof *index);
}

int sb_library_stream_url(const sb_song_t *song, char *out, unsigned cap) {
    if (!song || !song->id[0] || !out || !cap || !sbp.base[0] || !sbp.user[0] || !sbp.password[0]) return -1;
    return sb_url(out, cap, sbp.base, "stream", song->id, sbp.user, sbp.password, 0);
}

int sb_library_offline_path(const sb_song_t *song, char *out, unsigned cap) {
    if (!song || !out || !cap) return -1;
    return sb_offline_find(song, out, cap);
}

int sb_library_cover_url(const sb_song_t *song, char *out, unsigned cap) {
    char path[256];
    int n;
    if (!song || !song->cover[0] || !out || !cap || sb_art_path(path, sizeof path, song->cover) || access(path, 0))
        return 0;
    n = snprintf(out, cap, "file://%s", path);
    return n >= 0 && (unsigned)n < cap ? 1 : 0;
}

int sb_library_is_dsd(const sb_song_t *song) { return song && sb_is_dsd(song->suffix); }

int sb_library_matches(const sb_song_t *song, int filter, const char *name, const char *artist) {
    if (!song) return 0;
    switch (filter) {
    case SB_LIBRARY_FILTER_NONE:
        return 1;
    case SB_LIBRARY_FILTER_ALBUM:
        return name && *name && !cc_nocase(song->album, name) &&
               (!artist || !*artist || !cc_nocase(song->album_artist, artist));
    case SB_LIBRARY_FILTER_ARTIST:
        return name && *name && !cc_nocase(song->artist, name);
    case SB_LIBRARY_FILTER_ALBUM_ARTIST:
        return name && *name && !cc_nocase(song->album_artist[0] ? song->album_artist : song->artist, name);
    case SB_LIBRARY_FILTER_COMPOSER:
        return name && *name && !cc_nocase(song->composer, name);
    case SB_LIBRARY_FILTER_GENRE:
        return name && *name && !cc_nocase(song->genre, name);
    default:
        return 0;
    }
}

/* Mixed library queues contain local stSongInfo copies and server rows which
 * retain their original raw stream URL. Keep the bounded queue in view order;
 * no audio is decoded or rewritten here. */
int sb_library_play_queue(const sb_library_queue_entry_t *entries, unsigned count, int at, int how) {
    unsigned begin, n, i, registered = 0, hash, j;
    unsigned target;
    void *q;
    char **owned;
    enum { SB_QUEUE_FIELDS = 8 };
    unsigned rec[REC_SIZE / 4];
    int queue_at, failed = 0;
    if (!entries || !count) return -1;
    if (how == SO_SHUFFLE) {
        begin = 0;
        n = count > SB_QUEUE_MAX ? SB_QUEUE_MAX : count;
        target = pod_rand(n);
    } else {
        if (at < 0 || (unsigned)at >= count) return -1;
        target = (unsigned)at;
        begin = count > SB_QUEUE_MAX && count - target > SB_QUEUE_MAX ? target : 0;
        n = count - begin;
        if (n > SB_QUEUE_MAX) n = SB_QUEUE_MAX;
        target -= begin;
    }
    if (!n || target >= n) return -1;
    q = _create_deque("stSongInfo");
    owned = (char **)calloc((size_t)n * SB_QUEUE_FIELDS, sizeof *owned);
    if (!q || !owned) {
        if (q) deque_destroy(q);
        free(owned);
        pod_toast(SB_ENGLISH("Could not prepare library queue"));
        return -1;
    }
    deque_init(q);
    queue_at = -1;
    sbp.play_count = 0;
    for (i = 0; i < n; ++i) {
        const sb_library_queue_entry_t *entry = &entries[begin + i];
        if (entry->source == SB_LIBRARY_LOCAL && entry->local_record) {
            _deque_push_back(q, (void *)entry->local_record);
        } else if (entry->server_song) {
            const sb_song_t *song = entry->server_song;
            char path[SB_URL], filename[SB_TEXT + 16];
            char *fields[SB_QUEUE_FIELDS] = {0};
            if (entry->source == SB_LIBRARY_STREAM) {
                if (sb_library_is_dsd(song) ||
                    (entry->stream_url ? snprintf(path, sizeof path, "%s", entry->stream_url) >= (int)sizeof path
                                       : sb_library_stream_url(song, path, sizeof path))) {
                    failed = 1;
                    break;
                }
            } else if (sb_library_offline_path(song, path, sizeof path) != 1) {
                failed = 1;
                break;
            }
            if (sb_track_filename(filename, sizeof filename, song) < 0) {
                failed = 1;
                break;
            }
            fields[0] = strdup(filename[0] ? filename : SB_ENGLISH("Untitled"));
            fields[1] = strdup(path);
            fields[2] = strdup(song->title[0] ? song->title : SB_ENGLISH("Untitled"));
            fields[3] = strdup(song->album);
            fields[4] = strdup(song->artist);
            fields[5] = strdup(song->genre);
            fields[6] = strdup(song->composer);
            fields[7] = strdup(song->album_artist[0] ? song->album_artist : song->artist);
            for (j = 0; j < SB_QUEUE_FIELDS; ++j)
                if (!fields[j]) failed = 1;
            if (failed) {
                for (j = 0; j < SB_QUEUE_FIELDS; ++j) free(fields[j]);
                break;
            }
            memset(rec, 0, sizeof rec);
            hash = 2166136261u;
            for (j = 0; song->id[j]; ++j) hash = (hash ^ (unsigned char)song->id[j]) * 16777619u;
            hash = (hash & 0x3fffffffu) + 2u;
            do {
                unsigned collision = 0;
                for (j = 0; j < registered; ++j)
                    if (sbp.play_ids[j] == -(int)hash) {
                        collision = 1;
                        break;
                    }
                if (collision)
                    hash = hash == 0x3fffffffu ? 2u : hash + 1u;
                else
                    break;
            } while (1);
            *(int *)((char *)rec + REC_ID) = -(int)hash;
            *(char **)((char *)rec + REC_NAME) = fields[0];
            *(char **)((char *)rec + REC_PATH) = fields[1];
            *(char **)((char *)rec + REC_TITLE) = fields[2];
            *(char **)((char *)rec + REC_ALBUM) = fields[3];
            *(char **)((char *)rec + REC_ARTIST) = fields[4];
            *(char **)((char *)rec + REC_GENRE) = fields[5];
            *(char **)((char *)rec + REC_COMPOSER) = fields[6];
            *(char **)((char *)rec + REC_ALBUM_ARTIST) = fields[7];
            *(int *)((char *)rec + REC_TYPE) = 8;
            *(int *)((char *)rec + REC_CLASS) = CLASS_ALL_SONGS;
            *(int *)((char *)rec + REC_TRACK) = (int)song->track;
            *(int *)((char *)rec + REC_DISC) = (int)song->disc;
            _deque_push_back(q, rec);
            if (deque_size(q) != i + 1) {
                for (j = 0; j < SB_QUEUE_FIELDS; ++j) free(fields[j]);
                failed = 1;
                break;
            }
            for (j = 0; j < SB_QUEUE_FIELDS; ++j) owned[i * SB_QUEUE_FIELDS + j] = fields[j];
            if (registered < SB_QUEUE_MAX) {
                sbp.play_ids[registered] = -(int)hash;
                memset(sbp.play_cover[registered], 0, sizeof sbp.play_cover[registered]);
                if (song->cover[0]) memcpy(sbp.play_cover[registered], song->cover, sizeof sbp.play_cover[registered]);
                ++registered;
            }
        } else {
            failed = 1;
            break;
        }
        if (i == target) queue_at = (int)i;
    }
    if (failed || queue_at < 0 || deque_size(q) != n) {
        for (i = 0; i < n * SB_QUEUE_FIELDS; ++i) free(owned[i]);
        free(owned);
        deque_destroy(q);
        sbp.play_count = 0;
        pod_toast(SB_ENGLISH("Could not prepare the complete library queue"));
        return -1;
    }
    sbp.play_count = (int)registered;
    if (how == SO_IN_ORDER)
        pod_set_in_order_for_queue();
    else if (how == SO_SHUFFLE)
        pod_set_mode_for_queue(MODE_SHUFFLE);
    pod_open_player(q, queue_at, CLASS_ALL_SONGS);
    deque_destroy(q);
    for (i = 0; i < n * SB_QUEUE_FIELDS; ++i) free(owned[i]);
    free(owned);
    return 0;
}

/* Stock Recent Played/Most Played rows persist the in-memory stream record's
 * URL and metadata. Resolve it back to the synced index when possible (for its
 * cover and stable server ID), then use that exact raw URL for the single-item
 * replay so a missing SD file is never mistaken for the stream source. */
int sb_library_play_recent(void *record) {
    const char *path, *title, *artist, *album;
    const char *stream_url;
    sb_song_t fallback;
    sb_library_index_t index;
    sb_library_queue_entry_t entry;
    unsigned i;
    int id;
    if (!record) return -1;
    path = *(char **)((char *)record + REC_PATH);
    stream_url = path && (sb_prefix(path, "http://") || sb_prefix(path, "https://")) ? path : (const char *)0;
    /* Let the stock local queue win whenever its file is still present. If a
     * remembered local path has gone missing, the same synced server track is
     * a useful fallback instead of the stock "Storage unavailable" error. */
    if (path && !stream_url && access(path, F_OK) == 0) return -1;
    title = *(char **)((char *)record + REC_TITLE);
    artist = *(char **)((char *)record + REC_ARTIST);
    album = *(char **)((char *)record + REC_ALBUM);
    id = *(int *)((char *)record + REC_ID);
    memset(&fallback, 0, sizeof fallback);
    snprintf(fallback.title, sizeof fallback.title, "%s", title ? title : "");
    snprintf(fallback.artist, sizeof fallback.artist, "%s", artist ? artist : "");
    snprintf(fallback.album, sizeof fallback.album, "%s", album ? album : "");
    if (sb_library_index_open(&index) == 0) {
        for (i = 0; i < index.count; ++i) {
            const sb_song_t *song = &index.songs[i];
            unsigned hash = 2166136261u, j;
            for (j = 0; song->id[j]; ++j) hash = (hash ^ (unsigned char)song->id[j]) * 16777619u;
            hash = (hash & 0x3fffffffu) + 2u;
            if (!sb_library_is_dsd(song) &&
                ((stream_url && id < 0 && (unsigned)-id == hash) ||
                 (!cc_nocase(song->title, fallback.title) && !cc_nocase(song->artist, fallback.artist) &&
                  !cc_nocase(song->album, fallback.album)))) {
                memset(&entry, 0, sizeof entry);
                entry.server_song = song;
                entry.stream_url = stream_url;
                entry.server_index = i;
                entry.source = SB_LIBRARY_STREAM;
                id = sb_library_play_queue(&entry, 1, 0, SO_KEEP);
                sb_library_index_close(&index);
                return id;
            }
        }
        sb_library_index_close(&index);
    }
    if (!stream_url) return -1;
    memset(&entry, 0, sizeof entry);
    entry.server_song = &fallback;
    entry.stream_url = path;
    entry.source = SB_LIBRARY_STREAM;
    return sb_library_play_queue(&entry, 1, 0, SO_KEEP);
}

static void sb_set_active_tab(int active) {
    unsigned c = pal_fill();
    char ink[8];
    unsigned i;
    snprintf(ink, sizeof ink, "#%02x%02x%02x", c & 255u, (c >> 8) & 255u, (c >> 16) & 255u);
    for (i = 0; i < 2; ++i) {
        if (sbp.tab_label[i])
            widget_set_prop_str(sbp.tab_label[i], "style:normal:text_color", (int)i == active ? ink : "#FFFFFF");
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
    if (sbp.connect_label) widget_set_text_utf8(sbp.connect_label, SB_ENGLISH(sbp.connected ? "Connected" : "Server"));
}

static int sb_page_timer_missing(void) { return sbp.win && !sbp.timer; }

static int sb_input_locked(void) { return sb_page_timer_missing() || ((sbp.busy || sbp.done) && sbp.mode != 4); }

static int sb_fetch_art(sb_sink_t *sink, const char *id) {
    char url[SB_URL], path[256], png[256], part[272], extra[32];
    unsigned free_kb = 0;
    int fd, ok = 0, is_jpeg, is_png;
    if (!id[0] || !pod_card_mounted() || !pn_free_kb("/mnt/mmc", &free_kb) || free_kb < 34816 ||
        sb_art_path(path, sizeof path, id) || access(path, 0) == 0)
        return 0;
    mkdir(CARD_DIR, 0755);
    mkdir(SB_ART_DIR, 0755);
    snprintf(extra, sizeof extra, "&size=240");
    if (sb_url(url, sizeof url, sbp.base, "getCoverArt", id, sbp.user, sbp.password, extra) ||
        snprintf(part, sizeof part, "%s.part", path) >= (int)sizeof part)
        return 0;
    fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    memset(sink, 0, sizeof *sink);
    sink->fd = fd;
    sink->limit = SB_ART_MAX;
    if (!sb_http_timeout(url, sink, 24L) && sink->written > 4 && sink->prefix_used >= 4 && fsync(fd) == 0 &&
        close(fd) == 0) {
        fd = -1;
        is_jpeg = sink->prefix[0] == 0xff && sink->prefix[1] == 0xd8 && sink->prefix[2] == 0xff;
        is_png = sink->prefix_used >= 8 && sink->prefix[0] == 0x89 && sink->prefix[1] == 'P' &&
                 sink->prefix[2] == 'N' && sink->prefix[3] == 'G' && sink->prefix[4] == 0x0d &&
                 sink->prefix[5] == 0x0a && sink->prefix[6] == 0x1a && sink->prefix[7] == 0x0a;
        if (is_png && !sb_art_path_ext(png, sizeof png, id, "png"))
            ok = rename(part, png) == 0;
        else if (is_jpeg)
            ok = rename(part, path) == 0;
    }
    if (fd >= 0) close(fd);
    if (!ok) unlink(part);
    sink->fd = -1;
    return ok;
}

static int sb_text_type(const char *type) {
    char lower[64];
    unsigned i;
    if (!type || !type[0]) return 0;
    for (i = 0; i + 1 < sizeof lower && type[i]; ++i) lower[i] = (char)sb_ascii_lower((unsigned char)type[i]);
    lower[i] = 0;
    return sb_prefix(lower, "text/") || sb_prefix(lower, "application/json") || sb_prefix(lower, "application/xml") ||
           sb_prefix(lower, "application/xhtml") || sb_prefix(lower, "application/problem+");
}

static int sb_audio_response_valid(const sb_sink_t *sink, long expected_status, long long expected_range_start) {
    unsigned i = 0;
    if (!sink || sink->http_status != expected_status || sink->written <= 0 || sink->prefix_used < 3 ||
        (sink->content_length >= 0 && sink->written != sink->content_length) || sb_text_type(sink->content_type))
        return 0;
    if (expected_status == 206 &&
        (!sink->range_seen || sink->range_start != expected_range_start || sink->range_end < sink->range_start ||
         sink->range_total == -2 || sink->range_end - sink->range_start == LLONG_MAX ||
         sink->written != sink->range_end - sink->range_start + 1))
        return 0;
    while (i < sink->prefix_used &&
           (sink->prefix[i] == ' ' || sink->prefix[i] == '\t' || sink->prefix[i] == '\r' || sink->prefix[i] == '\n'))
        ++i;
    if (i < sink->prefix_used && (sink->prefix[i] == '<' || sink->prefix[i] == '{' || sink->prefix[i] == '[')) return 0;
    return 1;
}

static void sb_sink_prepare_file(sb_sink_t *sink, int fd) {
    sink->used = 0;
    sink->prefix_used = 0;
    sink->fd = fd;
    sink->curl_result = 0;
    sink->http_status = 0;
    sink->content_length = -1;
    sink->range_start = sink->range_end = sink->range_total = -1;
    sink->range_seen = 0;
    sink->content_type[0] = 0;
    sink->written = 0;
    sink->last_check = 0;
    sink->limit = 0;
}

static int sb_download_file(const char *url, const char *part, const char *final, sb_sink_t *sink) {
    char range[40];
    long long offset;
    int fd, rc = -1, resumable = 0;
    unsigned free_kb = 0;
    if (!pod_card_mounted() || !pn_free_kb("/mnt/mmc", &free_kb)) {
        sb_download_set_error(SB_DL_ERR_CARD);
        return -1;
    }
    if (free_kb <= 32768) {
        sb_download_set_error(SB_DL_ERR_SPACE);
        return -1;
    }
    fd = open(part, O_RDWR | O_CREAT, 0644);
    if (fd < 0) {
        sb_download_set_error(SB_DL_ERR_STORAGE);
        return -1;
    }
    offset = lseek(fd, 0, 2);
    if (offset < 0) {
        /* Stock lseek uses a 32-bit long. Restart an unseekable partial rather
         * than appending a full response at an unknown offset. */
        int oldfd = fd;
        fd = -1;
        if (close(oldfd) < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        offset = 0;
    }
    sbp.download_offset = offset;
    sb_sink_prepare_file(sink, fd);
    if (offset > 0) {
        unsigned want = offset < (long long)sizeof sink->prefix ? (unsigned)offset : sizeof sink->prefix;
        int got;
        if (lseek(fd, 0, 0) < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        got = read(fd, sink->prefix, want);
        if (got != (int)want || lseek(fd, 0, 2) < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        sink->prefix_used = want;
        if (snprintf(range, sizeof range, "%lld-", offset) >= (int)sizeof range) {
            sb_download_set_error(SB_DL_ERR_PATH);
            goto done;
        }
    } else
        range[0] = 0;
    rc = sb_http_timeout_range(url, sink, 0L, range);
    if (offset > 0 && (sink->http_status == 200 || sink->http_status == 416)) {
        int oldfd = fd;
        fd = -1;
        if (close(oldfd) < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
            goto done;
        }
        offset = 0;
        sbp.download_offset = 0;
        sb_sink_prepare_file(sink, fd);
        rc = sb_http_timeout_range(url, sink, 0L, (const char *)0);
    }
    if (!rc) {
        if (!sb_audio_response_valid(sink, offset > 0 ? 206 : 200, offset))
            sb_download_set_error(SB_DL_ERR_RESPONSE);
        else if (fsync(fd) < 0)
            sb_download_set_error(SB_DL_ERR_STORAGE);
        else {
            int close_rc = close(fd);
            fd = -1;
            if (close_rc < 0)
                sb_download_set_error(SB_DL_ERR_STORAGE);
            else if (!rename(part, final)) {
                int dir = open(SB_OFFLINE_DIR, O_RDONLY, 0);
                if (dir >= 0) {
                    (void)fsync(dir);
                    close(dir);
                }
                sb_atomic_store(&sbp.download_resumable, 0);
                sink->fd = -1;
                return 1;
            } else {
                sb_download_set_error(SB_DL_ERR_STORAGE);
                resumable = 1;
            }
        }
    } else {
        if (sink->http_status >= 400)
            sb_download_set_error(SB_DL_ERR_SERVER);
        else if (sb_atomic_load(&sbp.download_error) == SB_DL_ERR_NONE)
            sb_download_set_error(SB_DL_ERR_NETWORK);
        if (sink->curl_result != 0 &&
            (sink->http_status == 0 || sink->http_status >= 500 || sink->http_status == 408 ||
             sink->http_status == 429 || sink->curl_result == CURLE_PARTIAL_FILE ||
             sink->curl_result == CURLE_OPERATION_TIMEDOUT || sink->curl_result == CURLE_WRITE_ERROR))
            resumable = 1;
    }
    if (sb_atomic_load(&sbp.download_error) == SB_DL_ERR_FILE_LIMIT) resumable = 0;
    if (resumable && sink->written == 0 && offset == 0) resumable = 0;
    if (resumable && pod_card_mounted())
        sb_atomic_store(&sbp.download_resumable, 1);
    else {
        sb_atomic_store(&sbp.download_resumable, 0);
        if (pod_card_mounted()) unlink(part);
    }
done:
    if (fd >= 0) close(fd);
    sink->fd = -1;
    return -1;
}

static int sb_sync_art(sb_sink_t *sink) {
    sb_index_head_t head;
    sb_song_t song;
    char failed[24][SB_ID];
    unsigned i, j, total, failed_count = 0, failed_next = 0;
    int rc = 1;
    long file_size;
    int fd = open(SB_INDEX_FILE, O_RDONLY, 0);
    if (fd < 0 || read(fd, &head, sizeof head) != sizeof head || !sb_index_head_valid(head) ||
        !sb_index_file_size(fd, head, &file_size)) {
        if (fd >= 0) close(fd);
        sbp.art_syncing = 0;
        return -1;
    }
    (void)file_size;
    total = head.count + head.dsd_count;
    sbp.art_syncing = 1;
    sbp.art_count = sbp.art_total = sbp.art_cached = sbp.art_failed = 0;
    for (i = 0; i < total; ++i) {
        if (sb_atomic_load(&sbp.art_pause_request)) {
            rc = 2;
            break;
        }
        if (!pod_card_mounted() || sbp.connection_lost) {
            rc = -1;
            break;
        }
        if (read(fd, &song, sizeof song) != sizeof song || !sb_song_record_valid(&song)) {
            rc = -1;
            break;
        }
        if (song.cover[0]) {
            char path[256];
            int retry = 1;
            if (sb_art_path(path, sizeof path, song.cover)) {
                ++sbp.art_failed;
            } else if (access(path, 0) != 0) {
                for (j = 0; j < failed_count; ++j)
                    if (!strcmp(failed[j], song.cover)) {
                        retry = 0;
                        break;
                    }
                if (retry) {
                    if (sb_fetch_art(sink, song.cover))
                        ++sbp.art_cached;
                    else if (sb_atomic_load(&sbp.art_pause_request)) {
                        rc = 2;
                        break;
                    } else {
                        ++sbp.art_failed;
                        memcpy(failed[failed_next], song.cover, sizeof failed[failed_next]);
                        failed[failed_next][sizeof failed[failed_next] - 1] = 0;
                        failed_next = (failed_next + 1) % (sizeof failed / sizeof failed[0]);
                        if (failed_count < sizeof failed / sizeof failed[0]) ++failed_count;
                    }
                }
            }
        }
        sbp.art_count = (int)i + 1;
        sbp.art_total = (int)total;
    }
    close(fd);
    sbp.art_syncing = 0;
    if (rc == 1 && sbp.art_failed) rc = 0;
    if (sbp.connection_lost || !pod_card_mounted()) rc = -1;
    return rc;
}

const char *sb_cover_file(void *track) {
    unsigned i;
    int id;
    if (!track) return (const char *)0;
    id = *(int *)((char *)track + REC_ID);
    for (i = 0; i < (unsigned)sbp.play_count; ++i) {
        char path[256];
        if (sbp.play_ids[i] != id || !sbp.play_cover[i][0] || sb_art_path(path, sizeof path, sbp.play_cover[i]) ||
            access(path, 0) != 0)
            continue;
        memcpy(sbp.cover_file, path, sizeof path);
        return sbp.cover_file;
    }
    return (const char *)0;
}

static int sb_index_load(unsigned offset, int dsd_view) {
    sb_index_head_t head;
    unsigned count, base;
    int fd = open(SB_INDEX_FILE, O_RDONLY, 0), n, i;
    long file_size;
    long long record_offset;
    if (fd < 0) return -1;
    n = read(fd, &head, sizeof head);
    if (n != sizeof head || !sb_index_head_valid(head) || !sb_index_file_size(fd, head, &file_size)) {
        close(fd);
        return -1;
    }
    (void)file_size;
    count = dsd_view ? head.dsd_count : head.count;
    base = dsd_view ? head.count : 0;
    if (offset > count || (count && offset == count)) {
        close(fd);
        return -1;
    }
    record_offset = (long long)sizeof head + (long long)(base + offset) * sizeof(sb_song_t);
    if (record_offset > LONG_MAX || lseek(fd, (long)record_offset, 0) < 0) {
        close(fd);
        return -1;
    }
    sbp.count = 0;
    for (i = 0; i < SB_MAX && offset + (unsigned)i < count; ++i) {
        if (read(fd, &sbp.songs[i], sizeof(sb_song_t)) != sizeof(sb_song_t) || !sb_song_record_valid(&sbp.songs[i])) {
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

static void sb_az_clear(void) {
    az_rail_end(&sbp.az);
    free(sbp.az_rank);
    sbp.az_rank = (unsigned char *)0;
    sbp.az.count = sbp.az.content = sbp.az.nsec = 0;
    if (sbp.az.rail) {
        widget_set_visible(sbp.az.rail, 0, 0);
        widget_set_sensitive(sbp.az.rail, 0);
    }
}

/* The server list is virtualized over the full index. Build only the compact
 * section map, so the rail can jump across pages without loading every row. */
static void sb_az_rebuild(void) {
    sb_library_index_t index;
    unsigned count, base, rows, i, step;
    int dsd_view = sbp.view == SB_VIEW_DSD && sbp.dsd_view;
    if (!sbp.win || !sbp.az.rail || !sbp.indexed_view || !((sbp.view == SB_VIEW_TRACKS && !sbp.dsd_view) || dsd_view) ||
        sb_library_index_open(&index)) {
        sb_az_clear();
        return;
    }
    count = dsd_view ? index.dsd_count : index.count;
    base = dsd_view ? index.count : 0;
    step = sbp.grid_mode ? 2u : 1u;
    rows = sbp.grid_mode ? (count + 1u) / 2u : count;
    sb_az_clear();
    if (!rows || rows > SB_SYNC_LIMIT) {
        sb_library_index_close(&index);
        return;
    }
    sbp.az_rank = (unsigned char *)calloc(rows, 1);
    if (!sbp.az_rank) {
        sb_library_index_close(&index);
        return;
    }
    for (i = 0; i < rows; ++i) {
        unsigned at = i * step;
        sbp.az_rank[i] = (unsigned char)az_rank_of(cc_name_initial(index.songs[base + at].title));
    }
    sb_library_index_close(&index);
    sbp.az.count = (int)rows;
    sbp.az.top = 0;
    sbp.az.row = sbp.grid_mode ? SB_GRID_PITCH : SB_ROW_H;
    sbp.az.content = (int)rows * sbp.az.row;
    if (sbp.az.content < SB_VISIBLE * SB_ROW_H) sbp.az.content = SB_VISIBLE * SB_ROW_H;
    sbp.az.view_h = SB_VIEWPORT_H;
    sbp.az.rail_origin = SB_LIST_TOP;
    sbp.az.rail_only = 1;
    az_sections(&sbp.az, sbp.az_rank, 1);
    free(sbp.az_rank);
    sbp.az_rank = (unsigned char *)0;
    if (sbp.az.nsec > 0) az_rail_fit(&sbp.az, SB_VIEWPORT_H);
}

static int sb_on_az_rail(void *ctx, void *event) {
    (void)ctx;
    if (sbp.win && sbp.indexed_view && (sbp.view == SB_VIEW_TRACKS || sbp.view == SB_VIEW_DSD)) {
        az_rail_event(&sbp.az, event);
        (void)sb_scroll_event((void *)0, (void *)0);
        widget_invalidate_force(sbp.scroll, (void *)0);
    }
    return RET_OK;
}

static int sb_on_az_paint(void *ctx, void *event) {
    (void)ctx;
    if (sbp.win && sbp.indexed_view && (sbp.view == SB_VIEW_TRACKS || sbp.view == SB_VIEW_DSD))
        az_rail_paint(&sbp.az, event);
    return RET_OK;
}

static int sb_index_read_range(unsigned offset, unsigned count, sb_song_t *songs) {
    sb_index_head_t head;
    unsigned i;
    int fd = open(SB_INDEX_FILE, O_RDONLY, 0);
    long size;
    long long record_offset;
    if (fd < 0 || !songs || !count || count > SB_MAX) {
        if (fd >= 0) close(fd);
        return -1;
    }
    if (read(fd, &head, sizeof head) != sizeof head || !sb_index_head_valid(head) ||
        !sb_index_file_size(fd, head, &size) || offset > head.count || count > head.count - offset) {
        close(fd);
        return -1;
    }
    (void)size;
    record_offset = (long long)sizeof head + (long long)offset * sizeof(sb_song_t);
    if (record_offset > LONG_MAX || lseek(fd, (long)record_offset, 0) < 0) {
        close(fd);
        return -1;
    }
    for (i = 0; i < count; ++i)
        if (read(fd, &songs[i], sizeof songs[i]) != sizeof songs[i] || !sb_song_record_valid(&songs[i])) {
            close(fd);
            return -1;
        }
    close(fd);
    return (int)count;
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
    sb_az_rebuild();
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
        int local_file = 0;
        int source = sbp.row_data + i;
        int track_actions =
            source >= 0 && source < sbp.count &&
            (sbp.view == SB_VIEW_SEARCH || sbp.view == SB_VIEW_DSD || (sbp.view == SB_VIEW_TRACKS && sbp.indexed_view));
        int is_dsd = track_actions && sb_is_dsd(sbp.songs[source].suffix);
        if (track_actions) {
            char path[320];
            local_file = sb_offline_find(&sbp.songs[source], path, sizeof path);
            widget_set_prop_str(sbp.row_download_icon[i], "image", local_file ? "pod_ic_rd_remove" : "pod_sb_download");
            widget_set_prop_str(sbp.grid_download_icon[i], "image",
                                local_file ? "pod_ic_rd_remove" : "pod_sb_download");
        } else {
            widget_set_prop_str(sbp.row_download_icon[i], "image", "pod_sb_download");
            widget_set_prop_str(sbp.grid_download_icon[i], "image", "pod_sb_download");
        }
        widget_resize(sbp.title[i], track_actions ? SB_LIST_TEXT_W : 278, 24);
        widget_resize(sbp.sub[i], track_actions ? SB_LIST_TEXT_W : 278, 20);
        widget_set_visible(sbp.art[i], track_actions, 0);
        widget_set_visible(sbp.row_download[i], track_actions && !sbp.grid_mode, 0);
        widget_set_sensitive(sbp.row_download[i], track_actions && !sbp.grid_mode);
        widget_set_visible(sbp.grid_download[i], track_actions && sbp.grid_mode, 0);
        widget_set_sensitive(sbp.grid_download[i], track_actions && sbp.grid_mode);
        if (source >= 0 && source < sbp.count) {
            char art[256], uri[272];
            widget_set_text_utf8(sbp.title[i],
                                 sbp.songs[source].title[0] ? sbp.songs[source].title : SB_ENGLISH("Untitled"));
            snprintf(detail, sizeof detail, "%s  •  %s", sbp.songs[source].artist, sbp.songs[source].album);
            widget_set_text_utf8(sbp.sub[i], detail);
            widget_set_text_utf8(sbp.grid_title[i],
                                 sbp.songs[source].title[0] ? sbp.songs[source].title : SB_ENGLISH("Untitled"));
            widget_set_text_utf8(sbp.grid_sub[i], sbp.songs[source].artist);
            const char *placeholder = is_dsd ? "pod_ic_dsd_art" : "pod_ic_navidrome_art";
            if (sbp.songs[source].cover[0] && !sb_art_path(art, sizeof art, sbp.songs[source].cover) &&
                access(art, 0) == 0) {
                snprintf(uri, sizeof uri, "file://%s", art);
            } else {
                snprintf(uri, sizeof uri, "%s", placeholder);
            }
            widget_set_prop_str(sbp.art[i], "image", sbp.grid_mode ? placeholder : uri);
            widget_set_prop_str(sbp.grid_art[i], "image", sbp.grid_mode ? uri : placeholder);
            widget_set_visible(sbp.title[i], 1, 0);
            widget_set_visible(sbp.sub[i], 1, 0);
        } else {
            widget_set_text_utf8(sbp.title[i], "");
            widget_set_text_utf8(sbp.sub[i], "");
            widget_set_text_utf8(sbp.grid_title[i], "");
            widget_set_text_utf8(sbp.grid_sub[i], "");
            widget_set_visible(sbp.art[i], 0, 0);
            widget_set_prop_str(sbp.art[i], "image", "");
            widget_set_prop_str(sbp.grid_art[i], "image", "");
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
    if (!sink) {
        if (sbp.mode == 3)
            sbp.sync_error = SB_SYNC_ERR_MEMORY;
        else if (sbp.mode == 2)
            sb_download_set_error(SB_DL_ERR_MEMORY);
        goto finished;
    }
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
    } else if (sbp.mode == 2 && sbp.download_song_valid) {
        sb_song_t *song = &sbp.download_song;
        char part[336], final[320];
        int mkdir_rc = mkdir(SB_OFFLINE_DIR, 0775), part_len;
        if (mkdir_rc && access(SB_OFFLINE_DIR, 0) != 0) {
            sb_download_set_error(SB_DL_ERR_STORAGE);
        } else if (sb_url(url, sizeof url, sbp.base, "download", song->id, sbp.user, sbp.password, 0)) {
            sb_download_set_error(SB_DL_ERR_REQUEST);
        } else if (sb_offline_path(song, final, sizeof final) != 0 ||
                   (part_len = snprintf(part, sizeof part, "%s.part", final)) < 0 ||
                   (unsigned)part_len >= sizeof part) {
            sb_download_set_error(SB_DL_ERR_PATH);
        } else if (access(final, 0) == 0) {
            sb_download_set_error(SB_DL_ERR_EXISTS);
        } else {
            rc = sb_download_file(url, part, final, sink);
        }
        if (rc == 1 && sbp.download_is_dsd) {
            sbp.library_refresh_result = -1;
            sbp.library_refreshing = 1;
            __sync_synchronize();
            if (pod_card_mounted()) sbp.library_refresh_result = scanSpecFolder(SB_OFFLINE_DIR, 0);
            sbp.library_refreshing = 0;
        }
    } else if (sbp.mode == 3)
        rc = sb_sync_library(sink);
    else if (sbp.mode == 4)
        rc = sb_sync_art(sink);
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
    if (sb_page_timer_missing()) return -1;
    if (get_wifisignal() <= 0) {
        sb_set_connected(0);
        if (sbp.status) {
            widget_set_text_utf8(sbp.status, SB_ENGLISH("Connect to Wi-Fi before using Navidrome."));
            widget_set_prop_str(sbp.status, "style:normal:text_color", "#FF453A");
        }
        return -1;
    }
    if (sbp.busy || sbp.done || !sbp.user[0] || !sbp.password[0]) return -1;
    if (!sb_curl_init()) return -1;
    sbp.mode = mode;
    sbp.connection_lost = 0;
    sb_atomic_store(&sbp.http_status, 0);
    if (mode == 3) {
        sbp.sync_count = sbp.sync_shown = 0;
        sbp.sync_limit_hit = 0;
        sbp.sync_error = SB_SYNC_ERR_NONE;
    }
    if (mode == 4) {
        sbp.art_count = sbp.art_total = 0;
        sbp.art_cached = sbp.art_failed = 0;
        sbp.art_shown = 0;
        sb_atomic_store(&sbp.art_pause_request, 0);
        sbp.art_syncing = 1;
    }
    if (mode == 2) {
        if (!sbp.download_song_valid && sbp.selected >= 0 && sbp.selected < sbp.count) {
            sb_song_copy(&sbp.download_song, &sbp.songs[sbp.selected]);
            sbp.download_song_valid = 1;
        }
        if (!sbp.download_song_valid) return -1;
        sbp.library_refreshing = 0;
        sbp.library_refresh_result = 0;
        sbp.library_refresh_shown = 0;
        sb_atomic_store(&sbp.download_active, 1);
        sb_atomic_store(&sbp.download_percent, 0);
        sb_atomic_store(&sbp.download_percent_known, 0);
        sb_atomic_store(&sbp.download_kb, 0);
        sb_atomic_store(&sbp.download_resumable, 0);
        sbp.download_offset = 0;
        sb_atomic_store(&sbp.art_pause_request, 0);
        sbp.download_status_kind = -1;
        sbp.download_status_value = -1;
        sbp.download_anim_x = sbp.download_anim_ticks = 0;
        sbp.download_anim_dir = 1;
        sbp.download_is_dsd = sb_is_dsd(sbp.download_song.suffix);
        sb_atomic_store(&sbp.download_error, SB_DL_ERR_NONE);
    }
    sbp.done = 0;
    sbp.result = -1;
    __sync_synchronize();
    sbp.busy = 1;
    if (pthread_create(&th, (void *)0, sb_worker, (void *)0) != 0) {
        sbp.busy = 0;
        if (mode == 2) {
            sbp.download_song_valid = 0;
            sb_atomic_store(&sbp.download_active, 0);
        }
        if (mode == 4) sbp.art_syncing = 0;
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

static void sb_download_failure_status(void) {
    char msg[96];
    int error = sb_atomic_load(&sbp.download_error);
    int status = sb_atomic_load(&sbp.http_status);
    if (status == 401) {
        sb_set_status(SB_ENGLISH("Navidrome rejected login (HTTP 401)."));
    } else if (status == 403) {
        sb_set_status(SB_ENGLISH("Server denied this track (HTTP 403)."));
    } else if (error == SB_DL_ERR_SPACE && sb_atomic_load(&sbp.download_resumable)) {
        sb_set_status(SB_ENGLISH("Low space. Free space, then tap Download to resume."));
    } else if (error == SB_DL_ERR_SPACE) {
        sb_set_status(SB_ENGLISH("Not enough SD space for this track."));
    } else if (error == SB_DL_ERR_CARD) {
        sb_set_status(SB_ENGLISH("SD card is unavailable."));
    } else if (error == SB_DL_ERR_FILE_LIMIT) {
        sb_set_status(SB_ENGLISH("This track exceeds the supported download size."));
    } else if (error == SB_DL_ERR_STORAGE && sb_atomic_load(&sbp.download_resumable)) {
        sb_set_status(SB_ENGLISH("SD write paused. Check the card, then tap Download to resume."));
    } else if (error == SB_DL_ERR_STORAGE) {
        sb_set_status(SB_ENGLISH("SD write failed. Check space or file-size limits."));
    } else if (error == SB_DL_ERR_PATH) {
        sb_set_status(SB_ENGLISH("Could not prepare this track's SD file."));
    } else if (error == SB_DL_ERR_EXISTS) {
        sb_set_status(SB_ENGLISH("This file already exists on the SD card."));
    } else if (error == SB_DL_ERR_REQUEST) {
        sb_set_status(SB_ENGLISH("Could not prepare this track's server request."));
    } else if (error == SB_DL_ERR_RESPONSE) {
        sb_set_status(SB_ENGLISH("Server returned invalid audio for this track."));
    } else if (error == SB_DL_ERR_MEMORY) {
        sb_set_status(SB_ENGLISH("Not enough memory to start this download."));
    } else if (status == 404) {
        sb_set_status(SB_ENGLISH("Server cannot find this track (HTTP 404)."));
    } else if (status >= 400 && sb_atomic_load(&sbp.download_resumable)) {
        sb_set_status(SB_ENGLISH("Server interrupted this download; tap Download to resume."));
    } else if (status >= 400) {
        snprintf(msg, sizeof msg, SB_ENGLISH("Track request failed (HTTP %d)."), status);
        sb_set_status(msg);
    } else if (sb_atomic_load(&sbp.download_resumable)) {
        sb_set_status(SB_ENGLISH("Download paused; tap Download to resume."));
    } else if (error == SB_DL_ERR_NETWORK) {
        sb_set_status(SB_ENGLISH("Network error while downloading this track."));
    } else {
        sb_set_status(SB_ENGLISH("Download failed. Check this track on the server."));
    }
}

static void sb_download_progress_hide(void) {
    if (sbp.download_bar) widget_set_visible(sbp.download_bar, 0, 0);
    if (sbp.download_fill) widget_set_visible(sbp.download_fill, 0, 0);
}

static void sb_download_progress_update(void) {
    char msg[72];
    int library_refresh = !!sbp.library_refreshing;
    int known = !library_refresh && !!sb_atomic_load(&sbp.download_percent_known);
    int value = library_refresh ? 0
                : known         ? sb_atomic_load(&sbp.download_percent)
                                : sb_atomic_load(&sbp.download_kb) / 1024;
    if (sbp.download_bar) widget_set_visible(sbp.download_bar, 1, 0);
    if (sbp.download_fill) {
        int width, x = 0;
        if (known) {
            width = SB_DL_BAR_W * value / 100;
            if (width < 1) width = 1;
        } else {
            width = 56;
            if (++sbp.download_anim_ticks >= 2) {
                sbp.download_anim_ticks = 0;
                sbp.download_anim_x += sbp.download_anim_dir * 12;
                if (sbp.download_anim_x >= SB_DL_BAR_W - width) {
                    sbp.download_anim_x = SB_DL_BAR_W - width;
                    sbp.download_anim_dir = -1;
                } else if (sbp.download_anim_x <= 0) {
                    sbp.download_anim_x = 0;
                    sbp.download_anim_dir = 1;
                }
            }
            x = sbp.download_anim_x;
        }
        widget_move(sbp.download_fill, x, 0);
        widget_resize(sbp.download_fill, width, SB_DL_BAR_H);
        widget_set_visible(sbp.download_fill, 1, 0);
    }
    if (sbp.download_status_kind != (library_refresh ? 2 : known) || sbp.download_status_value != value) {
        if (library_refresh)
            snprintf(msg, sizeof msg, SB_ENGLISH("Navidrome busy · updating SD library"));
        else if (known)
            snprintf(msg, sizeof msg, SB_ENGLISH("Navidrome busy · downloading %d%%"), value);
        else if (value)
            snprintf(msg, sizeof msg, SB_ENGLISH("Navidrome busy · %d MB downloaded"), value);
        else
            snprintf(msg, sizeof msg, SB_ENGLISH("Navidrome busy · download starting"));
        sb_set_status(msg);
        sbp.download_status_kind = library_refresh ? 2 : known;
        sbp.download_status_value = value;
    }
}

static int sb_download_blocked(int at) {
    if (!sbp.busy) return 0;
    if (sbp.mode == 4 && at >= 0 && at < sbp.count && sb_is_dsd(sbp.songs[at].suffix))
        sb_set_status(SB_ENGLISH("Artwork cache busy. Retry DSD download when it finishes."));
    else
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
    return 1;
}

#define SB_STREAM_POLL_MS 500
#define SB_STREAM_GRACE_MS 5000

static int sb_stream_track_active(void) {
    if (!sbp.stream_queue_active) return 0;
    void *queue = *(void **)PLAY_QUEUE;
    int pos = mclGetPlayPos(), id, i;
    void *record;
    if (!queue || pos < 0 || (unsigned)pos >= deque_size(queue)) return 0;
    record = deque_at(queue, (unsigned)pos);
    if (!record) return 0;
    id = *(int *)((char *)record + REC_ID);
    for (i = 0; i < sbp.play_count; ++i)
        if (sbp.play_ids[i] == id) return 1;
    return 0;
}

static int sb_stream_tick(const void *unused) {
    unsigned now = (unsigned)time_now_ms();
    int state = mclGetPlayStatus();
    (void)unused;
    if (!sb_stream_track_active()) {
        if ((int)(now - sbp.stream_grace_until) < 0) {
            if (state == 2) reset_poweroptions_timer(1, 1, 0);
            return RET_REPEAT;
        }
        sbp.stream_timer = 0;
        sbp.stream_queue_active = 0;
        return RET_OK;
    }
    if (state == 2)
        reset_poweroptions_timer(1, 1, 0);
    else if (state == 1 && (int)(now - sbp.stream_grace_until) >= 0) {
        sbp.stream_timer = 0;
        sbp.stream_queue_active = 0;
        return RET_OK;
    }
    return RET_REPEAT;
}

static void sb_stream_stop(void) {
    sbp.stream_queue_active = 0;
    if (sbp.stream_timer) timer_remove(sbp.stream_timer);
    sbp.stream_timer = 0;
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
        rc = keyboard_open(SB_ENGLISH("Navidrome"), SB_ENGLISH("Username"), sbp.user, sb_setup_user_done, 0, KB_LONG);
    else if (sbp.setup_prompt == SB_SETUP_PASSWORD)
        rc = keyboard_open(SB_ENGLISH("Navidrome"), SB_ENGLISH("Server password"), 0, sb_setup_password_done, 0,
                           KB_LONG);
    if (rc == 0) {
        sbp.setup_prompt = sbp.setup_tries = 0;
        return RET_OK;
    }
    if (++sbp.setup_tries < 40) return RET_REPEAT;
    sbp.setup_prompt = sbp.setup_tries = 0;
    pod_toast(SB_ENGLISH("Could not open login field"));
    return RET_OK;
}

static void sb_setup_defer_prompt(int prompt) {
    sbp.setup_prompt = prompt;
    sbp.setup_tries = 0;
    if (!timer_add(sb_setup_next_prompt, (void *)0, 50)) {
        sbp.setup_prompt = 0;
        pod_toast(SB_ENGLISH("Could not open login field"));
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
        pod_toast(SB_ENGLISH("Enter a valid HTTP or HTTPS server URL"));
        return;
    }
    memcpy(sbp.setup_base, text, n + 1);
    while (n > 8 && sbp.setup_base[n - 1] == '/') sbp.setup_base[--n] = 0;
    sb_setup_defer_prompt(SB_SETUP_USER);
}

static void sb_setup_user_done(const char *text) {
    unsigned n = sb_len(text);
    if (!n || n >= sizeof sbp.setup_user || sb_has_char(text, '|')) {
        pod_toast(SB_ENGLISH("Enter a valid username"));
        return;
    }
    memcpy(sbp.setup_user, text, n + 1);
    sb_setup_defer_prompt(SB_SETUP_PASSWORD);
}

static void sb_setup_password_done(const char *text) {
    char config[512];
    int n;
    if (!text[0]) {
        pod_toast(SB_ENGLISH("Enter a server password"));
        return;
    }
    if (sb_has_char(text, '|')) {
        pod_toast(SB_ENGLISH("Password cannot contain |"));
        return;
    }
    n = snprintf(config, sizeof config, "%s|%s|%s", sbp.setup_base, sbp.setup_user, text);
    memset(sbp.setup_base, 0, sizeof sbp.setup_base);
    memset(sbp.setup_user, 0, sizeof sbp.setup_user);
    if (n < 0 || (unsigned)n >= sizeof config) {
        pod_toast(SB_ENGLISH("Server settings are too long"));
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
    keyboard_open(SB_ENGLISH("Navidrome"), SB_ENGLISH("Server URL"), initial, sb_setup_url_done, 0, KB_LONG);
}

static int sb_scroll_event(void *ctx, void *e) {
    unsigned first = sb_first_row();
    (void)ctx;
    (void)e;
    if (sb_input_locked() || sbp.switching_view) return RET_OK;
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
    if (sb_input_locked()) {
        sb_set_status(SB_ENGLISH("A request is still running"));
        return RET_OK;
    }
    n = sb_show_library(0);
    if (n > 0)
        sb_set_status(SB_ENGLISH("Songs"));
    else if (n == 0)
        sb_set_status(SB_ENGLISH("No regular songs in the synced library"));
    else
        sb_set_status("Sync the library after connecting to the server.");
    return RET_OK;
}

static int sb_dsd_click(void *ctx, void *e) {
    int n;
    (void)ctx;
    (void)e;
    if (sb_input_locked()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
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
    if (sb_input_locked()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
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
            sb_set_status(SB_ENGLISH("Could not refresh this song page"));
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
    widget_set_prop_str(sbp.view_button, "style:pressed:icon",
                        sbp.grid_mode ? "pod_nav_list_down" : "pod_nav_grid_down");
    (void)home_write_atomic(SB_VIEW_FILE, SB_VIEW_TMP, sbp.grid_mode ? "1\n" : "0\n");
    sb_resize_rows();
    sbp.row_base = -1;
    widget_set_prop_int(sbp.scroll, "yoffset",
                        sbp.grid_mode ? (int)(first / 2) * SB_GRID_PITCH : (int)first * SB_ROW_H);
    sb_place_rows(first);
    sb_render_rows();
    sbp.switching_view = 0;
    sb_az_rebuild();
    return RET_OK;
}

static int sb_sync_click(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sbp.busy || sbp.done || sb_page_timer_missing()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
        return RET_OK;
    }
    if (!sbp.user[0] || !sbp.password[0]) {
        sb_setup_start();
        return RET_OK;
    }
    if (!pod_confirm(SB_ENGLISH("Sync Navidrome songs and artwork to the SD card now?"))) return RET_OK;
    if (sb_start(3) == 0)
        sb_set_status("Syncing library to SD card…");
    else
        sb_set_status("Library sync could not start");
    return RET_OK;
}

static int sb_play_click(void *ctx, void *e);

static int sb_play_local_file(const sb_song_t *song, const char *path) {
    unsigned rec[REC_SIZE / 4];
    void *q;
    char *fields[5];
    const char *name = strrchr(path, '/');
    unsigned h;
    if (!name)
        name = path;
    else
        ++name;
    fields[0] = strdup(name);
    fields[1] = strdup(path);
    fields[2] = strdup(song->title[0] ? song->title : SB_ENGLISH("Untitled"));
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
    sbp.play_count = 1;
    sbp.play_ids[0] = -(int)((h & 0x3fffffffu) + 2u);
    memcpy(sbp.play_cover[0], song->cover, sizeof sbp.play_cover[0]);
    sb_stream_stop();
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

/* Tapping a row plays it; an undownloaded DSD must be started with its Download control. */
static int sb_select_click(void *ctx, void *e) {
    int at = (int)(long)ctx;
    (void)e;
    if (sb_input_locked()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
        return RET_OK;
    }
    at += sbp.row_data;
    if (at < 0 || at >= sbp.count) return RET_OK;
    sbp.selected = at;
    if (sbp.dsd_view || sb_is_dsd(sbp.songs[at].suffix)) {
        char path[320];
        if (sb_offline_find(&sbp.songs[at], path, sizeof path)) {
            if (sb_play_local_file(&sbp.songs[at], path) == 0) return RET_OK;
            sb_set_status(SB_ENGLISH("Could not play the downloaded DSD file"));
            return RET_OK;
        }
        sb_set_status(SB_ENGLISH("Tap Download to save this DSD track to SD."));
        return RET_OK;
    }
    {
        char path[320];
        if (sb_offline_find(&sbp.songs[at], path, sizeof path)) {
            if (sb_play_local_file(&sbp.songs[at], path) == 0) return RET_OK;
            sb_set_status(SB_ENGLISH("Could not play the downloaded song"));
            return RET_OK;
        }
    }
    return sb_play_click(0, 0);
}

static void sb_search_done(const char *text) {
    unsigned i;
    unsigned n = sb_len(text);
    if (n >= sizeof sbp.query) n = sizeof sbp.query - 1;
    for (i = 0; i < n; ++i) sbp.query[i] = text[i];
    sbp.query[n] = 0;
    if (sbp.busy || sbp.done || sb_page_timer_missing()) {
        sb_set_status(SB_ENGLISH("A request is still running"));
        return;
    }
    sbp.indexed_view = 0;
    sbp.dsd_view = 0;
    sbp.view = SB_VIEW_SEARCH;
    sb_az_clear();
    sbp.row_data = 0;
    sbp.row_base = -1;
    sbp.count = 0;
    sbp.selected = -1;
    widget_set_prop_int(sbp.scroll, "yoffset", 0);
    if (sb_start(1) == 0)
        sb_set_status(SB_ENGLISH("Searching Navidrome…"));
    else
        sb_set_status(SB_ENGLISH("Search could not start"));
}

static void sb_config_done(const char *text) {
    char *a = 0, *b = 0;
    unsigned i, n = sb_len(text);
    if (n >= 500) {
        pod_toast(SB_ENGLISH("Configuration is too long"));
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
        pod_toast(SB_ENGLISH("Enter URL|username|password"));
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
        pod_toast(SB_ENGLISH("Server URL must use HTTP or HTTPS"));
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
                (void)fsync(dir);
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
            sb_set_status(SB_ENGLISH("Could not check Navidrome server."));
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
    if (sbp.busy || sbp.done || sb_page_timer_missing()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
        return RET_OK;
    }
    sb_setup_start();
    return RET_OK;
}
static int sb_search_click(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (sbp.busy || sbp.done || sb_page_timer_missing()) {
        sb_set_status(SB_ENGLISH("Wait for the current request to finish"));
        return RET_OK;
    }
    if (!sbp.user[0] || !sbp.password[0]) {
        sb_setup_start();
        return RET_OK;
    }
    keyboard_open(SB_ENGLISH("Navidrome Search"), SB_ENGLISH("Search songs"), 0, sb_search_done, 0, KB_LONG);
    return RET_OK;
}

static int sb_play_click(void *ctx, void *e) {
    int at = sbp.selected;
    char *fields[5];
    unsigned rec[REC_SIZE / 4];
    int ids[SB_MAX];
    char covers[SB_MAX][SB_ID];
    char **owned_fields;
    sb_song_t *queue_songs;
    void *q;
    int i, n, queued = 0, play_at = 0, collision;
    (void)ctx;
    (void)e;
    if (sb_input_locked()) {
        sb_set_status(SB_ENGLISH("A request is still running"));
        return RET_OK;
    }
    if (at < 0 || at >= sbp.count) {
        pod_toast(SB_ENGLISH("Select a song first"));
        return RET_OK;
    }
    if (sb_is_dsd(sbp.songs[at].suffix)) {
        sb_set_status("DSD streaming is disabled; download the original file for local playback.");
        return RET_OK;
    }
    sbp.selected = at;
    queue_songs = (sb_song_t *)calloc(SB_MAX, sizeof *queue_songs);
    owned_fields = (char **)calloc(SB_MAX * 5, sizeof *owned_fields);
    if (!queue_songs || !owned_fields) {
        free(queue_songs);
        free(owned_fields);
        pod_toast(SB_ENGLISH("Could not prepare stream queue"));
        return RET_OK;
    }
    if (sbp.indexed_view && sbp.view == SB_VIEW_TRACKS) {
        unsigned first = (unsigned)sbp.index_offset + (unsigned)at;
        unsigned left = first < (unsigned)sbp.index_count ? (unsigned)sbp.index_count - first : 0;
        n = (int)(left > SB_MAX ? SB_MAX : left);
        if (n <= 0 || sb_index_read_range(first, (unsigned)n, queue_songs) != n) {
            free(queue_songs);
            free(owned_fields);
            pod_toast(SB_ENGLISH("Could not read the synced song list"));
            return RET_OK;
        }
    } else {
        n = sbp.count - at;
        if (n > SB_MAX) n = SB_MAX;
        for (i = 0; i < n; ++i) sb_song_copy(&queue_songs[i], &sbp.songs[at + i]);
    }
    q = _create_deque("stSongInfo");
    if (!q) {
        free(queue_songs);
        free(owned_fields);
        return RET_OK;
    }
    deque_init(q);
    for (i = 0; i < n; ++i) {
        sb_song_t *song = &queue_songs[i];
        char url[SB_URL], file_name[SB_TEXT + 16];
        unsigned h = 2166136261u, j;
        if (sb_is_dsd(song->suffix)) continue;
        if (sb_url(url, sizeof url, sbp.base, "stream", song->id, sbp.user, sbp.password, 0) ||
            sb_track_filename(file_name, sizeof file_name, song) < 0)
            break;
        for (j = 0; j < 5; ++j) fields[j] = 0;
        fields[0] = strdup(file_name[0] ? file_name : SB_ENGLISH("Untitled"));
        fields[1] = strdup(url);
        fields[2] = strdup(song->title[0] ? song->title : SB_ENGLISH("Untitled"));
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
        memcpy(covers[queued], song->cover, sizeof covers[queued]);
        for (j = 0; j < 5; ++j) owned_fields[queued * 5 + j] = fields[j];
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
        _deque_push_back(q, rec);
        ++queued;
    }
    if (queued <= 0 || (int)deque_size(q) != queued || play_at < 0) {
        deque_destroy(q);
        free(queue_songs);
        for (i = 0; i < queued * 5; ++i) free(owned_fields[i]);
        free(owned_fields);
        pod_toast(SB_ENGLISH("Could not prepare stream queue"));
        return RET_OK;
    }
    sbp.play_count = queued;
    for (i = 0; i < queued; ++i) {
        sbp.play_ids[i] = ids[i];
        memcpy(sbp.play_cover[i], covers[i], sizeof sbp.play_cover[i]);
    }
    free(queue_songs);
    if (sbp.busy && sbp.mode == 4) {
        sbp.art_pause_for_playback = 1;
        sb_atomic_store(&sbp.art_pause_request, 1);
    }
    mclLoadPlayList(q, play_at, 0);
    deque_destroy(q);
    for (i = 0; i < queued * 5; ++i) free(owned_fields[i]);
    free(owned_fields);
    mclSetStartSeekTime(0);
    start_playqueue(play_at);
    if (sbp.stream_timer) timer_remove(sbp.stream_timer);
    sbp.stream_queue_active = 1;
    sbp.stream_grace_until = (unsigned)time_now_ms() + SB_STREAM_GRACE_MS;
    sbp.stream_timer = timer_add(sb_stream_tick, (void *)0, SB_STREAM_POLL_MS);
    if (!sbp.stream_timer) {
        sbp.stream_queue_active = 0;
        reset_poweroptions_timer(1, 1, 0);
    }
    on_backtoplayer_onclick((void *)0, (void *)0);
    return RET_OK;
}
static int sb_delete_offline(int at) {
    char path[320];
    int is_dsd;
    if (at < 0 || at >= sbp.count || !sb_offline_find(&sbp.songs[at], path, sizeof path)) return -1;
    is_dsd = sb_is_dsd(sbp.songs[at].suffix);
    if (!pod_confirm(SB_ENGLISH(is_dsd ? "Delete this downloaded DSD track from the SD card?"
                                       : "Delete this downloaded song from the SD card?")))
        return 0;
    if (!pod_card_mounted() || unlink(path)) {
        sb_set_status(
            SB_ENGLISH(is_dsd ? "Could not delete the downloaded DSD file" : "Could not delete the downloaded song"));
        return -1;
    }
    sb_render_rows();
    sb_set_status(SB_ENGLISH(is_dsd ? "Downloaded DSD track deleted" : "Downloaded song deleted"));
    return 1;
}

static int sb_row_download_click(void *ctx, void *e) {
    int at = (int)(long)ctx + sbp.row_data;
    char path[320];
    (void)e;
    if (sb_page_timer_missing()) {
        sb_set_status(SB_ENGLISH("Navidrome page timer unavailable. Close and reopen the page."));
        return RET_OK;
    }
    if (at < 0 || at >= sbp.count) {
        pod_toast(SB_ENGLISH("Select a song first"));
        return RET_OK;
    }
    if ((sbp.busy || sbp.done) && sbp.mode == 4) {
        sbp.selected = at;
        if (sb_offline_find(&sbp.songs[at], path, sizeof path))
            (void)sb_delete_offline(at);
        else {
            if (sbp.pending_download_at) {
                sb_set_status(SB_ENGLISH("A download is already queued"));
                return RET_OK;
            }
            sb_song_copy(&sbp.download_song, &sbp.songs[at]);
            sbp.download_song_valid = 1;
            sbp.pending_download_at = 1;
            sb_atomic_store(&sbp.art_pause_request, 1);
            sb_set_status(SB_ENGLISH("Download queued; pausing artwork cache"));
        }
        return RET_OK;
    }
    if (sb_download_blocked(at)) return RET_OK;
    sbp.selected = at;
    if (sb_offline_find(&sbp.songs[at], path, sizeof path)) {
        (void)sb_delete_offline(at);
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
    if (sbp.connection_lost && sbp.connected) sb_set_connected(0);
    if (sbp.busy && sbp.mode == 3 && sbp.sync_count != sbp.sync_shown) {
        char msg[64];
        sbp.sync_shown = sbp.sync_count;
        snprintf(msg, sizeof msg, SB_ENGLISH("%d tracks synced…"), sbp.sync_shown);
        sb_set_status(msg);
    }
    if (sbp.busy && sbp.mode == 2 && sbp.library_refreshing && !sbp.library_refresh_shown) {
        sbp.library_refresh_shown = 1;
        sb_set_status(SB_ENGLISH("Adding downloaded DSD to the SD library…"));
    }
    if (sbp.busy && sbp.mode == 4 && sbp.art_syncing && sbp.art_count != sbp.art_shown) {
        char msg[64];
        sbp.art_shown = sbp.art_count;
        snprintf(msg, sizeof msg, "Artwork scan %d/%d…", sbp.art_count, sbp.art_total);
        sb_set_status(msg);
    }
    if (sbp.busy && sbp.mode == 2 && sb_atomic_load(&sbp.download_active)) sb_download_progress_update();
    if (sbp.done && !sbp.busy) {
        __sync_synchronize();
        sbp.done = 0;
        if (sbp.mode == 2) {
            sb_atomic_store(&sbp.download_active, 0);
            sb_download_progress_hide();
            sbp.download_song_valid = 0;
        }
        if (sbp.connection_lost) sb_set_connected(0);
        if (sbp.mode == 8) {
            if (sbp.result > 0) {
                sb_set_connected(1);
                sb_set_status("Connected to Navidrome");
                if (!sbp.index_valid) {
                    if (sb_start(3) == 0) sb_set_status("Connected · syncing songs to SD…");
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
            if (sbp.result < 0 && (sb_atomic_load(&sbp.http_status) == 401 || sb_atomic_load(&sbp.http_status) == 403))
                sb_set_status(SB_ENGLISH("Server rejected login or access"));
            else if (sbp.result < 0)
                sb_set_status("Search failed. Check Wi-Fi, server, and credentials.");
            else if (!sbp.count)
                sb_set_status("No songs found");
            else {
                char msg[64];
                snprintf(msg, sizeof msg, "%d results. Use a row's play or download icon.", sbp.count);
                sb_set_status(msg);
            }
        } else if (sbp.mode == 3) {
            int loaded = sbp.result >= 0 ? sb_index_load(0, 0) : -1;
            if (sbp.result >= 0 && loaded >= 0) {
                sbp.row_data = 0;
                sbp.dsd_view = 0;
                widget_set_prop_int(sbp.scroll, "yoffset", 0);
                sb_resize_rows();
                sb_place_rows(0);
                sb_render_rows();
                if (!sbp.index_count && !sbp.dsd_count)
                    sb_set_status("Navidrome library is empty.");
                else {
                    sb_set_status("Songs synced. Artwork will cache in the background.");
                    if (mclGetPlayStatus() == 2 || mclGetPlayStatus() == 3) {
                        sbp.art_pause_for_playback = 1;
                        sb_set_status("Songs synced. Artwork caching waits until playback stops.");
                    } else if (sb_start(4) == 0)
                        sb_set_status("Songs ready · caching artwork to SD…");
                    else
                        sb_set_status("Songs synced. Wi-Fi is needed to cache artwork.");
                }
            } else if (sbp.sync_limit_hit)
                sb_set_status(SB_ENGLISH("Over 100k tracks; old index kept"));
            else if (loaded < 0 && sbp.result >= 0)
                sb_set_status(SB_ENGLISH("Synced index could not be read from SD card."));
            else if (sbp.sync_error == SB_SYNC_ERR_CARD)
                sb_set_status(SB_ENGLISH("SD card is unavailable. Insert it and retry."));
            else if (sbp.sync_error == SB_SYNC_ERR_SPACE)
                sb_set_status(SB_ENGLISH("SD card space too low for the library index."));
            else if (sbp.sync_error == SB_SYNC_ERR_STORAGE)
                sb_set_status(SB_ENGLISH("SD card write failed. Check card and free space."));
            else if (sbp.sync_error == SB_SYNC_ERR_NETWORK) {
                sb_set_connected(0);
                sb_set_status(SB_ENGLISH("Wi-Fi or server connection failed during sync."));
            } else if (sbp.sync_error == SB_SYNC_ERR_REQUEST)
                sb_set_status(SB_ENGLISH("Could not prepare the library sync request."));
            else if (sbp.sync_error == SB_SYNC_ERR_AUTH)
                sb_set_status(SB_ENGLISH("Server rejected the library sync request."));
            else if (sbp.sync_error == SB_SYNC_ERR_SERVER)
                sb_set_status(SB_ENGLISH("Server returned an HTTP error during sync."));
            else if (sbp.sync_error == SB_SYNC_ERR_RESPONSE)
                sb_set_status(SB_ENGLISH("Server returned unreadable library data."));
            else if (sbp.sync_error == SB_SYNC_ERR_EMPTY)
                sb_set_status(SB_ENGLISH("Server returned an empty library response."));
            else if (sbp.sync_error == SB_SYNC_ERR_MEMORY)
                sb_set_status(SB_ENGLISH("Not enough memory to sync the library."));
            else
                sb_set_status(SB_ENGLISH("Library sync failed. Check server and SD card."));
        } else if (sbp.mode == 4) {
            sbp.art_syncing = 0;
            sb_render_rows();
            if (sbp.result == 1)
                sb_set_status("Artwork cache finished.");
            else if (sbp.result == 0) {
                char msg[80];
                snprintf(msg, sizeof msg, SB_ENGLISH("Artwork: %d saved, %d failed"), sbp.art_cached, sbp.art_failed);
                sb_set_status(msg);
            } else if (sbp.result == 2 && sbp.art_pause_for_playback)
                sb_set_status(SB_ENGLISH("Artwork cache paused during playback; it will resume after playback stops."));
            else if (sbp.result == 2)
                sb_set_status(SB_ENGLISH("Artwork cache paused for download."));
            else
                sb_set_status(sbp.connection_lost ? "Artwork caching paused; check server connection."
                                                  : "Artwork scan stopped; check SD card and server.");
            if (sbp.pending_download_at > 0) {
                sbp.pending_download_at = 0;
                if (sb_start(2) == 0)
                    sb_set_status(SB_ENGLISH("Downloading original file to SD card…"));
                else {
                    sbp.download_song_valid = 0;
                    if (get_wifisignal() > 0) sb_set_status(SB_ENGLISH("Download could not start"));
                }
            }
        } else {
            if (sbp.mode == 2) {
                if (sbp.refresh_index_after_download) {
                    sbp.refresh_index_after_download = 0;
                    if (sb_index_load(0, sbp.dsd_view) >= 0) {
                        sbp.row_data = 0;
                        widget_set_prop_int(sbp.scroll, "yoffset", 0);
                        sb_resize_rows();
                    }
                }
                sb_place_rows(0);
                sb_render_rows();
            }
            if (sbp.result > 0 && sbp.download_is_dsd) {
                if (sbp.library_refresh_result > 0)
                    sb_set_status(SB_ENGLISH("DSD downloaded and added to the SD library."));
                else
                    sb_set_status(SB_ENGLISH("DSD downloaded, but the SD library refresh failed."));
            } else if (sbp.result > 0)
                sb_set_status(SB_ENGLISH("Original song downloaded to /mnt/mmc/Navidrome"));
            else
                sb_download_failure_status();
        }
        if (sbp.ping_after_work && !sbp.busy && sbp.mode != 8) {
            sbp.ping_after_work = 0;
            if (sb_start(8) == 0) sb_set_status("Checking Navidrome server…");
        }
    }
    if (sbp.art_pause_for_playback && sbp.win && sbp.connected && !sbp.busy && !sbp.done && mclGetPlayStatus() == 1) {
        if (sb_start(4) == 0) {
            sbp.art_pause_for_playback = 0;
            sb_set_status(SB_ENGLISH("Playback stopped. Resuming artwork cache…"));
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
    sbp.ping_after_work = 0;
    sbp.refresh_index_after_download = 0;
    sbp.win = win;
    if (!sbp.count && !sbp.user[0]) sbp.selected = -1;
    sbp.status = widget_lookup(win, "sb_status", 1);
    sbp.download_bar = widget_lookup(win, "sb_download_progress", 1);
    sbp.download_fill = widget_lookup(win, "sb_download_fill", 1);
    if (sb_atomic_load(&sbp.download_active)) {
        sbp.download_status_kind = -1;
        sbp.download_status_value = -1;
    }
    sb_download_progress_hide();
    sbp.scroll = widget_lookup(win, "sb_scrollview", 1);
    sbp.rows = widget_lookup(win, "sb_rows", 1);
    sbp.az.win = win, sbp.az.sv = sbp.scroll;
    sbp.az.st_hdr = widget_lookup(win, "label_hdr", 1);
    sbp.az.st_rail = widget_lookup(win, "label_rail", 1);
    sbp.az.st_rail_on = widget_lookup(win, "label_rail_on", 1);
    sbp.az.rail = widget_lookup(win, "sg_rail", 1);
    sbp.az.bubble = widget_lookup(win, "sg_bubble", 1);
    sbp.az.bubble_letter = widget_lookup(win, "sg_bubble_letter", 1);
    az_make_disc(&sbp.az);
    sbp.connect = widget_lookup(win, "sb_connect", 1);
    sbp.connect_label = widget_lookup(win, "sb_connect_label", 1);
    sbp.connected_dot = widget_lookup(win, "sb_connected_dot", 1);
    sb_set_connected(0);
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
    widget_set_prop_str(sbp.view_button, "style:pressed:icon",
                        sbp.grid_mode ? "pod_nav_list_down" : "pod_nav_grid_down");
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
        snprintf(name, sizeof name, "sb_row_download%d", i);
        sbp.row_download[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_download_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_row_download_icon%d", i);
        sbp.row_download_icon[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "sb_grid_download%d", i);
        sbp.grid_download[i] = widget_lookup(win, name, 1);
        pod_bind(win, name, sb_row_download_click, (void *)(long)i);
        snprintf(name, sizeof name, "sb_grid_download_icon%d", i);
        sbp.grid_download_icon[i] = widget_lookup(win, name, 1);
    }
    widget_on(sbp.scroll, EVT_SCROLL, sb_scroll_event, 0);
    if (sbp.az.rail) {
        widget_on(sbp.az.rail, EVT_POINTER_DOWN, sb_on_az_rail, 0);
        widget_on(sbp.az.rail, EVT_POINTER_MOVE, sb_on_az_rail, 0);
        widget_on(sbp.az.rail, EVT_POINTER_UP, sb_on_az_rail, 0);
        widget_on(sbp.az.rail, EVT_POINTER_ABORT, sb_on_az_rail, 0);
        widget_on(sbp.az.rail, EVT_AFTER_PAINT, sb_on_az_paint, 0);
    }
    if (!sbp.busy || (sbp.mode != 1 && sbp.mode != 2 && sbp.mode != 3))
        (void)sb_show_library(0);
    else {
        sbp.row_data = 0;
        sbp.row_base = -1;
        if (sbp.mode == 2 && sbp.indexed_view) sbp.refresh_index_after_download = 1;
        sb_resize_rows();
        sb_place_rows(0);
        for (i = 0; i < SB_VISIBLE; ++i) {
            widget_set_sensitive(sbp.row[i], 0);
            widget_set_sensitive(sbp.grid_row[i], 0);
            widget_set_sensitive(sbp.row_download[i], 0);
            widget_set_sensitive(sbp.grid_download[i], 0);
        }
    }
    sbp.timer = timer_add(sb_tick, 0, 100);
    widget_on(win, EVT_DESTROY, sb_destroy_event, 0);
    if (!sbp.timer) {
        sb_set_status(SB_ENGLISH("Navidrome page timer unavailable. Close and reopen the page."));
        return;
    }
    if (sbp.user[0] && (sbp.busy || sbp.done)) {
        if (sbp.mode != 8) sbp.ping_after_work = 1;
        if (sbp.mode == 3)
            sb_set_status("Library sync continuing in background…");
        else if (sbp.mode == 4)
            sb_set_status("Songs ready · artwork caching in background…");
        else if (sbp.mode == 2 && sb_atomic_load(&sbp.download_active))
            sb_download_progress_update();
        else if (sbp.mode == 2 && sbp.library_refreshing)
            sb_set_status(SB_ENGLISH("Adding downloaded DSD to the SD library…"));
        else
            sb_set_status("Navidrome request still running…");
    } else if (sbp.user[0]) {
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
    az_rail_end(&sbp.az);
    az_free(&sbp.az);
    free(sbp.az_rank);
    sbp.az_rank = (unsigned char *)0;
    memset(&sbp.az, 0, sizeof sbp.az);
    sbp.win = 0;
    sbp.status = 0;
    sbp.download_bar = 0;
    sbp.download_fill = 0;
    sbp.scroll = 0;
    sbp.rows = 0;
    sbp.timer = 0;
    sbp.connect = 0;
    sbp.connect_label = 0;
    sbp.connected_dot = 0;
    sbp.view_button = 0;
    sbp.view_icon = 0;
    sbp.ping_after_work = 0;
    sbp.refresh_index_after_download = 0;
    memset(sbp.tab_label, 0, sizeof sbp.tab_label);
    memset(sbp.tab_mark, 0, sizeof sbp.tab_mark);
    memset(sbp.row, 0, sizeof sbp.row);
    memset(sbp.art, 0, sizeof sbp.art);
    memset(sbp.grid_row, 0, sizeof sbp.grid_row);
    memset(sbp.grid_title, 0, sizeof sbp.grid_title);
    memset(sbp.grid_sub, 0, sizeof sbp.grid_sub);
    memset(sbp.grid_art, 0, sizeof sbp.grid_art);
    memset(sbp.row_download, 0, sizeof sbp.row_download);
    memset(sbp.row_download_icon, 0, sizeof sbp.row_download_icon);
    memset(sbp.grid_download, 0, sizeof sbp.grid_download);
    memset(sbp.grid_download_icon, 0, sizeof sbp.grid_download_icon);
    memset(sbp.title, 0, sizeof sbp.title);
    memset(sbp.sub, 0, sizeof sbp.sub);
}
