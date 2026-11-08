"""Internet Radio (patch/radio.c, patch/radiopage.c, patch/radionp.c, docs/modules/radio.md): the parsers (playlist, CSV stations, countries and genres, the escape, the caption), the pure
state table (every cell, the single restart, the Wi-Fi rule), the start through stock's hciplayer (the DAC readied, the resume position, the URL, the refusals), the tick that reconciles with
stock's status (connecting, playing, pause, stall, end, time-out, socket change, Bluetooth), stop from every state and the hand-over hook, the keep-awake calls, the directory fetch (guards,
options, answers), the card files (favourites written atomically, recent stations) and the pages (asset, rows, taps, the sheet, Now Playing). The compiled payload runs under Unicorn;
hciplayer, the network and the DAC are not run: stock's calls are mocks that set the same flags stock does."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

PCP = sibling('podcasts')
PCN = sibling('pcnet')   # the podcast network machine: the card, libcurl and libjpeg mocks the logo worker runs on
KB = sibling('keyboard')
CA, RADIO_DIR = '/etc/m1plus-cacert.pem', '/mnt/mmc/Radio'
FAVS, RECENT = RADIO_DIR + '/favourites.m3u', '/mnt/data/m1plus/radio-recent'
PLAYSPEED = pod.DATA['PLAYSPEED_MODE'][0]
DACOFF, G_OUT, G_VOL = pod.DATA['DACOFF_TIME'][0], pod.DATA['G_HEADSET_OUTPUT'][0], pod.DATA['G_VOLUME'][0]
RESUME, RUNNING, SOCK = pod.DATA['RESUME_POS'][0], pod.DATA['HCI_RUNNING'][0], pod.DATA['HCI_SOCK_FD'][0]
ST = dict(IDLE=0, CONNECTING=1, PLAYING=2, ERROR=3, STOPPED=4, PAUSED=5)
E = dict(OK=0, WIFI=1, CLOCK=2, BUSY=3, FAIL=4, EMPTY=5, PODBUSY=6)
MAXL = 301   # RD_MAX + 1 rows of each offset table


class RM(PCN.NM):
    """The card machine plus what the radio calls: the string functions, the process calls (fork, execl, kill, waitpid, setsid, dup2), the stock player and DAC calls."""
    def __init__(self):
        super().__init__()
        self.start_ret = 1          # mcl_tidalStartPlayer
        self._ps, self._hs, self._run = 1, 0, 0   # mclGetPlayStatus (1 stopped, 2 playing, 3 paused), mclGetHciplayerStatus, the running byte
        self.out_way = 0            # mclGetOutputWay
        self.proc = []              # ('start', url) and ('mclStop',) in order
        self.speeds = []            # mclSetPlaySpeed's arguments in order (not in proc or calls: they stay what the tests below compare)
        self.wifi = 3
        self.wall = 1_800_000_000
        self.status = 1             # nothing plays
        self.present.add(CA)
        self.fs['/dev/null'] = b''
        self.dirs.update({'/mnt', '/mnt/mmc', RADIO_DIR, '/mnt/data', '/mnt/data/m1plus'})
        self.setword(G_OUT, 0); self.setword(DACOFF, 0); self.setword(G_VOL, 17); self.setword(SOCK, 7)

    # the stock flags live in demo's data: the engine reads the memory, the mocks of stock's calls write it
    ps = property(lambda self: self._ps, lambda self, v: setattr(self, '_ps', v))
    hs = property(lambda self: self._hs, lambda self, v: setattr(self, '_hs', v))
    run = property(lambda self: self.u.mem_read(RUNNING, 1)[0], lambda self, v: self.u.mem_write(RUNNING, bytes([v])))

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'strlen': ret = len(self.read_cstr(a0).encode('latin-1'))
        elif name == 'strstr':
            h, n = self.read_cstr(a0), self.read_cstr(a1); i = h.find(n); ret = a0 + i if i >= 0 else 0
        elif name == 'strchr':
            h = self.read_cstr(a0); i = h.find(chr(a1 & 0xff)) if a1 & 0xff else len(h); ret = a0 + i if i >= 0 else 0
        elif name == 'strrchr':
            h = self.read_cstr(a0); i = h.rfind(chr(a1 & 0xff)) if a1 & 0xff else len(h); ret = a0 + i if i >= 0 else 0
        elif name == 'strncasecmp':
            x, y = self.read_cstr(a0)[:a2].lower(), self.read_cstr(a1)[:a2].lower(); ret = (x > y) - (x < y)
        elif name == 'mcl_tidalStartPlayer':   # (stock: sends set-songurl, sets the running byte and the status to playing)
            url = self.read_cstr(a0); self.proc.append(('start', url)); self.calls.append(('mcl_tidalStartPlayer', url, self.word(RESUME)))
            ret = self.start_ret
            if ret == 1: self.run, self.ps = 1, 2
        elif name == 'mclStop':
            self.proc.append(('mclStop',)); self.calls.append(('mclStop',)); ret = 0xffffffff if not self.run else 0
            self.run, self.ps, self.hs = 0, 1, 0
        elif name == 'mclSetPlaySpeed': self.speeds.append(a0); ret = 1
        elif name == 'mclGetPlayStatus': ret = self.ps
        elif name == 'mclGetHciplayerStatus': ret = self.hs
        elif name == 'stop_player': self.calls.append(('stop_player',)); ret = 0
        elif name == 'set_outputchannel': self.calls.append(('set_outputchannel', a0, a1, a2)); ret = 1
        elif name == 'mclSetPcmMode': self.calls.append(('mclSetPcmMode',)); ret = 1
        elif name == 'mclSetMute': self.calls.append(('mclSetMute', a0)); ret = 1
        elif name == 'set_devicevolume': self.calls.append(('set_devicevolume', a0)); ret = 1
        elif name == 'mclSetDacPwr': self.calls.append(('mclSetDacPwr', a0)); ret = 1
        elif name == 'mclGetOutputWay': ret = self.out_way
        elif name == 'access' and self.read_cstr(a0) in self.dirs: ret = 0
        elif name == 'access' and self.read_cstr(a0) in self.fs: ret = 0
        elif name == 'stock_start_player_trampoline': ret = 1
        elif name == 'stock_save_stop_trampoline': self.calls.append(('stock_save_stop',)); ret = 0
        elif name == 'stock_save_start_trampoline': self.calls.append(('stock_save_start', a0)); ret = 0
        elif name in ('mclSetPause', 'mclSetResume'):   # (stock: {mcl-pause} / {mcl-resume} to hciplayer, then the status 3 / 2)
            self.calls.append((name,)); self.proc.append((name,)); self.ps = 3 if name == 'mclSetPause' else 2; ret = 1
        elif name == 'open' and a1 & 0x100 and self.read_cstr(a0).startswith(RADIO_DIR + '/') and self.read_cstr(a0).rsplit('/', 1)[0] not in self.dirs:   # creating a file beneath a folder that is not there
            self.calls.append(('open', self.read_cstr(a0), a1)); ret = 0xffffffff
        elif name == 'mkdir' and self.read_cstr(a0).startswith(RADIO_DIR) and self.read_cstr(a0).rsplit('/', 1)[0] not in self.dirs:   # mkdir without its parent
            self.calls.append(('mkdir', self.read_cstr(a0))); ret = 0xffffffff
        elif name == 'fopen' and 'w' in self.read_cstr(a1) and self.read_cstr(a0).startswith(RADIO_DIR):   # stdio write on the card dict (the logo's .tmp)
            path = self.read_cstr(a0); self.calls.append(('fopen', path, self.read_cstr(a1)))
            if ('fopen', path) in self.fail or path.rsplit('/', 1)[0] not in self.dirs: ret = 0
            else: self.fs[path] = b''; ret = self.alloc(4); self.fp[ret] = [path, 0]
        elif name == 'close' and a0 not in self.fds: self.calls.append(('close', a0)); ret = 0   # the child closes every descriptor from 3 up
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    # ---- helpers
    def put_text(self, path, text): self.put(path, text.encode('utf-8') if isinstance(text, str) else text)

    def buf(self, data):
        b = data if isinstance(data, bytes) else data.encode('utf-8')
        a = self.malloc(len(b) + 8); self.u.mem_write(a, b + b'\0' * 8); return a

    def tables(self, n=MAXL, three=True):
        return [self.malloc(4 * n) for _ in range(3 if three else 2)]

    def offs(self, base, n): return list(struct.unpack(f'<{n}I', bytes(self.u.mem_read(base, 4 * n))))


def stack(m, *words):
    """The stack arguments of the next call (o32: the fifth argument and on are at sp + 16)."""
    m.u.mem_write(STACK + 16, struct.pack(f'<{len(words)}I', *words))


def machine():
    m = RM()
    for sym in ('stock_start_player_trampoline', 'stock_save_stop_trampoline', 'stock_save_start_trampoline'):
        m.handlers[PSYMS[sym]] = sym
    return m


def strings(m, buf, names, urls, infos=None, n=None):
    """[(name, url, info)] of the first n rows of the offset tables."""
    n = len(names) if n is None else n
    return [(m.read_cstr(buf + names[i]), m.read_cstr(buf + urls[i]), m.read_cstr(buf + infos[i]) if infos and infos[i] else '') for i in range(n)]


def playlist(m, text, max=MAXL):
    b = m.buf(text); nm, ur, inf = m.tables()
    n = m.call(PSYMS['rd_playlist'], a0=b, a1=nm, a2=ur, a3=inf, count=4000000)   # (max is the fifth argument: on the stack)
    return strings(m, b, m.offs(nm, n), m.offs(ur, n), m.offs(inf, n), n)


def parsers_tests(ctx):
    """1. The playlist, the CSVs, the escape, the ffmpeg lines, the caption."""
    expect = ctx.expect
    m = machine()
    stack(m, MAXL)   # rd_playlist's fifth argument, max, is on the stack
    got = playlist(m, '#EXTM3U\n#EXTINF:-1,Radio Paradise\nhttp://stream.radioparadise.com/mp3-128\n#EXTINF:-1,SomaFM Groove Salad\nhttp://ice1.somafm.com/groovesalad-128-mp3\n')
    expect(got == [('Radio Paradise', 'http://stream.radioparadise.com/mp3-128', ''), ('SomaFM Groove Salad', 'http://ice1.somafm.com/groovesalad-128-mp3', '')], f'an .m3u: #EXTINF names the next address ({got})')
    got = playlist(m, b'\xef\xbb\xbf' + '#EXTM3U\r\n#EXTINF:1,Name, with comma\r\n#RADIOBROWSERUUID:abc\r\nhttps://a.example/s\r\n\r\nhttp://nameless.example/x\r\n'.encode())   # real BOM bytes
    expect(got == [('Name, with comma', 'https://a.example/s', ''), ('http://nameless.example/x', 'http://nameless.example/x', '')],
           f'CRLF, a BOM, radio-browser\'s extra comment lines, a comma in the name, an address with no name is its own name ({got})')
    got = playlist(m, '[playlist]\nTitle2=Second\nFile1=http://one.example/a\nFile2=http://two.example/b\nTitle1=First\nNumberOfEntries=2\nVersion=2\n')
    expect(got == [('First', 'http://one.example/a', ''), ('Second', 'http://two.example/b', '')], f'a .pls: FileN= is the address, TitleN= names the FileN of the same N whatever their order ({got})')
    got = playlist(m, '#EXTM3U\n#M1+:Germany\tMP3\t128\n#EXTINF:-1,Station\nhttp://x.example/s\n#EXTINF:-1,Next\nhttp://y.example/s\nnot a station\nftp.example/none\n')
    expect(got == [('Station', 'http://x.example/s', 'Germany\tMP3\t128'), ('Next', 'http://y.example/s', '')], f'#M1+: is the next station\'s info, a line without :// is no station ({got})')
    big = '#EXTM3U\n' + ''.join(f'#EXTINF:-1,S{i}\nhttp://h.example/{i}\n' for i in range(300))
    stack(m, 5)
    got = playlist(m, big)
    expect(len(got) == 5 and got[4][0] == 'S4', 'at most max stations are taken')
    stack(m, MAXL)
    expect(playlist(m, '') == [] and playlist(m, '\n\n#EXTM3U\n') == [], 'empty text, a header only: no station')
    # ---- the CSV of stations
    header = 'changeuuid,stationuuid,serveruuid,name,url,url_resolved,homepage,favicon,tags,country,countrycode,iso_3166_2,state,language,languagecodes,votes,lastchangetime,lastchangetime_iso8601,codec,bitrate,hls'
    def row(name, url, res, country, codec, rate, tags='"a,b"', fav='http://fav'):
        q = lambda s: '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n') else s
        return f'u1,u2,,{q(name)},{url},{res},http://home,{fav},{tags},{q(country)},DE,DE-RP,,english,,5,2026,2026,{codec},{rate},0'
    csv = '\n'.join([header, row('MANGORADIO', 'http://a.example/x.m3u', 'https://a.example/stream', 'Germany', 'MP3', '128'),
                     row('Quoted, "Name"', 'http://b.example/s', '', 'The United States Of America', 'AAC+', '64'),
                     row('', 'http://c.example/s', '', 'X', 'MP3', '1'),
                     row('No address', '', '', 'Y', 'MP3', '1'),
                     row('Line\nbreak', 'ftp://d.example', '', 'Z', 'MP3', '1'),
                     'short,row', row('Last', 'http://e.example/s', 'http://e.example/r', '', '', '0')]) + '\n'
    src = m.buf(csv); pool_size = len(csv) + 600; pool = m.malloc(pool_size); nm, ur, inf = m.tables()
    stack(m, nm, ur, inf, MAXL)   # o32: a0 src, a1 len, a2 pool, a3 size; the tables and max follow on the stack
    n = m.call(PSYMS['rd_stations'], a0=src, a1=len(csv), a2=pool, a3=pool_size, count=40000000)
    got = strings(m, pool, m.offs(nm, n), m.offs(ur, n), m.offs(inf, n), n)
    expect([g[0] for g in got] == ['MANGORADIO', 'Quoted, "Name"', 'Line break', 'Last'] and got[0][1] == 'https://a.example/stream' and got[1][1] == 'http://b.example/s' and got[3][1] == 'http://e.example/r'
           and got[1][2] == 'The United States Of America\tAAC+\t64\thttp://fav' and got[3][2] == '\t\t0\thttp://fav' and got[0][2] == 'Germany\tMP3\t128\thttp://fav', f'the four stations kept, in order, a line feed inside a quoted name read as it is ({got})')
    # ---- countries and genres
    ccsv = 'name,iso_3166_1,stationcount\nThe United States Of America,US,7804\n"Korea, Republic Of",KR,100\n,XX,5\nGermany,DE,6329\n'
    b = m.buf(ccsv); nm, ky, ct = m.tables()
    stack(m, MAXL, 1)
    n = m.call(PSYMS['rd_choices'], a0=b, a1=nm, a2=ky, a3=ct, count=4000000)
    got = [(m.read_cstr(b + o), m.read_cstr(b + k), m.read_cstr(b + c)) for o, k, c in zip(m.offs(nm, n), m.offs(ky, n), m.offs(ct, n))]
    expect(got == [('The United States Of America', 'US', '7804'), ('Korea, Republic Of', 'KR', '100'), ('Germany', 'DE', '6329')], f'countries: name, code, count; a quoted name keeps its comma, a nameless row is skipped ({got})')
    tcsv = 'name,stationcount\npop,6202\n"drum, bass",12\nrock,3158\n'
    b = m.buf(tcsv); nm, ky, ct = m.tables()
    stack(m, MAXL, 0)
    n = m.call(PSYMS['rd_choices'], a0=b, a1=nm, a2=ky, a3=ct, count=4000000)
    got = [(m.read_cstr(b + o), m.read_cstr(b + k), m.read_cstr(b + c)) for o, k, c in zip(m.offs(nm, n), m.offs(ky, n), m.offs(ct, n))]
    expect(got == [('pop', 'pop', '6202'), ('drum, bass', 'drum, bass', '12'), ('rock', 'rock', '3158')], f'genres: the name is the key ({got})')
    # ---- the escape, the caption
    out = m.malloc(64)
    for text, want in (('abc-_.~XYZ019', 'abc-_.~XYZ019'), ('a b/c', 'a%20b%2Fc'), ('Café', 'Caf%C3%A9'), ('r&b?x=1', 'r%26b%3Fx%3D1'), ('', '')):
        m.call(PSYMS['rd_url_escape'], a0=m.buf(text), a1=out, a2=64, count=100000)
        expect(m.read_cstr(out) == want, f'the escape of {text!r}: {want}')
    m.call(PSYMS['rd_url_escape'], a0=m.buf('é' * 40), a1=out, a2=16, count=100000)
    expect(len(m.read_cstr(out)) <= 15 and len(m.read_cstr(out)) % 3 == 0, 'a long text is cut at a whole escape inside the buffer')
    cap = m.malloc(128)
    for info, want in (('Germany\tMP3\t128', 'Germany · MP3 128k'), ('\tMP3\t0', 'MP3'), ('Germany\t\t', 'Germany'), ('', ''), ('\t\t0', ''), ('France\tAAC+\t64', 'France · AAC+ 64k')):
        m.call(PSYMS['rd_caption'], a0=m.buf(info), a1=cap, a2=128, count=100000)
        expect(m.read_cstr(cap).encode('latin-1').decode('utf-8') == want, f'the caption of {info!r}: {want!r} (got {m.read_cstr(cap)!r})')


LIST_SIZE = 16 + 3 * MAXL * 4


def new_list(m, text=None, kind=0):
    l = m.malloc(LIST_SIZE); m.u.mem_write(l, bytes(LIST_SIZE))
    if text is not None:
        b = m.buf(text); m.call(PSYMS['rd_list_set'], a0=l, a1=b, a2=len(text.encode('utf-8')), a3=kind, count=40000000)
    return l


STATIONS = '#EXTM3U\n#M1+:Germany\tMP3\t128\n#EXTINF:-1,One\nhttp://one.example/a\n#EXTINF:-1,Two\nhttps://two.example/b\n#EXTINF:-1,Three\nhttp://three.example/c\n'


def play(m, text=STATIONS, i=0):
    l = new_list(m, text)
    m.calls = []; m.proc = []
    r = m.call(PSYMS['rd_play'], a0=l, a1=i, count=40000000)
    m.after = list(m.calls)   # (every m.call clears m.calls)
    return l, r


def state(m): return m.call(PSYMS['rd_state'], count=2000000)
def poll(m):
    """One rd_poll; the calls it made (m.call clears m.calls, so a later m.call would lose them)."""
    m.call(PSYMS['rd_poll'], count=40000000)
    return list(m.calls)
def cstr_of(m, name): return m.read_cstr(m.call(PSYMS[name], count=100000))


def step(m, state, ev, tries=0, wifi=1):
    """rd_step: (next state, actions, why)."""
    r = m.call(PSYMS['rd_step'], a0=state, a1=ev, a2=tries, a3=wifi, count=200000)
    return r & 255, r >> 8 & 255, r >> 16


# the actions
STOP, START, RETRY, PAUSE = 1, 2, 4, 8
# the state table of docs/modules/radio.md, written out: event -> one (next, actions, why) per state IDLE CONNECTING PLAYING ERROR STOPPED PAUSED (None = no change, no action)
sI, sC, sP, sE, sS, sA = ST['IDLE'], ST['CONNECTING'], ST['PLAYING'], ST['ERROR'], ST['STOPPED'], ST['PAUSED']
TABLE = {
    'PLAY':      [(sC, START, 0), (sC, STOP | START, 0), (sC, STOP | START, 0), (sC, START, 0), (sC, START, 0), (sC, STOP | START, 0)],
    'BAD':       [(sE, 0, 1), (sE, STOP, 1), (sE, STOP, 1), (sE, 0, 1), (sE, 0, 1), (sE, STOP, 1)],
    'BT':        [(sE, 0, 2), (sE, STOP, 2), (sE, STOP, 2), (sE, 0, 2), (sE, 0, 2), (sE, STOP, 2)],
    'FAILSTART': [(sE, STOP, 3)] * 6,
    'STOP':      [None, (sS, STOP, 0), (sS, STOP, 0), (sS, 0, 0), None, (sS, STOP, 0)],
    'LOCAL':     [None, (sS, STOP, 0), (sS, STOP, 0), None, None, (sS, STOP, 0)],
    'REROUTE':   [None, (sC, STOP | START, 0), (sC, STOP | START, 0), None, None, (sA, STOP | START | PAUSE, 0)],
    'REROUTE_PAUSED': [None, (sA, STOP | START | PAUSE, 0), (sA, STOP | START | PAUSE, 0), None, None, (sA, STOP | START | PAUSE, 0)],
    'HEAR':      [None, (sP, 0, 0), None, None, None, (sP, 0, 0)],
    'PAUSE':     [None, (sA, 0, 0), (sA, 0, 0), None, None, None],
    'RESUME':    [None, None, None, None, None, (sP, 0, 0)],
    'ENDED':     [None, (sC, RETRY, 5), (sE, STOP, 4), None, None, (sE, STOP, 4)],
    'STALL':     [None, None, (sC, STOP | START, 6), None, None, None],
    'TIMEOUT':   [None, (sE, STOP, 7), None, None, None, None],
    'NOWIFI':    [(sE, 0, 8), (sE, STOP, 8), (sE, STOP, 8), (sE, 0, 8), (sE, 0, 8), (sE, STOP, 8)],
}
EV = {name: k for k, name in enumerate(TABLE)}   # (the order of the enum in radio.h)
WHY = ['', 'Unsupported address', 'Bluetooth is not supported', 'Could not start', 'Playback ended', 'Could not connect', 'Stream stalled', 'No response', 'No Wi-Fi', 'Player not ready']


def table_tests(ctx):
    """2. The pure step: every cell of the state table, the single restart and the Wi-Fi rule."""
    expect = ctx.expect
    m = machine()
    bad = []
    for name, row in TABLE.items():
        for st, cell in enumerate(row):
            want = cell or (st, 0, 0)
            got = step(m, st, EV[name])
            if got != want: bad.append((name, st, got, want))
    expect(not bad, f'all 84 + 6 cells of the state table ({bad[:3]})')
    expect(step(m, sC, EV['ENDED'], tries=1) == (sE, STOP, 5) and step(m, sP, EV['STALL'], tries=1) == (sE, STOP, 6),
           'a second early end or stall is the error state (one restart per play), with a stop')
    expect(step(m, sC, EV['ENDED'], wifi=0) == (sE, STOP, 8) and step(m, sP, EV['STALL'], wifi=0) == (sE, STOP, 8) and step(m, sC, EV['TIMEOUT'], wifi=0) == (sE, STOP, 8)
           and step(m, sP, EV['ENDED'], wifi=0) == (sE, STOP, 8), 'with Wi-Fi gone an end, a stall or a time-out says "No Wi-Fi" and restarts nothing')
    expect(step(m, sC, EV['BAD'], wifi=0) == (sE, STOP, 1), 'a refused address keeps its own words whatever the Wi-Fi does')
    expect(step(m, 9, 0) == (9, 0, 0) and step(m, sI, 99) == (sI, 0, 0), 'an unknown state or event changes nothing')
    for st in (sI, sC, sP, sE, sS, sA):
        expect(step(m, st, EV['STOP'])[0] == (sI if st == sI else sS) and step(m, step(m, st, EV['STOP'])[0], EV['STOP'])[0] in (sS, sI), f'Stop from state {st} reaches Stopped (idle stays idle), twice is the same')
        expect(step(m, st, EV['PLAY'])[0] == sC and step(m, st, EV['PLAY'])[1] & START, f'a play tap in state {st} starts a connection')
    # no state is a dead end: from every state there is a Play and a Stop
    expect(all(TABLE['PLAY'][st][0] == sC for st in range(6)), 'every state can start a station')


def up(m, text=STATIONS, i=0):
    """A station started and heard: PLAYING."""
    l, r = play(m, text, i)
    m.clock += 2000; m.hs = 1
    poll(m)
    return l, r


def starts(m): return [c[1] for c in m.proc if c[0] == 'start']
def stops(m): return sum(c[0] == 'mclStop' for c in m.proc)
def error(m): return cstr_of(m, 'rd_error')


def play_tests(ctx):
    """3. Starting: the recipe's order, the refusals, a station switch."""
    expect = ctx.expect
    m = machine()
    l, r = play(m)
    expect(r == 1 and state(m) == ST['CONNECTING'], f'a station starts: connecting ({r}, {state(m)})')
    order = [c[:2] if c[0] != 'mcl_tidalStartPlayer' else c for c in m.after if c[0] in ('stop_player', 'set_outputchannel', 'mclSetPcmMode', 'mclSetMute', 'set_devicevolume', 'mcl_tidalStartPlayer', 'timer_add', 'mclStop')]
    expect(order == [('stop_player',), ('set_outputchannel', 0), ('mclSetPcmMode',), ('mclSetMute', 0), ('set_devicevolume', 17), ('mcl_tidalStartPlayer', 'http://one.example/a', 0), ('mclSetMute', 0), ('timer_add', PSYMS['rd_tick'])],
           f"stock's stop_player, the DAC readied (output, PCM mode, unmute, volume), the resume position 0 at the call, the URL, then unmuted again, then the one timer ({order})")
    expect(m.fs.get(RECENT, b'').startswith(b'#EXTM3U\n#EXTINF:-1,One\n') and b'#M1+:Germany\tMP3\t128\n' in m.fs[RECENT] and m.fs[RECENT].count(b'EXTINF') == 1,
           'the recent file has the station first (with its info)')
    expect(m.call(PSYMS['rd_at']) == 0 and m.call(PSYMS['rd_running']) == 1, 'running, on the first station')
    # ---- refusals
    m = machine()
    for url in ('file:///etc/passwd', 'ftp://x.example/s', 'rtsp://x.example/s', 'concat:a|b://x', 'http://x.example/a|b', 'http://x.example/a}b'):
        l, r = play(m, f'#EXTINF:-1,Bad\n{url}\n')
        expect(r == 0 and state(m) == ST['ERROR'] and error(m) == 'Unsupported address' and not m.proc and 'stop_player' not in [c[0] for c in m.after], f'{url}: only plain http(s) addresses without "|" or "}}" play, nothing is started')
    m = machine(); m.out_way = 1
    l, r = play(m)
    expect(r == 0 and state(m) == ST['ERROR'] and 'Bluetooth' in error(m) and not m.proc and 'stop_player' not in [c[0] for c in m.after], "Bluetooth output: no radio, stock's player untouched")
    m = machine(); m.out_way = 2; m.setword(G_OUT, 3)
    l, r = play(m)
    names = [c[0] for c in m.after]
    expect(r == 1 and starts(m) == ['http://one.example/a'] and 'set_outputchannel' in names
           and not [n for n in names if n in ('mclSetPcmMode', 'mclSetDacPwr', 'set_devicevolume')],
           "a USB DAC: it starts after set_outputchannel (as stock's start_player), the built-in DAC's readying is skipped")
    m = machine()
    l, r = play(m, '')
    expect(r == 0 and not m.proc, 'an empty list plays nothing')
    m = machine()
    l, r = play(m, STATIONS, 7)
    expect(r == 0 and not m.proc, 'a station out of range plays nothing')
    # ---- the start fails
    m = machine(); m.setword(SOCK, 0xffffffff)
    l, r = play(m)
    expect(r == 0 and state(m) == ST['ERROR'] and error(m) == 'Player not ready' and not starts(m) and not [c for c in m.after if c[0] == 'timer_add'], 'hciplayer has no socket: nothing is sent, "Player not ready", no timer')
    m = machine(); m.start_ret = 0xffffffff
    l, r = play(m)
    expect(r == 0 and state(m) == ST['ERROR'] and error(m) == 'Could not start' and stops(m) == 1 and not [c for c in m.after if c[0] == 'timer_add'], 'mcl_tidalStartPlayer refuses: "Could not start", stopped, no timer')
    expect(b'One' not in m.fs.get(RECENT, b''), 'a start that failed is not put in the recent stations')
    # ---- a station while one plays: stopped first, started once, one timer
    m = machine()
    up(m)
    l2, r = play(m, STATIONS, 1)
    adds = [c for c in m.after if c[0] == 'timer_add']
    expect(m.proc == [('mclStop',), ('start', 'https://two.example/b')] and 'stop_player' not in [c[0] for c in m.after] and m.call(PSYMS['rd_at']) == 1 and len(adds) == 1 and state(m) == ST['CONNECTING'],
           f'the next station: mclStop, then the new URL, one timer ({m.proc})')
    l3, r = play(m, STATIONS, 2)
    expect(m.proc == [('mclStop',), ('start', 'http://three.example/c')] and state(m) == ST['CONNECTING'], 'a switch while still connecting stops and starts again')
    l4, r = play(m, STATIONS, 2)
    expect(m.proc == [('mclStop',), ('start', 'http://three.example/c')] and state(m) == ST['CONNECTING'], 'a double tap on the same station is a clean restart')
    l5, r = play(m, '#EXTINF:-1,Bad\nhttp://x.example/a|b\n')
    expect(r == 0 and m.proc == [('mclStop',)] and state(m) == ST['ERROR'], 'a refused station while one plays stops it and shows the error (no half-started stream)')
    l6, r = play(m, STATIONS, 0)
    expect(r == 1 and state(m) == ST['CONNECTING'] and starts(m) == ['http://one.example/a'], 'and the error state starts the next one')


