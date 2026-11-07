#!/usr/bin/env python3
"""Icon set for the Shanling M1 Plus UI: Lucide (ISC) in the Minimal look, a few Tabler glyphs (MIT) where Lucide has
no match. Asset-only.
Description, mapping table, substitutes and what stays stock: docs/ui.md.

Replaces, in the default theme's images/xx (same file names, same pixel size, RGBA PNG, same
file mode):
  46 settings icons    40x40, a bare white Lucide glyph (24 px canvas, stroke 2.0 px) centred, no disc; the four
                       stock badges (DAC, DSD output, ReplayGain) redrawn as white text badges in a thin rounded rect
  18 Home icons        66x66 (+ 17 pressed `_down`), white glyph (38 px canvas, stroke 1.75) on the #777777 disc (#555555 pressed)
  pull-down tiles      50x50, one ring style for every tile (docs/ui.md): #777777 ring + glyph = off,
                       white disc + dark glyph = on, #444444 = disabled; Lucide glyphs (24 px canvas), custom gain bars,
                       "PO"/"LO" in Inter (17 px); backlight sun icons 20x20
  status bar           play/pause (filled), volume 0-4, Wi-Fi 0-4 (unlit arcs #666666), Bluetooth,
                       digital out; stroke 1.5 px at 14-16 px, 2 px at 20 px
  list placeholders    6 folder/playlist/artist/genre/composer/album discs, albumcover s/m/info tiles
  round 2 (docs/ui.md "Icon audit"): navbar actions, chevrons, selection marks, dialog actions as plain white
                       glyphs at the stock size (pressed #777777); Folders file/SD/USB rows, Playlists page
                       and CD-ripper discs; equaliser preset art recoloured white; speed badges, the Play all
                       pill, secured Wi-Fi rows; the Now Playing np_* glyphs (mod_nowplaying.py copies them)
Stays stock: brand art and text badges (codec badges, SyncLink, A-B), theme1
(its own image files), the battery (tools/battery_art.py draws it for mod_battery/mod_lockscreen).

Build time only copies the committed PNGs (assets/icons/png/); builds stay deterministic and
need no rasteriser. The PNGs are generated from the committed SVG sources (assets/icons/lucide/svg/, lucide-static
1.61.0, ISC; assets/icons/tabler/svg/, @tabler/icons 3.49.0, MIT, the few 'T:' glyphs) by --generate (needs
rsvg-convert and Pillow).

Usage: mod_icons.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place; a build.py step)
       mod_icons.py --generate                  rebuild assets/icons/png from the svg sources
       mod_icons.py --fetch TGZ                 copy the used SVGs + LICENSE out of a lucide-static or @tabler/icons
                                                tarball (SHA-256 pinned; parsed as data, nothing is executed)
       mod_icons.py --check [WORKDIR]           verify the asset PNGs (+ a work tree) against the stock pins
"""
import argparse, hashlib, io, math, os, re, shutil, stat, subprocess, sys, tarfile
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from modlib import clone_workdir, edit_ui, write_keep_mode
import pod_i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(ROOT, 'assets', 'icons', 'tabler')
SVG = os.path.join(ASSET, 'svg')                       # Tabler outline/ + filled/ (the 'T:' glyphs only)
PNG = os.path.join(ROOT, 'assets', 'icons', 'png')
IMG = 'rootfs/release/assets/default/raw/images/xx'
TGZ_SHA = 'aa3042907eb0bdb079fd70733e2d75f785683d4726279128a0ca2343099f7074'   # @tabler/icons 3.49.0
LUCIDE_SHA = '62773cd2ee411ad2e37c1973d1e4c4b49f9a6c57da6b5d5d0abca08756ba75f1'   # lucide-static 1.61.0
WHITE, DISC, DISC_DOWN, OFF = (255, 255, 255), (0x77,) * 3, (0x55,) * 3, (0x66,) * 3

# ---------------------------------------------------------------- mapping (stock image -> glyph)
# glyph: a Lucide name; 'T:name' = a Tabler glyph (Lucide has no match); '+name' = custom SVG in assets/icons/custom/
# drawn in the same style (no match in either set); 'name:filled' = the outline shapes filled solid (Tabler's own
# filled style for 'T:' names); 'badge:TEXT' = a text badge (Inter in a thin rounded rect, badge() below).
HOME = [  # Home ids 1..17 in English order, HiFi (id 0, zh_CN only) last
    ('tidal', 'TIDAL (online only)', 'T:brand-tidal'), ('sset_updatemusic', 'Update Library', 'refresh-cw'),
    ('mymusic', 'All Songs', 'music'), ('folder', 'Folders', 'folder'), ('album', 'Albums', 'disc-3'),
    ('songer', 'Artists', 'mic-vocal'), ('genre', 'Genres', 'guitar'), ('composer', 'Composers', 'feather'),
    ('hr', 'Hi-Res', '+badge-hr'), ('fav', 'Favorites', 'star'), ('many', 'Most Played', 'flame'),
    ('recent', 'Recently Played', 'history'), ('recentadd', 'Recently Added', 'clock-plus'),
    ('playlist', 'Playlists', 'list-music'), ('cdripper', 'CD Ripper', 'disc'), ('playset', 'Play Settings', 'sliders-horizontal'),
    ('sysset', 'System Settings', 'settings'), ('hifimusic', 'HiFi Store (zh_CN)', 'store'),
]
SETTINGS = [  # the 46 40x40 settings icons
    ('playset_foldercover', 'Folder cover', 'image'), ('pset_balance', 'Balance', 'scale'),
    ('pset_bootvol', 'Boot volume', 'volume-1'), ('pset_covermode', 'Cover mode', 'maximize'),
    ('pset_dac', 'DAC', 'badge:DAC'), ('pset_digital', 'Digital output', 'cable'),
    ('pset_dsdoutput', 'DSD output', 'badge:DSD'), ('pset_eq', 'Equalizer', 'sliders-vertical'),
    ('pset_filter', 'Digital filter', 'waves'), ('pset_gain', 'Gain', 'gauge'),
    ('pset_gapless', 'Gapless', 'infinity'), ('pset_jumpfolder', 'Jump folder', 'folder-output'),
    ('pset_maxvol', 'Max volume', 'volume-2'), ('pset_memplay', 'Resume play', 'bookmark'),
    ('pset_playmode', 'Play mode', 'repeat'), ('pset_replaygain', 'ReplayGain', 'badge:RG'),
    ('pset_usbaudiovol', 'USB audio volume', 'usb'), ('screensaver_info', 'Show info', 'info'),
    ('screensaver_timeshow', 'Show time', 'clock'), ('sset_about', 'About', 'info'),
    ('sset_atmosphereled', 'LED light', 'lightbulb'), ('sset_carmode', 'Car mode', 'car'),
    ('sset_covermode', 'Cover mode', 'maximize'), ('sset_display', 'Display', 'sun'),
    ('sset_doublewake', 'Double-tap wake', 'mouse-pointer-click'), ('sset_dsdoutput', 'DSD output', 'badge:DSD'),
    ('sset_keylock', 'Key lock', 'lock'), ('sset_lighttime', 'Backlight time', 'timer'),
    ('sset_netservice', 'Network services', 'globe'), ('sset_outputway', 'Output', 'headphones'),
    ('sset_powermanager', 'Power', 'power'), ('sset_prove', 'Certification', 'badge-check'),
    ('sset_screenlock', 'Screen lock', 'lock-keyhole'), ('sset_system', 'System update', 'circle-arrow-up'),
    ('sset_theme', 'Theme', 'palette'), ('sset_tswake', 'Touch wake', 'pointer'),
    ('sset_usbaudiovol', 'USB audio volume', 'usb'), ('sset_usbmode', 'USB mode', 'usb'),
    ('sset_wifiset', 'Wi-Fi', 'wifi'), ('system_formatcard', 'Format card', 'memory-stick'),
    ('system_language', 'Language', 'languages'), ('system_reset', 'Reset', 'rotate-ccw'),
    ('system_scrotate', 'Screen rotation', 'rotate-ccw-square'), ('system_time', 'Date & time', 'calendar'),
    ('system_update', 'Firmware update', 'download'), ('usb_chargeswitch', 'USB charging', 'battery-charging'),
]
PULLDOWN = {  # glyph per tile
    'drop_wifi': 'wifi', 'drop_bt': 'bluetooth', 'drop_keylock': 'lock', 'drop_eq': 'sliders-vertical',
    'drop_usbaudio': 'usb', 'drop_usbdac': '+dac', 'drop_usbstorage': 'hard-drive',
    'drop_playset': 'sliders-horizontal', 'drop_sysset': 'settings',
    'drop_lighticon0': 'sun-dim', 'drop_lighticon1': 'sun',
}
STATUS = {'bar_play': 'play', 'bar_pause': 'pause', 'bar_vol0': 'volume', 'bar_vol1': 'volume-1',
          'bar_vol2': 'volume-2', 'bar_vol3': '+volume-3waves', 'bar_vol4': 'volume-x', 'bar_wifi': 'wifi',
          'bar_bt': 'bluetooth', 'bar_digital': 'plug'}
WIFI_LEVELS = [None, 'wifi-zero', 'wifi-low', 'wifi-high', 'wifi']     # index = bar_wifi0..4
LISTS = [('icon_folder', 'folder', 'folder'), ('icon_playlist', 'playlist', 'list-music'),
         ('icon_artist', 'artist', 'mic-vocal'), ('icon_genre', 'genre', 'guitar'),
         ('icon_composer', 'composer', 'feather'), ('icon_cdalbum', 'album', 'disc-3')]
COVERS = ['albumcover_s', 'albumcover_m', 'albumcover_info']   # the "no cover" placeholder, 60/90/100 px
COVER_GLYPH, COVER_FRAC = 'disc-3', 0.52      # the glyph's px as a fraction of the tile
# The album page (patch/albumpage.c): the cover tint (ah_tint: a window sized black gradient, patch/offsets.inc AH_TINT_*; the cover's corners are
# cut by the payload, no masks); Shuffle's 40 px disc
# with its glyph (pressed one lighter) and the Play pill's play glyph (dark, 16 px, no padding); the pill itself is an image too (180 x 40,
# ah_pill / ah_pill_down, drawn centred in the 44 px high button, so the touch rectangle is taller than the pill). The sizes are AH_* in patch/offsets.inc (test/pod/albumpage.py checks them).
AH_TINT = (64, 200, 346, 450)   # alpha at the top row, at row AH_TINT_ROWS - 1 and below (the held deep tint, 78 % dark), the rows, the window height
ALBUM = ['ah_tint', 'ah_play', 'ah_shuffle', 'ah_shuffle_down', 'ah_pill', 'ah_pill_down', 'ah_wave']
AH_SHUF_DISC, AH_SHUF_DISC_DOWN, AH_SHUF_GLYPH, AH_DISC_PX = (0x2A,) * 3, (0x44,) * 3, 19, 40   # AH_DISC (patch/offsets.inc)
AH_PLAY_GLYPH, AH_PLAY_INK = 16, (0x14,) * 3
AH_PILL_PX, AH_PILL_FILL, AH_PILL_FILL_DOWN = (180, 40), (0xFF,) * 3, (0xBE,) * 3   # AH_PLAY_W x AH_PILL_H
DPAGE = ['dp_back', 'dp_back_down', 'dp_pill', 'dp_pill_down', 'dp_play', 'dp_add', 'dp_add_down', 'dp_added', 'dp_added_down']   # the Daily Mix page (patch/dailymix.c dp_*): the glass back disc (a white chevron), the white Play pill (pressed a light grey), its dark play glyph, the Add disc (Shuffle's disc and pressed colours, a plus: saves the mix as a playlist; a check once it is saved)
DP_BACK_PX, DP_BACK_GLYPH, DP_PILL_PX, DP_PILL_INK, DP_PILL_DOWN = 40, 20, (148, 40), AH_PLAY_INK, (0xD6, 0xD6, 0xD8)   # patch/offsets.inc DP_BACK_DISC, DP_PILL_H, DP_PLAY_W
DP_ADD_GLYPH = 'plus'
DP_ADDED_GLYPH = 'check'
DAILY = ['dm_disc', 'dm_disc_down'] + DPAGE   # the Daily Mix card's play disc and the page's images (DPAGE) (patch/dailymix.c, tools/pod_ui.py): a 48 px glass disc with a 22 px white play glyph, one px right of centre (a triangle's weight sits left of its box)
DM_DISC_PX, DM_PLAY_GLYPH = 48, 22     # patch/offsets.inc DM_DISC, tools/pod_dailymix.py DM_PLAY_GLYPH
# The iPod page's click wheel (patch/ipod.c, docs/modules/ipod.md): light/dark 220 px images, a ring with a 90 px centre button and the four labels drawn in; the corners are transparent
# (the window's colour shows). IP_WHEEL_D / IP_HUB_R in patch/offsets.inc are these numbers (test/pod/ipod.py checks them).
IPOD = ['ipod_wheel', 'ipod_wheel_dark', 'ipod_mode_shuffle', 'ipod_mode_repeat', 'ipod_mode_repeat1', 'ipod_playing', 'ipod_placeholder', 'ipod_podcasts']
IPOD_WHEEL_D, IPOD_HUB_R = 220, 45
IPOD_PC_PANE, IPOD_PC_GLYPH_Y = (160, 240), 104   # patch/offsets.inc IP_PANE_W x IP_PANE_H, IP_PC_GLYPH_Y: the main menu's Podcasts pane (patch/ipod.c ip_paint_pane)
IPOD_PLACEHOLDER = os.path.join(ROOT, 'assets', 'icons', 'ipod-placeholder-256.png')   # the user-supplied iTunes Cover Flow placeholder (1200 px), scaled once to 256 px with a good filter; the Pod's one cover for anything without art
IPOD_MODE_SRC = 32    # the Now Playing mode marks are drawn at 2 x (IP_MODE_PX = 16) and reduced by the payload (patch/offsets.inc)
IP_PLAY_SRC = 14
DAILY = DAILY + IPOD
# The Tape page (patch/tape.c, docs/modules/tape.md): the More dialog's row icon and the page's four pictures (tools/tape_art.py draws them; the page is landscape, the pictures are turned for the portrait panel).
import tape_art
TAPE = list(tape_art.NAMES)   # the page's pictures: tape_top and tape_screw shared, and tape_shell / tape_hubs / tape_marks for each theme (the row icon pod_ic_tape is a row image, installed with them)
DAILY = DAILY + TAPE
# The Vinyl page (patch/vinyl.c, docs/modules/vinyl.md): its seven pictures (tools/vinyl_art.py draws them; portrait, as the panel). The More sheet's row icon is pod_ic_vinyl.
import vinyl_art, png_pack
VINYL = list(vinyl_art.NAMES)
DAILY = DAILY + VINYL
# The Settings pages (tools/pod_settings.py, docs/modules/settings.md "Cards"): a 20 px glyph (CARD_GLYPH_PX, stroke 2) centred in a 24 px image on each row, by the row's label; the card's
# chevron (Lucide chevron-right fitted to 9 x 15, #777777, stroke 2) and the picker's check (20 px, white).
CARD_GLYPH_PX, CARD_CHEVRON, CARD_CHECK = 20, ('pod_chev', 10, 16, (0x8A,) * 3), ('pod_check', 20)
CARD_GLYPHS = {'Wi-Fi': 'wifi', 'Bluetooth': 'bluetooth', 'Home Screen': 'house', 'Library': 'disc-3', 'Now Playing': 'audio-lines',
               'Play Mode': 'repeat', 'EQ': 'sliders-vertical', 'All Playback Settings': 'headphones', 'Display': 'sun', 'Sample Rate RGB': 'lightbulb', 'Appearance': 'palette', 'Accent': 'palette', 'Background': '+contrast',
               'Control Center': 'layout-grid',
               'Keyboards': '+keyboard', 'About': 'info', 'All System Settings': 'settings', 'Developer': 'code', 'Main Menu': 'list-checks', 'Extras': 'ellipsis',
               'Recent Albums': 'history', 'Daily Mix': 'shuffle', 'Regenerate Daily Mix': 'refresh-cw', 'Update Library': 'refresh-cw',
               'Landscape': 'rotate-cw-square', 'Rebuild Covers': 'image-up', 'Theme': '+cassette-tape', 'Record': '+turntable', 'Base': 'palette', 'Boot to M1+ Music': 'power', 'Open Shanling Home': '@shanling', 'Equalizer': 'sliders-vertical',
               'Screenshot': 'camera', 'Clear Cover Cache': 'trash', 'Clear Track Durations': 'trash', 'Delete Unsupported Files': 'trash', 'Reset All Settings': 'rotate-ccw', 'Cache': 'hard-drive','Settings Files': 'file-cog', 'Download from AutoEq': 'download', 'Podcast Discover': 'compass', 'English': 'languages', 'Chinese (Pinyin)': 'languages', 'Battery Percentage': 'battery-charging'}


def card_name(g):
    """The image of a card row's glyph: pod_ci_<glyph>."""
    return 'pod_ci_' + g.lstrip('+@').replace('-', '_')


# A card is drawn by its rows (the stock list_view layouter stacks the scroll_view's children and ignores their y, so a card cannot be a view of its own: tools/pod_settings.py): the background of
# each row is one of four pieces, ROW_W x ROW_H with the card (x CARD_X .. CARD_X + CARD_W, fill CARD_RGB, corners CARD_R where the piece has them) drawn in and transparent outside, and the pressed
# twin (the lit grey). Names pod_cd_<piece>[_down]; the geometry is tools/pod_settings.py's (CARD_PIECE).
CARD_PIECE = {'ROW_W': 320, 'ROW_H': 52, 'CARD_X': 10, 'CARD_W': 300, 'CARD_R': 12, 'FILL': (0x1C,) * 3, 'LIT': (0x2C, 0x2C, 0x2E)}
CARD_PIECES = ('single', 'top', 'mid', 'bot')
CARD_PIECE_IMAGES = [f'pod_cd_{p}{d}' for p in CARD_PIECES for d in ('', '_down')]
CARD_TALL = 60   # the Presets page's rows (tools/pod_settings.py LIB_ROW_H): the same pieces, CARD_TALL high, pod_cdl_<piece>[_down]
CARD_TALL_IMAGES = [f'pod_cdl_{p}{d}' for p in CARD_PIECES for d in ('', '_down')]
# The Accent picker's swatches (docs/modules/accent.md): a round disc of accent i (tools/palette.py ACCENTS' order; Neutral is today's #EEEEEC fill) where a row's glyph goes, SWATCH_PX in the glyph's canvas.
SWATCH_PX = 20
SWATCHES = [f'pod_sw{i}' for i in range(7)]
CARD_IMAGES = sorted({card_name(g) for g in CARD_GLYPHS.values()}) + [CARD_CHEVRON[0], CARD_CHECK[0]] + CARD_PIECE_IMAGES + CARD_TALL_IMAGES + SWATCHES
# Find Cover & Lyrics' empty and failed states (docs/modules/onlineart.md): a muted grey glyph, ES_PX px, stroke 2, over the state's title (tools/pod_ui.py oa_es_icon; patch/onlineart.c names them)
ES_ICONS = {'pod_es_timer': 'timer', 'pod_es_music': 'music', 'pod_es_image': 'image', 'pod_es_wifi': 'wifi-low', 'pod_es_calendar': 'calendar', 'pod_es_lock': 'lock', 'pod_es_plug': 'plug',
            'pod_es_info': 'info', 'pod_es_card': 'memory-stick', 'pod_es_drive': 'hard-drive', 'pod_es_download': 'download', 'pod_es_check': 'badge-check'}
ES_PX, ES_RGB = 40, (0x8E, 0x8E, 0x93)
# The Wi-Fi page's network rows (patch/wifipage.c, docs/modules/wifi.md): a Wi-Fi fan signal glyph (wf_sig0..3: Lucide's wifi drawn whole in the dim grey, the level's arcs white over it: 3 wifi, 2 wifi-high, 1 wifi-low, 0 all dim; 20 x 16), the lock (16 px) and info (22 px)
# glyphs in the secondary grey, a white check (20 px; not the accent-tinted picker check) and eight frames of a small grey spinner (wf_spin0..7, 14 px: the header's while scanning, the check's place while joining).
WIFI_SIG_W, WIFI_SIG_H, WIFI_SIG_DIM, WIFI_GREY, WIFI_SPIN_PX = 20, 16, (0x55, 0x55, 0x59), (0xAA,) * 3, 14
WIFI_SIG_GLYPHS = {1: 'wifi-low', 2: 'wifi-high', 3: 'wifi'}     # the lit arcs of wf_sig1..3
WIFI_GLYPHS = {'wf_lock': ('lock', 16, WIFI_GREY), 'wf_info': ('info', 22, WIFI_GREY), 'wf_check': ('check', 20, WHITE),
               'wf_eye': ('eye', 22, WIFI_GREY), 'wf_eyeoff': ('eye-off', 22, WIFI_GREY)}   # the password page's show / hide button (eye: the password is hidden, a tap shows it)
WIFI_IMAGES = sorted(WIFI_GLYPHS) + [f'wf_sig{n}' for n in range(4)] + [f'wf_spin{i}' for i in range(8)]


def wifi_signal(lit):
    """WIFI_SIG_W x WIFI_SIG_H: Lucide's wifi fan, all of it in WIFI_SIG_DIM, with the arcs of level `lit` (WIFI_SIG_GLYPHS) white over it; 0 is all dim. The fan's ink is the same at every level, so the glyph does not move."""
    def fan(p):
        full = glyph('wifi', p, 'small', WIFI_SIG_DIM).copy()
        if lit: full.alpha_composite(glyph(WIFI_SIG_GLYPHS[lit], p, 'small'))
        return full
    return fit(fan, WIFI_SIG_W, WIFI_SIG_H, WIFI_SIG_W, 'c')


