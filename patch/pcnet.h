/* Podcast feeds on the network: subscribe (import), refresh one show or all (patch/pcnet.c; docs/modules/podcasts.md "Feeds").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * ONE detached pthread does all the network and card writes of a refresh, one show at a time; the UI never calls into it. The page asks pn_refresh (UI thread: the guards, then the
 * thread) and afterwards only READS the status record (pn_busy / pn_gen / pn_progress / pn_current / pn_status) from its own timer, and reloads the shows when pn_gen changed: AWTK is
 * not thread safe, and the model's list functions stay the one source of the page's rows (the worker writes the same .episodes / .show files they read).
 *
 * Two lanes: the JOB lane (a refresh, a search, a preview, a chart, Find Cover & Lyrics, Software Update, AutoEq, the archive: one at a time, PN_BUSY to the next) and the DOWNLOAD lane (the episode
 * queue's own thread, pn_dl_*). A download runs beside a job and never gives way to one: no page pauses the downloads.
 */
#pragma once

#include "common.h"
#include "net.h"
#include "netfile.h"
#define PN_CA M1_CA /* (common.h) */
#define PN_MIN_EPOCH M1_MIN_EPOCH
#define PN_FEED_CAP 8388608u /* a feed larger than this (after gzip) is refused */
#define PN_COVER_CAP 6291456u /* a cover picture larger than this is refused while it downloads */
#define PN_IMPORT_FILE "subscriptions.txt" /* in the Podcasts folder: one feed url a line */
#define PN_OPML_FILE \
    "subscriptions.opml" /* in the Podcasts folder: an OPML export of another app (any *.opml in the card root is read too) */
#define PN_EXPORT_FILE \
    "subscriptions-export.opml" /* what the Subscriptions page's Export OPML writes, in the Podcasts folder */

/* Results of a refresh, per feed (and what the guards say): the page shows the words. */
enum {
    PN_OK = 0,
    PN_NOWIFI, /* the Wi-Fi is not connected */
    PN_NOCLOCK, /* the clock was never set (certificates need the date) */
    PN_NOCERT, /* PN_CA is missing, or libcurl cannot read it */
    PN_CERT, /* the server's certificate was refused */
    PN_NET, /* no connection, no answer, a time-out */
    PN_GONE, /* HTTP 404 or 410 */
    PN_HTTP, /* another HTTP error */
    PN_NOTFEED, /* the answer is not an RSS feed (or it is too large) */
    PN_STORAGE, /* no card, or a file could not be written */
    PN_MEM, /* no memory, or no thread */
    PN_BUSY, /* a refresh is already running */
    PN_CANCELLED, /* the transfer was aborted by the page's Cancel (never shown: the show keeps its earlier status) */
    PN_CARDFULL, /* a download: the card would keep less than PN_DL_MARGIN_KB free */
    PN_NOTAUDIO, /* a download: the answer is a web page (Content-Type text/...), not an episode */
    PN_QFULL, /* the download queue is full (PN_QMAX) */
    PN_NOFEED, /* search: an Apple Podcasts address whose show has no feed address */
    PN_NOLYRICS, /* lyrics: no LRCLIB record has any */
    PN_OVERLOAD, /* find cover & lyrics: the service answered 503 or 429 (busy) on every try */
    PN_UPCHECK, /* software update: GitHub's answer is not the redirect to a release of the repository (any other status, address or tag) */
    PN_UPBAD /* software update: the downloaded file is not the package of the version offered (short, too large or another version) */
};

/* Episode downloads (docs/modules/podcasts.md "Downloads"). The policy follows q2-podcasts (MIT): one at a time, chunks written with open / write / fsync / close, Range resume, a stall limit,
 * retries after 10, 20 and 40 s, a free-space margin. The queue is in memory only. */
/* PN_QMAX: downloads queued or running. PN_DL_BUF: bytes gathered before a chunk is written (open, write, fsync, close), so the card is rarely held busy. PN_DL_MARGIN_KB: the card always keeps this much
 * free (32 MB), checked before the download and before every chunk. PN_DL_PATH_MAX: the longest path of a download, the .part file included. PN_DL_STALL: seconds without a byte (libcurl's low-speed
 * time-out at 1 byte a second). PN_DL_RETRIES: network failures retried, after 10, 20 and 40 s (the count starts again after an attempt that got bytes). PN_DL_MAX_BYTES: a larger download is
 * refused (the file offsets are 32 bit). PN_FAILS: download failures remembered for the rows. */
