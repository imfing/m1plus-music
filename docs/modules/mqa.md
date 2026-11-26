# Non-MQA Probe Skip

**Sources:** `tools/mod_player.py` (`MQA_PROBE_RET`, `PINS`).

Stops stock `hciplayer` from running its MQA decoder on ordinary non-MQA FLAC and PCM tracks only to
discard the output.

## Stock behaviour

At track start, `reinit_audio_chain` calls `mqa_probe` (`0x42e428`) for stereo 16-bit or 24-bit
FLAC/PCM streams (`codec` 11 or 13) at 44.1, 48, 88.2, 96, 176.4 or 192 kHz (excluding DSD and
lossy codecs such as M4A/MP3):

- `mqa_probe` allocates the MQA detector (`0x72f300`), reads an initial probe chunk (`0x47f0ac`),
  runs the detector (`0x72f380`) and frees it (`0x72f360`).
- When the detector reports MQA (`1`), `mqa_probe` returns `2` (`movz $v0, $s1, $s0` at `0x42e570`).
- When the detector reports non-MQA (`0`), or the initial decoded length is zero or not frame-aligned,
  stock loads `$v0 = 1` (`0x42e564`, `0x42e548`) instead of `0`.
- `reinit_audio_chain` skips MQA decoder setup only when the return value is `<= 0`
  (`blez $t5, 0x42f088` at `0x42e940`). On `1`, it still allocates the `0x9018`-byte MQA decoder
  (`0x72f388`), stores `mqa_mode = 1` at `0xb10c54` (`0x42efbc`), and uses the shadow decoder as a
  continuous mid-track detector: in `fill_audio_out_buffers` (`0x42f468`, `0x42f690`, `0x42f7cc`)
  it feeds every audio block through the MQA decoder (`0x72f45c`), flushes it at EOF (`0x72f498`),
  and queries its status via `0x72f500` into `0xb10c1c`. Because `mqa_mode != 2`, the decoded PCM
  output is discarded and raw PCM goes to ALSA unless `0x42fa14` / `0x42fad0` sees status `1..3`,
  in which case `0x42fb18` upgrades `mqa_mode` to `2` and rebuilds the audio chain (`0x42e680`).

## Patch (`tools/mod_player.py`)

Two pinned word edits in `MQA_PROBE_RET`, with no added payload code and no setting:

| Address | Stock | Patched | Effect |
|---|---|---|---|
| `0x42e548` | `0x24020001` (`addiu $v0, $zero, 1`) | `0x24020000` (`addiu $v0, $zero, 0`) | Short/unaligned initial probe returns `0` |
| `0x42e564` | `0x24020001` (`addiu $v0, $zero, 1`) | `0x24020000` (`addiu $v0, $zero, 0`) | Non-MQA probe returns `0`; real MQA still overwrites `$v0` with `2` at `0x42e570` |

With `0` returned, `reinit_audio_chain` jumps over MQA decoder allocation to `0x42f088`, `mqa_mode`
stays `0`, and ordinary FLAC/PCM playback takes the same direct ALSA output path stock already uses
for M4A and MP3.

## Constraints and known limitations

- Only the track-start probe detects MQA; streams whose MQA sync appears only mid-track are not
  unfolded. Standard MQA files carry the sync word at the start and continue to return `2` and
  unfold normally.
- Stock skips `mqa_probe` at `0x42e8f0` when `mqa_mode != 0`. Because patched non-MQA FLAC/PCM
  tracks keep `mqa_mode == 0`, every subsequent `reinit_audio_chain` (`0x42e680`, such as an EQ
  toggle or output switch) runs `mqa_probe` again; the one-chunk probe is small and still returns
  `0`.
- Every edit and surrounding instruction is pinned in `tools/mod_player.py`; any mismatch fails the
  build. Because these are two stock instruction immediates (not payload hooks), `/mnt/mmc/m1plus-off`
  does not revert them.
