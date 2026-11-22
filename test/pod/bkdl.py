"""Audiobooks, LibriVox on the card (patch/bkdl.c, patch/bkdl.h, patch/pcnet.c pnw_download, patch/bkmodel.c, docs/modules/audiobooks.md "LibriVox"): the FAT-safe names, the manifest (written
atomically, read back, every malformed form refused), the book folder (collisions, reuse by identifier, the cover), the download job through the scripted libcurl (all parts, only the missing ones, Range
resume, pause and restart, every terminal failure, the retries, the guards, a thread of its own beside the job slot and the Podcasts queue) and the model's view of a book with a manifest and no part
yet. The compiled payload runs under Unicorn; the card is a dict of paths (file names are latin-1 views of their UTF-8 bytes, as the harness reads C strings)."""
import os, re, sys
from urllib.parse import unquote
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BK = sibling('bknet')
DL = sibling('pcdl')
BKM = sibling('bkmodel')
SE, PCN = BK.SE, BK.PCN
fn = SE.fn
PN = dict(BK.PN, CANCELLED=12, CARDFULL=13, NOTAUDIO=14, QFULL=15)
D = BK.defs('books.h', 'bknet.h', 'bkdl.h', 'pcnet.h')
FILE, TITLE, MAXP, MAN_CAP, PATH_MAX = D['BK_FILE'], D['BK_TITLE'], D['BK_MAX_PARTS'], D['BD_MAN_CAP'], D['PN_DL_PATH_MAX']
ID, AUTHOR = D['BN_ID'], D['BN_AUTHOR']
ROOT_DIR = '/mnt/mmc/Audiobooks'
HOST = 'https://archive.org'
R_NONE, R_DONE, R_PAUSED, R_FAILED = 0, 1, 2, 3
KB = 1024
MARGIN_MB = 32
BOOK_SIZE = 148 + FILE + ID + TITLE + AUTHOR + 4 + MAXP * (2 * FILE + TITLE + 8)
OFF = dict(root=0, dir=148, id=148 + FILE, title=148 + FILE + ID, author=148 + FILE + ID + TITLE, n=148 + FILE + ID + TITLE + AUTHOR)
POFF = OFF['n'] + 4
PSIZE = 2 * FILE + TITLE + 8


def L(s): return s.encode('utf-8').decode('latin-1')   # a name as the harness's read_cstr gives it


def cz(m, s):
    """A C string of a name as the harness has it (latin-1 view of UTF-8 bytes)."""
    a = m.alloc(len(s) + 1); m.u.mem_write(a, s.encode('latin-1') + b'\0')
    return a


def key_of(d): return PCN.pc_hash('audiobooks/' + d)


def enc(name):
    return ''.join(c if re.fullmatch(r'[A-Za-z0-9\-._~]', c) else ''.join(f'%{b:02X}' for b in c.encode('utf-8')) for c in name)


def machine(site=None, **kw):
    m = BK.machine(site=site, **kw)
    m.jinit()
    return m


def cs(raw): return raw.split(b'\0')[0].decode('utf-8', 'replace')


def read_book(m, d):
    """bd_open's record as a dict, or None."""
    p = fn(m, 'bd_open', cz(m, d))
    if not p: return None
    raw = bytes(m.u.mem_read(p, BOOK_SIZE))
    n = int.from_bytes(raw[OFF['n']:OFF['n'] + 4], 'little')
    parts = []
    for i in range(n):
        r = raw[POFF + i * PSIZE:POFF + (i + 1) * PSIZE]
        parts.append(dict(file=cs(r[:FILE]), name=cs(r[FILE:2 * FILE]), title=cs(r[2 * FILE:2 * FILE + TITLE]), secs=int.from_bytes(r[-8:-4], 'little'), bytes=int.from_bytes(r[-4:], 'little')))
    book = dict(root=cs(raw[:148]), dir=cs(raw[OFF['dir']:OFF['id']]), id=cs(raw[OFF['id']:OFF['title']]), title=cs(raw[OFF['title']:OFF['author']]), author=cs(raw[OFF['author']:OFF['n']]), parts=parts)
    counts = [m.alloc(4) for _ in range(3)]
    fn(m, 'bd_counts', p, *counts)
    book['counts'] = tuple(m.word(c) for c in counts)
    book['present'] = [fn(m, 'bd_present', p, i) for i in range(n)]
    fn(m, 'bd_free', p)
    return book


def fat(m, text, mx):
    raw = text if isinstance(text, bytes) else text.encode('utf-8')
    a = m.alloc(len(raw) + 1); m.u.mem_write(a, raw + b'\0')
    o = m.alloc(mx + 8); m.u.mem_write(o, bytes([0xAA]) * (mx + 8))
    n = fn(m, 'bd_fat', a, mx, o)
    out = bytes(m.u.mem_read(o, mx + 8))
    z = out.index(0)
    assert out[mx + 1:] == bytes([0xAA]) * 7, 'bd_fat wrote past max + 1'
    assert z == n, 'length matches'
    return out[:z].decode('utf-8')


# ---- A world: a held preview of a book, ready to create and download

def obj(name, title, size, secs='1:00'):
    return BK.obj(name=name, format='64Kbps MP3', source='derivative', size=str(size), length=secs, **({'title': title} if title is not None else {}))


class World:
    """A machine whose archive serves one book: files answer, picture, and the parts (data[name]). hook(name, start, opts) may return a response dict to replace the part's."""
    def __init__(self, parts=None, ident='test_book_librivox', **kw):
        self.ident = ident
        self.parts = parts if parts is not None else [('b_01.mp3', 'Chapter One', 70000), ('b_02.mp3', 'Chapter Two', 50000), ('b_03.mp3', 'Chapter Three', 90000)]
        self.data = {n: bytes((b + i) & 255 for b in body(s)) for i, (n, t, s) in enumerate(self.parts)}
        self.reqs, self.hook, self.serve = [], None, True
        files = BK.result(*[obj(n, t, s) for n, t, s in self.parts])
        self.files = files
        self.m = machine(site=self.site, **kw)

    def site(self, url, o):
        if '/metadata/' in url: return {'body': self.files, 'chunk': 16384}
        if '/services/img/' in url: return {'body': getattr(self, 'site_img', BK.THUMB), 'chunk': 5500}
        if '/download/' not in url: return {'rc': 6}
        name = self.unq(url.rsplit('/', 1)[1])
        rng = o.get(10007)
        start = int(rng.rstrip('-')) if rng else 0
        self.reqs.append((url, start))
        if self.hook:
            r = self.hook(name, start, o)
            if r is not None: return r
        data = self.data[name]
        base = dict(chunk=65536, ctype='audio/mpeg')
        if start:
            return dict(base, code=206, body=data[start:], length=len(data) - start, head=[f'Content-Range: bytes {start}-{len(data) - 1}/{len(data)}'])
        return dict(base, code=200, body=data, length=len(data))

    @staticmethod
    def unq(s): return unquote(s)

    def preview(self):
        r, th = BK.preview(self.m, self.ident)
        assert r == 0 and fn(self.m, 'bn_preview_count') == len(self.parts), 'the preview is held'

    def create(self, title='My Book', author='Au Thor', ident=None):
        return create(self.m, ident or self.ident, title, author)

    def book(self, title='My Book', author='Au Thor'):
        self.preview()
        r, d = self.create(title, author)
        assert r == 0, f'created ({r})'
        return d


def create(m, ident, title, author):
    out = m.alloc(160)
    r = fn(m, 'bd_create', m.cstr(ident), m.cstr(title), m.cstr(author), out, 160)
    return r, m.read_cstr(out) if r == 0 else None


def start(m, d, run=True):
    m.thread = None
    r = fn(m, 'bd_start', cz(m, d))
    th = m.thread
    if run and th: PCN.work(m, th)
    return r, th


def progress(m, inside=False):
    a = [m.alloc(4) for _ in range(5)]
    ok = m.nested(PSYMS['bd_progress'], *a) if inside else fn(m, 'bd_progress', *a)
    return (m.word(a[0]), m.word(a[1]), m.word(a[2]), m.word(a[3]), m.word(a[4])) if ok else None


def result(m, d):
    c = m.alloc(4)
    r = fn(m, 'bd_result', key_of(d), c)
    return r, m.word(c)


def view(m): return dict(active=fn(m, 'bd_active'), gen=fn(m, 'bd_gen'), busy=fn(m, 'pn_dl_running') + fn(m, 'pn_job_busy') + fn(m, 'pn_busy'))   # busy: what the job slot and the episode queue show (a book download shows in neither)


def manifest(m, d): return m.fs.get(f'{ROOT_DIR}/{d}/.librivox')


def folder(m, d): return sorted(p[len(f'{ROOT_DIR}/{d}/'):] for p in m.fs if p.startswith(f'{ROOT_DIR}/{d}/'))


def man_text(parts, ident='some_book', title='T', author='A', head=None):
    lines = [head or 'M1PLUS-LIBRIVOX 1', f'i={ident}', f't={title}', f'a={author}']
    lines += ['\t'.join(str(x) for x in p) for p in parts]
    return ('\n'.join(lines) + '\n').encode('utf-8')


