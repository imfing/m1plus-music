#!/usr/bin/env python3
"""Compile the M1+ Music payload, install its hook into demo, and add the page assets.

Runs on a workdir that already has the battery, lock screen and space mods applied (so demo's
.pdr is zeroed); it patches that demo and writes the new ui/*.bin. The injection follows q2-pod's
design (its tools/build.py), reduced to the one hook this project needs:

  * payload compiled non-PIC (clang --target=mipsel-linux-gnu -march=mips32r2 -mabi=32 -mfp64
    -mno-abicalls -fno-pic -G0 -Oz), linked at 0xb00000 by patch/link.ld, objcopy'd to patch.bin;
  * appended to demo through its final PT_NULL program header, rewritten to a PT_LOAD (RWX) at
    0xb00000; the payload keeps no .bss, so memsz == filesz and nothing else moves;
  * the Home icon click dispatcher's 3-word PIC prologue (checked) is overwritten with `j
    m1plus_home_click; nop`; a trampoline restores $gp (0xa03ed0) and resumes the stock function at
    its 4th instruction, so the payload can still call it (open a stock Home destination, or fall
    through for every non-entry tap);
  * stock functions are reached through absolute-address macros, libc only through demo's own GOT
    slots -- both pinned.

A second hook, home_page_init, runs the boot guard (patch/home.c); a third, playing_page_init, tints Now Playing
and shows the remaining time (patch/nowplaying.c). The library rows are pinned
call-site and immediate edits (patch/rows.json). Every patched word and the input demo are pinned
by value/SHA before anything is written.

Usage: pod.py WORKDIR
"""
import argparse, concurrent.futures, io, json, os, pathlib, re, stat, struct, subprocess, sys
from elftools.elf.elffile import ELFFile
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import modlib
from modlib import sha256 as sha
import autotime, coex, palette, pcregion, pod_pages, pod_ui, textgamma, themeoff, timezones
from build import TAG, VERSION, REPO, about   # the About row of the iPod page shows about(tag) (patch/m1plus.c M1PLUS_TAG)
from pod_pins import *   # the *_PINS tables and their address constants (pod.X_PINS stays valid)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH = os.path.join(ROOT, 'patch')
DEMO = 'release/bin/demo'

# Toolchain: Homebrew LLVM/LLD (Apple clang has no MIPS target). Override with $LLVM_BIN / $LLD_BIN.
LLVM = os.environ.get('LLVM_BIN', '/opt/homebrew/opt/llvm/bin')
LLD = os.environ.get('LLD_BIN', '/opt/homebrew/opt/lld/bin')
CLANG = os.path.join(LLVM, 'clang')
OBJCOPY = os.path.join(LLVM, 'llvm-objcopy')
LD = os.path.join(LLD, 'ld.lld')

# compiled in this order, linked with --gc-sections (docs/architecture.md)
SOURCES = ['m1plus.c', 'common.c', 'filetime.c', 'menu.c', 'covercache.c', 'artistphoto.c', 'durations.c', 'coverflow.c', 'albums.c', 'artists.c', 'shuffle.c', 'nowplaying.c', 'bigcover.c', 'lockscreen.c', 'display.c', 'keyspower.c', 'minibar.c', 'grid.c', 'recent.c', 'dailymix.c', 'homecover.c', 'covlist.c', 'setfiles.c', 'rows.c', 'shot.c', 'home.c', 'fontregion.c', 'textgamma.c',
           'scroll.c', 'playmore.c', 'pulldown.c', 'playlists.c', 'azlist.c', 'songops.c', 'libsrc.c', 'rowmenu.c', 'songs.c', 'albumpage.c', 'queuepage.c', 'upnext.c', 'ipod.c', 'ipod_cf.c', 'ipod_theme.c', 'ipod_render.c', 'pcmodel.c', 'pcfeed.c', 'pcjson.c', 'pcopml.c', 'pcpng.c', 'pccover.c', 'pcwrap.c', 'pcnotes.c', 'pcdetail.c', 'upver.c', 'pcnet.c', 'podcasts.c', 'pcfind.c', 'radio.c', 'radiopage.c', 'radionp.c', 'radioinfo.c', 'songinfo.c', 'tape.c', 'palette.c', 'vinyl.c', 'onlineart.c', 'update.c', 'relnotes.c', 'keyboard.c', 'search.c', 'battery.c', 'charging.c', 'nextalbum.c', 'lineout.c', 'lyrics.c', 'picker.c', 'folders.c', 'timezones.c', 'pcregion.c', 'viewsort.c', 'wifictl.c', 'wifipage.c', 'sbnet.c', 'sbparse.c', 'sbdl.c', 'sbapi.c', 'sbsrc.c', 'ndserver.c', 'ndroot.c',
           'tidalkb.c', 'peq.c', 'peq_ui.c', 'peqpage.c', 'peqlib.c', 'autoeq.c', 'tenband.c', 'peqband.c', 'peqout.c']

# Navidrome data layer (patch/sbapi.c): kept by the linker until the pages that call it exist; the integration drops names as callers appear
ND_KEEP = ['sba_free_tracks', 'sba_free_albums', 'sba_free_artists', 'sba_free_playlists', 'sba_user', 'sba_conf_url_set', 'sba_conf_user_set', 'sba_conf_password_set', 'sba_conf_clear', 'sba_cancel', 'sba_sync_due', 'sba_sync', 'sba_fetch_album', 'sba_fetch_artist', 'sba_fetch_playlist', 'sba_fetch_songs', 'sba_search', 'sba_star', 'sba_cover', 'sba_cover_path', 'sba_cover_have', 'sba_cover_get', 'sba_track_cover', 'sba_rec_cover', 'sba_albums', 'sba_artists', 'sba_playlists', 'sba_starred_tracks', 'sba_album_tracks', 'sba_artist_albums', 'sba_playlist_tracks', 'sba_songs', 'sba_songs_more', 'sba_search_tracks', 'sba_search_albums', 'sba_search_artists', 'sba_songs_cached', 'sba_stream_url', 'sba_track_filename', 'sba_is_dsd', 'sba_now_cover', 'sba_rec_track', 'sba_queue_note', 'sba_net_open']

FLAGS = ['--target=mipsel-linux-gnu', '-march=mips32r2', '-mabi=32', '-mfp64',
         '-mno-abicalls', '-fno-pic', '-G0', '-ffreestanding', '-fno-builtin',
         '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
         '-Oz', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
         '-ffunction-sections', '-fdata-sections']

# Stock V2.1 demo after mod_space zeroes its .pdr (what this step receives). demo is unchanged by
# the battery/lockscreen asset mods.
ZEROED_DEMO_SHA = 'cdd2e97e85076e8ed4f7ce7b34b7b8065ab041477ddeb2b00dc78aa541c37a7b'

BASE = 0xb00000            # payload load address (stock LOAD ends at va 0xa10fc8)
GP = 0xa03ed0             # demo's $gp (DT_PLTGOT + 0x7ff0); every PIC prologue resolves this

# The one hook: the Home icon click dispatcher (unnamed in .dynsym). It runs only from a Home icon
# tap (widget_on EVT_CLICK, home_page_init). (stock address, replacement payload symbol).
HOME_CLICK = 0x533b80
HOME_CLICK_PROLOGUE = (0x3c1c004d, 0x279c0350, 0x0399e021)  # lui/addiu $gp; addu $gp,$gp,$t9

# The second hook (the boot guard): home_page_init, run once when the Home window
# is created at start-up. m1plus_home_init runs the stock function to completion, then the boot guard.
HOME_INIT = 0x534cd4
HOME_INIT_PROLOGUE = (0x3c1c004d, 0x279cf1fc, 0x0399e021)

# The third hook (patch/nowplaying.c): playing_page_init, the Now Playing page's init (called by the navigator's
# page-init dispatcher only when the page is built, never at boot). m1plus_playing_init runs the stock function
# first, then starts the page-scoped tint and remaining-time timer.
PLAYING_INIT = 0x53d1e4
PLAYING_INIT_PROLOGUE = (0x3c1c004c, 0x279c6cec, 0x0399e021)

BIGCOVER_INIT = 0x529a24
BIGCOVER_INIT_PROLOGUE = (0x3c1c004e, 0x279ca4ac, 0x0399e021)


# The lock screen's mini player layout (patch/lockscreen.c, docs/modules/lockscreen.md, payload hook 25): screensaver_page_init, built by the navigator's page-init dispatcher whenever the lock
# screen opens. m1plus_lockscreen_init runs the stock init, then (setting "1") re-lays the track card out as the Home bar's layout.
LOCKSCREEN_INIT = 0x53fd44
LOCKSCREEN_INIT_PROLOGUE = (0x3c1c004c, 0x279c418c, 0x0399e021)


# Light Mode (patch/palette.c, docs/modules/accent.md, docs/modules/payload.md hooks 10 - 12): three hooks on the painter's inputs, q2-pod's (its style_get_color / style_get_gradient / image_manager_add hooks).
# Each is a plain pass-through while Light Mode is off (the setting, the kill switch, the bad-boot note).
#   style_get_color    0x659fcc  PIC prologue, the hook is `j m1plus_style_color` and a trampoline resumes at +12 (addiu sp, sp, -0x80)
#   style_get_gradient 0x659f9c  a leaf without prologue: beqz a0; nop; lw v0, (a0). Its first two words become `j m1plus_style_gradient; nop`, which does the whole of it (null style, no vtable
#                                or no get_gradient slot +0x18: 0; else the slot). style_get_color's own `bal` to it (0x65a048, returning to STYLE_COLOR_GRADIENT_RET 0x65a050) stays unmapped
#   image_manager_add  0x655638  PIC prologue, the trampoline resumes at +12 (beqz a0, ...)
STYLE_COLOR, STYLE_COLOR_PROLOGUE = 0x659fcc, (0x3c1c003b, 0x279c9f04, 0x0399e021)
IMAGE_ADD, IMAGE_ADD_PROLOGUE = 0x655638, (0x3c1c003b, 0x279ce898, 0x0399e021)
STYLE_GRADIENT, STYLE_GRADIENT_WORDS = 0x659f9c, (0x10800009, 0, 0x8c820000)
STYLE_COLOR_RET = 0x65a050   # patch/offsets.inc STYLE_COLOR_GRADIENT_RET (the test compares the two)


