/* Subsonic network layer (patch/sbnet.c): request plumbing shared by the Navidrome page and the
 * Subsonic data layer. It builds token-authenticated rest/<view>.view URLs, runs the libcurl GET
 * (HTTPS certificate checks always on, /etc/m1plus-cacert.pem), downloads to a .part file, and
 * walks Subsonic JSON. It keeps no UI or playback state; the app watches requests through the two
 * hooks given to sbn_init.
 */
#pragma once

#define SBN_RESPONSE_MAX \
    (4u << 20) /* the most a sink's body buffer holds (NUL included); a larger response fails the transfer */
#define SBN_RESPONSE_START (64u * 1024) /* its first size; it doubles when the body needs more */
#define SBN_E_INIT (-2) /* sbn_http: no curl handle or no sink, nothing was sent and no hook ran */
#define SBN_IDENTITY \
    544 /* bytes of the string that tells whose partial file a resume record belongs to, the NUL included */
/* sink->werr: the first write that failed stopped the transfer (CURLE_WRITE_ERROR); sbn_download also sets SBN_W_IO when the finished file could not be synced, closed or renamed */
enum { SBN_W_NONE = 0, SBN_W_RESPONSE, SBN_W_SPACE, SBN_W_CARD, SBN_W_IO };
#define SBN_E_URL (-3) /* sbn_get: the URL did not fit or the server is not an http(s) URL */

/* One server login. The strings are borrowed. auth is the login secret (sbn_auth_make): SBN_AUTH hex digits, the salt (16) then the token md5(password + salt) (32); sbnet never sees the password
 * after Sign In made the secret. */
#define SBN_AUTH 48
typedef struct {
    const char *base; /* http(s) server root, no trailing slash and no /rest */
    const char *user;
    const char *auth;
} sbn_server_t;
int sbn_auth_ok(const char *auth); /* 1 for a well-formed secret */
int sbn_auth_make(
    char *out,
    const char
        *password); /* the secret of a password into out (SBN_AUTH + 1 bytes), with a fresh random salt; 0 or -1 */

/* One transfer's destination and result. A sink with fd < 0 collects the body in data (heap, cap
 * bytes, NUL terminated, used bytes; sbn_http allocates it SBN_RESPONSE_START and doubles it up to
 * SBN_RESPONSE_MAX as the body arrives; it is kept for the next transfer); with fd >= 0 the body is
 * written to that file and data stays NULL. Prepare it with sbn_sink_reset,
 * give the memory back with sbn_sink_trim / sbn_sink_free. Heap-allocate it (calloc). */
typedef struct {
    char *data;
    unsigned cap;
    char content_type[64];
    unsigned char prefix[8]; /* the first body bytes of a file transfer, for sniffing the type */
    unsigned prefix_used;
    unsigned used;
    int fd;
    int curl_result; /* the CURLcode of the transfer */
    long http_status;
    long long content_length;
    long long range_start, range_end, range_total; /* Content-Range of a 206; -1 unknown, total -2 malformed */
    int range_seen;
    long long written, last_check;
    long long resume_offset; /* where a resumed download continues: sbn_download sets it, the progress hook reads it */
    /* An audio file transfer only (sbn_download sets audio): a body is written only after the headers say it is the audio we asked for, and a resumed one only if its strong ETag still
     * identifies the saved .part file (patch/sbnet.c). */
    int audio, headers_ok, header_status, body_started, resume_saved;
    int werr; /* why the body write stopped the transfer (SBN_W_*), 0 when it did not */
    char etag[128], resume_etag[128]; /* the response's strong ETag; the one saved with the .part file */
    const char *validator_path,
        *identity; /* the resume record's file; who the .part belongs to (server, user, track): borrowed from sbn_download's caller */
} sbn_sink_t;

/* The progress hook (libcurl's transfer-info callback; ctx is the sink; non-zero aborts) and the
 * observer called after every finished transfer (sink->curl_result and ->http_status are set). */
typedef int (*sbn_xfer_fn)(void *sink, long long total, long long now, long long up_total, long long up_now);
typedef void (*sbn_after_fn)(const sbn_sink_t *sink);

/* Initialise libcurl once and register the two hooks (either may be NULL). 1 on success. */
int sbn_init(sbn_xfer_fn xfer, sbn_after_fn after);

/* Clear a sink for a new in-memory transfer (fd = -1); the body buffer, if it has one, is kept. */
void sbn_sink_reset(sbn_sink_t *sink);
/* Free the body buffer when it is larger than keep bytes (sbn_sink_free: always). The body is gone: call it between transfers. */
void sbn_sink_trim(sbn_sink_t *sink, unsigned keep);
void sbn_sink_free(sbn_sink_t *sink);