#define PN_QMAX 32
#define PN_DL_BUF 524288u
#define PN_DL_MARGIN_KB NET_RESERVE_KB /* (patch/netfile.h: one reserve for every download) */
#define PN_DL_PATH_MAX 240
#define PN_DL_STALL 60
#define PN_DL_RETRIES 3
#define PN_DL_MAX_BYTES 2147483647u
#define PN_FAILS 16

enum { PN_DL_NONE = 0, PN_DL_WAIT = 1, PN_DL_ACTIVE = 2, PN_DL_FAILED = 3 };

/* The conditions to start (UI thread): the card is there, the Wi-Fi is connected (stock get_wifisignal), the clock is set, the CA bundle exists. 0 or PN_*. */
int pn_guard(void);
/* Refresh the shows shows[idx[0..n)] that have a feed url: the guards, then one worker thread. root is the Podcasts folder as the card spells it. 0 when the thread runs, else PN_* (nothing started). */
int pn_refresh(const char *root, const pc_show_t *shows, const int *idx, int n);
int pn_busy(
    void); /* a refresh worker is running (a download worker is pn_dl_running, a search or preview worker pn_job_busy) */
/* What a job's thread does. A page cancels only the kinds it starts (pn_cancel): another page's job is never its to stop. */
enum {
    PN_KIND_REFRESH = 1, /* Refresh All, one show, Import (the Podcasts page's dialog) */
    PN_KIND_SEARCH = 3,
    PN_KIND_PREVIEW = 4,
    PN_KIND_ART = 5, /* Find Cover & Lyrics, Find Artist Photo: the lookup */
    PN_KIND_PICK = 6, /* ... and the save */
    PN_KIND_UPDATE = 7, /* Software Update: the check and the download */
    PN_KIND_CHART = 8,
    PN_KIND_EQ = 9, /* AutoEq */
    PN_KIND_ARCH = 10 /* a show's whole episode list */
};
#define PN_K(kind) (1u << (kind))
#define PN_K_REFRESH PN_K(PN_KIND_REFRESH)
#define PN_K_PODCASTS \
    (PN_K(PN_KIND_SEARCH) | PN_K(PN_KIND_PREVIEW) | PN_K(PN_KIND_CHART) | \
     PN_K(PN_KIND_ARCH)) /* the Podcasts page's jobs */
#define PN_K_ART (PN_K(PN_KIND_ART) | PN_K(PN_KIND_PICK))
#define PN_K_UPDATE PN_K(PN_KIND_UPDATE)
#define PN_K_EQ PN_K(PN_KIND_EQ)
/* UI thread: ask the running job to stop if it is one of kinds (PN_K_*): the transfer in progress is aborted (libcurl's transfer-info callback), no further show is started. A job of another
 * kind, another page's, goes on; with no job running nothing happens. */
void pn_cancel(unsigned kinds);
int pn_cancelling(void); /* a worker is running and was asked to stop */
unsigned pn_part(
    void); /* how far the show being refreshed has come, 0..1000 (the feed's length when the server gave it; the picture is the last tenth) */
/* The last job: shows refreshed (OK, up to date or new), shows that failed, and whether Cancel ended it. Valid when pn_busy() is 0. */
void pn_summary(unsigned *ok, unsigned *failed, int *cancelled);
unsigned pn_gen(void); /* changes whenever the status record does (a show finished, the worker ended) */
void pn_progress(int *done, int *total); /* shows finished / asked, of the last (or running) job */
unsigned pn_current(void); /* pc_hash of the feed url being fetched now, 0 when none */
int pn_status(
    unsigned feed, int *code,
    unsigned *
        fresh); /* the last result of the feed (pc_hash of its url) in this session: 1 and *code (PN_*), *fresh new items; 0 when there is none */
/* Subscribe to the feeds the card offers that no show has yet: the lines of <root>/subscriptions.txt and the outlines of <root>/subscriptions.opml and of every *.opml in the card's root (patch/pcopml.h), one
 * source after another sharing the PC_MAX_SHOWS shows' room. A folder and a .show file each (the title is the OPML's name, else the host, until the first refresh names it). An OPML file all of whose outlines were seen
 * (and that held one) is renamed <name>.imported; subscriptions.txt stays. Returns how many were added (the shows already there do not count), -1 when there is no source at all. shows[0..nshows): the folders now there. */