def poll_tests(ctx):
    """4. The tick: stock's status decides, every state has an exit."""
    expect = ctx.expect
    m = machine()
    l, r = play(m)
    m.hs = 1; m.clock += 1000
    poll(m)
    expect(state(m) == ST['CONNECTING'], "stock's flags are not read in the first 1.5 s")
    m.run = 0; m.ps = 1; m.hs = 0
    poll(m)
    expect(state(m) == ST['CONNECTING'] and not stops(m), 'and an end inside the grace is not read either')
    m = machine()
    l, r = play(m)
    m.setword(DACOFF, 12); m.clock += 2000; m.hs = 1
    calls = poll(m)
    expect(state(m) == ST['PLAYING'], 'hciplayer says playing: Playing')
    expect(('reset_poweroptions_timer', 1, 1, 0) in calls and m.word(DACOFF) == 0, "every poll holds standby and auto power-off (not the screen) and zeroes the DAC's idle counter")
    m.setword(DACOFF, 0xffffffff); m.clock += 500
    poll(m)
    expect(m.s32(DACOFF) == -1, 'a DAC stock powered off (-1) is left for the next start to power on')
    expect(m.call(PSYMS['rd_tick'], a0=0, count=40000000) == 8, 'the timer repeats while a station plays')
    for k in range(40):   # a long healthy stream
        m.clock += 500; poll(m)
    expect(state(m) == ST['PLAYING'] and not stops(m), 'a stream that keeps playing stays playing')
    # ---- connecting: 20 s bound
    m = machine()
    l, r = play(m)
    m.clock += 19999; poll(m)
    expect(state(m) == ST['CONNECTING'], '19.999 s without a "playing": still connecting')
    m.clock += 1; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No response' and stops(m) == 1 and m.call(PSYMS['rd_tick'], a0=0, count=40000000) == 0, '20 s: "No response", hciplayer stopped, the timer ends')
    m.clock += 1000000; calls = poll(m)
    expect(('reset_poweroptions_timer', 1, 1, 0) not in calls and stops(m) == 1, 'an error state touches nothing')
    # ---- connecting: stock reports an error (no dns resolver): one restart after 1 s, then the error
    m = machine()
    l, r = play(m)
    m.clock += 2000; m.run = 0; m.ps = 1
    poll(m)
    expect(state(m) == ST['CONNECTING'] and starts(m) == ['http://one.example/a'] and not stops(m), 'an early end: still connecting, nothing restarted yet')
    m.clock += 999; poll(m)
    expect(len(starts(m)) == 1, '999 ms later: still waiting')
    m.clock += 1; poll(m)
    expect(starts(m) == ['http://one.example/a'] * 2 and state(m) == ST['CONNECTING'], 'after 1 s the same station is started again, once')
    m.clock += 2000; m.run = 0; m.ps = 1
    poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'Could not connect' and m.call(PSYMS['rd_tick'], a0=0, count=40000000) == 0, 'a second early end: "Could not connect"')
    m = machine()
    l, r = play(m)
    m.wifi = -1   # (the connection is lost after the start: Wi-Fi down at the start itself is the Nowifi event, no attempt)
    m.clock += 2000; m.run = 0; m.ps = 1
    poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and len(starts(m)) == 1, 'an early end with Wi-Fi off: "No Wi-Fi", no restart')
    # the play button of the error retries
    m.wifi = 3
    l, r = play(m)
    expect(r == 1 and state(m) == ST['CONNECTING'] and len(starts(m)) == 1, 'and Play from the error state starts again')
    # ---- playing: a stall restarts once
    m = machine()
    up(m)
    m.hs = 0; m.clock += 9999; poll(m)
    expect(state(m) == ST['PLAYING'], '9.999 s without "playing": still playing')
    m.clock += 1; poll(m)
    expect(state(m) == ST['CONNECTING'] and m.proc[-2:] == [('mclStop',), ('start', 'http://one.example/a')], f'10 s: stopped and started once more ({m.proc})')
    m.clock += 2000; m.hs = 1; poll(m)
    expect(state(m) == ST['PLAYING'], 'and playing again')
    m.hs = 0; m.clock += 10000; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'Stream stalled' and stops(m) == 2, 'a second stall inside the minute: "Stream stalled", stopped')
    m = machine()
    up(m)
    m.hs = 0; m.clock += 10000; poll(m)
    m.clock += 2000; m.hs = 1; poll(m)
    for k in range(125): m.clock += 500; poll(m)
    m.hs = 0; m.clock += 10000; poll(m)
    expect(state(m) == ST['CONNECTING'] and len(starts(m)) == 3, 'a stream that held for a minute earns another restart')
    m = machine(); up(m)
    m.wifi = -1; m.hs = 0; m.clock += 10000; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and len(starts(m)) == 1, 'a stall with Wi-Fi off: "No Wi-Fi", no restart')
    # ---- playing: stock stopped it, hciplayer ended or was restarted
    m = machine(); up(m)
    m.run = 0; m.ps = 1; m.hs = 0; m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'Playback ended' and m.call(PSYMS['rd_running']) == 0, 'the running byte gone (hciplayer exited, or stock stopped it): "Playback ended", not "Playing"')
    m = machine(); up(m)
    m.setword(SOCK, 9); m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'Playback ended', "demo's socket to hciplayer changed (hciplayer restarted): the stream is gone")
    m = machine(); up(m)
    m.setword(SOCK, 0xffffffff); m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'], 'no socket: ended')
    m = machine(); up(m)
    m.ps = 1; m.clock += 500; poll(m)
    expect(state(m) == ST['PLAYING'], "stock's status says stopped but hciplayer still plays: the audio wins, nothing is stopped")
    m.hs = 0; m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'], 'stopped and not playing: ended')
    # ---- pause (stock's key sets the status to 3): no stall, no time-out, resume
    m = machine(); up(m)
    m.ps = 3; m.hs = 0; m.clock += 500; poll(m)
    expect(state(m) == ST['PAUSED'] and m.call(PSYMS['rd_running']) == 1, 'stock paused: Paused, still the radio')
    m.clock += 600000; poll(m)
    expect(state(m) == ST['PAUSED'] and not stops(m), 'a pause has no time limit')
    m.ps = 2; m.hs = 1; m.clock += 500; poll(m)
    expect(state(m) == ST['PLAYING'], 'resumed: Playing')
    m.ps = 3; m.hs = 0; m.clock += 500; poll(m)
    m.run = 0; m.ps = 1; m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'], 'paused, then stock stopped: not stuck on Paused')
    # ---- the output switches to Bluetooth mid-stream
    m = machine(); up(m)
    m.out_way = 1; m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'] and 'Bluetooth' in error(m) and stops(m) == 1, 'Bluetooth took the output: stopped, said so')


def stop_tests(ctx):
    """5. Stop from every state, the hand-over hook, the timer."""
    expect = ctx.expect
    for label, setup in (('connecting', lambda m: play(m)), ('playing', lambda m: up(m)),
                         ('paused', lambda m: (up(m), setattr(m, 'ps', 3), setattr(m, 'clock', m.clock + 500), poll(m)))):
        m = machine(); setup(m)
        m.proc = []; m.calls = []
        m.call(PSYMS['rd_stop'], count=4000000)
        calls = list(m.calls)
        expect(m.proc == [('mclStop',)] and state(m) == ST['STOPPED'] and ('timer_remove', 0x777) in calls and m.call(PSYMS['rd_running']) == 0, f'stop while {label}: mclStop, Stopped, the timer removed ({m.proc})')
        m.proc = []; m.call(PSYMS['rd_stop'], count=4000000)
        expect(not m.proc and state(m) == ST['STOPPED'], 'a second stop does nothing')
    m = machine(); up(m)
    m.run = 0; m.ps = 1; m.proc = []                      # stock stopped it already
    m.call(PSYMS['rd_stop'], count=4000000)
    expect(m.proc == [('mclStop',)] and state(m) == ST['STOPPED'], 'stop after stock stopped it: mclStop anyway (returns at once), Stopped')
    m = machine()
    m.call(PSYMS['rd_stop'], count=4000000)
    expect(state(m) == ST['IDLE'] and not m.proc, 'stop with nothing started touches nothing')
    m = machine(); play(m, '#EXTINF:-1,Bad\nftp://x/a\n')
    m.proc = []; m.call(PSYMS['rd_stop'], count=4000000)
    expect(state(m) == ST['STOPPED'] and not m.proc, 'stop in the error state clears it, stock untouched')
    # ---- the hand-over hook
    m = machine(); up(m)
    m.proc = []
    rv = m.call(PSYMS['rd_start_player'], count=40000000)
    expect(rv == 1 and m.proc == [('mclStop',)] and state(m) == ST['STOPPED'], f"mclStartPlayer's hook: a playing radio is stopped (mclStop, so stock's next call is set-songurl, not set-nexturl), then stock runs ({m.proc}, result {rv})")
    expect(m.call(PSYMS['rd_tick'], a0=0, count=40000000) == 0, "the engine's timer sees the stop and ends itself (the hook may run off the UI thread: no timer call there)")
    for label, setup in (('connecting', lambda m: play(m)), ('paused', lambda m: (up(m), setattr(m, 'ps', 3), setattr(m, 'clock', m.clock + 500), poll(m)))):
        m = machine(); setup(m); m.proc = []
        m.call(PSYMS['rd_start_player'], count=40000000)
        expect(m.proc == [('mclStop',)] and state(m) == ST['STOPPED'], f'a local track chosen while {label} wins')
    m = machine(); m.proc = []; m.calls = []
    rv = m.call(PSYMS['rd_start_player'], count=4000000)
    expect(rv == 1 and not m.proc and not [c for c in m.calls if not c[0].startswith(('access', 'fopen', 'open', 'write', 'fsync', 'close', 'rename', 'mkdir', 'unlink'))], "with no radio (every boot, Memory Playback included) the hook is one comparison and stock's function")
    m = machine(); play(m); m.call(PSYMS['rd_stop'], count=40000000); m.proc = []
    m.call(PSYMS['rd_start_player'], count=4000000)
    expect(not m.proc, 'after a stop the hook does nothing')
    m = machine(); play(m); m.clock += 20000; poll(m); m.proc = []
    m.call(PSYMS['rd_start_player'], count=4000000)
    expect(not m.proc and state(m) == ST['ERROR'], 'in the error state the hook does nothing either')
    # ---- who owns the Home mini bar (rd_owns_bar): a started station, until a local track starts
    m = machine()
    expect(m.call(PSYMS['rd_owns_bar']) == 0, 'at boot (nothing played) the radio does not own the bar')
    play(m, '#EXTINF:-1,Bad\nftp://x/a\n')
    expect(m.call(PSYMS['rd_owns_bar']) == 0, 'a refused address does not take the bar')
    m = machine(); play(m)
    expect(m.call(PSYMS['rd_owns_bar']) == 1, 'a started station owns the bar')
    m.call(PSYMS['rd_stop'], count=40000000)
    expect(state(m) == ST['STOPPED'] and m.call(PSYMS['rd_owns_bar']) == 1, 'Stop keeps it (the bar shows the stopped station)')
    m.call(PSYMS['rd_start_player'], count=4000000)
    expect(m.call(PSYMS['rd_owns_bar']) == 0, 'a local track starting hands it back, also after a Stop')
    l, r = play(m)
    expect(m.call(PSYMS['rd_owns_bar']) == 1, 'a new station takes it again')
    m.call(PSYMS['rd_start_player'], count=40000000)
    expect(m.call(PSYMS['rd_owns_bar']) == 0, 'a local track over a running station hands it back')
    # ---- the radio after local music: Play works again
    m = machine(); up(m)
    m.call(PSYMS['rd_start_player'], count=40000000)
    l, r = play(m)
    expect(r == 1 and state(m) == ST['CONNECTING'] and 'stop_player' in [c[0] for c in m.after], 'the radio can start again after local music took over (stock is stopped first)')
    # ---- Multiple Speed: the radio is live, so always 1x; the user's mode (never written) goes back when the radio lets go
    m = machine(); play(m)
    expect(m.speeds == [] and m.word(PLAYSPEED) == 0, 'at 1x nothing is sent')
    m.call(PSYMS['rd_stop'], count=4000000)
    expect(m.speeds == [], 'and nothing is sent back at 1x')
    m = machine(); m.setword(PLAYSPEED, 2); play(m)
    expect(m.speeds == [0] and m.word(PLAYSPEED) == 2 and m.proc == [('start', 'http://one.example/a')], f'at 1.5x: mclSetPlaySpeed(0) before the URL, the saved mode untouched ({m.speeds})')
    play(m, i=1)
    expect(m.speeds == [0, 0] and m.word(PLAYSPEED) == 2, 'a station switch sends 1x again and does not restore (still the radio)')
    up(m); m.call(PSYMS['rd_stop'], count=4000000)
    expect(m.speeds == [0, 0, 0, 2] and m.word(PLAYSPEED) == 2, f'Stop: the saved mode goes to hciplayer after mclStop ({m.speeds})')
    m.call(PSYMS['rd_stop'], count=4000000)
    expect(m.speeds == [0, 0, 0, 2], 'a second stop sends nothing more')
    m = machine(); m.setword(PLAYSPEED, 3); up(m); m.speeds = []; m.proc = []
    m.call(PSYMS['rd_start_player'], count=40000000)
    expect(m.proc == [('mclStop',)] and m.speeds == [3], f"a local track chosen: the user's speed before stock's start ({m.speeds})")
    m = machine(); m.setword(PLAYSPEED, 1); play(m); m.speeds = []; m.clock += 20000; poll(m)
    expect(state(m) == ST['ERROR'] and m.speeds == [1], f'an error that stops hciplayer gives the speed back ({m.speeds})')
    m.call(PSYMS['rd_stop'], count=4000000)
    expect(m.speeds == [1], 'Stop from Error sends nothing (the radio was not running)')
    m = machine(); m.setword(PLAYSPEED, 2); play(m, '#EXTINF:-1,Bad\nftp://x/a\n')
    expect(m.speeds == [], 'a refused address never touched the speed')


def reroute_tests(ctx):
    """5b. The output changes under a station (docs/modules/radio.md "Output changes"): save_stop_player / save_start_player hooks."""
    expect = ctx.expect
    names = lambda m: [c[0] for c in m.calls]
    def switch(m, out, way, a0=0):
        """What stock runs for an output change: save_stop_player, set_outputchannel's effect on the selector and the way, save_start_player(a0). Returns the calls of the second half."""
        m.call(PSYMS['rd_save_stop'], count=4000000); first = list(m.calls)
        m.setword(G_OUT, out); m.out_way = way; m.proc = []
        m.call(PSYMS['rd_save_start'], a0=a0, count=40000000)
        return first, list(m.calls)
    # ---- a jack switch while playing: the same station again on the new output, stock's pair never reaches mclStartPlayer
    m = machine(); up(m); m.proc = []; m.calls = []
    first, second = switch(m, 1, 0)
    expect(not [c for c in first + second if c[0] in ('stock_save_stop', 'stock_save_start', 'stock_start_player')], f'a running station: stock\'s save_stop_player and save_start_player are not run ({first + second})')
    expect(starts(m) == ['http://one.example/a'] and state(m) == ST['CONNECTING'] and ('set_outputchannel', 1, 2, 0) in second and ('set_devicevolume', 17) in second and ('mclSetMute', 0) in second,
           f'PO to BAL: Connecting, the same URL, the new output readied and the volume set ({second})')
    m.clock += 2000; m.hs = 1; poll(m)
    expect(state(m) == ST['PLAYING'], 'and it is Playing when hciplayer says so')
    # the stop half alone does not end the radio, and the restart is not counted against the one retry
    m = machine(); up(m); m.proc = []
    m.call(PSYMS['rd_save_stop'], count=4000000)
    expect(m.proc == [('mclStop',)] and state(m) == ST['PLAYING'] and m.call(PSYMS['rd_running']) == 1, 'save_stop: mclStop only, the state stays until the start half')
    m.call(PSYMS['rd_save_start'], a0=0, count=40000000)
    m.clock += 2000; m.run = 0; m.ps = 1; m.hs = 0; m.proc = []; poll(m)
    expect(state(m) == ST['CONNECTING'], 'an early end right after a reroute still has its one retry (Connecting, not Error)')
    m.clock += 1500; poll(m)
    expect(starts(m) == ['http://one.example/a'] and state(m) == ST['CONNECTING'], 'and the retry starts the station again')
    # ---- connecting
    m = machine(); play(m)
    switch(m, 1, 0)
    expect(starts(m) == ['http://one.example/a'] and state(m) == ST['CONNECTING'], 'a reroute while connecting restarts the station')
    # ---- USB DAC plugged, then unplugged
    m = machine(); up(m)
    first, second = switch(m, 3, 2)
    expect(starts(m) == ['http://one.example/a'] and ('set_outputchannel', 3, 2, 0) in second and not [n for n in names(m) if n in ('mclSetPcmMode', 'mclSetDacPwr', 'set_devicevolume')],
           f'a USB DAC plugged: the station restarts after set_outputchannel(3), the built-in DAC\'s readying skipped ({second})')
    m.clock += 2000; m.hs = 1; poll(m)
    first, second = switch(m, 0, 0)
    expect(starts(m) == ['http://one.example/a'] and ('set_outputchannel', 0, 2, 0) in second and ('mclSetPcmMode',) in second and ('set_devicevolume', 17) in second and state(m) == ST['CONNECTING'],
           f'the USB DAC unplugged back to the jack: the built-in DAC readied again ({second})')
    # ---- paused: restarted on the new output and paused again
    m = machine(); up(m); m.ps = 3; m.clock += 500; poll(m)
    expect(state(m) == ST['PAUSED'], 'headphones removed (stock calls mclSetPause, status 3): the radio shows Paused')
    first, second = switch(m, 1, 0)
    expect(starts(m) == ['http://one.example/a'] and m.proc[-1] == ('mclSetPause',) and state(m) == ST['PAUSED'], f'a reroute while paused restarts and pauses again ({m.proc})')
    m.clock += 2000; poll(m)
    expect(state(m) == ST['PAUSED'], 'and the tick keeps it Paused (status 3), no error')
    # ---- stock's argument 1 (jacks, USB, standby wake): restarted, then paused so the user presses play
    for label, st0 in (('playing', 'up'), ('connecting', 'play'), ('paused', 'pause')):
        m = machine()
        if st0 == 'play': play(m)
        else: up(m)
        if st0 == 'pause': m.ps = 3; m.clock += 500; poll(m)
        first, second = switch(m, 1, 0, a0=1)
        expect(starts(m) == ['http://one.example/a'] and m.proc[-1] == ('mclSetPause',) and state(m) == ST['PAUSED'] and ('set_outputchannel', 1, 2, 0) in second
               and not [c for c in first + second if c[0] in ('stock_save_stop', 'stock_save_start', 'stock_start_player')], f'{label}: save_start_player(1) restarts the station on the new output and leaves it Paused ({m.proc})')
    m.clock += 2000; poll(m)
    expect(state(m) == ST['PAUSED'], 'the tick keeps it Paused (status 3)')
    m.ps = 2; m.hs = 1; m.clock += 500; poll(m)
    expect(state(m) == ST['PLAYING'], 'the play button (status 2) resumes it')
    m = machine(); up(m); switch(m, 1, 0, a0=1); m.proc = []
    rv = m.call(PSYMS['rd_start_player'], count=40000000)
    expect(rv == 1 and m.proc == [('mclStop',)] and state(m) == ST['STOPPED'], 'a local track picked while Paused after a switch stops the radio')
    m = machine(); up(m); switch(m, 1, 0, a0=1); m.proc = []
    switch(m, 2, 1, a0=1)
    expect(state(m) == ST['ERROR'] and 'Bluetooth' in error(m), 'Bluetooth after a paused reroute is still the error')
    # ---- Bluetooth: the error, stock's restart never runs
    m = machine(); up(m); m.proc = []
    first, second = switch(m, 2, 1)
    expect(state(m) == ST['ERROR'] and 'Bluetooth' in error(m) and not starts(m) and not [c for c in first + second if c[0] in ('stock_save_stop', 'stock_save_start', 'stock_start_player')],
           f'switch to Bluetooth: Error "Bluetooth is not supported", no start, the trampoline not called ({first + second})')
    m = machine(); up(m)
    switch(m, 2, 0)
    expect(state(m) == ST['ERROR'] and 'Bluetooth' in error(m), 'the selector 2 alone is Bluetooth as well')
    # a stop with no start half (Bluetooth linking): the next tick says so
    m = machine(); up(m); m.out_way = 1
    m.call(PSYMS['rd_save_stop'], count=4000000); m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'] and 'Bluetooth' in error(m), 'a stop with no start while the way is Bluetooth: Bluetooth error at the tick')
    m = machine(); up(m)
    m.call(PSYMS['rd_save_stop'], count=4000000); m.clock += 500; poll(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'Playback ended', 'a stop with no start on a jack reads as an end at the tick')
    # ---- no station running: stock's functions, untouched
    for label, setup in (('idle', lambda m: None), ('error', lambda m: (play(m, '#EXTINF:-1,Bad\nftp://x/a\n'),)), ('stopped', lambda m: (play(m), m.call(PSYMS['rd_stop'], count=4000000)))):
        m = machine(); setup(m); m.proc = []; m.calls = []
        stock = lambda: [c for c in m.calls if c[0].startswith('stock_')]   # (the per-output EQ's check runs first in rd_save_start: patch/peqout.c, tested in peq.py)
        m.call(PSYMS['rd_save_stop'], count=4000000); a = stock()
        m.calls = []
        m.call(PSYMS['rd_save_start'], a0=1, count=4000000); b = stock()
        expect(a == [('stock_save_stop',)] and b == [('stock_save_start', 1)] and not m.proc, f'{label}: both hooks are stock\'s function with its argument, nothing else')
    # ---- a user's local track still wins, also right after a reroute
    m = machine(); up(m); switch(m, 1, 0); m.proc = []
    rv = m.call(PSYMS['rd_start_player'], count=40000000)
    expect(rv == 1 and m.proc == [('mclStop',)] and state(m) == ST['STOPPED'], 'a local track chosen after a reroute stops the radio and runs stock')


TOP_CSV = ('changeuuid,stationuuid,serveruuid,name,url,url_resolved,homepage,favicon,tags,country,countrycode,iso_3166_2,state,language,languagecodes,votes,lastchangetime,lastchangetime_iso8601,codec,bitrate,hls\n'
           'a,b,,Alpha FM,http://alpha.example/s,http://alpha.example/r,h,f,"x,y",Germany,DE,,,,,1,t,t,MP3,128,0\n'
           'a,b,,Beta Radio,https://beta.example/s,,h,f,x,France,FR,,,,,1,t,t,AAC,64,0\n')
COUNTRIES_CSV = 'name,iso_3166_1,stationcount\nThe Gambia,GM,35\nGermany,DE,6329\nAndorra,AD,0\nFrance,FR,3562\nAustria,AT,14\n'
GENRES_CSV = 'name,stationcount\npop,6202\nrock,3158\n'


def fetch(m, path, kind, site=None):
    sites = []
    m.curl_site = site or (lambda url, o: (sites.append((url, dict(o))), {'body': TOP_CSV.encode()})[1])
    m.calls = []
    r = m.call(PSYMS['rd_fetch'], a0=m.buf(path), a1=kind, count=40000000)
    return r, sites


def finish(m):
    fn, arg = m.thread
    m.call(fn, a0=arg, count=1 << 40)


def take(m, l):
    err = m.malloc(4)
    r = m.call(PSYMS['rd_fetch_take'], a0=l, a1=err, count=40000000)
    return r, m.s32(err)


