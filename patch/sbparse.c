/* Subsonic / OpenSubsonic response parsers (declared in patch/sbapi.h; docs/modules/subsonic.md "Data and cache").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). Pure functions over the JSON walker of patch/sbnet.c: no network, no files, no allocation; every read is bounded by the end of
 * the body or of the element being read, text is cut at a UTF-8 boundary, and a row without a usable id is skipped. A body is accepted only when it is one complete
 * "subsonic-response" with status "ok" (a truncated transfer is refused whole, never half read).
 */
#include "offsets.inc"
#include "sbnet.h"
#include "sbapi.h"

static void sp_zero(void *p, unsigned n) {
    unsigned char *b = (unsigned char *)p;
    while (n--) *b++ = 0;
}

static int sp_digit(int c) { return c >= '0' && c <= '9'; }

/* ---- fields ---- */

/* A text member into dst (cut to fit); "" when absent. */
static void sp_text(char *dst, unsigned cap, const char *obj, const char *end, const char *key) {
    dst[0] = 0;
    if (sbn_member_truncate(obj, end, key, dst, cap) <= 0) dst[0] = 0;
}

/* An unsigned number member. Servers that send numbers as strings are read too. Absent or odd: 0. */
static unsigned sp_num(const char *obj, const char *end, const char *key) {
    char buf[24];
    unsigned v = 0, i;
    buf[0] = 0;
    if (sbn_member(obj, end, key, buf, sizeof buf, &v) != 1) return 0;
    if (!buf[0]) return v;
    if (!sp_digit(buf[0])) return 0;
    v = 0;
    for (i = 0; sp_digit(buf[i]); ++i)
        if (v < 0x10000000u) v = v * 10 + (unsigned)(buf[i] - '0');
    return v;
}

/* An id member: a string (or a number, written out) that fits SBA_ID. 1 when there is one; 0 when it is absent, empty or too long. */
static int sp_id(char *dst, const char *obj, const char *end, const char *key) {
    unsigned v = 0, n = 0;
    char tmp[12];
    dst[0] = 0;
    if (sbn_member(obj, end, key, dst, SBA_ID, &v) != 1) {
        dst[0] = 0;
        return 0;
    }
    if (!dst[0] && v) {
        while (v) tmp[n++] = (char)('0' + v % 10), v /= 10;
        for (v = 0; n;) dst[v++] = tmp[--n];
        dst[v] = 0;
    }
    return dst[0] != 0;
}

/* 1 when the member is present and not null / empty (getStarred2 rows and star times: "starred":"2024-05-01T10:00:00Z"). */
static unsigned char sp_flag(const char *obj, const char *end, const char *key) {
    char buf[48];
    int r;
    buf[0] = 0;
    r = sbn_member(obj, end, key, buf, sizeof buf, (unsigned *)0);
    return r < 0 || (r == 1 && buf[0]) ? 1 : 0;
}

/* "2024-05-01T10:00:00.123Z" -> epoch seconds (UTC); 0 when it is not a date or before 1970. */
static unsigned sp_time(const char *obj, const char *end, const char *key) {
    char s[48];
    unsigned y, m, d, hh = 0, mm = 0, ss = 0, i;
    int yy;
    unsigned long days;
    s[0] = 0;
    if (sbn_member(obj, end, key, s, sizeof s, (unsigned *)0) != 1 || sbn_len(s) < 10) return 0;
    for (i = 0; i < 10; ++i)
        if (i == 4 || i == 7 ? s[i] != '-' : !sp_digit(s[i])) return 0;
    y = (unsigned)((s[0] - '0') * 1000 + (s[1] - '0') * 100 + (s[2] - '0') * 10 + (s[3] - '0'));
    m = (unsigned)((s[5] - '0') * 10 + (s[6] - '0'));
    d = (unsigned)((s[8] - '0') * 10 + (s[9] - '0'));
    if (y < 1970 || m < 1 || m > 12 || d < 1 || d > 31) return 0;
    if ((s[10] == 'T' || s[10] == ' ') && sp_digit(s[11]) && sp_digit(s[12]) && s[13] == ':' && sp_digit(s[14]) &&
        sp_digit(s[15])) {
        hh = (unsigned)((s[11] - '0') * 10 + (s[12] - '0'));
        mm = (unsigned)((s[14] - '0') * 10 + (s[15] - '0'));
        if (s[16] == ':' && sp_digit(s[17]) && sp_digit(s[18])) ss = (unsigned)((s[17] - '0') * 10 + (s[18] - '0'));
    }
    yy = (int)y - (m <= 2 ? 1 : 0); /* days from civil (Hinnant): March-based year */
    days = (unsigned long)((yy / 4 - yy / 100 + yy / 400) + 365 * yy + (153 * (int)(m > 2 ? m - 3 : m + 9) + 2) / 5 +
                           (int)d - 1 - 719468);
    return (unsigned)(days * 86400ul + hh * 3600ul + mm * 60ul + ss);
}

