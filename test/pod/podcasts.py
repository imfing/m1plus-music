"""Podcasts (patch/pcmodel.c, patch/podcasts.c, docs/modules/podcasts.md): the episode model (the files on the card merged with the metadata file the subscribe phase
will write, newest first), the resume ring, the jump to a saved place, the played marks, the speed per show, Shuffle's queue without podcasts, the page (two levels,
covers, rows, taps, play) and the menu item. The compiled payload runs under Unicorn with the stock calls mocked; the card is a dict of paths."""
import datetime, os, random, struct
import mod_icons, paths, pod_show
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

ROOT = '/mnt/mmc/Podcasts'
EMPTY_HINT = 'No podcasts. Copy a folder for each show into Podcasts on the card, or put subscriptions.txt there and choose Import from Card in the menu at the top right.'
STATE = '/mnt/mmc/.m1plus/podcasts'
RING, SPEED = STATE + '/resume', STATE + '/speed'
PLAYSPEED_MODE = pod.DATA['PLAYSPEED_MODE'][0]
EPS_HEAD = 'M1PLUS-EPISODES 1\n'
SCREEN_Y0 = 80   # the list's top on the screen: the 30 px system bar and the 50 px navbar
VIEW_H, ROW, CELL = O['GRID_VIEW_H'], O['PC_ROW_H'], O['PS_CELL_H']
SC_YOFF = O['SC_YOFF']


def pc_hash(s):
    """FNV-1a over the ASCII-lower-cased bytes, never 0 (patch/pcmodel.c pc_hash)."""
    h = 2166136261
    for c in s.encode('utf-8'):
        h = ((h ^ (c + 32 if 65 <= c <= 90 else c)) * 16777619) & 0xffffffff
    return h or 1


def guid_hash(s):
    h = 2166136261
    for c in s.encode('utf-8'): h = ((h ^ c) * 16777619) & 0xffffffff
    return h or 1


class PM(ListMachine):
    """The machine plus what the model and the page call that the shared mocks do not know: opendir / readdir over the card dict (self.fs: path -> bytes, self.dirs), __xstat's
    mtime, stdio over those bytes, the player (status, position, seek, speed), and a deque that copies the records it is given as the stock one does."""
    def __init__(self):
        super().__init__()
        self.mtime, self.dh, self.fp, self.sizes = {}, {}, {}, {}   # sizes: a file's st_size when it is not its bytes' length (a gigabyte episode)
        self.status = 2          # mclGetPlayStatus: 2 playing, 3 paused
        self.pt = (0, 0, 1)      # get_playtimeandlength: position, length, result
        self.seeks, self.speeds = [], []
        self.dent = self.alloc(300)
        self.dirs.update({'/mnt', '/mnt/mmc'})
        self.setword(PLAYSPEED_MODE, 0)

    def kids(self, path):
        names = set()
        for p in list(self.fs) + list(self.files) + list(self.dirs):
            if p != path and p.rsplit('/', 1)[0] == path: names.add(p.rsplit('/', 1)[1])
        return sorted(names)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'opendir':
            path = self.read_cstr(a0); self.calls.append(('opendir', path))
            if path in self.dirs:
                ret = self.alloc(8); self.dh[ret] = [self.kids(path), 0]
            else: ret = 0
        elif name == 'readdir':
            d = self.dh[a0]
            if d[1] < len(d[0]):
                nm = d[0][d[1]].encode('latin-1'); d[1] += 1
                self.u.mem_write(self.dent, bytes(300)); self.u.mem_write(self.dent + 11, nm + b'\0'); ret = self.dent
            else: ret = 0
        elif name == 'closedir':
            self.dh.pop(a0, None); ret = 0
        elif name == '__xstat':
            path = self.read_cstr(a1)
            if ('__xstat', path) in self.fail or not (path in self.fs or path in self.dirs or path in self.files): ret = 0xffffffff
            else:
                self.u.mem_write(a2, bytes(144)); self.setword(a2 + 0x40, self.mtime.get(path, 0)); self.setword(a2 + 0x30, self.sizes.get(path, len(self.fs.get(path, b'')))); ret = 0
            self.calls.append(('__xstat', a0, path))
        elif name == 'memmove':
            self.u.mem_write(a0, bytes(self.u.mem_read(a1, a2))); ret = a0
        elif name == 'fopen' and self.read_cstr(a0) in self.fs and 'w' not in self.read_cstr(a1) and self.read_cstr(a0) not in self.files:
            path = self.read_cstr(a0); h = self.alloc(4); self.fp[h] = [path, 0]; self.calls.append(('fopen', path, self.read_cstr(a1))); ret = h
        elif name == 'fread' and a3 in self.fp:
            path, pos = self.fp[a3]; data = self.fs[path][pos:pos + a1 * a2]
            if data: self.u.mem_write(a0, data)
            self.fp[a3][1] += len(data); ret = len(data) // a1
        elif name == 'fseek' and a0 in self.fp:
            path, pos = self.fp[a0]; self.fp[a0][1] = {0: a1, 1: pos + a1, 2: len(self.fs[path]) + a1}[a2]; ret = 0
        elif name == 'fclose' and a0 in self.fp:
            self.fp.pop(a0); ret = 0
        elif name == 'mclGetPlayStatus':
            ret = self.status
        elif name == 'get_playtimeandlength':
            self.calls.append(('get_playtimeandlength',)); pos, ln, r = self.pt
            self.setword(a0, pos); self.setword(a1, ln); ret = r
        elif name == 'seek_time':
            self.calls.append(('seek_time', a0)); self.seeks.append(a0); self.pt = (a0, self.pt[1], self.pt[2]); ret = 1
        elif name == 'mclSetPlaySpeed':
            self.calls.append(('mclSetPlaySpeed', a0)); self.speeds.append(a0); ret = 1
        elif name == '_deque_push_back':   # the stock copy function duplicates the record's strings; ours are heap strings of the mock, so the record alone is copied
            rec = self.alloc(REC_SIZE); self.u.mem_write(rec, bytes(self.u.mem_read(a1, REC_SIZE)))
            self.deques.setdefault(a0, []).append(rec); self.calls.append(('_deque_push_back', a0, rec)); ret = 0
        if ret is not None:
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    # ---- the card
    def put(self, path, data=b'', mtime=0):
        """A file (and every folder above it)."""
        self.fs[path] = data
        if mtime: self.mtime[path] = mtime
        d = path.rsplit('/', 1)[0]
        while d and d not in self.dirs: self.dirs.add(d); d = d.rsplit('/', 1)[0]

    def folder(self, path):
        d = path
        while d and d not in self.dirs: self.dirs.add(d); d = d.rsplit('/', 1)[0]

    # ---- the model's records
    def ep(self, a):
        raw = bytes(self.u.mem_read(a, O['PC_EP_SIZE']))
        cs = lambda b: b.split(b'\0', 1)[0].decode('utf-8', 'replace')
        g, p, d, l, h, s = struct.unpack_from('<6I', raw, O['PC_EP_GUID'])
        return dict(file=cs(raw[:O['PC_FILE']]), title=cs(raw[O['PC_FILE']:O['PC_EP_GUID'] - 0]), guid=g, pub=p, dur=d, length=l, hash=h, state=s, desc=cs(raw[O['PC_EP_DESC']:O['PC_EP_SIZE']]))

    def show(self, a):
        raw = bytes(self.u.mem_read(a, O['PC_SHOW_SIZE']))
        cs = lambda b: b.split(b'\0', 1)[0].decode('utf-8', 'replace')
        n, h, fresh, checked = struct.unpack_from('<4I', raw, O['PC_SH_COUNT'])
        return dict(dir=cs(raw[:128]), title=cs(raw[128:224]), cover=cs(raw[224:352]), feed=cs(raw[O['PC_SH_FEED']:O['PC_SH_IMAGE']]), image=cs(raw[O['PC_SH_IMAGE']:O['PC_SH_COUNT']]), count=n, hash=h, fresh=fresh, checked=checked,
                    author=cs(raw[O['PC_SH_AUTHOR']:O['PC_SH_CAT']]), category=cs(raw[O['PC_SH_CAT']:O['PC_SH_DESC']]), desc=cs(raw[O['PC_SH_DESC']:O['PC_SH_NEWEST']]), newest=struct.unpack_from('<I', raw, O['PC_SH_NEWEST'])[0],
                    modified=struct.unpack_from('<I', raw, O['PC_SH_MODIFIED'])[0])

    # ---- the payload's entry points
    def parse_eps(self, text, mx=300):
        raw = text if isinstance(text, bytes) else text.encode('utf-8')
        buf, out = self.alloc(len(raw) + 1), self.ep_buffer(mx)
        self.u.mem_write(buf, raw + b'\0'); self.u.mem_write(out, bytes(mx * O['PC_EP_SIZE']))
        n = self.call(PSYMS['pc_parse_eps'], a0=buf, a1=len(raw), a2=out, a3=mx, count=20000000)
        return [self.ep(out + i * O['PC_EP_SIZE']) for i in range(n)]

    def shows(self, mx=40):
        out = self.alloc(mx * O['PC_SHOW_SIZE']); self.u.mem_write(out, bytes(mx * O['PC_SHOW_SIZE']))
        n = self.call(PSYMS['pc_scan_shows'], a0=out, a1=mx, count=200000000)
        return [self.show(out + i * O['PC_SHOW_SIZE']) for i in range(n)], out

    def ep_buffer(self, mx):
        """One zeroed-by-the-caller output array of mx episodes per machine and size: the records are big (456 bytes) and a test reads them hundreds of times."""
        bufs = self.__dict__.setdefault('_ep_buffers', {})
        if mx not in bufs: bufs[mx] = self.alloc(mx * O['PC_EP_SIZE'])
        return bufs[mx]

    def episodes(self, show_addr, mx=300):
        out = self.ep_buffer(mx); self.u.mem_write(out, bytes(mx * O['PC_EP_SIZE']))
        n = self.call(PSYMS['pc_load_show'], a0=show_addr, a1=out, a2=mx, count=400000000)
        return [self.ep(out + i * O['PC_EP_SIZE']) for i in range(n)]

    def state(self, h):
        pos, ln = self.alloc(4), self.alloc(4)
        s = self.call(PSYMS['pc_state'], a0=h, a1=pos, a2=ln, count=2000000)
        return s, self.word(pos), self.word(ln)

    def note(self, rec, count=20000000):
        return self.call(PSYMS['pc_note'], a0=rec, count=count)

    def track(self, path, title='T'):
        t = self.record(album='A', artist='B', path=path, title=title, name=path.rsplit('/', 1)[1])
        self.play([t], 0)
        return t

    def ring(self):
        """(slot count, [(hash, pos, len, flags)]) of the ring file, or None."""
        data = self.fs.get(RING)
        if data is None: return None
        assert data[:4] == b'PCR1', data[:4]
        n = struct.unpack_from('<I', data, 4)[0]
        assert len(data) == 8 + 16 * n, (len(data), n)
        return n, [struct.unpack_from('<4I', data, 8 + 16 * i) for i in range(n)]


def card_machine(cls=PM):
    """A card with three shows: Alpha Show (no metadata), bravo (with .episodes) and The Daily (a .show file); Empty has no episode."""
    m = cls()
    for f, mt in (('ep1.mp3', 1000), ('ep2.mp3', 2000), ('Ep10.M4A', 2000)): m.put(f'{ROOT}/Alpha Show/{f}', b'', mt)
    m.put(f'{ROOT}/Alpha Show/notes.txt'); m.put(f'{ROOT}/Alpha Show/cover.JPG', b'x'); m.put(f'{ROOT}/Alpha Show/folder.png', b'x'); m.put(f'{ROOT}/Alpha Show/.DS_Store')
    m.put(f'{ROOT}/bravo/b1.mp3', b'', 10); m.put(f'{ROOT}/bravo/b2.mp3', b'', 20); m.put(f'{ROOT}/bravo/b3.mp3.part'); m.put(f'{ROOT}/bravo/extra.mp3', b'', 3500)
    m.put(f'{ROOT}/bravo/b5.mp3', b'', 42)
    m.put(f'{ROOT}/bravo/.episodes', (EPS_HEAD +
          'g=g1\tp=3000\td=600\tl=1000\tf=b1.mp3\tt=Bravo One\n'
          'g=g2\tp=5000\td=1200\tf=b2.mp3\tt=Bravo Two\tu=https://e.example/b2.mp3\n'
          'g=g3\tp=4000\tf=b3.mp3\tt=Three (part)\tu=https://e.example/b3.mp3\n'
          'g=g4\tp=6000\tf=b4.mp3\tt=Four (remote)\tu=https://e.example/b4.mp3?sig=1\n'
          'g=g5\tf=b5.mp3\n').encode())
    m.put(f'{ROOT}/The Daily/d1.mp3', b'', 7)
    m.put(f'{ROOT}/The Daily/.show', b'M1PLUS-SHOW 1\ntitle=The Daily News\nfeed=https://daily.example/rss\nimage=https://daily.example/i.jpg\n')
    m.folder(f'{ROOT}/Empty'); m.put(f'{ROOT}/.hidden/h.mp3'); m.put(f'{ROOT}/loose.mp3')
    m.put(f'{ROOT}/MetaOnly/.episodes', (EPS_HEAD + 'g=m1\tp=9\tf=m1.mp3\tt=Not yet\tu=https://e.example/m1\n').encode())
    return m


