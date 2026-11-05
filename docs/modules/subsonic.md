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
separately; lists scroll continuously and load metadata in windows. DSD tracks appear in their
own section and offer original-file downloads only, since the stock player misidentifies streamed
DSD. Other tracks can be streamed or downloaded.
That saves the original file under `/mnt/mmc/Navidrome`; downloads refuse to overwrite an existing
file, use a `.part` file before rename, cap a file at 512 MiB, and keep at least 32 MiB free on the
card. Run Shanling's normal Update Library scan to add downloaded audio files to its local library.

Streaming requests Subsonic `stream.view` with `format=raw`; this integration does not request
transcoding or process audio. DSF and DFF are withheld from stream queues because the stock player
currently misidentifies these streams; the original files remain available through SD download.
Other playback uses the stock `stSongInfo` queue and `hciplayer` path,
with the queue ABI cross-checked against
[shanling-m1plus-navidrome](https://github.com/shivaluma/shanling-m1plus-navidrome) (MIT,
Copyright 2026 shivaluma and contributors). The reference uses a local HTTP proxy; this payload
queues the configured HTTP or HTTPS stream URL directly. Hardware playback, seeking, format
compatibility and audible bit-perfect output still need device validation.

The metadata sync uses Subsonic `search3` with an empty query and paged offsets (Navidrome's
supported fast-sync path, also used by offline-first clients such as
[Symfonium](https://docs.symfonium.app/wiki/providers/subsonic-opensubsonic-media-provider-configuration/)).
It caps the index at 20,000 tracks and writes a temporary index before replacing the prior one.
It also fetches available `coverArt` images to a hidden SD cache, with a 2 MiB per-image cap and
a 34 MiB free-space reserve. Stream queue entries link cached art to Now Playing and the mini
player; missing/failed artwork does not invalidate the music index. A server check requires Wi-Fi
and displays green status after a successful authenticated ping.

The feature changes only the app payload and UI assets. It does not patch startup, bootloader or
recovery code. The generated update remains limited to the repo's existing kernel/rootfs update
path.