# Stock functions the payload calls, by absolute address (pinned). (return, args, address)
FUNCTIONS = {
    'widget_lookup':           ('void *', 'void *, const char *, int', 0x666a74),
    'widget_on':               ('int', 'void *, int, void *, void *', 0x666d20),
    'edit_set_focus':          ('int', 'void *, int', 0x62a1dc),   # patch/tidalkb.c: stock's own focus (and so T9) when our keyboard is not used
    'widget_get_window':       ('void *', 'void *', 0x66a9a8),
    'widget_set_text_utf8':    ('int', 'void *, const char *', 0x66f720),
    'navigator_back':          ('int', 'void', 0x4d20dc),
    'on_backtoplayer_onclick': ('int', 'void *, void *', 0x4cd58c),
    'window_open':             ('void *', 'const char *', 0x679fd4),
    # Cover Flow (patch/coverflow.c): widgets, the stock slide_menu, images and bitmaps
    'widget_set_visible':      ('int', 'void *, int, int', 0x66c394),
    'widget_set_prop_int':     ('int', 'void *, const char *, int', 0x66ff3c),
    'widget_get_prop_int':     ('int', 'void *, const char *, int', 0x6686f8),
    'widget_get_prop_str':     ('const char *', 'void *, const char *, const char *', 0x6685e0),
    'widget_set_prop_str':     ('int', 'void *, const char *, const char *', 0x66f8a8),
    'widget_set_sensitive':    ('int', 'void *, int', 0x666b9c),
    'widget_set_opacity':      ('int', 'void *, int', 0x669140),   # (the Regenerate Daily Mix row, dimmed: opacity byte +0x34, widget_paint's global alpha)
    'widget_use_style':        ('int', 'void *, const char *', 0x66aa64),
    'hscroll_label_set_only_parent_focus': ('int', 'void *, int', 0x6092e8),
    'widget_grab':             ('int', 'void *, void *', 0x668958),
    'widget_ungrab':           ('int', 'void *, void *', 0x6689f4),
    'widget_count_children':   ('unsigned', 'void *', 0x669f00),
    'widget_get_child':        ('void *', 'void *, unsigned', 0x669f20),
    'widget_destroy_children': ('int', 'void *', 0x67050c),
    'widget_invalidate_force': ('int', 'void *, void *', 0x6691d0),
    'widget_factory':          ('void *', 'void', 0x674218),
    'widget_factory_create_widget': ('void *', 'void *, const char *, void *, int, int, int, int', 0x6744b4),
    'image_create':            ('void *', 'void *, int, int, int, int', 0x62d8d4),
    'image_set_draw_type':     ('int', 'void *, int', 0x62d964),
    'image_base_set_image':    ('int', 'void *, const char *', 0x654910),
    'widget_load_image':       ('int', 'void *, const char *, void *', 0x66b0d8),
    'widget_unload_image':     ('int', 'void *, void *', 0x66b888),
    'bitmap_create_ex':        ('void *', 'unsigned, unsigned, unsigned, unsigned', 0x64005c),
    'bitmap_destroy':          ('int', 'void *', 0x63fdb4),
    'bitmap_lock_buffer_for_read':  ('const unsigned char *', 'void *', 0x640738),
    'bitmap_lock_buffer_for_write': ('unsigned char *', 'void *', 0x6407b0),
    'bitmap_unlock_buffer':    ('int', 'void *', 0x640828),
    'bitmap_get_line_length':  ('unsigned', 'void *', 0x640264),
    'canvas_draw_image':       ('int', 'void *, void *, const void *, const void *', 0x6455d4),
    # the Albums grid (patch/albums.c): its pointer position and the canvas text calls (draw_text_in_rect draws at the
    # canvas' current font, colour and alignment, widget_prepare_text_style sets them from the widget's style)
    'widget_to_local':         ('int', 'void *, void *', 0x669b88),
    'widget_set_state':        ('int', 'void *, const char *', 0x66962c),   # the Main Menu page's pressed arrow (patch/menu.c)
    'widget_prepare_text_style': ('int', 'void *, void *', 0x66a214),
    'canvas_draw_text_in_rect': ('int', 'void *, const unsigned *, unsigned, const void *', 0x6496a0),
    'canvas_measure_text':     ('float', 'void *, const unsigned *, unsigned', 0x644544),   # float_t in $f0
    # the library title order (patch/covercache.c cc_name_keys): stock's utf8_to_pinyin(in, out) appends to out (strlen) one byte per ASCII char and, for a CJK char U+4E00..U+9FA5, its pinyin initial
    'utf8_to_pinyin':          ('void', 'const char *, char *', 0x73a5f0),
    # the Albums list rows' highlight and hairline: color_t is one word (lcd_set_fill_color stores $a1 at lcd+0xbc), r,g,b,a bytes;
    # canvas_fill_rect @0x644e4c takes h on the stack and clips to the canvas' clip rect
    'canvas_set_fill_color':   ('int', 'void *, unsigned', 0x644220),
    'canvas_fill_rect':        ('int', 'void *, int, int, int, int', 0x644e4c),
    # Cover Flow landscape (patch/coverflow.c): the page's font, as canvas_draw_text @0x645348 calls it. font_get_vmetrics
    # returns its 8 byte struct (ascent s16 first) through a hidden pointer in $a0
    'font_get_glyph':          ('int', 'void *, unsigned, unsigned, void *', 0x6508b0),
    'font_get_vmetrics':       ('void', 'void *, void *, unsigned', 0x650918),
    'tk_utf8_to_utf16_ex':     ('unsigned *', 'const char *, unsigned, unsigned *, unsigned', 0x70eb24),   # wchar_t is 32 bit
    'slide_menu_set_value':    ('int', 'void *, int', 0x61399c),
    'list_item_create':        ('void *', 'void *, int, int, int, int', 0x60bec8),
    'label_create':            ('void *', 'void *, int, int, int, int', 0x62ee90),
    'timer_add':               ('unsigned', 'int (*)(const void *), void *, unsigned', 0x663530),
    'timer_remove':            ('int', 'unsigned', 0x66360c),
    # Cover Flow data: the stock library queries and the art extractors
    'loadLocalClassList':      ('int', 'int', 0x4ee504),
    'loadAlbumList':           ('int', 'int, void *', 0x4ee8d8),   # Artists: an artist's albums (album_page_init)
    'loadAlbumdetailList':     ('int', 'int, void *', 0x4eea98),   # an album row (a RECORD pointer, not an index) to its songs: loadLocalClassList(0xff11) for the All songs row
    'loadSongList':            ('int', 'void *, const char *, int, int', 0x4e2ce0),
    'toolsQueryDbTable':       ('int', 'const char *, const char *, void *, int', 0x5ee77c),   # (db, sql, row callback, sort); hooked (pc_library_query), so a call goes through the Library filter
    'navigator_to_with_context': ('int', 'const char *, const void *', 0x4d1d48),
    'toolsGetAlbumCover':      ('int', 'const char *, const char *, int, int', 0x5eaee0),
    'toolsGetExternCover':     ('int', 'const char *, const char *, int, int', 0x5eafec),
    # Shuffle (patch/shuffle.c, docs/architecture.md): the stock play mode as the Play settings page
    # sets it (@0x49fc78), the random seed, and the message box
    'mclGetPlayMode':          ('int', 'void', 0x5d3628),
    'mclSetPlayMode':          ('int', 'int', 0x5d278c),
    'notifyPlayMode':          ('int', 'void', 0x50ee04),
    'dmrSendPlayMode':         ('int', 'int', 0x4f10f0),
    'write_int_config':        ('int', 'int, const char *, const char *', 0x4d6a2c),
    # the Lock Screen's Wallpaper picker (patch/lockscreen.c lkwp_*): stock's picture list builder (0x4d7524: toolsGetScreenSaverPic fills the deque pdeq_screensaverlist, the Default entry in front, an unreadable
    # chosen picture back to the default) and its config writer (0x5e43f8: file, section, key, value), as the stock wallpaper grid's tap handler 0x4ab52c calls it
    'get_screensaver_image':   ('int', 'void', 0x4d7524),
    'toolsWriteConfig':        ('int', 'const char *, const char *, const char *, const char *', 0x5e43f8),
    # the Equalizer page (patch/peq_ui.c): stock's own switch handler (on_eqswitch_onclick 0x49d750) flips equalizer_flag, writes
    # [PLAYSET] EQFLAG and calls this with equalizer_mode (1..11, clamped by config_init): mcl-seteq with the mode's ten gains,
    # flag 0 (closes the player's equalizer) while equalizer_flag is 0, else 1 or 2 (adds it, or sends the gains again)
    'set_equalizer_value':     ('void', 'int', 0x4d851c),
    'toolsRandnum':            ('int', 'int', 0x5e0c58),
    'time_now_ms':             ('unsigned', 'void', 0x70cf58),   # uint64_t; o32 LE returns the low word in $v0
    'get_wifisignal':          ('int', 'void', 0x506cc8),        # Podcast network guard: -1 when not connected, else a level 2..5 (networkGetWifiSignal / ConnectStatus / PhysicStatus)
    # Home (patch/home.c): the window stack, to open the menu only when the stock Home is the topmost
    # normal window and fully opened
    'window_manager':          ('void *', 'void', 0x6774b4),
    'window_manager_get_top_main_window': ('void *', 'void *', 0x6774f0),
    'widget_is_window_opened': ('int', 'void *', 0x66aa04),
    # Library rows (patch/rows.c, docs/architecture.md): the row constructors' own layout call, and what
    # the row fit reads and resizes
    'widget_set_children_layout': ('int', 'void *, const char *', 0x656f7c),
    'widget_get_type':         ('const char *', 'void *', 0x66a794),
    'widget_get_visible':      ('int', 'void *', 0x672948),
    'widget_resize':           ('int', 'void *, int, int', 0x66d13c),
    'widget_move':             ('int', 'void *, int, int', 0x66cfc0),
    'hscroll_label_set_only_focus': ('int', 'void *, int', 0x60929c),
    # The M1+ Music icon on the Home grid (patch/home.c): what the stock icon builder 0x533d8c calls per icon
    # (view_create, image_create, widget_set_prop_bool "clickable", widget_use_style, widget_set_name, widget_on,
    # label_create, label_set_line_wrap), plus the page/indicator calls of the page builder 0x534064
    'view_create':             ('void *', 'void *, int, int, int, int', 0x6346f0),
    'widget_set_prop_bool':    ('int', 'void *, const char *, int', 0x670170),
    'widget_set_name':         ('int', 'void *, const char *', 0x6668d0),
    'label_set_line_wrap':     ('int', 'void *, int', 0x62e068),
    'slide_indicator_set_max': ('int', 'void *, unsigned', 0x616b70),
    'widget_destroy':          ('int', 'void *', 0x66e544),
    'window_close':            ('int', 'void *', 0x675b70),   # "Shanling Home" closes the menu under the Settings page
    # The album view (patch/covercache.c, patch/songops.c): the stock play sequence, and the cover-task list the stock
    # album page builds before albuminfo_page opens
    'start_player':            ('int', 'void *, int, int, int', 0x4e4648),
    'albumcoverinfo_init':     ('void', 'void *', 0x4dcf9c),
    'batchadd_albumcover_task': ('void', 'int, int', 0x4dccac),   # local_albumsmallcover_task: ends with albumcover_taskstate = 1
}
# Now Playing (patch/nowplaying.c): the window's bg_color through the style API (widget_set_style(widget, "normal:bg_color",
# &value_t) is AWTK's widget_set_style_color: it makes the style mutable, stores the value and invalidates), the uint32
# value_t it takes, and the player's position and length in seconds (what the page's own timer shows, @0x53a8fc)
FUNCTIONS.update({
    'widget_set_style':        ('int', 'void *, const char *, const void *', 0x66c448),
    'value_set_uint32':        ('void *', 'void *, unsigned', 0x711858),
    # The album page's Play pill (patch/albumpage.c): the translated text (a wchar_t string) and its width
    # in the widget's own style, as widget_measure_text @0x66c7e0 gets it (widget_get_canvas, widget_prepare_text_style,
    # canvas_measure_text @0x644544; 0 when there is no canvas or no text)
    'widget_get_text':         ('const unsigned *', 'void *', 0x667ea4),
    'widget_measure_text':     ('float', 'void *, const unsigned *', 0x66c7e0),
    'get_playtimeandlength':   ('int', 'int *, int *', 0x4e015c),
    # Cover Flow opens on the playing album (patch/covercache.c cc_playing): the playing track's index in the play
    # queue, the call get_playtimeandlength and the lock screen refresh make (@0x4e0198, @0x53f718); -1 for none
    'mclGetPlayPos':           ('int', 'void', 0x5d4290),
    # Shuffle (patch/shuffle.c): the play position word mclGetPlayPos reads is stored back after the queue is reordered
    'mclSetPlayPos':           ('void', 'int', 0x5d42d8),
    # the Gapless setter: stores the setting byte, and for 0 with a preload open sends {mcl-closegapless} and stores -1 in the preload state (the one cancel helper of patch/shuffle.c cancel_preload: reorders, insert, Clear)
    'mclSetGaplessMode':       ('int', 'int', 0x5d28ac),
})
# Localisation (patch/i18n.h): the stock translation. locale_info() is the app's locale, locale_info_tr(locale, key) the
# table lookup (the key itself when absent), widget_set_tr_text(widget, key) stores the key on the widget (the window
# manager re-translates it when the language changes) and sets the translated text
FUNCTIONS.update({
    'locale_info':             ('void *', 'void', 0x6588b0),
    'locale_info_tr':          ('const char *', 'void *, const char *', 0x658db4),
    'widget_set_tr_text':      ('int', 'void *, const char *', 0x66f994),
    # patch/lockscreen.c lk_date: copies the format (tk_str_copy into digit_clock +0x78) and formats the time at once (0x626b08); RET_BAD_PARAMS for a null widget
    'digit_clock_set_format':  ('int', 'void *, const char *', 0x626bbc),
})
# Light Mode (patch/palette.c): a change of the effective mode drops the cached images (the image manager: AWTK's image_manager() and image_manager_unload_all, which the window manager's
# locale handler also calls) and repaints the window manager
FUNCTIONS.update({
    'image_manager':           ('void *', 'void', 0x655544),
    'image_manager_unload_all': ('int', 'void *', 0x655fdc),
})
# The track rows' playing marker (patch/rows.c rows_track_icon): widget_restack(widget, index) moves a child within its
# parent's children (clamps the index to the last; reads the parent @0x66a014; no relayout of its own)
FUNCTIONS.update({
    'widget_restack':          ('int', 'void *, unsigned', 0x669fc4),
    # what widget_set_visible calls with the parent after a change (@0x66c424): the restack changes the flow even when the
    # icon's visibility does not
    'widget_set_need_relayout_children': ('int', 'void *', 0x66c338),
})
# Now Playing opens the way a track row does (the row handler @0x52569c, loop @0x525904..0x5259d8; patch/songops.c
# pod_open_player): the window stack calls
# Time zones (patch/timezones.c, docs/modules/timezones.md): setenv("TZ") and the picker's row builder, both stock's own, called by the hooks
FUNCTIONS.update({
    'toolsSetTimeZone':           ('int', 'const char *', 0x5e3288),
    'timezone_listitem_layout':   ('void *', 'void *, int', 0x4a21c8),
})
FUNCTIONS.update({
    'navigator_window_is_exist':  ('int', 'const char *', 0x4d2040),
    'navigator_close':         ('int', 'const char *', 0x4d2118),   # closes the named page (Now Playing's Look up album / artist, patch/playmore.c)
    'window_manager_get_top_window': ('void *', 'void *', 0x6775c4),
})
# The mini player bar (patch/minibar.c, docs/modules/minibar.md): the calls the stock transport buttons make, and the play state
# they read. The lock screen's btn_play / btn_next handlers (strcmp-bound to 0x53f964 / 0x53f900 by name @0x53f3d4 / @0x53f410) are
# `playpause_quick_click()` / `next_quick_click(e, 0)` followed by the page's own refresh (0x53f520); Now Playing's next button
# (@0x53c16c: `next_quick_click(e, 0)`) and the hardware keys (on_wm_keyup_fun @0x4cda78 / @0x4cdba4) call the same two. Both do
# their own checks (queue, network source, "not found" toast) and tell the other listeners (notifyPlayStatus, dmr, Bluetooth).
# next_quick_click reads e->time (event_t u64 @8: `lw a1, 8(a0); lw a2, 0xc(a0)` @0x4ccf2c) and ignores a click within 1000 ms of the
# last one it took (the global 0xa05a40). mclGetPlayStatus is `lw v0, status`: 2 = playing (the lock screen refresh @0x53f82c shows
# btn_imgpause1_style for 2 and btn_imgplay1_style for anything else), mclSetPause stores 3 (@0x5d2658), mclSetResume 2 (@0x5d26c8).
FUNCTIONS.update({
    'playpause_quick_click':   ('int', 'void', 0x4cd150),
    'next_quick_click':        ('int', 'void *, int', 0x4ccf00),
    'mclGetPlayStatus':        ('int', 'void', 0x5d3640),
    # The playing stream as the player reports it (the mutex 0xa0ab20, then a copy of the 0x34 bytes at 0xa0ab50 into the caller's): bit rate in bit/s at 0, sample rate in Hz at 4, the codec's name at
    # 0x10 ('FLAC', 'ALAC', 'WAV', 'APE', 'AIFF', 'DSD', 'DSF', 'ISO' are the names get_hrflag @0x4dfbc4 looks for), bits a sample at 0x30 (1 for DSD). get_playinfo @0x4dfb14 (the idle tick) copies it to
    # playsong_info 0xa0e930, which show_player_face prints as '%s|%.1fkHz|%dbit|%dkbps'. Returns 1.
    'mclGetInfo':              ('int', 'void *', 0x5d3518),
})
# The Playlists page (patch/playlists.c, docs/modules/playlists.md): the stock playlist creation, and the click handlers of the stock Playlists
# page's Import and Export rows (static, unnamed; ret_t (ctx, event), neither reads its arguments: each asks with the stock confirm dialog,
# runs importPlayList / exportPlayList and tells the result in the stock message box).
FUNCTIONS.update({
    'createPlayListItem':      ('int', 'void *, const char *', 0x4eeca8),   # (the stock list, name or NULL): the new id, -1 full, -2 name exists
    # The Daily Mix page's Add disc (patch/dailymix.c dp_save, docs/modules/dailymix.md): the playlist-table calls of the stock batch add (batch_add_file @0x4da7dc, class
    # 0xf001 -> 0xf00b: @0x4db34c..0x4db3d0), made per song in the mix's order. All three are thin wrappers over toolsGetMaxId / toolsCheckExist / toolsInsertDbTable on
    # "playlist" in /mnt/data/database.db.
    'checkPlayListExist':      ('int', 'void *, int', 0x4ee1a8),            # (song record, playlist id): 1 = that song is already in it
    'getPlayListMaxId':        ('int', 'void', 0x4ee184),                   # the largest id in the table (the new song row's id is max(100, that) + 1)
    'addPlayList':             ('int', 'void *', 0x4ee1cc),                 # (song record: id REC_ID, playlist id REC_DISC): inserts the row, 1 = done
    # Saved episodes (patch/podcasts.c pg_save_toggle): the star button's own three calls (manage_myfav 0x4ef884: checkFavExist, then deleteMusicFromFav or addMyFav on the record),
    # on "myfav" in /mnt/data/database.db. A record of ours (name, path, title, album, artist) is enough: a NULL string is skipped by the insert.
    'checkFavExist':           ('int', 'void *', 0x4ee210),                 # (song record): 1 = a row with its filename, fileurl and cue times is in myfav
    'addMyFav':                ('int', 'void *', 0x4ee234),                 # (song record): inserts the row, 1
    'deleteMusicFromFav':      ('int', 'void *', 0x4ede88),                 # (song record): deletes the row (the same key), 1
})
# The Songs page (patch/songs.c, docs/modules/songs.md): the stock multi-select's selection vector (`*0xa045e0`, a vector<int> indexed by the row of
# *pdeq_showlist, 1 = selected: select_recordinit(n) clears it and pushes n zeros, set_selectindex(i) toggles v[i] and returns 1) and the stock batch
# delete (batch_delete_file(class, list, selection, 0, delete_file): the generic loop for 0xf001, deleteMusicFromMusicDb per selected row, remove_file when
# the flag is set, and `*0xa05a5a = 1` at the end). All of them touch no widget (docs/modules/songs.md has the evidence).
FUNCTIONS.update({
    # Navidrome offline DSD downloads (patch/sbdl.c): stock's folder scan worker calls this with drop=0 to add
    # files from one folder to songtable without dropping the existing library; it touches no UI widgets.
    'scanSpecFolder':         ('int', 'const char *, int', 0x4e9e90),
    'select_recordinit':       ('void', 'int', 0x4da3b0),
    'set_selectindex':         ('int', 'int', 0x4da434),
    'batch_delete_file':       ('int', 'int, void *, void *, int, int', 0x4e1408),
    # The album page's playing row (patch/albumpage.c): the stock row builder 0x524b50 asks is_playing(g_class_type, the record's CUE start, its file name, its url) for the gold title
    'is_playing':              ('int', 'int, int, const char *, const char *', 0x4d9d64),
    # Battery Percentage (patch/battery.c): stock's bucketed capacity, called first by the hook at show_sysbar_face's call site; it leaves the result in power_capacity (DATA POWER_CAPACITY)
    'get_battery_capacity':    ('int', 'void', 0x4e6dd8),
    # The Queue page (patch/queuepage.c): the queue drawer's row handler 0x479f60 plays row i with start_playqueue(i) (@0x47a0c8: airplay_stop, mclSetPlayPos, mclStartPlayer, notifyPlayStatus; it
    # is told apart from a stream by mclGetPlayType and the network state, @0x479ff4..0x47a028)
    'start_playqueue':         ('int', 'int', 0x4e47d0),
    'mclGetPlayType':          ('int', 'void', 0x5d3658),
    'delete_playqueue_file':   ('int', 'int', 0x4e48d8),   # Now Playing's Delete (patch/playmore.c pm_on_delete): the playing row out of the queue and the library, the file too for 1
    'add_playrecord':          ('int', 'void', 0x4efb08),   # stock's play-history writer (recentplay / oftenplay), called through patch/sbsrc.c sbs_play_record (PLAYREC_SITE)
    # Now Playing's mode button picture (@0x539888): widget_lookup(window, "btn_playmode"), then the style of mclGetPlayMode()'s mode (btn_imgorder / cycle1 / random / cycle). Stock runs it from the page init and
    # from the button's own click handler 0x53b5fc (mclSetPlayMode, write_int_config, this, notifyPlayMode, dmrSendPlayMode) and nowhere else, so a mode set by another page leaves the picture stale
    # until patch/nowplaying.c calls it again when the page is back in front.
})
NP_MODE_BUTTON = 0x539888   # not a symbol (the stock names there are the neighbouring page's): pinned by SONGS_PINS
# The iPod page (patch/ipod.c, docs/modules/ipod.md): the previous-track twin of next_quick_click (same prologue, same 1 s guard on e->time, `prev_music` 0x4e428c in place of
# `next_music` 0x4e4338; the Now Playing button @0x53c1d8 and the hardware key @0x4cdb64 call it with (event, 0)), and the album track query loadAlbumdetailList(class, ROW RECORD)
# (@0x4eea98: its second argument is the album record of the shown list, `lw v0, (a1)` the id and `0x14(a1)` the name; class 0xf003 -> 0xff10, 0xff01 -> 0xff11, 0xff02 -> 0xff14).
# The page's one timer (docs/modules/ipod.md): timer_modify(id, ms) sets the timer's duration (`sw s1, 0x40(s0)`) and its start time, nothing else (fast while the main
# menu's cover pans or Cover Flow slides, 500 ms elsewhere).
FUNCTIONS.update({
    'prev_quick_click':        ('int', 'void *, int', 0x4cccb0),
    'loadAlbumdetailList':     ('int', 'int, void *', 0x4eea98),
    'timer_modify':            ('int', 'unsigned, unsigned', 0x663840),
})
# Podcasts (patch/pcmodel.c, docs/modules/podcasts.md "Addresses"): the stock seek and the stock speed.
# seek_time(sec) is the key path's seek commit (the Now Playing slider and the hardware keys call it; q2-pod's player_seek_time): it reads mclGetPlayStatus (1 = stopped: nothing
# happens) and mclGetPlayPos, adds the playing record's CUE start (`lw a0, 0x48(v0)`; 0 for a plain file), sends mclSetSeek (@0x4e0608), resumes a paused player
# (status 3: mclSetResume) and waits, at most 200 times 10 ms, until get_playtimeandlength is within a second of the target. mclSetPlaySpeed(mode) formats
# "{mcl-playspeed\%d}" with its argument (the string @0x756510, sprintf's third argument is `move a2, a0`) and sends it to hciplayer; the stock Multiple Speed page (4 handlers
# @0x4799xx..0x479cxx) stores 3, 2, 1 or 0 in playspeed_mode (0xa05acc), calls mclSetPlaySpeed with it, saves [PLAYSET] PLAYSPEED and restarts the player; config_mplayer
# (@0x4d869c) sends playspeed_mode at the player's set-up; config_init (@0x4e53e4) reads a stored value >= 4 as 0. The pages' images say the modes: 0 1x, 1 1.25x (p_1_25), 2 1.5x (p_1_5), 3 2x (p_2).
FUNCTIONS.update({
    'seek_time':               ('int', 'int', 0x4e0544),
    'mclSetPlaySpeed':         ('int', 'int', 0x5d281c),
    # Podcast downloads (patch/podcasts.c pg_awake_tick): stock's reset_poweroptions_timer(standby, auto_off, screen): a non-zero argument sets that countdown again (standby via setstandby_time, auto power-off via setsavepower_time, the screen's light via setlight_time); the page passes (1, 1, 0)
    'reset_poweroptions_timer': ('void', 'int, int, int', 0x4d7874),
    'reset_atmosphereled_rgb': ('void', 'void', 0x4e6b9c),   # Settings > Display > LED Light (patch/display.c): the lamp follows the byte atmosphereled_mode
})
# Settings (patch/m1plus.c, docs/modules/settings.md "Stock pages", "Stock state"): navigator_to opens the stock pages; the EQ preset's name is stock's table lookup (a tr key).
FUNCTIONS.update({
    'navigator_to':            ('int', 'const char *', 0x4d1d80),
    'get_equalizer_preset_name': ('int', 'int, char *', 0x49daec),
    # About (docs/modules/settings.md "About"): the card's capacity and free space (statfs, in G as floats), the connection state and the IP address, as the stock About page reads them
    'getDiskMemoryInfo':       ('int', 'const char *, float *, float *', 0x5b30e0),
    'networkGetConnectStatus': ('int', 'void', 0x5d7cac),
    'networkGetIPAddr':        ('int', 'int, char *', 0x5d753c),
    # The Wi-Fi page (patch/wifipage.c, docs/modules/wifi.md): stock's own switch (wifi_switch(1) toggles Wi-Fi: on starts wifi_connect.sh, off kills the supplicant)
    'wifi_switch':             ('int', 'int', 0x507a8c),
})
TIDALKB_SEARCH = 0x4c4740
# Regional CJK forms (patch/fontregion.c, docs/modules/fonts.md "Regional forms"): the font manager, the live "default" font
# (one stb font object for every size: match compares the name only), its glyph cache, and the locale's change event
FUNCTIONS.update({
    'font_manager':            ('void *', 'void', 0x650ad0),
    'font_manager_get_font':   ('void *', 'void *, const char *, int', 0x650dc4),   # lookup, else load and add
    'font_manager_shrink_cache': ('int', 'void *, int', 0x6510b8),   # glyph_cache_shrink of every font; 0 keeps none
    'locale_info_on':          ('int', 'void *, int, void *, void *', 0x658ba8),   # emitter_on(locale + 0x10, 0x122, cb, ctx)
})
# Stock's Google Pinyin engine (ime_pinyin: MatrixSearch, DictTrie, SpellingTrie, NGram; docs/modules/keyboard.md "Pinyin engine (probe)"). The C entry points sit over one global
# MatrixSearch* (0xa0a360, created by im_open_decoder, NULL until then); its first byte is inited_, which search / get_candidate / get_candidate_num test. im_open_decoder(sys dict path,
# user dict path) replaces any object there (stock's own keyboard init calls it with /usr/dict_pinyin.dat, which the rootfs does not have, so the object it leaves is never initialised).
FUNCTIONS.update({
    'im_open_decoder':         ('int', 'const char *, const char *', 0x5c7350),
    'im_close_decoder':        ('void', 'void', 0x5c7534),
    'im_search':               ('unsigned', 'const char *, unsigned', 0x5c760c),
    'im_reset_search':         ('void', 'void', 0x5c76e8),
    'im_get_candidate':        ('unsigned short *', 'unsigned, unsigned short *, unsigned', 0x5c7754),
    'im_choose':               ('unsigned', 'unsigned', 0x5c77c0),
    'im_get_fixed_len':        ('unsigned', 'void', 0x5c7824),
    'im_get_spl_start_pos':    ('unsigned', 'const unsigned short **', 0x5c778c),
    # MatrixSearch::get_predicts(this, history (1..7 char16), out char16[n][8], n): the commonly following words (no C entry point of its own)
    '_ZN10ime_pinyin12MatrixSearch12get_predictsEPKtPA8_tj': ('unsigned', 'void *, const unsigned short *, unsigned short (*)[8], unsigned', 0x5c6834),
})
FUNCTIONS['get_playtime'] = ('int', 'void', 0x4e02e4)   # the position the stock lyric timers compare "lrc_time" with (docs/modules/lyrics.md)
FUNCTIONS['widget_update_style'] = ('int', 'void *', 0x666780)   # the lyrics probe resolves its style before it measures (patch/lyrics.c ly_probe_face; a no-op once resolved)
# The library scan's folder walk (patch/common.c m1_scan_dir, docs/modules/payload.md hook 5): toolsLoadAllFile (0x5efd98) lists each folder with the function at 0x5ea364 (readdir
# loop, 0x5ea600); for a directory entry (d_type 4, name in s0) it skips "." with `strcmp(name, ".")` (0x5ea6a8), ".." and a list of system folders (lost+found, System Volume
# Information, RECYCLER, $RECYCLE.BIN, .LOST.DIR, .fseventsd, .Spotlight-V100, .Trashes); a zero result goes back to readdir (0x5ea600). Every other dot-folder is walked. The
# strcmp call is replaced by `jal m1_scan_dir` (q2-pod's SCAN_DIRS): the delay slot still loads a1 = ".", a0 = the name. Not on the boot path (tools/reach.py): the scan runs from
# the Update Local Music item and the other scan callers only.
# The Library query filter (patch/pcmodel.c pc_library_query / pc_sorted_query, docs/modules/payload.md hook 6): the two functions every songtable select goes through, hooked at their PIC prologues
# (q2-pod's toolsQueryDbTable / toolsQueryDbTableAndSort hooks). Both take (db, sql, row callback, sort) in a0..a3 and use no stack arguments.
QUERY_DB, QUERY_DB_PROLOGUE = 0x5ee77c, (0x3c1c0041, 0x279c5754, 0x0399e021)
ALBUM_HEAD, ALBUM_GROUP = 'select id,album,songer,fileurl from songtable', ' group by album COLLATE NOCASE'   # the album list statements' head and grouping (getAllAlbum's string at 0x74bad8; the getAlbumBy* family has the same columns and grouping)
ALBUM_SQL = ALBUM_HEAD + ALBUM_GROUP   # getAllAlbum's statement (sprintf of the string at 0x74bad8 with the one at 0x74ba4c), run by the payload's cover map; Get Info's lookup adds a where album='...' COLLATE NOCASE between the two
QUERY_SORT, QUERY_SORT_PROLOGUE = 0x5ee9ac, (0x3c1c0041, 0x279c5524, 0x0399e021)
LINEOUT_SITES = ((0x544f90, 0x544f88), (0x475ad8, 0x475ad0))   # (the jalr widget_set_text_utf8, the lw t9 that loads it)
EQ_ROW_RESUME = 0x4a0070
# Continue with Next Album, hook 26 (patch/nextalbum.c na_end, docs/modules/nextalbum.md "The hook"): mclNextSong's List play branch (raw mode word 0) tests `pos < size - 1` at 0x5d5950..0x5d5974;
# when it fails, 0x5d5988 / 0x5d598c (`lw v0, GOT; lw v1, class word`) start the end-of-queue handling (the folder callback check, mclStop at 0x5d59d8, then {mcl-orderstop} for the automatic call or a restart of the last
# song for a manual Next). The two words become `j pod_na_site; nop`; the stub calls na_end and, when it appended the next album, jumps back to the end test 0x5d5950 (which now finds the queue longer and plays
# pos + 1 through mclStartPlayer), else re-executes the two words and resumes at 0x5d5990. $s1 (the call's argument), $s2 (the queue's global), the frame and $gp survive the C call. Reachable on the main loop's idle path
# (the automatic call) and from a key press; not at boot. na_end's stock queries (the album page's own getters, left without their last step into *pdeq_showlist) are pinned below with the dispatcher words that choose them.
NEXTALBUM_SITE, NEXTALBUM_AGAIN, NEXTALBUM_RESUME = 0x5d5988, 0x5d5950, 0x5d5990
NEXTALBUM_DISPLACED = (0x8f8280b4, 0x8c43abd8)   # lw v0, -0x7f4c(gp); lw v1, -0x5428(v0): re-executed by the stub when na_end answers 0
FUNCTIONS.update({   # the album page's own lists and tracks, called without loadLocalClassList's last step (deque_assign into *pdeq_showlist): the rows stay in *tools_pdeq_directory
    'getAlbumByAlbumArtist':   ('int', 'const char *', 0x4eb0e4), 'getAlbumByArtist': ('int', 'const char *', 0x4eaccc), 'getAlbumByComposer': ('int', 'const char *', 0x4eb514),
    'getMusicByAlbum':         ('int', 'const char *', 0x4ecb5c), 'getMusicByAlbumAndAlbumSonger': ('int', 'const char *, const char *, int', 0x4ed008),
    'getMusicByAlbumAndSonger': ('int', 'const char *, const char *, int', 0x4ecd3c), 'getMusicByAlbumAndComposer': ('int', 'const char *, const char *, int', 0x4ed2d4),
})
# Queue page Clear (patch/shuffle.c pod_clear_upnext, docs/modules/queue.md "Clear engine"): the tracks after the play position are removed in place with libcstl's deque_pop_back, which demo does
# not import. libcstl is a fixed shared library of the firmware (a DT_NEEDED of demo): the payload finds it from demo's resolved GOT slot of deque_size (an import it calls anyway), pop_back =
# slot - CSTL_SIZE + CSTL_POP. The build pins the library file (SHA-256, the symbols' offsets, the words of both functions); at run time the same words are compared at the resolved addresses, and a
# mismatch or an unresolved slot (still the stub inside demo's image) refuses Clear. deque_pop_back is `lw t9, GOT _deque_shrink_at_end; jr t9; addiu a1, zero, 1` (0x3f3dc): destroy callback of the
# last element + free of an emptied block, no allocation (the call graph was walked by hand, docs/modules/queue.md).
LIBCSTL, LIBCSTL_LINK = 'usr/lib/libcstl.so.2.2.0', 'usr/lib/libcstl.so.2'
LIBCSTL_SHA = '91d6c02ceb93bea8eb1a7e980668223bdb89e8eadfb19ea15fb0b0ad73ae615a'
CSTL_SIZE, CSTL_SIZE_WORDS = 0x391f4, (0x3c1c0006, 0x279c9fbc, 0x0399e021, 0x27bdffb8, 0x00801025, 0x8f998ff0, 0x8c840114, 0x8c490124)
CSTL_POP, CSTL_POP_WORDS = 0x3ad64, (0x3c1c0006, 0x279c844c, 0x0399e021, 0x8f999194, 0x03200008, 0x24050001)
CSTL_SHRINK = 0x3f3dc

