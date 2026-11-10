# Get Info (`patch/songinfo.c`, `patch/songinfo.h`, `test/pod/songinfo.py`)

A track's details page, opened by the Get Info row of the track rows' "..." sheet ([rowmenu](rowmenu.md)). Device: the compact layout was checked on V2.1zAZYTAAAB (look and open); the readers per format are emulated only.

**Source:** `songinfo_open(rec)` copies the title (the file name when empty), artist, album, path and CUE start/end of the row's `stSongInfo`, so the caller may destroy the record at once. The page
`m1plus_songinfo` (`tools/pod_ui.py build_songinfo_page`, `pod_pages.SONGINFO`, last in the page table) is Station Info's structure ([radio](radio.md), `patch/radioinfo.c`): the stock navbar (Back, Now Playing,
title "Get Info") over a stock list holding one content view painted in its `EVT_AFTER_PAINT`, texts wrapped once by `pd_lines`, the navbar fade shown while scrolled. Four hidden labels carry the text styles
(`label_head` 22 px white, `label_sub` 16 px `#8E8E93`, `label_key` 14 px `#8E8E93`, `label_val` 18 px white). No timer, nothing written; the memory goes with the window. Returns -1
with no record, no window, an asset without the widgets or no memory; a second open while the page is on top opens nothing.

## Content
- **Header:** the cover, 96 px at (16, 16) with 8 px corners (one `grid_t` tile: the Cover Flow cache file of the track's own album key, else the file of the library's album record of that name (`cc_album_rep_key`: a collab "A; B" has no file under its own artist, the cache is named after the row getAllAlbum lists for the album. ONE targeted query at open, none when the own file exists or the track has no album tag: getAllAlbum's own statement and album row callback `0x4e93c8` through `toolsQueryDbTable` with the name as a filter, `select id,album,songer,fileurl from songtable where album='<name>' COLLATE NOCASE group by album COLLATE NOCASE` (quotes doubled; over 250 bytes asks nothing). The Library filter (`pq_filter`) rewrites it as every album list (the condition joins its WHERE, the one `min()` of its HAVING gives the album's first track and so the bare columns `id`, `songer`, `fileurl`), so the record is the one the full list has for that name whatever order SQLite scans the rows in; `test/pod/scan.py` runs both statements on SQLite over tracks under several songers in two insertion orders. The stock database has no index (no CREATE INDEX string in the demo). No album list is loaded, `*pdeq_showlist` untouched, the record cleared at once), else the placeholder disc; no cache job is started), the title (at most two lines), artist and
  album (one line each, left out when empty) at x 124, 180 px wide, centred on the cover's height.
- **Pairs** (x 16, 288 px, a label over its value on 18 + 22 px pitches, 10 px between pairs and 16 px under the cover so Format to Size fit above the fold with Path's label peeking, a pair with no value left out), in order: **Format** (the file extension upper-cased), **Sample Rate / Bit Depth** (`44.1 kHz / 16-bit`; just **Sample Rate** when the depth
  is unknown), **Bitrate** (`N kbps`), **Duration** (`m:ss`, `h:mm:ss`), **Size** (decimal units: `845 KB`, `36.4 MB`, `1.23 GB`), **Path** (wrapped in full). Action rows (Go to Album, Go to Artist, Delete) can follow the last pair: the
  content ends at `gi.h`.
- **Sources:** one read of the file's first 2 KB (a second after an ID3v2 tag, skipped by its synchsafe size) parsed as FLAC STREAMINFO (rate, bits, total samples), a WAV `fmt ` chunk, an Ogg Vorbis identification header
  (rate) or, for an MPEG extension only (MP3, MP2, MP1, MPA, MPGA), the first MPEG audio frame header whose next frame, when inside the bytes read, has a matching header (rate); the size by `cc_file_size`; the duration from, in order, a CUE track's own end - start, the durations table ([album page](album-page.md)), FLAC's total, else TagLib's length of this one
  file (`dur_probe`, one open on the UI thread; not stored). A CUE track's duration is its own, less the start for the last track.
- **Bitrate** is the file's average (bytes over seconds, including tags and art), not a stream value; hidden for a CUE track. **Not readable:** sample rate and depth of M4A/AAC/ALAC, Opus, APE, DSD, WMA and other
  formats (their rows are hidden, the rest shows); bit depth of every lossy format. A missing file shows Format and Path only.

## A Navidrome track (ND-14)

`songinfo_open` asks `sbs_track(rec)` first: a record that is a Navidrome track (`nd://`) is not a file, so the page takes its facts from the source's row (the record's own data completed from the album's cache file): Format (the suffix, upper
case), Sample Rate / Bit Depth (what the server sent; from the file's first bytes when the track is downloaded and the server left them out), Bitrate (the server's own figure), Duration, Size (the server's, else the file's) and
**Path only for a downloaded track** (the local file; the server's own path is not kept in the cache). The cover is the cached Navidrome picture (`sba_cover_have`, loaded with `grid_art_url`), else the placeholder; nothing is requested.
No file is read for an undownloaded track and TagLib is never used. Tests: `songinfo/remote_tests`.

## Tests and preview
`test/pod/songinfo.py`: the asset and the page table, the 13 translations and the longest label (French, 280 of 288 px); FLAC (44.1/16, 96/24, 176.4/24 over an hour and a GB, 22.05/8), WAV, Ogg, MP3 with
no tag and after tags of 300, 5000 and 70000 bytes, a sync with no next frame skipped, an unreadable header, an M4A holding MPEG-like bytes (no rate), a missing file, no or a folder-only extension, no title, CUE tracks, long path and title; geometry, scroll and the fade; no record, second
open, window and asset failures, destroy (bitmaps and tables freed), a replaced page. Preview: `uv run python -I tools/preview_songinfo.py work/mod-release out/preview/songinfo.png`.

**Handover:** to add the action rows, append blocks after `Path` in `gi_build` and give them hit tests in a touch handler on `gi_view`; nothing there takes touches yet.
