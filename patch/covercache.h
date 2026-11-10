/* Cover cache and album helpers shared by the pages that show album art (patch/coverflow.c, patch/albums.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The cache design (one JPEG per album, /mnt/mmc/.m1plus/covers/r<key>-168.jpg, an empty file marking "no
 * art") follows q2-pod's; see docs/modules/coverflow.md.
 */
#pragma once

#define CARD_DIR \
    "/mnt/mmc/.m1plus" /* the one hidden folder the payload keeps on the card: covers/ (the cache), daily-mix/ (the Daily Mix: tracks, art), durations (the track durations table), the Cover Flow position and recently-played (the Home shelf's albums); made by the writers, only while the card is mounted */
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
/* The whole w x h picture fitted inside size x size (never cropped, size at most AR_MAX), centred over the word bg, in out (size * size words): the longer side becomes size, the other follows, by the
 * exact area average (a longer side of exactly size is a pixel copy). 1; 0 and out untouched when the sizes are over ar_init's limits. */
int cc_fit(const unsigned char *data, unsigned w, unsigned h, unsigned stride, const unsigned char *at, unsigned size,
           unsigned bg, unsigned *out);
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
void cc_size_text(char *buf, unsigned n,
                  unsigned bytes); /* "14.2 MB" (tenths below 10 MB, then whole MB): the Cache page's Size row */
const char *cc_url(char *out, unsigned key); /* "file://<cache file>" (out holds 80), NULL: no art cached */
unsigned cc_cover_key(
    void *albums, unsigned key, const char *album,
    char *
        url); /* url (NULL ok; holds 80) gets the chosen key's cc_url, "" when no file. Key when its cache file has a picture, else the first library album (albums: cc_albums) named album (NOCASE, not the Unknown row) whose file has one, else key */
/* The cache key of the library album record of that name (ASCII NOCASE): the row getAllAlbum lists for it, which the cover files are named after (a collab's own key has no file).
 * ONE targeted query through toolsQueryDbTable, *pdeq_showlist untouched; 0: no album tag, a name over 250 bytes, a failed query, no such album. Ask once. */
unsigned cc_album_rep_key(const char *album);
/* The cover map (patch/covercache.c): the library albums' names -> the keys of their cache files, from ONE getAllAlbum query that leaves *pdeq_showlist alone. 8 bytes per
 * album kept (the hash of the folded name and the key; integers only) and 2 bits for whether its file holds a picture (looked at the first time the album is asked for, never
 * by the build), at most CC_CMAP_MAX albums are kept (the first by name; the rest are not found). Free it with cc_cmap_free. */
#define CC_CMAP_MAX 4096
typedef struct cc_cmap cc_cmap_t;
/* The albums the query returned, the entries kept (not ambiguous), the entries dropped for sharing a hash with another key. */
typedef struct {
    unsigned rows, kept, ambiguous;
} cc_cmap_stat_t;
/* NULL: nothing to look up (no albums, a failed query, no memory, only ambiguous names); st (NULL ok) is filled either way. Opens no file. */
cc_cmap_t *cc_cmap_build(cc_cmap_stat_t *st);
/* The cache key holding album's cover (ASCII NOCASE), 0 when none: not in the library, ambiguous, or its file holds no picture (the file is looked at once, on the first ask);
 * map NULL ok. */
unsigned cc_cmap_key(cc_cmap_t *map, const char *album);
void cc_cmap_free(cc_cmap_t *map);
int cc_decode(void *w, const char *url, int unload, unsigned size, int box, unsigned *out);
/* cc_decode for a picture that must not be cropped: the whole picture fitted inside size x size over the word bg (cc_fit). 1 when out was written. */
int cc_decode_fit(void *w, const char *url, int unload, unsigned size, unsigned bg, unsigned *out);
void *cc_copy_list(void *list); /* a stock list copied into a deque of our own */
void *
cc_albums(void); /* the stock Albums list (getAllAlbum), copied; NULL if empty or the copy failed (cc_list_failed) */
void *cc_songs(void); /* the stock Songs list (getAllMusic), copied; NULL if empty or failed (cc_list_failed) */
int cc_list_failed(
    void); /* the last cc_albums / cc_songs returned NULL because the copy of a non-empty list failed (a failed query is not told apart from an empty list: stock returns 0 for both) */
