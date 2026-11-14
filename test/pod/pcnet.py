"""Podcast feeds on the network (patch/pcnet.c, docs/modules/podcasts.md "Feeds"): the guards, the import of subscriptions.txt, the refresh worker (one detached thread, one show at a
time) against a scripted libcurl: the request's options (verification never switched off), the files written (atomically; .episodes and .show), the first refresh naming the folder,
every failure (certificate, network, 404, an HTML page, a feed too large, a card that cannot be written) and what the page reads (busy, generation, progress, current feed, status)."""
import os, re
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDS = os.path.join(ROOT, 'test', 'data', 'feeds')
CA, ROOT_DIR, KILL = '/etc/m1plus-cacert.pem', '/mnt/mmc/Podcasts', '/mnt/mmc/m1plus-off'
PN = dict(OK=0, NOWIFI=1, NOCLOCK=2, NOCERT=3, CERT=4, NET=5, GONE=6, HTTP=7, NOTFEED=8, STORAGE=9, MEM=10, BUSY=11)


PCP = sibling('podcasts')


def pc_hash(s): return PCP.pc_hash(s)


class NM(PCP.PM):
    """The card machine plus what the worker calls: directories that exist for access, renamed whole."""
    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('access', 'rmdir', 'rename', 'fopen') and name not in JPEG_MOCKS:
            return super()._hook(u, address, size, _)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        ret = None
        if name == 'access' and self.read_cstr(a0) in self.dirs:
            ret = 0
        elif name == 'rmdir':
            p = self.read_cstr(a0); self.calls.append(('rmdir', p))
            ret = -1 if [q for q in list(self.fs) + list(self.dirs) if q != p and q.startswith(p + '/')] or p not in self.dirs else 0
            if ret == 0: self.dirs.discard(p)
        elif name == 'rename' and self.read_cstr(a0) in self.dirs:
            src, dst = self.read_cstr(a0), self.read_cstr(a1)
            self.calls.append(('rename', src, dst))
            if ('rename', dst) in self.fail: ret = -1
            else:
                for p in sorted(self.dirs):
                    if p == src or p.startswith(src + '/'): self.dirs.discard(p); self.dirs.add(dst + p[len(src):])
                for p in list(self.fs):
                    if p.startswith(src + '/'): self.fs[dst + p[len(src):]] = self.fs.pop(p)
                ret = 0
        elif name == 'fopen' and 'w' in self.read_cstr(a1) and self.read_cstr(a0).startswith((ROOT_DIR, '/mnt/mmc/.m1plus')):   # stdio write: a file on the card dict
            path = self.read_cstr(a0); self.calls.append(('fopen', path, self.read_cstr(a1)))
            if ('fopen', path) in self.fail: ret = 0
            else: self.fs[path] = b''; ret = self.alloc(4); self.fp[ret] = [path, 0]
        elif name in JPEG_MOCKS:
            ret = getattr(self, 'j_' + name)(a0, a1, a2)
            if ret is None: return   # a libjpeg error: the registers are already the setjmp's
        if ret is not None:
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)

    # ---- libjpeg 7 as demo's copy behaves, over PIL: the structures by the offsets of patch/pccover.c (tools/pod.py JPEG_PINS), the error exit as stock's (longjmp to the buffer after the
    # error manager). jfail: the stages that fail ('read_header', 'start', 'read:N' at that row, 'write:N', 'finish'); jlog: what happened, for the tests.
    jd, je, jb, jlog, jfail = None, None, None, None, ()

    def jinit(self):
        if self.jd is None: self.jd, self.je, self.jb, self.jlog, self.jfail = {}, {}, {}, [], set()

    def jerr(self, c, why):
        """libjpeg's error_exit: the one the payload installed must be stock's; then stock's longjmp(err + 0x88, 1) to the _setjmp that is still live."""
        err = self.word(c)
        assert self.word(err) == 0x5dbfe0, 'the payload installs stock\'s error_exit, not libjpeg\'s default (exit)'
        self.jlog.append(('error', why))
        regs = self.jb[err + 0x88]
        for r, v in regs.items(): self.u.reg_write(r, v)
        self.u.reg_write(UC_MIPS_REG_V0, 1); self.u.reg_write(UC_MIPS_REG_PC, regs[UC_MIPS_REG_RA])

    def j_jpeg_std_error(self, a0, a1, a2):
        self.jinit(); self.setword(a0, 0x11111111); self.jlog.append('std_error'); return a0

    def j__setjmp(self, a0, a1, a2):
        self.jinit(); self.jlog.append('setjmp')
        self.jb[a0] = {r: self.u.reg_read(r) for r in [UC_MIPS_REG_0 + i for i in (16, 17, 18, 19, 20, 21, 22, 23, 28, 29, 30, 31)]}
        return 0

    def j_jpeg_CreateDecompress(self, c, ver, size):
        assert (ver, size) == (70, 0x1d8), 'libjpeg 7 and its decompress struct size'
        self.jd[c] = {}; self.jlog.append('create_decompress'); return 0

    def j_jpeg_stdio_src(self, c, fp, _):
        self.jd[c]['path'] = self.fp[fp][0]; return 0

    def j_jpeg_read_header(self, c, req, _):
        from PIL import Image
        import io
        st = self.jd[c]
        if 'read_header' in self.jfail: return self.jerr(c, 'header')
        try:
            im = Image.open(io.BytesIO(self.fs[st['path']])); assert im.format == 'JPEG'; im.load()
        except Exception: return self.jerr(c, 'not a JPEG')
        st['im'] = im; n = {'L': 1, 'RGB': 3, 'CMYK': 4}[im.mode]
        self.setword(c + 0x1c, im.size[0]); self.setword(c + 0x20, im.size[1]); self.setword(c + 0x24, n)
        return 1

    def j_jpeg_start_decompress(self, c, _, __):
        st = self.jd[c]; im = st['im']
        num, den = self.word(c + 0x30), self.word(c + 0x34)
        assert num == 1 and den in (1, 2, 4, 8), f'scale {num}/{den}'
        if 'start' in self.jfail: return self.jerr(c, 'start')
        if den > 1: im = im.reduce(den)   # the DCT scaling: ceil(size / den), as libjpeg's output_width
        st['y'], st['data'], st['row'] = 0, im.tobytes(), im.size[0] * self.word(c + 0x24)
        self.setword(c + 0x70, im.size[0]); self.setword(c + 0x74, im.size[1])
        self.jlog.append(('scale', den, im.size)); return 1

    def j_jpeg_read_scanlines(self, c, rows, n):
        st = self.jd[c]
        if f'read:{st["y"]}' in self.jfail: return self.jerr(c, 'read')
        if (st['y'] + 1) * st['row'] > len(st['data']): return 0
        self.u.mem_write(self.word(rows), st['data'][st['y'] * st['row']:(st['y'] + 1) * st['row']]); st['y'] += 1
        return 1

    def j_jpeg_destroy_decompress(self, c, _, __):
        self.jd.pop(c); self.jlog.append('destroy_decompress'); return 0

    def j_jpeg_CreateCompress(self, c, ver, size):
        assert (ver, size) == (70, 0x1a8), 'libjpeg 7 and its compress struct size'
        self.je[c] = {'rows': []}; self.jlog.append('create_compress'); return 0

    def j_jpeg_stdio_dest(self, c, fp, _):
        self.je[c]['path'] = self.fp[fp][0]; return 0

    def j_jpeg_set_defaults(self, c, _, __):
        assert (self.word(c + 0x24), self.word(c + 0x28)) == (3, 2) and self.word(c + 0x1c) > 0 and self.word(c + 0x20) > 0, 'RGB input of known size'
        return 0

    def j_jpeg_set_quality(self, c, q, force):
        self.je[c]['q'] = q; return 0

    def j_jpeg_start_compress(self, c, _, __):
        self.je[c]['size'] = (self.word(c + 0x1c), self.word(c + 0x20)); return 0

    def j_jpeg_write_scanlines(self, c, rows, n):
        st = self.je[c]
        if f'write:{len(st["rows"])}' in self.jfail: return self.jerr(c, 'write')
        st['rows'].append(bytes(self.u.mem_read(self.word(rows), 3 * st['size'][0]))); return 1

    def j_jpeg_finish_compress(self, c, _, __):
        from PIL import Image
        import io
        st = self.je[c]
        if 'finish' in self.jfail: return self.jerr(c, 'finish')
        assert len(st['rows']) == st['size'][1], 'every row written'
        b = io.BytesIO(); Image.frombytes('RGB', st['size'], b''.join(st['rows'])).save(b, 'JPEG', quality=st['q'])
        self.fs[st['path']] = b.getvalue(); self.jlog.append(('encoded', st['size'], st['q'])); return 0

    def j_jpeg_destroy_compress(self, c, _, __):
        self.je.pop(c); self.jlog.append('destroy_compress'); return 0