def fetch_tests(ctx):
    """4. The directory: the guards, the one worker thread and its libcurl options, the answers, the cancel."""
    expect = ctx.expect
    m = machine()
    path = '/csv/stations/topvote/100?hidebroken=true'
    m.wifi = 0
    r, _ = fetch(m, path, 1)
    expect(r == E['WIFI'] and 'pthread_create' not in m.names(), 'no Wi-Fi: RD_E_WIFI, no thread')
    m = machine(); m.wall = 1_600_000_000
    r, _ = fetch(m, path, 1)
    expect(r == E['CLOCK'] and 'pthread_create' not in m.names(), 'a clock before the firmware existed (certificates would not verify): RD_E_CLOCK')
    m = machine(); m.present.discard(CA)
    r, _ = fetch(m, path, 1)
    expect(r == E['FAIL'] and 'pthread_create' not in m.names(), 'no CA bundle: a failure, no thread')
    m = machine(); m.thread_ok = False
    r, _ = fetch(m, path, 1)
    expect(r == E['FAIL'] and m.call(PSYMS['rd_fetch_state']) == 0, 'a thread that will not start: a failure, nothing running')
    m = machine()
    r, sites = fetch(m, path, 1)
    expect(r == 0 and m.thread[0] == PSYMS['rd_fetch_worker'] and m.call(PSYMS['rd_fetch_state']) == 1, 'a fetch: one worker thread, running')
    r2 = m.call(PSYMS['rd_fetch'], a0=m.buf(path), a1=1, count=40000000)
    expect(r2 == E['BUSY'], 'a second fetch while one runs: RD_E_BUSY')
    finish(m)
    o = sites[0][1]
    expect(sites[0][0] == 'https://all.api.radio-browser.info' + path and o[10065] == CA and o[52] == 1 and o[68] == 5 and o[181] == 3 and o[182] == 3 and o[99] == 1 and o[78] == 10 and o[13] == 30
           and o[10102] == '' and o[10018].startswith('M1PlusMusic/') and 64 not in o and 81 not in o and o[43] == 0 and 20219 in o,
           f"the request: the directory's name, the firmware's CA bundle, redirects (5) limited to http(s), 10 s to connect and 30 in all, no signals, the transfer callback for the cancel; verification is never switched off ({sorted(o)})")
    expect(m.call(PSYMS['rd_fetch_state']) == 2, 'the worker has ended: the answer waits')
    l = new_list(m)
    r, err = take(m, l)
    got = [(m.read_cstr(m.word(l) + m.word(l + 16 + 4 * i)), m.read_cstr(m.word(l) + m.word(l + 16 + 4 * MAXL + 4 * i))) for i in range(m.s32(l + 8))]
    expect(r == 1 and err == 0 and got == [('Alpha FM', 'http://alpha.example/r'), ('Beta Radio', 'https://beta.example/s')], f'the stations of the CSV are the page\'s list ({got})')
    expect(('pthread_join',) in m.calls and m.call(PSYMS['rd_fetch_state']) == 0, 'the worker is joined, nothing is waiting any more')
    expect(len(m.curl) == 0, 'the easy handle is cleaned up')
    # a list the page has stays when an answer has nothing in it
    for body, code, want in ((b'', 200, E['FAIL']), (TOP_CSV.encode(), 500, E['FAIL']), (b'changeuuid,name,url\n', 200, E['EMPTY'])):
        m.curl_site = None
        r, _ = fetch(m, path, 1, site=lambda url, o, b=body, c=code: {'body': b, 'code': c})
        finish(m)
        r, err = take(m, l)
        expect(r == 0 and err == want and len(got) == 2 and m.s32(l + 8) == 2, f'an answer that is empty or an HTTP {code}: the list the page has is kept, the error is {want}')
    r, _ = fetch(m, path, 1, site=lambda url, o: {'rc': 60})
    finish(m)
    r, err = take(m, l)
    expect(r == 0 and err == E['FAIL'], 'a certificate or network failure: a failure')
    # countries and genres
    for body, kind, want in ((COUNTRIES_CSV, 2, [('The Gambia', 'GM', '35'), ('Germany', 'DE', '6329'), ('France', 'FR', '3562'), ('Austria', 'AT', '14')]), (GENRES_CSV, 3, [('pop', 'pop', '6202'), ('rock', 'rock', '3158')])):
        r, _ = fetch(m, '/csv/x', kind, site=lambda url, o, b=body: {'body': b.encode()})
        finish(m)
        pl = new_list(m)
        r, err = take(m, pl)
        buf = m.word(pl)
        rows = [(m.read_cstr(buf + m.word(pl + 16 + 4 * i)), m.read_cstr(buf + m.word(pl + 16 + 4 * MAXL + 4 * i)), m.read_cstr(buf + m.word(pl + 16 + 8 * MAXL + 4 * i))) for i in range(m.s32(pl + 8))]
        expect(r == 1 and rows == want, f'kind {kind}: name, key and count (a country with no stations is dropped) ({rows})')
    # the cancel: Return while loading; the worker ends within a transfer callback, and the next fetch finds the slot free
    r, _ = fetch(m, path, 1)
    m.call(PSYMS['rd_fetch_cancel'], count=100000)
    finish(m)
    r, err = take(m, l)
    expect(r == 0, 'a cancelled fetch gives nothing')
    r, _ = fetch(m, path, 1)
    expect(r == 0, 'and the next fetch starts (the finished worker is joined first)')
    finish(m)
    m.call(PSYMS['rd_fetch_drop'], count=100000)
    expect(m.call(PSYMS['rd_fetch_state']) == 0, 'the page closing drops an answer nobody took')
    # the answer is cut at 256 KB
    big = (TOP_CSV.split('\n')[0] + '\n' + ''.join(f'a,b,,Station {i},http://h.example/{i},,h,f,x,Germany,DE,,,,,1,t,t,MP3,128,0\n' for i in range(5000))).encode()
    r, _ = fetch(m, path, 1, site=lambda url, o: {'body': big})
    finish(m)
    r, err = take(m, l)
    expect(len(big) > 256 * 1024 and r == 1 and m.s32(l + 8) == MAXL - 1 or m.s32(l + 8) == MAXL, f'a larger answer is cut at the cap and its whole rows are used ({m.s32(l + 8)} stations)')


def card_tests(ctx):
    """5. The card: favourites.m3u (atomic), the user's lists, the recent stations."""
    expect = ctx.expect
    m = machine()
    l = new_list(m, STATIONS)
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=1, count=40000000)
    expect(r == 1 and m.fs[FAVS] == b'#EXTM3U\n#EXTINF:-1,Two\nhttps://two.example/b\n' and FAVS + '.tmp' not in m.fs, f'a station added: favourites.m3u made through a .tmp ({m.fs.get(FAVS)})')
    expect(('rename', FAVS + '.tmp', FAVS) in m.calls and ('fsync', FAVS + '.tmp') in m.calls, 'written aside, synced, renamed')
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=0, count=40000000)
    expect(r == 1 and m.fs[FAVS] == b'#EXTM3U\n#EXTINF:-1,Two\nhttps://two.example/b\n#EXTINF:-1,One\n#M1+:Germany\tMP3\t128\nhttp://one.example/a\n', f'the next one is appended with its info ({m.fs[FAVS]})')
    expect(m.call(PSYMS['rd_fav_has'], a0=m.buf('http://one.example/a'), count=40000000) == 1 and m.call(PSYMS['rd_fav_has'], a0=m.buf('http://three.example/c'), count=40000000) == 0, 'the file says which stations are favourites')
    s0 = m.call(PSYMS['rd_serial'], count=10000)
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=1, count=40000000)
    expect(r == 0 and m.fs[FAVS] == b'#EXTM3U\n#EXTINF:-1,One\n#M1+:Germany\tMP3\t128\nhttp://one.example/a\n' and m.call(PSYMS['rd_serial'], count=10000) == s0 + 1, 'the same station again takes it out; the serial moves (the heart redraws)')
    before = m.fs[FAVS]
    m.card_mounted = False
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=2, count=40000000)
    expect(r == 0xffffffff and m.fs[FAVS] == before and FAVS + '.tmp' not in m.fs, 'no card mounted: -1, nothing written')
    m.card_mounted = True
    m.fail.add(('rename', FAVS))
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=2, count=40000000)
    expect(r == 0xffffffff and m.fs[FAVS] == before and FAVS + '.tmp' not in m.fs, 'a rename that fails: -1, the old file stays, no temp file is left')
    m.fail.discard(('rename', FAVS))
    m.put_text(FAVS, b'#EXTM3U\n#EXTINF:-1,A\nhttp://a.example/x\n\0#EXTINF:-1,B\nhttp://b.example/y\n')
    before = m.fs[FAVS]
    r = m.call(PSYMS['rd_fav_toggle'], a0=l, a1=2, count=40000000)
    expect(r == 0xffffffff and m.fs[FAVS] == before, 'a favourites file with a NUL in it (it would hide stations): never rewritten')
    # favourites.m3u alone is the Stations list; no file is an empty list, not a failure
    m = machine()
    m.put_text(FAVS, '#EXTM3U\n#EXTINF:-1,Fav\nhttp://fav.example/f\n')
    m.put_text(RADIO_DIR + '/Jazz.m3u', '#EXTM3U\n#EXTINF:-1,Jazz One\nhttp://jazz.example/1\n')
    out = new_list(m)
    r = m.call(PSYMS['rd_favs_read'], a0=out, count=40000000)
    got = [m.read_cstr(m.word(out) + m.word(out + 16 + 4 * i)) for i in range(m.s32(out + 8))]
    expect(r == 1 and got == ['Fav'], f'the Stations list is favourites.m3u only; the card files are not read live ({got})')
    m = machine()
    out = new_list(m)
    r = m.call(PSYMS['rd_favs_read'], a0=out, count=40000000)
    expect(r == 1 and m.s32(out + 8) == 0, 'no favourites file: an empty list, not a failure')
    # ---- Import from Card (rd_fav_import)
    def imp(m):
        fp = m.malloc(8); m.u.mem_write(fp, bytes(8))
        r = m.call(PSYMS['rd_fav_import'], a0=fp, count=80000000)
        return (r - (1 << 32) if r >= 1 << 31 else r), m.s32(fp)
    def renames(m): return len([c for c in m.calls if c[0] == 'rename'])
    m = machine()
    m.put_text(FAVS, '#EXTM3U\n#EXTINF:-1,Fav\nhttp://fav.example/f\n')
    m.put_text(RADIO_DIR + '/World.PLS', '[playlist]\nFile1=http://world.example/1\nTitle1=World One\n')   # (put in this order: the import sorts by name)
    m.put_text(RADIO_DIR + '/Mix.m3u8', '#EXTM3U\n#EXTINF:-1,Mix Jazz\nhttp://jazz.example/1\n#EXTINF:-1,Mix One\nhttp://mix.example/1\n#EXTINF:-1,Mix One Again\nhttp://mix.example/1\n')
    m.put_text(RADIO_DIR + '/Jazz.m3u', '#EXTM3U\n#EXTINF:-1,Jazz One\nhttp://jazz.example/1\n#EXTINF:-1,Fav Again\nhttp://fav.example/f\n')
    m.put_text(RADIO_DIR + '/notes.txt', 'http://not.example/a\n')
    m.put_text(RADIO_DIR + '/.hidden.m3u', 'http://hidden.example/a\n')
    users = {k: bytes(v) for k, v in m.fs.items() if k != FAVS}
    s0 = m.call(PSYMS['rd_serial'], count=10000)
    r, full = imp(m)
    want = b'#EXTM3U\n' + row('Fav', 'http://fav.example/f') + row('Jazz One', 'http://jazz.example/1') + row('Mix One', 'http://mix.example/1') + row('World One', 'http://world.example/1')
    expect(r == 3 and full == 0 and m.fs[FAVS] == want, f'import: .m3u, .m3u8 and .pls by file name (Jazz, Mix, World), the stations already in the file or imported before skipped, appended in file order ({r}, {m.fs.get(FAVS)})')
    expect(renames(m) == 1 and ('rename', FAVS + '.tmp', FAVS) in m.calls and FAVS + '.tmp' not in m.fs and m.call(PSYMS['rd_serial'], count=10000) == s0 + 1, 'written once through the card write path; the serial moves (the list re-reads)')
    expect({k: bytes(v) for k, v in m.fs.items() if k != FAVS} == users and not [c for c in m.calls if c[0] == 'unlink'], "the user's files (and .txt, dot files) are untouched: no change, no rename, no delete")
    r, full = imp(m)
    expect(r == 0 and full == 0 and m.fs[FAVS] == want and renames(m) == 0 and m.call(PSYMS['rd_serial'], count=10000) == s0 + 1, f'importing again adds nothing and writes nothing ({r}, {full}, {renames(m)}, {m.fs[FAVS] == want})')
    # no favourites file yet: it is made; the stations of a repeated .pls address collapse; one new station
    m = machine()
    m.put_text(RADIO_DIR + '/a.pls', '[playlist]\nFile1=http://x.example/1\nFile2=http://x.example/1\nTitle2=Dup\n')
    r, full = imp(m)
    expect(r == 1 and m.fs[FAVS].startswith(b'#EXTM3U\n') and m.fs[FAVS].count(b'\nhttp://x.example/1\n') == 1, f'no favourites.m3u yet: made by the import, a repeated address once ({r}, {m.fs.get(FAVS)})')
    # nothing to import
    m = machine()
    m.put_text(FAVS, '#EXTM3U\n#EXTINF:-1,Fav\nhttp://fav.example/f\n')
    m.put_text(RADIO_DIR + '/readme.txt', 'x\n')
    before = m.fs[FAVS]
    r, full = imp(m)
    expect(r == -2 and m.fs[FAVS] == before and renames(m) == 0, 'only favourites.m3u, a dot file and a .txt in the folder: -2 (no playlists), nothing written')
    # no card, a write that fails
    m = machine()
    m.put_text(FAVS, '#EXTM3U\n#EXTINF:-1,Fav\nhttp://fav.example/f\n')
    m.put_text(RADIO_DIR + '/a.m3u', '#EXTINF:-1,A\nhttp://a.example/1\n')
    before = m.fs[FAVS]
    m.card_mounted = False
    r, full = imp(m)
    expect(r == -1 and m.fs[FAVS] == before and FAVS + '.tmp' not in m.fs, 'no card mounted: -1, nothing written')
    m.card_mounted = True
    m.fail.add(('rename', FAVS))
    r, full = imp(m)
    expect(r == -1 and m.fs[FAVS] == before and FAVS + '.tmp' not in m.fs, 'a write that fails: -1, the old file stays, no temp file')
    m.fail.discard(('rename', FAVS))
    m.put_text(FAVS, b'#EXTM3U\n#EXTINF:-1,A\nhttp://a.example/x\n\0#EXTINF:-1,B\nhttp://b.example/y\n')
    before = m.fs[FAVS]
    r, full = imp(m)
    expect(r == -1 and m.fs[FAVS] == before, 'a favourites file with a NUL in it: never rewritten')
    # the cap: RD_MAX stations
    n_fav, n_new = 298, 5
    m = machine()
    m.put_text(FAVS, '#EXTM3U\n' + ''.join(f'#EXTINF:-1,F{i}\nhttp://f.example/{i}\n' for i in range(n_fav)))
    m.put_text(RADIO_DIR + '/new.m3u', '#EXTM3U\n' + ''.join(f'#EXTINF:-1,N{i}\nhttp://n.example/{i}\n' for i in range(n_new)))
    r, full = imp(m)
    expect(r == 2 and full == 1 and m.fs[FAVS].count(b'#EXTINF') == 300 and b'http://n.example/1\n' in m.fs[FAVS] and b'http://n.example/2\n' not in m.fs[FAVS], f'the cap: 300 stations, what fits is added and "full" says the cap stopped it ({r}, {full})')
    before = m.fs[FAVS]
    r, full = imp(m)
    expect(r == 0 and full == 1 and m.fs[FAVS] == before, 'at the cap: nothing added, full, nothing written')
    # the recent stations: the first one is the station last played
    m = machine()
    l, r = play(m, STATIONS, 1)
    out = new_list(m)
    expect(m.call(PSYMS['rd_last_read'], a0=out, count=40000000) == 1 and m.s32(out + 8) == 1 and m.read_cstr(m.word(out) + m.word(out + 16)) == 'Two', 'the first recent station is the one that was started (rd_last_read: a one-station list)')
    big = '#EXTM3U\n' + ''.join(f'#EXTINF:-1,R{i}\nhttp://r.example/{i}\n' for i in range(12))
    L = new_list(m, big)
    for i in range(12): m.call(PSYMS['rd_recent_push'], a0=L, a1=i, count=40000000)
    out = new_list(m)
    m.call(PSYMS['rd_recent_read'], a0=out, count=40000000)
    buf = m.word(out); got = [m.read_cstr(buf + m.word(out + 16 + 4 * i)) for i in range(m.s32(out + 8))]
    expect(got == [f'R{i}' for i in range(11, 1, -1)], f'recent: the last ten, newest first ({got})')
    m.call(PSYMS['rd_recent_push'], a0=L, a1=5, count=40000000)
    expect(RECENT + '.tmp' not in m.fs and ('rename', RECENT + '.tmp', RECENT) in m.calls and ('fsync', '/mnt/data/m1plus') in m.calls, 'written through the settings folder\'s atomic writer (temp file, renamed over radio-recent, folder synced)')
    m.call(PSYMS['rd_recent_read'], a0=out, count=40000000)
    buf = m.word(out); got = [m.read_cstr(buf + m.word(out + 16 + 4 * i)) for i in range(m.s32(out + 8))]
    expect(got == ['R5', 'R11', 'R10', 'R9', 'R8', 'R7', 'R6', 'R4', 'R3', 'R2'], f'a station played again moves to the front, once ({got})')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The pages
UI_DIR = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui') if WORK else None
SCREEN_Y0 = 30 + 50
ROW_ROOT, ROW_LIST, TOP, VIEW_H = 52, 64, 60, O['GRID_VIEW_H']
SC_YOFF = O['SC_YOFF']
PAGE_WIDGETS = ('view_grid', 'btn_return', 'btn_backtoplayer', 'btn_search', 'label_title', 'sg_title', 'label_status', 'label_row_title', 'label_row_sub', 'img_nb_fade', 'label_grid_title', 'label_grid_sub', 'label_hdr', 'label_rail', 'label_rail_on',
                'sg_rail', 'sg_bubble', 'sg_bubble_letter', 'rd_credit', 'kb_field', 'radio_listview', 'btn_radioview', 'btn_more', 'rd_sh_scrim', 'rd_sh_card', 'rd_sh_import', 'rd_sh_import_hr', 'rd_sh_clear', 'rd_sh_clear_hr')
ICONS = ('pod_ic_rd_stations', 'pod_ic_rd_top', 'pod_ic_rd_country', 'pod_ic_rd_genre', 'pod_ic_nowplaying', 'pod_ic_recent', 'pod_ic_rd_browser')
NP_WIDGETS = ('rn_art', 'rn_art_ic', 'btn_return', 'btn_play', 'btn_prev', 'btn_next', 'btn_fav', 'rn_title', 'rn_artist', 'rn_station', 'rn_info', 'rn_elapsed', 'rn_live', 'rn_more', 'rd_sh_scrim', 'rd_sh_card', 'rd_sh_add', 'rd_sh_add_ic', 'rd_sh_add_tx', 'rd_sh_add_hr', 'rd_sh_info', 'rd_sh_info_hr')
NP_WIN = 0x20002000


VIEW, VIEW_TMP = '/mnt/data/m1plus/radio-view', '/mnt/data/m1plus/radio-view.tmp'