int pn_import(const char *root, const pc_show_t *shows, int nshows);
/* How many import sources the card has now (subscriptions.txt, subscriptions.opml, *.opml in the card's root): the Shows page's "..." shows Import from Card when it is not 0. */
int pn_import_found(const char *root);
/* Write Podcasts/subscriptions-export.opml: OPML 2.0, one outline per show with a feed address, by title, atomically. *count: the shows written. 1 when written, 0 when not (nothing is left behind). */
int pn_export(const char *root, const pc_show_t *shows, int nshows, int *count);
/* Unsubscribe: the show's .show rewritten without its feed address (nothing else changes; the .episodes stay). 1 when written. */
int pn_unsubscribe(const char *root, const pc_show_t *show);
/* Unsubscribe completely, as the Show page does: pn_unsubscribe, the .part files and queued downloads of the show gone, and with no episode file left its own files and folder too. 0 not written (nothing touched), 1 the show stays (files left), 2 gone. */
int pn_unsubscribe_show(const char *root, const pc_show_t *show);

/* ---- Downloads. All of these run on the UI thread; the download thread (one, with one episode at a time; it runs beside a job) only reads and writes the status record. */
/* The key of an episode in the queue and the failure table: pc_hash of "<show folder>/<file name>". */
unsigned pn_dl_key(const char *dir, const char *file);
/* Queue the download of file in the show folder dir (the names as the model has them; root is the Podcasts folder). The guards run first (card, Wi-Fi, clock, CA bundle: PN_*), a path over PN_DL_PATH_MAX is PN_STORAGE, a full queue PN_QFULL;
 * a queued or running one is left as it is (a cancel not yet taken is undone). Starts the worker when none runs. 0 when queued. */
int pn_dl_add(const char *root, const char *dir, const char *file);
/* Take the episode out of the queue; one that is running is aborted at once (the .part stays: a later add resumes it). */
void pn_dl_cancel(unsigned key);
/* Cancel and delete (Remove Download, Delete, Unsubscribe; the caller unlinks the .part and the file itself): as pn_dl_cancel, and the running one writes nothing more, never puts its file in place and removes its .part when it ends.
 * A download whose file is already in place (the thread may still be syncing the folder) is a finished episode: the drop flags nothing and the file is the caller's to keep or unlink. An add of the same episode before the thread has ended is queued afresh behind it. */
void pn_dl_drop(unsigned key);
/* Start the download thread for the queued downloads when it does not run (pn_dl_add does; the Podcasts page's timer asks again for a queue whose thread could not be made). The guards run first; when they fail every queued download fails with their code (shown on its row). 0 or PN_*. */
int pn_dl_start(void);
int pn_dl_running(void); /* the download thread is running */
int pn_dl_count(void); /* downloads queued or running */
int pn_dl_waiting(void); /* downloads queued and not running */
unsigned pn_dl_gen(
    void); /* moves with every step of progress (another percent, or another MB when the length is unknown) and every state change */
/* The state of an episode: PN_DL_NONE, PN_DL_WAIT (queued, or waiting to retry), PN_DL_ACTIVE (*got of *total bytes; total 0 = unknown), PN_DL_FAILED (*code PN_*). */
int pn_dl_state(unsigned key, int *code, unsigned *got, unsigned *total);
/* The download being fetched now: its key (0 when none) and its progress. */
unsigned pn_dl_current(unsigned *got, unsigned *total);
/* Forget the failure of an episode (its row is a plain remote one again, or Paused with a .part). */
void pn_dl_clear(unsigned key);
/* The n-th download the Downloads page lists, from 0: the queue in the order it was asked (dir, file, *code 0), then the failed ones (*code the PN_* reason). Returns its key, 0 past the last. dir and file take PC_FILE bytes. */
unsigned pn_dl_listed(int n, char *dir, char *file, int *code);
/* KB free on the file system of path (common.h m1_free_kb). The Downloads page's storage line. */
#define pn_free_kb m1_free_kb

/* ---- Search (docs/modules/podcasts.md "Search"). One job at a time, never beside a refresh (a download goes on). All of these run on the UI thread; the worker only
 * writes the record they read. The store's country is the Podcast Region (patch/pcregion.h): the search puts pcregion_code() after PN_SEARCH_URL's "country=", then "&term=". */
#define PN_SEARCH_URL "https://itunes.apple.com/search?media=podcast&entity=podcast&limit=25&country="
#define PN_LOOKUP_URL "https://itunes.apple.com/lookup?id="
/* Podcast Index's answers of the same shape and with the same parser (no key, no country; it refuses a request whose User-Agent does not name the application, which every request of ours does: patch/net.c NET_AGENT).
 * Used instead of the store's, never besides it, while Settings > Library > Podcasts > Podcast Directory says Podcast Index (pcdir_index, patch/podcasts.c): the search, and the lookup of a result's or a link's id. Discover's
 * charts and a chart row's lookup stay the store's whatever it says. */