# ---------------------------------------------------------------------------
def text_tests(ctx):
    """The two text formats, the date, the hash, the path test, the number format."""
    expect = ctx.expect
    m = PM()
    fixture = (EPS_HEAD + '# a comment line\n'
               'g=guid-1\tp=1700000000\td=2700\tl=1234567\tf=ep one.mp3\tt=Episode One\tu=https://example.com/a.mp3?sig=abc\n'
               'g=guid-2\tp=1700100000\td=3000\tf=ep2.mp3\tt=Second – Café\n'
               'x=only a description\tp=5\n'
               'p=1\td=2\n'
               't=Title only\tz=unknown key\n'
               'g=guid-3\tf=gone.mp3\tt=Remote\tu=https://example.com/c.mp3\tl=99\n')
    e = m.parse_eps(fixture)
    expect(len(e) == 4 and [x['title'] for x in e] == ['Episode One', 'Second – Café', 'Title only', 'Remote'],
           f'the metadata file: an entry per line with a key (the comment, the description-only and the date-only lines are not entries): {[x["title"] for x in e]}')
    expect((e[0]['guid'], e[0]['pub'], e[0]['dur'], e[0]['length'], e[0]['file'], e[0]['state']) == (guid_hash('guid-1'), 1700000000, 2700, 1234567, 'ep one.mp3', O['PC_REMOTE'])
           and e[1]['length'] == 0 and e[2]['file'] == '' and e[2]['guid'] == 0 and e[3]['length'] == 99 and e[3]['file'] == 'gone.mp3',
           'the fields: g (hashed), p, d, l, f, t; a missing field is 0 or empty; the url (u) is for the subscribe phase and is not kept; an entry starts as PC_REMOTE (the merge decides)')
    expect(len(m.parse_eps(fixture, 2)) == 2, 'at most max entries')
    expect(m.parse_eps(fixture.replace('\n', '\r\n'))[0]['title'] == 'Episode One' and len(m.parse_eps(fixture.replace('\n', '\r\n'))) == 4, 'CRLF line ends read the same')
    expect(m.parse_eps(fixture.replace('1\n', '2\n', 1)) == [] and m.parse_eps(fixture.split('\n', 1)[1]) == [] and m.parse_eps('') == [] and m.parse_eps(b'\xff\xfe junk') == []
           and m.parse_eps('m1plus-episodes 1\ng=x\n')[0]['guid'] == guid_hash('x') and m.parse_eps('M1PLUS-EPISODES 1 \ng=x\n') == [],
           'a file with another version, no header, no content or binary junk gives no entries (the header line is exact, its case aside)')
    long = 'é' * 100
    e = m.parse_eps(EPS_HEAD + f't={long}\tf={"f" * 127}\n')
    expect(e[0]['title'] == 'é' * 47 and e[0]['file'] == 'f' * 127, 'a title is cut before a continuation byte (47 two-byte characters in 95 bytes), a file name of 127 bytes fits')
    e = m.parse_eps(EPS_HEAD + f'f={"f" * 128}\n' + f't=x\tf={"g" * 130}\n')
    expect(len(e) == 1 and e[0]['file'] == '', 'a file name that does not fit is no file name (an entry with nothing else is dropped)')
    expect(m.parse_eps(EPS_HEAD + 'p=99999999999999\td=4294967295\tt=big\n')[0]['pub'] == 0xfffffffe, 'a number too large saturates instead of wrapping')
    expect(m.parse_eps(EPS_HEAD + 't=a\tb\tt\t=c\tt=d\n')[0]['title'] == 'd', 'fields without a key are skipped; the last of a key wins')
    # the show file
    sh = m.alloc(O['PC_SHOW_SIZE']); m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    txt = 'M1PLUS-SHOW 1\ntitle=My Show\nfeed=https://f.example/rss\nimage=https://f.example/i.jpg\nother=1\n'
    buf = m.cstr(txt)
    expect(m.call(PSYMS['pc_parse_show'], a0=buf, a1=len(txt), a2=sh, count=2000000) == 1 and m.show(sh)['title'] == 'My Show' and m.show(sh)['feed'] == 'https://f.example/rss'
           and m.show(sh)['image'] == 'https://f.example/i.jpg', 'the show file: title, feed and image')
    buf = m.cstr('title=x\n'); m.u.mem_write(sh, bytes(O['PC_SHOW_SIZE']))
    expect(m.call(PSYMS['pc_parse_show'], a0=buf, a1=8, a2=sh, count=2000000) == 0 and m.show(sh)['title'] == '', 'a show file without its header is ignored')
    out = m.alloc(64)
    # the hash and the paths
    for s in ('/mnt/mmc/Podcasts/Show/ep.mp3', '', 'a', 'CAFÉ x'):
        buf = m.cstr(s)
        expect(m.call(PSYMS['pc_hash'], a0=buf, count=200000) == pc_hash(s), f'pc_hash({s!r}) is FNV-1a over the ASCII-lower-cased bytes')
    a, b = m.cstr('/MNT/MMC/PODCASTS/Show/Ep.MP3'), m.cstr('/mnt/mmc/podcasts/show/ep.mp3')
    expect(m.call(PSYMS['pc_hash'], a0=a, count=200000) == m.call(PSYMS['pc_hash'], a0=b, count=200000), 'the case of the path does not change the key')
    for path, want in (('/mnt/mmc/Podcasts/Show/ep.mp3', 1), ('/mnt/mmc/podcasts/Show/Sub/ep.mp3', 1), ('/MNT/MMC/PODCASTS/S/e', 1), ('/mnt/mmc/Podcasts/ep.mp3', 0), ('/mnt/mmc/Podcasts/Show/', 0),
                       ('/mnt/mmc/Podcasts//ep.mp3', 0), ('/mnt/mmc/Podcasts/', 0), ('/mnt/mmc/Podcast/Show/ep.mp3', 0), ('/mnt/mmc/Music/Podcasts/Show/ep.mp3', 0), ('', 0)):
        expect(m.call(PSYMS['pc_is_path'], a0=m.cstr(path), count=200000) == want, f'pc_is_path({path!r}) is {want}')
    expect(m.call(PSYMS['pc_show_of'], a0=m.cstr('/mnt/mmc/Podcasts/My Show/ep.mp3'), count=200000) == pc_hash('My Show')
           and m.call(PSYMS['pc_show_of'], a0=m.cstr('/mnt/mmc/Music/a.mp3'), count=200000) == 0, 'the show of a path is the hash of its folder name; another path has none')
    # the number format
    for fmt, n, want in (('%d min left', 5, '5 min left'), ('%d', 0, '0'), ('Played', 7, 'Played'), ('%d episodes', 1234567, '1234567 episodes'), ('Odcinki: %d', 40, 'Odcinki: 40')):
        m.call(PSYMS['pc_fmt'], a0=out, a1=16, a2=m.cstr(fmt), a3=n, count=200000)
        expect(m.read_cstr(out) == want[:15], f'pc_fmt({fmt!r}, {n}) = {want[:15]!r}')


def scan_tests(ctx):
    """The shows and the episodes of a card: the metadata merge, the order, the states, the fall-back without metadata, the limits."""
    expect = ctx.expect
    m = card_machine()
    shows, arr = m.shows()
    expect([s['title'] for s in shows] == ['bravo', 'Alpha Show', 'MetaOnly', 'The Daily News'],
           f'the shows are the folders with an episode file or a metadata file, the most recently updated first (the newest episode: bravo 6000, Alpha Show 2000, MetaOnly 9, The Daily 7); Empty, the dot folder and the loose file are not shows: {[s["title"] for s in shows]}')
    expect([s['newest'] for s in shows] == [6000, 2000, 9, 7],
           f'newest: the largest p= of the entries (bravo; a remote episode counts), else the newest file\'s date (Alpha Show, The Daily), a metadata-only show its entry\'s ({[s["newest"] for s in shows]})')
    by = {s['dir']: s for s in shows}
    expect(by['Alpha Show']['count'] == 3 and by['bravo']['count'] == 4 and by['The Daily']['count'] == 1 and by['MetaOnly']['count'] == 0,
           f'the count is the files on the card: .part files, other files and metadata entries without a file are not counted ({[(s["dir"], s["count"]) for s in shows]})')
    expect(by['Alpha Show']['cover'] == 'cover.JPG' and by['bravo']['cover'] == '', 'the cover is cover.* before folder.* (any case), none when there is no picture')
    expect(by['The Daily']['title'] == 'The Daily News' and by['The Daily']['feed'] == 'https://daily.example/rss' and by['The Daily']['image'] == 'https://daily.example/i.jpg'
           and by['Alpha Show']['feed'] == '' and by['Alpha Show']['hash'] == pc_hash('Alpha Show'), 'a show file gives the title, the feed and the image url; the folder name is the title otherwise, and its hash the show key')
    expect(all(s['fresh'] == s['count'] for s in shows), 'every episode is new (no place saved, not played)')
    expect(len(m.shows(2)[0]) == 2, 'at most max shows')
    # without metadata: the file names and dates
    alpha = arr + O['PC_SHOW_SIZE'] * [s['dir'] for s in shows].index('Alpha Show')
    e = m.episodes(alpha)
    expect([x['file'] for x in e] == ['ep2.mp3', 'Ep10.M4A', 'ep1.mp3'] and [x['title'] for x in e] == ['ep2', 'Ep10', 'ep1'] and [x['pub'] for x in e] == [2000, 2000, 1000],
           f'no metadata: the episodes are the audio files (mp3 m4a ...; not notes.txt, the picture or a dot file), the title the name without its extension, the date the file\'s, newest first, ties by name descending: {[x["file"] for x in e]}')
    expect(all(x['state'] == O['PC_LOCAL'] and x['dur'] == 0 and x['guid'] == 0 and x['hash'] == pc_hash(f'{ROOT}/Alpha Show/{x["file"]}') for x in e),
           'they are PC_LOCAL with no duration, and the ring key is the hash of the full path')
    # with metadata
    bravo = arr + O['PC_SHOW_SIZE'] * [s['dir'] for s in shows].index('bravo')
    e = m.episodes(bravo)
    expect([x['file'] for x in e] == ['b4.mp3', 'b2.mp3', 'b3.mp3', 'extra.mp3', 'b1.mp3', 'b5.mp3'], f'with metadata: the entries and the files together, newest first by the entry\'s date: {[x["file"] for x in e]}')
    expect([x['state'] for x in e] == [O['PC_REMOTE'], O['PC_LOCAL'], O['PC_PART'], O['PC_LOCAL'], O['PC_LOCAL'], O['PC_LOCAL']],
           'an entry with its file is PC_LOCAL, one with only name.part is PC_PART, one with neither is PC_REMOTE, a file with no entry is PC_LOCAL')
    expect([x['title'] for x in e] == ['Four (remote)', 'Bravo Two', 'Three (part)', 'extra', 'Bravo One', 'b5']
           and [x['pub'] for x in e] == [6000, 5000, 4000, 3500, 3000, 42] and e[4]['dur'] == 600 and e[4]['length'] == 1000 and e[1]['dur'] == 1200,
           f'titles, dates, durations and lengths come from the metadata; a missing title is the file name, a missing date the file\'s ({[x["title"] for x in e]})')
    expect([x['hash'] != 0 for x in e] == [False, True, False, True, True, True] and e[1]['hash'] == pc_hash(f'{ROOT}/bravo/b2.mp3') and e[1]['guid'] == guid_hash('g2'),
           'only a local file has a ring key; the guid is kept as its hash')
    expect([x['file'] for x in m.episodes(bravo, 3)] == ['b4.mp3', 'b2.mp3', 'b3.mp3'], 'at most max episodes: the newest')
    # a metadata-only show
    only = arr + O['PC_SHOW_SIZE'] * [s['dir'] for s in shows].index('MetaOnly')
    e = m.episodes(only)
    expect(len(e) == 1 and e[0]['state'] == O['PC_REMOTE'] and e[0]['title'] == 'Not yet' and e[0]['hash'] == 0, 'a show with metadata and no file lists its episode as PC_REMOTE')
    # limits and stray names
    m2 = card_machine()
    m2.put(f'{ROOT}/x/' + 'n' * 130 + '.mp3'); m2.put(f'{ROOT}/' + 'L' * 130 + '/a.mp3')
    shows2, arr2 = m2.shows()
    expect([s['title'] for s in shows2] == ['bravo', 'Alpha Show', 'MetaOnly', 'The Daily News'],
           'a folder name or a file name that does not fit the buffers (127 bytes) is skipped: a folder with nothing else is no show')
    m3 = PM()
    for i in range(350): m3.put(f'{ROOT}/Big/{i:03}.mp3', b'', 1000 + i)
    shows3, arr3 = m3.shows()
    e = m3.episodes(arr3)
    expect(shows3[0]['count'] == 350 and len(e) == 300 and e[0]['file'] == '349.mp3' and e[-1]['file'] == '050.mp3', f'at most 300 episodes are kept, the newest ({len(e)}, {e[0]["file"]}..{e[-1]["file"]})')
    m4 = PM()
    for i in range(45): m4.put(f'{ROOT}/S{i:02}/a.mp3')
    expect(len(m4.shows(40)[0]) == 40, 'the page asks for 40 shows at most')
    # the folder's spelling and absence
    out = m.alloc(64)
    expect(m.call(PSYMS['pc_root'], a0=out, count=2000000) == 1 and m.read_cstr(out) == ROOT, 'pc_root: the folder as the card has it')
    m5 = PM(); m5.put('/mnt/mmc/podcasts/Show/a.mp3'); m5.put('/mnt/mmc/Music/podcasts.txt')
    out = m5.alloc(64)
    expect(m5.call(PSYMS['pc_root'], a0=out, count=2000000) == 1 and m5.read_cstr(out) == '/mnt/mmc/podcasts' and m5.shows()[0][0]['dir'] == 'Show',
           'a folder spelled podcasts (the card is case-sensitive) is found, and its shows are listed')
    m6 = PM(); m6.folder('/mnt/mmc/Music')
    out = m6.alloc(64)
    expect(m6.call(PSYMS['pc_root'], a0=out, count=2000000) == 0 and m6.shows()[0] == [], 'no Podcasts folder: no root, no shows')
    # the dates: a stat that fails leaves 0
    m7 = PM(); m7.put(f'{ROOT}/Z/z.mp3', b'', 5); m7.fail.add(('__xstat', f'{ROOT}/Z/z.mp3'))
    s7, a7 = m7.shows()
    expect(m7.episodes(a7)[0]['pub'] == 0 and m7.episodes(a7)[0]['title'] == 'z', 'a file whose stat fails is still an episode (date 0)')
    # the fresh count follows the ring
    m.call(PSYMS['pc_mark'], a0=pc_hash(f'{ROOT}/Alpha Show/ep1.mp3'), a1=1, count=20000000)
    m.call(PSYMS['pc_mark'], a0=pc_hash(f'{ROOT}/Alpha Show/ep2.mp3'), a1=1, count=20000000)
    shows, _ = m.shows()
    expect({s['dir']: s['fresh'] for s in shows} == {'Alpha Show': 1, 'bravo': 4, 'The Daily': 1, 'MetaOnly': 0}, f'the new count drops for played episodes ({[(s["dir"], s["fresh"]) for s in shows]})')