# ---------------------------------------------------------------------------
def name_tests(ctx):
    """bd_fat: the FAT characters, spaces, dots, UTF-8 cuts, invalid bytes."""
    expect = ctx.expect
    m = machine()
    for text, mx, want in (('plain title', 80, 'plain title'), ('a:b*c?d"e<f>g|h\\i/j', 80, 'a b c d e f g h i j'), ('tab\there\nnewline\x01ctl\x7f.', 80, 'tab here newline ctl'),
                           ('  ..Title. . ', 80, 'Title'), ('x  y   z', 80, 'x y z'), ('.hidden', 80, 'hidden'), ('end...', 80, 'end'), ('', 80, ''), (':::', 80, ''), ('...', 80, ''),
                           ('Les Misérables', 80, 'Les Misérables'), ('é' * 50, 7, 'é' * 3), ('三国演义', 7, '三国'), ('三国演义', 6, '三国'), ('三国演义', 5, '三'), ('三国演义', 2, ''), ('😀😀', 7, '😀'),
                           ('abc. def', 4, 'abc'), ('abc def', 4, 'abc'), ('ab' + 'c' * 200, 10, 'ab' + 'c' * 8), ('a|b', 3, 'a b')):
        got = fat(m, text, mx)
        expect(got == want, f'bd_fat({text!r}, {mx}) = {got!r}, want {want!r}')
    expect(fat(m, b'a\xffb\xc3', 20) == 'ab' and fat(m, b'\xe4\xb8a\x80b', 20) == 'ab' and fat(m, b'caf\xc3\xa9\xc3', 20) == 'café', 'bytes that are not UTF-8 (a stray lead or continuation byte) are dropped')
    for mx in range(0, 12):
        got = fat(m, 'ab é三 😀 cd', mx)
        got.encode('utf-8')
        expect(len(got.encode('utf-8')) <= mx and not got.endswith((' ', '.')), f'every cut length keeps the limit and a clean end (max {mx}: {got!r})')


def create_tests(ctx):
    """bd_create: the folder, the cover, the manifest, the local names, collisions, reuse, failures."""
    expect = ctx.expect
    w = World([(n, t, s) for n, t, s in ((f'prideandprejudice_{x}_austen_64kb.mp3', t, 1000 + i) for i, (x, t) in enumerate(zip('01 02 03'.split(), ('Chapters 1-3', 'Chapter 6', 'Chapters 60-61'))))], ident='pride_and_prejudice_librivox')
    m = w.m
    w.preview()
    r, d = w.create('Pride and Prejudice', 'Jane Austen')
    root = ROOT_DIR
    expect(r == 0 and d == 'Pride and Prejudice' and f'{root}/{d}' in m.dirs and root in m.dirs, f'the book folder is made under Audiobooks ({r}, {d})')
    want = ('M1PLUS-LIBRIVOX 1\ni=pride_and_prejudice_librivox\nt=Pride and Prejudice\na=Jane Austen\n'
            '1 Chapters 1-3.mp3\t60\t1000\tprideandprejudice_01_austen_64kb.mp3\tChapters 1-3\n'
            '2 Chapter 6.mp3\t60\t1001\tprideandprejudice_02_austen_64kb.mp3\tChapter 6\n'
            '3 Chapters 60-61.mp3\t60\t1002\tprideandprejudice_03_austen_64kb.mp3\tChapters 60-61\n').encode()
    expect(manifest(m, d) == want, f'the manifest: header, one line a part: {manifest(m, d)}')
    expect(folder(m, d) == ['.librivox', 'cover.jpg'] and m.fs[f'{root}/{d}/cover.jpg'] == BK.THUMB, f'the folder holds the manifest and the cover only (no temp file): {folder(m, d)}')
    expect(m.fs.get(BK.DIR + '/preview.jpg') == BK.THUMB, 'the preview keeps its picture (a copy was made)')
    b = read_book(m, d)
    expect(b and b['id'] == 'pride_and_prejudice_librivox' and b['title'] == 'Pride and Prejudice' and b['author'] == 'Jane Austen' and b['counts'] == (0, 3, 3003) and b['present'] == [0, 0, 0] and
           [p['file'] for p in b['parts']] == ['1 Chapters 1-3.mp3', '2 Chapter 6.mp3', '3 Chapters 60-61.mp3'] and b['parts'][2] == dict(file='3 Chapters 60-61.mp3', name='prideandprejudice_03_austen_64kb.mp3', title='Chapters 60-61', secs=60, bytes=1002),
           f'it reads back: {b}')
    # the same book again: the folder is reused as it is
    before = dict(m.fs)
    r, d2 = w.create('Another title', 'Someone else')
    expect(r == 0 and d2 == d and m.fs == before and not [p for p in m.dirs if 'Another' in p or '(2)' in p], 'the folder that names the identifier is reused, nothing rewritten')
    # a folder of that identifier under another name is the book
    m.put(f'{root}/Custom Name/.librivox', man_text([], 'other_librivox'))
    # another identifier with the same title: ' (2)', ' (3)'
    w2 = World(ident='b2_librivox', parts=w.parts)
    w2.m.fs, w2.m.dirs = m.fs, m.dirs
    w2.preview()
    r, d3 = w2.create('Pride and Prejudice', 'x')
    expect(r == 0 and d3 == 'Pride and Prejudice (2)' and b'i=b2_librivox' in manifest(w2.m, d3), f'a folder of that name that is another book: " (2)" ({d3})')
    w2.ident = 'b3_librivox'; w2.files = BK.result(*[obj(n, t, s) for n, t, s in w.parts]); w2.preview()
    r, d4 = w2.create('Pride and Prejudice', 'x')
    expect(d4 == 'Pride and Prejudice (3)', f'" (3)": {d4}')
    # a folder that is not a book, a file of the name
    m.put(f'{root}/Plain/a.mp3', b'x'); m.put(f'{root}/Filey', b'x')
    for title, want_dir in (('Plain', 'Plain (2)'), ('Filey', 'Filey (2)')):
        w2.ident = 'c_' + title; w2.preview()
        r, dd = w2.create(title, '')
        expect(r == 0 and dd == want_dir, f'{title!r} exists and is not this book: {dd}')
    # reuse by identifier whatever the folder is called
    w3 = World(ident='other_librivox', parts=w.parts)
    w3.m.fs, w3.m.dirs = m.fs, m.dirs
    w3.preview()
    r, dd = w3.create('Whatever', 'x')
    expect(r == 0 and dd == 'Custom Name', f'a manifest that names the identifier decides, not the folder name ({dd})')
    # an identifier is in one folder at most: the 100-folder bound of the scan does not matter for the normal case
    # failures
    m2 = World().m
    expect(create(m2, 'test_book_librivox', 'T', 'A')[0] == PN['NOBOOK'], 'no preview held: PN_NOBOOK')
    w4 = World(); w4.preview()
    expect(create(w4.m, 'another_id', 'T', 'A')[0] == PN['NOBOOK'] and create(w4.m, 'a/b', 'T', 'A')[0] == PN['NOBOOK'], 'an identifier that is not the held one, or no identifier: PN_NOBOOK')
    w4.m.card_mounted = False
    expect(create(w4.m, w4.ident, 'T', 'A')[0] == PN['STORAGE'] and not [p for p in w4.m.dirs if 'Audiobooks' in p], 'no card: PN_STORAGE, nothing made')
    w5 = World(); w5.preview()
    w5.m.fail.add(('mkdir', ROOT_DIR))
    expect(create(w5.m, w5.ident, 'T', 'A')[0] == PN['STORAGE'], 'no Audiobooks folder and none can be made: PN_STORAGE')
    w6 = World(); w6.preview()
    w6.m.fail.add(('mkdir', f'{ROOT_DIR}/Book'))
    expect(create(w6.m, w6.ident, 'Book', 'A')[0] == PN['STORAGE'] and f'{ROOT_DIR}/Book' not in w6.m.dirs, 'the folder cannot be made: PN_STORAGE')
    w7 = World(); w7.preview()
    w7.m.fail.add(('open', f'{ROOT_DIR}/Book/.librivox.tmp'))
    r, _ = create(w7.m, w7.ident, 'Book', 'A')
    expect(r == PN['STORAGE'] and f'{ROOT_DIR}/Book' not in w7.m.dirs and not [p for p in w7.m.fs if p.startswith(f'{ROOT_DIR}/Book/')], f'the manifest cannot be written: PN_STORAGE, no folder, no cover left ({r})')
    w8 = World(); w8.preview()
    r, th = BK.preview(w8.m, 'x_librivox', run=False)
    expect(r == 0 and create(w8.m, 'x_librivox', 'T', 'A')[0] == PN['NOBOOK'], 'the preview still running: nothing is held yet, PN_NOBOOK')
    # a title with nothing usable; no picture
    w9 = World(); w9.preview(); w9.m.fs.pop(BK.DIR + '/preview.jpg')
    r, dd = create(w9.m, w9.ident, ':::', 'A')
    expect(r == 0 and dd == 'Audiobook' and 'cover.jpg' not in ''.join(folder(w9.m, dd)), f'a title of nothing but forbidden characters: "Audiobook"; no picture, no cover ({dd})')
    # the Audiobooks folder spelled otherwise on the card is the one used
    w10 = World(); w10.preview(); w10.m.dirs.add('/mnt/mmc/AUDIOBOOKS')
    r, dd = create(w10.m, w10.ident, 'Book', 'A')
    expect(r == 0 and '/mnt/mmc/AUDIOBOOKS/Book' in w10.m.dirs and ROOT_DIR not in w10.m.dirs, f'the folder as the card spells it ({dd})')
    # a png picture is cover.png
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (180, 180), (90, 40, 30)).save(buf, 'PNG'); png = buf.getvalue()
    w11 = World(); w11.site_img = png
    w11.preview()
    m11 = w11.m
    expect(m11.fs.get(BK.DIR + '/preview.png') == png, 'the preview fetched a png')
    r, dd = create(m11, w11.ident, 'Book', 'A')
    expect(r == 0 and folder(m11, dd) == ['.librivox', 'cover.png'] and m11.fs[f'{ROOT_DIR}/{dd}/cover.png'] == png, f'a png picture is cover.png ({folder(m11, dd)})')


