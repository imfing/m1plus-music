"""The Home pins (patch/pins.c, patch/pins.h, tools/pod_pins_home.py, docs/modules/pins.md): the constants shared with patch/offsets.inc, the menu asset's section and long press
sheet, the playlist card's rows, the strings and glyphs, the file model (round trip, malformed files), the pin and unpin calls against the model (order, cap of six, the toast, no
twice, cut names) and the section in the Home list under demo's own layouter (hidden: the plain menu; shown: first, the rows below it)."""
import os, random, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_icons, pod_pins_home as H
recent = sibling('recent')

PINS, PINS_TMP = '/mnt/mmc/.m1plus/home-pins', '/mnt/mmc/.m1plus/home-pins.tmp'
PIN_KEYS = ('Pin Album', 'Unpin Album', 'Pin Playlist', 'Unpin Playlist', 'Pin Song', 'Unpin Song', 'Pin Artist', 'Unpin Artist', 'Unpin an item first')


def u(s): return s.encode('utf-8').decode('latin-1')   # the model keeps a file's bytes as latin-1 characters


def album(name, artist='X', path=None):
    """The pin of an album as the payload stores it."""
    return ('a', H.identity(name), (album_key(artist, name), 0, 0, 0), u(name), u(path if path is not None else f'/mnt/mmc/{artist}/{name}/1.flac'))


def song(path, title, artist='X', album='Y', cue=0):
    """The pin of a song as the payload stores it: key the FNV of its path (and CUE start), the cover key of its album, its title, its path field ("<start>@" before the path for a CUE track)."""
    return ('s', H.song_id(path, cue), (album_key(artist, album), 0, 0, 0), u(title), u(H.song_path(path, cue)))


def artist(name, scope='0'):
    """The pin of an artist as the payload stores it: the key the FNV of its name (case folded), its one cover key the artist photo's cache key, its name, the list it was pinned from ("0" Artists, "1" Album Artists)."""
    return ('r', H.identity(name), (H.artist_key(name), 0, 0, 0), u(name), scope)


def playlist(pid, name, keys=()):
    return ('p', pid, H.keys4(keys), u(name), '')


ENTRIES = [album('Kind of Blue', 'Miles Davis'), playlist(3, 'Late Night Jazz', (11, 22, 33)), album('Homogenic', 'Bjork'), playlist(9, 'Road Trip', (44,)),
           album('Mezzanine', 'Massive Attack'), playlist(12, 'Empty')]


class PM(Machine):
    COUNT = True


def machine(data=None):
    m = PM()
    if data is not None: m.fs[PINS] = data
    return m


def pin_album(m, e):
    return struct.unpack('<i', struct.pack('<I', m.call(PSYMS['pins_pin_album'], a0=m.cstr(e[3]), a1=e[2][0], a2=m.cstr(e[4]), count=4000000)))[0]


def pin_playlist(m, e, keys):
    kp = m.alloc(16); m.u.mem_write(kp, struct.pack('<4I', *(list(keys) + [0] * 4)[:4]))
    return struct.unpack('<i', struct.pack('<I', m.call(PSYMS['pins_pin_playlist'], a0=e[1], a1=m.cstr(e[3]), a2=kp, a3=len(keys), count=4000000)))[0]


def pin_song(m, path, title='Track', artist='X', album='Y', cue=0):
    r = m.record(album=album, artist=artist, path=path, title=title)
    m.setword(r + O['REC_CUE_START'], cue)
    return struct.unpack('<i', struct.pack('<I', m.call(PSYMS['pins_pin_song'], a0=r, count=4000000)))[0]


def has_album(m, e): return m.call(PSYMS['pins_has_album'], a0=m.cstr(e[3]), count=4000000)
def has_playlist(m, e): return m.call(PSYMS['pins_has_playlist'], a0=e[1], a1=m.cstr(e[3]), count=4000000)


def constants_and_asset_tests(ctx):
    """The numbers, the asset, the strings, the glyphs."""
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_menu.bin'), 'rb').read())

    names = ('PIN_W', 'PIN_COLS', 'PIN_MARGIN', 'PIN_GAP', 'PIN_COVER', 'PIN_R', 'PIN_TOP', 'PIN_TGAP', 'PIN_TH', 'PIN_TEXT_PX', 'PIN_ROW_GAP', 'PIN_PITCH', 'PIN_BOTTOM', 'PIN_MAX', 'PIN_ROWS')
    expect([O[k] for k in names] == [310, 3, 12, 8, 90, 6, 6, 6, 20, 15, 10, 126, 8, 6, 2], f'the tiles: 3 columns of 90 px covers (x 12, 8 apart), 6 px corners, 6 px on top, name line 20 px 6 px under, rows 126 apart ({[O[k] for k in names]})')
    expect(O['PIN_COVER'] == (O['PIN_W'] - 2 * O['PIN_MARGIN'] - (O['PIN_COLS'] - 1) * O['PIN_GAP']) // O['PIN_COLS'] and O['PIN_PITCH'] == O['PIN_COVER'] + O['PIN_TGAP'] + O['PIN_TH'] + O['PIN_ROW_GAP']
           and O['PIN_MAX'] == O['PIN_COLS'] * O['PIN_ROWS'] and O['PIN_W'] == O['SH_W'], 'the cover is what the 310 px list leaves for three columns; the pitch is cover + 6 + 20 + 10; six pins fill two rows')
    heights = [pod_ui.PIN_H(n) for n in (1, 2)]
    expect(heights == [130, 256] and pod_ui.PIN_HMAX == 256 and O['PIN_BOTTOM'] == 8, f'a section is 6 + rows of tiles (the last without its 10 px of row gap) + 8 px of air: 130 and 256 ({heights})')
    expect((O['PIN_STR'], O['PIN_PATH'], O['PIN_FILE_MAX']) == (H.STR, H.PATH, H.FILE_MAX) and O['PIN_MAX'] == H.MAX, 'the file model and the payload agree on the cap and the sizes')
    expect(O['PIN_FIRST_MS'] > 0 and O['PIN_TICK_MS'] > 0 and O['PIN_CHECK_MS'] == O['RC_RESOLVE_MS'], 'a one-shot before the first decode, a tick per cover, the library check after the same 5 s as Recently Played\'s resolve')
    expect(O['PIN_MARGIN'] + O['PIN_COLS'] * O['PIN_COVER'] + (O['PIN_COLS'] - 1) * O['PIN_GAP'] + O['PIN_MARGIN'] == 310, 'the margins are equal on both sides')

    sv = ui.find('pod_scrollview')
    kids = [c.name for c in sv.children]
    expect(kids[-4:] == ['pod_pins', 'pod_daily', 'pod_shelf', 'pod_pad'], f'the pins are a child of the list\'s scroll view (the payload stacks them first) ({kids[-4:]})')
    sec = sv.find('pod_pins')
    expect(sec.type == 'view' and (sec.x, sec.y, sec.w, sec.h) == (0, 0, 310, 256) and sec.get('visible') == 'false' and sec.get('sensitive') == 'false' and sec.get('style:normal:bg_color') == '#000000',
           'pod_pins is a 310 x 256 black view, hidden and insensitive in the asset')
    lab = sec.find('pod_pin_title')
    expect([c.name for c in sec.children] == ['pod_pin_title'] and lab.type == 'label' and lab.get('visible') == 'false' and lab.get('sensitive') == 'false'
           and lab.get('style:normal:font_size') == '15' and lab.get('style:normal:text_color') == '#FFFFFF' and lab.get('style:normal:text_align_h') == 'center',
           'no header: its one child is the hidden, insensitive label with the name style (15 px white, centred)')
    others = [p.key for p in pod_pages.PAGES if p is not pod_pages.MENU and any(w.name in pod_ui.PIN_NAMES for w in awtk_ui.parse(open(os.path.join(raw, 'ui', p.key + '.bin'), 'rb').read()).walk())]
    expect(not others, f'only the menu page carries the section ({others})')
    tree = asset_tree(os.path.join(raw, 'ui', 'm1plus_menu.bin'))
    expect(node(tree, 'pod_pins').flags & (F_VISIBLE | F_SENSITIVE) == 0 and node(tree, 'pod_pins').flags & F_ENABLE, 'asset_tree reads the section hidden and insensitive')

    # the long press sheet: six rows for albums (Play, Shuffle, Unpin Album, Add to Playlist, Play Next, Play After) on the six-row glass, the window's last two children
    kids = [c.name for c in ui.children]
    expect(kids[-2:] == ['rm_scrim', 'rm_card'], f'the sheet is the window\'s last two children, over the bar ({kids})')
    card = ui.find('rm_card')
    labs = [card.find(f'rm_label{i}').get('tr_text') for i in range(6)]
    icons = [card.find(f'rm_icon{i}').get('image') for i in range(6)]
    expect(labs == ['Play', 'Shuffle', 'Unpin Album', 'Add to Playlist', 'Play Next', 'Play After']
           and icons == ['rm_ic_pplay', 'rm_ic_pshuffle', 'rm_ic_unpin', 'rm_ic_add', 'rm_ic_next', 'rm_ic_after']
           and (card.x, card.y, card.w, card.h) == (0, 450 - 300, 320, 300)
           and card.get('style:normal:bg_image') == 'pc_sheet6' and card.get('visible') == 'false' and card.get('sensitive') == 'false' and ui.find('rm_scrim').get('visible') == 'false',
           'the Home sheet: Play, Shuffle, Unpin Album, Add to Playlist, Play Next, Play After on the six-row glass, hidden')
    al_ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_albums.bin'), 'rb').read())
    al_card = al_ui.find('rm_card')
    expect([al_card.find(f'rm_label{i}').get('tr_text') for i in range(6)] == labs
           and [al_card.find(f'rm_icon{i}').get('image') for i in range(6)] == icons
           and al_card.get('style:normal:bg_image') == 'pc_sheet6' and (al_card.x, al_card.y, al_card.w, al_card.h) == (0, 150, 320, 300)
           and [c.name for c in al_card.children][-2:] == ['rm_hair0', 'rm_hair1'],
           'the Albums page sheet matches the six-row album sheet, hairlines last')
    ar_ui = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_artists.bin'), 'rb').read())
    ar_card = ar_ui.find('rm_card')
    expect([ar_card.find(f'rm_label{i}').get('tr_text') for i in range(3)] == ['Play', 'Shuffle', 'Unpin Album']
           and ar_card.find('rm_item3') is None and ar_card.get('style:normal:bg_image') == 'pc_sheet3',
           'the Artists page keeps the three-row sheet')
    expect(mod_icons.RM_PIN_ICONS == (('rm_ic_pplay', 'play'), ('rm_ic_pshuffle', 'shuffle'), ('rm_ic_unpin', 'pin-off'))
           , 'the sheet\'s glyphs are Lucide play, shuffle and pin-off')
    xx = os.path.join(raw, 'images', 'xx')
    for n in ('rm_ic_pplay', 'rm_ic_pshuffle', 'rm_ic_unpin', 'pod_ic_vspin', 'pod_ic_vsunpin'):
        expect(os.path.exists(os.path.join(xx, n + '.png')) and open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read(), f'{n}.png is in the package, the committed one')
    expect(mod_icons.SONGS_IMAGES['pod_ic_vspin'] == ('pin', mod_icons.WHITE, None, 20) and mod_icons.SONGS_IMAGES['pod_ic_vsunpin'] == ('pin-off', mod_icons.WHITE, None, 20),
           'the playlist card\'s glyphs are Lucide pin and pin-off on the cards\' 20 px canvas')
    svg = os.path.join(ROOT, 'assets', 'icons', 'lucide', 'svg')
    expect(all(os.path.exists(os.path.join(svg, n + '.svg')) for n in ('pin', 'pin-off', 'play', 'shuffle')), 'the Lucide sources are committed')

    expect(all(k in pod_i18n.TEXT and len(pod_i18n.TEXT[k]) == 13 and all(pod_i18n.TEXT[k].values()) for k in PIN_KEYS), 'the pin strings are in all 13 languages')
    expect('Pin to Home' not in pod_i18n.TEXT and 'Unpin from Home' not in pod_i18n.TEXT, 'the words are Apple Music\'s per type (Pin Album, Pin Playlist)')
    exp = ui_find_songs()
    expect(exp.find('vs_label9').get('tr_text') == 'Pin Playlist' and exp.find('vs_glyph9').get('image') == 'pod_ic_vspin', 'the Songs page\'s card has the pin row in slot 9')


def ui_find_songs():
    return awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_songs.bin'), 'rb').read())