static int sp_has(const char *s, const char *needle) {
    unsigned i, j;
    for (i = 0; s[i]; ++i) {
        for (j = 0; needle[j] && s[i + j] == needle[j]; ++j) {
        }
        if (!needle[j]) return 1;
    }
    return 0;
}

static void sp_lower(char *s) {
    for (; *s; ++s) *s = (char)sbn_ascii_lower((unsigned char)*s);
}

/* The file suffix: the song's own "suffix", else its contentType, else the extension of its "path". Lower case. */
static void sp_suffix(char *dst, const char *obj, const char *end) {
    static const struct {
        const char *mime, *suffix;
    } map[] = {{"dsf", "dsf"},   {"dff", "dff"},    {"dsd", "dsf"},    {"flac", "flac"}, {"mpeg", "mp3"},
               {"mp3", "mp3"},   {"mp4", "m4a"},    {"m4a", "m4a"},    {"aac", "aac"},   {"opus", "opus"},
               {"ogg", "ogg"},   {"vorbis", "ogg"}, {"wavpack", "wv"}, {"wav", "wav"},   {"aiff", "aiff"},
               {"x-ape", "ape"}, {"ape", "ape"}};
    char tmp[SBA_TEXT];
    unsigned i;
    sp_text(dst, SBA_SUFFIX, obj, end, "suffix");
    if (!dst[0]) {
        tmp[0] = 0;
        if (sbn_member_truncate(obj, end, "contentType", tmp, 48) > 0 && tmp[0]) {
            sp_lower(tmp);
            for (i = 0; i < sizeof map / sizeof map[0]; ++i)
                if (sp_has(tmp, map[i].mime)) {
                    const char *s = map[i].suffix;
                    unsigned k;
                    for (k = 0; s[k]; ++k) dst[k] = s[k];
                    dst[k] = 0;
                    return;
                }
        }
    }
    if (!dst[0]) {
        unsigned n, dot = 0, k;
        tmp[0] = 0;
        if (sbn_member(obj, end, "path", tmp, sizeof tmp, (unsigned *)0) != 1) return;
        for (n = 0; tmp[n]; ++n)
            if (tmp[n] == '/')
                dot = 0;
            else if (tmp[n] == '.')
                dot = n + 1;
        if (!dot || sbn_len(tmp + dot) >= SBA_SUFFIX) return;
        for (k = 0; tmp[dot + k]; ++k) dst[k] = tmp[dot + k];
        dst[k] = 0;
    }
    sp_lower(dst);
}

/* ---- the response and its containers ---- */

/* The "subsonic-response" object of a complete ok body, NULL (with *err set) otherwise: 40 / 41 are SBA_AUTH, 70 SBA_NOTFOUND, any other body SBA_PARSE. */
static const char *sp_open(const char *json, unsigned n, const char **end, int *err) {
    const char *resp, *e;
    unsigned code = 0;
    char tmp[8];
    if (err) *err = SBA_PARSE;
    if (!json || !n) return 0;
    *end = json + n;
    if (sbn_response_ok(json, n)) {
        resp = sbn_object(sbn_ws(json, *end), *end, "subsonic-response");
        return resp;
    }
    resp = sbn_object(sbn_ws(json, *end), *end, "subsonic-response");
    e = resp ? sbn_object(resp, *end, "error") : 0;
    if (e && err && sbn_member(e, *end, "code", tmp, sizeof tmp, &code) == 1)
        *err = code == 40 || code == 41 ? SBA_AUTH : code == 70 ? SBA_NOTFOUND : SBA_PARSE;
    return 0;
}

typedef struct {
    const char *p, *end;
} sp_it_t;

/* The next object element of the array: its start in *o and its end in *oe; 0 at the end of the array (or a truncation). */
static int sp_next(sp_it_t *it, const char **o, const char **oe) {
    for (;;) {
        const char *p = sbn_ws(it->p, it->end), *e;
        if (p < it->end && *p == ',') p = sbn_ws(p + 1, it->end);
        if (p >= it->end || *p == ']') return 0;
        e = sbn_skip(p, it->end);
        if (!e) return 0;
        it->p = e;
        if (*p != '{') continue;
        *o = p;
        *oe = e;
        return 1;
    }
}

