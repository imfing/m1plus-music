# Navidrome / Subsonic

The Navidrome row in Extras opens the remote music library (`patch/subsonic.c`). Server URL,
username, and password are entered in separate keyboard prompts. Credentials are saved in
`/mnt/mmc/.m1plus/navidrome.conf` and loaded when the page opens. The
file is plain text on the SD card (created with owner-only permissions where the filesystem
supports them), so protect the card accordingly. Each Subsonic request uses a fresh salted token.
HTTPS verifies the server certificate against `/etc/m1plus-cacert.pem`;
HTTP is unencrypted and should only be used on a trusted network.

Navidrome's built-in labels, prompts, and status messages are shown in English regardless of the
device's selected interface language. Song and artist metadata remains as supplied by the server;
the stock interface language setting still applies to the rest of M1+ Music.

Entering or changing server credentials saves them on the SD card and starts a metadata sync
automatically. The page also has an explicit Sync button for later refreshes. They stay saved
until you enter different credentials. The page has Songs and DSD Downloads sections, a persistent
grid/list toggle, and server-side search. The Songs tab and Extras row use a crisp record mark;
large 136 px record and DSD marks are used when tracks have no cached cover art, while available
cover art is displayed as before. Song rows play when tapped and keep only the Download or Delete
control on the right. The SD index stores regular tracks and DSD tracks
separately; lists scroll continuously and load 64 metadata records at a time. Sync accepts an empty
library and caps the combined index at 100,000 tracks; a larger catalog leaves the previous index in
place and reports the limit. Manual sync asks for confirmation, and reopening a page with a valid
index does not start a full resync. DSD tracks appear under a dedicated DSD badge. Before download,
tapping a DSD row only instructs the user to use its Download control; it never starts a transfer.
After download, tapping the row plays the local file and the right-side control offers confirmed
Delete. DSD is never streamed because the stock player misidentifies it. Regular
tracks can be streamed or downloaded; tapping a row streams or plays the local download, and the
right-side control downloads or deletes it. Downloads use an ID-prefixed name
under `/mnt/mmc/Navidrome`, refuse to overwrite an existing file, use a `.part` file before rename,
have no per-file size or total-time cap, and keep at least 32 MiB free on the card. During a
download, the page shows a percentage or animated progress bar and marks Navidrome busy; other
Navidrome actions wait for the transfer. Interrupted transfers keep a partial file and resume with
HTTP range requests when the server supports them; resumed responses must start at the saved byte
offset and match the declared range length. If the stock 32-bit `lseek` cannot represent a partial
file's size, the transfer restarts from byte zero rather than appending at an unknown offset.
Downloads abort if throughput stays below 512 bytes per second for 45 seconds. After a DSD download
succeeds, the stock folder scanner adds `/mnt/mmc/Navidrome` to the existing SD music library in
the background without rebuilding the rest of the library. If artwork caching is running, a
requested download pauses artwork caching and starts after the current image request stops. Errors
report HTTP status, invalid audio responses, low space and SD write failures. A write failure also
asks the user to check any per-file size limit; resumable transfers retain their partial file.

Streaming requests Subsonic `stream.view` with `format=raw`; this integration does not request
transcoding or process audio. DSF and DFF are withheld from stream queues because the stock player
currently misidentifies these streams; the original files remain available through SD download.
Other playback uses the stock `stSongInfo` queue and `hciplayer` path. While a Navidrome track is
playing, a playback-owned timer keeps the stock standby and auto power-off timers awake; it stops
refreshing them while paused and ends when the player stops or changes to a non-Navidrome queue.
Stream queues begin at the
selected track and include up to 64 regular tracks total, reading across index windows without
allocating the entire library at once. Downloaded files play through the stock local-file queue. The
queue ABI was cross-checked against
[shanling-m1plus-navidrome](https://github.com/shivaluma/shanling-m1plus-navidrome) (MIT,
Copyright 2026 shivaluma and contributors). That reference uses a local HTTP proxy; this payload
queues the configured HTTP or HTTPS stream URL directly. Navidrome playback has been tested on a
device and reported working. On the tracks tested, the M1 Plus showed the original sample rate and
bit depth; together with raw streaming and no client-side transcoding, this is consistent with
bit-perfect playback. The display does not prove sample-for-sample identity at the DAC. Seeking and
less common format edge cases have not been independently validated.

