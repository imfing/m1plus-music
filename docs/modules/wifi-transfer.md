# Wi-Fi Transfer

**Sources:** `patch/netservice.c` (pages), `patch/qr.c` and its model `tools/qr.py` (the QR code),
`patch/webapi.c` (`api.cgi`), `assets/webapp/index.html`, `tools/mod_webapp.py`, `tools/pod_pins.py`
`NETSERVICE_PINS`.

Stock runs `thttpd -C /etc/thttpd.conf` when Wi-Fi Transfer is on (port 8888, `dir=/usr/share/web`,
`cgipat=**.cgi`, `user=root`). The mod leaves the player binary, thttpd and its configuration alone and
replaces what thttpd serves: one CGI, `/cgi-bin/api.cgi`, and one hand-written vanilla-JS page. No hook,
nothing at boot or paint. The device side is Settings > Network Services and its Wi-Fi Transfer page.

## Network Services and the device page

Settings > Network Services (`m1plus_netservice`) and its Wi-Fi Transfer page (`m1plus_wifitransfer`)
replace stock's `systemset/netservice_page` and `systemset/wifitransport_page`. All System Settings keeps
stock's own pages. The state is stock's own bytes; nothing of ours is saved.

| Page | Rows |
|---|---|
| Network Services | AirPlay switch (ACT 166), DLNA switch (167), a gap, **SyncLink** (opens stock's page, Back returns here), **Wi-Fi Transfer** (168) |
| Wi-Fi Transfer | no rows; centred: a hero (tile, white `wifi` glyph, title, grey description) or, in its place, the address as a QR code; one address card `<ip>:8888` (22 px bold, no `http://`), a grey footer note, the Show QR Code pill |

- **Switches** call stock's `airplay_switch` / `dlna_switch` and show the byte. There is no
  AirPlay-playing guard, as on stock's page (the Control Center tiles do refuse; [pulldown](pulldown.md)).
  Turning one on without Wi-Fi shows the toast "Connect to Wi-Fi first"; the byte is still stored.
- **The row** and the Control Center tile ([pulldown](pulldown.md)) open the page only while Wi-Fi is
  connected; otherwise the toast and no window (stock opens a message dialog). Both go through
  `pd_open_page`, so there is one window: one left behind the player is restacked, never opened twice.
- **Start on open.** In stock's order: bind a key filter, the close handler and a destroy handler, then
  `stop_player()` and `switch_wifitransport(1)` (the `thttpd` command above). A refused bind starts
  nothing. The key filter swallows the media keys `0xd5`..`0xd7` as stock does; volume keys work.
- **Address.** `pod_big0_t` shows `<ip>:8888`, or `-` without a connection, as the page opens and each
  time it is back in front. It takes no tap.
- **Stop on close.** EVT_WINDOW_CLOSE (Back, Home, any close) calls `switch_wifitransport(0)`; EVT_DESTROY
  does the same once for a window that never saw the close.
- **Decision:** the Now Playing button also stops the server and the page restarts it, without stopping
  the player again, when it is back in front (EVT_WINDOW_TO_FG). Stock leaves the server running under the
  player, with the pull-down and the standby countdown blocked.
- Wi-Fi dropping, USB, the lock screen and power-off are as in stock: nothing is stopped.
- The page's texts are our own keys in 13 languages; stock's long `wifits_info` texts are not used.
  `AirPlay` and `DLNA` are brands.
- The page uses the layout items `Hero`, `QrCard`, `BigCard`, `Note(center=True)` and `QrPill`
  ([settings](settings.md#cards)).

### QR code

- **The pill.** Under the note, a small flat pill (`pod_qrbtn`: the rest surface, the grey 14 px label
  and Lucide `qr-code` glyph `wt_qr`) reads Show QR Code. A tap hides the hero and shows the code
  (`pod_qr`) in its place; the pill then reads Hide QR Code and a second tap swaps back. The two items
  are as high as each other and the layouter stacks only the visible one, so the address card, the
  note and the pill never move. Every open starts with the hero; Now Playing and back keeps the state.
  `wt_pill_fit` sizes the pill to its label and centres the glyph and label as a pair
  (`m1_pill_styles`), 5 px apart. The label sits `PILL_DROP` (1) px below the pill's centre, so its
  capitals centre on the pill and the glyph: `margin_top` 3 and
  `margin_bottom` 1 move the text and icon box down, and `wt_qr.png` has 2 clear rows under the
  glyph, which keeps the glyph where it was.
- **The code.** `HTTP://<ip>:8888` in capitals: the alphanumeric mode has no small letters and a
  browser accepts the scheme in any case. `patch/qr.c qr_make` makes version 2 (25 x 25), level M,
  one alphanumeric segment of at most 38 characters, the mask of least penalty; the longest address
  (27 characters) always fits. It follows ISO/IEC 18004 as Project Nayuki's QR Code generator (MIT)
  implements it; the code is our own, reduced to the one size. The symbol is made again only when the
  address text changes.
- **The paint.** `pod_qr_code` (132 px) is painted in its `EVT_AFTER_PAINT`: `#E5E5EA` paper, black
  modules of 4 px with a 4-module border, corners of radius 12 in the page's colour (`m1_corners`).
  The paper and the modules are raw canvas colours, not `ui_ink`, so Light Mode keeps a dark-on-light
  code. Near white rather than `#FFFFFF`: the code shows only on demand and is softer on the black page.
- **No address** (Wi-Fi gone while the page is open): the hero, and the pill hidden. A refused paint
  or click bind also leaves the pill hidden.

Stock shipped a Chinese GCDWebUploader port (jQuery, Bootstrap, five cgic CGIs) with shell-injection and
JSON-escaping faults (a built-in extension whitelist in `list.cgi`, `system("rm -rf ...")` after only a
prefix check, uploads buffered whole on the card); the build removes all of it and `api.cgi` replaces it.

## The page

`assets/webapp/index.html` (about 68 KB, installed by `mod_webapp` as `usr/share/web/index.html`): HTML, CSS and
JS in one file, no libraries, no external requests, no fonts. Title "M1 Plus", subtitle "Wi-Fi Transfer".
Light or dark by `prefers-color-scheme` unless the user picked one; black/white/grey. List view only (no thumbnails or previews: the
player's CPU serves every byte).

- Folder path in the URL hash (`#/Music/Album`), so Back/Forward work; breadcrumbs (root included) are links.
  Listings come from `list`, sorted in the page by name/date/size (folders first); a filter box narrows the
  current folder. Storage bar from `df`, refreshed after uploads and deletes.
- Tap a folder: opens it. Tap a file: selects it only. Double-click a file, the "..." menu and the selection bar
  download. With a selection, the selection bar replaces the crumbs and tools row (phones: only the tools row)
  at fixed heights, so nothing shifts. Esc clears, Cmd/Ctrl+A selects all, Delete deletes, "/" focuses the filter.
  Dragging rows onto a folder or crumb moves them.
- One file downloads with `op=download` (a link); a folder or several items with `op=tar`, a hidden form POST
  into a hidden iframe (paths in the body; a refusal shows as a toast).
- New Folder, Rename, Move (a folder-tree picker that lists one level at a time, starting with the root and the
  chain to the current folder) and Delete confirm dialogs. Move/delete/tar send their paths in a POST body.
  Every mutating request is a POST with `Content-Type: application/octet-stream`.
- Upload: Upload Files, Upload Folder or drop anywhere (folders keep their tree: each parent is created with
  `mkdir`, parents first, once per batch; dot files such as `.DS_Store` and `._*` are skipped). One file at a
  time, one XHR each: a file below 2 GiB is a single request, from 2 GiB on 1 GiB chunks (`offset`, `last`). The
  free space is checked against `df` before queueing. A name clash (409 with `conflict=fail`) asks Replace / Skip
  / Keep Both with "Apply to all remaining" (Escape or a click outside counts as Skip, so the queue goes on), then resends with `replace` or `keep`. The queue panel shows overall
  progress, size left and ETA (measured upload rate), per-file progress, cancel (aborts the request; the server
  deletes the `.part`) and retry. A cancelled or failed chunked upload leaves its hidden `.part` (nothing can
  delete it unless Show Hidden Files is on; the next upload of the name truncates it). Empty folders in a dropped tree are not
  created. The listing refreshes at most every 5 s while uploading and at the end.
- Names with exFAT-illegal characters are refused in the dialogs and in the queue before anything is sent; the
  server's own `{"error"}` text shows in a toast otherwise.
- Show Hidden Files (header eye button, `localStorage` `wt-hidden`, default off): every request then carries `hidden=1`; dot names are listed dimmed, and turning it off inside a dot folder goes up to the first visible parent. `.m1plus` and everything below it is read-only: New Folder, Upload, Rename, Move, Delete and dropping files are disabled there (the move picker leaves it out).
- Header controls (top right): a language `<select>` (Auto + the 13 native names, `localStorage` `wt-lang`; a change
  re-renders labels, crumbs, listing, space and the queue panel without a reload; an open dialog keeps its
  language until closed) and a theme button cycling Auto, Light, Dark (`wt-theme`). A script in `<head>` sets
  `data-theme` on `<html>` before first paint; the dark variables apply for `:root[data-theme=dark]` and, in
  Auto (no attribute), under the `prefers-color-scheme` query; `color-scheme` follows. Phones show both as icons.
  Storage access is wrapped in try/catch (private mode keeps the choice for the page's life only).
- Strings: the browser language (`navigator.languages`), English fallback; the mod's 13 languages (codes `en zh
  zh-HK ja ko fr de es it th pl ru uk`, Traditional Chinese for `zh-HK/TW/MO/Hant`). The table is the `STR` JSON
  object in the page (generated once from a Python table; nine words reuse `tools/pod_i18n.py` translations).

## Build and packaging

`tools/mod_webapp.py` (step `mod_webapp` in `tools/build.py`, after `mod_cacerts`):

- removes all 23 stock files below `usr/share/web` except `favicon.ico` (each pinned by SHA-256), the five
  symlinks (pinned by target) and the `css`, `js`, `fonts` directories; `removed_rels()` is the build's
  `--allow-removed` list (`pack_args`), `added_rels()` the `--allow-added` one;
- replaces `index.html` (pinned stock hash) with `assets/webapp/index.html`;
- builds `patch/webapi.c` and installs it as `usr/share/web/cgi-bin/api.cgi`, mode 755, stock mtime.

`tools/buildcache.py` records the directories a step removes (the stock `css`, `js`, `fonts`) with its removed
files and replays them, so a cached build has the same tree as a fresh one.

### The executable

`api.cgi` is a static, libc-free MIPS32r2 o32 executable (about 24 KB): `clang --target=mipsel-linux-gnu
-march=mips32r2 -mabi=32 -msoft-float -mnan=2008 -mno-abicalls -fno-pic -G0 -ffreestanding -fno-builtin -Os`,
`ld.lld -m elf32ltsmip -static -nostdlib -e __start --gc-sections -s`, then `llvm-objcopy` drops `.pdr`,
`.mdebug.abi32`, `.comment`. Its own `__start` and a `rawsys` stub issue the Linux system calls (o32 numbers
`4000 + n`: open, read, write, close, unlink, rename, mkdir, rmdir, fsync, statfs, getdents64, statx, exit_group),
so it needs no `ld-linux-mipsn8.so.1`, no `libc.so.6` and no headers. `e_flags` are `0x70001401` (stock
binaries: `0x70001405`, which adds only CPIC): mips32r2, o32, NaN 2008 (as stock; the kernel checks the
NaN mode against the CPU), soft-float ABI, no FP64. The same source compiles for the host with `-DWEBAPI_HOST`
(`-DWEBAPI_ROOT="<dir>"` moves the root off `/mnt/mmc`): libc replaces the raw calls behind the same `os_*` layer.
Errors are mapped to portable codes; MIPS errno numbers differ (`ENOTEMPTY` 93, `ENAMETOOLONG` 78).

Types and layouts assumed on the device: `struct statx` (arch independent, 256 bytes; kernel 5.10),
`linux_dirent64`, and o32 `struct statfs` (eight 32-bit words: type, bsize, frsize, blocks, bfree, files, ffree,
bavail). `df` rejects an implausible statfs answer (block size outside 512..16 MiB, free above total) with a 500.
Files open with `O_LARGEFILE` (a 32-bit task otherwise gets `EOVERFLOW` above 2 GiB).

## API contract

`/cgi-bin/api.cgi?op=<op>&...`. Parameters come from the query string and, for POSTs other than `upload`, from
a `application/x-www-form-urlencoded`-formatted body (query first; up to 256 KiB, 4096 parameters; a parameter without `=` has an empty value), so a
selection of any size travels in the body. Paths are card paths: `/` is `/mnt/mmc`, `/Music/Album`; repeated
`path` parameters name several items. Every op takes an optional `hidden=1` (query or form body; see Path rules). Read ops accept GET or POST; `mkdir`, `rename`, `move`, `delete`, `upload`
accept POST only (405 otherwise, `Allow` header).

**Mutating requests must send `Content-Type: application/octet-stream`** (403 otherwise). A cross-site page
cannot send that type without a CORS preflight, thttpd answers `OPTIONS` with 501, and a plain `<form>` posts
only form types, so another site cannot trigger a delete from the user's browser (the server has no login).
The form-encoded body of `move`/`delete` is sent with this type too.

Errors: `Status: <code> <text>` and `{"error":"<message>"}` (`application/json; charset=utf-8`):
400 bad request/name/path/length, 403 hidden name (without `hidden=1`), `.m1plus` read-only, symbolic link, root, wrong content type, 404 missing,
405 method, 409 exists/offset mismatch, 500 card or write failure, 507 card full.

| op | parameters | answer |
|---|---|---|
| `list` | `path` (folder, default `/`) | `{"path":"/Music","entries":[{"name","dir":bool,"size","mtime","items"?}]}`; every file and folder, unsorted; `size` 0 for folders; `mtime` seconds; `items` = entries in a folder, hidden names skipped unless `hidden=1`, capped at 9999, for the first 3000 folders of a listing; symlinks and special files are skipped |
| `df` | none | `{"total":bytes,"free":bytes}` (`free` = available to the user) |
| `download` | `path` (file) | the file: `Content-Length`, `Content-Type: application/octet-stream`, `Content-Disposition: attachment; filename="<ASCII fallback>"; filename*=UTF-8''<percent-encoded>`; no ranges. A folder is 400 |
| `tar` | one or more `path` (files or folders, not `/`), optional `name` | a GNU tar stream (`application/x-tar`, no `Content-Length`): members named from each item's own name (`Album/01.flac`), folders recursed, hidden names (unless `hidden=1`) and non-regular files left out, uid/gid 0, mode 644/755, mtime kept, names over 100 bytes in `././@LongLink` records, sizes from 8 GiB in base-256. Archive name `name`, else the item's name, else `M1 Plus`, plus `.tar`. A file that shrinks while read is zero-filled to its announced size. A dry run (stat/readdir/open only) precedes the first header: a selection with anything below 40 folder levels under an item, a path over 4096 bytes or an unreadable entry is a 400/500 JSON error, never a truncated archive; a read error once streaming has begun ends the response without the end-of-archive blocks |
| `mkdir` | `path` (parent), `name` | `{"name":"<name>"}`; 409 if it exists |
| `rename` | `path` (item), `name` (new name, same folder) | `{"name":...}`; 409 if the target exists (a case-only change is allowed: the card ignores case); the same name is a no-op |
| `move` | `path` (items, repeatable), `to` (folder), `conflict=fail` (default) or `keep` | `{"moved":[{"from","to"}]}` (final names; `keep` picks `name 2.ext`); `fail` answers 409 for any clash before anything moves; items already in `to` are skipped; a folder into itself or below is 400 |
| `delete` | `path` (items, repeatable) | `{"deleted":N}`; recursive, never follows symlinks, every path checked before the first deletion |
| `upload` | `path` (folder), `name`, `conflict=fail` (default) `\|replace\|keep`, optional `offset`, `last` | the raw file as the body (not multipart); `{"name":"<final name>","size":N}` |

**Upload**: `Content-Length` is required. The body streams in 64 KiB reads into `<folder>/.<name>.part`
(created or truncated, a stale one is replaced), is `fsync`ed, then renamed. `fail`: 409 if the name exists
(checked before the body is read; a refusal first swallows up to 4 MiB of the body so a small file's client
still sees the answer); `replace`: rename over a file (409 over a folder); `keep`: first free `name 2.ext`,
`name 3.ext`, ... (split at the last dot). Free space below `Content-Length` is 507 up front. A short body,
client abort or write error deletes the `.part` (a replaced file is untouched until the rename). The page
creates parent folders first with `mkdir`; folder trees are plain sequences of `mkdir` and `upload`.
Chunked form (needed above 2 GiB - 1, thttpd's limit below): `offset=0` starts, each later request sends
`offset=<bytes stored so far>` (409 if the `.part` size differs) and the last adds `last=1`; non-final answers are
`{"size":N}`, the final one the name. Conflict policy is applied at the first chunk (`fail`) and again at the end.

### Path rules

Every path is walked component by component below `/mnt/mmc`: `.` or `..` is 400, any component starting with
`.` is 403 (macOS `._` files, `/.m1plus`, upload `.part` files) unless the request has `hidden=1`, which makes list, item counts, tar, download, delete, move and rename (as the source) accept and include dot names; a symbolic link anywhere is 403 (stricter than
`realpath` and equivalent on the card's FAT/exFAT, which has none), `%00` is 400. The card root is refused for
`delete`, `rename`, `move` and `tar`. Names the API creates: one component, 1..240 bytes, no control characters,
`/` or leading dot (400, also with `hidden=1`: mkdir, upload and rename targets never start with a dot). `/.m1plus` (any case, the player's data folder) and everything below it is read-only even with `hidden=1`: `mkdir`, `upload`, `rename`, `move` (source or destination) and `delete` answer 403 ".m1plus is read-only"; list, download and tar work. `mkdir`, `rename` and `upload` also refuse, with 400 and a message, what exFAT rejects
or strips: `" * : < > ? \ |` and a trailing dot or space; the check runs before any upload body is read. Nothing calls a shell: `system`, `popen`, `exec` and libc do not exist in the binary.
`rename(2)` replaces files silently, so `rename` and `move` look first (check-then-rename; one user, no lock).
exFAT keeps the old case when a rename only changes case (`Small.bin` to `small.bin` answered 200 and changed
nothing), so `rename` of a case-only change goes through a hidden temporary name (`.rename0.tmp`, the next digit
if taken) in the same folder and renames it back to the old name if the second step fails. `move` keeps the
file's name, so it has no case-only case.

## thttpd limits the design works around

Read statically from `usr/bin/thttpd` 2.29; never executed.

- Only `GET`, `HEAD` and `POST` exist; `PUT` and `OPTIONS` are 501. Hence POST uploads.
- Request line plus headers must fit 5000 bytes: keep the query short, put item lists in the POST body.
- A POST body is at most 2^31 - 1 bytes (`Content-Length` is a 32-bit `strtol`). Larger files use the
  chunked upload.
- Bodies and CGI output are streamed in 1 KiB pieces, never buffered. `Status: NNN` sets the code (the
  reason text is thttpd's own). Without `Content-Length` the close ends the body, so a truncated tar shows
  as a missing end block, not an HTTP error.
- There is no CGI time limit, so long uploads and tar downloads are not cut off.
- A CGI runs as root in its own folder.
