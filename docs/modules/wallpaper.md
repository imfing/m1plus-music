# Wallpaper

## Wallpaper (`tools/mod_wallpaper.py`, `tools/wallpaper_prepare.py`)

How a wallpaper is chosen (the folder, the list, the tap, who reads it) and our picker page: [lock screen](lockscreen.md) "Wallpaper picker".

With no custom wallpaper `get_screensaver_image` (`0x4d7524`) and `config_init` keep the resource name
`screensaver_default` as `SCREENSAVERPATH`; a chosen picture is `file://` plus its path. Only the
resource changes: `images/xx/screensaver_default.png` (320x480; `xx` is the only set that has it;
`screensaver_default1.png`, 640x480, is unreferenced and stays) becomes a drawn bokeh field
(`assets/bokeh-320x480.png`, our own design): a vertical gradient from indigo through aqua to deep sea
green, with soft discs of lavender, blue and mint light, large and faint behind the clock, small and
brighter along the card's sides and under it (the card covers the middle). `wallpaper_prepare.py OUT.png`
draws it with Pillow, reduces it to an 8-bit palette (256 colours, median cut, no dithering) and
compresses it losslessly with primage (OxiPNG level 6, keeps the palette): 9,485 bytes, SHA-256
`8bf48350...`, against the stock picture's 398,437, so the swap frees about 389 KB of rootfs. The
output is deterministic; primage is needed only to redraw it, the build copies the committed file.
demo's loader is stb_image, which expands palette PNGs. The step pins the stock file's SHA-256 (`92e7162b...`) and the asset's.