#define PN_INDEX_SEARCH_URL "https://api.podcastindex.org/search?limit=25&term="
#define PN_INDEX_LOOKUP_URL "https://api.podcastindex.org/lookup?entity=podcast&id="
int pcdir_index(void); /* patch/podcasts.c: 1 when the chosen directory is Podcast Index */
#define PN_JSON_CAP 98304u /* a search or lookup answer over 96 KB is cut there (25 results are about 44 KB) */
#define PN_THUMB_CAP 262144u /* a result's artwork (about 5 KB) over this is refused */
#define PN_INDEX_THUMB_CAP \
    2097152u /* the same for a Podcast Index result: its artwork is the feed's own picture (often 3000 x 3000, 100 KB to 2 MB), shrunk after the download */
#define PN_SEARCH_DIR \
    "/mnt/mmc/.m1plus/podcasts/search" /* the thumbnails t<n>.jpg|png and the preview's cover preview.jpg: scratch, made again by every search */
#define PN_PREVIEW_COVER PN_SEARCH_DIR "/preview.jpg"

enum { PN_S_IDLE = 0, PN_S_QUERY = 1, PN_S_THUMBS = 2, PN_S_DONE = 3 };

/* What a text typed in the search field is: 0 a search term, 1 a feed address (http:// or https://, not an Apple Podcasts show link), 2 an Apple Podcasts show link (podcasts.apple.com ... /id<digits>; the digits into id, size bytes: ids pass 32 bits). */
int pn_classify(const char *text, char *id, unsigned size);
/* Start the search for the UTF-8 term: the guards, the old thumbnails removed, one worker (the query, then the artwork of each result one by one). 0 when it runs; PN_BUSY when a worker runs (the page waits and asks again). */
int pn_search(const char *term);
int pn_job_busy(void); /* a search or preview worker is running */
int pn_search_state(
    void); /* PN_S_*: the query runs / its answer is in and the artwork follows / the worker has ended */
int pn_search_code(
    void); /* the query's result once the answer is in (PN_OK, or PN_NET, PN_HTTP, ... and PN_CANCELLED) */
unsigned pn_search_gen(void); /* moves whenever the answer or a thumbnail arrives, and when the worker ends */
int pn_search_count(void); /* results (valid once the state is past PN_S_QUERY with PN_OK) */
const pj_result_t *pn_search_result(int i);
int pn_search_thumb(int i, char *path,
                    unsigned size); /* 1 and the path of result i's picture file when it has arrived */
void pn_search_clean(void); /* remove the thumbnails and forget the results */
/* Preview a show: the feed at url (an address), or the feed the store's lookup gives for the Apple id digits (id not empty), fetched and parsed as a refresh does, held in memory (not a show folder), with its picture shrunk to PN_PREVIEW_COVER. art: the store's artworkUrl600 of a search result ("" for none), used when the feed's picture fails; a lookup (id) brings its own. 0 when it runs. */
int pn_preview(const char *url, const char *id, const char *art);
/* The same for a chart row: the lookup of the Apple id is made in the store cc (the chart's), so a show of another store than the Podcast Region's still has its record. eid: an episode row's own
 * id ("" for a show row): then the store's episode lookup of the show is made too, after the feed, and the feed item that episode is is held (preview_match); its failure is no failure of the preview. */
int pn_preview_chart(const char *id, const char *cc, const char *eid);
int pn_preview_state(void); /* 0 none, 1 running, 2 done */
int pn_preview_code(void); /* PN_OK, or why not (PN_NOFEED: the lookup found no feed address) */
void *pn_preview_parser(void); /* the held pf_parser_t, NULL when none */
int pn_preview_match(
    void); /* the held feed's item index the chart's episode is (its index in pn_preview_parser), -1 when none or no episode */
const char *pn_preview_feed(void); /* the feed address of the held preview */
int pn_preview_cover(void); /* the preview's picture file is there */
void pn_preview_drop(void); /* free the held preview and its picture */
/* Subscribe to the held preview exactly as an import and its first refresh would: a folder named from the feed's title, .episodes, .show (feed, title, image, author, category, description), cover.jpg. root: the Podcasts folder; shows[0..nshows): the folders now there.
 * Returns PN_OK (*dir the folder's name, the preview dropped), PN_STORAGE when nothing could be written (nothing is left behind), PN_NOTFEED when no preview is held. UI thread, no network. */