# The Add to Playlist picker (patch/picker.c, docs/modules/picker.md): batch_add_file(class, 0xf00b, list, selection, playlist id) as the stock picker's row handler 0x53d300 calls it
FUNCTIONS['batch_add_file'] = ('int', 'int, int, void *, void *, int', 0x4da7dc)
# Stock data the payload reads or writes, by absolute address. Exported objects are checked
# against .dynsym; the two unnamed ones carry the code that proves them.
DATA = {
    'ROTATEMODE':         (0xa05a9c, None),   # int, config.ini ROTATEMODE (0/1); 1 swaps the volume keys 0xdc <-> 0xdd (VOLKEYS_PINS)
    # the stock Tidal search page's result structs { total, limit, offset, deque_t * } (patch/tidalkb.c tk_reset_results; TIDALKB_PINS) and the scroll offset its timer restores
    'TIDAL_TRACKS':       (0xa10264, None), 'TIDAL_ARTISTS': (0xa10254, None), 'TIDAL_ALBUMS': (0xa10244, None), 'TIDAL_SCROLL': (0xa04150, None),
    'BACKLIGHT_STATUS':   (0x97cae4, 'backlight_status'), # byte: 0 off, 1 lit (awake_screen)
    'PDEQ_SHOWLIST':      (0xa045d8, 'pdeq_showlist'),   # deque_t * of the loaded list
    'PDEQ_TOOLS_TMP':     (0xa03964, 'tools_pdeq_directory'),   # deque_t * the stock song row callback fills (toolsQueryDbTable clears it first; loadLocalClassList assigns it to the show list, then clears it)
    'PARSE_COVER_MUTEX':  (0xa04588, 'parse_cover_mutex'),  # the lock every stock art caller holds
    # g_class_type: albuminfo_page_init stores classinfo[0] (0xff10) there @0x5268ec, and the row
    # handler passes it to loadSongList and playing_page @0x5275a4.
    'G_CLASS_TYPE':       (0x97cad4, None),
    # the stock browsing record loadAlbumdetailList fills (@0x4eeac8); its first word is the class.
    'CLASSINFO':          (0xa0c768, None),
    # the stock Artists page's artist / album artist switch (handler @0x535770): toggles the word, saves
    # [PLAYSET] ARTISTTYPE and sets the byte (the stock page's list-reload flag, read @0x535fe8)
    'ARTIST_TYPE':        (0xa05a14, None),
    # hciplayer state (patch/radio.c, docs/modules/radio.md; gp page 0xa10000): mcl_tidalStartPlayer's resume position (-0x543c; < 0 makes it ask the queue; the wrapper resets it to -1),
    # the "player running" byte (-0x5476; nonzero makes mclStartPlayer send set-nexturl; cleared by an "exit" or "error" reply) and the socket fd (-0x5414; -1 = nothing is sent)
    'RESUME_POS':         (0xa0abc4, None),
    'HCI_RUNNING':        (0xa0ab8a, None),
    'HCI_SOCK_FD':        (0xa0abec, None),
    'ARTIST_RELOAD':      (0xa06d20, None),
    # set to 1 by the stock Play all handler (@0x525e64) after start_player; the Shuffle button does the same
    'FORCE_REFRESH':      (0xa05a63, 'force_refreshflag'),
    # songerinfoflag: the album row handler @0x52569c opens Now Playing through its pop loop only when this byte is set
    # (read @0x5258c8; also referenced by album_page_init @0x52511c, airplay_page_init and the msginfo dialog)
    'SONGER_FLAG':        (0xa04737, 'songerinfoflag'),
    # the cover source type: parseplaycover_thd sets 1 (busy), 2 / 3 / 5 (a /tmp JPEG), the Now Playing cover loader
    # @0x53a5d8 reads it (`lw s1, 0x97cad8; lw v1, (s1); bne v1, 2 ...`, @0x53a6a8)
    'COVER_SRC':          (0x97cad8, None),
    # savecover_path: char[0x400], the path parseplaycover_thd last finished a cover for. It copies the track's path here (`snprintf(buf, 0x400, "%s")` @0x4df1a0) only AFTER it has stored the new source (2 / 3 / 5) and
    # released the lock, and skips a track whose path equals it (strcmp @0x4df028); COVER_SRC is 1 while it works. So source in {2, 3} with this equal to the playing path means the source is that track's (patch/bigcover.c)
    'COVER_PARSED':       (0xa04c3c, 'savecover_path'),
    # stock's Cover mode switch (Playback Settings > Cover mode; the timed Now Playing view runs only while it is on): a byte, 0 / 1, toggled by xori and saved as [SYSSET] COVERMODE (IDLE_PINS, patch/bigcover.c)
    'COVER_MODE':         (0xa05aa5, None),
    # the play queue: a deque_t * (stSongInfo rows, the queue start_player copied). Every reader pairs it with
    # mclGetPlayPos: get_playtimeandlength `lw s1, 0xa0394c; deque_size(*s1)` then `deque_at(*s1, pos)` (@0x4e01cc..0x4e0268),
    # the lock screen refresh (@0x53f73c, "queued" = 0 <= pos < size), the queue drawer (@0x47a8f0)
    'PLAY_QUEUE':         (0xa0394c, None),
    # the player's gapless state word (1 = a preload is open; mclSetGaplessMode(0) @0x5d28ac closes it with "{mcl-closegapless}" and stores -1): patch/shuffle.c cancel_preload closes it after a reorder, an insert or Clear
    'MCL_PRELOAD':        (0xa0abd0, None),
    'DMR_SERVERFLAG':     (0xa06020, 'dmr_serverflag'),   # int: 1 while stock's DLNA renderer (UPnP) service runs (dlna_service_running 0x507bec reads it; Clear and the queue insert stay off then, docs/modules/queue.md)
    'MCL_PRELOAD_NEXT':   (0xa0abcc, None),   # int: the queue index the preload opened (-1 none; the decision 0x5d0ea4 stores -1 first, @0x5d0ecc)
    'MCL_GAPLESS':        (0xa0ab89, None),   # byte: the Gapless setting (mclSetGaplessMode 0x5d28ac stores it; mclNextSong 0x5d583c and mclAutoChange 0x5d632c read it)
    # the menu's list (patch/menu.c mn_plain_paint): g_scroll_view_vtable is a widget's vtable word (+0x70) when it is a scroll_view;
    # 0x60c164 is the paint-children hook list_view_on_add_child (0x60cc08) stores in a scroll_view (@0x60cd04..0x60cd10,
    # `addiu v1, v1, -0x3e9c`; its prologue `lui gp, 0x3f; addiu gp, gp, 0x7d6c`, test/pod/pulldown.py pins both words)
    'SV_VTABLE':          (0x97a298, 'g_scroll_view_vtable'),
    'LV_PAINT_HOOK':      (0x60c164, None),
    # the Playlists page (patch/playlists.c): the stock playlist list (loadLocalClassList(0xf00b) assigns it, @0x4ee63c), the title the
    # Songs page shows (allmusic_page_init strcpy's it @0x528a74; the Playlists row handler snprintf's the name into it @0x53d5b8) and
    # navigation_status (0 = normal, 1 = the multi-select mode of the lists: the stock export reads it @0x53ddc0)
    'PDEQ_PLAYLIST':      (0xa045d0, 'pdeq_playlist'),
    'NAV_TITLE':          (0xa0533c, 'nagvation_title'),
    'NAVIGATION_STATUS':  (0xa05a24, 'navigation_status'),
    # the Songs page (patch/songs.c): sort_flag, the list order of class 0xf001 (0 alphabetical, 1 file name, 2 file format, 3 newest first, 4 oldest first;
    # getAllMusic dispatches on it, config_init reads it from [SYSSET] SORTSELECT, the sort dialog's row handler @0x47d114 stores it and writes the key)
    'SORT_FLAG':          (0xa059d4, 'sort_flag'),
    # the stock multi-select's selection: a pointer to a vector<int> (created once at start-up, ~0x50bb34) indexed by the row of *pdeq_showlist, 1 = selected
    'SEL_VEC':            (0xa045e0, None),
    # the Pinyin engine's global MatrixSearch* (PINYIN_PINS): NULL until im_open_decoder, and its first byte is inited_
    'PY_ENGINE':          (0xa0a360, None),
    # the iPod page's battery (patch/ipod.c): the stock status bar window; the app keeps it (system_bar_init @0x545490); its pgbar_battery value and img_battery picture are what the real bar shows
    'SYSTEM_BAR':         (0xa06f90, 'system_bar'),
    # Battery Percentage (patch/battery.c): the capacity get_battery_capacity leaves (an int, 0..100), which show_sysbar_face and the pull-down's face draw the fill from
    'POWER_CAPACITY':     (0xa059ec, 'power_capacity'),
    # the four words show_sysbar_face tests (0x54510c..0x545148) to decide whether the low / normal picture is chosen (not the charging one); BATTERY_PINS
    'POWER_EXT':          (0xa059f8, None),
    'POWER_USBSTATE':     (0xa059f4, None),
    'POWER_FLAG':         (0xa05aa8, None),
    'USBDAC_CHARGEFLAG':  (0x97cae8, 'usbdac_chargeflag'),
    # Podcasts (patch/pcmodel.c): the stock speed mode, 0..3 (see the PODCAST_PINS note)
    'PLAYSPEED_MODE':     (0xa05acc, 'playspeed_mode'),
    # Podcasts: the id3 state get_id3info (0x4dfd58) fills from the file's tags; the title / artist the player pages and the lock screen read
    'PLAYSONG_ID3INFO':   (0xa0d88c, 'playsong_id3info'),
    'SONG_NAME':          (0xa0513c, 'song_name'),
    'SONG_ARTIST':        (0xa0503c, 'song_artist'),
    # Settings (patch/m1plus.c, docs/modules/settings.md "Stock state"): the state the top page shows at the right of Wi-Fi, Bluetooth, EQ and Language (one byte each, one int each; the stock
    # status bar and pull-down read the same words): wififlag (1 on; wifi_switch clears it and saves [SYSSET] WIFI), bluetoothflag, equalizer_flag (the byte on_eqswitch_onclick flips and saves as [PLAYSET] EQFLAG),
    # equalizer_mode (the preset, 1..11) and language (the language menu's index, 0 zh_CN .. 12 uk_UK, as switch_language numbers them)
    'WIFI_FLAG':          (0x97caf8, 'wififlag'),
    'BT_FLAG':            (0xa05ac0, 'bluetoothflag'),
    'EQ_FLAG':            (0xa05ac2, 'equalizer_flag'),
    'EQ_MODE':            (0x97cb00, 'equalizer_mode'),
    # About: the serial number (a string of 16 bytes) and the Wi-Fi MAC (32), and the stock literals the model and firmware rows show
    'PRODUCT_SN':         (0xa0553c, 'product_sncode'),
    'WIFI_MAC':           (0xa061a8, 'wifi_mac'),
    'ABOUT_MODEL':        (0x747718, None),
    'ABOUT_FW':           (0x74773c, None),
    # Internet Radio (patch/radio.c, RADIO_PINS): the output selector stock's start_player passes to set_outputchannel (0, 1 the jacks, 2 Bluetooth, 3 USB), the idle counter of the DAC's power-off
    # (on_wm_idle_status: counting 1..30 while nothing plays, then mclSetDacPwr(0) and -1; a playing track zeroes it) and the volume the volume dialog and set_hs_po_output set
    'G_HEADSET_OUTPUT':   (0xa05a10, None),
    'LINEOUT_FLAG':       (0xa05aa7, None),   # the byte Settings > Line Out sets (LINEOUT_PINS: show_sysbar_face tests it); patch/peqout.c reads it for the per-output EQ
    'DACOFF_TIME':        (0x97cae0, 'dacoff_time'),
    'G_VOLUME':           (0x97cb10, 'volume'),
}
LIBC = {
    'atoi': ('int', 'const char *'), 'access': ('int', 'const char *, int'),
    # the Daily Mix's day number (patch/dailymix.c dm_today): the wall clock and its local calendar fields (struct tm: seconds, minutes, hours, mday, mon, year first)
    'time': ('long', 'long *'), 'localtime': ('const int *', 'const long *'),
    # Home (patch/home.c): the marker, the setting and the opt-in log
    'open': ('int', 'const char *, int, int'), 'read': ('int', 'int, void *, unsigned'),
    'write': ('int', 'int, const void *, unsigned'), 'close': ('int', 'int'), 'fsync': ('int', 'int'),
    # Cover Flow: the thumbnail cache, its one worker thread and the album/track deques
    'memset': ('void *', 'void *, int, unsigned'), 'memcpy': ('void *', 'void *, const void *, unsigned'),
    'strcmp': ('int', 'const char *, const char *'), 'strdup': ('char *', 'const char *'),
    'snprintf': ('int', 'char *, unsigned, const char *, ...'),
    'calloc': ('void *', 'unsigned, unsigned'), 'free': ('void', 'void *'),
    'fopen': ('void *', 'const char *, const char *'), 'fclose': ('int', 'void *'),
    'fread': ('unsigned', 'void *, unsigned, unsigned, void *'),
    'fwrite': ('unsigned', 'const void *, unsigned, unsigned, void *'),
    'fseek': ('int', 'void *, long, int'), 'ftell': ('long', 'void *'),
    'rename': ('int', 'const char *, const char *'), 'unlink': ('int', 'const char *'),
    'mkdir': ('int', 'const char *, unsigned'), 'statfs': ('int', 'const char *, void *'),
    'pthread_create': ('int', 'unsigned long *, const void *, void *(*)(void *), void *'),
    'pthread_join': ('int', 'unsigned long, void **'),
    'pthread_mutex_lock': ('int', 'void *'), 'pthread_mutex_unlock': ('int', 'void *'),
    '_create_deque': ('void *', 'const char *'), 'deque_init': ('void', 'void *'),
    'deque_assign': ('void', 'void *, const void *'), 'deque_size': ('unsigned', 'const void *'),
    'deque_at': ('void *', 'const void *, unsigned'), 'deque_destroy': ('void', 'void *'), 'deque_clear': ('void', 'void *'),
    # Artists and the artist-scoped Cover Flow (patch/artists.c, patch/coverflow.c)
    'strcasecmp': ('int', 'const char *, const char *'), '_deque_push_back': ('void', 'void *, const void *'),
    # Screenshot (patch/shot.c): the frame buffer, as stock's lcd_linux_fb_create calls them (ioctl 0x4600 / 0x4602, mmap)
    'ioctl': ('int', 'int, unsigned, void *'), 'mmap': ('void *', 'void *, unsigned, int, int, int, int'),
    'munmap': ('int', 'void *, unsigned'),
    # Podcasts (patch/pcmodel.c): the shows and episodes are found with opendir / readdir (struct dirent, 32-bit: d_name at +11), the files' dates with the stat stub's __xstat (version 3,
    # struct stat 144 bytes, st_mtime at +0x40; stock's own stat(), @0x741b20, is __xstat(3, ..)), the ring is moved in place
    'opendir': ('void *', 'const char *'), 'readdir': ('char *', 'void *'), 'closedir': ('int', 'void *'),
    '__xstat': ('int', 'int, const char *, void *'), 'memmove': ('void *', 'void *, const void *, unsigned'),
    # Podcast network (patch/pcnet.c): the libcurl easy interface, already imported by demo (stock's curl_init)
    'curl_global_init': ('int', 'long'), 'curl_easy_init': ('void *', 'void'), 'curl_easy_setopt': ('int', 'void *, int, ...'),
    'curl_easy_perform': ('int', 'void *'), 'curl_easy_getinfo': ('int', 'void *, int, ...'), 'curl_easy_cleanup': ('void', 'void *'),
    'pthread_detach': ('int', 'unsigned long'), 'sleep': ('unsigned', 'unsigned'),
    'lseek': ('long', 'int, long, int'),   # Podcast downloads (patch/pcnet.c): the size of a .part file, lseek(fd, 0, SEEK_END)
    # Podcast cover shrink (patch/pccover.c): demo's own libjpeg 7 (stock's picture decoder / encoder at 0x5dd5ec, 0x5de554 call the same ones), and _setjmp for its error exit (JPEG_PINS)
    'jpeg_std_error': ('void *', 'void *'), 'jpeg_CreateDecompress': ('void', 'void *, int, unsigned'), 'jpeg_stdio_src': ('void', 'void *, void *'),
    'jpeg_read_header': ('int', 'void *, int'), 'jpeg_start_decompress': ('int', 'void *'), 'jpeg_read_scanlines': ('unsigned', 'void *, unsigned char **, unsigned'),
    'jpeg_destroy_decompress': ('void', 'void *'), 'jpeg_CreateCompress': ('void', 'void *, int, unsigned'), 'jpeg_stdio_dest': ('void', 'void *, void *'),
    'jpeg_set_defaults': ('void', 'void *'), 'jpeg_set_quality': ('void', 'void *, int, int'), 'jpeg_start_compress': ('void', 'void *, int'),
    'jpeg_write_scanlines': ('unsigned', 'void *, unsigned char **, unsigned'), 'jpeg_finish_compress': ('void', 'void *'), 'jpeg_destroy_compress': ('void', 'void *'),
    '_setjmp': ('int', 'void *'),
    # The Wi-Fi page (patch/wifictl.c): the control socket, as stock's wpa_ctrl client makes it (AF_UNIX datagram, bind to a private path, connect to the interface's socket, send, select, recv; demo imports all of them)
    'socket': ('int', 'int, int, int'), 'bind': ('int', 'int, const void *, unsigned'), 'connect': ('int', 'int, const void *, unsigned'), 'send': ('int', 'int, const void *, unsigned, int'),
    'recv': ('int', 'int, void *, unsigned, int'), 'select': ('int', 'int, void *, void *, void *, void *'), 'getpid': ('int', 'void'), 'usleep': ('int', 'unsigned'),
    'rmdir': ('int', 'const char *'),   # Podcasts unsubscribe (patch/podcasts.c): the show folder left empty
    # Internet Radio (patch/radio.c, docs/modules/radio.md): the parsers' string calls; demo imports all of them
    'strlen': ('unsigned', 'const char *'), 'strstr': ('char *', 'const char *, const char *'), 'strchr': ('char *', 'const char *, int'), 'strrchr': ('char *', 'const char *, int'),
    'strncasecmp': ('int', 'const char *, const char *, unsigned'),
    # Album cover extraction (patch/covercache.c art_embedded): libtag_c's taglib_album_picture(track, out, 0x100000, 0x600000), exactly as toolsGetAlbumCover calls it (the picture goes to /tmp/.tmp_picture; out is not used); 2 = JPEG, 1 = PNG, 0 = none
    'taglib_album_picture': ('int', 'const char *, char *, int, int'),
    # Track durations (patch/durations.c dur_probe): libtag_c's taglib_file_new(path, readAudioProperties) / taglib_file_audioproperties / taglib_file_free, as toolsGetMusicInfo (0x5ec6a8) calls them (demo imports all three)
    'taglib_file_new': ('void *', 'const char *, int'), 'taglib_file_audioproperties': ('void *', 'void *'), 'taglib_file_free': ('void', 'void *'),
    # the Equalizer page's preset parser (patch/peq.c, after q2-pod's: it reads numbers with sscanf, the APO shelves need pow and sqrt)
    '__isoc99_sscanf': ('int', 'const char *, const char *, ...'), 'ferror': ('int', 'void *'),
    'pow': ('double', 'double, double'), 'sqrt': ('double', 'double'), 'cos': ('double', 'double'), 'sin': ('double', 'double'),
}


