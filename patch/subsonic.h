/* Navidrome/Subsonic protocol support (patch/subsonic.c).
 *
 * The player keeps server IDs as opaque strings: Navidrome uses UUID/MD5 IDs.
 * Stream URLs always request format=raw so the server does not transcode.
 */
#pragma once

#include <stddef.h>

#define SB_ID 96
#define SB_TEXT 192
#define SB_META 96
#define SB_URL 1024
#define SB_MAX 64
#define SB_QUEUE_MAX 4096
#define SB_LIBRARY_EMPTY_HINT "Update Local Music or sync Navidrome first"
#define SB_LIBRARY_LOADING_HINT "Loading Navidrome library"
#define SB_LIBRARY_NO_MATCH_HINT "No matching songs in this category"

enum {
    SB_LIBRARY_FILTER_NONE,
    SB_LIBRARY_FILTER_ALBUM,
    SB_LIBRARY_FILTER_ARTIST,
    SB_LIBRARY_FILTER_ALBUM_ARTIST,
    SB_LIBRARY_FILTER_COMPOSER,
    SB_LIBRARY_FILTER_GENRE
};

enum { SB_LIBRARY_LOCAL, SB_LIBRARY_STREAM, SB_LIBRARY_OFFLINE };

typedef struct {
    char id[SB_ID];
    char title[SB_TEXT];
    char artist[SB_TEXT];
    char album[SB_TEXT];
    char album_artist[SB_META];
    char composer[SB_META];
    char genre[SB_META];
    char cover[SB_ID];
    char suffix[12];
    unsigned duration;
    unsigned track;
    unsigned disc;
    unsigned size;
    unsigned bitrate;
    unsigned sample_rate;
    unsigned bit_depth;
    unsigned created;
} sb_song_t;

/* A read-only view of the committed index on the SD card. The mmap keeps the
 * large catalog out of heap memory; callers must close it before leaving a
 * page. */
typedef struct {
    const sb_song_t *songs;
    unsigned count;
    unsigned dsd_count;
    size_t mapping_size;
    void *mapping;
} sb_library_index_t;

typedef struct {
    unsigned *hashes;
    unsigned count;
} sb_library_downloads_t;

typedef struct {
    const void *local_record;
    const sb_song_t *server_song;
    const char *stream_url; /* a retained raw URL, used for persisted recent-history rows */
    unsigned server_index;
    int source;
} sb_library_queue_entry_t;

/* Build an authenticated Subsonic URL. base is an HTTPS server root without
 * /rest; password is converted to a salted Subsonic token and never placed in
 * the URL. IDs and arguments are escaped. 0 on success, -1 on invalid input. */
int sb_url(char *out, unsigned cap, const char *base, const char *method, const char *id, const char *user,
           const char *password, const char *extra);

/* Format one page of the full-library search3 sync. */
int sb_sync_query(char *out, unsigned cap, unsigned offset);

/* Build a queue display filename with the server's original suffix. */
int sb_track_filename(char *out, unsigned cap, const sb_song_t *song);

/* Parse songs in one Subsonic JSON response (getAlbum, getPlaylist, search3,
 * getRandomSongs). Missing fields remain empty/zero; overlong display metadata
 * is safely truncated. Returns count, or -1 for malformed/failed responses. */
int sb_songs(const char *json, unsigned n, sb_song_t *out, int max);

/* Runtime integration: opens a Subsonic browser in an already opened page window. */
void sb_page_open(void *win);
void sb_page_close(void);
/* Cached Navidrome cover for a currently queued stream, or NULL. */
const char *sb_cover_file(void *track);

/* Library overlay helpers. They use only the already-synced index and saved
 * SD credentials; opening the view never contacts the server or starts a sync. */
int sb_library_index_open(sb_library_index_t *index);
void sb_library_index_close(sb_library_index_t *index);
int sb_library_downloads_open(sb_library_downloads_t *downloads);
void sb_library_downloads_close(sb_library_downloads_t *downloads);
int sb_library_downloads_contains(const sb_library_downloads_t *downloads, const sb_song_t *song);
int sb_library_stream_url(const sb_song_t *song, char *out, unsigned cap);
int sb_library_offline_path(const sb_song_t *song, char *out, unsigned cap);
int sb_library_cover_url(const sb_song_t *song, char *out, unsigned cap);
int sb_library_is_dsd(const sb_song_t *song);
int sb_library_matches(const sb_song_t *song, int filter, const char *name, const char *artist);
int sb_library_play_queue(const sb_library_queue_entry_t *entries, unsigned count, int at, int how);
int sb_library_play_recent(void *record); /* replay a Navidrome stream remembered by the stock Recent lists */
