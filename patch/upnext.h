/* Up Next: Play Next / Play After into the stock play queue (patch/upnext.c, docs/modules/queue.md "Up Next: Play Next / Play After").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The queue handling follows q2-pod's patch/playback.c (playback_queue_insert); the in-place insert, the Shuffle order kept in step, the refusals and the addresses are this project's.
 */
#pragma once

/* upnext_add's answers: > 0 the rows were taken, < 0 refused and nothing changed. */
#define UPNEXT_ADDED 1 /* the rows are in the stock queue (Play Next: after the playing song; Play After: at the end) */
#define UPNEXT_STARTED 2 /* nothing was playing: the rows are the queue now and the first one plays */
#define UPNEXT_EMPTY (-1) /* no rows */
#define UPNEXT_STREAM \
    (-2) /* a stream is playing (play type 2, 3, 0xf0, 0xf1: the Queue page's and the stock drawer's streams) */
#define UPNEXT_FOLDER \
    (-3) /* folder playback (play type 1): the queue is rebuilt from the folder at its end, which would drop the rows */
#define UPNEXT_PODCAST (-4) /* a podcast episode among the rows */
#define UPNEXT_MISSING (-5) /* a row whose file is not on the card */
#define UPNEXT_FULL (-6) /* the queue would pass 65536 songs (SHUFFLE_MAX) */
#define UPNEXT_MEMORY (-7) /* Shuffle's saved order could not be grown (no memory) */
#define UPNEXT_DLNA \
    (-8) /* the DLNA renderer service runs: its threads read the queue without a lock, so the queue is not edited */

/* Play Next (after == 0: right after the playing song, newest first; the rows of one call keep their order) or Play After (after != 0: at the end of the queue). `rows` is a
 * deque of stSongInfo that stays the caller's (the rows are copied). Returns one of the codes above. UI thread. */
int upnext_add(void *rows, int after);
