/* Subsonic network layer: token auth, URL building, libcurl GET and download, JSON walker (see sbnet.h). */
#include <limits.h>
#include "offsets.inc"
#include "stock.h"
#include "sbnet.h"
#include "sbapi.h" /* SBA_RESERVE_KB */
#include "utf8.h"
#include "common.h"
#include "curlopts.h"
#include "net.h"

#define SBN_TEXT 192 /* longest password the token input holds */

/* Writable state lives in .scratch (the payload has no .bss). */
static struct {
    sbn_xfer_fn xfer;
    sbn_after_fn after;
    int ready;
} sbn_st __attribute__((section(".scratch")));

unsigned sbn_len(const char *s) {
    unsigned n = 0;
    if (s)
        while (s[n]) ++n;
    return n;
}

int sbn_eq(const char *a, unsigned n, const char *b) {
    unsigned i = 0;
    while (b[i] && i < n && a[i] == b[i]) ++i;
    return i == n && !b[i];
}

int sbn_ascii_lower(unsigned c) { return c >= 'A' && c <= 'Z' ? (int)(c + ('a' - 'A')) : (int)c; }

int sbn_prefix(const char *value, const char *prefix) {
    unsigned i = 0;
    if (!value) return 0;
    while (prefix[i] && value[i] == prefix[i]) ++i;
    return !prefix[i];
}

int sbn_https(const char *url) { return sbn_prefix(url, "https://"); }

int sbn_http_url(const char *url) { return sbn_prefix(url, "http://") || sbn_https(url); }

static int sbn_put(char *out, unsigned cap, unsigned *used, unsigned c) {
    if (*used + m1_utf8_len(c) >= cap) return 0;
    *used += m1_utf8_put(out + *used, c);
    return 1;
}

const char *sbn_ws(const char *p, const char *end) {
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
    return p;
}

/* Decode one JSON string, bounded to its containing response. */
const char *sbn_string(const char *p, const char *end, char *out, unsigned cap) {
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
                if (end - p < 4 || (a = m1_hexval(p[0])) < 0 || (b = m1_hexval(p[1])) < 0 ||
                    (d = m1_hexval(p[2])) < 0 || (e = m1_hexval(p[3])) < 0)
                    return 0;
                c = (unsigned)((a << 12) | (b << 8) | (d << 4) | e);
                p += 4;
                if (c >= 0xd800 && c <= 0xdbff && end - p >= 6 && p[0] == '\\' && p[1] == 'u') {
                    int x = m1_hexval(p[2]), y = m1_hexval(p[3]), z = m1_hexval(p[4]), w = m1_hexval(p[5]);
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
        } else if (c && !sbn_put(out, cap, &used, c))
            return 0;
    }
    if (p >= end) return 0;
    out[used] = 0;
    return p + 1;
}

const char *sbn_skip(const char *p, const char *end) {
    unsigned depth = 0;
    int quote = 0, esc = 0;
    char open[64]; /* the opener of each level; a deeper nesting is refused */
    const char *start;
    p = sbn_ws(p, end);
    start = p;
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
        return p == start ? 0 : p; /* no progress: a malformed value */
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
        else if (c == '{' || c == '[') {
            if (depth >= sizeof open) return 0;
            open[depth++] = c;
        } else if (c == '}' || c == ']') {
            if (!depth || open[depth - 1] != (c == '}' ? '{' : '[')) return 0;
            if (--depth == 0) return p + 1;
        }
    }
    return 0;
}

/* Find an object-valued member and return its value's opening brace. */
const char *sbn_object(const char *obj, const char *end, const char *key) {
    const char *p = sbn_ws(obj, end);
    if (p >= end || *p != '{') return 0;
    ++p;
    while ((p = sbn_ws(p, end)) < end && *p != '}') {
        char name[48];
        const char *q = sbn_string(p, end, name, sizeof name);
        if (!q) return 0;
        p = sbn_ws(q, end);
        if (p >= end || *p++ != ':') return 0;
        p = sbn_ws(p, end);
        if (sbn_eq(name, sbn_len(name), key)) return p < end && *p == '{' ? p : 0;
        p = sbn_skip(p, end);
        if (!p) return 0;
        p = sbn_ws(p, end);
        if (p < end && *p == ',')
            ++p;
        else if (p < end && *p != '}')
            return 0;
    }
    return 0;
}