def wifi_spinner(i, ss=8):
    """WIFI_SPIN_PX square: a 280 degree arc 2.5 px wide in the secondary grey, turned i x 45 degrees."""
    from PIL import Image, ImageDraw
    n = WIFI_SPIN_PX * ss
    big = Image.new('L', (n, n), 0)
    ImageDraw.Draw(big).arc((int(1.25 * ss), int(1.25 * ss), n - int(1.25 * ss) - 1, n - int(1.25 * ss) - 1), 45 * i, 45 * i + 280, fill=255, width=int(2.5 * ss))
    im = Image.new('RGBA', (WIFI_SPIN_PX,) * 2, WIFI_GREY + (0,)); im.putalpha(big.resize((WIFI_SPIN_PX,) * 2, Image.LANCZOS)); return im


DAILY = DAILY + CARD_IMAGES + WIFI_IMAGES + ['pod_ic_tape', 'pod_ic_vinyl', 'pod_ic_art'] + sorted(ES_ICONS)   # (pod_ic_tape, pod_ic_vinyl: Now Playing's More sheet's Cassette Mode and Vinyl Mode rows, tools/mod_lists.py: no row page uses them)
# M1+ Music menu and Shuffle page rows: label -> (added image, glyph). A bare white glyph (BARE_PX canvas) left of the title.
# '@shanling' = the brand mark cut out of a stock image (shanling_mark below), not a glyph.
POD_ROWS = {'Now Playing': ('pod_ic_nowplaying', 'audio-lines'), 'Cover Flow': ('pod_ic_coverflow', '+coverflow'),   # audio-lines: the wave of the navbar's Now Playing button
            'Shuffle': ('pod_ic_shuffle', 'shuffle'), 'Songs': ('pod_ic_songs', 'music'),
            'Albums': ('pod_ic_albums', 'disc-3'), 'Artists': ('pod_ic_artists', 'mic-vocal'),
            'Genres': ('pod_ic_genres', 'guitar'), 'Folders': ('pod_ic_folders', 'folder'),
            'Playlists': ('pod_ic_playlists', 'list-music'), 'Navidrome': ('pod_ic_navidrome', 'disc-3'), 'Settings': ('pod_ic_prefs', 'sliders-horizontal'), 'Extras': ('pod_ic_extras', 'ellipsis'),
            'Shuffle Songs': ('pod_ic_shufsongs', 'music'), 'Shuffle Albums': ('pod_ic_shufalbums', 'disc-3'),
            'Shuffle Folders': ('pod_ic_shuffolders', 'folder'),
            # the Extras page (the stock Home tiles the menu does not repeat; glyphs as the Home grid's)
            'Favorites': ('pod_ic_fav', 'star'), 'Recently Added': ('pod_ic_recentadd', 'clock-plus'),
            'Recently Played': ('pod_ic_recent', 'history'), 'Most Played': ('pod_ic_most', 'flame'),
            'Composers': ('pod_ic_composers', 'feather'), 'Hi-Res': ('pod_ic_hires', '+badge-hr'),
            'Update Library': ('pod_ic_update', 'refresh-cw'), 'Tidal': ('pod_ic_tidal', 'T:brand-tidal'),
            'CD Ripper': ('pod_ic_cdripper', 'disc'), 'Pod': ('pod_ic_ipod', '+ipod'), 'Podcasts': ('pod_ic_podcasts', 'podcast'), 'Search': ('pod_ic_search', 'search'), 'Radio': ('pod_ic_radio', 'radio'),
            'Cassette Mode': ('pod_ic_tape', '+cassette-tape'), 'Vinyl Mode': ('pod_ic_vinyl', '+turntable'), 'Cover & Lyrics': ('pod_ic_art', '+cover-lyrics'),   # Now Playing's More sheet rows (tools/mod_lists.py)
            # the Control Center page (pod_pages.PULLDOWN_TILES): each tile's own glyph (PULLDOWN below); Output's tile shows the text PO / LO, so its row has stock's Output glyph (sset_outputway)
            'Wi-Fi': ('pod_ic_wifi', 'wifi'), 'Bluetooth': ('pod_ic_bt', 'bluetooth'), 'Button Lock': ('pod_ic_lock', 'lock'), 'Gain': ('pod_ic_gain', '+gain-high'),
            'USB Mode': ('pod_ic_usbmode', 'usb'), 'Output': ('pod_ic_output', 'headphones'), 'Playback': ('pod_ic_playset', 'sliders-horizontal'), 'System': ('pod_ic_sysset', 'settings')}
# The Folders page's row glyphs (patch/folders.c): the menu rows' bare white 24 px glyph for what POD_ROWS has no row for: an audio file, the SD card, a USB drive (folders, playlist files, the CD Library and the wave are pod_ic_folders, pod_ic_playlists, pod_ic_cdripper, pod_ic_nowplaying)
FOLDER_ROWS = {'fo_ic_file': 'file-music', 'fo_ic_sd': 'memory-stick', 'fo_ic_usb': 'usb'}
SUBSONIC_ICONS = {'pod_sb_sync': 'refresh-cw', 'pod_sb_download': 'download',
                  'pod_sb_dsd': 'badge:DSD'}
SUBSONIC_ART = ('pod_ic_navidrome_art', 'pod_ic_dsd_art')
SUBSONIC_ART_PX = 136
# The Radio page's row glyphs (patch/radiopage.c): bare white 24 px glyphs for Top Stations, By Country (flag), By Genre, Stations (radio) and Radio Browser (globe; Now Playing and Recently Played are the menu rows' pod_ic_nowplaying and pod_ic_recent);
# RADIO_ART is the radio-set glyph of the placeholders (the stations' tiles, the Now Playing page's art box, the mini bar): muted grey (ES_RGB), RADIO_ART_PX px.
RADIO_ROWS = {'pod_ic_rd_stations': 'radio-tower', 'pod_ic_rd_top': 'trending-up', 'pod_ic_rd_country': 'earth', 'pod_ic_rd_genre': 'tag', 'pod_ic_rd_browser': 'globe'}
RADIO_ART, RADIO_ART_PX = ('pod_ic_rd_art', '+radio-set'), 96   # custom radio-set (IconPark radio, Apache-2.0): every logo-less placeholder; the Pod menu's Radio row keeps Lucide radio
# The "M1+ Music" icon patch/home.c adds to the stock Home grid (id 99): 66x66 like the stock Home icons
# (white Lucide smartphone glyph on the #777777 disc, #555555 pressed), style home_m1plus_style in home_page.bin.
POD_HOME = ('m1plus', 'm1plus_down')
POD_HOME_GLYPH, POD_HOME_STYLE = 'smartphone', 'home_m1plus_style'
POD_UI = ['m1plus_menu', 'm1plus_shuffle', 'm1plus_extras', 'm1plus_mainmenu', 'm1plus_extrascfg', 'm1plus_pulldown']   # the pages whose rows get the 24 px row glyphs of POD_ROWS (the Settings pages' cards have their own, CARD_GLYPHS)
# The navbar toggles (tools/pod_ui.py NAV_VIEW_ICON, patch/albums.c, patch/artists.c): the glyph of the view a tap switches to, a plain
# 24 px white glyph like the navbar's others (pressed #777777), added to the images.
NAV_VIEW = {'pod_nav_grid': 'layout-grid', 'pod_nav_list': 'list',
            'pod_nav_gridl': 'layout-grid', 'pod_nav_listl': 'list',   # the same toggle as the left cap of [toggle | Now Playing] (the Radio search results, which have no Search button)
            'pod_nav_coverflow': '+coverflow',   # Lucide gallery-horizontal with shorter side covers
            'pod_nav_more': 'ellipsis',   # the Playlists page's "..." menu button
            'pod_nav_globe': 'globe',   # the Podcasts page's Apple Podcasts search, the capsule's left cap
            'pod_nav_moremid': 'ellipsis',   # the Podcasts page's "..." as the middle piece of [Globe | ... | Now Playing]
            'pod_nav_songs': 'list',   # Cover Flow's artist page: our Songs page on the artist's songs (the left cap, then Now Playing)
            'pod_nav_search': 'search',
            'pod_nav_listplus': 'list-plus',   # the Playlists page's actions card (New Playlist, Import, Export, Delete Playlists): the capsule's left cap at 168, Lucide list-plus = SF Symbols text.badge.plus
            'pod_nav_select': 'list-checks',   # the Songs page's Select button as the middle piece after Search / Cover Flow (the lists whose "..." card would hold Select alone)
            'pod_nav_selectl': 'list-checks',   # Select as the left cap of [Select | Now Playing] (the album page, the Folders page)
            'pod_nav_settings': 'sliders-horizontal',   # the Extras page's Settings button: the left cap of [Settings | Now Playing]
            'pod_nav_bprev': 'chevron-left', 'pod_nav_bnext': 'chevron-right'}   # the band page's Previous / Next band: the capsule [Previous | Next | Now Playing] (patch/peqband.c)
# the glass piece each Pod page button is (docs/modules/navbar.md): the Albums and Playlists pages' capsule is Cover Flow / "..." (left cap), the grid / list
# toggle (middle), Now Playing (right cap); the Artists page's is "..." (left cap) and Now Playing; the Cover Flow artist page's is Songs (left cap) and Now Playing
NAV_VIEW_POS = {'pod_nav_grid': 'middle', 'pod_nav_list': 'middle', 'pod_nav_gridl': 'left', 'pod_nav_listl': 'left', 'pod_nav_coverflow': 'left',
                'pod_nav_more': 'left', 'pod_nav_moremid': 'middle', 'pod_nav_globe': 'left', 'pod_nav_songs': 'left', 'pod_nav_search': 'left', 'pod_nav_listplus': 'left', 'pod_nav_select': 'middle', 'pod_nav_selectl': 'left', 'pod_nav_settings': 'left',
                'pod_nav_bprev': 'left', 'pod_nav_bnext': 'middle'}
NAV_PX = 24
# The Playlists page's "..." card's action rows (tools/pod_ui.py build_playlists_page: the shared view-sort card's slots 6..9, in row order): a bare white glyph left of the label, as on Now
# Playing's More sheet's rows, drawn at PL_MENU_PX (20: the 24 px of the sheet's rows looked big beside the 18 px labels; the stroke stays 2 px).
# New, Import, Export, Delete.
PL_MENU_PX = 20
PL_MENU_ICONS = (('pl_ic_new', 'list-plus'), ('pl_ic_import', 'file-input'), ('pl_ic_export', 'file-output'), ('pl_ic_delete', 'trash'))
# The track rows' "..." menu (patch/rowmenu.c, docs/modules/rowmenu.md; tools/pod_ui.py row_menu): bare BARE_PX glyphs as on Now Playing's More sheet's own rows (pod_ic_tape), Play Next, Play After, Add to Playlist; and
# the row's own "..." (RM_DOTS: the Lucide ellipsis, 24 px white on transparent; the payload makes it a RM_DOTS_RGB bitmap from the image's coverage and paints it at the right end of a track row)
RM_MENU_ICONS = (('rm_ic_next', 'list-start'), ('rm_ic_after', 'list-end'), ('rm_ic_add', 'list-plus'), ('rm_ic_fav', 'star'), ('rm_ic_info', 'info'))
RM_FAV_ON = ('rm_ic_unfav', 'star')   # Favorite's glyph while the track is a favourite (Undo Favorite): the same star filled solid; the payload swaps the row's image
RM_DOTS = ('rm_dots', 'ellipsis')
RM_DOTS_PX = 24
# Bare glyphs (no disc) on every list page: a BARE_PX canvas, stroke BARE_SW px absolute. The Pod rows' image is that
# canvas, x 16..40 in the 52 px row, vertically centred; the title starts at POD_TEXT_X and the 1 px #222222 hairline
# under each row starts there too (the pressed band stays full width). The stock settings pages keep their 40 x 40 images
# (labels at x 60) with the same glyph centred in them.
BARE_PX, BARE_SW = 24, 2.0
POD_ICON_X, POD_ICON = 16, BARE_PX
POD_TEXT_X = 56
HAIR_X, HAIR_COLOUR = POD_TEXT_X, '#222222'
ROW_STATES = ('normal', 'over', 'pressed', 'focused', 'disable')
CHEVRON, CHEVRON_DOWN = (0x8A,) * 3, (0x6E,) * 3     # every list chevron (stock right_arrow, the Main Menu's arrows): grey, darker pressed
# The status bar's Screenshot camera (patch/shot.c shows it while the 5 s countdown runs; tools/pod_ui.py adds the hidden widget): 16 px, white
SHOT_BAR = ('pod_bar_shot', 'camera')
SHOT_BAR_PX = 16
# The status bar's sync icon (patch/lineout.c shows it on every page while a cover or duration build runs; tools/statusbar.py adds the hidden widget pod_sync to both bar copies): Lucide refresh-cw, white, 18 x 18, 1.5 px stroke, static
SYNC_BAR = ('pod_bar_sync', 'refresh-cw')
SYNC_BAR_PX = 18
# The Home Made for You header's busy mark (patch/dailymix.c shows pod_dm_busy while a Daily Mix job runs): the same glyph in the secondary grey #AAAAAA, static, 16 px (about 14 px of ink, near the list chevron's 16 px height)
SYNC_DM = 'dm_sync'
SYNC_DM_PX = 16
# The status bar's Line Out pill (patch/lineout.c swaps it for stock's white "LO" text while Line Out is on): an amber #FFD60A (not the Accent Orange #FF9F0A) pill, fully rounded
# ends, black "LO" in Inter. A saturated image: Light Mode's flip (chroma over LIGHT_CHROMA) and the accent tints (named lists) leave it as drawn.
LO_BAR = 'pod_bar_lo'
LO_BAR_W, LO_BAR_H, LO_BAR_PX, LO_BAR_RGB = 26, 16, 12, (0xFF, 0xD6, 0x0A)

# ---- round 2 (docs/ui.md "Icon audit"): the stock images the pages and dialogs still showed.
# Plain glyph images at the stock size: white (pressed `_down`: #777777), no disc. 'name:filled' = the shapes filled
# (Tabler's own filled style for 'T:' names). (stock image, glyph, pressed image or None); each file keeps its own size.
GLYPHS = [
    # navbar actions and list affordances
    ('add', 'plus', 'add_down'), ('back_to_player', 'audio-lines', 'back_to_player_down'),
     ('cancel', 'x', 'cancel_down'), ('delete', 'trash', 'delete_down'),
    ('mulselect', 'list-checks', 'mulselect_down'), ('songsort', 'arrow-down-wide-narrow', 'songsort_down'),
    ('tidal_sort', 'arrow-down-wide-narrow', 'tidal_sort_down'), ('search', 'search', 'search_down'),
    ('return', 'chevron-left', 'return_down'), ('right_arrow', 'chevron-right', 'right_arrow_down'),
    ('list_more', 'ellipsis', 'list_moredown'), ('p_more', 'ellipsis', 'p_moredown'),
    ('dac_set', 'settings', 'dac_setdown'), ('rippersystem', 'settings', 'rippersystem_down'),
    ('expansion', 'chevron-down', 'expansion_down'), ('expansion_2', 'chevron-up', 'expansion_2_down'),
    ('albumsinger', 'disc-3', None), ('songsinger', 'music', None),
    ('p_random', 'shuffle', None), ('p_cycle', 'repeat', None), ('p_cycle1', 'repeat-1', None),    # the queue dialog's mode
    ('p_order', 'repeat-off', None),
    ('mulselected', 'T:circle-check:filled', None), ('selected', 'T:circle-check:filled', None),   # a filled disc with the tick cut out: Lucide has none
    ('screensaver_selected', 'T:circle-check:filled', None), ('unselect', 'circle', None),
    ('screensaver_unselect', 'circle', None), ('cdselected', 'square', None), ('selecting', 'square-check', None),
    # transport glyphs of the pages without the Now Playing look (Bluetooth receiver, USB DAC, AirPlay)
    ('play', 'play:filled', None), ('pause', 'pause:filled', None),
    ('next', 'skip-forward:filled', 'next_down'), ('prev', 'skip-back:filled', 'prev_down'),
    # actions in dialogs and pages
    ('rename', 'pencil', None), ('bt_del', 'trash', None), ('bt_scan', 'refresh-cw', None), ('datetime', 'calendar', None),
    ('wifi_add', 'circle-plus', None), ('kb_visible', 'eye', None), ('kb_invisible', 'eye-off', None),
    ('p_abrepeat', 'T:a-b', None), ('p_add', 'list-plus', None), ('p_delete', 'trash', None),    # a-b: no Lucide glyph (Playback speed: the Podcasts sheet's gauge)
    ('p_multiple', 'gauge', None), ('p_onlinesearch', 'globe', None),
    ('player_albuminfo', 'disc-3', None), ('player_songerinfo', 'mic-vocal', None),
    ('batchadd_fav', 'star', None), ('batchadd_playlist', 'list-plus', None),
]
GREY_GLYPHS = {'kb_visible': 0x8C, 'kb_invisible': 0x8C}     # the password eye was grey in stock
# Sizes of the glyph images (docs/ui.md): the ink box of the navbar and the other glyph buttons is 20 of the stock 22 px
# (stroke 2.0 px); the dialog glyphs 0.88 of their ink box; the selection marks 0.88 of their ink. Now Playing's
# back_to_player stays as it was.
NAV_K, DIALOG_K, MARK_K, GLYPH_SW = 20 / 22, 0.88, 0.88, 2.0
SMALL_GLYPHS = {'add', 'cancel', 'delete', 'mulselect', 'songsort', 'tidal_sort', 'search', 'return', 'right_arrow',
                'list_more', 'p_more', 'dac_set', 'rippersystem', 'expansion', 'expansion_2', 'albumsinger', 'songsinger',
                'p_random', 'p_cycle', 'p_cycle1', 'p_order'}
DIALOG_GLYPHS = {'rename', 'bt_del', 'bt_scan', 'datetime', 'wifi_add', 'kb_visible', 'kb_invisible', 'p_abrepeat', 'p_add',
                 'p_delete', 'p_multiple', 'p_onlinesearch', 'player_albuminfo', 'player_songerinfo', 'batchadd_fav', 'batchadd_playlist'}
MARK_GLYPHS = {'mulselected', 'selected', 'screensaver_selected', 'unselect', 'screensaver_unselect', 'cdselected', 'selecting'}
CHEVRONS = {'right_arrow', 'expansion', 'expansion_2'}      # the grey list chevrons (CHEVRON, pressed CHEVRON_DOWN)
# 40 x 40 images (Folders rows, Playlists page, the CD ripper's track dialog): bare glyphs, as the settings icons
FORMATS = ['aac', 'aiff', 'alac', 'ape', 'dff', 'dsf', 'dts', 'flac', 'iso', 'm4a', 'mp2', 'mp3', 'ogg', 'opus', 'wav', 'wma']
DISCS = [('icon_' + f, 'file-music') for f in FORMATS] + [
    ('icon_tf', 'memory-stick'), ('icon_otg', 'usb'), ('icon_cdgenres', 'guitar'), ('icon_cdsonger', 'mic-vocal'),
    ('icon_cdyears', 'calendar'), ('playlist_add', 'list-plus'), ('playlist_import', 'file-input'),
    ('playlist_export', 'file-output')]
# stock line art kept (instruments, text) and only recoloured white: the orange of the equaliser preset icons
RECOLOUR = ['eq_blues', 'eq_classical', 'eq_custom', 'eq_dance', 'eq_jazz', 'eq_metal', 'eq_pop', 'eq_rock', 'eq_vocal']
# playback-speed badges (36x20 text): grey outline, white when selected
SPEEDS = {'p_1': ('1.0X', 0), 'p_1_sel': ('1.0X', 1), 'p_1_25': ('1.25X', 0), 'p_1_25_sel': ('1.25X', 1),
          'p_1_5': ('1.5X', 0), 'p_1_5_sel': ('1.5X', 1), 'p_2': ('2.0X', 0), 'p_2_sel': ('2.0X', 1)}
PLAYALL = {'playall': 0, 'Play_all': 0, 'playall_down': 1, 'Play_all_down': 1}      # 90x28 "Play all" pills
WIFI_LOCK = {f'wifi_{i}': i for i in range(1, 5)}                                    # secured network, level 1..4
# Now Playing (mod_nowplaying.py copies these): name -> (glyph, canvas px or (w, h), max ink px, tone, pressed name or None
# [, disc px]). 'pil:NAME' = the solid glyph drawn with PIL (g_play ... below; the transport glyphs, which read better than
# Tabler's filled ones); a disc px puts a flat translucent white disc of that diameter behind the glyph (star and More).
NP = {'np_play': ('pil:play', 44, 0, 'fg', 'np_play_down'), 'np_pause': ('pil:pause', 44, 0, 'fg', 'np_pause_down'),
      'np_next': ('pil:next', 44, 0, 'fg', 'np_next_down'), 'np_prev': ('pil:prev', 44, 0, 'fg', 'np_prev_down'),
      'mb_play': ('pil:mb_play', 32, 0, 'white', 'mb_play_down'), 'mb_pause': ('pil:mb_pause', 32, 0, 'white', 'mb_pause_down'),
      'mb_stop': ('pil:mb_stop', 32, 0, 'white', 'mb_stop_down'),   # the play/pause slot while a station connects or plays (patch/minibar.c mb_glyph): a tap stops
      'mb_next': ('pil:mb_next', (34, 24), 0, 'white', 'mb_next_down'),
      'mb_next_off': ('pil:mb_next', (34, 24), 0, 'off', None),   # the next button while a station owns the bar (patch/minibar.c mb_next_look): NP_OFF grey, inert
      'mb_glass': ('pil:glass', (304, 56), 0, 'fg', 'mb_glass_down'),
      'lk_card': ('pil:glass_card', (288, 334), 0, 'fg', None),
      'pm_sheet': ('pil:glass_sheet', (320, 250), 0, 'fg', None), 'pm_sheet6': ('pil:glass_sheet6', (320, 300), 0, 'fg', None),
      'pl_glass': ('pil:glass_menu', (72, 200), 0, 'fg', None),
      'vs_glass7': ('pil:glass_viewsort', (72, 336), 0, 'fg', None), 'vs_glass6': ('pil:glass_viewsort6', (72, 288), 0, 'fg', None),
      'vs_glass5': ('pil:glass_viewsort5', (72, 240), 0, 'fg', None), 'vs_glass4': ('pil:glass_viewsort4', (72, 192), 0, 'fg', None), 'vs_glass1': ('pil:glass_viewsort1', (72, 48), 0, 'fg', None),
      'vs_glass3': ('pil:glass_viewsort3', (72, 144), 0, 'fg', None), 'vs_glass2': ('pil:glass_viewsort2', (72, 96), 0, 'fg', None),
      'rm_glass': ('pil:glass_rowmenu', (320, 150), 0, 'fg', None),
      'pq_glass': ('pil:glass_peqdialog', (72, 276), 0, 'fg', None),   # the band page's unsaved-changes dialog (patch/peqband.c): the Playlists menu's glass (patch3_x), 76 px of head and four 50 px buttons high
      'bk_glass': ('pil:glass_bandkeypad', (320, 320), 0, 'fg', None),   # the band page's number keypad sheet (patch/peqband.c): the sheet's glass, 320 px high, top corners only
      'np_grabber': ('pil:grabber', (120, 44), 0, 'ghost', 'np_grabber_down'),
      'np_row_playing': ('pil:wave', (40, 20), 0, 'fg', None),
      'rn_play': ('pil:play', 64, 0, 'white', 'rn_play_down'), 'rn_stop': ('pil:stop', 64, 0, 'white', 'rn_stop_down'),   # Radio Now Playing's one large button (patch/radionp.c)
      'np_random': ('shuffle', 30, 18, 'mid', None), 'np_cycle': ('repeat', 30, 18, 'mid', None),
      'np_cycle1': ('repeat-1', 30, 18, 'mid', None), 'np_order': ('repeat-off', 30, 18, 'off', None),
      'np_fav': ('star:filled', 44, 18, 'fg', None, 32), 'np_unfav': ('star', 44, 18, 'fg', 'np_unfav_down', 32),
      'np_save': ('bookmark:filled', 44, 18, 'fg', None, 32), 'np_unsave': ('bookmark', 44, 18, 'fg', 'np_unsave_down', 32),   # an episode's favourite button (docs/modules/podcasts.md "Saved")
      'np_more': ('ellipsis', 44, 18, 'fg', 'np_more_down', 32), 'np_playqueue': ('list-music', 30, 18, 'mid', 'np_playqueue_down')}