JPEG_MOCKS = {'jpeg_std_error', '_setjmp', 'jpeg_CreateDecompress', 'jpeg_stdio_src', 'jpeg_read_header', 'jpeg_start_decompress', 'jpeg_read_scanlines', 'jpeg_destroy_decompress',
              'jpeg_CreateCompress', 'jpeg_stdio_dest', 'jpeg_set_defaults', 'jpeg_set_quality', 'jpeg_start_compress', 'jpeg_write_scanlines', 'jpeg_finish_compress', 'jpeg_destroy_compress'}


def feed_bytes(name): return open(os.path.join(FEEDS, name), 'rb').read()


def machine(site=None, ca=True, **kw):
    m = NM()
    m.dirs.update({ROOT_DIR, '/mnt/mmc/.m1plus'})
    if ca: m.present.add(CA)
    m.curl_site = site or (lambda url, o: {'rc': 6})
    for k, v in kw.items(): setattr(m, k, v)
    return m


def sub(m, folder, feed, title='', checked=0, image='', modified=0):
    m.put(f'{ROOT_DIR}/{folder}/.show', f'M1PLUS-SHOW 1\ntitle={title or folder}\nfeed={feed}\nimage={image}\nchecked={checked}\n'.encode() + (f'modified={modified}\n'.encode() if modified else b''))


def start(m, folders):
    """pn_refresh over the shows pc_scan_shows finds, those named in folders (in that order); returns (result, thread)."""
    shows, arr = m.shows()
    by = {s['dir']: i for i, s in enumerate(shows)}
    idx = m.alloc(4 * len(folders) + 4)
    for k, f in enumerate(folders): m.setword(idx + 4 * k, by[f])
    m.thread = None
    r = m.call(PSYMS['pn_refresh'], a0=m.cstr(ROOT_DIR), a1=arr, a2=idx, a3=len(folders), count=1 << 40)
    return r, m.thread


def work(m, th): m.call(th[0], a0=th[1], count=1 << 40)


def status(m, feed):
    code, fresh = m.alloc(4), m.alloc(4)
    ok = m.call(PSYMS['pn_status'], a0=pc_hash(feed), a1=code, a2=fresh, count=2000000)
    return (m.word(code), m.word(fresh)) if ok else None


def show_of(m, folder):
    shows, _ = m.shows()
    return next((s for s in shows if s['dir'] == folder), None)