# ---------------------------------------------------------------------------
def ring_tests(ctx):
    """The ring of places: save, load, the edges, played marks, the file format, capacity, and what a card that is not there does."""
    expect = ctx.expect
    ep = lambda n: f'{ROOT}/Alpha Show/ep{n}.mp3'
    H1, H2 = pc_hash(ep(1)), pc_hash(ep(2))
    m = PM()
    music = m.record(path='/mnt/mmc/Music/a.flac')
    m.play([music], 0); m.pt = (50, 200, 1)
    m.note(music)
    expect('get_playtimeandlength' not in m.names() and not m.fs and m.state(H1) == (0, 0, 0), 'music: pc_note looks at nothing and writes nothing')
    rec = m.track(ep(1)); m.pt = (100, 3000, 1)
    m.note(rec)
    expect(m.state(H1) == (1, 100, 3000), 'a podcast at 100 s of 3000: a place')
    expect(RING not in m.fs, 'and not written yet (the ring is written at most every 30 s while an episode plays)')
    m.clock += 31000; m.pt = (131, 3000, 1); m.note(rec)
    expect(m.ring() == (1, [(H1, 131, 3000, 0)]), f'after 30 s: written, "PCR1", the count, then the slots (hash, position, length, flags): {m.ring()}')
    expect(RING + '.tmp' not in m.fs and ('rename', RING + '.tmp', RING) in m.calls and ('mkdir', '/mnt/mmc/.m1plus') in m.calls and ('mkdir', STATE) in m.calls, 'atomically: a temp file, then rename; the folders are made')
    m.pt = (140, 3000, 1); m.status = 3; m.note(rec)
    expect(m.ring() == (1, [(H1, 140, 3000, 0)]), 'paused: written at once')
    m.status = 3; m.note(rec)
    expect(not [c for c in m.calls if c[0] == 'open'], 'unchanged: nothing is written again')
    # the edges
    m.status = 2; m.clock += 31000
    m.pt = (10, 3000, 1); m.note(rec)
    expect(m.state(H1) == (1, 140, 3000), 'the first seconds are no place: the one saved stays')
    rec2 = m.track(ep(2)); m.pt = (10, 3000, 1); m.note(rec2)
    expect(m.state(H2) == (0, 0, 0), 'a new episode in its first 30 s gets no slot')
    m.pt = (29, 3000, 1); m.note(rec2)
    expect(m.state(H2)[0] == 0, 'at 29 s still none')
    m.pt = (30, 3000, 1); m.note(rec2)
    expect(m.state(H2) == (1, 30, 3000), 'at 30 s there is a place')
    m.pt = (269, 300, 1); m.note(rec2)
    expect(m.state(H2) == (1, 269, 300), 'a 5 minute episode, 31 s from the end: still a place')
    m.pt = (270, 300, 1); m.note(rec2)
    expect(m.state(H2) == (2, 0, 300), '30 s from the end: played (the place is cleared)')
    m.pt = (500, 3000, 1); m.note(rec2)
    expect(m.state(H2) == (1, 500, 3000), 'played, then heard again from the middle: a place again, no longer played')
    m.pt = (2850, 3000, 1); m.note(rec2)
    expect(m.state(H2)[0] == 2, '95 % of a long episode: played (before the last 30 s when it is long)')
    m.pt = (2849, 3000, 1); m.note(rec2)
    expect(m.state(H2) == (1, 2849, 3000), 'just under 95 %: a place')
    m.pt = (70, 100, 1); m.note(rec2)
    expect(m.state(H2)[0] == 2, 'a 100 s episode at 70 s: played (the last 30 s)')
    # a track change leaves the last place and writes it
    rec1 = m.track(ep(1)); m.pt = (777, 3000, 1); m.note(rec1)
    m.clock += 100; music_rec = m.record(path='/mnt/mmc/Music/b.flac'); m.play([music_rec], 0)
    m.calls = []; m.note(music_rec)
    ring = m.ring()
    expect(m.state(H1)[:2] == (1, 777) and ring[1][0][0] == H1 and ring[1][0][1] == 777 and 'mclSetPlaySpeed' not in m.names(), 'a track change leaves the place last seen and writes it')
    expect([s[0] for s in ring[1]] == [H1, H2], 'most recent first')
    # marks
    m.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000)
    expect(m.state(H1) == (2, 0, 3000) and m.ring()[1][0][3] == 1, 'pc_mark played: a played slot, written at once')
    r0 = m.call(PSYMS['pc_rev'], count=200000)
    m.call(PSYMS['pc_mark'], a0=H1, a1=0, count=30000000)
    expect(m.state(H1)[0] == 0 and H1 not in [s[0] for s in m.ring()[1]] and m.call(PSYMS['pc_rev'], count=200000) == r0 + 1, 'pc_mark new again: the slot is gone, written, the revision grows')
    m.call(PSYMS['pc_mark'], a0=pc_hash('nothing'), a1=0, count=30000000)
    expect(m.call(PSYMS['pc_rev'], count=200000) == r0 + 1, 'forgetting what was never there changes nothing')
    m.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000)
    m.call(PSYMS['pc_restart'], a0=H1, count=30000000)
    expect(m.state(H1)[0] == 0, 'pc_restart: a played episode starts new')
    m.call(PSYMS['pc_mark'], a0=H2, a1=0, count=30000000); m.pt = (500, 3000, 1); m.note(m.track(ep(2)))
    m.call(PSYMS['pc_restart'], a0=H2, count=30000000)
    expect(m.state(H2) == (1, 500, 3000), 'pc_restart leaves a place alone (the jump to it is pc_note\'s)')
    # a new machine reads the file back
    m.call(PSYMS['pc_flush'], count=30000000)
    m2 = PM(); m2.fs[RING] = m.fs[RING]; m2.dirs.add(STATE)
    expect(m2.state(H2) == m.state(H2) and m2.state(pc_hash('x'))[0] == 0, 'the file is read at the first look')
    m2.call(PSYMS['pc_mark'], a0=pc_hash('y'), a1=1, count=30000000)
    expect(m2.ring()[1][0][0] == pc_hash('y') and [s[0] for s in m2.ring()[1]][1:] == [s[0] for s in m.ring()[1]], 'and kept when a new slot is written')
    # damaged files are an empty ring
    good = m.fs[RING]
    for what, data in (('bad magic', b'XXXX' + good[4:]), ('count over 512', b'PCR1' + struct.pack('<I', 513) + bytes(16 * 513)), ('truncated', good[:-5]), ('empty', b''), ('short', b'PCR1')):
        m3 = PM(); m3.fs[RING] = data
        expect(m3.state(H2)[0] == 0, f'{what}: an empty ring')
    # capacity
    m4 = PM()
    for i in range(520): m4.call(PSYMS['pc_mark'], a0=1000 + i, a1=1, count=60000000)
    n, slots = m4.ring()
    expect(n == 512 and slots[0][0] == 1519 and slots[-1][0] == 1008 and len(m4.fs[RING]) == 8 + 512 * 16 and m4.state(1000)[0] == 0 and m4.state(1519)[0] == 2,
           f'512 places (q2-pod\'s ring): the newest first, the oldest 8 gone ({n}, {slots[0][0]}, {slots[-1][0]})')
    # a card that is not there
    m5 = PM(); m5.card_mounted = False
    m5.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000)
    expect(RING not in m5.fs and m5.state(H1)[0] == 2 and not [c for c in m5.calls if c[0] == 'mkdir'], 'no card mounted: nothing is written, the mark is kept in memory')
    m5.card_mounted = True; m5.call(PSYMS['pc_flush'], count=30000000)
    expect(m5.ring() == (1, [(H1, 0, 0, 1)]), 'and written at the next flush once the card is back')
    m6 = PM(); m6.fail.add(('write', RING + '.tmp'))
    m6.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000)
    expect(RING not in m6.fs and RING + '.tmp' not in m6.fs and ('unlink', RING + '.tmp') in m6.calls, 'a failed write leaves no file and no temp file')
    m6.fail.clear(); m6.call(PSYMS['pc_flush'], count=30000000)
    expect(m6.ring() == (1, [(H1, 0, 0, 1)]), 'and is tried again at the next flush')
    m7 = PM(); m7.fail.add(('rename', RING))
    m7.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000)
    expect(RING not in m7.fs and ('unlink', RING + '.tmp') in m7.calls, 'a failed rename removes the temp file')
    # no memory: the feature does nothing, nothing crashes
    m8 = PM(); m8.calloc_fail = True
    m8.call(PSYMS['pc_mark'], a0=H1, a1=1, count=30000000); rec = m8.track(ep(1)); m8.pt = (100, 3000, 1); m8.note(rec)
    expect(m8.state(H1)[0] == 0 and RING not in m8.fs, 'without memory for the ring places are not kept (and nothing breaks)')


def resume_tests(ctx):
    """The jump to a saved place after an episode starts (the stock seek), and when it does not happen."""
    expect = ctx.expect
    ep = f'{ROOT}/Alpha Show/ep1.mp3'
    H = pc_hash(ep)
    def machine(place=(500, 3000)):
        m = PM()
        if place: m.fs[RING] = b'PCR1' + struct.pack('<I', 1) + struct.pack('<4I', H, place[0], place[1], 0)   # a ring file with the one place
        m.clock = 100000
        return m
    m = machine()
    expect(m.state(H) == (1, 500, 3000), 'a place of 500 s is saved')
    rec = m.track(ep); m.pt = (0, 3000, 1); m.note(rec)
    expect(m.seeks == [], 'the episode has just been started (second 0): not yet')
    m.pt = (2, 3000, 1); m.note(rec)
    expect(m.seeks == [500], f'at second 2, playing: the stock seek to the place ({m.seeks})')
    m.note(rec)
    expect(m.seeks == [500] and m.state(H) == (1, 500, 3000), 'once; the place is not recorded over by the seconds before the jump')
    m.pt = (3, 3000, 1); m.clock += 500; m.note(rec)
    expect(m.state(H) == (1, 500, 3000), 'just after the jump the player\'s second is not trusted (2 s)')
    m.pt = (503, 3000, 1); m.clock += 2500; m.note(rec)
    expect(m.state(H) == (1, 503, 3000), 'then it is recorded again')
    # not while paused, not when late, not when it never starts
    m = machine(); rec = m.track(ep); m.status = 3; m.pt = (2, 3000, 1); m.note(rec)
    expect(m.seeks == [], 'paused at the start: no jump (it waits for Play)')
    m.status = 2; m.note(rec)
    expect(m.seeks == [500], 'playing: the jump')
    m = machine(); rec = m.track(ep); m.pt = (5, 3000, 1); m.note(rec)
    expect(m.seeks == [] and m.state(H) == (1, 500, 3000), 'first seen at 5 s: too late to jump, the place is not forgotten')
    m = machine(); rec = m.track(ep); m.pt = (0, 3000, 1); m.note(rec); m.clock += 16000; m.note(rec)
    expect(m.seeks == [], 'a jump that has not happened after 15 s is dropped')
    m.pt = (3, 3000, 1); m.note(rec)
    expect(m.seeks == [] and m.state(H) == (1, 500, 3000), 'and the first seconds then do not forget the place')
    m = machine(); rec = m.track(ep); m.pt = (600, 3000, 1); m.note(rec)
    expect(m.seeks == [] and m.state(H) == (1, 600, 3000), 'an episode already past its place: nothing to jump to')
    # an episode with no place, a played one, and a place under the edge
    m = PM(); rec = m.track(ep); m.pt = (2, 3000, 1); m.note(rec)
    expect(m.seeks == [], 'no place: no jump')
    m = PM(); m.call(PSYMS['pc_mark'], a0=H, a1=1, count=30000000); rec = m.track(ep); m.pt = (2, 3000, 1); m.note(rec)
    expect(m.seeks == [], 'a played episode starts from the beginning')
    m = PM(); rec = m.track(ep); m.pt = (30, 3000, 1); m.note(rec); m.note(m.record(path='/mnt/mmc/Music/a.flac')); m.status = 2
    rec = m.track(ep); m.pt = (1, 3000, 1); m.note(rec)
    expect(m.seeks == [30], 'a place at the 30 s edge is a place')
    # a player with no length yet
    m = machine(); rec = m.track(ep); m.pt = (2, 0, 1); m.note(rec); m.pt = (2, 3000, 0); m.note(rec)
    expect(m.seeks == [], 'no length, or a failed call: nothing happens')
    m.pt = (2, 3000, 1); m.note(rec)
    expect(m.seeks == [500], 'then the jump')