def part_name_tests(ctx):
    """The local names: width of the number, FAT characters, empty titles, UTF-8, the limits."""
    expect = ctx.expect

    def names(parts, title='Book'):
        w = World(parts)
        w.preview()
        r, d = w.create(title, 'A')
        assert r == 0
        b = read_book(w.m, d)
        return d, [p['file'] for p in b['parts']], w, b

    for n, w_ in ((1, 1), (9, 1), (10, 2), (99, 2), (100, 3), (300, 3)):
        d, files, w, b = names([(f'p{i:03}.mp3', f'T{i}', 10) for i in range(n)])
        expect(len(files) == n and files[0] == '0' * (w_ - 1) + '1 T0.mp3' and files[-1] == f'{n:0{w_}} T{n - 1}.mp3', f'{n} parts: numbers padded to {w_} digits ({files[0]}, {files[-1]})')
    # the reading order is kept: the model lists a book's files in natural order (bk_natcmp), and that must be the manifest's order whatever the titles are
    def cmp(m, a, b):
        r = m.call(PSYMS['bk_natcmp'], a0=m.cstr(a), a1=m.cstr(b), count=2000000)
        return r - (1 << 32) if r & 0x80000000 else r

    def titled(i, n, kind):
        return {'plain': f'Chapter {i + 1}', 'reversed': f'{n - i} to go', 'digits': str((i * 7919) % 1000), 'same': 'Chapter', 'own': f'{i + 1:03} - Name {i}', 'none': None, 'spaced': f' {n - i}. x'}[kind]
    for n in (9, 10, 11, 99, 100, 101, 300):
        for kind in ('plain', 'reversed', 'digits', 'same', 'own', 'none', 'spaced'):
            if n == 300 and kind not in ('reversed', 'digits'): continue
            d, files, w, b = names([(f'p{i:03}.mp3', titled(i, n, kind), 10) for i in range(n)])
            bad = [(files[i], files[i + 1]) for i in range(n - 1) if cmp(w.m, files[i], files[i + 1]) >= 0]
            expect(len(files) == n and not bad and [p['name'] for p in b['parts']] == [f'p{i:03}.mp3' for i in range(n)], f'{n} parts, {kind} titles: the natural order of the local names is the reading order ({bad[:2]})')
    # the archive's own order: names in natural order, whatever order the answer lists them in
    d, files, w, b = names([('b_10.mp3', 'Ten', 5), ('b_2.mp3', 'Two', 5), ('b_1.mp3', 'One', 5), ('b_9.mp3', 'Nine', 5)])
    expect(files == ['1 One.mp3', '2 Two.mp3', '3 Nine.mp3', '4 Ten.mp3'], f'the parts are numbered in the natural order of the archive\'s names: {files}')
    # a title that carries the part's own number is not numbered twice
    d, files, w, b = names([('a1.mp3', '001 - Marseilles', 5), ('a2.mp3', '02. Father and Son', 5), ('a3.mp3', '3', 5), ('a4.mp3', '7 Days', 5), ('a5.mp3', '5th Avenue', 5), ('a6.mp3', '6: ', 5), ('a7.mp3', '0070 x', 5)])
    expect(files == ['1 Marseilles.mp3', '2 Father and Son.mp3', '3 3.mp3', '4 7 Days.mp3', '5 5th Avenue.mp3', '6 6.mp3', '7 0070 x.mp3'], f'a leading number equal to the part\'s goes, any other stays: {files}')
    expect(b['parts'][0]['title'] == '001 - Marseilles', 'the manifest keeps the title as the archive has it')
    d, files, w, b = names([('a.mp3', 'What: Why? "Yes" <no> | a\\b/c', 5), ('b.mp3', None, 5), ('c.name.with.dots.mp3', '', 5), ('???.mp3', '', 5), ('.mp3', None, 5), ('noext', None, 5),
                            ('é.mp3', 'Café ' + '三' * 4, 5), ('d.mp3', '  ..  ', 5), ('e.mp3', 'Same', 5), ('f.mp3', 'Same', 5), ('s.mp3', ':::', 5)])
    want = ['01 mp3.mp3', '02 Part 2.mp3', '03 What Why Yes no a b c.mp3', '04 b.mp3', '05 c.name.with.dots.mp3', '06 d.mp3', '07 Same.mp3', '08 Same.mp3', '09 noext.mp3', '10 s.mp3', '11 Café 三三三三.mp3']
    expect(files == want, f'FAT characters become spaces; an empty title takes the archive name\'s stem, then "Part N": {files}')
    expect(all(not any(c in f for c in '\\/:*?"<>|') and not f.endswith(('. mp3', ' .mp3')) for f in files), 'no forbidden character in a local name')
    expect(len(set(files)) == len(files), 'names are distinct')
    # the stored title is the archive's, as it came (control bytes aside)
    expect(b['parts'][2]['title'].startswith('What: Why?') and b['parts'][3]['title'] == 'b' and b['parts'][1]['name'] == '???.mp3' and b['parts'][9]['title'] == ':::', f'the manifest keeps the archive\'s title and name: {b["parts"][2]}')
    # long names: the model's name limit and the download path limit
    long_title = 'x' * (TITLE - 1)
    d, files, w, b = names([(f'part{i:03}.mp3', long_title, 10) for i in range(300)], title='L' * 200)
    expect(len(d) == 72, f'a folder title is cut at 72 bytes ({len(d)})')
    worst = max(len(f'{ROOT_DIR}/{d}/{f}.part') for f in files)
    expect(all(len(f.encode('latin-1')) < FILE for f in files) and worst <= PATH_MAX and files[299] == '300 ' + long_title + '.mp3', f'300 long names: under {FILE} bytes, the .part path within {PATH_MAX} ({worst})')
    d, files, w, b = names([('a.mp3', 'é' * 47, 1)], title='三' * 40)
    expect(d == L('三' * 24), f'the folder title is cut on a character boundary: {d!r}')
    expect(files == ['1 ' + 'é' * 47 + '.mp3'], f'the title of a part keeps its UTF-8 ({files})')
    # a collision suffix keeps the folder within its limit
    w = World(); w.preview(); w.m.dirs.add(f'{ROOT_DIR}/{"L" * 72}')
    r, dd = create(w.m, w.ident, 'L' * 200, 'A')
    expect(r == 0 and dd == 'L' * 72 + ' (2)', f'a long folder title with a suffix: {dd}')
    # a manifest field never carries a tab or line feed
    d, files, w, b = names([('a.mp3', 'Tab\there\nand there', 1)], title='T\ta\nb')
    expect(b['parts'][0]['title'] == 'Tab here and there' and b['title'] == 'T a b' and manifest(w.m, d).count(b'\t') == 4 and manifest(w.m, d).count(b'\n') == 5, f'tabs and line feeds in a field become spaces: {b["parts"][0]}')


