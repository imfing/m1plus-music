/* The rules of a file download (patch/netfile.c): the headers of a resumed file, the room on the card, a file with a size limit, the rename into place. Podcasts (patch/pcnet.c), Subsonic
 * (patch/sbnet.c) and the update package use them from their own callbacks; the request itself is patch/net.h's. docs/modules/network.md.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* A Content-Type that is no media file: text, JSON, XML (a login page, an error document). NULL and "" are not. */
int net_text_type(const char *type);

/* --- A response's headers, for a caller that resumes a file --- */

typedef struct net_head {
    int status; /* of the response these headers belong to (each response of a redirect chain starts again) */
    int range_seen; /* a Content-Range line came */
    long long range_start, range_end, range_total; /* -1 unknown; total -2 malformed */
    char etag[128]; /* the ETag when it is a strong one, else "" */
    char type[64];
} net_head_t;

/* One header line (a request's header callback hands it over, n bytes). 1 when it was the blank line that ends a response's headers, 2 for a status line (the record starts again), else 0. */
int net_head_line(net_head_t *h, const char *line, unsigned n);
/* A strong ETag (RFC 9110): a quoted string, no W/ prefix, nothing inside that could break a header line; under 128 bytes. */
int net_strong_etag(const char *value);
/* The headers answer a Range request from offset to the file's end: a 206 whose Content-Range starts at offset and ends at the last byte of a known total. */
int net_head_resumes(const net_head_t *h, long long offset);
/* "If-Range: <etag>" into line (size bytes) and the one-entry header list for net_req_t.headers into list (two pointers); 0 when etag is not a strong one or does not fit. */
int net_if_range(char *line, unsigned size, void *list[2], const char *etag);

/* --- A file on the card --- */

#define NET_RESERVE_KB 32768u /* a download leaves the card this much free (32 MiB) */
/* Why a write stopped a transfer (libcurl reports CURLE_WRITE_ERROR). NET_W_RESPONSE is the caller's: the answer is not the file asked for. */
enum { NET_W_NONE = 0, NET_W_RESPONSE, NET_W_SPACE, NET_W_CARD, NET_W_IO, NET_W_CAP };

/* Room for need_kb more on the file system of path with the reserve kept: NET_W_NONE, NET_W_SPACE, or NET_W_CARD when the card cannot be asked. */
int net_room(const char *path, unsigned need_kb);

typedef struct net_file {
    int fd;
    int why; /* NET_W_* of the write that stopped the transfer */
    unsigned cap; /* the most bytes the file may get (written included), 0: no limit */
    const char *room; /* the reserve is checked on this path's file system after every MiB written; 0: not checked */
    long long written, checked;
} net_file_t;

/* n bytes to the file: n, or 0 with f->why (a write callback returns it as it is). */
unsigned net_file_write(net_file_t *f, const char *data, unsigned n);
/* fsync and close; 1 when both worked. fd is -1 after it. */
int net_file_close(net_file_t *f);
/* part becomes final and the folder dir is made durable: 1; 0 when the rename failed (part stays); -1 when the file is in place but dir could not be synced. */
int net_publish(const char *part, const char *final, const char *dir);
/* The second half alone, for a caller that orders its rename with something else: the folder dir made durable, 1 when it worked. */
int net_sync_dir(const char *dir);