int cc_open_album(
    void *artist_row, unsigned scope,
    int index); /* the stock Albums row sequence (artist_row NULL), or that artist's (scope CLASS_ARTISTS) or composer's (CLASS_COMPOSERS); 0 once the page is requested */
int cc_find_album(
    const char *
        album); /* the library Albums row with that album name (NOCASE), -1: none; cc_open_album(NULL, 0, row) opens it */
/* The album order shared by Cover Flow and Albums (Settings > Library > Album Order). The stock list is never reordered: the
 * sorted view is a permutation of its row numbers, and anything that goes back to stock (cc_open_album) takes the stock row. */
int cc_nocase(const char *a, const char *b); /* ASCII case-insensitive compare (SQLite NOCASE) */
int cc_key_cmp(
    const char *a,
    const char *
        b); /* the name order of the lists on prepared keys: digit runs by value, ASCII case folded, digits and symbols (any non-ASCII byte too) before letters */
int cc_name_cmp(
    const char *a,
    const char *
        b); /* cc_key_cmp of the names without leading white space, leading punctuation (when a letter or digit follows) and a leading "The " (no pinyin or kana initials: see cc_name_keys) */
const char *cc_name_key(
    const char *
        s); /* s without leading white space, leading punctuation (so_name) and a leading "The " (when something follows it): the text the Artist order compares */
int cc_name_initial(
    const char *
        name); /* the first byte of that text, a CJK character as its pinyin initial (stock's utf8_to_pinyin), a kana as its romaji initial: the section letter of a name */
const char **cc_name_keys(
    unsigned n, const char *(*name)(const void *ctx, unsigned i),
    const void *
        ctx); /* the keys of n names for cc_key_cmp, CJK characters as pinyin and kana as romaji initials; one block to free(); NULL: no names or no memory (keep the stock order) */
void cc_heapsort(unsigned *v, unsigned n,
                 int (*cmp)(unsigned,
                            unsigned)); /* in place, no memory; cmp must be total (break ties by the row number) */
#define CC_SORT_TITLE 0 /* the Albums page's orders (cc_sort_mode, ALBUMS_SORT_FILE) */
#define CC_SORT_ARTIST 1
#define CC_SORT_RECENT 2
#define CC_SORT_YEAR 3
#define CC_SORT_MODES 4
int cc_sort_mode(
    void); /* the saved order, 0..3; Artist when there is no valid file (the retired album-order file is moved into it once first) */
int cc_sort_rev(
    void); /* 1 when the saved order is in its other direction (Z-A, Oldest First); 0 for the default direction and for no valid file */
int cc_sort_mode_set(
    int mode,
    int rev); /* save it atomically; the mode, or -1 when it could not be saved (and the setting is unchanged) */
unsigned *cc_album_order(
    void *
        albums); /* heap array of the rows in display order for cc_sort_mode (Recently Added and Year read the whole song list once); NULL = stock order (no memory / no songs) */
int cc_scoped_sort(
    void); /* cc_sort_mode for one artist's albums: Artist shows as Title; its direction is cc_sort_rev */
unsigned *cc_album_order_mode(
    void *albums, int mode,
    int rev); /* cc_album_order for the given CC_SORT_* and direction instead of the saved ones; NULL: no albums or no memory (Title falls back to the stock order, backwards for Z-A); "Unknown Album" and the All Songs row stay last */
unsigned *cc_album_years(
    void *albums,
    void *
        songs); /* one artist's albums' years: per row of `albums` the earliest year tag (1000..2999) among the songs of `songs` that name that album (the Year order's rule), 0 = none; heap, NULL without memory */
void *cc_row(void *albums, const unsigned *order, unsigned i); /* display row i of the list */
void *cc_playing(void); /* the stSongInfo of the track the player is on, NULL if nothing is queued */

