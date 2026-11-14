/* A small, bounded JSON extractor for the iTunes search and lookup answers (patch/pcjson.h; docs/modules/podcasts.md "Search").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "pcjson.h"
#include "utf8.h"

typedef struct {
    const unsigned char *s, *e;
} pj_t;

typedef struct
{ /* where a string goes: out (NULL: nowhere, the string is only skipped), its size, the bytes used, whether something was left out */
    char *out;
    unsigned cap, n;
    int cut;
    int nl; /* 1: \n stays a line feed and \r is dropped (lyrics); 0: both are a space */
} pj_out_t;

static void pj_ws(pj_t *p) {
    while (p->s < p->e && (*p->s == ' ' || *p->s == '\t' || *p->s == '\n' || *p->s == '\r')) ++p->s;
}

/* The value of the four hex digits at s (all four must be inside the text), -1 for anything else. */
static int pj_hex4(const unsigned char *s, const unsigned char *e) {
    int v = 0, i;
    if (e - s < 4) return -1;
    for (i = 0; i < 4; ++i) {
        int h = m1_hexval(s[i]);
        if (h < 0) return -1;
        v = v << 4 | h;
    }
    return v;
}

/* One code point as UTF-8 into the string, whole or not at all: the first one that does not fit (the NUL has its byte) ends what is kept, so the result is always a prefix cut on a character boundary. */
static void pj_put(pj_out_t *o, unsigned cp) {
    unsigned len = m1_utf8_len(cp);
    if (!o->out || o->cut) return;
    if (o->n + len + 1 > o->cap) {
        o->cut = 1;
        return;
    }
    o->n += m1_utf8_put(o->out + o->n, cp);
}

/* The string whose opening quote is at p->s, decoded into o: \" \\ \/ and the escapes of a control character (a space), \uXXXX (a surrogate pair is one character; a lone surrogate, \u0000 and a \u
 * without four hex digits are dropped), a raw control character is a space, a raw byte sequence that is not UTF-8 is dropped. p ends after the closing quote; 0 when the text ends first. */
static int pj_str(pj_t *p, pj_out_t *o) {
    ++p->s;
    for (;;) {
        unsigned c;
        if (p->s >= p->e) return 0;
        c = *p->s++;
        if (c == '"') return 1;
        if (c == '\\') {
            if (p->s >= p->e) return 0;
            c = *p->s++;
            if (c == 'u') {
                int hi = pj_hex4(p->s, p->e);
                if (hi < 0) continue;
                p->s += 4;
                if (hi >= 0xd800 && hi < 0xdc00) { /* needs its low half right behind it */
                    int lo = p->e - p->s >= 2 && p->s[0] == '\\' && p->s[1] == 'u' ? pj_hex4(p->s + 2, p->e) : -1;
                    if (lo >= 0xdc00 && lo < 0xe000) {
                        p->s += 6;
                        pj_put(o, 0x10000u + ((unsigned)(hi - 0xd800) << 10) + (unsigned)(lo - 0xdc00));
                    }
                } else if ((hi >= 0xdc00 && hi < 0xe000) || hi == 0) {
                    continue;
                } else
                    pj_put(o, hi < 0x20 ? ' ' : (unsigned)hi);
            } else if (o->nl && c == 'n')
                pj_put(o, '\n');
            else if (o->nl && c == 'r')
                continue;
            else if (c == 'n' || c == 'r' || c == 't' || c == 'b' || c == 'f')
                pj_put(o, ' ');
            else if (c >= 0x80)
                --p->s; /* a backslash before a multi-byte character: the character is read as itself */
            else
                pj_put(o, c < 0x20 ? ' ' : c);
        } else if (c < 0x20)
            pj_put(o, ' ');
        else if (c < 0x80)
            pj_put(o, c);
        else {
            int need = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc2 ? 1 : 0, i;
            unsigned cp = c & (need == 3 ? 0x07u : need == 2 ? 0x0fu : 0x1fu);
            if (!need || c > 0xf4 || p->e - p->s < need) continue;
            for (i = 0; i < need; ++i) {
                if ((p->s[i] & 0xc0) != 0x80) break;
                cp = cp << 6 | (p->s[i] & 0x3fu);
            }
            if (i < need || (need == 2 && cp < 0x800) || (need == 3 && (cp < 0x10000 || cp > 0x10ffff)) ||
                (cp >= 0xd800 && cp < 0xe000))
                continue; /* the lead byte is dropped; what follows it is read on its own */
            p->s += need;
            pj_put(o, cp);
        }
    }
}

