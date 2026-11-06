/* Software Update, the pure rules (patch/upver.c; docs/modules/update.md): the release tag, the comparison, the redirect and the downloaded package's first lines.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Nothing here touches the network, a widget or a stock function; patch/pcnet.c runs them on the worker's answers.
 */
#pragma once

#define UP_TAG 20 /* a tag buffer: "99999.99999.99999" and the NUL */
#define UP_MODEL "Shanling M1 Plus" /* line 1 of the package's firmware_v20.info (stock's updater compares it) */
#define UP_PKG_PREFIX "V2.1-" /* line 2 is this and the tag (tools/build.py TAG) */
#define UP_INFO "firmware_v20.info"

/* 1 when s is exactly major.minor.patch: three runs of 1..5 decimal digits, joined by dots, nothing before, between or after (no "v", no suffix, no space, no CR, no query, no sign). v: the three numbers. */
int up_parse(const char *s, unsigned v[3]);
/* major, then minor, then patch: -1, 0 or 1. */
int up_cmp(const unsigned a[3], const unsigned b[3]);
/* What a release tag means for a build whose version is own (dev: a development build, which has none to compare): 0 the tag is not a version (nothing is offered), 1 the build is as new or newer ("Up to date"),
 * 2 the release is offered. A development build is offered any valid tag. */
int up_offer(const char *tag, const char *own, int dev);
/* The tag in the Location of the answer to https://github.com/<repo>/releases/latest: the Location must be exactly https://github.com/<repo>/releases/tag/<tag> with a tag that up_parse accepts. 1 and the tag in out, else 0. */
int up_redirect_tag(const char *location, const char *repo, char *out, unsigned size);
/* 1 when the tar file at path starts with the member firmware_v20.info (a valid header, its checksum right) whose first two lines are UP_MODEL and UP_PKG_PREFIX + tag (a development tag: the tag
 * itself), each ended by a line feed. */
int up_info_ok(const char *path, const char *tag);

/* The development channel (docs/modules/update.md "Development channel"): the card file UP_CHAN_FILE names a server that answers GitHub's paths under its own address. */
#define UP_CHAN_FILE "/mnt/mmc/m1plus-update-url"
#define UP_BASE 97 /* the server's address and the NUL */
/* 1 when s is a development build's tag: "V2.1z" and 1..12 capital letters (tools/workflow.py). */
int up_devtag(const char *s);
/* The channel file at path: -1 when it is unreadable as an address, 0 when there is none, 1 and the address in base (UP_BASE bytes): "http://" or "https://" and printable ASCII without spaces,
 * trailing white space and slashes dropped. */
int up_chan_read(const char *path, char *base);
/* The tag in the Location of the answer to <base>/releases/latest: exactly <base>/releases/tag/<tag>, the tag a version (up_parse) or a development tag. 1 and the tag in out, else 0. */
int up_chan_tag(const char *location, const char *base, char *out, unsigned size);
/* What a channel's tag means for the build whose About text is about (M1PLUS_TAG): 1 the same build ("Up to date"), 2 any other one is offered (older or newer: the server says what to install). */
int up_chan_offer(const char *tag, const char *about);

/* Where the jobs ask (patch/pcnet.c knows nothing of the channel; it asks these). up_source, at the start of each check: the channel file into up_base ("" for GitHub); -1 when the file names no address. */
int up_source(void);
enum { UP_URL_LATEST, UP_URL_NOTES, UP_URL_ASSET };
/* The address of a request (the tag of the notes and the asset): GitHub's, or the same path under up_base. */
void up_url(int what, const char *tag, char *out, unsigned size);
/* 1 for GitHub: https only. A channel may be http. */
int up_https_only(void);
/* The redirect's Location of the latest request: 0 it names no release, 1 the build is up to date, 2 the release in tag (size >= UP_TAG) is offered. */
int up_latest(const char *location, char *tag, unsigned size);
/* 1 when tag is one the download accepts: a version, or a development tag. */
int up_tag_ok(const char *tag);

/* The release notes of GitHub's release JSON (js, n bytes; DECODED IN PLACE, so it is changed): the top-level "body" string (a "body" key of a nested object is never taken), its JSON escapes decoded to UTF-8
 * and cleaned for the screen (carriage returns dropped, heading # and bold ** dropped, "- " / "* " items shown as a bullet, no blank edges), into out (cap bytes, the NUL included; cut between two UTF-8 characters).
 * Returns the length, 0 for no notes: no body, null, an empty or malformed string, not an object. */
#define UP_NOTES_MAX 8192 /* bytes of notes kept, without the NUL */
unsigned up_notes(char *js, unsigned n, char *out, unsigned cap);

/* The build's own version (tools/build.py VERSION, the compiler's M1PLUS_VERSION), whether it is a development build (M1PLUS_DEV) and the repository (M1PLUS_REPO). Writable so a test can change them. */
extern char up_own[UP_TAG];
extern int up_dev;
extern char up_repo[48];
extern char
    up_base[UP_BASE]; /* the development channel the last check read, "" for GitHub (the download asks the same) */
extern char up_about
    [UP_TAG]; /* the About text (M1PLUS_TAG: the version, or a development build's tag), what the channel compares */