NP_FG, NP_DIM = (0xEE, 0xEE, 0xEC), (0x8C,) * 3        # q2-pod's off-white and its muted pressed grey
NP_MID, NP_OFF = (0xC8,) * 3, (0x6E,) * 3               # the mode and queue glyphs (brighter than the secondary grey #AAAAAA); repeat-off, dimmer
NP_TONES = {'fg': (NP_FG, 255), 'mid': (NP_MID, 255), 'off': (NP_OFF, 255), 'ghost': ((255, 255, 255), 110), 'white': ((255, 255, 255), 255)}   # rgb, alpha
NP_PRESSED = {'ghost': ((255, 255, 255), 190), 'white': ((255, 255, 255), 140)}            # every other tone presses to NP_DIM
NP_DISC_ALPHA, NP_DISC_ALPHA_DOWN = 26, 51                # the star and More disc: #FFFFFF1A, pressed #FFFFFF33

SHANLING = '@shanling'

def gname(g): return g.lstrip('+').split(':')[0] if not g.startswith('T:') else 'T:' + g.split(':')[1]   # 'T:x' keeps its prefix
def is_custom(g): return g.startswith('+')
def is_tabler(g): return g.startswith('T:')
def is_filled(g): return g.endswith(':filled')
def is_badge(g): return g.startswith('badge:')

def used_glyphs():
    """(Lucide names, Tabler names) of every glyph the tables use; custom ones excluded."""
    gl = [e[2] for e in HOME + SETTINGS + LISTS] + list(PULLDOWN.values()) + list(STATUS.values()) + \
        [g for g in WIFI_LEVELS if g] + [COVER_GLYPH, POD_HOME_GLYPH, SHOT_BAR[1], SYNC_BAR[1]] + list(NAV_VIEW.values()) + list(SUBSONIC_ICONS.values()) + [g for _, g in PL_MENU_ICONS] + [g for _, g in RM_MENU_ICONS] + [RM_FAV_ON[1]] + [RM_DOTS[1]] + list(ES_ICONS.values()) + [v[1] for v in POD_ROWS.values() if v[1] != SHANLING] + list(FOLDER_ROWS.values()) + list(RADIO_ROWS.values()) + [RADIO_ART[1]] + [g for g in CARD_GLYPHS.values() if g != SHANLING] + \
        [g for _, g, _ in GLYPHS] + [v[0] for v in SONGS_IMAGES.values()] + [v[0] for v in KEYBOARD_IMAGES.values()] + [KB_CLEAR[1], DP_ADD_GLYPH] + list(PC_GLYPHS) + [g for _, g in DISCS] + [v[0] for v in NP.values() if not v[0].startswith('pil:')] + ['lock:filled'] + R3_GLYPHS
    names = {gname(g) for g in gl if g and not is_custom(g) and not is_badge(g)}
    return sorted(n for n in names if not n.startswith('T:')), sorted(n[2:] for n in names if n.startswith('T:'))

# ---------------------------------------------------------------- SVG -> RGBA (generation only)
TAGS = {'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'ellipse'}
ATTRS = {'d', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height', 'x1', 'y1', 'x2', 'y2', 'points',
         'fill-rule', 'clip-rule', 'transform'}
SAFE = re.compile(r'^[0-9A-Za-z.,\-+ ()#%]*$')

def parse_svg(path):
    """Shapes of a Lucide / Tabler SVG as data: [(tag, attrs)]; only whitelisted tags/attributes survive."""
    els = []
    for e in ET.parse(path).getroot().iter():
        tag = e.tag.split('}')[-1]
        if tag not in TAGS: continue
        a = {k.split('}')[-1]: v for k, v in e.attrib.items()}
        if a.get('stroke') == 'none' and a.get('fill') == 'none': continue      # the 24x24 bounding box
        els.append((tag, {k: v for k, v in a.items() if k in ATTRS and SAFE.match(v) and 'url' not in v.lower()}))
    return els

CUSTOM = os.path.join(ROOT, 'assets', 'icons', 'custom')
LUCIDE = os.path.join(ROOT, 'assets', 'icons', 'lucide')    # lucide-static 1.61.0 (ISC), npm tarball SHA-256 LUCIDE_SHA
LUCIDE_SVG = os.path.join(LUCIDE, 'svg')
def svg_path(name, style='outline'):
    if name.startswith('T:'): return os.path.join(SVG, style, name[2:] + '.svg')
    for d in (CUSTOM, LUCIDE_SVG):
        c = os.path.join(d, name + '.svg')
        if os.path.isfile(c): return c
    raise FileNotFoundError(name)

def build_svg(name, style, px, sw, solid, dx=0.0, dy=0.0, margin=0):
    """margin: extra px on every side of the px x px glyph canvas (the image is px + 2 margin wide, the glyph scale unchanged)."""
    els = parse_svg(svg_path(name, style))
    solid = solid or name == 'ellipsis'      # Lucide's dots are r=1 circles: filled, they stay solid at any size (outlined, they go hollow when large)
    col = '#FFFFFF'
    if style == 'filled': g = f'fill="{col}"'
    else: g = (f'fill="{col if solid else "none"}" stroke="{col}" stroke-width="{sw}" '
               'stroke-linecap="round" stroke-linejoin="round"')
    body = ''.join('<%s %s/>' % (t, ' '.join(f'{k}="{v}"' for k, v in a.items())) for t, a in els)
    tx, ty = dx * 24 / px, dy * 24 / px
    m, tot = margin * 24 / px, px + 2 * margin
    vb = f'{-m:.6f} {-m:.6f} {24 + 2 * m:.6f} {24 + 2 * m:.6f}' if margin else '0 0 24 24'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{tot}" height="{tot}" viewBox="{vb}">'
            f'<g transform="translate({tx:.4f} {ty:.4f})" {g}>{body}</g></svg>')

RSVG_CACHE = os.path.join(paths.ROOT, 'work', 'cache', 'rsvg')   # rsvg-convert's PNG by (version, svg, px), beside work/cache/build; M1_NO_CACHE skips it
_rsvg_version = None

def _rsvg(svg, px):
    global _rsvg_version
    from PIL import Image
    if _rsvg_version is None:
        _rsvg_version = subprocess.run(['rsvg-convert', '--version'], capture_output=True, check=True).stdout
    key = hashlib.sha256(b'\0'.join((_rsvg_version, svg.encode(), str(px).encode()))).hexdigest()
    path = os.path.join(RSVG_CACHE, key[:2], key + '.png')
    if os.environ.get('M1_NO_CACHE') or not os.path.isfile(path):
        png = subprocess.run(['rsvg-convert', '-w', str(px), '-h', str(px), '-f', 'png'], input=svg.encode(),
                             capture_output=True, check=True).stdout
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'wb') as f: f.write(png)
        os.replace(tmp, path)   # atomic: parallel tests may render the same glyph
    else:
        png = open(path, 'rb').read()
    return Image.open(io.BytesIO(png)).convert('RGBA')

def _crisp(im):
    a = im.getchannel('A').tobytes(); tot = sum(a) or 1
    return sum(v * v for v in a) / (255.0 * tot)       # 1.0 = every inked pixel fully opaque

_rc = {}
def render(name, px, style='outline', sw=2, solid=False):
    """White glyph px x px; sub-pixel offset (<= 0.5 px) chosen for the crispest edges, no hinting."""
    k = (name, px, style, sw, solid)
    if k not in _rc:
        steps = (0, 0.25, 0.5, -0.25) if px <= 24 else (0, 0.5)
        best = None
        for dx in steps:
            for dy in steps:
                im = _rsvg(build_svg(name, style, px, sw, solid, dx, dy), px)
                c = _crisp(im) - 0.002 * (abs(dx) + abs(dy))      # tie-break toward the centre
                if best is None or c > best[0]: best = (c, im)
        _rc[k] = best[1]
    return _rc[k]

def tint(im, rgb):
    from PIL import Image
    out = Image.new('RGBA', im.size, rgb + (0,)); out.putalpha(im.getchannel('A')); return out

DISC_SW = 1.75      # stroke (24 grid units) of the glyphs on the 66 px Home discs

def glyph(g, px, ctx, rgb=WHITE):
    """ctx: 'disc' stroke 1.75 (the Home discs); 'bare' BARE_SW px absolute (the list icons); 'tile'/'cover' stroke 2
    (pull-down ring, no-cover tile); 'solid' filled shapes, 1.5 px absolute at <= 16 px, 2 px above; 'small' 1.5 px
    absolute at <= 16 px, 2 px above."""
    n = gname(g)
    if ctx == 'solid': im = render(n, px, 'outline', 1.5 * 24 / px if px <= 16 else 2, True)
    elif ctx == 'small': im = render(n, px, 'outline', 1.5 * 24 / px if px <= 16 else 2)
    elif ctx == 'disc': im = render(n, px, 'outline', DISC_SW)
    elif ctx == 'bare': im = render(n, px, 'outline', BARE_SW * 24 / px)
    else: im = render(n, px, 'outline', 2)
    return tint(im, rgb) if rgb != WHITE else im

def ink_crop(im):
    bb = im.getchannel('A').getbbox(); return im.crop(bb) if bb else im

