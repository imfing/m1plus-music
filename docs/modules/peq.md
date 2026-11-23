# Parametric EQ

**Sources:** `patch/peq.c` / `peq.h` (engine, parser, record), `patch/peq_player.c` (hciplayer
filter), `patch/peq_ui.c` (Equalizer page), `patch/peqlib.c` (Presets page), `patch/peqpage.c`
(Preset page), `patch/peqband.c` (band page), `patch/autoeq.c` and `AutoEq` in `patch/pcnet.c`
(download), `patch/tenband.c` (10-Band editor), `patch/peqout.c` (per-output EQ);
`tools/mod_player.py` (hciplayer patch), `tools/peq_graph.py` and `tools/tenband_model.py`
(page models), `build_peq_page` / `build_peqpage_page` in `tools/pod_ui.py`.
User instructions: [equalizer guide](../equalizer-guide.md).

A parametric EQ that runs inside hciplayer as an audio filter, with APO / AutoEq presets from the
card, a 10-Band editor, and a separate setting per output. Based on Diamond Bond's open-source Q2
parametric EQ (MIT): the preset layout, APO parser, RBJ designs, Auto preamp, ramped engine, DSD
pass-through and reload on stock's gain command are its. The carried filter memory is ours.

Stock's slider page (All Playback Settings > Equalizer) opens our Equalizer page instead: its one
caller, the list's click handler, is redirected by a pinned two-word edit (`EQ_PINS` in
`tools/pod.py`); the stock page stays in the image, unreachable. Stock's ten gains are not used.

## Engine

The filter runs in hciplayer at every sample rate (stock's skipped anything above 48 kHz) and on
every output, since it sits before ALSA. **DSD passes untouched**; the Equalizer page and 10-Band
editor end with the note "EQ is not applied to DSD."

- **A filter, not a rewrite:** `peq_open` replaces stock's equalizer filter. A change to the
  playback loop's insert gate and the rate gate of `mcl-seteq` lets it run at any rate.
  `tools/mod_player.py` pins the binary, its words and the facts the C reads.
  The payload is `peq.c` + `stereo.c` + `peq_player.c`, linked into a spare segment, with no
  `.bss`; per-instance state is heap.
- **EQ off keeps the filter.** With stock's switch off the filter stays in the chain and passes
  the native format and every block through, so playback is stock's, bit for bit (unless Mono
  Audio or Crossfeed is on, [stereo](stereo.md)). The engine ramps in and out of bypass in 20 ms,
  so a mid-track switch is smooth. Switching EQ on, or a stereo option on with EQ off, while the
  filter passes the native format would leave it unable to work until the next file, so only then
  the filter is removed once and the loop adds a new instance.
- **Rate and format:** a DSD codec, a rate outside 8-384 kHz or a special format is accepted as it
  comes and played untouched. Otherwise the curve is compiled for the rate and channel count and
  the chain asks for float.
- **Reload:** stock's gain command (channel 0) makes the filter read the curve again. A different
  one crossfades over 20 ms. Control runs on the playback loop, never in the PCM callback.
- **Kill switch:** with `/mnt/mmc/m1plus-off` present the filter passes everything through.
- **Carried filter memory (gapless join).** hciplayer rebuilds the filter chain for every file,
  so the old instance is gone before the new one opens. An instance that is going away at a
  natural end of file copies its filter state, with the preset, rate, channel count and time. The
  next instance adopts it once on its first block if the rate, channels and whole preset match
  and the join is under 3 s old. A skip, stop, pause, rate change, different preset, DSD,
  bypass or the kill switch starts from zero memory and clears the carry. The demuxer's EOF flag
  tells a natural end from a skip.
- **Engine:** up to 64 bands (`PEQ_BANDS`), each on both channels or one side; RBJ peak and
  shelves in double; preamp after the cascade; balance turns one side down. **Auto preamp** (a file
  without `Preamp:`) is minus the largest response of either side at the rate playing, never a
  boost, at most 60 dB. A band at or past Nyquist is skipped at that rate. Denormals are flushed,
  non-finite input becomes 0, and samples above 1.0 are kept for stock's volume, bounded at +-1000 (+60 dBFS, `PEQ_OUT_MAX`) so
  a stack of large boosts never reaches infinity.

