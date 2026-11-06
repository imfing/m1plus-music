/* Software Update, the pure rules (patch/upver.h; docs/modules/update.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "upver.h"

#ifndef M1PLUS_VERSION
#error "M1PLUS_VERSION is set by tools/pod.py from tools/build.py VERSION"
#endif

char up_own[UP_TAG] = M1PLUS_VERSION;
int up_dev __attribute__((section(".data.up_dev"))) =
    M1PLUS_DEV; /* (a zero would be .bss, which the payload does not have) */
char up_repo[48] = M1PLUS_REPO;
char up_about[UP_TAG] = M1PLUS_TAG;
char up_base[UP_BASE] __attribute__((section(".scratch")));

static unsigned up_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

int up_parse(const char *s, unsigned v[3]) {
    int part, digits;
    unsigned n;
    if (!s) return 0;
    for (part = 0; part < 3; ++part) {
        n = 0;
        for (digits = 0; s[digits] >= '0' && s[digits] <= '9'; ++digits) {
            if (digits >= 5) return 0;
            n = n * 10 + (unsigned)(s[digits] - '0');
        }
        if (!digits) return 0;
        v[part] = n;
        s += digits;
        if (part < 2) {
            if (*s != '.') return 0;
            ++s;
        }
    }
    return *s == 0;
}

int up_cmp(const unsigned a[3], const unsigned b[3]) {
    int i;
    for (i = 0; i < 3; ++i)
        if (a[i] != b[i]) return a[i] < b[i] ? -1 : 1;
    return 0;
}

int up_offer(const char *tag, const char *own, int dev) {
    unsigned t[3], o[3];
    if (!up_parse(tag, t)) return 0;
    if (dev) return 2;
    if (!up_parse(own, o)) return 0;
    return up_cmp(t, o) > 0 ? 2 : 1;
}

int up_redirect_tag(const char *loc, const char *repo, char *out, unsigned size) {
    static const char head[] = "https://github.com/", mid[] = "/releases/tag/";
    unsigned v[3], i, n;
    if (!loc || !repo || !out || size < UP_TAG) return 0;
    for (i = 0; head[i]; ++i)
        if (loc[i] != head[i]) return 0;
    loc += i;
    n = up_len(repo);
    for (i = 0; i < n; ++i)
        if (loc[i] != repo[i]) return 0;
    loc += n;
    for (i = 0; mid[i]; ++i)
        if (loc[i] != mid[i]) return 0;
    loc += i;
    if (!up_parse(loc, v)) return 0;
    n = up_len(loc);
    for (i = 0; i <= n; ++i) out[i] = loc[i];
    return 1;
}

int up_devtag(const char *s) {
    static const char head[] = "V2.1z";
    unsigned i, n;
    if (!s) return 0;
    for (i = 0; head[i]; ++i)
        if (s[i] != head[i]) return 0;
    for (n = 0; s[i + n] >= 'A' && s[i + n] <= 'Z'; ++n) {
    }
    return n >= 1 && n <= 12 && !s[i + n];
}

int up_chan_read(const char *path, char *base) {
    char buf[UP_BASE + 32];
    unsigned got = 0, n, i;
    int fd = open(path, O_RDONLY, 0), r;
    base[0] = 0;
    if (fd < 0) return 0;
    while (got < sizeof buf && (r = read(fd, buf + got, sizeof buf - got)) > 0) got += (unsigned)r;
    close(fd);
    if (got == sizeof buf) return -1; /* longer than any address it may hold */
    n = got;
    while (n &&
           (buf[n - 1] == '\n' || buf[n - 1] == '\r' || buf[n - 1] == ' ' || buf[n - 1] == '\t' || buf[n - 1] == '/'))
        --n;
    if (n >= UP_BASE) return -1;
    for (i = 0; i < n; ++i)
        if (buf[i] <= ' ' || buf[i] > '~') return -1;
    buf[n] = 0;
    for (i = 0; "http://"[i] && buf[i] == "http://"[i]; ++i) {
    }
    if (i < 7) {
        for (i = 0; "https://"[i] && buf[i] == "https://"[i]; ++i) {
        }
        if (i < 8) return -1;
    }
    if (n == i) return -1; /* no host */
    for (i = 0; i <= n; ++i) base[i] = buf[i];
    return 1;
}