/* The cache builder, shared by Cover Flow (its Preparing screen, and Settings > Library > Rebuild Covers) and the
 * Albums page (in the background). ONE worker thread app-wide: a job set is held from cc_build_open until
 * cc_build_stop, and cc_build_open refuses while one is held. The owner polls the counters from a page-scoped timer
 * (UI thread) and must call cc_build_stop when it is done with the set and when its page is destroyed. Stop never waits for
 * the thread: a worker that has exited or has no job left is joined and the set freed at once; one still inside a job is cancelled and orphaned (it keeps
 * the set, stock's art call cannot be interrupted) and is joined and freed by the next cc_build_open / cc_build_busy /
 * cc_build_orphan / cc_build_stop once it has exited. Until then cc_build_open refuses and cc_build_busy is true.
 * The thread touches only its own jobs, the counters, files under ART_DIR and the art calls under parse_cover_mutex (stock's two and
 * taglib_album_picture; our own resize runs outside it); never a widget, a deque or the image manager.
 * A card job that hangs: ART_DIR/.inflight (ART_DIR is .m1plus/covers on the card, hidden in Finder) is a small text record of the job being extracted, written once the stock parser lock is held:
 *   m1plus cover 1 / key: <8 hex> / build: <the player's build tag> / track: <path> / end
 * (a `\` or newline in a path is written `\\` or `\n`, any other control byte `\xNN`; no `end` line: cut short). cc_build_open turns a leftover one (the last run died or hung) into
 * r<key>-168.jpg.try (an empty file; a power-off is no proof), and a second leaves r<key>-168.jpg.bad, a text record of the same shape with `result: interrupted twice`, `phase: unknown` and the track
 * (a finished job for the key removes the .try; an .inflight with no valid key line is removed and blames no one; a cut one still strikes, with `track: unknown`); every set skips a key with a .bad (existence only; cc_clear_bad, called when Rebuild Covers is requested, removes them all). cc_build_done,
 * which the pages poll, also stops a set whose done counter has not moved for CC_STALL_MS and then returns total: the worker is orphaned as by cc_build_stop, the job is marked .bad (and its .inflight removed) if its extraction had begun,
 * with `result: timed out`, the `phase:` where the worker's progress stopped (embedded art: reading tags, shrinking, stock fallback; folder: scanning, image shrinking, stock fallback; not that a file is corrupt) and, when known, `image: <path> WxH jpeg|png [progressive|baseline]`.
 * A timed-out "folder image, shrinking" on a progressive JPEG over 4 MP would mean the PV_REFUSED guard was bypassed.
 * The poll that finds the worker exited frees the set.
 *   CC_MISSING  only albums with no cache file (neither a picture nor the empty "no art" marker); cc_build_add skips the rest
 *   CC_REBUILD  every album is extracted again and its file replaced (temp + rename), a marker too, so an album that gained
 *               art gets it; an album that now yields none keeps what it has (old files stay until a new one replaces them) */
enum { CC_MISSING = 0, CC_REBUILD = 1, CC_DURATIONS = 2 };
/* CC_DURATIONS is a set of another kind (patch/durations.c): its jobs are files whose length TagLib reads (cc_build_add_dur), nothing is written to the card and cc_build_start needs
 * no card space. The owner merges what finished (cc_build_dur, i < cc_build_done) into the durations table. */
int cc_build_add_dur(
    const char *track, unsigned key,
    unsigned size); /* 1 added; 0 skipped (not a CC_DURATIONS set, or the key is already a job); -1 full or no memory */
int cc_build_dur(
    int i, unsigned *key, unsigned *size,
    unsigned *sec); /* the finished job i: 1, or 0 when it is not finished or the set is not a CC_DURATIONS one */
#define CC_MAX_JOBS 4000 /* the job array is bounded (Cover Flow's MAX_ALBUMS) */
#define CC_MAX_LEN_JOBS \
    30000 /* a CC_DURATIONS set's bound (a job is 16 bytes and a path copy); a longer library is measured in more passes */
