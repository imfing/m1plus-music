# Crossfade

**Sources:** `patch/xfade.h`, `patch/xfade.c`, `patch/xfsrc.h`, `patch/xfsrc.c`, `patch/xfadeset.c`,
`patch/peq_player.c`, `patch/nowplaying.c` (`np_resampled`), `patch/m1plus.c`, `patch/radio.c`, `patch/shuffle.c`, `patch/home.c`, `patch/setfiles.c`,
`tools/mod_player.py`, `tools/pod_pages.py` (`PLAYSET_PAGE`, `PSXFADE_PAGE`, `XfadeCard`), `tools/pod_ui.py`
(`cards_xfade`), `tools/mod_icons.py` (`xf_dots`), `tools/pod_pins.py` (`XFADE_PINS`).

True overlapping crossfade between consecutive tracks using `hciplayer`'s second `MPContext`
(`next_mpctx`, `0xaf9b90`) populated by stock `PreInitNextSong`. Track B is decoded in lockstep
with Track A during the final `D` seconds and mixed with an equal-power curve before Mono Audio,
Parametric EQ, Crossfeed and the VU level tap. When Crossfade is off or outside the transition
window, samples pass bit-exact untouched.

## Behaviour

Settings > Playback Settings > **Crossfade** (`m1plus_psxfade`) is an iOS-style page: a
**Crossfade** switch (default **Off**, `ACT_XFADESET`), and while it is on a **Crossfade Duration**
card (a slider, 1 to 12 s in 1 s steps, default **5 s**; the text over it follows the slider live:
"5 seconds", "1 second"), a **Keep Albums Gapless** switch (default **On**) and two notes (what
Keep Albums Gapless does; that the sample rate stays the same from track to track). While the
switch is off only its card shows: the header, duration card, Keep Albums Gapless row and notes are
hidden and insensitive (`xfade_show`, `patch/xfadeset.c`), and the page closes up. The duration card
(`XfadeCard`, 96 px and a 20 px gap) uses the Display brightness slider's look (`slider_look`, 6 px
track, `pod_sl_thumb`), "1 s" and "12 s" at its ends and twelve grey dots under the track, one per
second (the baked image `pod_xf_dots`). The slider saves each new value at once; its duration is
kept while the switch is off. The Playback hub's Crossfade row shows **Off** or **N s**.

- **Keep Albums Gapless (On):** consecutive tracks sharing the same non-empty album tag stay
  gapless (`seconds = 0`); album changes, playlists, shuffle and mixed folders crossfade.
- **Keep Albums Gapless (Off):** every eligible track transition crossfades.
- **Exclusions:** DSD (`.dsf`, `.dff`, `.iso`, `dsdiff`, `ffdsd*`), pass-through codecs
  (`hwac3`, `hwmpa`, `spdif`), MQA (`MQA_MODE == 2`), CUE sheet tracks, Podcasts
  (`/mnt/mmc/Podcasts/`), Audiobooks (`/mnt/mmc/Audiobooks/`), HTTP/HTTPS streams (the three
  prefixes in any ASCII case), Repeat Track,
  tracks shorter than 10 s, and `/mnt/mmc/m1plus-off` (kill switch).
- **Duration clamp:** on short tracks, `demo` clamps the duration to `(total - 4) / 2` seconds
  and `hciplayer` applies the same `(duration - 4) / 2` clamp against both Track A and Track B
  (via `demuxer_get_time_length` on `next_mpctx->demuxer`) so fade-in and fade-out never collide
  and short next tracks (< 10 s) stay gapless.

## Dual-decoder engine (`patch/xfade.c`)

Stock `hciplayer`'s `PreInitNextSong` (`0x42b834`) opens the next file's stream, demuxer,
`d_audio` and `sh_audio` into `next_mpctx` (`0xaf9b90`) and sets `NEXT_STATE` (`0xb10dd0`) to `2`.
Stock `ad_ffmpeg` allocates a separate `AVCodecContext` in each `sh_audio->context` (`+0x28`).
Its decode path also checks global player exit flags; independent codec contexts alone do not
establish that concurrent preloaded demuxing works for every format.

- **FLAC seek isolation:** the vendor FLAC decoder reads a global seek threshold at `0xb15290`,
  set by `demux_audio` seek and cleared when that demuxer closes. Crossfade saves this threshold,
  sets it to zero while initializing or decoding Track B, and restores it before returning to
  Track A, including on initialization failure or decode error. B starts at the beginning of its
  file and must not inherit A's seek position.

