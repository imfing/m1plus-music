/* M1+ Music scrobble upload: the card's .scrobbler.log sent to ListenBrainz and Last.fm, and the two accounts (patch/scrobup.c, docs/modules/scrobble.md "Upload").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* scrobup_poll's results once the job is over. */
#define SCROBUP_OK \
    1 /* an upload: every listen of the log was taken or refused for good (*sent taken, scrobup_rejected() refused; both 0: there was nothing to upload). A check: the token is valid, the user name is stored */
#define SCROBUP_FAIL \
    (-1) /* a request failed (no network, a timeout, a certificate, any answer but 200, 400 and 401), the kill switch appeared, or there was no memory. A check: also an answer that is not the service's, and a token changed meanwhile */
#define SCROBUP_AUTH \
    (-2) /* a service refused its account: ListenBrainz the token (401; a check: "valid": false), Last.fm the credentials (error 4, 10, 13, 26). scrobup_auth says which. The file is not changed */
#define SCROBUP_DISK \
    (-3) /* an upload: the card did not take the archives or the new log (or is gone): the listens sent stay in the log and go again. A check: the user name could not be written to the card's scrobble.ini */

/* scrobup_kind: the job that runs, or the last one. */
#define SCROBUP_UPLOAD 0
#define SCROBUP_CHECK 1 /* ListenBrainz: validate-token */
#define SCROBUP_LFCHECK 2 /* Last.fm: auth.getMobileSession */

/* The services, as bits (scrobup_auth). */
#define SCROBUP_LB 1
#define SCROBUP_LF 2

/* scrobup_lastfm: the Last.fm account. */
#define SCROBUP_LF_NONE \
    0 /* not set: no card, no file, no [LASTFM] section, or one of its four keys missing or unusable */
#define SCROBUP_LF_NEW 1 /* set, and not asked of the service since the boot (or since the file changed) */
#define SCROBUP_LF_IN 2 /* signed in: a session made from these credentials is kept (RAM only) */
#define SCROBUP_LF_BAD 3 /* the service refused these credentials (RAM only, as Invalid Token) */

/* Who starts a job polls it, and nobody else does: the settings pages (patch/scrobpage.c), or the automatic upload (patch/scrobble.c). */
#define SCROBUP_UI 0
#define SCROBUP_AUTO 1

/* stock's window while a computer has the card (navigator_to at 0x4cf2bc; ui/usbmode_page.bin): no caller starts an upload while it exists. */
#define SCROBUP_USB_PAGE "usbmode_page"

/* All of these are for the UI thread only. One thread at most: an upload and a check never run together.
 * scrobup_start: an upload. 1 a thread was started, 0 a job is running already (or is over and not polled yet), -1 it cannot start: the kill switch, no mounted card, no
 * service set up in the card's scrobble.ini (read at every start, whatever is kept in RAM), or no thread. The Scrobbling switch is not asked (it gates the logging only).
 * scrobup_check_start: the token is asked of the service (validate-token). The same results (the token is on the card: no card, no check).
 * scrobup_busy: 1 from a start until the poll that returned its result. scrobup_kind: which job that is. scrobup_owner: who started it (SCROBUP_UI or SCROBUP_AUTO).
 * scrobup_poll: 0 while the thread runs (and when there is none); once it is over, one SCROBUP_* result (the thread is joined) with *sent the listens the service took,
 * also when a later request failed (0 for a check). After a check's SCROBUP_OK scrobup_account gives the user name.
 * The poll also keeps Invalid Token (scrobup_invalid): set by SCROBUP_AUTH while the account still has the token that was refused, cleared by a check's SCROBUP_OK and by an
 * upload that had listens taken.
 * scrobup_rejected: the listens the service refused for good (HTTP 400, alone in a request) in the last upload, moved to .scrobbler.log.rejected; read it after the poll. */
int scrobup_start(int owner);
int scrobup_check_start(int owner);
int scrobup_busy(void);
int scrobup_kind(void);
int scrobup_owner(void);
int scrobup_poll(int *sent);
int scrobup_rejected(void);

/* Last.fm beside ListenBrainz (both read from the card's scrobble.ini at every start).
 * An upload goes to every service that is set up and not refused (a refused one is left out, so it never holds the log back; when every service that is set up stands
 * refused they are all asked again). A listen leaves the log once each of those services has taken it or refused it for good: for .sent when one took it, for .rejected when
 * all refused it. SCROBUP_AUTH: one service refused its account in this run (scrobup_auth says which); the upload ended there, and the next one leaves that service out.
 * scrobup_lastfm_check_start: the Last.fm credentials are asked of the service (auth.getMobileSession); results as scrobup_check_start, the job's kind is SCROBUP_LFCHECK.
 * Its poll: SCROBUP_OK signed in (the session is kept in RAM), SCROBUP_AUTH refused, SCROBUP_FAIL no answer, or the file's credentials are no longer those asked about.
 * scrobup_auth: after a poll, the services (SCROBUP_LB | SCROBUP_LF) whose account the job found refused, or left out because it stood refused. */
int scrobup_lastfm_check_start(int owner);
int scrobup_auth(void);

/* The account: /mnt/mmc/scrobble.ini on the card, section [LISTENBRAINZ], TOKEN= (the user token) and USER= (the user name once a check confirmed the token: a display
 * cache). Nothing of it is on flash. The user writes the file on a computer, which is the only way to set a token (1 to SU_TOKEN bytes of printable ASCII without a
 * space); the device writes only the USER line (after a valid check) and keeps every other byte. There is no sign-out on the device: the user takes the
 * token out of the file.
 * scrobup_account: 0 no token (no card, no file, no TOKEN line, an empty value or one that is no token); 1 a token is there, name (n bytes, SU_NAME holds any) its user
 * name or "" when no check has confirmed it. Asks no network. The file is read once and the answer kept in RAM until scrobup_forget, a start or a
 * check's result.
 * scrobup_forget: the card's file may have changed (a computer had the card): the next scrobup_account reads it again. The settings pages call it when they open and at
 * an Upload Scrobbles tap, the automatic upload when it has no usable token.
 * scrobup_invalid: 1 while the account's token is the one the service refused (RAM only, so until the next boot at most): set by a poll (above), cleared by
 * another token in the file (seen when it is read). The rows say Invalid Token, and no
 * automatic upload starts. It answers for the account as it was last read: ask scrobup_account first. */
int scrobup_account(char *name, unsigned n);
void scrobup_forget(void);
int scrobup_invalid(void);

/* The Last.fm account: the same file's [LASTFM] section, USER=, PASSWORD=, API_KEY= and API_SECRET= (the user's own API account), all four written by the user on a computer.
 * The device never writes them. The session key is asked of the service when a job needs one and kept in RAM only, with the credentials it was made
 * from: it is dropped when the file holds other ones, when the service calls it invalid and at a restart.
 * scrobup_lastfm: one SCROBUP_LF_* state, name (n bytes, SU_NAME holds any; may be NULL) the USER value, "" for SCROBUP_LF_NONE. No network; the file is read as for
 * scrobup_account (one read answers for both services).
 * scrobup_configured: 1 when a service is set up (ListenBrainz's token or Last.fm's four keys): a manual upload can start. scrobup_usable: 1 when one of those is not refused:
 * the automatic upload starts only then. */
int scrobup_lastfm(char *name, unsigned n);
int scrobup_configured(void);
int scrobup_usable(void);