def manifest_tests(ctx):
    """bd_open, bd_counts, bd_present, bd_find: the reader and its refusals."""
    expect = ctx.expect
    m = machine()
    root = ROOT_DIR
    good = [('1 A.mp3', 60, 1000, 'a.mp3', 'A'), ('2 B.mp3', 0, 0, 'b b.mp3', ''), ('3 C.mp3', 7, 4294967295, 'c.mp3', 'C c')]
    m.put(f'{root}/Good/.librivox', man_text(good, 'good_id', 'The Good Book', 'Auth'))
    m.put(f'{root}/Good/1 A.mp3', b'x')
    b = read_book(m, 'Good')
    expect(b and b['id'] == 'good_id' and b['title'] == 'The Good Book' and b['author'] == 'Auth' and b['dir'] == 'Good' and b['root'] == root and len(b['parts']) == 3, f'a manifest is read: {b and b["parts"]}')
    expect(b['parts'][2] == dict(file='3 C.mp3', name='c.mp3', title='C c', secs=7, bytes=4294967295) and b['parts'][1]['title'] == '', 'a part: file, seconds, bytes, archive name, title (maybe empty)')
    expect(b['present'] == [1, 0, 0] and b['counts'] == (1, 2, 4294967295), f'present = the file is on the card; missing and their bytes (saturating): {b["counts"]}')
    m.put(f'{root}/Good/2 B.mp3.part', b'x')
    expect(read_book(m, 'Good')['present'] == [1, 0, 0], 'a .part file is not a part')
    # tolerance
    for label, text in (('CRLF', man_text(good, 'good_id').replace(b'\n', b'\r\n')), ('unknown keys and blank lines', b'M1PLUS-LIBRIVOX 1\n\nz=1\ni=good_id\nlang=en\n\n' + man_text(good, '')[len(b'M1PLUS-LIBRIVOX 1\ni=\nt=T\na=A\n'):]),
                        ('no t= and a=', b'M1PLUS-LIBRIVOX 1\ni=good_id\n1 A.mp3\t1\t2\ta.mp3\t\n'), ('no parts', b'M1PLUS-LIBRIVOX 1\ni=good_id\nt=T\na=A\n'), ('no final line feed', b'M1PLUS-LIBRIVOX 1\ni=good_id\n1 A.mp3\t1\t2\ta.mp3\tA'),
                        ('a leading dot in the archive name', man_text([('1.mp3', 1, 2, '.hidden.mp3', 'x')], 'good_id'))):
        m.put(f'{root}/Tol/.librivox', text)
        bk = read_book(m, 'Tol')
        expect(bk is not None and bk['id'] == 'good_id', f'tolerated: {label}')
    m.put(f'{root}/Tol/.librivox', man_text(good, 'good_id', 'T' * 200, 'A' * 200))
    bk = read_book(m, 'Tol')
    expect(bk and len(bk['title'].encode()) == TITLE - 1 and len(bk['author'].encode()) == AUTHOR - 1, 'a title and an author that are too long are cut')
    # refused
    P = good[0]
    bad = {'no magic': b'i=good_id\n' + man_text([P])[len(b'M1PLUS-LIBRIVOX 1\n'):], 'wrong version': man_text([P], head='M1PLUS-LIBRIVOX 2'), 'magic with a tail': man_text([P], head='M1PLUS-LIBRIVOX 1 x'),
           'no i=': b'M1PLUS-LIBRIVOX 1\nt=T\n', 'empty i=': b'M1PLUS-LIBRIVOX 1\ni=\n', 'id with a slash': man_text([P], 'a/b'), 'id with a space': man_text([P], 'a b'), 'id too long': man_text([P], 'a' * ID),
           'four fields': b'M1PLUS-LIBRIVOX 1\ni=x\n1.mp3\t1\t2\ta.mp3\n', 'six fields': b'M1PLUS-LIBRIVOX 1\ni=x\n1.mp3\t1\t2\ta.mp3\tT\tU\n', 'seconds not a number': man_text([('1.mp3', 'x', 2, 'a.mp3', '')]),
           'bytes negative': man_text([('1.mp3', 1, -2, 'a.mp3', '')]), 'bytes over 2^32': man_text([('1.mp3', 1, 4294967296, 'a.mp3', '')]), 'empty seconds': man_text([('1.mp3', '', 2, 'a.mp3', '')]),
           'empty file name': man_text([('', 1, 2, 'a.mp3', '')]), 'file with a slash': man_text([('a/b.mp3', 1, 2, 'a.mp3', '')]), 'file with a backslash': man_text([('a\\b.mp3', 1, 2, 'a.mp3', '')]),
           'file starting with a dot': man_text([('.a.mp3', 1, 2, 'a.mp3', '')]), 'file ..': man_text([('..', 1, 2, 'a.mp3', '')]), 'file too long': man_text([('f' * FILE, 1, 2, 'a.mp3', '')]),
           'archive name with a slash': man_text([('1.mp3', 1, 2, 'x/a.mp3', '')]), 'archive name ..': man_text([('1.mp3', 1, 2, '..', '')]), 'empty archive name': man_text([('1.mp3', 1, 2, '', '')]),
           'control byte in the file name': man_text([('a\x01.mp3', 1, 2, 'a.mp3', '')]), 'the same file twice': man_text([('1.mp3', 1, 2, 'a.mp3', ''), ('1.mp3', 1, 2, 'b.mp3', '')]),
           'a line that is no key=value': b'M1PLUS-LIBRIVOX 1\ni=x\nhello\n', 'a key after the parts': man_text([P]) + b't=late\n', 'more than 300 parts': man_text([(f'{i}.mp3', 1, 2, f'a{i}.mp3', '') for i in range(MAXP + 1)]),
           'a line starting with =': b'M1PLUS-LIBRIVOX 1\ni=x\n=x\n', 'empty': b'', 'only the magic': b'M1PLUS-LIBRIVOX 1\n', 'a binary file': bytes(range(256)) * 20, 'too large': man_text([P]) + b'#' * MAN_CAP}
    for label, text in bad.items():
        m.put(f'{root}/Bad/.librivox', text)
        expect(read_book(m, 'Bad') is None, f'refused: {label}')
    m.put(f'{root}/Bad/.librivox', man_text([(f'{i}.mp3', 1, 2, f'a{i}.mp3', '') for i in range(MAXP)]))
    expect(read_book(m, 'Bad') is not None and len(read_book(m, 'Bad')['parts']) == MAXP, 'exactly 300 parts are fine')
    expect(read_book(m, 'Nope') is None and read_book(m, '') is None and read_book(m, '../x') is None and read_book(m, '.hidden') is None and read_book(m, 'a/b') is None, 'a folder with no manifest, or a name that is no folder name: none')
    # bd_find
    def find(ident, mach=m):
        out = mach.alloc(160)
        r = fn(mach, 'bd_find', mach.cstr(ident), out, 160)
        return mach.read_cstr(out) if r else None
    expect(find('good_id') == 'Good' and find('nothing') is None and find('') is None, 'bd_find: the folder whose manifest names the identifier')
    m.fs.pop(f'{root}/Bad/.librivox'); m.put(f'{root}/Bad/.librivox', b'M1PLUS-LIBRIVOX 1\ni=bad_id\nnonsense\n')
    expect(find('bad_id') is None and find('good_id') == 'Good', 'bd_find: a manifest whose header is malformed names nothing')
    m.put(f'{root}/Other/.librivox', man_text([P], 'good_id'))
    expect(find('good_id') in ('Good', 'Other'), 'bd_find: an identifier twice: one of them')
    m2 = machine()
    for i in range(105): m2.put(f'{root}/f{i:03}/.librivox', man_text([], f'id{i:03}'))
    expect(find('id050', m2) == 'f050' and find('id099', m2) == 'f099' and find('id104', m2) is None, 'bd_find looks at 100 folders at most')
    m3 = machine()
    m3.put(f'{root}/Big/.librivox', man_text([(f'{i}.mp3', 1, 2, f'a{i}.mp3', 'T' * 90) for i in range(MAXP)], 'big_id'))
    expect(find('big_id', m3) == 'Big', 'bd_find reads only the header of a large manifest')
    m3.put(f'{root}/Big/.librivox', b'M1PLUS-LIBRIVOX 1\n' + b'i=late_id\n')
    expect(find('late_id', m3) == 'Big', 'a header at the very start of a short file')


def model_tests(ctx):
    """patch/bkmodel.c: a folder with a manifest is a book, a .part is no part, neither disturbs a key."""
    expect = ctx.expect
    m = BKM.BM()
    root = ROOT_DIR
    m.put(f'{root}/Fresh/.librivox', man_text([('1 A.mp3', 1, 2, 'a.mp3', 'A')]))
    m.put(f'{root}/Fresh/cover.jpg', b'x')
    m.put(f'{root}/Fresh/1 A.mp3.part', b'x' * 5000)
    m.put(f'{root}/Half/.librivox', man_text([('1 A.mp3', 1, 2, 'a.mp3', 'A'), ('2 B.mp3', 1, 2, 'b.mp3', 'B')]))
    m.put(f'{root}/Half/1 A.mp3', b'x'); m.sizes[f'{root}/Half/1 A.mp3'] = 3000
    m.put(f'{root}/Half/2 B.mp3.part', b'x'); m.sizes[f'{root}/Half/2 B.mp3.part'] = 9000
    m.put(f'{root}/Plain/notes.txt', b'x')
    m.put(f'{root}/Dots/.hidden', b'x')
    books, _ = m.books()
    by = {b['dir']: b for b in books}
    expect(sorted(by) == ['Fresh', 'Half'], f'a folder with a manifest is a book even with no part; a folder with only other files is not: {sorted(by)}')
    expect(by['Fresh'] == dict(dir='Fresh', title='Fresh', cover='cover.jpg', parts=0, kb=0, hash=PCN.pc_hash('audiobooks/Fresh'), loose=0), f'the book with no part yet: 0 parts, the cover, the key: {by["Fresh"]}')
    expect(by['Half']['parts'] == 1 and by['Half']['kb'] == 3 and by['Half']['hash'] == PCN.pc_hash('audiobooks/Half'), f'a .part file is not counted: {by["Half"]}')
    # the parts of Half through a records of the model's scan
    _, arr = m.books()
    idx = [b['dir'] for b in books].index('Half')
    parts = m.parts(arr + idx * BKM.BOOK)
    expect([p['rel'] for p in parts] == ['1 A.mp3'], f'bk_load_parts: the finished part only: {parts}')
    idx0 = [b['dir'] for b in books].index('Fresh')
    expect(m.parts(arr + idx0 * BKM.BOOK) == [], 'bk_load_parts: no parts for a book with none yet')
    # progress by bytes: the manifest and the .part change nothing
    m2 = BKM.BM()
    m2.put(f'{root}/Half/1 A.mp3', b'x'); m2.sizes[f'{root}/Half/1 A.mp3'] = 3000
    b2, arr2 = m2.books()
    p2 = m2.parts(arr2)
    m2.put(f'{root}/Half/.librivox', man_text([('1 A.mp3', 1, 2, 'a.mp3', 'A')]))
    m2.put(f'{root}/Half/2 B.mp3.part', b'x')
    b3, arr3 = m2.books()
    p3 = m2.parts(arr3)
    expect(b2[0]['hash'] == b3[0]['hash'] and b2[0]['kb'] == b3[0]['kb'] and [(p['rel'], p['hash'], p['kb']) for p in p2] == [(p['rel'], p['hash'], p['kb']) for p in p3], 'the manifest and a .part file change neither the key nor a part\'s resume key nor the size')


