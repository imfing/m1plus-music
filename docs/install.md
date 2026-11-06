# Install and update

You need a Shanling M1 Plus, a working TF/microSD card and the `update.bin` from the latest
[M1+ Music Navidrome release](https://github.com/iamgauravmishra/m1plus-music-navidrome/releases/latest).

Only kernel and rootfs are updated. The bootloader and recovery kernel stay unchanged, but the
M1 Plus recovery button combination remains unverified. Keep the battery charged and leave
the card inserted until the update finishes.

This is unofficial third-party firmware. Install it at your own risk. Back up your card before
updating. I am not responsible for damage caused by installing or using this firmware.

## Install

1. Back up the card and shut down the player before removing it.
2. Copy the release's `update.bin` to the card root.
3. Insert the card with the player off, then turn it on.
4. Open **System settings → System Update → TF card update** and confirm.
5. Wait for the player to restart. Check the **M1+ Music** tag in About, below stock V2.1.
6. Follow the [user guide](guide.md#start-listening) to scan your music and start listening.

Music stays on the card. Overwrite the retained `update.bin` for the next update.

## Update

From 1.1.0, open **Settings → System → About → Software Update** with Wi-Fi on: it downloads the
newest release to the card and starts the TF card update (see the [user guide](guide.md#settings)).
Without Wi-Fi, or from 1.0.0, repeat the installation steps with the newer release's `update.bin`.

## Disable M1+ Music

Create an empty file named exactly `m1plus-off` at the card root. Remove it to enable
M1+ Music again.
The boot guard also falls back to stock Home after a failed custom startup.

## Restore stock

Download the official M1 Plus firmware from [Shanling](https://en.shanling.com/download/118),
unzip it, copy its `update.bin` to the card root and install it through the same TF-card menu.

If M1+ Music fails to open, try disabling it with `m1plus-off` first. Do not assume the Q2's
recovery buttons work on the M1 Plus.

Package builders: see [build and restore instructions](workflow.md#integration-and-restore).
