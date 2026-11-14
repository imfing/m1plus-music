/* One HTTP request over libcurl's easy interface (patch/net.h; docs/modules/network.md). demo imports the easy interface only (no multi handle), so a request blocks its thread.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "curlopts.h"
#include "net.h"

#define NET_AGENT \
    "M1PlusMusic/1.0 (https://github.com/imfing/m1plus-mod)" /* the app's name and address (LRCLIB asks for them) */

int net_init(void) { return curl_global_init(CURL_GLOBAL_ALL) == CURLE_OK; }

long net_status(const net_req_t *r) {
    long code = 0;
    if (r->h) curl_easy_getinfo(r->h, CURLINFO_RESPONSE_CODE, &code);
    return code;
}

const char *net_type(const net_req_t *r) {
    const char *type = (const char *)0;
    if (r->h) curl_easy_getinfo(r->h, CURLINFO_CONTENT_TYPE, &type);
    return type;
}

/* A libcurl string into the caller's buffer: "" when there is none; one that does not fit is cut (a type) or dropped whole (an address: half of one is another address). */
static void net_copy(char *out, unsigned size, const char *s, int cut) {
    unsigned n = 0;
    if (!out || !size) return;
    out[0] = 0;
    if (!s) return;
    while (s[n]) ++n;
    if (n >= size) {
        if (!cut) return;
        n = size - 1;
    }
    memcpy(out, s, n);
    out[n] = 0;
}

static int net_is_https(const char *url) {
    return url && (url[0] | 32) == 'h' && (url[1] | 32) == 't' && (url[2] | 32) == 't' && (url[3] | 32) == 'p' &&
           (url[4] | 32) == 's' && url[5] == ':';
}

#define SET(option, value) bad |= curl_easy_setopt(h, option, value)

int net_perform(net_req_t *r) {
    void *h = curl_easy_init();
    const char *s = (const char *)0;
    unsigned f = r->flags;
    long proto = f & NET_HTTPS ? CURLPROTO_HTTPS : CURLPROTO_HTTP_HTTPS;
    int bad = 0;
    r->http = 0, r->filetime = -1, r->length = -1;
    net_copy(r->type, r->type_size, s, 1);
    net_copy(r->loc, r->loc_size, s, 0);
    if (!h) return r->rc = NET_NOHANDLE;
    SET(CURLOPT_URL, r->url);
    SET(CURLOPT_WRITEFUNCTION, r->write);
    SET(CURLOPT_WRITEDATA, r->wdata);
    if (r->header) {
        SET(CURLOPT_HEADERFUNCTION, r->header);
        SET(CURLOPT_HEADERDATA, r->hdata);
    }
    if (r->xfer) {
        SET(CURLOPT_NOPROGRESS, 0L);
        SET(CURLOPT_XFERINFOFUNCTION, r->xfer);
        SET(CURLOPT_XFERINFODATA, r->xdata);
    }
    if (r->err) SET(CURLOPT_ERRORBUFFER, r->err);
    if (f & NET_FAIL) SET(CURLOPT_FAILONERROR, 1L);
    if (r->low_limit) {
        SET(CURLOPT_LOW_SPEED_LIMIT, (long)r->low_limit);
        SET(CURLOPT_LOW_SPEED_TIME, (long)r->low_time);
    }
    SET(CURLOPT_NOSIGNAL, 1L); /* a thread: no SIGALRM resolver time-outs */
    SET(CURLOPT_FOLLOWLOCATION, f & NET_NOFOLLOW ? 0L : 1L);
    SET(CURLOPT_MAXREDIRS, (long)r->redirs);
    SET(CURLOPT_PROTOCOLS, proto); /* (a redirect to file:// or ftp:// is refused) */
    SET(CURLOPT_REDIR_PROTOCOLS, f & NET_NODOWNGRADE && net_is_https(r->url) ? (long)CURLPROTO_HTTPS : proto);
    SET(CURLOPT_CONNECTTIMEOUT, (long)r->connect_s);
    SET(CURLOPT_TIMEOUT, (long)r->total_s);
    SET(CURLOPT_USERAGENT, NET_AGENT);
    SET(CURLOPT_ACCEPT_ENCODING, f & NET_NOENCODING ? (const char *)0 : f & NET_IDENTITY ? "identity" : "");
    SET(CURLOPT_CAINFO, M1_CA);
    if (f & NET_HEAD) SET(CURLOPT_NOBODY, 1L);
    if (f & NET_FILETIME) SET(CURLOPT_FILETIME, 1L);
    if (r->since) {
        SET(CURLOPT_TIMECONDITION, (long)CURL_TIMECOND_IFMODSINCE);
        SET(CURLOPT_TIMEVALUE, r->since);
    }
    if (r->range) SET(CURLOPT_RANGE, r->range);
    if (r->headers) SET(CURLOPT_HTTPHEADER, r->headers);
    r->h = h;
    r->rc = bad ? CURLE_FAILED_INIT : curl_easy_perform(h); /* an option libcurl refused: nothing is sent */
    if (curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &r->http) != CURLE_OK) r->http = 0;
    if (curl_easy_getinfo(h, CURLINFO_CONTENT_LENGTH_DOWNLOAD_T, &r->length) != CURLE_OK) r->length = -1;
    if (f & NET_FILETIME) curl_easy_getinfo(h, CURLINFO_FILETIME, &r->filetime);
    if (r->type && curl_easy_getinfo(h, CURLINFO_CONTENT_TYPE, &s) == CURLE_OK) net_copy(r->type, r->type_size, s, 1);
    s = (const char *)0;
    if (r->loc && curl_easy_getinfo(h, CURLINFO_REDIRECT_URL, &s) == CURLE_OK) net_copy(r->loc, r->loc_size, s, 0);
    r->h = (void *)0;
    curl_easy_cleanup(h);
    return r->rc;
}

/* ---------------------------------------------------------------------------
 * What a result means
 */

int net_tls(int rc) {
    if (rc == CURLE_SSL_CACERT_BADFILE) return 2;
    return rc == CURLE_SSL_CACERT || rc == CURLE_SSL_CONNECT_ERROR || rc == CURLE_PEER_FAILED_VERIFICATION ||
           rc == CURLE_SSL_CERTPROBLEM || rc == CURLE_SSL_CIPHER || rc == CURLE_SSL_ISSUER_ERROR;
}

int net_http_passing(long http) { return http >= 500 || http == 408 || http == 429; }