- **Stage placement:** `xfade_process_float()` / `xfade_process_native()` run at the top of
  `play()` in `patch/peq_player.c`, before Mono Audio, PEQ, Crossfeed and the VU tap. Because
  `peq_player.c` stays in the filter chain even with EQ off (`pass_native`), Crossfade works with
  EQ, Mono and Crossfeed all off (in `S16`, `S24`, `S32` or `U8` native PCM) as well as in the
  float32 chain.
- **Idle cost:** while `NEXT_STATE != 2`, `prepare()` does not open `/tmp/m1plus-xfade` and
  returns `0` immediately. Once `NEXT_STATE == 2`, it reads `/tmp/m1plus-xfade` (in-RAM tmpfs,
  re-checked at most every 0.5 s until the fade starts so last-second setting changes take effect).
- **Codec init and handoff:** when Track A enters the final `D` seconds, `try_start()` calls
  stock `init_best_audio_codec` (`0x47eb50`) on `next_mpctx->sh_audio` and sets
  `NEXT_CODEC_INITED` (`0xb10d70`) = `1`. Stock's gapless swap (`0x4222b0`) sees
  `NEXT_CODEC_INITED == 1`, sets `INITIALIZED_ACODEC` so `reinit_audio_chain` skips re-initializing
  the codec, and keeps any unconsumed bytes already decoded in `next_sh->a_buffer` along with
  `sh_audio->pts` and `pts_bytes`. Because `pull_b_frame()` consumes exact frames via a block
  cursor and compacts `next_sh->a_buffer` once per refill/block, Track B resumes sample-accurately
  at `0:0D` after the swap with negligible CPU overhead.
- **Equal-power curve:** Track A fades by `cos(u * pi / 2)` and Track B fades by
  `sin(u * pi / 2)` for `u in [0, 1]`, stepped per block with a 2D rotation oscillator. On native
  integer outputs, summed peaks above `+/-0.95` pass through a gentle asymptotic soft clipper so
  overlapping loud tracks never wrap.
- **Sample-rate and channel adaptation:** when Track B's sample rate differs from Track A's, Track B is converted in
  real time by hciplayer's libswresample (`patch/xfsrc.c`, `XF_SRC_FILTER_SIZE`) during the overlap. The converter goes
  whole (context, delay and waiting frames) to Track B's own filter instance, so the rate change after the join is
  continuous (see "Kept output and conversion"). Mono and stereo streams mix cleanly across channel-count changes.
- **ReplayGain matching:** because stock's `replaygain` filter runs upstream of `peq_player.c`,
  Track A already carries ReplayGain while `next_sh->a_buffer` is raw decoded PCM. `next_rg_gain()`
  reads Track B's ReplayGain tags from `0xb0c790` when `RG_MODE` (`0xb10e30`) is `1` (Track) or
  `2` (Album), applying the same dB-to-linear conversion and peak limiting as stock (`0x428354`).

## Edge cases and aborts

- **VBR early EOF:** if Track A reaches EOF before `u` reaches `1.0`, `leave()` saves
  `xfade_carry` (`u`, `dur`) across `uninit()` -> `adopt()`, including across sample-rate or
  channel changes. Track B's filter instance finishes the remaining fade-in (`XF_TAIL_IN`, capped
  at 3 s) smoothly to `1.0`.
- **VBR late EOF:** if `pos_frames` reaches `tot_frames` before Track A's demuxer ends,
  `force_eof()` sets `d_audio->eof = 1` and `mpctx->eof = 1` so `hciplayer` executes the gapless
  swap on the next loop iteration while `XF_DONE` outputs pure Track B. This skips stock's own
  end-of-track drain, so `flush_tail` writes what stock has not written yet (see "Kept output and
  conversion").
- **Track position:** `track_a_pos()` is stock's `calc_a_pts` (`0x44600c`) less what the decoder's
  buffer still holds: `sh_audio->pts` plus the bytes decoded since, or, for a decoder without
  timestamps, the demuxer's last packet pts plus the packet data read but not decoded
  (`ds_tell_pts` over `i_bps`). A track length the demuxer did not know at the start is asked for
  again every 0.5 s.
- **Track B early EOF:** if Track B's decoder runs out of audio during overlap (for example on an
  overestimated or truncated file), `process_block()` records the preload's `seq` in `bad_seq`,
  ramps Track A smoothly back to `1.0` over 20 ms (or leaves the block bit-exact if zero Track B
  frames were mixed), frees `next_mpctx` and sets `NEXT_FLAG = 1` so `PreInitNextSong` re-preloads
  Track B cleanly from `0:00` for a normal gapless join without re-entering crossfade.