def speed_tests(ctx):
    """The speed per show: the table file, the stock mode and message, and putting it back for music."""
    expect = ctx.expect
    SH = pc_hash('Alpha Show')
    ep = f'{ROOT}/Alpha Show/ep1.mp3'
    m = PM()
    expect(m.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 0, 'a show with no speed set: 1x (mode 0)')
    ok = m.call(PSYMS['pc_speed_set'], a0=SH, a1=2, count=30000000); set_calls = list(m.calls)
    expect(ok == 1 and m.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 2, 'set 1.5x (mode 2): kept')
    d = m.fs[SPEED]
    expect(d[:4] == b'PCS1' and struct.unpack_from('<I', d, 4)[0] == 1 and struct.unpack_from('<2I', d, 8) == (SH, 2) and len(d) == 16, f'the file: "PCS1", the count, (show hash, mode) pairs ({d!r})')
    expect(('rename', SPEED + '.tmp', SPEED) in set_calls, 'written atomically')
    for bad in (4, -1, 100):
        expect(m.call(PSYMS['pc_speed_set'], a0=SH, a1=bad, count=30000000) == 0 and m.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 2, f'mode {bad} is refused, the old one stays')
    expect(m.call(PSYMS['pc_speed_set'], a0=0, a1=1, count=30000000) == 0, 'no show, no speed')
    m2 = PM(); m2.fs[SPEED] = m.fs[SPEED]
    expect(m2.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 2 and m2.call(PSYMS['pc_speed_get'], a0=SH + 1, count=2000000) == 0, 'the file is read back; another show is 1x')
    m2.fs[SPEED] = b'PCS1' + struct.pack('<I', 1) + struct.pack('<2I', SH, 9)
    m3 = PM(); m3.fs[SPEED] = m2.fs[SPEED]
    expect(m3.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 0, 'a stored mode of 4 or more is 1x (as stock reads PLAYSPEED)')
    for what, data in (('bad magic', b'XXXX' + bytes(12)), ('count over 64', b'PCS1' + struct.pack('<I', 65) + bytes(8 * 65)), ('truncated', b'PCS1' + struct.pack('<I', 3) + bytes(8))):
        m4 = PM(); m4.fs[SPEED] = data
        expect(m4.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 0, f'{what}: no speeds')
    m5 = PM()
    for i in range(70): m5.call(PSYMS['pc_speed_set'], a0=100 + i, a1=1 + i % 3, count=30000000)
    expect(struct.unpack_from('<I', m5.fs[SPEED], 4)[0] == 64 and m5.call(PSYMS['pc_speed_get'], a0=100, count=2000000) == 0 and m5.call(PSYMS['pc_speed_get'], a0=169, count=2000000) == 1 + 69 % 3,
           '64 shows; the oldest are forgotten')
    m6 = PM(); m6.fail.add(('write', SPEED + '.tmp'))
    expect(m6.call(PSYMS['pc_speed_set'], a0=SH, a1=1, count=30000000) == 0 and m6.call(PSYMS['pc_speed_get'], a0=SH, count=2000000) == 0, 'a failed save: reported, and the old table (none) stays')
    m6.card_mounted = False
    expect(m6.call(PSYMS['pc_speed_set'], a0=SH, a1=1, count=30000000) == 0, 'no card: not saved')
    # apply: the stock mode global and the player message, only when it changes
    m = PM(); m.call(PSYMS['pc_speed_set'], a0=SH, a1=2, count=30000000); m.calls = []
    m.call(PSYMS['pc_speed_apply'], a0=SH, count=3000000)
    expect(m.speeds == [2] and m.word(PLAYSPEED_MODE) == 2, 'pc_speed_apply: playspeed_mode = 2 and mclSetPlaySpeed(2)')
    m.call(PSYMS['pc_speed_apply'], a0=SH, count=3000000)
    expect(m.speeds == [2], 'again: nothing to change')
    m = PM(); m.call(PSYMS['pc_speed_apply'], a0=SH, count=3000000)
    expect(m.speeds == [] and m.word(PLAYSPEED_MODE) == 0, 'a show at 1x with the player at 1x: nothing is sent')
    # pc_note: an episode starting takes its show's speed; music takes the old one back (after the page's grace)
    m = PM(); m.call(PSYMS['pc_speed_set'], a0=SH, a1=3, count=30000000); m.setword(PLAYSPEED_MODE, 1); m.clock = 100000
    rec = m.track(ep); m.pt = (5, 3000, 1); m.note(rec)
    expect(m.speeds == [3] and m.word(PLAYSPEED_MODE) == 3, 'an episode of the show started by another page takes the show\'s speed (3 over the stock 1)')
    music = m.record(path='/mnt/mmc/Music/a.flac'); m.play([music], 0)
    m.clock += 5000; m.note(music)
    expect(m.speeds == [3], 'music right after (within 15 s of the speed being set): nothing yet, the episode may be about to start')
    m.clock += 20000; m.note(music)
    expect(m.speeds == [3, 1] and m.word(PLAYSPEED_MODE) == 1, 'music a while later: the speed of before is back (stock mode 1)')
    m.note(music)
    expect(m.speeds == [3, 1], 'once')
    # the page sets the speed before the episode: the music still playing is not taken for the end of it
    m = PM(); m.call(PSYMS['pc_speed_set'], a0=SH, a1=1, count=30000000); m.clock = 100000
    music = m.record(path='/mnt/mmc/Music/a.flac'); m.play([music], 0)
    m.call(PSYMS['pc_speed_apply'], a0=SH, count=3000000); m.note(music); m.clock += 2000; m.note(music)
    expect(m.speeds == [1] and m.word(PLAYSPEED_MODE) == 1, 'the speed set by the page stays while the music of before is seen playing')
    rec = m.track(ep); m.pt = (5, 3000, 1); m.note(rec)
    expect(m.speeds == [1], 'and the episode finds it set')
    # two episodes of one show: no change between them
    rec2 = m.track(f'{ROOT}/Alpha Show/ep2.mp3'); m.note(rec2)
    expect(m.speeds == [1], 'the next episode of the show: the speed stays')
    # another show with another speed
    m.call(PSYMS['pc_speed_set'], a0=pc_hash('bravo'), a1=2, count=30000000)
    rec3 = m.track(f'{ROOT}/bravo/b1.mp3'); m.note(rec3)
    expect(m.speeds == [1, 2] and m.word(PLAYSPEED_MODE) == 2, 'an episode of another show: its own speed')
    m.clock += 100000; m.note(m.record(path='/mnt/mmc/Music/a.flac'))
    expect(m.speeds == [1, 2, 0] and m.word(PLAYSPEED_MODE) == 0, 'and then music: back to the very first (1x), not to the first show\'s')


def strip_tests(ctx):
    """Shuffle's queue without the podcast files."""
    expect = ctx.expect
    m = PM()
    mk = lambda p: m.record(path=p)
    songs = [mk('/mnt/mmc/Music/a.flac'), mk(f'{ROOT}/S/e1.mp3'), mk('/mnt/mmc/Music/b.flac'), mk(f'{ROOT}/S/e2.mp3'), mk('/mnt/mmc/Music/c.flac')]
    q = m.new_deque(songs); idx = m.alloc(4)
    m.setword(idx, 2)
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    paths = lambda d: [m.read_cstr(m.word(rec + O['REC_PATH'])) for rec in m.deques[d]]
    keep = lambda *i: [m.read_cstr(m.word(songs[k] + O['REC_PATH'])) for k in i]
    expect(r != q and paths(r) == keep(0, 2, 4) and m.s32(idx) == 1 and ('deque_destroy',) in m.calls and q not in m.deques,
           'the queue without the podcast files (copies), the index following the song it was on, the old queue destroyed')
    q = m.new_deque(songs); m.setword(idx, 1)
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    expect(m.s32(idx) == 1 and len(m.deques[r]) == 3, 'on a podcast: the next song that stays')
    q = m.new_deque(songs); m.setword(idx, 3)
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    expect(m.s32(idx) == 2 and len(m.deques[r]) == 3, 'on the second podcast: the song after it')
    q = m.new_deque(songs[:4]); m.setword(idx, 3)
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    expect(m.s32(idx) == 0 and len(m.deques[r]) == 2, 'on a last podcast: the first that stays')
    q = m.new_deque([songs[0], songs[2]]); m.setword(idx, 1); m.calls = []
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    expect(r == q and m.s32(idx) == 1 and '_create_deque' not in m.names() and 'deque_destroy' not in m.names(), 'no podcast: the queue itself, nothing made')
    q = m.new_deque([songs[1], songs[3]]); m.setword(idx, 0)
    r = m.call(PSYMS['pc_strip'], a0=q, a1=idx, count=30000000)
    expect(r == 0 and q not in m.deques, 'nothing but podcasts: no queue (the old one destroyed)')
    expect(m.call(PSYMS['pc_strip'], a0=0, a1=idx, count=3000000) == 0, 'no queue: none')


# ---------------------------------------------------------------------------
JPEG_APP = b'\xff\xe0\x00\x10JFIF\0' + bytes(9)


def jpeg(w, h, app=1):
    """The start of a JPEG: SOI, `app` APP0 segments, a SOF0 with the size (what pc_cover_ok reads)."""
    return b'\xff\xd8' + JPEG_APP * app + b'\xff\xc0\x00\x11\x08' + struct.pack('>HH', h, w) + b'\x03' + bytes(9)


def png(w, h):
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + struct.pack('>II', w, h) + b'\x08\x02\x00\x00\x00'


def cover_tests(ctx):
    """pc_cover_ok: the stock loader holds the whole bitmap, so a picture is decoded only when its header says it is small enough."""
    expect = ctx.expect
    m = PM()
    P = f'{ROOT}/S/cover.jpg'
    ok = lambda data, path=P: (m.fs.__setitem__(path, data), m.call(PSYMS['pc_cover_ok'], a0=m.cstr(path), count=2000000))[1]
    expect(ok(jpeg(600, 600)) == 1 and ok(jpeg(1000, 1000)) == 1 and ok(jpeg(1449, 1449)) == 1, 'a JPEG of up to 2.1 million pixels is accepted (1449 x 1449 is the last square)')
    expect(ok(jpeg(1450, 1450)) == 0 and ok(jpeg(3000, 3000)) == 0 and ok(jpeg(8000, 200)) == 1 and ok(jpeg(8193, 10)) == 0, 'a larger one is refused (the decode would hold 8 MB or more), a wide thin one is fine, a side over 8192 is not')
    expect(ok(jpeg(600, 600, app=40)) == 1, 'size markers after many APP segments are found (40 of them)')
    expect(ok(jpeg(600, 600, app=70)) == 0, 'but only 64 segments are walked')
    expect(ok(png(1000, 1000)) == 1 and ok(png(2000, 2000)) == 0 and ok(png(100000, 1)) == 0 and ok(png(0, 10)) == 0, 'a PNG: the IHDR size; zero or huge sides are refused')
    expect(ok(b'GIF89a' + bytes(30)) == 0 and ok(b'x') == 0 and ok(b'') == 0 and ok(b'\xff\xd8\xff\xd9' + bytes(30)) == 0 and ok(b'\xff\xd8\xff\xda' + bytes(30)) == 0, 'another format, a short file, a JPEG that ends before its frame header: refused')
    expect(ok(jpeg(600, 600)[:-11]) == 0, 'a frame header cut short: refused')
    expect(m.call(PSYMS['pc_cover_ok'], a0=m.cstr(f'{ROOT}/none.jpg'), count=2000000) == 0, 'no file: refused')


# ---- the page
SHEET_ROWS = [r[0] for r in pod_ui.PS_SHEET_ROWS]
PG_WIDGETS = (['podcasts_listview', 'view_grid', 'label_status', 'label_title', 'img_nb_fade', 'label_row_title', 'label_row_sub', 'pg_big', 'img_ah_tint',
               'btn_return', 'btn_backtoplayer', 'btn_more', 'btn_globe', 'btn_search', 'ps_field', 'ps_hint', 'ps_text', 'ps_clear', 'ps_mag', 'btn_selall', 'pg_bar', 'pg_del', 'pg_unsubp', 'pod_pd_scrim', 'pod_pd_card', 'pod_pd_title', 'pod_pd_name', 'pod_pd_track', 'pod_pd_fill', 'pod_pd_count', 'pod_pd_cancel',
               'pg_sh_scrim', 'pg_sh_card', 'pg_sh_speed_vl', 'pg_sh_refresh_vl'] + [n for n, *_ in pod_ui.PS_STYLES] + [f'pg_sh_{r}{s}' for r in SHEET_ROWS for s in ('', '_tx', '_hr')])
T0 = 1700000000   # 2023-11-14 22:13:20 UTC
DAY = 86400


def page_card(m):
    """Alpha Show (two files, a 600 px cover) and bravo (metadata with durations, no cover)."""
    m.put(f'{ROOT}/Alpha Show/ep1.mp3', b'', T0); m.put(f'{ROOT}/Alpha Show/ep2.mp3', b'', T0 + DAY)
    m.put(f'{ROOT}/Alpha Show/cover.jpg', jpeg(600, 600))
    for i, d in ((1, 600), (2, 1200), (3, 3600)): m.put(f'{ROOT}/bravo/b{i}.mp3', b'', 5)
    m.put(f'{ROOT}/bravo/.episodes', (EPS_HEAD + ''.join(f'g=g{i}\tp={T0 + i * DAY}\td={d}\tf=b{i}.mp3\tt=Bravo {i}\n' for i, d in ((1, 600), (2, 1200), (3, 3600)))).encode())
    m.images[f'file://{ROOT}/Alpha Show/cover.jpg'] = (600, 600, bytes((200, 40, 40, 255)) * 600 * 600)
    m.images['p_default'] = (16, 16, bytes((90, 90, 90, 255)) * 256)
    m.load_image = 0


def atlas_image(name='pc_atlas'):
    """The Show page's atlas (assets/icons/png/pc_atlas.png), or another of its images, as the image manager would give it: (w, h, RGBA bytes)."""
    from PIL import Image
    im = Image.open(os.path.join(mod_icons.PNG, name + '.png')).convert('RGBA')
    return im.width, im.height, im.tobytes()


def page_machine(card=page_card, cls=None):
    m = (cls or PM)()
    if card: card(m)
    for n in PG_WIDGETS: m.widget(n)
    win, lv, sv, view = m.alloc(0x80), m.widgets['podcasts_listview'], m.alloc(0x180), m.widgets['view_grid']
    m.u.mem_write(sv, bytes(0x180)); m.u.mem_write(lv, bytes(0x80)); m.u.mem_write(view, bytes(0x80))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv), (view, 0, VIEW_H, sv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['podcasts_scrollview'] = sv
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    m.sv, m.view = sv, view
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.setword(m.widgets['label_title'] + 8, 156)
    m.setword(m.widgets['pg_big'] + 8, O['SG_TITLE_W'])
    m.clock = 5000
    m.images['pc_atlas'] = atlas_image()
    m.images['pod_ic_dltile'] = atlas_image('pod_ic_dltile')
    m.images['pod_ic_subtile'] = atlas_image('pod_ic_subtile')
    m.images['pod_ic_savetile'] = atlas_image('pod_ic_savetile')
    m.images['pod_ic_discovertile'] = atlas_image('pod_ic_discovertile')
    return m


def opened(card=page_card, cls=None):
    m = page_machine(card, cls)
    assert m.call(PSYMS['podcasts_open'], count=40000000) == 0
    return m


def paint(m, off=0):
    """One EVT_AFTER_PAINT of the content view at scroll offset off: (blits, texts, styles, fills)."""
    m.setword(m.sv + SC_YOFF, off & 0xffffffff)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - off) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    fn, ctx = m.bound[(m.view, O['EVT_AFTER_PAINT'])]
    m.call(fn, a0=ctx, a1=ev, count=400000000)
    return list(m.blits), list(m.texts), list(m.text_styles), list(m.fills)