def page_machine(window=0x20001000, view=b'1\n'):
    """view: the radio-view file (default the grid: most tests below measure the grid; None: no file, the default list)."""
    m = machine()
    if view is not None: m.fs[VIEW] = view
    m.window = window
    m.windows['m1plus_radionp'] = NP_WIN
    m.load_image = 0
    KB.keyboard_machine(m)   # the keyboard's pad, strip and field widgets with their geometry (keyboard_attach finds them by name)
    for w in PAGE_WIDGETS: Machine.widget(m, w)
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    for n in ICONS: m.images[n] = (24, 24, bytes((0xee, 0xee, 0xee, 255)) * (24 * 24))
    m.images['pod_ic_rd_art'] = (96, 96, bytes((0x8e, 0x8e, 0x93, 255)) * (96 * 96))
    win, lv, sv, view = m.alloc(0x80), m.alloc(0x80), m.alloc(0x180), m.widgets['view_grid']
    m.u.mem_write(sv, bytes(0x180))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, VIEW_H, win), (sv, 0, VIEW_H, lv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    m.widgets['radio_scrollview'] = sv
    for off, v in ((4, 0), (8, 320), (0xc, VIEW_H), (0x44, sv)): m.setword(view + off, v)
    m.setword(m.widgets['label_title'] + 8, 156); m.setword(m.widgets['sg_title'] + 8, 296)
    m.mem_geometry, m.live_scroll = True, frozenset({sv})
    m.sv, m.view = sv, view
    m.widgets['radio_listview'] = lv
    m.lv = lv
    return m


def open_radio(m): m.call(PSYMS['radio_open'], count=900000000); return list(m.calls)
def opened_view(view, **kw):
    m = page_machine(view=view, **kw); open_radio(m)
    return m


def opened(**kw):
    m = page_machine(**kw); open_radio(m)
    return m


def paint(m):
    """One EVT_AFTER_PAINT on the content view: (blits, texts with their styles, fills)."""
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.setword(m.canvas + O['CANVAS_OY'], (SCREEN_Y0 - m.word(m.sv + SC_YOFF)) & 0xffffffff)
    m.blits.clear(); m.texts.clear(); m.text_styles.clear(); m.fills.clear()
    m.call(PSYMS['rp_on_paint'], a0=0, a1=ev, count=400000000)
    return list(m.blits), list(zip(m.texts, m.text_styles)), list(m.fills)


def rows_text(m, which='label_row_title'):
    return [t for (t, r), s in paint(m)[1] if s == which]


def tap(m, x, y, dx=0, dy=0):
    m.touch('down', x, SCREEN_Y0 + y, 1000, fn='rp_on_down')
    m.touch('up', x + dx, SCREEN_Y0 + y + dy, 1080, fn='rp_on_up')
    return list(m.calls)


def tap_row(m, r, x=100, root=False, off=0, gap=0):
    m.calls.clear()
    return tap(m, x, TOP + r * (ROW_ROOT if root else ROW_LIST) + (gap if r else 0) + 20 - off)


def tap_cell(m, i, off=0):
    """A tap on station i of the grid (2 columns of 144 px covers from x 12, rows 200 px apart from y 60)."""
    m.calls.clear()
    return tap(m, 12 + (i % 2) * 152 + 20, TOP + (i // 2) * 200 + 20 - off)


def grid_titles(m): return rows_text(m, 'label_grid_title')
def grid_subs(m): return rows_text(m, 'label_grid_sub')


def click(m, name):
    m.click(name, count=900000000)
    return list(m.calls)


def destroy_np(m, win=None):
    """The window's EVT_DESTROY as AWTK delivers it: the handler bound on `win` (default: the machine's window), with its bound ctx."""
    fn, c = m.bound[(m.windows.get('m1plus_radionp', m.window) if win is None else win, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=4000000)


def vis(m, name):
    w = m.widgets[name]
    return m.props.get((w, 'visible'), 1), m.props.get((w, 'sensitive'), 1)


def ui(name): return awtk_ui.parse(open(os.path.join(UI_DIR, name + '.bin'), 'rb').read())
def u8(s):
    """A mocked text as the user reads it: UTF-8 bytes read as latin-1 (the payload's own strings come back twice over from the mocked translation)."""
    for _ in range(2):
        try: s = s.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError): break
    return s
def text_of(m, name): return u8(m.wtext.get(m.widgets[name]))


def asset_tests(ctx):
    """6. The built assets and the entries."""
    expect = ctx.expect
    P = pod_pages
    root = ui('m1plus_radio'); f = root.find
    expect(root.name == 'm1plus_radio_page' == P.RADIO.name and P.RADIO.kind == 'radio' and P.RADIO in P.PAGES and ui('m1plus_radionp').name == 'm1plus_radionp_page' == P.RADIONP.name and P.RADIONP in P.PAGES
           and P.PAGES[-19:-16] == [P.RADIO, P.RADIONP, P.RADIOINFO] and P.PAGES[-14:-9] == [P.WIFI_PAGE, P.WIFIINFO_PAGE, P.WIFIPASS_PAGE, P.WIFIOTHER_PAGE, P.WIFISEC_PAGE] and P.PAGES[-9:-1] == [P.PEQ_PAGE, P.PEQP_PAGE, P.PEQLIB_PAGE, P.TENBAND_PAGE, P.TENCURVE_PAGE, P.TENPREAMP_PAGE, P.AUTOEQ_PAGE, P.PEQBAND_PAGE], 'the pages m1plus_radio, m1plus_radionp and m1plus_radioinfo are built and follow the Pull-down page in the page table (Get Info, the Podcast Region picker and the Wi-Fi pages come after them)')
    expect(all(f(n) is not None for n in PAGE_WIDGETS if n != 'radio_scrollview'), 'every widget the stations page looks up is in the asset')
    lv, sv, grid = f('radio_listview'), f('radio_scrollview'), f('view_grid')
    expect((lv.y, lv.h) == (50, VIEW_H) and sv.w == 310 and f('scroll_bar_m') is not None and grid.get('style:normal:bg_color') == '#000000', 'a stock list under the 50 px navbar holding the content view')
    k = {c.name: c for c in f('navigationbar_view').children}
    expect((k['btn_search'].x, k['btn_search'].w) == (214, 46) and k['btn_search'].get('style:normal:icon') == 'pod_nav_search' and k['btn_search'].get('visible') != 'false' and 'btn_globe' not in k
           and k['btn_search'].x + k['btn_search'].w == k['btn_backtoplayer'].x and k['btn_backtoplayer'].get('style:normal:icon') == 'ah_nav_play'
           and (k['btn_more'].x, k['btn_more'].w) == (214, 46) and k['btn_more'].get('style:normal:icon') == 'pod_nav_more' and k['btn_more'].get('visible') == 'false',
           'Search | Now Playing is one glass capsule: the magnifier the left cap, flush against Now Playing, the right cap; the Stations "..." (btn_more) is hidden in the same slot')
    expect(k['label_title'].get('visible') == 'false' and k['label_title'].w == 214 - 58, 'the small title is hidden until the large one has scrolled away, and runs to the magnifier')
    big = f('sg_title')
    expect((big.x, big.y, big.h) == (O['SG_TITLE_X'], 0, O['SG_TITLE_H']) and big.get('style:normal:font_size') == '32' and big.get('sensitive') == 'false', "the large title is the Songs page's: 32 px at x 12, insensitive")
    for n in ('label_status', 'label_row_title', 'label_row_sub', 'label_grid_title', 'label_grid_sub', 'label_hdr', 'label_rail', 'label_rail_on', 'sg_bubble', 'img_nb_fade', 'rd_credit', 'kb_field'):
        expect(f(n).get('visible') == 'false' and f(n).get('sensitive') == 'false', f'{n}: hidden and insensitive at rest')
    cr = f('rd_credit')
    expect((cr.x, cr.w, cr.h) == (0, 296, 20) and cr.get('style:normal:font_size') == '14' and cr.get('style:normal:text_color') == '#8E8E93' and cr.get('style:normal:text_align_h') == 'left'
           and pod_i18n.shown_english(cr) == 'Stations from radio-browser.info' and cr in f('view_grid').children, "the credit: a small grey caption inside the content view, so it scrolls with the rows")
    expect(f('kb_field').y == 56 and all(f(n) is not None for n in ('kb_pad', 'kb_strip', 'kb_stem', 'kb_pop', 'kb_text', 'kb_hint', 'kb_caret', 'kb_clear', 'kb_go')), "the search page's field and pad are in the asset, the field under the navbar")
    fld, se = f('kb_field'), awtk_ui.parse(open(os.path.join(UI_DIR, 'm1plus_search.bin'), 'rb').read()).find('kb_field')
    expect((fld.x, fld.h, fld.get('style:normal:round_radius'), fld.get('style:normal:bg_color')) == (se.x, se.h, se.get('style:normal:round_radius'), se.get('style:normal:bg_color'))
           and fld.x + fld.w == 320 - se.x and fld.y >= 50 and f('kb_clear').x + f('kb_clear').w == fld.w and f('kb_text').x + f('kb_text').w <= f('kb_clear').x and f('kb_hint').w == f('kb_text').w,
           "Radio's search field is the Search page's (x, height, radius, colour) and runs the page's width (margin each side, no round X beside it), under the 50 px navbar; the clear button ends it and the text stops short of it")
    names_ = [c.name for c in root.children]
    expect(names_.index('radio_listview') < names_.index('kb_field') and names_.index('rd_sh_card') > names_.index('kb_field') and names_[-2:] == ['rd_sh_scrim', 'rd_sh_card'] and f('rd_sh_add') is None
           and f('rd_sh_import') is not None and f('rd_sh_scrim').get('visible') == 'false' and f('rd_sh_card').get('visible') == 'false', 'the pad lies over the list; the Stations sheet (Import from Card) is last, above everything, hidden; a station is added to Stations from Now Playing')
    expect(f('sg_rail') is not None and f('sg_rail').x == O['SG_RAIL_X'] and f('sg_bubble_letter') is not None and f('label_grid_title').get('style:normal:font_size') == '18' and f('label_grid_sub').get('style:normal:text_color') == '#AAAAAA'
           and f('label_hdr') is not None, "the countries' rail, its bubble and header style, and the Albums grid's two text styles are in the asset")
    item = next(i for i, r in enumerate(P.ITEMS) if r.label == 'Radio')
    expect(item == 22 == len(P.ITEMS) - 2 and P.ITEMS[item].action == P.ACT_RADIO == 50 and P.ID_CHARS[item] == 'n' and item not in P.DEFAULT_MENU and P.EXTRAS_GROUPS[1][1][-3:] == ('Radio', 'Search', 'Navidrome')
           and P.parse_menu_full(b'123456n\n') == ([1, 2, 3, 4, 5, 6, 22], []) and P.format_menu([1, 2, 22]) == '12n\n' and len(P.format_menu(list(range(10)), list(range(10, 18)) + [19, 20, 21, 22])) < P.MENU_FILE_MAX
           and 'radio-recent' in P.SETTING_FILES, 'Radio is item 22 (saved as "n"), hidden from the menu by default, in the Library group of Extras after Podcasts and before Search')
    xx = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx')
    from PIL import Image
    expect(all(os.path.exists(os.path.join(xx, n + '.png')) and Image.open(os.path.join(xx, n + '.png')).size == (24, 24) for n in ICONS), 'the glyphs the rows draw are in the tree, 24 x 24')
    expect(all(os.path.exists(os.path.join(xx, n + '.png')) for n in ('pod_ic_radio', 'pod_ic_rd_art', 'pod_ic_rd_add', 'pod_ic_rd_remove', 'pod_ic_rd_import', 'pod_ic_rd_stations', 'np_fav', 'np_unfav', 'np_unfav_down')) and not any(os.path.exists(os.path.join(xx, n + '.png')) for n in ('pod_ic_rd_fav', 'pod_ic_rd_unfav')), 'and the menu glyph, the art glyph, the sheet glyphs (plus, minus, import), the Stations row glyph; no star glyph is left')
    np = ui('m1plus_radionp'); g = np.find
    expect(all(g(n) is not None for n in NP_WIDGETS + ('rn_art', 'rn_art_ic', 'img_np_tint', 'label_title')), 'every widget the Now Playing page looks up is in the asset')
    import mod_nowplaying as NP
    expect((g('btn_return').x, g('btn_return').y, g('btn_return').w, g('btn_return').h) == NP.RETURN and (g('rn_art').x, g('rn_art').y, g('rn_art').w, g('rn_art').h) == (NP.ART_X, NP.ART_Y, NP.ART, NP.ART)
           and g('rn_art').get('style:normal:round_radius') == '10' and (g('rn_more').x, g('rn_more').y, g('rn_more').w) == (NP.MORE_X, NP.BTN_Y, NP.BTN) and g('rn_more').get('style:normal:bg_image') == 'np_more',
           "Now Playing's numbers: the grabber, the 264 px art card with 10 px corners, the round '...' where the More disc is")
    t, a, play = g('rn_title'), g('rn_artist'), g('btn_play')
    expect(t.x == a.x == NP.M and t.x + t.w == a.x + a.w <= NP.MORE_X and t.get('style:normal:font_size') == '22' and t.get('style:normal:text_color') == '#FFFFFF' and a.get('style:normal:font_size') == '17'
           and a.get('style:normal:text_color') == '#AAAAAA' and t.y + t.h <= a.y and a.y + a.h <= 366, 'the station name (22 px white) over its line (17 px grey), left aligned in the room the "..." leaves')
    live = g('rn_live')
    expect(live.get('visible') == 'false' and (live.x, live.w) == (NP.M, 320 - 2 * NP.M) and [c.name for c in live.children] == ['rn_live_l', 'rn_live_r', 'rn_live_tx'] and live.children[0].h == NP.LIVE_BAR_H == 4
           and live.children[0].get('image') == 'rn_live_l' and live.children[1].get('image') == 'rn_live_r' and live.children[0].x + live.children[0].w < live.children[2].x and live.children[2].x + live.children[2].w < live.children[1].x
           and live.children[2].get('style:normal:font_size') == '13', 'a LIVE divider: a 4 px fading capsule image each side of a small LIVE, hidden until a station runs')
    expect(play.x + play.w // 2 == 160 and (play.w, play.h) == (64, 64) and play.y >= 366 + 16 and play.y + play.h <= 450 and play.get('style:normal:bg_image') == 'rn_play' and play.get('style:pressed:bg_image') == 'rn_play_down',
           'one large centred play / stop button under the divider')
    for n in ('btn_fav', 'btn_prev', 'btn_next', 'rn_station', 'rn_info', 'rn_elapsed'):
        expect(g(n).get('visible') == 'false' and g(n).get('sensitive') == 'false', f'{n}: kept for the payload, hidden and insensitive (no star, no prev / next on the page)')
    expect(g('rd_sh_card') is not None and g('rd_sh_add') is not None and g('rd_sh_scrim').h == 450 and (names_ := [c.name for c in np.children]).index('rd_sh_card') > names_.index('btn_return'), 'the sheet is on the page, over everything')
    rows2 = [c for c in g('rd_sh_card').children]
    expect([c.name for c in rows2] == ['rd_sh_add', 'rd_sh_info'] and (g('rd_sh_card').h, g('rd_sh_card').y) == (2 * O['PM_ROW_H'], 450 - 2 * O['PM_ROW_H']) and g('rd_sh_card').get('style:normal:bg_image') == 'pc_sheet2'
           and rows2[1].y == O['PM_ROW_H'] and g('rd_sh_info_ic').get('image') == 'pod_ic_rd_info' and g('rd_sh_info_tx').get('text') in ('Station Info', None) and g('rd_sh_info_tx').get('style:normal:text_color') == '#FFFFFF',
           "Radio Now Playing's sheet has two rows: Add to / Remove from My Stations, Station Info (Lucide info), white, the card two rows high")
    cr_ = f('rd_sh_card')
    expect([c.name for c in cr_.children] == ['rd_sh_import', 'rd_sh_clear'] and f('rd_sh_clear_ic').get('image') == 'pc_ic_trash' and f('rd_sh_clear_tx').get('style:normal:text_color') == '#FFFFFF'
           and f('rd_sh_import_ic').get('image') == 'pod_ic_rd_import', "the stations page's sheet has Import from Card and Clear Recently Played (the trash glyph of the other delete rows, neutral white), the payload shows one")
    ri = ui('m1plus_radioinfo'); h = ri.find
    expect(ri.name == 'm1plus_radioinfo_page' == P.RADIOINFO.name and P.RADIOINFO.kind == 'radioinfo' and P.RADIOINFO.title == 'Station Info' and all(h(n) is not None for n in SI_WIDGETS + ('ri_scrollview', 'btn_return', 'label_title'))
           and ri.get('style:normal:bg_color') == '#000000' and h('ri_view').get('style:normal:bg_color') == '#000000' and h('ri_listview').type == 'list_view' and h('ri_scrollview').type == 'scroll_view' and h('scroll_bar_m') is not None
           and (h('ri_listview').y, h('ri_listview').h, h('ri_view').w) == (50, 400, 320) and h('img_nb_fade').get('visible') == 'false' and h('img_nb_fade').get('sensitive') == 'false',
           'Station Info: a black page, the stock navbar (Back, Now Playing) over a stock list holding one content view, the fade hidden at rest')
    expect(all(h(n).get('visible') == 'false' and h(n).get('sensitive') == 'false' for n in ('label_head', 'label_key', 'label_val'))
           and [h(n).get(f'style:normal:{k}') for n, k in (('label_head', 'font_size'), ('label_key', 'font_size'), ('label_val', 'font_size'))] == ['28', '14', '18']
           and [h(n).get('style:normal:text_color') for n in ('label_head', 'label_key', 'label_val')] == ['#FFFFFF', '#8E8E93', '#FFFFFF'], 'the three text styles: a 28 px white heading, the 14 px grey (#8E8E93) label, the 18 px white value')
    expect(h('rd_sh_card') is None, 'the page has no sheet of its own')
    expect(all(g(n).get('sensitive') == 'false' for n in ('rn_art','rn_art_ic', 'img_np_shadow', 'rn_title', 'rn_artist', 'rn_live', 'img_np_tint')),
           'decoration and text are insensitive: only the grabber, the "..." and the play button take touches')
    for n in ('rn_title', 'rn_artist', 'rn_station', 'rn_info', 'rn_elapsed'):
        expect(g(n).x >= 0 and g(n).x + g(n).w <= 320 and g(n).y + g(n).h <= 450, f'{n} lies inside the window')
    # ---- the captions: word wrap, and room for every caption in every language
    from awtk_text import Ttf, StbText
    import pod_wrap
    st = f('label_status')
    expect(st is not None and (st.x, st.w) == (20, 280) and st.h >= 120 and st.y + st.h // 2 == 225 and st.get('style:normal:font_size') == '18', 'the caption label: 280 px wide, 120 px tall, centred on the same line as before')
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    built = {fn[:-4]: dict(__import__('awtk_strings').load(os.path.join(raw, 'strings', fn))) for fn in sorted(os.listdir(os.path.join(raw, 'strings')))}
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    caps = ['Loading…', 'No Wi-Fi', 'Set the date first', 'Directory unavailable. Tap to try again.', 'No stations', 'No recently played stations', 'Not enough memory',
            'Add stations from Radio Browser or import .m3u files from the card.']
    pitch = 18 * 5 // 4 + 1   # a line of the 18 px label (the 'spacer' style row pitch is about 1.25 x the size)
    long = []
    for loc in pod_i18n.LOCALES:
        for key in caps:
            t = built[loc].get(key, key)
            sb = StbText(font, 18)
            lines = pod_wrap.wrap(t, [sb.layout(c)[1] for c in t], st.w, 6, sb.layout('…')[1])
            if len(lines) * pitch > st.h or lines[-1].endswith('…') and not t.endswith('…'): long.append((loc, key, len(lines)))
    expect(not long, f'every caption fits the label (at most {st.h // pitch} lines of 280 px) in all 13 languages ({long[:4]})')
    expect(max(len(pod_wrap.wrap(built['en_US'][caps[-1]], [StbText(font, 18).layout(c)[1] for c in built['en_US'][caps[-1]]], st.w, 6, 5)) for _ in (0,)) <= 3, 'the empty-list hint is three lines or fewer in English')
    # the sheet rows and the root row's names fit in every language
    np_ = ui('m1plus_radionp'); rows = [np_.find('rd_sh_add_tx')]
    over = []
    for w_ in rows:
        px = int(w_.get('style:normal:font_size') or 17)
        for loc in pod_i18n.LOCALES:
            for key in ('Add to My Stations', 'Remove from My Stations'):
                t = built[loc].get(key, key)
                if StbText(font, px).layout(t)[1] > w_.w: over.append((loc, key, StbText(font, px).layout(t)[1], w_.w))
    expect(not over, f'the sheet row\'s two texts fit its label in all 13 languages ({over[:4]})')
    over = []
    for w_, keys in ((np_.find('rd_sh_info_tx'), ('Station Info',)), (f('rd_sh_clear_tx'), ('Clear Recently Played',)), (f('rd_sh_import_tx'), ('Import from Card',))):
        px = int(w_.get('style:normal:font_size') or 17)
        for loc in pod_i18n.LOCALES:
            for key in keys:
                t = built[loc].get(key, key)
                if StbText(font, px).layout(t)[1] > w_.w: over.append((loc, key, StbText(font, px).layout(t)[1], w_.w))
    expect(not over, f'the new sheet rows (Station Info, Clear Recently Played) fit their labels in all 13 languages ({over[:4]})')
    over = []
    for loc in pod_i18n.LOCALES:
        for key in ('Stream URL', 'Logo URL', 'Country', 'Codec', 'Bitrate', 'Source', 'Status'):
            if StbText(font, 14).layout(built[loc].get(key, key))[1] > 288: over.append((loc, key))
        for key in ('Radio Browser', 'Imported', 'Playing', 'Connecting…', 'Paused', 'Stopped', "Can't play"):
            if StbText(font, 18).layout(built[loc].get(key, key))[1] > 288: over.append((loc, key))
        if StbText(font, 22).layout(built[loc].get('Station Info', 'Station Info'))[1] > h('label_title').w: over.append((loc, 'the navbar title'))
    expect(not over and all(k in pod_i18n.TEXT for k in ('Station Info', 'Stream URL', 'Logo URL', 'Country', 'Codec', 'Bitrate', 'Source', 'Imported', 'Playing', 'Clear Recently Played', 'Cleared Recently Played', 'Could not clear Recently Played')),
           f'Station Info: every label and word fits one line in all 13 languages, the navbar title fits, and the new texts have their translations ({over[:4]})')
    over = [(loc, StbText(font, 21).layout(built[loc]['My Stations'])[1]) for loc in pod_i18n.LOCALES if StbText(font, 21).layout(built[loc]['My Stations'])[1] > 252 - 24]
    expect(not over, f'the root row "My Stations" fits the row text in all languages ({over})')
    expect(all(pod_i18n.TEXT[k]['en_US'] == k for k in ('My Stations', 'Add to My Stations', 'Remove from My Stations', 'Added to My Stations', 'Removed from My Stations', 'Could not save My Stations', 'My Stations is full', 'Directory unavailable. Tap to try again.'))
           and not any(k in pod_i18n.TEXT for k in ('Stations', 'Add to Stations', 'Remove from Stations', 'Added to Stations', 'Removed from Stations', 'Could not save Stations', 'Stations is full', 'Directory unavailable')),
           'the renamed texts are the keys; the old ones are gone from the table')
    # ---- the icons: Lucide earth for By Country, radio-tower for the root row; the unused ones are gone
    import mod_icons
    svgs = os.path.join(ROOT, 'assets', 'icons', 'lucide', 'svg')
    expect(mod_icons.RADIO_ROWS['pod_ic_rd_country'] == 'earth' and mod_icons.RADIO_ROWS['pod_ic_rd_stations'] == 'radio-tower' and mod_icons.POD_ROWS['Radio'][1] == 'radio'
           and os.path.exists(os.path.join(svgs, 'earth.svg')) and os.path.exists(os.path.join(svgs, 'radio-tower.svg')) and not os.path.exists(os.path.join(svgs, 'flag.svg')),
           'By Country is Lucide earth, the root row radio-tower, the Pod menu row keeps radio; flag.svg is gone')


def open_tests(ctx):
    """7. The entry, the fallbacks and the root list."""
    expect = ctx.expect
    page = pod_pages.MENU
    row = next(i for i, r in enumerate(page.rows) if r.label == 'Radio')
    m = page_machine()
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * row, count=900000000)
    expect(('window_open', 'm1plus_radio') in m.calls, 'the Radio row of the menu opens the page')
    m = page_machine(window=0)
    expect(m.call(PSYMS['radio_open'], count=900000000) == 0xffffffff and 'timer_add' not in m.names(), 'a window that will not open: nothing runs')
    m = page_machine(); m.widgets.pop('sg_rail')
    open_radio(m)
    expect(('navigator_back',) in m.calls, 'an asset that is not ours: the page leaves again')
    m = opened()
    expect(m.call(PSYMS['radio_open'], count=900000000) == 0xffffffff and 'window_open' not in m.names(), 'a page already open is not opened twice')
    m.call(PSYMS['rp_on_destroy'], count=4000000)
    expect(m.destroyed >= len(ICONS) + 2, f'destroy frees the glyphs and the chevron ({m.destroyed} bitmaps)')
    # the root level
    # every glyph bitmap is white ink with alpha over nothing: cc_decode hands the ink flattened over black, which showed as a black square behind a pressed row
    m = page_machine()
    ink = bytes([255, 255, 255, 255]) * 6 + bytes([0, 0, 0, 0]) * (24 * 24 - 6)
    for n in ICONS: m.images[n] = (24, 24, ink)
    open_radio(m)
    blits, texts, fills = paint(m)
    gl = next(b for b in blits if b[2][2] == 24 and b[2][0] == 16)
    data, bw, bh = m.bitmaps[gl[0]]
    px = [struct.unpack('<I', bytes(m.u.mem_read(data + 4 * i, 4)))[0] for i in range(bw * bh)]
    expect(all(c >> 24 == 0 or c & 0xffffff == 0xffffff for c in px) and sum(c >> 24 == 255 for c in px) == 6 and sum(c >> 24 == 0 for c in px) == bw * bh - 6, 'a row glyph: white ink with its coverage as alpha, the rest clear (no black ground)')
    m = opened()
    expect(rows_text(m) == ['My Stations', 'Recently Played', 'Radio Browser'] and text_of(m, 'sg_title') == 'Radio', f'the root: three rows, the large title Radio ({rows_text(m)})')
    blits, texts, fills = paint(m)
    expect([(b[2][0], b[2][1]) for b in blits if b[2][2] == 24] == [(16, TOP + i * ROW_ROOT + 14) for i in range(3)] and len([b for b in blits if b[2][2] == 10]) == 3, 'a 24 px glyph at x 16 and a chevron on each row')
    expect([r for (t, r), s in texts if s == 'label_row_title'][0][0] == 56, 'the titles start at x 56')
    m = page_machine(); m.put_text(RECENT, '#EXTM3U\n#EXTINF:-1,Rec One\nhttp://rec.example/1\n'); open_radio(m)
    expect(rows_text(m)[0] == 'Now Playing' and len(rows_text(m)) == 4, 'Recently Played has a station: a Now Playing row first')
    m = page_machine(); m.put_text(RECENT, '#EXTM3U\n'); open_radio(m)
    expect(rows_text(m) == ['My Stations', 'Recently Played', 'Radio Browser'], 'an empty recent file (after Clear), nothing running: no Now Playing row')
    m = opened(); l, r = play(m); m.call(PSYMS['rp_on_fg'], a0=0, count=40000000)
    expect(rows_text(m)[:2] == ['Now Playing', 'My Stations'], 'a station playing: a Now Playing row first, also after the page comes back to the front')
    blits, texts, fills = paint(m)
    hair = sorted(f_[2] for f_ in fills if f_[4] == 1 and f_[1] == 56)   # the separators (x 56, 1 px high)
    ys = [TOP + 52 * i + (24 if i else 0) + 51 for i in range(4)]
    expect(hair == ys[1:] and ys[0] not in hair, f'a group of one row (Now Playing) ends without a separator, the rest keep theirs ({hair})')
    expect(vis(m, 'rd_credit') == (0, 0), 'the root has no credit (Radio Browser and the search results do)')


FAV_TEXT = ('#EXTM3U\n#M1+:Germany\tMP3\t128\n#EXTINF:-1,Fav One\nhttp://fav.example/1\n#EXTINF:-1,Fav Two\nhttps://fav.example/2\n#M1+:France\tAAC\t64\n#EXTINF:-1,Fav Three\nhttp://fav.example/3\n')
def row(name, url): return f'#EXTINF:-1,{name}\n{url}\n'.encode()
PATH_TOP = '/csv/stations/topvote/100?hidebroken=true'
QUERY = 'order=votes&reverse=true&limit=100&hidebroken=true'


def np_widgets(m):
    for w in NP_WIDGETS: Machine.widget(m, w)
    for w, t in (('rn_title', ''), ('rn_artist', '')): m.wtext[m.widgets[w]] = t


def tick(m): return m.call(PSYMS['rp_on_tick'], a0=0, count=40000000)


def click_search(m):
    """The magnifier; from the root first into Radio Browser (the root has none)."""
    if text_of(m, 'sg_title') == 'Radio': tap_row(m, 2, root=True)
    return click(m, 'btn_search')


def tap_dir(m, r):
    """Radio Browser (the root's third row, no Now Playing row), then its row r: 0 Top Stations, 1 By Country, 2 By Genre."""
    tap_row(m, 2, root=True)
    return tap_row(m, r, root=True)


def sites_of(m):
    sites = []
    m.curl_site = lambda url, o: (sites.append(url), {'body': m.answer})[1]
    return sites


def levels_tests(ctx):
    """8. The levels: favourites, recent stations, a station's tap, Back."""
    expect = ctx.expect
    m = opened()
    tap_row(m, 0, root=True)
    expect(text_of(m, 'label_status') == 'Add stations from Radio Browser or import .m3u files from the card.' and vis(m, 'label_status') == (1, 1) and vis(m, 'view_grid') == (0, 0), 'Stations with nothing in it: the grey caption, the rows hidden and insensitive')
    expect(vis(m, 'btn_more') == (1, 1) and vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_radioview') == (0, 0) and m.props.get((m.widgets['btn_more'], 'x'), 0) == 214 and icon_of(m, 'btn_backtoplayer') == 'ah_nav_play', 'the "..." stays visible (on the 214 slot, Now Playing the right cap) so Import is reachable: no Search, no toggle')
    expect(text_of(m, 'label_title') == 'My Stations' and vis(m, 'label_title')[0] == 1, 'the small title names the level')
    m.calls.clear(); click(m, 'btn_return')
    expect(vis(m, 'view_grid') == (1, 1) and vis(m, 'label_status') == (0, 0) and ('navigator_back',) not in m.calls and rows_text(m)[0] == 'My Stations', 'Back from the empty Stations: the root again, the page stays')
    expect(vis(m, 'btn_more') == (0, 0) and vis(m, 'btn_search') == (0, 0), 'the root has neither "..." nor Search')
    m = page_machine(); m.put_text(FAVS, FAV_TEXT); open_radio(m)
    tap_row(m, 0, root=True)
    expect(grid_titles(m) == ['Fav One', 'Fav Two', 'Fav Three'] and grid_subs(m) == ['Germany · MP3 128k', 'France · AAC 64k'] and text_of(m, 'sg_title') == 'My Stations',
           f'Stations: the stations as a grid, the name and the caption of each (the third cell\'s too, cut by the window: the clip cuts them) ({grid_titles(m)}, {grid_subs(m)})')
    blits, texts, fills = paint(m)
    covers = [(b[2][0], b[2][1], b[2][2]) for b in blits if b[2][2] == 144]
    expect(covers == [(12, TOP, 144), (164, TOP, 144), (12, TOP + 200, 144)] and not [b for b in blits if b[2][2] == 10], f'two columns of 144 px covers (x 12 and 164, rows 200 apart), no chevron, no "..." ({covers})')
    ts = [r for (t, r), st in texts if st == 'label_grid_title']
    ss = [r for (t, r), st in texts if st == 'label_grid_sub']
    expect(ts == [(12, TOP + 148, 144, 22), (164, TOP + 148, 144, 22), (12, TOP + 348, 144, 22)] and ss[0] == (12, TOP + 170, 144, 20), f"the Albums grid's text: the name 4 px under the cover (22 px), the caption under it (20 px) ({ts}, {ss})")
    ph = m.bitmaps[next(b[0] for b in blits if b[2][2] == 144)]
    px = lambda x, y: struct.unpack('<I', bytes(m.u.mem_read(ph[0] + 4 * (y * ph[1] + x), 4)))[0]
    expect((px(0, 0), px(20, 20), px(72, 72)) == (0xff000000, 0xff2e2c2c, 0xff938e8e), f'a station without a logo: a #2C2C2E card, the radio glyph in the middle, the corners blended into black ({px(0, 0):#x} {px(20, 20):#x} {px(72, 72):#x})')
    # a tap plays it and opens Now Playing; the page stays under it
    np_widgets(m)
    m.proc = []
    back = m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])]   # (Now Playing's page binds the same widget name in this one-window mock)
    calls = tap_cell(m, 1)
    m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])] = back
    expect(('window_open', 'm1plus_radionp') in calls and m.proc and m.proc[0][0] == 'start' and ('stop_player',) in calls, f'a tap on a station: stock stopped, the URL handed to hciplayer, Radio\'s Now Playing opens ({[c for c in calls if c[0] == "window_open"]})')
    expect(m.call(PSYMS['rd_at']) == 1 and m.call(PSYMS['rd_state']) == ST['CONNECTING'] and m.read_cstr(m.word(m.call(PSYMS['rd_list'])) + m.word(m.call(PSYMS['rd_list']) + 16 + 4)) == 'Fav Two', 'the second station plays, from a copy of the list')
    expect(RECENT in m.fs and m.fs[RECENT].split(b'\n')[1] == b'#EXTINF:-1,Fav Two', 'it is the newest recent one, first in the file')
    calls = click(m, 'btn_return')
    expect(rows_text(m)[:3] == ['Now Playing', 'My Stations', 'Recently Played'] and ('navigator_back',) not in calls, 'Back from the list: the root, with a Now Playing row now a station is up')
    m.proc = []
    destroy_np(m)   # (the page the station's tap opened is gone)
    calls = tap_row(m, 0, root=True)
    expect(('window_open', 'm1plus_radionp') in calls and not m.proc, 'the Now Playing row opens it, starting nothing')
    blits, texts, fills = paint(m)
    ys = [r[1] for (t, r), st in texts if st == 'label_row_title']
    expect(ys == [TOP + O['LIST_TITLE_Y'] * 0 + (52 - O['LIST_TITLE_H']) // 2, TOP + 52 + 24 + (52 - O['LIST_TITLE_H']) // 2, TOP + 2 * 52 + 24 + (52 - O['LIST_TITLE_H']) // 2,
                  TOP + 3 * 52 + 24 + (52 - O['LIST_TITLE_H']) // 2],
           f'the Now Playing row is a group of its own: a 24 px gap under it, the rows after it moved down ({ys})')
    expect(tap_row(m, 1, root=True) is not None and rows_text(m)[:2] == ['Now Playing', 'My Stations'], 'a touch in the gap hits no row')
    tap_row(m, 2, root=True, gap=24)
    expect(grid_titles(m) == ['Fav Two'] and text_of(m, 'sg_title') == 'Recently Played', f'Recently Played: the stations played ({grid_titles(m)})')
    # no recent stations
    m = opened()
    tap_row(m, 1, root=True)
    expect(text_of(m, 'label_status') == 'No recently played stations' and vis(m, 'btn_more') == (1, 1), 'no recently played stations: a caption, the "..." stays (Clear Recently Played)')
    # a station that does not start (a Bluetooth output) still opens Now Playing, which says why
    m = page_machine(); m.put_text(FAVS, FAV_TEXT); open_radio(m); np_widgets(m); m.out_way = 1
    tap_row(m, 0, root=True); calls = tap_cell(m, 0)
    expect(('window_open', 'm1plus_radionp') in calls and m.call(PSYMS['rd_state']) == ST['ERROR'], 'a station that cannot start leaves its reason to Now Playing')
    # the Now Playing row never starts a station: nothing active, a toast and nothing else
    def idle_row(m):
        calls = tap_row(m, 0, root=True)
        return [c[1] for c in calls if c[0] == 'toast'], ('window_open', 'm1plus_radionp') in calls, bool(m.proc)
    m = page_machine(); m.put_text(RECENT, '#EXTM3U\n#EXTINF:-1,Rec One\nhttp://rec.example/1\n'); open_radio(m); np_widgets(m)
    expect(rows_text(m)[0] == 'Now Playing' and idle_row(m) == (['No radio is playing'], False, False) and m.call(PSYMS['rd_state']) == ST['IDLE'], 'idle with a recent station: the Now Playing row toasts "No radio is playing", opens no page and starts nothing')
    m = opened(); l, r = play(m); poll(m); m.call(PSYMS['rd_stop'], count=40000000); m.proc = []
    m.call(PSYMS['rp_on_fg'], a0=0, count=40000000)
    expect(rows_text(m)[0] == 'Now Playing' and idle_row(m) == (['No radio is playing'], False, False) and m.call(PSYMS['rd_state']) == ST['STOPPED'], 'stopped: the same toast, no page, the station is not started again')
    m = page_machine(); m.put_text(FAVS, FAV_TEXT); open_radio(m); np_widgets(m); m.out_way = 1
    tap_row(m, 0, root=True)
    back = m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])]
    tap_cell(m, 0)
    m.bound[(m.widgets['btn_return'], O['EVT_CLICK'])] = back
    click(m, 'btn_return'); destroy_np(m); m.proc = []
    st_, got_ = m.call(PSYMS['rd_state']), (rows_text(m), idle_row(m))
    expect(st_ == ST['ERROR'] and got_[1] == (['No radio is playing'], False, False), f'error: the same toast, no page, no new start ({st_}, {got_})')
    # the scroll offset a level was left at comes back
    big = '#EXTM3U\n' + ''.join(f'#EXTINF:-1,S{i}\nhttp://s.example/{i}\n' for i in range(30))
    m = page_machine(); m.put_text(FAVS, big); open_radio(m)
    tap_row(m, 0, root=True)
    m.setword(m.sv + SC_YOFF, 500)
    fn, ctx_ = m.bound[(m.sv, O['EVT_SCROLL'])]; m.call(fn, a0=ctx_, a1=0, count=80000000)
    expect(vis(m, 'label_title')[0] == 1 and text_of(m, 'label_title') == 'My Stations', 'scrolled past the large title: the small one shows in the navbar')
    click(m, 'btn_return')
    expect(m.s32(m.sv + SC_YOFF) == 0, 'the root is at the top')