int cc_build_open(unsigned capacity, int mode); /* 1: an empty job set held; 0: another set is held, or no memory */
int cc_build_add(const char *track,
                 unsigned key); /* 1 added; 0 skipped (CC_MISSING and the file exists); -1 full or no memory */
/* An album's artist for the artist photos (patch/artistphoto.h): the album's track folder is kept for the purity check, and the artist gets one job (1) unless it has a result already (0), or the set
 * is full (-1). Call it for EVERY album of the library, before cc_build_start. force: check the artist again whatever it has (an artists-rebuild request). The snapshot is bounded (AP_LIB_MAX
 * albums; cc_build_artist_ok is 0 once it overflowed or ran out of memory, and the artist jobs then write nothing). Not in a CC_DURATIONS set. */
int cc_build_add_artist(const char *track, const char *artist, int force);
int cc_build_artist_ok(void);
/* One re-check job of the artist with key (patch/artistphoto.c ap_recheck); tracks = the first track path of each of its albums, one per line (copied). 1 added, -1 full or no memory. */
int cc_build_add_recheck(const char *tracks, unsigned key);
int cc_build_add_file(
    const char *track, const char *dst,
    unsigned
        px); /* a transient job instead: the album's art fitted inside px x px (never upscaled; kept only when its longer side is px) into the file dst through dst.tmp, no cache file, no marker (the Pod's cover pane, docs/modules/ipod.md) */
int cc_build_add_aspect(
    const char *track, const char *dst, unsigned px,
    int source); /* cc_build_add_file for a picture shown on its own (the timed cover page), from stock's cover source only (2 the embedded art, 3 the folder's; any other: 0, nothing added; the other source is never a substitute, so art that is small or unsupported makes no file): a picture whose longer side is exactly px keeps its aspect ratio (stock's resize stretches it to px x px), and stock's resize is never the fallback */
int cc_build_start(
    void); /* 1: the worker runs. 0: nothing to build, card full (MIN_FREE_MB), or no thread: the set is freed */
int cc_build_done(void); /* albums finished so far (advances as files appear) */
int cc_build_total(void);
int cc_build_running(void); /* a thread was started and the set is not stopped yet */
int cc_build_busy(void); /* a job set is held */
int cc_build_active(
    void); /* the worker runs a cover or duration set with work left: volatile reads only (no lock, no file), for the status bar's sync icon (patch/lineout.c); false for a transient file job, a cancelled or orphaned set */
void cc_build_stop(
    void); /* cancel, then join and free, or orphan a worker still inside a job (never blocks); safe when nothing is held */
int cc_build_orphan(
    void); /* a stopped worker has not exited yet (reaps it if it has) and was stopped less than CC_STALL_MS (10 s) ago: cc_build_open refuses for a moment, so retry; after that, give up until the next open */
void cc_clear_bad(void); /* removes every .bad under ART_DIR (the Rebuild Covers request) */
int cc_build_truncated(
    void); /* the set's last cc_build_near_step could not queue an album (set full, or out of memory): some albums were not queued; kept like stalled, until the next cc_build_open */
int cc_build_stalled(
    void); /* the last set ended because build_watch gave up on it (also after it is freed, until the next cc_build_open): its albums were not all built */
/* Albums by distance from row `centre` (the centre, then one after, one before, ...), as the shared album order shows them
 * (`order` may be NULL): each one with a track path is added. Returns the number of jobs held after (cc_build_total). */
int cc_build_near(void *albums, const unsigned *order, unsigned centre);
/* The same walk in bounded steps: `*cursor` starts at 0 and is advanced; at most `batch` albums are considered (and so
 * stat'ed) per call. 1 once the walk is complete (or the set is full: then `*cursor` is left on the album that did not fit), 0 when more remains. The caller keeps `centre`
 * and the set unchanged between calls, and starts the worker only after the last step (jobs are never written while it runs). `keys`, if not NULL, holds the cache key of each album by
 * display position (a scoped list's, patch/coverflow.c coverflow_artist_albums); NULL keys every album by cc_album_key. */
int cc_build_near_step(void *albums, const unsigned *order, const unsigned *keys, unsigned centre, unsigned *cursor,
                       unsigned batch);
#endif
