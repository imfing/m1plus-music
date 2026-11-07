# Sample Rate RGB

Extras > Settings > System > **Sample Rate RGB** is a persistent on/off switch for the wheel lamp's playback-format indicator. It defaults on. Turning it off restores Shanling's saved LED colors.

While a track is playing, RGB channels mix according to its format:

| Format | Red | Green | Blue |
|---|---:|---:|---:|
| Lossy audio, or PCM at 16-bit/44.1 kHz and below | 100% | 0% | 0% |
| PCM above 16-bit through 44.1 kHz; DSD64 | 60% | 0% | 40% |
| PCM above 44.1 kHz through 48 kHz | 20% | 0% | 80% |
| PCM above 48 kHz through 88.2 kHz | 0% | 0% | 100% |
| PCM above 88.2 kHz and below 176.4 kHz; DSD128 | 0% | 20% | 80% |
| PCM from 176.4 kHz to below 192 kHz; DSD256 | 0% | 40% | 60% |
| PCM at 192 kHz and above (24-bit or higher); DSD512 and above | 0% | 100% | 0% |

PCM at 192 kHz and above but below 24-bit stays blue. Unknown DSD rates fall back to red.
Volume scales the mixed output without changing its target channel ratios: zero turns the lamp
off, each five volume steps add one intensity level, and level 17 is reached at volume 85.
The stock lamp state has 17 levels per channel, so ratios are rounded to those levels,
especially when dim. The configured maximum-volume setting does not change the 0–85 scale.

The status callback reads Shanling's volume value but never writes it. Brightness updates on the stock playback-status refresh.

The switch is stored atomically in `/mnt/data/m1plus/rgb-indicator`: `0` is off and any other valid or legacy value is on. Missing or invalid settings default to on. A saved `2` from an older Visualizer build is treated as on and now selects Sample Rate RGB; there is no Visualizer mode or worker.

`tracklamp.c` replaces only the existing `mclGetPlayStatus` call at `0x4ce968` in `on_wm_idle_status`. It calls that stock function once and returns its result unchanged. While playing, it reads the current queue record, MCL's 52-byte metadata snapshot (codec, sample rate and bit depth), and the read-only volume global. The mixed channel levels are staged in Shanling's transient RGB state; the existing stock timer applies them. Pause, stop, radio handover, an empty queue, disabling the switch or `/mnt/mmc/m1plus-off` restores the user's saved stock lamp colors.

The feature does not read or alter PCM samples, decoder settings, sample-rate conversion, volume, DAC settings or playback controls. It adds no audio-path hook, network activity, timer or worker. Hardware checks are still needed to confirm the volume-to-brightness curve and color thresholds on the player.
