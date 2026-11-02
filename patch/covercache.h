/* Cover cache and album helpers shared by the pages that show album art (patch/coverflow.c, patch/albums.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The cache design (one JPEG per album, /mnt/mmc/.m1plus/covers/r<key>-168.jpg, an empty file marking "no
 * art") follows q2-pod's; see docs/modules/coverflow.md.
 */
#pragma once

#define CARD_DIR \
    "/mnt/mmc/.m1plus" /* the one hidden folder the payload keeps on the card: covers/ (the cache), daily-mix/ (the Daily Mix: tracks, art), the Cover Flow position, recently-played (the Home shelf's albums) and album-lengths (the album page's FLAC lengths); made by the writers, only while the card is mounted */
#define ART_DIR CARD_DIR "/covers" /* the cache: r<key>-168.jpg per album, an empty file for "no art" */

/* Pure pixel helpers, also built for the host (test/coverflow.py). */
unsigned cc_fnv(unsigned h, const char *s);
/* The centred square of a w x h image (byte order at[] = r, g, b, a positions; stride in bytes), size x size
 * RGBA over black into out: nearest neighbour (the Cover Flow textures) or an area average (box, the grid tiles). */
void cc_sample(const unsigned char *data, unsigned w, unsigned h, unsigned stride, const unsigned char *at,
               unsigned size, unsigned *out);
void cc_box(const unsigned char *data, unsigned w, unsigned h, unsigned stride, const unsigned char *at, unsigned size,
            unsigned *out);

/* An exact area average, one source row at a time (cc_box and the cover extraction, patch/pccover.c, share it). A target pixel is the mean of the source
 * area it covers, a source pixel counting for the fraction of it inside: integer weights (the source and target sizes scaled by each other, so a target
 * cell is `ow` wide in units where a source pixel is `tw`), exact sums, one rounding at the end. Any ratio, up and down. */
#define AR_MAX 512 /* the widest target row */
#define AR_LIMIT (1u << 24) /* ow * oh: 255 * that still fits 32 bits */
typedef struct {
    unsigned ow, oh, tw, th, total, j, ty, rend;
    unsigned acc[AR_MAX * 3], h[AR_MAX * 3];
    unsigned char out[AR_MAX * 3];
} ar_t;
typedef void (*ar_emit_t)(void *user, const unsigned char *rgb); /* one finished target row: tw x (r, g, b) */
/* 1, or 0 when a size is zero or over the limits (ow, oh <= 8192, ow * oh <= AR_LIMIT, tw <= AR_MAX). */
int ar_init(ar_t *a, unsigned ow, unsigned oh, unsigned tw, unsigned th);
/* The next source row: ow pixels of `step` bytes with r, g, b at the offsets ro, go, bo; ao < step is an alpha byte composed over black, ao >= step none.
 * Every target row the row completes goes to emit (none, one, or several when the target is taller than the source). */
void ar_push(ar_t *a, const unsigned char *px, unsigned step, unsigned ro, unsigned go, unsigned bo, unsigned ao,
             ar_emit_t emit, void *user);
/* The size stock's cover resize (0x5e00bc) gives a decoded w x h picture fitted inside t x t, never upscaled: 1 and the size, or 0 when stock keeps the picture as it is (it
 * is smaller than t in both ways). Stock's float arithmetic, quirks included: a picture exactly t wide (or tall) and shorter is stretched to t x t. */
int cc_stock_fit(unsigned w, unsigned h, unsigned t, unsigned *tw, unsigned *th);
/* The size of the picture stock hands to that resize for a JPEG of w0 x h0 with ncomp components: whole when both sides are at most 1024 and it has three components,
 * else decoded at libjpeg's 1/d with d from the longer side (1 under 1024, 2 up to 2048, 4 up to 4096, else 8), each side rounded up. */
void cc_stock_dims(unsigned w0, unsigned h0, unsigned ncomp, unsigned *w, unsigned *h);

#ifndef CF_HOST
const char *cc_str(void *rec, int field); /* a record's string field, "" if none */
unsigned cc_album_key(void *rec); /* FNV-1a of artist then album, never 0 */
unsigned cc_key_of(const char *artist, const char *album); /* the same key from the two names */
char *cc_path(char *out, unsigned size, unsigned key, const char *suffix);
long cc_file_size(const char *path);
const char *cc_url(char *out, unsigned key); /* "file://<cache file>" (out holds 80), NULL: no art cached */
unsigned cc_cover_key(
    void *albums, unsigned key,
    const char *
        album); /* key when its cache file has a picture, else the first library album (albums: cc_albums) named album (NOCASE, not the Unknown row) whose file has one, else key */
