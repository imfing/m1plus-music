# Navidrome / Subsonic

The Navidrome row in Extras opens the remote music library (`patch/subsonic.c`). Server URL,
username, and password are entered in separate keyboard prompts. Credentials are saved in
`/mnt/mmc/.m1plus/navidrome.conf` and loaded when the page opens. The
file is plain text on the SD card (created with owner-only permissions where the filesystem
supports them), so protect the card accordingly. Each Subsonic request uses a fresh salted token.
HTTPS verifies the server certificate against `/etc/m1plus-cacert.pem`;
HTTP is unencrypted and should only be used on a trusted network.

Entering or changing server credentials saves them on the SD card and starts a metadata sync
automatically. The page also has an explicit Sync button for later refreshes. They stay saved
until you enter different credentials. The page has Songs and DSD Downloads sections, a persistent
grid/list toggle, and server-side search. The SD index stores regular tracks and DSD tracks
separately; lists scroll continuously and load 64 metadata records at a time. Sync accepts an empty
library and caps the combined index at 20,000 tracks; a larger catalog leaves the previous index in
place and reports the limit. Manual sync asks for confirmation, and reopening a page with a valid
index does not start a full resync. DSD tracks appear under a dedicated DSD badge. Before download
they offer Download; afterward they offer local Play and confirmed Delete actions. DSD is never
streamed because the stock player misidentifies it. Regular tracks can be streamed or downloaded;
downloaded tracks show local Play and confirmed Delete actions. Downloads use an ID-prefixed name
under `/mnt/mmc/Navidrome`, refuse to overwrite an existing file, use a `.part` file before rename,
have no per-file size or total-time cap, and keep at least 32 MiB free on the card. A transfer
aborts if throughput stays below 512 bytes per second for 45 seconds. After a DSD download
succeeds, the stock folder scanner adds `/mnt/mmc/Navidrome` to the existing SD music library in
the background without rebuilding the rest of the library. If artwork caching is still running,
the page explains that the DSD download must be retried after caching finishes.

Streaming requests Subsonic `stream.view` with `format=raw`; this integration does not request
transcoding or process audio. DSF and DFF are withheld from stream queues because the stock player
currently misidentifies these streams; the original files remain available through SD download.
Other playback uses the stock `stSongInfo` queue and `hciplayer` path. Stream queues begin at the
selected track and include up to 64 regular tracks total, reading across index windows without
allocating the entire library at once. Downloaded files play through the stock local-file queue. The
queue ABI was cross-checked against
[shanling-m1plus-navidrome](https://github.com/shivaluma/shanling-m1plus-navidrome) (MIT,
Copyright 2026 shivaluma and contributors). That reference uses a local HTTP proxy; this payload
queues the configured HTTP or HTTPS stream URL directly. Hardware playback, seeking, format
compatibility and audible bit-perfect output still need device validation.

The metadata sync uses Subsonic `search3` with an empty query and paged offsets (Navidrome's
supported fast-sync path, also used by offline-first clients such as
[Symfonium](https://docs.symfonium.app/wiki/providers/subsonic-opensubsonic-media-provider-configuration/)).
It writes a temporary index before replacing the prior one. After the index is available, artwork
fetching runs in the background with visible progress, a shorter per-image timeout, a 24-entry
recent-failure dedupe, a 2 MiB per-image cap and a 34 MiB free-space reserve. The list remains
scrollable and playable during artwork caching; missing/failed artwork does not invalidate the music
index. Rendering loads full-size cached covers only for the active list or grid layout. A server
check requires Wi-Fi; transport failures clear the green status indicator.

The feature changes only the app payload and UI assets. It does not patch startup, bootloader or
recovery code. The generated update remains limited to the repo's existing kernel/rootfs update
path.