/* The array member `key` of the object `cont` of the response. 1 found (it set), 0 not there, -1 malformed. *head gets the container. */
static int sp_find(const char *resp, const char *end, const char *cont, const char *key, sp_it_t *it,
                   const char **head) {
    const char *c = sbn_object(resp, end, cont), *arr;
    int r;
    if (!c) return 0;
    *head = c;
    r = sbn_array_member(c, end, key, &arr);
    if (r <= 0) return r;
    it->p = arr;
    it->end = end;
    return 1;
}

/* ---- rows ---- */

static int sp_track(sba_track_t *t, const char *o, const char *e, const char *head, const char *he) {
    sp_zero(t, sizeof *t);
    if (!sp_id(t->id, o, e, "id")) return 0;
    sp_text(t->title, SBA_TEXT, o, e, "title");
    if (!t->title[0]) sp_text(t->title, SBA_TEXT, o, e, "name");
    sp_text(t->artist, SBA_TEXT, o, e, "artist");
    sp_text(t->album, SBA_TEXT, o, e, "album");
    sp_id(t->album_id, o, e, "albumId");
    sp_id(t->cover, o, e, "coverArt");
    sp_suffix(t->suffix, o, e);
    t->seconds = sp_num(o, e, "duration");
    t->track = sp_num(o, e, "track");
    t->disc = sp_num(o, e, "discNumber");
    t->year = sp_num(o, e, "year");
    t->size = sp_num(o, e, "size");
    t->bitrate = sp_num(o, e, "bitRate");
    t->sample_rate = sp_num(o, e, "samplingRate");
    t->bit_depth = sp_num(o, e, "bitDepth");
    t->created = sp_time(o, e, "created");
    t->starred = sp_flag(o, e, "starred");
    if (head) { /* getAlbum: what a song leaves out is the album's */
        if (!t->album_id[0]) sp_id(t->album_id, head, he, "id");
        if (!t->cover[0]) sp_id(t->cover, head, he, "coverArt");
        if (!t->year) t->year = sp_num(head, he, "year");
        if (!t->album[0]) sp_text(t->album, SBA_TEXT, head, he, "name");
        if (!t->artist[0]) sp_text(t->artist, SBA_TEXT, head, he, "artist");
    }
    return 1;
}

static int sp_album(sba_album_t *a, const char *o, const char *e, const char *head, const char *he) {
    sp_zero(a, sizeof *a);
    if (!sp_id(a->id, o, e, "id")) return 0;
    sp_text(a->name, SBA_TEXT, o, e, "name");
    if (!a->name[0]) sp_text(a->name, SBA_TEXT, o, e, "title");
    sp_text(a->artist, SBA_TEXT, o, e, "artist");
    sp_id(a->artist_id, o, e, "artistId");
    sp_id(a->cover, o, e, "coverArt");
    a->year = sp_num(o, e, "year");
    a->songs = sp_num(o, e, "songCount");
    a->seconds = sp_num(o, e, "duration");
    a->created = sp_time(o, e, "created");
    a->starred = sp_flag(o, e, "starred");
    if (head) { /* getArtist: the albums belong to the artist */
        if (!a->artist[0]) sp_text(a->artist, SBA_TEXT, head, he, "name");
        if (!a->artist_id[0]) sp_id(a->artist_id, head, he, "id");
    }
    return 1;
}

static int sp_artist(sba_artist_t *a, const char *o, const char *e) {
    sp_zero(a, sizeof *a);
    if (!sp_id(a->id, o, e, "id")) return 0;
    sp_text(a->name, SBA_TEXT, o, e, "name");
    sp_id(a->cover, o, e, "coverArt");
    a->albums = sp_num(o, e, "albumCount");
    a->starred = sp_flag(o, e, "starred");
    return 1;
}

static int sp_playlist(sba_playlist_t *p, const char *o, const char *e) {
    sp_zero(p, sizeof *p);
    if (!sp_id(p->id, o, e, "id")) return 0;
    sp_text(p->name, SBA_TEXT, o, e, "name");
    sp_id(p->cover, o, e, "coverArt");
    p->songs = sp_num(o, e, "songCount");
    p->seconds = sp_num(o, e, "duration");
    return 1;
}

/* ---- the parsers ---- */

int sba_parse_ping(const char *json, unsigned n, int *err) {
    const char *end;
    if (!sp_open(json, n, &end, err)) return -1;
    if (err) *err = SBA_OK;
    return 0;
}

