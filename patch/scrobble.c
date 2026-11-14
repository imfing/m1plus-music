/* M1+ Music offline scrobbling: every listen appended to /mnt/mmc/.scrobbler.log in Rockbox's AudioScrobbler portable player format, for any
 * .scrobbler.log uploader (Last.fm, ListenBrainz) once the card is in a computer (docs/modules/scrobble.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The listen rule, the log line and the header follow q2-pod (patch/scrobble.c, docs/internals.md "Play counts" and "Scrobbling").
 *
 * No hook of its own. Two entry points:
 *   scrobble_note     the poll: the page timers that already look at the playing track call it, lit and dark (Now Playing and the mini bar
 *                     through recent_note; the Podcasts, iPod, Cassette and Vinyl pages). It asks the player at most every SC_POLL_MS and reads the player's position and counts a step forward as heard when the step is no longer than the
 *                     wall time since the last look plus SC_SLACK_S: a seek or a resume jump adds nothing, a pause adds nothing, and the period
 *                     does not matter (500 ms, 1 s dark, a page left for minutes and come back to on the same track). A main-loop poll would
 *                     call the same function.
 *   scrobble_started  the tag reader's hook (pc_id3_path, every fresh parse: a track start, Memory Playback at boot included) for a path that is not
 *                     a podcast: the file's tags stock has just parsed are kept, and the track starts at second 0 now. The track it replaces gets
 *                     the time since its last look, at most up to its length, before it is judged. Only time_now_ms is called (the player is not asked); a log write only for that
 *                     track, so never at boot.
 * A track longer than SC_MIN_S is a listen once SC_MAX_S or half its length has been heard; it is logged then (so the last track is not lost when
 * the player is switched off), once per play; a line that could not be written (no clock yet, no card, the kill switch, the log not opened) is tried again at the next look.
 * A play starts again when the position falls back under SC_SLACK_S from SC_SLACK_S or more (repeat one, the start again); its start time is its
 * second 0, pinned to the wall clock at the first look with a set clock (a pause does not move it). Not logged: podcasts, a track without an artist (or "Unknown"), a length the player never gave (a track no timer saw), a clock
 * before SC_CLOCK_MIN (until it is set).
 * The setting (Settings > Library > Scrobbling, SCROBBLE_FILE: "1" on, anything else or no file OFF, the default) is read once, by the first poll, and kept in RAM; while it
 * is off the poll returns before it asks the player, and the hook (which never reads a file) does nothing until a poll has read it on.
 *
 * The automatic upload (sa_*, docs/modules/scrobble.md "Automatic upload") has no clock but the poll: sc_line counts the listens it writes, and scrobble_note, while any
 * are counted, looks once a minute at most whether an upload (patch/scrobup.c, owner SCROBUP_AUTO) may start, and collects its result. Nothing of it runs at boot, in the
 * main loop or from the tag reader's hook; with nothing counted the poll pays two compares for it.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "home.h"
#include "common.h"
#include "podcasts.h"
#include "scrobble.h"
#include "scrobup.h"

/* The log's lock (scrobble.h): a zeroed pthread mutex (24 bytes on MIPS glibc), as the cover worker's. */
static unsigned sc_mutex[8] __attribute__((section(".scratch"), aligned(8)));

void scrobble_lock(void) { pthread_mutex_lock(sc_mutex); }
void scrobble_unlock(void) { pthread_mutex_unlock(sc_mutex); }

static struct {
    unsigned key; /* the track: FNV-1a of its path with the CUE start mixed in, 0 none */
    int len; /* seconds, the player's; 0 unknown */
    int pos; /* the position at the last look; -1 none yet (the first look only sets it) */
    unsigned seen_ms; /* time_now_ms of the last look (or of the start) */
    unsigned start_ms; /* time_now_ms of this play's second 0 (the start, or the first look less its position) */
    unsigned
        start; /* this play's start on the wall clock, pinned at the first look with a set clock; 0 not yet (the log line then takes start_ms) */
    unsigned heard; /* seconds heard in this play */
    int done; /* this play is logged (or judged not to be) */
    int track; /* the record's track number, 0 none, -1 not looked at yet (the first timer look reads it: the tag reader's hook asks stock nothing) */
    int set; /* the setting: 0 not read yet, 1 off, 2 on */
    char artist[SC_STR], album[SC_STR], title[SC_TITLE];
} sc __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * The setting
 */