- **Backward seek:** if Track A's stream position jumps backward by more than `0.5 s` mid-fade,
  `start_abort()` ramps Track A back to `1.0` and Track B down to `0.0` over 20 ms, calls stock
  `uninit_next_song` (`0x42a9cc`), clears `NEXT_CODEC_INITED` / `NEXT_STATE`, and sets
  `NEXT_FLAG = 1` so `PreInitNextSong` re-preloads Track B cleanly from `0:00`.
- **Queue edit / cancel (`mcl-closegapless`):** if `NEXT_STATE` drops out of `2` mid-fade,
  `start_abort()` runs the same 20 ms ramp without calling `uninit_next_song`.

## Preload coordination and Gapless bridge (`patch/xfadeset.c`)

`demo` coordinates Crossfade without any new binary hook by extending Hook 36 (`rd_auto_change` ->
`xfade_auto_change` -> stock `mclAutoChange`).

- **Runtime record:** `/tmp/m1plus-xfade` (tmpfs, zero flash wear) holds a 20-byte `xfade_record`:
  8-byte magic `"M1XFD01\0"`, `int seconds` (`0..12`), monotonic `int seq`, and `int keep`.
  `xfade_boot()` removes any stale file on startup; `xfade_on_preload_cancel()` (called from
  `patch/shuffle.c` `cancel_preload()`) and `xfade_auto_change()` whenever `MCL_PRELOAD == 0`
  write `seconds = 0` so short, same-album or excluded tracks never inherit a previous track's
  duration.
- **`keep`:** tells "Crossfade is off or stays out of this join" (`0`) from "this join does not
  fade" (`1` with `seconds == 0`). It is `1` when Crossfade is on and the coming join is between
  two music tracks: not a CUE track, not DSD by extension, not an `http(s)://` path, and not under
  `/mnt/mmc/Podcasts/` or `/mnt/mmc/Audiobooks/` (prefixes matched without regard to ASCII case).
  A same-album join under Keep Albums Gapless and a track under 10 s are such joins. The player
  reads it only in `xf_uninit_player` (`patch/xfsrc.c`): a session whose output is already kept in
  another format goes on across a `keep` join without a fade; with `keep == 0` stock reopens the
  output. `xfade_auto_change()` rewrites the record whenever `seconds` or `keep` for the coming
  join changes while no preload is open (`MCL_PRELOAD == 0`); then it is also `0` while nothing
  plays or playback is paused. Turning Crossfade off writes `0` at once.
- **Early preload:** stock `mclAutoChange` only triggers gapless preload ~5 s before EOF, which is
  too late for a long crossfade. When Crossfade is enabled and `total - cur <= eff + 5`,
  `xfade_auto_change()` writes `eff` (with `keep = 1`) to `/tmp/m1plus-xfade` and calls stock
  `mcl_gapless_preload` (`0x5d0ea4`, pinned in `XFADE_PINS`). The play time (a locked copy of two words,
  which stock's `mclAutoChange` also reads on every pass) is read on every idle pass. The queue records are
  looked at every 500 ms (`XF_CHECK_MS`) while the track is further from its end than `sec + 5` s, and on
  every pass inside that window or on another track, so a seek into the last seconds is seen before stock's
  own preload (about 5 s before the end) opens without the duration. Between two looks the last `keep`
  stands.
- **Gapless-off bridge:** if the user's Gapless setting (`MCL_GAPLESS`, `0xa0ab89`) is off while
  Crossfade is on, `xfade_auto_change()` temporarily sets `MCL_GAPLESS = 1` across
  `mcl_gapless_preload()` (and across the seamless `mclNextSong(1)` handoff inside `mclAutoChange`
  when `HCI_RUNNING == 0` and `MCL_PRELOAD == 1`), restoring `0` immediately so the user's Gapless
  setting is never altered. Turning Crossfade off while such a preload is open calls
  `mclSetGaplessMode(0)` to close it cleanly.

## Settings and files

| Path | Kind | Values / default |
|---|---|---|
| `/mnt/data/m1plus/playback-crossfade` | flash setting | one character: `a`..`l` on with 1..12 s; `A`..`L` off with 1..12 s kept; missing or any other: off, 5 s (default) |
| `/mnt/data/m1plus/playback-crossfade-auto` | flash setting | `0` Always; missing or `1` Keep Albums Gapless (default) |
| `/tmp/m1plus-xfade` | tmpfs runtime | 20-byte `xfade_record` (`M1XFD01\0`, `seconds`, `seq`, `keep`) |
| `/tmp/m1plus-xfout` | tmpfs runtime | 8-byte `xfout_record` (magic `XFO1`, `int rate`): the rate the output is kept at while tracks are converted to it, `0` when the output is a track's own again |

The player writes `/tmp/m1plus-xfout` (`patch/xfsrc.c` `tell_out`): the rate when a join keeps the
output in another format, `0` at every real open of the output (`xf_ao_init`). The first sticky
session creates the file; before that an open of the output only looks for it. `xfade_boot()`
removes it. `xfade_out_rate()` (`patch/xfadeset.c`) reads it for Now Playing's info page, whose
Sample Rate row then shows `44.1 → 96 kHz` ([Now Playing](nowplaying.md)); it answers 0 when
`hciplayer` is not running, since a player that went away leaves its record.

## Kept output and conversion (`patch/xfsrc.c`)

Stock closes and reopens ALSA at every track change, gapless or not: the end-of-track cleanup
(`0x4217d8`) calls `uninit_player(0xff7a)`, whose mask includes the audio output (`0x2`), and the
next `reinit_audio_chain` opens it at the next track's native format (about 16 ms when the format
is the same, 180 to 530 ms when it changes). A crossfade into another sample rate would end in
that gap, so while Crossfade has a part in a join the output stays open and Track B is converted
to its rate. A session whose output is kept in another format than the playing track's is
**sticky**.