### The record

`/mnt/data/m1plus/playback-eq` (`M1PEQ03\0`, 2248 bytes) holds the mode (10-Band or preset file),
the preset file name, and the 10-Band fields: `curve` (0..9), `preamp` (Auto, or 0..12 dB down),
`gain[10]` (what plays) and `custom[10]`. Written whole by demo (temp file, fsync, rename), read by
both binaries. A missing or invalid record (bad magic, size, mode, range or non-finite gain) plays
Flat with Auto preamp; an older record version is not read. The 10-Band mode plays `gain[]` as ten
RBJ peaking bands at 31 Hz - 16 kHz, Q 1.41, plus the preamp. Stock's `equalizer_flag` stays the
on/off switch.

### The parser (`patch/peq.c`)

APO / AutoEq text, at most 16384 bytes with lines of 512: `Preamp:`, `Channel: L|R|all`, `Filter:
ON|OFF PK|PEQ|LS|LSC|HS|HSC Fc .. Gain .. [Q ..]`, comments, a BOM, CRLF, a decimal comma. OFF
filters are skipped. LS and HS without Q use slope 0.9, and with Q the corner moves to the centre
(Equalizer APO's rules). Ranges: 20-20000 Hz, +-24 dB, Q 0.1-10, preamp -60..24 dB, 64 bands.

**Lenient:** what the engine has no band for is skipped and counted (`peq_error.skipped`), not
refused: other commands (`Device:`, `Include:`, `GraphicEQ:` ...), ON filters of another type
(`LP`, `HP`, `BP`, `NO`, `AP` ...), and a `Channel:` that names a channel other than L, R, all (its
filters are skipped until the next `Channel:`, never applied to the wrong side). **Still
refused:** a malformed number on a supported line, a value out of range on an ON filter, over 64
bands, an oversized file, and a file with no usable ON band. The parser is demo's only: the player
reads the parsed record.

## Presets

### Presets page (`patch/peqlib.c`)

Opened from the Equalizer page's Presets row. A cards page with:

- **Download from AutoEq** (own card, below).
- **AutoEq** section: files whose first line is `# AutoEq: <path>` or `# AutoEq edited: <path>`,
  each a two-line row (name, `Source · Kind`, the source shown percent-decoded) with a chevron. Both
  section headers are hidden while empty.
- **On Card** section: every other `.txt` in `/mnt/mmc/EQ`, grey line "On card".

A tap opens the Preset page. The card is read again when the page comes back to the front. At most
64 files are listed (`PQ_ROWS`, one constant mirrored in `tools/pod_pages.py`; every row is a
widget baked into the asset, so the cap costs asset size). The Equalizer's Presets count is every
`.txt` on the card, so it can be larger.

### AutoEq download (`patch/autoeq.c`)

Data is [AutoEq](https://github.com/jaakkopasanen/AutoEq) (MIT, Jaakko Pasanen): `results/INDEX.md`
from `raw.githubusercontent.com` (about 0.85 MB, 22 sources), and a result's
`<Name> ParametricEQ.txt` (about 500 bytes). There is **no source filter**: results show every
source, and the grey line says which. The request layer and job slot are in
[network](network.md); `PN_KIND_EQ` uses the one job slot.

- **Page:** its own window `m1plus_autoeq`, built like Radio's search level: Back, the title
  "AutoEq", Now Playing's disc, a search field, a keyboard, and one list of two-line rows (name,
  `Source · Kind[ · Target]`) with a trailing download arrow, a spinning ring or a white check.
- **The list on the card:** `/mnt/mmc/.m1plus/autoeq/index.md` plus an `updated` stamp. A list that
  is there is used offline and never fetched on a keystroke. A missing one is downloaded when
  the page opens ("Downloading List…"). One older than 30 days, undated or future-dated is
  refreshed in the background (a failure is silent). Only a body that starts with `# Index` and is
  at most 3 MB replaces the list. A failure shows its word with **Try Again**.
- **Rows:** a result shows the ring and "Downloading…" while it fetches, then "Saved to EQ · Tap to
  use"; the grey line's kind is Over-ear, In-ear or Earbud (else the source alone).
- **Search:** the file is scanned again for each query (nothing of the index is held in memory).
  Every word (at most 4) must be a case-insensitive substring of the name, from any source. Results
  rank by exact name, then prefix, then the rest, at most 20.
- **Download:** a tap on an unsaved result fetches the file to a part file (at most 16 KB). The path
  is checked first because the index came off the network. **Only a file that parses** is renamed
  into `/mnt/mmc/EQ`; otherwise "Cannot read this preset" and nothing is kept. Back or Now Playing
  cancels a running job.
- **Names:** the first line of a downloaded file is the comment `# AutoEq: <path>`. A Save over it
  rewrites it as `# AutoEq edited: <path>`, so an edited file is no longer "saved" for that result
  and a tap downloads the original to the next free name. Saved means a file with exactly that
  stamp exists under `<Name>.txt`, `<Name> (<Source>).txt`, `<Name> (<Source> 2).txt` ... up to 9. A
  user's unstamped file is never overwritten, so each source and target gets its own file. Names
  are cleaned for the card and cut under 64 bytes. With all nine taken, a tap says "Storage
  unavailable".
- **Tap to use** on a saved result is the same as a tap on its row on the Equalizer page. A finished
  download is selected at once. The playing row says "In use".

### Preset page (`patch/peqpage.c`)

Opened by a file row. It parses the file first ("Cannot read this preset" if it no longer
parses). The page shows the preset's graph card, a **Preamp** row, a **Bands** header, one two-line
row per band that plays (frequency; type and Q, with L or R for a one-side band; gain at the
right), a note "N lines not supported were skipped." when the parser skipped lines, **Rename
Preset** and **Delete Preset**. The title is the file name without `.txt`.

- **Graph:** one bitmap painted before the view's labels. It plots the left channel's response at
  48 kHz without the preamp and balance, 20 Hz - 20 kHz. The scale is +-12 dB, widening to +-18 and
  +-24 when the curve passes it.
- **Row text:** frequency `N Hz` / `N kHz`; grey line "Peak · Q 1.41", "Low shelf · Q 0.7", "High
  shelf · Q 0.7", with " · L" or " · R" for one side; gain `+4.8 dB`, `−2.4 dB`, `0.0 dB`.
- **Preamp row:** the file's `Preamp:` with its sign, or `Auto · -6.0 dB`, the cut the player makes
  at 48 kHz. It is read-only.
- A filter that parsed but is OFF has no row (the page shows what the engine has).
- **Delete Preset** (red, with the stock confirm "Delete Preset?") unlinks the file and returns to
  the Presets page. If it is the preset that plays,
  the record goes back to the 10-Band EQ and stock's Equalizer is switched off. Failure: "Failed To
  Delete Preset".

### Preset editing (`patch/peqpage.c`, `patch/peqband.c`)

The preset page keeps `work` (the bands that play) and `saved` (what the file parses to); they
differ when the preset is edited. The record carries an unsaved edit: reopening the file that the
record plays starts from the record's preset. Tapping the preset on the Equalizer page parses the
file again and drops unsaved edits.

- **Band page:** a graph with a ring on the band, a Peak / Low shelf / High shelf control, and
  Frequency (log), Gain (+-12 dB, 0.1) and Q (log, 0.01) sliders. Previous / Next band are the
  navbar capsule and wrap. Band edits play at once through the 10-Band editor's path (record saved
  and the gain command sent at most every 150 ms while dragging, and at the release). The first
  edit of a preset that was not playing makes it the preset that plays.