int pn_subscribe(const char *root, const pc_show_t *shows, int nshows, char *dir, unsigned dsize);

/* ---- Discover (docs/modules/podcasts.md "Discover"): Apple's top 25 shows (kind 0) and top 25 episodes (kind 1) of the Podcast Region. The job (the one worker slot, never beside another) fetches a chart that is not held, then the artwork
 * of its rows one by one. The answers stay in memory for the session; a changed region asks again. All of these run on the UI thread; the worker only writes the record they read. */
#define PN_CHART_URL "https://rss.marketingtools.apple.com/api/v2/"
#define PN_CHART_SHOWS "/podcasts/top/25/podcasts.json"
#define PN_CHART_EPISODES "/podcasts/top/25/podcast-episodes.json"
/* Start the job for chart kind: the guards, then one worker. A request that fails with a network or server error is made up to three times; a storefront with no such chart (a 404, or no rows) answers with the United States' chart.
 * 0 when it runs; PN_BUSY when a worker runs (the page waits and asks again); else the guard's PN_*. A held chart is not fetched again, its artwork that was not tried is. */
int pn_chart(int kind);
int pn_chart_state(
    int kind); /* 0 none (or cancelled while asking), 1 the answer is being fetched, 2 answered: pn_chart_code says how */
int pn_chart_code(int kind); /* PN_OK, or why not (PN_NET, PN_HTTP, PN_GONE, ...) */
int pn_chart_count(int kind); /* rows of an answered chart (0 until then, and after a failure) */
int pn_chart_held(int kind); /* answered with rows for the storefront in use now (no request is needed) */
unsigned pn_chart_gen(void); /* moves with every answer, thumbnail and the end of a job */
const char *pn_chart_country(int kind); /* the storefront the answer is of: the region's, or "US" after a fall back */
const pj_chart_t *pn_chart_item(int kind, int i); /* row i (rank i + 1) of an answered chart, NULL out of range */
int pn_chart_thumb(int kind, int i, char *path,
                   unsigned size); /* 1 and the path of row i's picture file when it has arrived */
int pn_chart_pending(int kind); /* rows of a held chart whose artwork has not been tried */
void pn_chart_clean(void); /* remove the artwork files and forget that any was tried (the answers stay) */

/* ---- Find Cover & Lyrics (docs/modules/onlineart.md): album covers from the iTunes Search API then Deezer, lyrics from LRCLIB. One job at a time, never beside a refresh (a download goes on);
 * the same guards, libcurl options and thread rules as the search. All of these run on the UI thread; the worker only writes the record they read. */
#define PN_ART_MAX 12 /* covers offered: iTunes' first (at most PN_ART_ITUNES_MAX), Deezer's after them */
#define PN_ART_ITUNES_MAX 6
#define PN_ARTIST_MAX 6 /* photos offered for an artist: those under the very name first */
#define PN_ARTIST_OTHER 4 /* of them, at most this many of Deezer's under another name */
#define PN_ARTIST_NETEASE 2 /* ... and at most this many of NetEase's */
#define PN_NETEASE_MAX 10 /* NetEase's artists read (the request asks for 10) */
#define PN_ART_Q \
    96 /* a query field (artist, album, title), UTF-8 bytes with the NUL; longer is cut on a character boundary */
#define PN_LYR_MAX 20 /* lyrics candidates kept: the exact match, then LRCLIB's search results */
#define PN_LRC_CAP 49152u /* lyrics kept: a text that goes on ends at its last whole line */
#define PN_PICK_CAP 3145728u /* a cover picture larger than this is refused while it downloads */
#define PN_ART_DIR \
    "/mnt/mmc/.m1plus/art" /* scratch: the thumbnails a<n>.jpg|png, the larger picture full.jpg|png / pick.src and the lyrics l<n>.txt (until the page saves one) */
#define PN_ART_ITUNES "https://itunes.apple.com/search?media=music&entity=album&limit=8&term="
#define PN_ART_DEEZER "https://api.deezer.com/search/album?limit=8&q="
#define PN_ART_LRCLIB "https://lrclib.net/api/"
#define PN_ART_DEEZER_ARTIST "https://api.deezer.com/search/artist?limit=25&q="
#define PN_ART_NETEASE_ARTIST "https://music.163.com/api/search/get?type=100&limit=10&s="
#define PN_NETEASE_BLANK "/5639395138885805.jpg" /* the picture NetEase gives an artist that has none */
#define PN_NETEASE_THUMB "?param=250y250" /* NetEase's picture at 250 px (pn_art_full asks for 500y500) */

