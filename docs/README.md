# Documentation

## Guides

| Guide | Use it for |
|---|---|
| [Install](install.md) | Prepare the card, update the player, disable the mod or restore stock |
| [User guide](guide.md) | Browse music, control playback and customize the interface |
| [Development](workflow.md) | Set up uv, build, test, format and prepare releases |

## References

| Reference | Contents |
|---|---|
| [Architecture](architecture.md) | Payload, build pipeline, hooks and feature source maps |
| [UI](ui.md) | Preview, layout rules, fonts, assets and rendering |
| [Firmware](firmware.md) | Stock hashes, updater behaviour, partitions and space recovery |
| [Device checks](modules/device-checks.md) | Hardware validation checklist |
| [History](history.md) | Recorded milestones, device findings and lessons |
| [Navidrome / Subsonic](modules/subsonic.md) | Remote library, raw streaming, SD downloads and validation limits |

Read the relevant `modules/` doc for implementation, pins and tests before changing a feature.
Before searching stock binaries, read [payload](modules/payload.md) and [addresses](modules/addresses.md).

## Source layout

| Directory | Contents |
|---|---|
| `tools/` | Host build, validation, assets, previews and binary analysis |
| `patch/` | Runtime C payload, stock offsets and linker script |
| `test/` | MIPS/host tests and package goldens |
| `assets/` | Fonts, icon sources, boot logo and wallpaper |

Module references describe current behavior, source files, safety constraints and validation
limits. Keep implementation plans and superseded designs in git history. Use `tools/pod.py`
for current pins/sources and build manifests for sizes. Device results apply only to their
recorded build.
