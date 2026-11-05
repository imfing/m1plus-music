/* Navidrome/Subsonic protocol support (patch/subsonic.c).
 *
 * The player keeps server IDs as opaque strings: Navidrome uses UUID/MD5 IDs.
 * Stream URLs always request format=raw so the server does not transcode.
 */
#pragma once

#define SB_ID 96
#define SB_TEXT 192
#define SB_URL 1024
#define SB_MAX 64

typedef struct {
    char id[SB_ID];
    char title[SB_TEXT];
    char artist[SB_TEXT];
    char album[SB_TEXT];
    char cover[SB_ID];
    char suffix[12];
    unsigned duration;
    unsigned track;
    unsigned disc;
    unsigned size;
    unsigned bitrate;
    unsigned sample_rate;
    unsigned bit_depth;
} sb_song_t;

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
 * getRandomSongs). Fields absent from a response remain empty/zero. Returns
 * count, or -1 for malformed/failed API responses. */
int sb_songs(const char *json, unsigned n, sb_song_t *out, int max);

/* Runtime integration: opens a Subsonic browser in an already opened page window. */
void sb_page_open(void *win);
void sb_page_close(void);
/* Cached Navidrome cover for a currently queued stream, or NULL. */
const char *sb_cover_file(void *track);
