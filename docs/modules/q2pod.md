# q2-pod design reference

M1+ Music is inspired by q2-pod. Both devices use an Ingenic/MTouch/AWTK stack, but the M1 Plus
has different stock addresses, page assets and touchscreen controls. Never reuse a Q2 address
or patch word without checking the pinned M1 Plus binary.

| Mechanism | M1 Plus source |
|---|---|
| Payload segment, pinned edits, GOT stubs and trampolines | `tools/pod.py`, `patch/link.ld` |
| Stock layouts and page definitions | `patch/offsets.inc`, `tools/pod_pages.py` |
| Cover Flow rendering and cache | `patch/coverflow.c`, `patch/covercache.c` |
| Library row edits | `patch/rows.json`, `patch/rows.c` |
| UTC RTC (`hwclock -wu`) | `tools/autotime.py` ([autotime](autotime.md)); q2-pod `RTC_WRITE` |
| PEQ: hciplayer's equalizer replaced, the APO parser, the engine | `tools/mod_player.py`, `patch/peq.c`, `patch/peq_player.c` ([peq](peq.md)) |
| Host/MIPS testing | `test/coverflow.py`, `test/patch.py`, `test/pod/` |

The [Charge Limit](charging.md) follows q2-pod's 80% stop / 75% resume idea on the M1 Plus's
kernel charging switch; no q2-pod code or address is used.

The README acknowledges q2-pod; file-specific notices identify borrowed material. The
[payload](payload.md) and [safety](safety.md) documents define this project's allowed hooks.
