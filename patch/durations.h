/* Track durations: the table of measured file durations (docs/modules/album-page.md "Album length", docs/modules/homecover.md "Track durations").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The design (a per-file length cache keyed by a path hash, measured through stock's TagLib on the worker thread, the vtable call of
 * AudioProperties::length()) follows q2-pod's Long Songs lengths cache (patch/navigation.c, docs/internals.md#long-songs); the file
 * format, the size check, the pruning and the CUE math are this project's.
 */
#pragma once
#include "covercache.h"

/* The table, on the card beside the cover cache: written whole through DUR_FILE ".tmp" and a rename. */
#define DUR_FILE CARD_DIR "/durations"
#define DUR_MAX_ENTRIES 200000 /* a table of more is refused (and rebuilt) */

typedef struct {
    unsigned key; /* FNV-1a of the path, never 0 */
    unsigned size; /* the file's size when measured: a different size is a different file */
    unsigned sec; /* its length in seconds; 0 = TagLib could not read it (not tried again until the size changes) */
} dur_ent_t;

unsigned dur_key(const char *path);
/* The table is read on the first acquire and freed on the last release (an owner holds it while it looks up or merges). */
void dur_acquire(void);
void dur_release(void);
/* path's seconds when its entry has this size; -1 when there is none or the size differs (it must be measured). */
int dur_file(const char *path, unsigned size);
/* A track record's seconds: a CUE track with both ends is end - start (never measured); otherwise the file's length less the CUE start. > 0 known; 0 not usable (unreadable, no
 * file, shorter than the start); -1 the file is not measured yet, and *size is the size to measure it with. */
int dur_song(void *rec, unsigned *size);
/* The entries merged into the table (a key already there is replaced, the last of equal keys wins) and the file written; 0, or -1 when the file could not be written (the
 * table in memory has them). */
int dur_merge(const dur_ent_t *add, unsigned n);
/* A pass over the library: dur_pass_begin, dur_pass_seen(path) for each song, dur_pass_end drops the entries nobody named (nothing when no song was named) and writes. */
void dur_pass_begin(void);
void dur_pass_seen(const char *path);
unsigned dur_pass_end(void); /* entries dropped */
int dur_has(const char *path); /* the table has an entry for path, any size (acquired) */
/* The worker's measurement: TagLib's length of the file in seconds, 0 when it cannot be read. */
int dur_probe(const char *path);
/* f with its %d replaced by n and its %s by s1, then s2 (the translations put them where the language wants them; the table's text is never a printf format). */
void dur_subst(char *out, unsigned size, const char *f, int n, const char *s1, const char *s2);
/* "49 minutes", "1 hour, 12 minutes" (rounded to the minute, at least one) in the page's language. */
void dur_text(char *out, unsigned size, unsigned sec);
/* Settings > Developer > Clear Track Durations: the file is deleted and the table held in memory (if any) emptied. */
void dur_clear(void);
/* Settings > Developer > Cache, Measured Tracks: the table's header (magic, count) and file size are read here, once as the page opens and
 * again after a clear (open, read 12 bytes, lseek, close); nothing is read at paint. dur_stat writes "count · size" from that, or "0"
 * (no card, no file, a bad magic). */
void dur_stat_open(void);
void dur_stat(char *buf, unsigned n);
unsigned dur_epoch(void); /* counts the clears: a pass that found the table complete is stale after one */