int up_chan_tag(const char *loc, const char *base, char *out, unsigned size) {
    static const char mid[] = "/releases/tag/";
    unsigned v[3], i, n;
    if (!loc || !base || !out || size < UP_TAG) return 0;
    n = up_len(base);
    for (i = 0; i < n; ++i)
        if (loc[i] != base[i]) return 0;
    loc += n;
    for (i = 0; mid[i]; ++i)
        if (loc[i] != mid[i]) return 0;
    loc += i;
    if (!up_parse(loc, v) && !up_devtag(loc)) return 0;
    n = up_len(loc);
    for (i = 0; i <= n; ++i) out[i] = loc[i];
    return 1;
}

int up_chan_offer(const char *tag, const char *about) {
    unsigned v[3], i;
    if (!up_parse(tag, v) && !up_devtag(tag)) return 0;
    for (i = 0; tag[i] && tag[i] == about[i]; ++i) {
    }
    return tag[i] == about[i] ? 1 : 2;
}

int up_source(void) { return up_chan_read(UP_CHAN_FILE, up_base) < 0 ? -1 : 0; }

void up_url(int what, const char *tag, char *out, unsigned size) {
    if (up_base[0]) {
        if (what == UP_URL_LATEST)
            snprintf(out, size, "%s/releases/latest", up_base);
        else if (what == UP_URL_NOTES)
            snprintf(out, size, "%s/releases/tags/%s", up_base, tag);
        else
            snprintf(out, size, "%s/releases/download/%s/update.bin", up_base, tag);
    } else if (what == UP_URL_LATEST)
        snprintf(out, size, "https://github.com/%s/releases/latest", up_repo);
    else if (what == UP_URL_NOTES)
        snprintf(out, size, "https://api.github.com/repos/%s/releases/tags/%s", up_repo, tag);
    else
        snprintf(out, size, "https://github.com/%s/releases/download/%s/update.bin", up_repo, tag);
}

int up_https_only(void) { return !up_base[0]; }

int up_latest(const char *loc, char *tag, unsigned size) {
    if (up_base[0]) return up_chan_tag(loc, up_base, tag, size) ? up_chan_offer(tag, up_about) : 0;
    return up_redirect_tag(loc, up_repo, tag, size) ? up_offer(tag, up_own, up_dev) : 0;
}

int up_tag_ok(const char *tag) {
    unsigned v[3];
    return up_parse(tag, v) || up_devtag(tag);
}

/* Octal digits of a tar header field (spaces and NULs after them), -1 when it is anything else. */
static long up_oct(const unsigned char *f, unsigned n) {
    long v = 0;
    unsigned i = 0;
    while (i < n && f[i] == ' ') ++i;
    if (i == n || f[i] < '0' || f[i] > '7') return -1;
    for (; i < n && f[i] >= '0' && f[i] <= '7'; ++i) v = v * 8 + (f[i] - '0');
    for (; i < n; ++i)
        if (f[i] != ' ' && f[i] != 0) return -1;
    return v;
}

int up_info_ok(const char *path, const char *tag) {
    unsigned char hdr[512], body[512];
    char want[96];
    unsigned i, sum = 0, got = 0, size, w = 0;
    unsigned v[3];
    long n, chk;
    int fd, r, ok = 0, dev = up_devtag(tag);
    static const char pre[] = UP_MODEL "\n" UP_PKG_PREFIX;
    if (!dev && !up_parse(tag, v)) return 0;
    fd = open(path, O_RDONLY, 0);
    if (fd < 0) return 0;
    while (got < sizeof hdr && (r = read(fd, hdr + got, sizeof hdr - got)) > 0) got += (unsigned)r;
    if (got == sizeof hdr) {
        for (i = 0; i < sizeof hdr; ++i) sum += i >= 148 && i < 156 ? ' ' : hdr[i];
        chk = up_oct(hdr + 148, 8);
        n = up_oct(hdr + 124, 12);
        for (i = 0; UP_INFO[i] && hdr[i] == (unsigned char)UP_INFO[i]; ++i) {
        }
        /* the member is the plain file firmware_v20.info of a tar (magic "ustar", checksum right), small enough to be one block */
        if (!UP_INFO[i] && hdr[i] == 0 && chk >= 0 && (unsigned)chk == sum && hdr[257] == 'u' && hdr[258] == 's' &&
            hdr[259] == 't' && hdr[260] == 'a' && hdr[261] == 'r' && (hdr[156] == '0' || hdr[156] == 0) && n > 0 &&
            n <= (long)sizeof body) {
            size = (unsigned)n;
            got = 0;
            while (got < size && (r = read(fd, body + got, size - got)) > 0) got += (unsigned)r;
            if (got == size) {
                for (i = 0; pre[i]; ++i) {
                    want[w++] = pre[i];
                    if (dev && pre[i] == '\n') break; /* a development package's line 2 is its tag */
                }
                for (i = 0; tag[i] && w < sizeof want - 2; ++i) want[w++] = tag[i];
                want[w++] = '\n';
                ok = size >= w;
                for (i = 0; ok && i < w; ++i) ok = body[i] == (unsigned char)want[i];
            }
        }
    }
    close(fd);
    return ok;
}