/* One value skipped, at any depth up to PJ_DEPTH, by its brackets and strings. 1 when it ended inside the text, 0 when the text ended (or went too deep, or the value is not one). */
static int pj_skip(pj_t *p) {
    int depth = 0;
    for (;;) {
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '"') {
            pj_out_t none;
            none.out = (char *)0, none.cap = none.n = 0, none.cut = none.nl = 0;
            if (!pj_str(p, &none)) return 0;
        } else if (c == '{' || c == '[') {
            if (++depth > PJ_DEPTH) return 0;
            ++p->s;
            continue;
        } else if (c == '}' || c == ']') {
            if (!depth) return 0;
            ++p->s;
            if (--depth) continue;
            return 1;
        } else if (c == ',' || c == ':') {
            if (!depth) return 0;
            ++p->s;
            continue;
        } else {
            const unsigned char *start = p->s;
            while (p->s < p->e && *p->s != ',' && *p->s != '}' && *p->s != ']' && *p->s != ':' && *p->s != ' ' &&
                   *p->s != '\t' && *p->s != '\n' && *p->s != '\r' && *p->s != '"' && *p->s != '{' && *p->s != '[')
                ++p->s;
            if (p->s == start) return 0;
        }
        if (!depth) return 1;
    }
}

/* A number at p->s: its digits as an unsigned (more than 32 bits: 0xffffffff, a sign, fraction or exponent: the digits before them, a negative number 0); p ends after the token. */
static unsigned pj_num(pj_t *p) {
    unsigned long long v = 0;
    int neg = *p->s == '-', digits = 1;
    while (p->s < p->e && *p->s != ',' && *p->s != '}' && *p->s != ']' && *p->s != ' ' && *p->s != '\t' &&
           *p->s != '\n' && *p->s != '\r') {
        if (*p->s < '0' || *p->s > '9')
            digits = 0;
        else if (digits && v < 0xffffffffull)
            v = v * 10 + (*p->s - '0');
        ++p->s;
    }
    return neg ? 0 : v > 0xffffffffull ? 0xffffffffu : (unsigned)v;
}

