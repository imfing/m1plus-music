/* Artist photos for the local library (docs/modules/artists.md "Artist photos").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Discovery of the artist.jpg / folder.jpg pictures beside the music, the cache files in AP_DIR and the library snapshot the purity check reads. Built by the cover worker
 * (patch/covercache.c): every function below but ap_key and ap_lib_add runs on the worker thread.
 */
#pragma once
#include "covercache.h"

#define AP_DIR \
    CARD_DIR \
    "/artists" /* the cache: a<key>-44.jpg (list rows), a<key>-168.jpg (page header), a<key>.src, .pick, .try; an empty -44 file = no photo */
#define AP_LIST 44
#define AP_HEAD 168
#define AP_LIB_MAX \
    8000 /* albums the purity snapshot holds; a larger library gets no artist photos (a folder's purity could not be proven) */

/* The artist key: FNV of the name trimmed, ASCII case folded, without a leading "The ". 0 for a blank name. */
unsigned ap_key(const char *name);
/* The snapshot of the library's albums (track folder, artist key) that purity is judged on. 1 added (key 0 = no artist: the entry conflicts with every real key); 0 not kept (full or no memory: the snapshot is then unusable, ap_lib_ok is 0). */
int ap_lib_add(const char *track, unsigned key);
int ap_lib_ok(void);
/* 1 the first time key is seen in this snapshot (so an artist gets one job), else 0. */
int ap_first(unsigned key);
void ap_lib_free(void);
/* The Home pass has added every album: the purity map goes to AP_DIR/purity (UI thread, one write of at most 200 KB), for the re-check below. 1 saved; 0 not (the old file is removed: it describes another library).
 * ap_lib_drop removes it (a pass that made no snapshot). */
int ap_lib_save(void);
void ap_lib_drop(void);
/* ---- showing a photo (UI thread; docs/modules/artists.md "Artist photos") */
#define AP_ROW_D 40 /* the Artists rows' circle */
#define AP_HEAD_D 88 /* the artist page's circle (AL_PHOTO_D), box-reduced from the -168 file at decode */
#define AP_GLYPH "pod_ic_ar_art" /* the placeholder's mic-vocal glyph (#8C8C8C on transparent, tools/mod_icons.py) */
/* What ap_lookup found (the Artists page keeps it, 2 bits an artist): nothing known yet (no file), a photo under the name's own key, no photo (the marker), a photo under the lead artist's key. */
enum { AP_UNKNOWN, AP_PHOTO, AP_NONE, AP_LEAD };
/* The lead artist of "A feat. B": the name before the first of " feat. ", " ft. ", " featuring ", " & ", " x ", ", ", "; " (ASCII case folded; the earliest in the name wins) into out (n bytes). 0: none of them, or a lead too long. */
int ap_lead(const char *name, char *out, unsigned n);
/* The -44 (size AP_LIST) or -168 (AP_HEAD) file of the name's own key when it holds a picture (AP_PHOTO), else of the lead artist's key (AP_LEAD); url ("file://..." in 80 bytes) is set for those two. AP_NONE: the name's file is the empty
 * marker and the lead has no photo either (or none, or its marker); AP_UNKNOWN: a file is missing. Opens files: never from a paint. */
int ap_lookup(const char *name, unsigned size, char *url);
/* A d x d RGBA bitmap with its pixels locked in *px (flags clear: alpha is used), or NULL (the caller unlocks it and destroys it). */
void *ap_bitmap(int d, unsigned **px);
/* The pixels of a d x d picture cut to the circle that touches its sides: the alpha is the circle's coverage (8 x 8 samples on the edge). */
void ap_circle(unsigned *px, int d);
/* The placeholder: a #333333 circle with the muted glyph at 0.52 of d; NULL when no bitmap can be made. */
void *ap_placeholder(void *win, int d);
/* One artist: look for its photo among its albums' folders and write the cache files (or the empty marker). force: every artist is checked again (an artists-rebuild request). Worker thread. */
void ap_job(const char *track, unsigned key, int force, const volatile int *cancelled);
/* ---- the re-check of one artist (an artist's page asks for it when it opens) */
/* UI thread: asks the cover worker to look at one artist again; tracks = the first track path of each of its albums, one per line (the page has them). 1 started, 0 not (no key, the worker is busy: the Home
 * pass will see it). Poll the set with cc_build_done / cc_build_total and free it with cc_build_stop as any page-owned set. The worker never queries the database: it reads the map ap_lib_save wrote; without it
 * only the album folders are looked in and no marker is written. */
int ap_recheck(const char *name, const char *tracks);
/* Counts the re-checks that made, replaced or removed a photo. A page compares it with the value it saw to know that a photo changed. */
unsigned ap_epoch(void);
/* Worker thread: the job ap_recheck queues. */
void ap_recheck_job(const char *tracks, unsigned key, const volatile int *cancelled);