SCROLL_DONE = 0x6101b8              # scroll_view's EVT_ANIM_END handler (static): wa = 0, the scroll end events; ret_t (ctx = widget, event)
FUNCTIONS.update({
    'widget_dispatch':         ('int', 'void *, void *', 0x66cec8),
    'widget_dispatch_event_to_target_recursive': ('int', 'void *, void *', 0x66e08c),
    'widget_animator_destroy': ('int', 'void *', 0x6735ac),
})


# ---- The Folders page (patch/folders.c, docs/modules/folders.md) -------------------------------------------------------
# The stock folder_page keeps its state in globals and four functions: layer (0xa0554c: 0 before the first enter, 1 the root list of storages, 2 and up the folders), the path (0xa05550),
# the title (0xa0533c, filled by getFormatString("folder") at the root and the folder's name below), the m3u path (0xa0483c, set while a playlist file is open) and the shown list
# (*pdeq_showlist, stSongInfo records: +8 name, +0xc url, +0x34 type 2 SD / 3 OTG / 4 folder / 1 playlist file / 8 audio file, +0x48 cue). Our page calls the stock functions on that state.
FUNCTIONS.update({
    'folder_enter':            ('int', 'int, int', 0x4db978),      # (record index, yoffset): -1 resets to the root list; 8 = an audio file (nothing changed), 1 = entered, -1 .. -4 = not entered
    'folder_back':             ('int', 'int *', 0x4dbecc),         # (yoffset out): 0 = left the root (state cleared), else one level up; *out is the offset the child was entered at (not written at the root)
    'folder_reload':           ('int', 'void', 0x4db7ec),          # the current level's list again
    'is_folderplaying':        ('int', 'const char *', 0x5329d8),  # the folder (record url) holds the song being played from a folder queue
})
DATA.update({
    'TIME_ZONE':          (0xa05ab4, 'time_zone'),   # int: [SYSSET] TIMEZONE, the saved zone index (patch/timezones.c)
    'LOCK_ON':            (0xa05aa3, 'screensaver_mode'),   # byte: stock's lock screen switch ([SYSSET] SCREENSAVER; patch/lockscreen.c lk_enabled)
    'LOCK_TIMESHOW':      (0xa05aa2, 'screensaver_timeshow'),   # byte: stock's lock screen "show time" switch ([SYSSET] SSAVERTIMESHOW; patch/lockscreen.c lk_time)
    'LIGHT_MODE':         (0xa05a7c, 'backlighttime_mode'),   # int: stock's backlight time index, 0 never .. 4 five minutes ([SYSSET] LIGHTTIME; patch/display.c disp_light)
    'LED_MODE':           (0xa05a75, 'atmosphereled_mode'),   # byte: stock's lamp mode, 0 off, 1 green, 2 blue ([SYSSET] ATMOSPHERELEDMODE; patch/display.c disp_led)
    'LED_FOLLOW':         (0xa05a74, 'ledfollowscreen_flag'),   # byte: stock's Follow Screen switch ([SYSSET] LEDFOLLOWSCREEN; patch/display.c disp_follow)
    # Settings > System > Buttons & Power (patch/keyspower.c, docs/modules/keyspower.md): stock's own state words
    'KEY_LOCK_FLAG':      (0xa05aa0, 'keylock_flag'),   # byte: Button Lock on ([SYSSET] LOCKFLAG; the Control Center tile system_keylock writes it too)
    'KEY_LOCK_MODE':      (0x97caec, 'keylock_mode'),   # int: the lock's mode, 1 volume keys, 2 the other keys, 3 both ([SYSSET] LOCKMODE)
    'TAP_WAKE':           (0xa05aa1, 'doublewake_flag'),   # byte: Tap to Wake ([SYSSET] DOUBLEWAKE)
    'STANDBY_FLAG':       (0xa05a8c, 'standbyflag'),   # byte: Auto-Standby on ([SYSSET] STANDBYMODE)
    'SHUTDOWN_MODE':      (0xa05a84, 'savepowermode'),   # int: Auto-Shutdown, 0 off, 1 .. 4 = 1, 3, 5, 10 minutes ([SYSSET] SAVEPOWERMODE)
    # stock's brightness page code, bound to our slider (patch/display.c; no symbols: the entries and stock's own bindings are pinned, LOCKSCREEN_PINS)
    'BRIGHT_REFRESH':     (0x4a4450, None),   # int (window): label_brightness and slider_brightness from the word lightness
    'BRIGHT_CHANGED':     (0x4a4678, None),   # int (window, event): the slider's EVT_VALUE_CHANGED handler
    'BRIGHT_CHANGING':    (0x4a4744, None),   # int (window, event): its EVT_VALUE_CHANGING handler
    'LIGHTNESS':          (0x97caf0, 'lightness'),   # int: stock's brightness, 0 .. 100 ([SYSSET] LIGHTNESS; written by stock's own handlers only, test/pod/display.py reads it)
    'LOCK_PICTURE':     (0xa0473c, 'screensaver_picture'),   # char[256]: the chosen wallpaper, the resource name screensaver_default or a path ("file://" is added where it is shown; [SYSSET] SCREENSAVERPATH)
    'LOCK_LIST':          (0xa045cc, 'pdeq_screensaverlist'),   # void *: the deque the wallpaper grid lists (strings: the Default name first, then up to five paths)
    'FOLDER_LAYER':       (0xa0554c, None),
    'FOLDER_TITLE':       (0xa0533c, None),
    'FOLDER_M3U':         (0xa0483c, None),
    'FOLDER_COVER':       (0xa05a67, 'foldercover_flag'),   # byte: stock's Folder cover switch ([PLAYSET] FOLDERCOVER; patch/folders.c reads it, docs/modules/folders.md)
})


