# Scrobbling

Listens are appended to `/mnt/mmc/.scrobbler.log`, Rockbox's AudioScrobbler portable-player 1.1
format, so any `.scrobbler.log` uploader can send them to Last.fm or ListenBrainz once the card is in
a computer. The device can send them to ListenBrainz itself ([Upload](#upload), from [Settings](#settings): the account and a manual Upload Scrobbles; with the Auto Upload switch on, also [by itself](#automatic-upload) while music plays on Wi-Fi). **Settings > Library > Scrobbling** (a value row, On or Off, on the Library page; it opens the Scrobbling page, whose first card is the **Scrobbling** switch with the note "Saved to .scrobbler.log on the card.") switches the logging on; it is off by
default (`/mnt/data/m1plus/scrobbling`: `1` or `1` and a newline on, missing or anything else off, read by `set_read`; `scrobble_setting`,
`scrobble_toggle`, saved with `home_write_atomic`). About 100 bytes a listen.

The setting is read once, by the first poll, and kept in RAM. While it is off the poll returns
before it asks the player, so the default costs the timers nothing; the tag-reader hook never reads
the file (it runs at boot) and does nothing until a poll has read it on. Turning it on starts from
the next look at the playing track; turning it off forgets the current one.

Sources: `patch/scrobble.c`, `patch/scrobble.h`; constants `SC_*` in `offsets.inc`. Tests:
`test/pod/scrobble.py`. The rule, the line and the header follow q2-pod (`patch/scrobble.c`, its
`docs/internals.md` "Play counts" and "Scrobbling"), as do the upload and the archive below; its
Last.fm sender is not ported, and the automatic upload is our own (q2-pod's runs from the UI main loop, ours from the poll).

No hook of its own. It uses the existing tag-reader hook (`docs/modules/payload.md` hook 5) and the
page timers that already look at the playing track.

## The log

An empty or missing file first gets the header `#AUDIOSCROBBLER/1.1`, `#TZ/UTC`, `#CLIENT/M1+ Music`. Each line is

```
artist \t album \t title \t track number \t length (s) \t L \t start (Unix time) \t (MusicBrainz ID, empty) \n
```

- **Tags**: stock's freshly parsed `playsong_id3info` (`0xa0d88c`: album `+0x404`, artist `+0x504`,
  title `+0x684`; the file's tags, or the record's for a CUE track) when it is the track's, else the
  song record's. No title: the file name less its extension. The track number is the record's
  (`REC_TRACK`, empty when 0). Control bytes (tabs, newlines) become spaces; a field is cut under
  `SC_STR` (256) or `SC_TITLE` (512) bytes before a UTF-8 continuation byte.
- **Time**: the play's second 0 on the wall clock: `time_now_ms` at the start (or at the first look
  less its position), pinned to `time()` at the first look with a set clock, so a pause never moves
  it. A clock set later (Auto Time) gets `time()` less the `time_now_ms` since second 0. The system clock is UTC: `/etc/localtime` is
  `Etc/UTC` and stock's time-zone setting only `setenv("TZ")`s demo (`toolsSetTimeZone`
  `0x5e3288`), so `#TZ/UTC` is right.
- Each line is one `open(O_APPEND)`, `write`, `fsync`, `close`, under the log's lock
  (`scrobble_lock`, which the upload's reads and rewrite hold too; it is taken only once the clock,
  the card and the kill switch allow a write). The play counts as logged only once
  `write` has written; a short write is not repeated (it would leave the half line twice).

Not logged: podcasts (`pc_is_path`), an empty or `Unknown` artist, a track whose length the player
never gave. A clock before 2020 (`SC_CLOCK_MIN`), the kill switch, no mounted card
(`pod_card_mounted`), a log that does not open or a write of nothing write nothing now and are
tried again at each look (every `SC_POLL_MS` at most) while the track plays.

## A listen

A track longer than `SC_MIN_S` (30 s) is a listen once `SC_MAX_S` (240 s) or half its length has been
heard. It is logged at that moment (so the last track before power-off is not lost), once per play.
A play starts again when the position falls back under `SC_SLACK_S` from `SC_SLACK_S` or more (repeat
one, a restart).

**Heard** is counted from the player's position (`get_playtimeandlength`): a step forward counts
when it is at most the wall time since the last look plus `SC_SLACK_S` (2 s). A seek or Memory
Playback's resume jump adds nothing, a pause adds nothing, and the polling period does not matter:
Now Playing's 500 ms, the 1 s dark ticks, or a page left for minutes and come back to on the same
track all count the same. A CUE image's tracks are told apart by their start (`REC_CUE_START` mixed
into the path's key).

## Entry points