def job_tests(ctx):
    """The download job against the scripted archive."""
    expect = ctx.expect
    w = World()
    m = w.m
    d = w.book()
    root = f'{ROOT_DIR}/{d}'
    key = key_of(d)
    expect(view(m) == dict(active=0, gen=view(m)['gen'], busy=0) and progress(m) is None and result(m, d) == (R_NONE, 0), 'before any job: nothing runs, no result')
    seen = []

    def sample(url, sent, total):
        seen.append((url.rsplit('/', 1)[1], sent, progress(m, True), m.nested(PSYMS['bd_active']), m.nested(PSYMS['pn_job_busy']), m.nested(PSYMS['pn_dl_running']), m.nested(PSYMS['pn_busy'])))
    orig = w.site

    def site(url, o):
        r = orig(url, o)
        if '/download/' in url and 'body' in r: r = dict(r, xfer=sample)
        return r
    m.curl_site = site
    g0 = view(m)['gen']
    r, th = start(m, d, run=False)
    expect(r == 0 and th and th[0] == PSYMS['bd_main'] and view(m)['active'] == key and view(m)['busy'] == 0 and progress(m)[:2] == (0, 3), f'bd_start starts a thread of its own and leaves the job slot and the episode queue alone: {r}, {progress(m)}')
    m.thread = None
    expect(start(m, d, run=False) == (0, None) and fn(m, 'pn_dl_start') == 0 and view(m)['busy'] == 0 and fn(m, 'bd_active') == key,
           'while it runs: asking for the same book again is OK and creates no thread; the job slot and the episode queue stay idle')
    PCN.work(m, th)
    expect(view(m)['active'] == 0 and view(m)['busy'] == 0 and progress(m) is None and view(m)['gen'] > g0 and result(m, d) == (R_DONE, 0), f'the job ends: DONE, nothing active, the generation moved ({result(m, d)})')
    expect([u for u, s in w.reqs] == [f'{HOST}/download/{w.ident}/{n}' for n, t, sz in w.parts] and all(s == 0 for u, s in w.reqs), f'the parts are asked for in order, each from the start: {w.reqs}')
    files = [f'{root}/{x}' for x in ('1 Chapter One.mp3', '2 Chapter Two.mp3', '3 Chapter Three.mp3')]
    expect(all(m.fs.get(f) == w.data[n] for f, (n, t, sz) in zip(files, w.parts)) and not [p for p in m.fs if p.endswith('.part')], 'every part is on the card whole under its local name; no .part left')
    expect(read_book(m, d)['counts'] == (3, 0, 0), 'the counts: all present')
    expect(seen and all(s[3] == key and s[4] == 0 and s[5] == 0 and s[6] == 0 and s[2] and s[2][1] == 3 for s in seen), 'while the transfers run: the book is active; pn_job_busy, pn_dl_running and pn_busy are all 0 (the download is a thread of its own)')
    first = [s for s in seen if s[0] == w.parts[0][0]]
    expect(first and first[-1][2][0] == 0 and first[-1][2][3] == 70000 and 0 < first[-1][2][2] <= 70000 and [s for s in seen if s[0] == w.parts[2][0]][-1][2][0] == 2, f'progress: the part index, the bytes got and the part\'s size ({first[-1][2]})')
    # a book with everything: start again does nothing
    m.thread = None
    expect(start(m, d)[0] == 0 and m.thread is None and result(m, d) == (R_DONE, 0) and len(w.reqs) == 3, 'nothing missing: nothing starts, the result is DONE')
    # only the missing parts, resume of a .part
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    m.fs[f'{root}/1 Chapter One.mp3'] = w.data[w.parts[0][0]]
    m.fs[f'{root}/2 Chapter Two.mp3.part'] = w.data[w.parts[1][0]][:30000]
    r, th = start(m, d)
    expect(r == 0 and w.reqs == [(f'{HOST}/download/{w.ident}/{w.parts[1][0]}', 30000), (f'{HOST}/download/{w.ident}/{w.parts[2][0]}', 0)], f'the present part is not asked for; the .part resumes with a Range: {w.reqs}')
    expect(m.fs.get(f'{root}/2 Chapter Two.mp3') == w.data[w.parts[1][0]] and m.fs.get(f'{root}/3 Chapter Three.mp3') == w.data[w.parts[2][0]] and not [p for p in m.fs if p.endswith('.part')] and result(m, d) == (R_DONE, 0), 'the resumed file is whole and right')
    # a server that ignores the Range: the file starts again
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    m.fs[f'{root}/1 Chapter One.mp3.part'] = b'garbage' * 1000
    w.hook = lambda name, start_, o: dict(code=200, body=w.data[name], length=len(w.data[name]), chunk=65536, ctype='audio/mpeg') if start_ else None
    start(m, d)
    expect(m.fs.get(f'{root}/1 Chapter One.mp3') == w.data[w.parts[0][0]] and result(m, d) == (R_DONE, 0), 'a server that answers 200 to a Range: the part starts again and is right')
    # pause and restart
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    hit = []

    def pause_at(name, start_, o):
        if name != w.parts[1][0] or hit: return None
        def x(url, sent, total):
            if sent >= 20000 and not hit:
                hit.append(sent); m.nested(PSYMS['bd_pause'], key_of(d))
        return dict(chunk=10000, ctype='audio/mpeg', code=200, body=w.data[name], length=len(w.data[name]), xfer=x)
    w.hook = pause_at
    r, th = start(m, d)
    got = len(m.fs.get(f'{root}/2 Chapter Two.mp3.part', b''))
    expect(r == 0 and result(m, d) == (R_PAUSED, 0) and view(m)['active'] == 0 and view(m)['busy'] == 0 and 0 < got < 50000 and got == w.data[w.parts[1][0]][:got].__len__() and m.fs[f'{root}/2 Chapter Two.mp3.part'] == w.data[w.parts[1][0]][:got] and
           m.fs.get(f'{root}/1 Chapter One.mp3') == w.data[w.parts[0][0]] and f'{root}/3 Chapter Three.mp3' not in m.fs and len(w.reqs) == 2, f'a pause stops at once and keeps the .part ({result(m, d)}, {got} bytes, {len(w.reqs)} requests)')
    w.reqs.clear()
    r, th = start(m, d)
    expect(r == 0 and w.reqs[0] == (f'{HOST}/download/{w.ident}/{w.parts[1][0]}', got) and len(w.reqs) == 2 and result(m, d) == (R_DONE, 0) and m.fs.get(f'{root}/2 Chapter Two.mp3') == w.data[w.parts[1][0]],
           f'restart: part 1 is not asked for again, part 2 resumes at {got}, and the book completes ({w.reqs})')
    # a pause before the worker has run
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    r, th = start(m, d, run=False)
    fn(m, 'bd_pause', key_of(d))
    PCN.work(m, th)
    expect(result(m, d) == (R_PAUSED, 0) and not w.reqs and view(m)['busy'] == 0, 'a pause asked before the first request: nothing fetched, PAUSED')
    fn(m, 'bd_pause', key_of(d))
    expect(view(m)['active'] == 0 and start(m, d)[0] == 0 and result(m, d) == (R_DONE, 0), 'a pause with nothing running does nothing (the next job is not stopped)')
    # pn_cancel does not stop a book job (leaving a Podcasts page must not end it)
    w = World(); m = w.m; d = w.book()
    w.hook = lambda name, start_, o: dict(chunk=20000, ctype='audio/mpeg', code=200, body=w.data[name], length=len(w.data[name]), xfer=lambda url, sent, total: m.nested(PSYMS['pn_cancel']) if sent == 20000 else None)
    start(m, d)
    expect(result(m, d) == (R_DONE, 0), 'pn_cancel (a Podcasts page leaving) does not stop a book job')
    # terminal failures stop the job with the code
    for label, hook, code in (('404 on a part', lambda n, s, o: dict(rc=22, code=404) if n == W3[1] else None, PN['GONE']), ('HTTP 410', lambda n, s, o: dict(rc=22, code=410) if n == W3[1] else None, PN['GONE']),
                              ('HTTP 403', lambda n, s, o: dict(rc=22, code=403) if n == W3[1] else None, PN['HTTP']), ('a web page', lambda n, s, o: dict(ctype='text/html; charset=utf-8', body=b'<html>no</html>', code=200) if n == W3[1] else None, PN['NOTAUDIO']),
                              ('a certificate error', lambda n, s, o: dict(rc=60) if n == W3[1] else None, PN['CERT'])):
        w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
        W3 = [n for n, t, s in w.parts]
        w.hook = hook
        start(m, d)
        expect(result(m, d) == (R_FAILED, code) and view(m)['busy'] == 0 and view(m)['active'] == 0 and len(w.reqs) == 2 and m.fs.get(f'{root}/1 Chapter One.mp3') == w.data[W3[0]] and
               f'{root}/2 Chapter Two.mp3' not in m.fs and not [p for p in m.fs if p.endswith('.part')], f'{label}: the job stops with {code}; the part before it is kept, the one after is not asked for ({result(m, d)}, {len(w.reqs)} requests)')
    # the retry policy: a 503 is asked again after 10 s; four failures end the job
    w = World(); m = w.m; d = w.book(); n0 = w.parts[0][0]
    cnt = []
    w.hook = lambda n, s, o: (cnt.append(1), dict(rc=22, code=503))[1] if n == n0 and len(cnt) < 1 else None
    start(m, d)
    sl = [c[1] for c in m.calls if c[0] == 'sleep']
    expect(result(m, d) == (R_DONE, 0) and sl == [1] * 10, f'a 503 is retried after 10 s (ten one-second sleeps, so a pause is heard): {len(sl)} sleeps')
    w = World(); m = w.m; d = w.book(); n0 = w.parts[0][0]
    w.hook = lambda n, s, o: dict(rc=22, code=503) if n == n0 else None
    start(m, d)
    sl = [c[1] for c in m.calls if c[0] == 'sleep']
    expect(result(m, d) == (R_FAILED, PN['HTTP']) and sl == [1] * 70 and len(w.reqs) == 4, f'retries after 10, 20, 40 s, then it stops with the code ({result(m, d)})')
    # a pause while the worker waits to retry, and the wait flag the page reads
    w = World(); m = w.m; d = w.book(); n0 = w.parts[0][0]
    w.hook = lambda n, s, o: dict(rc=22, code=503) if n == n0 else None
    waits = []

    def on_sleep(k):
        if k == 3: waits.append(progress(m, True)[4]); m.nested(PSYMS['bd_pause'], key_of(d))
    m.on_sleep = on_sleep
    start(m, d)
    expect(waits == [1] and result(m, d) == (R_PAUSED, 0) and len(w.reqs) == 1 and view(m)['busy'] == 0 and not [p for p in m.fs if p.endswith('.part')], f'a pause is heard while waiting to retry (wait flag {waits}, result {result(m, d)})')
    # stalled network: curl error 28
    w = World(); m = w.m; d = w.book(); w.hook = lambda n, s, o: dict(rc=28)
    start(m, d)
    expect(result(m, d) == (R_FAILED, PN['NET']) and len(w.reqs) == 4, 'a network failure: retried, then PN_NET')
    # card full
    w = World(free_mb=MARGIN_MB); m = w.m; d = w.book()
    start(m, d)
    expect(result(m, d) == (R_FAILED, PN['CARDFULL']) and not w.reqs, f'a card that would keep under 32 MB free: PN_CARDFULL before the first request ({result(m, d)})')
    w = World(free_mb=MARGIN_MB + 1); m = w.m; d = w.book()
    start(m, d)
    expect(result(m, d) == (R_DONE, 0) and len(w.reqs) == 3, 'a margin that fits every part: all three are fetched')
    w = World([(f'b_0{i}.mp3', f'T{i}', 1200000) for i in range(3)], free_mb=MARGIN_MB + 1); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    start(m, d)
    expect(result(m, d) == (R_FAILED, PN['CARDFULL']) and not w.reqs, f'the first part does not fit the margin: stops before it ({result(m, d)})')
    # the guards
    for label, kw, code in (('no Wi-Fi', dict(wifi=-1), PN['NOWIFI']), ('a clock never set', dict(wall=1700000000), PN['NOCLOCK']), ('no card', dict(card_mounted=False), PN['STORAGE'])):
        w = World(); m = w.m; d = w.book()
        for k, v in kw.items(): setattr(m, k, v)
        r, th = start(m, d)
        expect(r == code and th is None and view(m)['busy'] == 0 and result(m, d) == (R_NONE, 0) and not w.reqs, f'{label}: bd_start answers {code}, nothing starts')
    w = World(); m = w.m; d = w.book(); m.present.discard(PCN.CA)
    expect(start(m, d)[0] == PN['NOCERT'], 'no CA bundle: PN_NOCERT')
    w = World(); m = w.m; d = w.book(); m.thread_ok = False
    r, th = start(m, d)
    expect(r == PN['MEM'] and view(m)['active'] == 0 and view(m)['busy'] == 0 and progress(m) is None, 'a thread that cannot be made: PN_MEM, nothing active')
    # no manifest, a malformed one
    expect(start(m, 'Nope')[0] == PN['NOBOOK'] and start(m, '')[0] == PN['NOBOOK'], 'a folder with no manifest: PN_NOBOOK')
    m.put(f'{ROOT_DIR}/Broken/.librivox', b'M1PLUS-LIBRIVOX 1\ni=x\nnonsense\n')
    expect(start(m, 'Broken')[0] == PN['NOBOOK'], 'a malformed manifest: PN_NOBOOK')
    # a part whose path is too long is not fetched
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    txt = manifest(m, d).decode().split('\n')
    txt[4] = '\t'.join(['x' * 122 + '.mp3'] + txt[4].split('\t')[1:])
    long_dir = 'D' * 120
    m.put(f'{ROOT_DIR}/{long_dir}/.librivox', '\n'.join(txt).encode())
    start(m, long_dir)
    expect(result(m, long_dir) == (R_FAILED, PN['STORAGE']) and len(w.reqs) == 0, f'a path over the download limit: PN_STORAGE, not fetched ({result(m, long_dir)})')
    # a part name with characters that need escaping
    w = World([('Chapter 1 & 2 (é).mp3', 'T', 5000)]); m = w.m; d = w.book()
    start(m, d)
    expect(w.reqs and w.reqs[0][0] == f'{HOST}/download/{w.ident}/Chapter%201%20%26%202%20%28%C3%A9%29.mp3' and result(m, d) == (R_DONE, 0), f'the archive name is percent-encoded in the address: {w.reqs}')
    # results per book
    w = World(); m = w.m; d = w.book()
    w.hook = lambda n, s, o: dict(rc=22, code=404)
    start(m, d)
    expect(result(m, d) == (R_FAILED, PN['GONE']), 'book one failed')
    w.ident2 = 'second_librivox'
    w.hook = None
    w.ident = 'second_librivox'
    w.preview(); r, d2 = w.create('Second', 'x')
    start(m, d2)
    expect(result(m, d2) == (R_DONE, 0) and result(m, d) == (R_FAILED, PN['GONE']) and result(m, 'Unknown') == (R_NONE, 0), 'the results are kept per book')
    r, th = start(m, d, run=False)
    expect(result(m, d) == (R_NONE, 0) and result(m, d2) == (R_DONE, 0), 'a new job of a book clears its result while it runs')
    PCN.work(m, th)
    expect(result(m, d) == (R_DONE, 0), 'and it has a new one when it ends')