def run(ctx):
    expect = ctx.expect
    WSJ = feed_bytes('wsj-3items.xml')
    HEAD = feed_bytes('headlines-3items.xml')
    F_WSJ, F_HEAD = 'https://feeds.example/wsj', 'https://feeds.example/headlines'

    # 1. The guards
    m = machine()
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['OK'], 'card, Wi-Fi, clock and CA bundle: nothing in the way')
    m.card_mounted = False
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['STORAGE'], 'no card: PN_STORAGE')
    m.card_mounted = True; m.wifi = -1
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['NOWIFI'], 'Wi-Fi not connected (get_wifisignal -1): PN_NOWIFI')
    m.wifi = 0
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['NOWIFI'], 'get_wifisignal 0: not connected either')
    m.wifi = 2; m.wall = 1700000000
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['NOCLOCK'], 'a clock before mid 2025 was never set: PN_NOCLOCK (certificates would not verify)')
    m.wall = 1800000000; m.present.discard(CA); m.present.add('/mnt/mmc/.m1plus/cacert.pem')
    expect(m.call(PSYMS['pn_guard'], count=2000000) == PN['NOCERT'], 'no firmware CA bundle: PN_NOCERT (a bundle on the card is not read)')

    # 2. Starting
    m = machine()
    sub(m, 'A', F_WSJ); sub(m, 'B', ''); m.put(f'{ROOT_DIR}/C/c.mp3')
    r, th = start(m, ['A'])
    names = [c[0] for c in m.calls]
    expect(r == 0 and th and th[0] == PSYMS['pn_main'] and ('curl_global_init', 3) in m.calls and names.count('pthread_create') == 1 and names.count('pthread_detach') == 1
           and names.index('curl_global_init') < names.index('pthread_create'), 'a refresh: curl initialised on the UI thread, one detached worker')
    expect(m.call(PSYMS['pn_busy'], count=2000) == 1, 'busy from the start')
    d, t = m.alloc(4), m.alloc(4)
    m.call(PSYMS['pn_progress'], a0=d, a1=t, count=2000)
    expect((m.word(d), m.word(t)) == (0, 1), 'progress 0 of 1')
    g0 = m.call(PSYMS['pn_gen'], count=2000)
    shows, arr = m.shows()
    r2 = m.call(PSYMS['pn_refresh'], a0=m.cstr(ROOT_DIR), a1=arr, a2=m.alloc(4), a3=1, count=1 << 40)
    expect(r2 == PN['BUSY'], 'a second refresh while one runs: PN_BUSY')
    sites = []
    m.curl_site = lambda url, o: (sites.append((url, dict(o))), {'body': WSJ})[1]
    work(m, th)
    expect(m.call(PSYMS['pn_busy'], count=2000) == 0 and m.call(PSYMS['pn_gen'], count=2000) > g0, 'the worker ends: not busy, the generation moved')
    m.call(PSYMS['pn_progress'], a0=d, a1=t, count=2000)
    expect((m.word(d), m.word(t)) == (1, 1), 'progress 1 of 1')
    expect([u for u, _ in sites if u == F_WSJ] == [F_WSJ] and not [u for u, _ in sites if 'feeds.example' in u and u != F_WSJ], 'only the show with a feed was fetched (B has an empty feed, C none)')
    o = sites[0][1]   # the feed's request is the first
    expect(o[10065] == CA and o[52] == 1 and o[68] == 16 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[99] == 1 and o[78] == 20 and o[19] == 1000 and o[20] == 30 and o[13] == 120
           and o[10102] == '' and o[10018].startswith('M1PlusMusic/') and 64 not in o and 81 not in o and 10007 not in o,
           'the request: CAINFO the firmware\'s bundle, redirects (16) limited to http(s), fail on HTTP error, no signals, time-outs, every encoding, a User-Agent, no Range; no SSL_VERIFY option is ever set')
    expect(len([c for c in m.calls if c[0] == 'curl_easy_init']) == 0 and len(m.curl) == 0, 'every easy handle is cleaned up')
    m.calls = []
    r, th = start(m, [])
    expect(r == 0 and th is None and 'pthread_create' not in [c[0] for c in m.calls], 'no show asked: nothing starts, success')
    m = machine(ca=False); sub(m, 'A', F_WSJ)
    r, th = start(m, ['A'])
    expect(r == PN['NOCERT'] and th is None, 'no bundle at all: the refresh does not start (the guard)')
    m = machine(thread_ok=False); sub(m, 'A', F_WSJ)
    r, th = start(m, ['A'])
    calls = list(m.calls)
    expect(r == PN['MEM'] and m.call(PSYMS['pn_busy'], count=2000) == 0 and 'pthread_detach' not in [c[0] for c in calls] and ('free', calls[[c[0] for c in calls].index('calloc')][2]) in calls,
           'a thread that cannot be made: PN_MEM, not busy, the job freed')
    m = machine(); sub(m, 'A', F_WSJ)
    shows, arr = m.shows(); idx = m.alloc(8); m.setword(idx, 0); m.calloc_fail = True
    expect(m.call(PSYMS['pn_refresh'], a0=m.cstr(ROOT_DIR), a1=arr, a2=idx, a3=1, count=1 << 40) == PN['MEM'], 'no memory for the job: PN_MEM')
    m = machine(); sub(m, 'A', F_WSJ); m.wifi = -1
    r, th = start(m, ['A'])
    expect(r == PN['NOWIFI'] and th is None and 'curl_global_init' not in [c[0] for c in m.calls], 'the guards run before anything starts: no Wi-Fi, no thread, no curl')

    # 3. The first refresh: the folder named by the show, the files, the status
    m = machine(site=lambda url, o: {'body': WSJ})
    sub(m, 'feeds.example-1a2b3c4d', F_WSJ, title='feeds.example')
    g0 = m.call(PSYMS['pn_gen'], count=2000)
    r, th = start(m, ['feeds.example-1a2b3c4d'])
    work(m, th)
    calls3 = list(m.calls)
    expect(f'{ROOT_DIR}/feeds.example-1a2b3c4d/.show' not in m.fs and f'{ROOT_DIR}/WSJ Minute Briefing/.show' in m.fs and f'{ROOT_DIR}/WSJ Minute Briefing/.episodes' in m.fs,
           'the first refresh names the folder after the show (the import used the host)')
    s = show_of(m, 'WSJ Minute Briefing')
    expect(s and s['title'] == 'WSJ Minute Briefing' and s['feed'] == F_WSJ and s['image'].startswith('https://image.simplecastcdn.com/images/2c92a2cd') and s['checked'] == 1800000000,
           'the .show file: the feed\'s title, the feed url, the picture url, checked = now; the model reads it')
    expect(s['author'] == 'The Wall Street Journal' and s['category'] == 'News' and s['desc'].startswith('The top business headlines from The Wall Street Journal, three times daily. Whether it’s the latest')
           and 150 < len(s['desc'].encode()) <= 200 and b'\t' not in m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.show'],
           'the .show file also has the channel\'s author, its first category (not the sub-category) and its summary (cut at 200 bytes) as plain text, the model reads them')
    shown_before = m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.show']
    text = m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'].decode()
    lines = [dict(f.split('=', 1) for f in ln.split('\t')) for ln in text.split('\n')[1:] if ln]
    expect(text.startswith('M1PLUS-EPISODES 1\n') and [l['t'] for l in lines] == ['Intensifying Tech Selloff Drags Down Nasdaq', 'Amazon, Intel Earnings Add Fuel to Tech Selloff', 'Alphabet Stock Suffers Worst Day on Record']
           and lines[0]['f'] == '2026-10-30 Intensifying Tech Selloff Drags Down Nasdaq.mp3' and lines[1]['d'] == '93' and lines[1]['l'] == '1574698' and lines[1]['u'].startswith('https://dowjones.simplecastaudio.com/')
           and '&amp;' not in lines[1]['u'] and lines[2]['p'] == '1793307480', 'the .episodes file: three episodes newest first with date, duration, size, a file name and the enclosure url as the feed gives it')
    expect(status(m, F_WSJ) == (PN['OK'], 3) and m.call(PSYMS['pn_gen'], count=2000) > g0 and m.call(PSYMS['pn_current'], count=2000) == 0, 'the status: OK, three new; nothing is being fetched now')
    expect(not [p for p in m.fs if p.endswith('.tmp')], 'no temp file is left')
    eps, _ = m.shows()
    expect(eps[0]['count'] == 0, 'a subscription with nothing downloaded has no episode files (count 0)')
    wr = [c for c in calls3 if c[0] == 'rename']
    expect([c[2].rsplit('/', 1)[1] for c in wr] == ['.notes', '.episodes', '.show', 'WSJ Minute Briefing'], 'both files are written to a temp file and renamed into place, the folder renamed last')
    fsyncs = [c for c in calls3 if c[0] == 'fsync']
    expect(len(fsyncs) == 3, 'each file (.notes, .episodes, .show) is fsynced before its rename')

    # 4. A second refresh: nothing new, nothing renamed, the title kept, the time moved
    before = dict(m.fs)
    m.wall += 3600
    m.curl_site = lambda url, o: {'body': WSJ.replace(b'<title>WSJ Minute Briefing</title>', b'<title>WSJ Renamed Upstream</title>', 1)}
    r, th = start(m, ['WSJ Minute Briefing'])
    work(m, th)
    s = show_of(m, 'WSJ Minute Briefing')
    expect(m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'] == before[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'] and status(m, F_WSJ) == (PN['OK'], 0),
           'the same feed again: the same .episodes, no new episode')
    expect(s['title'] == 'WSJ Minute Briefing' and s['checked'] == 1800003600 and f'{ROOT_DIR}/WSJ Renamed Upstream/.show' not in m.fs, 'the title and the folder are not changed after the first refresh; checked moved')
    # a feed that now gives no author, category, summary or episode description keeps what the files had
    bare = re.sub(rb'<itunes:author>.*?</itunes:author>|<itunes:category[^>]*/>|<itunes:category[^>]*>|</itunes:category>|<itunes:summary>.*?</itunes:summary>|<description>.*?</description>|<content:encoded>.*?</content:encoded>', b'', WSJ, flags=re.S)
    expect(b'itunes:author' not in bare and b'itunes:summary' not in bare and b'<description' not in bare, 'the stripped feed has none of them')
    m.wall += 3600
    m.curl_site = lambda url, o: {'body': bare}
    eps_before = m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes']
    r, th = start(m, ['WSJ Minute Briefing']); work(m, th)
    s2 = show_of(m, 'WSJ Minute Briefing')
    expect((s2['author'], s2['category'], s2['desc']) == (s['author'], s['category'], s['desc']) and s2['checked'] == s['checked'] + 3600 and m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'] == eps_before and shown_before != m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.show'],
           'a refresh whose feed gives an empty author, category and summary keeps the old values in .show (only checked moves) and the old episode descriptions in .episodes')
    # conditional GET: If-Modified-Since is the server's own Last-Modified (modified=, CURLINFO_FILETIME), never the device clock; a 304 is "unchanged", not an error
    LM1, LM2, LM3 = 1799990000, 1799993000, 1799996000
    folder = f'{ROOT_DIR}/WSJ Minute Briefing'
    seen = []
    m.wall += 7200
    m.curl_site = lambda url, o: (seen.append(dict(o)), {'body': WSJ, 'filetime': LM1})[1]
    r, th = start(m, ['WSJ Minute Briefing']); work(m, th)
    s3 = show_of(m, 'WSJ Minute Briefing')
    expect(seen and 33 not in seen[0] and 34 not in seen[0] and seen[0].get(69) == 1, 'no modified= yet: an unconditional request that asks for the file time (CURLOPT_FILETIME)')
    expect(s3['modified'] == LM1 and b'\nmodified=%d\n' % LM1 in m.fs[f'{folder}/.show'], 'a 200 stores the server\'s Last-Modified as modified=')
    eps_before, checked_before = m.fs[f'{folder}/.episodes'], s3['checked']
    seen.clear()
    m.wall += 7200   # the device clock is two hours fast: the condition must not follow it
    m.curl_site = lambda url, o: (seen.append(dict(o)), {'code': 304})[1]
    g0 = m.call(PSYMS['pn_gen'], count=2000)
    r, th = start(m, ['WSJ Minute Briefing']); work(m, th)
    s4 = show_of(m, 'WSJ Minute Briefing')
    expect([o[10002] for o in seen].count(F_WSJ) == 1 and seen[0].get(33) == 1 and seen[0].get(34) == LM1, 'a stored modified=: TIMECONDITION IFMODSINCE with TIMEVALUE = exactly that (no device clock, no margin)')
    expect(m.fs[f'{folder}/.episodes'] == eps_before and not [c for c in m.calls if c[0] == 'rename' and c[2].endswith('/.episodes')] and s4['checked'] == m.wall and s4['checked'] > checked_before and s4['modified'] == LM1
           and (s4['title'], s4['feed'], s4['image'], s4['author'], s4['category'], s4['desc']) == (s2['title'], s2['feed'], s2['image'], s2['author'], s2['category'], s2['desc']),
           'a 304: .episodes untouched, .show kept with checked moved to now and modified= unchanged')
    expect(status(m, F_WSJ) == (PN['OK'], 0) and m.call(PSYMS['pn_gen'], count=2000) > g0 and not [p for p in m.fs if p.endswith('.tmp')], 'a 304 is OK with 0 new (not an error, not an empty feed), no temp file')
    # a server whose content is newer than the stored time answers 200 although the device clock is far ahead; three refreshes in a row each see the update
    server = {'lm': LM2, 'full': 0}

    def live(url, o):
        if url != F_WSJ: return {'body': b'x'}
        seen.append(dict(o))
        if o.get(34) is not None and o[34] >= server['lm']: return {'code': 304}
        server['full'] += 1
        return {'body': WSJ, 'filetime': server['lm']}
    mf = machine(site=live); mf.wall += 7200; sub(mf, 'N', F_WSJ, checked=1799990000, modified=LM1)
    for lm in (LM2, LM3, LM3 + 1000):
        server['lm'] = lm; seen.clear(); full = server['full']; mf.wall += 60
        r, th = start(mf, ['N']); work(mf, th)
        got = re.search(rb'\nmodified=(\d+)\n', mf.fs[f'{ROOT_DIR}/N/.show'])
        expect(server['full'] == full + 1 and got and int(got.group(1)) == lm and (not seen[0] or seen[0].get(34) is None or seen[0][34] < lm), f'the server changed at {lm}: a 200 (not a 304 from a fast device clock), modified= follows')
    seen.clear(); mf.wall += 60
    r, th = start(mf, ['N']); work(mf, th)
    expect(seen[0].get(34) == LM3 + 1000 and server['full'] == full + 1 and status(mf, F_WSJ) == (PN['OK'], 0), 'nothing new since: the same time goes back and the server answers 304')
    # a server that sends no Last-Modified: no condition, and the key is dropped
    mn = machine(site=lambda url, o: (seen.append(dict(o)), {'body': WSJ})[1]); sub(mn, 'N', F_WSJ, checked=1799990000, modified=LM1)
    mn.put(f'{ROOT_DIR}/N/.episodes', b'M1PLUS-EPISODES 1\n'); seen.clear()
    r, th = start(mn, ['N']); work(mn, th)
    expect(seen[0].get(34) == LM1 and b'modified=' not in mn.fs[f'{ROOT_DIR}/N/.show'], 'an answer with no Last-Modified clears modified=')
    seen.clear(); mn.wall += 60
    r, th = start(mn, ['N']); work(mn, th)
    expect(33 not in seen[0] and 34 not in seen[0] and status(mn, F_WSJ) == (PN['OK'], 0), 'then no condition is sent')
    m2 = machine(site=lambda url, o: (seen.append(dict(o)), {'body': WSJ})[1]); sub(m2, 'N', F_WSJ, checked=0); seen.clear()
    r, th = start(m2, ['N']); work(m2, th)
    expect(seen and 33 not in seen[0] and 34 not in seen[0] and status(m2, F_WSJ) == (PN['OK'], 3), 'checked 0: no condition is sent and the feed is read in full')
    m2 = machine(site=lambda url, o: (seen.append(dict(o)), {'body': WSJ})[1]); sub(m2, 'N', F_WSJ, checked=1799990000); seen.clear()
    r, th = start(m2, ['N']); work(m2, th)
    expect(seen and 33 not in seen[0] and status(m2, F_WSJ) == (PN['OK'], 3), 'an old .show with checked= but no modified=: no condition (the device clock is not a validator)')
    # no .episodes (deleted, or an earlier write failed): the request is unconditional and the file comes back
    m2 = machine(site=lambda url, o: (seen.append(dict(o)), {'body': WSJ, 'filetime': LM1})[1]); sub(m2, 'N', F_WSJ, checked=1799990000, modified=LM1); seen.clear()
    r, th = start(m2, ['N']); work(m2, th)
    expect(seen and 33 not in seen[0] and status(m2, F_WSJ) == (PN['OK'], 3) and f'{ROOT_DIR}/N/.episodes' in m2.fs, 'modified= but no .episodes: no condition, the file is written')
    m2.fs.pop(f'{ROOT_DIR}/N/.episodes')
    seen.clear()
    r, th = start(m2, ['N']); work(m2, th)
    expect([o[10002] for o in seen].count(F_WSJ) == 1 and 33 not in seen[0] and f'{ROOT_DIR}/N/.episodes' in m2.fs and status(m2, F_WSJ) == (PN['OK'], 3), '.episodes deleted after a refresh: the next request is unconditional and restores it')
    # a 304 although the cache went missing since the request was built: once more, without the condition
    hits = []

    def racy(url, o):
        if url != F_WSJ: return {'body': b'x'}
        hits.append(dict(o))
        if len(hits) == 1:
            m2.fs.pop(f'{ROOT_DIR}/N/.episodes', None)
            return {'code': 304}
        return {'body': WSJ, 'filetime': LM1}
    m2.curl_site = racy
    r, th = start(m2, ['N']); work(m2, th)
    expect(len(hits) == 2 and hits[0].get(33) == 1 and 33 not in hits[1] and f'{ROOT_DIR}/N/.episodes' in m2.fs and status(m2, F_WSJ) == (PN['OK'], 3), 'a 304 with the cache gone: one unconditional retry, the feed is read in full')
    # a 304 for a show with no cover still fetches it; the cover request carries no condition
    seen.clear()
    m3 = machine(site=lambda url, o: (seen.append(dict(o)), {'code': 304} if url == F_WSJ else {'body': b'x'})[1])
    sub(m3, 'C', F_WSJ, checked=1799990000, image='https://image.simplecastcdn.com/c.jpg', modified=LM1)
    m3.put(f'{ROOT_DIR}/C/.episodes', b'M1PLUS-EPISODES 1\n'); seen.clear()
    r, th = start(m3, ['C']); work(m3, th)
    expect(len(seen) == 2 and seen[0].get(33) == 1 and 33 not in seen[1] and status(m3, F_WSJ) == (PN['OK'], 0), 'a 304 with no cover: the cover is requested, without a condition')
    m.curl_site = lambda url, o: (seen.append(dict(o)), {'body': WSJ})[1]
    # a downloaded file stays the episode's; an entry outside the window with its file is carried
    dl =f'{ROOT_DIR}/WSJ Minute Briefing/' + lines[2]['f']
    m.put(dl, b'audio')
    old = m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'].decode() + 'g=old-guid\tp=5\td=9\tl=7\tf=old file.mp3\tt=Old\tu=https://x/o.mp3\n'
    m.put(f'{ROOT_DIR}/WSJ Minute Briefing/.episodes', old.encode()); m.put(f'{ROOT_DIR}/WSJ Minute Briefing/old file.mp3', b'audio')
    r, th = start(m, ['WSJ Minute Briefing']); work(m, th)
    got = m.fs[f'{ROOT_DIR}/WSJ Minute Briefing/.episodes'].decode()
    expect('old-guid' in got and got.count('\n') == 5 and lines[2]['f'] in got, 'an old entry with its file on the card stays in .episodes when the feed no longer lists it')
    shows, arr = m.shows()
    eps = m.episodes(arr + [s['dir'] for s in shows].index('WSJ Minute Briefing') * O['PC_SHOW_SIZE'])
    expect([(e['title'][:12], e['state']) for e in eps] == [('Intensifying', O['PC_REMOTE']), ('Amazon, Inte', O['PC_REMOTE']), ('Alphabet Sto', O['PC_LOCAL']), ('Old', O['PC_LOCAL'])],
           'the model merges the refreshed file with the files: two episodes remote, the two with files local')

    # 5. Failures, one by one: the old files stay, the status says why
    def one_failure(result, site_result, label, folder='F', feed='https://feeds.example/f'):
        m = machine(site=lambda url, o: site_result)
        sub(m, folder, feed, checked=5); m.put(f'{ROOT_DIR}/{folder}/.episodes', b'M1PLUS-EPISODES 1\ng=keep\tf=k.mp3\tt=Kept\n')
        files = dict(m.fs)
        r, th = start(m, [folder]); work(m, th)
        expect(status(m, feed) == (PN[result], 0) and m.fs == files and not [p for p in m.fs if p.endswith('.tmp')] and m.call(PSYMS['pn_busy'], count=2000) == 0, f'{label}: {result}, the files untouched, no temp file')
    one_failure('CERT', {'rc': 60, 'code': 0}, 'a certificate that does not verify (60)')
    one_failure('CERT', {'rc': 35, 'code': 0}, 'a TLS handshake that fails (35)')
    one_failure('CERT', {'rc': 51, 'code': 0}, 'a host name that does not match (51)')
    one_failure('NOCERT', {'rc': 77, 'code': 0}, 'a CA file libcurl cannot read (77)')
    one_failure('NET', {'rc': 6, 'code': 0}, 'a host that does not resolve (6)')
    one_failure('NET', {'rc': 28, 'code': 0}, 'a time-out (28)')
    one_failure('NET', {'rc': 56, 'code': 0}, 'a connection that drops (56)')
    one_failure('GONE', {'rc': 22, 'code': 404}, 'HTTP 404')
    one_failure('GONE', {'rc': 22, 'code': 410}, 'HTTP 410')
    one_failure('HTTP', {'rc': 22, 'code': 503}, 'HTTP 503')
    one_failure('NOTFEED', {'body': b'<html><body>Sign in</body></html>'}, 'an HTML page with 200')
    one_failure('NOTFEED', {'body': b'{"error": "no"}'}, 'JSON')
    one_failure('NOTFEED', {'body': b''}, 'an empty answer')
    one_failure('NOTFEED', {'body': b'<rss><channel><title>X</title>' + b'<!-- ' + b'x' * (9 << 20) + b' -->', 'chunk': 65536}, 'a feed over 8 MiB with no item before the cap (the write callback stops the transfer)')
    # a feed over 8 MiB whose newest items come first (TED Talks Daily, 8.5 MB): parsed up to the cap, the items kept, a success
    big = WSJ.replace(b'</channel>', b'<item><title>Cut by the cap</title><enclosure url="https://x/cut.mp3" type="audio/mpeg" length="9"/><!-- ' + b'x' * (9 << 20) + b' --></item></channel>')
    m = machine(site=lambda url, o: {'body': big, 'chunk': 65536})
    sub(m, 'S', F_WSJ, checked=5)
    r, th = start(m, ['S']); work(m, th)
    got = m.fs.get(f'{ROOT_DIR}/S/.episodes', b'').decode()
    expect(status(m, F_WSJ)[0] == PN['OK'] and got.count('\n') == 4 and 'Cut by the cap' not in got,
           'a feed over 8 MiB with its items first: PN_OK, the items parsed before the cap kept, the item cut by the cap left out')
    # writes that fail
    for what in ('.episodes', '.show'):
        m = machine(site=lambda url, o: {'body': WSJ})
        sub(m, 'S', F_WSJ, title='Fixed', checked=5)
        m.fail.add(('rename', f'{ROOT_DIR}/S/{what}'))
        r, th = start(m, ['S']); work(m, th)
        expect(status(m, F_WSJ) == (PN['STORAGE'], 0) and not [p for p in m.fs if p.endswith('.tmp')] and (what == '.show' or f'{ROOT_DIR}/S/.episodes' not in m.fs),
               f'{what} that cannot be renamed into place: PN_STORAGE, the temp file removed')
    m = machine(site=lambda url, o: {'body': WSJ}); sub(m, 'S', F_WSJ, checked=5); m.fail.add(('open', f'{ROOT_DIR}/S/.episodes.tmp'))
    r, th = start(m, ['S']); work(m, th)
    expect(status(m, F_WSJ) == (PN['STORAGE'], 0), 'a temp file that cannot be opened: PN_STORAGE')

    # 6. Refresh All: one show failing does not stop the others; the progress, the current feed
    cur = []
    def site_all(url, o):
        if url.startswith('https://feeds.example/'): cur.append((url, m.word(PSYMS['pn'] + 16)))   # pn.cur (a nested call would clobber the emulated call in progress)
        return {'body': WSJ} if 'wsj' in url else {'body': HEAD} if 'headlines' in url else {'rc': 28}
    m = machine(site=site_all)
    sub(m, 'one', F_WSJ); sub(m, 'two', 'https://feeds.example/dead'); sub(m, 'three', F_HEAD)
    r, th = start(m, ['one', 'two', 'three'])
    d, t = m.alloc(4), m.alloc(4)
    m.call(PSYMS['pn_progress'], a0=d, a1=t, count=2000)
    expect(r == 0 and (m.word(d), m.word(t)) == (0, 3), 'Refresh All: 0 of 3')
    work(m, th)
    m.call(PSYMS['pn_progress'], a0=d, a1=t, count=2000)
    expect([u for u, _ in cur] == [F_WSJ, 'https://feeds.example/dead', F_HEAD] and all(c == pc_hash(u) for u, c in cur), 'the shows are fetched in order, pn_current the feed being fetched')
    expect(status(m, F_WSJ) == (PN['OK'], 3) and status(m, 'https://feeds.example/dead') == (PN['NET'], 0) and status(m, F_HEAD) == (PN['OK'], 3) and (m.word(d), m.word(t)) == (3, 3),
           'one show timing out does not stop the next: OK, NET, OK; progress 3 of 3')
    titles = {s['title'] for s in m.shows()[0]}
    expect('The Headlines' in titles and 'WSJ Minute Briefing' in titles and 'two' in titles, 'the other feeds were written and named too; the failed one keeps its folder and title')
    expect(status(m, 'https://nothing.example/') is None and m.call(PSYMS['pn_current'], count=2000) == 0, 'a feed never fetched has no status; none is being fetched')
    # a rename that would overwrite another folder is not done
    m = machine(site=lambda url, o: {'body': WSJ}); sub(m, 'imp', F_WSJ, title='imp'); m.folder(f'{ROOT_DIR}/WSJ Minute Briefing')
    r, th = start(m, ['imp']); work(m, th)
    expect(f'{ROOT_DIR}/imp/.show' in m.fs and show_of(m, 'imp')['title'] == 'WSJ Minute Briefing', 'a folder of that name already there: the show keeps its import folder, its title is still the show\'s')

    # 7. Import
    def imp(text, shows_fn=None, folders=()):
        m = machine()
        for f, feed in folders: sub(m, f, feed)
        if text is not None: m.put(f'{ROOT_DIR}/subscriptions.txt', text.encode())
        shows, arr = m.shows()
        n = m.call(PSYMS['pn_import'], a0=m.cstr(ROOT_DIR), a1=arr, a2=len(shows), count=1 << 40)
        n = n - (1 << 32) if n >= 1 << 31 else n
        return m, n
    m, n = imp(None)
    expect(n == -1, 'no subscriptions.txt: -1')
    text = ('# my shows\n\n  https://a.example/rss  \nhttp://b.example:8080/feed.xml?x=1&y=2\r\nftp://nope.example/x\nnot a url\nhttps://has space.example/x\nhttps://a.example/rss\n'
            'https://c.example/' + 'p' * 400 + '\nhttps://d.example\nhttps://e.example/another\thttps://tab\n')
    m, n = imp(text)
    shows, _ = m.shows()
    feeds = sorted(s['feed'] for s in shows)
    expect(n == 3 and feeds == ['http://b.example:8080/feed.xml?x=1&y=2', 'https://a.example/rss', 'https://d.example'],
           f'three urls imported: comments, blanks, a non-http scheme, text, a space, a duplicate, an over-long url (400 bytes) and a tab-joined line are not: {feeds}')
    a = next(s for s in shows if s['feed'] == 'https://a.example/rss')
    expect(a['title'] == 'a.example' and a['dir'] == 'a.example-%08x' % pc_hash('https://a.example/rss') and a['checked'] == 0 and a['count'] == 0,
           'each gets a folder "<host>-<hash>" and a .show file with the host as its title and checked 0')
    b = next(s for s in shows if 'b.example' in s['feed'])
    expect(b['dir'] == 'b.example-%08x' % pc_hash(b['feed']) and b['title'] == 'b.example', 'the host without its port')
    n2 = m.call(PSYMS['pn_import'], a0=m.cstr(ROOT_DIR), a1=m.shows()[1], a2=3, count=1 << 40)
    expect(n2 == 0, 'importing the same file again adds nothing')
    m, n = imp('https://a.example/rss\nhttps://new.example/x\n', folders=[('Existing', 'https://a.example/rss')])
    expect(n == 1 and sorted(s['feed'] for s in m.shows()[0]) == ['https://a.example/rss', 'https://new.example/x'], 'a feed an existing show already has is not added again')
    m, n = imp(''.join(f'https://s{i}.example/rss\n' for i in range(O['PC_MAX_SHOWS'] + 20)))
    expect(n == O['PC_MAX_SHOWS'] and len(m.shows()[0]) == O['PC_MAX_SHOWS'], 'at most PC_MAX_SHOWS shows: the rest of a long list is left')
    m, n = imp('https://a.example/rss\n', folders=[(f'f{i}', f'https://f{i}.example/') for i in range(39)])
    expect(n == 1, 'room for exactly one more')
    m, n = imp('https://a.example/rss\n')
    expect(not [p for p in m.fs if p.endswith('.tmp')], 'no temp file left by the import')
    m = machine(); m.put(f'{ROOT_DIR}/subscriptions.txt', b'https://a.example/rss\n')
    m.fail.add(('open', f'{ROOT_DIR}/a.example-{pc_hash("https://a.example/rss"):08x}/.show.tmp'))
    shows, arr = m.shows()
    expect(m.call(PSYMS['pn_import'], a0=m.cstr(ROOT_DIR), a1=arr, a2=0, count=1 << 40) == 0, 'a show file that cannot be written: that url is not counted')

    # 8. The cover picture (docs/modules/podcasts.md "Cover art"): downloaded after the feed, shrunk once to PV_SIZE, renamed into place
    import io
    from PIL import Image

    def picture(w, h, mode='RGB', fmt='JPEG', **kw):
        im = Image.new(mode, (w, h))
        px = im.load()
        for x in range(w):   # left half red, right half blue (gray: dark, light): the shrink must keep the picture, not only its size
            c = (220, 30, 30) if x < w // 2 else (30, 30, 220)
            for y in range(0, h, max(1, h // 64)):
                for yy in range(y, min(h, y + max(1, h // 64))): px[x, yy] = c if mode == 'RGB' else (40 if x < w // 2 else 215) if mode == 'L' else (0, 0, 0, 0)
        b = io.BytesIO(); im.save(b, fmt, **kw)
        return b.getvalue()

    IMG = 'https://image.simplecastcdn.com/'
    FOLDER = f'{ROOT_DIR}/WSJ Minute Briefing'

    def cover_run(pic, folder_files=(), jfail=(), feed=WSJ, image_status=None):
        """A first refresh of the WSJ feed whose picture answers pic (bytes) or the scripted status; returns (m, requests, files of the folder)."""
        reqs = []
        def site(url, o):
            reqs.append((url, dict(o)))
            if url == F_WSJ: return {'body': feed}
            if image_status: return image_status
            return {'body': pic}
        m = machine(site=site)
        m.jinit(); m.jfail = set(jfail)
        sub(m, 'feeds.example-1a2b3c4d', F_WSJ, title='feeds.example')
        for f, data in folder_files: m.put(f'{ROOT_DIR}/feeds.example-1a2b3c4d/{f}', data)
        r, th = start(m, ['feeds.example-1a2b3c4d'])
        g0 = m.call(PSYMS['pn_gen'], count=2000)
        work(m, th)
        files = sorted(p.rsplit('/', 1)[1] for p in m.fs if p.startswith(FOLDER + '/'))
        m.g_moved = m.call(PSYMS['pn_gen'], count=2000) > g0
        return m, reqs, files

    def decoded(m, name='cover.jpg'):
        im = Image.open(io.BytesIO(m.fs[f'{FOLDER}/{name}'])); im.load()
        return im

    big = picture(3000, 3000)
    m, reqs, files = cover_run(big)
    cv = decoded(m)
    expect(cv.format == 'JPEG' and cv.size == (192, 192) and files == ['.episodes', '.notes', '.show', 'cover.jpg'], f'a 3000 x 3000 cover becomes a 192 x 192 JPEG named cover.jpg, in the renamed folder; no temp file left: {files} {cv.size}')
    expect(cv.getpixel((10, 96))[0] > 180 and cv.getpixel((10, 96))[2] < 80 and cv.getpixel((180, 96))[2] > 180 and cv.getpixel((180, 96))[0] < 80, 'the picture is kept (red left, blue right)')
    expect(('scale', 8, (375, 375)) in m.jlog and ('encoded', (192, 192), 85) in m.jlog and m.jlog.count('std_error') == 1 and m.jlog[-2:] == ['destroy_decompress', 'destroy_compress'],
           'libjpeg decodes at 1/8 (375 x 375 of 3000), the encoder writes 192 x 192 at quality 85, both destroyed')
    expect(status(m, F_WSJ) == (PN['OK'], 3) and m.g_moved, 'the status is the feed\'s: OK, three new')
    img_reqs = [(u, o) for u, o in reqs if u != F_WSJ]
    expect(len(img_reqs) == 1 and img_reqs[0][0].startswith(IMG), 'the picture url the feed named is requested once')
    o = img_reqs[0][1]
    expect(o[10065] == CA and o[52] == 1 and o[68] == 16 and o[181] == 3 and o[182] == 3 and o[45] == 1 and o[99] == 1 and o[78] == 20 and o[19] == 1000 and o[20] == 30 and o[13] == 120 and 64 not in o and 81 not in o,
           'the same request options as the feed: CA bundle, redirects limited to http(s), fail on HTTP error, time-outs; no SSL_VERIFY option')
    s = show_of(m, 'WSJ Minute Briefing')
    expect(s['cover'] == 'cover.jpg' and m.call(PSYMS['pc_cover_ok'], a0=m.cstr(f'{FOLDER}/cover.jpg'), count=2000000) == 1, 'the model finds the cover and the page would decode it (header check)')
    expect(not m.fs.get(f'{FOLDER}/.cover.src') and not [c for c in m.calls if c[0] == 'rename' and c[1].endswith('.cover.src')], 'the download is removed after the shrink')

    # a second refresh does not fetch the picture again
    reqs.clear(); m.curl_site = lambda url, o: (reqs.append(url), {'body': WSJ})[1]; m.wall += 60
    r, th = start(m, ['WSJ Minute Briefing']); work(m, th)
    expect(reqs == [F_WSJ], 'a folder with a cover: only the feed is requested')

    m, reqs, files = cover_run(picture(3000, 2000))
    expect(decoded(m).size == (192, 128), 'not square: fitted inside 192 x 192, the aspect kept (3000 x 2000 -> 192 x 128)')
    m, reqs, files = cover_run(picture(100, 80))
    expect(decoded(m).size == (100, 80) and ('scale', 1, (100, 80)) in m.jlog, 'a small picture is not upscaled (100 x 80 stays), decoded at 1/1')
    m, reqs, files = cover_run(picture(1000, 1000, 'L'))
    expect(decoded(m).size == (192, 192) and ('scale', 4, (250, 250)) in m.jlog and decoded(m).getpixel((10, 96))[0] < 90 and decoded(m).getpixel((180, 96))[0] > 170,
           'a gray JPEG becomes colour (192 x 192), decoded at 1/4 (1/8 would fall under 192 px)')
    m, reqs, files = cover_run(picture(1400, 1400, progressive=True))
    expect(decoded(m).size == (192, 192) and ('scale', 4, (350, 350)) in m.jlog, 'a progressive JPEG within the size cap is shrunk too (1400 x 1400, 1/4)')
    m, reqs, files = cover_run(picture(3000, 3000, progressive=True))
    expect(files == ['.episodes', '.notes', '.show'] and not [e for e in m.jlog if e == 'create_decompress'] and status(m, F_WSJ) == (PN['OK'], 3),
           'a progressive JPEG above 2.1 million pixels is refused before libjpeg sees it (it would hold all its coefficients): no cover, the status untouched')
    m, reqs, files = cover_run(picture(4100, 4100, optimize=True))
    expect(files == ['.episodes', '.notes', '.show'] and 'create_decompress' not in m.jlog, 'a baseline JPEG above 16 million pixels is refused')

    # a cover the user put there wins; every spelling the page knows
    for name in ('cover.jpg', 'cover.png', 'cover.jpeg', 'folder.jpg', 'folder.png', 'folder.jpeg'):
        m, reqs, files = cover_run(big, folder_files=[(name, b'mine')])
        expect(not [u for u, _ in reqs if u != F_WSJ] and m.fs.get(f'{FOLDER}/{name}') == b'mine' and sorted(files) == sorted(['.episodes', '.notes', '.show', name]), f'a {name} in the folder: no download, the file untouched')

    # failures: nothing left, the feed's status untouched
    def no_cover(m, files, label):
        expect(files == ['.episodes', '.notes', '.show'] and status(m, F_WSJ) == (PN['OK'], 3) and m.call(PSYMS['pn_busy'], count=2000) == 0 and len(m.curl) == 0, f'{label}: no cover and no leftover file, the feed\'s status OK with three new')
    m, reqs, files = cover_run(b'', image_status={'rc': 22, 'code': 404}); no_cover(m, files, 'HTTP 404 for the picture')
    m, reqs, files = cover_run(b'', image_status={'rc': 60, 'code': 0}); no_cover(m, files, 'a certificate error on the picture')
    m, reqs, files = cover_run(b'', image_status={'rc': 28, 'code': 0, 'body': big[:50000]}); no_cover(m, files, 'a time-out half way through the picture')
    m, reqs, files = cover_run(b'<html>not a picture</html>'); no_cover(m, files, 'an HTML page with 200')
    m, reqs, files = cover_run(b''); no_cover(m, files, 'an empty answer')
    m, reqs, files = cover_run(b'GIF89a' + bytes(100)); no_cover(m, files, 'a GIF')
    m, reqs, files = cover_run(big[:20000]); no_cover(m, files, 'a truncated JPEG (libjpeg\'s error exit longjmps back)')
    expect(('error', 'read') in m.jlog or ('error', 'not a JPEG') in m.jlog, 'the truncated JPEG ended in libjpeg\'s error exit')
    m, reqs, files = cover_run(b'\xff\xd8' + big[2:700] + bytes(5000)); no_cover(m, files, 'a JPEG whose data is garbage')
    m, reqs, files = cover_run(picture(500, 500, 'CMYK')); no_cover(m, files, 'a CMYK JPEG')
    m, reqs, files = cover_run(b'x' * (6 * 1048576 + 1)); no_cover(m, files, 'a download over 6 MiB (the write callback stops it)')
    for stage in ('read_header', 'start', 'read:100', 'write:50', 'finish'):
        m, reqs, files = cover_run(big, jfail=[stage])
        no_cover(m, files, f'libjpeg failing at {stage}')
        expect(m.jlog.count('destroy_decompress') == m.jlog.count('create_decompress') and m.jlog.count('destroy_compress') == m.jlog.count('create_compress') and ('error', stage.split(':')[0].replace('read_header', 'header')) in m.jlog,
               f'{stage}: libjpeg\'s error exit returned through stock\'s longjmp to our setjmp, and every libjpeg object was destroyed')
    m = machine(site=lambda url, o: {'body': WSJ if url == F_WSJ else big})
    sub(m, 'feeds.example-1a2b3c4d', F_WSJ, title='feeds.example'); m.fail.add(('fopen', f'{FOLDER}/.cover.tmp'))
    r, th = start(m, ['feeds.example-1a2b3c4d']); work(m, th)
    files = sorted(p.rsplit('/', 1)[1] for p in m.fs if p.startswith(FOLDER + '/'))
    no_cover(m, files, 'a temp file that cannot be opened')
    m = machine(site=lambda url, o: {'body': WSJ if url == F_WSJ else big})
    sub(m, 'feeds.example-1a2b3c4d', F_WSJ, title='feeds.example'); m.fail.add(('rename', f'{ROOT_DIR}/WSJ Minute Briefing/cover.jpg'))
    r, th = start(m, ['feeds.example-1a2b3c4d']); work(m, th)
    files = sorted(p.rsplit('/', 1)[1] for p in m.fs if p.startswith(FOLDER + '/'))
    no_cover(m, files, 'a rename into place that fails')
    m = machine(site=lambda url, o: {'body': WSJ if url == F_WSJ else big})
    sub(m, 'feeds.example-1a2b3c4d', F_WSJ, title='feeds.example'); m.fail.add(('open', f'{FOLDER}/.cover.src'))
    r, th = start(m, ['feeds.example-1a2b3c4d']); work(m, th)
    expect(not [p for p in m.fs if 'cover' in p] and status(m, F_WSJ) == (PN['OK'], 3), 'a download file that cannot be opened: no cover, the status untouched')

    # PNG: kept as it is when the page can decode it, else refused
    m, reqs, files = cover_run(picture(600, 600, fmt='PNG'))
    expect(files == ['.episodes', '.notes', '.show', 'cover.jpg'] and decoded(m).size == (192, 192) and 'create_decompress' not in m.jlog and show_of(m, 'WSJ Minute Briefing')['cover'] == 'cover.jpg',
           'a PNG becomes the same 192 x 192 cover.jpg (the streaming decoder of pcpng.c; the details are in pcpng.py)')
    m, reqs, files = cover_run(picture(100, 100, fmt='PNG')[:60]); no_cover(m, files, 'a truncated PNG')
    PT = sibling('pcpng')   # (Pillow cannot write an interlaced PNG: the header's flag is set by hand)
    inter = PT.png(200, 200, 2, 8, bytes(601) * 200, interlace=1)
    m, reqs, files = cover_run(inter)
    expect(files == ['.episodes', '.notes', '.show', 'cover.png'] and m.fs[f'{FOLDER}/cover.png'] == inter, 'an interlaced PNG small enough for the page is kept as cover.png (it cannot be shrunk in one pass)')
    m, reqs, files = cover_run(PT.png(3000, 3000, 2, 8, bytes(9001) * 3000, interlace=1)); no_cover(m, files, 'a large interlaced PNG')

    # no picture url, or one that is not http(s): nothing is requested
    for url in ('', 'ftp://x.example/a.jpg', 'file:///etc/passwd', 'javascript:1'):
        reqs = []
        m = machine(site=lambda u, o: (reqs.append(u), {'body': WSJ.replace(b'https://image.simplecastcdn.com', url.encode()) if u == F_WSJ else big})[1])
        sub(m, 'S', F_WSJ, title='S', image=''); r, th = start(m, ['S']); work(m, th)
        expect(len(reqs) == 1 and status(m, F_WSJ) == (PN['OK'], 3), f'a picture url of {url!r}: not requested')

    # the url the show file already has is used when the feed names none
    reqs = []
    m = machine(site=lambda u, o: (reqs.append(u), {'body': re.sub(rb'<itunes:image[^>]*>|<image>.*?</image>', b'', WSJ, flags=re.S) if u == F_WSJ else big})[1])
    sub(m, 'S', F_WSJ, title='S', image=IMG + 'old.jpg', checked=5); r, th = start(m, ['S']); work(m, th)
    expect(reqs == [F_WSJ, IMG + 'old.jpg'] and f'{ROOT_DIR}/S/cover.jpg' in m.fs, 'a feed with no picture: the url already in .show is used')