/* ---------------------------------------------------------------------------
 * The release notes: the top-level "body" string of GitHub's release JSON (api.github.com/repos/<repo>/releases/tags/<tag>)
 */

/* The index after the string that starts at js[i] (a quote), -1 when it is not closed or holds a raw control character (JSON allows none). The escapes are skipped, not checked. */
static int up_str_end(const char *js, unsigned n, unsigned i) {
    for (++i; i < n; ++i) {
        unsigned char c = (unsigned char)js[i];
        if (c == '"') return (int)i + 1;
        if (c < 0x20) return -1;
        if (c == '\\' && ++i >= n) return -1;
    }
    return -1;
}

static int up_hex4(const char *s, unsigned n, unsigned i) {
    int v = 0, k;
    if (i + 4 > n) return -1;
    for (k = 0; k < 4; ++k) {
        char c = s[i + (unsigned)k];
        int d = c >= '0' && c <= '9'   ? c - '0'
                : c >= 'a' && c <= 'f' ? c - 'a' + 10
                : c >= 'A' && c <= 'F' ? c - 'A' + 10
                                       : -1;
        if (d < 0) return -1;
        v = v * 16 + d;
    }
    return v;
}

static unsigned up_utf8(char *p, unsigned cp) {
    if (cp < 0x80) {
        p[0] = (char)cp;
        return 1;
    }
    if (cp < 0x800) {
        p[0] = (char)(0xc0 | cp >> 6), p[1] = (char)(0x80 | (cp & 0x3f));
        return 2;
    }
    if (cp < 0x10000) {
        p[0] = (char)(0xe0 | cp >> 12), p[1] = (char)(0x80 | (cp >> 6 & 0x3f)), p[2] = (char)(0x80 | (cp & 0x3f));
        return 3;
    }
    p[0] = (char)(0xf0 | cp >> 18), p[1] = (char)(0x80 | (cp >> 12 & 0x3f)), p[2] = (char)(0x80 | (cp >> 6 & 0x3f)),
    p[3] = (char)(0x80 | (cp & 0x3f));
    return 4;
}

/* The string that starts at js[i] decoded in place (a decoded escape is never longer than its source), the text at js + i + 1; *len its length. 0 when the string is malformed: a bad escape, a raw control
 * character, no closing quote. A lone surrogate becomes U+FFFD; \u0000 is dropped. */
static int up_unjson(char *js, unsigned n, unsigned i, unsigned *len) {
    unsigned r = i + 1, w = i + 1;
    while (r < n) {
        unsigned char c = (unsigned char)js[r];
        if (c == '"') {
            *len = w - (i + 1);
            return 1;
        }
        if (c < 0x20) return 0;
        if (c != '\\') {
            js[w++] = (char)c, ++r;
            continue;
        }
        if (++r >= n) return 0;
        c = (unsigned char)js[r++];
        switch (c) {
        case 'n':
            js[w++] = '\n';
            break;
        case 'r':
            js[w++] = '\r';
            break;
        case 't':
            js[w++] = '\t';
            break;
        case 'b':
            js[w++] = '\b';
            break;
        case 'f':
            js[w++] = '\f';
            break;
        case '"':
        case '\\':
        case '/':
            js[w++] = (char)c;
            break;
        case 'u': {
            int a = up_hex4(js, n, r), b;
            unsigned cp;
            if (a < 0) return 0;
            r += 4;
            cp = (unsigned)a;
            if (cp >= 0xd800 && cp < 0xdc00) {
                if (r + 1 < n && js[r] == '\\' && js[r + 1] == 'u' && (b = up_hex4(js, n, r + 2)) >= 0xdc00 &&
                    b < 0xe000) {
                    cp = 0x10000 + ((cp - 0xd800) << 10) + ((unsigned)b - 0xdc00);
                    r += 6;
                } else
                    cp = 0xfffd;
            } else if (cp >= 0xdc00 && cp < 0xe000)
                cp = 0xfffd;
            if (cp) w += up_utf8(js + w, cp);
            break;
        }
        default:
            return 0;
        }
    }
    return 0;
}