- **`xf_uninit_player`** replaces the `jal` at `0x4217d8` (the only wrapped `uninit_player` site;
  `0x424074`, `0x424244`, `0x425df8`, `0x42e1b4`, `0x42eb00`, `0x42fa3c`, `0x42fae4` and `0x430084`
  stay stock). It drops bit `0x2` from the mask, and copies `mpctx->audio_out` to `next_mpctx + 8`
  (the swap copies `next_mpctx` over `mpctx`), when all of these hold:
  - an automatic change: `mpctx->eof == 1`, `NEXT_STATE == 2`, the gapless switch `0xb10e40 == 1`,
    the output open;
  - crossfade has a part in the join: this join faded, or its record has `seconds > 0`, or the
    session is sticky and the record has `keep` (a same-album join);
  - the session is sticky, or this join faded, or Track B's rate, channels and format equal
    `ao_data`;
  - the filter can convert: neither track is DSD, and for another format Track B is 8 to 384 kHz,
    1 or 2 channels, a plain PCM format.

  Otherwise the mask is stock's and the output reopens natively. A skip, a stop, Crossfade off and a
  join into a podcast, an audiobook or a stream are all stock.
- **`xf_ao_init`** (ao_alsa's init slot) clears the sticky state: every real open is native.
- **`xf_reinit_chain`** wraps the swap's `reinit_audio_chain` call (`0x421cec`). With the output
  open, stock sends a control to `sh_audio->afilter` before allocating it, and a preloaded track
  has none (stock never gets here with a fresh `sh_audio`): the wrapper allocates the empty stream
  as `init_audio_filters` would. In a sticky session it sets `ao_data.rate` to the track's own rate
  for the call, so stock builds the chain without its own resampler, then restores `ao_data` and
  sets the chain's target rate (`af_stream + 0x28`) to the output's: `af_add`'s output check
  (`0x44c37c`) would otherwise remove our filter, which ends at the output rate.
- **The filter converts** (`patch/peq_player.c`): at `REINIT`, `xf_out_rate()` gives the kept
  output's rate when it differs from the track's; the instance then reports that rate and
  `af->mul`, forces float, converts each block in `convert()` and runs Mono, PEQ, Crossfeed, VU and
  Crossfade after it. `convert()` restates rate, channels, format and bps on every block, because
  the `af_format` after it rewrites the `af_data` it is handed.
- **The converter carries over** (`leave` / `adopt`): Track B's overlap converter, or else the
  leaving instance's own, goes to the next instance when the input rate, output rate and channels
  match and the join is under `CARRY_MS`. Its delay is about 8 input frames and is not reported.
  It is hciplayer's statically linked libswresample (`swr_alloc_set_opts`, `av_opt_set_int`,
  `swr_init`, `swr_convert`, `swr_free`; float in and out, `XF_SRC_FILTER_SIZE` 16).
- **`flush_tail`:** `ao_alsa`'s `play` writes whole 4096-byte bursts, and
  `fill_audio_out_buffers` keeps the remainder in `sh_audio->a_out_buffer` (`+0x78`, length
  `+0x7c`) for the next call; `uninit_player` frees it. Stock drains it at a natural end, but the
  crossfade ends Track A itself. Before a kept-output swap the wrapper writes it with the
  final-chunk flag (at most 8 writes when the driver takes only part), otherwise 2 to 10 ms that
  are already Track B's would be dropped: a tick.
