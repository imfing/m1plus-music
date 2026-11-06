# Software Update (`patch/update.c`, `patch/relnotes.c`, `patch/upver.c`, `patch/pcnet.c` "Software Update", `test/pod/update.py`, `test/pod/updatepage.py`)

An over-the-air update for this project: over Wi-Fi the page finds the newest GitHub release, downloads its `update.bin` to the TF card's `/mnt/mmc/update.bin`, then calls the firmware's own TF card update, so the user
lands on stock's confirmation. **Stock still does the battery check, the confirmation, the MD5 checks and the flash**; nothing here touches flashing, the bootloader or the recovery kernel.
No new hook, no patched stock word and no new import: the entry is a link row on the About page, the page a new window asset, the network the Podcasts worker's libcurl client (one job slot), the hand-over a **pinned call** of
stock's TF card update click handler (below). The dialogs are the payload's existing ones: the stock confirm dialog (as Screenshot and Rebuild Covers use it) and the Podcasts refresh dialog's scrim and card.

The design follows q2-pod's Network Update (github.com/DiamondBond/q2-pod, `patch/netupdate.c`, `docs/internals.md` "Network Update"): a header-only request to `releases/latest` whose redirect names the tag, a download
into `<asset>.part` that is renamed into place only when complete (a failure deletes the `.part` and keeps the old file), a page that shows the progress, keeps the device awake and cancels on a second press, and the
firmware's TF card update at the end. The code is our own. Differences: the asset is fetched by its tag (not `latest`), the version is compared as numbers, and the downloaded package's own version lines are checked.

Preview: `uv run python -I tools/preview_update.py work/mod-release out/preview/update.png [--lang CODE]` (sixteen states, the notes page not drawn; the asset walked by the shared painter, not pixel-exact; not tracked).

## What the user sees

