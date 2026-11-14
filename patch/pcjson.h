/* A small, bounded JSON extractor for the iTunes search and lookup answers (patch/pcjson.c; docs/modules/podcasts.md "Search").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * demo has no JSON library and the answer is untrusted, so this is no parser: it walks the text once, without recursion and without allocating, finds the top-level "results" array and takes
 * six members of each object in it (collectionId, collectionName, artistName, feedUrl, artworkUrl100, artworkUrl600); everything else is skipped by its brackets and quotes. Every read is bounded by the
 * length given; every write by the field's size. Strings are decoded to UTF-8 (escapes, \uXXXX with surrogate pairs) and cut on a character boundary.
 */
#pragma once

#define PJ_MAX 25 /* results kept (the request asks for 25) */
#define PJ_NAME 80 /* a show's name, UTF-8 bytes with the NUL (cut before a continuation byte) */
#define PJ_AUTHOR 56
#define PJ_ART \
    320 /* the artwork url; one that does not fit is no url (""). Podcast Index names the feed's own picture, whose address is often 230 to 250 bytes */
#define PJ_DEPTH 32 /* nesting skipped; a deeper value ends the walk */

typedef struct {
    unsigned id; /* collectionId, 0 = none (a larger number is 0xffffffff) */
    char name[PJ_NAME]; /* collectionName */
    char author[PJ_AUTHOR]; /* artistName */
    char feed[PC_URL]; /* feedUrl: "" = none, also for one longer than the field (a cut address is no address) */
    char art[PJ_ART]; /* artworkUrl100, "" likewise */
    char art6
        [PJ_ART]; /* artworkUrl600 (a baseline 600 x 600 JPEG): the preview's picture when the feed's cannot be decoded; "" likewise (Deezer's: none) */
} pj_result_t;

/* The objects of the top-level "results" array of the n bytes at json that have a collectionName or a feedUrl, at most max, in order, into out. An object cut short by the end of the text is
 * not kept. Returns how many (0 for an empty array), or -1 when there is no "results" array (not an answer of the store). Never reads outside json[0, n) or writes outside out[0, max). */
int pj_results(const char *json, unsigned n, pj_result_t *out, int max);

#define PJ_CHART 25 /* chart rows kept (the requests ask for the top 25) */

typedef struct {
    char id
        [16]; /* the show's Apple id as digits (they pass 32 bits): a show chart's "id", an episode chart's "/id<digits>" of its "url" (the episode's own id is another number); "" = none */
    char name[PJ_NAME]; /* name: the show's, or the episode's title */
    char author[PJ_AUTHOR]; /* artistName: the show's author, or for an episode its show */
    char art[PJ_ART]; /* artworkUrl100 */
    char eid
        [16]; /* an episode row's own id (its "id", digits; the episode's trackId in the lookup): "" for a show row */
} pj_chart_t;

/* Apple's top charts (https://rss.marketingtools.apple.com/api/v2/<cc>/podcasts/top/25/podcasts.json, .../podcast-episodes.json): the objects of "results" inside the top-level "feed" object, in order (rank = position),
 * at most max, into out; episodes 1 takes the id from the "url". Returns how many (0 for an empty array), or -1 when there is no feed.results array. Never reads outside json[0, n) or writes outside out[0, max). */
int pj_chart(const char *json, unsigned n, int episodes, pj_chart_t *out, int max);

#define PJ_EPS 20 /* episode records kept from a lookup (the request asks for 20) */
#define PJ_DATE 32 /* a releaseDate (ISO 8601 text) */

typedef struct {
    char id[16]; /* trackId as digits ("" = none) */
    char url
        [PC_URL]; /* episodeUrl, the enclosure address the store has: "" = none, also for one longer than the field */
    char name[PJ_NAME]; /* trackName: the episode's title */
    char date[PJ_DATE]; /* releaseDate, e.g. 2026-11-04T13:17:00Z: "" = none */
} pj_ep_t;

/* The episode records of the top-level "results" array of an episode lookup (https://itunes.apple.com/lookup?id=<show>&entity=podcastEpisode&limit=20&country=<cc>): the objects that have a
 * trackId, at most max, in order, into out. The show's own record has the show's id, which no episode has. Returns how many (0 for an empty array), or -1 when there is no "results" array.
 * Never reads outside json[0, n) or writes outside out[0, max). */
