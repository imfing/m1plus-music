"""Get Info (patch/songinfo.c, docs/modules/songinfo.md): the page asset, and the page the payload paints for a track: the header (cover, title, artist, album) and the pairs read from the file's first
bytes (FLAC, WAV, Ogg Vorbis, MPEG with and without an ID3v2 tag, a file with none of them), its size, the durations table / FLAC total / TagLib length, a CUE track, a missing file, long texts,
the page being up already, and the window's destroy. The compiled payload runs under Unicorn; the card is a dict of paths."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

UI_DIR = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui') if WORK else None
WIN = 0x20004000
WIDGETS = ('gi_view', 'img_nb_fade', 'label_head', 'label_sub', 'label_key', 'label_val', 'btn_return', 'btn_backtoplayer')
SC_YOFF = O['SC_YOFF']


def u8(s):
    for _ in range(2):
        try: s = s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError): break
    return s


def flac(rate=44100, bits=16, channels=2, total=44100 * 185):
    """fLaC + the STREAMINFO block header and body (34 bytes): 20 bits of rate, 3 of channels - 1, 5 of bits - 1, 36 of samples."""
    packed = rate << 44 | (channels - 1) << 41 | (bits - 1) << 36 | total
    return b'fLaC' + bytes([0, 0, 0, 34]) + struct.pack('>HH', 4096, 4096) + bytes(6) + packed.to_bytes(8, 'big') + bytes(16) + bytes(64)


def wav(rate=48000, bits=24):
    fmt = struct.pack('<HHIIHH', 1, 2, rate, rate * 2 * bits // 8, 2 * bits // 8, bits)
    return b'RIFF' + struct.pack('<I', 4096) + b'WAVE' + b'LIST' + struct.pack('<I', 6) + bytes(6) + b'fmt ' + struct.pack('<I', 16) + fmt + b'data' + bytes(64)


def ogg(rate=44100):
    return b'OggS' + bytes([0, 2]) + bytes(8) + bytes(4) + bytes(4) + bytes(4) + bytes([1, 30]) + b'\x01vorbis' + struct.pack('<IBIII', 0, 2, rate, 0, 0) + bytes(64)


def mp3(tag=0, rate_idx=0):
    """An ID3v2 tag of `tag` body bytes (0: none), then padding and an MPEG 1 layer III frame header at 128 kbps."""
    head = b''
    if tag:
        size = bytes([(tag >> 21) & 0x7f, (tag >> 14) & 0x7f, (tag >> 7) & 0x7f, tag & 0x7f])
        head = b'ID3\x03\x00\x00' + size + bytes(tag)
    return head + bytes(5) + bytes([0xff, 0xfb, 0x90 | rate_idx << 2, 0x00]) + bytes(64)


def machine(path, data, size=None, secs=None, **rec_kw):
    m = ListMachine()   # (the widget text calls: the wrapper measures 8 px a char)
    m.windows['m1plus_songinfo'] = WIN
    m.top_main = 0
    m.window = WIN
    for n in WIDGETS: m.widget(n)
    m.sv = m.alloc(0x100); m.widgets['gi_scrollview'] = m.sv
    m.canvas = m.alloc(0x80)
    if data is not None:
        m.fs[path] = data
        if size is not None: m.files[path] = size   # (what ftell says: a 30 MB file whose first bytes are the test's)
    if secs is not None: m.durations[path] = secs
    m.rec = m.record(path=path, **rec_kw)
    return m


def open_page(m, rec=None):
    m.calls.clear()
    ret = m.call(PSYMS['songinfo_open'], a0=rec or m.rec, count=900000000)
    m.open_calls = list(m.calls)
    m.top_main = WIN
    return ret


def paint(m, off=0):
    """One EVT_AFTER_PAINT of the content view at scroll offset off: [(style, text, x, y, w)]."""
    m.setword(m.sv + SC_YOFF, off)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.texts.clear(); m.text_styles.clear(); m.blits.clear()
    fn, c = m.bound[(m.widgets['gi_view'], O['EVT_AFTER_PAINT'])]
    m.call(fn, a0=c, a1=ev, count=40000000)
    return [(s, u8(t), r[0], r[1] + off, r[2]) for (t, r), s in zip(m.texts, m.text_styles)]


def parse(m):
    """(header {style: joined text}, pairs {label: joined value lines}, in order) from the paints that scroll through the whole content (a text is drawn only when wholly in view)."""
    head, pairs, key = {'label_head': '', 'label_sub': []}, {}, None
    seen = {}
    for off in range(0, 1200, 100):
        for r in paint(m, off): seen[(r[3], r[0], r[1])] = r
    paint(m, 0)
    for s, t, x, y, w in (seen[k] for k in sorted(seen)):
        if s == 'label_head': head['label_head'] += t
        elif s == 'label_sub': head['label_sub'].append(t)
        elif s == 'label_key': key = t; pairs[key] = ''
        elif s == 'label_val': pairs[key] += t
    return head, pairs


SR = 'Sample Rate / Bit Depth'


def asset_tests(ctx):
    """1. The page asset: a black page, the stock navbar over a stock list holding one content view, four hidden text styles."""
    expect = ctx.expect
    import pod_pages as P
    gi = awtk_ui.parse(open(os.path.join(UI_DIR, 'm1plus_songinfo.bin'), 'rb').read()); h = gi.find
    expect(gi.name == 'm1plus_songinfo_page' == P.SONGINFO.name and P.SONGINFO.kind == 'songinfo' and P.SONGINFO.title == 'Get Info' and P.PAGES[P.REGION_PAGE_INDEX - 1] is P.SONGINFO,
           'the page m1plus_songinfo is built, titled Get Info and followed in the page table by the Podcast Region picker and the Wi-Fi pages')
    expect(all(h(n) is not None for n in WIDGETS + ('gi_scrollview', 'gi_listview', 'label_title')) and gi.get('style:normal:bg_color') == '#000000' and h('gi_view').get('style:normal:bg_color') == '#000000'
           and h('gi_listview').type == 'list_view' and h('gi_scrollview').type == 'scroll_view' and h('scroll_bar_m') is not None and (h('gi_listview').y, h('gi_listview').h, h('gi_view').w) == (50, 400, 320)
           and h('img_nb_fade').get('visible') == 'false' and h('img_nb_fade').get('sensitive') == 'false',
           'a black page, the stock navbar (Back, Now Playing) over a stock list holding one content view, the fade hidden at rest')
    expect(all(h(n).get('visible') == 'false' and h(n).get('sensitive') == 'false' for n in ('label_head', 'label_sub', 'label_key', 'label_val'))
           and [h(n).get('style:normal:font_size') for n in ('label_head', 'label_sub', 'label_key', 'label_val')] == ['22', '16', '14', '18']
           and [h(n).get('style:normal:text_color') for n in ('label_head', 'label_sub', 'label_key', 'label_val')] == ['#FFFFFF', '#8E8E93', '#8E8E93', '#FFFFFF'],
           'the four text styles: a 22 px white title, 16 px grey (#8E8E93) artist and album, the 14 px grey label, the 18 px white value')
    import pod_i18n
    keys = ['Get Info', 'Favorite', 'Undo Favorite', 'Added to Favorites', 'Removed from Favorites', 'Format', 'Sample Rate', 'Bit Depth', 'Bitrate', 'Duration', 'Size', 'Path']
    expect(all(k in pod_i18n.TEXT and set(pod_i18n.TEXT[k]) == set(pod_i18n.LOCALES) for k in keys), 'every text of the page and the sheet rows has its 13 translations')
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    widest = max((StbText(font, 14).layout(dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin')))['Sample Rate'] + ' / ' + dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin')))['Bit Depth'])[1], loc)
                 for loc in pod_i18n.LOCALES)
    expect(widest[0] <= 288, f'the longest label (Sample Rate / Bit Depth, {widest[1]}, {widest[0]:.0f} px at 14 px) fits the 288 px line')


def field_tests(ctx):
    """2. The pairs of each format, in order, with the header."""
    expect = ctx.expect
    # FLAC, 44.1 kHz / 16 bit, 3:05, 30 MB
    path = '/mnt/mmc/Music/Artist/Album/01 Track.flac'
    m = machine(path, flac(), size=30_000_000, title='A Long Song', artist='The Artist', album='The Album')
    ret = open_page(m)
    head, pairs = parse(m)
    expect(ret == 0 and ('window_open', 'm1plus_songinfo') in m.open_calls and ('widget_on', m.widgets['gi_view'], O['EVT_AFTER_PAINT']) == m.open_calls[[c[:3] for c in m.open_calls].index(('widget_on', m.widgets['gi_view'], O['EVT_AFTER_PAINT']))][:3],
           'Get Info opens the window and paints the content view')
    expect(head['label_head'] == 'A Long Song' and head['label_sub'] == ['The Artist', 'The Album'], f'the header: the title, then the artist and the album ({head})')
    expect(list(pairs) == ['Format', SR, 'Bitrate', 'Duration', 'Size', 'Path'], f'FLAC: the pairs in order ({list(pairs)})')
    expect(pairs['Format'] == 'FLAC' and pairs[SR] == '44.1 kHz / 16-bit' and pairs['Duration'] == '3:05' and pairs['Size'] == '30.0 MB' and pairs['Path'].replace(' ', '') == path.replace(' ', ''),
           f'FLAC: 44.1 kHz / 16-bit from STREAMINFO, 3:05 from its total samples, 30.0 MB, the path ({pairs})')
    expect(pairs['Bitrate'] == '1297 kbps', f'FLAC: the average bitrate, bytes over seconds ({pairs["Bitrate"]})')
    expect(('taglib_file_new', path, 1) not in m.calls and ('taglib_file_new', path, 1) not in m.open_calls, 'FLAC: TagLib is not opened (the header has the length)')
    # the cover: one 96 px blit at the page's left, 16 px from the top; scrolled, it moves up
    paint(m)
    cov = [b for b in m.blits if b[2][2:] == (96, 96)]
    expect(len(cov) == 1 and cov[0][2][:2] == (16, 16), f'the cover is drawn 96 px square at (16, 16) ({[b[2] for b in m.blits]})')
    paint(m, 40)
    cov = [b for b in m.blits if b[2][2] == 96]
    expect([(b[1], b[2]) for b in cov] == [((0, 24, 96, 72), (16, 0, 96, 72))], f'scrolled by 40, the cover moves up with the content, its top 24 px cut ({[(b[1], b[2]) for b in cov]})')
    # 96 kHz / 24 bit
    m = machine(path, flac(96000, 24, total=96000 * 61), size=61_000_000)
    open_page(m); _, pairs = parse(m)
    expect(pairs[SR] == '96 kHz / 24-bit' and pairs['Duration'] == '1:01' and pairs['Size'] == '61.0 MB', f'FLAC 96 kHz / 24-bit ({pairs})')
    m = machine(path, flac(176400, 24, total=176400 * 3725), size=1_230_000_000)
    open_page(m); _, pairs = parse(m)
    expect(pairs[SR] == '176.4 kHz / 24-bit' and pairs['Duration'] == '1:02:05' and pairs['Size'] == '1.23 GB', f'FLAC 176.4 kHz, an hour long, over a GB ({pairs})')
    m = machine(path, flac(22050, 8, total=22050 * 10), size=999)
    open_page(m); _, pairs = parse(m)
    expect(pairs[SR] == '22.05 kHz / 8-bit' and pairs['Size'] == '999 B', f'22.05 kHz / 8-bit, a size under 1 KB ({pairs})')
    # WAV
    p2 = '/mnt/mmc/Music/x.wav'
    m = machine(p2, wav(), size=5_760_000, secs=20)
    open_page(m); _, pairs = parse(m)
    expect(pairs['Format'] == 'WAV' and pairs[SR] == '48 kHz / 24-bit' and pairs['Duration'] == '0:20' and pairs['Size'] == '5.8 MB', f'WAV: the fmt chunk past a LIST chunk, the length from TagLib ({pairs})')
    expect(pairs['Bitrate'] == '2304 kbps', f'WAV bitrate ({pairs["Bitrate"]})')
    # Ogg Vorbis
    p3 = '/mnt/mmc/Music/y.ogg'
    m = machine(p3, ogg(32000), size=480_000, secs=240)
    open_page(m); _, pairs = parse(m)
    expect(pairs['Format'] == 'OGG' and pairs['Sample Rate'] == '32 kHz' and SR not in pairs and pairs['Bitrate'] == '16 kbps' and pairs['Duration'] == '4:00',
           f'Ogg Vorbis: the rate from the identification header and no bit depth ({pairs})')
    # MP3, no tag, and after an ID3v2 tag larger than the first read
    p4 = '/mnt/mmc/Music/z.mp3'
    m = machine(p4, mp3(), size=3_840_000, secs=240)
    open_page(m); _, pairs = parse(m)
    expect(pairs['Format'] == 'MP3' and pairs['Sample Rate'] == '44.1 kHz' and pairs['Bitrate'] == '128 kbps' and pairs['Duration'] == '4:00' and pairs['Size'] == '3.8 MB' and ('taglib_file_new', p4, 1) in m.open_calls,
           f'MP3 without a tag: the first frame\'s sample rate, the average bitrate, TagLib\'s length ({pairs})')
    for tag, idx, want in ((300, 1, '48 kHz'), (5000, 0, '44.1 kHz'), (70000, 2, '32 kHz')):
        m = machine(p4, mp3(tag, idx), size=3_840_000, secs=240)
        open_page(m); _, pairs = parse(m)
        expect(pairs.get('Sample Rate') == want, f'MP3 after an ID3v2 tag of {tag} bytes: {want} ({pairs.get("Sample Rate")})')
    # a format the page cannot read: Format, Bitrate, Duration, Size, Path; no Sample Rate row
    p5 = '/mnt/mmc/Music/w.m4a'
    m = machine(p5, bytes(100), size=4_800_000, secs=240)
    open_page(m); _, pairs = parse(m)
    expect(list(pairs) == ['Format', 'Bitrate', 'Duration', 'Size', 'Path'] and pairs['Format'] == 'M4A' and pairs['Bitrate'] == '160 kbps', f'an unreadable header: no Sample Rate row ({list(pairs)})')
    # MPEG-like bytes inside another container (an M4A free box) are no frame; nor is a lone sync in an MP3 whose next frame header does not follow
    m = machine(p5, bytes(4) + b'ftypM4A ' + bytes(8) + b'free' + bytes([0xff, 0xfb, 0x90, 0x00]) + bytes(64), size=4_800_000, secs=240)
    open_page(m); _, pairs = parse(m)
    expect('Sample Rate' not in pairs, f'an M4A with MPEG-like bytes: no Sample Rate ({pairs.get("Sample Rate")})')
    m = machine(p4, bytes([0xff, 0xfb, 0x90, 0x00]) + bytes(500) + bytes([0xff, 0xfb, 0x94, 0x00]) + bytes(300), size=3_840_000, secs=240)
    open_page(m); _, pairs = parse(m)
    expect(pairs.get('Sample Rate') == '48 kHz', f'MP3: a sync whose next frame (417 bytes on) has no header is skipped ({pairs.get("Sample Rate")})')
    # the durations table wins over a TagLib call: no TagLib when the card has the entry
    # a file that is gone: only what the record knows
    m = machine('/mnt/mmc/Music/gone.flac', None)
    open_page(m); head, pairs = parse(m)
    expect(list(pairs) == ['Format', 'Path'] and ('taglib_file_new', '/mnt/mmc/Music/gone.flac', 1) not in m.open_calls, f'a missing file: Format and Path only ({list(pairs)})')
    # no extension, an extension that is not one
    m = machine('/mnt/mmc/Music/noext', None)
    open_page(m); _, pairs = parse(m)
    expect(list(pairs) == ['Path'], f'no extension: no Format row ({list(pairs)})')
    m = machine('/mnt/mmc/Music/dir.v2/noext', None)
    open_page(m); _, pairs = parse(m)
    expect(list(pairs) == ['Path'], f'a dot in a folder name is not an extension ({list(pairs)})')
    # an empty title shows the file name
    m = machine(path, flac(), size=1000000, title='', name='01 Track.flac')
    open_page(m); head, _ = parse(m)
    expect(head['label_head'] == '01 Track.flac', f'no title: the file name ({head})')
    # CUE track: its own length, no bitrate (the file's length is not the track's)
    m = machine(path, flac(), size=30_000_000)
    m.setword(m.rec + O['REC_CUE_START'], 60); m.setword(m.rec + O['REC_CUE_END'], 180)
    open_page(m); _, pairs = parse(m)
    expect(pairs['Duration'] == '2:00' and 'Bitrate' not in pairs and pairs['Size'] == '30.0 MB', f'a CUE track with both ends: its length, no bitrate, the file\'s size ({pairs})')
    m = machine(path, flac(), size=30_000_000)
    m.setword(m.rec + O['REC_CUE_START'], 100)
    open_page(m); _, pairs = parse(m)
    expect(pairs['Duration'] == '1:25' and 'Bitrate' not in pairs, f'the last CUE track: the file\'s length less its start ({pairs})')
    # a long path wraps in full; a long title is cut at two lines
    long_path = '/mnt/mmc/Music/' + '/'.join(['A very long folder name number %d' % i for i in range(6)]) + '/01 Track.flac'
    m = machine(long_path, flac(), size=1_000_000, title='T' * 400)
    open_page(m); head, pairs = parse(m)
    expect(pairs['Path'].replace(' ', '') == long_path.replace(' ', ''),
           f'a long path wraps over lines and shows in full ({pairs["Path"]})')
    heads = [t for s, t, x, y, w in paint(m) if s == 'label_head']
    expect(len(heads) == 2 and heads[-1].endswith('…'), f'a title longer than two lines ends in an ellipsis ({heads})')
    expect(m.props.get((m.sv, 'virtual_h')) == [c[3] for c in m.open_calls if c[0] == 'widget_resize' and c[1] == m.widgets['gi_view']][-1] > 400, 'the scroll view is as tall as the content')


def geometry_tests(ctx):
    """3. Where things are: the header texts beside the cover and centred on its height, the pairs under it from x 16, every text wholly in the view."""
    expect = ctx.expect
    path = '/mnt/mmc/Music/a.flac'
    m = machine(path, flac(), size=30_000_000, title='Title', artist='Artist', album='Album')
    open_page(m)
    rows = paint(m)
    hdr = [r for r in rows if r[0] in ('label_head', 'label_sub')]
    pr = [r for r in rows if r[0] in ('label_key', 'label_val')]
    expect(all(r[2] == 124 and r[4] == 180 for r in hdr) and all(r[2] == 16 and r[4] == 288 for r in pr), 'the header texts start at x 124 (180 px wide), the pairs at x 16 (288 px)')
    top, bottom = hdr[0][3], hdr[-1][3] + 20
    expect(abs((top + bottom) / 2 - (16 + 48)) <= 2 and min(r[3] for r in pr) >= 16 + 96, f'the three header lines are centred on the cover ({top}..{bottom}); the pairs are under it ({min(r[3] for r in pr)})')
    keys = [r[1] for r in rows if r[0] == 'label_key' and r[3] + 18 <= 400]
    expect(keys[-2:] == ['Size', 'Path'] and sum(r[0] == 'label_val' and r[3] + 22 <= 400 for r in rows) >= len(keys) - 1, f'at rest, Format to Size show above the fold and Path\'s label peeks under them ({keys})')
    rows = paint(m, 60)
    expect(all(0 <= r[3] - 60 and r[3] - 60 + 24 <= 400 for r in rows), 'scrolled, every text drawn lies wholly inside the 400 px view')
    expect(m.props.get((m.widgets['img_nb_fade'], 'visible')) == 1, 'scrolled, the navbar fade shows')
    paint(m, 0)
    expect(m.props.get((m.widgets['img_nb_fade'], 'visible')) == 0, 'at rest it is hidden again')


def lifecycle_tests(ctx):
    """4. No record, a second open, Back, a missing asset, the window's destroy."""
    expect = ctx.expect
    path = '/mnt/mmc/Music/a.flac'
    m = machine(path, flac(), size=30_000_000)
    ret = m.call(PSYMS['songinfo_open'], a0=0, count=900000000)
    expect(ret == 0xffffffff and ('window_open', 'm1plus_songinfo') not in m.calls, 'no record: -1, no window')
    m = machine(path, flac(), size=30_000_000)
    open_page(m)
    m.calls.clear()
    m.widget_on_fail = set(); m.home_opened = 1
    expect(m.call(PSYMS['songinfo_open'], a0=m.rec, count=900000000) == 0 and ('window_open', 'm1plus_songinfo') not in m.calls, 'a second open while the page is up (on top) opens nothing')
    # Back and the Now Playing disc are bound
    fn_back = m.bound.get((m.widgets['btn_return'], O['EVT_CLICK']))
    expect(fn_back is not None and m.bound.get((m.widgets['btn_backtoplayer'], O['EVT_CLICK'])) is not None, 'Back and the Now Playing disc are bound')
    # a window that will not open
    m = machine(path, flac(), size=30_000_000)
    m.windows['m1plus_songinfo'] = 0; m.window = 0
    expect(open_page(m) == 0xffffffff, 'a window that will not open: -1')
    # an asset that is not ours: the page leaves again
    m = machine(path, flac(), size=30_000_000)
    del m.widgets['label_sub']
    ret = open_page(m)
    expect(ret == 0xffffffff and ('navigator_back',) in m.open_calls, 'an asset that is not ours: -1, the page leaves again')
    # destroy frees the page and every bitmap
    m = machine(path, flac(), size=30_000_000)
    open_page(m); parse(m)
    fn, c = m.bound[(WIN, O['EVT_DESTROY'])]
    m.calls.clear()
    m.call(fn, a0=c, count=4000000)
    expect(len(m.bitmaps) == 0, f'closing the page frees every bitmap ({len(m.bitmaps)} left)')
    frees = [c for c in m.calls if c[0] == 'free']
    expect(len(frees) >= 3, f'and its tables ({len(frees)} frees)')
    # a closing page is replaced; its late destroy leaves the new page alone
    m = machine(path, flac(), size=30_000_000)
    open_page(m)
    old = WIN; new = 0x25100000
    m.windows['m1plus_songinfo'] = new; m.window = new
    m.top_main = 0x26100000
    m.calls.clear()
    m.call(PSYMS['songinfo_open'], a0=m.rec, count=900000000)
    expect(('window_open', 'm1plus_songinfo') in m.calls, 'under another window: a fresh page opens')
    m.calls.clear()
    fn, c = m.bound[(old, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=4000000)
    expect(not [c for c in m.calls if c[0] == 'free'], 'the old page\'s late destroy frees nothing of the new one')


def cover_tests(ctx):
    """5. The cover: the track's own Cover Flow cache file, else the file of the library album record of its album name (a collab, "A; B"): ONE targeted query, getAllAlbum's statement
    filtered to the name, whose record is the one the album list has (the cache files are named after it); never the album list."""
    expect = ctx.expect
    path, album = '/mnt/mmc/Music/a.flac', 'WHAT HAPPENED TO THE STREETS?'
    def cover_machine(artist, album_, canon=('21 Savage', album), files=(('21 Savage', album),)):
        """The track `artist` / `album_`; the library lists the album once, as the record `canon` (artist, album), its tracks under several songers; a cache file under each key in `files`."""
        m = machine(path, flac(), size=30_000_000, artist=artist, album=album_)
        m.load_image = 0
        for k, (fa, fb) in enumerate(files):
            file = art_file(album_key(fa, fb))
            m.present.add(file); m.files[file] = 4096; m.images['file://' + file] = (168, 168, bytes((190 + 20 * k, 50, 55, 255)) * (168 * 168))
        m.class_lists[0xf001] = [m.record(album=album, artist='Young Nudy', path='/mnt/mmc/Music/a0.flac', rid=6), m.record(album=album, artist='21 Savage', path='/mnt/mmc/Music/b.flac', rid=7),
                                 m.record(album=album, artist='Drake', path='/mnt/mmc/Music/c.flac', rid=8), m.rec]
        m.class_lists[O['CLASS_ALBUMS']] = [m.record(album=canon[1], artist=canon[0], path='/mnt/mmc/Music/b.flac', rid=7), m.record(album='Other', artist='Zed', path='/mnt/mmc/Music/z.flac', rid=9)]
        return m
    def asked(m): return [c[2] for c in m.open_calls if c[0] == 'toolsQueryDbTable']
    def url(a, b): return 'file://' + art_file(album_key(a, b))
    def quoted(name): return f"select id,album,songer,fileurl from songtable where album='{name.replace(chr(39), chr(39) * 2)}' COLLATE NOCASE group by album COLLATE NOCASE"
    q = quoted(album)
    m = cover_machine('21 Savage; Young Nudy', album)
    shown = m.word(pod.DATA['PDEQ_SHOWLIST'][0])
    expect(open_page(m) == 0 and asked(m) == [q] and url('21 Savage', album) in m.loads, f'a collab track: the album\'s cover, from one targeted query on the album name ({asked(m)}, {m.loads})')
    expect(all(c[3:] == (0x4e93c8, 0) for c in m.open_calls if c[0] == 'toolsQueryDbTable'), 'with stock\'s album row callback, as getAllAlbum')
    expect(not any(c[0] in ('loadLocalClassList', 'deque_assign', 'loadAlbumList') for c in m.open_calls) and m.word(pod.DATA['PDEQ_SHOWLIST'][0]) == shown and m.deques[m.word(pod.DATA['PDEQ_TOOLS_TMP'][0])] == [],
           'the stock album list is not loaded (*pdeq_showlist untouched), the query\'s record is cleared')
    # the album's tracks list several artists; the library's record for the album is the one the cache is named after, not the first track's nor the track's own
    other = ('Young Nudy', album)
    m = cover_machine('G Herbo; Drake', album, canon=('Drake', album), files=(('Drake', album),))
    open_page(m)
    expect(asked(m) == [q] and url('Drake', album) in m.loads and len(m.loads) == 1, f'the cache file exists only under the album record\'s key (a third artist\'s): that is the cover ({m.loads})')
    m = cover_machine('G Herbo; Drake', album, canon=('Drake', album), files=(other, ('Drake', album), ('21 Savage', album)))
    open_page(m)
    expect(url('Drake', album) in m.loads and url(*other) not in m.loads and url('21 Savage', album) not in m.loads and len(asked(m)) == 1,
           'files under a sibling track\'s artists too (stale or from another build): the album record\'s key decides, not the first track with a file')
    m = cover_machine('G Herbo; 21 Savage', album.lower())
    open_page(m)
    expect(url('21 Savage', album) in m.loads and asked(m) == [quoted(album.lower())], 'the album name is matched without case')
    m = cover_machine('21 Savage', album)
    open_page(m)
    expect(url('21 Savage', album) in m.loads and not asked(m), 'a track whose own key has a file asks nothing')
    m = cover_machine('21 Savage; Drake', '')
    open_page(m)
    expect(not any(u.startswith('file://') for u in m.loads) and not asked(m), 'a track with no album tag: the placeholder, no query')
    m = cover_machine('21 Savage; Drake', album, files=())
    open_page(m)
    expect(asked(m) == [q] and not any(u.startswith('file://') for u in m.loads), 'an album with no cache file at all: the placeholder')
    m = cover_machine('Ghost; Q', 'Not In The Library')
    open_page(m)
    expect(asked(m) == [quoted('Not In The Library')] and not any(u.startswith('file://') for u in m.loads) and m.deques[m.word(pod.DATA['PDEQ_TOOLS_TMP'][0])] == [], 'an album the library lacks: one query, the placeholder')
    m = cover_machine('21 Savage; Drake', album)
    m.album_query_fails = True
    open_page(m)
    expect(len(asked(m)) == 1 and not any(u.startswith('file://') for u in m.loads), 'a failed query: the placeholder')
    quote = "It's a 'Wonder'"
    m = cover_machine("O'Brien; X", quote, canon=("O'Brien", quote), files=(("O'Brien", quote),))
    open_page(m)
    expect(asked(m) == [quoted(quote)] and "'It''s a ''Wonder'''" in asked(m)[0] and url("O'Brien", quote) in m.loads, f'quotes in the album name are doubled ({asked(m)})')
    m = cover_machine('A; B', 'x' * 251)
    open_page(m)
    expect(not asked(m), 'a name over 250 bytes asks nothing')
    # one targeted query on the open and no more: painting asks the database nothing
    m = cover_machine('21 Savage; Young Nudy', album)
    open_page(m); m.calls.clear(); paint(m); paint(m, 40)
    expect([c for c in m.calls if c[0] == 'toolsQueryDbTable'] == [], 'painting asks the database nothing')


def remote_tests(ctx):
    """5. A Navidrome track (ND-14): the page reads the server's data (the cached row, completed from the album's file) instead of a file: format, sample rate and bit depth, bitrate, duration, size;
    nothing is opened under "nd://" and TagLib is not used; Path appears only for a downloaded track (the local file); the cover is the cached Navidrome picture, else the placeholder."""
    expect = ctx.expect
    import importlib.util
    spec = importlib.util.spec_from_file_location('podtest_sbapi', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sbapi.py'))
    SA = importlib.util.module_from_spec(spec); spec.loader.exec_module(SA)
    meta = 't\t185\tflac\t0\tcv9\tal1'
    m = machine('nd://t9', None, title='Nine', artist='The Artist', album='The Album')
    m.setword(m.rec + 0x28, m.cstr(meta))
    m.fs[f'{SA.ND}/al/al1.idx'] = SA.cache_file('track', [SA.row('track', id='t9', title='Nine', artist='The Artist', album='The Album', album_id='al1', cover='cv9', suffix='flac', seconds=185, track=9, disc=1,
                                                              size=30_000_000, bitrate=900, sample_rate=96000, bit_depth=24)])
    open_page(m)
    head, pairs = parse(m)
    expect(head['label_head'] == 'Nine' and head['label_sub'] == ['The Artist', 'The Album'], f'remote: the header texts ({head})')
    expect(list(pairs) == ['Format', SR, 'Bitrate', 'Duration', 'Size'], f'remote, not downloaded: the pairs without a Path ({list(pairs)})')
    expect(pairs['Format'] == 'FLAC' and pairs[SR] == '96 kHz / 24-bit' and pairs['Bitrate'] == '900 kbps' and pairs['Duration'] == '3:05' and pairs['Size'] == '30.0 MB',
           f'remote: the server\'s format, rate and depth, its own bitrate, duration and size ({pairs})')
    expect(not [c for c in m.calls + m.open_calls if c[0] in ('taglib_file_new', 'dur_probe') or (c[0] in ('open', 'fopen') and str(c[1]).startswith('nd://'))], 'remote: no file read, no TagLib')
    # the album's file has no row: only what the record carries (format and length)
    m = machine('nd://t9', None, title='Nine')
    m.setword(m.rec + 0x28, m.cstr(meta))
    open_page(m)
    _, pairs = parse(m)
    expect(list(pairs) == ['Format', 'Duration'] and pairs['Format'] == 'FLAC' and pairs['Duration'] == '3:05', f'remote, no cached row: Format and Duration from the record ({pairs})')
    # no sizes anywhere: no bitrate from nothing
    m = machine('nd://t9', None, title='Nine')
    m.setword(m.rec + 0x28, m.cstr('t\t0\tmp3\t0\t\t'))
    open_page(m)
    _, pairs = parse(m)
    expect(list(pairs) == ['Format'] and pairs['Format'] == 'MP3', f'remote with nothing else known: Format alone ({pairs})')
    # downloaded: the local file is the Path, and what the server leaves out is read from it
    spec = importlib.util.spec_from_file_location('podtest_sbdl', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sbdl.py'))
    SD = importlib.util.module_from_spec(spec); spec.loader.exec_module(SD)
    t = SD.track('t9', 'Nine', 'flac')
    local = f'{SD.MUSIC}/{SD.name_of(t)}'
    m = machine('nd://t9', None, title='Nine')
    m.setword(m.rec + 0x28, m.cstr(meta))
    m.fs[local] = flac(); m.files[local] = 30_000_000
    m.fs[SD.IDX] = ('M1PLUS-DL 1\n' + '\t'.join(f'{k}={v}' for k, v in (('i', 't9'), ('t', 'Nine'), ('p', SD.name_of(t)), ('w', 30_000_000), ('x', 'flac'), ('l', 185))) + '\n').encode()
    m.dirs.add(SD.MUSIC) if hasattr(m, 'dirs') else None
    open_page(m)
    _, pairs = parse(m)
    expect(pairs.get('Path', '').replace(' ', '') == local.replace(' ', '') and pairs.get(SR) == '44.1 kHz / 16-bit' and pairs.get('Size') == '30.0 MB', f'remote, downloaded: Path is the local file; the rate and depth the server left out come from its header ({pairs})')
    # a stock record is not remote
    m = machine('/mnt/mmc/Music/a.flac', flac(), size=30_000_000)
    open_page(m)
    _, pairs = parse(m)
    expect(pairs['Format'] == 'FLAC' and 'Path' in pairs, 'a stock record still reads its file')


SECTIONS = [asset_tests, field_tests, geometry_tests, lifecycle_tests, cover_tests, remote_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