enum { PN_A_IDLE = 0, PN_A_COVERS = 1, PN_A_THUMBS = 2, PN_A_DONE = 3 };
enum { PN_SRC_ITUNES = 0, PN_SRC_DEEZER = 1, PN_SRC_NETEASE = 2 };

/* A lyrics candidate (LRCLIB record with lyrics): the texts are UTF-8, cut on a character boundary. */
typedef struct {
    char title[80], artist[56], album[80];
    unsigned secs; /* the record's length in seconds, 0 = unknown */
    int synced; /* it has syncedLyrics (else plain) */
} pn_lyr_t;

/* Start the lookup for artist, album and title (UTF-8; album may be empty: the title is then searched with the artist; seconds: the track's length, 0 = unknown) : the guards, the old files removed, one worker (iTunes,
 * Deezer, the thumbnails one by one, then the lyrics). 0 when it runs; PN_BUSY when a worker runs (the page waits and asks again); PN_MEM when a query does not fit. */
int pn_art(const char *artist, const char *album, const char *title, unsigned seconds);
/* A lookup fails fast: every request is made once. A busy answer (HTTP 503 or 429) is PN_OVERLOAD at once; a busy LRCLIB get skips the search, a busy iTunes still lets Deezer run. The page's Try Again asks again. */
enum { PN_PART_COVERS = 1, PN_PART_LYRICS = 2 };
/* Look up one part again with the query of the last pn_art (the other part's results stay as they are): PN_PART_COVERS or PN_PART_LYRICS. Same returns as pn_art. */
int pn_art_again(int part);
int pn_art_state(
    void); /* PN_A_*: the cover queries run / the answers are in and the thumbnails follow / the covers are done (the lyrics may still be coming: pn_lyr_state) */
int pn_art_code(
    void); /* the cover lookup's result once the answer is in: PN_OK (with pn_art_count() 0: no results), or why not */
int pn_art_count(void); /* covers (valid once the state is past PN_A_COVERS with PN_OK) */
unsigned pn_art_gen(void); /* moves whenever an answer, a thumbnail or the lyrics arrive, and when the worker ends */
int pn_art_thumb(int i, char *path,
                 unsigned size); /* 1 and the path of cover i's thumbnail picture when it has arrived */
int pn_art_thumb_state(int i); /* 0 not yet, 1 the picture is there, 2 it could not be had (the placeholder stays) */
/* Cover i's album, artist (UTF-8, "" when the service gave none) and source (PN_SRC_*); valid for 0 <= i < pn_art_count(). */
const char *pn_art_name(int i);
const char *pn_art_artist(int i);
int pn_art_source(int i);
/* The address of the larger picture for a thumbnail's url: the store's 100x100bb becomes 600x600bb, Deezer's 250x250 becomes 500x500; any other address is returned as it is. 1 when it fits out. */
int pn_art_full(const char *thumb, char *out, unsigned size);
/* Download cover i's larger picture for the confirmation page (the job slot; checked as a picture the loader takes: JPEG or PNG within pc_cover_ok). 0 when the worker runs; PN_BUSY, or a guard's code.
 * The result is pn_pick_state / pn_pick_code; the file is pn_art_full_path. */
int pn_art_fetch(int i);
int pn_art_full_path(
    int i, char *path,
    unsigned
        size); /* 1 and the path of the downloaded larger picture of cover i, when pn_art_fetch has completed for it */
void pn_art_full_drop(void); /* remove the downloaded larger picture (no worker must run) */
/* Lyrics: pn_lyr_state 0: the lookup has not answered, 1: it has (pn_lyr_code, pn_lyr_count). The candidates are in display order: LRCLIB's exact match (api/get) first, then api/search's records by how close their
 * length is to the track's (a synced one first among equals). */
int pn_lyr_state(void);
int pn_lyr_code(void); /* PN_OK (candidates), PN_NOLYRICS (no record has any), or the failure's PN_* */
int pn_lyr_count(void);
const pn_lyr_t *pn_lyr_get(int i); /* candidate i, NULL when out of range */
/* The lyrics text of candidate i: malloc'd (the caller frees), NUL-terminated, at most PN_LRC_CAP bytes; NULL when there is none or no memory. *n: its length. */
char *pn_lyr_text(int i, unsigned *n);
/* Write candidate i's lyrics to path (UI thread, atomically: path.tmp then rename; the card only). 1 when written. */
int pn_lyr_save(int i, const char *path);
/* Make the cover the user picked: shrink picture i's larger version into the cache file of each non-zero key (the cover cache, ART_DIR/<key>-168.jpg, and a .pick marker beside it that Rebuild Covers
 * honours) and, when dir is not empty, put the original JPEG into that folder as the folder picture stock's Now Playing reads. The larger picture is the one pn_art_fetch downloaded for i, else it is
 * downloaded now. 0 when the worker runs; PN_BUSY, or a guard's code. */