int pj_episodes(const char *json, unsigned n, pj_ep_t *out, int max);

/* The same for Deezer's album search (https://api.deezer.com/search/album): the objects of the top-level "data" array, with title as name, artist.name as author, cover_medium (250 px) as art and id. -1: no "data" array. */
int pj_deezer(const char *json, unsigned n, pj_result_t *out, int max);
/* The same for Deezer's artist search (https://api.deezer.com/search/artist): name as name and, not cut, as feed ("" for one longer than the field: the match of a name is made on it), picture_medium (250 px) as art and nb_fan (the artist's followers) as id; author is "". -1: no "data" array. */
int pj_deezer_artists(const char *json, unsigned n, pj_result_t *out, int max);
/* The same for NetEase Cloud Music's artist search (https://music.163.com/api/search/get?type=100, not a documented service): the objects of the "artists" array of the top-level "result" object, with name as name and feed
 * (as Deezer's artist), img1v1Url (the square picture) as art, picUrl as art6 and fansSize as id. 0 for a "result" with no "artists" (the answer when nothing is found); -1: no "result" object (an error answer). */
int pj_netease_artists(const char *json, unsigned n, pj_result_t *out, int max);

typedef struct {
    char title[PJ_NAME], artist[PJ_AUTHOR], album[PJ_NAME]; /* trackName, artistName, albumName */
    unsigned secs; /* duration in whole seconds, 0 = none */
    int synced; /* the text given is syncedLyrics (else plainLyrics) */
} pj_lrc_t;

/* LRCLIB's answer (https://lrclib.net/api/get: one object; /api/search: an array of them), n bytes at json: every record that has lyrics (synced and non blank, else plain and non blank; a record
 * with neither is skipped), in order, as fn(ctx, record, text) with the text decoded (line feeds stay line feeds, carriage returns are dropped, a text that does not fit cap ends at its last whole
 * line); fn returns 0 to stop. a and b are two scratch buffers of cap + 1 bytes (the decoded texts of the record being read); the text passed is one of them, valid during the call only. Returns the
 * records passed to fn, or -1 when the answer is not an object or an array. An object cut short by the end of the text is not passed. */
int pj_lrc_each(const char *json, unsigned n, unsigned cap, char *a, char *b,
                int (*fn)(void *, const pj_lrc_t *, const char *), void *ctx);

#define PJ_M_NONE 0 /* no such member, or the text is not one whole object */
#define PJ_M_STRING 1 /* a string: decoded into dst */
#define PJ_M_TRUE 2
#define PJ_M_FALSE 3
#define PJ_M_OTHER 4 /* a number, null, an object or an array */

/* The member called want (under 15 bytes) of the top-level object of the n bytes at json (ListenBrainz's validate-token answer): one PJ_M_* kind, a string's text decoded into dst
 * (cap bytes with the NUL, cut on a character boundary; "" for every other kind). The first member of that name counts. The object must be whole: a text that ends before its closing
 * brace, or is not an object, has no member. Never reads outside json[0, n) or writes outside dst[0, cap). */
int pj_member(const char *json, unsigned n, const char *want, char *dst, unsigned cap);

/* pj_member that also gives the member's own text (Last.fm's answers nest: session.key, scrobbles.scrobble[i].ignoredMessage.code): *val the value's first byte inside json and *len its
 * length (a string with its quotes, an object or an array with its brackets, a number's digits), so that it can be read again as an object (pj_member, pj_span) or an array (pj_next).
 * dst may be NULL (a string is then not decoded), val may be NULL. *val and *len are set only when a kind other than PJ_M_NONE is returned. */
int pj_span(const char *json, unsigned n, const char *want, char *dst, unsigned cap, const char **val, unsigned *len);

/* The elements of the array that is the n bytes at json, one a call: *at is 0 before the first and is moved on; 1 with *val / *len the element's text, 0 at the array's end, when the
 * text is no array, or when it ends inside an element. */
int pj_next(const char *json, unsigned n, unsigned *at, const char **val, unsigned *len);