/* The decoded text s (n bytes) for the screen, into out (cap bytes with the NUL): carriage returns dropped, the # of a heading and the ** of bold dropped, "- " and "* " list items shown as a bullet, three
 * line feeds in a row made two, no blank edges, cut where cap is full and always between two UTF-8 characters. */
static unsigned up_clean(const char *s, unsigned n, char *out, unsigned cap) {
    unsigned i = 0, o = 0;
    int bol = 1;
    while (i < n) {
        unsigned char c = (unsigned char)s[i];
        unsigned len = 1, k;
        if (bol) {
            unsigned j = i, h;
            while (j < n && s[j] == ' ') ++j;
            for (h = j; h < n && s[h] == '#'; ++h) {
            }
            bol = 0;
            if (h > j && h - j <= 6 && h < n && s[h] == ' ') { /* a heading: its marker and the air around it go */
                for (i = h + 1; i < n && s[i] == ' '; ++i) {
                }
                continue;
            }
            if (j + 1 < n && (s[j] == '-' || s[j] == '*') &&
                s[j + 1] == ' ') { /* a list item: its indent, then a bullet */
                if (o + (j - i) + 4 >= cap) break;
                for (; i < j; ++i) out[o++] = ' ';
                out[o++] = (char)0xe2, out[o++] = (char)0x80, out[o++] = (char)0xa2, out[o++] = ' ';
                i = j + 2;
                continue;
            }
        }
        if (c == '\r') {
            ++i;
            continue;
        }
        if (c == '*' && i + 1 < n && s[i + 1] == '*') {
            i += 2;
            continue;
        }
        if (c == '\n') {
            ++i;
            bol = 1;
            if (!o || (o >= 2 && out[o - 1] == '\n' && out[o - 2] == '\n')) continue;
            if (o + 1 >= cap) break;
            out[o++] = '\n';
            continue;
        } else if (c == ' ' && !o) {
            ++i;
            continue;
        } else if (c >= 0xf0)
            len = 4;
        else if (c >= 0xe0)
            len = 3;
        else if (c >= 0xc0)
            len = 2;
        if (i + len > n) len = n - i;
        if (o + len >= cap) break;
        for (k = 0; k < len; ++k) out[o++] = s[i + k];
        i += len;
    }
    while (o && (out[o - 1] == '\n' || out[o - 1] == ' ' || out[o - 1] == '\t')) --o;
    out[o] = 0;
    return o;
}

unsigned up_notes(char *js, unsigned n, char *out, unsigned cap) {
    unsigned i = 0, e, len;
    int depth = 0;
    if (!cap) return 0;
    out[0] = 0;
    while (i < n && (js[i] == ' ' || js[i] == '\n' || js[i] == '\r' || js[i] == '\t')) ++i;
    if (i >= n || js[i] != '{') return 0;
    while (i < n) {
        char c = js[i];
        if (c == '{' || c == '[')
            ++depth, ++i;
        else if (c == '}' || c == ']') {
            if (--depth <= 0) return 0; /* the top-level object is over without a body */
            ++i;
        } else if (c == '"') {
            int se = up_str_end(js, n, i);
            unsigned j;
            if (se < 0) return 0;
            e = (unsigned)se;
            for (j = e; j < n && (js[j] == ' ' || js[j] == '\n' || js[j] == '\r' || js[j] == '\t'); ++j) {
            }
            if (depth == 1 && j < n && js[j] == ':' && e - i == 6 && js[i + 1] == 'b' && js[i + 2] == 'o' &&
                js[i + 3] == 'd' && js[i + 4] == 'y') { /* the key "body" of the top-level object */
                for (++j; j < n && (js[j] == ' ' || js[j] == '\n' || js[j] == '\r' || js[j] == '\t'); ++j) {
                }
                if (j >= n || js[j] != '"' || !up_unjson(js, n, j, &len)) return 0; /* null, a number, a bad string */
                return up_clean(js + j + 1, len, out, cap);
            }
            i = e;
        } else
            ++i;
    }
    return 0;
}