/* Build the authenticated URL of a Subsonic view ("ping", "search3", "getAlbum", "stream",
 * "download", "getCoverArt", ...): <base>/rest/<view>.view?u=..&t=<md5(password+salt)>&s=<salt>
 * &v=1.16.1&c=m1plus-music&f=json, the token and salt being the login secret's (srv.auth), so no password is needed or kept.
 * id (may be NULL) is added as &id=<escaped>; "stream" gets &format=raw so the server does not
 * transcode; extra (may be NULL) is appended verbatim, build it with sbn_urlenc (e.g. "&size=240").
 * 0 on success, -1 on bad input or when out is too small. */
int sbn_url(char *out, unsigned cap, sbn_server_t srv, const char *view, const char *id, const char *extra);

/* Percent-escape s into out at offset used (RFC 3986 unreserved characters pass); returns the new
 * length, or 0 when s is NULL or the result does not fit. */
unsigned sbn_urlenc(char *out, unsigned cap, unsigned used, const char *s);

/* GET a URL (timeout in seconds, 0 = none; range like "1048576-" or NULL) into sink. 0 on success
 * (HTTP 2xx), -1 when the transfer failed, SBN_E_INIT when it could not start. */
int sbn_http(const char *url, sbn_sink_t *sink, long timeout, const char *range);

/* Reset sink, build a view's URL (sbn_url) and GET it with a 180 s limit. The JSON body is in
 * sink->data/used on success; check it with sbn_response_ok. 0 on success, SBN_E_URL when the URL
 * could not be built, else as sbn_http. */
int sbn_get(sbn_server_t srv, const char *view, const char *id, const char *extra, sbn_sink_t *sink);

/* Download url to the file final through the partial file part, resuming a partial one; dir_path is
 * the folder to sync after the rename (rules and *resumable_out: see patch/sbnet.c). identity names
 * who the partial file is for (server, user and track, one string under SBN_IDENTITY bytes; NULL: no
 * resume, a failed transfer drops its partial file). Needs 32 MB free on the card. 1 on success,
 * -1 otherwise. */
int sbn_download(const char *url, const char *part, const char *final, const char *dir_path, const char *identity,
                 sbn_sink_t *sink, int *resumable_out);

/* write() all of data; 1 on success. */
int sbn_write_all(int fd, const void *data, unsigned size);

/* MD5 of n bytes (n <= 247, what its 256-byte block buffer holds; sbn_auth_make passes up to 207), as used by the token. */
void sbn_md5(const unsigned char *msg, unsigned n, unsigned char out[16]);

/* Small string helpers shared with the page. */
unsigned sbn_len(const char *s);
int sbn_eq(const char *a, unsigned n, const char *b); /* a[0..n) equals the whole string b */
int sbn_prefix(const char *value, const char *prefix);
int sbn_ascii_lower(unsigned c);
int sbn_https(const char *url);
int sbn_http_url(const char *url); /* http:// or https:// */

/* JSON walker. Every call is bounded by end and never reads past it; obj and p point at a value
 * (a '{' for an object). Absent keys and malformed text give 0, NULL or -1 as noted; none abort. */
const char *sbn_ws(const char *p, const char *end); /* skip white space */
const char *sbn_skip(const char *p, const char *end); /* just past the value at p, NULL if unterminated */
/* Decode the string at p (UTF-8, backslash-u escapes) into out; returns just past it, NULL when it
 * does not fit in cap or is unterminated. out NULL or cap 0 only skips it. */
const char *sbn_string(const char *p, const char *end, char *out, unsigned cap);
const char *sbn_object(const char *obj, const char *end, const char *key); /* the '{' of member key of obj, or NULL */
/* Member key of the object obj: a string goes to out, a number to *num (out[0] = 0), true/false/null
 * leave both empty. 1 found, 0 absent or odd type, -1 string too long for cap. */
int sbn_member(const char *obj, const char *end, const char *key, char *out, unsigned cap, unsigned *num);
/* As sbn_member for strings, but a too-long string is cut at a UTF-8 boundary instead of failing. */
int sbn_member_truncate(const char *obj, const char *end, const char *key, char *out, unsigned cap);
/* Find the array member key of obj (checked structurally, so a title containing "song": cannot
 * match); *array is just past its '['. 1 found, 0 absent, -1 malformed or duplicate key. */
int sbn_array_member(const char *obj, const char *end, const char *key, const char **array);
/* 1 when json[0..n) is one complete object whose "subsonic-response" has status "ok". */
int sbn_response_ok(const char *json, unsigned n);
