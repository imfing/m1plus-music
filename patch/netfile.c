/* The rules of a file download, shared by its callers (patch/netfile.h; docs/modules/network.md): what a response's headers say about a resumed file, the room on the card, a file with a size limit, and
 * the rename that makes a .part the file. No libcurl here: patch/net.c runs the request, the caller's write and header callbacks hand the bytes and the lines over.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "netfile.h"

static int net_lower(unsigned c) { return c >= 'A' && c <= 'Z' ? (int)(c + 32) : (int)c; }

/* s starts with prefix (lower case), whatever the case of s. */
static int net_starts(const char *s, const char *prefix) {
    for (; *prefix; ++s, ++prefix)
        if (net_lower((unsigned char)*s) != *prefix) return 0;
    return 1;
}

int net_text_type(const char *type) {
    return type &&
           (net_starts(type, "text/") || net_starts(type, "application/json") || net_starts(type, "application/xml") ||
            net_starts(type, "application/xhtml") || net_starts(type, "application/problem+"));
}

/* ---------------------------------------------------------------------------
 * A response's headers
 */

int net_strong_etag(const char *value) {
    unsigned i, n = 0;
    while (value[n]) ++n;
    if (n < 2 || n >= 128 || value[0] != '"' || value[n - 1] != '"') return 0;
    for (i = 1; i + 1 < n; ++i)
        if ((unsigned char)value[i] < 33 || value[i] == '"' || (unsigned char)value[i] == 127) return 0;
    return 1;
}

/* The value of the header line "key:" (key in lower case), trimmed, into out. 1 matched (out empty when the value did not fit cap), 0 another header. */
static int net_head_value(const char *line, unsigned n, const char *key, char *out, unsigned cap) {
    unsigned i = 0, end = n, length;
    while (key[i]) {
        if (i >= n || net_lower((unsigned char)line[i]) != key[i]) return 0;
        ++i;
    }
    while (i < end && (line[i] == ' ' || line[i] == '\t')) ++i;
    while (end > i && (line[end - 1] == '\r' || line[end - 1] == '\n' || line[end - 1] == ' ' || line[end - 1] == '\t'))
        --end;
    length = end - i;
    out[0] = 0;
    if (length >= cap) return 1;
    memcpy(out, line + i, length);
    out[length] = 0;
    return 1;
}

/* Decimal digits at line[*at] into *v: the count of digits, 0 for none or a number over 63 bits. */
static unsigned net_digits(const char *line, unsigned n, unsigned *at, long long *v) {
    unsigned i = *at, digits = 0;
    long long x = 0;
    while (i < n && line[i] >= '0' && line[i] <= '9') {
        unsigned digit = (unsigned)(line[i++] - '0');
        if (x > 922337203685477580LL || (x == 922337203685477580LL && digit > 7)) return 0;
        x = x * 10 + digit;
        ++digits;
    }
    *at = i, *v = x;
    return digits;
}

int net_head_line(net_head_t *h, const char *line, unsigned n) {
    char value[80];
    unsigned i;
    long long start, end, total;
    if (n >= 5 && net_starts(line, "http/")) { /* a status line: the headers of another response begin */
        h->range_seen = 0;
        h->range_start = h->range_end = h->range_total = -1;
        h->status = 0;
        h->etag[0] = h->type[0] = 0;
        for (i = 5; i < n && line[i] != ' '; ++i) {
        }
        if (i + 3 < n && line[i + 1] >= '0' && line[i + 1] <= '9' && line[i + 2] >= '0' && line[i + 2] <= '9' &&
            line[i + 3] >= '0' && line[i + 3] <= '9')
            h->status = (line[i + 1] - '0') * 100 + (line[i + 2] - '0') * 10 + line[i + 3] - '0';
        return 2;
    }
    if ((n == 2 && line[0] == '\r' && line[1] == '\n') || (n == 1 && line[0] == '\n')) return 1;
    if (net_head_value(line, n, "etag:", h->etag, sizeof h->etag)) {
        if (!net_strong_etag(h->etag)) h->etag[0] = 0;
        return 0;
    }
    if (net_head_value(line, n, "content-type:", h->type, sizeof h->type)) return 0;
    if (!net_head_value(line, n, "content-range:", value, sizeof value)) return 0;
    h->range_seen = 1;
    h->range_start = h->range_end = h->range_total = -1;
    n = 0;
    while (value[n]) ++n;
    if (n < 6 || !net_starts(value, "bytes ") || value[6] == '*') return 0; /* "bytes <start>-<end>/<total or *>" */
    i = 6;
    if (!net_digits(value, n, &i, &start) || i >= n || value[i++] != '-') return 0;
    if (!net_digits(value, n, &i, &end) || i >= n || value[i++] != '/' || end < start) return 0;
    h->range_start = start, h->range_end = end;
    if (i < n && value[i] != '*') h->range_total = net_digits(value, n, &i, &total) && total > end ? total : -2;
    return 0;
}

int net_head_resumes(const net_head_t *h, long long offset) {
    return h->status == 206 && h->range_seen && h->range_start == offset && h->range_end >= h->range_start &&
           h->range_total > 0 && h->range_end == h->range_total - 1;
}

int net_if_range(char *line, unsigned size, void *list[2], const char *etag) {
    if (!net_strong_etag(etag) || snprintf(line, size, "If-Range: %s", etag) >= (int)size) return 0;
    list[0] = line, list[1] = (void *)0; /* libcurl's curl_slist: {char *data; next} */
    return 1;
}

/* ---------------------------------------------------------------------------
 * A file on the card
 */

int net_room(const char *path, unsigned need_kb) {
    unsigned kb = 0;
    if (!m1_free_kb(path, &kb)) return NET_W_CARD;
    return kb <= NET_RESERVE_KB || kb - NET_RESERVE_KB < need_kb ? NET_W_SPACE : NET_W_NONE;
}

unsigned net_file_write(net_file_t *f, const char *data, unsigned n) {
    if (!n) return 0;
    if (f->cap && (f->written > (long long)f->cap || n > f->cap - (unsigned)f->written)) return f->why = NET_W_CAP, 0;
    if ((long long)n > 0x7fffffffffffffffLL - f->written) return f->why = NET_W_SPACE, 0;
    if (f->room && f->written - f->checked >= 1024 * 1024) {
        int why = net_room(f->room, 0);
        if (why) return f->why = why, 0;
        f->checked = f->written;
    }
    if (!m1_write_all(f->fd, data, n)) return f->why = NET_W_IO, 0;
    f->written += n;
    return n;
}

int net_file_close(net_file_t *f) {
    int ok = f->fd >= 0 && fsync(f->fd) == 0;
    if (f->fd >= 0 && close(f->fd)) ok = 0;
    f->fd = -1;
    return ok;
}

int net_sync_dir(const char *dir) {
    int fd = open(dir, O_RDONLY, 0), ok = fd >= 0 && fsync(fd) == 0;
    if (fd >= 0) close(fd);
    return ok;
}

int net_publish(const char *part, const char *final, const char *dir) {
    if (rename(part, final)) return 0;
    return net_sync_dir(dir) ? 1 : -1;
}