def file_and_api_tests(ctx):
    """The file model, and the pin and unpin calls against it."""
    expect = ctx.expect
    # ------------------------------------------------------------------ the model
    data = H.dump(ENTRIES)
    expect(H.parse(data) == ENTRIES and H.parse(H.MAGIC) == [] and H.parse(b'') == [], 'the model round-trips a full list; the bare magic is an empty list')
    bad = {'magic': b'M1P0\n' + data[5:], 'no newline': data[:-1], 'seven': H.MAGIC + b'a\t00000001\t00000002\t0\t0\t0\tname\n', 'kind': data.replace(b'a\t', b'x\t', 1),
           'zero key': H.dump([('a', 0, (1, 0, 0, 0), 'n', '')]), 'album no cover': H.dump([('a', 1, (0, 0, 0, 0), 'n', '')]), 'album with two covers': H.dump([('a', 1, (1, 2, 0, 0), 'n', '')]),
           'playlist gap': H.dump([('p', 1, (1, 0, 2, 0), 'n', '')]), 'playlist twice': H.dump([('p', 1, (5, 5, 0, 0), 'n', '')]), 'playlist path': H.dump([('p', 1, (1, 0, 0, 0), 'n', '/x')]),
           'song no path': H.dump([('s', 1, (1, 0, 0, 0), 'n', '')]), 'song two covers': H.dump([('s', 1, (1, 2, 0, 0), 'n', '/x')]), 'song no cover': H.dump([('s', 1, (0, 0, 0, 0), 'n', '/x')]),
           'artist with a path': H.dump([('r', 1, (1, 0, 0, 0), 'n', '/x')]), 'artist with scope 2': H.dump([('r', 1, (1, 0, 0, 0), 'n', '2')]), 'song cue zero': H.dump([('s', 1, (1, 0, 0, 0), 'n', '0@/x')]), 'song cue no path': H.dump([('s', 1, (1, 0, 0, 0), 'n', '5@x')]), 'song cue ten digits': H.dump([('s', 1, (1, 0, 0, 0), 'n', '1234567890@/x')]), 'artist two covers': H.dump([('r', 1, (1, 2, 0, 0), 'n', '')]), 'artist no cover': H.dump([('r', 1, (0, 0, 0, 0), 'n', '')]),
           'twice': H.dump([ENTRIES[0], ENTRIES[0]]), 'seven pins': H.dump([album(f'A{i}') for i in range(7)]), 'empty name': H.dump([('a', 1, (1, 0, 0, 0), '', '')]),
           'control byte': H.dump([('a', 1, (1, 0, 0, 0), 'a\x01b', '')]), 'upper hex': data.replace(b'00000003', b'0000000A', 1), 'long name': H.dump([('a', 1, (1, 0, 0, 0), 'n' * 96, '')]),
           'long path': H.dump([('a', 1, (1, 0, 0, 0), 'n', 'p' * 256)]), 'too big': data + b'\n' * 4000}
    expect(all(H.parse(v) == [] for v in bad.values()), f'every malformed file reads as an empty list ({[k for k, v in bad.items() if H.parse(v) != []]})')
    songs = [song('/mnt/mmc/A/b.flac', 'Title'), song('/mnt/mmc/C/d.flac', 'Other', 'Z', 'W')]
    expect(H.parse(H.dump(songs + ENTRIES[:2])) == songs + ENTRIES[:2] and H.song_id('/mnt/mmc/A/b.flac') == pod_mix_fnv('/mnt/mmc/A/b.flac') and H.song_id('/mnt/mmc/a/b.flac') != H.song_id('/mnt/mmc/A/b.flac'),
           'the model round-trips songs among albums and playlists; a song\'s key is the FNV-1a of its path as written (case matters)')
    expect(H.parse(H.dump([album('x' * 95)])) != [] and H.parse(H.dump([('a', 1, (1, 0, 0, 0), 'n', 'p' * 255)])) != [], 'names of 95 and paths of 255 bytes are the longest')
    expect(H.pin([], ENTRIES[0]) == ([ENTRIES[0]], 'ok') and H.pin(ENTRIES, album('Seven'))[1] == 'full' and H.pin(ENTRIES[:2], ENTRIES[1]) == (ENTRIES[:2], 'ok')
           and H.pin(ENTRIES[:2], ENTRIES[2])[0] == ENTRIES[:3] and H.unpin(ENTRIES, 'p', 3) == [e for e in ENTRIES if e[1] != 3], 'the model: a new pin joins the end, full at six, no pin twice, unpin')
    expect(H.move(ENTRIES, 0, 3) == ENTRIES[1:4] + ENTRIES[:1] + ENTRIES[4:] and H.move(ENTRIES, 5, 0) == ENTRIES[5:] + ENTRIES[:5] and H.move(ENTRIES, 2, 2) == ENTRIES and H.move(ENTRIES, 2, 9) == ENTRIES,
           'the model: a move takes the pin out and puts it at the slot, the others close up')
    expect(H.keys4([5, 0, 5, 6, 7, 8, 9]) == (5, 6, 7, 8) and H.keys4([]) == (0, 0, 0, 0), 'a playlist\'s keys: the distinct non-zero ones, at most four')

    # ------------------------------------------------------------------ the calls
    m = machine()
    expect(has_album(m, ENTRIES[0]) == 0 and has_playlist(m, ENTRIES[1]) == 0, 'no file: nothing is pinned')
    expect(pin_album(m, ENTRIES[0]) == 0 and m.fs[PINS] == H.dump(ENTRIES[:1]) and PINS_TMP not in m.fs, 'the first pin writes the file (atomically: no temp file left)')
    expect(pin_playlist(m, ENTRIES[1], (11, 22, 33)) == 0 and m.fs[PINS] == H.dump(ENTRIES[:2]), 'a playlist pin goes to the end with its mosaic keys')
    expect(has_album(m, ENTRIES[0]) == 1 and has_playlist(m, ENTRIES[1]) == 1 and has_playlist(m, playlist(4, 'x')) == 0 and has_album(m, album('Homogenic')) == 0, 'has: by the album\'s title and the playlist\'s id')
    expect(m.call(PSYMS['pins_has_album'], a0=m.cstr('KIND OF BLUE'), count=4000000) == 1, 'an album is its title, ASCII case aside (as Recently Played\'s identity)')
    before = m.fs[PINS]
    expect(pin_album(m, ENTRIES[0]) == 0 and m.fs[PINS] == before, 'pinning what is pinned changes nothing')
    for e in ENTRIES[2:]:
        (pin_album(m, e) if e[0] == 'a' else pin_playlist(m, e, [k for k in e[2] if k]))
    expect(m.fs[PINS] == H.dump(ENTRIES) and H.parse(m.fs[PINS]) == ENTRIES, 'six pins, in the order they were pinned')
    m.calls = []
    full = album('Seventh')
    r = pin_album(m, full)
    expect(r == -1 and m.fs[PINS] == H.dump(ENTRIES) and toasts(m) == ['Unpin an item first'],
           f'a seventh pin is refused ({r}) with the toast "Unpin an item first", the file untouched ({toasts(m)})')
    m.calls = []
    expect(pin_playlist(m, playlist(77, 'Seventh'), ()) == -1 and len(toasts(m)) == 1, 'a playlist is refused the same way')
    expect(m.call(PSYMS['pins_unpin_album'], a0=m.cstr('Homogenic'), count=4000000) == 1 and m.fs[PINS] == H.dump(H.unpin(ENTRIES, 'a', ENTRIES[2][1])), 'unpin removes the pin and keeps the order')
    expect(m.call(PSYMS['pins_unpin_album'], a0=m.cstr('Homogenic'), count=4000000) == 0 and m.call(PSYMS['pins_unpin_playlist'], a0=3, a1=m.cstr('Late Night Jazz'), count=4000000) == 1 and m.call(PSYMS['pins_unpin_playlist'], a0=3, a1=m.cstr('Late Night Jazz'), count=4000000) == 0,
           'unpinning what is not pinned answers 0')
    expect(pin_album(m, full) == 0 and H.parse(m.fs[PINS])[-1] == full, 'with room again the seventh item is pinned, at the end')
    # ------------------------------------------------------------------ songs
    m = machine()
    S = '/mnt/mmc/Artist/Album/01 Track.flac'
    ok = lambda path: m.call(PSYMS['pins_song_ok'], a0=m.cstr(path), count=4000000)
    expect(ok(S) == 1 and ok('') == 0 and ok('relative/x.flac') == 0 and ok('/' + 'p' * 254) == 1 and ok('/' + 'p' * 255) == 0, 'a song can be pinned when its path is absolute and under 256 bytes')
    expect(pin_song(m, S, 'Track', 'Artist', 'Album') == 0 and H.parse(m.fs[PINS]) == [song(S, 'Track', 'Artist', 'Album')] and PINS_TMP not in m.fs,
           'Pin Song writes the song\'s line: the FNV of its path, its album\'s cover key, its title, its path')
    expect(m.call(PSYMS['pins_has_song'], a0=m.cstr(S), count=4000000) == 1 and m.call(PSYMS['pins_has_song'], a0=m.cstr(S.upper()), count=4000000) == 0, 'has: by the path, case as written')
    before = m.fs[PINS]
    expect(pin_song(m, S, 'Track', 'Artist', 'Album') == 0 and m.fs[PINS] == before, 'a song that is pinned is not pinned twice')
    expect(pin_song(m, '/mnt/mmc/x/y.flac', '', 'A', 'B') == 0 and H.parse(m.fs[PINS])[-1][3] == 'y.flac', 'a song with no title is named by its file')
    expect(pin_song(m, '', 'T') == -2 and pin_song(m, 'rel/x.flac', 'T') == -2 and len(H.parse(m.fs[PINS])) == 2, 'no path, or not an absolute one: nothing to pin (PINS_FAIL)')
    for i in range(4): pin_song(m, f'/mnt/mmc/n{i}.flac', f'N{i}')
    m.calls = []
    before = m.fs[PINS]
    expect(pin_song(m, '/mnt/mmc/seventh.flac', 'S') == -1 and m.fs[PINS] == before and toasts(m) == ['Unpin an item first'], 'a seventh pin, a song among them, shows the toast and changes nothing')
    expect(m.call(PSYMS['pins_unpin_song'], a0=m.cstr(S), count=4000000) == 1 and m.call(PSYMS['pins_unpin_song'], a0=m.cstr(S), count=4000000) == 0 and len(H.parse(m.fs[PINS])) == 5, 'unpin by path: 1 once, then 0')
    # nothing to pin, no write
    m = machine(); m.calls = []
    expect(m.call(PSYMS['pins_pin_album'], a0=m.cstr(''), a1=5, a2=0, count=4000000) & 0xffffffff == 0xfffffffe and m.call(PSYMS['pins_pin_album'], a0=m.cstr('x'), a1=0, a2=0, count=4000000) & 0xffffffff == 0xfffffffe
           and m.call(PSYMS['pins_pin_playlist'], a0=0xffffffff, a1=m.cstr('x'), a2=0, a3=0, count=4000000) & 0xffffffff == 0xfffffffe and PINS not in m.fs, 'an empty name, no cover key or a negative playlist id pins nothing (PINS_FAIL)')
    # stock's playlist ids start at 0: the first playlist pins, is found, follows a rename and unpins like any other; the file with key 0 reads back
    m = machine(); zero = playlist(0, 'First', (11,))
    expect(pin_playlist(m, zero, (11,)) == 0 and m.fs[PINS] == H.dump([zero]) and H.parse(m.fs[PINS]) == [zero] and has_playlist(m, zero) == 1, 'playlist id 0 pins and is found (the model reads key 0 of a playlist)')
    expect(m.call(PSYMS['pins_rename_playlist'], a0=0, a1=m.cstr('First'), a2=m.cstr('Renamed'), count=4000000) == 1 and m.fs[PINS] == H.dump([playlist(0, 'Renamed', (11,))]), 'playlist id 0: its pin follows a rename')
    expect(m.call(PSYMS['pins_unpin_playlist'], a0=0, a1=m.cstr('Renamed'), count=4000000) == 1 and H.parse(m.fs[PINS]) == [], 'playlist id 0 unpins')
    # a failed write
    m = machine(); m.fail.add(('rename', PINS))
    expect(pin_album(m, ENTRIES[0]) == -2 and PINS not in m.fs and PINS_TMP not in m.fs, 'a failed write answers PINS_FAIL and leaves no file')
    # no card: nothing is read, nothing is written
    m = machine(H.dump(ENTRIES[:2])); m.card_mounted = False
    expect(pin_album(m, ENTRIES[2]) == -2 and m.fs[PINS] == H.dump(ENTRIES[:2]) and PINS_TMP not in m.fs, 'no card: a pin answers PINS_FAIL and writes nothing')
    # tags: control bytes become spaces, over-long names are cut on a UTF-8 boundary
    m = machine()
    nm = 'Café\t\x01' + 'x' * 200
    pin_album(m, ('a', 0, (7, 0, 0, 0), nm, '/mnt/mmc/é' * 60))
    got = H.parse(m.fs[PINS])
    exp_name = H.field(nm.encode(), H.STR)
    expect(len(got) == 1 and got[0][3].encode('latin-1') == exp_name and got[0][4].encode('latin-1') == H.field(('/mnt/mmc/é' * 60).encode(), H.PATH) and got[0][1] == H.identity(nm) and len(exp_name) == 95,
           'control bytes in a tag become spaces and a name or path is cut below its size without splitting a UTF-8 sequence: the file is always valid')
    # the file the payload reads is read as the model does (random damage)
    rnd = random.Random(7)
    names = [e[3] for e in ENTRIES if e[0] == 'a']
    ok = 0
    for i in range(60):
        d = bytearray(H.dump(ENTRIES))
        for _ in range(rnd.randint(0, 3)):
            at = rnd.randrange(len(d))
            op = rnd.randrange(3)
            if op == 0: d[at] = rnd.choice(b'0123456789abcdefgx\t\n \x00')
            elif op == 1: del d[at]
            else: d.insert(at, rnd.choice(b'0a\t\n'))
        d = bytes(d)
        m = machine(d)
        parsed = H.parse(d)
        want = {(e[0], e[1]) for e in parsed}
        pl = {e[1]: e for e in parsed if e[0] == 'p'}   # (a playlist pin is its id and its name: ask with the name the file has)
        got = {('a', H.identity(n)) for n in names if has_album(m, album(n))} | {('p', e[1]) for e in ENTRIES if e[0] == 'p' and has_playlist(m, pl.get(e[1], e))}
        ok += got == want & ({('a', H.identity(n)) for n in names} | {('p', e[1]) for e in ENTRIES if e[0] == 'p'})
    expect(ok == 60, f'the payload and the model read 60 damaged files alike ({ok})')