static int sc_on(void) {
    if (!sc.set) sc.set = set_read(SCROBBLE_FILE, 0) == '1' ? 2 : 1;
    return sc.set == 2;
}

int scrobble_setting(void) { return sc_on(); }

int scrobble_toggle(void) {
    int next = !sc_on();
    if (home_write_atomic(SCROBBLE_FILE, SCROBBLE_TMP, next ? "1\n" : "0\n") != 0) return -1;
    sc.set = next ? 2 : 1;
    sc.key = 0; /* on: the next poll starts from its first look; off: the track is forgotten */
    return next;
}

/* ---------------------------------------------------------------------------
 * The automatic upload
 */
static struct {
    int set; /* Auto Upload: 0 not read yet, 1 off, 2 on */
    int job; /* an upload this file started whose result is not collected yet */
    int stop; /* no more automatic uploads this boot: one had listens refused and none taken */
    int fail; /* the last one failed, or could not start: none before fail_ms + SA_RETRY */
    unsigned
        pending; /* the listens written since the last automatic upload that went through (those of earlier boots are not counted: they go with the first upload) */
    unsigned took; /* pending at the job's start */
    unsigned first_ms; /* time_now_ms of the first of them */
    unsigned eval_ms, fail_ms, start_ms; /* the last look at the conditions, the last failure, the job's start */
} sau __attribute__((used, section(".scratch"))); /* (used: kept as one object, the tests read it) */

static int sa_on(void) {
    if (!sau.set) sau.set = set_read(SCROBBLE_AUTO_FILE, 0) == '1' ? 2 : 1;
    return sau.set == 2;
}

int scrobble_auto_setting(void) { return sa_on(); }

int scrobble_auto_toggle(void) {
    int next = !sa_on();
    if (home_write_atomic(SCROBBLE_AUTO_FILE, SCROBBLE_AUTO_TMP, next ? "1\n" : "0\n") != 0) return -1;
    sau.set = next ? 2 : 1;
    return next;
}

/* An automatic upload that is over: its result is taken (the worker is free again) and applied, without a word. Also called by the settings pages (patch/scrobpage.c), so
 * that a job nobody collected (the music stopped) never blocks the user's own start. Somebody else's job is left alone. */
void scrobble_auto_collect(void) {
    int sent = 0, r;
    if (!scrobup_busy() || scrobup_owner() != SCROBUP_AUTO) {
        sau.job = 0;
        return;
    }
    /* (a refused account: the poll keeps Invalid Token, or Last.fm's refusal, and sa_tick starts nothing while no other service is usable; with one, the next upload
     * leaves the refused service out) */
    r = scrobup_poll(&sent);
    if (!r) return;
    sau.job = 0, sau.fail = 0;
    if (!sent && scrobup_rejected() > 0)
        sau.stop = 1; /* the service takes nothing: the log is not drained into .rejected run after run */
    if (r == SCROBUP_OK) { /* what was logged meanwhile still waits */
        sau.pending = sau.pending > sau.took ? sau.pending - sau.took : 0;
        sau.first_ms = sau.start_ms;
    } else if (r != SCROBUP_AUTH)
        sau.fail = 1, sau.fail_ms = time_now_ms();
}

/* From the poll, while listens wait or a job runs. Once SA_EVAL at most: Auto Upload on, the first waiting listen SA_WAIT old, SA_RETRY since a failure, no job, no USB
 * mode, the Wi-Fi connected (it is never switched on), a service that is set up and not refused (ListenBrainz or Last.fm). scrobup_start looks at the kill switch and the card. */
