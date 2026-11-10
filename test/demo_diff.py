#!/usr/bin/env python3
"""Check that a built demo differs from the stock demo only where the mods say.

usage: python3 -I test/demo_diff.py <stock demo> <built demo>

Allowed differences: the zeroed .pdr section (space step), the program headers (the payload PT_LOAD),
the 8-byte Home-icon hook at 0x533b80, the 8-byte boot guard hook at home_page_init 0x534cd4, the 8-byte
Now Playing hook at playing_page_init
0x53d1e4, the 8-byte timed cover page hook at bigcover_page_init 0x529a24, the one word of the timed open's navigator_to call at 0x53d0ec (the idle view), the 8-byte lock screen hook at screensaver_page_init 0x53fd44, the 8-byte More dialog hook at dialog_playmore_dialog_init 0x479cc4, the 8-byte pull-down hook at dialog_dropdown_dialog_init 0x475f04, the pinned literals of tools/autotime.py (hwclock -su/-wu), the one word at get_id3info 0x4dff4c (the tag reader's strcpy call, now a jal into the payload), the one data word g_scroll_view_vtable + 0x98 (0x97a330, patch/scroll.c), the words listed in patch/rows.json, the four cover-size immediates of the lock screen (each must be
stock | 264), the five A-B marker immediates of Now Playing (tools/mod_nowplaying.py marker_edits) and bytes
the four pinned branch words of tools/coex.py (Wi-Fi and Bluetooth together), the pinned words of tools/themeoff.py (theme1 off), appended after the stock file. Anything else is an error. Exit status 0 = clean.
"""
import json, os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, 'tools'))
import mod_nowplaying as mn
import autotime, coex, themeoff, timezones
import pod   # the Shuffle hooks and display sites (tools/pod.py SETMODE, LOADPL, MODE_SITES)
HOOK = (0x533b80, 8)
HOME_INIT = (0x534cd4, 8)   # home_page_init: the boot guard's hook (docs/architecture.md)
PLAYING = (0x53d1e4, 8)     # playing_page_init: the Now Playing hook (patch/nowplaying.c)
BIGCOVER = (0x529a24, 8)    # bigcover_page_init: the timed cover page hook (patch/bigcover.c)
LOCKSCREEN = (0x53fd44, 8)  # screensaver_page_init: the lock screen's mini player layout hook (patch/lockscreen.c)
PLAYMORE = (0x479cc4, 8)    # dialog_playmore_dialog_init: the More menu hook (patch/playmore.c)
PULLDOWN = (0x475f04, 8)    # dialog_dropdown_dialog_init: the pull-down tile hook (patch/pulldown.c)
BACKTOPLAYER = (0x4cd58c, 8)   # on_backtoplayer_onclick: Radio Now Playing from stock pages (patch/radionp.c rn_backtoplayer)
START_PLAYER = (0x5d5300, 8)   # mclStartPlayer: the hand-over hook (patch/radio.c rd_start_player, docs/modules/radio.md)
SAVE_STOP = (0x4e2304, 8)   # save_stop_player: the output-change hooks (patch/radio.c rd_save_stop / rd_save_start, docs/modules/radio.md "Output changes")
SAVE_START = (0x4e23e8, 8)
ID3_SITE = (0x4dff4c, 4)    # get_id3info: the jalr strcpy of the parsed path, now jal pc_id3_path (patch/pcmodel.c, docs/modules/podcasts.md "Tags")
QUERY = (0x5ee77c, 0x5ee9ac)   # toolsQueryDbTable, toolsQueryDbTableAndSort: the PIC prologue's first two words, now `j` into the payload and a nop (patch/pcmodel.c, docs/modules/payload.md hook 6)
SCAN_SITE = (0x5ea6a8, 4)  # the library scan's folder test: the jalr strcmp(name, "."), now jal pod_scan_dir (patch/common.c, docs/modules/payload.md hook 5)
UPDATE_SITE = (0x4e1124, 4)  # update_firmware: the compare's operand addiu a1 (the literal "V2.1" 0x74773c -> the string "about_version" 0x74772c; docs/modules/version.md)
IDLE_SITE = (pod.IDLE_SITE, 4)  # the timed open's jalr navigator_to, now jal bc_timed_open (patch/bigcover.c, docs/modules/payload.md hook 24)
TIDALKB_SITE = (pod.TIDALKB_SITE, 4)  # the stock Tidal search page's edit_set_focus call, now jal tidal_kb_focus (patch/tidalkb.c, docs/modules/payload.md hook 27)
WIFIHUB_SITE = (pod.WIFIHUB_SITE, 4)  # the Wi-Fi row of the All System Settings hub: the jalr navigator_to, now jal wifi_hub_open (patch/wifipage.c, docs/modules/payload.md hook 21)
PULLDOWN_OPEN = tuple(pod.PULLDOWN_OPEN_SITES)  # on_wm_tsmove_fun: the two `bal navigator_to` that open the page a pull-down tile chose, now jal pd_open_settings (patch/pulldown.c, docs/modules/payload.md hook 22)
BATTERY_SITE = (0x5450f8, 4)  # show_sysbar_face: the jalr get_battery_capacity, now jal bp_capacity (patch/battery.c, docs/modules/payload.md hook 8)
LINEOUT_SITES = tuple(a for a, _ in pod.LINEOUT_SITES)   # show_sysbar_face and dropdown_showface: the jalr widget_set_text_utf8 of label_volume, now jal lo_set_text (patch/lineout.c, docs/modules/payload.md hook 16)
LIGHT = (0x659fcc, 0x655638, 0x659f9c)   # Light Mode's hooks (patch/palette.c, docs/modules/payload.md hooks 10 - 12): style_get_color and image_manager_add (PIC prologues: `j` and a nop) and the style_get_gradient leaf (the same two words)
SHUFFLE_HOOKS = (pod.SETMODE, pod.LOADPL, pod.FILETIME)   # (FILETIME: toolsGetFileCreateTime, patch/filetime.c, hook 19) mclSetPlayMode, mclLoadPlayList: the PIC prologue's first two words, now `j` into the payload and a nop (patch/shuffle.c, docs/modules/payload.md hooks 13, 14)
MODE_SITES = tuple(a for a, _ in pod.MODE_SITES)   # the 19 `jalr mclGetPlayMode` call sites, now `jal sh_display_mode`
SCROLL_SLOT =(0x97a330, 4) # g_scroll_view_vtable.on_event_before_children: 0 in stock, the payload's m1plus_scroll_event (patch/scroll.c)
COVER = 264                 # the cover size demo writes (tools/mod_lockscreen.py, Now Playing's art)
COVER_IMM = (0x4df1dc, 0x4df1e0, 0x4df21c, 0x4df220)