def toasts(m): return [c[1] for c in m.calls if c[0] == 'toast']


def pod_mix_fnv(path):
    h = O['FNV_SEED']
    for c in path.encode(): h = ((h ^ c) * 16777619) & 0xffffffff
    return h or 1


class PH(recent.ST):
    """The Home instance as real widget structs with the pins' section first-to-be in the asset's order (rows, pins, shelf, spacer)."""

    def __init__(self, entries=None, **kw):
        kw['start'] = False
        super().__init__(**kw)
        self.pins = self.widget(self.zv, 0, 0, pod_ui.PIN_W, pod_ui.PIN_HMAX, self.sv, emitter=True)
        self.u.mem_write(self.pins + 0x24, struct.pack('<H', 0x1))
        self.plab = self.widget(self.zv, 0, 0, 10, 10, self.pins)
        self.u.mem_write(self.plab + 0x24, struct.pack('<H', 0x1))
        self.kids(self.pins, [self.plab])
        self.kids(self.sv, self.rows + [self.pins, self.shelf, self.pad])
        self.widgets.update({'pod_pins': self.pins, 'pod_pin_title': self.plab})
        self.ret = {}   # what the trapped pages answer (patch/albums.c, patch/songs.c and patch/coverflow.c are tested in their own modules)
        for n in ('albums_open_artist', 'coverflow_artist', 'songs_play_artist', 'so_play'): self.handlers[PSYMS[n]] = n
        self.album_tracks, self.cur_album, self.plays, self.type_seen = {}, None, [], []   # album title -> its track rows (loadAlbumdetailList / loadLocalClassList); so_play's (class, [(path, cue start)], from, how); artist_type seen by songs_play_artist
        self.up_calls, self.up_ret = [], 1
        if entries is not None: self.fs[PINS] = H.dump(entries) if not isinstance(entries, bytes) else entries
        self.arrange(); self.relayout()

    def trap_upnext(self, ret=1):
        self.up_calls, self.up_ret = [], ret
        self.handlers[PSYMS['upnext_add']] = 'upnext_add'
        self.handlers[PSYMS['picker_open']] = 'picker_open'
        self.pk_calls, self.pk_ret = [], 0   # picker_open (class, count, the marks) and what it answers
        self.strings['msg_addfailed'] = 'Adding Failed'

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        regs = [u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)]
        if name == 'picker_open':
            self.pk_calls.append((regs[0], regs[1], bytes(self.u.mem_read(regs[2], (regs[1] + 7) // 8))))
            self.calls.append(('picker_open', regs[0], regs[1]))
            u.reg_write(UC_MIPS_REG_V0, self.pk_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'upnext_add':
            rows = [self.read_cstr(self.word(r + O['REC_PATH'])) for r in self.deques.get(regs[0], [])]
            self.up_calls.append((rows, regs[1]))
            self.calls.append(('upnext_add', regs[1], len(rows)))
            u.reg_write(UC_MIPS_REG_V0, self.up_ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'so_play':
            rows = [(self.read_cstr(self.word(r + O['REC_PATH'])), self.s32(r + O['REC_CUE_START'])) for r in self.deques.get(regs[1], [])]
            self.plays.append((regs[0], rows, regs[2] if regs[2] < 1 << 31 else regs[2] - (1 << 32), regs[3]))
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'loadAlbumdetailList' and self.album_tracks:
            self.cur_album = self.read_cstr(self.word(regs[1] + O['REC_ALBUM']))
            self.calls.append(('loadAlbumdetailList', self.cur_album))
            self.setword(pod.DATA['CLASSINFO'][0], O['CLASS_ARTIST_SONGS'])
            u.reg_write(UC_MIPS_REG_V0, len(self.album_tracks.get(self.cur_album, []))); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'loadLocalClassList' and regs[0] == O['CLASS_ARTIST_SONGS'] and self.cur_album is not None:
            items = self.album_tracks.get(self.cur_album, [])
            self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
            u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'songs_play_artist': self.type_seen.append(self.word(pod.DATA['ARTIST_TYPE'][0]))
        if name in ('albums_open_artist', 'coverflow_artist', 'songs_play_artist'):
            a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
            title = lambda r: self.read_cstr(self.word(r + O['REC_TITLE']))
            rows = [title(r) for r in self.deques.get(a0, [])] if name != 'songs_play_artist' else [title(a0)]
            self.calls.append((name, tuple(rows), a1, a2))
            u.reg_write(UC_MIPS_REG_V0, self.ret.get(name, 0) & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if self.handlers.get(address) == 'widget_get_prop_int':
            a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
            prop = self.read_cstr(a1)
            if a0 == getattr(self, 'pins', None) and prop in ('y', 'h'):
                u.reg_write(UC_MIPS_REG_V0, self.word(self.pins + {'y': 4, 'h': 0xc}[prop])); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
        super()._hook(u, address, size, _)

    def begin(self):
        self.calls = []
        self.call(PSYMS['pins_start'], a0=self.root, count=8000000)

    def order(self):
        arr = self.word(self.sv + 0x58); elms = self.word(arr + 8)
        names = {self.pins: 'pins', self.shelf: 'shelf', self.pad: 'pad'}
        return [names.get(c) or self.rows.index(c) for c in (self.word(elms + 4 * i) for i in range(self.word(arr)))]


def section_tests(ctx):
    """The section in the Home list: hidden it is the plain menu; shown it is the first child, 130 or 256 px high, and the rows sit below it."""
    expect = ctx.expect
    m = PH(entries=None)
    base_vh = m.vh()
    ys0 = m.row_ys()
    m.begin()
    expect(not m.is_shown(m.pins) and m.row_ys() == ys0 and m.vh() == base_vh, 'nothing pinned: the section stays hidden and insensitive and the menu is exactly the plain one')
    expect(('widget_on', m.root, O['EVT_DESTROY'], PSYMS['pn_on_destroy'], m.root) in m.calls and PSYMS['pn_first'] in [t[0] for t in m.timers], 'start registers the window\'s events and arms the one-shot')

    for n, h in ((1, 130), (2, 130), (3, 130), (4, 256), (6, 256)):
        m = PH(entries=ENTRIES[:n])
        ys = m.row_ys()
        m.begin()
        shown = m.is_shown(m.pins)
        expect(shown and m.s32(m.pins + 0xc) == h and m.s32(m.pins + 4) == 0, f'{n} pins: the section is shown, {h} px high, at the top')
        expect(m.order()[0] == 'pins' and all(m.row_ys()[i] == ys[i] + h for i in ys) and m.vh() == base_vh + h,
               f'{n} pins: the first child, every row {h} px lower, virtual_h grows by {h} ({sorted(m.row_ys().items())[:2]})')
    # tile x: 1 or 2 pins are one row centred in the section, 3 or more start at the margin (a partial last row from the left)
    for n, xs in ((1, [110]), (2, [61, 159]), (3, [12, 110, 208]), (4, [12, 110, 208, 12]), (5, [12, 110, 208, 12, 110]), (6, [12, 110, 208, 12, 110, 208])):
        m = PH(entries=ENTRIES[:n]); m.begin()
        got = [m.call(PSYMS['pn_x'], a0=i, count=100000) for i in range(n)]
        expect(got == xs and [pod_ui.pin_x(i, n) for i in range(n)] == xs, f'{n} pins: tile x {xs} (centred row for 1 and 2, left-aligned otherwise), got {got}')
    # a pin of stock's first playlist (id 0) is a pin like any other
    m = PH(entries=[playlist(0, 'First', (11,))]); m.begin()
    expect(m.is_shown(m.pins) and m.s32(m.pins + 0xc) == 130, 'a file whose playlist pin has id 0 shows its section')
    # a bad file is no section
    m = PH(entries=b'junk'); m.begin()
    expect(not m.is_shown(m.pins) and m.vh() == base_vh, 'a malformed file shows nothing')
    # an asset without the section or the label: the menu is as it was
    m = PH(entries=ENTRIES[:2]); m.widgets.pop('pod_pin_title'); m.begin()
    expect(not m.is_shown(m.pins) and m.vh() == base_vh and not [t for t in m.timers if t[0] == PSYMS['pn_first']], 'a missing widget: nothing is shown or moved, no timer')
    # a pin removed from the file while the menu is behind another page disappears when the menu is in front again
    m = PH(entries=ENTRIES[:4]); m.begin()
    m.fs[PINS] = H.dump([])
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    expect(not m.is_shown(m.pins) and m.vh() == base_vh and m.row_ys() == ys0, 'the to-foreground reads the file again: with nothing pinned the section goes and the rows are back at the top')
    # a pin whose name alone changed in the file (a renamed playlist: same id, same cover keys) keeps its tile and shows the new name
    def names(m):
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        m.texts.clear()
        m.call(PSYMS['pn_on_paint'], a0=0, a1=e, count=40000000)
        return [t[0] for t in m.texts]
    m = PH(entries=[playlist(3, 'Jazz', (11, 22, 33)), album('Homogenic', 'Bjork')]); m.begin()
    first = names(m)
    m.fs[PINS] = H.dump([playlist(3, 'Evening', (11, 22, 33)), album('Homogenic', 'Bjork')])
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    expect(first == ['Jazz', 'Homogenic'] and names(m) == ['Evening', 'Homogenic'], f'a renamed playlist\'s pin shows its new name at the next to-foreground ({first}, {names(m)})')

def tr(m, name):
    """The last translation key the payload set on the widget."""
    return ([c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[name]] or [None])[-1]


SHEET_WIDGETS = ('rm_scrim', 'rm_card') + tuple(f'rm_item{i}' for i in range(7)) + tuple(f'rm_label{i}' for i in range(7)) + tuple(f'rm_icon{i}' for i in range(7)) + ('rm_hair0', 'rm_hair1')


def sheet_tests(ctx):
    """Home grid long-press sheets: a song opens 2 rows (Play | Unpin Song), a playlist 3 (Play, Shuffle | Unpin Playlist), and an album 6 (Play, Shuffle | Unpin Album, Add to Playlist | Play Next, Play After), the groups apart by a hairline; switching between them restores labels, icons and visibility; Play Next and Play After queue every track of the album in order via upnext_add; Add to Playlist marks every track for the picker."""
    expect = ctx.expect
    RM = sibling('rowmenu')
    S = song('/mnt/mmc/Artist/Album/01 Track.flac', 'Track', 'Artist', 'Album')
    m = PH(entries=[S, ENTRIES[1], ENTRIES[0]])
    for n in SHEET_WIDGETS: Machine.widget(m, n)
    m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
    t1 = m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/Miles Davis/Kind of Blue/1.flac', title='So What', rid=1)
    t2 = m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/Miles Davis/Kind of Blue/2.flac', title='Freddie', rid=2)
    t3 = m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/Miles Davis/Kind of Blue/3.flac', title='Blue in Green', rid=3)
    m.album_tracks = {'Kind of Blue': [t1, t2, t3]}
    m.showlist = [m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/Miles Davis/Kind of Blue/1.flac', rid=9)]
    m.trap_upnext(1)
    m.begin()
    expect(m.is_shown(m.pins) and m.s32(m.pins + 0xc) == 130, 'three pins: one row of tiles')
    card = m.widgets['rm_card']
    def moved(m):
        return {n: m.s32(m.widgets[n] + 4) for n in [f'rm_item{i}' for i in range(7)] + ['rm_hair0', 'rm_hair1'] if (m.is_visible if 'hair' in n else m.is_shown)(m.widgets[n])}
    # 1. song (2 rows) -> 2. playlist (3 rows) -> 3. album (6 rows, restoring labels/icons/rows after song & playlist)
    for tile, rows in ((0, 2), (1, 3), (2, 6)):
        m.calls = []
        m.call(PSYMS['pn_open_sheet'], a0=tile, count=900000000)
        placed = [(m.s32(card + 4), m.s32(card + 8), m.s32(card + 0xc))]
        glass = m.props.get((card, 'style:normal:bg_image'))
        expect(placed == [(450 - 50 * rows, 320, 50 * rows)] and glass == f'pc_sheet{rows}' and m.is_shown(card),
               f'tile {tile}: the sheet opens {rows} rows high on pc_sheet{rows} ({placed}, {glass})')
        if rows == 2:
            expect(not m.is_shown(m.widgets['rm_item2']) and not m.is_shown(m.widgets['rm_item3']) and not m.is_shown(m.widgets['rm_item4'])
                   and tr(m, 'rm_label1') == 'Unpin Song' and m.props.get((m.widgets['rm_icon1'], 'image')) == 'rm_ic_unpin'
                   and moved(m) == {'rm_item0': 0, 'rm_hair0': 50, 'rm_item1': 50} and not m.is_visible(m.widgets['rm_hair1']),
                   f'a song\'s sheet: Play | Unpin Song, a hairline at 50; rows 2..4 hidden ({moved(m)})')
            m.click('rm_scrim', count=900000000)
        elif rows == 3:
            expect(m.is_shown(m.widgets['rm_item2']) and not m.is_shown(m.widgets['rm_item3']) and not m.is_shown(m.widgets['rm_item4'])
                   and tr(m, 'rm_label1') == 'Shuffle' and tr(m, 'rm_label2') == 'Unpin Playlist'
                   and m.props.get((m.widgets['rm_icon2'], 'image')) == 'rm_ic_unpin'
                   and moved(m) == {'rm_item0': 0, 'rm_item1': 50, 'rm_hair0': 100, 'rm_item2': 100} and not m.is_visible(m.widgets['rm_hair1']),
                   f'a playlist\'s sheet: Play, Shuffle | Unpin Playlist, a hairline at 100; rows 3..4 hidden ({moved(m)})')
            m.click('rm_scrim', count=900000000)
        else:
            expect(all(m.is_shown(m.widgets[f'rm_item{i}']) for i in range(6)) and not m.is_shown(m.widgets['rm_item6'])
                   and tr(m, 'rm_label1') == 'Shuffle' and m.props.get((m.widgets['rm_icon1'], 'image')) == 'rm_ic_pshuffle'
                   and tr(m, 'rm_label2') == 'Unpin Album' and m.props.get((m.widgets['rm_icon2'], 'image')) == 'rm_ic_unpin'
                   and tr(m, 'rm_label3') == 'Add to Playlist' and m.props.get((m.widgets['rm_icon3'], 'image')) == 'rm_ic_add'
                   and tr(m, 'rm_label4') == 'Play Next' and m.props.get((m.widgets['rm_icon4'], 'image')) == 'rm_ic_next'
                   and tr(m, 'rm_label5') == 'Play After' and m.props.get((m.widgets['rm_icon5'], 'image')) == 'rm_ic_after'
                   and moved(m) == {'rm_item0': 0, 'rm_item1': 50, 'rm_hair0': 100, 'rm_item2': 100, 'rm_item3': 150, 'rm_hair1': 200, 'rm_item4': 200, 'rm_item5': 250},
                   f'an album\'s sheet restores its words: Play, Shuffle | Unpin Album, Add to Playlist | Play Next, Play After on pc_sheet6, hairlines at 100 and 200 ({moved(m)})')
            m.click('rm_scrim', count=900000000)
    # Play Next and Play After on the pinned album queue all three tracks in order and toast
    want_paths = ['/mnt/mmc/Miles Davis/Kind of Blue/1.flac', '/mnt/mmc/Miles Davis/Kind of Blue/2.flac', '/mnt/mmc/Miles Davis/Kind of Blue/3.flac']
    for item, after, toast in (('rm_item4', 0, 'Playing Next'), ('rm_item5', 1, 'Added to Queue')):
        m.up_calls = []; m.calls = []
        m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000)
        m.click(item, count=900000000)
        expect(not m.is_shown(card) and m.up_calls == [(want_paths, after)] and toasts(m) == [toast],
               f'pinned album {toast}: upnext_add gets all 3 tracks in order ({m.up_calls}, {toasts(m)})')
    # UPNEXT_STARTED: no toast; refusals: translated toast
    m.up_ret = 2; m.up_calls = []; m.calls = []
    m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000); m.click('rm_item4', count=900000000)
    expect(m.up_calls == [(want_paths, 0)] and not toasts(m), 'UPNEXT_STARTED shows no toast')
    for code, say in ((-2, 'Not available while streaming'), (-6, 'Queue is full'), (-8, 'Not available while DLNA is on')):
        m.up_ret = code; m.calls = []
        m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000); m.click('rm_item5', count=900000000)
        expect(toasts(m) == [say], f'refusal {code} toasts {say} ({toasts(m)})')
    # Add to Playlist: the picker opens for the album's tracks, every one marked; a picker that will not open says so
    m.pk_calls = []; m.calls = []
    m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000); m.click('rm_item3', count=900000000)
    expect(not m.is_shown(card) and len(m.pk_calls) == 1 and m.pk_calls[0][1] == 3 and m.pk_calls[0][2][0] & 7 == 7 and not toasts(m), f'pinned album Add to Playlist: the picker gets the 3 tracks, all marked ({m.pk_calls}, {toasts(m)})')
    m.pk_ret = -1; m.calls = []
    m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000); m.click('rm_item3', count=900000000)
    expect(toasts(m) == ['Adding Failed'], f'a picker that cannot open: Adding Failed ({toasts(m)})')
    m.pk_ret = 0
    # Album not in the library: "Not found", upnext_add and the picker not called, pin stays
    m.showlist = []; m.up_ret = 1; m.up_calls = []; m.pk_calls = []
    for item in ('rm_item4', 'rm_item3'):
        m.calls = []
        m.call(PSYMS['pn_open_sheet'], a0=2, count=900000000); m.click(item, count=900000000)
        expect(not m.up_calls and not m.pk_calls and toasts(m) == ['Not found'] and len(H.parse(m.fs[PINS])) == 3,
               f'missing album ({item}): Not found, no upnext_add, no picker, pin stays ({toasts(m)})')
    # Unpin Song (rm_item1) and Unpin Album (rm_item2)
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.click('rm_item1', count=900000000)
    expect(H.parse(m.fs[PINS]) == [ENTRIES[1], ENTRIES[0]] and not m.is_shown(card), 'Unpin Song removes the song\'s line')
    m.call(PSYMS['pn_open_sheet'], a0=1, count=900000000); m.click('rm_item2', count=900000000)
    expect(H.parse(m.fs[PINS]) == [ENTRIES[1]] and not m.is_shown(card), 'Unpin Album on slot 2 removes the album\'s line')


def recent_sheet_tests(ctx):
    """A Recently Played tile on Home held RM_LONG_MS opens the six-row album sheet (Play, Shuffle | Pin Album / Unpin Album by the pins file, Add to Playlist | Play Next, Play After) and its release opens no album; a drift, an abort or an early release cancels
    the hold; Pin Album writes the album's line (the tile's title, cover key and track path), Unpin Album removes it; Play Next / Play After queue the album via upnext_add; Play and Shuffle read the stock album list."""
    expect = ctx.expect
    RM = sibling('rowmenu')
    tiles = recent.ents(2)
    m = PH(entries=[ENTRIES[1]])
    m.fs[recent.RECENT] = recent.pod_recent.dump(tiles)
    for n in SHEET_WIDGETS: Machine.widget(m, n)
    m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
    t = tiles[1]
    tname = t[3].encode('latin-1').decode()
    tr1 = m.record(album=tname, artist='A', path='/mnt/mmc/A/t1.flac', title='T1', rid=1)
    tr2 = m.record(album=tname, artist='A', path='/mnt/mmc/A/t2.flac', title='T2', rid=2)
    m.album_tracks = {tname: [tr1, tr2]}
    m.showlist = [m.record(album=tname, artist='A', path=t[5], rid=7)]
    m.trap_upnext(1)
    recent.covered(m, 2)
    m.begin()
    m.start()
    x, y = recent.cx(1), recent.sy(60)   # the second tile's cover
    timers = lambda: [c for c in m.calls if c[0] == 'timer_add' and c[1] == PSYMS['rm_on_hold']]
    m.calls = []
    m.gesture([('d', x, y, 0)])
    expect(len(timers()) == 1 and timers()[0][2] == O['RM_LONG_MS'] and not m.is_shown(m.widgets['rm_card']), f'a press on a Recently Played tile arms the one {O["RM_LONG_MS"]} ms hold, nothing is open yet')
    m.call(PSYMS['rm_on_hold'], count=900000000)
    card = m.widgets['rm_card']
    expect(m.is_shown(card) and m.props.get((card, 'style:normal:bg_image')) == 'pc_sheet6'
           and tr(m, 'rm_label1') == 'Shuffle' and tr(m, 'rm_label4') == 'Play Next' and m.props.get((m.widgets['rm_icon4'], 'image')) == 'rm_ic_next'
           and tr(m, 'rm_label2') == 'Pin Album' and m.props.get((m.widgets['rm_icon2'], 'image')) == 'rm_ic_pin' and tr(m, 'rm_label3') == 'Add to Playlist'
           and all(m.is_shown(m.widgets[f'rm_item{i}']) for i in range(6)),
           'held: the six-row sheet opens with Play, Shuffle | Pin Album, Add to Playlist | Play Next, Play After')
    got = m.gesture([('u', x, y, 600)])
    expect(m.is_shown(card) and not [c for c in got if c[0] == 'navigator_to_with_context'] and m.opened() == [], 'the release afterwards opens no album and leaves the sheet open')
    m.u.mem_write(m.pins + 0xc, struct.pack('<i', 0))   # a stale height: only a redone section is 130 again
    m.click('rm_item2', count=900000000)
    want = H.parse(m.fs.get(PINS, b''))
    expect(m.s32(m.pins + 0xc) == 130 and m.is_shown(m.pins), 'Pin Album redoes the section at once (Home stays in front: no to-foreground does it)')
    expect(not m.is_shown(card) and want[-1][0] == 'a' and want[-1][3] == t[3] and want[-1][1] == H.identity(tname) and want[-1][2][0] == t[1] and want[-1][4] == t[5] and len(want) == 2,
           f'Pin Album writes the tile\'s album (title, cover key, track path) at the end and closes the sheet ({want})')
    m.gesture([('d', x, y, 1000)]); m.call(PSYMS['rm_on_hold'], count=900000000)
    expect(tr(m, 'rm_label2') == 'Unpin Album' and m.props.get((m.widgets['rm_icon2'], 'image')) == 'rm_ic_unpin', 'a pinned album reads Unpin Album with the pin-off glyph')
    m.gesture([('u', x, y, 600)])
    m.u.mem_write(m.pins + 0xc, struct.pack('<i', 0))
    m.click('rm_item2', count=900000000)
    expect([e[3] for e in H.parse(m.fs.get(PINS, b''))] == [ENTRIES[1][3]] and m.s32(m.pins + 0xc) == 130, 'Unpin Album removes the line and redoes the section')
    for item, after, toast in (('rm_item4', 0, 'Playing Next'), ('rm_item5', 1, 'Added to Queue')):
        m.gesture([('d', x, y, 1000)]); m.call(PSYMS['rm_on_hold'], count=900000000); m.gesture([('u', x, y, 600)])
        m.up_calls = []; m.calls = []
        m.click(item, count=900000000)
        expect(not m.is_shown(card) and m.up_calls == [(['/mnt/mmc/A/t1.flac', '/mnt/mmc/A/t2.flac'], after)] and toasts(m) == [toast],
               f'Recently Played {toast}: queues both tracks in order ({m.up_calls}, {toasts(m)})')
    for item, name in (('rm_item0', 'Play'), ('rm_item1', 'Shuffle')):
        m.gesture([('d', x, y, 1000)]); m.call(PSYMS['rm_on_hold'], count=900000000); m.gesture([('u', x, y, 600)])
        m.calls = []
        m.click(item, count=900000000)
        expect(not m.is_shown(card) and 'loadAlbumList' in [c[0] for c in m.calls], f'{name} closes the sheet and reads the stock album list')
    # cancelled: a drift, an abort, an early release (the tap still opens the album)
    m.gesture([('d', x, y, 1000)]); m.calls = []
    m.gesture([('m', x + 20, y, 100)])
    expect(any(c[0] == 'timer_remove' for c in m.calls), 'a drift of 20 px stops the hold')
    m.gesture([('a', x, y)]); m.calls = []
    m.gesture([('d', x, y, 1000), ('a', x, y)])
    expect(any(c[0] == 'timer_remove' for c in m.calls) and not m.is_shown(card), 'an abort stops the hold')
    m.calls = []
    m.gesture([('d', x, y, 1000), ('u', x, y, 60)])
    expect(any(c[0] == 'timer_remove' for c in m.calls) and not m.is_shown(card), 'a release before the time stops the hold and opens no sheet')


def reorder_tests(ctx):
    """Hold and drag on Home (patch/pins.c pn_on_hold / pn_follow / pn_drop_lift / pn_commit): the held tile lifts (the touch grabbed, the list's yslidable off); released where it was it opens the sheet; dragged SC_DRAG_PX it
    reorders (the others close up around the slot under it) and the release saves the order; a quick drag is the list's; an abort, a release outside or a failed save change nothing; yslidable is always back."""
    expect = ctx.expect
    RM = sibling('rowmenu')
    n = 4

    def mk(fail=False):
        m = PH(entries=ENTRIES[:n])
        for nm in SHEET_WIDGETS: Machine.widget(m, nm)
        m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
        m.begin()
        if fail: m.fail.add(('rename', PINS))
        return m

    def at(m, i, dx=0, dy=0):
        """The window point on tile i's cover (its centre, moved by dx, dy)."""
        return (pod_ui.pin_x(i, n) + O['PIN_COVER'] // 2 + dx, O['HOME_PAD'] + m.y_of(m.pins) - m.yoff() + O['PIN_TOP'] + i // O['PIN_COLS'] * O['PIN_PITCH'] + O['PIN_COVER'] // 2 + dy)

    def hold(m, i):
        m.gesture([('d', *at(m, i), 0)])
        m.calls = []
        m.call(PSYMS['rm_on_hold'], count=900000000)
        return m.calls

    grabbed = lambda m: m.word(m.sv + 0x4c) == m.pins   # widget_t.grab (@0x4c): stock's widget_grab / widget_ungrab run for real (a grab is refused when the widget has another)
    slide = lambda m: m.props.get((m.sv, 'yslidable'))
    order = lambda m: [e[1] for e in H.parse(m.fs[PINS])]
    keys = [e[1] for e in ENTRIES[:n]]
    vis = lambda m, nm: m.is_visible(m.widgets[nm])
    sens = lambda m, nm: bool(m.flags(m.widgets[nm]) & 8)   # the sensitive bit (is_shown = visible and sensitive)
    relaid = lambda m: m.u.mem_write(m.sv + 0x91, bytes([1]))   # the device's next frame after the sheet shows or hides: widget_set_visible marks the window for layout and stock's list_view layouter sets yslidable again (scroll_view_set_yslidable(sv, 1) @0x60b1e4; the machine's list has no scroll bar, so its layout does not)

    # held and released where it was: the lift, then the sheet
    m = mk()
    got = hold(m, 1)
    card = m.widgets['rm_card']
    label = tr(m, 'rm_label2')
    expect(grabbed(m) and slide(m) == 0 and vis(m, 'rm_card') and vis(m, 'rm_scrim'), 'the hold lifts the tile and opens the sheet at once: the touch is grabbed, the list\'s yslidable is off')
    expect([m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [0, 1, 2, 3], 'lifted, not dragged: every tile is in its own slot')
    got = m.gesture([('m', *at(m, 1, 4, 3), 20), ('u', *at(m, 1, 4, 3), 30)])
    expect(m.is_shown(card) and label == 'Unpin Playlist' and not grabbed(m) and slide(m) == 1 and order(m) == keys and not [c for c in got if c[0] == 'navigator_to_with_context'],
           'released within SC_DRAG_PX: the sheet stays open (tile 1, a playlist: Unpin Playlist), the grab and the sliding are given back, the file and the order are as they were, nothing opens')
    m.click('rm_item2', count=900000000)
    expect(not m.is_shown(card) and order(m) == [k for k in keys if k != keys[1]], 'after the release a sheet row still works (Unpin)')
    m = mk(); hold(m, 1)
    m.gesture([('m', *at(m, 1, 0, 40), 20)])
    expect(not vis(m, 'rm_card') and not sens(m, 'rm_scrim') and not sens(m, 'rm_card') and slide(m) == 0 and grabbed(m), 'a drag closes the sheet; the scrim and card are hidden and insensitive')
    # the layout that follows the sheet (shown at the hold, hidden at the drag) turns the list's sliding back on: the list still never moves, during the drag or at the release
    for dy in (-60, 60, 120):
        m = mk(); m.setword(m.sv + 0x84, 0); hold(m, 1); relaid(m)
        ys = []
        for k in range(1, 5):
            m.gesture([('m', *at(m, 1, 0, dy * k // 4), 20)]); ys.append(m.yoff()); relaid(m)
        m.gesture([('m', *at(m, 1, 0, dy), 20), ('u', *at(m, 1, 0, dy), 20)])
        expect(ys == [0] * 4 and m.yoff() == 0 and not m.wa() and not m.anims and slide(m) == 1 and not grabbed(m),
               f'yslidable set again by the layout, dragged {dy} px: the list does not scroll with the finger and does not fling at the release ({ys}, {m.yoff()}, animator {m.wa():#x})')
    m = mk(); m.setword(m.sv + 0x84, 0); hold(m, 0); relaid(m)
    m.gesture([('u', *at(m, 3), 30)])
    expect(order(m) == [keys[1], keys[2], keys[3], keys[0]] and m.yoff() == 0 and not m.wa() and not m.is_shown(m.widgets['rm_card']),
           f'held, the layout ran, released a row below with no move event: the list hook sends no abort, the pin drops there ({order(m)})')
    m = mk(); hold(m, 1)
    m.gesture([('a', *at(m, 1))])
    expect(not vis(m, 'rm_card') and not vis(m, 'rm_scrim') and not grabbed(m) and slide(m) == 1 and order(m) == keys, 'an abort after the hold (before any drag) closes the sheet too')
    m = mk(); hold(m, 1)
    m.call(PSYMS['pn_on_background'], a0=m.root, a1=0, count=8000000)
    expect(not vis(m, 'rm_card') and not sens(m, 'rm_scrim'), 'the window going to the background closes the sheet, nothing left sensitive')
    m = mk(); hold(m, 1); m.gesture([('u', *at(m, 1), 30)]); m.click('rm_scrim', count=900000000)
    expect(not m.is_shown(m.widgets['rm_card']) and order(m) == keys, 'after the release a scrim tap closes the sheet')
    # the release reports the displacement alone (no move event): a drag, not a hold on the wrong tile
    m = mk(); hold(m, 0)
    m.gesture([('u', *at(m, 1), 30)])
    expect(not m.is_shown(m.widgets['rm_card']) and order(m) == [keys[1], keys[0], keys[2], keys[3]] and slide(m) == 1 and not grabbed(m),
           'held on tile 0, released over tile 1 with no move event: the sheet closes, the pin moves to slot 1')

    # held, dragged to the last slot, released: reordered and saved
    m = mk()
    hold(m, 0)
    m.gesture([('m', *at(m, 0, 30, 0), 20), ('m', *at(m, 3), 20)])
    expect(not m.is_shown(m.widgets['rm_card']) and slide(m) == 0 and [m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [1, 2, 3, 0],
           'dragging: the sheet closed, the list still off, the other tiles close up (slots 0..3 show tiles 1, 2, 3 and the lifted one)')
    m.gesture([('m', *at(m, 2), 20)])
    expect([m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [1, 2, 0, 3], 'over slot 2 they reflow live: 1, 2, lifted, 3')
    m.calls = []
    got = m.gesture([('m', *at(m, 3), 20), ('u', *at(m, 3), 30)])
    expect(order(m) == [e[1] for e in H.move(ENTRIES[:n], 0, 3)] and PINS_TMP not in m.fs and not m.is_shown(m.widgets['rm_card']) and slide(m) == 1 and not grabbed(m)
           and [m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [0, 1, 2, 3], f'the release saves the new order (atomically), no sheet, the list slides again ({order(m)})')
    hold(m, 3)
    m.gesture([('m', *at(m, 3, 0, 0), 20), ('m', *at(m, 0), 20), ('u', *at(m, 0), 30)])
    expect(order(m) == [keys[0], keys[1], keys[2], keys[3]], 'dragged back to the first slot: the order is the original again')
    # a point beyond the grid is its nearest cell (clamped to the pins there are); a drag that ends on its own slot writes nothing
    m = mk(); hold(m, 0)
    m.gesture([('m', *at(m, 3, 60, 0), 20), ('u', *at(m, 3, 60, 0), 30)])
    expect(order(m) == [keys[1], keys[2], keys[3], keys[0]], 'right of the last tile: the last slot')
    m = mk(); before = m.fs[PINS]; hold(m, 1); m.calls = []
    m.gesture([('m', *at(m, 1, 25, 5), 20), ('u', *at(m, 1, 25, 5), 30)])
    expect(m.fs[PINS] == before and not [c for c in m.calls if c[0] == 'rename'] and not m.is_shown(m.widgets['rm_card']) and slide(m) == 1, 'dragged but dropped on its own slot: nothing is written, no sheet')

    # a quick drag never lifts: the hold is cancelled and the list scrolls
    m = mk(); before = m.fs[PINS]
    m.gesture([('d', *at(m, 0), 0)]); m.calls = []
    m.gesture([('m', *at(m, 0, 0, 30), 20)])
    expect(any(c[0] == 'timer_remove' for c in m.calls_all), 'a move of 30 px before the hold stops it')
    m.gesture([('u', *at(m, 0, 0, 30), 30)])
    expect(m.fs[PINS] == before and not grabbed(m) and slide(m) in (None, 1) and not m.is_shown(m.widgets['rm_card']), 'no lift, no grab, the list untouched, no reorder, no sheet')

    # abort / release outside / failed save: the old order, the list slides again
    m = mk(); before = m.fs[PINS]; hold(m, 0)
    m.gesture([('m', *at(m, 0, 20, 0), 20), ('m', *at(m, 3), 20)])
    got = m.gesture([('a', *at(m, 3))])
    expect(m.fs[PINS] == before and slide(m) == 1 and not grabbed(m) and not m.is_shown(m.widgets['rm_card'])
           and [m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [0, 1, 2, 3], 'an abort mid-drag: the old order, nothing saved, the touch and the sliding given back')
    m = mk(); before = m.fs[PINS]; hold(m, 0)
    m.gesture([('m', *at(m, 0, 20, 0), 20), ('m', *at(m, 3), 20), ('u', *at(m, 3, 0, 300), 30)])
    expect(m.fs[PINS] == before and slide(m) == 1, 'released far below the section: cancelled, nothing saved')
    m = mk(fail=True); before = m.fs[PINS]; hold(m, 0)
    m.gesture([('m', *at(m, 0, 20, 0), 20), ('m', *at(m, 3), 20), ('u', *at(m, 3), 30)])
    expect(m.fs[PINS] == before and PINS_TMP not in m.fs and slide(m) == 1 and [m.call(PSYMS['pn_tile_in'], a0=p, count=100000) for p in range(n)] == [0, 1, 2, 3], 'a failed save leaves the file and the order as they were')
    m = mk(); hold(m, 0)
    m.call(PSYMS['pn_on_background'], a0=m.root, a1=0, count=8000000)
    expect(slide(m) == 1 and not grabbed(m), 'the window going to the background ends a lift')
    m = mk(); hold(m, 0)
    m.call(PSYMS['pn_on_destroy'], a0=m.root, a1=0, count=8000000)
    expect(slide(m) == 1, 'the window\'s end gives the sliding back')



ARTISTS = ('Miles Davis', 'Nina Simone', 'The Beatles')


def artist_tests(ctx):
    """Artist pins (kind r): the model, the calls (identity by name, the photo's cache key, no path), the circle tiles (photo, or the Artists page's placeholder, corners black), a tap opens the artist's Albums page, the sheet
    (Play, Shuffle, Unpin Artist), and the library check."""
    expect = ctx.expect
    A = sibling('artists')
    RM = sibling('rowmenu')
    me, ns, bt = (artist(n) for n in ARTISTS)
    pin_a = lambda m, n: struct.unpack('<i', struct.pack('<I', m.call(PSYMS['pins_pin_artist'], a0=m.cstr(n), count=4000000)))[0]
    has_a = lambda m, n: m.call(PSYMS['pins_has_artist'], a0=m.cstr(n), count=4000000)
    expect(H.parse(H.dump([me, ENTRIES[0], bt])) == [me, ENTRIES[0], bt] and me[2][0] == A.ap_key('Miles Davis') and bt[2][0] == A.ap_key('Beatles') and me[2][0] != ns[2][0], 'the model round-trips artists; the cover key is the photo cache key (The and case folded)')
    # ---- the calls
    m = machine()
    expect(has_a(m, 'Miles Davis') == 0 and pin_a(m, 'Miles Davis') == 0 and H.parse(m.fs[PINS]) == [me] and PINS_TMP not in m.fs, 'Pin Artist writes the artist\'s line (name key, photo key, name, the list it was pinned from)')
    expect(has_a(m, 'MILES DAVIS') == 1 and has_a(m, 'Nina Simone') == 0, 'an artist is its name, ASCII case aside')
    before = m.fs[PINS]
    expect(pin_a(m, 'Miles Davis') == 0 and m.fs[PINS] == before, 'pinning a pinned artist changes nothing')
    expect(pin_a(m, '') == -2 and pin_a(m, '   ') == -2 and pin_a(m, 'x' * 96) == -2 and pin_a(m, 'x' * 95) == 0, 'a blank name or one too long for the file pins nothing (PINS_FAIL)')
    expect(pin_album(m, ENTRIES[0]) == 0 and pin_a(m, 'The Beatles') == 0 and [e[0] for e in H.parse(m.fs[PINS])] == ['r', 'r', 'a', 'r'], 'artists join the end among the others')
    expect(m.call(PSYMS['pins_unpin_artist'], a0=m.cstr('miles davis'), count=4000000) == 1 and m.call(PSYMS['pins_unpin_artist'], a0=m.cstr('miles davis'), count=4000000) == 0 and not H.has(H.parse(m.fs[PINS]), 'r', me[1]), 'unpin: 1 once, then 0')
    m = machine(H.dump(ENTRIES)); m.calls = []
    expect(pin_a(m, 'Nina Simone') == -1 and toasts(m) == ['Unpin an item first'], 'a seventh pin is refused with the toast')

    # ---- the tiles: a photo as a circle, else the Artists page's placeholder circle, both cut in the alpha (transparent corners: a lifted tile drawn over its neighbours shows no black)
    def mk(entries, photos=('Miles Davis',), library=ARTISTS):
        m = PH(entries=entries)
        for n in SHEET_WIDGETS: Machine.widget(m, n)
        m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
        A.seed_photos(m, photos, color=(200, 40, 40))
        m.showlist = [m.record(title=n, artist=n, rid=i + 1) for i, n in enumerate(library)]
        m.begin()
        return m

    def decode(m):
        m.call(PSYMS['pn_first'], count=40000000)
        n = 0
        while m.call(PSYMS['pn_tick'], a0=0, count=40000000) == O['RET_REPEAT'] and n < 12: n += 1

    def paint(m):
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        m.blits.clear()
        m.call(PSYMS['pn_on_paint'], a0=0, a1=e, count=40000000)
        return [b for b in m.blits if b[2][2:] == (90, 90)]

    px = lambda m, bmp, x, y: A.bmp_px(m, bmp, x, y)
    m = mk([me, ENTRIES[0], ns])
    decode(m)
    tiles = paint(m)
    expect(len(tiles) == 3, f'three tiles are painted ({len(tiles)})')
    a, b, c = tiles
    expect(px(m, a[0], 0, 0) >> 24 == 0 and px(m, a[0], 89, 89) >> 24 == 0 and px(m, a[0], 45, 45) >> 24 == 255 and abs((px(m, a[0], 45, 45) & 255) - 200) <= 3 and px(m, a[0], 45, 1) & 0xffffff != 0,
           f'the photo is cut to a circle: transparent corners, the red picture inside ({px(m, a[0], 0, 0):#x}, {px(m, a[0], 45, 45):#x})')
    expect(px(m, c[0], 45, 8) == 0xff333333 and px(m, c[0], 1, 1) >> 24 == 0, f'no photo: the Artists page\'s #333333 circle placeholder with transparent corners ({px(m, c[0], 45, 8):#x})')
    expect(px(m, b[0], 0, 0) >> 24 == 0 and px(m, b[0], 45, 45) >> 24 == 255 and px(m, b[0], 45, 45) != px(m, a[0], 45, 45), 'an album tile beside them keeps its rounded square, its corners cut in the alpha too')
    # the photo arrives later: the to-foreground looks again and the tile becomes the picture
    A.seed_photos(m, ('Nina Simone',), color=(40, 200, 90))
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    decode(m)
    c = paint(m)[2]
    expect(px(m, c[0], 45, 45) >> 8 & 255 > 180 and px(m, c[0], 0, 0) >> 24 == 0, 'a photo that appears while the menu is behind replaces the placeholder at the next to-foreground')

    # ---- tap: the artist's Albums page (as the Artists row); an artist the library does not list says "Not found" and the pin stays
    def tap(m, i, n=2):
        """A tap on tile i's cover (the first row of n tiles); the calls of the pages it asked for."""
        x, y = pod_ui.pin_x(i, n) + O['PIN_COVER'] // 2, O['HOME_PAD'] + m.y_of(m.pins) - m.yoff() + O['PIN_TOP'] + O['PIN_COVER'] // 2
        m.calls_all.clear()
        m.gesture([('d', x, y, 0), ('u', x, y, 60)])
        return [c for c in m.calls_all if c[0] in ('albums_open_artist', 'coverflow_artist')]

    m = mk([me, ns])
    got = tap(m, 1)
    expect(got == [('albums_open_artist', ('Nina Simone',), 0, 0xf004)], f'a tap opens the artist\'s Albums page on its row, class artists ({got})')
    m.ret['albums_open_artist'] = -1
    expect([c[0] for c in tap(m, 0)] == ['albums_open_artist', 'coverflow_artist'], 'a window that will not open falls back to Cover Flow, as the Artists page does')
    m = mk([me, ns], library=('Nina Simone',))
    m.calls = []
    expect(not tap(m, 0) and [e[3] for e in H.parse(m.fs[PINS])] == ['Miles Davis', 'Nina Simone'] and toasts(m) == ['Not found'], 'an artist the library does not list opens nothing, says Not found and keeps the pin')
    m = mk([me, ns], library=())
    tap(m, 0)
    expect(len(H.parse(m.fs[PINS])) == 2, 'an empty or failed artist list tells nothing: the pin stays')

    # ---- the sheet: Play, Shuffle, Unpin Artist
    m = mk([me, ns])
    m.call(PSYMS['pn_open_sheet'], a0=1, count=900000000)
    card = m.widgets['rm_card']
    expect(m.is_shown(card) and tr(m, 'rm_label2') == 'Unpin Artist' and tr(m, 'rm_label1') == 'Shuffle' and m.props.get((card, 'style:normal:bg_image')) == 'pc_sheet3', 'the sheet: Play, Shuffle, Unpin Artist on the three-row glass')
    m.calls = []; m.click('rm_item1', count=900000000)
    got = [c for c in m.calls if c[0] == 'songs_play_artist']
    expect(got == [('songs_play_artist', ('Nina Simone',), 0xf004, 2)] and not m.is_shown(card), f'Shuffle plays all the artist\'s songs in the shuffle mode ({got})')
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.calls = []; m.click('rm_item0', count=900000000)
    expect([c[1:] for c in m.calls if c[0] == 'songs_play_artist'] == [(('Miles Davis',), 0xf004, 1)], 'Play plays them in order')
    m.ret['songs_play_artist'] = -1; m.calls = []; m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.click('rm_item0', count=900000000)
    expect(toasts(m) == ["Can't play"], 'nothing to play: the toast')
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.click('rm_item2', count=900000000)
    expect([e[3] for e in H.parse(m.fs[PINS])] == ['Nina Simone'], 'Unpin Artist removes the line')

    # ---- the library check never drops an artist, even one a non-empty list lacks (a library mid-scan lists fewer)
    for why, rows in (('a short list', ['Nina Simone']), ('an empty list', [])):
        m = PH(entries=[me, ns, bt]); m.showlist = [m.record(title=n, rid=i + 1) for i, n in enumerate(rows)]; m.begin()
        m.clock = O['PIN_CHECK_MS'] + 1000
        m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
        expect(m.fs[PINS] == H.dump([me, ns, bt]), f'the check keeps every artist pin ({why})')


def tap_tile(m, i, n=2):
    """A tap on tile i's cover (the first row of n tiles); the calls it made."""
    x, y = pod_ui.pin_x(i, n) + O['PIN_COVER'] // 2, O['HOME_PAD'] + m.y_of(m.pins) - m.yoff() + O['PIN_TOP'] + O['PIN_COVER'] // 2
    m.calls_all.clear()
    m.gesture([('d', x, y, 0), ('u', x, y, 60)])
    return list(m.calls_all)


def read_error_tests(ctx):
    """A file that cannot be read is never overwritten: an open or read error, or a list the payload does not understand, makes a pin, an unpin, a reorder, the library check and a drop leave it alone (a missing file or an empty one is no pins);
    a song file that fails to open for a reason other than 'not there' keeps its pin."""
    expect = ctx.expect
    good = H.dump(ENTRIES[:3])
    unpin_a = lambda m, name: m.call(PSYMS['pins_unpin_album'], a0=m.cstr(name), count=4000000)
    for why, setup in (('open error (EIO)', lambda m: m.fail.add(('open', PINS))), ('read error', lambda m: m.fail.add(('read', PINS)))):
        m = machine(good); setup(m); m.calls = []
        expect(pin_album(m, ENTRIES[4]) == -2 and m.fs[PINS] == good and toasts(m) == ["Can't update pins"] and PINS_TMP not in m.fs, f'{why}: Pin Album answers PINS_FAIL, says so and leaves the file ({toasts(m)})')
        m.calls = []
        expect(pin_playlist(m, ENTRIES[3], (44,)) == -2 and pin_song(m, '/mnt/mmc/a.flac') == -2 and m.fs[PINS] == good, f'{why}: a playlist and a song are refused the same way')
        expect(unpin_a(m, 'Homogenic') == 0 and m.fs[PINS] == good and m.call(PSYMS['pins_unpin_playlist'], a0=3, a1=m.cstr('Late Night Jazz'), count=4000000) == 0, f'{why}: Unpin removes nothing and writes nothing')
        m.fail.clear()
        expect(pin_album(m, ENTRIES[4]) == 0 and m.fs[PINS] == H.dump(ENTRIES[:3] + [ENTRIES[4]]), f'{why}: once the card reads again the pin goes in at the end of the list as it was')
    m = machine(good); m.begin = None
    for why, bad in (('junk', b'junk'), ('a later version\'s kind', good.replace(b'a\t', b'z\t', 1)), ('seven pins', H.MAGIC + b''.join(H.dump([album(f'A{i}')])[5:] for i in range(7))),
                     ('cut short', good[:-9]), ('too big', good + b'\n' * 4000), ('3 bytes', b'M1P')):
        m = machine(bad); m.calls = []
        expect(pin_album(m, ENTRIES[4]) == -2 and m.fs[PINS] == bad and toasts(m) == ["Can't update pins"] and unpin_a(m, 'Homogenic') == 0 and m.fs[PINS] == bad,
               f'a file that is {why} is not replaced by a pin or an unpin: it is the user\'s to delete')
    for why, data in (('empty', b''), ('absent', None)):
        m = machine(data)
        expect(pin_album(m, ENTRIES[0]) == 0 and H.parse(m.fs[PINS]) == ENTRIES[:1], f'a file that is {why} is no pins: the first pin writes the list')
    # the section's own writes: a reorder commit and the library check
    m = PH(entries=ENTRIES[:3]); m.begin()
    m.fail.add(('open', PINS))
    pt = lambda i, dx=0: (pod_ui.pin_x(i, 3) + O['PIN_COVER'] // 2 + dx, O['HOME_PAD'] + m.y_of(m.pins) - m.yoff() + O['PIN_TOP'] + O['PIN_COVER'] // 2)
    m.gesture([('d', *pt(0), 0)]); m.call(PSYMS['rm_on_hold'], count=900000000)
    m.gesture([('m', *pt(0, 30), 20), ('m', *pt(2), 20), ('u', *pt(2), 30)])
    expect(m.fs[PINS] == H.dump(ENTRIES[:3]), 'a drop to reorder while the file cannot be read writes nothing')
    m = PH(entries=ENTRIES[:3]); m.showlist = [m.record(album='Nothing', artist='Else', rid=3)]; m.begin()
    m.clock = O['PIN_CHECK_MS'] + 1000; m.fail.add(('open', PINS))
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    expect(m.fs[PINS] == H.dump(ENTRIES[:3]), 'the library check on a file that cannot be read writes nothing')
    m.fail.clear(); m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    expect(m.fs[PINS] == H.dump(ENTRIES[:3]), 'and it runs at the next to-foreground: the albums the library lacks stay')
    # a tap on a song never drops its pin: a file that is gone says File not found, one that fails to open otherwise Can't play
    S = song('/mnt/mmc/Artist/Album/01 Track.flac', 'Track', 'Artist', 'Album')
    path = '/mnt/mmc/Artist/Album/01 Track.flac'
    for why, fail, say in (('EIO', True, "Can't play"), ('not there', False, 'File not found')):
        m = PH(entries=[S, ENTRIES[0]]); m.present.add('/tmp/mmc_add')   # (the card is in: so_card)
        if fail: m.fs[path] = b'x'; m.fail.add(('open', path))
        m.begin(); m.calls = []
        tap_tile(m, 0)
        expect([e[0] for e in H.parse(m.fs[PINS])] == ['s', 'a'] and toasts(m) == [say], f'a song file that fails to open ({why}) keeps its pin on a tap and says {say} ({toasts(m)})')
    m = PH(entries=[S, ENTRIES[0]]); m.present.add('/tmp/mmc_add'); m.fs[path] = b'x'; m.fail.add(('open', path)); m.showlist = [m.record(album='Kind of Blue', artist='Miles Davis', path='/mnt/mmc/Miles Davis/Kind of Blue/1.flac', rid=2)]; m.begin()
    m.clock = O['PIN_CHECK_MS'] + 1000; m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    expect([e[0] for e in H.parse(m.fs[PINS])] == ['s', 'a'], 'the library check keeps a song whose file fails to open for another reason than "not there"')


def artist_scope_tests(ctx):
    """An artist pin remembers the list it was made from (Artists or Album Artists) and is looked for and played there: a guest artist pinned in Artists is not dropped while Album Artists is shown; an old line (no scope) tries the shown list, then the other."""
    expect = ctx.expect
    AT = pod.DATA['ARTIST_TYPE'][0]
    pin_a = lambda m, n: struct.unpack('<i', struct.pack('<I', m.call(PSYMS['pins_pin_artist'], a0=m.cstr(n), count=4000000)))[0]
    expect(H.parse(H.dump([artist('A', ''), artist('B', '0'), artist('C', '1')])) != [] and H.parse(H.dump([artist('A', '2')])) == [], 'the model reads an old line (no scope), "0" and "1"; any other scope is malformed')
    m = machine(); pin_a(m, 'Miles Davis')
    expect(H.parse(m.fs[PINS]) == [artist('Miles Davis', '0')], 'Pin Artist while Artists is shown writes scope 0')
    m = machine(); m.setword(AT, 1); pin_a(m, 'Miles Davis')
    expect(H.parse(m.fs[PINS]) == [artist('Miles Davis', '1')], 'while Album Artists is shown, scope 1')

    class PHS(PH):
        """The stock deque's copy (_deque_push_back copies the record and strdups its strings: Split Artists' first-name row is built on the stack)."""
        def _hook(self, u, address, size, _):
            if self.handlers.get(address, '') == '_deque_push_back':
                a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
                rec = bytearray(bytes(u.mem_read(a1, 0x58)))
                for off in range(4, 0x30, 4):
                    q = struct.unpack_from('<I', rec, off)[0]
                    if q:
                        t = self.read_cstr(q).encode('latin-1'); a = self.malloc(len(t) + 1)
                        u.mem_write(a, t + b'\0'); struct.pack_into('<I', rec, off, a)
                c = self.malloc(0x58); u.mem_write(c, bytes(rec))
                self.deques.setdefault(a0, []).append(c); self.calls.append(('_deque_push_back', a0, c))
                u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            return super()._hook(u, address, size, _)

    def mk(entries, artists_list, album_artists, type_=0, cls=PH):
        m = cls(entries=entries)
        for n in SHEET_WIDGETS: Machine.widget(m, n)
        RM = sibling('rowmenu'); m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
        m.showlist = [m.record(title=n, artist=n, rid=i + 1) for i, n in enumerate(artists_list)]
        m.album_artists = [m.record(title=n, artist=n, rid=i + 1) for i, n in enumerate(album_artists)]
        m.setword(AT, type_)
        m.begin()
        return m

    guest = artist('Guest', '0')
    # Album Artists is shown; the guest is an Artist only
    m = mk([guest, artist('Host', '1')], ('Guest', 'Host'), ('Host',), 1)
    got = [c for c in tap_tile(m, 0) if c[0] in ('albums_open_artist', 'coverflow_artist', 'write_int_config')]
    expect(('albums_open_artist', ('Guest',), 0, 0xf004) in got and m.word(AT) == 0 and ('write_int_config', 0, 'PLAYSET', 'ARTISTTYPE') in got and len(H.parse(m.fs[PINS])) == 2,
           f'a tap on a guest pinned in Artists opens it with Artists as the list (saved, as the Show group does), and the pin stays ({got}, {m.word(AT)})')
    m = mk([guest, artist('Host', '1')], ('Guest', 'Host'), ('Host',), 0)
    got = [c for c in tap_tile(m, 1) if c[0] in ('albums_open_artist', 'coverflow_artist', 'write_int_config')]
    expect(('albums_open_artist', ('Host',), 0, 0xf004) in got and m.word(AT) == 1 and ('write_int_config', 1, 'PLAYSET', 'ARTISTTYPE') in got, f'and the other way: a pin from Album Artists opens in it ({got})')
    m = mk([guest, artist('Host', '0')], ('Guest', 'Host'), ('Host',), 0)
    tap_tile(m, 0)
    expect(m.word(AT) == 0 and not [c for c in m.calls_all if c[0] == 'write_int_config'], 'a pin from the list shown changes no setting')
    # Play and Shuffle read the pinned list and give the setting back
    m = mk([guest, artist('Host', '1')], ('Guest', 'Host'), ('Host',), 1)
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.calls = []; m.click('rm_item0', count=900000000)
    expect([c[1:] for c in m.calls if c[0] == 'songs_play_artist'] == [(('Guest',), 0xf004, 1)] and m.type_seen == [0] and m.word(AT) == 1 and len(H.parse(m.fs[PINS])) == 2,
           f'Play reads the guest in the Artists list and puts Album Artists back ({m.type_seen}, {m.word(AT)})')
    # the library check never drops an artist pin, in any list
    for why, entries, lists, type_, left in (
            ('a guest pinned in Artists, Album Artists shown', [guest], (('Guest',), ('Host',)), 1, 1),
            ('a pin from Album Artists, Artists shown', [artist('Host', '1')], (('Guest',), ('Host',)), 0, 1),
            ('an artist in neither list', [artist('Gone', '0'), artist('Host', '1')], (('Guest',), ('Host',)), 1, 1),
            ('an old line found in the other list', [artist('Host', '')], (('Guest',), ('Host',)), 0, 1),
            ('an old line found in neither', [artist('Gone', '')], (('Guest',), ('Host',)), 0, 0)):
        m = PH(entries=entries); m.showlist = [m.record(title=n, rid=i + 1) for i, n in enumerate(lists[0])]; m.album_artists = [m.record(title=n, rid=i + 1) for i, n in enumerate(lists[1])]
        m.setword(AT, type_); m.begin(); m.clock = O['PIN_CHECK_MS'] + 1000
        m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
        got = H.parse(m.fs[PINS])
        want = [e[3] for e in entries]
        expect([e[3] for e in got] == want, f'check, {why}: {[e[3] for e in got]}')
        expect(m.word(AT) == type_, f'check, {why}: the stock artist_type is as it was ({m.word(AT)})')

    # Split Artists off after the pin was made with it on: the unsplit list has no row "Guest". Whether or not a field credits it, a tap says Not found and the pin stays, and the check keeps it
    for why, lists in (('credited in a field', (('Lead; Guest', 'Host'), ('Host',))), ('credited, other case', (('LEAD feat. GUEST',), ())), ('credited by no one', (('Lead', 'Host'), ('Host',)))):
        m = mk([guest, artist('Host', '1')], *lists)
        got = tap_tile(m, 0)
        say = [c[1] for c in got if c[0] == 'toast']
        opened = [c for c in got if c[0] in ('albums_open_artist', 'coverflow_artist')]
        expect(len(H.parse(m.fs[PINS])) == 2 and not opened and say == ['Not found'], f'tap, {why}: the pin stays and the tap says Not found ({say}, {len(H.parse(m.fs[PINS]))})')
        m = PH(entries=[guest]); m.showlist = [m.record(title=n, rid=i + 1) for i, n in enumerate(lists[0])]; m.album_artists = [m.record(title=n, rid=i + 1) for i, n in enumerate(lists[1])]
        m.begin(); m.clock = O['PIN_CHECK_MS'] + 1000
        m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
        expect(len(H.parse(m.fs[PINS])) == 1, f'check, {why}: the pin stays')

    # Split Artists turned on after "Lead; Guest" was pinned with it off: the tile still reads "Lead; Guest", so a tap must not open Lead's albums (artists_find splits the name and takes the first one). No exact row: the pin stays and the tap says "Not found"; Play / Shuffle keep it too
    joined = artist('Lead; Guest', '0')
    m = mk([joined], ('Lead', 'Guest'), ('Lead',), cls=PHS); m.fs['/mnt/data/m1plus/library-artist-split'] = b'm23\n'
    got = tap_tile(m, 0, 1)
    expect(not [c for c in got if c[0] in ('albums_open_artist', 'coverflow_artist')] and [c[1] for c in got if c[0] == 'toast'] == ['Not found'] and len(H.parse(m.fs[PINS])) == 1,
           f'split on, pinned "Lead; Guest": a tap opens no other artist, says Not found and keeps the pin ({[c for c in got if c[0] != "toast"][:3]})')
    m = mk([joined], ('Lead', 'Guest'), ('Lead',), cls=PHS); m.fs['/mnt/data/m1plus/library-artist-split'] = b'm23\n'
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.calls = []; m.click('rm_item0', count=900000000)
    expect(not [c for c in m.calls if c[0] == 'songs_play_artist'] and len(H.parse(m.fs[PINS])) == 1, 'split on, pinned "Lead; Guest": Play plays no other artist and keeps the pin')
    m = mk([artist('Lead', '0')], ('Lead', 'Guest'), ('Lead',), cls=PHS); m.fs['/mnt/data/m1plus/library-artist-split'] = b'm23\n'
    expect(('albums_open_artist', ('Lead',), 0, 0xf004) in tap_tile(m, 0, 1), 'split on, pinned "Lead": the tap still opens Lead')


CUE_IMG = '/mnt/mmc/Album/image.flac'


def cue_and_album_tests(ctx):
    """A CUE image's tracks share one file: each is its own pin (the path and the CUE start), and a tap plays from that track. A song's album is found from its own library record, so a changed representative track or cover key
    of the album does not break it."""
    expect = ctx.expect
    # ---- the model and the calls
    expect(H.song_id(CUE_IMG, 0) == H.song_id(CUE_IMG) and H.song_id(CUE_IMG, 90000) != H.song_id(CUE_IMG) and H.song_id(CUE_IMG, 90000) != H.song_id(CUE_IMG, 180000)
           and H.split_song_path('90000@/a/b') == ('/a/b', 90000) and H.split_song_path('/a/b') == ('/a/b', 0) and H.split_song_path('09@/x') is None, 'the model: a start changes a song\'s key, none leaves it; "<start>@" before the path')
    m = machine()
    expect(pin_song(m, CUE_IMG, 'One', cue=0) == 0 and pin_song(m, CUE_IMG, 'Two', cue=90000) == 0 and pin_song(m, CUE_IMG, 'Three', cue=180000) == 0 and pin_song(m, CUE_IMG, 'Two', cue=90000) == 0,
           'three tracks of one file pin, and pinning one again changes nothing')
    got = H.parse(m.fs[PINS])
    expect(got == [song(CUE_IMG, 'One'), song(CUE_IMG, 'Two', cue=90000), song(CUE_IMG, 'Three', cue=180000)] and got[1][4] == '90000@' + CUE_IMG, f'one line each, the start before the path ({[e[4] for e in got]})')
    has = lambda p, c: m.call(PSYMS['pins_has_song'], a0=m.cstr(p), a1=c, count=4000000)
    expect(has(CUE_IMG, 0) == 1 and has(CUE_IMG, 90000) == 1 and has(CUE_IMG, 120000) == 0, 'has: by path and start')
    expect(m.call(PSYMS['pins_unpin_song'], a0=m.cstr(CUE_IMG), a1=90000, count=4000000) == 1 and [e[3] for e in H.parse(m.fs[PINS])] == ['One', 'Three'], 'unpin takes the one track and leaves the others')
    ok = lambda p, c: m.call(PSYMS['pins_song_ok'], a0=m.cstr(p), a1=c, count=4000000)
    expect(ok('/' + 'p' * 254, 0) == 1 and ok('/' + 'p' * 254, 5) == 0 and ok('/' + 'p' * 252, 5) == 1 and ok('/' + 'p' * 244, 123456789) == 1 and ok('/' + 'p' * 245, 123456789) == 0, 'the "<start>@" is part of the path field\'s 255 bytes')

    # ---- play: the album from that track
    def lib(m, rep_path, rep_artist):
        t = [m.record(album='Album', artist='Y', path=CUE_IMG, title=n, name='image.flac', rid=i + 1) for i, n in enumerate(('One', 'Two', 'Three'))]
        for r, c in zip(t, (0, 90000, 180000)): m.setword(r + O['REC_CUE_START'], c)
        s1 = m.record(album='Album', artist='Y', path='/mnt/mmc/Album/04.flac', title='Four', rid=4)
        m.album_tracks = {'Album': t + [s1]}
        m.class_lists[0xf001] = t + [s1]
        m.class_lists[O['CLASS_ALBUMS']] = m.showlist = [m.record(album='Album', artist=rep_artist, path=rep_path, rid=9)]
        m.fs[CUE_IMG] = m.fs['/mnt/mmc/Album/04.flac'] = b'x'

    for cue, at in ((0, 0), (90000, 1), (180000, 2)):
        m = PH(entries=[song(CUE_IMG, 'T', 'Y', 'Album', cue)]); lib(m, CUE_IMG, 'Y'); m.begin()
        tap_tile(m, 0, 1)
        expect(m.plays and m.plays[-1][2] == at and len(m.plays[-1][1]) == 4, f'a tap on the CUE track at {cue} plays the album from track {at} ({m.plays[-1:] and m.plays[-1][2]})')
    # the album's representative track and cover key changed since the pin: the song's own record still names its album
    m = PH(entries=[song('/mnt/mmc/Album/04.flac', 'Four', 'X', 'Album')]); lib(m, '/mnt/mmc/Other/1.flac', 'Z'); m.begin()
    calls = tap_tile(m, 0, 1)
    expect(m.plays and m.plays[-1][2] == 3 and not [c for c in calls if c[0] == 'toast'], f'the album\'s row has another cover key and representative path: the song still plays its album from its track ({m.plays[-1:] and m.plays[-1][2]}, {[c for c in calls if c[0] == "toast"]})')
    m = PH(entries=[song('/mnt/mmc/Album/04.flac', 'Four', 'X', 'Album')]); lib(m, '/mnt/mmc/Other/1.flac', 'Z'); m.class_lists[0xf001] = []; m.begin()
    calls = tap_tile(m, 0, 1)
    expect(not m.plays and [c[1] for c in calls if c[0] == 'toast'] == ["Can't play"], 'a song the library has no record of, and no album found by key or path, is "Can\'t play"')
    m = PH(entries=[song('/mnt/mmc/Album/04.flac', 'Four', 'X', 'Album')]); lib(m, '/mnt/mmc/Album/04.flac', 'Z'); m.class_lists[0xf001] = []; m.begin()
    tap_tile(m, 0, 1)
    expect(m.plays and m.plays[-1][2] == 3, 'no record of the song: the album\'s representative track path still finds it as before')

    # ---- a long album tag compares whole (a 96 byte title used to be cut to 95 and match nothing); an untagged song's album is the Unknown Album row
    P4 = '/mnt/mmc/Album/04.flac'

    def lib2(m, tag, rows):
        t = m.record(album=tag, artist='Y', path=P4, title='Four', rid=4)
        m.album_tracks = {name: [t] for name in {r for r, _, _ in rows}}
        m.class_lists[0xf001] = [t]
        m.class_lists[O['CLASS_ALBUMS']] = m.showlist = [m.record(album=name, artist='Z', path=rep, rid=rid) for name, rep, rid in rows]
        m.fs[P4] = b'x'

    for n in (95, 96, 255):
        tag = 'L' * n
        m = PH(entries=[song(P4, 'Four', 'X', tag)]); lib2(m, tag, [(tag, '/mnt/mmc/Other/1.flac', 9)]); m.begin()
        calls = tap_tile(m, 0, 1)
        expect(m.plays and m.plays[-1][2] == 0 and not [c for c in calls if c[0] == 'toast'], f'a {n} byte album tag finds its album ({m.plays[-1:]}, {[c for c in calls if c[0] == "toast"]})')
    m = PH(entries=[song(P4, 'Four', 'X', '')]); lib2(m, '', [('Other', '/mnt/mmc/Other/1.flac', 9), ('Unknown Album', '', -1)]); m.begin()
    calls = tap_tile(m, 0, 1)
    expect(m.plays and m.plays[-1][2] == 0 and ('loadAlbumdetailList', 'Unknown Album') in m.calls_all and not [c for c in calls if c[0] == 'toast'],
           f'a song with no album tag plays from the Unknown Album row ({m.plays[-1:]}, {[c for c in calls if c[0] == "toast"]})')
    m = PH(entries=[song(P4, 'Four', 'X', '')]); lib2(m, '', [('Other', '/mnt/mmc/Other/1.flac', 9)]); m.begin()
    expect(not m.plays and [c[1] for c in tap_tile(m, 0, 1) if c[0] == 'toast'] == ["Can't play"], 'no Unknown Album row and nothing else to find it by: "Can\'t play"')


def pin_write_tests(ctx):
    """A write that fails leaves the list in memory as the file has it (Unpin on the sheet, the API's pin and unpin, the library check): the tile stays and "Can't update pins" is said. A playlist pin is its id and its name: a replacement
    playlist (the stock ids are reused) is not pinned by the deleted one's pin, and pinning it replaces the stale pin."""
    expect = ctx.expect
    RM = sibling('rowmenu')

    def mk(entries, showlist=None):
        m = PH(entries=entries)
        for nm in SHEET_WIDGETS: Machine.widget(m, nm)
        m.images['rm_dots'] = (RM.DOTS, RM.DOTS, RM.dots_pixels())
        if showlist: m.showlist = [m.record(album=a, artist='Else', rid=i + 1) for i, a in enumerate(showlist)]
        m.begin()
        return m

    # ---- the sheet's Unpin with a write that fails
    m = mk(ENTRIES[:4]); before = m.fs[PINS]; m.fail.add(('rename', PINS)); m.calls = []
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.click('rm_item2', count=900000000)
    expect(m.fs[PINS] == before and PINS_TMP not in m.fs and toasts(m) == ["Can't update pins"] and m.is_shown(m.pins) and m.s32(m.pins + 0xc) == 256 and m.call(PSYMS['pn_tile_in'], a0=0, count=100000) == 0,
           f'Unpin with a failing write: the file and the tile stay, "Can\'t update pins" ({toasts(m)}, h {m.s32(m.pins + 0xc)})')
    m.fail.clear(); m.calls = []
    m.call(PSYMS['pn_open_sheet'], a0=0, count=900000000); m.click('rm_item2', count=900000000)
    expect(H.parse(m.fs[PINS]) == ENTRIES[1:4] and m.s32(m.pins + 0xc) == 130 and not toasts(m), 'and once the card writes again the same Unpin removes it and the section shrinks')
    # ---- the API
    m = machine(H.dump(ENTRIES[:3])); m.fail.add(('rename', PINS)); m.calls = []
    expect(m.call(PSYMS['pins_unpin_album'], a0=m.cstr('Homogenic'), count=4000000) == 0 and m.fs[PINS] == H.dump(ENTRIES[:3]) and toasts(m) == ["Can't update pins"], f'the API\'s Unpin answers 0 and says so ({toasts(m)})')
    m.calls = []
    expect(pin_album(m, ENTRIES[4]) == -2 and m.fs[PINS] == H.dump(ENTRIES[:3]) and toasts(m) == ["Can't update pins"], 'a pin that cannot be written says so too')
    # ---- the library check: albums the list lacks stay; an album whose row has another cover key takes it, and a re-key that cannot be written leaves the file
    m = mk(ENTRIES[:4], showlist=('Nothing',)); m.clock = O['PIN_CHECK_MS'] + 1000
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    expect(m.fs[PINS] == H.dump(ENTRIES[:4]) and m.s32(m.pins + 0xc) == 256, f'the check keeps the albums the library does not list (h {m.s32(m.pins + 0xc)})')
    stale = [(e[0], e[1], (0x1234, 0, 0, 0), e[3], e[4]) if i == 0 else e for i, e in enumerate(ENTRIES[:4])]
    m = mk(stale, showlist=('Kind of Blue',)); m.fail.add(('rename', PINS)); m.clock = O['PIN_CHECK_MS'] + 1000
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    expect(m.fs[PINS] == H.dump(stale) and m.s32(m.pins + 0xc) == 256, f'a re-key that cannot be written leaves the file and the tiles (h {m.s32(m.pins + 0xc)})')
    m = mk(stale, showlist=('Kind of Blue',)); m.clock = O['PIN_CHECK_MS'] + 1000
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=900000000)
    got = H.parse(m.fs[PINS])
    expect(len(got) == 4 and got[0][2][0] not in (0x1234, 0) and got[1:] == stale[1:], f'the check re-keys the album to its row\'s cover key and keeps the rest ({got[0][2] if got else None})')
    # an empty (or failed) album or playlist list: the tap says Not found, Play says Can't play, the pins stay
    m = mk(ENTRIES[:2]); m.showlist = []
    for i, what in ((0, 'album'), (1, 'playlist')):
        tap_tile(m, i)
        expect([c[1] for c in m.calls_all if c[0] == 'toast'] == ['Not found'] and m.fs[PINS] == H.dump(ENTRIES[:2]), f'no {what} list: a tap says Not found and the pin stays')
        m.call(PSYMS['pn_open_sheet'], a0=i, count=900000000); m.calls = []; m.click('rm_item0', count=900000000)
        expect(toasts(m) == ["Can't play"] and not m.plays and m.fs[PINS] == H.dump(ENTRIES[:2]), f'no {what} list: Play says Can\'t play and the pin stays ({toasts(m)})')

    # ---- playlists by id and name
    old, new = playlist(3, 'Old', (11,)), playlist(3, 'New', (22,))
    others = [album('Kind of Blue', 'Miles Davis'), old, playlist(9, 'Road Trip', (44,))]
    m = machine(H.dump(others))
    has = lambda e: m.call(PSYMS['pins_has_playlist'], a0=e[1], a1=m.cstr(e[3]), count=4000000)
    expect(has(old) == 1 and has(new) == 0 and m.read_cstr(m.call(PSYMS['pins_label_playlist'], a0=3, a1=m.cstr('New'), count=4000000)) == 'Pin Playlist', 'a replacement playlist of the same id is not pinned')
    expect(m.call(PSYMS['pins_unpin_playlist'], a0=3, a1=m.cstr('New'), count=4000000) == 0 and m.fs[PINS] == H.dump(others), 'and its Unpin leaves the deleted playlist\'s pin')
    expect(pin_playlist(m, new, (22,)) == 0 and H.parse(m.fs[PINS]) == [others[0], new, others[2]], 'pinning the replacement replaces the stale pin in place (one entry for the id)')
    expect(has(new) == 1 and has(old) == 0 and pin_playlist(m, new, (22,)) == 0 and len(H.parse(m.fs[PINS])) == 3, 'now the replacement is the pinned one; pinning it again changes nothing')
    expect(m.call(PSYMS['pins_unpin_playlist'], a0=3, a1=m.cstr('New'), count=4000000) == 1 and [e[3] for e in H.parse(m.fs[PINS])] == ['Kind of Blue', 'Road Trip'], 'Unpin with the right name removes it')
    m = machine(H.dump(others)); m.fail.add(('rename', PINS)); m.calls = []
    expect(pin_playlist(m, new, (22,)) == -2 and m.fs[PINS] == H.dump(others), 'a replacement that cannot be written leaves the stale pin as it was')


SECTIONS = [constants_and_asset_tests, file_and_api_tests, section_tests, sheet_tests, reorder_tests, recent_sheet_tests, artist_tests, read_error_tests, artist_scope_tests, cue_and_album_tests, pin_write_tests]   # tools/check.py runs each as its own task
