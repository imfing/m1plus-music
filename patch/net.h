/* One HTTP request (patch/net.c): the only place of the payload that makes, sets up, runs and frees a libcurl easy handle. Podcasts and the jobs of its worker (patch/pcnet.c), the radio
 * (patch/radio.c) and Subsonic (patch/sbnet.c) fill a net_req_t and call net_perform from their own thread; what the answer means (a feed, JSON, a picture, a file on the card), the
 * queues and the threads stay theirs. docs/modules/network.md.
 *
 * Every request: no signals, http(s) only, the app's user agent, the firmware's CA bundle with verification ON (no SSL_VERIFYPEER / SSL_VERIFYHOST option is ever set: libcurl's
 * defaults check the peer and the host name).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

typedef unsigned (*net_write_fn)(char *data, unsigned size, unsigned nmemb, void *user);
/* libcurl's transfer-info callback (about once a second, and with every chunk), 64-bit counts; non-zero aborts the transfer (CURLE_ABORTED_BY_CALLBACK): a request's Cancel. */
typedef int (*net_xfer_fn)(void *user, long long dltotal, long long dlnow, long long ultotal, long long ulnow);

enum {
    NET_FAIL =
        1, /* an HTTP code of 400 or more fails the request (CURLE_HTTP_RETURNED_ERROR) instead of handing over the error page */
    NET_NOFOLLOW = 2, /* a redirect is the answer (its address into loc), not followed */
    NET_HEAD = 4, /* headers only */
    NET_HTTPS = 8, /* https only, the address and every redirect */
    NET_NODOWNGRADE = 16, /* an https address is never redirected to http */
    NET_FILETIME = 32, /* the answer's Last-Modified into filetime */
    NET_IDENTITY = 64, /* the body as it is stored ("identity"): a range of an encoded body would not resume */
    NET_NOENCODING =
        128, /* no Accept-Encoding at all (default: every encoding libcurl has; gzip makes a 3 MB feed 400 kB) */
};

#define NET_NOHANDLE (-1) /* net_perform: libcurl gave no handle, nothing was sent */

typedef struct net_req {
    /* asked (zero the record first; url and write are needed, the rest is optional) */
    const char *url;
    net_write_fn write; /* the body */
    void *wdata;
    net_write_fn header; /* each header line, or 0 */
    void *hdata;
    net_xfer_fn xfer; /* progress and Cancel, or 0 */
    void *xdata;
    char *err; /* libcurl's words for a failure (160 bytes), or 0 */
    const char *range; /* "from-" of a resumed file, or 0 */
    void *headers; /* extra request headers, a curl_slist ({char *data; next}), or 0 */
    char *type; /* the answer's Content-Type goes here (type_size bytes, "" when none), or 0 */
    char *loc; /* with NET_NOFOLLOW: the redirect's address (loc_size bytes, "" when none or too long), or 0 */
    unsigned type_size, loc_size;
    long since; /* If-Modified-Since, seconds since 1970 (a 304 with no body when not newer); 0: no condition */
    int redirs, connect_s; /* redirect hops; seconds to connect */
    int total_s; /* seconds for the whole request, 0: no limit */
    int low_limit, low_time; /* a stall: under low_limit bytes a second for low_time seconds; 0: no stall check */
    unsigned flags; /* NET_* */
    /* answered */
    void *h; /* the handle while the request runs (net_status, net_type from a callback) */
    int rc; /* libcurl's result (CURLE_*, patch/curlopts.h), or NET_NOHANDLE */
    long http; /* the HTTP status, 0 when none came */
    long filetime; /* NET_FILETIME: seconds since 1970, -1 when the server sent none */
    long long length; /* the length the server announced, -1 when it gave none */
} net_req_t;

/* --- What a result means (the callers map these to their own codes) --- */

/* libcurl's result is a TLS failure: 0 no, 1 the certificate was refused (the peer, the host name, the chain, the handshake), 2 the CA bundle is missing or unreadable. */
int net_tls(int rc);
/* An HTTP status that may pass: the server's own trouble (5xx), 408 and 429. */
int net_http_passing(long http);

/* libcurl's global state, counted and not thread safe: call on the UI thread before a request's thread is made (stock's own curl_init did it once already). 1 on success. */
int net_init(void);
/* Run r on a handle of its own, on the calling thread, to its end; the handle is gone when this returns. Returns r->rc. */
int net_perform(net_req_t *r);
/* From a write or header callback of a running request: the HTTP status so far, and the Content-Type (owned by libcurl, NULL when none). */
long net_status(const net_req_t *r);
const char *net_type(const net_req_t *r);