def reboot_tests(ctx):
    """After a reboot nothing runs and the manifest plus the files are the state."""
    expect = ctx.expect
    w = World(); m = w.m; d = w.book(); root = f'{ROOT_DIR}/{d}'
    hit = []

    def pause_at(name, start_, o):
        if name != w.parts[1][0]: return None
        def x(url, sent, total):
            if sent >= 20000 and not hit: hit.append(1); m.nested(PSYMS['bd_pause'], key_of(d))
        return dict(chunk=10000, ctype='audio/mpeg', code=200, body=w.data[name], length=len(w.data[name]), xfer=x)
    w.hook = pause_at
    start(m, d)
    w2 = World()
    m2 = w2.m
    m2.fs.update(m.fs); m2.dirs.update(m.dirs)
    b = read_book(m2, d)
    expect(b and b['present'] == [1, 0, 0] and b['counts'] == (1, 2, 140000) and view(m2) == dict(active=0, gen=view(m2)['gen'], busy=0) and result(m2, d) == (R_NONE, 0) and not m2.thread, f'a fresh boot: the files and the manifest say 1 of 3, nothing runs ({b and b["counts"]})')
    expect(fn(m2, 'bd_find', m2.cstr(w.ident), m2.alloc(160), 160) == 1, 'the folder is found by its identifier')
    w2.reqs.clear(); w2.data = w.data
    r, th = start(m2, d)
    expect(r == 0 and len(w2.reqs) == 2 and w2.reqs[0][1] == len(m.fs[f'{root}/2 Chapter Two.mp3.part']) and result(m2, d) == (R_DONE, 0), f'asked again, it resumes the .part ({w2.reqs})')