int sba_parse_tracks(const char *json, unsigned n, sba_track_t *out, int max, int *err) {
    static const struct {
        const char *cont, *key;
    } where[] = {{"album", "song"},    {"playlist", "entry"},   {"searchResult3", "song"},
                 {"starred2", "song"}, {"randomSongs", "song"}, {"songsByGenre", "song"}};
    const char *end, *resp, *head = 0, *o, *oe;
    sp_it_t it;
    int count = 0, r, k;
    if (!(resp = sp_open(json, n, &end, err))) return -1;
    if (err) *err = SBA_OK;
    for (k = 0; k < (int)(sizeof where / sizeof where[0]); ++k) {
        r = sp_find(resp, end, where[k].cont, where[k].key, &it, &head);
        if (r < 0) {
            if (err) *err = SBA_PARSE;
            return -1;
        }
        if (r > 0) break;
        if (head) break; /* the container is there without the array: an empty answer */
    }
    if (k == (int)(sizeof where / sizeof where[0]) || !out || max <= 0 || !head || r <= 0) return 0;
    while (count < max && sp_next(&it, &o, &oe))
        if (sp_track(&out[count], o, oe, k == 0 ? head : 0, end)) ++count;
    return count;
}

int sba_parse_albums(const char *json, unsigned n, sba_album_t *out, int max, int *err) {
    static const struct {
        const char *cont, *key;
    } where[] = {{"albumList2", "album"}, {"artist", "album"}, {"searchResult3", "album"}, {"starred2", "album"}};
    const char *end, *resp, *head = 0, *o, *oe;
    sp_it_t it;
    int count = 0, r = 0, k;
    if (!(resp = sp_open(json, n, &end, err))) return -1;
    if (err) *err = SBA_OK;
    for (k = 0; k < (int)(sizeof where / sizeof where[0]); ++k) {
        head = 0;
        r = sp_find(resp, end, where[k].cont, where[k].key, &it, &head);
        if (r < 0) {
            if (err) *err = SBA_PARSE;
            return -1;
        }
        if (r > 0 || head) break;
    }
    if (k == (int)(sizeof where / sizeof where[0]) || !out || max <= 0 || r <= 0) return 0;
    while (count < max && sp_next(&it, &o, &oe))
        if (sp_album(&out[count], o, oe, k == 1 ? head : 0, end)) ++count;
    return count;
}

int sba_parse_artists(const char *json, unsigned n, sba_artist_t *out, int max, int *err) {
    const char *end, *resp, *head = 0, *o, *oe;
    sp_it_t it, in;
    int count = 0, r;
    if (!(resp = sp_open(json, n, &end, err))) return -1;
    if (err) *err = SBA_OK;
    if (!out || max <= 0) return 0;
    r = sp_find(resp, end, "artists", "index", &it, &head);
    if (r < 0) {
        if (err) *err = SBA_PARSE;
        return -1;
    }
    if (r > 0) { /* getArtists: index[] of letters, each with artist[] */
        while (count < max && sp_next(&it, &o, &oe)) {
            const char *arr;
            int q = sbn_array_member(o, oe, "artist", &arr);
            if (q < 0) {
                if (err) *err = SBA_PARSE;
                return -1;
            }
            if (q == 0) continue;
            in.p = arr;
            in.end = oe;
            while (count < max && sp_next(&in, &o, &oe))
                if (sp_artist(&out[count], o, oe)) ++count;
            if (count >= max) break;
        }
        return count;
    }
    if (head) return 0;
    r = sp_find(resp, end, "searchResult3", "artist", &it, &head);
    if (r == 0 && !head) r = sp_find(resp, end, "starred2", "artist", &it, &head);
    if (r < 0) {
        if (err) *err = SBA_PARSE;
        return -1;
    }
    if (r == 0) return 0;
    while (count < max && sp_next(&it, &o, &oe))
        if (sp_artist(&out[count], o, oe)) ++count;
    return count;
}

int sba_parse_playlists(const char *json, unsigned n, sba_playlist_t *out, int max, int *err) {
    const char *end, *resp, *head = 0, *o, *oe;
    sp_it_t it;
    int count = 0, r;
    if (!(resp = sp_open(json, n, &end, err))) return -1;
    if (err) *err = SBA_OK;
    r = sp_find(resp, end, "playlists", "playlist", &it, &head);
    if (r < 0) {
        if (err) *err = SBA_PARSE;
        return -1;
    }
    if (r == 0 || !out || max <= 0) return 0;
    while (count < max && sp_next(&it, &o, &oe))
        if (sp_playlist(&out[count], o, oe)) ++count;
    return count;
}