def segs(b):
    phoff = struct.unpack_from('<I', b, 28)[0]; size, num = struct.unpack_from('<HH', b, 42)
    return phoff, size, num, [struct.unpack_from('<8I', b, phoff + i * size) for i in range(num)]

def va_to_off(b, va):
    for t, o, v, _, f, m, fl, al in segs(b)[3]:
        if t == 1 and v <= va < v + f: return o + va - v
    raise ValueError(hex(va))

def sections(b):
    shoff = struct.unpack_from('<I', b, 32)[0]; shsize, shnum, shstr = struct.unpack_from('<HHH', b, 46)
    sh = [struct.unpack_from('<10I', b, shoff + i * shsize) for i in range(shnum)]
    names = sh[shstr][4]
    out = {}
    for s in sh:
        n = b[names + s[0]:b.index(b'\0', names + s[0])].decode()
        out[n] = (s[4], s[5])       # offset, size
    return out

def rows_words():
    """address -> stock word for every [addr, word, ...] entry in rows.json (the 'pinned' ones included)."""
    found = {}
    def walk(x):
        if isinstance(x, list):
            if len(x) >= 2 and isinstance(x[0], str) and isinstance(x[1], str) and x[0].startswith('0x') and x[1].startswith('0x'):
                found[int(x[0], 16)] = int(x[1], 16)
            else:
                for y in x: walk(y)
        elif isinstance(x, dict):
            for y in x.values(): walk(y)
    walk(json.load(open(os.path.join(ROOT, 'patch', 'rows.json'))))
    return found