# ---- Internet Radio (patch/radio.c, docs/modules/radio.md) --------------------------------------------------------------------
# The stock calls the radio makes, from the UI thread on a tap (the same sequence stock's start_player and stop_player run) and its one hook: mclStartPlayer, which every local track's start
# runs before hciplayer opens the PCM (q2-pod's ringnav_start_player hooks it too). rd_start_player stops the radio, then runs stock. Reachable at boot (Memory Playback's start_player), where
# the radio is never running: it does one comparison there.
START_PLAYER, START_PLAYER_PROLOGUE = 0x5d5300, (0x3c1c0043, 0x279cebd0, 0x0399e021)
# Hook 18: save_stop_player / save_start_player, the pair every output change runs around set_outputchannel (check_otg_status, set_hs_po_output, set_hs_bal_output, switchBluetooth, the BT
# link handlers, the DSD mode, into_standby): the stop is mclSetMute(1), 150 ms, mclStop (only when mclGetPlayStatus is not 1; it saves that status), the start calls mclStartPlayer when the saved
# status is not 1 and below the queue size. While a station runs, rd_save_stop stops the stream and rd_save_start restarts it on the new output (patch/radio.c). Both are UI-thread handlers' calls.
SAVE_STOP, SAVE_STOP_PROLOGUE = 0x4e2304, (0x3c1c0052, 0x279c1bcc, 0x0399e021)
SAVE_START, SAVE_START_PROLOGUE = 0x4e23e8, (0x3c1c0052, 0x279c1ae8, 0x0399e021)
# Hook 17: stock's on_backtoplayer_onclick (every stock page's Now Playing button): rn_backtoplayer opens Radio Now Playing while a station connects or plays, else resumes stock. Not reachable at boot.
BACKTOPLAYER, BACKTOPLAYER_PROLOGUE = 0x4cd58c, (0x3c1c0053, 0x279c6944, 0x0399e021)
FUNCTIONS.update({
    'stop_player':          ('void', 'void', 0x4e08c4),             # stops hciplayer unless stopped: mclSetMute(1), 150 ms, mclStop, the notifications (UI thread, stock's own key paths)
    'set_outputchannel':    ('int', 'int, int, int', 0x4d6f68),      # (output, mode, power): the jacks: mclSetHeadsetMode(0) and mclSetDacPwr(1) (a2 0) / (100)
    'set_devicevolume':     ('int', 'int', 0x4d6cf8),
    # Playing through hciplayer: mcl_tidalStartPlayer(url) is mclStartPlayer minus the queue lookup (it sends {set-songurl\\URL|...}); mclStop sends {mcl-stop} and waits for hciplayer's "exit"
    # (returns -1 at once when the running byte is 0); mclGetHciplayerStatus is the byte mclSyncPlayerStatus's thread refreshes every 200 ms from {player-status\request} (1 = "playing")
    'mcl_tidalStartPlayer': ('int', 'const char *', 0x5d5184), 'mclStop': ('int', 'void', 0x5d244c), 'mclGetHciplayerStatus': ('int', 'void', 0x5d436c),
    'mclSetPause': ('int', 'void', 0x5d2604), 'mclSetResume': ('int', 'void', 0x5d2668),   # the mini bar's pause / resume of a station (patch/minibar.c): {mcl-pause} / {mcl-resume} to hciplayer, then the status 3 / 2
    'into_standby': ('void', 'void', 0x4e7508),   # stock standby path: stops active output, turns off the display and releases Wi-Fi/CPU without writing power preferences
    'mclSetPcmMode':        ('int', 'void', 0x5d6080), 'mclSetMute': ('int', 'int', 0x5d4dac), 'mclGetOutputWay': ('int', 'void', 0x5d45a4), 'mclSetDacPwr': ('int', 'int', 0x5d5c1c),
})


def patch_radio(image, ps, payload_len):
    target = ps['rd_start_player']
    check(BASE <= target < BASE + payload_len, 'radio entry symbol outside payload')
    hook(image, START_PLAYER, START_PLAYER_PROLOGUE, target, 'mclStartPlayer')
    for at, prologue, sym, what in ((SAVE_STOP, SAVE_STOP_PROLOGUE, 'rd_save_stop', 'save_stop_player'), (SAVE_START, SAVE_START_PROLOGUE, 'rd_save_start', 'save_start_player')):
        target = ps[sym]
        check(BASE <= target < BASE + payload_len, f'{sym} symbol outside payload')
        hook(image, at, prologue, target, what)
    target = ps['rn_backtoplayer']
    check(BASE <= target < BASE + payload_len, 'back-to-player entry symbol outside payload')
    hook(image, BACKTOPLAYER, BACKTOPLAYER_PROLOGUE, target, 'on_backtoplayer_onclick')


# ---- Now Playing's More dialog (patch/playmore.c, docs/modules/playmore.md) -------------------------------------------
# dialog_playmore_dialog_init, the init of dialog/playmore_dialog: called only by the navigator's dialog-init dispatcher
# (0x4d1244 .. 0x4d124c, behind the strcmp with "dialog/playmore_dialog"), when Now Playing's More button opens the dialog.
# m1plus_playmore_init runs the stock init to completion (it binds every row and pins the dialog at y 130), then re-orders
# the rows; any mismatch leaves the stock menu.
PLAYMORE_INIT = 0x479cc4
PLAYMORE_INIT_PROLOGUE = (0x3c1c0059, 0x279ca20c, 0x0399e021)


def patch_playmore(image, ps, payload_len):
    target = ps['m1plus_playmore_init']
    check(BASE <= target < BASE + payload_len, 'playmore entry symbol outside payload')
    check_pins(image, PLAYMORE_PINS)
    hook(image, PLAYMORE_INIT, PLAYMORE_INIT_PROLOGUE, target, 'dialog_playmore_dialog_init')


# ---- the pull-down (patch/pulldown.c, docs/modules/pulldown.md) -----------------------------------------------------------
# dialog_dropdown_dialog_init, the init of dialog/dropdown_dialog: called only by the navigator's dialog-init dispatcher
# (0x4d1c7c .. 0x4d1c84, behind the strcmp with "dialog/dropdown_dialog"), when the status bar swipe opens the pull-down.
# m1plus_pulldown_init runs the stock init to completion (it binds the dialog's pointer handlers and every tile's click through
# the widget_foreach visitor 0x473f30), then lays the eight tiles out as the saved file says; any mismatch leaves the stock grid.
PULLDOWN_INIT = 0x475f04
PULLDOWN_INIT_PROLOGUE = (0x3c1c0059, 0x279cdfcc, 0x0399e021)
# The "inside settings" flags: stock's System Settings / Playback Settings page inits store 1 (0x4ada78 / 0x4a0c88), their Back handlers clear a positive flag, the Home foreground callback clears both, and nothing else does: the
# Now Playing button (on_backtoplayer_onclick) leaves the page in the window stack behind the player with its flag set. The pull-down's tile visitor (0x473f30) disables a tile and skips its click bind while the flag is
# positive, its click handlers (0x4754c8 System, 0x475558 Playback) do nothing for a nonzero flag and otherwise store 2 and quit the dialog; on_wm_tsmove_fun then opens the page by navigator_to for a flag of 2. m1plus_pulldown_init
# reconciles both flags with the window stack before the stock init, and the two navigator_to calls (PULLDOWN_OPEN_SITES, "playset/playset_page" then "systemset/sysset_page") become pd_open_settings (docs/modules/payload.md hook 22).
DATA.update({
    'SYSSET_FLAG':        (0xa05a48, 'syssetinto_flag'),     # int: 1 while System Settings is open, 2 for a moment after its tile is tapped
    'PLAYSET_FLAG':       (0xa05a4c, 'playsetinto_flag'),    # int: the same for Playback Settings
})
FUNCTIONS['window_manager_switch_to'] = ('int', 'void *, void *, void *, int', 0x67891c)   # (wm, current window, target window, close current): stock's own restack of a window already in the stack
PULLDOWN_PINS += PULLDOWN_FLAG_PINS
PULLDOWN_SITE_WORDS = ((PULLDOWN_OPEN_SITES[0], 0x0411113a), (PULLDOWN_OPEN_SITES[1], 0x04111130))   # the two `bal navigator_to` (0x4d1d80) words the hook replaces


def patch_pulldown(image, ps, payload_len):
    target = ps['m1plus_pulldown_init']
    check(BASE <= target < BASE + payload_len, 'pulldown entry symbol outside payload')
    check_pins(image, PULLDOWN_PINS)
    check_pins(image, [(a, old, 'on_wm_tsmove_fun: bal navigator_to') for a, old in PULLDOWN_SITE_WORDS])
    hook(image, PULLDOWN_INIT, PULLDOWN_INIT_PROLOGUE, target, 'dialog_dropdown_dialog_init')
    check(BASE <= ps['pd_open_settings'] < BASE + payload_len, 'pull-down page open symbol outside payload')
    for a in PULLDOWN_OPEN_SITES: struct.pack_into('<I', image, fileoff(image, a), jal(ps['pd_open_settings'], a))   # (PULLDOWN_PINS checked each site's word and its delay slot)


def gen_scroll_h(out):
    (pathlib.Path(out) / 'scroll.h').write_text(
        '/* Generated by tools/pod.py; do not edit. */\n#pragma once\n'
        f'#define stock_scroll_done ((int (*)(void *, void *))0x{SCROLL_DONE:x}u)\n')


def j(addr): return 0x08000000 | (addr >> 2)
def check(cond, msg):
    if not cond: raise ValueError(msg)
def check_pins(buf, pins): modlib.check_pins(buf, pins, fileoff)


def segments(b):
    phoff = struct.unpack_from('<I', b, 28)[0]
    size, num = struct.unpack_from('<HH', b, 42)
    check(size == 32, 'unexpected program header size')
    return [(phoff + i * size, struct.unpack_from('<8I', b, phoff + i * size)) for i in range(num)]


def fileoff(b, a):
    for _, (t, o, v, _, f, _, _, _) in segments(b):
        if t == 1 and v <= a < v + f: return o + a - v
    raise ValueError(f'unmapped address {a:#x}')


def dynsym(path):
    out = {}
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        sec = elf.get_section_by_name('.dynsym')
        for s in sec.iter_symbols():
            if s['st_value'] and s.name: out.setdefault(s.name, s['st_value'])
    return out


def got_slots(path, names):
    """Absolute GOT slot address for each wanted imported libc function."""
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        dynsymsec = elf.get_section_by_name('.dynsym'); got = elf.get_section_by_name('.got')
        tags = {t.entry.d_tag: t.entry.d_val for t in elf.get_section_by_name('.dynamic').iter_tags()}
        local, gotsym = tags['DT_MIPS_LOCAL_GOTNO'], tags['DT_MIPS_GOTSYM']
        n = dynsymsec.num_symbols()
        slot = {}
        for i in range(gotsym, n):
            nm = dynsymsec.get_symbol(i).name
            if nm in names: slot[nm] = got['sh_addr'] + 4 * (local + i - gotsym)
    missing = set(names) - set(slot)
    check(not missing, f'libc not imported by demo: {sorted(missing)}')
    return slot


def check_libcstl_bytes(data):
    """The pins on the bytes of libcstl (the tests hand it a doctored copy): the three symbols' offsets and the words of deque_size and deque_pop_back, in a text that is mapped at its file offsets."""
    elf = ELFFile(io.BytesIO(data))
    syms = {s.name: s['st_value'] for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name}
    check((syms.get('deque_size'), syms.get('deque_pop_back'), syms.get('_deque_shrink_at_end')) == (CSTL_SIZE, CSTL_POP, CSTL_SHRINK), 'libcstl: deque_size / deque_pop_back / _deque_shrink_at_end moved')
    load = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD')
    check(load['p_vaddr'] == load['p_offset'] == 0 and load['p_filesz'] > CSTL_POP + 24, 'libcstl: the first segment is not the text at its file offsets')
    check(struct.unpack_from('<8I', data, CSTL_SIZE) == CSTL_SIZE_WORDS, 'libcstl: deque_size words differ from the pin')
    check(struct.unpack_from('<6I', data, CSTL_POP) == CSTL_POP_WORDS, 'libcstl: deque_pop_back words differ from the pin')


