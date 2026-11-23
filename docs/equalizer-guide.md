# Equalizer

[User guide](guide.md) · [Settings](settings-guide.md) · [Features](features-guide.md)

**Settings → Playback → EQ** opens the Equalizer. Its switch turns the EQ on or off; when off,
the EQ does not alter playback. The EQ works at every sample rate and on every output; DSD plays
without it.
While the switch is on, the status bar shows **EQ** after the volume.

Headphones, Line Out and a USB DAC each keep their own EQ (on or off, and what plays), and it
switches by itself when the output changes. The grey line under the switch names the output you
are setting.

## Get started

1. Connect the output you want to adjust and open **Settings → Playback → EQ**.
2. Turn the EQ on and choose **10-Band EQ** or a preset.
3. To adjust the bands, open **Edit 10-Band EQ**. For a headphone correction, connect to Wi-Fi and open **Presets → Download from AutoEq**.

## Edit and manage presets

Below the preset list:

- **Edit 10-Band EQ:** drag anywhere in a band's column to set it (±12 dB in 0.5 dB steps); the
  graph and the sound follow. **Curve** picks Flat, a genre curve or Custom (moving a slider on a
  genre curve copies it into Custom). **Preamp** is Auto, which lowers the level by the largest
  boost to prevent distortion, or a fixed cut. **Reset** returns to Flat. **Save as Preset** saves
  the curve as a preset file.
- **Presets:** **Download from AutoEq** searches the AutoEq database by headphone name (with
  Wi-Fi); tap a result to save its correction, then tap it again to use it. Your presets are
  listed under AutoEq and On Card. Open one to see its curve and bands; tap a band to change its
  type, frequency, gain or Q (the values can be typed on a number keypad). Leaving with unsaved
  changes asks whether to **Save**, **Save As New…** or **Don't Save**. **Delete Preset** removes the file.

Presets are Equalizer APO / AutoEq parametric `.txt` files in the `EQ` folder on the card (up to
64 files of up to 64 bands each; `Preamp`, `Channel` and `Filter` lines with peak and shelf filters), so you can also copy your
own there.