- **The row**: Settings > System > About > **Software Update**, a link row (chevron, no glyph, the About page's row style; `ACT_UPDATE`) **right below the version row** (M1+ Music) in the About page's first card. It is not in the System card
  (Settings > System lists Display, Appearance, Keyboards, About, All System Settings as on main); Developer > Tools > System Update (the stock page) stays. Back from the update page returns to About. With the kill switch `/mnt/mmc/m1plus-off` `update_open` refuses.
- **The page** (black, the stock navbar with Back and Now Playing, neutral white and grey, no accent colour): one block with **fixed places** (`tools/pod_ui.py UP_YS`: the same in every state, so nothing jumps), centred in the 400 px under the navbar: a 48 px glyph, 16 px, the title (22 px white), 8 px, the detail (18 px grey #AAAAAA, centred, at most two lines of 280 px), 24 px, a pill (260 x 48, 20 px text), 12 px, a second pill; a state shows the parts it has (`patch/update.c up_apply`). Every string is one of our translation keys (13 languages, `docs/modules/i18n.md`); `%s` is the version, put in by the payload.

  | State | Glyph | Title | Explanation | Pills |
  |---|---|---|---|---|
  | idle | download | M1+ Music | Version 1.0.0 (the installed version; a development build shows its `V2.1z...` tag) | Check for Update |
  | checking | | Checking… | | |
  | up to date | check | Up to Date | You have the latest version. | Check for Update |
  | offered | download | Version 1.0.1 available | Current version: 1.0.0 | Download and Install, Release Notes (only when the check kept the release's notes) |
  | downloading | | the popup (below) over the offer | | |
  | downloaded | check | Update Downloaded | Version 1.0.1 is ready to install. | Install, Check Again |
  | no Wi-Fi | wifi | Connect to Wi-Fi first | Turn on Wi-Fi and try again. | Try Again |
  | clock never set | calendar | Set the date first | Secure connections need the right date. | Try Again |
  | no CA bundle | lock | Certificates missing | This device has no certificate bundle. | |
  | certificate | lock | Certificate problem | The server's certificate was not accepted. | Try Again |
  | no connection | plug | Can't reach GitHub | Check your Wi-Fi connection. | Try Again |
  | not a release answer | info | Can't check for updates | GitHub did not name a release. Try again later. | Try Again |
  | wrong package | info | Download doesn't match | The file was not the version offered. Nothing was changed. | Try Again |
  | under 110 MB free | card | Card is full | Free at least 110 MB on the card. | Try Again |
  | write failed | card | Can't write to the card | Check the TF card and try again. | Try Again |
  | no memory | drive | Not enough memory | | Try Again |
  | cancelled | download | Download cancelled | | Download and Install |

  **Try Again** repeats the job that failed: the check, or the download of the release already offered (without asking again). The title of "Version 1.x.y available" is sized for two digits a part; a longer number is clipped by its label.
- **Release Notes** (offered state only, the second pill) opens a page of its own (below) with the release's notes. Back returns to the update page, still offering the release; Now Playing is the update page's own handler (`pod_on_player`: it leaves and cancels what runs).
- **Download and Install** asks first in the **stock confirm dialog** (`pod_confirm_code`, `dialog/confirminfo_dialog`, kind 5, modal): "Download 1.0.1 (55 MB)? It replaces update.bin on the card." in the dialog's own 20 px type (the same as Screenshot, Rebuild Covers and the others). The label is 260 px less the style's 12 px margins (236 px) and breaks at spaces only; `test/pod/updatepage.py` wraps every translation at that width (three lines at most, "55 MB" never split); the page behind the translucent dialog is cleared while it is up. Its two buttons are relabelled **Cancel** (left, `btn_cancel`)
  and **Download** (right, `btn_enter`) by a timer that finds the dialog by name, the way the Screenshot dialog's buttons become 5 s / 10 s (`patch/shot.c`; stock reads the results 4 and 0xa). **Cancel (or the back key) starts nothing and makes no request.**
- **The download popup**: Yes opens a modal popup over the page, the Podcasts refresh dialog's own pieces (a full-client scrim that takes every touch, the glass card with a Cancel row; `tools/pod_ui.py podcasts_dialog('up_pd', ...)`): the title
  "Downloading 1.0.1" (20 px, the stock dialog's message size), a grey line (18 px, "This may take a few minutes."), a 6 px rounded progress bar, "NN%" (20 px) and **Cancel** (20 px, a 48 px row like the stock dialog's buttons; 20 px side padding; `podcasts_dialog(big=True)`). Cancel (or Back, which is Cancel while the popup is up) asks the worker to stop; the button goes dead and the line says
  **Cancelling…** until the worker has really stopped; then the popup closes, the `.part` is deleted, the old `update.bin` stays and the page says Download cancelled. **Errors close the popup and show on the page** (the table above). A download waiting for the
  job slot shows the popup at 0 % at once (Cancel drops it). A page opened while the previous page's job is still ending shows the popup as Cancelling….
- **When the download finishes** the popup closes and, with this page in front (`EVT_WINDOW_TO_FG`/`BG`), **stock's TF card update is called directly on the next tick** **with the page's block cleared around it** (device findings, V2.1zANMEAAAF and AAAG: stock's install confirmation looked wrong, the page's Install and Check Again pills standing out behind it, while our own confirmation looked right. It is the same asset, `dialog/confirminfo_dialog` at `0x744570`, opened by `navigator_to_with_context` at `0x4a71cc` with a kind 1 context, so there is no other asset to restyle; the difference is that our `up_ask` clears the page block first because the dialog is translucent, and the stock call did not. Deferring the call one tick did not change it, so the clearing, not the highlighter or the timing, is what makes ours look right.) `up_hide_block` clears the glyph, texts and both pills (visible=false and sensitive=false) in the tick that closes the popup; the next tick (`up.install_wait`, so the clear is painted first) calls stock and `up_sync` restores the block when the call returns, whatever it returns. The confirmation is modal (`navigator_to_with_context` returns the answer, `0xa` for Yes) and the flash dialog after a Yes is opened by `navigator_to` (`0x4a7208`), so the call returns and the block comes back under it; the Install pill does the same in one step. If another window came in front in between, the block is restored and the pill does it later. `test/pod/updatepage.py` flow_tests pins the order: popup hidden, block cleared, stock's call, block restored (its click handler: stock's confirmation "msg_confirmupdate", then `check_updatefw_exist`, the low-battery /
  not-found / latest messages, then the flash dialog): the user lands on stock's own confirmation, no page opens in between. If the user says No there, the page shows Update Downloaded with **Install** (calls it again) and **Check Again**. While another window is
  in front, or after a Cancel, nothing is started; the Install pill does it.
- **Check Again** (after a download) asks GitHub again. A version that is offered, **including the one already downloaded**, can be downloaded again: the same `.part` -> verify -> rename path replaces `update.bin` (the old file stays until the new one is
  verified, and stays on a failure, a cancel or a package that is not the offered version). Nothing newer: Up to Date (the downloaded file stays on the card); a failed check shows its error.
- **Opening the page** forgets an old answer or failure (the page starts from the installed version) but keeps a finished download while `/mnt/mmc/update.bin` is still on the card: Update Downloaded with Install and Check Again, "elsewhere, next time".
- **Now Playing** leaves the page and cancels what runs (a download's `.part` is deleted, `update.bin` stays as it was); the worker ends by itself.
- While a job runs the page's 250 ms timer calls stock's `reset_poweroptions_timer(1, 1, 0)` once a second (the standby and auto power-off countdowns set again, the screen's light left alone; stock standby would stop the Wi-Fi), exactly as the
  Podcasts downloads do (`docs/modules/payload.md`). It is the page's own timer (removed with the window), not a global one. Under a stock dialog (a modal call) the timer and the pills leave everything alone (`up.modal`).
- **One job at a time.** The check and the download are jobs of the one worker slot of `patch/pcnet.c` (`PN_KIND_UPDATE`, counted by `pn_job_busy`). A running Podcasts download is paused first (`pn_dl_pause`; its queue stays), the job starts from the tick
  once the slot is free (the title already says Checking… / Downloading 0%), and the queued downloads start again when the slot is free and the page has nothing waiting (and on destroy).

## Release notes (`patch/relnotes.c`, `patch/upver.c up_notes`, `pcnet.c pn_up_notes_fetch`)

Right after a check that results in an offer, the same worker job asks `https://api.github.com/repos/<repo>/releases/tags/<tag>` (the tag the check found, never `latest`; same options as every request: https only, verification on, the firmware CA bundle,
the worker's `User-Agent`, no `SSL_VERIFY*`) and keeps the release's `body` in memory (`pn_up_notes`, heap, freed by the next check or `pn_up_reset`; nothing on the card). **Only HTTP 200 counts and every failure is non-fatal**: a 404, a 403 rate limit,
a network or certificate error, an answer over `PN_UP_API_CAP` (64 KB; a larger one fails the transfer), JSON without a top-level body, `null`, empty or malformed leave the offer standing without notes (no pill). Up to Date and the error states fetch nothing; a new check clears the old notes;
Cancel during the notes request cancels the check.

`up_notes` finds the top-level `"body"` string with a depth-tracking scan (a `body` key of the `author` or `assets` objects is never taken; only the exact raw key `body` matches), decodes it in place (`\n \r \t \" \\ \/ \b \f`, `\uXXXX` to UTF-8 with surrogate pairs; a lone surrogate becomes U+FFFD, `\u0000` is dropped; a bad escape, a raw control character or an unterminated string is no notes) and cleans it for the screen:
`\r` dropped, `#`..`######` heading markers and `**` dropped, `- ` and `* ` items shown as `• `, three line feeds made two, blank edges trimmed, everything else plain text. The result is cut at `UP_NOTES_MAX` (8192 bytes) between two UTF-8 characters.
The `Accept: application/vnd.github+json` header is **not sent**: it needs `curl_slist_append`, which the payload does not import, and GitHub's API answers JSON without it.

**The page** (`m1plus_relnotes`, `tools/pod_ui.py build_relnotes_page`, `Release Notes` is its navbar title and the pill's text): black, the stock navbar with Back and Now Playing, and the Find Cover & Lyrics lyrics detail's scroll mechanism: a stock list (`list_view > scroll_view` + scroll bar) holding ONE content view that
the payload paints in its `EVT_AFTER_PAINT` with the scroll offset taken off the canvas (`SC_YOFF`), and sizes with `widget_resize` and `virtual_h`, so the stock scroll view does the dragging and the fling. The text is wrapped once by the Podcasts episode page's wrapper (`pd_lines`, `patch/pcwrap.c`: from the font's own advances, kinsoku, CJK anywhere) to 288 px at x 16:
the heading "Version 1.0.1" (22 px white) at y 12, then the notes (18 px, #E6E6E6) 24 px apart, 12 px for an empty line. A line shows only when wholly inside the 400 px view. Limits: 600 characters a source line, 40 wrapped lines a source line, 700 lines in all (8 KB of notes need about 270). Neutral white and grey, no accent colour.

## The version rules (`patch/upver.c`, tested as tables)

- **The tag** is exactly `D+.D+.D+`: three runs of 1 to 5 decimal digits joined by dots, nothing before, between or after: no `v`, no `-rc1`, no sign, no space, no `\r`, `\n`, `?query` or `#fragment`, no sixth digit (`100000.0.0`). Anything else is
  "Can't check for updates", never "newer". Leading zeros parse (`01.002.0003` = 1.2.3; the tag text is kept as it is for the address and the package line).
- **The comparison** is numeric, major then minor then patch (1.10.0 > 1.9.9, 2.0.0 > 1.99.99, 1.0.1 = 1.0.1).
- **The build's own version** is `tools/build.py VERSION`, injected by `tools/pod.py` as `-DM1PLUS_VERSION` (the same constant that makes `TAG` and the About text), with `-DM1PLUS_DEV` (1 when the build tag is not the release's: a `V2.1z...` dev build) and
  `-DM1PLUS_REPO` (`tools/build.py REPO`, `imfing/m1plus-music`, the one place the repository is named; the address is built from it). They live in `up_own`, `up_dev` and `up_repo` (writable, so a test can set them); `test/pod/update.py build_tests`
  proves the payload's version equals `build.VERSION` and parses, the repository equals `build.REPO`, the flag follows the tag.
- **What a release means** (`up_offer`): a release build is offered a tag strictly newer than its version; equal or older is "Up to Date" (so a newer build is never offered an older release). **A development build has no comparable version: it is always
  offered the latest release** (any valid tag, whatever its number; "Version 1.0.0 available"), and every other check below still applies. Stock's updater accepts it because `V2.1z...` differs from `V2.1-<tag>` (it refuses only an identical version, there is no
  "newer" check on the device, so this page is the only downgrade guard).

## The check

`pn_up_check` (UI thread: the guards of `pn_guard`: card, Wi-Fi, clock, CA bundle `/etc/m1plus-cacert.pem`; then one detached pthread) asks `https://github.com/<repo>/releases/latest` **header only, without following**
(`CURLOPT_NOBODY`, `CURLOPT_FOLLOWLOCATION` 0, https only, verification on, no `SSL_VERIFY*` option is ever set). The answer is accepted only when **all** hold: curl succeeded, the status is a redirect (301, 302, 303, 307, 308), and
`CURLINFO_REDIRECT_URL` is **exactly** `https://github.com/<repo>/releases/tag/<tag>` for the configured repository with a tag that parses (`up_redirect_tag`: the prefix is compared, not a "contains"). A 200, a 404 or other HTTP error, a missing Location,
another host, another repository, `http://`, a different path, another case, or a bad tag is `PN_UPCHECK`, never "up to date". Network failures are the Podcasts codes (`PN_NET`, `PN_CERT`, `PN_NOCERT`). The tag of an offered release is held for the download.

## The download

`pn_up_download` (needs an offered release; the guards again; `statfs` of `/mnt/mmc`: **at least 110 MB free** (`PN_UP_NEED_KB` 112640, the package is about 55 MB and the one it replaces stays until the rename), else `PN_CARDFULL` and nothing is touched):

1. `/mnt/mmc/update.bin.part` is deleted and created fresh (no resume: a half file is not trusted).
2. `https://github.com/<repo>/releases/download/<tag>/update.bin` **by the tag the page showed, never `latest`**, so a release published between the check and the download cannot swap in another version. Redirects are followed (to the asset host), https
   only (a redirect to http is refused), verification on, no gzip, `CURLOPT_TIMEOUT` 0 (55 MB on a slow link; the low-speed limit of 1 kB/s for 30 s still ends a stalled one), at most 128 MB (`PN_UP_CAP`).
3. Every write goes to the `.part`; the progress is libcurl's transfer-info callback (`pn.part`, the page shows `pn_up_pct`); **Cancel** (`pn_cancel`) stops the transfer through the same callback.
4. When curl succeeded (HTTP 200, the whole answer, the same length as `Content-Length` when the server gave one): `fsync` and `close` the `.part`.
5. **The package must say it is the version offered** (`up_info_ok`): the file is a tar whose **first member is exactly `firmware_v20.info`** (a plain file, magic `ustar`, a correct header checksum, one block of text at most), line 1 is `Shanling M1 Plus` and line 2 is
   `V2.1-<tag>` (`tools/build.py TAG`), each ended by a line feed. Another model, another version, the stock `V2.1`, a dev tag, a missing second line, CRLF, a `./` in the name, the member not first, a link, a damaged header, a file cut short or not a tar: `PN_UPBAD`
   ("Download doesn't match"). This makes the file on the card the version that was offered (the MD5s of the other members are stock's check at install time).
6. `rename(.part, update.bin)`, then `fsync` of `/mnt/mmc`. **Any failure before the rename deletes the `.part` and leaves the old `update.bin` as it was.** A directory `fsync` that fails after the rename is reported (the file is in place).

A write that fails is "Card is full" when `statfs` then shows under 1 MB free, else "Can't write to the card" (errno is not reachable from the payload). Not verified: `SHA256SUMS` (`make publish` uploads it). A first version trusts TLS to GitHub,
curl's length check, the info lines and stock's own MD5 check; verifying `SHA256SUMS` is a follow-up.

## Development channel (`patch/upver.c`, `tools/ota_server.py`)

For development, a local server can stand in for GitHub (`make ota-serve`, `make ota`; the address goes in a card file, `UP_CHAN_FILE`). The package checks above still apply. Tests: `test/pod/update.py channel_tests`.

## Pins and hooks

**One new pinned stock call, no hook.** `tf_update_click` is the click handler of the `listitem_sd` row ("TF card update") of `systemset/fwupdate_page` at **`0x4a7160`** (`tools/pod.py` `TF_UPDATE`, `TFUPDATE_PINS`: the prologue, the string loads,
the `jalr`s and the widget walk that binds it, all checked against the stock binary; the build refuses on a mismatch). It is a plain function that **ignores its arguments** and uses no page state: it builds the stock message `msg_confirmupdate` and
calls `navigator_to_with_context("dialog/confirminfo_dialog")` (modal; only Yes, 0xa, goes on), then `check_updatefw_exist("/mnt/mmc", "/mnt/mmc/update.bin")`: 1 -> `navigator_to("dialog/cardupdate_dialog")` (the flash dialog: its init
`0x471578` stops the player and starts the update thread), and the other results are stock's own messages (`msg_lowpower` for the battery, `msg_notfoundfw`, `msg_latestfw`, `msg_checkfwerr`, `msg_nottf`, `msg_notmemory`). Nothing in it reads
the System Update page's widgets, so the payload calls it directly on the UI thread from a click handler or the page's timer, exactly as stock's event loop does; nothing it needs is a new hook, patched word or import (the pins live in
`tools/pod.py` with the other stock-code pins; the payload defines `tf_update_click` as a macro of the absolute address like `stock_playlist_import`). Opening `systemset/fwupdate_page` is therefore no longer needed (Developer > System Update still does).
Not run on a device: the flash itself is stock's, untouched.

`reset_poweroptions_timer` (`0x4d7874`, `PODCAST_PINS`) and `navigator_back` were pinned already; this page's timer is a second caller of the first. `tools/pod.py` `SOURCES` gains `upver.c` (before `pcnet.c`) and `update.c`, and compiles with
`-DM1PLUS_VERSION`, `-DM1PLUS_DEV`, `-DM1PLUS_REPO`; `patch/curlopts.h` gains `CURLOPT_NOBODY`, `CURLPROTO_HTTPS`, `CURLINFO_REDIRECT_URL` and `CURLINFO_CONTENT_LENGTH_DOWNLOAD_T`; `up_dev` is placed in a `.data.up_dev` section (a zero would be `.bss`,
which the payload has none of). Assets: `ui/m1plus_update.bin` (`tools/pod_ui.py build_update_page`, `pod_pages.UPDATE`; `podcasts_dialog` takes the widget prefix and the title key), the About page's row `ACT_UPDATE` (44), `ui/m1plus_relnotes.bin` (`build_relnotes_page`, `pod_pages.RELNOTES`), the glyphs `pod_es_download` and
`pod_es_check` (`tools/mod_icons.py ES_ICONS`, `assets/icons/png`), 29 translation keys (`tools/pod_i18n.py`; "Release Notes" is the new one). `pcnet.c` gains no import (`calloc` and `free` were there); `tools/pod.py` `SOURCES` gains `relnotes.c`. No import is added (open, read, write, fsync, rename, unlink, statfs, access, snprintf and libcurl's easy interface were there).

## Tests

- `test/pod/update.py` (worker, scripted libcurl): the parser and comparison tables (valid, leading zeros, six digits, `v1.0.0`, `1.0`, `1.0.0.0`, `1.0.0-rc1`, empty, trailing CR/LF/space, a query, a fragment, non-ASCII digits), what a tag means for a release and a development build, the redirect
  table (exact prefix, other host / repo / scheme / case / path, bad tags), the build's version, flag and repository against `tools/build.py`, `up_info_ok` on real tars (valid, an older or other version, the stock version, a dev tag, another model, one line, no line feed, CRLF, cut at every
  header boundary, a bad checksum, another member name, not first, a link, zeros), the release notes (`up_notes` on the real GitHub answer for 1.0.0 saved in `test/data/release/`: assets, uploader and author objects before the body; escapes, surrogate pairs, a nested `body` key before the real one, null, empty and truncated bodies, bad strings, markdown, the byte cap at every character size; the notes request's address by tag, its options, every failure (403 / 404 / 500, network and certificate, 64 KB limit, bad JSON) leaving the offer without notes, old notes cleared by a new check, nothing fetched for Up to Date or an error, Cancel during the request), the check (options, every verdict, 200 / 404 / 500 / 503 / 304, no Location, the five redirect codes, network failures, the guards, no thread, Cancel, a failed second check forgetting the first offer), a development
  build (offered 1.0.0, 0.0.1, 1.0.1, 9.9.9 and downloads each, with every reliability check still applied), the download (the tag's address, the options, the `.part` and the rename order with the directory `fsync`, the old `update.bin` intact during the transfer, the progress, wrong packages,
  announced lengths, network and HTTP failures and a second try, write / open / fsync / rename / directory-fsync failures, card full, 109 / 110 MB, no Wi-Fi, Cancel and starting again, `pn_up_reset`).
- `test/pod/updatepage.py` (the page under Unicorn): the asset (boxes, hidden and insensitive widgets, the popup's scrim and card, contrast, neutral colours, every text in 13 languages, the confirm text in three lines, the About row), the flow (idle, check, offer, the confirm dialog,
  the popup watched by the page's timer, the direct call of stock's TF card update and no page), the confirm dialog (Cancel / back / 0 start nothing and make no request; its buttons relabelled; the text in 13 languages), the popup (Cancel, Cancelling… until the worker stopped, Back is Cancel,
  errors close it, a waiting download), Check Again and a second download over an existing `update.bin` (a failure, a cancel and a wrong package keep the first file; success replaces it through the `.part`; up to date; a failed check; a development build), reopening, a page in the background,
  every failure in 13 languages and Try Again, every state in 13 languages, waiting for a busy slot, the power timers, destroy, the kill switch, a wrong asset, the About row. The call of `tf_update_click` is mocked (it is stock's flash path). The Release Notes pill only when the check kept notes (and not under the popup, in Up to Date or Update Downloaded), the notes page (asset, neutral colours, heading and wrapped lines at their places, a long text scrolling to its last line, CJK and unbroken words wrapped, Back returning to the same offer, destroy and reopening, a window or asset that fails, the pill and heading in 13 languages).

## Device checks (not run)

TLS to `github.com` and the asset host with the firmware CA bundle (a `Certificate problem` says a root is missing); the 302 of `releases/latest` as the device's libcurl sees it (`CURLINFO_REDIRECT_URL`); a 55 MB download on the card (speed, the 120 s limit gone, the stall limit); the power timers
(no standby or auto power-off during a long download with the screen off); the confirm dialog's relabelled buttons (the dialog's name and button names as stock has them); the popup over the page; **the direct call of stock's TF card update handler** from our page and our timer (its
confirmation, the battery check, the flash dialog; what Back does afterwards); the notes: `api.github.com` with the firmware CA bundle (a `Certificate problem` on the notes only leaves no pill, so look for the pill on a release that has a body), the unauthenticated rate limit (60 requests an hour per address: a 403 just hides the pill), the pill and the page on the device (scrolling by finger, the scroll bar, Back to the same offer, Now Playing); Check Again and a second download over an existing file; a card under 110 MB free; Wi-Fi lost mid-download (`Can't reach GitHub`, the `.part` gone); Cancel and Back during a download.