- **`scrobble_note(track)`, the poll.** Called with `cc_playing()` by Now Playing's and the mini
  bar's timers (through `recent_note`, lit and dark) and by the Podcasts, iPod, Cassette and Vinyl
  pages' timers (lit and dark; Vinyl is its own fullscreen window, so Now Playing's timer is off
  while it is in front). It asks the player at most every `SC_POLL_MS` (500 ms), so a faster caller
  (the iPod page's animation timer) costs nothing extra. A main-loop poll, if one is ever allowed
  (AGENTS.md safety rules), would call this same function and need nothing else. It is also the
  only clock of the [automatic upload](#automatic-upload), looked at before anything else (also
  with no track, and with Scrobbling off): two compares while no listen waits and no job runs.
- **`scrobble_started(info, path)`, a track start.** Called from `pc_id3_path` for any path that is
  not a podcast (every fresh parse: `start_player`, `change_music`, the idle handler's auto change,
  Memory Playback at boot). It copies the struct's tags and starts the track at second 0 now; only
  `time_now_ms` is called, so the boot path asks the player nothing (bounded in the test). The track
  it replaces gets the time since its last look, at most up to its end, and is judged: that can
  append its line, never at boot.

## Limits

- A track no timer saw at all (played entirely while a stock page is in front) has no length and is
  not logged. A track seen once and then left gets the time to its end extrapolated at the next
  start, so a long pause in that unseen stretch counts as heard. A main-loop poll would remove both.
- A line still not written when the track changes is lost (one pending listen is kept, the
  current track's).
- Repeat one of a track no timer sees is one play (the tag reader caches the same file).
- Not seen on the device: whether `get_id3info` runs before the player reports the new track (the
  design does not depend on it), and the clock after a cold boot without Wi-Fi (the probe found the
  RTC right).

## Upload

`patch/scrobup.c` sends the log to ListenBrainz and to Last.fm ([Last.fm](#lastfm)) on one worker
thread through demo's libcurl, and reads both accounts (ListenBrainz: the token, the user name;
Last.fm: user name, password, API key and secret) from one file on the card, `scrobble.ini`
([The account's file](#the-accounts-file)); nothing of an account is on flash. It has no hook, no timer and no page of
its own: nothing runs unless one of its functions is called. Two callers start jobs: the settings UI
([Settings](#settings), `patch/scrobpage.c`, owner `SCROBUP_UI`) and the automatic upload
([Automatic upload](#automatic-upload), `patch/scrobble.c`, owner `SCROBUP_AUTO`). Sources: `patch/scrobup.c`,
`patch/scrobup.h`, `pj_member` in `patch/pcjson.c`; constants `SU_*` in `offsets.inc`; tests
`test/pod/scrobup.py` (the thread's routine run by the test, libcurl the harness's scripted
server).

### Interface (UI thread only)

Jobs. One thread at most, one busy state: an upload and a check never run together. `owner` is
`SCROBUP_UI` 0 or `SCROBUP_AUTO` 1: who starts a job polls it, and nobody else does.

| Call | Result |
|---|---|
| `scrobup_start(owner)` | An upload. `1` a thread was started; `0` a job (upload or check) is running, or is over and not polled yet; `-1` it cannot start: kill switch, no mounted card, no service set up (`scrobup_configured`), no thread. The card's `scrobble.ini` is read at every start, whoever starts it and whatever is kept in RAM. The upload goes to every service that is set up and not refused ([Two services, one log](#two-services-one-log)) |
| `scrobup_lastfm_check_start(owner)` | A check of the Last.fm credentials (`auth.getMobileSession`; the job's kind is `SCROBUP_LFCHECK` 2). The same three results. Its poll: `SCROBUP_OK` signed in (the session is kept in RAM), `SCROBUP_AUTH` refused, `SCROBUP_FAIL` no usable answer, or the file's credentials are no longer those that were asked about |
| `scrobup_auth()` | After a poll: the services (`SCROBUP_LB` 1, `SCROBUP_LF` 2, as bits) whose account that job found refused, or left out of an upload because it stood refused. `0` when every service that is set up took part and none refused |
| `scrobup_check_start(owner)` | A check of the token with the service (validate-token). The same three results (the token is on the card: no card, no check) |
| `scrobup_busy()` | `1` from a start until the poll that returned its result |
| `scrobup_kind()` | `SCROBUP_UPLOAD` 0, `SCROBUP_CHECK` 1 (ListenBrainz) or `SCROBUP_LFCHECK` 2 (Last.fm): the job that runs, or the last one |
| `scrobup_owner()` | `SCROBUP_UI` or `SCROBUP_AUTO`: who started that job. A caller asks it (and the kind) before it polls, and reads nothing of a job that is not its own |
| `scrobup_poll(&sent)` | `0` while the thread runs (and when there is none; `sent` untouched). Once it is over, one result, once, with the thread joined (table below). `sent` is the listens the service took, also on a failure (`0` for a check); it may be NULL. The poll also keeps Invalid Token (`scrobup_invalid`, below) |
| `scrobup_rejected()` | The listens the service refused for good (HTTP 400 for the listen alone) in the last job, moved to `.scrobbler.log.rejected`. Read it after the poll; it is 0 after a check and after an upload without a 400 |

| Result | An upload | A check |
|---|---|---|
| `SCROBUP_OK` 1 | Every listen was answered 200 or 400: the log is empty of listens. `sent` and `scrobup_rejected()` both 0 is "nothing to upload" | The token is valid; the user name is stored and `scrobup_account` gives it |
| `SCROBUP_FAIL` -1 | No network, timeout, certificate, any status but 200, 400 and 401 (429 and 5xx among them), the kill switch seen between two requests, more than `SU_REJ` separate runs of refused listens, no memory | The same request failures, any status but 200 and 401, an answer that is not the service's object (cut short, over `SU_ANS`, no `valid`, valid without a usable `user_name`), or the token in the card's file is no longer the one that was checked (changed, signed out, the card gone). Nothing changes |
| `SCROBUP_AUTH` -2 | 401: the token was refused; or Last.fm refused its credentials (error 4, 10, 13, 26). `scrobup_auth()` says which service. Nothing more is sent; what was answered before is retired | `"valid": false`, or a 401. The token and its stored name are kept: the UI decides |
| `SCROBUP_DISK` -3 | The card did not take an archive or the new log, the log does not open or read, it is not the log the upload read, or the card is gone: the log is as it was | The user name could not be written to the card's `scrobble.ini` (the card does not take it, or the file is over `SU_INI_MAX`); the token stays, without a name |

The account. No network; all of them cheap enough for a page that opens or refreshes. The token
is set only by the user writing [the account's file](#the-accounts-file) on a computer: no call
sets one, and none removes one (there is no sign-out on the device: the user takes the lines
out of the file). The one write (a valid check's `USER`) is the in-place rewrite of that file.

| Call | Result |
|---|---|
| `scrobup_account(name, n)` | `0` no token (no mounted card, no file, no section, no `TOKEN` line, an empty value, or a value that is no token); `1` a token is there, `name` its user name, or `""` when no check has confirmed it (`SU_NAME` 64 bytes hold any name; `name` may be NULL). The file is read once and the answer kept in RAM until `scrobup_forget`, a start or a check's poll |
| `scrobup_forget()` | The card's file may have changed (a computer had the card): the next `scrobup_account` reads it again. RAM only, no file access of its own. Called by the settings pages when one opens and at an Upload Scrobbles tap, and by the automatic upload's look ([when the file is read](#when-the-file-is-read)) |
| `scrobup_invalid()` | `1` while the account's token is the one the service refused: **Invalid Token**. RAM only (per boot; the file holds nothing of it): the refused token is remembered, and the answer follows the file each time it is read, so another token written on a computer is not invalid, and the refused one put back is. Set by a poll that returns `SCROBUP_AUTH`, whoever polls, when the file still has the token that was refused (the file is read for that); forgotten by a check's `SCROBUP_OK` and an upload that had listens taken. It answers for the account as last read: ask `scrobup_account` first. The rows show it, and no automatic upload starts while it stands |

The Last.fm account, and the two questions about any account. No network either.

| Call | Result |
|---|---|
| `scrobup_lastfm(name, n)` | The state of the Last.fm account, `name` its `USER` value (`""` when not set; may be NULL): `SCROBUP_LF_NONE` 0 not set (no card, no file, no `[LASTFM]` section, or one of its four keys missing or unusable); `SCROBUP_LF_NEW` 1 set, and not asked of the service since the boot or since the file changed; `SCROBUP_LF_IN` 2 signed in (a session made from these credentials is in RAM); `SCROBUP_LF_BAD` 3 the service refused these credentials. Read with the same one read as `scrobup_account`, and kept as long |
| `scrobup_configured()` | `1` when a service is set up: a ListenBrainz token or Last.fm's four keys. The gate of a manual upload (Upload Scrobbles) |
| `scrobup_usable()` | `1` when one of those is not refused. The gate of the automatic upload |

The Scrobbling switch is not asked: it gates the logging only, and a log that is there uploads with
the switch off. Wi-Fi is not asked either: without a connection the first request fails
(`SCROBUP_FAIL`) after at most `SU_CONNECT_S`.

### Files

| File | |
|---|---|
| `/mnt/mmc/scrobble.ini` (`SU_INI`, `scrobup.c`) | The accounts, and their only store ([below](#the-accounts-file)). A visible file the user writes on a computer (the only way to sign in); the player changes only `[LISTENBRAINZ]`'s `USER` line (a valid check). Settings Files has no row for it and Reset All Settings does not touch it |
| `/mnt/mmc/scrobble.ini.tmp` | The new `scrobble.ini` until its rename; removed on any failure |
| `/mnt/mmc/.scrobbler.log` | Read, then rewritten once as the header and what was not answered |
| `/mnt/mmc/.scrobbler.log.sent` | The archive: every line that left the log after a 200 (skipped lines too), appended, comments dropped. Made at its first line. Nothing reads or trims it |
| `/mnt/mmc/.scrobbler.log.rejected` | The lines of the listens the service answered 400 (each asked alone), appended, comments dropped, in the log's format: a user can look at them, fix them and put them back in the log. Nothing reads or trims it |
| `/mnt/mmc/.scrobbler.log.tmp` | The new log until its rename; removed on any failure |

### The account's file

```
[LISTENBRAINZ]
TOKEN=0f8fad5b-d9cb-469f-a165-70867728950e
USER=name
```

`TOKEN` is the user token, written by the user on a computer: the device has no token entry and
never writes one. `USER` is the user name the service gave for it, a display cache (the
Account row after a reboot, without a request) that any valid check corrects and that nothing else
uses. An empty `TOKEN=` is Not Set. A `[LASTFM]` section in the same file is the Last.fm account
([Last.fm](#lastfm)); the two sections are read and edited by the same code, each with its own
section name and key table (`su_svc`). Code: `su_ini_scan`, `su_ini_read`, `su_load`, `su_ini_set` in
`patch/scrobup.c`; tests `ini_tests`, `edit_tests`, `account_tests`, `lastfm_ini_tests` in
`test/pod/scrobup.py`.

**Reading** (`su_ini_scan`), line by line:

- A UTF-8 BOM at the file's start, a CR before a line's end and blanks (any byte up to a space) at
  a line's start are dropped. An empty line and a line that starts with `;` or `#` are comments.
- `[name]` starts a section: blanks inside the brackets are dropped, the name is compared in either
  case, text behind the bracket is ignored. Only the **first** `[LISTENBRAINZ]` section is looked
  at; it ends at the next section's header.
- Inside it `key = value`: blanks around the key and the value are dropped, the key is compared in
  either case, the value is everything behind the first `=` (so `=`, `;` and `#` inside a value
  are the value's). Only the **first** `TOKEN` and the first `USER` count.
- Every other section, key and line is passed over. `[LASTFM]` is read the same way for its own
  four keys, in a second pass over the same bytes: a `USER` line belongs to the section it is in.
- `TOKEN`'s value must have a token's shape (1 to `SU_TOKEN` bytes of printable ASCII without a
  space), else there is no token: no quotes, and no comment behind the value. `USER`'s value goes
  through `su_name` (control bytes and bytes that are not UTF-8 dropped, under `SU_NAME` bytes).
- No mounted card (the mount point is not opened), no file, a file that is not this text (UTF-16):
  no token. A file that is there and does not read (or no memory): no token now, read again by the
  next call.
- Of a file over `SU_INI_MAX` (4096 bytes, `offsets.inc`) only the whole lines of its first 4096
  bytes are read; a `TOKEN` line that crosses that byte is not read (a cut token is never sent).

**Writing** (`su_ini_set(name)`, the only writer; UI thread; one caller: the poll of a valid
ListenBrainz check, with the user name): the file is read whole, edited in memory and
written as `scrobble.ini.tmp` on the card, synced, then renamed onto it (`m1_save`, as the log's
rewrite; mode 0644).

- The device never writes a token, a `TOKEN` line, a section, anything of `[LASTFM]` or the file
  itself: with no file, no section or no token there is nothing to write (a name is only ever
  written beside a token that was just read). There is no sign-out: the user takes the lines out
  of the file (the owner's decision, 2026-11-12: the file is the one way in and the one way out).
- A user name: an existing `USER` line keeps its key, its blanks and its line end, only the
  value's bytes are replaced; a missing `USER` line is added right behind the `TOKEN` line, ending
  as the file's first line does (CR LF or LF).
- Every other byte stays: comments, other sections, the order of the lines, a BOM, a second
  `[LISTENBRAINZ]` section or a second `TOKEN` line (which the reader does not use either).
- **Refused, with the file as it was**: no mounted card; a file that is there and does not read; a
  file over `SU_INI_MAX`, before or after the edit (never cut); a card that does not take the temp
  file or the rename. The check ends as `SCROBUP_DISK`.

The worker thread never opens this file: `su_begin` copies the token into the request's header on
the UI thread, and the check's poll writes the name on the UI thread.

#### When the file is read

The RAM copy (`sa`: state, token, name) is refreshed, with one read of the file each time:

| When | By |
|---|---|
| The first `scrobup_account` after boot | the first caller (a page's row, the automatic look) |
| Every start of an upload or a check, whoever starts it | `su_begin` |
| The poll of a check's `SCROBUP_OK`, and of any `SCROBUP_AUTH` | `scrobup_poll` (is the token still the one that was asked about?) |
| The poll of any job that Last.fm took part in | `scrobup_poll` (the session, or the refusal, is kept only for the credentials the file still has) |
| By the write of a check's name, and by the next look after it | `su_ini_set` |
| The Scrobbling page, the ListenBrainz page or the Last.fm page opens | `lb_opened` → `scrobup_forget` |
| An Upload Scrobbles tap | `lb_upload_tap` → `scrobup_forget` |
| The automatic upload's look, once it has got past every other condition | `sa_tick` → `scrobup_forget` ([Automatic upload](#automatic-upload)) |

Never from `scrobble_note` outside that look, from the pages' timer, when a page comes back in
front, at boot or from the tag reader's hook. So a file edited on a computer takes effect without
a reboot: at the next page that opens, the next manual upload, and the automatic upload's next
look once the card is back (within `SA_EVAL`).

### The thread

1. Reads the log `SU_WIN` (64 KB) at a time, each read under the log's lock, and takes whole lines.
   No log is nothing to upload (`SCROBUP_OK`, 0); only an open that fails with `ENOENT`
   (`__errno_location`) is "no log"; a log that does not open for any other reason, or does not
   seek or read, is `SCROBUP_DISK`, as is a card that is gone.
   Skipped: comments, a line over `SU_LINE` (2560 bytes, also one longer than a window), a line not
   rated `L`, one without artist or title, with fewer than seven fields, or whose time is not 1 to
   10 digits, is past 32 bits or is before `SU_TIME_MIN` (October 2002, the earliest listen
   ListenBrainz takes: one such line would have the whole request refused). A CR before the newline
   is dropped. A last line without a newline waits for the next upload.
2. Sends the others in batches of `SU_BATCH` (50) listens or `SU_RAW` (16 KB) of log, whichever
   comes first, so the body is under `SU_BODY` (192 KB) whatever the escaping (JSON: 6 bytes a
   byte at worst; Last.fm's form: 9). No lock is held during a request. What follows is
   ListenBrainz alone; with Last.fm set up too each batch goes to both, and a listen leaves the
   log by the rule of [Two services, one log](#two-services-one-log). HTTP 200: the batch counts in `sent`. HTTP 400 for a batch of one listen: the
   service will never take it, so it is set aside for `.rejected` and counted in
   `scrobup_rejected()`. HTTP 400 for a batch of several: one listen may be the cause, so the batch
   is **narrowed**: its listens are sent again one request each, in order (`su_flush`); those
   answered 200 count in `sent`, those answered 400 alone are set aside, and the upload goes on with
   the next batch (a refused listen does not block later uploads, and does not take its batch with
   it). Any other answer, to a batch or to a single listen, ends the upload and leaves what was not
   answered 200 or 400 in the log: 401 as `SCROBUP_AUTH`, 429, 5xx and no answer as
   `SCROBUP_FAIL`. Before every request but the first the kill switch is looked at (`home_off`, two
   `access` calls); when it is there the upload ends as `SCROBUP_FAIL`.
3. Once, at the end or at the failure, under the lock (`su_retire`): the log's bytes up to the last
   listen that was answered 200 or 400 (after a full run, all that was read) leave the log, each
   to its file, `.sent` or `.rejected`, and the log becomes the header plus everything after those
   bytes. A batch's bytes run from the end of the batch before it to the first line that did not
   fit it, so skipped lines go where the batch around them goes; in a narrowed batch a listen's
   bytes run from the end of the listen before it to its own line's end (the batch's end for its
   last listen), so a skipped line goes with the listen after it. Order: the new log is
   written and synced as `.tmp` first (a full card fails before an archive gains anything), the
   archives are written and synced, then the rename. Any failure leaves the log as it was, so those
   listens go again with the next upload (an archive may then hold them twice; ListenBrainz drops a
   listen it already has). A log of comments only is not rewritten.
   Before anything is written the bytes that are to leave are read again and compared with what
   the upload read (`su_hash`, FNV-1a carried along the windows; `run.dh` is its value at
   `run.done`): a log that was replaced or changed meanwhile, shorter, longer or of the same
   size, is left alone, nothing is archived, and the upload ends as `SCROBUP_DISK`. What the
   service took of the old log is then in neither file; a listen the UI appended meanwhile is
   behind those bytes and does not change the comparison.

The refused listens are remembered as up to `SU_REJ` (128) byte runs, in the log's order; listens
(and whole batches) refused in a row are one run, so "every listen refused" is one, and sent and
refused listens may alternate inside a batch. A 129th separate run ends the upload as
`SCROBUP_FAIL` with everything before it retired; the next upload goes on from there. The runs
are 1 KB of the thread's stack.

A listen appended while the upload runs is behind the bytes that leave, so it stays in the log; the
appender and the rewrite hold the same lock (`scrobble_lock` / `scrobble_unlock`, `scrobble.h`), so a
line is never torn or lost. The UI thread can wait on that lock for one 64 KB read, or for the
rewrite, which copies whatever stays in the log (little after a full success, the rest of the
log after an early failure). The card is checked (`m1_card_mounted`) before each read and before
the rewrite.

### The requests

All go through `su_http` (Last.fm's are under [Last.fm](#lastfm): no `Authorization` line, a
form's content type). ListenBrainz: headers `Authorization: Token <token>` and, for a POST,
`Content-Type: application/json` (a `curl_slist` on the stack, as sbnet's one: the payload's import
table has no `curl_slist_append`); HTTPS only (`CURLOPT_PROTOCOLS`), no redirect followed, `M1_CA`
with peer and host verification on, `SU_CONNECT_S` 15 s and `SU_TOTAL_S` 60 s, `NOSIGNAL`.
`curl_global_init` is called on the UI thread at the start, as the podcast refresh does.

**The upload**: `POST https://api.listenbrainz.org/1/submit-listens`, body

```
{"listen_type":"import","payload":[{"listened_at":N,"track_metadata":{"artist_name":"..","track_name":"..","release_name":"..","additional_info":{"duration":N,"tracknumber":N,"media_player":"M1+ Music","submission_client":"M1+ Music"}}}, ..]}
```

`release_name` is left out for an empty album, `duration` and `tracknumber` for a field that is not
a number above 0. Strings are JSON-escaped (`"`, `\`, control bytes as `\u00XX`); a byte that is not
well-formed UTF-8 goes as U+FFFD, so one bad tag cannot make the service refuse the batch. The
answer's body is not read.

**The check**: `GET https://api.listenbrainz.org/1/validate-token`, no body. The answer
`{"code":200,"message":"Token valid.","valid":true,"user_name":".."}` is collected into `SU_ANS`
(2 KB; a longer one ends the transfer) and read with `pj_member` (`patch/pcjson.c`: one member of
the top-level object, the object must be whole, strings decoded as the podcast search's are).
`"valid": true` with a `user_name` string is `SCROBUP_OK`; `"valid": false` (or a 401) is
`SCROBUP_AUTH`; anything else is `SCROBUP_FAIL`. The name is untrusted: control characters, DEL,
C1 controls and bytes that are not UTF-8 are dropped, spaces at its ends too, and it is cut under
`SU_NAME` (64) bytes on a character boundary (`su_name`; the same filter reads the name back from
the file). A name that is empty after that is no answer. The thread only keeps the name in RAM; the
poll (UI thread) reads the card's `scrobble.ini` again and writes the name back as `USER=` only when
the file's token is still the one that was checked, and only when the name differs from the one
there.

### Automatic upload

**Settings > Library > Scrobbling > Auto Upload** (a switch, off by default;
`/mnt/data/m1plus/scrobble-auto`: `1` on, read once and kept in RAM like the Scrobbling switch;
`scrobble_auto_setting`, `scrobble_auto_toggle`). While it is on, the log is uploaded by itself
while music plays on Wi-Fi. Code: `sa_*` and the state `sau` in `patch/scrobble.c`; constants
`SA_*` (seconds) in `offsets.inc`; tests `auto_*_tests` in `test/pod/scrobble.py`.

No hook, nothing at boot, nothing in the main loop, no timer of its own. Its only clock is the
poll, `scrobble_note`, which the page timers call while a track is on a page that shows it:

- **Counting.** Each line `sc_line` writes counts in RAM (`sau.pending`, and `time_now_ms` of the
  first one). Listens from before this boot are not counted, but go with the first automatic
  upload: the whole log is sent.
- **The poll's cost.** `scrobble_note` first does `if (sau.job || sau.pending) sa_tick()`: with
  nothing counted and no job (Scrobbling off, or no listen yet this boot) that is two compares
  and nothing else. With a listen counted and Auto Upload off: the switch's file is read once,
  then one more compare. With it on: one `time_now_ms` a call.
- **When.** At most once every `SA_EVAL` (60 s) the conditions are looked at, in this order:
  the first counted listen is `SA_WAIT` (600 s) old (one upload for a run of tracks, not one a
  track); `SA_RETRY` (1800 s) have passed since a failure; no job is busy (`scrobup_busy`, the
  user's upload or check included); stock's `usbmode_page` window does not exist;
  `get_wifisignal() > 0`. Up to here nothing touches the card. Then the card's `scrobble.ini` is
  read (`scrobup_forget`, `scrobup_usable`): a service is set up and not refused (a ListenBrainz
  token that is not Invalid Token, or Last.fm credentials the service has not refused). Then `scrobup_start(SCROBUP_AUTO)`, which looks at the kill switch and
  the card itself and reads the file once more; its `-1` counts as a failure (the next try
  `SA_RETRY` later, not every minute). The Wi-Fi is asked its state and never switched on.
- **The file's cost.** A look reads `scrobble.ini` only when everything else would let an upload
  start: with a usable token that look starts the upload; with none (no file, an empty or
  unusable `TOKEN`, no mounted card, which is two `statfs` and no open, or a refused token) it is
  one read of at most 4 KB a minute while a listen has waited ten minutes on Wi-Fi with Auto
  Upload on. That read is what lets a token written on a computer (over USB, or in a card reader)
  start the uploads without a reboot: within `SA_EVAL` of the card's return. No token is not a
  failure (`sau.fail` stays 0).
- **The result** is collected by `scrobble_auto_collect`: from the poll (every call while the
  job is known), and from the settings pages before they look at the worker (`lb_poll`: a page
  that opens, each tick, an Upload Scrobbles tap), so a job that ended after the music stopped
  never blocks the user's own start. It asks `scrobup_busy()` and `scrobup_owner()` first and
  never polls the pages' job; the pages never poll or toast this one. Every outcome is silent
  (no toast, no dialog, no widget):

  | Result | |
  |---|---|
  | `SCROBUP_OK` | The count drops by what waited at the job's start; a listen logged meanwhile still waits, from the job's start on |
  | `SCROBUP_FAIL`, `SCROBUP_DISK` | The next try no sooner than `SA_RETRY` after the result was collected. The log is as the upload left it |
  | `SCROBUP_AUTH` | The poll marks the service that refused (Invalid Token, or Last.fm's refusal; the rows show it at their next refresh). With no other usable service nothing starts while it stands: until another token or other credentials are written into `scrobble.ini`, a valid check, a manual upload that has listens taken, Sign Out, or the next boot. With another usable service the next look (within `SA_EVAL`) starts an upload that leaves the refused one out |
  | Any result with nothing sent and at least one listen refused (400) | No automatic upload until the next boot (`sau.stop`): a service that takes nothing must not drain the log into `.rejected` run after run. Manual uploads are not affected |

- **Standby.** Nothing keeps the device awake for an automatic upload (the pages' keep-awake is
  for the user's own job only): it relies on playback keeping the device and the Wi-Fi up. A
  request cut off by standby ends as `SCROBUP_FAIL` with the log intact and is tried again.
- **The card's `scrobble.ini`** is read by an automatic upload and never written: it starts no
  check, so it adds no `USER` line (the pages do, when one opens).

What does not count: a listen the log did not take (no card, the kill switch); a manual upload
(the count stays, so the next automatic upload may find nothing to send: one read of the log, no
request). Limits: an upload starts only while a page whose timer calls `scrobble_note` is up (as
the logging itself); a result is collected at the next call, so with the music stopped and no
settings page opened the worker stays busy (harmless: only the user's start needs it, and that
collects it first); `time_now_ms` wraps after 49 days of uptime. Not seen on the device.

The rules two callers share the worker under:

- **Poll ownership.** A caller polls only the job it started: a finished job blocks every later
  start until `scrobup_poll` has returned its result, and a result read by the wrong caller is a
  lost toast or a toast for a job the user never started. `patch/scrobpage.c` remembers its own
  start (`lbs.job`) and, before every poll, asks `scrobup_busy()`, `scrobup_owner()` and
  `scrobup_kind()`: no job, the automatic upload's, or a job of another kind means the result is
  not its own, and it reads nothing.
- **USB mode and Wi-Fi are the caller's to check.** `scrobup_start` looks at neither. Both
  callers refuse while stock's `usbmode_page` window exists (`navigator_window_is_exist`,
  `SCROBUP_USB_PAGE`) and while `get_wifisignal() <= 0`, and both ask about USB mode before they
  ask for the token: in USB storage mode the card is expected to be unmounted, and without the
  card there is no token to read (and the start itself returns `-1`).

### Two services, one log

An upload goes to every service that is set up and not refused (`su.use`, decided by `su_begin`
from the file as it is at the start). Each batch is sent to ListenBrainz first (narrowed there
when it is answered 400), then to Last.fm (`su_flush`, `su_lb_batch`, `su_lf_batch`), and each
service's answer for each listen is kept (`run.st`: taken, or refused for good). Tests:
`both_tests` in `test/pod/scrobup.py`.

- **When a listen leaves the log.** Once every service of the upload has taken it or refused it
  for good. It goes to `.sent` when at least one service took it (and counts in `sent`), to
  `.rejected` only when all of them refused it (and counts in `scrobup_rejected()`).
- **A service that fails for now** (no answer, 5xx, 429, a Last.fm error that is no refusal) ends
  the upload: the listens it has not answered for stay in the log, with everything behind them,
  and go again to **both** services with the next upload. The service that had already taken them
  gets them twice; both drop a listen they already have (same artist, track and time).
- **A service that refuses its account** (ListenBrainz 401; Last.fm error 4, 10, 13, 26) ends the
  upload as `SCROBUP_AUTH`, and the poll marks that service refused when the file still holds the
  account that was asked about: Invalid Token for ListenBrainz, `SCROBUP_LF_BAD` for Last.fm.
  Both marks are RAM only and follow the file: other credentials written on a computer are not
  refused, the refused ones put back are. `scrobup_auth()` names the service.
- **A refused service is left out** of the uploads that follow, so it never holds the log back:
  the listens then leave on the other service's answer alone and are never sent to the refused
  one (they are in `.sent`; a user who wants them there too can put the lines back in the log).
  `scrobup_auth()` after such an upload still names the service that was left out, so a page can
  say so. When every service that is set up stands refused, an upload that is started all the
  same (a manual one: the automatic upload does not start) asks them all again.
- A refusal ends: ListenBrainz as before (another token, a valid check, an upload in which the
  service answered 200, a reboot); Last.fm with other credentials in the file, a check
  or an upload in which the service gave a session or took a batch, a reboot.

### Last.fm

The account is the `[LASTFM]` section of the card's `scrobble.ini`, written by the user on a
computer; the device never asks for it by keyboard and stores nothing of it on flash.

```
[LASTFM]
USER=name
PASSWORD=the account's password
API_KEY=0123456789abcdef0123456789abcdef
API_SECRET=fedcba9876543210fedcba9876543210
```

`API_KEY` and `API_SECRET` are the user's own API account (last.fm/api/account/create); no key is
built into the firmware. The account is set up when all four keys are in the first `[LASTFM]`
section and usable: `USER` a name as `su_name` keeps one, `PASSWORD` 1 to `SU_LF_PASS` (128)
bytes without a control byte (the blanks around it are dropped, the ones inside are its own),
`API_KEY` and `API_SECRET` 1 to `SU_LF_KEY` (64) bytes of printable ASCII without a space. The
section is read as the ListenBrainz one is (either case, BOM, CR LF, comments, the first line of
each key, the 4 KB cap). The device never writes to it.

**The session key** is not stored on the card. `auth.getMobileSession` is asked when a job needs
a key and has none; the key is kept in RAM (`sl.sk`) with the credentials it was made from
(`sl.skc`). It is dropped when the file is read and holds other credentials (or none, or the card
is away), when the service answers error 9, at a refusal and at a reboot. The worker
never opens the file: `su_begin` copies the credentials and the key for it, and the poll (UI
thread) takes the key the thread left, only for the credentials the file still has.

**The calls** (`su_lf_call`): `POST https://ws.audioscrobbler.com/2.0/`,
`Content-Type: application/x-www-form-urlencoded`, no `Authorization` line, TLS and time limits
as for ListenBrainz. Every byte of a name or a value but `A-Z a-z 0-9 - _ . ~` is percent-encoded.
`api_sig` is the MD5 (lower-case hex) of every parameter but `format`, name then value as they
are (UTF-8, not encoded), in the byte order of the names, then the secret. That order has
`trackNumber[..]` before `track[..]` and `artist[10]` before `artist[1]` (`]` is above the
digits): `su_lf_form` emits the parameters in it, once into the MD5 and once into the body. MD5
is libcrypto's `MD5_Init` / `MD5_Update` / `MD5_Final`, which demo imports (`tools/pod.py`
`LIBC`). A byte of a tag that is not well-formed UTF-8 goes as U+FFFD into both: the service
reads the body as UTF-8, and any other byte would make the signature wrong, which is a refusal.

- `auth.getMobileSession`: `username`, `password`, `api_key`, `api_sig`, `format=json`. The
  answer `{"session":{"name":"..","key":"..","subscriber":0}}`; a key that is not 1 to 64
  printable bytes is no answer.
- `track.scrobble`: `artist[i]`, `track[i]`, `timestamp[i]` and, when the listen has them,
  `album[i]`, `duration[i]`, `trackNumber[i]`, for i from 0 in the log's order, up to `SU_BATCH`
  (50, the service's limit), with `api_key`, `sk`, `api_sig`, `format=json`. The answer
  `{"scrobbles":{"scrobble":[{..,"ignoredMessage":{"code":"0","#text":""},..}, ..],"@attr":{..}}}`
  (one object instead of the array for one listen) is read by position: a listen whose entry has
  an `ignoredMessage` code other than 0 is **refused for good** (1 the artist, 2 the track, 3 a
  time too old, 4 too new), the others are taken, also when the answer has no entry for them.
  Code 5 (the daily limit) is not for good: the batch failed (`SCROBUP_FAIL`) and goes again.
  The answer is collected into a second `SU_BODY` buffer (it repeats every tag; one that does not
  fit is no answer), allocated only when Last.fm takes part.
- **Errors.** Last.fm answers an error with an HTTP status of its own (403, 400) and
  `{"error":N,"message":".."}`, so the body is read whatever the status. 4 (user name or
  password), 10 and 26 (the API key), 13 (the signature, so the secret): `SCROBUP_AUTH`. 9 (the
  session key): the key is dropped, a new one is asked for and the batch is sent again, once an
  upload; a second error 9 is `SCROBUP_FAIL`. Every other error (8, 11, 16, 29 among them), any
  other status without an error member, and no answer: `SCROBUP_FAIL`.

JSON: `pj_span` and `pj_next` in `patch/pcjson.c` (a member's own text, so that a nested object
can be read again; the elements of an array). Tests: `lastfm_ini_tests`, `lastfm_sign_tests`
(the signatures against values worked out in the test with hashlib), `lastfm_session_tests`,
`lastfm_error_tests`, `lastfm_ignored_tests` in `test/pod/scrobup.py`; the harness's MD5 is
hashlib's.

### Not done for Last.fm

`USER` is not corrected from the service's answer (`session.name`); the password is in the file
in plain text, as the owner decided; `auth.getMobileSession` is asked with the password each boot
(no session key on the card). The pages are under [Settings](#settings).

### Limits

- Not run against the real service or on the device: the requests' shape follows ListenBrainz's
  documentation and q2-pod. `SU_TIME_MIN`, "a duplicate listen is dropped", "400 is a batch that
  will never be taken" and validate-token's answer (200 with `"valid": false` for a bad token) are
  ListenBrainz's documented behaviour, not observed here.
- Last.fm: not run against the real service with an account. Seen from this side with a made-up
  key only: an error is `{"message":..,"error":N}` with HTTP 403 (error 10) or 400 (errors 3 and
  6). The answers of `auth.getMobileSession` and `track.scrobble`, the order of the scrobbles in
  an answer (read by position), the `ignoredMessage` codes and "a duplicate scrobble is dropped"
  are Last.fm's documented behaviour, not observed here. Whether the device's libcrypto has
  `MD5_*` is taken from demo importing them; not run on the device.
- With two services, a batch one service took and the other failed on is sent to both again by
  the next upload: the first service sees those listens twice and is relied on to drop them.
- A service that stands refused is left out, and the listens uploaded meanwhile are never sent to
  it: they leave the log for `.sent` on the other service's answer. Nothing sends `.sent` again.
- A wrong `API_SECRET` (error 13) or API key marks the whole Last.fm account refused, like a wrong
  password. Last.fm's error 6 (a parameter it does not like) is a plain failure with no narrowing:
  a batch that always gets it holds the log back for both services until the line is removed.
- A Last.fm password that begins or ends with a blank cannot be written in the file.
- 429 and 5xx are plain failures: no retry, no back-off, `Retry-After` is not read.
- A batch answered 400 costs one request a listen (up to 50, a connection each: no handle is
  reused), and there is no bound on it: a 400 that every request gets (a change of the service's
  API) asks once for every batch and once for every listen, then empties the log into `.rejected`.
  Nothing is lost, and nothing sends that file; the automatic upload stops after one such run.
- One upload remembers `SU_REJ` (128) separate runs of refused listens; a log with more ends as
  `SCROBUP_FAIL` ("Upload failed, N sent") and needs another upload for the rest.
- A check that finds the token invalid keeps the `USER` line beside it.
- The token and the Last.fm password are plain text in a visible file on the card (the owner's
  decision: a file on flash could not be found or edited); whoever has the card has both.
- `scrobble.ini` is not fsynced through its directory (`m1_save`, as the log's rewrite). The
  rename onto the existing file is the kernel's for the card's file system (the same step the
  log's rewrite takes); a power cut between the temp file and the rename leaves
  `scrobble.ini.tmp` beside the old file, and the next write replaces it. Not seen on the device.
- The file is read and written by the UI thread: at most 4 KB a read, and one read and one write
  a confirmed name.
- A file over `SU_INI_MAX` works for uploads when the account is in its first 4 KB, but cannot be
  changed from the device, and a confirmed user name is not kept: the Account row stays empty and
  each page that opens checks the token again.
- No quotes and no inline comment in a value: `TOKEN="abc"` sends the quotes (the service then
  refuses it: Invalid Token); `TOKEN=abc ; note` is no token. UTF-16 files (Windows Notepad's
  "Unicode") are not read: Not Set.
- A page that opens with an unconfirmed token starts a check; until it answers (at most
  `SU_TOTAL_S`) Upload Scrobbles says "Already uploading".
- There is no token entry on the device (the owner's decision, 2026-11-12: one way to sign in):
  without a computer to write `scrobble.ini` there is no account. A token the service refused
  stays Invalid Token until the file holds another one (or a valid check, listens taken
  or a reboot): a page that opens does not ask the same refused token again.
- A card removed without USB mode while a page is up: the rows keep what was read until a page
  opens or Upload Scrobbles is tapped.
- A failed archive write can leave part of the lines in `.sent` or `.rejected` (there is no
  truncate back), and they are archived again by the upload that succeeds.
- The rewrite replaces any other writer's header (Rockbox's `#CLIENT/`) with ours.
- An upload already running when the card is handed to a computer over USB still reads and, if
  the card is mounted at that moment, rewrites the log.

## Settings

The UI of the upload and the accounts: `patch/scrobpage.c` (`lb_*`, `lf_*`, state `lbs`), called by the
Settings pages of `patch/m1plus.c`; rows and pages in `tools/pod_pages.py` (`LIBRARY_PAGE`,
`LB_PAGE`, `LF_PAGE`), strings in `tools/pod_i18n.py`, glyphs `musicbrainz`, `lastdotfm` (the two marks, filled, one colour: `assets/icons/custom/`), `upload` and
`clock` (`tools/mod_icons.py`); tests `test/pod/scrobpage.py`; mock-up
`tools/preview/preview_scrobble.py`. No hook, nothing at boot, nothing in the main loop; no
upload without a tap unless Auto Upload is on ([Automatic upload](#automatic-upload)). The pages
show the accounts and change nothing of them: no entry and no sign-out on the device.

**Settings > Library > Scrobbling** is a cards page of its own (`SCROBBLING_PAGE`, `m1plus_scrobbling`, page key placed after `m1plus_lastfm` in `PAGE_ORDER`, macro `POD_SCROBBLING_PAGE`).
The Library page has one row for it, **Scrobbling** (`ACT_SCROBPAGE` 139, a value row with the chevron and the Lucide `list-music` glyph, `VK_SCROB`: On or Off from
`scrobble_setting`; no payload code runs when it opens: the row is read again like every value row when the Library page is back in front). The page's cards:

1. the **Scrobbling** switch (`ACT_SCROBBLE` 96) and the note "Saved to .scrobbler.log on the card.";
2. **ListenBrainz** and **Last.fm**, below;
3. **Auto Upload** (`ACT_LBAUTO` 112) and **Upload Scrobbles**, and the note "Uploads on Wi-Fi while music plays."

Nothing on the page is dimmed while Scrobbling is off: the accounts, Auto Upload and Upload Scrobbles keep working, so a log already on the card can still be uploaded.
The page is `lb_opened` page 0 (the timer's `pages` bit 0) and its `EVT_WINDOW_TO_FG` calls `lb_on_front`; the Library page does neither (it shows no account, so it needs no
`scrobble.ini` watch). The rows:

- **ListenBrainz** (`ACT_LB` 108, a value row with the chevron, `lb_row_text`): the user name; "Not Set" with no
  token; "Invalid Token" after the service refused the token; nothing for a token no check has
  confirmed. Opens the ListenBrainz page.
- **Last.fm** (`ACT_LF` 113, the same, `lf_row_text`): the file's `USER`; "Not Set" unless all four keys are
  there; "Sign-in Failed" after the service refused them (`SCROBUP_LF_BAD`). Opens the Last.fm page.
- **Upload Scrobbles** (`ACT_SCROBUP` 109, an action row, `lb_upload_tap`). In this order: a job
  runs (an upload or a check, ours or not) → "Already uploading"; stock's `usbmode_page` window
  exists → "Not available in USB mode"; no mounted card → "Storage unavailable" (the accounts are on
  the card, so these two come before the account: neither is "no account"); no service set up (`scrobup_configured`), with the
  card's `scrobble.ini` read again (`scrobup_forget`) → "Set up an account first";
  `get_wifisignal() <= 0` (the check of the Podcasts, Radio and Subsonic pages) → "Connect to
  Wi-Fi first"; else `scrobup_start()`: `1` → "Uploading scrobbles", `0` → "Already uploading",
  `-1` (the kill switch, no thread) → "Storage unavailable". The Scrobbling switch is not asked.
  One toast at the end:

  | Result | Toast |
  |---|---|
  | `SCROBUP_AUTH`, `scrobup_auth()` has `SCROBUP_LB` | "ListenBrainz: Invalid Token" (the service's name, then the row's text; the token is kept) |
  | `SCROBUP_AUTH` otherwise | "Last.fm: Sign-in Failed" |
  | `SCROBUP_DISK` | "Card error, %d sent" |
  | `SCROBUP_FAIL` | "Upload failed, %d sent" |
  | `SCROBUP_OK`, `scrobup_rejected()` > 0 | "%d sent, %d rejected" |
  | `SCROBUP_OK`, sent > 0 | "Scrobbles sent: %d" |
  | `SCROBUP_OK`, both 0 | "Nothing to upload" |

  An upload that ended `SCROBUP_OK` with a service left out (it stood refused) says nothing of
  that: the service's row does.

Under the card's note, a card of one row: the **Auto Upload** switch (`ACT_LBAUTO` 112, a row of
`sw_tab`: `scrobble_auto_setting` / `scrobble_auto_toggle`; off by default; one switch for both
services; it works with or without an account, starts nothing and says nothing at the tap) and
its note "Uploads on Wi-Fi while music plays." ([Automatic upload](#automatic-upload)).

**The ListenBrainz page** (`m1plus_listenbrainz`) and **the Last.fm page**
(`m1plus_lastfm`): one card of one row and a note, no glyphs. They show the account and
set nothing of it: sign-in is the card's `scrobble.ini` alone ([the account's file](#the-accounts-file)),
and so is signing out (`ACT_LBTOKEN` 110 and `ACT_LBOUT` 111 are gone, their ids not reused).

- **Account** (an info row, `INFO_LBACCT` / `INFO_LFACCT`, `lb_account_text` / `lf_account_text`): "Not Set"; the
  user name; "Checking…" while the service's check runs; "Invalid Token" / "Sign-in Failed"; for ListenBrainz empty for a token no check has
  confirmed. The token and the password are never shown. A check that fails for another
  reason (`SCROBUP_FAIL`, `SCROBUP_DISK`) says nothing and leaves the account unchecked; a check
  never toasts.
- The note: "Put your token from listenbrainz.org in scrobble.ini on the card." (three lines of
  room); "Put USER, PASSWORD, API_KEY and API_SECRET under [LASTFM] in scrobble.ini on the card.
  Get an API key at last.fm/api." (five).

**The card's `scrobble.ini`** is read again (`lb_opened`: `scrobup_forget`, then `scrobup_account`)
when the Scrobbling page, the ListenBrainz page or the Last.fm page opens, and at an Upload Scrobbles tap; never from
the timer, at boot or when a page comes back in front. The rows are read again when the account
differs from what they showed. A token no check has confirmed (no `USER`: written on a computer,
or the Wi-Fi was down) that is not Invalid Token is checked then (`lb_check`: `scrobup_check_start`), when the Wi-Fi is connected
and no job runs; there is no toast for the file (a file without a usable token is Not Set).
Last.fm credentials not asked since the boot (`SCROBUP_LF_NEW`) are checked the same way
(`scrobup_lastfm_check_start`, the job's kind `SCROBUP_LFCHECK`). One job runs at a time: the
page's own service is asked first (the Last.fm page: Last.fm; the others: ListenBrainz), the
other one when the first needs no check, and Last.fm after a ListenBrainz check's result is shown.

**Invalid Token** is the account layer's RAM state (`scrobup_invalid`, per boot): set by the poll
of a check or an upload answered `SCROBUP_AUTH`, the automatic upload's too; gone with another
token in the file (written on a computer), a valid check,
and an upload that had listens taken. The token is kept (the file is the user's to correct).
Nothing of it is in a file.

**The timer** (`lb_tick`, `LB_TICK_MS` 500 ms) exists only while the Scrobbling page or one of
the two account pages is up and a job runs or a polled result is not shown yet; it is added at a
start, when a page opens or comes back in front with a job in flight, and removed when the last
of the pages is destroyed or at its last tick. Each tick: an automatic upload that is over is
collected (`scrobble_auto_collect`, silently), then the poll of our own job (see
[poll ownership](#automatic-upload)); while that job runs,
`reset_poweroptions_timer(1, 1, 0)` every second tick (the Software Update page's keep-awake);
with the screen dark nothing else: the toast and the rows wait for the first lit tick. A job
that ends after the pages closed is polled when one opens again (its toast at the first tick)
or by an Upload Scrobbles tap, which then shows that result and starts nothing. An automatic
upload that runs is only watched (the tap says "Already uploading", no keep-awake); once it is
over the rows are read again (Invalid Token, if it found that) and nothing is toasted.

Limits: while a check runs (up to `SU_TOTAL_S`) Upload Scrobbles answers "Already uploading".
The token's shape (`SU_TOKEN` bytes) is judged when the file is read (`su_shape`). Not seen on
the device or against the real service.

## Device checks

Not run yet. Record the build tag with each result.

| Check | Steps | Expect |
|---|---|---|
| SCROB-UP-01 | With no `scrobble.ini` on the card open Settings > Library > Scrobbling > ListenBrainz. Then, on a computer, write `scrobble.ini` at the card's root (`[LISTENBRAINZ]`, `TOKEN=<token>`), put the card back and open the page again (Wi-Fi connected) | First: the page has Account (Not Set), the note naming `scrobble.ini`, and Auto Upload; no Token row, nothing opens a keyboard. Then: Account reads Checking… and then the user name; the ListenBrainz row shows the name |
| SCROB-UP-02 | Delete `scrobble.ini`; on a computer write `scrobble.ini` at the card's root (`[LISTENBRAINZ]`, `TOKEN=<token>`, Windows line ends, a `[LASTFM]` section and a comment beside it); put the card back, open Settings > Library > Scrobbling (Wi-Fi connected) | No toast; the row shows the user name after the check; on the computer the file has `USER=<name>` behind the `TOKEN` line and every other byte as written; no reboot was needed |
| SCROB-UP-03 | With a checked token, restart; open Settings > Library > Scrobbling | The row shows the user name without a new check (no network needed): it is `USER=` in `scrobble.ini`; nothing of the account is in `/mnt/data/m1plus` |
| SCROB-UP-20 | After SCROB-UP-01 read `scrobble.ini` on a computer; then delete the `TOKEN` line there and open Settings > Library > Scrobbling | First: `[LISTENBRAINZ]`, `TOKEN=<the token>` as written, and `USER=<name>` added behind it. After: both ListenBrainz rows read Not Set (that is the sign-out); the device wrote nothing |
| SCROB-UP-21 | Auto Upload on, no token; play until a listen is ten minutes old; connect USB (storage mode), write `scrobble.ini` with the token, disconnect, play on with Wi-Fi | Within about a minute of playback the log is uploaded with the file's token; no reboot, no toast |
| SCROB-UP-22 | With a checked token, remove the card; open Settings > Library > Scrobbling and the ListenBrainz page; tap Upload Scrobbles | Both pages read Not Set; "Storage unavailable"; with the card back, the next page that opens shows the name again |
| SCROB-UP-04 | Play a few songs with Scrobbling on, then Upload Scrobbles | "Uploading scrobbles", then "Scrobbles sent: N"; the listens are on listenbrainz.org with the right times; `.scrobbler.log` holds only its header, `.scrobbler.log.sent` the lines |
| SCROB-UP-05 | Upload Scrobbles again | "Nothing to upload" |
| SCROB-UP-06 | Wi-Fi off (and once with Wi-Fi on but not connected): Upload Scrobbles | "Connect to Wi-Fi first"; the log is untouched |
| SCROB-UP-07 | Write a wrong token (a changed character) into `scrobble.ini` on a computer, open Settings > Library > Scrobbling with Wi-Fi on; then Upload Scrobbles | Account and the ListenBrainz row read Invalid Token; the upload toasts "ListenBrainz: Invalid Token" and the log is untouched; the right token written into the file shows the name again when a page opens |
| SCROB-UP-08 | Start an upload of a long log (a few hundred lines) while a song passes its scrobble point | The new listen is in `.scrobbler.log` after the upload; nothing is lost or torn |
| SCROB-UP-09 | Start an upload and let the screen go dark; wake it after a minute | The final toast shows when the screen is lit; the device did not go to standby mid-upload |
| SCROB-UP-10 | Start an upload, leave Settings at once; come back to Settings > Library > Scrobbling later | The result's toast shows shortly after the page opens; a new upload can start |
| SCROB-UP-11 | With `[LASTFM]` complete in the file (Wi-Fi connected) open Settings > Library > Scrobbling, then the Last.fm page; then once with a wrong `PASSWORD` | The Last.fm row shows `USER`; the page's Account shows Checking… and then the name, no toast. Wrong password: both read Sign-in Failed; the right one written into the file is checked when a page opens again |
| SCROB-UP-12 | Connect USB (storage mode), then try to reach Upload Scrobbles | The USB page is in front; if the row can be reached: "Not available in USB mode" (or "Storage unavailable"), nothing is written to the card |
| SCROB-UP-13 | Scrobbling and Auto Upload on, a checked token, Wi-Fi connected: play an album from Now Playing for 20 minutes without touching Settings | About ten minutes after the first listen was logged the listens so far are on listenbrainz.org and in `.scrobbler.log.sent`; `.scrobbler.log` holds only what was logged since. No toast at any time |
| SCROB-UP-14 | Auto Upload on, Wi-Fi off: play for 20 minutes; then connect Wi-Fi and keep playing | Nothing is uploaded and the Wi-Fi is not switched on while it is off; within about a minute of the connection the whole log is uploaded. No toast |
| SCROB-UP-15 | Auto Upload on, a wrong token in `scrobble.ini` and no settings page opened since (so it is not checked), Wi-Fi connected, play for 15 minutes; then open Settings > Library > Scrobbling | The row and the Account row read Invalid Token; no toast was shown; the log is untouched and nothing more is tried. The right token written into the file: the name shows when a page opens, and the log is uploaded while music plays |
| SCROB-UP-16 | Auto Upload on, a long log (a few hundred lines): open Settings > Library > Scrobbling while the automatic upload runs (about ten minutes into playing) and tap Upload Scrobbles | "Already uploading"; no toast when the automatic upload ends; a second tap after that starts the user's own upload with its own toast ("Nothing to upload") |
| SCROB-UP-30 | Open Settings > Library; open its Scrobbling row, turn the switch on, go back; then off and back again; with Scrobbling off tap Upload Scrobbles on the page (a log on the card, an account set up, Wi-Fi) | The Library row says Off, then On, then Off, each time right after the page is back (not before); with it off the account rows, Auto Upload and Upload Scrobbles are not dimmed and the upload starts |
| SCROB-UP-17 | Auto Upload on: play for 12 minutes, let the screen go dark and keep playing through three more songs | The uploads go on with the screen dark (the log empties about every ten minutes of new listens); no toast when the screen is lit again |
| SCROB-UP-18 | Auto Upload on: start playing, pause after the first listen is logged and let the device go to standby before ten minutes pass; wake it and play on | The upload happens within about a minute of playback resuming, once the listen is ten minutes old (a run that standby cut off in the middle of a request is tried again half an hour later); nothing is lost from the log |
| SCROB-UP-19 | On a computer, add to `.scrobbler.log`, between good lines, one line whose time is a year in the future (ListenBrainz is expected to refuse it with a 400; if it takes it the check is void), then Upload Scrobbles | "N sent, 1 rejected": only that line is in `.scrobbler.log.rejected`, the others of its batch are on listenbrainz.org and in `.scrobbler.log.sent` |
| SCROB-UP-23 | On a computer add `[LASTFM]` with `USER`, `PASSWORD`, `API_KEY`, `API_SECRET` (an API account made at last.fm/api) to `scrobble.ini`, keep the ListenBrainz token; play two tracks, then Upload Scrobbles | "N sent": the listens are on listenbrainz.org and on last.fm, with the right artist, title, album and time (CJK tags too); the log is its header; `scrobble.ini` is byte for byte as written (no session key in it) |
| SCROB-UP-24 | As SCROB-UP-23 with only the `[LASTFM]` section in the file | The upload starts (no "Set up an account first") and the listens are on last.fm |
| SCROB-UP-25 | As SCROB-UP-23 with a wrong `PASSWORD`; Upload Scrobbles twice | First: "Last.fm: Sign-in Failed" and the log is untouched. Second: the listens go to ListenBrainz alone and leave the log. With the right password written into the file the next upload reaches Last.fm again (only listens logged after that) |
| SCROB-UP-26 | As SCROB-UP-23; put a line whose time is a month old into `.scrobbler.log` on a computer, then Upload Scrobbles | Last.fm ignores it (too old), ListenBrainz takes it: the line is in `.scrobbler.log.sent`, not in `.rejected`; the others are on both services |