def check_libcstl(demo_path):
    """Clear's library: demo needs libcstl.so.2, which is the pinned file (SHA-256, symbols, words). Returns demo's image end (the first address above its segments, page aligned): a resolved
    import lies above it, an unresolved one is a stub inside."""
    root = pathlib.Path(demo_path).parents[2]
    lib, link = root / LIBCSTL, root / LIBCSTL_LINK
    data = lib.read_bytes() if lib.is_file() else b''
    check(sha(data) == LIBCSTL_SHA, f'{LIBCSTL}: not the pinned libcstl (got {sha(data)[:16]})')
    check(link.is_symlink() and os.path.realpath(link) == os.path.realpath(lib), f'{LIBCSTL_LINK} is not a link to {LIBCSTL}')
    check_libcstl_bytes(data)
    with open(demo_path, 'rb') as f:
        elf = ELFFile(f)
        needed = [t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag == 'DT_NEEDED']
        end = max(s['p_vaddr'] + s['p_memsz'] for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD')
    check(pathlib.Path(LIBCSTL_LINK).name in needed, 'demo no longer needs libcstl.so.2')
    return (end + 0xfff) & ~0xfff


def gen_stock_h(out, demo_path):
    syms = dynsym(demo_path)
    slots = got_slots(demo_path, LIBC)
    image_end = check_libcstl(demo_path)
    h = ['/* Generated by tools/pod.py from demo .dynsym; do not edit. */', '#pragma once']
    for name, (ret, args, addr) in FUNCTIONS.items():
        check(syms.get(name) == addr, f'{name}: address {syms.get(name)} != pinned {addr:#x}')
        h.append(f'#define {name} (({ret} (*)({args}))0x{addr:x}u)')
    for name, (ret, args) in LIBC.items():
        h.append(f'extern {ret} pod_lib_{name}({args});')
        h.append(f'#define {name} pod_lib_{name}')
    for name, (addr, sym) in DATA.items():
        if sym is not None:
            check(syms.get(sym) == addr, f'{sym}: address {syms.get(sym)} != pinned {addr:#x}')
        h.append(f'#define {name} 0x{addr:x}u')
    h.append(f'#define GOT_DEQUE_SIZE 0x{slots["deque_size"]:x}u')   # demo's GOT slot of deque_size: the resolved address locates libcstl's deque_pop_back (patch/shuffle.c cstl_pop_back)
    h.append(f'#define STOCK_IMAGE_END 0x{image_end:x}u')   # the first address above demo's segments: a lazily bound slot holds a stub below it until the first call
    h.append(f'#define CSTL_SIZE_OFF 0x{CSTL_SIZE:x}u'); h.append(f'#define CSTL_POP_OFF 0x{CSTL_POP:x}u')
    h.append('#define CSTL_SIZE_WORDS {' + ','.join(f'0x{w:08x}u' for w in CSTL_SIZE_WORDS) + '}'); h.append('#define CSTL_POP_WORDS {' + ','.join(f'0x{w:08x}u' for w in CSTL_POP_WORDS) + '}')
    h.append('#define STOCK_DB_PATH ((const char *)0x745a34u)')   # "/mnt/data/database.db" (QUERY_PINS)
    h.append('#define STOCK_SONG_ROW ((void *)0x4e9058u)')       # the song row callback getAllMusic passes to toolsQueryDbTable (QUERY_PINS)
    h.append('#define STOCK_ALBUM_ROW ((void *)0x4e93c8u)')      # the album row callback getAllAlbum passes (QUERY_PINS)
    h.append('#define STOCK_ALBUM_HEAD "' + ALBUM_HEAD + '"')    # the album list statement up to its filter and the grouping after it (cc_album_rep_key puts a where between them)
    h.append('#define STOCK_ALBUM_GROUP "' + ALBUM_GROUP + '"')
    h.append('#define STOCK_ALBUM_SQL STOCK_ALBUM_HEAD STOCK_ALBUM_GROUP')   # getAllAlbum's statement with its %s filled, byte for byte (checked against the string at 0x74bad8)
    h.append(f'#define STOCK_HOME_CLICK 0x{HOME_CLICK:x}u')   # the icon click handler stock registers per icon
    h.append(f'#define POD_ENTRY_NAME "{pod_pages.HOME_ENTRY}"')   # the added icon's widget name (a decimal id, as stock's)
    h.append(f'#define stock_np_mode_button ((int (*)(void *))0x{NP_MODE_BUTTON:x}u)')   # Now Playing's mode button picture (patch/nowplaying.c)
    h.append(f'#define stock_playlist_import ((int (*)(void *, void *))0x{PLAYLIST_IMPORT:x}u)')   # the stock Playlists page's Import / Export rows
    h.append(f'#define stock_playlist_export ((int (*)(void *, void *))0x{PLAYLIST_EXPORT:x}u)')
    h.append(f'#define stock_tidal_search ((int (*)(void *, void *))0x{TIDALKB_SEARCH:x}u)')   # the stock Tidal search page's search routine (patch/tidalkb.c; TIDALKB_PINS)
    h.append(f'#define tf_update_click ((int (*)(void *, void *))0x{TF_UPDATE:x}u)')   # the stock TF card update's click handler (patch/update.c; TFUPDATE_PINS)
    # the engine's dictionary members (patch/search.c pinyin initials; not exported, pinned by PINYIN_PINS): DictList::get_lemma_id(this, char16 *, len), get_splids_for_hanzi(this, hanzi, half_splid, splids, max), SpellingTrie::get_spelling_str(this, id)
    h.append('#define py_lemma_id ((unsigned (*)(void *, const unsigned short *, unsigned))0x5c01a4u)')
    h.append('#define py_splids ((unsigned short (*)(void *, unsigned short, unsigned short, unsigned short *, unsigned short))0x5bffd4u)')
    h.append('#define py_spelling ((const char *(*)(void *, unsigned short))0x5c922cu)')
    h.append('#define TIMEZONE_NAMES {' + ','.join(json.dumps(tz) for _, tz in timezones.TIMEZONES) + '}')   # patch/timezones.c
    h.append('#define TIMEZONE_LABELS {' + ','.join(json.dumps(label) for label, _ in timezones.TIMEZONES) + '}')
    h.append('#define TIMEZONE_ORDER {' + ','.join(map(str, timezones.ORDER)) + '}')
    h.append(f'#define glyph_cache_lookup ((int (*)(void *, unsigned, unsigned, void *))0x{GLYPH_CACHE_LOOKUP:x}u)')   # static in demo (TEXTGAMMA_PINS): 0 on a hit, the glyph_t copied to a3
    h.append(f'/* text coverage gamma G = {textgamma.GAMMA} (tools/textgamma.py) */')
    h.append('#define TEXT_GAMMA_LUT {' + ', '.join(str(v) for v in textgamma.lut()) + '}')   # patch/textgamma.c
    h.append('#define PCREGION_CODES {' + ','.join(json.dumps(c) for c in pcregion.CODES) + '}')   # patch/pcregion.c: the Podcast Region picker's storefronts (tools/pcregion.py)
    h.append('#define PCREGION_NAMES {' + ','.join(json.dumps(n) for n in pcregion.NAMES) + '}')
    h.append('#define PCREGION_ZONES {' + ','.join(json.dumps(c) for c in pcregion.ZONE_TABLE) + '}')   # the storefront of each time zone index ("" = none)
    h.append(f'#define PCREGION_N {len(pcregion.CODES)}')
    h.append('extern int stock_home_click_trampoline(void *, void *);')
    h.append('extern int stock_playing_init_trampoline(void *, void *);')
    h.append('extern int stock_bigcover_init_trampoline(void *, void *);')
    h.append('extern int stock_lockscreen_init_trampoline(void *, void *);')
    h.append('extern int stock_playmore_init_trampoline(void *, void *);')
    h.append('extern int stock_pulldown_init_trampoline(void *, void *);')
    h.append('extern int stock_start_player_trampoline(void);')
    h.append('extern void stock_save_stop_trampoline(void);')
    h.append('extern void stock_save_start_trampoline(int);')
    h.append('extern int stock_backtoplayer_trampoline(void *, void *);')
    h.append('extern int stock_dbquery_trampoline(const char *, const char *, void *, int);')
    h.append('extern int stock_sorted_query_trampoline(const char *, const char *, void *, int);')
    for macro, names in (('LIGHT_KEEP', palette.KEEP), ('LIGHT_WHOLE', palette.WHOLE), ('TINT_SURFACE', palette.TINT_SURFACE), ('LIGHT_EXEMPT', palette.EXEMPT), ('LIGHT_COVER', palette.COVER_PAGES), ('ACCENT_FILL', palette.ACCENT_FILL), ('ACCENT_SWITCH', palette.ACCENT_SWITCH), ('ACCENT_PRESS', palette.ACCENT_PRESS), ('ACCENT_DISC', palette.ACCENT_DISC), ('ACCENT_GLYPH', palette.ACCENT_GLYPH), ('ACCENT_GLYPH_NOT', palette.ACCENT_GLYPH_NOT), ('ACCENT_TILE', palette.ACCENT_TILE), ('ACCENT_SHUFDOWN', palette.ACCENT_SHUFDOWN), ('ACCENT_GLYPH_STOCK', palette.ACCENT_GLYPH_STOCK)):   # Light Mode's image name prefixes (tools/palette.py): a string literal of NUL-ended names
        h.append(f'#define {macro} "' + ''.join(n + '\\0' for n in names) + '"')
    h.append('extern int coverflow_open(void);')
    h.append('extern int coverflow_landscape(void);')
    h.append('extern int coverflow_landscape_toggle(void);')
    h.append('extern int coverflow_volkeys(void);')
    h.append('extern int coverflow_volkeys_toggle(void);')
    # the customisable menu (patch/menu.c): its item count, the default shown prefix and the row geometry
    h.append(f'#define POD_MENU_ITEMS {len(pod_pages.ITEMS)}')
    h.append(f'#define POD_MENU_DEFAULT {len(pod_pages.DEFAULT_MENU)}')   # the default menu: this many items ...
    h.append('#define POD_MENU_DEFAULT_IDS {' + ', '.join(str(i) for i in pod_pages.DEFAULT_MENU) + '}')   # ... these item ids, in order
    h.append(f'#define POD_MENU_FILE_MAX {pod_pages.MENU_FILE_MAX}')
    h.append(f'#define POD_MENU_ROWS {len(pod_pages.MENU.rows)}')
    h.append(f'#define POD_SETTINGS_ID {pod_pages.SETTINGS_ID}')
    h.append(f'#define POD_EXTRAS_ROWS {len(pod_pages.EXTRAS_PAGE.rows)}')
    h.append('#define POD_EXTRAS_ORDER {' + ', '.join(str(i) for i in pod_pages.EXTRAS_ORDER) + '}')   # the Extras page's rows (item ids) top to bottom
    h.append(f'#define POD_EXTRAS_GROUPS {len(pod_pages.EXTRAS_GROUPS)}')   # the Extras page's titled groups (section headers pod_hdr0 ..) ...
    h.append('#define POD_EXTRAS_GROUP {' + ', '.join(str(g) for g in pod_pages.EXTRAS_GROUP_OF) + '}')   # ... the group of each item id ...
    h.append(f'#define POD_EXTRAS_HDR_H {pod_pages.HDR_H}')   # ... and a header's height
    h.append(f'#define POD_ROW_H {pod_ui.ROW_H}')
    import pod_settings as PST   # the Equalizer page's column (patch/peq_ui.c): its height with n presets (POD_PEQ_BASE + n rows) and with none (the hint under Graphic EQ)
    h.append(f'#define POD_PEQ_BASE {PST.layout(pod_pages.peq_items(1))[1] - PST.ROW_H}')
    h.append(f'#define POD_PEQ_NONE {PST.layout(pod_pages.peq_items(0))[1]}')
    h.append(f'#define POD_LIB_BASE {PST.layout([pod_pages.PEQLIB_DOWNLOAD])[1]}')   # the Presets page's column with no file: the top and end spacers and the download row (patch/peqlib.c)
    h.append(f'#define POD_LIB_HDR {PST.HDR_H}')
    h.append(f'#define POD_LIB_ROW {PST.LIB_ROW_H}')
    # the Songs rail's alignment, from the tree's own font (tools/pod_ui.py rail_metrics): twice the cap ink's centre within an item, and each letter's rect shift
    font_path = os.path.join(os.path.dirname(os.path.dirname(demo_path)), 'assets/default/raw/fonts/default.ttf')
    ink2, dx = pod_ui.rail_metrics(font_path)
    for n, w in zip((2, 3, 4), pod_ui.pct_widths(font_path)): h.append(f'#define BP_W{n} {w}')   # the status bar percentage label's width for a text of n characters ("5%", "87%", "100%"; patch/battery.c)
    h.append(f'#define SG_RAIL_INK2 {ink2}')
    h.append('#define SG_RAIL_DX {' + ', '.join(str(d) for d in dx) + '}   /* "#", A..Z */')
    h.append('extern int shuffle_play(int);')
    (out / 'stock.h').write_text('\n'.join(h) + '\n')
    # The page and row tables, included by patch/m1plus.c alone.
    h = ['/* Generated by tools/pod.py from tools/pod_pages.py; do not edit. */', '#pragma once']
    pages = pod_pages.PAGES
    for pi, page in enumerate(pages):
        if page.rows:
            h.append(f'static const struct pod_row pod_rows_{pi}[] = {{')
            for ri, r in enumerate(page.rows):
                h.append(f'    {{"pod_row{ri}", {r.action}, {r.arg}}},')
            h.append('};')
    h.append('static const struct pod_stock POD_STOCK[] = {')   # ACT_STOCK's pages: the navigator path, the window name (0: no restack) and the value the row shows (VK_*: 0 none, else 1 + the index in STOCK_VALUES)
    for name, value, window in pod_pages.STOCK_PAGES:
        h.append(f'    {{"{name}", {chr(34) + window + chr(34) if window else 0}, {pod_pages.STOCK_VALUES.index(value) + 1 if value else 0}}},')
    h.append('};')
    import pod_settings as ST   # the value labels' fit (patch/m1plus.c value_fit): the right edge of a value's box and the room a value may take, the label's left edge and the gap between them
    h.append(f'#define POD_VALUE_RIGHT {ST.value_box()[0] + ST.VALUE_W}')
    h.append(f'#define POD_VALUE_MAX {ST.VALUE_MAX}')
    h.append(f'#define POD_VALUE_GAP {ST.VALUE_LABEL_GAP}')
    h.append(f'#define POD_LABEL_X {ST.TEXT_X}')
    h.append(f'#define POD_INFO_RIGHT {ST.RIGHT}')   # the About rows' value: its right edge, the most it takes, and the label's left edge
    h.append(f'#define POD_INFO_MAX {ST.INFO_MAX}')
    h.append(f'#define POD_INFO_LABEL_X {ST.CM + ST.PAD}')
    h.append('static const struct pod_page POD_PAGES[] = {')
    for pi, page in enumerate(pages):
        rows = f'pod_rows_{pi}' if page.rows else '0'
        h.append(f'    {{"{page.key}", {rows}, {len(page.rows)}, {page.wrap_notes()}u}},')
    h.append('};')
    h.append(f'#define POD_PAGE_COUNT {len(pages)}')
    h.append(f'#define POD_ENTRY_ID {pod_pages.HOME_ENTRY}')
    h.append('#define POD_ENTRY_PAGE 0')
    h.append('#define POD_MENU_PAGE 0')
    h.append(f'#define POD_SETTINGS_PAGE {pod_pages.SETTINGS_PAGE_INDEX}')
    h.append(f'#define POD_EXTRAS_PAGE {pod_pages.EXTRAS_PAGE_INDEX}')
    h.append(f'#define POD_MENUCFG_PAGE {pod_pages.MENUCFG_PAGE_INDEX}')
    h.append(f'#define POD_EXTRASCFG_PAGE {pod_pages.EXTRASCFG_PAGE_INDEX}')
    h.append(f'#define POD_DEVELOPER_PAGE {pod_pages.DEVELOPER_PAGE_INDEX}')
    h.append(f'#define POD_CACHE_PAGE {pod_pages.CACHE_PAGE_INDEX}')
    h.append(f'#define POD_DISPLAY_PAGE {pod_pages.DISPLAY_PAGE_INDEX}')
    h.append(f'#define POD_KEYSPOWER_PAGE {pod_pages.KEYSPOWER_PAGE_INDEX}')
    h.append(f'#define POD_FILES_PAGE {pod_pages.FILES_PAGE_INDEX}')
    h.append(f'#define POD_PULLDOWN_PAGE {pod_pages.PULLDOWN_PAGE_INDEX}')
    h.append(f'#define POD_PEQ_PAGE {pod_pages.PEQ_PAGE_INDEX}')
    h.append(f'#define POD_LOCK_PAGE {pod_pages.LOCK_PAGE_INDEX}')
    h.append(f'#define POD_PEQP_PAGE {pod_pages.PEQP_PAGE_INDEX}')
    h.append(f'#define POD_PEQLIB_PAGE {pod_pages.PEQLIB_PAGE_INDEX}')
    h.append(f'#define POD_TENBAND_PAGE {pod_pages.TENBAND_PAGE_INDEX}')
    h.append(f'#define POD_TENCURVE_PAGE {pod_pages.TENCURVE_PAGE_INDEX}')
    h.append(f'#define POD_TENPREAMP_PAGE {pod_pages.TENPREAMP_PAGE_INDEX}')
    h.append(f'#define POD_PEQBAND_PAGE {pod_pages.PEQBAND_PAGE_INDEX}')
    (out / 'pages.h').write_text('\n'.join(h) + '\n')
    return slots


def gen_asm(out, slots):
    # $gp-restoring trampoline that resumes the stock dispatcher past its 3-word PIC prologue.
    asm = ['.set noreorder', '.text',
           '.globl stock_home_click_trampoline', 'stock_home_click_trampoline:',
           f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{HOME_CLICK + 12:x}', 'nop']
    # the same for home_page_init
    asm += ['.globl stock_home_init_trampoline', 'stock_home_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{HOME_INIT + 12:x}', 'nop']
    # and for the Now Playing page's init
    asm += ['.globl stock_playing_init_trampoline', 'stock_playing_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{PLAYING_INIT + 12:x}', 'nop']
    # and for the timed cover page's init
    asm += ['.globl stock_bigcover_init_trampoline', 'stock_bigcover_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{BIGCOVER_INIT + 12:x}', 'nop']
    # and for the lock screen's init
    asm += ['.globl stock_lockscreen_init_trampoline', 'stock_lockscreen_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{LOCKSCREEN_INIT + 12:x}', 'nop']
    # and for the Now Playing More dialog's init
    asm += ['.globl stock_playmore_init_trampoline', 'stock_playmore_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{PLAYMORE_INIT + 12:x}', 'nop']
    # and for the pull-down's init
    asm += ['.globl stock_pulldown_init_trampoline', 'stock_pulldown_init_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{PULLDOWN_INIT + 12:x}', 'nop']
    # and for mclStartPlayer (Internet Radio's hand-over)
    asm += ['.globl stock_start_player_trampoline', 'stock_start_player_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{START_PLAYER + 12:x}', 'nop']
    # and for save_stop_player / save_start_player (Internet Radio's output changes)
    for nm, at in (('stop', SAVE_STOP), ('start', SAVE_START)):
        asm += [f'.globl stock_save_{nm}_trampoline', f'stock_save_{nm}_trampoline:',
                f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{at + 12:x}', 'nop']
    # and for on_backtoplayer_onclick (Radio Now Playing from stock pages)
    asm += ['.globl stock_backtoplayer_trampoline', 'stock_backtoplayer_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{BACKTOPLAYER + 12:x}', 'nop']
    # and for the two Library query functions
    for nm, at in (('dbquery', QUERY_DB), ('sorted_query', QUERY_SORT), ('setmode', SETMODE), ('loadplaylist', LOADPL), ('file_created', FILETIME)):
        asm += [f'.globl stock_{nm}_trampoline', f'stock_{nm}_trampoline:',
                f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{at + 12:x}', 'nop']
    # and for Light Mode's style_get_color and image_manager_add (style_get_gradient is a leaf the hook reimplements: no trampoline)
    for nm, at in (('style_color', STYLE_COLOR), ('image_add', IMAGE_ADD)):
        asm += [f'.globl stock_{nm}_trampoline', f'stock_{nm}_trampoline:',
                f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{at + 12:x}', 'nop']
    # and for select_timezone (patch/timezones.c)
    asm += ['.globl stock_timezone_trampoline', 'stock_timezone_trampoline:',
            f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{timezones.SELECT + 12:x}', 'nop']
    # the Play Settings Equalizer row (patch/tenband.c): open the editor, then the stock function's epilogue (its frame is untouched: the C call uses the stack below it, $gp is set again)
    asm += ['.globl pod_lock_site', 'pod_lock_site:', 'jal lk_redirect', 'nop', f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', 'bnez $v0, 1f', 'nop',
            'lw $a0, -0x58f8($gp)', f'j 0x{LOCKROW_NAV:x}', 'addiu $a0, $a0, 0x7d24', f'1: j 0x{LOCKROW_DONE:x}', 'nop']   # (the fallback is stock's own two words: a0 = "systemset/screensaver_page", then its navigator_to call)
    asm += ['.globl pod_eq_site', 'pod_eq_site:', 'jal peq_open', 'nop', f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', f'j 0x{EQ_ROW_RESUME:x}', 'nop']
    # Continue with Next Album (patch/nextalbum.c na_end): mclNextSong's List play end branch. Appended: back to the end test (the queue is longer now); not: the two displaced words, then stock's own end.
    asm += ['.globl pod_na_site', 'pod_na_site:', 'jal na_end', 'nop', f'lui $gp, {GP >> 16}', f'ori $gp, $gp, {GP & 0xffff}', 'bnez $v0, 1f', 'nop',
            'lw $v0, -0x7f4c($gp)', 'lw $v1, -0x5428($v0)', f'j 0x{NEXTALBUM_RESUME:x}', 'nop', '1:', f'j 0x{NEXTALBUM_AGAIN:x}', 'nop']
    # libc GOT-slot stubs (load the resolved pointer from demo's own GOT, tail-call it).
    for name, addr in slots.items():
        asm += [f'.section .text.pod_lib_{name},"ax",@progbits', f'.globl pod_lib_{name}', f'pod_lib_{name}:',
                f'lui $t8, {addr >> 16}', f'ori $t8, $t8, {addr & 0xffff}', 'lw $t9, 0($t8)', 'jr $t9', 'nop']
    asm += ['.globl memcpy', '.set memcpy, pod_lib_memcpy', '.globl memset', '.set memset, pod_lib_memset',   # the compiler's own struct copies (patch/peq.c)
            '.globl sqrt', '.set sqrt, pod_lib_sqrt']   # __builtin_sqrt's call for a negative argument (errno), patch/peq.c
    (out / 'pod_asm.S').write_text('\n'.join(asm) + '\n')


def run(*args): subprocess.run([str(a) for a in args], check=True)


def symbols_elf(path):
    out = {}
    text = subprocess.check_output([os.path.join(LLVM, 'llvm-readelf'), '-sW', str(path)], text=True)
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 8 and f[0].endswith(':'):
            try: out[f[7]] = int(f[1], 16)
            except ValueError: pass
    return out


def compile_payload(out, demo_path, tag=TAG):
    out = pathlib.Path(out)
    slots = gen_stock_h(out, demo_path)
    gen_scroll_h(out)
    gen_asm(out, slots)
    objs = [out / (src + '.o') for src in SOURCES]   # (SOURCES order: the link is byte-identical to a serial compile)

    def compile_one(src, obj):
        cmd = [str(a) for a in (CLANG, *FLAGS, f'-DM1PLUS_TAG="{about(tag)}"', f'-DM1PLUS_VERSION="{VERSION}"', f'-DM1PLUS_DEV={int(about(tag) != VERSION)}', f'-DM1PLUS_REPO="{REPO}"', '-I', out, '-I', PATCH, '-c', os.path.join(PATCH, src), '-o', obj)]
        return subprocess.run(cmd, stderr=subprocess.PIPE, text=True)

    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as pool:   # one clang a source; the sources do not depend on each other
        done = list(pool.map(compile_one, SOURCES, objs))
    for r in done:   # the first failing source in SOURCES order, its whole stderr
        if r.stderr: sys.stderr.write(r.stderr)
        if r.returncode: raise subprocess.CalledProcessError(r.returncode, r.args)
    run(CLANG, *FLAGS, '-c', out / 'pod_asm.S', '-o', out / 'pod_asm.o')
    # compact_set_row_layout is reached only from the patched stock call sites, so keep it
    keep = ['--undefined=compact_set_row_layout', '--undefined=m1plus_home_init',
            '--undefined=stock_home_init_trampoline', '--undefined=m1plus_playing_init',
            '--undefined=stock_playing_init_trampoline', '--undefined=m1plus_bigcover_init', '--undefined=stock_bigcover_init_trampoline', '--undefined=m1plus_lockscreen_init', '--undefined=stock_lockscreen_init_trampoline', '--undefined=m1plus_scroll_event',
            '--undefined=m1plus_playmore_init', '--undefined=stock_playmore_init_trampoline', '--undefined=m1plus_pulldown_init', '--undefined=pd_open_settings', '--undefined=stock_pulldown_init_trampoline', '--undefined=rd_start_player', '--undefined=rd_step', '--undefined=stock_start_player_trampoline', '--undefined=rd_save_stop', '--undefined=rd_save_start', '--undefined=stock_save_stop_trampoline', '--undefined=stock_save_start_trampoline', '--undefined=rn_backtoplayer', '--undefined=stock_backtoplayer_trampoline', '--undefined=pc_id3_path', '--undefined=pc_library_query', '--undefined=pc_sorted_query', '--undefined=stock_dbquery_trampoline', '--undefined=stock_sorted_query_trampoline',
            '--undefined=sba_parse_tracks', '--undefined=sba_parse_albums', '--undefined=sba_parse_artists', '--undefined=sba_parse_playlists', '--undefined=sba_parse_ping',   # (sbparse.c until sbapi.c calls them)
            '--undefined=m1plus_style_color', '--undefined=m1plus_style_gradient', '--undefined=m1plus_image_add', '--undefined=stock_style_color_trampoline', '--undefined=stock_image_add_trampoline', '--undefined=pal_map', '--undefined=pal_active', '--undefined=pal_background', '--undefined=pal_accent', '--undefined=pal_accent_saved', '--undefined=pal_accent_set', '--undefined=pal_accent_color', '--undefined=pal_fill',
            '--undefined=bc_timed_open', '--undefined=m1_scan_dir', '--undefined=sh_set_mode', '--undefined=sbs_play_record', '--undefined=sh_load_playlist', '--undefined=sh_display_mode', '--undefined=sh_clear_queue', '--undefined=pod_na_site', '--undefined=na_next_key', '--undefined=na_set_cur', '--undefined=na_cur', '--undefined=na_active', '--undefined=stock_setmode_trampoline', '--undefined=stock_loadplaylist_trampoline', '--undefined=ft_created', '--undefined=stock_file_created_trampoline', '--undefined=tz_select', '--undefined=tz_row', '--undefined=tz_label', '--undefined=stock_timezone_trampoline', '--undefined=bp_capacity', '--undefined=lo_set_text', '--undefined=wifi_hub_open', '--undefined=tidal_kb_focus', '--undefined=pod_eq_site', '--undefined=pod_lock_site', '--undefined=pf_items', '--undefined=pf_seen', '--undefined=so_play_src', '--undefined=lib_navidrome', '--undefined=sba_songs_window', '--undefined=sbs_playing', '--undefined=sbs_track']   # (pf_items, pf_seen: accessors of the parser the tests read; so_play_src, albums_open_src: the library seam, no caller yet)
    keep += ['--undefined=' + n for n in ND_KEEP]   # (the Navidrome data layer has no caller until the pages land: patch/sbapi.h; the tests call these)
    run(LD, '-m', 'elf32ltsmip', '--gc-sections', '-T', os.path.join(PATCH, 'link.ld'),
        '-e', 'm1plus_home_click', '--undefined=m1plus_home_click', '--undefined=stock_home_click_trampoline',
        # Navidrome downloads (patch/sbdl.c): kept until the pages that call them land (ND-10); the tests run them
        *[f'--undefined={n}' for n in ('sba_dl_add', 'sba_dl_cancel', 'sba_dl_cancel_all', 'sba_dl_state', 'sba_dl_gen', 'sba_dl_busy', 'sba_dl_path', 'sba_dl_delete', 'sba_downloaded')],
        *keep, *objs, out / 'pod_asm.o', '-o', out / 'patch.elf')
    run(OBJCOPY, '-O', 'binary', out / 'patch.elf', out / 'patch.bin')
    ps = symbols_elf(out / 'patch.elf')
    payload = (out / 'patch.bin').read_bytes()
    # The payload is position-fixed and its segment is file-backed from end to end: writable state
    # lives in .scratch, which the compiler emits as zero-filled PROGBITS (so it is in patch.bin and
    # memsz == filesz); a non-empty .bss would need memory past the file image, so it is refused.
    scratch = 0
    with open(out / 'patch.elf', 'rb') as f:
        for sec in ELFFile(f).iter_sections():
            if sec.name in ('.bss', '.sbss') and sec['sh_size']:
                raise ValueError(f'payload has non-empty {sec.name}; put writable state in .scratch')
            if sec.name == '.scratch':
                scratch = sec['sh_size']
                check(sec['sh_type'] == 'SHT_PROGBITS', '.scratch must be file-backed (PROGBITS)')
                off = sec['sh_addr'] - BASE
                check(0 <= off and off + scratch <= len(payload), '.scratch outside the payload')
                check(not any(payload[off:off + scratch]), '.scratch must start zeroed')
    return ps, payload, scratch


def append_payload(image, payload, base):
    """Rewrite demo's final PT_NULL header into a file-backed PT_LOAD (RWX) mapping payload at base."""
    segs = segments(image)
    nulls = [(o, p) for o, p in segs if p[0] == 0]
    check(len(nulls) == 1 and nulls[0][0] == segs[-1][0], 'no final PT_NULL slot')
    check(all(p[2] + p[5] <= base for _, p in segs if p[0] == 1), 'payload mapping overlaps a LOAD segment')
    off = (len(image) + 0xffff) & ~0xffff
    image.extend(bytes(off - len(image)))
    image.extend(payload)
    struct.pack_into('<8I', image, nulls[0][0], 1, off, base, base, len(payload), len(payload), 7, 0x10000)
    return off


# The library rows (patch/rows.c): pinned call-site and immediate
# edits of the stock row constructors, listed in patch/rows.json. Not hooks: no prologue changes;
# the one hook stays HOME_CLICK.
ROWS_JSON = os.path.join(PATCH, 'rows.json')
JALR_T9 = 0x0320f809
ROW_LAYOUT_STRINGS = {0x745158: b'default(r=1,c=0,x=12,s=8)\0', 0x745360: b'default(r=1,c=0,x=0,s=8)\0'}
DEFAULT_LAYOUT_VTABLE, DEFAULT_LAYOUT_FN = 0x904924, 0x63a444   # patch/offsets.inc (patch/rows.c copies it)


def jal(addr, at):
    check((addr & 0xf0000000) == ((at + 4) & 0xf0000000) and addr % 4 == 0, f'{at:#x}: jal target out of range')
    return 0x0c000000 | ((addr >> 2) & 0x03ffffff)


def patch_rows(image, ps):
    """Apply patch/rows.json to image (bytearray) in place; every word checked first. Returns the
    list of changes [address, old, new, kind]."""
    J = json.load(open(ROWS_JSON))
    target = ps.get('compact_set_row_layout')
    check(target is not None, 'payload has no compact_set_row_layout')
    edits, seen = [], set()
    def at(a, old):
        check(a not in seen, f'{a:#x}: listed twice'); seen.add(a)
        got = struct.unpack_from('<I', image, fileoff(image, a))[0]
        check(got == old, f'{a:#x}: {got:#010x} != pinned {old:#010x}')
    for g in J['immediates']:
        v = g['value']; check(0 <= v < 0x8000, f'bad immediate {v}')
        for a, old, *_ in g['sites']:
            a, old = int(a, 16), int(old, 16)
            if old & 0xffff07ff in (0x21, 0x25):   # move rd, $zero (addu / or rd, $zero, $zero) -> addiu rd, $zero, imm
                new = 0x24000000 | ((old >> 11) & 31) << 16 | v
            else:
                check(old >> 26 == 9 and (old >> 21) & 31 == 0, f'{a:#x}: not addiu rt, $zero, imm nor move rd, $zero')
                new = (old & 0xffff0000) | v
            at(a, old); edits.append((a, old, new, 'immediate'))
    for a, old, *_ in J['row_layout_calls']['sites']:
        a, old = int(a, 16), int(old, 16)
        check(old == JALR_T9, f'{a:#x}: not jalr $t9'); at(a, old)
        edits.append((a, old, jal(target, a), 'call'))
    for a, old, *_ in J['nops']['sites']:
        a, old = int(a, 16), int(old, 16)
        check(old == JALR_T9, f'{a:#x}: not jalr $t9'); at(a, old)
        edits.append((a, old, 0, 'nop'))
    icon = ps.get('rows_track_icon')
    check(icon is not None, 'payload has no rows_track_icon')
    for a, old, *_ in J['icon_calls']['sites']:
        a, old = int(a, 16), int(old, 16)
        check(old == JALR_T9, f'{a:#x}: not jalr $t9'); at(a, old)
        edits.append((a, old, jal(icon, a), 'icon'))
    for g in J['pinned']:
        for a, old, *_ in g['sites']:
            at(int(a, 16), int(old, 16))
    for a, text in ROW_LAYOUT_STRINGS.items():   # the shared layout strings stay as they are
        off = fileoff(image, a); check(bytes(image[off:off + len(text)]) == text, f'{a:#x}: layout string changed')
    off = fileoff(image, DEFAULT_LAYOUT_VTABLE + 8)
    check(struct.unpack_from('<I', image, off)[0] == DEFAULT_LAYOUT_FN, 'default layouter vtable slot 2 moved')
    for a, old, new, _ in edits:
        struct.pack_into('<I', image, fileoff(image, a), new)
    return [[hex(a), hex(old), hex(new), kind] for a, old, new, kind in edits]


def hook(patched, addr, prologue_pinned, target, what):
    """Overwrite the 3-word PIC prologue at addr with `j target; nop`, after checking it and the
    $gp it computes."""
    off = fileoff(patched, addr)
    prologue = struct.unpack_from('<III', patched, off)
    check(prologue == prologue_pinned, f'{what} prologue mismatch: {[hex(x) for x in prologue]}')
    low = prologue_pinned[1] & 0xffff
    gp = ((prologue_pinned[0] & 0xffff) << 16) + (low if low < 0x8000 else low - 0x10000) + addr
    check(gp == GP, f'{what} GOT base {gp:#x} != {GP:#x}')
    struct.pack_into('<II', patched, off, j(target), 0)


def patch_scroll(image, ps, payload_len, demo_path):
    """List gestures: check every pinned word and the vtable symbol, then write m1plus_scroll_event into the (empty)
    on_event_before_children slot of g_scroll_view_vtable. Returns [slot address, old, new]."""
    target = ps['m1plus_scroll_event']
    check(BASE <= target < BASE + payload_len, 'scroll entry symbol outside payload')
    check(dynsym(demo_path).get('g_scroll_view_vtable') == SCROLL_VTABLE, 'g_scroll_view_vtable moved')
    check_pins(image, SCROLL_PINS)
    struct.pack_into('<I', image, fileoff(image, SCROLL_SLOT), target)
    return [hex(SCROLL_SLOT), '0x0', hex(target)]


def patch_timezones(image, ps, payload_len):
    """Time zones (docs/modules/timezones.md): check every pinned word, then the select_timezone hook, the saved-index clamp, the row count and limit, and the picker's two call sites."""
    for name in ('tz_select', 'tz_row', 'tz_label'):
        check(BASE <= ps[name] < BASE + payload_len, f'{name} outside payload')
    check(timezones.COUNT < 0x8000 - 3 and timezones.COUNT == len(timezones.ORDER) and sorted(timezones.ORDER) == list(range(timezones.COUNT)), 'bad zone table')
    check(all(len(label) <= timezones.MAX_LABEL for label, _ in timezones.TIMEZONES), 'zone label too long')
    edits = timezones.edits(jal(ps['tz_row'], timezones.ROW_CALL), jal(ps['tz_label'], timezones.LABEL_CALL))
    check_pins(image, timezones.PINS + tuple((a, old, what) for a, old, _, what in edits))
    hook(image, timezones.SELECT, timezones.SELECT_PROLOGUE, ps['tz_select'], 'select_timezone')
    for a, _, new, _ in edits:
        struct.pack_into('<I', image, fileoff(image, a), new)


def patch_demo(raw, payload, ps, demo_path):
    patched = bytearray(raw)
    target, target2 = ps['m1plus_home_click'], ps['m1plus_home_init']
    check(BASE <= target < BASE + len(payload), 'entry symbol outside payload')
    check(BASE <= target2 < BASE + len(payload), 'home init entry symbol outside payload')
    hook(patched, HOME_CLICK, HOME_CLICK_PROLOGUE, target, 'home click')
    hook(patched, HOME_INIT, HOME_INIT_PROLOGUE, target2, 'home_page_init')
    target4 = ps['m1plus_playing_init']
    check(BASE <= target4 < BASE + len(payload), 'playing init entry symbol outside payload')
    hook(patched, PLAYING_INIT, PLAYING_INIT_PROLOGUE, target4, 'playing_page_init')
    target5 = ps['m1plus_bigcover_init']
    check(BASE <= target5 < BASE + len(payload), 'bigcover init entry symbol outside payload')
    check_pins(patched, VOLKEYS_PINS)   # no hook: the volume keys are taken on our own page; the premises must still hold
    check_pins(patched, BIGCOVER_PINS)
    hook(patched, BIGCOVER_INIT, BIGCOVER_INIT_PROLOGUE, target5, 'bigcover_page_init')
    target6 = ps['m1plus_lockscreen_init']
    check(BASE <= target6 < BASE + len(payload), 'lockscreen init entry symbol outside payload')
    check_pins(patched, LOCKSCREEN_PINS)
    hook(patched, LOCKSCREEN_INIT, LOCKSCREEN_INIT_PROLOGUE, target6, 'screensaver_page_init')
    check(BASE <= ps['bc_timed_open'] < BASE + len(payload), 'idle view hook symbol outside payload')
    check_pins(patched, IDLE_PINS)
    struct.pack_into('<I', patched, fileoff(patched, IDLE_SITE), jal(ps['bc_timed_open'], IDLE_SITE))   # (the pins above checked the site's word, its delay slot, the GOT load and the callback round it)
    patch_playmore(patched, ps, len(payload))
    patch_timezones(patched, ps, len(payload))
    patch_pulldown(patched, ps, len(payload))
    check_pins(patched, RADIO_PINS)
    patch_radio(patched, ps, len(payload))
    check_pins(patched, LOCKROW_PINS + KEYSPOWER_PINS + PLAYLIST_PINS + SONGS_PINS + IPOD_PINS + PODCAST_PINS + SETTINGS_PINS + TIDALKB_PINS + PINYIN_PINS + JPEG_PINS + COVER_PINS + TAPE_PINS + LYRICS_PINS + SCAN_PINS + QUERY_PINS + FONT_PINS + TEXTGAMMA_PINS + BATTERY_PINS + PLAYREC_PINS + LINEOUT_PINS + SHUFFLE_PINS + NEXTALBUM_PINS + FILETIME_PINS + PICKER_PINS + FOLDER_PINS + UPDATE_PINS + TFUPDATE_PINS + LIGHT_PINS + EQ_PINS)   # stock code the Playlists and Songs pages call: checked, not written
    for at, text in ((0x74bad8, ALBUM_SQL.replace('songtable', '%s')), (0x74ba4c, 'songtable')):   # the strings getAllAlbum fills: the payload's STOCK_ALBUM_SQL is their sprintf
        want = text.encode() + b'\0'
        check(bytes(patched[fileoff(patched, at):fileoff(patched, at) + len(want)]) == want, f'{at:#x}: not the string "{text}" the album cover map reproduces')
    target5 = ps['pc_id3_path']
    check(BASE <= target5 < BASE + len(payload), 'tag reader hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, ID3_SITE), jal(target5, ID3_SITE))   # (the pins above checked the site's word and its neighbours)
    hook(patched, QUERY_DB, QUERY_DB_PROLOGUE, ps['pc_library_query'], 'toolsQueryDbTable')
    hook(patched, QUERY_SORT, QUERY_SORT_PROLOGUE, ps['pc_sorted_query'], 'toolsQueryDbTableAndSort')
    check(all(BASE <= ps[n] < BASE + len(payload) for n in ('pc_library_query', 'pc_sorted_query')), 'query hook symbol outside payload')
    target6 = ps['m1_scan_dir']
    check(BASE <= target6 < BASE + len(payload), 'scan hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, SCAN_SITE), jal(target6, SCAN_SITE))
    target8 = ps['bp_capacity']
    check(BASE <= ps['wifi_hub_open'] < BASE + len(payload), 'Wi-Fi hub hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, WIFIHUB_SITE), jal(ps['wifi_hub_open'], WIFIHUB_SITE))   # (SETTINGS_PINS checked the site's word, its delay slot and the thunk around it)
    check(BASE <= ps['tidal_kb_focus'] < BASE + len(payload), 'Tidal keyboard hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, TIDALKB_SITE), jal(ps['tidal_kb_focus'], TIDALKB_SITE))   # (TIDALKB_PINS checked the site's word, its delay slot and the bind callback around it)
    check(BASE <= ps['sbs_play_record'] < BASE + len(payload), 'play history hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, PLAYREC_SITE), jal(ps['sbs_play_record'], PLAYREC_SITE))   # (PLAYREC_PINS checked the site's word, its delay slot and its neighbours)
    check(BASE <= ps['lo_set_text'] < BASE + len(payload), 'Line Out hook symbol outside payload')
    for a, _ in LINEOUT_SITES: struct.pack_into('<I', patched, fileoff(patched, a), jal(ps['lo_set_text'], a))   # (the pins checked each site's lw t9 GOT widget_set_text_utf8, a1, the jalr and the delay slot)
    check(BASE <= target8 < BASE + len(payload), 'battery hook symbol outside payload')
    struct.pack_into('<I', patched, fileoff(patched, BATTERY_SITE), jal(target8, BATTERY_SITE))   # (the pins above checked the site's word, its delay slot and its neighbours)
    for nm, at, pro in (('sh_set_mode', SETMODE, SETMODE_PROLOGUE), ('sh_load_playlist', LOADPL, LOADPL_PROLOGUE), ('ft_created', FILETIME, FILETIME_PROLOGUE)):   # Apple-style Shuffle (patch/shuffle.c)
        check(BASE <= ps[nm] < BASE + len(payload), f'{nm} outside payload')
        hook(patched, at, pro, ps[nm], nm)
    check(BASE <= ps['sh_display_mode'] < BASE + len(payload), 'sh_display_mode outside payload')
    check(BASE <= ps['sh_clear_queue'] < BASE + len(payload), 'sh_clear_queue outside payload')
    struct.pack_into('<I', patched, fileoff(patched, CLEAR_SITE), jal(ps['sh_clear_queue'], CLEAR_SITE))   # the delay slot (a0 = *queue) stays stock's
    check(BASE <= ps['pod_eq_site'] < BASE + len(payload), 'pod_eq_site outside payload')
    check(BASE <= ps['pod_lock_site'] < BASE + len(payload), 'pod_lock_site outside payload')
    struct.pack_into('<II', patched, fileoff(patched, LOCKROW), j(ps['pod_lock_site']), 0)   # (the pins above checked the case's three words and the epilogue it resumes at)
    struct.pack_into('<II', patched, fileoff(patched, EQ_ROW), j(ps['pod_eq_site']), 0)   # (the pins above checked the row's three words and the epilogue it resumes at)
    check(BASE <= ps['pod_na_site'] < BASE + len(payload) and BASE <= ps['na_end'] < BASE + len(payload), 'pod_na_site outside payload')
    check(tuple(struct.unpack_from('<II', patched, fileoff(patched, NEXTALBUM_SITE))) == NEXTALBUM_DISPLACED, 'mclNextSong end branch: the two displaced words changed')
    struct.pack_into('<II', patched, fileoff(patched, NEXTALBUM_SITE), j(ps['pod_na_site']), 0)   # (NEXTALBUM_PINS checked the site's words, the end test it returns to and the words it resumes at)
    for a, _ in MODE_SITES:   # the pins above checked each site's jalr and the lw t9 of mclGetPlayMode before it
        struct.pack_into('<I', patched, fileoff(patched, a), jal(ps['sh_display_mode'], a))
    struct.pack_into('<I', patched, fileoff(patched, UPDATE_SITE), UPDATE_NEW)   # (the pins above checked the site's word and its neighbours)
    autotime.apply(patched, fileoff)   # two pinned string literals: hwclock -su / -wu, the RTC as UTC (docs/modules/autotime.md)
    coex.apply(patched, fileoff)   # Wi-Fi and Bluetooth together: four pinned beqz -> b (docs/modules/overlays.md)
    themeoff.apply(patched, fileoff)   # stock theme1 off: the config_init clamp and the System page's row table and count (docs/modules/theme.md)
    # Light Mode (the pins above checked the words after each prologue, the gradient call and image_manager_add's callers): the two PIC prologue hooks and the gradient leaf
    check(all(BASE <= ps[n] < BASE + len(payload) for n in ('m1plus_style_color', 'm1plus_style_gradient', 'm1plus_image_add')), 'Light Mode hook symbol outside payload')
    hook(patched, STYLE_COLOR, STYLE_COLOR_PROLOGUE, ps['m1plus_style_color'], 'style_get_color')
    hook(patched, IMAGE_ADD, IMAGE_ADD_PROLOGUE, ps['m1plus_image_add'], 'image_manager_add')
    check(dynsym(demo_path).get('style_get_gradient') == STYLE_GRADIENT and dynsym(demo_path).get('style_get_color') == STYLE_COLOR and dynsym(demo_path).get('image_manager_add') == IMAGE_ADD,
          'Light Mode: a hooked symbol moved')
    off = fileoff(patched, STYLE_GRADIENT)
    check(struct.unpack_from('<III', patched, off) == STYLE_GRADIENT_WORDS, 'style_get_gradient: unexpected leaf')
    struct.pack_into('<II', patched, off, j(ps['m1plus_style_gradient']), 0)
    check(STYLE_COLOR_RET == 0x65a048 + 8 and struct.unpack_from('<I', patched, fileoff(patched, 0x65a048))[0] == 0x0411ffd4,
          'style_get_color: unexpected gradient call')   # (bal at 0x65a048 with its delay slot: it returns to 0x65a050 and still reaches the leaf's first word: the hook's jump)
    check(dynsym(demo_path).get('playsong_id3info') == 0xa0d88c, 'playsong_id3info moved')
    edits = patch_rows(patched, ps)
    # no row edit may touch a PIC prologue (the hooks are the only ones) or a hook site
    check(all(not any(h <= int(a, 16) < h + 12 for h in (HOME_CLICK, HOME_INIT, PLAYING_INIT, BIGCOVER_INIT, LOCKSCREEN_INIT, PLAYMORE_INIT, PULLDOWN_INIT, START_PLAYER, SAVE_STOP, SAVE_START, BACKTOPLAYER, QUERY_DB, QUERY_SORT, STYLE_COLOR, IMAGE_ADD, SETMODE, LOADPL, FILETIME, timezones.SELECT)) and not STYLE_GRADIENT <= int(a, 16) < STYLE_GRADIENT + 8 and not any(int(a, 16) == s for s, _ in MODE_SITES) and int(a, 16) != CLEAR_SITE and not ID3_SITE <= int(a, 16) < ID3_SITE + 4 and not SCAN_SITE <= int(a, 16) < SCAN_SITE + 4 and not BATTERY_SITE <= int(a, 16) < BATTERY_SITE + 4 and not any(int(a, 16) == s for s, _ in LINEOUT_SITES) and int(a, 16) != WIFIHUB_SITE and int(a, 16) != IDLE_SITE and int(a, 16) != TIDALKB_SITE and int(a, 16) not in PULLDOWN_OPEN_SITES and not EQ_ROW <= int(a, 16) < EQ_ROW + 8 and not NEXTALBUM_SITE <= int(a, 16) < NEXTALBUM_SITE + 8
              for a, *_ in edits), 'row edit on a hook')
    check(all(not (SCROLL_SLOT <= int(a, 16) < SCROLL_SLOT + 4 or a in {hex(p[0]) for p in SCROLL_PINS}) for a, *_ in edits),
          'row edit on a list gesture word')
    scroll = patch_scroll(patched, ps, len(payload), demo_path)
    seg_off = append_payload(patched, payload, BASE)
    return bytes(patched), seg_off, edits, scroll


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir')
    ap.add_argument('--tag', default=TAG)
    a = ap.parse_args()
    rootfs = os.path.join(a.workdir, 'rootfs')
    demo_path = os.path.join(rootfs, DEMO)
    raw = open(demo_path, 'rb').read()
    check(sha(raw) == ZEROED_DEMO_SHA, f'demo is not the .pdr-zeroed stock V2.1 binary (got {sha(raw)})')
    build = pathlib.Path(a.workdir) / 'podbuild'; build.mkdir(exist_ok=True)
    check(re.fullmatch(r'V2\.1(z[A-Z]+|-\d+\.\d+\.\d+)', a.tag) is not None and len(a.tag) <= 31, 'invalid build tag')
    ps, payload, scratch = compile_payload(build, demo_path, a.tag)
    patched, seg_off, edits, scroll = patch_demo(raw, payload, ps, demo_path)
    # keep demo's permission bits
    mode = stat.S_IMODE(os.stat(demo_path).st_mode)
    os.chmod(demo_path, mode | 0o200); open(demo_path, 'wb').write(patched); os.chmod(demo_path, mode)
    assets = pod_ui.write_assets(rootfs, pod_pages.PAGES)
    pod_ui.add_shot_indicator(rootfs)     # the hidden camera in ui/system_bar.bin (patch/shot.c)
    pod_ui.add_battery_label(rootfs)      # the hidden percentage in ui/system_bar.bin and both pull-downs (patch/battery.c)
    pod_ui.add_tidal_keyboard(rootfs)     # the keyboard's field and pad in ui/tidal/tidal_serach_page.bin (patch/tidalkb.c)
    manifest = {
        'base': BASE, 'gp': GP, 'payload_len': len(payload),
        'payload_sha256': sha(payload), 'scratch_bytes': scratch, 'entry_symbol': ps['m1plus_home_click'],
        'segment_file_off': seg_off, 'hook': {'addr': HOME_CLICK, 'target': ps['m1plus_home_click']},
        'hook_init': {'addr': HOME_INIT, 'target': ps['m1plus_home_init']},
        'hook_playing': {'addr': PLAYING_INIT, 'target': ps['m1plus_playing_init']},
        'hook_bigcover': {'addr': BIGCOVER_INIT, 'target': ps['m1plus_bigcover_init']},
        'hook_lockscreen': {'addr': LOCKSCREEN_INIT, 'target': ps['m1plus_lockscreen_init']},
        'hook_playmore': {'addr': PLAYMORE_INIT, 'target': ps['m1plus_playmore_init']},
        'hook_pulldown': {'addr': PULLDOWN_INIT, 'target': ps['m1plus_pulldown_init']},
        'hook_pulldown_open': {'sites': [hex(a) for a in PULLDOWN_OPEN_SITES], 'target': ps['pd_open_settings']},
        'hook_start_player': {'addr': START_PLAYER, 'target': ps['rd_start_player']},
        'hook_save_stop': {'addr': SAVE_STOP, 'target': ps['rd_save_stop']}, 'hook_save_start': {'addr': SAVE_START, 'target': ps['rd_save_start']},
        'hook_backtoplayer': {'addr': BACKTOPLAYER, 'target': ps['rn_backtoplayer']},
        'hook_id3': {'addr': ID3_SITE, 'target': ps['pc_id3_path']},
        'hook_query': {'addr': QUERY_DB, 'target': ps['pc_library_query']}, 'hook_sorted_query': {'addr': QUERY_SORT, 'target': ps['pc_sorted_query']},
        'hook_scan': {'addr': SCAN_SITE, 'target': ps['m1_scan_dir']},
        'hook_battery': {'addr': BATTERY_SITE, 'target': ps['bp_capacity']},
        'hook_wifihub': {'addr': WIFIHUB_SITE, 'target': ps['wifi_hub_open']},
        'hook_idle': {'addr': IDLE_SITE, 'target': ps['bc_timed_open']},
        'hook_tidalkb': {'addr': TIDALKB_SITE, 'target': ps['tidal_kb_focus']},
        'hook_playrecord': {'addr': PLAYREC_SITE, 'target': ps['sbs_play_record']},
        'hook_lineout': {'sites': [hex(a) for a, _ in LINEOUT_SITES], 'target': ps['lo_set_text']},
        'hook_timezone': {'addr': timezones.SELECT, 'target': ps['tz_select']}, 'timezone_row': {'addr': timezones.ROW_CALL, 'target': ps['tz_row']}, 'timezone_label': {'addr': timezones.LABEL_CALL, 'target': ps['tz_label']},
        'hook_style_color': {'addr': STYLE_COLOR, 'target': ps['m1plus_style_color']}, 'hook_style_gradient': {'addr': STYLE_GRADIENT, 'target': ps['m1plus_style_gradient']},
        'hook_image_add': {'addr': IMAGE_ADD, 'target': ps['m1plus_image_add']},
        'hook_setmode': {'addr': SETMODE, 'target': ps['sh_set_mode']}, 'hook_loadplaylist': {'addr': LOADPL, 'target': ps['sh_load_playlist']}, 'hook_file_created': {'addr': FILETIME, 'target': ps['ft_created']},
        'hook_clear_queue': {'addr': CLEAR_SITE, 'target': ps['sh_clear_queue']}, 'hook_eq_row': {'addr': EQ_ROW, 'target': ps['pod_eq_site']}, 'hook_next_album': {'addr': NEXTALBUM_SITE, 'target': ps['pod_na_site']}, 'hook_lock_row': {'addr': LOCKROW, 'target': ps['pod_lock_site']},
        'hook_display_mode': {'sites': [hex(a) for a, _ in MODE_SITES], 'target': ps['sh_display_mode']},
        'scroll_slot': {'addr': SCROLL_SLOT, 'target': ps['m1plus_scroll_event']}, 'scroll_edit': scroll,
        'zeroed_demo_sha256': ZEROED_DEMO_SHA, 'patched_demo_sha256': sha(patched),
        'assets': assets, 'entry_home_id': pod_pages.HOME_ENTRY,
        'row_edits': edits, 'row_fit': ps['compact_set_row_layout'],
    }
    (build / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'payload {len(payload)} bytes ({scratch} .scratch) @ {BASE:#x} (entry {ps["m1plus_home_click"]:#x}), '
          f'hook @ {HOME_CLICK:#x}, boot guard hook @ {HOME_INIT:#x} (home_page_init), '
          f'Now Playing init hook @ {PLAYING_INIT:#x}, '
          f'scroll_view before-children slot @ {SCROLL_SLOT:#x} -> {ps["m1plus_scroll_event"]:#x}')
    kinds = {k: sum(e[3] == k for e in edits) for k in ('immediate', 'call', 'nop')}
    print(f'  rows: {len(edits)} pinned edits ({kinds["immediate"]} immediates, {kinds["call"]} row-layout '
          f'calls -> compact_set_row_layout @ {ps["compact_set_row_layout"]:#x}, {kinds["nop"]} rebind resizes nopped)')
    for rel, n in assets: print(f'  asset {rel} ({n} bytes)')


if __name__ == '__main__': main()
