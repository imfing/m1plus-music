"""Wi-Fi and Bluetooth together: four pinned words in demo (docs/modules/overlays.md "Wi-Fi and Bluetooth together").

Stock keeps the radios exclusive in the UI only. Switching one on while the other is on asks (kind-5 confirm, msg_wifi_open / msg_bt_open) whether to turn the other off first, and on OK
switches it off before the requested radio goes on. The question's text becomes a warning (tools/pod_i18n.py COEX_TEXT, tools/mod_strings.py); OK now only switches the requested radio on.
Cancel is unchanged. No code is added; none of this is on the boot path.

Bluetooth side (the Control Center Bluetooth tile, the stock Bluetooth settings switch): after OK the handler tests the Wi-Fi flag and calls wifi_switch(1) (off); the `beqz v0, skip` after that
test becomes `b skip` (same target). Nothing runs between the confirm and that test.

Wi-Fi side (the Control Center Wi-Fi tile, the stock Wi-Fi settings page, which is only a fallback behind our own page): after OK stock first cancels a Bluetooth start in progress: bt_exit_init
(byte 0xa038a8) = 1, a wait of up to 20 x usleep(200000) while bt_initstatus (0xa038a4) is not 0, switchBluetooth(1, 0) when Bluetooth is on, then both words cleared, and only then wifi_switch(1).
Setting bt_exit_init aborts Bluetooth's startup worker, and with the switch-off skipped Bluetooth would stay "on" (bluetoothflag 1) but dead. So the first word of that preamble (the lw of the
bt_exit_init GOT slot, right after the confirm returned 10) becomes `b` to the lw t9 of the wifi_switch(1) call: the whole preamble (the write, the wait, the switch-off, the clearing) is skipped
on OK. The delay slot is the preamble's next word, a lui into a register nothing reads afterwards.
"""

# (address, stock word, new word, what)
EDITS = (
    (0x474d98, 0x10400005, 0x10000005, 'Control Center Bluetooth tile: `beqz v0, skip` -> `b skip`: after OK, skip wifi_switch(1) (Wi-Fi stays on)'),
    (0x474fd8, 0x8f92a9a4, 0x10000013, 'Control Center Wi-Fi tile: lw s2, GOT bt_exit_init -> `b 0x475028` (lw t9 wifi_switch): after OK, skip the Bluetooth cancellation preamble'),
    (0x4a3b64, 0x10400004, 0x10000004, 'Bluetooth settings switch: `beqz v0, skip` -> `b skip`: after OK, skip wifi_switch(1) (Wi-Fi stays on)'),
    (0x4b0b9c, 0x8f82a9a4, 0x10000018, 'Wi-Fi settings switch: lw v0, GOT bt_exit_init -> `b 0x4b0c00` (lw t9 wifi_switch): after OK, skip the Bluetooth cancellation preamble'),
)
# words that must be stock's: (address, word, what); the skipped call is lw t9 GOT (wifi_switch -0x566c) + jalr t9
PINS = (
    (0x474d94, 0x92820000, 'Bluetooth tile: lbu v0, (s4): the Wi-Fi flag'), (0x474da0, 0x8f99a994, 'Bluetooth tile: lw t9, GOT wifi_switch'), (0x474da4, 0x0320f809, 'Bluetooth tile: jalr wifi_switch'),
    (0x474fc4, 0x0320f809, 'Wi-Fi tile: jalr navigator_to_with_context (the confirm)'), (0x474fd0, 0x14430019, 'Wi-Fi tile: bne v0, v1 (not OK) -> 0x475038'),
    (0x474fdc, 0x3c150003, 'Wi-Fi tile: lui s5, 3 (the branch\'s delay slot; s5 is the usleep argument of the skipped wait only)'),
    (0x475028, 0x8f99a994, 'Wi-Fi tile: lw t9, GOT wifi_switch (the branch target)'), (0x47502c, 0x0320f809, 'Wi-Fi tile: jalr wifi_switch'), (0x475030, 0x24040001, 'Wi-Fi tile: a0 = 1'),
    (0x4a3b60, 0x92220000, 'Bluetooth switch: lbu v0, (s1): the Wi-Fi flag'), (0x4a3b68, 0x8f99a994, 'Bluetooth switch: lw t9, GOT wifi_switch'), (0x4a3b6c, 0x0320f809, 'Bluetooth switch: jalr wifi_switch'),
    (0x4b0b88, 0x0320f809, 'Wi-Fi switch: jalr navigator_to_with_context (the confirm)'), (0x4b0b94, 0x14430028, 'Wi-Fi switch: bne v0, v1 (not OK) -> 0x4b0c38'),
    (0x4b0ba0, 0x3c140003, 'Wi-Fi switch: lui s4, 3 (the branch\'s delay slot; s4 is the usleep argument of the skipped wait only)'),
    (0x4b0c00, 0x8f99a994, 'Wi-Fi switch: lw t9, GOT wifi_switch (the branch target)'), (0x4b0c04, 0x0320f809, 'Wi-Fi switch: jalr wifi_switch'), (0x4b0c08, 0x24040001, 'Wi-Fi switch: a0 = 1'),
)


def apply(patched, fileoff):
    """Check every stock word in the bytearray `patched` (word at `fileoff(patched, address)`), then write the four branches."""
    import struct
    for a, w, _ in PINS + tuple((a, old, what) for a, old, _, what in EDITS):
        got = struct.unpack_from('<I', patched, fileoff(patched, a))[0]
        if got != w: raise ValueError(f'{a:#x} ({_}): {got:#010x} != pinned {w:#010x}')
    for a, _, new, _ in EDITS:
        struct.pack_into('<I', patched, fileoff(patched, a), new)