- **Number keypad:** a tap on a row's name or value opens a bottom sheet with a value field and keys
  (minus for Gain, Hz / kHz for Frequency) and a grey "Range ..." line. **Done** applies the number
  clamped to the engine's range (Frequency 20 Hz - 20 kHz, Gain -24 to +24 dB, Q 0.1 - 10; the
  slider itself ends at +-12 dB), saves and plays at once; an empty number changes nothing. **Cancel** or a tap on the dim changes nothing. Name entries use the QWERTY keyboard.
- **Leaving with unsaved edits:** Back and Now Playing on the band page ask through a popup
  "Save Changes?" with the preset's name:
  **Save**, **Save As New…** (name starts as "<name> (Edited)"), **Don't Save** (the file's preset
  plays again), **Cancel**. Exits that do not ask (status bar, pull-down, power key, hardware
  keys) leave the edit in the record, so it plays, and the file untouched. The popup is in the
  band page's asset because the stock confirm has two buttons only.
- **Save:** writes APO text to a temp file, parses it back (a file the parser would refuse is never
  renamed in), then renames over. **Save As** cleans the name, drops a typed `.txt`, refuses
  "Name already in use" and a 65th file ("Preset limit reached"); the new file plays and the
  original is untouched; names are cut at 59 bytes plus `.txt`. A failed record or slot write says "Not saved" and the page stays
  unsaved. **Rename Preset** renames the file, and the record and slots follow.