def hint(m, off=0):
    """The empty page's hint as painted in the content (its wrapped lines in the dim 20 px grey style, joined), '' for none."""
    return ' '.join(' '.join(t.split()) for t, _ in drawn(m, off, 'label_ps_cdim'))


def paint_bottom(m):
    """A frame scrolled to the bottom of the Shows level, where the Library rows are (the page's 400 px view)."""
    return paint(m, max(0, m.props.get((m.sv, 'virtual_h'), 0) - 400))


def drawn(m, off=0, style=None):
    """[(text, (x, y, w, h))] of a frame, one text style or all."""
    _, texts, styles, _ = paint(m, off)
    return [t for t, s in zip(texts, styles) if style in (None, s)]


def tap(m, x, y, off=0, dt=80, move=0):
    """A touch at content point (x, y) of the list scrolled to off: down, up (the handlers the payload bound)."""
    m.setword(m.sv + SC_YOFF, off & 0xffffffff); m.setword(m.view + 4, -off & 0xffffffff)   # (the scroll_view moves its child up by the offset)
    sy = SCREEN_Y0 + y - off
    m.touch('down', x, sy, 1000, fn='pg_on_down')
    m.touch('up', x, sy + move, 1000 + dt, fn='pg_on_up', count=80000000)


def show_at(m, title):
    """(x, y, off) of a point on the cover of the show whose title starts with `title` on the Shows level: its caption is looked for in frames scrolled 100 px apart (a text is drawn only wholly in view);
    y is the content y, off the offset of the frame that showed it (tap it with that offset)."""
    for off in range(0, 6000, 100):
        for (t, r), s in zip(*paint(m, off)[1:3]):
            if s == 'label_ps_gtitle' and t.startswith(title):
                return r[0] + 10, r[1] + off - O['GRID_TITLE_GAP'] - O['GRID_COVER'] // 2, off
    raise AssertionError(f'no show {title!r} on the Shows level')


def lib_row_at(m, name):
    """(content y of the middle, offset) of the Shows level's Library row called name: the rows close the page, so the frames are scrolled 100 px apart until its title is drawn (a text is drawn only wholly in view)."""
    for off in range(0, 6000, 100):
        for (t, r), s in zip(*paint(m, off)[1:3]):
            if s == 'label_row_title' and t.startswith(name):
                return r[1] + r[3] // 2 + off, off
    raise AssertionError(f'no {name} row on the Shows level')


def tap_downloads(m, **kw):
    """A tap on the Shows level's Downloads row (found by its title, scrolled into view)."""
    y, off = lib_row_at(m, 'Downloads')
    return tap(m, 150, y, off=off, **kw)


def tap_discover(m, **kw):
    """A tap on the Shows level's Discover row (found by its title, scrolled into view)."""
    y, off = lib_row_at(m, 'Discover')
    return tap(m, 150, y, off=off, **kw)


