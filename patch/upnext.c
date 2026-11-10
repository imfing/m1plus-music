/* M1+ Music Up Next: Play Next / Play After into the stock play queue (docs/modules/queue.md "Up Next: Play Next / Play After" has the design, the evidence and the handover).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The shape follows q2-pod's patch/playback.c (playback_queue_insert); the in-place insert (the device-proven Phase 0 probe, generalised to n rows), the refusals and the
 * addresses are this project's. The stock queue is read live by every stock reader, so queued songs go into it straight away and stock plays it in order in every mode
 * (Shuffle is the payload's own flag, patch/shuffle.c: the queue is already in its shuffled order). The insert itself lives in patch/shuffle.c (pod_queue_insert) so that
 * Shuffle's saved order stays valid and the payload lock is held; this file is the refusals and the start of a queue when nothing plays.
 * Nothing runs unless a caller (patch/rowmenu.c) calls it: no hook, no timer, no thread.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "home.h"
#include "i18n.h"
#include "podcasts.h"
#include "radio.h"
#include "upnext.h"
#include "sbapi.h"

extern unsigned pod_rand(unsigned n); /* patch/shuffle.c */

#define I(w, off) (*(int *)((char *)(w) + (off)))

/* The play types that are not for the queue: streams (the Queue page's and the stock drawer's list) and folder playback (type 1: the queue is rebuilt from the folder at its end). */
static int up_play_type(void) {
    int t = mclGetPlayType();
    if (t == QP_STREAM_A || t == QP_STREAM_B || t == QP_STREAM_C || t == QP_STREAM_D) return UPNEXT_STREAM;
    return t == 1 ? UPNEXT_FOLDER : 0;
}

/* Nothing is playing: the rows are the queue, as the stock Songs row starts one (start_player copies them; with Shuffle on the load hook reorders them, the first row first).
 * The Shuffle flag and the repeat mode stay as they are, so no pod_set_*_for_queue call. */
static int up_start(void *rows) {
    int cls = I(deque_at(rows, 0), REC_CLASS);
    if (!cls) cls = CLASS_ALL_SONGS;
    *(int *)G_CLASS_TYPE = cls;
    start_player(rows, 0, cls, PLAY_MODE);
    *(unsigned char *)FORCE_REFRESH = 1;
    return UPNEXT_STARTED;
}

int upnext_add(void *rows, int after) {
    void *q = *(void **)PLAY_QUEUE;
    unsigned n = rows ? deque_size(rows) : 0, size = q ? deque_size(q) : 0, i;
    int pos = mclGetPlayPos(), t, r;
    if (!n) return UPNEXT_EMPTY;
    if (rd_running())
        return UPNEXT_STREAM; /* a station connects, plays or is paused: Radio sets no stock play type, so up_play_type() cannot see it, and the local queue (if any) is dormant */
    for (i = 0; i < n; ++i) { /* every row: a local song whose file is there */
        const char *path = cc_str(deque_at(rows, i), REC_PATH);
        if (pc_is_path(path)) return UPNEXT_PODCAST;
        if (path[0] == 'h' && path[1] == 't' && path[2] == 't' && path[3] == 'p' &&
            sba_rec_track(I(deque_at(rows, i), REC_ID))[0])
            continue; /* a Navidrome row's stream address (sbsrc queue_row noted its id): nothing on the card to find */
        if (!*path || access(path, F_OK)) return UPNEXT_MISSING;
    }
    if (size && pos >= 0 && (unsigned)pos < size) { /* something is playing */
        t = up_play_type();
        if (t) return t;
        r = pod_queue_insert(rows, after);
        if (r == POD_INSERT_OK) return UPNEXT_ADDED;
        if (r == POD_INSERT_FULL) return UPNEXT_FULL;
        if (r == POD_INSERT_MEMORY) return UPNEXT_MEMORY;
        if (r == POD_INSERT_DLNA) return UPNEXT_DLNA;
        /* POD_INSERT_IDLE: the queue went away between the look and the lock: start it */
    }
    return up_start(rows);
}