- **Format written:** the `# AutoEq edited:` stamp only when saving over an AutoEq file; `Preamp:` only
  when the preset has one; centre-form shelves with Q; `Channel:` wherever the side changes (a
  balance is written as the other side's `Channel:` preamp); numbers to 4 decimals, zeros trimmed.
  **Not preserved:** lines the parser skipped (`Device:`, `LP` / `HP`, OFF filters, other
  channels, comments except the stamp), so a Save drops them.

## 10-Band EQ

Our ten-band EQ replaces stock's slider page: ten octave bands (31 Hz - 16 kHz), stock's genre
curves as presets. Stock's own `af_equalizer` is not used. The state is in the record above.

- **Equalizer page:** the picker's first row is **10-Band EQ** with the curve name in grey
  (`Rock`, `Custom`); a tap only picks it. The bottom card holds **Edit 10-Band EQ** (opens the
  editor) and **Presets**.
- **Editor** (title "10-Band EQ"): a **Curve** row, the graph card (preamp left out), a region line,
  a card of **ten vertical sliders** (+-12 dB, 0.5 dB steps, value above each, frequency under it),
  then **Preamp** and **Reset**, and **Save as Preset** under them.
- **Sliders:** a drag anywhere in a column moves that band. While dragging, the value shows in a
  white pill and the region line names the band's region (`Sub bass · rumble`, `Mid bass · punch
  and warmth`, `Lower mids · body and fullness`, `Upper mids · shouty if too much`, `Treble ·
  detail and sparkle`, `Air · openness`). The sound follows in steps of 150 ms, and the record is
  saved when the drag ends. A
  slider move on a built-in curve copies it into **Custom**, silently overwriting the previous one.
  The view takes the window's grab so the page does not scroll under the finger.
- **Curve page:** Flat, Pop, Rock, Dance, Blues, Metal, Vocal, Classical, Jazz, Custom; a tap picks
  and goes back. The genre gains are stock's own table copied into the payload (checked against
  the `demo` binary by `parser_tests`); Flat is zero; Custom is the user's.
- **Preamp page:** **Auto** in a card of its own with the note "Auto reduces the level to help
  prevent distortion from EQ boosts.", then `0 dB`, `-1 dB` ... `-12 dB` (no positive values). Auto's grey value is the cut it makes now
  (`0.0 dB` for a flat curve, else the cut at 48 kHz).
- **Reset:** sets Flat with Auto preamp. On Custom it asks first ("Reset 10-Band EQ?") because it
  erases the user's curve; on a built-in curve it resets at once.
- **Save as Preset:** writes the ten gains and preamp as a new file in `/mnt/mmc/EQ` (ten `PK`
  bands, `Q 1.41`, no AutoEq stamp, name entry as Save As) (`Preamp:` only when not Auto; the name entry starts as the curve's name) and toasts "Saved as
  Preset". The record
  and playback are unchanged.
- **Decision:** any editor edit, Curve pick, Preamp pick or Reset also sets the mode to the 10-Band
  EQ and drops the preset file, because the user could not hear the edit otherwise. If a preset
  was playing, a toast says "Switched to 10-Band EQ" at the release.
- With Preamp Auto the player uses the engine's Auto. Flat with Auto is bit-exact.
- An editor opened while another sits under Now Playing replaces it.

## Per-output EQ (`patch/peqout.c`)

Headphones, Line Out and a USB DAC each keep their own EQ (Off or on, the 10-Band curve, gains
and preamp, or a preset file). It switches by itself when the output changes, also while a track
plays. The Equalizer page names the output it edits in a grey line under the switch card ("For
Headphones", "For Line Out", "For USB DAC"). Bluetooth is not an output of its own: it keeps the
headphone EQ.

- **Design:** the player still reads one record, `playback-eq` (the playing record), unchanged.
  Beside it are per-output slots `playback-eq-headphones`, `-lineout`, `-usb` and
  `playback-eq-output` (the output the playing record belongs to, and each output's setting of
  stock's Equalizer switch). On an output change `peqout_sync` files the playing record in the old
  output's slot, loads the new output's slot (if any) as the playing record, sets the switch to
  what that output had, and writes the owner last. An output with no slot keeps what plays. A
  failure stops before anything changed and is retried at the next call, so one output's curve is
  never attributed to another.
- **First run:** the first sync only records the owner, so the same EQ plays on every output until
  one is edited.
- **Switch rule:** saves, Save As and Revert never switch the Equalizer on by themselves. On an
  output change the switch follows that output's last setting, both ways.
- **Detection:** USB audio is the USB DAC; the built-in DAC with stock's Line Out byte set is Line
  Out; else Headphones (including Bluetooth).
- **Where it runs** (no new hook): the status bar's one-second timer, the start-player and
  save-start paths, and the Equalizer page when it opens or returns. Each has a one-int-compare
  early exit. The kill switch makes it do nothing. It is not on the boot path.
- **Routing:** `peqout.c` alone decides whether a write goes to the playing record or to a slot.
  An edit session remembers its **owner** output; after a change, Save and Don't Save act on the
  owner's slot, never on the output now playing. Rename and Delete Preset rewrite every slot that
  names the file (a deleted file's slots point at the 10-Band EQ with the switch off). Open pages
  reload when the output changes.

## Equalizer page (`patch/peq_ui.c`)

**Settings > Playback > EQ** (its value is Off, the preset that plays, or the 10-Band curve name)
and stock's All Playback Settings > Equalizer open it. It is a [Settings cards](settings.md) page,
neutral white and grey.

- **Card 1:** the Equalizer switch (stock's own handler) and the grey output line.
- **Card 2:** the picker: **10-Band EQ**, then every APO / AutoEq `.txt` in `/mnt/mmc/EQ` sorted by
  name (at most 64). A check marks what plays. With no files, a hint says where they go ("Download headphone presets in Presets, or copy APO .txt files into EQ on the card."). Preset
  rows have no chevron: a tap anywhere selects. Rows are shown and hidden at run time, with the
  card's pieces (top, middle, bottom, single) set to match.
- **Card 3:** **Edit 10-Band EQ** (curve name) and **Presets** (file count).
- The page ends with the DSD note.
- **A tap on a preset** parses it, saves the record, turns stock's Equalizer on if it was off, and
  the new curve plays within a block (a 20 ms ramp). A failed save says "Not saved" and keeps the
  old record and mark. An unparsable file shows "Cannot read this preset" and changes nothing.
- Back in front re-reads the folder, the record and the switch. No hook, no timer.
- **Settings Files** (Developer > Tools) lists the record `playback-eq` only; Reset All Settings
  removes the per-output files with the rest of the folder.

## Limits

- One preset file cap of 64 in the lists; 64 bands per preset.
- Preamp on the preset page is read-only.
- No band add or remove; a Save drops lines the parser skipped.
- The preset page shows a stale record as edited if the file changed on a computer; not handled.
- No per-device USB profile.