int cc_decode(void *w, const char *url, int unload, unsigned size, int box, unsigned *out);
void *cc_copy_list(void *list); /* a stock list copied into a deque of our own */
void *cc_albums(void); /* the stock Albums list (getAllAlbum), copied; NULL if empty */
int cc_open_album(
    void *artist_row, unsigned scope,
    int index); /* the stock Albums row sequence (artist_row NULL), or that artist's (scope CLASS_ARTISTS) or composer's (CLASS_COMPOSERS); 0 once the page is requested */
int cc_find_album(
    const char *
        album); /* the library Albums row with that album name (NOCASE), -1: none; cc_open_album(NULL, 0, row) opens it */
/* The album order shared by Cover Flow and Albums (Settings > Library > Album Order). The stock list is never reordered: the
 * sorted view is a permutation of its row numbers, and anything that goes back to stock (cc_open_album) takes the stock row. */
int cc_nocase(const char *a,
              const char *b); /* ASCII case-insensitive compare (SQLite NOCASE, as the stock list groups) */
int cc_name_cmp(const char *a,
                const char *b); /* cc_nocase with a leading "The " dropped from both (the Artist order's name key) */
const char *cc_name_key(
    const char *
        s); /* s without a leading "The " (when something follows it): the text the Artist order compares, and the Artists page's section letter comes from */
void cc_heapsort(unsigned *v, unsigned n,
                 int (*cmp)(unsigned,
                            unsigned)); /* in place, no memory; cmp must be total (break ties by the row number) */
int cc_sort_artist(void); /* the setting: 1 Artist (default), 0 Album */
int cc_sort_set(
    int artist); /* set it (1 Artist, 0 Album), saved atomically; the state, or -1 when it could not be saved (and the setting is unchanged) */
unsigned *cc_album_order(
    void *albums); /* heap array of the rows in display order; NULL = stock order (Album mode, or no memory) */
void *cc_row(void *albums, const unsigned *order, unsigned i); /* display row i of the list */
void *cc_playing(void); /* the stSongInfo of the track the player is on, NULL if nothing is queued */

/* The cache builder, shared by Cover Flow (its Preparing screen, and Settings > Library > Rebuild Covers) and the
 * Albums page (in the background). ONE worker thread app-wide: a job set is held from cc_build_open until
 * cc_build_stop, and cc_build_open refuses while one is held. The owner polls the counters from a page-scoped timer
 * (UI thread) and must call cc_build_stop (cancel, join, free) when it is done with the set and when its page is destroyed.
 * The thread touches only its own jobs, the counters, files under ART_DIR and the stock art calls under parse_cover_mutex;
 * never a widget, a deque or the image manager.
 *   CC_MISSING  only albums with no cache file (neither a picture nor the empty "no art" marker); cc_build_add skips the rest
 *   CC_REBUILD  every album is extracted again and its file replaced (temp + rename), a marker too, so an album that gained
 *               art gets it; an album that now yields none keeps what it has (old files stay until a new one replaces them) */
enum { CC_MISSING = 0, CC_REBUILD = 1 };
#define CC_MAX_JOBS 4000 /* the job array is bounded (Cover Flow's MAX_ALBUMS) */
int cc_build_open(unsigned capacity, int mode); /* 1: an empty job set held; 0: another set is held, or no memory */
int cc_build_add(const char *track,
                 unsigned key); /* 1 added; 0 skipped (CC_MISSING and the file exists); -1 full or no memory */
int cc_build_add_file(
    const char *track, const char *dst,
    unsigned
        px); /* a transient job instead: the album's art fitted inside px x px (never upscaled; kept only when its longer side is px) into the file dst through dst.tmp, no cache file, no marker (the Pod's cover pane, docs/modules/ipod.md) */
int cc_build_start(
    void); /* 1: the worker runs. 0: nothing to build, card full (MIN_FREE_MB), or no thread: the set is freed */
int cc_build_done(void); /* albums finished so far (advances as files appear) */
int cc_build_total(void);
int cc_build_running(void); /* a thread was started and the set is not stopped yet */
int cc_build_busy(void); /* a job set is held */
void cc_build_stop(void); /* cancel, join (bounded by one album's art), free; safe when nothing is held */
/* Albums by distance from row `centre` (the centre, then one after, one before, ...), as the shared album order shows them
 * (`order` may be NULL): each one with a track path is added. Returns the number of jobs held after (cc_build_total). */
int cc_build_near(void *albums, const unsigned *order, unsigned centre);
/* The same walk in bounded steps: `*cursor` starts at 0 and is advanced; at most `batch` albums are considered (and so
 * stat'ed) per call. 1 once the walk is complete (or the set is full), 0 when more remains. The caller keeps `centre`
 * and the set unchanged between calls, and starts the worker only after the last step (jobs are never written while it runs). */
int cc_build_near_step(void *albums, const unsigned *order, unsigned centre, unsigned *cursor, unsigned batch);
#endif