static void sbn_trim_utf8(char *out, unsigned cap) {
    unsigned n, start, lead, need;
    unsigned c;
    if (!out || !cap) return;
    n = sbn_len(out);
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

static int sbn_member_mode(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num,
                           int truncate_text) {
    const char *p = sbn_ws(obj, end);
    if (p >= end || *p != '{') return 0;
    ++p;
    while ((p = sbn_ws(p, end)) < end && *p != '}') {
        char name[48];
        const char *q = sbn_string(p, end, name, sizeof name);
        if (!q) return 0;
        p = sbn_ws(q, end);
        if (p >= end || *p++ != ':') return 0;
        p = sbn_ws(p, end);
        if (sbn_eq(name, sbn_len(name), key)) {
            if (*p == '"') {
                q = sbn_string(p, end, out, cap);
                if (!q) {
                    if (!truncate_text || !out || !cap || !sbn_string(p, end, (char *)0, 0)) return -1;
                    sbn_trim_utf8(out, cap);
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
        p = sbn_skip(p, end);
        if (!p) return 0;
        p = sbn_ws(p, end);
        if (p < end && *p == ',')
            ++p;
        else if (p < end && *p != '}')
            return 0;
    }
    return 0;
}

int sbn_member(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num) {
    return sbn_member_mode(obj, end, key, out, cap, num, 0);
}

int sbn_member_truncate(const char *obj, const char *end, const char *key, char *out, unsigned cap) {
    return sbn_member_mode(obj, end, key, out, cap, (unsigned *)0, 1);
}

/* Locate a songs array structurally so text inside a title cannot look like a JSON key. */
int sbn_array_member(const char *obj, const char *end, const char *key, const char **array) {
    const char *p = sbn_ws(obj, end);
    int found = 0;
    *array = 0;
    if (p >= end || *p != '{') return -1;
    ++p;
    for (;;) {
        char name[48];
        const char *q, *value;
        p = sbn_ws(p, end);
        if (p >= end) return -1;
        if (*p == '}') return found;
        q = sbn_string(p, end, name, sizeof name);
        if (!q) return -1;
        p = sbn_ws(q, end);
        if (p >= end || *p++ != ':') return -1;
        value = sbn_ws(p, end);
        if (sbn_eq(name, sbn_len(name), key)) {
            if (value >= end || *value != '[' || found) return -1;
            *array = value + 1;
            found = 1;
        }
        p = sbn_skip(value, end);
        if (!p) return -1;
        p = sbn_ws(p, end);
        if (p >= end) return -1;
        if (*p == ',') {
            p = sbn_ws(p + 1, end);
            if (p >= end || *p == '}') return -1;
        } else if (*p != '}')
            return -1;
    }
}

int sbn_response_ok(const char *json, unsigned n) {
    char status[16];
    const char *end, *root, *after, *p;
    if (!json || !n) return 0;
    end = json + n;
    root = sbn_ws(json, end);
    if (root >= end || *root != '{') return 0;
    after = sbn_skip(root, end);
    if (!after || sbn_ws(after, end) != end) return 0;
    p = sbn_object(root, end, "subsonic-response");
    if (!p || !sbn_skip(p, end)) return 0;
    if (sbn_member(p, end, "status", status, sizeof status, (unsigned *)0) <= 0) return 0;
    return sbn_eq(status, sbn_len(status), "ok");
}

/* Subsonic's token authentication is MD5(password + random salt). The salt is
 * generated per request so the password never appears in the URL passed to the
 * stock player. The salted token itself has no expiry: anyone who sees a URL can
 * replay it until the password changes. */
static unsigned sbn_rotl(unsigned x, unsigned n) { return (x << n) | (x >> (32 - n)); }
void sbn_md5(const unsigned char *msg, unsigned n, unsigned char out[16]) {
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
            bb = bb + sbn_rotl(a + f + k[j] + m[g], s[j]);
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

/* 1 when auth is a saved login secret: SBN_AUTH hex digits, the salt (16) then the token (32). */
int sbn_auth_ok(const char *auth) {
    unsigned i;
    if (!auth) return 0;
    for (i = 0; i < SBN_AUTH; ++i)
        if (!((auth[i] >= '0' && auth[i] <= '9') || (auth[i] >= 'a' && auth[i] <= 'f'))) return 0;
    return auth[SBN_AUTH] == 0;
}

/* The login secret of a password, made once at Sign In: a random salt (16 hex digits) and the token md5(password + salt) (32) in out (SBN_AUTH + 1 bytes). The password itself is not kept
 * anywhere after this. 0, or -1 (a password too long, no random bytes). */
int sbn_auth_make(char *out, const char *password) {
    static const char hex[] = "0123456789abcdef";
    unsigned char raw[8], digest[16], input[SBN_TEXT + 16];
    unsigned i, n = sbn_len(password);
    int fd;
    if (!out || !n || n >= SBN_TEXT || n > sizeof input - 16) return -1;
    fd = open("/dev/urandom", O_RDONLY, 0);
    if (fd < 0) return -1;
    if (read(fd, raw, sizeof raw) != (int)sizeof raw) {
        close(fd);
        return -1;
    }
    close(fd);
    for (i = 0; i < 8; ++i) out[2 * i] = hex[raw[i] >> 4], out[2 * i + 1] = hex[raw[i] & 15];
    memcpy(input, password, n);
    memcpy(input + n, out, 16);
    sbn_md5(input, n + 16, digest);
    for (i = 0; i < 16; ++i) out[16 + 2 * i] = hex[digest[i] >> 4], out[16 + 2 * i + 1] = hex[digest[i] & 15];
    out[SBN_AUTH] = 0;
    memset(input, 0, sizeof input);
    memset(digest, 0, sizeof digest);
    return 0;
}

int sbn_url(char *out, unsigned cap, sbn_server_t srv, const char *method, const char *id, const char *extra) {
    const char *base = srv.base, *user = srv.user, *auth = srv.auth;
    unsigned n = 0, i;
    char salt[17];
    int k;
    if (!out || !cap || !base || !method || !user || !sbn_auth_ok(auth) || !sbn_http_url(base)) return -1;
    k = snprintf(out, cap, "%s/rest/%s.view?u=", base, method);
    if (k < 0 || (unsigned)k >= cap) return -1;
    n = m1_urlenc(out, cap, (unsigned)k, user);
    if (!n) return -1;
    memcpy(salt, auth, 16);
    salt[16] = 0;
    k = snprintf(out + n, cap - n, "&t=%s&s=%s&v=1.16.1&c=m1plus-music&f=json", auth + 16, salt);
    if (k < 0 || (unsigned)k >= cap - n) return -1;
    n += (unsigned)k;
    if (id) {
        k = snprintf(out + n, cap - n, "&id=");
        if (k < 0 || (unsigned)k >= cap - n) return -1;
        n = m1_urlenc(out, cap, n + (unsigned)k, id);
        if (!n) return -1;
    }
    if (sbn_eq(method, sbn_len(method), "stream")) {
        k = snprintf(out + n, cap - n, "&format=raw");
        if (k < 0 || (unsigned)k >= cap - n) return -1;
        n += (unsigned)k;
    }
    if (extra) {
        unsigned x = sbn_len(extra);
        if (n + x >= cap) return -1;
        for (i = 0; i < x; ++i) out[n++] = extra[i];
    }
    out[n] =
        0; /* m1_urlenc leaves no terminator: this is the one place that ends the string (n < cap on every path here) */
    return 0;
}

int sbn_get(sbn_server_t srv, const char *view, const char *id, const char *extra, sbn_sink_t *sink) {
    char url[1024];
    sbn_sink_reset(sink);
    if (sbn_url(url, sizeof url, srv, view, id, extra)) return SBN_E_URL;
    return sbn_http(url, sink, 180L, (const char *)0);
}

void sbn_sink_reset(sbn_sink_t *sink) {
    char *data = sink->data;
    unsigned cap = sink->cap;
    memset(sink, 0, sizeof *sink);
    sink->data = data, sink->cap = data ? cap : 0;
    sink->file.fd = -1;
}

void sbn_sink_free(sbn_sink_t *sink) {
    free(sink->data);
    sink->data = (char *)0, sink->cap = sink->used = 0;
}

void sbn_sink_trim(sbn_sink_t *sink, unsigned keep) {
    if (sink->cap > keep) sbn_sink_free(sink);
}

/* Make room for need bytes (the body and its NUL): double up to SBN_RESPONSE_MAX. 0 when the cap is passed or there is no memory; the buffer is then freed, so the transfer ends with nothing held. */
static int sbn_room(sbn_sink_t *s, unsigned need) {
    unsigned cap = s->cap ? s->cap : SBN_RESPONSE_START;
    char *p;
    if (s->data && need <= s->cap) return 1;
    if (need <= SBN_RESPONSE_MAX)
        while (cap < need) cap *= 2;
    if (need > SBN_RESPONSE_MAX || !(p = (char *)calloc(1, cap))) {
        sbn_sink_free(s);
        return 0;
    }
    if (s->data) memcpy(p, s->data, s->used);
    free(s->data);
    s->data = p, s->cap = cap;
    return 1;
}

int sbn_init(sbn_xfer_fn xfer, sbn_after_fn after) {
    sbn_st.xfer = xfer;
    sbn_st.after = after;
    if (sbn_st.ready) return 1;
    if (!net_init()) return 0;
    sbn_st.ready = 1;
    return 1;
}

static int sbn_resume_save(const sbn_sink_t *sink, const char *path);

static unsigned sbn_write(char *ptr, unsigned size, unsigned nmemb, void *ctx) {
    sbn_sink_t *s = (sbn_sink_t *)ctx;
    unsigned n = size * nmemb;
    if (!s || (size && n / size != nmemb)) return 0;
    if (s->file.fd >= 0) {
        if (s->audio) {
            if (s->head.status >= 300 && s->head.status < 400)
                return n; /* a redirect's body never belongs in the audio file */
            if (!s->headers_ok) { /* not the audio we asked for (or a resume the server did not honour): nothing is appended */
                s->file.why = SBN_W_RESPONSE;
                return 0;
            }
            if (!s->body_started) {
                s->body_started = 1;
                if (s->head.etag[0] && s->validator_path && s->identity)
                    s->resume_saved = sbn_resume_save(s, s->validator_path);
            }
        }
        if (s->prefix_used < sizeof s->prefix) {
            unsigned take = (unsigned)sizeof s->prefix - s->prefix_used;
            if (take > n) take = n;
            memcpy(s->prefix + s->prefix_used, ptr, take);
            s->prefix_used += take;
        }
        return net_file_write(&s->file, ptr, n); /* (the reserve is asked again after every MiB) */
    }
    if (n >= SBN_RESPONSE_MAX - s->used || !sbn_room(s, s->used + n + 1)) return 0;
    memcpy(s->data + s->used, ptr, n);
    s->used += n;
    s->data[s->used] = 0;
    return n;
}

/* Are the headers of this response the ones a download wants? A fresh file: 200. A resumed one: a 206 for exactly the bytes after the saved ones, ending at the file's end, with the strong ETag
 * the .part file was saved under. Never a text or JSON type (a login page, a Subsonic error). */
static int sbn_download_headers_valid(const sbn_sink_t *sink) {
    if (net_text_type(sink->content_type)) return 0;
    if (!sink->resume_offset) return sink->head.status == 200;
    return net_head_resumes(&sink->head, sink->resume_offset) && net_strong_etag(sink->resume_etag) &&
           !strcmp(sink->head.etag, sink->resume_etag);
}

/* libcurl's header callback: the shared reader keeps the status, the strong ETag, the type and the Content-Range (patch/netfile.c net_head_line); an audio transfer is judged at the end of each
 * response's headers. */
static unsigned sbn_header(char *ptr, unsigned size, unsigned nmemb, void *ctx) {
    sbn_sink_t *sink = (sbn_sink_t *)ctx;
    unsigned n = size * nmemb;
    int end;
    if (!sink || (size && n / size != nmemb)) return 0;
    end = net_head_line(&sink->head, ptr, n);
    memcpy(sink->content_type, sink->head.type, sizeof sink->content_type);
    if (end == 2) sink->headers_ok = 0; /* (a status line: another response begins) */
    if (end == 1 && sink->audio) sink->headers_ok = sbn_download_headers_valid(sink);
    return n;
}
int sbn_http(const char *url, sbn_sink_t *sink, long timeout, const char *range) {
    net_req_t r;
    int rc;
    void *if_range_list[2];
    char if_range[144];
    if (!sink) return SBN_E_INIT;
    if (sink->file.fd < 0 && !sink->data && !sbn_room(sink, 1))
        return SBN_E_INIT; /* (an answer with no body still leaves data a string) */
    memset(&r, 0, sizeof r);
    r.url = url, r.write = sbn_write, r.wdata = sink, r.header = sbn_header, r.hdata = sink;
    r.xfer = sbn_st.xfer, r.xdata = sink;
    r.type = sink->content_type, r.type_size = sizeof sink->content_type;
    r.flags = NET_FAIL | NET_NODOWNGRADE | NET_NOENCODING;
    r.redirs = 5, r.connect_s = 12, r.total_s = (int)timeout;
    r.low_limit = 512, r.low_time = timeout > 0 && timeout < 45L ? (int)(timeout / 2L) : 45;
    if (range && *range) r.range = range;
    /* the Range only holds if the file is still the one the .part file came from */
    if (sink->audio && sink->resume_offset && net_if_range(if_range, sizeof if_range, if_range_list, sink->resume_etag))
        r.headers = if_range_list;
    rc = net_perform(&r);
    sink->curl_result = rc;
    sink->http_status = r.http;
    if (rc == NET_NOHANDLE) return SBN_E_INIT;
    sink->content_length = r.length;
    if (sbn_st.after) sbn_st.after(sink);
    return rc == 0 ? 0 : -1;
}

static int sbn_audio_response_valid(const sbn_sink_t *sink, long expected_status, long long expected_range_start) {
    unsigned i = 0;
    if (!sink || sink->http_status != expected_status || sink->file.written <= 0 || sink->prefix_used < 3 ||
        (sink->content_length >= 0 && sink->file.written != sink->content_length) || net_text_type(sink->content_type))
        return 0;
    if (expected_status == 206 && (!sink->head.range_seen || sink->head.range_start != expected_range_start ||
                                   sink->head.range_end < sink->head.range_start || sink->head.range_total == -2 ||
                                   sink->head.range_end - sink->head.range_start == LLONG_MAX ||
                                   sink->file.written != sink->head.range_end - sink->head.range_start + 1))
        return 0;
    while (i < sink->prefix_used &&
           (sink->prefix[i] == ' ' || sink->prefix[i] == '\t' || sink->prefix[i] == '\r' || sink->prefix[i] == '\n'))
        ++i;
    if (i < sink->prefix_used && (sink->prefix[i] == '<' || sink->prefix[i] == '{' || sink->prefix[i] == '[')) return 0;
    return 1;
}

static void sbn_sink_prepare_file(sbn_sink_t *sink, int fd) {
    sink->audio = sink->headers_ok = sink->body_started = sink->resume_saved = 0;
    memset(&sink->file, 0, sizeof sink->file);
    memset(&sink->head, 0, sizeof sink->head);
    sink->file.room = fd >= 0 ? "/mnt/mmc" : (const char *)0;
    sink->resume_etag[0] = 0;
    sink->validator_path = sink->identity = (const char *)0;
    sink->used = 0;
    sink->prefix_used = 0;
    sink->file.fd = fd;
    sink->curl_result = 0;
    sink->http_status = 0;
    sink->content_length = -1;
    sink->head.range_start = sink->head.range_end = sink->head.range_total = -1;
    sink->content_type[0] = 0;
}

/* The resume record next to a .part file (<part>.etag): the strong ETag of the file the .part bytes came from, and who asked (server, user, track). A resume is only attempted when a record
 * for the same identity names a strong ETag; the Range then carries If-Range with it, and a 206 is accepted only with that same ETag. */
typedef struct {
    char magic[8], identity[SBN_IDENTITY], etag[128];
} sbn_resume_t;

static int sbn_bytes_equal(const char *a, const char *b, unsigned n) {
    unsigned i;
    for (i = 0; i < n; ++i)
        if (a[i] != b[i]) return 0;
    return 1;
}

static int sbn_fixed_equal(const char *field, unsigned cap, const char *value) {
    unsigned i = 0;
    while (i < cap && field[i] && value[i] && field[i] == value[i]) ++i;
    return i < cap && !field[i] && !value[i];
}

static int sbn_resume_save(const sbn_sink_t *sink, const char *path) {
    sbn_resume_t meta;
    char tmp[360];
    if (sbn_len(sink->identity) >= sizeof meta.identity || snprintf(tmp, sizeof tmp, "%s.tmp", path) >= (int)sizeof tmp)
        return 0;
    memset(&meta, 0, sizeof meta);
    memcpy(meta.magic, "SBRES1\0\0", sizeof meta.magic);
    memcpy(meta.identity, sink->identity, sbn_len(sink->identity));
    memcpy(meta.etag, sink->head.etag, sbn_len(sink->head.etag));
    return m1_save(path, tmp, 0600, &meta, sizeof meta);
}

/* The saved ETag for this identity into etag (128 bytes); 1 when there is a valid record. */
static int sbn_resume_load(const char *path, const char *identity, char *etag) {
    sbn_resume_t meta;
    char extra;
    int fd, n, tail;
    if (!identity) return 0;
    fd = open(path, O_RDONLY, 0);
    if (fd < 0) return 0;
    n = read(fd, &meta, sizeof meta);
    tail = read(fd, &extra, 1);
    close(fd);
    if (n != (int)sizeof meta || tail != 0 || !sbn_bytes_equal(meta.magic, "SBRES1\0\0", sizeof meta.magic) ||
        !sbn_fixed_equal(meta.identity, sizeof meta.identity, identity) || meta.etag[sizeof meta.etag - 1] ||
        !net_strong_etag(meta.etag))
        return 0;
    memcpy(etag, meta.etag, sizeof meta.etag);
    return 1;
}

/* GET url into the file part, check that the body is audio of the expected size, then rename part onto final and sync the folder dir_path. A partial file is continued with a Range request
 * only if its resume record (<part>.etag, written when the first body byte arrives) holds a strong ETag for this identity: the request carries If-Range with it, and only a 206 for exactly
 * the missing bytes with that same ETag is appended; anything else (200, 416, another ETag, a text type, a Content-Range that does not fit) starts the file again from byte 0. Without a
 * strong ETag, or without an identity, nothing is kept after a failure. Needs 32 MB free on the card. Returns 1 when final is in place, -1 otherwise. *resumable_out is left at -1 when
 * nothing was decided (early failure), else 1 when part is kept for a later resume (network trouble, 5xx, 408/429) or 0 when it was removed or completed. */
int sbn_download(const char *url, const char *part, const char *final, const char *dir_path, const char *identity,
                 sbn_sink_t *sink, int *resumable_out) {
    char range[40], validator[320], etag[128];
    long long offset;
    int fd, rc = -1, resumable = 0, ok;
    *resumable_out = -1;
    etag[0] = 0;
    sink->file.why = m1_card_mounted() ? net_room("/mnt/mmc", 0) : SBN_W_CARD;
    if (sink->file.why) return -1;
    if (snprintf(validator, sizeof validator, "%s.etag", part) >= (int)sizeof validator) return -1;
    fd = open(part, O_RDWR | O_CREAT, 0644);
    if (fd < 0) {
        sink->file.why = m1_card_mounted() ? SBN_W_IO : SBN_W_CARD;
        return -1;
    }
    offset = lseek(fd, 0, 2);
    if (offset > 0) (void)sbn_resume_load(validator, identity, etag);
    if (offset < 0 || (offset > 0 && !net_strong_etag(etag))) {
        /* Stock lseek uses a 32-bit long. Restart an unseekable partial, or one with no valid
         * record of what it is, rather than appending a response at an unknown offset. */
        int oldfd = fd;
        fd = -1;
        if (close(oldfd) < 0) goto done;
        fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) goto done;
        offset = 0;
    }
    sbn_sink_prepare_file(sink, fd);
    sink->audio = 1;
    sink->resume_offset = offset;
    sink->validator_path = validator;
    sink->identity = identity;
    if (offset > 0)
        snprintf(sink->resume_etag, sizeof sink->resume_etag, "%s", etag);
    else
        unlink(validator);
    if (offset > 0) {
        unsigned want = offset < (long long)sizeof sink->prefix ? (unsigned)offset : sizeof sink->prefix;
        int got;
        if (lseek(fd, 0, 0) < 0) goto done;
        got = read(fd, sink->prefix, want);
        if (got != (int)want || lseek(fd, 0, 2) < 0) goto done;
        sink->prefix_used = want;
        if (snprintf(range, sizeof range, "%lld-", offset) >= (int)sizeof range) goto done;
    } else
        range[0] = 0;
    rc = sbn_http(url, sink, 0L, range);
    if (offset > 0 &&
        (sink->http_status == 200 || sink->http_status == 416 || (sink->http_status == 206 && !sink->headers_ok))) {
        int oldfd = fd;
        fd = -1;
        if (close(oldfd) < 0) goto done;
        fd = open(part, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) goto done;
        offset = 0;
        sbn_sink_prepare_file(sink, fd);
        sink->audio = 1;
        sink->resume_offset = 0;
        sink->validator_path = validator;
        sink->identity = identity;
        unlink(validator);
        rc = sbn_http(url, sink, 0L, (const char *)0);
    }
    ok = !rc && sbn_audio_response_valid(sink, offset > 0 ? 206 : 200, offset);
    if (ok) {
        fd = -1; /* closed either way */
        if (!net_file_close(&sink->file)) {
            ok = 0;
            sink->file.why = SBN_W_IO;
        }
    }
    if (ok) {
        if (net_publish(part, final, dir_path)) { /* (a folder that could not be synced does not fail the file) */
            unlink(validator);
            *resumable_out = 0;
            sink->file.fd = -1;
            return 1;
        }
        sink->file.why = SBN_W_IO;
        resumable = 1;
    } else if (sink->curl_result != 0 &&
               (sink->http_status == 0 || sink->http_status >= 500 || sink->http_status == 408 ||
                sink->http_status == 429 || sink->curl_result == CURLE_PARTIAL_FILE ||
                sink->curl_result == CURLE_OPERATION_TIMEDOUT || sink->curl_result == CURLE_WRITE_ERROR))
        resumable = 1;
    /* A resume that wrote no byte this transfer and got no usable answer (none, 5xx, 408, 429 or a timeout) leaves the partial file and its record as they were. Any response that started appending bytes keeps the strict rule: its appended bytes are only resumable when the headers were checked before the first body write and the record was saved with it. */
    if (offset > 0 && !sink->body_started &&
        (sink->http_status == 0 || sink->http_status >= 500 || sink->http_status == 408 || sink->http_status == 429 ||
         sink->curl_result == CURLE_OPERATION_TIMEDOUT)) {
        resumable = 1;
    } else if (!sink->headers_ok || !sink->resume_saved || !net_strong_etag(sink->head.etag))
        resumable = 0;
    if (resumable && fd >= 0 && fsync(fd) < 0) resumable = 0;
    if (resumable && sink->file.written == 0 && offset == 0) resumable = 0;
    if (resumable && m1_card_mounted())
        *resumable_out = 1;
    else {
        *resumable_out = 0;
        if (m1_card_mounted()) {
            unlink(part);
            unlink(validator);
        }
    }
done:
    if (fd >= 0) close(fd);
    sink->file.fd = -1;
    return -1;
}
