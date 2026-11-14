/* M1+ Music: the scrobble upload settings (ListenBrainz, Last.fm) (patch/scrobpage.c, docs/modules/scrobble.md "Settings"): what patch/m1plus.c's Settings pages call.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

/* The rows' texts (UTF-8, already translated; n bytes).
 * lb_row_text: the Scrobbling page's ListenBrainz row: "Not Set", "Invalid Token", the user name, or "" for a token no check has confirmed.
 * lb_account_text: the ListenBrainz page's Account row: the same, and "Checking…" while a check runs.
 * lf_row_text: the Scrobbling page's Last.fm row: "Not Set", "Sign-in Failed", or the file's USER value. lf_account_text: the Last.fm page's Account row: the same, and
 * "Checking…" while its check runs. */
void lb_row_text(char *out, unsigned n);
void lb_account_text(char *out, unsigned n);
void lf_row_text(char *out, unsigned n);
void lf_account_text(char *out, unsigned n);

/* The Scrobbling page's Upload Scrobbles (a toast now, and one at the end from the pages' timer). No account is set or removed here: the user writes the card's
 * scrobble.ini. */
void lb_upload_tap(void);

/* The Scrobbling page (page 0), the ListenBrainz page (1) or the Last.fm page (2) has opened: the card's scrobble.ini is read again (and an account no check has confirmed
 * is checked, with the Wi-Fi up), and a timer runs while a job is in flight and one of the pages is up. */
void lb_opened(void *win, int page);
void lb_on_front(void);

/* patch/m1plus.c: the pages read their rows again. */
void pod_lb_refresh(void);