def fit(fn, cw, ch, start, align='c'):
    """fn(px) -> glyph; the largest px <= start whose ink fits cw x ch, placed in a cw x ch canvas."""
    from PIL import Image
    px = start
    while True:
        g = ink_crop(fn(px))
        if (g.width <= cw and g.height <= ch) or px <= 8: break
        px -= 1
    c = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    x = cw - g.width if align == 'r' else (0 if align == 'l' else (cw - g.width) // 2)
    c.alpha_composite(g, (x, (ch - g.height) // 2)); return c

# The Shanling mark for the "Shanling Home" row: the brand's own swoosh from the stock shutdown screen
# (images/xx/shutdown.png, white on a blue shape above the SHANLING wordmark), isolated by whiteness (min of r, g, b:
# the blue shape is far from white), scaled to MARK_W px wide and thickened (the swoosh is a hairline in the stock art:
# a bare glyph needs the weight of the Lucide strokes, about 2 px) by a round dilation of MARK_DIL px; white on
# transparent. The stock file is pinned.
SHUTDOWN_SHA = 'b5133684f5f6100415161b5722b63cab1c0123538f3de440e2725e3c5f3dbc6e'
SHUTDOWN_CROP = (92, 144, 228, 216)     # the mark, without the wordmark below it (starts at y 217)
MARK_W, MARK_DIL, MARK_SS = BARE_PX, 1.5, 4      # ink width of the result; px the strokes grow; supersampling

def shanling_mark():
    from PIL import Image, ImageChops, ImageOps
    path = os.path.join(find_stock_img(), 'shutdown.png')
    assert sha256(open(path, 'rb').read()) == SHUTDOWN_SHA, 'shutdown.png is not the pinned stock file'
    rgb = Image.open(path).convert('RGB').crop(SHUTDOWN_CROP)
    big = rgb.resize((rgb.width * 4, rgb.height * 4), Image.LANCZOS)
    r, g, bl = big.split()
    mask = ImageChops.darker(ImageChops.darker(r, g), bl).point(lambda v: max(0, min(255, (v - 110) * 255 // 110)))
    mask = mask.crop(mask.getbbox())
    w0 = (MARK_W - MARK_DIL) * MARK_SS                # the width the swoosh has before it grows by MARK_DIL on each axis
    mask = mask.resize((round(w0), round(mask.height * w0 / mask.width)), Image.LANCZOS)
    rad = MARK_DIL * MARK_SS / 2; n = int(rad) + 1
    mask = ImageOps.expand(mask, n); grown = mask
    for dy in range(-n, n + 1):
        for dx in range(-n, n + 1):
            if dx * dx + dy * dy <= rad * rad + 0.01: grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
    grown = grown.crop(grown.getbbox())
    mask = grown.resize((MARK_W, max(1, round(grown.height * MARK_W / grown.width))), Image.BOX)
    im = Image.new('RGBA', mask.size, WHITE + (0,)); im.putalpha(mask); return im

# A text badge (DAC, DSD, RG: the stock discs of the DAC / DSD output / ReplayGain settings, redrawn bare): white Inter
# text in a thin rounded rectangle, the weight of the Lucide strokes at that size; BADGE_W x BADGE_H ink.
BADGE_W, BADGE_H, BADGE_SW, BADGE_R, BADGE_PAD = BARE_PX, 16, 1.5, 3.5, 1.5

def badge(text, ss=8, size=(BADGE_W, BADGE_H), font_px=14, stroke=BADGE_SW, radius=BADGE_R, pad=BADGE_PAD):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    big = Image.new('L', (w * ss, h * ss), 0); d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=255)
    i = stroke * ss
    d.rounded_rectangle((i, i, w * ss - 1 - i, h * ss - 1 - i), radius=max(0, radius - stroke) * ss, fill=0)
    room = (w - 2 * (stroke + pad)) * ss
    px = font_px
    while True:                                     # the largest text that clears the outline by BADGE_PAD
        f = ImageFont.truetype(TILE_FONT, px * ss); bb = f.getbbox(text, stroke_width=ss // 8)
        if bb[2] - bb[0] <= room or px <= 6: break
        px -= 1
    d.text(((w * ss - (bb[2] - bb[0])) // 2 - bb[0], (h * ss - (bb[3] - bb[1])) // 2 - bb[1]), text, font=f, fill=255, stroke_width=ss // 8)
    im = Image.new('RGBA', (w, h), WHITE + (0,)); im.putalpha(big.resize((w, h), Image.BOX)); return im

def lo_pill(ss=8):
    from PIL import Image, ImageDraw, ImageFont
    w, h = LO_BAR_W, LO_BAR_H
    mask = Image.new('L', (w * ss, h * ss), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss / 2, fill=255)
    txt = Image.new('L', (w * ss, h * ss), 0); f = ImageFont.truetype(TILE_FONT, LO_BAR_PX * ss); sw = ss // 3
    bb = f.getbbox('LO', stroke_width=sw)
    ImageDraw.Draw(txt).text(((w * ss - (bb[2] - bb[0])) // 2 - bb[0], (h * ss - (bb[3] - bb[1])) // 2 - bb[1]), 'LO', font=f, fill=255, stroke_width=sw)
    amber = Image.new('RGBA', (w * ss, h * ss), LO_BAR_RGB + (255,))
    black = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 255)); amber.paste(black, (0, 0), txt)
    amber.putalpha(mask)
    return amber.resize((w, h), Image.BOX)

def bare_icon(g, canvas):
    """The bare glyph g (a Lucide / Tabler name, '+custom', 'badge:TEXT' or the Shanling mark) centred in a canvas x canvas
    transparent image."""
    from PIL import Image
    gi = badge(g[6:]) if is_badge(g) else shanling_mark() if g == SHANLING else glyph(g, BARE_PX, 'bare')
    c = Image.new('RGBA', (canvas, canvas), WHITE + (0,)); c.alpha_composite(gi, ((canvas - gi.width) // 2, (canvas - gi.height) // 2)); return c

def card_piece(piece, lit=False, ss=8, tall=False):
    """One row's slice of a card: single (all four corners rounded), top (the upper two), mid (none) or bot (the lower two), anti-aliased, transparent outside the card; tall: CARD_TALL high."""
    from PIL import Image, ImageDraw
    c = CARD_PIECE; w, h, x0, cw, r = c['ROW_W'], CARD_TALL if tall else c['ROW_H'], c['CARD_X'], c['CARD_W'], c['CARD_R']
    big = Image.new('L', (w * ss, h * ss), 0); d = ImageDraw.Draw(big)
    box = (x0 * ss, 0, (x0 + cw) * ss - 1, h * ss - 1)
    rounded = {'single': (True, True, True, True), 'top': (True, True, False, False), 'mid': (False,) * 4, 'bot': (False, False, True, True)}[piece]
    d.rounded_rectangle(box, r * ss, fill=255, corners=rounded)
    im = Image.new('RGBA', (w, h), (c['LIT'] if lit else c['FILL']) + (0,)); im.putalpha(big.resize((w, h), Image.LANCZOS)); return im

def swatch(i):
    """The Accent picker's swatch i: an antialiased disc (4 x 4 samples per pixel) of SWATCH_PX in a POD_ICON canvas, in the accent's colour (Neutral: #EEEEEC)."""
    from PIL import Image, ImageDraw
    import palette
    rgb = palette.NEUTRAL_FILL if i == 0 else palette.ACCENT_RGB[palette.ACCENTS[i]]
    ss = 8; big = Image.new('L', (POD_ICON * ss,) * 2, 0)
    o = (POD_ICON - SWATCH_PX) * ss // 2
    ImageDraw.Draw(big).ellipse((o, o, o + SWATCH_PX * ss - 1, o + SWATCH_PX * ss - 1), fill=255)
    im = Image.new('RGBA', (POD_ICON,) * 2, tuple(rgb) + (0,)); im.putalpha(big.resize((POD_ICON,) * 2, Image.LANCZOS)); return im


def card_icon(g):
    """A Settings card row's glyph: the glyph at CARD_GLYPH_PX (stroke 2) centred in a POD_ICON canvas; a badge and the Shanling mark keep their size."""
    from PIL import Image
    if is_badge(g) or g == SHANLING: return bare_icon(g, POD_ICON)
    gi = glyph(g, CARD_GLYPH_PX, 'bare'); c = Image.new('RGBA', (POD_ICON,) * 2, WHITE + (0,))
    c.alpha_composite(gi, ((POD_ICON - gi.width) // 2, (POD_ICON - gi.height) // 2)); return c

POD_CHEV_W, POD_CHEV_H = 10, 16

def pod_chevron(rgb, canvas=None):
    """patch/common.c pod_make_chevron, pixel for pixel: a two segment stroke 2 px wide, 4 x 4 samples per pixel (integer eighths of
    a pixel), POD_CHEV_W x POD_CHEV_H. `canvas` (w, h) puts it right aligned and vertically centred on a larger transparent canvas."""
    from PIL import Image
    def seg2(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay; n = (px - ax) * dx + (py - ay) * dy; d = dx * dx + dy * dy
        if n <= 0: return (px - ax) ** 2 + (py - ay) ** 2
        if n >= d: return (px - bx) ** 2 + (py - by) ** 2
        cr = (px - ax) * dy - (py - ay) * dx
        return cr * cr // d
    im = Image.new('RGBA', (POD_CHEV_W, POD_CHEV_H), tuple(rgb) + (0,))
    for y in range(POD_CHEV_H):
        for x in range(POD_CHEV_W):
            n = 0
            for i in range(4):
                for j in range(4):
                    sx, sy = x * 8 + 2 * j + 1, y * 8 + 2 * i + 1
                    if min(seg2(sx, sy, 14, 14, 68, 64), seg2(sx, sy, 68, 64, 14, 114)) <= 64: n += 1
            im.putpixel((x, y), tuple(rgb) + (n * 255 // 16,))
    if canvas:
        c = Image.new('RGBA', canvas, tuple(rgb) + (0,)); c.paste(im, (canvas[0] - POD_CHEV_W, (canvas[1] - POD_CHEV_H) // 2)); im = c
    return im

def disc(size, rgb, ss=4):
    from PIL import Image, ImageDraw
    big = Image.new('L', (size * ss, size * ss), 0)
    ImageDraw.Draw(big).ellipse((0, 0, size * ss - 1, size * ss - 1), fill=255)
    im = Image.new('RGBA', (size, size), rgb + (0,)); im.putalpha(big.resize((size, size), Image.LANCZOS)); return im

def pill(size, rgb, ss=4):
    """A stadium (full round ends) of size (w, h), anti-aliased like disc()."""
    from PIL import Image, ImageDraw
    w, h = size
    big = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss // 2, fill=255)
    im = Image.new('RGBA', (w, h), rgb + (0,)); im.putalpha(big.resize((w, h), Image.LANCZOS)); return im

def on_disc(g, size, rgb):
    d = disc(size, rgb); d.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2)); return d

# glyph canvas on the Home discs (the 24 grid has 2 px padding, so the ink is about 5/6 of it): 38 px on the 66 px discs
HOME_GLYPH = 38

# ---- round 2: plain glyph images (no disc) at an exact canvas size
def fit_px(n, style, solid, cw, ch, pad, sw_px):
    """The largest canvas px whose glyph `n` (absolute stroke sw_px) has its ink inside (cw - 2 pad) x (ch - 2 pad)."""
    lo, hi = 8, 120
    while lo < hi:
        mid = (lo + hi + 1) // 2; bb = _rsvg(build_svg(n, style, mid, sw_px * 24 / mid, solid), mid).getchannel('A').getbbox()
        if bb and bb[2] - bb[0] <= cw - 2 * pad and bb[3] - bb[1] <= ch - 2 * pad: lo = mid
        else: hi = mid - 1
    return lo

def glyph_fit(g, cw, ch, rgb=WHITE, pad=1, stroke=None):
    """Glyph g ('name', 'name:filled' or 'T:name') as the largest glyph whose ink fits (cw - 2 pad) x (ch - 2 pad),
    absolute stroke 2 px (1.5 px on canvases under 22 px, or `stroke`), centred in a transparent cw x ch canvas. ':filled' is
    Tabler's filled style for 'T:' names and the Lucide outline shapes filled solid otherwise."""
    from PIL import Image
    n, filled = gname(g), is_filled(g)
    tabler_filled = filled and is_tabler(g)
    style = 'filled' if tabler_filled else 'outline'
    solid = filled and not tabler_filled
    sw_px = stroke or (2.0 if min(cw, ch) >= 22 else 1.5)
    lo = fit_px(n, style, solid, cw, ch, pad, sw_px)
    ink = ink_crop(render(n, lo, style, sw_px * 24 / lo, solid))
    c = Image.new('RGBA', (cw, ch), (0, 0, 0, 0)); c.alpha_composite(ink, ((cw - ink.width) // 2, (ch - ink.height) // 2))
    return tint(c, rgb) if rgb != WHITE else c

def glyph_box(g, canvas, k, rgb=WHITE, stroke=GLYPH_SW):
    """Glyph g fitted into the stock glyph box (the canvas less its 1 px pad, 6 px on canvases of 48 px and up) scaled by k,
    stroke `stroke` px absolute, centred in a transparent canvas (cw, ch)."""
    from PIL import Image
    cw, ch = canvas; pad = 6 if min(cw, ch) >= 48 else 1
    bw, bh = max(4, round((cw - 2 * pad) * k)), max(4, round((ch - 2 * pad) * k))
    c = Image.new('RGBA', canvas, (0, 0, 0, 0)); c.alpha_composite(glyph_fit(g, bw, bh, rgb, 0, stroke), ((cw - bw) // 2, (ch - bh) // 2)); return c

def glyph_mark(g, canvas, k, rgb=WHITE, stroke=GLYPH_SW):
    """A selection mark: the stock-size glyph's ink scaled by k (same canvas, centred; 1.5 px stroke when the ink is under 14 px)."""
    from PIL import Image
    ink = glyph_fit(g, *canvas, rgb, 1).getchannel('A').getbbox()
    tw, th = max(6, round((ink[2] - ink[0]) * k)), max(6, round((ink[3] - ink[1]) * k))
    c = Image.new('RGBA', canvas, (0, 0, 0, 0))
    c.alpha_composite(glyph_fit(g, tw, th, rgb, 0, stroke if min(tw, th) >= 14 else 1.5), ((canvas[0] - tw) // 2, (canvas[1] - th) // 2)); return c

def recolour_white(path):
    """A stock image's alpha as a white glyph: the line art kept, the orange gone."""
    from PIL import Image
    a = Image.open(path).convert('RGBA').getchannel('A')
    im = Image.new('RGBA', a.size, (255, 255, 255, 0)); im.putalpha(a); return im

def speed_badge(label, selected, size=(36, 20), ss=4):
    from PIL import Image, ImageDraw, ImageFont
    w, h = size; col = WHITE if selected else (0x77,) * 3
    big = Image.new('L', (w * ss, h * ss), 0); d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=4 * ss, fill=255)
    d.rounded_rectangle((ss, ss, (w - 1) * ss - 1, (h - 1) * ss - 1), radius=3 * ss, fill=0)
    px = 12
    while True:                                     # the largest text that clears the 1 px outline by 3 px
        f = ImageFont.truetype(TILE_FONT, px * ss); bb = f.getbbox(label)
        if bb[2] - bb[0] <= (w - 8) * ss or px <= 8: break
        px -= 1
    d.text(((w * ss - (bb[2] - bb[0])) // 2 - bb[0], (h * ss - (bb[3] - bb[1])) // 2 - bb[1]), label, font=f, fill=255)
    im = Image.new('RGBA', size, col + (0,)); im.putalpha(big.resize(size, Image.LANCZOS)); return im

PILL_GLYPH = 10      # the play glyph's px in the pill

def play_all_pill(pressed, size=(90, 28), ss=4):
    """The Play all button: off-white pill, dark text and play glyph (pressed: #8C8C8C). q2-pod's pill, Inter text."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = size; bg = NP_DIM if pressed else NP_FG; ink = (0x14,) * 3
    big = Image.new('L', (w * ss, h * ss), 0); ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss // 2, fill=255)
    im = Image.new('RGBA', size, bg + (0,)); im.putalpha(big.resize(size, Image.LANCZOS))
    play = glyph_fit('play:filled', PILL_GLYPH, PILL_GLYPH, ink, 0)
    f = ImageFont.truetype(TILE_FONT, 14); bb = f.getbbox('Play all'); tw = bb[2] - bb[0]
    x0 = (w - (play.width + 6 + tw)) // 2
    im.alpha_composite(play, (x0, (h - play.height) // 2))
    m = Image.new('L', size, 0); ImageDraw.Draw(m).text((x0 + play.width + 6 - bb[0], (h - (bb[3] - bb[1])) // 2 - bb[1]), 'Play all', font=f, fill=255)
    t = Image.new('RGBA', size, ink + (0,)); t.putalpha(m); im.alpha_composite(t); return im

def wifi_lock(level, size=(30, 21)):
    """Secured network, signal 1..4: the Wi-Fi fan (unlit arcs #666666, lit arcs white) and a small lock."""
    from PIL import Image
    def fan(p):
        full = glyph('wifi', p, 'small', OFF).copy(); full.alpha_composite(glyph(WIFI_LEVELS[level], p, 'small')); return full
    c = Image.new('RGBA', size, (0, 0, 0, 0)); f = fit(fan, 21, 17, 22, 'l')
    c.alpha_composite(f, (0, (size[1] - f.height) // 2))
    lock = glyph_fit('lock:filled', 9, 11, WHITE, 0); c.alpha_composite(lock, (size[0] - lock.width, size[1] - lock.height))
    return c

def generate_all(sizes):
    """sizes: {file name: (w, h)} of the stock files -> {file name: RGBA image}."""
    from PIL import Image
    f = {}
    for n, _, g in SETTINGS + LISTS: f[n] = bare_icon(g, 40)
    for n, _, g in HOME:
        if not g: continue
        f[n] = on_disc(glyph(g, HOME_GLYPH, 'disc'), 66, DISC)
        f[n + '_down'] = on_disc(glyph(g, HOME_GLYPH, 'disc'), 66, DISC_DOWN)
    f[POD_HOME[0]] = on_disc(glyph(POD_HOME_GLYPH, HOME_GLYPH, 'disc'), 66, DISC)
    f[POD_HOME[1]] = on_disc(glyph(POD_HOME_GLYPH, HOME_GLYPH, 'disc'), 66, DISC_DOWN)
    # pull-down tiles: one ring style, off / on / disabled (docs/ui.md)
    for n, (g, st) in TILES.items(): f[n] = ring_tile(g, st)
    for n in ('drop_lighticon0', 'drop_lighticon1'):
        f[n] = fit(lambda p, g=PULLDOWN[n]: glyph(g, p, 'small'), 20, 20, 20)
    # status bar
    f['bar_play'] = fit(lambda p: glyph(STATUS['bar_play'], p, 'solid'), 14, 18, 16)
    f['bar_pause'] = fit(lambda p: glyph(STATUS['bar_pause'], p, 'solid'), 14, 18, 16)
    for i in range(5):
        f[f'bar_vol{i}'] = fit(lambda p, i=i: glyph(STATUS[f'bar_vol{i}'], p, 'small'), 24, 18, 22, 'l')
    def wifi(level, p):
        full = glyph(STATUS['bar_wifi'], p, 'small', OFF).copy()
        if level: full.alpha_composite(glyph(WIFI_LEVELS[level], p, 'small'))
        return full
    for i in range(5): f[f'bar_wifi{i}'] = fit(lambda p, i=i: wifi(i, p), 24, 16, 22)
    f['bar_bt'] = fit(lambda p: glyph(STATUS['bar_bt'], p, 'small', OFF), 47, 20, 22, 'r')
    f['bar_btcon'] = fit(lambda p: glyph(STATUS['bar_bt'], p, 'small'), 47, 20, 22, 'r')
    f['bar_digital'] = fit(lambda p: glyph(STATUS['bar_digital'], p, 'small'), 18, 18, 20)
    # "no cover" tiles: the stock tile colour, a muted glyph at COVER_FRAC of the tile
    for n in COVERS:
        w = sizes[n][0]; bg = sizes[n + ':bg']
        t = Image.new('RGBA', (w, w), bg + (255,))
        g = glyph(COVER_GLYPH, round(w * COVER_FRAC), 'cover', (0x8C,) * 3)       # stroke 2
        t.alpha_composite(g, ((w - g.width) // 2, (w - g.height) // 2))
        f[n] = t if sizes[n + ':mode'] == 'RGBA' else t.convert('RGB')
    for n, g in POD_ROWS.values(): f[n] = bare_icon(g, POD_ICON)
    for n, g in FOLDER_ROWS.items(): f[n] = bare_icon(g, POD_ICON)
    for n, g in SUBSONIC_ICONS.items(): f[n] = bare_icon(g, POD_ICON)
    nav_art = glyph('disc-3', 108, 'cover')
    f[SUBSONIC_ART[0]] = Image.new('RGBA', (SUBSONIC_ART_PX, SUBSONIC_ART_PX), (0, 0, 0, 0))
    f[SUBSONIC_ART[0]].alpha_composite(nav_art, ((SUBSONIC_ART_PX - nav_art.width) // 2, (SUBSONIC_ART_PX - nav_art.height) // 2))
    dsd_badge = badge('DSD', ss=8, size=(112, 68), font_px=42, stroke=3.5, radius=12, pad=8)
    f[SUBSONIC_ART[1]] = Image.new('RGBA', (SUBSONIC_ART_PX, SUBSONIC_ART_PX), (0, 0, 0, 0))
    f[SUBSONIC_ART[1]].alpha_composite(dsd_badge, ((SUBSONIC_ART_PX - dsd_badge.width) // 2, (SUBSONIC_ART_PX - dsd_badge.height) // 2))
    for n, g in RADIO_ROWS.items(): f[n] = bare_icon(g, POD_ICON)
    f[RADIO_ART[0]] = glyph_fit(RADIO_ART[1], RADIO_ART_PX, RADIO_ART_PX, ES_RGB, 4, 4.0)
    for g in set(CARD_GLYPHS.values()): f[card_name(g)] = card_icon(g)
    name, w, h, rgb = CARD_CHEVRON
    f[name] = pod_chevron(rgb)
    f[CARD_CHECK[0]] = glyph_fit('check', CARD_CHECK[1], CARD_CHECK[1])
    for i, n in enumerate(SWATCHES): f[n] = swatch(i)
    for n, (g, px, rgb) in WIFI_GLYPHS.items(): f[n] = glyph_fit(g, px, px, rgb, 1, 2.0 if px >= 22 else 1.5)
    for n in range(4): f[f'wf_sig{n}'] = wifi_signal(n)
    for i in range(8): f[f'wf_spin{i}'] = wifi_spinner(i)
    for p in CARD_PIECES:
        f[f'pod_cd_{p}'] = card_piece(p); f[f'pod_cd_{p}_down'] = card_piece(p, True)
        f[f'pod_cdl_{p}'] = card_piece(p, tall=True); f[f'pod_cdl_{p}_down'] = card_piece(p, True, tall=True)
    for n, g in PL_MENU_ICONS: f[n] = glyph(g, PL_MENU_PX, 'bare')
    for n, g in RM_MENU_ICONS: f[n] = glyph(g, BARE_PX, 'bare')
    f[RM_FAV_ON[0]] = glyph(RM_FAV_ON[1], BARE_PX, 'solid')
    f[RM_DOTS[0]] = glyph(RM_DOTS[1], RM_DOTS_PX, 'bare')
    for n, g in ES_ICONS.items(): f[n] = glyph_fit(g, ES_PX, ES_PX, ES_RGB, 2, 2.0)
    for n, g in NAV_VIEW.items():
        pos = NAV_VIEW_POS[n]
        f[n] = capsule_piece(pos, g, False)
        f[n + '_down'] = capsule_piece(pos, g, True)
    f[SHOT_BAR[0]] = fit(lambda p: glyph(SHOT_BAR[1], p, 'small'), SHOT_BAR_PX, SHOT_BAR_PX, SHOT_BAR_PX)
    f[LO_BAR] = lo_pill()
    f[SYNC_BAR[0]] = glyph_fit(SYNC_BAR[1], SYNC_BAR_PX, SYNC_BAR_PX, WHITE, 1, 1.5)
    f[SYNC_DM] = glyph_fit(SYNC_BAR[1], SYNC_DM_PX, SYNC_DM_PX, (0xAA,) * 3, 1, 1.5)
    # round 2: glyph images at the stock size, discs, recoloured line art, badges, pills
    for n, g, down in GLYPHS:
        grey = (GREY_GLYPHS[n],) * 3 if n in GREY_GLYPHS else WHITE
        col, col_down = (CHEVRON, CHEVRON_DOWN) if n in CHEVRONS else (grey, (0x77,) * 3)
        def make(size, rgb, n=n, g=g):
            if n in SMALL_GLYPHS: return glyph_box(g, size, NAV_K, rgb)
            if n in DIALOG_GLYPHS: return glyph_box(g, size, DIALOG_K, rgb)
            if n in MARK_GLYPHS: return glyph_mark(g, size, MARK_K, rgb)
            return glyph_fit(g, *size, rgb, 6 if min(size) >= 48 else 1)
        if n == 'right_arrow':      # the shared list chevron, its right edge on the stock canvas' (a 13 x 22 button at x 285 lands the glyph at 288..298)
            f[n] = pod_chevron(col, sizes[n]); f[down] = pod_chevron(col_down, sizes[down]); continue
        f[n] = make(sizes[n], col)
        if down: f[down] = make(sizes[down], col_down)
    for n, g in DISCS: f[n] = bare_icon(g, 40)
    for n in RECOLOUR: f[n] = recolour_white(os.path.join(find_stock_img(), n + '.png'))
    for n, (label, sel) in SPEEDS.items(): f[n] = speed_badge(label, sel)
    for n, pressed in PLAYALL.items(): f[n] = play_all_pill(pressed)
    for n, level in WIFI_LOCK.items(): f[n] = wifi_lock(level)
    f.update(album_images())
    f.update(podcast_images())
    f.update(r3_images())
    return f

def ah_tint_alpha(y):
    """patch/common.c pod_alpha with the album page's constants (AH_TINT): the black gradient's alpha on window row y."""
    top, bot, rows, _ = AH_TINT
    return bot if y >= rows - 1 else top + ((bot - top) * y + (rows - 1) // 2) // (rows - 1)

# The Songs page (patch/songs.c, docs/modules/songs.md): the glyphs of its flat pills (Play, Shuffle, Add to playlist, Delete: a 16 px canvas each, the ink at
# most SG_INK px; Delete's is red-ish) and the tick of the sort card's current order (14 px). White except Delete's; no pressed variants (the pills are flat).
DARK_GLYPH = (0x14, 0x14, 0x14)
SONGS_IMAGES = {'sg_play': ('play:filled', WHITE, 14, 16), 'sg_shuffle': ('shuffle', WHITE, 16, 16), 'sg_repeat': ('repeat', WHITE, 16, 16), 'sg_repeat1': ('repeat-1', WHITE, 16, 16), 'sg_listplus': ('list-plus', WHITE, 16, 16),
                'sg_shuffle_on': ('shuffle', DARK_GLYPH, 16, 16), 'sg_repeat_on': ('repeat', DARK_GLYPH, 16, 16), 'sg_repeat1_on': ('repeat-1', DARK_GLYPH, 16, 16),   # the Queue page's lit buttons (#C8C8C8): a near black glyph
                'sg_trash': ('trash', (0xFF, 0x6B, 0x6B), 16, 16), 'sg_tick': ('+check', WHITE, 14, 14),
                'pod_ic_vslist': ('list', WHITE, 20, 20), 'pod_ic_vsgrid': ('layout-grid', WHITE, 20, 20), 'pod_ic_vssearch': ('search', WHITE, 20, 20), 'pod_ic_vsselect': ('T:circle-check', WHITE, 20, 20),
                'pod_ic_vsartist': ('mic-vocal', WHITE, 20, 20), 'pod_ic_vsalbumartist': ('user-star', WHITE, 20, 20)}   # the view row of the Albums "..." card: the glyph of the view a tap switches to (bare, as the Playlists menu's rows)
ALBUM += sorted(SONGS_IMAGES)

# The keyboard page's glyphs (patch/keyboard.c, docs/modules/keyboard.md): shift (outline, white) and shift on (filled, dark on the light key), delete, the field's magnifier (grey) and its clear
# disc (a dark x on a grey disc), exact canvases; the custom SVGs are Lucide's arrow-big-up and delete. White and grey only.
KEYBOARD_IMAGES = {'qk_shift': ('+arrow-big-up', (255, 255, 255), 18, 18), 'qk_shifton': ('+arrow-big-up:filled', (0x1C, 0x1C, 0x1E), 18, 18),
                   'qk_delete': ('+delete', (255, 255, 255), 24, 20), 'qk_mag': ('search', (0x8E, 0x8E, 0x93), 16, 16)}
KB_CLEAR = ('qk_clear', 'x', (0x1C, 0x1C, 0x1E), 9, 16, (0x63, 0x63, 0x66))   # name, glyph, its colour, its ink px, the disc's diameter, the disc
ALBUM += sorted(KEYBOARD_IMAGES) + [KB_CLEAR[0]]
# the Search page's X (patch/search.h SE_CLOSE_*): a flat disc as high as the field, in the field's grey (pressed lighter), a white 13 px x; not the 42 px glass
SE_CLOSE = ('se_close', 'x', WHITE, 13, 36, (0x1C, 0x1C, 0x1E), (0x3A, 0x3A, 0x3C))   # name, glyph, its colour, its ink px, the disc's diameter, the disc, pressed
ALBUM += [SE_CLOSE[0], SE_CLOSE[0] + '_down']
# the Home cache pill's stop button (tools/pod_ui.py cache_pill): a flat 28 px disc #2C2C2E (pressed #3A3A3C) with a white 14 px x
CACHE_X = ('pod_cache_x', 'x', WHITE, 14, 28, (0x2C, 0x2C, 0x2E), (0x3A, 0x3A, 0x3C))
ALBUM += [CACHE_X[0], CACHE_X[0] + '_down']

def keyboard_images():
    f = {n: glyph_fit(g, cw, ch, rgb, 1 if n != 'qk_mag' else 0) for n, (g, rgb, cw, ch) in KEYBOARD_IMAGES.items()}
    n, g, rgb, ink, d, fill = KB_CLEAR
    f[n] = clear_disc(ink, d, fill, rgb)
    n, g, rgb, ink, d, fill, down = SE_CLOSE
    f[n], f[n + '_down'] = (on_disc(glyph_fit(g, ink, ink, rgb, 0), d, c) for c in (fill, down))
    n, g, rgb, ink, d, fill, down = CACHE_X
    f[n], f[n + '_down'] = (on_disc(glyph_fit(g, ink, ink, rgb, 0, 1.5), d, c) for c in (fill, down))
    return f

def clear_disc(ink, d, fill, rgb, stroke=2.0, ss=16):
    """The field's clear button: a d px disc with an x of ink px (round ends, stroke px) drawn at ss x about the disc's own centre and reduced with a box filter, so the cross is centred in x and
    y to a fraction of a pixel (glyph_fit's crop of an odd canvas put its ink 0.85 px left of the centre; test/pod/keyboard.py measures it)."""
    from PIL import Image, ImageDraw
    big = Image.new('L', (d * ss, d * ss), 0)
    dr = ImageDraw.Draw(big)
    c, h, r = (d * ss - 1) / 2, (ink - stroke) / 2 * ss, stroke * ss / 2
    for sx in (-1, 1):
        dr.line((c - h, c - sx * h, c + h, c + sx * h), fill=255, width=int(round(stroke * ss)))
    for sx in (-1, 1):
        for sy in (-1, 1): dr.ellipse((c + sx * h - r, c + sy * h - r, c + sx * h + r, c + sy * h + r), fill=255)
    cross = Image.new('RGBA', (d, d), rgb + (0,)); cross.putalpha(big.resize((d, d), Image.BOX))
    im = disc(d, fill); im.alpha_composite(cross); return im

def songs_images():
    from PIL import Image
    f = {}
    for n, (g, rgb, ink, canvas) in SONGS_IMAGES.items():
        c = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0)); gi = glyph_fit(g, ink, ink, rgb, 0)
        c.alpha_composite(gi, ((canvas - gi.width) // 2, (canvas - gi.height) // 2)); f[n] = c
    return f

# The Podcasts Show page (patch/podcasts.c, docs/modules/podcasts.md "The Show page"). ONE atlas, pc_atlas (PA_SIZE square, straight-alpha RGBA), holds what the page paints
# in its content view (no widget per cell): the progress ring's 12 steps, the state glyphs, the "on the card" badge, the "..." glyph and the discs the pills' ends are cut from. The
# cells are patch/offsets.inc PA_* (test/pod/pcshow.py checks they are these numbers); the payload decodes the atlas once with its alpha (podcasts.c pg_atlas). The bottom sheets' glyphs
# are images of their own (they sit in widgets) and the sheets' glass for one to five rows (the More sheet's glass, a picture per height).
PA_SIZE = 160
PA_RING_N, PA_RING_PX, PA_RING_COLS = 12, 16, 6          # ring k (the arc k / 12 of the circle, 0..11) at column k % 6, row k / 6 of 16 px cells from the atlas' top left
PA_G_Y, PA_G_PX = 32, 16                                 # the 16 px glyph strip: arrow-down, play, pause, retry, check (grey), play (dark) at x 16 * index
PA_DOTS_Y, PA_DOTS_PX, PA_BADGE_X, PA_BADGE_PX = 48, 20, 24, 12   # the "..." glyph (20 px, grey) at x 0; the 12 px badge at x 24
PA_PILL_Y, PA_PILLF_X, PA_PILLO_X, PA_PILLW_X, PA_PILLR_X, PA_PILL_PX, PA_PILLW_PX = 68, 0, 32, 64, 108, 30, 40   # the discs: filled (30), outlined (30), white (40) and outlined (40): the Latest Episode pill's ends
PA_FILL_A, PA_RING_A, PA_TRACK_A = 56, 110, 80           # alpha of the filled pill, of the outlined pill's ring (2 px), of the progress ring's track
PA_GREY, PA_BADGE_GREY, PA_DARK, PA_RED = (0xAA,) * 3, (0xD0,) * 3, (0x14,) * 3, (0xFF, 0x6B, 0x6B)
PA_CHEV = 6                                              # glyph 6 of the strip: the chevron-right (grey) of the Shows page's Downloads row
PA_TILE_PX, PA_TILE_R, PA_TILE_RGB, PA_TILE_GLYPH = 44, 8, (0x1E,) * 3, 22   # the Library rows' tile: a 44 px rounded square, the Lucide glyph (22 px, white) on it
PC_DL_TILE = 'pod_ic_dltile'                           # the Downloads row's tile: the same square with the Lucide download glyph (an image of its own, like the other two, so the accent can tint its glyph by name)
PC_SAVE_TILE = 'pod_ic_savetile'                         # the Saved row's tile: the same square with the Lucide bookmark glyph
PC_SRCH_TILE = 'pod_ic_discovertile'                       # the Search row's tile: the same square with the Lucide compass glyph
PC_LIB_TILE = 'pod_ic_subtile'                           # the Subscriptions row's tile: the same square (an image of its own, so the atlas stays as it is: test/pod/navbars.py ignores pod_ic_) with the Lucide podcast glyph
PA_PLAYB_X, PA_PLAYB_Y, PA_PLAYB_PX, PA_PLAYB_RIM_A, PA_PLAYB_GLYPH = 48, 112, 28, 90, 12   # Continue Listening's play disc: 28 px, a white 26 px disc inside a 1 px black rim (35 %, so it reads on a white cover too), the dark play triangle (12 px) nudged 1 px right to look centred
PC_ATLAS = 'pc_atlas'
PC_SHEET_ICONS = (('pc_ic_import', 'file-input', WHITE), ('pc_ic_speed', 'gauge', WHITE), ('pc_ic_refresh', 'refresh-cw', WHITE), ('pc_ic_select', 'list-checks', WHITE), ('pc_ic_check', '+check', WHITE),
                  ('pc_ic_unsub', 'x', PA_RED), ('pc_ic_down', 'arrow-down', WHITE), ('pc_ic_trash', 'trash', WHITE), ('pc_ic_undo', 'rotate-ccw', WHITE),
                  ('pod_ic_export', 'file-output', WHITE), ('pod_ic_save', 'bookmark', WHITE),
                  ('pod_ic_rd_add', 'plus', WHITE), ('pod_ic_rd_remove', 'minus', WHITE), ('pod_ic_rd_import', 'import', WHITE), ('pod_ic_rd_info', 'info', WHITE))   # the Radio sheets: Add to / Remove from Stations and Station Info (Now Playing), Import from Card (Stations; its Recently Played sheet's Clear row uses pc_ic_trash)   # (pod_ic_ names: the images the stock pages' digest test ignores, test/pod/navbars.py NEW_IMAGES; a new pc_ image would change test/navbars-stock.sha256 in every branch)
PC_SHEET_PX = 20
PC_SHEETS = (('pc_sheet1', 50), ('pc_sheet2', 100), ('pc_sheet3', 150), ('pc_sheet4', 200), ('pc_sheet5', 250))   # the sheets' glass for 1..5 rows (Now Playing's pm_sheet / pm_sheet5 for 4 and 5, but a name of ours: the Show page's rows need no other page's image)
PC_GLYPHS = ('arrow-down', 'download', 'chevron-right', 'file-input', 'podcast', 'compass', 'file-output', 'plus', 'minus', 'import')                                 # the Lucide glyph the set adds to the sources (the download symbol of the pill, the badge and the sheet)
PODCASTS = [PC_ATLAS, PC_DL_TILE, PC_LIB_TILE, PC_SAVE_TILE, PC_SRCH_TILE] + [n for n, _, _ in PC_SHEET_ICONS] + [n for n, _ in PC_SHEETS]
ALBUM += PODCASTS

def _pc_ring(k):
    """The progress ring's step k: a faint 2 px track and the arc from 12 o'clock for k / PA_RING_N of the circle, white, 16 px."""
    from PIL import Image, ImageChops, ImageDraw
    px, s, w = PA_RING_PX, 8, 2
    n = px * s
    def arc(frac):
        m = Image.new('L', (n, n), 0)
        d = ImageDraw.Draw(m)
        if frac > 0: d.arc((0, 0, n - 1, n - 1), -90, -90 + 360 * frac, fill=255, width=w * s)
        return m.resize((px, px), Image.LANCZOS)
    track = Image.new('L', (n, n), 0)
    ImageDraw.Draw(track).ellipse((0, 0, n - 1, n - 1), outline=255, width=w * s)
    track = track.resize((px, px), Image.LANCZOS).point(lambda v: v * PA_TRACK_A // 255)
    out = Image.new('RGBA', (px, px), WHITE + (0,))
    out.putalpha(ImageChops.lighter(track, arc(k / PA_RING_N)))
    return out

def _pc_disc(size, rgb, alpha, ring=0):
    """A disc (or a ring `ring` px wide) of one colour at one alpha, anti-aliased: the ends of a pill."""
    from PIL import Image, ImageChops, ImageDraw
    s = 8
    m = Image.new('L', (size * s, size * s), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size * s - 1, size * s - 1), fill=255)
    if ring:
        inner = Image.new('L', (size * s, size * s), 0)
        ImageDraw.Draw(inner).ellipse((ring * s, ring * s, (size - ring) * s - 1, (size - ring) * s - 1), fill=255)
        m = ImageChops.subtract(m, inner)
    out = Image.new('RGBA', (size, size), rgb + (0,))
    out.putalpha(m.resize((size, size), Image.LANCZOS).point(lambda v: v * alpha // 255))
    return out

def _pc_badge():
    """The 12 px "on the card" badge: a light grey disc with the Lucide arrow-down cut out of it (transparent: the page shows through)."""
    from PIL import Image, ImageChops
    px = PA_BADGE_PX
    disc_ = _pc_disc(px, PA_BADGE_GREY, 255)
    g = glyph('arrow-down', 8, 'small')            # 8 px, 1.5 px stroke
    cut = Image.new('L', (px, px), 0); cut.paste(g.getchannel('A'), ((px - g.width) // 2, (px - g.height) // 2))
    out = disc_.copy(); out.putalpha(ImageChops.subtract(disc_.getchannel('A'), cut))
    return out

def _pc_tile(name='download'):
    """A Library row's 44 px tile: an opaque #1E1E1E rounded square (8 px corners, anti-aliased) with a Lucide glyph (download for Downloads, podcast for Subscriptions) centred on it."""
    from PIL import Image, ImageDraw
    px, s = PA_TILE_PX, 8
    m = Image.new('L', (px * s, px * s), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, px * s - 1, px * s - 1), radius=PA_TILE_R * s, fill=255)
    out = Image.new('RGBA', (px, px), PA_TILE_RGB + (0,)); out.putalpha(m.resize((px, px), Image.LANCZOS))
    g = glyph(name, PA_TILE_GLYPH, 'small')
    out.alpha_composite(g, ((px - g.width) // 2, (px - g.height) // 2))
    return out

def _pc_playb():
    """Continue Listening's 28 px play disc: a white disc inside a faint black rim, a dark play triangle on it."""
    px = PA_PLAYB_PX
    out = _pc_disc(px, (0, 0, 0), PA_PLAYB_RIM_A)
    out.alpha_composite(_pc_disc(px - 2, WHITE, 255), (1, 1))
    g = tint(glyph('play', PA_PLAYB_GLYPH, 'solid'), PA_DARK)
    out.alpha_composite(g, ((px - g.width) // 2 + 1, (px - g.height) // 2))
    return out

def pc_atlas():
    """The atlas image (PA_SIZE square)."""
    from PIL import Image, ImageOps
    a = Image.new('RGBA', (PA_SIZE, PA_SIZE), (0, 0, 0, 0))
    for k in range(PA_RING_N): a.alpha_composite(_pc_ring(k), (k % PA_RING_COLS * PA_RING_PX, k // PA_RING_COLS * PA_RING_PX))
    def cell(i, im): a.alpha_composite(im, (i * PA_G_PX + (PA_G_PX - im.width) // 2, PA_G_Y + (PA_G_PX - im.height) // 2))
    cell(0, glyph('arrow-down', PA_G_PX, 'small'))
    cell(1, glyph('play', 14, 'solid')); cell(2, glyph('pause', 14, 'solid'))
    cell(3, ImageOps.mirror(glyph('rotate-ccw', PA_G_PX, 'small')))
    cell(4, tint(glyph('+check', 14, 'small'), PA_GREY))
    cell(5, tint(glyph('play', 14, 'solid'), PA_DARK))
    cell(PA_CHEV, tint(glyph('chevron-right', PA_G_PX, 'small'), PA_GREY))
    d = glyph('ellipsis', PA_DOTS_PX, 'solid'); a.alpha_composite(tint(d, PA_GREY), (0, PA_DOTS_Y))
    a.alpha_composite(_pc_badge(), (PA_BADGE_X, PA_DOTS_Y))
    a.alpha_composite(_pc_playb(), (PA_PLAYB_X, PA_PLAYB_Y))
    a.alpha_composite(_pc_disc(PA_PILL_PX, WHITE, PA_FILL_A), (PA_PILLF_X, PA_PILL_Y))
    a.alpha_composite(_pc_disc(PA_PILL_PX, WHITE, PA_RING_A, 2), (PA_PILLO_X, PA_PILL_Y))
    a.alpha_composite(_pc_disc(PA_PILLW_PX, WHITE, 255), (PA_PILLW_X, PA_PILL_Y))
    a.alpha_composite(_pc_disc(PA_PILLW_PX, WHITE, PA_RING_A, 2), (PA_PILLR_X, PA_PILL_Y))
    return a

def podcast_images():
    f = {PC_ATLAS: pc_atlas(), PC_DL_TILE: _pc_tile(), PC_LIB_TILE: _pc_tile('podcast'), PC_SAVE_TILE: _pc_tile('bookmark'), PC_SRCH_TILE: _pc_tile('compass')}
    for n, g, rgb in PC_SHEET_ICONS: f[n] = tint(glyph(g, PC_SHEET_PX, 'small'), rgb) if rgb != WHITE else glyph(g, PC_SHEET_PX, 'small')
    for n, h in PC_SHEETS: f[n] = glass_image(320, h, 18, fill=GLASS_SHEET_FILL, top_only=True)
    assert sorted(f) == sorted(PODCASTS)
    return f

def album_images():
    """The album page's images (ALBUM): the tint gradient, Shuffle's disc + glyph, the pill, the play glyph."""
    from PIL import Image
    f = {}
    w = 320; h = AH_TINT[3]
    tint = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for y in range(h): tint.paste((0, 0, 0, ah_tint_alpha(y)), (0, y, w, y + 1))
    f['ah_tint'] = tint
    g = glyph_fit('shuffle', AH_SHUF_GLYPH, AH_SHUF_GLYPH, WHITE, 0)
    f['ah_shuffle'] = on_disc(g, AH_DISC_PX, AH_SHUF_DISC)
    f['ah_shuffle_down'] = on_disc(g, AH_DISC_PX, AH_SHUF_DISC_DOWN)
    f['ah_wave'] = ab_wave()
    f['ah_pill'] = pill(AH_PILL_PX, AH_PILL_FILL)
    f['ah_pill_down'] = pill(AH_PILL_PX, AH_PILL_FILL_DOWN)
    p = glyph_fit('play:filled', AH_PLAY_GLYPH, AH_PLAY_GLYPH, AH_PLAY_INK, 0)
    f['ah_play'] = p                 # no padding: the payload places it beside the pill's text (patch/albumpage.c)
    f.update(ah_nav_images())
    f.update(songs_images())
    f.update(keyboard_images())
    f[NB_FADE[0]] = nb_fade_image()
    g = glyph_fit('play:filled', DM_PLAY_GLYPH, DM_PLAY_GLYPH, WHITE, 0)
    for n, pressed in (('dm_disc', False), ('dm_disc_down', True)):
        d = glass_image(DM_DISC_PX, DM_DISC_PX, DM_DISC_PX // 2, pressed)
        d.alpha_composite(g, ((DM_DISC_PX - g.width) // 2 + 1, (DM_DISC_PX - g.height) // 2)); f[n] = d
    chev = glyph_fit('chevron-left', DP_BACK_GLYPH, DP_BACK_GLYPH, WHITE, 0)
    for n, pressed in (('dp_back', False), ('dp_back_down', True)):   # the page's back disc: the same glass, a chevron optically centred (its weight sits left of its box: one px right of centre)
        d = glass_image(DP_BACK_PX, DP_BACK_PX, DP_BACK_PX // 2, pressed)
        d.alpha_composite(chev, ((DP_BACK_PX - chev.width) // 2 - 1, (DP_BACK_PX - chev.height) // 2)); f[n] = d
    for n, rgb in (('dp_pill', (255, 255, 255)), ('dp_pill_down', DP_PILL_DOWN)): f[n] = solid_pill(*DP_PILL_PX, rgb)
    f['dp_play'] = glyph_fit('play:filled', AH_PLAY_GLYPH, AH_PLAY_GLYPH, DP_PILL_INK, 0)
    plus = glyph_fit(DP_ADD_GLYPH, AH_SHUF_GLYPH, AH_SHUF_GLYPH, WHITE, 0)   # the Shuffle glyph's box and stroke on the Shuffle disc's two greys
    f['dp_add'] = on_disc(plus, AH_DISC_PX, AH_SHUF_DISC)
    f['dp_add_down'] = on_disc(plus, AH_DISC_PX, AH_SHUF_DISC_DOWN)
    tick = glyph_fit(DP_ADDED_GLYPH, AH_SHUF_GLYPH, AH_SHUF_GLYPH, WHITE, 0)   # the mix's playlist exists
    f['dp_added'] = on_disc(tick, AH_DISC_PX, AH_SHUF_DISC)
    f['dp_added_down'] = on_disc(tick, AH_DISC_PX, AH_SHUF_DISC_DOWN)
    f['ipod_wheel'] = ipod_wheel()
    f['ipod_wheel_dark'] = ipod_wheel(dark=True)
    for n, g in (('ipod_mode_shuffle', 'shuffle'), ('ipod_mode_repeat', 'repeat'), ('ipod_mode_repeat1', 'repeat-1')):   # patch/ipod.c ip_mode_bitmap: a heavy white glyph at 32 px, 16 px after the box filter
        f[n] = glyph_fit(g, IPOD_MODE_SRC, IPOD_MODE_SRC, WHITE, 2, 4.0)
    from PIL import Image
    f['ipod_playing'] = glyph_fit('volume-2', 2 * IP_PLAY_SRC, 2 * IP_PLAY_SRC, WHITE, 2, 4.0)   # patch/ipod.c: the playing track's speaker, a heavy white glyph at 28 px, 14 px after the box filter
    f['ipod_placeholder'] = Image.open(IPOD_PLACEHOLDER).convert('RGB')   # the Pod's cover for anything without art (docs/modules/ipod.md)
    f['ipod_podcasts'] = ipod_podcasts_pane()
    import tape_art
    f.update(tape_art.images())
    f.update(vinyl_art.images())
    return f

def ipod_podcasts_pane():
    """The main menu's Podcasts pane (the iPod 6G's): a vertical blue-grey gradient in ipod-player's info pane colours (A7C1D6 to 3E4D5C), and the classic white podcast glyph (a head in three broadcast arcs open at the
    bottom, a tapered body through their gap) with a soft glow, drawn at 4 x and reduced. Opaque. The payload writes No Podcasts under it."""
    from PIL import Image, ImageDraw, ImageFilter
    k, (w, h), cx, cy = 4, IPOD_PC_PANE, IPOD_PC_PANE[0] / 2, IPOD_PC_GLYPH_Y
    bg = Image.new('RGB', (w, h))
    px = bg.load()
    top, bot = (0xA7, 0xC1, 0xD6), (0x3E, 0x4D, 0x5C)   # ipod-player's infoPaneTop / infoPaneBottom
    for y in range(h):
        for x in range(w):
            t = y / (h - 1)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bot))
    m = Image.new('L', (w * k, h * k), 0)
    d = ImageDraw.Draw(m)
    def s(v): return v * k
    sw = 4.5
    for r, gap in ((54, 52), (40, 50), (26, 44)):   # ring radius, half the bottom gap in degrees
        a0, a1 = 90 + gap, 90 - gap + 360
        d.arc((s(cx - r - sw / 2), s(cy - r - sw / 2), s(cx + r + sw / 2), s(cy + r + sw / 2)), a0, a1, fill=255, width=round(s(sw)))
        for a in (a0, a1):   # round caps
            ex, ey = cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
            d.ellipse((s(ex - sw / 2), s(ey - sw / 2), s(ex + sw / 2), s(ey + sw / 2)), fill=255)
    hr, hy = 11.5, cy - 10
    d.ellipse((s(cx - hr), s(hy - hr), s(cx + hr), s(hy + hr)), fill=255)
    bt, bb, wt, wb = cy + 6, 160, 13.5, 8.5   # the body: top and bottom, half widths, round ends
    d.polygon([(s(cx - wt), s(bt + wt)), (s(cx + wt), s(bt + wt)), (s(cx + wb), s(bb - wb)), (s(cx - wb), s(bb - wb))], fill=255)
    d.ellipse((s(cx - wt), s(bt), s(cx + wt), s(bt + 2 * wt)), fill=255)
    d.ellipse((s(cx - wb), s(bb - 2 * wb), s(cx + wb), s(bb)), fill=255)
    mask = m.resize((w, h), Image.BOX)
    glow = mask.filter(ImageFilter.GaussianBlur(4)).point(lambda v: v * 3 // 5)
    out = bg.convert('RGBA')
    out.alpha_composite(Image.merge('RGBA', (*Image.new('RGB', (w, h), (255, 255, 255)).split(), glow)))
    out.alpha_composite(Image.merge('RGBA', (*Image.new('RGB', (w, h), (255, 255, 255)).split(), mask)))
    return out.convert('RGB')

def ipod_wheel(dark=False):
    """The click wheel: a light or charcoal ring (a vertical gradient inside a 1 px rim) with a centre button, drawn at 4 x and reduced; the labels MENU, |<<, >>| and >|| on the ring."""
    from PIL import Image, ImageDraw, ImageFont
    k, d, hr = 4, IPOD_WHEEL_D, IPOD_HUB_R
    r = d // 2
    big = Image.new('RGBA', (d * k, d * k), (0, 0, 0, 0))
    def grad(radius, top, bot, rim):
        m = Image.new('L', big.size, 0); ImageDraw.Draw(m).ellipse((r * k - radius * k, r * k - radius * k, r * k + radius * k - 1, r * k + radius * k - 1), fill=255)
        g = Image.new('RGBA', big.size, (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
        for y in range(r * k - radius * k, r * k + radius * k):
            t = (y - (r * k - radius * k)) / (2 * radius * k)
            gd.line((0, y, big.width, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
        rm = Image.new('RGBA', big.size, (0, 0, 0, 0)); ImageDraw.Draw(rm).ellipse((r * k - radius * k, r * k - radius * k, r * k + radius * k - 1, r * k + radius * k - 1), fill=rim + (255,))
        inner = Image.new('L', big.size, 0); ImageDraw.Draw(inner).ellipse((r * k - radius * k + k, r * k - radius * k + k, r * k + radius * k - k - 1, r * k + radius * k - k - 1), fill=255)
        big.alpha_composite(rm); big.paste(g, (0, 0), inner)
    if dark:
        grad(r, (0x25, 0x25, 0x26), (0x1D, 0x1D, 0x1E), (0x14, 0x14, 0x15))
        grad(hr, (0x36, 0x36, 0x38), (0x2A, 0x2A, 0x2C), (0x0C, 0x0C, 0x0D))
    else:
        grad(r, (0xF6,) * 3, (0xEE,) * 3, (0xA8, 0xAB, 0xB0))
        grad(hr, (0xEE,) * 3, (0xCF,) * 3, (0xB0,) * 3)
    lab = ((0xFF,) * 3 if dark else (0x9F, 0xA9, 0xB3)) + (255,); dr = ImageDraw.Draw(big); mid = (r + hr) * k // 2; g = 5 * k; cx = cy = r * k
    for sx in (-1, 1):   # |<< and >>|: two triangles pointing along sx, then the bar
        x = cx + sx * mid
        for xc in (x - 3 * k, x + 3 * k):
            dr.polygon([(xc - sx * 3 * k, cy - g), (xc - sx * 3 * k, cy + g), (xc + sx * 3 * k, cy)], fill=lab)
        bx = x + sx * 8 * k
        dr.rectangle((min(bx, bx + sx * 2 * k), cy - g, max(bx, bx + sx * 2 * k), cy + g), fill=lab)
    by = cy + mid
    dr.polygon([(cx - 8 * k, by - 5 * k), (cx - 8 * k, by + 5 * k), (cx - 1 * k, by)], fill=lab)
    dr.rectangle((cx + 2 * k, by - 5 * k, cx + 4 * k, by + 5 * k), fill=lab); dr.rectangle((cx + 6 * k, by - 5 * k, cx + 8 * k, by + 5 * k), fill=lab)
    out = big.resize((d, d), Image.LANCZOS)
    f = ImageFont.truetype(TILE_FONT, 16); bb = f.getbbox('MENU')
    ImageDraw.Draw(out).text((r - (bb[2] - bb[0]) / 2 - bb[0], r - mid // k - (bb[3] - bb[1]) / 2 - bb[1]), 'MENU', font=f, fill=lab)
    return out

def solid_pill(w, h, rgb):
    """A w x h pill (corner radius h / 2) of one opaque colour, anti-aliased (8 x supersampled)."""
    from PIL import Image, ImageDraw
    k = 8
    m = Image.new('L', (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=h * k // 2, fill=255)
    im = Image.new('RGBA', (w, h), rgb + (255,)); im.putalpha(m.resize((w, h), Image.BOX)); return im

# Glass navbar buttons (docs/modules/navbar.md): every glass piece is one image, cut to the REAL button it sits in (main's slots: the Pod pages' right-hand
# buttons 46 wide at x 122 / 168 / 214, Now Playing 60 wide at 260, glyph centres 152 / 198 / 244 / 290 with NAV_SHIFT below), drawn by the button's `icon` centred in it. A
# lone button is a disc (glass_image of the mini bar's pane, the white glyph on it); the Pod pages' buttons that abut (Cover Flow / "..." | toggle | Now
# Playing) are slices of ONE capsule (r = 21) from 21 px left of the first glyph to 21 px right of Now Playing's, so the join is seamless (the slices are
# cut from one pane, the straight parts of a pane being identical). Pressed: a disc is the lighter glass; a capsule slice keeps the rest glass (the
# capsule stays one pane) with a round highlight on its glyph (NAV_PRESS_D, concentric with the cap ends: every glyph is 21 px from a cap's edge).
GLASS_H, GLASS_GLYPH = 42, 20                # the glass is 42 px high (y 4 .. 46 in a 50 px bar), the glyph's ink box 20 px (the navbar's NAV_K size)
NAV_SLOT_W, NAV_PLAY_W, NAV_CAPSULE_W = 46, 60, 141   # patch/offsets.inc NAV_VIEW_W; Now Playing's button; the pane of the capsule's pieces (any width: the Albums capsule is 177 .. 311, the Artists one 223 .. 311)
NAV_PRESS_D, NAV_PRESS_ALPHA = 36, 0.14      # a pressed slice's highlight: a white disc 36 px across (3 px of glass above and below it), 14 % opaque

def glass_piece(w, x0, x1, glyph, glyph_cx, pressed=False, cap=None, h=GLASS_H):
    """A w x h image whose glass covers columns [x0, x1): a disc (r = h / 2) when x1 - x0 == h, else the slice of the capsule cap = (c0, c1) (image
    columns, c1 - c0 wide, r = h / 2, the pane glass_image(c1 - c0, ...)); `glyph` (Lucide / 'T:' Tabler name) in white centred on column glyph_cx.
    Pressed: a disc's glass is the lighter one, a slice's the rest glass with the round highlight under the glyph. Straight-alpha RGBA."""
    from PIL import Image
    c0, c1 = cap or (x0, x1)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.alpha_composite(glass_image(c1 - c0, h, h // 2, pressed and not cap).crop((x0 - c0, 0, x1 - c0, h)), (x0, 0))
    if pressed and cap:
        d = disc(NAV_PRESS_D, WHITE); d.putalpha(d.getchannel('A').point(lambda v: round(v * NAV_PRESS_ALPHA)))
        out.alpha_composite(d, (glyph_cx - NAV_PRESS_D // 2, (h - NAV_PRESS_D) // 2))
    if glyph:
        g = glyph_fit(glyph, GLASS_GLYPH, GLASS_GLYPH, WHITE, 0, 2.0)
        out.alpha_composite(g, (glyph_cx - g.width // 2, (h - g.height) // 2))
    return out

# The slots are 46 apart but Now Playing's glyph is 53 right of the last slot's (its 60 px button keeps stock's glyph at 290), so every slot's glass and
# glyph is drawn NAV_SHIFT right of its button: the glyphs 152 / 198 / 244 / 290, 46 apart. The button (the touch) stays on main's slot; its image is
# NAV_SHIFT_W wide, centred on it (AWTK draws an icon centred at its own size), 2 x NAV_SHIFT wider, the content in its right NAV_SLOT_W columns.
NAV_SHIFT = 7
NAV_SHIFT_W = NAV_SLOT_W + 2 * NAV_SHIFT
# the capsule's pieces in the Pod pages' 46 px slots and Now Playing's 60 px button: position -> (w, glass columns, glyph centre, capsule columns)
S2 = 2 * NAV_SHIFT
CAPSULE_PIECES = {'left': (NAV_SHIFT_W, S2 + 2, S2 + 46, S2 + 23, (S2 + 2, S2 + 2 + NAV_CAPSULE_W)),
                  'middle': (NAV_SHIFT_W, S2, S2 + 46, S2 + 23, (S2 - 44, S2 + NAV_CAPSULE_W - 44)),
                  'right': (NAV_PLAY_W, NAV_SHIFT, 51, 30, (-90, 51)), 'only': (NAV_SHIFT_W, S2 + 2, S2 + 44, S2 + 23, None)}

def capsule_piece(position, glyph, pressed=False):
    w, x0, x1, cx, cap = CAPSULE_PIECES[position]
    return glass_piece(w, x0, x1, glyph, cx, pressed, cap)

# image -> (width, glass columns, glyph centre, glyph, capsule columns or None): the lone discs. Back (the Pod pages' 44 px button centres it: x 8 .. 50),
# Now Playing's disc (Pod pages, button x 260: glass 269 .. 311), the USB mode page's settings disc, and the album page's select mode (add / delete 146 / 221
# centred in their 60 px buttons at 116 / 191, cancel 290 in the one at 268, the all / unselect toggle 29 in its 50 px one at 0).
AH_NAV_PIECES = {'ah_nav_back': (42, 0, 42, 21, 'chevron-left', None), 'ah_nav_close': (42, 0, 42, 21, 'x', None), 'ah_nav_np': (NAV_PLAY_W, 9, 51, 30, 'audio-lines', None),
                 'ah_nav_set': (NAV_PLAY_W, 9, 51, 30, 'settings', None),   # the USB mode page's DAC settings (tools/mod_ipodrows.py edit_usbmode), on Now Playing's disc
                 'ah_nav_add': (NAV_PLAY_W, 9, 51, 30, 'plus', None), 'ah_nav_del': (NAV_PLAY_W, 9, 51, 30, 'trash', None), 'ah_nav_cancel': (NAV_PLAY_W, 1, 43, 22, 'x', None),
                 'ah_nav_unsel': (50, 8, 50, 29, 'circle', None)}
AH_NAV_SELECTED = ('ah_nav_sel', 'T:circle-check:filled')    # the select-all toggle's "all selected" state (a 50 px disc; no pressed image: stock has none)
AH_NAV_RIGHT = 'ah_nav_play'                                 # Now Playing as the capsule's right cap (Pod pages)
AH_NAV_NAMES = sorted([n + s for n in [*AH_NAV_PIECES, AH_NAV_RIGHT] for s in ('', '_down')] + [AH_NAV_SELECTED[0]])

def ah_nav_images():
    """The glass buttons' images (AH_NAV_NAMES)."""
    f = {}
    for suffix, pressed in (('', False), ('_down', True)):
        for n, (w, x0, x1, cx, g, cap) in AH_NAV_PIECES.items():
            f[n + suffix] = glass_piece(w, x0, x1, g, cx, pressed, cap)
        f[AH_NAV_RIGHT + suffix] = capsule_piece('right', 'audio-lines', pressed)
    w, x0, x1, cx, _ = (50, 8, 50, 29, 0)
    f[AH_NAV_SELECTED[0]] = glass_piece(w, x0, x1, AH_NAV_SELECTED[1], cx)
    assert sorted(f) == AH_NAV_NAMES
    return f

ALBUM += AH_NAV_NAMES

# The soft fade under a navbar that is an opaque bar (the iOS scroll-edge look): an insensitive image over the top of the list, black at its first row
# and transparent at its last, so rows dissolve as they scroll up under the bar. Asset only (no blur, no paint code). The curve is eased, so the rows
# at rest stay clear: alpha 255 (1 - t)^3.6, <= 8 from row 12 down (the first row of a text page has its ink from row 15, a switch from row 12). The cover pages
# (Albums, Playlists: covers from row 4 / 10) start with the fade hidden and show it only while scrolled (patch/albums.c, patch/playlists.c).
NB_FADE = ('nb_fade', 320, 20)
ALBUM.append(NB_FADE[0])

def nb_fade_alpha(y, h=NB_FADE[2]):
    return round(255 * (1 - (y + 0.5) / h) ** 3.6)

def nb_fade_image():
    from PIL import Image
    im = Image.new('RGBA', NB_FADE[1:], (0, 0, 0, 0))
    for y in range(NB_FADE[2]): im.paste((0, 0, 0, nb_fade_alpha(y)), (0, y, NB_FADE[1], y + 1))
    return im

def _aa(size, draw, scale=8, box=False):
    """Draw at scale x with draw(ImageDraw, s) in white on transparent, downsample (anti-aliased mask; box = a plain
    average, no ringing outside the shape)."""
    from PIL import Image, ImageDraw
    big = Image.new('L', (size[0] * scale, size[1] * scale), 0)
    draw(ImageDraw.Draw(big), scale)
    return big.resize(size, Image.BOX if box else Image.LANCZOS)

# the solid shapes, drawn at s x on a w x h canvas (white mask)
GRABBER = (36, 5, 11)               # w, h, y
# The transport glyphs ("B2 crisp"): our own rounded convex polygons (inset by r, then dilated by r: true round corners),
# drawn 16x and box-downsampled. Ink sizes in device px; docs/ui.md.
TSS = 16
PLAY_INK = (29, 31)                 # w x h of the rounded ink
PLAY_SHIFT = 1.5                    # optical centring: the ink sits this far right of the canvas centre
PLAY_R = 0.10                       # corner radius, x the play height
PAUSE_H, PAUSE_BAR_W, PAUSE_GAP, PAUSE_R = 28, 0.30, 0.36, 0.30       # height; bar width, gap (x height); radius (x bar width)
SKIP_H, SKIP_WR, SKIP_OV, SKIP_RK = 24, 1.46, 0.18, 0.6              # ink height; total width x height; overlap x triangle width; radius x the play radius
# The mini player bar's glyphs (patch/offsets.inc MB_*, docs/modules/minibar.md): the same shapes, bare white, drawn for the bar: pause 22 px tall, next 30 x 17,
# play 19 x 22 (a triangle as tall as the pause bars reads a little smaller, so the ink is as tall as the pause); pressed = 55 % white
MB_PLAY_INK, MB_PAUSE_H, MB_SKIP_H, MB_SKIP_W = (19, 22), 22, 17, 30
# The screensaver's play1 / pause1 (round 3 below): the same shapes on a 32 px disc, 12 x 14 play, 14 px pause; the triangle's corners a little rounder (0.16 of its height)
SS_PLAY_INK, SS_PAUSE_H, SS_PLAY_R = (12, 14), 14, 0.16

def _inset(poly, r):
    """A convex polygon moved inward by r (vertices intersect the offset edges)."""
    n = len(poly); area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1; lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]; dx, dy = x2 - x1, y2 - y1; ln = (dx * dx + dy * dy) ** .5
        lines.append((x1 - dy / ln * sgn * r, y1 + dx / ln * sgn * r, dx, dy))
    out = []
    for i in range(n):
        ax, ay, adx, ady = lines[i - 1]; bx, by, bdx, bdy = lines[i]
        t = ((bx - ax) * bdy - (by - ay) * bdx) / (adx * bdy - ady * bdx)
        out.append((ax + adx * t, ay + ady * t))
    return out

def _tri(x0, y0, w, h, fwd):
    return [(x0, y0), (x0 + w, y0 + h / 2), (x0, y0 + h)] if fwd else [(x0 + w, y0), (x0, y0 + h / 2), (x0 + w, y0 + h)]

def _tri_ink(w, h, r):
    """Width and height of the rounded triangle (pre-rounding box w x h, right-pointing)."""
    ip = _inset(_tri(0, 0, w, h, True), r)
    xs, ys = [p[0] for p in ip], [p[1] for p in ip]
    return max(xs) - min(xs) + 2 * r, max(ys) - min(ys) + 2 * r

def _fit_tri(ink_w, ink_h, r):
    """The pre-rounding (w, h) whose rounded ink is ink_w x ink_h."""
    w, h = ink_w, ink_h
    for _ in range(40):
        iw, ih = _tri_ink(w, h, r); w *= ink_w / iw; h *= ink_h / ih
    return w, h

def _round_poly(d, poly, r, s):
    ip = _inset(poly, r); n = len(ip)
    cx = sum(p[0] for p in poly) / n; cy = sum(p[1] for p in poly) / n
    d.polygon([(x * s, y * s) for x, y in ip], fill=255)
    for i in range(n):
        (x1, y1), (x2, y2) = ip[i], ip[(i + 1) % n]; dx, dy = x2 - x1, y2 - y1; ln = (dx * dx + dy * dy) ** .5
        nx, ny = dy / ln, -dx / ln
        if nx * ((x1 + x2) / 2 - cx) + ny * ((y1 + y2) / 2 - cy) < 0: nx, ny = -nx, -ny      # outward
        d.polygon([(x1 * s, y1 * s), (x2 * s, y2 * s), ((x2 + nx * r) * s, (y2 + ny * r) * s), ((x1 + nx * r) * s, (y1 + ny * r) * s)], fill=255)
        d.ellipse([(x1 - r) * s, (y1 - r) * s, (x1 + r) * s, (y1 + r) * s], fill=255)

def transport_mask(kind, size):
    """The 'L' mask of the transport glyph `kind` (play, pause, next, prev) on a size (px or (w, h)) canvas, ink centred."""
    from PIL import Image, ImageDraw
    cw, ch = size if isinstance(size, tuple) else (size, size)
    bar, ss = kind.startswith('mb_'), kind.startswith('ss_')      # the mini player bar's glyphs: the same shapes at the bar's sizes (MB_*); ss_: the screensaver's (SS_*)
    kind = kind.removeprefix('mb_').removeprefix('ss_')
    play_ink, pause_h, skip_h, skip_wr = (MB_PLAY_INK, MB_PAUSE_H, MB_SKIP_H, MB_SKIP_W / MB_SKIP_H) if bar else (PLAY_INK, PAUSE_H, SKIP_H, SKIP_WR)
    if ss: play_ink, pause_h = SS_PLAY_INK, SS_PAUSE_H
    play_r = SS_PLAY_R if ss else PLAY_R
    play_shift = PLAY_SHIFT * play_ink[1] / PLAY_INK[1]
    s = TSS; big = Image.new('L', (cw * s, ch * s), 0); d = ImageDraw.Draw(big)
    if kind == 'play':
        r = play_r * play_ink[1]; w, h = _fit_tri(*play_ink, r)
        iw, ih = _tri_ink(w, h, r)
        ip = _inset(_tri(0, 0, w, h, True), r); minx, miny = min(p[0] for p in ip), min(p[1] for p in ip)
        ox, oy = (cw - iw) / 2 + play_shift - (minx - r), (ch - ih) / 2 - (miny - r)
        _round_poly(d, _tri(ox, oy, w, h, True), r, s)
    elif kind == 'pause':
        bh = pause_h; bw, gap = PAUSE_BAR_W * bh, PAUSE_GAP * bh; x0, y0 = (cw - 2 * bw - gap) / 2, (ch - bh) / 2
        for x in (x0, x0 + bw + gap):
            d.rounded_rectangle([round(x * s), round(y0 * s), round((x + bw) * s) - 1, round((y0 + bh) * s) - 1], radius=PAUSE_R * bw * s, fill=255)
    else:
        fwd = kind == 'next'; r = SKIP_RK * PLAY_R * play_ink[1]; ink_w = skip_wr * skip_h
        w, h = _fit_tri(ink_w / (2 - SKIP_OV), skip_h, r)        # first guess for one triangle ...
        for _ in range(40):                                     # ... then the pair spans ink_w
            tw = _tri_ink(w, h, r)[0]; span = tw + (w - w * SKIP_OV)
            w *= ink_w / span; h = _fit_tri(w, skip_h, r)[1]
        ip = _inset(_tri(0, 0, w, h, True), r); iw0, ih = _tri_ink(w, h, r)
        total = iw0 + w * (1 - SKIP_OV); minx, miny = min(p[0] for p in ip) - r, min(p[1] for p in ip) - r
        ox, oy = (cw - total) / 2 - minx, (ch - ih) / 2 - miny
        for i in range(2):
            _round_poly(d, _tri(ox + i * w * (1 - SKIP_OV), oy, w, h, fwd), r, s)
    return big.resize((cw, ch), Image.BOX)

def g_grabber(d, s, w, h):
    # the sheet handle: a pill centred in the button's width, y px from its top
    pw, ph, y = GRABBER
    d.rounded_rectangle([(w - pw) / 2 * s, y * s, (w + pw) / 2 * s - 1, (y + ph) * s - 1], radius=ph / 2 * s, fill=255)

# The playing row's marker (patch/rows.c rows_track_icon): a 40 x 20 image drawn centred in the 40 px icon widget, the 20 px wave at
# its right end (x 20..40, flush with the titles' 298 px right margin); four round-ended bars, 3 px wide, 8/3 px apart.
WAVE_BARS, WAVE_W, WAVE_GAP, WAVE_PX = (8, 16, 20, 12), 3, 8 / 3, 20
def g_wave(d, s, w, h):
    x0 = w - WAVE_PX
    for i, bh in enumerate(WAVE_BARS):
        x, y = x0 + i * (WAVE_W + WAVE_GAP), (h - bh) / 2
        d.rounded_rectangle([round(x * s), round(y * s), round((x + WAVE_W) * s) - 1, round((y + bh) * s) - 1], radius=WAVE_W / 2 * s, fill=255)

AB_WAVE_PX, AB_WAVE_RGB = 12, (0xEE, 0xEE, 0xEC)   # AB_WAVE (patch/offsets.inc): the playing track's marker on the album page, the rows' wave (np_row_playing, 20 px) scaled to a square canvas
def ab_wave():
    from PIL import Image
    k, px = AB_WAVE_PX / WAVE_PX, AB_WAVE_PX
    def shape(d, s):
        for i, bh in enumerate(WAVE_BARS):
            x, y, w, h = i * (WAVE_W + WAVE_GAP) * k, (px - bh * k) / 2, WAVE_W * k, bh * k
            d.rounded_rectangle([round(x * s), round(y * s), round((x + w) * s) - 1, round((y + h) * s) - 1], radius=w / 2 * s, fill=255)
    im = Image.new('RGBA', (px, px), AB_WAVE_RGB); im.putalpha(_aa((px, px), shape, 16, True)); return im

def pil_glyph(kind, size, rgb, alpha=255):
    """The solid glyph `kind` (play, pause, next, prev, grabber) on a size (px or (w, h)) canvas, in rgb at alpha."""
    from PIL import Image
    w, h = size if isinstance(size, tuple) else (size, size)
    shape = {'grabber': g_grabber, 'wave': g_wave}.get(kind)
    if kind in ('stop', 'mb_stop'):   # Radio Now Playing's stop: a filled rounded square (the mini bar's, 18 of 32 px, sits lighter than the pause bars' 22 px)
        from PIL import ImageDraw
        ss, a = 8, round(min(w, h) * (0.5 if kind == 'stop' else 0.5625)); big = Image.new('L', (w * ss, h * ss), 0)
        ImageDraw.Draw(big).rounded_rectangle([(w * ss - a * ss) // 2, (h * ss - a * ss) // 2, (w * ss + a * ss) // 2 - 1, (h * ss + a * ss) // 2 - 1], radius=a * ss // 5, fill=255)
        mask = big.resize((w, h), Image.LANCZOS)
    else: mask = _aa((w, h), lambda d, s: shape(d, s, w, h), 16 if kind == 'wave' else 8, kind == 'wave') if shape else transport_mask(kind, (w, h))
    if alpha != 255: mask = mask.point(lambda v: v * alpha // 255)
    im = Image.new('RGBA', mask.size, rgb); im.putalpha(mask); return im

def ink_metrics(sil, ink):
    """(bbox centre, silhouette centroid) of a glyph, each (x, y) in px: `ink` is the rendered glyph, `sil` its filled
    silhouette (the same shape with the holes filled). The bbox edges are sub-pixel (an edge pixel counts by its coverage)."""
    w, h = ink.size
    a, s = ink.getchannel('A'), sil.getchannel('A')
    cols = [max(a.getpixel((x, y)) for y in range(h)) / 255 for x in range(w)]
    rows = [max(a.getpixel((x, y)) for x in range(w)) / 255 for y in range(h)]
    def edges(cov):
        idx = [i for i, v in enumerate(cov) if v > 0]
        return idx[0] + 1 - cov[idx[0]], idx[-1] + cov[idx[-1]]
    (x0, x1), (y0, y1) = edges(cols), edges(rows)
    tot = sum(s.getpixel((x, y)) for y in range(h) for x in range(w))
    cx = sum((x + 0.5) * s.getpixel((x, y)) for y in range(h) for x in range(w)) / tot
    cy = sum((y + 0.5) * s.getpixel((x, y)) for y in range(h) for x in range(w)) / tot
    return ((x0 + x1) / 2, (y0 + y1) / 2), (cx, cy)

NP_OPTICAL_STEP, NP_OPTICAL_MAX, NP_MARGIN = 0.25, 1.5, 3   # the glyph's sub-pixel shift (px, in steps), the most it may move, the room round it

def np_glyph(g, size, ink_px, rgb):
    """Glyph g (a 2.0 px stroke, `ink_px` ink) on a size x size canvas, placed by its optical centre: the middle of the ink's
    bounding box and of its silhouette's centroid (a star's lower points reach less far than its top one, so its box centre looks low), moved to
    the canvas centre in quarter-pixel steps by an SVG translation (not by whole pixels, which would leave up to 0.5 px)."""
    from PIL import Image
    n, solid = gname(g), is_filled(g)
    sw_px = 2.0
    px = fit_px(n, 'outline', solid, size, size, (size - ink_px) // 2, sw_px)
    off = (size - px - 2 * NP_MARGIN) // 2                    # the glyph's canvas (px + 2 NP_MARGIN, room for the shift) lies at (off, off)
    sw, t = sw_px * 24 / px, px + 2 * NP_MARGIN
    base = _rsvg(build_svg(n, 'outline', px, sw, solid, margin=NP_MARGIN), t)
    (bx, by), (cx, cy) = ink_metrics(_rsvg(build_svg(n, 'outline', px, sw, True, margin=NP_MARGIN), t), base)
    ox, oy = (bx + cx) / 2, (by + cy) / 2                      # the optical centre in the glyph canvas
    want = size / 2 - off                                      # where it belongs in that canvas
    q = lambda v: round(max(-NP_OPTICAL_MAX, min(NP_OPTICAL_MAX, v)) / NP_OPTICAL_STEP) * NP_OPTICAL_STEP
    dx, dy = q(want - ox), q(want - oy)
    im = _rsvg(build_svg(n, 'outline', px, sw, solid, dx, dy, margin=NP_MARGIN), t)
    a = im.getchannel('A')
    assert not any(a.crop(r).getbbox() for r in ((0, 0, t, 1), (0, t - 1, t, t), (0, 0, 1, t), (t - 1, 0, t, t))), f'{g}: the centred glyph touches its canvas edge'
    c = Image.new('RGBA', (size, size), (0, 0, 0, 0)); c.alpha_composite(im, (off, off))
    return tint(c, rgb) if rgb != WHITE else c

# The mini player bar's glass pill (mb_glass, mb_glass_down; patch/offsets.inc MB_W x MB_H, radius MB_R = h / 2; docs/modules/minibar.md): a translucent
# dark fill with a soft vertical sheen, a 1 px rim light that is brightest along the top arc and fades towards the bottom, and a faint inner highlight line
# just inside the top edge. Straight-alpha RGBA, anti-aliased (8x supersampled, box filter). Pressed: a brighter fill and rim.
GLASS = (304, 56, 28)                                         # w, h, radius
GLASS_CARD = (288, 334, 18)                                   # the lock screen's now-playing card (mod_lockscreen.py; docs/modules/lockscreen.md)
GLASS_SHEET6 = (320, 300, 18)                               # the same sheet with the Cassette and Vinyl rows (page 1, six rows): its own image, not a crop of a taller one (docs/modules/playmore.md)
GLASS_SHEET = (320, 250, 18)                                  # Now Playing's More sheet, page 2 (five rows: the back header, Speed, A-B repeat, Find Cover & Lyrics, Delete; patch/playmore.c, docs/modules/playmore.md): top corners only
GLASS_SHEET_FILL = ((0x2A, 0x2A, 0x2C), (0x1E, 0x1E, 0x20), 0.88)   # denser than the card (0.76): rows, labels and grey badges sit straight on it (docs/modules/playmore.md)
GLASS_VIEWSORT = (72, 336, 14)    # the Albums "..." card (patch/viewsort.c, docs/modules/albums.md): Search, Grid, List and four sort rows of 48 px; one picture per height
GLASS_VIEWSORT6 = (72, 288, 14)   # the same card one row short (one artist's albums: no Artist row): six rows
GLASS_VIEWSORT5 = (72, 240, 14)   # the Songs library's card: Select and the four sorts (five rows)
GLASS_VIEWSORT4 = (72, 192, 14)   # the Artists "..." card: Search, the two Show rows and Name (four rows)
GLASS_VIEWSORT1 = (72, 48, 14)    # the Genres and Composers "..." card: Name alone (one row); the Songs page's genre and artist lists: Select alone
GLASS_VIEWSORT2 = (72, 96, 14)    # the Songs page's lists with Search Songs and Select (two rows)
GLASS_VIEWSORT3 = (72, 144, 14)   # Recently Added's albums view: Search Songs, Grid, List (three rows)
GLASS_ROWMENU = (320, 250, 18)   # the track rows' menu (patch/rowmenu.c, docs/modules/rowmenu.md): Now Playing's More sheet's pane, five rows high, top corners only
GLASS_PEQDIALOG = (72, 276, 14)  # the band page's unsaved-changes dialog (docs/modules/peq.md "Preset editing"): the Playlists menu's pane, 76 px of head and four 50 px buttons high; drawn patch3_x
GLASS_BANDKEYPAD = (320, 320, 18)   # the band page's number keypad sheet (docs/modules/peq.md "Preset editing"): the track rows' menu's pane, 320 px high
GLASS_MENU = (72, 200, 14)    # the Playlists page's "..." menu card (patch/playlists.c, docs/modules/playlists.md): the sheet's glass, all four corners; drawn patch3_x
                              # (the middle 24 px stretched to the card's width), as tall as the card (tools/pod_ui.py PL_CARD_H)
GLASS_FILL = {False: ((0x2D, 0x2D, 0x2F), (0x23, 0x23, 0x25), 0.82), True: ((0x3A, 0x3A, 0x3C), (0x30, 0x30, 0x32), 0.86)}   # top rgb, bottom rgb, alpha
GLASS_CARD_FILL = ((0x2A, 0x2A, 0x2C), (0x1E, 0x1E, 0x20), 0.76)   # the card: a little more see-through (only its 12 px frame and the text band show)
GLASS_RIM = {False: (0.30, 0.08), True: (0.40, 0.14)}         # rim white alpha at the top and at the bottom row
GLASS_LINE = 0.07                                             # the inner highlight's alpha at the top, fading to 0 by mid height

def glass_image(w, h, r, pressed=False, fill=None, top_only=False):
    """A w x h glass pane of corner radius r; fill = (top rgb, bottom rgb, alpha) replaces the GLASS_FILL of the state.
    top_only: a sheet that sits on the screen's bottom edge: only the top corners are rounded, and the rim and the inner line
    run off the bottom (no light line along the foot, the sides carry the rim down, fading)."""
    from PIL import Image, ImageChops, ImageDraw
    k = 8
    def pill(inset, rad):
        im = Image.new('L', (w * k, h * k), 0)
        bot = (h - inset) * k - 1 + (4 * r * k if top_only else 0)       # past the canvas: the bottom corners and edge are cut off
        ImageDraw.Draw(im).rounded_rectangle([inset * k, inset * k, (w - inset) * k - 1, bot], radius=rad * k, fill=255)
        return im
    def small(im): return im.resize((w, h), Image.BOX)
    body, rim_ring = small(pill(0, r)), small(ImageChops.subtract(pill(0, r), pill(1, r - 1)))
    line_ring = small(ImageChops.subtract(pill(1, r - 1), pill(2, r - 2)))
    top, bot, alpha = fill or GLASS_FILL[pressed]
    def col(y): return tuple(round(t + (b - t) * y / (h - 1)) for t, b in zip(top, bot))
    fill = Image.new('RGBA', (w, h))
    for y in range(h): fill.paste(col(y) + (round(255 * alpha),), (0, y, w, y + 1))
    fill.putalpha(ImageChops.multiply(fill.getchannel('A'), body))
    def ramp(a0, a1, span):   # a white layer through `ring`, its alpha a0 on row 0 to a1 at row `span`
        g = Image.new('L', (w, h))
        for y in range(h): g.paste(round(255 * (a0 + (a1 - a0) * min(y / span, 1))), (0, y, w, y + 1))
        return g
    def white(ring, g):
        lay = Image.new('RGBA', (w, h), (255, 255, 255, 0)); lay.putalpha(ImageChops.multiply(ring, g)); return lay
    out = fill
    out = Image.alpha_composite(out, white(line_ring, ramp(GLASS_LINE, 0, h / 2)))
    out = Image.alpha_composite(out, white(rim_ring, ramp(*GLASS_RIM[pressed], h - 1)))
    return out

def np_disc(size, disc_px, alpha, g, ink, rgb):
    """A size x size canvas: a flat white disc of disc_px at `alpha` centred, the glyph g (ink px) over it, centred optically."""
    from PIL import Image
    d = disc(disc_px, (255, 255, 255)); d.putalpha(d.getchannel('A').point(lambda v: v * alpha // 255))
    c = Image.new('RGBA', (size, size), (255, 255, 255, 0)); o = (size - disc_px) // 2
    c.alpha_composite(d, (o, o)); c.alpha_composite(np_glyph(g, size, ink, rgb)); return c

def np_images():
    """The Now Playing glyphs (mod_nowplaying.py): the tones of NP_TONES, pressed #8C8C8C (the grabber: brighter); the
    transport glyphs are the solid PIL-drawn shapes, star and More sit on a translucent disc, the rest Tabler."""
    out = {}
    for n, (g, px, ink, tone, down, *rest) in NP.items():
        for name, pressed in ((n, False), (down, True)):
            if not name: continue
            rgb, alpha = (NP_PRESSED.get(tone) or (NP_DIM, 255)) if pressed else NP_TONES[tone]
            if g == 'pil:glass': out[name] = glass_image(*GLASS, pressed)
            elif g == 'pil:glass_card': out[name] = glass_image(*GLASS_CARD, fill=GLASS_CARD_FILL)
            elif g == 'pil:glass_sheet': out[name] = glass_image(*GLASS_SHEET, fill=GLASS_SHEET_FILL, top_only=True)
            elif g == 'pil:glass_sheet6': out[name] = glass_image(*GLASS_SHEET6, fill=GLASS_SHEET_FILL, top_only=True)
            elif g == 'pil:glass_menu': out[name] = glass_image(*GLASS_MENU, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort': out[name] = glass_image(*GLASS_VIEWSORT, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort6': out[name] = glass_image(*GLASS_VIEWSORT6, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort5': out[name] = glass_image(*GLASS_VIEWSORT5, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort4': out[name] = glass_image(*GLASS_VIEWSORT4, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort1': out[name] = glass_image(*GLASS_VIEWSORT1, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort2': out[name] = glass_image(*GLASS_VIEWSORT2, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_viewsort3': out[name] = glass_image(*GLASS_VIEWSORT3, fill=GLASS_SHEET_FILL)
            elif g == 'pil:glass_rowmenu': out[name] = glass_image(*GLASS_ROWMENU, fill=GLASS_SHEET_FILL, top_only=True)
            elif g == 'pil:glass_bandkeypad': out[name] = glass_image(*GLASS_BANDKEYPAD, fill=GLASS_SHEET_FILL, top_only=True)
            elif g == 'pil:glass_peqdialog': out[name] = glass_image(*GLASS_PEQDIALOG, fill=GLASS_SHEET_FILL)
            elif g.startswith('pil:'): out[name] = pil_glyph(g[4:], px, rgb, alpha)
            elif rest: out[name] = np_disc(px, rest[0], NP_DISC_ALPHA_DOWN if pressed else NP_DISC_ALPHA, g, ink, rgb)
            else: out[name] = glyph_fit(g, px, px, rgb, (px - ink) // 2, 1.5 if ink < 22 else None)   # the small mode / queue glyphs keep a 1.5 px stroke
    return out

# ---------------------------------------------------------------- one ring style for every pull-down tile (docs/ui.md)
RING_OFF, RING_DIS, RING_ON_GLYPH = (0x77,) * 3, (0x44,) * 3, (0x14,) * 3
TILE_GLYPH, TILE_TEXT = 24, 17      # glyph px (24 grid, stroke 2) and "PO" / "LO" text px inside the 50 px ring
TILE_FONT = os.path.join(ROOT, 'assets', 'fonts', 'Inter-m1plus.ttf')
# tile image -> (glyph or 'text:XX', state); the stock geometry: 50 x 50, the circle touching the bounds
TILES = {
    'drop_wifi': ('wifi', 'off'), 'drop_wifiopen': ('wifi', 'on'), 'drop_bt': ('bluetooth', 'off'),
    'drop_btopen': ('bluetooth', 'on'), 'drop_keylock': ('lock', 'off'), 'drop_keylockopen': ('lock', 'on'),
    'drop_eq': ('sliders-vertical', 'off'), 'drop_eqopen': ('sliders-vertical', 'on'),
    'drop_usbaudio': ('usb', 'on'), 'drop_usbdac': ('+dac', 'on'), 'drop_usbstorage': ('hard-drive', 'on'),
    'drop_playset': ('sliders-horizontal', 'off'), 'drop_playsetdown': ('sliders-horizontal', 'on'),
    'drop_sysset': ('settings', 'off'), 'drop_syssetdown': ('settings', 'on'),
    'drop_lowgain': ('+gain-low', 'off'), 'drop_highgain': ('+gain-high', 'on'),
    'drop_lowgaindisable': ('+gain-low', 'dis'), 'drop_highgaindisable': ('+gain-high', 'dis'),
    'drop_po': ('text:PO', 'off'), 'drop_lo': ('text:LO', 'on')}
TILES_NEW = ['drop_lowgain', 'drop_highgain', 'drop_lowgaindisable', 'drop_highgaindisable', 'drop_po', 'drop_lo']

def ring_tile(g, state, on_style='disc'):
    """50 x 50 tile: off = grey ring + grey glyph, dis = dark-grey, on = white filled disc + dark glyph
    ('disc') or white ring + white glyph ('ring', the alternative documented in docs/ui.md)."""
    from PIL import Image, ImageDraw, ImageFont
    ss, N, sw = 4, 50, 2
    big = Image.new('L', (N * ss, N * ss), 0); dr = ImageDraw.Draw(big)
    filled = state == 'on' and on_style == 'disc'
    if filled: dr.ellipse((0, 0, N * ss - 1, N * ss - 1), fill=255)
    else:
        dr.ellipse((0, 0, N * ss - 1, N * ss - 1), fill=255); dr.ellipse((sw * ss, sw * ss, (N - sw) * ss - 1, (N - sw) * ss - 1), fill=0)
    col = {'off': RING_OFF, 'dis': RING_DIS, 'on': WHITE}[state]
    gcol = RING_ON_GLYPH if filled else col
    t = Image.new('RGBA', (N, N), col + (0,)); t.putalpha(big.resize((N, N), Image.LANCZOS))
    if g.startswith('text:'):
        f = ImageFont.truetype(TILE_FONT, TILE_TEXT); bb = f.getbbox(g[5:])
        ti = Image.new('RGBA', (bb[2] - bb[0] + 2, bb[3] - bb[1] + 2), gcol + (0,))
        m = Image.new('L', ti.size, 0); ImageDraw.Draw(m).text((1 - bb[0], 1 - bb[1]), g[5:], font=f, fill=255)
        ti.putalpha(m); gi = ti
    else: gi = ink_crop(glyph(g, TILE_GLYPH, 'tile', gcol))
    t.alpha_composite(gi, ((N - gi.width) // 2, (N - gi.height) // 2)); return t


# ---------------------------------------------------------------- round 3: playback, badges, controls, hero art
# Stock images that were still stock after round 2 (docs/modules/icons.md "Round 3"). Kept stock: every MQA image, eq_*, vol_dot,
# vol_progressbak, volume_bg, charge_big, dac_charge.
R3_DISC_A, R3_DISC_A_DOWN = 51, 102           # the translucent white disc behind the screensaver's transport shapes: 20 %, pressed 40 %
PM_DISC_A, PM_DISC_A_DOWN, PM_GLYPH_A_DOWN = 51, 90, 205   # the volume / Bluetooth plus and minus discs: 20 %, pressed 35 %; the pressed glyph 80 % white
# image -> (glyph, canvas px, disc px, glyph px = its canvas, stroke px); even canvas and stroke put the bar edges on pixel boundaries
PM_BUTTONS = {'vol_add': ('plus', 44, 42, 32, 2), 'vol_dec': ('minus', 44, 42, 32, 2), 'bt_add': ('plus', 100, 90, 64, 4), 'bt_dec': ('minus', 100, 90, 64, 4)}
PM_DOWN = {'vol_add': 'vol_adddown', 'vol_dec': 'vol_decdown', 'bt_add': 'bt_add_down', 'bt_dec': 'bt_dec_down'}
PM_CHECK = ('T:circle-check:filled', 80, 52, 14, 77)    # led_select: glyph, canvas, glyph px, its offset, disc alpha (30 %)
R3_BADGES = {'p_hr': ('HR', (28, 18)), '16bit': ('16bit', (40, 18)), '24bit': ('24bit', (40, 18))}   # white outline badges (badge()); replaygain is the settings' RG badge centred in 40 px
R3_SUNS = {'light_lefticon': 'sun-dim', 'light_righticon': 'sun'}
R3_PLAYING = ('audio-lines', 40, 24)            # icon_playing: a bare white glyph (canvas, ink px)
R3_QUEUE = 'list-music'                         # p_playqueue (+ down, #777777): sized like SMALL_GLYPHS
# hero art (the USB DAC / storage, Wi-Fi transfer and Bluetooth receiver pages): a dark grey gradient disc with a 1 px rim and soft rings.
# image -> (disc px, glyph, glyph px); the stock images are 250 / 250 / 210 / 254 px
HERO = {'usb_dac': (146, 'usb', 76), 'usb_storage': (146, 'hard-drive', 76), 'wifits_icon': (104, 'wifi', 58), 'btrecv_icon': (116, 'bluetooth', 64)}
HERO_TOP, HERO_BOT, HERO_K = (0x30,) * 3, (0x1A,) * 3, 4
HERO_GLYPH = (0xC0,) * 3                     # the glyph's grey: softer than white, so it sits in the disc
HERO_RIM = (0.34, 0.14)                          # rim white alpha at the disc's top and bottom
HERO_RINGS, HERO_LINE_A, HERO_GLOW_A, HERO_GLOW_BLUR = 3, (0.32, 0.23, 0.14), 0.06, 1.2   # ring lines' alpha (inner to outer), the glow step per band, the glow's blur (px)
# chargebg: the stock empty battery frame (charge_big) with the white Lucide battery-charging bolt, 60 % of the first design's size, centred
CHARGE_FRAME_SHA = '0911a86708c1ea3d157e5cd7c6551fd377374411a7f30d0acca63c57eb956154'   # stock charge_big.png, the frame (pinned: it is read, not replaced)
BOLT_PTS, BOLT_SCALE = [(11, 7), (8, 12), (12, 12), (9, 17)], 8.6 * 0.6    # grid units; px per grid unit
R3_GLYPHS = ['plus', 'minus', 'sun-dim', 'sun', 'list-music', 'audio-lines', 'usb', 'hard-drive', 'wifi', 'bluetooth', 'T:circle-check:filled']

def alpha_scale(im, a):
    im = im.copy(); im.putalpha(im.getchannel('A').point(lambda v: v * a // 255)); return im

def translucent_disc(size, disc_px, alpha, ss=8):
    """A size x size canvas with a centred flat white disc of disc_px at `alpha`."""
    from PIL import Image, ImageDraw
    big = Image.new('L', (size * ss, size * ss), 0); o = (size - disc_px) / 2 * ss
    ImageDraw.Draw(big).ellipse((o, o, o + disc_px * ss - 1, o + disc_px * ss - 1), fill=alpha)
    im = Image.new('RGBA', (size, size), WHITE + (0,)); im.putalpha(big.resize((size, size), Image.BOX)); return im

def screensaver_transport(kind, pressed, size=36, disc_px=32):
    from PIL import Image
    c = translucent_disc(size, disc_px, R3_DISC_A_DOWN if pressed else R3_DISC_A)
    g = Image.new('RGBA', (size, size), WHITE + (0,)); g.putalpha(transport_mask('ss_' + kind, size))
    c.alpha_composite(g); return c

def pm_button(g, size, disc_px, ink, sw, pressed):
    c = translucent_disc(size, disc_px, PM_DISC_A_DOWN if pressed else PM_DISC_A)
    gl = _rsvg(build_svg(g, 'outline', ink, sw * 24 / ink, False), ink)
    if pressed: gl = alpha_scale(gl, PM_GLYPH_A_DOWN)
    c.alpha_composite(gl, ((size - ink) // 2, (size - ink) // 2)); return c

def led_select_image():
    g, size, px, off, alpha = PM_CHECK
    c = translucent_disc(size, size, alpha); c.alpha_composite(glyph_fit(g, px, px, WHITE, 0), (off, off)); return c

def hero_disc(size, d):
    """The dark grey disc of diameter d centred in size x size: a vertical gradient HERO_TOP to HERO_BOT, a 1 px rim whose white alpha fades from HERO_RIM[0] to [1]."""
    from PIL import Image, ImageChops, ImageDraw
    k = HERO_K; s = size * k; cx = s / 2; r = d * k / 2; y0, y1 = cx - r, cx + r
    mask = Image.new('L', (s, s), 0); ImageDraw.Draw(mask).ellipse([cx - r, cx - r, cx + r, cx + r], fill=255)
    inner = Image.new('L', (s, s), 0); ImageDraw.Draw(inner).ellipse([cx - r + k, cx - r + k, cx + r - k, cx + r - k], fill=255)
    grad, ra = Image.new('RGBA', (s, s)), Image.new('L', (s, s))
    for y in range(s):
        t = min(max((y - y0) / (y1 - y0), 0), 1)
        grad.paste(tuple(round(a + (b - a) * t) for a, b in zip(HERO_TOP, HERO_BOT)) + (255,), (0, y, s, y + 1))
        ra.paste(round(255 * (HERO_RIM[0] + (HERO_RIM[1] - HERO_RIM[0]) * t)), (0, y, s, y + 1))
    grad.putalpha(mask)
    rim = Image.new('RGBA', (s, s), WHITE + (0,)); rim.putalpha(ImageChops.multiply(ImageChops.subtract(mask, inner), ra))
    grad.alpha_composite(rim); return grad.resize((size, size), Image.LANCZOS)

def hero_rings(size, d):
    """Soft concentric rings round the disc: HERO_RINGS thin lines of fading alpha over a faint blurred glow."""
    from PIL import Image, ImageDraw, ImageFilter
    k, n = HERO_K, HERO_RINGS; s = size * k; cx = s / 2; r0 = d * k / 2; rmax = size * k / 2 - 2 * k
    rad = lambda i: r0 + (rmax - r0) * i / n
    glow = Image.new('RGBA', (s, s), (0, 0, 0, 0)); gd = ImageDraw.Draw(glow)
    for i in range(n, 0, -1): gd.ellipse([cx - rad(i), cx - rad(i), cx + rad(i), cx + rad(i)], fill=(255, 255, 255, round(255 * HERO_GLOW_A * (n - i + 1))))
    glow = glow.filter(ImageFilter.GaussianBlur(k * HERO_GLOW_BLUR)); glow.putalpha(glow.getchannel('A').point(lambda v: v * 6 // 10))
    lines = Image.new('RGBA', (s, s), (0, 0, 0, 0)); ld = ImageDraw.Draw(lines)
    for i in range(1, n + 1): ld.ellipse([cx - rad(i), cx - rad(i), cx + rad(i), cx + rad(i)], outline=(255, 255, 255, round(255 * HERO_LINE_A[i - 1])), width=k)
    glow.alpha_composite(lines); return glow.resize((size, size), Image.LANCZOS)

def hero_image(size, d, g, gpx):
    c = hero_rings(size, d); c.alpha_composite(hero_disc(size, d))
    gl = tint(render(g, gpx, 'outline', 2), HERO_GLYPH); ink = gl.getchannel('A').getbbox()
    c.alpha_composite(gl, (round(size / 2 - (ink[0] + ink[2]) / 2), round(size / 2 - (ink[1] + ink[3]) / 2))); return c

def charge_bolt_image():
    """The stock empty battery frame (charge_big) with a white bolt, drawn at 8x as a 2-unit round stroke polyline."""
    from PIL import Image, ImageDraw
    path = os.path.join(find_stock_img(), 'charge_big.png')
    assert sha256(open(path, 'rb').read()) == CHARGE_FRAME_SHA, 'charge_big.png is not the pinned stock file'
    base = read_png(path).convert('RGBA'); w, h = base.size; s = 8
    big = Image.new('RGBA', (w * s, h * s), (0, 0, 0, 0)); d = ImageDraw.Draw(big)
    sc = BOLT_SCALE * s; mx = sum(p[0] for p in BOLT_PTS) / len(BOLT_PTS); my = (BOLT_PTS[0][1] + BOLT_PTS[-1][1]) / 2
    pts = [(w * s / 2 + (x - mx) * sc, h * s / 2 + (y - my) * sc) for x, y in BOLT_PTS]
    sw = 2 * sc * 0.55; d.line(pts, fill=WHITE + (255,), width=round(sw), joint='curve')
    for x, y in pts: d.ellipse([x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2], fill=WHITE + (255,))
    base.alpha_composite(big.resize((w, h), Image.LANCZOS)); return base

# the Update Library spinner (scanmusic_dialog img_animation: scan1..scan12, 200x200, 100 ms a frame): a white arc with a fading
# tail sweeping round a faint track; the song count (label_msg1) sits in the middle
SCAN_FRAMES, SCAN_SIZE = 12, 200
SCAN_R, SCAN_W, SCAN_TRACK_A, SCAN_TAIL, SCAN_TAIL_GAMMA = 84, 5, 30, 240, 1.6   # radius, stroke (px), track alpha, tail (degrees), alpha ramp

def scan_frame(i):
    """Frame i (0-based): the head at 12 o'clock + i/SCAN_FRAMES of a turn, the tail's alpha ramping up to it."""
    from PIL import Image, ImageDraw
    k = HERO_K; s = SCAN_SIZE * k; c = s / 2; r, w = SCAN_R * k, SCAN_W * k; box = [c - r, c - r, c + r, c + r]
    im = Image.new('RGBA', (s, s), WHITE + (0,)); d = ImageDraw.Draw(im)
    d.ellipse(box, outline=WHITE + (SCAN_TRACK_A,), width=w)
    head, steps = -90 + 360 * i / SCAN_FRAMES, 60
    for j in range(steps):
        a0 = head - SCAN_TAIL + SCAN_TAIL * j / steps
        d.arc(box, a0, a0 + SCAN_TAIL / steps + 1, fill=WHITE + (round(255 * (j / steps) ** SCAN_TAIL_GAMMA),), width=w)
    hx, hy = c + (r - w / 2) * math.cos(math.radians(head)), c + (r - w / 2) * math.sin(math.radians(head))
    d.ellipse([hx - w / 2, hy - w / 2, hx + w / 2, hy + w / 2], fill=WHITE + (255,))     # the round head
    return im.resize((SCAN_SIZE, SCAN_SIZE), Image.LANCZOS)

SCAN_NAMES = [f'scan{i}' for i in range(1, SCAN_FRAMES + 1)]

def r3_images():
    """The round 3 images (R3_NAMES)."""
    f = {}
    for n in ('play1', 'pause1'):
        f[n] = screensaver_transport(n[:-1], False); f[n + '_down'] = screensaver_transport(n[:-1], True)
    f['icon_playing'] = np_glyph(R3_PLAYING[0], R3_PLAYING[1], R3_PLAYING[2], WHITE)
    f['p_playqueue'] = glyph_box(R3_QUEUE, (24, 22), NAV_K, WHITE)
    f['p_playqueuedown'] = glyph_box(R3_QUEUE, (24, 22), NAV_K, (0x77,) * 3)
    for n, (text, size) in R3_BADGES.items(): f[n] = badge(text, size=size)
    f['replaygain'] = bare_icon('badge:RG', 40)
    for n, (g, size, d, ink, sw) in PM_BUTTONS.items():
        f[n] = pm_button(g, size, d, ink, sw, False); f[PM_DOWN[n]] = pm_button(g, size, d, ink, sw, True)
    f['led_select'] = led_select_image()
    for n, g in R3_SUNS.items(): f[n] = glyph_fit(g, 24, 24, WHITE, 0)
    for n, (d, g, gpx) in HERO.items(): f[n] = hero_image(HERO_SIZE[n], d, g, gpx)
    f['chargebg'] = charge_bolt_image()
    for i, n in enumerate(SCAN_NAMES): f[n] = scan_frame(i)
    return f

HERO_SIZE = {'usb_dac': 250, 'usb_storage': 250, 'wifits_icon': 210, 'btrecv_icon': 254}
R3_NAMES = sorted(['play1', 'play1_down', 'pause1', 'pause1_down', 'icon_playing', 'p_playqueue', 'p_playqueuedown', 'replaygain', 'led_select',
                   'chargebg'] + list(R3_BADGES) + list(R3_SUNS) + list(PM_BUTTONS) + list(PM_DOWN.values()) + list(HERO) + SCAN_NAMES)

# ---------------------------------------------------------------- stock pins
# SHA-256 of each file this step replaces, in the stock V2.1 images/xx (the tree the other steps start from)
_PIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mod_icons_pins.txt')

def replaced_names():
    return sorted(set(TILES_NEW) | set(
        [n for n, _, g in SETTINGS + LISTS if g] + [n for n, _, g in HOME if g] + [n + '_down' for n, _, g in HOME if g] +
        ['drop_wifi', 'drop_wifiopen', 'drop_bt', 'drop_btopen', 'drop_keylock', 'drop_keylockopen', 'drop_eq',
         'drop_eqopen', 'drop_usbaudio', 'drop_usbdac', 'drop_usbstorage', 'drop_playset', 'drop_sysset',
         'drop_playsetdown', 'drop_syssetdown', 'drop_lighticon0', 'drop_lighticon1',
         'bar_play', 'bar_pause', 'bar_bt', 'bar_btcon', 'bar_digital'] + [f'bar_vol{i}' for i in range(5)] +
        [f'bar_wifi{i}' for i in range(5)] + COVERS +
        [n for n, _, _ in GLYPHS] + [d for _, _, d in GLYPHS if d] + [n for n, _ in DISCS] + RECOLOUR +
        list(SPEEDS) + list(PLAYALL) + list(WIFI_LOCK) + R3_NAMES))

def pod_row_names(): return sorted({n for n, _ in POD_ROWS.values()})
def nav_names(): return sorted(set(NAV_VIEW) | {n + '_down' for n in NAV_VIEW})
def pod_names(): return sorted(set(pod_row_names()) | set(FOLDER_ROWS) | set(SUBSONIC_ICONS) | set(SUBSONIC_ART) | set(RADIO_ROWS) | {RADIO_ART[0]} | set(POD_HOME) | set(nav_names()) | set(ALBUM) | set(DAILY) | {SHOT_BAR[0], LO_BAR, SYNC_BAR[0], SYNC_DM} | {n for n, _ in PL_MENU_ICONS} | {n for n, _ in RM_MENU_ICONS} | {RM_FAV_ON[0], RM_DOTS[0]})
def np_names(): return sorted(set(NP) | {v[4] for v in NP.values() if v[4]})

def added_rels(stock_rootfs=None, *args):
    """Rootfs-relative paths of the files this step adds (fwtool --allow-added): the M1+ Music row icons."""
    return [f'{IMG.removeprefix("rootfs/")}/{n}.png' for n in pod_names()]

def sha256(b): return hashlib.sha256(b).hexdigest()

def load_pins():
    pins = {}
    for line in open(_PIN_FILE):
        if line.strip() and not line.startswith('#'):
            h, n = line.split(); pins[n] = h
    return pins

def read_png(path):
    from PIL import Image
    im = Image.open(path); im.load(); return im

def find_stock_img():
    stock = paths.find_stock(paths.ZIP)
    if not stock: sys.exit('no unpacked stock tree found (run tools/build.py once)')
    return os.path.join(stock, IMG)

# ---------------------------------------------------------------- commands
def cmd_pins():
    d = find_stock_img()
    with open(_PIN_FILE, 'w') as o:
        o.write('# SHA-256 of the stock V2.1 images/xx files tools/mod_icons.py replaces (tools/mod_icons.py --pins)\n')
        for n in replaced_names(): o.write(f'{sha256(open(os.path.join(d, n + ".png"), "rb").read())}  {n}\n')

def cmd_generate():
    d = find_stock_img(); sizes = {}
    for n in replaced_names():
        im = read_png(os.path.join(d, n + '.png')); sizes[n] = im.size
        if n in COVERS:
            sizes[n + ':mode'] = im.mode; sizes[n + ':bg'] = im.convert('RGB').getpixel((2, 2))
    files = generate_all(sizes)
    assert sorted(files) == sorted(replaced_names() + pod_names()), set(files) ^ set(replaced_names() + pod_names())
    nps = np_images(); assert sorted(nps) == np_names(), set(nps) ^ set(np_names())
    files.update(nps)
    shutil.rmtree(PNG, ignore_errors=True); os.makedirs(PNG)
    for n, im in sorted(files.items()):
        want = sizes.get(n)
        assert n in pod_names() + np_names() or im.size == want, (n, im.size, want)
        if n in VINYL: open(os.path.join(PNG, n + '.png'), 'wb').write(png_pack.pack(im))   # (the Vinyl pictures only: smallest lossless, tools/png_pack.py)
        else: im.save(os.path.join(PNG, n + '.png'), optimize=True)
    print(f'{len(files)} PNGs, {sum(os.path.getsize(os.path.join(PNG, f)) for f in os.listdir(PNG))} bytes -> {PNG}')

def cmd_fetch(tgz):
    data = open(tgz, 'rb').read(); h = sha256(data)
    lucide, tabler = used_glyphs()
    if h == LUCIDE_SHA:
        shutil.rmtree(LUCIDE_SVG, ignore_errors=True); os.makedirs(LUCIDE_SVG)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for n in lucide: open(os.path.join(LUCIDE_SVG, n + '.svg'), 'wb').write(t.extractfile(f'package/icons/{n}.svg').read())
            open(os.path.join(LUCIDE, 'LICENSE'), 'wb').write(t.extractfile('package/LICENSE').read())
        print('lucide svg sources:', len(os.listdir(LUCIDE_SVG)))
    elif h == TGZ_SHA:
        shutil.rmtree(SVG, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for style in ('outline', 'filled'):
                os.makedirs(os.path.join(SVG, style), exist_ok=True)
                for n in tabler:
                    try: m = t.getmember(f'package/icons/{style}/{n}.svg')
                    except KeyError:
                        assert style == 'filled', f'missing outline glyph {n}'; continue
                    open(os.path.join(SVG, style, n + '.svg'), 'wb').write(t.extractfile(m).read())
            open(os.path.join(ASSET, 'LICENSE'), 'wb').write(t.extractfile('package/LICENSE').read())
        print('tabler svg sources:', {s: len(os.listdir(os.path.join(SVG, s))) for s in ('outline', 'filled')})
    else: sys.exit('tarball SHA-256 mismatch (pinned: lucide-static 1.61.0 or @tabler/icons 3.49.0)')

def check_assets(stock_dir, work_dir=None):
    """Asset PNGs against the stock files: same size and mode; pins match; optional work tree check."""
    pins = load_pins(); n_ok = 0
    assert sorted(pins) == replaced_names(), 'pin file out of date (mod_icons.py --pins)'
    for n in replaced_names():
        sp = os.path.join(stock_dir, n + '.png')
        assert sha256(open(sp, 'rb').read()) == pins[n], f'{n}.png: stock file does not match the pin'
        s, a = read_png(sp), read_png(os.path.join(PNG, n + '.png'))
        size = s.size
        assert (a.size, a.mode, a.format) == (size, s.mode, 'PNG') and s.format == 'PNG', f'{n}.png: {a.size} {a.mode} vs {size} {s.mode}'
        if work_dir:
            w = read_png(os.path.join(work_dir, n + '.png'))
            assert (w.size, w.mode) == (s.size, s.mode), f'{n}.png in the work tree has an unexpected format'
        n_ok += 1
    return n_ok

def apply(src, out):
    clone_workdir(src, out)
    d = os.path.join(out, IMG)
    n_ok = check_assets(find_stock_img(), d)
    total_old = total_new = 0
    for n in replaced_names():
        p = os.path.join(d, n + '.png'); new = open(os.path.join(PNG, n + '.png'), 'rb').read()
        total_old += os.path.getsize(p); mode = os.stat(p).st_mode
        write_keep_mode(p, new); total_new += len(new)
        im = read_png(p); assert im.size == read_png(os.path.join(PNG, n + '.png')).size    # round trip
        assert stat.S_IMODE(os.stat(p).st_mode) == stat.S_IMODE(mode)
    n_rows = apply_pod_rows(out, POD_ROWS)
    add_home_icon(out)
    add_nav_icons(out)
    add_album_icons(out)
    print(f'icons: {n_ok} images replaced, {total_old} -> {total_new} bytes ({total_new - total_old:+d}); {n_rows} M1+ Music row icons '
          f'and the Home grid icon ({POD_HOME_STYLE}) added')

IMG_MODE, IMG_MTIME = 0o755, 1750924035     # as the other added images (mod_nowplaying.py)
UI_DIR = 'rootfs/release/assets/default/raw/ui'

def apply_pod_rows(out, rows):
    """Bare glyphs on the M1+ Music menu / Shuffle / Settings / Extras / Main Menu rows: an insensitive image at the row's
    left, the title at POD_TEXT_X, and the hairline under the row inset to start under the title: the theme's full-width
    one (list_item_style's bottom border) is switched off for these rows and an insensitive 1 px view, pod_hair, draws it
    from HAIR_X to the row's right edge (the pressed band stays the full-width theme colour). Row height, chevrons,
    names and the payload's row table untouched."""
    from awtk_ui import Widget
    if not any(os.path.exists(os.path.join(out, UI_DIR, k + '.bin')) for k in POD_UI): return 0
    used = {}
    def edit(root):
        for row in [w for w in root.walk() if w.type == 'list_item' and w.name.startswith('pod_row')]:
            lab = next(c for c in row.children if c.type == 'hscroll_label')
            assert not any(c.name == 'pod_icon' for c in row.children), 'already has icons'
            text = pod_i18n.shown_english(lab); assert text in rows, f'no icon for the row {text!r}'
            img = rows[text][0]; used[img] = 1
            right = min([c.x - 7 if c.get('image') == 'right_arrow' else c.x for c in row.children if c.type in ('image', 'button') or c.name.startswith('pod_value')] or [row.w - 12])   # the chevron, switch, up arrow or value
            lab.x, lab.w = POD_TEXT_X, right - POD_TEXT_X
            ic = Widget('image', POD_ICON_X, (row.h - POD_ICON) // 2, POD_ICON, POD_ICON,
                        [('name', 'pod_icon'), ('image', img), ('draw_type', 'icon'), ('sensitive', 'false')])
            row.children.insert(0, ic)
            for st in ROW_STATES: row.set(f'style:{st}:border_width', '0')
            hair = Widget('view', HAIR_X, row.h - 1, min(row.w, 310) - HAIR_X, 1, [('name', 'pod_hair'), ('sensitive', 'false')])
            for st in ROW_STATES: hair.set(f'style:{st}:bg_color', HAIR_COLOUR)
            row.children.append(hair)
    for k in POD_UI:
        p = os.path.join(out, UI_DIR, k + '.bin')
        if os.path.exists(p):
            edit_ui(p, edit); os.utime(p, (IMG_MTIME, IMG_MTIME))   # an added file: keep the build deterministic
    d = os.path.join(out, IMG)
    for n in used:
        p = os.path.join(d, n + '.png'); assert not os.path.exists(p), f'{n}.png already in the tree'
        shutil.copyfile(os.path.join(PNG, n + '.png'), p); os.chmod(p, IMG_MODE); os.utime(p, (IMG_MTIME, IMG_MTIME))
    return len(used)

HOME_STYLES = 'rootfs/release/assets/default/raw/styles/home_page.bin'

def add_home_icon(out):
    """The Home grid's "M1+ Music" icon (patch/home.c builds the widget at run time): its two images and the image
    style home_m1plus_style, a copy of home_tidal_style (normal/disable/focused/pressed/selected) pointing at them,
    inserted in the stock sort order (widget type, style name) among the other home_*_style items."""
    import awtk_style
    p = os.path.join(out, HOME_STYLES)
    old = open(p, 'rb').read(); th = awtk_style.parse(old)
    assert awtk_style.serialize(th) == old, 'home_page.bin does not round-trip'
    assert not th.find('image', POD_HOME_STYLE), 'home_m1plus_style already in the tree'
    src = th.find('image', 'home_tidal_style'); assert len(src) == 5, 'unexpected home_tidal_style'
    new = []
    for it in src:
        props = [(k, t, (POD_HOME[1] if it.state == 'pressed' else POD_HOME[0]) if k == 'bg_image' else v) for k, t, v in it.props]
        new.append(awtk_style.Item('image', POD_HOME_STYLE, it.state, props))
    at = next((i for i, it in enumerate(th.items) if it.widget == 'image' and it.style > POD_HOME_STYLE),
              max(i for i, it in enumerate(th.items) if it.widget == 'image') + 1)
    th.items[at:at] = new
    write_keep_mode(p, awtk_style.serialize(th))
    d = os.path.join(out, IMG)
    for n in POD_HOME:
        q = os.path.join(d, n + '.png'); assert not os.path.exists(q), f'{n}.png already in the tree'
        shutil.copyfile(os.path.join(PNG, n + '.png'), q); os.chmod(q, IMG_MODE); os.utime(q, (IMG_MTIME, IMG_MTIME))

def add_nav_icons(out):
    """The Albums view toggle's four images (used by ui/m1plus_albums.bin, which swaps the glyph at run time with its mode)
    the status bar's Screenshot camera (the hidden pod_shot image tools/pod_ui.py adds to ui/system_bar.bin) and the Playlists
    page's menu glyphs (ui/m1plus_playlists.bin)."""
    d = os.path.join(out, IMG)
    for n in nav_names() + [SHOT_BAR[0], LO_BAR, SYNC_BAR[0], SYNC_DM] + [n for n, _ in PL_MENU_ICONS] + [n for n, _ in RM_MENU_ICONS] + [RM_FAV_ON[0], RM_DOTS[0]]:
        q = os.path.join(d, n + '.png'); assert not os.path.exists(q), f'{n}.png already in the tree'
        shutil.copyfile(os.path.join(PNG, n + '.png'), q); os.chmod(q, IMG_MODE); os.utime(q, (IMG_MTIME, IMG_MTIME))

def add_album_icons(out):
    """The album page's images (ALBUM): the tint, Shuffle's disc and glyph, the pill and the play glyph; patch/albumpage.c
    and tools/pod_ui.py build_album_page refer to them by name."""
    d = os.path.join(out, IMG)
    for n in ALBUM + DAILY + list(FOLDER_ROWS) + list(RADIO_ROWS) + list(SUBSONIC_ICONS) + list(SUBSONIC_ART) + [RADIO_ART[0]]:
        q = os.path.join(d, n + '.png'); assert not os.path.exists(q), f'{n}.png already in the tree'
        shutil.copyfile(os.path.join(PNG, n + '.png'), q); os.chmod(q, IMG_MODE); os.utime(q, (IMG_MTIME, IMG_MTIME))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', nargs='?'); ap.add_argument('out', nargs='?')
    ap.add_argument('--generate', action='store_true'); ap.add_argument('--pins', action='store_true')
    ap.add_argument('--fetch', metavar='TGZ', help='run once per tarball (Lucide, Tabler)'); ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.pins: cmd_pins()
    elif a.generate: cmd_generate()
    elif a.fetch: cmd_fetch(a.fetch)
    elif a.check:
        print(check_assets(find_stock_img(), os.path.join(a.src, IMG) if a.src else None), 'files OK')
    elif a.src and a.out: apply(a.src, a.out)
    else: ap.error('SRC and OUT workdirs, or a command')

if __name__ == '__main__': main()