## Library views

The synced Navidrome index is also presented as a virtual layer in the stock Songs, Albums, Artists,
Album Artists, Genres, and Composers views. It does not write server-only rows into the stock music
database or change its SD scanner. Opening a view reads the saved index from the SD card; it does not
connect or sync. Songs and category pages scan the index in small UI batches so local rows remain
usable while the server list is collected. If another stock query replaces the local list while a
category is open, the view drops those stale local references and rebuilds from the saved server
index instead of leaving a blank page. Empty and loading messages use wrapped two-line labels.

Library rows merge local SD records with regular Navidrome tracks. A server track is suppressed when
title, artist, and album match a local record and track/disc or duration also supports the match.
This prefers a local copy and leaves uncertain matches as separate rows. A matching local copy is
also kept in a filtered category when its SD metadata omits or disagrees on that category's genre,
composer, or album-artist value. The Navidrome page continues to list the full server catalog
regardless of local copies. Local or downloaded rows have no Navidrome marker; tracks that will
stream from the server show a small green dot at the end of the title row. Covers remain album art.
A downloaded item can play from its SD path before the stock scanner has refreshed; after the
scanner sees it, the local record takes precedence.

Un-downloaded DSF/DFF tracks are excluded from all virtual library views and queues. After a DSD
download, the existing background SD scan makes the local file available; it then appears as a local
item. Regular server tracks stream through the same `format=raw` route or play from their download
path. Tapping a track queues the remaining entries in the current view order, including local SD
paths and raw server URLs; the mixed queue is capped at 4,096 entries. Shuffle starts from a random
position. The Navidrome page keeps its own server listing and playback behavior.

Navidrome album art is read from the existing artwork cache. The UI does not create another artwork
cache or duplicate artwork files. Album Artist, Composer, and Genre rows use metadata returned by
the server; tracks lacking those fields cannot appear in that category. Synced metadata is a
snapshot: use the Navidrome Sync action to refresh it. The index schema changed to `SBIDX3`; an
older index is ignored until a new sync completes. This mixed library queue has its own 4,096-entry
cap; the Navidrome page's stream queue keeps its existing 64-track cap.

The metadata sync uses Subsonic `search3` with an empty query and paged offsets (Navidrome's
supported fast-sync path, also used by offline-first clients such as
[Symfonium](https://docs.symfonium.app/wiki/providers/subsonic-opensubsonic-media-provider-configuration/)).
If an empty-query response is unreadable, sync retries without the query and then with Navidrome's
trailing-wildcard empty-query form. Long display metadata is truncated safely instead of aborting a
whole page. Library indexing keeps a 2 MiB free-space reserve and checks each page's actual metadata
size;
artwork caching has its separate 34 MiB reserve. A failed or short-on-space sync removes its
temporary files and leaves the previous index in place. It writes a temporary index before
replacing the prior one. After the index is available, artwork
fetching runs in the background with visible progress, JPEG and PNG signature checks, a shorter
per-image timeout, a 24-entry recent-failure dedupe, a 2 MiB per-image cap and a 34 MiB free-space
reserve. Starting Navidrome playback pauses this worker and aborts its current image fetch; artwork
caching resumes after playback stops once the Navidrome page is open and connected. A download
request can also pause this worker between image requests or abort the current fetch. The list
remains scrollable and playable during artwork caching; missing/failed artwork does not invalidate
the music index. Navidrome's list and Now Playing load the same cached image file; the player does
not make a second artwork copy. Rendering loads full-size cached covers only for the active list or
grid layout. A
server check requires Wi-Fi; transport failures clear the green status indicator.

The feature changes only the app payload and UI assets. It does not patch startup, bootloader or
recovery code. The generated update remains limited to the repo's existing kernel/rootfs update
path.