static void sa_tick(void) {
    unsigned now;
    if (sau.job) {
        scrobble_auto_collect();
        return;
    }
    if (sau.stop || !sa_on()) return;
    now = time_now_ms();
    if (now - sau.eval_ms < SA_EVAL * 1000u) return;
    sau.eval_ms = now;
    if (now - sau.first_ms < SA_WAIT * 1000u || (sau.fail && now - sau.fail_ms < SA_RETRY * 1000u)) return;
    if (scrobup_busy() || navigator_window_is_exist(SCROBUP_USB_PAGE) || get_wifisignal() <= 0) return;
    /* the card's scrobble.ini as it is now (it may have been written on a computer since it was last read): one read a look that gets this far, so one a minute at most
     * and only while there is no usable account (with one the upload starts here). No card is no account */
    scrobup_forget();
    if (!scrobup_usable()) return;
    sau.took = sau.pending, sau.start_ms = now;
    if (scrobup_start(SCROBUP_AUTO) == 1)
        sau.job = 1;
    else
        sau.fail = 1, sau.fail_ms = now; /* the kill switch, no card, no thread: not every minute */
}

/* ---------------------------------------------------------------------------
 * The listens
 */
static unsigned sc_key(const char *path, int cue) {
    unsigned h = FNV_SEED;
    for (; *path; ++path) h = (h ^ (unsigned char)*path) * 16777619u;
    h = (h ^ (unsigned)cue) * 16777619u; /* a CUE image's tracks share one path */
    return h | !h;
}