def main():
    a = sys.argv[1:]
    s, m = open(a[0], 'rb').read(), open(a[1], 'rb').read()
    allowed = {}                      # byte offset -> reason
    def allow(off, n, why):
        for k in range(off, off + n): allowed[k] = why
    phoff, size, num, _ = segs(s)
    allow(phoff, size * num, 'phdrs')
    pdr = sections(s)['.pdr']; allow(pdr[0], pdr[1], 'pdr')
    allow(va_to_off(s, HOOK[0]), HOOK[1], 'hook')
    allow(va_to_off(s, HOME_INIT[0]), HOME_INIT[1], 'home-init hook')
    allow(va_to_off(s, PLAYING[0]), PLAYING[1], 'playing init hook')
    allow(va_to_off(s, BIGCOVER[0]), BIGCOVER[1], 'timed cover page init hook')
    allow(va_to_off(s, LOCKSCREEN[0]), LOCKSCREEN[1], 'lock screen init hook')
    allow(va_to_off(s, PLAYMORE[0]), PLAYMORE[1], 'more dialog init hook')
    allow(va_to_off(s, PULLDOWN[0]), PULLDOWN[1], 'pull-down init hook')
    allow(va_to_off(s, START_PLAYER[0]), START_PLAYER[1], 'start player hook')
    allow(va_to_off(s, SAVE_STOP[0]), SAVE_STOP[1], 'save stop hook')
    allow(va_to_off(s, SAVE_START[0]), SAVE_START[1], 'save start hook')
    allow(va_to_off(s, BACKTOPLAYER[0]), BACKTOPLAYER[1], 'back to player hook')
    allow(va_to_off(s, ID3_SITE[0]), ID3_SITE[1], 'tag reader hook')
    allow(va_to_off(s, SCAN_SITE[0]), SCAN_SITE[1], 'library scan hook')
    allow(va_to_off(s, BATTERY_SITE[0]), BATTERY_SITE[1], 'battery percentage hook')
    for q in PULLDOWN_OPEN: allow(va_to_off(s, q), 4, 'pull-down settings tile hook')
    allow(va_to_off(s, WIFIHUB_SITE[0]), WIFIHUB_SITE[1], 'Wi-Fi hub row hook')
    allow(va_to_off(s, IDLE_SITE[0]), IDLE_SITE[1], 'idle view hook (the timed open)')
    allow(va_to_off(s, TIDALKB_SITE[0]), TIDALKB_SITE[1], 'Tidal search keyboard hook')
    for q in LINEOUT_SITES: allow(va_to_off(s, q), 4, 'Line Out pill hook')
    allow(va_to_off(s, UPDATE_SITE[0]), UPDATE_SITE[1], 'updater version compare')
    allow(va_to_off(s, timezones.SELECT), 8, 'select_timezone hook')   # time zones (tools/timezones.py): the hook, the clamp, the row count and limit, the two call sites
    for a, *_ in timezones.edits(0, 0): allow(va_to_off(s, a), 4, 'time zone words')
    allow(va_to_off(s, pod.EQ_ROW), 8, 'Play Settings Equalizer row hook')
    allow(va_to_off(s, pod.LOCKROW), 8, 'Display page Lock Screen row hook')
    allow(va_to_off(s, pod.NEXTALBUM_SITE), 8, 'mclNextSong end branch hook (Continue with Next Album)')
    for q in SHUFFLE_HOOKS: allow(va_to_off(s, q), 8, 'shuffle hook')
    for q in MODE_SITES: allow(va_to_off(s, q), 4, 'play mode display site')
    allow(va_to_off(s, pod.CLEAR_SITE), 4, 'dmr_serverstart deque_clear site')
    for a, old, new, _ in autotime.EDITS: allow(va_to_off(s, a), len(old), 'auto time literals')
    for a, *_ in themeoff.EDITS: allow(va_to_off(s, a), 4, 'theme1 off')
    for a, *_ in coex.EDITS: allow(va_to_off(s, a), 4, 'Wi-Fi + Bluetooth together')
    for q in QUERY: allow(va_to_off(s, q), 8, 'library query hook')
    for q in LIGHT: allow(va_to_off(s, q), 8, 'Light Mode hook')
    allow(va_to_off(s, SCROLL_SLOT[0]), SCROLL_SLOT[1], 'scroll vtable slot')
    markers = mn.marker_edits()
    for va in markers: allow(va_to_off(s, va), 4, 'markers')
    rows = rows_words()
    for va in rows: allow(va_to_off(s, va), 4, 'rows')
    for va in COVER_IMM: allow(va_to_off(s, va), 4, 'cover')
    diff = [k for k in range(len(s)) if s[k] != m[k]]
    bad = [k for k in diff if k not in allowed]
    count = {}
    for k in diff: count[allowed.get(k)] = count.get(allowed.get(k), 0) + 1
    print(f'stock {len(s)} bytes, built {len(m)} bytes (appended {len(m) - len(s)}); differing bytes by region: {count}')
    ok = not bad and len(m) >= len(s)
    if bad: print('UNEXPECTED differing bytes at file offsets', [hex(k) for k in bad[:20]], '...' if len(bad) > 20 else '')
    # words: how many of the rows.json words changed, and what the cover words are
    changed = [va for va in rows if s[va_to_off(s, va):va_to_off(s, va) + 4] != m[va_to_off(m, va):va_to_off(m, va) + 4]]
    print(f'rows.json: {len(rows)} entries, {len(changed)} changed words')
    # the cover sites must not be among rows.json's words
    over = [hex(v) for v in COVER_IMM if v in rows]
    print('cover sites overlapping rows.json:', over or 'none')
    ok = ok and not over
    for va in COVER_IMM:
        o = va_to_off(s, va); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = mw == (sw & 0xffff0000) | COVER
        print(f'cover {va:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    h = HOOK[0]; o = va_to_off(s, h)
    print(f'hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'unchanged')
    h = HOME_INIT[0]; o = va_to_off(s, h)
    print(f'home-init hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = PLAYING[0]; o = va_to_off(s, h)
    print(f'Now Playing hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = BIGCOVER[0]; o = va_to_off(s, h)
    print(f'Timed cover page hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = LOCKSCREEN[0]; o = va_to_off(s, h)
    print(f'Lock screen hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = PULLDOWN[0]; o = va_to_off(s, h)
    print(f'Pull-down hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = PLAYMORE[0]; o = va_to_off(s, h)
    print(f'More dialog hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = START_PLAYER[0]; o = va_to_off(s, h)
    print(f'start player hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    for nm, (h, _) in (('save stop', SAVE_STOP), ('save start', SAVE_START)):
        o = va_to_off(s, h)
        print(f'{nm} hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
        ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    h = BACKTOPLAYER[0]; o = va_to_off(s, h)
    print(f'back to player hook {h:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'changed' if s[o:o + 8] != m[o:o + 8] else 'UNCHANGED')
    ok = ok and s[o:o + 8] != m[o:o + 8] and s[o + 8:o + 16] == m[va_to_off(m, h) + 8:va_to_off(m, h) + 16]
    o = va_to_off(s, ID3_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))   # jalr t9 -> jal into the payload
    print(f'tag reader hook {ID3_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    for q in QUERY:
        o = va_to_off(s, q); mw = struct.unpack_from('<I', m, o)[0]
        good = mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12] and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'library query hook {q:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
        ok = ok and good
    for q in LIGHT:
        o = va_to_off(s, q); mw = struct.unpack_from('<I', m, o)[0]
        good = mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12] and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'Light Mode hook {q:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, SCAN_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'library scan hook {SCAN_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    o = va_to_off(s, BATTERY_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'battery percentage hook {BATTERY_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    for q in PULLDOWN_OPEN:
        o = va_to_off(s, q); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = sw >> 16 == 0x0411 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'pull-down settings tile hook {q:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, WIFIHUB_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'Wi-Fi hub row hook {WIFIHUB_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    o = va_to_off(s, IDLE_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'idle view hook {IDLE_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    o = va_to_off(s, TIDALKB_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'Tidal search keyboard hook {TIDALKB_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    for q in LINEOUT_SITES:
        o = va_to_off(s, q); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'Line Out pill hook {q:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, pod.LOCKROW); mw = struct.unpack_from('<I', m, o)[0]
    good = (struct.unpack_from('<II', s, o) == (0x8f84a708, 0x1000fff6) and mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12]
            and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s)))
    print(f'Display page Lock Screen row hook {pod.LOCKROW:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
    ok = ok and good
    o = va_to_off(s, pod.EQ_ROW); mw = struct.unpack_from('<I', m, o)[0]
    good = (struct.unpack_from('<II', s, o) == (0x8f84a708, 0x1000ff93) and mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12]
            and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s)))
    print(f'Play Settings Equalizer row hook {pod.EQ_ROW:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
    ok = ok and good
    o = va_to_off(s, pod.NEXTALBUM_SITE); mw = struct.unpack_from('<I', m, o)[0]
    good = (struct.unpack_from('<II', s, o) == pod.NEXTALBUM_DISPLACED and mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12]
            and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s)))
    print(f'mclNextSong end branch hook {pod.NEXTALBUM_SITE:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
    ok = ok and good
    for q in SHUFFLE_HOOKS:
        o = va_to_off(s, q); mw = struct.unpack_from('<I', m, o)[0]
        good = mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12] and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'shuffle hook {q:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
        ok = ok and good
    for q in MODE_SITES + (pod.CLEAR_SITE,):   # the clear site is the same shape: jalr -> jal into the payload (dmr_serverstart's deque_clear, sh_clear_queue)
        o = va_to_off(s, q); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = sw == 0x0320f809 and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'play mode display site {q:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, timezones.SELECT); mw = struct.unpack_from('<I', m, o)[0]
    good = mw >> 26 == 2 and m[o + 4:o + 8] == bytes(4) and s[o + 8:o + 12] == m[o + 8:o + 12] and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
    print(f'select_timezone hook {timezones.SELECT:#x}: {s[o:o + 8].hex()} -> {m[o:o + 8].hex()}', 'ok' if good else 'WRONG')
    ok = ok and good
    for a, old, _, _ in timezones.edits(0, 0):
        o = va_to_off(s, a); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = sw == old and mw != old
        if a in (timezones.ROW_CALL, timezones.LABEL_CALL):
            good = good and mw >> 26 == 3 and 0xb00000 <= (mw & 0x3ffffff) << 2 < 0xb00000 + (len(m) - len(s))
        print(f'time zone word {a:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, UPDATE_SITE[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    lit = va_to_off(s, 0x74773c); neu = va_to_off(s, 0x74772c)
    good = (sw, mw) == (0x24a5773c, 0x24a5772c) and s[lit:lit + 5] == m[lit:lit + 5] == b'V2.1\0' and m[neu:neu + 14] == b'about_version\0'   # the literal stays, the compare reads another string
    print(f'updater compare {UPDATE_SITE[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    for a, old, new, what in coex.EDITS:   # docs/modules/overlays.md "Wi-Fi and Bluetooth together": beqz v0 -> b, same target
        o = va_to_off(s, a); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = (sw, mw) == (old, new)
        print(f'Wi-Fi + Bluetooth {a:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    for a, old, new, what in autotime.EDITS:   # docs/modules/autotime.md: each slot holds the stock text in stock and the new text in the build, NUL-padded to the same length
        o = va_to_off(s, a); good = s[o:o + len(old)] == old and m[o:o + len(new)] == new
        print(f'auto time literal {a:#x}: {old.rstrip(bytes(1))!r} -> {new.rstrip(bytes(1))!r}', 'ok' if good else 'WRONG')
        ok = ok and good
    for a, text in autotime.NEIGHBOURS:
        o = va_to_off(s, a); good = s[o:o + len(text)] == m[o:o + len(text)] == text
        print(f'auto time neighbour {a:#x}', 'ok' if good else 'WRONG')
        ok = ok and good
    for a, old, new, what in themeoff.EDITS:   # docs/modules/theme.md: the stock word in stock, the new one in the build
        o = va_to_off(s, a); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = (sw, mw) == (old, new)
        print(f'theme1 off {a:#x} ({what}): {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    o = va_to_off(s, SCROLL_SLOT[0]); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
    good = sw == 0 and 0xb00000 <= mw < 0xb00000 + (len(m) - len(s)) and mw % 4 == 0   # an empty slot, now a word inside the payload
    print(f'scroll_view before-children slot {SCROLL_SLOT[0]:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
    ok = ok and good
    for va, (old, new) in markers.items():   # the A-B markers: the stock word in stock, the new one in the build
        o = va_to_off(s, va); sw = struct.unpack_from('<I', s, o)[0]; mw = struct.unpack_from('<I', m, o)[0]
        good = (sw, mw) == (old, new)
        print(f'marker {va:#x}: {sw:#010x} -> {mw:#010x}', 'ok' if good else 'WRONG')
        ok = ok and good
    print('OK (1 passed, 0 failed)' if ok else 'FAIL (0 passed, 1 failed)')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
