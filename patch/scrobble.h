/* M1+ Music offline scrobbling (patch/scrobble.c, docs/modules/scrobble.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* The poll: the track the player is on (cc_playing(), NULL when none). Called by the page timers that already look at the playing track
 * (recent_note: Now Playing's and the mini bar's; the Podcasts, iPod, Cassette and Vinyl pages'); any period works (the player is asked at most every
 * SC_POLL_MS), so a main-loop poll could call it too. */
void scrobble_note(void *track);
/* A track starts (the tag reader's hook, pc_id3_path, for a path that is not a podcast): info is stock's freshly parsed id3 struct. */
void scrobble_started(const char *info, const char *path);
/* Settings > Library > Scrobbling: the switch's state (off unless SCROBBLE_FILE holds "1"), and a flip of it (the new state, -1 when it could not be saved). */
int scrobble_setting(void);
int scrobble_toggle(void);

/* The automatic upload (Settings > Library > Scrobbling > Auto Upload, SCROBBLE_AUTO_FILE, off by default): the switch's state and a flip of it, as above. While it is on,
 * scrobble_note starts an upload (patch/scrobup.c, owner SCROBUP_AUTO) once listens logged this boot have waited SA_WAIT, with a token and the Wi-Fi connected, and collects
 * its result; nothing is ever shown.
 * scrobble_auto_collect: an automatic upload that is over is polled and its result applied, silently (nothing happens while it runs, or for somebody else's job). The
 * settings pages call it before they look at the worker, so that a job the poll did not collect (the music stopped) does not block the user's upload. */
int scrobble_auto_setting(void);
int scrobble_auto_toggle(void);
void scrobble_auto_collect(void);

/* The log, and the lock every writer of it holds: the UI thread's append of one line (open to close, nothing else), and the upload thread's reads and its one rewrite
 * (patch/scrobup.c). Never held across a network call. */
#define SC_LOG "/mnt/mmc/.scrobbler.log"
#define SC_HEADER "#AUDIOSCROBBLER/1.1\n#TZ/UTC\n#CLIENT/M1+ Music\n"
void scrobble_lock(void);
void scrobble_unlock(void);