def interplay_tests(ctx):
    """The book download is a thread of its own: it runs beside the job slot (catalog, preview, search, refresh) and the Podcasts episode queue, and nothing gives way."""
    expect = ctx.expect

    def podcast_world():
        w = World(); m = w.m; d = w.book()
        PCN.sub(m, 'Show', 'https://feeds.example/show', title='Show', checked=1)
        m.put(f'{DL.SHOW}/.episodes', DL.eps_text(DL.entries()))
        m.curl_site = lambda url, o: DL.server(DL.DATA)(url, o) if url.startswith('https://cdn.example/') else w.site(url, o)
        return w, m, d

    def add_episode(m):
        m.thread = None
        r = m.call(PSYMS['pn_dl_add'], a0=m.cstr(DL.RP), a1=m.cstr('Show'), a2=m.cstr('a.mp3'), count=1 << 40)
        return r, m.thread
    # a Podcasts episode download starts beside a book download, on its own thread, and is not refused
    w, m, d = podcast_world()
    r, bth = start(m, d, run=False)
    r2, eth = add_episode(m)
    expect(r == 0 and r2 == 0 and bth and eth and bth[0] == PSYMS['bd_main'] and eth[0] == PSYMS['pn_dmain'] and bth != eth and fn(m, 'pn_dl_running') == 1 and fn(m, 'bd_active') == key_of(d),
           'a Podcasts download beside a book download: its own thread starts at once, both are alive, nothing waits')
    expect(fn(m, 'pn_dl_count') == 1 and fn(m, 'bd_active') == key_of(d), 'the book is not in the episode queue: it holds the one episode')
    PCN.work(m, eth)
    expect(m.fs.get(f'{DL.SHOW}/a.mp3') == DL.DATA and fn(m, 'pn_dl_running') == 0 and fn(m, 'bd_active') == key_of(d), 'the episode ends beside the pending book download, which is still active')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0) and read_book(m, d)['counts'] == (3, 0, 0) and fn(m, 'bd_active') == 0, 'then the book ends: both are on the card whole')
    # a refresh starts beside a book download
    w, m, d = podcast_world()
    r, bth = start(m, d, run=False)
    sr, sth = PCN.start(m, ['Show'])
    expect(sr == 0 and sth and sth[0] == PSYMS['pn_main'] and fn(m, 'pn_busy') == 1 and fn(m, 'bd_active') == key_of(d), f'a refresh beside a book download is not refused ({sr})')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0) and fn(m, 'pn_busy') == 1, 'the book ends while the refresh is still pending')
    PCN.work(m, sth)
    expect(fn(m, 'pn_busy') == 0, 'and the refresh ends too')
    # the other direction: an episode download running, a book download starts and is not refused
    w, m, d = podcast_world()
    r2, eth = add_episode(m)
    r, bth = start(m, d, run=False)
    expect(r2 == 0 and eth and r == 0 and bth and bth[0] == PSYMS['bd_main'] and fn(m, 'pn_dl_running') == 1 and fn(m, 'bd_active') == key_of(d), 'the queue\'s thread running: a book download starts beside it')
    PCN.work(m, eth)
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0) and m.fs.get(f'{DL.SHOW}/a.mp3') == DL.DATA, 'both finish')
    # a catalog search and a preview run while a book downloads (two threads alive at once)
    w = World(); m = w.m; d = w.book()
    orig = w.site
    m.curl_site = lambda url, o: BK.catalog_site([])(url, o) if 'advancedsearch' in url else orig(url, o)
    r, bth = start(m, d, run=False)
    m.thread = None
    cr = fn(m, 'bn_catalog', m.cstr(''))
    cth = m.thread
    expect(r == 0 and cr == 0 and cth and cth[0] != PSYMS['bd_main'] and bth and fn(m, 'pn_job_busy') == 1 and fn(m, 'bd_active') == key_of(d) and fn(m, 'pn_busy') == 0,
           'a catalog request while a book downloads: its thread starts in the job slot, the download stays active')
    PCN.work(m, cth)
    expect(fn(m, 'pn_job_busy') == 0 and fn(m, 'bd_active') == key_of(d), 'the catalog job ends beside the pending download')
    m.thread = None
    pr = fn(m, 'bn_preview', m.cstr('test_book_librivox'))
    pth = m.thread
    expect(pr == 0 and pth and pth[0] != PSYMS['bd_main'] and fn(m, 'pn_job_busy') == 1 and fn(m, 'bd_active') == key_of(d), 'a preview while a book downloads: its thread starts too')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0) and fn(m, 'pn_job_busy') == 1, 'the download ends while the preview job is pending: it does not touch the slot')
    PCN.work(m, pth)
    expect(fn(m, 'pn_job_busy') == 0, 'and the preview ends too')
    # the same book again while it runs: nothing is added, no thread, the first goes on
    w = World(); m = w.m; d = w.book()
    r, bth = start(m, d, run=False)
    r2, th2 = start(m, d, run=False)
    expect(r == 0 and r2 == 0 and th2 is None and fn(m, 'bd_active') == key_of(d), 'the same book asked for while it runs: OK, no thread, it stays active')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0), 'the first ends')
    # dropping the held preview beside a download: the download reads its manifest, not the preview
    w = World(); m = w.m; d = w.book()
    r, bth = start(m, d, run=False)
    fn(m, 'bn_preview_drop')
    expect(fn(m, 'bn_preview_count') == 0, 'bn_preview_drop works while the download runs (the job slot is free)')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0) and read_book(m, d)['counts'] == (3, 0, 0), 'the download ends whole')
    # leaving the LibriVox level cancels only the books' kinds (PN_K_BOOKS): never the download, never another page's job
    K_BOOKS = (1 << 11) | (1 << 12)
    w = World(); m = w.m; d = w.book()
    orig = w.site
    m.curl_site = lambda url, o: BK.catalog_site([])(url, o) if 'advancedsearch' in url else orig(url, o)
    r, bth = start(m, d, run=False)
    m.thread = None
    fn(m, 'bn_catalog', m.cstr(''))
    cth = m.thread
    fn(m, 'pn_cancel', K_BOOKS)
    PCN.work(m, cth)
    expect(fn(m, 'bn_catalog_code') == PN['CANCELLED'] and fn(m, 'bd_active') == key_of(d), 'pn_cancel(PN_K_BOOKS) stops a catalog job; the download is not a job and is not touched')
    PCN.work(m, bth)
    expect(result(m, d) == (R_DONE, 0), 'the download ends whole')
    w = World(); m = w.m
    m.curl_site = lambda url, o: {'body': b'{"results":[]}'}
    m.thread = None
    fn(m, 'pn_search', m.cstr('x'))
    sth = m.thread
    fn(m, 'pn_cancel', K_BOOKS)
    PCN.work(m, sth)
    expect(sth and fn(m, 'pn_search_code') != PN['CANCELLED'], 'pn_cancel(PN_K_BOOKS) does not stop a Podcasts search job')