def tap_line(m, **kw):
    """A tap on the refresh line (its grey text's middle)."""
    for (t, r), s in zip(*paint(m, 0)[1:3]):
        if s == 'label_ps_meta' and (t.startswith('Updated') or t.startswith('Never') or t.startswith('Refreshing') or t == 'Waiting' or t.endswith('ago · ')):
            return tap(m, r[0] + 20, r[1] + r[3] // 2, **kw)
    raise AssertionError('no refresh line on the Shows level')


def tap_show(m, title, **kw):
    """A tap on a show's cover on the Shows level: its Show page opens."""
    x, y, off = show_at(m, title)
    tap(m, x, y, off=off, **kw)


def click(m, name):
    fn, ctx = m.bound[(m.widgets[name], O['EVT_CLICK'])]
    return m.call(fn, a0=ctx, a1=0, count=40000000)


def title_text(m):
    """The page's title now: the navbar's title label while it shows (a Show page scrolled, select mode's "N Selected"), else the large heading (the Shows, Downloads and Subscriptions levels; the navbar has no title there), else the label's text (set by widget_set_text_utf8)."""
    big, nav = m.widgets['pg_big'], m.widgets['label_title']
    t = m.wtext.get(big) if m.props.get((big, 'visible'), 1) and not m.props.get((nav, 'visible'), 0) else m.wtext.get(nav)
    return t.encode('latin-1').decode('utf-8') if t is not None else None


def hdr(m):
    """Where the Show level's cells start (content y): the Episodes header's top and its height, read from a frame scrolled 100 px (a text is drawn only wholly in view: at the top a tall header hides it)."""
    _, texts, styles, _ = paint(m, 100)
    return next(r[1] for (t, r), s in zip(texts, styles) if s == 'label_ps_head') + 100 + O['PS_HEAD_H']


def cell_y(m, i): return hdr(m) + i * CELL


def body(m, i, **kw):
    """A tap on the date line of cell i: its body."""
    tap(m, 150, cell_y(m, i) + 12, **kw)


def act(m, i, **kw):
    """A tap on cell i's state pill: what the cell does (play it, download it, pause, resume, retry)."""
    tap(m, 30, cell_y(m, i) + O['PS_PILL_Y'] + O['PS_PILL_H'] // 2, **kw)


def dots(m, i, **kw):
    tap(m, O['PS_DOTS_CX'], cell_y(m, i) + O['PS_PILL_Y'] + O['PS_PILL_H'] // 2, **kw)


def latest(m, **kw):
    """A tap on the Latest Episode pill."""
    _, texts, styles, _ = paint(m, 0)
    r = next(r for (t, r), s in zip(texts, styles) if s in ('label_ps_latest', 'label_ps_latestw'))
    tap(m, r[0] + 20, r[1] + r[3] // 2, **kw)


def all_cells(m):
    """cells() of every cell of the open show: frames scrolled 120 px apart from the first cell (a cell's texts are drawn only while wholly in view)."""
    h = hdr(m)
    n = (m.props.get((m.sv, 'virtual_h')) - h - 20) // CELL
    out = {}
    for k in range(n * CELL // 120 + 2):
        for i, c in cells(m, h + 120 * k).items():
            if i not in out and 0 <= i < n and c['title'] and c['pill']: out[i] = c
    return out


def cells(m, off=0):
    """{index: {date, title: [lines], desc: [lines], pill, played}} of the cells in a frame (the texts by style and place)."""
    h = hdr(m)
    _, texts, styles, _ = paint(m, off)
    out = {}
    for (t, r), s in zip(texts, styles):
        if not s.startswith('label_ps_') or s in ('label_ps_name', 'label_ps_sec', 'label_ps_meta', 'label_ps_head', 'label_ps_latest', 'label_ps_latestw'): continue
        i = (r[1] + off - h) // CELL
        c = out.setdefault(i, dict(date='', title=[], desc=[], pill='', played=False))
        if s == 'label_ps_date': c['date'] = t
        elif s in ('label_ps_ctitle', 'label_ps_cdim'): c['title'].append(t); c['played'] = s == 'label_ps_cdim'
        elif s == 'label_ps_cdesc': c['desc'].append(t)
        elif s == 'label_ps_pill': c['pill'] = t
    return out


def ring_of(m, h):
    return m.state(h)


def open_tests(ctx):
    """The page opens on the shows: no widget per row, the handlers, the covers one a tick, the empty states."""
    expect = ctx.expect
    m = page_machine()
    expect(m.call(PSYMS['podcasts_open'], count=40000000) == 0, 'podcasts_open returns 0')
    calls = list(m.calls)
    expect(('window_open', 'm1plus_podcasts') in calls and not [c for c in calls if c[0] in ('list_item_create', 'hscroll_label_create', 'image_create', 'image_base_set_image')],
           'the window opens; no widget is made per show or episode (the content view paints the rows)')
    H2 = pod_show.shows_layout(2, False, 0)
    expect(m.props.get((m.sv, 'virtual_h')) == H2['h'] == 520 and ('widget_resize', m.view, 320, H2['h']) in calls and m.props.get((m.sv, 'yoffset')) == 0,
           f'the content is the large title, the Shows header, the grid of two shows (bravo, Alpha Show), then the Discover, Downloads and Saved Library rows (no feed: no Subscriptions row) and the air under them ({H2["h"]} px), at the top')
    expect(title_text(m) == 'Podcasts' and m.props.get((m.widgets['label_status'], 'visible'), 1) == 0 and m.props.get((m.widgets['label_title'], 'visible')) == 0
           and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1, 'the large title shows, the navbar\'s small one is hidden at rest; the empty-state line is hidden')
    for ev in ('EVT_AFTER_PAINT', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        expect((m.view, O[ev]) in m.bound, f'the content view handles {ev}')
    expect((m.sv, O['EVT_SCROLL']) in m.bound and (m.sv, O['EVT_SCROLL_END']) in m.bound and (m.window, O['EVT_WINDOW_TO_BG']) in m.bound and (m.window, O['EVT_WINDOW_TO_FG']) in m.bound
           and (m.window, O['EVT_DESTROY']) in m.bound, 'the scroll events, the window\'s background, foreground and destroy are bound')
    expect([(c[1], c[2]) for c in calls if c[0] == 'timer_add'] == [(PSYMS['pg_tick'], 1000), (PSYMS['pg_on_load'], 16)],
           f'a 1 s page timer is armed (the place is noted from it), then the cover loader\'s 16 ms one ({[c for c in calls if c[0] == "timer_add"]})')
    expect([c for c in calls if c[0] == 'bitmap_create_ex'][:2] == [('bitmap_create_ex', O['SG_MARK'], O['SG_MARK'])] * 2, 'only the two select marks are made at open (26 px): there is no unplayed dot bitmap any more')
    expect(('window_open', 'm1plus_podcasts') in m.calls and m.call(PSYMS['podcasts_open'], count=4000000) == 0xffffffff, 'a second open while the page is up is refused')
    # the rows
    bl, texts, styles, fills = paint(m)
    cells = [pod_show.grid_cell(i, H2['y_grid']) for i in range(2)]
    want = [(t, (cx, ty, O['GRID_COVER'], O['GRID_TITLE_H']), 'label_ps_gtitle') for t, (cx, cy, ty, sy) in zip(('bravo', 'Alpha Show'), cells)] + \
           [(t, (cx, sy, O['GRID_COVER'], O['GRID_SUB_H']), 'label_ps_gsub') for t, (cx, cy, ty, sy) in zip(('Local · 3 episodes', 'Local · 2 episodes'), cells)] + \
           [('Discover', (O['PP_DL_TEXT_X'], H2['y_srch'] + O['LIST_TITLE_Y'], O['PP_DL_TEXT_W'], O['LIST_TITLE_H']), 'label_row_title'), ('Apple Podcasts', (O['PP_DL_TEXT_X'], H2['y_srch'] + O['LIST_SUB_Y'], O['PP_DL_TEXT_W'], O['LIST_SUB_H']), 'label_row_sub'),
            ('Shows', (O['PP_SHOWS_X'], H2['y_shows'], 320 - 2 * O['PP_SHOWS_X'], O['PP_HEAD_H']), 'label_ps_sech')]
    expect(sorted((t, r, s) for (t, r), s in zip(texts, styles)) == sorted(want),
           f'a show: its name (18 px) and "N episodes" (15 px grey; no feed: the marker) in the Albums grid\'s places, the most recently updated first: {[(t, r, s) for (t, r), s in zip(texts, styles)]}')
    covers = [b for b in bl if tuple(b[2][2:]) == (O['GRID_COVER'], O['GRID_COVER'])]
    expect([tuple(b[2]) for b in covers] == [(cx, cy, O['GRID_COVER'], O['GRID_COVER']) for cx, cy, ty, sy in cells], 'a 144 px cover (the placeholder at first) at the grid\'s place in each cell')
    expect(not [f for f in fills if f[0] == O['LIST_HAIR'] and f[1] != O['PP_DL_TEXT_X']] and not [b for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])], 'no list row: no full-width hairline, no 52 px cover (the Library row has its own hairline from its text)')
    # the covers: one a tick, the nearest to the top first; a cover only when its header is small
    placeholder = covers[0][0]
    n = 0
    while any(c[0] == 'timer_add' and c[1] == PSYMS['pg_on_load'] for c in (m.calls if n else calls)) and n < 10:
        m.call(PSYMS['pg_on_load'], a0=0, count=40000000); n += 1
        if not any(c[0] == 'timer_add' for c in m.calls): break
    loads = [u for u in m.loads if u.startswith('file://')]
    expect(loads == [f'file://{ROOT}/Alpha Show/cover.jpg'], f'the cover file is decoded (bravo has none; nothing else is loaded) ({loads})')
    bl, _, _, _ = paint(m)
    covers = [b for b in bl if tuple(b[2][2:]) == (O['GRID_COVER'], O['GRID_COVER'])]
    expect(covers[1][0] != placeholder and covers[0][0] == placeholder, 'Alpha Show shows its picture now, bravo the placeholder disc')
    data, w, h = m.bitmaps[covers[1][0]]
    px = struct.unpack('<I', m.u.mem_read(data + (72 * w + 72) * 4, 4))[0]
    expect((w, h) == (O['GRID_COVER'], O['GRID_COVER']) and px & 0xffffff == 0x2828c8, f'the cover is the 600 px picture reduced to 144 ({px:08x})')
    expect(not [c for c in m.calls if c[0] == 'widget_load_image'] and not any(c[0] == 'widget_load_image' for c in paint_calls(m)), 'painting decodes nothing')
    # a picture that is too large is never decoded
    m2 = page_machine(lambda mm: (page_card(mm), mm.put(f'{ROOT}/Alpha Show/cover.jpg', jpeg(3000, 3000))))
    m2.call(PSYMS['podcasts_open'], count=40000000)
    for _ in range(6): m2.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [u for u in m2.loads if u.startswith('file://')], 'a 3000 x 3000 picture is not decoded (the stock loader would hold 36 MB)')
    # the empty states
    m3 = page_machine(lambda mm: mm.folder('/mnt/mmc/Music'))
    m3.call(PSYMS['podcasts_open'], count=40000000)
    st = m3.widgets['label_status']
    expect(('widget_set_tr_text', st, EMPTY_HINT) in m3.calls and m3.props.get((st, 'visible')) == 1 and m3.props.get((m3.view, 'visible')) == 0
           and ('label_set_line_wrap', st, 1) in m3.calls and m3.props.get((m3.widgets['label_title'], 'visible')) == 0, 'no Podcasts folder: the hint shows, the list (and the large title) is hidden, the navbar has no title')
    m4 = page_machine(lambda mm: mm.folder(ROOT))
    m4.call(PSYMS['podcasts_open'], count=40000000)
    expect(m4.props.get((m4.widgets['label_status'], 'visible')) == 1, 'an empty Podcasts folder: the same hint')
    m5 = page_machine(); m5.calloc_fail_size = (O['PC_MAX_SHOWS'] + 1) * O['PC_SHOW_SIZE']
    m5.call(PSYMS['podcasts_open'], count=40000000)
    expect(('widget_set_tr_text', m5.widgets['label_status'], 'Not enough memory') in m5.calls, 'no memory for the shows: "Not enough memory"')
    # an asset that is not ours
    for gone in ('view_grid', 'label_ps_name', 'podcasts_scrollview', 'label_title'):
        m6 = page_machine(); m6.widgets.pop(gone)
        r = m6.call(PSYMS['podcasts_open'], count=40000000)
        expect(r == 0xffffffff and 'navigator_back' in m6.names() and not any(c[0] == 'timer_add' for c in m6.calls), f'without {gone} the page leaves again and arms nothing')
    m7 = page_machine(); m7.windows['m1plus_podcasts'] = 0
    expect(m7.call(PSYMS['podcasts_open'], count=4000000) == 0xffffffff, 'a window that will not open: -1')
    # a lot of shows
    m8 = page_machine(lambda mm: [mm.put(f'{ROOT}/S{i:02}/a.mp3') for i in range(45)])
    m8.call(PSYMS['podcasts_open'], count=200000000)
    expect(m8.props.get((m8.sv, 'virtual_h')) == pod_show.shows_layout(40, False, 0)['h'], 'at most 40 shows are listed')


def paint_calls(m): return m.calls


def level_tests(ctx):
    """A tap on a show opens its page in place: the header and the cells, the states, Back goes up a level."""
    expect = ctx.expect
    m = opened()
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    x, y, _ = show_at(m, 'bravo')
    tap(m, x, y, off=30)   # (the list scrolled 30 px: Back finds it there)
    shown = title_text(m)
    h = hdr(m)
    expect(shown == 'bravo' and m.props.get((m.sv, 'virtual_h')) == h + 3 * CELL + 20 and m.props.get((m.sv, 'yoffset')) == 0,
           f'a tap on bravo: the navbar title is the show, the content a header ({h} px), three cells and the air under them ({m.props.get((m.sv, "virtual_h"))}), at the top')
    d = lambda t: when_model(t, 1800000000)   # (the machine's clock: 2027-01-15)
    c = all_cells(m)
    expect([c[i]['title'] for i in range(3)] == [['Bravo 3'], ['Bravo 2'], ['Bravo 1']] and not any(c[i]['played'] for i in range(3)),
           f'the episodes newest first, the titles from the metadata, bright ({[c[i]["title"] for i in range(3)]})')
    expect([c[i]['date'] for i in range(3)] == [d(T0 + 3 * DAY), d(T0 + 2 * DAY), d(T0 + DAY)], f'the date lines ({[c[i]["date"] for i in range(3)]})')
    expect([c[i]['pill'] for i in range(3)] == ['60m', '20m', '10m'], f'the state pills say the length ({[c[i]["pill"] for i in range(3)]})')
    # state: played; a place
    h2, h3 = pc_hash(f'{ROOT}/bravo/b2.mp3'), pc_hash(f'{ROOT}/bravo/b3.mp3')
    m.call(PSYMS['pc_mark'], a0=h2, a1=1, count=30000000)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    c = all_cells(m)
    expect([c[i]['played'] for i in range(3)] == [False, True, False], 'a played episode\'s title is in the grey style (and the others bright: the brightness tells them apart)')
    m.call(PSYMS['pc_mark'], a0=h2, a1=0, count=30000000)
    m.pt = (360, 3600, 1); m.status = 2
    m.play([m.record(path=f'{ROOT}/bravo/b3.mp3')], 0); m.clock += 40000
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    c = all_cells(m)
    expect(c[0]['pill'] == '54m left' and m.state(h3) == (1, 360, 3600) and not c[0]['played'], f'an episode in progress (the page\'s timer noted its place): "54m left" ({c[0]["pill"]})')
    # Back goes up a level
    m.calls = []
    click(m, 'btn_return')
    expect('navigator_back' not in m.names() and title_text(m) == 'Podcasts' and m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(2, False, 1)['h'] and m.props.get((m.sv, 'yoffset')) == 30,
           'Back from the episodes: the shows again (with Continue Listening now: bravo\'s episode is partly played), the list where it was (30), the page stays')
    m.calls = []
    click(m, 'btn_return')
    expect('navigator_back' in m.names(), 'Back from the shows leaves the page')
    # the header's cover and Alpha Show
    m = opened()
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.loads.clear()
    tap_show(m, 'Alpha Show')
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    bl, _, _, _ = paint(m)
    big = [b for b in bl if tuple(b[2][2:]) == (O['PS_ART'], O['PS_ART'])]
    expect([tuple(b[2]) for b in big] == [(O['PS_ART_X'], 0, O['PS_ART'], O['PS_ART'])] and f'file://{ROOT}/Alpha Show/cover.jpg' in m.loads, 'the Show header: the 160 px cover (decoded from the picture) at x 80, flush with the list\'s top')
    c = all_cells(m)
    expect([c[i]['title'] for i in range(2)] == [['ep2'], ['ep1']], f'the files\' names are the titles when there is no metadata ({[c[i]["title"] for i in range(2)]})')
    # a show with nothing downloaded
    m = opened(lambda mm: (page_card(mm), mm.put(f'{ROOT}/MetaOnly/.episodes', (EPS_HEAD + 'g=m1\tp=9\tf=m1.mp3\tt=Not yet\tu=https://e.example/m1\n').encode())))
    x, y, off = show_at(m, 'MetaOnly')
    expect([t for t, _ in drawn(m, off, style='label_ps_gsub')][-1:] == ['Local · 0 episodes'] and m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(3, False, 0)['h'],
           'a show with metadata and no file is on the Shows level too (no Feeds level: every show is here)')
    tap(m, x, y, off=off)
    expect(title_text(m) == 'MetaOnly' and all_cells(m)[0]['pill'] == 'Download', 'and it opens: its episode that is not on the card is a download cell')
    click(m, 'btn_return')
    expect(m.props.get((m.widgets['label_status'], 'visible')) == 0 and m.props.get((m.view, 'visible')) == 1, 'Back brings the shows back')


def touch_tests(ctx):
    """Taps: a show opens, a cell plays (with the ones after it); stray touches do nothing."""
    expect = ctx.expect
    m = opened()
    h2 = pc_hash(f'{ROOT}/bravo/b2.mp3')
    H2 = pod_show.shows_layout(2, False, 0)
    gx, gy = pod_show.grid_cell(0, H2['y_grid'])[:2]
    opens = lambda mm: mm.props.get((mm.sv, 'virtual_h')) != H2['h']   # (a Show page has another height)
    for what, x, y, dy in (('a drag past the threshold', gx + 10, gy + 10, 14), ('the air below the last row', gx + 10, H2['h'] - 5, 0), ('the gap between two covers', gx + O['GRID_COVER'] + 3, gy + 10, 0),
                           ('the large title', 30, 20, 0), ('the margin left of the first cover', 4, gy + 10, 0)):
        mm = opened(); tap(mm, x, y, move=dy)
        expect(not opens(mm), f'a touch on {what} opens nothing')
    mm = opened(); mm.touch('down', gx + 10, SCREEN_Y0 + gy + 10, 1000, fn='pg_on_down'); mm.touch('up', gx + O['GRID_COVER'] + O['GRID_GAP'] + 10, SCREEN_Y0 + gy + 10, 1080, fn='pg_on_up', count=40000000)
    expect(not opens(mm), 'a press on one cover released on another opens nothing')
    m.touch('down', gx + 10, SCREEN_Y0 + gy + 10, 1000, fn='pg_on_down')
    _, _, _, fills = paint(m)
    expect(not [f for f in fills if f[0] == O['LIST_PRESS']], 'a show has no pressed fill (only the Downloads row presses)')
    m.touch('abort', gx + 10, SCREEN_Y0 + gy + 10, 1010, fn='pg_on_abort')
    # play
    tap_show(m, 'bravo')
    m.calls = []
    act(m, 1)   # Bravo 2: the second cell's pill
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    expect(len(nav) == 1 and nav[0][1] == 'playing_page' and nav[0][2:] == (1, 1, O['PLAY_MODE']), f'a tap on an episode opens Now Playing with the queue: index 1, class 1 (folder play), mode 2 ({nav})')
    q, idx = m.played
    field = lambda r, off: m.read_cstr(m.word(r + off))
    expect([field(r, O['REC_PATH']) for r in q] == [f'{ROOT}/bravo/b3.mp3', f'{ROOT}/bravo/b2.mp3', f'{ROOT}/bravo/b1.mp3'] and idx == 1,
           'the queue is the show\'s episodes in the list\'s order, from the first cell; the tapped one starts (the ones after it play next)')
    r = q[1]
    expect((field(r, O['REC_NAME']), field(r, O['REC_TITLE']), field(r, O['REC_ALBUM']), field(r, O['REC_ARTIST'])) == ('b2.mp3', 'Bravo 2', 'bravo', 'bravo')
           and m.word(r + O['REC_TYPE']) == 8 and m.word(r + O['REC_CLASS']) == 1, 'a record: the file name, the title, the show as album and artist, a song (type 8), class 1')
    expect(m.word(pod.DATA['G_CLASS_TYPE'][0]) == 1, 'the browsing class is 1 (folder play)')
    m.mode = O['MODE_SHUFFLE']; m.calls = []; act(m, 0)
    expect(m.mode == O['MODE_ORDER'] and ('mclSetPlayMode', O['MODE_ORDER']) in m.calls, 'a tap on a cell\'s pill plays it in order: a shuffle mode is turned off')
    expect(('deque_destroy',) in m.calls and not [c for c in m.calls if c[0] == 'loadSongList'], 'the queue is the page\'s own: no stock list query is made, the page frees its copy')
    # a played episode starts again; a missing file does not start
    m.call(PSYMS['pc_mark'], a0=h2, a1=1, count=30000000)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    m.calls = []; act(m, 1); played = any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in m.calls)
    expect(m.state(h2)[0] == 0 and played, 'a played episode is new again when it is started (it plays from the beginning)')
    del m.fs[f'{ROOT}/bravo/b1.mp3']
    m.calls = []; act(m, 2)
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page'] and any(c[0] == 'toast' and c[1] == 'Storage unavailable' for c in m.calls),
           'an episode whose file has gone: "Storage unavailable", nothing starts')
    m.fs[f'{ROOT}/bravo/b1.mp3'] = b''
    # a tap on the left edge of a cell is the cell (no dot column)
    m.calls = []; tap(m, 4, cell_y(m, 0) + 12)
    h3 = pc_hash(f'{ROOT}/bravo/b3.mp3')
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'] and m.state(h3)[0] != 2 and [t for (t, r), s in zip(*paint(m, 0)[1:3]) if s == 'label_ps_head'], 'a tap at the left edge of a cell opens its episode page and marks nothing (the body no longer plays: the pill does)')
    click(m, 'btn_return')
    m.call(PSYMS['pc_mark'], a0=h3, a1=0, count=3000000)
    m.calls = []; tap(m, 200, 30)
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'a tap on the header\'s cover or name does nothing')
def lifecycle_tests(ctx):
    """The page timer, the window's events, the places noted from the page, the destroy."""
    expect = ctx.expect
    m = opened()
    rec = m.track(f'{ROOT}/bravo/b3.mp3'); m.pt = (400, 3600, 1); m.clock += 40000
    r = m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(r == O['RET_REPEAT'] and m.state(pc_hash(f'{ROOT}/bravo/b3.mp3')) == (1, 400, 3600), 'the page\'s timer notes the playing episode\'s place and goes on')
    m.screen(False); m.pt = (500, 3600, 1); m.calls = []
    r = m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(r == O['RET_REPEAT'] and m.state(pc_hash(f'{ROOT}/bravo/b3.mp3'))[1] == 500, 'with the screen off the place is still noted (the repaint waits)')
    m.screen(True)
    # background: timers go, the ring is written
    m.clock += 40000; m.pt = (600, 3600, 1); m.note(rec)
    m.calls = []; fn, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(len([c for c in m.calls if c[0] == 'timer_remove']) >= 1 and m.ring()[1][0][1] == 600, 'to the background: the timers are removed and the ring is written')
    r = m.call(PSYMS['pg_tick'], a0=0, count=4000000)
    expect(r == 0 and not [c for c in m.calls if c[0] == 'get_playtimeandlength'], 'a stray tick after that does nothing')
    m.calls = []; fn, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(any(c[0] == 'timer_add' and c[2] == 1000 for c in m.calls), 'to the foreground: the timer again')
    # the bar of the other pages: recent_note notes the place, and an episode is no album of the shelf
    m2 = PM(); m2.dirs.add('/mnt/data')
    rec = m2.track(f'{ROOT}/bravo/b3.mp3'); m2.pt = (400, 3600, 1)
    r = m2.call(PSYMS['recent_note'], a0=rec, count=40000000)
    expect(r == 0 and m2.state(pc_hash(f'{ROOT}/bravo/b3.mp3')) == (1, 400, 3600) and '/mnt/mmc/.m1plus/recently-played' not in m2.fs, 'recent_note (the Now Playing and mini bar timers): the place is noted; the shelf does not take an episode')
    music = m2.record(album='Alb', artist='Art', path='/mnt/mmc/Music/a.flac')
    expect(m2.call(PSYMS['recent_note'], a0=music, count=40000000) == 1 and '/mnt/mmc/.m1plus/recently-played' in m2.fs, 'music is recorded on the shelf as before')
    # destroy
    m = opened()
    for _ in range(3): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.calls = []
    fn, ctx_ = m.bound[(m.window, O['EVT_DESTROY'])]; m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(any(c[0] == 'timer_remove' for c in m.calls) and sum(1 for c in m.calls if c[0] == 'bitmap_destroy') >= 2, 'destroy: the timers and the bitmaps (the dot, the tiles) go')
    m.calls = []
    expect(m.call(PSYMS['pg_tick'], a0=0, count=4000000) == 0 and m.call(PSYMS['podcasts_open'], count=40000000) == 0, 'afterwards nothing runs, and the page opens again')
    # the date lines are made again when the page comes back to the front (no timer for it)
    m = page_machine(); m.mtime[f'{ROOT}/Alpha Show/ep1.mp3'] = 1800000000 - 3600; m.mtime[f'{ROOT}/Alpha Show/ep2.mp3'] = 1800000000 - 30
    m.call(PSYMS['podcasts_open'], count=40000000)
    tap_show(m, 'Alpha Show')
    lines = lambda: [all_cells(m)[i]['date'] for i in range(2)]
    expect(lines() == ['Just now', '1h ago'], f'the lines read as of the clock when the page opens ({lines()})')
    m.wall += 7200; fn, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=ctx_, a1=0, count=4000000)
    fn, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(lines() == ['2h ago', '3h ago'], f'back in front two hours later: made again ({lines()})')
    # a stray event after the shows changed on the card
    m = opened()
    m.put(f'{ROOT}/Zeta/z1.mp3', b'', T0)
    tap_show(m, 'bravo'); click(m, 'btn_return')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.shows_layout(3, False, 0)['h'], 'Back to the shows reads the card again (a show that came meanwhile is there)')