def directory_tests(ctx):
    """9. The directory: top stations, countries, genres, search, the failures and the cancel."""
    expect = ctx.expect
    m = opened(); m.wifi = 0
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'No Wi-Fi' and vis(m, 'view_grid') == (0, 0) and 'pthread_create' not in m.names(), 'Top Stations without Wi-Fi: "No Wi-Fi", no worker')
    click(m, 'btn_return')
    expect(rows_text(m)[0] == 'Top Stations', 'Back: Radio Browser, the level it covered')
    m = opened(); m.wall = 1_600_000_000
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Set the date first', 'a clock that was never set: "Set the date first"')
    m = opened(); m.present.discard(CA)
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.', 'no CA bundle: "Directory unavailable"')
    # Radio Browser: the directory's levels, credited
    m = opened()
    tap_row(m, 2, root=True)
    expect(rows_text(m) == ['Top Stations', 'By Country', 'By Genre'] and text_of(m, 'sg_title') == 'Radio Browser' and vis(m, 'rd_credit') == (1, 1) and m.props[(m.widgets['rd_credit'], 'x')] == 56
           and m.props[(m.widgets['rd_credit'], 'y')] == TOP + 3 * 52 + 12, 'Radio Browser: Top Stations, By Country, By Genre, the credit 12 px under the last row at the text inset')
    # Top Stations
    m = opened(); m.answer = TOP_CSV.encode()
    sites = sites_of(m)
    calls = tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Loading…' and ('timer_add', PSYMS['rp_on_tick'], 250) in calls and 'pthread_create' in [c[0] for c in calls], 'a tap on Top Stations: Loading…, one worker, the 250 ms page timer')
    expect(tick(m) == 8, 'the timer repeats while the worker runs')
    finish(m)
    r = tick(m)
    expect(r == 0 and sites == ['https://all.api.radio-browser.info' + PATH_TOP] and grid_titles(m) == ['Alpha FM', 'Beta Radio'] and grid_subs(m) == ['Germany · MP3 128k', 'France · AAC 64k']
           and text_of(m, 'sg_title') == 'Top Stations' and vis(m, 'view_grid') == (1, 1), f'the answer: the stations in the grid, their captions, the title ({grid_titles(m)}, {grid_subs(m)})')
    expect(vis(m, 'rd_credit') == (0, 0) and vis(m, 'sg_rail')[0] == 0, 'Top Stations: no credit, no rail')
    expect(tick(m) == 0, 'the timer is gone with the work')
    click(m, 'btn_return')
    expect(rows_text(m)[0] == 'Top Stations' and text_of(m, 'sg_title') == 'Radio Browser', 'Back from the list: Radio Browser')
    # Back while loading: the transfer is cancelled, the root is back, a late tick does nothing
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    tap_dir(m, 0)
    calls = click(m, 'btn_return')
    expect(vis(m, 'view_grid') == (1, 1) and rows_text(m)[0] == 'Top Stations' and ('timer_remove', 0x777) in calls and ('navigator_back',) not in calls, 'Back while Loading: Radio Browser, the timer removed, the page stays')
    finish(m)
    expect(tick(m) == 0 and vis(m, 'view_grid') == (1, 1) and rows_text(m)[0] == 'Top Stations', 'the cancelled worker ends: nothing reaches the page')
    tap_row(m, 0, root=True)
    expect(text_of(m, 'label_status') == 'Loading…', 'and a new fetch starts at once')
    # a failure: the caption, and Back to the level it covered
    m = opened(); m.curl_site = lambda url, o: {'rc': 60}
    tap_dir(m, 0); finish(m); tick(m)
    expect(text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.' and vis(m, 'view_grid') == (0, 0), 'a failed fetch: "Directory unavailable"')
    click(m, 'btn_return')
    expect(rows_text(m)[0] == 'Top Stations' and text_of(m, 'sg_title') == 'Radio Browser', 'Back: the level it covered')
    # an answer with no station
    m = opened(); m.answer = b'changeuuid,name,url\n'; sites_of(m)
    tap_dir(m, 0); finish(m); tick(m)
    expect(text_of(m, 'label_status') == 'No stations', 'an answer with nothing in it: "No stations"')
    # one worker at a time
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    m.call(PSYMS['rd_fetch'], a0=m.buf(PATH_TOP), a1=1, count=40000000)
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Loading…' and m.names().count('pthread_create') == 0, 'a fetch already running: the page waits on its timer, no second worker')
    for _ in range(31): tick(m)
    expect(text_of(m, 'label_status') == 'Loading…', 'about eight seconds of asking again')
    expect(tick(m) == 0 and text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.', 'then it gives up: "Directory unavailable"')
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    r = m.call(PSYMS['rd_logo_start'], a0=m.buf('https://logo.example/a.png'), count=40000000)
    tap_dir(m, 0)
    expect(r == 1 and text_of(m, 'label_status') == 'Loading…' and m.names().count('pthread_create') == 0, 'a logo job in the way: cancelled, the fetch waits for it')
    finish(m)   # the logo worker ends
    tick(m)
    expect(m.names().count('pthread_create') == 1, 'and starts when the logo worker has ended')
    # countries: the Genres page's A-Z list
    m = opened(); m.answer = COUNTRIES_CSV.encode(); sites = sites_of(m)
    tap_dir(m, 1); finish(m); tick(m)
    names = ['Austria', 'France', 'The Gambia', 'Germany']
    expect(sites == ['https://all.api.radio-browser.info/csv/countries?order=name&hidebroken=true'] and rows_text(m) == names and text_of(m, 'sg_title') == 'Countries',
           f'By Country: every country with stations (Andorra has none), A-Z by name with "The" dropped ({rows_text(m)})')
    sec = [0, 1, 2, 2]   # A, F, G, G
    ys = [52 + (sec[i] + 1) * 28 + i * 52 for i in range(4)]
    blits, texts, fills = paint(m)
    ts = [r for (t, r), st in texts if st == 'label_row_title']
    expect(ts == [(24, y + (52 - O['LIST_TITLE_H']) // 2, 252 - 24, O['LIST_TITLE_H']) for y in ys] and rows_text(m, 'label_row_sub') == [], f"the rows are the Genres page's: 52 px, the name at x 24 to 252, no count ({ts})")
    expect(sorted(set(rows_text(m, 'label_hdr'))) == ['A', 'F', 'G'] and [(b[2][0], b[2][1]) for b in blits if b[2][2] == 10] == [(262, y + 18) for y in ys], 'section letters A, F, G (The Gambia files under G) and the chevron at x 262')
    expect(sorted(f_[2] for f_ in fills if f_[0] == 0xff222222 and f_[4] == 1) == sorted(y + 51 for y in ys), 'the #222222 hairlines')
    expect(vis(m, 'sg_rail') == (1, 1), 'the A-Z rail is there')
    expect(vis(m, 'rd_credit') == (0, 0), 'By Country: no credit')
    m.answer = TOP_CSV.encode()
    calls = tap(m, 100, ys[3] + 20); finish(m); tick(m)
    expect(sites[1] == f'https://all.api.radio-browser.info/csv/stations/bycountrycodeexact/DE?{QUERY}' and text_of(m, 'sg_title') == 'Germany' and grid_titles(m) == ['Alpha FM', 'Beta Radio'],
           f"a country: its stations by the code, the title is its name ({sites[1:]})")
    expect(vis(m, 'rd_credit') == (0, 0), "a country's stations: no credit")
    click(m, 'btn_return')
    expect(rows_text(m) == names and text_of(m, 'sg_title') == 'Countries' and vis(m, 'sg_rail') == (1, 1), 'Back: the countries and the rail')
    click(m, 'btn_return')
    expect(rows_text(m) == ['Top Stations', 'By Country', 'By Genre'] and text_of(m, 'sg_title') == 'Radio Browser' and vis(m, 'sg_rail')[0] == 0, 'and Radio Browser, the rail gone')
    click(m, 'btn_return')
    expect(rows_text(m)[0] == 'My Stations' and text_of(m, 'sg_title') == 'Radio', 'and the root')
    # genres, with a tag that needs escaping
    m = opened(); m.answer = ('name,stationcount\ndrum, bass,5\n"drum, bass",12\nrock,3\n').encode(); sites = sites_of(m)
    tap_dir(m, 2); finish(m); tick(m)
    expect(sites == ['https://all.api.radio-browser.info/csv/tags?order=stationcount&reverse=true&limit=60'] and text_of(m, 'sg_title') == 'Genres', 'By Genre: the tags')
    expect(vis(m, 'rd_credit') == (0, 0), 'By Genre: no credit')
    m.answer = TOP_CSV.encode()
    names_ = rows_text(m)
    tap_row(m, names_.index('drum, bass')); finish(m); tick(m)
    expect(sites[1] == f'https://all.api.radio-browser.info/csv/stations/bytagexact/drum%2C%20bass?{QUERY}' and text_of(m, 'sg_title') == 'drum, bass', f'a genre: its stations by tag, %-escaped ({sites[1]})')
    expect(vis(m, 'rd_credit') == (0, 0), "a genre's stations: no credit")

def search_tests(ctx):
    """10a. Search in the page: the field and the pad, the results below the field, Back."""
    expect = ctx.expect
    m = opened(); m.answer = TOP_CSV.encode(); sites = sites_of(m)
    calls = click_search(m)
    expect(('window_open', 'm1plus_keyboard') not in calls and vis(m, 'kb_field') == (1, 1) and vis(m, 'btn_search') == (0, 0) and vis(m, 'sg_title')[0] == 0 and text_of(m, 'label_title') == 'Search Stations'
           and vis(m, 'label_title')[0] == 1, 'the magnifier: the search page in this page, the field under the navbar, no separate window')
    expect(m.props[(m.lv, 'h')] == 400 - 180 and m.props[(m.sv, 'h')] == 400 - 180 and grid_titles(m) == [], 'the list stops above the pad; no rows yet')
    expect(m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_np', 'Now Playing is the glass disc alone while the left cap is away')
    m.call(PSYMS['keyboard_set_text'], a0=m.buf('jazz fm'), count=4000000)
    m.calls.clear(); m.call(PSYMS['rp_on_go'], count=40000000)
    expect(text_of(m, 'label_status') == 'Loading…' and m.props[(m.lv, 'h')] == 400, 'the action key: Loading…, the pad goes, the list has its height back')
    finish(m); tick(m)
    expect(sites == [f'https://all.api.radio-browser.info/csv/stations/byname/jazz%20fm?{QUERY}'] and grid_titles(m) == ['Alpha FM', 'Beta Radio'] and vis(m, 'kb_field') == (1, 1) and vis(m, 'sg_title')[0] == 0,
           f'the results of "jazz fm" below the field, no separate list page ({sites})')
    expect(m.props[(m.widgets['rd_credit'], 'y')] == 48 + 200 - 10 + 12 and m.props[(m.widgets['rd_credit'], 'x')] == 12 and vis(m, 'rd_credit') == (1, 1), 'the directory is credited under the search results')
    blits, texts, fills = paint(m)
    expect([r for (t, r), s in texts if s == 'label_grid_title'][0][1] == 48 + 148, 'the grid starts under the field (48), not under a large title')
    # a result plays
    m2 = opened(); m2.answer = TOP_CSV.encode(); sites_of(m2)
    click_search(m2); m2.call(PSYMS['keyboard_set_text'], a0=m2.buf('x'), count=4000000); m2.call(PSYMS['rp_on_go'], count=40000000); finish(m2); tick(m2)
    np_widgets(m2)
    back = m2.bound[(m2.widgets['btn_return'], O['EVT_CLICK'])]
    m2.proc = []
    calls = tap(m2, 164 + 20, 48 + 20)
    expect(m2.proc[:1] and m2.proc[0][0] == 'start' and ('window_open', 'm1plus_radionp') in calls and m2.call(PSYMS['rd_at']) == 1, 'a tap on a result plays it and opens Now Playing, from the search page')
    m2.bound[(m2.widgets['btn_return'], O['EVT_CLICK'])] = back
    # Back leaves the search for the level it began on; Back from the Loading caption stays in the search
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    click_search(m); m.call(PSYMS['keyboard_set_text'], a0=m.buf('y'), count=4000000); m.call(PSYMS['rp_on_go'], count=40000000)
    calls = click(m, 'btn_return')
    expect(vis(m, 'kb_field') == (1, 1) and vis(m, 'label_status') == (0, 0) and vis(m, 'view_grid') == (1, 1) and ('navigator_back',) not in calls, 'Back while Loading: still the search page, the transfer cancelled')
    calls = click(m, 'btn_return')
    expect(vis(m, 'kb_field') == (0, 0) and vis(m, 'btn_search') == (1, 1) and rows_text(m)[0] == 'Top Stations' and vis(m, 'sg_title')[0] == 1 and ('navigator_back',) not in calls
           and m.props[(m.lv, 'h')] == 400 and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_play', 'Back from the search page: the level it began on, the field and the pad gone, the capsule back')
    # an empty field: the action key does nothing; a tap on the field brings the pad back
    m = opened(); m.answer = TOP_CSV.encode(); sites = sites_of(m)
    click_search(m)
    m.call(PSYMS['rp_on_go'], count=40000000)
    expect(not sites and 'pthread_create' not in m.names() and text_of(m, 'label_status') != 'Loading…', 'an empty query searches nothing')
    m.call(PSYMS['keyboard_set_text'], a0=m.buf('z'), count=4000000)
    m.call(PSYMS['rp_on_go'], count=40000000)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev, O['EVT_POINTER_UP'])
    fn, ctx_ = m.bound[(m.widgets['kb_field'], O['EVT_POINTER_UP'])]
    m.call(fn, a0=ctx_, a1=ev, count=40000000)
    expect(m.props[(m.lv, 'h')] == 400 - 180, 'a tap on the field: the pad is back, the list is short again')
    # a failure in the search: the caption, Back to the search page
    m = opened(); m.curl_site = lambda url, o: {'rc': 60}
    click_search(m); m.call(PSYMS['keyboard_set_text'], a0=m.buf('q'), count=4000000); m.call(PSYMS['rp_on_go'], count=40000000)
    finish(m); tick(m)
    expect(text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.', 'a failed search: the caption')
    click(m, 'btn_return')
    expect(vis(m, 'kb_field') == (1, 1) and vis(m, 'view_grid') == (1, 1), 'Back: the search page again')

    search_back_tests(ctx)


def search_back_tests(ctx):
    """Back from the search page returns to exactly the level it began on: its rows, the offset, the title, the navbar and the credit, whether or not results came."""
    expect = ctx.expect
    def shot(m): return (grid_titles(m), rows_text(m), text_of(m, 'sg_title'), get_off(m), vis(m, 'rd_credit'), vis(m, 'btn_radioview'), vis(m, 'btn_search'), vis(m, 'sg_rail'), vis(m, 'kb_field'),
                         m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')))
    def search(m, results):
        click_search(m)
        if results:
            m.answer = TOP_CSV.encode(); sites_of(m)
            m.call(PSYMS['keyboard_set_text'], a0=m.buf('x'), count=4000000); m.call(PSYMS['rp_on_go'], count=40000000); finish(m); tick(m)
            expect(grid_titles(m) == ['Alpha FM', 'Beta Radio'], 'the results replaced the level on the search page')
        else:
            expect(grid_titles(m) == [], 'the search page, no results yet')
    def levels():
        def country():
            m = opened(); m.answer = COUNTRIES_CSV.encode(); sites_of(m); tap_dir(m, 1); finish(m); tick(m)
            m.answer = stations_csv(40).encode(); tap(m, 100, 292 + 20); finish(m); tick(m); return m
        def top():
            m = opened(); top_stations(m, 40); return m
        def genre():
            m = opened(); m.answer = ('name,stationcount\nrock,3\njazz,2\n').encode(); sites_of(m); tap_dir(m, 2); finish(m); tick(m)
            m.answer = stations_csv(40).encode(); tap_row(m, 0); finish(m); tick(m); return m
        def browser():
            m = opened(); tap_row(m, 2, root=True); return m
        return (('a country', country, 150), ('Top Stations', top, 150), ('a genre', genre, 150), ('Radio Browser', browser, 0))
    for name, make, off in levels():
        for results in (True, False):
            m = make()
            if off: set_off(m, off)
            before = shot(m)
            expect(before[0] or before[1], f'{name}: a level with rows to compare')
            search(m, results)
            click(m, 'btn_return')
            expect(shot(m) == before, f"Back from the search {'results' if results else 'before any results'}: {name} as it was, rows, offset {off}, title, credit and navbar ({before[:5]} / {shot(m)[:5]})")
            search(m, results)
            click(m, 'btn_return')
            expect(shot(m) == before, f'{name}: and a second search and Back')


def logo_tests(ctx):
    """10b. Station logos: the favicon in the CSV, the worker, the cache, the rows and Now Playing."""
    expect = ctx.expect
    m = machine()
    fav = m.malloc(256)
    expect(m.call(PSYMS['rd_favicon'], a0=m.buf('Germany\tMP3\t128\thttps://l.example/a.png'), a1=fav, a2=256, count=100000) == 1 and m.read_cstr(fav) == 'https://l.example/a.png', 'the favicon is the fourth field of the info')
    for info in ('Germany\tMP3\t128', 'Germany\tMP3\t128\t', 'a\tb\tc\tftp://x.example/a.ico', '\t\t\tfile:///etc/x', ''):
        expect(m.call(PSYMS['rd_favicon'], a0=m.buf(info), a1=fav, a2=256, count=100000) == 0 and m.read_cstr(fav) == '', f'no favicon in {info!r}')
    header = 'name,url,url_resolved,favicon,country,codec,bitrate\n'
    csv = header + 'A,http://a.example/s,,https://l.example/a.png,DE,MP3,128\nB,http://b.example/s,,ftp://l.example/b.ico,DE,MP3,128\nC,http://c.example/s,,' + 'http://x/' + 'y' * 300 + ',DE,MP3,128\nD,http://d.example/s,,,DE,MP3,128\n'
    l = new_list(m, csv, 1)
    buf = m.word(l); info = lambda i: m.read_cstr(buf + m.word(l + 16 + 8 * MAXL + 4 * i))
    expect([info(i) for i in range(4)] == ['DE\tMP3\t128\thttps://l.example/a.png', 'DE\tMP3\t128\t', 'DE\tMP3\t128\t', 'DE\tMP3\t128\t'], 'the CSV: only an http(s) address of at most 200 bytes is kept')
    # it survives a favourite
    m.fs.pop(FAVS, None)
    m.call(PSYMS['rd_fav_toggle'], a0=l, a1=0, count=40000000)
    expect(b'#M1+:DE\tMP3\t128\thttps://l.example/a.png\n' in m.fs[FAVS], 'a favourite keeps its logo address in its #M1+: line')
    out = new_list(m)
    m.call(PSYMS['rd_favs_read'], a0=out, a1=0, count=40000000)
    expect(m.read_cstr(m.word(out) + m.word(out + 16 + 8 * MAXL)) == 'DE\tMP3\t128\thttps://l.example/a.png', 'and reads it back')
    # the cache's states
    h = m.call(PSYMS['rd_logo_hash'], a0=m.buf('https://l.example/a.png'), count=100000)
    path = m.malloc(64)
    expect(m.call(PSYMS['rd_logo_file'], a0=h, a1=path, a2=64, count=100000) == 0 and m.read_cstr(path) == f'{RADIO_DIR}/.logos/{h:08x}.jpg', 'not tried: 0, the file is under Radio/.logos')
    m.put(f'{RADIO_DIR}/.logos/{h:08x}.no', b'')
    expect(m.call(PSYMS['rd_logo_file'], a0=h, a1=path, a2=64, count=100000) == 0xffffffff, 'a .no file: -1')
    m.put(f'{RADIO_DIR}/.logos/{h:08x}.jpg', b'x')
    expect(m.call(PSYMS['rd_logo_file'], a0=h, a1=path, a2=64, count=100000) == 1, 'a made logo: 1')
    # the worker
    url = 'https://l.example/b.png'
    h2 = m.call(PSYMS['rd_logo_hash'], a0=m.buf(url), count=100000)
    start = lambda m, u: m.call(PSYMS['rd_logo_start'], a0=m.buf(u), count=40000000)
    def run_logo(site, u=url, **kw):
        mm = machine()
        for k, v in kw.items(): setattr(mm, k, v)
        mm.curl_site = site
        r = start(mm, u)
        calls = list(mm.calls)
        if r: finish(mm)
        return mm, r, calls
    got = []
    mm, r, calls = run_logo(lambda u, o: (got.append(dict(o)), {'body': b'GIF89a......', 'ctype': 'image/gif'})[1])
    hh = h2
    expect(r == 1 and 'pthread_create' in [c[0] for c in calls], 'a logo job starts one worker')
    o = got[0]
    expect(o[10002] == url and o[10065] == CA and o[78] == 5 and o[13] == 10 and o[68] == 3 and o[181] == 3 and o[45] == 1 and o[99] == 1 and 64 not in o and 81 not in o and 20219 in o,
           'its request: the CA bundle, 5 s to connect, 10 s in all, 3 redirects limited to http(s), HTTP errors fail, verification on')
    mm.call(PSYMS['rd_logo_running'], count=100000)
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.no' in mm.fs and f'{RADIO_DIR}/.logos/{hh:08x}.jpg' not in mm.fs and mm.call(PSYMS['rd_logo_file'], a0=hh, a1=path, a2=64, count=100000) == 0xffffffff
           and mm.call(PSYMS['rd_logo_running'], count=100000) == 0 and '/tmp/m1plus-logo.src' not in mm.fs, 'a GIF (or an ICO, an SVG, a page): not decodable here, a .no file, the source removed, the worker joined')
    mm, r, calls = run_logo(lambda u, o: {'code': 404, 'rc': 22})
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.no' in mm.fs, 'an HTTP error: a .no file')
    mm, r, calls = run_logo(lambda u, o: {'rc': 6})
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.no' not in mm.fs and mm.call(PSYMS['rd_logo_file'], a0=hh, a1=path, a2=64, count=100000) == 0xffffffff, 'a network failure: no file, but not tried again this session')
    big = b'\xff\xd8\xff' + bytes(300000)
    mm, r, calls = run_logo(lambda u, o: {'body': big, 'chunk': 65536})
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.no' in mm.fs, 'a body over 256 KB is cut: a .no file')
    from PIL import Image
    import io
    b = io.BytesIO(); Image.new('RGB', (64, 64), (200, 30, 30)).save(b, 'JPEG')
    mm, r, calls = run_logo(lambda u, o: {'body': b.getvalue()})
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.jpg' in mm.fs and f'{RADIO_DIR}/.logos/{hh:08x}.tmp' not in mm.fs and mm.call(PSYMS['rd_logo_file'], a0=hh, a1=path, a2=64, count=100000) == 1,
           'a JPEG: shrunk by the podcast cover code into <hash>.jpg (through a .tmp)')
    b = io.BytesIO(); Image.new('RGBA', (32, 32), (10, 200, 30, 255)).save(b, 'PNG')
    mm, r, calls = run_logo(lambda u, o: {'body': b.getvalue()})
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.jpg' in mm.fs, 'a PNG: the same')
    # the guards
    for what, kw in (('no Wi-Fi', {'wifi': 0}), ('a clock never set', {'wall': 1_600_000_000}), ('the card not mounted', {'card_mounted': False})):
        mm, r, calls = run_logo(lambda u, o: {'body': b'x'}, **kw)
        expect(r == 0 and 'pthread_create' not in [c[0] for c in calls], f'{what}: no logo job')
    mm = machine(); mm.present.discard(CA)
    expect(start(mm, url) == 0, 'no CA bundle: no logo job')
    mm = machine(); mm.put(f'{RADIO_DIR}/.logos/{hh:08x}.no', b'')
    expect(start(mm, url) == 0 and start(mm, 'ftp://x.example/a.ico') == 0 and start(mm, '') == 0, 'a logo that is known to be missing, a bad address, none: nothing started')
    mm = machine(); mm.curl_site = lambda u, o: {'body': b'x'}
    expect(start(mm, url) == 1 and start(mm, 'https://l.example/c.png') == 0, 'one logo at a time')
    # a fresh card has no Radio/ (the card refuses files beneath a missing folder): the worker makes Radio/ and .logos/ itself
    mm = machine(); mm.dirs.discard(RADIO_DIR); mm.curl_site = lambda u, o: {'body': b.getvalue()}
    b = io.BytesIO(); Image.new('RGB', (64, 64), (200, 30, 30)).save(b, 'JPEG')
    start(mm, url); finish(mm); made = [c for c in mm.calls if c[0] == 'mkdir']; mm.call(PSYMS['rd_logo_running'], count=100000)
    expect(f'{RADIO_DIR}/.logos/{hh:08x}.jpg' in mm.fs and mm.call(PSYMS['rd_logo_file'], a0=hh, a1=path, a2=64, count=100000) == 1 and made == [('mkdir', RADIO_DIR), ('mkdir', f'{RADIO_DIR}/.logos')],
           'a fresh card without Radio/: the JPEG logo is cached all the same (Radio/ made before .logos/)')
    # a card that refuses the .no marker: no new download this session for any logo (not 16 and then again); cached ones still answer 1
    nopath = f'{RADIO_DIR}/.logos/{hh:08x}.no'
    mm, r, calls = run_logo(lambda u, o: {'code': 404, 'rc': 22}, fail={('open', nopath)})
    others = [0x1000 + i for i in range(20)]
    mm.put(f'{RADIO_DIR}/.logos/{0x77:08x}.jpg', b'x')
    expect(nopath not in mm.fs and mm.call(PSYMS['rd_logo_file'], a0=hh, a1=path, a2=64, count=100000) == 0xffffffff
           and all(mm.call(PSYMS['rd_logo_file'], a0=o_, a1=path, a2=64, count=100000) == 0xffffffff for o_ in others) and mm.call(PSYMS['rd_logo_file'], a0=0x77, a1=path, a2=64, count=100000) == 1,
           'the card refuses the marker: -1 for that logo and for 20 never-fetched others, a cached one is still 1')
    # the cache is bounded
    mm = machine()
    for i in range(401): mm.put(f'{RADIO_DIR}/.logos/{i:08x}.jpg', b'x')
    mm.curl_site = lambda u, o: {'body': b'GIF89a'}
    start(mm, url); finish(mm); mm.call(PSYMS['rd_logo_running'], count=100000)
    left = [p_ for p_ in mm.fs if p_.startswith(f'{RADIO_DIR}/.logos/')]
    expect(len(left) <= 1, f'past 400 files the folder is emptied before the next logo is kept ({len(left)} left)')
    # the directory fetch is not made to wait behind more than a transfer callback
    mm = machine(); mm.curl_site = lambda u, o: {'body': b'x'}
    start(mm, url)
    r = mm.call(PSYMS['rd_fetch'], a0=mm.buf(PATH_TOP), a1=1, count=40000000)
    expect(r == E['BUSY'], 'a directory fetch asked while a logo job runs: cancels it and answers busy (the page asks again)')
    finish(mm)
    r = mm.call(PSYMS['rd_fetch'], a0=mm.buf(PATH_TOP), a1=1, count=40000000)
    expect(r == 0, 'and starts once the logo worker has ended')
    # a logo job is not started while the directory fetch runs
    mm = machine(); mm.curl_site = lambda u, o: {'body': TOP_CSV.encode()}
    mm.call(PSYMS['rd_fetch'], a0=mm.buf(PATH_TOP), a1=1, count=40000000)
    expect(start(mm, url) == 0, 'no logo job beside the directory fetch')

    # ---- the rows: a made logo is the row's cover, a missing one the radio glyph, the worker starts for the first row in view
    csv = header + 'Alpha,http://a.example/s,,https://l.example/a.png,DE,MP3,128\nBeta,http://b.example/s,,https://l.example/b.png,DE,MP3,128\nGamma,http://c.example/s,,,DE,MP3,128\n'
    m = opened(); m.answer = csv.encode(); sites_of(m)
    ha = m.call(PSYMS['rd_logo_hash'], a0=m.buf('https://l.example/a.png'), count=100000)
    m.put(f'{RADIO_DIR}/.logos/{ha:08x}.jpg', jpeg_header(52))
    m.images[f'file://{RADIO_DIR}/.logos/{ha:08x}.jpg'] = (52, 52, struct.pack('<I', 0xff2233ee) * (52 * 52))
    tap_dir(m, 0); finish(m); tick(m)
    m.sizes[f'{RADIO_DIR}/.logos/{ha:08x}.jpg'] = 4000
    ltick = lambda: m.call(PSYMS['rp_on_ltick'], a0=0, count=400000000)
    m.screen(True); m.top_main = m.window
    paint(m)
    expect(ltick() == 8 and any(c[0] == 'widget_load_image' or c[0] == 'bitmap_create_ex' for c in m.calls), 'the page\'s logo timer decodes the made logo of the first row, one a tick')
    blits, texts, fills = paint(m)
    cv = [b_ for b_ in blits if b_[2][2] == 144]
    expect(len(cv) >= 2 and cv[0][2][:2] == (12, TOP) and cv[0][0] != cv[1][0], 'the logo is the first tile\'s cover (144 px at x 12), its own bitmap, the next tile still the placeholder')
    ltick()
    expect(m.names().count('pthread_create') == 1, 'the second tile has none yet: the logo worker starts for it (one job)')
    expect(ltick() == 8, 'a tick with the worker running waits')
    finish(m)
    ltick(); paint(m)
    # the timer rests while the screen is dark or the page is covered or the list moves
    m2 = opened(); m2.answer = csv.encode(); sites_of(m2)
    tap_dir(m2, 0); finish(m2); tick(m2)
    m2.screen(False); m2.top_main = m2.window
    m2.call(PSYMS['rp_on_ltick'], a0=0, count=400000000)
    expect(m2.names().count('pthread_create') == 0, 'a dark screen: the logo timer starts no job')
    m2.screen(True); m2.top_main = 0
    m2.call(PSYMS['rp_on_ltick'], a0=0, count=400000000)
    expect(m2.names().count('pthread_create') == 0, 'the page covered: none either')
    expect(m2.call(PSYMS['rp_on_destroy'], count=4000000) is not None and m2.call(PSYMS['rp_on_ltick'], a0=0, count=4000000) == 0, 'after the page is gone the timer ends')


def favs_tests(ctx):
    """10. The station grid has no per-station sheet; Stations follows Now Playing's sheet; the root's Back; the "..." sheet (Import from Card)."""
    expect = ctx.expect
    m = page_machine(); m.put_text(FAVS, FAV_TEXT); open_radio(m); np_widgets(m)
    tap_row(m, 0, root=True)
    expect(grid_titles(m) == ['Fav One', 'Fav Two', 'Fav Three'], 'Stations: the stations')
    m.proc = []
    calls = tap_cell(m, 1)
    expect(('window_open', 'm1plus_radionp') in calls and m.call(PSYMS['rd_at']) == 1, 'a tap anywhere on a tile plays it (the right edge too: there is no "...")')
    destroy_np(m)
    # Stations is changed on Now Playing's sheet: the list on the page under it follows when the page comes back
    m.call(PSYMS['rd_fav_toggle'], a0=m.call(PSYMS['rd_list']), a1=1, count=40000000)
    m.call(PSYMS['rp_on_fg'], a0=0, count=40000000)
    expect(grid_titles(m) == ['Fav One', 'Fav Three'] and b'Fav Two' not in m.fs[FAVS], f'the page coming back to the front reads Stations again: the removed station is gone ({grid_titles(m)})')
    # every station removed: the level stays, with its hint and the "..."
    for i in (1, 0):
        l = new_list(m); m.call(PSYMS['rd_favs_read'], a0=l, count=40000000)
        m.call(PSYMS['rd_fav_toggle'], a0=l, a1=i, count=40000000)
    m.call(PSYMS['rp_on_fg'], a0=0, count=40000000)
    expect(text_of(m, 'label_status') == 'Add stations from Radio Browser or import .m3u files from the card.' and vis(m, 'btn_more') == (1, 1) and vis(m, 'view_grid') == (0, 0), 'with none left: the hint over an empty Stations, the "..." still there')
    # Recently Played is not Stations: no reread
    m = page_machine(); m.put_text(RECENT, '#EXTM3U\n#EXTINF:-1,Rec One\nhttp://rec.example/1\n'); open_radio(m)
    tap_row(m, 2, root=True, gap=24)
    m.call(PSYMS['rp_on_fg'], a0=0, count=40000000)
    expect(grid_titles(m) == ['Rec One'], 'Recently Played stays as it is')
    # the root's Back leaves the page
    m = opened(); m.calls.clear(); click(m, 'btn_return')
    expect(('navigator_back',) in m.calls, 'Back at the root closes the page')
    # the card files are not read live: Stations is favourites.m3u only, every row a station row
    for view, subs in ((None, lambda m: rows_text(m, 'label_row_sub')), (b'1\n', grid_subs)):
        m = page_machine(view=view); m.put_text(FAVS, FAV_TEXT.split('#EXTINF:-1,Fav Two')[0]); m.put_text(RADIO_DIR + '/jazz.m3u', '#EXTM3U\n#M1+:Italy\tMP3\t64\n#EXTINF:-1,Jazz One\nhttp://jazz.example/1\n')
        open_radio(m); np_widgets(m); tap_row(m, 0, root=True)
        titles = rows_text(m) if view is None else grid_titles(m)
        expect(titles == ['Fav One'] and subs(m) == ['Germany · MP3 128k'], f'{"list" if view is None else "grid"}: only favourites.m3u is listed, with its info line, no file name ({titles}, {subs(m)})')
    m = page_machine(view=None); m.put_text(FAVS, FAV_TEXT); m.put_text(RADIO_DIR + '/jazz.m3u', '#EXTM3U\n#EXTINF:-1,Jazz One\nhttp://jazz.example/1\n')
    open_radio(m); np_widgets(m); tap_row(m, 0, root=True)
    tap_row(m, 0)
    m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(vis(m, 'rn_more') == (1, 1), 'Now Playing: the "..." is there for every station')
    destroy_np(m)
    # ---- the "..." sheet and Import from Card
    toasts = lambda calls: [c[1] for c in calls if c[0] == 'toast']
    m = page_machine(view=None); m.put_text(FAVS, FAV_TEXT); m.put_text(RADIO_DIR + '/jazz.m3u', '#EXTM3U\n#EXTINF:-1,Jazz One\nhttp://jazz.example/1\n#EXTINF:-1,Fav Dup\nhttp://fav.example/1\n')
    open_radio(m); np_widgets(m); tap_row(m, 0, root=True)
    calls = click(m, 'btn_more')
    expect(vis(m, 'rd_sh_card') == (1, 1) and vis(m, 'rd_sh_scrim') == (1, 1) and vis(m, 'rd_sh_import') == (1, 1) and vis(m, 'rd_sh_import_hr')[0] == 0 and m.props.get((m.widgets['rd_sh_clear'], 'visible'), 0) == 0
           and m.props.get((m.widgets['rd_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1' , 'the "..." opens the sheet: one row (one sheet-high card, no hairline)')
    m.calls.clear(); click(m, 'btn_return')
    expect(vis(m, 'rd_sh_card') == (0, 0) and ('navigator_back',) not in m.calls and rows_text(m) == ['Fav One', 'Fav Two', 'Fav Three'], 'Back with the sheet open closes the sheet only')
    click(m, 'btn_more'); click(m, 'rd_sh_scrim')
    expect(vis(m, 'rd_sh_card') == (0, 0) and vis(m, 'rd_sh_import') == (0, 0) and b'Jazz One' not in m.fs[FAVS], 'the scrim closes it; nothing imported')
    click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['Added 1 station'] and rows_text(m) == ['Fav One', 'Fav Two', 'Fav Three', 'Jazz One'] and b'Jazz One' in m.fs[FAVS] and vis(m, 'rd_sh_card') == (0, 0),
           f'Import from Card: "Added 1 station", the sheet closed, the list refreshed in place with the new station last ({toasts(calls)}, {rows_text(m)})')
    click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['No new stations'] and rows_text(m)[-1] == 'Jazz One', f'again: "No new stations" ({toasts(calls)})')
    m.fs.pop(RADIO_DIR + '/jazz.m3u'); click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['No playlists in the Radio folder'], f'no playlist file: "No playlists in the Radio folder" ({toasts(calls)})')
    m.put_text(RADIO_DIR + '/two.m3u', '#EXTM3U\n#EXTINF:-1,T1\nhttp://t.example/1\n#EXTINF:-1,T2\nhttp://t.example/2\n')
    m.card_mounted = False; click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['Could not save My Stations'], f'no card: the save-failure message ({toasts(calls)})')
    m.card_mounted = True; click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['Added 2 stations'] and m.fs[FAVS].endswith(row('T1', 'http://t.example/1') + row('T2', 'http://t.example/2')), f'two stations: "Added 2 stations" ({toasts(calls)})')
    # an empty Stations imports too, and its caption goes
    m = page_machine(view=None); m.put_text(RADIO_DIR + '/two.m3u', '#EXTM3U\n#EXTINF:-1,T1\nhttp://t.example/1\n#EXTINF:-1,T2\nhttp://t.example/2\n')
    open_radio(m); tap_row(m, 0, root=True)
    expect(vis(m, 'label_status') == (1, 1), 'an empty Stations')
    click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['Added 2 stations'] and rows_text(m) == ['T1', 'T2'] and vis(m, 'label_status') == (0, 0) and vis(m, 'view_grid') == (1, 1) and vis(m, 'btn_radioview') == (1, 1),
           f'Import into an empty Stations: the stations, no caption, the toggle ({toasts(calls)}, {rows_text(m)})')
    # the cap
    m = page_machine(view=None); m.put_text(FAVS, '#EXTM3U\n' + ''.join(f'#EXTINF:-1,F{i}\nhttp://f.example/{i}\n' for i in range(300)))
    m.put_text(RADIO_DIR + '/two.m3u', '#EXTM3U\n#EXTINF:-1,T1\nhttp://t.example/1\n')
    open_radio(m); tap_row(m, 0, root=True); click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_import')
    expect(toasts(calls) == ['My Stations is full'] and b'http://t.example/1' not in m.fs[FAVS], f'at the cap: "Stations is full", nothing added ({toasts(calls)})')
    # no "..." on Radio Browser
    m = page_machine(view=None); open_radio(m)
    tap_row(m, 2, root=True)
    expect(vis(m, 'btn_more') == (0, 0), 'Radio Browser has no "..."')
    recent_tests(ctx)


def recent_tests(ctx):
    """Recently Played has My Stations' "..." and a sheet with one row, Clear Recently Played."""
    expect = ctx.expect
    toasts = lambda calls: [c[1] for c in calls if c[0] == 'toast']
    rec = '#EXTM3U\n#EXTINF:-1,Rec One\nhttp://rec.example/1\n#EXTINF:-1,Rec Two\nhttp://rec.example/2\n'
    x = lambda m, n: m.props.get((m.widgets[n], 'x'), 214)
    m = page_machine(view=None); m.put_text(RECENT, rec); open_radio(m); np_widgets(m)
    tap_row(m, 2, root=True, gap=24)
    expect(rows_text(m) == ['Rec One', 'Rec Two'] and vis(m, 'btn_more') == (1, 1) and vis(m, 'btn_radioview') == (1, 1) and vis(m, 'btn_search') == (0, 0)
           and (x(m, 'btn_more'), x(m, 'btn_radioview'), x(m, 'btn_backtoplayer')) == (168, 214, 260) and icon_of(m, 'btn_backtoplayer') == 'ah_nav_play'
           and icon_of(m, 'btn_radioview') == 'pod_nav_grid', 'Recently Played: the capsule [... | toggle | Now Playing] as My Stations has it (the "..." 168, the toggle 214, Now Playing 260), no Search')
    click(m, 'btn_more')
    expect(vis(m, 'rd_sh_card') == (1, 1) and vis(m, 'rd_sh_scrim') == (1, 1) and vis(m, 'rd_sh_clear') == (1, 1) and m.props.get((m.widgets['rd_sh_import'], 'visible'), 0) == 0 and vis(m, 'rd_sh_clear_hr')[0] == 0
           and m.props.get((m.widgets['rd_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1', 'the "..." opens a one-row sheet: Clear Recently Played, not Import from Card')
    m.calls.clear(); click(m, 'btn_return')
    expect(vis(m, 'rd_sh_card') == (0, 0) and ('navigator_back',) not in m.calls and rows_text(m) == ['Rec One', 'Rec Two'] and RECENT in m.fs and b'Rec One' in m.fs[RECENT], 'Back with the sheet open closes the sheet only')
    click(m, 'btn_more'); click(m, 'rd_sh_scrim')
    expect(vis(m, 'rd_sh_card') == (0, 0) and vis(m, 'rd_sh_clear') == (0, 0) and b'Rec One' in m.fs[RECENT], 'the scrim closes it; nothing cleared')
    click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_clear')
    expect(toasts(calls) == ['Cleared Recently Played'] and m.fs[RECENT] == b'#EXTM3U\n' and RECENT + '.tmp' not in m.fs and vis(m, 'rd_sh_card') == (0, 0),
           f'Clear Recently Played: the toast, radio-recent emptied through the atomic writer, the sheet closed ({toasts(calls)}, {m.fs[RECENT]!r})')
    expect(text_of(m, 'label_status') == 'No recently played stations' and vis(m, 'label_status') == (1, 1) and vis(m, 'view_grid') == (0, 0) and vis(m, 'btn_radioview') == (0, 0)
           and vis(m, 'btn_more') == (1, 1) and x(m, 'btn_more') == 214 and x(m, 'btn_backtoplayer') == 260 and text_of(m, 'sg_title') == 'Recently Played',
           'the list refreshed in place: the caption, the "..." on the 214 slot, no toggle (as an empty My Stations)')
    # the empty level keeps the "..." and Clear still works (nothing to clear: the same toast)
    m.calls.clear(); click(m, 'btn_more'); calls = click(m, 'rd_sh_clear')
    expect(toasts(calls) == ['Cleared Recently Played'] and text_of(m, 'label_status') == 'No recently played stations', 'Clear on the empty level: the same toast and caption')
    m.calls.clear(); click(m, 'btn_return')
    expect(('navigator_back',) not in m.calls and rows_text(m)[:3] == ['My Stations', 'Recently Played', 'Radio Browser'] and vis(m, 'btn_more') == (0, 0), 'Back from the empty caption: the root, the page stays, no "..."')
    # opening Recently Played with the file empty or missing: the caption and the "..." at once
    for state in (b'#EXTM3U\n', None):
        m = page_machine(view=None)
        if state is not None: m.put_text(RECENT, state)
        open_radio(m); tap_row(m, 1, root=True)
        expect(text_of(m, 'label_status') == 'No recently played stations' and vis(m, 'btn_more') == (1, 1) and x(m, 'btn_more') == 214 and vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (0, 0)
               and x(m, 'btn_backtoplayer') == 260, f'Recently Played with {"an empty" if state else "no"} file: the caption, the "..." on 214, Now Playing the right cap')
    # a playing station goes on and the root keeps its Now Playing row
    m = page_machine(view=None); l, r = play(m)
    expect(RECENT in m.fs and b'One' in m.fs[RECENT] and r == 1, 'a station plays: it is in the recent file')
    open_radio(m); np_widgets(m)
    tap_row(m, 2, root=True, gap=24)
    expect(rows_text(m) == ['One'], f'Recently Played lists it ({rows_text(m)})')
    m.proc = []; m.calls.clear(); click(m, 'btn_more'); calls = click(m, 'rd_sh_clear')
    expect(toasts(calls) == ['Cleared Recently Played'] and m.call(PSYMS['rd_running']) == 1 and m.call(PSYMS['rd_state']) == ST['CONNECTING'] and not stops(m) and m.fs[RECENT] == b'#EXTM3U\n',
           'clearing does not stop the station')
    click(m, 'btn_return')
    expect(rows_text(m)[:3] == ['Now Playing', 'My Stations', 'Recently Played'], 'the root still has its Now Playing row')
    # nothing running: Clear takes the root's Now Playing row with it (the history is the last played)
    m = page_machine(view=None); m.put_text(RECENT, rec); open_radio(m)
    expect(rows_text(m)[0] == 'Now Playing', 'idle with a recent station: the Now Playing row')
    tap_row(m, 2, root=True, gap=24); click(m, 'btn_more'); click(m, 'rd_sh_clear'); click(m, 'btn_return')
    expect(rows_text(m) == ['My Stations', 'Recently Played', 'Radio Browser'], f'Clear Recently Played with nothing running: the Now Playing row is gone ({rows_text(m)})')
    # a card/settings write that fails: the list stays and says so
    m = page_machine(view=None); m.put_text(RECENT, rec); open_radio(m); tap_row(m, 2, root=True, gap=24)
    m.fail.add(('rename', RECENT)); click(m, 'btn_more'); m.calls.clear()
    calls = click(m, 'rd_sh_clear')
    expect(toasts(calls) == ['Could not clear Recently Played'] and rows_text(m) == ['Rec One', 'Rec Two'] and b'Rec One' in m.fs[RECENT], f'a write that cannot be made: "Could not clear Recently Played", the list as it was ({toasts(calls)})')
    # the toggle still works on this level and the mode is shared
    m = page_machine(view=None); m.put_text(RECENT, rec); open_radio(m); tap_row(m, 2, root=True, gap=24)
    click(m, 'btn_radioview')
    expect(grid_titles(m) == ['Rec One', 'Rec Two'] and m.fs.get(VIEW) == b'1\n', 'the toggle on Recently Played switches the mode')


def np_machine(**kw):
    m = machine()
    m.window = NP_WIN
    m.top_main = NP_WIN   # pod_is_top: the page is in front
    np_widgets(m)
    for k, v in kw.items(): setattr(m, k, v)
    return m


def np_state(m):
    """The two labels' texts as the page left them."""
    return {n: u8(m.wtext.get(m.widgets[n])) for n in ('rn_title', 'rn_artist')}


def np_tests(ctx):
    """11. Radio's Now Playing."""
    expect = ctx.expect
    m = np_machine()
    l, r = play(m)
    m.call(PSYMS['rn_open'], count=900000000)
    s = np_state(m)
    expect(s == {'rn_title': 'One', 'rn_artist': 'Connecting…'} and vis(m, 'rn_live')[0] == 1, f'connecting: the station\'s name, Connecting… under it, the LIVE divider ({s})')
    expect(('timer_add', PSYMS['rn_tick'], 500) in m.calls, 'one 500 ms page timer')
    pic = lambda n, st='normal': m.props.get((m.widgets[n], f'style:{st}:bg_image'))
    expect(pic('btn_play') == 'rn_stop' and pic('btn_play', 'pressed') == 'rn_stop_down', 'running: the one button is the stop square')
    m.clock += 2000; m.hs = 1
    poll(m)
    m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    s = np_state(m)
    expect(s == {'rn_title': 'One', 'rn_artist': 'Germany · MP3 128k'}, f'playing: the station\'s name over "Country · CODEC 128k" (no stream title reaches demo) ({s})')
    m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'widget_set_text_utf8'], 'a tick with nothing new writes no label text (a scrolling label keeps its place)')
    m.ps = 3; m.hs = 0; m.clock += 500
    poll(m); m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(np_state(m)['rn_artist'] == 'Paused' and pic('btn_play') == 'rn_play' and pic('btn_play', 'pressed') == 'rn_play_down', 'paused from outside (the mini bar, a key): "Paused", the button turns play')
    m.proc = []; m.wifi = 3; click(m, 'btn_play')
    expect(m.proc == [('mclSetResume',)] and state(m) == ST['PAUSED'], f'play while Paused: stock\'s resume, not a restart or a stop ({m.proc})')
    m.ps = 2; m.hs = 1; m.clock += 500
    poll(m); m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(pic('btn_play') == 'rn_stop', 'playing again: the stop square')
    # a station with no info: an empty line
    m2 = np_machine(); l2 = new_list(m2, '#EXTM3U\n#EXTINF:-1,Bare FM\nhttp://bare.example/s\n'); m2.call(PSYMS['rd_play'], a0=l2, a1=0, count=40000000)
    m2.call(PSYMS['rn_open'], count=900000000)
    m2.clock += 2000; m2.hs = 1
    poll(m2); m2.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(np_state(m2) == {'rn_title': 'Bare FM', 'rn_artist': ''}, f'a station with no info: an empty line ({np_state(m2)})')
    # the round "..." and its sheet: the favourite
    m.put_text(FAVS, '#EXTM3U\n#EXTINF:-1,One\nhttp://one.example/a\n')
    calls = click(m, 'rn_more')
    expect(vis(m, 'rd_sh_card') == (1, 1) and vis(m, 'rd_sh_scrim') == (1, 1) and text_of(m, 'rd_sh_add_tx') == 'Remove from My Stations' and ('image_base_set_image', m.widgets['rd_sh_add_ic'], 'pod_ic_rd_remove') in [c[:3] for c in calls],
           'the "..." opens the sheet: a station that is in the file says Remove from Stations')
    click(m, 'rd_sh_scrim')
    expect(vis(m, 'rd_sh_card') == (0, 0) and vis(m, 'rd_sh_add') == (0, 0), 'the scrim closes it')
    click(m, 'rn_more')
    calls = click(m, 'rd_sh_add')
    expect(any(c[0] == 'toast' and c[1] == 'Removed from My Stations' for c in calls) and b'One' not in m.fs[FAVS] and vis(m, 'rd_sh_card') == (0, 0), 'Remove: out of favourites.m3u, the toast, the sheet closed')
    click(m, 'rn_more')
    expect(text_of(m, 'rd_sh_add_tx') == 'Add to My Stations', 'then it offers Add to Stations')
    calls = click(m, 'rd_sh_add')
    expect(any(c[0] == 'toast' and c[1] == 'Added to My Stations' for c in calls) and b'One' in m.fs[FAVS], 'Add: appended, the toast')
    click(m, 'rn_more'); calls = click(m, 'btn_return')
    expect(vis(m, 'rd_sh_card') == (0, 0) and ('navigator_back',) not in calls, 'Back with the sheet open closes the sheet only')
    # next / previous still step along the list (hidden buttons: the hardware keys come later)
    click(m, 'btn_next')
    expect(m.call(PSYMS['rd_at']) == 1 and np_state(m)['rn_title'] == 'Two', 'next: the second station')
    click(m, 'btn_next'); click(m, 'btn_next')
    expect(m.call(PSYMS['rd_at']) == 0, 'next past the last: the first')
    click(m, 'btn_prev')
    expect(m.call(PSYMS['rd_at']) == 2, 'previous before the first: the last')
    # play / stop
    calls = click(m, 'btn_play')
    expect(m.call(PSYMS['rd_state']) == ST['STOPPED'] and pic('btn_play') == 'rn_play' and pic('btn_play', 'pressed') == 'rn_play_down' and vis(m, 'rn_live')[0] == 0 and np_state(m)['rn_artist'] == 'Stopped',
           'the button on a running station stops it: Stopped, the play triangle, no LIVE divider')
    m.proc = []
    click(m, 'btn_play')
    expect(starts(m) == ['http://three.example/c'] and m.call(PSYMS['rd_state']) == ST['CONNECTING'], 'and starts it again')
    # an error
    m.clock += 20000; poll(m); m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    s = np_state(m)
    expect(m.call(PSYMS['rd_state']) == ST['ERROR'] and s['rn_title'] == 'Three' and s['rn_artist'] == "Can't play: No response", f"an error: the state's words replace the line ({s})")
    # the screen dark or the page covered: no work
    m.screen(False); m.calls.clear(); m.clock += 100000
    m.call(PSYMS['rn_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] == 'widget_set_text_utf8'], 'a dark screen: the tick does nothing')
    m.screen(True)
    # Back and destroy
    calls = click(m, 'btn_return')
    expect(('navigator_back',) in calls, 'the grabber goes back')
    destroy_np(m)
    expect(('timer_remove', 0x777) in m.calls, 'destroy removes the timer')
    m.calls.clear()
    expect(m.call(PSYMS['rn_tick'], a0=0, count=4000000) == 0, 'a timer that fires after the page was destroyed ends')
    # the page leaves nothing running when the radio goes on without it
    m = np_machine()
    l, r = play(m)
    m.call(PSYMS['rn_open'], count=900000000)
    destroy_np(m)
    expect(m.call(PSYMS['rd_running']) == 1, 'closing the page leaves the station playing (the engine owns the playback)')
    # the station's logo in the art box
    csv = 'name,url,url_resolved,favicon,country,codec,bitrate\nLogo FM,http://a.example/s,,https://l.example/a.png,DE,MP3,128\nPlain FM,http://b.example/s,,,DE,MP3,128\n'
    m = np_machine()
    m.put_text(FAVS, '')
    lst = new_list(m, csv, 1)
    m.calls = []; m.proc = []
    m.call(PSYMS['rd_play'], a0=lst, a1=0, count=40000000)
    m.call(PSYMS['rn_open'], count=900000000)
    ha = m.call(PSYMS['rd_logo_hash'], a0=m.buf('https://l.example/a.png'), count=100000)
    lp = f'{RADIO_DIR}/.logos/{ha:08x}.jpg'
    expect(vis(m, 'rn_art_ic')[0] == 1 and m.call(PSYMS['rd_logo_running'], count=100000) == 1, 'no logo yet: the glyph stays, the logo worker is asked for it')
    m.curl_site = lambda u, o: {'body': b'GIF89a'}
    m.put(lp, jpeg_header(192)); m.sizes[lp] = 4000; m.load_image = 0
    m.canvas = m.alloc(0x80)
    m.images['file://' + lp] = (192, 192, struct.pack('<I', 0xff2233ee) * (192 * 192))
    m.call(PSYMS['rn_tick'], a0=0, count=400000000)
    expect(vis(m, 'rn_art_ic')[0] == 0, 'the logo is made: the glyph goes, the logo is decoded once')
    st = [x for x in m.styled if x[1] == 'normal:bg_color']
    tone = [v for w, n, v in st if w == m.window][-1]
    expect(tone not in (0xff202020, 0xffffffff) and (m.widgets['rn_art'], 'normal:bg_color', 0xffffffff) in st, f'the window takes the logo\'s tone ({tone:#x}) and the card is white')
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.blits.clear()
    fn, ctx_ = m.bound[(m.widgets['rn_art'], O['EVT_AFTER_PAINT'])]
    m.call(fn, a0=ctx_, a1=ev, count=40000000)
    expect(len(m.blits) == 1 and m.blits[0][2][:4] == (36, 36, 192, 192), f'the logo is drawn centred in the art box ({m.blits})')
    m.call(PSYMS['rn_tick'], a0=0, count=400000000)
    expect(m.names().count('bitmap_create_ex') == 0, 'a tick decodes nothing more')
    m.proc = []
    click(m, 'btn_next')
    expect(vis(m, 'rn_art_ic')[0] == 1, 'the next station has no logo: the glyph is back')
    st = [x for x in m.styled if x[1] == 'normal:bg_color']
    expect([v for w, n, v in st if w == m.window][-1] == 0xff202020 and [v for w, n, v in st if w == m.widgets['rn_art']][-1] == 0xff2e2c2c, 'with the neutral grey window and the grey card')
    destroy_np(m)
    expect(m.destroyed >= 1, 'destroy frees the logo bitmap')
    # opening twice, a window that will not open, an asset that is not ours
    m = np_machine(); l, r = play(m)
    expect(m.call(PSYMS['rn_open'], count=900000000) == 0 and m.call(PSYMS['rn_open'], count=900000000) == 0 and m.names().count('window_open') == 0, 'a second open while the page is up opens nothing')
    # the bug: a page that is closing (destroyed later) or under another window did not reopen
    W2 = 0x25000000
    m = np_machine(); l, r = play(m)
    m.call(PSYMS['rn_open'], count=900000000)
    old = m.window
    m.home_opened = 0   # closing: AWTK keeps the window until a later EVT_DESTROY
    m.window = m.top_main = W2; m.calls.clear()
    expect(m.call(PSYMS['rn_open'], count=900000000) == 0 and m.names().count('window_open') == 1, 'a closing page: a fresh window opens')
    expect(('window_close', old) not in m.calls, 'a closing page is not closed again')
    m.home_opened = 1; m.calls.clear()
    destroy_np(m, old)   # the old window's late EVT_DESTROY
    expect(m.call(PSYMS['rn_open'], count=900000000) == 0 and m.names().count('window_open') == 0 and m.call(PSYMS['rn_tick'], a0=0, count=4000000) != 0,
           'the old window\'s late destroy leaves the new page\'s state alone (still open, timer alive)')
    destroy_np(m, W2)
    expect(m.call(PSYMS['rn_tick'], a0=0, count=4000000) == 0, 'the new window\'s own destroy clears it')
    m = np_machine(); l, r = play(m)
    m.call(PSYMS['rn_open'], count=900000000)
    old = m.window; m.window = W2; m.top_main = 0x26000000   # still open, but under another window
    m.calls.clear()
    expect(m.call(PSYMS['rn_open'], count=900000000) == 0 and m.names().count('window_open') == 1 and ('window_close', old) in m.calls,
           'under another window: the old page is closed and a fresh one opens')
    m = np_machine(window=0)
    expect(m.call(PSYMS['rn_open'], count=900000000) == 0xffffffff, 'a window that will not open: -1')
    m = np_machine(); m.widgets.pop('rn_live')
    m.call(PSYMS['rn_open'], count=900000000)
    expect(('navigator_back',) in m.calls, 'an asset that is not ours: the page leaves again')


SI_WIN = 0x20003000
SI_WIDGETS = ('ri_view', 'img_nb_fade', 'label_head', 'label_key', 'label_val', 'btn_backtoplayer')
INFO_CSV = ('name,url,url_resolved,favicon,country,codec,bitrate\nLogo FM,http://a.example/s,,https://l.example/a.png,Germany,MP3,128\n'
            'Bare FM,http://b.example/s,,,,,0\n')


def info_machine(text=INFO_CSV, kind=1, i=0, **kw):
    """Radio Now Playing up on a station of the list, Station Info's window and widgets ready (the page itself opens from the sheet: info_go)."""
    m = np_machine(**kw)
    lst = new_list(m, text, kind); m.call(PSYMS['rd_play'], a0=lst, a1=i, count=40000000)
    m.call(PSYMS['rn_open'], count=900000000)
    m.windows['m1plus_radioinfo'] = SI_WIN
    for n in SI_WIDGETS: Machine.widget(m, n)
    m.sv = m.alloc(0x100); m.widgets['ri_scrollview'] = m.sv
    m.canvas = m.alloc(0x80)
    return m


def info_go(m):
    click(m, 'rn_more')
    calls = click(m, 'rd_sh_info')
    m.top_main = SI_WIN
    m.go_calls = calls   # (every m.call clears m.calls: painting loses them)
    return calls


def info_height(m):
    """The content view's last height the payload set."""
    return [c[3] for c in m.go_calls if c[0] == 'widget_resize' and c[1] == m.widgets['ri_view']][-1]


def info_paint(m, off=0):
    """One EVT_AFTER_PAINT of the content view at scroll offset off: [(style, text, absolute y)]."""
    m.setword(m.sv + SC_YOFF, off)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.texts.clear(); m.text_styles.clear()
    fn, c = m.bound[(m.widgets['ri_view'], O['EVT_AFTER_PAINT'])]
    m.call(fn, a0=c, a1=ev, count=40000000)
    return [(s, u8(t), r[1] + off) for (t, r), s in zip(m.texts, m.text_styles)]


def info_all(m):
    """Every text of the page, scrolled through in 100 px steps: [(style, text, y)] by y."""
    seen = {}
    for off in range(0, 2000, 100):
        for s, t, y in info_paint(m, off): seen[(y, s, t)] = 1
    return [(s, t, y) for y, s, t in sorted(seen)]


def info_pairs(m):
    """{label: value} from the painted blocks (the value lines joined), and the heading."""
    heading, pairs, key = '', {}, None
    for s, t, y in info_all(m):
        if s == 'label_head': heading += t
        elif s == 'label_key': key = t; pairs[key] = ''
        elif s == 'label_val': pairs[key] += t
    return heading, pairs


def info_tests(ctx):
    """12a. Station Info: the sheet's second row, the page's pairs, wrapping, the live status, Back."""
    expect = ctx.expect
    m = info_machine()
    calls = click(m, 'rn_more')
    expect(vis(m, 'rd_sh_add') == (1, 1) and vis(m, 'rd_sh_info') == (1, 1) and vis(m, 'rd_sh_add_hr')[0] == 0 and vis(m, 'rd_sh_info_hr')[0] == 1
           and ('widget_move', m.widgets['rd_sh_info'], 0, O['PM_ROW_H']) in calls and ('widget_move', m.widgets['rd_sh_card'], 0, O['AH_WIN_H'] - 2 * O['PM_ROW_H']) in calls
           and ('widget_resize', m.widgets['rd_sh_card'], 320, 2 * O['PM_ROW_H']) in calls and m.props.get((m.widgets['rd_sh_card'], 'style:normal:bg_image')) == 'pc_sheet2',
           "the round '...' opens a two-row sheet: Add to / Remove from My Stations, then Station Info under a hairline (pc_sheet2, two rows high)")
    click(m, 'rd_sh_scrim')
    expect(vis(m, 'rd_sh_info') == (0, 0) and vis(m, 'rd_sh_card') == (0, 0) and ('window_open', 'm1plus_radioinfo') not in m.calls, 'the scrim closes both rows and opens nothing')
    calls = info_go(m)
    expect(('window_open', 'm1plus_radioinfo') in calls and vis(m, 'rd_sh_card') == (0, 0) and vis(m, 'rd_sh_info') == (0, 0) and ('timer_add', PSYMS['sinfo_tick'], 500) in calls
           and info_height(m) > 400, 'the row closes the sheet and opens Station Info (seven pairs: more than the 400 px list shows), with a 500 ms page timer')
    expect(m.props.get((m.sv, 'virtual_h')) == info_height(m), 'the scroll view is as tall as the content')
    heading, pairs = info_pairs(m)
    expect(heading == 'Logo FM' and pairs == {'Stream URL': 'http://a.example/s', 'Logo URL': 'https://l.example/a.png', 'Country': 'Germany', 'Codec': 'MP3', 'Bitrate': '128 kbps',
                                              'Source': 'Radio Browser', 'Status': 'Connecting…'}, f'the heading is the station name; the pairs in order with their values ({heading!r}, {pairs})')
    allt = info_all(m)
    expect([t for s, t, y in allt if s == 'label_key'] == ['Stream URL', 'Logo URL', 'Country', 'Codec', 'Bitrate', 'Source', 'Status'], 'the labels in the asked order')
    ys = [y for s, t, y in allt]
    expect(ys == sorted(ys) and len(set(ys)) == len(ys), 'every line has a place of its own, top to bottom')
    # the styles: heading, label, value
    expect({s for s, t, y in allt} == {'label_head', 'label_key', 'label_val'}, 'three text styles: the heading, the small grey label, the white value')
    # a station without a logo, codec or bitrate: those pairs are left out; imported
    m = info_machine(INFO_CSV, 1, 1); info_go(m)
    heading, pairs = info_pairs(m)
    expect(heading == 'Bare FM' and pairs == {'Stream URL': 'http://b.example/s', 'Source': 'Radio Browser', 'Status': 'Connecting…'}, f'empty fields (and a bitrate of 0) are omitted ({pairs})')
    m = info_machine(STATIONS, 0, 1); info_go(m)
    heading, pairs = info_pairs(m)
    expect(heading == 'Two' and pairs == {'Stream URL': 'https://two.example/b', 'Source': 'Imported', 'Status': 'Connecting…'}, f'a station with no directory info: Source "Imported" ({pairs})')
    m = info_machine(STATIONS, 0, 0); info_go(m)
    heading, pairs = info_pairs(m)
    expect(pairs.get('Country') == 'Germany' and pairs.get('Codec') == 'MP3' and pairs.get('Bitrate') == '128 kbps' and 'Logo URL' not in pairs and pairs.get('Source') == 'Radio Browser', f'a station with #M1+ info but no logo: no Logo URL pair, Source Radio Browser ({pairs})')
    # long values wrap at 36 chars (8 px each in 288 px): the address shows in full, a long name in at most three lines
    long_url = 'http://stream.example.com/' + 'x' * 150 + '?a=1&b=2'
    long_logo = 'https://img.example.com/' + 'y' * 90 + '.png'
    csv = f'name,url,url_resolved,favicon,country,codec,bitrate\n{"Very " * 30}Long,{long_url},,{long_logo},Germany,MP3,128\n'
    m = info_machine(csv); info_go(m)
    vals = [(t, y) for s, t, y in info_all(m) if s == 'label_val']
    heading, pairs = info_pairs(m)
    expect(pairs['Stream URL'] == long_url and pairs['Logo URL'] == long_logo and all(len(t) <= 36 for t, y in vals) and sum(t.startswith(('http://stream', 'xxxx')) or 'x' in t for t, y in vals) >= 5,
           f'a long address wraps by characters over several lines and shows in full, no ellipsis ({[t for t, y in vals][:6]})')
    heads = [t for s, t, y in info_all(m) if s == 'label_head']
    expect(len(heads) == 3 and heads[-1].endswith('…') and all(len(t) <= 36 for t in heads), f'a long name: at most three heading lines, the last with an ellipsis ({heads})')
    expect(info_height(m) > 400 and m.props.get((m.sv, 'virtual_h')) == info_height(m), f'the content scrolls: the view is taller than the 400 px list ({info_height(m)})')
    # words wrap at spaces
    csv = 'name,url,url_resolved,favicon,country,codec,bitrate\nShort,http://a.example/s,,,Democratic Republic of the Congo and more,MP3,128\n'
    m = info_machine(csv); info_go(m)
    lines = [t for s, t, y in info_all(m) if s == 'label_val' and 'Democratic' in t or s == 'label_val' and 'more' in t]
    expect(lines and all(len(t) <= 36 for t in lines) and not any(t.startswith(' ') or t.endswith(' ') for t in lines), f'a value with spaces wraps at the spaces ({lines})')
    # the scroll: the nav fade shows once scrolled
    m = info_machine(); info_go(m); m.calls.clear()
    info_paint(m, 0)
    expect(not any(c[0] == 'widget_set_visible' and c[1] == m.widgets['img_nb_fade'] and c[2] for c in m.calls), 'at rest the fade is not shown')
    info_paint(m, 40)
    expect(any(c[0] == 'widget_set_visible' and c[1] == m.widgets['img_nb_fade'] and c[2] == 1 for c in m.calls), 'scrolled: the fade under the navbar shows')
    # the status is live
    m = info_machine(); info_go(m)
    status = lambda: info_pairs(m)[1]['Status']
    m.clock += 2000; m.hs = 1; poll(m); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(status() == 'Playing', f'playing: Status Playing ({status()})')
    m.ps = 3; m.hs = 0; m.clock += 500; poll(m); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(status() == 'Paused', f'paused from outside: Paused ({status()})')
    m.calls.clear(); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(not any(c[0] in ('widget_resize', 'widget_invalidate_force') for c in m.calls), 'a tick with nothing new lays nothing out again')
    m.call(PSYMS['rd_stop'], count=40000000); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(status() == 'Stopped', f'stopped: Stopped ({status()})')
    l2 = new_list(m, INFO_CSV, 1); m.call(PSYMS['rd_play'], a0=l2, a1=0, count=40000000); m.clock += 20000; poll(m); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(m.call(PSYMS['rd_state']) == ST['ERROR'] and status() == 'No response', f'an error: its text ({status()})')
    heading, pairs = info_pairs(m)
    expect(heading == 'Logo FM' and pairs['Stream URL'] == 'http://a.example/s', 'the other pairs are as they were')
    m.screen(False); m.clock += 100000; l3 = new_list(m, INFO_CSV, 1); m.call(PSYMS['rd_play'], a0=l3, a1=0, count=40000000); m.calls.clear()
    m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(status() == 'No response' and not any(c[0] == 'widget_resize' for c in m.calls), 'a dark screen: the tick does nothing')
    m.screen(True)
    # a Status that wraps changes the height
    m = info_machine(); info_go(m)
    m.hs = 0; m.clock += 20000; poll(m); m.call(PSYMS['sinfo_tick'], a0=0, count=40000000)
    expect(any(c[0] == 'widget_resize' and c[1] == m.widgets['ri_view'] for c in m.calls), 'the content is sized again when the status changes')
    # Back returns to Radio Now Playing (the sheet is closed); Now Playing opens it from the disc
    m = info_machine(); info_go(m); m.calls.clear()
    calls = click(m, 'btn_return')
    expect(('navigator_back',) in calls and vis(m, 'rd_sh_card') == (0, 0), 'Back goes back (to Radio Now Playing, whose sheet is closed)')
    m = info_machine(); info_go(m); m.calls.clear()
    calls = click(m, 'btn_backtoplayer')
    expect(('window_open', 'm1plus_radionp') in calls and not [c for c in calls if c[0] == 'on_backtoplayer_onclick'], 'the Now Playing disc opens Radio Now Playing while a station runs')
    # destroy: the timer goes, a late tick ends; the page reopens
    m = info_machine(); info_go(m)
    fn, c = m.bound[(SI_WIN, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=4000000)
    expect(('timer_remove', 0x777) in m.calls and m.call(PSYMS['sinfo_tick'], a0=0, count=4000000) == 0, 'destroy removes the timer; a tick that fires later ends')
    m.top_main = NP_WIN
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0 and ('window_open', 'm1plus_radioinfo') in m.calls, 'and the page opens again')
    m.top_main = SI_WIN
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0 and m.names().count('window_open') == 0, 'a second open while it is up (on top) opens nothing')
    # a closing page (destroyed later) is replaced; its late destroy leaves the new page alone
    m = info_machine(); info_go(m)
    old = SI_WIN; W2 = 0x25100000
    m.windows['m1plus_radioinfo'] = W2; m.top_main = 0x26100000; m.calls.clear()
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0 and m.names().count('window_open') == 1 and ('window_close', old) in m.calls, 'under another window: the old page is closed and a fresh one opens')
    m.top_main = W2; m.calls.clear()
    fn, c = m.bound[(old, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=4000000)
    expect(m.call(PSYMS['sinfo_tick'], a0=0, count=4000000) != 0, "the old window's late destroy leaves the new page alone")
    # no station, a window that will not open, an asset that is not ours
    m = np_machine(); m.windows['m1plus_radioinfo'] = SI_WIN
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0xffffffff and ('window_open', 'm1plus_radioinfo') not in m.calls, 'no station: -1, no window')
    m = info_machine(); m.windows['m1plus_radioinfo'] = 0; m.calls.clear()
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0xffffffff, 'a window that will not open: -1')
    m = info_machine(); m.widgets.pop('label_val'); m.calls.clear()
    expect(m.call(PSYMS['sinfo_open'], count=900000000) == 0xffffffff and ('navigator_back',) in m.calls, 'an asset that is not ours: the page leaves again')


def entry_tests(ctx):
    """12. Every Now Playing entry opens Radio Now Playing while a station connects or plays (hook 17, rn_backtoplayer, and pod_open_now_playing)."""
    expect = ctx.expect
    import pod_pages
    stock_calls = lambda m: [c for c in m.calls if c[0] == 'on_backtoplayer_onclick']
    opens = lambda m: m.names().count('window_open')
    entries = (('pod_open_now_playing', {}), ('pod_on_player', {'a0': 0, 'a1': 0}), ('rn_backtoplayer', {'a0': 0, 'a1': 0}))
    for fn, kw in entries:
        m = np_machine(); m.call(PSYMS[fn], count=900000000, **kw)
        expect(len(stock_calls(m)) == 1 and not opens(m), f'{fn}: no station, stock Now Playing through the trampoline')
        m = np_machine(); l, r = play(m); m.call(PSYMS[fn], count=900000000, **kw)
        expect(not stock_calls(m) and opens(m) == 1 and ('window_open', 'm1plus_radionp') in m.calls, f'{fn}: a station connecting: Radio Now Playing opens, stock does not')
        m.call(PSYMS[fn], count=900000000, **kw)
        expect(not stock_calls(m) and not opens(m), f'{fn}: Radio Now Playing already up: no second copy, no stock page')
        m = np_machine(); l, r = play(m); poll(m); m.call(PSYMS["rd_stop"], count=40000000); m.call(PSYMS[fn], count=900000000, **kw)
        expect(len(stock_calls(m)) == 1 and not opens(m), f'{fn}: stopped after playing: stock')
        m = np_machine(window=0); l, r = play(m); m.call(PSYMS[fn], count=900000000, **kw)
        expect(len(stock_calls(m)) == 1, f'{fn}: Radio Now Playing will not open: stock Now Playing')
    m = np_machine(); l, r = play(m)
    expect(m.call(PSYMS['rn_backtoplayer'], a0=0, a1=0, count=900000000) == 0 and m.call(PSYMS['pod_on_player'], a0=0, a1=0, count=900000000) == 0, 'the handlers answer RET_OK')
    # the Home menu's Now Playing row (patch/m1plus.c)
    page = next(p for p in pod_pages.PAGES if p.key == 'm1plus_menu')
    row = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_PLAYER)
    m = np_machine(); m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * row, count=900000000)
    expect(len(stock_calls(m)) == 1 and not opens(m), 'Home Now Playing row, no station: stock')
    m = np_machine(); l, r = play(m); m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * row, count=900000000)
    expect(not stock_calls(m) and ('window_open', 'm1plus_radionp') in m.calls, 'Home Now Playing row, a station plays: Radio Now Playing')
    # the hook as built: pinned prologue, `j rn_backtoplayer; nop`, the word the trampoline resumes at is stock's, $gp restored
    A = pod.BACKTOPLAYER
    stock = open(os.path.join(paths.find_stock() or os.path.join(os.path.dirname(WORK), 'stock'), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    expect(A == 0x4cd58c and pod.BACKTOPLAYER_PROLOGUE == (0x3c1c0053, 0x279c6944, 0x0399e021) and tuple(w(stock, A + 4 * i) for i in range(3)) == pod.BACKTOPLAYER_PROLOGUE,
           'stock has the three PIC prologue words the hook pins (on_backtoplayer_onclick)')
    expect(0x530000 + 0x6944 + A == pod.GP, 'the prologue computes $gp = 0xa03ed0')
    expect((w(built, A), w(built, A + 4), w(built, A + 8)) == (pod.j(PSYMS['rn_backtoplayer']), 0, pod.BACKTOPLAYER_PROLOGUE[2]) and w(built, A + 12) == w(stock, A + 12) == 0x27bdffd0,
           'the built demo has `j rn_backtoplayer; nop` over the first two prologue words and stock\'s addiu sp at the resume point')
    expect(MANIFEST['hook_backtoplayer'] == {'addr': A, 'target': PSYMS['rn_backtoplayer']}, 'the manifest records the hook')
    t = struct.unpack_from('<4I', open(os.path.join(BUILD, 'patch.bin'), 'rb').read(), PSYMS['stock_backtoplayer_trampoline'] - pod.BASE)
    expect(t == (0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(A + 12), 0), 'the trampoline restores $gp and resumes stock at the 4th instruction')
    expect(any(a == 0x4cd598 for a, *_ in pod.RADIO_PINS), 'the resume word is pinned')


def stations_csv(n, logos=False):
    return 'name,url,url_resolved,favicon,country,codec,bitrate\n' + ''.join(
        f'S{i},http://s{i}.example/s,,{"https://l.example/%d.png" % i if logos else ""},Germany,MP3,128\n' for i in range(n))


def top_stations(m, n=40, logos=False):
    """The Top Stations level with n stations (the answer of the directory)."""
    m.answer = stations_csv(n, logos).encode(); sites_of(m)
    tap_dir(m, 0); finish(m); tick(m)


def set_off(m, off): m.setword(m.sv + SC_YOFF, off)
def get_off(m): return m.s32(m.sv + SC_YOFF)
def icon_of(m, n, st='normal'): return m.props.get((m.widgets[n], f'style:{st}:icon'))


def view_tests(ctx):
    """13. The station lists' list / grid toggle (the Albums page's): the mode file, the geometry of the list, the navbar slots, the toggle, logos and the credit."""
    expect = ctx.expect
    # ---- the asset: a hidden toggle on the 214 slot, the Albums one
    root = ui('m1plus_radio')
    def find(w, n):
        if w.name == n: return w
        for c in w.children:
            r = find(c, n)
            if r is not None: return r
    tg = find(root, 'btn_radioview')
    expect(tg is not None and (tg.x, tg.w) == (214, 46) and tg.get('visible') == 'false' and tg.get('sensitive') == 'false' and tg.get('style:normal:icon') == 'pod_nav_list',
           'the asset has the toggle, a 46 px button on the 214 slot, hidden and insensitive')
    # ---- the mode file: the list by default; "1" the grid; "0", garbage and an empty file the list
    for data, grid in ((None, 0), (b'0\n', 0), (b'1\n', 1), (b'1', 1), (b'x\n', 0), (b'', 0), (b'10', 0)):
        m = opened_view(data)
        top_stations(m, 3)
        got = 'grid' if grid_titles(m) else 'list'
        expect(got == ('grid' if grid else 'list'), f'radio-view {data!r}: the {"grid" if grid else "list"} ({got})')
    # ---- the list's geometry: Albums' list under the large title
    m = opened_view(None); top_stations(m, 40)
    blits, texts, fills = paint(m)
    names = [(t, r) for (t, r), s in texts if s == 'label_row_title']
    subs = [(t, r) for (t, r), s in texts if s == 'label_row_sub']
    expect(names[:3] == [(f'S{i}', (74, TOP + 64 * i + 9, 234, 24)) for i in range(3)] and subs[:2] == [('Germany · MP3 128k', (74, TOP + 64 * i + 35, 234, 20)) for i in range(2)],
           f'a row is 64 px: the name (21 px style) at x 74, y +9, the caption (18 px style) at y +35 ({names[:2]}, {subs[:1]})')
    covers = [b[2] for b in blits if b[2][2] == 52]
    expect(covers[:3] == [(10, TOP + 64 * i + 6, 52, 52) for i in range(3)], f'the 52 px logo tile at (10, 6) of its row ({covers[:3]})')
    hair = [f[2] for f in fills if f[0] == O['LIST_HAIR']]
    expect(hair[:3] == [TOP + 64 * i + 63 for i in range(3)] and not [f for f in fills if f[0] == O['LIST_PRESS']], f'a hairline under each row, no pressed fill at rest ({hair[:3]})')
    expect(not grid_titles(m) and len(names) <= 8, 'only the rows in view are painted')
    expect(vis(m, 'rd_credit') == (0, 0), 'Top Stations: no credit in the list either')
    # the logo-less tile: the grey card with the radio glyph, 52 px, the corners cut in the alpha (the pressed fill shows behind them)
    ph = next(b[0] for b in blits if b[2][2] == 52)
    px = struct.unpack('<%dI' % (52 * 52), m.u.mem_read(m.word(ph + 0x14), 52 * 52 * 4))
    glyph_px = [v for v in px[20 * 52 + 10: 20 * 52 + 42] if v != 0xff000000 | 0x2e2c2c]
    expect(px[0] >> 24 == 0 and px[51] >> 24 == 0 and px[52 * 51] >> 24 == 0 and px[52 * 52 - 1] >> 24 == 0 and px[26 * 52 + 26] >> 24 == 255 and px[4 * 52 + 4] == 0xff000000 | 0x2e2c2c
           and px[8 * 52 + 26] == 0xff000000 | 0x2e2c2c and glyph_px, 'the placeholder is the grey card with the glyph in its middle third, corners transparent')
    # ---- hit testing
    np_widgets(m)
    calls = tap(m, 300, TOP + 64 + 30)
    expect(m.call(PSYMS['rd_at']) == 1 and ('window_open', 'm1plus_radionp') in calls, 'a tap on the right end of row 1 plays station 1 and opens Now Playing (no per-row "...")')
    m = opened_view(None); top_stations(m, 40)
    np_widgets(m)
    m.calls.clear(); calls = tap(m, 100, 30)
    expect(('window_open', 'm1plus_radionp') not in calls, 'a tap on the large title plays nothing')
    m.calls.clear(); calls = tap(m, 100, TOP + 64 * 2 + 40, dy=30)
    expect(('window_open', 'm1plus_radionp') not in calls, 'a press that moved on is no tap')
    m.touch('down', 100, SCREEN_Y0 + TOP + 64 + 10, 1000, fn='rp_on_down')
    pr = [f for f in paint(m)[2] if f[0] == O['LIST_PRESS']]
    expect(pr == [(O['LIST_PRESS'], 0, TOP + 64, 320, 63)], f'a pressed row is filled #333333 over its first 63 lines ({pr})')
    m.touch('up', 100, SCREEN_Y0 + TOP + 64 + 10, 1080, fn='rp_on_up')
    # ---- toggle visibility and the capsule, level by level
    m = opened_view(None)
    expect(vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (0, 0) and icon_of(m, 'btn_backtoplayer') == 'ah_nav_np', 'the root: no toggle, no Search, Now Playing the glass disc alone')
    tap_row(m, 2, root=True)
    expect(vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (1, 1) and vis(m, 'btn_more') == (0, 0) and m.props.get((m.widgets['btn_search'], 'x'), 214) == 214 and icon_of(m, 'btn_backtoplayer') == 'ah_nav_play', 'Radio Browser: Search on the 214 slot, no toggle, no "..."')
    m.answer = COUNTRIES_CSV.encode(); sites_of(m); tap_row(m, 1, root=True); finish(m); tick(m)
    expect(vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (1, 1), 'By Country: no toggle, Search')
    click(m, 'btn_return')
    m.answer = GENRES_CSV.encode(); sites_of(m); tap_row(m, 2, root=True); finish(m); tick(m)
    expect(vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (1, 1), 'By Genre: no toggle, Search')
    click(m, 'btn_return'); click(m, 'btn_return')
    m.put_text(FAVS, FAV_TEXT)
    tap_row(m, 0, root=True)
    expect(vis(m, 'btn_radioview') == (1, 1) and vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_more') == (1, 1), 'Stations: the toggle and the "..." show, no Search (the directory is Radio Browser)')
    expect(m.props.get((m.widgets['btn_more'], 'x'), 214) == 168 and m.props.get((m.widgets['btn_radioview'], 'x'), 214) == 214 and m.props.get((m.widgets['btn_backtoplayer'], 'x'), 260) == 260,
           'the capsule [... | toggle | Now Playing]: "..." 168 (left cap, where Search sits), the toggle 214 (middle), Now Playing 260 (right cap)')
    expect(icon_of(m, 'btn_radioview') == icon_of(m, 'btn_radioview', 'over') == 'pod_nav_grid' and icon_of(m, 'btn_radioview', 'pressed') == 'pod_nav_grid_down'
           and icon_of(m, 'btn_backtoplayer') == 'ah_nav_play' and m.props[(m.widgets['label_title'], 'w')] == 168 - 58, 'the list shows the grid glyph (the mode a tap gives, the middle piece), Now Playing is the right cap, the small title ends at the "..."')
    click(m, 'btn_return')
    expect(vis(m, 'btn_radioview') == (0, 0) and vis(m, 'btn_search') == (0, 0) and vis(m, 'btn_more') == (0, 0), 'Back to the root: the toggle and the "..." go')
    m = opened_view(None); tap_row(m, 1, root=True)
    expect(vis(m, 'btn_search') == (0, 0), 'Recently Played (a caption here): no Search either')
    m = opened_view(None)
    # ---- the toggle: the mode, the glyph, the file
    top_stations(m, 40)
    expect(vis(m, 'btn_radioview') == (1, 1), 'Top Stations: the toggle shows')
    calls = click(m, 'btn_radioview')
    expect(grid_titles(m)[:2] == ['S0', 'S1'] and not rows_text(m) and m.fs.get(VIEW) == b'1\n' and VIEW_TMP not in m.fs, f'the toggle: the grid, "1" saved atomically ({m.fs.get(VIEW)!r})')
    expect(icon_of(m, 'btn_radioview') == 'pod_nav_list' and icon_of(m, 'btn_radioview', 'pressed') == 'pod_nav_list_down', 'the grid shows the list glyph')
    click(m, 'btn_radioview')
    expect(rows_text(m)[:2] == ['S0', 'S1'] and not grid_titles(m) and m.fs.get(VIEW) == b'0\n' and icon_of(m, 'btn_radioview') == 'pod_nav_grid', 'and back: the list, "0" saved, the grid glyph again')
    # a fresh page reads the saved choice
    click(m, 'btn_radioview')
    m2 = opened_view(m.fs[VIEW]); top_stations(m2, 3)
    expect(grid_titles(m2)[:2] == ['S0', 'S1'] and not rows_text(m2), 'a page opened later is in the saved mode')
    # ---- the first visible station stays; a coasting list stops
    for first in (10, 11, 25):
        m = opened_view(None); top_stations(m, 40)
        set_off(m, TOP + 64 * first)
        click(m, 'btn_radioview')   # to the grid
        off = get_off(m)
        expect(off == TOP + first // 2 * 200 and grid_titles(m)[0] == f'S{first // 2 * 2}', f'list row {first} at the top: the grid starts at its row ({off}, {grid_titles(m)[:1]})')
        click(m, 'btn_radioview')
        expect(get_off(m) == TOP + (first // 2 * 2) * 64 and rows_text(m)[0].startswith('S'), f'and back: the list at station {first // 2 * 2} ({get_off(m)})')
    m = opened_view(None); top_stations(m, 40)
    set_off(m, 20)
    click(m, 'btn_radioview')
    expect(get_off(m) == 20, 'the large title still showing: the offset stays')
    wa = m.alloc(0x80); m.u.mem_write(wa, bytes(0x80)); m.setword(wa + O['SC_AN_STATE'], O['SC_AN_RUNNING']); m.setword(wa + O['SC_AN_WIDGET'], m.sv); m.setword(m.sv + O['SC_WA'], wa)
    calls = click(m, 'btn_radioview')
    expect(('widget_animator_destroy', wa) in calls and ('stock_scroll_done', m.sv) in calls and m.word(m.sv + O['SC_WA']) == 0, 'a running scroll animation is stopped by the toggle')
    # a caption (Loading) or a level without stations: the toggle does nothing
    m = opened_view(None)
    m.fs.pop(VIEW, None); m.calls.clear(); m.call(m.bound[(m.widgets['btn_radioview'], O['EVT_CLICK'])][0], a0=0, a1=0, count=40000000)
    expect(VIEW not in m.fs, 'the toggle on the root changes nothing')
    # ---- the search results: the toggle as the left cap beside Now Playing, the credit at the mode's inset
    for view, cx, gl in ((None, 74, 'pod_nav_gridl'), (b'1\n', 12, 'pod_nav_listl')):
        m = opened_view(view); m.answer = stations_csv(3).encode(); sites_of(m)
        click_search(m)
        expect(vis(m, 'btn_radioview') == (0, 0), 'the search page before any result: no toggle')
        m.call(PSYMS['keyboard_set_text'], a0=m.buf('x'), count=4000000); m.call(PSYMS['rp_on_go'], count=40000000); finish(m); tick(m)
        expect(vis(m, 'btn_radioview') == (1, 1) and vis(m, 'btn_search') == (0, 0) and icon_of(m, 'btn_radioview') == gl and icon_of(m, 'btn_radioview', 'pressed') == gl + '_down'
               and icon_of(m, 'btn_backtoplayer') == 'ah_nav_play' and m.props.get((m.widgets['btn_radioview'], 'x'), 214) == 214, f'search results: the toggle is the left cap on 214 ({gl}), Now Playing the right cap')
        end_ = 48 + (3 * 64 if view is None else 2 * 200 - 10)
        cr = (m.props[(m.widgets['rd_credit'], 'x')], m.props[(m.widgets['rd_credit'], 'y')])
        expect(cr == (cx, end_ + 12) and vis(m, 'rd_credit') == (1, 1), f'the credit under the last {"row" if view is None else "cell"}, left at x {cx} ({cr})')
        click(m, 'btn_radioview')
        cr = (m.props[(m.widgets['rd_credit'], 'x')], m.props[(m.widgets['rd_credit'], 'y')])
        expect(cr[0] == (12 if view is None else 74) and vis(m, 'rd_credit') == (1, 1), f'after the toggle the credit follows the mode ({cr})')
    m = opened_view(None); m.put_text(FAVS, FAV_TEXT); tap_row(m, 0, root=True)
    expect(vis(m, 'rd_credit') == (0, 0), 'Stations in the list: no credit')
    # ---- logos follow the cells in view; the list reads two rows ahead; nothing decodes while the list moves
    def logo_machine(view, n=16):
        m = opened_view(view); m.screen(True); m.top_main = m.window
        top_stations(m, n, logos=True)
        for i in range(n):
            h = m.call(PSYMS['rd_logo_hash'], a0=m.buf(f'https://l.example/{i}.png'), count=100000)
            p = f'{RADIO_DIR}/.logos/{h:08x}.jpg'
            m.put(p, jpeg_header(52)); m.sizes[p] = 4000
            m.images[f'file://{p}'] = (52, 52, struct.pack('<I', 0xff2233ee) * (52 * 52))
        paint(m)
        return m
    def ticks(m, n):
        """n logo ticks: (logos decoded, workers started); every call starts a fresh call log."""
        d = w = 0
        for _ in range(n):
            m.call(PSYMS['rp_on_ltick'], a0=0, count=400000000)
            d += m.names().count('bitmap_create_ex'); w += m.names().count('pthread_create')
        return d, w
    m = logo_machine(None)
    got = ticks(m, 14)
    expect(got == (6 + 2, 0), f'the list decodes the six rows in view and two ahead, then rests ({got})')
    m = logo_machine(None)
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([1, 1]))
    expect(ticks(m, 4) == (0, 0), 'a dragged list decodes nothing')
    wa = m.alloc(0x80); m.u.mem_write(wa, bytes(0x80)); m.setword(wa + O['SC_AN_STATE'], O['SC_AN_RUNNING']); m.setword(wa + O['SC_AN_WIDGET'], m.sv); m.setword(m.sv + O['SC_WA'], wa)
    m.u.mem_write(m.sv + O['SC_PRESSED'], bytes([0, 0]))
    expect(ticks(m, 4) == (0, 0), 'a scroll animation decodes nothing')
    m = logo_machine(b'1\n')
    got = ticks(m, 14)
    expect(got == (4 + 2, 0), f'the grid decodes the four cells in view and the grid row after ({got})')


def nowifi_tests(ctx):
    """12. No Wi-Fi: every way a station starts says so at once (the Nowifi event), nothing connects, and the next start after Wi-Fi is back works."""
    expect = ctx.expect
    started = lambda m: [c for c in m.proc if c[0] == 'start']
    # ---- a tap / Retry (rd_play) from Idle: Error "No Wi-Fi", no attempt, local music untouched
    m = machine(); m.wifi = -1
    l, r = play(m)
    names = [c[0] for c in m.after]
    expect(r == 0 and state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m) and 'stop_player' not in names and 'timer_add' not in names and 'mclStop' not in [c[0] for c in m.proc]
           and m.call(PSYMS['rd_running']) == 0, f'Idle, Wi-Fi off: Error "No Wi-Fi" at once, no start, no timer, stock\'s player left alone ({r}, {state(m)}, {names})')
    expect(m.s32(m.call(PSYMS['rd_list']) + 8) >= 1 and m.call(PSYMS['rd_at']) == 0, 'the list and the position are kept, so Retry has a station')
    m.wifi = 4; m.proc = []
    r = m.call(PSYMS['rd_play'], a0=m.call(PSYMS['rd_list']), a1=0, count=40000000)
    expect(r == 1 and state(m) == ST['CONNECTING'] and starts(m) == ['http://one.example/a'], 'Wi-Fi back: the same Retry connects (nobody is stuck in Error)')
    # Wi-Fi level 0 is "no connection" too
    m = machine(); m.wifi = 0
    l, r = play(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m), 'get_wifisignal 0: no connection either')
    # ---- from Playing / Connecting: a tap on another station without Wi-Fi stops the stream and says so
    for how in ('up', 'play'):
        m = machine(); (up if how == 'up' else play)(m); m.proc = []; m.wifi = -1
        l, r = play(m, STATIONS, 1)
        expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m) and stops(m) == 1 and m.call(PSYMS['rd_running']) == 0, f'a station started from {how} without Wi-Fi: the stream is stopped, Error "No Wi-Fi"')
        expect(m.call(PSYMS['rd_at']) == 1, 'and the tapped station is the one a Retry plays')
    # ---- from Stopped / Error
    m = machine(); up(m); m.call(PSYMS['rd_stop'], count=4000000); m.wifi = -1; m.proc = []
    play(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m), 'from Stopped')
    play(m)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m) and stops(m) == 0, 'from Error: again, the same words')
    # ---- Resume of a paused station without Wi-Fi
    m = machine(); up(m); m.ps = 3; poll(m)
    expect(state(m) == ST['PAUSED'], 'a paused station')
    m.wifi = -1; m.proc = []; m.calls = []
    m.call(PSYMS['rd_resume'], count=4000000)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and stops(m) == 1 and ('mclSetResume',) not in m.proc, 'Resume without Wi-Fi: stopped, Error "No Wi-Fi", stock\'s resume not sent')
    m = machine(); up(m); m.ps = 3; poll(m); m.proc = []
    m.call(PSYMS['rd_resume'], count=4000000)
    expect(state(m) == ST['PAUSED'] and m.proc == [('mclSetResume',)], 'Resume with Wi-Fi: stock\'s resume')
    m = machine(); up(m); m.proc = []
    m.call(PSYMS['rd_resume'], count=4000000)
    expect(state(m) == ST['PLAYING'] and not m.proc, 'Resume while playing: nothing')
    # ---- an output change (Reroute, Reroute paused) without Wi-Fi
    for a0, what in ((0, 'Reroute'), (1, 'Reroute paused')):
        for mk in (up, play):
            m = machine(); mk(m)
            m.call(PSYMS['rd_save_stop'], count=4000000)
            m.setword(G_OUT, 1); m.wifi = -1; m.proc = []
            m.call(PSYMS['rd_save_start'], a0=a0, count=40000000)
            expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m), f'{what} without Wi-Fi ({mk.__name__}): Error "No Wi-Fi", no restart')
    m = machine(); up(m); m.ps = 3; poll(m); m.call(PSYMS['rd_save_stop'], count=4000000); m.wifi = -1; m.proc = []
    m.call(PSYMS['rd_save_start'], a0=1, count=40000000)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not started(m), 'Reroute paused from Paused without Wi-Fi: Error')
    # ---- the pages
    m = np_machine(); m.wifi = -1
    l, r = play(m)
    m.call(PSYMS['rn_open'], count=40000000)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi', 'Radio Now Playing opens on the error (its play button is the Retry)')
    m = opened(); m.wifi = -1; m.put_text(FAVS, FAV_TEXT); tap_row(m, 0, root=True); m.proc = []
    tap_row(m, 0)
    expect(state(m) == ST['ERROR'] and error(m) == 'No Wi-Fi' and not starts(m) and m.call(PSYMS['rd_running']) == 0, 'a tap in a station list without Wi-Fi: the error, nothing connects')
    m.wifi = 4
    tap_row(m, 0)
    expect(state(m) == ST['CONNECTING'] and m.call(PSYMS['rd_running']) == 1, 'and with Wi-Fi back the tap connects')