def queue_tests(ctx):
    """The book downloads are a queue: one thread, one transfer at a time, the books in the order they were asked, the thread taking the next by itself (no page tick); pause per book; failures."""
    expect = ctx.expect
    S_NONE, S_RUN, S_WAIT = 0, 1, 2

    def books(w, n):
        ds = []
        for k in range(n):
            w.ident = f'book{k}_librivox'
            w.preview()
            r, d = w.create(f'Book {k}', 'x')
            assert r == 0
            ds.append(d)
        return ds

    def st(m, d): return fn(m, 'bd_state', key_of(d))

    def order(w): return [u.split('/')[-2] for u, s in w.reqs]

    def queued(w, n):
        """n books made, the first started (its thread not run yet), the others asked for."""
        ds = books(w, n)
        r, th = start(w.m, ds[0], run=False)
        assert r == 0 and th
        for d in ds[1:]:
            assert start(w.m, d, run=False)[0] == 0
        return ds, th
    # two and three books run in order, each of its parts, with one call of the thread
    w = World(); m = w.m; A, B, C = books(w, 3)
    r, th = start(m, A, run=False)
    r2, th2 = start(m, B, run=False)
    r3, th3 = start(m, C, run=False)
    expect((r, r2, r3) == (0, 0, 0) and th and th[0] == PSYMS['bd_main'] and th2 is None and th3 is None, f'the first start makes the thread, the next two make none ({r}, {r2}, {r3})')
    expect((st(m, A), st(m, B), st(m, C)) == (S_RUN, S_WAIT, S_WAIT) and view(m)['active'] == key_of(A) and progress(m)[:2] == (0, 3), 'states: the first runs, the others wait; the running one is the active one')
    g0 = view(m)['gen']
    expect(start(m, B, run=False) == (0, None) and start(m, A, run=False) == (0, None) and view(m)['gen'] == g0 and st(m, B) == S_WAIT, 'a book that runs or waits is not added twice: OK, no thread, nothing moves')
    PCN.work(m, th)
    expect(order(w) == ['book0_librivox'] * 3 + ['book1_librivox'] * 3 + ['book2_librivox'] * 3 and all(result(m, d) == (R_DONE, 0) for d in (A, B, C)) and
           view(m)['active'] == 0 and (st(m, A), st(m, B), st(m, C)) == (S_NONE,) * 3 and progress(m) is None and view(m)['busy'] == 0,
           f'one run of the thread fetches the three books in order, no tick starting the next; all DONE, nothing active ({order(w)})')
    expect(all(read_book(m, d)['counts'] == (3, 0, 0) for d in (A, B, C)), 'every book is whole on the card')
    expect(start(m, B, run=False) == (0, None), 'a book that is whole has nothing missing: nothing starts')
    m.fs.pop(f'{ROOT_DIR}/{B}/1 Chapter One.mp3')
    r, th = start(m, B, run=False)
    expect(r == 0 and th and th[0] == PSYMS['bd_main'], 'the thread ended with the queue: the next start makes a new one')
    PCN.work(m, th)
    expect(result(m, B) == (R_DONE, 0), 'and it fetches the missing part')
    # the generation moves with every change of the queue
    w = World(); m = w.m; (A, B), th = queued(w, 2)
    g1 = view(m)['gen']
    fn(m, 'bd_pause', key_of(B))
    expect(view(m)['gen'] > g1, 'bd_gen moves when a book leaves the queue')
    PCN.work(m, th)
    # pause of the running book hands over to the next; its .part stays
    w = World(); m = w.m; A, B, C = books(w, 3)
    hit = []
    orig = w.site

    def pause_a(url, sent, total):
        if 'book0_librivox' in url and sent >= 20000 and not hit:
            hit.append(sent)
            m.nested(PSYMS['bd_pause'], key_of(A))

    def site(url, o):
        r = orig(url, o)
        return dict(r, xfer=pause_a, chunk=10000) if '/download/' in url and 'body' in r else r
    m.curl_site = site
    r, th = start(m, A, run=False)
    start(m, B, run=False); start(m, C, run=False)
    PCN.work(m, th)
    got = len(m.fs.get(f'{ROOT_DIR}/{A}/1 Chapter One.mp3.part', b''))
    expect(result(m, A) == (R_PAUSED, 0) and result(m, B) == (R_DONE, 0) and result(m, C) == (R_DONE, 0) and 0 < got < 70000 and order(w)[0] == 'book0_librivox' and order(w)[1:] == ['book1_librivox'] * 3 + ['book2_librivox'] * 3 and view(m)['active'] == 0,
           f'pausing the running book keeps its .part ({got} bytes) and the thread goes on with the next two ({order(w)})')
    # pause of a waiting book: it leaves the queue as paused and is never fetched
    w = World(); m = w.m; (A, B, C), th = queued(w, 3)
    fn(m, 'bd_pause', key_of(B))
    expect(st(m, B) == S_NONE and result(m, B) == (R_PAUSED, 0) and st(m, A) == S_RUN and st(m, C) == S_WAIT, 'a waiting book that is paused leaves the queue and reads PAUSED; the others stay')
    PCN.work(m, th)
    expect(order(w) == ['book0_librivox'] * 3 + ['book2_librivox'] * 3 and result(m, A) == (R_DONE, 0) and result(m, B) == (R_PAUSED, 0) and result(m, C) == (R_DONE, 0), f'the thread never fetches it ({order(w)})')
    fn(m, 'bd_pause', key_of(A))
    expect(result(m, A) == (R_DONE, 0) and view(m)['active'] == 0, 'a pause of a book that neither runs nor waits changes nothing')
    # pausing the running book and asking for it again before it stopped: it goes behind the others and is fetched whole
    w = World(); m = w.m; (A, B), th = queued(w, 2)
    fn(m, 'bd_pause', key_of(A))
    r, th2 = start(m, A, run=False)
    expect(r == 0 and th2 is None and st(m, A) == S_RUN and st(m, B) == S_WAIT, 'asked again while its pause is pending: queued behind, no second thread')
    PCN.work(m, th)
    expect(order(w) == ['book1_librivox'] * 3 + ['book0_librivox'] * 3 and result(m, A) == (R_DONE, 0) and result(m, B) == (R_DONE, 0), f'the pause ended it with no request; B is fetched, then A whole ({order(w)})')
    # a failure of one book goes on to the next
    w = World(); m = w.m; (A, B, C), th = queued(w, 3)
    orig = w.site
    m.curl_site = lambda url, o: dict(rc=22, code=404) if '/book1_librivox/' in url else orig(url, o)
    PCN.work(m, th)
    expect(result(m, A) == (R_DONE, 0) and result(m, B) == (R_FAILED, PN['GONE']) and result(m, C) == (R_DONE, 0) and view(m)['active'] == 0, f'a part the archive no longer has fails that book only; the queue goes on ({result(m, B)})')
    # a failure every book would meet stops the queue: the rest leave it as paused
    for label, hook, code in (('the link', lambda url, o: dict(rc=28), PN['NET']), ('certificates', lambda url, o: dict(rc=60), PN['CERT'])):
        w = World(); m = w.m; (A, B, C, D), th = queued(w, 4)
        orig = w.site
        m.curl_site = lambda url, o, hook=hook, orig=orig: hook(url, o) if '/book1_librivox/' in url else orig(url, o)
        PCN.work(m, th)
        expect(result(m, A) == (R_DONE, 0) and result(m, B) == (R_FAILED, code) and result(m, C) == (R_PAUSED, 0) and result(m, D) == (R_PAUSED, 0) and
               (st(m, C), st(m, D)) == (S_NONE, S_NONE) and view(m)['active'] == 0 and not [u for u, s in w.reqs if 'book2_librivox' in u or 'book3_librivox' in u],
               f'{label}: the book fails with {code}, the two waiting leave the queue as paused, not as failures, and are not asked for')
    w = World(free_mb=MARGIN_MB + 1); m = w.m
    w.parts[:] = [(f'b_0{i}.mp3', f'T{i}', 1200000) for i in range(3)]
    w.data = {n: bytes(b & 255 for b in body(s)) for n, t, s in w.parts}
    w.files = BK.result(*[obj(n, t, s) for n, t, s in w.parts])
    (A, B), th = queued(w, 2)
    PCN.work(m, th)
    expect(result(m, A) == (R_FAILED, PN['CARDFULL']) and result(m, B) == (R_PAUSED, 0) and not w.reqs, f'a card too full for the first part: the book fails, the other leaves the queue as paused ({result(m, A)}, {result(m, B)})')
    # a path too long for one book is that book's alone
    w = World(); m = w.m; (A, B), th = queued(w, 2)
    txt = manifest(m, A).decode().split('\n')
    txt[4] = '\t'.join(['x' * 122 + '.mp3'] + txt[4].split('\t')[1:])
    long_dir = 'D' * 120
    m.put(f'{ROOT_DIR}/{long_dir}/.librivox', '\n'.join(txt).encode())
    m.fs.pop(f'{ROOT_DIR}/{A}/.librivox', None)
    r = start(m, long_dir, run=False)[0]
    PCN.work(m, th)
    expect(r == 0 and result(m, long_dir) == (R_FAILED, PN['STORAGE']) and result(m, B) == (R_DONE, 0), 'a part path over the download limit fails that book only (the queue goes on)')
    # the queue holds 16 books behind the running one
    w = World(); m = w.m
    parts = [(f'{i} T.mp3', 60, 1000, f'b_0{i + 1}.mp3', 'T') for i in range(2)]
    for k in range(18): m.put(f'{ROOT_DIR}/Q{k}/.librivox', man_text(parts, ident=f'q{k}_librivox', title=f'Q{k}'))
    r, th = start(m, 'Q0', run=False)
    rs = [start(m, f'Q{k}', run=False)[0] for k in range(1, 18)]
    expect(r == 0 and rs[:16] == [0] * 16 and rs[16] == PN['QFULL'] and st(m, 'Q16') == S_WAIT and st(m, 'Q17') == S_NONE, f'sixteen books wait behind the running one; a seventeenth is PN_QFULL ({rs})')
    expect(start(m, 'Q5', run=False)[0] == 0, 'a book that waits already is OK even when the queue is full')
    fn(m, 'bd_pause', key_of('Q3'))
    expect(start(m, 'Q17', run=False)[0] == 0 and st(m, 'Q17') == S_WAIT, 'a place freed by a pause is taken by the next')
    # the guards refuse a book to join the queue as to start it
    w = World(); m = w.m; (A, B), th = queued(w, 2)
    m.wifi = -1
    expect(start(m, B, run=False)[0] == 0, 'a book that waits already is not asked again')
    w2 = World(); m2 = w2.m; (A2, B2), th2 = queued(w2, 2)
    w2.ident = 'book9_librivox'; w2.preview(); r, E = w2.create('Book 9', 'x')
    m2.wifi = -1
    expect(start(m2, E, run=False)[0] == PN['NOWIFI'] and st(m2, E) == S_NONE, 'no Wi-Fi: a new book is refused, not queued')


SECTIONS = [name_tests, create_tests, part_name_tests, manifest_tests, model_tests, job_tests, reboot_tests, interplay_tests, queue_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