def asset_tests(ctx):
    """The page's asset: the Albums list's structure, the hidden labels, the menu's item."""
    expect, P = ctx.expect, pod_pages
    path = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_podcasts.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    lv = tree.find('podcasts_listview')
    expect(lv is not None and lv.y == pod_ui.NAVBAR_H and lv.y + lv.h == 450 and [c.type for c in lv.children] == ['scroll_view', 'scroll_bar_m'], 'list_view (50-450) > scroll_view + scroll_bar_m, as stock')
    sv = lv.children[0]
    expect(sv.name == 'podcasts_scrollview' and [c.name for c in sv.children] == ['view_grid'] and sv.w == 310, 'the scroll_view holds the one content view')
    big = tree.find('pg_big')
    expect(sv.children[0].name == 'view_grid' and [c.name for c in sv.children[0].children] == ['pg_big', 'ps_field'] and big.get('tr_text') == 'Podcasts' and big.get('sensitive') == 'false' and big.x == O['SG_TITLE_X'] and big.y == 0 and big.h == O['PP_TITLE_H']
           and big.get('style:normal:font_size') == str(O['PP_TITLE_PX']), 'the content view holds the large title (a label, as the Songs page\'s: it scrolls and is clipped with the content), insensitive')
    for name in ('label_status', 'img_nb_fade', 'label_row_title', 'label_row_sub', 'img_ah_tint', *[n for n, *_ in pod_ui.PS_STYLES]):
        w = tree.find(name)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == 'false', f'{name} starts hidden and insensitive')
    nav = tree.find('navigationbar_view')
    expect([c.name for c in nav.children] == ['label_title', 'btn_return', 'btn_backtoplayer', 'btn_more', 'btn_globe', 'btn_search', 'btn_selall'] and tree.find('label_title').get('tr_text') == 'Podcasts',
           'the navbar: title, Back, Now Playing, "..." (the Show level, and the Shows level when Import is possible), the globe (the Shows level, while Podcast Discover is on) and the magnifier (the Discover level) on the same slot, and Select All: no Feeds button')
    mb, npb = tree.find('btn_more'), tree.find('btn_backtoplayer')
    expect(mb.x == pod_ui.NAV_VIEW_X and mb.get('style:normal:icon') == 'pod_nav_more' and npb.get('style:normal:icon') == 'ah_nav_np' and tree.find('label_title').x + tree.find('label_title').w <= mb.x,
           'the "..." is the left cap of the capsule that ends in Now Playing; the title stops at its left edge')
    img_dir = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx')
    expect(not os.path.exists(os.path.join(img_dir, 'pod_nav_feeds.png')) and not os.path.exists(os.path.join(img_dir, 'pod_nav_feeds_down.png')) and 'pod_nav_feeds' not in mod_icons.NAV_VIEW, 'the Feeds glyph is gone from the tree')
    expect(tree.find('label_status').h >= 60, 'the hint has room for three lines')
    # the item
    item = next(i for i, r in enumerate(P.ITEMS) if r.label == 'Podcasts')
    expect(item == 20 == len(P.ITEMS) - 4 and P.ITEMS[item].action == P.ACT_PODCASTS == 23 and P.ID_CHARS[item] == 'l' and item not in P.DEFAULT_MENU and P.PAGES[P.PAGES.index(P.PODCASTS) + 1:] == [P.TAPE, P.NPSET_PAGE, P.KEYBOARD, P.KEYBOARDS_PAGE, P.THEME_PAGE, P.ABOUT_PAGE, P.SEARCH, P.ALBUM_PAGE, P.VINYL, P.FOLDERS, P.QUEUE_PAGE, P.RECORD_PAGE, P.VINYL_WHITE, P.VTHEME_PAGE, P.ONLINEART, P.CACHE_PAGE, P.COVLIST, P.FILES_PAGE, P.UPDATE, P.RELNOTES, P.BG_PAGE, P.ACCENT_PAGE, P.APPEARANCE_PAGE, P.PULLDOWN_PAGE, P.RADIO, P.RADIONP, P.RADIOINFO, P.SONGINFO, P.REGION_PAGE, P.WIFI_PAGE, P.WIFIINFO_PAGE, P.WIFIPASS_PAGE, P.WIFIOTHER_PAGE, P.WIFISEC_PAGE, P.PEQ_PAGE, P.PEQP_PAGE, P.PEQLIB_PAGE, P.TENBAND_PAGE, P.TENCURVE_PAGE, P.TENPREAMP_PAGE, P.AUTOEQ_PAGE, P.PEQBAND_PAGE, P.SUBSONIC_PAGE]
           and P.PODCASTS.kind == 'podcasts', 'Podcasts is item 20 (saved as "l"), before Search, hidden from the menu by default; its page follows the Pod (the Tape pages come after it)')
    expect(P.EXTRAS_GROUPS[1][1][-4] == 'Podcasts' and P.EXTRAS_GROUP_OF[item] == 1 and P.EXTRAS_GROUPS[0][1] == ('Now Playing', 'Shuffle', 'Pod')
           and P.parse_menu_full(b'123456l\n') == ([1, 2, 3, 4, 5, 6, 20], []) and P.format_menu([1, 2, 20]) == '12l\n', 'Extras lists it in the Library group, before Radio and Search; the saved list carries it as l')
    expect(pod_i18n.key_for('Podcasts') == 'Podcasts' and 'Podcasts' in pod_i18n.TEXT and 'Podcasts' not in pod_i18n.BRANDS, 'the label is a translated key (13 languages)')
    # the menu row opens the page; a window that will not open does nothing
    on_row = PSYMS['on_row']
    rows0 = PSYMS['pod_rows_0']
    m = Machine(); m.call(on_row, a0=rows0 + 12 * item, count=5000000)
    expect(('window_open', 'm1plus_podcasts') in m.calls and 'stock_resume' not in m.names(), 'the Podcasts row opens m1plus_podcasts, not a stock page')
    m = Machine(); m.windows['m1plus_podcasts'] = 0; m.call(on_row, a0=rows0 + 12 * item, count=5000000)
    expect('stock_resume' not in m.names() and 'navigator_back' not in m.names(), 'a window that will not open: nothing else happens')
    rows_x = PSYMS[f'pod_rows_{P.EXTRAS_PAGE_INDEX}']
    m = Machine(); m.call(on_row, a0=rows_x + 12 * item, count=5000000)
    expect(('window_open', 'm1plus_podcasts') in m.calls, 'the same from the Extras page')
    # the images: the Extras icon (the row's glyph, tools/mod_icons.py POD_ROWS)
    expect(os.path.isfile(os.path.join(mod_icons.PNG, 'pod_ic_podcasts.png')) and mod_icons.POD_ROWS['Podcasts'][0] == 'pod_ic_podcasts', 'the row\'s icon is committed (a Lucide podcast glyph)')


def integration_tests(ctx):
    """Shuffle without podcasts."""
    expect = ctx.expect
    sib = sibling('shuffle')
    rows = [(f'/mnt/mmc/Music/{c}/{i}.flac', c) for c in 'AB' for i in range(1, 5)] + [(f'{ROOT}/Show/ep{i}.mp3', 'Show') for i in range(1, 9)]
    for seed in range(6):
        m = sib.shuffle_machine(rows); m.seed = seed * 7 + 1
        r = m.call(PSYMS['shuffle_play'], a0=0, count=200000000)
        q, idx = m.played
        paths = [sib.field(m, x, O['REC_PATH']) for x in q]
        expect(r == 0 and len(q) == 8 and not any('/Podcasts/' in p for p in paths) and '/Podcasts/' not in paths[idx], f'seed {seed}: Shuffle Songs: the queue has the 8 songs of the library and no episode, and it starts on a song ({len(q)})')
    m = sib.shuffle_machine([(f'{ROOT}/Show/ep{i}.mp3', 'Show') for i in range(1, 4)])
    r = m.call(PSYMS['shuffle_play'], a0=0, count=200000000)
    expect(r != 0 and m.played is None and any(c[0] == 'toast' for c in m.calls), 'a library of nothing but episodes: nothing to shuffle (the stock message)')
    for kind in (1, 2):
        m = sib.shuffle_machine(rows)
        r = m.call(PSYMS['shuffle_play'], a0=kind, count=200000000)
        q, idx = m.played
        expect(r == 0 and len(q) == 8 and not any('/Podcasts/' in sib.field(m, x, O['REC_PATH']) for x in q), f'Shuffle {"Albums" if kind == 1 else "Folders"}: no episode in the queue')
    m = sib.shuffle_machine([r for r in rows if '/Podcasts/' not in r[0]]); m.calls = []
    m.call(PSYMS['shuffle_play'], a0=0, count=200000000)
    expect('_create_deque' in m.names() and m.names().count('_create_deque') == 1, 'a library with no episode: the queue is the stock one, no copy is made')


MON = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
NOW = 1800000000   # 2027-01-15 08:00:00 UTC