int pn_art_pick(int i, const char *dir, unsigned key0, unsigned key1);
/* Find Artist Photo (docs/modules/onlineart.md "Artist photos"): the same lookup for an artist's name alone. The covers part is the artist search of Deezer, then NetEase's: Deezer's artists
 * under the very name, then NetEase's (those of the very name, else its first; at most PN_ARTIST_NETEASE), then at most PN_ARTIST_OTHER of Deezer's others, the most followed first in each, PN_ARTIST_MAX in all, each with a picture
 * of its own; pn_art_name is the artist, pn_art_artist "", the source PN_SRC_DEEZER or PN_SRC_NETEASE. A service that fails while the other answers is left out without a word. There is no lyrics part (pn_art_again takes
 * PN_PART_COVERS only). Thumbnails, pn_art_fetch and the larger picture as for a cover. Same returns as pn_art. */
int pn_artist(const char *name);
/* Make picture i the photo of the artist with this key (patch/artistphoto.c ap_key, ap_pick: both cache files and the .pick marker). 0 when the worker runs; PN_BUSY, or a guard's code. The result is pn_pick_state /
 * pn_pick_code (PN_STORAGE: the files could not be made). */
int pn_artist_pick(int i, unsigned key);
int pn_pick_state(void); /* 0 none, 1 running, 2 done */
int pn_pick_code(
    void); /* PN_OK: the cover is in the cache (or, after pn_art_fetch, the picture is there); else why not */
void pn_art_clean(
    void); /* remove the thumbnails, the larger picture and the held lyrics, forget the results (no worker must run) */

/* ---- Software Update (docs/modules/update.md): the newest release of the project from GitHub, downloaded to the card as update.bin for stock's own TF card update. Two jobs of the one worker slot (never beside
 * another job; the Podcasts downloads go on). All of these run on the UI thread; the worker only writes the record they read. Cancel is pn_cancel(PN_K_UPDATE). */
#define PN_UP_DIR "/mnt/mmc"
#define PN_UP_FILE PN_UP_DIR "/update.bin" /* where stock's TF card update looks */
#define PN_UP_PART PN_UP_FILE ".part" /* the download, until it is checked */
#define PN_UP_NEED_KB \
    112640u /* free on the card before a download starts: 110 MB (the package is about 55 MB, and the one it replaces stays until the rename) */
#define PN_UP_LOC 256 /* the longest redirect address the check reads the tag from; a longer one is no release news */
#define PN_UP_CAP 134217728u /* a package larger than this (128 MB) is refused while it downloads */

enum {
    PN_U_IDLE = 0, /* nothing checked (also after a check that was cancelled) */
    PN_U_CHECKING = 1,
    PN_U_CHECKED = 2, /* pn_up_result says what the check found */
    PN_U_DOWNLOADING = 3,
    PN_U_DOWNLOADED = 4, /* update.bin on the card is the package of pn_up_tag() */
    PN_U_FAILED = 5 /* pn_up_code() is why, pn_up_stage() which job */
};
enum {
    PN_U_CURRENT = 1,
    PN_U_AVAILABLE = 2
}; /* pn_up_result: the build is as new as the latest release / a release is offered */

/* Ask GitHub for the latest release: the guards (card, Wi-Fi, clock, CA bundle), then the worker. 0 when it runs; PN_BUSY when another job runs; else the guard's PN_* (also the state: PN_U_FAILED). */
int pn_up_check(void);
/* Download the release the last check offered: the guards, a card with PN_UP_NEED_KB free (PN_CARDFULL), then the worker. Same returns, and PN_UPCHECK when no release is offered. */
int pn_up_download(void);
int pn_up_state(void); /* PN_U_* */
int pn_up_code(
    void); /* the failure's PN_*: PN_NOWIFI, PN_NOCLOCK, PN_NOCERT, PN_CERT, PN_NET, PN_UPCHECK, PN_UPBAD, PN_CARDFULL, PN_STORAGE, PN_MEM, PN_CANCELLED */