static int sc_eq(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* A tag into a field: control bytes (a tab or a newline would break the line) become spaces, cut before a UTF-8 continuation byte. */
static void sc_copy(char *out, unsigned size, const char *s) {
    unsigned n = 0;
    while (n + 1 < size && s[n]) {
        unsigned char c = (unsigned char)s[n];
        out[n] = c < 0x20 || c == 0x7f ? ' ' : (char)c;
        ++n;
    }
    if (s[n])
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    out[n] = 0;
}

/* The file name of a path less its extension: the title of a track without one. */
static void sc_name(char *out, unsigned size, const char *path) {
    const char *b = path, *dot = 0, *p;
    unsigned n = 0;
    for (p = path; *p; ++p)
        if (*p == '/')
            b = p + 1, dot = 0;
        else if (*p == '.')
            dot = p;
    if (!dot || dot == b) dot = p;
    while (b + n < dot && n + 1 < size) ++n;
    sc_copy(out, n + 1, b);
}

/* Appends the listen; 0 when it is on the card (or cannot be finished: a short write is not repeated, which would leave the half line twice), -1 to try again
 * at the next look (no clock yet, no card, the kill switch, the log not opened or nothing written). */
static int sc_line(unsigned now_ms) {
    char buf[SC_LINE], num[12];
    unsigned now = (unsigned)time((long *)0), n;
    int fd, w;
    if (now < SC_CLOCK_MIN || !m1_card_mounted() || home_off()) return -1;
    scrobble_lock(); /* the upload's rewrite holds it too: the line goes into the log that stays, whole (patch/scrobup.c) */
    fd = open(SC_LOG, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) {
        scrobble_unlock();
        return -1;
    }
    num[0] = 0;
    if (sc.track > 0) snprintf(num, sizeof num, "%d", sc.track);
    n = (unsigned)snprintf(buf, sizeof buf, "%s%s\t%s\t%s\t%s\t%d\tL\t%u\t\n", lseek(fd, 0, 2) == 0 ? SC_HEADER : "",
                           sc.artist, sc.album, sc.title, num, sc.len,
                           sc.start ? sc.start : now - (now_ms - sc.start_ms) / 1000);
    w = n < sizeof buf ? write(fd, buf, n) : (int)n; /* (the fields are bounded: never too long) */
    fsync(fd);
    close(fd);
    scrobble_unlock();
    if (w > 0 && !sau.pending++) sau.first_ms = now_ms; /* the automatic upload's count */
    return w > 0 ? 0 : -1;
}

/* Heard enough: logged once per play; a line not written is tried again at the next look. */
static void sc_judge(unsigned now) {
    if (sc.done || !sc.key || sc.len <= SC_MIN_S) return;
    if (sc.heard < SC_MAX_S && sc.heard * 2 < (unsigned)sc.len) return;
    if (sc.artist[0] && !sc_eq(sc.artist, "Unknown") && sc_line(now) != 0) return;
    sc.done = 1;
}

/* The track is over: the time since its last look, as far as its end, then judged. */
static void sc_leave(unsigned now) {
    if (sc.key && !sc.done && sc.len > 0 && sc.pos >= 0) {
        unsigned gap = (now - sc.seen_ms) / 1000, left = sc.pos < sc.len ? (unsigned)(sc.len - sc.pos) : 0;
        sc.heard += gap < left ? gap : left;
        sc_judge(now);
    }
    sc.key = 0;
}

/* A play from second pos (0 or more) of the track now, or from the first look's position (pos -1). */
static void sc_play(int pos, unsigned now) {
    sc.heard = 0, sc.done = 0, sc.start = 0, sc.start_ms = now - (unsigned)(pos > 0 ? pos : 0) * 1000u;
}

static void sc_begin(unsigned key, int pos, unsigned now) {
    sc.key = key, sc.len = 0, sc.pos = pos, sc.seen_ms = now, sc.track = -1;
    sc_play(pos, now);
}

/* The tags: stock's parsed struct (the file's tags, or the record's for a CUE track) when it is this track's, else the record's (rec). */
static void sc_tags(const char *info, void *rec, const char *path) {
    const char *title = info ? info + 0x684 : cc_str(rec, REC_TITLE);
    sc_copy(sc.artist, sizeof sc.artist, info ? info + 0x504 : cc_str(rec, REC_ARTIST));
    sc_copy(sc.album, sizeof sc.album, info ? info + 0x404 : cc_str(rec, REC_ALBUM));
    if (*title)
        sc_copy(sc.title, sizeof sc.title, title);
    else
        sc_name(sc.title, sizeof sc.title, path);
}

void scrobble_started(const char *info, const char *path) {
    unsigned key, now;
    if (sc.set != 2) return; /* off, or not read yet (no file is read here: this runs at boot) */
    key = sc_key(path, I(info, 0x400));
    if (key == sc.key) return;
    now = time_now_ms();
    sc_leave(now);
    sc_begin(key, 0, now);
    sc_tags(info, (void *)0, path);
}

void scrobble_note(void *t) {
    const char *path, *info = (const char *)PLAYSONG_ID3INFO;
    unsigned key, now;
    int pos = 0, len = 0, cue;
    if (sau.job || sau.pending)
        sa_tick(); /* the automatic upload: nothing but these two compares while no listen waits */
    if (!t || !sc_on()) return; /* (for a moment between two tracks the player has none) */
    path = cc_str(t, REC_PATH);
    now = time_now_ms();
    if (!*path || pc_is_path(path)) { /* a podcast (or a stream): not scrobbled, and the track before it is over */
        sc_leave(now);
        return;
    }
    cue = I(t, REC_CUE_START);
    key = sc_key(path, cue);
    if (key !=
        sc.key) { /* a start the tag reader did not report (its cache, or a start before the payload looked): from the first look on */
        sc_leave(now);
        sc_begin(key, -1, now);
        sc_tags(sc_eq(info, path) && I(info, 0x400) == cue ? info : (const char *)0, t, path);
    } else if (sc.pos >= 0 && now - sc.seen_ms < SC_POLL_MS)
        return; /* looked a moment ago */
    if (sc.track < 0) sc.track = I(t, REC_TRACK);
    if (get_playtimeandlength(&pos, &len) != 1 || len <= 0 || pos < 0) return;
    sc.len = len;
    if (sc.pos < 0)
        sc_play(pos, now); /* the first look: the play began pos seconds ago */
    else {
        int step = pos - sc.pos;
        if (step > 0 && (unsigned)step <= (now - sc.seen_ms) / 1000 + SC_SLACK_S)
            sc.heard += (unsigned)step;
        else if (pos < SC_SLACK_S && sc.pos >= SC_SLACK_S)
            sc_play(pos, now); /* back to the start: repeat one, or the start again; a new play */
    }
    if (!sc.start) { /* the wall clock of second 0, once the clock is set: a pause after it does not move it */
        unsigned wall = (unsigned)time((long *)0);
        if (wall >= SC_CLOCK_MIN) sc.start = wall - (now - sc.start_ms) / 1000;
    }
    sc.pos = pos, sc.seen_ms = now;
    sc_judge(now);
}