def when_model(pub, now, tz=0, tr=None):
    """Apple Podcasts' date line (docs/modules/podcasts.md "The date"), written again; tr(key, n) is the language's text of a key (English: the key with n for %d)."""
    tr = tr or (lambda key, n=None: key.replace('%d', str(n)))
    year_now = datetime.datetime.fromtimestamp(now + tz, datetime.timezone.utc).year
    if year_now >= 2024 and pub <= now + 60:
        d = max(now - pub, 0)
        if d < 60: return tr('Just now')
        if d < 3600: return tr('%dm ago', d // 60)
        if d < 86400: return tr('%dh ago', d // 3600)
        if d < 7 * 86400: return tr('%dd ago', d // 86400)
    t = datetime.datetime.fromtimestamp(pub + tz, datetime.timezone.utc)
    s = tr(f'{MON[t.month - 1]} %d', t.day)
    return s + (tr(', %d', t.year) if t.year != year_now else '')


def when_tests(ctx):
    """pc_when: each band at its edges, the year boundary, a date ahead of the clock, a clock never set, the local calendar, every language."""
    expect = ctx.expect
    m = PM(); out = m.alloc(80)
    def when(pub, now=NOW, tz=0, loc=None):
        m.tz = tz
        if loc: m.set_language(loc)
        m.call(PSYMS['pc_when'], a0=pub & 0xffffffff, a1=now, a2=out, a3=80, count=2000000)
        return m.read_cstr(out)
    for d, want in ((0, 'Just now'), (59, 'Just now'), (60, '1m ago'), (61, '1m ago'), (3599, '59m ago'), (3600, '1h ago'), (86399, '23h ago'), (86400, '1d ago'), (6 * 86400 + 86399, '6d ago'),
                    (7 * 86400 - 1, '6d ago')):
        expect(when(NOW - d) == want, f'{d} s ago: {want} ({when(NOW - d)!r})')
    expect(when(NOW - 7 * 86400) == 'Jan 8' and when(NOW - 7 * 86400) == when_model(NOW - 7 * 86400, NOW), 'seven days ago: the date, "Jan 8" (this year, no year)')
    expect(when(NOW + 30) == 'Just now' and when(NOW + 60) == 'Just now' and when(NOW + 61) == when_model(NOW + 61, NOW) == 'Jan 15', 'a date up to a minute ahead of the clock is "Just now"; further ahead: the absolute date')
    expect(when(NOW + 5 * DAY) == 'Jan 20', 'five days ahead: "Jan 20", not a negative age')
    N2 = 1798891200   # 2027-01-02 12:00 UTC
    expect(when(N2 - 13 * DAY, N2) == 'Dec 20, 2026' and when(N2 - 40 * DAY, N2) == 'Nov 23, 2026' and when(N2 - 2 * DAY, N2) == '2d ago' and when(N2 - 365 * DAY, N2) == 'Jan 2, 2026', f'another year: the year follows ("Dec 20, 2026"); this year it does not {[when(N2 - 13 * DAY, N2), when(N2 - 40 * DAY, N2), when(N2 - 2 * DAY, N2), when(N2 - 365 * DAY, N2)]}')
    expect(when(NOW - 30 * DAY) == 'Dec 16, 2026' and when(1700000000, 1700000000 + 30 * DAY) == 'Nov 14', 'the year boundary: Jan 15 2027 looking at Dec 16 2026; an unchanged year gives no year')
    expect(when(1700000000, 1700000000 + 3600) == 'Nov 14' and when(1700000000 - 30 * DAY, 1700000000) == 'Oct 15', 'a clock before 2024 (never set): relative ages are not trusted, the absolute date is shown')
    # the local calendar of the status bar clock
    pub = NOW - 14 * DAY - 4 * 3600   # 2027-01-01 04:00 UTC
    expect(when(pub, tz=0) == when_model(pub, NOW, 0) and when(pub, tz=-5 * 3600) == when_model(pub, NOW, -5 * 3600) == 'Dec 31, 2026' and when(pub, tz=0) == 'Jan 1', 'the day is the local one (a clock zone behind UTC puts it on the day before, and the year with it)')
    # random: against the model
    rnd = random.Random(9); bad = []
    for _ in range(300):
        now = rnd.randrange(1704067200, 1900000000); pub = now - rnd.choice((0, 30, 100, 5000, 50000, 400000, 3000000, 40000000)) + rnd.randrange(-100, 100); tz = rnd.choice((0, 3600 * 8, -3600 * 5))
        if when(pub, now, tz) != when_model(pub, now, tz): bad.append((pub, now, tz, when(pub, now, tz), when_model(pub, now, tz)))
    expect(not bad, f'300 random dates against the model: {bad[:2]}')
    # every language: the texts of pod_i18n, in the order of the language
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, n=None, t=t: pod_i18n.TEXT[key][t].replace('%d', str(n)).encode('utf-8').decode('latin-1') if n is not None else pod_i18n.TEXT[key][t].encode('utf-8').decode('latin-1')
        for pub in (NOW - 10, NOW - 600, NOW - 7200, NOW - 3 * DAY, NOW - 20 * DAY, NOW - 200 * DAY, NOW + 100 * DAY):
            expect(when(pub, loc=loc) == when_model(pub, NOW, 0, tr), f'{loc}: {when_model(pub, NOW, 0, tr)!r}')
    m.set_language(None)
    # no localtime: nothing, no crash; a short buffer cuts
    m.tz = 0
    m.call(PSYMS['pc_when'], a0=NOW - 3 * DAY, a1=NOW, a2=out, a3=4, count=2000000)
    expect(m.read_cstr(out) == '3d ', 'a buffer that is too short cuts the text')


def width_tests(ctx):
    """The date line of a cell in every language, measured in the real font (the label_ps_date 15 px style): the room is the cell's text width less the two badges (a check and the disc), so the longest date fits."""
    expect = ctx.expect
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))
    st = StbText(font, dict((n, px) for n, px, *_ in pod_ui.PS_STYLES)['label_ps_date'])
    room = O['PS_CELL_W'] - O['PS_BADGE_CHECK_W'] - O['PS_BADGE_DISC_W']
    worst = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, n=None, t=t: (pod_i18n.TEXT[key][t].replace('%d', str(n)) if n is not None else pod_i18n.TEXT[key][t])
        dates = [when_model(NOW - d, NOW, 0, tr) for d in (10, 600, 7200, 3 * DAY, 20 * DAY, 200 * DAY)] + [when_model(NOW - (d + 45) * DAY, NOW, 0, tr) for d in range(0, 365, 30)]
        w = max(st.layout(d)[1] for d in dates)
        worst.append((loc, round(w)))
    print(f'  widest date a language needs (px, room {room}):', worst)
    expect(all(w <= room for _, w in worst), f'the longest date line (a date with a year) fits {room} px in every language, with the two badges ({[x for x in worst if x[1] > room]})')


GET_ID3INFO, ID3_SITE_VA = 0x4dfd58, 0x4dff4c
GOT = pod.GP   # GOT slots are read from the demo's own data: the stubs stock's PIC code calls through
GOT_FUNCS = {-0xcdc: 'strcpy', -0xa94: 'strcmp', -0xadc: 'memset', -0xa1c: 'snprintf', -0xce4: 'deque_size', -0xa8c: 'deque_at'}


class ID3(PM):
    """The machine with stock's get_id3info (0x4dfd58) running for real: its callees mocked (the tag reader gives the tags a test sets; the cached struct is stock's own global)."""
    def __init__(self, stock=False):
        super().__init__()
        for off, name in GOT_FUNCS.items(): self.handlers[self.word(GOT + off)] = name
        for a, n in ((0x5d3658, 'mclGetPlayType'), (0x5d4384, 'mclGetCueFlag'), (0x4debb4, 'setparsecover_info'), (0x5ec6a8, 'toolsGetMusicInfo'), (0x5e0cc0, 'toolsTrimLeft')):
            self.handlers[a] = n
        self.tags = dict(title='', artist='', album='')   # what toolsGetMusicInfo finds in the file
        self.cue = 0
        if stock: self.setword(ID3_SITE_VA, 0x0320f809)   # the stock word: no payload at the site

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        ret = None
        if name == 'strcpy':
            self.u.mem_write(a0, self.read_cstr(a1).encode('latin-1') + b'\0'); ret = a0
        elif name == 'mclGetPlayType': ret = 1
        elif name == 'mclGetCueFlag': ret = self.cue
        elif name in ('setparsecover_info', 'toolsTrimLeft'): self.calls.append((name,)); ret = 0
        elif name == 'toolsGetMusicInfo':   # (0, info + 0x404, path): album +0, artist +0x100, [+0x200], title +0x280 of the buffer
            self.calls.append(('toolsGetMusicInfo', self.read_cstr(a2)))
            for off, key in ((0, 'album'), (0x100, 'artist'), (0x280, 'title')): self.u.mem_write(a1 + off, self.tags[key].encode('utf-8') + b'\0')
            ret = 1
        if ret is not None:
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    def parse(self, path, record=None, **tags):
        """get_id3info for the track at `path` (a queue of one): (id3 title, artist, album, song_name, song_artist)."""
        self.tags.update(tags)
        self.u.mem_write(pod.DATA['PLAYSONG_ID3INFO'][0], bytes(0xa9c)); self.u.mem_write(pod.DATA['SONG_NAME'][0], bytes(0x200)); self.u.mem_write(pod.DATA['SONG_ARTIST'][0], bytes(0x100))
        rec = record or self.record(album='', artist='', path=path, title='', name=path.rsplit('/', 1)[1])
        self.play([rec], 0)
        self.call(GET_ID3INFO, count=2000000)
        i = pod.DATA['PLAYSONG_ID3INFO'][0]
        return (self.read_cstr(i + 0x684), self.read_cstr(i + 0x504), self.read_cstr(i + 0x404), self.read_cstr(pod.DATA['SONG_NAME'][0]), self.read_cstr(pod.DATA['SONG_ARTIST'][0]))


def tag_tests(ctx):
    """The tag reader hook: stock's get_id3info runs for real over the site (0x4dff4c, the strcpy of the parsed path). Stock shows "Unknown" for an episode without tags; the hook puts the episode and the show there."""
    expect = ctx.expect
    p = f'{ROOT}/WSJ Show/ep1.mp3'
    # the build: the one word is a jal into the payload, its neighbours and the pinned words are stock's
    site = pod.fileoff(ID3().data, ID3_SITE_VA)
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = ID3().data
    w = lambda b, off: struct.unpack_from('<I', b, off)[0]
    expect(w(stock_demo, site) == 0x0320f809 and w(built, site) >> 26 == 3 and (w(built, site) & 0x3ffffff) << 2 == PSYMS['pc_id3_path'], 'the build replaced stock\'s `jalr t9` at 0x4dff4c by `jal pc_id3_path`')
    expect(all(w(stock_demo, pod.fileoff(stock_demo, a)) == old and (a == ID3_SITE_VA or w(built, pod.fileoff(built, a)) == old) for a, old, _ in pod.PODCAST_PINS),
           'every pinned word (get_id3info\'s prologue and the words around the site, seek_time, mclSetPlaySpeed) is stock\'s in the stock demo and unchanged in the build, but the site')
    expect(pod.ID3_SITE == ID3_SITE_VA and w(stock_demo, pod.fileoff(stock_demo, 0x4dff50)) == 0x8e05000c, 'the delay slot still loads a1 = the record\'s path')
    expect(pod.dynsym(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO)).get('playsong_id3info') == 0xa0d88c and pod.DATA['SONG_NAME'][0] == 0xa0513c and pod.DATA['SONG_ARTIST'][0] == 0xa0503c,
           'the id3 struct and the two globals are the pinned symbols')
    from elftools.elf.elffile import ELFFile
    with open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb') as f:
        sizes = {s.name: s['st_size'] for s in ELFFile(f).get_section_by_name('.dynsym').iter_symbols() if s.name in ('playsong_id3info', 'song_name', 'song_artist')}
    expect(sizes['playsong_id3info'] >= 0x684 + 0x200 and sizes['song_name'] >= 0x200 and sizes['song_artist'] >= 0x100, f'the hook\'s copies (title 0x200, artist and album 0x100) fit the symbols\' sizes ({ {k: hex(v) for k, v in sizes.items()} })')
    # stock without the payload: no tags -> the file name and "Unknown"
    s = ID3(stock=True).parse(p)
    expect(s[3] == 'ep1.mp3' and s[4].startswith('Unknow') and s[1] == '', f'stock: no tags: the file name as the title and "Unknown" as the artist ({s})')
    # with the hook: our own record (episode title and show), tags absent
    m = ID3()
    rec = m.record(album='WSJ Show', artist='WSJ Show', path=p, title='Episode 9', name='ep1.mp3')
    s = m.parse(p, record=rec)
    expect(s == ('Episode 9', 'WSJ Show', 'WSJ Show', 'Episode 9', 'WSJ Show'), f'our record: the episode and the show in the struct and in song_name / song_artist ({s})')
    s = m.parse(p, record=rec, title='20261030 HL REFILE', artist='Narrator', album='Tag Album')
    expect(s[0] == 'Episode 9' and s[1] == 'WSJ Show' and s[2] == 'WSJ Show', 'the record wins over tags that are there (the episode title is the feed\'s)')
    # a record of the library (no title/artist of ours) and no tags: the show folder
    s = ID3().parse(p)
    expect(s == ('', 'WSJ Show', 'WSJ Show', 'ep1.mp3', 'WSJ Show'), f'a scanned record, no tags: the file name as stock has it, the show as artist and album ({s})')
    s = ID3().parse(p, title='20261030 HL REFILE', artist='Unknown')
    expect(s[0] == '20261030 HL REFILE' and s[1] == 'WSJ Show' and s[3] == '20261030 HL REFILE' and s[4] == 'WSJ Show', f'a title tag only (an "Unknown" artist counts as none): the tag title, the show ({s})')
    s = ID3().parse(p, title='T', artist='Real Artist', album='Real Album')
    expect(s == ('T', 'Real Artist', 'Real Album', 'T', 'Real Artist'), f'tags that are all there are left alone ({s})')
    # anything else is stock's
    mp = '/mnt/mmc/Music/a/b.flac'
    a = ID3(stock=True).parse(mp, title='T'); b = ID3().parse(mp, title='T')
    expect(a == b and b[4].startswith('Unknow') and b[3] == 'T', f'music: the same as stock ({b})')
    a = ID3(stock=True).parse(mp, title='T', artist='A', album='B'); b = ID3().parse(mp, title='T', artist='A', album='B')
    expect(a == b == ('T', 'A', 'B', 'T', 'A'), 'music with tags: unchanged')
    # the cache: a parse for the same path is skipped by stock before the site (the hook runs on fresh parses only)
    m = ID3(); m.parse(p, record=m.record(album='S', artist='S', path=p, title='E', name='ep1.mp3')); m.calls = []
    m.call(GET_ID3INFO, count=2000000)
    expect('toolsGetMusicInfo' not in m.names(), 'the second call for the same file does not parse again (stock\'s cache), and so does not pass the hook')
    # the kill switch: stock
    m = ID3(); m.present.add('/mnt/mmc/m1plus-off')
    s = m.parse(p, record=m.record(album='S', artist='S', path=p, title='E', name='ep1.mp3'))
    expect(s[3] == 'ep1.mp3' and s[4].startswith('Unknow') and s[1] == '', f'/mnt/mmc/m1plus-off: stock\'s text ({s})')
    m = ID3(); m.present.add('/mnt/data/m1plus-off')
    expect(m.parse(p, record=m.record(album='S', artist='S', path=p, title='E', name='ep1.mp3'))[4].startswith('Unknow'), 'and the flash switch too')
    # the copy is stock's: the path in the struct (the cache key) and the CUE start word kept; a long path is cut under the 0x400 field
    m = ID3(); long = '/mnt/mmc/Podcasts/S/' + 'x' * 1100 + '.mp3'
    m.parse(long, record=m.record(album='S', artist='S', path=long, title='E', name='x.mp3'))
    i = pod.DATA['PLAYSONG_ID3INFO'][0]
    expect(m.read_cstr(i) == long[:0x3ff] and m.word(i + 0x400) == 0, 'the cache key is the path (cut before the CUE start at +0x400)')
    # the cached struct keeps the path of a normal track
    m = ID3(); m.parse(p, record=m.record(album='S', artist='S', path=p, title='E', name='ep1.mp3'))
    expect(m.read_cstr(i) == p, 'the struct\'s key is the path, as strcpy left it')
    # no work for music at boot: the hook is a copy and a prefix test (instructions)
    m = ID3().count(); m.parse(mp, title='T')
    m2 = ID3(stock=True).count(); m2.parse(mp, title='T')
    expect(m.icount - m2.icount < 1000, f'a plain path costs {m.icount - m2.icount} instructions more than stock')
    # a record that is not the one playing (the path differs): not trusted, the show folder only
    m = ID3(); rec = m.record(album='X', artist='X', path='/mnt/mmc/Podcasts/Other/zz.mp3', title='Wrong', name='zz.mp3')
    m.u.mem_write(pod.DATA['PLAYSONG_ID3INFO'][0], bytes(0xa9c)); m.play([rec], 0)
    ret = m.call(PSYMS['pc_id3_path'], a0=i, a1=m.cstr(p), count=200000)
    expect(ret == i and m.read_cstr(i + 0x504) == 'WSJ Show' and m.read_cstr(i + 0x684) == '', 'a playing record with another path is ignored')
    # the page's own record carries what the hook wants
    mm = opened(); tap_show(mm, 'Alpha Show'); mm.calls = []
    act(mm, 0)
    q, idx = mm.played
    expect(mm.read_cstr(mm.word(q[0] + O['REC_ARTIST'])) == 'Alpha Show' and mm.read_cstr(mm.word(q[0] + O['REC_TITLE'])) == 'ep2', 'a record queued by the page carries the episode title and the show as artist')


SECTIONS = [when_tests, width_tests, tag_tests, text_tests, scan_tests, ring_tests, resume_tests, speed_tests, strip_tests, cover_tests, open_tests, level_tests, touch_tests, lifecycle_tests, asset_tests, integration_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