int pn_up_stage(void); /* 1 the check, 2 the download: the job of the last failure or the running one */
int pn_up_result(void); /* PN_U_CURRENT, PN_U_AVAILABLE, or 0 (no check has found anything) */
const char *pn_up_tag(void); /* the offered release ("1.0.1"), "" when none */
unsigned pn_up_pct(void); /* the download's progress, 0..100 */
/* The notes of the offered release (GitHub's release body, cleaned for the screen, at most UP_NOTES_MAX bytes of UTF-8), "" when there are none. Memory only; the next check forgets them. */
const char *pn_up_notes(void);
#define PN_UP_API_CAP 65536u /* the release JSON is read up to this many bytes; a larger answer gives no notes */
/* Forget an old answer or failure when the page opens (nothing while a job runs; a download whose file is still on the card is kept). */
void pn_up_reset(void);

/* ---- AutoEq (docs/modules/peq.md "AutoEq download", patch/autoeq.c is the page): the project's index of equalization results, and one headphone's ParametricEQ.txt. One worker in the job slot (never beside another job); the same
 * guards, libcurl options and thread rules as the others. All of these run on the UI thread; the worker only writes the record they read. */
#define PN_EQ_BASE "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/"
#define PN_EQ_DIR "/mnt/mmc/.m1plus/autoeq"
#define PN_EQ_INDEX \
    PN_EQ_DIR "/index.md" /* the list as the project writes it (results/INDEX.md), whole; the page reads it in place */
#define PN_EQ_PART PN_EQ_DIR "/index.part" /* the list while it downloads */
#define PN_EQ_STAMP PN_EQ_DIR "/updated" /* the clock (seconds, decimal) when the list was last downloaded whole */
#define PN_EQ_MAX_AGE \
    2592000u /* 30 days: an older list is downloaded again when the page opens (the old one serves until then) */
#define PN_EQ_PRESET \
    PN_EQ_DIR \
    "/preset.part" /* the preset the last pn_eq_get fetched: the stamp line, then the file as the project has it */
#define PN_EQ_INDEX_CAP 3145728u /* the list is 0.85 MB; a larger answer is refused while it downloads */
#define PN_EQ_FILE_CAP 16384u /* a preset is at most what the parser reads (PEQ_FILE_LIMIT) */

enum { PN_E_IDLE = 0, PN_E_RUNNING = 1, PN_E_DONE = 2, PN_E_FAILED = 3 };

/* See All (docs/modules/podcasts.md "All episodes"): the show's feed fetched again with every item kept, into its .archive. pn_arch_start: the guards, then the worker (0 when it runs; PN_BUSY while another job
 * runs, the page asks again; PN_NOFEED for a show with no feed address). State: PN_AR_*, of the show pn_arch_hash() (pc_show_t.hash); after a failure pn_arch_code() is the PN_* why. pn_arch_reset forgets a
 * finished job (nothing while one runs). A finished job bumps pn_gen. */
enum { PN_AR_IDLE = 0, PN_AR_RUNNING = 1, PN_AR_DONE = 2, PN_AR_FAILED = 3 };
int pn_arch_start(const char *root, const pc_show_t *s);
int pn_arch_state(void);
int pn_arch_code(void);
int pn_arch_failed(
    unsigned
        hash); /* the PN_* the last job of that show failed with (not a cancel), 0 when it did not; kept until the next start of that show, a success or a cancel */
unsigned pn_arch_count(
    void); /* the items the running attempt has written to the archive so far (0 at the start of every attempt) */
unsigned pn_arch_hash(void);
void pn_arch_reset(void);

/* Download the list (the guards, then the worker): it is renamed over PN_EQ_INDEX only when it came whole and starts with the project's heading. 0 when the worker runs; PN_BUSY when another job runs; else the guard's PN_*
 * (also the state: PN_E_FAILED). */
int pn_eq_index(void);
/* Download the ParametricEQ.txt of the headphone at path (below PN_EQ_BASE as the index writes it: "Source/Kind/Name", percent-encoded; anything else is PN_NOFEED) into PN_EQ_PRESET, stamp and a line feed first. Same returns. */
int pn_eq_get(const char *path, const char *stamp);
int pn_eq_state(void); /* PN_E_* */
int pn_eq_code(
    void); /* the failure's PN_*: PN_NOWIFI, PN_NOCLOCK, PN_NOCERT, PN_CERT, PN_NET, PN_GONE, PN_HTTP, PN_NOTFEED, PN_CARDFULL, PN_STORAGE, PN_MEM, PN_CANCELLED */
int pn_eq_mode(void); /* the job of the state: 0 the list, 1 a preset */
void pn_eq_reset(void); /* forget a finished job (nothing while one runs) */