static int pj_is(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* A string value at p->s (the opening quote) into dst of size cap (at most; the NUL after it). 0 when the text ended first. *cut: something was left out. */
static int pj_val(pj_t *p, char *dst, unsigned cap, int *cut) {
    pj_out_t vo;
    vo.out = dst, vo.cap = cap, vo.n = vo.cut = vo.nl = 0;
    if (!pj_str(p, &vo)) return 0;
    dst[vo.n] = 0;
    if (cut) *cut = vo.cut;
    return 1;
}

/* The key string at p->s and the ':' after it; 1 with p on the value, 0 when the object is not well formed or the text ends. */
static int pj_key(pj_t *p, char *key, unsigned size) {
    if (!pj_val(p, key, size, (int *)0)) return 0;
    pj_ws(p);
    if (p->s >= p->e || *p->s != ':') return 0;
    ++p->s;
    pj_ws(p);
    return p->s < p->e;
}

/* The "name" of the object at p->s ('{') into dst (Deezer's artist); every other member skipped. p ends after the '}'. 0 when the text ended. */
static int pj_nested_name(pj_t *p, char *dst, unsigned cap) {
    ++p->s;
    for (;;) {
        char key[8];
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '}') {
            ++p->s;
            return 1;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return 0;
        if (*p->s == '"' && pj_is("name", key)) {
            if (!pj_val(p, dst, cap, (int *)0)) return 0;
        } else if (!pj_skip(p))
            return 0;
    }
}

/* The object whose '{' is at p->s into r. dz 0: the store's (collectionId, collectionName, artistName, feedUrl, artworkUrl100, artworkUrl600); 1: Deezer's album (id, title, artist.name, cover_medium as art); 2: Deezer's artist (name, whole in feed too, picture_medium as art, nb_fan as id); 3: NetEase's artist (name likewise, img1v1Url as art, picUrl as art6, fansSize as id).
 * 1 when its '}' was reached, 0 when the text ended (or it was not an object): then r is not an answer. */
static int pj_obj(pj_t *p, pj_result_t *r, int dz) {
    r->id = 0;
    r->name[0] = r->author[0] = r->feed[0] = r->art[0] = r->art6[0] = 0;
    ++p->s;
    for (;;) {
        char key[24];
        int which, cut = 0;
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '}') {
            ++p->s;
            return 1;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return 0;
        if (dz == 2)
            which = pj_is("nb_fan", key) ? 1 : pj_is("name", key) ? 4 : pj_is("picture_medium", key) ? 5 : 0;
        else if (dz == 3)
            which = pj_is("fansSize", key)    ? 1
                    : pj_is("name", key)      ? 4
                    : pj_is("img1v1Url", key) ? 5
                    : pj_is("picUrl", key)    ? 6
                                              : 0;
        else if (dz)
            which = pj_is("id", key)             ? 1
                    : pj_is("title", key)        ? 2
                    : pj_is("artist", key)       ? 3
                    : pj_is("cover_medium", key) ? 5
                                                 : 0;
        else
            which = pj_is("collectionId", key)     ? 1
                    : pj_is("collectionName", key) ? 2
                    : pj_is("artistName", key)     ? 3
                    : pj_is("feedUrl", key)        ? 4
                    : pj_is("artworkUrl100", key)  ? 5
                    : pj_is("artworkUrl600", key)  ? 6
                                                   : 0;
        if (which == 1 && *p->s >= '0' && *p->s <= '9')
            r->id = pj_num(p);
        else if (dz == 1 && which == 3 && *p->s == '{') {
            if (!pj_nested_name(p, r->author, PJ_AUTHOR)) return 0;
        } else if (which >= 2 && *p->s == '"' && !(dz == 1 && which == 3)) {
            char *dst = which == 2   ? r->name
                        : which == 3 ? r->author
                        : which == 4 ? r->feed
                        : which == 6 ? r->art6
                                     : r->art;
            if (!pj_val(p, dst, which == 2 ? PJ_NAME : which == 3 ? PJ_AUTHOR : which == 4 ? PC_URL : PJ_ART, &cut))
                return 0;
            if (cut && which >= 4) dst[0] = 0; /* a cut address is no address */
            if (dz >= 2 && which == 4) { /* (an artist's name: whole in feed, cut as any name in name) */
                unsigned k = 0, j;
                while (dst[k] && k < PJ_NAME - 1) ++k;
                if (dst[k])
                    while (k && ((unsigned char)dst[k] & 0xc0) == 0x80) --k;
                for (j = 0; j < k; ++j) r->name[j] = dst[j];
                r->name[k] = 0;
            }
        } else if (!pj_skip(p))
            return 0;
    }
}

/* The elements of the array whose '[' has been passed: the objects (the others are skipped) into out, up to max. Returns how many were kept. */
static int pj_array(pj_t *p, pj_result_t *out, int max, int dz) {
    int n = 0;
    for (;;) {
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return n;
        c = *p->s;
        if (c == ']') {
            ++p->s;
            return n;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (n >= max) return n;
        if (c == '{') {
            if (!pj_obj(p, &out[n], dz)) return n; /* cut short: not kept */
            if (out[n].name[0] || out[n].feed[0]) ++n;
        } else if (!pj_skip(p))
            return n;
    }
}

/* The members of the object whose '{' has been passed, up to the one called want whose value opens with open ('[' or '{'): 1 with p after that character, 0 when the object ends without it, -1 when it is not well
 * formed or the text ends. */
static int pj_find(pj_t *p, const char *want, unsigned open) {
    for (;;) {
        char key[16];
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return -1;
        c = *p->s;
        if (c == '}') return 0;
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return -1;
        if (*p->s == open && pj_is(want, key)) {
            ++p->s;
            return 1;
        }
        if (!pj_skip(p)) return -1;
    }
}

/* The members of the top-level object, up to the array called want: its objects. -1 when there is none. */
static int pj_top(const char *json, unsigned n, pj_result_t *out, int max, const char *want, int dz) {
    pj_t p;
    p.s = (const unsigned char *)json, p.e = p.s + n;
    pj_ws(&p);
    if (p.s >= p.e || *p.s != '{' || max <= 0) return -1;
    ++p.s;
    return pj_find(&p, want, '[') == 1 ? pj_array(&p, out, max, dz) : -1;
}

int pj_results(const char *json, unsigned n, pj_result_t *out, int max) {
    return pj_top(json, n, out, max, "results", 0);
}

int pj_deezer(const char *json, unsigned n, pj_result_t *out, int max) { return pj_top(json, n, out, max, "data", 1); }

int pj_deezer_artists(const char *json, unsigned n, pj_result_t *out, int max) {
    return pj_top(json, n, out, max, "data", 2);
}

int pj_netease_artists(const char *json, unsigned n, pj_result_t *out, int max) {
    pj_t p;
    int r;
    p.s = (const unsigned char *)json, p.e = p.s + n;
    pj_ws(&p);
    if (p.s >= p.e || *p.s != '{' || max <= 0) return -1;
    ++p.s;
    if (pj_find(&p, "result", '{') != 1) return -1;
    r = pj_find(&p, "artists", '[');
    return r == 1 ? pj_array(&p, out, max, 3) : r; /* (a "result" with no "artists": nothing was found) */
}

/* The digits of s, nothing else in it, 1 to 15 of them and not all zeros, into out (16 bytes); 1 when they are an Apple id. */
static int pj_digits(const char *s, char *out) {
    unsigned n = 0, nz = 0;
    for (; *s >= '0' && *s <= '9'; ++s) {
        if (n >= 15) return 0;
        out[n++] = *s;
        nz |= *s != '0';
    }
    out[n] = 0;
    return n && nz && !*s;
}

/* The Apple id in a store address: the digits after its first "/id" that has a digit next (".../podcast/the-daily/id1200361736?i=1000..."), into out. 0 for none, for more than 15 digits, and for digits that ran to the end of a cut address. */
static int pj_url_id(const char *u, int cut, char *out) {
    for (; *u; ++u)
        if (u[0] == '/' && u[1] == 'i' && u[2] == 'd' && u[3] >= '0' && u[3] <= '9') {
            unsigned n = 0, nz = 0;
            const char *d = u + 3;
            for (; *d >= '0' && *d <= '9'; ++d) {
                if (n >= 15) return 0;
                out[n++] = *d;
                nz |= *d != '0';
            }
            out[n] = 0;
            return n && nz && !(cut && !*d);
        }
    return 0;
}

static void pj_idcopy(char *dst, const char *src) {
    unsigned i = 0;
    for (; src[i]; ++i) dst[i] = src[i];
    dst[i] = 0;
}

/* An id member's value at p->s (a number or a string) into out (16 bytes): its digits, "" when it is none; 0 when the text is not well formed. */
static int pj_idval(pj_t *p, char *out) {
    int cut = 0;
    if (*p->s >= '0' &&
        *p->s <= '9') { /* a number: its digits as written (an episode's id is past 32 bits, which pj_num clamps) */
        char t[24];
        unsigned i = 0;
        while (p->s < p->e && *p->s != ',' && *p->s != '}' && *p->s != ']' && *p->s != ' ' && *p->s != '\t' &&
               *p->s != '\n' && *p->s != '\r') {
            if (i < sizeof t - 1) t[i++] = (char)*p->s; /* (a longer one has over 15 digits: no id) */
            ++p->s;
        }
        t[i] = 0;
        if (!pj_digits(t, out)) out[0] = 0; /* (0 is no id) */
        return 1;
    }
    {
        char t[24];
        if (!pj_val(p, t, sizeof t, &cut)) return 0;
        if (cut || !pj_digits(t, out)) out[0] = 0;
    }
    return 1;
}

/* The chart object whose '{' is at p->s into r: id (a string of digits, or a number), name, artistName, artworkUrl100 and url. 1 when its '}' was reached, 0 when the text ended (or it was not well formed). */
static int pj_cobj(pj_t *p, pj_chart_t *r, int episodes) {
    char idv[16], urlid[16];
    idv[0] = urlid[0] = 0;
    r->name[0] = r->author[0] = r->art[0] = 0;
    ++p->s;
    for (;;) {
        char key[16];
        int which, cut = 0;
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '}') {
            ++p->s;
            pj_idcopy(r->id, episodes ? urlid : idv);
            pj_idcopy(r->eid, episodes ? idv : "");
            return 1;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return 0;
        which = pj_is("id", key)              ? 1
                : pj_is("name", key)          ? 2
                : pj_is("artistName", key)    ? 3
                : pj_is("artworkUrl100", key) ? 4
                : pj_is("url", key)           ? 5
                                              : 0;
        if (which == 1 && (*p->s == '"' || (*p->s >= '0' && *p->s <= '9'))) {
            if (!pj_idval(p, idv)) return 0;
        } else if (which == 5 && *p->s == '"') {
            char u[PC_URL];
            if (!pj_val(p, u, sizeof u, &cut)) return 0;
            if (!pj_url_id(u, cut, urlid)) urlid[0] = 0;
        } else if (which >= 2 && which <= 4 && *p->s == '"') {
            char *dst = which == 2 ? r->name : which == 3 ? r->author : r->art;
            if (!pj_val(p, dst, which == 2 ? PJ_NAME : which == 3 ? PJ_AUTHOR : PJ_ART, &cut)) return 0;
            if (cut && which == 4) dst[0] = 0; /* a cut address is no address */
        } else if (!pj_skip(p))
            return 0;
    }
}

/* The elements of the "results" array whose '[' has been passed: the objects with a name into out, up to max. */
static int pj_carray(pj_t *p, pj_chart_t *out, int max, int episodes) {
    int n = 0;
    for (;;) {
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return n;
        c = *p->s;
        if (c == ']') {
            ++p->s;
            return n;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (n >= max) return n;
        if (c == '{') {
            if (!pj_cobj(p, &out[n], episodes)) return n; /* cut short: not kept */
            if (out[n].name[0]) ++n;
        } else if (!pj_skip(p))
            return n;
    }
}

int pj_chart(const char *json, unsigned n, int episodes, pj_chart_t *out, int max) {
    pj_t p;
    int in_feed = 0;
    p.s = (const unsigned char *)json, p.e = p.s + n;
    pj_ws(&p);
    if (p.s >= p.e || *p.s != '{' || max <= 0) return -1;
    ++p.s;
    for (;;) {
        char key[16];
        unsigned c;
        pj_ws(&p);
        if (p.s >= p.e) return -1;
        c = *p.s;
        if (c == '}') return -1;
        if (c == ',') {
            ++p.s;
            continue;
        }
        if (c != '"' || !pj_key(&p, key, sizeof key)) return -1;
        if (!in_feed && *p.s == '{' && pj_is("feed", key)) { /* the members of the envelope are the object's own */
            in_feed = 1;
            ++p.s;
            continue;
        }
        if (in_feed && *p.s == '[' && pj_is("results", key)) {
            ++p.s;
            return pj_carray(&p, out, max, episodes);
        }
        if (!pj_skip(&p)) return -1;
    }
}

/* The episode record whose '{' is at p->s into r: trackId, episodeUrl, trackName and releaseDate. 1 when its '}' was reached, 0 when the text ended (or it was not well formed). */
static int pj_eobj(pj_t *p, pj_ep_t *r) {
    char idv[16];
    idv[0] = r->id[0] = r->url[0] = r->name[0] = r->date[0] = 0;
    ++p->s;
    for (;;) {
        char key[16];
        int which, cut = 0;
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '}') {
            ++p->s;
            pj_idcopy(r->id, idv);
            return 1;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return 0;
        which = pj_is("trackId", key)       ? 1
                : pj_is("episodeUrl", key)  ? 2
                : pj_is("trackName", key)   ? 3
                : pj_is("releaseDate", key) ? 4
                                            : 0;
        if (which == 1 && (*p->s == '"' || (*p->s >= '0' && *p->s <= '9'))) {
            if (!pj_idval(p, idv)) return 0;
        } else if (which >= 2 && *p->s == '"') {
            char *dst = which == 2 ? r->url : which == 3 ? r->name : r->date;
            if (!pj_val(p, dst, which == 2 ? PC_URL : which == 3 ? PJ_NAME : PJ_DATE, &cut)) return 0;
            if (cut && which == 2) dst[0] = 0; /* a cut address is no address */
        } else if (!pj_skip(p))
            return 0;
    }
}

/* The elements of the "results" array whose '[' has been passed: the episode records with a trackId into out, up to max. */
static int pj_earray(pj_t *p, pj_ep_t *out, int max) {
    int n = 0;
    for (;;) {
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return n;
        c = *p->s;
        if (c == ']') {
            ++p->s;
            return n;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (n >= max) return n;
        if (c == '{') {
            if (!pj_eobj(p, &out[n])) return n; /* cut short: not kept */
            if (out[n].id[0]) ++n;
        } else if (!pj_skip(p))
            return n;
    }
}

int pj_episodes(const char *json, unsigned n, pj_ep_t *out, int max) {
    pj_t p;
    p.s = (const unsigned char *)json, p.e = p.s + n;
    pj_ws(&p);
    if (p.s >= p.e || *p.s != '{' || max <= 0) return -1;
    ++p.s;
    for (;;) {
        char key[16];
        unsigned c;
        pj_ws(&p);
        if (p.s >= p.e) return -1;
        c = *p.s;
        if (c == '}') return -1;
        if (c == ',') {
            ++p.s;
            continue;
        }
        if (c != '"' || !pj_key(&p, key, sizeof key)) return -1;
        if (*p.s == '[' && pj_is("results", key)) {
            ++p.s;
            return pj_earray(&p, out, max);
        }
        if (!pj_skip(&p)) return -1;
    }
}

/* One LRCLIB record at p->s ('{') into r (trackName, artistName, albumName, duration in whole seconds) and the texts s (syncedLyrics) and pl (plainLyrics), each at most cap, a null or a missing one is "";
 * a cut text ends at its last whole line. 1 when the '}' was reached. */
static int pj_lrc_obj(pj_t *p, pj_lrc_t *r, char *s, char *pl, unsigned cap) {
    s[0] = pl[0] = 0;
    r->title[0] = r->artist[0] = r->album[0] = 0;
    r->secs = 0, r->synced = 0;
    ++p->s;
    for (;;) {
        char key[16];
        unsigned c;
        pj_ws(p);
        if (p->s >= p->e) return 0;
        c = *p->s;
        if (c == '}') {
            ++p->s;
            return 1;
        }
        if (c == ',') {
            ++p->s;
            continue;
        }
        if (c != '"' || !pj_key(p, key, sizeof key)) return 0;
        if (*p->s == '"' && (pj_is("syncedLyrics", key) || pj_is("plainLyrics", key))) {
            char *dst = pj_is("syncedLyrics", key) ? s : pl;
            pj_out_t vo;
            vo.out = dst, vo.cap = cap, vo.n = vo.cut = 0, vo.nl = 1;
            if (!pj_str(p, &vo)) return 0;
            if (vo.cut)
                while (vo.n && dst[vo.n - 1] != '\n') --vo.n;
            dst[vo.n] = 0;
        } else if (*p->s == '"' && (pj_is("trackName", key) || pj_is("artistName", key) || pj_is("albumName", key))) {
            char *dst = pj_is("trackName", key) ? r->title : pj_is("artistName", key) ? r->artist : r->album;
            if (!pj_val(p, dst, dst == r->artist ? PJ_AUTHOR : PJ_NAME, (int *)0)) return 0;
        } else if (*p->s >= '0' && *p->s <= '9' && pj_is("duration", key))
            r->secs = pj_num(p);
        else if (!pj_skip(p))
            return 0;
    }
}

/* Whether the text has anything but white space. */
static int pj_text(const char *t) {
    for (; *t; ++t)
        if (*t != ' ' && *t != '\n') return 1;
    return 0;
}

int pj_lrc_each(const char *json, unsigned n, unsigned cap, char *a, char *b,
                int (*fn)(void *, const pj_lrc_t *, const char *), void *ctx) {
    pj_t p;
    pj_lrc_t r;
    int count = 0, array;
    p.s = (const unsigned char *)json, p.e = p.s + n;
    pj_ws(&p);
    if (p.s >= p.e || (*p.s != '{' && *p.s != '[')) return -1;
    array = *p.s == '[';
    if (array) ++p.s;
    for (;;) {
        unsigned c;
        pj_ws(&p);
        if (p.s >= p.e) break;
        c = *p.s;
        if (c == ',') {
            ++p.s;
            continue;
        }
        if (c == ']') break;
        if (c == '{') {
            if (!pj_lrc_obj(&p, &r, a, b, cap)) break; /* cut short: not kept */
            r.synced = pj_text(a);
            if (r.synced || pj_text(b)) {
                ++count;
                if (!fn(ctx, &r, r.synced ? a : b)) break;
            }
            if (!array) break;
        } else if (!pj_skip(&p))
            break;
        else if (!array)
            return -1;
    }
    return count;
}

int pj_member(const char *json, unsigned n, const char *want, char *dst, unsigned cap) {
    return pj_span(json, n, want, dst, cap, (const char **)0, (unsigned *)0);
}

int pj_next(const char *json, unsigned n, unsigned *at, const char **val, unsigned *len) {
    pj_t p;
    p.s = (const unsigned char *)json + *at, p.e = (const unsigned char *)json + n;
    if (*at >= n) return 0;
    if (!*at) {
        pj_ws(&p);
        if (p.s >= p.e || *p.s != '[') return 0;
        ++p.s;
    }
    pj_ws(&p);
    if (p.s < p.e && *p.s == ',') ++p.s;
    pj_ws(&p);
    if (p.s >= p.e || *p.s == ']') return 0;
    *val = (const char *)p.s;
    if (!pj_skip(&p)) return 0;
    *len = (unsigned)((const char *)p.s - *val);
    *at = (unsigned)(p.s - (const unsigned char *)json);
    return 1;
}

int pj_span(const char *json, unsigned n, const char *want, char *dst, unsigned cap, const char **val, unsigned *len) {
    pj_t p;
    int got = PJ_M_NONE;
    char none[1];
    p.s = (const unsigned char *)json, p.e = p.s + n;
    if (!dst) dst = none, cap = 1;
    if (!cap) return PJ_M_NONE;
    dst[0] = 0;
    pj_ws(&p);
    if (p.s >= p.e || *p.s != '{') return PJ_M_NONE;
    ++p.s;
    for (;;) {
        char key[16];
        const unsigned char *v;
        unsigned c;
        pj_ws(&p);
        if (p.s >= p.e) return PJ_M_NONE;
        c = *p.s;
        if (c == '}') return got;
        if (c == ',') {
            ++p.s;
            continue;
        }
        if (c != '"' || !pj_key(&p, key, sizeof key)) return PJ_M_NONE;
        v = p.s;
        if (got != PJ_M_NONE || !pj_is(want, key)) {
            if (!pj_skip(&p)) return PJ_M_NONE;
        } else if (*v == '"') {
            if (!pj_val(&p, dst, cap, (int *)0)) return PJ_M_NONE;
            got = PJ_M_STRING;
        } else {
            if (!pj_skip(&p)) return PJ_M_NONE;
            got = p.s - v == 4 && v[0] == 't' && v[1] == 'r' && v[2] == 'u' && v[3] == 'e' ? PJ_M_TRUE
                  : p.s - v == 5 && v[0] == 'f' && v[1] == 'a' && v[2] == 'l' && v[3] == 's' && v[4] == 'e'
                      ? PJ_M_FALSE
                      : PJ_M_OTHER;
        }
        if (got != PJ_M_NONE && val && v) *val = (const char *)v, *len = (unsigned)(p.s - v), val = (const char **)0;
    }
}