def retry_tests(ctx):
    """13. The directory tries again after a network failure; a tap on the failure asks again; our logo job yields and a podcast job is waited for 20 s."""
    expect = ctx.expect
    m = machine()
    def retry(rc, code, attempt): return m.call(PSYMS['rd_fetch_retry'], a0=rc & 0xffffffff, a1=code, a2=attempt, count=200000)
    grid = {(6, 0, 1): 1, (6, 0, 2): 2, (6, 0, 3): 0, (28, 0, 1): 1, (35, 0, 1): 1, (60, 0, 2): 2, (56, 0, 1): 1, (0, 503, 1): 1, (0, 500, 2): 2, (0, 503, 3): 0,
            (0, 404, 1): 0, (0, 400, 1): 0, (0, 200, 1): 0, (0, 301, 1): 0, (42, 0, 1): 0, (23, 0, 1): 0, (6, 0, 0): 0}
    bad = {k: (retry(*k), want) for k, want in grid.items() if retry(*k) != want}
    expect(not bad, f'retry rule (curl code, HTTP status, attempt) -> seconds: network, TLS and 5xx twice at 1 s and 2 s; 4xx, 3xx, 200, cancel (42, 23) and a third try never ({bad})')
    path = '/csv/stations/topvote/100?hidebroken=true'
    def run(site, cancel_on_sleep=None, log=False):
        m = machine()
        if log: m.present.add('/mnt/mmc/m1plus-log')
        r, sites = fetch(m, path, 1, site=site)
        if cancel_on_sleep: m.on_sleep = lambda n: cancel_on_sleep(m, n)
        finish(m)
        performs = [c for c in m.calls if c[0] == 'curl_perform']
        sleeps = [c[1] for c in m.calls if c[0] == 'sleep']
        inits = m.names().count('curl_easy_init'); cleans = m.names().count('curl_easy_cleanup')
        return m, performs, sleeps, inits, cleans
    m, p, sl, i, c = run(lambda url, o: {'rc': 6})
    l = new_list(m); r, err = take(m, l)
    expect(len(p) == 3 and sl == [1, 1, 1] and i == 3 and c == 3 and r == 0 and err == E['FAIL'], f'a network failure: three attempts, 1 s then 2 s apart, a fresh handle each, then a failure ({len(p)}, {sl}, {i}, {c}, {err})')
    n = [0]
    def flaky(url, o):
        n[0] += 1
        return {'rc': 28} if n[0] < 3 else {'body': TOP_CSV.encode()}
    m, p, sl, i, c = run(flaky)
    l = new_list(m); r, err = take(m, l)
    expect(len(p) == 3 and r == 1 and err == 0 and m.s32(l + 8) == 2, 'the third attempt answers: the stations are the list')
    n = [0]
    def once(url, o):
        n[0] += 1
        return {'rc': 35} if n[0] == 1 else {'body': TOP_CSV.encode()}
    m, p, sl, i, c = run(once)
    l = new_list(m); r, err = take(m, l)
    expect(len(p) == 2 and r == 1 and sum(sl) == 1, 'a failure then an answer: one more attempt after 1 s')
    for code in (404, 400, 410):
        m, p, sl, i, c = run(lambda url, o, k=code: {'code': k, 'body': b'x'})
        expect(len(p) == 1 and not sl, f'HTTP {code}: no retry')
    m, p, sl, i, c = run(lambda url, o: {'code': 503, 'body': b'busy'})
    l = new_list(m); r, err = take(m, l)
    expect(len(p) == 3 and r == 0 and err == E['FAIL'], 'HTTP 503 is tried three times, then a failure')
    n = [0]
    def late(url, o):
        n[0] += 1
        return {'code': 502, 'body': b'junk'} if n[0] == 1 else {'body': TOP_CSV.encode()}
    m, p, sl, i, c = run(late)
    l = new_list(m); r, err = take(m, l)
    got = [(m.read_cstr(m.word(l) + m.word(l + 16 + 4 * k))) for k in range(m.s32(l + 8))]
    expect(r == 1 and got == ['Alpha FM', 'Beta Radio'], f'a 502 body is not mixed into the answer of the next try ({got})')
    # the cancel: before the transfer (rc 42), and while the worker waits between tries
    m = machine(); r, sites = fetch(m, path, 1, site=lambda url, o: {'rc': 6})
    m.call(PSYMS['rd_fetch_cancel'], count=100000); finish(m)
    expect(len([c for c in m.calls if c[0] == 'curl_perform']) == 1 and not [c for c in m.calls if c[0] == 'sleep'], 'Back before the transfer ends: one attempt, no wait')
    m, p, sl, i, c = run(lambda url, o: {'rc': 6}, cancel_on_sleep=lambda mm, k: mm.nested(PSYMS['rd_fetch_cancel']))
    expect(len(p) == 1 and sl == [1], f'Back while the worker waits between tries: the wait ends and no further attempt ({len(p)}, {sl})')
    # the log line (opt-in file)
    m, p, sl, i, c = run(lambda url, o: {'rc': 28}, log=True)
    logged = m.fs.get('/mnt/mmc/m1plus.log', b'').decode('latin-1')
    expect('radio: directory' in logged and 'curl 28' in logged and 'attempts 3' in logged and path in logged, f'a failed fetch logs the final curl code, status and attempts when the log file exists ({logged!r})')
    m, p, sl, i, c = run(lambda url, o: {'rc': 28}, log=False)
    expect('/mnt/mmc/m1plus.log' not in m.fs, 'and nothing without it')
    m, p, sl, i, c = run(lambda url, o: {'body': TOP_CSV.encode()}, log=True)
    expect('/mnt/mmc/m1plus.log' not in m.fs, 'a good answer logs nothing')
    # ---- the page: Loading stays up during the retries, the failure caption, a tap asks again
    m = opened(); m.curl_site = lambda url, o: {'rc': 60}
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Loading…', 'the page says Loading while the worker tries')
    expect(m.props.get((m.widgets['label_status'], 'word_wrap')) in (1, True), 'the status label breaks at spaces (word_wrap), not mid-word')
    finish(m); tries = len([c for c in m.calls if c[0] == 'curl_perform']); tick(m)
    expect(text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.' and tries == 3, f'after the last try: the failure caption ({tries} tries)')
    sites = []; m.curl_site = lambda url, o: (sites.append(url), {'body': TOP_CSV.encode()})[1]
    m.calls = []
    m.touch('up', 160, SCREEN_Y0 + 160, 1000, fn='rp_on_retry')
    expect(text_of(m, 'label_status') == 'Loading…' and 'pthread_create' in m.names(), 'a tap on the caption fetches the same level again (Loading…)')
    m.touch('up', 160, SCREEN_Y0 + 160, 1100, fn='rp_on_retry')
    expect(m.names().count('pthread_create') == 0, 'a second tap while it loads starts nothing')
    finish(m); tick(m)
    expect(sites == ['https://all.api.radio-browser.info' + PATH_TOP] and grid_titles(m) == ['Alpha FM', 'Beta Radio'] and text_of(m, 'sg_title') == 'Top Stations', f'and the answer is the level it was asked for ({sites}, {grid_titles(m)})')
    # a country: the retry asks for the same country
    m = opened(); m.answer = COUNTRIES_CSV.encode(); sites_of(m)
    tap_dir(m, 1); finish(m); tick(m)
    sites = []; m.curl_site = lambda url, o: (sites.append(url), {'rc': 6})[1]
    tap(m, 100, 52 + 3 * 28 + 3 * 52 + 20)   # Germany
    finish(m); tick(m)
    expect(text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.', 'a country\'s stations that fail')
    sites.clear(); m.calls = []
    m.touch('up', 160, SCREEN_Y0 + 160, 1000, fn='rp_on_retry'); finish(m)
    expect(len(set(sites)) == 1 and '/bycountrycodeexact/' in sites[0], f'the retry asks for the same country ({sorted(set(sites))})')
    # no Wi-Fi: straight away, and a tap after Wi-Fi is back fetches
    m = opened(); m.wifi = -1
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'No Wi-Fi' and 'pthread_create' not in m.names() and vis(m, 'view_grid') == (0, 0), 'no Wi-Fi: the caption at once, no Loading, no worker')
    m.wifi = 4; m.answer = TOP_CSV.encode(); sites_of(m); m.calls = []
    m.touch('up', 160, SCREEN_Y0 + 160, 1000, fn='rp_on_retry')
    expect(text_of(m, 'label_status') == 'Loading…' and 'pthread_create' in m.names(), 'Wi-Fi back: a tap on the caption fetches')
    # an answer with no station is final: a tap does nothing
    m = opened(); m.answer = b'changeuuid,name,url\n'; sites_of(m)
    tap_dir(m, 0); finish(m); tick(m); m.calls = []
    m.touch('up', 160, SCREEN_Y0 + 160, 1000, fn='rp_on_retry')
    expect(text_of(m, 'label_status') == 'No stations' and 'pthread_create' not in m.names(), '"No stations": a tap asks nothing')
    # the search fetch fails: the same tap (the typed query)
    # ---- a logo job yields at once; a podcast job is waited for about 20 s
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    r = m.call(PSYMS['rd_logo_start'], a0=m.buf('https://logo.example/a.png'), count=40000000)
    tap_dir(m, 0)
    expect(r == 1 and text_of(m, 'label_status') == 'Loading…' and m.names().count('pthread_create') == 0, 'a logo job in the way is asked to end; the directory fetch is next')
    finish(m); tick(m)
    expect(m.names().count('pthread_create') == 1, 'and starts on the first tick after it ended')
    m = opened(); m.answer = TOP_CSV.encode(); sites_of(m)
    m.setword(PSYMS['pn'], 1)   # a podcast refresh is running (pn.busy, kind 0)
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'Loading…' and m.names().count('pthread_create') == 0, 'a podcast job in the way: the page waits')
    for _ in range(79): tick(m)
    expect(text_of(m, 'label_status') == 'Loading…', 'about twenty seconds of asking again (80 ticks of 250 ms, the 80th gives up)')
    expect(tick(m) == 0 and text_of(m, 'label_status') == 'Directory unavailable. Tap to try again.', 'then it gives up with the tap-to-retry caption')
    m.setword(PSYMS['pn'], 0); sites_of(m); m.calls = []
    m.touch('up', 160, SCREEN_Y0 + 160, 1000, fn='rp_on_retry')
    expect(text_of(m, 'label_status') == 'Loading…' and 'pthread_create' in m.names(), 'the podcast job is over: a tap fetches')
    m = opened(); m.setword(PSYMS['pn'], 1); m.wifi = -1
    tap_dir(m, 0)
    expect(text_of(m, 'label_status') == 'No Wi-Fi', 'Wi-Fi is checked before a busy podcast job: "No Wi-Fi" at once')
    m = machine(); m.setword(PSYMS['pn'], 1)
    r, _ = fetch(m, path, 1)
    expect(r == E['PODBUSY'], 'rd_fetch: a podcast job in the way is RD_E_PODBUSY')


SECTIONS = [parsers_tests, table_tests, play_tests, poll_tests, stop_tests, reroute_tests, fetch_tests, card_tests, asset_tests, open_tests, levels_tests, directory_tests, search_tests, logo_tests, favs_tests, np_tests, info_tests, entry_tests, view_tests, nowifi_tests, retry_tests]


def run(ctx):
    for section in SECTIONS: section(ctx)