- **Pause returns to the track's own format** (`xf_ao_pause`, `xf_ao_resume`, ao_alsa's pause and
  resume slots). In a sticky session with no crossfade running, pause first writes the tail and
  waits for the output's queue to play out (at most 0.5 s; about 0.2 s at 96 kHz, 0.4 s at
  44.1 kHz), then pauses. Resume ends the session: `uninit_player(2)`, `reinit_audio_chain`, then
  the driver's resume, the sequence stock's pause loop uses when the output device changes
  (`0x430084`). The filter drops a rate request it accepted while sticky.
- **Tests:** libswresample itself does not run under Unicorn; `test/pod/crossfade.py` stubs its
  five calls with a stateful linear-interpolation model.

## Stock `hciplayer` reference

Verified in the disassembly of stock `hciplayer` (mplayer 1.3 with vendor changes).

- **Globals:** `mpctx` pointer `0xaf9e30`, `next_mpctx` `0xaf9b90` (`0x2a0` bytes), `NEXT_STATE`
  `0xb10dd0`, `NEXT_CODEC_INITED` `0xb10d70`, player flags `0xb10e70` (`0x2` output, `0x40`
  stream, `0x200` demuxer, `0x400` codec), gapless switch `0xb10e40`, `ao_data` rate / channels /
  format `0xafa1a0` / `0xafa1a4` / `0xafa1a8`, buffersize `0xafa1b4`, outburst `0xafa1b0`.
- **Swap** (`0x422244`): copies `next_mpctx` over `mpctx`, clears `NEXT_STATE`, sets flags
  `0x240` (`0x640` when the codec was initialised), then `reinit_audio_chain` (`0x42e680`) at
  `0x421cec`. With flag `0x2` clear it initialises the filters at the native format and opens the
  output (`0x42e80c`); with it set it rebuilds only the chain against the current `ao_data`.
- **ao_alsa** driver table `0x88f168`: control `+4`, init `+8` (`0x438648`), uninit `+0xc`
  (`0x43834c`), reset `+0x10` (`0x439850`), get_space `+0x14` (`0x437e1c`), play `+0x18`
  (`0x43aae4`), pause `+0x20` (`0x438224`), resume `+0x24` (`0x4384ac`). Init always closes and
  reopens the PCM; uninit closes it only when `[0xb10e54] == 1`. ALSA's own resampling is off
  (`set_rate_resample(0)`), so the hardware rate must exist. The buffer is 16384 frames.
- **Chain negotiation** (`0x44c710`): for a rate mismatch stock asks the filters, last to first,
  with `control(af, 0x40000100, &rate)`, and inserts `resample` or `lavcresample` when none
  accepts. Our filter is added later by the playback loop (`af_add`, `0x44cc88`), so it is not in
  the chain to answer at that point.
- **FLAC seek threshold:** the float at `0xb15290`, written by `demux_audio`'s seek and cleared
  when that demuxer closes; `flac_decode_frame` rejects every frame that starts before it. It is
  global, not per decoder.
- **libswresample:** `swr_alloc_set_opts` `0x7235bc`, `swr_init` `0x41e32c`, `swr_convert`
  `0x724b40`, `swr_free` `0x41e2d0`, `av_opt_set_int` `0x6f9770`; plain O32 calls, 64-bit
  arguments in even register pairs. `tools/mod_player.py` pins each prologue.

## Known limitations

- Crossfade applies to automatic track transitions (List Play, Repeat All, Shuffle). Manual
  Next / Previous skips cut immediately as in stock.
- In a sticky session the output keeps the first track's sample rate, and later tracks are
  resampled to it until a pause, a skip or a join that crossfade stays out of. The Sample Rate row
  of Now Playing's info page shows both rates meanwhile.
- A sticky session's pause takes effect up to about 0.4 s late (the queued audio plays out), and
  its resume reopens the output like a track start. A pause during the overlap keeps the session.
- Outside a sticky session, a join into another format that does not fade reopens the output as
  stock does. DSD, more than two channels and rates over 384 kHz reopen it in any session.
- The kill switch (`/mnt/mmc/m1plus-off`) is not looked at when the output is kept. Created in the
  middle of a sticky session, it switches the filter's conversion off while the output stays at
  the other rate, so the next joined track plays at the wrong speed until the output reopens (a
  pause, a skip). With the switch present from boot no session becomes sticky.
- Very short tracks under 10 s are skipped.
